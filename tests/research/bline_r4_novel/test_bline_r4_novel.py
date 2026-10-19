"""Synthetic invariant and integration tests for B-line R4 novel mechanism selection."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from scripts.research.bline_multiyear.coverage_extension import EventClusterer
from scripts.research.bline_r4_novel.adapter import (
    DAY_US,
    HOUR_US,
    MINUTE_US,
    US,
    evaluate_origin_feature,
    is_protected_epoch,
)
from scripts.research.bline_r4_novel.contracts import (
    freeze_registration,
    prior_failure_matrix,
    registration_contract,
    scientific_novelty_gate_preflight,
)


def test_prior_failure_matrix_loaded() -> None:
    """Invariant: prior failure matrix references exact quotes in validation register."""
    matrix = prior_failure_matrix()
    assert "ledger_sha256" in matrix
    assert len(matrix["verified_failures"]) >= 13
    family_ids = [f["family_id"] for f in matrix["verified_failures"]]
    assert "flow_spread_H33_H34" in family_ids
    assert "PA_B_T6" in family_ids
    assert "funding_mark_R3" in family_ids
    assert "R8_novelty_stop" in family_ids


def test_scientific_novelty_gate_preflight() -> None:
    """Invariant: precondition gate evaluates <= 2 hypotheses and selects exactly 1."""
    preflight = scientific_novelty_gate_preflight()
    assert preflight["status"] == "PREFLIGHT_PASS_EXACTLY_ONE_CANDIDATE"
    assert len(preflight["hypotheses_evaluated"]) == 2
    assert preflight["candidate_count"] == 1

    h1 = preflight["hypotheses_evaluated"][0]
    assert h1["hypothesis_id"] == "HYPOTHESIS_1_STATE_IMPACT_ASYMMETRY"
    assert h1["preflight_verdict"] == "REJECTED_SOURCE_INSUFFICIENT_AND_COLLINEAR"
    assert not h1["selected_for_registration"]

    h2 = preflight["hypotheses_evaluated"][1]
    assert h2["hypothesis_id"] == "HYPOTHESIS_2_TRAPPED_LEVERAGE_OVERHANG"
    assert h2["preflight_verdict"] == "ACCEPTED_NOVEL_AND_SOURCE_COMPATIBLE"
    assert h2["selected_for_registration"]


def test_immutable_registration_freeze(tmp_path: Path) -> None:
    """Invariant: registration is frozen deterministically with 0 parameter search budget."""
    input_binding = {
        "task": "TEST",
        "mock_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    }
    reg = registration_contract(input_binding)
    assert reg["parameter_search_budget"] == 0
    assert reg["threshold_search_budget"] == 0
    assert reg["mechanism"]["id"] == "TRAPPED_LEVERAGE_OVERHANG_BREAKOUT"

    digest1 = freeze_registration(tmp_path, reg)
    assert (tmp_path / "exploratory_registration.v1.json").exists()
    assert (tmp_path / "registration_freeze_receipt.json").exists()

    # Re-freezing identical content is idempotent
    digest2 = freeze_registration(tmp_path, reg)
    assert digest1 == digest2

    # Attempting to freeze conflicting content raises ValueError
    reg_tampered = dict(reg)
    reg_tampered["parameter_search_budget"] = 99
    with pytest.raises(ValueError, match="REGISTRATION_ALREADY_FROZEN"):
        freeze_registration(tmp_path, reg_tampered)


def test_causality_and_interval_boundaries() -> None:
    """Invariant: all bar intervals and metrics records strictly precede decision cutoff."""
    t_origin = 1640995260  # 2022-01-01 00:01:00 UTC (origin)
    cutoff = t_origin - 60  # 2022-01-01 00:00:00 UTC (cutoff)
    cutoff_us = cutoff * US

    expected_native_label_us = cutoff_us - 10 * MINUTE_US  # 23:50:00 UTC
    content_upper_us = expected_native_label_us + 5 * MINUTE_US  # 23:55:00 UTC
    pred_24h_us = expected_native_label_us - DAY_US
    pred_4h_us = expected_native_label_us - 4 * HOUR_US

    assert content_upper_us < cutoff_us
    assert cutoff_us < t_origin * US

    oi_map = {
        expected_native_label_us: 100000.0,
        pred_24h_us: 95000.0,
        pred_4h_us: 99000.0,
    }
    sha_map = {expected_native_label_us: "mock_sha"}
    x_info = {
        "x_eligible": True,
        "log_return_4h": -0.015,
        "x_end_us": cutoff_us - MINUTE_US,
    }

    res = evaluate_origin_feature(
        t_origin, x_info, oi_map, sha_map, registration_sha="test_reg"
    )
    assert res["cutoff"] == cutoff
    assert res["content_upper_us"] < cutoff_us
    assert res["x_eligible"]
    assert res["z_eligible"]
    assert res["paired_xz_eligible"]
    assert res["x_condition"]
    assert res["z_condition"]
    assert res["trigger"]
    assert res["action"] == "SHORT"
    assert res["paired_baseline_action"] == "SHORT"
    assert res["no_action_reasons"] == []


def test_missing_source_explicit_no_action() -> None:
    """Invariant: missing current OI or predecessor yields explicit NO_ACTION and logs reason."""
    t_origin = 1640995260
    cutoff = t_origin - 60
    cutoff_us = cutoff * US
    expected_us = cutoff_us - 10 * MINUTE_US
    pred_24h_us = expected_us - DAY_US
    pred_4h_us = expected_us - 4 * HOUR_US

    x_info = {"x_eligible": True, "log_return_4h": -0.02}

    # Case 1: current OI missing
    oi_map_no_cur = {pred_24h_us: 95000.0, pred_4h_us: 99000.0}
    res1 = evaluate_origin_feature(t_origin, x_info, oi_map_no_cur, {}, "reg")
    assert not res1["z_eligible"]
    assert not res1["paired_xz_eligible"]
    assert not res1["trigger"]
    assert res1["action"] == "NO_ACTION"
    assert res1["paired_baseline_action"] == "NO_ACTION"
    assert "NATIVE_BASE_OI_MISSING_AT_CUTOFF_GUARD" in res1["no_action_reasons"]

    # Case 2: 24h predecessor missing
    oi_map_no_pred24 = {expected_us: 100000.0, pred_4h_us: 99000.0}
    res2 = evaluate_origin_feature(t_origin, x_info, oi_map_no_pred24, {}, "reg")
    assert not res2["z_eligible"]
    assert "PREDECESSOR_24H_BASE_OI_MISSING" in res2["no_action_reasons"]
    assert res2["action"] == "NO_ACTION"

    # Case 3: 4h predecessor missing
    oi_map_no_pred4 = {expected_us: 100000.0, pred_24h_us: 95000.0}
    res3 = evaluate_origin_feature(t_origin, x_info, oi_map_no_pred4, {}, "reg")
    assert not res3["z_eligible"]
    assert "PREDECESSOR_4H_BASE_OI_MISSING" in res3["no_action_reasons"]
    assert res3["action"] == "NO_ACTION"

    # Case 4: X missing
    oi_full = {expected_us: 100000.0, pred_24h_us: 95000.0, pred_4h_us: 99000.0}
    res4 = evaluate_origin_feature(t_origin, None, oi_full, {}, "reg")
    assert not res4["x_eligible"]
    assert not res4["paired_xz_eligible"]
    assert res4["action"] == "NO_ACTION"
    assert "X_MISSING_ORIGIN" in res4["no_action_reasons"]


def test_no_protected_dates_or_holdout_access() -> None:
    """Invariant: protected H40/H39 origins expose no values and return NO_ACTION."""
    t_h40 = int(datetime.fromisoformat("2025-06-01T01:00:00Z").timestamp())
    assert is_protected_epoch(t_h40)

    oi_full = {
        (t_h40 - 60 - 600) * US: 100000.0,
        (t_h40 - 60 - 600) * US - DAY_US: 90000.0,
        (t_h40 - 60 - 600) * US - 4 * HOUR_US: 95000.0,
    }
    x_mock = {"x_eligible": True, "log_return_4h": -0.03}
    res = evaluate_origin_feature(t_h40, x_mock, oi_full, {}, "reg")
    assert not res["x_eligible"]
    assert not res["z_eligible"]
    assert not res["paired_xz_eligible"]
    assert res["base_open_interest"] is None
    assert res["action"] == "NO_ACTION"
    assert "PROTECTED_HOLDOUT_WINDOW" in res["no_action_reasons"]


def test_zero_fills_zero_returns_zero_real_labels() -> None:
    """Invariant: feature adapter contains no fill prices, returns, or forward labels."""
    t = 1640995260
    cutoff = t - 60
    cutoff_us = cutoff * US
    expected_us = cutoff_us - 10 * MINUTE_US
    oi_map = {
        expected_us: 100000.0,
        expected_us - DAY_US: 95000.0,
        expected_us - 4 * HOUR_US: 99000.0,
    }
    x_info = {"x_eligible": True, "log_return_4h": -0.015}

    res = evaluate_origin_feature(t, x_info, oi_map, {}, "reg")

    forbidden_fields = [
        "fill_price",
        "realized_pnl",
        "net_return",
        "forward_return",
        "outcome",
        "slippage",
        "execution_cost",
    ]
    for field in forbidden_fields:
        assert field not in res


def test_episode_clustering_and_density() -> None:
    """Invariant: EventClusterer groups triggers within horizon window into non-overlapping episodes."""
    base_t = 1640995260  # T0
    # Create triggers at T0, T0 + 1h, T0 + 2h (should be 1 episode for 8h)
    # Then a trigger at T0 + 8h (should start a 2nd episode)
    triggers = [
        {"t": base_t, "name": "trig_0"},
        {"t": base_t + 3600, "name": "trig_1"},
        {"t": base_t + 7200, "name": "trig_2"},
        {"t": base_t + 8 * 3600, "name": "trig_3"},
    ]

    episodes_8h = EventClusterer.cluster(triggers, horizon_hours=8)
    assert len(episodes_8h) == 2
    assert episodes_8h[0].trigger_count == 3
    assert episodes_8h[0].start_t == base_t
    assert episodes_8h[0].end_t == base_t + 8 * 3600
    assert episodes_8h[1].trigger_count == 1
    assert episodes_8h[1].start_t == base_t + 8 * 3600

    # For 4h horizon:
    # trig_0, trig_1, trig_2 are in [T0, T0+4h) -> Episode 1
    # trig_3 is at T0 + 8h -> Episode 2
    episodes_4h = EventClusterer.cluster(triggers, horizon_hours=4)
    assert len(episodes_4h) == 2

    # For 24h horizon:
    # All 4 triggers fall in [T0, T0+24h) -> Episode 1
    episodes_24h = EventClusterer.cluster(triggers, horizon_hours=24)
    assert len(episodes_24h) == 1
    assert episodes_24h[0].trigger_count == 4


def test_paired_evaluation_symmetry() -> None:
    """Invariant: missing Z masks paired baseline X; both arms evaluated on identical origins."""
    t = 1640995260
    # X condition is met (return <= -1%)
    x_info = {"x_eligible": True, "log_return_4h": -0.02}

    # When Z is missing:
    res_no_z = evaluate_origin_feature(t, x_info, {}, {}, "reg")
    assert res_no_z["x_condition"]
    assert not res_no_z["z_eligible"]
    assert not res_no_z["paired_xz_eligible"]
    assert res_no_z["paired_baseline_action"] == "NO_ACTION"
    assert res_no_z["action"] == "NO_ACTION"

    # When Z is present:
    cutoff_us = (t - 60) * US
    expected_us = cutoff_us - 10 * MINUTE_US
    oi_map = {
        expected_us: 100000.0,
        expected_us - DAY_US: 95000.0,
        expected_us - 4 * HOUR_US: 99000.0,
    }
    res_with_z = evaluate_origin_feature(t, x_info, oi_map, {}, "reg")
    assert res_with_z["paired_xz_eligible"]
    assert res_with_z["paired_baseline_action"] == "SHORT"
    assert res_with_z["action"] == "SHORT"
