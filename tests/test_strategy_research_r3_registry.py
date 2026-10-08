"""Tests for R3 candidate registry, exact 8 IDs, and cost geometry eligibility."""

import pytest

from btc_quant_agent.strategy_research.r3_overnight.candidate_registry import (
    get_default_registry,
)
from btc_quant_agent.strategy_research.r3_overnight.constants import (
    CANDIDATE_IDS,
    EXPECTED_CANDIDATE_COUNT,
    STRESS_COST_GEOMETRY_INELIGIBLE,
)
from btc_quant_agent.strategy_research.r3_overnight.types import (
    CandidateFamily,
    CostScenario,
    Direction,
    Horizon,
)


def test_registry_contains_exact_eight_candidates():
    registry = get_default_registry()
    candidates = registry.list_candidates()
    assert len(candidates) == EXPECTED_CANDIDATE_COUNT == 8

    registered_ids = [c.id for c in candidates]
    assert registered_ids == list(CANDIDATE_IDS)


def test_registry_families_and_horizons():
    registry = get_default_registry()

    sc_long_4h = registry.get_candidate("STRUCTURAL_CONTINUATION_LONG_04H")
    assert sc_long_4h.family == CandidateFamily.STRUCTURAL_CONTINUATION
    assert sc_long_4h.direction == Direction.LONG
    assert sc_long_4h.horizon == Horizon.H4
    assert sc_long_4h.holding_minutes == 240

    sc_short_12h = registry.get_candidate("STRUCTURAL_CONTINUATION_SHORT_12H")
    assert sc_short_12h.family == CandidateFamily.STRUCTURAL_CONTINUATION
    assert sc_short_12h.direction == Direction.SHORT
    assert sc_short_12h.horizon == Horizon.H12
    assert sc_short_12h.holding_minutes == 720

    cr_long_12h = registry.get_candidate("CLOSED_RETEST_LONG_12H")
    assert cr_long_12h.family == CandidateFamily.CLOSED_RETEST
    assert cr_long_12h.direction == Direction.LONG
    assert cr_long_12h.horizon == Horizon.H12

    cr_short_4h = registry.get_candidate("CLOSED_RETEST_SHORT_04H")
    assert cr_short_4h.family == CandidateFamily.CLOSED_RETEST
    assert cr_short_4h.direction == Direction.SHORT
    assert cr_short_4h.horizon == Horizon.H4


def test_prohibit_ninth_candidate():
    registry = get_default_registry()
    with pytest.raises(KeyError, match="not registered"):
        registry.get_candidate("NON_EXISTENT_STRATEGY_9")


def test_stress_cost_geometry_ineligibility():
    """
    12h horizon under stress scenario requires stop >= 280bp vs max 250bp.
    Must be flagged STRESS_COST_GEOMETRY_INELIGIBLE.
    """
    registry = get_default_registry()

    # 4h variants are eligible under both base and stress
    elig_4h_base, reason = registry.check_geometry_eligibility("STRUCTURAL_CONTINUATION_LONG_04H", CostScenario.BASE)
    assert elig_4h_base is True and reason is None

    elig_4h_stress, reason = registry.check_geometry_eligibility("STRUCTURAL_CONTINUATION_LONG_04H", CostScenario.STRESS)
    assert elig_4h_stress is True and reason is None

    # 12h variants are eligible under BASE
    elig_12h_base, reason = registry.check_geometry_eligibility("STRUCTURAL_CONTINUATION_LONG_12H", CostScenario.BASE)
    assert elig_12h_base is True and reason is None

    # 12h variants are INELIGIBLE under STRESS
    elig_12h_stress, reason = registry.check_geometry_eligibility("STRUCTURAL_CONTINUATION_LONG_12H", CostScenario.STRESS)
    assert elig_12h_stress is False
    assert reason == STRESS_COST_GEOMETRY_INELIGIBLE

    # Check closed retest 12h under stress
    elig_cr_12h, reason = registry.check_geometry_eligibility("CLOSED_RETEST_SHORT_12H", CostScenario.STRESS)
    assert elig_cr_12h is False
    assert reason == STRESS_COST_GEOMETRY_INELIGIBLE
