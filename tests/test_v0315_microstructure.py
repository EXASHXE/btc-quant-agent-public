from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from btc_quant_agent.data.binance import DerivativeCollection
from btc_quant_agent.data.forward_store import (
    CADENCE_MS,
    ForwardDerivativeRecord,
    ForwardDerivativeStore,
)
from btc_quant_agent.domain import DerivativesSnapshot
from btc_quant_agent.evidence_epoch import EvidenceEpoch
from btc_quant_agent.forward_evidence import forward_evidence_status
from btc_quant_agent.microstructure import (
    AggTrade,
    DepthEvent,
    LocalOrderBook,
    MicrostructureCampaign,
    MicrostructureStore,
    SequenceGap,
    event_ofi,
)

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = ROOT / "configs/forward/v0.3.15_microstructure_capture_campaign.json"
EPOCH = ROOT / "configs/forward/v0.3.14_derivatives_evidence_epoch.json"


def _depth(first: int, final: int, previous: int, *, bid: float = 100.0) -> DepthEvent:
    return DepthEvent(1, 2, first, final, previous, ((bid, 2.0),), ((101.0, 3.0),), 3, 4)


def test_snapshot_buffer_bridge_stale_continuity_and_gap_resync() -> None:
    book = LocalOrderBook()
    snapshot = {"lastUpdateId": 100, "bids": [["99", "1"]], "asks": [["102", "1"]]}
    assert book.bootstrap(snapshot, [_depth(99, 101, 98)]) == 1
    assert book.update_id == 101
    assert book.apply(_depth(99, 101, 98)) is False
    assert book.apply(_depth(102, 103, 101, bid=100.5)) is True
    with pytest.raises(SequenceGap):
        book.apply(_depth(104, 105, 999))
    assert book.update_id is None
    assert not book.bids


def test_first_bridge_is_required_and_reconnect_starts_empty() -> None:
    book = LocalOrderBook()
    snapshot = {"lastUpdateId": 100, "bids": [], "asks": []}
    with pytest.raises(SequenceGap, match="bridges"):
        book.bootstrap(snapshot, [_depth(101, 102, 100)])
    book.reset()
    assert book.update_id is None


def test_aggtrade_maker_aggressor_semantics_and_timestamps() -> None:
    sell = AggTrade.parse({"E": 10, "T": 9, "a": 7, "p": "100", "q": "2", "m": True}, 20, 30)
    buy = AggTrade.parse({"E": 11, "T": 10, "a": 8, "p": "101", "q": "1", "m": False}, 21, 31)
    assert sell.buyer_is_maker and sell.aggressive_side == "SELL"
    assert not buy.buyer_is_maker and buy.aggressive_side == "BUY"
    assert sell.event_time_ms == 10 and sell.receive_time_ms == 20


def test_store_deduplicates_events_and_reports_real_latency(tmp_path: Path) -> None:
    campaign = MicrostructureCampaign.load(CAMPAIGN)
    store = MicrostructureStore(tmp_path, campaign.campaign_id, campaign.start_ms)
    trade = AggTrade(10, 7, 100.0, 2.0, True, "SELL", 9, 20, 30)
    depth = _depth(1, 2, 0)
    assert store.append_trade(trade)
    assert not store.append_trade(trade)
    assert store.append_depth(depth)
    assert not store.append_depth(depth)
    status = store.status(campaign.start_ms + 1_000)
    assert status["agg_trade_events"] == 1
    assert status["depth_events"] == 1
    assert status["latency_ms"]["p50"] == 10
    assert status["aggregate_buckets"] == 3
    assert status["aggregation_intervals_ms"] == [1_000, 60_000, 900_000]
    assert status["duplicate_count"] == 2
    assert status["conflict_count"] == 0
    assert status["direction_claim"] == "NONE"


def test_book_samples_aggregate_without_future_data_and_gap_marks_bucket(tmp_path: Path) -> None:
    campaign = MicrostructureCampaign.load(CAMPAIGN)
    store = MicrostructureStore(tmp_path, campaign.campaign_id, campaign.start_ms)
    event = DepthEvent(61_000, 61_000, 1, 2, 0, ((100.0, 2.0),), ((101.0, 1.0),), 61_010, 9)
    book = LocalOrderBook()
    book.bootstrap(
        {"lastUpdateId": 1, "bids": [["99", "1"]], "asks": [["102", "1"]]},
        [event],
    )
    assert store.append_book_sample(event, book.stats(), 3.5)
    assert not store.append_book_sample(event, book.stats(), 3.5)
    store.gap(61_500, "TEST_GAP", "causal completeness marker")
    path = next(tmp_path.glob("microstructure-*.sqlite3"))
    connection = sqlite3.connect(path)
    row = connection.execute(
        "SELECT book_sample_count,ofi_sum,gap_count FROM aggregates "
        "WHERE interval_ms=60000 AND bucket_start_ms=60000"
    ).fetchone()
    fifteen_minute_row = connection.execute(
        "SELECT book_sample_count,gap_count FROM aggregates "
        "WHERE interval_ms=900000 AND bucket_start_ms=0"
    ).fetchone()
    connection.close()
    assert row == (1, 3.5, 1)
    assert fifteen_minute_row == (1, 1)


def test_connected_coverage_requires_both_streams(tmp_path: Path) -> None:
    campaign = MicrostructureCampaign.load(CAMPAIGN)
    store = MicrostructureStore(tmp_path, campaign.campaign_id, campaign.start_ms)
    instance = store.instance_start(campaign.start_ms, "test-instance")
    depth_session = store.session_start(campaign.start_ms, "depth", instance)
    store.session_start(campaign.start_ms + 200, "trade", instance)
    store.heartbeat(campaign.start_ms + 1_000, instance)
    status = store.status(campaign.start_ms + 1_000)
    assert status["connected_seconds_by_stream"] == {"depth": 1.0, "trade": 0.8}
    assert status["connected_seconds"] == 0.8
    assert status["uptime_ratio"] == 0.8
    store.session_end(campaign.start_ms + 1_000, depth_session)


def test_event_ofi_is_sign_symmetric_and_has_no_future_price() -> None:
    previous = (100.0, 2.0, 101.0, 3.0)
    current = (100.0, 4.0, 101.0, 1.0)
    assert event_ofi(previous, current) == 4.0
    mirrored_previous = (-101.0, 3.0, -100.0, 2.0)
    mirrored_current = (-101.0, 1.0, -100.0, 4.0)
    assert event_ofi(mirrored_previous, mirrored_current) == -4.0


def test_derivatives_status_uses_epoch_source_of_truth_not_archive(tmp_path: Path) -> None:
    epoch = EvidenceEpoch.load(EPOCH)
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    empty = {field: False for field in epoch.required_fields}
    for index in range(6):
        collection = DerivativeCollection(
            index * CADENCE_MS,
            index * CADENCE_MS + 1,
            DerivativesSnapshot(observed_at_ms=index * CADENCE_MS + 1),
            epoch.required_fields,
            empty,
            {"all": "failed"},
        )
        store.append(
            ForwardDerivativeRecord.from_collection(
                "BTCUSDT", f"legacy-{index}", collection, trigger_source="LEGACY_UNKNOWN"
            )
        )
    status = store.status(evidence_epoch_path=EPOCH, now_ms=epoch.epoch_start_ms)
    assert status["research_eligibility"] == status["active_epoch"]["eligibility_state"]
    assert status["archive_pre_epoch"]["classification"] == "NOT_FOR_ELIGIBILITY"
    assert status["archive_pre_epoch"]["largest_gap_slots"] >= 6

    combined = forward_evidence_status(
        derivatives_store_path=store.path,
        opportunity_store_path=tmp_path / "opportunity.sqlite3",
        epoch_path=EPOCH,
        campaign_path=ROOT / "configs/forward/v0.3.13_opportunity_shadow_campaign.json",
        microstructure_root=tmp_path / "microstructure",
        microstructure_campaign_path=CAMPAIGN,
        now_ms=epoch.epoch_start_ms,
    )
    assert (
        status["research_eligibility"]
        == combined["derivatives"]["active_epoch"]["eligibility_state"]
    )


def test_campaign_is_data_only_and_frozen() -> None:
    campaign = MicrostructureCampaign.load(CAMPAIGN)
    assert campaign.campaign_id == "MICROSTRUCTURE_FORWARD_V0315_20260831T190000Z"
    assert "/public/stream?streams=btcusdt@depth@100ms" in campaign.depth_url
    assert "/market/stream?streams=btcusdt@aggTrade" in campaign.trade_url
