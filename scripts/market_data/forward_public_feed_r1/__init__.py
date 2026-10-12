"""Binance USDⓈ-M Futures Public Forward Market Recorder (R1).

High-reliability, public-only, account-free, order-free BTCUSDT forward market recorder.
Produces sealed MarketEventV1 receipts, maintains BookIntegrityV1 depth, and enforces PIT time authority.
"""

from __future__ import annotations

from .contracts import (
    ALLOWED_PRODUCT,
    ALLOWED_SYMBOL,
    BINANCE_DOCS_URLS,
    CHANNELS,
    QUALITY_LEVELS,
    SCHEMA_VERSION,
    BookIntegrityV1,
    MarketEventV1,
    canonical_json_bytes,
    compute_dedupe_key,
    compute_sha256,
)

__all__ = [
    "ALLOWED_PRODUCT",
    "ALLOWED_SYMBOL",
    "BINANCE_DOCS_URLS",
    "CHANNELS",
    "QUALITY_LEVELS",
    "SCHEMA_VERSION",
    "BookIntegrityV1",
    "MarketEventV1",
    "canonical_json_bytes",
    "compute_dedupe_key",
    "compute_sha256",
]
