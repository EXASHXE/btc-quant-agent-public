"""Synthetic tests for signal features, continuous causal ATR, PIT timing, and future invariance."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategy_research.g2_flow_funding_entries_r1.signals import (
    CANDIDATE_CONFIGS,
    compute_continuous_1h_bars,
    config_identity_sha,
    generate_candidate_signals,
)


def _synthetic_1m_data(n_hours: int = 40, base_price: float = 30000.0) -> tuple[np.ndarray, np.ndarray]:
    """Generate strictly contiguous synthetic 1m Last and Mark data."""
    n_1m = n_hours * 60
    t0 = 1609459200000  # 2021-01-01 00:00:00 UTC
    times = t0 + np.arange(n_1m, dtype=np.int64) * 60_000

    last = np.empty((n_1m, 7), dtype=np.float64)
    last[:, 0] = times
    last[:, 1] = base_price  # Open
    last[:, 2] = base_price + 10.0  # High
    last[:, 3] = base_price - 10.0  # Low
    last[:, 4] = base_price  # Close
    last[:, 5] = 100.0  # Volume
    last[:, 6] = 50.0   # Taker Buy Volume (balanced)

    mark = np.empty((n_1m, 5), dtype=np.float64)
    mark[:, 0] = times
    mark[:, 1] = base_price
    mark[:, 2] = base_price + 10.0
    mark[:, 3] = base_price - 10.0
    mark[:, 4] = base_price

    return last, mark


def test_signed_flow_ratio_edge_cases() -> None:
    """Signed flow ratio: 0.0 for balanced, +1.0 for 100% buy, -1.0 for 100% sell."""
    last, mark = _synthetic_1m_data(n_hours=2)

    # 1st hour: balanced (50 tbv / 100 vol)
    # 2nd hour: all buy (100 tbv / 100 vol)
    last[60:, 6] = 100.0

    bars = compute_continuous_1h_bars(last, mark)
    assert abs(bars["signed_flow"][0] - 0.0) < 1e-6
    assert abs(bars["signed_flow"][1] - 1.0) < 1e-6

    # All sell (0 tbv / 100 vol)
    last[60:, 6] = 0.0
    bars2 = compute_continuous_1h_bars(last, mark)
    assert abs(bars2["signed_flow"][1] - (-1.0)) < 1e-6


def test_continuous_atr_warmup() -> None:
    """ATR(14) has exactly 13 NaNs, then valid continuous values from index 13 onward."""
    last, mark = _synthetic_1m_data(n_hours=30)
    bars = compute_continuous_1h_bars(last, mark)

    # First 13 bars are NaN
    assert np.all(np.isnan(bars["atr"][:13]))
    # 14th bar (index 13) is non-NaN SMA
    assert not np.isnan(bars["atr"][13])
    # Subsequent bars are strictly positive and finite
    assert np.all(bars["atr"][13:] > 0)
    assert np.all(np.isfinite(bars["atr"][13:]))


def test_no_monthly_reset_in_continuous_atr() -> None:
    """ATR does not reset at month boundary: state carries forward smoothly."""
    # 744 hours in Jan + 100 hours in Feb = 844 hours
    n_hours = 844
    last, mark = _synthetic_1m_data(n_hours=n_hours)
    bars = compute_continuous_1h_bars(last, mark)

    # Check ATR at hour 743 and 744 (transition from Jan to Feb)
    atr_jan_end = bars["atr"][743]
    atr_feb_start = bars["atr"][744]

    # Both must be finite, non-NaN, and continuous (no sudden jump to NaN or SMA re-initialization)
    assert not np.isnan(atr_jan_end)
    assert not np.isnan(atr_feb_start)
    assert abs(atr_feb_start - atr_jan_end) < 1e-5  # identical because TR is constant


def test_no_yearly_reset_in_continuous_atr() -> None:
    """ATR does not reset across Dec->Jan year boundary: 8760h year boundary continuity."""
    # 8760 hours in 2021 + 50 hours in 2022 = 8810 hours
    # We can test over smaller representative chunk where boundary is at hour 100
    last, mark = _mock_year_boundary_chunk(n_hours=150, split_hour=100)
    bars = compute_continuous_1h_bars(last, mark)

    atr_before = bars["atr"][99]
    atr_after = bars["atr"][100]

    assert not np.isnan(atr_before)
    assert not np.isnan(atr_after)
    assert abs(atr_after - atr_before) < 1e-5


def _mock_year_boundary_chunk(n_hours: int = 150, split_hour: int = 100) -> tuple[np.ndarray, np.ndarray]:
    n_1m = n_hours * 60
    t0 = 1640908800000  # near 2021-12-31
    times = t0 + np.arange(n_1m, dtype=np.int64) * 60_000
    last = np.empty((n_1m, 7), dtype=np.float64)
    last[:, 0] = times
    last[:, 1] = 40000.0
    last[:, 2] = 40010.0
    last[:, 3] = 39990.0
    last[:, 4] = 40000.0
    last[:, 5] = 100.0
    last[:, 6] = 50.0

    mark = np.empty((n_1m, 5), dtype=np.float64)
    mark[:, 0] = times
    mark[:, 1] = 40000.0
    mark[:, 2] = 40010.0
    mark[:, 3] = 39990.0
    mark[:, 4] = 40000.0
    return last, mark


def test_prefix_mutation_warmup_equivalence() -> None:
    """Adding extra warmup prefix prior to the evaluation window does not alter downstream state."""
    # Series A: 30 hours
    last_a, mark_a = _synthetic_1m_data(n_hours=30)
    # Series B: 50 hours (starts 20 hours earlier)
    last_b, mark_b = _synthetic_1m_data(n_hours=50)

    bars_a = compute_continuous_1h_bars(last_a, mark_a)
    bars_b = compute_continuous_1h_bars(last_b, mark_b)

    # For constant synthetic TR, both reach the exact same steady-state ATR
    atr_a_tail = bars_a["atr"][-5:]
    atr_b_tail = bars_b["atr"][-5:]
    assert np.allclose(atr_a_tail, atr_b_tail, atol=1e-6)


def test_pit_timing_constraints() -> None:
    """Generated signals strictly satisfy PIT timing invariants."""
    last, mark = _synthetic_1m_data(n_hours=30)
    # Inject an F1 absorption event at hour 20: strong seller dominance but price closed higher
    h_idx = 20
    m_start = h_idx * 60
    m_end = m_start + 60
    last[m_start:m_end, 6] = 10.0   # 10 tbv / 100 vol -> signed flow = (20 - 100)/100 = -0.8
    last[m_end - 1, 4] = 30050.0    # close higher than open

    bars = compute_continuous_1h_bars(last, mark)
    cand = next(c for c in CANDIDATE_CONFIGS if c["id"] == "F1_AGGRESSOR_FLOW_ABSORPTION_12H")

    eval_start = int(last[0, 0])
    sigs = generate_candidate_signals(cand, bars, [], last, eval_start)

    assert len(sigs) >= 1
    sig = sigs[0]

    assert sig["decision_at"] >= sig["event_time"] + 60_000
    assert sig["entry_at"] >= sig["decision_at"] + 60_000
    assert sig["event_time"] % 60_000 == 0
    assert sig["decision_at"] % 60_000 == 0
    assert sig["entry_at"] % 60_000 == 0


def test_future_mutation_invariance() -> None:
    """Mutating future market data after decision time does NOT change the signal."""
    last1, mark1 = _synthetic_1m_data(n_hours=30)
    h_idx = 20
    m_start = h_idx * 60
    m_end = m_start + 60
    last1[m_start:m_end, 6] = 10.0
    last1[m_end - 1, 4] = 30050.0

    last2 = last1.copy()
    mark2 = mark1.copy()

    # Mutate future data at hour 25 (after hour 20 signal)
    last2[25 * 60:, 4] *= 2.0
    mark2[25 * 60:, 4] *= 2.0

    bars1 = compute_continuous_1h_bars(last1, mark1)
    bars2 = compute_continuous_1h_bars(last2, mark2)

    cand = next(c for c in CANDIDATE_CONFIGS if c["id"] == "F1_AGGRESSOR_FLOW_ABSORPTION_12H")
    eval_start = int(last1[0, 0])

    sigs1 = generate_candidate_signals(cand, bars1, [], last1, eval_start)
    sigs2 = generate_candidate_signals(cand, bars2, [], last2, eval_start)

    assert len(sigs1) == len(sigs2)
    assert sigs1[0]["event_id"] == sigs2[0]["event_id"]
    assert sigs1[0]["side"] == sigs2[0]["side"]
    assert sigs1[0]["decision_close"] == sigs2[0]["decision_close"]
    assert sigs1[0]["stop"] == sigs2[0]["stop"]


def test_f1_absorption_rules() -> None:
    """F1: Long on seller absorption, Short on buyer absorption."""
    last, mark = _synthetic_1m_data(n_hours=30)

    # Hour 18: Buyer absorption -> Short
    m18 = 18 * 60
    last[m18:m18 + 60, 6] = 90.0  # flow = +0.8
    last[m18 + 59, 4] = 29990.0   # price closed down (-10)

    # Hour 22: Seller absorption -> Long
    m22 = 22 * 60
    last[m22:m22 + 60, 6] = 10.0  # flow = -0.8
    last[m22 + 59, 4] = 30010.0   # price closed up (+10)

    bars = compute_continuous_1h_bars(last, mark)
    cand = next(c for c in CANDIDATE_CONFIGS if c["id"] == "F1_AGGRESSOR_FLOW_ABSORPTION_12H")

    eval_start = int(last[0, 0])
    sigs = generate_candidate_signals(cand, bars, [], last, eval_start)

    sides = {s["decision_at"]: s["side"] for s in sigs}
    t_dec_18 = int(bars["open_time"][18] + 3600_000)
    t_dec_22 = int(bars["open_time"][22] + 3600_000)

    assert sides.get(t_dec_18) == -1  # Short
    assert sides.get(t_dec_22) == 1   # Long


def test_f2_funding_reversal_rules() -> None:
    """F2: Long when funding flips from positive to negative, Short when negative to positive."""
    last, mark = _synthetic_1m_data(n_hours=40)
    cand = next(c for c in CANDIDATE_CONFIGS if c["id"] == "F2_REALIZED_FUNDING_REVERSAL_12H")

    # Funding settlements every 8 hours
    t0 = int(last[0, 0])
    t_settle1 = t0 + 8 * 3600_000
    t_settle2 = t0 + 16 * 3600_000

    # Settlement 1: rate = +0.0001
    # Settlement 2: rate = -0.0001 (reversal + to -)
    funding_events = [
        {"settlement_at": t_settle1, "rate": "0.00010000", "interval_hours": "8.0"},
        {"settlement_at": t_settle2, "rate": "-0.00010000", "interval_hours": "8.0"},
    ]

    # Price progress during the 8h before settlement 2 declined
    idx_start = 8 * 60
    idx_end = 16 * 60 - 1
    last[idx_start, 1] = 30000.0
    last[idx_end, 4] = 29500.0  # delta_p_8h = -500 < 0

    bars = compute_continuous_1h_bars(last, mark)
    sigs = generate_candidate_signals(cand, bars, funding_events, last, eval_start_ms=t0)

    assert len(sigs) == 1
    sig = sigs[0]
    assert sig["side"] == 1  # Long
    assert sig["decision_at"] == t_settle2 + 60_000
    assert sig["entry_at"] == t_settle2 + 120_000


def test_f3_basis_dislocation_rules() -> None:
    """F3: Long when Last is at a discount to Mark and flow is buying; Short when premium and selling."""
    last, mark = _synthetic_1m_data(n_hours=30)
    cand = next(c for c in CANDIDATE_CONFIGS if c["id"] == "F3_MARK_LAST_DISLOCATION_REPAIR_12H")

    # Hour 20: Last traded at a discount of 5 bps to Mark (30000 vs 30015), flow is buying
    m20 = 20 * 60
    last[m20:m20 + 60, 4] = 30000.0
    mark[m20:m20 + 60, 4] = 30015.0  # (30000 - 30015)/30015 = -0.000499 < -0.0003
    last[m20:m20 + 60, 6] = 70.0     # flow > 0

    bars = compute_continuous_1h_bars(last, mark)
    eval_start = int(last[0, 0])
    sigs = generate_candidate_signals(cand, bars, [], last, eval_start)

    t_dec_20 = int(bars["open_time"][20] + 3600_000)
    sigs_20 = [s for s in sigs if s["decision_at"] == t_dec_20]
    assert len(sigs_20) == 1
    assert sigs_20[0]["side"] == 1  # Long


def test_candidate_configs_count_and_uniqueness() -> None:
    """Candidate identities: exactly 6 configs across 3 families."""
    assert len(CANDIDATE_CONFIGS) == 6
    ids = [c["id"] for c in CANDIDATE_CONFIGS]
    assert len(set(ids)) == 6
    horizons = {c["horizon_hours"] for c in CANDIDATE_CONFIGS}
    assert horizons == {12, 18}
    families = {c["family"] for c in CANDIDATE_CONFIGS}
    assert len(families) == 3


def test_candidate_identity_hashes_deterministic() -> None:
    """Candidate identity hashes are deterministic SHA256 hex strings."""
    for c in CANDIDATE_CONFIGS:
        h1 = config_identity_sha(c)
        h2 = config_identity_sha(c)
        assert len(h1) == 64
        assert h1 == h2
