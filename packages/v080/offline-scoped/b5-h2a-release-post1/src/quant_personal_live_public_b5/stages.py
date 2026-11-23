"""Signed first-run request stages and nominal debit calculation."""

from dataclasses import dataclass

from quant_personal_public_b1.policy import require
from quant_personal_public_bridge_b4.collector import WARM_BARS, completed_end, observation_query
from quant_personal_public_bridge_b4.normalize import OBSERVATIONS
from quant_personal_public_bridge_b4.routes import INSTRUMENTS, KLINES, TIME

from .contract import (
    BASE_MAX_REQUESTS, BASE_MAX_WEIGHT, FUNDING, INTERVALS, SYMBOL_ORDER, PublicRequest, bounded_int,
)

SCOPE_V2 = "H2A_OWNER_PUBLIC_SCOPE_V2"
STAGE_CONTRACT = "H2A_FIRST_CANARY_V1"
TIMEOUT_PROFILE = "B5_SCAN60S_REQUEST1500MS_V1"
CANARY_ROUTES = (TIME, INSTRUMENTS)


def market_requests(cutoff):
    """Exact market continuation from the first witnessed venue cutoff."""
    for symbol in SYMBOL_ORDER:
        for frame, width in INTERVALS.items():
            end = completed_end(frame, cutoff)
            yield PublicRequest(KLINES, {"symbol": symbol, "interval": frame, "limit": WARM_BARS,
                                        "startTime": end-WARM_BARS*width, "endTime": end-width})
    for symbol in SYMBOL_ORDER:
        for name, route in OBSERVATIONS.items():
            if route != INSTRUMENTS:
                yield observation_query(name, symbol, cutoff)
    yield PublicRequest(TIME, {})


def market_floor():
    # This fixed UTC fixture date affects only bounds, never the route weights.
    requests = tuple(market_requests(1_735_689_720_000))
    known = sum(r.validate()[0] for r in requests if r.route != FUNDING)
    funding = sum(r.route == FUNDING for r in requests)
    return len(requests), known, funding


@dataclass(frozen=True)
class StagePlan:
    market_count: int | None
    market_weight: int | None

    @property
    def market_allowed(self):
        return self.market_count is not None

    @classmethod
    def parse(cls, raw, funding_debit):
        require(type(raw) is dict and raw.keys() == {"contract","canary","market","timeout_profile"}
                and raw["contract"] == STAGE_CONTRACT and raw["timeout_profile"] == TIMEOUT_PROFILE
                and raw["canary"] == {"count": 2, "weight": 2}
                and all(type(v) is int for v in raw["canary"].values()), "CANARY_SCOPE_INVALID")
        budget = raw["market"]
        if budget is None:
            return cls(None, None)
        require(type(budget) is dict and budget.keys() == {"count","weight"}
                and type(funding_debit) is int, "MARKET_STAGE_SCOPE_INVALID")
        count, known, funding = market_floor()
        require(bounded_int(budget["count"], count, BASE_MAX_REQUESTS-2)
                and bounded_int(budget["weight"], known+funding*funding_debit, BASE_MAX_WEIGHT-2),
                "MARKET_STAGE_BUDGET_INVALID")
        return cls(budget["count"], budget["weight"])

    def plan_totals(self):
        return 2+(self.market_count or 0), 2+(self.market_weight or 0)
