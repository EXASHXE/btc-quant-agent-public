from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.funding_crowding_research import (
    StrictAfterPriceSeries,
    _cluster_bootstrap_median,
    funding_direction,
    opportunity_union,
)
from btc_quant_agent.funding_stability_research import (
    SEED,
    build_extreme_episodes,
    h22_verdict,
    interaction_verdict,
)
from btc_quant_agent.research import DEV_END_MS, DEV_START_MS

PROTOCOL = Path("configs/research/v0.3.8_funding_stability_protocol.json")


def _feature(timestamp: int, direction: str) -> dict[str, object]:
    return {
        "timestamp_ms": timestamp,
        "funding_direction": direction,
        "year": 2021,
        "split": "EARLY",
    }


def test_funding_episode_onset_excludes_repeated_same_tail_settlements() -> None:
    onsets, members = build_extreme_episodes([_feature(1, "LONG"), _feature(2, "LONG")])
    assert len(onsets) == 1
    assert [row["episode_index"] for row in members] == [0, 1]


def test_funding_episode_breaks_on_middle_or_opposite_tail() -> None:
    rows = [_feature(1, "LONG"), _feature(2, "NO_BIAS"), _feature(3, "LONG"), _feature(4, "SHORT")]
    onsets, _ = build_extreme_episodes(rows)
    assert [row["funding_direction"] for row in onsets] == ["LONG", "LONG", "SHORT"]


def test_funding_episode_direction_rule_unchanged_from_v037() -> None:
    assert funding_direction(0.25) == "LONG"
    assert funding_direction(0.75) == "SHORT"
    assert funding_direction(0.5) == "NO_BIAS"


def _candle(open_ms: int) -> Candle:
    return Candle("BTCUSDT", "1m", open_ms, open_ms + 59_999, 100, 101, 99, 100, 1)


def test_episode_labels_start_strictly_after_settlement() -> None:
    timestamp = DEV_START_MS + 60_000
    label = StrictAfterPriceSeries([_candle(timestamp), _candle(timestamp + 60_000)]).label(
        timestamp, 1, 1, "LONG"
    )
    assert label["reference_open_time_ms"] == timestamp + 60_000


def test_episode_horizons_do_not_cross_holdout() -> None:
    assert StrictAfterPriceSeries([_candle(DEV_END_MS - 60_000)]).label(
        DEV_END_MS - 120_000, 480, 1, "LONG"
    )["incomplete"]


def test_persistence_index_is_diagnostic_only() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["episodes"]["member_index_buckets"] == ["0", "1", ">=2"]
    assert "strategy arm" not in json.dumps(protocol).lower()


def test_market_state_is_asof_closed_data_only() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert "latest fully closed 1H" in protocol["market_state_attribution"]["source"]


@pytest.mark.parametrize("tag", ["TP", "BR"])
def test_h24_h25_ignore_original_pattern_direction(tag: str) -> None:
    raw = [{"timestamp_ms": 1, "direction": "SHORT"}]
    row = opportunity_union(raw if tag == "BR" else [], raw if tag == "TP" else [])[0]
    assert "direction" not in row


def test_h24_controls_match_funding_tail_year_atr_without_future_labels() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    controls = protocol["interaction_common"]["controls"]
    assert "same year/15m ATR decile/Funding side" in controls
    assert ">=24h" in controls


def test_interaction_bootstrap_clusters_by_utc_day() -> None:
    rows = [{"day": str(i % 4), "value": float(i), "incomplete": False} for i in range(16)]
    result = _cluster_bootstrap_median(rows, "value", "day", seed=SEED, simulations=20)
    assert result["cluster_field"] == "day"
    assert result == _cluster_bootstrap_median(rows, "value", "day", seed=SEED, simulations=20)


def _h22() -> tuple[dict[str, object], ...]:
    summary = {
        "week_clusters": 100,
        "horizons": {
            f"{h}m": {
                "count": 300,
                "signed_median": 0.1,
                "by_direction": {
                    s: {"count": 150, "signed_median": 0.1} for s in ("LONG", "SHORT")
                },
            }
            for h in (240, 480)
        },
    }
    boot = {f"{h}m": {"p05": 0} for h in (240, 480)}
    perm = {"horizons": {f"{h}m": {"deterministic_point_delta": 0.1} for h in (240, 480)}}
    split = {s: {f"{h}m": {"signed_median": 0.1} for h in (240, 480)} for s in ("EARLY", "LATE")}
    return summary, boot, perm, split


def _interaction() -> dict[str, object]:
    return {
        "day_clusters": 80,
        "bootstrap": {f"{h}m": {"p05": 0} for h in (240, 480)},
        "horizons": {
            f"{h}m": {
                "count": 180,
                "signed_median": 0.1,
                "candidate_minus_control_delta": 0.1,
                "by_direction": {s: {"count": 90, "signed_median": 0.1} for s in ("LONG", "SHORT")},
                "by_split": {s: 0.1 for s in ("EARLY", "LATE")},
            }
            for h in (240, 480)
        },
    }


def test_h22_h24_h25_verdicts_follow_protocol() -> None:
    assert h22_verdict(*_h22()) == "SUPPORTED"
    assert interaction_verdict(_interaction()) == "SUPPORTED"
    low = copy.deepcopy(_interaction())
    low["day_clusters"] = 1
    assert interaction_verdict(low) == "INCONCLUSIVE_LOW_SAMPLE"
    false = copy.deepcopy(_interaction())
    for h in (240, 480):
        false["horizons"][f"{h}m"]["candidate_minus_control_delta"] = -0.1
    assert interaction_verdict(false) == "FALSIFIED"


def test_no_funding_window_or_threshold_variants_exist() -> None:
    feature = json.loads(PROTOCOL.read_text())["funding_feature"]
    assert feature["history_events"] == 270
    assert feature["window_or_threshold_scan"] is False


def test_v038_artifacts_are_development_only() -> None:
    scope = json.loads(PROTOCOL.read_text())["scope"]
    assert scope["holdout_forbidden"] is True
    assert scope["development"].endswith("2026-02-01T00:00:00Z)")


def test_final_holdout_unconsumed() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert "Final Holdout" in protocol["prohibitions"]
    assert protocol["frozen_state"]["candidate_freeze"] is False
