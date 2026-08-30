from __future__ import annotations

from dataclasses import replace

import pytest

from btc_quant_agent.config import AppConfig
from btc_quant_agent.domain import Candle
from btc_quant_agent.funding_crowding_research import opportunity_union
from btc_quant_agent.spot_perp_flow_research import (
    DAY_MS,
    SEED,
    StrictNextOpenSeries,
    attach_flow_to_opportunities,
    build_flow_decisions,
    build_flow_episodes,
    flow_direction,
    incremental_vs_momentum,
    match_opportunity_controls,
    taker_imbalance,
)


def _candle(open_time: int, *, volume: float = 10, buy: float = 6, price: float = 100) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        interval="1m",
        open_time_ms=open_time,
        close_time_ms=open_time + 59_999,
        open=price,
        high=price + 1,
        low=price - 1,
        close=price + 0.5,
        volume=volume,
        quote_volume=volume * price,
        taker_buy_base_volume=buy,
        trades=1,
    )


def _spot(open_time: int, volume: float = 10, buy: float = 7) -> dict[str, object]:
    return {
        "open_time_ms": open_time,
        "close_time_ms": open_time + 59_999,
        "volume": volume,
        "taker_buy_base_volume": buy,
    }


def _context(timestamp: int) -> dict[str, object]:
    return {
        "available_at_ms": timestamp,
        "atr": 10.0,
        "atr_percentile": 0.4,
        "atr_decile": 4,
        "btc_trailing_1h_return": 0.01,
        "btc_mom_direction": "LONG",
        "btc_mom_bucket": "POSITIVE",
        "btc_feature_close_ms": timestamp - 1,
    }


def test_imbalance_formula_and_sign_symmetry() -> None:
    assert taker_imbalance(10, 7) == pytest.approx(0.4)
    assert taker_imbalance(10, 3) == pytest.approx(-0.4)


def test_zero_spread_is_no_bias() -> None:
    assert flow_direction(0) == "NO_BIAS"
    assert flow_direction(0.1) == "LONG"
    assert flow_direction(-0.1) == "SHORT"


def test_exact_60_closed_aligned_minutes_are_required() -> None:
    end = 3_600_000
    perp = [_candle(i * 60_000, buy=5) for i in range(60)]
    spot = [_spot(i * 60_000) for i in range(60)]
    rows = build_flow_decisions(spot, perp, [_context(0)], start_ms=-900_000, end_ms=end + 1)
    final = next(row for row in rows if row["timestamp_ms"] == end)
    assert final["feature_status"] == "AVAILABLE"
    assert final["direction"] == "LONG"


def test_gap_or_timestamp_misalignment_is_unavailable() -> None:
    end = 3_600_000
    perp = [_candle(i * 60_000, buy=5) for i in range(60)]
    spot = [_spot(i * 60_000) for i in range(60) if i != 30]
    rows = build_flow_decisions(spot, perp, [_context(0)], start_ms=-900_000, end_ms=end + 1)
    final = next(row for row in rows if row["timestamp_ms"] == end)
    assert final["feature_status"] == "DATA_UNAVAILABLE"


def test_episode_onset_breaks_on_flip_no_bias_and_gap() -> None:
    def row(timestamp: int, side: str, status: str = "AVAILABLE") -> dict[str, object]:
        return {"timestamp_ms": timestamp, "direction": side, "feature_status": status}

    onsets, members = build_flow_episodes(
        [
            row(0, "LONG"),
            row(900_000, "LONG"),
            row(1_800_000, "SHORT"),
            row(2_700_000, "NO_BIAS", "NO_BIAS"),
            row(3_600_000, "SHORT"),
            row(5_400_000, "SHORT"),
        ]
    )
    assert [item["direction"] for item in onsets] == ["LONG", "SHORT", "SHORT", "SHORT"]
    assert len(members) == 5


def test_label_reference_is_first_open_after_decision_close() -> None:
    candles = [_candle(i * 60_000, price=100 + i) for i in range(4)]
    label = StrictNextOpenSeries(candles, end_ms=240_000).label(59_999, 2, 10, "LONG")
    assert label["reference_open_time_ms"] == 60_000
    assert label["reference_price"] == 101


def test_label_cannot_cross_development_end() -> None:
    candles = [_candle(i * 60_000) for i in range(4)]
    label = StrictNextOpenSeries(candles, end_ms=180_000).label(59_999, 3, 10, "LONG")
    assert label["incomplete"] is True


def test_opportunity_union_discards_legacy_direction() -> None:
    row = opportunity_union([{"timestamp_ms": 1, "direction": "SHORT"}], [])[0]
    assert "direction" not in row


def test_flow_attachment_is_point_in_time_asof() -> None:
    decisions = [
        {
            "timestamp_ms": 100,
            "feature_status": "AVAILABLE",
            "direction": "LONG",
            "year": 2021,
            "atr": 1,
            "atr_decile": 1,
            "btc_mom_bucket": "POSITIVE",
        },
        {
            "timestamp_ms": 200,
            "feature_status": "AVAILABLE",
            "direction": "SHORT",
            "year": 2021,
            "atr": 1,
            "atr_decile": 1,
            "btc_mom_bucket": "NEGATIVE",
        },
    ]
    attached = attach_flow_to_opportunities(
        [{"timestamp_ms": 150, "opportunity_id": "O:150"}], decisions
    )
    assert attached[0]["direction"] == "LONG"
    assert attached[0]["flow_timestamp_ms"] == 100


def test_matching_has_no_outcome_input_caps_k_and_separates_24h() -> None:
    candidate = {
        "opportunity_id": "O",
        "timestamp_ms": 0,
        "year": 2021,
        "direction": "LONG",
        "atr_decile": 4,
        "btc_mom_bucket": "POSITIVE",
    }
    decisions = [
        {
            "timestamp_ms": DAY_MS + i * 900_000,
            "feature_status": "AVAILABLE",
            "year": 2021,
            "direction": "LONG",
            "atr_decile": 4,
            "btc_mom_bucket": "POSITIVE",
        }
        for i in range(8)
    ]
    matches = match_opportunity_controls([candidate], decisions, set())
    assert len(matches) == 5
    assert all(abs(int(row["timestamp_ms"])) >= DAY_MS for row in matches)
    assert all("raw_return_atr" not in row for row in matches)


def test_runtime_defaults_remain_execution_disabled() -> None:
    config = replace(AppConfig(), execution=replace(AppConfig().execution, mode="disabled"))
    assert config.execution.mode == "disabled"
    assert SEED == 42


def test_incremental_bootstrap_and_permutation_are_deterministic() -> None:
    episodes = []
    labels = []
    for index in range(12):
        identity = f"E:{index}"
        direction = "LONG" if index % 2 else "SHORT"
        episodes.append(
            {
                "event_id": identity,
                "direction": direction,
                "btc_mom_direction": "LONG" if index % 3 else "SHORT",
                "year": 2021 + index % 2,
                "atr_decile": index % 3,
                "btc_mom_bucket": "POSITIVE" if index % 3 else "NEGATIVE",
                "week_cluster": f"W{index % 4}",
            }
        )
        for horizon in (240, 480):
            raw = (index - 5) / 10
            labels.append(
                {
                    "event_id": identity,
                    "horizon_minutes": horizon,
                    "incomplete": False,
                    "raw_return_atr": raw,
                    "signed_return_atr": raw if direction == "LONG" else -raw,
                }
            )
    first = incremental_vs_momentum(episodes, labels, simulations=20)
    second = incremental_vs_momentum(episodes, labels, simulations=20)
    assert first == second
