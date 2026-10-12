"""Tests for ReplayEngine, immutable log replay, and audit witness generation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.contracts import (
    ALLOWED_PRODUCT,
    MarketEventV1,
    compute_sha256,
)
from market_data.forward_public_feed_r1.durability import DurabilityError, SegmentWriter
from market_data.forward_public_feed_r1.fixture import DeterministicExchangeFixture
from market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine
from market_data.forward_public_feed_r1.replay import ReplayEngine, ReplayWitness


def test_replay_empty_directory_raises(tmp_path: Path) -> None:
    engine = ReplayEngine(data_dir=tmp_path)
    with pytest.raises(DurabilityError, match="No segment files found"):
        engine.replay_all()


def test_replay_single_segment_full_verification(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="test-replay-ep")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    book = OrderBookIntegrityEngine()

    # 1. Snapshot
    snap = fix.generate_depth_snapshot_frame(levels=10, last_update_id=1000)
    snap_receipt = book.apply_snapshot(snap, observed_wall_ms=1000)
    snap_ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="depth_snapshot",
        provider_event_ms=snap["E"],
        provider_transaction_ms=snap["T"],
        observed_wall_utc_ms=1000,
        observed_monotonic_ns=1_000_000_000,
        available_at_ms=1000,
        source_stream_id="btcusdt@depth_snapshot",
        connection_epoch="test-replay-ep",
        source_sequence=1000,
        payload_sha256=compute_sha256(snap),
        payload=snap,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256=writer.manifest_sha256,
        book=snap_receipt,
    )
    writer.append_event(snap_ev)

    # 2. Continuous deltas
    for i in range(5):
        delta = fix.generate_depth_delta_frame(span=2)
        d_receipt = book.apply_delta(delta, observed_wall_ms=1000 + (i + 1) * 100)
        d_ev = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="depth_delta",
            provider_event_ms=delta["E"],
            provider_transaction_ms=delta["T"],
            observed_wall_utc_ms=1000 + (i + 1) * 100,
            observed_monotonic_ns=1_000_000_000 + (i + 1) * 100_000,
            available_at_ms=1000 + (i + 1) * 100,
            source_stream_id="btcusdt@depth@100ms",
            connection_epoch="test-replay-ep",
            source_sequence=delta["u"],
            payload_sha256=compute_sha256(delta),
            payload=delta,
            quality=d_receipt.quality,
            reason_codes=d_receipt.reason_codes,
            raw_source_manifest_sha256=writer.manifest_sha256,
            book=d_receipt,
        )
        writer.append_event(d_ev)

    writer.close()

    # Replay
    engine = ReplayEngine(data_dir=tmp_path)
    events, witness = engine.replay_all()

    assert len(events) == 6
    assert witness.events_replayed == 6
    assert witness.depth_continuous is True
    assert witness.first_wall_utc_ms == 1000
    assert witness.last_wall_utc_ms == 1500
    assert witness.channel_counts["depth_snapshot"] == 1
    assert witness.channel_counts["depth_delta"] == 5
    assert witness.quality_counts["VERIFIED"] == 6


def test_replay_preserves_original_arrival_watermarks(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="test-watermark-ep")
    payload = {"price": "65000.00"}
    ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="agg_trade",
        provider_event_ms=5000,
        provider_transaction_ms=4998,
        observed_wall_utc_ms=5050,
        observed_monotonic_ns=2_500_000_000,
        available_at_ms=5050,
        source_stream_id="btcusdt@aggTrade",
        connection_epoch="test-watermark-ep",
        source_sequence=1,
        payload_sha256=compute_sha256(payload),
        payload=payload,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256=writer.manifest_sha256,
    )
    writer.append_event(ev)
    writer.close()

    engine = ReplayEngine(data_dir=tmp_path)
    events, _witness = engine.replay_all()
    assert len(events) == 1
    r_ev = events[0]
    # Original timestamps must match exactly
    assert r_ev.observed_wall_utc_ms == 5050
    assert r_ev.observed_monotonic_ns == 2_500_000_000
    assert r_ev.available_at_ms == 5050
    assert r_ev.available_at_ms >= r_ev.observed_wall_utc_ms


def test_replay_flags_discontinuous_orderbook(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="test-gap-replay")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")

    # Snapshot
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)
    snap_ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="depth_snapshot",
        provider_event_ms=snap["E"],
        provider_transaction_ms=snap["T"],
        observed_wall_utc_ms=1000,
        observed_monotonic_ns=1_000_000_000,
        available_at_ms=1000,
        source_stream_id="btcusdt@depth_snapshot",
        connection_epoch="test-gap-replay",
        source_sequence=1000,
        payload_sha256=compute_sha256(snap),
        payload=snap,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256=writer.manifest_sha256,
    )
    writer.append_event(snap_ev)

    # Discontinuous delta (pu=2000 != 1000)
    gap_delta = fix.generate_depth_delta_frame(span=2, force_pu=2000)
    gap_ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="depth_delta",
        provider_event_ms=gap_delta["E"],
        provider_transaction_ms=gap_delta["T"],
        observed_wall_utc_ms=1100,
        observed_monotonic_ns=1_100_000_000,
        available_at_ms=1100,
        source_stream_id="btcusdt@depth@100ms",
        connection_epoch="test-gap-replay",
        source_sequence=gap_delta["u"],
        payload_sha256=compute_sha256(gap_delta),
        payload=gap_delta,
        quality="INVALID",
        reason_codes=["GAP_DETECTED"],
        raw_source_manifest_sha256=writer.manifest_sha256,
    )
    writer.append_event(gap_ev)
    writer.close()

    engine = ReplayEngine(data_dir=tmp_path)
    _events, witness = engine.replay_all()
    assert witness.depth_continuous is False
    assert witness.events_replayed == 2


def test_replay_witness_to_dict_structure() -> None:
    witness = ReplayWitness(
        events_replayed=10,
        first_wall_utc_ms=1000,
        last_wall_utc_ms=2000,
        head_hash="head_hash_123",
        depth_continuous=True,
        channel_counts={"agg_trade": 10},
        quality_counts={"VERIFIED": 10},
        reason_code_counts={"OK": 10},
    )
    d = witness.to_dict()
    assert d["events_replayed"] == 10
    assert d["depth_continuous"] is True
    assert d["head_hash"] == "head_hash_123"
