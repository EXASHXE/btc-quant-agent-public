"""Compare the recorded cards with a chronological rebuild from raw B5 QA receipts."""

import argparse
import json
from pathlib import Path

from quant_personal_decision_b2.model import digest
from quant_personal_live_public_b5.admission import Adapter
from quant_personal_live_public_b5.decision import DecisionJournal, engine, replay
from quant_personal_live_public_b5.ledger import Ledger

parser=argparse.ArgumentParser()
parser.add_argument("case",type=Path)
parser.add_argument("new_journal",type=Path)
args=parser.parse_args()
if args.new_journal.exists():
    raise SystemExit("A fresh review journal is required")
adapter=Adapter(Ledger.open_qa(args.case/"source.sqlite"))
original=DecisionJournal(args.case/"journal.sqlite")
rebuilder=engine(adapter,args.new_journal)
with original.connect() as db:
    ids=[row[0] for row in db.execute("SELECT id FROM cards ORDER BY as_of")]
for ident in ids:
    saved=original.read(card_id=ident)
    verified=replay(adapter,saved)
    when=saved["reprice"]
    params={"reprice_minutes":when["requested_delay_minutes"],"episode_id":saved["episode_id"]} if when else {}
    rebuilt=rebuilder.evaluate(saved["symbol"],scan=saved["evaluation_receipt"]["source_scan_id"],
                               as_of_ms=saved["evaluated_ms"],**params)
    old={k:v for k,v in saved.items() if k != "journal_recorded_wall_ms"}
    new={k:v for k,v in rebuilt.items() if k != "journal_recorded_wall_ms"}
    if old != new:
        raise SystemExit(f"REPLAY_MISMATCH {ident}")
    print(json.dumps({**verified,"deterministic_payload_sha256":digest(old),"pass":True},sort_keys=True))
