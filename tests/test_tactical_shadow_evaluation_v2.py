from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Import test fixture from test_tactical_feature_evidence_v2
from test_tactical_feature_evidence_v2 import build_sample_evidence_and_assessment

from btc_quant_agent.domain import Candle
from btc_quant_agent.market_watch.domain import (
    DIRECTIONAL_OUTCOME_PROFILE_VERSION,
    MARKET_WATCH_EVIDENCE_VERSION,
    TACTICAL_COHORT_SUMMARY_VERSION,
    ShadowExecutionPathModel,
    ShadowPathResolution,
)
from btc_quant_agent.market_watch.evidence import (
    TacticalFeatureEvidenceV2,
    canonical_evidence_json,
)
from btc_quant_agent.market_watch.shadow import ShadowEvaluationManager
from btc_quant_agent.market_watch.shadow_evidence import (
    EvaluationTerminalStatus,
    FundingStatus,
    TacticalShadowAttributionConflictError,
    TacticalShadowEvaluationConflictError,
    TacticalShadowEvaluationIdentityError,
    build_tactical_shadow_evaluation_v2,
    canonical_shadow_evaluation_json,
    classify_rule_score_bucket,
    compute_tactical_cohort_summary_v1,
    deserialize_tactical_shadow_evaluation,
    evaluate_tactical_funding_v1,
    get_playbook_evaluation_profile,
    sample_size_label,
    validate_tactical_shadow_evaluation,
    verify_shadow_evaluation_identity,
)
from btc_quant_agent.market_watch.state import MarketWatchStateStore


def _create_mock_shadow_record(
    ev: TacticalFeatureEvidenceV2,
    shadow_id: int = 1,
    fill_status: str = "FILLED",
    fill_price: float = 50000.0,
    fill_time_ms: int = 1_700_000_100_000,
    terminal_status: str = "FILLED",
    terminal_reason: str = "TP1",
    exit_price: float = 51500.0,
    exit_time_ms: int = 1_700_014_500_000,
    mfe_r: float = 1.8,
    mae_r: float = -0.3,
    tp1_hit: bool = True,
    tp2_hit: bool = False,
    sl_hit: bool = False,
    gross_r: float = 1.5,
    friction_r: float = 0.05,
    net_r: float = 1.45,
    coverage_status: str = "COMPLETE",
    evaluation_profile_version: str = DIRECTIONAL_OUTCOME_PROFILE_VERSION,
    evaluation_horizon_ms: int = 12 * 3600 * 1000,
) -> dict[str, Any]:
    """Helper to generate a DB-like shadow record matching a given feature evidence."""
    t0 = ev.decision_time_ms
    bar_len = 15 * 60 * 1000
    return {
        "id": shadow_id,
        "timestamp_ms": t0,
        "symbol": ev.symbol,
        "snapshot_hash": ev.snapshot_hash,
        "policy_version": ev.policy_version,
        "config_hash": ev.config_hash,
        "agent_decision": ev.decision_trace.final_directional_decision,
        "agent_setup": ev.selected_playbook,
        "entry_quality": ev.entry_quality,
        "reason_codes_json": json.dumps(list(ev.reason_codes)),
        "reference_decision": None,
        "reference_notes": None,
        "entry_price": fill_price,
        "stop_loss": 49000.0,
        "tp1": 51500.0,
        "tp2": 52500.0,
        "direction": ev.decision_trace.final_directional_decision,
        "future_mfe": mfe_r,
        "future_mae": mae_r,
        "tp1_hit": 1 if tp1_hit else 0,
        "tp2_hit": 1 if tp2_hit else 0,
        "sl_hit": 1 if sl_hit else 0,
        "time_to_target_ms": (exit_time_ms - fill_time_ms) if tp1_hit else None,
        "time_to_stop_ms": (exit_time_ms - fill_time_ms) if sl_hit else None,
        "net_r": net_r if fill_status != "NO_FILL" else None,
        "gross_r": gross_r if fill_status != "NO_FILL" else None,
        "friction_r": friction_r if fill_status != "NO_FILL" else None,
        "regime_after": "RESOLVED_TERMINAL" if fill_status != "NO_FILL" else "NO_FILL",
        "resolved": 1,
        "evaluation_horizon_bars": 16,
        "evaluation_end_ms": t0 + (16 * bar_len),
        "observation_type": "ACTIONABLE_TRIGGERED",
        "signal_identity": ev.signal_identity,
        "signal_time_ms": t0,
        "entry_zone_low": 49950.0,
        "entry_zone_high": 50050.0,
        "entry_window_bars": 4,
        "entry_window_end_ms": t0 + (4 * bar_len),
        "fill_status": fill_status,
        "fill_time_ms": fill_time_ms if fill_status != "NO_FILL" else None,
        "fill_price": fill_price if fill_status != "NO_FILL" else None,
        "path_resolution": ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value,
        "execution_path_model": ShadowExecutionPathModel.PARTIAL_FIRST_BAR_1M_THEN_15M.value,
        "setup_key": ev.setup_key,
        "evidence_version": MARKET_WATCH_EVIDENCE_VERSION,
        "entry_window_start_ms": t0,
        "evaluation_start_ms": fill_time_ms if fill_status != "NO_FILL" else None,
        "terminal_reason": terminal_reason,
        "exit_time_ms": exit_time_ms if fill_status != "NO_FILL" else (t0 + 4 * bar_len),
        "exit_price": exit_price if fill_status != "NO_FILL" else None,
        "coverage_status": coverage_status,
        "coverage_reason": None,
        "semantic_identity_json": json.dumps(ev.semantic_identity.to_dict()),
        "feature_evidence_id": ev.evidence_id,
        "evaluation_profile_version": evaluation_profile_version,
        "evaluation_horizon_ms": evaluation_horizon_ms,
    }


def test_b2a_01_playbook_evaluation_profiles() -> None:
    """Verify frozen evaluation horizon profiles (Section 18)."""
    p_pullback = get_playbook_evaluation_profile("TREND_PULLBACK")
    assert p_pullback["horizon_hours"] == 12
    assert p_pullback["horizon_bars"] == 48
    assert p_pullback["horizon_ms"] == 12 * 3600 * 1000

    p_breakout = get_playbook_evaluation_profile("BREAKOUT_RETEST")
    assert p_breakout["horizon_hours"] == 12
    assert p_breakout["horizon_bars"] == 48

    p_failed_bo = get_playbook_evaluation_profile("FAILED_BREAKOUT")
    assert p_failed_bo["horizon_hours"] == 8
    assert p_failed_bo["horizon_bars"] == 32
    assert p_failed_bo["horizon_ms"] == 8 * 3600 * 1000

    p_failed_bd = get_playbook_evaluation_profile("FAILED_BREAKDOWN")
    assert p_failed_bd["horizon_hours"] == 8
    assert p_failed_bd["horizon_bars"] == 32

    p_vol = get_playbook_evaluation_profile("VOLATILITY_EXPANSION")
    assert p_vol["horizon_hours"] == 8
    assert p_vol["horizon_bars"] == 32


def test_b2a_02_rule_score_bucket_classification() -> None:
    """Verify Rule Score bucket mapping (Section 34)."""
    assert classify_rule_score_bucket(0.0) == "0–39.999"
    assert classify_rule_score_bucket(39.999) == "0–39.999"
    assert classify_rule_score_bucket(40.0) == "40–59.999"
    assert classify_rule_score_bucket(59.999) == "40–59.999"
    assert classify_rule_score_bucket(60.0) == "60–74.999"
    assert classify_rule_score_bucket(74.999) == "60–74.999"
    assert classify_rule_score_bucket(75.0) == "75–89.999"
    assert classify_rule_score_bucket(89.999) == "75–89.999"
    assert classify_rule_score_bucket(90.0) == "90–100"
    assert classify_rule_score_bucket(100.0) == "90–100"
    assert classify_rule_score_bucket(None) == "UNKNOWN"


def test_b2a_03_sample_size_labels() -> None:
    """Verify sample size classification (Section 36)."""
    assert sample_size_label(0) == "VERY_LOW_SAMPLE"
    assert sample_size_label(9) == "VERY_LOW_SAMPLE"
    assert sample_size_label(10) == "LOW_SAMPLE"
    assert sample_size_label(29) == "LOW_SAMPLE"
    assert sample_size_label(30) == "OBSERVED_SAMPLE"
    assert sample_size_label(100) == "OBSERVED_SAMPLE"


def test_b2a_04_funding_accounting_signed_formula() -> None:
    """Verify funding cash formula: LONG is -mark*rate, SHORT is +mark*rate (Section 22)."""
    fill_t = 1_700_000_000_000
    exit_t = fill_t + (12 * 3600 * 1000)
    fill_p = 50000.0
    sl = 49000.0  # initial risk = 1000.0
    settlement_t = fill_t + (4 * 3600 * 1000)

    # 1. LONG with positive funding rate -> pays funding (negative cash)
    funding_data = [
        {"funding_time_ms": settlement_t, "funding_rate": 0.0001, "mark_price": 50500.0}
    ]
    acct_long = evaluate_tactical_funding_v1(
        direction="LONG",
        fill_price=fill_p,
        stop_loss=sl,
        fill_time_ms=fill_t,
        exit_time_ms=exit_t,
        funding_records=funding_data,
    )
    assert acct_long.funding_status == FundingStatus.COMPLETE.value
    assert acct_long.settlements_count == 1
    # funding_cash = -50500 * 0.0001 = -5.05
    assert pytest.approx(acct_long.funding_cash_total, 1e-6) == -5.05
    # funding_r = -5.05 / 1000 = -0.00505
    assert pytest.approx(acct_long.funding_pnl_r, 1e-6) == -0.00505

    # 2. SHORT with positive funding rate -> receives funding (positive cash)
    sl_short = 51000.0  # initial risk = 1000.0
    acct_short = evaluate_tactical_funding_v1(
        direction="SHORT",
        fill_price=fill_p,
        stop_loss=sl_short,
        fill_time_ms=fill_t,
        exit_time_ms=exit_t,
        funding_records=funding_data,
    )
    assert acct_short.funding_status == FundingStatus.COMPLETE.value
    assert pytest.approx(acct_short.funding_cash_total, 1e-6) == 5.05
    assert pytest.approx(acct_short.funding_pnl_r, 1e-6) == 0.00505


def test_b2a_05_funding_ambiguous_fill_boundary() -> None:
    """Verify ambiguous fill boundary (within 60s of fill) yields AMBIGUOUS_FILL_BOUNDARY (Section 22)."""
    fill_t = 1_700_000_000_000
    exit_t = fill_t + (12 * 3600 * 1000)
    # Settlement occurs 30s after fill
    ambiguous_settlement_t = fill_t + 30_000

    funding_data = [
        {"funding_time_ms": ambiguous_settlement_t, "funding_rate": 0.0001, "mark_price": 50000.0}
    ]
    acct = evaluate_tactical_funding_v1(
        direction="LONG",
        fill_price=50000.0,
        stop_loss=49000.0,
        fill_time_ms=fill_t,
        exit_time_ms=exit_t,
        funding_records=funding_data,
    )
    assert acct.funding_status == FundingStatus.AMBIGUOUS_FILL_BOUNDARY.value
    assert acct.funding_pnl_r is None


def test_b2a_06_funding_incomplete_history_and_fetch_error() -> None:
    """Verify INCOMPLETE_HISTORY and FETCH_ERROR taxonomies."""
    fill_t = 1_700_000_000_000
    exit_t = fill_t + 3600_000

    # None funding records -> INCOMPLETE_HISTORY
    acct_none = evaluate_tactical_funding_v1(
        direction="LONG",
        fill_price=50000.0,
        stop_loss=49000.0,
        fill_time_ms=fill_t,
        exit_time_ms=exit_t,
        funding_records=None,
    )
    assert acct_none.funding_status == FundingStatus.INCOMPLETE_HISTORY.value

    # Fetch error -> FETCH_ERROR
    acct_err = evaluate_tactical_funding_v1(
        direction="LONG",
        fill_price=50000.0,
        stop_loss=49000.0,
        fill_time_ms=fill_t,
        exit_time_ms=exit_t,
        funding_records=None,
        fetch_error=True,
    )
    assert acct_err.funding_status == FundingStatus.FETCH_ERROR.value

    # Missing mark price -> INCOMPLETE_MARK_PRICE
    funding_data_missing_mark = [
        {"funding_time_ms": fill_t + 120_000, "funding_rate": 0.0001, "mark_price": None}
    ]
    acct_mark = evaluate_tactical_funding_v1(
        direction="LONG",
        fill_price=50000.0,
        stop_loss=49000.0,
        fill_time_ms=fill_t,
        exit_time_ms=exit_t,
        funding_records=funding_data_missing_mark,
    )
    assert acct_mark.funding_status == FundingStatus.INCOMPLETE_MARK_PRICE.value


def test_b2a_07_no_fill_evaluation_structure() -> None:
    """Verify NO_FILL evaluation semantics (Section 21)."""
    ev, _ = build_sample_evidence_and_assessment()
    rec = _create_mock_shadow_record(ev, fill_status="NO_FILL", terminal_reason="NO_FILL")

    evaluation = build_tactical_shadow_evaluation_v2(
        shadow_record=rec,
        feature_evidence=ev,
        candles_15m=(),
        funding_records=None,
    )

    assert evaluation.terminal_status == EvaluationTerminalStatus.NO_FILL.value
    assert evaluation.fill_status == "NO_FILL"
    assert evaluation.fill_time_ms is None
    assert evaluation.fill_price is None
    assert evaluation.time_to_fill_ms is None
    assert evaluation.time_from_fill_to_terminal_ms is None
    assert evaluation.net_r_ex_funding is None
    assert evaluation.net_r_after_funding is None
    assert evaluation.funding_accounting.funding_status == FundingStatus.NOT_APPLICABLE.value
    assert evaluation.coverage.entry_coverage_complete is True
    assert evaluation.coverage.outcome_coverage_complete is False

    # Checkpoints must all exist and have status NO_FILL
    assert len(evaluation.outcome_checkpoints) == 4
    for cp in evaluation.outcome_checkpoints:
        assert cp.status in ("NOT_APPLICABLE", "NO_FILL")
        assert cp.mark_price is None
        assert cp.mark_to_market_gross_r is None

    # Validate identity and serialization round-trip
    verify_shadow_evaluation_identity(evaluation)
    raw_json = canonical_shadow_evaluation_json(evaluation)
    deserialized = deserialize_tactical_shadow_evaluation(raw_json)
    assert deserialized == evaluation


def test_b2a_08_filled_tp1_evaluation_structure() -> None:
    """Verify FILLED evaluation with TP1 and funding complete (Section 19 & 22)."""
    ev, _ = build_sample_evidence_and_assessment()
    fill_t = ev.decision_time_ms + 15 * 60 * 1000
    exit_t = fill_t + (6 * 3600 * 1000)
    rec = _create_mock_shadow_record(
        ev,
        fill_status="FILLED",
        fill_price=50000.0,
        fill_time_ms=fill_t,
        terminal_status="FILLED",
        terminal_reason="TP1",
        exit_price=51500.0,
        exit_time_ms=exit_t,
        gross_r=1.5,
        friction_r=0.05,
        net_r=1.45,
    )

    funding_data = [
        {"funding_time_ms": fill_t + (2 * 3600 * 1000), "funding_rate": 0.0001, "mark_price": 50600.0}
    ]
    # LONG: funding_cash = -50600 * 0.0001 = -5.06
    # initial risk = 50000 - 49000 = 1000
    # funding_r = -0.00506
    # net_r_after_funding = 1.45 - 0.00506 = 1.44494

    evaluation = build_tactical_shadow_evaluation_v2(
        shadow_record=rec,
        feature_evidence=ev,
        candles_15m=(),
        funding_records=funding_data,
    )

    assert evaluation.terminal_status == EvaluationTerminalStatus.FILLED.value
    assert evaluation.fill_status == "FILLED"
    assert evaluation.tp1_hit is True
    assert evaluation.sl_hit is False
    assert evaluation.net_r_ex_funding == 1.45
    assert pytest.approx(evaluation.net_r_after_funding, 1e-5) == 1.44494
    assert evaluation.funding_accounting.funding_status == FundingStatus.COMPLETE.value
    assert evaluation.attribution is not None
    assert evaluation.attribution.selected_playbook == ev.selected_playbook
    assert evaluation.attribution.rule_score == ev.rule_score

    validate_tactical_shadow_evaluation(evaluation)


def test_b2a_09_attribution_crosscheck_fail_closed() -> None:
    """Verify attribution mismatch against FeatureEvidenceV2 raises TacticalShadowAttributionConflictError (Section 9)."""
    ev, _ = build_sample_evidence_and_assessment()
    rec = _create_mock_shadow_record(ev)

    # 1. Playbook mismatch
    rec_bad_pb = dict(rec)
    rec_bad_pb["agent_setup"] = "FAILED_BREAKOUT"
    with pytest.raises(TacticalShadowAttributionConflictError):
        build_tactical_shadow_evaluation_v2(rec_bad_pb, ev)

    # 2. Direction mismatch
    rec_bad_dir = dict(rec)
    rec_bad_dir["direction"] = "SHORT"
    with pytest.raises(TacticalShadowAttributionConflictError):
        build_tactical_shadow_evaluation_v2(rec_bad_dir, ev)

    # 3. Signal identity mismatch
    rec_bad_sig = dict(rec)
    rec_bad_sig["signal_identity"] = "BTCUSDT:TREND_PULLBACK:LONG:100:99999"
    with pytest.raises(TacticalShadowAttributionConflictError):
        build_tactical_shadow_evaluation_v2(rec_bad_sig, ev)

    # 4. Snapshot hash mismatch
    rec_bad_hash = dict(rec)
    rec_bad_hash["snapshot_hash"] = "tampered_hash"
    with pytest.raises(TacticalShadowAttributionConflictError):
        build_tactical_shadow_evaluation_v2(rec_bad_hash, ev)


def test_b2a_10_database_persistence_and_conflict() -> None:
    """Verify SQLite persistence, unique natural key, idempotence, and conflict errors (Section 24 & 25)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_b2a.db"
        store = MarketWatchStateStore(db_path)

        ev, _ = build_sample_evidence_and_assessment()
        now_ms = 1_700_000_100_000
        # Save feature evidence
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO tactical_feature_evidence_v2 (
                    evidence_id, evidence_schema_version, decision_time_ms, symbol,
                    snapshot_hash, policy_version, config_hash, semantic_identity_hash,
                    signal_identity, setup_key, lifecycle_state, selected_playbook,
                    final_directional_decision, rule_score, reference_universe_status,
                    evidence_json, persisted_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev.evidence_id, ev.evidence_schema_version, ev.decision_time_ms, ev.symbol,
                    ev.snapshot_hash, ev.policy_version, ev.config_hash, None,
                    ev.signal_identity, ev.setup_key, ev.lifecycle_state, ev.selected_playbook,
                    ev.decision_trace.final_directional_decision, ev.rule_score, "COMPLETE",
                    canonical_evidence_json(ev), now_ms,
                ),
            )
            conn.commit()

        rec = _create_mock_shadow_record(ev, shadow_id=42)
        evaluation = build_tactical_shadow_evaluation_v2(rec, ev)

        # 1. First save succeeds
        saved_id = store.save_shadow_evaluation(evaluation)
        assert saved_id == evaluation.evaluation_id

        # 2. Idempotent re-save returns existing ID
        re_saved = store.save_shadow_evaluation(evaluation)
        assert re_saved == evaluation.evaluation_id

        # 3. Retrieve by ID
        fetched = store.get_shadow_evaluation(saved_id)
        assert fetched is not None
        assert fetched.evaluation_id == evaluation.evaluation_id
        assert fetched.symbol == ev.symbol

        # 4. Retrieve by shadow_record_id
        fetched_by_rec = store.get_shadow_evaluation_by_shadow_id(42)
        assert fetched_by_rec is not None
        assert fetched_by_rec.evaluation_id == evaluation.evaluation_id

        # 5. List query
        listed = store.list_shadow_evaluations(symbol="BTCUSDT")
        assert len(listed) == 1
        assert listed[0].evaluation_id == evaluation.evaluation_id

        # 6. Conflict error on divergent evaluation for same natural key
        # Create divergent evaluation with same shadow_record_id and profile version
        rec_divergent = dict(rec)
        rec_divergent["exit_price"] = 99999.0
        eval_divergent = build_tactical_shadow_evaluation_v2(rec_divergent, ev)
        with pytest.raises(TacticalShadowEvaluationConflictError):
            store.save_shadow_evaluation(eval_divergent)

        # 7. Identity error on corrupted/tampered DB record
        with store._connect() as conn:
            conn.execute(
                "UPDATE tactical_shadow_evaluations_v2 SET evaluation_json = REPLACE(evaluation_json, 'BTCUSDT', 'ETHUSDT')"
            )
            conn.commit()
        with pytest.raises(TacticalShadowEvaluationIdentityError):
            store.get_shadow_evaluation(saved_id)


def test_b2a_11_cohort_summary_aggregation_and_stratification() -> None:
    """Verify compute_tactical_cohort_summary_v1 metrics and stratification (Section 31-36)."""
    ev1, _ = build_sample_evidence_and_assessment()
    ev2, _ = build_sample_evidence_and_assessment()

    # Create 3 evaluations:
    # 1. Filled TP1 (gross R = 1.5, friction = 0, net R = 1.5)
    rec1 = _create_mock_shadow_record(ev1, shadow_id=1, fill_status="FILLED", terminal_reason="TP1", exit_price=51500.0, friction_r=0.0)
    eval1 = build_tactical_shadow_evaluation_v2(rec1, ev1)

    # 2. Filled STOP (gross R = -1.0, friction = 0, net R = -1.0)
    rec2 = _create_mock_shadow_record(ev1, shadow_id=2, fill_status="FILLED", terminal_reason="STOP", tp1_hit=False, sl_hit=True, exit_price=49000.0, friction_r=0.0)
    eval2 = build_tactical_shadow_evaluation_v2(rec2, ev1)

    # 3. NO_FILL (net R = None)
    rec3 = _create_mock_shadow_record(ev2, shadow_id=3, fill_status="NO_FILL", terminal_reason="NO_FILL")
    eval3 = build_tactical_shadow_evaluation_v2(rec3, ev2)

    evaluations = [eval1, eval2, eval3]

    # Overall summary
    summary = compute_tactical_cohort_summary_v1(evaluations, stratification_dimension="playbook")
    assert summary["summary_schema_version"] == TACTICAL_COHORT_SUMMARY_VERSION
    assert summary["evaluation_count"] == 3

    overall = summary["cohorts"]["OVERALL"]
    assert overall["signal_count"] == 3
    assert overall["sample_label"] == "VERY_LOW_SAMPLE"
    assert overall["fill_count"] == 2
    assert overall["no_fill_count"] == 1
    # P(fill) = 2 / 3
    assert pytest.approx(overall["sample_fill_rate"], 1e-4) == 2 / 3
    # Conditional frequencies over filled:
    # TP1: 1 / 2 = 0.5
    # STOP: 1 / 2 = 0.5
    # TIMEOUT: 0 / 2 = 0.0
    assert pytest.approx(overall["sample_tp1_rate_given_fill"], 1e-4) == 0.5
    assert pytest.approx(overall["sample_stop_rate_given_fill"], 1e-4) == 0.5
    assert pytest.approx(overall["sample_timeout_rate_given_fill"], 1e-4) == 0.0

    # Net R per signal ex funding treats NO_FILL as 0 R: (1.5 - 1.0 + 0.0) / 3 = 0.5 / 3 = 0.1667
    assert pytest.approx(overall["sample_mean_net_r_per_signal_ex_funding"], 1e-4) == 0.5 / 3
    # Net R per fill ex funding averages only filled: (1.5 - 1.0) / 2 = 0.25
    assert pytest.approx(overall["mean_net_r_ex_funding"], 1e-4) == 0.25

    # Check stratification
    strat = summary["cohorts"]["stratified_cohorts"]
    assert "BREAKOUT_RETEST" in strat
    assert strat["BREAKOUT_RETEST"]["signal_count"] == 3


def test_b2a_12_end_to_end_shadow_resolver_integration() -> None:
    """Verify resolve_pending_observations produces and saves TacticalShadowEvaluationV2 (Section 17-20)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_b2a_e2e.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)

        ev, assessment = build_sample_evidence_and_assessment()
        now_ms = 1_700_000_100_000

        # Save feature evidence
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO tactical_feature_evidence_v2 (
                    evidence_id, evidence_schema_version, decision_time_ms, symbol,
                    snapshot_hash, policy_version, config_hash, semantic_identity_hash,
                    signal_identity, setup_key, lifecycle_state, selected_playbook,
                    final_directional_decision, rule_score, reference_universe_status,
                    evidence_json, persisted_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev.evidence_id, ev.evidence_schema_version, ev.decision_time_ms, ev.symbol,
                    ev.snapshot_hash, ev.policy_version, ev.config_hash, None,
                    ev.signal_identity, ev.setup_key, ev.lifecycle_state, ev.selected_playbook,
                    ev.decision_trace.final_directional_decision, ev.rule_score, "COMPLETE",
                    canonical_evidence_json(ev), now_ms,
                ),
            )
            conn.commit()

        # Record decision
        rec_id = mgr.record_decision(assessment)
        assert rec_id > 0

        # Resolve with NO_FILL (entry window expires with complete coverage)
        t0 = assessment.snapshot.decision_time_ms
        bar_len = 15 * 60 * 1000
        # Entry window is 4 bars: t0 to t0 + 4 * bar_len
        # Candles price stays above entry (105-108), never touching 50000
        candles = [
            Candle("BTCUSDT", "15m", t0 + i * bar_len, t0 + (i + 1) * bar_len, 50500.0, 50800.0, 50300.0, 50600.0, 100.0)
            for i in range(5)
        ]
        client = MagicMock()
        client.klines.return_value = candles

        res = mgr.resolve_pending_observations(client, current_time_ms=t0 + 5 * bar_len)
        assert res["resolved_count"] == 1

        # Verify TacticalShadowEvaluationV2 was materialized and saved!
        eval_saved = store.get_shadow_evaluation_by_shadow_id(rec_id)
        assert eval_saved is not None
        assert eval_saved.shadow_record_id == rec_id
        assert eval_saved.feature_evidence_id == ev.evidence_id
        assert eval_saved.terminal_status == EvaluationTerminalStatus.NO_FILL.value
        assert eval_saved.fill_status == "NO_FILL"
