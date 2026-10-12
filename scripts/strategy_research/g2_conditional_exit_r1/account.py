"""Single-position 1x sidecar account simulator for G2 Conditional Exit R1."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    HOUR,
    LOT,
    MIN_NOTIONAL,
    MINUTE,
    _effective,
    _fee,
    _index,
    _proposed,
    _slippage,
)

from .conditional_book import PartialIneligibleError, execute_conditional_position
from .contract import ALL_SCHEMES

PROSPECTIVE_HORIZON_HOURS = {
    "E0": 12,
    "H1": 18,
    "X1_NET_POSITIVE_AT_12H": 18,
    "X2_COMPLETED_4H_TREND_AT_12H": 18,
}


def path_eligible(entry_at: int, fold_end_ms: int, hours: int = 18) -> bool:
    """Prospective full deadline OPEN plus ACK must fall strictly inside fold_end_ms."""
    return entry_at + hours * HOUR + MINUTE < fold_end_ms


def size_position(
    last: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    cash: float,
) -> tuple[float, dict[str, float]]:
    """Original R3 12h admission and reservation (1x, 5% reserve, 0.001 lot, 5 USDT min notional)."""
    configured = {**candidate, "horizon_hours": 12}
    p = _proposed(last, event, configured, cost)
    budget = 0.95 * min(cash, 1000.0)
    raw = float(p["raw_entry"])
    worst = max(
        float(p["effective_entry"]),
        _effective(raw + 0.25 * float(event["atr_hour"]), 1, cost, True),
    )
    fee = worst * float(cost["fee_bps"]) / 10_000.0
    reserve = (
        1.10
        * worst
        * (float(cost["fee_bps"]) + 0.5 * float(cost["spread_bps"]) + _slippage(cost))
        / 10_000.0
    )
    fund = 1.10 * raw * 8.0 * 12 / 10_000.0
    per_unit = worst + fee + reserve + fund
    q = math.floor(budget / per_unit / LOT + 1e-10) * LOT
    if q <= 0 or q * raw < MIN_NOTIONAL:
        raise PartialIneligibleError("SIZE_OR_MIN_NOTIONAL")
    if q * float(p["effective_entry"]) + _fee(float(p["effective_entry"]), q, cost) > budget + 1e-8:
        raise ValueError("Entry would breach 1x/5%-reserve budget")
    return q, {
        "budget": budget,
        "per_unit": per_unit,
        "reserved_notional": q * worst,
        "exit_cost_reserve": q * reserve,
        "funding_reserve": q * fund,
    }


def mark_curve(
    trades: list[dict[str, Any]],
    mark: np.ndarray,
    start_ms: int,
    end_ms: int,
    cash0: float,
    cost: dict[str, float],
) -> dict[str, Any]:
    """Compute minute-by-minute liquidation mark equity curve across [start_ms, end_ms)."""
    first = _index(mark, start_ms)
    last_idx = _index(mark, end_ms - MINUTE)
    close_clocks = mark[first : last_idx + 1, 0] + MINUTE - 1
    values = np.full(len(close_clocks), cash0, dtype=float)
    peak_exposure = 0.0
    breaches = 0
    occupied = 0
    cash = cash0
    cursor = 0

    for t in trades:
        ie = _index(mark, int(t["entry_at"])) - first
        if ie < cursor or int(t["exit_ack_at"]) >= end_ms:
            raise ValueError("Overlapping trade or exit ACK leaked fold")
        values[cursor:ie] = cash
        final = _index(mark, int(t["exit_ack_at"]) // MINUTE * MINUTE) - first
        for i in range(ie, final + 1):
            clock = int(close_clocks[i])
            settled = cash + sum(
                float(j["cash_delta"]) for j in t["journal"] if int(j["timestamp"]) <= clock
            )
            remaining = float(t["quantity"]) - sum(
                float(x["quantity"]) for x in t["tiers"] if int(x["exit_at"]) <= clock
            )
            if remaining < -1e-10:
                raise ValueError("Negative remaining quantity on mark curve")
            pending = sum(
                int(t["side"])
                * (float(x["effective_exit"]) - float(t["effective_entry"]))
                * float(x["quantity"])
                for x in t["tiers"]
                if int(x["exit_at"]) <= clock < int(x["exit_ack_at"])
            )
            if remaining > 1e-10:
                raw = float(mark[first + i, 4])
                liq = _effective(raw, int(t["side"]), cost, False)
                value = (
                    settled
                    + pending
                    + int(t["side"]) * (liq - float(t["effective_entry"])) * remaining
                    - _fee(liq, remaining, cost)
                )
                occupied += 1
                ratio = raw * remaining / value
                peak_exposure = max(peak_exposure, ratio)
                breaches += int(ratio > 1.0 + 1e-9)
            else:
                value = settled + pending
            if value <= 0:
                raise ValueError("Nonpositive marked account equity")
            values[i] = value
        cash += float(t["net_after_funding_usdt"])
        if abs(values[final] - cash) >= 1e-7:
            raise ValueError("Ending trade ACK equity diverges from settled cash")
        cursor = final + 1

    values[cursor:] = cash
    peaks = np.maximum.accumulate(np.r_[cash0, values])
    return {
        "curve": np.column_stack((close_clocks, values)),
        "ending_equity": cash,
        "min_mark_equity": float(np.min(values)),
        "max_mtm_drawdown_pct": float(np.max((peaks - np.r_[cash0, values]) / peaks) * 100.0),
        "max_exposure_ratio": peak_exposure,
        "exposure_above_1x_minutes": int(breaches),
        "occupied_minutes": occupied,
        "occupancy_fraction": occupied / len(values),
    }


def replay_fold(
    last: np.ndarray,
    mark: np.ndarray,
    rates: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    candidate: dict[str, Any],
    fold: dict[str, Any],
    cost: dict[str, float],
    scheme: str,
    cash0: float,
    *,
    partial_tp1_fraction: float | None = None,
) -> dict[str, Any]:
    """Replay one monthly fold for a single-position 1x account."""
    if scheme not in ALL_SCHEMES:
        raise ValueError(f"Unregistered scheme in replay_fold: {scheme}")

    start_ms = int(fold["start_ms"])
    end_ms = int(fold["end_ms"])
    cash = float(cash0)
    next_allowed = start_ms
    trades: list[dict[str, Any]] = []
    fates: Counter[str] = Counter()
    rejected: list[dict[str, Any]] = []
    prospective_hours = PROSPECTIVE_HORIZON_HOURS[scheme]
    cooldown_ms = int(candidate.get("cooldown_hours", 6)) * HOUR

    for e in sorted(signals, key=lambda x: (int(x["entry_at"]), str(x["event_id"]))):
        entry_at = int(e["entry_at"])
        if not (start_ms <= entry_at < end_ms):
            continue
        if entry_at < next_allowed:
            fates["POSITION_ACK_OR_COOLDOWN"] += 1
            rejected.append({
                "event_id": e["event_id"],
                "entry_at": entry_at,
                "reason": "POSITION_ACK_OR_COOLDOWN",
                "next_allowed_at": next_allowed,
            })
            continue
        if not path_eligible(entry_at, end_ms, prospective_hours):
            fates["PROSPECTIVE_FOLD_CENSOR"] += 1
            rejected.append({
                "event_id": e["event_id"],
                "entry_at": entry_at,
                "reason": "PROSPECTIVE_FOLD_CENSOR",
                "prospective_hours": prospective_hours,
                "fold_end_ms": end_ms,
            })
            continue
        try:
            q, reserve = size_position(last, e, candidate, cost, cash)
        except ValueError as exc:
            expected = (
                "late entry breached quarter-hour-ATR gap veto",
                "Stop is on wrong side of entry",
                "Effective stop risk is nonpositive",
            )
            if not isinstance(exc, PartialIneligibleError) and str(exc) not in expected:
                raise
            reason = "ENTRY_OR_SIZE_REJECTED"
            fates[reason] += 1
            rejected.append({
                "event_id": e["event_id"],
                "entry_at": entry_at,
                "reason": reason,
                "detail": str(exc),
            })
            continue

        try:
            t = execute_conditional_position(
                last,
                mark,
                rates,
                e,
                candidate,
                cost,
                scheme,
                q,
                partial_tp1_fraction=partial_tp1_fraction,
            )
        except PartialIneligibleError as exc:
            fates["INELIGIBLE_PARTIAL_SIZE"] += 1
            rejected.append({
                "event_id": e["event_id"],
                "entry_at": entry_at,
                "reason": "INELIGIBLE_PARTIAL_SIZE",
                "detail": str(exc),
            })
            continue

        if int(t["exit_ack_at"]) >= end_ms:
            raise ValueError("Full path admitted but exit ACK leaked fold")
        if abs(sum(float(j["cash_delta"]) for j in t["journal"]) - float(t["net_after_funding_usdt"])) >= 1e-7:
            raise ValueError("Journal cash delta sum does not match net_after_funding_usdt")

        after = cash + float(t["net_after_funding_usdt"])
        if after <= 0:
            raise ValueError("Nonpositive closing cash")
        t.update({
            "cash_before_entry": cash,
            "cash_after_ack": after,
            "reserve": reserve,
        })
        trades.append(t)
        cash = after
        fates["FILLED"] += 1
        next_allowed = max(int(t["exit_ack_at"]), int(t["exit_at"]) + cooldown_ms)

    account = mark_curve(trades, mark, start_ms, end_ms, cash0, cost)
    if abs(account["ending_equity"] - cash) >= 1e-7:
        raise ValueError("Account curve ending equity diverges from closing cash")
    return {
        "trades": trades,
        "fates": dict(fates),
        "skipped_event_ids": rejected,
        **account,
    }
