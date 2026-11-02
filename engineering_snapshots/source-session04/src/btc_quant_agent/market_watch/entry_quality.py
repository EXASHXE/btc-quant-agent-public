from __future__ import annotations

from .config import MarketWatchConfig
from .domain import (
    DerivativesMetrics,
    DerivativesRegime,
    DirectionalDecision,
    EntryQuality,
    ExhaustionMetrics,
    ExhaustionState,
    TimeframeSnapshot,
)


def evaluate_exhaustion(
    tf: TimeframeSnapshot,
    derivatives: DerivativesMetrics | None,
    config: MarketWatchConfig,
) -> ExhaustionMetrics:
    """Evaluate whether price is extended from short- and intermediate-term means.

    Output:
    - NORMAL
    - ELEVATED
    - EXTREME (blocks chasing current trend direction)
    """
    tc = config.thresholds
    atr = max(tf.atr, 1e-6)
    close = tf.close

    dist_ema20_atr = (close - tf.ema_fast) / atr
    dist_ema50_atr = (close - tf.ema_mid) / atr

    sup = tf.recent_swing_low or (close - 2.0 * atr)
    res = tf.recent_swing_high or (close + 2.0 * atr)
    dist_to_support_atr = max(0.0, (close - sup) / atr)
    dist_to_resistance_atr = max(0.0, (res - close) / atr)

    # Multi-bar return approximation from ROC
    multi_bar_extension_atr = (close * tf.roc_12bars) / atr

    reasons: list[str] = []
    abs_d20 = abs(dist_ema20_atr)
    abs_d50 = abs(dist_ema50_atr)

    # Check for funding / derivative crowding synergy with extension
    is_crowded = False
    if derivatives is not None and derivatives.regime in (
        DerivativesRegime.LONG_CROWDING,
        DerivativesRegime.SHORT_CROWDING,
    ):
        is_crowded = True

    if abs_d20 >= tc.extreme_overextension_ema20_atr or abs_d50 >= tc.overextension_ema50_atr:
        state = ExhaustionState.EXTREME
        reasons.append("OVEREXTENDED_FROM_MEAN")
        reasons.append("DO_NOT_CHASE")
        reasons.append("WAIT_FOR_PULLBACK")
        reasons.append("MOMENTUM_EXHAUSTION_RISK")
        if is_crowded:
            reasons.append("CROWDED_EXTENSION")
    elif abs_d20 >= tc.overextension_ema20_atr:
        state = ExhaustionState.ELEVATED
        reasons.append("ELEVATED_EXTENSION_FROM_EMA")
        if is_crowded:
            reasons.append("CROWDED_EXTENSION")
    else:
        state = ExhaustionState.NORMAL

    return ExhaustionMetrics(
        state=state,
        distance_from_ema20_atr=dist_ema20_atr,
        distance_from_ema50_atr=dist_ema50_atr,
        distance_to_support_atr=dist_to_support_atr,
        distance_to_resistance_atr=dist_to_resistance_atr,
        recent_extension_atr=abs_d20,
        multi_bar_extension_atr=multi_bar_extension_atr,
        reasons=tuple(reasons),
    )


def calculate_net_risk_reward(
    *,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    direction: DirectionalDecision,
    config: MarketWatchConfig,
    funding_rate: float | None = None,
) -> tuple[float, float]:
    """Calculate gross and net risk/reward accounting for fees, slippage, and funding friction.

    Returns (gross_rr, net_rr).
    """
    if entry_price <= 0 or stop_loss <= 0 or take_profit <= 0:
        return 0.0, 0.0

    if direction == DirectionalDecision.LONG:
        gross_risk = entry_price - stop_loss
        gross_reward = take_profit - entry_price
    elif direction == DirectionalDecision.SHORT:
        gross_risk = stop_loss - entry_price
        gross_reward = entry_price - take_profit
    else:
        return 0.0, 0.0

    if gross_risk <= 0 or gross_reward <= 0:
        return 0.0, 0.0

    gross_rr = gross_reward / gross_risk

    # Friction accounting
    round_trip_fee = 2.0 * config.taker_fee_rate
    round_trip_slippage = 2.0 * (config.slippage_bps_per_side / 10_000.0)

    # Adverse funding cost estimate
    obs_funding = funding_rate if funding_rate is not None else 0.0
    if direction == DirectionalDecision.LONG:
        adverse_funding = max(obs_funding, config.funding_stress_rate)
    else:
        adverse_funding = max(-obs_funding, config.funding_stress_rate)
    funding_cost = adverse_funding * 2.0  # estimate 2 funding periods holding

    stop_pct = gross_risk / entry_price
    reward_pct = gross_reward / entry_price

    total_loss_cost_pct = stop_pct + round_trip_fee + round_trip_slippage + funding_cost
    total_reward_cost_pct = round_trip_fee + round_trip_slippage + funding_cost

    net_reward_pct = reward_pct - total_reward_cost_pct
    if total_loss_cost_pct <= 0 or net_reward_pct <= 0:
        return gross_rr, 0.0

    net_rr = net_reward_pct / total_loss_cost_pct
    return round(gross_rr, 2), round(net_rr, 2)


def evaluate_entry_quality(
    *,
    direction: DirectionalDecision,
    exhaustion: ExhaustionMetrics,
    net_rr: float,
    tf_15m: TimeframeSnapshot,
    derivatives: DerivativesMetrics | None,
    config: MarketWatchConfig,
) -> tuple[EntryQuality, tuple[str, ...], tuple[str, ...]]:
    """Determine whether current location represents an attractive entry or a chase."""
    reasons: list[str] = []
    risks: list[str] = []
    tc = config.thresholds

    if direction == DirectionalDecision.WAIT:
        return EntryQuality.POOR, ("NO_DIRECTIONAL_DECISION",), ()

    # Rule 1: EXTREME overextension fatally degrades entry quality
    if exhaustion.state == ExhaustionState.EXTREME:
        reasons.extend(exhaustion.reasons)
        risks.append("CHASE_INTO_EXTREME_EXTENSION")
        return EntryQuality.POOR, tuple(reasons), tuple(risks)

    # Rule 2: Friction & Net RR floor check
    if net_rr < config.min_net_rr:
        reasons.append("INSUFFICIENT_NET_RR")
        risks.append(f"NET_RR_{net_rr:.2f}_BELOW_{config.min_net_rr:.2f}")
        return EntryQuality.MARGINAL, tuple(reasons), tuple(risks)

    # Rule 3: Spread check
    if (
        derivatives is not None
        and derivatives.spread_bps is not None
        and derivatives.spread_bps > tc.max_spread_bps
    ):
        risks.append("WIDE_SPREAD_FRICTION")
        return EntryQuality.MARGINAL, tuple(reasons), tuple(risks)

    # Entry geometry
    dist_ema = abs(exhaustion.distance_from_ema20_atr)
    close_to_mean = dist_ema <= tc.pullback_ema_tolerance_atr
    volume_conf = tf_15m.volume_z >= tc.min_volume_z

    score = 0
    if close_to_mean:
        score += 2
        reasons.append("PRICE_CLOSE_TO_KEY_EMA")
    elif dist_ema <= tc.overextension_ema20_atr:
        score += 1
        reasons.append("MODERATE_DISTANCE_FROM_EMA")
    else:
        score -= 1
        risks.append("PRICE_STRETCHED_FROM_EMA")

    if volume_conf:
        score += 1
        reasons.append("PARTICIPATION_HEALTHY")
    else:
        score -= 1
        risks.append("LOW_VOLUME_CONFIRMATION")

    if net_rr >= config.high_quality_net_rr:
        score += 2
        reasons.append("EXCELLENT_NET_RR")
    elif net_rr >= config.min_net_rr:
        score += 1
        reasons.append("ACCEPTABLE_NET_RR")

    if derivatives is not None:
        if (direction == DirectionalDecision.LONG and derivatives.regime == DerivativesRegime.HEALTHY_LONG_BUILD) or (
            direction == DirectionalDecision.SHORT and derivatives.regime == DerivativesRegime.HEALTHY_SHORT_BUILD
        ):
            score += 2
            reasons.append("DERIVATIVES_ALIGNED")
        elif (direction == DirectionalDecision.LONG and derivatives.regime == DerivativesRegime.LONG_CROWDING) or (
            direction == DirectionalDecision.SHORT and derivatives.regime == DerivativesRegime.SHORT_CROWDING
        ):
            score -= 2
            risks.append("DERIVATIVES_CROWDED_ADVERSE")
        elif derivatives.regime == DerivativesRegime.DELEVERAGING:
            score -= 2
            risks.append("DELEVERAGING_ENVIRONMENT")

    if score >= 5 and exhaustion.state == ExhaustionState.NORMAL:
        return EntryQuality.EXCELLENT, tuple(reasons), tuple(risks)
    if score >= 3:
        return EntryQuality.GOOD, tuple(reasons), tuple(risks)
    if score >= 1:
        return EntryQuality.MARGINAL, tuple(reasons), tuple(risks)
    return EntryQuality.POOR, tuple(reasons), tuple(risks)
