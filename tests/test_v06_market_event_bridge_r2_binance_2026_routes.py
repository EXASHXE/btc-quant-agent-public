"""20 Pytest unit tests for Binance 2026 routed WebSocket and REST endpoints."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.proxy_route import (
    BINANCE_2026_MARKET_WS_BASE,
    BINANCE_2026_PUBLIC_WS_BASE,
    BINANCE_2026_REST_BASE,
    NetworkErrorCode,
    NetworkRouteError,
    build_2026_market_stream_url,
    build_2026_public_stream_url,
    validate_2026_routed_url,
)


def test_route_2026_public_stream_url_format() -> None:
    url = build_2026_public_stream_url("BTCUSDT")
    assert url == "wss://fstream.binance.com/public/stream?streams=btcusdt@depth@100ms"
    validate_2026_routed_url(url, expected_route="public")


def test_route_2026_market_stream_url_format() -> None:
    url = build_2026_market_stream_url("BTCUSDT")
    assert url == "wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade/btcusdt@kline_1m/btcusdt@markPrice@1s"
    validate_2026_routed_url(url, expected_route="market")


def test_route_2026_rest_depth_url() -> None:
    url = f"{BINANCE_2026_REST_BASE}/fapi/v1/depth?symbol=BTCUSDT&limit=1000"
    validate_2026_routed_url(url, expected_route="rest")


def test_route_2026_rest_funding_url() -> None:
    url = f"{BINANCE_2026_REST_BASE}/fapi/v1/fundingRate?symbol=BTCUSDT&limit=5"
    validate_2026_routed_url(url, expected_route="rest")


def test_reject_legacy_unrouted_stream_root() -> None:
    legacy_url = "wss://fstream.binance.com/stream"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(legacy_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID
    assert "deprecated since 2026-04-23" in str(exc_info.value)


def test_reject_legacy_unrouted_stream_with_query() -> None:
    legacy_url = "wss://fstream.binance.com/stream?streams=btcusdt@depth@100ms"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(legacy_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_legacy_unrouted_market_streams() -> None:
    legacy_url = "wss://fstream.binance.com/stream?streams=btcusdt@kline_1m/btcusdt@markPrice@1s"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(legacy_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_private_listen_key_in_public_ws() -> None:
    bad_url = f"{BINANCE_2026_PUBLIC_WS_BASE}?listenKey=test_key_123"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_private_listen_key_in_market_ws() -> None:
    bad_url = f"{BINANCE_2026_MARKET_WS_BASE}?listenKey=test_key_123"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_private_order_endpoint() -> None:
    bad_url = f"{BINANCE_2026_REST_BASE}/fapi/v1/order?symbol=BTCUSDT"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_coin_m_delivery_host_ws() -> None:
    bad_url = "wss://dapi.binance.com/public/stream?streams=btcusd_perp@depth"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_coin_m_delivery_host_rest() -> None:
    bad_url = "https://dapi.binance.com/dapi/v1/depth?symbol=BTCUSD_PERP"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_spot_host_ws() -> None:
    bad_url = "wss://api.binance.com/stream?streams=btcusdt@depth"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_spot_host_rest() -> None:
    bad_url = "https://api.binance.com/api/v3/depth?symbol=BTCUSDT"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_testnet_future_host() -> None:
    bad_url = "wss://testnet.binancefuture.com/public/stream"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_testnet_vision_host() -> None:
    bad_url = "https://testnet.binance.vision/fapi/v1/depth"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_ws_fapi_private_protocol() -> None:
    bad_url = "wss://fstream.binance.com/ws-fapi/v1"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_cross_channel_depth_on_market_route() -> None:
    bad_url = f"{BINANCE_2026_MARKET_WS_BASE}?streams=btcusdt@depth@100ms"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url, expected_route="market")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID
    assert "Depth stream 'btcusdt@depth@100ms' forbidden on '/market/stream'" in str(exc_info.value)


def test_reject_cross_channel_mark_on_public_route() -> None:
    bad_url = f"{BINANCE_2026_PUBLIC_WS_BASE}?streams=btcusdt@markPrice@1s"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url, expected_route="public")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_reject_cross_channel_aggtrade_on_public_route() -> None:
    bad_url = f"{BINANCE_2026_PUBLIC_WS_BASE}?streams=btcusdt@aggTrade"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_url, expected_route="public")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID
