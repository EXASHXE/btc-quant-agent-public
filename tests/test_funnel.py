from dataclasses import replace
from unittest.mock import patch

from btc_quant_agent.config import AppConfig
from btc_quant_agent.domain import Candle, Pivot, Regime, ScanResult, TimeframeFeatures
from btc_quant_agent.funnel import explain_regime_classification, trace_setup_funnels
from btc_quant_agent.multifactor import assess_factors
from btc_quant_agent.regime import classify_regime
from btc_quant_agent.strategies import breakout_retest, trend_pullback


def _feature(**changes: object) -> TimeframeFeatures:
    base = TimeframeFeatures(
        close=103.0,
        ema_fast=102.0,
        ema_mid=100.0,
        ema_slow=95.0,
        ema_mid_slope=1.0,
        ema_slow_slope=0.5,
        atr=2.0,
        atr_percentile=0.5,
        adx=28.0,
        volume_z=1.0,
        rsi=55.0,
        roc=0.01,
        bb_width_percentile=0.5,
        cvd_slope=1.0,
        cvd_available=True,
        last_swing_high=110.0,
        previous_swing_high=105.0,
        last_swing_low=90.0,
        previous_swing_low=85.0,
        structure="HH_HL",
        bar_open_time_ms=0,
        bar_close_time_ms=1,
    )
    return replace(base, **changes)


def _bar(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        "BTCUSDT", "15m", index * 900_000, (index + 1) * 900_000 - 1,
        open_, high, low, close, 10.0,
    )


def _result() -> ScanResult:
    return ScanResult("WAIT", "OK", "diagnostic fixture", reason_code="NO_SETUP")


def test_regime_explanation_matches_classifier() -> None:
    config = AppConfig().strategy
    cases = (
        _feature(),
        _feature(atr_percentile=0.95),
        _feature(adx=10.0),
        _feature(structure="MIXED"),
        _feature(
            close=90.0, ema_fast=92.0, ema_mid=95.0, ema_slow=100.0,
            ema_mid_slope=-1.0, ema_slow_slope=-0.5, structure="LH_LL",
        ),
    )
    for features in cases:
        assert explain_regime_classification(features, config).regime == str(
            classify_regime(features, config)
        )


@patch(
    "btc_quant_agent.funnel.confirmed_pivots",
    return_value=[Pivot("LOW", 1, 3, 90.0, 0), Pivot("HIGH", 2, 4, 110.0, 0)],
)
@patch(
    "btc_quant_agent.strategies.confirmed_pivots",
    return_value=[Pivot("LOW", 1, 3, 90.0, 0), Pivot("HIGH", 2, 4, 110.0, 0)],
)
def test_trend_pullback_stage_predicates_match_strategy_logic(
    _strategy_pivots: object, _funnel_pivots: object
) -> None:
    candles = [
        _bar(0, 101, 102, 100.5, 101.5), _bar(1, 101, 102, 100.4, 101.4),
        _bar(2, 101, 102, 99.9, 101.3), _bar(3, 101, 102, 100.2, 101.5),
        _bar(4, 101.5, 102.5, 100.4, 102.0), _bar(5, 102, 103.5, 101, 103),
    ]
    features = _feature()
    expected = trend_pullback(candles, features, Regime.TREND_UP, AppConfig().strategy)
    traces = trace_setup_funnels(
        candles, features, features, features, Regime.TREND_UP, AppConfig(), _result()
    )
    long_trace = next(item for item in traces if item.setup == "TREND_PULLBACK" and item.direction == "LONG")
    assert long_trace.stages[9].predicate_passed == (expected is not None)


@patch(
    "btc_quant_agent.funnel.confirmed_pivots",
    return_value=[Pivot("HIGH", 2, 4, 100.0, 0)],
)
@patch(
    "btc_quant_agent.strategies.confirmed_pivots",
    return_value=[Pivot("HIGH", 2, 4, 100.0, 0)],
)
def test_breakout_stage_predicates_match_strategy_logic(
    _strategy_pivots: object, _funnel_pivots: object
) -> None:
    candles = [_bar(i, 99, 99.8, 98.5, 99.2) for i in range(6)]
    candles.extend([_bar(6, 99.8, 101.2, 99.7, 101), _bar(7, 100.1, 101, 99.9, 100.8)])
    features = _feature(ema_fast=99.0)
    expected = breakout_retest(candles, features, Regime.TREND_UP, AppConfig().strategy)
    traces = trace_setup_funnels(
        candles, features, features, features, Regime.TREND_UP, AppConfig(), _result()
    )
    long_trace = next(item for item in traces if item.setup == "BREAKOUT_RETEST" and item.direction == "LONG")
    assert long_trace.stages[10].predicate_passed == (expected is not None)


def test_setup_funnel_regime_denominator_matches_classifier() -> None:
    candles = [_bar(i, 99, 100, 98, 99) for i in range(8)]
    features = _feature()
    traces = trace_setup_funnels(
        candles, features, features, features, Regime.TREND_UP, AppConfig(), _result()
    )
    assert sum(item.stages[0].predicate_passed for item in traces) == 2
    assert all(
        item.stages[0].predicate_passed == (
            item.direction == "LONG"
        )
        for item in traces
    )


def test_funnel_regime_denominator_matches_classifier() -> None:
    test_setup_funnel_regime_denominator_matches_classifier()


def test_extreme_bar_is_separate_funnel_stage() -> None:
    candles = [_bar(i, 99, 100, 98, 99) for i in range(7)]
    candles.append(_bar(7, 99, 110, 90, 99))
    features = _feature(atr=2.0)
    traces = trace_setup_funnels(
        candles, features, features, features, Regime.TREND_UP, AppConfig(), _result()
    )
    long_traces = [item for item in traces if item.direction == "LONG"]
    assert all(item.stages[0].predicate_passed for item in long_traces)
    assert all(item.stages[1].stage.endswith("EXTREME_BAR_PASS") for item in long_traces)
    assert all(not item.stages[1].predicate_passed for item in long_traces)


def test_funnel_stage_labels_match_predicates() -> None:
    candles = [_bar(i, 99, 100, 98, 99) for i in range(8)]
    features = _feature()
    traces = trace_setup_funnels(
        candles, features, features, features, Regime.TREND_UP, AppConfig(), _result()
    )
    for trace in traces:
        assert trace.stages[0].stage.endswith("REGIME_ELIGIBLE")
        assert trace.stages[1].stage.endswith("EXTREME_BAR_PASS")
        assert trace.stages[0].predicate_passed == (trace.direction == "LONG")


def test_funnel_instrumentation_does_not_change_decision() -> None:
    candles = [_bar(i, 99, 100, 98, 99) for i in range(8)]
    result = _result()
    before = result.as_dict()
    trace_setup_funnels(
        candles, _feature(), _feature(), _feature(), Regime.RANGE, AppConfig(), result
    )
    assert result.as_dict() == before


@patch(
    "btc_quant_agent.funnel.confirmed_pivots",
    return_value=[Pivot("HIGH", 2, 4, 100.0, 0)],
)
@patch(
    "btc_quant_agent.strategies.confirmed_pivots",
    return_value=[Pivot("HIGH", 2, 4, 100.0, 0)],
)
def test_factor_trace_matches_assessment(
    _strategy_pivots: object, _funnel_pivots: object
) -> None:
    candles = [_bar(i, 99, 99.8, 98.5, 99.2) for i in range(6)]
    candles.extend([_bar(6, 99.8, 101.2, 99.7, 101), _bar(7, 100.1, 101, 99.9, 100.8)])
    features = _feature(ema_fast=99.0)
    trace = next(
        item for item in trace_setup_funnels(
            candles, features, features, features, Regime.TREND_UP, AppConfig(), _result()
        ) if item.candidate is not None
    )
    assert trace.factor == assess_factors(
        trace.candidate, features, features, features, None, AppConfig().strategy
    )
