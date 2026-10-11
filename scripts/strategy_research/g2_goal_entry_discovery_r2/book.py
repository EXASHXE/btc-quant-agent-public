"""Deterministic 1m execution replay and cash accounting for Goal A R2.

Enforces:
- 1m adverse execution (_effective) on open prices.
- Stop-before-target collision priority.
- Conservative limit fill proxy for target profit.
- Precise observed signed funding cash flows.
- 0.1 tick, 0.001 lot, 5.0 USDT minimum notional.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

import numpy as np

MINUTE = 60_000
HOUR = 3600_000
TICK = 0.1
LOT = 0.001
MIN_NOTIONAL = 5.0

BASE = {"fee_bps": 6.0, "spread_bps": 4.0, "slip_bps": 3.0, "nominal_roundtrip_bps": 22.0}
STRESS = {"fee_bps": 12.0, "spread_bps": 8.0, "slip_bps": 6.0, "nominal_roundtrip_bps": 44.0}


class TradeExecutionError(ValueError):
    """Execution constraint violated."""


def _tick(price: float, upwards: bool) -> float:
    """Round to 0.1 tick: ceiling for buy/stop-short, floor for sell/stop-long."""
    scaled = price / TICK
    return (math.ceil(scaled - 1e-9) if upwards else math.floor(scaled + 1e-9)) * TICK


def _slippage(cost: dict[str, float]) -> float:
    return float(cost.get("slip_bps", cost.get("slippage_bps", 0.0)))


def _effective(raw_price: float, side: int, cost: dict[str, float], entry: bool) -> float:
    """Apply half-spread and slippage adverse to the trader."""
    spread = float(cost.get("spread_bps", 0.0))
    slip = _slippage(cost)
    adverse_fraction = (0.5 * spread + slip) / 10_000.0
    sign = side if entry else -side
    return _tick(raw_price * (1.0 + sign * adverse_fraction), upwards=sign > 0)


def _fee(notional_price: float, quantity: float, cost: dict[str, float]) -> float:
    """Trading fee based on filled notional."""
    return notional_price * quantity * (float(cost.get("fee_bps", 0.0)) / 10_000.0)


def _ack(clock: int) -> int:
    """Exchange order acknowledgement quantization."""
    return (clock // MINUTE + 1) * MINUTE + (MINUTE if clock % MINUTE else 0)


def _index(data: np.ndarray, clock: int) -> int:
    """Binary search for exact millisecond timestamp."""
    i = int(np.searchsorted(data[:, 0], clock, side="left"))
    if i >= len(data) or int(data[i, 0]) != clock:
        raise TradeExecutionError(f"Missing 1m bar at timestamp {clock}")
    return i


def mark_close_asof(mark_1m: np.ndarray, clock: int) -> float:
    """Latest completed 1m Mark price close at or prior to clock."""
    i = int(np.searchsorted(mark_1m[:, 0], clock, side="right")) - 1
    if i < 0:
        raise TradeExecutionError(f"No prior Mark price at timestamp {clock}")
    return float(mark_1m[i, 4])


def execute_position(
    last_1m: np.ndarray,
    mark_1m: np.ndarray,
    rates: list[dict[str, Any]],
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    quantity: float,
    *,
    side_override: int | None = None,
) -> dict[str, Any]:
    """Execute a single position and compute trade P&L + observed Funding."""
    t_entry = int(event["entry_at"])
    horizon_hours = int(candidate.get("horizon_hours", event.get("horizon_hours", 12)))
    target_r = float(candidate.get("target_R", event.get("target_R", 2.0)))
    side = int(event["side"] if side_override is None else side_override)

    if side not in (-1, 1):
        raise TradeExecutionError("Invalid trade side")

    i_entry = _index(last_1m, t_entry)
    raw_open = float(last_1m[i_entry, 1])
    filled_entry = _effective(raw_open, side, cost, entry=True)

    source_stop = float(event["stop"])
    raw_risk = abs(raw_open - source_stop)
    stop = source_stop if side_override is None else (raw_open - side * raw_risk)

    if side * (raw_open - stop) <= 0:
        raise TradeExecutionError("Stop is on wrong side of entry")

    stop = _tick(stop, upwards=side < 0)
    initial_risk = side * (filled_entry - stop)
    if initial_risk <= 0:
        raise TradeExecutionError("Effective initial risk is nonpositive")

    target = _tick(filled_entry + side * target_r * initial_risk, upwards=side < 0)

    # Replay 1m bars until stop, target, or horizon deadline
    deadline_at = t_entry + horizon_hours * HOUR
    i_deadline = _index(last_1m, deadline_at)

    exit_reason = None
    raw_exit = 0.0
    exit_at = 0

    for i in range(i_entry, i_deadline):
        t_bar = int(last_1m[i, 0])
        bar_high = float(last_1m[i, 2])
        bar_low = float(last_1m[i, 3])

        stop_touched = (bar_low <= stop) if side > 0 else (bar_high >= stop)
        target_touched = (bar_high >= target) if side > 0 else (bar_low <= target)

        if stop_touched and target_touched:
            # STOP LOSS WINS on simultaneous collision
            exit_reason = "STOP_LOSS"
            raw_exit = stop
            exit_at = t_bar
            break
        elif stop_touched:
            exit_reason = "STOP_LOSS"
            raw_exit = stop
            exit_at = t_bar
            break
        elif target_touched:
            exit_reason = "TARGET_PROFIT"
            raw_exit = target
            exit_at = t_bar
            break

    if exit_reason is None:
        # Exited at horizon deadline open
        exit_reason = "HORIZON_EXPIRY"
        raw_exit = float(last_1m[i_deadline, 1])
        exit_at = deadline_at

    effective_exit = _effective(raw_exit, side, cost, entry=False)
    exit_ack_at = _ack(exit_at)

    fee_entry = _fee(filled_entry, quantity, cost)
    fee_exit = _fee(effective_exit, quantity, cost)
    gross_usdt = side * (raw_exit - raw_open) * quantity
    adverse_drag = side * (filled_entry - raw_open + raw_exit - effective_exit) * quantity
    net_usdt = side * (effective_exit - filled_entry) * quantity - fee_entry - fee_exit

    # Funding settlements strictly during holding window: t_entry < settlement_at <= exit_at
    funding_cash_usdt = 0.0
    funding_events = []
    for r in rates:
        s_time = int(r["settlement_at"])
        if t_entry < s_time <= exit_at:
            m_price = mark_close_asof(mark_1m, s_time)
            rate_dec = Decimal(str(r["rate"]))
            f_delta = float(-Decimal(side) * rate_dec * Decimal(str(quantity)) * Decimal(str(m_price)))
            funding_cash_usdt += f_delta
            funding_events.append({
                "settlement_at": s_time,
                "rate": str(r["rate"]),
                "mark_price": m_price,
                "cash_delta": f_delta,
            })

    net_after_funding_usdt = net_usdt + funding_cash_usdt
    initial_notional = quantity * filled_entry
    net_bps = (net_usdt / initial_notional) * 10_000.0 if initial_notional > 0 else 0.0
    net_after_funding_bps = (net_after_funding_usdt / initial_notional) * 10_000.0 if initial_notional > 0 else 0.0

    return {
        "event_id": event["event_id"],
        "candidate_id": candidate["id"],
        "side": side,
        "quantity": quantity,
        "entry_at": t_entry,
        "raw_entry": raw_open,
        "effective_entry": filled_entry,
        "stop": stop,
        "target": target,
        "initial_risk": initial_risk,
        "exit_at": exit_at,
        "exit_ack_at": exit_ack_at,
        "exit_reason": exit_reason,
        "raw_exit": raw_exit,
        "effective_exit": effective_exit,
        "gross_usdt": gross_usdt,
        "adverse_drag": adverse_drag,
        "fee_entry": fee_entry,
        "fee_exit": fee_exit,
        "net_usdt": net_usdt,
        "funding_cash_usdt": funding_cash_usdt,
        "net_after_funding_usdt": net_after_funding_usdt,
        "net_bps": net_bps,
        "net_after_funding_bps": net_after_funding_bps,
        "funding_events": funding_events,
    }
