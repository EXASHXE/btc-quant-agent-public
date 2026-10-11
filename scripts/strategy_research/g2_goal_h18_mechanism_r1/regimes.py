"""Predeclared as-of state labels, feature extractors, and power gates."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np

MIN_EVENTS_PER_STRATUM = 10
HOUR_MS = 3600 * 1000
DAY_MS = 24 * HOUR_MS


def extract_year(entry_at_ms: int) -> str:
    """Extract calendar year from entry timestamp."""
    dt = datetime.fromtimestamp(entry_at_ms / 1000, UTC)
    return str(dt.year)


def extract_side(side: int) -> str:
    """Extract side label from side integer."""
    if side == 1:
        return "LONG"
    if side == -1:
        return "SHORT"
    raise ValueError(f"Invalid side: {side}")


def extract_trend_alignment(
    last_bars: np.ndarray,
    entry_at_ms: int,
    side: int,
) -> str:
    """Compute trend alignment from completed 4h return strictly preceding entry.

    last_bars: numpy array of 1m bars with columns [timestamp, open, high, low, close, ...]
    entry_at_ms: entry timestamp in ms
    side: 1 for LONG, -1 for SHORT
    """
    start_ms = entry_at_ms - 4 * HOUR_MS
    # Select bars strictly before entry_at_ms and >= start_ms
    mask = (last_bars[:, 0] >= start_ms) & (last_bars[:, 0] < entry_at_ms)
    bars = last_bars[mask]
    if len(bars) < 240:
        # Not enough completed bars (e.g., at edge or missing)
        return "NEUTRAL"

    p_start = float(bars[0, 1])  # open of first 1m bar in 4h window
    p_end = float(bars[-1, 4])  # close of last completed 1m bar before entry
    if p_start <= 0:
        return "NEUTRAL"

    ret_4h = (p_end - p_start) / p_start
    alignment = side * ret_4h
    if alignment > 1e-7:
        return "TREND_ALIGNED"
    elif alignment < -1e-7:
        return "COUNTERTREND"
    else:
        return "NEUTRAL"


def compute_1h_atr14(hourly_bars: np.ndarray) -> np.ndarray:
    """Compute ATR(14) on 1-hour OHLC bars using true range."""
    n = len(hourly_bars)
    if n < 15:
        return np.full(n, np.nan)

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
    atr[14] = np.mean(tr[1:15])
    for i in range(15, n):
        atr[i] = (atr[i - 1] * 13.0 + tr[i]) / 14.0

    return atr


def extract_volatility_regime(
    hourly_bars: np.ndarray,
    entry_at_ms: int,
    lookback_days: int = 90,
) -> str:
    """Compute expanding previous-only 90d volatility level.

    hourly_bars: numpy array with columns [timestamp, open, high, low, close, ...]
    entry_at_ms: entry timestamp in ms
    lookback_days: strictly prior lookback window (default 90 days)
    """
    start_lookback = entry_at_ms - lookback_days * DAY_MS
    # Completed bars strictly before entry
    prior_mask = (hourly_bars[:, 0] >= start_lookback) & (hourly_bars[:, 0] < entry_at_ms)
    bars_window = hourly_bars[prior_mask]

    # Check if window has at least 90% of expected 90d hourly bars (90 * 24 = 2160 bars)
    min_required_bars = int(lookback_days * 24 * 0.90)
    if len(bars_window) < min_required_bars:
        return "INCOMPLETE_LOOKBACK"

    atr = compute_1h_atr14(bars_window)
    valid_mask = ~np.isnan(atr) & (bars_window[:, 4] > 0)
    if np.sum(valid_mask) < 100:
        return "INCOMPLETE_LOOKBACK"

    norm_atr = atr[valid_mask] / bars_window[valid_mask, 4]
    expanding_median = float(np.median(norm_atr))

    # Current completed ATR is the latest valid point
    current_norm_atr = float(norm_atr[-1])
    if current_norm_atr >= expanding_median:
        return "HIGH_VOL"
    else:
        return "LOW_VOL"


def extract_funding_regime(
    funding_rates: list[dict[str, Any]],
    signal_at_ms: int,
) -> str:
    """Extract funding state strictly observed before signal time.

    Never use a rate settled at or after signal_at_ms.
    """
    prior_rates = [
        r for r in funding_rates
        if int(r["settlement_at"]) < signal_at_ms
    ]
    if not prior_rates:
        return "UNKNOWN"

    latest_rate = max(prior_rates, key=lambda r: int(r["settlement_at"]))
    rate_val = float(latest_rate["rate"])

    if rate_val > 1e-7:
        return "POSITIVE"
    elif rate_val < -1e-7:
        return "NEGATIVE"
    else:
        return "ZERO"


def calculate_effective_utc_weeks(timestamps_ms: list[int]) -> int:
    """Calculate number of distinct UTC calendar weeks spanned by events."""
    if not timestamps_ms:
        return 0
    weeks = {
        datetime.fromtimestamp(ts / 1000, UTC).isocalendar()[:2]
        for ts in timestamps_ms
    }
    return len(weeks)


def stratify_cohorts(
    events: list[dict[str, Any]],
    regime_key: str,
    min_events: int = MIN_EVENTS_PER_STRATUM,
) -> dict[str, dict[str, Any]]:
    """Group events by a single predeclared regime dimension and check sample power.

    events: list of dicts, each having 'labels' dict with regime_key and 'delta_net_bps'
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
