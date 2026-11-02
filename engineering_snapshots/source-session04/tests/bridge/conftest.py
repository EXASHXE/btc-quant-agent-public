import socket
from pathlib import Path

import pytest

from btc_quant_agent.platform.bridge.config import load


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("OFFLINE_BRIDGE_NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture
def config():
    return load(Path(__file__).resolve().parents[2] / "configs/bridge/offline.yaml")
