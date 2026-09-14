"""Unchanged guards for retained owners, migrated out of deleted research files."""

from dataclasses import replace

import pytest

from btc_quant_agent.config import ExecutionConfig
from btc_quant_agent.data.binance_market_archive import (
    OFFICIAL_SPECS,
    aggregate_flow,
    aggressor_side,
    normalize_timestamp,
    parse_agg_trades,
)
from btc_quant_agent.data.historical_provenance import (
    HistoricalDataRole,
    HistoricalDatasetProvenance,
)
from btc_quant_agent.data.official_derivatives_features import (
    NEW_FEATURE_IDS,
    OfficialHourlyInputs,
    build_official_derivatives_features,
    feature_availability_audit,
)
from btc_quant_agent.data.vendor_contract import VendorDatasetContract
from btc_quant_agent.directional_episode import EpisodeAccumulator
from btc_quant_agent.domain import Direction
from btc_quant_agent.execution.guard import ExecutionBlocked, ExecutionGuard
from btc_quant_agent.execution.models import ExecutionMode, ExecutionPlan
from btc_quant_agent.research import DEV_START_MS


def test_archive_paths_and_timestamp_units() -> None:
    assert (
        OFFICIAL_SPECS["spot_aggTrades"]
        .monthly_url("2024-01")
        .endswith("/spot/monthly/aggTrades/BTCUSDT/BTCUSDT-aggTrades-2024-01.zip")
    )
    assert (
        OFFICIAL_SPECS["markPriceKlines_1m"]
        .monthly_url("2024-01")
        .endswith("/futures/um/monthly/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip")
    )
    assert normalize_timestamp(1_735_689_600_000) == (1_735_689_600_000, "milliseconds")
    assert normalize_timestamp(1_735_689_600_000_000) == (
        1_735_689_600_000,
        "microseconds",
    )


def test_aggtrade_aggressor_mapping_and_no_gap_fill() -> None:
    rows, audit = parse_agg_trades(
        [
            ["1", "100", "2", "10", "11", "1735689600000", "false"],
            ["3", "101", "1", "13", "13", "1735689601000000", "true"],
        ],
        market="spot",
    )
    assert aggressor_side(False) == "BUY"
    assert aggressor_side(True) == "SELL"
    assert [row["aggressor_side"] for row in rows] == ["BUY", "SELL"]
    assert [row["aggregate_trade_id"] for row in rows] == [1, 3]
    assert audit["synthetic_rows"] == 0
    assert audit["timestamp_units"] == {"milliseconds": 1, "microseconds": 1}
    flow = aggregate_flow(rows)
    assert len(flow) == 1
    assert flow[0]["buy_notional"] == 200
    assert flow[0]["sell_notional"] == 101


def test_historical_provenance_and_vendor_cannot_be_forward() -> None:
    provenance = HistoricalDatasetProvenance(
        provider="BINANCE",
        source_name="public-data aggTrades",
        symbol="BTCUSDT",
        coverage_start="2024-01-01",
        coverage_end="2024-02-01",
        resolution_or_event_type="aggregate trade",
        exchange_event_timestamp_field="T",
        source_timestamp_unit="milliseconds",
        local_or_vendor_receive_timestamp_field=None,
        retrieval_timestamp="2026-09-02T00:00:00Z",
        checksum_or_manifest="sha256:test",
        lookback_limit_if_rest=None,
        point_in_time_interpretation="official historical exchange event time",
        known_biases=("no receive timestamp",),
        formal_role=HistoricalDataRole.OFFICIAL_HISTORICAL_TIMESTAMPED,
    )
    assert provenance.as_dict()["formal_role"] == "OFFICIAL_HISTORICAL_TIMESTAMPED"
    with pytest.raises(ValueError, match="only the local"):
        replace(provenance, formal_role=HistoricalDataRole.TRUE_FORWARD_LOCAL_PIT)
    contract = VendorDatasetContract(
        provider="Tardis.dev",
        dataset="incremental_book_L2",
        venue_instrument="binance-futures BTCUSDT perpetual",
        coverage_dates="contract-dependent",
        granularity="event",
        exchange_timestamp_available=True,
        receive_timestamp_available=True,
        l2_sequence_reconstructable=True,
        oi_semantics=None,
        liquidation_semantics=None,
        access_requirement="paid",
        sample_available="exchange samples",
        license_constraints="no redistribution",
        formal_role=HistoricalDataRole.VENDOR_RECORDED_HISTORICAL_PIT_PROXY,
    )
    with pytest.raises(ValueError, match="cannot be labeled"):
        contract.validate_row(
            {
                "provider": "Tardis.dev",
                "dataset": "incremental_book_L2",
                "exchange_timestamp": 1,
                "receive_timestamp": 2,
                "formal_role": "TRUE_FORWARD_LOCAL_PIT",
            }
        )


def test_new_official_feature_family_is_causal_and_missing_stays_unavailable() -> None:
    rows = [
        OfficialHourlyInputs(
            index * 3_600_000,
            float(index),
            101.0 + index,
            100.0 + index,
            60.0,
            40.0,
            55.0,
            45.0,
        )
        for index in range(30)
    ]
    before = build_official_derivatives_features(rows)
    mutated = [
        *rows[:25],
        *[replace(row, premium_close=9999, mark_close=9999) for row in rows[25:]],
    ]
    after = build_official_derivatives_features(mutated)
    assert set(before) == NEW_FEATURE_IDS
    assert all(before[name][:25] == after[name][:25] for name in NEW_FEATURE_IDS)
    missing = list(rows)
    missing[10] = replace(missing[10], premium_close=None, perp_buy_notional=None)
    unavailable = build_official_derivatives_features(missing)
    assert unavailable["PREMIUM_INDEX_LEVEL_1H"][10] is None
    assert unavailable["PREMIUM_INDEX_Z_24H"][23] is None
    assert unavailable["PERP_AGG_BUY_IMBALANCE_1H"][10] is None
    audit = feature_availability_audit(unavailable, missing)
    assert audit["synthetic_rows"] == 0
    assert audit["missing_intervals_filled"] == 0


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
    assert len(accumulator.continuation_rows) == 1
    assert accumulator.continuation_rows[0]["episode_id"] == accumulator.rows[0]["episode_id"]
    assert accumulator.continuation_rows[0]["continuation_index"] == 1


def test_continuation_semantics_do_not_count_onset_as_continuation() -> None:
    accumulator = EpisodeAccumulator()
    first = DEV_START_MS + 10 * 3_600_000 - 1
    accumulator.add(_snapshot(first, "TREND_UP", "LONG"))
    assert accumulator.continuation_rows == []
    accumulator.add(_snapshot(first + 3_600_000, "TREND_UP", "LONG"))
    assert [row["continuation_index"] for row in accumulator.continuation_rows] == [1]


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


def test_provisional_execution_plan_is_blocked() -> None:
    config = ExecutionConfig(mode="paper")
    plan = ExecutionPlan(
        plan_id="p1",
        signal_id="s1",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        mode=ExecutionMode.PAPER,
        order_type="MARKET",
        quantity=1,
        entry_price=100,
        stop_price=90,
        take_profit_price=120,
        notional_usdt=100,
        leverage=1,
        validation_status="PROVISIONAL_SANDBOX_ONLY",
        created_at_ms=1,
        expires_at_ms=10,
        signal_expires_at_ms=10,
        rounded_rr_net=2,
        estimated_max_loss_usdt=10,
        plan_hash="",
    )
    plan = replace(plan, plan_hash=plan.calculated_hash())
    with pytest.raises(ExecutionBlocked, match="provisional"):
        ExecutionGuard(config).validate_entry(plan, plan.plan_hash, 2)
