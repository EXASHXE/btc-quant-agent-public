"""USD-M normalization shared by collection and independent admission."""

from decimal import Decimal, localcontext

from quant_personal_public_b1 import normalize as n
from quant_personal_public_b1.compat import funding_payload, oi_payload
from quant_personal_public_b1.policy import require

from .routes import (
    DEPTH, FUNDING, INSTRUMENTS, MARK, OI, OI_HISTORY, QUOTE, TICKER, Request,
)
from .source import digest

OBSERVATIONS = {
    "instrument": INSTRUMENTS, "ticker": TICKER, "funding": FUNDING, "oi_history": OI_HISTORY,
    "oi": OI, "mark": MARK, "depth": DEPTH, "quote": QUOTE,
}
FRESH_MS = {"instrument": 3_600_000, "ticker": 1_200_000, "funding": 90_000_000,
            "oi_history": 660_000, "oi": 30_000, "mark": 10_000, "depth": 5_000, "quote": 5_000}
REFRESH_MS = {"instrument": 1_800_000, "ticker": 900_000, "funding": 900_000, "oi_history": 300_000}


def venue_limits(body):
    source = n.obj(body)
    rows = []
    for raw in n.rows(source.get("rateLimits")):
        row = n.obj(raw)
        kind = row.get("rateLimitType")
        rows.append({**row, "rateLimitType": "RAW_REQUESTS" if kind == "RAW_REQUEST" else kind})
    return n.exchange_limits({**source, "rateLimits": rows})


def pages(request: Request, body: object) -> dict:
    p = request.params
    parsed = n.candles(body, p["interval"], p["startTime"], p["endTime"])
    return {c.open_ms: (c, digest(raw)) for c, raw in zip(parsed, body, strict=True)}


def observation(request: Request, body: object, symbol: str):
    route, p = request.route, request.params
    require(route == INSTRUMENTS or p["symbol"] == symbol, "CONTEXT_SYMBOL_MISMATCH", symbol)
    if route == INSTRUMENTS:
        event, data = None, n.exchange_info(body, (symbol,))[0][symbol]
        require("MARKET_LOT_SIZE" in data["filters"], "MARKET_LOT_FILTER_MISSING")
    elif route == DEPTH:
        if "symbol" in n.obj(body):
            n.check_symbol(body, symbol)
        event, data = n.depth(body, p["limit"])
        require(bool(data["bids"]) and bool(data["asks"]), "NO_TWO_SIDED_DEPTH")
    elif route == FUNDING:
        funding_rows = []
        for row in n.rows(body):
            item = n.obj(row)
            require("fundingRateType" not in item, "NON_VENUE_FUNDING_FIELD")
            label = item.get("rateType", "UNKNOWN")
            require(label in ("Regular", "Special", "UNKNOWN"), "UNKNOWN_FUNDING_RATE_TYPE")
            funding_rows.append({**item, "fundingRateType": label})
        event, data = funding_payload(funding_rows, p)
        require(bool(data["rows"]), "FUNDING_HISTORY_EMPTY")
    elif route == OI_HISTORY:
        event, data = oi_payload(body, symbol, p["limit"])
        require(event is not None, "OI_HISTORY_EMPTY")
        require(all(p["startTime"] <= row["source_ms"] <= p["endTime"] for row in data["rows"]),
                "OI_HISTORY_OUTSIDE_WINDOW")
    else:
        parser = {TICKER: n.ticker, QUOTE: n.quote, OI: n.open_interest, MARK: n.mark}[route]
        event, data = parser(body, symbol)
    return event, data


def observation_ref(ident, scan, raw_sha, request, body, symbol, seen):
    event, data = observation(request, body, symbol)
    output_event = data.get("event_ms", event)
    require(output_event is None or 0 < output_event <= seen.upper_ms, "LATE_CONTEXT", request.route)
    publication = ({"venue_ms": data["event_ms"], "field": "E", "meaning": "MESSAGE_OUTPUT_TIME"}
                   if request.route == DEPTH else "UNKNOWN")
    return {"receipt_id": ident, "source_scan_id": scan, "raw_sha256": raw_sha,
            "normalized_sha256": digest(data), "source_event_ms": event,
            "source_publication": publication, "received_venue_lower_ms": seen.lower_ms,
            "received_venue_upper_ms": seen.upper_ms}, data


def bar_ref(ident, scan, raw_sha, candle, row_sha, previous):
    revision = 1 if previous is None else previous["revision"] + 1
    return {"receipt_id": ident, "source_scan_id": scan, "raw_sha256": raw_sha,
            "normalized_sha256": digest(candle.values()), "source_row_sha256": row_sha,
            "open_ms": candle.open_ms, "end_ms_exclusive": candle.end_ms_exclusive,
            "close_ms_inclusive": candle.close_ms_inclusive, "source_publication": "UNKNOWN",
            "finality": "COMPLETE", "revision": revision,
            "previous_revision_sha256": previous["source_row_sha256"] if previous else None}


def validate_age(name, ref, as_of):
    event = ref["source_event_ms"]
    relevant = event if event is not None else ref["received_venue_lower_ms"]
    require(ref["received_venue_upper_ms"] <= as_of and 0 <= as_of - relevant <= FRESH_MS[name],
            "STALE_OR_LATE_CONTEXT", name)


def coherent(context):
    visible = {key: item["values"] for key, item in context.items()}
    quote, book = visible["quote"], visible["depth"]
    with localcontext() as ctx:
        ctx.prec = 40
        for key, side in (("bidPrice", "bids"), ("askPrice", "asks")):
            ticker = Decimal(quote[key])
            level = Decimal(book[side][0][0])
            require(abs(level - ticker) / ticker <= Decimal("0.001"), "QUOTE_DEPTH_CONTRADICTION")
    observed = [context[key]["source_event_ms"] for key in ("quote", "depth", "mark", "oi")]
    require(max(observed) - min(observed) <= 5_000, "FAST_OBSERVATION_SKEW")
    require(context["funding"]["source_event_ms"] < visible["mark"]["nextFundingTime"],
            "FUNDING_MARK_TIME_CONTRADICTION")
