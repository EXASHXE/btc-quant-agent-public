from __future__ import annotations

import csv
from pathlib import Path

from ..backtest import FundingEvent


def read_funding_events_csv(path: str | Path) -> list[FundingEvent]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    events = [
        FundingEvent(
            timestamp_ms=int(row["timestamp_ms"]),
            funding_rate=float(row["funding_rate"]),
            mark_price=float(row["mark_price"]) if row.get("mark_price") else None,
        )
        for row in rows
    ]
    if events != sorted(events, key=lambda event: event.timestamp_ms):
        raise ValueError("funding events must be chronological")
    if len({event.timestamp_ms for event in events}) != len(events):
        raise ValueError("duplicate funding timestamp")
    return events
