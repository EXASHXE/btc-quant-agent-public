"""Historical candle aggregation, extracted without inferring formal PIT proof."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from ..domain import Candle

INTERVAL_MS = {"1m": 60_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}


def resample(candles: Sequence[Candle], interval: str) -> list[Candle]:
    bucket_ms = INTERVAL_MS[interval]
    buckets: dict[int, list[Candle]] = {}
    for bar in candles:
        bucket = (bar.open_time_ms // bucket_ms) * bucket_ms
        buckets.setdefault(bucket, []).append(bar)
    output: list[Candle] = []
    expected_children = bucket_ms // INTERVAL_MS[candles[0].interval] if candles else 0
    for bucket, children in sorted(buckets.items()):
        if len(children) != expected_children:
            continue
        children = sorted(children, key=lambda item: item.open_time_ms)
        if any(
            current.open_time_ms - previous.open_time_ms != INTERVAL_MS[candles[0].interval]
            for previous, current in pairwise(children)
        ):
            continue
        output.append(
            Candle(
                symbol=children[0].symbol,
                interval=interval,
                open_time_ms=bucket,
                close_time_ms=bucket + bucket_ms - 1,
                open=children[0].open,
                high=max(item.high for item in children),
                low=min(item.low for item in children),
                close=children[-1].close,
                volume=sum(item.volume for item in children),
                quote_volume=sum(item.quote_volume for item in children),
                taker_buy_base_volume=sum(item.taker_buy_base_volume for item in children),
                trades=sum(item.trades for item in children),
                closed=True,
            )
        )
    return output
