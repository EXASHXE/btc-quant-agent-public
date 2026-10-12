"""Exact semantic contracts, schemas, and serialization for MarketEventV1 and BookIntegrityV1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION: str = "market-event-v1"
ALLOWED_PRODUCT: str = "BINANCE_USDT_M_PERP"
ALLOWED_SYMBOL: str = "BTCUSDT"

CHANNELS: tuple[str, ...] = (
    "last_kline_1m",
    "mark_price",
    "agg_trade",
    "depth_delta",
    "depth_snapshot",
    "funding_settled",
    "health",
)

QUALITY_LEVELS: tuple[str, ...] = (
    "VERIFIED",
    "DEGRADED",
    "UNKNOWN",
    "INVALID",
)

BINANCE_DOCS_URLS: dict[str, str] = {
    "introduction": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/Introduction",
    "websocket_streams": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Live-Subscribing-Unsubscribing-to-streams",
    "depth_stream": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Diff-Book-Depth-Streams",
    "depth_snapshot": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Order-Book",
    "kline_stream": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Kline-Candlestick-Streams",
    "mark_price_stream": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Mark-Price-Stream",
    "agg_trade_stream": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Aggregate-Trade-Streams",
    "funding_rate_history": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Get-Funding-Rate-History",
}

ALLOWED_WS_HOSTS: tuple[str, ...] = (
    "fstream.binance.com",
)

ALLOWED_REST_HOSTS: tuple[str, ...] = (
    "fapi.binance.com",
)

FORBIDDEN_HOST_PATTERNS: tuple[str, ...] = (
    "dapi.binance.com",       # COIN-M strictly forbidden
    "api.binance.com",        # Spot strictly forbidden
    "testnet.binancefuture.com", # Testnet forbidden
    "testnet.binance.vision",
)

FORBIDDEN_PRIVATE_KEYWORDS: tuple[str, ...] = (
    "apikey",
    "api_key",
    "secretkey",
    "secret_key",
    "listenkey",
    "orderid",
    "clientorderid",
    "signature",
    "privatekey",
    "wallet",
)


class ContractValidationError(ValueError):
    """Raised when an event fails strict schema or semantic validation."""


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize object to deterministic canonical UTF-8 JSON bytes (RFC 8785 style)."""
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_sha256(data: bytes | str | dict[str, Any]) -> str:
    """Compute hex-encoded SHA-256 digest."""
    if isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, (dict, list)):
        raw = canonical_json_bytes(data)
    else:
        raw = data
    return hashlib.sha256(raw).hexdigest()


def compute_dedupe_key(
    symbol: str,
    channel: str,
    connection_epoch: str,
    provider_id_or_raw_sha: str,
) -> str:
    """Deterministic deduplication key: sha256(symbol:channel:epoch:provider-id-or-raw-sha)."""
    seed = f"{symbol}:{channel}:{connection_epoch}:{provider_id_or_raw_sha}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def assert_no_private_identifiers(payload: Any, path: str = "") -> None:
    """Strictly verify payload does not contain private identifiers or API keys."""
    if isinstance(payload, dict):
        for k, v in payload.items():
            k_lower = str(k).lower().replace("-", "").replace("_", "")
            for forbidden in FORBIDDEN_PRIVATE_KEYWORDS:
                if forbidden in k_lower:
                    raise ContractValidationError(
                        f"Forbidden private identifier '{k}' detected at '{path}'. Public feeds only."
                    )
            assert_no_private_identifiers(v, f"{path}.{k}" if path else str(k))
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            assert_no_private_identifiers(item, f"{path}[{idx}]")


@dataclass(frozen=True)
class BookIntegrityV1:
    """Order book integrity receipt snapshot."""

    snapshot_update_id: int | None
    first_update_id: int | None
    final_update_id: int | None
    previous_final_update_id: int | None
    continuous: bool
    best_bid: str | None
    best_ask: str | None
    observed_depth_levels: int
    stale_age_ms: int
    quality: str
    reason_codes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.quality not in QUALITY_LEVELS:
            raise ContractValidationError(
                f"Invalid book quality: '{self.quality}'. Must be one of {QUALITY_LEVELS}"
            )
        if self.observed_depth_levels < 0:
            raise ContractValidationError(
                f"observed_depth_levels cannot be negative: {self.observed_depth_levels}"
            )
        if self.stale_age_ms < 0:
            raise ContractValidationError(
                f"stale_age_ms cannot be negative: {self.stale_age_ms}"
            )
        if self.best_bid is not None and self.best_ask is not None:
            bid = float(self.best_bid)
            ask = float(self.best_ask)
            if bid <= 0.0 or ask <= 0.0:
                raise ContractValidationError("Bid and ask prices must be positive")
            if bid >= ask and self.continuous and self.quality == "VERIFIED":
                raise ContractValidationError(
                    f"Crossed book detected in VERIFIED status: bid {self.best_bid} >= ask {self.best_ask}"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_update_id": self.snapshot_update_id,
            "first_update_id": self.first_update_id,
            "final_update_id": self.final_update_id,
            "previous_final_update_id": self.previous_final_update_id,
            "continuous": self.continuous,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "observed_depth_levels": self.observed_depth_levels,
            "stale_age_ms": self.stale_age_ms,
            "quality": self.quality,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BookIntegrityV1:
        return cls(
            snapshot_update_id=data.get("snapshot_update_id"),
            first_update_id=data.get("first_update_id"),
            final_update_id=data.get("final_update_id"),
            previous_final_update_id=data.get("previous_final_update_id"),
            continuous=bool(data.get("continuous", False)),
            best_bid=data.get("best_bid"),
            best_ask=data.get("best_ask"),
            observed_depth_levels=int(data.get("observed_depth_levels", 0)),
            stale_age_ms=int(data.get("stale_age_ms", 0)),
            quality=str(data.get("quality", "UNKNOWN")),
            reason_codes=list(data.get("reason_codes", [])),
        )


@dataclass(frozen=True)
class MarketEventV1:
    """Canonical sealed MarketEventV1 receipt."""

    schema_version: str
    symbol: str
    product: str
    channel: str
    provider_event_ms: int | None
    provider_transaction_ms: int | None
    observed_wall_utc_ms: int
    observed_monotonic_ns: int
    available_at_ms: int
    source_stream_id: str
    connection_epoch: str
    source_sequence: int | None
    payload_sha256: str
    payload: dict[str, Any]
    quality: str
    reason_codes: list[str]
    raw_source_manifest_sha256: str
    book: BookIntegrityV1 | None = None

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError(
                f"Invalid schema_version '{self.schema_version}'. Expected '{SCHEMA_VERSION}'"
            )
        if self.product != ALLOWED_PRODUCT:
            raise ContractValidationError(
                f"Invalid product '{self.product}'. Expected '{ALLOWED_PRODUCT}'"
            )
        if self.symbol != ALLOWED_SYMBOL:
            raise ContractValidationError(
                f"Invalid symbol '{self.symbol}'. Expected exact uppercase '{ALLOWED_SYMBOL}'"
            )
        if self.channel not in CHANNELS:
            raise ContractValidationError(
                f"Invalid channel '{self.channel}'. Expected one of {CHANNELS}"
            )
        if self.quality not in QUALITY_LEVELS:
            raise ContractValidationError(
                f"Invalid quality '{self.quality}'. Expected one of {QUALITY_LEVELS}"
            )
        if self.available_at_ms < self.observed_wall_utc_ms:
            raise ContractValidationError(
                f"available_at_ms ({self.available_at_ms}) cannot be earlier than "
                f"observed_wall_utc_ms ({self.observed_wall_utc_ms})"
            )
        # Check payload integrity
        assert_no_private_identifiers(self.payload)
        expected_payload_sha = compute_sha256(self.payload)
        if self.payload_sha256 != expected_payload_sha:
            raise ContractValidationError(
                f"payload_sha256 mismatch: given '{self.payload_sha256}', "
                f"calculated '{expected_payload_sha}'"
            )

    def dedupe_key(self) -> str:
        provider_id = (
            str(self.source_sequence)
            if self.source_sequence is not None
            else self.payload_sha256
        )
        return compute_dedupe_key(
            self.symbol,
            self.channel,
            self.connection_epoch,
            provider_id,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "product": self.product,
            "channel": self.channel,
            "provider_event_ms": self.provider_event_ms,
            "provider_transaction_ms": self.provider_transaction_ms,
            "observed_wall_utc_ms": self.observed_wall_utc_ms,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "available_at_ms": self.available_at_ms,
            "source_stream_id": self.source_stream_id,
            "connection_epoch": self.connection_epoch,
            "source_sequence": self.source_sequence,
            "payload_sha256": self.payload_sha256,
            "payload": self.payload,
            "quality": self.quality,
            "reason_codes": list(self.reason_codes),
            "raw_source_manifest_sha256": self.raw_source_manifest_sha256,
            "book": self.book.to_dict() if self.book is not None else None,
        }
        return result

    def canonical_json(self) -> str:
        return canonical_json_bytes(self.to_dict()).decode("utf-8")

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_dict())

    def event_sha256(self) -> str:
        return compute_sha256(self.canonical_bytes())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketEventV1:
        book_data = data.get("book")
        book = BookIntegrityV1.from_dict(book_data) if book_data else None
        return cls(
            schema_version=str(data.get("schema_version", "")),
            symbol=str(data.get("symbol", "")),
            product=str(data.get("product", "")),
            channel=str(data.get("channel", "")),
            provider_event_ms=data.get("provider_event_ms"),
            provider_transaction_ms=data.get("provider_transaction_ms"),
            observed_wall_utc_ms=int(data.get("observed_wall_utc_ms", 0)),
            observed_monotonic_ns=int(data.get("observed_monotonic_ns", 0)),
            available_at_ms=int(data.get("available_at_ms", 0)),
            source_stream_id=str(data.get("source_stream_id", "")),
            connection_epoch=str(data.get("connection_epoch", "")),
            source_sequence=data.get("source_sequence"),
            payload_sha256=str(data.get("payload_sha256", "")),
            payload=dict(data.get("payload", {})),
            quality=str(data.get("quality", "UNKNOWN")),
            reason_codes=list(data.get("reason_codes", [])),
            raw_source_manifest_sha256=str(data.get("raw_source_manifest_sha256", "")),
            book=book,
        )
