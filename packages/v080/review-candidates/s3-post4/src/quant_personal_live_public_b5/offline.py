"""Synthetic-only B5 exercises and a prospective wire plan with an unresolved funding debit."""

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from quant_personal_decision_b2.fixtures import AFTER_TRIGGER, FabricatedMarket
from quant_personal_decision_b2.model import check
from quant_personal_public_b1.fixture import FixtureClock, FixtureTransport
from quant_personal_public_b1.session import RunIdentity
from quant_personal_public_bridge_b4.collector import WARM_BARS, completed_end, observation_query
from quant_personal_public_bridge_b4.demo import SCENARIOS, advance
from quant_personal_public_bridge_b4.fixtures import usd_m_fixture
from quant_personal_public_bridge_b4.normalize import OBSERVATIONS
from quant_personal_public_bridge_b4.routes import INSTRUMENTS, KLINES, QUOTE, TIME

from .admission import Adapter
from .approval import Approval, Limit, RouteScope, Scope
from .collection import collect
from .contract import (
    AUTHORITY, CONTRACT, FUNDING, INTERVALS, QA_WARNINGS, SYMBOL_ORDER, PublicRequest,
)
from .decision import engine, replay
from .ledger import Active, Ledger

PROSPECTIVE_CUTOFF_MS = 1_735_689_720_000
BOOTSTRAP_PHASES = ("bootstrap", "confirm", "refresh_5", "refresh_10")


def plan(cutoff=PROSPECTIVE_CUTOFF_MS):
    requests = [PublicRequest(TIME, {}), PublicRequest(INSTRUMENTS, {})]
    for symbol in SYMBOL_ORDER:
        for frame, width in INTERVALS.items():
            close = completed_end(frame, cutoff)
            requests.append(PublicRequest(KLINES, {"symbol": symbol, "interval": frame, "limit": WARM_BARS,
                                                  "startTime": close-WARM_BARS*width, "endTime": close-width}))
    for symbol in SYMBOL_ORDER:
        requests.extend(observation_query(name, symbol, cutoff)
                        for name, route in OBSERVATIONS.items() if route != INSTRUMENTS)
    requests.append(PublicRequest(TIME, {}))
    known, funding_count = 0, 0
    rows = []
    for req in requests:
        weight, _ = req.validate()
        if req.route == FUNDING:
            funding_count += 1
            weight = None
        else:
            known += weight
        rows.append({"path": req.route, "method": "GET", "params": dict(req.params), "documented_debit": weight})
    return {"authorization": "NOT_AUTHORIZED", "state": "LIVE_DISABLED", "authority": AUTHORITY,
            "contract": CONTRACT, "fixture_cutoff_ms": cutoff, "requests": rows,
            "planned_requests": len(rows), "known_weight": known, "funding_calls": funding_count,
            "illustrative_weight_with_b4_assumption": known+funding_count,
            "approved_weight": None,
            "refresh_envelopes": {"refresh_5": None, "refresh_10": None}}


def qa_approval(path, *, max_count=48, max_weight=64, funding=1, now=PROSPECTIVE_CUTOFF_MS):
    # There are no signatures or production peer values in a synthetic grant.
    scope = Scope("a"*64, RouteScope("QA","b"*64,1,"qa-only","192.0.2.2","192.0.2.3",("192.0.2.4",), "f"*64),
                  path, path.with_name("qa-journal.sqlite"), 2,
                  MappingProxyType({phase: Limit(max_count,max_weight) for phase in BOOTSTRAP_PHASES}),
                  Limit(96,120), Limit(4*max_count, 4*max_weight), 4, funding)
    return Approval("c"*32, "d"*64, scope, now-100_000, now+3_600_000, "e"*64)


class FixtureWire:
    """Fabricated venue-shaped envelope and weight counters with no socket methods."""

    def __init__(self, clock, fixture=None, mutate=None):
        self.clock = clock
        self.fixture = fixture or FixtureTransport(clock, mutate=usd_m_fixture)
        self.mutate = mutate
        self.minute = None
        self.used = 0

    def send(self, request, timeout_ms):
        debit, _ = request.validate()
        result = self.fixture.send(request, timeout_ms)
        minute = self.clock.venue_ms//60_000
        if self.minute != minute:
            self.minute, self.used = minute, 0
        self.used += debit
        header = self.used if request.route != QUOTE else 99999
        result = replace(result, headers={"x-mbx-used-weight-1m": str(header), **result.headers})
        return self.mutate(request, result) if self.mutate else result


def qa_active(source, clock=None, *, approval=None):
    clock = clock or FixtureClock()
    approval = approval or qa_approval(source, now=clock.sample().wall_ms)
    active = Active(Ledger.qa(source, approval), approval, clock, RunIdentity("B5-QA-BOOT", "B5-QA-PROCESS"))
    active.claim()
    return active


def run_case(root: Path, scenario, *, chase=False, funding_crossing=False):
    root.mkdir()
    source, journal = root / "source.sqlite", root / "journal.sqlite"
    feed = FabricatedMarket(source, *SCENARIOS[scenario])
    feed.transport.mutate = lambda route, params, body: usd_m_fixture(route, params, feed.respond(route, params, body))
    active = qa_active(source, feed.clock)
    wire = FixtureWire(feed.clock, feed.transport)
    adapter = Adapter(active.ledger)
    evaluator = engine(adapter, journal)
    cards, counts = [], []
    with active.ledger.store.collector():
        for index, phase in enumerate(BOOTSTRAP_PHASES):
            delay = 5*(index-1)
            offset = 120_000 if index == 0 else AFTER_TRIGGER
            if index >= 2:
                offset = cards[1]["evaluated_ms"] - feed.base_end + 60_000*delay
            variant = "chase" if chase and index >= 2 else "funding" if funding_crossing else "inside"
            advance(feed, offset, variant)
            publication = collect(active, phase, wire, ("BTCUSDT",))
            as_of = publication["visible_venue_upper_ms"]
            check(as_of is not None, "QA_SOURCE_BLOCKED", str(publication["stage"]["issue"]))
            extra = {"reprice_minutes": delay, "episode_id":cards[1]["episode_id"]} if index >= 2 else {}
            cards.append(evaluator.evaluate("BTCUSDT", scan=publication["scan_id"], as_of_ms=as_of, **extra))
            counts.append(publication["stage"]["stats"])
        active.close()
    evaluator.journal.manual(card_id=cards[1]["card_id"], operator_id="qa-review", action="SKIP",
                             time_ms=cards[1]["evaluated_ms"], note="Synthetic QA")
    return {"scenario": scenario, "warnings": QA_WARNINGS, "cards": cards, "budgets": counts}


def readiness(root):
    root.mkdir()
    cases = []
    for name, pair in SCENARIOS.items():
        path = root / name
        case = run_case(path, name)
        cases_cards = case["cards"]
        result = [c["market_status"] for c in cases_cards]
        episode = cases_cards[1]["episode"] or {}
        passed = (result == ["WATCH","EXECUTABLE","EXECUTABLE","EXECUTABLE"]
                  and (episode.get("family"),episode.get("direction")) == pair
                  and [c["reprice"]["requested_delay_minutes"] for c in cases_cards[2:]] == [5,10])
        adapter = Adapter(Ledger.open_qa(path/"source.sqlite"))
        cases.append({"scenario": name, "statuses": result, "pass": passed, "budgets": case["budgets"],
                      "replay": [replay(adapter, card) for card in cases_cards]})
    return {"authorization":"NOT_AUTHORIZED", "warnings": QA_WARNINGS, "cases":cases,
            "offline_readiness": all(c["pass"] for c in cases)}
