import ipaddress
import socket

import pytest


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    original = socket.socket.connect

    def loopback(sock, address):
        if sock.family == socket.AF_UNIX or ipaddress.ip_address(address[0]).is_loopback:
            return original(sock, address)
        raise AssertionError("J_TEST_EXTERNAL_NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", loopback)
    monkeypatch.setattr(socket.socket, "connect_ex", loopback)
    from btc_quant_agent.platform.live.models import sample

    def qa_sample():
        value = sample()
        value["wall_ms"] = value["mono_before_ms"] + 1000000000000
        return value

    for module in ("source", "store", "product", "swing_review", "operational_clock"):
        monkeypatch.setattr("btc_quant_agent.platform.live." + module + ".sample", qa_sample)
