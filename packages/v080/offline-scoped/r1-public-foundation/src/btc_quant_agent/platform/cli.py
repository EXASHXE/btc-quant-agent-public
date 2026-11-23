"""Offline swing contract CLI. Legacy dispatch, acquisition and execution are retired."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .config import load_config
from .core import primitive
from .swing import INTERVALS, PRODUCT, decide
from .swing_store import DecisionStore

ROOT = Path(__file__).resolve().parents[3]


def local_output(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.resolve().is_relative_to(ROOT):
        raise ValueError("OUTPUT_MUST_REMAIN_IN_ISOLATED_ACTIVE_PROJECT")
    return path


def execute(args):
    if args.command == "offline-rc":
        from .rc_operator import (ingest_synthetic_fixture, observe_episode,
                                  recover, review_once, run_demo, status)

        output = local_output(args.output)
        if args.operation == "status":
            return status(output)
        if args.operation == "recover":
            return recover(output)
        if args.operation == "ingest":
            return ingest_synthetic_fixture(output, args.fixture)
        if args.operation == "review":
            return review_once(output, args.symbol, args.trigger_ms, args.decision_ms,
                               args.holding_hours)
        if args.operation == "observe":
            return observe_episode(output, args.episode_id, asof_ms=args.asof_ms)
        if args.operation == "export-c":
            from .program_c_export import build_export, write_export
            from .rc_store import RCStore

            store = RCStore(output / "state.sqlite", readonly=True)
            value = build_export(store)
            path = write_export(output, value)
            return {"mode": "FROZEN_SOURCE_NEUTRAL_EPISODE_EXPORT",
                    "path": str(path), "export_sha256": value["export_sha256"],
                    "opportunities": value["opportunity_count"],
                    "evaluator_run": False, "study_created": False}
        return run_demo(output, all_no_setup=args.operation == "no-setup")
    if args.command == "source" and args.operation == "inspect":
        from .qualified_source import source_status

        if args.wire_file:
            if args.exposure != "native":
                raise ValueError("NATIVE_WIRE_CANNOT_BE_RELABELLED_SYNTHETIC")
            from .rc_operator import inspect_native_wire_file

            required = (args.symbol, args.interval, args.received_ms, args.available_ms,
                        args.durable_ms, args.observed_now_ms)
            if any(value is None for value in required):
                raise ValueError("NATIVE_WIRE_INSPECTION_REQUIRES_EXPLICIT_UNQUALIFIED_TIMES_AND_SCOPE")
            return inspect_native_wire_file(args.wire_file, symbol=args.symbol,
                                            interval=args.interval,
                                            received_ms=args.received_ms,
                                            available_ms=args.available_ms,
                                            durable_ms=args.durable_ms,
                                            observed_now_ms=args.observed_now_ms)
        status = source_status(exposure=args.exposure.upper())
        exposure = "SYNTHETIC" if args.exposure.lower() == "synthetic" else "NATIVE_UNQUALIFIED"
        return {"exposure": exposure, "status": status,
                "native_provenance": "NO_ADMITTED_RECEIPTS; any decoded raw kline remains quarantine-only",
                "network_requests": 0, "source_qualified": False,
                "note": "inspection only; no acquisition or authority promotion"}
    if args.command == "strategies":
        from .strategies import REGISTRY
        from .swing import require_active_strategy

        if args.operation == "inspect":
            require_active_strategy(args.id)
            return primitive(REGISTRY[args.id])
        return {"product": PRODUCT, "strategies": list(REGISTRY),
                "S2": "SECONDARY_CONTRACT_DISABLED_PENDING_SCIENTIFIC_VALIDATION",
                "S3": "RESEARCH_CHALLENGER_DISABLED", "S4": "SHARED_FILTERS_NOT_ALPHA"}
    if args.command == "configs":
        c = load_config(args.path)
        return {"valid": True, "config_hash": c.hash, "product": c.product.model_dump(mode="json")}
    if args.command == "advisory":
        config = load_config(args.config)
        now = args.now_ms if args.now_ms is not None else time.time_ns() // 1_000_000
        trigger = now // INTERVALS["4H"] * INTERVALS["4H"]
        snapshots = [decide(symbol=s, decision_ms=now, trigger_close_ms=trigger, policy=config.product)
                     for s in config.universe]
        store = DecisionStore(local_output(args.store))
        for snapshot in snapshots:
            store.append(snapshot)
        return {"snapshots": [s.model_dump(mode="json") for s in snapshots],
                "note": "NO_DATA_ACQUIRED; NO_SETUP; qualified LT-B producer required"}
    if args.command == "ui":
        from .ui import page

        now = args.now_ms if args.now_ms is not None else time.time_ns() // 1_000_000
        raw = json.loads(Path(args.snapshot).read_text()) if args.snapshot else None
        result = local_output(args.output)
        result.parent.mkdir(parents=True, exist_ok=True)
        if result.exists():
            raise ValueError("DASHBOARD_OUTPUT_EXISTS_CHOOSE_NEW_FILE")
        result.write_text(page(raw, now_ms=now), encoding="utf-8")
        return {"dashboard": str(result), "mode": "LOCAL_FILE_READ_ONLY_NO_NOTIFICATIONS"}
    raise ValueError("COMMAND_OUT_OF_ACTIVE_SCOPE")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="quant", description="Offline low-frequency swing advisory contracts")
    commands = parser.add_subparsers(dest="command", required=True)
    rc = commands.add_parser("offline-rc", help="Bounded SYNTHETIC Program A RC workflow").add_subparsers(dest="operation", required=True)
    for operation in ("demo", "no-setup", "status", "recover"):
        task = rc.add_parser(operation)
        task.add_argument("--output", default="artifacts/program_a_demo" if operation != "no-setup" else "artifacts/program_a_no_setup")
    ingest = rc.add_parser("ingest", help="Ingest one allowlisted local SYNTHETIC prefix")
    ingest.add_argument("--fixture", required=True,
                        choices=("SYNTHETIC_positive_v1.jsonl", "SYNTHETIC_all_no_setup_v1.jsonl",
                                 "SYNTHETIC_mixed_v1.jsonl"))
    ingest.add_argument("--output", default="artifacts/manual")
    review = rc.add_parser("review", help="Run one bounded S1 review against durable local receipts")
    review.add_argument("--output", default="artifacts/manual")
    review.add_argument("--symbol", required=True, choices=("BTCUSDT", "ETHUSDT", "SOLUSDT"))
    review.add_argument("--trigger-ms", required=True, type=int)
    review.add_argument("--decision-ms", required=True, type=int)
    review.add_argument("--holding-hours", type=int, default=24)
    observe = rc.add_parser("observe", help="Append one synthetic later observation to a persisted episode")
    observe.add_argument("--output", default="artifacts/manual")
    observe.add_argument("--episode-id", required=True)
    observe.add_argument("--asof-ms", type=int)
    export = rc.add_parser("export-c", help="Write immutable source-neutral episodes; do not evaluate")
    export.add_argument("--output", default="artifacts/manual")
    source = commands.add_parser("source", help="Inspect source qualification without connecting")
    source_task = source.add_subparsers(dest="operation", required=True).add_parser("inspect")
    source_task.add_argument("--exposure", choices=("synthetic", "native"), required=True)
    source_task.add_argument("--wire-file")
    source_task.add_argument("--symbol", choices=("BTCUSDT", "ETHUSDT", "SOLUSDT"))
    source_task.add_argument("--interval", choices=("1h", "4h", "1d"))
    source_task.add_argument("--received-ms", type=int)
    source_task.add_argument("--available-ms", type=int)
    source_task.add_argument("--durable-ms", type=int)
    source_task.add_argument("--observed-now-ms", type=int)
    strategies = commands.add_parser("strategies").add_subparsers(dest="operation", required=True)
    strategies.add_parser("list")
    strategies.add_parser("inspect").add_argument("id")
    configs = commands.add_parser("configs").add_subparsers(dest="operation", required=True)
    configs.add_parser("validate").add_argument("path")
    advisory = commands.add_parser("advisory").add_subparsers(dest="operation", required=True)
    scan = advisory.add_parser("scan")
    scan.add_argument("--config", default=str(ROOT / "configs/trend_pullback.yaml"))
    scan.add_argument("--store", default="artifacts/swing.sqlite")
    scan.add_argument("--now-ms", type=int)
    ui = commands.add_parser("ui", help="Render a static local snapshot; no listening server")
    ui.add_argument("--snapshot")
    ui.add_argument("--output", default="artifacts/swing_dashboard.html")
    ui.add_argument("--now-ms", type=int)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(primitive(execute(args)), indent=2, sort_keys=True, allow_nan=False))
    except (ValueError, KeyError, RuntimeError, FileNotFoundError) as exc:
        parser.exit(2, f"quant: {exc}\n")
