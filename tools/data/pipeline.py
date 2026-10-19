"""V065-DATA-R2 Multi-Exchange Data Acquisition Pipeline Orchestrator.

Orchestrates Binance USD-M and OKX USDT-SWAP historical data acquisition,
verifying and indexing BTC/ETH base series (2026-07..2026-09) plus L2/tick flow controls.
Enforces hard batch budgets:
- <= 4 GiB newly compressed
- <= 16 GiB newly expanded
- <= 2000 total requests
- >= 100 GiB free disk space
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tools.data.binance_usdm import run_binance_expansion
from tools.data.common import (
    DEFAULT_COMPRESSED_CAP,
    DEFAULT_EXPANDED_CAP,
    DEFAULT_REQUEST_CAP,
    Budget,
    BudgetExceededError,
)
from tools.data.okx_swap import run_okx_expansion

DEFAULT_DATA_ROOT = Path("/root/workspace/project/crypto-data/historical")


def run_pipeline(
    data_root: Path = DEFAULT_DATA_ROOT,
    venue: str = "all",
    action: str = "acquire",
    start_date: str | None = None,
    end_date: str | None = None,
    tranche_id: str | None = None,
    compressed_cap: int = DEFAULT_COMPRESSED_CAP,
    expanded_cap: int = DEFAULT_EXPANDED_CAP,
    request_cap: int = DEFAULT_REQUEST_CAP,
) -> dict[str, Any]:
    """Execute data acquisition across selected venues."""
    data_root.mkdir(parents=True, exist_ok=True)
    budget = Budget(
        compressed_cap=compressed_cap,
        expanded_cap=expanded_cap,
        request_cap=request_cap,
        workspace=data_root,
    )
    budget.check_disk()

    if tranche_id:
        binance_dir = data_root / f"binance-usdm-{tranche_id}"
        okx_dir = data_root / f"okx-swap-{tranche_id}"
        summary_file = data_root / f"V065_DATA_{tranche_id.upper()}_EXPANSION_SUMMARY.json"
        pipeline_task = f"V065-DATA-R3_Agy_Cross_Exchange_{tranche_id.upper()}"
        tranche_label = f"{start_date} through {end_date} exclusive"
    else:
        binance_dir = data_root / "binance-usdm-expansion"
        okx_dir = data_root / "okx-swap-expansion"
        summary_file = data_root / "V065_DATA_R2_EXPANSION_SUMMARY.json"
        pipeline_task = "V065-DATA-R2_Agy_Cross_Exchange_Data_Acquisition"
        tranche_label = "2026-07-01 through 2026-10-01 exclusive (base series Q3 2026)"

    results: dict[str, Any] = {
        "pipeline_task": pipeline_task,
        "action": action,
        "venue": venue,
        "tranche_id": tranche_id,
        "start_date": start_date,
        "end_date": end_date,
        "tranche": tranche_label,
        "venues_executed": {},
    }

    try:
        if venue in ("binance", "all"):
            print("=== Executing Binance USD-M Expansion ===")
            binance_res = run_binance_expansion(
                binance_dir,
                budget,
                action=action,
                start_date=start_date,
                end_date=end_date,
                tranche_id=tranche_id,
            )
            results["venues_executed"]["binance"] = {
                "terminal": binance_res["terminal"],
                "inventory": binance_res["inventory"],
                "manifest_path": str(binance_dir / "manifest.json"),
                "coverage_path": str(binance_dir / "coverage.json"),
                "qc_path": str(binance_dir / "qc.json"),
            }

        if venue in ("okx", "all"):
            print("=== Executing OKX USDT-SWAP Expansion ===")
            okx_res = run_okx_expansion(
                okx_dir,
                budget,
                action=action,
                start_date=start_date,
                end_date=end_date,
                tranche_id=tranche_id,
            )
            results["venues_executed"]["okx"] = {
                "terminal": okx_res["terminal"],
                "inventory": okx_res["inventory"],
                "manifest_path": str(okx_dir / "manifest.json"),
                "coverage_path": str(okx_dir / "coverage.json"),
                "qc_path": str(okx_dir / "qc.json"),
            }

        # Check terminals
        terminals = [v["terminal"] for v in results["venues_executed"].values()]
        if all(t == "DATA_TRANCHE_VERIFIED" for t in terminals):
            overall_terminal = "DATA_TRANCHE_VERIFIED"
        else:
            overall_terminal = "DATA_PARTIAL_WITH_NEXT_BATCH"

    except BudgetExceededError as e:
        overall_terminal = "STOP_BUDGET"
        results["budget_error"] = str(e)
    except Exception as e:  # noqa: BLE001
        overall_terminal = "DATA_PARTIAL_WITH_NEXT_BATCH"
        results["execution_error"] = f"{type(e).__name__}: {e}"

    results["terminal"] = overall_terminal
    results["disk_measurement"] = budget.check_disk()
    results["budget_usage"] = {
        "compressed_bytes_consumed": budget.compressed_bytes,
        "expanded_bytes_consumed": budget.expanded_bytes,
        "requests_made": budget.requests_made,
        "compressed_cap": budget.compressed_cap,
        "expanded_cap": budget.expanded_cap,
        "request_cap": budget.request_cap,
    }

    with summary_file.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, sort_keys=True)
        f.write("\n")
    results["summary_file"] = str(summary_file)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="V065-DATA-R2/R3 Data Acquisition Pipeline")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT, help="Base data root directory")
    parser.add_argument("--venue", choices=("binance", "okx", "all"), default="all", help="Target venue")
    parser.add_argument("--action", choices=("acquire", "verify"), default="acquire", help="Pipeline action")
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD, inclusive)")
    parser.add_argument("--end-date", type=str, default=None, help="End date (YYYY-MM-DD, exclusive)")
    parser.add_argument("--tranche-id", type=str, default=None, help="Tranche ID (e.g. 2026q2)")
    parser.add_argument("--compressed-cap", type=int, default=DEFAULT_COMPRESSED_CAP, help="Compressed cap bytes")
    parser.add_argument("--expanded-cap", type=int, default=DEFAULT_EXPANDED_CAP, help="Expanded cap bytes")
    parser.add_argument("--request-cap", type=int, default=DEFAULT_REQUEST_CAP, help="Request cap count")
    parser.add_argument("--owner-authorized", action="store_true", required=True, help="Explicit Owner Authorization")
    args = parser.parse_args()

    res = run_pipeline(
        data_root=args.data_root,
        venue=args.venue,
        action=args.action,
        start_date=args.start_date,
        end_date=args.end_date,
        tranche_id=args.tranche_id,
        compressed_cap=args.compressed_cap,
        expanded_cap=args.expanded_cap,
        request_cap=args.request_cap,
    )
    print("\n--- Execution Summary ---")
    print(json.dumps(res, indent=2))
    return 0 if res["terminal"] == "DATA_TRANCHE_VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main())
