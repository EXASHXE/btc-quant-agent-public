"""Tests for BinancePublicFeedClient, URL security validation, AST methods, and frame mapping."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.connector import (
    BinancePublicFeedClient,
    NetworkGateError,
    validate_public_url,
)
from market_data.forward_public_feed_r1.contracts import ContractValidationError
from market_data.forward_public_feed_r1.fixture import DeterministicExchangeFixture


def test_network_default_forbidden() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    with pytest.raises(NetworkGateError, match="Network access blocked"):
        client.fetch_public_depth_snapshot()

    with pytest.raises(NetworkGateError, match="Network access blocked"):
        client.fetch_latest_settled_funding()


def test_validate_public_url_official_endpoints() -> None:
    # Valid USDⓈ-M endpoints
    validate_public_url("https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT", method="GET")
    validate_public_url("wss://fstream.binance.com/stream?streams=btcusdt@aggTrade", method="GET")


def test_validate_public_url_blocks_coin_m() -> None:
    # COIN-M endpoint dapi.binance.com is strictly forbidden
    with pytest.raises(ContractValidationError, match="Forbidden host 'dapi.binance.com'"):
        validate_public_url("https://dapi.binance.com/dapi/v1/depth?symbol=BTCUSD_PERP", method="GET")


def test_validate_public_url_blocks_spot() -> None:
    # Spot endpoint api.binance.com is strictly forbidden
    with pytest.raises(ContractValidationError, match="Forbidden host 'api.binance.com'"):
        validate_public_url("https://api.binance.com/api/v3/depth?symbol=BTCUSDT", method="GET")


def test_validate_public_url_blocks_post_put_delete() -> None:
    with pytest.raises(ContractValidationError, match="Method 'POST' forbidden"):
        validate_public_url("https://fapi.binance.com/fapi/v1/depth", method="POST")

    with pytest.raises(ContractValidationError, match="Method 'DELETE' forbidden"):
        validate_public_url("https://fapi.binance.com/fapi/v1/depth", method="DELETE")

    with pytest.raises(ContractValidationError, match="Method 'PUT' forbidden"):
        validate_public_url("https://fapi.binance.com/fapi/v1/depth", method="PUT")


def test_validate_public_url_blocks_private_keywords() -> None:
    # Private order endpoints
    with pytest.raises(ContractValidationError, match="Forbidden keyword 'order'"):
        validate_public_url("https://fapi.binance.com/fapi/v1/order?symbol=BTCUSDT", method="GET")

    # Private listenKey endpoint
    with pytest.raises(ContractValidationError, match="Forbidden keyword 'listenkey'"):
        validate_public_url("https://fapi.binance.com/fapi/v1/listenKey", method="GET")


def test_connector_rejects_case_sensitive_symbol_confusion() -> None:
    with pytest.raises(ContractValidationError, match="Symbol 'btcusdt' invalid"):
        BinancePublicFeedClient(symbol="btcusdt", network_mode="disabled")

    with pytest.raises(ContractValidationError, match="Symbol 'ETHUSDT' invalid"):
        BinancePublicFeedClient(symbol="ETHUSDT", network_mode="disabled")


def test_map_raw_frame_kline() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    kline_frame = fix.generate_kline_frame(interval="1m", closed=True)
    import json
    raw_str = json.dumps(kline_frame)

    event = client.map_raw_frame_to_event(
        raw_msg=raw_str,
        observed_wall_ms=1728720000050,
        observed_monotonic_ns=1000000000,
        raw_manifest_sha256="msha",
    )
    assert event is not None
    assert event.channel == "last_kline_1m"
    assert event.payload["k"]["x"] is True
    assert event.symbol == "BTCUSDT"


def test_map_raw_frame_mark_price() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    frame = fix.generate_mark_price_frame()
    import json
    raw_str = json.dumps(frame)

    event = client.map_raw_frame_to_event(
        raw_msg=raw_str,
        observed_wall_ms=1728720000050,
        observed_monotonic_ns=1000000000,
        raw_manifest_sha256="msha",
    )
    assert event is not None
    assert event.channel == "mark_price"
    assert "r" in event.payload


def test_map_raw_frame_agg_trade() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    frame = fix.generate_agg_trade_frame(price_offset=Decimal("1.00"), buyer_is_maker=True)
    import json
    raw_str = json.dumps(frame)

    event = client.map_raw_frame_to_event(
        raw_msg=raw_str,
        observed_wall_ms=1728720000050,
        observed_monotonic_ns=1000000000,
        raw_manifest_sha256="msha",
    )
    assert event is not None
    assert event.channel == "agg_trade"
    assert event.payload["m"] is True


def test_map_raw_frame_depth_delta() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)
    client.book_engine.apply_snapshot(snap, 1728720000000)

    delta = fix.generate_depth_delta_frame(span=2, force_pu=1000)
    import json
    raw_str = json.dumps(delta)

    event = client.map_raw_frame_to_event(
        raw_msg=raw_str,
        observed_wall_ms=1728720000050,
        observed_monotonic_ns=1000000000,
        raw_manifest_sha256="msha",
    )
    assert event is not None
    assert event.channel == "depth_delta"
    assert event.book is not None
    assert event.book.continuous is True


def test_map_raw_frame_corrupt_json_returns_none() -> None:
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    event = client.map_raw_frame_to_event(
        raw_msg="broken_non_json_data",
        observed_wall_ms=1000,
        observed_monotonic_ns=1000,
        raw_manifest_sha256="msha",
    )
    assert event is None


def test_run_bounded_public_stream_unreachable_network_reports_gracefully() -> None:
    async def _test() -> None:
        client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="allow-public")
        # Mock snapshot fetch failure (e.g. simulated network geoblock / unreachable)
        with patch.object(client, "fetch_public_depth_snapshot", side_effect=OSError("Geoblocked: 403 Forbidden")):
            stats = await client.run_bounded_public_stream(duration_seconds=1)
            assert stats["status"] == "NOT_TESTED_SOURCE_UNREACHABLE"
            assert "403 Forbidden" in stats["error"]

    import asyncio
    asyncio.run(_test())
