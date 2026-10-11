"""Deterministic synthetic margin, liquidation, stop-vs-liquidation clock, and denominator unit tests (>=50 cases).

Tests the independent pure-Decimal engine (`decimal_margin_engine.py`) and scenario reconciliation
(`reconcile_c_r1_scenarios.py`) across all 56 C R2 synthetic scenarios and all 32 C R1 scenarios.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from scripts.strategy_research.g2_goal_c_risk_assurance_r2 import C_R1_EVIDENCE_DIR
from scripts.strategy_research.g2_goal_c_risk_assurance_r2.decimal_margin_engine import (
    BPS_DIVISOR,
    COST_MODELS_DEC,
    compute_filtered_scenario_denominators,
    compute_stop_vs_liquidation_inequalities,
    dec_effective_price,
    solve_decimal_liquidation_price_and_move,
)
from scripts.strategy_research.g2_goal_c_risk_assurance_r2.reconcile_c_r1_scenarios import (
    build_c_r2_56_synthetic_margin_matrix,
    reconcile_c_r1_32_scenarios,
)

_C_R2_56_MATRIX = build_c_r2_56_synthetic_margin_matrix()
_C_R2_56_SCENARIOS = _C_R2_56_MATRIX["scenarios"]


@pytest.mark.parametrize(
    "scenario",
    _C_R2_56_SCENARIOS,
    ids=[s["scenario_id"] for s in _C_R2_56_SCENARIOS],
)
def test_c_r2_56_synthetic_margin_and_liquidation_scenarios(scenario: dict) -> None:
    """Verify conservation, strict M0=N/L margin, clock ordering, and deficit separation across 56 fixtures."""
    assert scenario["admitted"] is True
    sid = scenario["scenario_id"]
    lev = Decimal(str(scenario["leverage"]))
    notional = Decimal(str(scenario["initial_notional_usdt"]))
    strict_m0 = Decimal(str(scenario["strict_exchange_initial_margin_usdt"]))
    posted_m0 = Decimal(str(scenario["initial_margin_posted_usdt"]))
    disc_buf = Decimal(str(scenario["discretionary_margin_buffer_usdt"]))

    # 1. Strict exchange initial margin conservation: M_strict == N / L and M_posted == M_strict + B_disc
    assert abs(strict_m0 - (notional / lev)) <= Decimal("0.0002")
    assert abs(posted_m0 - (strict_m0 + disc_buf)) <= Decimal("0.0002")
    # In C R2's 56-scenario matrix, all sizing modes use strict M0 = N/L (zero hidden buffer)
    assert disc_buf == Decimal(0)

    # 2. Liquidation at shock occurs iff effective_margin_equity <= maintenance_margin_required
    eff_eq = Decimal(str(scenario["effective_margin_equity_at_shock_usdt"]))
    mm_req = Decimal(str(scenario["maintenance_margin_required_usdt"]))
    assert scenario["mark_liquidated_at_shock"] is (eff_eq <= mm_req)

    # 3. Group-specific invariants
    if sid.startswith("CR2_G1_"):
        # Group 1: 7.5% stop, 6.8% intrabar Mark move, 9.5% gap
        if scenario["leverage"] in (1.0, 5.0, 10.0):
            assert scenario["mark_liquidated_before_strategy_stop"] is False
        elif scenario["leverage"] == 15.0:
            # Under strict M0 = N/L, BOTH Naive and Risk-Capped 15x positions liquidate on a 6.8% Mark move!
            assert scenario["mark_liquidated_before_strategy_stop"] is True

    elif sid.startswith("CR2_G2_"):
        # Group 2: Real historical W1 max 1R stop (3.6120%)
        if sid.endswith("_NO_EXTRA_WICK"):
            # Without an intrabar Mark wick beyond 3.6120%, NEITHER 10x NOR 15x liquidates before the stop!
            assert scenario["mark_liquidated_before_strategy_stop"] is False
            assert (
                scenario["stop_vs_liquidation_clock_ordering"]
                == "STRATEGY_STOP_FIRST_BEFORE_LIQUIDATION_THRESHOLD"
            )
        elif sid.endswith("_INTRABAR_WICK_520BP"):
            if scenario["leverage"] == 15.0:
                # A 5.20% intrabar Mark wick triggers 15x liquidation (~4.95% threshold) even though 1m close is 3.50%!
                assert scenario["mark_liquidated_at_shock"] is True
                assert scenario["mark_liquidated_at_close"] is False
                assert (
                    scenario["stop_vs_liquidation_clock_ordering"]
                    == "INTRABAR_MARK_WICK_BREACHES_LIQUIDATION_WHILE_CLOSE_SAFE"
                )
            else:
                assert scenario["mark_liquidated_at_shock"] is False

    elif sid.startswith("CR2_G3_"):
        # Group 3: Post-TP1 partial quantity reduction (`open_qty < initial_qty`)
        assert scenario["open_qty_at_shock_btc"] < scenario["initial_qty_btc"]
        if sid.endswith("_TP1_ACKED"):
            # ACKed TP1 profit increases posted_margin_liq_adverse_move_pct compared to un-ACKed TP1
            peer_id = sid.replace("_TP1_ACKED", "_TP1_UNACKED")
            peer = next(x for x in _C_R2_56_SCENARIOS if x["scenario_id"] == peer_id)
            assert (
                scenario["posted_margin_liq_adverse_move_pct"]
                > peer["posted_margin_liq_adverse_move_pct"]
            )

    elif sid.startswith("CR2_G4_"):
        # Group 4: Funding timing and cancel-replace ACK latency race
        if sid.endswith("_CANCEL_REPLACE_RACE_FULL_QTY"):
            assert scenario["stop_exec_qty_btc"] == scenario["initial_qty_btc"]
            peer_id = sid.replace("_CANCEL_REPLACE_RACE_FULL_QTY", "_STOP_QTY_REDUCED")
            peer = next(x for x in _C_R2_56_SCENARIOS if x["scenario_id"] == peer_id)
            assert (
                scenario["total_account_equity_after_gap_usdt"]
                < peer["total_account_equity_after_gap_usdt"]
            )

    elif sid.startswith("CR2_G5_ISO_DEFICIT_POS_TOTAL_EQ_"):
        # Negative isolated collateral after 12% gap, but POSITIVE total account equity (> 900 USDT)
        assert scenario["isolated_collateral_bankrupt_after_gap"] is True
        assert scenario["isolated_margin_bankruptcy_deficit_usdt"] < 0.0
        assert scenario["account_insolvent_after_gap"] is False
        assert scenario["total_account_equity_after_gap_usdt"] > 900.0
        assert scenario["negative_isolated_but_positive_total_equity"] is True

    elif sid.startswith("CR2_G5_TOTAL_ACCOUNT_INSOLVENT_15X_"):
        assert scenario["isolated_collateral_bankrupt_after_gap"] is True
        assert scenario["account_insolvent_after_gap"] is True
        assert scenario["total_account_equity_after_gap_usdt"] < 0.0

    elif sid.startswith("CR2_G5_UNKNOWN_BRACKET_MMR_250BP_"):
        assert (
            scenario["historical_bracket_status"]
            == "UNKNOWN_HISTORICAL_BINANCE_BRACKET__SENSITIVITY_ONLY"
        )
        if scenario["leverage"] == 15.0:
            # With 250 bps MMR + 125 bps clearance + frictions (> 305.5 bps), 15x liquidates even at 3.50% move!
            assert scenario["mark_liquidated_before_strategy_stop"] is True


def test_closed_form_decimal_liquidation_price_exact_equality() -> None:
    """Prove `solve_decimal_liquidation_price_and_move` satisfies exact Decimal equality at `P_liq`."""
    cost = COST_MODELS_DEC["STRESS"]
    fee_frac = cost["fee_bps"] / BPS_DIVISOR
    adv_frac = (Decimal("0.5") * cost["spread_bps"] + cost["slip_bps"]) / BPS_DIVISOR
    clear_frac = Decimal("75.0") / BPS_DIVISOR
    entry_p = Decimal("30000.0")
    q = Decimal("0.500")

    for side in (1, -1):
        eff_e = dec_effective_price(entry_p, side, cost, is_entry=True)
        for lev in (Decimal(5), Decimal(10), Decimal(15)):
            for mmr in (Decimal("0.004"), Decimal("0.005"), Decimal("0.010")):
                wallet_m = (entry_p * q) / lev - (eff_e * q * fee_frac)
                p_liq, delta_p = solve_decimal_liquidation_price_and_move(
                    side=side,
                    entry_price=entry_p,
                    eff_entry=eff_e,
                    open_qty=q,
                    wallet_margin_balance=wallet_m,
                    fee_frac=fee_frac,
                    adverse_exec_frac=adv_frac,
                    mmr=mmr,
                    clear_frac=clear_frac,
                )
                # Verify P_liq == entry_p * (1 - side * delta_p)
                reconstructed_p_liq = entry_p * (Decimal(1) - Decimal(side) * delta_p)
                assert abs(p_liq - reconstructed_p_liq) < Decimal("1e-35")

                # Verify isolated Mark equity after exit fee buffer == maintenance margin at P_liq
                upnl = Decimal(side) * (p_liq - eff_e) * q
                exit_buf = q * p_liq * (fee_frac + adv_frac)
                iso_mark_eq = wallet_m + upnl - exit_buf
                mm_req = q * p_liq * (mmr + clear_frac)
                assert abs(iso_mark_eq - mm_req) < Decimal("1e-35")


def test_filtered_scenario_denominators_never_exceed_one_and_handle_empty() -> None:
    """Verify denominator helper enforces 0 <= X <= Y and returns UNKNOWN when Y == 0."""
    preds = {
        "non_empty_15x": lambda s: s["leverage"] == 15.0,
        "empty_20x": lambda s: s["leverage"] == 20.0,
    }
    res = compute_filtered_scenario_denominators(_C_R2_56_SCENARIOS, preds)
    assert res["non_empty_15x"]["denominator_n"] > 0
    for m_data in res["non_empty_15x"]["counts"].values():
        assert 0 <= m_data["numerator"] <= m_data["denominator"]
        assert m_data["fraction"] <= 1.0

    assert res["empty_20x"]["denominator_n"] == 0
    for m_data in res["empty_20x"]["counts"].values():
        assert m_data["ratio_str"] == "UNKNOWN"
        assert m_data["fraction"] is None


def test_stop_vs_liquidation_inequalities_falsify_c_r1_15x_string() -> None:
    """Prove 3.6120% W1 and 3.5591% W2 stops do NOT exceed 15x margin under 40-100 bps MMR."""
    ineq = compute_stop_vs_liquidation_inequalities()
    disp = ineq["c_r1_contradiction_2_disposition"]
    assert (
        disp["c_r1_machine_string_3_61pct_exceeds_15x_margin"]
        == "INVALID__MATHEMATICALLY_FALSE_UNDER_STANDARD_MMR"
    )
    assert disp["min_combined_nonprice_buffer_pct_to_liquidate_at_w1_max_3_6120pct_at_15x"] == pytest.approx(
        3.0547, abs=1e-4
    )

    rows_15x = [r for r in ineq["liquidation_threshold_grid"] if r["leverage"] == 15]
    assert len(rows_15x) == 6
    for r in rows_15x:
        # Under 40-100 bps MMR, adverse Mark move to liquidation is 4.31%..5.07% > 3.6120%
        assert 4.30 <= r["adverse_mark_move_to_liquidation_pct"] <= 5.10
        assert r["liquidates_at_w1_max_stop_3_6120pct_without_extra_wick"] is False
        assert r["liquidates_at_w2_max_stop_3_5591pct_without_extra_wick"] is False
        assert r["liquidates_before_synthetic_7_5000pct_stop"] is True
        assert r["headroom_above_w1_max_stop_pct"] > 0.69


def test_reconcile_c_r1_32_scenarios_exposes_7_over_10_and_strict_nl_flips() -> None:
    """Verify C R1's 32 scenarios have Y=10 for naive_10x_15x (5/10 and 7/10, not 5/6 and 7/6)."""
    recon = reconcile_c_r1_32_scenarios(C_R1_EVIDENCE_DIR)
    assert recon["scenario_count"] == 32
    assert recon["all_32_rows_booleans_exact_match"] is True
    assert recon["pure_decimal_formula_sizing_max_abs_diff"] == pytest.approx(30.0, abs=1e-4)
    assert len(recon["contradiction_3_root_cause_and_witness"]["float_lot_drift_scenario_ids"]) == 7

    d = recon["grouped_denominators_and_counts"]
    naive_f = d["naive_10x_15x_no_tp1_c_r1_filter"]
    assert naive_f["denominator_n"] == 10
    assert naive_f["counts"]["mark_liquidated_before_strategy_stop"]["ratio_str"] == "5/10"
    assert naive_f["counts"]["isolated_gap_bankruptcy_deficit"]["ratio_str"] == "7/10"

    loop1_f = d["naive_10x_15x_loop1_only_6_cases"]
    assert loop1_f["denominator_n"] == 6
    assert loop1_f["counts"]["mark_liquidated_before_strategy_stop"]["ratio_str"] == "3/6"
    assert loop1_f["counts"]["isolated_gap_bankruptcy_deficit"]["ratio_str"] == "3/6"

    capped_f = d["risk_capped_10x_15x_6_cases"]
    assert capped_f["denominator_n"] == 6
    assert capped_f["counts"]["mark_liquidated_before_strategy_stop"]["ratio_str"] == "0/6"
    assert capped_f["counts"]["strict_nl_liquidated_before_strategy_stop"]["ratio_str"] == "3/6"
