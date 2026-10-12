"""Point-in-Time (PIT) time authority, ingress timestamping, and latency diagnostics."""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .contracts import MarketEventV1

MAX_ALLOWED_CLOCK_DIVERGENCE_MS: int = 5_000
MAX_LATENCY_SAMPLES: int = 10_000


class PointInTimeViolationError(ValueError):
    """Raised when cross-channel join violates Point-In-Time causality or quality."""


@dataclass(frozen=True)
class IngressTimestamp:
    """Ingress timestamp captured at the network boundary pre-parse."""

    observed_wall_utc_ms: int
    observed_monotonic_ns: int
    available_at_ms: int
    quality: str  # VERIFIED or DEGRADED
    reason_codes: list[str] = field(default_factory=list)


class TimeAuthority:
    """Manages observation clocks, detects clock rollback, and computes PIT latencies."""

    def __init__(
        self,
        connection_epoch: str | None = None,
        max_clock_divergence_ms: int = MAX_ALLOWED_CLOCK_DIVERGENCE_MS,
    ) -> None:
        self.connection_epoch = (
            connection_epoch
            if connection_epoch is not None
            else f"epoch-{time.time_ns()}-pid{os.getpid()}"
        )
        self.max_clock_divergence_ms = max_clock_divergence_ms

        # Clock tracking
        self.last_observed_wall_ms: int | None = None
        self.last_observed_monotonic_ns: int | None = None
        self.clock_uncertain_count: int = 0
        self.monotonic_violation_count: int = 0
        self.dropped_ingress_count: int = 0

        # Latency samples (milliseconds)
        self._latency_samples: list[int] = []
        self._offset_samples: list[int] = []

    def capture_ingress(
        self,
        override_wall_ms: int | None = None,
        override_monotonic_ns: int | None = None,
    ) -> IngressTimestamp:
        """Capture wall and monotonic timestamps immediately upon packet arrival.

        Pre-parse capture guarantees that no unobserved moment receives known-at credit.
        """
        wall_ms = (
            override_wall_ms
            if override_wall_ms is not None
            else time.time_ns() // 1_000_000
        )
        mono_ns = (
            override_monotonic_ns
            if override_monotonic_ns is not None
            else time.monotonic_ns()
        )

        quality = "VERIFIED"
        reasons: list[str] = ["OK"]

        # Check for monotonic violations within the process
        if self.last_observed_monotonic_ns is not None and mono_ns < self.last_observed_monotonic_ns:
            quality = "DEGRADED"
            reasons.append("MONOTONIC_REGRESSION")
            self.monotonic_violation_count += 1

        # Check for system clock rollback (wall clock moved backward while monotonic advanced)
        if self.last_observed_wall_ms is not None and self.last_observed_monotonic_ns is not None:
            if mono_ns >= self.last_observed_monotonic_ns and wall_ms < self.last_observed_wall_ms:
                quality = "DEGRADED"
                reasons.append("CLOCK_UNCERTAIN")
                self.clock_uncertain_count += 1
            else:
                # Check for extreme divergence between wall clock step and monotonic step
                elapsed_wall_ms = wall_ms - self.last_observed_wall_ms
                elapsed_mono_ms = (mono_ns - self.last_observed_monotonic_ns) // 1_000_000
                divergence = abs(elapsed_wall_ms - elapsed_mono_ms)
                if divergence > self.max_clock_divergence_ms:
                    quality = "DEGRADED"
                    reasons.append("CLOCK_UNCERTAIN")
                    self.clock_uncertain_count += 1

        if quality == "DEGRADED" and "OK" in reasons:
            reasons.remove("OK")

        self.last_observed_wall_ms = wall_ms
        self.last_observed_monotonic_ns = mono_ns

        # available_at_ms is never earlier than observed_wall_utc_ms
        available_at_ms = wall_ms

        return IngressTimestamp(
            observed_wall_utc_ms=wall_ms,
            observed_monotonic_ns=mono_ns,
            available_at_ms=available_at_ms,
            quality=quality,
            reason_codes=reasons,
        )

    def record_transit_latency(self, provider_event_ms: int | None, observed_wall_ms: int) -> None:
        """Record transit latency and exchange clock offset diagnostic."""
        if provider_event_ms is not None and provider_event_ms > 0:
            latency = observed_wall_ms - provider_event_ms
            if latency >= 0:
                self._latency_samples.append(latency)
                if len(self._latency_samples) > MAX_LATENCY_SAMPLES:
                    self._latency_samples.pop(0)

            # Record exchange clock offset (provider clock minus receiver wall clock)
            offset = provider_event_ms - observed_wall_ms
            self._offset_samples.append(offset)
            if len(self._offset_samples) > MAX_LATENCY_SAMPLES:
                self._offset_samples.pop(0)

    def increment_dropped_ingress(self, count: int = 1) -> None:
        """Record dropped messages due to queue overflow or buffer saturation."""
        self.dropped_ingress_count += count

    def get_latency_percentiles(self) -> dict[str, float]:
        """Compute P50, P90, P99 latencies in milliseconds."""
        if not self._latency_samples:
            return {"p50_ms": 0.0, "p90_ms": 0.0, "p99_ms": 0.0, "sample_count": 0}

        sorted_samples = sorted(self._latency_samples)
        n = len(sorted_samples)

        def percentile(p: float) -> float:
            k = (n - 1) * p
            f = math.floor(k)
            c = math.ceil(k)
            if f == c:
                return float(sorted_samples[int(k)])
            d0 = sorted_samples[int(f)] * (c - k)
            d1 = sorted_samples[int(c)] * (k - f)
            return float(d0 + d1)

        return {
            "p50_ms": percentile(0.50),
            "p90_ms": percentile(0.90),
            "p99_ms": percentile(0.99),
            "sample_count": n,
        }

    def get_diagnostics(self) -> dict[str, Any]:
        """Summary of time authority health and clock diagnostic state."""
        percentiles = self.get_latency_percentiles()
        offset_diag = {
            "latest_ms": self._offset_samples[-1] if self._offset_samples else 0,
            "mean_ms": round(sum(self._offset_samples) / len(self._offset_samples), 2) if self._offset_samples else 0.0,
            "sample_count": len(self._offset_samples),
        }
        return {
            "connection_epoch": self.connection_epoch,
            "last_observed_wall_ms": self.last_observed_wall_ms,
            "clock_uncertain_count": self.clock_uncertain_count,
            "monotonic_violation_count": self.monotonic_violation_count,
            "dropped_ingress_count": self.dropped_ingress_count,
            "latencies": percentiles,
            "exchange_offset": offset_diag,
            "clock_status": "CLOCK_UNCERTAIN" if self.clock_uncertain_count > 0 else "CLOCK_SYNCHRONIZED",
        }


def join_mark_and_last(
    mark_event: MarketEventV1,
    last_kline_event: MarketEventV1,
    decision_at_ms: int,
) -> dict[str, Any]:
    """Point-in-Time cross-channel join of Mark Price and Last 1m Candle.

    Causal constraints:
    1. Both input events must have quality == 'VERIFIED'.
    2. Neither input event may have arrived after decision_at_ms (available_at_ms <= decision_at_ms).
    3. Derived feature known_at is max(mark.available_at_ms, last.available_at_ms).
    """
    if mark_event.symbol != last_kline_event.symbol:
        raise PointInTimeViolationError(
            f"Cannot join: mark_event symbol '{mark_event.symbol}' != last_kline symbol '{last_kline_event.symbol}'"
        )
    if mark_event.quality != "VERIFIED":
        raise PointInTimeViolationError(
            f"Cannot join: mark_event quality '{mark_event.quality}' is not VERIFIED"
        )
    if last_kline_event.quality != "VERIFIED":
        raise PointInTimeViolationError(
            f"Cannot join: last_kline_event quality '{last_kline_event.quality}' is not VERIFIED"
        )
    if mark_event.available_at_ms > decision_at_ms:
        raise PointInTimeViolationError(
            f"Causality violation: mark_event available_at_ms {mark_event.available_at_ms} > decision_at_ms {decision_at_ms}"
        )
    if last_kline_event.available_at_ms > decision_at_ms:
        raise PointInTimeViolationError(
            f"Causality violation: last_kline_event available_at_ms {last_kline_event.available_at_ms} > decision_at_ms {decision_at_ms}"
        )

    feature_known_at_ms = max(mark_event.available_at_ms, last_kline_event.available_at_ms)
    mark_payload = mark_event.payload
    kline_payload = last_kline_event.payload
    k = kline_payload.get("k", {})

    mark_p = mark_payload.get("p")
    kline_c = k.get("c")
    basis = None
    if mark_p is not None and kline_c is not None:
        try:
            basis = str(Decimal(str(kline_c)) - Decimal(str(mark_p)))
        except (InvalidOperation, TypeError, ValueError):
            basis = None

    return {
        "symbol": mark_event.symbol,
        "decision_at_ms": decision_at_ms,
        "feature_known_at_ms": feature_known_at_ms,
        "mark_price": mark_p,
        "index_price": mark_payload.get("i"),
        "estimated_funding_rate": mark_payload.get("r"),
        "kline_close": kline_c,
        "kline_closed": k.get("x", False),
        "mark_last_basis": basis,
        "quality": "VERIFIED",
    }
