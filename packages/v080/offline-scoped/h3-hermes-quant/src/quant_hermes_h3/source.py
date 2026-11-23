"""Compose the accepted H2-A collector, B5 verifier and B2 engine."""

from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from quant_personal_decision_b2.fixtures import AFTER_TRIGGER, FabricatedMarket
from quant_personal_live_public_b5.admission import Adapter
from quant_personal_live_public_b5.approval import Limit
from quant_personal_live_public_b5.collection import collect
from quant_personal_live_public_b5.contract import QA
from quant_personal_live_public_b5.decision import engine, replay
from quant_personal_live_public_b5.ledger import Ledger
from quant_personal_live_public_b5.offline import (
    BOOTSTRAP_PHASES,
    FixtureWire,
    qa_active,
    qa_approval,
)
from quant_personal_live_public_b5.stages import StagePlan
from quant_personal_public_bridge_b4.demo import SCENARIOS, advance
from quant_personal_public_bridge_b4.fixtures import usd_m_fixture

from .safety import Blocked, private_directory
from .telemetry import correlate


def offline_adapter(path):
    ledger = Ledger.open_qa(path)
    if ledger.origin != QA:
        raise Blocked("SOURCE_LANE_NOT_OFFLINE")
    return Adapter(ledger)


class ObservedWire(FixtureWire):
    def __init__(self, clock, measurements, case, fixture=None, mutate=None):
        super().__init__(clock, fixture, mutate)
        self.measurements, self.case = measurements, case
        self.number = 0

    def send(self, request, timeout_ms):
        debit, _ = request.validate()
        self.number += 1
        key = correlate(self.case, "get", self.number)
        self.measurements.record("GET_DISPATCH", key, count=1, weight=debit)
        try:
            result = super().send(request, timeout_ms)
        except Exception:
            self.measurements.record("GET_RESPONSE", key, code="SOURCE_BLOCKED")
            raise
        self.measurements.record(
            "GET_RESPONSE", key, code="OK" if result.status == 200 else "SOURCE_BLOCKED"
        )
        return result


class FixtureCase:
    """One fresh causal source/journal pair, with an explicitly staged first scan."""

    def __init__(self, root, measurements, scenario=None, *, canary=False, mutate=None):
        self.root, self.measurements = Path(root), measurements
        self.root.mkdir(mode=0o700)
        private_directory(self.root)
        self.source = self.root / "source.sqlite"
        self.journal = self.root / "journal.sqlite"
        self.feed = (
            None if scenario is None else FabricatedMarket(self.source, *SCENARIOS[scenario])
        )
        if self.feed is not None:
            feed = self.feed
            feed.transport.mutate = lambda route, params, payload: usd_m_fixture(
                route,
                params,
                feed.respond(route, params, payload),
            )
            self.active = qa_active(self.source, feed.clock)
        else:
            base = qa_approval(self.source)
            stage = StagePlan(None, None) if canary else StagePlan(37, 40)
            total = Limit(*stage.plan_totals())
            scope = replace(
                base.scope,
                stage_plan=stage,
                phase_limits=MappingProxyType({"bootstrap": total}),
                total=total,
                funding_debit=None if canary else 1,
            )
            self.active = qa_active(self.source, approval=replace(base, scope=scope))
        self.wire = ObservedWire(
            self.active.clock,
            measurements,
            self.root.name,
            self.feed.transport if self.feed else None,
            mutate,
        )
        self.adapter = Adapter(self.active.ledger)
        self.evaluator = engine(self.adapter, self.journal)
        self.trace = []
        self.cards = []

    @contextmanager
    def collecting(self):
        with self.active.ledger.store.collector():
            try:
                yield self
            finally:
                self.active.close()

    def evaluate(self, phase_index=0, *, quote="inside"):
        kwargs = {}
        if self.feed is not None:
            offset = 120_000 if phase_index == 0 else AFTER_TRIGGER
            if phase_index >= 2:
                original = self.cards[1]
                if not original["episode_id"] or original["first_trigger_evaluation_ms"] is None:
                    raise Blocked("REPRICE_UNCONFIRMED_EPISODE")
                delay = 5 * (phase_index - 1)
                offset = (
                    original["first_trigger_evaluation_ms"] - self.feed.base_end + 60_000 * delay
                )
                kwargs = {"reprice_minutes": delay, "episode_id": original["episode_id"]}
            advance(self.feed, offset, quote)
        symbols = ("BTCUSDT",) if self.feed is not None else ()
        phase = BOOTSTRAP_PHASES[phase_index]
        publication = (
            collect(self.active, phase, self.wire, symbols)
            if symbols
            else collect(self.active, phase, self.wire)
        )
        stamp = publication["visible_venue_upper_ms"]
        basic = {
            "phase": phase,
            "request_budget": publication["stage"]["stats"],
            "scan_id": publication["scan_id"],
            "available_venue_ms": stamp,
            "evidence": QA,
            "source_issue": publication["stage"]["issue"],
        }
        symbols = symbols or tuple(publication["stage"]["symbols"])
        if stamp is None:
            status = "SOURCE_BLOCKED" if basic["source_issue"] else "NOT_EVALUATED"
            self.trace.append({**basic, "market_status": status})
            if status == "SOURCE_BLOCKED":
                self.measurements.record(
                    "SOURCE_GAP", correlate(self.root.name, phase), code=status
                )
            return []

        result = []
        for symbol in symbols:
            key = card_correlation(self.root.name, phase, symbol)
            self.measurements.record("SOURCE_PUBLICATION", key, venue_ms=stamp)
            self.measurements.record("B2_BEGIN", key, venue_ms=stamp)
            card = self.evaluator.evaluate(
                symbol, scan=publication["scan_id"], as_of_ms=stamp, **kwargs
            )
            self.measurements.record("B2_END", key, code=card["market_status"], venue_ms=stamp)
            self.measurements.record("CARD_COMMIT", key, code=card["market_status"], venue_ms=stamp)
            verified = None
            if card["evaluation_receipt"] is not None:
                verified = replay(self.adapter, card)
                self.measurements.record(
                    "RAW_RECEIPT_VERIFIED", key, count=verified["raw_receipt_count"], venue_ms=stamp
                )
            else:
                self.measurements.record("SOURCE_GAP", key, code="SOURCE_BLOCKED", venue_ms=stamp)
            if phase_index >= 2:
                self.measurements.record(
                    f"REPRICE_{delay}", key, code=card["market_status"], venue_ms=stamp
                )
            self.trace.append(
                {
                    **basic,
                    "symbol": symbol,
                    "market_status": card["market_status"],
                    "receipt_replay": verified,
                    "episode_id": card["episode_id"],
                    "card_id": card["card_id"],
                    "measurement_key": key,
                }
            )
            self.cards.append(card)
            result.append(card)
        return result


def card_correlation(case, phase, symbol):
    return correlate(case, phase, symbol)


def actionability(original, original_version, observations):
    """Preserve original Core fields and later observations as separate records."""
    if (
        not original["episode_id"]
        or original["first_trigger_evaluation_ms"] is None
        or original["reprice"] is not None
        or original["plan"] is None
    ):
        raise Blocked("REPRICE_UNCONFIRMED_EPISODE")
    plan = original["plan"]
    trajectory = []
    for card in (original, *observations):
        receipt = card["evaluation_receipt"]
        if not receipt or card["episode_id"] != original["episode_id"]:
            raise Blocked("REPRICE_SOURCE_OR_EPISODE_MISMATCH")
        when = card["reprice"]
        quote = card["card_context"]["quote"]
        values = quote["values"]
        later = None if when is None else when["requested_delay_minutes"]
        if later is not None and (
            later not in (5, 10)
            or when["observed_venue_ms"] < original["evaluated_ms"] + later * 60_000
            or receipt["source_published_venue_ms"] <= original["evaluated_ms"]
        ):
            raise Blocked("REPRICE_CAUSAL_ORDER")
        trajectory.append(
            {
                "label": "T0" if later is None else f"T+{later}m",
                "kind": "SIGNAL_PUBLICATION" if when is None else "NEW_SOURCE_REPRICE_OBSERVATION",
                "episode_id": original["episode_id"],
                "original_card_version": original_version,
                "observation_card_id": card["card_id"],
                "reprice": when,
                "evaluated_venue_ms": card["evaluated_ms"],
                "source_available_venue_ms": receipt["source_published_venue_ms"],
                "source_available_stamp": receipt["source_durable_availability"],
                "freshness": "B5_ADMITTED_AT_EVALUATION",
                "quote_times": {name: val for name, val in quote.items() if name.endswith("_ms")},
                "bid": values.get("bidPrice"),
                "ask": values.get("askPrice"),
                "spread_usdt": values.get("spread"),
                "market_status": card["market_status"],
                "reasons": card["reasons"],
            }
        )
    if [row["label"] for row in trajectory] != ["T0", "T+5m", "T+10m"]:
        raise Blocked("REPRICE_INCOMPLETE_OR_OUT_OF_ORDER")
    return {
        "evidence": QA,
        "episode_id": original["episode_id"],
        "original_card_id": original["card_id"],
        "original_card_version": original_version,
        "original_entry": [plan["entry_low"], plan["entry_high"]],
        "original_stop": plan["hard_stop"],
        "original_targets": plan["targets"],
        "structural_invalidation": original["episode"]["structural_invalidation"],
        "original_no_chase_boundary": plan["no_chase_boundary"],
        "no_chase_policy": original["policy"],
        "trajectory": trajectory,
        "real_collection": "REPRICE_UNOBSERVED",
    }


def refresh_interface():
    return {
        "state": "INACTIVE",
        "real_observations": "REPRICE_UNOBSERVED",
        "required_gate": "H3-REPRICE",
        "schedule_enabled": False,
    }
