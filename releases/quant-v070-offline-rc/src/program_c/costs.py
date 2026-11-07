"""Explicit per-base price costs; no synthetic projection becomes executable PnL."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .integrity import digest, number, require
from .protocol import COST_CASES


def cost_projection(entry: float, exit_price: float, hours: float, costs: dict | None, case: str) -> dict:
    require(case in COST_CASES, "COST_CASE_NOT_PREDECLARED")
    if costs is None:
        return {"total_per_base": None, "components_per_base": None, "status": "COST_UNKNOWN",
                "executable_status": "EXE_COST_UNVERIFIED"}
    fee_m, spread_m, slip_m, carry_m, impact_m, jump_bps = COST_CASES[case]
    entry_fee = costs[costs["entry_fee_mode"].lower() + "_fee_each_side_bps"]
    exit_fee = costs[costs["exit_fee_mode"].lower() + "_fee_each_side_bps"]
    reference_price = max(entry, exit_price)
    impact_bps = costs["impact_bps_at_reference"] * costs["assumed_notional_quote"] / costs["reference_notional_quote"]
    cadence = math.ceil(hours / costs["funding_cadence_hours"])
    components = {
        "entry_fee": entry * entry_fee * fee_m / 10_000,
        "exit_fee": exit_price * exit_fee * fee_m / 10_000,
        "round_trip_spread": reference_price * costs["spread_round_trip_bps"] * spread_m / 10_000,
        "entry_slippage": entry * costs["entry_slippage_bps"] * slip_m / 10_000,
        "exit_slippage": exit_price * costs["exit_slippage_bps"] * slip_m / 10_000,
        "impact_size": (entry + exit_price) * impact_bps * impact_m / 10_000,
        "funding": reference_price * costs["funding_bps_per_cadence"] * cadence * carry_m / 10_000,
        "carrying": reference_price * costs["carrying_bps_per_day"] * hours / 24 * carry_m / 10_000,
        "financing": reference_price * costs["financing_bps_per_day"] * hours / 24 * carry_m / 10_000,
        "jump_allowance": reference_price * jump_bps / 10_000,
    }
    capacity = costs["available_capacity_quote"]
    return {"total_per_base": sum(components.values()), "components_per_base": components,
            "charged_funding_cadences": cadence, "assumed_notional_quote": costs["assumed_notional_quote"],
            "capacity_status": "UNKNOWN" if capacity is None else (
                "ASSUMED_SUFFICIENT" if capacity >= costs["assumed_notional_quote"] else "INSUFFICIENT"),
            "instrument_specification": "SYNTHETIC_ASSUMPTION_ONLY", "status": "UNCALIBRATED_SYNTHETIC_MODEL",
            "executable_status": "EXE_COST_UNVERIFIED"}


@dataclass(frozen=True)
class ExecutionEvidence:
    """Material for future external verification. Self-asserted flags are insufficient."""

    admission_root: str
    payload: dict


def hypothetical_executable_r(evidence: ExecutionEvidence, trusted_roots: set[str],
                              direction: str, initial_price_risk: float, asof_ms: int) -> float | None:
    """Requires a Controller-pinned external evidence payload; task trust set is empty.

    This calculates a hypothetical quote/capacity payoff, never an actual fill.
    Tests use fabricated pins solely to exercise the numerical branch.
    """
    p = evidence.payload
    if evidence.admission_root not in trusted_roots or digest(p) != evidence.admission_root:
        return None
    required = {"source", "symbol", "venue", "instrument_type", "price_unit", "multiplier", "tick",
                "entry_ms", "exit_ms", "entry_bid", "entry_ask", "exit_bid", "exit_ask",
                "entry_capacity_quote", "exit_capacity_quote", "notional_quote", "available_ms", "durable_ms",
                "fees_funding_impact_per_base", "independently_verified"}
    if set(p) != required or p["independently_verified"] is not True or p["source"] != "NATIVE_QUALIFIED":
        return None
    if p["instrument_type"] != "LINEAR_QUOTE_BASE" or p["price_unit"] != "USDT_PER_BASE":
        return None
    numeric = ["multiplier", "tick", "entry_bid", "entry_ask", "exit_bid", "exit_ask", "notional_quote",
               "entry_capacity_quote", "exit_capacity_quote"]
    if not all(number(p[k], positive=True) for k in numeric) or not number(initial_price_risk, positive=True):
        return None
    if not (p["entry_bid"] <= p["entry_ask"] and p["exit_bid"] <= p["exit_ask"]
            and p["entry_ms"] < p["exit_ms"] <= p["available_ms"] <= p["durable_ms"] <= asof_ms
            and min(p["entry_capacity_quote"], p["exit_capacity_quote"]) >= p["notional_quote"]
            and number(p["fees_funding_impact_per_base"])):
        return None
    if direction == "LONG":
        payoff = p["exit_bid"] - p["entry_ask"]
    elif direction == "SHORT":
        payoff = p["entry_bid"] - p["exit_ask"]
    else:
        return None
    return (payoff - p["fees_funding_impact_per_base"]) / initial_price_risk
