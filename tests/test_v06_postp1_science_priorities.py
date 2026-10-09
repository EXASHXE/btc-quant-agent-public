"""Verify ranking boundaries without certifying a strategy or external engine."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts/strategy_research/postp1_science_algebra"
SPEC = importlib.util.spec_from_file_location("postp1_priorities", SCRIPTS / "priorities.py")
assert SPEC and SPEC.loader
PRIORITIES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRIORITIES)
RUBRIC = json.loads((SCRIPTS / "priority_rubric.json").read_text())
INPUTS = json.loads((SCRIPTS / "priority_inputs.json").read_text())


def test_all_metadata_states_stay_blocked():
    result = PRIORITIES.evaluate(RUBRIC, INPUTS)
    assert result["actual_source_admission_count"] == 0
    for ranking in result["base_rankings"]:
        assert len(ranking["ranked"]) == 11
        assert all(not r["eligible_for_execution"] for r in ranking["ranked"])


def test_mirrored_sides_are_tied_not_directional_recommendation():
    rows = PRIORITIES.rank(INPUTS["rows"], RUBRIC, "STRESS_FROZEN_PROXY", "UNKNOWN")
    long = next(r for r in rows if r["id"] == "STRUCTURAL_CONTINUATION_LONG_04H")
    short = next(r for r in rows if r["id"] == "STRUCTURAL_CONTINUATION_SHORT_04H")
    assert long["weighted_score"] == short["weighted_score"] == 63.75
    assert long["tied_rank"] == short["tied_rank"] == 1


def test_missing_falsifiability_dimension_can_change_priority():
    result = PRIORITIES.evaluate(RUBRIC, INPUTS)
    assert result["ranking_instability_count"] > 0
    assert any("PROPOSED_FAILED_BREAKOUT_REVERSAL_SHORT_04H" in r["entering_top4"]
               for r in result["leave_one_dimension_out"])


def test_full_universe_missingness_penalty_is_explicit():
    a = PRIORITIES.rank(INPUTS["rows"], RUBRIC, "BASE_FROZEN_PROXY", "UNKNOWN")
    b = PRIORITIES.rank(INPUTS["rows"], RUBRIC, "BASE_FROZEN_PROXY", "MULTIASSET_INCOMPLETE")
    scores = {r["id"]: r["weighted_score"] for r in a}
    for r in b:
        if r["id"].startswith(("STRUCTURAL_", "CLOSED_")):
            assert scores[r["id"]]-r["weighted_score"] == 3.75


def test_priorities_deterministic_and_budget_preserved():
    assert PRIORITIES.evaluate(RUBRIC, INPUTS) == PRIORITIES.evaluate(RUBRIC, INPUTS)
    assert sum(r["kind"] == "ORIGINAL_EIGHT_UNCHANGED" for r in INPUTS["rows"]) == 8
    assert sum(r["kind"] == "PROPOSED_ONLY_NOT_FROZEN" for r in INPUTS["rows"]) == 3
