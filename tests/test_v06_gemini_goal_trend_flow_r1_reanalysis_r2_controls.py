"""Synthetic matched-control and invented funding-clock checks."""
from __future__ import annotations

import numpy as np
import pytest

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_controls import (
    funding_sensitivity,
    matched_control,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    HOUR,
    MINUTE,
    STRESS,
    episode,
)

T0 = 1_609_459_200_000  # invented flat synthetic UTC day
CAND = {"id": "synthetic", "horizon_hours": 4, "target_R": 2.0}


def bars(count: int = 400) -> np.ndarray:
    arr = np.zeros((count, 6), dtype=float)
    arr[:, 0] = T0 + np.arange(count) * MINUTE
    arr[:, 1:5] = 50_000.0
    return arr


def event(side: int = 1) -> dict:
    return {
        "event_id": "e", "side": side, "event_time": T0,
        "decision_at": T0 + MINUTE, "entry_at": T0 + 2 * MINUTE,
        "decision_close": 50_000.0, "atr_hour": 1000.0,
        "stop": 50_000.0 - side * 1000.0,
    }


@pytest.mark.parametrize("side", [1, -1])
@pytest.mark.parametrize("cost", [BASE, STRESS])
def test_flat_balanced_matches_real_trading_cost_and_pause(side, cost):
    data, ev = bars(), event(side)
    actual = episode(data, ev, CAND, cost, quantity=0.013)
    ctl = matched_control(data, ev, CAND, cost, actual)
    assert ctl["pause_net_bps"] == ctl["pause_net_usdt"] == 0
    assert ctl["balanced_net_bps"] == pytest.approx(-cost["nominal_roundtrip_bps"])
    assert ctl["paired_increment_bps"] == pytest.approx(0)
    assert ctl["total_quantity"] == actual["quantity"]
    assert ctl["long"]["quantity"] == ctl["short"]["quantity"] == 0.0065
    assert ctl["nontradable"]


@pytest.mark.parametrize("side", [1, -1])
def test_stop_geometry_reflects_about_same_entry_and_target_r(side):
    data, ev = bars(), event(side)
    actual = episode(data, ev, CAND, BASE, quantity=0.013)
    ctl = matched_control(data, ev, CAND, BASE, actual)
    for sign in (-1, 1):
        leg = ctl["long"] if sign == 1 else ctl["short"]
        assert leg["entry_at"] == actual["entry_at"]
        assert leg["decision_at"] == actual["decision_at"]
        assert leg["side"] == sign
        assert abs(leg["raw_entry"] - leg["stop"]) == pytest.approx(1000)
        assert sign * (leg["target"] - leg["effective_entry"]) == pytest.approx(
            2 * leg["initial_risk"] if "initial_risk" in leg else
            2 * sign * (leg["effective_entry"] - leg["stop"]), abs=0.11
        )


def test_balanced_notional_is_single_accepted_notional():
    data, ev = bars(), event()
    actual = episode(data, ev, CAND, BASE, quantity=0.013)
    ctl = matched_control(data, ev, CAND, BASE, actual)
    assert ctl["long"]["entry_notional"] + ctl["short"]["entry_notional"] == pytest.approx(
        actual["entry_notional"]
    )
    assert ctl["balanced_net_usdt"] == pytest.approx(
        ctl["long"]["net_usdt"] + ctl["short"]["net_usdt"]
    )
    assert ctl["pair_entry_cash_proxy_usdt"] < 1000
    assert ctl["pair_mtm_minutes"] == 241
    assert 0 < ctl["pair_max_mtm_drawdown_pct_on_1000_usdt"] < 1


def test_opposite_stop_terminates_independently_without_reselecting_entry():
    data, ev = bars(), event()
    data[10, 3] = 49_000.0
    actual = episode(data, ev, CAND, BASE, quantity=0.013)
    ctl = matched_control(data, ev, CAND, BASE, actual)
    assert actual["exit_reason"] == ctl["long"]["exit_reason"] == "STOP"
    assert ctl["short"]["exit_reason"] == "TIME_CAP"
    assert ctl["long"]["entry_at"] == ctl["short"]["entry_at"]


def test_control_rejects_changed_accepted_clock_or_notional():
    data, ev = bars(), event()
    actual = episode(data, ev, CAND, BASE, quantity=0.013)
    bad = dict(actual, entry_at=actual["entry_at"] + MINUTE)
    with pytest.raises(ValueError, match="entry clock"):
        matched_control(data, ev, CAND, BASE, bad)
    bad = dict(actual, entry_notional=actual["entry_notional"] + 10)
    with pytest.raises(ValueError, match="notional"):
        matched_control(data, ev, CAND, BASE, bad)


def test_future_after_both_episodes_cannot_change_control():
    data, ev = bars(), event()
    actual = episode(data, ev, CAND, BASE, quantity=0.013)
    first = matched_control(data, ev, CAND, BASE, actual)
    data[300:, 1:5] = 10_000.0
    second = matched_control(data, ev, CAND, BASE, actual)
    assert second["balanced_net_bps"] == first["balanced_net_bps"]


def trade(side: int = 1, *, entry: int = T0 + 2 * HOUR,
          exit_at: int = T0 + 18 * HOUR) -> dict:
    return {"entry_at": entry, "exit_at": exit_at, "side": side,
            "entry_notional": 1000.0, "net_bps": -22.0}


@pytest.mark.parametrize("rate,side,expected", [
    (4.0, 1, -8.0), (4.0, -1, 8.0), (-4.0, 1, 8.0), (-4.0, -1, -8.0),
])
def test_signed_eight_hour_funding_reverses(rate, side, expected):
    out = funding_sensitivity(trade(side), rate)
    assert out["settlement_count"] == 2  # UTC 08 and UTC 16
    assert out["funding_bps"] == expected


def test_unknown_hourly_adverse_is_never_a_credit():
    short = trade(-1)
    eight = funding_sensitivity(short, 4.0, adverse_only=True)
    hourly = funding_sensitivity(short, 4.0, cadence_hours=1, adverse_only=True)
    assert hourly["settlement_count"] > eight["settlement_count"]
    assert hourly["net_after_funding_bps"] < eight["net_after_funding_bps"] < short["net_bps"]


def test_settlement_boundary_plus_minus_15_seconds():
    one = trade(entry=T0 + 8 * HOUR, exit_at=T0 + 8 * HOUR + MINUTE)
    before = funding_sensitivity(one, 8.0, offset_seconds=-15)
    exact = funding_sensitivity(one, 8.0, offset_seconds=0)
    after = funding_sensitivity(one, 8.0, offset_seconds=15)
    assert [before["settlement_count"], exact["settlement_count"], after["settlement_count"]] == [0, 1, 1]


def test_exit_boundary_excludes_event_at_exact_exit():
    one = trade(entry=T0 + 7 * HOUR, exit_at=T0 + 8 * HOUR)
    assert funding_sensitivity(one, 4.0)["settlement_count"] == 0
    assert funding_sensitivity(one, 4.0, offset_seconds=-15)["settlement_count"] == 1


def test_bad_funding_clock_fails_closed():
    with pytest.raises(ValueError, match="frozen"):
        funding_sensitivity(trade(), 4.0, cadence_hours=4)
    with pytest.raises(ValueError, match="frozen"):
        funding_sensitivity(trade(), 4.0, offset_seconds=60)
