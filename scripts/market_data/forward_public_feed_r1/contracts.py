"""Exact semantic contracts, schemas, and serialization for MarketEventV1 and BookIntegrityV1."""

from __future__ import annotations

import decimal
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
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

FORBIDDEN_HOSTS: tuple[str, ...] = (
    "dapi.binance.com",          # COIN-M strictly forbidden
    "api.binance.com",           # Spot strictly forbidden
    "testnet.binancefuture.com", # Testnet forbidden
    "testnet.binance.vision",
)

FORBIDDEN_PRIVATE_KEYWORDS: tuple[str, ...] = (
    "order",
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
    "userdata",
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


def get_aggressor_side(payload: dict[str, Any]) -> str:
    """Extract trade aggressor side from Binance aggTrade frame.
    
    Binance USDⓈ-M 'm' field: Was the buyer the maker?
    - If m is True: buyer was maker, so seller was taker / aggressor -> SELL.
    - If m is False: buyer was taker / aggressor -> BUY.
    """
    m = payload.get("m")
    if m is True:
        return "SELL"
    if m is False:
        return "BUY"
    return "UNKNOWN"


def validate_provider_payload_shape(
    channel: str,
    payload: dict[str, Any],
    allowed_symbol: str = ALLOWED_SYMBOL,
) -> None:
    """Strictly validate provider payload shape, required public fields, and symbol allowlist."""
    assert_no_private_identifiers(payload)

    # Check top-level symbol if present
    s = payload.get("s")
    if s is not None and s != allowed_symbol:
        raise ContractValidationError(
            f"Provider symbol '{s}' does not match allowed symbol '{allowed_symbol}'"
        )

    if channel == "last_kline_1m":
        k = payload.get("k")
        if not isinstance(k, dict):
            raise ContractValidationError("Kline payload missing 'k' candle dictionary")
        if k.get("s") and k.get("s") != allowed_symbol:
            raise ContractValidationError(
                f"Kline candle symbol '{k.get('s')}' does not match '{allowed_symbol}'"
            )
        for req in ("t", "T", "s", "i", "o", "c", "h", "l", "v", "x"):
            if req not in k:
                raise ContractValidationError(f"Kline payload missing required field '{req}'")

    elif channel == "mark_price":
        for req in ("p", "r", "T"):
            if req not in payload:
                raise ContractValidationError(f"Mark price payload missing required field '{req}'")

    elif channel == "agg_trade":
        for req in ("a", "p", "q", "m"):
            if req not in payload:
                raise ContractValidationError(f"Agg trade payload missing required field '{req}'")

    elif channel == "depth_delta":
        for req in ("U", "u", "b", "a"):
            if req not in payload:
                raise ContractValidationError(f"Depth delta payload missing required field '{req}'")

    elif channel == "depth_snapshot":
        for req in ("lastUpdateId", "bids", "asks"):
            if req not in payload:
                raise ContractValidationError(f"Depth snapshot missing required field '{req}'")

    elif channel == "funding_settled":
        for req in ("fundingRate", "fundingTime"):
            if req not in payload:
                raise ContractValidationError(f"Funding settled payload missing required field '{req}'")


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
        if self.best_bid is not None:
            try:
                bid_dec = Decimal(str(self.best_bid))
                if not bid_dec.is_finite() or bid_dec <= Decimal(0):
                    raise ContractValidationError(
                        f"best_bid must be a positive finite decimal, got '{self.best_bid}'"
                    )
            except (decimal.InvalidOperation, TypeError) as exc:
                raise ContractValidationError(f"Invalid best_bid '{self.best_bid}': {exc}") from exc

        if self.best_ask is not None:
            try:
                ask_dec = Decimal(str(self.best_ask))
                if not ask_dec.is_finite() or ask_dec <= Decimal(0):
                    raise ContractValidationError(
                        f"best_ask must be a positive finite decimal, got '{self.best_ask}'"
                    )
            except (decimal.InvalidOperation, TypeError) as exc:
                raise ContractValidationError(f"Invalid best_ask '{self.best_ask}': {exc}") from exc

        if self.best_bid is not None and self.best_ask is not None:
            bid_dec = Decimal(str(self.best_bid))
            ask_dec = Decimal(str(self.best_ask))
            if bid_dec >= ask_dec and self.continuous and self.quality == "VERIFIED":
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
        # Check raw source manifest digest
        if not self.raw_source_manifest_sha256 or not isinstance(self.raw_source_manifest_sha256, str):
            raise ContractValidationError("raw_source_manifest_sha256 must be a non-empty string digest")
        if len(self.raw_source_manifest_sha256) == 64 and not all(c in "0123456789abcdefABCDEF" for c in self.raw_source_manifest_sha256):
            raise ContractValidationError(
                f"raw_source_manifest_sha256 has invalid characters: '{self.raw_source_manifest_sha256}'"
            )

        # Check payload integrity and symbol allowlist
        assert_no_private_identifiers(self.payload)
        payload_sym = self.payload.get("s")
        if payload_sym is not None and payload_sym != self.symbol:
            raise ContractValidationError(
                f"Payload symbol '{payload_sym}' does not match allowed symbol '{self.symbol}'"
            )
        kline_sym = self.payload.get("k", {}).get("s") if isinstance(self.payload.get("k"), dict) else None
        if kline_sym is not None and kline_sym != self.symbol:
            raise ContractValidationError(
                f"Kline candle symbol '{kline_sym}' does not match allowed symbol '{self.symbol}'"
            )

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


def build_market_event_envelope(
    symbol: str,
    channel: str,
    payload: dict[str, Any],
    observed_wall_utc_ms: int,
    observed_monotonic_ns: int,
    available_at_ms: int,
    provider_event_ms: int | None = None,
    provider_transaction_ms: int | None = None,
    source_stream_id: str = "",
    connection_epoch: str | int = "1",
    source_sequence: int | None = None,
    quality: str = "VERIFIED",
    reason_codes: list[str] | None = None,
    raw_source_manifest_sha256: str = "",
    product: str = ALLOWED_PRODUCT,
    schema_version: str = SCHEMA_VERSION,
    book: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical factory for market-event-v1 envelope dictionaries."""
    payload_sha = compute_sha256(payload)
    envelope: dict[str, Any] = {
        "schema_version": schema_version,
        "symbol": symbol,
        "product": product,
        "channel": channel,
        "provider_event_ms": provider_event_ms,
        "provider_transaction_ms": provider_transaction_ms,
        "observed_wall_utc_ms": observed_wall_utc_ms,
        "observed_monotonic_ns": observed_monotonic_ns,
        "available_at_ms": available_at_ms,
        "source_stream_id": source_stream_id,
        "connection_epoch": connection_epoch,
        "source_sequence": source_sequence,
        "payload_sha256": payload_sha,
        "payload": payload,
        "quality": quality,
        "reason_codes": list(reason_codes) if reason_codes is not None else ["OK"],
        "raw_source_manifest_sha256": raw_source_manifest_sha256,
    }
    if book is not None:
        envelope["book"] = book
    return envelope

