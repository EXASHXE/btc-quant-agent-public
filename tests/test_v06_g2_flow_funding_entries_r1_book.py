"""Synthetic tests for order mechanics, fill priority, quarter-ATR gap veto, and funding cashflow attribution."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategy_research.g2_flow_funding_entries_r1.book import (
    BASE,
    HOUR,
    MINUTE,
    _effective,
    _tick,
    execute_position,
    mark_close_asof,
    propose_entry,
)


def _mock_path(n_minutes: int = 1000, start_ms: int = 1609459200000, base_price: float = 30000.0) -> tuple[np.ndarray, np.ndarray]:
    times = start_ms + np.arange(n_minutes, dtype=np.int64) * MINUTE
    last = np.empty((n_minutes, 7), dtype=np.float64)
    last[:, 0] = times
    last[:, 1] = base_price
    last[:, 2] = base_price + 5.0
    last[:, 3] = base_price - 5.0
    last[:, 4] = base_price
    last[:, 5] = 100.0
    last[:, 6] = 50.0

    mark = np.empty((n_minutes, 5), dtype=np.float64)
    mark[:, 0] = times
    mark[:, 1] = base_price
    mark[:, 2] = base_price + 5.0
    mark[:, 3] = base_price - 5.0
    mark[:, 4] = base_price

    return last, mark


def test_tick_rounding_semantics() -> None:
    """0.1 tick rounding: ceiling for buy/stop-short, floor for sell/stop-long."""
    # Ceiling upwards
    assert _tick(100.01, upwards=True) == 100.1
    assert _tick(100.09, upwards=True) == 100.1
    assert _tick(100.00, upwards=True) == 100.0

    # Floor downwards
    assert _tick(100.09, upwards=False) == 100.0
    assert _tick(100.01, upwards=False) == 100.0
    assert _tick(100.10, upwards=False) == 100.1


def test_effective_price_adverse_impact() -> None:
    """_effective prices are strictly worse for the trader on entry and exit."""
    raw = 30000.0
    # Buy entry: price > raw
    buy_entry = _effective(raw, side=1, cost=BASE, entry=True)
    assert buy_entry > raw

    # Sell exit: price < raw
    sell_exit = _effective(raw, side=1, cost=BASE, entry=False)
    assert sell_exit < raw

    # Sell short entry: price < raw
    short_entry = _effective(raw, side=-1, cost=BASE, entry=True)
    assert short_entry < raw

    # Buy cover exit: price > raw
    short_exit = _effective(raw, side=-1, cost=BASE, entry=False)
    assert short_exit > raw


def test_quarter_atr_gap_veto() -> None:
    """propose_entry raises error if open diverges from decision close by > 0.25 ATR."""
    last, _ = _mock_path(n_minutes=20)
    t0 = int(last[0, 0])
    event = {
        "event_time": t0 + 5 * MINUTE,
        "decision_at": t0 + 6 * MINUTE,
        "entry_at": t0 + 7 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,  # 0.25 * ATR = 25.0
        "stop": 29850.0,
        "side": 1,
    }
    cand = {"horizon_hours": 12, "target_r": 2.0}

    # Open divergence of 20 (within 25) passes
    last[7, 1] = 30020.0
    p = propose_entry(last, event, cand, BASE)
    assert p["raw_entry"] == 30020.0

    # Open divergence of 30 (> 25) fails
    last[7, 1] = 30030.0
    with pytest.raises(ValueError, match="quarter-hour-ATR gap veto"):
        propose_entry(last, event, cand, BASE)


def test_stop_gap_priority() -> None:
    """Opening gap adverse through stop triggers STOP_GAP fill at open."""
    last, mark = _mock_path(n_minutes=50)
    t0 = int(last[0, 0])
    event = {
        "event_id": "test_stop_gap",
        "event_time": t0 + 5 * MINUTE,
        "decision_at": t0 + 6 * MINUTE,
        "entry_at": t0 + 7 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    cand = {"id": "test", "horizon_hours": 12, "target_r": 2.0}

    # At minute 15, open gaps below stop (to 29800)
    last[15, 1] = 29800.0
    last[15, 2] = 29820.0
    last[15, 3] = 29790.0
    last[15, 4] = 29810.0

    trade = execute_position(last, mark, [], event, cand, BASE, quantity=0.01)
    assert trade["exit_reason"] == "STOP_GAP"
    assert trade["raw_exit"] == 29800.0
    assert trade["exit_at"] == int(last[15, 0])


def test_target_gap_capped_priority() -> None:
    """Opening gap favorable through target triggers TARGET_GAP_CAPPED fill capped at target."""
    last, mark = _mock_path(n_minutes=50)
    t0 = int(last[0, 0])
    event = {
        "event_id": "test_target_gap",
        "event_time": t0 + 5 * MINUTE,
        "decision_at": t0 + 6 * MINUTE,
        "entry_at": t0 + 7 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    cand = {"id": "test", "horizon_hours": 12, "target_r": 2.0}

    # Target is approx 30300. At minute 15, open gaps to 30400
    last[15, 1] = 30400.0
    last[15, 2] = 30450.0
    last[15, 3] = 30390.0
    last[15, 4] = 30420.0

    trade = execute_position(last, mark, [], event, cand, BASE, quantity=0.01)
    assert trade["exit_reason"] == "TARGET_GAP_CAPPED"
    assert trade["raw_exit"] == trade["target"]


def test_same_minute_stop_precedes_target() -> None:
    """When both stop and target are touched within the same minute, STOP takes precedence."""
    last, mark = _mock_path(n_minutes=50)
    t0 = int(last[0, 0])
    event = {
        "event_id": "test_collision",
        "event_time": t0 + 5 * MINUTE,
        "decision_at": t0 + 6 * MINUTE,
        "entry_at": t0 + 7 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    cand = {"id": "test", "horizon_hours": 12, "target_r": 2.0}

    # At minute 12, high reaches target (30350) AND low breaches stop (29800)
    last[12, 1] = 30000.0
    last[12, 2] = 30500.0  # target reached
    last[12, 3] = 29800.0  # stop reached
    last[12, 4] = 30000.0

    trade = execute_position(last, mark, [], event, cand, BASE, quantity=0.01)
    assert trade["exit_reason"] == "STOP"
    assert trade["raw_exit"] == trade["stop"]


def test_time_cap_expiration() -> None:
    """When position reaches deadline without hitting stop or target, TIME_CAP triggers."""
    # 12 hours = 720 minutes
    last, mark = _mock_path(n_minutes=800)
    t0 = int(last[0, 0])
    event = {
        "event_id": "test_time_cap",
        "event_time": t0 + 5 * MINUTE,
        "decision_at": t0 + 6 * MINUTE,
        "entry_at": t0 + 7 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    cand = {"id": "test", "horizon_hours": 12, "target_r": 2.0}

    trade = execute_position(last, mark, [], event, cand, BASE, quantity=0.01)
    assert trade["exit_reason"] == "TIME_CAP"
    assert trade["exit_at"] == event["entry_at"] + 12 * HOUR


def test_funding_cashflow_long_position() -> None:
    """Long position pays positive funding rate and receives negative funding rate."""
    last, mark = _mock_path(n_minutes=800)
    t0 = int(last[0, 0])
    entry_at = t0 + 7 * MINUTE
    event = {
        "event_id": "test_funding_long",
        "event_time": t0 + 5 * MINUTE,
        "decision_at": t0 + 6 * MINUTE,
        "entry_at": entry_at,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,  # Long
    }
    cand = {"id": "test", "horizon_hours": 12, "target_r": 2.0}

    # Settle funding at entry + 4 hours (within trade holding)
    t_settle = entry_at + 4 * HOUR
    funding_events = [
        {"settlement_at": t_settle, "rate": "0.00010000", "interval_hours": "8.0"}
    ]

    trade = execute_position(last, mark, funding_events, event, cand, BASE, quantity=0.01)
    assert trade["funding_events_count"] == 1
    # Rate is +0.0001: long pays, so funding cashflow is negative
    assert trade["funding_usdt"] < 0
    # Expected: -1 * 0.01 * 30000 * 0.0001 = -0.03
    assert abs(trade["funding_usdt"] - (-0.03)) < 1e-4


def test_funding_cashflow_short_position() -> None:
    """Short position receives positive funding rate and pays negative funding rate."""
    last, mark = _mock_path(n_minutes=800)
    t0 = int(last[0, 0])
    entry_at = t0 + 7 * MINUTE
    event = {
        "event_id": "test_funding_short",
        "event_time": t0 + 5 * MINUTE,
        "decision_at": t0 + 6 * MINUTE,
        "entry_at": entry_at,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 30150.0,
        "side": -1,  # Short
    }
    cand = {"id": "test", "horizon_hours": 12, "target_r": 2.0}

    t_settle = entry_at + 4 * HOUR
    funding_events = [
        {"settlement_at": t_settle, "rate": "0.00010000", "interval_hours": "8.0"}
    ]

    trade = execute_position(last, mark, funding_events, event, cand, BASE, quantity=0.01)
    assert trade["funding_events_count"] == 1
    # Rate is +0.0001: short receives, so funding cashflow is positive
    assert trade["funding_usdt"] > 0
    # Expected: -(-1) * 0.01 * 30000 * 0.0001 = +0.03
    assert abs(trade["funding_usdt"] - 0.03) < 1e-4


def test_funding_outside_trade_interval_ignored() -> None:
    """Funding events before entry or after exit are strictly ignored."""
    last, mark = _mock_path(n_minutes=800)
    t0 = int(last[0, 0])
    entry_at = t0 + 7 * MINUTE
    event = {
        "event_id": "test_funding_ignored",
        "event_time": t0 + 5 * MINUTE,
        "decision_at": t0 + 6 * MINUTE,
        "entry_at": entry_at,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    cand = {"id": "test", "horizon_hours": 12, "target_r": 2.0}

    funding_events = [
        {"settlement_at": entry_at - HOUR, "rate": "0.001", "interval_hours": "8.0"},  # before
        {"settlement_at": entry_at + 15 * HOUR, "rate": "0.001", "interval_hours": "8.0"},  # after 12h cap
    ]

    trade = execute_position(last, mark, funding_events, event, cand, BASE, quantity=0.01)
    assert trade["funding_events_count"] == 0
    assert trade["funding_usdt"] == 0.0


def test_mark_close_asof_clock() -> None:
    """mark_close_asof returns strictly completed 1m close before or at timestamp."""
    _, mark = _mock_path(n_minutes=60)
    t0 = int(mark[0, 0])
    # Timestamp at exact minute open (e.g. minute 10:00:00)
    t_target = t0 + 10 * MINUTE
    _price, close_at = mark_close_asof(mark, t_target)
    # The latest completed close must be the minute ending at t_target - 1ms
    assert close_at == t_target - 1
    assert close_at <= t_target
