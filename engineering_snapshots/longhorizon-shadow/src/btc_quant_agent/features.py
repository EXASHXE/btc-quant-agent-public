from __future__ import annotations

import math
from collections.abc import Sequence

from .config import StrategyConfig
from .domain import Candle, TimeframeFeatures
from .indicators import (
    adx,
    atr,
    bollinger_width,
    ema,
    rate_of_change,
    rsi,
)
from .structure import confirmed_pivots, structure_label


def minimum_history(config: StrategyConfig) -> int:
    # Five slow-EMA periods make recursive initialization error small enough for live parity.
    return max(config.ema_slow * 5, config.atr_period * 5, 100)


def _latest_percentile(values: Sequence[float], lookback: int) -> float:
    sample = values[-lookback:]
    return sum(item <= values[-1] for item in sample) / len(sample)


def _latest_zscore(values: Sequence[float], window: int) -> float:
    sample = [float(value) for value in values[-window:]]
    mean = sum(sample) / len(sample)
    variance = sum((value - mean) ** 2 for value in sample) / len(sample)
    std = math.sqrt(variance)
    return (float(values[-1]) - mean) / std if std > 0 else 0.0


def _latest_bb_width_percentile(
    closes: Sequence[float], period: int, lookback: int
) -> float:
    source = closes[-(lookback + period - 1) :]
    widths = bollinger_width(source, period)[-(min(lookback, len(closes))) :]
    return _latest_percentile(widths, len(widths))


def build_features(candles: Sequence[Candle], config: StrategyConfig) -> TimeframeFeatures:
    if len(candles) < minimum_history(config):
        raise ValueError(f"insufficient history: {len(candles)} < {minimum_history(config)}")
    if any(not bar.closed for bar in candles):
        raise ValueError("feature pipeline accepts closed candles only")
    closes = [bar.close for bar in candles]
    highs = [bar.high for bar in candles]
    lows = [bar.low for bar in candles]
    volumes = [bar.volume for bar in candles]
    cvd_available = any(bar.taker_buy_base_volume > 0 for bar in candles)
    signed_taker_volume = (
        [2.0 * bar.taker_buy_base_volume - bar.volume for bar in candles]
        if cvd_available
        else [0.0 for _ in candles]
    )
    ema_fast_values = ema(closes, config.ema_fast)
    ema_mid_values = ema(closes, config.ema_mid)
    ema_slow_values = ema(closes, config.ema_slow)
    atr_values = atr(highs, lows, closes, config.atr_period)
    adx_values = adx(highs, lows, closes, config.adx_period)
    percentile_lookback = min(120, len(candles))
    atr_percentile = _latest_percentile(atr_values, percentile_lookback)
    volume_z = _latest_zscore(volumes, 30)
    rsi_values = rsi(closes, config.rsi_period)
    roc_values = rate_of_change(closes, config.roc_period)
    bb_width_percentile = _latest_bb_width_percentile(
        closes, config.bb_period, percentile_lookback
    )
    cvd = []
    running = 0.0
    for delta in signed_taker_volume:
        running += delta
        cvd.append(running)
    pivots = confirmed_pivots(candles, config.pivot_left, config.pivot_right)
    swing_highs = [pivot.price for pivot in pivots if pivot.kind == "HIGH"]
    swing_lows = [pivot.price for pivot in pivots if pivot.kind == "LOW"]
    lookback = config.slope_lookback
    latest = candles[-1]
    return TimeframeFeatures(
        close=latest.close,
        ema_fast=ema_fast_values[-1],
        ema_mid=ema_mid_values[-1],
        ema_slow=ema_slow_values[-1],
        ema_mid_slope=(ema_mid_values[-1] - ema_mid_values[-1 - lookback]) / lookback,
        ema_slow_slope=(ema_slow_values[-1] - ema_slow_values[-1 - lookback]) / lookback,
        atr=atr_values[-1],
        atr_percentile=atr_percentile,
        adx=adx_values[-1],
        volume_z=volume_z,
        rsi=rsi_values[-1],
        roc=roc_values[-1],
        bb_width_percentile=bb_width_percentile,
        cvd_slope=(cvd[-1] - cvd[-1 - config.cvd_window]) / config.cvd_window,
        cvd_available=cvd_available,
        last_swing_high=swing_highs[-1] if swing_highs else None,
        previous_swing_high=swing_highs[-2] if len(swing_highs) > 1 else None,
        last_swing_low=swing_lows[-1] if swing_lows else None,
        previous_swing_low=swing_lows[-2] if len(swing_lows) > 1 else None,
        structure=structure_label(pivots),
        bar_open_time_ms=latest.open_time_ms,
        bar_close_time_ms=latest.close_time_ms,
    )
