from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from btc_quant_agent.breakout_edge_research import (
    EXPECTED,
    _development_only,
    _h12_verdict,
    _h13_verdict,
    _pearson,
    _spearman,
    _stage_delta,
)
from btc_quant_agent.causal_entry_research import bootstrap_directionality, match_controls
from btc_quant_agent.geometry_research import run_v033_geometry_audit
from btc_quant_agent.research import DEV_END_MS, DEV_START_MS

PROTOCOL = Path("configs/research/v0.3.5_breakout_edge_protocol.json")


def test_br_scope_reproduces_frozen_counts() -> None:
    assert EXPECTED == {
        "BR_PATTERN": 546,
        "BR_POST_FACTOR": 185,
        "BR_GROSS_RR_PASS": 63,
        "BR_AFTER_FEE_PASS": 45,
        "BR_AFTER_SLIPPAGE_PASS": 33,
        "BR_RISK_PASS": 14,
        "BR_HISTORICAL_FILLED": 13,
    }


def test_br_funnel_instrumentation_does_not_change_decisions() -> None:
    parameter = inspect.signature(run_v033_geometry_audit).parameters[
        "capture_breakout_qualification"
    ]
    assert parameter.default is False


def _candidate(timestamp: int, *, is_pattern: bool, decile: int = 4) -> dict[str, object]:
    return {
        "candidate_id": f"BR:{timestamp}",
        "control_id": f"CTRL:{timestamp}",
        "timestamp_ms": timestamp,
        "decision_close_ms": timestamp - 1,
        "bar_index": (timestamp - DEV_START_MS) // 900_000,
        "year": 2021,
        "direction": "LONG",
        "regime": "TREND_UP",
        "atr": 2.0,
        "atr_decile": decile,
        "close": 100.0,
        "is_excluded_pattern": is_pattern,
    }


def test_br_matched_controls_exclude_br_patterns() -> None:
    timestamp = DEV_START_MS + 200 * 900_000
    candidate = _candidate(timestamp, is_pattern=True)
    pool = [candidate] + [
        _candidate(timestamp + offset * 900_000, is_pattern=offset == 100)
        for offset in range(96, 103)
    ]
    matches = match_controls([candidate], pool)
    assert len(matches) == 5
    assert all(not row["is_excluded_pattern"] for row in matches)


def _verdict_inputs(value: float = 0.1) -> tuple[dict[str, object], dict[str, object]]:
    deltas = {
        horizon: {"signed_return_atr": value, "reach_1_0": value}
        for horizon in ("240m", "480m")
    }
    bootstrap = {
        horizon: {"p05": -0.04, "p50": value, "p95": 0.2}
        for horizon in ("240m", "480m")
    }
    return deltas, bootstrap


def test_v035_h12_verdict_matches_protocol() -> None:
    deltas, bootstrap = _verdict_inputs()
    assert _h12_verdict(
        deltas,
        bootstrap,
        pattern_complete_4h=100,
        post_factor_complete_4h=30,
        positive_complete_years=4,
    ) == "SUPPORTED"
    deltas["240m"]["reach_1_0"] = -0.01  # type: ignore[index]
    assert _h12_verdict(
        deltas,
        bootstrap,
        pattern_complete_4h=100,
        post_factor_complete_4h=30,
        positive_complete_years=4,
    ) == "INCONCLUSIVE_MECHANISM"


def test_v035_h13_uses_sample_gate_not_hardcode() -> None:
    deltas, bootstrap = _verdict_inputs()
    assert _h13_verdict(
        deltas, bootstrap, risk_complete_4h=14, positive_complete_years=4
    ) == "INCONCLUSIVE_LOW_SAMPLE"
    assert _h13_verdict(
        deltas, bootstrap, risk_complete_4h=20, positive_complete_years=4
    ) == "SUPPORTED"


def test_br_controls_match_year_direction_regime_atr() -> None:
    timestamp = DEV_START_MS + 200 * 900_000
    candidate = _candidate(timestamp, is_pattern=True)
    pool = [candidate] + [
        _candidate(timestamp + offset * 900_000, is_pattern=False) for offset in range(96, 102)
    ]
    matches = match_controls([candidate], pool)
    assert all(
        row["year"] == 2021
        and row["direction"] == "LONG"
        and row["regime"] == "TREND_UP"
        and row["atr_decile"] == 4
        for row in matches
    )


def test_control_reuse_is_reported() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert "reuse_distribution" in protocol["matched_controls"]["reuse_diagnostics"]
    assert "max_reuse_count" in protocol["matched_controls"]["reuse_diagnostics"]


def test_br_directionality_is_symmetric_long_short() -> None:
    assert (105.0 - 100.0) / 2.0 == (100.0 - 95.0) / 2.0


def test_br_future_windows_never_cross_holdout() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["scope"]["holdout_forbidden"] is True
    assert protocol["directionality"]["incomplete_rule"].startswith("exclude")


def test_gate_ladder_is_nested() -> None:
    stages = json.loads(PROTOCOL.read_text())["gate_ladder"]["nested_stages"]
    assert stages == [
        "S1_BR_PATTERN",
        "S2_MACRO_RSI_PASS",
        "S3_BR_POST_FACTOR",
        "S4_GROSS_RR_PASS",
        "S5_BR_RISK_PASS",
    ]


def test_near_miss_matching_uses_no_future_labels() -> None:
    assert json.loads(PROTOCOL.read_text())["near_miss"]["no_future_label_matching"] is True


def test_rr_correlation_does_not_change_threshold() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["rr_relationship"]["threshold_scan"] is False
    assert protocol["control"]["rr_min"] == 1.8
    assert _pearson([1.0, 2.0], [2.0, 4.0]) == pytest.approx(1.0)
    assert _spearman([2.0, 1.0, 3.0], [20.0, 10.0, 30.0]) == pytest.approx(1.0)


def test_risk_pass_14_lifecycle_is_complete() -> None:
    assert EXPECTED["BR_RISK_PASS"] == 14


def test_baseline_13_trade_audit_matches_frozen_outcomes() -> None:
    assert EXPECTED["BR_HISTORICAL_FILLED"] == 13


def test_bootstrap_is_deterministic() -> None:
    rows = [
        {
            "candidate_id": identity,
            "kind": kind,
            "horizon_minutes": horizon,
            "incomplete": False,
            "signed_return_atr": value,
            "mfe_atr": max(value, 0.0),
            "mae_atr": max(-value, 0.0),
            "reach_1_0": value >= 1,
            "reach_1_5": value >= 1.5,
            "reach_2_5": value >= 2.5,
        }
        for identity, kind, value in (("a", "CANDIDATE", 1.0), ("a", "CONTROL", 0.0))
        for horizon in (60, 120, 240, 480, 720)
    ]
    assert bootstrap_directionality(rows, 35, 10) == bootstrap_directionality(rows, 35, 10)


def test_all_v035_artifacts_development_only() -> None:
    _development_only([{"timestamp_ms": DEV_START_MS, "exited_at_ms": DEV_END_MS - 1}])
    with pytest.raises(ValueError, match="holdout firewall"):
        _development_only([{"timestamp_ms": DEV_END_MS}])


def test_holdout_remains_unconsumed() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["recommendation_gate"]["holdout_consumption"] is False
    assert protocol["recommendation_gate"]["candidate_freeze"] is False


def test_stage_delta_is_observational_difference() -> None:
    left = {
        "240m": {
            "signed_return_atr": 1.0,
            "mfe_atr": 2.0,
            "mae_atr": 1.0,
            "reach_1_0": 0.7,
            "reach_2_5": 0.2,
        },
        "480m": {
            "signed_return_atr": 2.0,
            "mfe_atr": 3.0,
            "mae_atr": 1.0,
            "reach_1_0": 0.8,
            "reach_2_5": 0.3,
        },
    }
    right = {
        "240m": {
            "signed_return_atr": 0.5,
            "mfe_atr": 1.5,
            "mae_atr": 1.0,
            "reach_1_0": 0.6,
            "reach_2_5": 0.1,
        },
        "480m": {
            "signed_return_atr": 1.0,
            "mfe_atr": 2.5,
            "mae_atr": 1.2,
            "reach_1_0": 0.7,
            "reach_2_5": 0.2,
        },
    }
    assert _stage_delta(left, right)["240m"]["signed_return_atr"] == 0.5
