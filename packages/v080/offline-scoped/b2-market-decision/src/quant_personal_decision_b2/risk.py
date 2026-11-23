"""Decimal market geometry and conditional, quantity-independent cost math."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from itertools import pairwise
from math import lcm
from typing import Any

from .model import HOUR, D, DecisionError, Market, Policy, check, decimal

ZERO = D(0)


@dataclass(frozen=True)
class Filters:
    tick: Decimal
    min_price: Decimal
    max_price: Decimal
    step: Decimal
    min_qty: Decimal
    max_qty: Decimal
    min_notional: Decimal


def round_grid(value: Decimal, step: Decimal, *, up: bool) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * step


def filters(instrument: dict[str, Any]) -> Filters:
    accepted = instrument["filters"]
    price = accepted["PRICE_FILTER"]
    lot = accepted["LOT_SIZE"]
    market_lot = accepted.get("MARKET_LOT_SIZE", lot)
    steps = [decimal(row["stepSize"], "stepSize", positive=True) for row in (lot, market_lot)]
    exponent = min(int(step.as_tuple().exponent) for step in steps)
    step = D(lcm(*(int(v.scaleb(-exponent)) for v in steps))).scaleb(exponent)
    return Filters(decimal(price["tickSize"], "tickSize", positive=True), D(price["minPrice"]), D(price["maxPrice"]),
                   step, max(D(lot["minQty"]), D(market_lot["minQty"])),
                   min(D(lot["maxQty"]), D(market_lot["maxQty"])), D(accepted["MIN_NOTIONAL"]["notional"]))


def prices(episode: dict[str, Any], spec: Filters) -> tuple[Decimal, Decimal, Decimal]:
    low, high = (D(x) for x in episode["entry_band_unrounded"])
    return (round_grid(low, spec.tick, up=True), round_grid(high, spec.tick, up=False),
            round_grid(D(episode["hard_stop_unrounded"]), spec.tick, up=episode["sign"] < 0))


def within_filter(price: Decimal, spec: Filters) -> bool:
    return price > 0 and price >= spec.min_price and (spec.max_price <= 0 or price <= spec.max_price)


def reference_vwap(levels: list[list[str]], quantity: Decimal) -> tuple[Decimal | None, Decimal]:
    offered = sum((D(row[1]) for row in levels), D(0))
    if quantity <= 0 or offered < quantity:
        return None, offered
    remaining = quantity
    value = D(0)
    for price, available in levels:
        filled = min(D(available), remaining)
        value += D(price) * filled
        remaining -= filled
        if not remaining:
            break
    return value / quantity, offered


def path_net(sign: int, entry: Decimal, exit_fill: Decimal, fee: Decimal, funding: Decimal) -> Decimal:
    return sign * (exit_fill - entry) - (entry + exit_fill) * fee - funding


def funding_model(values: dict[str, Any], market: Market, sign: int, entry: Decimal,
                  policy: Policy) -> tuple[Decimal, dict[str, Any], str | None]:
    next_time = values["nextFundingTime"]
    rate = D(values["lastFundingRate"])
    mark = D(values["markPrice"])
    regular = [row["source_ms"] for row in market.context["funding"]["values"]["rows"]
               if row.get("fundingRateType", "Regular") == "Regular"]
    gaps = [b - a for a, b in pairwise(regular)]
    cadence = gaps[-1] if len(gaps) >= 2 and gaps[-1] == gaps[-2] and 0 < gaps[-1] <= 24 * HOUR else None
    exit_ms = market.evaluated_ms + policy.holding_hours * HOUR
    problem = None
    crossings = 0
    if next_time <= market.evaluated_ms:
        problem = "FUNDING_TIME_UNRECONCILED"
    elif next_time <= exit_ms:
        crossings = 1
        if cadence:
            crossings += (exit_ms - next_time) // cadence
        else:
            problem = "FUNDING_CADENCE_UNESTABLISHED"
    adverse_rate = max(sign * rate, policy.funding_stress_rate)
    basis = max(mark, entry)
    cost = basis * adverse_rate * crossings
    return cost, {"indicated_rate": rate, "signed_indicated_debit_rate": sign * rate,
                  "adverse_rate_used": adverse_rate, "basis_usdt_per_base": basis,
                  "next_funding_ms": next_time, "inferred_cadence_ms": cadence,
                  "modeled_crossings": crossings, "stress_cost_usdt_per_base": cost,
                  "holding_horizon_hours": policy.holding_hours, "planned_horizon_end_ms": exit_ms,
                  "rate_source_receipt_id": market.context["mark"]["receipt_id"],
                  "cadence_source_receipt_id": market.context["funding"]["receipt_id"]}, problem


def target_levels(episode: dict[str, Any], entry: Decimal, stop: Decimal, spec: Filters, policy: Policy) -> list[dict[str, Any]]:
    sign = episode["sign"]
    step = spec.tick
    nominal = sign * (entry - stop)
    first = episode["obstacles"]["first"]
    obstacle = D(first["price"]) if first else None
    levels = []
    for i, multiple in enumerate(policy.tp_multiples, 1):
        target = round_grid(entry + sign * multiple * nominal, step, up=sign < 0)
        issue = None
        if nominal <= 0 or sign * (target - entry) <= 0:
            issue = "TARGET_GEOMETRY_UNESTABLISHED"
        elif obstacle is None:
            issue = "FIRST_OBSTACLE_UNESTABLISHED"
        elif sign * (obstacle - target) < step:
            issue = "TARGET_BEYOND_FIRST_OBSTACLE"
        elif not within_filter(target, spec):
            issue = "TARGET_INSTRUMENT_FILTER"
        levels.append({"label": f"TP{i}", "price": target if not issue else None,
                       "status": "UNESTABLISHED" if issue else "ESTABLISHED", "reason": issue})
    return levels


def market_plan(market: Market, episode: dict[str, Any], policy: Policy,
                frozen_targets: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], list[str]]:
    c = {key: value["values"] for key, value in market.context.items()}
    sign = episode["sign"]
    tr = D(episode["atr14"])
    spec = filters(c["instrument"])
    low, high, stop = prices(episode, spec)
    ask, bid = D(c["quote"]["askPrice"]), D(c["quote"]["bidPrice"])
    mark, index = D(c["mark"]["markPrice"]), D(c["mark"]["indexPrice"])
    spread = ask - bid
    slippage = policy.slippage_bps / 10_000
    reasons = []
    check(low <= high and within_filter(stop, spec), "INSTRUMENT_PRICE_FILTER")
    rounded_quantity = round_grid(policy.reference_base, spec.step, up=False)
    side, other_side = ("asks", "bids") if sign > 0 else ("bids", "asks")
    entry_vwap, displayed = reference_vwap(c["depth"][side], rounded_quantity)
    exit_vwap, opposing_displayed = reference_vwap(c["depth"][other_side], rounded_quantity)
    best = ask if sign > 0 else bid
    book_best = D(c["depth"][side][0][0]) if c["depth"][side] else None
    if entry_vwap is None or exit_vwap is None:
        reasons.append("REFERENCE_DEPTH_INSUFFICIENT")
    if book_best is None or abs(book_best - best) / best * 10_000 > policy.max_quote_depth_gap_bps:
        reasons.append("QUOTE_DEPTH_INCONSISTENT")
    qualified_book = sign * max(sign * best, sign * entry_vwap) if entry_vwap is not None else best
    entry = round_grid(qualified_book * (1 + sign * slippage), spec.tick, up=sign > 0)
    if not spec.min_qty <= rounded_quantity <= spec.max_qty or entry * rounded_quantity < spec.min_notional:
        reasons.append("REFERENCE_INSTRUMENT_MINIMUM")
    if sign * entry > sign * (high if sign > 0 else low):
        reasons.append("MISSED_NO_CHASE")
    elif entry < low or entry > high:
        reasons.append("OUTSIDE_ENTRY_ZONE")
    if (any(not within_filter(price, spec) for price in (entry, low, high, stop))
            or sign * (entry - stop) <= 0):
        reasons.append("INSTRUMENT_PRICE_FILTER")
    basis_bps = (mark - index) / index * 10_000
    if abs(basis_bps) > policy.max_basis_bps:
        reasons.append("MARK_INDEX_BASIS_LIMIT")
    momentum = sign * (market.bars["5m"][-1].close - market.bars["5m"][-4].close)
    if momentum < -tr * policy.max_5m_adverse_atr:
        reasons.append("FIVE_MINUTE_ADVERSE_MOMENTUM")
    funding, funding_view, funding_problem = funding_model(c["mark"], market, sign, entry, policy)
    if funding_problem:
        reasons.append(funding_problem)
    shock = max(spec.tick, tr * policy.stop_stress_atr)

    def exit_price(zone: Decimal, *, stress: Decimal = ZERO) -> Decimal:
        return round_grid(zone - sign * (spread / 2 + zone * slippage + stress), spec.tick, up=sign < 0)

    stressed_stop = exit_price(stop, stress=shock)
    unit_risk = -path_net(sign, entry, stressed_stop, policy.fee_rate, funding)
    geometric_risk = sign * (best - stop)
    if unit_risk <= 0 or stressed_stop <= 0 or geometric_risk <= 0:
        raise DecisionError("INVALID_STOP_GEOMETRY")
    template = frozen_targets if frozen_targets is not None else target_levels(episode, entry, stop, spec, policy)
    targets = []
    for row in template:
        p = D(row["price"]) if row["price"] is not None else None
        view = {**row, "exit_fill": None, "geometric_r": None, "net_usdt_per_base": None, "net_r": None}
        if p is not None:
            fill = exit_price(p)
            net = path_net(sign, entry, fill, policy.fee_rate, funding)
            view.update(exit_fill=fill, geometric_r=sign * (p - best) / geometric_risk,
                        net_usdt_per_base=net, net_r=net / unit_risk)
        targets.append(view)

    first = episode["obstacles"]["first"]
    obstacle_net = None
    if first:
        obstacle_level = D(first["price"])
        conservative_exit = exit_price(obstacle_level - sign * spec.tick)
        obstacle_net = path_net(sign, entry, conservative_exit, policy.fee_rate, funding) / unit_risk
        if obstacle_net < policy.min_obstacle_after_cost_r:
            reasons.append("FIRST_OBSTACLE_ROOM_INSUFFICIENT")
    else:
        reasons.append("FIRST_OBSTACLE_UNESTABLISHED")
    if targets[0]["net_r"] is None or targets[0]["net_r"] < policy.min_tp1_after_cost_r:
        reasons.append("TP1_AFTER_COST_R_INSUFFICIENT")
    paths = [{"name": "STOP_ONLY", "net_usdt_per_base": -unit_risk, "net_r": D(-1)}]
    total = D(0)
    remaining = D(1)
    for i, (target, fraction) in enumerate(zip(targets, policy.exit_fractions, strict=True)):
        if target["net_usdt_per_base"] is None:
            break
        total += fraction * target["net_usdt_per_base"]
        remaining -= fraction
        cash = total - remaining * unit_risk
        paths.append({"name": "_".join(row["label"] for row in targets[:i + 1]) + ("_THEN_STOP" if remaining else ""),
                      "net_usdt_per_base": cash, "net_r": cash / unit_risk})
    oi_rows = c["oi_history"]["rows"]
    change = None
    if len(oi_rows) >= 2 and oi_rows[-1]["source_ms"] - oi_rows[-2]["source_ms"] == c["oi_history"]["period_ms"]:
        earlier, later = (D(row["sumOpenInterest"]) for row in oi_rows[-2:])
        if earlier:
            change = (later - earlier) / earlier
    return {
        "schema": "B2_MARKET_PLAN_V1", "price_currency": "USDT", "risk_unit": "USDT_PER_BASE_UNIT",
        "entry_low": low, "entry_high": high, "no_chase_boundary": high if sign > 0 else low,
        "unrounded_market_side_price": best, "entry_reference_vwap": entry_vwap, "entry_fill": entry,
        "hard_stop": stop, "stop_stress_usdt_per_base": shock, "expected_stop_stress_fill": stressed_stop,
        "unit_stop_loss_usdt": unit_risk, "geometric_risk_usdt_per_base": geometric_risk,
        "reference_requested_base": policy.reference_base, "reference_rounded_base": rounded_quantity,
        "reference_nominal_usdt": entry * rounded_quantity, "reference_stop_loss_usdt": unit_risk * rounded_quantity,
        "reference_use": "VISIBLE_LIQUIDITY_TEST_ONLY", "displayed_entry_side_base": displayed,
        "displayed_exit_side_base": opposing_displayed, "reference_depth_sufficient": entry_vwap is not None and exit_vwap is not None,
        "bid": bid, "ask": ask, "spread_usdt": spread, "fee_rate_each_side": policy.fee_rate,
        "slippage_bps_each_side": policy.slippage_bps, "tick": spec.tick, "joint_qty_step": spec.step,
        "min_notional_usdt": spec.min_notional, "mark": mark, "index": index, "mark_index_basis_bps": basis_bps,
        "funding": funding_view, "open_interest_base": c["oi"]["openInterest"],
        "oi_period_change_fraction": change,
        "oi_participation": "UNKNOWN_GAP_OR_WARMUP" if change is None else (
            "RISING" if change > 0 else "FALLING" if change < 0 else "FLAT"),
        "five_minute_directional_displacement_usdt": momentum, "oi_omitted_periods": c["oi_history"]["omitted_periods"],
        "targets": targets, "obstacles": episode["obstacles"], "first_obstacle_after_cost_r": obstacle_net,
        "remaining_to_first_obstacle_usdt_per_base": None if first is None else sign * (D(first["price"]) - entry),
        "conditional_paths": paths, "partial_exit_fractions": policy.exit_fractions,
        "statistical_expected_value": "UNKNOWN", "evidence_confidence": "SYNTHETIC_ONLY",
    }, list(dict.fromkeys(reasons))
