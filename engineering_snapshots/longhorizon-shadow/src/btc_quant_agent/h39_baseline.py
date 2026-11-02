"""Strategy-neutral, causal baseline state producer for H39."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .indicators import atr

H39_ATR_PERIOD = 14
H39_ATR_HISTORY_15M_BARS = 500
_MINUTE_MS = 60_000
_BAR_MS = 15 * _MINUTE_MS


def causal_wilder_atr_15m(
    canonical_1m: Mapping[int, Mapping[str, Any]],
    decision_close_ms: int,
    *,
    history_bars: int = H39_ATR_HISTORY_15M_BARS,
    period: int = H39_ATR_PERIOD,
) -> float | None:
    """Return ATR14 from completed 15m bars strictly before a decision boundary.

    The 500-bar history and Wilder seed match the normal runtime feature path.
    Any missing 1m child fails closed; incomplete bars are never synthesized.
    """
    if decision_close_ms % _BAR_MS != 0 or history_bars < period:
        return None
    first_bar = decision_close_ms - history_bars * _BAR_MS
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    for bar_open in range(first_bar, decision_close_ms, _BAR_MS):
        children = [canonical_1m.get(bar_open + i * _MINUTE_MS) for i in range(15)]
        if any(child is None for child in children):
            return None
        complete = [child for child in children if child is not None]
        try:
            highs.append(max(float(child["high"]) for child in complete))
            lows.append(min(float(child["low"]) for child in complete))
            closes.append(float(complete[-1]["close"]))
        except (KeyError, TypeError, ValueError):
            return None
    value = float(atr(highs, lows, closes, period)[-1])
    return value if value > 0.0 else None
