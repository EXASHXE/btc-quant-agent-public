from __future__ import annotations

from .config import StrategyConfig
from .domain import Regime, TimeframeFeatures


def classify_regime(features: TimeframeFeatures, config: StrategyConfig) -> Regime:
    if features.atr_percentile >= config.high_vol_atr_percentile:
        return Regime.HIGH_VOLATILITY
    up = (
        features.close > features.ema_mid > features.ema_slow
        and features.ema_mid_slope > 0
        and features.ema_slow_slope >= 0
        and features.adx >= config.adx_trend_min
        and features.structure == "HH_HL"
    )
    down = (
        features.close < features.ema_mid < features.ema_slow
        and features.ema_mid_slope < 0
        and features.ema_slow_slope <= 0
        and features.adx >= config.adx_trend_min
        and features.structure == "LH_LL"
    )
    if up:
        return Regime.TREND_UP
    if down:
        return Regime.TREND_DOWN
    if features.adx < config.adx_trend_min * 0.75:
        return Regime.RANGE
    return Regime.TRANSITION
