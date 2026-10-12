"""Public-only Binance USDⓈ-M client with strict network gating and endpoint allowlist."""

from __future__ import annotations

import asyncio
import json
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import websockets

from .contracts import (
    ALLOWED_PRODUCT,
    ALLOWED_REST_HOSTS,
    ALLOWED_SYMBOL,
    ALLOWED_WS_HOSTS,
    FORBIDDEN_HOSTS,
    FORBIDDEN_PRIVATE_KEYWORDS,
    ContractValidationError,
    MarketEventV1,
    compute_sha256,
)
from .order_book import OrderBookIntegrityEngine
from .time_authority import TimeAuthority

BINANCE_USDT_M_REST_BASE: str = "https://fapi.binance.com"
BINANCE_USDT_M_WS_BASE: str = "wss://fstream.binance.com/stream"


class NetworkGateError(RuntimeError):
    """Raised when network access is attempted while network is disabled."""


def validate_public_url(url: str, method: str = "GET") -> None:
    """Validate that URL and method conform strictly to public Binance USDⓈ-M futures rules."""
    if method.upper() != "GET":
        raise ContractValidationError(
            f"Method '{method}' forbidden. Public recorder strictly permits 'GET' only."
        )

    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()

    if scheme not in ("https", "wss"):
        raise ContractValidationError(f"Forbidden protocol '{scheme}'. Must be https or wss.")

    # Check forbidden hosts
    if host in FORBIDDEN_HOSTS or any(host.endswith(f".{bad}") for bad in FORBIDDEN_HOSTS):
        raise ContractValidationError(f"Forbidden host '{host}' in '{url}'. Public USDⓈ-M only.")

    # Check allowed hosts
    allowed = ALLOWED_REST_HOSTS if scheme == "https" else ALLOWED_WS_HOSTS
    if host not in allowed:
        raise ContractValidationError(f"Host '{host}' is not in allowlist {allowed}.")

    # Check forbidden private keywords in path or query
    for kw in FORBIDDEN_PRIVATE_KEYWORDS:
        if kw in path or kw in parsed.query.lower():
            raise ContractValidationError(f"Forbidden keyword '{kw}' detected in endpoint '{url}'.")


class BinancePublicFeedClient:
    """Public read-only client for Binance USDⓈ-M Futures (BTCUSDT)."""

    def __init__(
        self,
        symbol: str = ALLOWED_SYMBOL,
        network_mode: str = "disabled",
        time_authority: TimeAuthority | None = None,
        book_engine: OrderBookIntegrityEngine | None = None,
    ) -> None:
        if symbol != ALLOWED_SYMBOL:
            raise ContractValidationError(f"Symbol '{symbol}' invalid. Must be exact '{ALLOWED_SYMBOL}'")

        self.symbol = symbol
        self.network_mode = network_mode
        self.time_authority = time_authority or TimeAuthority()
        self.book_engine = book_engine or OrderBookIntegrityEngine(symbol=symbol)

    def _assert_network_permitted(self) -> None:
        if self.network_mode != "allow-public":
            raise NetworkGateError(
                f"Network access blocked. network_mode='{self.network_mode}' (must be 'allow-public')."
            )

    def fetch_public_depth_snapshot(self, limit: int = 1000) -> tuple[dict[str, Any], int, int]:
        """Fetch REST depth snapshot from official public endpoint."""
        self._assert_network_permitted()
        url = f"{BINANCE_USDT_M_REST_BASE}/fapi/v1/depth?symbol={self.symbol}&limit={limit}"
        validate_public_url(url, method="GET")

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "PublicForwardRecorder/1.0", "Accept": "application/json"},
            method="GET",
        )

        # Ingress clock captured immediately before/after network receive
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            ingress = self.time_authority.capture_ingress()
            raw_bytes = resp.read()

        data = json.loads(raw_bytes.decode("utf-8"))
        return data, ingress.observed_wall_utc_ms, ingress.observed_monotonic_ns

    def fetch_latest_settled_funding(self, limit: int = 5) -> tuple[list[dict[str, Any]], int, int]:
        """Fetch latest settled funding records from official public endpoint."""
        self._assert_network_permitted()
        url = f"{BINANCE_USDT_M_REST_BASE}/fapi/v1/fundingRate?symbol={self.symbol}&limit={limit}"
        validate_public_url(url, method="GET")

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "PublicForwardRecorder/1.0", "Accept": "application/json"},
            method="GET",
        )

        with urllib.request.urlopen(req, timeout=10.0) as resp:
            ingress = self.time_authority.capture_ingress()
            raw_bytes = resp.read()

        data = json.loads(raw_bytes.decode("utf-8"))
        return data, ingress.observed_wall_utc_ms, ingress.observed_monotonic_ns

    def map_raw_frame_to_event(
        self,
        raw_msg: str | bytes,
        observed_wall_ms: int,
        observed_monotonic_ns: int,
        raw_manifest_sha256: str,
    ) -> MarketEventV1 | None:
        """Parse raw incoming stream frame and create sealed MarketEventV1."""
        if isinstance(raw_msg, bytes):
            raw_str = raw_msg.decode("utf-8")
        else:
            raw_str = raw_msg

        try:
            payload = json.loads(raw_str)
        except json.JSONDecodeError:
            return None

        # Combined stream wrapper check: {"stream": "...", "data": {...}}
        stream_id = ""
        if "data" in payload and "stream" in payload:
            stream_id = payload["stream"]
            data = payload["data"]
        else:
            data = payload

        event_type = data.get("e")

        channel: str | None = None
        source_seq: int | None = None
        provider_event_ms: int | None = data.get("E")
        provider_tx_ms: int | None = data.get("T")
        book_receipt = None
        quality = "VERIFIED"
        reason_codes = ["OK"]

        if event_type == "kline":
            channel = "last_kline_1m"
            k = data.get("k", {})
            source_seq = k.get("L")
            if not stream_id:
                stream_id = f"{self.symbol.lower()}@kline_{k.get('i', '1m')}"

        elif event_type == "markPriceUpdate":
            channel = "mark_price"
            if not stream_id:
                stream_id = f"{self.symbol.lower()}@markPrice"

        elif event_type == "aggTrade":
            channel = "agg_trade"
            source_seq = data.get("a")
            if not stream_id:
                stream_id = f"{self.symbol.lower()}@aggTrade"

        elif event_type == "depthUpdate":
            channel = "depth_delta"
            source_seq = data.get("u")
            if not stream_id:
                stream_id = f"{self.symbol.lower()}@depth@100ms"

            # Apply to book engine
            book_receipt = self.book_engine.apply_delta(data, observed_wall_ms)
            if not book_receipt.continuous or book_receipt.quality != "VERIFIED":
                quality = book_receipt.quality
                reason_codes = list(book_receipt.reason_codes)

        else:
            return None

        self.time_authority.record_transit_latency(provider_event_ms, observed_wall_ms)
        payload_sha = compute_sha256(data)

        return MarketEventV1(
            schema_version="market-event-v1",
            symbol=self.symbol,
            product=ALLOWED_PRODUCT,
            channel=channel,
            provider_event_ms=provider_event_ms,
            provider_transaction_ms=provider_tx_ms,
            observed_wall_utc_ms=observed_wall_ms,
            observed_monotonic_ns=observed_monotonic_ns,
            available_at_ms=observed_wall_ms,
            source_stream_id=stream_id,
            connection_epoch=self.time_authority.connection_epoch,
            source_sequence=source_seq,
            payload_sha256=payload_sha,
            payload=data,
            quality=quality,
            reason_codes=reason_codes,
            raw_source_manifest_sha256=raw_manifest_sha256,
            book=book_receipt,
        )

    async def run_bounded_public_stream(
        self,
        duration_seconds: int = 60,
        on_event_callback: Any = None,
    ) -> dict[str, Any]:
        """Connect to official public combined streams for bounded duration."""
        self._assert_network_permitted()

        streams = [
            f"{self.symbol.lower()}@kline_1m",
            f"{self.symbol.lower()}@markPrice@1s",
            f"{self.symbol.lower()}@aggTrade",
            f"{self.symbol.lower()}@depth@100ms",
        ]
        url = f"{BINANCE_USDT_M_WS_BASE}?streams={'/'.join(streams)}"
        validate_public_url(url, method="GET")

        stats = {
            "status": "RUNNING",
            "events_received": 0,
            "duration_seconds": duration_seconds,
            "error": None,
        }

        # First, fetch snapshot to bridge book
        try:
            snap_data, snap_wall, _snap_mono = self.fetch_public_depth_snapshot()
            self.book_engine.apply_snapshot(snap_data, snap_wall)
        except Exception as exc:  # noqa: BLE001
            stats["status"] = "NOT_TESTED_SOURCE_UNREACHABLE"
            stats["error"] = f"REST depth snapshot failed: {exc}"
            return stats

        stop_time = asyncio.get_event_loop().time() + duration_seconds

        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                while asyncio.get_event_loop().time() < stop_time:
                    try:
                        timeout_left = max(0.1, stop_time - asyncio.get_event_loop().time())
                        raw_msg = await asyncio.wait_for(ws.recv(), timeout=timeout_left)
                        ingress = self.time_authority.capture_ingress()

                        event = self.map_raw_frame_to_event(
                            raw_msg,
                            ingress.observed_wall_utc_ms,
                            ingress.observed_monotonic_ns,
                            raw_manifest_sha256="live_stream",
                        )
                        if event is not None:
                            stats["events_received"] += 1
                            if on_event_callback is not None:
                                on_event_callback(event)
                    except TimeoutError:
                        break
            stats["status"] = "PUBLIC_SMOKE_VERIFIED"
        except (socket.gaierror, ssl.SSLError, ConnectionRefusedError, websockets.WebSocketException) as exc:
            stats["status"] = "NOT_TESTED_SOURCE_UNREACHABLE"
            stats["error"] = f"WebSocket connection failed: {exc}"

        return stats
