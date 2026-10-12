"""Deterministic tests for MarketEventV1, BookIntegrityV1, and wire contracts.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
import sys
from pathlib import Path

# Ensure repo root is on sys.path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from scripts.strategy_research.forward_shadow_research_r1.contract import (
    BookIntegrityV1,
    Channel,
    MarketEventV1,
    Quality,
    canonical_json,
    parse_agg_trade_payload,
    parse_funding_payload,
    parse_kline_payload,
    sha256_hex,
)


def test_canonical_json_deterministic():
    d1 = {"b": 2, "a": 1, "nested": {"y": 20, "x": 10}}
    d2 = {"nested": {"x": 10, "y": 20}, "a": 1, "b": 2}
    assert canonical_json(d1) == canonical_json(d2)
    assert canonical_json(d1) == b'{"a":1,"b":2,"nested":{"x":10,"y":20}}'


def test_market_event_valid_instantiation():
    payload = {"k": {"t": 1000, "T": 1059, "c": "65000.0", "x": True}}
    p_sha = sha256_hex(canonical_json(payload))
    event = MarketEventV1(
        channel=Channel.LAST_KLINE_1M,
        observed_wall_utc_ms=2000,
        observed_monotonic_ns=1000000,
        available_at_ms=2000,
        source_stream_id="test_stream",
        connection_epoch="1",
        payload_sha256=p_sha,
        payload=payload,
        quality=Quality.VERIFIED,
    )
    assert event.symbol == "BTCUSDT"
    assert event.product == "BINANCE_USDT_M_PERP"
    assert event.quality == Quality.VERIFIED
    d = event.to_dict()
    assert d["channel"] == "last_kline_1m"


def test_market_event_rejects_invalid_symbol():
    payload = {"foo": "bar"}
    p_sha = sha256_hex(canonical_json(payload))
    data = {
        "schema_version": "market-event-v1",
        "symbol": "ETHUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "last_kline_1m",
        "observed_wall_utc_ms": 1000,
        "observed_monotonic_ns": 1000,
        "available_at_ms": 1000,
        "source_stream_id": "stream",
        "connection_epoch": "1",
        "payload_sha256": p_sha,
        "payload": payload,
    }
    try:
        MarketEventV1.from_dict(data)
        assert False, "Should have raised ValueError for non-BTCUSDT symbol"
    except ValueError as e:
        assert "Only BTCUSDT admitted" in str(e)


def test_market_event_rejects_invalid_product():
    payload = {"foo": "bar"}
    p_sha = sha256_hex(canonical_json(payload))
    data = {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_COIN_M_PERP",
        "channel": "last_kline_1m",
        "observed_wall_utc_ms": 1000,
        "observed_monotonic_ns": 1000,
        "available_at_ms": 1000,
        "source_stream_id": "stream",
        "connection_epoch": "1",
        "payload_sha256": p_sha,
        "payload": payload,
    }
    try:
        MarketEventV1.from_dict(data)
        assert False, "Should have raised ValueError for invalid product"
    except ValueError as e:
        assert "Invalid product" in str(e)


def test_market_event_payload_sha_mismatch():
    payload = {"test": 123}
    data = {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "last_kline_1m",
        "observed_wall_utc_ms": 1000,
        "observed_monotonic_ns": 1000,
        "available_at_ms": 1000,
        "source_stream_id": "stream",
        "connection_epoch": "1",
        "payload_sha256": "fake_sha_does_not_match",
        "payload": payload,
        "quality": "VERIFIED",
    }
    ev = MarketEventV1.from_dict(data)
    assert ev.quality == Quality.INVALID
    assert "PAYLOAD_SHA256_MISMATCH" in ev.reason_codes


def test_market_event_available_before_wall_fails_closed():
    payload = {"foo": "bar"}
    p_sha = sha256_hex(canonical_json(payload))
    data = {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "last_kline_1m",
        "observed_wall_utc_ms": 2000,
        "observed_monotonic_ns": 1000,
        "available_at_ms": 1500,  # Available before wall clock observation!
        "source_stream_id": "stream",
        "connection_epoch": "1",
        "payload_sha256": p_sha,
        "payload": payload,
        "quality": "VERIFIED",
    }
    ev = MarketEventV1.from_dict(data)
    assert ev.quality == Quality.INVALID
    assert "AVAILABLE_BEFORE_WALL_INGRESS" in ev.reason_codes


def test_market_event_dedupe_key():
    payload = {"id": 9999, "price": 65000.0}
    p_sha = sha256_hex(canonical_json(payload))
    ev1 = MarketEventV1(
        channel=Channel.AGG_TRADE,
        observed_wall_utc_ms=1000,
        observed_monotonic_ns=100,
        available_at_ms=1000,
        source_stream_id="stream",
        connection_epoch="1",
        payload_sha256=p_sha,
        payload=payload,
        quality=Quality.VERIFIED,
    )
    ev2 = MarketEventV1(
        channel=Channel.AGG_TRADE,
        observed_wall_utc_ms=2000,  # Arrived later
        observed_monotonic_ns=200,
        available_at_ms=2000,
        source_stream_id="stream",
        connection_epoch="1",
        payload_sha256=p_sha,
        payload=payload,
        quality=Quality.VERIFIED,
    )
    assert ev1.dedupe_key() == ev2.dedupe_key()


def test_book_integrity_crossed_spread():
    book = BookIntegrityV1(
        best_bid=65001.0,
        best_ask=65000.0,  # Bid >= Ask: crossed!
        bids=((65001.0, 1.0),),
        asks=((65000.0, 1.0),),
    )
    qual, reasons = book.validate()
    assert qual == Quality.INVALID
    assert "CROSSED_SPREAD" in reasons


def test_book_integrity_negative_quotes():
    book = BookIntegrityV1(
        best_bid=-10.0,
        best_ask=65000.0,
    )
    qual, reasons = book.validate()
    assert qual == Quality.INVALID
    assert "INVALID_QUOTE_PRICE" in reasons


def test_book_integrity_depth_stale_over_1000ms():
    book = BookIntegrityV1(
        best_bid=65000.0,
        best_ask=65001.0,
        stale_age_ms=1050,  # > 1000ms stale
    )
    qual, reasons = book.validate()
    assert qual == Quality.DEGRADED
    assert "STALE_DEPTH_OVER_1000MS" in reasons


def test_book_integrity_discontinuous():
    book = BookIntegrityV1(
        best_bid=65000.0,
        best_ask=65001.0,
        continuous=False,
    )
    qual, reasons = book.validate()
    assert qual == Quality.DEGRADED
    assert "L2_DISCONTINUOUS" in reasons


def test_book_top_n_imbalance():
    bids = ((65000.0, 3.0), (64999.0, 2.0))
    asks = ((65001.0, 1.0), (65002.0, 1.0))
    book = BookIntegrityV1(
        best_bid=65000.0,
        best_ask=65001.0,
        bids=bids,
        asks=asks,
    )
    # bid notional = 65000*3 + 64999*2 = 195000 + 129998 = 324998
    # ask notional = 65001*1 + 65002*1 = 130003
    imb = book.top_n_imbalance(2)
    assert imb is not None
    assert imb > 0.40  # Heavy bid skew


def test_book_spread_bps():
    book = BookIntegrityV1(
        best_bid=65000.0,
        best_ask=65006.5,
    )
    spread = book.spread_bps(65000.0)
    assert spread is not None
    # 6.5 / 65000 * 10000 = 1.0 bp
    assert abs(spread - 1.0) < 1e-4


def test_stale_mark_price_detection():
    payload = {"p": "65000.0"}
    p_sha = sha256_hex(canonical_json(payload))
    data = {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "mark_price",
        "provider_event_ms": 10000,
        "observed_wall_utc_ms": 12500,  # 2500ms > 2000ms stale
        "observed_monotonic_ns": 1000,
        "available_at_ms": 12500,
        "source_stream_id": "stream",
        "connection_epoch": "1",
        "payload_sha256": p_sha,
        "payload": payload,
        "quality": "VERIFIED",
    }
    ev = MarketEventV1.from_dict(data)
    assert ev.quality == Quality.DEGRADED
    assert "STALE_MARK_OVER_2000MS" in ev.reason_codes


def test_parse_kline_payload():
    payload = {
        "k": {
            "t": 1700000000000,
            "T": 1700000059999,
            "o": "65000.0",
            "h": "65050.0",
            "l": "64990.0",
            "c": "65020.0",
            "v": "15.5",
            "x": True,
            "V": "8.0",
        }
    }
    bar = parse_kline_payload(payload)
    assert bar.bar_open_ms == 1700000000000
    assert bar.bar_close_ms == 1700000059999
    assert bar.closed is True
    assert bar.open == 65000.0
    assert bar.high == 65050.0
    assert bar.low == 64990.0
    assert bar.close == 65020.0
    assert bar.volume == 15.5
    assert bar.taker_buy_volume == 8.0


def test_parse_agg_trade_payload():
    payload = {
        "a": 123456,
        "p": "65100.5",
        "q": "1.25",
        "f": 100,
        "l": 102,
        "T": 1700000010000,
        "m": True,  # buyer maker => seller aggressor
    }
    trade = parse_agg_trade_payload(payload)
    assert trade.aggregate_trade_id == 123456
    assert trade.price == 65100.5
    assert trade.quantity == 1.25
    assert trade.is_buyer_maker is True


def test_parse_funding_payload_settled_vs_estimated():
    settled_payload = {
        "T": 1700000000000,
        "r": "0.0001",
        "p": "65000.0",
        "settled": True,
    }
    f_settled = parse_funding_payload(settled_payload)
    assert f_settled.settled is True
    assert f_settled.funding_rate == 0.0001

    est_payload = {
        "T": 1700000000000,
        "r": "0.0001",
        "p": "65000.0",
        "estimated": True,
        "settled": False,
    }
    f_est = parse_funding_payload(est_payload)
    assert f_est.settled is False
