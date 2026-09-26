from __future__ import annotations

from typing import Any

from ..domain import Regime
from .config import MarketWatchConfig
from .domain import (
    ConfidenceBand,
    DerivativesMetrics,
    DerivativesRegime,
    DirectionalDecision,
    ExhaustionMetrics,
    ExhaustionState,
    PlaybookType,
    TimeframeSnapshot,
)


def evaluate_timeframe_alignment(
    tf_4h: TimeframeSnapshot,
    tf_1h: TimeframeSnapshot,
    tf_15m: TimeframeSnapshot,
) -> tuple[str, list[str]]:
    """Determine multi-timeframe role alignment and conflict reason codes."""
    reasons: list[str] = []

    # 4H macro bias
    macro_up = tf_4h.regime == Regime.TREND_UP
    macro_down = tf_4h.regime == Regime.TREND_DOWN

    # 1H operational trend
    trend_up = tf_1h.regime == Regime.TREND_UP
    trend_down = tf_1h.regime == Regime.TREND_DOWN

    # 15m execution
    exec_up = tf_15m.close > tf_15m.ema_fast
    exec_down = tf_15m.close < tf_15m.ema_fast

    if macro_up and trend_up and exec_up:
        reasons.append("HTF_LTF_ALIGNED")
        reasons.append("FOUR_HOUR_TREND_DOMINANT")
        return "ALIGNED_LONG", reasons
    if macro_down and trend_down and exec_down:
        reasons.append("HTF_LTF_ALIGNED")
        reasons.append("FOUR_HOUR_TREND_DOMINANT")
        return "ALIGNED_SHORT", reasons

    if macro_up and trend_down:
        reasons.append("HTF_LTF_CONFLICT")
        reasons.append("ONE_HOUR_COUNTER_TREND")
        return "CONFLICT", reasons
    if macro_down and trend_up:
        reasons.append("HTF_LTF_CONFLICT")
        reasons.append("ONE_HOUR_TRANSITION")
        return "CONFLICT", reasons

    if not macro_up and not macro_down and (trend_up or trend_down):
        reasons.append("ONE_HOUR_TREND_DOMINANT")
        return "ONE_HOUR_ONLY", reasons

    reasons.append("TIME_FRAMES_MIXED")
    return "MIXED", reasons


def evaluate_trend_pullback(
    *,
    tf_4h: TimeframeSnapshot,
    tf_1h: TimeframeSnapshot,
    tf_15m: TimeframeSnapshot,
    derivatives: DerivativesMetrics,
    exhaustion: ExhaustionMetrics,
    config: MarketWatchConfig,
) -> dict[str, Any] | None:
    """Evaluate Trend Pullback playbook strictly using closed bar confirmations."""
    tc = config.thresholds
    atr = max(tf_15m.atr, 1e-6)

    # 4H macro alignment check
    if tf_4h.regime == Regime.TREND_UP and tf_1h.regime == Regime.TREND_UP:
        # Looking for Long pullback
        if exhaustion.state == ExhaustionState.EXTREME and exhaustion.distance_from_ema20_atr > 0:
            return None  # Overextended to the upside

        # Check if 15m pulled back toward EMA20/EMA50
        dist_ema20 = (tf_15m.close - tf_15m.ema_fast) / atr
        dist_ema50 = (tf_15m.close - tf_15m.ema_mid) / atr

        # In a pullback, price touched or approached EMA20/50 without breaking structure
        floor = tf_15m.recent_swing_low or (tf_15m.close - 1.5 * atr)
        pullback_valid = (
            abs(dist_ema20) <= tc.pullback_ema_tolerance_atr * 1.5
            or abs(dist_ema50) <= tc.pullback_ema_tolerance_atr * 1.5
        ) and (tf_15m.close > floor)

        # Closed bar re-acceleration confirmation: 15m closed above EMA20 and close > open
        closed_confirmed = tf_15m.close > tf_15m.latest_closed_bar.open and tf_15m.close >= tf_15m.ema_fast

        if pullback_valid and closed_confirmed:
            target_candidates = [r for r in tf_1h.resistances if r > tf_15m.close]
            tp1 = min(target_candidates) if target_candidates else (tf_15m.close + 2.0 * atr)
            tp2 = tp1 + 1.5 * atr
            stop_loss = floor - 0.2 * atr
            invalidation = floor

            reasons = [
                "4H_1H_TREND_UP_ALIGNED",
                "15M_PULLBACK_CONFIRMED",
                "CLOSED_BAR_REACCELERATION",
            ]
            risks = []
            if derivatives.regime == DerivativesRegime.LONG_CROWDING:
                risks.append("LONG_CROWDING_PRESENT")

            return {
                "decision": DirectionalDecision.LONG,
                "setup": PlaybookType.TREND_PULLBACK,
                "entry_low": min(tf_15m.close, tf_15m.ema_fast),
                "entry_high": max(tf_15m.close, tf_15m.ema_fast),
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "invalidation": invalidation,
                "confidence": ConfidenceBand.HIGH if tf_1h.adx >= 25 else ConfidenceBand.MEDIUM,
                "reasons": reasons,
                "risks": risks,
            }

    if tf_4h.regime == Regime.TREND_DOWN and tf_1h.regime == Regime.TREND_DOWN:
        # Looking for Short pullback
        if exhaustion.state == ExhaustionState.EXTREME and exhaustion.distance_from_ema20_atr < 0:
            return None  # Overextended to the downside

        dist_ema20 = (tf_15m.close - tf_15m.ema_fast) / atr
        dist_ema50 = (tf_15m.close - tf_15m.ema_mid) / atr
        ceiling = tf_15m.recent_swing_high or (tf_15m.close + 1.5 * atr)

        pullback_valid = (
            abs(dist_ema20) <= tc.pullback_ema_tolerance_atr * 1.5
            or abs(dist_ema50) <= tc.pullback_ema_tolerance_atr * 1.5
        ) and (tf_15m.close < ceiling)

        closed_confirmed = tf_15m.close < tf_15m.latest_closed_bar.open and tf_15m.close <= tf_15m.ema_fast

        if pullback_valid and closed_confirmed:
            target_candidates = [s for s in tf_1h.supports if s < tf_15m.close]
            tp1 = max(target_candidates) if target_candidates else (tf_15m.close - 2.0 * atr)
            tp2 = tp1 - 1.5 * atr
            stop_loss = ceiling + 0.2 * atr
            invalidation = ceiling

            reasons = [
                "4H_1H_TREND_DOWN_ALIGNED",
                "15M_PULLBACK_CONFIRMED",
                "CLOSED_BAR_REACCELERATION",
            ]
            risks = []
            if derivatives.regime == DerivativesRegime.SHORT_CROWDING:
                risks.append("SHORT_CROWDING_PRESENT")

            return {
                "decision": DirectionalDecision.SHORT,
                "setup": PlaybookType.TREND_PULLBACK,
                "entry_low": min(tf_15m.close, tf_15m.ema_fast),
                "entry_high": max(tf_15m.close, tf_15m.ema_fast),
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "invalidation": invalidation,
                "confidence": ConfidenceBand.HIGH if tf_1h.adx >= 25 else ConfidenceBand.MEDIUM,
                "reasons": reasons,
                "risks": risks,
            }

    return None


def evaluate_breakout_retest(
    *,
    tf_1h: TimeframeSnapshot,
    tf_15m: TimeframeSnapshot,
    derivatives: DerivativesMetrics,
    exhaustion: ExhaustionMetrics,
    config: MarketWatchConfig,
) -> dict[str, Any] | None:
    """Evaluate Breakout + Retest playbook.

    Rules:
    - Breakout must be confirmed on CLOSED candle (close > R + breakout_threshold)
    - Retest: low approaches R, closed bar remains above R
    - Reject wick-only breakout or open-candle-only
    """
    tc = config.thresholds
    atr = max(tf_15m.atr, 1e-6)
    closed_bar = tf_15m.latest_closed_bar

    # Bullish breakout retest
    if tf_1h.resistances:
        level = tf_1h.resistances[-1]
        retest_tol = tc.retest_atr_tolerance * atr
        min_break = tc.breakout_atr_threshold * atr

        # Confirm that breakout already closed above level and retest held
        if (
            closed_bar.close >= level + min_break * 0.5
            and closed_bar.low <= level + retest_tol
            and closed_bar.close > closed_bar.open
            and exhaustion.state != ExhaustionState.EXTREME
        ):
            tp1 = tf_15m.close + 2.5 * atr
            tp2 = tf_15m.close + 4.0 * atr
            stop_loss = level - 0.3 * atr
            invalidation = level - retest_tol

            reasons = [
                "BREAKOUT_CONFIRMED",
                "RETEST_CONFIRMED",
                "CLOSED_BAR_HOLDING_ABOVE_RESISTANCE",
            ]
            risks = []
            if derivatives.oi_1h_change is not None and derivatives.oi_1h_change <= 0:
                risks.append("BREAKOUT_LOW_PARTICIPATION")

            return {
                "decision": DirectionalDecision.LONG,
                "setup": PlaybookType.BREAKOUT_RETEST,
                "entry_low": level,
                "entry_high": tf_15m.close,
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "invalidation": invalidation,
                "confidence": ConfidenceBand.MEDIUM,
                "reasons": reasons,
                "risks": risks,
            }

    # Bearish breakdown retest
    if tf_1h.supports:
        level = tf_1h.supports[-1]
        retest_tol = tc.retest_atr_tolerance * atr
        min_break = tc.breakout_atr_threshold * atr

        if (
            closed_bar.close <= level - min_break * 0.5
            and closed_bar.high >= level - retest_tol
            and closed_bar.close < closed_bar.open
            and exhaustion.state != ExhaustionState.EXTREME
        ):
            tp1 = tf_15m.close - 2.5 * atr
            tp2 = tf_15m.close - 4.0 * atr
            stop_loss = level + 0.3 * atr
            invalidation = level + retest_tol

            reasons = [
                "BREAKDOWN_CONFIRMED",
                "RETEST_CONFIRMED",
                "CLOSED_BAR_HOLDING_BELOW_SUPPORT",
            ]
            risks = []
            if derivatives.oi_1h_change is not None and derivatives.oi_1h_change <= 0:
                risks.append("BREAKDOWN_LOW_PARTICIPATION")

            return {
                "decision": DirectionalDecision.SHORT,
                "setup": PlaybookType.BREAKOUT_RETEST,
                "entry_low": tf_15m.close,
                "entry_high": level,
                "stop_loss": stop_loss,
                "take_profit_1": tp1,
                "take_profit_2": tp2,
                "invalidation": invalidation,
                "confidence": ConfidenceBand.MEDIUM,
                "reasons": reasons,
                "risks": risks,
            }

    return None


def evaluate_failed_breakout(
    *,
    tf_1h: TimeframeSnapshot,
    tf_15m: TimeframeSnapshot,
    derivatives: DerivativesMetrics,
    config: MarketWatchConfig,
) -> dict[str, Any] | None:
    """Evaluate Failed Breakout / Failed Breakdown.

    Detects:
    - Bullish breakout failure: price poked above resistance but closed candle lost level decisively,
      especially with rising OI or positive crowded funding -> FAILED_BREAKOUT_BEARISH_WATCH.
    - Bearish breakdown failure: price traded below support but closed back above level.
    """
    closed_bar = tf_15m.latest_closed_bar
    atr = max(tf_15m.atr, 1e-6)

    # Bullish failure
    if tf_1h.resistances:
        level = tf_1h.resistances[-1]
        # Bar poked above level but closed back below it (wick rejection)
        if closed_bar.high > level and closed_bar.close < level:
            reasons = [
                "FAILED_BREAKOUT_DETECTED",
                "CLOSED_BACK_BELOW_RESISTANCE",
            ]
            risks: list[str] = []
            if derivatives.oi_1h_change is not None and derivatives.oi_1h_change > 0:
                reasons.append("OI_EXPANDED_ON_FAILURE_LONGS_TRAPPED")
            if derivatives.funding_rate is not None and derivatives.funding_rate > 0:
                reasons.append("FUNDING_POSITIVE_LONGS_TRAPPED")

            reasons.append("FAILED_BREAKOUT_BEARISH_WATCH")

            return {
                "decision": DirectionalDecision.WAIT,
                "setup": PlaybookType.FAILED_BREAKOUT,
                "entry_low": 0.0,
                "entry_high": 0.0,
                "stop_loss": closed_bar.high + 0.2 * atr,
                "take_profit_1": tf_15m.close - 2.0 * atr,
                "take_profit_2": tf_15m.close - 3.5 * atr,
                "invalidation": closed_bar.high,
                "failed_level": level,
                "confidence": ConfidenceBand.MEDIUM,
                "reasons": reasons,
                "risks": risks,
            }

    # Bearish breakdown failure
    if tf_1h.supports:
        level = tf_1h.supports[-1]
        # Bar poked below level but closed back above it (wick rejection)
        if closed_bar.low < level and closed_bar.close > level:
            reasons = [
                "FAILED_BREAKDOWN_DETECTED",
                "CLOSED_BACK_ABOVE_SUPPORT",
            ]
            risks = []
            if derivatives.oi_1h_change is not None and derivatives.oi_1h_change > 0:
                reasons.append("OI_EXPANDED_ON_FAILURE_SHORTS_TRAPPED")

            reasons.append("FAILED_BREAKDOWN_BULLISH_WATCH")

            return {
                "decision": DirectionalDecision.WAIT,
                "setup": PlaybookType.FAILED_BREAKDOWN,
                "entry_low": 0.0,
                "entry_high": 0.0,
                "stop_loss": closed_bar.low - 0.2 * atr,
                "take_profit_1": tf_15m.close + 2.0 * atr,
                "take_profit_2": tf_15m.close + 3.5 * atr,
                "invalidation": closed_bar.low,
                "failed_level": level,
                "confidence": ConfidenceBand.MEDIUM,
                "reasons": reasons,
                "risks": risks,
            }

    return None


def evaluate_volatility_expansion(
    *,
    tf_1h: TimeframeSnapshot,
    tf_15m: TimeframeSnapshot,
    derivatives: DerivativesMetrics,
    exhaustion: ExhaustionMetrics,
    config: MarketWatchConfig,
) -> dict[str, Any] | None:
    """Evaluate Volatility Expansion playbook.

    Prior compression (BB width low) -> sudden ATR/Volume expansion on closed break.
    """
    atr = max(tf_15m.atr, 1e-6)

    # 1H or 15m was compressed, now expanding
    was_compressed = tf_1h.is_volatility_compressed or tf_15m.bb_width_percentile <= 0.25
    is_expanding = tf_15m.volume_z >= 1.0 and tf_15m.atr_percentile >= 0.70

    if was_compressed and is_expanding and exhaustion.state != ExhaustionState.EXTREME:
        closed_bar = tf_15m.latest_closed_bar
        if closed_bar.close > tf_15m.ema_fast and closed_bar.close > closed_bar.open:
            return {
                "decision": DirectionalDecision.LONG,
                "setup": PlaybookType.VOLATILITY_EXPANSION,
                "entry_low": tf_15m.ema_fast,
                "entry_high": tf_15m.close,
                "stop_loss": tf_15m.close - 1.5 * atr,
                "take_profit_1": tf_15m.close + 2.5 * atr,
                "take_profit_2": tf_15m.close + 4.0 * atr,
                "invalidation": tf_15m.close - 1.2 * atr,
                "confidence": ConfidenceBand.MEDIUM,
                "reasons": [
                    "VOLATILITY_COMPRESSION_TO_EXPANSION",
                    "ATR_AND_VOLUME_SURGE",
                ],
                "risks": ["CHASE_RISK_IF_FAST_REVERSAL"],
            }
        if closed_bar.close < tf_15m.ema_fast and closed_bar.close < closed_bar.open:
            return {
                "decision": DirectionalDecision.SHORT,
                "setup": PlaybookType.VOLATILITY_EXPANSION,
                "entry_low": tf_15m.close,
                "entry_high": tf_15m.ema_fast,
                "stop_loss": tf_15m.close + 1.5 * atr,
                "take_profit_1": tf_15m.close - 2.5 * atr,
                "take_profit_2": tf_15m.close - 4.0 * atr,
                "invalidation": tf_15m.close + 1.2 * atr,
                "confidence": ConfidenceBand.MEDIUM,
                "reasons": [
                    "VOLATILITY_COMPRESSION_TO_EXPANSION",
                    "ATR_AND_VOLUME_SURGE",
                ],
                "risks": ["CHASE_RISK_IF_FAST_REVERSAL"],
            }

    return None
