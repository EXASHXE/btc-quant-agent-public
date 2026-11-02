import pytest

from btc_quant_agent.platform.selection.fixtures import BASE, SYMBOLS, history, structural_bars
from btc_quant_agent.platform.selection.selector import Policy, Setup, scan
from btc_quant_agent.platform.selection.sources import STRUCTURE
from btc_quant_agent.platform.selection.store import SelectorStore


@pytest.fixture(scope="session")
def corpus():
    policy = Policy(symbols=SYMBOLS)
    bars = structural_bars()
    return policy, bars, history(bars, BASE + 305 * STRUCTURE, policy)


@pytest.fixture
def store(tmp_path):
    return SelectorStore(tmp_path / "selector.sqlite")


@pytest.fixture(scope="session")
def setup_cards(corpus, tmp_path_factory):
    policy, _, h = corpus
    db = SelectorStore(tmp_path_factory.mktemp("qualified-setups") / "scan.sqlite")
    scan(history(corpus[1], h.universe.cutoff - STRUCTURE, policy), db, policy)
    result = scan(h, db, policy)
    return [Setup(x["anchors"], x["ranking"], tuple(x["vetoes"])) for x in result["candidates"]]


@pytest.fixture
def setup(setup_cards):
    return next(s for s in setup_cards if s.anchors["strategy"] == "trend_pullback")


@pytest.fixture
def resting_setup(setup_cards):
    return next(s for s in setup_cards if s.anchors["strategy"] == "breakout_retest")
