"""Standalone, research-only minute replay for the frozen BTC experiment.

Input bars are [UTC open milliseconds, open, high, low, close, volume].  A bar
with open ``t`` is known no earlier than ``t + 120_000`` in this experiment:
one minute to close and one further minute for availability.  No market-data
reader, trading API, or production engine is imported here.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

MINUTE = 60_000
HOUR = 60 * MINUTE
TICK = 0.1  # Research assumption; exchange filter history is unverified.
LOT = 0.001
MIN_NOTIONAL = 5.0
BASE = {"fee_bps": 6.0, "spread_bps": 2.0, "slip_bps": 3.0}
STRESS = {"fee_bps": 12.0, "spread_bps": 4.0, "slip_bps": 6.0}


def _id(candidate: dict[str, Any]) -> str:
    return str(candidate.get("id", candidate.get("candidate_id", "UNNAMED")))


def _hours(candidate: dict[str, Any]) -> int:
    return int(candidate.get("hold_hours", candidate.get("horizon_hours", 4)))


def _original(candidate: dict[str, Any]) -> bool:
    if "original" in candidate:
        return bool(candidate["original"])
    return str(candidate.get("family", "")).upper() in {"STRUCTURAL_CONTINUATION", "CLOSED_RETEST"}


def _tick(price: float, upwards: bool) -> float:
    units = price / TICK
    return (math.ceil(units - 1e-9) if upwards else math.floor(units + 1e-9)) * TICK


def _slippage(cost: dict[str, float]) -> float:
    return float(cost.get("slippage_bps", cost.get("slip_bps", 0.0)))


def _effective(raw: float, side: int, cost: dict[str, float], entry: bool) -> float:
    adverse = (float(cost["spread_bps"]) + _slippage(cost)) / 10_000
    sign = side if entry else -side
    return _tick(raw * (1 + sign * adverse), upwards=sign > 0)


def _fee(price: float, quantity: float, cost: dict[str, float]) -> float:
    return price * quantity * float(cost["fee_bps"]) / 10_000


def _index(data: np.ndarray, clock: int) -> int:
    i = int(np.searchsorted(data[:, 0], clock, side="left"))
    if i >= len(data) or int(data[i, 0]) != clock:
        raise ValueError(f"missing UTC minute at {clock}")
    return i


def _validate_clock(data: np.ndarray) -> None:
    if data.ndim != 2 or data.shape[1] != 6 or len(data) < 3:
        raise ValueError("expected dense six-column 1m bars")
    if not np.all(np.isfinite(data[:, :5])):
        raise ValueError("nonfinite price or clock")
    if np.any(np.diff(data[:, 0]) != MINUTE):
        raise ValueError("duplicate, unsorted, or missing UTC minute")


def _event_clock(event: dict[str, Any]) -> tuple[int, int, int]:
    end = int(event["event_time"])
    decision = int(event["decision_at"])
    entry = int(event["entry_at"])
    if end % MINUTE or decision % MINUTE or entry % MINUTE:
        raise ValueError("event, decision and entry must be exact UTC minutes")
    if decision < end + MINUTE or entry < decision + MINUTE:
        raise ValueError("closed-bar availability or next-open delay violated")
    return end, decision, entry


def _fold(fold: dict[str, Any]) -> tuple[int, int]:
    start = int(fold.get("start_ms", fold.get("start", 0)))
    end = int(fold.get("end_ms", fold.get("end", 0)))
    if start % MINUTE or end % MINUTE or end <= start:
        raise ValueError("invalid half-open scoring fold")
    return start, end


def _proposed(
    data: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    *,
    side_override: int | None = None,
) -> dict[str, Any]:
    end, decision, entry = _event_clock(event)
    i = _index(data, entry)
    if i < 2:
        raise ValueError("entry lacks two completed, available minute bars")
    if int(data[i - 2, 0]) + 2 * MINUTE > entry:
        raise ValueError("last available price is too recent")
    side = int(event["side"] if side_override is None else side_override)
    if side not in (-1, 1):
        raise ValueError("side must be signed")
    raw = float(data[i, 1])
    filled = _effective(raw, side, cost, entry=True)
    source_stop = float(event["stop"])
    raw_risk = abs(raw - source_stop)
    stop = source_stop if side_override is None else raw - side * raw_risk
    if side * (raw - stop) <= 0:
        raise ValueError("stop is on the wrong side of entry")
    stop = _tick(stop, upwards=side < 0)
    initial_risk = side * (filled - stop)
    if initial_risk <= 0:
        raise ValueError("effective stop risk is nonpositive")
    target_r = float(candidate.get("target_R", candidate.get("target_r", 2.0)))
    if target_r < 2:
        raise ValueError("target below frozen 2R minimum")
    target = _tick(filled + side * target_r * initial_risk, upwards=side < 0)
    risk_bps = 10_000 * raw_risk / raw
    max_risk = 250 if _original(candidate) else 300
    if not 30 <= risk_bps <= max_risk:
        raise ValueError("initial stop outside frozen 30–250/300 bp range")
    gap = abs(raw - float(event["decision_close"]))
    if gap > 0.25 * float(event["atr_hour"]) + 1e-9:
        raise ValueError("late entry breached quarter-hour-ATR gap veto")
    hours = _hours(candidate)
    if hours not in (4, 8, 12, 24):
        raise ValueError("unfrozen hold horizon")
    if _original(candidate) and side_override is None:
        # Unknown cadence is stressed as one adverse 8 bp settlement per hour.
        c = 44 + 8 * hours + 2 * TICK / raw * 10_000
        stop_bps = 10_000 * initial_risk / filled
        target_bps = 10_000 * side * (target - filled) / filled
        if stop_bps + 1e-9 < 2 * c or target_bps + 1e-9 < 3 * c:
            raise ValueError("original stress-cost stop/target geometry ineligible")
    return {
        "event_time": end,
        "decision_at": decision,
        "entry_at": entry,
        "entry_index": i,
        "side": side,
        "raw_entry": raw,
        "effective_entry": filled,
        "stop": stop,
        "target": target,
        "initial_risk": initial_risk,
        "risk_bps": risk_bps,
        "hold_hours": hours,
        "last_available_close": float(data[i - 2, 4]),
    }


def _exit(
    data: np.ndarray,
    proposal: dict[str, Any],
    cost: dict[str, float],
    *,
    force_at: int | None = None,
    quantity: float = 1.0,
) -> dict[str, Any]:
    side = proposal["side"]
    stop = proposal["stop"]
    target = proposal["target"]
    start = proposal["entry_index"]
    deadline = proposal["entry_at"] + proposal["hold_hours"] * HOUR
    for i in range(start, len(data)):
        minute = int(data[i, 0])
        op, hi, lo = map(float, data[i, 1:4])
        if force_at is not None and minute >= force_at:
            raw, reason, at = op, "DRAWDOWN_KILL", minute
        elif side * (op - stop) <= 0:
            raw, reason, at = op, "STOP_GAP", minute
        elif minute >= deadline:
            raw = min(op, target) if side > 0 else max(op, target)
            reason, at = "TIME_CAP", minute
        elif side * (op - target) >= 0:
            raw, reason, at = target, "TARGET_GAP_CAPPED", minute
        elif lo <= stop if side > 0 else hi >= stop:
            raw, reason, at = stop, "STOP", minute + MINUTE - 1
        elif hi >= target if side > 0 else lo <= target:
            raw, reason, at = target, "TARGET", minute + MINUTE - 1
        else:
            continue
        effective = _effective(raw, side, cost, entry=False)
        return {
            "exit_index": i,
            "exit_at": at,
            "exit_ack_at": ((at + MINUTE - 1) // MINUTE) * MINUTE + MINUTE,
            "raw_exit": raw,
            "effective_exit": effective,
            "exit_reason": reason,
            "exit_fee": _fee(effective, quantity, cost),
            "mae_bps": 10_000
            * min(
                side
                * (float(data[j, 3 if side > 0 else 2]) - proposal["raw_entry"])
                / proposal["raw_entry"]
                for j in range(start, i + 1)
            ),
            "mfe_bps": 10_000
            * max(
                side
                * (float(data[j, 2 if side > 0 else 3]) - proposal["raw_entry"])
                / proposal["raw_entry"]
                for j in range(start, i + 1)
            ),
        }
    raise ValueError("missing bar through fixed maximum hold")


def _trade(
    data: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    quantity: float,
    proposal: dict[str, Any],
    outcome: dict[str, Any],
    fold_id: str = "",
    *,
    control: str = "",
) -> dict[str, Any]:
    side = proposal["side"]
    raw_entry, raw_exit = proposal["raw_entry"], outcome["raw_exit"]
    eff_entry, eff_exit = proposal["effective_entry"], outcome["effective_exit"]
    entry_fee = _fee(eff_entry, quantity, cost)
    exit_fee = _fee(eff_exit, quantity, cost)
    gross = side * (raw_exit - raw_entry) * quantity
    drag = side * (eff_entry - raw_entry + raw_exit - eff_exit) * quantity
    net = gross - drag - entry_fee - exit_fee
    notional = raw_entry * quantity
    initial_risk_cash = proposal["initial_risk"] * quantity
    return {
        "candidate": _id(candidate),
        "fold": fold_id,
        "control": control,
        "event_id": str(event.get("event_id", proposal["event_time"])),
        "event_time": proposal["event_time"],
        "decision_at": proposal["decision_at"],
        "entry_at": proposal["entry_at"],
        "exit_at": outcome["exit_at"],
        "exit_ack_at": outcome["exit_ack_at"],
        "side": side,
        "raw_entry": raw_entry,
        "effective_entry": eff_entry,
        "raw_exit": raw_exit,
        "effective_exit": eff_exit,
        "stop": proposal["stop"],
        "target": proposal["target"],
        "exit_reason": outcome["exit_reason"],
        "hold_hours": proposal["hold_hours"],
        "duration_minutes": (outcome["exit_at"] - proposal["entry_at"]) / MINUTE,
        "quantity": quantity,
        "entry_notional": notional,
        "entry_fee_usdt": entry_fee,
        "exit_fee_usdt": exit_fee,
        "fee_usdt": entry_fee + exit_fee,
        "execution_drag_usdt": drag,
        "gross_usdt": gross,
        "net_usdt": net,
        "gross_bps": gross / notional * 10_000,
        "net_bps": net / notional * 10_000,
        "net_r": net / initial_risk_cash,
        "mae_bps": outcome["mae_bps"],
        "mfe_bps": outcome["mfe_bps"],
        "regime_vol_bps": event.get("regime_vol_bps"),
        "trend_bar_end": event.get("trend_bar_end"),
        "cost_proxy_excludes_funding": True,
        "economic_grade": "EXPLORATORY_COST_PROXY_ONLY",
        "measurement_identity": candidate.get("measurement_identity"),
        "original_protocol_economic_status": candidate.get("original_protocol_economic_status"),
    }


def episode(
    data: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    quantity: float = 1.0,
    *,
    side_override: int | None = None,
    control: str = "",
) -> dict[str, Any]:
    """One independent, unfunded, fixed-quantity, time-matched episode."""
    _validate_clock(data)
    if quantity <= 0 or not math.isfinite(quantity):
        raise ValueError("quantity must be finite and positive")
    proposal = _proposed(data, event, candidate, cost, side_override=side_override)
    outcome = _exit(data, proposal, cost, quantity=quantity)
    return _trade(data, event, candidate, cost, quantity, proposal, outcome, control=control)


def _size(
    equity: float, proposal: dict[str, Any], candidate: dict[str, Any], cost: dict[str, float]
) -> float:
    if equity <= 0:
        return 0.0
    fraction = float(candidate.get("allocation_fraction", 1 / 3 if _original(candidate) else 1))
    budget = (
        min(1000 * fraction, 0.95 * equity * fraction)
        if _original(candidate)
        else 0.95 * equity * fraction
    )
    raw = proposal["raw_entry"]
    atr = proposal["atr_hour"]
    worst = raw + 0.25 * atr
    adverse = (float(cost["spread_bps"]) + _slippage(cost)) / 10_000
    x = _tick(worst * (1 + adverse), upwards=True)
    entry_fee = x * float(cost["fee_bps"]) / 10_000
    exit_reserve = (
        1.1 * x * (float(cost["fee_bps"]) + float(cost["spread_bps"]) + _slippage(cost)) / 10_000
    )
    funding_reserve = 1.1 * proposal["last_available_close"] * 8 * proposal["hold_hours"] / 10_000
    per_unit = x + entry_fee + exit_reserve + funding_reserve
    q = math.floor((budget / per_unit) / LOT + 1e-10) * LOT
    if q * raw < MIN_NOTIONAL or q <= 0:
        return 0.0
    if q * raw > equity + 1e-9:  # No leverage multiplication.
        q = math.floor((equity / raw) / LOT + 1e-10) * LOT
    return max(0.0, q)


def simulate(
    data: np.ndarray,
    events: list[dict[str, Any]],
    candidate: dict[str, Any],
    fold: dict[str, Any],
    cost: dict[str, float],
    initial_equity: float = 1000.0,
    initial_highwater: float | None = None,
) -> dict[str, Any]:
    """Independent one-position account, with dense close-marked 1m curve.

    Signals must be frozen before this function sees bar bodies.  The final
    price curve is ex-post measurement; decisions use only bars available at
    the earlier decision clock.  A closed trade cannot fund a new entry until
    its ACK, and every rejected event is counted without retry.
    """
    _validate_clock(data)
    start, end = _fold(fold)
    first = _index(data, start)
    last = _index(data, end - MINUTE)
    if initial_equity <= 0:
        raise ValueError("initial equity must be positive")
    event_list = sorted(events, key=lambda e: (int(e["entry_at"]), str(e.get("event_id", ""))))
    count: Counter[str] = Counter()
    event_log: list[dict[str, Any]] = []

    def note(ev: dict[str, Any], reason: str) -> None:
        count[reason] += 1
        event_log.append(
            {
                "event_id": str(ev.get("event_id", "")),
                "decision_at": int(ev["decision_at"]),
                "entry_at": int(ev["entry_at"]),
                "result": reason,
            }
        )

    trades: list[dict[str, Any]] = []
    curve = np.full(last - first + 1, initial_equity, dtype=np.float64)
    cash = initial_equity
    highwater = initial_equity if initial_highwater is None else initial_highwater
    disabled = False
    busy_until = start
    last_structural_trend = -1
    active: dict[str, Any] | None = None
    pending: list[tuple[int, float]] = []
    kill_at: int | None = None
    reduce_at: int | None = None
    active_minutes = 0
    j = 0
    for n, i in enumerate(range(first, last + 1)):
        t = int(data[i, 0])
        arrived = [p for p in pending if p[0] <= t]
        cash += sum(p[1] for p in arrived)
        pending = [p for p in pending if p[0] > t]
        if active is not None:
            p = active["proposal"]
            outcome = active["planned"]
            if kill_at == t and t <= int(data[outcome["exit_index"], 0]):
                outcome = _exit(data, p, cost, force_at=t, quantity=active["remaining"])
            if int(data[outcome["exit_index"], 0]) == t:
                if outcome["exit_at"] > t:
                    active_minutes += 1
                piece = _trade(
                    data,
                    active["event"],
                    candidate,
                    cost,
                    active["remaining"],
                    p,
                    outcome,
                    fold_id=str(fold.get("id", fold.get("year", ""))),
                )
                active["pieces"].append(piece)
                pending.append((outcome["exit_ack_at"], piece["net_usdt"]))
                whole = dict(piece)
                whole["quantity"] = active["initial_quantity"]
                whole["entry_notional"] = p["raw_entry"] * active["initial_quantity"]
                for field in (
                    "entry_fee_usdt",
                    "exit_fee_usdt",
                    "fee_usdt",
                    "execution_drag_usdt",
                    "gross_usdt",
                    "net_usdt",
                ):
                    whole[field] = sum(x[field] for x in active["pieces"])
                whole["gross_bps"] = whole["gross_usdt"] / whole["entry_notional"] * 10_000
                whole["net_bps"] = whole["net_usdt"] / whole["entry_notional"] * 10_000
                whole["net_r"] = whole["net_usdt"] / (
                    p["initial_risk"] * active["initial_quantity"]
                )
                whole["partial_reductions"] = active["reductions"]
                trades.append(whole)
                cool = 4 if _original(candidate) else int(candidate.get("cooldown_hours", 1))
                busy_until = max(busy_until, outcome["exit_ack_at"] + cool * HOUR)
                active = None
                kill_at = None
                reduce_at = None
            elif reduce_at == t:
                known_n = n - 2
                known_close = float(data[i - 2, 4]) if known_n >= 0 else float(data[i, 1])
                known_equity = float(curve[known_n]) if known_n >= 0 else cash
                allowed_q = max(0.0, math.floor(max(0.0, known_equity) / known_close / LOT) * LOT)
                if allowed_q < LOT:
                    kill_at = t + MINUTE
                    count["NO_LEVERAGE_FULL_EXIT_QUEUED"] += 1
                    cut = 0.0
                else:
                    cut = round(active["remaining"] - allowed_q, 9)
                if cut > 0:
                    raw = float(data[i, 1])
                    eff = _effective(raw, p["side"], cost, entry=False)
                    gross = p["side"] * (raw - p["raw_entry"]) * cut
                    drag = p["side"] * (p["effective_entry"] - p["raw_entry"] + raw - eff) * cut
                    fee = _fee(p["effective_entry"], cut, cost) + _fee(eff, cut, cost)
                    net = gross - drag - fee
                    partial = {
                        "entry_fee_usdt": _fee(p["effective_entry"], cut, cost),
                        "exit_fee_usdt": _fee(eff, cut, cost),
                        "fee_usdt": fee,
                        "execution_drag_usdt": drag,
                        "gross_usdt": gross,
                        "net_usdt": net,
                    }
                    active["pieces"].append(partial)
                    active["reductions"].append(
                        {
                            "at": t,
                            "quantity": cut,
                            "raw_exit": raw,
                            "effective_exit": eff,
                            "net_usdt": net,
                        }
                    )
                    active["remaining"] = round(active["remaining"] - cut, 9)
                    pending.append((t + MINUTE, net))
                    count["NO_LEVERAGE_REDUCTION"] += 1
                reduce_at = None
        while j < len(event_list) and int(event_list[j]["entry_at"]) <= t:
            ev = event_list[j]
            j += 1
            try:
                _, _, entry = _event_clock(ev)
            except ValueError:
                note(ev, "LOOKAHEAD_OR_CLOCK")
                continue
            if entry < start or entry + _hours(candidate) * HOUR > end:
                note(ev, "PURGED_FOLD_EDGE")
                continue
            if entry != t:
                note(ev, "OUTSIDE_OR_MISSING_ENTRY_MINUTE")
                continue
            if disabled:
                note(ev, "DISABLED")
                continue
            if active is not None or pending or t < busy_until:
                note(ev, "POSITION_ACK_OR_COOLDOWN")
                continue
            if (
                _original(candidate)
                and str(candidate.get("family", "")).upper() == "STRUCTURAL_CONTINUATION"
            ):
                trend_end = int(ev.get("trend_bar_end", -1))
                if trend_end <= last_structural_trend:
                    note(ev, "NO_NEW_COMPLETED_4H_BAR")
                    continue
            try:
                proposal = _proposed(data, ev, candidate, cost)
                proposal["atr_hour"] = float(ev["atr_hour"])
            except ValueError as exc:
                note(ev, str(exc))
                continue
            quantity = _size(cash, proposal, candidate, cost)
            if quantity <= 0:
                note(ev, "SIZE_OR_MIN_NOTIONAL")
                continue
            planned = _exit(data, proposal, cost, quantity=quantity)
            if planned["exit_at"] >= end:
                note(ev, "EXIT_OUTSIDE_FOLD")
                continue
            active = {
                "event": ev,
                "proposal": proposal,
                "planned": planned,
                "initial_quantity": quantity,
                "remaining": quantity,
                "pieces": [],
                "reductions": [],
            }
            active_minutes += 1
            note(ev, "FILLED")
            if (
                _original(candidate)
                and str(candidate.get("family", "")).upper() == "STRUCTURAL_CONTINUATION"
            ):
                last_structural_trend = int(ev.get("trend_bar_end", -1))
            if int(data[planned["exit_index"], 0]) == t:
                # Protection is standing at the entry open.  Intrabar extrema
                # may close the position in that same minute, stop first.
                trade = _trade(
                    data,
                    ev,
                    candidate,
                    cost,
                    quantity,
                    proposal,
                    planned,
                    fold_id=str(fold.get("id", fold.get("year", ""))),
                )
                trade["partial_reductions"] = []
                trades.append(trade)
                pending.append((planned["exit_ack_at"], trade["net_usdt"]))
                cool = 4 if _original(candidate) else int(candidate.get("cooldown_hours", 1))
                busy_until = max(busy_until, planned["exit_ack_at"] + cool * HOUR)
                active = None
        economic_pending = sum(x[1] for x in pending)
        if active is None:
            curve[n] = cash + economic_pending
        else:
            if t > active["proposal"]["entry_at"]:
                active_minutes += 1
            p = active["proposal"]
            close = float(data[i, 4])
            mark_exit = _effective(close, p["side"], cost, entry=False)
            reserve = _fee(mark_exit, active["remaining"], cost)
            entry_fee = _fee(p["effective_entry"], active["remaining"], cost)
            curve[n] = (
                cash
                + economic_pending
                + p["side"] * (mark_exit - p["effective_entry"]) * active["remaining"]
                - entry_fee
                - reserve
            )
        # Last available close at this open is i-2; earlier closes can trigger
        # only next-open action, never a retroactive fill on the current bar.
        if n >= 2:
            known = float(curve[n - 2])
            highwater = max(highwater, known)
            if not disabled and highwater - known >= 100 - 1e-9:
                disabled = True
                count["DRAWDOWN_DISABLE"] += 1
                if active is not None:
                    kill_at = t + MINUTE
            if active is not None and not disabled:
                last_close = float(data[i - 2, 4])
                if active["remaining"] * last_close > max(0.0, known) + 1e-9:
                    reduce_at = t + MINUTE
    for ev in event_list[j:]:
        note(ev, "PURGED_FOLD_EDGE")
    daily: list[dict[str, float | int]] = []
    for n in range(0, len(curve), 1440):
        end_n = min(n + 1440, len(curve)) - 1
        daily.append(
            {
                "utc_day_start_ms": int(data[first + n, 0]),
                "equity": float(curve[end_n]),
                "pnl_from_start": float(curve[end_n] - initial_equity),
            }
        )
    return {
        "trades": trades,
        "curve": curve,
        "curve_start_ms": start,
        "daily_equity": daily,
        "waits": dict(count),
        "event_log": event_log,
        "ending_equity": cash + sum(x[1] for x in pending),
        "highwater": max(highwater, float(np.max(curve))),
        "disabled": disabled,
        "active_minutes": active_minutes,
        "cost_proxy_excludes_funding": True,
        "economic_grade": "EXPLORATORY_COST_PROXY_ONLY",
    }
