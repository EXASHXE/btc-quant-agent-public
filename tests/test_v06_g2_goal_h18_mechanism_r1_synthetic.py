"""Comprehensive deterministic synthetic tests for Gemini Goal B: H18 Mechanism."""
from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from scripts.strategy_research.g2_goal_h18_mechanism_r1.audit import (
    decimal_effective_price,
)
from scripts.strategy_research.g2_goal_h18_mechanism_r1.contract import (
    CANDIDATES,
    COST_MODELS,
    MIN_EVENTS_PER_STRATUM,
    SCHEMES,
    TASK_ID,
    get_frozen_contract_data,
    verify_contract_integrity,
)
from scripts.strategy_research.g2_goal_h18_mechanism_r1.decomposition import (
    aggregate_decomposition,
    decompose_contrast,
    decompose_trade,
)
from scripts.strategy_research.g2_goal_h18_mechanism_r1.opportunity import analyze_opportunity_cost
from scripts.strategy_research.g2_goal_h18_mechanism_r1.path_analysis import analyze_time_cap_strata
from scripts.strategy_research.g2_goal_h18_mechanism_r1.prospectus import (
    get_prospective_protocol_summary,
)
from scripts.strategy_research.g2_goal_h18_mechanism_r1.regimes import (
    calculate_effective_utc_weeks,
    extract_funding_regime,
    extract_side,
    extract_trend_alignment,
    extract_volatility_regime,
    extract_year,
    stratify_cohorts,
)
from scripts.strategy_research.g2_goal_h18_mechanism_r1.statistics import (
    block_bootstrap_contrasts,
)


# 1. Contract & Freeze Tests
def test_contract_integrity_and_immutability():
    data = get_frozen_contract_data()
    assert verify_contract_integrity(data)
    assert data["TASK_ID"] == TASK_ID
    assert data["new_configurable_exit_policies_authorized"] == 0
    assert set(data["candidates"]) == set(CANDIDATES)
    assert set(data["schemes"]) == set(SCHEMES)
    assert set(data["cost_models"]) == set(COST_MODELS)


# 2. Underpowered Bins Tests
def test_underpowered_bins_flagged():
    # Cohort with 5 events (< 10) must be flagged UNDERPOWERED
    events = [
        {"entry_at": 1620000000000 + i * 86400000, "delta_net_bps": 10.0, "labels": {"regime": "BIN_A"}}
        for i in range(5)
    ]
    strat = stratify_cohorts(events, "regime", min_events=MIN_EVENTS_PER_STRATUM)
    assert "BIN_A" in strat
    assert strat["BIN_A"]["underpowered"] is True
    assert strat["BIN_A"]["power_status"] == "UNDERPOWERED"
    assert strat["BIN_A"]["event_count"] == 5


def test_sufficient_power_bins_unflagged():
    # Cohort with 12 events (>= 10) must be flagged SUFFICIENT_SUPPORT
    events = [
        {"entry_at": 1620000000000 + i * 86400000, "delta_net_bps": 10.0, "labels": {"regime": "BIN_B"}}
        for i in range(12)
    ]
    strat = stratify_cohorts(events, "regime", min_events=MIN_EVENTS_PER_STRATUM)
    assert strat["BIN_B"]["underpowered"] is False
    assert strat["BIN_B"]["power_status"] == "SUFFICIENT_SUPPORT"
    assert strat["BIN_B"]["event_count"] == 12


# 3. Volatility Regime & Incomplete As-Of Window Tests
def test_incomplete_as_of_volatility_window():
    # Synthetic hourly bars with only 30 days of data (< 90 days required)
    n_bars = 30 * 24
    timestamps = np.arange(n_bars) * 3600000
    bars = np.column_stack([
        timestamps,
        np.full(n_bars, 50000.0),
        np.full(n_bars, 50500.0),
        np.full(n_bars, 49500.0),
        np.full(n_bars, 50000.0),
    ])
    entry_ms = int(timestamps[-1] + 3600000)
    label = extract_volatility_regime(bars, entry_ms, lookback_days=90)
    assert label == "INCOMPLETE_LOOKBACK"


def test_volatility_expanding_median_split():
    # Synthetic hourly bars with 100 days of data
    n_bars = 100 * 24
    timestamps = np.arange(n_bars) * 3600000
    # First 80 days low vol, last 20 days high vol
    highs = np.full(n_bars, 50100.0)
    lows = np.full(n_bars, 49900.0)
    highs[-100:] = 52000.0
    lows[-100:] = 48000.0
    bars = np.column_stack([
        timestamps,
        np.full(n_bars, 50000.0),
        highs,
        lows,
        np.full(n_bars, 50000.0),
    ])
    entry_ms = int(timestamps[-1] + 3600000)
    label = extract_volatility_regime(bars, entry_ms, lookback_days=90)
    assert label in ("HIGH_VOL", "LOW_VOL")


# 4. Causal As-Of Funding State Tests
def test_causal_funding_regime_no_future_leakage():
    signal_time = 1620000000000
    rates = [
        {"settlement_at": signal_time - 3600000, "rate": "0.00010000"},  # strictly prior: positive
        {"settlement_at": signal_time + 3600000, "rate": "-0.00050000"}, # future: negative (must be ignored!)
    ]
    label = extract_funding_regime(rates, signal_time)
    assert label == "POSITIVE"


def test_causal_funding_regime_unknown_when_empty():
    signal_time = 1620000000000
    rates = [
        {"settlement_at": signal_time + 3600000, "rate": "0.00010000"},
    ]
    label = extract_funding_regime(rates, signal_time)
    assert label == "UNKNOWN"


# 5. Causal 4h Trend Alignment Tests
def test_causal_4h_trend_alignment_long_bull():
    entry_ms = 4 * 3600 * 1000 + 60000
    # 241 1m bars from 0 to 4h
    timestamps = np.arange(241) * 60000
    # Price rises from 50000 to 51000
    prices = np.linspace(50000.0, 51000.0, 241)
    bars = np.column_stack([
        timestamps,
        prices,
        prices + 10,
        prices - 10,
        prices,
    ])
    lbl = extract_trend_alignment(bars, entry_ms, side=1)
    assert lbl == "TREND_ALIGNED"


def test_causal_4h_trend_alignment_long_bear():
    entry_ms = 4 * 3600 * 1000 + 60000
    timestamps = np.arange(241) * 60000
    prices = np.linspace(51000.0, 50000.0, 241)
    bars = np.column_stack([
        timestamps,
        prices,
        prices + 10,
        prices - 10,
        prices,
    ])
    lbl = extract_trend_alignment(bars, entry_ms, side=1)
    assert lbl == "COUNTERTREND"


def test_causal_4h_trend_alignment_short_bear():
    entry_ms = 4 * 3600 * 1000 + 60000
    timestamps = np.arange(241) * 60000
    prices = np.linspace(51000.0, 50000.0, 241)
    bars = np.column_stack([
        timestamps,
        prices,
        prices + 10,
        prices - 10,
        prices,
    ])
    lbl = extract_trend_alignment(bars, entry_ms, side=-1)
    assert lbl == "TREND_ALIGNED"


def test_causal_4h_trend_alignment_neutral():
    entry_ms = 4 * 3600 * 1000 + 60000
    timestamps = np.arange(241) * 60000
    prices = np.full(241, 50000.0)
    bars = np.column_stack([
        timestamps,
        prices,
        prices,
        prices,
        prices,
    ])
    lbl = extract_trend_alignment(bars, entry_ms, side=1)
    assert lbl == "NEUTRAL"


# 6. Sign & Quantity Tests
def test_sign_quantity_positive_long_pnl():
    trade = {
        "event_id": "TEST_LONG_1",
        "side": 1,
        "quantity": 0.02,
        "raw_entry": 50000.0,
        "raw_exit": 51000.0,
        "effective_entry": 50020.0,
        "effective_exit": 50980.0,
        "entry_notional": 1000.0,
        "funding_cash_usdt": "-0.10",
        "fee_entry": 1.20,
        "fee_exit": 1.22,
        "net_after_funding_usdt": str((50980.0 - 50020.0) * 0.02 - 0.10 - 1.20 - 1.22),
        "net_after_funding_bps": "166.8",
    }
    d = decompose_trade(trade)
    assert d["gross_price_pnl_usdt"] == pytest.approx(20.0)
    assert d["effective_price_pnl_usdt"] == pytest.approx(19.2)
    assert d["execution_drag_usdt"] == pytest.approx(0.8)


def test_sign_quantity_positive_short_pnl():
    trade = {
        "event_id": "TEST_SHORT_1",
        "side": -1,
        "quantity": 0.02,
        "raw_entry": 50000.0,
        "raw_exit": 49000.0,
        "effective_entry": 49980.0,
        "effective_exit": 49020.0,
        "entry_notional": 1000.0,
        "funding_cash_usdt": "0.15",
        "fee_entry": 1.20,
        "fee_exit": 1.18,
        "net_after_funding_usdt": str((-1) * (49020.0 - 49980.0) * 0.02 + 0.15 - 1.20 - 1.18),
        "net_after_funding_bps": "169.7",
    }
    d = decompose_trade(trade)
    assert d["gross_price_pnl_usdt"] == pytest.approx(20.0)
    assert d["effective_price_pnl_usdt"] == pytest.approx(19.2)


def test_funding_sign_convention_long_pays():
    # Long pays when funding rate is positive
    side = 1
    q = Decimal("0.02")
    mark = Decimal("50000.0")
    rate = Decimal("0.0001")
    cash = - Decimal(side) * q * mark * rate
    assert cash == Decimal("-0.1")


def test_funding_sign_convention_short_receives():
    # Short receives when funding rate is positive
    side = -1
    q = Decimal("0.02")
    mark = Decimal("50000.0")
    rate = Decimal("0.0001")
    cash = - Decimal(side) * q * mark * rate
    assert cash == Decimal("0.1")


# 7. Additive Decomposition Identities
def test_decomposition_additive_cash_identity():
    trade = {
        "event_id": "TEST_EV_1",
        "side": 1,
        "quantity": 0.015,
        "raw_entry": 40000.0,
        "raw_exit": 41000.0,
        "effective_entry": 40050.0,
        "effective_exit": 40950.0,
        "entry_notional": 600.0,
        "funding_cash_usdt": "0.50",
        "fee_entry": 0.72,
        "fee_exit": 0.74,
        "net_after_funding_usdt": str((40950.0 - 40050.0) * 0.015 + 0.50 - 0.72 - 0.74),
        "net_after_funding_bps": "209.0",
    }
    d = decompose_trade(trade)
    rec = d["effective_price_pnl_usdt"] + d["funding_cash_usdt"] - d["total_fees_usdt"]
    assert abs(rec - d["net_after_funding_usdt"]) < 1e-6


def test_decomposition_contrast_delta_identity():
    t_old = {
        "event_id": "EV_PAIR_1",
        "scheme": "E0",
        "side": 1,
        "quantity": 0.02,
        "raw_entry": 50000.0,
        "raw_exit": 50500.0,
        "effective_entry": 50020.0,
        "effective_exit": 50480.0,
        "entry_notional": 1000.0,
        "funding_cash_usdt": "0.0",
        "fee_entry": 1.20,
        "fee_exit": 1.21,
        "net_after_funding_usdt": "6.79",
        "net_after_funding_bps": "67.9",
        "gross_bps": "100.0",
    }
    t_new = {
        "event_id": "EV_PAIR_1",
        "scheme": "H1",
        "side": 1,
        "quantity": 0.02,
        "raw_entry": 50000.0,
        "raw_exit": 51500.0,
        "effective_entry": 50020.0,
        "effective_exit": 51480.0,
        "entry_notional": 1000.0,
        "funding_cash_usdt": "-0.20",
        "fee_entry": 1.20,
        "fee_exit": 1.24,
        "net_after_funding_usdt": "26.56",
        "net_after_funding_bps": "265.6",
        "gross_bps": "300.0",
    }
    c = decompose_contrast(t_new, t_old)
    rec_delta = c["delta_effective_price_usdt"] + c["delta_funding_usdt"] - c["delta_exit_fee_usdt"]
    assert abs(rec_delta - c["delta_net_usdt"]) < 1e-6


# 8. Decimal Tick Rounding Tests
def test_decimal_tick_rounding_entry_long():
    # Long entry: price moves upward (ceiling to nearest 0.1)
    raw = Decimal("50000.03")
    eff = decimal_effective_price(raw, side=1, spread_bps=Decimal("8.0"), slip_bps=Decimal("16.0"), is_entry=True)
    assert eff % Decimal("0.1") == Decimal(0)
    assert eff > raw


def test_decimal_tick_rounding_exit_long():
    # Long exit: price moves downward (floor to nearest 0.1)
    raw = Decimal("50000.07")
    eff = decimal_effective_price(raw, side=1, spread_bps=Decimal("8.0"), slip_bps=Decimal("16.0"), is_entry=False)
    assert eff % Decimal("0.1") == Decimal(0)
    assert eff < raw


def test_decimal_tick_rounding_entry_short():
    # Short entry: price moves downward (floor to nearest 0.1)
    raw = Decimal("50000.07")
    eff = decimal_effective_price(raw, side=-1, spread_bps=Decimal("8.0"), slip_bps=Decimal("16.0"), is_entry=True)
    assert eff % Decimal("0.1") == Decimal(0)
    assert eff < raw


def test_decimal_tick_rounding_exit_short():
    # Short exit: price moves upward (ceiling to nearest 0.1)
    raw = Decimal("50000.03")
    eff = decimal_effective_price(raw, side=-1, spread_bps=Decimal("8.0"), slip_bps=Decimal("16.0"), is_entry=False)
    assert eff % Decimal("0.1") == Decimal(0)
    assert eff > raw


# 9. Path Analysis & Time-Cap vs Early Exit Strata Tests
def test_time_cap_strata_early_exit_immutability():
    paired = [
        {
            "event_id": "EV_STOP_1",
            "baseline_time_cap": False,
            "cells": {
                "E0": {"exit_at": 1000, "net_after_funding_bps": "-150.0", "gross_bps": "-100.0", "funding_cash_usdt": "0", "fee_exit": 1.0, "exit_reason": "STOP"},
                "H1": {"exit_at": 1000, "net_after_funding_bps": "-150.0", "gross_bps": "-100.0", "funding_cash_usdt": "0", "fee_exit": 1.0, "exit_reason": "STOP"},
                "H2": {"exit_at": 1000, "net_after_funding_bps": "-150.0", "gross_bps": "-100.0", "funding_cash_usdt": "0", "fee_exit": 1.0, "exit_reason": "STOP"},
            },
        },
        {
            "event_id": "EV_TC_1",
            "baseline_time_cap": True,
            "cells": {
                "E0": {"exit_at": 1000, "net_after_funding_bps": "20.0", "gross_bps": "40.0", "funding_cash_usdt": "0", "fee_exit": 1.0, "exit_reason": "TIME_CAP"},
                "H1": {"exit_at": 2000, "net_after_funding_bps": "50.0", "gross_bps": "70.0", "funding_cash_usdt": "-0.1", "fee_exit": 1.1, "exit_reason": "TIME_CAP"},
                "H2": {"exit_at": 3000, "net_after_funding_bps": "40.0", "gross_bps": "60.0", "funding_cash_usdt": "-0.2", "fee_exit": 1.1, "exit_reason": "TIME_CAP"},
            },
            "path24h": {
                "before12h": {"Last_MFE_R": 1.0, "Last_MAE_R": -0.2, "Mark_MFE_R": 1.0, "Mark_MAE_R": -0.2},
                "12to18h": {"Last_MFE_R": 1.2, "Last_MAE_R": -0.1, "Mark_MFE_R": 1.1, "Mark_MAE_R": -0.1},
                "18to24h": {"Last_MFE_R": 0.8, "Last_MAE_R": -0.5, "Mark_MFE_R": 0.8, "Mark_MAE_R": -0.5},
            },
        },
    ]
    res = analyze_time_cap_strata(paired)
    assert res["early_exit_count"] == 1
    assert res["time_cap_count"] == 1
    assert res["early_exit_mutation_count"] == 0
    assert res["h1_12to18h"]["mean_delta_net_bps"] == pytest.approx(30.0)


# 10. Whole Account Opportunity Cost Tests
def test_opportunity_cost_identical_trade_set_detection():
    acc_e0 = {"accepted_event_ids": ["E1", "E2"], "metrics": {"mean_duration_minutes": 720.0, "trade_count": 2}}
    acc_h1 = {"accepted_event_ids": ["E1", "E2"], "occupied_minutes": 2160, "skipped_signal_fates": [{"event_id": "E1_BURST_1", "reason": "POSITION_ACK_OR_COOLDOWN"}]}
    acc_h2 = {"accepted_event_ids": ["E1", "E2"], "occupied_minutes": 2880, "skipped_signal_fates": [{"event_id": "E1_BURST_1", "reason": "POSITION_ACK_OR_COOLDOWN"}]}
    res = analyze_opportunity_cost(acc_e0, acc_h1, acc_h2, "CAND_1", "STRESS")
    assert res["event_set_equivalence"]["h1_matches_e0_exactly"] is True
    assert res["event_set_equivalence"]["h2_matches_e0_exactly"] is True
    assert res["signal_collisions"]["blocked_in_12_to_18h_window"] == 0


# 11. Determinism & Bootstrap Tests
def test_bootstrap_determinism_with_seed():
    reg = [
        ("C1:H1-E0", [{"entry_at": 1620000000000 + i * 86400000 * 10, "delta_bps": 20.0 + i} for i in range(15)]),
        ("C1:H2-E0", [{"entry_at": 1620000000000 + i * 86400000 * 10, "delta_bps": 15.0 + i} for i in range(15)]),
    ]
    r1 = block_bootstrap_contrasts(reg, block_days=14, draws=1000, seed=42)
    r2 = block_bootstrap_contrasts(reg, block_days=14, draws=1000, seed=42)
    assert r1["critical_95_max_t"] == pytest.approx(r2["critical_95_max_t"])
    assert r1["contrasts"][0]["bootstrap_se_bps"] == pytest.approx(r2["contrasts"][0]["bootstrap_se_bps"])


def test_bootstrap_zero_trade_blocks_retained():
    # 10 trades spaced by 30 days across 3 years will have many zero trade blocks
    reg = [
        ("C1:H1-E0", [
            {"entry_at": 1620000000000 + i * 30 * 86400000, "delta_bps": 25.0 + i}
            for i in range(10)
        ]),
    ]
    res = block_bootstrap_contrasts(reg, block_days=14, draws=500, seed=42)
    contrast_res = res["contrasts"][0]
    assert contrast_res["zero_trade_blocks"] > 60
    assert contrast_res["total_calendar_blocks"] > 70


# 12. Helper Function Tests
def test_effective_utc_weeks_calculation():
    # Two timestamps in the same ISO week
    ts1 = 1620000000000  # Monday May 3, 2021
    ts2 = 1620100000000  # Tuesday May 4, 2021
    assert calculate_effective_utc_weeks([ts1, ts2]) == 1

    # Two timestamps in different ISO weeks
    ts3 = ts1 + 7 * 86400000  # next week
    assert calculate_effective_utc_weeks([ts1, ts3]) == 2


def test_extract_year_and_side():
    ts = 1620000000000  # 2021
    assert extract_year(ts) == "2021"
    assert extract_side(1) == "LONG"
    assert extract_side(-1) == "SHORT"
    with pytest.raises(ValueError):
        extract_side(0)


def test_prospective_protocol_summary_non_executed():
    proto = get_prospective_protocol_summary()
    assert proto["new_selectable_policies_executed_now"] == 0
    assert proto["controller_gate_required"] is True
    assert proto["D1_conditional_extension"]["status"] == "DESIGN_ONLY_NON_EXECUTED"
    assert proto["D2_atr_trailing"]["status"] == "DESIGN_ONLY_NON_EXECUTED"


def test_aggregate_decomposition_empty():
    agg = aggregate_decomposition([])
    assert agg["count"] == 0
    assert agg["mean_delta_net_bps"] == 0.0
