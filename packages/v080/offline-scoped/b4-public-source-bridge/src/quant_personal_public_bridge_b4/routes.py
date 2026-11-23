"""Versioned unsigned USD-M request rules; build only canonical HTTP targets."""

from dataclasses import dataclass
from types import MappingProxyType
from urllib.parse import urlencode

from quant_personal_public_b1.policy import (
    DEPTH, DEPTH_WEIGHTS, FUNDING, INSTRUMENTS, INTERVALS, KLINES, MARK, OI,
    OI_HISTORY, QUOTE, SYMBOLS, TICKER, TIME, request_weight, require,
)
from quant_personal_public_b1.wire import HOST, PORT, Params

CONTRACT = "USD-M-2026-11-20-B4-V1"
DAY = 86_400_000
FUNDING_WINDOW_MS = 3 * DAY
FUNDING_LIMIT = 256
OI_PERIOD_MS = 300_000
OI_LIMIT = 5
ROUTES = MappingProxyType({
    TIME: frozenset(),
    INSTRUMENTS: frozenset(),
    KLINES: frozenset({"symbol", "interval", "limit", "startTime", "endTime"}),
    TICKER: frozenset({"symbol"}),
    QUOTE: frozenset({"symbol"}),
    DEPTH: frozenset({"symbol", "limit"}),
    OI: frozenset({"symbol"}),
    OI_HISTORY: frozenset({"symbol", "period", "limit", "startTime", "endTime"}),
    FUNDING: frozenset({"symbol", "limit", "startTime", "endTime"}),
    MARK: frozenset({"symbol"}),
})
FIXED_WEIGHTS = MappingProxyType({
    TIME: 1, INSTRUMENTS: 1, TICKER: 1, QUOTE: 2, OI: 1, MARK: 1, OI_HISTORY: 0, FUNDING: 1,
})


@dataclass(frozen=True)
class Request:
    route: str
    params: Params
    method: str = "GET"
    host: str = HOST
    port: int = PORT

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))

    def validate(self) -> tuple[int, bytes]:
        require(type(self.method) is str and self.method == "GET" and type(self.route) is str
                and self.route in ROUTES, "FORBIDDEN_ROUTE")
        require(type(self.host) is str and self.host == HOST and type(self.port) is int and self.port == PORT,
                "ORIGIN_NOT_APPROVED")
        params = dict(self.params)
        require(params.keys() == ROUTES[self.route], "FORBIDDEN_QUERY")
        if "symbol" in params:
            symbol = params["symbol"]
            require(type(symbol) is str and symbol in SYMBOLS, "FORBIDDEN_SYMBOL")
        if self.route == KLINES:
            weight = request_weight("GET", KLINES, params)
            width = INTERVALS[params["interval"]]
            require((params["endTime"] - params["startTime"]) // width + 1 == params["limit"],
                    "KLINE_LIMIT_DOES_NOT_MATCH_WINDOW")
        elif self.route == DEPTH:
            require(type(params["limit"]) is int and params["limit"] in DEPTH_WEIGHTS, "FORBIDDEN_DEPTH_LIMIT")
            weight = DEPTH_WEIGHTS[params["limit"]]
        else:
            weight = FIXED_WEIGHTS[self.route]
        if self.route in {FUNDING, OI_HISTORY}:
            start, end, limit = (params[key] for key in ("startTime", "endTime", "limit"))
            cap = 1000 if self.route == FUNDING else 500
            span = FUNDING_WINDOW_MS if self.route == FUNDING else OI_LIMIT * OI_PERIOD_MS
            require(all(type(x) is int for x in (start, end, limit))
                    and 0 < start <= end < 2**63 and end - start <= span and 1 <= limit <= cap,
                    "FORBIDDEN_HISTORY_WINDOW")
            if self.route == OI_HISTORY:
                require(type(params["period"]) is str and params["period"] == "5m", "FORBIDDEN_OI_PERIOD")
        query = urlencode(sorted(params.items()))
        target = self.route + ("?" + query if query else "")
        wire = (f"GET {target} HTTP/1.1\r\nHost: {HOST}\r\n"
                "Accept: application/json\r\nAccept-Encoding: gzip\r\nConnection: close\r\n\r\n")
        return weight, wire.encode("ascii")

    def data(self) -> dict:
        return {"host": self.host, "port": self.port, "method": self.method, "params": dict(self.params)}
