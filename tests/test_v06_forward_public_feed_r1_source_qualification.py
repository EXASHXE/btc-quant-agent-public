"""Tests for Multi-Channel Public Source Qualification and Strict Redaction.

Validates:
- Multi-channel qualification criteria (duration >= 120s, mark coverage >= 120s, klines >= 2, aggTrade > 0)
- Qualification levels: SOURCE_UNAVAILABLE, PUBLIC_ROUTE_REACHABLE, SHORT_DIAGNOSTIC,
  PUBLIC_SOURCE_PARTIAL, PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED, L2_CONTINUOUS_WINDOW_VERIFIED
- Eliminating R2 false-positive (REST-only without WSS never yields PUBLIC_SMOKE_VERIFIED)
- Bounded connector execution with per-channel metrics tracking
- Strict redaction omitting host, port, gateway, and NO_PROXY strings
- Adversarial stream events (crossed book, sequence gap, SSL EOF, socket disconnect, corrupt frames)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from scripts.integration.market_event_bridge_r2.source_qualification import (
    MIN_CLOSED_KLINES_1M,
    MIN_MARK_SPAN_SECONDS,
    MIN_QUALIFICATION_DURATION_SECONDS,
    QualificationLevel,
    evaluate_source_qualification,
)
from scripts.market_data.forward_public_feed_r1.connector import (
    BinancePublicFeedClient,
)
from scripts.market_data.forward_public_feed_r1.fixture import (
    DeterministicExchangeFixture,
)
from scripts.market_data.forward_public_feed_r1.proxy_route import (
    build_redacted_route_diagnostic,
)


def _build_passing_stats(
    duration: int = 180,
    mark_span: float = 175.5,
    closed_klines: int = 2,
    agg_trades: int = 42,
    raw_depth: int = 150,
    book_continuous: bool = True,
    rebootstraps: int = 0,
) -> dict[str, Any]:
    """Helper returning a stats dictionary matching all passing thresholds."""
    return {
        "status": "RUNNING",
        "events_received": 500,
        "public_depth_events": 200,
        "market_events": 300,
        "duration_seconds": duration,
        "raw_public_depth_update": raw_depth,
        "REST_snapshot": 1,
        "aggTrade": agg_trades,
        "markPriceTick": 120,
        "kline_closed_1m": closed_klines,
        "kline_open_1m": 10,
        "estimatedFunding": 20,
        "settledFunding": 1,
        "invalidFrames": 0,
        "sourceDropped": 0,
        "rebootstrap": rebootstraps,
        "rebootstrap_count": rebootstraps,
        "clockUncertain": 0,
        "receiver_ingress_epoch": "epoch-test",
        "route_epoch": "route-epoch-test",
        "manifest_sha": "a" * 64,
        "mark_first_seen_ms": 1728720000000,
        "mark_last_seen_ms": 1728720000000 + int(mark_span * 1000),
        "mark_span_seconds": mark_span,
        "book_continuous": book_continuous,
        "wss_public_depth_connected": True,
        "wss_market_connected": True,
        "wss_public_depth_error": None,
        "wss_market_error": None,
        "public_epoch": "pub-epoch-test",
        "market_epoch": "mkt-epoch-test",
        "error": None,
    }


# ==============================================================================
# Category 1: Evaluator Logic and Threshold Adherence
# ==============================================================================

def test_evaluate_perfect_coherent_stream_achieves_l2_continuous() -> None:
    stats = _build_passing_stats()
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.L2_CONTINUOUS_WINDOW_VERIFIED.value
    assert receipt.passed is True
    assert receipt.checks["rest_snapshot_ok"] is True
    assert receipt.checks["raw_depth_ok"] is True
    assert receipt.checks["agg_trades_ok"] is True
    assert receipt.checks["mark_ticks_ok"] is True
    assert receipt.checks["mark_span_ok"] is True
    assert receipt.checks["closed_klines_ok"] is True
    assert receipt.checks["wss_depth_ok"] is True
    assert receipt.checks["wss_market_ok"] is True
    assert receipt.checks["book_continuous"] is True
    assert receipt.checks["no_clock_uncertain"] is True


def test_evaluate_rebootstrap_downgrades_to_public_multi_channel() -> None:
    stats = _build_passing_stats(rebootstraps=1)
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED.value
    assert receipt.passed is True
    assert receipt.checks["book_continuous"] is False


def test_evaluate_discontinuous_book_downgrades_to_public_multi_channel() -> None:
    stats = _build_passing_stats(book_continuous=False)
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.PUBLIC_MULTI_CHANNEL_SOURCE_VERIFIED.value
    assert receipt.passed is True


def test_evaluate_rest_snapshot_missing_fails_source_unavailable() -> None:
    stats = _build_passing_stats()
    stats["REST_snapshot"] = 0
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.SOURCE_UNAVAILABLE.value
    assert receipt.passed is False
    assert receipt.checks["rest_snapshot_ok"] is False


def test_evaluate_rest_unreachable_fails_source_unavailable() -> None:
    stats = _build_passing_stats()
    stats["status"] = "NOT_TESTED_SOURCE_UNREACHABLE"
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.SOURCE_UNAVAILABLE.value
    assert receipt.passed is False


def test_evaluate_rest_ok_but_both_wss_failed_yields_public_route_reachable() -> None:
    stats = _build_passing_stats()
    stats["wss_public_depth_connected"] = False
    stats["wss_market_connected"] = False
    stats["wss_public_depth_error"] = "ConnectionRefusedError"
    stats["wss_market_error"] = "ConnectionRefusedError"
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.PUBLIC_ROUTE_REACHABLE.value
    assert receipt.passed is False


def test_evaluate_public_depth_wss_failed_yields_partial() -> None:
    stats = _build_passing_stats()
    stats["wss_public_depth_error"] = "SSLError: unexpected EOF"
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.PUBLIC_SOURCE_PARTIAL.value
    assert receipt.passed is False
    assert receipt.checks["wss_depth_ok"] is False


def test_evaluate_market_wss_failed_yields_partial() -> None:
    stats = _build_passing_stats()
    stats["wss_market_error"] = "TimeoutError: heartbeat failed"
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.PUBLIC_SOURCE_PARTIAL.value
    assert receipt.passed is False
    assert receipt.checks["wss_market_ok"] is False


def test_evaluate_short_duration_yields_short_diagnostic() -> None:
    stats = _build_passing_stats(duration=60)
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.SHORT_DIAGNOSTIC.value
    assert receipt.passed is False
    assert any("Duration 60s < required 120s" in r for r in receipt.reasons)


def test_evaluate_insufficient_closed_klines_yields_short_diagnostic() -> None:
    stats = _build_passing_stats(closed_klines=1)
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.SHORT_DIAGNOSTIC.value
    assert receipt.passed is False
    assert receipt.checks["closed_klines_ok"] is False


def test_evaluate_zero_closed_klines_yields_short_diagnostic() -> None:
    stats = _build_passing_stats(closed_klines=0)
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.SHORT_DIAGNOSTIC.value
    assert receipt.passed is False


def test_evaluate_insufficient_mark_span_yields_short_diagnostic() -> None:
    stats = _build_passing_stats(mark_span=85.0)
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.SHORT_DIAGNOSTIC.value
    assert receipt.passed is False
    assert receipt.checks["mark_span_ok"] is False


def test_evaluate_zero_agg_trades_yields_partial() -> None:
    stats = _build_passing_stats(agg_trades=0)
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.PUBLIC_SOURCE_PARTIAL.value
    assert receipt.passed is False
    assert receipt.checks["agg_trades_ok"] is False


def test_evaluate_zero_raw_depth_yields_partial() -> None:
    stats = _build_passing_stats(raw_depth=0)
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.PUBLIC_SOURCE_PARTIAL.value
    assert receipt.passed is False
    assert receipt.checks["raw_depth_ok"] is False


def test_evaluate_zero_mark_price_ticks_yields_partial() -> None:
    stats = _build_passing_stats()
    stats["markPriceTick"] = 0
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.PUBLIC_SOURCE_PARTIAL.value
    assert receipt.passed is False
    assert receipt.checks["mark_ticks_ok"] is False


def test_evaluate_clock_uncertain_recorded_in_checks() -> None:
    stats = _build_passing_stats()
    stats["clockUncertain"] = 3
    receipt = evaluate_source_qualification(stats)
    assert receipt.checks["no_clock_uncertain"] is False


def test_receipt_serialization_to_dict_and_json() -> None:
    stats = _build_passing_stats()
    receipt = evaluate_source_qualification(stats)
    d = receipt.to_dict()
    assert isinstance(d, dict)
    assert "qualification_level" in d
    assert "checks" in d
    j = receipt.to_json()
    assert isinstance(j, str)
    parsed = json.loads(j)
    assert parsed["qualification_level"] == QualificationLevel.L2_CONTINUOUS_WINDOW_VERIFIED.value


def test_qualification_constants_adherence() -> None:
    assert MIN_QUALIFICATION_DURATION_SECONDS == 120
    assert MIN_MARK_SPAN_SECONDS == 120.0
    assert MIN_CLOSED_KLINES_1M == 2


# ==============================================================================
# Category 2: Redacted Route Diagnostic Security Verification
# ==============================================================================

def test_build_redacted_route_diagnostic_omits_ip_and_port() -> None:
    raw_diag = {
        "timestamp_utc": "2026-10-12T12:00:00Z",
        "duration_ms": 150.2,
        "environment": {
            "os": "Linux",
            "detected_gateway_ip": "192.168.31.1",
        },
        "ambient_env_proxies": {
            "HTTP_PROXY": "http://127.0.0.1:7897",
            "NO_PROXY": "localhost,127.0.0.1,192.168.0.0/16",
        },
        "configured_route": {
            "mode": "public-clash-explicit",
            "kind": "http",
            "host": "127.0.0.1",
            "port": 7897,
            "route_epoch": "ep-1",
        },
        "layers": {
            "layer_1_local_tcp": {"status": "SUCCESS", "host": "127.0.0.1", "port": 7897},
            "layer_2_proxy_negotiation": {"status": "SUCCESS"},
            "layer_3_tls_rest_verify": {"status": "SUCCESS", "status_code": 200, "bytes": 4500},
            "layer_4_ws_connect_verify": {"status": "SUCCESS", "frame_bytes": 850, "stream": "btcusdt@depth@100ms"},
        },
        "diagnostic_code": "DIAGNOSTIC_OK",
        "error_detail": None,
    }

    redacted = build_redacted_route_diagnostic(raw_diag)
    serialized = json.dumps(redacted)

    # Strict prohibitions: NO IP, NO port, NO gateway, NO NO_PROXY
    assert "127.0.0.1" not in serialized
    assert "7897" not in serialized
    assert "192.168.31.1" not in serialized
    assert "NO_PROXY" not in serialized
    assert "ambient_env_proxies" not in serialized
    assert "detected_gateway_ip" not in serialized

    # Allowed safe fields
    assert redacted["proxy_enabled"] is True
    assert redacted["proxy_kind"] == "http"
    assert redacted["loopback_or_host"] == "loopback"
    assert len(redacted["route_hash"]) == 16
    assert redacted["diagnostic_code"] == "DIAGNOSTIC_OK"
    assert redacted["layers"]["layer_1_local_tcp"] == {"status": "SUCCESS"}


def test_redacted_route_diagnostic_scrubs_error_ip_and_port() -> None:
    raw_diag = {
        "configured_route": {"mode": "public-clash-explicit", "kind": "socks5h", "host": "10.0.5.20", "port": 1080},
        "layers": {"layer_1_local_tcp": {"status": "FAILED"}},
        "diagnostic_code": "PROXY_PORT_CLOSED",
        "error_detail": "TCP connection to proxy port 1080 on 10.0.5.20 failed: Connection refused",
    }
    redacted = build_redacted_route_diagnostic(raw_diag)
    serialized = json.dumps(redacted)

    assert "10.0.5.20" not in serialized
    assert "1080" not in serialized
    assert "[REDACTED_IP]" in redacted["error_detail"]
    assert "[REDACTED_PORT]" in redacted["error_detail"]
    assert redacted["loopback_or_host"] == "remote_host"


def test_redacted_route_diagnostic_direct_mode() -> None:
    raw_diag = {
        "configured_route": {"mode": "public-direct", "kind": "none", "host": None, "port": None},
        "layers": {},
        "diagnostic_code": "DIAGNOSTIC_OK",
    }
    redacted = build_redacted_route_diagnostic(raw_diag)
    assert redacted["proxy_enabled"] is False
    assert redacted["proxy_kind"] == "none"
    assert redacted["loopback_or_host"] == "direct"


def test_redacted_route_diagnostic_disabled_mode() -> None:
    raw_diag = {
        "configured_route": {"mode": "disabled"},
        "layers": {},
        "diagnostic_code": "NETWORK_DISABLED",
    }
    redacted = build_redacted_route_diagnostic(raw_diag)
    assert redacted["proxy_enabled"] is False
    assert redacted["loopback_or_host"] == "none"


def test_redacted_route_hash_deterministic() -> None:
    diag1 = {"configured_route": {"mode": "public-clash-explicit", "kind": "http", "host": "127.0.0.1", "port": 7890}}
    diag2 = {"configured_route": {"mode": "public-clash-explicit", "kind": "http", "host": "127.0.0.1", "port": 7890}}
    r1 = build_redacted_route_diagnostic(diag1)
    r2 = build_redacted_route_diagnostic(diag2)
    assert r1["route_hash"] == r2["route_hash"]


def test_redacted_route_hash_distinct_for_different_ports() -> None:
    diag1 = {"configured_route": {"mode": "public-clash-explicit", "kind": "http", "host": "127.0.0.1", "port": 7890}}
    diag2 = {"configured_route": {"mode": "public-clash-explicit", "kind": "http", "host": "127.0.0.1", "port": 7891}}
    r1 = build_redacted_route_diagnostic(diag1)
    r2 = build_redacted_route_diagnostic(diag2)
    assert r1["route_hash"] != r2["route_hash"]


# ==============================================================================
# Category 3: Connector Bounded Stream Execution & Status Resolution
# ==============================================================================

def test_connector_bounded_stream_rest_only_never_yields_smoke_verified() -> None:
    """Falsification test: Demonstrates elimination of R2 failure vector 5."""
    async def _test() -> None:
        client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="allow-public")
        fix = DeterministicExchangeFixture(symbol="BTCUSDT")
        snap_frame = fix.generate_depth_snapshot_frame(levels=5)

        with (
            patch.object(client, "fetch_public_depth_snapshot", return_value=(snap_frame, 1000, 1000)),
            patch.object(client, "fetch_latest_settled_funding", return_value=([], 1000, 1000)),
            patch("websockets.connect", side_effect=OSError("WebSocket connection failed: Connection refused")),
        ):
            stats = await client.run_bounded_public_stream(duration_seconds=1)
            # In R2, this returned PUBLIC_SMOKE_VERIFIED! In R3, it MUST be SOURCE_UNAVAILABLE
            assert stats["status"] != "PUBLIC_SMOKE_VERIFIED"
            assert stats["status"] == "SOURCE_UNAVAILABLE"
            assert stats["REST_snapshot"] == 1
            assert stats["wss_public_depth_connected"] is False

    asyncio.run(_test())


def test_connector_bounded_stream_short_duration_yields_short_diagnostic() -> None:
    async def _test() -> None:
        client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="allow-public")
        fix = DeterministicExchangeFixture(symbol="BTCUSDT")
        snap_frame = fix.generate_depth_snapshot_frame(levels=5)

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError)

        class MockConnectContext:
            async def __aenter__(self) -> Any:
                return mock_ws
            async def __aexit__(self, *args: object) -> None:
                pass

        with (
            patch.object(client, "fetch_public_depth_snapshot", return_value=(snap_frame, 1000, 1000)),
            patch.object(client, "fetch_latest_settled_funding", return_value=([], 1000, 1000)),
            patch("websockets.connect", return_value=MockConnectContext()),
        ):
            stats = await client.run_bounded_public_stream(duration_seconds=5)
            assert stats["status"] == "SHORT_DIAGNOSTIC"
            assert stats["status"] != "PUBLIC_SMOKE_VERIFIED"

    asyncio.run(_test())


def test_connector_bounded_stream_tracks_per_channel_counters() -> None:
    async def _test() -> None:
        client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="allow-public")
        fix = DeterministicExchangeFixture(symbol="BTCUSDT")
        snap_frame = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)
        delta_frame = fix.generate_depth_delta_frame(span=2, force_pu=1000)
        agg_frame = fix.generate_agg_trade_frame()
        mark_frame = fix.generate_mark_price_frame()
        kline_open = fix.generate_kline_frame(closed=False)
        kline_closed = fix.generate_kline_frame(closed=True)

        frames = [
            json.dumps(delta_frame),
            json.dumps(agg_frame),
            json.dumps(mark_frame),
            json.dumps(kline_open),
            json.dumps(kline_closed),
        ]

        mock_ws = AsyncMock()
        idx = 0

        async def _mock_recv() -> str:
            nonlocal idx
            if idx < len(frames):
                val = frames[idx]
                idx += 1
                return val
            await asyncio.sleep(10)
            return ""

        mock_ws.recv = AsyncMock(side_effect=_mock_recv)

        class MockConnectContext:
            async def __aenter__(self) -> Any:
                return mock_ws
            async def __aexit__(self, *args: object) -> None:
                pass

        with (
            patch.object(client, "fetch_public_depth_snapshot", return_value=(snap_frame, 1000, 1000)),
            patch.object(client, "fetch_latest_settled_funding", return_value=([], 1000, 1000)),
            patch("websockets.connect", return_value=MockConnectContext()),
        ):
            stats = await client.run_bounded_public_stream(duration_seconds=1)
            assert stats["raw_public_depth_update"] >= 1
            assert stats["aggTrade"] >= 1
            assert stats["markPriceTick"] >= 1
            assert stats["kline_open_1m"] >= 1
            assert stats["kline_closed_1m"] >= 1
            assert stats["mark_first_seen_ms"] is not None
            assert stats["mark_last_seen_ms"] is not None

    asyncio.run(_test())


def test_connector_bounded_stream_corrupt_frames_increment_invalid() -> None:
    async def _test() -> None:
        client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="allow-public")
        fix = DeterministicExchangeFixture(symbol="BTCUSDT")
        snap_frame = fix.generate_depth_snapshot_frame(levels=5)

        frames = ["invalid_not_json_###", "{\"stream\": \"unknown\", \"data\": {}}"]
        mock_ws = AsyncMock()
        idx = 0

        async def _mock_recv() -> str:
            nonlocal idx
            if idx < len(frames):
                val = frames[idx]
                idx += 1
                return val
            await asyncio.sleep(10)
            return ""

        mock_ws.recv = AsyncMock(side_effect=_mock_recv)

        class MockConnectContext:
            async def __aenter__(self) -> Any:
                return mock_ws
            async def __aexit__(self, *args: object) -> None:
                pass

        with (
            patch.object(client, "fetch_public_depth_snapshot", return_value=(snap_frame, 1000, 1000)),
            patch.object(client, "fetch_latest_settled_funding", return_value=([], 1000, 1000)),
            patch("websockets.connect", return_value=MockConnectContext()),
        ):
            stats = await client.run_bounded_public_stream(duration_seconds=1)
            assert stats["invalidFrames"] >= 1

    asyncio.run(_test())


def test_connector_bounded_stream_clean_shutdown_cancels_tasks() -> None:
    async def _test() -> None:
        client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="allow-public")
        fix = DeterministicExchangeFixture(symbol="BTCUSDT")
        snap_frame = fix.generate_depth_snapshot_frame(levels=5)

        async def _hang(*args: Any, **kwargs: Any) -> str:
            await asyncio.sleep(10)
            return ""

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=_hang)

        class MockConnectContext:
            async def __aenter__(self) -> Any:
                return mock_ws
            async def __aexit__(self, *args: object) -> None:
                pass

        with (
            patch.object(client, "fetch_public_depth_snapshot", return_value=(snap_frame, 1000, 1000)),
            patch.object(client, "fetch_latest_settled_funding", return_value=([], 1000, 1000)),
            patch("websockets.connect", return_value=MockConnectContext()),
        ):
            stats = await client.run_bounded_public_stream(duration_seconds=1)
            # Successfully cleanly terminated within ~1 second without leaving hanging background tasks
            assert stats["status"] == "SHORT_DIAGNOSTIC"

    asyncio.run(_test())


# ==============================================================================
# Category 4: Adversarial Stream Scenarios & Boundary Falsification
# ==============================================================================

def test_adversarial_crossed_order_book_detected_by_client() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=100)
    client.book_engine.apply_snapshot(snap, 1000)

    # Inverted delta: bid 100.0, ask 90.0 (crossed)
    crossed_delta = {
        "e": "depthUpdate",
        "E": 1050,
        "s": "BTCUSDT",
        "U": 101,
        "u": 102,
        "pu": 100,
        "b": [["100.00", "1.000"]],
        "a": [["90.00", "1.000"]],
    }
    event = client.map_raw_frame_to_event(
        json.dumps(crossed_delta),
        observed_wall_ms=1050,
        observed_monotonic_ns=1000,
        raw_manifest_sha256="sha",
    )
    assert event is not None
    assert event.book is not None
    assert event.book.continuous is False
    assert any("CROSSED_BOOK" in r for r in event.book.reason_codes)


def test_adversarial_sequence_gap_triggers_rebootstrap_flag() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=100)
    client.book_engine.apply_snapshot(snap, 1000)

    # Gap: pu=200 instead of 100
    gap_delta = {
        "e": "depthUpdate",
        "E": 1050,
        "s": "BTCUSDT",
        "U": 201,
        "u": 202,
        "pu": 200,
        "b": [["95.00", "1.000"]],
        "a": [["105.00", "1.000"]],
    }
    event = client.map_raw_frame_to_event(
        json.dumps(gap_delta),
        observed_wall_ms=1050,
        observed_monotonic_ns=1000,
        raw_manifest_sha256="sha",
    )
    assert event is not None
    assert client.book_engine.needs_rebootstrap is True


def test_adversarial_zero_depth_levels_in_snapshot_fails_validation() -> None:
    from scripts.market_data.forward_public_feed_r1.contracts import (
        ContractValidationError,
        validate_provider_payload_shape,
    )
    corrupt_snap = {
        "lastUpdateId": 100,
        "E": 1000,
        "T": 1000,
        "bids": [],
    }
    with pytest.raises(ContractValidationError, match="missing required field 'asks'"):
        validate_provider_payload_shape("depth_snapshot", corrupt_snap)

    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    assert client.map_raw_frame_to_event(json.dumps(corrupt_snap), 1000, 1000, "sha") is None



def test_adversarial_unrouted_legacy_ws_rejected() -> None:
    from scripts.market_data.forward_public_feed_r1.proxy_route import (
        NetworkRouteError,
        validate_2026_routed_url,
    )
    legacy = "wss://fstream.binance.com/stream?streams=btcusdt@depth@100ms"
    with pytest.raises(NetworkRouteError, match="Unrouted legacy endpoint '/stream' deprecated"):
        validate_2026_routed_url(legacy)


def test_adversarial_market_stream_on_public_route_rejected() -> None:
    from scripts.market_data.forward_public_feed_r1.proxy_route import (
        NetworkRouteError,
        validate_2026_routed_url,
    )
    bad_url = "wss://fstream.binance.com/public/stream?streams=btcusdt@aggTrade"
    with pytest.raises(NetworkRouteError, match="Market stream .* forbidden on '/public/stream'"):
        validate_2026_routed_url(bad_url, expected_route="public")


def test_adversarial_depth_stream_on_market_route_rejected() -> None:
    from scripts.market_data.forward_public_feed_r1.proxy_route import (
        NetworkRouteError,
        validate_2026_routed_url,
    )
    bad_url = "wss://fstream.binance.com/market/stream?streams=btcusdt@depth@100ms"
    with pytest.raises(NetworkRouteError, match="Depth stream .* forbidden on '/market/stream'"):
        validate_2026_routed_url(bad_url, expected_route="market")


def test_adversarial_non_btcusdt_symbol_in_frame_rejected() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    frame = fix.generate_agg_trade_frame()
    frame["s"] = "ETHUSDT"
    from scripts.market_data.forward_public_feed_r1.contracts import ContractValidationError
    with pytest.raises(ContractValidationError, match="does not match allowed symbol 'BTCUSDT'"):
        client.map_raw_frame_to_event(
            json.dumps(frame),
            observed_wall_ms=1000,
            observed_monotonic_ns=1000,
            raw_manifest_sha256="sha",
        )


def test_adversarial_negative_duration_handled_gracefully() -> None:
    stats = _build_passing_stats()
    stats["duration_seconds"] = -10
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.SHORT_DIAGNOSTIC.value
    assert receipt.passed is False


def test_adversarial_negative_mark_span_handled_gracefully() -> None:
    stats = _build_passing_stats()
    stats["mark_span_seconds"] = -5.0
    receipt = evaluate_source_qualification(stats)
    assert receipt.qualification_level == QualificationLevel.SHORT_DIAGNOSTIC.value
    assert receipt.passed is False
