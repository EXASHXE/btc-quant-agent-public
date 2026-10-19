"""CLI interface for B-line R3 2022 native position gap investigation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .contracts import TASK, TERMINAL_DECISION
from .reconcile import (
    DEFAULT_CATALOG_PATH,
    DEFAULT_CHECKSUM_DIR,
    DEFAULT_OUTPUT_DIR,
    compare_reference_slices,
    generate_all_reports,
    reconcile_year_2022,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Forensic investigation CLI for 2022 Binance native position ratio coverage."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: run
    run_parser = subparsers.add_parser("run", help="Run full reconciliation and generate deliverables.")
    run_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Target output directory for research deliverables.",
    )

    # Subcommand: audit
    audit_parser = subparsers.add_parser("audit", help="Audit 2022 coverage and print summary table.")
    audit_parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="Path to deduplicated catalog sqlite.",
    )
    audit_parser.add_argument(
        "--checksums",
        type=Path,
        default=DEFAULT_CHECKSUM_DIR,
        help="Path to checksums directory.",
    )

    # Subcommand: slices
    slices_parser = subparsers.add_parser(
        "slices", help="Compare 2021/2022/2023 reference slices for schema shifts."
    )
    slices_parser.add_argument(
        "--catalog",
        type=Path,
        default=DEFAULT_CATALOG_PATH,
        help="Path to deduplicated catalog sqlite.",
    )

    args = parser.parse_args()

    if args.command == "run":
        print(f"[{TASK}] Generating all reports in: {args.output}")
        manifest = generate_all_reports(args.output)
        print("Generated deliverables with SHA256:")
        for name, digest in manifest.items():
            print(f"  {name}: {digest}")
        print(f"\nTerminal Decision: {TERMINAL_DECISION}")
        return 0

    elif args.command == "audit":
        print(f"[{TASK}] Auditing 2022 archives...")
        rec = reconcile_year_2022(args.catalog, args.checksums)
        summary = rec["year_2022_summary"]
        print("\n=== 2022 YEAR SUMMARY ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")

        print("\n=== MONTHLY BREAKDOWN ===")
        print(f"{'Month':<8} | {'Hours':<6} | {'Native OI':<10} | {'Pos Ratio Present':<18} | {'Pos Ratio Missing':<18}")
        print("-" * 75)
        for m, s in sorted(rec["monthly_origin_counts"].items()):
            print(f"{m:<8} | {s['scheduled_hours']:<6} | {s['native_oi_present']:<10} | {s['native_ratio_present']:<18} | {s['native_ratio_missing']:<18}")

        print("\n=== GAP CLASSIFICATION ===")
        for k, v in rec["gap_classifications"].items():
            print(f"  {k}: {v}")

        sim = rec["simulated_coverage_upper_bound"]
        print("\n=== SIMULATED COVERAGE UPPER BOUND ===")
        print(f"  Label: {sim['label']}")
        print(f"  Simulated origins: {sim['simulated_eligible_hourly_origins']}")
        print(f"  Counterfactual additional: {sim['counterfactual_additional_origins']}")
        print(f"\nTerminal Decision: {rec['terminal_decision']}")
        return 0

    elif args.command == "slices":
        print(f"[{TASK}] Comparing reference slices...")
        slices = compare_reference_slices(args.catalog)
        print(f"{'Period':<12} | {'Year':<6} | {'Header Match':<12} | {'Pos Present':<12} | {'Pos Blank':<10}")
        print("-" * 65)
        for s in slices:
            print(f"{s['period']:<12} | {s['year']:<6} | {s['header_exact_match']!s:<12} | {s['pos_ratio_present_rows']:<12} | {s['pos_ratio_blank_rows']:<10}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
