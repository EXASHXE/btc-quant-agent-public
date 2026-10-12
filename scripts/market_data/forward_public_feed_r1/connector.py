"""Public-only Binance USDⓈ-M client with strict network gating and endpoint allowlist."""

from __future__ import annotations

import asyncio
import json
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
    validate_provider_payload_shape,
)
from .order_book import OrderBookIntegrityEngine
from .proxy_route import (
    ProxyRouteConfig,
    build_2026_market_stream_url,
    build_2026_public_stream_url,
    validate_2026_routed_url,
)
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
        proxy_config: ProxyRouteConfig | None = None,
    ) -> None:
        if symbol != ALLOWED_SYMBOL:
            raise ContractValidationError(f"Symbol '{symbol}' invalid. Must be exact '{ALLOWED_SYMBOL}'")

        self.symbol = symbol
        self.network_mode = network_mode
        self.time_authority = time_authority or TimeAuthority()
        self.book_engine = book_engine or OrderBookIntegrityEngine(symbol=symbol)

        if proxy_config is not None:
            self.proxy_config = proxy_config
            if proxy_config.mode in ("public-direct", "public-clash-explicit") and self.network_mode == "disabled":
                self.network_mode = proxy_config.mode
        else:
            mode = "public-direct" if network_mode == "allow-public" else network_mode
            self.proxy_config = ProxyRouteConfig(mode=mode)

    def _assert_network_permitted(self) -> None:
        if self.network_mode not in ("allow-public", "public-direct", "public-clash-explicit"):
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

        opener = self.proxy_config.build_urllib_opener()
        with opener.open(req, timeout=10.0) as resp:
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

        opener = self.proxy_config.build_urllib_opener()
        with opener.open(req, timeout=10.0) as resp:
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

        # Validate symbol allowlist in provider frame
        payload_sym = data.get("s")
        if payload_sym is not None and payload_sym != self.symbol:
            raise ContractValidationError(
                f"Payload symbol '{payload_sym}' does not match allowed symbol '{self.symbol}'"
            )

        channel: str | None = None
        source_seq: int | None = None
        provider_event_ms: int | None = data.get("E")
        provider_tx_ms: int | None = data.get("T")
        book_receipt = None
        quality = "VERIFIED"
        reason_codes = ["OK"]

        if "lastUpdateId" in data and "bids" in data and "asks" in data:
            channel = "depth_snapshot"
            validate_provider_payload_shape(channel, data, self.symbol)
            book_receipt = self.book_engine.apply_snapshot(data, observed_wall_ms)
            source_seq = data.get("lastUpdateId")
            provider_event_ms = data.get("E", observed_wall_ms)
            provider_tx_ms = data.get("T")
            if not stream_id:
                stream_id = f"{self.symbol.lower()}@depth_snapshot"
            if not book_receipt.continuous or book_receipt.quality != "VERIFIED":
                quality = book_receipt.quality
                reason_codes = list(book_receipt.reason_codes)

        elif "fundingRate" in data and "fundingTime" in data:
            channel = "funding_settled"
            validate_provider_payload_shape(channel, data, self.symbol)
            provider_event_ms = data.get("fundingTime")
            source_seq = None
            if not stream_id:
                stream_id = f"{self.symbol.lower()}@fundingRate"

        elif event_type == "kline":
            channel = "last_kline_1m"
            validate_provider_payload_shape(channel, data, self.symbol)
            k = data.get("k", {})
            source_seq = k.get("L")
            if not stream_id:
                stream_id = f"{self.symbol.lower()}@kline_{k.get('i', '1m')}"

        elif event_type == "markPriceUpdate":
            channel = "mark_price"
            validate_provider_payload_shape(channel, data, self.symbol)
            if not stream_id:
                stream_id = f"{self.symbol.lower()}@markPrice"

        elif event_type == "aggTrade":
            channel = "agg_trade"
            validate_provider_payload_shape(channel, data, self.symbol)
            source_seq = data.get("a")
            if not stream_id:
                stream_id = f"{self.symbol.lower()}@aggTrade"

        elif event_type == "depthUpdate":
            channel = "depth_delta"
            validate_provider_payload_shape(channel, data, self.symbol)
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
        raw_writer: Any = None,
        event_writer: Any = None,
        custom_url: str | None = None,
    ) -> dict[str, Any]:
        """Connect to official 2026 public depth and market streams for bounded duration."""
        self._assert_network_permitted()

        public_url = build_2026_public_stream_url(self.symbol)
        market_url = build_2026_market_stream_url(self.symbol)

        if custom_url is not None:
            validate_public_url(custom_url, method="GET")
            target_urls = [(custom_url, "custom")]
        else:
            validate_2026_routed_url(public_url, expected_route="public")
            validate_2026_routed_url(market_url, expected_route="market")
            target_urls = [(public_url, "public_depth"), (market_url, "market_events")]

        stats: dict[str, Any] = {
            "status": "RUNNING",
            "qualification_level": "NOT_TESTED",
            "events_received": 0,
            "public_depth_events": 0,
            "market_events": 0,
            "duration_seconds": duration_seconds,
            "raw_public_depth_update": 0,
            "REST_snapshot": 0,
            "aggTrade": 0,
            "markPriceTick": 0,
            "kline_closed_1m": 0,
            "kline_open_1m": 0,
            "estimatedFunding": 0,
            "settledFunding": 0,
            "invalidFrames": 0,
            "sourceDropped": 0,
            "rebootstrap": 0,
            "rebootstrap_count": 0,
            "clockUncertain": 0,
            "receiver_ingress_epoch": self.time_authority.connection_epoch,
            "route_epoch": getattr(self.proxy_config, "route_epoch", "route-epoch-0"),
            "manifest_sha": None,
            "mark_first_seen_ms": None,
            "mark_last_seen_ms": None,
            "mark_span_seconds": 0.0,
            "book_continuous": True,
            "wss_public_depth_connected": False,
            "wss_market_connected": False,
            "wss_public_depth_error": None,
            "wss_market_error": None,
            "public_epoch": f"pub-{self.time_authority.connection_epoch}",
            "market_epoch": f"mkt-{self.time_authority.connection_epoch}",
            "error": None,
        }

        # First, fetch snapshot to bridge book
        try:
            snap_data, snap_wall, snap_mono = self.fetch_public_depth_snapshot()
            snap_raw_bytes = json.dumps(snap_data)
            if raw_writer is not None:
                _h, snap_man_sha = raw_writer.append_raw_frame(
                    snap_raw_bytes, snap_wall, snap_mono
                )
            else:
                snap_man_sha = compute_sha256(snap_raw_bytes)
            snap_event = self.map_raw_frame_to_event(
                snap_raw_bytes,
                snap_wall,
                snap_mono,
                raw_manifest_sha256=snap_man_sha,
            )
            if snap_event is not None:
                stats["events_received"] += 1
                stats["public_depth_events"] += 1
                stats["REST_snapshot"] += 1
                stats["manifest_sha"] = snap_man_sha
                if event_writer is not None:
                    event_writer.append_event(snap_event)
                if on_event_callback is not None:
                    on_event_callback(snap_event)
        except Exception as exc:  # noqa: BLE001
            stats["status"] = "NOT_TESTED_SOURCE_UNREACHABLE"
            stats["qualification_level"] = "SOURCE_UNAVAILABLE"
            stats["error"] = f"REST depth snapshot failed: {exc}"
            return stats

        # Fetch initial completed settled funding record
        try:
            funding_records, fund_wall, fund_mono = self.fetch_latest_settled_funding(limit=1)
            if funding_records:
                latest_fund = funding_records[0]
                fund_raw_bytes = json.dumps(latest_fund)
                if raw_writer is not None:
                    _fh, fund_man_sha = raw_writer.append_raw_frame(
                        fund_raw_bytes, fund_wall, fund_mono
                    )
                else:
                    fund_man_sha = compute_sha256(fund_raw_bytes)
                fund_event = self.map_raw_frame_to_event(
                    fund_raw_bytes,
                    fund_wall,
                    fund_mono,
                    raw_manifest_sha256=fund_man_sha,
                )
                if fund_event is not None:
                    stats["events_received"] += 1
                    stats["market_events"] += 1
                    stats["settledFunding"] += 1
                    stats["manifest_sha"] = fund_man_sha
                    if event_writer is not None:
                        event_writer.append_event(fund_event)
        except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError, ValueError, ContractValidationError):
            pass

        stop_time = asyncio.get_event_loop().time() + duration_seconds
        ws_proxy = self.proxy_config.get_websockets_proxy() if self.proxy_config else None

        async def _consume_stream(stream_url: str, stream_tag: str) -> None:
            try:
                async with websockets.connect(
                    stream_url,
                    proxy=ws_proxy,
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    if stream_tag == "public_depth":
                        stats["wss_public_depth_connected"] = True
                    elif stream_tag == "market_events":
                        stats["wss_market_connected"] = True
                    elif stream_tag == "custom":
                        stats["wss_public_depth_connected"] = True
                        stats["wss_market_connected"] = True

                    while asyncio.get_event_loop().time() < stop_time:
                        timeout_left = max(0.1, stop_time - asyncio.get_event_loop().time())
                        try:
                            raw_msg = await asyncio.wait_for(ws.recv(), timeout=timeout_left)
                        except TimeoutError:
                            break

                        ingress = self.time_authority.capture_ingress()
                        if raw_writer is not None:
                            _eh, raw_manifest_sha = raw_writer.append_raw_frame(
                                raw_msg,
                                ingress.observed_wall_utc_ms,
                                ingress.observed_monotonic_ns,
                            )
                        else:
                            raw_manifest_sha = compute_sha256(raw_msg)

                        event = self.map_raw_frame_to_event(
                            raw_msg,
                            ingress.observed_wall_utc_ms,
                            ingress.observed_monotonic_ns,
                            raw_manifest_sha256=raw_manifest_sha,
                        )
                        if event is None:
                            stats["invalidFrames"] += 1
                            continue

                        stats["events_received"] += 1
                        stats["manifest_sha"] = raw_manifest_sha
                        if stream_tag == "public_depth":
                            stats["public_depth_events"] += 1
                        else:
                            stats["market_events"] += 1

                        if event.channel == "depth_delta":
                            stats["raw_public_depth_update"] += 1
                            if event.book is not None and not event.book.continuous:
                                stats["book_continuous"] = False
                        elif event.channel == "agg_trade":
                            stats["aggTrade"] += 1
                        elif event.channel == "mark_price":
                            stats["markPriceTick"] += 1
                            now_ms = event.provider_event_ms or event.observed_wall_utc_ms
                            if stats["mark_first_seen_ms"] is None:
                                stats["mark_first_seen_ms"] = now_ms
                            stats["mark_last_seen_ms"] = now_ms
                            stats["mark_span_seconds"] = max(
                                0.0,
                                round((stats["mark_last_seen_ms"] - stats["mark_first_seen_ms"]) / 1000.0, 3)
                            )
                            if "r" in event.payload or "estimatedSettlePrice" in event.payload:
                                stats["estimatedFunding"] += 1
                        elif event.channel == "last_kline_1m":
                            k = event.payload.get("k", {})
                            if k.get("x") is True:
                                stats["kline_closed_1m"] += 1
                            else:
                                stats["kline_open_1m"] += 1
                        elif event.channel == "funding_settled":
                            stats["settledFunding"] += 1

                        if "CLOCK_UNCERTAIN" in event.reason_codes:
                            stats["clockUncertain"] += 1

                        if event_writer is not None:
                            event_writer.append_event(event)
                        if on_event_callback is not None:
                            on_event_callback(event)

                        if self.book_engine.needs_rebootstrap:
                            try:
                                reb_snap, reb_wall, reb_mono = self.fetch_public_depth_snapshot()
                                reb_raw_bytes = json.dumps(reb_snap)
                                if raw_writer is not None:
                                    _rh, reb_man_sha = raw_writer.append_raw_frame(
                                        reb_raw_bytes, reb_wall, reb_mono
                                    )
                                else:
                                    reb_man_sha = compute_sha256(reb_raw_bytes)
                                reb_event = self.map_raw_frame_to_event(
                                    reb_raw_bytes,
                                    reb_wall,
                                    reb_mono,
                                    raw_manifest_sha256=reb_man_sha,
                                )
                                if reb_event is not None and event_writer is not None:
                                    event_writer.append_event(reb_event)
                                stats["rebootstrap_count"] += 1
                                stats["rebootstrap"] += 1
                                stats["REST_snapshot"] += 1
                            except Exception as reb_exc:  # noqa: BLE001
                                stats["rebootstrap_error"] = str(reb_exc)
            except Exception as exc:  # noqa: BLE001
                stats["sourceDropped"] += 1
                err_msg = str(exc)
                if stream_tag == "public_depth":
                    stats["wss_public_depth_error"] = err_msg
                elif stream_tag == "market_events":
                    stats["wss_market_error"] = err_msg
                else:
                    stats["error"] = err_msg
        tasks = [asyncio.create_task(_consume_stream(u, tag)) for u, tag in target_urls]
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        # Qualification level evaluation
        if custom_url is not None:
            depth_ok = stats["wss_public_depth_connected"] and (stats["wss_public_depth_error"] is None)
            market_ok = depth_ok
        else:
            depth_ok = stats["wss_public_depth_connected"] and (stats["wss_public_depth_error"] is None)
            market_ok = stats["wss_market_connected"] and (stats["wss_market_error"] is None)

        if not depth_ok and not market_ok:
            if stats["REST_snapshot"] > 0:
                stats["status"] = "SOURCE_UNAVAILABLE"
            else:
                stats["status"] = "NOT_TESTED_SOURCE_UNREACHABLE"
        elif not depth_ok or not market_ok:
            stats["status"] = "PUBLIC_SOURCE_PARTIAL"
        elif stats["duration_seconds"] < 120 or stats["mark_span_seconds"] < 120.0 or stats["kline_closed_1m"] < 2:
            stats["status"] = "SHORT_DIAGNOSTIC"
        elif stats["aggTrade"] == 0 or stats["raw_public_depth_update"] == 0:
            stats["status"] = "PUBLIC_SOURCE_PARTIAL"
        else:
            book_ok = self.book_engine.continuous and self.book_engine.is_bootstrapped and not self.book_engine.needs_rebootstrap and stats["book_continuous"]
            if book_ok:
                stats["status"] = "L2_CONTINUOUS_WINDOW_VERIFIED"
            else:
                stats["status"] = "PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED"

        stats["qualification_level"] = stats["status"]
        return stats
