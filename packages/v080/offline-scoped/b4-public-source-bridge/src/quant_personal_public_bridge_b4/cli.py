"""Local inspection, synthetic dry-run, readiness, card and replay commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .live import LiveDisabled, open_live


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "live-scan":
        try:
            open_live()
        except LiveDisabled as exc:
            print(str(exc), file=sys.stderr)
            return 3

    from quant_personal_decision_b2.model import DecisionError, encode
    from quant_personal_public_b1.policy import SourceBlocked

    from .demo import SCENARIOS, replay, run
    from .admission import MarketAdapter
    from .decision import DecisionJournal, compose, observe
    from .routes import CONTRACT, HOST, INTERVALS, ROUTES, SYMBOLS
    from .source import Ledger
    from .transport import FIXTURE, LOOPBACK, WARNINGS

    parser = argparse.ArgumentParser(prog="quant-public-b4")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("live-scan", help="disabled in this wheel")
    dry = commands.add_parser("dry-run", help="collect and evaluate one synthetic scenario into a new directory")
    dry.add_argument("directory", type=Path)
    dry.add_argument("--scenario", choices=SCENARIOS, default="trend_pullback-long")
    dry.add_argument("--chase", action="store_true")
    readiness = commands.add_parser("readiness", help="run all four offline scenarios into a new directory")
    readiness.add_argument("directory", type=Path)
    inspect = commands.add_parser("inspect", help="inspect bridge contract or local source publication")
    inspect.add_argument("--source", type=Path)
    inspect.add_argument("--origin", choices=(FIXTURE, LOOPBACK), default=FIXTURE)
    inspect.add_argument("--scan", type=int)
    for command in ("card", "replay", "note", "evaluate"):
        entry = commands.add_parser(command)
        entry.add_argument("journal", type=Path)
        if command != "evaluate":
            entry.add_argument("--card-id", required=command == "note")
        if command in {"replay", "evaluate"}:
            entry.add_argument("source", type=Path)
            entry.add_argument("--origin", choices=(FIXTURE, LOOPBACK), default=FIXTURE)
        if command == "note":
            entry.add_argument("--event-id", required=True)
            entry.add_argument("--as-of", type=int, required=True)
            entry.add_argument("--action", choices=("WATCH", "SKIP", "INTENDED_ACTION", "NOTE"), required=True)
            entry.add_argument("--note", default="")
        if command == "evaluate":
            entry.add_argument("--scan", type=int, required=True)
            entry.add_argument("--as-of", type=int, required=True)
            entry.add_argument("--symbol", choices=sorted(SYMBOLS), required=True)
            entry.add_argument("--observe-only", action="store_true")
            entry.add_argument("--reprice", type=int, choices=(5, 10))
            entry.add_argument("--episode-id")
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            value = {"contract": CONTRACT, "future_host": HOST, "live": "NOT_AUTHORIZED",
                     "live_requests_enabled": False, "warnings": list(WARNINGS), "symbols": sorted(SYMBOLS),
                     "frames": list(INTERVALS), "allowed_routes": {k: sorted(v) for k, v in ROUTES.items()}}
            if args.source:
                value["publication"] = Ledger(args.source, args.origin).publication(args.scan)
        elif args.command == "dry-run":
            value = run(args.directory, args.scenario, chase=args.chase)
        elif args.command == "readiness":
            args.directory.mkdir()
            cases = []
            for name, (family, direction) in SCENARIOS.items():
                case = run(args.directory / name, name)
                cards = case["cards"]
                confirmed = cards[1]["episode"] or {}
                passed = (cards[1]["market_status"] == "EXECUTABLE"
                          and (confirmed.get("family"), confirmed.get("direction")) == (family, direction)
                          and [c["reprice"]["requested_delay_minutes"] for c in cards[2:]] == [5, 10])
                cases.append({"scenario": name, "pass": passed, "statuses": [c["market_status"] for c in cards],
                              "requests_by_scan": case["requests_by_scan"],
                              "replay": replay(args.directory / name / "source.sqlite",
                                               args.directory / name / "journal.sqlite", cards[1]["card_id"])})
            value = {"live": "NOT_AUTHORIZED", "warnings": list(WARNINGS),
                     "offline_readiness": all(c["pass"] for c in cases), "cases": cases}
        elif args.command == "evaluate" and args.observe_only:
            if args.reprice is not None or args.episode_id is not None:
                raise DecisionError("OBSERVE_ONLY_REPRICE_CONFLICT")
            value = observe(MarketAdapter(args.source, args.origin), args.symbol, scan=args.scan, as_of_ms=args.as_of)
        elif args.command == "evaluate":
            value = compose(args.source, args.journal, args.origin).evaluate(
                args.symbol, scan=args.scan, as_of_ms=args.as_of, reprice_minutes=args.reprice,
                episode_id=args.episode_id)
        elif args.command == "replay":
            value = replay(args.source, args.journal, args.card_id, origin=args.origin)
        elif args.command == "note":
            value = DecisionJournal(args.journal).manual(card_id=args.card_id, operator_id=args.event_id,
                                                          action=args.action, time_ms=args.as_of, note=args.note)
        else:
            value = DecisionJournal(args.journal).read(card_id=args.card_id)
            if value is None:
                raise DecisionError("CARD_UNKNOWN")
    except (DecisionError, SourceBlocked, OSError, LiveDisabled) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(encode(value))
    return 0 if value.get("offline_readiness", True) else 2
