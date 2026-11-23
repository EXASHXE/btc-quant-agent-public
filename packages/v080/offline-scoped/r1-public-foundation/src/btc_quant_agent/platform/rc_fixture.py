"""Frozen, constructed simulator candles; these prices are not market observations."""
from __future__ import annotations

import math
from dataclasses import asdict

from ..domain import Candle
from .rc_source import SYMBOLS, canonical, normalize
from .swing import INTERVALS

SEED = 7061106
TRIGGER = 1793923200000  # 2026-11-06 00:00 UTC, fixed simulator clock
DECISION = TRIGGER + 1000


def wire(candle, *, revision=0, delay_ms=100, at_ms=None):
    end = candle.close_time_ms + 1
    source = end + delay_ms if at_ms is None else at_ms
    c = asdict(candle)
    c["available_at_ms"] = source + 20
    return canonical({"schema": "SYNTHETIC_CLOSED_BAR_V1", "venue": "SYNTHETIC_SIMULATOR",
                      "source_id": "PROGRAM_A_SYNTHETIC_V1", "candle": c,
                      "source_event_ms": source, "received_ms": source + 10,
                      "available_ms": source + 20, "durable_ms": source + 30, "revision": revision})


def _hourly(symbol, flat):
    scale = {"BTCUSDT": 100.0, "ETHUSDT": 10.0, "SOLUSDT": 1.0}[symbol]
    suffix = [126, 128, 130, 132, 134, 146, 132, 130, 129, 130, 131, 130,
              129, 129.5, 130, 131, 131.5, 132, 131, 130, 129.5, 130, 130.5, 132.5]
    count = 80 * 6
    closes = ([120.0] * count if flat else
              [100 + 26 * i / (count - len(suffix)) + 0.6 * math.sin(i * math.pi / 4)
               for i in range(count - len(suffix))] + suffix)
    output = []
    previous = closes[0]
    for index, end_price in enumerate(closes):
        for hour in range(4):
            opening = previous + (end_price - previous) * hour / 4
            closing = previous + (end_price - previous) * (hour + 1) / 4
            wick = 0.1 + 0.02 * (index % 3)
            high, low = max(opening, closing) + wick, min(opening, closing) - wick
            if flat:
                high, low = 120.1, 119.9
            if not flat and index == count - 1 and hour == 0:
                low = min(low, 129.6)
            start = TRIGGER - count * INTERVALS["4H"] + (index * 4 + hour) * INTERVALS["1H"]
            output.append(Candle(symbol, "1H", start, start + INTERVALS["1H"] - 1,
                                 opening * scale, high * scale, low * scale, closing * scale,
                                 1000.0, quote_volume=1000 * closing * scale))
        previous = end_price
    return output


def fixture(*, flat=False, optional_hourly=True):
    """Aggregate a common hourly history, then serve only declared warmup windows."""
    records = []
    for symbol in SYMBOLS:
        hourly = _hourly(symbol, flat)
        members = {"1H": hourly}
        for interval in ("4H", "1D"):
            width = INTERVALS[interval] // INTERVALS["1H"]
            aggregates = []
            for index in range(0, len(hourly), width):
                group = hourly[index:index + width]
                aggregates.append(Candle(symbol, interval, group[0].open_time_ms, group[-1].close_time_ms,
                                         group[0].open, max(c.high for c in group), min(c.low for c in group),
                                         group[-1].close, sum(c.volume for c in group),
                                         quote_volume=sum(c.quote_volume for c in group)))
            members[interval] = aggregates
        for interval, keep in (("1H", 24), ("4H", 80), ("1D", 60)):
            if interval == "1H" and not optional_hourly:
                continue
            records.extend(normalize(wire(c)) for c in members[interval][-keep:])
    # Delivery order is fixed, and per-series ascending; the source adapter never sorts inputs.
    return tuple(sorted(records, key=lambda r: (r.bar.end_ms, r.bar.candle.symbol, r.bar.candle.interval)))


def mixed_fixture():
    rows = [r for r in fixture() if r.bar.candle.symbol == "BTCUSDT"]
    rows += [r for r in fixture(flat=True) if r.bar.candle.symbol != "BTCUSDT"]
    return tuple(sorted(rows, key=lambda r: (r.bar.end_ms, r.bar.candle.symbol, r.bar.candle.interval)))


def future_fixture(decision, *, scenario="target", hours=50):
    """Declared conditional future paths; never used by the ex-ante compiler."""
    o = decision.opportunity
    sign = 1 if o.direction == "LONG" else -1
    entry, stop = sum(o.entry_region) / 2, o.buffered_stop
    target = o.target_zones[0]
    risk = abs(entry - stop)
    records = []
    for index in range(hours):
        opening = closing = entry
        high, low = entry + risk * 0.1, entry - risk * 0.1
        if scenario == "no_fill":
            opening = closing = (o.entry_region[0] + stop) / 2 if sign == 1 else (o.entry_region[1] + stop) / 2
            high, low = opening + risk * 0.02, opening - risk * 0.02
        elif scenario == "missed":
            opening = closing = (o.entry_region[1] + risk if sign == 1 else o.entry_region[0] - risk)
            high, low = opening + risk * 0.02, opening - risk * 0.02
        elif index == (1 if scenario == "entry_ambiguous" else 8):
            if scenario in ("target", "ambiguous", "entry_ambiguous"):
                high = max(high, target + risk * 0.1) if sign == 1 else high
                low = min(low, target - risk * 0.1) if sign == -1 else low
            if scenario in ("stop", "ambiguous", "entry_ambiguous"):
                low = min(low, stop - risk * 0.1) if sign == 1 else low
                high = max(high, stop + risk * 0.1) if sign == -1 else high
        start = decision.trigger_close_ms + index * INTERVALS["1H"]
        records.append(normalize(wire(Candle(decision.symbol, "1H", start, start + INTERVALS["1H"] - 1,
                                             opening, high, low, closing, 1000.0))))
    return tuple(records)
