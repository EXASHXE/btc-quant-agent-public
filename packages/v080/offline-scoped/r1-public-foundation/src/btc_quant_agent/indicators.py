from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import pairwise


def ema(values: Sequence[float], period: int) -> list[float]:
    if period <= 0 or not values:
        raise ValueError("EMA requires values and period > 0")
    alpha = 2.0 / (period + 1.0)
    output = [float(values[0])]
    for value in values[1:]:
        output.append(alpha * float(value) + (1.0 - alpha) * output[-1])
    return output


def true_ranges(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]
) -> list[float]:
    if not (len(highs) == len(lows) == len(closes)) or not closes:
        raise ValueError("OHLC lengths must match and be non-empty")
    output = [float(highs[0]) - float(lows[0])]
    for i in range(1, len(closes)):
        output.append(
            max(
                float(highs[i]) - float(lows[i]),
                abs(float(highs[i]) - float(closes[i - 1])),
                abs(float(lows[i]) - float(closes[i - 1])),
            )
        )
    return output


def wilder(values: Sequence[float], period: int) -> list[float]:
    if period <= 0 or not values:
        raise ValueError("Wilder smoothing requires values and period > 0")
    output = [float(values[0])]
    alpha = 1.0 / period
    for value in values[1:]:
        output.append(output[-1] + alpha * (float(value) - output[-1]))
    return output


def atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int
) -> list[float]:
    return wilder(true_ranges(highs, lows, closes), period)


def adx(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int
) -> list[float]:
    if len(closes) < 2:
        return [0.0] * len(closes)
    trs = true_ranges(highs, lows, closes)
    plus_dm = [0.0]
    minus_dm = [0.0]
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    atr_values = wilder(trs, period)
    plus_smoothed = wilder(plus_dm, period)
    minus_smoothed = wilder(minus_dm, period)
    dx: list[float] = []
    for tr, plus, minus in zip(atr_values, plus_smoothed, minus_smoothed, strict=True):
        if tr <= 0:
            dx.append(0.0)
            continue
        plus_di = 100.0 * plus / tr
        minus_di = 100.0 * minus / tr
        denom = plus_di + minus_di
        dx.append(100.0 * abs(plus_di - minus_di) / denom if denom else 0.0)
    return wilder(dx, period)


def rolling_zscore(values: Sequence[float], window: int) -> list[float]:
    output: list[float] = []
    for i, value in enumerate(values):
        sample = [float(v) for v in values[max(0, i - window + 1) : i + 1]]
        mean = sum(sample) / len(sample)
        variance = sum((x - mean) ** 2 for x in sample) / len(sample)
        std = math.sqrt(variance)
        output.append((float(value) - mean) / std if std > 0 else 0.0)
    return output


def percentile_rank(values: Sequence[float], lookback: int) -> list[float]:
    output: list[float] = []
    for i, value in enumerate(values):
        sample = values[max(0, i - lookback + 1) : i + 1]
        output.append(sum(1 for item in sample if item <= value) / len(sample))
    return output


def rsi(values: Sequence[float], period: int) -> list[float]:
    if period <= 0 or not values:
        raise ValueError("RSI requires values and period > 0")
    gains = [0.0]
    losses = [0.0]
    for prior, current in pairwise(values):
        change = float(current) - float(prior)
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = wilder(gains, period)
    avg_loss = wilder(losses, period)
    output: list[float] = []
    for gain, loss in zip(avg_gain, avg_loss, strict=True):
        if loss == 0:
            output.append(100.0 if gain > 0 else 50.0)
            continue
        relative_strength = gain / loss
        output.append(100.0 - 100.0 / (1.0 + relative_strength))
    return output


def rate_of_change(values: Sequence[float], period: int) -> list[float]:
    if period <= 0 or not values:
        raise ValueError("ROC requires values and period > 0")
    output: list[float] = []
    for index, value in enumerate(values):
        reference = float(values[max(0, index - period)])
        output.append((float(value) / reference - 1.0) if reference else 0.0)
    return output


def bollinger_width(values: Sequence[float], period: int) -> list[float]:
    if period <= 1 or not values:
        raise ValueError("Bollinger width requires values and period > 1")
    output: list[float] = []
    for index in range(len(values)):
        sample = [float(v) for v in values[max(0, index - period + 1) : index + 1]]
        mean = sum(sample) / len(sample)
        variance = sum((value - mean) ** 2 for value in sample) / len(sample)
        std = math.sqrt(variance)
        output.append(4.0 * std / mean if mean else 0.0)
    return output
