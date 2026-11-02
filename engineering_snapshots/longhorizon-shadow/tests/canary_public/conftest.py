import socket
import pytest

from btc_quant_agent.platform.canary.public_policy import load_scope


@pytest.fixture(autouse=True)
def network_denied(monkeypatch, tmp_path):
    def blocked(*a, **k):
        raise AssertionError("SYNTHETIC_TEST_MARKET_NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    # Isolate test admission state from an actual observed provider denial.
    monkeypatch.setattr(
        "btc_quant_agent.platform.canary.public_policy.ACCESS_DENIAL", tmp_path / "access_denial.json"
    )


@pytest.fixture
def scope():
    return load_scope()
