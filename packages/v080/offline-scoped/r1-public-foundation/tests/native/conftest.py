import ipaddress
import socket

import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    original = socket.socket.connect

    def loopback(sock, address):
        if sock.family == socket.AF_UNIX:
            return original(sock, address)
        try:
            allowed = ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            allowed = False
        if not allowed:
            raise AssertionError("EXTERNAL_NETWORK_FORBIDDEN")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", loopback)
    monkeypatch.setattr(
        socket.socket, "connect_ex", lambda *_: (_ for _ in ()).throw(AssertionError("NO_CONNECT_EX"))
    )
