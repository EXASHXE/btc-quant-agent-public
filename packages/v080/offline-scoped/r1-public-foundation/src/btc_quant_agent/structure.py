from __future__ import annotations

from collections.abc import Sequence

from .domain import Candle, Pivot


def confirmed_pivots(candles: Sequence[Candle], left: int = 2, right: int = 2) -> list[Pivot]:
    """Return pivots only at the bar where their right-side confirmation becomes available."""
    if left < 1 or right < 1:
        raise ValueError("pivot left/right must be positive")
    pivots: list[Pivot] = []
    for confirmed_index in range(left + right, len(candles)):
        pivot_index = confirmed_index - right
        window = candles[pivot_index - left : pivot_index + right + 1]
        pivot = candles[pivot_index]
        other_highs = [bar.high for i, bar in enumerate(window) if i != left]
        other_lows = [bar.low for i, bar in enumerate(window) if i != left]
        if pivot.high > max(other_highs):
            pivots.append(
                Pivot("HIGH", pivot_index, confirmed_index, pivot.high, pivot.open_time_ms)
            )
        if pivot.low < min(other_lows):
            pivots.append(Pivot("LOW", pivot_index, confirmed_index, pivot.low, pivot.open_time_ms))
    return pivots


def visible_pivots(
    candles: Sequence[Candle], decision_index: int, left: int = 2, right: int = 2
) -> list[Pivot]:
    if decision_index < 0:
        return []
    return [
        pivot
        for pivot in confirmed_pivots(candles[: decision_index + 1], left, right)
        if pivot.confirmed_index <= decision_index
    ]


def structure_label(pivots: Sequence[Pivot]) -> str:
    highs = [pivot.price for pivot in pivots if pivot.kind == "HIGH"]
    lows = [pivot.price for pivot in pivots if pivot.kind == "LOW"]
    if len(highs) < 2 or len(lows) < 2:
        return "UNCONFIRMED"
    high_label = "HH" if highs[-1] > highs[-2] else "LH"
    low_label = "HL" if lows[-1] > lows[-2] else "LL"
    return f"{high_label}_{low_label}"


def confirmed_levels(
    candles: Sequence[Candle], left: int = 2, right: int = 2
) -> tuple[list[float], list[float]]:
    pivots = confirmed_pivots(candles, left, right)
    support = [pivot.price for pivot in pivots if pivot.kind == "LOW"]
    resistance = [pivot.price for pivot in pivots if pivot.kind == "HIGH"]
    return support, resistance
