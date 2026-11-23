"""Offline Layer 2 PRIVATE_USER_DATA signed GET client, allowlist, fake signer, and disabled live stubs."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .models import (
    CONNECTION_MODE_FIXTURE,
    EVIDENCE_CLASS_SYNTHETIC,
    PRIVATE_CONNECTION_NOT_ACTIVATED,
    REDACTED,
    SEVEN_DAYS_MS,
    PermissionDeniedError,
    PrivateConnectionNotActivatedError,
    PrivateRequestRejectedError,
    RateLimitError,
    ResponseValidationError,
    TimestampSyncError,
    parse_symbol,
    raw_sha256,
    redact_mapping,
    redact_text,
)

ROUTE_ACCOUNT = "/fapi/v3/account"
ROUTE_POSITION_RISK = "/fapi/v3/positionRisk"
ROUTE_OPEN_ORDERS = "/fapi/v1/openOrders"
ROUTE_OPEN_ALGO_ORDERS = "/fapi/v1/openAlgoOrders"
ROUTE_USER_TRADES = "/fapi/v1/userTrades"
ROUTE_ALL_ORDERS = "/fapi/v1/allOrders"
ROUTE_ALL_ALGO_ORDERS = "/fapi/v1/allAlgoOrders"
ROUTE_INCOME = "/fapi/v1/income"

DEFAULT_RECV_WINDOW_MS = 5000
MAX_RECV_WINDOW_MS = 60_000
MAX_RAW_RESPONSE_BYTES = 4_000_000
MIN_VALID_EPOCH_MS = 1_500_000_000_000
MAX_VALID_EPOCH_MS = 4_102_444_800_000  # 2100-01-01 UTC

_ALGO_TYPE_RE = re.compile(r"^[A-Z0-9_]{2,40}$")
_INCOME_TYPE_RE = re.compile(r"^[A-Z0-9_]{2,40}$")
_RFC3986_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"
)

SECURITY_SENSITIVE_PARAMS = frozenset({"timestamp", "recvWindow", "signature"})


@dataclass(frozen=True)
class EndpointSpec:
    path: str
    method: str
    allowed_params: frozenset[str]
    required_params: frozenset[str]
    max_limit: int | None
    window_rule: str  # "NONE" | "LTE_7D" | "LT_7D" | "INCOME_3M"
    base_weight: int
    all_symbol_weight: int | None
    expected_json_type: type[Any]
    is_historical: bool


CORE_ALLOWLIST: dict[str, EndpointSpec] = {
    ROUTE_ACCOUNT: EndpointSpec(
        path=ROUTE_ACCOUNT,
        method="GET",
        allowed_params=frozenset({"recvWindow", "timestamp"}),
        required_params=frozenset(),
        max_limit=None,
        window_rule="NONE",
        base_weight=5,
        all_symbol_weight=5,
        expected_json_type=dict,
        is_historical=False,
    ),
    ROUTE_POSITION_RISK: EndpointSpec(
        path=ROUTE_POSITION_RISK,
        method="GET",
        allowed_params=frozenset({"symbol", "recvWindow", "timestamp"}),
        required_params=frozenset(),
        max_limit=None,
        window_rule="NONE",
        base_weight=5,
        all_symbol_weight=5,
        expected_json_type=list,
        is_historical=False,
    ),
    ROUTE_OPEN_ORDERS: EndpointSpec(
        path=ROUTE_OPEN_ORDERS,
        method="GET",
        allowed_params=frozenset({"symbol", "recvWindow", "timestamp"}),
        required_params=frozenset(),
        max_limit=None,
        window_rule="NONE",
        base_weight=1,
        all_symbol_weight=40,
        expected_json_type=list,
        is_historical=False,
    ),
    ROUTE_OPEN_ALGO_ORDERS: EndpointSpec(
        path=ROUTE_OPEN_ALGO_ORDERS,
        method="GET",
        allowed_params=frozenset({"algoType", "symbol", "algoId", "recvWindow", "timestamp"}),
        required_params=frozenset(),
        max_limit=None,
        window_rule="NONE",
        base_weight=1,
        all_symbol_weight=40,
        expected_json_type=list,
        is_historical=False,
    ),
    ROUTE_USER_TRADES: EndpointSpec(
        path=ROUTE_USER_TRADES,
        method="GET",
        allowed_params=frozenset(
            {"symbol", "orderId", "startTime", "endTime", "fromId", "limit", "recvWindow", "timestamp"}
        ),
        required_params=frozenset({"symbol"}),
        max_limit=1000,
        window_rule="LTE_7D",
        base_weight=5,
        all_symbol_weight=None,
        expected_json_type=list,
        is_historical=True,
    ),
    ROUTE_ALL_ORDERS: EndpointSpec(
        path=ROUTE_ALL_ORDERS,
        method="GET",
        allowed_params=frozenset(
            {"symbol", "orderId", "startTime", "endTime", "limit", "recvWindow", "timestamp"}
        ),
        required_params=frozenset({"symbol"}),
        max_limit=1000,
        window_rule="LT_7D",
        base_weight=5,
        all_symbol_weight=None,
        expected_json_type=list,
        is_historical=True,
    ),
    ROUTE_ALL_ALGO_ORDERS: EndpointSpec(
        path=ROUTE_ALL_ALGO_ORDERS,
        method="GET",
        allowed_params=frozenset(
            {"symbol", "algoId", "startTime", "endTime", "page", "limit", "recvWindow", "timestamp"}
        ),
        required_params=frozenset({"symbol"}),
        max_limit=100,
        window_rule="LT_7D",
        base_weight=5,
        all_symbol_weight=None,
        expected_json_type=list,
        is_historical=True,
    ),
    ROUTE_INCOME: EndpointSpec(
        path=ROUTE_INCOME,
        method="GET",
        allowed_params=frozenset(
            {"symbol", "incomeType", "startTime", "endTime", "page", "limit", "recvWindow", "timestamp"}
        ),
        required_params=frozenset(),
        max_limit=1000,
        window_rule="INCOME_3M",
        base_weight=30,
        all_symbol_weight=30,
        expected_json_type=list,
        is_historical=True,
    ),
}


def rfc3986_encode(raw: str) -> str:
    """Pure-Python RFC-3986 percent encoder (zero urllib/network dependency)."""
    out: list[str] = []
    for byte in raw.encode("utf-8"):
        ch = chr(byte)
        if ch in _RFC3986_UNRESERVED:
            out.append(ch)
        else:
            out.append(f"%{byte:02X}")
    return "".join(out)


def canonical_query_string(items: Sequence[tuple[str, str]]) -> str:
    """Serialize query parameters deterministically in sorted key order."""
    ordered = sorted(items, key=lambda pair: pair[0])
    return "&".join(f"{rfc3986_encode(k)}={rfc3986_encode(v)}" for k, v in ordered)


@dataclass(frozen=True)
class CredentialMaterial:
    """Narrow credential container whose repr/str never expose key or secret material."""

    key_id: str
    api_key: str
    secret: str
    mode: str = "FIXTURE_FAKE_ONLY"

    def __repr__(self) -> str:
        return (
            f"CredentialMaterial(key_id={self.key_id!r}, api_key={REDACTED!r}, "
            f"secret={REDACTED!r}, mode={self.mode!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@runtime_checkable
class CredentialProvider(Protocol):
    @property
    def provider_mode(self) -> str: ...

    def get_credentials(self) -> CredentialMaterial: ...


class FakeCredentialProvider:
    """Deterministic fake credential provider strictly for offline tests and demos."""

    provider_mode = "FIXTURE_FAKE_ONLY"

    def __init__(
        self,
        *,
        key_id: str = "b3-synthetic-test-key",
        api_key: str = "FAKE_B3_API_KEY_NOT_REAL_0001",
        secret: str = "FAKE_B3_API_SECRET_NOT_REAL_0001",
    ) -> None:
        if not api_key or not secret or not key_id:
            raise PrivateRequestRejectedError("INVALID_FAKE_CREDENTIALS")
        self._material = CredentialMaterial(
            key_id=key_id,
            api_key=api_key,
            secret=secret,
            mode=self.provider_mode,
        )

    def get_credentials(self) -> CredentialMaterial:
        return self._material

    def secret_tokens(self) -> tuple[str, ...]:
        return (self._material.api_key, self._material.secret)

    def __repr__(self) -> str:
        return f"FakeCredentialProvider(key_id={self._material.key_id!r}, mode={self.provider_mode!r})"


class DisabledProductionCredentialProvider:
    """Permanently disconnected production secret-store stub (reads no env/keyring/DPAPI/files)."""

    provider_mode = PRIVATE_CONNECTION_NOT_ACTIVATED

    def get_credentials(self) -> CredentialMaterial:
        raise PrivateConnectionNotActivatedError(
            "Production credential providers (keyring/DPAPI/env/files) are disabled in B3 offline build"
        )


@runtime_checkable
class RequestSigner(Protocol):
    @property
    def signer_mode(self) -> str: ...

    def sign(self, canonical_query: str, credentials: CredentialMaterial) -> str: ...


class DeterministicFakeSigner:
    """Deterministic local HMAC-SHA256 test signer.

    Does NOT claim that a real Binance key type or permission set has been selected.
    """

    signer_mode = "DETERMINISTIC_FAKE_HMAC_SHA256_TEST_ONLY"

    def sign(self, canonical_query: str, credentials: CredentialMaterial) -> str:
        if credentials.mode != "FIXTURE_FAKE_ONLY":
            raise PrivateConnectionNotActivatedError(
                "Fake signer only accepts FIXTURE_FAKE_ONLY test credentials"
            )
        return hmac.new(
            credentials.secret.encode("utf-8"),
            canonical_query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


@runtime_checkable
class TimeProvider(Protocol):
    def now_wall_ms(self) -> int: ...

    def now_monotonic_ms(self) -> int: ...

    def venue_offset_ms(self) -> int: ...

    def offset_uncertainty_ms(self) -> int: ...

    def resync_offset(self) -> int: ...


class DeterministicFakeClock:
    """Injected deterministic clock with venue time offset and bounded single-resync support."""

    def __init__(
        self,
        *,
        wall_ms: int = 1_735_691_520_000,
        monotonic_ms: int = 1_000_000,
        venue_offset_ms: int = 150,
        offset_uncertainty_ms: int = 10,
        resync_target_offset_ms: int | None = None,
    ) -> None:
        self._wall_ms = wall_ms
        self._monotonic_ms = monotonic_ms
        self._venue_offset_ms = venue_offset_ms
        self._offset_uncertainty_ms = offset_uncertainty_ms
        self._resync_target_offset_ms = (
            venue_offset_ms if resync_target_offset_ms is None else resync_target_offset_ms
        )
        self.resync_count = 0

    def advance(self, delta_ms: int) -> None:
        if delta_ms < 0:
            raise PrivateRequestRejectedError("CLOCK_REGRESSION")
        self._wall_ms += delta_ms
        self._monotonic_ms += delta_ms

    def now_wall_ms(self) -> int:
        return self._wall_ms

    def now_monotonic_ms(self) -> int:
        return self._monotonic_ms

    def venue_offset_ms(self) -> int:
        return self._venue_offset_ms

    def offset_uncertainty_ms(self) -> int:
        return self._offset_uncertainty_ms

    def venue_time_estimate_ms(self) -> int:
        return self._wall_ms + self._venue_offset_ms

    def resync_offset(self) -> int:
        self.resync_count += 1
        self._venue_offset_ms = self._resync_target_offset_ms
        return self._venue_offset_ms


@dataclass(frozen=True)
class SignedPrivateRequest:
    """Immutable signed GET request passed exclusively to an offline transport."""

    method: str
    path: str
    canonical_unsigned_query: str
    signed_query: str
    headers: dict[str, str]
    redacted_params: dict[str, Any]
    weight_cost: int
    signer_mode: str

    def redacted_summary(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "params": self.redacted_params,
            "headers": {"X-MBX-APIKEY": REDACTED},
            "signed_query": REDACTED,
            "weight_cost": self.weight_cost,
            "signer_mode": self.signer_mode,
        }

    def __repr__(self) -> str:
        return (
            f"SignedPrivateRequest(method={self.method!r}, path={self.path!r}, "
            f"signed_query={REDACTED!r}, headers={{'X-MBX-APIKEY': {REDACTED!r}}})"
        )


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    raw_body: bytes
    headers: dict[str, str] = field(default_factory=dict)
    source_identity: str = "OFFLINE_FIXTURE_TRANSPORT_V1"


@runtime_checkable
class OfflineTransport(Protocol):
    @property
    def transport_mode(self) -> str: ...

    def send(self, request: SignedPrivateRequest) -> TransportResponse: ...


class DisabledLiveHttpTransport:
    """Hard-disabled live HTTP transport stub; zero socket/HTTP capability."""

    transport_mode = PRIVATE_CONNECTION_NOT_ACTIVATED

    def send(self, request: SignedPrivateRequest) -> TransportResponse:
        raise PrivateConnectionNotActivatedError(
            "Live HTTP transport is absent and disabled in B3 offline build"
        )


FixtureHandler = Callable[[SignedPrivateRequest], TransportResponse]


class OfflineFixtureTransport:
    """In-memory deterministic offline fixture transport recording redacted call logs."""

    transport_mode = CONNECTION_MODE_FIXTURE

    def __init__(
        self,
        routes: Mapping[str, Any] | None = None,
        *,
        handler: FixtureHandler | None = None,
        clock: DeterministicFakeClock | None = None,
        latency_ms: int = 12,
        source_identity: str = "OFFLINE_FIXTURE_TRANSPORT_V1",
    ) -> None:
        self._routes: dict[str, Any] = dict(routes or {})
        self._handler = handler
        self._clock = clock
        self._latency_ms = latency_ms
        self.source_identity = source_identity
        self.call_count = 0
        self.redacted_history: list[dict[str, Any]] = []
        self.observed_requests: list[SignedPrivateRequest] = []

    def send(self, request: SignedPrivateRequest) -> TransportResponse:
        # Defense-in-depth: even the offline transport refuses non-GET or unlisted paths.
        if request.method != "GET" or request.path not in CORE_ALLOWLIST:
            raise PrivateRequestRejectedError("TRANSPORT_BOUNDARY_REJECTED", f"{request.method} {request.path}")
        self.call_count += 1
        self.observed_requests.append(request)
        self.redacted_history.append(request.redacted_summary())
        if self._clock is not None and self._latency_ms > 0:
            self._clock.advance(self._latency_ms)
        if self._handler is not None:
            return self._handler(request)
        if request.path not in self._routes:
            body = json.dumps({"code": -1000, "msg": "Fixture route not configured"}).encode("utf-8")
            return TransportResponse(status_code=404, raw_body=body, source_identity=self.source_identity)
        target = self._routes[request.path]
        if callable(target):
            result = target(request)
            if isinstance(result, TransportResponse):
                return result
            body = json.dumps(result, separators=(",", ":")).encode("utf-8")
            return TransportResponse(status_code=200, raw_body=body, source_identity=self.source_identity)
        if isinstance(target, TransportResponse):
            return target
        if isinstance(target, bytes):
            return TransportResponse(status_code=200, raw_body=target, source_identity=self.source_identity)
        body = json.dumps(target, separators=(",", ":")).encode("utf-8")
        return TransportResponse(status_code=200, raw_body=body, source_identity=self.source_identity)


@dataclass(frozen=True)
class EndpointCallReceipt:
    """Redacted per-call receipt capturing independent NON_ATOMIC timing and provenance."""

    endpoint: str
    symbol: str | None
    request_wall_ms: int
    receive_wall_ms: int
    request_monotonic_ms: int
    receive_monotonic_ms: int
    venue_time_estimate_ms: int
    offset_uncertainty_ms: int
    source_identity: str
    raw_sha256: str
    http_status: int
    weight_cost: int
    redacted_params: dict[str, Any]
    evidence_class: str = EVIDENCE_CLASS_SYNTHETIC
    connection_mode: str = CONNECTION_MODE_FIXTURE

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint,
            "symbol": self.symbol,
            "request_wall_ms": self.request_wall_ms,
            "receive_wall_ms": self.receive_wall_ms,
            "request_monotonic_ms": self.request_monotonic_ms,
            "receive_monotonic_ms": self.receive_monotonic_ms,
            "venue_time_estimate_ms": self.venue_time_estimate_ms,
            "offset_uncertainty_ms": self.offset_uncertainty_ms,
            "source_identity": self.source_identity,
            "raw_sha256": self.raw_sha256,
            "http_status": self.http_status,
            "weight_cost": self.weight_cost,
            "redacted_params": self.redacted_params,
            "evidence_class": self.evidence_class,
            "connection_mode": self.connection_mode,
        }


def _reject_non_finite_json(token: str) -> Any:
    raise ResponseValidationError("NON_FINITE_JSON_CONSTANT", token)


def _validate_exact_int_param(value: object, name: str, *, minimum: int, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise PrivateRequestRejectedError("INVALID_PARAM_TYPE", name)
    if value < minimum:
        raise PrivateRequestRejectedError("PARAM_BELOW_MIN", name)
    if maximum is not None and value > maximum:
        raise PrivateRequestRejectedError("PARAM_ABOVE_MAX", name)
    return value


def validate_and_extract_params(
    method: str,
    path: str,
    params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None,
    *,
    default_timestamp_ms: int,
    default_recv_window_ms: int,
) -> tuple[EndpointSpec, dict[str, Any], list[tuple[str, str]], int]:
    """Final request boundary validator. Must run BEFORE signing or invoking transport."""
    if not isinstance(method, str) or method != "GET":
        raise PrivateRequestRejectedError("METHOD_NOT_ALLOWED", str(method))
    if not isinstance(path, str) or path not in CORE_ALLOWLIST:
        raise PrivateRequestRejectedError("ENDPOINT_NOT_ALLOWLISTED", str(path))
    spec = CORE_ALLOWLIST[path]
    if spec.method != "GET":
        raise PrivateRequestRejectedError("METHOD_NOT_ALLOWED", path)

    # Extract items while catching duplicate keys (both sequence and mapping inputs).
    raw_items: list[tuple[str, Any]]
    if params is None:
        raw_items = []
    elif isinstance(params, Mapping):
        raw_items = [(str(k), v) for k, v in params.items()]
    elif isinstance(params, Sequence) and not isinstance(params, (str, bytes)):
        raw_items = []
        for entry in params:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise PrivateRequestRejectedError("MALFORMED_PARAM_PAIR")
            raw_items.append((str(entry[0]), entry[1]))
    else:
        raise PrivateRequestRejectedError("INVALID_PARAMS_CONTAINER")

    seen: set[str] = set()
    cleaned: dict[str, Any] = {}
    for key, val in raw_items:
        if key in seen:
            code = "DUPLICATE_SECURITY_PARAM" if key in SECURITY_SENSITIVE_PARAMS else "DUPLICATE_PARAM"
            raise PrivateRequestRejectedError(code, key)
        seen.add(key)
        if key == "signature":
            raise PrivateRequestRejectedError("CALLER_SIGNATURE_FORBIDDEN", key)
        if key not in spec.allowed_params:
            raise PrivateRequestRejectedError("UNEXPECTED_PARAM", key)
        if val is None:
            raise PrivateRequestRejectedError("NULL_PARAM_FORBIDDEN", key)
        cleaned[key] = val

    for req_key in spec.required_params:
        if req_key not in cleaned:
            raise PrivateRequestRejectedError("MISSING_REQUIRED_PARAM", req_key)

    # Inject timestamp and recvWindow if not caller-provided, then strictly validate both.
    ts_raw = cleaned.get("timestamp", default_timestamp_ms)
    ts_val = _validate_exact_int_param(ts_raw, "timestamp", minimum=MIN_VALID_EPOCH_MS, maximum=MAX_VALID_EPOCH_MS)
    rw_raw = cleaned.get("recvWindow", default_recv_window_ms)
    rw_val = _validate_exact_int_param(rw_raw, "recvWindow", minimum=1, maximum=MAX_RECV_WINDOW_MS)
    cleaned["timestamp"] = ts_val
    cleaned["recvWindow"] = rw_val

    # Validate endpoint-specific parameters.
    if "symbol" in cleaned:
        cleaned["symbol"] = parse_symbol(cleaned["symbol"], "symbol")
    if "algoType" in cleaned:
        if not isinstance(cleaned["algoType"], str) or not _ALGO_TYPE_RE.fullmatch(cleaned["algoType"]):
            raise PrivateRequestRejectedError("INVALID_ALGO_TYPE", "algoType")
    if "incomeType" in cleaned:
        if not isinstance(cleaned["incomeType"], str) or not _INCOME_TYPE_RE.fullmatch(cleaned["incomeType"]):
            raise PrivateRequestRejectedError("INVALID_INCOME_TYPE", "incomeType")
    if "limit" in cleaned:
        assert spec.max_limit is not None
        cleaned["limit"] = _validate_exact_int_param(cleaned["limit"], "limit", minimum=1, maximum=spec.max_limit)
    if "page" in cleaned:
        cleaned["page"] = _validate_exact_int_param(cleaned["page"], "page", minimum=1, maximum=100_000)
    for id_param in ("orderId", "algoId", "fromId"):
        if id_param in cleaned:
            cleaned[id_param] = _validate_exact_int_param(cleaned[id_param], id_param, minimum=0)

    start_ms: int | None = None
    end_ms: int | None = None
    if "startTime" in cleaned:
        start_ms = _validate_exact_int_param(
            cleaned["startTime"], "startTime", minimum=MIN_VALID_EPOCH_MS, maximum=MAX_VALID_EPOCH_MS
        )
        cleaned["startTime"] = start_ms
    if "endTime" in cleaned:
        end_ms = _validate_exact_int_param(
            cleaned["endTime"], "endTime", minimum=MIN_VALID_EPOCH_MS, maximum=MAX_VALID_EPOCH_MS
        )
        cleaned["endTime"] = end_ms

    if start_ms is not None and end_ms is not None:
        if end_ms < start_ms:
            raise PrivateRequestRejectedError("INVALID_TIME_WINDOW_ORDER", "endTime < startTime")
        span = end_ms - start_ms
        if spec.window_rule == "LTE_7D" and span > SEVEN_DAYS_MS:
            raise PrivateRequestRejectedError("TIME_WINDOW_EXCEEDS_7_DAYS", spec.path)
        if spec.window_rule == "LT_7D" and span >= SEVEN_DAYS_MS:
            raise PrivateRequestRejectedError("TIME_WINDOW_MUST_BE_UNDER_7_DAYS", spec.path)

    if path == ROUTE_USER_TRADES and "fromId" in cleaned and ("startTime" in cleaned or "endTime" in cleaned):
        raise PrivateRequestRejectedError("FROM_ID_CONFLICTS_WITH_TIME_WINDOW", spec.path)

    weight = spec.base_weight if ("symbol" in cleaned or spec.all_symbol_weight is None) else spec.all_symbol_weight
    query_pairs = [(k, str(v)) for k, v in cleaned.items()]
    return spec, cleaned, query_pairs, weight


class PrivateUserDataClient:
    """Offline GET-only Binance USD-M Futures PRIVATE_USER_DATA client.

    Restricted exclusively to an injected OfflineTransport and FakeCredentialProvider.
    No live HTTP, no DNS, no sockets, no real secret store, and no Layer 3 mutations.
    """

    def __init__(
        self,
        *,
        transport: OfflineTransport,
        credentials: CredentialProvider,
        signer: RequestSigner,
        clock: TimeProvider,
        recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
    ) -> None:
        if getattr(transport, "transport_mode", None) != CONNECTION_MODE_FIXTURE:
            raise PrivateConnectionNotActivatedError("Only offline fixture transport is permitted in B3")
        if getattr(credentials, "provider_mode", None) != "FIXTURE_FAKE_ONLY":
            raise PrivateConnectionNotActivatedError("Only FakeCredentialProvider is permitted in B3")
        _validate_exact_int_param(recv_window_ms, "recvWindow", minimum=1, maximum=MAX_RECV_WINDOW_MS)
        self._transport = transport
        self._credentials = credentials
        self._signer = signer
        self._clock = clock
        self._recv_window_ms = recv_window_ms
        self.total_weight_used = 0

    def _extra_secrets(self, creds: CredentialMaterial, signature: str = "", signed_query: str = "") -> tuple[str, ...]:
        tokens = [creds.api_key, creds.secret]
        if signature:
            tokens.append(signature)
        if signed_query:
            tokens.append(signed_query)
        return tuple(tokens)

    def request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = None,
    ) -> tuple[Any, EndpointCallReceipt]:
        """Validate, sign with fake test credentials, send over offline transport, and validate response."""
        return self._execute_with_bounded_resync(method, path, params, resync_attempted=False)

    def _execute_with_bounded_resync(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None,
        *,
        resync_attempted: bool,
    ) -> tuple[Any, EndpointCallReceipt]:
        req_wall = self._clock.now_wall_ms()
        req_mono = self._clock.now_monotonic_ms()
        venue_ts = req_wall + self._clock.venue_offset_ms()

        # FINAL REQUEST BOUNDARY: strictly enforced BEFORE reading credentials, signing, or transport.
        spec, cleaned, query_pairs, weight = validate_and_extract_params(
            method,
            path,
            params,
            default_timestamp_ms=venue_ts,
            default_recv_window_ms=self._recv_window_ms,
        )

        creds = self._credentials.get_credentials()
        if creds.mode != "FIXTURE_FAKE_ONLY":
            raise PrivateConnectionNotActivatedError("Non-fake credentials rejected")

        unsigned_query = canonical_query_string(query_pairs)
        signature = self._signer.sign(unsigned_query, creds)
        signed_query = f"{unsigned_query}&signature={signature}"
        secrets = self._extra_secrets(creds, signature, signed_query)

        redacted_params = redact_mapping(cleaned, extra_secrets=secrets)
        signed_req = SignedPrivateRequest(
            method=spec.method,
            path=spec.path,
            canonical_unsigned_query=unsigned_query,
            signed_query=signed_query,
            headers={"X-MBX-APIKEY": creds.api_key},
            redacted_params=redacted_params,
            weight_cost=weight,
            signer_mode=self._signer.signer_mode,
        )

        response = self._transport.send(signed_req)
        self.total_weight_used += weight
        recv_wall = self._clock.now_wall_ms()
        recv_mono = self._clock.now_monotonic_ms()
        venue_est = recv_wall + self._clock.venue_offset_ms()
        uncertainty = self._clock.offset_uncertainty_ms()

        if len(response.raw_body) > MAX_RAW_RESPONSE_BYTES:
            raise ResponseValidationError(
                "RESPONSE_TOO_LARGE",
                f"Endpoint {spec.path} exceeded {MAX_RAW_RESPONSE_BYTES} bytes",
                extra_secrets=secrets,
            )

        body_digest = raw_sha256(response.raw_body)
        parsed = self._decode_and_check_errors(
            spec=spec,
            response=response,
            secrets=secrets,
            resync_attempted=resync_attempted,
            method=method,
            path=path,
            params=params,
        )
        if isinstance(parsed, tuple):
            # Returned directly from bounded single retry after -1021 resync.
            return parsed

        if not isinstance(parsed, spec.expected_json_type):
            raise ResponseValidationError(
                "UNEXPECTED_RESPONSE_TYPE",
                f"{spec.path} expected {spec.expected_json_type.__name__}",
                extra_secrets=secrets,
            )

        receipt = EndpointCallReceipt(
            endpoint=spec.path,
            symbol=cleaned.get("symbol"),
            request_wall_ms=req_wall,
            receive_wall_ms=recv_wall,
            request_monotonic_ms=req_mono,
            receive_monotonic_ms=recv_mono,
            venue_time_estimate_ms=venue_est,
            offset_uncertainty_ms=uncertainty,
            source_identity=response.source_identity,
            raw_sha256=body_digest,
            http_status=response.status_code,
            weight_cost=weight,
            redacted_params=redacted_params,
        )
        return parsed, receipt

    def _decode_and_check_errors(
        self,
        *,
        spec: EndpointSpec,
        response: TransportResponse,
        secrets: tuple[str, ...],
        resync_attempted: bool,
        method: str,
        path: str,
        params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None,
    ) -> Any:
        try:
            text = response.raw_body.decode("utf-8")
            parsed = json.loads(text, parse_constant=_reject_non_finite_json)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResponseValidationError(
                "MALFORMED_JSON_RESPONSE",
                redact_text(f"{spec.path}: invalid JSON payload", secrets),
                extra_secrets=secrets,
            ) from exc

        error_code: int | None = None
        error_msg = ""
        if isinstance(parsed, dict) and "code" in parsed and isinstance(parsed["code"], int) and parsed["code"] < 0:
            error_code = parsed["code"]
            error_msg = str(parsed.get("msg", ""))

        # Permission denied: NEVER retry, NEVER widen permissions or fallback credentials.
        if response.status_code in (401, 403) or error_code in (-2014, -2015):
            raise PermissionDeniedError(
                "PERMISSION_DENIED_FAIL_CLOSED",
                f"{spec.path} status={response.status_code} code={error_code}",
                extra_secrets=secrets,
            )

        # Rate limits / IP ban: fail closed without unbounded retries.
        if response.status_code in (418, 429) or error_code == -1003:
            retry_after_raw = response.headers.get("Retry-After") or response.headers.get("retry-after")
            retry_after_ms: int | None = None
            if retry_after_raw is not None and retry_after_raw.isdigit():
                retry_after_ms = int(retry_after_raw) * 1000
            err_code_str = "IP_BANNED_418" if response.status_code == 418 else "RATE_LIMITED_429"
            raise RateLimitError(
                err_code_str,
                f"{spec.path} status={response.status_code} code={error_code}",
                retry_after_ms=retry_after_ms,
            )

        # Timestamp out of recvWindow (-1021): at most ONE bounded resync + retry.
        if error_code == -1021:
            if not resync_attempted:
                self._clock.resync_offset()
                # Strip any caller-supplied stale timestamp on the bounded retry so fresh offset applies.
                retry_params: dict[str, Any] | None = None
                if params is not None:
                    items = list(params.items()) if isinstance(params, Mapping) else list(params)
                    retry_params = {str(k): v for k, v in items if str(k) != "timestamp"}
                return self._execute_with_bounded_resync(method, path, retry_params, resync_attempted=True)
            raise TimestampSyncError(
                "TIMESTAMP_RESYNC_EXHAUSTED",
                f"{spec.path} remained out of sync after bounded single resync",
                extra_secrets=secrets,
            )

        if response.status_code != 200 or error_code is not None:
            raise ResponseValidationError(
                "ENDPOINT_ERROR_RESPONSE",
                f"{spec.path} status={response.status_code} code={error_code} msg={redact_text(error_msg, secrets)}",
                extra_secrets=secrets,
            )
        return parsed

    # Typed convenience wrappers for the 8 core allowlisted signed GET endpoints only.
    def get_account(self) -> tuple[dict[str, Any], EndpointCallReceipt]:
        data, receipt = self.request("GET", ROUTE_ACCOUNT)
        return data, receipt

    def get_position_risk(self, *, symbol: str | None = None) -> tuple[list[dict[str, Any]], EndpointCallReceipt]:
        params = {"symbol": symbol} if symbol is not None else None
        data, receipt = self.request("GET", ROUTE_POSITION_RISK, params)
        return data, receipt

    def get_open_orders(self, *, symbol: str | None = None) -> tuple[list[dict[str, Any]], EndpointCallReceipt]:
        params = {"symbol": symbol} if symbol is not None else None
        data, receipt = self.request("GET", ROUTE_OPEN_ORDERS, params)
        return data, receipt

    def get_open_algo_orders(
        self,
        *,
        symbol: str | None = None,
        algo_type: str | None = None,
        algo_id: int | None = None,
    ) -> tuple[list[dict[str, Any]], EndpointCallReceipt]:
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = symbol
        if algo_type is not None:
            params["algoType"] = algo_type
        if algo_id is not None:
            params["algoId"] = algo_id
        data, receipt = self.request("GET", ROUTE_OPEN_ALGO_ORDERS, params or None)
        return data, receipt

    def get_user_trades(
        self,
        *,
        symbol: str,
        order_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        from_id: int | None = None,
        limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], EndpointCallReceipt]:
        params: dict[str, Any] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if from_id is not None:
            params["fromId"] = from_id
        if limit is not None:
            params["limit"] = limit
        data, receipt = self.request("GET", ROUTE_USER_TRADES, params)
        return data, receipt

    def get_all_orders(
        self,
        *,
        symbol: str,
        order_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], EndpointCallReceipt]:
        params: dict[str, Any] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = order_id
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if limit is not None:
            params["limit"] = limit
        data, receipt = self.request("GET", ROUTE_ALL_ORDERS, params)
        return data, receipt

    def get_all_algo_orders(
        self,
        *,
        symbol: str,
        algo_id: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], EndpointCallReceipt]:
        params: dict[str, Any] = {"symbol": symbol}
        if algo_id is not None:
            params["algoId"] = algo_id
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if page is not None:
            params["page"] = page
        if limit is not None:
            params["limit"] = limit
        data, receipt = self.request("GET", ROUTE_ALL_ALGO_ORDERS, params)
        return data, receipt

    def get_income(
        self,
        *,
        symbol: str | None = None,
        income_type: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], EndpointCallReceipt]:
        params: dict[str, Any] = {}
        if symbol is not None:
            params["symbol"] = symbol
        if income_type is not None:
            params["incomeType"] = income_type
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        if page is not None:
            params["page"] = page
        if limit is not None:
            params["limit"] = limit
        data, receipt = self.request("GET", ROUTE_INCOME, params or None)
        return data, receipt
