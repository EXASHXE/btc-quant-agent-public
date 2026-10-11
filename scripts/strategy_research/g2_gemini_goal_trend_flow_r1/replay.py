"""Deterministic 1m execution replay and cash accounting with BASE/STRESS costs."""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

MINUTE = 60_000
HOUR = 3600_000
TICK = 0.1
LOT = 0.001
MIN_NOTIONAL = 5.0

# A spread_bps is the *full* spread. _effective charges half on each leg.
BASE = {"fee_bps": 6.0, "spread_bps": 4.0, "slip_bps": 3.0, "nominal_roundtrip_bps": 22.0}
STRESS = {"fee_bps": 12.0, "spread_bps": 8.0, "slip_bps": 6.0, "nominal_roundtrip_bps": 44.0}


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

    if (t_end % MINUTE or t_decision % MINUTE or t_entry % MINUTE
            or t_decision < t_end + MINUTE or t_entry < t_decision + MINUTE):
        raise ValueError("Availability order violated")

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
    if quantity <= 0 or not math.isfinite(quantity):
        raise ValueError("Quantity must be finite and positive")
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
        raise ValueError("Missing complete minute path through time cap")

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
    # A raw open fill and an intraminute stop both need a subsequent ACK.
    exit_ack_at = (exit_at // MINUTE + 1) * MINUTE + (MINUTE if exit_at % MINUTE else 0)

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
    """One cash account; minute marks are measurement, never future trading input.

    ``initial_equity`` is the preceding fold's ending equity. A trade changes
    spendable equity only at its exit ACK. The full minute path is measured
    after each accepted event, but later decisions use only settled equity.
    """
    start = int(fold["start_ms"])
    end = int(fold["end_ms"])
    if start % MINUTE or end % MINUTE or end <= start or initial_equity <= 0:
        raise ValueError("Invalid fold or starting equity")
    first = _index(data, start)
    last = _index(data, end - MINUTE)
    if np.any(np.diff(data[first:last + 1, 0]) != MINUTE):
        raise ValueError("Missing, duplicate or unsorted UTC scoring minute")
    curve = np.full(last - first + 1, initial_equity, dtype=np.float64)
    counts: Counter[str] = Counter()
    trades: list[dict[str, Any]] = []
    equity = float(initial_equity)
    cooldown_ms = int(candidate.get("cooldown_hours", 4)) * HOUR
    next_allowed_entry = start
    curve_cursor = first
    close_equities = [equity]
    max_marked_exposure_ratio = 0.0
    marked_exposure_breach_minutes = 0

    for ev in sorted(events, key=lambda x: (int(x["entry_at"]), str(x.get("event_id", "")))):
        entry_at = int(ev["entry_at"])
        if not start <= entry_at < end:
            continue
        if entry_at < next_allowed_entry:
            counts["POSITION_ACK_OR_COOLDOWN"] += 1
            continue
        try:
            proposal = _proposed(data, ev, candidate, cost)
        except ValueError as exc:
            counts["LOOKAHEAD_OR_CLOCK" if "Availability" in str(exc) else "ENTRY_OR_SOURCE_REJECTED"] += 1
            continue
        # Frozen 1x account cap, 5% cash reserve, conservative entry/exit
        # execution and unknown-cadence funding *reservation* (not a cash bill).
        # A floor to LOT cannot increase a budget or create leverage.
        budget = 0.95 * min(equity, 1000.0)
        raw = proposal["raw_entry"]
        worst_entry = max(proposal["effective_entry"], _effective(raw + 0.25 * float(ev["atr_hour"]), 1, cost, True))
        fee_unit = worst_entry * float(cost["fee_bps"]) / 10_000
        exit_reserve = 1.10 * worst_entry * (
            float(cost["fee_bps"]) + 0.5 * float(cost["spread_bps"]) + _slippage(cost)
        ) / 10_000
        funding_reserve = 1.10 * raw * 8.0 * proposal["horizon_hours"] / 10_000
        per_unit = worst_entry + fee_unit + exit_reserve + funding_reserve
        qty = math.floor(budget / per_unit / LOT + 1e-10) * LOT
        if qty <= 0 or qty * raw < MIN_NOTIONAL:
            counts["SIZE_OR_MIN_NOTIONAL"] += 1
            continue
        if qty * proposal["effective_entry"] + _fee(proposal["effective_entry"], qty, cost) > budget + 1e-8:
            raise ValueError("Entry would breach 1x/reserve budget")
        try:
            tr = episode(data, ev, candidate, cost, quantity=qty)
        except ValueError:
            counts["INCOMPLETE_EPISODE"] += 1
            continue
        if tr["exit_ack_at"] >= end:
            counts["EXIT_ACK_OUTSIDE_FOLD"] += 1
            continue
        i_entry, i_exit = tr["entry_index"], tr["exit_index"]
        curve[curve_cursor - first:i_entry - first] = equity
        entry_fee = tr["fee_entry"]
        for i in range(i_entry, i_exit + 1):
            minute = int(data[i, 0])
            if minute >= tr["exit_at"] or i == i_exit:
                mark = equity + tr["net_usdt"]
            else:
                raw_close = float(data[i, 4])
                liquidation = _effective(raw_close, tr["side"], cost, False)
                mark = (
                    equity + tr["side"] * (liquidation - tr["effective_entry"]) * qty
                    - entry_fee - _fee(liquidation, qty, cost)
                )
                if mark <= 0:
                    raise ValueError("Insolvent liquidation-cost minute mark")
                exposure_ratio = raw_close * qty / mark
                max_marked_exposure_ratio = max(max_marked_exposure_ratio, exposure_ratio)
                marked_exposure_breach_minutes += exposure_ratio > 1.0 + 1e-9
            curve[i - first] = mark
        # On a raw-open exit, this recorded mark is a completed-bar equity;
        # entry decisions remain blocked until the later ACK.
        equity += tr["net_usdt"]
        if equity <= 0:
            raise ValueError("Insolvent account after gap fill")
        tr["cash_before_entry"] = equity - tr["net_usdt"]
        tr["cash_after_ack"] = equity
        trades.append(tr)
        close_equities.append(equity)
        next_allowed_entry = max(tr["exit_ack_at"], tr["exit_at"] + cooldown_ms)
        curve_cursor = i_exit + 1
        counts["FILLED"] += 1

    curve[curve_cursor - first:] = equity
    peaks = np.maximum.accumulate(np.concatenate(([initial_equity], curve)))
    max_mtm_dd = float(np.max((peaks - np.concatenate(([initial_equity], curve))) / peaks) * 100)
    close_arr = np.array(close_equities)
    close_peaks = np.maximum.accumulate(close_arr)
    trade_dd = float(np.max((close_peaks - close_arr) / close_peaks) * 100)
    return {
        "candidate": candidate.get("id", "UNKNOWN"),
        "year": fold.get("year", 0),
        "month": fold.get("month", 0),
        "starting_equity": initial_equity,
        "ending_equity": equity,
        "trades": trades,
        "minute_equity_curve": np.column_stack((data[first:last + 1, 0] + MINUTE - 1, curve)),
        "max_mtm_drawdown_pct": max_mtm_dd,
        "trade_close_drawdown_pct": trade_dd,
        "max_position_notional_to_marked_equity": max_marked_exposure_ratio,
        "marked_exposure_breach_minutes": marked_exposure_breach_minutes,
        "event_fates": dict(counts),
    }
