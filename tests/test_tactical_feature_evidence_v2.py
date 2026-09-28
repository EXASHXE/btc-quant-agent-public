from __future__ import annotations

import dataclasses
import math
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Self
from unittest.mock import MagicMock

import pytest

from btc_quant_agent.domain import Candle, Regime
from btc_quant_agent.market_watch.config import (
    MarketWatchConfig,
    compute_market_watch_config_hash,
    compute_market_watch_config_hash_from_payload,
)
from btc_quant_agent.market_watch.domain import (
    ACTIVE_PLAYBOOKS,
    RESERVED_INACTIVE_PLAYBOOKS,
    TACTICAL_POLICY_VERSION,
    BenchmarkContext,
    CandidateStatus,
    DerivativesMetrics,
    DerivativesRegime,
    DirectionalDecision,
    DirectionalPlan,
    EntryQuality,
    ExhaustionMetrics,
    ExhaustionState,
    GridDecision,
    GridPlan,
    MarketSnapshot,
    PlaybookCandidate,
    PlaybookType,
    PriceMetrics,
    ScanHealth,
    SignalLifecycleState,
    SymbolAssessment,
    TacticalSemanticIdentity,
    TimeframeSnapshot,
)
from btc_quant_agent.market_watch.evidence import (
    ClosedBarEvidence,
    DecisionConfigEvidence,
    PolicyDecisionTrace,
    PolicyGateStageTrace,
    TacticalCausalityError,
    TacticalEvidenceConflictError,
    TacticalEvidenceIdentityError,
    TacticalEvidenceLinkageError,
    TacticalEvidenceValidationError,
    TacticalFeatureEvidenceV2,
    build_tactical_feature_evidence,
    canonical_evidence_json,
    canonical_evidence_payload,
    canonical_json_dump,
    compute_evidence_id,
    deserialize_tactical_feature_evidence,
    validate_tactical_feature_evidence,
    verify_tactical_evidence_identity,
)
from btc_quant_agent.market_watch.ranking import (
    calculate_rule_score,
    calculate_rule_score_breakdown,
)
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from btc_quant_agent.market_watch.snapshot import (
    ReturnObservation,
)
from btc_quant_agent.market_watch.state import (
    MarketWatchStateStore,
)

# ==============================================================================
# Helpers and Fixtures
# ==============================================================================

def make_test_candles(
    symbol: str = "BTCUSDT",
    interval: str = "15m",
    count: int = 60,
    base_price: float = 50000.0,
    step_ms: int = 900_000,
    end_ms: int = 1_700_000_000_000,
) -> list[Candle]:
    start_ms = end_ms - count * step_ms
    candles = []
    price = base_price
    for i in range(count):
        o_t = start_ms + i * step_ms
        c_t = o_t + step_ms - 1
        open_p = price
        close_p = price + (20.0 if i % 2 == 0 else -10.0)
        high_p = max(open_p, close_p) + 30.0
        low_p = min(open_p, close_p) - 30.0
        candles.append(
            Candle(
                symbol=symbol,
                interval=interval,
                open_time_ms=o_t,
                close_time_ms=c_t,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=100.0 + i,
                quote_volume=(100.0 + i) * close_p,
            )
        )
        price = close_p
    return candles


def make_dummy_timeframe(
    symbol: str = "BTCUSDT",
    interval: str = "15m",
    close: float = 50000.0,
    watermark_ms: int = 1_700_000_000_000,
) -> TimeframeSnapshot:
    closed = Candle(
        symbol=symbol,
        interval=interval,
        open_time_ms=watermark_ms - 900_000,
        close_time_ms=watermark_ms,
        open=close - 10.0,
        high=close + 20.0,
        low=close - 20.0,
        close=close,
        volume=5000.0,
        quote_volume=5000.0 * close,
    )
    return TimeframeSnapshot(
        interval=interval,
        latest_bar=closed,
        latest_closed_bar=closed,
        closed_bar_end_time_ms=watermark_ms,
        close=close,
        ema_fast=50100.0,
        ema_mid=49900.0,
        ema_fast_slope=0.001,
        ema_mid_slope=0.0005,
        atr=250.0,
        atr_percentile=0.5,
        adx=30.0,
        rsi=55.0,
        roc=0.01,
        volume=5000.0,
        volume_z=1.2,
        bb_width=0.04,
        bb_width_percentile=0.4,
        recent_swing_high=51000.0,
        recent_swing_low=49000.0,
        supports=(49000.0,),
        resistances=(51000.0,),
        structure="HH_HL",
        regime=Regime.TREND_UP,
        is_volatility_compressed=False,
        is_volatility_expanded=False,
        ema_slow=49500.0,
        ema_slow_status="AVAILABLE",
    )


def build_sample_evidence_and_assessment(
    symbol: str = "BTCUSDT",
    decision_time_ms: int = 1_700_000_100_000,
    config: MarketWatchConfig | None = None,
) -> tuple[TacticalFeatureEvidenceV2, SymbolAssessment]:
    cfg = config or MarketWatchConfig()
    watermark_ms = 1_700_000_000_000
    tf_15m = make_dummy_timeframe("15m", 50000.0, watermark_ms)
    tf_1h = make_dummy_timeframe("1h", 50000.0, watermark_ms)
    tf_4h = make_dummy_timeframe("4h", 50000.0, watermark_ms)

    ret_1h = ReturnObservation(
        horizon_ms=3_600_000,
        value=0.005,
        availability="AVAILABLE",
        anchor_close_time_ms=watermark_ms - 3_600_000,
        latest_close_time_ms=watermark_ms,
    )
    ret_4h = ReturnObservation(
        horizon_ms=14_400_000,
        value=0.012,
        availability="AVAILABLE",
        anchor_close_time_ms=watermark_ms - 14_400_000,
        latest_close_time_ms=watermark_ms,
    )
    ret_12h = ReturnObservation(
        horizon_ms=43_200_000,
        value=0.025,
        availability="AVAILABLE",
        anchor_close_time_ms=watermark_ms - 43_200_000,
        latest_close_time_ms=watermark_ms,
    )

    deriv_metrics = DerivativesMetrics(
        mark_price=50005.0,
        index_price=50000.0,
        funding_rate=0.0001,
        funding_time_ms=watermark_ms - 1000,
        current_open_interest=50000.0,
        open_interest_time_ms=watermark_ms - 2000,
        oi_1h_change=0.02,
        oi_4h_change=0.05,
        oi_12h_change=0.08,
        global_account_long_short_ratio=1.1,
        long_short_time_ms=watermark_ms - 3000,
        top_trader_position_ratio=1.2,
        top_trader_account_ratio=1.15,
        taker_buy_sell_ratio=1.05,
        taker_time_ms=watermark_ms - 4000,
        basis_rate=0.0001,
        basis_bps=1.0,
        basis_time_ms=watermark_ms - 5000,
        spread_bps=1.2,
        order_book_imbalance=0.1,
        field_availability={"mark_price": True, "funding_rate": True},
        endpoint_errors={},
    )

    price_metrics = PriceMetrics(
        last_price=50000.0,
        mark_price=50005.0,
        change_24h_pct=0.03,
        high_24h=51000.0,
        low_24h=49000.0,
        quote_volume_24h=1_000_000_000.0,
    )

    snapshot = MarketSnapshot(
        symbol=symbol,
        decision_time_ms=decision_time_ms,
        observed_at_ms=watermark_ms + 10_000,
        exchange_time_ms=watermark_ms + 10_000,
        tf_15m=tf_15m,
        tf_1h=tf_1h,
        tf_4h=tf_4h,
        derivatives=deriv_metrics,
        price=price_metrics,
        snapshot_hash="dummy_snap_hash_12345",
        health=ScanHealth.OK,
        health_reasons=(),
        collection_started_at_ms=watermark_ms + 5_000,
        collection_completed_at_ms=watermark_ms + 15_000,
        closed_bar_watermarks={
            "15m": watermark_ms,
            "1h": watermark_ms,
            "4h": watermark_ms,
        },
        source_receipt_timestamps={
            "derivatives_observed_at_ms": watermark_ms + 8_000,
            "ticker_receipt_ms": watermark_ms + 9_000,
            "oi_hist_receipt_ms": watermark_ms + 9_500,
            "top_pos_receipt_ms": watermark_ms + 9_600,
            "top_acc_receipt_ms": watermark_ms + 9_700,
            "server_time_receipt_ms": watermark_ms + 9_800,
        },
        return_observations=(ret_1h, ret_4h, ret_12h),
    )

    exhaustion = ExhaustionMetrics(state=ExhaustionState.NORMAL, reasons=())

    rule_breakdown = calculate_rule_score_breakdown(
        decision=DirectionalDecision.LONG,
        tf_1h=tf_1h,
        tf_15m=tf_15m,
        entry_quality=EntryQuality.EXCELLENT,
        derivatives=deriv_metrics,
        exhaustion=exhaustion,
        relative_perf=None,
        benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
        net_rr=1.45,
        has_fatal_veto=False,
        config=cfg,
    )

    directional_plan = DirectionalPlan(
        symbol=symbol,
        decision=DirectionalDecision.LONG,
        setup=PlaybookType.BREAKOUT_RETEST,
        regime=Regime.TREND_UP,
        entry_quality=EntryQuality.EXCELLENT,
        entry_low=49800.0,
        entry_high=50200.0,
        stop_loss=48000.0,
        take_profit_1=53000.0,
        take_profit_2=55000.0,
        invalidation_level=48000.0,
        gross_rr=1.5,
        net_rr=1.45,
        opportunity_score=rule_breakdown.final_rule_score,
        rule_score=rule_breakdown.final_rule_score,
        derivatives_regime=DerivativesRegime.NEUTRAL,
        benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
        reason_codes=("CONFIRMED_PLAYBOOK_CANDIDATE", "FAVORABLE_STRUCTURE"),
        risk_codes=(),
    )

    grid_plan = GridPlan(
        symbol=symbol,
        decision=GridDecision.PAUSE,
    )

    exhaustion = ExhaustionMetrics(state=ExhaustionState.NORMAL, reasons=())

    cand = PlaybookCandidate(
        playbook=PlaybookType.BREAKOUT_RETEST,
        candidate_status=CandidateStatus.ACTIONABLE,
        decision=DirectionalDecision.LONG,
        entry_low=49800.0,
        entry_high=50200.0,
        stop_loss=48000.0,
        take_profit_1=53000.0,
        take_profit_2=55000.0,
        structural_anchor_id=None,
        reason_codes=("Valid breakout",),
        risk_codes=(),
        setup_creation_bar_end_ms=watermark_ms,
        invalidation=48000.0,
    )

    t_eq = PolicyGateStageTrace(
        stage_name="entry_quality_gate",
        input_decision="LONG",
        output_decision="LONG",
    )
    t_bg = PolicyGateStageTrace(
        stage_name="benchmark_gate",
        input_decision="LONG",
        output_decision="LONG",
    )
    t_dg = PolicyGateStageTrace(
        stage_name="derivatives_gate",
        input_decision="LONG",
        output_decision="LONG",
    )
    t_fv = PolicyGateStageTrace(
        stage_name="fatal_veto_gate",
        input_decision="LONG",
        output_decision="LONG",
        veto_flag=False,
    )
    decision_trace = PolicyDecisionTrace(
        selected_candidate_decision="LONG",
        after_entry_quality_gate=t_eq,
        after_benchmark_gate=t_bg,
        after_derivatives_gate=t_dg,
        after_fatal_veto=t_fv,
        final_directional_decision="LONG",
    )

    cfg_hash = compute_market_watch_config_hash(cfg)
    sem_id = TacticalSemanticIdentity(
        tactical_policy_version=TACTICAL_POLICY_VERSION,
        config_hash=cfg_hash,
    )

    temp_assessment = SymbolAssessment(
        symbol=symbol,
        snapshot=snapshot,
        directional=directional_plan,
        grid=grid_plan,
        opportunity_score=rule_breakdown.final_rule_score,
        rule_score=rule_breakdown.final_rule_score,
        relative_performance=None,
        exhaustion=exhaustion,
        rank=0,
        veto_reasons=(),
        alert_fingerprint="",
        lifecycle_state=SignalLifecycleState.CANDIDATE,
        policy_version=TACTICAL_POLICY_VERSION,
        config_hash=cfg_hash,
        signal_identity=f"SIG:{symbol}:LONG:BREAKOUT_RETEST:{watermark_ms}",
        setup_key=f"SETUP:{symbol}:BREAKOUT_RETEST:50000.0",
        eligible_playbooks=(PlaybookType.BREAKOUT_RETEST.value,),
        actionable_playbooks=(PlaybookType.BREAKOUT_RETEST.value,),
        selected_playbook=PlaybookType.BREAKOUT_RETEST.value,
        reference_universe_status="UNIVERSE_COMPLETE",
        missing_reference_members=(),
        semantic_identity=sem_id,
    )

    evidence = build_tactical_feature_evidence(
        assessment=temp_assessment,
        playbook_candidates=[cand],
        decision_trace=decision_trace,
        rule_score_breakdown=rule_breakdown,
        config=cfg,
    )

    assessment = dataclasses.replace(
        temp_assessment,
        feature_evidence_id=evidence.evidence_id,
        feature_evidence=evidence,
    )

    return evidence, assessment


# ==============================================================================
# B1-01: Determinism
# ==============================================================================

def test_b1_01_evidence_determinism_same_inputs() -> None:
    """B1-01: Identical inputs produce identical evidence_id and canonical json."""
    ev1, _ = build_sample_evidence_and_assessment(symbol="BTCUSDT", decision_time_ms=1_700_000_100_000)
    ev2, _ = build_sample_evidence_and_assessment(symbol="BTCUSDT", decision_time_ms=1_700_000_100_000)

    assert ev1.evidence_id == ev2.evidence_id
    assert len(ev1.evidence_id) == 64
    assert all(c in "0123456789abcdef" for c in ev1.evidence_id)

    json1 = canonical_json_dump(canonical_evidence_payload(ev1))
    json2 = canonical_json_dump(canonical_evidence_payload(ev2))
    assert json1 == json2


def test_b1_01_evidence_determinism_cross_process() -> None:
    """B1-01: Independent Python process produces identical evidence_id."""
    script = """
import sys
from btc_quant_agent.market_watch.config import MarketWatchConfig
from tests.test_tactical_feature_evidence_v2 import build_sample_evidence_and_assessment

ev, _ = build_sample_evidence_and_assessment("BTCUSDT", 1_700_000_100_000)
print(ev.evidence_id)
"""
    ev_local, _ = build_sample_evidence_and_assessment("BTCUSDT", 1_700_000_100_000)
    res = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=True)
    out_id = res.stdout.strip()
    assert out_id == ev_local.evidence_id


# ==============================================================================
# B1-02: Map Ordering Invariance
# ==============================================================================

def test_b1_02_map_ordering_invariance() -> None:
    """B1-02: Varying dict key order produces identical canonical JSON and hash."""
    d1 = {"z_key": 1, "a_key": 2, "nested": {"beta": 10, "alpha": 20}}
    d2 = {"nested": {"alpha": 20, "beta": 10}, "a_key": 2, "z_key": 1}

    dump1 = canonical_json_dump(d1)
    dump2 = canonical_json_dump(d2)
    assert dump1 == dump2

    ev, _ = build_sample_evidence_and_assessment()
    payload = canonical_evidence_payload(ev)
    # Shuffle top level keys
    shuffled_payload = {k: payload[k] for k in reversed(list(payload.keys()))}
    assert canonical_json_dump(payload) == canonical_json_dump(shuffled_payload)


# ==============================================================================
# B1-03: Feature Sensitivity
# ==============================================================================

def test_b1_03_feature_sensitivity_modifications() -> None:
    """B1-03: Mutating any input component alters evidence_id."""
    base_ev, _ = build_sample_evidence_and_assessment()
    base_id = base_ev.evidence_id

    # 1. Mutate decision_time_ms
    ev_time, _ = build_sample_evidence_and_assessment(decision_time_ms=base_ev.decision_time_ms + 1000)
    assert ev_time.evidence_id != base_id

    # 2. Mutate symbol
    ev_sym, _ = build_sample_evidence_and_assessment(symbol="ETHUSDT")
    assert ev_sym.evidence_id != base_id

    # 3. Mutate config
    cfg_mod = MarketWatchConfig(min_net_rr=2.5)
    ev_cfg, _ = build_sample_evidence_and_assessment(config=cfg_mod)
    assert ev_cfg.evidence_id != base_id

    # 4. Mutate rule score breakdown component
    ev_rule = dataclasses.replace(
        base_ev,
        rule_score_breakdown=dataclasses.replace(base_ev.rule_score_breakdown, final_rule_score=50.0),
    )
    new_rule_id = compute_evidence_id(ev_rule)
    assert new_rule_id != base_id

    # 5. Mutate watermark in source provenance
    ev_prov = dataclasses.replace(
        base_ev,
        source_provenance=dataclasses.replace(
            base_ev.source_provenance,
            closed_bar_watermark_15m=base_ev.source_provenance.closed_bar_watermark_15m - 900_000,
        ),
    )
    assert compute_evidence_id(ev_prov) != base_id

    # 6. Mutate derivatives feature
    ev_deriv = dataclasses.replace(
        base_ev,
        market_snapshot_features=dataclasses.replace(
            base_ev.market_snapshot_features,
            derivatives=dataclasses.replace(
                base_ev.market_snapshot_features.derivatives,
                funding_rate=0.0005,
            ),
        ),
    )
    assert compute_evidence_id(ev_deriv) != base_id

    # 7. Mutate gate decision trace
    ev_trace = dataclasses.replace(
        base_ev,
        decision_trace=dataclasses.replace(
            base_ev.decision_trace,
            final_directional_decision="WAIT",
        ),
    )
    assert compute_evidence_id(ev_trace) != base_id


# ==============================================================================
# B1-04: Persistence Timestamp Independence
# ==============================================================================

def test_b1_04_persistence_timestamp_independence() -> None:
    """B1-04: Persisting at different times does not change evidence_id or canonical payload."""
    ev, assessment = build_sample_evidence_and_assessment()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_store.db"
        store = MarketWatchStateStore(db_path)

        # Save with evidence
        store.save_symbol_state(
            symbol=ev.symbol,
            assessment=assessment,
            now_ms=1_700_000_500_000,
            alert_sent=False,
            evidence=ev,
        )

        retrieved = store.get_tactical_feature_evidence(ev.evidence_id)
        assert retrieved is not None
        assert retrieved.evidence_id == ev.evidence_id
        assert canonical_json_dump(canonical_evidence_payload(retrieved)) == canonical_json_dump(canonical_evidence_payload(ev))

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT persisted_at_ms, evidence_json FROM tactical_feature_evidence_v2 WHERE evidence_id = ?",
                (ev.evidence_id,),
            ).fetchone()
            assert row is not None
            assert row[0] == 1_700_000_500_000
            assert row[1] == canonical_evidence_json(ev)

        # Now simulate persistence at a different time under another ID or retrieval
        deserialized = deserialize_tactical_feature_evidence(row[1])
        assert deserialized.evidence_id == ev.evidence_id


# ==============================================================================
# B1-05: Non-Finite Float Rejection
# ==============================================================================

def test_b1_05_non_finite_float_rejection() -> None:
    """B1-05: NaN, +Inf, -Inf anywhere raises TacticalEvidenceValidationError."""
    base_ev, _ = build_sample_evidence_and_assessment()

    # NaN in rule score breakdown
    ev_nan = dataclasses.replace(
        base_ev,
        rule_score_breakdown=dataclasses.replace(
            base_ev.rule_score_breakdown,
            final_rule_score=float("nan"),
        ),
    )
    with pytest.raises(TacticalEvidenceValidationError, match="Invalid non-finite number"):
        validate_tactical_feature_evidence(ev_nan)

    # Inf in derivatives features
    ev_inf = dataclasses.replace(
        base_ev,
        market_snapshot_features=dataclasses.replace(
            base_ev.market_snapshot_features,
            derivatives=dataclasses.replace(
                base_ev.market_snapshot_features.derivatives,
                funding_rate=float("inf"),
            ),
        ),
    )
    with pytest.raises(TacticalEvidenceValidationError, match="Invalid non-finite number"):
        validate_tactical_feature_evidence(ev_inf)

    # -Inf in timeframe features
    ev_ninf = dataclasses.replace(
        base_ev,
        market_snapshot_features=dataclasses.replace(
            base_ev.market_snapshot_features,
            tf_15m=dataclasses.replace(base_ev.market_snapshot_features.tf_15m, rsi=float("-inf")),
        ),
    )
    with pytest.raises(TacticalEvidenceValidationError, match="Invalid non-finite number"):
        validate_tactical_feature_evidence(ev_ninf)


# ==============================================================================
# B1-06: Causality Violation Rejection
# ==============================================================================

def test_b1_06_causality_violation_rejection() -> None:
    """B1-06: Closed-bar watermark or receipts after decision_time_ms raises TacticalCausalityError."""
    base_ev, _ = build_sample_evidence_and_assessment()
    dec_t = base_ev.decision_time_ms

    # 1. 15m watermark > decision_time_ms
    ev_wm = dataclasses.replace(
        base_ev,
        source_provenance=dataclasses.replace(
            base_ev.source_provenance,
            closed_bar_watermark_15m=dec_t + 100,
        ),
    )
    with pytest.raises(TacticalCausalityError, match="15m closed-bar watermark"):
        validate_tactical_feature_evidence(ev_wm)

    # 2. 1h watermark > decision_time_ms
    ev_wm1h = dataclasses.replace(
        base_ev,
        source_provenance=dataclasses.replace(
            base_ev.source_provenance,
            closed_bar_watermark_1h=dec_t + 100,
        ),
    )
    with pytest.raises(TacticalCausalityError, match="1h closed-bar watermark"):
        validate_tactical_feature_evidence(ev_wm1h)

    # 3. Return latest close time > decision_time_ms
    bad_ret = dataclasses.replace(
        base_ev.source_provenance.returns[0],
        latest_close_time_ms=dec_t + 500,
    )
    ev_ret = dataclasses.replace(
        base_ev,
        source_provenance=dataclasses.replace(
            base_ev.source_provenance,
            returns=(bad_ret, base_ev.source_provenance.returns[1], base_ev.source_provenance.returns[2]),
        ),
    )
    with pytest.raises(TacticalCausalityError, match="latest close time"):
        validate_tactical_feature_evidence(ev_ret)

    # 4. Receipt timestamp > decision_time_ms
    ev_receipt = dataclasses.replace(
        base_ev,
        source_provenance=dataclasses.replace(
            base_ev.source_provenance,
            ticker_receipt_ms=dec_t + 10,
        ),
    )
    with pytest.raises(TacticalCausalityError, match="Receipt timestamp ticker_receipt_ms"):
        validate_tactical_feature_evidence(ev_receipt)

    # 5. collection_started_at_ms > collection_completed_at_ms
    ev_coll = dataclasses.replace(
        base_ev,
        collection_started_at_ms=base_ev.collection_completed_at_ms + 10,
    )
    with pytest.raises(TacticalCausalityError, match="collection_started_at_ms"):
        validate_tactical_feature_evidence(ev_coll)

    # 6. observed_at_ms > decision_time_ms
    ev_obs = dataclasses.replace(
        base_ev,
        observed_at_ms=dec_t + 100,
    )
    with pytest.raises(TacticalCausalityError, match="observed_at_ms"):
        validate_tactical_feature_evidence(ev_obs)


# ==============================================================================
# B1-07: Population Coverage & Candidate Completeness
# ==============================================================================

def test_b1_07_population_coverage_and_candidates() -> None:
    """B1-07: Evidence persisted for WAIT/NO_TRADE, candidates contain all 5 playbooks and NO RANGE_MEAN_REVERSION."""
    base_ev, _ = build_sample_evidence_and_assessment()

    # Verify all 5 active playbooks present in candidate evidence
    candidate_types = [c.playbook for c in base_ev.playbook_candidates]
    for p in ACTIVE_PLAYBOOKS:
        assert p.value in candidate_types

    # Registry order verification
    expected_order = [p.value for p in ACTIVE_PLAYBOOKS]
    assert candidate_types == expected_order

    # Verify RANGE_MEAN_REVERSION is strictly absent
    for reserved in RESERVED_INACTIVE_PLAYBOOKS:
        assert reserved.value not in candidate_types

    # Verify WAIT / NO_TRADE population coverage in scanner
    client = MagicMock()
    now_ms = 1_700_000_100_000
    client.server_time_ms.return_value = now_ms
    client.klines.return_value = make_test_candles(count=50, end_ms=1_700_000_000_000)
    client.collect_derivatives.return_value = MagicMock(
        snapshot=MagicMock(
            mark_price=50000.0,
            index_price=50000.0,
            funding_rate=0.0001,
            funding_time_ms=now_ms - 1000,
            open_interest=50000.0,
            open_interest_time_ms=now_ms - 2000,
            open_interest_change_pct=0.01,
            taker_buy_sell_ratio=1.0,
            taker_time_ms=now_ms - 3000,
            basis_rate=0.0001,
            basis_time_ms=now_ms - 4000,
            long_short_account_ratio=1.0,
            long_short_time_ms=now_ms - 5000,
            order_book_imbalance=0.0,
            spread_bps=1.0,
            observed_at_ms=now_ms - 500,
        ),
        field_availability={"mark_price": True},
        endpoint_errors={},
    )
    client._optional_get.return_value = None

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_coverage.db"
        store = MarketWatchStateStore(db_path)
        config = MarketWatchConfig()
        scanner = MarketWatchScanner(config=config, client=client, store=store)

        ranked, _alerts = scanner.scan_universe(["BTCUSDT", "ETHUSDT"])
        assert len(ranked) == 2
        for item in ranked:
            # Assessment has evidence id attached
            assert item.feature_evidence_id is not None
            assert len(item.feature_evidence_id) == 64
            # Evidence can be read back from store
            ev_row = store.get_tactical_feature_evidence(item.feature_evidence_id)
            assert ev_row is not None
            assert ev_row.symbol == item.symbol
            # Validates that even if directional decision is NO_TRADE or WAIT, evidence is persisted
            assert ev_row.decision_trace.final_directional_decision in [d.value for d in DirectionalDecision]


# ==============================================================================
# B1-08: Decision Trace & Rule Score Breakdown
# ==============================================================================

def test_b1_08_decision_trace_and_rule_score_breakdown() -> None:
    """B1-08: 4 Policy gate stages recorded; breakdown matching calculate_rule_score."""
    ev, _ = build_sample_evidence_and_assessment()
    dt = ev.decision_trace
    assert dt.after_entry_quality_gate.stage_name == "entry_quality_gate"
    assert dt.after_benchmark_gate.stage_name == "benchmark_gate"
    assert dt.after_derivatives_gate.stage_name == "derivatives_gate"
    assert dt.after_fatal_veto.stage_name == "fatal_veto_gate"

    # Verify rule score breakdown matches calculate_rule_score exactly
    combos = [
        (DirectionalDecision.LONG, EntryQuality.EXCELLENT, False),
        (DirectionalDecision.LONG, EntryQuality.GOOD, False),
        (DirectionalDecision.SHORT, EntryQuality.MARGINAL, False),
        (DirectionalDecision.WAIT, EntryQuality.POOR, True),
    ]

    tf1 = make_dummy_timeframe("BTCUSDT", "1h")
    tf15 = make_dummy_timeframe("BTCUSDT", "15m")
    deriv = DerivativesMetrics(mark_price=50000.0, funding_rate=0.0001, taker_buy_sell_ratio=1.1)
    exh = ExhaustionMetrics(state=ExhaustionState.NORMAL, reasons=())
    cfg = MarketWatchConfig()

    for dec, eq, veto in combos:
        bd = calculate_rule_score_breakdown(
            decision=dec,
            tf_1h=tf1,
            tf_15m=tf15,
            entry_quality=eq,
            derivatives=deriv,
            exhaustion=exh,
            relative_perf=None,
            benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
            net_rr=1.45,
            has_fatal_veto=veto,
            config=cfg,
        )
        single = calculate_rule_score(
            decision=dec,
            tf_1h=tf1,
            tf_15m=tf15,
            entry_quality=eq,
            derivatives=deriv,
            exhaustion=exh,
            relative_perf=None,
            benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
            net_rr=1.45,
            has_fatal_veto=veto,
            config=cfg,
        )
        assert bd.final_rule_score == single


# ==============================================================================
# B1-09: Persistence Conflict & Idempotence
# ==============================================================================

def test_b1_09_persistence_conflict_and_idempotence() -> None:
    """B1-09: Idempotent re-save succeeds; conflicting evidence_id raises TacticalEvidenceConflictError."""
    ev, assessment = build_sample_evidence_and_assessment()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_conflict.db"
        store = MarketWatchStateStore(db_path)

        def save_state(ev_to_save: TacticalFeatureEvidenceV2) -> None:
            store.save_symbol_state(
                symbol=ev_to_save.symbol,
                assessment=assessment,
                now_ms=1_700_000_500_000,
                alert_sent=False,
                evidence=ev_to_save,
            )

        # First save: success
        save_state(ev)

        # Second save with exact same evidence_id: idempotent success
        save_state(ev)

        # Third save with same natural key but DIFFERENT evidence_id: conflict error
        conflicting_ev = dataclasses.replace(
            ev,
            entry_quality="GOOD",
        )
        conflicting_ev = dataclasses.replace(
            conflicting_ev,
            evidence_id=compute_evidence_id(conflicting_ev),
        )
        with pytest.raises(TacticalEvidenceConflictError, match="Evidence conflict"):
            save_state(conflicting_ev)


# ==============================================================================
# B1-10: Shadow Linkage & DB Immutability
# ==============================================================================

def test_b1_10_shadow_linkage_and_immutability() -> None:
    """B1-10: Shadow record links to evidence; missing evidence raises error; resolving shadow leaves evidence immutable."""
    ev, assessment = build_sample_evidence_and_assessment()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_shadow.db"
        store = MarketWatchStateStore(db_path)

        # 1. Attempt shadow record with non-existent feature_evidence_id -> fails
        with pytest.raises(TacticalEvidenceLinkageError, match="non-existent"):
            store.record_shadow_observation(
                timestamp_ms=ev.decision_time_ms,
                symbol=ev.symbol,
                snapshot_hash=ev.snapshot_hash,
                agent_decision=ev.decision_trace.final_directional_decision,
                agent_setup=ev.selected_playbook or "BREAKOUT_RETEST",
                entry_quality=ev.entry_quality,
                reason_codes=list(ev.reason_codes),
                policy_version=ev.policy_version,
                config_hash=ev.config_hash,
                entry_price=50000.0,
                stop_loss=48000.0,
                tp1=53000.0,
                tp2=55000.0,
                direction="LONG",
                feature_evidence_id="0" * 64,
            )

        # 2. Persist state and evidence
        store.save_symbol_state(
            symbol=ev.symbol,
            assessment=assessment,
            now_ms=ev.decision_time_ms,
            alert_sent=False,
            evidence=ev,
        )

        # 3. Record shadow observation with existing feature_evidence_id -> succeeds
        shadow_id = store.record_shadow_observation(
            timestamp_ms=ev.decision_time_ms,
            symbol=ev.symbol,
            snapshot_hash=ev.snapshot_hash,
            agent_decision=ev.decision_trace.final_directional_decision,
            agent_setup=ev.selected_playbook or "BREAKOUT_RETEST",
            entry_quality=ev.entry_quality,
            reason_codes=list(ev.reason_codes),
            policy_version=ev.policy_version,
            config_hash=ev.config_hash,
            entry_price=50000.0,
            stop_loss=48000.0,
            tp1=53000.0,
            tp2=55000.0,
            direction="LONG",
            feature_evidence_id=ev.evidence_id,
        )
        assert shadow_id > 0

        # Verify shadow record in DB has feature_evidence_id
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT feature_evidence_id FROM market_watch_shadow_records WHERE id = ?", (shadow_id,))
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == ev.evidence_id

        # 4. Resolve shadow record and verify evidence record remains strictly identical
        ev_before = store.get_tactical_feature_evidence(ev.evidence_id)
        assert ev_before is not None
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE market_watch_shadow_records SET resolved = 1, terminal_reason = 'RESOLVED_TARGET', exit_price = 53050.0 WHERE id = ?",
                (shadow_id,),
            )
            conn.commit()

        ev_after = store.get_tactical_feature_evidence(ev.evidence_id)
        assert ev_after is not None
        assert canonical_json_dump(canonical_evidence_payload(ev_after)) == canonical_json_dump(canonical_evidence_payload(ev_before))
        assert ev_after.evidence_id == ev_before.evidence_id

        # Check DB row persisted_at_ms unchanged
        with sqlite3.connect(db_path) as conn:
            row_p = conn.execute("SELECT persisted_at_ms FROM tactical_feature_evidence_v2 WHERE evidence_id = ?", (ev.evidence_id,)).fetchone()
            assert row_p is not None
            assert row_p[0] == ev.decision_time_ms


# ==============================================================================
# Storage Benchmark (1000 Rows)
# ==============================================================================

def test_storage_benchmark_1000_records() -> None:
    """Benchmark: 1,000 distinct evidence records persisted into SQLite (< 20 KB per record average)."""
    base_ev, _ = build_sample_evidence_and_assessment()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_benchmark.db"
        store = MarketWatchStateStore(db_path)

        count = 1000
        start_time = time.perf_counter()

        with store._connect() as conn:
            for i in range(count):
                # Construct unique decision time and evidence id
                dec_t = base_ev.decision_time_ms + i * 60_000
                ev_id = f"{i:064x}"
                ev = dataclasses.replace(
                    base_ev,
                    decision_time_ms=dec_t,
                    evidence_id=ev_id,
                )
                payload_json = canonical_json_dump(canonical_evidence_payload(ev))
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
                        ev.semantic_identity.canonical_hash(),
                        ev.signal_identity,
                        ev.setup_key,
                        ev.lifecycle_state,
                        ev.selected_playbook,
                        ev.decision_trace.final_directional_decision,
                        ev.rule_score,
                        ev.reference_universe_evidence.status,
                        payload_json,
                        dec_t + 100,
                    ),
                )
            conn.commit()

        duration = time.perf_counter() - start_time
        file_size_bytes = db_path.stat().st_size
        avg_bytes_per_row = file_size_bytes / count

        print(f"Benchmark: {count} records written in {duration:.3f}s ({count / duration:.1f} rec/s).")
        print(f"DB file size: {file_size_bytes / 1024:.1f} KB, Avg per row: {avg_bytes_per_row / 1024:.2f} KB")

        # Invariant: average row storage must be comfortably under 20 KB
        assert avg_bytes_per_row < 20 * 1024, f"Average row size {avg_bytes_per_row} exceeds 20KB limit"


# ==============================================================================
# B1-R1: Integrity and Completeness Seal Tests (Sections 28 - 40)
# ==============================================================================

def test_b1_r1_full_population_proof() -> None:
    """Section 28: Population proof for LONG, SHORT, WAIT with setup, and WAIT + NO_TRADE."""
    cfg = MarketWatchConfig()
    now_ms = 1_700_000_100_000

    def _make_client(direction: str, setup_name: str) -> MagicMock:
        c = MagicMock()
        c.server_time_ms.return_value = now_ms
        c.klines.return_value = make_test_candles(count=60, end_ms=1_700_000_000_000)
        c.collect_derivatives.return_value = MagicMock(
            snapshot=MagicMock(
                mark_price=50000.0,
                index_price=50000.0,
                funding_rate=0.0001,
                funding_time_ms=now_ms + 14_400_000,
                open_interest=50000.0,
                open_interest_time_ms=now_ms - 2000,
                open_interest_change_pct=0.01,
                taker_buy_sell_ratio=1.0,
                taker_time_ms=now_ms - 3000,
                basis_rate=0.0001,
                basis_time_ms=now_ms - 4000,
                long_short_account_ratio=1.0,
                long_short_time_ms=now_ms - 5000,
                order_book_imbalance=0.0,
                spread_bps=1.0,
                observed_at_ms=now_ms - 500,
            ),
            field_availability={"mark_price": True, "funding_rate": True},
            endpoint_errors={},
        )
        c._optional_get.return_value = None
        return c

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_population.db"
        store = MarketWatchStateStore(db_path)

        # 1. LONG fixture
        ev_long, a_long = build_sample_evidence_and_assessment(symbol="BTCUSDT")
        store.save_symbol_state("BTCUSDT", a_long, now_ms, evidence=ev_long)
        ev_row_long = store.get_tactical_feature_evidence(ev_long.evidence_id)
        assert ev_row_long is not None
        assert ev_row_long.decision_trace.final_directional_decision == "LONG"
        assert ev_row_long.selected_playbook == PlaybookType.BREAKOUT_RETEST.value

        # 2. SHORT fixture
        ev_short_raw, a_short_raw = build_sample_evidence_and_assessment(symbol="ETHUSDT")
        d_short = dataclasses.replace(
            a_short_raw.directional,
            decision=DirectionalDecision.SHORT,
            setup=PlaybookType.TREND_PULLBACK,
            entry_low=2950.0,
            entry_high=3050.0,
            stop_loss=3200.0,
            take_profit_1=2700.0,
        )
        dt_short = PolicyDecisionTrace(
            selected_candidate_decision="SHORT",
            after_entry_quality_gate=PolicyGateStageTrace("entry_quality_gate", "SHORT", "SHORT"),
            after_benchmark_gate=PolicyGateStageTrace("benchmark_gate", "SHORT", "SHORT"),
            after_derivatives_gate=PolicyGateStageTrace("derivatives_gate", "SHORT", "SHORT"),
            after_fatal_veto=PolicyGateStageTrace("fatal_veto_gate", "SHORT", "SHORT"),
            final_directional_decision="SHORT",
        )
        cand_short = PlaybookCandidate(
            playbook=PlaybookType.TREND_PULLBACK,
            candidate_status=CandidateStatus.ACTIONABLE,
            decision=DirectionalDecision.SHORT,
            entry_low=2950.0,
            entry_high=3050.0,
            stop_loss=3200.0,
            take_profit_1=2700.0,
            take_profit_2=2500.0,
            structural_anchor_id=None,
            reason_codes=("Valid trend pullback short",),
            risk_codes=(),
            setup_creation_bar_end_ms=1_700_000_000_000,
        )
        a_short = dataclasses.replace(
            a_short_raw,
            symbol="ETHUSDT",
            directional=d_short,
            selected_playbook=PlaybookType.TREND_PULLBACK.value,
        )
        ev_short = build_tactical_feature_evidence(
            assessment=a_short,
            playbook_candidates=[cand_short],
            decision_trace=dt_short,
            rule_score_breakdown=dataclasses.replace(ev_short_raw.rule_score_breakdown, effective_direction="SHORT"),
            config=cfg,
        )
        store.save_symbol_state("ETHUSDT", a_short, now_ms, evidence=ev_short)
        ev_row_short = store.get_tactical_feature_evidence(ev_short.evidence_id)
        assert ev_row_short is not None
        assert ev_row_short.decision_trace.final_directional_decision == "SHORT"
        assert ev_row_short.selected_playbook == PlaybookType.TREND_PULLBACK.value

        # 3. WAIT with identified setup (e.g. entry quality gated to WAIT)
        dt_wait_setup = PolicyDecisionTrace(
            selected_candidate_decision="LONG",
            after_entry_quality_gate=PolicyGateStageTrace("entry_quality_gate", "LONG", "WAIT", ("ENTRY_QUALITY_BELOW_MINIMUM_WAIT",)),
            after_benchmark_gate=PolicyGateStageTrace("benchmark_gate", "WAIT", "WAIT"),
            after_derivatives_gate=PolicyGateStageTrace("derivatives_gate", "WAIT", "WAIT"),
            after_fatal_veto=PolicyGateStageTrace("fatal_veto_gate", "WAIT", "WAIT"),
            final_directional_decision="WAIT",
        )
        d_wait_setup = dataclasses.replace(
            a_long.directional,
            decision=DirectionalDecision.WAIT,
            setup=PlaybookType.BREAKOUT_RETEST,
            entry_quality=EntryQuality.POOR,
            reason_codes=("ENTRY_QUALITY_BELOW_MINIMUM_WAIT",),
        )
        a_wait_setup = dataclasses.replace(
            a_long,
            symbol="SOLUSDT",
            directional=d_wait_setup,
            selected_playbook=PlaybookType.BREAKOUT_RETEST.value,
        )
        ev_wait_setup = build_tactical_feature_evidence(
            assessment=a_wait_setup,
            playbook_candidates=[cand_short, PlaybookCandidate(
                playbook=PlaybookType.BREAKOUT_RETEST,
                candidate_status=CandidateStatus.WATCH,
                decision=DirectionalDecision.WAIT,
                entry_low=None,
                entry_high=None,
                stop_loss=None,
                take_profit_1=None,
                take_profit_2=None,
                structural_anchor_id=None,
                reason_codes=("Watching breakout",),
                risk_codes=(),
                setup_creation_bar_end_ms=1_700_000_000_000,
            )],
            decision_trace=dt_wait_setup,
            rule_score_breakdown=ev_long.rule_score_breakdown,
            config=cfg,
        )
        store.save_symbol_state("SOLUSDT", a_wait_setup, now_ms, evidence=ev_wait_setup)
        ev_row_ws = store.get_tactical_feature_evidence(ev_wait_setup.evidence_id)
        assert ev_row_ws is not None
        assert ev_row_ws.decision_trace.final_directional_decision == "WAIT"
        assert ev_row_ws.selected_playbook == PlaybookType.BREAKOUT_RETEST.value

        # 4. WAIT + NO_TRADE (no confirmed candidate emitted)
        client = _make_client("WAIT", "NO_TRADE")
        scanner = MarketWatchScanner(config=cfg, client=client, store=store)
        ranked, _alerts = scanner.scan_universe(["BNBUSDT"])
        assert len(ranked) >= 1
        bnb = next(r for r in ranked if r.symbol == "BNBUSDT")
        assert bnb.feature_evidence_id is not None
        ev_bnb = store.get_tactical_feature_evidence(bnb.feature_evidence_id)
        assert ev_bnb is not None
        assert ev_bnb.decision_trace.final_directional_decision == "WAIT"
        assert ev_bnb.selected_playbook is None
        assert ev_bnb.directional_risk_plan.setup == "NO_TRADE"


def test_b1_r1_candidate_completeness_proof() -> None:
    """Section 29: Every evidence object contains exactly 5 active playbooks in frozen order and NO RANGE_MEAN_REVERSION."""
    ev, _ = build_sample_evidence_and_assessment()
    assert len(ev.playbook_candidates) == 5
    expected_order = tuple(p.value for p in ACTIVE_PLAYBOOKS)
    actual_order = tuple(c.playbook for c in ev.playbook_candidates)
    assert actual_order == expected_order
    assert "RANGE_MEAN_REVERSION" not in actual_order

    # Candidate status validation
    for cand in ev.playbook_candidates:
        if cand.playbook == PlaybookType.BREAKOUT_RETEST.value:
            assert cand.candidate_status == "ACTIONABLE"
        else:
            assert cand.candidate_status == "ABSENT"


def test_b1_r1_deep_immutability_adversarial() -> None:
    """Section 30: Adversarial tests verifying deep immutability across all reachable structures."""
    ev, _ = build_sample_evidence_and_assessment()

    # 1. Top-level dataclass mutation
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        ev.symbol = "DOGEUSDT"  # type: ignore[misc]

    # 2. DecisionConfigEvidence immutability
    assert isinstance(ev.decision_config, DecisionConfigEvidence)
    assert isinstance(ev.decision_config.canonical_json, str)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        ev.decision_config.canonical_json = "{}"  # type: ignore[misc]
    # to_dict returns a fresh copy; mutating it does not affect evidence
    cfg_copy = ev.decision_config.to_dict()
    cfg_copy["min_net_rr"] = 999.0
    assert ev.decision_config.to_dict()["min_net_rr"] != 999.0

    # 3. Source provenance & returns
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        ev.source_provenance.closed_bar_watermark_15m = 0  # type: ignore[misc]
    with pytest.raises(TypeError):
        ev.source_provenance.returns[0] = None  # type: ignore[index]

    # 4. Playbook candidates
    with pytest.raises(TypeError):
        ev.playbook_candidates[0] = None  # type: ignore[index]

    # 5. Decision trace
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        ev.decision_trace.final_directional_decision = "SHORT"  # type: ignore[misc]

    # 6. Rule score breakdown
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        ev.rule_score_breakdown.final_rule_score = 100.0  # type: ignore[misc]

    # 7. Reference universe evidence
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        ev.reference_universe_evidence.score = 50.0  # type: ignore[misc]

    # 8. Policy state before
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        ev.policy_state_before.previous_setup = "TREND_PULLBACK"  # type: ignore[misc]

    # 9. Latest closed bar
    tf_15m = ev.market_snapshot_features.tf_15m
    assert isinstance(tf_15m.latest_closed_bar, ClosedBarEvidence)
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        tf_15m.latest_closed_bar.close = 0.0  # type: ignore[misc]


def test_b1_r1_stale_id_mutation() -> None:
    """Section 31: Mutating content while keeping old evidence ID fails closed across all pathways."""
    ev, assessment = build_sample_evidence_and_assessment()
    old_id = ev.evidence_id

    # Create tampered evidence: changed rule_score but stale old_id
    tampered_rsb = dataclasses.replace(
        ev.rule_score_breakdown,
        final_rule_score=ev.rule_score + 5.0,
    )
    tampered_ev = dataclasses.replace(
        ev,
        rule_score=ev.rule_score + 5.0,
        rule_score_breakdown=tampered_rsb,
        evidence_id=old_id,  # Stale ID!
    )

    # 1. Direct identity verification must reject
    with pytest.raises(TacticalEvidenceIdentityError, match="Evidence identity verification failed"):
        verify_tactical_evidence_identity(tampered_ev)

    # 2. Persistence must reject
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_stale_id.db"
        store = MarketWatchStateStore(db_path)
        with pytest.raises(TacticalEvidenceIdentityError):
            store.save_symbol_state("BTCUSDT", assessment, 1_700_000_500_000, evidence=tampered_ev)

    # 3. Deserialization must reject
    tampered_raw = canonical_evidence_json(tampered_ev)
    with pytest.raises(TacticalEvidenceIdentityError):
        deserialize_tactical_feature_evidence(tampered_raw)


def test_b1_r1_stored_corruption() -> None:
    """Section 32: Tampered database evidence_json fails closed on read."""
    ev, assessment = build_sample_evidence_and_assessment()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_corruption.db"
        store = MarketWatchStateStore(db_path)
        store.save_symbol_state("BTCUSDT", assessment, 1_700_000_500_000, evidence=ev)

        # Directly tamper the stored evidence_json in SQLite without updating evidence_id
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                UPDATE tactical_feature_evidence_v2
                SET evidence_json = REPLACE(evidence_json, '"rule_score":75.58', '"rule_score":99.99')
                WHERE evidence_id = ?
                """,
                (ev.evidence_id,),
            )
            conn.commit()

        # Read path must detect the tampering and fail closed
        with pytest.raises(TacticalEvidenceIdentityError):
            store.get_tactical_feature_evidence(ev.evidence_id)


def test_b1_r1_config_self_containment() -> None:
    """Section 33: Stored DecisionConfigEvidence reproduces config_hash for default and non-default fixtures."""
    # 1. Default config
    cfg_default = MarketWatchConfig()
    ev_def, _ = build_sample_evidence_and_assessment(config=cfg_default)
    stored_payload_def = ev_def.decision_config.to_dict()
    recomputed_hash_def = compute_market_watch_config_hash_from_payload(stored_payload_def)
    assert recomputed_hash_def == ev_def.config_hash
    assert ev_def.config_hash == "27f7d4c835a36330"

    # 2. Non-default config
    cfg_custom = MarketWatchConfig(min_net_rr=2.5, maker_fee_rate=0.0003, scan_interval_minutes=5)
    ev_cust, _ = build_sample_evidence_and_assessment(config=cfg_custom)
    stored_payload_cust = ev_cust.decision_config.to_dict()
    recomputed_hash_cust = compute_market_watch_config_hash_from_payload(stored_payload_cust)
    assert recomputed_hash_cust == ev_cust.config_hash
    assert ev_cust.config_hash == "bc35d7240d77cea0"


def test_b1_r1_pit_adversarial() -> None:
    """Section 34: Strict point-in-time and causality invariant adversarial tests."""
    ev, _ = build_sample_evidence_and_assessment()
    dec_t = ev.decision_time_ms

    # 1. Anchor time > latest close time
    bad_ret_anchor = ReturnObservation(
        horizon_ms=3_600_000,
        value=0.01,
        availability="AVAILABLE",
        anchor_close_time_ms=dec_t - 1000,
        latest_close_time_ms=dec_t - 2000,
    )
    ev_bad_anchor = dataclasses.replace(
        ev,
        source_provenance=dataclasses.replace(ev.source_provenance, returns=(bad_ret_anchor,)),
    )
    with pytest.raises(TacticalCausalityError, match="anchor time"):
        validate_tactical_feature_evidence(ev_bad_anchor)

    # 2. Available return with null anchor
    bad_ret_null_anchor = ReturnObservation(
        horizon_ms=3_600_000,
        value=0.01,
        availability="AVAILABLE",
        anchor_close_time_ms=None,
        latest_close_time_ms=dec_t - 1000,
    )
    ev_null_anchor = dataclasses.replace(
        ev,
        source_provenance=dataclasses.replace(ev.source_provenance, returns=(bad_ret_null_anchor,)),
    )
    with pytest.raises(TacticalCausalityError, match="anchor/latest close time is None"):
        validate_tactical_feature_evidence(ev_null_anchor)

    # 3. Available return with null value
    bad_ret_null_val = ReturnObservation(
        horizon_ms=3_600_000,
        value=None,
        availability="AVAILABLE",
        anchor_close_time_ms=dec_t - 3_600_000,
        latest_close_time_ms=dec_t,
    )
    ev_null_val = dataclasses.replace(
        ev,
        source_provenance=dataclasses.replace(ev.source_provenance, returns=(bad_ret_null_val,)),
    )
    with pytest.raises(TacticalCausalityError, match="value is None"):
        validate_tactical_feature_evidence(ev_null_val)

    # 4. Horizon span mismatch (3_600_000 required, but span is 1_800_000)
    bad_ret_span = ReturnObservation(
        horizon_ms=3_600_000,
        value=0.01,
        availability="AVAILABLE",
        anchor_close_time_ms=dec_t - 1_800_000,
        latest_close_time_ms=dec_t,
    )
    ev_bad_span = dataclasses.replace(
        ev,
        source_provenance=dataclasses.replace(ev.source_provenance, returns=(bad_ret_span,)),
    )
    with pytest.raises(TacticalCausalityError, match="span"):
        validate_tactical_feature_evidence(ev_bad_span)

    # 5. collection_completed > decision_time
    ev_bad_coll = dataclasses.replace(ev, collection_completed_at_ms=dec_t + 1000)
    with pytest.raises(TacticalCausalityError, match="collection_completed_at_ms"):
        validate_tactical_feature_evidence(ev_bad_coll)

    # 6. Receipt timestamp > decision_time
    ev_bad_receipt = dataclasses.replace(
        ev,
        source_provenance=dataclasses.replace(ev.source_provenance, ticker_receipt_ms=dec_t + 500),
    )
    with pytest.raises(TacticalCausalityError, match="Receipt timestamp"):
        validate_tactical_feature_evidence(ev_bad_receipt)

    # 7. Past event timestamp > decision_time
    ev_bad_past = dataclasses.replace(
        ev,
        source_provenance=dataclasses.replace(ev.source_provenance, open_interest_time_ms=dec_t + 500),
    )
    with pytest.raises(TacticalCausalityError, match="Source event timestamp"):
        validate_tactical_feature_evidence(ev_bad_past)

    # 8. Positive test: funding_time_ms is KNOWN_FUTURE_SCHEDULE_TIME and may legitimately be > decision_time
    ev_future_funding = dataclasses.replace(
        ev,
        source_provenance=dataclasses.replace(ev.source_provenance, funding_time_ms=dec_t + 14_400_000),
    )
    validate_tactical_feature_evidence(ev_future_funding)


def test_b1_r1_feature_completeness_regression() -> None:
    """Section 35: Evidence changes when latest_closed_bar or has_prior_compression_window changes."""
    ev1, _ = build_sample_evidence_and_assessment()

    # Modify latest_closed_bar OHLC in timeframe 15m
    lcb1 = ev1.market_snapshot_features.tf_15m.latest_closed_bar
    lcb2 = dataclasses.replace(lcb1, high=lcb1.high + 50.0)
    tf2 = dataclasses.replace(ev1.market_snapshot_features.tf_15m, latest_closed_bar=lcb2)
    ev2 = dataclasses.replace(
        ev1,
        market_snapshot_features=dataclasses.replace(ev1.market_snapshot_features, tf_15m=tf2),
    )
    ev2 = dataclasses.replace(ev2, evidence_id=compute_evidence_id(canonical_evidence_payload(ev2)))
    assert ev2.evidence_id != ev1.evidence_id

    # Modify has_prior_compression_window
    tf3 = dataclasses.replace(ev1.market_snapshot_features.tf_1h, has_prior_compression_window=True)
    ev3 = dataclasses.replace(
        ev1,
        market_snapshot_features=dataclasses.replace(ev1.market_snapshot_features, tf_1h=tf3),
    )
    ev3 = dataclasses.replace(ev3, evidence_id=compute_evidence_id(canonical_evidence_payload(ev3)))
    assert ev3.evidence_id != ev1.evidence_id


def test_b1_r1_decision_trace_gates() -> None:
    """Section 36: Verify exact runtime gate names in PolicyDecisionTrace."""
    ev, _ = build_sample_evidence_and_assessment()
    dt = ev.decision_trace
    assert dt.after_entry_quality_gate.stage_name == "entry_quality_gate"
    assert dt.after_benchmark_gate.stage_name == "benchmark_gate"
    assert dt.after_derivatives_gate.stage_name == "derivatives_gate"
    assert dt.after_fatal_veto.stage_name == "fatal_veto_gate"

    # Verify gate veto trace
    trace_veto = PolicyDecisionTrace(
        selected_candidate_decision="LONG",
        after_entry_quality_gate=PolicyGateStageTrace("entry_quality_gate", "LONG", "LONG"),
        after_benchmark_gate=PolicyGateStageTrace("benchmark_gate", "LONG", "LONG"),
        after_derivatives_gate=PolicyGateStageTrace("derivatives_gate", "LONG", "WAIT", ("DERIVATIVES_LONG_CROWDED",)),
        after_fatal_veto=PolicyGateStageTrace("fatal_veto_gate", "WAIT", "WAIT", veto_flag=True),
        final_directional_decision="WAIT",
    )
    assert trace_veto.after_derivatives_gate.output_decision == "WAIT"
    assert trace_veto.after_fatal_veto.veto_flag is True
    assert trace_veto.final_directional_decision == "WAIT"


def test_b1_r1_rule_score_regression() -> None:
    """Section 37: RuleScore numerical semantics preserved exactly without drift."""
    ev, _ = build_sample_evidence_and_assessment()
    assert math.isclose(ev.rule_score, ev.rule_score_breakdown.final_rule_score, abs_tol=1e-6)
    assert ev.rule_score_semantics == "RULE_SCORE_V1"


def test_b1_r1_natural_key_conflict_scan() -> None:
    """Section 38: StateStore _init_db detects conflicting natural keys and raises B1_R1_EXISTING_EVIDENCE_CONFLICT."""
    ev, assessment = build_sample_evidence_and_assessment()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_nk_conflict.db"
        # Setup initial DB
        store = MarketWatchStateStore(db_path)
        store.save_symbol_state("BTCUSDT", assessment, 1_700_000_500_000, evidence=ev)

        # Drop unique index and manually insert a duplicate natural key with divergent evidence_id
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("DROP INDEX IF EXISTS idx_tactical_feat_ev_natural_key")
            conn.execute(
                """
                INSERT INTO tactical_feature_evidence_v2 (
                    evidence_id, evidence_schema_version, decision_time_ms, symbol,
                    snapshot_hash, policy_version, config_hash, evidence_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "e" * 64,
                    ev.evidence_schema_version,
                    ev.decision_time_ms,
                    ev.symbol,
                    ev.snapshot_hash,
                    ev.policy_version,
                    ev.config_hash,
                    "{}",
                ),
            )
            conn.commit()

        # Re-initializing MarketWatchStateStore must fail closed
        with pytest.raises(TacticalEvidenceConflictError, match="B1_R1_EXISTING_EVIDENCE_CONFLICT"):
            MarketWatchStateStore(db_path)


def test_b1_r1_concurrent_persistence_conflict() -> None:
    """Section 39: Natural-key uniqueness enforces idempotent success and conflict on divergent identity."""
    ev, assessment = build_sample_evidence_and_assessment()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_concurrent.db"
        store = MarketWatchStateStore(db_path)

        # 1. First save succeeds
        store.save_symbol_state("BTCUSDT", assessment, 1_700_000_500_000, evidence=ev)

        # 2. Idempotent second save with same evidence_id succeeds
        store.save_symbol_state("BTCUSDT", assessment, 1_700_000_500_000, evidence=ev)

        # 3. Third save with same natural key but different valid evidence_id raises TacticalEvidenceConflictError
        diff_ev = dataclasses.replace(ev, entry_quality="GOOD")
        diff_ev = dataclasses.replace(diff_ev, evidence_id=compute_evidence_id(diff_ev))
        with pytest.raises(TacticalEvidenceConflictError, match="Evidence conflict for natural key"):
            store.save_symbol_state("BTCUSDT", assessment, 1_700_000_500_000, evidence=diff_ev)


def test_b1_r1_atomic_rollback() -> None:
    """Section 40: Force an error between evidence insert and assessment completion to prove atomic rollback."""
    ev, assessment = build_sample_evidence_and_assessment()

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_atomic.db"
        store = MarketWatchStateStore(db_path)

        real_connect = store._connect

        class FaultyConnection:
            def __init__(self, conn: sqlite3.Connection) -> None:
                self._conn = conn

            def __enter__(self) -> Self:
                self._conn.__enter__()
                return self

            def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> object:
                return self._conn.__exit__(exc_type, exc_val, exc_tb)  # type: ignore[arg-type]

            def execute(self, sql: str, *args: object, **kwargs: object) -> object:
                if "INSERT INTO market_watch_symbol_state" in sql:
                    raise sqlite3.OperationalError("Simulated mid-transaction failure")
                return self._conn.execute(sql, *args, **kwargs)

            def __getattr__(self, name: str) -> object:
                return getattr(self._conn, name)

        store._connect = lambda: FaultyConnection(real_connect())  # type: ignore[assignment]
        with pytest.raises(sqlite3.OperationalError, match="Simulated mid-transaction failure"):
            store.save_symbol_state("BTCUSDT", assessment, 1_700_000_500_000, evidence=ev)

        store._connect = real_connect

        # Assert atomic rollback: NO evidence row committed!
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM tactical_feature_evidence_v2")
            assert cursor.fetchone()[0] == 0
            cursor = conn.execute("SELECT COUNT(*) FROM market_watch_assessments")
            assert cursor.fetchone()[0] == 0

        # Normal retry succeeds exactly once
        store.save_symbol_state("BTCUSDT", assessment, 1_700_000_500_000, evidence=ev)
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM tactical_feature_evidence_v2")
            assert cursor.fetchone()[0] == 1
            cursor = conn.execute("SELECT COUNT(*) FROM market_watch_assessments")
            assert cursor.fetchone()[0] == 1

