from __future__ import annotations

import json
from pathlib import Path

import pytest

from btc_quant_agent.config import AppConfig
from btc_quant_agent.cross_asset_breadth_research import (
    BASKET,
    SEED,
    _asof_feature,
    _match_controls,
    btc_momentum_direction,
    build_breadth_episodes,
    composition_audit,
    xab_direction,
)
from btc_quant_agent.funding_crowding_research import _cluster_bootstrap_median, opportunity_union

PROTOCOL = Path("configs/research/v0.3.9_cross_asset_breadth_protocol.json")


def _row(timestamp: int, direction: str, status: str = "EXTREME") -> dict[str, object]:
    return {"timestamp_ms": timestamp, "direction": direction, "feature_status": status}


def test_cross_asset_basket_identity_is_frozen() -> None:
    assert BASKET == ("ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LTCUSDT")


def test_cross_asset_uses_only_closed_hourly_bars() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol["feature"]["lookback_completed_1h_bars"] == 4
    assert "fully closed" in protocol["data"]["missing_rule"]


def test_cross_asset_feature_never_reads_future_bar() -> None:
    rows = [_row(100, "LONG"), _row(200, "SHORT")]
    assert _asof_feature(199, rows) == rows[0]
    assert _asof_feature(99, rows) is None


def test_cross_asset_missing_member_invalidates_feature() -> None:
    with pytest.raises(ValueError, match="five"):
        xab_direction([1, 1, 1, 1])


def test_xab4h_rule_exactly_four_of_five() -> None:
    assert xab_direction([1, 1, 1, 1, -1]) == "LONG"
    assert xab_direction([-1, -1, -1, -1, 1]) == "SHORT"


def test_xab4h_no_bias_for_three_of_five() -> None:
    assert xab_direction([1, 1, 1, -1, -1]) == "NO_BIAS"


def test_breadth_episode_breaks_on_no_bias() -> None:
    onsets, _ = build_breadth_episodes(
        [_row(1, "LONG"), _row(2, "NO_BIAS", "NO_BIAS"), _row(3, "LONG")]
    )
    assert len(onsets) == 2


def test_breadth_episode_breaks_on_opposite_side() -> None:
    onsets, _ = build_breadth_episodes([_row(1, "LONG"), _row(2, "SHORT")])
    assert [row["direction"] for row in onsets] == ["LONG", "SHORT"]


def test_primary_unit_is_episode_onset() -> None:
    onsets, members = build_breadth_episodes([_row(1, "LONG"), _row(2, "LONG")])
    assert len(onsets) == 1 and len(members) == 2
    assert onsets[0]["episode_index"] == 0


def test_btc_label_starts_strictly_after_decision() -> None:
    protocol = json.loads(PROTOCOL.read_text())
    assert "strictly after" in protocol["labels"]["reference"]


def test_xab_permutation_stratifies_btc_momentum_sign() -> None:
    assert (
        "BTC trailing 4h return sign"
        in json.loads(PROTOCOL.read_text())["h26"]["permutation_strata"]
    )


def test_btc_mom4h_baseline_is_frozen() -> None:
    assert [btc_momentum_direction(v) for v in (1, 0, -1)] == ["LONG", "NO_BIAS", "SHORT"]
    assert "4h return sign" in json.loads(PROTOCOL.read_text())["h27"]["btc_baseline"]


def test_xab_vs_btc_momentum_pairing_is_deterministic() -> None:
    rows = [{"value": float(i), "week": str(i % 3), "incomplete": False} for i in range(12)]
    assert _cluster_bootstrap_median(
        rows, "value", "week", seed=SEED, simulations=20
    ) == _cluster_bootstrap_median(rows, "value", "week", seed=SEED, simulations=20)


def test_opportunity_original_direction_is_not_used() -> None:
    assert "direction" not in opportunity_union([{"timestamp_ms": 1, "direction": "SHORT"}], [])[0]


def test_opportunity_controls_match_xab_and_btc_momentum_bucket() -> None:
    features = [
        {
            "timestamp_ms": 100,
            "feature_status": "EXTREME",
            "direction": "LONG",
            "btc_mom_bucket": "POSITIVE",
        }
    ]
    candidate = {
        "opportunity_id": "O",
        "timestamp_ms": 100,
        "year": 2021,
        "atr_decile": 4,
        "direction": "LONG",
        "btc_mom_bucket": "POSITIVE",
        "bar_index": 200,
    }
    control = {
        "control_id": "C",
        "timestamp_ms": 100,
        "year": 2021,
        "atr_decile": 4,
        "bar_index": 1,
    }
    matches = _match_controls([candidate], [control], features, set())
    assert len(matches) == 1
    assert matches[0]["btc_mom_bucket"] == "POSITIVE"


def test_leave_one_out_is_diagnostic_only() -> None:
    rows = []
    for index, direction in enumerate(("LONG", "SHORT")):
        value = 1.0 if direction == "LONG" else -1.0
        rows.append(
            {
                "feature_status": "EXTREME",
                "direction": direction,
                **{f"{symbol}_r4h": value for symbol in BASKET},
            }
        )
    assert composition_audit(rows)["diagnostic_only"] is True


def test_no_v039_artifact_crosses_holdout() -> None:
    assert json.loads(PROTOCOL.read_text())["scope"]["holdout_forbidden"] is True


def test_v039_execution_remains_disabled() -> None:
    assert AppConfig().execution.mode == "disabled"
    assert json.loads(PROTOCOL.read_text())["frozen_state"]["candidate_freeze"] is False


def test_bootstrap_seed_39_is_honored() -> None:
    assert SEED == 39
    assert json.loads(PROTOCOL.read_text())["frozen_state"]["seed"] == 39
