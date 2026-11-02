"""Deadline-aware public target sockets; optionally explicit tunneled egress."""

from __future__ import annotations

import socket
import ipaddress
import threading
import time
import ssl

import httpcore
from httpcore._backends.sync import SyncBackend, SyncStream

from .public_policy import PublicStop
from .public_egress import ProxyConfig, TARGET_HOSTS, tunnel


class GuardedStream(SyncStream):
    def __init__(self, sock, owner, target_host=None):
        super().__init__(sock)
        self.owner = owner
        self.target_host = target_host
        owner.register(sock)

    def read(self, max_bytes, timeout=None):
        return super().read(max_bytes, timeout=self.owner.timeout(timeout))

    def write(self, buffer, timeout=None):
        return super().write(buffer, timeout=self.owner.timeout(timeout))

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        if (
            ssl_context.verify_mode != ssl.CERT_REQUIRED
            or not ssl_context.check_hostname
            or server_hostname not in TARGET_HOSTS
            or (self.target_host is not None and server_hostname != self.target_host)
        ):
            raise PublicStop("TLS_TARGET_OR_VERIFICATION_INVALID")
        stream = super().start_tls(ssl_context, server_hostname, self.owner.timeout(timeout))
        self.owner.check()
        sock = getattr(stream, "_sock", None)
        if sock is None:
            raise PublicStop("UNSUPPORTED_HTTP_LIBRARY_STREAM")
        return GuardedStream(sock, self.owner, self.target_host)


class DirectSockets(SyncBackend):
    def __init__(self, check, *, proxy_url=None):
        self.check = check
        self.proxy = ProxyConfig.parse(proxy_url) if proxy_url else None
        self.route_info = (
            self.proxy.receipt()
            if self.proxy
            else {"egress_mode": "DIRECT", "target_tls": "STRICT_VERIFICATION_REQUIRED"}
        )
        self.sockets = set()
        self.lock = threading.Lock()

    def register(self, sock):
        with self.lock:
            self.sockets = {s for s in self.sockets if s.fileno() >= 0}
            self.sockets.add(sock)

    def timeout(self, value):
        left = self.check()
        return min(left, 5 if value is None else value)

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host not in TARGET_HOSTS or port != 443 or local_address is not None:
            raise PublicStop("NETWORK_HOST_OR_ROUTE_FORBIDDEN")
        self.check()
        dial_host = self.proxy.host if self.proxy else host
        dial_port = self.proxy.port if self.proxy else port
        addresses = socket.getaddrinfo(dial_host, dial_port, type=socket.SOCK_STREAM)
        # Recheck AFTER potentially slow DNS, before opening any socket.
        last = None
        for family, kind, proto, _, address in addresses:
            self.check()
            if not self.proxy and not ipaddress.ip_address(address[0]).is_global:
                raise PublicStop("NETWORK_PRIVATE_ADDRESS_FORBIDDEN")
            sock = socket.socket(family, kind, proto)
            self.register(sock)
            try:
                sock.settimeout(self.timeout(timeout))
                for opt in socket_options or ():
                    sock.setsockopt(*opt)
                sock.connect(address)
                self.check()
                if self.proxy:
                    deadline = time.monotonic() + self.timeout(timeout)

                    def handshake_check():
                        self.check()
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise PublicStop("EGRESS_HANDSHAKE_TIMEOUT")
                        sock.settimeout(min(remaining, self.timeout(timeout)))

                    tunnel(sock, self.proxy, host, port, handshake_check)
                return GuardedStream(sock, self, host)
            except PublicStop:
                sock.close()
                raise
            except OSError as exc:
                sock.close()
                last = exc
        raise httpcore.ConnectError(str(last))

    def connect_unix_socket(self, *args, **kwargs):
        raise PublicStop("UNIX_ROUTE_FORBIDDEN")

    def abort(self):
        with self.lock:
            sockets = list(self.sockets)
        for s in sockets:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass
