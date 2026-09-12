from __future__ import annotations

import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .binance import classify_public_error
from .rest import BoundedRequester, RequestPolicy, shared_coordinator

ENDPOINTS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("ping", "/fapi/v1/ping", {}),
    ("premium_index", "/fapi/v1/premiumIndex", {"symbol": "BTCUSDT"}),
    ("open_interest", "/fapi/v1/openInterest", {"symbol": "BTCUSDT"}),
    (
        "open_interest_history",
        "/futures/data/openInterestHist",
        {"symbol": "BTCUSDT", "period": "1h", "limit": "2"},
    ),
    (
        "taker_ratio",
        "/futures/data/takerlongshortRatio",
        {"symbol": "BTCUSDT", "period": "15m", "limit": "1"},
    ),
    (
        "global_long_short",
        "/futures/data/globalLongShortAccountRatio",
        {"symbol": "BTCUSDT", "period": "1h", "limit": "1"},
    ),
    (
        "basis",
        "/futures/data/basis",
        {
            "pair": "BTCUSDT",
            "contractType": "PERPETUAL",
            "period": "5m",
            "limit": "1",
        },
    ),
)


def proxy_summary(environ: dict[str, str] | None = None) -> dict[str, Any]:
    values = environ or dict(os.environ)
    raw = next(
        (
            values.get(name)
            for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")
            if values.get(name)
        ),
        None,
    )
    if not raw:
        return {"configured": False, "scheme": None, "host": None, "credentials": False}
    parsed = urllib.parse.urlsplit(raw)
    host = parsed.hostname or "INVALID"
    safe_host = host if host in {"localhost", "127.0.0.1", "::1"} else "REDACTED_HOST"
    return {
        "configured": True,
        "scheme": parsed.scheme or "UNKNOWN",
        "host": safe_host,
        "port_configured": parsed.port is not None,
        "credentials": parsed.username is not None or parsed.password is not None,
    }


def _classify(exc: BaseException) -> str:
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, socket.gaierror):
        return "DNS_ERROR"
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "TIMEOUT"
    if isinstance(reason, ssl.SSLError):
        return "TLS_ERROR"
    if isinstance(exc, urllib.error.HTTPError):
        return "HTTP_ERROR"
    if isinstance(reason, OSError) and getattr(reason, "errno", None) in {51, 65, 101, 113}:
        return "NETWORK_UNREACHABLE"
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError, ValueError)):
        return "PARSE_ERROR"
    return "NETWORK_UNREACHABLE"


def diagnose_binance_network(
    *, base_url: str = "https://fapi.binance.com", timeout: float = 10.0
) -> dict[str, Any]:
    started = int(time.time() * 1_000)
    origin = urllib.parse.urlsplit(base_url)
    host = origin.hostname or "fapi.binance.com"
    requester = BoundedRequester(RequestPolicy(timeout, timeout, 1, 0, 0, 0.05),
                                 shared_coordinator(f"{origin.scheme.lower()}://{origin.netloc.lower()}"))
    try:
        addresses = requester.run(lambda: sorted({row[4][0] for row in socket.getaddrinfo(host, 443)}), retryable=lambda _: False)
        dns = {"status": "OK", "address_count": len(addresses)}
    except (socket.gaierror, TimeoutError) as exc:
        dns = {"status": _classify(exc), "error_type": type(exc).__name__}
    endpoints: dict[str, Any] = {}
    for name, path, params in ENDPOINTS:
        query = urllib.parse.urlencode(params)
        url = f"{base_url.rstrip('/')}{path}" + (f"?{query}" if query else "")
        endpoint_started = time.perf_counter()
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "btc-quant-agent-network-diagnostic/0.3.13"}
            )
            def fetch(request: urllib.request.Request = request) -> int:
                with urllib.request.urlopen(request, timeout=requester.transport_timeout) as response:
                    payload = response.read(2 * 1024 * 1024 + 1)
                    if len(payload) > 2 * 1024 * 1024:
                        raise ValueError("REST response exceeds size bound")
                    json.loads(payload.decode("utf-8"))
                    return int(response.status)
            status = requester.run(fetch, retryable=lambda exc: classify_public_error(exc)[1])
            endpoints[name] = {"status": "OK", "http_status": status,
                               "latency_ms": round((time.perf_counter() - endpoint_started) * 1_000, 3)}
        except Exception as exc:  # noqa: BLE001 - diagnostic maps every transport failure
            endpoints[name] = {
                "status": _classify(exc),
                "error_type": type(exc).__name__,
                "http_status": int(exc.code) if isinstance(exc, urllib.error.HTTPError) else None,
                "latency_ms": round((time.perf_counter() - endpoint_started) * 1_000, 3),
            }
    return {
        "checked_at_ms": started,
        "target_host": host,
        "dns": dns,
        "proxy": proxy_summary(),
        "endpoints": endpoints,
        "overall_status": "OK"
        if dns["status"] == "OK" and all(row["status"] == "OK" for row in endpoints.values())
        else "DEGRADED",
    }
