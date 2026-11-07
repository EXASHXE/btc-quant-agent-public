from __future__ import annotations

import copy
import math

import pytest
from program_c.engine import ledger
from program_c.integrity import digest
from program_c.protocol import WEEK
from program_c.statistics import (
    bootstrap_interval,
    bounded_interval,
    cluster_episodes,
    ideal_no_edge_probability,
    kish_effective_clusters,
    matched_controls,
    power_plan,
    summarize,
)


@pytest.mark.parametrize("r,probability", [(2, 1/3), (3, 0.25), (4, 0.2)])
def test_correct_ideal_barrier_arithmetic(r, probability):
    assert ideal_no_edge_probability(r) == probability
    assert probability * r - (1-probability) == pytest.approx(0)


def test_same_path_null_retains_directions_censoring_and_no_extra_episodes(fixture_export):
    row = fixture_export("winning_unambiguous")["episodes"][0]
    result = matched_controls(row, [])
    controls = result["same_path_random_direction"]
    assert {c["outcome"] for c in controls} == {"TARGET_FIRST", "STOP_FIRST"}
    assert sum(c["weight"] for c in controls) == 1
    assert result["control_denominator"]["independent_additional_episodes"] == 0
    row = fixture_export("right_censoring")["episodes"][0]
    controls = matched_controls(row, [])["same_path_random_direction"]
    assert all(c["outcome"] == "RIGHT_CENSORED" for c in controls)


def test_fixed_seed_timing_never_selects_on_future_outcome(fixture_export):
    obj = fixture_export("winning_unambiguous")
    row, pool = obj["episodes"][0], obj["control_pool"]
    first = matched_controls(row, pool)["randomized_timing"]
    assert first["candidate_count"] == 2
    second = matched_controls(row, list(reversed(pool)))["randomized_timing"]
    assert first == second
    changed = copy.deepcopy(pool)
    changed[0]["path"][0]["high"] = 1000
    third = matched_controls(row, changed)["randomized_timing"]
    assert third["selected_episode_id"] == first["selected_episode_id"]
    assert first["future_outcomes_used_in_selection"] is False


def test_timing_strata_exclude_incompatible_regime(fixture_export):
    obj = fixture_export("winning_unambiguous")
    for row in obj["control_pool"]:
        row["regime"] = "TREND_DOWN"
    assert matched_controls(obj["episodes"][0], obj["control_pool"])["randomized_timing"]["candidate_count"] == 0


def test_correlated_symbols_count_one_cluster(protocol, fixture_export):
    obj = fixture_export("overlapping_multi_symbol_shock")
    mapping, clusters = cluster_episodes(obj["episodes"])
    assert len(mapping) == 3 and len(clusters) == 1
    summary = summarize(obj, ledger(obj, protocol), protocol)
    assert summary["denominators"]["eligible_setup_episodes"] == 3
    assert summary["denominators"]["independent_clusters_QA"] == 1
    assert summary["effective_sample_size"]["QA_episode_weighted_Kish_clusters"] == 1


def test_cross_week_overlaps_union_cluster(fixture_export):
    row = fixture_export("coverage_1D_5d")["episodes"][0]
    other = copy.deepcopy(row)
    other["episode_id"] = "other"
    other["trigger_close_ms"] += 2 * 24 * 3_600_000
    other["expiry_ms"] += 2 * 24 * 3_600_000
    assert len(cluster_episodes([row, other])[1]) == 1


def test_kish_does_not_inflate_clusters():
    assert kish_effective_clusters([1, 1, 1]) == 3
    assert 1 < kish_effective_clusters([1, 100]) < 2
    assert kish_effective_clusters([]) == 0


def test_insufficient_n_bootstrap_honest():
    assert bootstrap_interval([1])["interval"] is None
    assert bootstrap_interval([1])["status"] == "INSUFFICIENT_CLUSTERS"


def test_cluster_bootstrap_deterministic():
    values = list(range(40))
    assert bootstrap_interval(values) == bootstrap_interval(values)
    assert bootstrap_interval(values)["clusters"] == 40


def test_distribution_free_power_and_uncertainty_formulas(protocol):
    p = power_plan(protocol)
    n = p["required_independent_clusters_per_family_under_assumptions"]
    alpha = p["per_family_alpha"]
    width, delta = 12, p["practical_effect_R"]
    radius = width * math.sqrt(math.log(2/alpha)/(2*n))
    guaranteed_power = 1-math.exp(-2*n*(delta-radius)**2/width**2)
    assert guaranteed_power >= 0.8
    assert radius <= p["uncertainty_half_width_R"]
    assert n > 200
    assert p["minimum_independent_clusters_per_symbol_direction_cell"] == 50
    assert p["minimum_independent_utc_weeks"] == 40
    assert p["assumptions_currently_satisfied"] is False


def test_intervals_require_verified_bounds(protocol):
    assert bounded_interval([1]*50, protocol)["interval"] is None
    assert bounded_interval([100]*50, protocol, True)["interval"] is None
    assert bounded_interval([0.5]*50, protocol, True)["interval"][0] < 0.5


def test_synthetic_weeks_never_supply_native_support(protocol, fixture_export):
    obj = fixture_export("precise_time_stop")
    original = obj["episodes"][0]
    # Metadata-only QA clustering probe; no fabricated 40-week backtest claim.
    episodes = []
    for i in range(45):
        row = copy.deepcopy(original)
        row["trigger_close_ms"] += i * 2 * WEEK
        row["expiry_ms"] += i * 2 * WEEK
        row["episode_id"] = digest(["QA_METADATA_ONLY", i])
        episodes.append(row)
    obj["episodes"] = episodes
    summary = summarize(obj, ledger(obj, protocol), protocol)
    assert summary["denominators"]["independent_clusters_QA"] >= 40
    assert summary["effective_sample_size"]["native_economic"] == 0
    assert summary["independent_native_UTC_weeks"] == 0
    assert not any(summary["support_gates"].values())


def test_no_setup_denominator_is_preserved(protocol, fixture_export):
    obj = fixture_export("all_no_setup")
    summary = summarize(obj, [], protocol)
    assert summary["denominators"]["all_candidate_trigger_decisions"] == 3
    assert summary["denominators"]["NO_SETUP_decisions"] == 3
    assert summary["unknown_path_fraction"] is None
    assert summary["scientific_decision"] == "INSUFFICIENT_SUPPORT"
