"""Tests for proxy_route.py: Binance 2026 routed URLs, explicit Clash proxy, and network diagnostic."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.connector import BinancePublicFeedClient
from market_data.forward_public_feed_r1.proxy_route import (
    BINANCE_2026_MARKET_WS_BASE,
    BINANCE_2026_PUBLIC_WS_BASE,
    NetworkErrorCode,
    NetworkRouteError,
    ProxyRouteConfig,
    build_2026_market_stream_url,
    build_2026_public_stream_url,
    detect_wsl2_networking,
    probe_tcp_socket,
    run_desensitized_network_diagnostic,
    sanitize_env_proxy_map,
    validate_2026_routed_url,
)


def test_proxy_route_config_validation_modes() -> None:
    # Valid modes
    c1 = ProxyRouteConfig(mode="disabled")
    c1.validate()
    assert c1.to_proxy_url() is None

    c2 = ProxyRouteConfig(mode="public-direct")
    c2.validate()
    assert c2.to_proxy_url() is None

    c3 = ProxyRouteConfig(mode="public-clash-explicit", kind="http", host="127.0.0.1", port=7890)
    c3.validate()
    assert c3.to_proxy_url() == "http://127.0.0.1:7890"

    c4 = ProxyRouteConfig(mode="public-clash-explicit", kind="socks5h", host="127.0.0.1", port=7891)
    c4.validate()
    assert c4.to_proxy_url() == "socks5h://127.0.0.1:7891"

    # Invalid mode
    with pytest.raises(NetworkRouteError) as exc_info:
        ProxyRouteConfig(mode="invalid_mode").validate()
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_proxy_route_config_validation_missing_host_or_port() -> None:
    # Missing host
    with pytest.raises(NetworkRouteError) as exc_info:
        ProxyRouteConfig(mode="public-clash-explicit", host=None, port=7890).validate()
    assert exc_info.value.code == NetworkErrorCode.PROXY_CONNECT_FAILED

    # Missing port
    with pytest.raises(NetworkRouteError) as exc_info:
        ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=None).validate()
    assert exc_info.value.code == NetworkErrorCode.PROXY_CONNECT_FAILED

    # Out of range port
    with pytest.raises(NetworkRouteError) as exc_info:
        ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=70000).validate()
    assert exc_info.value.code == NetworkErrorCode.PROXY_CONNECT_FAILED

    # Unsupported kind
    with pytest.raises(NetworkRouteError) as exc_info:
        ProxyRouteConfig(mode="public-clash-explicit", kind="ftp", host="127.0.0.1", port=7890).validate()
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_proxy_route_sanitized_dict() -> None:
    cfg = ProxyRouteConfig(mode="public-clash-explicit", kind="http", host="127.0.0.1", port=7897, route_epoch="ep-1")
    d = cfg.to_sanitized_dict()
    assert d["mode"] == "public-clash-explicit"
    assert d["host"] == "127.0.0.1"
    assert d["port"] == 7897
    assert d["route_epoch"] == "ep-1"
    assert d["has_proxy"] is True
    assert "password" not in d
    assert "token" not in d


def test_build_2026_urls() -> None:
    pub_url = build_2026_public_stream_url("BTCUSDT")
    assert pub_url == f"{BINANCE_2026_PUBLIC_WS_BASE}?streams=btcusdt@depth@100ms"

    mkt_url = build_2026_market_stream_url("BTCUSDT")
    assert mkt_url == f"{BINANCE_2026_MARKET_WS_BASE}?streams=btcusdt@aggTrade/btcusdt@kline_1m/btcusdt@markPrice@1s"


def test_validate_2026_routed_url_rejects_legacy_unrouted() -> None:
    legacy_url = "wss://fstream.binance.com/stream?streams=btcusdt@aggTrade"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(legacy_url)
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID
    assert "deprecated since 2026-04-23" in str(exc_info.value)


def test_validate_2026_routed_url_rejects_cross_channel_contamination() -> None:
    # Market stream on public route
    bad_pub = f"{BINANCE_2026_PUBLIC_WS_BASE}?streams=btcusdt@kline_1m"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_pub, expected_route="public")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID

    # Depth stream on market route
    bad_mkt = f"{BINANCE_2026_MARKET_WS_BASE}?streams=btcusdt@depth@100ms"
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(bad_mkt, expected_route="market")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_validate_2026_routed_url_rejects_private_and_other_products() -> None:
    # Coin-M
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url("wss://dapi.binance.com/ws/btcusdt")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID

    # Spot
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url("wss://api.binance.com/ws/btcusdt")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID

    # Private keyword listenKey
    with pytest.raises(NetworkRouteError) as exc_info:
        validate_2026_routed_url(f"{BINANCE_2026_PUBLIC_WS_BASE}?listenKey=abc")
    assert exc_info.value.code == NetworkErrorCode.BINANCE_ROUTING_INVALID


def test_build_urllib_opener_and_ws_proxy() -> None:
    # Disabled
    cfg_dis = ProxyRouteConfig(mode="disabled")
    with pytest.raises(NetworkRouteError) as exc_info:
        cfg_dis.build_urllib_opener()
    assert exc_info.value.code == NetworkErrorCode.NETWORK_DISABLED

    with pytest.raises(NetworkRouteError) as exc_info:
        cfg_dis.get_websockets_proxy()
    assert exc_info.value.code == NetworkErrorCode.NETWORK_DISABLED

    # Direct
    cfg_dir = ProxyRouteConfig(mode="public-direct")
    opener_dir = cfg_dir.build_urllib_opener()
    assert opener_dir is not None
    assert cfg_dir.get_websockets_proxy() is None

    # Explicit
    cfg_exp = ProxyRouteConfig(mode="public-clash-explicit", kind="http", host="127.0.0.1", port=7890)
    opener_exp = cfg_exp.build_urllib_opener()
    assert opener_exp is not None
    assert cfg_exp.get_websockets_proxy() == "http://127.0.0.1:7890"


def test_detect_wsl2_networking() -> None:
    info = detect_wsl2_networking()
    assert "os" in info
    assert "python_version" in info
    assert "is_wsl" in info
    assert "wsl_network_mode" in info


def test_sanitize_env_proxy_map() -> None:
    with patch.dict(os.environ, {"HTTP_PROXY": "http://user:secret123@127.0.0.1:7890", "HTTPS_PROXY": "http://127.0.0.1:7890"}):
        m = sanitize_env_proxy_map()
        assert "secret123" not in m["HTTP_PROXY"]
        assert "***" in m["HTTP_PROXY"]
        assert m["HTTPS_PROXY"] == "http://127.0.0.1:7890"


def test_probe_tcp_socket_closed_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 65530))],
    )
    assert probe_tcp_socket("127.0.0.1", 65530, timeout=0.2) is False


def test_run_desensitized_network_diagnostic_disabled() -> None:
    cfg = ProxyRouteConfig(mode="disabled")
    diag = run_desensitized_network_diagnostic(cfg)
    assert diag["diagnostic_code"] == "NETWORK_DISABLED"
    assert diag["configured_route"]["mode"] == "disabled"


def test_run_desensitized_network_diagnostic_closed_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 65530))],
    )
    cfg = ProxyRouteConfig(mode="public-clash-explicit", kind="http", host="127.0.0.1", port=65530)
    diag = run_desensitized_network_diagnostic(cfg)
    assert diag["diagnostic_code"] == "PROXY_PORT_CLOSED"
    assert diag["layers"]["layer_1_local_tcp"]["status"] == "FAILED"


def test_connector_with_proxy_config() -> None:
    cfg = ProxyRouteConfig(mode="public-clash-explicit", kind="http", host="127.0.0.1", port=7890)
    client = BinancePublicFeedClient(symbol="BTCUSDT", proxy_config=cfg)
    assert client.network_mode == "public-clash-explicit"
    assert client.proxy_config == cfg
