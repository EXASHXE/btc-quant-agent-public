from __future__ import annotations

import hashlib
from collections.abc import Sequence

from .config import StrategyConfig
from .domain import Candidate, Candle, Direction, Regime, Setup, TimeframeFeatures
from .structure import confirmed_pivots


def _structure_id(candles: Sequence[Candle], setup: Setup, level: float) -> str:
    raw = f"{setup}:{level:.2f}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _levels(candles: Sequence[Candle], config: StrategyConfig) -> tuple[list[float], list[float]]:
    recent = candles[-config.level_lookback_bars :]
    pivots = confirmed_pivots(recent, config.pivot_left, config.pivot_right)
    lows = [pivot.price for pivot in pivots if pivot.kind == "LOW"]
    highs = [pivot.price for pivot in pivots if pivot.kind == "HIGH"]
    return lows, highs


def trend_pullback(
    candles: Sequence[Candle], features: TimeframeFeatures, regime: Regime, config: StrategyConfig
) -> Candidate | None:
    if len(candles) < 6 or regime not in (Regime.TREND_UP, Regime.TREND_DOWN):
        return None
    supports, resistances = _levels(candles, config)
    latest = candles[-1]
    prior = candles[-2]
    if latest.high - latest.low >= config.extreme_bar_atr * features.atr:
        return None
    recent = candles[-5:]
    tolerance = config.pullback_atr_tolerance * features.atr

    if regime == Regime.TREND_UP:
        structure_floor = features.last_swing_low
        if structure_floor is None:
            return None
        pullback_price = min(bar.low for bar in recent)
        touched = features.ema_mid - tolerance <= pullback_price <= features.ema_mid + tolerance
        intact = pullback_price > structure_floor
        confirmed = latest.close > features.ema_fast and latest.close > prior.high
        if not (touched and intact and confirmed and features.volume_z >= config.volume_z_min):
            return None
        target_options = [level for level in resistances if level > latest.close]
        if not target_options:
            return None
        target = min(target_options)
        score = min(95, 65 + int(min(features.adx, 40) - config.adx_trend_min) + 10)
        return Candidate(
            Direction.LONG,
            Setup.TREND_PULLBACK,
            min(latest.close, features.ema_fast),
            max(latest.close, features.ema_fast),
            structure_floor,
            target,
            score,
            _structure_id(candles, Setup.TREND_PULLBACK, structure_floor),
            ("1H 为确认上涨趋势", "15m 回踩中期均线后重新站上快线", "最新收盘突破前一根高点"),
        )

    structure_ceiling = features.last_swing_high
    if structure_ceiling is None:
        return None
    pullback_price = max(bar.high for bar in recent)
    touched = features.ema_mid - tolerance <= pullback_price <= features.ema_mid + tolerance
    intact = pullback_price < structure_ceiling
    confirmed = latest.close < features.ema_fast and latest.close < prior.low
    if not (touched and intact and confirmed and features.volume_z >= config.volume_z_min):
        return None
    target_options = [level for level in supports if level < latest.close]
    if not target_options:
        return None
    target = max(target_options)
    score = min(95, 65 + int(min(features.adx, 40) - config.adx_trend_min) + 10)
    return Candidate(
        Direction.SHORT,
        Setup.TREND_PULLBACK,
        min(latest.close, features.ema_fast),
        max(latest.close, features.ema_fast),
        structure_ceiling,
        target,
        score,
        _structure_id(candles, Setup.TREND_PULLBACK, structure_ceiling),
        ("1H 为确认下跌趋势", "15m 反抽中期均线后重新跌破快线", "最新收盘跌破前一根低点"),
    )


def breakout_retest(
    candles: Sequence[Candle], features: TimeframeFeatures, regime: Regime, config: StrategyConfig
) -> Candidate | None:
    if len(candles) < 8 or regime not in (Regime.TREND_UP, Regime.TREND_DOWN):
        return None
    recent = candles[-config.level_lookback_bars : -3]
    pivots = confirmed_pivots(recent, config.pivot_left, config.pivot_right)
    latest = candles[-1]
    breakout = candles[-2]
    if latest.high - latest.low >= config.extreme_bar_atr * features.atr:
        return None
    retest_tolerance = config.retest_atr_tolerance * features.atr
    min_breakout = config.breakout_atr_min * features.atr

    if regime == Regime.TREND_UP:
        resistance = [pivot.price for pivot in pivots if pivot.kind == "HIGH"]
        if not resistance:
            return None
        level = resistance[-1]
        valid_break = breakout.close >= level + min_breakout
        valid_retest = latest.low <= level + retest_tolerance and latest.close > level
        continuation = latest.close > latest.open and features.volume_z >= config.volume_z_min
        if not (valid_break and valid_retest and continuation):
            return None
        future_resistance = [
            pivot.price for pivot in pivots if pivot.price > latest.close and pivot.kind == "HIGH"
        ]
        projected = not future_resistance
        target = min(future_resistance) if future_resistance else latest.close + 2.5 * features.atr
        invalidation = min(latest.low, level - retest_tolerance)
        return Candidate(
            Direction.LONG,
            Setup.BREAKOUT_RETEST,
            level,
            latest.close,
            invalidation,
            target,
            78,
            _structure_id(candles, Setup.BREAKOUT_RETEST, level),
            ("15m 有效收盘突破确认压力", "回踩原压力后收盘保持其上", "回踩 K 线重新收阳"),
            ("上方无已确认压力，目标使用冻结 ATR 投影",) if projected else (),
        )

    support = [pivot.price for pivot in pivots if pivot.kind == "LOW"]
    if not support:
        return None
    level = support[-1]
    valid_break = breakout.close <= level - min_breakout
    valid_retest = latest.high >= level - retest_tolerance and latest.close < level
    continuation = latest.close < latest.open and features.volume_z >= config.volume_z_min
    if not (valid_break and valid_retest and continuation):
        return None
    future_support = [
        pivot.price for pivot in pivots if pivot.price < latest.close and pivot.kind == "LOW"
    ]
    projected = not future_support
    target = max(future_support) if future_support else latest.close - 2.5 * features.atr
    invalidation = max(latest.high, level + retest_tolerance)
    return Candidate(
        Direction.SHORT,
        Setup.BREAKOUT_RETEST,
        latest.close,
        level,
        invalidation,
        target,
        78,
        _structure_id(candles, Setup.BREAKOUT_RETEST, level),
        ("15m 有效收盘跌破确认支撑", "反抽原支撑后收盘保持其下", "反抽 K 线重新收阴"),
        ("下方无已确认支撑，目标使用冻结 ATR 投影",) if projected else (),
    )


def find_candidate(
    candles: Sequence[Candle], features: TimeframeFeatures, regime: Regime, config: StrategyConfig
) -> Candidate | None:
    return trend_pullback(candles, features, regime, config) or breakout_retest(
        candles, features, regime, config
    )
