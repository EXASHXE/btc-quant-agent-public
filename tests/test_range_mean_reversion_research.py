from __future__ import annotations

import importlib
import json
import math
from pathlib import Path

import pytest

from btc_quant_agent.backtest import resample
from btc_quant_agent.config import AppConfig
from btc_quant_agent.domain import Candle, Regime
from btc_quant_agent.range_mean_reversion_research import (
    SEED,
    DevelopmentMinuteSeries,
    assert_development_only,
    boll20,
    build_episodes,
    build_features_15m,
    cluster_bootstrap,
    fade_side,
    label_event,
    match_non_range_controls,
)
from btc_quant_agent.research import DEV_END_MS, DEV_START_MS
from btc_quant_agent.strategies import find_candidate


def _bar(open_ms: int, *, interval: str = "1m", price: float = 100.0,
         high: float | None = None, low: float | None = None) -> Candle:
    width = 60_000 if interval == "1m" else 900_000
    return Candle(
        "BTCUSDT", interval, open_ms, open_ms + width - 1, price,
        high if high is not None else price + 0.1,
        low if low is not None else price - 0.1,
        price, 1.0,
    )


def _feature(index: int, side: str, state: str = "RANGE") -> dict[str, object]:
    open_ms = index * 900_000
    return {
        "timestamp_ms": open_ms + 900_000,
        "decision_open_ms": open_ms,
        "decision_close_ms": open_ms + 899_999,
        "feature_status": "EXTREME" if side != "NO_BIAS" else "NO_BIAS",
        "side": side,
        "market_state": state,
        "year": 2021,
        "atr_decile": 5,
        "abs_z_decile": 8,
    }


def _event(decision_close_ms: int, side: str = "LONG_FADE", center: float = 101.0) -> dict[str, object]:
    return {
        "event_id": "e", "timestamp_ms": decision_close_ms + 1,
        "decision_close_ms": decision_close_ms, "year": 2021, "split": "EARLY",
        "week_cluster": "2021-W01", "day_cluster": "2021-01-01", "side": side,
        "market_state": "RANGE", "atr": 1.0, "center": center, "sigma": 0.5,
    }


def test_exact_boll20_population_sigma() -> None:
    values = list(range(1, 21))
    center, sigma, z = boll20(values) or (0.0, 0.0, 0.0)
    assert center == 10.5
    assert sigma == pytest.approx(math.sqrt(sum((x - 10.5) ** 2 for x in values) / 20))
    assert z == pytest.approx((20 - center) / sigma)


def test_no_signal_before_20_closed_bars_and_sigma_zero() -> None:
    assert boll20([100.0] * 19) is None
    assert boll20([100.0] * 20) is None


def test_resample_drops_partial_15m_bar() -> None:
    rows = [_bar(i * 60_000) for i in range(16)]
    assert len(resample(rows, "15m")) == 1


def test_latest_fully_closed_1h_state_asof() -> None:
    bars = [_bar(i * 900_000, interval="15m", price=float(i)) for i in range(20)]
    states = [
        {"feature_1h_close_ms": 3_599_999, "market_state": "RANGE", "atr": 1.0, "atr_percentile": .5, "atr_decile": 5},
        {"feature_1h_close_ms": 99_999_999, "market_state": "TREND_UP", "atr": 2.0, "atr_percentile": .6, "atr_decile": 6},
    ]
    assert build_features_15m(bars, states)[-1]["market_state"] == "RANGE"
    assert build_features_15m(bars, states)[-1]["feature_1h_close_ms"] <= bars[-1].close_time_ms


def test_long_short_symmetry_and_zero_z() -> None:
    assert fade_side(-2.0) == "LONG_FADE"
    assert fade_side(2.0) == "SHORT_FADE"
    assert fade_side(0.0) == "NO_BIAS"


def test_episode_start_and_break_rules() -> None:
    rows = [_feature(0, "LONG_FADE"), _feature(1, "LONG_FADE"), _feature(2, "NO_BIAS"), _feature(3, "LONG_FADE"), _feature(4, "SHORT_FADE")]
    onsets, members = build_episodes(rows, regime="RANGE")
    assert len(onsets) == 3
    assert [row["episode_index"] for row in members] == [0, 1, 0, 0]


def test_episode_breaks_on_gap_unavailable_and_range_exit() -> None:
    rows = [_feature(0, "LONG_FADE"), _feature(2, "LONG_FADE"), _feature(3, "LONG_FADE", "TREND_UP"), _feature(4, "LONG_FADE")]
    rows[1]["feature_status"] = "UNAVAILABLE"
    onsets, _ = build_episodes(rows, regime="RANGE")
    assert len(onsets) == 2


def test_label_starts_strictly_after_decision_and_center_is_frozen() -> None:
    bars = [_bar(DEV_START_MS + i * 60_000, price=100.0 + i / 10) for i in range(10)]
    series = DevelopmentMinuteSeries(bars)
    result = label_event(_event(DEV_START_MS + 59_999, center=100.4), series, 2)
    assert result["entry_reference_ms"] == DEV_START_MS + 60_000
    assert result["frozen_center"] == 100.4


def test_center_before_adverse_and_adverse_before_center() -> None:
    bars = [
        _bar(DEV_START_MS, price=100),
        _bar(DEV_START_MS + 60_000, price=100, high=101.1, low=99.9),
        _bar(DEV_START_MS + 120_000, price=100),
    ]
    assert label_event(_event(DEV_START_MS + 59_999), DevelopmentMinuteSeries(bars), 2)["ordering"] == "CENTER_FIRST"
    bars[1] = _bar(DEV_START_MS + 60_000, price=100, high=100.1, low=98.9)
    assert label_event(_event(DEV_START_MS + 59_999), DevelopmentMinuteSeries(bars), 2)["ordering"] == "ADVERSE_FIRST"


def test_same_bar_ambiguity_is_conservative_failure() -> None:
    bars = [_bar(DEV_START_MS), _bar(DEV_START_MS + 60_000, price=100, high=101.1, low=98.9)]
    result = label_event(_event(DEV_START_MS + 59_999), DevelopmentMinuteSeries(bars), 1)
    assert result["ordering"] == "SAME_1M_BAR_AMBIGUOUS"
    assert result["center_first"] is False


def test_future_window_cannot_cross_dev_end() -> None:
    bars = [_bar(DEV_START_MS), _bar(DEV_END_MS - 60_000)]
    series = DevelopmentMinuteSeries(bars)
    assert series.window(DEV_END_MS - 60_000, 1)[1] is True


def test_artifact_firewall_rejects_holdout_timestamp() -> None:
    assert_development_only({"timestamp_ms": DEV_END_MS - 1})
    with pytest.raises(ValueError):
        assert_development_only({"rows": [{"timestamp_ms": DEV_END_MS}]})


def test_matching_rejects_outcomes_and_k_over_five() -> None:
    candidate = {**_feature(0, "LONG_FADE"), "event_id": "c", "abs_z": 2.1}
    control = {**_feature(100, "LONG_FADE", "TREND_UP"), "event_id": "n", "abs_z": 2.2}
    with pytest.raises(ValueError):
        match_non_range_controls([{**candidate, "signed_return_atr": 1}], [control])
    with pytest.raises(ValueError):
        match_non_range_controls([candidate], [control], k=6)


def test_matching_enforces_24h_and_exact_strata() -> None:
    candidate = {**_feature(0, "LONG_FADE"), "event_id": "c"}
    near = {**_feature(10, "LONG_FADE", "TREND_UP"), "event_id": "near"}
    far = {**_feature(100, "LONG_FADE", "TREND_UP"), "event_id": "far"}
    rows = match_non_range_controls([candidate], [near, far])
    assert [row["control_id"] for row in rows] == ["far"]
    assert rows[0]["distance_hours"] >= 24


def test_seed_40_is_used_deterministically() -> None:
    rows = [{"week": str(i % 3), "value": float(i)} for i in range(12)]
    left = cluster_bootstrap(rows, "value", "week", simulations=20)
    right = cluster_bootstrap(rows, "value", "week", simulations=20)
    assert left == right
    assert left["seed"] == SEED == 40


def test_protocol_freezes_seed_and_ambiguity_rule() -> None:
    protocol = json.loads(Path("configs/research/v0.3.10_range_mean_reversion_protocol.json").read_text())
    assert protocol["randomness"] == {"seed": 40, "bootstrap_simulations": 2000, "quantiles": [0.05, 0.5, 0.95]}
    assert "conservatively" in protocol["entry_and_labels"]["ambiguous_primary_rule"]


def test_execution_remains_disabled() -> None:
    config = AppConfig()
    assert config.runtime.validation_status == "EXPERIMENTAL"
    assert config.execution.mode == "disabled"
    assert config.execution.auto_execute is False
    assert config.execution.allow_live is False


def test_import_does_not_change_tp_br_output() -> None:
    config = AppConfig().strategy
    before = find_candidate([], pytest.MonkeyPatch(), Regime.RANGE, config)  # type: ignore[arg-type]
    import btc_quant_agent.range_mean_reversion_research as research_module
    importlib.reload(research_module)
    after = find_candidate([], pytest.MonkeyPatch(), Regime.RANGE, config)  # type: ignore[arg-type]
    assert before == after is None
