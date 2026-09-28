from __future__ import annotations

from .config import MarketWatchConfig
from .domain import DerivativesMetrics, DerivativesRegime, DirectionalDecision


def evaluate_derivatives_regime(
    price_change_1h_pct: float | None,
    derivatives: DerivativesMetrics,
    config: MarketWatchConfig,
) -> tuple[DerivativesRegime, tuple[str, ...], tuple[str, ...]]:
    """Deterministic evaluation of derivatives state machine based on price and OI interactions.

    Core principles:
    - PRICE UP + OI UP: genuine participation potentially supporting trend
    - PRICE UP + OI DOWN: short covering, lower continuation confidence
    - PRICE DOWN + OI UP: fresh short pressure / trapped longs
    - PRICE DOWN + OI DOWN: deleveraging / liquidation, avoid blind short chasing
    - Funding extremes + crowded ratios: crowding penalty
    """
    tc = config.thresholds
    reasons: list[str] = []
    risks: list[str] = []

    oi_1h = derivatives.oi_1h_change
    oi_4h = derivatives.oi_4h_change
    funding = derivatives.funding_rate
    taker = derivatives.taker_buy_sell_ratio
    gls = derivatives.global_account_long_short_ratio
    ttp = derivatives.top_trader_position_ratio

    # If critical derivative metrics are missing
    if oi_1h is None and funding is None:
        return DerivativesRegime.UNKNOWN, ("DERIVATIVES_DATA_UNAVAILABLE",), ()

    # Crowding checks
    is_long_crowded = False
    is_short_crowded = False

    if funding is not None:
        if funding >= tc.funding_extreme_abs:
            risks.append("FUNDING_RATE_EXTREME_LONG")
            is_long_crowded = True
        elif funding >= tc.funding_crowding_abs:
            risks.append("FUNDING_RATE_ELEVATED_LONG")
            if gls is not None and gls >= tc.global_long_crowding_ratio:
                is_long_crowded = True
        elif funding <= -tc.funding_extreme_abs:
            risks.append("FUNDING_RATE_EXTREME_SHORT")
            is_short_crowded = True
        elif funding <= -tc.funding_crowding_abs:
            risks.append("FUNDING_RATE_ELEVATED_SHORT")
            if gls is not None and gls <= tc.global_short_crowding_ratio:
                is_short_crowded = True

    if gls is not None:
        if gls >= tc.global_long_crowding_ratio:
            risks.append("GLOBAL_ACCOUNT_LONG_CROWDED")
            is_long_crowded = True
        elif gls <= tc.global_short_crowding_ratio:
            risks.append("GLOBAL_ACCOUNT_SHORT_CROWDED")
            is_short_crowded = True

    if ttp is not None:
        if ttp >= tc.top_trader_crowding_ratio:
            risks.append("TOP_TRADER_LONG_HEAVY")
            if funding is not None and funding >= tc.funding_crowding_abs:
                is_long_crowded = True
        elif ttp <= (1.0 / tc.top_trader_crowding_ratio):
            risks.append("TOP_TRADER_SHORT_HEAVY")
            if funding is not None and funding <= -tc.funding_crowding_abs:
                is_short_crowded = True

    # Sharp deleveraging check
    if (oi_1h is not None and oi_1h <= -0.04) or (oi_4h is not None and oi_4h <= -0.07):
        risks.append("SHARP_DELEVERAGING_ACTIVE")
        if price_change_1h_pct is not None and price_change_1h_pct < -0.005:
            reasons.append("LONG_LIQUIDATION_CASCADE")
            risks.append("DO_NOT_CHASE_SHORT")
            return DerivativesRegime.LONG_LIQUIDATION, tuple(reasons), tuple(risks)
        return DerivativesRegime.DELEVERAGING, tuple(reasons), tuple(risks)

    # Price down + long crowding
    if price_change_1h_pct is not None and price_change_1h_pct < -0.002 and is_long_crowded:
        reasons.append("PRICE_FALLING_INTO_LONG_CROWDING")
        reasons.append("STRONGER_BEARISH_CONFIRMATION")
        return DerivativesRegime.LONG_CROWDING, tuple(reasons), tuple(risks)

    # Price up + short crowding
    if price_change_1h_pct is not None and price_change_1h_pct > 0.002 and is_short_crowded:
        reasons.append("PRICE_RISING_INTO_SHORT_CROWDING")
        reasons.append("SHORT_SQUEEZE_RISK_FOR_BEARS")
        return DerivativesRegime.SHORT_CROWDING, tuple(reasons), tuple(risks)

    # Leverage build without directional movement
    if price_change_1h_pct is not None and abs(price_change_1h_pct) < 0.003 and (oi_1h is not None and oi_1h >= 0.025):
        reasons.append("OPEN_INTEREST_EXPANDING_IN_RANGE")
        return DerivativesRegime.LEVERAGE_BUILD_NO_DIRECTION, tuple(reasons), tuple(risks)

    # Directional interactions with OI
    if oi_1h is not None and price_change_1h_pct is not None:
        # Price UP + OI UP
        if price_change_1h_pct >= 0.003 and oi_1h >= 0.005 and not is_long_crowded:
            reasons.append("PRICE_UP_OI_UP_EXPANSION")
            if taker is not None and taker >= 1.0:
                reasons.append("TAKER_BUY_CONFIRMATION")
            return DerivativesRegime.HEALTHY_LONG_BUILD, tuple(reasons), tuple(risks)

        # Price DOWN + OI UP
        if price_change_1h_pct <= -0.003 and oi_1h >= 0.005 and not is_short_crowded:
            reasons.append("PRICE_DOWN_OI_UP_PRESSURE")
            if taker is not None and taker <= 1.0:
                reasons.append("TAKER_SELL_CONFIRMATION")
            return DerivativesRegime.HEALTHY_SHORT_BUILD, tuple(reasons), tuple(risks)

        # Price UP + OI DOWN
        if price_change_1h_pct >= 0.005 and oi_1h <= -0.008:
            reasons.append("PRICE_UP_OI_DOWN")
            risks.append("SHORT_COVERING_RALLY")
            risks.append("LOWER_CONTINUATION_CONFIDENCE")
            return DerivativesRegime.SHORT_COVERING, tuple(reasons), tuple(risks)

        # Price DOWN + OI DOWN
        if price_change_1h_pct <= -0.005 and oi_1h <= -0.008:
            reasons.append("PRICE_DOWN_OI_DOWN")
            risks.append("LONG_LIQUIDATION_UNWIND")
            risks.append("DO_NOT_CHASE_SHORT")
            return DerivativesRegime.LONG_LIQUIDATION, tuple(reasons), tuple(risks)

    if is_long_crowded:
        return DerivativesRegime.LONG_CROWDING, tuple(reasons), tuple(risks)
    if is_short_crowded:
        return DerivativesRegime.SHORT_CROWDING, tuple(reasons), tuple(risks)

    reasons.append("DERIVATIVES_BALANCED")
    return DerivativesRegime.NEUTRAL, tuple(reasons), tuple(risks)


def is_severe_long_crowding(derivatives: DerivativesMetrics, config: MarketWatchConfig | None = None) -> bool:
    """Determine if long crowding is severe enough to gate directional Long actions to WAIT."""
    cfg = config or MarketWatchConfig()
    tc = cfg.thresholds
    funding = derivatives.funding_rate
    gls = derivatives.global_account_long_short_ratio
    ttp = derivatives.top_trader_position_ratio

    if funding is not None and isinstance(funding, (int, float)) and funding >= tc.funding_extreme_abs:
        return True
    if (
        funding is not None
        and isinstance(funding, (int, float))
        and funding >= tc.funding_crowding_abs
        and gls is not None
        and isinstance(gls, (int, float))
        and gls >= tc.global_long_crowding_ratio
    ):
        return True
    if (
        funding is not None
        and isinstance(funding, (int, float))
        and funding >= tc.funding_crowding_abs
        and ttp is not None
        and isinstance(ttp, (int, float))
        and ttp >= tc.top_trader_crowding_ratio
    ):
        return True
    if gls is not None and isinstance(gls, (int, float)) and gls >= tc.global_long_crowding_ratio * 1.2:
        return True
    return bool(ttp is not None and isinstance(ttp, (int, float)) and ttp >= tc.top_trader_crowding_ratio * 1.25)


def is_severe_short_crowding(derivatives: DerivativesMetrics, config: MarketWatchConfig | None = None) -> bool:
    """Determine if short crowding is severe enough to gate directional Short actions to WAIT."""
    cfg = config or MarketWatchConfig()
    tc = cfg.thresholds
    funding = derivatives.funding_rate
    gls = derivatives.global_account_long_short_ratio
    ttp = derivatives.top_trader_position_ratio

    if funding is not None and isinstance(funding, (int, float)) and funding <= -tc.funding_extreme_abs:
        return True
    if (
        funding is not None
        and isinstance(funding, (int, float))
        and funding <= -tc.funding_crowding_abs
        and gls is not None
        and isinstance(gls, (int, float))
        and gls <= tc.global_short_crowding_ratio
    ):
        return True
    if (
        funding is not None
        and isinstance(funding, (int, float))
        and funding <= -tc.funding_crowding_abs
        and ttp is not None
        and isinstance(ttp, (int, float))
        and ttp <= (1.0 / tc.top_trader_crowding_ratio)
    ):
        return True
    if gls is not None and isinstance(gls, (int, float)) and gls <= tc.global_short_crowding_ratio * 0.8:
        return True
    return bool(ttp is not None and isinstance(ttp, (int, float)) and ttp <= (1.0 / (tc.top_trader_crowding_ratio * 1.25)))


def apply_derivatives_action_gate(
    *,
    decision: DirectionalDecision,
    derivatives: DerivativesMetrics,
    config: MarketWatchConfig,
) -> tuple[DirectionalDecision, tuple[str, ...], tuple[str, ...]]:
    """Enforce Derivatives Action Gate.

    Rules:
    - SHORT + LONG_LIQUIDATION / DELEVERAGING => WAIT with DO_NOT_CHASE_SHORT.
    - LONG + severe LONG_CROWDING => WAIT.
    - SHORT + severe SHORT_CROWDING => WAIT.
    - Moderate crowding remains score penalty only (handled in opportunity scoring).
    """
    if decision == DirectionalDecision.WAIT:
        return decision, (), ()

    reasons: list[str] = []
    risks: list[str] = []

    if decision == DirectionalDecision.SHORT:
        if derivatives.regime in (DerivativesRegime.LONG_LIQUIDATION, DerivativesRegime.DELEVERAGING):
            reasons.append("DERIVATIVES_VETO_SHORT_ON_LIQUIDATION_UNWIND")
            risks.append("DO_NOT_CHASE_SHORT")
            return DirectionalDecision.WAIT, tuple(reasons), tuple(risks)

        if is_severe_short_crowding(derivatives, config):
            reasons.append("DERIVATIVES_VETO_SEVERE_SHORT_CROWDING")
            risks.append("SHORT_CROWDING_RISK")
            return DirectionalDecision.WAIT, tuple(reasons), tuple(risks)

    elif decision == DirectionalDecision.LONG and is_severe_long_crowding(derivatives, config):
        reasons.append("DERIVATIVES_VETO_SEVERE_LONG_CROWDING")
        risks.append("LONG_CROWDING_RISK")
        return DirectionalDecision.WAIT, tuple(reasons), tuple(risks)

    return decision, (), ()
