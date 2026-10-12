"""Integration adapter contract for consuming prospective PublicFeed MarketEventV1 streams.

Under B-line Controller Authority:
TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .contract import (
    BarData,
    Channel,
    MarketEventV1,
    Quality,
    parse_agg_trade_payload,
    parse_funding_payload,
    parse_kline_payload,
)
from .execution import ShadowExecutionEngine


@dataclass
class AdapterStats:
    total_events_received: int = 0
    duplicate_events_count: int = 0
    clock_uncertain_events_count: int = 0
    verified_events_count: int = 0
    degraded_events_count: int = 0
    invalid_events_count: int = 0
    channel_counts: dict[str, int] = field(default_factory=dict)


class PublicFeedAdapter:
    """Decoupled consumer of canonical MarketEventV1 wire protocol.

    Maintains deduplication, monotonic arrival verification, and feeds
    the ShadowExecutionEngine strictly without cross-worktree imports.
    """

    def __init__(self, execution_engine: ShadowExecutionEngine):
        self.engine = execution_engine
        self.stats = AdapterStats()
        self.seen_dedupe_keys: set[str] = set()

        self.last_monotonic_ns: int = -1
        self.last_wall_utc_ms: int = -1

        # Pending time-aligned bar pairing
        self.pending_last_1m: BarData | None = None
        self.pending_mark_1m: BarData | None = None

    def ingest_line(self, line: str) -> MarketEventV1 | None:
        """Ingest single raw line of MarketEventV1 JSON."""
        stripped = line.strip()
        if not stripped:
            return None
        data = json.loads(stripped)
        return self.ingest_dict(data)

    def ingest_dict(self, data: dict[str, Any]) -> MarketEventV1 | None:
        """Ingest dictionary and route to execution engine."""
        self.stats.total_events_received += 1
        event = MarketEventV1.from_dict(data)

        # Deduplication check
        d_key = event.dedupe_key()
        if d_key in self.seen_dedupe_keys:
            self.stats.duplicate_events_count += 1
            return None
        self.seen_dedupe_keys.add(d_key)

        # Receiver clock causality check
        if (
            self.last_monotonic_ns >= 0
            and event.observed_monotonic_ns > self.last_monotonic_ns
            and event.observed_wall_utc_ms < self.last_wall_utc_ms
        ):
            self.stats.clock_uncertain_events_count += 1
            # Wall time jumped backwards relative to monotonic order
            reasons = list(event.reason_codes) + ["RECEIVER_CLOCK_JUMP_BACKWARD"]
            event = MarketEventV1(
                channel=event.channel,
                provider_event_ms=event.provider_event_ms,
                provider_transaction_ms=event.provider_transaction_ms,
                observed_wall_utc_ms=event.observed_wall_utc_ms,
                observed_monotonic_ns=event.observed_monotonic_ns,
                available_at_ms=event.available_at_ms,
                source_stream_id=event.source_stream_id,
                connection_epoch=event.connection_epoch,
                source_sequence=event.source_sequence,
                payload_sha256=event.payload_sha256,
                payload=event.payload,
                quality=Quality.INVALID,
                reason_codes=tuple(reasons),
                raw_source_manifest_sha256=event.raw_source_manifest_sha256,
                book=event.book,
            )

        self.last_monotonic_ns = event.observed_monotonic_ns
        self.last_wall_utc_ms = event.observed_wall_utc_ms

        # Record quality
        if event.quality == Quality.VERIFIED:
            self.stats.verified_events_count += 1
        elif event.quality == Quality.DEGRADED:
            self.stats.degraded_events_count += 1
        else:
            self.stats.invalid_events_count += 1

        ch_name = event.channel.value
        self.stats.channel_counts[ch_name] = self.stats.channel_counts.get(ch_name, 0) + 1

        # Dispatch by channel
        if event.quality != Quality.INVALID:
            self._dispatch_event(event)

        return event

    def _dispatch_event(self, event: MarketEventV1) -> None:
        """Route valid event to the shadow execution engine."""
        # Update book if present
        if event.book is not None and event.book.quality == Quality.VERIFIED:
            self.engine.on_book_update(event.book)

        if event.channel == Channel.AGG_TRADE:
            trade_data = parse_agg_trade_payload(event.payload)
            self.engine.on_agg_trade(trade_data)

        elif event.channel == Channel.FUNDING_SETTLED:
            funding_data = parse_funding_payload(event.payload)
            if funding_data.settled:
                self.engine.on_funding_settled(funding_data, event.available_at_ms)

        elif event.channel == Channel.LAST_KLINE_1M:
            bar_data = parse_kline_payload(
                event.payload,
                quality=event.quality,
                available_at_ms=event.available_at_ms,
            )
            if bar_data.closed:
                self.pending_last_1m = bar_data
                self._check_and_flush_paired_minute(event.available_at_ms)

        elif event.channel == Channel.MARK_PRICE:
            bar_data = parse_kline_payload(
                event.payload,
                quality=event.quality,
                available_at_ms=event.available_at_ms,
            )
            if bar_data.closed:
                self.pending_mark_1m = bar_data
                self._check_and_flush_paired_minute(event.available_at_ms)

    def _check_and_flush_paired_minute(self, current_available_ms: int) -> None:
        """Pair strictly time-aligned Last and Mark 1m closes before advancing engine."""
        if self.pending_last_1m is not None and self.pending_mark_1m is not None:
            # Check timestamp match
            if (
                self.pending_last_1m.bar_open_ms == self.pending_mark_1m.bar_open_ms
                and self.pending_last_1m.bar_close_ms == self.pending_mark_1m.bar_close_ms
            ):
                max_avail = max(
                    self.pending_last_1m.available_at_ms,
                    self.pending_mark_1m.available_at_ms,
                    current_available_ms,
                )
                self.engine.on_minute_bars(
                    last_bar_1m=self.pending_last_1m,
                    mark_bar_1m=self.pending_mark_1m,
                    current_available_at_ms=max_avail,
                )
                self.pending_last_1m = None
                self.pending_mark_1m = None
            elif self.pending_last_1m.bar_close_ms < self.pending_mark_1m.bar_close_ms:
                # Last is behind mark; wait for matching mark or drop desynced
                self.pending_last_1m = None
            else:
                self.pending_mark_1m = None

    def replay_stream(self, lines: Iterator[str]) -> None:
        """Stream replay convenience method."""
        for line in lines:
            self.ingest_line(line)
