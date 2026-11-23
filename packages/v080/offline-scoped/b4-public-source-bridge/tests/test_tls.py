import json
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from quant_personal_public_b1.clock import SystemClock
from quant_personal_public_b1.fixture import make_body
from quant_personal_public_b1.policy import SourceBlocked

from quant_personal_public_bridge_b4.admission import MarketAdapter
from quant_personal_public_bridge_b4.collector import Collector
from quant_personal_public_bridge_b4.fixtures import usd_m_fixture
from quant_personal_public_bridge_b4.routes import HOST, TIME, Request
from quant_personal_public_bridge_b4.transport import LOOPBACK, LoopbackHTTPS


def response(body, status=200, fields=b"", length=None):
    length = len(body) if length is None else length
    return (f"HTTP/1.1 {status} Fixture\r\nContent-Length: {length}\r\n"
            "Content-Type: application/json\r\nConnection: close\r\n".encode() + fields + b"\r\n" + body)


class TLS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        area = tempfile.TemporaryDirectory()
        cls.addClassCleanup(area.cleanup)
        cls.root = Path(area.name)
        cls.certs = {}
        for dns in (HOST, "wrong-host.invalid"):
            cert, key = cls.root / f"{dns}.pem", cls.root / f"{dns}.key"
            args = ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", "7",
                    "-subj", f"/CN={dns}", "-addext", f"subjectAltName=DNS:{dns}", "-keyout", str(key), "-out", str(cert)]
            subprocess.run(args, check=True, capture_output=True)
            cls.certs[dns] = cert, key

    @contextmanager
    def server(self, make, dns=HOST):
        book = {"sni": [], "requests": []}
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        cert, key = self.certs[dns]
        context.load_cert_chain(cert, key)
        context.set_servername_callback(lambda _sock, name, _ctx: book["sni"].append(name))

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                method, url, _ = self.rfile.readline(3000).decode().split()
                host = self.rfile.readline(3000).decode().strip()
                book["requests"].append((method, url, host))
                while self.rfile.readline(3000) not in (b"\r\n", b""):
                    pass
                try:
                    self.wfile.write(make(url))
                except (OSError, ssl.SSLError):
                    pass

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True

            def get_request(self):
                conn, address = super().get_request()
                conn.settimeout(1)
                try:
                    return context.wrap_socket(conn, server_side=True), address
                except OSError:
                    conn.close()
                    raise

        with Server(("127.0.0.1", 0), Handler) as server:
            worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
            worker.start()
            try:
                yield LoopbackHTTPS(server.server_address[1], cert), book
            finally:
                server.shutdown()
                worker.join()

    def test_tls_schema_and_raw_to_adapter(self):
        def real_shape(url):
            split = urlsplit(url)
            params = {k: int(v) if v.isdecimal() else v for k, v in parse_qsl(split.query)}
            body = usd_m_fixture(split.path, params, make_body(split.path, params, time.time_ns() // 1_000_000))
            return response(json.dumps(body).encode())

        with self.server(real_shape) as (wire, log):
            path = self.root / "loopback.sqlite"
            pub = Collector(path, wire, SystemClock(), origin=LOOPBACK).scan(("BTCUSDT",))
            self.assertIsNone(pub["stage"]["issue"])
            self.assertIsNone(pub["stage"]["markets"]["BTCUSDT"]["issue"])
            market = MarketAdapter(path, LOOPBACK).read("BTCUSDT", scan=pub["scan_id"])
            self.assertEqual(len(log["requests"]), 15)
            self.assertTrue(all(method == "GET" and host == f"Host: {HOST}" for method, _, host in log["requests"]))
            self.assertEqual(set(log["sni"]), {HOST})
            self.assertTrue(all(x["tls"]["peer"] == "127.0.0.1" for x in market.source["raw_receipts"]))
            self.assertIn("NOT_GENUINE_MARKET", market.source["warnings"])

    def test_wrong_san_and_untrusted_certificate(self):
        blank = lambda _url: response(b"{}")
        with self.server(blank, "wrong-host.invalid") as (wire, log):
            with self.assertRaisesRegex(SourceBlocked, "TLS_VERIFICATION_FAILED"):
                wire.send(Request(TIME, {}), 1000)
            self.assertEqual(log, {"sni": [HOST], "requests": []})
        with self.server(blank) as (wire, log):
            wrong_chain = LoopbackHTTPS(wire.port, self.certs["wrong-host.invalid"][0])
            with self.assertRaisesRegex(SourceBlocked, "TLS_VERIFICATION_FAILED"):
                wrong_chain.send(Request(TIME, {}), 1000)
            self.assertEqual(log["requests"], [])

    def test_transport_revalidates_before_socket(self):
        with self.server(lambda _url: response(b"{}")) as (wire, log):
            with self.assertRaisesRegex(SourceBlocked, "FORBIDDEN_QUERY"):
                wire.send(Request(TIME, {"symbol": "BTCUSDT"}), 1000)
            with self.assertRaisesRegex(SourceBlocked, "FORBIDDEN_ROUTE"):
                wire.send(Request(TIME, {}, method="POST"), 1000)
            self.assertEqual(log["sni"], [])
            self.assertEqual(log["requests"], [])

    def test_redirect_truncation_oversize_and_denial(self):
        samples = (
            ("redirect", response(b"", 302, b"Location: https://fapi.binance.com/\r\n"), "HTTP_REDIRECT"),
            ("truncated", response(b"{}", length=10), "TRUNCATED_HTTP_BODY"),
            ("oversize", response(b"x" * 4_000_001), "DECODED_PAYLOAD_TOO_LARGE"),
            ("waf", response(b"{}", 403), "HTTP_403"),
            ("restriction", response(b"", 451), "HTTP_451"),
            ("malformed", response(b'{"serverTime":'), "MALFORMED_JSON"),
        )
        for name, raw, reason in samples:
            with self.subTest(name=name), self.server(lambda _url: raw) as (wire, log):
                source = self.root / f"{name}.sqlite"
                pub = Collector(source, wire, origin=LOOPBACK).scan(("BTCUSDT",))
                self.assertEqual(pub["stage"]["issue"]["code"], reason)
                self.assertEqual(len(log["requests"]), 1)

    def test_timeout_retries_only_once(self):
        def stalled(_url):
            time.sleep(0.8)
            return response(b"{}")

        with self.server(stalled) as (wire, log):
            pub = Collector(self.root / "timeout.sqlite", wire, origin=LOOPBACK).scan(("BTCUSDT",))
            self.assertEqual(pub["stage"]["issue"]["code"], "TRANSIENT_WIRE_FAILURE")
            self.assertEqual(len(log["requests"]), 2)
