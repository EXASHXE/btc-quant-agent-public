"""Command-line interface for P2 metadata-only root locator and coverage auditor."""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from scripts.strategy_research.p2_metadata_locator.config import (
    CODE_START_SHA,
    CONTROLLER_DISPATCH_BLOB,
    CONTROLLER_DISPATCH_SHA,
    DEFAULT_CANDIDATE_ROOTS,
    PROMPT_PINNED_BLOB,
    PROMPT_PINNED_SHA,
    REMOTE_BRANCH,
    TASK_ID,
)
from scripts.strategy_research.p2_metadata_locator.matrix import generate_coverage_matrix
from scripts.strategy_research.p2_metadata_locator.scanner import MetadataScanner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="P2 bounded metadata root locator and source readiness reconnaissance."
    )
    parser.add_argument(
        "--approved-root",
        type=str,
        default=None,
        help="Optional explicit local root path provided by owner for verification.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery plan without writing final persistent evidence.",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=None,
        help="Output path for P2_METADATA_ROOT_AND_COVERAGE.json.",
    )
    parser.add_argument(
        "--receipt-out",
        type=str,
        default=None,
        help="Output path for P2_SCAN_BUDGET_AND_TEST_RECEIPT.json.",
    )
    parser.add_argument(
        "--matrix-out",
        type=str,
        default=None,
        help="Output path for P2_SCOPED_PATH_AND_PROTECTION_MATRIX.json.",
    )
    return parser


def run_locator(args: argparse.Namespace) -> int:
    candidate_roots = list(DEFAULT_CANDIDATE_ROOTS)
    if args.approved_root:
        # Prepend explicit owner approved root
        candidate_roots.insert(0, os.path.abspath(args.approved_root))

    scanner = MetadataScanner(candidate_roots=candidate_roots)
    receipt = scanner.run()
    matrix = generate_coverage_matrix(receipt)

    print("=" * 80)
    print(f"TASK_ID: {TASK_ID}")
    print(f"TERMINAL_VERDICT: {receipt.terminal_verdict.value}")
    print(f"CONFIRMED_ROOT: {receipt.confirmed_root or 'NONE (UNKNOWN)'}")
    print(f"BUDGET_EXHAUSTED: {receipt.budget_exhausted}")
    print(f"DURATION: {receipt.duration_seconds}s")
    print(f"DIR_ENTRIES_SCANNED: {receipt.counters.dir_entries_scanned}")
    print(f"LSTAT_CALLS: {receipt.counters.lstat_calls}")
    print(f"SELECTED_PARTITION_LSTATS: {receipt.counters.selected_partition_lstat_calls}")
    print(f"SYMLINKS_FOLLOWED: {receipt.counters.symlinks_followed}")
    print(f"REAL_DATA_BODY_BYTES_READ: {receipt.counters.real_data_body_bytes_read}")
    print(f"PROTECTED_ACCESSES: {receipt.counters.protected_body_or_partition_accesses}")
    print(f"ONE_OWNER_REQUEST: {receipt.one_owner_request}")
    print("=" * 80)

    coverage_payload = {
        "schema_version": "P2_METADATA_ROOT_AND_COVERAGE_V1",
        "task_id": TASK_ID,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "controller_dispatch_blob": CONTROLLER_DISPATCH_BLOB,
        "prompt_pinned_sha": PROMPT_PINNED_SHA,
        "prompt_pinned_blob": PROMPT_PINNED_BLOB,
        "code_start_sha": CODE_START_SHA,
        "remote_branch": REMOTE_BRANCH,
        "terminal_verdict": receipt.terminal_verdict.value,
        "confirmed_root": receipt.confirmed_root,
        "one_owner_request": receipt.one_owner_request,
        "feasibility": matrix.feasibility.to_dict(),
        "btc_safe_months_summary": [
            {
                "candidate_root": ev.candidate_root,
                "certainty": ev.certainty.value,
                "partitions": {k: v.to_dict() for k, v in ev.safe_partitions_checked.items()},
            }
            for ev in receipt.evaluated_roots
        ],
        "no_body_counters": {
            "parquet_opens": 0,
            "csv_opens": 0,
            "zip_opens": 0,
            "market_file_hashes": 0,
            "market_decodings": 0,
            "real_data_body_bytes_read": receipt.counters.real_data_body_bytes_read,
            "protected_body_or_partition_accesses": receipt.counters.protected_body_or_partition_accesses,
            "symlink_follows": receipt.counters.symlinks_followed,
            "remote_market_calls": receipt.counters.remote_market_calls,
        },
    }

    receipt_payload = {
        "schema_version": "P2_SCAN_BUDGET_AND_TEST_RECEIPT_V1",
        **receipt.to_dict(),
    }

    matrix_payload = {
        "schema_version": "P2_SCOPED_PATH_AND_PROTECTION_MATRIX_V1",
        **matrix.to_dict(),
    }

    if not args.dry_run:
        if args.json_out:
            os.makedirs(os.path.dirname(os.path.abspath(args.json_out)), exist_ok=True)
            with open(args.json_out, "w", encoding="utf-8") as f:
                json.dump(coverage_payload, f, indent=2, sort_keys=True)
            print(f"Wrote coverage to: {args.json_out}")

        if args.receipt_out:
            os.makedirs(os.path.dirname(os.path.abspath(args.receipt_out)), exist_ok=True)
            with open(args.receipt_out, "w", encoding="utf-8") as f:
                json.dump(receipt_payload, f, indent=2, sort_keys=True)
            print(f"Wrote receipt to: {args.receipt_out}")

        if args.matrix_out:
            os.makedirs(os.path.dirname(os.path.abspath(args.matrix_out)), exist_ok=True)
            with open(args.matrix_out, "w", encoding="utf-8") as f:
                json.dump(matrix_payload, f, indent=2, sort_keys=True)
            print(f"Wrote protection matrix to: {args.matrix_out}")

    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(run_locator(args))


if __name__ == "__main__":
    main()
