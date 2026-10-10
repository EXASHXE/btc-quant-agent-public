"""Independent hand-sized causal and cash examples; no market files."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.strategy_research.g2_btc_empirical_fast_r1.replay import (
    BASE,
    MINUTE,
    STRESS,
    episode,
    simulate,
)


def bars(count: int = 520, price: float = 1000.0) -> np.ndarray:
    a = np.empty((count, 6), dtype=np.float64)
    a[:, 0] = np.arange(count) * MINUTE
    a[:, 1:5] = price
    a[:, 5] = 1.0
    return a


def test_tail_signal_has_explicit_wait_fate() -> None:
    d = bars()
    ev = event(510)
    result = simulate(d, [ev], CHALLENGE, {"id": "tail", "start_ms": 0,
        "end_ms": 500 * MINUTE}, BASE)
    assert result['waits']['PURGED_FOLD_EDGE'] == 1
    assert len(result['event_log']) == 1
    assert result['event_log'][0]['event_id'] == ev['event_id']


def event(entry_minute: int = 3, side: int = 1, stop: float | None = None) -> dict:
    return {
        "event_time": (entry_minute - 2) * MINUTE,
        "decision_at": (entry_minute - 1) * MINUTE,
        "entry_at": entry_minute * MINUTE,
        "decision_close": 1000.0,
        "atr_hour": 100.0,
        "stop": 980.0 if side > 0 else 1020.0 if stop is None else stop,
        "side": side,
        "event_id": f"s{entry_minute}",
        "trend_bar_end": 0,
        "regime_vol_bps": 80.0,
    }


CHALLENGE = {
    "id": "C1",
    "family": "TREND_PULLBACK",
    "horizon_hours": 4,
    "cooldown_hours": 1,
    "target_r": 2.0,
}
ORIGINAL = {"id": "O1", "family": "STRUCTURAL_CONTINUATION", "horizon_hours": 4, "target_r": 2.0}
FOLD = {"id": "invented", "start_ms": 3 * MINUTE, "end_ms": 510 * MINUTE}


def test_next_open_and_no_same_bar_signal_fill() -> None:
    d = bars()
    e = event()
    t = episode(d, e, CHALLENGE, BASE)
    assert t["entry_at"] == 3 * MINUTE
    e["entry_at"] = e["decision_at"]
    with pytest.raises(ValueError, match="delay"):
        episode(d, e, CHALLENGE, BASE)


def test_completed_bar_availability_rejects_backdating() -> None:
    d = bars()
    e = event()
    e["decision_at"] = e["event_time"]
    with pytest.raises(ValueError, match="availability"):
        episode(d, e, CHALLENGE, BASE)


def test_stop_wins_collision_even_on_entry_bar() -> None:
    d = bars()
    d[3, 2] = 1100
    d[3, 3] = 900
    t = episode(d, event(), CHALLENGE, BASE)
    assert t["exit_reason"] == "STOP"
    assert t["raw_exit"] == 980
    assert t["exit_at"] == 4 * MINUTE - 1
    r = simulate(d, [event()], CHALLENGE, FOLD, BASE)
    assert r["trades"][0]["exit_reason"] == "STOP"


def test_adverse_gap_worse_open_and_favorable_gap_capped() -> None:
    d = bars()
    d[4, 1:4] = [970, 970, 970]
    down = episode(d, event(), CHALLENGE, BASE)
    assert down["raw_exit"] == 970 and down["exit_reason"] == "STOP_GAP"
    d = bars()
    d[4, 1:4] = [1100, 1100, 1100]
    up = episode(d, event(), CHALLENGE, BASE)
    assert up["raw_exit"] == up["target"] < 1100
    assert up["exit_reason"] == "TARGET_GAP_CAPPED"


def test_short_signed_funding_free_cost_direction_and_stop_priority() -> None:
    d = bars()
    d[4, 1:4] = [1030, 1030, 1030]
    short = episode(d, event(side=-1), CHALLENGE, BASE)
    assert short["side"] == -1
    assert short["exit_reason"] == "STOP_GAP"
    assert short["net_usdt"] < short["gross_usdt"]
    assert short["cost_proxy_excludes_funding"]


def test_cost_legs_once_and_stress_more_adverse() -> None:
    d = bars()
    d[4, 1:4] = [1100, 1100, 1100]
    base = episode(d, event(), CHALLENGE, BASE, quantity=2)
    stress = episode(d, event(), CHALLENGE, STRESS, quantity=2)
    assert base["fee_usdt"] == pytest.approx(
        2 * (base["effective_entry"] + base["effective_exit"]) * 6 / 10_000
    )
    assert base["net_usdt"] == pytest.approx(
        base["gross_usdt"] - base["fee_usdt"] - base["execution_drag_usdt"]
    )
    assert stress["net_usdt"] < base["net_usdt"]


def test_fixed_horizon_time_exit_at_open_and_hold_clock() -> None:
    d = bars()
    t = episode(d, event(), CHALLENGE, BASE)
    assert t["exit_reason"] == "TIME_CAP"
    assert t["exit_at"] == (3 + 240) * MINUTE
    assert t["duration_minutes"] == 240


def test_quarter_atr_gap_veto_has_no_fill() -> None:
    d = bars()
    late = event()
    late["decision_close"] = 970
    r = simulate(d, [late], CHALLENGE, FOLD, BASE)
    assert not r["trades"]
    assert any("gap veto" in reason for reason in r["waits"])


def test_scoring_tail_purges_full_planned_horizon() -> None:
    d = bars()
    tail = event(270)
    r = simulate(d, [tail], CHALLENGE, {"start_ms": 3 * MINUTE, "end_ms": 500 * MINUTE}, BASE)
    assert not r["trades"]
    assert r["waits"]["PURGED_FOLD_EDGE"] == 1


def test_one_position_ack_and_cooldown_reject_overlap() -> None:
    d = bars()
    first = event()
    second = event(5)
    third = event(300)
    r = simulate(d, [first, second, third], CHALLENGE, FOLD, BASE)
    assert r["waits"]["POSITION_ACK_OR_COOLDOWN"] >= 1
    assert len(r["trades"]) == 1  # 300m is within 1h of 243m exit ACK.


def test_original_stress_geometry_rejects_12h_unknown_hourly() -> None:
    d = bars(900)
    candidate = {**ORIGINAL, "horizon_hours": 12}
    with pytest.raises(ValueError, match="geometry"):
        episode(d, event(), candidate, BASE)


def test_original_structural_requires_fresh_completed_4h_bar() -> None:
    d = bars(900)
    d[4, 1:4] = [1100, 1100, 1100]
    first = event()
    first["trend_bar_end"] = 1
    second = event(400)
    second["trend_bar_end"] = 1
    fold = {"start_ms": 3 * MINUTE, "end_ms": 800 * MINUTE}
    r = simulate(d, [first, second], ORIGINAL, fold, BASE)
    assert r["waits"]["NO_NEW_COMPLETED_4H_BAR"] == 1
    assert len(r["trades"]) == 1


def test_sizing_lot_cash_and_min_notional() -> None:
    d = bars()
    d[4, 1:4] = [1100, 1100, 1100]
    original = simulate(d, [event()], ORIGINAL, FOLD, BASE)
    challenge = simulate(d, [event()], CHALLENGE, FOLD, BASE)
    q1, q2 = original["trades"][0]["quantity"], challenge["trades"][0]["quantity"]
    assert q1 < q2 <= 0.95
    assert q1 / 0.001 == pytest.approx(round(q1 / 0.001))
    assert q2 * 1000 <= 1000
    tiny = simulate(d, [event()], CHALLENGE, FOLD, BASE, initial_equity=5)
    assert not tiny["trades"]


def test_dense_curve_daily_and_repeatability() -> None:
    d = bars()
    d[4, 1:4] = [1100, 1100, 1100]
    a = simulate(d, [event()], CHALLENGE, FOLD, BASE)
    b = simulate(d, [copy.deepcopy(event())], CHALLENGE, FOLD, BASE)
    np.testing.assert_array_equal(a["curve"], b["curve"])
    assert a["trades"] == b["trades"]
    assert len(a["curve"]) == 507
    assert a["ending_equity"] == pytest.approx(1000 + a["trades"][0]["net_usdt"])
    assert a["daily_equity"][-1]["equity"] == pytest.approx(a["ending_equity"])


def test_profit_is_not_available_before_exit_ack() -> None:
    d = bars()
    d[4, 1:4] = [1100, 1100, 1100]
    first, quick = event(), event(4)
    quick["event_id"] = "quick"
    r = simulate(d, [first, quick], CHALLENGE, FOLD, BASE)
    assert len(r["trades"]) == 1
    assert r["waits"]["POSITION_ACK_OR_COOLDOWN"] == 1
    assert r["trades"][0]["exit_ack_at"] > r["trades"][0]["exit_at"]


def test_drawdown_guard_uses_delayed_mark_then_next_open() -> None:
    d = bars()
    d[3, 4] = 700
    d[3, 3] = 700
    d[4, 1:5] = [700, 700, 700, 700]
    r = simulate(d, [event()], CHALLENGE, FOLD, BASE)
    assert r["trades"][0]["exit_reason"] in {"STOP", "STOP_GAP"}
    assert r["disabled"] or r["ending_equity"] < 1000


def test_gap_loss_disables_later_signal_after_available_close() -> None:
    d = bars()
    d[4, 1:4] = [800, 800, 800]
    first, later = event(), event(8)
    later["event_id"] = "later"
    r = simulate(d, [first, later], CHALLENGE, FOLD, BASE)
    assert len(r["trades"]) == 1
    assert r["trades"][0]["exit_reason"] == "STOP_GAP"
    assert r["disabled"]
    assert r["waits"]["DISABLED"] == 1


def test_unfunded_control_reverses_side_at_same_timestamp() -> None:
    d = bars()
    d[4, 1:4] = [1100, 1100, 1100]
    main = episode(d, event(), CHALLENGE, BASE)
    opposite = episode(d, event(), CHALLENGE, BASE, side_override=-1, control="TIME_MATCHED_SHORT")
    assert main["entry_at"] == opposite["entry_at"]
    assert opposite["side"] == -1
    assert opposite["control"] == "TIME_MATCHED_SHORT"


def test_no_future_close_used_in_sizing() -> None:
    d = bars()
    d[3, 4] = 2000  # Unknown until bar 3 has closed plus availability.
    a = simulate(d, [event()], CHALLENGE, FOLD, BASE)
    d[3, 4] = 1000
    b = simulate(d, [event()], CHALLENGE, FOLD, BASE)
    assert a["trades"][0]["quantity"] == b["trades"][0]["quantity"]


def test_missing_or_duplicate_utc_minute_fails_closed() -> None:
    d = bars()
    d[17, 0] = d[16, 0]
    with pytest.raises(ValueError, match="missing UTC minute"):
        simulate(d, [event()], CHALLENGE, FOLD, BASE)
    d[17, 0] = 18 * MINUTE
    with pytest.raises(ValueError, match="missing UTC minute"):
        episode(d, event(), CHALLENGE, BASE)


def test_frozen_registry_cost_alias_and_target_r_key() -> None:
    d = bars()
    d[4, 1:4] = [1100, 1100, 1100]
    canonical = {"fee_bps": 6, "spread_bps": 2, "slippage_bps": 3}
    candidate = {**CHALLENGE, "target_R": 3, "target_r": 2}
    t = episode(d, event(), candidate, canonical)
    assert t["target"] > episode(d, event(), CHALLENGE, BASE)["target"]
    assert t["fee_usdt"] > 0
    assert t["economic_grade"] == "EXPLORATORY_COST_PROXY_ONLY"


def test_expiry_open_adverse_stop_gap_precedes_time_cap() -> None:
    d = bars()
    expiry = 3 + 240
    d[expiry, 1:4] = [970, 970, 970]
    t = episode(d, event(), CHALLENGE, BASE)
    assert t["exit_at"] == expiry * MINUTE
    assert t["exit_reason"] == "STOP_GAP"
    assert t["raw_exit"] == 970


def test_wait_ledger_one_record_per_event_and_no_prices() -> None:
    d = bars()
    d[4, 1:4] = [1100, 1100, 1100]
    events = [event(), event(5), event(500)]
    r = simulate(d, events, CHALLENGE, FOLD, BASE)
    assert len(r["event_log"]) == len(events)
    assert [e["result"] for e in r["event_log"]] == [
        "FILLED",
        "POSITION_ACK_OR_COOLDOWN",
        "PURGED_FOLD_EDGE",
    ]
    assert all(set(e) == {"event_id", "decision_at", "entry_at", "result"} for e in r["event_log"])


def test_initial_highwater_carries_across_fold_for_delayed_kill() -> None:
    d = bars()
    fresh = simulate(d, [], CHALLENGE, FOLD, BASE, initial_equity=900)
    carry = simulate(d, [], CHALLENGE, FOLD, BASE, initial_equity=900, initial_highwater=1000)
    assert not fresh["disabled"]
    assert carry["disabled"]
    assert carry["waits"]["DRAWDOWN_DISABLE"] == 1


def test_original_shadow_quantity_matches_frozen_reserved_budget() -> None:
    d = bars()
    d[4, 1:4] = [1100, 1100, 1100]
    candidate = {**ORIGINAL, "allocation_fraction": 1 / 3}
    r = simulate(d, [event()], candidate, FOLD, BASE)
    q = r["trades"][0]["quantity"]
    x = 1025.6  # tick ceil((raw1000 + .25 * ATR100) * (1 + 5bp))
    per_unit = x + x * 6 / 10_000 + 1.1 * x * 11 / 10_000 + 1.1 * 1000 * 8 * 4 / 10_000
    expected = int(((0.95 * 1000 / 3) / per_unit) / 0.001) * 0.001
    assert q == pytest.approx(expected)
