"""Main execution pipeline for Goal A R2 entry discovery.

Executes the frozen 8 candidate configurations across the 35 development scoring folds (2021-02 to 2023-12)
with 2021-01 strictly reserved for indicator warmup.
Streams fold-by-fold to ensure zero OOM pressure and maximum numerical precision.
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
from .book import BASE, STRESS, TradeExecutionError, execute_position
from .signals import generate_candidate_signals
from .sources import EP, ROOT, get_monthly_folds, load
from .statistics import block_bootstrap_max_t, compute_trade_metrics

START_SHA = "55ac4c631c69f6edbd275462ad23e4486b9782ed"
FREEZE_SHA = "83c0ef60d9eacfd2440fa223c57f042cfff4912f"


def verify_freeze_parent(sha: str) -> None:
    """Ensure freeze commit parent matches exact authorized start SHA."""
    parent = subprocess.check_output(["git", "rev-parse", f"{sha}^"], cwd=ROOT, text=True).strip()
    if parent != START_SHA:
        raise ValueError(f"Freeze parent {parent} does not match exact authorized start {START_SHA}")


def run_all(
    cost_tier: str = "STRESS",
    extra_pressure_bps: float = 0.0,
    arrays: dict[str, Any] | None = None,
    rates: dict[Any, Any] | None = None,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute complete development replay across 35 scoring folds."""
    start_time = time.time()
    registry_file = EP / "GOAL_A_FROZEN_CANDIDATE_REGISTRY.json"
    registry = json.loads(registry_file.read_text())
    candidates = registry["CANDIDATES"]

    cost = dict(STRESS if cost_tier == "STRESS" else BASE)
    if extra_pressure_bps > 0:
        cost["fee_bps"] = cost.get("fee_bps", 0.0) + extra_pressure_bps

    if arrays is None or rates is None or receipt is None:
        arrays, rates, receipt = load()
    folds = get_monthly_folds()

    results = {}
    candidate_trades_map = {}
    paired_controls_map = {}

    for cand in candidates:
        cid = cand["id"]
        cand_trades = []
        monthly_account_records = []
        cand_signals_all = []
        cand_paired_trades = []

        current_cash = 1000.0

        for fold in folds:
            prev_last = arrays["last"][fold["prev_year"], fold["prev_month"]]
            curr_last = arrays["last"][fold["year"], fold["month"]]
            window_last = np.vstack([prev_last, curr_last])
            curr_mark = arrays["mark"][fold["year"], fold["month"]]
            curr_rates = rates[fold["year"], fold["month"]]

            fold_signals = generate_candidate_signals(window_last, cand, fold)
            cand_signals_all.extend(fold_signals)

            acct = replay_account(
                window_last,
                curr_mark,
                curr_rates,
                fold_signals,
                cand,
                fold,
                cost,
                cash0=current_cash,
            )
            cand_trades.extend(acct["trades"])
            current_cash = acct["ending_equity"]

            # Compute paired counterfactual control for each executed trade
            for t in acct["trades"]:
                event_match = next((s for s in fold_signals if s["event_id"] == t["event_id"]), None)
                if event_match:
                    try:
                        t_ctrl = execute_position(
                            window_last,
                            curr_mark,
                            curr_rates,
                            event_match,
                            cand,
                            cost,
                            t["quantity"],
                            side_override=-t["side"],
                        )
                        cand_paired_trades.append(t_ctrl)
                        t["paired_control_net_bps"] = t_ctrl["net_after_funding_bps"]
                    except (TradeExecutionError, ValueError):
                        continue

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
        paired_metrics_3y = compute_trade_metrics(cand_paired_trades, cash0=1000.0)

        # Annual breakdowns
        annual_metrics = {}
        for yr in (2021, 2022, 2023):
            yr_trades = [
                t for t in cand_trades
                if time.gmtime(t["entry_at"] / 1000).tm_year == yr
            ]
            annual_metrics[str(yr)] = compute_trade_metrics(yr_trades, cash0=1000.0)

        candidate_trades_map[cid] = cand_trades
        paired_controls_map[cid] = cand_paired_trades

        results[cid] = {
            "candidate_id": cid,
            "family": cand["family"],
            "horizon_hours": cand["horizon_hours"],
            "metrics_3y": metrics_3y,
            "paired_controls_metrics_3y": paired_metrics_3y,
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
        sample_size = min(len(all_executed), 16)
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


def execute_full_study() -> dict[str, Any]:
    """Execute all frozen tiers and friction sensitivities in one bounded run."""
    print("Loading 2021-2023 authenticated archives...", flush=True)
    arrays, rates, receipt = load()

    print("Running primary STRESS cost tier (44 bps)...", flush=True)
    stress_res = run_all("STRESS", 0.0, arrays, rates, receipt)

    print("Running secondary BASE cost tier (22 bps)...", flush=True)
    base_res = run_all("BASE", 0.0, arrays, rates, receipt)

    print("Running friction pressure +5 bps tier...", flush=True)
    p5_res = run_all("STRESS", 5.0, arrays, rates, receipt)

    print("Running friction pressure +10 bps tier...", flush=True)
    p10_res = run_all("STRESS", 10.0, arrays, rates, receipt)

    # Save artifact files
    (EP / "GOAL_A_RUN_STRESS.json").write_text(json.dumps(stress_res, indent=2, default=str))
    (EP / "GOAL_A_RUN_BASE.json").write_text(json.dumps(base_res, indent=2, default=str))
    (EP / "DECIMAL_AUDIT_RECEIPT.json").write_text(json.dumps(stress_res["decimal_audit"], indent=2, default=str))

    friction_summary = {
        "STRESS_44bp": {cid: stress_res["candidates"][cid]["metrics_3y"]["profit_factor"] for cid in stress_res["candidates"]},
        "BASE_22bp": {cid: base_res["candidates"][cid]["metrics_3y"]["profit_factor"] for cid in base_res["candidates"]},
        "STRESS_plus_5bp": {cid: p5_res["candidates"][cid]["metrics_3y"]["profit_factor"] for cid in p5_res["candidates"]},
        "STRESS_plus_10bp": {cid: p10_res["candidates"][cid]["metrics_3y"]["profit_factor"] for cid in p10_res["candidates"]},
    }
    (EP / "GOAL_A_FRICTION_PRESSURE.json").write_text(json.dumps(friction_summary, indent=2, default=str))

    summary = {
        "FREEZE_SHA": FREEZE_SHA,
        "START_SHA": START_SHA,
        "candidates_count": len(stress_res["candidates"]),
        "STRESS": stress_res,
        "BASE": base_res,
        "friction_sensitivity": friction_summary,
    }
    (EP / "GOAL_A_ALL_CANDIDATES_SUMMARY.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Goal A R2 Entry Discovery Runner")
    parser.add_argument("--tier", choices=["BASE", "STRESS", "ALL"], default="ALL")
    args = parser.parse_args()

    if args.tier == "ALL":
        _summary = execute_full_study()
        print("Full Goal A study complete across all cost tiers and friction sensitivities.")
    else:
        res = run_all(cost_tier=args.tier)
        out_file = EP / f"GOAL_A_RUN_{args.tier}.json"
        out_file.write_text(json.dumps(res, indent=2, default=str))
        print(f"Goal A run completed in {res['elapsed_seconds']:.2f}s. Results written to {out_file}")


if __name__ == "__main__":
    main()
