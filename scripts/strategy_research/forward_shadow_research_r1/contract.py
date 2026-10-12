"""Contract definitions for MarketEventV1, BookIntegrityV1, and strict causal envelopes.

Under B-line Controller Authority:
V06_FORWARD_SHADOW_G1G3_THREE_GEMINI_GOALS_R1_CONTROLLER_AUTHORITY.md
TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def canonical_json(data: Any) -> bytes:
    """Deterministic UTF-8 JSON serialization with sorted keys and no whitespace variation."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Return SHA-256 hex digest of bytes."""
    return hashlib.sha256(data).hexdigest()


class Channel(str, Enum):
    LAST_KLINE_1M = "last_kline_1m"
    MARK_PRICE = "mark_price"
    AGG_TRADE = "agg_trade"
    DEPTH_DELTA = "depth_delta"
    DEPTH_SNAPSHOT = "depth_snapshot"
    FUNDING_SETTLED = "funding_settled"
    HEALTH = "health"


class Quality(str, Enum):
    VERIFIED = "VERIFIED"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"


@dataclass(frozen=True)
class BookIntegrityV1:
    snapshot_update_id: int | None = None
    first_update_id: int | None = None
    final_update_id: int | None = None
    previous_final_update_id: int | None = None
    continuous: bool = True
    best_bid: float | None = None
    best_ask: float | None = None
    bids: tuple[tuple[float, float], ...] = field(default_factory=tuple)  # (price, qty)
    asks: tuple[tuple[float, float], ...] = field(default_factory=tuple)  # (price, qty)
    observed_depth_levels: int = 0
    stale_age_ms: int = 0
    quality: Quality = Quality.VERIFIED
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> tuple[Quality, tuple[str, ...]]:
        """Validate book integrity invariants."""
        reasons = list(self.reason_codes)
        current_quality = self.quality

        # Check crossed spread
        if self.best_bid is not None and self.best_ask is not None:
            if self.best_bid <= 0 or self.best_ask <= 0:
                reasons.append("INVALID_QUOTE_PRICE")
                current_quality = Quality.INVALID
            elif self.best_bid >= self.best_ask:
                reasons.append("CROSSED_SPREAD")
                current_quality = Quality.INVALID

        # Check depth staleness (> 1000ms fails closed)
        if self.stale_age_ms > 1000:
            reasons.append("STALE_DEPTH_OVER_1000MS")
            if current_quality == Quality.VERIFIED:
                current_quality = Quality.DEGRADED

        # Continuity check
        if not self.continuous:
            reasons.append("L2_DISCONTINUOUS")
            if current_quality == Quality.VERIFIED:
                current_quality = Quality.DEGRADED

        return current_quality, tuple(dict.fromkeys(reasons))

    def top_n_imbalance(self, n: int = 10) -> float | None:
        """Compute top-N order book imbalance: (bid_notional - ask_notional) / (sum)."""
        if not self.bids or not self.asks:
            return None
        top_bids = self.bids[:n]
        top_asks = self.asks[:n]
        bid_notional = sum(p * q for p, q in top_bids)
        ask_notional = sum(p * q for p, q in top_asks)
        total = bid_notional + ask_notional
        if total <= 0:
            return None
        return (bid_notional - ask_notional) / total

    def spread_bps(self, ref_price: float) -> float | None:
        """Spread in basis points relative to ref_price."""
        if self.best_bid is None or self.best_ask is None or ref_price <= 0:
            return None
        return ((self.best_ask - self.best_bid) / ref_price) * 10000.0


@dataclass(frozen=True)
class BarData:
    bar_open_ms: int
    bar_close_ms: int
    closed: bool
    open: float
    high: float
    low: float
    close: float
    volume: float
    taker_buy_volume: float = 0.0
    quality: Quality = Quality.VERIFIED
    available_at_ms: int = 0


@dataclass(frozen=True)
class SettledFundingData:
    funding_time_ms: int
    funding_rate: float
    mark_price: float
    settled: bool = True


@dataclass(frozen=True)
class AggTradeData:
    aggregate_trade_id: int
    price: float
    quantity: float
    first_trade_id: int
    last_trade_id: int
    trade_time_ms: int
    is_buyer_maker: bool  # True => buyer is maker => seller is taker/aggressor (sell trade)


@dataclass(frozen=True)
class MarketEventV1:
    channel: Channel
    observed_wall_utc_ms: int
    observed_monotonic_ns: int
    available_at_ms: int
    source_stream_id: str
    connection_epoch: str
    payload_sha256: str
    payload: dict[str, Any]
    quality: Quality
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    raw_source_manifest_sha256: str = ""
    symbol: str = "BTCUSDT"
    product: str = "BINANCE_USDT_M_PERP"
    schema_version: str = "market-event-v1"
    provider_event_ms: int | None = None
    provider_transaction_ms: int | None = None
    source_sequence: int | None = None
    book: BookIntegrityV1 | None = None

    def dedupe_key(self) -> str:
        """Deterministic dedupe key: sha256(symbol:channel:epoch:provider_id_or_raw_sha)."""
        provider_id = (
            self.payload.get("id")
            or self.payload.get("a")
            or self.payload.get("E")
            or self.payload_sha256
        )
        ident = f"{self.symbol}:{self.channel.value}:{self.connection_epoch}:{provider_id}"
        return sha256_hex(ident.encode("utf-8"))

    def to_dict(self) -> dict[str, Any]:
        """Convert to canonical dictionary."""
        d: dict[str, Any] = {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "product": self.product,
            "channel": self.channel.value,
            "provider_event_ms": self.provider_event_ms,
            "provider_transaction_ms": self.provider_transaction_ms,
            "observed_wall_utc_ms": self.observed_wall_utc_ms,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "available_at_ms": self.available_at_ms,
            "source_stream_id": self.source_stream_id,
            "connection_epoch": str(self.connection_epoch),
            "source_sequence": self.source_sequence,
            "payload_sha256": self.payload_sha256,
            "payload": self.payload,
            "quality": self.quality.value,
            "reason_codes": list(self.reason_codes),
            "raw_source_manifest_sha256": self.raw_source_manifest_sha256,
        }
        if self.book is not None:
            d["book"] = {
                "snapshot_update_id": self.book.snapshot_update_id,
                "first_update_id": self.book.first_update_id,
                "final_update_id": self.book.final_update_id,
                "previous_final_update_id": self.book.previous_final_update_id,
                "continuous": self.book.continuous,
                "best_bid": self.book.best_bid,
                "best_ask": self.book.best_ask,
                "bids": [list(b) for b in self.book.bids],
                "asks": [list(a) for a in self.book.asks],
                "observed_depth_levels": self.book.observed_depth_levels,
                "stale_age_ms": self.book.stale_age_ms,
                "quality": self.book.quality.value,
                "reason_codes": list(self.book.reason_codes),
            }
        return d

    def to_canonical_json(self) -> bytes:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MarketEventV1:
        """Parse and strictly validate a MarketEventV1 from a dictionary."""
        if data.get("schema_version") != "market-event-v1":
            raise ValueError(f"Invalid schema_version: {data.get('schema_version')}")
        if data.get("symbol") != "BTCUSDT":
            raise ValueError(f"Only BTCUSDT admitted: {data.get('symbol')}")
        if data.get("product") != "BINANCE_USDT_M_PERP":
            raise ValueError(f"Invalid product: {data.get('product')}")

        channel = Channel(data["channel"])
        quality = Quality(data.get("quality", "UNKNOWN"))
        reasons = list(data.get("reason_codes", []))

        # Payload SHA-256 verification
        payload = data.get("payload", {})
        payload_bytes = canonical_json(payload)
        actual_payload_sha = sha256_hex(payload_bytes)
        declared_sha = data.get("payload_sha256", "")
        if declared_sha and declared_sha != actual_payload_sha:
            reasons.append("PAYLOAD_SHA256_MISMATCH")
            quality = Quality.INVALID

        # Wall vs Monotonic consistency: available_at_ms must be >= observed_wall_utc_ms
        obs_wall = int(data["observed_wall_utc_ms"])
        avail_ms = int(data.get("available_at_ms", obs_wall))
        if avail_ms < obs_wall:
            reasons.append("AVAILABLE_BEFORE_WALL_INGRESS")
            quality = Quality.INVALID

        # Channel specific validation: mark stale > 2000ms fails closed
        provider_event_ms = data.get("provider_event_ms")
        if (
            channel == Channel.MARK_PRICE
            and provider_event_ms is not None
            and (obs_wall - provider_event_ms) > 2000
        ):
            reasons.append("STALE_MARK_OVER_2000MS")
            if quality == Quality.VERIFIED:
                quality = Quality.DEGRADED

        # Parse BookIntegrityV1 if present
        book = None
        book_data = data.get("book")
        if book_data is not None:
            bids = tuple((float(b[0]), float(b[1])) for b in book_data.get("bids", []))
            asks = tuple((float(a[0]), float(a[1])) for a in book_data.get("asks", []))
            book = BookIntegrityV1(
                snapshot_update_id=book_data.get("snapshot_update_id"),
                first_update_id=book_data.get("first_update_id"),
                final_update_id=book_data.get("final_update_id"),
                previous_final_update_id=book_data.get("previous_final_update_id"),
                continuous=bool(book_data.get("continuous", True)),
                best_bid=float(book_data["best_bid"]) if book_data.get("best_bid") is not None else None,
                best_ask=float(book_data["best_ask"]) if book_data.get("best_ask") is not None else None,
                bids=bids,
                asks=asks,
                observed_depth_levels=int(book_data.get("observed_depth_levels", len(bids) + len(asks))),
                stale_age_ms=int(book_data.get("stale_age_ms", 0)),
                quality=Quality(book_data.get("quality", "VERIFIED")),
                reason_codes=tuple(book_data.get("reason_codes", [])),
            )
            book_qual, book_reasons = book.validate()
            if book_qual in (Quality.DEGRADED, Quality.INVALID):
                reasons.extend(book_reasons)
                if quality == Quality.VERIFIED:
                    quality = book_qual

        return cls(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product="BINANCE_USDT_M_PERP",
            channel=channel,
            provider_event_ms=provider_event_ms,
            provider_transaction_ms=data.get("provider_transaction_ms"),
            observed_wall_utc_ms=obs_wall,
            observed_monotonic_ns=int(data["observed_monotonic_ns"]),
            available_at_ms=avail_ms,
            source_stream_id=str(data["source_stream_id"]),
            connection_epoch=str(data["connection_epoch"]),
            source_sequence=data.get("source_sequence"),
            payload_sha256=actual_payload_sha,
            payload=payload,
            quality=quality,
            reason_codes=tuple(dict.fromkeys(reasons)),
            raw_source_manifest_sha256=str(data.get("raw_source_manifest_sha256", "")),
            book=book,
        )


def parse_kline_payload(
    payload: dict[str, Any],
    quality: Quality = Quality.VERIFIED,
    available_at_ms: int = 0,
) -> BarData:
    """Parse standard Binance USD-M Futures kline payload into BarData."""
    # Binance kline payload structure: {'k': {'t': open_time, 'T': close_time, 'o': open, ... 'x': is_closed}}
    # or direct fields
    k = payload.get("k", payload)
    return BarData(
        bar_open_ms=int(k.get("t", 0)),
        bar_close_ms=int(k.get("T", 0)),
        closed=bool(k.get("x", False)),
        open=float(k.get("o", 0.0)),
        high=float(k.get("h", 0.0)),
        low=float(k.get("l", 0.0)),
        close=float(k.get("c", 0.0)),
        volume=float(k.get("v", 0.0)),
        taker_buy_volume=float(k.get("V", 0.0)),
        quality=quality,
        available_at_ms=available_at_ms,
    )


def parse_agg_trade_payload(payload: dict[str, Any]) -> AggTradeData:
    """Parse Binance aggTrade payload into AggTradeData."""
    # Binance fields: a: agg_id, p: price, q: quantity, f: first_id, l: last_id, T: timestamp, m: is_buyer_maker
    return AggTradeData(
        aggregate_trade_id=int(payload.get("a", 0)),
        price=float(payload.get("p", 0.0)),
        quantity=float(payload.get("q", 0.0)),
        first_trade_id=int(payload.get("f", 0)),
        last_trade_id=int(payload.get("l", 0)),
        trade_time_ms=int(payload.get("T", 0)),
        is_buyer_maker=bool(payload.get("m", False)),
    )


def parse_funding_payload(payload: dict[str, Any]) -> SettledFundingData:
    """Parse settled official realized funding payload."""
    # Binance fields: E: event_time, T: funding_time, r: funding_rate, p: mark_price
    # Must be official settled event
    is_settled = bool(payload.get("settled", True))
    if payload.get("estimated", False) or not is_settled:
        return SettledFundingData(
            funding_time_ms=int(payload.get("T", 0)),
            funding_rate=float(payload.get("r", 0.0)),
            mark_price=float(payload.get("p", payload.get("markPrice", 0.0))),
            settled=False,
        )
    return SettledFundingData(
        funding_time_ms=int(payload.get("T", payload.get("funding_time_ms", 0))),
        funding_rate=float(payload.get("r", payload.get("funding_rate", 0.0))),
        mark_price=float(payload.get("p", payload.get("mark_price", 0.0))),
        settled=True,
    )
