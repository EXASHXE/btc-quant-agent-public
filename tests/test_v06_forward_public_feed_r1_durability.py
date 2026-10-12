"""Tests for SegmentWriter, SegmentReader, hash-chaining, atomic manifests, and torn-write recovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.contracts import (
    MarketEventV1,
    compute_sha256,
)
from market_data.forward_public_feed_r1.durability import (
    GENESIS_HASH,
    DurabilityError,
    SegmentReader,
    SegmentWriter,
)


def _make_dummy_event(seq: int, wall_ms: int = 1728720000000) -> MarketEventV1:
    payload = {"price": f"{65000 + seq}.00", "qty": "0.1"}
    return MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product="BINANCE_USDT_M_PERP",
        channel="agg_trade",
        provider_event_ms=wall_ms,
        provider_transaction_ms=wall_ms - 2,
        observed_wall_utc_ms=wall_ms + 10,
        observed_monotonic_ns=1_000_000_000 + seq * 1000,
        available_at_ms=wall_ms + 10,
        source_stream_id="btcusdt@aggTrade",
        connection_epoch="test-durability-epoch",
        source_sequence=seq,
        payload_sha256=compute_sha256(payload),
        payload=payload,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="msha",
    )


def test_segment_writer_initialization(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="ep1")
    assert writer.segment_index == 1
    assert writer.current_record_count == 0
    assert writer.head_hash == GENESIS_HASH
    writer.close()

    manifest_file = tmp_path / "manifest_ep1_000001.json"
    assert manifest_file.exists()
    man = SegmentReader.read_manifest(manifest_file)
    assert man["record_count"] == 0
    assert man["head_hash"] == GENESIS_HASH


def test_segment_writer_hash_chain_append(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="ep1")
    e1 = _make_dummy_event(1)
    e2 = _make_dummy_event(2)

    h1 = writer.append_event(e1)
    assert h1 != GENESIS_HASH
    assert writer.head_hash == h1

    h2 = writer.append_event(e2)
    assert h2 != h1
    assert writer.head_hash == h2
    writer.close()

    seg_file = tmp_path / "segment_ep1_000001.jsonl"
    events, head_hash = SegmentReader.read_segment(seg_file)
    assert len(events) == 2
    assert head_hash == h2
    assert events[0].source_sequence == 1
    assert events[1].source_sequence == 2


def test_manifest_tampering_detection(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="ep1")
    writer.append_event(_make_dummy_event(1))
    writer.close()

    manifest_file = tmp_path / "manifest_ep1_000001.json"
    with open(manifest_file, "r") as f:
        data = json.load(f)

    # Tamper record_count
    data["record_count"] = 999
    with open(manifest_file, "w") as f:
        json.dump(data, f)

    with pytest.raises(DurabilityError, match="Manifest sha mismatch"):
        SegmentReader.read_manifest(manifest_file)


def test_hash_chain_break_detection(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="ep1")
    writer.append_event(_make_dummy_event(1))
    writer.append_event(_make_dummy_event(2))
    writer.close()

    seg_file = tmp_path / "segment_ep1_000001.jsonl"
    lines = seg_file.read_text(encoding="utf-8").splitlines()

    # Tamper line 2 prev_hash
    line2 = json.loads(lines[1])
    line2["prev_hash"] = "ffff" * 16
    lines[1] = json.dumps(line2)
    seg_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(DurabilityError, match="Hash chain break"):
        SegmentReader.read_segment(seg_file)


def test_torn_write_detection_without_repair(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="ep1")
    writer.append_event(_make_dummy_event(1))
    writer.close()

    seg_file = tmp_path / "segment_ep1_000001.jsonl"
    with open(seg_file, "a") as f:
        f.write('{"index": 2, "prev_hash": "partially_written_json_fragment...\n')

    with pytest.raises(DurabilityError, match="Segment corruption"):
        SegmentReader.read_segment(seg_file, auto_repair_torn_write=False)


def test_torn_write_auto_repair_and_quarantine(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="ep1")
    e1 = _make_dummy_event(1)
    h1 = writer.append_event(e1)
    writer.close()

    seg_file = tmp_path / "segment_ep1_000001.jsonl"
    # Append torn write
    with open(seg_file, "a") as f:
        f.write('{"index": 2, "broken_record": ... truncated\n')

    events, head_hash = SegmentReader.read_segment(seg_file, auto_repair_torn_write=True)
    assert len(events) == 1
    assert head_hash == h1

    # Verify quarantine file exists
    quarantine_file = tmp_path / "segment_ep1_000001.quarantine"
    assert quarantine_file.exists()
    assert "truncated" in quarantine_file.read_text()


def test_segment_rotation_on_max_records(tmp_path: Path) -> None:
    writer = SegmentWriter(base_dir=tmp_path, epoch="ep1", max_records_per_segment=3)
    for i in range(7):
        writer.append_event(_make_dummy_event(i))
    writer.close()

    # 7 records with max 3 per segment -> segment 1 (3), segment 2 (3), segment 3 (1)
    assert (tmp_path / "segment_ep1_000001.jsonl").exists()
    assert (tmp_path / "segment_ep1_000002.jsonl").exists()
    assert (tmp_path / "segment_ep1_000003.jsonl").exists()

    events1, head1 = SegmentReader.read_segment(tmp_path / "segment_ep1_000001.jsonl")
    assert len(events1) == 3

    events2, head2 = SegmentReader.read_segment(
        tmp_path / "segment_ep1_000002.jsonl",
        expected_prev_hash=head1,
    )
    assert len(events2) == 3

    events3, head3 = SegmentReader.read_segment(
        tmp_path / "segment_ep1_000003.jsonl",
        expected_prev_hash=head2,
    )
    assert len(events3) == 1
    assert head3 == writer.head_hash
