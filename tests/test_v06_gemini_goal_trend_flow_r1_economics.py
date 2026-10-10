"""Comprehensive unit tests for execution economics, cost accounting, and anti-lookahead rules."""
from __future__ import annotations

import math
from decimal import Decimal
import numpy as np
import pytest

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.audit import (
    audit_single_trade,
    d,
    rounded,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.metrics import (
    compute_drawdown,
    block_bootstrap,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    MINUTE,
    STRESS,
    TICK,
    _effective,
    _fee,
    _proposed,
    _tick,
    episode,
    simulate_fold,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.signals import (
    aggregate_bars,
    _atr_fast,
    _ema_fast,
)


def test_01_tick_rounding_adverse():
    """Verify tick rounding ceiling for buy and floor for sell."""
    assert np.isclose(_tick(100.04, upwards=True), 100.1)
    assert np.isclose(_tick(100.06, upwards=False), 100.0)
    assert np.isclose(_tick(100.10, upwards=True), 100.1)
    assert np.isclose(_tick(100.10, upwards=False), 100.1)


def test_02_effective_price_costs():
    """Verify spread and slip adverse shifts for entry and exit under BASE and STRESS."""
    raw = 50000.0
    eff_long_entry = _effective(raw, side=1, cost=BASE, entry=True)
    assert np.isclose(eff_long_entry, 50060.0)  # 50000 * (1 + (2 + 10)/10000) = 50060.0

    eff_long_exit = _effective(raw, side=1, cost=BASE, entry=False)
    assert np.isclose(eff_long_exit, 49940.0)  # 50000 * (1 - (2 + 10)/10000) = 49940.0

    assert np.isclose(_effective(raw, side=1, cost=STRESS, entry=True), 50150.0)  # 50000 * (1 + 30/10000)
    assert np.isclose(_effective(raw, side=1, cost=STRESS, entry=False), 49850.0)


def test_03_fee_deducted_properly():
    """Verify fee calculation on notional traded."""
    price = 50000.0
    qty = 0.02
    fee = _fee(price, qty, STRESS)
    assert abs(fee - 1.0) < 1e-9  # 1000 * 10 / 10000 = 1.0


def test_04_stop_before_target_same_minute():
    """Verify STOP collision priority over TARGET within the same minute."""
    t0 = 1609459200000
    data = np.zeros((10, 7), dtype=np.float64)
    for i in range(10):
        data[i, 0] = t0 + i * 60000
        data[i, 1] = 50000.0
        data[i, 2] = 50050.0
        data[i, 3] = 49950.0
        data[i, 4] = 50000.0
        data[i, 5] = 100.0
        data[i, 6] = 50.0

    # At bar index 4 (entry is at index 2), both stop (49500) and target (51000) are touched:
    data[4, 2] = 51500.0
    data[4, 3] = 49000.0

    event = {
        "event_id": "TEST_COL",
        "side": 1,
        "event_time": t0,
        "decision_at": t0 + 60000,
        "entry_at": t0 + 120000,  # index 2
        "stop": 49500.0,
        "target_r": 2.0,
        "decision_close": 50000.0,
        "atr_hour": 500.0,
    }
    cand = {"id": "TEST_CAND", "horizon_hours": 4, "target_R": 2.0}

    tr = episode(data, event, cand, BASE, quantity=1.0)
    assert tr["exit_reason"] == "STOP"
    assert tr["raw_exit"] == 49500.0


def test_05_adverse_stop_gap_worse_open():
    """Verify adverse stop gap is filled at the worse open price."""
    t0 = 1609459200000
    data = np.zeros((10, 7), dtype=np.float64)
    for i in range(10):
        data[i, 0] = t0 + i * 60000
        data[i, 1] = 50000.0
        data[i, 2] = 50050.0
        data[i, 3] = 49950.0
        data[i, 4] = 50000.0
        data[i, 5] = 100.0
        data[i, 6] = 50.0

    # Entry is at index 2. At index 4, market gaps open down to 49200 (worse than stop 49500):
    data[4, 1] = 49200.0
    data[4, 2] = 49300.0
    data[4, 3] = 49100.0
    data[4, 4] = 49250.0

    event = {
        "event_id": "TEST_SG",
        "side": 1,
        "event_time": t0,
        "decision_at": t0 + 60000,
        "entry_at": t0 + 120000,
        "stop": 49500.0,
        "target_r": 2.0,
        "decision_close": 50000.0,
        "atr_hour": 500.0,
    }
    cand = {"id": "TEST_CAND", "horizon_hours": 4, "target_R": 2.0}

    tr = episode(data, event, cand, BASE, quantity=1.0)
    assert tr["exit_reason"] == "STOP_GAP"
    assert tr["raw_exit"] == 49200.0


def test_06_target_gap_capped():
    """Verify favorable target gap is capped at limit target price."""
    t0 = 1609459200000
    data = np.zeros((10, 7), dtype=np.float64)
    for i in range(10):
        data[i, 0] = t0 + i * 60000
        data[i, 1] = 50000.0
        data[i, 2] = 50050.0
        data[i, 3] = 49950.0
        data[i, 4] = 50000.0
        data[i, 5] = 100.0
        data[i, 6] = 50.0

    # Entry at index 2. At index 4, market gaps open to 52000:
    data[4, 1] = 52000.0
    data[4, 2] = 52500.0
    data[4, 3] = 51900.0
    data[4, 4] = 52200.0

    event = {
        "event_id": "TEST_TG",
        "side": 1,
        "event_time": t0,
        "decision_at": t0 + 60000,
        "entry_at": t0 + 120000,
        "stop": 49500.0,
        "target_r": 2.0,
        "decision_close": 50000.0,
        "atr_hour": 500.0,
    }
    cand = {"id": "TEST_CAND", "horizon_hours": 4, "target_R": 2.0}

    tr = episode(data, event, cand, BASE, quantity=1.0)
    assert tr["exit_reason"] == "TARGET_GAP_CAPPED"
    assert tr["raw_exit"] == tr["target"]


def test_07_time_cap_deadline():
    """Verify trade exits at timecap deadline."""
    t0 = 1609459200000
    data = np.zeros((300, 7), dtype=np.float64)
    for i in range(300):
        data[i, 0] = t0 + i * 60000
        data[i, 1] = 50000.0
        data[i, 2] = 50050.0
        data[i, 3] = 49950.0
        data[i, 4] = 50000.0
        data[i, 5] = 100.0
        data[i, 6] = 50.0

    event = {
        "event_id": "TEST_TC",
        "side": 1,
        "event_time": t0,
        "decision_at": t0 + 60000,
        "entry_at": t0 + 120000,
        "stop": 49000.0,
        "target_r": 2.0,
        "decision_close": 50000.0,
        "atr_hour": 500.0,
    }
    cand = {"id": "TEST_CAND", "horizon_hours": 4, "target_R": 2.0}

    tr = episode(data, event, cand, BASE, quantity=1.0)
    assert tr["exit_reason"] == "TIME_CAP"
    assert (tr["exit_at"] - tr["entry_at"]) == 4 * 3600_000


def test_08_quarter_atr_gap_veto():
    """Verify entry vetoed if open gap > 0.25 * ATR."""
    t0 = 1609459200000
    data = np.zeros((10, 7), dtype=np.float64)
    for i in range(10):
        data[i, 0] = t0 + i * 60000
        data[i, 1] = 50000.0
        data[i, 2] = 50050.0
        data[i, 3] = 49950.0
        data[i, 4] = 50000.0
        data[i, 5] = 100.0
        data[i, 6] = 50.0

    # Decision close was 49800, ATR is 400 (quarter ATR is 100).
    # Actual entry open at index 2 is 50000 (gap = 200 > 100) -> vetoed!
    event = {
        "event_id": "TEST_VETO",
        "side": 1,
        "event_time": t0,
        "decision_at": t0 + 60000,
        "entry_at": t0 + 120000,
        "stop": 49000.0,
        "target_r": 2.0,
        "decision_close": 49800.0,
        "atr_hour": 400.0,
    }
    cand = {"id": "TEST_CAND", "horizon_hours": 4, "target_R": 2.0}

    with pytest.raises(ValueError, match="late entry breached quarter-hour-ATR gap veto"):
        _proposed(data[:, :6], event, cand, BASE)


def test_09_cash_accounting_conservation():
    """Verify final cash strictly equals initial capital plus sum of net USDT."""
    t0 = 1609459200000
    data = np.zeros((100, 7), dtype=np.float64)
    for i in range(100):
        data[i, 0] = t0 + i * 60000
        data[i, 1] = 50000.0
        data[i, 2] = 50050.0
        data[i, 3] = 49950.0
        data[i, 4] = 50000.0
        data[i, 5] = 100.0
        data[i, 6] = 50.0

    data[10, 3] = 49000.0

    event = {
        "event_id": "TEST_SIM",
        "side": 1,
        "event_time": t0,
        "decision_at": t0 + 60000,
        "entry_at": t0 + 120000,
        "stop": 49500.0,
        "target_r": 2.0,
        "decision_close": 50000.0,
        "atr_hour": 500.0,
    }
    cand = {"id": "TEST_CAND", "horizon_hours": 4, "target_R": 2.0, "cooldown_hours": 1}
    fold = {"start_ms": t0 + 120000, "end_ms": t0 + 90 * 60000, "year": 2021, "month": 1}

    res = simulate_fold(data, [event], cand, fold, STRESS, initial_equity=1000.0)
    assert len(res["trades"]) == 1
    tr = res["trades"][0]
    expected_end = 1000.0 + tr["net_usdt"]
    assert abs(res["ending_equity"] - expected_end) < 1e-6


def test_10_decimal_audit_verification():
    """Verify independent Decimal walkthrough matches trade output."""
    t0 = 1609459200000
    data = np.zeros((20, 7), dtype=np.float64)
    for i in range(20):
        data[i, 0] = t0 + i * 60000
        data[i, 1] = 50000.0
        data[i, 2] = 50050.0
        data[i, 3] = 49950.0
        data[i, 4] = 50000.0
        data[i, 5] = 100.0
        data[i, 6] = 50.0

    data[5, 2] = 52000.0  # target hit

    event = {
        "event_id": "TEST_AUD",
        "side": 1,
        "event_time": t0,
        "decision_at": t0 + 60000,
        "entry_at": t0 + 120000,
        "stop": 49500.0,
        "target_r": 2.0,
        "decision_close": 50000.0,
        "atr_hour": 500.0,
    }
    cand = {"id": "TEST_CAND", "horizon_hours": 4, "target_R": 2.0}

    tr = episode(data, event, cand, STRESS, quantity=0.02)
    audit = audit_single_trade(data, tr, STRESS)
    assert audit["assertions"] == "PASS"
    assert audit["exit_reason"] == "TARGET"


def test_11_aggregation_and_anti_lookahead():
    """Verify 1m bar aggregation with taker volume and strict closed bar availability."""
    t0 = 1609459200000
    data = np.zeros((15, 7), dtype=np.float64)
    for i in range(15):
        data[i, 0] = t0 + i * 60000
        data[i, 1] = 100.0
        data[i, 2] = 110.0
        data[i, 3] = 90.0
        data[i, 4] = 105.0
        data[i, 5] = 10.0
        data[i, 6] = 6.0

    agg = aggregate_bars(data, 15)
    assert len(agg["end_ms"]) == 1
    assert agg["volume"][0] == 150.0
    assert agg["taker_buy_volume"][0] == 90.0
    assert abs(agg["signed_flow_ratio"][0] - 0.20) < 1e-6
    assert agg["end_ms"][0] == t0 + 15 * 60000 - 1


def test_12_drawdown_computation():
    """Verify accurate maximum drawdown percentage calculation."""
    curve = [1000.0, 1100.0, 1050.0, 990.0, 1200.0]
    dd = compute_drawdown(curve)
    # Peak was 1100.0, trough was 990.0: dd = (1100 - 990) / 1100 = 110 / 1100 = 10.0%
    assert abs(dd - 10.0) < 1e-6


def test_13_block_bootstrap_reproducibility():
    """Verify block bootstrap reproducibility with random seed."""
    trades = [
        {"entry_at": 1609459200000 + i * 86400000, "net_bps": float(i % 10 - 4)}
        for i in range(50)
    ]
    res1 = block_bootstrap(trades, block_days=7, n_iter=500, seed=123)
    res2 = block_bootstrap(trades, block_days=7, n_iter=500, seed=123)
    assert np.isclose(res1["mean"], res2["mean"])
    assert np.isclose(res1["lcb_95"], res2["lcb_95"])
