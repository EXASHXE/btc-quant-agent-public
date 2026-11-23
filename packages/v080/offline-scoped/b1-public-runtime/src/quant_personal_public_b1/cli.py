"""Read-only operator commands for the local B1 fixture runtime."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .fixture import FixtureClock
from .live import open_live
from .policy import SourceBlocked
from .runtime import Runtime
from .session import RunIdentity
from .store import Store, encode
from .wire import FIXTURE, LOOPBACK


def demo(output: Path) -> int:
    output.mkdir(exist_ok=False)
    db = output / "fixture.sqlite"
    clock = FixtureClock()
    first = Runtime.fixtures(db, clock, identity=RunIdentity("fixture-clock-v1", "demo-initial"))
    cold = first.scan()
    clock.advance(300_000)
    second = Runtime.fixtures(db, clock, identity=RunIdentity("fixture-clock-v1", "demo-refresh"))
    warm = second.scan()
    saved = Store(db, FIXTURE, "fixture-local")
    reload_equal = cold == saved.snapshot(scan=1) and warm == saved.snapshot(scan=2)
    for snapshot in (cold, warm):
        index = snapshot["scan_id"]
        (output / f"snapshot_{index}.json").write_text(json.dumps(snapshot, indent=2) + "\n")
        (output / f"receipts_{index}.json").write_text(json.dumps(second.budget.evidence(index), indent=2) + "\n")
    summary = {"origin": cold["source_origin"], "symbols": cold["symbols"], "timeframes": cold["frame_order"],
               "status": [cold["source_status"], warm["source_status"]],
               "strategy_status": warm["strategy_status"], "account_context_status": warm["account_context_status"],
               "request_counts": [cold["request_count"], warm["request_count"]],
               "reload_equal": reload_equal, "historical_cutoff_visible": saved.snapshot(
                   as_of_ms=cold["clock"].get("bar_cutoff_venue_ms")) is not None}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(encode(summary))
    return int(not (reload_equal and cold["data_ready"] and warm["data_ready"]
                    and not summary["historical_cutoff_visible"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-public-b1", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo_cmd = commands.add_parser("demo", help="two deterministic fixture scans and causal replay")
    demo_cmd.add_argument("--output", type=Path, required=True)
    read = commands.add_parser("read", help="inspect a committed snapshot without dispatching requests")
    read.add_argument("--db", type=Path, required=True)
    read.add_argument("--origin", choices=("fixture", "loopback"), required=True)
    identity = read.add_mutually_exclusive_group()
    identity.add_argument("--scan", type=int)
    identity.add_argument("--as-of-venue-ms", type=int)
    commands.add_parser("live", help="show the dormant genuine-public capability gate")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            return demo(args.output)
        if args.command == "live":
            open_live(operating_scope=None, controller_activation=None)
        origin, egress = (FIXTURE, "fixture-local") if args.origin == "fixture" else (LOOPBACK, "loopback-qa")
        result = Store(args.db, origin, egress).snapshot(scan=args.scan, as_of_ms=args.as_of_venue_ms)
        print(encode(result))
        return 0 if result is not None else 1
    except SourceBlocked as exc:
        print(encode({"error": exc.code, "detail": exc.detail}))
        return 2
    except (sqlite3.Error, OSError) as exc:
        print(encode({"error": "LOCAL_IO_FAILED", "detail": str(exc)}))
        return 2
