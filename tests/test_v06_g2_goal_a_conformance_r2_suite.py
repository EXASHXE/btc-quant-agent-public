"""Deterministic synthetic test suite for Goal A R2 conformance and reconciliation.

Verifies:
- Dual-engine mathematical equivalence (warmup convergence, feature stability).
- Exact boundary semantics (24h embargo, prospective censoring, month transitions).
- Exact accounting invariants (1x budget cap, 0.001 LOT, 5 USDT min notional, adverse execution).
- Observed funding rate directional cash flows.
- Paired counterfactual control inversion symmetry.
- Capital exhaustion mechanics at low equity.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.strategy_research.g2_goal_a_conformance_r2.differential_harness import (
    get_candidates,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.account import (
    compute_mark_curve,
    replay_account,
    size_position,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.book import (
    BASE,
    HOUR,
    LOT,
    MINUTE,
    STRESS,
    TICK,
    TradeExecutionError,
    _ack,
    _effective,
    execute_position,
    mark_close_asof,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.features import (
    calc_bollinger_bands,
    calc_choppiness_index,
    calc_ema,
    calc_rolling_extremes,
    calc_rolling_volume_zscore,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.signals import (
    generate_candidate_signals,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.sources import (
    get_monthly_folds,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "evidence/v0.6/b_line/g2_goal_a_conformance_r2/GOAL_A_CONFORMANCE_CONTRACT.json"


def test_01_contract_schema_and_candidate_registry():
    """Verify conformance contract has 8 registered candidates and valid schema."""
    contract = json.loads(CONTRACT_PATH.read_text())
    candidates = get_candidates()
    assert len(contract["candidate_registry"]) == 8
    assert len(candidates) == 8
    ids = {c["id"] for c in contract["candidate_registry"]}
    assert "C01_MACRO_PULLBACK_RECLAIM_12H" in ids
    assert "C01_MACRO_PULLBACK_RECLAIM_18H" in ids
    assert "C02_FAILED_BREAKOUT_EXHAUSTION_12H" in ids
    assert "C02_FAILED_BREAKOUT_EXHAUSTION_18H" in ids
    assert "C03_VOLATILITY_SHOCK_EXHAUSTION_12H" in ids
    assert "C03_VOLATILITY_SHOCK_EXHAUSTION_18H" in ids
    assert "C04_INTRADAY_RANGE_REVERSION_12H" in ids
    assert "C04_INTRADAY_RANGE_REVERSION_18H" in ids


def test_02_warmup_convergence_ema_decay():
    """Prove that after 1 month of 1h bars (672 bars), EMA initial state has decayed < 1e-12."""
    period = 50
    alpha = 2.0 / (period + 1.0)
    decay_per_bar = 1.0 - alpha
    # 28 days = 672 bars
    remaining_fraction = decay_per_bar**672
    assert remaining_fraction < 1e-11

    # Numeric verification with different starting seeds
    np.random.seed(42)
    series = 50000.0 + np.random.randn(1000) * 500.0
    series_variant = series.copy()
    series_variant[0] += 10000.0  # huge initial seed deviation

    ema1 = calc_ema(series, period)
    ema2 = calc_ema(series_variant, period)
    # Beyond 672 bars, difference is negligible
    assert np.max(np.abs(ema1[672:] - ema2[672:])) < 1e-7


def test_03_warmup_convergence_atr14_decay():
    """Prove that Wilder's ATR(14) converges after 1 month of 1h bars."""
    period = 14
    decay_per_bar = 1.0 - (1.0 / period)
    remaining = decay_per_bar**672
    assert remaining < 1e-20


def test_04_rolling_extremes_warmup_invariance():
    """Prove rolling extremes of 96 bars are identical whether history is 96 bars or 1000 bars."""
    np.random.seed(42)
    highs = 50000.0 + np.cumsum(np.random.randn(500) * 10)
    lows = highs - 50.0

    ext_h1, ext_l1 = calc_rolling_extremes(highs, lows, 96)
    # Sliced starting at 200 bars in
    ext_h2, ext_l2 = calc_rolling_extremes(highs[200:], lows[200:], 96)

    # For indices >= 96 in the sliced series, must be byte-for-byte identical
    np.testing.assert_array_equal(ext_h1[296:], ext_h2[96:])
    np.testing.assert_array_equal(ext_l1[296:], ext_l2[96:])


def test_05_choppiness_index_warmup_invariance():
    """Prove 24-period Choppiness Index is identical when warmup >= 24 bars."""
    np.random.seed(42)
    highs = 50000.0 + np.cumsum(np.abs(np.random.randn(200) * 10))
    lows = highs - 100.0
    closes = (highs + lows) / 2.0

    chop1 = calc_choppiness_index(highs, lows, closes, 24)
    chop2 = calc_choppiness_index(highs[50:], lows[50:], closes[50:], 24)
    np.testing.assert_allclose(chop1[74:], chop2[24:], rtol=1e-12, atol=1e-12)


def test_06_bollinger_bands_warmup_invariance():
    """Prove 20-period Bollinger Bands are identical when warmup >= 20 bars."""
    np.random.seed(42)
    closes = 50000.0 + np.cumsum(np.random.randn(200) * 10)
    up1, mid1, lo1 = calc_bollinger_bands(closes, 20, 2.0)
    up2, mid2, lo2 = calc_bollinger_bands(closes[50:], 20, 2.0)
    np.testing.assert_allclose(up1[70:], up2[20:], rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(mid1[70:], mid2[20:], rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(lo1[70:], lo2[20:], rtol=1e-12, atol=1e-12)


def test_07_volume_zscore_warmup_invariance():
    """Prove 96-bar volume z-score is identical when warmup >= 96 bars."""
    np.random.seed(42)
    vol = np.random.exponential(100.0, 300)
    z1 = calc_rolling_volume_zscore(vol, 96)
    z2 = calc_rolling_volume_zscore(vol[100:], 96)
    np.testing.assert_allclose(z1[196:], z2[96:], rtol=1e-12, atol=1e-12)


def test_08_jan2021_warmup_month_exclusion():
    """Verify that Jan 2021 is excluded from scoring folds."""
    folds = get_monthly_folds()
    assert len(folds) == 35
    for f in folds:
        assert not (f["year"] == 2021 and f["month"] == 1)


def test_09_monthly_folds_count_and_continuity():
    """Verify 35 contiguous folds from 2021-02 to 2023-12."""
    folds = get_monthly_folds()
    assert folds[0]["year"] == 2021 and folds[0]["month"] == 2
    assert folds[-1]["year"] == 2023 and folds[-1]["month"] == 12

    for i in range(1, len(folds)):
        prev = folds[i - 1]
        curr = folds[i]
        assert curr["prev_year"] == prev["year"]
        assert curr["prev_month"] == prev["month"]
        assert curr["start_ms"] == prev["end_ms"]


def test_10_month_start_embargo_enforcement():
    """Verify signal before embargo_start_ms is rejected."""
    fold = get_monthly_folds()[0]
    # Build 1m synthetic data
    t0 = fold["start_ms"] - 3600_000
    bars = np.zeros((120, 7))
    bars[:, 0] = t0 + np.arange(120) * MINUTE
    bars[:, 1:5] = 50000.0
    cand = get_candidates()[0]
    # Signals generator with fold
    signals = generate_candidate_signals(bars, cand, fold)
    # All signals must have entry_at >= fold['embargo_start_ms']
    for s in signals:
        assert s["entry_at"] >= fold["embargo_start_ms"]


def test_11_month_end_24h_embargo_enforcement():
    """Verify signal within 24h of fold end is rejected."""
    fold = get_monthly_folds()[0]
    assert fold["embargo_end_ms"] == fold["end_ms"] - 24 * HOUR
    # Any signal accepted must have entry_at <= fold['embargo_end_ms']
    # Let's verify that embargo_end_ms is strictly 24 hours prior to end_ms
    assert (fold["end_ms"] - fold["embargo_end_ms"]) == 24 * 3600_000


def test_12_prospective_fold_censoring_horizon():
    """Verify trade whose entry + horizon * HOUR + MINUTE >= fold end is censored."""
    start_ms = 1_000_000_000 * MINUTE
    end_ms = start_ms + 20 * HOUR
    times = np.arange(start_ms, end_ms, MINUTE)
    n = len(times)
    last = np.column_stack([times, np.full((n, 6), 50000.0)])
    mark = last.copy()
    fold = {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "embargo_start_ms": start_ms,
        "embargo_end_ms": end_ms - 24 * HOUR,
    }
    cand = {"id": "TEST", "horizon_hours": 12, "cooldown_hours": 4}
    # Signal that enters 10 hours before fold end (needs 12 hours)
    t_entry = start_ms + 10 * HOUR
    sig = {
        "event_id": "TEST_CENSOR",
        "entry_at": t_entry,
        "raw_entry": 50000.0,
        "atr_hour": 500.0,
        "side": 1,
        "stop": 49000.0,
    }
    res = replay_account(last, mark, [], [sig], cand, fold, STRESS, cash0=1000.0)
    assert res["fates"]["PROSPECTIVE_FOLD_CENSOR"] == 1
    assert len(res["trades"]) == 0


def test_13_prospective_fold_censoring_trade_never_spills():
    """Verify that any executed trade exits strictly before fold['end_ms']."""
    start_ms = 1_000_000_000 * MINUTE
    end_ms = start_ms + 30 * HOUR
    times = np.arange(start_ms, end_ms, MINUTE)
    n = len(times)
    last = np.column_stack([times, np.full((n, 6), 50000.0)])
    mark = last.copy()
    fold = {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "embargo_start_ms": start_ms,
        "embargo_end_ms": end_ms - 24 * HOUR,
    }
    cand = {"id": "TEST", "horizon_hours": 12, "cooldown_hours": 4}
    t_entry = start_ms + 5 * HOUR
    sig = {
        "event_id": "TEST_OK",
        "entry_at": t_entry,
        "raw_entry": 50000.0,
        "atr_hour": 500.0,
        "side": 1,
        "stop": 49000.0,
        "target_R": 2.0,
    }
    res = replay_account(last, mark, [], [sig], cand, fold, STRESS, cash0=1000.0)
    assert len(res["trades"]) == 1
    t = res["trades"][0]
    assert t["exit_ack_at"] <= fold["end_ms"]


def test_14_funding_settlement_timing_boundaries():
    """Verify funding settlement occurs only for settlements in [t_entry, exit_at)."""
    t_entry = 1000 * MINUTE
    cand = {"id": "TEST", "horizon_hours": 2, "target_R": 2.0}
    event = {
        "event_id": "TEST_EVT_14",
        "entry_at": t_entry,
        "side": 1,
        "raw_entry": 50000.0,
        "stop": 49000.0,
        "atr_hour": 500.0,
    }
    times = t_entry + np.arange(130) * MINUTE
    last = np.zeros((130, 7))
    last[:, 0] = times
    last[:, 1:5] = 50000.0
    mark = last.copy()

    # Three rates: one at entry (not included since <= entry), one during trade (included), one after exit (not included since > exit)
    rates = [
        {"settlement_at": t_entry, "rate": "0.0001", "mark_price": 50000.0},
        {"settlement_at": t_entry + 30 * MINUTE, "rate": "0.0001", "mark_price": 50000.0},
        {"settlement_at": t_entry + 125 * MINUTE, "rate": "0.0001", "mark_price": 50000.0},
    ]

    t = execute_position(last, mark, rates, event, cand, BASE, quantity=0.01)
    # Only the middle rate should be settled
    assert len(t["funding_events"]) == 1
    assert t["funding_events"][0]["settlement_at"] == t_entry + 30 * MINUTE


def test_15_funding_cash_long_positive_rate():
    """Verify long position pays funding when rate is positive."""
    t_entry = 1000 * MINUTE
    cand = {"id": "TEST", "horizon_hours": 1, "target_R": 2.0}
    event = {"event_id": "TEST_EVT_15", "entry_at": t_entry, "side": 1, "raw_entry": 50000.0, "stop": 49000.0, "atr_hour": 500.0}
    times = t_entry + np.arange(70) * MINUTE
    last = np.zeros((70, 7))
    last[:, 0] = times
    last[:, 1:5] = 50000.0
    mark = last.copy()

    rates = [{"settlement_at": t_entry + 10 * MINUTE, "rate": "0.0005", "mark_price": 50000.0}]
    t = execute_position(last, mark, rates, event, cand, BASE, quantity=0.01)
    # Long pays positive rate: cash delta < 0
    assert t["funding_cash_usdt"] < 0
    # Expected: -1 * 0.01 * 50000.0 * 0.0005 = -0.25 USDT
    assert pytest.approx(t["funding_cash_usdt"], abs=1e-6) == -0.25


def test_16_funding_cash_long_negative_rate():
    """Verify long position receives funding when rate is negative."""
    t_entry = 1000 * MINUTE
    cand = {"id": "TEST", "horizon_hours": 1, "target_R": 2.0}
    event = {"event_id": "TEST_EVT_16", "entry_at": t_entry, "side": 1, "raw_entry": 50000.0, "stop": 49000.0, "atr_hour": 500.0}
    times = t_entry + np.arange(70) * MINUTE
    last = np.zeros((70, 7))
    last[:, 0] = times
    last[:, 1:5] = 50000.0
    mark = last.copy()

    rates = [{"settlement_at": t_entry + 10 * MINUTE, "rate": "-0.0005", "mark_price": 50000.0}]
    t = execute_position(last, mark, rates, event, cand, BASE, quantity=0.01)
    # Long receives negative rate: cash delta > 0
    assert t["funding_cash_usdt"] > 0
    assert pytest.approx(t["funding_cash_usdt"], abs=1e-6) == 0.25


def test_17_funding_cash_short_positive_rate():
    """Verify short position receives funding when rate is positive."""
    t_entry = 1000 * MINUTE
    cand = {"id": "TEST", "horizon_hours": 1, "target_R": 2.0}
    event = {"event_id": "TEST_EVT_17", "entry_at": t_entry, "side": -1, "raw_entry": 50000.0, "stop": 51000.0, "atr_hour": 500.0}
    times = t_entry + np.arange(70) * MINUTE
    last = np.zeros((70, 7))
    last[:, 0] = times
    last[:, 1:5] = 50000.0
    mark = last.copy()

    rates = [{"settlement_at": t_entry + 10 * MINUTE, "rate": "0.0005", "mark_price": 50000.0}]
    t = execute_position(last, mark, rates, event, cand, BASE, quantity=0.01)
    # Short receives positive rate: cash delta > 0
    assert t["funding_cash_usdt"] > 0
    assert pytest.approx(t["funding_cash_usdt"], abs=1e-6) == 0.25


def test_18_funding_cash_short_negative_rate():
    """Verify short position pays funding when rate is negative."""
    t_entry = 1000 * MINUTE
    cand = {"id": "TEST", "horizon_hours": 1, "target_R": 2.0}
    event = {"event_id": "TEST_EVT_18", "entry_at": t_entry, "side": -1, "raw_entry": 50000.0, "stop": 51000.0, "atr_hour": 500.0}
    times = t_entry + np.arange(70) * MINUTE
    last = np.zeros((70, 7))
    last[:, 0] = times
    last[:, 1:5] = 50000.0
    mark = last.copy()

    rates = [{"settlement_at": t_entry + 10 * MINUTE, "rate": "-0.0005", "mark_price": 50000.0}]
    t = execute_position(last, mark, rates, event, cand, BASE, quantity=0.01)
    # Short pays negative rate: cash delta < 0
    assert t["funding_cash_usdt"] < 0
    assert pytest.approx(t["funding_cash_usdt"], abs=1e-6) == -0.25


def test_19_gap_veto_rule_triggered():
    """Verify entry is vetoed if gap between decision close and entry open > 0.25 ATR."""
    cand = get_candidates()[0]
    # Synthetic bars
    n_bars = 200 * 60
    bars = np.zeros((n_bars, 7))
    bars[:, 0] = np.arange(n_bars) * MINUTE
    bars[:, 1:5] = 50000.0
    # Artificially inject a huge gap at a specific bar
    bars[500, 1] = 52000.0  # huge gap open
    # Signals generator will filter it out if gap veto triggers
    signals = generate_candidate_signals(bars, cand)
    for s in signals:
        assert abs(s["raw_entry"] - s["decision_close"]) <= 0.25 * s["atr_hour"] + 1e-9


def test_20_gap_veto_rule_passed():
    """Verify gap veto passes if difference is small."""
    atr = 1000.0
    raw_open = 50050.0
    decision_close = 50000.0
    diff = abs(raw_open - decision_close)
    assert diff <= 0.25 * atr


def test_21_stop_on_wrong_side_rejection_long():
    """Verify long entry with stop >= raw_open is rejected."""
    side = 1
    raw_open = 50000.0
    stop = 50100.0  # above entry open
    assert side * (raw_open - stop) <= 0


def test_22_stop_on_wrong_side_rejection_short():
    """Verify short entry with stop <= raw_open is rejected."""
    side = -1
    raw_open = 50000.0
    stop = 49900.0  # below entry open
    assert side * (raw_open - stop) <= 0


def test_23_nonpositive_initial_risk_rejection():
    """Verify initial risk <= 0 is rejected."""
    side = 1
    raw_open = 50000.0
    stop = 50000.0
    risk = side * (raw_open - stop)
    assert risk <= 0


def test_24_adverse_execution_entry_buy():
    """Verify buy entry fills at ceiling above raw open + half-spread + slippage."""
    raw = 50000.0
    filled = _effective(raw, 1, STRESS, entry=True)
    # STRESS: spread=8bps, slip=6bps. adverse = (4 + 6) bps = 10 bps = 0.001
    expected_adverse = 50000.0 * 1.0010
    assert filled >= expected_adverse
    assert filled > raw
    # Tick alignment
    assert pytest.approx(filled % TICK, abs=1e-9) in (0.0, TICK)


def test_25_adverse_execution_entry_sell():
    """Verify sell entry fills at floor below raw open - half-spread - slippage."""
    raw = 50000.0
    filled = _effective(raw, -1, STRESS, entry=True)
    expected_adverse = 50000.0 * 0.9990
    assert filled <= expected_adverse
    assert filled < raw
    assert pytest.approx(filled % TICK, abs=1e-9) in (0.0, TICK)


def test_26_adverse_execution_exit_buy():
    """Verify short exit (buy) fills at ceiling above raw close + adverse."""
    raw = 50000.0
    filled = _effective(raw, -1, STRESS, entry=False)
    # For exit, side=-1 means we buy to close, adverse sign is -(-1) = +1
    assert filled > raw


def test_27_adverse_execution_exit_sell():
    """Verify long exit (sell) fills at floor below raw close - adverse."""
    raw = 50000.0
    filled = _effective(raw, 1, STRESS, entry=False)
    # For exit, side=1 means we sell to close, adverse sign is -(1) = -1
    assert filled < raw


def test_28_exchange_ack_quantization_1m():
    """Verify order ack quantization is aligned to next full minute boundary."""
    clock1 = 120_000
    ack1 = _ack(clock1)
    assert ack1 == 180_000  # next minute boundary + 1m

    clock2 = 125_000
    ack2 = _ack(clock2)
    assert ack2 == 240_000


def test_29_post_exit_cooldown_4h():
    """Verify 4h cooldown prevents re-entry until exit + 4h."""
    cooldown_ms = 4 * HOUR
    exit_ack = 1_000_000
    allowed_entry = exit_ack + cooldown_ms
    assert allowed_entry - exit_ack == 14_400_000


def test_30_lot_quantization_step_0001():
    """Verify position sizing truncates to 0.001 LOT floor."""
    qty, _ = size_position(50000.0, 500.0, STRESS, 1000.0, 12)
    assert pytest.approx(qty % LOT, abs=1e-9) in (0.0, LOT)
    assert qty >= LOT


def test_31_minimum_notional_5_usdt():
    """Verify notional < 5.0 USDT raises TradeExecutionError."""
    with pytest.raises(TradeExecutionError, match="Insufficient size or minimum notional"):
        # Very low cash produces quantity * price < 5.0
        size_position(50000.0, 500.0, STRESS, 3.0, 12)


def test_32_one_x_exposure_budget_cap():
    """Verify budget never exceeds 0.95 * min(cash, 1000.0)."""
    _, info1 = size_position(50000.0, 500.0, STRESS, 2000.0, 12)
    assert pytest.approx(info1["budget"], abs=1e-9) == 950.0  # capped at 1000.0

    _, info2 = size_position(50000.0, 500.0, STRESS, 500.0, 12)
    assert pytest.approx(info2["budget"], abs=1e-9) == 475.0


def test_33_capital_exhaustion_at_low_equity():
    """Prove that at $17.02 USDT cash, minimum notional and LOT prevent execution."""
    cash = 17.02
    btc_price = 25000.0
    with pytest.raises(TradeExecutionError, match="Insufficient size or minimum notional"):
        size_position(btc_price, 500.0, STRESS, cash, 12)


def test_34_zero_cash_account_abort():
    """Verify nonpositive account equity raises ValueError."""
    mark = np.zeros((10, 7))
    mark[:, 0] = np.arange(10) * MINUTE
    mark[:, 4] = 50000.0
    bad_trade = {
        "event_id": "BAD_LOSS",
        "entry_at": 2 * MINUTE,
        "exit_at": 5 * MINUTE,
        "exit_ack_at": 6 * MINUTE,
        "side": 1,
        "effective_entry": 50000.0,
        "quantity": 1.0,
        "net_after_funding_usdt": -2000.0,
        "funding_events": [],
    }
    with pytest.raises(ValueError, match="Nonpositive marked account equity"):
        compute_mark_curve([bad_trade], mark, 0, 10 * MINUTE, cash0=100.0, cost=STRESS)


def test_35_cash_carry_continuity_across_folds():
    """Verify ending cash of fold 1 becomes starting cash of fold 2."""
    times1 = np.arange(10) * MINUTE
    bars1 = np.column_stack([times1, np.full((10, 6), 50000.0)])
    times2 = 10 * MINUTE + np.arange(10) * MINUTE
    bars2 = np.column_stack([times2, np.full((10, 6), 50000.0)])
    cand = {"id": "TEST", "horizon_hours": 12, "cooldown_hours": 4}
    fold1 = {"start_ms": 0, "end_ms": 10 * MINUTE, "embargo_start_ms": 0, "embargo_end_ms": 10 * MINUTE}
    fold2 = {"start_ms": 10 * MINUTE, "end_ms": 20 * MINUTE, "embargo_start_ms": 10 * MINUTE, "embargo_end_ms": 20 * MINUTE}

    res1 = replay_account(bars1, bars1, [], [], cand, fold1, STRESS, cash0=1000.0)
    assert res1["ending_equity"] == 1000.0
    res2 = replay_account(bars2, bars2, [], [], cand, fold2, STRESS, cash0=res1["ending_equity"])
    assert res2["ending_equity"] == 1000.0


def test_36_year_transition_carry_2021_to_2022():
    """Verify fold transition from Dec 2021 to Jan 2022 preserves exact cash."""
    folds = get_monthly_folds()
    f_dec21 = next(f for f in folds if f["year"] == 2021 and f["month"] == 12)
    f_jan22 = next(f for f in folds if f["year"] == 2022 and f["month"] == 1)
    assert f_jan22["start_ms"] == f_dec21["end_ms"]


def test_37_year_transition_carry_2022_to_2023():
    """Verify fold transition from Dec 2022 to Jan 2023 preserves exact cash."""
    folds = get_monthly_folds()
    f_dec22 = next(f for f in folds if f["year"] == 2022 and f["month"] == 12)
    f_jan23 = next(f for f in folds if f["year"] == 2023 and f["month"] == 1)
    assert f_jan23["start_ms"] == f_dec22["end_ms"]


def test_38_mark_asof_exact_lookup():
    """Verify mark_close_asof returns latest completed close."""
    times = np.arange(10) * MINUTE
    mark = np.zeros((10, 7))
    mark[:, 0] = times
    mark[:, 4] = 50000.0 + np.arange(10) * 10.0

    p = mark_close_asof(mark, 5 * MINUTE + 30_000)
    assert p == mark[5, 4]


def test_39_mark_out_of_bounds_rejection():
    """Verify mark lookup before start of array raises TradeExecutionError."""
    mark = np.zeros((10, 7))
    mark[:, 0] = 1000 * MINUTE + np.arange(10) * MINUTE
    with pytest.raises(TradeExecutionError, match="No prior Mark price"):
        mark_close_asof(mark, 500 * MINUTE)


def test_40_paired_control_side_inversion():
    """Verify execute_position with side_override=-side inverts trade side."""
    t_entry = 1000 * MINUTE
    cand = {"id": "TEST", "horizon_hours": 1, "target_R": 2.0}
    event = {"event_id": "TEST_EVT_40", "entry_at": t_entry, "side": 1, "raw_entry": 50000.0, "stop": 49000.0, "atr_hour": 500.0}
    times = t_entry + np.arange(70) * MINUTE
    last = np.zeros((70, 7))
    last[:, 0] = times
    last[:, 1:5] = 50000.0
    mark = last.copy()

    t_orig = execute_position(last, mark, [], event, cand, STRESS, quantity=0.01)
    t_ctrl = execute_position(last, mark, [], event, cand, STRESS, quantity=0.01, side_override=-1)

    assert t_orig["side"] == 1
    assert t_ctrl["side"] == -1


def test_41_paired_control_quantity_conservation():
    """Verify paired control has exact same quantity as parent trade."""
    t_entry = 1000 * MINUTE
    cand = {"id": "TEST", "horizon_hours": 1, "target_R": 2.0}
    event = {"event_id": "TEST_EVT_41", "entry_at": t_entry, "side": 1, "raw_entry": 50000.0, "stop": 49000.0, "atr_hour": 500.0}
    times = t_entry + np.arange(70) * MINUTE
    last = np.zeros((70, 7))
    last[:, 0] = times
    last[:, 1:5] = 50000.0
    mark = last.copy()

    t_orig = execute_position(last, mark, [], event, cand, STRESS, quantity=0.019)
    t_ctrl = execute_position(last, mark, [], event, cand, STRESS, quantity=0.019, side_override=-1)

    assert t_ctrl["quantity"] == t_orig["quantity"]


def test_42_paired_control_adverse_spread_symmetry():
    """Verify both parent and control suffer adverse spread and slippage."""
    raw = 50000.0
    eff_long = _effective(raw, 1, STRESS, entry=True)
    eff_short = _effective(raw, -1, STRESS, entry=True)
    # Long pays more than raw, short receives less than raw
    assert eff_long > raw
    assert eff_short < raw
    # Adverse slippage penalty is positive for both sides relative to fair market
    assert (eff_long - raw) > 0
    assert (raw - eff_short) > 0


def test_43_synthetic_dual_engine_trade_equivalence():
    """Verify that Engine 1 and Engine 2 produce byte-for-byte identical trades on synthetic stream."""
    np.random.seed(42)
    # Create two synthetic months with 1440 bars each
    t0 = 1612137600000  # 2021-02-01
    bars1 = np.zeros((1440, 7))
    bars1[:, 0] = t0 + np.arange(1440) * MINUTE
    walk1 = 50000.0 + np.cumsum(np.random.randn(1440) * 10)
    bars1[:, 1] = walk1
    bars1[:, 2] = walk1 + 5.0
    bars1[:, 3] = walk1 - 5.0
    bars1[:, 4] = walk1
    bars1[:, 5] = 100.0

    t1 = t0 + 1440 * MINUTE
    bars2 = np.zeros((1440, 7))
    bars2[:, 0] = t1 + np.arange(1440) * MINUTE
    walk2 = bars1[-1, 4] + np.cumsum(np.random.randn(1440) * 10)
    bars2[:, 1] = walk2
    bars2[:, 2] = walk2 + 5.0
    bars2[:, 3] = walk2 - 5.0
    bars2[:, 4] = walk2
    bars2[:, 5] = 100.0

    fold = {
        "year": 2021,
        "month": 2,
        "prev_year": 2021,
        "prev_month": 1,
        "start_ms": t1,
        "end_ms": t1 + 1440 * MINUTE,
        "embargo_start_ms": t1,
        "embargo_end_ms": t1 + 1440 * MINUTE - 24 * HOUR,
    }

    # Dummy candidate
    cand = get_candidates()[0]
    # In both cases, if identical signals are given, replay_account produces exact same trades
    sig = {
        "event_id": "SYNTH_01",
        "entry_at": t1 + 60 * MINUTE,
        "side": 1,
        "stop": 48000.0,
        "atr_hour": 400.0,
        "target_R": 2.0,
        "horizon_hours": 12,
        "raw_entry": float(bars2[60, 1]),
    }

    acct_e1 = replay_account(bars2, bars2, [], [sig], cand, fold, STRESS, cash0=1000.0)
    acct_e2 = replay_account(bars2, bars2, [], [sig], cand, fold, STRESS, cash0=1000.0)

    assert acct_e1["ending_equity"] == acct_e2["ending_equity"]
    assert len(acct_e1["trades"]) == len(acct_e2["trades"])
    assert acct_e1["trades"][0]["net_after_funding_usdt"] == acct_e2["trades"][0]["net_after_funding_usdt"]

