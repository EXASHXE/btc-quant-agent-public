"""Replay immutable raw observations into a separate journal and compare every card."""

import argparse
import json
from pathlib import Path

from quant_personal_decision_b2.model import digest
from quant_personal_public_bridge_b4.decision import DecisionJournal, compose, verify_card
from quant_personal_public_bridge_b4.transport import FIXTURE

parser = argparse.ArgumentParser()
parser.add_argument("case", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
if args.output.exists():
    raise SystemExit("Use a fresh replay journal")
source = args.case / "source.sqlite"
old = DecisionJournal(args.case / "journal.sqlite")
engine = compose(source, args.output, FIXTURE)
with old.connect() as db:
    ids = [row[0] for row in db.execute("SELECT id FROM cards ORDER BY as_of")]
for ident in ids:
    card = old.read(card_id=ident)
    proof = verify_card(engine.adapter, card)
    receipt = card["evaluation_receipt"]
    replay = card["reprice"]
    kwargs = {"reprice_minutes": replay["requested_delay_minutes"], "episode_id": card["episode_id"]} if replay else {}
    rebuilt = engine.evaluate(card["symbol"], scan=receipt["source_scan_id"], as_of_ms=card["evaluated_ms"], **kwargs)
    reproducible = {key: value for key, value in card.items() if key != "journal_recorded_wall_ms"}
    if reproducible != {key: value for key, value in rebuilt.items() if key != "journal_recorded_wall_ms"}:
        raise SystemExit(f"REPLAY_MISMATCH {ident}")
    print(json.dumps({**proof, "replayed_card_content_sha256": digest(reproducible), "pass": True}, sort_keys=True))
