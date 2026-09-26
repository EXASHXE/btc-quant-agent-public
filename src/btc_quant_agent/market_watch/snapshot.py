from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from ..domain import Candle, Regime
from ..indicators import (
    adx,
    atr,
    bollinger_width,
    ema,
    percentile_rank,
    rate_of_change,
    rolling_zscore,
    rsi,
)
from ..structure import confirmed_pivots, structure_label
from .config import MarketWatchConfig
from .domain import (
    DerivativesMetrics,
    PriceMetrics,
    TimeframeSnapshot,
)


def compute_timeframe_snapshot(
    interval: str,
    closed_candles: Sequence[Candle],
    forming_candle: Candle | None,
    config: MarketWatchConfig,
) -> TimeframeSnapshot:
    """Compute deterministic indicators and structure strictly on closed candles.

    The forming candle (if present) is kept strictly for display/monitoring and
    is NEVER used for confirmed indicators or structure.
    """
    if len(closed_candles) < 30:
        raise ValueError(f"insufficient history for {interval}: {len(closed_candles)} < 30")

    latest_closed = closed_candles[-1]
    latest_bar = forming_candle if forming_candle is not None else latest_closed

    closes = [bar.close for bar in closed_candles]
    highs = [bar.high for bar in closed_candles]
    lows = [bar.low for bar in closed_candles]
    volumes = [bar.volume for bar in closed_candles]

    tc = config.thresholds
    ema_fast_vals = ema(closes, tc.ema_fast)
    ema_mid_vals = ema(closes, tc.ema_mid)

    slope_lookback = min(tc.slope_lookback, len(closed_candles) - 1)
    fast_slope = (ema_fast_vals[-1] - ema_fast_vals[-1 - slope_lookback]) / slope_lookback
    mid_slope = (ema_mid_vals[-1] - ema_mid_vals[-1 - slope_lookback]) / slope_lookback

    atr_vals = atr(highs, lows, closes, tc.atr_period)
    current_atr = atr_vals[-1]
    lookback = min(120, len(atr_vals))
    atr_percentiles = percentile_rank(atr_vals, lookback)
    current_atr_pct = atr_percentiles[-1]

    adx_vals = adx(highs, lows, closes, tc.adx_period)
    current_adx = adx_vals[-1]

    rsi_vals = rsi(closes, 14)
    current_rsi = rsi_vals[-1]

    roc_vals = rate_of_change(closes, 12)
    current_roc = roc_vals[-1]

    z_vals = rolling_zscore(volumes, min(30, len(volumes)))
    current_volume_z = z_vals[-1]

    bb_period = min(20, len(closes))
    bb_widths = bollinger_width(closes, bb_period)
    current_bb_width = bb_widths[-1]
    bb_pct_vals = percentile_rank(bb_widths, min(120, len(bb_widths)))
    current_bb_pct = bb_pct_vals[-1]

    # Structure & pivots on closed bars
    level_lookback = min(160, len(closed_candles))
    recent_closed = closed_candles[-level_lookback:]
    pivots = confirmed_pivots(recent_closed, tc.pivot_left, tc.pivot_right)
    swing_highs = [p.price for p in pivots if p.kind == "HIGH"]
    swing_lows = [p.price for p in pivots if p.kind == "LOW"]
    struct_label = structure_label(pivots)

    # Extended regime classification
    regime = _classify_timeframe_regime(
        close=latest_closed.close,
        ema_fast=ema_fast_vals[-1],
        ema_mid=ema_mid_vals[-1],
        fast_slope=fast_slope,
        mid_slope=mid_slope,
        adx_val=current_adx,
        atr_pct=current_atr_pct,
        structure=struct_label,
        config=config,
    )

    is_compressed = current_bb_pct <= tc.vol_compression_bb_pct
    is_expanded = current_atr_pct >= 0.75 and current_volume_z >= 0.5

    return TimeframeSnapshot(
        interval=interval,
        latest_bar=latest_bar,
        latest_closed_bar=latest_closed,
        closed_bar_end_time_ms=latest_closed.close_time_ms,
        close=latest_closed.close,
        ema_fast=ema_fast_vals[-1],
        ema_mid=ema_mid_vals[-1],
        ema_fast_slope=fast_slope,
        ema_mid_slope=mid_slope,
        atr=current_atr,
        atr_percentile=current_atr_pct,
        adx=current_adx,
        rsi=current_rsi,
        roc=current_roc,
        volume=latest_closed.volume,
        volume_z=current_volume_z,
        bb_width=current_bb_width,
        bb_width_percentile=current_bb_pct,
        recent_swing_high=swing_highs[-1] if swing_highs else None,
        recent_swing_low=swing_lows[-1] if swing_lows else None,
        supports=tuple(swing_lows[-5:]),
        resistances=tuple(swing_highs[-5:]),
        structure=struct_label,
        regime=regime,
        is_volatility_compressed=is_compressed,
        is_volatility_expanded=is_expanded,
    )


def _classify_timeframe_regime(
    *,
    close: float,
    ema_fast: float,
    ema_mid: float,
    fast_slope: float,
    mid_slope: float,
    adx_val: float,
    atr_pct: float,
    structure: str,
    config: MarketWatchConfig,
) -> Regime:
    tc = config.thresholds
    if atr_pct >= tc.high_vol_atr_percentile:
        return Regime.HIGH_VOLATILITY

    up = (
        close > ema_fast > ema_mid
        and fast_slope > 0
        and mid_slope >= 0
        and adx_val >= tc.adx_trend_min
        and structure == "HH_HL"
    )
    down = (
        close < ema_fast < ema_mid
        and fast_slope < 0
        and mid_slope <= 0
        and adx_val >= tc.adx_trend_min
        and structure == "LH_LL"
    )

    if up:
        return Regime.TREND_UP
    if down:
        return Regime.TREND_DOWN
    if adx_val < tc.adx_trend_min * 0.8:
        return Regime.RANGE
    return Regime.TRANSITION


def compute_snapshot_hash(
    symbol: str,
    decision_time_ms: int,
    price: PriceMetrics,
    tf_15m: TimeframeSnapshot,
    tf_1h: TimeframeSnapshot,
    tf_4h: TimeframeSnapshot,
    derivatives: DerivativesMetrics,
) -> str:
    """Generate a deterministic hash of the snapshot inputs for reproducibility."""
    payload = {
        "symbol": symbol,
        "decision_time_ms": decision_time_ms,
        "last_price": price.last_price,
        "15m_close": tf_15m.close,
        "15m_end": tf_15m.closed_bar_end_time_ms,
        "1h_close": tf_1h.close,
        "1h_end": tf_1h.closed_bar_end_time_ms,
        "4h_close": tf_4h.close,
        "4h_end": tf_4h.closed_bar_end_time_ms,
        "funding": derivatives.funding_rate,
        "oi": derivatives.current_open_interest,
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
