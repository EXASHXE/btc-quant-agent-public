"""Main execution pipeline for Goal A R2 entry discovery.

Executes the frozen 8 candidate configurations across the 35 development scoring folds (2021-02 to 2023-12)
with 2021-01 strictly reserved for indicator warmup.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from typing import Any

import numpy as np

from .account import replay_account
from .audit import audit_trade_decimal
from .book import BASE, STRESS
from .signals import generate_candidate_signals
from .sources import EP, ROOT, get_monthly_folds, load
from .statistics import block_bootstrap_max_t, compute_trade_metrics

START_SHA = "55ac4c631c69f6edbd275462ad23e4486b9782ed"


def verify_freeze_parent(sha: str) -> None:
    """Ensure freeze commit parent matches exact authorized start SHA."""
    parent = subprocess.check_output(["git", "rev-parse", f"{sha}^"], cwd=ROOT, text=True).strip()
    if parent != START_SHA:
        raise ValueError(f"Freeze parent {parent} does not match exact authorized start {START_SHA}")


def run_all(
    cost_tier: str = "STRESS",
    extra_pressure_bps: float = 0.0,
) -> dict[str, Any]:
    """Execute complete development replay across 35 scoring folds."""
    start_time = time.time()
    registry_file = EP / "GOAL_A_FROZEN_CANDIDATE_REGISTRY.json"
    registry = json.loads(registry_file.read_text())
    candidates = registry["CANDIDATES"]

    cost = dict(STRESS if cost_tier == "STRESS" else BASE)
    if extra_pressure_bps > 0:
        cost["fee_bps"] = cost.get("fee_bps", 0.0) + extra_pressure_bps

    arrays, rates, receipt = load()
    folds = get_monthly_folds()

    # Pre-aggregate concatenated continuous 1m last and mark data
    # To ensure zero boundary artifacts and full multi-month warmup
    all_months = [(f["year"], f["month"]) for f in folds]
    # Include 2021-01 warmup month
    sorted_months = [(2021, 1)] + all_months

    last_list = [arrays["last"][y, m] for (y, m) in sorted_months]
    mark_list = [arrays["mark"][y, m] for (y, m) in sorted_months]
    full_last = np.vstack(last_list)
    full_mark = np.vstack(mark_list)

    all_rates = []
    for y, m in sorted_months:
        all_rates.extend(rates[y, m])
    all_rates.sort(key=lambda r: int(r["settlement_at"]))

    results = {}
    candidate_trades_map = {}

    for cand in candidates:
        cid = cand["id"]
        cand_trades = []
        monthly_account_records = []
        cand_signals_all = []

        # Run month by month preserving single-position cash state
        current_cash = 1000.0

        for fold in folds:
            # Generate signals for this candidate within the fold embargo
            fold_signals = generate_candidate_signals(full_last, cand, fold)
            cand_signals_all.extend(fold_signals)

            acct = replay_account(
                full_last,
                full_mark,
                all_rates,
                fold_signals,
                cand,
                fold,
                cost,
                cash0=current_cash,
            )
            cand_trades.extend(acct["trades"])
            current_cash = acct["ending_equity"]

            monthly_account_records.append({
                "year": fold["year"],
                "month": fold["month"],
                "n_trades": len(acct["trades"]),
                "ending_equity": acct["ending_equity"],
                "min_mark_equity": acct["min_mark_equity"],
                "max_mtm_drawdown_pct": acct["max_mtm_drawdown_pct"],
                "occupancy_fraction": acct["occupancy_fraction"],
                "fates": acct["fates"],
            })

        metrics_3y = compute_trade_metrics(cand_trades, cash0=1000.0)

        # Annual breakdowns
        annual_metrics = {}
        for yr in (2021, 2022, 2023):
            yr_trades = [
                t for t in cand_trades
                if time.gmtime(t["entry_at"] / 1000).tm_year == yr
            ]
            annual_metrics[str(yr)] = compute_trade_metrics(yr_trades, cash0=1000.0)

        candidate_trades_map[cid] = cand_trades

        results[cid] = {
            "candidate_id": cid,
            "family": cand["family"],
            "horizon_hours": cand["horizon_hours"],
            "metrics_3y": metrics_3y,
            "annual_metrics": annual_metrics,
            "final_equity": current_cash,
            "total_signals_generated": len(cand_signals_all),
            "total_trades_filled": len(cand_trades),
            "monthly_records": monthly_account_records,
        }

    # Block bootstrap simultaneous maxT across all 8 configurations
    bootstrap_7d = block_bootstrap_max_t(
        candidate_trades_map,
        start_ms=folds[0]["start_ms"],
        end_ms=folds[-1]["end_ms"],
        block_days=7,
        n_draws=10_000,
        seed=42,
    )
    bootstrap_14d = block_bootstrap_max_t(
        candidate_trades_map,
        start_ms=folds[0]["start_ms"],
        end_ms=folds[-1]["end_ms"],
        block_days=14,
        n_draws=10_000,
        seed=42,
    )

    # Perform independent Decimal audit on real executed trades
    audit_receipts = []
    all_executed = [t for trs in candidate_trades_map.values() for t in trs]
    if all_executed:
        sample_size = min(len(all_executed), 12)
        indices = np.linspace(0, len(all_executed) - 1, sample_size, dtype=int)
        for idx in indices:
            audit_receipts.append(audit_trade_decimal(all_executed[idx], cost))

    elapsed = time.time() - start_time

    return {
        "cost_tier": cost_tier,
        "cost_spec": cost,
        "extra_pressure_bps": extra_pressure_bps,
        "elapsed_seconds": elapsed,
        "source_receipt": receipt,
        "candidates": results,
        "bootstrap_7d": bootstrap_7d,
        "bootstrap_14d": bootstrap_14d,
        "decimal_audit": audit_receipts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Goal A R2 Entry Discovery Runner")
    parser.add_argument("--tier", choices=["BASE", "STRESS"], default="STRESS")
    parser.add_argument("--pressure", type=float, default=0.0)
    args = parser.parse_args()

    res = run_all(cost_tier=args.tier, extra_pressure_bps=args.pressure)
    out_file = EP / f"GOAL_A_RUN_{args.tier}.json"
    out_file.write_text(json.dumps(res, indent=2, default=str))
    print(f"Goal A run completed in {res['elapsed_seconds']:.2f}s. Results written to {out_file}")


if __name__ == "__main__":
    main()
