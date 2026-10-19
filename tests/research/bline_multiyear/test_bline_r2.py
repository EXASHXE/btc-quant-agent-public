"""Focused regression and validation tests for V065-BLINE-R2-SAMPLE-EXPANSION."""
from __future__ import annotations

import json
import math

from scripts.research.bline_multiyear import contracts_r2 as r2_contracts
from scripts.research.bline_multiyear.coverage_extension import (
    FROZEN_R1_ROOT,
    EventClusterer,
    OIDiagnosticEngine,
    compute_before_after_btc,
)


def test_r1_artifacts_immutability() -> None:
    """Verify frozen R1 completion artifacts remain immutable and unchanged."""
    receipt_path = FROZEN_R1_ROOT / "completion-final" / "COMPLETION_RECEIPT.json"
    prereg_path = FROZEN_R1_ROOT / "preregister" / "preregistered_candidates.json"
    matrix_path = FROZEN_R1_ROOT / "features-release" / "feature_coverage_matrix.json"

    assert receipt_path.exists(), "R1 completion receipt missing"
    assert prereg_path.exists(), "R1 preregistration missing"
    assert matrix_path.exists(), "R1 coverage matrix missing"

    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    assert prereg["task"] == "V065-BLINE-R1"
    assert prereg["schema"] == "bline-r1.preregistration.v1"

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["terminal"] == "BLINE_R1_RESEARCH_PIPELINE_READY"
    assert "artifacts_sha256" in receipt


def test_event_episode_clustering_synthetic() -> None:
    """Test EventClusterer with known sequential timestamps."""
    base_t = 1700000000
    # Cluster 1: 3 consecutive hours (t, t+1h, t+2h)
    # Gap of 10 hours
    # Cluster 2: 2 triggers (t+12h, t+15h within 8h of t+12h)
    triggers = [
        {"t": base_t, "name": "trig1"},
        {"t": base_t + 3600, "name": "trig2"},
        {"t": base_t + 7200, "name": "trig3"},
        {"t": base_t + 12 * 3600, "name": "trig4"},
        {"t": base_t + 15 * 3600, "name": "trig5"},
    ]

    episodes_8h = EventClusterer.cluster(triggers, horizon_hours=8)
    assert len(episodes_8h) == 2
    assert episodes_8h[0].trigger_count == 3
    assert episodes_8h[1].trigger_count == 2

    metrics = EventClusterer.metrics(triggers, horizon_hours=8)
    assert metrics["total_trigger_hours"] == 5
    assert metrics["independent_episodes_count"] == 2
    assert metrics["max_cluster_size"] == 3
    assert metrics["mean_cluster_size"] == 2.5
    assert metrics["meets_minimum_acted_origins"] is False


def test_oi_episode_clustering_exact_r1_triggers() -> None:
    """Test the exact 4 R1 OI triggers collapse into 2 independent episodes."""
    # The 4 exact triggers from R1
    triggers = [
        {"t": 1780506060, "time": "2026-06-03T17:01:00Z"},
        {"t": 1780509660, "time": "2026-06-03T18:01:00Z"},
        {"t": 1780513260, "time": "2026-06-03T19:01:00Z"},
        {"t": 1787317260, "time": "2026-08-21T13:01:00Z"},
    ]

    # For all standard horizons (4h, 8h, 12h, 24h), the first 3 triggers collapse to 1 episode
    for h in (4, 8, 12, 24):
        eps = EventClusterer.cluster(triggers, horizon_hours=h)
        assert len(eps) == 2, f"Failed for horizon {h}h"
        assert eps[0].trigger_count == 3
        assert eps[1].trigger_count == 1

    metrics_8h = EventClusterer.metrics(triggers, horizon_hours=8)
    assert metrics_8h["independent_episodes_count"] == 2
    assert metrics_8h["weekly_blocks_count"] == 2
    assert metrics_8h["meets_minimum_acted_origins"] is False
    assert metrics_8h["meets_minimum_weekly_blocks"] is False
    assert metrics_8h["frozen_minimum_passed"] is False
    assert metrics_8h["decision"] == "INCONCLUSIVE_SUPPORT"


def test_oi_sample_missingness_diagnostics() -> None:
    """Verify OIDiagnosticEngine correctly identifies failure stages."""
    # 1. Missing X baseline
    r_no_x = {"t": 1780000000, "x_complete": False, "x_reason": "INCOMPLETE_24H_MINUTE_X"}
    diag1 = OIDiagnosticEngine.diagnose_origin(r_no_x)
    assert diag1["stage"] == "PRICE_BASELINE_INCOMPLETE"
    assert diag1["eligible"] is False

    # 2. Missing OI sample
    r_no_z = {"t": 1780000000, "x_complete": True, "x": [0.0] * 10, "z_status": "UNAVAILABLE", "z_reason": "MISSING_Z"}
    diag2 = OIDiagnosticEngine.diagnose_origin(r_no_z)
    assert diag2["stage"] == "OI_SAMPLE_UNAVAILABLE"
    assert diag2["detail"] == "MISSING_Z"

    # 3. Z observed, but no price drop (return_4h > -0.01)
    r_no_drop = {
        "t": 1780000000, "x_complete": True, "x": [0.0, 0.005, 0.0],
        "z_status": "OBSERVED", "z": [-0.03, math.log(1.8)],
    }
    diag3 = OIDiagnosticEngine.diagnose_origin(r_no_drop)
    assert diag3["stage"] == "X_BASELINE_NOT_MET"
    assert diag3["eligible"] is True
    assert diag3["triggered"] is False

    # 4. Z observed, price drop met, but no OI contraction
    r_no_oi = {
        "t": 1780000000, "x_complete": True, "x": [0.0, -0.015, 0.0],
        "z_status": "OBSERVED", "z": [0.01, math.log(1.8)],
    }
    diag4 = OIDiagnosticEngine.diagnose_origin(r_no_oi)
    assert diag4["stage"] == "OI_CONTRACTION_NOT_MET"
    assert diag4["triggered"] is False

    # 5. Full trigger
    r_trig = {
        "t": 1780000000, "x_complete": True, "x": [0.0, -0.015, 0.0],
        "z_status": "OBSERVED", "z": [-0.03, math.log(1.8)],
    }
    diag5 = OIDiagnosticEngine.diagnose_origin(r_trig)
    assert diag5["stage"] == "TRIGGERED"
    assert diag5["triggered"] is True


def test_funding_2022_economic_zero_vs_2026_unavailable() -> None:
    """Verify 2022 bear market zero is economic non-trigger while 2026 is unobserved field."""
    # Synthetic origin representing 2022 bear market (backwardation: negative premium & basis)
    r_2022 = {
        "t": 1650000000,  # 2022
        "x_complete": True,
        "x": [0.0, 0.015, 0.0],  # 1.5% rally occurs
        "derivatives": {
            "premium_prior4h": -0.0002,  # discount! fails >= +0.0005
            "basis_prior4h": -0.0001,    # discount! fails >= +0.0003
            "premium_change": -0.0003,
            "basis_change": -0.0003,
            "funding_rate": 0.00005,     # fails >= +0.0001
        },
    }
    # Evaluates to NO trigger, even though derivatives are 100% available
    base, sig, paired = r2_contracts.signals_r2(r_2022, "FUNDING_PREMIUM_RELEASE")
    assert paired is True, "Data must be paired eligible"
    assert base == -1, "Baseline rally was met"
    assert sig == 0, "Candidate condition must NOT trigger during persistent discount"

    # Synthetic origin representing 2026 in R1 (unobserved premium_index table)
    r_2026_r1 = {
        "t": 1780000000,  # 2026
        "x_complete": True,
        "x": [0.0, 0.015, 0.0],
        "derivatives": None,  # unobserved
    }
    base26, sig26, paired26 = r2_contracts.signals_r2(r_2026_r1, "FUNDING_PREMIUM_RELEASE")
    assert paired26 is False, "Must not be paired eligible when derivatives is None"
    assert base26 == 0 and sig26 == 0


def test_bybit_population_isolation() -> None:
    """Verify Bybit population is kept separate with 0 admitted sources."""
    reg = r2_contracts.registration_r2()
    assert "bybit" in reg["common"]["populations"]
    bybit = reg["common"]["populations"]["bybit"]
    assert bybit["role"] == "EXTERNAL_COMPARISON_POPULATION"
    assert bybit["status"] == "SOURCES_UNAVAILABLE_NOT_ADMITTED"

    # Testing signal on bybit row returns zero
    row_bybit = {
        "venue": "bybit",
        "asset": "BTC",
        "t": 1780000000,
        "x_complete": True,
        "x": [0.0, -0.02, 0.0],
        "z_status": "OBSERVED",
        "z": [-0.03, math.log(2.0)],
    }
    assert r2_contracts.signals_r2(row_bybit, "OI_DELEVERAGING_CONTINUATION") == (0, 0, False)


def test_r2_prospective_registration_schema() -> None:
    """Verify R2 registration conforms to schema and preserves frozen candidate thresholds."""
    reg = r2_contracts.registration_r2()
    assert reg["task"] == "V065-BLINE-R2-SAMPLE-EXPANSION"
    assert reg["schema"] == "bline-r2.preregistration.v1"
    assert reg["state"] == "PREREGISTERED_PROSPECTIVE_SAMPLE_EXPANSION"

    candidates = {c["id"]: c for c in reg["candidates"]}
    assert "FUNDING_PREMIUM_RELEASE" in candidates
    assert "OI_DELEVERAGING_CONTINUATION" in candidates

    # Threshold checks - must be exact frozen reproduction
    assert "log_return_4h >= 0.01" in candidates["FUNDING_PREMIUM_RELEASE"]["X_baseline"]
    assert "prior4h mark-index >=0.0005" in candidates["FUNDING_PREMIUM_RELEASE"]["X_plus_Z"]
    assert "prior4h cash basis >=0.0003" in candidates["FUNDING_PREMIUM_RELEASE"]["X_plus_Z"]
    assert "premium_change<=-0.0002" in candidates["FUNDING_PREMIUM_RELEASE"]["X_plus_Z"]
    assert "basis_change<=-0.0002" in candidates["FUNDING_PREMIUM_RELEASE"]["X_plus_Z"]
    assert "last_settled_funding>=0.0001" in candidates["FUNDING_PREMIUM_RELEASE"]["X_plus_Z"]

    assert "log_return_4h <= -0.01" in candidates["OI_DELEVERAGING_CONTINUATION"]["X_baseline"]
    assert "log_OI_4h<=-0.02" in candidates["OI_DELEVERAGING_CONTINUATION"]["X_plus_Z"]
    assert "log_top_position_LS>=log(1.5)" in candidates["OI_DELEVERAGING_CONTINUATION"]["X_plus_Z"]


def test_before_after_btc_delta_values() -> None:
    """Verify before/after delta accounting."""
    comparison = compute_before_after_btc()
    before = comparison["before_r1"]
    after = comparison["after_r2"]
    delta = comparison["delta"]

    # Before counts
    assert before["scheduled_origins"] == 40896
    assert before["x_eligible"] == 40846
    assert before["funding_triggers"] == 168
    assert before["oi_triggers"] == 4

    # Extension delta (September 2026 adds 720 hours)
    assert delta["scheduled_origins_delta"] == 720
    assert delta["x_eligible_delta"] == 720
    assert delta["oi_z_eligible_delta"] == 720
    assert delta["oi_triggers_delta"] == 6

    # After totals
    assert after["scheduled_origins"] == 41616
    assert after["x_eligible"] == 41566
    assert after["oi_z_eligible"] == 4387
    assert after["oi_triggers"] == 10
    assert after["oi_independent_episodes_8h"] == 4
    assert after["oi_weekly_blocks"] == 4
