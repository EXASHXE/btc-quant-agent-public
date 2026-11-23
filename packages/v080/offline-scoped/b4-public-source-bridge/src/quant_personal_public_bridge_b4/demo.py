"""Deterministic synthetic scenarios derived from accepted B2 fixture recipes."""

from pathlib import Path

from quant_personal_decision_b2.fixtures import AFTER_TRIGGER, EARLY, INITIAL, PULLBACK, FabricatedMarket
from quant_personal_decision_b2.model import MINUTE, check
from quant_personal_public_b1.session import RunIdentity

from .fixtures import usd_m_fixture

from .admission import MarketAdapter
from .collector import Collector
from .decision import DecisionJournal, compose, verify_card
from .transport import FIXTURE, WARNINGS

SCENARIOS = {f"{family.lower()}-{direction.lower()}": (family, direction)
             for family in (PULLBACK, EARLY) for direction in ("LONG", "SHORT")}
OFFSETS = (INITIAL, AFTER_TRIGGER, AFTER_TRIGGER + 5 * MINUTE, AFTER_TRIGGER + 10 * MINUTE)
SYMBOL = "BTCUSDT"


def advance(feed, offset, variant="inside"):
    target = feed.base_end + offset
    check(target >= feed.clock.venue_ms, "FIXTURE_TIME_REGRESSION")
    feed.clock.advance(target - feed.clock.venue_ms)
    feed.variant = variant


def run(directory: Path, scenario: str, *, chase: bool = False):
    directory.mkdir()
    source, journal = directory / "source.sqlite", directory / "journal.sqlite"
    feed = FabricatedMarket(source, *SCENARIOS[scenario])
    feed.transport.mutate = lambda route, params, body: usd_m_fixture(
        route, params, feed.respond(route, params, body))
    collector = Collector.fixture(source, feed.clock, feed.transport,
                                  RunIdentity(feed.boot, feed.epoch))
    cards, requests = [], []
    for ix, offset in enumerate(OFFSETS):
        if ix >= 2:
            offset = max(offset, cards[1]["evaluated_ms"] - feed.base_end + 5 * (ix - 1) * MINUTE)
        advance(feed, offset, "chase" if chase and ix >= 2 else "inside")
        before = len(feed.transport.calls)
        publication = collector.scan((SYMBOL,))
        requests.append(len(feed.transport.calls) - before)
        scan = publication["scan_id"]
        as_of = publication["visible_venue_upper_ms"]
        check(as_of is not None, "FIXTURE_SOURCE_FAILURE", str(publication["stage"]["issue"]))
        engine = compose(source, journal, FIXTURE)
        extra = {"reprice_minutes": 5 * (ix - 1), "episode_id": cards[1]["episode_id"]} if ix >= 2 else {}
        cards.append(engine.evaluate(SYMBOL, scan=scan, as_of_ms=as_of, **extra))
    review = DecisionJournal(journal)
    review.manual(card_id=cards[1]["card_id"], operator_id="synthetic-owner-skip",
                  action="SKIP", time_ms=cards[1]["evaluated_ms"], note="Offline QA fixture")
    return {"scenario": scenario, "warnings": list(WARNINGS), "requests_by_scan": requests, "cards": cards}


def replay(source, journal, card_id=None, *, origin=FIXTURE):
    card = DecisionJournal(journal).read(card_id=card_id)
    check(card is not None, "CARD_UNKNOWN")
    return verify_card(MarketAdapter(source, origin), card)
