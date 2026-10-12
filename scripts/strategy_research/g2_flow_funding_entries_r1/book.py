"""Single trade order execution, fill simulation, and funding cashflow attribution.

Preserves exact point-in-time order rules, 0.1 tick rounding, adverse spread/slippage,
quarter-ATR gap veto, and settlement funding cashflows using latest completed 1m Mark closes.
"""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

import numpy as np

MINUTE = 60_000
HOUR = 3_600_000
TICK = 0.1
LOT = 0.001
MIN_NOTIONAL = 5.0

BASE = {"fee_bps": 6.0, "spread_bps": 4.0, "slip_bps": 3.0, "nominal_roundtrip_bps": 22.0}
STRESS = {"fee_bps": 12.0, "spread_bps": 8.0, "slip_bps": 6.0, "nominal_roundtrip_bps": 44.0}


def _decimal(value: Any, label: str) -> Decimal:
    try:
        res = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid {label}: {value}") from exc
    if not res.is_finite():
        raise ValueError(f"Nonfinite {label}: {value}")
    return res


def _tick(price: float, upwards: bool) -> float:
    """Round to 0.1 tick: ceiling for buy/stop-loss-short, floor for sell/stop-loss-long."""
    scaled = price / TICK
    return round((math.ceil(scaled - 1e-9) if upwards else math.floor(scaled + 1e-9)) * TICK, 8)


def _slippage(cost: dict[str, float]) -> float:
    return float(cost.get("slippage_bps", cost.get("slip_bps", 0.0)))


def _effective(raw_price: float, side: int, cost: dict[str, float], entry: bool) -> float:
    """Apply half-spread and slippage adverse to the trader."""
    spread = float(cost.get("spread_bps", 0.0))
    slip = _slippage(cost)
    adverse_fraction = (0.5 * spread + slip) / 10_000.0
    sign = side if entry else -side
    return _tick(raw_price * (1.0 + sign * adverse_fraction), upwards=sign > 0)


def _fee(notional_price: float, quantity: float, cost: dict[str, float]) -> float:
    return notional_price * quantity * (float(cost.get("fee_bps", 0.0)) / 10_000.0)


def _index(data: np.ndarray, clock: int) -> int:
    i = int(np.searchsorted(data[:, 0], clock, side="left"))
    if i >= len(data) or int(data[i, 0]) != clock:
        raise ValueError(f"Missing UTC minute bar at {clock}")
    return i


def _ack(clock: int) -> int:
    return (clock // MINUTE + 1) * MINUTE + (MINUTE if clock % MINUTE else 0)


def mark_close_asof(mark: np.ndarray, timestamp_ms: int) -> tuple[Decimal, int]:
    """Latest completed Mark minute at or before timestamp_ms, without future lookahead."""
    starts = mark[:, 0]
    idx = int(np.searchsorted(starts, timestamp_ms - (MINUTE - 1), side="right")) - 1
    if idx < 0:
        raise ValueError("No completed Mark minute at settlement")
    close_at = int(starts[idx]) + MINUTE - 1
    if close_at > timestamp_ms:
        raise AssertionError("Future Mark close detected")
    return _decimal(mark[idx, 4], "Mark close"), close_at


def propose_entry(
    data: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    *,
    side_override: int | None = None,
) -> dict[str, Any]:
    """Validate entry timing, apply quarter-ATR gap veto, and construct order parameters."""
    t_end = int(event["event_time"])
    t_decision = int(event["decision_at"])
    t_entry = int(event["entry_at"])

    if (t_end % MINUTE or t_decision % MINUTE or t_entry % MINUTE
            or t_decision < t_end + MINUTE or t_entry < t_decision + MINUTE):
        raise ValueError(f"Availability order violated: event={t_end}, decision={t_decision}, entry={t_entry}")

    i = _index(data, t_entry)
    if i < 2:
        raise ValueError("Lacks two completed bars before entry")

    side = int(event["side"] if side_override is None else side_override)
    if side not in (-1, 1):
        raise ValueError("Invalid signed side")
    raw_open = float(data[i, 1])
    filled = _effective(raw_open, side, cost, entry=True)

    source_stop = float(event["stop"])
    raw_risk = abs(raw_open - source_stop)
    stop = source_stop if side_override is None else raw_open - side * raw_risk
    if side * (raw_open - stop) <= 0:
        raise ValueError("Stop is on wrong side of entry")

    stop = _tick(stop, upwards=side < 0)
    initial_risk = side * (filled - stop)
    if initial_risk <= 0:
        raise ValueError("Effective stop risk is nonpositive")

    target_r = float(candidate.get("target_R", candidate.get("target_r", 2.0)))
    target = _tick(filled + side * target_r * initial_risk, upwards=side < 0)

    # Quarter-ATR gap veto from decision close
    decision_close = float(event["decision_close"])
    atr_hour = float(event["atr_hour"])
    gap = abs(raw_open - decision_close)
    if gap > 0.25 * atr_hour + 1e-9:
        raise ValueError("late entry breached quarter-hour-ATR gap veto")

    horizon_hours = int(candidate.get("horizon_hours", event.get("horizon_hours", 12)))

    return {
        "event_time": t_end,
        "decision_at": t_decision,
        "entry_at": t_entry,
        "entry_index": i,
        "side": side,
        "raw_entry": raw_open,
        "effective_entry": filled,
        "stop": stop,
        "target": target,
        "initial_risk": initial_risk,
        "risk_bps": 10_000.0 * raw_risk / raw_open,
        "horizon_hours": horizon_hours,
    }


def execute_position(
    last: np.ndarray,
    mark: np.ndarray,
    funding_events: list[dict[str, Any]],
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    quantity: float,
    *,
    side_override: int | None = None,
) -> dict[str, Any]:
    """Simulate single position trajectory, stop/target/time cap fills, and funding attribution."""
    if quantity <= 0 or not math.isfinite(quantity):
        raise ValueError("Quantity must be positive and finite")

    proposal = propose_entry(last, event, candidate, cost, side_override=side_override)
    side = proposal["side"]
    stop = proposal["stop"]
    target = proposal["target"]
    start_idx = proposal["entry_index"]
    deadline = proposal["entry_at"] + proposal["horizon_hours"] * HOUR

    exit_reason = ""
    raw_exit = 0.0
    exit_at = 0
    exit_idx = -1

    for idx in range(start_idx, len(last)):
        minute = int(last[idx, 0])
        op = float(last[idx, 1])
        hi = float(last[idx, 2])
        lo = float(last[idx, 3])

        # Priority 1: STOP GAP (opening gap through stop on bar open)
        if side * (op - stop) <= 0:
            raw_exit = op
            exit_reason = "STOP_GAP"
            exit_at = minute
            exit_idx = idx
            break

        # Priority 2: TIME CAP
        if minute >= deadline:
            raw_exit = min(op, target) if side > 0 else max(op, target)
            exit_reason = "TIME_CAP"
            exit_at = minute
            exit_idx = idx
            break

        # Priority 3: TARGET GAP CAPPED
        if side * (op - target) >= 0:
            raw_exit = target
            exit_reason = "TARGET_GAP_CAPPED"
            exit_at = minute
            exit_idx = idx
            break

        # Priority 4: Same-minute STOP before TARGET collision
        stop_hit = (lo <= stop) if side > 0 else (hi >= stop)
        target_hit = (hi >= target) if side > 0 else (lo <= target)

        if stop_hit:
            raw_exit = stop
            exit_reason = "STOP"
            exit_at = minute + MINUTE - 1
            exit_idx = idx
            break
        elif target_hit:
            raw_exit = target
            exit_reason = "TARGET"
            exit_at = minute + MINUTE - 1
            exit_idx = idx
            break

    if not exit_reason:
        raise ValueError("Missing complete minute path through time cap")

    eff_entry = proposal["effective_entry"]
    eff_exit = _effective(raw_exit, side, cost, entry=False)

    fee_entry = _fee(eff_entry, quantity, cost)
    fee_exit = _fee(eff_exit, quantity, cost)

    gross_usdt = side * (raw_exit - proposal["raw_entry"]) * quantity
    drag_usdt = side * (eff_entry - proposal["raw_entry"] + raw_exit - eff_exit) * quantity
    trading_net_usdt = gross_usdt - drag_usdt - fee_entry - fee_exit

    notional = proposal["raw_entry"] * quantity
    exit_ack_at = _ack(exit_at)

    # Attribute settled funding cashflows in [entry_at, exit_at)
    entry_at = proposal["entry_at"]
    funding_journal: list[dict[str, Any]] = []
    total_funding_cash = Decimal(0)

    for fevent in funding_events:
        f_clock = int(fevent["settlement_at"])
        if f_clock < entry_at or f_clock >= exit_at:
            continue
        rate = _decimal(fevent["rate"], "funding rate")
        m_price, completed_at = mark_close_asof(mark, f_clock)
        cash_delta = -Decimal(side) * _decimal(quantity, "quantity") * m_price * rate
        total_funding_cash += cash_delta
        funding_journal.append({
            "timestamp": f_clock,
            "type": "FUNDING_SETTLEMENT",
            "rate": str(rate),
            "mark_price": str(m_price),
            "mark_close_at": completed_at,
            "cash_delta": float(cash_delta),
        })

    total_funding_float = float(total_funding_cash)
    net_after_funding_usdt = trading_net_usdt + total_funding_float

    gross_bps = 10_000.0 * gross_usdt / notional
    net_trading_bps = 10_000.0 * trading_net_usdt / notional
    funding_bps = 10_000.0 * total_funding_float / notional
    net_after_funding_bps = 10_000.0 * net_after_funding_usdt / notional

    # Journal cash entries
    cash_journal = [
        {"timestamp": proposal["entry_at"], "type": "ENTRY_FEE", "cash_delta": -fee_entry},
        *funding_journal,
        {"timestamp": exit_ack_at, "type": "EXIT_SETTLEMENT", "cash_delta": gross_usdt - drag_usdt - fee_exit},
    ]

    return {
        "candidate": candidate.get("id", "UNKNOWN"),
        "event_id": event.get("event_id", str(proposal["event_time"])),
        "side": side,
        "event_time": proposal["event_time"],
        "decision_at": proposal["decision_at"],
        "entry_at": proposal["entry_at"],
        "exit_at": exit_at,
        "exit_ack_at": exit_ack_at,
        "entry_index": start_idx,
        "exit_index": exit_idx,
        "raw_entry": proposal["raw_entry"],
        "effective_entry": eff_entry,
        "raw_exit": raw_exit,
        "effective_exit": eff_exit,
        "stop": stop,
        "target": target,
        "exit_reason": exit_reason,
        "quantity": quantity,
        "entry_notional": notional,
        "fee_entry": fee_entry,
        "fee_exit": fee_exit,
        "gross_usdt": gross_usdt,
        "execution_drag_usdt": drag_usdt,
        "trading_net_usdt": trading_net_usdt,
        "funding_usdt": total_funding_float,
        "net_after_funding_usdt": net_after_funding_usdt,
        "gross_bps": gross_bps,
        "net_trading_bps": net_trading_bps,
        "funding_bps": funding_bps,
        "net_after_funding_bps": net_after_funding_bps,
        "duration_minutes": (exit_at - proposal["entry_at"]) / MINUTE,
        "journal": cash_journal,
        "funding_events_count": len(funding_journal),
    }
