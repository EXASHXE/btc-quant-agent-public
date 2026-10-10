"""Signal calculation and multi-scale feature extractors for Waves 1, 2, and 3 Trend & Flow candidates."""
from __future__ import annotations

import math
import numpy as np


def aggregate_bars(arr: np.ndarray, minutes: int) -> dict[str, np.ndarray]:
    """Aggregate 1m rows into M-minute bars."""
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

    t_reshaped = t_1m.reshape((n_agg, minutes))
    o_reshaped = o_1m.reshape((n_agg, minutes))
    h_reshaped = h_1m.reshape((n_agg, minutes))
    l_reshaped = l_1m.reshape((n_agg, minutes))
    c_reshaped = c_1m.reshape((n_agg, minutes))
    v_reshaped = v_1m.reshape((n_agg, minutes))
    tbv_reshaped = tbv_1m.reshape((n_agg, minutes))

    open_times = t_reshaped[:, 0]
    opens = o_reshaped[:, 0]
    highs = np.max(h_reshaped, axis=1)
    lows = np.min(l_reshaped, axis=1)
    closes = c_reshaped[:, -1]
    volumes = np.sum(v_reshaped, axis=1)
    tbvs = np.sum(tbv_reshaped, axis=1)
    end_times = open_times + minutes * 60000 - 1

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


def _ema_fast(values: np.ndarray, period: int) -> np.ndarray:
    """Fast exponential moving average."""
    n = len(values)
    ema = np.empty(n, dtype=np.float64)
    if n == 0:
        return ema
    ema[0] = values[0]
    alpha = 2.0 / (period + 1.0)
    for i in range(1, n):
        ema[i] = alpha * values[i] + (1.0 - alpha) * ema[i - 1]
    return ema


def _sma_fast(values: np.ndarray, period: int) -> np.ndarray:
    """Fast simple moving average with NaN handling."""
    n = len(values)
    sma = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return sma
    valid_mask = ~np.isnan(values)
    clean = np.where(valid_mask, values, 0.0)
    cumsum = np.cumsum(np.insert(clean, 0, 0))
    count = np.cumsum(np.insert(valid_mask.astype(int), 0, 0))
    window_sum = cumsum[period:] - cumsum[:-period]
    window_cnt = count[period:] - count[:-period]
    valid_window = window_cnt == period
    sma[period - 1 :][valid_window] = window_sum[valid_window] / period
    return sma


def _std_fast(values: np.ndarray, period: int) -> np.ndarray:
    """Fast rolling standard deviation."""
    n = len(values)
    std = np.full(n, np.nan, dtype=np.float64)
    if n < period:
        return std
    for i in range(period - 1, n):
        std[i] = np.std(values[i - period + 1 : i + 1])
    return std


def _er_fast(closes: np.ndarray, window: int = 10) -> np.ndarray:
    """Kaufman's Efficiency Ratio."""
    n = len(closes)
    er = np.full(n, np.nan, dtype=np.float64)
    if n < window + 1:
        return er
    for i in range(window, n):
        change = abs(closes[i] - closes[i - window])
        volatility = np.sum(np.abs(np.diff(closes[i - window : i + 1])))
        er[i] = change / max(volatility, 1e-6)
    return er


def _atr_fast(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int) -> np.ndarray:
    """True Range Wilder EMA."""
    n = len(highs)
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
    alpha = 1.0 / period
    for i in range(period + 1, n):
        atr[i] = alpha * tr[i] + (1.0 - alpha) * atr[i - 1]
    return atr


def _adx_full(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Directional Movement Index, returning (adx, di_plus, di_minus)."""
    n = len(highs)
    adx = np.full(n, np.nan, dtype=np.float64)
    di_p = np.full(n, np.nan, dtype=np.float64)
    di_m = np.full(n, np.nan, dtype=np.float64)
    if n < 2 * period + 1:
        return adx, di_p, di_m

    plus_dm = np.zeros(n, dtype=np.float64)
    minus_dm = np.zeros(n, dtype=np.float64)
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = highs[0] - lows[0]

    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)

    smooth_tr = np.zeros(n, dtype=np.float64)
    smooth_plus = np.zeros(n, dtype=np.float64)
    smooth_minus = np.zeros(n, dtype=np.float64)

    smooth_tr[period] = np.sum(tr[1 : period + 1])
    smooth_plus[period] = np.sum(plus_dm[1 : period + 1])
    smooth_minus[period] = np.sum(minus_dm[1 : period + 1])

    dx = np.zeros(n, dtype=np.float64)
    for i in range(period + 1, n):
        smooth_tr[i] = smooth_tr[i - 1] - (smooth_tr[i - 1] / period) + tr[i]
        smooth_plus[i] = smooth_plus[i - 1] - (smooth_plus[i - 1] / period) + plus_dm[i]
        smooth_minus[i] = smooth_minus[i - 1] - (smooth_minus[i - 1] / period) + minus_dm[i]

        p = 100.0 * (smooth_plus[i] / max(smooth_tr[i], 1e-6))
        m = 100.0 * (smooth_minus[i] / max(smooth_tr[i], 1e-6))
        di_p[i] = p
        di_m[i] = m
        denom = p + m
        dx[i] = 100.0 * (abs(p - m) / max(denom, 1e-6))

    adx[2 * period] = np.mean(dx[period + 1 : 2 * period + 1])
    for i in range(2 * period + 1, n):
        adx[i] = ((adx[i - 1] * (period - 1)) + dx[i]) / period

    return adx, di_p, di_m


def generate_wave_signals(arr_1m: np.ndarray, cand_id: str, embargo_start_ms: int, embargo_end_ms: int) -> list[dict]:
    """Generate trade signals for a given candidate using strictly closed bars."""
    agg15 = aggregate_bars(arr_1m, 15)
    agg60 = aggregate_bars(arr_1m, 60)
    agg240 = aggregate_bars(arr_1m, 240)

    if not agg15 or not agg60 or not agg240:
        return []

    # Indicators on 15m
    atr15 = _atr_fast(agg15["high"], agg15["low"], agg15["close"], 14)
    vol_sma15 = _sma_fast(agg15["volume"], 20)

    # Indicators on 1h (60m)
    ema10_1h = _ema_fast(agg60["close"], 10)
    ema20_1h = _ema_fast(agg60["close"], 20)
    ema30_1h = _ema_fast(agg60["close"], 30)
    atr14_1h = _atr_fast(agg60["high"], agg60["low"], agg60["close"], 14)
    atr56_1h = _atr_fast(agg60["high"], agg60["low"], agg60["close"], 56)
    vol_sma1h = _sma_fast(agg60["volume"], 20)
    atr14_sma10_1h = _sma_fast(atr14_1h, 10)
    er_1h = _er_fast(agg60["close"], 10)

    # Bollinger Bands on 1h
    sma20_1h = _sma_fast(agg60["close"], 20)
    std20_1h = _std_fast(agg60["close"], 20)
    bb_upper_1h = sma20_1h + 2.0 * std20_1h
    bb_lower_1h = sma20_1h - 2.0 * std20_1h
    bb_width_1h = (bb_upper_1h - bb_lower_1h) / np.maximum(sma20_1h, 1e-6)

    # Rolling 24h VWAP on 1h bars
    cum_pv = np.cumsum(np.insert(agg60["close"] * agg60["volume"], 0, 0))
    cum_v = np.cumsum(np.insert(agg60["volume"], 0, 0))
    vwap_24h = np.full(len(agg60["close"]), np.nan, dtype=np.float64)
    if len(agg60["close"]) >= 24:
        v_diff = cum_v[24:] - cum_v[:-24]
        pv_diff = cum_pv[24:] - cum_pv[:-24]
        vwap_24h[23:] = pv_diff / np.maximum(v_diff, 1e-6)

    # Cumulative Volume Delta (CVD) on 1h bars
    cvd_raw = np.cumsum(2.0 * agg60["taker_buy_volume"] - agg60["volume"])

    # Indicators on 4h (240m)
    ema20_4h = _ema_fast(agg240["close"], 20)
    ema50_4h = _ema_fast(agg240["close"], 50)
    adx_4h, di_plus_4h, di_minus_4h = _adx_full(agg240["high"], agg240["low"], agg240["close"], 14)

    idx_1h_for_15m = np.searchsorted(agg60["end_ms"], agg15["end_ms"])
    idx_4h_for_15m = np.searchsorted(agg240["end_ms"], agg15["end_ms"])

    signals = []
    min_15m_idx = 1000

    for i in range(min_15m_idx, len(agg15["end_ms"])):
        t_event = int(agg15["end_ms"][i])
        if t_event < embargo_start_ms or t_event > embargo_end_ms:
            continue

        h1_idx = idx_1h_for_15m[i]
        if h1_idx < 60 or h1_idx >= len(agg60["end_ms"]):
            continue

        h4_idx = idx_4h_for_15m[i]
        if h4_idx < 30 or h4_idx >= len(agg240["end_ms"]):
            continue

        if agg60["end_ms"][h1_idx] > t_event:
            h1_idx -= 1
        if agg240["end_ms"][h4_idx] > t_event:
            h4_idx -= 1

        atr_1h = atr14_1h[h1_idx]
        if np.isnan(atr_1h) or atr_1h <= 0:
            continue

        close_15m = agg15["close"][i]
        open_15m = agg15["open"][i]
        high_15m = agg15["high"][i]
        low_15m = agg15["low"][i]
        flow_15m = agg15["signed_flow_ratio"][i]
        vol_15m = agg15["volume"][i]

        side = 0
        stop_mult = 1.5
        target_r = 2.0
        horizon_hours = 8

        # --- WAVE 1 CANDIDATES ---
        if cand_id == "W1_C01_MULTISCALE_TREND_ADOPTION_08H":
            horizon_hours = 8
            stop_mult = 1.5
            target_r = 2.0
            slope_4h = ema20_4h[h4_idx] - ema20_4h[h4_idx - 3]
            is_4h_bull = (agg240["close"][h4_idx] > ema20_4h[h4_idx] > ema50_4h[h4_idx]) and (slope_4h > 0)
            is_4h_bear = (agg240["close"][h4_idx] < ema20_4h[h4_idx] < ema50_4h[h4_idx]) and (slope_4h < 0)
            is_1h_bull = agg60["close"][h1_idx] > ema20_1h[h1_idx]
            is_1h_bear = agg60["close"][h1_idx] < ema20_1h[h1_idx]
            atr_15m = atr15[i]
            if not np.isnan(atr_15m) and atr_15m > 0:
                is_non_chase = abs(close_15m - open_15m) < 1.5 * atr_15m
                flow_prev = agg15["signed_flow_ratio"][i - 1]
                if is_4h_bull and is_1h_bull and is_non_chase and (flow_15m > 0.15) and (flow_prev > 0.15):
                    side = 1
                elif is_4h_bear and is_1h_bear and is_non_chase and (flow_15m < -0.15) and (flow_prev < -0.15):
                    side = -1

        elif cand_id == "W1_C02_PERSISTENT_TAKER_PRESSURE_08H":
            horizon_hours = 8
            stop_mult = 1.5
            target_r = 2.0
            is_4h_bull = ema20_4h[h4_idx] > ema50_4h[h4_idx]
            is_4h_bear = ema20_4h[h4_idx] < ema50_4h[h4_idx]
            flow_0 = flow_15m
            flow_1 = agg15["signed_flow_ratio"][i - 1]
            flow_2 = agg15["signed_flow_ratio"][i - 2]
            v_sma = vol_sma15[i]
            vol_ok = (not np.isnan(v_sma)) and (vol_15m > 1.2 * v_sma)
            if is_4h_bull and vol_ok and (flow_0 > 0.10) and (flow_1 > 0.10) and (flow_2 > 0.10):
                side = 1
            elif is_4h_bear and vol_ok and (flow_0 < -0.10) and (flow_1 < -0.10) and (flow_2 < -0.10):
                side = -1

        elif cand_id == "W1_C03_BREAKOUT_RETEST_WITH_FLOW_04H":
            horizon_hours = 4
            stop_mult = 1.2
            target_r = 2.0
            if h4_idx >= 23:
                h4_high_20 = np.max(agg240["high"][h4_idx - 22 : h4_idx - 2])
                h4_low_20 = np.min(agg240["low"][h4_idx - 22 : h4_idx - 2])
                recent_break_high = any(agg240["high"][h4_idx - 2 : h4_idx + 1] > h4_high_20)
                recent_break_low = any(agg240["low"][h4_idx - 2 : h4_idx + 1] < h4_low_20)
                if recent_break_high and (low_15m <= h4_high_20 + 0.5 * atr_1h) and (close_15m > h4_high_20) and (flow_15m > 0.10):
                    side = 1
                elif recent_break_low and (high_15m >= h4_low_20 - 0.5 * atr_1h) and (close_15m < h4_low_20) and (flow_15m < -0.10):
                    side = -1

        elif cand_id == "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H":
            horizon_hours = 12
            stop_mult = 2.0
            target_r = 2.0
            if h1_idx >= 60:
                atr_ratio_min = np.nanmin(atr14_1h[h1_idx - 12 : h1_idx] / np.maximum(atr56_1h[h1_idx - 12 : h1_idx], 1e-6))
                sma10_val = atr14_sma10_1h[h1_idx]
                expansion_now = (not np.isnan(sma10_val)) and (atr14_1h[h1_idx] > 1.25 * sma10_val)
                h1_high_20 = np.max(agg60["high"][h1_idx - 20 : h1_idx])
                h1_low_20 = np.min(agg60["low"][h1_idx - 20 : h1_idx])
                close_1h = agg60["close"][h1_idx]
                if (atr_ratio_min < 0.85) and expansion_now:
                    if (close_1h > h1_high_20) and (close_1h - h1_high_20 < 1.0 * atr_1h) and (flow_15m > 0.05):
                        side = 1
                    elif (close_1h < h1_low_20) and (h1_low_20 - close_1h < 1.0 * atr_1h) and (flow_15m < -0.05):
                        side = -1

        elif cand_id == "W1_C05_CROSS_SESSION_CONTINUATION_08H":
            horizon_hours = 8
            stop_mult = 1.5
            target_r = 2.0
            t_next = t_event + 1
            utc_hour = (t_next // 3600_000) % 24
            utc_minute = (t_next // 60_000) % 60
            if utc_minute == 0 and (utc_hour in (8, 13)):
                c0 = agg60["close"][h1_idx]
                o0 = agg60["open"][h1_idx]
                c1 = agg60["close"][h1_idx - 1]
                o1 = agg60["open"][h1_idx - 1]
                v0 = agg60["volume"][h1_idx]
                v_sma_h = vol_sma1h[h1_idx]
                if (not np.isnan(v_sma_h)) and (v0 > 1.2 * v_sma_h):
                    if (c0 > o0) and (c1 > o1) and (flow_15m > 0.10):
                        side = 1
                    elif (c0 < o0) and (c1 < o1) and (flow_15m < -0.10):
                        side = -1

        elif cand_id == "W1_C06_PERSISTENT_TREND_24H":
            horizon_hours = 24
            stop_mult = 2.5
            target_r = 2.5
            adx_val = adx_4h[h4_idx]
            is_4h_strong_bull = (ema20_4h[h4_idx] > ema50_4h[h4_idx]) and (not np.isnan(adx_val) and adx_val > 25)
            is_4h_strong_bear = (ema20_4h[h4_idx] < ema50_4h[h4_idx]) and (not np.isnan(adx_val) and adx_val > 25)
            flow_4h_cum = np.sum(agg60["signed_flow_ratio"][h4_idx - 3 : h4_idx + 1])
            ema20_val_1h = ema20_1h[h1_idx]
            pullback_bull = (low_15m <= ema20_val_1h <= high_15m) and (close_15m > ema20_val_1h)
            pullback_bear = (low_15m <= ema20_val_1h <= high_15m) and (close_15m < ema20_val_1h)
            if is_4h_strong_bull and (flow_4h_cum > 0) and pullback_bull:
                side = 1
            elif is_4h_strong_bear and (flow_4h_cum < 0) and pullback_bear:
                side = -1

        # --- WAVE 2 CANDIDATES ---
        elif cand_id == "W2_C01_VOLUME_WEIGHTED_MOMENTUM_SURGE_08H":
            horizon_hours = 8
            stop_mult = 1.5
            target_r = 2.0
            vwap = vwap_24h[h1_idx]
            v_sma_h = vol_sma1h[h1_idx]
            vol_1h = agg60["volume"][h1_idx]
            c_1h = agg60["close"][h1_idx]
            if not np.isnan(vwap) and not np.isnan(v_sma_h):
                vol_ok = vol_1h > 1.5 * v_sma_h
                if vol_ok and (c_1h > vwap + 0.5 * atr_1h) and (flow_15m > 0.15):
                    side = 1
                elif vol_ok and (c_1h < vwap - 0.5 * atr_1h) and (flow_15m < -0.15):
                    side = -1

        elif cand_id == "W2_C02_MULTI_TIMEFRAME_CHOP_EXIT_TREND_12H":
            horizon_hours = 12
            stop_mult = 2.0
            target_r = 2.0
            if h4_idx >= 3 and h1_idx >= 12:
                adx_min = np.nanmin(adx_4h[h4_idx - 3 : h4_idx])
                adx_now = adx_4h[h4_idx]
                dp = di_plus_4h[h4_idx]
                dm = di_minus_4h[h4_idx]
                h1_high_12 = np.max(agg60["high"][h1_idx - 12 : h1_idx])
                h1_low_12 = np.min(agg60["low"][h1_idx - 12 : h1_idx])
                c_1h = agg60["close"][h1_idx]
                if (adx_min < 18) and (adx_now > 20):
                    if (dp > dm) and (c_1h > h1_high_12):
                        side = 1
                    elif (dm > dp) and (c_1h < h1_low_12):
                        side = -1

        elif cand_id == "W2_C03_AGGRESSIVE_FLOW_CUMULATIVE_DELTA_DIVERGENCE_08H":
            horizon_hours = 8
            stop_mult = 1.5
            target_r = 2.0
            if h1_idx >= 24:
                cvd_12h_now = cvd_raw[h1_idx] - cvd_raw[h1_idx - 12]
                cvd_12h_hist = [cvd_raw[j] - cvd_raw[j - 12] for j in range(h1_idx - 12, h1_idx)]
                max_cvd_hist = max(cvd_12h_hist)
                min_cvd_hist = min(cvd_12h_hist)
                h1_high_12 = np.max(agg60["high"][h1_idx - 12 : h1_idx])
                h1_low_12 = np.min(agg60["low"][h1_idx - 12 : h1_idx])
                c_1h = agg60["close"][h1_idx]
                if (c_1h > h1_high_12) and (cvd_12h_now > max_cvd_hist) and (flow_15m > 0.10):
                    side = 1
                elif (c_1h < h1_low_12) and (cvd_12h_now < min_cvd_hist) and (flow_15m < -0.10):
                    side = -1

        elif cand_id == "W2_C04_DONCHIAN_MIDLINE_PULLBACK_CONTINUATION_08H":
            horizon_hours = 8
            stop_mult = 1.5
            target_r = 2.0
            if h1_idx >= 20:
                h1_high_20 = np.max(agg60["high"][h1_idx - 20 : h1_idx])
                h1_low_20 = np.min(agg60["low"][h1_idx - 20 : h1_idx])
                midline = 0.5 * (h1_high_20 + h1_low_20)
                is_4h_bull = (agg240["close"][h4_idx] > ema20_4h[h4_idx] > ema50_4h[h4_idx])
                is_4h_bear = (agg240["close"][h4_idx] < ema20_4h[h4_idx] < ema50_4h[h4_idx])
                touch_bull = (low_15m <= midline <= high_15m) and (close_15m > midline)
                touch_bear = (low_15m <= midline <= high_15m) and (close_15m < midline)
                if is_4h_bull and touch_bull and (flow_15m > 0.10):
                    side = 1
                elif is_4h_bear and touch_bear and (flow_15m < -0.10):
                    side = -1

        elif cand_id == "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H":
            horizon_hours = 12
            stop_mult = 1.8
            target_r = 2.5
            if h1_idx >= 60:
                atr_ratio_min = np.nanmin(atr14_1h[h1_idx - 12 : h1_idx] / np.maximum(atr56_1h[h1_idx - 12 : h1_idx], 1e-6))
                sma10_val = atr14_sma10_1h[h1_idx]
                expansion_now = (not np.isnan(sma10_val)) and (atr14_1h[h1_idx] > 1.20 * sma10_val)
                v_sma_h = vol_sma1h[h1_idx]
                vol_1h = agg60["volume"][h1_idx]
                vol_ok = (not np.isnan(v_sma_h)) and (vol_1h > 1.5 * v_sma_h)
                h1_high_20 = np.max(agg60["high"][h1_idx - 20 : h1_idx])
                h1_low_20 = np.min(agg60["low"][h1_idx - 20 : h1_idx])
                close_1h = agg60["close"][h1_idx]
                if (atr_ratio_min < 0.85) and expansion_now and vol_ok:
                    if (close_1h > h1_high_20) and (flow_15m > 0.10):
                        side = 1
                    elif (close_1h < h1_low_20) and (flow_15m < -0.10):
                        side = -1

        elif cand_id == "W2_C06_EXTREME_FLOW_EXHAUSTION_REVERSAL_TO_TREND_04H":
            horizon_hours = 4
            stop_mult = 1.2
            target_r = 2.0
            is_4h_bull = ema20_4h[h4_idx] > ema50_4h[h4_idx]
            is_4h_bear = ema20_4h[h4_idx] < ema50_4h[h4_idx]
            flow_prev = agg15["signed_flow_ratio"][i - 1]
            c_prev = agg15["close"][i - 1]
            o_prev = agg15["open"][i - 1]
            h_prev = agg15["high"][i - 1]
            l_prev = agg15["low"][i - 1]
            lower_wick_prev = min(c_prev, o_prev) - l_prev
            upper_wick_prev = h_prev - max(c_prev, o_prev)
            hammer_flush = (flow_prev < -0.30) and (lower_wick_prev > 2.0 * max(upper_wick_prev, 1e-4))
            climax_flush = (flow_prev > 0.30) and (upper_wick_prev > 2.0 * max(lower_wick_prev, 1e-4))
            if is_4h_bull and hammer_flush and (close_15m > c_prev) and (flow_15m > 0.10):
                side = 1
            elif is_4h_bear and climax_flush and (close_15m < c_prev) and (flow_15m < -0.10):
                side = -1

        # --- WAVE 3 CANDIDATES ---
        elif cand_id == "W3_C01_EMA_CROSS_MULTI_HORIZON_TREND_FILTER_08H":
            horizon_hours = 8
            stop_mult = 1.5
            target_r = 2.0
            is_4h_bull = ema20_4h[h4_idx] > ema50_4h[h4_idx]
            is_4h_bear = ema20_4h[h4_idx] < ema50_4h[h4_idx]
            # Fresh cross within last 2 1h bars
            cross_up = any(ema10_1h[j] > ema30_1h[j] and ema10_1h[j - 1] <= ema30_1h[j - 1] for j in range(h1_idx - 1, h1_idx + 1))
            cross_down = any(ema10_1h[j] < ema30_1h[j] and ema10_1h[j - 1] >= ema30_1h[j - 1] for j in range(h1_idx - 1, h1_idx + 1))
            if is_4h_bull and cross_up and (flow_15m > 0.20):
                side = 1
            elif is_4h_bear and cross_down and (flow_15m < -0.20):
                side = -1

        elif cand_id == "W3_C02_KAUFMAN_EFFICIENCY_RATIO_EXPANSION_08H":
            horizon_hours = 8
            stop_mult = 1.5
            target_r = 2.0
            if h1_idx >= 12:
                er_chop = np.nanmin(er_1h[h1_idx - 12 : h1_idx]) < 0.30
                er_trend = er_1h[h1_idx] > 0.65
                c_1h = agg60["close"][h1_idx]
                c_1h_prev = agg60["close"][h1_idx - 10]
                if er_chop and er_trend and (c_1h > c_1h_prev) and (flow_15m > 0.15):
                    side = 1
                elif er_chop and er_trend and (c_1h < c_1h_prev) and (flow_15m < -0.15):
                    side = -1

        elif cand_id == "W3_C03_BOLLINGER_BAND_WIDTH_SQUEEZE_EXPLOSION_12H":
            horizon_hours = 12
            stop_mult = 1.8
            target_r = 2.5
            if h1_idx >= 30:
                bw_min = np.nanmin(bb_width_1h[h1_idx - 30 : h1_idx - 1])
                bw_squeeze = bb_width_1h[h1_idx] < bw_min
                v_sma_h = vol_sma1h[h1_idx]
                vol_ok = (not np.isnan(v_sma_h)) and (agg60["volume"][h1_idx] > 1.5 * v_sma_h)
                c_1h = agg60["close"][h1_idx]
                if bw_squeeze and vol_ok:
                    if (c_1h > bb_upper_1h[h1_idx]) and (flow_15m > 0.15):
                        side = 1
                    elif (c_1h < bb_lower_1h[h1_idx]) and (flow_15m < -0.15):
                        side = -1

        elif cand_id == "W3_C04_ASYMMETRIC_LONG_BIASED_TREND_FLOW_12H":
            horizon_hours = 12
            stop_mult = 1.5
            target_r = 2.5
            is_4h_bull = ema20_4h[h4_idx] > ema50_4h[h4_idx]
            is_1h_bull = agg60["close"][h1_idx] > ema20_1h[h1_idx]
            atr_exp = atr14_1h[h1_idx] > atr14_sma10_1h[h1_idx]
            flow_prev = agg15["signed_flow_ratio"][i - 1]
            if is_4h_bull and is_1h_bull and atr_exp and (flow_15m > 0.15) and (flow_prev > 0.15):
                side = 1  # Long only

        elif cand_id == "W3_C05_ASYMMETRIC_SHORT_BIASED_FLOW_COLLAPSE_08H":
            horizon_hours = 8
            stop_mult = 1.2
            target_r = 2.0
            is_4h_bear = ema20_4h[h4_idx] < ema50_4h[h4_idx]
            o_1h = agg60["open"][h1_idx]
            c_1h = agg60["close"][h1_idx]
            vol_1h = agg60["volume"][h1_idx]
            v_sma_h = vol_sma1h[h1_idx]
            is_sharp_drop = (o_1h - c_1h) > 1.5 * atr_1h
            vol_surge = (not np.isnan(v_sma_h)) and (vol_1h > 2.0 * v_sma_h)
            if is_4h_bear and is_sharp_drop and vol_surge and (flow_15m < -0.25):
                side = -1  # Short only

        elif cand_id == "W3_C06_TIME_WEIGHTED_SESSION_PULLBACK_08H":
            horizon_hours = 8
            stop_mult = 1.5
            target_r = 2.0
            t_next = t_event + 1
            utc_hour = (t_next // 3600_000) % 24
            if 10 <= utc_hour <= 18:
                is_4h_bull = (agg240["close"][h4_idx] > ema20_4h[h4_idx] > ema50_4h[h4_idx])
                is_4h_bear = (agg240["close"][h4_idx] < ema20_4h[h4_idx] < ema50_4h[h4_idx])
                ema10_val = ema10_1h[h1_idx]
                touch_bull = (low_15m <= ema10_val <= high_15m) and (close_15m > ema10_val)
                touch_bear = (low_15m <= ema10_val <= high_15m) and (close_15m < ema10_val)
                if is_4h_bull and touch_bull and (flow_15m > 0.15):
                    side = 1
                elif is_4h_bear and touch_bear and (flow_15m < -0.15):
                    side = -1

        if side != 0:
            stop_dist = stop_mult * atr_1h
            stop_price = close_15m - side * stop_dist
            t_round = int(agg15["open_time"][i] + 15 * 60000)
            signals.append({
                "event_id": f"{cand_id}_{t_round}_{side}",
                "candidate_id": cand_id,
                "side": side,
                "event_time": t_round - 60000,
                "decision_at": t_round,
                "entry_at": t_round + 60000,
                "decision_close": close_15m,
                "atr_hour": atr_1h,
                "stop": stop_price,
                "target_r": target_r,
                "horizon_hours": horizon_hours,
            })

    return signals
