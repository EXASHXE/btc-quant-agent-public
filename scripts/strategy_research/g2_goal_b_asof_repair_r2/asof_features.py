"""Strict time-causal as-of-ENTRY feature extractors for Gemini Goal B R2.

Enforces zero lookahead:
1. PRE_ENTRY_TREND_ALIGNED: Strictly prior 240 1m LAST bars ending <= signal decision clock.
2. PRE_ENTRY_ATR_REGIME: Strictly prior-only 90d (2,160h) completed 1h Wilder ATR14 / Close median.
3. PRE_ENTRY_FUNDING_STATE: Latest official funding rate settled strictly before signal decision.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

MIN_EVENTS_PER_STRATUM = 10

# Column indices for 1m LAST bars:
# 0: open_time (ms), 1: open, 2: high, 3: low, 4: close, 5: volume, 6: close_time (ms)
COL_OPEN_TIME = 0
COL_OPEN = 1
COL_HIGH = 2
COL_LOW = 3
COL_CLOSE = 4
COL_VOLUME = 5
COL_CLOSE_TIME = 6

TREND_BARS_REQUIRED = 240
ATR_LOOKBACK_HOURS_REQUIRED = 2160
ATR_PERIOD = 14
HOUR_MS = 3600 * 1000


def extract_pre_entry_trend_aligned(
    bars_1m: np.ndarray,
    signal_decision_at_ms: int,
    side: int,
    entry_at_ms: int | None = None,
) -> dict[str, Any]:
    """Compute PRE_ENTRY_TREND_ALIGNED from strictly completed 240 1m bars.

    Endpoint close time must be <= min(signal_decision_at_ms, entry_at_ms - 1ms).
    Bars must be strictly contiguous (60,000 ms step between successive bar opens).
    """
    if entry_at_ms is not None:
        cutoff_ms = min(signal_decision_at_ms, entry_at_ms - 1)
    else:
        cutoff_ms = signal_decision_at_ms

    if len(bars_1m) == 0:
        return {
            "trend_regime": "INCOMPLETE",
            "alignment_val": 0.0,
            "return_4h": 0.0,
            "bar_count": 0,
            "valid": False,
            "reason": "EMPTY_BAR_ARRAY",
        }

    # Filter completed bars whose close_time <= cutoff_ms
    mask = bars_1m[:, COL_CLOSE_TIME] <= cutoff_ms
    completed = bars_1m[mask]

    if len(completed) < TREND_BARS_REQUIRED:
        return {
            "trend_regime": "INCOMPLETE",
            "alignment_val": 0.0,
            "return_4h": 0.0,
            "bar_count": len(completed),
            "valid": False,
            "reason": f"INSUFFICIENT_BARS_{len(completed)}_LT_{TREND_BARS_REQUIRED}",
        }

    # Take exactly the last 240 completed bars
    window_240 = completed[-TREND_BARS_REQUIRED:]

    # Verify continuity: open_time must increment by exactly 60,000 ms
    open_times = window_240[:, COL_OPEN_TIME]
    diffs = np.diff(open_times)
    if not np.all(diffs == 60_000):
        max_diff = int(np.max(diffs)) if len(diffs) > 0 else 0
        min_diff = int(np.min(diffs)) if len(diffs) > 0 else 0
        return {
            "trend_regime": "INCOMPLETE",
            "alignment_val": 0.0,
            "return_4h": 0.0,
            "bar_count": TREND_BARS_REQUIRED,
            "valid": False,
            "reason": f"NON_CONTIGUOUS_BARS_MIN_{min_diff}_MAX_{max_diff}",
        }

    p_start = float(window_240[0, COL_OPEN])
    p_end = float(window_240[-1, COL_CLOSE])

    if p_start <= 0:
        return {
            "trend_regime": "INCOMPLETE",
            "alignment_val": 0.0,
            "return_4h": 0.0,
            "bar_count": TREND_BARS_REQUIRED,
            "valid": False,
            "reason": "NON_POSITIVE_START_PRICE",
        }

    ret_4h = (p_end - p_start) / p_start
    alignment = float(side) * ret_4h

    # Regime categorization with zero-threshold deadband of 1e-7
    if alignment > 1e-7:
        regime = "TREND_ALIGNED"
    elif alignment < -1e-7:
        regime = "COUNTERTREND"
    else:
        regime = "NEUTRAL"

    return {
        "trend_regime": regime,
        "alignment_val": alignment,
        "return_4h": ret_4h,
        "p_start": p_start,
        "p_end": p_end,
        "start_open_ms": int(window_240[0, COL_OPEN_TIME]),
        "end_close_ms": int(window_240[-1, COL_CLOSE_TIME]),
        "cutoff_ms": cutoff_ms,
        "bar_count": TREND_BARS_REQUIRED,
        "valid": True,
        "reason": "OK",
    }


def resample_1m_to_1h(bars_1m: np.ndarray) -> np.ndarray:
    """Resample contiguous 1m bars into full 1h OHLC bars.

    Only emits hours that have all 60 minutes present.
    Output columns: [open_time, open, high, low, close, close_time].
    """
    if len(bars_1m) == 0:
        return np.empty((0, 6), dtype=float)

    # Hour bucket = floor(open_time / 3600_000) * 3600_000
    open_times = bars_1m[:, COL_OPEN_TIME].astype(np.int64)
    hour_starts = (open_times // HOUR_MS) * HOUR_MS

    # Unique hour starts in sorted order
    unique_hours, split_indices, counts = np.unique(
        hour_starts, return_index=True, return_counts=True
    )

    valid_hours = []
    for h_start, s_idx, cnt in zip(unique_hours, split_indices, counts, strict=True):
        if cnt == 60:
            h_slice = bars_1m[s_idx : s_idx + 60]
            # Verify contiguous 1m in this hour
            if np.all(np.diff(h_slice[:, COL_OPEN_TIME]) == 60_000):
                o = float(h_slice[0, COL_OPEN])
                h = float(np.max(h_slice[:, COL_HIGH]))
                l = float(np.min(h_slice[:, COL_LOW]))
                c = float(h_slice[-1, COL_CLOSE])
                c_time = float(h_slice[-1, COL_CLOSE_TIME])
                valid_hours.append([float(h_start), o, h, l, c, c_time])

    if not valid_hours:
        return np.empty((0, 6), dtype=float)

    return np.array(valid_hours, dtype=float)


def compute_wilder_atr14(hourly_bars: np.ndarray) -> np.ndarray:
    """Compute Wilder ATR(14) on 1-hour OHLC bars.

    TR_0 = High_0 - Low_0
    TR_t = max(High_t - Low_t, |High_t - Close_{t-1}|, |Low_t - Close_{t-1}|)
    Initial ATR at index 13: mean(TR[0..13]) (14 bars).
    Subsequent: ATR_t = (ATR_{t-1} * 13 + TR_t) / 14.
    """
    n = len(hourly_bars)
    if n < ATR_PERIOD:
        return np.full(n, np.nan, dtype=float)

    highs = hourly_bars[:, 2]
    lows = hourly_bars[:, 3]
    closes = hourly_bars[:, 4]

    tr = np.empty(n, dtype=float)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    atr = np.full(n, np.nan, dtype=float)
    atr[ATR_PERIOD - 1] = float(np.mean(tr[:ATR_PERIOD]))
    for i in range(ATR_PERIOD, n):
        atr[i] = (atr[i - 1] * 13.0 + tr[i]) / 14.0

    return atr


def extract_pre_entry_atr_regime(
    hourly_bars: np.ndarray,
    signal_decision_at_ms: int,
    lookback_hours: int = ATR_LOOKBACK_HOURS_REQUIRED,
    entry_at_ms: int | None = None,
) -> dict[str, Any]:
    """Compute PRE_ENTRY_ATR_REGIME from expanding strictly prior 90d hourly bars.

    Only completed hours with close_time <= cutoff_ms are considered.
    If fewer than lookback_hours (2,160) completed hours exist,
    returns INCOMPLETE_LOOKBACK. Never auto-substitutes low volatility.
    """
    if entry_at_ms is not None:
        cutoff_ms = min(signal_decision_at_ms, entry_at_ms - 1)
    else:
        cutoff_ms = signal_decision_at_ms

    if len(hourly_bars) == 0:
        return {
            "volatility_regime": "INCOMPLETE_LOOKBACK",
            "current_norm_atr": 0.0,
            "median_norm_atr": 0.0,
            "lookback_bars": 0,
            "valid": False,
            "reason": "EMPTY_HOURLY_ARRAY",
        }

    # Filter completed hours whose close_time <= cutoff_ms
    mask = hourly_bars[:, 5] <= cutoff_ms
    completed_indices = np.where(mask)[0]

    if len(completed_indices) < lookback_hours:
        return {
            "volatility_regime": "INCOMPLETE_LOOKBACK",
            "current_norm_atr": 0.0,
            "median_norm_atr": 0.0,
            "lookback_bars": len(completed_indices),
            "valid": False,
            "reason": f"INSUFFICIENT_HOURS_{len(completed_indices)}_LT_{lookback_hours}",
        }

    # Compute Wilder ATR across the full array up to latest completed
    atr_all = compute_wilder_atr14(hourly_bars)
    closes = hourly_bars[:, 4]
    norm_atr = atr_all / closes

    latest_idx = completed_indices[-1]

    # Prior window of exactly `lookback_hours` bars ending at latest_idx
    window_norm_atr = norm_atr[latest_idx - lookback_hours + 1 : latest_idx + 1]

    # Check for NaNs
    valid_atr = window_norm_atr[~np.isnan(window_norm_atr)]
    if len(valid_atr) < lookback_hours - ATR_PERIOD:
        return {
            "volatility_regime": "INCOMPLETE_LOOKBACK",
            "current_norm_atr": 0.0,
            "median_norm_atr": 0.0,
            "lookback_bars": len(valid_atr),
            "valid": False,
            "reason": "TOO_MANY_NANS_IN_ATR_WINDOW",
        }

    median_norm_atr = float(np.median(valid_atr))
    current_norm_atr = float(norm_atr[latest_idx])

    if current_norm_atr >= median_norm_atr:
        regime = "HIGH_VOL"
    else:
        regime = "LOW_VOL"

    return {
        "volatility_regime": regime,
        "current_norm_atr": current_norm_atr,
        "median_norm_atr": median_norm_atr,
        "ratio": current_norm_atr / median_norm_atr if median_norm_atr > 0 else 1.0,
        "lookback_bars": lookback_hours,
        "latest_hour_open_ms": int(hourly_bars[latest_idx, 0]),
        "latest_hour_close_ms": int(hourly_bars[latest_idx, 5]),
        "cutoff_ms": cutoff_ms,
        "valid": True,
        "reason": "OK",
    }


def extract_pre_entry_funding_state(
    funding_settlements: list[dict[str, Any]],
    signal_decision_at_ms: int,
    lag_ms: int = 0,
    entry_at_ms: int | None = None,
) -> dict[str, Any]:
    """Compute PRE_ENTRY_FUNDING_STATE strictly from settlements before signal clock.

    calc_time must be strictly < (cutoff_ms - lag_ms).
    """
    if entry_at_ms is not None:
        cutoff_ms = min(signal_decision_at_ms, entry_at_ms - 1)
    else:
        cutoff_ms = signal_decision_at_ms

    effective_cutoff = cutoff_ms - lag_ms

    # Filter settlements strictly before effective cutoff
    prior = [s for s in funding_settlements if int(s["calc_time"]) < effective_cutoff]

    if not prior:
        return {
            "funding_regime": "UNKNOWN",
            "rate": 0.0,
            "calc_time": 0,
            "lag_ms": lag_ms,
            "valid": False,
            "reason": "NO_PRIOR_SETTLEMENT",
        }

    latest = max(prior, key=lambda s: int(s["calc_time"]))
    rate = float(latest["last_funding_rate"])

    if rate > 1e-7:
        regime = "POSITIVE"
    elif rate < -1e-7:
        regime = "NEGATIVE"
    else:
        regime = "ZERO"

    return {
        "funding_regime": regime,
        "rate": rate,
        "calc_time": int(latest["calc_time"]),
        "cutoff_ms": cutoff_ms,
        "lag_ms": lag_ms,
        "valid": True,
        "reason": "OK",
    }


def load_monthly_1m_bars(cache_dir: Path, year_month: str) -> np.ndarray:
    """Load public 1m LAST bars from monthly zip archive."""
    zip_path = cache_dir / f"last-BTCUSDT-1m-{year_month}.zip"
    if not zip_path.is_file():
        raise FileNotFoundError(f"Missing public archive: {zip_path}")

    rows: list[list[float]] = []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            with z.open(name) as f:
                reader = csv.reader(io.TextIOWrapper(f))
                for row in reader:
                    if not row or row[0].startswith("#") or not row[0].isdigit():
                        continue
                    rows.append(
                        [
                            float(row[0]),  # open_time
                            float(row[1]),  # open
                            float(row[2]),  # high
                            float(row[3]),  # low
                            float(row[4]),  # close
                            float(row[5]),  # volume
                            float(row[6]),  # close_time
                        ]
                    )
    return np.array(rows, dtype=float)


def load_monthly_funding_settlements(cache_dir: Path, year_month: str) -> list[dict[str, Any]]:
    """Load public official funding settlements from monthly zip archive."""
    zip_path = cache_dir / f"funding-BTCUSDT-fundingRate-{year_month}.zip"
    if not zip_path.is_file():
        raise FileNotFoundError(f"Missing public funding archive: {zip_path}")

    settlements: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            with z.open(name) as f:
                reader = csv.reader(io.TextIOWrapper(f))
                _ = next(reader, None)
                for row in reader:
                    if len(row) < 3 or not row[0].isdigit():
                        continue
                    settlements.append(
                        {
                            "calc_time": int(row[0]),
                            "funding_interval_hours": int(row[1]),
                            "last_funding_rate": float(row[2]),
                        }
                    )
    return settlements


def extract_year(entry_at_ms: int) -> str:
    """Extract calendar year string from timestamp in ms."""
    dt = datetime.fromtimestamp(entry_at_ms / 1000, UTC)
    return str(dt.year)


def extract_side(side: int) -> str:
    """Extract human-readable side string from side integer."""
    if side == 1:
        return "LONG"
    if side == -1:
        return "SHORT"
    raise ValueError(f"Invalid side integer: {side}")


def calculate_effective_utc_weeks(timestamps_ms: list[int]) -> int:
    """Calculate number of distinct UTC calendar weeks spanned by events."""
    if not timestamps_ms:
        return 0
    weeks = {datetime.fromtimestamp(ts / 1000, UTC).isocalendar()[:2] for ts in timestamps_ms}
    return len(weeks)


def stratify_cohorts(
    events: list[dict[str, Any]],
    regime_key: str,
    min_events: int = MIN_EVENTS_PER_STRATUM,
) -> dict[str, dict[str, Any]]:
    """Group events by a single predeclared regime dimension and check sample power.

    events: list of dicts with 'labels' dict containing regime_key, and 'delta_net_bps'.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        label = ev.get("labels", {}).get(regime_key, "UNKNOWN")
        groups.setdefault(label, []).append(ev)

    out: dict[str, dict[str, Any]] = {}
    for label, cohort in sorted(groups.items()):
        n = len(cohort)
        is_underpowered = n < min_events
        timestamps = [ev["entry_at"] for ev in cohort if "entry_at" in ev]
        effective_weeks = calculate_effective_utc_weeks(timestamps)

        deltas_net = [ev["delta_net_bps"] for ev in cohort if "delta_net_bps" in ev]
        mean_delta = float(np.mean(deltas_net)) if deltas_net else 0.0
        median_delta = float(np.median(deltas_net)) if deltas_net else 0.0
        std_delta = float(np.std(deltas_net, ddof=1)) if len(deltas_net) > 1 else 0.0

        out[label] = {
            "regime": regime_key,
            "label": label,
            "event_count": n,
            "underpowered": is_underpowered,
            "power_status": "UNDERPOWERED" if is_underpowered else "SUFFICIENT_SUPPORT",
            "effective_utc_weeks": effective_weeks,
            "mean_delta_net_bps": mean_delta,
            "median_delta_net_bps": median_delta,
            "std_delta_net_bps": std_delta,
            "favorable_count": sum(d > 0 for d in deltas_net),
            "adverse_count": sum(d < 0 for d in deltas_net),
            "flat_count": sum(d == 0 for d in deltas_net),
        }

    return out
