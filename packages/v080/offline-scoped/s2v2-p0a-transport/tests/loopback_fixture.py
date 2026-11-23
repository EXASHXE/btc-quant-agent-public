"""Test-only certificates and TCP listeners on the reserved loopback name."""

import datetime as dt
import json
import socket
import socketserver
import ssl
import struct
import threading
import time
import warnings
from contextlib import contextmanager
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from fixture_support import PRIVATE, Scenario, save, stamp
from quant_personal_public_b1.fixture import make_body
from quant_s2rb import FIXTURE_DOMAIN, FIXTURE_EVIDENCE, FIXTURE_HOST, SCHEMA
from quant_s2rb.runtime import Paths
from quant_s2v2.protocol import canonical, sha

RB_WHEEL = next(Path("/mnt/inputs").glob("quant_s2v2_release_bound*.whl"))


def certificates(directory):
    folder = directory / "ca"
    folder.mkdir(mode=0o700)
    now = dt.datetime.now(dt.UTC)

    def certificate(label, parent=None, signing_key=None, hostname=None):
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, label)])
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        builder = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject if parent is None else parent.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=10))
            .not_valid_after(now + dt.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=hostname is None, path_length=None), True)
        )
        if hostname:
            builder = builder.add_extension(
                x509.SubjectAlternativeName([x509.DNSName(hostname)]), False
            )
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False
            )
        cert = builder.sign(signing_key or key, hashes.SHA256())
        return key, cert

    ca_key, ca = certificate("SYNTHETIC QA ONLY S2 test CA")
    other_key, other = certificate("SYNTHETIC QA ONLY unrelated CA")
    results = {"ca": ca.public_bytes(serialization.Encoding.PEM)}
    for name, root, root_key, host in [
        ("good", ca, ca_key, FIXTURE_HOST),
        ("untrusted", other, other_key, FIXTURE_HOST),
        ("hostname", ca, ca_key, "other.s2v2.test"),
    ]:
        key, cert = certificate(f"synthetic {host}", root, root_key, host)
        path = folder / f"{name}.pem"
        path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            + cert.public_bytes(serialization.Encoding.PEM)
        )
        results[name] = path
    return results


def read_exact(conn, n):
    buffer = b""
    while len(buffer) < n:
        part = conn.recv(n - len(buffer))
        if not part:
            raise EOFError
        buffer += part
    return buffer


class Lab:
    def __init__(self, certs, case="good"):
        self.certs, self.case = certs, case
        self.dns, self.tcp, self.sni, self.http = [], [], [], []
        self.observe = None
        self.now = stamp
        self.ledger_seen = []
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        if case == "legacy_tls":
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                context.minimum_version = ssl.TLSVersion.TLSv1
                context.maximum_version = ssl.TLSVersion.TLSv1_1
            context.set_ciphers("DEFAULT:@SECLEVEL=0")
        context.load_cert_chain(certs[case if case in ("untrusted", "hostname") else "good"])

        def sni(_tls, name, _context):
            self.sni.append(name)
            expected = "unexpected.s2v2.test" if case == "sni" else FIXTURE_HOST
            return None if name == expected else ssl.ALERT_DESCRIPTION_UNRECOGNIZED_NAME

        context.set_servername_callback(sni)
        self.context = context

    def capture_ledger(self, effect):
        if self.observe:
            state = self.observe()
            self.ledger_seen.append(
                (effect, state[-1]["kind"], state[-1]["index"], state[-1]["debit"])
            )

    def dns_exchange(self, conn):
        size = struct.unpack("!H", read_exact(conn, 2))[0]
        query = read_exact(conn, size)
        self.dns.append(query[12:])
        self.capture_ledger("resolver")
        header = struct.pack("!6H", struct.unpack("!H", query[:2])[0], 0x8180, 1, 1, 0, 0)
        question = b"\x03bad" + query[12:] if self.case == "dns_question" else query[12:]
        peer = "127.0.0.2" if self.case == "dns_peer" else "127.0.0.1"
        record = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 0, 4) + socket.inet_aton(peer)
        result = header + question + record
        conn.sendall(struct.pack("!H", len(result)) + result)

    def tls_exchange(self, conn):
        self.tcp.append(conn.getpeername())
        with self.context.wrap_socket(conn, server_side=True) as tls:
            request = b""
            while not request.endswith(b"\r\n\r\n"):
                request += read_exact(tls, 1)
            self.http.append(request)
            self.capture_ledger("http")
            index = len(self.http)
            route = request.split(b" ")[1].decode("ascii")
            case = self.case
            if case == "timeout":
                time.sleep(1.2)
                return
            status = int(case) if case.isdigit() else 200
            body = make_body(route, {}, self.now())
            if not isinstance(body, dict):
                raise TypeError(body)
            if case == "metadata" and index == 2:
                body["symbols"][0]["contractType"] = "CURRENT_QUARTER"
            if case == "malformed":
                body = b'{"serverTime":'
            else:
                body = json.dumps(body).encode("ascii")
            count = index + 2
            if case == "weight_jump" and index == 2:
                count += 1
            size = len(body) + int(case == "truncated")
            message = [
                f"HTTP/1.1 {status} fixture",
                "Content-Type: application/json; charset=utf-8",
                f"Content-Length: {size}",
                "Connection: close",
            ]
            if case != "counter_missing":
                message.append(f"X-MBX-USED-WEIGHT-1M: {count}")
                if case == "counter_duplicate":
                    message.append(f"X-MBX-USED-WEIGHT-1M: {count}")
            if status == 429:
                message.append("Retry-After: 8")
            if status == 302:
                message.append("Location: https://unapproved.s2v2.test/else")
            tls.sendall(("\r\n".join(message) + "\r\n\r\n").encode("ascii") + body)

    @contextmanager
    def started(self):
        class Service(socketserver.ThreadingTCPServer):
            daemon_threads = True
            allow_reuse_address = False

        def handler(exchange):
            class Handler(socketserver.BaseRequestHandler):
                def handle(self):
                    self.request.settimeout(2)
                    try:
                        exchange(self.request)
                    except (ssl.SSLError, OSError, EOFError):
                        return

            return Handler

        with (
            Service(("127.0.0.1", 0), handler(self.dns_exchange)) as dns,
            Service(("127.0.0.1", 0), handler(self.tls_exchange)) as tls,
        ):
            threads = [
                threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.04})
                for server in (dns, tls)
            ]
            for thread in threads:
                thread.start()
            self.dns_port, self.tls_port = dns.server_address[1], tls.server_address[1]
            try:
                yield self
            finally:
                for server in (dns, tls):
                    server.shutdown()
                for thread in threads:
                    thread.join()


class Run:
    def __init__(self, lab, *, policy=None):
        self.base = Scenario()
        self.lab = lab
        b = self.base
        self.epoch = {"wall_ms": stamp(), "monotonic_ns": time.monotonic_ns()}
        self.clock = b.root / "fixture-clock.json"
        save(self.clock, self.epoch)
        self.lab.now = self.now
        now = self.now()
        self.policy = {
            "schema": "S2V2_DIRECT_EGRESS_V1",
            "evidence": FIXTURE_EVIDENCE,
            "hostname": FIXTURE_HOST,
            "port": lab.tls_port,
            "resolver": "127.0.0.1",
            "resolver_port": lab.dns_port,
            "peer": "127.0.0.1",
            "source": "127.0.0.1",
            "interface": "lo",
            "netns_inode": Path("/proc/self/ns/net").stat().st_ino,
            "route_table_sha": sha(Path("/proc/net/route").read_bytes()),
            "not_before_ms": now - 1000,
            "expires_ms": now + 120_000,
            "country": "KR",
            "product": "USD_M_USDT_PERPETUAL",
            "owner_attested": True,
            "product_verified": True,
            "independent_direct": True,
            "no_bypass": True,
            "shared_known": True,
            "product_evidence_sha": "1" * 64,
            "windows_egress_evidence_sha": "2" * 64,
            "shared_method_sha": "3" * 64,
        } | (policy or {})
        save(b.route, self.policy)
        b.ca.write_bytes(lab.certs["ca"])
        b.data.update(
            evidence=FIXTURE_EVIDENCE,
            release_sha=sha(RB_WHEEL.read_bytes()),
            route_sha=sha(b.route.read_bytes()),
            ca_sha=sha(b.ca.read_bytes()),
        )
        save(b.config, b.data)
        self.paths = Paths(b.config, b.grant, RB_WHEEL)
        self.issue()

    def now(self):
        return (
            self.epoch["wall_ms"] + (time.monotonic_ns() - self.epoch["monotonic_ns"]) // 1_000_000
        )

    def issue(self, *, scope=None, budget=None, run_id=None, domain=FIXTURE_DOMAIN):
        self.base.issue(
            scope={"evidence": FIXTURE_EVIDENCE} | (scope or {}),
            budget=budget,
            run_id=run_id,
            at=self.now(),
        )
        signed = self.base.scope
        signature = PRIVATE.sign(domain + canonical(signed)).hex()
        save(
            self.base.grant, {"schema": SCHEMA, "scope": signed, "controller_signature": signature}
        )

    def process_args(self, fault="none"):
        return [
            str(self.paths.configuration),
            str(self.paths.grant),
            str(self.paths.wheel),
            str(self.clock),
            fault,
        ]

    def events(self):
        return self.base.events()


def fixture_root():
    root = Path("/mnt/cases/ca-fixture")
    root.mkdir(mode=0o700)
    return root
