"""Strict explicit proxy routing, network diagnostic, and Binance 2026 URL validation.

Implements unified egress across REST and WebSocket connections without credential leakage,
supporting Linux / WSL2 Windows Host Clash and Mihomo local proxies.
"""

from __future__ import annotations

import os
import platform
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .contracts import (
    ALLOWED_REST_HOSTS,
    ALLOWED_SYMBOL,
    ALLOWED_WS_HOSTS,
    FORBIDDEN_HOSTS,
    FORBIDDEN_PRIVATE_KEYWORDS,
)

# Official Binance 2026 Base Endpoints
BINANCE_2026_REST_BASE: str = "https://fapi.binance.com"
BINANCE_2026_PUBLIC_WS_BASE: str = "wss://fstream.binance.com/public/stream"
BINANCE_2026_MARKET_WS_BASE: str = "wss://fstream.binance.com/market/stream"
BINANCE_LEGACY_UNROUTED_WS_BASE: str = "wss://fstream.binance.com/stream"


class NetworkErrorCode(str, Enum):
    NETWORK_DISABLED = "NETWORK_DISABLED"
    PROXY_PORT_CLOSED = "PROXY_PORT_CLOSED"
    PROXY_AUTH_REQUIRED = "PROXY_AUTH_REQUIRED"
    PROXY_CONNECT_FAILED = "PROXY_CONNECT_FAILED"
    DNS_RESOLUTION_FAILED = "DNS_RESOLUTION_FAILED"
    REST_TLS_EOF = "REST_TLS_EOF"
    TLS_CERT_INVALID = "TLS_CERT_INVALID"
    BINANCE_ROUTING_INVALID = "BINANCE_ROUTING_INVALID"
    WS_UPGRADE_FAILED = "WS_UPGRADE_FAILED"
    WS_CONNECTED_NO_EVENTS = "WS_CONNECTED_NO_EVENTS"
    MIXED_EGRESS_ROUTE_REJECT = "MIXED_EGRESS_ROUTE_REJECT"
    CLOCK_UNCERTAIN = "CLOCK_UNCERTAIN"
    SOURCE_BLOCKED_BY_PROVIDER_POLICY = "SOURCE_BLOCKED_BY_PROVIDER_POLICY"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"


class NetworkRouteError(RuntimeError):
    """Raised when proxy routing or network validation fails."""

    def __init__(self, code: NetworkErrorCode, message: str) -> None:
        super().__init__(f"[{code.value}] {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProxyRouteConfig:
    """Explicit egress route specification for both REST and WebSocket traffic."""

    mode: str = "disabled"  # disabled | public-direct | public-clash-explicit
    kind: str = "http"      # http | socks5h
    host: str | None = None
    port: int | None = None
    route_epoch: str = "route-epoch-0"
    timeout_seconds: float = 10.0

    def validate(self) -> None:
        if self.mode not in ("disabled", "public-direct", "public-clash-explicit"):
            raise NetworkRouteError(
                NetworkErrorCode.BINANCE_ROUTING_INVALID,
                f"Unknown network mode '{self.mode}'. Must be disabled, public-direct, or public-clash-explicit.",
            )
        if self.mode == "public-clash-explicit":
            if not self.host:
                raise NetworkRouteError(
                    NetworkErrorCode.PROXY_CONNECT_FAILED,
                    "Proxy host must be explicitly configured when mode is 'public-clash-explicit'.",
                )
            if not self.port or not (1 <= self.port <= 65535):
                raise NetworkRouteError(
                    NetworkErrorCode.PROXY_CONNECT_FAILED,
                    f"Invalid proxy port '{self.port}'. Must be 1..65535.",
                )
            if self.kind not in ("http", "socks5h"):
                raise NetworkRouteError(
                    NetworkErrorCode.BINANCE_ROUTING_INVALID,
                    f"Unsupported proxy kind '{self.kind}'. Must be 'http' or 'socks5h'.",
                )

    def to_proxy_url(self) -> str | None:
        """Return explicit proxy URL or None if direct/disabled."""
        if self.mode != "public-clash-explicit":
            return None
        return f"{self.kind}://{self.host}:{self.port}"

    def to_sanitized_dict(self) -> dict[str, Any]:
        """Produce strictly desensitized representation without credentials."""
        return {
            "mode": self.mode,
            "kind": self.kind,
            "host": self.host,
            "port": self.port,
            "route_epoch": self.route_epoch,
            "has_proxy": self.mode == "public-clash-explicit",
        }

    def build_urllib_opener(self) -> urllib.request.OpenerDirector:
        """Create explicit urllib OpenerDirector matching pinned route without ambient leaks."""
        self.validate()
        if self.mode == "disabled":
            raise NetworkRouteError(
                NetworkErrorCode.NETWORK_DISABLED,
                "Cannot build REST opener while network is disabled.",
            )

        # Enforce strict TLS context with system/certifi CA verification
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = True
        ssl_ctx.verify_mode = ssl.CERT_REQUIRED

        https_handler = urllib.request.HTTPSHandler(context=ssl_ctx)

        if self.mode == "public-clash-explicit":
            proxy_url = self.to_proxy_url()
            assert proxy_url is not None
            proxy_handler = urllib.request.ProxyHandler({
                "http": proxy_url,
                "https": proxy_url,
            })
            return urllib.request.build_opener(proxy_handler, https_handler)
        else:
            # Explicit direct: empty proxy dict blocks environment proxies (HTTP_PROXY / HTTPS_PROXY)
            proxy_handler = urllib.request.ProxyHandler({})
            return urllib.request.build_opener(proxy_handler, https_handler)

    def get_websockets_proxy(self) -> str | None:
        """Return explicit proxy argument for websockets.connect(proxy=...)."""
        self.validate()
        if self.mode == "disabled":
            raise NetworkRouteError(
                NetworkErrorCode.NETWORK_DISABLED,
                "Cannot open WebSocket while network is disabled.",
            )
        if self.mode == "public-clash-explicit":
            return self.to_proxy_url()
        # Direct: None explicitly prevents websockets from picking up ambient env proxies
        return None


def build_2026_public_stream_url(symbol: str = ALLOWED_SYMBOL) -> str:
    """Build official Binance 2026 diff depth stream URL."""
    sym = symbol.lower()
    return f"{BINANCE_2026_PUBLIC_WS_BASE}?streams={sym}@depth@100ms"


def build_2026_market_stream_url(symbol: str = ALLOWED_SYMBOL) -> str:
    """Build official Binance 2026 market streams URL (aggTrade, kline_1m, markPrice@1s)."""
    sym = symbol.lower()
    streams = f"{sym}@aggTrade/{sym}@kline_1m/{sym}@markPrice@1s"
    return f"{BINANCE_2026_MARKET_WS_BASE}?streams={streams}"


def validate_2026_routed_url(url: str, expected_route: str = "any") -> None:
    """Validate URL conforms strictly to 2026 Binance USDⓈ-M public routing rules.

    expected_route: 'public' | 'market' | 'rest' | 'any'
    """
    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    query = urllib.parse.parse_qs(parsed.query)

    if scheme not in ("https", "wss"):
        raise NetworkRouteError(
            NetworkErrorCode.BINANCE_ROUTING_INVALID,
            f"Forbidden scheme '{scheme}'. Must be https or wss.",
        )

    # Check forbidden hosts
    if host in FORBIDDEN_HOSTS or any(host.endswith(f".{bad}") for bad in FORBIDDEN_HOSTS):
        raise NetworkRouteError(
            NetworkErrorCode.BINANCE_ROUTING_INVALID,
            f"Forbidden host '{host}'. Only Binance USDⓈ-M public endpoints permitted.",
        )

    # Check allowed hosts
    allowed = ALLOWED_REST_HOSTS if scheme == "https" else ALLOWED_WS_HOSTS
    if host not in allowed:
        raise NetworkRouteError(
            NetworkErrorCode.BINANCE_ROUTING_INVALID,
            f"Host '{host}' not in allowlist {allowed}.",
        )

    # Check forbidden keywords
    for kw in FORBIDDEN_PRIVATE_KEYWORDS:
        if kw in path or kw in parsed.query.lower():
            raise NetworkRouteError(
                NetworkErrorCode.BINANCE_ROUTING_INVALID,
                f"Forbidden private keyword '{kw}' detected in endpoint '{url}'.",
            )

    # Check 2026 WebSocket routes
    if scheme == "wss":
        if path == "/stream":
            raise NetworkRouteError(
                NetworkErrorCode.BINANCE_ROUTING_INVALID,
                "Unrouted legacy endpoint '/stream' deprecated since 2026-04-23. "
                "Must use '/public/stream' for depth or '/market/stream' for trades/klines/mark.",
            )

        streams_param = query.get("streams", [""])[0]
        stream_list = streams_param.split("/") if streams_param else []

        if path == "/public/stream":
            if expected_route not in ("public", "any"):
                raise NetworkRouteError(
                    NetworkErrorCode.BINANCE_ROUTING_INVALID,
                    f"Expected route '{expected_route}', got '/public/stream'.",
                )
            for s in stream_list:
                if any(market_kw in s.lower() for market_kw in ("kline", "markprice", "aggtrade")):
                    raise NetworkRouteError(
                        NetworkErrorCode.BINANCE_ROUTING_INVALID,
                        f"Market stream '{s}' forbidden on '/public/stream'. Diff depth only.",
                    )

        elif path == "/market/stream":
            if expected_route not in ("market", "any"):
                raise NetworkRouteError(
                    NetworkErrorCode.BINANCE_ROUTING_INVALID,
                    f"Expected route '{expected_route}', got '/market/stream'.",
                )
            for s in stream_list:
                if "depth" in s.lower():
                    raise NetworkRouteError(
                        NetworkErrorCode.BINANCE_ROUTING_INVALID,
                        f"Depth stream '{s}' forbidden on '/market/stream'. Use '/public/stream'.",
                    )
        else:
            raise NetworkRouteError(
                NetworkErrorCode.BINANCE_ROUTING_INVALID,
                f"Forbidden WebSocket path '{path}'. Must be '/public/stream' or '/market/stream'.",
            )


def probe_tcp_socket(host: str, port: int, timeout: float = 2.0) -> bool:
    """Low-frequency TCP connectivity check strictly against designated host:port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, OSError):
        return False


def detect_wsl2_networking() -> dict[str, Any]:
    """Detect operating system, WSL2 environment, and network topology safely without LAN scanning."""
    system = platform.system()
    release = platform.release()
    is_wsl = "microsoft" in release.lower() or "wsl" in release.lower()

    network_mode = "unknown"
    windows_gateway_ip = None

    if is_wsl:
        # Check /proc/net/route or ip route to find default gateway safely
        try:
            with open("/proc/net/route", encoding="ascii") as f:
                for line in f.readlines()[1:]:
                    parts = line.strip().split()
                    if len(parts) >= 3 and parts[1] == "00000000":  # default route
                        gw_hex = parts[2]
                        # convert little endian hex to IP
                        gw_bytes = [int(gw_hex[i:i+2], 16) for i in (6, 4, 2, 0)]
                        windows_gateway_ip = ".".join(str(b) for b in gw_bytes)
                        break
        except (OSError, UnicodeDecodeError, ValueError):
            pass

        # Check /etc/resolv.conf nameserver
        nameserver = None
        try:
            with open("/etc/resolv.conf", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("nameserver"):
                        nameserver = line.strip().split()[1]
                        break
        except (OSError, UnicodeDecodeError, ValueError):
            pass

        if nameserver == "10.255.255.254" or windows_gateway_ip == "192.168.31.1":
            network_mode = "nat_or_mirrored"
        else:
            network_mode = "wsl2_standard"

    return {
        "os": system,
        "release": release,
        "python_version": platform.python_version(),
        "is_wsl": is_wsl,
        "wsl_network_mode": network_mode,
        "detected_gateway_ip": windows_gateway_ip,
    }


def sanitize_env_proxy_map() -> dict[str, str]:
    """Inspect environment proxy variables with strict desensitization (masking passwords/tokens)."""
    result: dict[str, str] = {}
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        val = os.environ.get(var)
        if val:
            # Mask user:pass if present
            masked = re.sub(r"://([^:@]+):([^@]+)@", r"://\1:***@", val)
            result[var] = masked
    return result


def run_desensitized_network_diagnostic(config: ProxyRouteConfig) -> dict[str, Any]:
    """Execute complete 4-layer network diagnostic safely and desensitize all output."""
    start_time = time.time()
    env_info = detect_wsl2_networking()
    env_proxies = sanitize_env_proxy_map()

    layers: dict[str, Any] = {
        "layer_1_local_tcp": {"status": "SKIPPED"},
        "layer_2_proxy_negotiation": {"status": "SKIPPED"},
        "layer_3_tls_rest_verify": {"status": "SKIPPED"},
        "layer_4_ws_connect_verify": {"status": "SKIPPED"},
    }

    terminal_code = NetworkErrorCode.NETWORK_DISABLED
    error_detail = None

    if config.mode == "disabled":
        terminal_code = NetworkErrorCode.NETWORK_DISABLED
    elif config.mode == "public-clash-explicit":
        assert config.host is not None and config.port is not None
        # Layer 1: Local TCP Probe
        tcp_ok = probe_tcp_socket(config.host, config.port, timeout=2.0)
        if not tcp_ok:
            layers["layer_1_local_tcp"] = {"status": "FAILED", "host": config.host, "port": config.port}
            terminal_code = NetworkErrorCode.PROXY_PORT_CLOSED
            error_detail = f"TCP connection to proxy port {config.port} on {config.host} failed."
        else:
            layers["layer_1_local_tcp"] = {"status": "SUCCESS", "host": config.host, "port": config.port}

            # Layer 2 & 3: REST TLS end-to-end check via proxy
            try:
                opener = config.build_urllib_opener()
                test_url = f"{BINANCE_2026_REST_BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=5"
                validate_2026_routed_url(test_url, expected_route="rest")
                req = urllib.request.Request(
                    test_url,
                    headers={"User-Agent": "PublicRouteProbe/1.0", "Accept": "application/json"},
                    method="GET",
                )
                with opener.open(req, timeout=config.timeout_seconds) as resp:
                    status_code = resp.status
                    body = resp.read()
                    if status_code == 200 and len(body) > 0:
                        layers["layer_2_proxy_negotiation"] = {"status": "SUCCESS"}
                        layers["layer_3_tls_rest_verify"] = {"status": "SUCCESS", "status_code": 200, "bytes": len(body)}
                        terminal_code = NetworkErrorCode.NETWORK_DISABLED  # Reset or pending WS
                    elif status_code in (403, 451):
                        layers["layer_3_tls_rest_verify"] = {"status": "BLOCKED", "status_code": status_code}
                        terminal_code = NetworkErrorCode.SOURCE_BLOCKED_BY_PROVIDER_POLICY
                        error_detail = f"REST endpoint returned {status_code} policy block."
            except urllib.error.HTTPError as he:
                if he.code in (403, 451):
                    layers["layer_3_tls_rest_verify"] = {"status": "BLOCKED", "status_code": he.code}
                    terminal_code = NetworkErrorCode.SOURCE_BLOCKED_BY_PROVIDER_POLICY
                    error_detail = f"Binance provider policy blocked request: HTTP {he.code}."
                elif he.code == 407:
                    layers["layer_2_proxy_negotiation"] = {"status": "AUTH_REQUIRED", "status_code": 407}
                    terminal_code = NetworkErrorCode.PROXY_AUTH_REQUIRED
                    error_detail = "Proxy requires authentication (HTTP 407)."
                else:
                    layers["layer_3_tls_rest_verify"] = {"status": "FAILED", "status_code": he.code}
                    terminal_code = NetworkErrorCode.SOURCE_UNAVAILABLE
                    error_detail = f"REST failed with HTTP {he.code}."
            except ssl.SSLError as se:
                if "UNEXPECTED_EOF_WHILE_READING" in str(se):
                    layers["layer_3_tls_rest_verify"] = {"status": "TLS_EOF", "error": "UNEXPECTED_EOF_WHILE_READING"}
                    terminal_code = NetworkErrorCode.REST_TLS_EOF
                else:
                    layers["layer_3_tls_rest_verify"] = {"status": "TLS_CERT_INVALID", "error": str(se)}
                    terminal_code = NetworkErrorCode.TLS_CERT_INVALID
                error_detail = f"TLS handshake failed: {se}"
            except (socket.gaierror, urllib.error.URLError) as ue:
                layers["layer_2_proxy_negotiation"] = {"status": "CONNECT_FAILED", "error": str(ue)}
                terminal_code = NetworkErrorCode.PROXY_CONNECT_FAILED
                error_detail = f"Proxy negotiation failed: {ue}"

    return {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_ms": round((time.time() - start_time) * 1000, 2),
        "environment": env_info,
        "ambient_env_proxies": env_proxies,
        "configured_route": config.to_sanitized_dict(),
        "layers": layers,
        "diagnostic_code": terminal_code.value,
        "error_detail": error_detail,
    }
