from pathlib import Path
import socket
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("NETWORK_FORBIDDEN_IN_Q0B_TESTS")
    monkeypatch.setattr(socket, "socket", refused)
    monkeypatch.setattr(socket, "create_connection", refused)
    monkeypatch.setattr(socket, "getaddrinfo", refused)
