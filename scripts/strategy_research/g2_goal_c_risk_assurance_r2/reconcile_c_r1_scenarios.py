"""Reconciliation of C R1's 32 synthetic margin scenarios and generation of C R2's 56-scenario fixture matrix.

Independently validates every row of C R1's `SYNTHETIC_MARGIN_AND_LEVERAGE_STRESS.json` via
`decimal_margin_engine.evaluate_decimal_margin_scenario`, computes exact filtered denominators
(resolving the impossible `7/6` human report error), exposes the IEEE-754 float lot-floor drift
(`0.474` vs exact `0.475` BTC at 15x naive) and discretionary margin top-up in
`RISK_BUDGET_CAPPED_ISOLATED`, and constructs 56 deterministic synthetic margin/liquidation fixtures.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .decimal_margin_engine import (
    D,
    compute_filtered_scenario_denominators,
    evaluate_decimal_margin_scenario,
)


def extract_c_r1_scenario_inputs(c_r1_row: dict[str, Any]) -> dict[str, Any]:
    """Extract input parameters from a committed C R1 scenario row for independent Decimal evaluation."""
    sid = str(c_r1_row["scenario_id"])
    return {
        "scenario_id": sid,
        "side": int(c_r1_row["side"]),
        "leverage": D(c_r1_row["leverage"]),
        "mmr": D(c_r1_row["hypothetical_mmr"]),
        "clearance_fee_bps": D(c_r1_row["hypothetical_clearance_fee_bps"]),
        "entry_price": D("30000.0"),
        "stop_distance_pct": D(c_r1_row["stop_distance_pct"]),
        "intrabar_adverse_mark_pct": D(c_r1_row["intrabar_adverse_mark_pct"]),
        "open_gap_adverse_pct": D(c_r1_row["open_gap_adverse_pct"]),
        "funding_rate_bps": D("8.0"),
        "partial_tp1_before_shock": bool(c_r1_row["partial_tp1_before_shock"]),
        "sizing_mode": str(c_r1_row["sizing_mode"]),
        "max_account_risk_pct": D("0.02"),
        "initial_cash": D("1000.0"),
        "cost_name": "STRESS",
    }


def reconcile_c_r1_32_scenarios(c_r1_evidence_dir: Path) -> dict[str, Any]:
    """Recompute all 32 C R1 synthetic scenarios in pure Decimal and audit denominators and invariants."""
    raw_json = json.loads(
        (c_r1_evidence_dir / "SYNTHETIC_MARGIN_AND_LEVERAGE_STRESS.json").read_text(encoding="utf-8")
    )
    env = raw_json["synthetic_leverage_stress_envelope"]
    c_r1_scenarios: list[dict[str, Any]] = env["scenarios"]
    assert len(c_r1_scenarios) == 32, f"Expected 32 C R1 scenarios, found {len(c_r1_scenarios)}"

    compared_fields = (
        "initial_qty_btc",
        "open_qty_at_shock_btc",
        "initial_notional_usdt",
        "effective_account_leverage_ratio",
        "initial_margin_posted_usdt",
        "stop_price",
        "maintenance_margin_required_usdt",
        "effective_margin_equity_at_shock_usdt",
        "mark_liquidated_at_shock",
        "mark_liquidated_before_strategy_stop",
        "isolated_margin_after_gap_usdt",
        "isolated_margin_bankruptcy_deficit_usdt",
        "total_account_equity_after_gap_usdt",
        "account_insolvent_after_gap",
    )

    recomputed_rows: list[dict[str, Any]] = []
    row_comparisons: list[dict[str, Any]] = []
    max_abs_diff_given_declared_qty = 0.0
    max_abs_diff_from_pure_decimal_sizing = 0.0
    float_lot_drift_rows: list[str] = []
    discretionary_buffer_rows: list[str] = []
    strict_nl_liquidation_flip_rows: list[str] = []

    for idx, old_row in enumerate(c_r1_scenarios):
        params = extract_c_r1_scenario_inputs(old_row)
        # 1. Pure Decimal from sizing formula (exposes 0.475 vs 0.474 float floor drift on 15x naive)
        new_row = evaluate_decimal_margin_scenario(**params)
        # 2. Pure Decimal given C R1's declared initial_qty_btc
        new_row_declared_q = evaluate_decimal_margin_scenario(
            **params,
            override_initial_qty_btc=D(old_row["initial_qty_btc"]),
        )
        recomputed_rows.append(new_row)

        field_diffs: dict[str, Any] = {}
        row_max_diff_formula = 0.0
        row_max_diff_declared_q = 0.0
        boolean_mismatches: list[str] = []
        for f in compared_fields:
            old_val = old_row[f]
            new_val = new_row[f]
            dec_q_val = new_row_declared_q[f]
            if isinstance(old_val, bool):
                match = bool(old_val) == bool(new_val) and bool(old_val) == bool(dec_q_val)
                if not match:
                    boolean_mismatches.append(f)
                field_diffs[f] = {
                    "c_r1": old_val,
                    "c_r2_decimal_formula": new_val,
                    "c_r2_decimal_declared_qty": dec_q_val,
                    "exact_match": match,
                }
            else:
                diff_f = abs(float(old_val) - float(new_val))
                diff_q = abs(float(old_val) - float(dec_q_val))
                row_max_diff_formula = max(row_max_diff_formula, diff_f)
                row_max_diff_declared_q = max(row_max_diff_declared_q, diff_q)
                max_abs_diff_from_pure_decimal_sizing = max(
                    max_abs_diff_from_pure_decimal_sizing, diff_f
                )
                max_abs_diff_given_declared_qty = max(max_abs_diff_given_declared_qty, diff_q)
                field_diffs[f] = {
                    "c_r1": old_val,
                    "c_r2_decimal_formula": new_val,
                    "c_r2_decimal_declared_qty": dec_q_val,
                    "abs_diff_formula": round(diff_f, 8),
                    "abs_diff_declared_qty": round(diff_q, 8),
                }

        has_float_lot_drift = abs(old_row["initial_qty_btc"] - new_row["initial_qty_btc"]) > 1e-9
        if has_float_lot_drift:
            float_lot_drift_rows.append(new_row["scenario_id"])

        has_disc_buffer = new_row["discretionary_margin_buffer_usdt"] > 0.0
        if has_disc_buffer:
            discretionary_buffer_rows.append(new_row["scenario_id"])

        strict_liq_flip = (
            new_row["strict_nl_liquidated_before_strategy_stop"]
            != new_row["mark_liquidated_before_strategy_stop"]
        )
        if strict_liq_flip:
            strict_nl_liquidation_flip_rows.append(new_row["scenario_id"])

        if strict_liq_flip:
            violating_inv = "DISCRETIONARY_MARGIN_TOPUP_REDUCES_EFFECTIVE_ISOLATED_LEVERAGE_FROM_15X_TO_8_7X__LIQUIDATES_UNDER_STRICT_NL_MARGIN"
        elif has_disc_buffer:
            violating_inv = "DISCRETIONARY_MARGIN_TOPUP_ABOVE_N_OVER_L"
        elif has_float_lot_drift:
            violating_inv = "IEEE754_FLOAT_LOT_FLOOR_DRIFT_0474_VS_DECIMAL_0475_BTC"
        else:
            violating_inv = "NONE_IN_ROW_ARITHMETIC__SUMMARY_DENOMINATOR_BUG_ONLY"

        row_comparisons.append({
            "row_index": idx,
            "scenario_id": old_row["scenario_id"],
            "sizing_mode": old_row["sizing_mode"],
            "leverage": old_row["leverage"],
            "hypothetical_mmr": old_row["hypothetical_mmr"],
            "side": old_row["side"],
            "partial_tp1_before_shock": old_row["partial_tp1_before_shock"],
            "c_r1_declared_qty_btc": old_row["initial_qty_btc"],
            "c_r2_exact_decimal_qty_btc": new_row["initial_qty_btc"],
            "c_r1_arithmetic_reproduced_given_declared_qty": (
                row_max_diff_declared_q <= 1e-4 and not boolean_mismatches
            ),
            "c_r1_arithmetic_reproduced_from_formula": (
                row_max_diff_formula <= 1e-4 and not boolean_mismatches
            ),
            "max_abs_numeric_diff_declared_qty": round(row_max_diff_declared_q, 8),
            "max_abs_numeric_diff_formula": round(row_max_diff_formula, 8),
            "max_abs_numeric_diff": round(row_max_diff_declared_q, 8),
            "boolean_mismatches": boolean_mismatches,
            "strict_exchange_initial_margin_usdt": new_row["strict_exchange_initial_margin_usdt"],
            "c_r1_posted_initial_margin_usdt": new_row["initial_margin_posted_usdt"],
            "discretionary_margin_buffer_usdt": new_row["discretionary_margin_buffer_usdt"],
            "effective_isolated_position_leverage": new_row["effective_isolated_position_leverage"],
            "posted_margin_liq_adverse_move_pct": new_row["posted_margin_liq_adverse_move_pct"],
            "strict_nl_margin_liq_adverse_move_pct": new_row["strict_nl_margin_liq_adverse_move_pct"],
            "c_r1_mark_liquidated_before_stop": new_row["mark_liquidated_before_strategy_stop"],
            "strict_nl_mark_liquidated_before_stop": new_row["strict_nl_liquidated_before_strategy_stop"],
            "isolated_margin_bankruptcy_deficit_usdt": new_row["isolated_margin_bankruptcy_deficit_usdt"],
            "total_account_equity_after_gap_usdt": new_row["total_account_equity_after_gap_usdt"],
            "account_insolvent_after_gap": new_row["account_insolvent_after_gap"],
            "earliest_violating_conceptual_invariant": violating_inv,
            "field_comparisons": field_diffs,
        })

    group_predicates = {
        "all_32_scenarios": lambda _s: True,
        "all_1x_5x_scenarios": lambda s: s["leverage"] in (1.0, 5.0),
        "naive_1x_5x_scenarios": lambda s: (
            s["sizing_mode"] == "NAIVE_FULL_LEVERAGE_NOTIONAL" and s["leverage"] in (1.0, 5.0)
        ),
        "risk_capped_1x_5x_scenarios": lambda s: (
            s["sizing_mode"] == "RISK_BUDGET_CAPPED_ISOLATED" and s["leverage"] in (1.0, 5.0)
        ),
        "naive_10x_15x_no_tp1_c_r1_filter": lambda s: (
            s["sizing_mode"] == "NAIVE_FULL_LEVERAGE_NOTIONAL"
            and s["leverage"] in (10.0, 15.0)
            and not s["partial_tp1_before_shock"]
        ),
        "naive_10x_15x_loop1_only_6_cases": lambda s: (
            s["scenario_id"].startswith("SYN_LEV_")
            and s["sizing_mode"] == "NAIVE_FULL_LEVERAGE_NOTIONAL"
            and s["leverage"] in (10.0, 15.0)
        ),
        "naive_10x_15x_loop2_partial_tp1_false_4_cases": lambda s: (
            s["scenario_id"].startswith("SYN_PARTIAL_TP1_")
            and not s["partial_tp1_before_shock"]
        ),
        "naive_10x_15x_loop2_partial_tp1_true_4_cases": lambda s: (
            s["scenario_id"].startswith("SYN_PARTIAL_TP1_")
            and s["partial_tp1_before_shock"]
        ),
        "naive_10x_15x_all_14_cases": lambda s: (
            s["sizing_mode"] == "NAIVE_FULL_LEVERAGE_NOTIONAL" and s["leverage"] in (10.0, 15.0)
        ),
        "risk_capped_10x_15x_6_cases": lambda s: (
            s["sizing_mode"] == "RISK_BUDGET_CAPPED_ISOLATED" and s["leverage"] in (10.0, 15.0)
        ),
    }

    denominators = compute_filtered_scenario_denominators(recomputed_rows, group_predicates)

    return {
        "c_r1_summary_findings_status": "INVALID__IMPOSSIBLE_7_OVER_6_DENOMINATOR_AND_HIDDEN_DISCRETIONARY_MARGIN_TOPUP",
        "scenario_count": len(recomputed_rows),
        "row_level_arithmetic_max_abs_diff": round(max_abs_diff_given_declared_qty, 8),
        "pure_decimal_formula_sizing_max_abs_diff": round(max_abs_diff_from_pure_decimal_sizing, 8),
        "all_32_rows_float_arithmetic_reproduced": max_abs_diff_given_declared_qty <= 1e-4,
        "all_32_rows_booleans_exact_match": all(
            not r["boolean_mismatches"] for r in row_comparisons
        ),
        "contradiction_3_root_cause_and_witness": {
            "c_r1_human_report_claim": (
                "5 / 6 naive 10x/15x scenarios suffer forced Mark liquidation before strategy stop; "
                "7 / 6 suffer isolated margin bankruptcy deficits on the 9.5%-10% stop gap."
            ),
            "c_r1_run_py_defect_location": "scripts/strategy_research/g2_goal_execution_assurance_r1/run.py lines 199-200",
            "c_r1_risk_envelope_filter_location": "scripts/strategy_research/g2_goal_execution_assurance_r1/risk_envelope.py lines 228-232",
            "exact_explanation": (
                "In risk_envelope.py lines 228-232, `naive_10x_15x` filters `scenarios` for "
                "`sizing_mode == 'NAIVE_FULL_LEVERAGE_NOTIONAL' and leverage in (10.0, 15.0) and not partial_tp1_before_shock`. "
                "That filter matches 10 scenarios out of 32 (6 from Loop 1 `SYN_LEV_*` + 4 from Loop 2 `SYN_PARTIAL_TP1_*_TP1_0`), "
                "NOT 6! Across those 10 scenarios, 5 (all five 15x scenarios) have `mark_liquidated_before_strategy_stop=True` (5/10), "
                "and 7 (all five 15x scenarios plus two 10x Loop-2 scenarios with 10% gap) have "
                "`isolated_margin_bankruptcy_deficit_usdt < 0` (7/10). C R1's `run.py` hardcoded `/ 6` in the Markdown template, "
                "producing `5 / 6` and the mathematically impossible `7 / 6`."
            ),
            "discretionary_margin_topup_finding": (
                "In C R1's `RISK_BUDGET_CAPPED_ISOLATED` mode (lines 91-96 of risk_envelope.py), `initial_margin_posted` "
                "was set to `max(N / L, N * per_unit_risk_frac)` (~11.46%-12.06% of notional), which adds a discretionary "
                "margin buffer above `N / L` and lowers effective isolated leverage on 15x scenarios to ~8.29x-8.72x. "
                "When evaluated at strict exchange initial margin `M0 = N / L` (6.67% at 15x), all 3 of the 15x risk-capped "
                "scenarios (`SYN_LEV_15X_MMR_40BP_RISK_`, `SYN_LEV_15X_MMR_50BP_RISK_`, `SYN_LEV_15X_MMR_100BP_RISK_`) "
                "STILL liquidate on the 6.8% Mark shock (`3/6` of risk-capped 10x/15x scenarios)."
            ),
            "ieee754_float_lot_floor_drift_finding": (
                "On the 7 15x naive scenarios (`target_notional = 950.0 * 15.0 = 14250.0`, `entry_price = 30000.0`), "
                "exact Decimal lot sizing is `14250 / 30000 = 0.475` BTC (`14,250.0` USDT notional, `950.0` USDT margin), "
                "whereas C R1's float expression `math.floor((14250.0 / 30000.0) / 0.001) * 0.001` evaluated "
                "`0.475 / 0.001` as `474.99999999999994` in IEEE-754 binary float, truncating to `0.474` BTC (`14,220.0` USDT notional)."
            ),
            "float_lot_drift_scenario_ids": float_lot_drift_rows,
            "discretionary_buffer_scenario_ids": discretionary_buffer_rows,
            "strict_nl_liquidation_flip_scenario_ids": strict_nl_liquidation_flip_rows,
        },
        "grouped_denominators_and_counts": denominators,
        "recomputed_32_scenarios": recomputed_rows,
        "row_by_row_audit_table": row_comparisons,
    }


def build_c_r2_56_synthetic_margin_matrix() -> dict[str, Any]:
    """Construct the frozen C R2 deterministic synthetic margin/liquidation matrix (56 scenarios >= 50 required).

    Covers:
    - Group 1 (24 scenarios): 1x/5x/10x/15x x 3 MMRs (40, 50, 100 bps) x Naive Full Leverage vs
      Risk-Capped with STRICT `M0 = N/L` initial margin (no hidden margin top-up) on 7.5% synthetic stop.
    - Group 2 (8 scenarios): 10x/15x x LONG/SHORT x Real historical W1 max 1R stop (3.6120%) under
      (a) 3.6120% Mark move (Stop-First, no liquidation) vs (b) 5.20% intrabar Mark wick (Liquidation-First at 15x).
    - Group 3 (8 scenarios): 10x/15x x LONG/SHORT x Partial TP1 quantity reduction (`q_rem = q - q1`)
      with un-ACKed pending TP1 profit vs ACKed spendable TP1 cash.
    - Group 4 (8 scenarios): 10x/15x x Fee/funding before vs after shock, 1m settled Mark close vs
      intrabar Mark High/Low wick, and cancel-replace ACK latency race at stop execution.
    - Group 5 (8 scenarios): Negative isolated collateral (`isolated_margin_after_gap < 0`) with POSITIVE
      total account equity (`total_account_equity > 0`) vs total account insolvency (`total_account_equity <= 0`),
      plus explicit `UNKNOWN_HISTORICAL_EXCHANGE_TIER` high-MMR stress rows.
    """
    scenarios: list[dict[str, Any]] = []

    # Group 1: 24 scenarios (4 leverages x 3 MMRs x 2 strict-M0 sizing modes)
    for lev in (1, 5, 10, 15):
        for mmr_bps, mmr_str in ((40, "0.004"), (50, "0.005"), (100, "0.010")):
            for mode, mode_tag in (
                ("NAIVE_FULL_LEVERAGE_NOTIONAL", "NAIVE"),
                ("RISK_BUDGET_CAPPED_STRICT_NL_MARGIN", "CAP_STRICT_NL"),
            ):
                sid = f"CR2_G1_LEV_{lev}X_MMR_{mmr_bps}BP_{mode_tag}"
                scenarios.append(
                    evaluate_decimal_margin_scenario(
                        scenario_id=sid,
                        side=1,
                        leverage=Decimal(lev),
                        mmr=Decimal(mmr_str),
                        clearance_fee_bps=Decimal("75.0"),
                        entry_price=Decimal("30000.0"),
                        stop_distance_pct=Decimal("0.075"),
                        intrabar_adverse_mark_pct=Decimal("0.068"),
                        mark_close_adverse_pct=Decimal("0.055"),
                        open_gap_adverse_pct=Decimal("0.095"),
                        partial_tp1_before_shock=False,
                        sizing_mode=mode,
                    )
                )

    # Group 2: 8 scenarios contrasting REAL historical W1 max stop (3.6120%) with vs without intrabar Mark wick
    for lev in (10, 15):
        for side, side_tag in ((1, "LONG"), (-1, "SHORT")):
            # Case A: Mark moves to 3.6120% stop without exceeding 15x liquidation threshold (~4.95%)
            scenarios.append(
                evaluate_decimal_margin_scenario(
                    scenario_id=f"CR2_G2_REAL_W1_STOP_{lev}X_{side_tag}_NO_EXTRA_WICK",
                    side=side,
                    leverage=Decimal(lev),
                    mmr=Decimal("0.005"),
                    clearance_fee_bps=Decimal("75.0"),
                    entry_price=Decimal("30000.0"),
                    stop_distance_pct=Decimal("0.036120"),
                    intrabar_adverse_mark_pct=Decimal("0.036120"),
                    mark_close_adverse_pct=Decimal("0.034000"),
                    open_gap_adverse_pct=Decimal("0.038000"),
                    partial_tp1_before_shock=False,
                    sizing_mode="NAIVE_FULL_LEVERAGE_NOTIONAL",
                )
            )
            # Case B: Intrabar Mark wick spikes to 5.20% (exceeding 15x threshold ~4.95% while 1m close settles at 3.50%)
            scenarios.append(
                evaluate_decimal_margin_scenario(
                    scenario_id=f"CR2_G2_REAL_W1_STOP_{lev}X_{side_tag}_INTRABAR_WICK_520BP",
                    side=side,
                    leverage=Decimal(lev),
                    mmr=Decimal("0.005"),
                    clearance_fee_bps=Decimal("75.0"),
                    entry_price=Decimal("30000.0"),
                    stop_distance_pct=Decimal("0.036120"),
                    intrabar_adverse_mark_pct=Decimal("0.052000"),
                    mark_close_adverse_pct=Decimal("0.035000"),
                    open_gap_adverse_pct=Decimal("0.053000"),
                    partial_tp1_before_shock=False,
                    sizing_mode="NAIVE_FULL_LEVERAGE_NOTIONAL",
                )
            )

    # Group 3: 8 scenarios testing post-TP1 partial quantity (`q_rem = q - q1`) and TP1 ACK cash spendability
    for lev in (10, 15):
        for side, side_tag in ((1, "LONG"), (-1, "SHORT")):
            for acked, ack_tag in ((False, "TP1_UNACKED"), (True, "TP1_ACKED")):
                scenarios.append(
                    evaluate_decimal_margin_scenario(
                        scenario_id=f"CR2_G3_PARTIAL_TP1_{lev}X_{side_tag}_{ack_tag}",
                        side=side,
                        leverage=Decimal(lev),
                        mmr=Decimal("0.005"),
                        clearance_fee_bps=Decimal("75.0"),
                        entry_price=Decimal("30000.0"),
                        stop_distance_pct=Decimal("0.060"),
                        intrabar_adverse_mark_pct=Decimal("0.092"),
                        mark_close_adverse_pct=Decimal("0.088"),
                        open_gap_adverse_pct=Decimal("0.115"),
                        partial_tp1_before_shock=True,
                        tp1_cash_acked_before_shock=acked,
                        sizing_mode="NAIVE_FULL_LEVERAGE_NOTIONAL",
                    )
                )

    # Group 4: 8 scenarios testing funding before/after shock and cancel-replace ACK latency race on stop
    for lev in (10, 15):
        for fund_before, fund_tag in ((True, "FUND_BEFORE"), (False, "FUND_AFTER")):
            for ack_race, race_tag in ((False, "STOP_QTY_REDUCED"), (True, "CANCEL_REPLACE_RACE_FULL_QTY")):
                scenarios.append(
                    evaluate_decimal_margin_scenario(
                        scenario_id=f"CR2_G4_CLOCK_{lev}X_{fund_tag}_{race_tag}",
                        side=1,
                        leverage=Decimal(lev),
                        mmr=Decimal("0.005"),
                        clearance_fee_bps=Decimal("75.0"),
                        entry_price=Decimal("30000.0"),
                        stop_distance_pct=Decimal("0.050"),
                        intrabar_adverse_mark_pct=Decimal("0.046"),
                        mark_close_adverse_pct=Decimal("0.042"),
                        open_gap_adverse_pct=Decimal("0.085"),
                        funding_rate_bps=Decimal("25.0"),
                        funding_settled_before_shock=fund_before,
                        partial_tp1_before_shock=True,
                        tp1_cash_acked_before_shock=False,
                        cancel_replace_ack_pending_at_stop=ack_race,
                        sizing_mode="NAIVE_FULL_LEVERAGE_NOTIONAL",
                    )
                )

    # Group 5a: 4 scenarios where RISK_BUDGET_CAPPED_STRICT_NL_MARGIN experiences a 12% gap:
    # isolated collateral goes negative (`isolated_margin_after_gap < 0`), while total account equity stays > +950 USDT!
    for lev in (10, 15):
        for side, side_tag in ((1, "LONG"), (-1, "SHORT")):
            scenarios.append(
                evaluate_decimal_margin_scenario(
                    scenario_id=f"CR2_G5_ISO_DEFICIT_POS_TOTAL_EQ_{lev}X_{side_tag}",
                    side=side,
                    leverage=Decimal(lev),
                    mmr=Decimal("0.005"),
                    clearance_fee_bps=Decimal("75.0"),
                    entry_price=Decimal("30000.0"),
                    stop_distance_pct=Decimal("0.036120"),
                    intrabar_adverse_mark_pct=Decimal("0.035000"),
                    mark_close_adverse_pct=Decimal("0.033000"),
                    open_gap_adverse_pct=Decimal("0.120000"),
                    partial_tp1_before_shock=False,
                    sizing_mode="RISK_BUDGET_CAPPED_STRICT_NL_MARGIN",
                )
            )
    # Group 5b: 2 scenarios where NAIVE_FULL_LEVERAGE_NOTIONAL at 15x experiences a 12% gap -> BOTH isolated collateral AND total account equity < 0!
    for side, side_tag in ((1, "LONG"), (-1, "SHORT")):
        scenarios.append(
            evaluate_decimal_margin_scenario(
                scenario_id=f"CR2_G5_TOTAL_ACCOUNT_INSOLVENT_15X_{side_tag}",
                side=side,
                leverage=Decimal(15),
                mmr=Decimal("0.005"),
                clearance_fee_bps=Decimal("75.0"),
                entry_price=Decimal("30000.0"),
                stop_distance_pct=Decimal("0.075000"),
                intrabar_adverse_mark_pct=Decimal("0.068000"),
                mark_close_adverse_pct=Decimal("0.068000"),
                open_gap_adverse_pct=Decimal("0.120000"),
                partial_tp1_before_shock=False,
                sizing_mode="NAIVE_FULL_LEVERAGE_NOTIONAL",
            )
        )
    # Group 5c: 2 scenarios illustrating UNKNOWN historical exchange maintenance bracket sensitivity (MMR=250 bps)
    for lev in (10, 15):
        scenarios.append(
            evaluate_decimal_margin_scenario(
                scenario_id=f"CR2_G5_UNKNOWN_BRACKET_MMR_250BP_{lev}X",
                side=1,
                leverage=Decimal(lev),
                mmr=Decimal("0.025"),
                clearance_fee_bps=Decimal("125.0"),
                entry_price=Decimal("30000.0"),
                stop_distance_pct=Decimal("0.036120"),
                intrabar_adverse_mark_pct=Decimal("0.035000"),
                mark_close_adverse_pct=Decimal("0.035000"),
                open_gap_adverse_pct=Decimal("0.045000"),
                partial_tp1_before_shock=False,
                sizing_mode="NAIVE_FULL_LEVERAGE_NOTIONAL",
                historical_bracket_status="UNKNOWN_HISTORICAL_BINANCE_BRACKET__SENSITIVITY_ONLY",
            )
        )

    assert len(scenarios) == 56, f"Expected 56 C R2 scenarios, got {len(scenarios)}"

    c_r2_group_predicates = {
        "all_56_c_r2_scenarios": lambda _s: True,
        "group1_naive_1x_5x": lambda s: (
            s["scenario_id"].startswith("CR2_G1_")
            and s["sizing_mode"] == "NAIVE_FULL_LEVERAGE_NOTIONAL"
            and s["leverage"] in (1.0, 5.0)
        ),
        "group1_naive_10x_15x": lambda s: (
            s["scenario_id"].startswith("CR2_G1_")
            and s["sizing_mode"] == "NAIVE_FULL_LEVERAGE_NOTIONAL"
            and s["leverage"] in (10.0, 15.0)
        ),
        "group1_strict_nl_capped_10x_15x": lambda s: (
            s["scenario_id"].startswith("CR2_G1_")
            and s["sizing_mode"] == "RISK_BUDGET_CAPPED_STRICT_NL_MARGIN"
            and s["leverage"] in (10.0, 15.0)
        ),
        "group2_real_w1_stop_no_wick": lambda s: (
            s["scenario_id"].startswith("CR2_G2_") and s["scenario_id"].endswith("_NO_EXTRA_WICK")
        ),
        "group2_real_w1_stop_with_520bp_wick": lambda s: (
            s["scenario_id"].startswith("CR2_G2_") and s["scenario_id"].endswith("_INTRABAR_WICK_520BP")
        ),
        "group5_negative_isolated_positive_total_equity": lambda s: bool(
            s.get("negative_isolated_but_positive_total_equity", False)
        ),
        "group5_total_account_insolvent": lambda s: bool(s.get("account_insolvent_after_gap", False)),
    }

    denominators = compute_filtered_scenario_denominators(scenarios, c_r2_group_predicates)
    return {
        "grade": "SYNTHETIC_ONLY_PARAMETRIC_DECIMAL_FIXTURE_MATRIX__NO_EMPIRICAL_LEVERAGED_PNL",
        "historical_exchange_maintenance_tiers": "UNKNOWN",
        "historical_liquidation_engine_mark_parameters": "UNKNOWN",
        "scenario_count": len(scenarios),
        "grouped_denominators_and_counts": denominators,
        "scenarios": scenarios,
    }
