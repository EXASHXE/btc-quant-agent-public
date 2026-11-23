"""Normalize Binance USDⓈ-M response schemas without float price or quantity arithmetic."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal, localcontext

from .policy import INTERVALS, SourceBlocked, require
from .wire import WINDOW_MS

# Bound magnitude and precision before doing financial arithmetic, including extreme exponents.
NUMERIC = re.compile(r"[+-]?[0-9]{1,30}(?:\.[0-9]{1,30})?")


def decimal_value(value: object, field: str, *, minimum: int | None = None, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not NUMERIC.fullmatch(value):
        raise SourceBlocked("INVALID_DECIMAL", field)
    number = Decimal(value)
    require((minimum is None or number >= minimum) and (not positive or number > 0), "DECIMAL_RANGE", field)
    return number


def obj(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SourceBlocked("EXPECTED_OBJECT")
    return value


def rows(value: object) -> list[object]:
    if not isinstance(value, list):
        raise SourceBlocked("EXPECTED_ARRAY")
    return value


def integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value < 2**63:
        raise SourceBlocked("INVALID_INTEGER", field)
    return value


def dec_fields(source: Mapping[str, object], names: str, *, minimum: int | None = None,
               positive: bool = False) -> dict[str, Decimal]:
    return {key: decimal_value(source.get(key), key, minimum=minimum, positive=positive)
            for key in names.split()}


def check_symbol(source: Mapping[str, object], symbol: str) -> None:
    require(source.get("symbol") == symbol, "RESPONSE_SYMBOL_MISMATCH", symbol)


def exchange_info(body: object, symbols: tuple[str, ...]) -> tuple[
    dict[str, dict[str, object]], dict[tuple[str, int], int]
]:
    value = obj(body)
    instruments: dict[str, dict[str, object]] = {}
    for row in rows(value.get("symbols")):
        product = obj(row)
        symbol = str(product.get("symbol"))
        if symbol not in symbols:
            continue
        require(symbol not in instruments, "DUPLICATE_SYMBOL", symbol)
        expected = {"contractType": "PERPETUAL", "status": "TRADING", "quoteAsset": "USDT", "marginAsset": "USDT"}
        require(all(product.get(key) == val for key, val in expected.items()), "INSTRUMENT_INELIGIBLE", symbol)
        require(product.get("baseAsset") == symbol.removesuffix("USDT"), "INSTRUMENT_BASE_MISMATCH", symbol)
        instruments[symbol] = {**expected, "symbol": symbol, "baseAsset": product["baseAsset"],
                               "filters": instrument_filters(product.get("filters"))}
    require(instruments.keys() == set(symbols), "INSTRUMENT_MISSING")
    return instruments, exchange_limits(value)


def exchange_limits(value: dict[str, object]) -> dict[tuple[str, int], int]:
    limits: dict[tuple[str, int], int] = {}
    for item in rows(value.get("rateLimits")):
        row = obj(item)
        kind = row.get("rateLimitType")
        if kind not in ("REQUEST_WEIGHT", "RAW_REQUESTS"):
            continue
        unit = str(row.get("interval"))
        require(unit in WINDOW_MS, "INVALID_RATE_LIMIT_INTERVAL")
        window = WINDOW_MS[unit] * integer(row.get("intervalNum"), "intervalNum", minimum=1)
        rule = str(kind), window
        require(window <= 86_400_000 and rule not in limits, "INVALID_RATE_LIMIT_WINDOW")
        limits[rule] = integer(row.get("limit"), "limit", minimum=1)
    require(any(kind == "REQUEST_WEIGHT" for kind, _ in limits), "REQUEST_WEIGHT_LIMIT_MISSING")
    return limits


def instrument_filters(body: object) -> dict[str, dict[str, object]]:
    filters: dict[str, dict[str, object]] = {}
    for item in rows(body):
        row = obj(item)
        name = row.get("filterType")
        if not isinstance(name, str) or not name or name in filters:
            raise SourceBlocked("INVALID_FILTER_IDENTITY")
        values: dict[str, object] = {}
        if name == "PRICE_FILTER":
            prices = dec_fields(row, "minPrice maxPrice", minimum=0)
            prices.update(dec_fields(row, "tickSize", positive=True))
            require(prices["maxPrice"] == 0 or prices["minPrice"] <= prices["maxPrice"], "PRICE_FILTER_RANGE")
            values.update(prices)
        elif name in ("LOT_SIZE", "MARKET_LOT_SIZE"):
            qty = dec_fields(row, "minQty maxQty stepSize", positive=True)
            require(qty["minQty"] <= qty["maxQty"], "LOT_SIZE_RANGE")
            values.update(qty)
        elif name == "MIN_NOTIONAL":
            values.update(dec_fields(row, "notional", positive=True))
        elif name == "PERCENT_PRICE":
            multipliers = dec_fields(row, "multiplierUp multiplierDown", positive=True)
            require(multipliers["multiplierDown"] <= multipliers["multiplierUp"], "PERCENT_PRICE_RANGE")
            values.update(multipliers)
            digits = row.get("multiplierDecimal")
            if isinstance(digits, str) and re.fullmatch(r"[0-9]{1,2}", digits):
                digits = int(digits)
            values["multiplierDecimal"] = integer(digits, "multiplierDecimal")
        elif name in ("MAX_NUM_ORDERS", "MAX_NUM_ALGO_ORDERS"):
            values["limit"] = integer(row.get("limit"), "limit", minimum=1)
        else:
            values = {key: value for key, value in row.items() if key != "filterType"}
        filters[name] = values
    require({"PRICE_FILTER", "LOT_SIZE", "MIN_NOTIONAL"} <= filters.keys(), "REQUIRED_FILTER_MISSING")
    return filters


@dataclass(frozen=True)
class Candle:
    open_ms: int
    close_ms_inclusive: int
    end_ms_exclusive: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    base_volume: Decimal
    quote_volume: Decimal
    trade_count: int
    taker_base_volume: Decimal
    taker_quote_volume: Decimal

    def values(self) -> dict[str, object]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def candles(body: object, interval: str, start: int, end: int) -> list[Candle]:
    values = rows(body)
    width = INTERVALS[interval]
    parsed: list[Candle] = []
    seen: set[int] = set()
    for raw in values:
        row = rows(raw)
        require(len(row) == 12, "KLINE_FIELD_COUNT")
        opened = integer(row[0], "openTime")
        closed = integer(row[6], "closeTime")
        require(opened % width == 0 and closed == opened + width - 1, "KLINE_BOUNDARY")
        require(start <= opened <= end, "KLINE_OUTSIDE_WINDOW")
        require(opened not in seen, "KLINE_DUPLICATE")
        require(not parsed or parsed[-1].open_ms < opened, "KLINE_REORDERED")
        seen.add(opened)
        op, hi, lo, cl = (decimal_value(row[i], name, positive=True)
                          for i, name in enumerate(("open", "high", "low", "close"), start=1))
        require(lo <= min(op, cl) <= max(op, cl) <= hi, "KLINE_INVALID_OHLC")
        base, quote, taker_base, taker_quote = (decimal_value(row[i], name, minimum=0) for i, name in
                                              ((5, "volume"), (7, "quoteVolume"),
                                               (9, "takerBuyBase"), (10, "takerBuyQuote")))
        require(taker_base <= base and taker_quote <= quote, "KLINE_INVALID_VOLUME")
        parsed.append(Candle(opened, closed, closed + 1, op, hi, lo, cl, base, quote,
                             integer(row[8], "numberOfTrades"), taker_base, taker_quote))
    require(len(parsed) == (end - start) // width + 1, "KLINE_GAP")
    return parsed


def ticker(body: object, symbol: str) -> tuple[int, dict[str, object]]:
    row = obj(body)
    check_symbol(row, symbol)
    prices = dec_fields(row, "openPrice highPrice lowPrice lastPrice weightedAvgPrice", positive=True)
    require(prices["lowPrice"] <= min(prices["openPrice"], prices["lastPrice"])
            <= max(prices["openPrice"], prices["lastPrice"]) <= prices["highPrice"], "TICKER_INVALID_RANGE")
    opened = integer(row.get("openTime"), "openTime")
    closed = integer(row.get("closeTime"), "closeTime")
    require(opened < closed, "TICKER_INVALID_WINDOW")
    return closed, {**prices, **dec_fields(row, "priceChange priceChangePercent"),
                    **dec_fields(row, "lastQty volume quoteVolume", minimum=0),
                    "openTime": opened, "closeTime": closed, "count": integer(row.get("count"), "count")}


def quote(body: object, symbol: str) -> tuple[int, dict[str, object]]:
    row = obj(body)
    check_symbol(row, symbol)
    values = dec_fields(row, "bidPrice askPrice bidQty askQty", positive=True)
    require(values["bidPrice"] <= values["askPrice"], "CROSSED_QUOTE")
    with localcontext() as context:
        context.prec = 64  # Covers subtraction across the supported 30+30 digit input envelope.
        spread = values["askPrice"] - values["bidPrice"]
    return integer(row.get("time"), "time"), {**values, "spread": spread, "liquidity_class": "BEST_VISIBLE_QUOTE"}


def depth(body: object, limit: int) -> tuple[int, dict[str, object]]:
    row = obj(body)
    bids, asks = book_side(row.get("bids"), limit, descending=True), book_side(row.get("asks"), limit)
    require(not bids or not asks or bids[0][0] < asks[0][0], "CROSSED_DEPTH")
    event, transaction = integer(row.get("E"), "E"), integer(row.get("T"), "T")
    require(transaction <= event, "DEPTH_TIME_ORDER")
    return transaction, {"bids": bids, "asks": asks, "lastUpdateId": integer(row.get("lastUpdateId"), "lastUpdateId"),
                         "event_ms": event, "requested_limit": limit, "short_side": min(len(bids), len(asks)) < limit,
                         "capped_side": max(len(bids), len(asks)) == limit,
                         "liquidity_class": "VISIBLE_NORMAL_BOOK_SNAPSHOT", "rpi_included": False,
                         "execution_guaranteed": False}


def book_side(value: object, limit: int, *, descending: bool = False) -> list[tuple[Decimal, Decimal]]:
    side = rows(value)
    require(len(side) <= limit, "DEPTH_LIMIT_EXCEEDED")
    levels: list[tuple[Decimal, Decimal]] = []
    for item in side:
        level = rows(item)
        require(len(level) == 2, "INVALID_DEPTH_LEVEL")
        price, qty = decimal_value(level[0], "depth price", positive=True), decimal_value(level[1], "depth qty", positive=True)
        if levels:
            prior = levels[-1][0]
            require(price < prior if descending else price > prior, "DEPTH_ORDER")
        levels.append((price, qty))
    return levels


def open_interest(body: object, symbol: str) -> tuple[int, dict[str, object]]:
    row = obj(body)
    check_symbol(row, symbol)
    return integer(row.get("time"), "time"), {**dec_fields(row, "openInterest", minimum=0)}


def mark(body: object, symbol: str) -> tuple[int, dict[str, object]]:
    row = obj(body)
    check_symbol(row, symbol)
    timestamp = integer(row.get("time"), "time")
    next_funding = integer(row.get("nextFundingTime"), "nextFundingTime", minimum=1)
    require(next_funding >= timestamp, "FUNDING_TIME_ORDER")
    return timestamp, {**dec_fields(row, "markPrice indexPrice", positive=True),
                       **dec_fields(row, "lastFundingRate interestRate"),
                       "nextFundingTime": next_funding}


def history(body: object, symbol: str, limit: int, *, funding: bool = False) -> tuple[int | None, dict[str, object]]:
    key = "fundingTime" if funding else "timestamp"
    items: list[dict[str, object]] = []
    previous = -1
    seen: set[tuple[int, str | None]] = set()
    for item in rows(body):
        row = obj(item)
        check_symbol(row, symbol)
        timestamp = integer(row.get(key), key, minimum=1)
        require(timestamp >= previous, "HISTORY_TIMESTAMP_ORDER")
        if funding:
            values = dec_fields(row, "fundingRate")
            values.update(dec_fields(row, "markPrice", positive=True))
        else:
            values = dec_fields(row, "sumOpenInterest sumOpenInterestValue", minimum=0)
        normalized: dict[str, object] = {"source_ms": timestamp, **values}
        rate_type = None
        if funding and "fundingRateType" in row:
            label = row["fundingRateType"]
            if not isinstance(label, str) or not label:
                raise SourceBlocked("INVALID_FUNDING_RATE_TYPE")
            rate_type = label
            normalized["fundingRateType"] = label
        identity = timestamp, rate_type
        require(identity not in seen, "HISTORY_DUPLICATE")
        seen.add(identity)
        items.append(normalized)
        previous = timestamp
    require(len(items) <= limit, "HISTORY_LIMIT_EXCEEDED")
    return previous if items else None, {"rows": items}
