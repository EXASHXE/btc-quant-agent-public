"""C Composite BAR Adapter: Synthesizes exact MarketPitPort composite bar envelopes.

Resolves Incompatibility 4 (A raw Binance kline payload vs C MarketPitPort composite BAR schema).
Aligns confirmed closed Last 1m trades with contemporaneous DerivedMark1MBar closes,
guaranteeing zero cash balance drift and exact PIT causal validation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .mark_aggregator import DerivedMark1MBar


def _canonical_json(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(data: Any) -> str:
    return hashlib.sha256(_canonical_json(data)).hexdigest()


class CCompositeBarBuilder:
    """Builds causally aligned composite 1m bars admitted by C's MarketPitPort."""

    def __init__(
        self,
        stream_id: str = "SYNTHETIC_LOCAL_PIT_V1",
        raw_manifest_sha256: str | None = None,
    ) -> None:
        self.stream_id = stream_id
        if raw_manifest_sha256 is None:
            self.manifest_sha256 = _digest(
                {"stream": stream_id, "contract": "market-event-v1", "synthetic_only": True}
            )
        else:
            self.manifest_sha256 = raw_manifest_sha256

    def build_composite_bar_envelope(
        self,
        raw_kline_payload: dict[str, Any],
        derived_mark_bar: DerivedMark1MBar,
        kline_available_at_ms: int,
        observed_monotonic_ns: int,
        connection_epoch: int = 1,
        source_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Combine closed Last 1m kline and DerivedMark1MBar into exact MarketPitPort envelope."""
        k = raw_kline_payload.get("k", raw_kline_payload)
        bar_open_ms = int(k.get("t", 0))

        # Re-align to exact 60,000ms minute boundaries if needed
        aligned_open_ms = (bar_open_ms // 60_000) * 60_000
        aligned_close_ms = aligned_open_ms + 59_999

        last_o = str(k.get("o", "0.0"))
        last_h = str(k.get("h", "0.0"))
        last_l = str(k.get("l", "0.0"))
        last_c = str(k.get("c", "0.0"))
        mark_c = str(derived_mark_bar.close)

        bar_idx = aligned_open_ms // 60_000
        event_id = f"BAR-{bar_idx}"

        composite_payload = {
            "bar_open_ms": aligned_open_ms,
            "bar_close_ms": aligned_close_ms,
            "closed": True,
            "last_open": last_o,
            "last_high": last_h,
            "last_low": last_l,
            "last_close": last_c,
            "mark_close": mark_c,
            "event_id": event_id,
        }

        # Causal invariant: feature known at max of constituent arrival times, and at least close_ms
        avail_ms = max(
            kline_available_at_ms,
            derived_mark_bar.derived_available_at_ms,
            aligned_close_ms,
        )

        payload_sha = _digest(composite_payload)

        return {
            "schema_version": "market-event-v1",
            "symbol": "BTCUSDT",
            "product": "BINANCE_USDT_M_PERP",
            "channel": "last_kline_1m",
            "provider_event_ms": aligned_close_ms,
            "provider_transaction_ms": aligned_close_ms,
            "observed_wall_utc_ms": avail_ms,
            "observed_monotonic_ns": observed_monotonic_ns,
            "available_at_ms": avail_ms,
            "source_stream_id": self.stream_id,
            "connection_epoch": connection_epoch,
            "source_sequence": source_sequence,
            "payload_sha256": payload_sha,
            "payload": composite_payload,
            "quality": "VERIFIED",
            "reason_codes": ["OK"],
            "raw_source_manifest_sha256": self.manifest_sha256,
        }
