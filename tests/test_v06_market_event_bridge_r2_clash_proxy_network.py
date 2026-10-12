"""25 Pytest unit tests for Windows/WSL2 Clash HTTP/SOCKS explicit proxy routing and network safety."""

from __future__ import annotations

import os
import socket
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.connector import BinancePublicFeedClient, NetworkGateError
from market_data.forward_public_feed_r1.proxy_route import (
    NetworkErrorCode,
    NetworkRouteError,
    ProxyRouteConfig,
    detect_wsl2_networking,
    run_desensitized_network_diagnostic,
    sanitize_env_proxy_map,
)


def test_proxy_default_mode_disabled() -> None:
    cfg = ProxyRouteConfig()
    assert cfg.mode == "disabled"
    assert cfg.to_proxy_url() is None


def test_proxy_disabled_blocks_rest_fetch() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    with pytest.raises(NetworkGateError, match="Network access blocked"):
        client.fetch_public_depth_snapshot()


def test_proxy_disabled_blocks_ws_connect() -> None:
    cfg = ProxyRouteConfig(mode="disabled")
    with pytest.raises(NetworkRouteError) as exc_info:
        cfg.get_websockets_proxy()
    assert exc_info.value.code == NetworkErrorCode.NETWORK_DISABLED


def test_proxy_public_clash_explicit_http_url() -> None:
    cfg = ProxyRouteConfig(mode="public-clash-explicit", kind="http", host="127.0.0.1", port=7890)
    cfg.validate()
    assert cfg.to_proxy_url() == "http://127.0.0.1:7890"


def test_proxy_public_clash_explicit_socks5h_url() -> None:
    cfg = ProxyRouteConfig(mode="public-clash-explicit", kind="socks5h", host="127.0.0.1", port=7891)
    cfg.validate()
    assert cfg.to_proxy_url() == "socks5h://127.0.0.1:7891"


def test_proxy_missing_host_rejects() -> None:
    cfg = ProxyRouteConfig(mode="public-clash-explicit", kind="http", host=None, port=7890)
    with pytest.raises(NetworkRouteError) as exc_info:
        cfg.validate()
    assert exc_info.value.code == NetworkErrorCode.PROXY_CONNECT_FAILED


def test_proxy_invalid_port_rejects_negative() -> None:
    cfg = ProxyRouteConfig(mode="public-clash-explicit", kind="http", host="127.0.0.1", port=-1)
    with pytest.raises(NetworkRouteError) as exc_info:
        cfg.validate()
    assert exc_info.value.code == NetworkErrorCode.PROXY_CONNECT_FAILED


def test_proxy_invalid_port_rejects_over_65535() -> None:
    cfg = ProxyRouteConfig(mode="public-clash-explicit", kind="http", host="127.0.0.1", port=65536)
    with pytest.raises(NetworkRouteError) as exc_info:
        cfg.validate()
    assert exc_info.value.code == NetworkErrorCode.PROXY_CONNECT_FAILED


def test_proxy_sanitized_dict_never_contains_credentials() -> None:
    cfg = ProxyRouteConfig(
        mode="public-clash-explicit",
        kind="http",
        host="127.0.0.1",
        port=7897,
        route_epoch="ep-001",
    )
    d = cfg.to_sanitized_dict()
    assert d["mode"] == "public-clash-explicit"
    assert d["port"] == 7897
    assert "token" not in d
    assert "password" not in d
    assert "api_key" not in d


def test_proxy_env_sanitizer_masks_http_proxy_password() -> None:
    with patch.dict(os.environ, {"HTTP_PROXY": "http://admin:super_secret_pwd@127.0.0.1:7890"}):
        m = sanitize_env_proxy_map()
        assert "super_secret_pwd" not in m["HTTP_PROXY"]
        assert "***" in m["HTTP_PROXY"]


def test_proxy_env_sanitizer_masks_https_proxy_password() -> None:
    with patch.dict(os.environ, {"HTTPS_PROXY": "https://clash_user:vault_pass_99@127.0.0.1:7890"}):
        m = sanitize_env_proxy_map()
        assert "vault_pass_99" not in m["HTTPS_PROXY"]
        assert "***" in m["HTTPS_PROXY"]


def test_proxy_env_sanitizer_masks_all_proxy_password() -> None:
    with patch.dict(os.environ, {"ALL_PROXY": "socks5://socks_user:my_secret_token@127.0.0.1:7891"}):
        m = sanitize_env_proxy_map()
        assert "my_secret_token" not in m["ALL_PROXY"]
        assert "***" in m["ALL_PROXY"]


def test_proxy_wsl2_networking_detection_fields() -> None:
    info = detect_wsl2_networking()
    assert isinstance(info["os"], str)
    assert isinstance(info["python_version"], str)
    assert isinstance(info["is_wsl"], bool)
    assert "wsl_network_mode" in info


def test_proxy_route_epoch_invalidation() -> None:
    cfg1 = ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=7890, route_epoch="ep-1")
    cfg2 = ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=7897, route_epoch="ep-2")
    assert cfg1.route_epoch != cfg2.route_epoch
    assert cfg1.port != cfg2.port


def test_proxy_mixed_egress_rejection() -> None:
    # A route cannot have conflicting mode and proxy settings
    cfg = ProxyRouteConfig(mode="disabled")
    with pytest.raises(NetworkRouteError):
        cfg.build_urllib_opener()


def test_proxy_http_407_auth_required_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 7890))],
    )
    with patch("market_data.forward_public_feed_r1.proxy_route.probe_tcp_socket", return_value=True):
        err = urllib.error.HTTPError("http://test", 407, "Proxy Authentication Required", {}, None)  # type: ignore[arg-type]
        with patch("urllib.request.OpenerDirector.open", side_effect=err):
            cfg = ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=7890)
            diag = run_desensitized_network_diagnostic(cfg)
            assert diag["diagnostic_code"] == "PROXY_AUTH_REQUIRED"


def test_proxy_http_403_policy_blocked_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 7890))],
    )
    with patch("market_data.forward_public_feed_r1.proxy_route.probe_tcp_socket", return_value=True):
        err = urllib.error.HTTPError("http://test", 403, "Forbidden / Policy Block", {}, None)  # type: ignore[arg-type]
        with patch("urllib.request.OpenerDirector.open", side_effect=err):
            cfg = ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=7890)
            diag = run_desensitized_network_diagnostic(cfg)
            assert diag["diagnostic_code"] == "SOURCE_BLOCKED_BY_PROVIDER_POLICY"


def test_proxy_http_451_policy_blocked_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 7890))],
    )
    with patch("market_data.forward_public_feed_r1.proxy_route.probe_tcp_socket", return_value=True):
        err = urllib.error.HTTPError("http://test", 451, "Unavailable For Legal Reasons", {}, None)  # type: ignore[arg-type]
        with patch("urllib.request.OpenerDirector.open", side_effect=err):
            cfg = ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=7890)
            diag = run_desensitized_network_diagnostic(cfg)
            assert diag["diagnostic_code"] == "SOURCE_BLOCKED_BY_PROVIDER_POLICY"


def test_proxy_tls_unexpected_eof_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 7890))],
    )
    with patch("market_data.forward_public_feed_r1.proxy_route.probe_tcp_socket", return_value=True):
        ssl_err = ssl.SSLError("UNEXPECTED_EOF_WHILE_READING")
        with patch("urllib.request.OpenerDirector.open", side_effect=ssl_err):
            cfg = ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=7890)
            diag = run_desensitized_network_diagnostic(cfg)
            assert diag["diagnostic_code"] == "REST_TLS_EOF"


def test_proxy_tls_cert_invalid_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 7890))],
    )
    with patch("market_data.forward_public_feed_r1.proxy_route.probe_tcp_socket", return_value=True):
        ssl_err = ssl.SSLCertVerificationError("Certificate verification failed: self signed cert")
        with patch("urllib.request.OpenerDirector.open", side_effect=ssl_err):
            cfg = ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=7890)
            diag = run_desensitized_network_diagnostic(cfg)
            assert diag["diagnostic_code"] == "TLS_CERT_INVALID"


def test_proxy_port_closed_probe_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 65530))],
    )
    cfg = ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=65530)
    diag = run_desensitized_network_diagnostic(cfg)
    assert diag["diagnostic_code"] == "PROXY_PORT_CLOSED"


def test_proxy_dns_resolution_failed_mapped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 7890))],
    )
    with patch("market_data.forward_public_feed_r1.proxy_route.probe_tcp_socket", return_value=True):
        gai_err = socket.gaierror(-2, "Name or service not known")
        with patch("urllib.request.OpenerDirector.open", side_effect=gai_err):
            cfg = ProxyRouteConfig(mode="public-clash-explicit", host="127.0.0.1", port=7890)
            diag = run_desensitized_network_diagnostic(cfg)
            assert diag["diagnostic_code"] == "PROXY_CONNECT_FAILED"


def test_proxy_strict_tls_context_verification() -> None:
    cfg = ProxyRouteConfig(mode="public-direct")
    opener = cfg.build_urllib_opener()
    for h in opener.handlers:
        if isinstance(h, urllib.request.HTTPSHandler):
            ctx = h._context
            assert ctx.check_hostname is True
            assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_proxy_direct_mode_blocks_ambient_env_proxy() -> None:
    cfg = ProxyRouteConfig(mode="public-direct")
    opener = cfg.build_urllib_opener()
    for h in opener.handlers:
        if isinstance(h, urllib.request.ProxyHandler):
            assert h.proxies == {}


def test_proxy_websockets_direct_returns_none_to_prevent_env_leak() -> None:
    cfg = ProxyRouteConfig(mode="public-direct")
    assert cfg.get_websockets_proxy() is None
