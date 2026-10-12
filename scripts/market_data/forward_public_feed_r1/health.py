"""Health supervisor, channel staleness evaluation, and source readiness gating."""

from __future__ import annotations

from typing import Any

from .contracts import (
    ALLOWED_PRODUCT,
    ALLOWED_SYMBOL,
    CHANNELS,
    MarketEventV1,
    compute_sha256,
)
from .time_authority import TimeAuthority

# Channel staleness tolerances (milliseconds)
STALENESS_THRESHOLDS_MS: dict[str, int] = {
    "last_kline_1m": 120_000,   # 2 minutes
    "mark_price": 10_000,       # 10 seconds
    "agg_trade": 30_000,        # 30 seconds
    "depth_delta": 5_000,       # 5 seconds
    "depth_snapshot": 300_000,  # 5 minutes
    "funding_settled": 28_800_000 + 3_600_000,  # 8 hours + 1 hour grace
}


class HealthSupervisor:
    """Supervises feed health across all channels and computes the source readiness gate."""

    def __init__(
        self,
        symbol: str = ALLOWED_SYMBOL,
        product: str = ALLOWED_PRODUCT,
        time_authority: TimeAuthority | None = None,
    ) -> None:
        self.symbol = symbol
        self.product = product
        self.time_authority = time_authority or TimeAuthority()

        # Channel tracking: channel_name -> last_observed_wall_ms
        self.channel_last_wall_ms: dict[str, int] = {}
        self.channel_event_counts: dict[str, int] = {ch: 0 for ch in CHANNELS}

        # Last settled funding details
        self.last_settled_funding_rate: str | None = None
        self.last_settled_funding_time_ms: int | None = None

        # Estimated funding from mark price (must remain distinct from settled funding!)
        self.latest_estimated_funding_rate: str | None = None
        self.latest_estimated_funding_time_ms: int | None = None

        # Book status
        self.book_quality: str = "UNKNOWN"
        self.book_continuous: bool = False
        self.book_gap_count: int = 0

    def record_channel_event(
        self,
        channel: str,
        wall_ms: int,
        payload: dict[str, Any],
        quality: str,
    ) -> None:
        """Update supervisor state when an event arrives."""
        self.channel_last_wall_ms[channel] = wall_ms
        self.channel_event_counts[channel] = self.channel_event_counts.get(channel, 0) + 1

        if channel == "funding_settled":
            self.last_settled_funding_rate = str(payload.get("fundingRate", ""))
            self.last_settled_funding_time_ms = payload.get("fundingTime")
        elif channel == "mark_price":
            # Estimated funding from mark price is tagged ESTIMATED_NOT_SETTLED
            self.latest_estimated_funding_rate = str(payload.get("r", ""))
            self.latest_estimated_funding_time_ms = payload.get("T")

    def record_book_status(self, quality: str, continuous: bool, reason_codes: list[str]) -> None:
        """Update latest order book integrity state."""
        self.book_quality = quality
        self.book_continuous = continuous
        if "GAP_DETECTED" in reason_codes or "SNAPSHOT_CROSSED_BOOK" in reason_codes:
            self.book_gap_count += 1

    def evaluate_source_gate(self, current_wall_ms: int) -> tuple[str, list[str]]:
        """Evaluate source readiness: SOURCE_READY, SOURCE_DEGRADED, or SOURCE_UNAVAILABLE."""
        reasons: list[str] = []

        # 1. Check book continuity
        if self.book_quality == "UNKNOWN":
            return "SOURCE_UNAVAILABLE", ["BOOK_AWAITING_SNAPSHOT"]
        if self.book_quality == "INVALID" or not self.book_continuous:
            return "SOURCE_UNAVAILABLE", ["BOOK_DISCONTINUOUS_OR_INVALID"]

        # 2. Check essential high-frequency channels: mark_price and depth_delta
        for ch in ("mark_price", "depth_delta"):
            last_ms = self.channel_last_wall_ms.get(ch)
            if last_ms is None:
                reasons.append(f"MISSING_{ch.upper()}")
            else:
                staleness = current_wall_ms - last_ms
                if staleness > STALENESS_THRESHOLDS_MS[ch]:
                    reasons.append(f"STALE_{ch.upper()}_{staleness}MS")

        # 3. Check clock uncertainty
        clock_diag = self.time_authority.get_diagnostics()
        if clock_diag["clock_status"] == "CLOCK_UNCERTAIN":
            reasons.append("CLOCK_UNCERTAIN")

        # 4. Check book degraded
        if self.book_quality == "DEGRADED":
            reasons.append("BOOK_DEGRADED")

        if any(r.startswith("MISSING_") for r in reasons):
            return "SOURCE_UNAVAILABLE", reasons

        if reasons:
            return "SOURCE_DEGRADED", reasons

        return "SOURCE_READY", ["OK"]

    def create_health_event(
        self,
        current_wall_ms: int,
        raw_manifest_sha256: str,
    ) -> MarketEventV1:
        """Generate a canonical MarketEventV1 on the health channel."""
        gate_status, reasons = self.evaluate_source_gate(current_wall_ms)
        quality = (
            "VERIFIED"
            if gate_status == "SOURCE_READY"
            else ("DEGRADED" if gate_status == "SOURCE_DEGRADED" else "INVALID")
        )

        ingress = self.time_authority.capture_ingress(override_wall_ms=current_wall_ms)
        clock_diag = self.time_authority.get_diagnostics()

        payload: dict[str, Any] = {
            "source_gate": gate_status,
            "book_quality": self.book_quality,
            "book_continuous": self.book_continuous,
            "book_gap_count": self.book_gap_count,
            "channel_counts": dict(self.channel_event_counts),
            "clock_diagnostics": clock_diag,
            "settled_funding": {
                "rate": self.last_settled_funding_rate,
                "time_ms": self.last_settled_funding_time_ms,
            },
            "estimated_funding": {
                "rate": self.latest_estimated_funding_rate,
                "time_ms": self.latest_estimated_funding_time_ms,
                "status": "ESTIMATED_NOT_SETTLED",
            },
        }

        payload_sha = compute_sha256(payload)

        return MarketEventV1(
            schema_version="market-event-v1",
            symbol=self.symbol,
            product=self.product,
            channel="health",
            provider_event_ms=current_wall_ms,
            provider_transaction_ms=None,
            observed_wall_utc_ms=ingress.observed_wall_utc_ms,
            observed_monotonic_ns=ingress.observed_monotonic_ns,
            available_at_ms=ingress.available_at_ms,
            source_stream_id="local_health_supervisor",
            connection_epoch=self.time_authority.connection_epoch,
            source_sequence=self.channel_event_counts.get("health", 0),
            payload_sha256=payload_sha,
            payload=payload,
            quality=quality,
            reason_codes=reasons,
            raw_source_manifest_sha256=raw_manifest_sha256,
            book=None,
        )
