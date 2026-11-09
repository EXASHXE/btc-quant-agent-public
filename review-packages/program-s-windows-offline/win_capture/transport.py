"""Strict stdlib-only allowlisted HTTPS transport for Windows capture (retries=0)."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import math
import socket
import ssl
import threading
from typing import Any
from urllib.parse import urlencode

ALLOWED_HOST = "fapi.binance.com"
ALLOWED_ROUTES = frozenset({"/fapi/v1/time", "/fapi/v1/exchangeInfo", "/fapi/v1/klines"})
RESPONSE_BYTES_MAX = 2_097_152


class CaptureError(ValueError):
    """Fail-closed capture/validation error."""

    def __init__(self, message: str, status: str = "WIN_CAPTURE_BLOCKED"):
        super().__init__(message)
        self.status = status


def _reject_constant(token: str) -> Any:
    raise CaptureError(f"WIN_JSON_NONFINITE:{token}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise CaptureError(f"WIN_JSON_DUPLICATE_KEY:{k}")
        if isinstance(v, float) and not math.isfinite(v):
            raise CaptureError("WIN_JSON_NONFINITE_FLOAT")
        out[k] = v
    return out


def strict_json(raw: bytes) -> Any:
    """Parse strict UTF-8 JSON without duplicate keys, NaN/Infinity, or trailing tokens."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CaptureError("WIN_JSON_UTF8_INVALID") from exc
    wrapped = '{"response":' + text + "}"
    parsed = json.loads(
        wrapped,
        parse_constant=_reject_constant,
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(parsed, dict) or set(parsed) != {"response"}:
        raise CaptureError("WIN_JSON_TRAILING_OR_INVALID")
    return parsed["response"]


class _PinnedLoopbackHTTPSConnection(http.client.HTTPSConnection):
    """Connects to 127.0.0.1:<port> while enforcing TLS SNI + hostname verification for ALLOWED_HOST."""

    def __init__(self, connect_host: str, port: int, *, context: ssl.SSLContext, timeout: float, sni: str):
        super().__init__(sni, port=port, timeout=timeout, context=context)
        self._connect_host = connect_host
        self._connect_port = port
        self._sni = sni

    def connect(self) -> None:
        raw_sock = socket.create_connection((self._connect_host, self._connect_port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw_sock, server_hostname=self._sni)
        except Exception:
            raw_sock.close()
            raise


class WindowsHttpsTransport:
    """Read-only GET transport: strict allowlist, CERT_REQUIRED, zero retries."""

    def __init__(
        self, *, qa: dict[str, Any] | None = None, cafile: str | None = None, proxy=None, admission=None
    ):
        self.qa = qa
        self.proxy = proxy
        self.admission = admission
        if qa is None and (not proxy or proxy.get("host") != "127.0.0.1" or admission is None):
            raise CaptureError("WIN_PRODUCTION_ACCESS_AND_LOCAL_CONNECT_REQUIRED")
        if qa is not None:
            host = str(qa["host"])
            if not ipaddress.ip_address(host).is_loopback:
                raise CaptureError("WIN_QA_LOOPBACK_ONLY")
            self.connect_host = host
            self.connect_port = int(qa["port"])
            ca = str(qa["cafile"])
        else:
            self.connect_host = ALLOWED_HOST
            self.connect_port = 443
            ca = cafile
        ctx = ssl.create_default_context(cafile=ca)
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self.ssl_context = ctx

    def get(
        self,
        route: str,
        params: dict[str, Any],
        timeout_seconds: float,
        clock_monitor: Any,
    ) -> dict[str, Any]:
        if route not in ALLOWED_ROUTES:
            raise CaptureError(f"WIN_ROUTE_NOT_ALLOWLISTED:{route}")
        if timeout_seconds <= 0:
            raise CaptureError("WIN_REQUEST_DEADLINE_EXPIRED")

        if self.qa is None:
            self.admission.check(route, params)
            remaining = (
                self.admission.grant["not_after_qpc_ms"] - self.admission.clock.sample()["qpc_after_ms"]
            ) / 1000
            if remaining <= 0.3:
                raise CaptureError("OWNER_WINDOW_TOO_SHORT")
            timeout_seconds = min(timeout_seconds, remaining - 0.2)
        query = urlencode(sorted(params.items())) if params else ""
        path = f"{route}?{query}" if query else route
        req_sample = clock_monitor.sample()

        conn = (
            _PinnedLoopbackHTTPSConnection(
                self.connect_host,
                self.connect_port,
                context=self.ssl_context,
                timeout=float(timeout_seconds),
                sni=ALLOWED_HOST,
            )
            if self.qa is not None and not self.qa.get("connect_tunnel")
            else http.client.HTTPSConnection(
                self.qa["host"] if self.qa else self.proxy["host"],
                self.qa["port"] if self.qa else self.proxy["port"],
                timeout=float(timeout_seconds),
                context=self.ssl_context,
            )
        )
        if self.qa is None or self.qa.get("connect_tunnel"):
            conn.set_tunnel(ALLOWED_HOST, 443)

        live_socket = [None]
        expired = threading.Event()

        def hard_stop():
            expired.set()
            sock = live_socket[0] or conn.sock
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            conn.close()

        watchdog = threading.Timer(float(timeout_seconds), hard_stop)
        watchdog.start()
        try:
            conn.connect()
            live_socket[0] = conn.sock
            if expired.is_set():
                hard_stop()
                raise CaptureError("WIN_ABSOLUTE_REQUEST_DEADLINE")
            certificate_sha256 = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
            conn.request(
                "GET",
                path,
                headers={"Host": ALLOWED_HOST, "Accept": "application/json", "Connection": "close"},
            )
            resp = conn.getresponse()
            raw = resp.read(RESPONSE_BYTES_MAX + 1)
            if expired.is_set():
                raise CaptureError("WIN_ABSOLUTE_REQUEST_DEADLINE")
            recv_sample = clock_monitor.sample()
            status = int(resp.status)
            headers = {k.lower(): v for k, v in resp.getheaders()}
        finally:
            watchdog.cancel()
            conn.close()
            watchdog.join()

        complete = len(raw) <= RESPONSE_BYTES_MAX
        if not complete:
            raw = raw[:RESPONSE_BYTES_MAX]

        return {
            "host": ALLOWED_HOST,
            "route": route,
            "params": dict(params),
            "path": path,
            "status": status,
            "headers": headers,
            "raw_bytes": raw,
            "response_complete": complete,
            "body_sha256": hashlib.sha256(raw).hexdigest(),
            "request_sample": req_sample,
            "receive_sample": recv_sample,
            "tls": {
                "chain": "CERT_REQUIRED",
                "hostname_verified": True,
                "sni": ALLOWED_HOST,
                "qa_loopback": self.qa is not None,
                "certificate_sha256": certificate_sha256,
                "proxy": (
                    {"host": self.proxy["host"], "port": self.proxy["port"]}
                    if self.proxy
                    else (
                        {"host": self.qa["host"], "port": self.qa["port"]}
                        if self.qa and self.qa.get("connect_tunnel")
                        else None
                    )
                ),
                "method": "CONNECT" if self.qa is None or self.qa.get("connect_tunnel") else "QA_PINNED_TLS",
            },
        }
