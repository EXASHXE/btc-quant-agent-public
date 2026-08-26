from pathlib import Path

import pytest

from btc_quant_agent.config import AppConfig
from btc_quant_agent.funnel import SetupFunnelTrace, StageObservation
from btc_quant_agent.funnel_research import (
    DEV_END_MS,
    DEV_START_MS,
    _counterfactual_counts,
    assert_development_only_rows,
    run_funnel_diagnostic,
)


def _trace(failed: str | None = None) -> SetupFunnelTrace:
    names = (
        "BR_01_REGIME_ELIGIBLE", "BR_02_EXTREME_BAR_PASS",
        "BR_03_CONFIRMED_PIVOT_EXISTS", "BR_04_BREAKOUT_CLOSE_PASS",
        "BR_05_BREAKOUT_DISTANCE_PASS", "BR_06_RETEST_TOUCH_PASS",
        "BR_07_RETEST_CLOSE_HOLDS_LEVEL", "BR_08_CONTINUATION_CANDLE",
        "BR_09_VOLUME_PASS", "BR_10_TARGET_EXISTS_OR_ATR_PROJECTION",
        "BR_11_PATTERN_CANDIDATE", "BR_12_4H_MACRO", "BR_13_RSI",
        "BR_14_FACTOR_SCORE", "BR_15_POSITIVE_GROUPS", "BR_16_RISK_PLAN",
        "BR_17_CONFIRMED",
    )
    stages = tuple(
        StageObservation(name, name != failed, name != failed, "PASS" if name != failed else "FAIL")
        for name in names
    )
    return SetupFunnelTrace(
        DEV_START_MS, 2021, 1, "LONG", "BREAKOUT_RETEST", "TREND_UP",
        stages, None, None, None, None, None, False, "WAIT", "TEST",
    )


def test_single_gate_ablation_changes_only_declared_gate() -> None:
    counts = _counterfactual_counts(_trace("BR_13_RSI"))
    assert counts["D2"]
    assert not counts["D1"]
    assert not any(counts[name] for name in ("D3", "D4", "D5", "D6", "D7", "D8"))


def test_funnel_uses_development_period_only() -> None:
    with pytest.raises(ValueError, match="complete development period"):
        run_funnel_diagnostic([], AppConfig(), [])


def test_holdout_stays_sealed() -> None:
    protocol = Path("configs/research/v0.3.1_funnel_protocol.json").read_text(encoding="utf-8")
    assert '"holdout_policy": "FORBIDDEN"' in protocol


def test_candidate_events_have_no_holdout_rows() -> None:
    assert_development_only_rows([{"timestamp_ms": DEV_START_MS}])
    with pytest.raises(ValueError, match="holdout firewall"):
        assert_development_only_rows([{"timestamp_ms": DEV_END_MS}])
