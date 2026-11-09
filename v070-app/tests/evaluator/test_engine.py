from __future__ import annotations

import copy
import itertools

import pytest
from conftest import reseal
from make_fixtures import seal_fact
from program_c.engine import first_passage, geometry, ledger, scenario
from program_c.integrity import WORKSPACE
from program_c.protocol import HOUR
from program_c.statistics import summarize
from program_c.validation import validate


@pytest.mark.parametrize("name,outcome", [
    ("winning_unambiguous", "TARGET_FIRST"), ("stop_first", "STOP_FIRST"),
    ("precise_time_stop", "TIME_STOP"), ("unfilled_entry", "NO_FILL"),
    ("delayed_missed_entry", "MISSED_ENTRY"), ("both_hit_same_bar", "AMBIGUOUS_OHLC_ORDER_UNKNOWN"),
    ("entry_exit_order_ambiguous", "AMBIGUOUS_OHLC_ORDER_UNKNOWN"), ("missing_interval", "MISSING_COVERAGE"),
    ("right_censoring", "RIGHT_CENSORED"), ("insufficient_horizon", "INSUFFICIENT_FUTURE_HORIZON"),
    ("coverage_4H_24h", "TARGET_FIRST"), ("coverage_1D_5d", "TARGET_FIRST"),
    ("three_hours_cannot_prove_5d", "INSUFFICIENT_FUTURE_HORIZON"), ("unqualified_source", "SOURCE_UNQUALIFIED"),
    ("late_entry_full_horizon", "TIME_STOP"), ("late_entry_insufficient_horizon", "INSUFFICIENT_FUTURE_HORIZON"),
    ("review_inside_bar", "AMBIGUOUS_OHLC_ORDER_UNKNOWN"),
])
def test_exact_outcomes(protocol, fixture_export, name, outcome):
    obj = fixture_export(name)
    row = validate(reseal(obj), protocol)["episodes"][0]
    assert first_passage(row).outcome == outcome


@pytest.mark.parametrize("stop_hit,target_hit,entry_at_open", list(itertools.product([False, True], repeat=3)))
@pytest.mark.parametrize("target_r", [2, 3, 4])
def test_exhaustive_bounded_order_truth_table(protocol, fixture_export, stop_hit, target_hit, entry_at_open, target_r):
    obj = fixture_export("precise_time_stop")
    row = obj["episodes"][0]
    bar = row["path"][0]
    bar.update(open=100 if entry_at_open else 98, low=89 if stop_hit else 98,
               high=100 + target_r * 10 + 1 if target_hit else 101, close=100)
    seal_fact(bar)
    row = validate(reseal(obj), protocol)["episodes"][0]
    actual = first_passage(row, target_r).outcome
    if (stop_hit and target_hit) or (not entry_at_open and (stop_hit or target_hit)):
        assert actual == "AMBIGUOUS_OHLC_ORDER_UNKNOWN"
    elif stop_hit:
        assert actual == "STOP_FIRST"
    elif target_hit:
        assert actual == "TARGET_FIRST"
    else:
        assert actual == "TIME_STOP"


def test_early_target_does_not_replace_full_horizon(protocol, fixture_export):
    obj = fixture_export("winning_unambiguous")
    row = obj["episodes"][0]
    row["path"] = row["path"][:2]
    row["coverage_end_ms"] = row["path"][-1]["end_ms"]
    row = validate(reseal(obj), protocol)["episodes"][0]
    assert first_passage(row).outcome == "INSUFFICIENT_FUTURE_HORIZON"


def test_gap_after_early_target_blocks_complete_path(protocol, fixture_export):
    obj = fixture_export("winning_unambiguous")
    del obj["episodes"][0]["path"][3]
    row = validate(reseal(obj), protocol)["episodes"][0]
    assert first_passage(row).outcome == "MISSING_COVERAGE"


def test_precise_time_stop_and_original_risk(protocol, fixture_export):
    row = fixture_export("precise_time_stop")["episodes"][0]
    result = scenario(row, "FROZEN", "BASE", 0)
    assert result.original_risk_per_base == 10
    assert result.event_ms == row["reviewed_ms"] + 4 * HOUR
    assert result.modeled_path_after_cost_R is not None
    assert 0.45 < result.modeled_path_after_cost_R < 0.5
    assert result.realized_R is None and result.executable_R is None and result.actual_fill is False


def test_adverse_gap_not_fair_minus_one(fixture_export):
    result = scenario(fixture_export("adverse_jump_gap")["episodes"][0], "FROZEN", "BASE", 0)
    assert result.outcome == "STOP_FIRST"
    assert result.modeled_path_after_cost_R is None
    assert result.modeled_payoff_bounds_R == [None, -1.0]


@pytest.mark.parametrize("name", ["both_hit_same_bar", "entry_exit_order_ambiguous", "unfilled_entry",
                                   "delayed_missed_entry", "right_censoring", "cost_unknown"])
def test_uncertainty_never_imputed_as_zero_or_win(fixture_export, name):
    row = scenario(fixture_export(name)["episodes"][0], "FROZEN", "BASE", 0)
    assert row.modeled_path_after_cost_R is None
    assert row.executable_R is None and row.realized_R is None


def test_future_values_cannot_change_exante_decision(protocol, fixture_export):
    obj = fixture_export("winning_unambiguous")
    before = copy.deepcopy(obj["episodes"][0])
    bar = obj["episodes"][0]["path"][1]
    bar.update(high=101, low=89, close=100)
    seal_fact(bar)
    after = validate(reseal(obj), protocol)["episodes"][0]
    assert before["row_sha256"] != after["row_sha256"]
    assert before["decision_digest"] == after["decision_digest"]
    assert before["episode_id"] == after["episode_id"]
    assert geometry(before) == geometry(after)
    assert first_passage(before).outcome == "TARGET_FIRST"
    assert first_passage(after).outcome == "STOP_FIRST"


def test_short_geometry_and_path_symmetry(protocol, fixture_export):
    obj = fixture_export("winning_unambiguous")
    obj["control_pool"] = []
    row = obj["episodes"][0]
    row.update(direction="SHORT", regime="TREND_DOWN", entry_region=[100, 101], structural_stop=110,
               fixed_preobservable_target_zones=[70])
    for bar in row["source_facts"] + row["path"]:
        old = copy.deepcopy(bar)
        bar.update(open=200-old["open"], close=200-old["close"], high=200-old["low"], low=200-old["high"])
        seal_fact(bar)
    row = validate(reseal(obj), protocol)["episodes"][0]
    assert geometry(row) == (100, 110, 70, 10)
    assert first_passage(row).outcome == "TARGET_FIRST"


def test_scenario_alternatives_never_multiply_episode_support(protocol, fixture_export):
    obj = fixture_export("winning_unambiguous")
    rows = ledger(obj, protocol)
    summary = summarize(obj, rows, protocol)
    assert len(rows) == 4 * 6 * 3
    assert summary["denominators"]["eligible_setup_episodes"] == 1
    assert summary["denominators"]["all_candidate_trigger_decisions"] == 3
    assert summary["effective_sample_size"]["native_economic"] == 0
    assert summary["scientific_decision"] == "INSUFFICIENT_SUPPORT"


def test_frozen_b_does_not_inherit_producer_order_or_return(protocol):
    raw = (WORKSPACE / "inputs/B_episode_export.original.json").read_bytes()
    obj = validate(raw, protocol)
    row = scenario(obj["episodes"][0], "FROZEN", "BASE", 0)
    assert row.producer_outcome == "TARGET_FIRST"
    assert row.outcome == "MISSING_COVERAGE"
    assert row.planned_R == pytest.approx(3.7830137159375736)
    assert row.producer_projected_after_cost_R == pytest.approx(3.3189732255071767)
    assert row.modeled_path_after_cost_R is None


def test_entry_expiry_does_not_extend_fixed_holding_period(protocol, fixture_export):
    obj = fixture_export("precise_time_stop")
    row = obj["episodes"][0]
    row["expiry_ms"] = row["reviewed_ms"] + 12 * HOUR
    row = validate(reseal(obj), protocol)["episodes"][0]
    result = first_passage(row)
    assert result.outcome == "TIME_STOP"
    assert result.event_ms == row["reviewed_ms"] + 4 * HOUR


def test_invalidation_before_entry_cannot_be_reactivated(protocol, fixture_export):
    obj = fixture_export("precise_time_stop")
    row = obj["episodes"][0]
    row["path"][0].update(open=98, high=98.5, low=89, close=98)
    seal_fact(row["path"][0])
    row = validate(reseal(obj), protocol)["episodes"][0]
    assert first_passage(row).outcome == "MISSED_ENTRY"


def test_horizon_boundary_cannot_use_later_ohlc_extreme(protocol, fixture_export):
    obj = fixture_export("coverage_4H_24h")
    obj["episodes"][0]["holding_horizon_hours"] = 5
    row = validate(reseal(obj), protocol)["episodes"][0]
    assert first_passage(row).outcome == "MISSING_COVERAGE"


def test_entry_at_expiry_is_not_eligible(protocol, fixture_export):
    obj = fixture_export("precise_time_stop")
    row = obj["episodes"][0]
    for bar in row["path"][:2]:
        bar.update(open=98, high=98.5, low=97, close=98)
        seal_fact(bar)
    row = validate(reseal(obj), protocol)["episodes"][0]
    assert first_passage(row).outcome == "NO_FILL"
