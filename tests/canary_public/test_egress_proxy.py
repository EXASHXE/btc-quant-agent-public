"""Offline-only gateway authorization, tunnel and audit tests (zero external I/O)."""

import pytest

from btc_quant_agent.platform.canary.public_egress import ProxyConfig, tunnel
from btc_quant_agent.platform.canary.public_network import DirectSockets
from btc_quant_agent.platform.canary.public_policy import PublicStop


class FakeTunnelSocket:
    def __init__(self, returned: bytes):
        self.returned = bytearray(returned)
        self.sent = []

    def sendall(self, value):
        self.sent.append(bytes(value))

    def recv(self, count):
        chunk = bytes(self.returned[:count])
        del self.returned[:count]
        return chunk


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:7897",
    "http://localhost:3128/",
    "socks5://127.0.0.1:7897",
    "socks5h://gateway.internal:1080",
])
def test_explicit_gateway_url_and_route_receipt(url):
    proxy = ProxyConfig.parse(url)
    assert proxy.host
    assert proxy.receipt()["egress_mode"] == "CONTROLLED_EGRESS_PROXY"
    assert proxy.receipt()["target_tls"] == "STRICT_VERIFICATION_REQUIRED"
    assert proxy.receipt()["physical_location"] == "NOT_INDEPENDENTLY_OBSERVED"


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:7897",
    "http://user:password@localhost:3128",
    "http://localhost:3128/admin",
    "http://localhost:3128?token=1",
    "http://localhost",
    "socks4://localhost:1080",
])
def test_reject_unscoped_or_authenticated_proxy(url):
    with pytest.raises(PublicStop, match="INVALID_EGRESS_PROXY_URL"):
        ProxyConfig.parse(url)


def test_http_connect_is_only_target_host_443_and_no_payload_mutation():
    sock = FakeTunnelSocket(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    proxy = ProxyConfig.parse("http://127.0.0.1:7897")
    tunnel(sock, proxy, "fapi.binance.com", 443, lambda: 10)
    assert sock.sent == [b"CONNECT fapi.binance.com:443 HTTP/1.1\r\nHost: fapi.binance.com:443\r\nProxy-Connection: Keep-Alive\r\n\r\n"]
    assert not sock.returned


@pytest.mark.parametrize("reply", [
    b"HTTP/1.1 403 Forbidden\r\n\r\n",
    b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n",
    b"HTTP/1.1 302 Found\r\nLocation: https://evil.example\r\n\r\n",
])
def test_proxy_denial_never_falls_back_to_another_host(reply):
    sock = FakeTunnelSocket(reply)
    with pytest.raises(PublicStop, match="EGRESS_HTTP_CONNECT_REJECTED"):
        tunnel(sock, ProxyConfig.parse("http://127.0.0.1:7897"), "fapi.binance.com", 443, lambda: 10)


def test_socks5_tunnel_targets_authorized_domain_with_remote_dns():
    # Greeting reply + CONNECT success, IPv4 bind + bind-port.
    sock = FakeTunnelSocket(b"\x05\x00\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
    tunnel(sock, ProxyConfig.parse("socks5h://127.0.0.1:1080"), "fstream.binance.com", 443, lambda: 10)
    assert sock.sent[0] == b"\x05\x01\x00"
    assert sock.sent[1].startswith(b"\x05\x01\x00\x03\x13fstream.binance.com")
    assert sock.sent[1].endswith(b"\x01\xbb")


@pytest.mark.parametrize("target,port", [
    ("api.binance.com", 443),
    ("fapi.binance.com", 80),
    ("example.org", 443),
])
def test_no_gateway_to_unapproved_destination(target, port):
    sock = FakeTunnelSocket(b"")
    with pytest.raises(PublicStop, match="EGRESS_TARGET_NOT_ALLOWLISTED"):
        tunnel(sock, ProxyConfig.parse("http://localhost:7897"), target, port, lambda: 10)
    assert not sock.sent


def test_direct_backend_does_not_pick_environment_proxy_unless_opted_in(monkeypatch):
    from btc_quant_agent.platform.canary.public_io import HttpWsBackend
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
    monkeypatch.delenv("L4_CONTROLLED_EGRESS", raising=False)
    b = HttpWsBackend()
    b.set_guard(lambda: 10)
    assert b.route_info["egress_mode"] == "DIRECT"


def test_opted_in_backend_uses_environment_gateway_and_reports_route(monkeypatch):
    from btc_quant_agent.platform.canary.public_io import HttpWsBackend
    monkeypatch.setenv("L4_CONTROLLED_EGRESS", "1")
    monkeypatch.setenv("L4_EGRESS_PROXY_URL", "socks5h://127.0.0.1:7897")
    b = HttpWsBackend()
    b.set_guard(lambda: 10)
    assert b.route_info["egress_mode"] == "CONTROLLED_EGRESS_PROXY"
    assert b.route_info["proxy_port"] == 7897
    assert b.direct.proxy.scheme == "socks5h"


def test_missing_explicit_gateway_fails_closed(monkeypatch):
    from btc_quant_agent.platform.canary.public_io import HttpWsBackend
    monkeypatch.setenv("L4_CONTROLLED_EGRESS", "1")
    for name in ("L4_EGRESS_PROXY_URL", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
    b = HttpWsBackend()
    with pytest.raises(PublicStop, match="EXPLICIT_EGRESS_PROXY_NOT_CONFIGURED"):
        b.set_guard(lambda: 10)


def test_unknown_target_rejected_before_any_dns(monkeypatch):
    def never(*a, **kw):
        raise AssertionError("DNS should not be attempted")
    monkeypatch.setattr("socket.getaddrinfo", never)
    d = DirectSockets(lambda: 10, proxy_url="http://127.0.0.1:7897")
    with pytest.raises(PublicStop, match="NETWORK_HOST_OR_ROUTE_FORBIDDEN"):
        d.connect_tcp("example.org", 443)
