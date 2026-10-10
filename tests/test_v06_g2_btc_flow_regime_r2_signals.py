"""Synthetic-only independent indicator and six-family R2 signal witnesses."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.strategy_research.g2_btc_flow_regime_r2 import signals

ROOT = Path(__file__).resolve().parents[1]
ROSTER = json.loads((ROOT / "evidence/v0.6/b_line/g2_btc_flow_regime_r2/"
                     "FROZEN_R2_ROSTER.json").read_text())
MIN = signals.MINUTE_MS


def minute_rows(count: int = 60 * 241) -> np.ndarray:
    rows = np.empty((count, 7), dtype=float)
    rows[:, 0] = np.arange(count) * MIN
    rows[:, 1] = 100
    rows[:, 2] = 100.05
    rows[:, 3] = 99.95
    rows[:, 4] = 100
    rows[:, 5] = 1
    rows[:, 6] = .5
    return rows


def test_flow_aggregates_base_volume_not_ratios() -> None:
    rows = minute_rows(15)
    rows[:14, 5:7] = (1, 1)
    rows[14, 5:7] = (14, 0)
    result = signals.flow_aggregate(rows, 15)
    assert result["volume"].tolist() == [28]
    assert result["taker_buy_volume"].tolist() == [14]
    assert result["imbalance"].tolist() == [0]


def test_flow_zero_volume_stays_undefined() -> None:
    rows = minute_rows(15)
    rows[:, 5:7] = 0
    assert np.isnan(signals.flow_aggregate(rows, 15)["imbalance"][0])


@pytest.mark.parametrize("invalid", ["negative", "too_many", "nonfinite", "zero_mismatch"])
def test_invalid_taker_volume_rejected(invalid: str) -> None:
    rows = minute_rows(15)
    if invalid == "negative":
        rows[0, 6] = -.1
    elif invalid == "too_many":
        rows[0, 6] = 1.1
    elif invalid == "nonfinite":
        rows[0, 6] = np.nan
    else:
        rows[0, 5:7] = (0, .1)
    with pytest.raises(ValueError):
        signals.flow_aggregate(rows, 15)


def test_rsi_wilder_seed_and_first_recursion_independently() -> None:
    # 14 gains of one point -> RSI100; next loss of one yields avg gain13/14,
    # avg loss1/14 -> RSI=100-100/14.
    prices = np.r_[np.arange(15, dtype=float), 13.]
    actual = signals.rsi14(prices)
    assert np.all(np.isnan(actual[:14]))
    assert actual[14] == 100
    assert actual[15] == pytest.approx(100 - 100 / 14)


@pytest.mark.parametrize(("prices", "want"), [
    (np.zeros(15), 50),
    (np.arange(15, dtype=float), 100),
    (-np.arange(15, dtype=float), 0),
])
def test_rsi_zero_division_conventions(prices: np.ndarray, want: float) -> None:
    assert signals.rsi14(prices)[14] == want


def test_clv_and_rejection_tails_fail_closed_on_zero_range() -> None:
    assert np.isnan(signals._clv(100, 100, 100))
    assert np.isnan(signals._tail(1, 100, 100, 100, 100))
    assert signals._tail(-1, 100, 101, 99, 100) == .5


def synthetic_bars(monkeypatch: pytest.MonkeyPatch) -> tuple[dict, dict, dict, int]:
    """Independent completed-bar fixture isolates each exact formula branch."""
    counts = {15: 976, 60: 244, 240: 61}
    bars = {}
    for minutes, count in counts.items():
        arr = {
            "end_ms": np.arange(1, count + 1, dtype=float) * minutes * MIN,
            "open": np.full(count, 100.),
            "high": np.full(count, 100.1 if minutes == 15 else 100.4),
            "low": np.full(count, 99.9 if minutes == 15 else 99.6),
            "close": np.full(count, 100.),
            "volume": np.full(count, 1. if minutes == 15 else 4.),
            "imbalance": np.full(count, .5),
        }
        bars[minutes] = arr
    q, h, f = bars[15], bars[60], bars[240]
    monkeypatch.setattr(signals, "flow_aggregate", lambda _rows, minutes: bars[minutes])
    monkeypatch.setattr(signals, "_ema", lambda close, n: (
        99. + np.arange(len(close)) * .001 if n == 20
        else np.full(len(close), 98.)))
    monkeypatch.setattr(signals, "_atr", lambda obj: np.full(
        len(obj["close"]), 1. if obj is f else (1.5 if obj is h else .1)))
    monkeypatch.setattr(signals, "_er", lambda close: np.full(len(close), .4))
    monkeypatch.setattr(signals, "rsi14", lambda close: np.full(len(close), 20.))
    return q, h, f, 964  # First 15m completion after hour ending at 241h.


@pytest.mark.parametrize("family", list(signals.FAMILIES))
@pytest.mark.parametrize("side", [1, -1])
def test_each_family_has_distinct_positive_closed_bar_witness(
        monkeypatch: pytest.MonkeyPatch, family: str, side: int) -> None:
    q, h, f, k = synthetic_bars(monkeypatch)
    if family == "FLOW_CONFIRMED_TREND":
        q["open"][k], q["high"][k], q["low"][k], q["close"][k] = (
            100, 100.3, 99.95, 100.25)
        q["volume"][k] = 2
    elif family == "EXHAUSTION_FADE":
        h["close"][240] = 97
        q["imbalance"][k - 1] = -.5
        q["open"][k], q["high"][k], q["low"][k], q["close"][k] = (
            100, 100.4, 99.5, 100.3)
    elif family == "LOW_ER_RANGE_REENTRY":
        monkeypatch.setattr(signals, "_er", lambda close: np.full(len(close), .1))
        monkeypatch.setattr(signals, "rsi14", lambda close: np.full(len(close), 40.))
        q["open"][k], q["high"][k], q["low"][k], q["close"][k] = (
            99.95, 100.09, 99.7, 100.05)
    elif family == "VOL_COMPRESSION_RELEASE":
        h["open"][240], h["high"][240], h["low"][240], h["close"][240] = (
            100, 101.5, 99.4, 100.9)
        h["volume"][240] = 8
        q["open"][k], q["high"][k], q["low"][k], q["close"][k] = (
            100.2, 100.7, 100.1, 100.6)
    elif family == "FLOW_ABSORPTION_REVERSAL":
        monkeypatch.setattr(signals, "_er", lambda close: np.full(len(close), .2))
        q["imbalance"][k - 2:k] = -.5
        for v in (k - 2, k - 1):
            q["open"][v], q["high"][v], q["low"][v], q["close"][v] = (
                99.95, 99.99, 99.8, 99.95)
        q["open"][k], q["high"][k], q["low"][k], q["close"][k] = (
            100, 100.08, 99.8, 100.05)
    else:
        h["close"][238:241] = (99, 99.4, 99.8)
        q["open"][k], q["high"][k], q["low"][k], q["close"][k] = (
            99.95, 100.1, 99.9, 100.05)
    if side == -1:
        for bars in (q, h, f):
            original_high, original_low = bars["high"].copy(), bars["low"].copy()
            bars["open"][:] = 200 - bars["open"]
            bars["high"][:] = 200 - original_low
            bars["low"][:] = 200 - original_high
            bars["close"][:] = 200 - bars["close"]
            bars["imbalance"] *= -1
        monkeypatch.setattr(signals, "_ema", lambda close, n: (
            101. - np.arange(len(close)) * .001 if n == 20
            else np.full(len(close), 102.)))
        monkeypatch.setattr(signals, "rsi14", lambda close: np.full(len(close), 80.))
    events = signals.generate(np.zeros((1, 7)), ROSTER)
    candidate = next(c for c in ROSTER["candidates"] if c["family"] == family)
    target_end = q["end_ms"][k]
    witness = [e for e in events[candidate["id"]] if e["event_time"] == target_end]
    assert witness, family
    assert witness[0]["side"] == side
    assert witness[0]["decision_at"] == target_end + MIN
    assert witness[0]["entry_at"] == target_end + 2 * MIN
    assert witness[0]["trend_bar_end"] <= target_end
    assert side * (witness[0]["decision_close"] - witness[0]["stop"]) > 0


def test_completed_bar_minimum_and_future_data_independence() -> None:
    rows = minute_rows(60 * 239)
    assert all(not e for e in signals.generate(rows, ROSTER).values())
    base = minute_rows(60 * 241)
    later = np.vstack((base, minute_rows(60)[0:60]))
    later[60 * 241:, 0] = np.arange(60 * 241, 60 * 242) * MIN
    later[60 * 241:, 1:5] = (120, 121, 119, 120)
    before = signals.generate(base, ROSTER)
    after = signals.generate(later, ROSTER)
    cutoff = len(base) * MIN
    assert {key: [e for e in value if e["event_time"] <= cutoff]
            for key, value in after.items()} == before


def test_incomplete_minute_grid_and_forged_roster_rejected() -> None:
    rows = minute_rows(240)
    with pytest.raises(ValueError):
        signals.generate(np.delete(rows, 60, axis=0), ROSTER)
    with pytest.raises(ValueError):
        signals.generate(rows, {"candidates": ROSTER["candidates"][:-1]})


def test_optional_diagnostics_conserve_all_closed_quarter_slots() -> None:
    rows = minute_rows(60 * 241)
    rows[:, 2], rows[:, 3] = 100.1, 99.9  # 20bp hourly ATR meets global gate.
    diagnostics = {"stale": True}
    events = signals.generate(rows, ROSTER, diagnostics)
    assert "stale" not in diagnostics
    assert events == signals.generate(rows, ROSTER)
    assert diagnostics["completed_15m_quarters"] == (
        diagnostics["before_60_completed_4h"]
        + diagnostics["before_20_completed_1h"]
        + diagnostics["global_atr_vol_bad"]
        + diagnostics["eligible_quarter_side_observations"] // 2
    )
    assert diagnostics["eligible_quarter_side_observations"] == 10
    assert diagnostics["first_after_hour_eligible_quarter_side_observations"] == 2
    for row in ROSTER["candidates"]:
        counts = diagnostics["candidates"][row["id"]]
        assert counts["fully_evaluated_eligible_quarter_side_observations"] == 10
        assert counts["emitted"] == len(events[row["id"]])
        assert counts["feature_conditions_not_met"] + counts["emitted"] == 10


def test_optional_diagnostics_count_real_emissions_without_reclassification(
        monkeypatch: pytest.MonkeyPatch) -> None:
    q, _h, _f, k = synthetic_bars(monkeypatch)
    q["open"][k], q["high"][k], q["low"][k], q["close"][k] = (
        100, 100.3, 99.95, 100.25)
    q["volume"][k] = 2
    diagnostics = {}
    events = signals.generate(np.zeros((1, 7)), ROSTER, diagnostics)
    key = next(c["id"] for c in ROSTER["candidates"]
               if c["family"] == "FLOW_CONFIRMED_TREND")
    counts = diagnostics["candidates"][key]
    assert counts["emitted"] == len(events[key]) >= 1
    assert counts["feature_conditions_not_met"] == (
        counts["fully_evaluated_eligible_quarter_side_observations"] - len(events[key]))
