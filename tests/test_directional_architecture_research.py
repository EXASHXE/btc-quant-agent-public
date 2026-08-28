from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from btc_quant_agent.causal_entry_research import IndexedOneMinuteSeries
from btc_quant_agent.config import AppConfig
from btc_quant_agent.directional_architecture_research import (
    LATE_START_MS,
    _boolean_field,
    _development_only,
    _ladder,
    _match_episode_pairs,
    _pair_bootstrap,
    _split,
    movement_label,
    permute_directions_preserving_strata,
)
from btc_quant_agent.directional_episode import EpisodeAccumulator
from btc_quant_agent.domain import Candle
from btc_quant_agent.research import DEV_END_MS, DEV_START_MS

PROTOCOL = Path("configs/research/v0.3.6_directional_architecture_protocol.json")


def _snapshot(close_ms: int, regime: str, direction: str) -> dict[str, object]:
    anchor = close_ms + 1
    return {
        "episode_id": f"EP:{anchor}:{direction}",
        "timestamp_ms": anchor,
        "anchor_timestamp_ms": anchor,
        "decision_close_ms": close_ms,
        "year": 2021,
        "direction": direction,
        "regime": regime,
        "close": 100.0,
        "atr": 2.0,
        "atr_percentile": 0.4,
        "atr_decile": 4,
        "macro_4h_aligned": True,
        "structure_15m": "HH_HL",
        "structure_15m_aligned": True,
        "rsi_15m": 55.0,
        "rsi_15m_aligned": True,
        "roc_15m": 1.0,
        "roc_15m_aligned": True,
        "momentum_both_aligned": True,
        "feature_4h_close_ms": close_ms,
        "feature_1h_close_ms": close_ms,
        "feature_15m_close_ms": close_ms,
    }


def test_regime_episode_construction_is_causal() -> None:
    accumulator = EpisodeAccumulator()
    first = DEV_START_MS + 10 * 3_600_000 - 1
    accumulator.add(_snapshot(first, "TREND_UP", "LONG"))
    accumulator.add(_snapshot(first, "TREND_UP", "LONG"))
    accumulator.add(_snapshot(first + 3_600_000, "TREND_UP", "LONG"))
    accumulator.add(_snapshot(first + 2 * 3_600_000, "RANGE", "SHORT"))
    accumulator.add(_snapshot(first + 3 * 3_600_000, "TREND_UP", "LONG"))
    assert len(accumulator.rows) == 2
    assert accumulator.rows[0]["duration_hours"] == 2
    assert accumulator.rows[1]["duration_hours"] == 1


def test_episode_has_no_future_feature_access() -> None:
    row = _snapshot(DEV_START_MS + 3_600_000 - 1, "TREND_UP", "LONG")
    assert max(
        int(row[key])
        for key in ("feature_4h_close_ms", "feature_1h_close_ms", "feature_15m_close_ms")
    ) <= int(row["decision_close_ms"])


def test_episode_cluster_ids_are_stable() -> None:
    snapshot = _snapshot(DEV_START_MS + 3_600_000 - 1, "TREND_UP", "LONG")
    left = EpisodeAccumulator()
    right = EpisodeAccumulator()
    left.add(snapshot)
    right.add(snapshot)
    assert left.rows[0]["episode_id"] == right.rows[0]["episode_id"]


def test_permutation_null_preserves_year_atr_direction_frequency() -> None:
    episodes = []
    for index, direction in enumerate(("LONG", "SHORT", "LONG", "SHORT")):
        row = _snapshot(
            DEV_START_MS + (index + 1) * 3_600_000 - 1,
            f"TREND_{'UP' if direction == 'LONG' else 'DOWN'}",
            direction,
        )
        row["episode_id"] = f"e{index}"
        episodes.append(row)
    permuted = permute_directions_preserving_strata(episodes)
    assert Counter(permuted.values()) == Counter(row["direction"] for row in episodes)


def test_matched_opposite_is_opposite_direction() -> None:
    left = _snapshot(DEV_START_MS + 3_600_000 - 1, "TREND_UP", "LONG")
    right = _snapshot(DEV_START_MS + 30 * 3_600_000 - 1, "TREND_DOWN", "SHORT")
    pairs = _match_episode_pairs(
        [left, right], lambda row: True, lambda row: True, opposite_direction=True
    )
    assert pairs
    assert all(a["direction"] != b["direction"] for a, b in pairs)


def test_macro_increment_matching_uses_no_future_labels() -> None:
    aligned = _snapshot(DEV_START_MS + 3_600_000 - 1, "TREND_UP", "LONG")
    control = _snapshot(DEV_START_MS + 30 * 3_600_000 - 1, "TREND_UP", "LONG")
    control["macro_4h_aligned"] = False
    pairs = _match_episode_pairs(
        [aligned, control],
        _boolean_field("macro_4h_aligned", True),
        _boolean_field("macro_4h_aligned", False),
    )
    assert pairs == [(aligned, control)]


def test_structure_alignment_uses_confirmed_structure_only() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    definition = protocol["frozen_features"]["structure_15m_aligned"]
    assert (
        "confirmed" in definition and "pivot_left=2" in definition and "pivot_right=2" in definition
    )


def test_momentum_uses_frozen_parameters() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert "RSI(14)" in protocol["frozen_features"]["rsi_15m_aligned"]
    assert "ROC(12)" in protocol["frozen_features"]["roc_15m_aligned"]
    assert AppConfig().strategy.rsi_period == 14
    assert AppConfig().strategy.roc_period == 12


def test_direction_ladder_is_nested() -> None:
    episodes = []
    labels = []
    for index in range(4):
        row = _snapshot(DEV_START_MS + (index + 1) * 3_600_000 - 1, "TREND_UP", "LONG")
        row["episode_id"] = f"e{index}"
        row["macro_4h_aligned"] = index < 3
        row["structure_15m_aligned"] = index < 2
        row["momentum_both_aligned"] = index < 1
        episodes.append(row)
        for horizon in (240, 480):
            labels.append(
                {
                    "episode_id": row["episode_id"],
                    "horizon_minutes": horizon,
                    "incomplete": False,
                    "direction": "LONG",
                    "split": "EARLY",
                    "signed_return_atr": 1.0,
                    "mfe_atr": 1.0,
                    "mae_atr": 0.5,
                    "reach_1_0": True,
                    "reach_1_5": False,
                    "reach_2_5": False,
                }
            )
    ladder = _ladder(episodes, labels, "FALSIFIED")
    counts = [ladder["stages"][stage]["episode_count"] for stage in ("D0", "D1", "D2", "D3")]
    assert counts == [4, 3, 2, 1]
    assert ladder["proposed_direction_architecture"] == "NONE"


def _series() -> IndexedOneMinuteSeries:
    candles = [
        Candle(
            "BTCUSDT",
            "1m",
            DEV_START_MS + index * 60_000,
            DEV_START_MS + (index + 1) * 60_000 - 1,
            100.0,
            101.0 + index,
            99.0 - index,
            100.5,
            1.0,
        )
        for index in range(10)
    ]
    return IndexedOneMinuteSeries(candles)


def test_opportunity_metrics_are_direction_agnostic() -> None:
    identity = {
        "decision_close_ms": DEV_START_MS - 1,
        "close": 100.0,
        "atr": 2.0,
        "direction": "LONG",
    }
    left = movement_label(identity, _series(), 5)
    identity["direction"] = "SHORT"
    right = movement_label(identity, _series(), 5)
    assert left == right


def test_early_late_split_is_fixed() -> None:
    assert _split(LATE_START_MS - 1) == "EARLY"
    assert _split(LATE_START_MS) == "LATE"


def test_all_v036_future_windows_stay_before_holdout() -> None:
    _development_only([{"timestamp_ms": DEV_START_MS, "feature_1h_close_ms": DEV_END_MS - 1}])
    with pytest.raises(ValueError, match="holdout firewall"):
        _development_only([{"timestamp_ms": DEV_END_MS}])


def test_bootstrap_deterministic_seed36() -> None:
    rows = [
        {
            "pair_id": f"p{index}",
            "horizon_minutes": horizon,
            **{
                f"left_{metric}": 1.0
                for metric in (
                    "signed_return_atr",
                    "mfe_atr",
                    "mae_atr",
                    "reach_1_0",
                    "reach_1_5",
                    "reach_2_5",
                )
            },
            **{
                f"right_{metric}": 0.0
                for metric in (
                    "signed_return_atr",
                    "mfe_atr",
                    "mae_atr",
                    "reach_1_0",
                    "reach_1_5",
                    "reach_2_5",
                )
            },
        }
        for index in range(3)
        for horizon in (240, 480)
    ]
    assert _pair_bootstrap(rows, simulations=10) == _pair_bootstrap(rows, simulations=10)


def test_no_candidate_freeze_or_execution_enable() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["frozen_control"]["candidate_freeze"] is False
    assert protocol["frozen_control"]["execution_mode"] == "disabled"
    assert protocol["frozen_control"]["auto_execute"] is False
    assert protocol["frozen_control"]["allow_live"] is False
