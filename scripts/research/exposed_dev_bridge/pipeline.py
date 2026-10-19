"""Manual offline P3 CLI; inspect never evaluates returns.

    python3 -m scripts.research.exposed_dev_bridge.pipeline inspect \
        --binance-root <Q3> --okx-root <Q3> --output-dir /tmp/fresh
    python3 -m scripts.research.exposed_dev_bridge.pipeline materialize \
        --scope <pre-existing-owner-scope.json> --output-dir /tmp/another-fresh

Use synthetic-contract-demo for the TEST-ONLY P1 parser/funding/cost contract.
inspect-proposal hashes compressed proposed files without decoding any CSV.
materialize accepts either legacy pre-pinned hashes or an explicit Owner v2
panel-materialization permission with a derived P1 integrity binding.
synthetic-fullfold runs the actual P1 folds on a TEST-ONLY P3 panel.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.cross_venue import pipeline as p2

from . import LABELS, TASK, checked_path
from .archive_adapter import materialize_authorized
from .inspection import inspect_proposal, inspect_sources, panel_schema, proposals, source_coverage

OUTPUT_FILES = ("source_coverage.json", "lineage_manifest.json", "hourly_origin_coverage.jsonl",
                "authorization_gate.json", "feature_panel_schema.json", "bridge_result.json", "test_receipt.json")


def _base(status: str) -> dict[str, Any]:
    return {"task": TASK, "status": status, "labels": list(LABELS),
            "historical_outcomes_evaluated": 0, "outcome_labels_read": 0,
            "market_requests": 0, "ticks_l2_opened": 0, "receiver_pit": "PIT_UNKNOWN",
            "real_funds_write": "NONE", "evaluation_delegated": False}


def _write(output: Path, documents: dict[str, Any], rows: list[dict[str, Any]],
           checks: dict[str, bool]) -> None:
    hashes = {}
    with n.directory_fd(output) as directory:
        def write(name: str, chunks: Any) -> None:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            digest = hashlib.sha256()
            with os.fdopen(fd, "wb") as stream:
                for block in chunks:
                    stream.write(block)
                    digest.update(block)
            hashes[name] = digest.hexdigest()
        for name in OUTPUT_FILES[:-1]:
            write(name, (n.canonical_bytes(r) for r in rows) if name.endswith(".jsonl")
                  else [n.canonical_bytes(documents[name])])
        write("test_receipt.json", [n.canonical_bytes({
            "task": TASK, "receipt_kind": "RUNTIME_CONTRACT_CHECKS_NOT_PYTEST",
            "pytest": "NOT_RUN_BY_CLI", "checks": checks, "artifact_sha256": dict(hashes),
            "historical_outcomes_evaluated": documents["bridge_result.json"]["historical_outcomes_evaluated"],
            "outcome_labels_read": documents["bridge_result.json"]["outcome_labels_read"],
            "labels": list(LABELS)})])


def inspect(roots: dict[tuple[str, str], Path], output_dir: Path) -> dict[str, Any]:
    output = p2.prepare_output(checked_path(output_dir), roots.values())
    state = inspect_sources(roots)
    coverage = source_coverage(state)
    denominator = sum((n.quarter_window(q)[1] - n.quarter_window(q)[0]) // 3600 * 2
                      for q in {q for q, _ in roots})
    result = {**_base("INSPECTION_ONLY"), "source_coverage_status": coverage["status"],
        "scheduled_origin_denominator": denominator, "origin_rows": len(state.rows),
        "no_action_origins": sum(r["action"] == "NO_ACTION" for r in state.rows),
        "native_feature_ready_origins": sum(r["native_feature_ready"] for r in state.rows),
        "p1_btc_x_ready_origins": sum(r["p1"].get("x_complete", False) for r in state.rows),
        "p1_btc_xz_ready_origins": sum(all(p1_ready(r["p1"])) for r in state.rows if r["asset"] == "BTC"),
        "proposed_development": proposals(state),
        "blockers": ["EXPOSED_DEV_NOT_AUTHORIZED", "GOVERNED_HOLDOUT_DATES_UNRESOLVED"],
        "error": {"code": state.error.code, "details": state.error.details} if state.error else None,
        "exit_code": 2 if state.error else 1 if coverage["status"] != "PASS" else 0}
    if state.error:
        result["blockers"].append(state.error.code)
    gate = {"gate_status": "DENIED", "reason": "NO_PREEXISTING_EXPLICIT_OWNER_EXPOSED_DEV_SCOPE",
            "scope_supplied": False, "outcome_labels_read": 0,
            "historical_outcomes_evaluated": 0, "labels": list(LABELS)}
    lineage = {"snapshots": [s.receipt() for s in state.snapshots],
        "sources": [{"source_id": s.source_id, "root": str(s.snapshot.root),
            "relative_path": s.record["local_path"], "venue": s.snapshot.venue,
            "market": s.record.get("market"), "symbol": s.record["symbol"], "family": s.record["family"],
            "period": s.record["period"], "verdict": s.record.get("verdict"),
            "manifest_raw_sha256": s.record.get("local_sha256"), "actual_raw_sha256": s.actual_sha256,
            "scan": s.scan} for s in state.sources],
        "feature_scan_budget": state.budget.receipt(), "p1_control_scan_budget": getattr(state, "p1_budget", None),
        "scanned_raw_inputs_unchanged": state.raw_inputs_unchanged,
        "raw_hash_scope": "FULLY_SCANNED_PASS_FEATURE_ZIPS_ONLY_NOT_L2_OR_TRADES",
        "file_calendar": {"okx": "UTC+08:00", "binance": "UTC"}, "event_epoch_shift_us": 0,
        "receiver_pit": "PIT_UNKNOWN"}
    _write(output, {"source_coverage.json": coverage, "lineage_manifest.json": lineage,
        "authorization_gate.json": gate, "feature_panel_schema.json": panel_schema(), "bridge_result.json": result},
        state.rows, {"fixed_origin_denominator_preserved": len(state.rows) == denominator,
            "all_origins_no_action": all(r["action"] == "NO_ACTION" for r in state.rows),
            "manifests_unchanged": bool(state.snapshots) and all(s.unchanged for s in state.snapshots),
            "scanned_raw_inputs_unchanged": state.raw_inputs_unchanged,
            "no_outcome_evaluation": True, "inspection_complete": state.error is None})
    return result


def p1_ready(row: dict[str, Any]) -> tuple[bool, bool]:
    from scripts.research.strategy_eval.clocked_dataset import ready
    return ready(row)


def materialize(scope: Path, output_dir: Path, p1_allowlist: Path | None = None,
                *, evaluate: bool = False) -> dict[str, Any]:
    # Output confinement is checked even when the supplied authority is invalid.
    # Reading this document is not permission to open any referenced payload.
    import json
    inputs = [scope] + ([p1_allowlist] if p1_allowlist is not None else [])
    try:
        with n.published_file(checked_path(scope), 1024**2) as stream:
            doc = json.loads(stream.read(), object_pairs_hook=n._unique, parse_constant=n._bad_constant)
        if type(doc) is dict and type(doc.get("sources")) is list:
            inputs.extend(Path(s["root"]) for s in doc["sources"]
                          if type(s) is dict and type(s.get("root")) is str)
    except (OSError, ValueError):
        pass
    output = p2.prepare_output(checked_path(output_dir), inputs)
    ledger: dict[str, Any] = {"outcome_source_records_exposed": 0, "dual_gate_authorized": False}
    try:
        admitted = materialize_authorized(scope, p1_allowlist, output, evaluate=evaluate, audit=ledger)
        ledger = admitted.pop("ledger")
        contract = ledger["authority_contract"]
        gate = {"gate_status": ("OWNER_PHASE_ONE_AND_DERIVED_P1_INTEGRITY" if
                               contract == "OWNER_PHASE_ONE_DERIVED_P1_INTEGRITY" else "DUAL_GATE_AUTHORIZED"),
                "authority_contract": contract, "p1_authorization": admitted["p1_authorization"]}
        result = {**_base(admitted["status"]), **admitted, "exit_code": 0,
                  "materialization": ("OWNER_PERMITTED_PANEL_DERIVED_INTEGRITY_PARSED" if
                                      contract == "OWNER_PHASE_ONE_DERIVED_P1_INTEGRITY" else
                                      "OWNER_AND_P1_PINNED_PANEL_PARSED"),
                  "outcome_labels_read": ledger["outcome_source_rows_read"],
                  "historical_outcomes_evaluated": admitted.get("evaluated_origin_count", 0),
                  "blockers": []}
    except (n.BridgeError, OSError, ValueError, KeyError, TypeError, csv.Error, zipfile.BadZipFile, UnicodeError) as exc:
        error = exc if isinstance(exc, n.BridgeError) else n.BridgeError(str(exc) if isinstance(exc, ValueError)
                                                                 else "SCOPE_PARSE_OR_IO_ERROR")
        evaluated = ledger.get("evaluated_origin_count", None if ledger.get("p1_evaluation_attempted") else 0)
        gate = {"gate_status": "DENIED", "reason": error.code, "details": error.details,
                "outcome_labels_read": ledger["outcome_source_records_exposed"], "historical_outcomes_evaluated": evaluated}
        result = {**_base("MATERIALIZATION_BLOCKED" if ledger["dual_gate_authorized"] else "AUTHORIZATION_DENIED"),
                  "outcome_labels_read": ledger["outcome_source_records_exposed"],
                  "historical_outcomes_evaluated": evaluated,
                  "evaluation_delegated": ledger.get("p1_evaluation_attempted", False),
                  "blockers": [error.code], "exit_code": 2,
                  "origin_rows": 0, "materialization": "DENIED_NO_OUTCOME_PANEL_WRITTEN"}
    _write(output, {"source_coverage.json": {"status": "SEE_LINEAGE", "families": []},
        "lineage_manifest.json": ledger, "authorization_gate.json": {**gate, "labels": list(LABELS)},
        "feature_panel_schema.json": panel_schema(), "bridge_result.json": result}, [],
        {"dual_gate_enforced": True, "no_synthetic_materialize_bypass": True,
         "no_evaluation_without_both_gates": True})
    return result


def run_demo(output_dir: Path, hours: int = 120) -> dict[str, Any]:
    from .synthetic_contract import run_demo as contract_demo
    summary = contract_demo(output_dir, n_hours=hours)
    return {**_base(summary["status"]), "origin_rows": summary["origins_scheduled"],
            "synthetic_trades": summary["p1_economics_delegation"]["resolved_trades"],
            "real_historical_outcomes_evaluated": 0, "exit_code": 0, "summary": summary}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("inspect")
    command.add_argument("--binance-root", type=Path, required=True)
    command.add_argument("--okx-root", type=Path, required=True)
    command.add_argument("--binance-q2", type=Path)
    command.add_argument("--okx-q2", type=Path)
    command.add_argument("--output-dir", type=Path, required=True)
    command = commands.add_parser("materialize")
    command.add_argument("--scope", type=Path, required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--p1-allowlist", type=Path)
    command.add_argument("--evaluate", action="store_true")
    command = commands.add_parser("synthetic-contract-demo", aliases=["demo"])
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--hours", type=int, default=120)
    command = commands.add_parser("synthetic-fullfold")
    command.add_argument("--output-dir", type=Path, required=True)
    command = commands.add_parser("inspect-proposal")
    command.add_argument("--scope", type=Path, required=True)
    command.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            roots = {("Q3", "binance"): args.binance_root, ("Q3", "okx"): args.okx_root}
            if args.binance_q2 is not None:
                roots["Q2", "binance"] = args.binance_q2
            if args.okx_q2 is not None:
                roots["Q2", "okx"] = args.okx_q2
            result = inspect(roots, args.output_dir)
            print(f"{result['status']} rc={result['exit_code']} origins={result['origin_rows']} outcomes=0")
            return result["exit_code"]
        elif args.command in ("demo", "synthetic-contract-demo"):
            result = run_demo(args.output_dir, hours=args.hours)
            print(f"{result['status']} rc={result['exit_code']} origins={result['origin_rows']} synthetic_trades={result['synthetic_trades']} real_historical_outcomes=0")
            return result["exit_code"]
        elif args.command == "synthetic-fullfold":
            from .synthetic_fullfold import run_fullfold
            result = run_fullfold(args.output_dir)
            print(f"{result['status']} rc={0 if result['executed_outer_folds'] == 3 else 1} origins={result['origin_count']} folds={result['executed_outer_folds']} real_outcome_labels_read=0")
            return 0 if result["executed_outer_folds"] == 3 else 1
        elif args.command == "inspect-proposal":
            result = inspect_proposal(args.scope, args.output_dir)
            print(f"{result['status']} rc=0 archives={result['pass_compressed_archives']} payload_rows=0 outcomes=0 P3_ACCESS_SCOPE_HOLD")
            return result["exit_code"]
        else:
            result = materialize(args.scope, args.output_dir, args.p1_allowlist, evaluate=args.evaluate)
            print(f"{result['status']} rc={result['exit_code']} origins={result['origin_rows']} outcomes={result['outcome_labels_read']}")
            return result["exit_code"]
    except (n.BridgeError, OSError, ValueError) as exc:
        print(f"BLOCKED {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
