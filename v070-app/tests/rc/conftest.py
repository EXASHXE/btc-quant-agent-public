import pytest

from btc_quant_agent.platform.rc_fixture import DECISION, TRIGGER, fixture
from btc_quant_agent.platform.rc_store import RCStore
from btc_quant_agent.platform.rc_strategy import decide_s1


@pytest.fixture(scope="session")
def positive_rows():
    return fixture()


@pytest.fixture(scope="session")
def flat_rows():
    return fixture(flat=True)


@pytest.fixture(scope="session")
def btc_rows(positive_rows):
    return tuple(r for r in positive_rows if r.bar.candle.symbol == "BTCUSDT")


@pytest.fixture(scope="session")
def positive(btc_rows):
    return decide_s1(symbol="BTCUSDT", trigger_ms=TRIGGER, decision_ms=DECISION, receipts=btc_rows)


@pytest.fixture
def stored(tmp_path, btc_rows, positive):
    store = RCStore(tmp_path / "state.sqlite")
    store.admit(btc_rows)
    store.commit(positive)
    return store
