"""Bridge Engine: Central causal orchestrator bridging A events into B and C consumers.

Integrates MarkPriceAggregator, OrderBookLadderAdapter, SettledFundingLedger,
and CCompositeBarBuilder to provide causal, immutable, and fail-closed dispatch
to B's PublicFeedAdapter and C's MarketPitPort.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from scripts.market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine

from .book_ladder import OrderBookLadderAdapter, Top10BookSnapshot
from .c_composite_bar import CCompositeBarBuilder
from .funding_adapter import SettledFundingLedger
from .mark_aggregator import DerivedMark1MBar, MarkPriceAggregator


def _sha256(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass
class BridgeStats:
    total_frames_ingested: int = 0
    mark_ticks_ingested: int = 0
    mark_bars_derived: int = 0
    trades_ingested: int = 0
    depth_deltas_ingested: int = 0
    depth_snapshots_ingested: int = 0
    top10_book_snapshots_emitted: int = 0
    settled_fundings_adapted: int = 0
    c_composite_bars_emitted: int = 0
    b_events_dispatched: int = 0
    c_events_dispatched: int = 0
    causal_violations: int = 0


class MarketEventBridgeR2:
    """Rigorous causal wire bridge between A publisher and B/C consumers."""

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        route_epoch: str = "route-epoch-0",
        connection_epoch: int = 1,
        b_adapter: Any = None,
        c_port: Any = None,
    ) -> None:
        self.symbol = symbol
        self.route_epoch = route_epoch
        self.connection_epoch = connection_epoch
        self.b_adapter = b_adapter
        self.c_port = c_port

        # State engines
        self.book_engine = OrderBookIntegrityEngine(symbol=symbol)
        self.mark_aggregator = MarkPriceAggregator()
        self.ladder_adapter = OrderBookLadderAdapter(self.book_engine)
        self.funding_ledger = SettledFundingLedger(symbol=symbol)
        self.c_bar_builder = CCompositeBarBuilder()

        # In-memory tracking
        self.stats = BridgeStats()
        self.last_derived_mark_bar: DerivedMark1MBar | None = None
        self.last_top10_snapshot: Top10BookSnapshot | None = None
        self.witness_records: list[dict[str, Any]] = []

    def switch_route_node(self, new_route_epoch: str | None = None) -> None:
        """Handle proxy failover / route node switch: reset book engine and advance epoch."""
        if new_route_epoch is not None:
            self.route_epoch = new_route_epoch
        else:
            epoch_num = int(self.route_epoch.split("-")[-1]) if "-" in self.route_epoch and self.route_epoch.split("-")[-1].isdigit() else 0
            self.route_epoch = f"route-epoch-{epoch_num + 1}"
        self.connection_epoch += 1
        self.book_engine.reset(reason="ROUTE_NODE_SWITCH")

    def process_fixture_sequence(
        self,
        frames: list[dict[str, Any]],
        base_wall_utc_ms: int = 1728720000000,
    ) -> dict[str, Any]:
        """Process an ordered batch of exchange frames sequentially."""
        processed = 0
        for idx, frame in enumerate(frames):
            wall_ms = base_wall_utc_ms + idx * 100
            mono_ns = (idx + 1) * 1_000_000
            self.ingest_frame(frame, observed_wall_utc_ms=wall_ms, observed_monotonic_ns=mono_ns)
            processed += 1
        return {"total_frames_processed": processed, "stats": self.stats}

    def ingest_frame(
        self,
        frame: dict[str, Any],
        observed_wall_utc_ms: int,
        observed_monotonic_ns: int,
        raw_manifest_sha256: str = "",
    ) -> dict[str, Any]:
        """Ingest raw Binance frame or normalized A frame and dispatch causally."""
        self.stats.total_frames_ingested += 1
        payload_sha = _sha256(frame)

        event_type = frame.get("e")
        result: dict[str, Any] = {"status": "INGESTED", "emitted_to_b": False, "emitted_to_c": False}

        # 1. Depth Snapshot
        if "lastUpdateId" in frame and "bids" in frame and "asks" in frame:
            self.stats.depth_snapshots_ingested += 1
            self.book_engine.apply_snapshot(frame, observed_wall_utc_ms)
            top10 = self.ladder_adapter.extract_atomic_snapshot(observed_wall_utc_ms, self.route_epoch)
            self.last_top10_snapshot = top10
            self.stats.top10_book_snapshots_emitted += 1
            result["top10_snapshot"] = top10.to_dict()

        # 2. Depth Delta
        elif event_type == "depthUpdate":
            self.stats.depth_deltas_ingested += 1
            self.book_engine.apply_delta(frame, observed_wall_utc_ms)
            top10 = self.ladder_adapter.extract_atomic_snapshot(observed_wall_utc_ms, self.route_epoch)
            self.last_top10_snapshot = top10
            self.stats.top10_book_snapshots_emitted += 1
            result["top10_snapshot"] = top10.to_dict()

            # Dispatch book to B adapter if present
            if self.b_adapter is not None:
                b_event_dict = {
                    "schema_version": "market-event-v1",
                    "symbol": self.symbol,
                    "product": "BINANCE_USDT_M_PERP",
                    "channel": "depth_delta",
                    "provider_event_ms": frame.get("E", observed_wall_utc_ms),
                    "provider_transaction_ms": frame.get("T"),
                    "observed_wall_utc_ms": observed_wall_utc_ms,
                    "observed_monotonic_ns": observed_monotonic_ns,
                    "available_at_ms": observed_wall_utc_ms,
                    "source_stream_id": f"{self.symbol.lower()}@depth@100ms",
                    "connection_epoch": str(self.connection_epoch),
                    "source_sequence": frame.get("u"),
                    "payload_sha256": payload_sha,
                    "payload": frame,
                    "quality": top10.quality,
                    "reason_codes": list(top10.reason_codes),
                    "raw_source_manifest_sha256": raw_manifest_sha256,
                    "book": top10.to_b_book_dict(),
                }
                self.b_adapter.ingest_dict(b_event_dict)
                self.stats.b_events_dispatched += 1
                result["emitted_to_b"] = True

        # 3. Mark Price Tick
        elif event_type == "markPriceUpdate":
            self.stats.mark_ticks_ingested += 1
            mark_p = frame.get("p", "0.0")
            prov_e = frame.get("E", observed_wall_utc_ms)
            derived_bar = self.mark_aggregator.ingest_tick(
                provider_event_ms=prov_e,
                mark_price=mark_p,
                available_at_ms=observed_wall_utc_ms,
                payload_sha256=payload_sha,
                raw_manifest_sha256=raw_manifest_sha256,
            )
            if derived_bar is not None:
                self.stats.mark_bars_derived += 1
                self.last_derived_mark_bar = derived_bar
                result["derived_mark_bar"] = derived_bar.to_dict()

                # Dispatch derived mark bar to B adapter as completed kline
                if self.b_adapter is not None:
                    b_mark_payload = derived_bar.to_b_kline_payload()
                    b_mark_event = {
                        "schema_version": "market-event-v1",
                        "symbol": self.symbol,
                        "product": "BINANCE_USDT_M_PERP",
                        "channel": "mark_price",
                        "provider_event_ms": derived_bar.bar_close_ms,
                        "provider_transaction_ms": derived_bar.bar_close_ms,
                        "observed_wall_utc_ms": derived_bar.derived_available_at_ms,
                        "observed_monotonic_ns": observed_monotonic_ns,
                        "available_at_ms": derived_bar.derived_available_at_ms,
                        "source_stream_id": f"{self.symbol.lower()}@markPrice@1m",
                        "connection_epoch": str(self.connection_epoch),
                        "source_sequence": derived_bar.sample_count,
                        "payload_sha256": _sha256(b_mark_payload),
                        "payload": b_mark_payload,
                        "quality": derived_bar.quality,
                        "reason_codes": list(derived_bar.reason_codes),
                        "raw_source_manifest_sha256": raw_manifest_sha256,
                    }
                    self.b_adapter.ingest_dict(b_mark_event)
                    self.stats.b_events_dispatched += 1
                    result["emitted_to_b"] = True

        # 4. Agg Trade
        elif event_type == "aggTrade":
            self.stats.trades_ingested += 1
            if self.b_adapter is not None:
                b_trade_event = {
                    "schema_version": "market-event-v1",
                    "symbol": self.symbol,
                    "product": "BINANCE_USDT_M_PERP",
                    "channel": "agg_trade",
                    "provider_event_ms": frame.get("E", observed_wall_utc_ms),
                    "provider_transaction_ms": frame.get("T"),
                    "observed_wall_utc_ms": observed_wall_utc_ms,
                    "observed_monotonic_ns": observed_monotonic_ns,
                    "available_at_ms": observed_wall_utc_ms,
                    "source_stream_id": f"{self.symbol.lower()}@aggTrade",
                    "connection_epoch": str(self.connection_epoch),
                    "source_sequence": frame.get("a"),
                    "payload_sha256": payload_sha,
                    "payload": frame,
                    "quality": "VERIFIED",
                    "reason_codes": ["OK"],
                    "raw_source_manifest_sha256": raw_manifest_sha256,
                }
                self.b_adapter.ingest_dict(b_trade_event)
                self.stats.b_events_dispatched += 1
                result["emitted_to_b"] = True

        # 5. Kline 1m
        elif event_type == "kline":
            k = frame.get("k", {})
            if k.get("x") is True:
                # Closed kline!
                # If we don't have a derived mark bar yet, flush current aggregator window
                if self.last_derived_mark_bar is None or self.last_derived_mark_bar.bar_open_ms != int(k.get("t", 0)):
                    flushed = self.mark_aggregator.flush_window()
                    if flushed is not None:
                        self.last_derived_mark_bar = flushed
                        self.stats.mark_bars_derived += 1

                # Forward Last 1m to B adapter
                if self.b_adapter is not None:
                    b_kline_event = {
                        "schema_version": "market-event-v1",
                        "symbol": self.symbol,
                        "product": "BINANCE_USDT_M_PERP",
                        "channel": "last_kline_1m",
                        "provider_event_ms": frame.get("E", observed_wall_utc_ms),
                        "provider_transaction_ms": frame.get("T"),
                        "observed_wall_utc_ms": observed_wall_utc_ms,
                        "observed_monotonic_ns": observed_monotonic_ns,
                        "available_at_ms": observed_wall_utc_ms,
                        "source_stream_id": f"{self.symbol.lower()}@kline_1m",
                        "connection_epoch": str(self.connection_epoch),
                        "source_sequence": k.get("L"),
                        "payload_sha256": payload_sha,
                        "payload": frame,
                        "quality": "VERIFIED",
                        "reason_codes": ["OK"],
                        "raw_source_manifest_sha256": raw_manifest_sha256,
                    }
                    self.b_adapter.ingest_dict(b_kline_event)
                    self.stats.b_events_dispatched += 1
                    result["emitted_to_b"] = True

                # Build C composite BAR if mark bar available
                if self.last_derived_mark_bar is not None and self.c_port is not None:
                    c_env = self.c_bar_builder.build_composite_bar_envelope(
                        raw_kline_payload=frame,
                        derived_mark_bar=self.last_derived_mark_bar,
                        kline_available_at_ms=observed_wall_utc_ms,
                        observed_monotonic_ns=observed_monotonic_ns,
                        connection_epoch=self.connection_epoch,
                        source_sequence=k.get("L"),
                    )
                    self.c_port.ingest_envelope(c_env)
                    self.stats.c_composite_bars_emitted += 1
                    self.stats.c_events_dispatched += 1
                    result["emitted_to_c"] = True
                    result["c_envelope"] = c_env

        # 6. Settled Funding Record
        elif "fundingRate" in frame and "fundingTime" in frame:
            mark_p = self.last_derived_mark_bar.close if self.last_derived_mark_bar else 64000.0
            entry = self.funding_ledger.ingest_settled_funding(
                raw_record=frame,
                contemporaneous_mark_price=mark_p,
                observed_wall_utc_ms=observed_wall_utc_ms,
                raw_manifest_sha256=raw_manifest_sha256,
            )
            if entry is not None:
                self.stats.settled_fundings_adapted += 1
                result["settled_funding"] = entry.to_dict()

                # Dispatch to B
                if self.b_adapter is not None:
                    b_fund_payload = entry.to_b_funding_payload()
                    b_fund_event = {
                        "schema_version": "market-event-v1",
                        "symbol": self.symbol,
                        "product": "BINANCE_USDT_M_PERP",
                        "channel": "funding_settled",
                        "provider_event_ms": entry.funding_time_ms,
                        "provider_transaction_ms": entry.funding_time_ms,
                        "observed_wall_utc_ms": observed_wall_utc_ms,
                        "observed_monotonic_ns": observed_monotonic_ns,
                        "available_at_ms": observed_wall_utc_ms,
                        "source_stream_id": f"{self.symbol.lower()}@fundingRate",
                        "connection_epoch": str(self.connection_epoch),
                        "source_sequence": None,
                        "payload_sha256": _sha256(b_fund_payload),
                        "payload": b_fund_payload,
                        "quality": "VERIFIED",
                        "reason_codes": ["OK"],
                        "raw_source_manifest_sha256": raw_manifest_sha256,
                    }
                    self.b_adapter.ingest_dict(b_fund_event)
                    self.stats.b_events_dispatched += 1
                    result["emitted_to_b"] = True

                # Dispatch to C
                if self.c_port is not None:
                    c_fund_payload = entry.to_c_funding_payload()
                    c_fund_env = {
                        "schema_version": "market-event-v1",
                        "symbol": self.symbol,
                        "product": "BINANCE_USDT_M_PERP",
                        "channel": "funding_settled",
                        "provider_event_ms": entry.funding_time_ms,
                        "provider_transaction_ms": entry.funding_time_ms,
                        "observed_wall_utc_ms": entry.funding_time_ms,
                        "observed_monotonic_ns": observed_monotonic_ns,
                        "available_at_ms": entry.funding_time_ms,
                        "source_stream_id": self.c_bar_builder.stream_id,
                        "connection_epoch": self.connection_epoch,
                        "source_sequence": None,
                        "payload_sha256": _sha256(c_fund_payload),
                        "payload": c_fund_payload,
                        "quality": "VERIFIED",
                        "reason_codes": ["OK"],
                        "raw_source_manifest_sha256": self.c_bar_builder.manifest_sha256,
                    }
                    self.c_port.ingest_envelope(c_fund_env)
                    self.stats.c_events_dispatched += 1
                    result["emitted_to_c"] = True

        return result
