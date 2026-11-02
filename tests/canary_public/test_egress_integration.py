"""Real TLS over owned socket pairs; fabricated certificates and application replies only."""

import base64
import hashlib
import socket
import ssl
import subprocess
import threading
from types import SimpleNamespace

import httpx
import pytest

from btc_quant_agent.platform.canary.public_io import HttpWsBackend
from btc_quant_agent.platform.canary.public_network import DirectSockets, GuardedStream
from btc_quant_agent.platform.canary.public_policy import (
    DEFAULT_GRANT,
    PublicStop,
    current_source_hashes,
    load_scope,
)
from .fixtures import Clock


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    root = tmp_path_factory.mktemp("egress-test-certificates")
    result = {}
    for name, san in (
        ("valid", "DNS:fapi.binance.com,DNS:fstream.binance.com"),
        ("wrong", "DNS:wrong.example"),
    ):
        key, cert = root / (name + ".key"), root / (name + ".pem")
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=Fabricated TLS test",
                "-addext",
                "subjectAltName=" + san,
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            capture_output=True,
        )
        result[name] = key, cert
    return result


@pytest.mark.parametrize("client", ["http", "websocket"])
@pytest.mark.parametrize("case", ["valid", "untrusted", "wrong_hostname"])
def test_both_clients_verify_original_target_over_preconnected_tunnel(
    client, case, certificates, scope, monkeypatch
):
    monkeypatch.setenv("L4_CONTROLLED_EGRESS", "1")
    monkeypatch.setenv("L4_EGRESS_PROXY_URL", "http://127.0.0.1:7897")
    backend = HttpWsBackend()
    backend.set_guard(lambda: 5)
    backend.bind_scope(scope, Clock())
    key, certificate = certificates["wrong" if case == "wrong_hostname" else "valid"]
    if case != "untrusted":
        backend._tls().load_verify_locations(cafile=str(certificate))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(certificate), str(key))
    sni, requests, failures = [], [], []
    server_context.set_servername_callback(lambda sock, name, ctx: sni.append(name))
    left, right = socket.socketpair()
    right.settimeout(3)
    original_setsockopt = socket.socket.setsockopt

    def unix_pair_options(sock, level, option, value):
        # This offline carrier is AF_UNIX, so TCP_NODELAY has no meaning. TLS is real.
        if sock.family == socket.AF_UNIX and level == socket.IPPROTO_TCP and option == socket.TCP_NODELAY:
            return None
        return original_setsockopt(sock, level, option, value)

    monkeypatch.setattr(socket.socket, "setsockopt", unix_pair_options)

    def serve():
        try:
            with server_context.wrap_socket(right, server_side=True) as server:
                data = bytearray()
                while b"\r\n\r\n" not in data:
                    block = server.recv(4096)
                    if not block:
                        return
                    data.extend(block)
                    assert len(data) < 8192
                requests.append(bytes(data))
                if client == "http":
                    server.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
                else:
                    headers = dict(
                        line.split(b": ", 1) for line in bytes(data).split(b"\r\n")[1:] if b": " in line
                    )
                    nonce = next(
                        value for name, value in headers.items() if name.lower() == b"sec-websocket-key"
                    )
                    accept = base64.b64encode(
                        hashlib.sha1(nonce + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest()
                    )
                    server.sendall(
                        b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "
                        + accept
                        + b"\r\n\r\n"
                    )
                    server.recv(4096)
                    server.sendall(b"\x88\x02\x03\xe8")
        except ssl.SSLError as exc:
            failures.append(type(exc).__name__)
        except OSError as exc:
            failures.append(type(exc).__name__)

    worker = threading.Thread(target=serve, daemon=False)
    worker.start()
    target = "fapi.binance.com" if client == "http" else "fstream.binance.com"
    monkeypatch.setattr(
        backend.direct, "connect_tcp", lambda host, port, **kw: GuardedStream(left, backend.direct, host)
    )
    try:

        def connect():
            if client == "http":
                return backend.get("https://fapi.binance.com/fapi/v1/time", {}, 3, Clock())
            connection = backend.connect(scope.ws_url("public"), 3, lambda value: None)
            connection.close()
            return connection

        if case == "valid":
            connect()
            assert requests and b"Host: " + target.encode() in requests[0]
            assert backend.tls_evidence[0]["target_hostname"] == target
            assert backend.tls_evidence[0]["egress_mode"] == "CONTROLLED_EGRESS_PROXY"
        else:
            with pytest.raises((ssl.SSLError, httpx.ConnectError), match="CERTIFICATE_VERIFY_FAILED"):
                connect()
            assert not requests and not backend.tls_evidence
        assert sni == [target]
    finally:
        backend.abort()
        backend.close()
        left.close()
        right.close()
        worker.join(timeout=4)
        assert not worker.is_alive()


def test_insecure_tls_context_rejected_before_io():
    backend = HttpWsBackend()
    backend.tls_context = SimpleNamespace(check_hostname=False, verify_mode=ssl.CERT_NONE)
    with pytest.raises(PublicStop, match="TLS_VERIFICATION_REQUIRED"):
        backend._tls()


def test_current_source_and_proxy_route_are_grant_bound(scope):
    assert scope.raw["policy"]["source_fingerprint"]
    scope.validate_route(
        {
            "egress_mode": "CONTROLLED_EGRESS_PROXY",
            "proxy_host": "127.0.0.1",
            "proxy_port": 7897,
            "tunnel_type": "SOCKS5",
        }
    )
    with pytest.raises(PublicStop, match="EGRESS_ROUTE_GRANT_MISMATCH"):
        scope.validate_route(
            {
                "egress_mode": "CONTROLLED_EGRESS_PROXY",
                "proxy_host": "other.example",
                "proxy_port": 7897,
                "tunnel_type": "HTTP_CONNECT",
            }
        )
    assert current_source_hashes()


def test_source_manifest_mismatch_blocks_before_network(monkeypatch):
    monkeypatch.setattr("btc_quant_agent.platform.canary.public_policy.current_source_hashes", lambda: {})
    with pytest.raises(PublicStop, match="CURRENT_SOURCE_BINDING_MISMATCH"):
        load_scope(DEFAULT_GRANT)


def test_old_sealed_grant_is_not_silently_rebound(scope):
    old = DEFAULT_GRANT.with_name("source_grant_20261030.json")
    with pytest.raises(PublicStop):
        load_scope(old)


def test_opted_in_fallback_is_selected_once_and_must_match_grant(scope, monkeypatch):
    monkeypatch.setenv("L4_CONTROLLED_EGRESS", "1")
    monkeypatch.delenv("L4_EGRESS_PROXY_URL", raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7897")
    backend = HttpWsBackend()
    backend.set_guard(lambda: 5)
    backend.bind_scope(scope, Clock())
    assert backend.route_info["egress_mode"] == "CONTROLLED_EGRESS_PROXY"
    monkeypatch.setenv("HTTPS_PROXY", "http://other.example:1080")
    assert backend.route_info["proxy_host"] == "127.0.0.1"


def test_tunnel_slowloris_has_one_total_deadline(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("btc_quant_agent.platform.canary.public_network.time.monotonic", lambda: now[0])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 7897))])

    class SlowSocket:
        closed = False

        def fileno(self):
            return -1 if self.closed else 123

        def settimeout(self, timeout):
            assert timeout > 0

        def connect(self, address):
            pass

        def sendall(self, data):
            pass

        def recv(self, count):
            now[0] += 0.6
            return b"H"

        def close(self):
            self.closed = True

    sock = SlowSocket()
    monkeypatch.setattr(socket, "socket", lambda *a: sock)
    backend = DirectSockets(lambda: 10, proxy_url="http://127.0.0.1:7897")
    with pytest.raises(PublicStop, match="EGRESS_HANDSHAKE_TIMEOUT"):
        backend.connect_tcp("fapi.binance.com", 443, timeout=1)
    assert sock.closed and now[0] < 2
