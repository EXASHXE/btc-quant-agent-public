"""Full execution harness for Wave research: two-pass determinism, audit, and decision reporting."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.audit import audit_candidate_trades
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.metrics import (
    block_bootstrap,
    calculate_candidate_metrics,
    evaluate_promotion_gate,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    STRESS,
    simulate_fold,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.signals import generate_wave_signals
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.sources import (
    get_monthly_folds,
    load_month,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "evidence/v0.6/b_line/g2_gemini_goal_trend_flow_r1"
DOCS_DIR = ROOT / "docs/strategy_research/g2_r3/gemini_goal_trend_flow_r1"


def verify_freeze_commit(wave: str, freeze_sha: str) -> dict:
    """Verify that the frozen registry is committed at the exact freeze SHA."""
    registry_path = EVIDENCE_DIR / f"{wave}_FROZEN_REGISTRY.json"
    if not registry_path.exists():
        raise FileNotFoundError(f"Registry {registry_path} not found")

    local_bytes = registry_path.read_bytes()
    rel_path = str(registry_path.relative_to(ROOT))

    try:
        git_bytes = subprocess.check_output(
            ["git", "show", f"{freeze_sha}:{rel_path}"],
            cwd=ROOT,
        )
    except subprocess.CalledProcessError as e:
        raise ValueError(f"Failed to read {rel_path} from commit {freeze_sha}: {e}")

    if local_bytes != git_bytes:
        raise ValueError("Local frozen registry does not match git commit contents!")

    registry = json.loads(local_bytes)
    return registry


def execute_wave(wave: str, freeze_sha: str) -> None:
    print(f"=== Starting Execution of {wave} (Freeze SHA: {freeze_sha}) ===")
    registry = verify_freeze_commit(wave, freeze_sha)
    candidates = registry["candidates"]
    folds = get_monthly_folds()

    print(f"Candidates count: {len(candidates)}, Folds count: {len(folds)}")

    # Pre-load and cache all validated monthly arrays (2021-01 to 2023-12)
    print("Pre-loading validated monthly data...")
    all_months = {}
    for y in range(2021, 2024):
        for m in range(1, 13):
            all_months[(y, m)] = load_month(y, m)
    print("All 36 monthly folds ready in memory.")

    # Results dictionary
    wave_results = {
        "wave": wave,
        "freeze_sha": freeze_sha,
        "task_id": registry.get("TASK_ID", "V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1"),
        "candidates": {},
        "wave_decision": "PENDING",
    }

    any_promoted = False
    falsified_candidates = []
    promoted_candidates = []

    for cand in candidates:
        cand_id = cand["id"]
        print(f"\n--- Evaluating Candidate: {cand_id} ---")

        # Two-pass determinism verification
        def run_pass(cost_model, pass_num=1):
            all_trades = []
            curr_equity = 1000.0
            for fold in folds:
                m_prev = all_months[(fold["prev_year"], fold["prev_month"])]
                m_curr = all_months[(fold["year"], fold["month"])]
                data_2m = np.vstack([m_prev, m_curr])

                sigs = generate_wave_signals(
                    data_2m,
                    cand_id,
                    fold["embargo_start_ms"],
                    fold["embargo_end_ms"],
                )

                fold_res = simulate_fold(
                    data_2m,
                    sigs,
                    cand,
                    fold,
                    cost_model,
                    initial_equity=curr_equity,
                )
                all_trades.extend(fold_res["trades"])
                curr_equity = fold_res["ending_equity"]
            return all_trades

        # Pass 1 & Pass 2 for STRESS to verify determinism
        stress_trades_p1 = run_pass(STRESS, 1)
        stress_trades_p2 = run_pass(STRESS, 2)

        if len(stress_trades_p1) != len(stress_trades_p2):
            raise AssertionError(f"Determinism failure on trade count: {len(stress_trades_p1)} vs {len(stress_trades_p2)}")
        if stress_trades_p1 and stress_trades_p2:
            p1_net = [t["net_bps"] for t in stress_trades_p1]
            p2_net = [t["net_bps"] for t in stress_trades_p2]
            if not np.allclose(p1_net, p2_net):
                raise AssertionError("Determinism failure on net bps across passes!")

        base_trades = run_pass(BASE, 1)

        # Performance metrics
        base_metrics = calculate_candidate_metrics(base_trades, "BASE")
        stress_metrics = calculate_candidate_metrics(stress_trades_p1, "STRESS")

        # Bootstrap
        boot_7d = block_bootstrap(stress_trades_p1, block_days=7, n_iter=10000, seed=42)
        boot_14d = block_bootstrap(stress_trades_p1, block_days=14, n_iter=10000, seed=42)

        # Gate check
        gate_res = evaluate_promotion_gate(stress_metrics, boot_7d)

        # 3-trade Decimal audit
        # Pick the month of the first trade for the audit
        audit_records = []
        if stress_trades_p1:
            first_tr = stress_trades_p1[0]
            t_dt = np.datetime64(int(first_tr["entry_at"]), "ms").astype("datetime64[s]").item()
            m_prev = all_months.get((t_dt.year, t_dt.month - 1 if t_dt.month > 1 else 12), all_months[(2021, 1)])
            m_curr = all_months[(t_dt.year, t_dt.month)]
            audit_data = np.vstack([m_prev, m_curr])
            audit_records = audit_candidate_trades(audit_data, stress_trades_p1, STRESS, sample_count=3)

        cand_output = {
            "candidate_id": cand_id,
            "family": cand.get("family", ""),
            "horizon_hours": cand.get("horizon_hours", 8),
            "determinism_verified": True,
            "base_metrics": base_metrics,
            "stress_metrics": stress_metrics,
            "bootstrap_7d": boot_7d,
            "bootstrap_14d": boot_14d,
            "promotion_gate": gate_res,
            "audit_samples": audit_records,
            "status": gate_res["verdict"],
        }

        wave_results["candidates"][cand_id] = cand_output

        print(f"STRESS N: {stress_metrics['trade_count']}, Mean Net BPS: {stress_metrics['mean_net_bps']:.2f}, Equal-Yr Net BPS: {stress_metrics['equal_year_net_bps']:.2f}, PF: {stress_metrics['profit_factor']:.2f}, Max DD: {stress_metrics['max_mtm_drawdown_pct']:.2f}%")
        print(f"Gate Verdict: {gate_res['verdict']}")

        if gate_res["all_passed"]:
            any_promoted = True
            promoted_candidates.append(cand_id)
        else:
            falsified_candidates.append(cand_id)

    if any_promoted:
        wave_decision = "PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT"
    else:
        wave_decision = "ALL_CANDIDATES_FALSIFIED_PROCEED_TO_NEXT_WAVE"

    wave_results["wave_decision"] = wave_decision

    # Write WAVE_01_RESULT.json
    result_path = EVIDENCE_DIR / f"{wave}_RESULT.json"
    result_path.write_text(json.dumps(wave_results, indent=2))
    print(f"\nWritten {result_path}")

    # Write WAVE_01_DECISION.md
    decision_md_path = DOCS_DIR / f"{wave}_DECISION.md"
    write_decision_markdown(decision_md_path, wave_results, registry)
    print(f"Written {decision_md_path}")

    # Update Cumulative Trial Budget Ledger
    ledger_path = EVIDENCE_DIR / "CUMULATIVE_TRIAL_BUDGET_LEDGER.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text())
        ledger["cumulative_trials_evaluated"] += len(candidates)
        ledger["remaining_trial_budget"] = ledger["max_agent_trial_budget"] - ledger["cumulative_trials_evaluated"]
        ledger["completed_waves"] += 1
        ledger["waves"][wave]["status"] = "COMPLETED"
        ledger["waves"][wave]["evaluation_result_file"] = f"evidence/v0.6/b_line/g2_gemini_goal_trend_flow_r1/{wave}_RESULT.json"
        ledger["waves"][wave]["promoted_candidates"] = promoted_candidates
        ledger["waves"][wave]["falsified_candidates"] = falsified_candidates
        ledger_path.write_text(json.dumps(ledger, indent=2))
        print(f"Updated {ledger_path}")

    print(f"=== Wave Execution Complete: {wave_decision} ===")


def write_decision_markdown(path: Path, results: dict, registry: dict) -> None:
    wave = results["wave"]
    freeze_sha = results["freeze_sha"]
    decision = results["wave_decision"]

    lines = [
        f"# {wave} Empirical Research Decision & Performance Report",
        "",
        f"- **TASK_ID**: `{results.get('task_id', '')}`",
        f"- **FREEZE_COMMIT_SHA**: `{freeze_sha}`",
        f"- **WAVE_DECISION**: `{decision}`",
        f"- **DATE_RANGE**: `2021-02 to 2023-12 (35 scored monthly folds, 2021-01 warmup)`",
        "- **SEALED_HOLDOUT**: `2024–2026 strictly untouched`",
        "",
        "## 1. Candidate Performance Summary Table (STRESS 44 bp)",
        "",
        "| Candidate ID | Family | Trades | Mean Gross bp | Mean Net bp | Equal-Yr Net bp | PF | Max MTM DD | 7d LCB | Gate Status |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for cand_id, data in results["candidates"].items():
        sm = data["stress_metrics"]
        boot = data["bootstrap_7d"]
        gate = data["promotion_gate"]
        status = data["status"]
        lines.append(
            f"| `{cand_id}` | `{data['family']}` | {sm['trade_count']} | {sm['mean_gross_bps']:.1f} | {sm['mean_net_bps']:.1f} | {sm['equal_year_net_bps']:.1f} | {sm['profit_factor']:.2f} | {sm['max_mtm_drawdown_pct']:.1f}% | {boot['lcb_95']:.1f} | `{status}` |"
        )

    lines.extend([
        "",
        "## 2. Gate Verification Details",
        "",
    ])

    for cand_id, data in results["candidates"].items():
        gate = data["promotion_gate"]
        lines.append(f"### `{cand_id}`")
        for g_name, g_info in gate["gates"].items():
            pass_str = "PASS" if g_info["passed"] else "FAIL"
            lines.append(f"- **{g_name}**: `{pass_str}` (details: {g_info})")
        lines.append("")

    lines.extend([
        "## 3. Next Action",
        "",
    ])

    if decision == "PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT":
        lines.append("A candidate has passed all 7 strict promotion criteria under 44 bp stress cost. Publishing promotable development hypothesis.")
    else:
        lines.append("All 6 Wave 1 candidates failed the promotion criteria under 44 bp stress cost. Advancing to Wave 2 under the cumulative trial budget.")

    path.write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wave", default="WAVE_01")
    parser.add_argument("--freeze", required=True)
    args = parser.parse_args()

    execute_wave(args.wave, args.freeze)
