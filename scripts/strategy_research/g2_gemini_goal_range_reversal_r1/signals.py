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

    # --- WAVE 2 CANDIDATES ---
    if any(k.startswith("W2_") for k in by_id):
        atr15_14 = _atr_fast(q15, 14)
        atr15_48 = _atr_fast(q15, 48)
        atr15_192 = _atr_fast(q15, 192)
        vol15_sma96 = _sma_fast(q15["volume"], 96)
        close_sma96 = _sma_fast(q15["close"], 96)
        close_sma192 = _sma_fast(q15["close"], 192)
        views192 = sliding_window_view(q15["close"], 192) if len(q15["close"]) >= 192 else np.empty((0, 192))
        close_std192 = np.full(len(q15["close"]), np.nan, dtype=np.float64)
        if len(views192) > 0:
            close_std192[191:] = np.std(views192, axis=-1)

        # 2-bar (30m) and 4-bar (1h) volume-weighted taker imbalance on 15m bars
        vol2 = _sma_fast(q15["volume"], 2) * 2.0
        sf2 = _sma_fast(q15["signed_flow"], 2) * 2.0
        taker_imb_2 = np.divide(sf2, vol2, out=np.zeros_like(sf2), where=vol2 > 0)

        vol4 = _sma_fast(q15["volume"], 4) * 4.0
        sf4 = _sma_fast(q15["signed_flow"], 4) * 4.0
        taker_imb_4 = np.divide(sf4, vol4, out=np.zeros_like(sf4), where=vol4 > 0)

        def _clamp_stop(close_px: float, side_val: int, raw_dist: float) -> float:
            dist = min(max(raw_dist, 0.0040 * close_px), 0.0250 * close_px)
            return close_px - side_val * dist

        # 1. W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H
        if "W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H" in by_id:
            cid = "W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 12))
            for k in range(292, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                if end % HOUR_MS != 0:
                    continue
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                close = q15["close"][k]
                a15 = atr15_14[k]
                a1h = atr1_20[h]
                if not (np.isfinite(a15) and a15 > 0 and _eligible_vol(close, a1h)):
                    continue
                hi_72h = float(np.max(q15["high"][k - 291 : k - 3]))
                lo_72h = float(np.min(q15["low"][k - 291 : k - 3]))
                width_bps = (hi_72h - lo_72h) / lo_72h * 10_000.0
                if not (180.0 <= width_bps <= 1200.0):
                    continue
                sweep_lo = float(np.min(q15["low"][k - 3 : k + 1]))
                sweep_hi = float(np.max(q15["high"][k - 3 : k + 1]))
                ret_1h = close - q15["open"][k - 3]
                # LONG: 1h window swept below 72h low, closed >= 0.25 ATR14 back inside range, positive 1h return
                if (
                    sweep_lo < lo_72h
                    and close >= lo_72h + 0.25 * a15
                    and ret_1h > 0
                    and taker_imb_4[k] >= -0.02
                ):
                    stop = _clamp_stop(close, 1, 3.0 * a15)
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
                            1.55,
                        )
                    )
                # SHORT: 1h window swept above 72h high, closed >= 0.25 ATR14 back inside range, negative 1h return
                if (
                    sweep_hi > hi_72h
                    and close <= hi_72h - 0.25 * a15
                    and ret_1h < 0
                    and taker_imb_4[k] <= 0.02
                ):
                    stop = _clamp_stop(close, -1, 3.0 * a15)
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
                            1.55,
                        )
                    )

        # 2. W2_C02_EXTREME_BOLLINGER_FLOW_DIVERGENCE_08H
        if "W2_C02_EXTREME_BOLLINGER_FLOW_DIVERGENCE_08H" in by_id:
            cid = "W2_C02_EXTREME_BOLLINGER_FLOW_DIVERGENCE_08H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 8))
            for k in range(192, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                close = q15["close"][k]
                opened = q15["open"][k]
                a15 = atr15_14[k]
                a1h = atr1_20[h]
                m192 = close_sma192[k]
                s192 = close_std192[k]
                if not (
                    np.isfinite(a15)
                    and a15 > 0
                    and np.isfinite(m192)
                    and np.isfinite(s192)
                    and s192 > 0
                    and _eligible_vol(close, a1h)
                ):
                    continue
                drift_48h_bps = abs(close - q15["close"][k - 192]) / q15["close"][k - 192] * 10_000.0
                if drift_48h_bps > 550.0:
                    continue
                z = (close - m192) / s192
                if z <= -2.15 and close > opened and taker_imb_2[k] >= 0.04:
                    stop = _clamp_stop(close, 1, 2.8 * a15)
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
                            1.55,
                        )
                    )
                elif z >= 2.15 and close < opened and taker_imb_2[k] <= -0.04:
                    stop = _clamp_stop(close, -1, 2.8 * a15)
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
                            1.55,
                        )
                    )

        # 3. W2_C03_LOW_VOL_REGIME_SHOCK_FADE_24H
        if "W2_C03_LOW_VOL_REGIME_SHOCK_FADE_24H" in by_id:
            cid = "W2_C03_LOW_VOL_REGIME_SHOCK_FADE_24H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 24))
            for k in range(195, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                close = q15["close"][k]
                a15 = atr15_14[k]
                a32 = atr15_32[k]
                a192 = atr15_192[k]
                a1h = atr1_20[h]
                if not (
                    np.isfinite(a15)
                    and a15 > 0
                    and np.isfinite(a32)
                    and np.isfinite(a192)
                    and a192 > 0
                    and _eligible_vol(close, a1h)
                ):
                    continue
                if 10_000.0 * a15 / close > 65.0 or (a32 / a192) > 1.25:
                    continue
                shock_4h = q15["close"][k - 2] - q15["close"][k - 16]
                rev_30m = close - q15["close"][k - 2]
                # LONG: 4h down-shock >= 1.8 ATR14, 30m positive reversal >= 0.2 ATR14, positive 30m taker flow
                if (
                    shock_4h <= -1.8 * a15
                    and rev_30m >= 0.20 * a15
                    and taker_imb_2[k] > 0.0
                ):
                    stop = _clamp_stop(close, 1, 3.5 * a15)
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
                            1.55,
                        )
                    )
                # SHORT: 4h up-shock >= 1.8 ATR14, 30m negative reversal >= 0.2 ATR14, negative 30m taker flow
                elif (
                    shock_4h >= 1.8 * a15
                    and rev_30m <= -0.20 * a15
                    and taker_imb_2[k] < 0.0
                ):
                    stop = _clamp_stop(close, -1, 3.5 * a15)
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
                            1.55,
                        )
                    )

        # 4. W2_C04_CLIMAX_VOLUME_TAKER_ABSORPTION_12H
        if "W2_C04_CLIMAX_VOLUME_TAKER_ABSORPTION_12H" in by_id:
            cid = "W2_C04_CLIMAX_VOLUME_TAKER_ABSORPTION_12H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 12))
            for k in range(98, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                close = q15["close"][k]
                opened = q15["open"][k]
                a15 = atr15_14[k]
                a1h = atr1_20[h]
                v96 = vol15_sma96[k - 1]
                if not (
                    np.isfinite(a15)
                    and a15 > 0
                    and np.isfinite(v96)
                    and v96 > 0
                    and _eligible_vol(close, a1h)
                ):
                    continue
                drift_24h_bps = abs(close - q15["close"][k - 96]) / q15["close"][k - 96] * 10_000.0
                if drift_24h_bps > 650.0:
                    continue
                vol_8 = float(np.sum(q15["volume"][k - 7 : k + 1]))
                if vol_8 < 1.65 * 8.0 * v96:
                    continue
                hi_8 = float(np.max(q15["high"][k - 7 : k + 1]))
                lo_8 = float(np.min(q15["low"][k - 7 : k + 1]))
                if (hi_8 - lo_8) < 2.2 * a15:
                    continue
                # LONG: 2h selloff climax rejected by >= 0.5 ATR from 2h low
                if (
                    q15["close"][k - 1] < q15["open"][k - 7]
                    and (close - lo_8) >= 0.50 * a15
                    and close > opened
                    and taker_imb_2[k] > 0.0
                ):
                    stop = _clamp_stop(close, 1, 3.0 * a15)
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
                            1.55,
                        )
                    )
                # SHORT: 2h buy climax rejected by >= 0.5 ATR from 2h high
                elif (
                    q15["close"][k - 1] > q15["open"][k - 7]
                    and (hi_8 - close) >= 0.50 * a15
                    and close < opened
                    and taker_imb_2[k] < 0.0
                ):
                    stop = _clamp_stop(close, -1, 3.0 * a15)
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
                            1.55,
                        )
                    )

        # 5. W2_C05_US_CLOSE_ASIA_OPEN_REVERSAL_12H
        if "W2_C05_US_CLOSE_ASIA_OPEN_REVERSAL_12H" in by_id:
            cid = "W2_C05_US_CLOSE_ASIA_OPEN_REVERSAL_12H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 12))
            emitted_session: set[tuple[int, int, int]] = set()
            for k in range(36, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                day_start = (end // DAY_MS) * DAY_MS
                tod_ms = end - day_start
                # Handoff windows: [00:15, 01:30] UTC (session 0) or [20:15, 21:30] UTC (session 20)
                if 15 * MINUTE_MS <= tod_ms <= 90 * MINUTE_MS:
                    sess_id = 0
                elif 20 * HOUR_MS + 15 * MINUTE_MS <= tod_ms <= 21 * HOUR_MS + 30 * MINUTE_MS:
                    sess_id = 20
                else:
                    continue
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                close = q15["close"][k]
                a15 = atr15_14[k]
                a1h = atr1_20[h]
                if not (np.isfinite(a15) and a15 > 0 and _eligible_vol(close, a1h)):
                    continue
                move_8h = q15["close"][k - 2] - q15["close"][k - 34]
                if not (1.6 * a15 <= abs(move_8h) <= 6.5 * a15):
                    continue
                rev_30m = close - q15["close"][k - 2]
                day_idx = day_start // DAY_MS
                if (
                    move_8h < 0
                    and (day_idx, sess_id, 1) not in emitted_session
                    and rev_30m >= 0.25 * a15
                    and taker_imb_2[k] > 0.0
                ):
                    emitted_session.add((day_idx, sess_id, 1))
                    stop = _clamp_stop(close, 1, 3.2 * a15)
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
                            1.55,
                        )
                    )
                elif (
                    move_8h > 0
                    and (day_idx, sess_id, -1) not in emitted_session
                    and rev_30m <= -0.25 * a15
                    and taker_imb_2[k] < 0.0
                ):
                    emitted_session.add((day_idx, sess_id, -1))
                    stop = _clamp_stop(close, -1, 3.2 * a15)
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
                            1.55,
                        )
                    )

        # 6. W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H
        if "W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H" in by_id:
            cid = "W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 4))
            for k in range(202, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                close = q15["close"][k]
                a15 = atr15_14[k]
                a48_pre = atr15_48[k - 8]
                a192_pre = atr15_192[k - 8]
                m96 = close_sma96[k]
                a1h = atr1_20[h]
                if not (
                    np.isfinite(a15)
                    and a15 > 0
                    and np.isfinite(a48_pre)
                    and np.isfinite(a192_pre)
                    and a192_pre > 0
                    and np.isfinite(m96)
                    and _eligible_vol(close, a1h)
                ):
                    continue
                if (a48_pre / a192_pre) > 0.85:
                    continue
                if abs(close - m96) > 0.80 * a15:
                    continue
                hi_8 = float(np.max(q15["high"][k - 8 : k]))
                lo_8 = float(np.min(q15["low"][k - 8 : k]))
                snap_30m = close - q15["close"][k - 2]
                # LONG: false downside expansion out of compression (>= 1.6 ATR below m96) that snapped back inside 0.8 ATR of m96
                if (m96 - lo_8) >= 1.60 * a15 and snap_30m >= 0.45 * a15:
                    stop = _clamp_stop(close, 1, 2.5 * a15)
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
                            1.55,
                        )
                    )
                # SHORT: false upside expansion out of compression (>= 1.6 ATR above m96) that snapped back inside 0.8 ATR of m96
                elif (hi_8 - m96) >= 1.60 * a15 and snap_30m <= -0.45 * a15:
                    stop = _clamp_stop(close, -1, 2.5 * a15)
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
                            1.55,
                        )
                    )

    # --- WAVE 3 CANDIDATES ---
    if any(k.startswith("W3_") for k in by_id):
        atr15_14 = _atr_fast(q15, 14)
        atr15_48 = _atr_fast(q15, 48)
        atr15_192 = _atr_fast(q15, 192)
        close_sma96 = _sma_fast(q15["close"], 96)
        vol1_sma20 = _sma_fast(h1["volume"], 20)

        def _clamp_stop_bps(close_px: float, side_val: int, raw_dist: float, min_bps: float = 85.0) -> float:
            dist = min(max(raw_dist, (min_bps / 10_000.0) * close_px), 0.0250 * close_px)
            return close_px - side_val * dist

        # 1. W3_C01_HIGH_VOL_72H_FAILED_BREAKOUT_WIDE_TARGET_24H
        if "W3_C01_HIGH_VOL_72H_FAILED_BREAKOUT_WIDE_TARGET_24H" in by_id:
            cid = "W3_C01_HIGH_VOL_72H_FAILED_BREAKOUT_WIDE_TARGET_24H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 24))
            for k in range(292, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                if end % HOUR_MS != 0:
                    continue
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 74:
                    continue
                close = q15["close"][k]
                a15 = atr15_14[k]
                a1h = atr1_20[h]
                if not (np.isfinite(a15) and a15 > 0 and _eligible_vol(close, a1h)):
                    continue
                if 10_000.0 * a1h / close < 65.0:
                    continue
                hi_72h = float(np.max(h1["high"][h - 72 : h]))
                lo_72h = float(np.min(h1["low"][h - 72 : h]))
                width_bps = (hi_72h - lo_72h) / lo_72h * 10_000.0
                if not (220.0 <= width_bps <= 1400.0):
                    continue
                sweep_lo = float(np.min(h1["low"][h - 1 : h + 1]))
                sweep_hi = float(np.max(h1["high"][h - 1 : h + 1]))
                # LONG: swept 72h low over last 2h, closed >= 0.15 ATR15 back inside 72h range, bullish 1h bar
                if (
                    sweep_lo < lo_72h
                    and close >= lo_72h + 0.15 * a15
                    and h1["close"][h] > h1["open"][h]
                    and sfr1[h] >= -0.04
                ):
                    stop = _clamp_stop_bps(close, 1, 1.60 * a1h, 85.0)
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
                            2.6,
                        )
                    )
                # SHORT: swept 72h high over last 2h, closed >= 0.15 ATR15 back inside 72h range, bearish 1h bar
                elif (
                    sweep_hi > hi_72h
                    and close <= hi_72h - 0.15 * a15
                    and h1["close"][h] < h1["open"][h]
                    and sfr1[h] <= 0.04
                ):
                    stop = _clamp_stop_bps(close, -1, 1.60 * a1h, 85.0)
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
                            2.6,
                        )
                    )

        # 2. W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H
        if "W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H" in by_id:
            cid = "W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 12))
            for k in range(202, len(q15["end_ms"])):
                if k % 2 != 1:
                    continue
                end = int(q15["end_ms"][k])
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                close = q15["close"][k]
                a15 = atr15_14[k]
                a48_pre = atr15_48[k - 8]
                a192_pre = atr15_192[k - 8]
                m96 = close_sma96[k]
                a1h = atr1_20[h]
                if not (
                    np.isfinite(a15)
                    and a15 > 0
                    and np.isfinite(a48_pre)
                    and np.isfinite(a192_pre)
                    and a192_pre > 0
                    and np.isfinite(m96)
                    and _eligible_vol(close, a1h)
                ):
                    continue
                if 10_000.0 * a1h / close < 55.0:
                    continue
                if (a48_pre / a192_pre) > 0.90:
                    continue
                if abs(close - m96) > 0.85 * a15:
                    continue
                hi_8 = float(np.max(q15["high"][k - 8 : k]))
                lo_8 = float(np.min(q15["low"][k - 8 : k]))
                snap_30m = close - q15["close"][k - 2]
                if (m96 - lo_8) >= 1.50 * a15 and snap_30m >= 0.40 * a15:
                    stop = _clamp_stop_bps(close, 1, 1.50 * a1h, 80.0)
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
                            2.4,
                        )
                    )
                elif (hi_8 - m96) >= 1.50 * a15 and snap_30m <= -0.40 * a15:
                    stop = _clamp_stop_bps(close, -1, 1.50 * a1h, 80.0)
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
                            2.4,
                        )
                    )

        # 3. W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H
        if "W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H" in by_id:
            cid = "W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 24))
            for h in range(50, len(h1["end_ms"])):
                end = int(h1["end_ms"][h])
                j = _last_complete(f4["end_ms"], end)
                if j < 59:
                    continue
                if not (np.isfinite(er4_12[j]) and er4_12[j] <= 0.34):
                    continue
                close = h1["close"][h]
                opened = h1["open"][h]
                a1h = atr1_20[h]
                if not (_eligible_vol(close, a1h) and 10_000.0 * a1h / close >= 60.0):
                    continue
                hi_48h = float(np.max(h1["high"][h - 48 : h]))
                lo_48h = float(np.min(h1["low"][h - 48 : h]))
                width = hi_48h - lo_48h
                if width < 2.20 * a1h:
                    continue
                mid = 0.5 * (hi_48h + lo_48h)
                # LONG: tested bottom 18% of 48h range and closed bullish below midline with non-negative 1h taker flow
                if (
                    h1["low"][h] <= lo_48h + 0.18 * width
                    and lo_48h + 0.08 * width <= close <= mid
                    and close > opened
                    and sfr1[h] >= 0.0
                ):
                    stop = _clamp_stop_bps(close, 1, 1.60 * a1h, 85.0)
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
                            2.5,
                        )
                    )
                # SHORT: tested top 18% of 48h range and closed bearish above midline with non-positive 1h taker flow
                elif (
                    h1["high"][h] >= hi_48h - 0.18 * width
                    and mid <= close <= hi_48h - 0.08 * width
                    and close < opened
                    and sfr1[h] <= 0.0
                ):
                    stop = _clamp_stop_bps(close, -1, 1.60 * a1h, 85.0)
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
                            2.5,
                        )
                    )

        # 4. W3_C04_HOURLY_TAKER_EXHAUSTION_WICK_REVERSAL_12H
        if "W3_C04_HOURLY_TAKER_EXHAUSTION_WICK_REVERSAL_12H" in by_id:
            cid = "W3_C04_HOURLY_TAKER_EXHAUSTION_WICK_REVERSAL_12H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 12))
            for h in range(25, len(h1["end_ms"])):
                end = int(h1["end_ms"][h])
                j = _last_complete(f4["end_ms"], end)
                if j < 59:
                    continue
                close = h1["close"][h]
                opened = h1["open"][h]
                a1h = atr1_20[h]
                v1_sma = vol1_sma20[h - 1]
                if not (
                    _eligible_vol(close, a1h)
                    and 10_000.0 * a1h / close >= 60.0
                    and np.isfinite(v1_sma)
                    and v1_sma > 0
                ):
                    continue
                vol3h = float(np.sum(h1["volume"][h - 3 : h]))
                if vol3h < 3.20 * v1_sma:
                    continue
                disp3h = h1["close"][h - 1] - h1["open"][h - 3]
                if (
                    disp3h <= -1.40 * a1h
                    and (close - opened) >= 0.25 * a1h
                    and sfr1[h] >= 0.01
                ):
                    stop = _clamp_stop_bps(close, 1, 1.60 * a1h, 85.0)
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
                            2.4,
                        )
                    )
                elif (
                    disp3h >= 1.40 * a1h
                    and (opened - close) >= 0.25 * a1h
                    and sfr1[h] <= -0.01
                ):
                    stop = _clamp_stop_bps(close, -1, 1.60 * a1h, 85.0)
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
                            2.4,
                        )
                    )

        # 5. W3_C05_REGIONAL_SESSION_SWEEP_RECLAIM_12H
        if "W3_C05_REGIONAL_SESSION_SWEEP_RECLAIM_12H" in by_id:
            cid = "W3_C05_REGIONAL_SESSION_SWEEP_RECLAIM_12H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 12))
            emitted_sess: set[tuple[int, int]] = set()
            for k in range(40, len(q15["end_ms"])):
                if k % 2 != 1:
                    continue
                end = int(q15["end_ms"][k])
                # 8h session boundary index
                sess_block = end // (8 * HOUR_MS)
                sess_start = sess_block * (8 * HOUR_MS)
                offset_ms = end - sess_start
                if not (15 * MINUTE_MS <= offset_ms <= 2 * HOUR_MS):
                    continue
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                close = q15["close"][k]
                opened = q15["open"][k]
                a15 = atr15_14[k]
                a1h = atr1_20[h]
                if not (
                    np.isfinite(a15)
                    and a15 > 0
                    and _eligible_vol(close, a1h)
                    and 10_000.0 * a1h / close >= 55.0
                ):
                    continue
                # Prior 8h session bars: [sess_start - 8h + 15m .. sess_start]
                s_idx0 = int(
                    np.searchsorted(
                        q15["end_ms"], sess_start - 8 * HOUR_MS + 15 * MINUTE_MS, side="left"
                    )
                )
                s_idx1 = int(np.searchsorted(q15["end_ms"], sess_start, side="right"))
                if s_idx1 - s_idx0 != 32:
                    continue
                s_high = float(np.max(q15["high"][s_idx0:s_idx1]))
                s_low = float(np.min(q15["low"][s_idx0:s_idx1]))
                if (s_high - s_low) < 1.40 * a1h:
                    continue
                if (
                    (sess_block, 1) not in emitted_sess
                    and min(q15["low"][k - 1], q15["low"][k]) < s_low
                    and close >= s_low
                    and close > opened
                    and sfr15[k] >= 0.0
                ):
                    emitted_sess.add((sess_block, 1))
                    stop = _clamp_stop_bps(close, 1, 1.50 * a1h, 80.0)
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
                            2.5,
                        )
                    )
                elif (
                    (sess_block, -1) not in emitted_sess
                    and max(q15["high"][k - 1], q15["high"][k]) > s_high
                    and close <= s_high
                    and close < opened
                    and sfr15[k] <= 0.0
                ):
                    emitted_sess.add((sess_block, -1))
                    stop = _clamp_stop_bps(close, -1, 1.50 * a1h, 80.0)
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
                            2.5,
                        )
                    )

        # 6. W3_C06_FOUR_HOUR_CLIMAX_STALL_REVERSAL_24H
        if "W3_C06_FOUR_HOUR_CLIMAX_STALL_REVERSAL_24H" in by_id:
            cid = "W3_C06_FOUR_HOUR_CLIMAX_STALL_REVERSAL_24H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 24))
            for j in range(60, len(f4["end_ms"])):
                end = int(f4["end_ms"][j])
                h = _last_complete(h1["end_ms"], end)
                if h < 20 or int(h1["end_ms"][h]) != end:
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
                if float(np.max(er4_6[j - 3 : j])) < 0.40:
                    continue
                if (
                    (f4["close"][j - 4] - float(np.min(f4["low"][j - 3 : j]))) >= 1.35 * a4
                    and f4["low"][j] >= f4["low"][j - 1] - 0.40 * a4
                    and close4 > open4
                    and sfr1[h] >= -0.01
                ):
                    stop = _clamp_stop_bps(close4, 1, 1.70 * a1h, 85.0)
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
                            f"{cid}:1:{end}",
                            2.8,
                        )
                    )
                elif (
                    (float(np.max(f4["high"][j - 3 : j])) - f4["close"][j - 4]) >= 1.35 * a4
                    and f4["high"][j] <= f4["high"][j - 1] + 0.40 * a4
                    and close4 < open4
                    and sfr1[h] <= 0.01
                ):
                    stop = _clamp_stop_bps(close4, -1, 1.70 * a1h, 85.0)
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
                            f"{cid}:-1:{end}",
                            2.8,
                        )
                    )

    # --- WAVE 4 CANDIDATES ---
    if any(k.startswith("W4_") for k in by_id):
        atr15_14 = _atr_fast(q15, 14)
        atr15_48 = _atr_fast(q15, 48)
        atr15_192 = _atr_fast(q15, 192)
        close_sma96 = _sma_fast(q15["close"], 96)
        vol1_sma20 = _sma_fast(h1["volume"], 20)
        sfr4 = f4["signed_flow_ratio"]

        vol2 = _sma_fast(q15["volume"], 2) * 2.0
        sf2 = _sma_fast(q15["signed_flow"], 2) * 2.0
        taker_imb_2 = np.divide(sf2, vol2, out=np.zeros_like(sf2), where=vol2 > 0)

        vol4_15 = _sma_fast(q15["volume"], 4) * 4.0
        sf4_15 = _sma_fast(q15["signed_flow"], 4) * 4.0
        taker_imb_4 = np.divide(sf4_15, vol4_15, out=np.zeros_like(sf4_15), where=vol4_15 > 0)

        def _clamp_stop_w4(close_px: float, side_val: int, raw_dist: float, min_bps: float = 45.0) -> float:
            dist = min(max(raw_dist, (min_bps / 10_000.0) * close_px), 0.0240 * close_px)
            return close_px - side_val * dist

        # 1. W4_C01_WIDE_72H_RECLAIM_DYNAMIC_MIDLINE_12H
        if "W4_C01_WIDE_72H_RECLAIM_DYNAMIC_MIDLINE_12H" in by_id:
            cid = "W4_C01_WIDE_72H_RECLAIM_DYNAMIC_MIDLINE_12H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 12))
            for k in range(292, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                if end % HOUR_MS != 0:
                    continue
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                close = q15["close"][k]
                a15 = atr15_14[k]
                a1h = atr1_20[h]
                if not (
                    np.isfinite(a15)
                    and a15 > 0
                    and _eligible_vol(close, a1h)
                    and 10_000.0 * a1h / close >= 55.0
                ):
                    continue
                hi_72h = float(np.max(q15["high"][k - 291 : k - 3]))
                lo_72h = float(np.min(q15["low"][k - 291 : k - 3]))
                width_bps = (hi_72h - lo_72h) / lo_72h * 10_000.0
                if not (240.0 <= width_bps <= 1300.0):
                    continue
                sweep_lo = float(np.min(q15["low"][k - 3 : k + 1]))
                sweep_hi = float(np.max(q15["high"][k - 3 : k + 1]))
                ret_1h = close - q15["open"][k - 3]
                if (
                    sweep_lo < lo_72h
                    and close >= lo_72h + 0.30 * a15
                    and ret_1h > 0
                    and taker_imb_4[k] >= 0.0
                ):
                    stop = _clamp_stop_w4(close, 1, 3.0 * a15, 45.0)
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
                            1.85,
                        )
                    )
                elif (
                    sweep_hi > hi_72h
                    and close <= hi_72h - 0.30 * a15
                    and ret_1h < 0
                    and taker_imb_4[k] <= 0.0
                ):
                    stop = _clamp_stop_w4(close, -1, 3.0 * a15, 45.0)
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
                            1.85,
                        )
                    )

        # 2. W4_C02_SQUEEZE_SNAPBACK_LOW_DRIFT_08H
        if "W4_C02_SQUEEZE_SNAPBACK_LOW_DRIFT_08H" in by_id:
            cid = "W4_C02_SQUEEZE_SNAPBACK_LOW_DRIFT_08H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 8))
            for k in range(202, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                if not (np.isfinite(er4_12[j]) and er4_12[j] <= 0.38):
                    continue
                close = q15["close"][k]
                a15 = atr15_14[k]
                a48_pre = atr15_48[k - 8]
                a192_pre = atr15_192[k - 8]
                m96 = close_sma96[k]
                a1h = atr1_20[h]
                if not (
                    np.isfinite(a15)
                    and a15 > 0
                    and np.isfinite(a48_pre)
                    and np.isfinite(a192_pre)
                    and a192_pre > 0
                    and np.isfinite(m96)
                    and _eligible_vol(close, a1h)
                ):
                    continue
                drift_48h_bps = abs(close - q15["close"][k - 192]) / q15["close"][k - 192] * 10_000.0
                if drift_48h_bps > 450.0:
                    continue
                if (a48_pre / a192_pre) > 0.86:
                    continue
                if abs(close - m96) > 0.75 * a15:
                    continue
                hi_8 = float(np.max(q15["high"][k - 8 : k]))
                lo_8 = float(np.min(q15["low"][k - 8 : k]))
                snap_30m = close - q15["close"][k - 2]
                if (
                    (m96 - lo_8) >= 1.65 * a15
                    and snap_30m >= 0.45 * a15
                    and sfr15[k] >= 0.02
                ):
                    stop = _clamp_stop_w4(close, 1, 2.6 * a15, 45.0)
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
                            1.75,
                        )
                    )
                elif (
                    (hi_8 - m96) >= 1.65 * a15
                    and snap_30m <= -0.45 * a15
                    and sfr15[k] <= -0.02
                ):
                    stop = _clamp_stop_w4(close, -1, 2.6 * a15, 45.0)
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
                            1.75,
                        )
                    )

        # 3. W4_C03_BOUNDED_48H_RANGE_REJECTION_12H
        if "W4_C03_BOUNDED_48H_RANGE_REJECTION_12H" in by_id:
            cid = "W4_C03_BOUNDED_48H_RANGE_REJECTION_12H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 12))
            for h in range(50, len(h1["end_ms"])):
                end = int(h1["end_ms"][h])
                j = _last_complete(f4["end_ms"], end)
                if j < 59:
                    continue
                if not (np.isfinite(er4_12[j]) and er4_12[j] <= 0.32):
                    continue
                close = h1["close"][h]
                opened = h1["open"][h]
                a1h = atr1_20[h]
                v1_sma = vol1_sma20[h - 1]
                if not (
                    _eligible_vol(close, a1h)
                    and 10_000.0 * a1h / close >= 50.0
                    and np.isfinite(v1_sma)
                    and v1_sma > 0
                    and h1["volume"][h] >= 0.95 * v1_sma
                ):
                    continue
                hi_48h = float(np.max(h1["high"][h - 48 : h]))
                lo_48h = float(np.min(h1["low"][h - 48 : h]))
                width = hi_48h - lo_48h
                if width < 2.40 * a1h:
                    continue
                mid = 0.5 * (hi_48h + lo_48h)
                if (
                    h1["low"][h] <= lo_48h + 0.16 * width
                    and lo_48h + 0.06 * width <= close <= mid
                    and close > opened
                    and sfr1[h] >= 0.03
                ):
                    stop = _clamp_stop_w4(close, 1, 1.35 * a1h, 50.0)
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
                            1.80,
                        )
                    )
                elif (
                    h1["high"][h] >= hi_48h - 0.16 * width
                    and mid <= close <= hi_48h - 0.06 * width
                    and close < opened
                    and sfr1[h] <= -0.03
                ):
                    stop = _clamp_stop_w4(close, -1, 1.35 * a1h, 50.0)
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
                            1.80,
                        )
                    )

        # 4. W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H
        if "W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H" in by_id:
            cid = "W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 8))
            for k in range(100, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                if not (np.isfinite(er4_12[j]) and er4_12[j] <= 0.36):
                    continue
                close = q15["close"][k]
                opened = q15["open"][k]
                a15 = atr15_14[k]
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
                if not (0.55 * 4.0 * v_sma <= vol4_15[k] <= 1.35 * 4.0 * v_sma):
                    continue
                hi_24h = float(np.max(q15["high"][k - 99 : k - 3]))
                lo_24h = float(np.min(q15["low"][k - 99 : k - 3]))
                probe_lo = float(np.min(q15["low"][k - 3 : k + 1]))
                probe_hi = float(np.max(q15["high"][k - 3 : k + 1]))
                if (
                    probe_lo <= lo_24h
                    and (close - opened) >= 0.35 * a15
                    and taker_imb_2[k] >= 0.05
                ):
                    stop = _clamp_stop_w4(close, 1, 2.6 * a15, 45.0)
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
                            1.80,
                        )
                    )
                elif (
                    probe_hi >= hi_24h
                    and (opened - close) >= 0.35 * a15
                    and taker_imb_2[k] <= -0.05
                ):
                    stop = _clamp_stop_w4(close, -1, 2.6 * a15, 45.0)
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
                            1.80,
                        )
                    )

        # 5. W4_C05_ASIA_RANGE_EUROPE_SWEEP_RETURN_12H
        if "W4_C05_ASIA_RANGE_EUROPE_SWEEP_RETURN_12H" in by_id:
            cid = "W4_C05_ASIA_RANGE_EUROPE_SWEEP_RETURN_12H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 12))
            emitted_day_side: set[tuple[int, int]] = set()
            for k in range(36, len(q15["end_ms"])):
                end = int(q15["end_ms"][k])
                day_start = (end // DAY_MS) * DAY_MS
                tod_ms = end - day_start
                if not (8 * HOUR_MS + 15 * MINUTE_MS <= tod_ms <= 14 * HOUR_MS):
                    continue
                h = _last_complete(h1["end_ms"], end)
                j = _last_complete(f4["end_ms"], end)
                if j < 59 or h < 20:
                    continue
                if not (np.isfinite(er4_12[j]) and er4_12[j] <= 0.42):
                    continue
                close = q15["close"][k]
                opened = q15["open"][k]
                a15 = atr15_20[k]
                a1h = atr1_20[h]
                if not (np.isfinite(a15) and a15 > 0 and _eligible_vol(close, a1h)):
                    continue
                s_idx_start = int(
                    np.searchsorted(q15["end_ms"], day_start + 15 * MINUTE_MS, side="left")
                )
                s_idx_end = int(
                    np.searchsorted(q15["end_ms"], day_start + 8 * HOUR_MS, side="right")
                )
                if s_idx_end - s_idx_start != 32:
                    continue
                s_high = float(np.max(q15["high"][s_idx_start:s_idx_end]))
                s_low = float(np.min(q15["low"][s_idx_start:s_idx_end]))
                day_id = day_start // DAY_MS
                if (
                    (day_id, 1) not in emitted_day_side
                    and min(q15["low"][k - 1], q15["low"][k]) <= s_low - 0.15 * a1h
                    and q15["low"][k] >= s_low - 2.20 * a1h
                    and close >= s_low + 0.05 * a1h
                    and (close - opened) >= 0.20 * a15
                    and sfr15[k] >= 0.02
                ):
                    emitted_day_side.add((day_id, 1))
                    stop = _clamp_stop_w4(close, 1, 1.45 * a1h, 45.0)
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
                            1.85,
                        )
                    )
                elif (
                    (day_id, -1) not in emitted_day_side
                    and max(q15["high"][k - 1], q15["high"][k]) >= s_high + 0.15 * a1h
                    and q15["high"][k] <= s_high + 2.20 * a1h
                    and close <= s_high - 0.05 * a1h
                    and (opened - close) >= 0.20 * a15
                    and sfr15[k] <= -0.02
                ):
                    emitted_day_side.add((day_id, -1))
                    stop = _clamp_stop_w4(close, -1, 1.45 * a1h, 45.0)
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
                            1.85,
                        )
                    )

        # 6. W4_C06_FOUR_HOUR_EXHAUSTION_MODERATE_VOL_24H
        if "W4_C06_FOUR_HOUR_EXHAUSTION_MODERATE_VOL_24H" in by_id:
            cid = "W4_C06_FOUR_HOUR_EXHAUSTION_MODERATE_VOL_24H"
            row = by_id[cid]
            horizon = int(row.get("holding_horizon_hours", 24))
            for j in range(60, len(f4["end_ms"])):
                end = int(f4["end_ms"][j])
                h = _last_complete(h1["end_ms"], end)
                if h < 20 or int(h1["end_ms"][h]) != end:
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
                    and 10_000.0 * a1h / close4 <= 115.0
                ):
                    continue
                if float(np.max(er4_6[j - 3 : j])) < 0.42:
                    continue
                if not (er4_6[j] <= er4_6[j - 1] or er4_6[j] <= 0.44):
                    continue
                if (
                    (f4["close"][j - 4] - float(np.min(f4["low"][j - 3 : j]))) >= 1.10 * a4
                    and f4["low"][j] >= f4["low"][j - 1] - 0.32 * a4
                    and (close4 - open4) >= 0.15 * a4
                    and sfr4[j] >= -0.01
                ):
                    stop = _clamp_stop_w4(close4, 1, 1.65 * a1h, 50.0)
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
                            f"{cid}:1:{end}",
                            1.85,
                        )
                    )
                elif (
                    (float(np.max(f4["high"][j - 3 : j])) - f4["close"][j - 4]) >= 1.10 * a4
                    and f4["high"][j] <= f4["high"][j - 1] + 0.32 * a4
                    and (open4 - close4) >= 0.15 * a4
                    and sfr4[j] <= 0.01
                ):
                    stop = _clamp_stop_w4(close4, -1, 1.65 * a1h, 50.0)
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
                            f"{cid}:-1:{end}",
                            1.85,
                        )
                    )

    return output
