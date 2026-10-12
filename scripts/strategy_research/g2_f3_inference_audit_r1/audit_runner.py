"""Audit runner coordinating independent forensic reconstruction and evidence compilation.

Operates strictly read-only on original evidence files and outputs machine-audited
evidence ledgers to the own namespace.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from scripts.strategy_research.g2_f3_inference_audit_r1.alternative_stats import (
    compute_adverse_event_sensitivity,
    compute_exact_binomial_sign_test,
    compute_fixed_se_block_bootstrap,
    evaluate_sparse_interval_refusal,
)
from scripts.strategy_research.g2_f3_inference_audit_r1.degenerate_studentizer import (
    audit_sparse_inference_mechanism,
)
from scripts.strategy_research.g2_f3_inference_audit_r1.diagnostics import (
    audit_event_and_block_support,
    audit_horizon_overlap,
    audit_profit_factor_sentinels,
    classify_source_causality_and_known_at,
    compute_gross_fee_economics,
    compute_leave_one_event_out_influence,
)
from scripts.strategy_research.g2_f3_inference_audit_r1.reconciliation import (
    load_jsonl_trades,
    reconcile_f3_candidate_ledger,
)

ORIGINAL_EVIDENCE_DIR = Path("evidence/v0.6/b_line/g2_flow_funding_entries_r1")
EVAL_START_MS = 1612137600000  # 2021-02-01 00:00:00 UTC
EVAL_END_MS = 1704067200000    # 2023-12-31 24:00:00 UTC


def run_full_forensic_audit(
    evidence_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute complete independent forensic audit over F3 and flow-funding evidence."""
    source_dir = evidence_dir or ORIGINAL_EVIDENCE_DIR

    # 1. Reconcile all F3 ledgers
    f3_ledgers = {
        "F3_12H_STRESS": reconcile_f3_candidate_ledger(source_dir / "F3_MARK_LAST_DISLOCATION_REPAIR_12H_STRESS_orders.jsonl"),
        "F3_18H_STRESS": reconcile_f3_candidate_ledger(source_dir / "F3_MARK_LAST_DISLOCATION_REPAIR_18H_STRESS_orders.jsonl"),
        "F3_12H_BASE": reconcile_f3_candidate_ledger(source_dir / "F3_MARK_LAST_DISLOCATION_REPAIR_12H_BASE_orders.jsonl"),
        "F3_18H_BASE": reconcile_f3_candidate_ledger(source_dir / "F3_MARK_LAST_DISLOCATION_REPAIR_18H_BASE_orders.jsonl"),
    }

    trades_12h_stress = load_jsonl_trades(source_dir / "F3_MARK_LAST_DISLOCATION_REPAIR_12H_STRESS_orders.jsonl")
    trades_18h_stress = load_jsonl_trades(source_dir / "F3_MARK_LAST_DISLOCATION_REPAIR_18H_STRESS_orders.jsonl")

    # 2. Reconcile signal counts vs executed trades
    # Load original results JSON to get candidate configs and fates
    results_path = source_dir / "FLOW_FUNDING_RESULTS.json"
    with open(results_path, encoding="utf-8") as f:
        orig_results = json.load(f)

    c12 = orig_results["candidates"]["F3_MARK_LAST_DISLOCATION_REPAIR_12H"]["costs"]["STRESS"]
    signals_count = orig_results["candidates"]["F3_MARK_LAST_DISLOCATION_REPAIR_12H"]["signals_count"]
    fates = c12["account"]["fates"]

    # 3. Diagnostics
    support_12h = audit_event_and_block_support(trades_12h_stress, EVAL_START_MS, EVAL_END_MS, block_days=14)
    support_12h_7d = audit_event_and_block_support(trades_12h_stress, EVAL_START_MS, EVAL_END_MS, block_days=7)
    overlap_12_18 = audit_horizon_overlap(trades_12h_stress, trades_18h_stress)
    influence_12h = compute_leave_one_event_out_influence(trades_12h_stress)
    influence_18h = compute_leave_one_event_out_influence(trades_18h_stress)
    economics_12h = compute_gross_fee_economics(trades_12h_stress)
    economics_18h = compute_gross_fee_economics(trades_18h_stress)

    # 4. Profit factor sentinel analysis
    annual_12h = f3_ledgers["F3_12H_STRESS"]["annual_reconciliation"]
    pf_sentinels_12h = audit_profit_factor_sentinels(annual_12h)

    # 5. Degenerate studentizer failure mechanism reconstruction
    # Reconstruct 14-day and 7-day block returns for all 6 candidates from original trade ledgers
    block_returns_14d: dict[str, np.ndarray] = {}
    block_returns_7d: dict[str, np.ndarray] = {}

    for cand_id, file_prefix in [
        ("F1_AGGRESSOR_FLOW_ABSORPTION_12H", "F1_AGGRESSOR_FLOW_ABSORPTION_12H_STRESS_orders.jsonl"),
        ("F1_AGGRESSOR_FLOW_ABSORPTION_18H", "F1_AGGRESSOR_FLOW_ABSORPTION_18H_STRESS_orders.jsonl"),
        ("F2_REALIZED_FUNDING_REVERSAL_12H", "F2_REALIZED_FUNDING_REVERSAL_12H_STRESS_orders.jsonl"),
        ("F2_REALIZED_FUNDING_REVERSAL_18H", "F2_REALIZED_FUNDING_REVERSAL_18H_STRESS_orders.jsonl"),
        ("F3_MARK_LAST_DISLOCATION_REPAIR_12H", "F3_MARK_LAST_DISLOCATION_REPAIR_12H_STRESS_orders.jsonl"),
        ("F3_MARK_LAST_DISLOCATION_REPAIR_18H", "F3_MARK_LAST_DISLOCATION_REPAIR_18H_STRESS_orders.jsonl"),
    ]:
        cand_trades = load_jsonl_trades(source_dir / file_prefix)
        # 14d
        b14_ms = 14 * 86_400_000
        n_b14 = math.ceil((EVAL_END_MS - EVAL_START_MS) / b14_ms)
        arr14 = np.zeros(n_b14, dtype=np.float64)
        for t in cand_trades:
            idx = int((t["entry_at"] - EVAL_START_MS) // b14_ms)
            if 0 <= idx < n_b14:
                arr14[idx] += float(t["net_after_funding_bps"])
        block_returns_14d[cand_id] = arr14

        # 7d
        b7_ms = 7 * 86_400_000
        n_b7 = math.ceil((EVAL_END_MS - EVAL_START_MS) / b7_ms)
        arr7 = np.zeros(n_b7, dtype=np.float64)
        for t in cand_trades:
            idx = int((t["entry_at"] - EVAL_START_MS) // b7_ms)
            if 0 <= idx < n_b7:
                arr7[idx] += float(t["net_after_funding_bps"])
        block_returns_7d[cand_id] = arr7

    audit_14d = audit_sparse_inference_mechanism(block_returns_14d, n_rounds=2000, seed=20261012, floor=1e-6)
    audit_7d = audit_sparse_inference_mechanism(block_returns_7d, n_rounds=2000, seed=20261012, floor=1e-6)

    # 6. Statistical alternatives
    refusal_12h = evaluate_sparse_interval_refusal(len(trades_12h_stress), support_12h["n_active_blocks"])
    sign_test_12h = compute_exact_binomial_sign_test(len(trades_12h_stress), economics_12h["win_count"])
    sign_test_18h = compute_exact_binomial_sign_test(len(trades_18h_stress), economics_18h["win_count"])
    sensitivity_12h = compute_adverse_event_sensitivity(trades_12h_stress)
    sensitivity_18h = compute_adverse_event_sensitivity(trades_18h_stress)
    fixed_se_bootstrap_12h = compute_fixed_se_block_bootstrap(block_returns_14d["F3_MARK_LAST_DISLOCATION_REPAIR_12H"])

    # 7. Source causality audit
    causality = classify_source_causality_and_known_at()

    # Terminal scientific verdict
    terminal_verdict = "F3_SPARSE_MECHANISM_SOURCE_AND_STATS_DIAGNOSED"

    audit_report = {
        "task_id": "V06_G2_GEMINI_F3_SPARSE_INFERENCE_AUDIT_R1",
        "terminal_verdict": terminal_verdict,
        "f3_ledgers_reconciliation": f3_ledgers,
        "signal_vs_executed_reconciliation": {
            "signals_total": signals_count,
            "executed_trades": len(trades_12h_stress),
            "rejections": fates,
            "rejection_mechanism": "SINGLE_POSITION_AND_4H_COOLDOWN_CONSTRAINT",
        },
        "diagnostics": {
            "support_14d": support_12h,
            "support_7d": support_12h_7d,
            "horizon_overlap": overlap_12_18,
            "leave_one_out_influence_12h": influence_12h,
            "leave_one_out_influence_18h": influence_18h,
            "economics_12h": economics_12h,
            "economics_18h": economics_18h,
            "pf_sentinels_12h": pf_sentinels_12h,
        },
        "degenerate_studentizer_audit": {
            "14_day_block_bootstrap": audit_14d,
            "7_day_block_bootstrap": audit_7d,
        },
        "statistical_alternatives": {
            "interval_refusal": refusal_12h,
            "sign_test_12h": sign_test_12h,
            "sign_test_18h": sign_test_18h,
            "adverse_sensitivity_12h": sensitivity_12h,
            "adverse_sensitivity_18h": sensitivity_18h,
            "exploratory_fixed_se_bootstrap_12h": fixed_se_bootstrap_12h,
        },
        "source_causality": causality,
    }

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / "F3_SPARSE_INFERENCE_AUDIT_EVIDENCE.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(audit_report, f, indent=2)

    return audit_report
