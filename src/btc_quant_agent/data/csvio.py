from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from ..domain import Candle


FIELDS = [
    "symbol",
    "interval",
    "open_time_ms",
    "close_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "taker_buy_base_volume",
    "trades",
]


def write_candles(path: str | Path, candles: Sequence[Candle]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for bar in candles:
            writer.writerow({field: getattr(bar, field) for field in FIELDS})


def read_candles(path: str | Path) -> list[Candle]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        Candle(
            symbol=row["symbol"],
            interval=row["interval"],
            open_time_ms=int(row["open_time_ms"]),
            close_time_ms=int(row["close_time_ms"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            quote_volume=float(row.get("quote_volume") or 0),
            taker_buy_base_volume=float(row.get("taker_buy_base_volume") or 0),
            trades=int(row.get("trades") or 0),
            closed=True,
        )
        for row in rows
    ]
