"""Tests for ReplayEngine orchestrating isolated 8-candidate virtual books."""

from decimal import Decimal

from btc_quant_agent.strategy_research.r3_overnight.constants import (
    CANDIDATE_IDS,
    STRESS_COST_GEOMETRY_INELIGIBLE,
)
from btc_quant_agent.strategy_research.r3_overnight.replay_engine import (
    ReplayEngine,
)
from btc_quant_agent.strategy_research.r3_overnight.synthetic_fixtures import (
    generate_flat_1m_series,
    generate_flat_mark_series,
)
from btc_quant_agent.strategy_research.r3_overnight.types import CostScenario


def test_replay_engine_instantiation_and_isolation():
    engine_base = ReplayEngine(cost_scenario=CostScenario.BASE)
    assert len(engine_base.books) == 8
    assert len(engine_base.ineligible_candidates) == 0

    engine_stress = ReplayEngine(cost_scenario=CostScenario.STRESS)
    assert len(engine_stress.books) == 8
    # 4 of the 8 candidates are 12h variants and must be flagged STRESS_COST_GEOMETRY_INELIGIBLE
    assert len(engine_stress.ineligible_candidates) == 4
    for cid, reason in engine_stress.ineligible_candidates.items():
        assert "12H" in cid
        assert reason == STRESS_COST_GEOMETRY_INELIGIBLE


def test_replay_engine_deterministic_hash():
    engine1 = ReplayEngine(cost_scenario=CostScenario.BASE)
    engine2 = ReplayEngine(cost_scenario=CostScenario.BASE)

    hash1 = engine1.compute_deterministic_receipt_hash()
    hash2 = engine2.compute_deterministic_receipt_hash()
    assert hash1 == hash2
    assert len(hash1) == 64


def test_replay_engine_run_synthetic_flat():
    start_ms = 1_700_000_000_000 // 3_600_000 * 3_600_000
    bars = generate_flat_1m_series(start_ms, 120, Decimal("50000.00"))
    marks = generate_flat_mark_series(start_ms, 120, Decimal("50000.00"))

    engine = ReplayEngine(cost_scenario=CostScenario.BASE)
    results = engine.run_simulation(
        bars_1m={"BTCUSDT": bars},
        marks_1m={"BTCUSDT": marks},
    )

    assert len(results) == 8
    # All 8 books ran without crashing
    for cid in CANDIDATE_IDS:
        assert cid in results
        book = engine.books[cid]
        assert not book.killed
        assert book.cash == Decimal("1000.000000000000")
