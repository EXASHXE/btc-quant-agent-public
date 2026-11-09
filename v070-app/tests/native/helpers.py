"""Fabricated keys, certificates, clock, exchange and CONNECT server. Loopback only."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import select
import socket
import ssl
import threading
import time

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.x509.oid import NameOID
from websockets.server import ServerProtocol
from websockets.http11 import Request

from btc_quant_agent.platform.native.clock import Clock
from btc_quant_agent.platform.native.contract import (
    AuditBody,
    AuditEnvelope,
    Envelope,
    Grant,
    Policy,
    canonical,
    digest,
    source_hash,
)
from btc_quant_agent.platform.owner_verifier import signed_bytes


class QAClock(Clock):
    def __init__(self, wall):
        super().__init__()
        self.wall = wall
        self.mono = 1000000
        self.step = 0

    def pair(self):
        self.mono += 1
        self.wall += 1
        return {"wall_ms": self.wall + self.step, "mono_before_ms": self.mono, "mono_after_ms": self.mono}


def key(key_id):
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return private, {
        key_id: {
            "public_key_base64": base64.b64encode(raw).decode(),
            "public_key_sha256": hashlib.sha256(raw).hexdigest(),
            "independently_verified": True,
            "verified_owner_reference": "FABRICATED_QA_ONLY",
        }
    }


def sign(body, key_id, private, cls):
    return cls(
        grant=body,
        key_id=key_id,
        signature_base64=base64.b64encode(private.sign(signed_bytes(body))).decode(),
    )


def authority(policy, output, now, **changes):
    owner, owners = key("SYNTHETIC_OWNER")
    auditor, auditors = key("SYNTHETIC_AUDITOR")
    fields = dict(
        exposure="SYNTHETIC_NETWORK",
        endpoint=policy.endpoint,
        clock_endpoint=policy.clock_endpoint,
        streams=policy.streams,
        source_sha256=source_hash(),
        executable_sha256="a" * 64,
        config_sha256=digest(policy.model_dump(mode="json")),
        rights_sha256="b" * 64,
        session_id="SYNTHETIC_" + hashlib.sha256(str(output).encode()).hexdigest()[:16],
        output=str(output.absolute()),
        issued_ms=now - 1000,
        start_ms=now - 100,
        end_ms=now + 100000,
        messages_max=2000,
        requests_max=100,
        outgoing_frames_max=100,
        storage_bytes_max=134217728,
        retention_seconds=3600,
        auditor_key_id="SYNTHETIC_AUDITOR",
    )
    fields.update(changes)
    grant = Grant(**fields)
    envelope = sign(grant, "SYNTHETIC_OWNER", owner, Envelope)
    audit = sign(
        AuditBody(
            grant_sha256=digest(grant.model_dump(mode="json")),
            rights_sha256="b" * 64,
            independent_reference="SYNTHETIC_ONLY",
        ),
        "SYNTHETIC_AUDITOR",
        auditor,
        AuditEnvelope,
    )
    roots = {"owner": owners, "auditor": auditors, "rights_sha256": "b" * 64}
    return grant, envelope, audit, roots


def certificates(directory, wrong=False):
    private = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "FABRICATED_LOCAL_CA")])
    names = ["wrong.invalid"] if wrong else ["fstream.binance.com", "fapi.binance.com"]
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False)
        .sign(private, hashes.SHA256())
    )
    directory.mkdir(parents=True, exist_ok=True)
    cert = directory / "synthetic-cert.pem"
    pem = directory / "synthetic-key.pem"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    pem.write_bytes(
        private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    return cert, pem


class LocalVenue:
    def __init__(self, directory, clock, messages, *, deny=False, wrong_cert=False, disconnect=False):
        self.clock, self.messages, self.deny, self.disconnect = clock, messages, deny, disconnect
        self.delay = 0.001
        self.cert, self.pem = certificates(directory, wrong_cert)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(self.cert, self.pem)
        self.sni = []
        context.set_servername_callback(lambda _sock, name, _ctx: self.sni.append(name))
        self.context = context
        self.target = self.listen()
        self.proxy = self.listen()
        self.targets = []
        self.errors = []
        self.done = threading.Event()
        self.workers = []
        self.sockets = []
        self.start(self.accept_target)
        self.start(self.accept_proxy)

    @staticmethod
    def listen():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        s.listen(32)
        s.settimeout(0.1)
        return s

    @property
    def policy(self):
        return Policy(proxy_ip="127.0.0.1", proxy_port=self.proxy.getsockname()[1])

    def start(self, fn, *args):
        t = threading.Thread(target=fn, args=args, daemon=True)
        self.workers.append(t)
        t.start()

    def accept_target(self):
        while not self.done.is_set():
            try:
                sock, _ = self.target.accept()
            except (TimeoutError, OSError):
                continue
            self.sockets.append(sock)
            self.start(self.handle_target, sock)

    def accept_proxy(self):
        while not self.done.is_set():
            try:
                sock, _ = self.proxy.accept()
            except (TimeoutError, OSError):
                continue
            self.sockets.append(sock)
            self.start(self.handle_proxy, sock)

    @staticmethod
    def head(sock):
        b = bytearray()
        while not b.endswith(b"\r\n\r\n"):
            d = sock.recv(1)
            if not d:
                raise EOFError()
            b.extend(d)
            if len(b) > 16384:
                raise ValueError("LOCAL_HEADER_LIMIT")
        return bytes(b)

    def handle_proxy(self, sock):
        target = None
        try:
            sock.settimeout(3)
            request = self.head(sock)
            self.targets.append(request.split(b"\r\n")[0].decode())
            if self.deny:
                sock.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            target = socket.create_connection(self.target.getsockname(), timeout=3)
            self.sockets.append(target)
            sock.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            while not self.done.is_set():
                ready, _, _ = select.select([sock, target], [], [], 0.1)
                for current in ready:
                    data = current.recv(65536)
                    if not data:
                        return
                    (target if current is sock else sock).sendall(data)
        except (OSError, EOFError):
            pass
        finally:
            sock.close()
            if target:
                target.close()

    def handle_target(self, sock):
        try:
            with self.context.wrap_socket(sock, server_side=True) as tls:
                tls.settimeout(3)
                head = self.head(tls)
                if head.startswith(b"GET /fapi/v1/time "):
                    body = canonical(
                        {
                            "serverTime": self.clock.wall
                            if hasattr(self.clock, "wall")
                            else self.clock.pair()["wall_ms"]
                        }
                    )
                    tls.sendall(
                        b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
                    )
                    return
                protocol = ServerProtocol(max_size=65536)
                protocol.receive_data(head)
                request = next(e for e in protocol.events_received() if isinstance(e, Request))
                protocol.send_response(protocol.accept(request))
                for data in protocol.data_to_send():
                    tls.sendall(data)
                if self.disconnect:
                    return
                protocol.send_ping(b"local-only")
                for data in protocol.data_to_send():
                    tls.sendall(data)
                for message in self.messages:
                    protocol.send_text(canonical(message) if isinstance(message, dict) else message)
                    for data in protocol.data_to_send():
                        tls.sendall(data)
                    time.sleep(self.delay)
                protocol.send_close(1000, "local finite fixture")
                for data in protocol.data_to_send():
                    tls.sendall(data)
                try:
                    protocol.receive_data(tls.recv(4096))
                except OSError:
                    pass
        except (OSError, EOFError, StopIteration) as exc:
            self.errors.append(type(exc).__name__)

    def close(self):
        self.done.set()
        self.target.close()
        self.proxy.close()
        for sock in self.sockets:
            try:
                sock.close()
            except OSError:
                pass
        for t in self.workers:
            t.join(0.3)
