"""Synthetic closed-form arithmetic only: no market reader, orders or replay.

Constant-notional bps are an idealized bridge. The separate two-price expression
charges fees on effective executed notionals. Neither is a funded account path.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Context, Decimal, localcontext
from math import ceil, sqrt
from statistics import NormalDist

D = Decimal
BPS = D(10000)
ZERO = D(0)
ONE = D(1)
NOTIONAL = D(1000)
MINUTE = 60000
HOUR = 3600000


def context():
    return localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN))


def money(value: Decimal) -> str:
    with context():
        return str(value.quantize(D("0.000000000001")))


def eligible_settlements(start: int, end: int, timestamps: list[int]) -> list[int]:
    """Possible ownership intersects inclusive +/-15s; synthetic times only."""
    if start > end or len(set(timestamps)) != len(timestamps):
        raise ValueError("invalid interval or duplicate settlement identity")
    return sorted(s for s in timestamps if start <= s + 15000 and end >= s - 15000)


def funding_proof_floor(settlement: int, rate_available: int = 0) -> int:
    # At a minute boundary, the right-hand intersecting minute is still required.
    last_end = ((settlement + 15000) // MINUTE + 1) * MINUTE
    return max(settlement + MINUTE, last_end + MINUTE, rate_available)


def geometry(stop_bp: Decimal, events: int, tick_bp: Decimal = ZERO) -> dict:
    if events < 0 or tick_bp < 0 or stop_bp <= 0:
        raise ValueError("invalid geometry")
    with context():
        c = D(44) + D(8) * events + tick_bp
        minimum = max(D(30), D(2) * c)
        eligible = D(30) <= stop_bp <= D(250) and stop_bp >= minimum
        return {"stress_cost_bp": money(c), "minimum_stop_bp": money(minimum),
                "eligible": eligible, "target_bp": money(D(2) * stop_bp),
                "status": "GEOMETRY_POSSIBLE_ONLY" if eligible else
                "STRESS_COST_GEOMETRY_INELIGIBLE"}


def nominal_payoff(
    market_move_bp: Decimal, side: int, stop_bp: Decimal, fee: Decimal,
    spread: Decimal, slip: Decimal, funding_bp: Decimal, events: int,
    notional: Decimal = NOTIONAL, tick_bp: Decimal = ZERO,
    funding_multiplier: Decimal = ONE, cap_target: bool = False,
) -> dict:
    if side not in (-1, 1) or min(fee, spread, slip, funding_bp, tick_bp) < 0:
        raise ValueError("side or adverse costs invalid")
    if events < 0 or stop_bp <= 0 or notional <= 0 or funding_multiplier <= 0:
        raise ValueError("invalid scale")
    with context():
        gross = D(side) * market_move_bp
        if cap_target:
            gross = min(gross, D(2) * stop_bp)
        fees = D(2) * fee
        execution_drag = D(2) * (spread + slip) + tick_bp
        funding = funding_bp * events * funding_multiplier
        costs = fees + execution_drag + funding
        net = gross - costs
        return {"gross_bp": money(gross), "fee_bp": money(fees),
                "execution_drag_bp": money(execution_drag), "funding_bp": money(funding),
                "net_bp": money(net), "net_usdt": money(notional * net / BPS),
                "net_R": money(net / stop_bp), "cost_bp": money(costs),
                "breakeven_gross_move_bp": money(costs),
                "ideal_binary_p_BE": money((stop_bp + costs) / (D(3) * stop_bp)),
                "reserve_usdt": money(D("1.10") * notional * funding_bp * events / BPS),
                "funding_liability_usdt": money(notional * funding / BPS)}


def two_price_payoff(row: dict, event_count: int) -> dict:
    """Invented entry/exit levels, adverse ticks and actual-notional fees once."""
    with context():
        entry = D(row["entry_price"])
        raw_exit = entry * (D(1) + D(row["market_move_bp"]) / BPS)
        side = row["side"]
        if row["cap_target"]:
            target = entry * (D(1) + side * D(2) * D(row["stop_bp"]) / BPS)
            raw_exit = min(raw_exit, target) if side == 1 else max(raw_exit, target)
        drag = (D(row["spread_bp"]) + D(row["slip_bp"])) / BPS
        tick = D(row["price_tick"])
        if entry <= 0 or raw_exit <= 0 or tick <= 0:
            raise ValueError("nonpositive invented price/tick")

        def round_price(price: Decimal, buy: bool) -> Decimal:
            rounding = ROUND_CEILING if buy else ROUND_FLOOR
            return (price / tick).to_integral_value(rounding=rounding) * tick

        effective_entry = round_price(entry * (1 + side * drag), side == 1)
        effective_exit = round_price(raw_exit * (1 - side * drag), side == -1)
        q = D(row["notional_usdt"]) / effective_entry
        gross = q * side * (raw_exit - entry)
        effective_gross = q * side * (effective_exit - effective_entry)
        fees = q * (effective_entry + effective_exit) * D(row["fee_bp"]) / BPS
        funding = q * entry * D(row["funding_mark_multiplier"])
        funding *= D(row["funding_rate_bp"]) * event_count / BPS
        net = effective_gross - fees - funding
        return {"raw_exit": money(raw_exit), "effective_entry": money(effective_entry),
                "effective_exit": money(effective_exit), "quantity_algebraic": money(q),
                "raw_gross_usdt": money(gross), "embedded_drag_usdt": money(gross-effective_gross),
                "fees_usdt": money(fees), "funding_usdt": money(funding),
                "net_usdt": money(net),
                "net_bp_on_effective_entry_notional": money(net / D(row["notional_usdt"]) * BPS),
                "scope": "TWO_INVENTED_LEVELS_NO_FUNDED_BOOK_OR_FILL_PROCESS"}


def funding_cashflow(side: int, notional: Decimal, rate_bp: Decimal) -> Decimal:
    if side not in (-1, 1) or notional <= 0:
        raise ValueError("invalid funding scale")
    with context():
        return -side * notional * rate_bp / BPS


def funding_knowledge(proof: bool, events: int | None) -> str:
    return "KNOWN_SYNTHETIC_SCHEDULE" if proof and events is not None else "UNKNOWN"


def mean_power(sigma: float, delta: float, comparisons: int, sided: int,
               n: float, alpha: float = 0.05, target: float = 0.8) -> dict:
    if sigma <= 0 or delta <= 0 or comparisons < 1 or sided not in (1, 2) or n <= 0:
        raise ValueError("invalid planning inputs")
    if not 0 < alpha < 1 or not 0 < target < 1:
        raise ValueError("invalid probability")
    normal = NormalDist()
    z = normal.inv_cdf(1 - alpha / (comparisons * sided))
    n80 = ceil(((z + normal.inv_cdf(target)) * sigma / delta) ** 2)
    shift = delta * sqrt(n) / sigma
    power = 1 - normal.cdf(z - shift)
    if sided == 2:
        power += normal.cdf(-z - shift)
    return {"z_critical": z, "n_for_80pct_approx": n80, "power_approx": power,
            "MDE_at_80pct_bp": (z + normal.inv_cdf(target)) * sigma / sqrt(n),
            "scope": "NORMAL_KNOWN_VARIANCE_EQUAL_INFORMATION_PLANNING_ONLY"}


def proportion_n(p0: float, p1: float, comparisons: int, sided: int = 1) -> int:
    if not 0 < p0 < 1 or not 0 < p1 < 1 or p0 == p1:
        raise ValueError("invalid proportion hypothesis")
    if comparisons < 1 or sided not in (1, 2):
        raise ValueError("invalid multiplicity")
    z = NormalDist().inv_cdf(1 - 0.05 / (comparisons * sided))
    zb = NormalDist().inv_cdf(0.8)
    return ceil(((z * sqrt(p0 * (1-p0)) + zb * sqrt(p1 * (1-p1))) / (p1-p0)) ** 2)


def effective_n(n: int, serial_rho: float) -> float:
    """Finite-N AR(1) illustration, not an estimated trade dependence model."""
    if n < 1 or not 0 <= serial_rho < 1:
        raise ValueError("invalid effective N")
    design_effect = 1 + 2 * sum((1-k/n) * serial_rho**k for k in range(1, n))
    return n / design_effect


def claim_valid(kind: str, x: dict) -> bool:
    """Finite synthetic audit predicates. No state transitions/market ingestion."""
    predicates = {
        "stale_mark": lambda: 0 <= x["age_ms"] <= 120000,
        "sl_tp": lambda: D(x["claimed_gross_bp"]) == -D(x["stop_bp"]),
        "gap": lambda: D(x["claimed_loss_bp"]) >= D(x["stop_bp"]) + D(x["gap_bp"]),
        "dual_hour": lambda: not (x["terminal_on_hour"] and x["new_seed_same_hour"]),
        "missing_hour": lambda: x["available_hours"] == x["required_hours"],
        "funding_floor": lambda: x["claimed_final_ms"] >= funding_proof_floor(x["S"]),
        "schedule": lambda: x["claimed_n"] == len(eligible_settlements(
            x["start"], x["end"], x["timestamps"])),
        "stress12": lambda: x["eligible_claim"] == geometry(D(250), 13)["eligible"],
        "support": lambda: min(x["fold_counts"]) >= 100,
        "oos": lambda: not (x["outcomes_exposed"] and x["blind_oos_claim"]),
        "conflict": lambda: len(set(x["same_source_close_prices"])) == 1,
        "paid_liability": lambda: not (x["paid"] and D(x["still_liable_usdt"]) > 0),
        "shared_kill": lambda: not x["B_killed_by_A_loss"],
        "quantity": lambda: D(x["exit_qty"]) <= D(x["filled_qty"]),
    }
    if kind not in predicates:
        raise ValueError("unknown finite claim")
    return predicates[kind]()
