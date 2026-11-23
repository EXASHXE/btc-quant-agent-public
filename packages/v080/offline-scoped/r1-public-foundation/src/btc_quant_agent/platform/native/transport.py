"""One CONNECT tunnel per request, strict original-target TLS, Sans-I/O WebSocket.

No environment proxy, direct fallback, redirects, reconnect or hidden receiver.
The caller's guard and durable budget charge run before every actual socket I/O.
"""

from __future__ import annotations

from collections import deque
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit
from typing import Any

from websockets.client import ClientProtocol
from websockets.frames import Frame, Opcode
from websockets.http11 import Response
from websockets.uri import parse_uri

from .contract import check_permit, require, strict


class Transport:
    def __init__(self, policy, grant, journal, clock, *, qa_ca=None, qa_proxy=False):
        self.policy, self.grant, self.journal, self.clock = policy, grant, journal, clock
        self.local_qa = qa_proxy
        check_permit(grant, policy, self.local_qa)
        if qa_ca is not None or qa_proxy:
            require(
                grant.exposure == "SYNTHETIC_NETWORK"
                and ipaddress.ip_address(policy.proxy_ip).is_loopback
                and qa_proxy,
                "LOCAL_QA_ONLY",
            )
        self.context = ssl.create_default_context(cafile=str(qa_ca) if qa_ca is not None else None)
        require(self.context.verify_mode == ssl.CERT_REQUIRED and self.context.check_hostname, "TLS_REQUIRED")
        self.sockets = set()
        self.tls = []
        self.protocol: Any = None
        self.sock: Any = None
        self.pending: deque[Any] = deque()
        self.last_receive_sample = None
        self.connected = False
        self.connection_attempts = 0
        self.sent_times: deque[int] = deque()
        self.last_activity_mono = None
        self.awaiting_pong = None
        self.closed = False

    def guard(self, probes=False):
        check_permit(self.grant, self.policy, self.local_qa)
        s = self.clock.check(self.grant, require_probes=probes)
        remaining = (self.grant.end_ms - s["wall_ms"]) / 1000
        return min(2.0, remaining)

    def _read_head(self, sock, maximum=16384):
        data = bytearray()
        while not data.endswith(b"\r\n\r\n"):
            sock.settimeout(self.guard())
            # Never consume bytes from the target TLS handshake into the proxy parser.
            chunk = sock.recv(1)
            require(chunk, "PROXY_OR_HTTP_EOF")
            data.extend(chunk)
            require(len(data) <= maximum, "HTTP_HEADER_LIMIT")
        return bytes(data)

    def tunnel(self, host):
        require(host in {"fstream.binance.com", "fapi.binance.com"}, "TARGET_FORBIDDEN")
        self.journal.charge(
            self.grant, "requests", self.grant.requests_max, {"target": host, "route": "HTTP_CONNECT"}
        )
        self.guard()
        ip = ipaddress.ip_address(self.policy.proxy_ip)
        sock = socket.socket(socket.AF_INET6 if ip.version == 6 else socket.AF_INET, socket.SOCK_STREAM)
        self.sockets.add(sock)
        self.connection_attempts += 1
        sock.settimeout(self.guard())
        # Exactly one attempt to the approved numeric proxy, never target DNS/direct.
        sock.connect((self.policy.proxy_ip, self.policy.proxy_port))
        self.guard()
        sock.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode())
        head = self._read_head(sock)
        require(
            head.split(b"\r\n")[0]
            in {
                b"HTTP/1.1 200 Connection established",
                b"HTTP/1.1 200 OK",
                b"HTTP/1.0 200 Connection established",
            },
            "PROXY_DENIED",
        )
        sock.settimeout(self.guard())
        target = self.context.wrap_socket(sock, server_hostname=host)
        self.sockets.discard(sock)
        self.sockets.add(target)
        self.guard()
        cert = target.getpeercert(binary_form=True)
        require(cert and target.version(), "ORIGINAL_TARGET_TLS_MISSING")
        import hashlib

        assert cert is not None
        self.tls.append(
            {
                "host": host,
                "sni": host,
                "certificate_sha256": hashlib.sha256(cert).hexdigest(),
                "chain": "CERT_REQUIRED",
                "hostname_verified": True,
                "tls_version": target.version(),
                "route": "HTTP_CONNECT",
                "proxy_ip": self.policy.proxy_ip,
                "proxy_port": self.policy.proxy_port,
            }
        )
        return target

    def probe(self):
        sock = self.tunnel("fapi.binance.com")
        try:
            sock.settimeout(self.guard())
            sock.sendall(b"GET /fapi/v1/time HTTP/1.1\r\nHost: fapi.binance.com\r\nConnection: close\r\n\r\n")
            head = self._read_head(sock)
            require(head.startswith(b"HTTP/1.1 200 "), "CLOCK_HTTP_STATUS")
            headers = {}
            for line in head.split(b"\r\n")[1:-2]:
                key, value = line.split(b":", 1)
                key = key.lower()
                require(key not in headers, "HTTP_DUPLICATE_HEADER")
                headers[key] = value.strip()
            require(
                b"transfer-encoding" not in headers and b"content-length" in headers, "CLOCK_HTTP_FRAMING"
            )
            size = int(headers[b"content-length"])
            require(0 < size <= 4096, "CLOCK_BODY_LIMIT")
            body = bytearray()
            while len(body) < size:
                sock.settimeout(self.guard())
                data = sock.recv(size - len(body))
                require(data, "CLOCK_BODY_TRUNCATED")
                body.extend(data)
            obj = strict(body)
            require(
                set(obj) == {"serverTime"} and type(obj["serverTime"]) is int and obj["serverTime"] > 0,
                "CLOCK_RESPONSE_INVALID",
            )
            return obj["serverTime"], {
                "headers": head.decode("ascii"),
                "body": body.decode("utf-8"),
                "tls": self.tls[-1],
            }
        finally:
            sock.close()
            self.sockets.discard(sock)

    def flush(self):
        for data in self.protocol.data_to_send():
            if not data:
                continue
            now = self.clock.sample()["mono_after_ms"]
            while self.sent_times and now - self.sent_times[0] >= 1000:
                self.sent_times.popleft()
            require(len(self.sent_times) < 10, "OUTGOING_RATE10_HARD_STOP")
            self.sent_times.append(now)
            self.journal.charge(self.grant, "outgoing", self.grant.outgoing_frames_max, {"bytes": len(data)})
            self.sock.settimeout(self.guard(True))
            self.sock.sendall(data)

    def open(self):
        require(not self.connected, "NO_RECONNECT")
        self.connected = True  # Failed handshake still consumes this attempt.
        self.sock = self.tunnel("fstream.binance.com")
        uri = self.policy.endpoint + "?streams=" + "/".join(self.policy.streams)
        require(urlsplit(uri).path == "/market/stream", "WS_ROUTE")
        self.protocol = ClientProtocol(parse_uri(uri), max_size=self.policy.max_frame_bytes)
        self.protocol.send_request(self.protocol.connect())
        self.flush()
        response = self.next_event()
        require(
            isinstance(response, Response)
            and response.status_code == 101
            and self.protocol.handshake_exc is None,
            "WS_UPGRADE_REJECTED",
        )

    def heartbeat(self):
        now = self.clock.check(self.grant)["mono_after_ms"]
        if self.last_activity_mono is None:
            self.last_activity_mono = now
        if self.awaiting_pong is not None:
            require(now - self.awaiting_pong[1] < 10000, "PONG_TIMEOUT")
        elif now - self.last_activity_mono >= 180000:
            payload = str(now).encode()
            self.protocol.send_ping(payload)
            self.awaiting_pong = (payload, now)
            self.flush()

    def next_event(self):
        while not self.pending:
            self.guard(True)
            self.sock.settimeout(min(0.2, self.guard(True)))
            try:
                raw = self.sock.recv(self.policy.max_frame_bytes)
            except socket.timeout:
                return None
            require(raw, "RECEIVER_INTERRUPTED_OR_PEER_CLOSED")
            received_sample = self.clock.sample()
            self.protocol.receive_data(raw)
            events = self.protocol.events_received()
            require(len(events) < 128, "QUEUE128_HARD_STOP")
            require(len(events) <= 96, "QUEUE96_HIGH_WATER_STOP")
            self.pending.extend((event, received_sample) for event in events)
            self.flush()  # Includes RFC6455 automatic pong; all output is budgeted.
        event, self.last_receive_sample = self.pending.popleft()
        self.last_activity_mono = self.last_receive_sample["mono_after_ms"]
        if isinstance(event, Frame) and event.opcode == Opcode.PONG and self.awaiting_pong is not None:
            require(bytes(event.data) == self.awaiting_pong[0], "PONG_IDENTITY_MISMATCH")
            self.awaiting_pong = None
        return event

    def close(self):
        error = None
        try:
            if self.protocol is not None and self.sock is not None and self.sock.fileno() >= 0:
                try:
                    if self.protocol.state.name == "OPEN":
                        self.protocol.send_close(1000, "finite session stop")
                        # Window may be over: no new application I/O beyond signed end.
                        if self.clock.sample()["wall_ms"] < self.grant.end_ms:
                            self.flush()
                except Exception as exc:
                    error = str(exc)
        finally:
            for sock in tuple(self.sockets):
                try:
                    sock.close()
                    require(sock.fileno() == -1, "SOCKET_TERMINATION_FAILED")
                except Exception as exc:
                    error = str(exc)
            self.sockets.clear()
            self.closed = error is None
        return self.closed, error

    @staticmethod
    def frame_payload(event):
        require(isinstance(event, Frame), "WS_EVENT_INVALID")
        require(
            event.opcode in {Opcode.TEXT, Opcode.PING, Opcode.PONG, Opcode.CLOSE},
            "FRAGMENT_OR_BINARY_FORBIDDEN",
        )
        require(event.fin, "FRAGMENT_FORBIDDEN")
        return event.opcode.name, bytes(event.data)
