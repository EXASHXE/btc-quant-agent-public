from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from btc_quant_agent.backtest import FundingEvent
from btc_quant_agent.config import AppConfig
from btc_quant_agent.domain import Candle
from btc_quant_agent.funding_crowding_research import (
    SEED,
    STALE_MS,
    StrictAfterPriceSeries,
    _cluster_bootstrap_median,
    asof_funding,
    attach_funding_to_opportunities,
    build_funding_features,
    causal_funding_percentile,
    funding_direction,
    h19_verdict,
    h20_verdict,
    h21_verdict,
    opportunity_union,
)
from btc_quant_agent.research import DEV_END_MS, DEV_START_MS

PROTOCOL = Path("configs/research/v0.3.7_funding_crowding_protocol.json")


def _events(count: int = 272) -> list[FundingEvent]:
    return [
        FundingEvent(DEV_START_MS + index * 28_800_000, float(index), 100.0)
        for index in range(count)
    ]


def _candle(open_ms: int, close: float = 100.0) -> Candle:
    return Candle(
        "BTCUSDT", "1m", open_ms, open_ms + 59_999, close, close + 1, close - 1, close, 1.0
    )


def test_funding_features_use_only_prior_270_settlements() -> None:
    rows = build_funding_features(_events())
    assert rows[269]["feature_status"] == "WARMUP_INCOMPLETE"
    assert rows[270]["funding_percentile"] == pytest.approx(1.0)
    assert rows[270]["history_count"] == 270


def test_current_funding_not_in_reference_distribution() -> None:
    values = [FundingEvent(DEV_START_MS + i, 0.0, 100.0) for i in range(270)]
    values.append(FundingEvent(DEV_START_MS + 270, 1.0, 100.0))
    assert build_funding_features(values)[-1]["funding_percentile"] == 1.0


def test_funding_percentile_tie_formula() -> None:
    assert causal_funding_percentile([0.0] * 135 + [1.0] * 135, 1.0) == pytest.approx(0.75)


def test_funding_tail_direction_mapping() -> None:
    assert [funding_direction(value) for value in (0.25, 0.5, 0.75)] == ["LONG", "NO_BIAS", "SHORT"]


def test_funding_warmup_is_incomplete_before_270() -> None:
    assert all(
        row["feature_status"] == "WARMUP_INCOMPLETE" for row in build_funding_features(_events(270))
    )


def test_funding_future_label_starts_after_settlement() -> None:
    event = DEV_START_MS + 60_000
    series = StrictAfterPriceSeries(
        [_candle(event), _candle(event + 60_000), _candle(event + 120_000)]
    )
    label = series.label(event, 1, 1.0, "LONG")
    assert label["reference_open_time_ms"] == event + 60_000


def test_funding_asof_never_uses_future_settlement() -> None:
    rows = [{"timestamp_ms": 100}, {"timestamp_ms": 200}]
    assert asof_funding(199, rows) == rows[0]
    assert asof_funding(99, rows) is None


def test_opportunity_funding_stale_rule() -> None:
    feature = {
        "timestamp_ms": 100,
        "feature_status": "EXTREME",
        "funding_direction": "LONG",
        "funding_percentile": 0.1,
    }
    opportunity = {
        "timestamp_ms": 100 + STALE_MS + 1,
        "opportunity_id": "O:1",
        "setup_tag": "BR",
        "decision_close_ms": 100,
        "atr": 1.0,
        "close": 1.0,
    }
    row = attach_funding_to_opportunities([opportunity], [feature], {})[0]
    assert row["funding_status"] == "STALE_FUNDING"
    assert row["funding_direction"] == "NO_BIAS"


def test_opportunity_union_deduplicates_exact_timestamp_only() -> None:
    rows = opportunity_union([{"timestamp_ms": 1}, {"timestamp_ms": 2}], [{"timestamp_ms": 1}])
    assert len(rows) == 2
    assert rows[0]["setup_tag"] == "BR+TP"


def test_original_tp_br_direction_not_used_for_h20() -> None:
    row = opportunity_union([{"timestamp_ms": 1, "direction": "SHORT"}], [])[0]
    assert "direction" not in row


def test_week_cluster_bootstrap_deterministic() -> None:
    rows = [{"week": str(i % 3), "value": float(i), "incomplete": False} for i in range(12)]
    assert _cluster_bootstrap_median(
        rows, "value", "week", simulations=20
    ) == _cluster_bootstrap_median(rows, "value", "week", simulations=20)


def test_day_cluster_bootstrap_deterministic() -> None:
    rows = [{"day": str(i % 4), "value": float(i), "incomplete": False} for i in range(16)]
    assert _cluster_bootstrap_median(
        rows, "value", "day", simulations=20, seed=SEED
    ) == _cluster_bootstrap_median(rows, "value", "day", simulations=20, seed=SEED)


def _h19_inputs() -> tuple[dict[str, object], ...]:
    summary = {
        "week_clusters": 100,
        "horizons": {
            f"{h}m": {
                "count": 400,
                "signed_median": 0.1,
                "by_direction": {
                    s: {"count": 200, "signed_median": 0.1} for s in ("LONG", "SHORT")
                },
            }
            for h in (240, 480)
        },
    }
    bootstrap = {f"{h}m": {"p05": 0.0} for h in (240, 480)}
    permutation = {"horizons": {f"{h}m": {"deterministic_point_delta": 0.1} for h in (240, 480)}}
    tail = {
        "horizons": {
            f"{h}m": {
                "bottom_minus_top": 0.1,
                "week_cluster_bootstrap": {"p05": 0.0},
                "spearman_percentile_raw_return": -0.1,
            }
            for h in (240, 480)
        }
    }
    early_late = {
        split: {f"{h}m": {"signed_median": 0.1} for h in (240, 480)} for split in ("EARLY", "LATE")
    }
    return summary, bootstrap, permutation, tail, early_late


def test_h19_verdict_matches_protocol_all_branches() -> None:
    args = _h19_inputs()
    assert h19_verdict(*args) == "SUPPORTED"
    low = copy.deepcopy(args)
    low[0]["horizons"]["480m"]["count"] = 1
    assert h19_verdict(*low) == "INCONCLUSIVE_LOW_SAMPLE"
    false = copy.deepcopy(args)
    false[0]["horizons"]["240m"]["signed_median"] = -0.1
    false[0]["horizons"]["480m"]["signed_median"] = -0.1
    assert h19_verdict(*false) == "FALSIFIED"
    inc = copy.deepcopy(args)
    inc[1]["240m"]["p05"] = -0.2
    assert h19_verdict(*inc) == "INCONCLUSIVE_MECHANISM"


def _h20_inputs() -> tuple[dict[str, object], ...]:
    summary = {
        "day_clusters": 80,
        "horizons": {
            f"{h}m": {
                "count": 120,
                "signed_median": 0.1,
                "by_direction": {s: {"count": 60, "signed_median": 0.1} for s in ("LONG", "SHORT")},
            }
            for h in (240, 480)
        },
    }
    bootstrap = {f"{h}m": {"p05": 0.0} for h in (240, 480)}
    permutation = {"horizons": {f"{h}m": {"deterministic_point_delta": 0.1} for h in (240, 480)}}
    splits = {
        split: {"horizons": {f"{h}m": {"signed_median": 0.1} for h in (240, 480)}}
        for split in ("EARLY", "LATE")
    }
    return summary, bootstrap, permutation, splits


def test_h20_verdict_matches_protocol_all_branches() -> None:
    args = _h20_inputs()
    assert h20_verdict(*args) == "SUPPORTED"
    low = copy.deepcopy(args)
    low[0]["day_clusters"] = 2
    assert h20_verdict(*low) == "INCONCLUSIVE_LOW_SAMPLE"
    false = copy.deepcopy(args)
    false[2]["horizons"]["240m"]["deterministic_point_delta"] = -0.1
    false[2]["horizons"]["480m"]["deterministic_point_delta"] = -0.1
    assert h20_verdict(*false) == "FALSIFIED"
    inc = copy.deepcopy(args)
    inc[1]["240m"]["p05"] = -0.2
    assert h20_verdict(*inc) == "INCONCLUSIVE_MECHANISM"


def _h21_inputs() -> tuple[dict[str, object], dict[str, object]]:
    summary = {
        "day_clusters": 30,
        "horizons": {
            f"{h}m": {
                "count": 40,
                "metrics": {m: {"delta": 0.1} for m in ("future_range_atr", "max_excursion_atr")},
            }
            for h in (240, 480)
        },
        "early_late": {
            split: {f"{h}m_future_range_delta": 0.1 for h in (240, 480)}
            for split in ("EARLY", "LATE")
        },
    }
    return summary, {f"{h}m": {"p05": 0.0, "p95": 0.2} for h in (240, 480)}


def test_h21_verdict_matches_protocol_all_branches() -> None:
    args = _h21_inputs()
    assert h21_verdict(*args) == "SUPPORTED"
    low = copy.deepcopy(args)
    low[0]["day_clusters"] = 1
    assert h21_verdict(*low) == "INCONCLUSIVE_LOW_SAMPLE"
    false = copy.deepcopy(args)
    for h in (240, 480):
        for m in ("future_range_atr", "max_excursion_atr"):
            false[0]["horizons"][f"{h}m"]["metrics"][m]["delta"] = -0.1
    assert h21_verdict(*false) == "FALSIFIED"
    inc = copy.deepcopy(args)
    inc[1]["240m"]["p05"] = -0.2
    assert h21_verdict(*inc) == "INCONCLUSIVE_MECHANISM"


def test_24h_labels_never_cross_holdout() -> None:
    bars = [_candle(DEV_END_MS - 10 * 60_000 + i * 60_000) for i in range(10)]
    assert StrictAfterPriceSeries(bars).label(DEV_END_MS - 11 * 60_000, 1440, 1.0, "LONG")[
        "incomplete"
    ]


def test_all_v037_artifacts_development_only() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert protocol["scope"]["holdout_forbidden"] is True
    assert protocol["scope"]["development"].endswith("2026-02-01T00:00:00Z)")


def test_no_oi_basis_longshort_history_used() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert protocol["prohibitions"]["oi_basis_longshort_orderbook_alpha"] is False


def test_no_candidate_freeze_or_execution_enablement() -> None:
    config = AppConfig()
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    assert config.execution.mode == "disabled"
    assert protocol["frozen_state"]["candidate_freeze"] is False
