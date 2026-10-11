"""Synthetic reference checks for the corrected Goal-A account and clock model."""
from decimal import Decimal

import numpy as np
import pytest

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    MINUTE,
    STRESS,
    _effective,
    _fee,
    episode,
    simulate_fold,
)

T0 = 1_609_459_200_000


def bars(count=300, price=50000.0):
    data = np.zeros((count, 6), dtype=float)
    data[:, 0] = T0 + np.arange(count) * MINUTE
    data[:, 1:5] = price
    return data


def event(side=1, entry=2, stop_distance=1000.0, price=50000.0):
    return {
        "event_id": f"event-{entry}", "side": side,
        "event_time": T0 + (entry - 2) * MINUTE,
        "decision_at": T0 + (entry - 1) * MINUTE,
        "entry_at": T0 + entry * MINUTE,
        "decision_close": price, "atr_hour": 1000.0,
        "stop": price - side * stop_distance,
    }


CAND = {"id": "synthetic", "horizon_hours": 4, "target_R": 2.0, "cooldown_hours": 1}


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("cost,expected", [(BASE, Decimal(22)), (STRESS, Decimal(44))])
def test_flat_price_reference_roundtrip(side, cost, expected):
    raw = Decimal(50000)
    entry = Decimal(str(_effective(float(raw), side, cost, True)))
    exit_ = Decimal(str(_effective(float(raw), side, cost, False)))
    q = Decimal("0.02")
    fee = Decimal(str(_fee(float(entry), float(q), cost))) + Decimal(str(_fee(float(exit_), float(q), cost)))
    net = Decimal(side) * (exit_ - entry) * q - fee
    assert abs(net / (raw * q) * 10000 + expected) < Decimal("0.0000001")


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("cost", [BASE, STRESS])
def test_actual_notional_fees_partial_quantity_and_ack(side, cost):
    data = bars()
    tr = episode(data, event(side), CAND, cost, quantity=0.013)
    assert tr["exit_reason"] == "TIME_CAP"
    assert tr["exit_ack_at"] > tr["exit_at"]
    assert tr["fee_entry"] == pytest.approx(tr["effective_entry"] * 0.013 * cost["fee_bps"] / 10000)
    assert tr["fee_exit"] == pytest.approx(tr["effective_exit"] * 0.013 * cost["fee_bps"] / 10000)
    assert tr["net_bps"] == pytest.approx(-cost["nominal_roundtrip_bps"])


def test_stop_gap_and_target_cap_are_adverse_or_capped():
    data = bars()
    data[3, 1:5] = [48000, 48000, 48000, 48000]
    tr = episode(data, event(), CAND, BASE)
    assert (tr["exit_reason"], tr["raw_exit"]) == ("STOP_GAP", 48000)
    data = bars()
    data[3, 1:5] = [55000, 55000, 55000, 55000]
    tr = episode(data, event(), CAND, BASE)
    assert tr["exit_reason"] == "TARGET_GAP_CAPPED"
    assert tr["raw_exit"] == tr["target"]


def test_matched_opposite_side_keeps_event_quantity_distance_and_hold():
    data = bars()
    actual = episode(data, event(), CAND, BASE, quantity=0.013)
    control = episode(data, event(), CAND, BASE, quantity=0.013, side_override=-1)
    assert actual["entry_at"] == control["entry_at"]
    assert actual["quantity"] == control["quantity"]
    assert actual["side"] == -control["side"]
    assert actual["duration_minutes"] == control["duration_minutes"]
    assert abs(actual["raw_entry"] - actual["stop"]) == abs(control["raw_entry"] - control["stop"])


def test_intraminute_close_mark_exposes_loss_hidden_by_flat_exit():
    data = bars()
    data[10, 3:5] = [49500, 49600]
    data[11, 1:5] = [50000] * 4
    fold = {"start_ms": T0 + 2 * MINUTE, "end_ms": T0 + 260 * MINUTE}
    result = simulate_fold(data, [event()], CAND, fold, BASE)
    assert len(result["trades"]) == 1
    assert result["max_mtm_drawdown_pct"] > result["trade_close_drawdown_pct"]


def test_sizing_reserve_and_ack_blocks_same_minute_reentry():
    data = bars(500)
    data[3, 3] = 49000
    fold = {"start_ms": T0 + 2 * MINUTE, "end_ms": T0 + 490 * MINUTE}
    result = simulate_fold(data, [event(entry=2), event(entry=3), event(entry=4)], CAND, fold, STRESS)
    assert len(result["trades"]) == 1
    assert result["trades"][0]["entry_notional"] <= 950.0
    assert result["trades"][0]["quantity"] * result["trades"][0]["effective_entry"] <= 950.0
    assert result["event_fates"].get("POSITION_ACK_OR_COOLDOWN", 0) >= 1


def test_bad_event_clock_rejected_without_cash_change():
    data = bars(300)
    ev = event()
    ev["decision_at"] = ev["event_time"]
    fold = {"start_ms": T0 + 2 * MINUTE, "end_ms": T0 + 260 * MINUTE}
    result = simulate_fold(data, [ev], CAND, fold, STRESS)
    assert not result["trades"]
    assert result["ending_equity"] == 1000.0
    assert result["event_fates"].get("LOOKAHEAD_OR_CLOCK") == 1


def test_missing_future_path_fails_closed_without_data_end_trade():
    data = bars(100)
    with pytest.raises(ValueError, match="complete minute path"):
        episode(data, event(), CAND, BASE)
    fold = {"start_ms": T0 + 2 * MINUTE, "end_ms": T0 + 90 * MINUTE}
    result = simulate_fold(data, [event()], CAND, fold, BASE)
    assert result["event_fates"].get("INCOMPLETE_EPISODE") == 1
    assert not result["trades"]


def test_empty_fold_curve_preserves_continuous_starting_equity():
    data = bars(300)
    fold = {"start_ms": T0 + 2 * MINUTE, "end_ms": T0 + 260 * MINUTE}
    result = simulate_fold(data, [], CAND, fold, STRESS, initial_equity=1123.0)
    assert result["ending_equity"] == 1123.0
    assert result["max_mtm_drawdown_pct"] == 0.0
    assert result["minute_equity_curve"].shape == (258, 2)
    assert np.all(result["minute_equity_curve"][:, 1] == 1123.0)


def test_intraminute_stop_cash_cannot_fund_next_open_before_ack():
    data = bars(300)
    data[3, 3] = 49000.0  # stop inside minute 3; ACK after minute 4 open
    cand = dict(CAND, cooldown_hours=0)
    fold = {"start_ms": T0 + 2 * MINUTE, "end_ms": T0 + 260 * MINUTE}
    result = simulate_fold(data, [event(entry=2), event(entry=4)], cand, fold, BASE)
    assert len(result["trades"]) == 1
    assert result["trades"][0]["exit_ack_at"] > T0 + 4 * MINUTE
    assert result["event_fates"]["POSITION_ACK_OR_COOLDOWN"] == 1


def test_adverse_short_mark_reports_transient_exposure_breach():
    data = bars()
    data[10, 2:5] = [53000.0, 50000.0, 53000.0]
    data[11, 1:5] = [50000.0] * 4
    fold = {"start_ms": T0 + 2 * MINUTE, "end_ms": T0 + 260 * MINUTE}
    result = simulate_fold(data, [event(side=-1, stop_distance=5000)], CAND, fold, BASE)
    assert result["trades"][0]["entry_notional"] <= 950
    assert result["max_position_notional_to_marked_equity"] > 1
    assert result["marked_exposure_breach_minutes"] >= 1
