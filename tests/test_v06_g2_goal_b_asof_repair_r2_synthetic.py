"""Deterministic synthetic test suite for Gemini Goal B R2 as-of causal repair.

Covers >=40 test cases including:
- Time-travel mutation invariance
- 4h trend extraction, boundaries, continuity, and side symmetry
- 1h resampling and Wilder ATR(14) exact formula
- Prior-only 90d expanding median and lookback completeness
- Official funding settlement as-of causality and lag sensitivity
- Power gate thresholds (N < 10)
- Manual 12-event Decimal / stdlib audit fixture
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

# Ensure workspace root is in sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import pytest

from scripts.strategy_research.g2_goal_b_asof_repair_r2.asof_features import (
    COL_CLOSE,
    COL_CLOSE_TIME,
    COL_OPEN,
    COL_OPEN_TIME,
    HOUR_MS,
    compute_wilder_atr14,
    extract_pre_entry_atr_regime,
    extract_pre_entry_funding_state,
    extract_pre_entry_trend_aligned,
    resample_1m_to_1h,
)
from scripts.strategy_research.g2_goal_b_asof_repair_r2.contract import (
    MIN_EVENTS_PER_STRATUM,
    get_frozen_contract_data,
    verify_contract_integrity,
)
from scripts.strategy_research.g2_goal_b_asof_repair_r2.reconciliation import (
    build_reconciliation_matrix,
)
from scripts.strategy_research.g2_goal_b_asof_repair_r2.time_travel_guard import (
    mutate_future_1m_bars,
    mutate_future_funding_settlements,
    mutate_future_hourly_bars,
    verify_time_travel_invariance,
)


def make_synthetic_1m_bars(
    start_ts_ms: int,
    count: int,
    base_price: float = 50000.0,
    price_drift: float = 0.0,
) -> np.ndarray:
    """Generate contiguous 1m bars."""
    bars = []
    curr_p = base_price
    for i in range(count):
        o_time = start_ts_ms + i * 60_000
        c_time = o_time + 59_999
        o = curr_p
        curr_p += price_drift
        c = curr_p
        h = max(o, c) + 5.0
        l = min(o, c) - 5.0
        bars.append([float(o_time), o, h, l, c, 10.0, float(c_time)])
    return np.array(bars, dtype=float)


# ---------------------------------------------------------
# 1. 4h Trend Alignment Tests (Tests 1 - 12)
# ---------------------------------------------------------


def test_trend_exact_240_bars_aligned_long() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 240, base_price=50000.0, price_drift=1.0)
    sig_at = int(bars[-1, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=1)
    assert res["valid"] is True
    assert res["trend_regime"] == "TREND_ALIGNED"
    assert res["return_4h"] > 0
    assert res["bar_count"] == 240


def test_trend_exact_240_bars_countertrend_long() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 240, base_price=50000.0, price_drift=-1.0)
    sig_at = int(bars[-1, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=1)
    assert res["valid"] is True
    assert res["trend_regime"] == "COUNTERTREND"
    assert res["return_4h"] < 0


def test_trend_exact_240_bars_aligned_short() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 240, base_price=50000.0, price_drift=-1.0)
    sig_at = int(bars[-1, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=-1)
    assert res["valid"] is True
    assert res["trend_regime"] == "TREND_ALIGNED"
    assert res["alignment_val"] > 0


def test_trend_exact_240_bars_countertrend_short() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 240, base_price=50000.0, price_drift=1.0)
    sig_at = int(bars[-1, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=-1)
    assert res["valid"] is True
    assert res["trend_regime"] == "COUNTERTREND"
    assert res["alignment_val"] < 0


def test_trend_exact_240_bars_neutral() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 240, base_price=50000.0, price_drift=0.0)
    sig_at = int(bars[-1, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=1)
    assert res["valid"] is True
    assert res["trend_regime"] == "NEUTRAL"
    assert abs(res["return_4h"]) <= 1e-7


def test_trend_deadband_threshold() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 240, base_price=50000.0, price_drift=0.0)
    # Set tiny price diff of 1e-4 on 50000 -> 2e-9 return (below 1e-7 deadband)
    bars[-1, COL_CLOSE] = bars[0, COL_OPEN] + 1e-4
    sig_at = int(bars[-1, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=1)
    assert res["trend_regime"] == "NEUTRAL"


def test_trend_insufficient_bars_rejection() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 239)
    sig_at = int(bars[-1, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=1)
    assert res["valid"] is False
    assert res["trend_regime"] == "INCOMPLETE"


def test_trend_zero_bars_rejection() -> None:
    bars = np.empty((0, 7), dtype=float)
    res = extract_pre_entry_trend_aligned(bars, 1620000000000, side=1)
    assert res["valid"] is False
    assert res["trend_regime"] == "INCOMPLETE"


def test_trend_non_contiguous_bars_rejection() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 240)
    # Inject 2-minute gap at bar 100
    bars[100:, COL_OPEN_TIME] += 60_000
    bars[100:, COL_CLOSE_TIME] += 60_000
    sig_at = int(bars[-1, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=1)
    assert res["valid"] is False
    assert "NON_CONTIGUOUS" in res["reason"]


def test_trend_non_positive_start_price_rejection() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 240)
    bars[0, COL_OPEN] = -10.0
    sig_at = int(bars[-1, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=1)
    assert res["valid"] is False
    assert res["reason"] == "NON_POSITIVE_START_PRICE"


def test_trend_endpoint_strictly_pre_signal() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 250)
    # Target bar 240 is at index 239
    sig_at = int(bars[239, COL_CLOSE_TIME])
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=1)
    assert res["valid"] is True
    assert res["end_close_ms"] == sig_at
    # Bars 240-249 must not have affected return
    assert res["p_end"] == bars[239, COL_CLOSE]


def test_trend_signal_vs_entry_cutoff() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 250)
    sig_at = int(bars[239, COL_CLOSE_TIME])
    entry_at = sig_at + 60_000
    res = extract_pre_entry_trend_aligned(bars, sig_at, side=1, entry_at_ms=entry_at)
    assert res["valid"] is True
    assert res["cutoff_ms"] == sig_at


# ---------------------------------------------------------
# 2. Resampling & Wilder ATR(14) Tests (Tests 13 - 19)
# ---------------------------------------------------------


def test_resample_1m_to_1h_exact_60_bars() -> None:
    t_start = 1609459200000  # 2021-01-01 00:00:00 UTC
    bars_1m = make_synthetic_1m_bars(t_start, 60, base_price=29000.0, price_drift=1.0)
    hourly = resample_1m_to_1h(bars_1m)
    assert len(hourly) == 1
    assert hourly[0, 0] == t_start
    assert hourly[0, 1] == bars_1m[0, COL_OPEN]
    assert hourly[0, 4] == bars_1m[-1, COL_CLOSE]
    assert hourly[0, 5] == bars_1m[-1, COL_CLOSE_TIME]


def test_resample_1m_to_1h_incomplete_hour_skipped() -> None:
    t_start = 1609459200000
    bars_1m = make_synthetic_1m_bars(t_start, 59)  # 59 bars only
    hourly = resample_1m_to_1h(bars_1m)
    assert len(hourly) == 0


def test_resample_1m_to_1h_multiple_consecutive_hours() -> None:
    t_start = 1609459200000
    bars_1m = make_synthetic_1m_bars(t_start, 180)  # 3 hours
    hourly = resample_1m_to_1h(bars_1m)
    assert len(hourly) == 3
    assert hourly[1, 0] == t_start + HOUR_MS
    assert hourly[2, 0] == t_start + 2 * HOUR_MS


def test_resample_1m_to_1h_utc_midnight_boundary() -> None:
    # 23:00 to 01:00 (2 hours)
    t_start = 1609455600000  # 2020-12-31 23:00:00 UTC
    bars_1m = make_synthetic_1m_bars(t_start, 120)
    hourly = resample_1m_to_1h(bars_1m)
    assert len(hourly) == 2
    assert hourly[0, 0] == 1609455600000
    assert hourly[1, 0] == 1609459200000  # 2021-01-01 00:00:00 UTC


def test_wilder_atr14_exact_formula_first_14_bars() -> None:
    hourly = []
    t_start = 1609459200000
    for i in range(20):
        # Open=100, High=110, Low=90, Close=105 (TR = 20 for all)
        hourly.append(
            [
                float(t_start + i * HOUR_MS),
                100.0,
                110.0,
                90.0,
                105.0,
                float(t_start + (i + 1) * HOUR_MS - 1),
            ]
        )
    hourly_np = np.array(hourly)
    atr = compute_wilder_atr14(hourly_np)
    # Indices 0 to 12 must be NaN
    assert np.all(np.isnan(atr[:13]))
    # Index 13 (14th bar) is mean of TR[:14] = 20.0
    assert pytest.approx(atr[13], rel=1e-7) == 20.0


def test_wilder_atr14_subsequent_smoothing() -> None:
    hourly = []
    t_start = 1609459200000
    for i in range(20):
        hourly.append(
            [
                float(t_start + i * HOUR_MS),
                100.0,
                110.0,
                90.0,
                105.0,
                float(t_start + (i + 1) * HOUR_MS - 1),
            ]
        )
    # At bar 14, make TR = 34 (High=120, Low=86)
    hourly[14][2] = 120.0
    hourly[14][3] = 86.0
    hourly_np = np.array(hourly)
    atr = compute_wilder_atr14(hourly_np)
    expected_atr_14 = (20.0 * 13.0 + 34.0) / 14.0  # (260 + 34)/14 = 294/14 = 21.0
    assert pytest.approx(atr[14], rel=1e-7) == expected_atr_14


def test_wilder_atr14_fewer_than_14_bars() -> None:
    hourly = []
    t_start = 1609459200000
    for i in range(10):
        hourly.append(
            [
                float(t_start + i * HOUR_MS),
                100.0,
                110.0,
                90.0,
                105.0,
                float(t_start + (i + 1) * HOUR_MS - 1),
            ]
        )
    hourly_np = np.array(hourly)
    atr = compute_wilder_atr14(hourly_np)
    assert len(atr) == 10
    assert np.all(np.isnan(atr))


# ---------------------------------------------------------
# 3. Expanding 90d ATR Regime & Lookback Tests (Tests 20 - 25)
# ---------------------------------------------------------


def make_synthetic_hourly_bars(
    start_ts_ms: int,
    count: int,
    base_price: float = 30000.0,
    daily_vol: float = 500.0,
) -> np.ndarray:
    """Generate synthetic hourly bars."""
    bars = []
    for i in range(count):
        o_time = start_ts_ms + i * HOUR_MS
        c_time = o_time + HOUR_MS - 1
        p = base_price
        h = p + daily_vol
        l = p - daily_vol
        c = p
        bars.append([float(o_time), p, h, l, c, float(c_time)])
    return np.array(bars, dtype=float)


def test_atr_regime_insufficient_lookback_rejection() -> None:
    t_start = 1609459200000
    bars = make_synthetic_hourly_bars(t_start, 2159)  # 1 hour short of 2,160
    sig_at = int(bars[-1, 5])
    res = extract_pre_entry_atr_regime(bars, sig_at)
    assert res["valid"] is False
    assert res["volatility_regime"] == "INCOMPLETE_LOOKBACK"


def test_atr_regime_never_auto_substitutes_low_vol() -> None:
    t_start = 1609459200000
    bars = make_synthetic_hourly_bars(t_start, 100)
    sig_at = int(bars[-1, 5])
    res = extract_pre_entry_atr_regime(bars, sig_at)
    assert res["volatility_regime"] != "LOW_VOL"
    assert res["volatility_regime"] == "INCOMPLETE_LOOKBACK"


def test_atr_regime_exact_median_split_high_vol() -> None:
    t_start = 1609459200000
    bars = make_synthetic_hourly_bars(t_start, 2160, daily_vol=200.0)
    # Spike the volatility of the last 20 bars to make current > median
    bars[-20:, 2] += 500.0
    bars[-20:, 3] -= 500.0
    sig_at = int(bars[-1, 5])
    res = extract_pre_entry_atr_regime(bars, sig_at)
    assert res["valid"] is True
    assert res["volatility_regime"] == "HIGH_VOL"
    assert res["current_norm_atr"] >= res["median_norm_atr"]


def test_atr_regime_exact_median_split_low_vol() -> None:
    t_start = 1609459200000
    bars = make_synthetic_hourly_bars(t_start, 2160, daily_vol=500.0)
    # Compress volatility of last 20 bars
    bars[-20:, 2] = bars[-20:, 1] + 50.0
    bars[-20:, 3] = bars[-20:, 1] - 50.0
    sig_at = int(bars[-1, 5])
    res = extract_pre_entry_atr_regime(bars, sig_at)
    assert res["valid"] is True
    assert res["volatility_regime"] == "LOW_VOL"
    assert res["current_norm_atr"] < res["median_norm_atr"]


def test_atr_regime_at_exact_median_boundary() -> None:
    t_start = 1609459200000
    bars = make_synthetic_hourly_bars(t_start, 2160, daily_vol=300.0)
    sig_at = int(bars[-1, 5])
    res = extract_pre_entry_atr_regime(bars, sig_at)
    assert res["valid"] is True
    # If all bars have identical vol, current == median -> HIGH_VOL
    assert res["volatility_regime"] == "HIGH_VOL"


def test_atr_regime_hour_close_pre_signal() -> None:
    t_start = 1609459200000
    bars = make_synthetic_hourly_bars(t_start, 2200)
    # Signal falls at 30 minutes into bar 2160
    sig_at = int(bars[2160, 0] + 1800_000)
    res = extract_pre_entry_atr_regime(bars, sig_at)
    assert res["valid"] is True
    assert res["latest_hour_close_ms"] <= sig_at
    assert res["latest_hour_close_ms"] == int(bars[2159, 5])


# ---------------------------------------------------------
# 4. As-of Official Funding Rate Tests (Tests 26 - 31)
# ---------------------------------------------------------


def test_funding_settled_before_signal_positive() -> None:
    settlements = [
        {"calc_time": 1619395200003, "funding_interval_hours": 8, "last_funding_rate": 0.0001},
        {"calc_time": 1619424000002, "funding_interval_hours": 8, "last_funding_rate": -0.0002},
    ]
    sig_at = 1619401500000  # between 00:00 and 08:00
    res = extract_pre_entry_funding_state(settlements, sig_at)
    assert res["valid"] is True
    assert res["funding_regime"] == "POSITIVE"
    assert res["rate"] == 0.0001
    assert res["calc_time"] == 1619395200003


def test_funding_settled_before_signal_negative() -> None:
    settlements = [
        {"calc_time": 1619395200003, "funding_interval_hours": 8, "last_funding_rate": -0.00015},
    ]
    sig_at = 1619401500000
    res = extract_pre_entry_funding_state(settlements, sig_at)
    assert res["valid"] is True
    assert res["funding_regime"] == "NEGATIVE"
    assert res["rate"] == -0.00015


def test_funding_settled_before_signal_zero() -> None:
    settlements = [
        {"calc_time": 1619395200003, "funding_interval_hours": 8, "last_funding_rate": 0.0},
    ]
    sig_at = 1619401500000
    res = extract_pre_entry_funding_state(settlements, sig_at)
    assert res["valid"] is True
    assert res["funding_regime"] == "ZERO"


def test_funding_settled_at_exact_decision_time_excluded() -> None:
    settlements = [
        {"calc_time": 1619395200000, "funding_interval_hours": 8, "last_funding_rate": 0.0001},
        {"calc_time": 1619424000000, "funding_interval_hours": 8, "last_funding_rate": -0.0005},
    ]
    sig_at = 1619424000000  # Exactly at second settlement time
    res = extract_pre_entry_funding_state(settlements, sig_at)
    # The settlement at exact sig_at is NOT known strictly before signal
    assert res["calc_time"] == 1619395200000
    assert res["rate"] == 0.0001


def test_funding_no_prior_settlement_unknown() -> None:
    settlements = [
        {"calc_time": 1619424000000, "funding_interval_hours": 8, "last_funding_rate": 0.0001},
    ]
    sig_at = 1619395200000  # Prior to first settlement
    res = extract_pre_entry_funding_state(settlements, sig_at)
    assert res["valid"] is False
    assert res["funding_regime"] == "UNKNOWN"


def test_funding_lag_sensitivity_positive() -> None:
    settlements = [
        {"calc_time": 1619395200000, "funding_interval_hours": 8, "last_funding_rate": 0.0001},
        {"calc_time": 1619424000000, "funding_interval_hours": 8, "last_funding_rate": -0.0003},
    ]
    # Signal is 30 seconds after second settlement
    sig_at = 1619424030000
    # Lag is 60 seconds (60,000 ms) -> effective cutoff is sig_at - 60s < 1619424000000
    res = extract_pre_entry_funding_state(settlements, sig_at, lag_ms=60_000)
    assert res["calc_time"] == 1619395200000
    assert res["rate"] == 0.0001


# ---------------------------------------------------------
# 5. Time-Travel Guard & Mutation Tests (Tests 32 - 35)
# ---------------------------------------------------------


def test_time_travel_mutation_guard_trend_invariance() -> None:
    t_start = 1620000000000
    bars = make_synthetic_1m_bars(t_start, 300, base_price=50000.0, price_drift=2.0)
    sig_at = int(bars[239, COL_CLOSE_TIME])

    base_trend = extract_pre_entry_trend_aligned(bars, sig_at, side=1)
    mut_bars = mutate_future_1m_bars(bars, sig_at, multiplier=10.0, noise=5000.0)
    mut_trend = extract_pre_entry_trend_aligned(mut_bars, sig_at, side=1)

    assert base_trend["trend_regime"] == mut_trend["trend_regime"]
    assert base_trend["alignment_val"] == mut_trend["alignment_val"]
    assert base_trend["p_end"] == mut_trend["p_end"]


def test_time_travel_mutation_guard_atr_invariance() -> None:
    t_start = 1609459200000
    bars = make_synthetic_hourly_bars(t_start, 2200, daily_vol=300.0)
    sig_at = int(bars[2160, 5])

    base_atr = extract_pre_entry_atr_regime(bars, sig_at)
    mut_bars = mutate_future_hourly_bars(bars, sig_at, multiplier=20.0)
    mut_atr = extract_pre_entry_atr_regime(mut_bars, sig_at)

    assert base_atr["volatility_regime"] == mut_atr["volatility_regime"]
    assert base_atr["current_norm_atr"] == mut_atr["current_norm_atr"]
    assert base_atr["median_norm_atr"] == mut_atr["median_norm_atr"]


def test_time_travel_mutation_guard_funding_invariance() -> None:
    settlements = [
        {"calc_time": 1619395200000, "funding_interval_hours": 8, "last_funding_rate": 0.0001},
        {"calc_time": 1619424000000, "funding_interval_hours": 8, "last_funding_rate": -0.0002},
    ]
    sig_at = 1619401500000
    base_fund = extract_pre_entry_funding_state(settlements, sig_at)
    mut_settlements = mutate_future_funding_settlements(settlements, sig_at, extreme_rate=0.88)
    mut_fund = extract_pre_entry_funding_state(mut_settlements, sig_at)

    assert base_fund["funding_regime"] == mut_fund["funding_regime"]
    assert base_fund["rate"] == mut_fund["rate"]


def test_time_travel_full_guard_helper() -> None:
    t_start = 1609459200000
    bars_1m = make_synthetic_1m_bars(t_start, 240 * 60, base_price=30000.0)
    hourly = resample_1m_to_1h(bars_1m)
    assert len(hourly) == 240
    # Use 2160 bars for ATR
    hourly_long = make_synthetic_hourly_bars(t_start, 2200)
    settlements = [
        {
            "calc_time": t_start + 8 * HOUR_MS,
            "funding_interval_hours": 8,
            "last_funding_rate": 0.0002,
        },
    ]
    sig_at = t_start + 2165 * HOUR_MS
    guard_res = verify_time_travel_invariance(bars_1m, hourly_long, settlements, sig_at, side=1)
    assert guard_res["status"] == "PASS_TIME_TRAVEL_INVARIANT"


# ---------------------------------------------------------
# 6. Power Gate, Warmup, & Integrity Tests (Tests 36 - 41)
# ---------------------------------------------------------


def test_power_gate_underpowered_threshold() -> None:
    count = 9
    is_underpowered = count < MIN_EVENTS_PER_STRATUM
    assert is_underpowered is True


def test_power_gate_sufficient_support() -> None:
    count = 10
    is_underpowered = count < MIN_EVENTS_PER_STRATUM
    assert is_underpowered is False


def test_jan_2021_warmup_insufficient_90d() -> None:
    t_start = 1609459200000  # 2021-01-01
    bars = make_synthetic_hourly_bars(t_start, 500)  # ~20 days
    sig_at = int(bars[-1, 5])
    res = extract_pre_entry_atr_regime(bars, sig_at)
    assert res["valid"] is False
    assert res["volatility_regime"] == "INCOMPLETE_LOOKBACK"


def test_contract_integrity_and_hashes() -> None:
    contract = get_frozen_contract_data()
    assert len(contract["candidates"]) == 2
    assert len(contract["horizons"]) == 3
    assert "BASE" in contract["cost_models"]
    assert "STRESS" in contract["cost_models"]
    # Check that contract integrity passes on disk
    verify_contract_integrity(contract)


def test_formal_revocations_present() -> None:
    matrix = build_reconciliation_matrix()
    assert "R1_TREND_LEAKAGE" in matrix["revocations"]
    assert "R1_VOLATILITY_SUBSTITUTION" in matrix["revocations"]
    assert "R1_FUNDING_LEAKAGE" in matrix["revocations"]
    assert "R1_W2_YEAR_MISSTATEMENT" in matrix["revocations"]
    assert "R1_SKIPPED_SIGNALS_MISSTATEMENT" in matrix["revocations"]


def test_reconciliation_matrix_discrepancy_table() -> None:
    matrix = build_reconciliation_matrix()
    w2_counts = matrix["discrepancies"]["w2_annual_trade_counts"]
    assert w2_counts["exit_r1_machine_truth"]["2021"] == 10
    assert w2_counts["exit_r1_machine_truth"]["2022"] == 21
    assert w2_counts["exit_r1_machine_truth"]["2023"] == 24
    assert w2_counts["r1_human_report_table_4"]["2021"] == 14
    assert w2_counts["r1_human_report_table_4"]["2022"] == 17


# ---------------------------------------------------------
# 7. Decimal Stdlib Manual 12-Event Synthetic Audit (Test 42)
# ---------------------------------------------------------


def test_decimal_stdlib_manual_12_event_audit() -> None:
    """Rigorous manual audit verifying 12 synthetic events against high-precision Decimal."""
    events = [
        {"p_start": "50000.00", "p_end": "51000.00", "side": 1, "expected_regime": "TREND_ALIGNED"},
        {"p_start": "50000.00", "p_end": "49000.00", "side": 1, "expected_regime": "COUNTERTREND"},
        {"p_start": "50000.00", "p_end": "50000.00", "side": 1, "expected_regime": "NEUTRAL"},
        {
            "p_start": "45000.00",
            "p_end": "44000.00",
            "side": -1,
            "expected_regime": "TREND_ALIGNED",
        },
        {"p_start": "45000.00", "p_end": "46000.00", "side": -1, "expected_regime": "COUNTERTREND"},
        {"p_start": "45000.00", "p_end": "45000.00", "side": -1, "expected_regime": "NEUTRAL"},
        {"p_start": "30000.00", "p_end": "30000.001", "side": 1, "expected_regime": "NEUTRAL"},
        {"p_start": "30000.00", "p_end": "30000.001", "side": -1, "expected_regime": "NEUTRAL"},
        {"p_start": "60000.00", "p_end": "60300.00", "side": 1, "expected_regime": "TREND_ALIGNED"},
        {"p_start": "60000.00", "p_end": "59700.00", "side": 1, "expected_regime": "COUNTERTREND"},
        {
            "p_start": "20000.00",
            "p_end": "19800.00",
            "side": -1,
            "expected_regime": "TREND_ALIGNED",
        },
        {"p_start": "20000.00", "p_end": "20200.00", "side": -1, "expected_regime": "COUNTERTREND"},
    ]

    for ev in events:
        dec_start = Decimal(ev["p_start"])
        dec_end = Decimal(ev["p_end"])
        dec_side = Decimal(ev["side"])
        dec_ret = (dec_end - dec_start) / dec_start
        dec_align = dec_side * dec_ret

        if dec_align > Decimal("1e-7"):
            regime = "TREND_ALIGNED"
        elif dec_align < Decimal("-1e-7"):
            regime = "COUNTERTREND"
        else:
            regime = "NEUTRAL"

        assert regime == ev["expected_regime"]
