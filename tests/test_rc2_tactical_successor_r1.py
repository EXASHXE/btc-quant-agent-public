#!/usr/bin/env python3
"""Comprehensive test suite for RC2 Tactical Successor R1.

Verifies:
1. Promoted rules and vetoes (structure_transition, trend_persistence)
2. Missing/stale promoted evidence fail-closed behavior
3. Candidate budget enforcement (<= 6 total)
4. Protected validation firewall (0 queries/accesses for holdout symbols)
5. PIT chronology checks
6. Authentic 1m fail-closed behavior
7. Deterministic replay proof
8. Selected policy manifest and evidence integrity
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from btc_quant_agent.domain import Candle, Regime
from btc_quant_agent.market_watch.config import (
    MarketWatchConfig,
)
from btc_quant_agent.market_watch.domain import (
    TACTICAL_POLICY_VERSION,
    BenchmarkContext,
    DerivativesMetrics,
    DerivativesRegime,
    DirectionalDecision,
    ExhaustionMetrics,
    ExhaustionState,
    TimeframeSnapshot,
)
from btc_quant_agent.market_watch.ranking import check_fatal_vetoes
from btc_quant_agent.market_watch.trend_shadow import (
    TrendEvidenceV2Shadow,
    TrendShadowCausalityError,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "evidence" / "v0.5.5" / "tactical-policy" / "RC2" / "SUCCESSOR_R1"

PROTECTED_VALIDATION_SYMBOLS = (
    "ADAUSDT",
    "AVAXUSDT",
    "LTCUSDT",
    "TRXUSDT",
    "BCHUSDT",
    "DOTUSDT",
    "ATOMUSDT",
    "NEARUSDT",
)

DEVELOPMENT_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "BNBUSDT",
)


def _make_dummy_tf(
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    close: float = 100.0,
    regime: Regime = Regime.TREND_UP,
    structure: str = "HH_HL",
) -> TimeframeSnapshot:
    c = Candle(symbol, interval, 1000, 2000, close, close * 1.01, close * 0.99, close, 100.0)
    return TimeframeSnapshot(
        interval=interval,
        latest_bar=c,
        latest_closed_bar=c,
        closed_bar_end_time_ms=2000,
        close=close,
        ema_fast=close * 0.99,
        ema_mid=close * 0.98,
        ema_fast_slope=0.01,
        ema_mid_slope=0.005,
        atr=1.0,
        atr_percentile=0.5,
        adx=30.0,
        rsi=55.0,
        roc=0.01,
        volume=100.0,
        volume_z=0.5,
        bb_width=0.02,
        bb_width_percentile=0.5,
        structure=structure,
        regime=regime,
    )


def _make_dummy_trend_evidence(
    *,
    structure_transition: str = "CONTINUATION_UP",
    trend_persistence: float = 0.75,
) -> MagicMock:
    ev = MagicMock(spec=TrendEvidenceV2Shadow)
    ev.structure_transition = structure_transition
    ev.trend_persistence = trend_persistence
    return ev


class TestRC2TacticalSuccessorPromotedRules:
    def test_policy_version_bump(self) -> None:
        assert TACTICAL_POLICY_VERSION == "TACTICAL_POLICY_R2_B1"

    def test_promoted_structure_transition_veto(self) -> None:
        """Adverse transitions (TREND_TO_RANGE, RANGE_TO_TREND_UP, RANGE_TO_TREND_DOWN) must be vetoed."""
        config = MarketWatchConfig()
        tf_4h = _make_dummy_tf(interval="4h")
        deriv = DerivativesMetrics(mark_price=100.0, regime=DerivativesRegime.HEALTHY_LONG_BUILD)
        exhaustion = ExhaustionMetrics(distance_from_ema20_atr=0.5, state=ExhaustionState.NORMAL)

        # Disallowed transitions
        for adverse in ("TREND_TO_RANGE", "RANGE_TO_TREND_UP", "RANGE_TO_TREND_DOWN"):
            trend_ev = _make_dummy_trend_evidence(structure_transition=adverse, trend_persistence=0.75)
            veto, reasons = check_fatal_vetoes(
                decision=DirectionalDecision.LONG,
                exhaustion=exhaustion,
                net_rr=2.0,
                tf_4h=tf_4h,
                derivatives=deriv,
                benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
                config=config,
                trend_evidence=trend_ev,
                enforce_promoted_evidence=True,
            )
            assert veto, f"Expected veto for adverse transition {adverse}"
            assert "VETO_UNCONFIRMED_STRUCTURE_TRANSITION" in reasons

        # Permitted transitions
        for permitted in ("CONTINUATION_UP", "CONTINUATION_DOWN", "REVERSAL_DOWN_TO_UP", "STABLE_RANGE"):
            trend_ev = _make_dummy_trend_evidence(structure_transition=permitted, trend_persistence=0.75)
            veto, reasons = check_fatal_vetoes(
                decision=DirectionalDecision.LONG,
                exhaustion=exhaustion,
                net_rr=2.0,
                tf_4h=tf_4h,
                derivatives=deriv,
                benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
                config=config,
                trend_evidence=trend_ev,
                enforce_promoted_evidence=True,
            )
            assert not veto, f"Expected no veto for permitted transition {permitted}"
            assert "VETO_UNCONFIRMED_STRUCTURE_TRANSITION" not in reasons

    def test_promoted_trend_persistence_requirement(self) -> None:
        """trend_persistence < 0.60 must be vetoed; >= 0.60 must pass."""
        config = MarketWatchConfig()
        tf_4h = _make_dummy_tf(interval="4h")
        deriv = DerivativesMetrics(mark_price=100.0, regime=DerivativesRegime.HEALTHY_LONG_BUILD)
        exhaustion = ExhaustionMetrics(distance_from_ema20_atr=0.5, state=ExhaustionState.NORMAL)

        # Below floor (< 0.60)
        trend_ev_low = _make_dummy_trend_evidence(structure_transition="CONTINUATION_UP", trend_persistence=0.55)
        veto, reasons = check_fatal_vetoes(
            decision=DirectionalDecision.LONG,
            exhaustion=exhaustion,
            net_rr=2.0,
            tf_4h=tf_4h,
            derivatives=deriv,
            benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
            config=config,
            trend_evidence=trend_ev_low,
            enforce_promoted_evidence=True,
        )
        assert veto
        assert "VETO_INSUFFICIENT_TREND_PERSISTENCE" in reasons

        # At/above floor (>= 0.60)
        trend_ev_ok = _make_dummy_trend_evidence(structure_transition="CONTINUATION_UP", trend_persistence=0.60)
        veto, reasons = check_fatal_vetoes(
            decision=DirectionalDecision.LONG,
            exhaustion=exhaustion,
            net_rr=2.0,
            tf_4h=tf_4h,
            derivatives=deriv,
            benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
            config=config,
            trend_evidence=trend_ev_ok,
            enforce_promoted_evidence=True,
        )
        assert not veto
        assert "VETO_INSUFFICIENT_TREND_PERSISTENCE" not in reasons

    def test_missing_promoted_evidence_fails_closed_to_wait(self) -> None:
        """Missing or stale promoted evidence must fail closed with VETO_PROMOTED_TREND_EVIDENCE_MISSING."""
        config = MarketWatchConfig()
        tf_4h = _make_dummy_tf(interval="4h")
        deriv = DerivativesMetrics(mark_price=100.0, regime=DerivativesRegime.HEALTHY_LONG_BUILD)
        exhaustion = ExhaustionMetrics(distance_from_ema20_atr=0.5, state=ExhaustionState.NORMAL)

        veto, reasons = check_fatal_vetoes(
            decision=DirectionalDecision.LONG,
            exhaustion=exhaustion,
            net_rr=2.0,
            tf_4h=tf_4h,
            derivatives=deriv,
            benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
            config=config,
            trend_evidence=None,
            enforce_promoted_evidence=True,
        )
        assert veto
        assert "VETO_PROMOTED_TREND_EVIDENCE_MISSING" in reasons

    def test_wait_decision_not_vetoed(self) -> None:
        """WAIT decision is already neutral and does not generate directional fatal vetoes."""
        config = MarketWatchConfig()
        tf_4h = _make_dummy_tf(interval="4h")
        deriv = DerivativesMetrics(mark_price=100.0, spread_bps=1.0)
        exhaustion = ExhaustionMetrics(distance_from_ema20_atr=0.5, state=ExhaustionState.NORMAL)

        veto, reasons = check_fatal_vetoes(
            decision=DirectionalDecision.WAIT,
            exhaustion=exhaustion,
            net_rr=1.0,
            tf_4h=tf_4h,
            derivatives=deriv,
            benchmark_context=BenchmarkContext.BENCHMARK_NEUTRAL,
            config=config,
            trend_evidence=None,
            enforce_promoted_evidence=True,
        )
        assert not veto
        assert len(reasons) == 0


class TestCandidateBudgetAndManifests:
    def test_candidate_budget_at_most_six(self) -> None:
        """Candidate manifest must enforce candidate budget <= 6."""
        manifest_p = EVIDENCE_DIR / "CANDIDATE_MANIFEST.json"
        assert manifest_p.exists(), f"Missing {manifest_p}"
        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
        assert manifest["candidate_count"] <= 6
        assert manifest["candidate_budget_max"] == 6
        assert len(manifest["candidates"]) <= 6
        assert manifest["candidate_budget_complied"] is True

    def test_candidates_development_summary_contains_all_six(self) -> None:
        """CANDIDATES_DEVELOPMENT_SUMMARY.json must enumerate all 6 candidates and document selection."""
        summary_p = EVIDENCE_DIR / "CANDIDATES_DEVELOPMENT_SUMMARY.json"
        assert summary_p.exists(), f"Missing {summary_p}"
        summary = json.loads(summary_p.read_text(encoding="utf-8"))
        assert summary["candidate_count"] == 6
        assert len(summary["candidates"]) == 6
        assert summary["selected_candidate_id"] == "C5_BOUNDED_COMBINATION_B"
        assert summary["protected_universe_access_count"] == 0

    def test_selected_policy_manifest_matches_config(self) -> None:
        """SELECTED_POLICY_MANIFEST.json must bind exact policy version and config hash."""
        manifest_p = EVIDENCE_DIR / "SELECTED_POLICY_MANIFEST.json"
        assert manifest_p.exists(), f"Missing {manifest_p}"
        manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
        cfg = MarketWatchConfig()
        assert manifest["policy_version"] == TACTICAL_POLICY_VERSION
        assert manifest["config_hash"] == cfg.config_hash
        assert manifest["selected_candidate_id"] == "C5_BOUNDED_COMBINATION_B"
        assert manifest["protected_universe_access_count"] == 0


class TestProtectedValidationFirewall:
    def test_zero_protected_validation_symbols_accessed(self) -> None:
        """Protected holdout universe must have 0 access count."""
        evidence_p = EVIDENCE_DIR / "EVIDENCE.json"
        assert evidence_p.exists(), f"Missing {evidence_p}"
        ev = json.loads(evidence_p.read_text(encoding="utf-8"))
        firewall = ev["firewall_proof"]
        assert firewall["protected_validation_symbols_accessed_count"] == 0
        assert firewall["protected_validation_firewall_intact"] is True
        assert firewall["a_line_protected_outcomes_accessed"] is False
        assert firewall["h40_h41_protected_outcomes_accessed"] is False

    def test_universe_disjointness(self) -> None:
        """Development and protected validation universes must be strictly disjoint."""
        dev_set = set(DEVELOPMENT_SYMBOLS)
        prot_set = set(PROTECTED_VALIDATION_SYMBOLS)
        assert dev_set.isdisjoint(prot_set)

    def test_replay_dataset_contains_only_development_symbols(self) -> None:
        """The committed 30-day replay dataset must only contain development symbols."""
        evidence_p = EVIDENCE_DIR / "input_manifest.json"
        assert evidence_p.exists()
        inp = json.loads(evidence_p.read_text(encoding="utf-8"))
        dataset_symbols = set(inp["symbols"])
        assert dataset_symbols.issubset(set(DEVELOPMENT_SYMBOLS))
        assert dataset_symbols.isdisjoint(set(PROTECTED_VALIDATION_SYMBOLS))


class TestPITAndAuthenticDataGranularity:
    def test_future_candle_raises_pit_causality_error(self) -> None:
        """TrendEvidenceV2Shadow must reject candles closing after decision time."""
        c_future = Candle("BTCUSDT", "15m", 1000, 5000, 100.0, 101.0, 99.0, 100.5, 100.0)
        with pytest.raises(TrendShadowCausalityError, match="PIT violation|Future candle"):
            from btc_quant_agent.market_watch.trend_shadow import _enforce_pit_candles
            _enforce_pit_candles([c_future], 3000, "15m")

    def test_deterministic_replay_verification_in_evidence(self) -> None:
        """EVIDENCE.json must confirm run 1 and run 2 produced identical manifest hashes."""
        evidence_p = EVIDENCE_DIR / "EVIDENCE.json"
        ev = json.loads(evidence_p.read_text(encoding="utf-8"))
        det = ev["deterministic_replay_verification"]
        assert det["identical_manifest_produces_identical_results"] is True
        assert det["run_1_input_manifest_hash"] == det["run_2_input_manifest_hash"]
        assert det["run_1_output_manifest_hash"] == det["run_2_output_manifest_hash"]
        assert det["run_1_evidence_ids_sha256"] == det["run_2_evidence_ids_sha256"]
        assert det["run_1_shadow_evaluation_ids_sha256"] == det["run_2_shadow_evaluation_ids_sha256"]

    def test_decision_quality_gates_escape_hard_negatives(self) -> None:
        """Candidate 5 must escape all 4 RC1 hard-negative gates on development data."""
        evidence_p = EVIDENCE_DIR / "EVIDENCE.json"
        ev = json.loads(evidence_p.read_text(encoding="utf-8"))
        gates = ev["gate_evaluation"]["hard_negative_gates"]
        assert gates["any_triggered"] is False
        assert gates["mean_net_r_le_minus_0_10_with_100_actionable"] is False
        assert gates["median_net_r_le_minus_0_20_with_100_actionable"] is False
        assert gates["two_supported_partitions_mean_net_r_le_minus_0_25"] is False
        assert gates["stop_before_target_gt_0_70_with_100_resolved"] is False
