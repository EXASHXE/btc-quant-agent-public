from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from .config import AppConfig, StrategyConfig
from .domain import (
    Candidate,
    Candle,
    Direction,
    Pivot,
    Regime,
    ScanResult,
    Setup,
    TimeframeFeatures,
)
from .multifactor import FactorAssessment, assess_factors, macro_aligned
from .regime import classify_regime
from .risk import build_position_plan
from .strategies import breakout_retest, trend_pullback
from .structure import confirmed_pivots


@dataclass(frozen=True)
class RegimeExplanation:
    regime: str
    primary_reason: str
    contributing_reasons: tuple[str, ...]


@dataclass(frozen=True)
class StageObservation:
    stage: str
    passed: bool
    predicate_passed: bool
    reason_code: str


@dataclass(frozen=True)
class SetupFunnelTrace:
    timestamp_ms: int
    year: int
    quarter: int
    direction: str
    setup: str
    regime: str
    stages: tuple[StageObservation, ...]
    candidate: Candidate | None
    target_source: str | None
    factor: FactorAssessment | None
    rr_gross: float | None
    rr_net: float | None
    risk_plan_pass: bool
    final_decision: str
    final_reason: str | None

    @property
    def failed_predicates(self) -> int:
        return sum(not item.predicate_passed for item in self.stages)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["failed_predicates"] = self.failed_predicates
        return payload


def explain_regime_classification(
    features: TimeframeFeatures, config: StrategyConfig
) -> RegimeExplanation:
    regime = classify_regime(features, config)
    if regime == Regime.HIGH_VOLATILITY:
        return RegimeExplanation(str(regime), "ATR_PERCENTILE_TOO_HIGH", ())
    if regime in (Regime.TREND_UP, Regime.TREND_DOWN):
        return RegimeExplanation(str(regime), "ALL_TREND_CONDITIONS_ALIGNED", ())
    if regime == Regime.RANGE:
        return RegimeExplanation(str(regime), "ADX_RANGE_THRESHOLD", ())

    ema_up = features.close > features.ema_mid > features.ema_slow
    ema_down = features.close < features.ema_mid < features.ema_slow
    slope_up = features.ema_mid_slope > 0 and features.ema_slow_slope >= 0
    slope_down = features.ema_mid_slope < 0 and features.ema_slow_slope <= 0
    reasons: list[str] = []
    if not (ema_up or ema_down):
        reasons.append("EMA_ORDER_MISMATCH")
    if not ((ema_up and slope_up) or (ema_down and slope_down)):
        reasons.append("SLOPE_MISMATCH")
    if features.adx < config.adx_trend_min:
        reasons.append("ADX_TOO_LOW")
    expected_structure = "HH_HL" if ema_up else "LH_LL" if ema_down else None
    if expected_structure is None or features.structure != expected_structure:
        reasons.append("STRUCTURE_MISMATCH")
    unique = tuple(dict.fromkeys(reasons))
    primary = unique[0] if len(unique) == 1 else "MULTIPLE_CONDITIONS"
    return RegimeExplanation(str(regime), primary, unique)


def _stage(
    output: list[StageObservation],
    name: str,
    predicate: bool,
    failure_reason: str,
) -> None:
    previously_passed = all(item.passed for item in output)
    passed = previously_passed and predicate
    reason = "PASS" if passed else failure_reason if previously_passed else "NOT_REACHED"
    output.append(StageObservation(name, passed, predicate, reason))


def _trend_trace(
    direction: Direction,
    candles: list[Candle],
    features_4h: TimeframeFeatures,
    features_1h: TimeframeFeatures,
    features_15m: TimeframeFeatures,
    regime: Regime,
    config: AppConfig,
    result: ScanResult,
    pivots: list[Pivot],
) -> SetupFunnelTrace:
    strategy = config.strategy
    latest = candles[-1]
    prior = candles[-2]
    recent = candles[-5:]
    supports = [pivot.price for pivot in pivots if pivot.kind == "LOW"]
    resistances = [pivot.price for pivot in pivots if pivot.kind == "HIGH"]
    expected_regime = Regime.TREND_UP if direction == Direction.LONG else Regime.TREND_DOWN
    structure_level = (
        features_15m.last_swing_low
        if direction == Direction.LONG
        else features_15m.last_swing_high
    )
    pullback_price = (
        min(bar.low for bar in recent)
        if direction == Direction.LONG
        else max(bar.high for bar in recent)
    )
    tolerance = strategy.pullback_atr_tolerance * features_15m.atr
    touched = features_15m.ema_mid - tolerance <= pullback_price <= features_15m.ema_mid + tolerance
    intact = (
        structure_level is not None
        and (
            pullback_price > structure_level
            if direction == Direction.LONG
            else pullback_price < structure_level
        )
    )
    reclaim = (
        latest.close > features_15m.ema_fast
        if direction == Direction.LONG
        else latest.close < features_15m.ema_fast
    )
    previous_break = latest.close > prior.high if direction == Direction.LONG else latest.close < prior.low
    volume_pass = features_15m.volume_z >= strategy.volume_z_min
    target_options = (
        [level for level in resistances if level > latest.close]
        if direction == Direction.LONG
        else [level for level in supports if level < latest.close]
    )
    not_extreme = latest.high - latest.low < strategy.extreme_bar_atr * features_15m.atr
    candidate = trend_pullback(candles, features_15m, regime, strategy)
    if candidate is not None and candidate.direction != direction:
        candidate = None

    stages: list[StageObservation] = []
    _stage(
        stages,
        "TP_01_REGIME_ELIGIBLE",
        len(candles) >= 6 and regime == expected_regime,
        "REGIME_NOT_ELIGIBLE",
    )
    _stage(stages, "TP_02_EXTREME_BAR_PASS", not_extreme, "EXTREME_BAR_REJECTED")
    _stage(stages, "TP_03_SWING_LEVEL_EXISTS", structure_level is not None, "SWING_LEVEL_MISSING")
    _stage(stages, "TP_04_EMA25_ZONE_TOUCHED", touched, "EMA25_ZONE_NOT_TOUCHED")
    _stage(stages, "TP_05_STRUCTURE_INTACT", intact, "STRUCTURE_BROKEN")
    _stage(stages, "TP_06_EMA7_RECLAIM", reclaim, "EMA7_NOT_RECLAIMED")
    _stage(stages, "TP_07_PREVIOUS_EXTREME_BREAK", previous_break, "PREVIOUS_EXTREME_NOT_BROKEN")
    _stage(stages, "TP_08_VOLUME_PASS", volume_pass, "VOLUME_BELOW_THRESHOLD")
    _stage(stages, "TP_09_TARGET_EXISTS", bool(target_options), "TARGET_MISSING")
    _stage(stages, "TP_10_PATTERN_CANDIDATE", candidate is not None, "PATTERN_NOT_CREATED")

    factor: FactorAssessment | None = None
    risk_plan = None
    if candidate is not None:
        factor = assess_factors(candidate, features_4h, features_1h, features_15m, None, strategy)
        macro_pass = macro_aligned(features_4h, direction)
        rsi_pass = (
            strategy.rsi_long_min <= features_15m.rsi <= strategy.rsi_long_max
            if direction == Direction.LONG
            else strategy.rsi_short_min <= features_15m.rsi <= strategy.rsi_short_max
        )
        score_pass = factor.score >= strategy.factor_score_min
        positive_pass = factor.positive_groups >= min(
            strategy.min_positive_factor_groups, len(factor.group_scores)
        )
        risk_plan = build_position_plan(candidate, features_15m.atr, strategy, config.risk)
    else:
        macro_pass = rsi_pass = score_pass = positive_pass = False
    _stage(stages, "TP_11_4H_MACRO_ALIGNED", macro_pass, "MACRO_MISALIGNED")
    _stage(stages, "TP_12_RSI_GATE", rsi_pass, "RSI_OUT_OF_RANGE")
    _stage(stages, "TP_13_FACTOR_SCORE", score_pass, "FACTOR_SCORE_BELOW_THRESHOLD")
    _stage(stages, "TP_14_POSITIVE_GROUPS", positive_pass, "POSITIVE_GROUPS_BELOW_THRESHOLD")
    _stage(stages, "TP_15_RR_RISK_PLAN", risk_plan is not None, "RISK_PLAN_REJECTED")
    confirmed = bool(
        result.signal
        and result.signal.setup == Setup.TREND_PULLBACK
        and result.signal.direction == direction
    )
    _stage(stages, "TP_16_CONFIRMED", confirmed, "NOT_CONFIRMED")
    timestamp = latest.close_time_ms + 1
    value = datetime.fromtimestamp(timestamp / 1000, UTC)
    return SetupFunnelTrace(
        timestamp,
        value.year,
        (value.month - 1) // 3 + 1,
        str(direction),
        str(Setup.TREND_PULLBACK),
        str(regime),
        tuple(stages),
        candidate,
        "CONFIRMED_LEVEL" if candidate else None,
        factor,
        risk_plan.rr_gross if risk_plan else None,
        risk_plan.rr_net if risk_plan else None,
        risk_plan is not None,
        result.action,
        result.reason_code,
    )


def _breakout_trace(
    direction: Direction,
    candles: list[Candle],
    features_4h: TimeframeFeatures,
    features_1h: TimeframeFeatures,
    features_15m: TimeframeFeatures,
    regime: Regime,
    config: AppConfig,
    result: ScanResult,
    pivots: list[Pivot],
) -> SetupFunnelTrace:
    strategy = config.strategy
    latest = candles[-1]
    breakout = candles[-2]
    expected_regime = Regime.TREND_UP if direction == Direction.LONG else Regime.TREND_DOWN
    directional = [
        pivot.price
        for pivot in pivots
        if pivot.kind == ("HIGH" if direction == Direction.LONG else "LOW")
    ]
    level = directional[-1] if directional else None
    min_breakout = strategy.breakout_atr_min * features_15m.atr
    tolerance = strategy.retest_atr_tolerance * features_15m.atr
    close_pass = bool(
        level is not None
        and (breakout.close > level if direction == Direction.LONG else breakout.close < level)
    )
    distance_pass = bool(
        level is not None
        and (
            breakout.close >= level + min_breakout
            if direction == Direction.LONG
            else breakout.close <= level - min_breakout
        )
    )
    touch_pass = bool(
        level is not None
        and (
            latest.low <= level + tolerance
            if direction == Direction.LONG
            else latest.high >= level - tolerance
        )
    )
    hold_pass = bool(
        level is not None
        and (latest.close > level if direction == Direction.LONG else latest.close < level)
    )
    continuation = latest.close > latest.open if direction == Direction.LONG else latest.close < latest.open
    volume_pass = features_15m.volume_z >= strategy.volume_z_min
    not_extreme = latest.high - latest.low < strategy.extreme_bar_atr * features_15m.atr
    candidate = breakout_retest(candles, features_15m, regime, strategy)
    if candidate is not None and candidate.direction != direction:
        candidate = None
    target_source = None
    if candidate is not None:
        target_source = "ATR_PROJECTION" if candidate.risks else "CONFIRMED_LEVEL"

    stages: list[StageObservation] = []
    _stage(
        stages,
        "BR_01_REGIME_ELIGIBLE",
        len(candles) >= 8 and regime == expected_regime,
        "REGIME_NOT_ELIGIBLE",
    )
    _stage(stages, "BR_02_EXTREME_BAR_PASS", not_extreme, "EXTREME_BAR_REJECTED")
    _stage(stages, "BR_03_CONFIRMED_PIVOT_EXISTS", level is not None, "PIVOT_MISSING")
    _stage(stages, "BR_04_BREAKOUT_CLOSE_PASS", close_pass, "BREAKOUT_CLOSE_FAILED")
    _stage(stages, "BR_05_BREAKOUT_DISTANCE_PASS", distance_pass, "BREAKOUT_DISTANCE_FAILED")
    _stage(stages, "BR_06_RETEST_TOUCH_PASS", touch_pass, "RETEST_NOT_TOUCHED")
    _stage(stages, "BR_07_RETEST_CLOSE_HOLDS_LEVEL", hold_pass, "RETEST_CLOSE_FAILED")
    _stage(stages, "BR_08_CONTINUATION_CANDLE", continuation, "CONTINUATION_CANDLE_FAILED")
    _stage(stages, "BR_09_VOLUME_PASS", volume_pass, "VOLUME_BELOW_THRESHOLD")
    _stage(stages, "BR_10_TARGET_EXISTS_OR_ATR_PROJECTION", True, "TARGET_UNAVAILABLE")
    _stage(stages, "BR_11_PATTERN_CANDIDATE", candidate is not None, "PATTERN_NOT_CREATED")

    factor: FactorAssessment | None = None
    risk_plan = None
    if candidate is not None:
        factor = assess_factors(candidate, features_4h, features_1h, features_15m, None, strategy)
        macro_pass = macro_aligned(features_4h, direction)
        rsi_pass = (
            strategy.rsi_long_min <= features_15m.rsi <= strategy.rsi_long_max
            if direction == Direction.LONG
            else strategy.rsi_short_min <= features_15m.rsi <= strategy.rsi_short_max
        )
        score_pass = factor.score >= strategy.factor_score_min
        positive_pass = factor.positive_groups >= min(
            strategy.min_positive_factor_groups, len(factor.group_scores)
        )
        risk_plan = build_position_plan(candidate, features_15m.atr, strategy, config.risk)
    else:
        macro_pass = rsi_pass = score_pass = positive_pass = False
    _stage(stages, "BR_12_4H_MACRO", macro_pass, "MACRO_MISALIGNED")
    _stage(stages, "BR_13_RSI", rsi_pass, "RSI_OUT_OF_RANGE")
    _stage(stages, "BR_14_FACTOR_SCORE", score_pass, "FACTOR_SCORE_BELOW_THRESHOLD")
    _stage(stages, "BR_15_POSITIVE_GROUPS", positive_pass, "POSITIVE_GROUPS_BELOW_THRESHOLD")
    _stage(stages, "BR_16_RISK_PLAN", risk_plan is not None, "RISK_PLAN_REJECTED")
    confirmed = bool(
        result.signal
        and result.signal.setup == Setup.BREAKOUT_RETEST
        and result.signal.direction == direction
    )
    _stage(stages, "BR_17_CONFIRMED", confirmed, "NOT_CONFIRMED")
    timestamp = latest.close_time_ms + 1
    value = datetime.fromtimestamp(timestamp / 1000, UTC)
    return SetupFunnelTrace(
        timestamp,
        value.year,
        (value.month - 1) // 3 + 1,
        str(direction),
        str(Setup.BREAKOUT_RETEST),
        str(regime),
        tuple(stages),
        candidate,
        target_source,
        factor,
        risk_plan.rr_gross if risk_plan else None,
        risk_plan.rr_net if risk_plan else None,
        risk_plan is not None,
        result.action,
        result.reason_code,
    )


def trace_setup_funnels(
    candles_15m: list[Candle],
    features_4h: TimeframeFeatures,
    features_1h: TimeframeFeatures,
    features_15m: TimeframeFeatures,
    regime: Regime,
    config: AppConfig,
    result: ScanResult,
) -> tuple[SetupFunnelTrace, ...]:
    strategy = config.strategy
    trend_pivots = confirmed_pivots(
        candles_15m[-strategy.level_lookback_bars :],
        strategy.pivot_left,
        strategy.pivot_right,
    )
    breakout_pivots = confirmed_pivots(
        candles_15m[-strategy.level_lookback_bars : -3],
        strategy.pivot_left,
        strategy.pivot_right,
    )
    return tuple(
        trace
        for direction in (Direction.LONG, Direction.SHORT)
        for trace in (
            _trend_trace(
                direction,
                candles_15m,
                features_4h,
                features_1h,
                features_15m,
                regime,
                config,
                result,
                trend_pivots,
            ),
            _breakout_trace(
                direction,
                candles_15m,
                features_4h,
                features_1h,
                features_15m,
                regime,
                config,
                result,
                breakout_pivots,
            ),
        )
    )
