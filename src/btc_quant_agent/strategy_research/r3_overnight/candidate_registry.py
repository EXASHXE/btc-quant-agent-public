"""Candidate registry defining the exact 8 R3 overnight discovery strategies."""


from btc_quant_agent.strategy_research.r3_overnight.constants import (
    CANDIDATE_IDS,
    EXPECTED_CANDIDATE_COUNT,
    STRESS_COST_GEOMETRY_INELIGIBLE,
    SUPPORTED_SYMBOLS,
)
from btc_quant_agent.strategy_research.r3_overnight.types import (
    CandidateDefinition,
    CandidateFamily,
    CostScenario,
    Direction,
    Horizon,
)

_RAW_CANDIDATES = [
    CandidateDefinition(
        id="STRUCTURAL_CONTINUATION_LONG_04H",
        family=CandidateFamily.STRUCTURAL_CONTINUATION,
        direction=Direction.LONG,
        horizon=Horizon.H4,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="STRUCTURAL_CONTINUATION_LONG_12H",
        family=CandidateFamily.STRUCTURAL_CONTINUATION,
        direction=Direction.LONG,
        horizon=Horizon.H12,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="STRUCTURAL_CONTINUATION_SHORT_04H",
        family=CandidateFamily.STRUCTURAL_CONTINUATION,
        direction=Direction.SHORT,
        horizon=Horizon.H4,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="STRUCTURAL_CONTINUATION_SHORT_12H",
        family=CandidateFamily.STRUCTURAL_CONTINUATION,
        direction=Direction.SHORT,
        horizon=Horizon.H12,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="CLOSED_RETEST_LONG_04H",
        family=CandidateFamily.CLOSED_RETEST,
        direction=Direction.LONG,
        horizon=Horizon.H4,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="CLOSED_RETEST_LONG_12H",
        family=CandidateFamily.CLOSED_RETEST,
        direction=Direction.LONG,
        horizon=Horizon.H12,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="CLOSED_RETEST_SHORT_04H",
        family=CandidateFamily.CLOSED_RETEST,
        direction=Direction.SHORT,
        horizon=Horizon.H4,
        symbols=SUPPORTED_SYMBOLS,
    ),
    CandidateDefinition(
        id="CLOSED_RETEST_SHORT_12H",
        family=CandidateFamily.CLOSED_RETEST,
        direction=Direction.SHORT,
        horizon=Horizon.H12,
        symbols=SUPPORTED_SYMBOLS,
    ),
]


class CandidateRegistry:
    """Registry maintaining the exact 8 pre-registered candidate specifications."""

    def __init__(self) -> None:
        self._candidates: dict[str, CandidateDefinition] = {
            c.id: c for c in _RAW_CANDIDATES
        }
        if len(self._candidates) != EXPECTED_CANDIDATE_COUNT:
            raise ValueError(
                f"Candidate registry must contain exactly {EXPECTED_CANDIDATE_COUNT} candidates, "
                f"found {len(self._candidates)}"
            )

    def get_candidate(self, candidate_id: str) -> CandidateDefinition:
        if candidate_id not in self._candidates:
            raise KeyError(f"Candidate ID '{candidate_id}' not registered in frozen 8-candidate set")
        return self._candidates[candidate_id]

    def list_candidates(self) -> list[CandidateDefinition]:
        return [self._candidates[cid] for cid in CANDIDATE_IDS]

    def check_geometry_eligibility(
        self, candidate_id: str, cost_scenario: CostScenario
    ) -> tuple[bool, str | None]:
        """
        Check theoretical cost geometry eligibility.
        
        Under stress scenario:
        12h horizon across 12 hourly funding windows at 8bp stress = 96bp adverse funding.
        Round trip transaction stress = 44bp.
        Total adverse cost hurdle = 140bp.
        With target = 2R, minimum stop distance required for non-negative payoff space is >= 2 * 140bp = 280bp.
        However, the maximum allowed initial stop distance is 250bp (2.5%).
        Since 280bp > 250bp, 12h stress variants cannot satisfy the pre-registered geometry.
        This must be reported as STRESS_COST_GEOMETRY_INELIGIBLE, NOT as a losing empirical return.
        """
        candidate = self.get_candidate(candidate_id)
        if cost_scenario == CostScenario.STRESS and candidate.horizon == Horizon.H12:
            return False, STRESS_COST_GEOMETRY_INELIGIBLE
        return True, None


def get_default_registry() -> CandidateRegistry:
    return CandidateRegistry()
