"""Causal 1m replay engine for Gemini Goal-B 2021-2023 range/reversal/vol discovery.

Reuses verified execution primitives from `g2_btc_empirical_fast_r1.replay` while supporting:
- 7-column 1m arrays (with taker_buy_volume)
- Dynamic conservative midline target_r (>= 1.5R) or fixed 2.0R
- Continuous 1x $1000 USDT account across 2021-2023 without artificial 10% drawdown truncation
  (preventing '回撤被错误截断'), while retaining the 1x no-leverage guard and monthly 24h edge isolation.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.replay import (
    BASE,
    HOUR,
    LOT,
    MIN_NOTIONAL,
    MINUTE,
    STRESS,
    TICK,
    _effective,
    _event_clock,
    _exit,
    _fee,
    _fold,
    _hours,
    _id,
    _index,
    _size,
    _tick,
    _trade,
)


def _as_6col(data: np.ndarray) -> np.ndarray:
    if data.ndim != 2 or data.shape[1] not in (6, 7) or len(data) < 3:
        raise ValueError("Expected dense 6 or 7 column 1m bars")
    return data[:, :6] if data.shape[1] == 7 else data


def _validate_clock(data6: np.ndarray) -> None:
    if not np.all(np.isfinite(data6[:, :5])):
        raise ValueError("Non-finite price or clock")
    if np.any(np.diff(data6[:, 0]) != MINUTE):
        raise ValueError("Duplicate, unsorted, or missing UTC minute")


def _candidate_hours(candidate: dict[str, Any], event: dict[str, Any] | None = None) -> int:
    if event is not None and "horizon_hours" in event:
        return int(event["horizon_hours"])
    exit_p = candidate.get("exit_parameters", {})
    return int(
        candidate.get(
            "hold_hours",
            candidate.get(
                "horizon_hours",
                candidate.get("holding_horizon_hours", exit_p.get("time_stop_hours", 4)),
            ),
        )
    )


def _cooldown_ms(candidate: dict[str, Any]) -> int:
    if "cooldown_bars_15m" in candidate:
        return int(candidate["cooldown_bars_15m"]) * 15 * MINUTE
    book_cfg = candidate.get("book", {})
    cool_hours = int(book_cfg.get("cooldown_hours", candidate.get("cooldown_hours", 1)))
    return cool_hours * HOUR


def _fast_index(data6: np.ndarray, clock: int) -> int:
    start0 = int(data6[0, 0])
    idx = (clock - start0) // MINUTE
    if 0 <= idx < len(data6) and int(data6[idx, 0]) == clock:
        return int(idx)
    return _index(data6, clock)


def _proposed(
    data6: np.ndarray,
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    *,
    side_override: int | None = None,
) -> dict[str, Any]:
    end, decision, entry = _event_clock(event)
    i = _fast_index(data6, entry)
    if i < 2:
        raise ValueError("entry lacks two completed, available minute bars")
    if int(data6[i - 2, 0]) + 2 * MINUTE > entry:
        raise ValueError("last available price is too recent")
    side = int(event["side"] if side_override is None else side_override)
    if side not in (-1, 1):
        raise ValueError("side must be signed")
    raw = float(data6[i, 1])
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

    stop_tp = candidate.get("stop_tp", {})
    default_r = float(
        stop_tp.get("target_R", candidate.get("target_R", candidate.get("target_r", 2.0)))
    )
    target_r = float(event.get("target_r", default_r))
    if target_r < 1.5 - 1e-9:
        raise ValueError("target below frozen 1.5R minimum")
    target = _tick(filled + side * target_r * initial_risk, upwards=side < 0)
    risk_bps = 10_000.0 * raw_risk / raw
    if not (30.0 <= risk_bps <= 300.0):
        raise ValueError("initial stop outside frozen 30-300 bp range")
    gap = abs(raw - float(event["decision_close"]))
    if gap > 0.25 * float(event["atr_hour"]) + 1e-9:
        raise ValueError("late entry breached quarter-hour-ATR gap veto")
    hours = _candidate_hours(candidate, event)
    if hours not in (4, 8, 12, 24):
        raise ValueError("unfrozen hold horizon")
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
        "target_r": target_r,
        "initial_risk": initial_risk,
        "risk_bps": risk_bps,
        "hold_hours": hours,
        "last_available_close": float(data6[i - 2, 4]),
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
    validate_clock: bool = True,
) -> dict[str, Any]:
    """One independent, unfunded, fixed-quantity, time-matched episode."""
    data6 = _as_6col(data)
    if validate_clock:
        _validate_clock(data6)
    if quantity <= 0 or not math.isfinite(quantity):
        raise ValueError("quantity must be finite and positive")
    proposal = _proposed(data6, event, candidate, cost, side_override=side_override)
    outcome = _exit(data6, proposal, cost, quantity=quantity)
    t = _trade(data6, event, candidate, cost, quantity, proposal, outcome, control=control)
    t["target_r"] = proposal["target_r"]
    t["economic_grade"] = "COST_PROXY_DEV_ONLY"
    return t


def simulate_fold(
    data: np.ndarray,
    events: list[dict[str, Any]],
    candidate: dict[str, Any],
    fold: dict[str, Any],
    cost: dict[str, float],
    initial_equity: float = 1000.0,
    initial_highwater: float | None = None,
    busy_until_in: int | None = None,
    *,
    enable_drawdown_kill: bool = False,
    validate_clock: bool = True,
) -> dict[str, Any]:
    """Simulate a scoring fold on a 1x account with dense close-marked 1m curve.

    By default `enable_drawdown_kill=False` so continuous 2021-2023 drawdowns are
    measured honestly without artificial 10% truncation ('回撤被错误截断').
    """
    data6 = _as_6col(data)
    if validate_clock:
        _validate_clock(data6)
    start, end = _fold(fold)
    first = _fast_index(data6, start)
    last = _fast_index(data6, end - MINUTE)
    if initial_equity <= 0:
        raise ValueError("initial equity must be positive")

    cool_ms = _cooldown_ms(candidate)
    cand_hours = _candidate_hours(candidate)

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
    total_minutes = last - first + 1
    curve = np.full(total_minutes, initial_equity, dtype=np.float64)
    cash = initial_equity
    highwater = initial_equity if initial_highwater is None else initial_highwater
    disabled = False
    busy_until = start if busy_until_in is None else max(start, busy_until_in)
    active: dict[str, Any] | None = None
    pending: list[tuple[int, float]] = []
    kill_at: int | None = None
    reduce_at: int | None = None
    active_minutes = 0
    j = 0

    # Consume any events that arrived strictly before `start`
    while j < len(event_list) and int(event_list[j]["entry_at"]) < start:
        ev = event_list[j]
        j += 1
        try:
            _event_clock(ev)
        except ValueError:
            note(ev, "LOOKAHEAD_OR_CLOCK")
            continue
        note(ev, "PURGED_FOLD_EDGE")

    n = 0
    while n < total_minutes:
        # Fast-forward across idle flat stretches when no trade/pending is open
        if active is None and not pending and not disabled:
            if j >= len(event_list):
                curve[n:] = cash
                highwater = max(highwater, cash)
                break
            next_entry_ms = int(event_list[j]["entry_at"])
            if next_entry_ms >= end:
                curve[n:] = cash
                highwater = max(highwater, cash)
                break
            target_n = (next_entry_ms - start) // MINUTE
            if target_n > n:
                curve[n:target_n] = cash
                highwater = max(highwater, cash)
                if enable_drawdown_kill and highwater - cash >= 100.0 - 1e-9:
                    disabled = True
                    count["DRAWDOWN_DISABLE"] += 1
                n = int(target_n)
                continue

        i = first + n
        t = int(data6[i, 0])
        arrived = [p for p in pending if p[0] <= t]
        if arrived:
            cash += sum(p[1] for p in arrived)
            pending = [p for p in pending if p[0] > t]

        if active is not None:
            p = active["proposal"]
            outcome = active["planned"]
            if kill_at == t and t <= int(data6[outcome["exit_index"], 0]):
                outcome = _exit(data6, p, cost, force_at=t, quantity=active["remaining"])
            if int(data6[outcome["exit_index"], 0]) == t:
                if outcome["exit_at"] > t:
                    active_minutes += 1
                piece = _trade(
                    data6,
                    active["event"],
                    candidate,
                    cost,
                    active["remaining"],
                    p,
                    outcome,
                    fold_id=str(fold.get("id", fold.get("year", ""))),
                )
                piece["target_r"] = p["target_r"]
                piece["economic_grade"] = "COST_PROXY_DEV_ONLY"
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
                whole["gross_bps"] = whole["gross_usdt"] / whole["entry_notional"] * 10_000.0
                whole["net_bps"] = whole["net_usdt"] / whole["entry_notional"] * 10_000.0
                whole["net_r"] = whole["net_usdt"] / (p["initial_risk"] * active["initial_quantity"])
                whole["partial_reductions"] = active["reductions"]
                whole["year"] = int(fold.get("year", 0))
                whole["month"] = int(fold.get("month", 0))
                trades.append(whole)
                busy_until = max(busy_until, outcome["exit_ack_at"] + cool_ms)
                active = None
                kill_at = None
                reduce_at = None
            elif reduce_at == t:
                known_n = n - 2
                known_close = float(data6[i - 2, 4]) if known_n >= 0 else float(data6[i, 1])
                known_equity = float(curve[known_n]) if known_n >= 0 else cash
                allowed_q = max(0.0, math.floor(max(0.0, known_equity) / known_close / LOT) * LOT)
                if allowed_q < LOT:
                    kill_at = t + MINUTE
                    count["NO_LEVERAGE_FULL_EXIT_QUEUED"] += 1
                    cut = 0.0
                else:
                    cut = round(active["remaining"] - allowed_q, 9)
                if cut > 0:
                    raw = float(data6[i, 1])
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
            if entry < start or entry + cand_hours * HOUR > end:
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
            try:
                proposal = _proposed(data6, ev, candidate, cost)
                proposal["atr_hour"] = float(ev["atr_hour"])
            except ValueError as exc:
                note(ev, str(exc))
                continue
            quantity = _size(cash, proposal, candidate, cost)
            if quantity <= 0:
                note(ev, "SIZE_OR_MIN_NOTIONAL")
                continue
            planned = _exit(data6, proposal, cost, quantity=quantity)
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
            if int(data6[planned["exit_index"], 0]) == t:
                trade = _trade(
                    data6,
                    ev,
                    candidate,
                    cost,
                    quantity,
                    proposal,
                    planned,
                    fold_id=str(fold.get("id", fold.get("year", ""))),
                )
                trade["target_r"] = proposal["target_r"]
                trade["economic_grade"] = "COST_PROXY_DEV_ONLY"
                trade["partial_reductions"] = []
                trade["year"] = int(fold.get("year", 0))
                trade["month"] = int(fold.get("month", 0))
                trades.append(trade)
                pending.append((planned["exit_ack_at"], trade["net_usdt"]))
                busy_until = max(busy_until, planned["exit_ack_at"] + cool_ms)
                active = None

        economic_pending = sum(x[1] for x in pending)
        if active is None:
            curve[n] = cash + economic_pending
        else:
            if t > active["proposal"]["entry_at"]:
                active_minutes += 1
            p = active["proposal"]
            close = float(data6[i, 4])
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

        if n >= 2:
            known = float(curve[n - 2])
            highwater = max(highwater, known)
            if enable_drawdown_kill and not disabled and highwater - known >= 100.0 - 1e-9:
                disabled = True
                count["DRAWDOWN_DISABLE"] += 1
                if active is not None:
                    kill_at = t + MINUTE
            if active is not None and not disabled:
                last_close = float(data6[i - 2, 4])
                if active["remaining"] * last_close > max(0.0, known) + 1e-9:
                    reduce_at = t + MINUTE
        n += 1

    for ev in event_list[j:]:
        try:
            _event_clock(ev)
        except ValueError:
            note(ev, "LOOKAHEAD_OR_CLOCK")
            continue
        note(ev, "PURGED_FOLD_EDGE")

    return {
        "trades": trades,
        "curve": curve,
        "curve_start_ms": start,
        "waits": dict(count),
        "event_log": event_log,
        "ending_equity": float(cash + sum(x[1] for x in pending)),
        "highwater": max(highwater, float(np.max(curve))),
        "busy_until": busy_until,
        "disabled": disabled,
        "active_minutes": active_minutes,
        "cost_proxy_excludes_funding": True,
        "economic_grade": "COST_PROXY_DEV_ONLY",
    }
