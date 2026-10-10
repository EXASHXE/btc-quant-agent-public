"""Causal, completed-bar BTC range/reversal/flow/volatility signal generators.

All features are computed exclusively from completed UTC 5m/15m/1h/4h bars.
A bar closing at `event_time` is evaluated at `decision_at = event_time + 60_000`
and its earliest permissible fill is the next 1m open at `entry_at = event_time + 120_000`.
"""
from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from scripts.strategy_research.g2_btc_empirical_fast_r1.signals import (
    FOUR_HOUR_MS,
    HOUR_MS,
    MINUTE_MS,
    _ema,
    _last_complete,
)

DAY_MS = 24 * HOUR_MS


def aggregate_with_taker(data: np.ndarray, minutes: int) -> dict[str, np.ndarray]:
    """Aggregate contiguous 1m bars into aligned UTC windows with taker-buy volume."""
    if minutes not in (5, 15, 60, 240):
        raise ValueError(f"Unsupported aggregation window: {minutes}m")
    bars = np.asarray(data, dtype=np.float64)
    if bars.ndim != 2 or bars.shape[1] not in (6, 7) or len(bars) == 0:
        raise ValueError("Expected non-empty 6 or 7 column 1m array")
    if bars.shape[1] == 6:
        tb = 0.5 * bars[:, 5:6]
        bars = np.hstack([bars, tb])
    times = bars[:, 0]
    if (
        not np.all(np.isfinite(bars))
        or np.any(times != np.floor(times))
        or np.any(times % MINUTE_MS != 0)
        or (len(times) > 1 and np.any(np.diff(times) != MINUTE_MS))
    ):
        raise ValueError("Minute rows must be finite, unique, aligned, and contiguous")
    if (
        np.any(bars[:, 2] < np.maximum(bars[:, 1], bars[:, 4]))
        or np.any(bars[:, 3] > np.minimum(bars[:, 1], bars[:, 4]))
        or np.any(bars[:, 2] < bars[:, 3])
        or np.any(bars[:, 5] < 0)
        or np.any(bars[:, 6] < -1e-6)
        or np.any(bars[:, 6] > bars[:, 5] + 1e-5)
    ):
        raise ValueError("Malformed OHLCV or taker_buy_volume")

    window_ms = minutes * MINUTE_MS
    first_window_start = ((int(times[0]) + window_ms - 1) // window_ms) * window_ms
    first = int(np.searchsorted(times, first_window_start))
    last = len(bars) - ((len(bars) - first) % minutes)
    names = (
        "end_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "taker_buy_volume",
        "taker_sell_volume",
        "signed_flow",
        "signed_flow_ratio",
    )
    if last <= first:
        return {name: np.empty(0, dtype=np.float64) for name in names}
    chunks = bars[first:last].reshape(-1, minutes, 7)
    vol = np.sum(chunks[:, :, 5], axis=1)
    tb_vol = np.minimum(vol, np.maximum(0.0, np.sum(chunks[:, :, 6], axis=1)))
    ts_vol = np.maximum(0.0, vol - tb_vol)
    signed_flow = tb_vol - ts_vol
    signed_flow_ratio = np.divide(
        signed_flow, vol, out=np.zeros_like(vol), where=vol > 0
    )
    result = {
        "end_ms": chunks[:, -1, 0] + MINUTE_MS,
        "open": chunks[:, 0, 1],
        "high": np.max(chunks[:, :, 2], axis=1),
        "low": np.min(chunks[:, :, 3], axis=1),
        "close": chunks[:, -1, 4],
        "volume": vol,
        "taker_buy_volume": tb_vol,
        "taker_sell_volume": ts_vol,
        "signed_flow": signed_flow,
        "signed_flow_ratio": signed_flow_ratio,
    }
    if np.any(result["end_ms"] % window_ms):
        raise AssertionError("UTC aggregate did not close on expected boundary")
    return result


def _sma_fast(values: np.ndarray, window: int) -> np.ndarray:
    output = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) < window or window <= 0:
        return output
    views = sliding_window_view(values, window)
    finite_mask = np.all(np.isfinite(views), axis=-1)
    means = np.mean(views, axis=-1)
    output[window - 1 :] = np.where(finite_mask, means, np.nan)
    return output


def _atr_fast(bars: dict[str, np.ndarray], window: int = 20) -> np.ndarray:
    close = bars["close"]
    if len(close) == 0:
        return np.empty(0, dtype=np.float64)
    prior = np.empty(len(close), dtype=np.float64)
    prior[0] = close[0]
    prior[1:] = close[:-1]
    tr = np.maximum.reduce(
        (
            bars["high"] - bars["low"],
            np.abs(bars["high"] - prior),
            np.abs(bars["low"] - prior),
        )
    )
    return _sma_fast(tr, window)


def _er_fast(close: np.ndarray, window: int = 12) -> np.ndarray:
    output = np.full(len(close), np.nan, dtype=np.float64)
    if len(close) <= window or window <= 0:
        return output
    abs_diff = np.abs(np.diff(close))
    denom = sliding_window_view(abs_diff, window).sum(axis=-1)
    num = np.abs(close[window:] - close[:-window])
    valid = denom > 0
    res = np.full(len(denom), np.nan, dtype=np.float64)
    res[valid] = num[valid] / denom[valid]
    output[window:] = res
    return output


def _eligible_vol(close: float, atr_hour: float) -> bool:
    if not (np.isfinite(close) and np.isfinite(atr_hour) and close > 0 and atr_hour > 0):
        return False
    bps = 10_000.0 * atr_hour / close
    return 15.0 <= bps <= 250.0


def _make_event(
    candidate_id: str,
    family: str,
    horizon: int,
    side: int,
    event_end: float,
    close: float,
    atr_hour: float,
    stop: float,
    trend_end: float,
    event_id: str,
    target_r: float = 2.0,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "family": family,
        "horizon_hours": int(horizon),
        "side": int(side),
        "event_time": int(event_end),
        "decision_at": int(event_end + MINUTE_MS),
        "entry_at": int(event_end + 2 * MINUTE_MS),
        "decision_close": float(close),
        "atr_hour": float(atr_hour),
        "stop": float(stop),
        "target_r": float(target_r),
        "trend_bar_end": int(trend_end),
        "regime_vol_bps": float(10_000.0 * atr_hour / close),
        "event_id": str(event_id),
    }


def generate_wave_signals(data: np.ndarray, registry: dict) -> dict[str, list[dict]]:
    """Generate signals for all registered candidates in a wave (WAVE_01..WAVE_04)."""
    q15 = aggregate_with_taker(data, 15)
    h1 = aggregate_with_taker(data, 60)
    f4 = aggregate_with_taker(data, 240)

    candidates = registry["candidates"]
    if not (1 <= len(candidates) <= 6):
        raise ValueError("Each wave must register between 1 and 6 candidates")

    output: dict[str, list[dict]] = {}
    for c in candidates:
        cid = c.get("candidate_id", c.get("id"))
        if cid in output:
            raise ValueError(f"Duplicate candidate_id: {cid}")
        output[cid] = []

    if len(q15["end_ms"]) == 0 or len(h1["end_ms"]) == 0 or len(f4["end_ms"]) == 0:
        return output

    # Precompute common multi-timeframe completed-bar features
    atr15_20 = _atr_fast(q15, 20)
    atr15_8 = _atr_fast(q15, 8)
    atr15_32 = _atr_fast(q15, 32)
    vol15_sma20 = _sma_fast(q15["volume"], 20)
    sfr15 = q15["signed_flow_ratio"]

    atr1_20 = _atr_fast(h1, 20)
    sfr1 = h1["signed_flow_ratio"]

    atr4_20 = _atr_fast(f4, 20)
    er4_12 = _er_fast(f4["close"], 12)
    er4_6 = _er_fast(f4["close"], 6)

    by_id = {c.get("candidate_id", c.get("id")): c for c in candidates}

    # --- WAVE 1 CANDIDATES ---
    # 1. W1_C01_FAILED_ACCEPTANCE_REENTRY_04H
    if "W1_C01_FAILED_ACCEPTANCE_REENTRY_04H" in by_id:
        cid = "W1_C01_FAILED_ACCEPTANCE_REENTRY_04H"
        row = by_id[cid]
        horizon = int(row["horizon_hours"])
        for k in range(26, len(q15["end_ms"])):
            end = q15["end_ms"][k]
            h = _last_complete(h1["end_ms"], end)
            j = _last_complete(f4["end_ms"], end)
            if j < 59 or h < 20:
                continue
            close = q15["close"][k]
            opened = q15["open"][k]
            a15 = atr15_20[k]
            a1h = atr1_20[h]
            if not (np.isfinite(a15) and a15 > 0 and _eligible_vol(close, a1h)):
                continue
            b_high = float(np.max(q15["high"][k - 26 : k - 2]))
            b_low = float(np.min(q15["low"][k - 26 : k - 2]))
            # LONG: excursion below b_low at k-2 or k-1, both k-1 and k close back inside, flow flips positive
            if (
                min(q15["low"][k - 2], q15["low"][k - 1]) < b_low - 0.10 * a15
                and q15["close"][k - 1] >= b_low
                and close >= b_low + 0.05 * a15
                and close > opened
                and sfr15[k] >= 0.04
            ):
                ext = float(np.min(q15["low"][k - 2 : k + 1]))
                raw_dist = max(abs(close - ext) + 0.35 * a15, 0.80 * a1h)
                stop = close - raw_dist
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        1,
                        end,
                        close,
                        a1h,
                        stop,
                        f4["end_ms"][j],
                        f"{cid}:1:{int(end)}",
                        2.0,
                    )
                )
            # SHORT: excursion above b_high at k-2 or k-1, both k-1 and k close back inside, flow flips negative
            if (
                max(q15["high"][k - 2], q15["high"][k - 1]) > b_high + 0.10 * a15
                and q15["close"][k - 1] <= b_high
                and close <= b_high - 0.05 * a15
                and close < opened
                and sfr15[k] <= -0.04
            ):
                ext = float(np.max(q15["high"][k - 2 : k + 1]))
                raw_dist = max(abs(ext - close) + 0.35 * a15, 0.80 * a1h)
                stop = close + raw_dist
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        -1,
                        end,
                        close,
                        a1h,
                        stop,
                        f4["end_ms"][j],
                        f"{cid}:-1:{int(end)}",
                        2.0,
                    )
                )

    # 2. W1_C02_RANGE_MEAN_REVERT_WITH_VOLUME_04H
    if "W1_C02_RANGE_MEAN_REVERT_WITH_VOLUME_04H" in by_id:
        cid = "W1_C02_RANGE_MEAN_REVERT_WITH_VOLUME_04H"
        row = by_id[cid]
        horizon = int(row["horizon_hours"])
        for k in range(21, len(q15["end_ms"])):
            end = q15["end_ms"][k]
            h = _last_complete(h1["end_ms"], end)
            j = _last_complete(f4["end_ms"], end)
            if j < 59 or h < 20:
                continue
            if not (np.isfinite(er4_12[j]) and er4_12[j] <= 0.30):
                continue
            close = q15["close"][k]
            opened = q15["open"][k]
            a15 = atr15_20[k]
            a1h = atr1_20[h]
            v_sma = vol15_sma20[k - 1]
            if not (
                np.isfinite(a15)
                and a15 > 0
                and np.isfinite(v_sma)
                and v_sma > 0
                and _eligible_vol(close, a1h)
            ):
                continue
            if q15["volume"][k] < 0.90 * v_sma:
                continue
            h16 = float(np.max(q15["high"][k - 16 : k]))
            l16 = float(np.min(q15["low"][k - 16 : k]))
            width = h16 - l16
            if not (1.20 * a1h <= width <= 4.50 * a1h):
                continue
            mid = 0.5 * (h16 + l16)
            # LONG
            if (
                q15["low"][k] <= l16 + 0.20 * width
                and l16 + 0.22 * width <= close <= mid - 0.10 * width
                and close > opened
                and sfr15[k] >= 0.02
            ):
                raw_stop = l16 - 0.40 * a15
                raw_dist = max(abs(close - raw_stop), 0.90 * a1h)
                stop = close - raw_dist
                dyn_r = min(2.0, max(1.5, abs(mid - close) / raw_dist))
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        1,
                        end,
                        close,
                        a1h,
                        stop,
                        f4["end_ms"][j],
                        f"{cid}:1:{int(end)}",
                        dyn_r,
                    )
                )
            # SHORT
            if (
                q15["high"][k] >= h16 - 0.20 * width
                and mid + 0.10 * width <= close <= h16 - 0.22 * width
                and close < opened
                and sfr15[k] <= -0.02
            ):
                raw_stop = h16 + 0.40 * a15
                raw_dist = max(abs(raw_stop - close), 0.90 * a1h)
                stop = close + raw_dist
                dyn_r = min(2.0, max(1.5, abs(close - mid) / raw_dist))
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        -1,
                        end,
                        close,
                        a1h,
                        stop,
                        f4["end_ms"][j],
                        f"{cid}:-1:{int(end)}",
                        dyn_r,
                    )
                )

    # 3. W1_C03_VOL_COMPRESSION_TO_REVERT_08H
    if "W1_C03_VOL_COMPRESSION_TO_REVERT_08H" in by_id:
        cid = "W1_C03_VOL_COMPRESSION_TO_REVERT_08H"
        row = by_id[cid]
        horizon = int(row["horizon_hours"])
        for k in range(33, len(q15["end_ms"])):
            end = q15["end_ms"][k]
            h = _last_complete(h1["end_ms"], end)
            j = _last_complete(f4["end_ms"], end)
            if j < 59 or h < 20:
                continue
            a8_prev = atr15_8[k - 1]
            a32_prev = atr15_32[k - 1]
            a15 = atr15_20[k]
            a1h = atr1_20[h]
            v_sma = vol15_sma20[k - 1]
            close = q15["close"][k]
            opened = q15["open"][k]
            if not (
                np.isfinite(a8_prev)
                and np.isfinite(a32_prev)
                and a32_prev > 0
                and np.isfinite(a15)
                and a15 > 0
                and np.isfinite(v_sma)
                and v_sma > 0
                and _eligible_vol(close, a1h)
            ):
                continue
            if a8_prev / a32_prev > 0.82:
                continue
            h12 = float(np.max(q15["high"][k - 12 : k]))
            l12 = float(np.min(q15["low"][k - 12 : k]))
            low_vol = q15["volume"][k] <= 1.35 * v_sma
            # LONG
            if (
                q15["low"][k] < l12 - 0.15 * a15
                and close >= l12
                and close > opened
                and (low_vol or sfr15[k] >= 0.02)
            ):
                stop = close - 1.40 * a1h
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        1,
                        end,
                        close,
                        a1h,
                        stop,
                        f4["end_ms"][j],
                        f"{cid}:1:{int(end)}",
                        2.0,
                    )
                )
            # SHORT
            if (
                q15["high"][k] > h12 + 0.15 * a15
                and close <= h12
                and close < opened
                and (low_vol or sfr15[k] <= -0.02)
            ):
                stop = close + 1.40 * a1h
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        -1,
                        end,
                        close,
                        a1h,
                        stop,
                        f4["end_ms"][j],
                        f"{cid}:-1:{int(end)}",
                        2.0,
                    )
                )

    # 4. W1_C04_AGGRESSIVE_FLOW_EXHAUSTION_08H
    if "W1_C04_AGGRESSIVE_FLOW_EXHAUSTION_08H" in by_id:
        cid = "W1_C04_AGGRESSIVE_FLOW_EXHAUSTION_08H"
        row = by_id[cid]
        horizon = int(row["horizon_hours"])
        for k in range(23, len(q15["end_ms"])):
            end = q15["end_ms"][k]
            h = _last_complete(h1["end_ms"], end)
            j = _last_complete(f4["end_ms"], end)
            if j < 59 or h < 20:
                continue
            close = q15["close"][k]
            opened = q15["open"][k]
            a15 = atr15_20[k]
            a15_prev = atr15_20[k - 1]
            a1h = atr1_20[h]
            v_sma = vol15_sma20[k - 1]
            if not (
                np.isfinite(a15)
                and a15 > 0
                and np.isfinite(a15_prev)
                and a15_prev > 0
                and np.isfinite(v_sma)
                and v_sma > 0
                and _eligible_vol(close, a1h)
            ):
                continue
            vol3 = float(np.sum(q15["volume"][k - 3 : k]))
            if vol3 < 3.0 * v_sma:
                continue
            mean_sfr3 = float(np.mean(sfr15[k - 3 : k]))
            b3 = abs(q15["close"][k - 3] - q15["open"][k - 3])
            b2 = abs(q15["close"][k - 2] - q15["open"][k - 2])
            b1 = abs(q15["close"][k - 1] - q15["open"][k - 1])
            if b1 > 0.85 * max(b3, b2):
                continue
            for side in (1, -1):
                if (
                    (-side) * mean_sfr3 >= 0.05
                    and (-side) * (q15["close"][k - 1] - q15["open"][k - 3]) >= 0.60 * a15_prev
                    and side * (close - opened) >= 0.30 * a15
                    and side * sfr15[k] >= 0.0
                ):
                    stop = close - side * 1.50 * a1h
                    output[cid].append(
                        _make_event(
                            cid,
                            row["family"],
                            horizon,
                            side,
                            end,
                            close,
                            a1h,
                            stop,
                            f4["end_ms"][j],
                            f"{cid}:{side}:{int(end)}",
                            2.0,
                        )
                    )

    # 5. W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H
    if "W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H" in by_id:
        cid = "W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H"
        row = by_id[cid]
        horizon = int(row["horizon_hours"])
        emitted_day_side: set[tuple[int, int]] = set()
        for k in range(34, len(q15["end_ms"])):
            end = int(q15["end_ms"][k])
            day_start = (end // DAY_MS) * DAY_MS
            tod_ms = end - day_start
            # Evaluate completed 15m bars with end_ms in [08:15, 16:00] UTC
            if not (8 * HOUR_MS + 15 * MINUTE_MS <= tod_ms <= 16 * HOUR_MS):
                continue
            h = _last_complete(h1["end_ms"], end)
            j = _last_complete(f4["end_ms"], end)
            if j < 59 or h < 20:
                continue
            close = q15["close"][k]
            opened = q15["open"][k]
            a15 = atr15_20[k]
            a1h = atr1_20[h]
            if not (np.isfinite(a15) and a15 > 0 and _eligible_vol(close, a1h)):
                continue
            # Find the 32 completed 15m bars in [00:00, 08:00) UTC of this day
            # Their end_ms are in [day_start + 15m, day_start + 8h]
            s_idx_start = int(np.searchsorted(q15["end_ms"], day_start + 15 * MINUTE_MS, side="left"))
            s_idx_end = int(np.searchsorted(q15["end_ms"], day_start + 8 * HOUR_MS, side="right"))
            if s_idx_end - s_idx_start != 32:
                continue
            s_high = float(np.max(q15["high"][s_idx_start:s_idx_end]))
            s_low = float(np.min(q15["low"][s_idx_start:s_idx_end]))
            day_id = day_start // DAY_MS
            # LONG
            if (
                (day_id, 1) not in emitted_day_side
                and min(q15["low"][k - 1], q15["low"][k]) <= s_low - 0.20 * a1h
                and q15["low"][k] >= s_low - 2.50 * a1h
                and close >= s_low - 0.10 * a1h
                and (close - opened) >= 0.20 * a15
                and sfr15[k] >= 0.0
            ):
                emitted_day_side.add((day_id, 1))
                stop = close - 1.60 * a1h
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        1,
                        end,
                        close,
                        a1h,
                        stop,
                        f4["end_ms"][j],
                        f"{cid}:1:{end}",
                        2.0,
                    )
                )
            # SHORT
            if (
                (day_id, -1) not in emitted_day_side
                and max(q15["high"][k - 1], q15["high"][k]) >= s_high + 0.20 * a1h
                and q15["high"][k] <= s_high + 2.50 * a1h
                and close <= s_high + 0.10 * a1h
                and (opened - close) >= 0.20 * a15
                and sfr15[k] <= 0.0
            ):
                emitted_day_side.add((day_id, -1))
                stop = close + 1.60 * a1h
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        -1,
                        end,
                        close,
                        a1h,
                        stop,
                        f4["end_ms"][j],
                        f"{cid}:-1:{end}",
                        2.0,
                    )
                )

    # 6. W1_C06_REGIME_TRANSITION_REVERSAL_24H
    if "W1_C06_REGIME_TRANSITION_REVERSAL_24H" in by_id:
        cid = "W1_C06_REGIME_TRANSITION_REVERSAL_24H"
        row = by_id[cid]
        horizon = int(row["horizon_hours"])
        for j in range(60, len(f4["end_ms"])):
            end = f4["end_ms"][j]
            h = _last_complete(h1["end_ms"], end)
            if h < 20 or int(h1["end_ms"][h]) != int(end):
                continue
            close4 = f4["close"][j]
            open4 = f4["open"][j]
            a4 = atr4_20[j]
            a1h = atr1_20[h]
            if not (
                np.isfinite(a4)
                and a4 > 0
                and np.all(np.isfinite(er4_6[j - 3 : j + 1]))
                and _eligible_vol(close4, a1h)
            ):
                continue
            if float(np.max(er4_6[j - 3 : j])) < 0.42:
                continue
            if not (er4_6[j] <= er4_6[j - 1] or er4_6[j] <= 0.45):
                continue
            # LONG: prior down-move exhausted, two adjacent 4h lows hold within 0.35 ATR4h, reversal close
            if (
                (f4["close"][j - 4] - float(np.min(f4["low"][j - 3 : j]))) >= 1.0 * a4
                and f4["low"][j] >= f4["low"][j - 1] - 0.35 * a4
                and close4 > open4
                and sfr1[h] >= -0.02
            ):
                stop = close4 - 1.80 * a1h
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        1,
                        end,
                        close4,
                        a1h,
                        stop,
                        end,
                        f"{cid}:1:{int(end)}",
                        2.0,
                    )
                )
            # SHORT: prior up-move exhausted, two adjacent 4h highs hold within 0.35 ATR4h, reversal close
            if (
                (float(np.max(f4["high"][j - 3 : j])) - f4["close"][j - 4]) >= 1.0 * a4
                and f4["high"][j] <= f4["high"][j - 1] + 0.35 * a4
                and close4 < open4
                and sfr1[h] <= 0.02
            ):
                stop = close4 + 1.80 * a1h
                output[cid].append(
                    _make_event(
                        cid,
                        row["family"],
                        horizon,
                        -1,
                        end,
                        close4,
                        a1h,
                        stop,
                        end,
                        f"{cid}:-1:{int(end)}",
                        2.0,
                    )
                )

    return output
