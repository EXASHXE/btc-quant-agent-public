from __future__ import annotations

from typing import Any

from ..domain import Regime
from .config import MarketWatchConfig
from .domain import (
    BreakoutState,
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
    prev_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Evaluate Breakout + Retest playbook with strict sequential state.

    BAR N:
        CLOSED breakout beyond level by configured threshold.
        Breakout confirmation produces BREAKOUT_CONFIRMED.
    BAR N+1..N+k:
        price retests breakout level.
        LONG retest requires:
            low reaches configured ATR tolerance around level (low <= level + retest_tol)
            CLOSED candle finishes above level (close >= level)
        SHORT mirror:
            high reaches configured ATR tolerance around level (high >= level - retest_tol)
            CLOSED candle finishes below level (close <= level)
    Only after this:
        RETEST_CONFIRMED.
    A wick crossing or same-bar 'break+retest' MUST NOT satisfy this.
    """
    tc = config.thresholds
    atr = max(tf_15m.atr, 1e-6)
    closed_bar = tf_15m.latest_closed_bar
    current_bar_end_ms = tf_15m.closed_bar_end_time_ms

    st = prev_state or {}
    prev_bo_state = st.get("breakout_state")
    prev_bo_level = st.get("breakout_level")
    prev_bo_dir = st.get("breakout_direction")
    prev_bo_time = st.get("breakout_bar_end_ms")

    # Check for active prior breakout awaiting retest (strictly BAR N+1..N+k)
    if (
        prev_bo_state == BreakoutState.BREAKOUT_CONFIRMED
        and prev_bo_level is not None
        and prev_bo_time is not None
        and prev_bo_dir is not None
        and current_bar_end_ms > prev_bo_time
    ):
        bars_elapsed = max(1, int((current_bar_end_ms - prev_bo_time) / (15 * 60 * 1000)))
        if bars_elapsed <= tc.max_retest_bars:
            retest_tol = tc.retest_atr_tolerance * atr
            if prev_bo_dir == "LONG":
                level = float(prev_bo_level)
                retested = (closed_bar.low <= level + retest_tol) and (closed_bar.low >= level - retest_tol * 1.5)
                closed_above = closed_bar.close >= level
                if retested and closed_above and exhaustion.state != ExhaustionState.EXTREME:
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
                        "breakout_state": BreakoutState.RETEST_CONFIRMED,
                        "breakout_level": level,
                        "breakout_direction": "LONG",
                        "breakout_bar_end_ms": prev_bo_time,
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
            elif prev_bo_dir == "SHORT":
                level = float(prev_bo_level)
                retested = (closed_bar.high >= level - retest_tol) and (closed_bar.high <= level + retest_tol * 1.5)
                closed_below = closed_bar.close <= level
                if retested and closed_below and exhaustion.state != ExhaustionState.EXTREME:
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
                        "breakout_state": BreakoutState.RETEST_CONFIRMED,
                        "breakout_level": level,
                        "breakout_direction": "SHORT",
                        "breakout_bar_end_ms": prev_bo_time,
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

    # Evaluate new Bar N breakout candidates (strictly cannot be retest on same bar)
    if tf_1h.resistances:
        level = tf_1h.resistances[-1]
        min_break = tc.breakout_atr_threshold * atr
        min_vol_z = tc.min_volume_z

        failed_bo = st.get("recent_failed_breakout")
        failed_bo_ms = st.get("recent_failed_breakout_ms")
        has_failed_memory = False
        if (
            failed_bo is not None
            and failed_bo_ms is not None
            and abs(level - float(failed_bo)) / max(level, 1e-4) <= 0.02
            and (current_bar_end_ms - int(failed_bo_ms) <= tc.failed_level_ttl_ms)
        ):
            min_break *= tc.failed_level_breakout_mult
            min_vol_z = max(min_vol_z, tc.failed_level_min_volume_z)
            has_failed_memory = True

        if (
            closed_bar.close >= level + min_break
            and closed_bar.close > closed_bar.open
            and tf_15m.volume_z >= min_vol_z
            and exhaustion.state != ExhaustionState.EXTREME
        ):
            reasons = [
                "BREAKOUT_CONFIRMED",
                "WAITING_FOR_RETEST_CONFIRMATION",
            ]
            if has_failed_memory:
                reasons.append("FAILED_BREAKOUT_MEMORY_HIGHER_CONFIRMATION_MET")
            risks = ["AWAITING_CONFIRMED_RETEST"]
            if derivatives.oi_1h_change is not None and derivatives.oi_1h_change <= 0:
                risks.append("BREAKOUT_LOW_PARTICIPATION")
            return {
                "decision": DirectionalDecision.WAIT,
                "setup": PlaybookType.BREAKOUT_RETEST,
                "breakout_state": BreakoutState.BREAKOUT_CONFIRMED,
                "breakout_level": level,
                "breakout_direction": "LONG",
                "breakout_bar_end_ms": current_bar_end_ms,
                "entry_low": level,
                "entry_high": closed_bar.close,
                "stop_loss": level - 0.3 * atr,
                "take_profit_1": closed_bar.close + 2.5 * atr,
                "take_profit_2": closed_bar.close + 4.0 * atr,
                "invalidation": level - tc.retest_atr_tolerance * atr,
                "confidence": ConfidenceBand.MEDIUM,
                "reasons": reasons,
                "risks": risks,
            }

    if tf_1h.supports:
        level = tf_1h.supports[-1]
        min_break = tc.breakout_atr_threshold * atr
        min_vol_z = tc.min_volume_z

        failed_bd = st.get("recent_failed_breakdown")
        failed_bd_ms = st.get("recent_failed_breakdown_ms")
        has_failed_memory = False
        if (
            failed_bd is not None
            and failed_bd_ms is not None
            and abs(level - float(failed_bd)) / max(level, 1e-4) <= 0.02
            and (current_bar_end_ms - int(failed_bd_ms) <= tc.failed_level_ttl_ms)
        ):
            min_break *= tc.failed_level_breakout_mult
            min_vol_z = max(min_vol_z, tc.failed_level_min_volume_z)
            has_failed_memory = True

        if (
            closed_bar.close <= level - min_break
            and closed_bar.close < closed_bar.open
            and tf_15m.volume_z >= min_vol_z
            and exhaustion.state != ExhaustionState.EXTREME
        ):
            reasons = [
                "BREAKDOWN_CONFIRMED",
                "WAITING_FOR_RETEST_CONFIRMATION",
            ]
            if has_failed_memory:
                reasons.append("FAILED_BREAKDOWN_MEMORY_HIGHER_CONFIRMATION_MET")
            risks = ["AWAITING_CONFIRMED_RETEST"]
            if derivatives.oi_1h_change is not None and derivatives.oi_1h_change <= 0:
                risks.append("BREAKDOWN_LOW_PARTICIPATION")
            return {
                "decision": DirectionalDecision.WAIT,
                "setup": PlaybookType.BREAKOUT_RETEST,
                "breakout_state": BreakoutState.BREAKOUT_CONFIRMED,
                "breakout_level": level,
                "breakout_direction": "SHORT",
                "breakout_bar_end_ms": current_bar_end_ms,
                "entry_low": closed_bar.close,
                "entry_high": level,
                "stop_loss": level + 0.3 * atr,
                "take_profit_1": closed_bar.close - 2.5 * atr,
                "take_profit_2": closed_bar.close - 4.0 * atr,
                "invalidation": level + tc.retest_atr_tolerance * atr,
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

    Strict sequence:
    1. Prior compression window (has_prior_compression_window)
    2. Closed structure breakout (above resistance/swing high or below support/swing low)
    3. ATR + Volume expansion (volume_z >= 1.0 and atr_percentile >= 0.70)
    EMA crossing alone is strictly insufficient.
    """
    atr = max(tf_15m.atr, 1e-6)

    # 1. Require actual prior compression window
    has_prior_comp = (
        tf_15m.has_prior_compression_window
        or tf_1h.has_prior_compression_window
        or tf_15m.is_volatility_compressed
        or tf_1h.is_volatility_compressed
        or (tf_15m.bb_width_percentile <= 0.25)
        or (tf_1h.bb_width_percentile <= 0.25)
    )
    if not has_prior_comp:
        return None

    # 2. Require ATR and Volume expansion
    is_expanding = tf_15m.volume_z >= 1.0 and tf_15m.atr_percentile >= 0.70
    if not is_expanding:
        return None

    if exhaustion.state == ExhaustionState.EXTREME:
        return None

    closed_bar = tf_15m.latest_closed_bar

    # 3. Closed structure breakout (not EMA crossing alone)
    res = (
        tf_15m.resistances[-1]
        if tf_15m.resistances
        else (
            tf_15m.recent_swing_high
            if tf_15m.recent_swing_high
            else (tf_1h.resistances[-1] if tf_1h.resistances else (tf_1h.recent_swing_high or (tf_15m.ema_fast + 0.5 * atr)))
        )
    )
    if closed_bar.close > res and closed_bar.close > closed_bar.open:
        return {
            "decision": DirectionalDecision.LONG,
            "setup": PlaybookType.VOLATILITY_EXPANSION,
            "entry_low": max(res, tf_15m.ema_fast),
            "entry_high": tf_15m.close,
            "stop_loss": tf_15m.close - 1.5 * atr,
            "take_profit_1": tf_15m.close + 2.5 * atr,
            "take_profit_2": tf_15m.close + 4.0 * atr,
            "invalidation": res - 0.2 * atr,
            "confidence": ConfidenceBand.MEDIUM,
            "reasons": [
                "PRIOR_COMPRESSION_WINDOW_CONFIRMED",
                "STRUCTURE_BREAKOUT_CONFIRMED",
                "ATR_AND_VOLUME_SURGE",
            ],
            "risks": ["CHASE_RISK_IF_FAST_REVERSAL"],
        }

    sup = (
        tf_15m.supports[-1]
        if tf_15m.supports
        else (
            tf_15m.recent_swing_low
            if tf_15m.recent_swing_low
            else (tf_1h.supports[-1] if tf_1h.supports else (tf_1h.recent_swing_low or (tf_15m.ema_fast - 0.5 * atr)))
        )
    )
    if closed_bar.close < sup and closed_bar.close < closed_bar.open:
        return {
            "decision": DirectionalDecision.SHORT,
            "setup": PlaybookType.VOLATILITY_EXPANSION,
            "entry_low": tf_15m.close,
            "entry_high": min(sup, tf_15m.ema_fast),
            "stop_loss": tf_15m.close + 1.5 * atr,
            "take_profit_1": tf_15m.close - 2.5 * atr,
            "take_profit_2": tf_15m.close - 4.0 * atr,
            "invalidation": sup + 0.2 * atr,
            "confidence": ConfidenceBand.MEDIUM,
            "reasons": [
                "PRIOR_COMPRESSION_WINDOW_CONFIRMED",
                "STRUCTURE_BREAKOUT_CONFIRMED",
                "ATR_AND_VOLUME_SURGE",
            ],
            "risks": ["CHASE_RISK_IF_FAST_REVERSAL"],
        }

    return None
