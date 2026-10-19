"""Entry-notional economics with explicit native settlement chronology.

Rates below are assumptions, not exchange tariffs. Mark prices value funding;
they are never entry or exit fills. No passive-fill inference is implemented.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from . import HORIZONS, PLAN

US = 1_000_000


def finite(value: Any) -> bool:
    return type(value) in (float, int) and math.isfinite(value)


@dataclass(frozen=True, slots=True)
class CostAssumptions:
    name: str
    entry_fee_bp: float | None
    exit_fee_bp: float | None
    entry_spread_bp: float | None
    exit_spread_bp: float | None
    entry_slippage_bp: float | None
    exit_slippage_bp: float | None

    def valid(self) -> bool:
        return all(finite(v) and v >= 0 for k, v in asdict(self).items() if k != "name")

    @property
    def nominal_round_trip_bp(self) -> float | None:
        if not self.valid():
            return None
        return sum(v for k, v in asdict(self).items() if k != "name")


BASELINE = CostAssumptions("baseline_16bp", 5.0, 5.0, 1.0, 1.0, 2.0, 2.0)
STRESS = CostAssumptions("stress_32bp", 8.0, 8.0, 3.0, 3.0, 5.0, 5.0)
SCENARIOS = (BASELINE, STRESS)


@dataclass(frozen=True, slots=True)
class Settlement:
    t_us: int
    rate: float | None
    mark: float | None


@dataclass(frozen=True, slots=True)
class Outcome:
    entry_t: int
    exit_t: int
    entry_price: float | None
    exit_price: float | None
    settlements: tuple[Settlement, ...] = ()
    # A complete, independent native calendar is required even for zero events.
    expected_settlements_us: tuple[int, ...] | None = None
    funding_coverage_us: tuple[int, int] | None = None

    @property
    def simple_return(self) -> float | None:
        if not (finite(self.entry_price) and self.entry_price > 0
                and finite(self.exit_price) and self.exit_price > 0):
            return None
        value = self.exit_price / self.entry_price - 1.0
        return value if finite(value) else None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Outcome:
        required = {"entry_t", "exit_t", "entry_price", "exit_price", "settlements",
                    "expected_settlements_us", "funding_coverage_us"}
        if type(value) is not dict or set(value) != required:
            raise ValueError("OUTCOME_SCHEMA_INVALID")
        try:
            return cls(value["entry_t"], value["exit_t"], value["entry_price"],
                       value["exit_price"], tuple(Settlement(**s) for s in value["settlements"]),
                       None if value["expected_settlements_us"] is None else
                       tuple(value["expected_settlements_us"]),
                       None if value["funding_coverage_us"] is None else
                       tuple(value["funding_coverage_us"]))
        except (TypeError, KeyError):
            raise ValueError("OUTCOME_SCHEMA_INVALID") from None


def funding_long_debit(outcome: Outcome) -> tuple[float | None, str]:
    coverage = outcome.funding_coverage_us
    calendar = outcome.expected_settlements_us
    if (coverage is None or len(coverage) != 2 or calendar is None
            or any(type(t) is not int for t in coverage)
            or not coverage[0] <= outcome.entry_t * US < outcome.exit_t * US <= coverage[1]):
        return None, "UNRESOLVED_FUNDING_COVERAGE"
    if (any(type(t) is not int for t in calendar)
            or list(calendar) != sorted(set(calendar))
            or any(not coverage[0] <= t <= coverage[1] for t in calendar)):
        return None, "FUNDING_CALENDAR_INVALID"
    times = [s.t_us for s in outcome.settlements]
    if any(type(t) is not int for t in times) or times != sorted(set(times)):
        return None, "FUNDING_CHRONOLOGY_INVALID"
    inside = lambda t: outcome.entry_t * US < t <= outcome.exit_t * US
    expected = [t for t in calendar if inside(t)]
    observed = [s for s in outcome.settlements if inside(s.t_us)]
    if [s.t_us for s in observed] != expected:
        return None, "UNRESOLVED_FUNDING_SETTLEMENT"
    if any(not finite(s.rate) or not finite(s.mark) or s.mark <= 0 for s in observed):
        return None, "UNRESOLVED_FUNDING_RATE_OR_MARK"
    debit = sum(s.rate * s.mark / outcome.entry_price for s in observed)
    return (debit, "RESOLVED") if finite(debit) else (None, "UNRESOLVED_FUNDING_RATE_OR_MARK")


def policy_action(prediction: float | None, horizon_h: int,
                  assumptions: CostAssumptions = BASELINE) -> int:
    if horizon_h not in HORIZONS:
        raise ValueError("HORIZON_NOT_FROZEN")
    nominal = assumptions.nominal_round_trip_bp
    if not finite(prediction) or nominal is None:
        return 0
    threshold = (nominal + PLAN["edge_buffer_bp"]
                 + PLAN["carry_reserve_bp_per_day"] * horizon_h / 24) / 10000
    return int(prediction > threshold) - int(prediction < -threshold)


def economics(outcome: Outcome | None, action: int, horizon_h: int,
              assumptions: CostAssumptions = BASELINE, *, maker: bool = False) -> dict[str, Any]:
    if type(action) is not int or action not in (-1, 0, 1) or horizon_h not in HORIZONS:
        raise ValueError("ACTION_OR_HORIZON_INVALID")
    result = {
        "action": action, "status": "NO_ACTION", "reason": "NO_ACTION",
        "gross_return": 0.0, "funding_debit": 0.0, "net_return": 0.0,
        "sleeve_pnl": 0.0, "capital_sleeve": 1.0 / horizon_h,
        "turnover": 0.0, "break_even_cost_bp": None,
        **{k: 0.0 for k in ("entry_fee", "exit_fee", "entry_spread", "exit_spread",
                           "entry_slippage", "exit_slippage", "total_cost")},
    }
    if maker and action:
        result.update(action=0, reason="FILL_UNKNOWN", fill_model_utility=None)
        return result
    if not action:
        return result
    result.update(status="UTILITY_UNRESOLVED", reason="UNRESOLVED_PRICE",
                  **{k: None for k in ("gross_return", "funding_debit", "net_return",
                                      "sleeve_pnl", "turnover", "total_cost",
                                      "entry_fee", "exit_fee", "entry_spread", "exit_spread",
                                      "entry_slippage", "exit_slippage")})
    if (outcome is None or type(outcome.entry_t) is not int or type(outcome.exit_t) is not int
            or outcome.exit_t - outcome.entry_t != horizon_h * 3600
            or outcome.simple_return is None):
        return result
    if not assumptions.valid():
        result["reason"] = "UNRESOLVED_COST_ASSUMPTION"
        return result
    funding, reason = funding_long_debit(outcome)
    if funding is None:
        result["reason"] = reason
        return result
    ratio = outcome.exit_price / outcome.entry_price
    components = {
        k.removesuffix("_bp"): v / 10000 * (ratio if k.startswith("exit_") else 1.0)
        for k, v in asdict(assumptions).items() if k != "name"
    }
    gross = action * outcome.simple_return
    signed_funding = action * funding
    total = sum(components.values())
    net = gross - signed_funding - total
    if not all(finite(v) for v in (*components.values(), gross, signed_funding, net)):
        result["reason"] = "UNRESOLVED_NONFINITE_ECONOMICS"
        return result
    result.update(components, status="RESOLVED", reason="RESOLVED", gross_return=gross,
                  funding_debit=signed_funding, total_cost=total, net_return=net,
                  sleeve_pnl=net / horizon_h, turnover=(1 + ratio) / horizon_h,
                  break_even_cost_bp=(gross - signed_funding) * 10000)
    return result


MAKER_SENSITIVITY = {
    "status": "FILL_UNKNOWN", "fill_fractions": [0, 0.25, 0.5, 1],
    "entry_fee_bp_assumption": 2, "exit": "ASSUMED_TAKER_LIQUIDATION",
    "adverse_selection": "UNKNOWN", "cancellation": "UNKNOWN",
    "utility": None, "interpretation": "SCENARIO_BOUNDS_ONLY_NO_ACK_OR_QUEUE_EVIDENCE",
    "filled_subset": "NOT_SELECTED_FROM_FUTURE_PRICES",
}
