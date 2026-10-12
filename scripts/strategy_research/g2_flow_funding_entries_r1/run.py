"""One-shot empirical runner for G2 Flow-Funding Alpha discovery R1.

Executes exactly 3 candidate identities x 2 horizons (12h, 18h) = 6 configurations
under STRESS 44bp primary and BASE 22bp secondary across 35 folds (2021-02..2023-12).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .account import get_folds, replay_account
from .book import BASE, STRESS, execute_position
from .signals import (
    CANDIDATE_CONFIGS,
    compute_continuous_1h_bars,
    config_identity_sha,
    generate_candidate_signals,
)
from .sources import EP, ROOT, SCRATCH, assemble_continuous_series, load
from .statistics import (
    compute_annual_breakdown,
    compute_block_bootstrap_max_t,
    compute_trade_metrics,
)

EXACT_START_SHA = "55ac4c631c69f6edbd275462ad23e4486b9782ed"
CONTRACT_PATH = EP / "FROZEN_CONTRACT.json"


def verify_freeze_contract() -> dict[str, Any]:
    """Verify that current code exactly matches the frozen contract without modification."""
    if not CONTRACT_PATH.is_file():
        raise FileNotFoundError(f"Missing frozen contract at {CONTRACT_PATH}")

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    # Verify implementation files
    for rel_path, expected_hash in contract["frozen_implementation_sha256"].items():
        actual_path = ROOT / rel_path
        if not actual_path.is_file():
            raise FileNotFoundError(f"Missing implementation file {rel_path}")
        actual_hash = hashlib.sha256(actual_path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"Implementation file {rel_path} modified post-freeze: {actual_hash} != {expected_hash}")

    # Verify candidate identities
    for cand in CANDIDATE_CONFIGS:
        cid = cand["id"]
        expected_cid_hash = contract["candidate_identity_hashes"][cid]
        actual_cid_hash = config_identity_sha(cand)
        if actual_cid_hash != expected_cid_hash:
            raise ValueError(f"Candidate {cid} configuration modified post-freeze")

    return contract


def run_matched_controls(
    last: np.ndarray,
    mark: np.ndarray,
    funding_events: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    candidate: dict[str, Any],
    cost: dict[str, float],
) -> list[dict[str, Any]]:
    """Compute matched counter-trade control on identical events."""
    controls = []
    for t in trades:
        # Reconstruct synthetic event from trade
        event_mock = {
            "event_id": t["event_id"],
            "event_time": t["event_time"],
            "decision_at": t["decision_at"],
            "entry_at": t["entry_at"],
            "decision_close": t["raw_entry"],
            "atr_hour": (abs(t["effective_entry"] - t["stop"]) / float(candidate["stop_mult"])),
            "stop": t["stop"],
            "side": t["side"],
            "target_r": candidate.get("target_r", 2.0),
            "horizon_hours": candidate["horizon_hours"],
        }
        try:
            counter = execute_position(
                last, mark, funding_events, event_mock, candidate, cost, t["quantity"], side_override=-t["side"]
            )
            net_bps_counter = float(counter["net_after_funding_bps"])
            net_bps_orig = float(t["net_after_funding_bps"])
            balanced = 0.5 * (net_bps_orig + net_bps_counter)
            controls.append({
                "event_id": t["event_id"],
                "side_orig": t["side"],
                "net_bps_orig": net_bps_orig,
                "net_bps_counter": net_bps_counter,
                "balanced_net_bps": balanced,
                "caveat": "NONTRADABLE_SAME_EVENT_PAIRED_REFERENCE_NOT_POOLED_CASH",
            })
        except (ValueError, KeyError):
            continue
    return controls


def execute_study(output_dir: Path | None = None) -> dict[str, Any]:
    """Execute the complete one-shot 35-fold research study across 6 configurations."""
    dest = output_dir or SCRATCH
    dest.mkdir(parents=True, exist_ok=True)

    verify_freeze_contract()
    print("Freeze contract verified successfully.", flush=True)

    # Load authenticated sources
    arrays, rates, source_receipt = load()
    print("Sources loaded.", flush=True)

    # Assemble continuous 36-month timeline
    last_1m, mark_1m = assemble_continuous_series(arrays)
    all_funding = [e for k in sorted(rates.keys()) for e in rates[k]]
    print("Continuous 36-month timeline assembled (1,576,800 minutes).", flush=True)

    # Compute continuous 1h bars with causal ATR and indicators
    bars_1h = compute_continuous_1h_bars(last_1m, mark_1m)
    print("Continuous 1h bars computed (26,280 hours). Warmup Jan 2021 preserved without monthly reset.", flush=True)

    folds = get_folds()
    eval_start_ms = folds[0]["start_ms"]  # 2021-02-01 00:00:00 UTC
    eval_end_ms = folds[-1]["end_ms"]    # 2023-12-31 24:00:00 UTC

    results_by_candidate: dict[str, Any] = {}
    trade_series_stress: dict[str, list[dict[str, Any]]] = {}

    for cand in CANDIDATE_CONFIGS:
        cid = cand["id"]
        print(f"Evaluating candidate {cid}...", flush=True)

        # Generate signals
        sigs = generate_candidate_signals(cand, bars_1h, all_funding, last_1m, eval_start_ms)
        print(f"  Signals generated: {len(sigs)}", flush=True)

        cand_results: dict[str, Any] = {
            "config": cand,
            "signals_count": len(sigs),
            "costs": {},
        }

        for cost_label, cost in [("STRESS", STRESS), ("BASE", BASE)]:
            account_run = replay_account(
                last_1m, mark_1m, all_funding, sigs, cand, folds, cost, initial_cash=1000.0
            )

            # Matched counter controls
            controls = run_matched_controls(last_1m, mark_1m, all_funding, account_run["trades"], cand, cost)

            # Performance breakdown
            annual = compute_annual_breakdown(account_run["trades"])
            overall = compute_trade_metrics(account_run["trades"])

            # Fixed-event equal notional metric (1000 notional)
            fixed_event_net_bps = [float(t["net_after_funding_bps"]) for t in account_run["trades"]]
            fixed_event_mean_bps = float(np.mean(fixed_event_net_bps)) if fixed_event_net_bps else 0.0

            cand_results["costs"][cost_label] = {
                "account": {
                    "initial_cash": account_run["initial_cash"],
                    "ending_cash": account_run["ending_cash"],
                    "net_pnl_usdt": account_run["net_pnl_usdt"],
                    "net_return_pct": account_run["net_return_pct"],
                    "fates": account_run["fates"],
                },
                "trade_metrics_overall": overall,
                "annual_breakdown": annual,
                "fixed_event_equal_notional": {
                    "trades_n": len(fixed_event_net_bps),
                    "mean_net_bps": fixed_event_mean_bps,
                    "sum_net_bps": float(np.sum(fixed_event_net_bps)) if fixed_event_net_bps else 0.0,
                },
                "matched_controls_n": len(controls),
                "matched_controls_mean_balanced_bps": (
                    float(np.mean([c["balanced_net_bps"] for c in controls])) if controls else 0.0
                ),
                "trades": account_run["trades"],
                "rejected": account_run["rejected"],
                "fold_summaries": account_run["fold_summaries"],
            }

            if cost_label == "STRESS":
                trade_series_stress[cid] = account_run["trades"]

        results_by_candidate[cid] = cand_results

    # Simultaneous Max-|T| calibrated intervals across all 6 comparisons
    bootstrap_14d = compute_block_bootstrap_max_t(
        trade_series_stress, eval_start_ms, eval_end_ms, block_days=14
    )
    bootstrap_7d = compute_block_bootstrap_max_t(
        trade_series_stress, eval_start_ms, eval_end_ms, block_days=7
    )

    # Evaluate decision criteria and final verdict
    verdicts = {}
    any_positive_lead = False

    for cand in CANDIDATE_CONFIGS:
        cid = cand["id"]
        stress_res = results_by_candidate[cid]["costs"]["STRESS"]
        n_trades = stress_res["trade_metrics_overall"]["n"]
        pnl_2023 = stress_res["annual_breakdown"]["2023"]["total_net_usdt"]
        overall_pf = stress_res["trade_metrics_overall"]["profit_factor"]
        ci_14d = bootstrap_14d["intervals"][cid]

        # Objective gates:
        # 1. Sample viability: >= 30 trades
        pass_n = n_trades >= 30
        # 2. After-cost PF > 1.0
        pass_pf = overall_pf > 1.0
        # 3. 2023 stability: positive after-cost PnL
        pass_2023 = pnl_2023 > 0.0
        # 4. Simultaneous lower bound strictly > 0
        pass_ci = (not ci_14d["spans_zero"]) and (ci_14d["simultaneous_ci_95"][0] > 0)

        eligible = pass_n and pass_pf and pass_2023 and pass_ci
        if eligible:
            any_positive_lead = True

        verdicts[cid] = {
            "n_executed": n_trades,
            "pass_sample_viability_n30": pass_n,
            "overall_profit_factor_stress": overall_pf,
            "pass_pf_gt_1": pass_pf,
            "pnl_2023_stress_usdt": pnl_2023,
            "pass_2023_stability": pass_2023,
            "simultaneous_ci_14d_95": ci_14d["simultaneous_ci_95"],
            "ci_spans_zero": ci_14d["spans_zero"],
            "pass_simultaneous_ci": pass_ci,
            "verdict": (
                "EXPLORATORY_ELIGIBLE_FOR_NEW_INDEPENDENT_DESIGN"
                if eligible
                else "INSUFFICIENT_COST_ADJUSTED_SUPPORT"
            ),
        }

    terminal_decision = (
        "G2_FLOW_FUNDING_NEW_LEADS_DEVELOPMENT_ONLY"
        if any_positive_lead
        else "G2_FLOW_FUNDING_NO_COST_ADJUSTED_SUPPORT"
    )

    final_delivery = {
        "task_id": "V06_G2_GEMINI_A_FLOW_FUNDING_ENTRY_R1",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "terminal_decision": terminal_decision,
        "authoritative_base_sha": EXACT_START_SHA,
        "contract_sha256": hashlib.sha256(CONTRACT_PATH.read_bytes()).hexdigest(),
        "candidates_evaluated_count": 6,
        "verdicts": verdicts,
        "bootstrap_14d": bootstrap_14d,
        "bootstrap_7d": bootstrap_7d,
        "source_receipt": {
            "minutes_total": len(last_1m),
            "hours_total": len(bars_1h["open_time"]),
            "funding_events_total": len(all_funding),
            "source_manifest_sha256": source_receipt["source_manifest_sha256"],
        },
    }

    # Write summary results
    (dest / "FLOW_FUNDING_RESULTS_SUMMARY.json").write_text(
        json.dumps(final_delivery, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "final_delivery": final_delivery,
        "results_by_candidate": results_by_candidate,
        "bootstrap_14d": bootstrap_14d,
        "bootstrap_7d": bootstrap_7d,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run G2 Flow-Funding empirical alpha evaluation")
    parser.add_argument("--out", type=str, default=str(SCRATCH), help="Output directory")
    args = parser.parse_args()
    execute_study(Path(args.out))


if __name__ == "__main__":
    main()
