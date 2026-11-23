"""Reviewed Binance public history queries and compatible response envelopes."""

from itertools import pairwise
from typing import Any

from .normalize import history, integer, obj, rows
from .policy import require
from .wire import Params

FUNDING_WINDOW_MS = 3 * 86_400_000
FUNDING_LIMIT = 1000
OI_PERIOD_MS = 300_000


def funding_query(symbol: str, cutoff_ms: int) -> dict[str, str | int]:
    return {"symbol": symbol, "startTime": cutoff_ms - FUNDING_WINDOW_MS,
            "endTime": cutoff_ms, "limit": FUNDING_LIMIT}


def funding_payload(body: object, params: Params) -> tuple[int | None, dict[str, object]]:
    requested_limit = int(params["limit"])
    bounded = "startTime" in params and "endTime" in params
    cap = requested_limit if bounded else max(200, requested_limit)
    source_rows = rows(body)
    require(len(source_rows) <= cap, "FUNDING_RESPONSE_EXCEEDS_DOCUMENTED_BOUND")
    if bounded:
        start, end = int(params["startTime"]), int(params["endTime"])
        for item in source_rows:
            timestamp = integer(obj(item).get("fundingTime"), "fundingTime", minimum=1)
            require(start <= timestamp <= end, "FUNDING_OUTSIDE_REQUEST_WINDOW")
        # Equal-to-limit does not prove the whole inclusive window was seen, even at a tied timestamp.
        require(len(source_rows) < cap, "FUNDING_WINDOW_SATURATED")
    stamp, output = history(source_rows, str(params["symbol"]), cap, funding=True)
    return stamp, {**output, "response_count": len(source_rows),
                   "query_semantics": "BOUNDED_INCLUSIVE_WINDOW" if bounded else "DOCUMENTED_MOST_RECENT_200"}


def oi_payload(body: object, symbol: str, limit: int) -> tuple[int | None, dict[str, Any]]:
    stamp, output = history(body, symbol, limit)
    times = [integer(obj(row).get("timestamp"), "timestamp", minimum=1) for row in rows(body)]
    gaps = [{"after_ms": a, "before_ms": b, "missing_periods": (b - a - 1) // OI_PERIOD_MS}
            for a, b in pairwise(times) if b - a > OI_PERIOD_MS]
    return stamp, {**output, "period_ms": OI_PERIOD_MS, "omitted_periods": gaps,
                   "documented_retention": "LATEST_ONE_MONTH"}
