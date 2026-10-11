"""Frozen, local per-position exit ledger for the two R31 research leads.

Only Last bars execute; Mark prices estimate settled funding notional. This is
an exit study sidecar, with no order interface or historical source reader.
"""
from __future__ import annotations

import math
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
from typing import Any

import numpy as np

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3.economics import (
    _decimal,
    _event_clock,
    _validate_events,
    mark_close_asof,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    HOUR,
    LOT,
    MIN_NOTIONAL,
    MINUTE,
    TICK,
    _effective,
    _fee,
    _proposed,
    _tick,
    episode,
)

SCHEMES = {"E0": 12, "H1": 18, "H2": 24, "E1": 12, "E2": 12}
FILL_MODES = {"primary", "through", "delay", "unfilled"}


class PartialIneligible(ValueError):
    """Original entry is valid but frozen partial tiers are too small."""


def _ack(clock: int) -> int:
    return (clock // MINUTE + 1) * MINUTE + (MINUTE if clock % MINUTE else 0)


def _split(quantity: float, entry: float, target1: float, target2: float) -> tuple[float, float]:
    q = _decimal(quantity, "quantity")
    lot = _decimal(LOT, "lot")
    nearest_lot_q = (q / lot).to_integral_value(rounding=ROUND_HALF_EVEN) * lot
    # R2 admitted quantity is float(math.floor(...)*LOT), which can carry
    # harmless binary ulps. Validate the intended lot without rescaling Q.
    if q <= 0 or abs(q - nearest_lot_q) > Decimal("0.000000000001"):
        raise PartialIneligible("Quantity is not a positive lot multiple")
    q1 = (nearest_lot_q / Decimal(2) / lot).to_integral_value(rounding=ROUND_FLOOR) * lot
    q2 = q - q1
    if q1 <= 0 or q2 <= 0:
        raise PartialIneligible("Zero partial tier")
    if min(q1 * _decimal(target1, "TP1"), q2 * _decimal(target2, "TP2"),
           q1 * _decimal(entry, "entry"), q2 * _decimal(entry, "entry")) < _decimal(MIN_NOTIONAL, "minimum notional"):
        raise PartialIneligible("Partial tier below minimum notional")
    return float(q1), float(q2)


def _breakeven_stop(proposal: dict[str, Any], cost: dict[str, float]) -> float:
    """First favorable raw tick with nonnegative residual net after both fees."""
    side = int(proposal["side"])
    entry = float(proposal["effective_entry"])
    start = _tick(entry, upwards=side > 0)
    raw = start
    for _ in range(100_000):
        exit_effective = _effective(raw, side, cost, entry=False)
        net_per_unit = side * (exit_effective - entry)
        net_per_unit -= _fee(entry, 1.0, cost) + _fee(exit_effective, 1.0, cost)
        if net_per_unit >= -1e-10:
            return max(raw, float(proposal["stop"])) if side > 0 else min(raw, float(proposal["stop"]))
        raw = round(raw + side * TICK, 8)
    raise ValueError("Net breakeven tick search did not converge")


def _exit_tier(
    proposal: dict[str, Any], cost: dict[str, float], quantity: float,
    raw_exit: float, exit_at: int, reason: str,
) -> dict[str, Any]:
    side = int(proposal["side"])
    raw_entry = float(proposal["raw_entry"])
    eff_entry = float(proposal["effective_entry"])
    eff_exit = _effective(raw_exit, side, cost, entry=False)
    gross = side * (raw_exit - raw_entry) * quantity
    drag = side * (eff_entry - raw_entry + raw_exit - eff_exit) * quantity
    fee_exit = _fee(eff_exit, quantity, cost)
    fee_entry_alloc = _fee(eff_entry, quantity, cost)
    return {
        "quantity": quantity,
        "raw_exit": raw_exit,
        "effective_exit": eff_exit,
        "exit_at": exit_at,
        "exit_ack_at": _ack(exit_at),
        "reason": reason,
        "fee_exit": fee_exit,
        "fee_entry_alloc": fee_entry_alloc,
        "gross_usdt": gross,
        "execution_drag_usdt": drag,
        "net_usdt": gross - drag - fee_entry_alloc - fee_exit,
    }


def _eligible_target(op: float, hi: float, lo: float, target: float, side: int) -> tuple[bool, bool]:
    """Opening gap or one-tick trade-through; separately report mere touch."""
    gap = side * (op - target) >= -1e-9
    extreme = hi if side > 0 else lo
    touched = side * (extreme - target) >= -1e-9
    through = side * (extreme - target) >= TICK - 1e-8
    return gap or through, touched and not (gap or through)


def _tiers(
    last: np.ndarray, proposal: dict[str, Any], cost: dict[str, float],
    scheme: str, quantity: float, fill_mode: str,
) -> tuple[list[dict[str, Any]], int]:
    side = int(proposal["side"])
    entry = int(proposal["entry_at"])
    deadline = entry + int(proposal["horizon_hours"]) * HOUR
    original_stop = float(proposal["stop"])
    target2 = float(proposal["target"])
    target1 = _tick(float(proposal["effective_entry"]) + side * float(proposal["initial_risk"]), upwards=side < 0)
    partial = scheme in {"E1", "E2"}
    if partial:
        q1, q2 = _split(quantity, float(proposal["effective_entry"]), target1, target2)
    else:
        q1, q2 = 0.0, quantity
    if side * (target2 - target1) <= 0:
        raise ValueError("Original target must be beyond TP1")
    stop = original_stop
    be_stop = _breakeven_stop(proposal, cost) if scheme == "E2" else None
    if be_stop is not None and side * (target2 - be_stop) <= 0:
        raise ValueError("Net break-even stop reaches original target")
    start_idx = int(proposal["entry_index"])
    rows: list[dict[str, Any]] = []
    touch_no_fill = 0
    tp1_ack: int | None = None
    deferred_tp2_until = -1
    skipped_confirmation: set[str] = set()
    pending: dict[str, int] = {}
    blocked_this_bar: set[str] = set()
    previous_minute = entry - MINUTE

    def allow_gap(name: str, minute: int) -> bool:
        if fill_mode in {"primary", "through"}:
            return True
        if fill_mode == "unfilled":
            if name not in skipped_confirmation:
                skipped_confirmation.add(name)
                blocked_this_bar.add(name)
                return False
            return True
        if pending.get(name) != minute - MINUTE:
            pending[name] = minute
            blocked_this_bar.add(name)
            return False
        return True

    for idx in range(start_idx, len(last)):
        minute = int(last[idx, 0])
        if minute != previous_minute + MINUTE:
            raise ValueError("Missing or unordered Last minute on exit path")
        previous_minute = minute
        blocked_this_bar.clear()
        op, hi, lo = (float(x) for x in last[idx, 1:4])
        if not (0 < lo <= op <= hi):
            raise ValueError("Invalid Last OHLC on exit path")
        if scheme == "E2" and tp1_ack is not None and minute >= tp1_ack:
            stop = max(stop, float(be_stop)) if side > 0 else min(stop, float(be_stop))
        remaining = q1 + q2
        if remaining <= 0:
            break
        stop_gap = side * (op - stop) <= 0
        if stop_gap:
            rows.append(_exit_tier(proposal, cost, remaining, op, minute, "STOP_GAP"))
            break
        if minute >= deadline:
            # Preserve original E0 time-cap cap at the final target.
            capped = min(op, target2) if side > 0 else max(op, target2)
            rows.append(_exit_tier(proposal, cost, remaining, capped, minute, "TIME_CAP"))
            break
        # Favorable open through both tiers proves an ordering-free double fill.
        gap1 = partial and q1 > 0 and side * (op - target1) >= 0 and allow_gap("TP1", minute)
        gap2 = q2 > 0 and side * (op - target2) >= 0 and allow_gap("TP2", minute)
        if gap1 and gap2:
            rows.append(_exit_tier(proposal, cost, q1, target1, minute, "TP1_GAP_CAPPED"))
            rows.append(_exit_tier(proposal, cost, q2, target2, minute, "TP2_GAP_CAPPED"))
            break
        if gap1:
            rows.append(_exit_tier(proposal, cost, q1, target1, minute, "TP1_GAP_CAPPED"))
            q1 = 0.0
            tp1_ack = _ack(minute)
            deferred_tp2_until = minute + MINUTE
        if gap2 and q1 == 0 and minute >= deferred_tp2_until:
            rows.append(_exit_tier(proposal, cost, q2, target2, minute, "TP2_GAP_CAPPED"))
            break
        stop_hit = lo <= stop if side > 0 else hi >= stop
        if stop_hit:
            rows.append(_exit_tier(proposal, cost, q1 + q2, stop, minute + MINUTE - 1, "STOP"))
            break
        # Intraminute stop precedes targets. TP1 then TP2 can never both
        # receive inferred fills in the same minute.
        for name, price, available in (("TP1", target1, q1), ("TP2", target2, q2)):
            if available <= 0 or name in blocked_this_bar or (name == "TP2" and (q1 > 0 or minute < deferred_tp2_until)):
                continue
            confirmed, touched_only = _eligible_target(op, hi, lo, price, side)
            touch_no_fill += int(touched_only)
            if not confirmed:
                pending.pop(name, None)
                continue
            if fill_mode == "unfilled" and name not in skipped_confirmation:
                skipped_confirmation.add(name)
                continue
            if fill_mode == "delay":
                if pending.get(name) != minute - MINUTE:
                    pending[name] = minute
                    continue
                if side * (op - price) < 0:
                    pending[name] = minute
                    continue
            if name == "TP1":
                rows.append(_exit_tier(proposal, cost, q1, price, minute + MINUTE - 1, "TP1"))
                q1 = 0.0
                tp1_ack = _ack(minute + MINUTE - 1)
                deferred_tp2_until = minute + MINUTE
                break
            rows.append(_exit_tier(proposal, cost, q2, price, minute + MINUTE - 1, "TP2"))
            q2 = 0.0
            break
        if q1 == 0 and q2 == 0:
            break
    if not rows or abs(sum(row["quantity"] for row in rows) - quantity) > 1e-9:
        raise ValueError("Missing complete exit path or quantity conservation failure")
    if any(row["quantity"] <= 0 for row in rows):
        raise ValueError("Nonpositive exit inventory")
    return rows, touch_no_fill


def _funding(
    proposal: dict[str, Any], tiers: list[dict[str, Any]],
    mark: np.ndarray, funding_events: list[dict[str, Any]], quantity: float,
) -> tuple[list[dict[str, Any]], Decimal]:
    _validate_events(funding_events)
    entry = int(proposal["entry_at"])
    exit_at = max(int(tier["exit_at"]) for tier in tiers)
    side = int(proposal["side"])
    receipts: list[dict[str, Any]] = []
    total = Decimal(0)
    for event in funding_events:
        clock = _event_clock(event)
        if clock < entry or clock >= exit_at:
            continue
        open_qty = _decimal(quantity, "quantity") - sum(
            (_decimal(tier["quantity"], "tier quantity") for tier in tiers if int(tier["exit_at"]) <= clock),
            Decimal(0),
        )
        if open_qty < 0:
            raise ValueError("Negative inventory at funding settlement")
        if open_qty == 0:
            continue
        rate = _decimal(event["rate"], "funding rate")
        source_price = event.get("mark_price")
        if source_price is None:
            price, completed_at = mark_close_asof(mark, clock)
            basis = "LATEST_COMPLETED_1M_MARK_CLOSE_APPROXIMATION"
        else:
            if not event.get("mark_price_source_proven", False):
                raise ValueError("Unproven exact settlement Mark")
            price = _decimal(source_price, "settlement Mark")
            completed_at = None
            basis = "PROVIDER_SETTLEMENT_MARK"
        if completed_at is not None:
            expected_close = ((clock - (MINUTE - 1)) // MINUTE) * MINUTE + MINUTE - 1
            if completed_at != expected_close:
                raise ValueError("Required completed Mark minute is missing at settlement")
        if price <= 0:
            raise ValueError("Nonpositive settlement Mark")
        cash = -Decimal(side) * open_qty * price * rate
        total += cash
        receipts.append({"settlement_at": clock, "source_rate_fraction": str(rate),
                         "side": side, "quantity": str(open_qty), "settlement_mark": str(price),
                         "mark_basis": basis, "mark_close_at": completed_at,
                         "signed_cash_usdt": str(cash)})
    return receipts, total


def position(
    last: np.ndarray, mark: np.ndarray, funding_events: list[dict[str, Any]],
    event: dict[str, Any], candidate: dict[str, Any], cost: dict[str, float],
    scheme: str, quantity: float, *, fill_mode: str = "primary",
    side_override: int | None = None,
) -> dict[str, Any]:
    """Execute one frozen exit scheme on a complete synthetic or admitted path."""
    if scheme not in SCHEMES or fill_mode not in FILL_MODES:
        raise ValueError("Unregistered exit scheme or fill sensitivity")
    if not math.isfinite(quantity) or quantity <= 0:
        raise ValueError("Quantity must be positive and finite")
    configured = {**candidate, "horizon_hours": SCHEMES[scheme]}
    proposal = _proposed(last, event, configured, cost, side_override=side_override)
    if scheme in {"E0", "H1", "H2"} and fill_mode == "primary":
        legacy = episode(last, event, configured, cost, side_override=side_override, quantity=quantity)
        if np.any(np.diff(last[int(proposal["entry_index"]):int(legacy["exit_index"]) + 1, 0]) != MINUTE):
            raise ValueError("Missing Last minute on inherited episode path")
        tiers = [_exit_tier(proposal, cost, quantity, float(legacy["raw_exit"]),
                            int(legacy["exit_at"]), str(legacy["exit_reason"]))]
        touch_no_fill = 0
        if any(abs(float(legacy[key]) - sum(float(row["net_usdt"]) for row in tiers)) > 1e-7
               for key in ("net_usdt",)):
            raise ValueError("Inherited E0/H identity mismatch")
    else:
        tiers, touch_no_fill = _tiers(last, proposal, cost, scheme, quantity, fill_mode)
        legacy = {}
    if sum(tier["quantity"] for tier in tiers) > quantity + 1e-9:
        raise ValueError("Exit quantity exceeds entry")
    settled, funding_cash = _funding(proposal, tiers, mark, funding_events, quantity)
    fee_entry = _fee(float(proposal["effective_entry"]), quantity, cost)
    fee_exit = sum(float(tier["fee_exit"]) for tier in tiers)
    gross = sum(float(tier["gross_usdt"]) for tier in tiers)
    drag = sum(float(tier["execution_drag_usdt"]) for tier in tiers)
    net = gross - drag - fee_entry - fee_exit
    notional = float(proposal["raw_entry"]) * quantity
    # Cash is credited at ACK; inventory leaves at the fill clock. Journal
    # includes both clocks so account replay cannot spend unacknowledged cash.
    journal: list[dict[str, Any]] = [
        {"kind": "ENTRY_FEE", "timestamp": int(proposal["entry_at"]),
         "cash_delta": -fee_entry, "remaining_quantity": quantity}
    ]
    exited = 0.0
    for tier in tiers:
        exited += float(tier["quantity"])
        remaining = round(quantity - exited, 12)
        journal.append({"kind": "EXIT_FEE", "timestamp": tier["exit_at"],
                        "cash_delta": -float(tier["fee_exit"]), "quantity_delta": -float(tier["quantity"]),
                        "remaining_quantity": remaining})
        journal.append({"kind": "EXIT_PNL_ACK", "timestamp": tier["exit_ack_at"],
                        "cash_delta": float(tier["gross_usdt"]) - float(tier["execution_drag_usdt"]),
                        "remaining_quantity": remaining})
    for receipt in settled:
        journal.append({"kind": "FUNDING", "timestamp": receipt["settlement_at"],
                        "cash_delta": float(receipt["signed_cash_usdt"]),
                        "remaining_quantity": float(receipt["quantity"])})
    journal.sort(key=lambda row: (int(row["timestamp"]),
                                  {"ENTRY_FEE": 0, "EXIT_FEE": 1, "FUNDING": 2,
                                   "EXIT_PNL_ACK": 3}[row["kind"]]))
    inventory = quantity
    for item in journal:
        inventory = round(inventory + float(item.get("quantity_delta", 0.0)), 12)
        if inventory < -1e-9:
            raise ValueError("Negative journal inventory")
        item["remaining_quantity"] = max(0.0, inventory)
    if abs(inventory) > 1e-9:
        raise ValueError("Residual journal inventory after flat exit")
    if abs(sum(row["cash_delta"] for row in journal) - (net + float(funding_cash))) > 1e-7:
        raise ValueError("Cash journal does not conserve net proceeds")
    last_tier = max(tiers, key=lambda row: (row["exit_at"], row["exit_ack_at"]))
    weighted_age = sum(tier["quantity"] * (tier["exit_at"] - proposal["entry_at"]) / MINUTE
                       for tier in tiers) / quantity
    tp1 = next((x for x in tiers if x["reason"].startswith("TP1")), None)
    instructions = []
    if scheme == "E2" and tp1 is not None and tp1["exit_ack_at"] <= last_tier["exit_at"]:
        instructions = [{"kind": "RESIDUAL_NET_BE", "effective_at": tp1["exit_ack_at"],
                         "raw_stop": _breakeven_stop(proposal, cost),
                         "entry_costs_only": True, "TP1_profit_and_future_funding_excluded": True}]
    result = {**legacy,
        "candidate": candidate.get("id", "UNKNOWN"),
        "event_id": event.get("event_id", str(proposal["event_time"])),
        "scheme": scheme, "fill_mode": fill_mode, "side": int(proposal["side"]),
        "event_time": int(proposal["event_time"]), "decision_at": int(proposal["decision_at"]),
        "entry_at": int(proposal["entry_at"]), "entry_index": int(proposal["entry_index"]),
        "exit_at": int(last_tier["exit_at"]), "exit_ack_at": int(last_tier["exit_ack_at"]),
        "exit_index": int(np.searchsorted(last[:, 0], last_tier["exit_at"], side="right")) - 1,
        "raw_entry": float(proposal["raw_entry"]),
        "effective_entry": float(proposal["effective_entry"]),
        "raw_exit": float(last_tier["raw_exit"]),
        "effective_exit": float(last_tier["effective_exit"]),
        "stop": float(proposal["stop"]), "target": float(proposal["target"]),
        "exit_reason": str(last_tier["reason"]), "quantity": quantity,
        "entry_notional": notional, "fee_entry": fee_entry, "fee_exit": fee_exit,
        "gross_usdt": gross, "execution_drag_usdt": drag, "net_usdt": net,
        "gross_bps": 10_000 * gross / notional, "net_bps": 10_000 * net / notional,
        "net_r": net / (quantity * float(proposal["initial_risk"])),
        "initial_risk": float(proposal["initial_risk"]),
        "risk_bps": float(proposal["risk_bps"]),
        "duration_minutes": (last_tier["exit_at"] - proposal["entry_at"]) / MINUTE,
        "weighted_exit_age_minutes": weighted_age, "tiers": tiers,
        "journal": journal, "funding_settlements": settled,
        "settlement_count": len(settled), "funding_cash_usdt": str(funding_cash),
        "net_after_funding_usdt": str(_decimal(net, "net") + funding_cash),
        "net_after_funding_bps": str(Decimal(10_000) * (_decimal(net, "net") + funding_cash) / _decimal(notional, "notional")),
        "touch_no_fill_count": touch_no_fill, "instructions": instructions,
    }
    return result
