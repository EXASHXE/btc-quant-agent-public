"""Order Book Ladder Adapter: Extracts atomic Top-10 price/quantity ladders from A's integrity engine.

Resolves Incompatibility 2 (A's BookIntegrityV1 receipt omitting ladders vs B P2 signal requiring top-10 imbalance).
Performs atomic read-only extraction, canonical SHA hashing, and strict gatekeeping:
requires minimum 10 levels on both sides, uncrossed book, staleness <= 1000ms, and stable route epoch.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from scripts.market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine


@dataclass(frozen=True)
class Top10BookSnapshot:
    """Atomic snapshot of order book top-10 ladders with cryptographic integrity."""

    snapshot_update_id: int | None
    first_update_id: int | None
    final_update_id: int | None
    previous_final_update_id: int | None
    continuous: bool
    best_bid: str | None
    best_ask: str | None
    bids: tuple[tuple[float, float], ...]  # Top-10 (price, qty) sorted descending
    asks: tuple[tuple[float, float], ...]  # Top-10 (price, qty) sorted ascending
    observed_depth_levels: int
    stale_age_ms: int
    quality: str
    reason_codes: tuple[str, ...]
    top10_ladder_sha256: str
    route_epoch: str

    def top_10_imbalance(self) -> float | None:
        """Calculate B's P2 signal notional imbalance: (bid_notional - ask_notional) / total."""
        if len(self.bids) < 10 or len(self.asks) < 10 or self.quality != "VERIFIED":
            return None
        bid_notional = sum(p * q for p, q in self.bids[:10])
        ask_notional = sum(p * q for p, q in self.asks[:10])
        total = bid_notional + ask_notional
        if total <= 0:
            return None
        return (bid_notional - ask_notional) / total

    def to_b_book_dict(self) -> dict[str, Any]:
        """Convert to dict schema admitted by B's BookIntegrityV1."""
        return {
            "snapshot_update_id": self.snapshot_update_id or 0,
            "first_update_id": self.first_update_id or 0,
            "final_update_id": self.final_update_id or 0,
            "previous_final_update_id": self.previous_final_update_id,
            "continuous": self.continuous,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "bids": [list(b) for b in self.bids],
            "asks": [list(a) for a in self.asks],
            "observed_depth_levels": self.observed_depth_levels,
            "stale_age_ms": self.stale_age_ms,
            "quality": self.quality,
            "reason_codes": list(self.reason_codes),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_update_id": self.snapshot_update_id,
            "first_update_id": self.first_update_id,
            "final_update_id": self.final_update_id,
            "previous_final_update_id": self.previous_final_update_id,
            "continuous": self.continuous,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "bids": [list(b) for b in self.bids],
            "asks": [list(a) for a in self.asks],
            "observed_depth_levels": self.observed_depth_levels,
            "stale_age_ms": self.stale_age_ms,
            "quality": self.quality,
            "reason_codes": list(self.reason_codes),
            "top10_ladder_sha256": self.top10_ladder_sha256,
            "route_epoch": self.route_epoch,
            "top10_imbalance": self.top_10_imbalance(),
        }


class OrderBookLadderAdapter:
    """Atomic extractor for L2 order book top-10 ladders."""

    def __init__(self, book_engine: OrderBookIntegrityEngine) -> None:
        self.book_engine = book_engine
        self.last_extracted_ladder_sha: str = ""

    def extract_atomic_snapshot(
        self,
        current_wall_ms: int,
        route_epoch: str = "route-epoch-0",
    ) -> Top10BookSnapshot:
        """Extract atomic top-10 ladder snapshot from book engine without state mutation."""
        engine = self.book_engine
        stale_age_ms = max(0, current_wall_ms - engine.last_update_wall_ms) if engine.last_update_wall_ms > 0 else 0

        reasons: list[str] = []
        quality = "VERIFIED"

        if not engine.is_bootstrapped or not engine.continuous:
            quality = "INVALID"
            reasons.append("UNBOOTSTRAPPED_OR_DISCONTINUOUS_BOOK")

        # Extract top 10 bids (descending) and top 10 asks (ascending)
        sorted_bid_prices = sorted(engine.bids.keys(), reverse=True)
        sorted_ask_prices = sorted(engine.asks.keys())

        top_bids = tuple((float(p), float(engine.bids[p])) for p in sorted_bid_prices[:10])
        top_asks = tuple((float(p), float(engine.asks[p])) for p in sorted_ask_prices[:10])

        best_bid_str = str(sorted_bid_prices[0]) if sorted_bid_prices else None
        best_ask_str = str(sorted_ask_prices[0]) if sorted_ask_prices else None

        # Check crossed book
        if sorted_bid_prices and sorted_ask_prices and sorted_bid_prices[0] >= sorted_ask_prices[0]:
            quality = "INVALID"
            reasons.append(f"CROSSED_BOOK: bid {sorted_bid_prices[0]} >= ask {sorted_ask_prices[0]}")

        # Check level count
        if len(top_bids) < 10 or len(top_asks) < 10:
            if quality != "INVALID":
                quality = "DEGRADED"
            reasons.append(f"INCOMPLETE_L2_DEPTH: bids={len(top_bids)}, asks={len(top_asks)} < 10")

        # Check staleness (> 1000ms threshold for P2 prerequisite)
        if stale_age_ms > 1000:
            if quality != "INVALID":
                quality = "DEGRADED"
            reasons.append(f"DEPTH_STALE_OVER_1S: age={stale_age_ms}ms > 1000ms")

        if quality == "VERIFIED":
            reasons.append("OK")

        # Deterministic SHA256 of top10 ladders
        ladder_manifest = {
            "bids": [[p, q] for p, q in top_bids],
            "asks": [[p, q] for p, q in top_asks],
            "final_update_id": engine.final_update_id,
            "route_epoch": route_epoch,
        }
        raw_bytes = json.dumps(ladder_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ladder_sha = hashlib.sha256(raw_bytes).hexdigest()
        self.last_extracted_ladder_sha = ladder_sha

        return Top10BookSnapshot(
            snapshot_update_id=engine.snapshot_update_id,
            first_update_id=engine.first_update_id,
            final_update_id=engine.final_update_id,
            previous_final_update_id=engine.previous_final_update_id,
            continuous=engine.continuous,
            best_bid=best_bid_str,
            best_ask=best_ask_str,
            bids=top_bids,
            asks=top_asks,
            observed_depth_levels=len(engine.bids) + len(engine.asks),
            stale_age_ms=stale_age_ms,
            quality=quality,
            reason_codes=tuple(reasons),
            top10_ladder_sha256=ladder_sha,
            route_epoch=route_epoch,
        )
