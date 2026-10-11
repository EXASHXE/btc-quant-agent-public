"""Causal multi-scale feature compiler for Goal A R2.

Strictly backward-looking indicators computed only on completed 1m bars.
Derived timeframes (5m, 15m, 1h) strictly respect completed bar boundaries.
No lookahead, no future-leakage.
"""
from __future__ import annotations

import numpy as np


def aggregate_bars(arr: np.ndarray, minutes: int) -> dict[str, np.ndarray]:
    """Aggregate Nx7 1m rows [time, open, high, low, close, volume, taker_buy_vol] into M-minute bars."""
    n_1m = arr.shape[0]
    n_agg = n_1m // minutes
    if n_agg == 0:
        return {}

    trimmed_len = n_agg * minutes
    t_1m = arr[:trimmed_len, 0]
    o_1m = arr[:trimmed_len, 1]
    h_1m = arr[:trimmed_len, 2]
    l_1m = arr[:trimmed_len, 3]
    c_1m = arr[:trimmed_len, 4]
    v_1m = arr[:trimmed_len, 5]
    tbv_1m = arr[:trimmed_len, 6]

    t_r = t_1m.reshape((n_agg, minutes))
    o_r = o_1m.reshape((n_agg, minutes))
    h_r = h_1m.reshape((n_agg, minutes))
    l_r = l_1m.reshape((n_agg, minutes))
    c_r = c_1m.reshape((n_agg, minutes))
    v_r = v_1m.reshape((n_agg, minutes))
    tbv_r = tbv_1m.reshape((n_agg, minutes))

    open_times = t_r[:, 0]
    opens = o_r[:, 0]
    highs = np.max(h_r, axis=1)
    lows = np.min(l_r, axis=1)
    closes = c_r[:, -1]
    volumes = np.sum(v_r, axis=1)
    tbvs = np.sum(tbv_r, axis=1)
    end_times = open_times + minutes * 60_000 - 1

    signed_flow = (2.0 * tbvs - volumes) / np.maximum(volumes, 1e-6)

    return {
        "open_time": open_times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
        "taker_buy_volume": tbvs,
        "end_ms": end_times,
        "signed_flow_ratio": signed_flow,
    }


def calc_ema(values: np.ndarray, period: int) -> np.ndarray:
    """Causal exponential moving average."""
    n = len(values)
    ema = np.empty(n, dtype=np.float64)
    if n == 0:
        return ema
    ema[0] = values[0]
    alpha = 2.0 / (period + 1.0)
    for i in range(1, n):
        ema[i] = alpha * values[i] + (1.0 - alpha) * ema[i - 1]
    return ema


def calc_sma(values: np.ndarray, period: int) -> np.ndarray:
    """Causal simple moving average with NaN handling for warmup."""
    n = len(values)
    sma = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return sma
    cumsum = np.cumsum(np.insert(values, 0, 0.0))
    window_sum = cumsum[period:] - cumsum[:-period]
    sma[period - 1 :] = window_sum / period
    return sma


def calc_rolling_std(values: np.ndarray, period: int) -> np.ndarray:
    """Causal rolling standard deviation."""
    n = len(values)
    res = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return res
    for i in range(period - 1, n):
        res[i] = float(np.std(values[i - period + 1 : i + 1], ddof=0))
    return res


def calc_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Causal Average True Range using Wilder's smoothing."""
    n = len(closes)
    atr = np.full(n, np.nan, dtype=np.float64)
    if n < period + 1:
        return atr

    tr = np.empty(n, dtype=np.float64)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)

    atr[period] = np.mean(tr[1 : period + 1])
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def calc_choppiness_index(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 24) -> np.ndarray:
    """Causal Choppiness Index = 100 * LOG10( SUM(ATR(1), period) / (MaxHigh(period) - MinLow(period)) ) / LOG10(period).
    
    A value > 55.0 signals consolidative/ranging regime; < 38.2 signals trending regime.
    """
    n = len(closes)
    chop = np.full(n, np.nan, dtype=np.float64)
    if n < period + 1:
        return chop

    tr = np.empty(n, dtype=np.float64)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))

    log_p = np.log10(period)
    for i in range(period, n):
        sum_tr = np.sum(tr[i - period + 1 : i + 1])
        max_h = np.max(highs[i - period + 1 : i + 1])
        min_l = np.min(lows[i - period + 1 : i + 1])
        hl_diff = max_h - min_l
        if hl_diff > 1e-8 and sum_tr > 1e-8:
            val = 100.0 * (np.log10(sum_tr / hl_diff) / log_p)
            chop[i] = min(max(val, 0.0), 100.0)
        else:
            chop[i] = 50.0
    return chop


def calc_bollinger_bands(closes: np.ndarray, period: int = 20, num_std: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Causal Bollinger Bands (upper, mid, lower)."""
    mid = calc_sma(closes, period)
    std = calc_rolling_std(closes, period)
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def calc_rolling_volume_zscore(volumes: np.ndarray, period: int = 96) -> np.ndarray:
    """Causal rolling volume z-score over period bars."""
    n = len(volumes)
    z = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return z
    for i in range(period - 1, n):
        window = volumes[i - period + 1 : i + 1]
        mean_v = np.mean(window)
        std_v = np.std(window, ddof=0)
        if std_v > 1e-8:
            z[i] = (volumes[i] - mean_v) / std_v
        else:
            z[i] = 0.0
    return z


def calc_rolling_extremes(highs: np.ndarray, lows: np.ndarray, period: int) -> tuple[np.ndarray, np.ndarray]:
    """Causal rolling maximum high and minimum low over past period completed bars (excluding current bar)."""
    n = len(highs)
    roll_h = np.full(n, np.nan, dtype=np.float64)
    roll_l = np.full(n, np.nan, dtype=np.float64)
    if n < period + 1:
        return roll_h, roll_l
    for i in range(period, n):
        roll_h[i] = np.max(highs[i - period : i])
        roll_l[i] = np.min(lows[i - period : i])
    return roll_h, roll_l
