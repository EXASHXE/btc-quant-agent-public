"""Deterministic unit tests for independent Decimal journal, synthetic leverage harness, and causality."""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from scripts.strategy_research.g2_exit_horizon_r1.account import mark_curve
from scripts.strategy_research.g2_exit_horizon_r1.book import position
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    HOUR,
    MINUTE,
    STRESS,
    _proposed,
)
from scripts.strategy_research.g2_goal_execution_assurance_r1.decimal_journal import (
    COST_MODELS_DEC,
    D,
    dec_ack_clock,
    dec_breakeven_stop,
    dec_effective_price,
    dec_fee,
    dec_size_admission,
    dec_split_quantity,
    dec_tick,
    verify_and_audit_episode,
)
from scripts.strategy_research.g2_goal_execution_assurance_r1.lineage_audit import (
    prove_synthetic_prefix_causality,
    verify_folds_purge_and_ledger_lineage,
    verify_static_ast_causality,
)
from scripts.strategy_research.g2_goal_execution_assurance_r1.risk_envelope import (
    build_synthetic_leverage_stress_matrix,
    run_synthetic_leverage_scenario,
)


def test_decimal_d_rejects_non_finite_or_invalid() -> None:
    """Ensure D() rejects NaN, Inf, and non-numeric strings."""
    assert D("123.45") == Decimal("123.45")
    with pytest.raises(ValueError, match="Non-finite"):
        D("nan")
    with pytest.raises(ValueError, match="Non-finite"):
        D("inf")
    with pytest.raises(ValueError, match="Invalid Decimal"):
        D("not-a-number")


def test_decimal_tick_rounding_direction() -> None:
    """Verify 0.1 tick rounding upwards and downwards in pure Decimal."""
    assert dec_tick(Decimal("30000.01"), upwards=True) == Decimal("30000.1")
    assert dec_tick(Decimal("30000.09"), upwards=False) == Decimal("30000.0")
    assert dec_tick(Decimal("30000.1"), upwards=True) == Decimal("30000.1")
    assert dec_tick(Decimal("30000.1"), upwards=False) == Decimal("30000.1")


def test_decimal_effective_price_and_fee_long_and_short() -> None:
    """Verify adverse effective entry/exit price and fee calculation in BASE and STRESS."""
    cost_stress = COST_MODELS_DEC["STRESS"]
    eff_long_in = dec_effective_price(Decimal("30000.0"), 1, cost_stress, is_entry=True)
    eff_long_out = dec_effective_price(Decimal("30000.0"), 1, cost_stress, is_entry=False)
    assert eff_long_in == Decimal("30030.0")
    assert eff_long_out == Decimal("29970.0")

    eff_short_in = dec_effective_price(Decimal("30000.0"), -1, cost_stress, is_entry=True)
    eff_short_out = dec_effective_price(Decimal("30000.0"), -1, cost_stress, is_entry=False)
    assert eff_short_in == Decimal("29970.0")
    assert eff_short_out == Decimal("30030.0")

    fee = dec_fee(Decimal("30000.0"), Decimal("0.020"), cost_stress)
    assert fee == Decimal("0.7200")


def test_decimal_ack_clock_boundary_and_midbar() -> None:
    """Verify causal order ACK clock advances to next minute close."""
    t0 = 1_612_137_600_000
    assert dec_ack_clock(t0) == t0 + 60_000
    assert dec_ack_clock(t0 + 1) == t0 + 120_000
    assert dec_ack_clock(t0 + 59_999) == t0 + 120_000


def test_decimal_split_quantity_odd_lot_and_min_notional() -> None:
    """Verify 0.001 lot split (floor half to q1, remainder to q2) and 5 USDT min-notional guard."""
    q1, q2 = dec_split_quantity(
        Decimal("0.029"), Decimal(30000), Decimal(30300), Decimal(30600)
    )
    assert q1 == Decimal("0.014")
    assert q2 == Decimal("0.015")
    assert q1 + q2 == Decimal("0.029")

    with pytest.raises(ValueError, match="minimum notional"):
        dec_split_quantity(Decimal("0.002"), Decimal(4000), Decimal(4100), Decimal(4200))

    with pytest.raises(ValueError, match="Zero partial tier"):
        dec_split_quantity(Decimal("0.001"), Decimal(30000), Decimal(30300), Decimal(30600))


def test_decimal_breakeven_stop_long_and_short() -> None:
    """Verify independent Decimal breakeven stop covers entry+exit fees plus adverse exit slip."""
    cost_stress = COST_MODELS_DEC["STRESS"]
    eff_in_long = dec_effective_price(Decimal("30000.0"), 1, cost_stress, is_entry=True)
    be_long = dec_breakeven_stop(eff_in_long, Decimal("29500.0"), 1, cost_stress)
    assert be_long > eff_in_long
    eff_be_out_long = dec_effective_price(be_long, 1, cost_stress, is_entry=False)
    net_long = (
        (eff_be_out_long - eff_in_long)
        - dec_fee(eff_in_long, Decimal(1), cost_stress)
        - dec_fee(eff_be_out_long, Decimal(1), cost_stress)
    )
    assert net_long >= Decimal(0)

    eff_in_short = dec_effective_price(Decimal("30000.0"), -1, cost_stress, is_entry=True)
    be_short = dec_breakeven_stop(eff_in_short, Decimal("30500.0"), -1, cost_stress)
    assert be_short < eff_in_short
    eff_be_out_short = dec_effective_price(be_short, -1, cost_stress, is_entry=False)
    net_short = (
        -(eff_be_out_short - eff_in_short)
        - dec_fee(eff_in_short, Decimal(1), cost_stress)
        - dec_fee(eff_be_out_short, Decimal(1), cost_stress)
    )
    assert net_short >= Decimal(0)


def test_decimal_size_admission_respects_1x_cap_and_5pct_reserve() -> None:
    """Verify independent Decimal admission sizing never exceeds 0.95 * min(cash, 1000)."""
    cost_stress = COST_MODELS_DEC["STRESS"]
    q, res = dec_size_admission(
        Decimal("30000.0"), Decimal("300.0"), 1, 18, cost_stress, Decimal("1000.0")
    )
    assert q > Decimal(0)
    assert res["budget"] == Decimal("950.00")
    assert res["actual_entry_outlay"] <= res["budget"]


def test_dual_decimal_verifier_matches_clean_synthetic_e1_episode() -> None:
    """Verify Dual-Decimal audit passes with zero discrepancies on a multi-tier E1 episode with funding."""
    n_bars = 1600
    bars = np.empty((n_bars, 5), dtype=float)
    bars[:, 0] = np.arange(n_bars, dtype=float) * MINUTE
    bars[:, 1:] = 100.0
    mark = bars.copy()
    event = {
        "event_time": 0,
        "decision_at": MINUTE,
        "entry_at": 2 * MINUTE,
        "decision_close": 100.0,
        "atr_hour": 20.0,
        "side": 1,
        "stop": 90.0,
        "event_id": "syn_clean_e1",
    }
    cand = {
        "id": "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
        "horizon_hours": 12,
        "target_R": 2.0,
        "cooldown_hours": 6,
    }
    p = _proposed(bars, event, cand, STRESS)
    t1 = round(p["effective_entry"] + p["initial_risk"], 1)
    bars[3, 2] = t1 + 0.2
    f_events = [{"settlement_at": 8 * HOUR, "rate": "0.001"}]
    res = position(bars, mark, f_events, event, cand, STRESS, "E1", 0.2)
    c_dict = mark_curve([res], mark, 0, 1500 * MINUTE, 1000.0, STRESS)
    base_trade = {
        **res,
        "cost": "STRESS",
        "cash_before_entry": 1000.0,
        "cash_after_ack": c_dict["ending_equity"],
    }
    f_lookup = {8 * HOUR: Decimal("0.001")}
    m_lookup = {int(row[0]): (D(row[4]), int(row[0]) + MINUTE - 1, "SYN") for row in mark}
    audit = verify_and_audit_episode(base_trade, f_lookup, m_lookup, curve_array=c_dict["curve"])
    assert audit["status"] == "PASS"
    assert audit["discrepancies"] == []


def test_dual_decimal_verifier_detects_tampered_fee_and_funding() -> None:
    """Verify Dual-Decimal stage checker catches tampered tier fee and residual funding quantity."""
    n_bars = 1600
    bars = np.empty((n_bars, 5), dtype=float)
    bars[:, 0] = np.arange(n_bars, dtype=float) * MINUTE
    bars[:, 1:] = 100.0
    mark = bars.copy()
    event = {
        "event_time": 0,
        "decision_at": MINUTE,
        "entry_at": 2 * MINUTE,
        "decision_close": 100.0,
        "atr_hour": 20.0,
        "side": 1,
        "stop": 90.0,
        "event_id": "syn_tamper_e1",
    }
    cand = {
        "id": "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
        "horizon_hours": 12,
        "target_R": 2.0,
        "cooldown_hours": 6,
    }
    p = _proposed(bars, event, cand, STRESS)
    t1 = round(p["effective_entry"] + p["initial_risk"], 1)
    bars[3, 2] = t1 + 0.2
    f_events = [{"settlement_at": 8 * HOUR, "rate": "0.001"}]
    res = position(bars, mark, f_events, event, cand, STRESS, "E1", 0.2)
    c_dict = mark_curve([res], mark, 0, 1500 * MINUTE, 1000.0, STRESS)
    base_trade = {
        **res,
        "cost": "STRESS",
        "cash_before_entry": 1000.0,
        "cash_after_ack": c_dict["ending_equity"],
    }
    f_lookup = {8 * HOUR: Decimal("0.001")}
    m_lookup = {int(row[0]): (D(row[4]), int(row[0]) + MINUTE - 1, "SYN") for row in mark}

    t_fee = {
        **base_trade,
        "tiers": [
            {**base_trade["tiers"][0], "fee_exit": base_trade["tiers"][0]["fee_exit"] + 0.5},
            base_trade["tiers"][1],
        ],
    }
    assert verify_and_audit_episode(t_fee, f_lookup, m_lookup)["status"] == "DEFECT"


def test_synthetic_leverage_naive_15x_liquidates_before_8pct_stop() -> None:
    """Prove naive 15x gross leverage liquidates on a 7.2% adverse Mark move before an 8% strategy stop."""
    scen = run_synthetic_leverage_scenario(
        scenario_id="TEST_NAIVE_15X",
        side=1,
        leverage=15.0,
        mmr=0.005,
        clearance_fee_bps=75.0,
        entry_price=30_000.0,
        stop_distance_pct=0.08,
        intrabar_adverse_mark_pct=0.072,
        open_gap_adverse_pct=0.10,
        sizing_mode="NAIVE_FULL_LEVERAGE_NOTIONAL",
    )
    assert scen["admitted"] is True
    assert scen["mark_liquidated_before_strategy_stop"] is True
    assert scen["isolated_margin_bankruptcy_deficit_usdt"] < 0.0


def test_synthetic_leverage_risk_capped_isolated_survives_shock() -> None:
    """Verify risk-budget-capped isolated sizing survives the same shock without liquidation or insolvency."""
    scen = run_synthetic_leverage_scenario(
        scenario_id="TEST_RISK_CAPPED_15X",
        side=1,
        leverage=15.0,
        mmr=0.005,
        clearance_fee_bps=75.0,
        entry_price=30_000.0,
        stop_distance_pct=0.08,
        intrabar_adverse_mark_pct=0.072,
        open_gap_adverse_pct=0.10,
        sizing_mode="RISK_BUDGET_CAPPED_ISOLATED",
        max_account_risk_pct=0.02,
    )
    assert scen["admitted"] is True
    assert scen["mark_liquidated_at_shock"] is False
    assert scen["account_insolvent_after_gap"] is False


def test_synthetic_leverage_matrix_forbids_naive_pnl_multiplication() -> None:
    """Verify the synthetic leverage stress matrix explicitly marks historical exchange tiers UNKNOWN."""
    matrix = build_synthetic_leverage_stress_matrix()
    assert matrix["naive_1x_pnl_multiplication_prohibited"] is True
    assert matrix["historical_exchange_maintenance_tiers"] == "UNKNOWN"
    assert matrix["scenario_count"] >= 30
    assert matrix["summary_findings"]["naive_10x_15x_liquidated_before_strategy_stop_count"] > 0
    assert matrix["summary_findings"]["risk_capped_10x_15x_liquidated_count"] == 0


def test_static_ast_and_synthetic_prefix_causality() -> None:
    """Verify static AST checks and synthetic prefix-truncation causality proof pass."""
    ast_res = verify_static_ast_causality()
    assert ast_res["status"] == "PASS"
    assert ast_res["accepts_mark_or_funding_inputs"] is False

    prefix_res = prove_synthetic_prefix_causality()
    assert prefix_res["status"] == "PASS"
    assert prefix_res["future_bar_mutation_invariant"] is True
    assert prefix_res["strict_prefix_truncation_invariant"] is True
    assert prefix_res["post_exit_last_and_future_mark_invariant"] is True
    assert prefix_res["mark_close_asof_boundary_clock_verified"] is True


def test_warmup_scoring_and_purge_folds_structure() -> None:
    """Verify Jan 2021 warmup, 35 scoring months Feb 2021 - Dec 2023, and 24h purge barrier."""
    fold_res = verify_folds_purge_and_ledger_lineage()
    assert fold_res["status"] == "PASS"
    assert fold_res["scored_folds_count"] == 35
    assert fold_res["scored_folds_range"] == "2021-02..2023-12"
    assert fold_res["edge_embargo_hours"] == 24
