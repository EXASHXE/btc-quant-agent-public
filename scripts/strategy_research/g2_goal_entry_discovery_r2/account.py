"""Single-position whole account replay with cash accounting for Goal A R2.

Enforces:
- 1x max exposure: budget = 0.95 * min(cash, 1000.0).
- 0.001 LOT, 5.0 USDT minimum notional.
- Exchange ACK quantization and 4h post-exit cooldown.
- Full minute-by-minute Mark MTM valuation curve.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

from .book import (
    HOUR,
    LOT,
    MIN_NOTIONAL,
    MINUTE,
    TradeExecutionError,
    _effective,
    _fee,
    _index,
    _slippage,
    execute_position,
)


def size_position(
    raw_open: float,
    atr_hour: float,
    cost: dict[str, float],
    cash: float,
    horizon_hours: int,
) -> tuple[float, dict[str, float]]:
    """Determine position size ensuring 1x exposure and conservative reserves."""
    budget = 0.95 * min(cash, 1000.0)
    worst = max(
        _effective(raw_open, 1, cost, True),
        _effective(raw_open + 0.25 * atr_hour, 1, cost, True),
    )
    fee_buf = worst * float(cost.get("fee_bps", 0.0)) / 10_000.0
    reserve_buf = 1.10 * worst * (
        float(cost.get("fee_bps", 0.0))
        + 0.5 * float(cost.get("spread_bps", 0.0))
        + _slippage(cost)
    ) / 10_000.0
    fund_buf = 1.10 * raw_open * 8.0 * horizon_hours / 10_000.0

    per_unit = worst + fee_buf + reserve_buf + fund_buf
    quantity = math.floor(budget / per_unit / LOT + 1e-10) * LOT

    if quantity <= 0 or (quantity * raw_open) < MIN_NOTIONAL:
        raise TradeExecutionError("Insufficient size or minimum notional breached")

    return quantity, {
        "budget": budget,
        "per_unit": per_unit,
        "reserved_notional": quantity * worst,
        "fee_buffer": quantity * fee_buf,
        "reserve_buffer": quantity * reserve_buf,
        "fund_buffer": quantity * fund_buf,
    }


def compute_mark_curve(
    trades: list[dict[str, Any]],
    mark_1m: np.ndarray,
    start_ms: int,
    end_ms: int,
    cash0: float,
    cost: dict[str, float],
) -> dict[str, Any]:
    """Compute continuous 1m Mark liquidation-equity valuation curve."""
    first = _index(mark_1m, start_ms)
    last = _index(mark_1m, end_ms - MINUTE)
    close_clocks = mark_1m[first : last + 1, 0] + MINUTE - 1
    values = np.full(len(close_clocks), cash0, dtype=float)

    peak_exposure = 0.0
    breaches = 0
    occupied = 0
    cash = cash0
    cursor = 0

    for t in trades:
        ie = _index(mark_1m, t["entry_at"]) - first
        values[cursor:ie] = cash
        final = _index(mark_1m, t["exit_ack_at"] // MINUTE * MINUTE) - first

        for i in range(ie, min(final + 1, len(values))):
            clock = int(close_clocks[i])
            if clock < t["exit_at"]:
                # Position open
                raw_mark = float(mark_1m[first + i, 4])
                liq = _effective(raw_mark, t["side"], cost, False)
                marked_pnl = t["side"] * (liq - t["effective_entry"]) * t["quantity"] - _fee(liq, t["quantity"], cost)
                # Funding cash up to this minute
                f_cash = sum(float(f["cash_delta"]) for f in t["funding_events"] if f["settlement_at"] <= clock)
                val = cash + marked_pnl + f_cash
                occupied += 1
                ratio = (raw_mark * t["quantity"]) / max(val, 1e-6)
                peak_exposure = max(peak_exposure, ratio)
                if ratio > 1.0 + 1e-9:
                    breaches += 1
            else:
                # Exited, waiting for ACK
                val = cash + float(t["net_after_funding_usdt"])

            if val <= 0:
                raise ValueError("Nonpositive marked account equity")
            values[i] = val

        cash += float(t["net_after_funding_usdt"])
        cursor = final + 1

    if cursor < len(values):
        values[cursor:] = cash

    peaks = np.maximum.accumulate(np.r_[cash0, values])
    drawdowns = (peaks - np.r_[cash0, values]) / peaks

    return {
        "ending_equity": float(cash),
        "min_mark_equity": float(np.min(values)),
        "max_mtm_drawdown_pct": float(np.max(drawdowns) * 100.0),
        "max_exposure_ratio": float(peak_exposure),
        "exposure_above_1x_minutes": int(breaches),
        "occupied_minutes": int(occupied),
        "occupancy_fraction": float(occupied / len(values)) if len(values) > 0 else 0.0,
    }


def replay_account(
    last_1m: np.ndarray,
    mark_1m: np.ndarray,
    rates: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    candidate: dict[str, Any],
    fold: dict[str, Any],
    cost: dict[str, float],
    cash0: float = 1000.0,
) -> dict[str, Any]:
    """Single-position whole-account replay across a monthly fold."""
    cash = cash0
    next_allowed = fold["start_ms"]
    trades = []
    fates = Counter()
    rejected = []
    horizon_hours = int(candidate.get("horizon_hours", 12))
    cooldown_hours = int(candidate.get("cooldown_hours", 4))

    # Sort signals strictly chronologically
    sorted_signals = sorted(signals, key=lambda s: (int(s["entry_at"]), str(s["event_id"])))

    for s in sorted_signals:
        t_entry = int(s["entry_at"])

        if t_entry < next_allowed:
            fates["POSITION_ACK_OR_COOLDOWN"] += 1
            rejected.append({"event_id": s["event_id"], "reason": "POSITION_ACK_OR_COOLDOWN"})
            continue

        # Prospective fold censoring: full trade deadline + ACK must fit in fold
        if t_entry + horizon_hours * HOUR + MINUTE >= fold["end_ms"]:
            fates["PROSPECTIVE_FOLD_CENSOR"] += 1
            rejected.append({"event_id": s["event_id"], "reason": "PROSPECTIVE_FOLD_CENSOR"})
            continue

        # Sizing check
        try:
            qty, reserve = size_position(
                s["raw_entry"],
                s["atr_hour"],
                cost,
                cash,
                horizon_hours,
            )
        except TradeExecutionError as exc:
            fates["ENTRY_OR_SIZE_REJECTED"] += 1
            rejected.append({"event_id": s["event_id"], "reason": "ENTRY_OR_SIZE_REJECTED", "detail": str(exc)})
            continue

        # Execute position
        try:
            t = execute_position(
                last_1m,
                mark_1m,
                rates,
                s,
                candidate,
                cost,
                qty,
            )
        except TradeExecutionError as exc:
            fates["EXECUTION_REJECTED"] += 1
            rejected.append({"event_id": s["event_id"], "reason": "EXECUTION_REJECTED", "detail": str(exc)})
            continue

        if t["exit_ack_at"] >= fold["end_ms"]:
            fates["PROSPECTIVE_FOLD_CENSOR"] += 1
            rejected.append({"event_id": s["event_id"], "reason": "PROSPECTIVE_FOLD_CENSOR"})
            continue

        after_cash = cash + float(t["net_after_funding_usdt"])
        if after_cash <= 0:
            raise ValueError("Nonpositive closing cash after trade")

        t["cash_before_entry"] = cash
        t["cash_after_ack"] = after_cash
        t["reserve"] = reserve

        trades.append(t)
        cash = after_cash
        fates["FILLED"] += 1

        next_allowed = max(t["exit_ack_at"], t["exit_at"] + cooldown_hours * HOUR)

    account_stats = compute_mark_curve(trades, mark_1m, fold["start_ms"], fold["end_ms"], cash0, cost)

    return {
        "trades": trades,
        "fates": dict(fates),
        "skipped_event_ids": rejected,
        **account_stats,
    }
