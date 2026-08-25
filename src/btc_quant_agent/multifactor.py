from __future__ import annotations

from dataclasses import dataclass

from .config import StrategyConfig
from .domain import Candidate, DerivativesSnapshot, Direction, TimeframeFeatures


@dataclass(frozen=True)
class FactorAssessment:
    score: float
    positive_groups: int
    group_scores: dict[str, float]
    evidence: tuple[str, ...]
    risks: tuple[str, ...]
    blocked_reason: str | None = None


def macro_aligned(features: TimeframeFeatures, direction: Direction) -> bool:
    if direction == Direction.LONG:
        return (
            features.close > features.ema_mid > features.ema_slow
            and features.ema_mid_slope > 0
            and features.ema_slow_slope >= 0
        )
    return (
        features.close < features.ema_mid < features.ema_slow
        and features.ema_mid_slope < 0
        and features.ema_slow_slope <= 0
    )


def assess_factors(
    candidate: Candidate,
    features_4h: TimeframeFeatures,
    features_1h: TimeframeFeatures,
    features_15m: TimeframeFeatures,
    derivatives: DerivativesSnapshot | None,
    config: StrategyConfig,
) -> FactorAssessment:
    direction = candidate.direction
    evidence: list[str] = []
    risks: list[str] = []
    scores: dict[str, float] = {}
    maxima: dict[str, float] = {}

    if not macro_aligned(features_4h, direction):
        return FactorAssessment(0.0, 0, {}, (), (), "4H macro trend is not aligned")
    evidence.append("4H 宏观趋势与候选方向一致")

    rsi_in_range = (
        config.rsi_long_min <= features_15m.rsi <= config.rsi_long_max
        if direction == Direction.LONG
        else config.rsi_short_min <= features_15m.rsi <= config.rsi_short_max
    )
    if config.enable_momentum_group and not rsi_in_range:
        return FactorAssessment(0.0, 0, {}, tuple(evidence), (), "15m RSI is overextended")

    if (
        config.enable_volatility_liquidity_group
        and derivatives
        and derivatives.spread_bps is not None
        and derivatives.spread_bps > config.max_spread_bps
    ):
        return FactorAssessment(0.0, 0, {}, tuple(evidence), (), "order book spread too wide")
    if config.enable_derivatives_group and derivatives and derivatives.funding_rate is not None:
        adverse_funding = (
            direction == Direction.LONG and derivatives.funding_rate > config.funding_extreme_abs
        ) or (
            direction == Direction.SHORT and derivatives.funding_rate < -config.funding_extreme_abs
        )
        if adverse_funding:
            return FactorAssessment(0.0, 0, {}, tuple(evidence), (), "extreme adverse funding")

    scores["trend_structure"] = 30.0
    maxima["trend_structure"] = 30.0

    if config.enable_momentum_group:
        momentum = 8.0
        if (direction == Direction.LONG and features_15m.roc > 0) or (
            direction == Direction.SHORT and features_15m.roc < 0
        ):
            momentum += 7.0
            evidence.append("15m ROC 与候选方向一致")
        else:
            risks.append("15m ROC 尚未同向")
        scores["momentum"] = momentum
        maxima["momentum"] = 15.0

    if config.enable_participation_group:
        participation = 6.0 if features_15m.volume_z >= config.volume_z_min else 0.0
        participation_max = 6.0
        if features_15m.cvd_available:
            participation_max += 8.0
            if (direction == Direction.LONG and features_15m.cvd_slope > 0) or (
                direction == Direction.SHORT and features_15m.cvd_slope < 0
            ):
                participation += 8.0
                evidence.append("15m CVD 斜率同向")
            else:
                risks.append("15m CVD 未确认")
        if derivatives and derivatives.taker_buy_sell_ratio is not None:
            participation_max += 6.0
            taker_aligned = (
                direction == Direction.LONG and derivatives.taker_buy_sell_ratio > 1.0
            ) or (direction == Direction.SHORT and derivatives.taker_buy_sell_ratio < 1.0)
            if taker_aligned:
                participation += 6.0
                evidence.append("主动买卖比同向")
            else:
                risks.append("主动买卖比未确认")
        scores["participation_flow"] = participation
        maxima["participation_flow"] = participation_max

    derivative_score = 0.0
    derivative_max = 0.0
    if config.enable_derivatives_group and derivatives:
        if derivatives.open_interest_change_pct is not None:
            derivative_max += 8.0
            price_aligned = (direction == Direction.LONG and features_15m.roc > 0) or (
                direction == Direction.SHORT and features_15m.roc < 0
            )
            if derivatives.open_interest_change_pct > 0 and price_aligned:
                derivative_score += 8.0
                evidence.append("价格趋势伴随 OI 增长")
            elif derivatives.open_interest_change_pct < 0 and price_aligned:
                derivative_score += 2.0
                risks.append("价格同向但 OI 下降，趋势可能由平仓推动")
            else:
                risks.append("价格与 OI 组合未确认候选方向")
        if derivatives.funding_rate is not None:
            derivative_max += 6.0
            contrarian = (direction == Direction.LONG and derivatives.funding_rate < 0) or (
                direction == Direction.SHORT and derivatives.funding_rate > 0
            )
            if contrarian:
                derivative_score += 6.0
                evidence.append("Funding 与候选方向呈温和逆向，拥挤度较低")
            elif abs(derivatives.funding_rate) <= config.funding_extreme_abs * 0.25:
                derivative_score += 3.0
            else:
                risks.append("Funding 同向偏高，未提供额外确认")
        if derivatives.basis_rate is not None:
            derivative_max += 3.0
            if abs(derivatives.basis_rate) <= config.max_abs_basis_rate:
                derivative_score += 3.0
            else:
                risks.append("基差绝对值偏高，拥挤风险上升")
        if derivatives.long_short_account_ratio is not None:
            derivative_max += 3.0
            not_crowded = (
                direction == Direction.LONG and derivatives.long_short_account_ratio < 1.6
            ) or (direction == Direction.SHORT and derivatives.long_short_account_ratio > 0.625)
            if not_crowded:
                derivative_score += 3.0
            else:
                risks.append("账户多空比显示候选方向拥挤")
    if config.enable_derivatives_group and derivative_max:
        scores["derivatives"] = derivative_score
        maxima["derivatives"] = derivative_max
    elif config.enable_derivatives_group:
        risks.append("衍生品横截面不足，derivatives 分组未计分")

    if config.enable_volatility_liquidity_group and config.enable_volatility_liquidity_score:
        volatility = 0.0
        volatility_max = 9.0
        if 0.10 <= features_15m.atr_percentile < config.high_vol_atr_percentile:
            volatility += 5.0
        if features_15m.bb_width_percentile >= 0.20:
            volatility += 4.0
        if derivatives and derivatives.spread_bps is not None:
            volatility_max += 3.0
            volatility += 3.0
        if derivatives and derivatives.order_book_imbalance is not None:
            volatility_max += 3.0
            imbalance_aligned = (
                direction == Direction.LONG and derivatives.order_book_imbalance > 0
            ) or (direction == Direction.SHORT and derivatives.order_book_imbalance < 0)
            if imbalance_aligned:
                volatility += 3.0
                evidence.append("盘口前五档不平衡同向")
            else:
                risks.append("盘口不平衡未确认")
        scores["volatility_liquidity"] = volatility
        maxima["volatility_liquidity"] = volatility_max

    raw = sum(scores.values())
    available = sum(maxima.values())
    normalized = 100.0 * raw / available if available else 0.0
    positive = sum(
        1 for group, maximum in maxima.items() if maximum and scores[group] / maximum >= 0.5
    )
    group_scores = {
        group: round(100.0 * scores[group] / maximum, 2)
        for group, maximum in maxima.items()
        if maximum
    }
    required_positive = min(config.min_positive_factor_groups, len(maxima))
    if normalized < config.factor_score_min:
        blocked = f"factor score {normalized:.1f} below {config.factor_score_min:.1f}"
    elif positive < required_positive:
        blocked = f"positive factor groups {positive} below {required_positive}"
    else:
        blocked = None
    return FactorAssessment(
        round(normalized, 2),
        positive,
        group_scores,
        tuple(evidence),
        tuple(risks),
        blocked,
    )
