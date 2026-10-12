"""Deterministic synthetic MarketEventV1 fixture generators for test and development suites.

Under B-line Controller Authority:
TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
from __future__ import annotations

from .contract import (
    BookIntegrityV1,
    Channel,
    MarketEventV1,
    Quality,
    canonical_json,
    sha256_hex,
)
from .signals import AggregatedBar


def make_test_book(
    best_bid: float = 65000.0,
    best_ask: float = 65001.0,
    depth_levels: int = 10,
    stale_age_ms: int = 50,
    continuous: bool = True,
    quality: Quality = Quality.VERIFIED,
    bids_skew: float = 1.0,
    asks_skew: float = 1.0,
) -> BookIntegrityV1:
    """Generate deterministic BookIntegrityV1 fixture."""
    bids: list[tuple[float, float]] = []
    asks: list[tuple[float, float]] = []
    for i in range(depth_levels):
        bp = best_bid - (i * 0.5)
        bq = (1.0 + (i * 0.1)) * bids_skew
        ap = best_ask + (i * 0.5)
        aq = (1.0 + (i * 0.1)) * asks_skew
        bids.append((bp, bq))
        asks.append((ap, aq))

    return BookIntegrityV1(
        snapshot_update_id=1000,
        first_update_id=1001,
        final_update_id=1010,
        previous_final_update_id=1000,
        continuous=continuous,
        best_bid=best_bid,
        best_ask=best_ask,
        bids=tuple(bids),
        asks=tuple(asks),
        observed_depth_levels=len(bids) + len(asks),
        stale_age_ms=stale_age_ms,
        quality=quality,
        reason_codes=(),
    )


def make_kline_event(
    channel: Channel,
    bar_open_ms: int,
    bar_close_ms: int,
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    volume: float = 10.0,
    closed: bool = True,
    observed_wall_utc_ms: int | None = None,
    observed_monotonic_ns: int = 1_000_000_000,
    available_at_ms: int | None = None,
    quality: Quality = Quality.VERIFIED,
) -> MarketEventV1:
    """Generate deterministic MarketEventV1 for last_kline_1m or mark_price."""
    obs_wall = observed_wall_utc_ms if observed_wall_utc_ms is not None else bar_close_ms + 5
    avail_ms = available_at_ms if available_at_ms is not None else obs_wall

    payload = {
        "k": {
            "t": bar_open_ms,
            "T": bar_close_ms,
            "s": "BTCUSDT",
            "i": "1m",
            "o": str(open_price),
            "h": str(high_price),
            "l": str(low_price),
            "c": str(close_price),
            "v": str(volume),
            "x": closed,
            "V": str(volume * 0.5),
        }
    }
    payload_bytes = canonical_json(payload)

    return MarketEventV1(
        channel=channel,
        provider_event_ms=bar_close_ms,
        provider_transaction_ms=bar_close_ms,
        observed_wall_utc_ms=obs_wall,
        observed_monotonic_ns=observed_monotonic_ns,
        available_at_ms=avail_ms,
        source_stream_id=f"stream_{channel.value}",
        connection_epoch="1",
        source_sequence=1,
        payload_sha256=sha256_hex(payload_bytes),
        payload=payload,
        quality=quality,
        raw_source_manifest_sha256="raw_manifest_hash",
    )


def make_agg_trade_event(
    trade_id: int,
    trade_time_ms: int,
    price: float,
    quantity: float,
    is_buyer_maker: bool,
    observed_wall_utc_ms: int | None = None,
    observed_monotonic_ns: int = 1_000_000_000,
) -> MarketEventV1:
    """Generate deterministic MarketEventV1 for agg_trade."""
    obs_wall = observed_wall_utc_ms if observed_wall_utc_ms is not None else trade_time_ms + 2
    payload = {
        "e": "aggTrade",
        "E": trade_time_ms,
        "s": "BTCUSDT",
        "a": trade_id,
        "p": str(price),
        "q": str(quantity),
        "f": trade_id * 10,
        "l": trade_id * 10 + 1,
        "T": trade_time_ms,
        "m": is_buyer_maker,
    }
    payload_bytes = canonical_json(payload)

    return MarketEventV1(
        channel=Channel.AGG_TRADE,
        provider_event_ms=trade_time_ms,
        provider_transaction_ms=trade_time_ms,
        observed_wall_utc_ms=obs_wall,
        observed_monotonic_ns=observed_monotonic_ns,
        available_at_ms=obs_wall,
        source_stream_id="stream_agg_trade",
        connection_epoch="1",
        source_sequence=trade_id,
        payload_sha256=sha256_hex(payload_bytes),
        payload=payload,
        quality=Quality.VERIFIED,
        raw_source_manifest_sha256="raw_manifest_hash",
    )


def make_funding_settled_event(
    funding_time_ms: int,
    funding_rate: float,
    mark_price: float,
    observed_wall_utc_ms: int | None = None,
    observed_monotonic_ns: int = 1_000_000_000,
    settled: bool = True,
) -> MarketEventV1:
    """Generate deterministic MarketEventV1 for funding_settled."""
    obs_wall = observed_wall_utc_ms if observed_wall_utc_ms is not None else funding_time_ms + 5
    payload = {
        "e": "markPriceUpdate",
        "E": funding_time_ms,
        "s": "BTCUSDT",
        "p": str(mark_price),
        "r": str(funding_rate),
        "T": funding_time_ms,
        "settled": settled,
    }
    payload_bytes = canonical_json(payload)

    return MarketEventV1(
        channel=Channel.FUNDING_SETTLED,
        provider_event_ms=funding_time_ms,
        provider_transaction_ms=funding_time_ms,
        observed_wall_utc_ms=obs_wall,
        observed_monotonic_ns=observed_monotonic_ns,
        available_at_ms=obs_wall,
        source_stream_id="stream_funding",
        connection_epoch="1",
        source_sequence=1,
        payload_sha256=sha256_hex(payload_bytes),
        payload=payload,
        quality=Quality.VERIFIED,
        raw_source_manifest_sha256="raw_manifest_hash",
    )


def generate_warmup_hourly_bars(
    start_time_ms: int,
    hours_count: int = 210,
    base_price: float = 65000.0,
    hourly_vol: float = 50.0,
) -> list[AggregatedBar]:
    """Generate continuous prefix of 1h bars with no gaps for ATR(14) warmup."""
    bars: list[AggregatedBar] = []
    hour_ms = 3600 * 1000
    current_time = start_time_ms
    price = base_price

    for i in range(hours_count):
        bar_open = current_time
        bar_close = current_time + hour_ms - 1
        high = price + hourly_vol
        low = price - hourly_vol
        close = price + (hourly_vol * 0.1)

        bars.append(
            AggregatedBar(
                bar_open_ms=bar_open,
                bar_close_ms=bar_close,
                open=price,
                high=high,
                low=low,
                close=close,
                volume=100.0,
                is_complete=True,
                bar_count=60,
            )
        )
        current_time += hour_ms
        price = close

    return bars
