"""Run H39 blind forward validation operations and generate v0.3.24 deliverables."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from btc_quant_agent.microstructure_research import (
    H39_BLIND_LEDGER_DEFAULT_PATH,
    H39BlindLedger,
    H39ResearchEngine,
    generate_all_v0324_deliverables,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Operate H39 Blind Validation pipeline (scheduled accumulation, integrity, backup, deliverables)"
    )
    parser.add_argument(
        "--output-dir",
        default="deliverables/v0.3.24",
        help="Directory to write deliverables",
    )
    parser.add_argument(
        "--microstructure-root",
        default="data/forward/BTCUSDT/microstructure",
        help="Root path of forward microstructure SQLite partitions",
    )
    parser.add_argument(
        "--opportunity-store",
        default="data/forward/BTCUSDT/opportunity_shadow.sqlite3",
        help="Path to opportunity_shadow SQLite database",
    )
    parser.add_argument(
        "--ledger-path",
        default=H39_BLIND_LEDGER_DEFAULT_PATH,
        help="Path to blind validation ledger SQLite database",
    )
    parser.add_argument(
        "--backup-dir",
        default="data/research/h39_validation/backups",
        help="Directory to store ledger backups",
    )
    parser.add_argument(
        "--only-finalized",
        action="store_true",
        default=True,
        help="Only ingest finalized partitions prior to today UTC",
    )
    parser.add_argument(
        "--include-active",
        action="store_true",
        default=False,
        help="Include active today partition in accumulation",
    )
    parser.add_argument(
        "--min-free-gb",
        type=float,
        default=5.0,
        help="Minimum required filesystem free space in GB",
    )
    parser.add_argument(
        "--scheduled-accumulate",
        action="store_true",
        help="Run full scheduled accumulation workflow (disk check, integrity, accumulate, backup)",
    )
    parser.add_argument(
        "--verify-integrity",
        action="store_true",
        help="Run SQLite integrity check and verify partition hash immutability",
    )
    parser.add_argument(
        "--backup-only",
        action="store_true",
        help="Create a consistent online SQLite backup of the ledger",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Show current blind validation accumulation status and metrics",
    )
    parser.add_argument(
        "--readiness-only",
        action="store_true",
        help="Check readiness for one-shot unblind",
    )
    args = parser.parse_args()

    engine = H39ResearchEngine(
        microstructure_root=args.microstructure_root,
        opportunity_store_path=args.opportunity_store,
    )
    ledger = H39BlindLedger(args.ledger_path)

    if args.status_only:
        status = engine.get_blind_validation_status(ledger_path=args.ledger_path)
        print(json.dumps(status, indent=2))
        return 0

    if args.readiness_only:
        readiness = engine.check_unblind_readiness(ledger_path=args.ledger_path)
        print(json.dumps(readiness, indent=2))
        return 0 if readiness.get("ready_for_unblind") else 1

    if args.verify_integrity:
        print(f"[H39 Operations] Verifying integrity of ledger: {args.ledger_path}")
        integ = ledger.verify_integrity()
        print(json.dumps(integ, indent=2))
        return 0 if integ.get("status") == "OK" else 1

    if args.backup_only:
        print(f"[H39 Operations] Creating online backup in: {args.backup_dir}")
        bak_file = ledger.backup_ledger(destination_dir=args.backup_dir)
        print(f"[H39 Operations] Backup successfully created: {bak_file}")
        return 0

    if args.scheduled_accumulate:
        only_fin = not args.include_active if args.include_active else args.only_finalized
        print(f"[H39 Operations] Running scheduled accumulation (only_finalized={only_fin})...")
        res = engine.run_scheduled_accumulation(
            output_ledger_path=args.ledger_path,
            backup_dir=args.backup_dir,
            min_free_gb=args.min_free_gb,
            only_finalized=only_fin,
        )
        print(json.dumps(res, indent=2))
        return 0

    print(f"[H39 Operations] Generating v0.3.24 deliverables in: {args.output_dir}")
    deliverables = generate_all_v0324_deliverables(
        output_dir=args.output_dir,
        microstructure_root=args.microstructure_root,
        opportunity_store_path=args.opportunity_store,
        ledger_path=args.ledger_path,
        backup_dir=args.backup_dir,
    )

    print("[H39 Operations] Generated deliverables:")
    for name, path in deliverables.items():
        print(f"  - {name}: {path}")

    status_path = Path(deliverables["H39_BLIND_OPERATIONAL_STATUS"])
    if status_path.exists():
        status_data = json.loads(status_path.read_text(encoding="utf-8"))
        print(f"\n[H39 Operational Status] State: {status_data.get('state')}")
        denom = status_data.get("clock_denominator", {})
        print(
            f"  Distinct days: {status_data.get('distinct_days_count')}/"
            f"{status_data.get('maturity_gates', {}).get('minimum_distinct_days')}"
        )
        print(
            f"  Eligible slots: {denom.get('eligible_boundary_count')}/"
            f"{status_data.get('maturity_gates', {}).get('minimum_eligible_observations')}"
        )
        print(f"  Eligible coverage ratio: {denom.get('eligible_coverage', 0.0):.2%}")
        print(f"  Raw observation coverage: {denom.get('raw_observation_coverage', 0.0):.2%}")
        print(f"  Maturity achieved: {status_data.get('maturity_achieved')}")

    print("\n[H39 Operations] Run completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

