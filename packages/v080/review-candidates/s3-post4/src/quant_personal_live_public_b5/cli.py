"""Operator entry points with a default-closed activation check."""

import argparse
import sqlite3
import sys
from pathlib import Path

from quant_personal_public_b1.policy import SourceBlocked
from quant_personal_public_b1.store import encode

from .contract import AUTHORITY, CONTRACT, DISABLED, INTERVALS, ROUTES, SYMBOL_ORDER
from .trust import production_roots


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in {"preflight","live-once","revoke"}:
        try:
            production_roots()
        except SourceBlocked as exc:
            print(exc.code, file=sys.stderr)
            return 3

    from quant_personal_decision_b2.model import DecisionError, check
    from quant_personal_public_bridge_b4.demo import SCENARIOS

    from .admission import Adapter
    from .decision import DecisionJournal, replay
    from .ledger import Ledger
    from .live import live_once, open_historical, preflight, revoke
    from .offline import readiness, run_case
    from .planning import preview

    parser = argparse.ArgumentParser(prog="quant-public-b5")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inspect")
    dry = sub.add_parser("dry-run")
    dry.add_argument("--fixture-directory", type=Path)
    dry.add_argument("--scenario", default="trend_pullback-long", choices=SCENARIOS)
    dry.add_argument("--chase", action="store_true")
    qa = sub.add_parser("readiness")
    qa.add_argument("directory", type=Path)
    for command in ("preflight","live-once","revoke"):
        entry = sub.add_parser(command)
        for name in ("wheel","scope","activation"):
            entry.add_argument("--"+name, required=True, type=Path)
    for command in ("card","replay"):
        entry = sub.add_parser(command)
        entry.add_argument("--journal",type=Path)
        entry.add_argument("--card-id")
        entry.add_argument("--genuine-wheel",type=Path)
        if command == "replay":
            entry.add_argument("--source",type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            try:
                production_roots()
                trust = "PROVISIONED_REQUIRES_EXACT_DUAL_APPROVAL_AND_ONE_SHOT"
            except SourceBlocked:
                trust = DISABLED
            value = {"authority": AUTHORITY, "methods":["GET"], "routes":list(ROUTES),
                     "symbols":list(SYMBOL_ORDER), "frames":list(INTERVALS), "contract":CONTRACT,
                     "production_state":trust, "funding_weight":"ACTIVATION_REVIEW_REQUIRED"}
        elif args.command == "dry-run":
            value = (preview() if args.fixture_directory is None else
                     run_case(args.fixture_directory, args.scenario, chase=args.chase))
        elif args.command == "readiness":
            value = readiness(args.directory)
        elif args.command == "live-once":
            value = live_once(args.wheel,args.scope,args.activation,
                              progress=lambda info: print(encode(info),file=sys.stderr,flush=True))
        elif args.command == "preflight":
            value = preflight(args.wheel,args.scope,args.activation)
        elif args.command == "revoke":
            value = revoke(args.wheel,args.scope,args.activation)
        else:
            adapter = None
            if args.genuine_wheel is not None:
                check(args.journal is None and getattr(args,"source",None) is None, "GENUINE_PATHS_ARE_SCOPE_BOUND")
                adapter, journal = open_historical(args.genuine_wheel)
            else:
                check(args.journal is not None, "QA_JOURNAL_REQUIRED")
                journal = args.journal
            decision = DecisionJournal(journal, adapter.ledger.origin) if adapter else DecisionJournal(journal)
            card = decision.read(card_id=args.card_id)
            check(card is not None, "CARD_UNKNOWN")
            if args.command == "card":
                value = card
            else:
                if adapter is None:
                    check(args.source is not None, "QA_SOURCE_LEDGER_REQUIRED")
                    adapter = Adapter(Ledger.open_qa(args.source))
                value = replay(adapter, card)
        print(encode(value))
        return 0 if value.get("offline_readiness",True) else 2
    except (SourceBlocked, DecisionError, sqlite3.Error, ValueError, TypeError, OSError) as exc:
        # Genuine errors expose a bounded reason, without local egress or file details.
        if args.command in {"preflight","live-once","revoke"} or getattr(args,"genuine_wheel",None) is not None:
            code = getattr(exc,"code","LOCAL_REVIEW_REQUIRED")
            print(code,file=sys.stderr)
            return 3 if code == DISABLED else 2
        print(str(exc),file=sys.stderr)
        return 2
