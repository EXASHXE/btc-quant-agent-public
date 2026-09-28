from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

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
    MARKET_SNAPSHOT_SCHEMA_VERSION,
    RETURN_FEATURE_SEMANTICS_VERSION,
    DerivativesMetrics,
    PriceMetrics,
    TimeframeSnapshot,
)


class ReturnAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    MISSING_HORIZON_ANCHOR = "MISSING_HORIZON_ANCHOR"


@dataclass(frozen=True)
class ReturnObservation:
    horizon_ms: int
    value: float | None
    availability: str
    anchor_close_time_ms: int | None
    latest_close_time_ms: int | None
    source_interval: str = "15m"
    semantics_version: str = RETURN_FEATURE_SEMANTICS_VERSION


def compute_return_observation(
    candles: Sequence[Candle],
    *,
    horizon_ms: int,
    source_interval: str = "15m",
) -> ReturnObservation:
    """Compute explicit elapsed-time return observation with provenance from confirmed closed candles.

    Frozen semantics:
    1. Use closed candles only.
    2. Order deterministically by close_time_ms.
    3. Let latest = latest confirmed closed candle.
    4. target_close_time = latest.close_time_ms - horizon_ms.
    5. Require an exact closed candle anchor at target_close_time.
    6. If the exact horizon anchor is absent:
          return ReturnObservation(value=None, availability=INSUFFICIENT_HISTORY or MISSING_HORIZON_ANCHOR)
    7. NEVER select the nearest earlier/later candle.
    8. NEVER interpolate.
    9. NEVER use a forming candle.
    10. Return latest.close / anchor.close - 1
    """
    if horizon_ms <= 0:
        raise ValueError(f"horizon_ms must be positive: {horizon_ms}")

    # 1. Closed candles only; filter out any forming candle (closed is False)
    closed = [c for c in candles if getattr(c, "closed", True)]
    if not closed:
        return ReturnObservation(
            horizon_ms=horizon_ms,
            value=None,
            availability=ReturnAvailability.INSUFFICIENT_HISTORY.value,
            anchor_close_time_ms=None,
            latest_close_time_ms=None,
            source_interval=source_interval,
            semantics_version=RETURN_FEATURE_SEMANTICS_VERSION,
        )

    # 2. Order deterministically by close_time_ms; deduplicate identical timestamps
    by_close_time: dict[int, Candle] = {}
    for c in closed:
        t = c.close_time_ms
        if t in by_close_time:
            if by_close_time[t].close != c.close:
                return ReturnObservation(
                    horizon_ms=horizon_ms,
                    value=None,
                    availability=ReturnAvailability.MISSING_HORIZON_ANCHOR.value,
                    anchor_close_time_ms=None,
                    latest_close_time_ms=None,
                    source_interval=source_interval,
                    semantics_version=RETURN_FEATURE_SEMANTICS_VERSION,
                )
        else:
            by_close_time[t] = c

    sorted_candles = sorted(by_close_time.values(), key=lambda c: c.close_time_ms)
    latest = sorted_candles[-1]
    target_close_time = latest.close_time_ms - horizon_ms

    earliest = sorted_candles[0]
    if earliest.close_time_ms > target_close_time:
        return ReturnObservation(
            horizon_ms=horizon_ms,
            value=None,
            availability=ReturnAvailability.INSUFFICIENT_HISTORY.value,
            anchor_close_time_ms=target_close_time,
            latest_close_time_ms=latest.close_time_ms,
            source_interval=source_interval,
            semantics_version=RETURN_FEATURE_SEMANTICS_VERSION,
        )

    anchor = by_close_time.get(target_close_time)
    if anchor is None or anchor.close <= 0:
        return ReturnObservation(
            horizon_ms=horizon_ms,
            value=None,
            availability=ReturnAvailability.MISSING_HORIZON_ANCHOR.value,
            anchor_close_time_ms=target_close_time,
            latest_close_time_ms=latest.close_time_ms,
            source_interval=source_interval,
            semantics_version=RETURN_FEATURE_SEMANTICS_VERSION,
        )

    return ReturnObservation(
        horizon_ms=horizon_ms,
        value=(latest.close / anchor.close) - 1.0,
        availability=ReturnAvailability.AVAILABLE.value,
        anchor_close_time_ms=anchor.close_time_ms,
        latest_close_time_ms=latest.close_time_ms,
        source_interval=source_interval,
        semantics_version=RETURN_FEATURE_SEMANTICS_VERSION,
    )


def closed_bar_return_with_status(
    candles: Sequence[Candle],
    *,
    horizon_ms: int,
) -> tuple[float | None, ReturnAvailability]:
    """Compute explicit elapsed-time return from confirmed closed candles with status."""
    obs = compute_return_observation(candles, horizon_ms=horizon_ms)
    return obs.value, ReturnAvailability(obs.availability)


def closed_bar_return(
    candles: Sequence[Candle],
    *,
    horizon_ms: int,
) -> float | None:
    """Compute explicit elapsed-time return from confirmed closed candles."""
    ret_val, _status = closed_bar_return_with_status(candles, horizon_ms=horizon_ms)
    return ret_val


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

    # Prior compression window detection (require actual prior compression in preceding bars)
    prior_window = bb_pct_vals[-min(20, len(bb_pct_vals)):-1] if len(bb_pct_vals) > 1 else []
    compressed_bars = sum(1 for v in prior_window if v <= tc.vol_compression_bb_pct)
    has_prior_compression = compressed_bars >= tc.vol_compression_min_bars

    is_compressed = (current_bb_pct <= tc.vol_compression_bb_pct) or has_prior_compression
    is_expanded = current_atr_pct >= 0.75 and current_volume_z >= 0.5

    # Observational EMA slow (e.g. EMA200) strictly from confirmed closed candles
    # Requires deterministic engineering warmup margin of ema_slow + 50 closed bars
    if len(closed_candles) >= tc.ema_slow + 50:
        ema_slow_vals = ema(closes, tc.ema_slow)
        current_ema_slow = ema_slow_vals[-1]
        current_ema_slow_status = "AVAILABLE"
    else:
        current_ema_slow = None
        current_ema_slow_status = "EMA_SLOW_INSUFFICIENT_HISTORY"

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
        roc_12bars=current_roc,
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
        has_prior_compression_window=has_prior_compression,
        roc=current_roc,
        ema_slow=current_ema_slow,
        ema_slow_status=current_ema_slow_status,
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
        "snapshot_schema_version": MARKET_SNAPSHOT_SCHEMA_VERSION,
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
        "funding_time_ms": derivatives.funding_time_ms,
        "oi": derivatives.current_open_interest,
        "oi_time_ms": derivatives.open_interest_time_ms,
    }
    raw = json.dumps(payload, default=str, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
