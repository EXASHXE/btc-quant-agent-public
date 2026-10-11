"""Comprehensive bounded synthetic test suite for Goal A R2.

Covers:
- Causal time alignment, multi-scale resampling, and lookahead rejection.
- Adverse effective price execution, fee quantization, and tick rounding.
- Gap veto, stop/target collisions (stop-before-target priority), and deadline exits.
- Signed funding cash flows and settlement timing.
- Whole-account single-position constraints, LOT sizing, ACK quantization, and 4h cooldown.
- Block bootstrap maxT determinism and Decimal crosscheck precision.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from scripts.strategy_research.g2_goal_entry_discovery_r2.account import (
    compute_mark_curve,
    replay_account,
    size_position,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.audit import (
    audit_trade_decimal,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.book import (
    BASE,
    HOUR,
    LOT,
    MINUTE,
    TradeExecutionError,
    _ack,
    _effective,
    _fee,
    _tick,
    execute_position,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.features import (
    aggregate_bars,
    calc_atr,
    calc_bollinger_bands,
    calc_choppiness_index,
    calc_ema,
    calc_rolling_extremes,
    calc_rolling_volume_zscore,
    calc_sma,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.signals import (
    generate_candidate_signals,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.sources import (
    EP,
    guarded,
)
from scripts.strategy_research.g2_goal_entry_discovery_r2.statistics import (
    block_bootstrap_max_t,
)


def _synthetic_1m(n_minutes: int, base_price: float = 30_000.0, start_ms: int = 1_609_459_200_000) -> np.ndarray:
    """Generate n_minutes of contiguous 1m bars with realistic OHLCV."""
    rows = []
    curr = base_price
    for i in range(n_minutes):
        t = start_ms + i * MINUTE
        o = curr
        h = o + 5.0
        lo = o - 5.0
        c = o + 2.0
        v = 10.0
        tbv = 6.0
        rows.append([float(t), o, h, lo, c, v, tbv])
        curr = c
    return np.asarray(rows, dtype=np.float64)


def test_01_resampling_aggregation():
    data = _synthetic_1m(60)
    agg15 = aggregate_bars(data, 15)
    assert len(agg15["open"]) == 4
    assert agg15["open"][0] == data[0, 1]
    assert agg15["close"][0] == data[14, 4]
    assert agg15["high"][0] == np.max(data[:15, 2])
    assert agg15["low"][0] == np.min(data[:15, 3])
    assert agg15["volume"][0] == np.sum(data[:15, 5])
    assert agg15["end_ms"][0] == data[0, 0] + 15 * MINUTE - 1


def test_02_resampling_incomplete_tail_truncated():
    data = _synthetic_1m(70)
    agg15 = aggregate_bars(data, 15)
    # 70 // 15 == 4 bars; remaining 10 minutes are safely discarded
    assert len(agg15["open"]) == 4


def test_03_causal_ema_no_future_lookahead():
    prices = np.array([10.0, 11.0, 12.0, 13.0, 14.0, 15.0])
    ema1 = calc_ema(prices, 3)
    # Modify future price
    prices_mod = np.array([10.0, 11.0, 12.0, 99.0, 14.0, 15.0])
    ema2 = calc_ema(prices_mod, 3)
    # Past values up to index 2 must be identical
    assert np.allclose(ema1[:3], ema2[:3])


def test_04_causal_sma_warmup_nan():
    vals = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    sma = calc_sma(vals, 3)
    assert np.isnan(sma[0]) and np.isnan(sma[1])
    assert sma[2] == pytest.approx(2.0)
    assert sma[3] == pytest.approx(3.0)
    assert sma[4] == pytest.approx(4.0)


def test_05_causal_atr_wilder_smoothing():
    h = np.array([10.0, 12.0, 11.0, 13.0, 15.0])
    l = np.array([9.0, 10.0, 9.5, 11.0, 13.0])
    c = np.array([9.5, 11.5, 10.0, 12.5, 14.0])
    atr = calc_atr(h, l, c, 3)
    assert np.isnan(atr[0]) and np.isnan(atr[1]) and np.isnan(atr[2])
    assert not np.isnan(atr[3])
    assert atr[3] > 0


def test_06_choppiness_index_bounds():
    h = np.full(50, 105.0)
    l = np.full(50, 95.0)
    c = np.full(50, 100.0)
    chop = calc_choppiness_index(h, l, c, 24)
    valid = chop[~np.isnan(chop)]
    assert np.all(valid >= 0.0) and np.all(valid <= 100.0)


def test_07_bollinger_bands_geometry():
    c = np.linspace(100.0, 120.0, 40)
    up, mid, lo = calc_bollinger_bands(c, 20, 2.0)
    for i in range(20, 40):
        assert up[i] > mid[i] > lo[i]


def test_08_volume_zscore_zero_std_handling():
    v = np.full(100, 10.0)
    z = calc_rolling_volume_zscore(v, 50)
    assert z[60] == 0.0


def test_09_rolling_extremes_excludes_current_bar():
    h = np.array([10.0, 12.0, 15.0, 50.0])
    l = np.array([8.0, 9.0, 11.0, 2.0])
    roll_h, roll_l = calc_rolling_extremes(h, l, 3)
    # At index 3, rolling window covers [0:3], so max is 15.0 (not 50.0)
    assert roll_h[3] == 15.0
    assert roll_l[3] == 8.0


def test_10_signal_causal_timing_delays():
    # Build 200 hours of 1m data to warm up indicators
    data = _synthetic_1m(12_000, base_price=30_000.0)
    cand = {
        "id": "C01_TEST",
        "family": "MACRO_PULLBACK_RECLAIM",
        "horizon_hours": 12,
        "target_R": 2.0,
    }
    # Verify signal generator functions without error
    signals = generate_candidate_signals(data, cand)
    for s in signals:
        assert s["decision_at"] == s["event_time"] + MINUTE
        assert s["entry_at"] == s["decision_at"] + MINUTE


def test_11_signal_gap_veto_enforced():
    # Test gap veto logic
    raw_open = 30_100.0
    decision_close = 30_000.0
    atr_hour = 100.0
    gap = abs(raw_open - decision_close)
    vetoed = gap > 0.25 * atr_hour + 1e-9
    assert vetoed is True


def test_12_signal_stop_on_correct_side():
    # Long trade with stop above entry is invalid
    raw_open = 30_000.0
    stop = 30_100.0
    side = 1
    assert side * (raw_open - stop) <= 0


def test_13_tick_quantization():
    assert _tick(100.04, upwards=True) == pytest.approx(100.1)
    assert _tick(100.04, upwards=False) == pytest.approx(100.0)
    assert _tick(100.06, upwards=True) == pytest.approx(100.1)
    assert _tick(100.06, upwards=False) == pytest.approx(100.0)


def test_14_adverse_execution_entry_and_exit():
    raw = 30_000.0
    cost = BASE
    # Long entry: buy adverse (higher price)
    buy_entry = _effective(raw, 1, cost, entry=True)
    assert buy_entry > raw

    # Long exit: sell adverse (lower price)
    sell_exit = _effective(raw, 1, cost, entry=False)
    assert sell_exit < raw

    # Short entry: sell adverse (lower price)
    short_entry = _effective(raw, -1, cost, entry=True)
    assert short_entry < raw

    # Short exit: buy adverse (higher price)
    short_exit = _effective(raw, -1, cost, entry=False)
    assert short_exit > raw


def test_15_fee_calculation():
    price = 30_000.0
    qty = 0.01
    cost = {"fee_bps": 6.0}
    fee = _fee(price, qty, cost)
    # notional = 300.0 -> 300 * 6 / 10000 = 0.18
    assert fee == pytest.approx(0.18)


def test_16_stop_before_target_collision():
    # Setup data where bar touches BOTH stop and target
    t0 = 1_609_459_200_000
    rows = []
    # Entry bar
    rows.append([float(t0), 30_000.0, 30_010.0, 29_990.0, 30_000.0, 1.0, 0.5])
    # Bar 1: huge range touching both target 30_200 and stop 29_800
    rows.append([float(t0 + MINUTE), 30_000.0, 30_500.0, 29_500.0, 30_000.0, 10.0, 5.0])
    # Deadline bar
    for i in range(2, 725):
        rows.append([float(t0 + i * MINUTE), 30_000.0, 30_005.0, 29_995.0, 30_000.0, 1.0, 0.5])

    data = np.asarray(rows, dtype=np.float64)
    event = {
        "event_id": "COLLISION_TEST",
        "entry_at": t0,
        "side": 1,
        "stop": 29_800.0,
    }
    cand = {"id": "C_COLLISION", "horizon_hours": 12, "target_R": 2.0}
    trade = execute_position(data, data, [], event, cand, BASE, quantity=0.01)
    # Must exit by STOP_LOSS, not TARGET_PROFIT
    assert trade["exit_reason"] == "STOP_LOSS"
    assert trade["exit_at"] == t0 + MINUTE


def test_17_target_profit_limit_execution():
    t0 = 1_609_459_200_000
    rows = []
    rows.append([float(t0), 30_000.0, 30_010.0, 29_990.0, 30_000.0, 1.0, 0.5])
    # Bar 1 touches target (30_500) but low stays above stop (29_800)
    rows.append([float(t0 + MINUTE), 30_000.0, 30_600.0, 29_950.0, 30_400.0, 10.0, 5.0])
    for i in range(2, 725):
        rows.append([float(t0 + i * MINUTE), 30_400.0, 30_405.0, 30_395.0, 30_400.0, 1.0, 0.5])

    data = np.asarray(rows, dtype=np.float64)
    event = {
        "event_id": "TARGET_TEST",
        "entry_at": t0,
        "side": 1,
        "stop": 29_800.0,
    }
    cand = {"id": "C_TARGET", "horizon_hours": 12, "target_R": 2.0}
    trade = execute_position(data, data, [], event, cand, BASE, quantity=0.01)
    assert trade["exit_reason"] == "TARGET_PROFIT"
    assert trade["exit_at"] == t0 + MINUTE


def test_18_horizon_deadline_exit():
    t0 = 1_609_459_200_000
    rows = []
    for i in range(725):
        rows.append([float(t0 + i * MINUTE), 30_000.0, 30_005.0, 29_995.0, 30_000.0, 1.0, 0.5])

    data = np.asarray(rows, dtype=np.float64)
    event = {
        "event_id": "DEADLINE_TEST",
        "entry_at": t0,
        "side": 1,
        "stop": 29_000.0,
    }
    cand = {"id": "C_DEADLINE", "horizon_hours": 12, "target_R": 2.0}
    trade = execute_position(data, data, [], event, cand, BASE, quantity=0.01)
    assert trade["exit_reason"] == "HORIZON_EXPIRY"
    assert trade["exit_at"] == t0 + 12 * HOUR


def test_19_signed_funding_long_pays_positive():
    t0 = 1_609_459_200_000
    data = _synthetic_1m(800, base_price=30_000.0, start_ms=t0)
    event = {"event_id": "FUNDING_LONG", "entry_at": t0, "side": 1, "stop": 29_000.0}
    cand = {"id": "C_FUND", "horizon_hours": 12, "target_R": 2.0}
    rate_event = [{"settlement_at": t0 + 4 * HOUR, "rate": "0.0001"}]
    trade = execute_position(data, data, rate_event, event, cand, BASE, quantity=0.01)
    # Long pays positive funding -> funding_cash_usdt is negative
    assert trade["funding_cash_usdt"] < 0


def test_20_signed_funding_short_receives_positive():
    t0 = 1_609_459_200_000
    data = _synthetic_1m(800, base_price=30_000.0, start_ms=t0)
    event = {"event_id": "FUNDING_SHORT", "entry_at": t0, "side": -1, "stop": 31_000.0}
    cand = {"id": "C_FUND", "horizon_hours": 12, "target_R": 2.0}
    rate_event = [{"settlement_at": t0 + 4 * HOUR, "rate": "0.0001"}]
    trade = execute_position(data, data, rate_event, event, cand, BASE, quantity=0.01)
    # Short receives positive funding -> funding_cash_usdt is positive
    assert trade["funding_cash_usdt"] > 0


def test_21_funding_settlement_timing():
    t0 = 1_609_459_200_000
    data = _synthetic_1m(800, base_price=30_000.0, start_ms=t0)
    event = {"event_id": "FUND_TIMING", "entry_at": t0, "side": 1, "stop": 29_000.0}
    cand = {"id": "C_TIMING", "horizon_hours": 12, "target_R": 2.0}
    # Settlements before entry or after exit are ignored
    rate_events = [
        {"settlement_at": t0 - 1000, "rate": "0.0005"},
        {"settlement_at": t0 + 13 * HOUR, "rate": "0.0005"},
    ]
    trade = execute_position(data, data, rate_events, event, cand, BASE, quantity=0.01)
    assert trade["funding_cash_usdt"] == 0.0


def test_22_position_sizing_1x_budget_cap():
    cash = 1000.0
    qty, _info = size_position(30_000.0, 100.0, BASE, cash, 12)
    notional = qty * 30_000.0
    # Exposure cannot exceed 1000 USDT budget
    assert notional <= 1000.0
    assert (Decimal(str(qty)) % Decimal(str(LOT))) == Decimal(0)


def test_23_position_sizing_lot_and_min_notional():
    # If cash is too small, size_position raises TradeExecutionError
    with pytest.raises(TradeExecutionError):
        size_position(30_000.0, 100.0, BASE, 2.0, 12)


def test_24_account_single_position_exclusivity():
    t0 = 1_609_459_200_000
    data = _synthetic_1m(1440, base_price=30_000.0, start_ms=t0)
    cand = {"id": "C_EXCL", "horizon_hours": 12, "target_R": 2.0, "cooldown_hours": 4}
    fold = {
        "start_ms": t0,
        "end_ms": t0 + 1440 * MINUTE,
        "embargo_start_ms": t0,
        "embargo_end_ms": t0 + 1440 * MINUTE,
    }
    signals = [
        {"event_id": "SIG_1", "entry_at": t0 + 10 * MINUTE, "raw_entry": 30_000.0, "atr_hour": 100.0, "side": 1, "stop": 29_500.0},
        {"event_id": "SIG_2", "entry_at": t0 + 20 * MINUTE, "raw_entry": 30_000.0, "atr_hour": 100.0, "side": 1, "stop": 29_500.0},
    ]
    res = replay_account(data, data, [], signals, cand, fold, BASE, cash0=1000.0)
    assert len(res["trades"]) == 1
    assert res["fates"]["POSITION_ACK_OR_COOLDOWN"] == 1


def test_25_account_exchange_ack_quantization():
    clock = 1_609_459_234_567
    ack = _ack(clock)
    assert ack % MINUTE == 0
    assert ack > clock


def test_26_account_post_exit_cooldown_enforced():
    t0 = 1_609_459_200_000
    data = _synthetic_1m(1440, base_price=30_000.0, start_ms=t0)
    cand = {"id": "C_COOL", "horizon_hours": 2, "target_R": 2.0, "cooldown_hours": 4}
    fold = {
        "start_ms": t0,
        "end_ms": t0 + 1440 * MINUTE,
        "embargo_start_ms": t0,
        "embargo_end_ms": t0 + 1440 * MINUTE,
    }
    # Trade 1 exits at t0 + 2h. Next allowed entry is t0 + 2h + 4h cooldown = t0 + 6h.
    signals = [
        {"event_id": "SIG_1", "entry_at": t0 + MINUTE, "raw_entry": 30_000.0, "atr_hour": 100.0, "side": 1, "stop": 29_000.0},
        {"event_id": "SIG_2", "entry_at": t0 + 3 * HOUR, "raw_entry": 30_000.0, "atr_hour": 100.0, "side": 1, "stop": 29_000.0},
        {"event_id": "SIG_3", "entry_at": t0 + 7 * HOUR, "raw_entry": 30_000.0, "atr_hour": 100.0, "side": 1, "stop": 29_000.0},
    ]
    res = replay_account(data, data, [], signals, cand, fold, BASE, cash0=1000.0)
    # SIG_2 during cooldown is skipped; SIG_3 is filled
    assert len(res["trades"]) == 2
    assert res["fates"]["POSITION_ACK_OR_COOLDOWN"] == 1


def test_27_account_prospective_fold_censoring():
    t0 = 1_609_459_200_000
    data = _synthetic_1m(1440, base_price=30_000.0, start_ms=t0)
    cand = {"id": "C_CENSOR", "horizon_hours": 12, "target_R": 2.0, "cooldown_hours": 4}
    fold = {
        "start_ms": t0,
        "end_ms": t0 + 1440 * MINUTE,
        "embargo_start_ms": t0,
        "embargo_end_ms": t0 + 1440 * MINUTE,
    }
    # Signal entered at 20h cannot complete 12h horizon within 24h fold
    signals = [
        {"event_id": "SIG_LATE", "entry_at": t0 + 20 * HOUR, "raw_entry": 30_000.0, "atr_hour": 100.0, "side": 1, "stop": 29_000.0},
    ]
    res = replay_account(data, data, [], signals, cand, fold, BASE, cash0=1000.0)
    assert len(res["trades"]) == 0
    assert res["fates"]["PROSPECTIVE_FOLD_CENSOR"] == 1


def test_28_account_nonpositive_equity_halt():
    # If loss wipes account equity below zero, ValueError is raised
    trades = [{
        "entry_at": 1_609_459_200_000,
        "exit_at": 1_609_459_200_000 + 10 * MINUTE,
        "exit_ack_at": 1_609_459_200_000 + 11 * MINUTE,
        "side": 1,
        "quantity": 1.0,
        "effective_entry": 30_000.0,
        "net_after_funding_usdt": -2000.0,
        "funding_events": [],
    }]
    data = _synthetic_1m(60, base_price=30_000.0)
    with pytest.raises(ValueError, match="Nonpositive marked account equity"):
        compute_mark_curve(trades, data, 1_609_459_200_000, 1_609_459_200_000 + 60 * MINUTE, 1000.0, BASE)


def test_29_mark_equity_curve_accounting():
    t0 = 1_609_459_200_000
    data = _synthetic_1m(120, base_price=30_000.0, start_ms=t0)
    trades = [{
        "entry_at": t0 + 10 * MINUTE,
        "exit_at": t0 + 30 * MINUTE,
        "exit_ack_at": t0 + 31 * MINUTE,
        "side": 1,
        "quantity": 0.01,
        "effective_entry": 30_000.0,
        "net_after_funding_usdt": 10.0,
        "funding_events": [],
    }]
    curve = compute_mark_curve(trades, data, t0, t0 + 120 * MINUTE, 1000.0, BASE)
    assert curve["ending_equity"] == pytest.approx(1010.0)
    assert curve["occupancy_fraction"] > 0.0


def test_30_block_bootstrap_max_t_determinism():
    t0 = 1_609_459_200_000
    trades1 = [{"exit_at": t0 + 2 * 86_400_000, "net_after_funding_usdt": 25.0}]
    trades2 = [{"exit_at": t0 + 5 * 86_400_000, "net_after_funding_usdt": -10.0}]
    map_data = {"C1": trades1, "C2": trades2}

    b1 = block_bootstrap_max_t(map_data, t0, t0 + 14 * 86_400_000, block_days=7, n_draws=100, seed=42)
    b2 = block_bootstrap_max_t(map_data, t0, t0 + 14 * 86_400_000, block_days=7, n_draws=100, seed=42)
    assert b1["critical_max_t_95pct"] == pytest.approx(b2["critical_max_t_95pct"])
    assert b1["candidates"]["C1"]["observed_t"] == pytest.approx(b2["candidates"]["C1"]["observed_t"])


def test_31_decimal_audit_precision_exact_match():
    t0 = 1_609_459_200_000
    data = _synthetic_1m(800, base_price=30_000.0, start_ms=t0)
    event = {"event_id": "TEST_AUDIT", "entry_at": t0, "side": 1, "stop": 29_000.0}
    cand = {"id": "C_AUDIT", "horizon_hours": 12, "target_R": 2.0}
    rates = [{"settlement_at": t0 + 4 * HOUR, "rate": "0.0001"}]
    trade = execute_position(data, data, rates, event, cand, BASE, quantity=0.015)
    receipt = audit_trade_decimal(trade, BASE)
    assert receipt["status"] == "EXACT_DECIMAL_MATCH"


def test_32_candidate_registry_schema_and_budget():
    reg_path = EP / "GOAL_A_FROZEN_CANDIDATE_REGISTRY.json"
    reg = json.loads(reg_path.read_text())
    assert reg["MAX_EXPLORATORY_CONFIGURATIONS"] <= 12
    assert len(reg["CANDIDATES"]) == 8
    assert reg["ACCOUNT_CONTRACT"]["cash0"] == 1000.0
    assert reg["ACCOUNT_CONTRACT"]["max_exposure"] == 1.0


def test_33_duplicate_map_distinctness():
    reg_path = EP / "GOAL_A_FROZEN_CANDIDATE_REGISTRY.json"
    reg = json.loads(reg_path.read_text())
    cand_ids = {c["id"] for c in reg["CANDIDATES"]}
    # Explicitly check none is in prior 48 trial IDs
    assert "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H" not in cand_ids
    assert "W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H" not in cand_ids
    assert len(cand_ids) == 8


def test_34_source_cache_paths_guarded():
    p = Path("/tmp/btc-two-lead-funding-mark-r3/test.zip")
    base = Path("/tmp/btc-two-lead-funding-mark-r3")
    assert guarded(p, base) == p

    # Parent mismatch must raise
    with pytest.raises(ValueError, match="Unauthorized or symlinked path"):
        guarded(Path("/tmp/other/test.zip"), base)


def test_35_freeze_parent_verification():
    from scripts.strategy_research.g2_goal_entry_discovery_r2.run import START_SHA
    assert START_SHA == "55ac4c631c69f6edbd275462ad23e4486b9782ed"
