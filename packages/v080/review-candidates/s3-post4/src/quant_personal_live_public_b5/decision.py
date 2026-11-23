"""B5 card envelope over the unchanged accepted B2 strategy, risk and journal."""


from quant_personal_decision_b2.engine import Engine
from quant_personal_decision_b2.journal import Journal
from quant_personal_decision_b2.model import DEFAULT_POLICY, check, digest

from .admission import ADAPTER
from .contract import GENUINE, QA, QA_WARNINGS
from .trust import production_roots

CARD_SCHEMA = "B5_MARKET_DECISION_ENVELOPE_V1"


class DecisionJournal(Journal):
    def __init__(self, path, lane=QA, *, create=False):
        if lane == GENUINE:
            production_roots()
        self.lane = lane
        super().__init__(path, create=create, policy=DEFAULT_POLICY)
        with self.connect() as db:
            bad = db.execute("""SELECT 1 FROM cards WHERE json_extract(payload,'$.b5_schema') IS NOT ?
                              OR json_extract(payload,'$.source_lane') IS NOT ? LIMIT 1""",
                             (CARD_SCHEMA, lane)).fetchone()
            check(bad is None, "B5_JOURNAL_ORIGIN")

    def publish(self, db, card, events):
        receipt = card["evaluation_receipt"]
        check(receipt is None or (receipt.get("adapter") == ADAPTER and receipt.get("source_origin") == self.lane),
              "B5_ADMITTED_RECEIPT_REQUIRED")
        card.update(b5_schema=CARD_SCHEMA, source_lane=self.lane, decision_scope="MARKET_SIDE",
                    source_status="READY" if card["data_ready"] else "SOURCE_BLOCKED",
                    safe_position_size="UNKNOWN", actual_order_protection="UNKNOWN",
                    warnings=list(QA_WARNINGS) if self.lane == QA else [])
        if self.lane == GENUINE:
            card["evidence"] = GENUINE if receipt is not None else "UNQUALIFIED_PUBLIC_SOURCE"
            if card.get("plan") and "evidence_confidence" in card["plan"]:
                card["plan"]["evidence_confidence"] = "MODELED_FROM_ADMITTED_PUBLIC_DATA"
            if card["market_status"] == "EXECUTABLE":
                card["next_human_action"] = "Verify exposure, protective orders and costs locally before any human action."
        return super().publish(db, card, events)

    @staticmethod
    def add_event(db, kind, card, detail, *, identity=None, evidence=QA):
        label = evidence if kind == "MANUAL" else card["evidence"]
        return Journal.add_event(db, kind, card, detail, identity=identity, evidence=label)


def engine(adapter, path):
    return Engine(adapter, DecisionJournal(path, adapter.ledger.origin, create=True))


def replay(adapter, card):
    receipt = card["evaluation_receipt"]
    check(receipt is not None and card.get("source_lane") == adapter.ledger.origin, "CARD_HAS_NO_ADMITTED_SOURCE")
    market = adapter.read(card["symbol"], scan=receipt["source_scan_id"], as_of_ms=card["evaluated_ms"],
                          publication_sha=receipt["source_publication_sha256"])
    check(digest(market.source) == digest(receipt), "CARD_RECEIPT_DIGEST_MISMATCH")
    return {"card_id": card["card_id"], "card_sha256": digest(card), "receipt_sha256": digest(market.source),
            "raw_receipt_count": len(market.source["raw_receipts"]), "market_status": card["market_status"],
            "evidence": card["evidence"]}
