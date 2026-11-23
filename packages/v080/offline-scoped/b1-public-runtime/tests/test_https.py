from __future__ import annotations

import base64
import gzip
import json
import os
import socket
import ssl
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from quant_personal_public_b1.fixture import make_body
from quant_personal_public_b1.live import open_live
from quant_personal_public_b1.policy import KLINES, QUOTE, TIME, SourceBlocked
from quant_personal_public_b1.runtime import Runtime
from quant_personal_public_b1.store import Store, sha
from quant_personal_public_b1.wire import (
    FIXTURE,
    GENUINE,
    HOST,
    LOOPBACK,
    HttpsTransport,
    LoopbackTarget,
    Request,
    WireLimits,
    json_body,
)


def identity(name):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])


def certificate(subject, subject_key, issuer, issuer_key, not_before, not_after, *, ca=False, san=None):
    builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
               .public_key(subject_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(not_before).not_valid_after(not_after)
               .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if san:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
    return builder.sign(issuer_key, hashes.SHA256())


@pytest.fixture
def certs(tmp_path):
    now = datetime.now(UTC)
    root_key = ec.generate_private_key(ec.SECP256R1())
    issuer = identity("Quant B1 test CA")
    root = certificate(issuer, root_key, issuer, root_key, now-timedelta(days=30), now+timedelta(days=30), ca=True)
    pem = serialization.Encoding.PEM
    root_path = tmp_path / "ca.pem"
    root_path.write_bytes(root.public_bytes(pem))
    wrong_key = ec.generate_private_key(ec.SECP256R1())
    wrong = identity("Wrong test CA")
    wrong_ca = certificate(wrong, wrong_key, wrong, wrong_key,
                           now-timedelta(days=3), now+timedelta(days=3), ca=True)
    wrong_path = tmp_path / "wrong_ca.pem"
    wrong_path.write_bytes(wrong_ca.public_bytes(pem))
    paths = {}
    for name, sni, not_after in (("valid", HOST, now+timedelta(days=3)),
                                 ("wrong_host", "other.example.test", now+timedelta(days=3)),
                                 ("expired", HOST, now-timedelta(days=1))):
        leaf_key = ec.generate_private_key(ec.SECP256R1())
        leaf = certificate(identity(sni), leaf_key, issuer, root_key, now-timedelta(days=5), not_after, san=sni)
        crt, key = tmp_path / f"{name}.pem", tmp_path / f"{name}.key"
        crt.write_bytes(leaf.public_bytes(pem))
        key.write_bytes(leaf_key.private_bytes(pem, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
        paths[name] = crt, key
    return root_path, wrong_path, paths


def response(body=b'{"serverTime":1735689720000}', *, code=200, headers=None):
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body)), **(headers or {})}
    metadata = "".join(f"{key}: {value}\r\n" for key, value in headers.items())
    return f"HTTP/1.1 {code} Local Fixture\r\n{metadata}\r\n".encode() + body


@contextmanager
def local_https(certs, handler, *, cert="valid", ca_index=0, handshake_wait=0):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(*certs[2][cert])
    calls = []
    failures = []
    serving = threading.Event()
    serving.set()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(.05)
        port = listener.getsockname()[1]

        def serve():
            while serving.is_set():
                try:
                    wire, _ = listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    return
                with wire:
                    try:
                        wire.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        if handshake_wait:
                            time.sleep(handshake_wait)
                        wire.settimeout(1)
                        with ctx.wrap_socket(wire, server_side=True) as peer:
                            req = b""
                            while b"\r\n\r\n" not in req and len(req) < 4096:
                                chunk = peer.recv(4096)
                                if not chunk:
                                    break
                                req += chunk
                            if req:
                                calls.append(req)
                                handler(peer, req)
                    except (OSError, ssl.SSLError):
                        continue
                    except Exception as exc:
                        failures.append(exc)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            yield LoopbackTarget("127.0.0.1", port, certs[ca_index]), calls
        finally:
            serving.clear()
            thread.join(2)
        if failures:
            raise failures[0]


@pytest.mark.parametrize("kind,ca_index", [("wrong_host", 0), ("expired", 0), ("valid", 1)])
def test_certificate_chain_hostname_and_expiry(certs, kind, ca_index):
    with local_https(certs, lambda peer, _: peer.sendall(response()), cert=kind, ca_index=ca_index) as (target, seen):
        with pytest.raises(SourceBlocked, match="TLS_VERIFICATION_FAILED"):
            HttpsTransport(target).send(Request(TIME, {}), 500)
        assert not seen


def test_trusted_loopback_gzip_and_provenance(certs):
    payload = b'{"serverTime":1735689720123}'
    encoded = gzip.compress(payload, mtime=0)
    with local_https(certs, lambda peer, _: peer.sendall(
            response(encoded, headers={"Content-Encoding": "gzip"}))) as (target, seen):
        answer = HttpsTransport(target).send(Request(TIME, {}), 500)
        assert answer.complete and answer.body == payload and answer.encoded_body == encoded
        assert answer.tls["verification"] == "CERT_REQUIRED_AND_HOSTNAME"
        assert answer.tls["peer"] == "127.0.0.1"
        assert answer.tls["sni"] == HOST
        assert answer.wire_bytes > len(encoded)
        assert seen[0].startswith(b"GET /fapi/v1/time HTTP/1.1\r\n")
        assert b"X-MBX-APIKEY" not in seen[0]
        assert f"Host: {HOST}".encode() in seen[0]


@pytest.mark.parametrize("candidate,reason", [
    (Request(TIME, {}, method="POST"), "FORBIDDEN_ROUTE"),
    (Request(TIME, {"signature": "synthetic"}), "FORBIDDEN_QUERY"),
    (Request(TIME, {"apiKey": "synthetic"}), "FORBIDDEN_QUERY"),
    (Request(TIME, {}, host="evil.example.test"), "ORIGIN_NOT_APPROVED"),
    (Request(TIME, {}, host="FAPI.BINANCE.COM"), "ORIGIN_NOT_APPROVED"),
    (Request(TIME, {}, port=9443), "ORIGIN_NOT_APPROVED"),
    (Request("https://fapi.binance.com/fapi/v1/time", {}), "FORBIDDEN_ROUTE"),
    (Request("/fapi/v1/time%00", {}), "FORBIDDEN_ROUTE"),
    (Request("/fapi/v3/account", {}), "FORBIDDEN_ROUTE"),
    (Request("/fapi/v1/listenKey", {}), "FORBIDDEN_ROUTE"),
    (Request("/fapi/v1/rpiDepth", {}), "FORBIDDEN_ROUTE"),
    (Request("/fapi/v1/aggTrades", {}), "FORBIDDEN_ROUTE"),
    (Request(KLINES, {"symbol": "DOGEUSDT", "interval": "1d", "startTime": 0, "endTime": 0, "limit": 1}),
     "FORBIDDEN_SYMBOL"),
    (Request(KLINES, {"symbol": "BTCUSDT", "interval": "1m", "startTime": 0, "endTime": 0, "limit": 1}),
     "FORBIDDEN_INTERVAL"),
])
def test_final_send_guard_precedes_socket(monkeypatch, tmp_path, candidate, reason):
    def no_dispatch(*_args, **_kwargs):
        pytest.fail("socket created before final request admission")

    monkeypatch.setattr(socket, "socket", no_dispatch)
    with pytest.raises(SourceBlocked, match=reason):
        HttpsTransport(LoopbackTarget("127.0.0.1", 1, tmp_path / "unused")).send(candidate, 500)


@pytest.mark.parametrize("address", ["1.1.1.1", HOST, "localhost", "0.0.0.0", "::ffff:192.0.2.1"])
def test_non_loopback_physical_peer_rejected(tmp_path, address):
    with pytest.raises(SourceBlocked, match="LOOPBACK_"):
        HttpsTransport(LoopbackTarget(address, 443, tmp_path / "unused")).send(Request(TIME, {}), 500)


def test_dormant_genuine_gate_ignores_env_and_self_claimed_documents(monkeypatch, tmp_path):
    for name in ("QUANT_LIVE", "ENABLE_LIVE", "BINANCE_API_KEY", "BINANCE_API_SECRET", "HTTPS_PROXY"):
        monkeypatch.setenv(name, "synthetic-untrusted-value")
    monkeypatch.setattr(socket, "socket", lambda *_: pytest.fail("live gate attempted socket creation"))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_: pytest.fail("live gate attempted DNS"))
    for scope, activation in ((None, None), ({"live_requests_enabled": True}, {"controller_approved": True})):
        with pytest.raises(SourceBlocked, match="LIVE_CAPABILITY_DORMANT"):
            open_live(operating_scope=scope, controller_activation=activation)
    assert not list(tmp_path.iterdir())


def test_redirect_never_followed_and_never_falls_back_to_fixtures(certs, tmp_path):
    def redirect(peer, _):
        peer.sendall(response(b"", code=302, headers={"Location": "https://elsewhere.invalid/private"}))

    with local_https(certs, redirect) as (target, seen):
        out = Runtime.loopback(tmp_path / "loopback", HttpsTransport(target)).scan(("BTCUSDT",))
        assert out["source_status"] == "SOURCE_BLOCKED" and out["source_origin"] == LOOPBACK
        assert not out["markets"] and out["issue"]["code"] == "HTTP_REDIRECT"
        assert len(seen) == 1


@pytest.mark.parametrize("kind", ["transfer", "decoded", "truncated", "trailing_gzip", "transfer_header"])
def test_wire_size_encoding_and_length_bounds(certs, kind):
    body = b"x" * 3000
    limits = WireLimits(max_transfer_bytes=1000, max_decoded_bytes=4000)
    if kind == "transfer":
        wire, expected = response(body), "ENCODED_TRANSFER_TOO_LARGE"
    elif kind == "decoded":
        wire = response(gzip.compress(body, mtime=0), headers={"Content-Encoding": "gzip"})
        limits = WireLimits(max_transfer_bytes=1000, max_decoded_bytes=200)
        expected = "DECODED_PAYLOAD_TOO_LARGE"
    elif kind == "truncated":
        wire = response(b"abc", headers={"Content-Length": "9"})
        expected = "TRUNCATED_HTTP_BODY"
    elif kind == "transfer_header":
        wire = response(b"abc", headers={"Transfer-Encoding": "chunked"})
        expected = "AMBIGUOUS_HTTP_LENGTH"
    else:
        wire = response(gzip.compress(b"abc", mtime=0) + b"tail", headers={"Content-Encoding": "gzip"})
        expected = "INVALID_GZIP_TRAILING_DATA"
    with local_https(certs, lambda peer, _: peer.sendall(wire)) as (target, _):
        reply = HttpsTransport(target, limits).send(Request(TIME, {}), 500)
        assert not reply.complete and reply.issue == expected and not reply.body


def test_slow_tls_handshake_times_out(certs):
    with local_https(certs, lambda peer, _: peer.sendall(response()), handshake_wait=.20) as (target, seen):
        with pytest.raises(SourceBlocked, match="TRANSIENT_WIRE_FAILURE"):
            HttpsTransport(target, WireLimits(connect_ms=40)).send(Request(TIME, {}), 500)
        assert not seen


@pytest.mark.parametrize("idle_ms,whole_ms", [(90, 900), (180, 260)])
def test_idle_or_whole_deadline_stops_stream(certs, idle_ms, whole_ms):
    def drip(peer, _):
        header = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 30\r\n\r\n"
        peer.sendall(header)
        for _ in range(6):
            time.sleep(.13)
            peer.sendall(b"x" * 5)

    with local_https(certs, drip) as (target, _):
        answer = HttpsTransport(target, WireLimits(idle_ms=idle_ms)).send(Request(TIME, {}), whole_ms)
        assert not answer.complete and answer.issue == "HTTP_BODY_INCOMPLETE"


def test_loopback_schema_malformed_and_venue_denial(certs, tmp_path):
    for name, wire, reason in (("bad", response(b"invalid json"), "MALFORMED_JSON"),
                               ("denied", response(b'{"msg":"blocked"}', code=451), "HTTP_451"),
                               ("shape", response(b'[]'), "EXPECTED_OBJECT"), ("unknown", response(b'{}', code=299), "HTTP_299")):
        with local_https(certs, lambda peer, _, raw=wire: peer.sendall(raw)) as (target, seen):
            runtime = Runtime.loopback(tmp_path / name, HttpsTransport(target))
            result = runtime.scan(("BTCUSDT",))
            assert result["issue"]["code"] == reason and result["source_origin"] == LOOPBACK
            assert not result["data_ready"] and not result["markets"]
            assert len(seen) == 1
            if name == "denied":
                restarted = Runtime.loopback(tmp_path / name, HttpsTransport(target))
                assert restarted.scan(("BTCUSDT",))["issue"]["code"] == reason and len(seen) == 1


def test_loopback_integrated_scan_origin_and_receipts(certs, tmp_path):
    # A stable fabricated venue epoch projected onto real monotonic time supports genuine TLS timings.
    start_ns = time.monotonic_ns()
    epoch_ms = 1_735_689_720_000
    numbers = {"startTime", "endTime", "limit"}

    def exchange(peer, raw):
        _, url, _ = raw.decode("ascii").splitlines()[0].split()
        target = urlsplit(url)
        params = {k: int(v) if k in numbers else v for k, v in parse_qsl(target.query)}
        stamp = epoch_ms + (time.monotonic_ns() - start_ns) // 1_000_000
        body = make_body(target.path, params, stamp)
        encoded = json.dumps(body).encode()
        if target.path == QUOTE:
            peer.sendall(response(gzip.compress(encoded, mtime=0), headers={"Content-Encoding": "gzip"}))
        else:
            peer.sendall(response(encoded))

    db = tmp_path / "loopback"
    with local_https(certs, exchange) as (target, seen):
        runtime = Runtime.loopback(db, HttpsTransport(target))
        result = runtime.scan(("BTCUSDT",))
        assert result["data_ready"], result
        assert result["source_origin"] == LOOPBACK and result["strategy_status"] == "NOT_EVALUATED"
        assert len(seen) == 15
        assert runtime.store.snapshot() == result
        receipts = runtime.budget.evidence(result["scan_id"])
        assert all(row["response"]["tls"]["verification"] == "CERT_REQUIRED_AND_HOSTNAME" for row in receipts)
        assert json_body(runtime.store.raw(receipts[0]["receipt_id"]))["serverTime"]
        raw_evidence = {}
        with runtime.store.connect() as conn:
            for row in receipts:
                attempt = row["receipt_id"]
                observed = runtime.store.raw(attempt)
                encoded = conn.execute("SELECT encoded FROM attempts WHERE id=?", (attempt,)).fetchone()[0]
                if row["route"] == QUOTE:
                    assert sha(encoded) == row["response"]["encoded_sha256"]
                    assert gzip.decompress(encoded) == observed
                raw_evidence[str(attempt)] = {
                    "body_base64": base64.b64encode(observed).decode(),
                    "compressed_entity_base64": base64.b64encode(encoded).decode() if encoded is not None else None,
                }
    for origin in (FIXTURE, GENUINE):
        with pytest.raises(SourceBlocked, match="DB_ORIGIN_MISMATCH"):
            Store(db, origin, "loopback-qa")
    if os.environ.get("B1_LOOPBACK_EVIDENCE"):
        path = Path(os.environ["B1_LOOPBACK_EVIDENCE"])
        path.write_text(json.dumps({"result": result, "receipts": receipts, "raw": raw_evidence}, indent=2) + "\n")
