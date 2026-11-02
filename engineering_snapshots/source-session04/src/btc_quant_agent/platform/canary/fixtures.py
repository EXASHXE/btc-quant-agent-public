"""Only fabricated HTTP/WS bodies and local clocks; no existing forward-payload reads."""

from __future__ import annotations

import json
from dataclasses import replace

from ..core import primitive
from .admission import Binding, bind_instrument
from .clocks import Capture, Probe, estimate_clock
from .policy import Endpoint
from .transport import Frame


def capture(event_ms: int, *, decision_delay_ms=100):
    start = event_ms - 20
    values = (
        start,
        event_ms + 20,
        event_ms + 30,
        event_ms + 40,
        event_ms + decision_delay_ms,
        event_ms + decision_delay_ms + 1,
    )
    # Independent declared synthetic monotonic epoch; wall and monotonic deltas agree.
    mono = tuple(v - 1_700_000_000_000 for v in values)
    return Capture(
        values[0],
        mono[0],
        values[1],
        mono[1],
        values[2],
        mono[2],
        values[3],
        mono[3],
        values[4],
        mono[4],
        values[5],
        mono[5],
    )


def clock_for(c: Capture):
    return estimate_clock(
        (
            Probe(
                c.request_wall_ms - 100,
                c.request_wall_ms - 80,
                c.request_mono_ms - 100,
                c.request_mono_ms - 80,
                c.request_wall_ms - 90,
            ),
        )
    )


def metadata(endpoint: Endpoint, symbol: str, event_ms: int, *, tick="0.01", lot="0.001"):
    body = {
        "symbol": symbol,
        "status": "TRADING",
        "contractType": "PERPETUAL",
        "baseAsset": symbol[:-4],
        "quoteAsset": "USDT",
        "marginAsset": "USDT",
        "filters": [
            {"filterType": "PRICE_FILTER", "tickSize": tick},
            {"filterType": "LOT_SIZE", "stepSize": lot, "minQty": lot},
            {"filterType": "MIN_NOTIONAL", "notional": "5"},
        ],
    }
    frame = Frame(
        endpoint.id,
        endpoint.provider,
        endpoint.host,
        endpoint.market,
        symbol,
        json.dumps(body, sort_keys=True),
        capture(event_ms),
        (("quantity", "BASE"),),
    )
    return frame, bind_instrument(frame, symbol)


def bbo(
    endpoint: Endpoint,
    symbol: str,
    event_ms: int,
    *,
    sequence=1,
    bid="100.00",
    ask="100.02",
    epoch=0,
    fault: str | None = None,
):
    body = {
        "e": "bookTicker",
        "s": symbol,
        "st": 1,
        "u": sequence,
        "E": event_ms,
        "T": event_ms - 2,
        "b": bid,
        "B": "10000",
        "a": ask,
        "A": "10000",
    }
    c, host, market, provider = capture(event_ms), endpoint.host, endpoint.market, endpoint.provider
    units = (("quantity", "BASE"), ("price", "USDT/BASE"))
    error, status = None, 200
    if fault == "missing_timestamp":
        body.pop("E")
    if fault == "wrong_symbol":
        body["s"] = "OTHERUSDT"
    if fault == "wrong_market":
        body["st"] = 2
    if fault == "wrong_provider":
        provider = "okx"
    if fault == "wrong_host":
        host = "https://dapi.binance.com"
    if fault == "wrong_units":
        units = (("quantity", "QUOTE"), ("price", "USDT/BASE"))
    if fault == "invalid_tick":
        body["b"] = "100.001"
    if fault == "stale":
        body["E"] -= 10000
        body["T"] -= 10000
    if fault == "future":
        body["E"] += 10000
        body["T"] += 10000
    if fault == "wall_jump":
        c = replace(c, available_wall_ms=c.available_wall_ms + 500)
    if fault == "sync_failure":
        c = replace(c, sync_evidence="")
    if fault == "timeout":
        error = "TIMEOUT"
    if fault == "disconnect":
        error = "DISCONNECT"
    if fault == "429":
        status = 429
    if fault == "418":
        status = 418
    return Frame(
        endpoint.id,
        provider,
        host,
        market,
        symbol,
        json.dumps(body, sort_keys=True),
        c,
        units,
        epoch,
        status,
        error,
    )


def candle_frame(
    endpoint: Endpoint, binding: Binding, start: int, *, interval=60_000, closed=True, end_receive_ms=None
):
    end = start + interval
    c = capture(end + 20)
    if end_receive_ms is not None:
        c = capture(end_receive_ms)
    row = [start, "100", "101", "99", "100.50", "1000", end - 1, "100500", 100, "500", "50250", "0"]
    if "_ws" in endpoint.id:
        body = {
            "E": end + 20,
            "s": binding.record.venue_symbol,
            "k": {
                "t": start,
                "T": end - 1,
                "i": "1m" if interval == 60_000 else "5m",
                "x": closed,
                "o": "100",
                "h": "101",
                "l": "99",
                "c": "100.50",
                "v": "1000",
                "q": "100500",
            },
        }
    else:
        body = {"interval_seconds": interval // 1000, "rows": [row]}
    return Frame(
        endpoint.id,
        endpoint.provider,
        endpoint.host,
        endpoint.market,
        binding.spec.symbol,
        json.dumps(body, sort_keys=True),
        c,
        (("volume", "BASE"), ("quote_volume", "USDT")),
    )


def frame_from_record(raw: dict) -> Frame:
    value = dict(raw)
    value["capture"] = Capture(**value["capture"])
    value["native_units"] = tuple(tuple(x) for x in value["native_units"])
    return Frame(**value)


def raw_record(frame: Frame) -> dict:
    return primitive(frame)
