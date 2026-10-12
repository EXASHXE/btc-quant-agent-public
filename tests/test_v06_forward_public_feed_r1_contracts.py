"""Tests for semantic contracts, MarketEventV1, BookIntegrityV1, and deterministic serialization."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

# Ensure scripts directory is on sys.path
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.contracts import (
    ALLOWED_PRODUCT,
    ALLOWED_SYMBOL,
    CHANNELS,
    QUALITY_LEVELS,
    SCHEMA_VERSION,
    BookIntegrityV1,
    ContractValidationError,
    MarketEventV1,
    canonical_json_bytes,
    compute_dedupe_key,
    compute_sha256,
)
from market_data.forward_public_feed_r1.fixture import DeterministicExchangeFixture


def test_schema_version_and_product_constants() -> None:
    assert SCHEMA_VERSION == "market-event-v1"
    assert ALLOWED_PRODUCT == "BINANCE_USDT_M_PERP"
    assert ALLOWED_SYMBOL == "BTCUSDT"
    assert "last_kline_1m" in CHANNELS
    assert "mark_price" in CHANNELS
    assert "agg_trade" in CHANNELS
    assert "depth_delta" in CHANNELS
    assert "depth_snapshot" in CHANNELS
    assert "funding_settled" in CHANNELS
    assert "health" in CHANNELS
    assert "VERIFIED" in QUALITY_LEVELS


def test_canonical_json_determinism() -> None:
    d1 = {"b": 2, "a": 1, "nested": {"z": 100, "y": 50}}
    d2 = {"nested": {"y": 50, "z": 100}, "a": 1, "b": 2}
    raw1 = canonical_json_bytes(d1)
    raw2 = canonical_json_bytes(d2)
    assert raw1 == raw2
    assert b" " not in raw1  # No space after comma/colon
    assert raw1 == b'{"a":1,"b":2,"nested":{"y":50,"z":100}}'


def test_sha256_determinism() -> None:
    d1 = {"symbol": "BTCUSDT", "price": "65000.00"}
    d2 = {"price": "65000.00", "symbol": "BTCUSDT"}
    sha1 = compute_sha256(d1)
    sha2 = compute_sha256(d2)
    assert sha1 == sha2
    assert len(sha1) == 64


def test_dedupe_key_generation() -> None:
    k1 = compute_dedupe_key("BTCUSDT", "agg_trade", "epoch-1", "trade-999")
    k2 = compute_dedupe_key("BTCUSDT", "agg_trade", "epoch-1", "trade-999")
    k3 = compute_dedupe_key("BTCUSDT", "agg_trade", "epoch-2", "trade-999")
    assert k1 == k2
    assert k1 != k3


def test_market_event_v1_valid_instantiation() -> None:
    payload = {"price": "65000.00", "quantity": "0.150"}
    payload_sha = compute_sha256(payload)
    event = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product="BINANCE_USDT_M_PERP",
        channel="agg_trade",
        provider_event_ms=1728720000000,
        provider_transaction_ms=1728719999999,
        observed_wall_utc_ms=1728720000010,
        observed_monotonic_ns=1000000000,
        available_at_ms=1728720000010,
        source_stream_id="btcusdt@aggTrade",
        connection_epoch="epoch-1",
        source_sequence=12345,
        payload_sha256=payload_sha,
        payload=payload,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="manifest_sha_001",
    )
    assert event.symbol == "BTCUSDT"
    assert event.channel == "agg_trade"
    assert len(event.event_sha256()) == 64
    assert len(event.dedupe_key()) == 64


def test_market_event_v1_rejects_wrong_schema_version() -> None:
    payload = {"p": "65000"}
    with pytest.raises(ContractValidationError, match="schema_version"):
        MarketEventV1(
            schema_version="market-event-v2",
            symbol="BTCUSDT",
            product="BINANCE_USDT_M_PERP",
            channel="agg_trade",
            provider_event_ms=1728720000000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1728720000010,
            observed_monotonic_ns=1000000000,
            available_at_ms=1728720000010,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-1",
            source_sequence=1,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="msha",
        )


def test_market_event_v1_rejects_wrong_product() -> None:
    payload = {"p": "65000"}
    with pytest.raises(ContractValidationError, match="product"):
        MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product="BINANCE_SPOT",
            channel="agg_trade",
            provider_event_ms=1728720000000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1728720000010,
            observed_monotonic_ns=1000000000,
            available_at_ms=1728720000010,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-1",
            source_sequence=1,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="msha",
        )


def test_market_event_v1_rejects_wrong_symbol() -> None:
    payload = {"p": "65000"}
    with pytest.raises(ContractValidationError, match="symbol"):
        MarketEventV1(
            schema_version="market-event-v1",
            symbol="btcusdt",  # Must be uppercase BTCUSDT
            product="BINANCE_USDT_M_PERP",
            channel="agg_trade",
            provider_event_ms=1728720000000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1728720000010,
            observed_monotonic_ns=1000000000,
            available_at_ms=1728720000010,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-1",
            source_sequence=1,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="msha",
        )


def test_market_event_v1_rejects_unknown_channel() -> None:
    payload = {"p": "65000"}
    with pytest.raises(ContractValidationError, match="channel"):
        MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product="BINANCE_USDT_M_PERP",
            channel="private_order_fill",
            provider_event_ms=1728720000000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1728720000010,
            observed_monotonic_ns=1000000000,
            available_at_ms=1728720000010,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-1",
            source_sequence=1,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="msha",
        )


def test_market_event_v1_rejects_invalid_quality() -> None:
    payload = {"p": "65000"}
    with pytest.raises(ContractValidationError, match="quality"):
        MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product="BINANCE_USDT_M_PERP",
            channel="agg_trade",
            provider_event_ms=1728720000000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1728720000010,
            observed_monotonic_ns=1000000000,
            available_at_ms=1728720000010,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-1",
            source_sequence=1,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="SUPERB",
            reason_codes=["OK"],
            raw_source_manifest_sha256="msha",
        )


def test_market_event_v1_rejects_future_available_at_earlier_than_observed_wall() -> None:
    payload = {"p": "65000"}
    with pytest.raises(ContractValidationError, match="available_at_ms"):
        MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product="BINANCE_USDT_M_PERP",
            channel="agg_trade",
            provider_event_ms=1728720000000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1728720000500,
            observed_monotonic_ns=1000000000,
            available_at_ms=1728720000100,  # Earlier than observed_wall_utc_ms!
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-1",
            source_sequence=1,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="msha",
        )


def test_market_event_v1_rejects_payload_sha_mismatch() -> None:
    payload = {"p": "65000"}
    with pytest.raises(ContractValidationError, match="payload_sha256 mismatch"):
        MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product="BINANCE_USDT_M_PERP",
            channel="agg_trade",
            provider_event_ms=1728720000000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1728720000100,
            observed_monotonic_ns=1000000000,
            available_at_ms=1728720000100,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-1",
            source_sequence=1,
            payload_sha256="wrong_payload_sha_1234567890",
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="msha",
        )


def test_market_event_v1_rejects_forbidden_private_keywords() -> None:
    payload = {"p": "65000", "apiKey": "forbidden_key_123"}
    with pytest.raises(ContractValidationError, match="Forbidden private identifier"):
        MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product="BINANCE_USDT_M_PERP",
            channel="agg_trade",
            provider_event_ms=1728720000000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1728720000100,
            observed_monotonic_ns=1000000000,
            available_at_ms=1728720000100,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-1",
            source_sequence=1,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="msha",
        )


def test_book_integrity_valid() -> None:
    book = BookIntegrityV1(
        snapshot_update_id=1000,
        first_update_id=1001,
        final_update_id=1005,
        previous_final_update_id=1000,
        continuous=True,
        best_bid="65000.00",
        best_ask="65000.50",
        observed_depth_levels=20,
        stale_age_ms=15,
        quality="VERIFIED",
        reason_codes=["OK"],
    )
    assert book.continuous is True
    assert book.best_bid == "65000.00"
    assert book.best_ask == "65000.50"


def test_book_integrity_crossed_book_rejection() -> None:
    with pytest.raises(ContractValidationError, match="Crossed book detected"):
        BookIntegrityV1(
            snapshot_update_id=1000,
            first_update_id=1001,
            final_update_id=1005,
            previous_final_update_id=1000,
            continuous=True,
            best_bid="65001.00",
            best_ask="65000.50",  # Bid > Ask!
            observed_depth_levels=20,
            stale_age_ms=15,
            quality="VERIFIED",
            reason_codes=["OK"],
        )


def test_book_integrity_negative_prices_rejection() -> None:
    with pytest.raises(ContractValidationError, match="positive"):
        BookIntegrityV1(
            snapshot_update_id=1000,
            first_update_id=1001,
            final_update_id=1005,
            previous_final_update_id=1000,
            continuous=True,
            best_bid="-10.00",
            best_ask="65000.50",
            observed_depth_levels=20,
            stale_age_ms=15,
            quality="VERIFIED",
            reason_codes=["OK"],
        )


def test_book_integrity_negative_stale_age_rejection() -> None:
    with pytest.raises(ContractValidationError, match="stale_age_ms"):
        BookIntegrityV1(
            snapshot_update_id=1000,
            first_update_id=1001,
            final_update_id=1005,
            previous_final_update_id=1000,
            continuous=True,
            best_bid="65000.00",
            best_ask="65000.50",
            observed_depth_levels=20,
            stale_age_ms=-1,
            quality="VERIFIED",
            reason_codes=["OK"],
        )


def test_book_integrity_to_from_dict() -> None:
    book = BookIntegrityV1(
        snapshot_update_id=1000,
        first_update_id=1001,
        final_update_id=1005,
        previous_final_update_id=1000,
        continuous=True,
        best_bid="65000.00",
        best_ask="65000.50",
        observed_depth_levels=20,
        stale_age_ms=15,
        quality="VERIFIED",
        reason_codes=["OK"],
    )
    d = book.to_dict()
    book2 = BookIntegrityV1.from_dict(d)
    assert book == book2


def test_market_event_v1_to_from_dict() -> None:
    payload = {"price": "65000.00"}
    event = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product="BINANCE_USDT_M_PERP",
        channel="agg_trade",
        provider_event_ms=1728720000000,
        provider_transaction_ms=None,
        observed_wall_utc_ms=1728720000010,
        observed_monotonic_ns=1000000000,
        available_at_ms=1728720000010,
        source_stream_id="btcusdt@aggTrade",
        connection_epoch="epoch-1",
        source_sequence=123,
        payload_sha256=compute_sha256(payload),
        payload=payload,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="msha",
    )
    d = event.to_dict()
    event2 = MarketEventV1.from_dict(d)
    assert event == event2
    assert event.canonical_json() == event2.canonical_json()


def test_market_event_v1_with_book() -> None:
    payload = {"e": "depthUpdate", "u": 1005}
    book = BookIntegrityV1(
        snapshot_update_id=1000,
        first_update_id=1001,
        final_update_id=1005,
        previous_final_update_id=1000,
        continuous=True,
        best_bid="65000.00",
        best_ask="65000.50",
        observed_depth_levels=20,
        stale_age_ms=5,
        quality="VERIFIED",
        reason_codes=["OK"],
    )
    event = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product="BINANCE_USDT_M_PERP",
        channel="depth_delta",
        provider_event_ms=1728720000000,
        provider_transaction_ms=1728719999999,
        observed_wall_utc_ms=1728720000010,
        observed_monotonic_ns=1000000000,
        available_at_ms=1728720000010,
        source_stream_id="btcusdt@depth@100ms",
        connection_epoch="epoch-1",
        source_sequence=1005,
        payload_sha256=compute_sha256(payload),
        payload=payload,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="msha",
        book=book,
    )
    assert event.book is not None
    assert event.book.best_bid == "65000.00"
    d = event.to_dict()
    event2 = MarketEventV1.from_dict(d)
    assert event == event2


def test_fixture_generator_kline_output() -> None:
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    frame = fix.generate_kline_frame(interval="1m", closed=False)
    assert frame["e"] == "kline"
    assert frame["s"] == "BTCUSDT"
    assert frame["k"]["i"] == "1m"
    assert frame["k"]["x"] is False

    closed_frame = fix.generate_kline_frame(interval="1m", closed=True)
    assert closed_frame["k"]["x"] is True


def test_fixture_generator_mark_price_output() -> None:
    fix = DeterministicExchangeFixture()
    frame = fix.generate_mark_price_frame()
    assert frame["e"] == "markPriceUpdate"
    assert frame["s"] == "BTCUSDT"
    assert "r" in frame
    assert "p" in frame
    assert "i" in frame


def test_fixture_generator_agg_trade_output() -> None:
    fix = DeterministicExchangeFixture()
    frame = fix.generate_agg_trade_frame(price_offset=Decimal("1.25"), quantity=Decimal("0.500"), buyer_is_maker=True)
    assert frame["e"] == "aggTrade"
    assert frame["m"] is True
    assert frame["p"] == "65001.25"
    assert frame["q"] == "0.500"


def test_fixture_generator_depth_snapshot_output() -> None:
    fix = DeterministicExchangeFixture()
    snap = fix.generate_depth_snapshot_frame(levels=10)
    assert "lastUpdateId" in snap
    assert len(snap["bids"]) == 10
    assert len(snap["asks"]) == 10
    # bids descending
    assert float(snap["bids"][0][0]) > float(snap["bids"][1][0])
    # asks ascending
    assert float(snap["asks"][0][0]) < float(snap["asks"][1][0])


def test_fixture_generator_depth_delta_output() -> None:
    fix = DeterministicExchangeFixture()
    snap = fix.generate_depth_snapshot_frame()
    delta = fix.generate_depth_delta_frame(span=5)
    assert delta["e"] == "depthUpdate"
    assert delta["pu"] == snap["lastUpdateId"]
    assert delta["U"] == snap["lastUpdateId"] + 1
    assert delta["u"] == snap["lastUpdateId"] + 6


def test_fixture_generator_settled_funding_output() -> None:
    fix = DeterministicExchangeFixture()
    funding = fix.generate_settled_funding_frame()
    assert funding["symbol"] == "BTCUSDT"
    assert "fundingRate" in funding
    assert "fundingTime" in funding
