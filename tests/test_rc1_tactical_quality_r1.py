from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.market_watch.config import (
    MarketWatchConfig,
    compute_market_watch_config_hash,
)
from btc_quant_agent.market_watch.decision_quality import (
    FROZEN_TACTICAL_PREDECESSOR_SHA,
    TACTICAL_DECISION_QUALITY_CONTRACT_VERSION,
    FrozenReleaseThresholds,
    TacticalDecisionQualityDecision,
    compute_grid_diagnostic_metrics,
    compute_subgroup_diagnostics,
    compute_subset_metrics,
    evaluate_decision_quality_gates,
)
from btc_quant_agent.market_watch.domain import TACTICAL_POLICY_VERSION
from btc_quant_agent.market_watch.replay import (
    DeterministicTacticalReplayRunner,
    HistoricalReplayClient,
    OOSPartitionSpec,
    PITCausalityViolationError,
    ReplayDataset,
    validate_oos_partitions,
)
from btc_quant_agent.market_watch.scanner import MarketWatchScanner
from btc_quant_agent.market_watch.state import MarketWatchStateStore
from btc_quant_agent.market_watch.trend_shadow import (
    REQUIRED_TREND_EVIDENCE_V2_SHADOW_FIELDS,
    TREND_EVIDENCE_V2_SHADOW_AUTHORITY,
    TREND_EVIDENCE_V2_SHADOW_SCHEMA_VERSION,
    TrendShadowCausalityError,
    compute_trend_evidence_v2_shadow,
    summarize_trend_evidence_v2_shadow,
    validate_trend_evidence_v2_shadow,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_synthetic_raw_cache(
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT"),
    n_15m: int = 360,
    base_ms: int = 1_750_000_000_000,
) -> dict[str, Any]:
    """Create a deterministic synthetic multi-timeframe dataset for fast unit tests."""
    step_15m = 900_000
    step_1h = 3_600_000
    step_4h = 14_400_000
    anchor_end_ms = base_ms + n_15m * step_15m

    data: dict[str, Any] = {}
    for sym_idx, sym in enumerate(symbols):
        base_price = 60_000.0 if sym == "BTCUSDT" else 3_000.0 + sym_idx * 100.0
        klines_15m: list[list[Any]] = []
        for i in range(n_15m):
            open_ms = base_ms + i * step_15m
            close_ms = open_ms + step_15m - 1
            wave = math.sin(i * 0.12 + sym_idx) * 0.015 + (i * 0.0002)
            o_p = round(base_price * (1.0 + wave), 4)
            c_p = round(base_price * (1.0 + wave + 0.0015 * math.cos(i * 0.2)), 4)
            h_p = round(max(o_p, c_p) * 1.003, 4)
            l_p = round(min(o_p, c_p) * 0.997, 4)
            vol = 100.0 + (i % 15) * 12.0
            klines_15m.append([open_ms, o_p, h_p, l_p, c_p, vol, close_ms, vol * c_p, 500, vol * 0.52])

        n_1h = max(260, n_15m // 4 + 200)
        start_1h = anchor_end_ms - n_1h * step_1h
        klines_1h: list[list[Any]] = []
        for i in range(n_1h):
            open_ms = start_1h + i * step_1h
            close_ms = open_ms + step_1h - 1
            wave = math.sin(i * 0.15 + sym_idx) * 0.02 + (i * 0.0004)
            o_p = round(base_price * (1.0 + wave), 4)
            c_p = round(base_price * (1.0 + wave + 0.002 * math.cos(i * 0.18)), 4)
            h_p = round(max(o_p, c_p) * 1.005, 4)
            l_p = round(min(o_p, c_p) * 0.995, 4)
            vol = 400.0 + (i % 12) * 35.0
            klines_1h.append([open_ms, o_p, h_p, l_p, c_p, vol, close_ms, vol * c_p, 1800, vol * 0.51])

        n_4h = 260
        start_4h = anchor_end_ms - n_4h * step_4h
        klines_4h: list[list[Any]] = []
        for i in range(n_4h):
            open_ms = start_4h + i * step_4h
            close_ms = open_ms + step_4h - 1
            wave = math.sin(i * 0.1 + sym_idx) * 0.03 + (i * 0.0008)
            o_p = round(base_price * (1.0 + wave), 4)
            c_p = round(base_price * (1.0 + wave + 0.003), 4)
            h_p = round(max(o_p, c_p) * 1.008, 4)
            l_p = round(min(o_p, c_p) * 0.992, 4)
            vol = 1500.0 + (i % 10) * 100.0
            klines_4h.append([open_ms, o_p, h_p, l_p, c_p, vol, close_ms, vol * c_p, 6000, vol * 0.53])

        funding_rates = [
            {
                "symbol": sym,
                "funding_time_ms": start_1h + i * 8 * step_1h,
                "funding_rate": 0.0001 + (i % 3) * 0.00005,
                "mark_price": base_price,
            }
            for i in range(n_1h // 8)
        ]
        oi_hist = [
            {
                "symbol": sym,
                "timestamp": start_1h + i * step_1h,
                "sumOpenInterest": f"{10000.0 + i * 15.0:.2f}",
                "sumOpenInterestValue": f"{(10000.0 + i * 15.0) * base_price:.2f}",
            }
            for i in range(n_1h)
        ]
        taker_hist = [
            {"timestamp": start_1h + i * step_1h, "buySellRatio": "1.08"} for i in range(n_1h)
        ]
        gls_hist = [
            {"timestamp": start_1h + i * step_1h, "longShortRatio": "1.12"} for i in range(n_1h)
        ]
        top_pos_hist = [
            {"timestamp": start_1h + i * step_1h, "longShortRatio": "1.15"} for i in range(n_1h)
        ]
        top_acc_hist = [
            {"timestamp": start_1h + i * step_1h, "longShortRatio": "1.10"} for i in range(n_1h)
        ]
        basis_hist = [
            {
                "timestamp": start_1h + i * step_1h,
                "basisRate": f"{0.0002 + (i % 5) * 0.00005:.6f}",
                "futuresPrice": f"{base_price * 1.0003:.2f}",
                "indexPrice": f"{base_price:.2f}",
            }
            for i in range(n_1h)
        ]
        data[sym] = {
            "klines_15m": klines_15m,
            "klines_1h": klines_1h,
            "klines_4h": klines_4h,
            "funding_rates": funding_rates,
            "oi_hist": oi_hist,
            "taker_hist": taker_hist,
            "gls_hist": gls_hist,
            "top_pos_hist": top_pos_hist,
            "top_acc_hist": top_acc_hist,
            "basis_hist": basis_hist,
        }

    return {
        "anchor_end_ms": anchor_end_ms,
        "symbols": list(symbols),
        "data": data,
    }


def test_deterministic_manifest_replay_twice() -> None:
    """Identical input manifest must produce bit-for-bit identical output manifest and hashes across two runs."""
    raw = _make_synthetic_raw_cache(symbols=("BTCUSDT", "ETHUSDT"), n_15m=320)
    btc_closes = [int(r[6]) for r in raw["data"]["BTCUSDT"]["klines_15m"]]
    steps = btc_closes[260:272]
    s0 = btc_closes[256]
    s1 = steps[0]
    s2 = steps[4]
    s3 = steps[8]
    s4 = steps[-1] + 1

    partitions = [
        OOSPartitionSpec("OOS_P1", s0, s1, s1, s2),
        OOSPartitionSpec("OOS_P2", s0, s2, s2, s3),
        OOSPartitionSpec("OOS_P3", s0, s3, s3, s4),
    ]
    ds1 = ReplayDataset.from_raw_cache(
        raw, step_timestamps_ms=steps, partitions=partitions, data_end_ms=raw["anchor_end_ms"]
    )
    ds2 = ReplayDataset.from_raw_cache(
        raw, step_timestamps_ms=steps, partitions=partitions, data_end_ms=raw["anchor_end_ms"]
    )

    cfg = MarketWatchConfig(
        symbols=("BTCUSDT", "ETHUSDT"),
        relative_strength_universe=("BTCUSDT", "ETHUSDT"),
    )
    res1 = DeterministicTacticalReplayRunner(ds1, config=cfg, evaluate_grid_stride=4).run()
    res2 = DeterministicTacticalReplayRunner(ds2, config=cfg, evaluate_grid_stride=4).run()

    assert res1["input_manifest"]["input_manifest_hash"] == res2["input_manifest"]["input_manifest_hash"]
    assert res1["output_manifest"]["output_manifest_hash"] == res2["output_manifest"]["output_manifest_hash"]
    assert res1["output_manifest"]["evidence_ids_sha256"] == res2["output_manifest"]["evidence_ids_sha256"]
    assert res1["output_manifest"]["trend_shadow_ids_sha256"] == res2["output_manifest"]["trend_shadow_ids_sha256"]
    assert res1["pit_audit"]["pit_violations_count"] == 0


def test_pit_causality_enforced_in_replay_client_and_trend_shadow(tmp_path: Path) -> None:
    """PIT causality checks must reject future candles, future funding queries, and backward clock movement."""
    raw = _make_synthetic_raw_cache(symbols=("BTCUSDT", "ETHUSDT"), n_15m=300)
    btc_closes = [int(r[6]) for r in raw["data"]["BTCUSDT"]["klines_15m"]]
    step_ms = btc_closes[260]
    partitions = [
        OOSPartitionSpec("P1", btc_closes[250], btc_closes[255], btc_closes[255], btc_closes[265]),
        OOSPartitionSpec("P2", btc_closes[250], btc_closes[265], btc_closes[265], btc_closes[275]),
        OOSPartitionSpec("P3", btc_closes[250], btc_closes[275], btc_closes[275], btc_closes[285]),
    ]
    ds = ReplayDataset.from_raw_cache(raw, step_timestamps_ms=[step_ms], partitions=partitions)
    client = HistoricalReplayClient(ds, step_ms)

    # 1. All returned klines must have close_time_ms <= step_ms
    bars_15m = client.klines("BTCUSDT", "15m", 60)
    assert bars_15m
    assert max(c.close_time_ms for c in bars_15m) <= step_ms

    # 2. Requesting historical_klines or funding_rate_history beyond as_of_ms raises PITCausalityViolationError
    with pytest.raises(PITCausalityViolationError):
        client.historical_klines("BTCUSDT", "15m", step_ms - 3_600_000, step_ms + 900_000)

    with pytest.raises(PITCausalityViolationError):
        client.funding_rate_history("BTCUSDT", step_ms - 3_600_000, step_ms + 900_000)

    # 3. Moving replay clock backward without allow_reset raises PITCausalityViolationError
    with pytest.raises(PITCausalityViolationError):
        client.set_as_of_ms(step_ms - 1)

    # 4. TrendEvidenceV2Shadow rejects future or unclosed candles
    from unittest.mock import patch

    cfg = MarketWatchConfig(symbols=("BTCUSDT", "ETHUSDT"), relative_strength_universe=("BTCUSDT", "ETHUSDT"))
    store = MarketWatchStateStore(tmp_path / "pit_test.db")
    scanner = MarketWatchScanner(cfg, client, store)
    with patch("btc_quant_agent.market_watch.scanner.time.time", return_value=step_ms / 1000.0):
        snap, _, _ = scanner.collect_symbol_snapshot("BTCUSDT", step_ms)
    assert snap is not None

    future_candle = Candle(
        symbol="BTCUSDT",
        interval="15m",
        open_time_ms=step_ms + 1,
        close_time_ms=step_ms + 900_000,
        open=60000.0,
        high=60100.0,
        low=59900.0,
        close=60050.0,
        volume=100.0,
        closed=True,
        available_at_ms=step_ms + 900_000,
    )
    with pytest.raises(TrendShadowCausalityError):
        compute_trend_evidence_v2_shadow(
            snapshot=snap,
            closed_candles_15m=[*bars_15m, future_candle],
            closed_candles_1h=client.klines("BTCUSDT", "1h", 60),
            config=cfg,
        )


def test_rolling_window_chronology_validation_and_support_gates() -> None:
    """Chronological rolling OOS partitions must reject empty, overlapping, or calibration-leaking windows."""
    with pytest.raises(PITCausalityViolationError, match="At least one OOSPartitionSpec"):
        validate_oos_partitions([])

    # Overlapping OOS windows rejected
    with pytest.raises(PITCausalityViolationError, match="Overlapping or non-chronological"):
        validate_oos_partitions(
            [
                OOSPartitionSpec("P1", 100, 200, 200, 350),
                OOSPartitionSpec("P2", 100, 300, 300, 400),
                OOSPartitionSpec("P3", 100, 400, 400, 500),
            ]
        )

    # Calibration window leaking into OOS start rejected
    with pytest.raises(PITCausalityViolationError, match="violates calibration < oos ordering"):
        validate_oos_partitions(
            [
                OOSPartitionSpec("P1", 100, 250, 200, 300),
                OOSPartitionSpec("P2", 100, 300, 300, 400),
                OOSPartitionSpec("P3", 100, 400, 400, 500),
            ]
        )


def test_cost_accounting_enters_net_r_and_detects_sign_flip() -> None:
    """Transaction costs (fees, slippage, funding) must enter net_R and trigger FAIL on systematic cost omission."""
    integrity_ok = {
        "pit_chronology_manifest_integrity": True,
        "transaction_costs_included_in_net_r": True,
        "no_outcome_informed_policy_retuning": True,
        "no_protected_a_line_outcomes_accessed": True,
        "deterministic_manifest_replay_identical": True,
    }
    agg_sign_flip = {
        "actionable_signal_count": 120,
        "filled_count": 120,
        "target_stop_resolved_count": 120,
        "long_actionable_count": 60,
        "short_actionable_count": 60,
        "mean_gross_R": 0.12,
        "mean_net_R": -0.04,
        "median_net_R": -0.02,
        "stop_before_target": 0.50,
        "fees": {"mean_fee_r": 0.0},
        "slippage": {"mean_slippage_r": 0.0},
    }
    parts = [
        {"actionable_signal_count": 40, "mean_net_R": 0.02},
        {"actionable_signal_count": 40, "mean_net_R": 0.01},
        {"actionable_signal_count": 40, "mean_net_R": -0.05},
    ]
    gate = evaluate_decision_quality_gates(
        integrity_checks=integrity_ok,
        aggregate_oos=agg_sign_flip,
        partition_oos_list=parts,
    )
    assert gate["hard_negative_gates"]["systematic_cost_omission_sign_flip"] is True
    assert gate["decision"] == TacticalDecisionQualityDecision.FAIL.value


def test_mechanical_gate_evaluation_and_no_subgroup_rescue() -> None:
    """Frozen thresholds must classify PASS, DIAGNOSTIC_ONLY, and FAIL mechanically without subgroup rescue."""
    integrity_ok = {
        "pit_chronology_manifest_integrity": True,
        "transaction_costs_included_in_net_r": True,
        "no_outcome_informed_policy_retuning": True,
        "no_protected_a_line_outcomes_accessed": True,
        "deterministic_manifest_replay_identical": True,
    }

    # 1. Well-supported PASS case
    agg_pass = {
        "actionable_signal_count": 120,
        "filled_count": 120,
        "target_stop_resolved_count": 120,
        "long_actionable_count": 55,
        "short_actionable_count": 65,
        "mean_gross_R": 0.22,
        "mean_net_R": 0.09,
        "median_net_R": 0.01,
        "stop_before_target": 0.52,
        "fees": {"mean_fee_r": 0.09},
        "slippage": {"mean_slippage_r": 0.04},
    }
    parts_pass = [
        {"actionable_signal_count": 40, "mean_net_R": 0.11},
        {"actionable_signal_count": 40, "mean_net_R": 0.08},
        {"actionable_signal_count": 40, "mean_net_R": -0.02},
    ]
    res_pass = evaluate_decision_quality_gates(
        integrity_checks=integrity_ok,
        aggregate_oos=agg_pass,
        partition_oos_list=parts_pass,
        thresholds=FrozenReleaseThresholds(),
    )
    assert res_pass["decision"] == TacticalDecisionQualityDecision.PASS.value

    # 2. Under-powered sample -> DIAGNOSTIC_ONLY
    agg_low_support = dict(agg_pass, actionable_signal_count=45)
    res_diag = evaluate_decision_quality_gates(
        integrity_checks=integrity_ok,
        aggregate_oos=agg_low_support,
        partition_oos_list=parts_pass,
    )
    assert res_diag["decision"] == TacticalDecisionQualityDecision.DIAGNOSTIC_ONLY.value

    # 3. Aggregate hard FAIL cannot be rescued even if a partition or subgroup is positive
    agg_fail = dict(agg_pass, mean_net_R=-0.18, median_net_R=-0.35, stop_before_target=0.75)
    res_fail = evaluate_decision_quality_gates(
        integrity_checks=integrity_ok,
        aggregate_oos=agg_fail,
        partition_oos_list=parts_pass,
    )
    assert res_fail["decision"] == TacticalDecisionQualityDecision.FAIL.value
    assert res_fail["subgroup_rescue_permitted"] is False
    assert res_fail["subgroup_rescue_applied"] is False


def test_wp_b_evidence_json_integrity() -> None:
    """Verify generated RC1 WP-B EVIDENCE.json contains all required contract sections and proofs."""
    import json

    ev_path = REPO_ROOT / "evidence" / "v0.5.5" / "tactical-policy" / "RC1" / "WP_B" / "EVIDENCE.json"
    assert ev_path.exists(), f"Missing {ev_path}"
    payload = json.loads(ev_path.read_text(encoding="utf-8"))

    assert payload["task_id"] == "B_LINE_TACTICAL_DECISION_QUALITY_R1"
    assert payload["release_id"] == "B_LINE_INITIAL_USABLE_RELEASE_V1_RC1"
    assert payload["frozen_tactical_predecessor_sha"] == FROZEN_TACTICAL_PREDECESSOR_SHA
    assert payload["policy_version"] == "TACTICAL_POLICY_R2_B0"
    assert payload["config_hash"] == "27f7d4c835a36330"

    det = payload["deterministic_replay_verification"]
    assert det["identical_manifest_produces_identical_results"] is True
    assert det["run_1_input_manifest_hash"] == det["run_2_input_manifest_hash"]
    assert det["run_1_output_manifest_hash"] == det["run_2_output_manifest_hash"]

    assert len(payload["rolling_oos_table"]) >= 3
    assert payload["shadow_trend_diagnostics"]["authority"] == "SHADOW_ONLY"
    assert payload["shadow_trend_diagnostics"]["active_policy_influence"] == "NONE"
    assert payload["no_protected_a_line_outcomes_proof"]["protected_a_line_outcomes_accessed"] is False
    assert payload["executable_tactical_policy_unchanged_proof"]["zero_diff_on_executable_policy_files"] is True
    assert payload["gate_evaluation"]["subgroup_rescue_permitted"] is False
    assert payload["gate_evaluation"]["subgroup_rescue_applied"] is False


def test_trend_evidence_v2_shadow_all_12_fields_and_shadow_only_authority(tmp_path: Path) -> None:
    """TREND_EVIDENCE_V2_SHADOW must populate all 12 contract fields with SHADOW_ONLY authority and zero active impact."""
    raw = _make_synthetic_raw_cache(symbols=("BTCUSDT", "ETHUSDT"), n_15m=300)
    btc_closes = [int(r[6]) for r in raw["data"]["BTCUSDT"]["klines_15m"]]
    step_ms = btc_closes[270]
    partitions = [
        OOSPartitionSpec("P1", btc_closes[250], btc_closes[255], btc_closes[255], btc_closes[265]),
        OOSPartitionSpec("P2", btc_closes[250], btc_closes[265], btc_closes[265], btc_closes[275]),
        OOSPartitionSpec("P3", btc_closes[250], btc_closes[275], btc_closes[275], btc_closes[285]),
    ]
    ds = ReplayDataset.from_raw_cache(raw, step_timestamps_ms=[step_ms], partitions=partitions)
    client = HistoricalReplayClient(ds, step_ms)
    cfg = MarketWatchConfig(symbols=("BTCUSDT", "ETHUSDT"), relative_strength_universe=("BTCUSDT", "ETHUSDT"))
    store = MarketWatchStateStore(tmp_path / "shadow_test.db")
    scanner = MarketWatchScanner(cfg, client, store)

    assessments, _ = scanner.scan_universe(symbols=("BTCUSDT", "ETHUSDT"), notify=False)
    btc_a = next(a for a in assessments if a.symbol == "BTCUSDT")
    assert btc_a.feature_evidence is not None
    ev_id_before = btc_a.feature_evidence.evidence_id

    p_fund, p_basis = client.prior_funding_and_basis("BTCUSDT")
    ts = compute_trend_evidence_v2_shadow(
        snapshot=btc_a.snapshot,
        closed_candles_15m=client.klines("BTCUSDT", "15m", 60),
        closed_candles_1h=client.klines("BTCUSDT", "1h", 60),
        closed_candles_4h=client.klines("BTCUSDT", "4h", 40),
        config=cfg,
        feature_evidence_id=ev_id_before,
        prior_funding_rate=p_fund,
        prior_basis_bps=p_basis,
    )
    validate_trend_evidence_v2_shadow(ts)
    assert ts.schema_version == TREND_EVIDENCE_V2_SHADOW_SCHEMA_VERSION
    assert ts.authority == TREND_EVIDENCE_V2_SHADOW_AUTHORITY
    ts_dict = ts.to_dict()
    for field in REQUIRED_TREND_EVIDENCE_V2_SHADOW_FIELDS:
        assert field in ts_dict

    summary = summarize_trend_evidence_v2_shadow([ts], net_r_by_feature_id={ev_id_before: 0.25})
    assert summary["authority"] == "SHADOW_ONLY"
    assert summary["active_policy_influence"] == "NONE"
    assert btc_a.feature_evidence.evidence_id == ev_id_before


def test_frozen_policy_hash_identity_and_zero_executable_diff() -> None:
    """Executable Tactical policy files must have zero git diff against frozen predecessor SHA 52c16a28."""
    assert TACTICAL_POLICY_VERSION == "TACTICAL_POLICY_R2_B0"
    assert TACTICAL_DECISION_QUALITY_CONTRACT_VERSION == "V0.5.5_B_LINE_TACTICAL_DECISION_QUALITY_R1"
    cfg_hash = compute_market_watch_config_hash(MarketWatchConfig())
    assert cfg_hash == "27f7d4c835a36330"

    executable_files = [
        "src/btc_quant_agent/market_watch/config.py",
        "src/btc_quant_agent/market_watch/context.py",
        "src/btc_quant_agent/market_watch/derivatives.py",
        "src/btc_quant_agent/market_watch/domain.py",
        "src/btc_quant_agent/market_watch/entry_quality.py",
        "src/btc_quant_agent/market_watch/evidence.py",
        "src/btc_quant_agent/market_watch/grid_policy.py",
        "src/btc_quant_agent/market_watch/grid_shadow.py",
        "src/btc_quant_agent/market_watch/grid_shadow_evidence.py",
        "src/btc_quant_agent/market_watch/lifecycle.py",
        "src/btc_quant_agent/market_watch/playbooks.py",
        "src/btc_quant_agent/market_watch/ranking.py",
        "src/btc_quant_agent/market_watch/scanner.py",
        "src/btc_quant_agent/market_watch/shadow.py",
        "src/btc_quant_agent/market_watch/shadow_evidence.py",
        "src/btc_quant_agent/market_watch/snapshot.py",
        "src/btc_quant_agent/market_watch/state.py",
    ]
    diff_out = subprocess.check_output(
        ["git", "diff", "--name-only", FROZEN_TACTICAL_PREDECESSOR_SHA, "--", *executable_files],
        cwd=REPO_ROOT,
        text=True,
    ).strip()
    assert diff_out == ""
    assert compute_grid_diagnostic_metrics([])["authority"] == "DIAGNOSTIC_ONLY"
    assert compute_subset_metrics(label="EMPTY", evidences=[], evaluations=[])["sample_count"] == 0
    assert "setup_x_direction" in compute_subgroup_diagnostics(evidences=[], evaluations=[])
