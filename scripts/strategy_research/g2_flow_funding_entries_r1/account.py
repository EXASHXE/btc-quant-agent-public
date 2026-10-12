"""Deterministic 1x cash account replay, position sizing, risk controls, and marked equity curves.

Enforces:
- 1x max notional exposure
- 5% cash reservation (95% budget cap)
- 0.001 BTC lot discretization
- 5.0 USDT minimum notional
- 4h cooldown between trades
- 24h prospective fold embargo to prevent fold boundary leakage
- Point-in-time cash balance updates only at exit ACK
"""
from __future__ import annotations

import calendar
import math
from collections import Counter
from typing import Any

import numpy as np

from .book import (
    HOUR,
    LOT,
    MIN_NOTIONAL,
    MINUTE,
    _effective,
    _fee,
    _index,
    _slippage,
    execute_position,
    propose_entry,
)


def get_folds() -> list[dict[str, Any]]:
    """Return the 35 evaluation monthly folds from 2021-02 through 2023-12."""
    folds = []
    fold_idx = 0
    for y in (2021, 2022, 2023):
        start_m = 2 if y == 2021 else 1
        for m in range(start_m, 13):
            start = calendar.timegm((y, m, 1, 0, 0, 0)) * 1000
            days_in_month = calendar.monthrange(y, m)[1]
            end = start + days_in_month * 86_400_000
            folds.append({
                "fold_index": fold_idx,
                "year": y,
                "month": m,
                "name": f"{y}-{m:02d}",
                "start_ms": start,
                "end_ms": end,
            })
            fold_idx += 1
    assert len(folds) == 35, f"Expected 35 folds, got {len(folds)}"
    return folds


def path_eligible(entry_at: int, fold_end_ms: int, hours: int = 24) -> bool:
    """Prospective full deadline plus ACK must complete strictly before fold end."""
    return entry_at + hours * HOUR + MINUTE < fold_end_ms


def compute_size(
    last: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    cash: float,
) -> tuple[float, dict[str, float]]:
    """Compute 1x position size under 5% cash reserve and conservative cost buffers."""
    proposal = propose_entry(last, event, candidate, cost)
    budget = 0.95 * min(cash, 1000.0)
    raw = proposal["raw_entry"]
    worst = max(proposal["effective_entry"], _effective(raw + 0.25 * float(event["atr_hour"]), 1, cost, True))
    fee = worst * cost["fee_bps"] / 10_000.0
    reserve = 1.10 * worst * (cost["fee_bps"] + 0.5 * cost["spread_bps"] + _slippage(cost)) / 10_000.0
    fund = 1.10 * raw * 8.0 * int(candidate.get("horizon_hours", 12)) / 10_000.0
    per_unit = worst + fee + reserve + fund

    q = math.floor(budget / per_unit / LOT + 1e-10) * LOT
    if q <= 0 or q * raw < MIN_NOTIONAL:
        raise ValueError(f"SIZE_OR_MIN_NOTIONAL: q={q}, notional={q * raw}")
    assert q * proposal["effective_entry"] + _fee(proposal["effective_entry"], q, cost) <= budget + 1e-8

    return q, {
        "budget": budget,
        "per_unit": per_unit,
        "reserved_notional": q * worst,
        "exit_cost_reserve": q * reserve,
        "funding_reserve": q * fund,
    }


def compute_marked_equity_curve(
    trades: list[dict[str, Any]],
    mark: np.ndarray,
    start_ms: int,
    end_ms: int,
    cash0: float,
    cost: dict[str, float],
) -> dict[str, Any]:
    """Compute minute-by-minute marked equity curve, peak exposure, and MTM drawdown."""
    first = _index(mark, start_ms)
    last = _index(mark, end_ms - MINUTE)
    close_clocks = mark[first:last + 1, 0] + MINUTE - 1
    values = np.full(len(close_clocks), cash0, dtype=float)

    peak_exposure = 0.0
    breaches = 0
    occupied = 0
    cash = cash0
    cursor = 0

    for t in trades:
        ie = _index(mark, t["entry_at"]) - first
        assert ie >= cursor and t["exit_ack_at"] < end_ms
        values[cursor:ie] = cash
        final = _index(mark, t["exit_ack_at"] // MINUTE * MINUTE) - first

        for i in range(ie, final + 1):
            clock = int(close_clocks[i])
            settled = cash + sum(float(j["cash_delta"]) for j in t["journal"] if j["timestamp"] <= clock)
            # Full position is held until exit_at
            remaining = t["quantity"] if clock < t["exit_at"] else 0.0
            pending = (t["gross_usdt"] - t["execution_drag_usdt"] - t["fee_exit"]) if (t["exit_at"] <= clock < t["exit_ack_at"]) else 0.0

            if remaining > 1e-10:
                raw_m = float(mark[first + i, 4])
                liq = _effective(raw_m, t["side"], cost, False)
                unrealized = t["side"] * (liq - t["effective_entry"]) * remaining - _fee(liq, remaining, cost)
                val = settled + pending + unrealized
                occupied += 1
                ratio = raw_m * remaining / val if val > 0 else 999.0
                peak_exposure = max(peak_exposure, ratio)
                breaches += ratio > 1.0 + 1e-8
            else:
                val = settled + pending

            if val <= 0:
                raise ValueError("Nonpositive marked account equity")
            values[i] = val

        cash += float(t["net_after_funding_usdt"])
        assert abs(values[final] - cash) < 1e-6, f"Ending cash discrepancy: {values[final]} vs {cash}"
        cursor = final + 1

    values[cursor:] = cash
    peaks = np.maximum.accumulate(np.r_[cash0, values])
    drawdowns = (peaks - np.r_[cash0, values]) / peaks

    return {
        "curve": np.column_stack((close_clocks, values)),
        "ending_equity": cash,
        "min_mark_equity": float(np.min(values)),
        "max_mtm_drawdown_pct": float(np.max(drawdowns) * 100.0),
        "max_exposure_ratio": peak_exposure,
        "exposure_above_1x_minutes": int(breaches),
        "occupied_minutes": occupied,
        "occupancy_fraction": occupied / len(values) if len(values) > 0 else 0.0,
    }


def replay_account(
    last: np.ndarray,
    mark: np.ndarray,
    funding_events: list[dict[str, Any]],
    signals: list[dict[str, Any]],
    candidate: dict[str, Any],
    folds: list[dict[str, Any]],
    cost: dict[str, float],
    initial_cash: float = 1000.0,
) -> dict[str, Any]:
    """Execute chronological account replay across all 35 folds.

    Maintains continuous cash equity between folds while enforcing fold boundaries.
    """
    cash = initial_cash
    cooldown_hours = int(candidate.get("cooldown_hours", 4))
    horizon_hours = int(candidate.get("horizon_hours", 12))

    all_executed_trades: list[dict[str, Any]] = []
    all_rejected: list[dict[str, Any]] = []
    fates: Counter[str] = Counter()
    fold_summaries: list[dict[str, Any]] = []

    # Sort signals strictly chronologically
    sorted_signals = sorted(signals, key=lambda s: (s["entry_at"], s["event_id"]))

    for fold in folds:
        fold_start = fold["start_ms"]
        fold_end = fold["end_ms"]
        next_allowed = fold_start
        fold_trades: list[dict[str, Any]] = []
        cash_start_fold = cash

        # Filter signals belonging to this fold by entry_at
        fold_sigs = [s for s in sorted_signals if fold_start <= s["entry_at"] < fold_end]

        for sig in fold_sigs:
            # Single-position and cooldown constraint
            if sig["entry_at"] < next_allowed:
                fates["POSITION_ACK_OR_COOLDOWN"] += 1
                all_rejected.append({
                    "event_id": sig["event_id"],
                    "fold": fold["name"],
                    "reason": "POSITION_ACK_OR_COOLDOWN",
                })
                continue

            # 24h prospective fold embargo
            if not path_eligible(sig["entry_at"], fold_end, hours=max(24, horizon_hours)):
                fates["PROSPECTIVE_FOLD_CENSOR"] += 1
                all_rejected.append({
                    "event_id": sig["event_id"],
                    "fold": fold["name"],
                    "reason": "PROSPECTIVE_FOLD_CENSOR",
                })
                continue

            # Size calculation with reserve and lot discretization
            try:
                quantity, reserve_info = compute_size(last, sig, candidate, cost, cash)
            except ValueError as exc:
                reason = "SIZE_OR_MIN_NOTIONAL" if "SIZE_OR_MIN_NOTIONAL" in str(exc) else "GAP_VETO_OR_STOP"
                fates[reason] += 1
                all_rejected.append({
                    "event_id": sig["event_id"],
                    "fold": fold["name"],
                    "reason": reason,
                    "detail": str(exc),
                })
                continue

            # Execute trade
            trade = execute_position(last, mark, funding_events, sig, candidate, cost, quantity)

            if trade["exit_ack_at"] >= fold_end:
                raise ValueError(f"Trade ACK {trade['exit_ack_at']} leaked fold boundary {fold_end}")

            after_cash = cash + float(trade["net_after_funding_usdt"])
            if after_cash <= 0:
                raise ValueError(f"Closing cash nonpositive: {after_cash}")

            trade.update({
                "fold": fold["name"],
                "cash_before_entry": cash,
                "cash_after_ack": after_cash,
                "reserve_info": reserve_info,
            })

            fold_trades.append(trade)
            all_executed_trades.append(trade)
            cash = after_cash
            fates["FILLED"] += 1
            next_allowed = max(trade["exit_ack_at"], trade["exit_at"] + cooldown_hours * HOUR)

        # Compute marked equity curve for the fold
        fold_mark_metrics = compute_marked_equity_curve(
            fold_trades, mark, fold_start, fold_end, cash_start_fold, cost
        )
        fold_summaries.append({
            "fold": fold["name"],
            "year": fold["year"],
            "month": fold["month"],
            "trades_count": len(fold_trades),
            "starting_cash": cash_start_fold,
            "ending_cash": cash,
            "net_pnl_usdt": cash - cash_start_fold,
            "min_mark_equity": fold_mark_metrics["min_mark_equity"],
            "max_mtm_drawdown_pct": fold_mark_metrics["max_mtm_drawdown_pct"],
            "occupancy_fraction": fold_mark_metrics["occupancy_fraction"],
        })

    # Global marked equity summary
    global_net_pnl = cash - initial_cash
    return {
        "candidate_id": candidate["id"],
        "cost_regime": "STRESS" if cost["fee_bps"] > 10.0 else "BASE",
        "initial_cash": initial_cash,
        "ending_cash": cash,
        "net_pnl_usdt": global_net_pnl,
        "net_return_pct": (cash / initial_cash - 1.0) * 100.0,
        "total_trades": len(all_executed_trades),
        "fates": dict(fates),
        "trades": all_executed_trades,
        "rejected": all_rejected,
        "fold_summaries": fold_summaries,
    }
