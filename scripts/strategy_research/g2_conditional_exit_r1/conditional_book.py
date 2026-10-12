"""Standalone causal conditional 12h->18h exit mechanism and dynamic quantity/cash journal."""
from __future__ import annotations

import math
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Decimal
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
    MINUTE,
    TICK,
    _effective,
    _fee,
    _proposed,
    _tick,
)

from .contract import ALL_SCHEMES

DEC_TICK = Decimal("0.1")
DEC_LOT = Decimal("0.001")
DEC_MIN_NOTIONAL = Decimal("5.0")
DEC_10000 = Decimal(10000)


class PartialIneligibleError(ValueError):
    """Raised when a partial tier split violates lot or minimum notional constraints."""


def ack_clock(clock: int) -> int:
    """Compute causal order acknowledgement timestamp (next minute open for open fills, +2m for bar-end fills)."""
    return (clock // MINUTE + 1) * MINUTE + (MINUTE if clock % MINUTE else 0)


def effective_price_decimal(
    raw_price: float | str | Decimal,
    side: int,
    cost: dict[str, float],
    *,
    entry: bool,
) -> Decimal:
    """Compute adverse half-spread + slippage effective price rounded to 0.1 tick in exact Decimal."""
    direction = side if entry else -side
    spread = _decimal(cost.get("spread_bps", 0.0), "spread_bps")
    slip = _decimal(cost.get("slippage_bps", cost.get("slip_bps", 0.0)), "slip_bps")
    adverse = (spread / Decimal(2) + slip) / DEC_10000
    raw_dec = _decimal(raw_price, "raw_price")
    val = raw_dec * (Decimal(1) + Decimal(direction) * adverse)
    units = val / DEC_TICK
    rounding = ROUND_CEILING if direction > 0 else ROUND_FLOOR
    return units.to_integral_value(rounding=rounding) * DEC_TICK


def split_partial_quantity(
    quantity: float,
    entry_price: float,
    target1: float,
    target2: float,
    fraction: float = 0.5,
) -> tuple[float, float]:
    """Split quantity into two lot-aligned partial tiers with min-notional verification."""
    q = _decimal(quantity, "quantity")
    nearest_lot_q = (q / DEC_LOT).to_integral_value(rounding=ROUND_HALF_EVEN) * DEC_LOT
    if q <= 0 or abs(q - nearest_lot_q) > Decimal("0.000000000001"):
        raise PartialIneligibleError("Quantity is not a positive lot multiple")
    frac_dec = _decimal(fraction, "fraction")
    q1 = (nearest_lot_q * frac_dec / DEC_LOT).to_integral_value(rounding=ROUND_FLOOR) * DEC_LOT
    q2 = q - q1
    if q1 <= 0 or q2 <= 0:
        raise PartialIneligibleError("Zero partial tier quantity")
    min_notional_check = min(
        q1 * _decimal(target1, "TP1"),
        q2 * _decimal(target2, "TP2"),
        q1 * _decimal(entry_price, "entry"),
        q2 * _decimal(entry_price, "entry"),
    )
    if min_notional_check < DEC_MIN_NOTIONAL:
        raise PartialIneligibleError("Partial tier below minimum 5 USDT notional")
    return float(q1), float(q2)


def evaluate_x1_at_12h(
    proposal: dict[str, Any],
    mark: np.ndarray,
    funding_events: list[dict[str, Any]],
    cost: dict[str, float],
    quantity: float,
    decision_12h_at: int,
    *,
    funding_lag_ms: int = 0,
    prior_realized_net_usdt: Decimal = Decimal(0),
    initial_entry_fee_usdt: Decimal | None = None,
) -> dict[str, Any]:
    """Evaluate X1_NET_POSITIVE_AT_12H strictly as-of the 12h boundary clock.

    Computes unrealized signed direction-adjusted net USDT at the most recent
    strictly completed 1m Mark close (open_time == decision_12h_at - 60_000,
    close_time == decision_12h_at - 1), using effective entry, all accrued known
    funding in [entry_at, decision_12h_at - 1 - funding_lag_ms], known entry fee,
    and hypothetical frozen exit fee + STRESS/BASE execution friction.
    """
    _validate_events(funding_events)
    if mark.ndim != 2 or mark.shape[1] < 5 or len(mark) == 0:
        raise ValueError("Mark array must be nonempty Nx5+")

    entry_at = int(proposal["entry_at"])
    if decision_12h_at <= entry_at or decision_12h_at % MINUTE != 0:
        raise ValueError("Invalid 12h decision clock")

    # Most recent strictly completed 1m Mark bar must close at decision_12h_at - 1
    expected_mark_open = decision_12h_at - MINUTE
    expected_mark_close = decision_12h_at - 1
    mark_price_dec, mark_close_at = mark_close_asof(mark, expected_mark_close)
    if mark_close_at != expected_mark_close:
        raise ValueError(
            f"Required completed 1m Mark minute missing at 12h decision: got {mark_close_at}, expected {expected_mark_close}"
        )
    if mark_price_dec <= 0:
        raise ValueError("Nonpositive Mark close at 12h decision")

    side = int(proposal["side"])
    q_dec = _decimal(quantity, "quantity")
    if q_dec <= 0:
        raise ValueError("Nonpositive quantity at 12h decision")

    eff_entry_dec = effective_price_decimal(proposal["raw_entry"], side, cost, entry=True)
    hyp_eff_exit_dec = effective_price_decimal(mark_price_dec, side, cost, entry=False)
    fee_bps_dec = _decimal(cost.get("fee_bps", 0.0), "fee_bps")

    if initial_entry_fee_usdt is not None:
        fee_entry_dec = initial_entry_fee_usdt
    else:
        fee_entry_dec = eff_entry_dec * q_dec * fee_bps_dec / DEC_10000
    hyp_fee_exit_dec = hyp_eff_exit_dec * q_dec * fee_bps_dec / DEC_10000

    # Accrued known funding settlements in [entry_at, decision_12h_at - 1 - funding_lag_ms]
    cutoff_ms = expected_mark_close - funding_lag_ms
    accrued_funding_dec = Decimal(0)
    accrued_settlements: list[dict[str, Any]] = []
    lag_window_settlements = 0

    for ev in funding_events:
        clock = _event_clock(ev)
        if clock < entry_at or clock >= decision_12h_at:
            continue
        if clock > cutoff_ms:
            lag_window_settlements += 1
            continue
        rate_dec = _decimal(ev["rate"], "funding rate")
        source_price = ev.get("mark_price")
        if source_price is not None:
            if not ev.get("mark_price_source_proven", False):
                raise ValueError("Unproven settlement Mark price")
            s_mark_dec = _decimal(source_price, "settlement Mark")
            s_close_at = None
        else:
            s_mark_dec, s_close_at = mark_close_asof(mark, clock)
            expected_s_close = ((clock - (MINUTE - 1)) // MINUTE) * MINUTE + MINUTE - 1
            if s_close_at != expected_s_close:
                raise ValueError("Missing completed 1m Mark bar at funding settlement")
        if s_mark_dec <= 0:
            raise ValueError("Nonpositive settlement Mark price")
        cash_dec = -Decimal(side) * q_dec * s_mark_dec * rate_dec
        accrued_funding_dec += cash_dec
        accrued_settlements.append({
            "settlement_at": clock,
            "rate": str(rate_dec),
            "settlement_mark": str(s_mark_dec),
            "mark_close_at": s_close_at,
            "signed_cash_usdt": str(cash_dec),
        })

    raw_entry_dec = _decimal(proposal["raw_entry"], "raw_entry")
    gross_mark_pnl_dec = Decimal(side) * (mark_price_dec - raw_entry_dec) * q_dec
    mark_drag_dec = Decimal(side) * (eff_entry_dec - raw_entry_dec + mark_price_dec - hyp_eff_exit_dec) * q_dec
    unrealized_after_drag_dec = Decimal(side) * (hyp_eff_exit_dec - eff_entry_dec) * q_dec
    if abs((gross_mark_pnl_dec - mark_drag_dec) - unrealized_after_drag_dec) > Decimal("1e-12"):
        raise AssertionError("Mark gross minus drag identity violation")

    estimated_net_dec = (
        prior_realized_net_usdt
        + unrealized_after_drag_dec
        - fee_entry_dec
        - hyp_fee_exit_dec
        + accrued_funding_dec
    )
    notional_dec = raw_entry_dec * q_dec
    estimated_net_bps_dec = DEC_10000 * estimated_net_dec / notional_dec

    # Strict > 0 rule: zero or negative exits at 12h
    extend_to_18h = bool(estimated_net_dec > Decimal(0))

    return {
        "policy": "X1_NET_POSITIVE_AT_12H",
        "decision_at": decision_12h_at,
        "mark_bar_open_at": expected_mark_open,
        "mark_bar_close_at": mark_close_at,
        "mark_close_price": float(mark_price_dec),
        "mark_close_price_str": str(mark_price_dec),
        "effective_entry": float(eff_entry_dec),
        "hypothetical_effective_exit": float(hyp_eff_exit_dec),
        "hypothetical_effective_exit_str": str(hyp_eff_exit_dec),
        "quantity": float(q_dec),
        "gross_mark_pnl_usdt": float(gross_mark_pnl_dec),
        "hypothetical_execution_drag_usdt": float(mark_drag_dec),
        "unrealized_price_pnl_after_drag_usdt": float(unrealized_after_drag_dec),
        "known_entry_fee_usdt": float(fee_entry_dec),
        "hypothetical_exit_fee_usdt": float(hyp_fee_exit_dec),
        "accrued_funding_usdt": float(accrued_funding_dec),
        "accrued_funding_usdt_str": str(accrued_funding_dec),
        "accrued_funding_count": len(accrued_settlements),
        "accrued_funding_settlements": accrued_settlements,
        "funding_lag_ms": funding_lag_ms,
        "lag_excluded_settlement_count": lag_window_settlements,
        "estimated_liquidation_net_usdt": float(estimated_net_dec),
        "estimated_liquidation_net_usdt_str": str(estimated_net_dec),
        "estimated_liquidation_net_bps": float(estimated_net_bps_dec),
        "extend_to_18h": extend_to_18h,
        "decision_basis": "12H_HOLDING_TIME_DECISION_NOT_ENTRY_PREDICTOR",
    }


def extract_completed_1h_last_candles(
    last: np.ndarray,
    decision_at_ms: int,
) -> list[dict[str, Any]]:
    """Aggregate strictly completed 1h Last candles with close_time <= decision_at_ms.

    Each 1h candle [H_open, H_open + 3_600_000 - 1] requires all 60 contiguous
    1m bars to be present and its final close timestamp H_open + 3_600_000 - 1
    to be <= decision_at_ms. Unclosed mid-hour bars are never included.
    """
    if last.ndim != 2 or last.shape[1] < 5 or len(last) == 0:
        raise ValueError("Last array must be nonempty Nx5+")

    # Filter 1m bars whose close_time (open_time + 59_999) <= decision_at_ms
    open_times = last[:, 0].astype(np.int64)
    completed_mask = (open_times + MINUTE - 1) <= decision_at_ms
    completed_1m = last[completed_mask]
    if len(completed_1m) < 240:
        raise ValueError(f"Insufficient completed 1m bars ({len(completed_1m)}) before {decision_at_ms}")

    c_opens = completed_1m[:, 0].astype(np.int64)
    hour_buckets = (c_opens // HOUR) * HOUR
    unique_hours, start_indices, counts = np.unique(
        hour_buckets, return_index=True, return_counts=True
    )

    completed_hours: list[dict[str, Any]] = []
    for h_open, s_idx, cnt in zip(unique_hours, start_indices, counts, strict=True):
        h_open_int = int(h_open)
        h_close_int = h_open_int + HOUR - 1
        if h_close_int > decision_at_ms:
            continue
        if cnt != 60:
            continue
        h_slice = completed_1m[s_idx : s_idx + 60]
        slice_opens = h_slice[:, 0].astype(np.int64)
        if int(slice_opens[0]) != h_open_int or int(slice_opens[-1]) != h_open_int + 59 * MINUTE:
            continue
        if not np.all(np.diff(slice_opens) == MINUTE):
            continue
        op = float(h_slice[0, 1])
        hi = float(np.max(h_slice[:, 2]))
        lo = float(np.min(h_slice[:, 3]))
        cl = float(h_slice[-1, 4])
        if cl <= 0 or op <= 0 or lo <= 0 or hi < lo:
            raise ValueError("Invalid OHLC in completed 1h Last candle")
        completed_hours.append({
            "open_time": h_open_int,
            "close_time": h_close_int,
            "open": op,
            "high": hi,
            "low": lo,
            "close": cl,
            "close_str": str(h_slice[-1, 4]),
            "minute_count": 60,
        })

    return completed_hours


def evaluate_x2_at_12h(
    last: np.ndarray,
    side: int,
    decision_12h_at: int,
) -> dict[str, Any]:
    """Evaluate X2_COMPLETED_4H_TREND_AT_12H strictly as-of the 12h boundary clock.

    Computes signed price return over the most recent 4 fully closed 1h Last candles
    available at decision_12h_at (with close_time <= decision_12h_at):
    extend iff side * (last_closed_1h_close - earliest_previous_completed_1h_close) > 0.
    Zero returns exit. Never uses an unclosed or future hour bar.
    """
    if side not in (-1, 1):
        raise ValueError(f"Invalid side: {side}")
    if decision_12h_at % MINUTE != 0:
        raise ValueError("Invalid 12h decision clock")

    completed_1h = extract_completed_1h_last_candles(last, decision_12h_at)
    if len(completed_1h) < 4:
        raise ValueError(
            f"Fewer than 4 completed 1h Last candles ({len(completed_1h)}) available at {decision_12h_at}"
        )

    window_4 = completed_1h[-4:]
    # Verify contiguous 1h bars and that the latest completed 1h bar is the immediately preceding UTC hour
    expected_last_hour_open = (decision_12h_at // HOUR - 1) * HOUR
    if window_4[-1]["open_time"] != expected_last_hour_open:
        raise ValueError(
            f"Latest completed 1h candle open {window_4[-1]['open_time']} != expected {expected_last_hour_open}"
        )
    for k in range(1, 4):
        if window_4[k]["open_time"] - window_4[k - 1]["open_time"] != HOUR:
            raise ValueError("Most recent 4 completed 1h Last candles are not contiguous")
        if window_4[k]["close_time"] > decision_12h_at:
            raise AssertionError("Unclosed 1h candle leaked into X2 window")

    earliest_candle = window_4[0]
    last_candle = window_4[-1]

    earliest_close_dec = _decimal(earliest_candle["close"], "earliest_1h_close")
    last_close_dec = _decimal(last_candle["close"], "last_1h_close")
    if earliest_close_dec <= 0 or last_close_dec <= 0:
        raise ValueError("Nonpositive 1h close price in X2 evaluation")

    signed_diff_dec = Decimal(side) * (last_close_dec - earliest_close_dec)
    raw_return_dec = (last_close_dec - earliest_close_dec) / earliest_close_dec
    signed_return_dec = Decimal(side) * raw_return_dec
    signed_return_bps_dec = DEC_10000 * signed_return_dec

    # Strict > 0 rule: zero or negative return exits at 12h
    extend_to_18h = bool(signed_diff_dec > Decimal(0))

    return {
        "policy": "X2_COMPLETED_4H_TREND_AT_12H",
        "decision_at": decision_12h_at,
        "completed_1h_candles_count": 4,
        "earliest_1h_open_at": earliest_candle["open_time"],
        "earliest_1h_close_at": earliest_candle["close_time"],
        "earliest_1h_close": float(earliest_close_dec),
        "earliest_1h_close_str": str(earliest_close_dec),
        "last_1h_open_at": last_candle["open_time"],
        "last_1h_close_at": last_candle["close_time"],
        "last_1h_close": float(last_close_dec),
        "last_1h_close_str": str(last_close_dec),
        "window_1h_closes": [float(c["close"]) for c in window_4],
        "window_1h_close_times": [int(c["close_time"]) for c in window_4],
        "unclosed_current_hour_open_at": (decision_12h_at // HOUR) * HOUR,
        "unclosed_current_hour_excluded": True,
        "signed_price_diff": float(signed_diff_dec),
        "signed_price_diff_str": str(signed_diff_dec),
        "raw_return_4h": float(raw_return_dec),
        "signed_return_4h": float(signed_return_dec),
        "signed_return_4h_bps": float(signed_return_bps_dec),
        "extend_to_18h": extend_to_18h,
        "decision_basis": "12H_HOLDING_TIME_DECISION_NOT_ENTRY_PREDICTOR",
    }


def _build_exit_tier(
    proposal: dict[str, Any],
    cost: dict[str, float],
    quantity: float,
    raw_exit: float,
    exit_at: int,
    reason: str,
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
        "exit_ack_at": ack_clock(exit_at),
        "reason": reason,
        "fee_exit": fee_exit,
        "fee_entry_alloc": fee_entry_alloc,
        "gross_usdt": gross,
        "execution_drag_usdt": drag,
        "net_usdt": gross - drag - fee_entry_alloc - fee_exit,
    }


def _compute_funding_settlements(
    proposal: dict[str, Any],
    tiers: list[dict[str, Any]],
    mark: np.ndarray,
    funding_events: list[dict[str, Any]],
    quantity: float,
) -> tuple[list[dict[str, Any]], Decimal]:
    """Accrue signed historical funding on remaining open quantity at each settlement in [entry_at, exit_at)."""
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
        receipts.append({
            "settlement_at": clock,
            "source_rate_fraction": str(rate),
            "side": side,
            "quantity": str(open_qty),
            "settlement_mark": str(price),
            "mark_basis": basis,
            "mark_close_at": completed_at,
            "signed_cash_usdt": str(cash),
        })
    return receipts, total


def execute_conditional_position(
    last: np.ndarray,
    mark: np.ndarray,
    funding_events: list[dict[str, Any]],
    event: dict[str, Any],
    candidate: dict[str, Any],
    cost: dict[str, float],
    scheme: str,
    quantity: float,
    *,
    side_override: int | None = None,
    partial_tp1_fraction: float | None = None,
    funding_lag_ms: int = 0,
) -> dict[str, Any]:
    """Execute one trade episode under E0, H1, X1_NET_POSITIVE_AT_12H, or X2_COMPLETED_4H_TREND_AT_12H.

    Preserves byte-for-byte E0 execution before 12h and when exiting at 12h,
    and byte-for-byte H1 execution when extending from 12h to 18h.
    Supports optional partial_tp1_fraction solely for synthetic multi-tier conservation tests.
    """
    if scheme not in ALL_SCHEMES:
        raise ValueError(f"Unregistered exit scheme: {scheme}")
    if partial_tp1_fraction is not None and not (0.0 < partial_tp1_fraction < 1.0):
        raise ValueError("Invalid partial_tp1_fraction")
    if not math.isfinite(quantity) or quantity <= 0:
        raise ValueError("Quantity must be positive and finite")

    # Initial entry proposal always uses the original 12h candidate parameters
    configured = {**candidate, "horizon_hours": 12}
    proposal = _proposed(last, event, configured, cost, side_override=side_override)
    side = int(proposal["side"])
    entry_at = int(proposal["entry_at"])
    start_idx = int(proposal["entry_index"])
    stop = float(proposal["stop"])
    target = float(proposal["target"])

    deadline_12h = entry_at + 12 * HOUR
    deadline_18h = entry_at + 18 * HOUR

    if partial_tp1_fraction is not None:
        target1 = _tick(
            float(proposal["effective_entry"]) + side * float(proposal["initial_risk"]),
            upwards=side < 0,
        )
        if side * (target - target1) <= 0:
            raise ValueError("Target must be beyond partial TP1")
        q1, q2 = split_partial_quantity(
            quantity, float(proposal["effective_entry"]), target1, target, partial_tp1_fraction
        )
    else:
        target1 = target
        q1, q2 = 0.0, quantity

    tiers: list[dict[str, Any]] = []
    decision_12h: dict[str, Any] = {
        "reached_12h_time_cap_boundary": False,
        "scheme": scheme,
        "decision_at": None,
        "extend_to_18h": False,
        "outcome_at_12h": "EXITED_BEFORE_12H",
        "decision_basis": "12H_HOLDING_TIME_DECISION_NOT_ENTRY_PREDICTOR",
    }
    active_deadline = deadline_12h
    extended_at_12h = False
    deferred_tp2_until = -1
    previous_minute = entry_at - MINUTE

    for idx in range(start_idx, len(last)):
        minute = int(last[idx, 0])
        if minute != previous_minute + MINUTE:
            raise ValueError("Missing or unordered Last minute on exit path")
        previous_minute = minute
        op, hi, lo = (float(x) for x in last[idx, 1:4])
        if not (0 < lo <= op <= hi):
            raise ValueError("Invalid Last OHLC on exit path")

        remaining = q1 + q2
        if remaining <= 0:
            break

        # Priority 1: Adverse STOP_GAP on bar open always precedes TIME_CAP / conditional selection
        if side * (op - stop) <= 0:
            tiers.append(_build_exit_tier(proposal, cost, remaining, op, minute, "STOP_GAP"))
            if minute == deadline_12h and not extended_at_12h:
                decision_12h = {
                    "reached_12h_time_cap_boundary": False,
                    "scheme": scheme,
                    "decision_at": deadline_12h,
                    "extend_to_18h": False,
                    "outcome_at_12h": "BOUNDARY_OPEN_STOP_GAP_PRECEDENCE",
                    "decision_basis": "12H_HOLDING_TIME_DECISION_NOT_ENTRY_PREDICTOR",
                }
            break

        # Priority 2a: 12h boundary decision (immediately before 12h TIME_CAP)
        if minute == deadline_12h and not extended_at_12h:
            if scheme == "E0":
                capped = min(op, target) if side > 0 else max(op, target)
                tiers.append(_build_exit_tier(proposal, cost, remaining, capped, minute, "TIME_CAP"))
                decision_12h = {
                    "reached_12h_time_cap_boundary": True,
                    "scheme": "E0",
                    "decision_at": deadline_12h,
                    "extend_to_18h": False,
                    "outcome_at_12h": "TIME_CAP_12H",
                    "decision_basis": "12H_HOLDING_TIME_DECISION_NOT_ENTRY_PREDICTOR",
                }
                break
            elif scheme == "H1":
                extended_at_12h = True
                active_deadline = deadline_18h
                decision_12h = {
                    "reached_12h_time_cap_boundary": True,
                    "scheme": "H1",
                    "decision_at": deadline_12h,
                    "extend_to_18h": True,
                    "outcome_at_12h": "UNCONDITIONAL_EXTEND_18H",
                    "decision_basis": "12H_HOLDING_TIME_DECISION_NOT_ENTRY_PREDICTOR",
                }
            elif scheme == "X1_NET_POSITIVE_AT_12H":
                prior_realized_dec = sum(
                    (
                        _decimal(t["gross_usdt"], "gross")
                        - _decimal(t["execution_drag_usdt"], "drag")
                        - _decimal(t["fee_exit"], "fee_exit")
                        for t in tiers
                    ),
                    Decimal(0),
                )
                full_entry_fee_dec = (
                    effective_price_decimal(proposal["raw_entry"], side, cost, entry=True)
                    * _decimal(quantity, "quantity")
                    * _decimal(cost.get("fee_bps", 0.0), "fee_bps")
                    / DEC_10000
                )
                x1_eval = evaluate_x1_at_12h(
                    proposal,
                    mark,
                    funding_events,
                    cost,
                    remaining,
                    deadline_12h,
                    funding_lag_ms=funding_lag_ms,
                    prior_realized_net_usdt=prior_realized_dec,
                    initial_entry_fee_usdt=full_entry_fee_dec,
                )
                if x1_eval["extend_to_18h"]:
                    extended_at_12h = True
                    active_deadline = deadline_18h
                    decision_12h = {
                        **x1_eval,
                        "reached_12h_time_cap_boundary": True,
                        "scheme": scheme,
                        "outcome_at_12h": "EXTENDED_TO_18H",
                    }
                else:
                    capped = min(op, target) if side > 0 else max(op, target)
                    tiers.append(_build_exit_tier(proposal, cost, remaining, capped, minute, "TIME_CAP"))
                    decision_12h = {
                        **x1_eval,
                        "reached_12h_time_cap_boundary": True,
                        "scheme": scheme,
                        "outcome_at_12h": "EXIT_AT_12H_TIME_CAP",
                    }
                    break
            elif scheme == "X2_COMPLETED_4H_TREND_AT_12H":
                x2_eval = evaluate_x2_at_12h(last, side, deadline_12h)
                if x2_eval["extend_to_18h"]:
                    extended_at_12h = True
                    active_deadline = deadline_18h
                    decision_12h = {
                        **x2_eval,
                        "reached_12h_time_cap_boundary": True,
                        "scheme": scheme,
                        "outcome_at_12h": "EXTENDED_TO_18H",
                    }
                else:
                    capped = min(op, target) if side > 0 else max(op, target)
                    tiers.append(_build_exit_tier(proposal, cost, remaining, capped, minute, "TIME_CAP"))
                    decision_12h = {
                        **x2_eval,
                        "reached_12h_time_cap_boundary": True,
                        "scheme": scheme,
                        "outcome_at_12h": "EXIT_AT_12H_TIME_CAP",
                    }
                    break

        # Priority 2b: Active deadline TIME_CAP (18h for extended trades)
        if minute >= active_deadline:
            capped = min(op, target) if side > 0 else max(op, target)
            tiers.append(_build_exit_tier(proposal, cost, remaining, capped, minute, "TIME_CAP"))
            break

        # Priority 3: Favorable open gap through target(s)
        if q1 > 0 and side * (op - target1) >= 0 and side * (op - target) >= 0:
            tiers.append(_build_exit_tier(proposal, cost, q1, target1, minute, "TP1_GAP_CAPPED"))
            tiers.append(_build_exit_tier(proposal, cost, q2, target, minute, "TARGET_GAP_CAPPED"))
            q1, q2 = 0.0, 0.0
            break
        if q1 > 0 and side * (op - target1) >= 0:
            tiers.append(_build_exit_tier(proposal, cost, q1, target1, minute, "TP1_GAP_CAPPED"))
            q1 = 0.0
            deferred_tp2_until = minute + MINUTE
        if q2 > 0 and q1 == 0 and minute >= deferred_tp2_until and side * (op - target) >= 0:
            tiers.append(_build_exit_tier(proposal, cost, q2, target, minute, "TARGET_GAP_CAPPED"))
            q2 = 0.0
            break

        # Priority 4: Intraminute STOP precedes TARGET collision
        stop_hit = (lo <= stop) if side > 0 else (hi >= stop)
        if stop_hit:
            tiers.append(_build_exit_tier(proposal, cost, q1 + q2, stop, minute + MINUTE - 1, "STOP"))
            q1, q2 = 0.0, 0.0
            break

        if q1 > 0:
            tp1_hit = (hi >= target1 + TICK - 1e-8) if side > 0 else (lo <= target1 - TICK + 1e-8)
            if tp1_hit:
                tiers.append(_build_exit_tier(proposal, cost, q1, target1, minute + MINUTE - 1, "TP1"))
                q1 = 0.0
                deferred_tp2_until = minute + MINUTE
                continue

        if q2 > 0 and q1 == 0 and minute >= deferred_tp2_until:
            target_hit = (hi >= target) if side > 0 else (lo <= target)
            if target_hit:
                tiers.append(_build_exit_tier(proposal, cost, q2, target, minute + MINUTE - 1, "TARGET"))
                q2 = 0.0
                break

    if not tiers or abs(sum(t["quantity"] for t in tiers) - quantity) > 1e-9:
        raise ValueError("Missing complete exit path or quantity conservation failure")
    if any(t["quantity"] <= 0 for t in tiers):
        raise ValueError("Nonpositive exit tier quantity")

    settled, funding_cash = _compute_funding_settlements(proposal, tiers, mark, funding_events, quantity)
    fee_entry = _fee(float(proposal["effective_entry"]), quantity, cost)
    fee_exit = sum(float(t["fee_exit"]) for t in tiers)
    gross = sum(float(t["gross_usdt"]) for t in tiers)
    drag = sum(float(t["execution_drag_usdt"]) for t in tiers)
    net = gross - drag - fee_entry - fee_exit
    notional = float(proposal["raw_entry"]) * quantity

    journal: list[dict[str, Any]] = [
        {
            "kind": "ENTRY_FEE",
            "timestamp": entry_at,
            "cash_delta": -fee_entry,
            "remaining_quantity": quantity,
        }
    ]
    exited = 0.0
    for tier in tiers:
        exited += float(tier["quantity"])
        remaining_after = round(quantity - exited, 12)
        journal.append({
            "kind": "EXIT_FEE",
            "timestamp": int(tier["exit_at"]),
            "cash_delta": -float(tier["fee_exit"]),
            "quantity_delta": -float(tier["quantity"]),
            "remaining_quantity": remaining_after,
        })
        journal.append({
            "kind": "EXIT_PNL_ACK",
            "timestamp": int(tier["exit_ack_at"]),
            "cash_delta": float(tier["gross_usdt"]) - float(tier["execution_drag_usdt"]),
            "remaining_quantity": remaining_after,
        })
    for receipt in settled:
        journal.append({
            "kind": "FUNDING",
            "timestamp": int(receipt["settlement_at"]),
            "cash_delta": float(receipt["signed_cash_usdt"]),
            "remaining_quantity": float(receipt["quantity"]),
        })
    journal.sort(
        key=lambda row: (
            int(row["timestamp"]),
            {"ENTRY_FEE": 0, "EXIT_FEE": 1, "FUNDING": 2, "EXIT_PNL_ACK": 3}[row["kind"]],
        )
    )

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
    weighted_age = (
        sum(tier["quantity"] * (tier["exit_at"] - entry_at) / MINUTE for tier in tiers) / quantity
    )
    net_after_funding_dec = _decimal(net, "net") + funding_cash
    net_after_funding_bps_dec = DEC_10000 * net_after_funding_dec / _decimal(notional, "notional")

    # Classify post-12h pathway outcome
    exit_at_final = int(last_tier["exit_at"])
    exit_reason_final = str(last_tier["reason"])
    if not decision_12h["reached_12h_time_cap_boundary"]:
        pathway_category = f"EARLY_BEFORE_12H_{exit_reason_final}"
    elif not decision_12h["extend_to_18h"]:
        pathway_category = "EXITED_AT_12H_TIME_CAP"
    else:
        pathway_category = f"EXTENDED_12H_TO_18H_{exit_reason_final}"

    return {
        "candidate": candidate.get("id", "UNKNOWN"),
        "event_id": event.get("event_id", str(proposal["event_time"])),
        "scheme": scheme,
        "side": side,
        "event_time": int(proposal["event_time"]),
        "decision_at": int(proposal["decision_at"]),
        "entry_at": entry_at,
        "entry_index": start_idx,
        "deadline_12h_at": deadline_12h,
        "deadline_18h_at": deadline_18h,
        "exit_at": exit_at_final,
        "exit_ack_at": int(last_tier["exit_ack_at"]),
        "exit_index": int(np.searchsorted(last[:, 0], exit_at_final, side="right")) - 1,
        "raw_entry": float(proposal["raw_entry"]),
        "effective_entry": float(proposal["effective_entry"]),
        "raw_exit": float(last_tier["raw_exit"]),
        "effective_exit": float(last_tier["effective_exit"]),
        "stop": stop,
        "target": target,
        "exit_reason": exit_reason_final,
        "pathway_category": pathway_category,
        "decision_12h": decision_12h,
        "quantity": quantity,
        "entry_notional": notional,
        "fee_entry": fee_entry,
        "fee_exit": fee_exit,
        "gross_usdt": gross,
        "execution_drag_usdt": drag,
        "net_usdt": net,
        "gross_bps": 10_000.0 * gross / notional,
        "net_bps": 10_000.0 * net / notional,
        "net_r": net / (quantity * float(proposal["initial_risk"])),
        "initial_risk": float(proposal["initial_risk"]),
        "risk_bps": float(proposal["risk_bps"]),
        "duration_minutes": (exit_at_final - entry_at) / MINUTE,
        "weighted_exit_age_minutes": weighted_age,
        "tiers": tiers,
        "journal": journal,
        "funding_settlements": settled,
        "settlement_count": len(settled),
        "funding_cash_usdt": str(funding_cash),
        "net_after_funding_usdt": str(net_after_funding_dec),
        "net_after_funding_bps": str(net_after_funding_bps_dec),
    }
