import socket
import pytest
from btc_quant_agent.platform.canary.control import CanaryStore
from btc_quant_agent.platform.canary.fixtures import metadata
from btc_quant_agent.platform.canary.policy import ROOT, load_catalog, load_policy


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **kw):
        raise AssertionError("L4_NO_SOURCE_NETWORK")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture
def policy():
    return load_policy(ROOT / "configs/canary/offline.yaml")


@pytest.fixture(scope="session")
def catalog():
    return load_catalog(ROOT / "configs/canary/endpoints.json")


@pytest.fixture
def store(tmp_path):
    return CanaryStore(tmp_path / "canary.sqlite")


@pytest.fixture
def binding(policy, catalog):
    return metadata(catalog["binance_usdm_exchange_info"], "BTCUSDT", policy.synthetic_start_ms + 100)
