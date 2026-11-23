"""Compose the admitted B4 Market with the pinned, unchanged B2 engine."""

from quant_personal_decision_b2.engine import Engine, market_card
from quant_personal_decision_b2.journal import Journal
from quant_personal_decision_b2.model import DEFAULT_POLICY, check, digest

from .admission import ADAPTER, MarketAdapter
from .transport import WARNINGS


class DecisionJournal(Journal):
    def __init__(self, path, *, create=False, policy=None):
        super().__init__(path, create=create, policy=policy)
        with self.connect() as db:
            bad = db.execute(
                """SELECT 1 FROM cards WHERE json_extract(payload, '$.bridge_schema')
                   IS NOT 'B4_MARKET_CARD_ENVELOPE_V1' LIMIT 1"""
            ).fetchone()
            check(bad is None, "B4_JOURNAL_ORIGIN")

    def publish(self, db, card, events):
        # The native B2 journal schema, hash chain and transactions are unchanged.
        receipt = card["evaluation_receipt"]
        check(receipt is None or receipt.get("adapter") == ADAPTER, "B4_RECEIPT_REQUIRED")
        card.update(bridge_schema="B4_MARKET_CARD_ENVELOPE_V1", warnings=list(WARNINGS),
                    source_status="READY" if card["data_ready"] else "SOURCE_BLOCKED")
        return super().publish(db, card, events)

    @staticmethod
    def unpack(row):
        card = Journal.unpack(row)
        check(card is None or (card.get("bridge_schema") == "B4_MARKET_CARD_ENVELOPE_V1"
                               and card.get("warnings") == list(WARNINGS)), "B4_JOURNAL_ORIGIN")
        return card


def compose(source, journal, origin):
    return Engine(MarketAdapter(source, origin), DecisionJournal(journal, create=True, policy=DEFAULT_POLICY))


def observe(adapter, symbol, *, scan, as_of_ms):
    card = market_card(adapter.read(symbol, scan=scan, as_of_ms=as_of_ms))
    return {**card, "bridge_schema": "B4_MARKET_CARD_ENVELOPE_V1", "warnings": list(WARNINGS),
            "source_status": "READY"}


def verify_card(adapter, card):
    receipt = card["evaluation_receipt"]
    check(receipt is not None, "CARD_HAS_NO_ADMITTED_INPUT")
    market = adapter.read(card["symbol"], scan=receipt["source_scan_id"], as_of_ms=card["evaluated_ms"],
                          publication_sha=receipt["source_publication_sha256"])
    check(digest(market.source) == digest(receipt), "CARD_RECEIPT_DIGEST_MISMATCH")
    return {"card_id": card["card_id"], "card_sha256": digest(card), "receipt_sha256": digest(receipt),
            "raw_receipts": len(receipt["raw_receipts"]), "market_status": card["market_status"],
            "warnings": list(WARNINGS)}
