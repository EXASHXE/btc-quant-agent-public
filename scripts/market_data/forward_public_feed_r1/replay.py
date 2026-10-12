"""Deterministic replay engine and audit witness verifier."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .connector import BinancePublicFeedClient
from .contracts import MarketEventV1
from .durability import (
    GENESIS_HASH,
    DurabilityError,
    RawSegmentReader,
    SegmentReader,
)
from .order_book import OrderBookIntegrityEngine


@dataclass(frozen=True)
class ReplayWitness:
    """Cryptographic audit witness generated after replay verification."""

    events_replayed: int
    first_wall_utc_ms: int | None
    last_wall_utc_ms: int | None
    head_hash: str
    depth_continuous: bool
    channel_counts: dict[str, int] = field(default_factory=dict)
    quality_counts: dict[str, int] = field(default_factory=dict)
    reason_code_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events_replayed": self.events_replayed,
            "first_wall_utc_ms": self.first_wall_utc_ms,
            "last_wall_utc_ms": self.last_wall_utc_ms,
            "head_hash": self.head_hash,
            "depth_continuous": self.depth_continuous,
            "channel_counts": dict(self.channel_counts),
            "quality_counts": dict(self.quality_counts),
            "reason_code_counts": dict(self.reason_code_counts),
        }


class ReplayEngine:
    """Verifies segment log immutability, raw logs, and continuous order book reconstruction."""

    def __init__(self, data_dir: str | Path, epoch: str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.epoch = epoch

    def replay_raw(self, auto_repair_torn_write: bool = False) -> tuple[list[MarketEventV1], ReplayWitness]:
        """Read saved immutable public raw segments with original observed arrival times, verify hashes and continuous depth."""
        if self.epoch:
            raw_files = sorted(self.data_dir.glob(f"raw_segment_{self.epoch}_*.jsonl"))
        else:
            raw_files = sorted(self.data_dir.glob("raw_segment_*.jsonl"))

        if not raw_files:
            raise DurabilityError(f"No raw segment files found in {self.data_dir}")

        all_events: list[MarketEventV1] = []
        current_prev_hash = GENESIS_HASH

        channel_counts: dict[str, int] = {}
        quality_counts: dict[str, int] = {}
        reason_counts: dict[str, int] = {}

        client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
        depth_continuous = True

        for raw_file in raw_files:
            # Verify raw manifest if present
            man_name = raw_file.name.replace("raw_segment_", "raw_manifest_").replace(".jsonl", ".json")
            man_path = raw_file.parent / man_name
            if man_path.exists():
                SegmentReader.read_manifest(man_path)

            with open(raw_file, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            first_entry_prev = None
            if first_line:
                try:
                    first_entry_prev = json.loads(first_line).get("prev_hash")
                except (json.JSONDecodeError, KeyError):
                    pass

            if first_entry_prev == GENESIS_HASH and current_prev_hash != GENESIS_HASH:
                current_prev_hash = GENESIS_HASH
                client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")

            entries, current_prev_hash = RawSegmentReader.read_raw_segment(
                raw_file,
                expected_prev_hash=current_prev_hash,
                auto_repair_torn_write=auto_repair_torn_write,
            )

            for entry in entries:
                raw_payload = entry["raw_payload"]
                wall_ms = entry["received_wall_utc_ms"]
                mono_ns = entry["received_monotonic_ns"]
                entry_hash = entry["entry_hash"]

                event = client.map_raw_frame_to_event(
                    raw_payload,
                    observed_wall_ms=wall_ms,
                    observed_monotonic_ns=mono_ns,
                    raw_manifest_sha256=entry_hash,
                )
                if event is not None:
                    all_events.append(event)
                    channel_counts[event.channel] = channel_counts.get(event.channel, 0) + 1
                    quality_counts[event.quality] = quality_counts.get(event.quality, 0) + 1
                    for r in event.reason_codes:
                        reason_counts[r] = reason_counts.get(r, 0) + 1

                    if event.book is not None and (not event.book.continuous or event.book.quality != "VERIFIED"):
                        depth_continuous = False

        first_wall = all_events[0].observed_wall_utc_ms if all_events else None
        last_wall = all_events[-1].observed_wall_utc_ms if all_events else None

        witness = ReplayWitness(
            events_replayed=len(all_events),
            first_wall_utc_ms=first_wall,
            last_wall_utc_ms=last_wall,
            head_hash=current_prev_hash,
            depth_continuous=depth_continuous,
            channel_counts=channel_counts,
            quality_counts=quality_counts,
            reason_code_counts=reason_counts,
        )

        return all_events, witness

    def replay_all(
        self,
        auto_repair_torn_write: bool = False,
        source: str = "auto",
    ) -> tuple[list[MarketEventV1], ReplayWitness]:
        """Read segment files in sorted order, verify hash chain, manifests, and book integrity."""
        if source == "raw":
            return self.replay_raw(auto_repair_torn_write=auto_repair_torn_write)

        if self.epoch:
            segment_files = sorted(self.data_dir.glob(f"segment_{self.epoch}_*.jsonl"))
        else:
            segment_files = sorted(self.data_dir.glob("segment_*.jsonl"))

        if not segment_files:
            if source == "auto":
                raw_files = (
                    sorted(self.data_dir.glob(f"raw_segment_{self.epoch}_*.jsonl"))
                    if self.epoch
                    else sorted(self.data_dir.glob("raw_segment_*.jsonl"))
                )
                if raw_files:
                    return self.replay_raw(auto_repair_torn_write=auto_repair_torn_write)
            raise DurabilityError(f"No segment files found in {self.data_dir}")

        all_events: list[MarketEventV1] = []
        current_prev_hash = GENESIS_HASH

        channel_counts: dict[str, int] = {}
        quality_counts: dict[str, int] = {}
        reason_counts: dict[str, int] = {}

        book_engine = OrderBookIntegrityEngine()
        depth_continuous = True

        for seg_file in segment_files:
            # Verify manifest checksum
            man_name = seg_file.name.replace("segment_", "manifest_").replace(".jsonl", ".json")
            man_path = seg_file.parent / man_name
            if man_path.exists():
                SegmentReader.read_manifest(man_path)

            # Check if this segment begins with GENESIS_HASH (independent session/run)
            # or continues an existing chain across consecutive epochs
            with open(seg_file, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
            first_entry_prev = None
            if first_line:
                try:
                    first_entry_prev = json.loads(first_line).get("prev_hash")
                except (json.JSONDecodeError, KeyError):
                    pass

            if first_entry_prev == GENESIS_HASH and current_prev_hash != GENESIS_HASH:
                current_prev_hash = GENESIS_HASH
                book_engine = OrderBookIntegrityEngine()

            events, current_prev_hash = SegmentReader.read_segment(
                seg_file,
                expected_prev_hash=current_prev_hash,
                auto_repair_torn_write=auto_repair_torn_write,
            )
            for event in events:
                all_events.append(event)
                channel_counts[event.channel] = channel_counts.get(event.channel, 0) + 1
                quality_counts[event.quality] = quality_counts.get(event.quality, 0) + 1
                for r in event.reason_codes:
                    reason_counts[r] = reason_counts.get(r, 0) + 1

                # Reconstruct book if snapshot or delta
                if event.channel == "depth_snapshot":
                    receipt = book_engine.apply_snapshot(event.payload, event.observed_wall_utc_ms)
                    if not receipt.continuous or receipt.quality != "VERIFIED":
                        depth_continuous = False
                elif event.channel == "depth_delta":
                    receipt = book_engine.apply_delta(event.payload, event.observed_wall_utc_ms)
                    if not receipt.continuous or receipt.quality != "VERIFIED":
                        depth_continuous = False

        first_wall = all_events[0].observed_wall_utc_ms if all_events else None
        last_wall = all_events[-1].observed_wall_utc_ms if all_events else None

        witness = ReplayWitness(
            events_replayed=len(all_events),
            first_wall_utc_ms=first_wall,
            last_wall_utc_ms=last_wall,
            head_hash=current_prev_hash,
            depth_continuous=depth_continuous,
            channel_counts=channel_counts,
            quality_counts=quality_counts,
            reason_code_counts=reason_counts,
        )

        return all_events, witness
