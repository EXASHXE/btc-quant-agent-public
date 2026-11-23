"""Typed unsigned request boundary, strict JSON, and bounded loopback HTTPS."""

from __future__ import annotations

import hashlib
import http.client
import io
import ipaddress
import json
import re
import socket
import ssl
import time
import zlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Protocol
from urllib.parse import urlencode

from .clock import Sample
from .policy import FUNDING, SourceBlocked, request_weight, require

HOST = "fapi.binance.com"
PORT = 443
MAX_REQUEST_BYTES = 2048
Params = Mapping[str, str | int]
WEIGHT_HEADER = re.compile(r"x-mbx-used-weight-(\d{1,4}[smhd])")
WINDOW_MS = {"SECOND": 1_000, "MINUTE": 60_000, "HOUR": 3_600_000, "DAY": 86_400_000}
FIXTURE = "OFFLINE_FIXTURE_V2"
LOOPBACK = "LOOPBACK_HTTPS_QA_V2"
GENUINE = "GENUINE_PUBLIC_V2"


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
        require(self.host == HOST and type(self.port) is int and self.port == PORT, "ORIGIN_NOT_APPROVED")
        params = dict(self.params)
        if self.route == FUNDING and set(params) == {"symbol", "limit", "startTime", "endTime"}:
            start, end = params.pop("startTime"), params.pop("endTime")
            require(type(start) is int and type(end) is int and 0 < start <= end < 2**63
                    and end - start <= 7 * 86_400_000, "FUNDING_WINDOW_INVALID")
        weight = request_weight(self.method, self.route, params)
        query = urlencode(sorted(self.params.items()))
        target = self.route + ("?" + query if query else "")
        wire = (
            f"GET {target} HTTP/1.1\r\nHost: {HOST}\r\n"
            "Accept: application/json\r\nAccept-Encoding: gzip\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
        require(len(wire) <= MAX_REQUEST_BYTES, "REQUEST_TOO_LARGE")
        return weight, wire


@dataclass(frozen=True)
class Reply:
    status: int
    headers: Mapping[str, str]
    body: bytes
    wire_bytes: int | None = None
    # The encoded HTTP entity (chunk framing removed), retained for gzip and digest verification.
    encoded_body: bytes | None = None
    complete: bool = True
    issue: str | None = None
    tls: Mapping[str, str] | None = None


@dataclass(frozen=True)
class Receipt:
    seq: int
    sent: Sample
    received: Sample
    body: object


class WireFailure(SourceBlocked):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        super().__init__(code)
        self.retryable = retryable


class Transport(Protocol):
    @property
    def origin(self) -> str: ...

    def send(self, request: Request, timeout_ms: int) -> Reply: ...


def json_body(raw: bytes) -> object:
    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for name, value in pairs:
            require(name not in result, "DUPLICATE_JSON_KEY", name)
            result[name] = value
        return result

    def invalid(_: str) -> object:
        raise SourceBlocked("NONFINITE_JSON")

    def finite(value: str) -> Decimal:
        try:
            number = Decimal(value)
        except InvalidOperation as exc:
            raise SourceBlocked("INVALID_JSON_NUMBER") from exc
        require(len(value) <= 64 and abs(number.adjusted()) <= 60, "JSON_NUMBER_RANGE")
        return number

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid, parse_float=finite)
    except (ValueError, RecursionError) as exc:
        if isinstance(exc, SourceBlocked):
            raise
        raise SourceBlocked("MALFORMED_JSON") from exc


@dataclass(frozen=True)
class WireLimits:
    connect_ms: int = 600
    idle_ms: int = 400
    max_transfer_bytes: int = 4_200_000
    max_decoded_bytes: int = 4_000_000

    def __post_init__(self) -> None:
        if any(type(v) is not int or v <= 0 for v in vars(self).values()):
            raise ValueError("positive finite wire limits required")


@dataclass(frozen=True)
class LoopbackTarget:
    address: str
    port: int
    ca_file: Path

    def validate(self) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        try:
            address = ipaddress.ip_address(self.address)
        except ValueError as exc:
            raise SourceBlocked("LOOPBACK_NUMERIC_ADDRESS_REQUIRED") from exc
        require(address.is_loopback and "%" not in self.address and type(self.port) is int and 1 <= self.port <= 65535,
                "LOOPBACK_TARGET_REQUIRED")
        return address


def remaining(deadline: float) -> float:
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("public request deadline")
    return seconds


class BoundedRead(io.RawIOBase):
    """Enforce raw wire cap and absolute/idle deadlines even beneath buffered HTTP parsing."""

    def __init__(self, sock: ssl.SSLSocket, deadline: float, policy: WireLimits) -> None:
        super().__init__()
        self.sock = sock
        self.deadline = deadline
        self.policy = policy
        self.seen = 0

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:  # type: ignore[override]
        self.sock.settimeout(min(remaining(self.deadline), self.policy.idle_ms / 1000))
        room = self.policy.max_transfer_bytes - self.seen
        max_bytes = min(len(b), max(1, room))
        size = self.sock.recv_into(b, max_bytes)
        self.seen += size
        require(self.seen <= self.policy.max_transfer_bytes, "ENCODED_TRANSFER_TOO_LARGE")
        return size


@dataclass
class ResponseSocket:
    raw: BoundedRead

    def makefile(self, _mode: str) -> io.BufferedReader:
        return io.BufferedReader(self.raw)


def entity(response: http.client.HTTPResponse, limit: int, deadline: float) -> tuple[bytes, bytes | None]:
    encoding = response.getheader("Content-Encoding", "identity").lower()
    require(encoding in {"identity", "gzip"}, "UNSUPPORTED_CONTENT_ENCODING")
    require(not (response.chunked and response.getheader("Content-Length") is not None), "AMBIGUOUS_HTTP_LENGTH")
    transfer = response.getheaders()
    require(all(len(response.headers.get_all(name, [])) <= 1 for name in ("Content-Length", "Transfer-Encoding",
                                                                          "Content-Encoding", "Content-Type")),
            "AMBIGUOUS_HTTP_HEADERS")
    require(not any(key.lower() == "transfer-encoding" and value.lower() != "chunked" for key, value in transfer),
            "UNSUPPORTED_TRANSFER_ENCODING")
    size_header = response.getheader("Content-Length")
    if size_header is not None:
        require(re.fullmatch(r"[0-9]{1,12}", size_header) is not None, "INVALID_CONTENT_LENGTH")
    original_length = response.length
    encoded = bytearray()
    decoded = bytearray()
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS) if encoding == "gzip" else None
    while True:
        remaining(deadline)
        chunk = response.read1(8192)
        if not chunk:
            break
        try:
            if inflater is None:
                decoded.extend(chunk)
            else:
                encoded.extend(chunk)
                decoded.extend(inflater.decompress(chunk, limit - len(decoded) + 1))
                require(not inflater.unconsumed_tail, "DECODED_PAYLOAD_TOO_LARGE")
                require(not inflater.unused_data, "INVALID_GZIP_TRAILING_DATA")
        except zlib.error as exc:
            raise SourceBlocked("INVALID_GZIP") from exc
        require(len(decoded) <= limit, "DECODED_PAYLOAD_TOO_LARGE")
    if original_length is not None:
        require(response.length == 0, "TRUNCATED_HTTP_BODY")
    if inflater is not None:
        require(inflater.eof, "TRUNCATED_GZIP")
    return bytes(decoded), bytes(encoded) if inflater is not None else None


def audit_headers(headers: list[tuple[str, str]]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for key, value in headers:
        name = key.lower()
        if name in {"retry-after", "date", "content-type", "content-encoding", "location"}:
            if name == "retry-after" and name in selected:
                # Ambiguous cooldown input gets the conservative parser fallback.
                value = "INVALID_DUPLICATE"
            selected[name] = value
        elif WEIGHT_HEADER.fullmatch(name) and re.fullmatch(r"[0-9]{1,10}", value):
            selected[name] = str(max(int(value), int(selected.get(name, "0"))))
    return selected


@dataclass(frozen=True)
class HttpsTransport:
    """B1 runs the real TLS/HTTP implementation only against an explicitly pinned loopback peer."""

    target: LoopbackTarget
    limits: WireLimits = field(default_factory=WireLimits)
    origin: str = field(init=False, default=LOOPBACK)

    def send(self, request: Request, timeout_ms: int) -> Reply:
        _, request_bytes = request.validate()
        address = self.target.validate()
        require(type(timeout_ms) is int and timeout_ms > 0, "REQUEST_DEADLINE")
        deadline = time.monotonic() + timeout_ms / 1000
        connect_deadline = min(deadline, time.monotonic() + self.limits.connect_ms / 1000)
        family = socket.AF_INET if address.version == 4 else socket.AF_INET6
        try:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.hostname_checks_common_name = False
            context.load_verify_locations(cafile=str(self.target.ca_file))
            with socket.socket(family, socket.SOCK_STREAM) as conn:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                conn.settimeout(remaining(connect_deadline))
                conn.connect((str(address), self.target.port))
                conn.settimeout(remaining(connect_deadline))
                with context.wrap_socket(conn, server_hostname=HOST) as tls:
                    cert = tls.getpeercert(binary_form=True)
                    if cert is None:
                        raise SourceBlocked("TLS_CERTIFICATE_MISSING")
                    proof = {"peer": str(address), "sni": HOST, "protocol": tls.version() or "UNKNOWN",
                             "certificate_sha256": hashlib.sha256(cert).hexdigest(),
                             "verification": "CERT_REQUIRED_AND_HOSTNAME"}
                    tls.settimeout(min(remaining(deadline), self.limits.idle_ms / 1000))
                    tls.sendall(request_bytes)
                    raw = BoundedRead(tls, deadline, self.limits)
                    # HTTPResponse only calls makefile on its constructor's socket argument.
                    response = http.client.HTTPResponse(ResponseSocket(raw), method="GET")  # type: ignore[arg-type]
                    headers: dict[str, str] = {}
                    status: int | None = None
                    try:
                        response.begin()
                        status = response.status
                        headers = audit_headers(response.getheaders())
                        if 300 <= response.status <= 399 or response.status == 418:
                            return Reply(response.status, headers, b"", raw.seen, complete=False, tls=proof)
                        decoded, encoded = entity(response, self.limits.max_decoded_bytes, deadline)
                        return Reply(response.status, headers, decoded, raw.seen, encoded, tls=proof)
                    except (SourceBlocked, TimeoutError, http.client.HTTPException, OSError) as exc:
                        if status is None:
                            raise
                        issue = exc.code if isinstance(exc, SourceBlocked) else "HTTP_BODY_INCOMPLETE"
                        return Reply(status, headers, b"", raw.seen, complete=False, issue=issue, tls=proof)
                    finally:
                        response.close()
        except ssl.SSLError as exc:
            raise WireFailure("TLS_VERIFICATION_FAILED") from exc
        except (TimeoutError, ConnectionResetError, ConnectionAbortedError) as exc:
            raise WireFailure("TRANSIENT_WIRE_FAILURE", retryable=True) from exc
        except (OSError, http.client.HTTPException, ValueError) as exc:
            if isinstance(exc, SourceBlocked):
                raise
            raise WireFailure("HTTPS_TRANSPORT_FAILED") from exc
