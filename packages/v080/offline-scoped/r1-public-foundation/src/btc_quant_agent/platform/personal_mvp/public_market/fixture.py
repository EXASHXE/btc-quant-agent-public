"""Deterministic fabricated API responses for the two-scan R1 demonstration and tests."""

import json
from collections.abc import Callable

from .adapter import Params, Reply
from .clock import Sample
from .policy import (
    DEPTH, FUNDING, INSTRUMENTS, INTERVALS, KLINES, MARK, OI, OI_HISTORY, QUOTE, SYMBOLS, TICKER, TIME,
)

VENUE_START_MS = 1_735_689_720_000  # 2025-01-01 00:02:00
PRICES = {"BTCUSDT": 100_000, "ETHUSDT": 3_500, "SOLUSDT": 200}


class FixtureClock:
    """Advance explicitly, with a known venue offset from the synthetic wall clock."""

    def __init__(self, venue_ms: int = VENUE_START_MS) -> None:
        self.venue_ms = venue_ms
        self.wall_ms = venue_ms - 350
        self.monotonic_ms = 10_000

    def sample(self) -> Sample:
        return Sample(self.wall_ms, self.monotonic_ms)

    def advance(self, ms: int) -> None:
        self.venue_ms += ms
        self.wall_ms += ms
        self.monotonic_ms += ms


def fixture_reply(body: object, *, status: int = 200, headers: dict[str, str] | None = None) -> Reply:
    return Reply(status, {"content-type": "application/json", **(headers or {})},
                 json.dumps(body, separators=(",", ":")).encode())


def fixture_instrument(symbol: str) -> dict[str, object]:
    return {"symbol": symbol, "baseAsset": symbol.removesuffix("USDT"), "contractType": "PERPETUAL",
            "status": "TRADING", "quoteAsset": "USDT", "marginAsset": "USDT", "filters": [
                {"filterType": "PRICE_FILTER", "minPrice": "0.01", "maxPrice": "1000000", "tickSize": "0.01"},
                *[{"filterType": name, "minQty": "0.001", "maxQty": "9999", "stepSize": "0.001"}
                  for name in ("LOT_SIZE", "MARKET_LOT_SIZE")],
                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                {"filterType": "PERCENT_PRICE", "multiplierUp": "1.100", "multiplierDown": "0.900",
                 "multiplierDecimal": "3"},
                {"filterType": "MAX_NUM_ORDERS", "limit": 200},
            ]}


class FixtureTransport:
    def __init__(self, clock: FixtureClock, *,
                 mutate: Callable[[str, Params, object], object] | None = None) -> None:
        self.clock = clock
        self.mutate = mutate
        self.calls: list[tuple[str, dict[str, str | int], int]] = []

    def get(self, route: str, params: Params, timeout_ms: int) -> Reply:
        self.calls.append((route, dict(params), timeout_ms))
        self.clock.advance(5)
        body = make_body(route, params, self.clock.venue_ms)
        if self.mutate is not None:
            body = self.mutate(route, params, body)
        self.clock.advance(5)
        if isinstance(body, Reply):
            return body
        return fixture_reply(body)


def make_body(route: str, params: Params, now_ms: int) -> object:
    if route == TIME:
        return {"serverTime": now_ms}
    if route == INSTRUMENTS:
        return {"serverTime": now_ms, "rateLimits": [
            {"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 2400},
            {"rateLimitType": "ORDERS", "interval": "MINUTE", "intervalNum": 1, "limit": 1200},
        ], "symbols": [fixture_instrument(symbol) for symbol in sorted(SYMBOLS)]}
    symbol = str(params["symbol"])
    base = PRICES[symbol]
    if route == KLINES:
        width = INTERVALS[str(params["interval"])]
        return [fixture_bar(base, opened, width) for opened in
                range(int(params["startTime"]), int(params["endTime"]) + 1, width)]
    price = base + (now_ms // 300_000) % 10
    if route == TICKER:
        return {"symbol": symbol, "openPrice": str(base), "highPrice": str(base + 50),
                "lowPrice": str(base - 50), "lastPrice": str(price), "weightedAvgPrice": str(base + 1),
                "priceChange": str(price - base), "priceChangePercent": "0.01", "lastQty": "0.020",
                "volume": "12345.678", "quoteVolume": "1200000.23", "openTime": now_ms - 86_400_000,
                "closeTime": now_ms, "count": 1500}
    if route == QUOTE:
        return {"symbol": symbol, "bidPrice": f"{price}.01", "askPrice": f"{price}.03",
                "bidQty": "1.234", "askQty": "2.345", "time": now_ms}
    if route == DEPTH:
        limit = int(params["limit"])
        return {"lastUpdateId": now_ms, "E": now_ms, "T": now_ms - 1,
                "bids": [[f"{price - level}.01", "1.23"] for level in range(limit)],
                "asks": [[f"{price + level}.03", "2.34"] for level in range(limit)]}
    if route == OI:
        return {"symbol": symbol, "openInterest": "10001.123", "time": now_ms}
    if route in (OI_HISTORY, FUNDING):
        step = 300_000 if route == OI_HISTORY else 28_800_000
        latest = now_ms // step * step
        timestamps = [latest - i * step for i in reversed(range(min(3, int(params["limit"]))))]
        if route == OI_HISTORY:
            return [{"symbol": symbol, "timestamp": stamp, "sumOpenInterest": "10000.10",
                     "sumOpenInterestValue": "999999.01"} for stamp in timestamps]
        return [{"symbol": symbol, "fundingTime": stamp, "fundingRate": "-0.00001",
                 "markPrice": str(base), "fundingRateType": "Regular"} for stamp in timestamps]
    if route == MARK:
        return {"symbol": symbol, "time": now_ms, "markPrice": f"{price}.02", "indexPrice": f"{price}.01",
                "lastFundingRate": "0.00001", "interestRate": "0.00010",
                "nextFundingTime": (now_ms // 28_800_000 + 1) * 28_800_000}
    raise AssertionError(f"fixture has no response for {route}")


def fixture_bar(base: int, opened: int, width: int) -> list[object]:
    price = base + (opened // width) % 7
    return [opened, str(price), str(price + 10), str(price - 10), f"{price}.01",
            "12.34", opened + width - 1, "100.123", 7, "5.0", "55.0", "0"]
