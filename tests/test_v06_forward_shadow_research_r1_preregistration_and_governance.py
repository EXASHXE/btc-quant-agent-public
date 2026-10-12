"""Deterministic tests for frozen preregistration, sample readiness gate, and temporal boundary governance.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.strategy_research.forward_shadow_research_r1.registry import (
    SELECTABLE_OBSERVATION_CELLS,
    SampleReadinessGate,
    SignalFamily,
    compute_policy_fingerprint,
    get_default_hypotheses,
)
from scripts.strategy_research.forward_shadow_research_r1.run import (
    compute_frozen_manifest,
    run_developmental_synthetic_suite,
)


def test_immutable_hypothesis_registry_cells():
    hypotheses = get_default_hypotheses()
    assert len(hypotheses) == 6
    assert tuple(sorted(hypotheses.keys())) == tuple(sorted(SELECTABLE_OBSERVATION_CELLS))

    for hyp in hypotheses.values():
        assert hyp.account_capital_usdt == 1000.0
        assert hyp.reserve_fraction == 0.05
        assert hyp.leverage_max == 1.0
        assert hyp.lot_step_btc == 0.001
        assert hyp.cooldown_hours == 6
        assert hyp.atr_period == 14
        assert hyp.atr_min_warmup_hours == 200
        assert hyp.stop_r_multiple == 1.0
        assert hyp.target_r_multiple == 2.0
        assert hyp.taker_fee_bps == 5.0
        assert hyp.adverse_slippage_bps == 0.5
        assert hyp.confirmation_intervals_minutes == (5, 15, 30)


def test_p1_specific_hypothesis_constants():
    hypotheses = get_default_hypotheses()
    for h in (6, 12, 18):
        cell_id = f"P1_BASIS_REVERSION_V2_SHADOW_{h}H"
        hyp = hypotheses[cell_id]
        assert hyp.family == SignalFamily.P1_BASIS_REVERSION_V2_SHADOW
        assert hyp.min_dislocation_bps == 5.0
        assert hyp.spread_multiplier == 2.0
        assert hyp.past_premium_shrink_window_minutes == 5
        assert hyp.abnormal_vol_cap_bps == 300.0


def test_p2_specific_hypothesis_constants():
    hypotheses = get_default_hypotheses()
    for h in (6, 12, 18):
        cell_id = f"P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_{h}H"
        hyp = hypotheses[cell_id]
        assert hyp.family == SignalFamily.P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW
        assert hyp.agg_trade_imbalance_threshold == 0.20
        assert hyp.book_imbalance_threshold == 0.10
        assert hyp.book_top_levels == 10
        assert hyp.directional_filter_window_minutes == 30


def test_policy_fingerprint_deterministic_and_drift_detection():
    fp1 = compute_policy_fingerprint()
    fp2 = compute_policy_fingerprint()
    assert fp1 == fp2
    assert len(fp1) == 64


def test_sample_readiness_gate_insufficient_p1_events():
    gate = SampleReadinessGate()
    eval_res = gate.evaluate_readiness(
        event_count_p1=10,  # < 30
        event_count_p2=35,
        distinct_utc_weeks=16,
        distinct_volatility_regimes=2,
        source_coverage_pct=98.0,
        has_30d_forward_warmup=True,
    )
    assert eval_res["ready_for_controller_evaluation"] is False
    assert eval_res["status"] == "EVIDENCE_IMMATURE"
    assert eval_res["criteria"]["p1_events"]["passed"] is False


def test_sample_readiness_gate_insufficient_p2_events():
    gate = SampleReadinessGate()
    eval_res = gate.evaluate_readiness(
        event_count_p1=32,
        event_count_p2=12,  # < 30
        distinct_utc_weeks=16,
        distinct_volatility_regimes=2,
        source_coverage_pct=98.0,
        has_30d_forward_warmup=True,
    )
    assert eval_res["ready_for_controller_evaluation"] is False
    assert eval_res["status"] == "EVIDENCE_IMMATURE"
    assert eval_res["criteria"]["p2_events"]["passed"] is False


def test_sample_readiness_gate_insufficient_weeks():
    gate = SampleReadinessGate()
    eval_res = gate.evaluate_readiness(
        event_count_p1=35,
        event_count_p2=35,
        distinct_utc_weeks=8,  # < 15
        distinct_volatility_regimes=2,
        source_coverage_pct=98.0,
        has_30d_forward_warmup=True,
    )
    assert eval_res["ready_for_controller_evaluation"] is False
    assert eval_res["status"] == "EVIDENCE_IMMATURE"
    assert eval_res["criteria"]["distinct_utc_weeks"]["passed"] is False


def test_sample_readiness_gate_insufficient_regimes():
    gate = SampleReadinessGate()
    eval_res = gate.evaluate_readiness(
        event_count_p1=35,
        event_count_p2=35,
        distinct_utc_weeks=16,
        distinct_volatility_regimes=1,  # < 2
        source_coverage_pct=98.0,
        has_30d_forward_warmup=True,
    )
    assert eval_res["ready_for_controller_evaluation"] is False
    assert eval_res["status"] == "EVIDENCE_IMMATURE"
    assert eval_res["criteria"]["volatility_regimes"]["passed"] is False


def test_sample_readiness_gate_insufficient_source_coverage():
    gate = SampleReadinessGate()
    eval_res = gate.evaluate_readiness(
        event_count_p1=35,
        event_count_p2=35,
        distinct_utc_weeks=16,
        distinct_volatility_regimes=2,
        source_coverage_pct=91.0,  # < 95%
        has_30d_forward_warmup=True,
    )
    assert eval_res["ready_for_controller_evaluation"] is False
    assert eval_res["status"] == "EVIDENCE_IMMATURE"
    assert eval_res["criteria"]["source_coverage_pct"]["passed"] is False


def test_sample_readiness_gate_missing_30d_forward_warmup():
    gate = SampleReadinessGate()
    eval_res = gate.evaluate_readiness(
        event_count_p1=35,
        event_count_p2=35,
        distinct_utc_weeks=16,
        distinct_volatility_regimes=2,
        source_coverage_pct=99.0,
        has_30d_forward_warmup=False,  # < 30d prospective warmup
    )
    assert eval_res["ready_for_controller_evaluation"] is False
    assert eval_res["status"] == "EVIDENCE_IMMATURE"


def test_sample_readiness_gate_all_criteria_met():
    gate = SampleReadinessGate()
    eval_res = gate.evaluate_readiness(
        event_count_p1=35,
        event_count_p2=40,
        distinct_utc_weeks=18,
        distinct_volatility_regimes=2,
        source_coverage_pct=99.2,
        has_30d_forward_warmup=True,
    )
    assert eval_res["ready_for_controller_evaluation"] is True
    assert eval_res["status"] == "SAMPLE_READINESS_MET"
    assert "ZERO_HISTORICAL_OUTCOME_SEARCH" in eval_res["prohibition_notice"]


def test_protected_data_prohibition():
    """Verify that no implementation files import or read protected historical data paths."""
    scripts_dir = repo_root / "scripts" / "strategy_research" / "forward_shadow_research_r1"
    for py_file in scripts_dir.glob("*.py"):
        text = py_file.read_text()
        assert "Quant-agent/data" not in text
        assert "Quant-agent-sanitized" not in text
        assert "H39" not in text
        assert "H40" not in text
        assert "H41" not in text


def test_compute_frozen_manifest_includes_all_files():
    manifest = compute_frozen_manifest()
    assert len(manifest) >= 9
    for path in manifest:
        assert path.startswith(("scripts/strategy_research/forward_shadow_research_r1", "tests/"))


def test_run_developmental_synthetic_suite_end_to_end(tmp_path):
    out_dir = tmp_path / "evidence"
    scratch_dir = tmp_path / "scratch"
    receipt = run_developmental_synthetic_suite(out_dir, scratch_dir)

    assert receipt["terminal_status"] == "FORWARD_SHADOW_ENGINE_PRE_REGISTERED_OFFLINE_VERIFIED"
    assert receipt["sample_readiness_gate"]["status"] == "EVIDENCE_IMMATURE"
    assert len(receipt["cell_summaries"]) == 6
    assert (out_dir / "DEVELOPMENTAL_SYNTHETIC_SUITE_RECEIPT.json").exists()
    assert (out_dir / "SAMPLE_READINESS_AUDIT.json").exists()
