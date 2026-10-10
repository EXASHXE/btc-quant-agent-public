"""Synthetic clocks and independently hand-checked indicator examples."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.strategy_research.g2_btc_empirical_fast_r1 import signals
from scripts.strategy_research.g2_btc_empirical_fast_r1.signals import (
    HOUR_MS,
    MINUTE_MS,
    _atr,
    _ema,
    _er,
    aggregate,
    generate,
)

REGISTRY = {"candidates": [
    {"id": "SC_LONG_4H", "family": "STRUCTURAL_CONTINUATION",
     "side": "LONG", "horizon_hours": 4},
    {"id": "SC_LONG_12H", "family": "STRUCTURAL_CONTINUATION",
     "side": "LONG", "horizon_hours": 12},
]}


def _minute_rows(hours: int) -> np.ndarray:
    rows = np.empty((hours * 60, 6), dtype=np.float64)
    for h in range(hours):
        base = 100 + .015 * h
        for m in range(60):
            i = h * 60 + m
            opened = base + .005 * m / 60 - (.35 if h == 240 else 0)
            close = opened + .005 / 60
            if h == 240 and m == 59:
                close = base + .15
            rows[i] = (i * MINUTE_MS, opened, max(opened + .05, close + .05),
                       opened - .8, close, 1)
    return rows


def test_aggregation_uses_complete_utc_windows_only() -> None:
    rows = _minute_rows(2)
    result = aggregate(rows[5:75], 15)
    assert result["end_ms"].tolist() == [30 * MINUTE_MS, 45 * MINUTE_MS,
                                           60 * MINUTE_MS, 75 * MINUTE_MS]
    assert result["volume"].tolist() == [15, 15, 15, 15]
    assert result["open"][0] == rows[15, 1]
    assert result["close"][-1] == rows[74, 4]


@pytest.mark.parametrize("mutation", ["gap", "duplicate", "unaligned", "nan"])
def test_aggregation_rejects_bad_minutes(mutation: str) -> None:
    rows = _minute_rows(1)
    if mutation == "gap":
        rows = np.delete(rows, 12, axis=0)
    elif mutation == "duplicate":
        rows[12, 0] = rows[11, 0]
    elif mutation == "unaligned":
        rows[12, 0] += 1
    else:
        rows[12, 4] = np.nan
    with pytest.raises(ValueError):
        aggregate(rows, 15)


def test_ema_sma_seed_then_exact_recursion() -> None:
    values = np.array([1., 2., 3., 4., 5.])
    actual = _ema(values, 3)
    assert np.isnan(actual[0]) and np.isnan(actual[1])
    assert actual[2:].tolist() == [2., 3., 4.]


def test_atr_first_tr_is_range_then_uses_previous_close() -> None:
    bars = {"high": np.full(22, 12.), "low": np.full(22, 10.),
            "close": np.full(22, 11.)}
    bars["high"][20] = 15
    actual = _atr(bars)
    assert np.isnan(actual[18])
    assert actual[19] == 2
    assert actual[20] == pytest.approx((19 * 2 + 5) / 20)


def test_efficiency_ratio_has_zero_denominator_ineligible() -> None:
    flat = _er(np.full(15, 100.))
    assert np.all(np.isnan(flat))
    ascending = _er(np.arange(15, dtype=float))
    assert ascending[12] == 1


def test_structural_event_needs_60_completed_four_hour_bars() -> None:
    assert not generate(_minute_rows(240), REGISTRY)["SC_LONG_4H"]
    events = generate(_minute_rows(242), REGISTRY)
    assert events["SC_LONG_4H"]
    first = events["SC_LONG_4H"][0]
    assert first["event_time"] == 241 * HOUR_MS
    assert first["trend_bar_end"] == 240 * HOUR_MS
    assert first["decision_at"] == first["event_time"] + MINUTE_MS
    assert first["entry_at"] == first["event_time"] + 2 * MINUTE_MS
    assert first["side"] == 1
    assert first["stop"] < first["decision_close"]


def test_future_bar_cannot_revise_prior_event_and_horizon_shares_trigger() -> None:
    original = _minute_rows(242)
    changed = original.copy()
    changed[241 * 60 :, 1:5] *= 1.4
    prefix = generate(original[: 241 * 60], REGISTRY)
    all_events = generate(original, REGISTRY)
    changed_events = generate(changed, REGISTRY)
    for candidate in ("SC_LONG_4H", "SC_LONG_12H"):
        assert [e for e in all_events[candidate]
                if e["event_time"] <= 241 * HOUR_MS] == prefix[candidate]
        assert [e for e in changed_events[candidate]
                if e["event_time"] <= 241 * HOUR_MS] == prefix[candidate]
    left, right = all_events["SC_LONG_4H"][0], all_events["SC_LONG_12H"][0]
    assert left["event_id"] == right["event_id"]
    assert left["horizon_hours"] == 4 and right["horizon_hours"] == 12


def test_unfinished_four_hour_bar_cannot_change_trend_state() -> None:
    base = _minute_rows(242)
    later = base.copy()
    later[241 * 60 :, 1:5] *= .8
    a, b = generate(base, REGISTRY), generate(later, REGISTRY)
    assert a["SC_LONG_4H"][0] == b["SC_LONG_4H"][0]


def test_frozen_registry_candidate_keys_and_horizons_bind_without_market_data() -> None:
    root = Path(__file__).resolve().parents[1]
    registry = json.loads((root / "evidence/v0.6/b_line/g2_btc_empirical_fast_r1/"
                           "FROZEN_STRATEGY_REGISTRY.json").read_text())
    output = generate(_minute_rows(60 * 4), registry)
    assert len(output) == registry["candidate_count"] == 12
    assert set(output) == {candidate["id"] for candidate in registry["candidates"]}
    assert all(not events for events in output.values())


def _flat_minutes(hours: int) -> np.ndarray:
    rows = np.empty((hours * 60, 6), dtype=float)
    rows[:, 0] = np.arange(hours * 60) * MINUTE_MS
    rows[:, 1] = 100
    rows[:, 2] = 100.25
    rows[:, 3] = 99.75
    rows[:, 4] = 100
    rows[:, 5] = 1
    return rows


def _set_hour(rows: np.ndarray, h: int, opened: float, high: float,
              low: float, close: float) -> None:
    rows[h * 60 : (h + 1) * 60, 1:5] = (opened, high, low, close)


def test_failed_breakout_requires_strict_close_beyond_boundary(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(signals, "_atr", lambda bars: np.full(len(bars["close"]), 1.25))
    monkeypatch.setattr(signals, "_trend", lambda *args, **kwargs: True)
    rows = _flat_minutes(241)
    # Prior 16 quarter-hour lows are 99.75. Exactly boundary+0.1*ATR is
    # 99.875: the frozen rule says "greater than", not "greater or equal".
    rows[240 * 60 + 45 :, 1:5] = (99.75, 100.25, 99.0, 99.875)
    registry = {"candidates": [{"id": "FAIL", "family": "FAILED_BREAKOUT",
                                "side": "LONG", "horizon_hours": 8}]}
    assert generate(rows, registry)["FAIL"] == []
    rows[-1, 4] = 99.876
    result = generate(rows, registry)["FAIL"]
    assert len(result) == 1 and result[0]["side"] == 1


def test_invalid_vol_hour_still_cancels_pending_retest(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(signals, "_atr", lambda bars: np.full(len(bars["close"]), 1.25))
    monkeypatch.setattr(signals, "_trend", lambda *args, **kwargs: True)
    actual_eligible = signals._eligible_atr
    monkeypatch.setattr(signals, "_eligible_atr",
                        lambda close, atr, *, challenger: (
                            False if close == 99.5 else actual_eligible(
                                close, atr, challenger=challenger)))
    rows = _flat_minutes(243)
    _set_hour(rows, 240, 99.75, 100.8, 99.7, 100.75)
    _set_hour(rows, 241, 100.2, 100.3, 99.4, 99.5)
    _set_hour(rows, 242, 100.3, 100.6, 100.25, 100.5)
    registry = {"candidates": [{"id": "RETEST", "family": "CLOSED_RETEST",
                                "side": "LONG", "horizon_hours": 4}]}
    assert generate(rows, registry)["RETEST"] == []
    # Without the wrong-direction close, the third hour is a valid first
    # confirmation of the breakout at hour 240.
    _set_hour(rows, 241, 100.2, 100.3, 100.0, 100.0)
    result = generate(rows, registry)["RETEST"]
    assert len(result) == 1
    assert result[0]["event_id"] == f"RETEST:1:{241 * HOUR_MS}"
    assert result[0]["atr_hour"] == 1.25
