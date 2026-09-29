from __future__ import annotations

import json
import sqlite3
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
    TacticalEvidenceLinkageError,
    TacticalFeatureEvidenceV2,
    canonical_evidence_json,
    canonical_evidence_payload,
    canonical_json_dump,
    compute_evidence_id,
    deserialize_tactical_feature_evidence,
)
from btc_quant_agent.market_watch.shadow import ShadowEvaluationManager
from btc_quant_agent.market_watch.shadow_evidence import (
    EvaluationTerminalStatus,
    FundingStatus,
    TacticalShadowAttributionConflictError,
    TacticalShadowEvaluationConflictError,
    TacticalShadowEvaluationIdentityError,
    TacticalShadowEvaluationValidationError,
    TacticalShadowProfileConflictError,
    build_tactical_shadow_evaluation_v2,
    canonical_shadow_evaluation_json,
    classify_rule_score_bucket,
    compute_diagnostic_checkpoints,
    compute_tactical_cohort_summary_v1,
    deserialize_tactical_shadow_evaluation,
    evaluate_tactical_funding_v1,
    get_playbook_evaluation_profile,
    sample_size_label,
    validate_tactical_shadow_evaluation,
    verify_shadow_evaluation_identity,
)
from btc_quant_agent.market_watch.state import MarketWatchStateStore


def _insert_feature_evidence_in_db(store: MarketWatchStateStore, ev: TacticalFeatureEvidenceV2) -> None:
    """Helper to persist TacticalFeatureEvidenceV2 into SQLite for prerequisite checks."""
    now_ms = 1_700_000_100_000
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
                ev.evidence_id,
                ev.evidence_schema_version,
                ev.decision_time_ms,
                ev.symbol,
                ev.snapshot_hash,
                ev.policy_version,
                ev.config_hash,
                None,
                ev.signal_identity,
                ev.setup_key,
                ev.lifecycle_state,
                ev.selected_playbook,
                ev.decision_trace.final_directional_decision,
                ev.rule_score,
                "COMPLETE",
                canonical_evidence_json(ev),
                now_ms,
            ),
        )
        conn.commit()


def _insert_shadow_record_in_db(store: MarketWatchStateStore, rec: dict[str, Any]) -> None:
    """Helper to persist a raw shadow record dict into market_watch_shadow_records for prerequisite checks."""
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO market_watch_shadow_records (
                id, timestamp_ms, symbol, snapshot_hash, policy_version, config_hash,
                agent_decision, agent_setup, entry_quality, reason_codes_json,
                reference_decision, reference_notes,
                entry_price, stop_loss, tp1, tp2, direction, future_mfe, future_mae,
                tp1_hit, tp2_hit, sl_hit, time_to_target_ms, time_to_stop_ms,
                net_r, gross_r, friction_r, regime_after,
                resolved, evaluation_horizon_bars, evaluation_end_ms, observation_type,
                signal_identity, signal_time_ms, entry_zone_low, entry_zone_high,
                entry_window_bars, entry_window_end_ms, fill_status, fill_time_ms,
                path_resolution, execution_path_model, setup_key, evidence_version,
                entry_window_start_ms, evaluation_start_ms, terminal_reason, exit_time_ms,
                exit_price, coverage_status, coverage_reason, semantic_identity_json,
                feature_evidence_id, evaluation_profile_version, evaluation_horizon_ms,
                fill_interval_start_ms, fill_interval_end_ms, fill_time_resolution
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                rec.get("id"),
                rec.get("timestamp_ms"),
                rec.get("symbol"),
                rec.get("snapshot_hash"),
                rec.get("policy_version"),
                rec.get("config_hash"),
                rec.get("agent_decision"),
                rec.get("agent_setup"),
                rec.get("entry_quality"),
                rec.get("reason_codes_json"),
                rec.get("reference_decision"),
                rec.get("reference_notes"),
                rec.get("entry_price"),
                rec.get("stop_loss"),
                rec.get("tp1"),
                rec.get("tp2"),
                rec.get("direction"),
                rec.get("future_mfe"),
                rec.get("future_mae"),
                rec.get("tp1_hit"),
                rec.get("tp2_hit"),
                rec.get("sl_hit"),
                rec.get("time_to_target_ms"),
                rec.get("time_to_stop_ms"),
                rec.get("net_r"),
                rec.get("gross_r"),
                rec.get("friction_r"),
                rec.get("regime_after"),
                rec.get("resolved"),
                rec.get("evaluation_horizon_bars"),
                rec.get("evaluation_end_ms"),
                rec.get("observation_type"),
                rec.get("signal_identity"),
                rec.get("signal_time_ms"),
                rec.get("entry_zone_low"),
                rec.get("entry_zone_high"),
                rec.get("entry_window_bars"),
                rec.get("entry_window_end_ms"),
                rec.get("fill_status"),
                rec.get("fill_time_ms"),
                rec.get("path_resolution"),
                rec.get("execution_path_model"),
                rec.get("setup_key"),
                rec.get("evidence_version"),
                rec.get("entry_window_start_ms"),
                rec.get("evaluation_start_ms"),
                rec.get("terminal_reason"),
                rec.get("exit_time_ms"),
                rec.get("exit_price"),
                rec.get("coverage_status"),
                rec.get("coverage_reason"),
                rec.get("semantic_identity_json"),
                rec.get("feature_evidence_id"),
                rec.get("evaluation_profile_version"),
                rec.get("evaluation_horizon_ms"),
                rec.get("fill_interval_start_ms"),
                rec.get("fill_interval_end_ms"),
                rec.get("fill_time_resolution"),
            ),
        )
        conn.commit()


def _create_mock_shadow_record(
    ev: TacticalFeatureEvidenceV2,
    shadow_id: int = 1,
    fill_status: str = "FILLED",
    fill_price: float = 50000.0,
    fill_time_ms: int | None = None,
    terminal_status: str = "FILLED",
    terminal_reason: str = "TP1",
    exit_price: float | None = None,
    exit_time_ms: int | None = None,
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
    evaluation_horizon_ms: int | None = None,
    evaluation_horizon_bars: int | None = None,
    fill_interval_start_ms: int | None = None,
    fill_interval_end_ms: int | None = None,
    fill_time_resolution: str | None = None,
) -> dict[str, Any]:
    """Helper to generate a DB-like shadow record matching a given feature evidence."""
    t0 = ev.decision_time_ms
    bar_len = 15 * 60 * 1000

    rp = ev.directional_risk_plan
    entry_low = rp.entry_low if rp else 49800.0
    entry_high = rp.entry_high if rp else 50200.0
    stop_loss = rp.stop_loss if rp else 48000.0
    tp1 = rp.take_profit_1 if rp else 53000.0
    tp2 = rp.take_profit_2 if rp else 55000.0

    if exit_price is None:
        if fill_status == "NO_FILL":
            exit_price = None
        elif terminal_reason == "TP1":
            exit_price = tp1
        elif terminal_reason == "STOP":
            exit_price = stop_loss
        elif terminal_reason == "TP2":
            exit_price = tp2
        else:
            exit_price = fill_price

    prof = get_playbook_evaluation_profile(ev.selected_playbook)
    bars = evaluation_horizon_bars if evaluation_horizon_bars is not None else prof["horizon_bars"]
    h_ms = evaluation_horizon_ms if evaluation_horizon_ms is not None else prof["horizon_ms"]

    if fill_status != "NO_FILL":
        if fill_time_ms is None or fill_time_ms <= t0:
            fill_time_ms = t0 + bar_len
        if exit_time_ms is None:
            exit_time_ms = fill_time_ms + 6 * 3600 * 1000
        f_start = fill_interval_start_ms if fill_interval_start_ms is not None else t0
        f_end = fill_interval_end_ms if fill_interval_end_ms is not None else fill_time_ms
        f_res = fill_time_resolution if fill_time_resolution is not None else "FIFTEEN_MINUTE_FALLBACK_INTERVAL"
        eval_end = fill_time_ms + h_ms
    else:
        f_start = None
        f_end = None
        f_res = None
        eval_end = t0 + (4 * bar_len)
        fill_time_ms = None
        fill_price = None
        if exit_time_ms is None:
            exit_time_ms = t0 + 4 * bar_len

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
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "direction": ev.decision_trace.final_directional_decision,
        "future_mfe": mfe_r,
        "future_mae": mae_r,
        "tp1_hit": 1 if tp1_hit else 0,
        "tp2_hit": 1 if tp2_hit else 0,
        "sl_hit": 1 if sl_hit else 0,
        "time_to_target_ms": (exit_time_ms - fill_time_ms) if (tp1_hit and fill_time_ms) else None,
        "time_to_stop_ms": (exit_time_ms - fill_time_ms) if (sl_hit and fill_time_ms) else None,
        "net_r": net_r if fill_status != "NO_FILL" else None,
        "gross_r": gross_r if fill_status != "NO_FILL" else None,
        "friction_r": friction_r if fill_status != "NO_FILL" else None,
        "regime_after": "RESOLVED_TERMINAL" if fill_status != "NO_FILL" else "NO_FILL",
        "resolved": 1,
        "evaluation_horizon_bars": bars,
        "evaluation_end_ms": eval_end,
        "observation_type": "ACTIONABLE_TRIGGERED",
        "signal_identity": ev.signal_identity,
        "signal_time_ms": t0,
        "entry_zone_low": entry_low,
        "entry_zone_high": entry_high,
        "entry_window_bars": 4,
        "entry_window_end_ms": t0 + (4 * bar_len),
        "fill_status": fill_status,
        "fill_time_ms": fill_time_ms,
        "fill_price": fill_price,
        "path_resolution": ShadowPathResolution.ONE_MINUTE_CHRONOLOGICAL.value,
        "execution_path_model": ShadowExecutionPathModel.PARTIAL_FIRST_BAR_1M_THEN_15M.value,
        "setup_key": ev.setup_key,
        "evidence_version": MARKET_WATCH_EVIDENCE_VERSION,
        "entry_window_start_ms": t0,
        "evaluation_start_ms": fill_time_ms,
        "terminal_reason": terminal_reason,
        "exit_time_ms": exit_time_ms if fill_status != "NO_FILL" else (t0 + 4 * bar_len),
        "exit_price": exit_price,
        "coverage_status": coverage_status,
        "coverage_reason": None,
        "semantic_identity_json": json.dumps(ev.semantic_identity.to_dict()),
        "feature_evidence_id": ev.evidence_id,
        "evaluation_profile_version": evaluation_profile_version,
        "evaluation_horizon_ms": h_ms,
        "fill_interval_start_ms": f_start,
        "fill_interval_end_ms": f_end,
        "fill_time_resolution": f_res,
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
        fill_interval_start_ms=fill_t - 60_000,
        fill_interval_end_ms=fill_t,
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
        fill_interval_start_ms=fill_t - 60_000,
        fill_interval_end_ms=fill_t,
    )
    assert acct_short.funding_status == FundingStatus.COMPLETE.value
    assert pytest.approx(acct_short.funding_cash_total, 1e-6) == 5.05
    assert pytest.approx(acct_short.funding_pnl_r, 1e-6) == 0.00505


def test_b2a_05_funding_ambiguous_fill_boundary() -> None:
    """Verify ambiguous fill boundary (within fill uncertainty interval) yields AMBIGUOUS_FILL_BOUNDARY (Section 18, 21)."""
    fill_t = 1_700_000_000_000
    exit_t = fill_t + (12 * 3600 * 1000)
    # Settlement occurs inside fill touch interval [fill_t, fill_t + 60_000]
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
        fill_interval_start_ms=fill_t,
        fill_interval_end_ms=fill_t + 60_000,
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
        fill_interval_start_ms=fill_t - 60_000,
        fill_interval_end_ms=fill_t,
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
        exit_price=53000.0,
        exit_time_ms=exit_t,
        gross_r=1.5,
        friction_r=0.05,
        net_r=1.45,
    )

    funding_data = [
        {"funding_time_ms": fill_t + (2 * 3600 * 1000), "funding_rate": 0.0001, "mark_price": 50600.0}
    ]
    # LONG: funding_cash = -50600 * 0.0001 = -5.06
    # initial risk = 50000 - 48000 = 2000
    # funding_r = -5.06 / 2000 = -0.00253
    # net_r_after_funding = 1.45 - 0.00253 = 1.44747

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
    assert pytest.approx(evaluation.net_r_after_funding, 1e-5) == 1.44747
    assert evaluation.funding_accounting.funding_status == FundingStatus.COMPLETE.value
    assert evaluation.attribution is not None
    assert evaluation.attribution.selected_playbook == ev.selected_playbook
    assert evaluation.attribution.rule_score == ev.rule_score

    validate_tactical_shadow_evaluation(evaluation)


def test_b2a_09_attribution_crosscheck_fail_closed() -> None:
    """Verify attribution mismatch against FeatureEvidenceV2 raises TacticalShadowAttributionConflictError (Section 22, 23, 24)."""
    ev, _ = build_sample_evidence_and_assessment()
    rec = _create_mock_shadow_record(ev)

    # 1. Playbook mismatch
    rec_bad_pb = dict(rec)
    rec_bad_pb["agent_setup"] = "FAILED_BREAKOUT"
    with pytest.raises(TacticalShadowAttributionConflictError, match="Playbook conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_pb, ev)

    # 2. Direction mismatch
    rec_bad_dir = dict(rec)
    rec_bad_dir["direction"] = "SHORT"
    with pytest.raises(TacticalShadowAttributionConflictError, match="Direction conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_dir, ev)

    # 3. Signal identity mismatch
    rec_bad_sig = dict(rec)
    rec_bad_sig["signal_identity"] = "BTCUSDT:TREND_PULLBACK:LONG:100:99999"
    with pytest.raises(TacticalShadowAttributionConflictError, match="Signal identity conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_sig, ev)

    # 4. Snapshot hash mismatch
    rec_bad_hash = dict(rec)
    rec_bad_hash["snapshot_hash"] = "tampered_hash"
    with pytest.raises(TacticalShadowAttributionConflictError, match="Snapshot hash conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_hash, ev)

    # 5. Symbol mismatch
    rec_bad_sym = dict(rec)
    rec_bad_sym["symbol"] = "ETHUSDT"
    with pytest.raises(TacticalShadowAttributionConflictError, match="Symbol conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_sym, ev)

    # 6. Signal time mismatch
    rec_bad_t = dict(rec)
    rec_bad_t["signal_time_ms"] = ev.decision_time_ms + 1000
    with pytest.raises(TacticalShadowAttributionConflictError, match="Signal time conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_t, ev)

    # 7. Feature evidence ID mismatch
    rec_bad_id = dict(rec)
    rec_bad_id["feature_evidence_id"] = "wrong_id"
    with pytest.raises(TacticalShadowAttributionConflictError, match="Feature evidence ID conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_id, ev)

    # 8. Entry zone low mismatch
    rec_bad_el = dict(rec)
    rec_bad_el["entry_zone_low"] = 49000.0
    with pytest.raises(TacticalShadowAttributionConflictError, match="Entry zone low conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_el, ev)

    # 9. Stop loss mismatch
    rec_bad_sl = dict(rec)
    rec_bad_sl["stop_loss"] = 47000.0
    with pytest.raises(TacticalShadowAttributionConflictError, match="Stop loss conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_sl, ev)

    # 10. TP1 mismatch
    rec_bad_tp1 = dict(rec)
    rec_bad_tp1["tp1"] = 54000.0
    with pytest.raises(TacticalShadowAttributionConflictError, match="TP1 conflict"):
        build_tactical_shadow_evaluation_v2(rec_bad_tp1, ev)


def test_b2a_10_database_persistence_and_conflict() -> None:
    """Verify SQLite persistence, unique natural key, idempotence, and conflict errors (Section 24 & 25)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_b2a.db"
        store = MarketWatchStateStore(db_path)

        ev, _ = build_sample_evidence_and_assessment()
        _insert_feature_evidence_in_db(store, ev)

        rec = _create_mock_shadow_record(ev, shadow_id=42)
        _insert_shadow_record_in_db(store, rec)

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
        rec_divergent = dict(rec)
        rec_divergent["exit_price"] = 48000.0
        rec_divergent["tp1_hit"] = 0
        rec_divergent["sl_hit"] = 1
        rec_divergent["terminal_reason"] = "STOP"
        rec_divergent["gross_r"] = -1.0
        rec_divergent["net_r"] = -1.05
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
    rec1 = _create_mock_shadow_record(ev1, shadow_id=1, fill_status="FILLED", terminal_reason="TP1", exit_price=53000.0, friction_r=0.0, gross_r=1.5, net_r=1.5)
    eval1 = build_tactical_shadow_evaluation_v2(rec1, ev1)

    # 2. Filled STOP (gross R = -1.0, friction = 0, net R = -1.0)
    rec2 = _create_mock_shadow_record(ev1, shadow_id=2, fill_status="FILLED", terminal_reason="STOP", tp1_hit=False, sl_hit=True, exit_price=48000.0, friction_r=0.0, gross_r=-1.0, net_r=-1.0)
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
        _insert_feature_evidence_in_db(store, ev)

        # Record decision
        rec_id = mgr.record_decision(assessment)
        assert rec_id > 0

        # Resolve with NO_FILL (entry window expires with complete coverage)
        t0 = assessment.snapshot.decision_time_ms
        bar_len = 15 * 60 * 1000
        # Entry window is 4 bars: t0 to t0 + 4 * bar_len
        # Candles price stays above entry, never touching 50000
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


def test_b2a_13_funding_ambiguity_scenarios() -> None:
    """Verify Section 21 required funding ambiguity test cases (15m fallback, 1m touch, after interval, before interval)."""
    # Base: 10:00 UTC = 1_700_000_000_000
    t_10_00 = 1_700_000_000_000
    t_10_06 = t_10_00 + 6 * 60 * 1000
    t_10_07 = t_10_00 + 7 * 60 * 1000
    t_10_07_30 = t_10_07 + 30 * 1000
    t_10_08 = t_10_00 + 8 * 60 * 1000
    t_10_09 = t_10_00 + 9 * 60 * 1000
    t_10_15 = t_10_00 + 15 * 60 * 1000
    exit_t = t_10_00 + 4 * 3600 * 1000

    # 1. 15m fallback:
    # fill candle: 10:00 -> 10:15, recorded fill_time: 10:15
    # funding event: 10:08
    # Expected: AMBIGUOUS_FILL_BOUNDARY
    funding_10_08 = [{"funding_time_ms": t_10_08, "funding_rate": 0.0001, "mark_price": 50000.0}]
    acct_15m = evaluate_tactical_funding_v1(
        direction="LONG",
        fill_price=50000.0,
        stop_loss=48000.0,
        fill_time_ms=t_10_15,
        exit_time_ms=exit_t,
        funding_records=funding_10_08,
        fill_interval_start_ms=t_10_00,
        fill_interval_end_ms=t_10_15,
    )
    assert acct_15m.funding_status == FundingStatus.AMBIGUOUS_FILL_BOUNDARY.value
    assert acct_15m.funding_pnl_r is None
    assert acct_15m.funding_cash_total is None

    # 2. 1m touch:
    # touch interval: 10:07 -> 10:08, funding: 10:07:30
    # Expected: AMBIGUOUS_FILL_BOUNDARY
    funding_10_07_30 = [{"funding_time_ms": t_10_07_30, "funding_rate": 0.0001, "mark_price": 50000.0}]
    acct_1m = evaluate_tactical_funding_v1(
        direction="LONG",
        fill_price=50000.0,
        stop_loss=48000.0,
        fill_time_ms=t_10_08,
        exit_time_ms=exit_t,
        funding_records=funding_10_07_30,
        fill_interval_start_ms=t_10_07,
        fill_interval_end_ms=t_10_08,
    )
    assert acct_1m.funding_status == FundingStatus.AMBIGUOUS_FILL_BOUNDARY.value
    assert acct_1m.funding_pnl_r is None

    # 3. After interval:
    # touch interval ends: 10:08, funding: 10:09
    # Expected: SETTLED if position remains open
    funding_10_09 = [{"funding_time_ms": t_10_09, "funding_rate": 0.0001, "mark_price": 50500.0}]
    acct_after = evaluate_tactical_funding_v1(
        direction="LONG",
        fill_price=50000.0,
        stop_loss=48000.0,
        fill_time_ms=t_10_08,
        exit_time_ms=exit_t,
        funding_records=funding_10_09,
        fill_interval_start_ms=t_10_07,
        fill_interval_end_ms=t_10_08,
    )
    assert acct_after.funding_status == FundingStatus.COMPLETE.value
    assert acct_after.settlements_count == 1
    assert acct_after.settlements[0].status == "SETTLED"
    assert acct_after.funding_pnl_r is not None
    assert acct_after.funding_cash_total is not None

    # 4. Before interval:
    # funding: 10:06 (before 10:07 touch start)
    # Expected: skipped, not applicable
    funding_10_06 = [{"funding_time_ms": t_10_06, "funding_rate": 0.0001, "mark_price": 49900.0}]
    acct_before = evaluate_tactical_funding_v1(
        direction="LONG",
        fill_price=50000.0,
        stop_loss=48000.0,
        fill_time_ms=t_10_08,
        exit_time_ms=exit_t,
        funding_records=funding_10_06,
        fill_interval_start_ms=t_10_07,
        fill_interval_end_ms=t_10_08,
    )
    assert acct_before.funding_status == FundingStatus.COMPLETE.value
    assert acct_before.settlements_count == 0
    assert acct_before.funding_pnl_r == 0.0


def test_b2a_14_diagnostic_checkpoints_gap_handling() -> None:
    """Verify Section 36 diagnostic checkpoints continuous coverage and gap handling."""
    t0 = 1_700_000_000_000
    bar_len = 15 * 60 * 1000
    fill_p = 50000.0
    sl = 48000.0

    # 1. Complete continuous candles for 4h (16 bars)
    candles_4h = [
        Candle(
            symbol="BTCUSDT",
            interval="15m",
            open_time_ms=t0 + i * bar_len,
            close_time_ms=t0 + (i + 1) * bar_len,
            open=50000.0 + i * 10.0,
            high=50000.0 + i * 10.0 + 50.0,
            low=50000.0 + i * 10.0 - 20.0,
            close=50000.0 + (i + 1) * 10.0,
            volume=100.0,
        )
        for i in range(16)
    ]
    # Trade still active at 4h, exit at 6h
    exit_t = t0 + 24 * bar_len
    cps = compute_diagnostic_checkpoints(
        direction="LONG",
        fill_price=fill_p,
        stop_loss=sl,
        fill_time_ms=t0,
        exit_time_ms=exit_t,
        terminal_reason=None,
        candles_15m=candles_4h,
    )
    cp_4h = next(cp for cp in cps if cp.checkpoint_horizon_hours == 4)
    assert cp_4h.status == "OBSERVED"
    assert cp_4h.mark_price == 50000.0 + 16 * 10.0
    assert cp_4h.mark_to_market_gross_r is not None
    assert cp_4h.mfe_r_to_checkpoint is not None
    assert cp_4h.mae_r_to_checkpoint is not None

    # 2. Missing intermediate candle (gap at bar 8) -> INSUFFICIENT_COVERAGE
    candles_gap = [c for i, c in enumerate(candles_4h) if i != 8]
    cps_gap = compute_diagnostic_checkpoints(
        direction="LONG",
        fill_price=fill_p,
        stop_loss=sl,
        fill_time_ms=t0,
        exit_time_ms=exit_t,
        terminal_reason=None,
        candles_15m=candles_gap,
    )
    cp_4h_gap = next(cp for cp in cps_gap if cp.checkpoint_horizon_hours == 4)
    assert cp_4h_gap.status == "INSUFFICIENT_COVERAGE"
    assert cp_4h_gap.mark_price is None
    assert cp_4h_gap.mark_to_market_gross_r is None
    assert cp_4h_gap.mfe_r_to_checkpoint is None
    assert cp_4h_gap.mae_r_to_checkpoint is None

    # 3. Terminated before 8h checkpoint (e.g. exit at 2h with TP1)
    cps_term = compute_diagnostic_checkpoints(
        direction="LONG",
        fill_price=fill_p,
        stop_loss=sl,
        fill_time_ms=t0,
        exit_time_ms=t0 + 2 * 3600 * 1000,
        terminal_reason="TP1",
        candles_15m=candles_4h,
    )
    cp_8h = next(cp for cp in cps_term if cp.checkpoint_horizon_hours == 8)
    assert cp_8h.status == "TERMINATED_BEFORE_CHECKPOINT"
    assert cp_8h.barrier_status == "TERMINATED_TP1"
    assert cp_8h.mark_price is None


def test_b2a_15_playbook_profile_persistence_integration() -> None:
    """Verify SQLite persistence for all 5 playbooks under DIRECTIONAL_OUTCOME_PROFILE_V1 (Section 37)."""
    playbooks = [
        ("TREND_PULLBACK", 48, 43_200_000),
        ("BREAKOUT_RETEST", 48, 43_200_000),
        ("FAILED_BREAKOUT", 32, 28_800_000),
        ("FAILED_BREAKDOWN", 32, 28_800_000),
        ("VOLATILITY_EXPANSION", 32, 28_800_000),
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_profiles.db"
        store = MarketWatchStateStore(db_path)

        for pb, expected_bars, expected_ms in playbooks:
            rec_id = store.record_shadow_observation(
                timestamp_ms=1_700_000_000_000,
                symbol="BTCUSDT",
                snapshot_hash="snap123",
                agent_decision="LONG",
                agent_setup=pb,
                entry_quality="GOOD",
                reason_codes=["TEST"],
                reference_decision=None,
                reference_notes=None,
                policy_version="TACTICAL_POLICY_R2_B0",
                config_hash="cfg123",
                entry_price=50000.0,
                stop_loss=48000.0,
                tp1=53000.0,
                tp2=55000.0,
                direction="LONG",
                observation_type="ACTIONABLE_TRIGGERED",
                signal_identity=f"BTCUSDT:{pb}:LONG:100",
                setup_key=f"BTCUSDT:{pb}:50000.0",
                evidence_version=MARKET_WATCH_EVIDENCE_VERSION,
                entry_window_start_ms=1_700_000_000_000,
                signal_time_ms=1_700_000_000_000,
                entry_zone_low=49800.0,
                entry_zone_high=50200.0,
                entry_window_bars=4,
                entry_window_end_ms=1_700_000_000_000 + 4 * 900_000,
                fill_status="WAITING_FOR_FILL",
                evaluation_profile_version=DIRECTIONAL_OUTCOME_PROFILE_VERSION,
                evaluation_horizon_bars=expected_bars,
                evaluation_horizon_ms=expected_ms,
            )

            # Query row directly from SQLite
            with store._connect() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(
                    "SELECT evaluation_horizon_bars, evaluation_horizon_ms, evaluation_profile_version "
                    "FROM market_watch_shadow_records WHERE id = ?",
                    (rec_id,),
                )
                row = cur.fetchone()
                assert row is not None
                assert row["evaluation_horizon_bars"] == expected_bars
                assert row["evaluation_horizon_ms"] == expected_ms
                assert row["evaluation_profile_version"] == DIRECTIONAL_OUTCOME_PROFILE_VERSION
                assert row["evaluation_horizon_ms"] == row["evaluation_horizon_bars"] * 15 * 60 * 1000


def _make_playbook_evidence(playbook_str: str = "FAILED_BREAKOUT") -> TacticalFeatureEvidenceV2:
    """Helper to generate a valid TacticalFeatureEvidenceV2 for a non-default playbook."""
    ev, _ = build_sample_evidence_and_assessment()
    payload = dict(canonical_evidence_payload(ev))
    payload["selected_playbook"] = playbook_str
    payload["setup_key"] = f"SETUP:{ev.symbol}:{playbook_str}:50000.0"
    payload["signal_identity"] = f"SIG:{ev.symbol}:LONG:{playbook_str}:1700000000000"
    rp_dict = dict(payload["directional_risk_plan"])
    rp_dict["setup"] = playbook_str
    payload["directional_risk_plan"] = rp_dict

    cand_list = []
    for c in payload["playbook_candidates"]:
        c_dict = dict(c)
        if c_dict["playbook"] == "BREAKOUT_RETEST":
            c_dict["candidate_status"] = "ABSENT"
            c_dict["decision"] = "WAIT"
        elif c_dict["playbook"] == playbook_str:
            c_dict["candidate_status"] = "ACTIONABLE"
            c_dict["decision"] = "LONG"
            c_dict["entry_low"] = 49800.0
            c_dict["entry_high"] = 50200.0
            c_dict["stop_loss"] = 48000.0
            c_dict["take_profit_1"] = 53000.0
            c_dict["take_profit_2"] = 55000.0
        cand_list.append(c_dict)
    payload["playbook_candidates"] = cand_list

    new_id = compute_evidence_id(payload)
    payload["evidence_id"] = new_id
    return deserialize_tactical_feature_evidence(canonical_json_dump(payload), verify_identity=True)


def test_b2a_16_resolver_12h_profile() -> None:
    """Verify 12h profile (BREAKOUT_RETEST) remains PENDING at 4h and resolves TIMEOUT at 12h (Section 38)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_12h.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)

        ev, _ = build_sample_evidence_and_assessment()
        _insert_feature_evidence_in_db(store, ev)

        t0 = ev.decision_time_ms
        bar_len = 15 * 60 * 1000
        # Create shadow record waiting for fill
        rec_id = store.record_shadow_observation(
            timestamp_ms=t0,
            symbol=ev.symbol,
            snapshot_hash=ev.snapshot_hash,
            agent_decision="LONG",
            agent_setup="BREAKOUT_RETEST",
            entry_quality="GOOD",
            reason_codes=["TEST"],
            reference_decision=None,
            reference_notes=None,
            policy_version=ev.policy_version,
            config_hash=ev.config_hash,
            entry_price=50000.0,
            stop_loss=48000.0,
            tp1=53000.0,
            tp2=55000.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_identity=ev.signal_identity,
            setup_key=ev.setup_key,
            evidence_version=MARKET_WATCH_EVIDENCE_VERSION,
            entry_window_start_ms=t0,
            signal_time_ms=t0,
            entry_zone_low=49800.0,
            entry_zone_high=50200.0,
            entry_window_bars=4,
            entry_window_end_ms=t0 + 4 * bar_len,
            fill_status="WAITING_FOR_FILL",
            evaluation_profile_version=DIRECTIONAL_OUTCOME_PROFILE_VERSION,
            evaluation_horizon_bars=48,
            evaluation_horizon_ms=43_200_000,
            feature_evidence_id=ev.evidence_id,
        )

        # Bar 1 (0 to 1): touches entry zone -> fill at t0 + bar_len
        # Subsequent bars: stay between 49500 and 50500 (never hit SL 48000 or TP1 53000)
        total_bars_12h = 1 + 48  # fill bar + 48 outcome bars
        candles = [
            Candle(
                symbol="BTCUSDT",
                interval="15m",
                open_time_ms=t0 + i * bar_len,
                close_time_ms=t0 + (i + 1) * bar_len,
                open=50000.0,
                high=50200.0,
                low=49800.0 if i == 0 else 49500.0,
                close=50050.0,
                volume=100.0,
            )
            for i in range(total_bars_12h)
        ]

        client = MagicMock()
        client.klines.return_value = candles

        # Check at 4h after fill (16 bars after fill = 17 total bars)
        t_4h = t0 + 17 * bar_len
        client.klines.return_value = candles[:17]
        res_4h = mgr.resolve_pending_observations(client, current_time_ms=t_4h)
        assert res_4h["results"][0]["status"] == "PENDING_UNMATURED"
        rec_db_4h = store.get_shadow_record(rec_id)
        assert rec_db_4h is not None
        assert rec_db_4h["resolved"] == 0
        assert rec_db_4h["fill_status"] == "FILLED"

        # Check at 12h after fill (48 bars after fill = 49 total bars)
        t_12h = t0 + total_bars_12h * bar_len
        client.klines.return_value = candles
        res_12h = mgr.resolve_pending_observations(client, current_time_ms=t_12h)
        assert res_12h["resolved_count"] == 1
        assert res_12h["results"][0]["status"] == "RESOLVED"
        assert res_12h["results"][0]["outcome"]["terminal_reason"] == "TIMEOUT"

        # Check persisted B2A evaluation
        eval_saved = store.get_shadow_evaluation_by_shadow_id(rec_id)
        assert eval_saved is not None
        assert eval_saved.terminal_reason == "TIMEOUT"
        assert eval_saved.evaluation_horizon_bars == 48
        assert eval_saved.evaluation_horizon_ms == 43_200_000
        assert eval_saved.exit_time_ms == eval_saved.fill_time_ms + 43_200_000


def test_b2a_17_resolver_8h_profile() -> None:
    """Verify 8h profile (FAILED_BREAKOUT) remains PENDING at 4h and resolves TIMEOUT at 8h (Section 39)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_8h.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)

        ev = _make_playbook_evidence("FAILED_BREAKOUT")
        _insert_feature_evidence_in_db(store, ev)

        t0 = ev.decision_time_ms
        bar_len = 15 * 60 * 1000
        rec_id = store.record_shadow_observation(
            timestamp_ms=t0,
            symbol=ev.symbol,
            snapshot_hash=ev.snapshot_hash,
            agent_decision="LONG",
            agent_setup="FAILED_BREAKOUT",
            entry_quality="GOOD",
            reason_codes=["TEST"],
            reference_decision=None,
            reference_notes=None,
            policy_version=ev.policy_version,
            config_hash=ev.config_hash,
            entry_price=50000.0,
            stop_loss=48000.0,
            tp1=53000.0,
            tp2=55000.0,
            direction="LONG",
            observation_type="ACTIONABLE_TRIGGERED",
            signal_identity=ev.signal_identity,
            setup_key=ev.setup_key,
            evidence_version=MARKET_WATCH_EVIDENCE_VERSION,
            entry_window_start_ms=t0,
            signal_time_ms=t0,
            entry_zone_low=49800.0,
            entry_zone_high=50200.0,
            entry_window_bars=4,
            entry_window_end_ms=t0 + 4 * bar_len,
            fill_status="WAITING_FOR_FILL",
            evaluation_profile_version=DIRECTIONAL_OUTCOME_PROFILE_VERSION,
            evaluation_horizon_bars=32,
            evaluation_horizon_ms=28_800_000,
            feature_evidence_id=ev.evidence_id,
        )

        total_bars_8h = 1 + 32  # fill bar + 32 outcome bars
        candles = [
            Candle(
                symbol="BTCUSDT",
                interval="15m",
                open_time_ms=t0 + i * bar_len,
                close_time_ms=t0 + (i + 1) * bar_len,
                open=50000.0,
                high=50200.0,
                low=49800.0 if i == 0 else 49500.0,
                close=50050.0,
                volume=100.0,
            )
            for i in range(total_bars_8h)
        ]

        client = MagicMock()

        # Check at 4h after fill (16 bars after fill = 17 total bars)
        t_4h = t0 + 17 * bar_len
        client.klines.return_value = candles[:17]
        res_4h = mgr.resolve_pending_observations(client, current_time_ms=t_4h)
        assert res_4h["results"][0]["status"] == "PENDING_UNMATURED"

        # Check at 8h after fill (32 bars after fill = 33 total bars)
        t_8h = t0 + total_bars_8h * bar_len
        client.klines.return_value = candles
        res_8h = mgr.resolve_pending_observations(client, current_time_ms=t_8h)
        assert res_8h["resolved_count"] == 1
        assert res_8h["results"][0]["status"] == "RESOLVED"
        assert res_8h["results"][0]["outcome"]["terminal_reason"] == "TIMEOUT"

        # Check persisted B2A evaluation
        eval_saved = store.get_shadow_evaluation_by_shadow_id(rec_id)
        assert eval_saved is not None
        assert eval_saved.terminal_reason == "TIMEOUT"
        assert eval_saved.evaluation_horizon_bars == 32
        assert eval_saved.evaluation_horizon_ms == 28_800_000
        assert eval_saved.exit_time_ms == eval_saved.fill_time_ms + 28_800_000


def test_b2a_18_legacy_b1_shadow_isolation() -> None:
    """Verify legacy B1 shadow records without B2A profile are PRE_B2A_HORIZON and never materialize B2A evaluation (Section 12, 13, 40)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_legacy.db"
        store = MarketWatchStateStore(db_path)
        mgr = ShadowEvaluationManager(store=store)

        ev, _ = build_sample_evidence_and_assessment()
        _insert_feature_evidence_in_db(store, ev)

        t0 = ev.decision_time_ms
        # Insert legacy shadow row with evaluation_profile_version = None, horizon_ms = None, horizon_bars = 16
        with store._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_watch_shadow_records (
                    id, timestamp_ms, symbol, snapshot_hash, policy_version, config_hash,
                    agent_decision, agent_setup, entry_quality, reason_codes_json,
                    entry_price, stop_loss, tp1, tp2, direction, future_mfe, future_mae,
                    tp1_hit, tp2_hit, sl_hit, net_r, gross_r, friction_r, regime_after,
                    resolved, evaluation_horizon_bars, evaluation_end_ms, observation_type,
                    signal_identity, signal_time_ms, entry_zone_low, entry_zone_high,
                    entry_window_bars, entry_window_end_ms, fill_status, fill_time_ms,
                    setup_key, evidence_version, terminal_reason, exit_time_ms, exit_price,
                    coverage_status, feature_evidence_id, evaluation_profile_version, evaluation_horizon_ms
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    99, t0, ev.symbol, ev.snapshot_hash, ev.policy_version, ev.config_hash,
                    "LONG", ev.selected_playbook, "GOOD", "[]",
                    50000.0, 48000.0, 53000.0, 55000.0, "LONG", 1.5, -0.2,
                    1, 0, 0, 1.45, 1.5, 0.05, "RESOLVED_TERMINAL",
                    1, 16, t0 + 16 * 900_000, "ACTIONABLE_TRIGGERED",
                    ev.signal_identity, t0, 49800.0, 50200.0,
                    4, t0 + 4 * 900_000, "FILLED", t0 + 900_000,
                    ev.setup_key, MARKET_WATCH_EVIDENCE_VERSION, "TP1", t0 + 4 * 3600_000, 53000.0,
                    "COMPLETE", ev.evidence_id, None, None,
                ),
            )
            conn.commit()

        # Materialization must return None for legacy record
        res = mgr._materialize_and_save_shadow_evaluation(99)
        assert res is None

        # Verify no row inserted into tactical_shadow_evaluations_v2
        with store._connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM tactical_shadow_evaluations_v2 WHERE shadow_record_id = 99")
            assert cur.fetchone()[0] == 0


def test_b2a_19_persistence_authority_linkage_checks() -> None:
    """Verify save_shadow_evaluation enforces database linkage and fails closed (Section 26 & 41)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_linkage.db"
        store = MarketWatchStateStore(db_path)

        ev, _ = build_sample_evidence_and_assessment()
        rec = _create_mock_shadow_record(ev, shadow_id=50)
        evaluation = build_tactical_shadow_evaluation_v2(rec, ev)

        # 1. Missing feature evidence in DB -> raises TacticalEvidenceLinkageError
        with pytest.raises(TacticalEvidenceLinkageError, match="Linked feature_evidence_id does not exist"):
            store.save_shadow_evaluation(evaluation)

        # Insert feature evidence
        _insert_feature_evidence_in_db(store, ev)

        # 2. Missing shadow record in DB -> raises TacticalShadowEvaluationValidationError
        with pytest.raises(TacticalShadowEvaluationValidationError, match="Linked shadow_record_id does not exist"):
            store.save_shadow_evaluation(evaluation)

        # 3. Unresolved shadow record -> raises TacticalShadowEvaluationValidationError
        rec_unresolved = dict(rec)
        rec_unresolved["resolved"] = 0
        _insert_shadow_record_in_db(store, rec_unresolved)
        with pytest.raises(TacticalShadowEvaluationValidationError, match="is unresolved"):
            store.save_shadow_evaluation(evaluation)

        # Update shadow record to resolved = 1
        with store._connect() as conn:
            conn.execute("UPDATE market_watch_shadow_records SET resolved = 1 WHERE id = 50")
            conn.commit()

        # 4. Linkage mismatch (different feature_evidence_id in shadow) -> raises TacticalShadowAttributionConflictError
        with store._connect() as conn:
            conn.execute("UPDATE market_watch_shadow_records SET feature_evidence_id = 'different_id' WHERE id = 50")
            conn.commit()
        with pytest.raises((TacticalEvidenceLinkageError, TacticalShadowAttributionConflictError), match="Linkage mismatch"):
            store.save_shadow_evaluation(evaluation)

        # Fix feature_evidence_id
        with store._connect() as conn:
            conn.execute("UPDATE market_watch_shadow_records SET feature_evidence_id = ? WHERE id = 50", (ev.evidence_id,))
            conn.commit()

        # 5. Profile mismatch in shadow record -> raises TacticalShadowProfileConflictError
        with store._connect() as conn:
            conn.execute("UPDATE market_watch_shadow_records SET evaluation_profile_version = 'PRE_B2A_LEGACY' WHERE id = 50")
            conn.commit()
        with pytest.raises(TacticalShadowProfileConflictError, match="Profile mismatch"):
            store.save_shadow_evaluation(evaluation)

        # Fix profile version -> save succeeds
        with store._connect() as conn:
            conn.execute("UPDATE market_watch_shadow_records SET evaluation_profile_version = ? WHERE id = 50", (DIRECTIONAL_OUTCOME_PROFILE_VERSION,))
            conn.commit()
        saved_id = store.save_shadow_evaluation(evaluation)
        assert saved_id == evaluation.evaluation_id


def test_b2a_20_self_consistent_semantic_corruption() -> None:
    """Verify self-consistent semantic corruption (e.g. invalid horizon arithmetic or profile mismatch) fails closed (Section 9, 29, 42)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_corruption.db"
        store = MarketWatchStateStore(db_path)

        ev, _ = build_sample_evidence_and_assessment()
        _insert_feature_evidence_in_db(store, ev)
        rec = _create_mock_shadow_record(ev, shadow_id=60)
        _insert_shadow_record_in_db(store, rec)

        valid_eval = build_tactical_shadow_evaluation_v2(rec, ev)

        # 1. Horizon invariant violation: bars * 900_000 != ms
        corrupted_payload = dict(valid_eval.to_canonical_payload())
        corrupted_payload["evaluation_horizon_bars"] = 16  # 16 * 900_000 = 14_400_000 != 43_200_000
        corr_json = canonical_json_dump(corrupted_payload)

        # Deserializing with verify_identity=True must reject invalid horizon arithmetic
        with pytest.raises(TacticalShadowEvaluationValidationError, match="Horizon invariant violated"):
            deserialize_tactical_shadow_evaluation(corr_json, verify_identity=True)

        # 2. Corrupted profile mapping (e.g. 32 bars for BREAKOUT_RETEST which requires 48 bars)
        corrupted_payload2 = dict(valid_eval.to_canonical_payload())
        corrupted_payload2["evaluation_horizon_bars"] = 32
        corrupted_payload2["evaluation_horizon_ms"] = 32 * 900_000
        corr_json2 = canonical_json_dump(corrupted_payload2)
        with pytest.raises(TacticalShadowEvaluationValidationError, match="does not match playbook"):
            deserialize_tactical_shadow_evaluation(corr_json2, verify_identity=True)
