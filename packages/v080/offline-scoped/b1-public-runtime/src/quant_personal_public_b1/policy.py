"""R1 symbol, route, weight and timing policies for USDⓈ-M fixture scans."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

SYMBOLS = frozenset({"BTCUSDT", "ETHUSDT", "SOLUSDT"})
INTERVALS = MappingProxyType({"1d": 86_400_000, "4h": 14_400_000, "1h": 3_600_000, "15m": 900_000, "5m": 300_000})
TIME = "/fapi/v1/time"
INSTRUMENTS = "/fapi/v1/exchangeInfo"
KLINES = "/fapi/v1/klines"
TICKER = "/fapi/v1/ticker/24hr"
QUOTE = "/fapi/v1/ticker/bookTicker"
DEPTH = "/fapi/v1/depth"
OI = "/fapi/v1/openInterest"
OI_HISTORY = "/futures/data/openInterestHist"
FUNDING = "/fapi/v1/fundingRate"
MARK = "/fapi/v1/premiumIndex"
RPI = "/fapi/v1/rpiDepth"
TRADES = "/fapi/v1/aggTrades"

WEIGHTS_VERSION = "USD-M-2026-11-18-B1"
DEPTH_WEIGHTS = MappingProxyType({5: 2, 10: 2, 20: 2, 50: 2, 100: 5, 500: 10, 1000: 20})
STATIC_WEIGHTS = MappingProxyType({
    TIME: 1, INSTRUMENTS: 1, TICKER: 1, QUOTE: 2, OI: 1, OI_HISTORY: 0, FUNDING: 1, MARK: 1,
})
SYMBOL_ONLY = frozenset({TICKER, QUOTE, OI, MARK})
WINDOW_CAPS = MappingProxyType({OI_HISTORY: 1000, FUNDING: 500})
PARAMS = MappingProxyType({key: frozenset(value) for key, value in {
    TIME: set(), INSTRUMENTS: set(), KLINES: {"symbol", "interval", "startTime", "endTime", "limit"},
    **{route: {"symbol"} for route in SYMBOL_ONLY},
    DEPTH: {"symbol", "limit"}, OI_HISTORY: {"symbol", "period", "limit"}, FUNDING: {"symbol", "limit"},
}.items()})
FRESHNESS = MappingProxyType({
    "instrument": 30_000, "ticker": 30_000, "book_ticker": 5_000, "depth": 5_000,
    "open_interest": 30_000, "open_interest_history": 660_000, "funding_history": 90_000_000,
    "mark_funding": 10_000,
})


class SourceBlocked(ValueError):
    """A fail-closed source outcome with an auditable reason code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise SourceBlocked(code, detail)


@dataclass(frozen=True)
class Policy:
    max_requests: int = 80
    max_weight: int = 200
    bootstrap_weight_limit: int = 100
    scan_timeout_ms: int = 12_000
    request_timeout_ms: int = 800
    max_body_bytes: int = 4_000_000
    close_grace_ms: int = 2_000
    max_clock_uncertainty_ms: int = 150
    max_wall_step_ms: int = 1_000
    max_clock_drift_ppm: int = 100
    history_bars: int = 32
    kline_limit: int = 100
    revision_overlap: int = 2
    depth_limit: int = 5
    history_limit: int = 5
    fallback_429_ms: int = 60_000
    freshness_ms: Mapping[str, int] = field(default_factory=lambda: FRESHNESS)
    candle_freshness_ms: Mapping[str, int] = field(default_factory=lambda: INTERVALS)

    def __post_init__(self) -> None:
        for key, value in vars(self).items():
            if key in ("freshness_ms", "candle_freshness_ms"):
                continue
            if type(value) is not int or value < 0 or (value == 0 and key not in (
                "close_grace_ms", "max_wall_step_ms", "max_clock_drift_ppm",
            )):
                raise ValueError(f"invalid policy value for {key}")
        if not (max(self.history_bars, self.revision_overlap) + 2 <= self.kline_limit <= 1500
                and self.depth_limit in DEPTH_WEIGHTS and self.history_limit <= 500
                and self.max_clock_drift_ppm <= 1000):
            raise ValueError("invalid scan bounds")
        for key, defaults in (("freshness_ms", FRESHNESS), ("candle_freshness_ms", INTERVALS)):
            values = dict(getattr(self, key))
            if values.keys() != defaults.keys() or any(type(n) is not int or n <= 0 for n in values.values()):
                raise ValueError(f"invalid {key}")
            object.__setattr__(self, key, MappingProxyType(values))


def request_weight(method: str, route: str, params: Mapping[str, str | int]) -> int:
    """Fail closed before transport. R1 is symbol-scoped even for routes with an all-symbol variant."""
    require(method == "GET" and route in PARAMS, "FORBIDDEN_ROUTE")
    require(params.keys() == PARAMS[route], "FORBIDDEN_QUERY")
    if "symbol" in params:
        symbol = params["symbol"]
        require(type(symbol) is str and symbol in SYMBOLS, "FORBIDDEN_SYMBOL")
    if route == KLINES:
        interval = params["interval"]
        if type(interval) is not str or interval not in INTERVALS:
            raise SourceBlocked("FORBIDDEN_INTERVAL")
        start, end, limit = (params[key] for key in ("startTime", "endTime", "limit"))
        if type(start) is not int or type(end) is not int or type(limit) is not int:
            raise SourceBlocked("FORBIDDEN_KLINE_WINDOW")
        width = INTERVALS[interval]
        require(0 <= start <= end < 2**63 and start % width == end % width == 0
                and (end - start) // width + 1 <= limit <= 1500, "FORBIDDEN_KLINE_WINDOW")
        if limit < 100:
            return 1
        if limit < 500:
            return 2
        return 5 if limit <= 1000 else 10
    if route in (DEPTH, OI_HISTORY, FUNDING):
        limit = params["limit"]
        if type(limit) is not int:
            raise SourceBlocked("FORBIDDEN_LIMIT")
        if route == DEPTH:
            require(limit in DEPTH_WEIGHTS, "FORBIDDEN_DEPTH_LIMIT")
            return DEPTH_WEIGHTS[limit]
        require(1 <= limit <= (500 if route == OI_HISTORY else 1000), "FORBIDDEN_LIMIT")
        if route == OI_HISTORY:
            require(params["period"] == "5m", "FORBIDDEN_OI_PERIOD")
    return STATIC_WEIGHTS[route]
