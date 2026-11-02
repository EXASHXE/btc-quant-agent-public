"""Entirely fabricated native responses and clocks; no observed market payloads."""

import json
import threading
import time

from btc_quant_agent.platform.canary.clocks import Probe, estimate_clock
from btc_quant_agent.platform.canary.public_io import Wire
from btc_quant_agent.platform.canary.public_policy import START, END, SYMBOLS
from btc_quant_agent.platform.core import primitive


class Clock:
    def __init__(self, wall=START + 1000):
        self.ms = wall
        self.base = wall
        self.lock = threading.Lock()

    def wall(self):
        with self.lock:
            return self.ms

    def mono(self):
        with self.lock:
            return 1000 + self.ms - START

    def pair(self):
        with self.lock:
            return self.ms, 1000 + self.ms - START

    def sleep(self, sec):
        with self.lock:
            self.ms += int(sec * 1000)
        time.sleep(0.0001)

    def set(self, ms):
        with self.lock:
            self.ms = ms


def meta_payload():
    return {
        "rateLimits": [
            {"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 2400}
        ],
        "symbols": [
            {
                "symbol": s,
                "baseAsset": s[:-4],
                "quoteAsset": "USDT",
                "marginAsset": "USDT",
                "status": "TRADING",
                "contractType": "PERPETUAL",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5"},
                ],
            }
            for s in SYMBOLS
        ],
    }


def wire(id, payload, t, symbol="*", stream=None, params=None, exposure="SYNTHETIC", **kwargs):
    return Wire(
        id,
        symbol,
        params or {},
        json.dumps(payload, sort_keys=True),
        t - 20,
        t - START + 1000 - 20,
        t + 30,
        t - START + 1030,
        t + 40,
        t - START + 1040,
        first_wall=t + 20 if stream is None else None,
        first_mono=t - START + 1020 if stream is None else None,
        stream=stream,
        exposure=exposure,
        **kwargs,
    )


def clock_dict(t, exposure="SYNTHETIC"):
    p = Probe(t - 120, t - 100, t - START + 880, t - START + 900, t - 110, exposure=exposure)
    return primitive(estimate_clock((p,), allowed_exposure=exposure))


def record(scope, w, metadata=None, clock=True):
    t = w.receive_wall - 30
    return {
        "exposure": w.exposure,
        "received_wall_ms": w.receive_wall,
        "symbol": w.symbol,
        "wire": w.record(),
        "decision_wall_ms": t + 100,
        "decision_mono_ms": t - START + 1100,
        "metadata": {"wire": metadata.record()} if metadata else None,
        "clock": clock_dict(t, w.exposure) if clock else None,
        "scope_hash": scope.hash,
    }


def quote(t, s="BTCUSDT", u=1, bid="100.00", ask="100.02", exposure="SYNTHETIC"):
    return wire(
        "binance_usdm_bbo_ws",
        {
            "stream": s.lower() + "@bookTicker",
            "data": {
                "e": "bookTicker",
                "s": s,
                "st": 1,
                "u": u,
                "E": t,
                "T": t - 2,
                "b": bid,
                "B": "10000",
                "a": ask,
                "A": "10000",
            },
        },
        t,
        s,
        stream=s.lower() + "@bookTicker",
        exposure=exposure,
    )


def candle(start, s="BTCUSDT", interval=60000, values=None, closed=True):
    v = values or {
        "open": 100,
        "high": 101,
        "low": 99,
        "close": 100.5,
        "volume": 1000,
        "quote_volume": 100500,
    }
    t = start + interval + 20
    i = "1m" if interval == 60000 else "5m"
    stream = s.lower() + "@kline_" + i
    return wire(
        "binance_usdm_klines_ws",
        {
            "stream": stream,
            "data": {
                "e": "kline",
                "s": s,
                "E": t,
                "st": 1,
                "k": {
                    "s": s,
                    "t": start,
                    "T": start + interval - 1,
                    "i": i,
                    "x": closed,
                    **{
                        k: str(v[f])
                        for k, f in [
                            ("o", "open"),
                            ("h", "high"),
                            ("l", "low"),
                            ("c", "close"),
                            ("v", "volume"),
                            ("q", "quote_volume"),
                        ]
                    },
                },
            },
        },
        t,
        s,
        stream=stream,
    )


class Socket:
    def __init__(self, backend):
        self.backend = backend

    def shutdown(self, *a):
        self.backend.closed = True


class Connection:
    def __init__(self, messages):
        self.messages = list(messages)
        self.closed = False
        self.socket = Socket(self)

    def recv(self, timeout=None):
        if self.closed:
            raise ConnectionError("CLOSED")
        if self.messages:
            return self.messages.pop(0)
        time.sleep(0.001)
        raise TimeoutError()

    def close(self):
        self.closed = True


class Backend:
    exposure = "SYNTHETIC"

    def __init__(self, scope, clock, responses=None):
        self.scope = scope
        self.clock = clock
        self.calls = []
        self.connections = []
        self.responses = responses or {}
        self.closed = False

    def get(self, url, params, timeout, clock, limit=0):
        self.calls.append((url, dict(params)))
        if "developers.binance.com" in url:
            row = next(x for x in self.scope.document["runtime_document_checks"] if url.endswith(x["path"]))
            return 200, "<html><body>" + " ".join(row["required_tokens"]) + "</body></html>", clock.pair()
        path = url.rsplit("/", 1)[-1]
        if path in self.responses:
            item = self.responses[path]
            if isinstance(item, Exception):
                raise item
            return item[0], json.dumps(item[1]), clock.pair()
        data = (
            meta_payload()
            if path == "exchangeInfo"
            else {"serverTime": clock.wall() + 10}
            if path == "time"
            else []
            if path == "fundingInfo"
            else {
                "symbol": params.get("symbol"),
                "time": clock.wall(),
                "openInterest": "1000",
                "markPrice": "100",
                "indexPrice": "100",
                "lastFundingRate": "0.0001",
                "nextFundingTime": END + 3600000,
                "closeTime": clock.wall(),
                "quoteVolume": "100000000",
                "volume": "1000000",
            }
        )
        clock.sleep(0.02)
        return 200, json.dumps(data), clock.pair()

    def connect(self, url, timeout, on_control):
        assert "wss://fstream.binance.com/" in url and "/private" not in url
        messages = []
        if "/public/" in url:
            for i in range(2):
                for s in SYMBOLS:
                    messages.append(quote(self.clock.wall() - 30, s, i + 1).payload_text)
        c = Connection(messages)
        self.connections.append(c)
        return c

    def close(self):
        self.closed = True


def structural_replay(scope, tmp_path):
    """Fabricated 66-bar, three-symbol provider-to-L23 replay shared with the offline demo."""
    from btc_quant_agent.platform.canary.control import CanaryStore
    from btc_quant_agent.platform.canary.public_journal import PublicJournal
    from btc_quant_agent.platform.canary.public_runtime import PublicEngine
    from btc_quant_agent.platform.selection.fixtures import structural_bars
    from btc_quant_agent.platform.selection.sources import STRUCTURE

    clock = Clock(START)
    store = CanaryStore(tmp_path / "state.sqlite", clock_ms=clock.wall)
    j = PublicJournal(tmp_path, store, clock, exposure="SYNTHETIC", reserve=0)
    model = PublicEngine(scope, clock, store, j, "SYNTHETIC")
    old = structural_bars(count=66, symbols=tuple(sorted(SYMBOLS)))
    grouped = {}
    for b in old:
        grouped.setdefault(b.end, []).append(b)
    for i, oldend in enumerate(sorted(grouped)):
        end = START + (i + 1) * STRUCTURE
        if i % 6 == 0:
            w = wire("binance_usdm_exchange_info", meta_payload(), end - 100)
            clock.set(w.available_wall)
            model.ingest(w)
        w = wire("binance_usdm_server_time", {"serverTime": end + 10}, end + 5)
        clock.set(w.available_wall)
        model.ingest(w)
        for b in grouped[oldend]:
            values, _ = b.values(b.end + 1000)
            w = candle(end - STRUCTURE, b.spec.symbol, STRUCTURE, values)
            clock.set(w.available_wall)
            model.ingest(w)
    model.flush()
    return model, j, store
