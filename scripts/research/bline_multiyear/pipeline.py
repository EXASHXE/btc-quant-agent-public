"""CLI: feature-coverage, preregister, synthetic-p1, evaluate-authorized.

Final artifacts are confined to research-bline-r1. Historical features never
contain outcomes. Real evaluation requires an already materialized, authorized
P3 panel and its derived P1 integrity allowlist, plus Owner binding to these
specific feature bytes and frozen registration. This CLI never authors permits.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.research.exposed_dev_bridge.archive_adapter import matched_population
from scripts.research.exposed_dev_bridge.authorization import (
    _private_dates_confirmed,
    validate_scope,
)
from scripts.research.strategy_eval import clocked_dataset as data
from scripts.research.strategy_eval import pipeline as p1

from . import LABELS, TASK
from .contracts import X_NAMES, canonical, epoch, excluded, prior_map, registration, sha
from .panel import Lake, coverage

DEFAULT_LAKE = Path("/root/workspace/project/crypto-data/lakehouse")
OUTPUT_ROOT = DEFAULT_LAKE/"research-bline-r1"
REPO = Path(__file__).resolve().parents[3]


def output_directory(path: Path) -> Path:
    path = data.safe_directory(path, missing=True)
    if not path.is_relative_to(OUTPUT_ROOT) or path == OUTPUT_ROOT:
        raise ValueError("OUTPUT_MUST_BE_NEW_RESEARCH_BLINE_R1_CHILD")
    if path.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    path.mkdir(parents=True)
    return path


def write_json(output: Path, name: str, value) -> None:
    with (output/name).open("xb") as stream:
        stream.write(canonical(value))


def _preexisting(path: Path, started_ns: int) -> None:
    data.safe_file(path.parent, path.name, 512*1024*1024)
    if path.stat().st_mtime_ns > started_ns:
        raise ValueError("AUTHORITY_OR_INPUT_NOT_PREEXISTING")


def evaluate_authorized(scope_path: Path | None, allowlist_path: Path | None,
                        panel_path: Path | None, features_path: Path | None,
                        registration_path: Path | None, *, started_ns: int,
                        audit: dict | None = None) -> dict:
    """Gate before reading outcome bytes. Reuse P3 validation; never infer DEV rights."""
    if any(p is None for p in (scope_path, allowlist_path, panel_path, features_path, registration_path)):
        raise ValueError("PREEXISTING_OWNER_V2_PRIVATE_ATTESTATION_AND_DERIVED_P1_ALLOWLIST_REQUIRED")
    for path in (scope_path, allowlist_path, panel_path, features_path, registration_path):
        _preexisting(path, started_ns)
    scope = validate_scope(scope_path, started_ns=started_ns)
    if scope["schema"] != "exposed_dev_bridge.owner-scope.v2":
        raise ValueError("OWNER_SCOPE_V2_REQUIRED")
    _private_dates_confirmed(scope)
    # Explicit Owner binding avoids treating authorization for the old P1
    # hypothesis/controls as implicit approval for a new B-line experiment.
    document = data.read_json(scope_path)
    binding = document.get("bline_r1_binding", {})
    if (binding.get("task") != TASK or binding.get("decision") != "AUTHORIZE_FIXED_CANDIDATE_EVALUATION"
            or binding.get("feature_panel_path") != str(features_path)
            or binding.get("feature_panel_sha256") != sha(features_path)
            or binding.get("registration_sha256") != sha(registration_path)
            or registration_path.read_bytes() != canonical(registration())):
        raise ValueError("OWNER_BLINE_FEATURE_AND_REGISTRATION_BINDING_REQUIRED")
    p1_binding = document.get("p1_binding", {})
    allowlist = data.read_json(allowlist_path)
    if (p1_binding.get("mode") != "DERIVED_P1_INTEGRITY_V1"
            or p1_binding.get("panel_path") != str(panel_path)
            or p1_binding.get("allowlist_path") != str(allowlist_path)
            or allowlist.get("owner_scope_sha256") != scope["scope_sha256"]
            or allowlist.get("binding_kind") != "DERIVED_INTEGRITY_NOT_OWNER_AUTHORIZATION"
            or allowlist.get("test_only") or allowlist.get("data_kind") == "TEST_ONLY_SYNTHETIC"):
        raise ValueError("VALID_DERIVED_P1_INTEGRITY_REQUIRED")
    start, end = p1_binding["start_utc_s"], p1_binding["end_utc_s"]
    if excluded(start, end):
        raise ValueError("PROTECTED_DATE_OVERLAP")
    if not any(a <= start*1_000_000 < end*1_000_000 <= b
               for a, b in scope["origin_ranges_utc_us_half_open"]):
        raise ValueError("OUTSIDE_OWNER_SCOPE")
    # Only now may P1 open real outcome panel bytes and validate its SHA/window.
    audit = {} if audit is None else audit
    audit["real_outcome_panel_open_attempted"] = True
    outcome_rows, parsed_start, integrity = p1.authorized_panel(panel_path, allowlist_path)
    audit["outcome_origins_parsed"] = len(outcome_rows)
    if parsed_start != start or start+len(outcome_rows)*3600 != end:
        raise ValueError("OWNER_P1_INTERVAL_MISMATCH")
    feature_rows = [json.loads(line) for line in features_path.read_text().splitlines() if line]
    selected = [r for r in feature_rows if r.get("venue") == "binance" and r.get("asset") == "BTC"
                and start <= r["t"] < end]
    if len(selected) != len(outcome_rows):
        raise ValueError("FEATURE_OUTCOME_PAIRING_MISMATCH")
    rows = []
    for feature, outcome in zip(selected, outcome_rows):
        if (feature["t"] != outcome["t"] or feature.get("x_names") != X_NAMES
                or feature.get("schema") != "bline-r1.features.v1"):
            raise ValueError("FEATURE_OUTCOME_PAIRING_MISMATCH")
        if feature["t"]-60-86400-120 < start:
            feature.update(x=None, x_complete=False)
        rows.append({**feature, "outcomes": outcome["outcomes"]})
    from .evaluation import candidate_economics
    audit["real_evaluation_attempted"] = True
    evaluation = p1.evaluate(matched_population(rows), start)
    audit["real_historical_outcomes_evaluated"] = len(rows)
    # Detect changes in authority/input during evaluation.
    if sha(scope_path) != scope["scope_sha256"]:
        raise ValueError("OWNER_SCOPE_CHANGED")
    if (binding["feature_panel_sha256"] != sha(features_path)
            or integrity["allowlist_sha256"] != sha(allowlist_path)
            or integrity["panel_sha256"] != sha(panel_path)
            or binding["registration_sha256"] != sha(registration_path)):
        raise ValueError("FEATURE_PANEL_CHANGED")
    return {"status": "EXPOSED_DEV_ONLY", "alpha": "NO_ALPHA_ESTABLISHED",
            "p1_status": evaluation["status"], "folds": evaluation["folds"],
            "candidate_cells": candidate_economics(rows, start), "integrity": integrity,
            "real_historical_outcomes_evaluated": len(rows), "source_admission": "SOURCE_NOT_ADMITTED"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["feature-coverage", "preregister", "synthetic-p1", "evaluate-authorized"])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--lake-root", type=Path, default=DEFAULT_LAKE)
    parser.add_argument("--start", default="2021-01-01T00:00:00Z")
    parser.add_argument("--end", default="2026-10-01T00:00:00Z")
    for name in ("scope", "allowlist", "panel", "features", "registration"):
        parser.add_argument("--"+name, type=Path)
    args = parser.parse_args(argv)
    began, started_ns = time.monotonic(), time.time_ns()
    output = output_directory(args.output_dir)
    exit_code = 0
    if args.action == "preregister":
        result = registration()
        write_json(output, "preregistered_candidates.json", result)
        write_json(output, "prior_mechanism_failure_map.json", prior_map(REPO))
    elif args.action == "feature-coverage":
        start = datetime.fromtimestamp(epoch(args.start), UTC)
        end = datetime.fromtimestamp(epoch(args.end), UTC)
        if start.day != 1 or start.hour or start.minute or start.second or end.day != 1 or end.hour or end.minute or end.second or end <= start:
            raise ValueError("MONTH_ALIGNED_BOUNDS_REQUIRED")
        lake = Lake(data.safe_directory(args.lake_root))
        full = coverage(lake, output, start, end)
        write_json(output, "feature_coverage_matrix.json", full["matrix"])
        with (output/"feature_coverage_matrix.csv").open("x", newline="") as stream:
            fields = [k for k, v in full["matrix"][0].items() if not isinstance(v, dict)]
            writer = csv.DictWriter(stream, fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(full["matrix"])
        write_json(output, "real_feature_examples.json", full["examples"])
        write_json(output, "source_lineage.json", full["lineage"])
        write_json(output, "source_integrity.json", full["integrity"])
        result = {"status": "FEATURE_ONLY_COMPLETE", "counts": full["counts"],
                  "real_outcome_labels_read": 0, "real_historical_outcomes_evaluated": 0}
    elif args.action == "synthetic-p1":
        from .evaluation import run_synthetic
        result = run_synthetic(output)
        write_json(output, "synthetic_p1_summary.json", result)
        exit_code = int(result["status"] != "PASS")
    else:
        audit = {}
        try:
            result = evaluate_authorized(args.scope, args.allowlist, args.panel, args.features,
                                         args.registration, started_ns=started_ns, audit=audit)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            result = {"status": "EVAL_BLOCKED_SCOPE_UNRESOLVED", "blocker": str(exc),
                      "real_outcome_labels_read": (audit.get("outcome_origins_parsed", "UNKNOWN")
                          if audit.get("real_outcome_panel_open_attempted") else 0),
                      "real_historical_outcomes_evaluated": audit.get(
                          "real_historical_outcomes_evaluated",
                          "UNKNOWN" if audit.get("real_evaluation_attempted") else 0), "audit": audit}
            exit_code = 2
        write_json(output, "authorization_gate.json", result)
    files = {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except ImportError:
        rss = None
    receipt = {"task": TASK, "action": args.action, "status": result.get("status", result.get("state")),
               "labels": LABELS, "argv": sys.argv[1:] if argv is None else argv,
               "artifacts_sha256": files, "elapsed_s": round(time.monotonic()-began, 3),
               "max_rss_linux_kib": rss,
               "implementation_sha256": {str(p.relative_to(REPO)): sha(p)
                   for p in sorted(Path(__file__).parent.glob("*.py"))}}
    write_json(output, "run_receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("task", "action", "status", "elapsed_s", "max_rss_linux_kib")}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
