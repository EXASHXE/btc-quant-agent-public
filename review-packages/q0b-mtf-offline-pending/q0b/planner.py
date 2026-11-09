"""Bounded offline request planning. Endpoint weights are pinned assumptions, not live claims."""
from dataclasses import asdict, dataclass
import re

from .schema import INTERVALS, digest
from .source import SourceError, allowed_range

DEFAULT_UNIVERSE = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
WEIGHTS = {"/fapi/v1/time": 1, "/fapi/v1/exchangeInfo": 1,
           "/fapi/v1/klines": 1, "/fapi/v1/ticker/bookTicker": 2}
MAX_SYMBOLS = 50
MAX_NEW_BARS = 32
OVERLAP_BARS = 2
LIMIT = 64
REQUEST_BUDGET = 400
WEIGHT_BUDGET = 800
RESERVE_FRACTION = 0.20


@dataclass(frozen=True)
class Request:
    endpoint: str
    params: dict
    symbol: str | None = None
    interval: str | None = None
    method: str = "GET"

    @property
    def weight(self):
        return WEIGHTS[self.endpoint]

    @property
    def identity(self):
        return digest(asdict(self))


@dataclass(frozen=True)
class CollectionPlan:
    asof_ms: int
    universe: tuple[str, ...]
    requests: tuple[Request, ...]
    quarantine: dict
    source_veto: str | None = None

    def to_dict(self):
        value = asdict(self)
        value.update(
            schema="Q0B_OFFLINE_COLLECTOR_PLAN_V2",
            universe_denominator=len(self.universe),
            request_count=len(self.requests),
            request_weight=sum(r.weight for r in self.requests),
            max_cycles_per_minute=1,
            immediate_retries=0,
            live_qualification="UNVERIFIED_OFFLINE_PINNED_WEIGHT_ASSUMPTIONS",
            reserve_fraction=RESERVE_FRACTION,
        )
        return value


def plan_collection(asof_ms, symbols=DEFAULT_UNIVERSE, watermarks=None, quarantined=None,
                    overall_source_veto=False):
    """Watermarks are accepted exclusive bar ends, never the machine's current time."""
    universe = tuple(sorted(symbols))
    if (not universe or len(set(universe)) != len(universe) or len(universe) > MAX_SYMBOLS
            or any(not isinstance(s, str) or not re.fullmatch(r"[A-Z0-9]{2,16}USDT", s) for s in universe)):
        raise ValueError("FIXED_UNIQUE_UNIVERSE_REQUIRES_1_TO_50_USDT_SYMBOLS")
    if type(asof_ms) is not int:
        raise ValueError("INTEGER_ASOF_REQUIRED")
    quarantine = dict(quarantined or {})
    if set(quarantine) - set(universe):
        raise ValueError("QUARANTINE_OUTSIDE_UNIVERSE")
    if overall_source_veto:
        return CollectionPlan(asof_ms, universe, (), quarantine, "OVERALL_SOURCE_VETO")
    watermarks = watermarks or {}
    requests = [Request("/fapi/v1/time", {}), Request("/fapi/v1/exchangeInfo", {})]
    for symbol in universe:
        if symbol in quarantine:
            continue
        staged = []
        try:
            for interval, step in INTERVALS.items():
                # Reserve 2s for closed-bar exchange uncertainty; never plan an open interval.
                end = (asof_ms - 2_000) // step * step
                watermark = watermarks.get((symbol, interval))
                if watermark is None:
                    start = end - MAX_NEW_BARS * step
                else:
                    if type(watermark) is not int or watermark % step or watermark > end:
                        raise SourceError("INVALID_OR_FUTURE_WATERMARK")
                    due = (end - watermark) // step
                    if due > MAX_NEW_BARS:
                        raise SourceError("BOUNDED_CATCHUP_EXCEEDED_NO_SILENT_TRUNCATION")
                    # Poll only at a new close; re-read two immutable overlap rows to detect revisions.
                    if due == 0:
                        continue
                    start = watermark - OVERLAP_BARS * step
                allowed_range(start, end)
                staged.append(Request("/fapi/v1/klines", {
                    "symbol": symbol, "interval": interval.lower(), "startTime": start,
                    "endTime": end - 1, "limit": LIMIT,
                }, symbol, interval))
            staged.append(Request("/fapi/v1/ticker/bookTicker", {"symbol": symbol}, symbol))
        except SourceError as error:
            quarantine[symbol] = error.code
            continue
        requests.extend(staged)
    if (len(requests) > REQUEST_BUDGET * (1 - RESERVE_FRACTION)
            or sum(r.weight for r in requests) > WEIGHT_BUDGET * (1 - RESERVE_FRACTION)):
        return CollectionPlan(asof_ms, universe, (), quarantine, "DECLARED_BUDGET_EXCEEDED")
    if len(quarantine) == len(universe):
        return CollectionPlan(asof_ms, universe, (), quarantine, "ALL_SYMBOLS_QUARANTINED")
    return CollectionPlan(asof_ms, universe, tuple(requests), quarantine)


class OfflineStub:
    """Transport boundary accepts only an explicit in-memory response map; no sockets/imports."""
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def execute(self, request):
        self.calls.append(request.identity)
        if request.identity not in self.responses:
            raise ValueError("OFFLINE_STUB_RESPONSE_MISSING")
        value = self.responses[request.identity]
        if isinstance(value, Exception):
            raise value
        return value


class OfflineCollector:
    def __init__(self, transport):
        if type(transport) is not OfflineStub:
            raise TypeError("OFFLINE_STUB_ONLY")
        self.transport = transport

    def collect(self, plan):
        result = {"universe": plan.universe, "universe_denominator": len(plan.universe),
                  "quarantine": dict(plan.quarantine), "source_veto": plan.source_veto,
                  "responses": {s: [] for s in plan.universe}, "network_calls": 0,
                  "admission": "UNADMITTED_FIXTURE_PAYLOADS_NO_SOURCE_AUTHORITY"}
        if plan.source_veto:
            return result
        for request in plan.requests:
            if request.symbol in result["quarantine"]:
                continue
            try:
                response = self.transport.execute(request)
            except Exception as error:
                if request.symbol is None:
                    result["source_veto"] = "GLOBAL_ENDPOINT_FAILURE:" + type(error).__name__
                    result["responses"] = {s: [] for s in plan.universe}
                    break
                result["quarantine"][request.symbol] = type(error).__name__
                result["responses"][request.symbol] = []
                continue
            if request.symbol is not None:
                result["responses"][request.symbol].append({"request_id": request.identity,
                                                           "payload": response})
        if len(result["quarantine"]) == len(plan.universe):
            result["source_veto"] = "ALL_SYMBOLS_QUARANTINED"
        return result
