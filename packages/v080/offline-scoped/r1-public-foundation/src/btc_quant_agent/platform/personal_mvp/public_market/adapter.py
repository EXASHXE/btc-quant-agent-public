"""Bounded unsigned GET dispatch with injected offline transport and conservative rate accounting."""

import json
import re
import ssl
from collections import deque
from dataclasses import dataclass
from datetime import timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Callable, Mapping, Protocol

from .clock import Clock, Sample, check_elapsed
from .policy import QUOTE, WINDOW_CAPS, Policy, SourceBlocked, request_weight, require

Params = Mapping[str, str | int]
WEIGHT_HEADER = re.compile(r"x-mbx-used-weight-(\d{1,4}[smhd])", re.I)
WINDOW_MS = {"SECOND": 1_000, "MINUTE": 60_000, "HOUR": 3_600_000, "DAY": 86_400_000}


@dataclass(frozen=True)
class Reply:
    status: int
    headers: Mapping[str, str]
    body: bytes


class Transport(Protocol):
    """Injected deterministic transport. R1 ships fixture transport only."""

    def get(self, route: str, params: Params, timeout_ms: int) -> Reply: ...


@dataclass(frozen=True)
class Receipt:
    seq: int
    sent: Sample
    received: Sample
    body: object


class RateLimits:
    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self.rules = {("REQUEST_WEIGHT", 60_000): policy.bootstrap_weight_limit}
        self.reported_rules: dict[tuple[str, int], int] = {}
        self.attempts: deque[tuple[int, str, int]] = deque()
        self.headers: dict[int, deque[tuple[int, int, int]]] = {}
        self.total_weight = 0
        self.cooldown_until: int | None = None
        self.halted: str | None = None

    def configure(self, rules: dict[tuple[str, int], int], now_ms: int) -> None:
        # Retain tighter previously observed rules in this session and all charges needed by future rules.
        for rule, limit in rules.items():
            self.reported_rules[rule] = min(limit, self.reported_rules.get(rule, limit))
        self.rules = dict(self.reported_rules)
        self.rules.setdefault(("REQUEST_WEIGHT", 60_000), self.policy.bootstrap_weight_limit)
        self.admit_window_cost("", 0, now_ms, attempts=0)

    def admit_window_cost(self, route: str, weight: int, now_ms: int, *, attempts: int = 1) -> None:
        # Windows roll conservatively from local monotonic observations, even across successive scans.
        while self.attempts and self.attempts[0][0] <= now_ms - 86_400_000:
            self.attempts.popleft()
        for (kind, window), limit in self.rules.items():
            in_window = [item for item in self.attempts if item[0] > now_ms - window]
            if kind == "RAW_REQUESTS":
                require(len(in_window) + attempts <= limit, "VENUE_REQUEST_LIMIT")
                continue
            used = sum(item[2] for item in in_window)
            reports = self.headers.get(window, ())
            used = max(used, max((reported + self.total_weight - at_report
                                  for stamp, reported, at_report in reports if stamp > now_ms - window),
                                 default=0))
            require(used + weight <= limit, "VENUE_WEIGHT_LIMIT")
        if route in WINDOW_CAPS:
            used = sum(item[1] == route for item in self.attempts if item[0] > now_ms - 300_000)
            require(used + attempts <= WINDOW_CAPS[route], "ENDPOINT_REQUEST_LIMIT")

    def charge(self, route: str, weight: int, now_ms: int) -> None:
        self.admit_window_cost(route, weight, now_ms)
        self.total_weight += weight
        self.attempts.append((now_ms, route, weight))

    def observe(self, route: str, headers: Mapping[str, str], now_ms: int) -> None:
        if route == QUOTE:
            return  # This endpoint's published used-weight header is inaccurate.
        for key, value in headers.items():
            match = WEIGHT_HEADER.fullmatch(key)
            if not match or not re.fullmatch(r"[0-9]{1,10}", value):
                continue
            unit = {"s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}[key[-1]]
            window = int(match[1][:-1]) * unit
            if not 0 < window <= 86_400_000:
                continue
            reports = self.headers.setdefault(window, deque())
            while reports and reports[0][0] <= now_ms - window:
                reports.popleft()
            reports.append((now_ms, int(value), self.total_weight))


def retry_after_ms(headers: Mapping[str, str], received: Sample, default: int) -> int:
    raw = headers.get("retry-after", "").strip()
    if re.fullmatch(r"[0-9]{1,10}", raw):
        return int(raw) * 1000
    try:
        end = parsedate_to_datetime(raw)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        # If the fixture includes server Date, avoid relying on a potentially offset local wall clock.
        if "date" in headers:
            reference = parsedate_to_datetime(headers["date"]).timestamp() * 1000
            return max(0, int(end.timestamp() * 1000 - reference) + 1000)
        return max(default, int(end.timestamp() * 1000 - received.wall_ms) + 1000)
    except (ValueError, TypeError, OverflowError, OSError):
        return default


def json_body(raw: bytes) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            require(key not in result, "DUPLICATE_JSON_KEY", key)
            result[key] = value
        return result

    def invalid_number(value: str) -> object:
        raise SourceBlocked("NONFINITE_JSON_NUMBER", value)

    def finite_number(value: str) -> Decimal:
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise SourceBlocked("INVALID_JSON_NUMBER") from exc
        require(len(value) <= 64 and abs(number.adjusted()) <= 60, "JSON_NUMBER_RANGE")
        return number

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_number,
                          parse_float=finite_number)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, SourceBlocked):
            raise
        raise SourceBlocked("MALFORMED_JSON") from exc


class PublicAdapter:
    """Transport boundary and rate state owned by a single serial scanner."""

    def __init__(self, transport: Transport, clock: Clock, policy: Policy) -> None:
        self.transport = transport
        self.clock = clock
        self.policy = policy
        self.limits = RateLimits(policy)

    def session(self, started: Sample, audit: Callable[..., int]) -> "PublicSession":
        return PublicSession(self, started, audit)


class PublicSession:
    def __init__(self, adapter: PublicAdapter, started: Sample, audit: Callable[..., int]) -> None:
        self.adapter = adapter
        self.started = started
        self.last = started
        self.audit = audit
        self.count = 0
        self.weight = 0

    def get(self, method: str, route: str, params: Params) -> Receipt:
        adapter, policy = self.adapter, self.adapter.policy
        limits = adapter.limits
        params = dict(params)
        weight = request_weight(method, route, params)
        for attempt in (1, 2):
            sent = adapter.clock.sample()
            check_elapsed(self.started, sent, policy)
            check_elapsed(self.last, sent, policy)
            if limits.halted:
                raise SourceBlocked(limits.halted)
            require(limits.cooldown_until is None or sent.mono_ms >= limits.cooldown_until, "RETRY_AFTER_ACTIVE")
            remaining = policy.scan_timeout_ms - (sent.mono_ms - self.started.mono_ms)
            require(remaining > 0, "SCAN_DEADLINE")
            require(self.count + 1 <= policy.max_requests and self.weight + weight <= policy.max_weight,
                    "LOCAL_SCAN_BUDGET")
            limits.charge(route, weight, sent.mono_ms)
            self.count += 1
            self.weight += weight
            timeout = min(remaining, policy.request_timeout_ms)
            try:
                reply = adapter.transport.get(route, params.copy(), timeout)
            except OSError as exc:
                received = adapter.clock.sample()
                tls = isinstance(exc, ssl.SSLError)
                transient = isinstance(exc, (TimeoutError, ConnectionResetError, ConnectionAbortedError))
                code = ("TLS_VERIFICATION_FAILED" if tls else
                        "TRANSIENT_TRANSPORT_FAILURE" if transient else "TRANSPORT_UNAVAILABLE")
                self.audit(route, params, sent, received, None, {}, None, code)
                if tls:
                    limits.halted = code
                if tls or not transient or attempt == 2:
                    raise SourceBlocked(code) from exc
                check_elapsed(sent, received, policy)
                self.last = received
                continue

            received = adapter.clock.sample()
            headers = {key.lower(): value for key, value in reply.headers.items()
                       if key.lower() in ("content-type", "date", "retry-after") or WEIGHT_HEADER.fullmatch(key)}
            seq = self.audit(route, params, sent, received, reply.status, headers, reply.body, None)
            limits.observe(route, headers, received.mono_ms)
            if reply.status == 429:
                limits.cooldown_until = received.mono_ms + retry_after_ms(headers, received, policy.fallback_429_ms)
                raise SourceBlocked("HTTP_429")
            if reply.status in (418, 403, 451):
                limits.halted = f"HTTP_{reply.status}"
                raise SourceBlocked(limits.halted)
            # Recognize explicit venue restrictions even if a fixture wraps them in an unexpected HTTP status.
            if len(reply.body) <= policy.max_body_bytes and re.search(
                rb"(restricted location|restricted jurisdiction|region restriction|country restriction|"
                rb"service unavailable from your location|not available in your (country|region))", reply.body, re.I,
            ):
                limits.halted = "VENUE_RESTRICTED"
                raise SourceBlocked(limits.halted)
            check_elapsed(sent, received, policy)
            self.last = received
            require(received.mono_ms - sent.mono_ms <= timeout, "REQUEST_DEADLINE")
            require(len(reply.body) <= policy.max_body_bytes, "RESPONSE_TOO_LARGE")
            if reply.status in (500, 502, 503, 504) and attempt == 1:
                continue
            require(reply.status == 200, f"HTTP_{reply.status}")
            return Receipt(seq, sent, received, json_body(reply.body))
        raise AssertionError("retry loop exhausted")
