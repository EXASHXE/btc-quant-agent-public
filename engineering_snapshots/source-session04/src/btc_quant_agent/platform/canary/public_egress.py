"""Explicit transport-only CONNECT/SOCKS5 gateway; TLS remains end-to-end to target."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .public_policy import PublicStop

TARGET_HOSTS = frozenset(("developers.binance.com", "fapi.binance.com", "fstream.binance.com"))


@dataclass(frozen=True)
class ProxyConfig:
    scheme: str
    host: str
    port: int

    @classmethod
    def parse(cls, url: str) -> "ProxyConfig":
        try:
            p = urlsplit(url)
            port = p.port
        except ValueError as exc:
            raise PublicStop("INVALID_EGRESS_PROXY_URL") from exc
        if (
            p.scheme not in ("http", "socks5", "socks5h")
            or not p.hostname
            or port is None
            or not 1 <= port <= 65535
            or p.username is not None
            or p.password is not None
            or p.query
            or p.fragment
            or p.path not in ("", "/")
        ):
            raise PublicStop("INVALID_EGRESS_PROXY_URL")
        return cls(p.scheme, p.hostname, port)

    def receipt(self) -> dict:
        # Never record credentials or inferred host jurisdiction.
        return {
            "egress_mode": "CONTROLLED_EGRESS_PROXY",
            "tunnel_type": "HTTP_CONNECT" if self.scheme == "http" else "SOCKS5",
            "proxy_host": self.host,
            "proxy_port": self.port,
            "target_tls": "STRICT_VERIFICATION_REQUIRED",
            "target_authority": "ALLOWED_HOSTS_PORT_443",
            "physical_location": "NOT_INDEPENDENTLY_OBSERVED",
        }


def _recv_exact(sock, count: int, check):
    data = bytearray()
    while len(data) < count:
        check()
        block = sock.recv(count - len(data))
        if not block:
            raise PublicStop("EGRESS_TUNNEL_INCOMPLETE")
        data.extend(block)
    return bytes(data)


def tunnel(sock, proxy: ProxyConfig, target_host: str, target_port: int, check) -> None:
    """Establish a byte-preserving tunnel, never a destination rewrite."""
    if target_host not in TARGET_HOSTS or target_port != 443:
        raise PublicStop("EGRESS_TARGET_NOT_ALLOWLISTED")
    check()
    if proxy.scheme == "http":
        request = (
            f"CONNECT {target_host}:443 HTTP/1.1\r\n"
            f"Host: {target_host}:443\r\n"
            "Proxy-Connection: Keep-Alive\r\n\r\n"
        ).encode("ascii")
        sock.sendall(request)
        head = bytearray()
        while b"\r\n\r\n" not in head:
            check()
            chunk = sock.recv(1)
            if not chunk:
                raise PublicStop("EGRESS_HTTP_CONNECT_INCOMPLETE")
            head.extend(chunk)
            if len(head) > 8192:
                raise PublicStop("EGRESS_HTTP_CONNECT_HEADER_TOO_LARGE")
        status = bytes(head).split(b"\r\n", 1)[0].split(b" ")
        if len(status) < 2 or status[0] not in (b"HTTP/1.0", b"HTTP/1.1") or status[1] != b"200":
            raise PublicStop("EGRESS_HTTP_CONNECT_REJECTED")
    else:
        sock.sendall(b"\x05\x01\x00")
        if _recv_exact(sock, 2, check) != b"\x05\x00":
            raise PublicStop("EGRESS_SOCKS5_AUTH_REJECTED")
        name = target_host.encode("ascii")
        sock.sendall(b"\x05\x01\x00\x03" + bytes([len(name)]) + name + (443).to_bytes(2, "big"))
        header = _recv_exact(sock, 4, check)
        if header[:3] != b"\x05\x00\x00":
            raise PublicStop("EGRESS_SOCKS5_CONNECT_REJECTED")
        if header[3] == 1:
            _recv_exact(sock, 4, check)
        elif header[3] == 4:
            _recv_exact(sock, 16, check)
        elif header[3] == 3:
            _recv_exact(sock, _recv_exact(sock, 1, check)[0], check)
        else:
            raise PublicStop("EGRESS_SOCKS5_ADDRESS_INVALID")
        _recv_exact(sock, 2, check)
    check()
