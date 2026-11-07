"""Finite local Source -> S1 -> durable Shadow -> HTML -> economic evaluator."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path


def main(argv=None):
    from . import rc_operator as operator
    from .program_c_export import build_export, write_export
    from .rc_store import RCStore
    parser = argparse.ArgumentParser(prog="quant", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    for name in ("replay", "status", "recover", "dashboard", "export", "ingest", "review", "observe"):
        task = commands.add_parser(name)
        task.add_argument("--output", type=Path, required=True)
        if name == "replay":
            task.add_argument("--all-no-setup", action="store_true")
        elif name == "ingest":
            task.add_argument("--fixture", default="SYNTHETIC_mixed_v1.jsonl")
        elif name == "review":
            task.add_argument("--symbol", choices=("BTCUSDT", "ETHUSDT", "SOLUSDT"), required=True)
            task.add_argument("--trigger-ms", type=int, required=True)
            task.add_argument("--decision-ms", type=int, required=True)
            task.add_argument("--holding-hours", type=int, default=24)
        elif name == "observe":
            task.add_argument("--episode-id", required=True)
            task.add_argument("--asof-ms", type=int)
    task = commands.add_parser("evaluate")
    task.add_argument("--input", type=Path, required=True)
    task.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            result = {"python": sys.version.split()[0], "status": "OFFLINE_READY_NATIVE_BLOCKED_AUTHORITY",
                      "dependencies": {p: importlib.metadata.version(p) for p in
                                       ("numpy", "pandas", "PyYAML", "pydantic")},
                      "strategy": "S1 trend_pullback", "S2": "RESEARCH_ONLY_DISABLED",
                      "S3": "RESEARCH_ONLY_DISABLED", "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
                      "source_qualified": False, "shadow_qualified": False, "economically_validated": False,
                      "native_admission": "NATIVE_BLOCKED_AUTHORITY", "native_market_requests": 0,
                      "clock": "UNVERIFIED", "rights": "UNKNOWN", "native_collector": "ABSENT"}
        elif args.command == "replay":
            result = operator.run_demo(args.output, all_no_setup=args.all_no_setup)
        elif args.command == "ingest":
            result = operator.ingest_synthetic_fixture(args.output, args.fixture)
        elif args.command == "review":
            result = operator.review_once(args.output, args.symbol, args.trigger_ms, args.decision_ms,
                                          args.holding_hours)
        elif args.command == "observe":
            result = operator.observe_episode(args.output, args.episode_id, asof_ms=args.asof_ms)
        elif args.command in ("recover", "dashboard"):
            result = operator.recover(args.output)
        elif args.command == "status":
            result = operator.status(args.output)
        elif args.command == "export":
            value = build_export(RCStore(args.output / "state.sqlite", readonly=True))
            result = {"path": str(write_export(args.output, value)), "export_sha256": value["export_sha256"]}
        else:
            from .evaluation_adapter import evaluate_export
            result = evaluate_export(args.input, args.output)
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
