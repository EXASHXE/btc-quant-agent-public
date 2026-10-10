"""Deterministic 1m execution replay and cash accounting with BASE/STRESS costs."""
from __future__ import annotations

import math
from typing import Any
import numpy as np

MINUTE = 60_000
HOUR = 3600_000
TICK = 0.1
LOT = 0.001
MIN_NOTIONAL = 5.0

BASE = {"fee_bps": 8.0, "spread_bps": 4.0, "slip_bps": 10.0, "nominal_roundtrip_bps": 22.0}
STRESS = {"fee_bps": 10.0, "spread_bps": 8.0, "slip_bps": 26.0, "nominal_roundtrip_bps": 44.0}


def _tick(price: float, upwards: bool) -> float:
    """Round to 0.1 tick: ceiling for buy/stop-loss-short, floor for sell/stop-loss-long."""
    scaled = price / TICK
    return (math.ceil(scaled - 1e-9) if upwards else math.floor(scaled + 1e-9)) * TICK


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


def _proposed(
    data: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    *,
    side_override: int | None = None,
) -> dict[str, Any]:
    t_end = int(event["event_time"])
    t_decision = int(event["decision_at"])
    t_entry = int(event["entry_at"])

    if t_decision <= t_end or t_entry <= t_decision:
        raise ValueError("Availability order violated")

    i = _index(data, t_entry)
    if i < 2:
        raise ValueError("Lacks two completed bars before entry")

    side = int(event["side"] if side_override is None else side_override)
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

    horizon_hours = int(candidate.get("horizon_hours", event.get("horizon_hours", 8)))

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


def episode(
    data: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    *,
    side_override: int | None = None,
    quantity: float = 1.0,
) -> dict[str, Any]:
    """Execute a single trade episode from entry to exit."""
    proposal = _proposed(data, event, candidate, cost, side_override=side_override)
    side = proposal["side"]
    stop = proposal["stop"]
    target = proposal["target"]
    start_idx = proposal["entry_index"]
    deadline = proposal["entry_at"] + proposal["horizon_hours"] * HOUR

    exit_reason = ""
    raw_exit = 0.0
    exit_at = 0
    exit_idx = -1

    for idx in range(start_idx, len(data)):
        minute = int(data[idx, 0])
        op = float(data[idx, 1])
        hi = float(data[idx, 2])
        lo = float(data[idx, 3])
        cl = float(data[idx, 4])

        # Priority 1: STOP GAP (adverse gap through stop on bar open)
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
        # Reached end of data before deadline
        raw_exit = float(data[-1, 4])
        exit_reason = "DATA_END"
        exit_at = int(data[-1, 0])
        exit_idx = len(data) - 1

    eff_entry = proposal["effective_entry"]
    eff_exit = _effective(raw_exit, side, cost, entry=False)

    fee_entry = _fee(eff_entry, quantity, cost)
    fee_exit = _fee(eff_exit, quantity, cost)

    gross_usdt = side * (raw_exit - proposal["raw_entry"]) * quantity
    drag_usdt = side * (eff_entry - proposal["raw_entry"] + raw_exit - eff_exit) * quantity
    net_usdt = gross_usdt - drag_usdt - fee_entry - fee_exit

    notional = proposal["raw_entry"] * quantity
    gross_bps = 10_000.0 * gross_usdt / notional
    net_bps = 10_000.0 * net_usdt / notional

    return {
        "candidate": candidate.get("id", "UNKNOWN"),
        "event_id": event.get("event_id", str(proposal["event_time"])),
        "side": side,
        "event_time": proposal["event_time"],
        "decision_at": proposal["decision_at"],
        "entry_at": proposal["entry_at"],
        "exit_at": exit_at,
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
        "fee_entry": fee_entry,
        "fee_exit": fee_exit,
        "gross_usdt": gross_usdt,
        "net_usdt": net_usdt,
        "gross_bps": gross_bps,
        "net_bps": net_bps,
        "duration_minutes": (exit_at - proposal["entry_at"]) / MINUTE,
    }


def simulate_fold(
    data: np.ndarray,
    events: list[dict[str, Any]],
    candidate: dict[str, Any],
    fold: dict[str, Any],
    cost: dict[str, float],
    initial_equity: float = 1000.0,
) -> dict[str, Any]:
    """Simulate single-position trading over a monthly fold with cooldown and cash conservation."""
    fold_start = fold["start_ms"]
    fold_end = fold["end_ms"]

    cooldown_ms = int(candidate.get("cooldown_hours", 4)) * HOUR
    valid_events = [
        e for e in events
        if fold_start <= e["entry_at"] < fold_end
    ]
    valid_events.sort(key=lambda x: x["entry_at"])

    equity = initial_equity
    trades = []
    next_allowed_entry = 0

    for ev in valid_events:
        if ev["entry_at"] < next_allowed_entry:
            continue

        raw_price = float(ev["decision_close"])
        if equity <= 10.0:
            break

        # 1x position sizing, 1000 USDT capital limit
        notional_target = min(equity, 1000.0)
        qty = math.floor((notional_target / raw_price) / LOT) * LOT
        if qty * raw_price < MIN_NOTIONAL:
            continue

        try:
            tr = episode(data[:, :6], ev, candidate, cost, quantity=qty)
        except ValueError:
            # Quarter-ATR gap veto or boundary error
            continue

        # Check if trade touches boundaries
        if tr["entry_at"] < fold_start or tr["exit_at"] >= fold_end:
            continue

        equity += tr["net_usdt"]
        trades.append(tr)
        next_allowed_entry = tr["exit_at"] + cooldown_ms

    return {
        "candidate": candidate.get("id", "UNKNOWN"),
        "year": fold.get("year", 0),
        "month": fold.get("month", 0),
        "starting_equity": initial_equity,
        "ending_equity": equity,
        "trades": trades,
    }
