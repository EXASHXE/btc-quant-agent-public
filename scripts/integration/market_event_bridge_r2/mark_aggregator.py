"""Mark Price Tick Aggregator: Derives verified 1-minute Mark bars from official 1-second ticks.

Resolves Incompatibility 1 (A markPriceUpdate tick vs B 1m kline consumer).
Enforces causal window completion, minimum sample coverage, jitter gap limits,
and source provenance tracking. Never promotes a single arbitrary tick to an official 1m bar.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

MIN_SAMPLES_PER_MINUTE: int = 40
MAX_JITTER_GAP_MS: int = 5_000


@dataclass(frozen=True)
class DerivedMark1MBar:
    """Causally derived 1-minute Mark Price Candlestick Bar."""

    bar_open_ms: int
    bar_close_ms: int
    closed: bool
    open: float
    high: float
    low: float
    close: float
    sample_count: int
    derived_available_at_ms: int
    feature_known_at_ms: int
    quality: str
    reason_codes: tuple[str, ...]
    parent_event_sha256: tuple[str, ...]
    raw_source_manifest_sha256: str
    symbol: str = "BTCUSDT"
    derivation_version: str = "derived-mark-1m-v1"
    producer_upstream_sha: str = "df00997f344eba82f7cca0d03ee1617948abee44"
    route_epoch: str = "route-epoch-0"
    connection_epoch: int = 1
    source_observed_wall_utc_ms: int = 0
    source_available_at_ms: int = 0
    clock_uncertainty_ms: int = 0

    def to_b_kline_payload(self) -> dict[str, Any]:
        """Convert to Binance kline payload structure expected by B's parse_kline_payload."""
        return {
            "e": "kline",
            "E": self.derived_available_at_ms,
            "s": self.symbol,
            "k": {
                "t": self.bar_open_ms,
                "T": self.bar_close_ms,
                "s": self.symbol,
                "i": "1m",
                "f": 0,
                "L": self.sample_count,
                "o": str(self.open),
                "c": str(self.close),
                "h": str(self.high),
                "l": str(self.low),
                "v": "0.0",
                "n": self.sample_count,
                "x": self.closed,
                "q": "0.0",
                "V": "0.0",
                "Q": "0.0",
                "B": "0",
            },
        }

    def to_dict(self) -> dict[str, Any]:
        src_wall = self.source_observed_wall_utc_ms or self.derived_available_at_ms
        src_avail = self.source_available_at_ms or self.derived_available_at_ms
        base = {
            "schema_version": self.derivation_version,
            "derivation_version": self.derivation_version,
            "symbol": self.symbol,
            "bar_open_ms": self.bar_open_ms,
            "bar_close_ms": self.bar_close_ms,
            "closed": self.closed,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "sample_count": self.sample_count,
            "source_observed_wall_utc_ms": src_wall,
            "source_available_at_ms": src_avail,
            "derived_available_at_ms": self.derived_available_at_ms,
            "feature_known_at_ms": self.feature_known_at_ms,
            "clock_uncertainty_ms": self.clock_uncertainty_ms,
            "route_epoch": self.route_epoch,
            "connection_epoch": self.connection_epoch,
            "producer_upstream_sha": self.producer_upstream_sha,
            "quality": self.quality,
            "reason_codes": list(self.reason_codes),
            "parent_event_sha256": list(self.parent_event_sha256),
            "raw_source_manifest_sha256": self.raw_source_manifest_sha256,
        }
        canonical_sha = hashlib.sha256(
            json.dumps(base, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        base["canonical_sha256"] = canonical_sha
        return base


@dataclass
class _BufferedMarkTick:
    provider_ms: int
    price: float
    available_at_ms: int
    payload_sha256: str
    manifest_sha256: str


class MarkPriceAggregator:
    """Aggregates discrete 1-second Mark Price ticks into rigorous DERIVED_MARK_1M bars."""

    def __init__(
        self,
        min_samples: int = MIN_SAMPLES_PER_MINUTE,
        max_gap_ms: int = MAX_JITTER_GAP_MS,
    ) -> None:
        self.min_samples = min_samples
        self.max_gap_ms = max_gap_ms
        self._current_window_open_ms: int | None = None
        self._buffer: list[_BufferedMarkTick] = []
        self.completed_bars: dict[int, DerivedMark1MBar] = {}

    def ingest_tick(
        self,
        provider_event_ms: int,
        mark_price: float | str | Decimal,
        available_at_ms: int,
        payload_sha256: str = "",
        raw_manifest_sha256: str = "",
    ) -> DerivedMark1MBar | None:
        """Ingest single mark price tick. Returns completed DerivedMark1MBar when minute rolls."""
        price_flt = float(mark_price)
        tick_window_open = (provider_event_ms // 60_000) * 60_000

        emitted_bar: DerivedMark1MBar | None = None

        if self._current_window_open_ms is None:
            self._current_window_open_ms = tick_window_open
        elif tick_window_open > self._current_window_open_ms:
            # Current minute rolled over; evaluate completed window
            emitted_bar = self._finalize_window(self._current_window_open_ms, self._buffer)
            self.completed_bars[self._current_window_open_ms] = emitted_bar
            self._current_window_open_ms = tick_window_open
            self._buffer = []

        self._buffer.append(
            _BufferedMarkTick(
                provider_ms=provider_event_ms,
                price=price_flt,
                available_at_ms=available_at_ms,
                payload_sha256=payload_sha256,
                manifest_sha256=raw_manifest_sha256,
            )
        )

        return emitted_bar

    def flush_window(self) -> DerivedMark1MBar | None:
        """Force finalize current buffer (e.g. at end of stream)."""
        if self._current_window_open_ms is not None and self._buffer:
            bar = self._finalize_window(self._current_window_open_ms, self._buffer)
            self.completed_bars[self._current_window_open_ms] = bar
            self._current_window_open_ms = None
            self._buffer = []
            return bar
        return None

    def _finalize_window(
        self,
        window_open_ms: int,
        ticks: list[_BufferedMarkTick],
    ) -> DerivedMark1MBar:
        window_close_ms = window_open_ms + 59_999
        reasons: list[str] = []
        quality = "VERIFIED"

        if len(ticks) < self.min_samples:
            quality = "UNKNOWN"
            reasons.append(f"INSUFFICIENT_SAMPLE_COVERAGE: count={len(ticks)} < min={self.min_samples}")

        # Check jitter gap between consecutive ticks
        max_observed_gap = 0
        for i in range(1, len(ticks)):
            gap = ticks[i].provider_ms - ticks[i - 1].provider_ms
            max_observed_gap = max(max_observed_gap, gap)
        if max_observed_gap > self.max_gap_ms:
            quality = "UNKNOWN"
            reasons.append(f"EXCESSIVE_JITTER_GAP: max_gap={max_observed_gap}ms > limit={self.max_gap_ms}ms")

        # Boundary checks
        if ticks:
            if ticks[0].provider_ms - window_open_ms > 10_000:
                quality = "UNKNOWN"
                reasons.append("LATE_WINDOW_START")
            if window_close_ms - ticks[-1].provider_ms > 10_000:
                quality = "UNKNOWN"
                reasons.append("EARLY_WINDOW_END")

        if quality == "VERIFIED":
            reasons.append("OK")

        prices = [t.price for t in ticks]
        o = prices[0] if prices else 0.0
        c = prices[-1] if prices else 0.0
        h = max(prices) if prices else 0.0
        low = min(prices) if prices else 0.0

        derived_available_at = max((t.available_at_ms for t in ticks), default=window_close_ms)
        parent_shas = tuple(t.payload_sha256 for t in ticks if t.payload_sha256)
        manifest_sha = ticks[-1].manifest_sha256 if ticks else ""

        return DerivedMark1MBar(
            bar_open_ms=window_open_ms,
            bar_close_ms=window_close_ms,
            closed=(quality == "VERIFIED"),
            open=round(o, 4),
            high=round(h, 4),
            low=round(low, 4),
            close=round(c, 4),
            sample_count=len(ticks),
            derived_available_at_ms=derived_available_at,
            feature_known_at_ms=derived_available_at,
            quality=quality,
            reason_codes=tuple(reasons),
            parent_event_sha256=parent_shas,
            raw_source_manifest_sha256=manifest_sha,
        )
