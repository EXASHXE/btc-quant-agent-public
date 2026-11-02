import socket

import pytest

from btc_quant_agent.platform.backtest import build_pipeline
from btc_quant_agent.platform.config import PlatformConfig
from btc_quant_agent.platform.data import SyntheticProvider


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("SYNTHETIC_ENGINEERING_NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture(scope="session")
def config():
    return PlatformConfig(bars=140)


@pytest.fixture(scope="session")
def events(config):
    return SyntheticProvider().events(config)


@pytest.fixture(scope="session")
def pipeline(events, config):
    return build_pipeline(events, config)[0]
