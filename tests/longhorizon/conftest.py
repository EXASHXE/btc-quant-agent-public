import socket
import pytest


@pytest.fixture(autouse=True)
def no_native_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("LONGHORIZON_OFFLINE_TEST_NATIVE_NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
