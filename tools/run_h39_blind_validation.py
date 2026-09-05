"""Run H39 blind forward validation accumulation and generate v0.3.23 deliverables."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from btc_quant_agent.microstructure_research import (
    H39_BLIND_LEDGER_DEFAULT_PATH,
    H39ResearchEngine,
    generate_all_v0323_deliverables,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Accumulate H39 Blind Forward Validation evidence and generate deliverables"
    )
    parser.add_argument(
        "--output-dir",
        default="deliverables/v0.3.23",
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
        "--accumulate-only",
        action="store_true",
        help="Only accumulate evidence into ledger without generating full deliverable set",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Only show current blind validation accumulation status",
    )
    args = parser.parse_args()

    engine = H39ResearchEngine(
        microstructure_root=args.microstructure_root,
        opportunity_store_path=args.opportunity_store,
    )

    if args.status_only:
        status = engine.get_blind_validation_status(ledger_path=args.ledger_path)
        print(json.dumps(status, indent=2))
        return 0

    if args.accumulate_only:
        print(f"[H39 Blind Validation] Accumulating into ledger: {args.ledger_path}")
        accum_res = engine.accumulate_blind_validation(output_ledger_path=args.ledger_path)
        print(
            f"[H39 Blind Validation] Ingested {accum_res['new_slots_ingested']} new slots "
            f"({accum_res['duplicate_slots_skipped']} duplicates skipped)"
        )
        return 0

    print(f"[H39 Blind Validation] Generating v0.3.23 deliverables in: {args.output_dir}")
    deliverables = generate_all_v0323_deliverables(
        output_dir=args.output_dir,
        microstructure_root=args.microstructure_root,
        opportunity_store_path=args.opportunity_store,
        ledger_path=args.ledger_path,
    )

    print("[H39 Blind Validation] Generated deliverables:")
    for name, path in deliverables.items():
        print(f"  - {name}: {path}")

    status_path = Path(deliverables["H39_BLIND_VALIDATION_STATUS"])
    if status_path.exists():
        status_data = json.loads(status_path.read_text(encoding="utf-8"))
        print(f"\n[H39 Validation Status] State: {status_data.get('state')}")
        print(
            f"  Distinct days: {status_data.get('distinct_days_count')}/"
            f"{status_data.get('maturity_gates', {}).get('minimum_distinct_days')}"
        )
        print(
            f"  Eligible slots: {status_data.get('eligible_boundary_count')}/"
            f"{status_data.get('maturity_gates', {}).get('minimum_eligible_observations')}"
        )
        print(f"  Coverage ratio: {status_data.get('coverage_ratio', 0.0):.2%}")
        print(f"  Maturity achieved: {status_data.get('maturity_achieved')}")

    print("\n[H39 Blind Validation] Run completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
