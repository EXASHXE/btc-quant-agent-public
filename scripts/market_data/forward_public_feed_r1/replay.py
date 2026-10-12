"""Deterministic replay engine and audit witness verifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import MarketEventV1
from .durability import GENESIS_HASH, DurabilityError, SegmentReader
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
    """Verifies segment log immutability and continuous order book reconstruction."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)

    def replay_all(self, auto_repair_torn_write: bool = False) -> tuple[list[MarketEventV1], ReplayWitness]:
        """Read all segment files in sorted order, verify hash chain and book integrity."""
        segment_files = sorted(self.data_dir.glob("segment_*.jsonl"))
        if not segment_files:
            raise DurabilityError(f"No segment files found in {self.data_dir}")

        all_events: list[MarketEventV1] = []
        current_prev_hash = GENESIS_HASH

        channel_counts: dict[str, int] = {}
        quality_counts: dict[str, int] = {}
        reason_counts: dict[str, int] = {}

        book_engine = OrderBookIntegrityEngine()
        depth_continuous = True

        for seg_file in segment_files:
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
