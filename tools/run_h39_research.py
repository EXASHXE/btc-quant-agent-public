#!/usr/bin/env python3
"""Run H39 microstructure alpha research evaluation and generate deliverables."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from btc_quant_agent.microstructure_research import generate_all_v0322_deliverables


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate v0.3.22 H39 Microstructure Alpha deliverables"
    )
    parser.add_argument(
        "--output-dir",
        default="deliverables/v0.3.22",
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
    args = parser.parse_args()

    print(f"[H39 Research] Generating deliverables in: {args.output_dir}")
    deliverables = generate_all_v0322_deliverables(
        output_dir=args.output_dir,
        microstructure_root=args.microstructure_root,
        opportunity_store_path=args.opportunity_store,
    )

    print("[H39 Research] Generated deliverables:")
    for name, path in deliverables.items():
        print(f"  - {name}: {path}")

    # Check development diagnostics status
    dev_path = Path(deliverables["H39_DEVELOPMENT_DIAGNOSTICS"])
    if dev_path.exists():
        dev_data = json.loads(dev_path.read_text(encoding="utf-8"))
        print(f"\n[H39 Development] Status: {dev_data.get('status')}")
        print(f"  Slots: {dev_data.get('eligible_slots')}/{dev_data.get('total_slots')} eligible")
        print(f"  Distinct days: {dev_data.get('distinct_days_count')}")

    val_path = Path(deliverables["H39_VALIDATION_STATUS"])
    if val_path.exists():
        val_data = json.loads(val_path.read_text(encoding="utf-8"))
        print(f"\n[H39 Validation] Status: {val_data.get('status')}")
        prog = val_data.get("accumulation_progress", {})
        print(f"  Accumulated days: {prog.get('distinct_days_accumulated')}/{prog.get('distinct_days_required')}")
        print(f"  Accumulated slots: {prog.get('eligible_slots_accumulated')}/{prog.get('eligible_slots_required')}")

    print("\n[H39 Research] Run completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
