"""Deterministic fabricated receipts; no transport, market payload or historical datasets."""

from __future__ import annotations

from dataclasses import replace
from math import sin

from ..core import Candle, DataProvenance, ExecutableQuote, InstrumentSpec, MarketEvent, dec, quantize
from .lifecycle import Monitor
from .selector import Policy
from .sources import MINUTE, STRUCTURE, UNITS, Bar, FrozenUniverse, Observation, SourceHistory

BASE = 1_800_000_000_000
SYMBOLS = tuple(
    sorted(
        (
            "BTCUSDT",
            "ETHUSDT",
            "ADAUSDT",
            "SOLUSDT",
            "XRPUSDT",
            "LINKUSDT",
            "LTCUSDT",
            "BNBUSDT",
            "AVAXUSDT",
            "DOGEUSDT",
            "DOTUSDT",
            "ATOMUSDT",
        )
    )
)


def observation(
    spec,
    field,
    value,
    end,
    interval=STRUCTURE,
    *,
    age=0,
    provider=None,
    symbol=None,
    unit=None,
    delay=100,
    complete=True,
):
    event = end - age
    p = DataProvenance(
        provider or spec.provider,
        f"FABRICATED:{spec.symbol}:{field}:{event}",
        event,
        event + 10,
        event + delay,
    )
    return Observation(
        field,
        float(value),
        symbol or spec.symbol,
        interval,
        unit or UNITS[field],
        p,
        2000 if field in {"open", "high", "low", "close", "volume", "quote_volume"} else 120_000,
        complete,
    )


def bar(spec, start, open_, high, low, close, volume=100_000, *, interval=STRUCTURE, extra=(), closed=True):
    values = {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "quote_volume": volume * close,
    }
    return Bar(
        spec,
        start,
        start + interval,
        interval,
        tuple(observation(spec, k, v, start + interval, interval) for k, v in values.items()) + tuple(extra),
        closed,
    )


def structural_bars(count=305, symbols=SYMBOLS) -> tuple[Bar, ...]:
    result = []
    for n, symbol in enumerate(symbols):
        spec = InstrumentSpec(symbol, provider="offline_fixture", min_notional=dec(5))
        prev = 100 + n * 4
        for i in range(count):
            if symbol == "ADAUSDT":
                price = 100 + 0.8 * (-1) ** i + 0.12 * sin(i * 0.13)
            else:
                price = 100 + n * 4 + 0.08 * i + 0.19 * sin(i * 0.4 + n * 0.1)
            if symbol == "SOLUSDT":
                price = 100 + n * 4 + 0.08 * i + 0.19 * sin(i * 0.4 + 2.5)
            high, low = max(price, prev) + 0.35, min(price, prev) - 0.35
            if symbol == "SOLUSDT":
                high, low = max(price, prev) + 0.05, min(price, prev) - 0.05
                if i == count - 12:
                    low = min(price, prev) - 0.6  # Confirmed earlier swing, not a future-derived stop.
            opening = prev
            if symbol == "ADAUSDT":
                opening, high, low = price, price + 0.35, price - 0.35
            if i == count - 1 and symbol == "ADAUSDT":
                low = 98.38  # Observed wick, completed close remains inside the prior channel.
            # Wide observed pullback wick reaches EMA20 while closing in the prior trend.
            if i == count - 1 and symbol == "ETHUSDT":
                low = price - 1.6
            end = BASE + (i + 1) * STRUCTURE
            extras = (
                observation(spec, "open_interest", 1_000_000 + i * 100, end),
                observation(spec, "funding_rate", 0.0001, end),
                observation(spec, "spot_close", price - 0.01, end),
            )
            result.append(
                bar(
                    spec,
                    BASE + i * STRUCTURE,
                    opening,
                    high,
                    low,
                    price,
                    100_000 + 3000 * sin(i * 0.7 + n),
                    extra=extras,
                )
            )
            prev = price
    return tuple(result)


def history(bars: tuple[Bar, ...], cutoff: int, policy: Policy) -> SourceHistory:
    return SourceHistory(
        bars,
        FrozenUniverse(
            tuple(sorted(policy.symbols)),
            policy.benchmark,
            cutoff,
            minimum_rank_members=policy.min_rank_members,
            decision_ts=cutoff + 1000,
        ),
    )


def monitor(anchors, minute, *, quote=True, fault=None, price=None, mode="normal", spec=None) -> Monitor:
    spec = spec or InstrumentSpec(anchors["symbol"], provider="offline_fixture")
    anchor, atr = float(anchors["anchor"]), anchors["atr"]
    side = 1 if anchors["side"] == "LONG" else -1
    start = anchors["setup_ts"] + (minute - 1) * MINUTE
    close = anchor + side * min(0.03 * minute, 0.12) * atr
    previous = close - side * 0.03 * atr
    previous_bar = bar(
        spec,
        start - MINUTE,
        previous - 0.01 * atr,
        previous + 0.005 * atr,
        previous - 0.015 * atr,
        previous,
        interval=MINUTE,
    )
    current = bar(
        spec,
        start,
        close - side * 0.02 * atr,
        close + 0.005 * atr,
        close - 0.03 * atr,
        close,
        interval=MINUTE,
    )
    now = current.end + 2000
    safe_offset = min(0.08 * atr, 0.1 * abs(anchor - float(anchors["stop"])))
    quote_price = anchor + side * safe_offset if price is None else price
    if mode == "lost" and minute >= 4:
        quote_price = float(anchors["chase_cap"]) + side * 0.05 * atr
    if mode == "target_consumed" and anchors["target"]:
        quote_price = float(anchors["target"]) + side * 0.1
    if mode == "gap":
        stop = float(anchors["stop"])
        close = stop - side * atr
        current = bar(spec, start, close, close + 0.1 * atr, close - 0.1 * atr, close, interval=MINUTE)
        quote_price = close
    qp = DataProvenance(
        spec.provider, f"FABRICATED:TOP_OF_BOOK:{spec.symbol}:{now - 500}", now - 500, now - 400, now - 300
    )
    bid, ask = (
        quantize(quote_price - 0.01, spec.tick_size),
        quantize(quote_price + 0.01, spec.tick_size, up=True),
    )
    q = ExecutableQuote(spec.symbol, bid, ask, qp, dec(10000), dec(10000)) if quote else None
    authority = "OFFLINE_EXECUTABLE_TOP_OF_BOOK"
    if fault == "stale_quote" and q:
        q = replace(
            q,
            provenance=replace(
                qp, exchange_event_ts=now - 10000, received_ts=now - 9900, available_ts=now - 9800
            ),
        )
    if fault == "invalid_authority":
        authority = "CANDLE_ESTIMATE"
    if fault == "high_spread" and q:
        q = replace(
            q,
            bid=quantize(quote_price * 0.99, spec.tick_size),
            ask=quantize(quote_price * 1.01, spec.tick_size),
        )
    if fault == "source_clock" and q:
        q = replace(q, provenance=replace(qp, received_ts=qp.exchange_event_ts - 1))
    funding = observation(spec, "funding_rate", 0.0001, current.end, MINUTE)
    cadence = 8 * 3_600_000
    next_ts = (now // cadence + 1) * cadence
    return Monitor(
        current,
        now,
        q,
        authority,
        funding,
        None if fault == "funding_unknown" else 8 * 3_600_000,
        next_ts,
        fault != "outage",
        anchors["regime"],
        previous_bar,
        anchors.get("beta"),
        anchors["setup_ts"] + 1000,
        cadence_evidence=observation(spec, "funding_interval_ms", cadence, current.end, MINUTE),
        next_funding_evidence=observation(spec, "next_funding_ts", next_ts, current.end, MINUTE),
    )


def market_event(m: Monitor) -> MarketEvent:
    v, _ = m.bar.values(m.bar.end + 1000)
    c = Candle(
        symbol=m.bar.spec.symbol,
        interval="1m",
        open_time_ms=m.bar.start,
        close_time_ms=m.bar.end - 1,
        open=v["open"],
        high=v["high"],
        low=v["low"],
        close=v["close"],
        volume=v["volume"],
        quote_volume=v["quote_volume"],
        closed=True,
        available_at_ms=m.bar.end + 100,
    )
    p = DataProvenance(
        m.bar.spec.provider,
        "FABRICATED:MANAGEMENT_BAR:" + m.bar.id,
        m.bar.end,
        m.bar.end + 10,
        m.bar.end + 100,
    )
    return MarketEvent(m.bar.spec, c, p, m.now, m.quote)
