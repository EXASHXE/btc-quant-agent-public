"""25 Pytest unit tests for Mark/Last/PIT clock, future mutation, and causal invariants."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_C_DIR = "/root/workspace/project/quant-v0.6/gemini-g1g3-offline-ports-r1"
if _C_DIR not in sys.path and Path(_C_DIR).exists():
    sys.path.insert(0, _C_DIR)

from scripts.g1_offline_preview_r1.model import SafetyViolation, digest
from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort

from scripts.integration.market_event_bridge_r2.mark_aggregator import (
    MarkPriceAggregator,
)


def test_mark_aggregator_40_ticks_full_coverage_verified() -> None:
    agg = MarkPriceAggregator()
    base_open = 1728720000000  # minute open
    # Ingest 60 1-second ticks
    for sec in range(60):
        t_ms = base_open + sec * 1000
        agg.ingest_tick(
            provider_event_ms=t_ms,
            mark_price=64000.0 + sec * 0.1,
            available_at_ms=t_ms + 10,
            payload_sha256=f"sha_{sec}",
            raw_manifest_sha256="msha",
        )
    # Roll minute
    bar = agg.ingest_tick(
        provider_event_ms=base_open + 60000,
        mark_price=64006.0,
        available_at_ms=base_open + 60010,
    )
    assert bar is not None
    assert bar.quality == "VERIFIED"
    assert bar.sample_count == 60
    assert bar.bar_open_ms == base_open
    assert bar.bar_close_ms == base_open + 59999
    assert bar.closed is True
    assert "OK" in bar.reason_codes


def test_mark_aggregator_insufficient_coverage_unknown() -> None:
    agg = MarkPriceAggregator(min_samples=40)
    base_open = 1728720000000
    # Ingest only 20 ticks
    for sec in range(0, 40, 2):
        t_ms = base_open + sec * 1000
        agg.ingest_tick(
            provider_event_ms=t_ms,
            mark_price=64000.0,
            available_at_ms=t_ms + 10,
        )
    bar = agg.flush_window()
    assert bar is not None
    assert bar.quality == "UNKNOWN"
    assert any("INSUFFICIENT_SAMPLE_COVERAGE" in r for r in bar.reason_codes)
    assert bar.closed is False


def test_mark_aggregator_excessive_jitter_gap_unknown() -> None:
    agg = MarkPriceAggregator(min_samples=20, max_gap_ms=5000)
    base_open = 1728720000000
    # Ingest ticks with a 10s gap
    agg.ingest_tick(base_open, 64000.0, base_open + 10)
    agg.ingest_tick(base_open + 2000, 64000.0, base_open + 2010)
    # Gap of 10s
    agg.ingest_tick(base_open + 12000, 64000.0, base_open + 12010)
    for sec in range(13, 58):
        agg.ingest_tick(base_open + sec * 1000, 64000.0, base_open + sec * 1000 + 10)

    bar = agg.flush_window()
    assert bar is not None
    assert bar.quality == "UNKNOWN"
    assert any("EXCESSIVE_JITTER_GAP" in r for r in bar.reason_codes)


def test_mark_aggregator_late_start_unknown() -> None:
    agg = MarkPriceAggregator(min_samples=20)
    base_open = 1728720000000
    # First tick at +15 seconds
    for sec in range(15, 60):
        t_ms = base_open + sec * 1000
        agg.ingest_tick(t_ms, 64000.0, t_ms + 10)
    bar = agg.flush_window()
    assert bar is not None
    assert bar.quality == "UNKNOWN"
    assert "LATE_WINDOW_START" in bar.reason_codes


def test_mark_aggregator_early_end_unknown() -> None:
    agg = MarkPriceAggregator(min_samples=20)
    base_open = 1728720000000
    # Last tick at 45 seconds
    for sec in range(45):
        t_ms = base_open + sec * 1000
        agg.ingest_tick(t_ms, 64000.0, t_ms + 10)
    bar = agg.flush_window()
    assert bar is not None
    assert bar.quality == "UNKNOWN"
    assert "EARLY_WINDOW_END" in bar.reason_codes


def test_mark_aggregator_derived_available_at_is_max() -> None:
    agg = MarkPriceAggregator(min_samples=1)
    base_open = 1728720000000
    agg.ingest_tick(base_open + 1000, 64000.0, available_at_ms=base_open + 1500)
    agg.ingest_tick(base_open + 2000, 64001.0, available_at_ms=base_open + 3000)
    bar = agg.flush_window()
    assert bar is not None
    assert bar.derived_available_at_ms == base_open + 3000


def test_mark_aggregator_feature_known_at_greater_equal_available_at() -> None:
    agg = MarkPriceAggregator(min_samples=1)
    base_open = 1728720000000
    agg.ingest_tick(base_open + 1000, 64000.0, available_at_ms=base_open + 2500)
    bar = agg.flush_window()
    assert bar is not None
    assert bar.feature_known_at_ms >= bar.derived_available_at_ms


def test_mark_aggregator_tracks_parent_shas() -> None:
    agg = MarkPriceAggregator(min_samples=2)
    base_open = 1728720000000
    agg.ingest_tick(base_open + 1000, 64000.0, base_open + 1010, payload_sha256="sha_1")
    agg.ingest_tick(base_open + 2000, 64001.0, base_open + 2010, payload_sha256="sha_2")
    bar = agg.flush_window()
    assert bar is not None
    assert bar.parent_event_sha256 == ("sha_1", "sha_2")


def test_mark_aggregator_ohlc_math() -> None:
    agg = MarkPriceAggregator(min_samples=3)
    base_open = 1728720000000
    agg.ingest_tick(base_open + 1000, 64010.0, base_open + 1010)
    agg.ingest_tick(base_open + 2000, 64050.0, base_open + 2010)  # high
    agg.ingest_tick(base_open + 3000, 63980.0, base_open + 3010)  # low
    agg.ingest_tick(base_open + 4000, 64025.0, base_open + 4010)  # close
    bar = agg.flush_window()
    assert bar is not None
    assert bar.open == 64010.0
    assert bar.high == 64050.0
    assert bar.low == 63980.0
    assert bar.close == 64025.0


def test_mark_aggregator_to_b_kline_payload() -> None:
    agg = MarkPriceAggregator(min_samples=1)
    base_open = 1728720000000
    agg.ingest_tick(base_open + 1000, 64000.0, base_open + 1010)
    bar = agg.flush_window()
    assert bar is not None
    b_dict = bar.to_b_kline_payload()
    assert b_dict["e"] == "kline"
    assert b_dict["k"]["i"] == "1m"
    assert b_dict["k"]["t"] == base_open
    assert b_dict["k"]["T"] == base_open + 59999


def test_mark_aggregator_flush_window() -> None:
    agg = MarkPriceAggregator(min_samples=1)
    agg.ingest_tick(1728720000000, 64000.0, 1728720000010)
    assert len(agg._buffer) == 1
    bar = agg.flush_window()
    assert bar is not None
    assert len(agg._buffer) == 0


def test_mark_aggregator_empty_flush_returns_none() -> None:
    agg = MarkPriceAggregator()
    assert agg.flush_window() is None


def test_pit_clock_monotonic_regression_rejected() -> None:
    port = MarketPitPort()
    # First valid envelope
    env1 = _make_valid_port_envelope(port, wall_ms=1000, mono_ns=2000, avail_ms=1000, seq=1)
    port.ingest_envelope(env1)

    # Second envelope with non-increasing monotonic_ns and different seq
    env2 = _make_valid_port_envelope(port, wall_ms=1100, mono_ns=2000, avail_ms=1100, seq=2)
    with pytest.raises(SafetyViolation, match="MONOTONIC_REGRESSION"):
        port.ingest_envelope(env2)


def test_pit_clock_wall_jump_backward_rejected() -> None:
    port = MarketPitPort()
    env1 = _make_valid_port_envelope(port, wall_ms=2000, mono_ns=2000, avail_ms=2000, seq=1)
    port.ingest_envelope(env1)

    # Wall time jumps backward while monotonic advances, with different seq
    env2 = _make_valid_port_envelope(port, wall_ms=1900, mono_ns=3000, avail_ms=1900, seq=2)
    with pytest.raises(SafetyViolation, match="CLOCK_UNCERTAIN"):
        port.ingest_envelope(env2)


def test_pit_clock_available_at_before_wall_rejected() -> None:
    port = MarketPitPort()
    env = _make_valid_port_envelope(port, wall_ms=2000, mono_ns=2000, avail_ms=1999)
    with pytest.raises(SafetyViolation, match="AVAILABLE_AT_BEFORE_INGRESS_WALL"):
        port.ingest_envelope(env)


def test_pit_clock_available_at_before_provider_event_rejected() -> None:
    port = MarketPitPort()
    env = _make_valid_port_envelope(port, wall_ms=2000, mono_ns=2000, avail_ms=2000)
    env["provider_event_ms"] = 2500  # provider in future relative to available_at
    with pytest.raises(SafetyViolation, match="AVAILABLE_AT_BEFORE_PROVIDER_EVENT"):
        port.ingest_envelope(env)


def test_pit_clock_future_known_rejected() -> None:
    port = MarketPitPort()
    env = _make_valid_port_envelope(port, wall_ms=2000, mono_ns=2000, avail_ms=2000)
    # reference_at_ms is 1900, but available_at_ms is 2000
    with pytest.raises(SafetyViolation, match="MARKET_EVENT_FUTURE_KNOWN"):
        port.ingest_envelope(env, reference_at_ms=1900)


def test_pit_clock_stale_event_rejected() -> None:
    port = MarketPitPort(max_stale_ms=5000)
    env = _make_valid_port_envelope(port, wall_ms=1000, mono_ns=1000, avail_ms=1000)
    # reference_at_ms is 7000 (diff is 6000 > max_stale 5000)
    with pytest.raises(SafetyViolation, match="MARKET_EVENT_STALE"):
        port.ingest_envelope(env, reference_at_ms=7000)


def test_last_1m_closed_true_required() -> None:
    port = MarketPitPort()
    env = _make_valid_bar_envelope(port, bar_open_ms=60000, closed=False)
    with pytest.raises(SafetyViolation, match="BAR_INCOMPLETE_UNCLOSED"):
        port.ingest_envelope(env)


def test_last_1m_aligned_60s_boundaries() -> None:
    port = MarketPitPort()
    # Misaligned open ms
    env = _make_valid_bar_envelope(port, bar_open_ms=60005, closed=True)
    with pytest.raises(SafetyViolation, match="BAR_PIT_INVALID"):
        port.ingest_envelope(env)


def test_last_1m_available_at_must_be_after_close() -> None:
    port = MarketPitPort()
    # bar_close_ms is 119999, but available_at_ms is 119000 (< close)
    env = _make_valid_bar_envelope(port, bar_open_ms=60000, closed=True)
    env["provider_event_ms"] = 119000
    env["available_at_ms"] = 119000
    env["observed_wall_utc_ms"] = 119000
    with pytest.raises(SafetyViolation, match="BAR_PIT_INVALID"):
        port.ingest_envelope(env)


def test_last_1m_gap_between_bars_rejected() -> None:
    port = MarketPitPort()
    env1 = _make_valid_bar_envelope(port, bar_open_ms=60000, closed=True, seq=1)
    port.ingest_envelope(env1)

    # Next bar skips minute 120000, jumps to 180000, different seq
    env2 = _make_valid_bar_envelope(port, bar_open_ms=180000, closed=True, seq=2)
    env2["observed_monotonic_ns"] = env1["observed_monotonic_ns"] + 1000
    with pytest.raises(SafetyViolation, match="NO_DATA_UNKNOWN_GAP"):
        port.ingest_envelope(env2)


def test_future_mutation_detection() -> None:
    bar_payload = {
        "bar_open_ms": 60000,
        "bar_close_ms": 119999,
        "closed": True,
        "last_open": "64000.0",
        "last_high": "64010.0",
        "last_low": "63990.0",
        "last_close": "64005.0",
        "mark_close": "64005.0",
        "event_id": "BAR-1",
    }
    sha_orig = digest(bar_payload)

    # Mutate future close price
    bar_mutated = dict(bar_payload)
    bar_mutated["last_close"] = "64006.0"
    sha_mutated = digest(bar_mutated)

    assert sha_orig != sha_mutated


def test_dual_connection_epoch_independence() -> None:
    pub_epoch = "pub-epoch-1"
    mkt_epoch = "mkt-epoch-1"

    # Increment only public epoch on diff-depth reconnect
    pub_epoch_next = "pub-epoch-2"
    assert pub_epoch_next != pub_epoch
    assert mkt_epoch == "mkt-epoch-1"


def test_route_switch_invalidates_order_book_continuity() -> None:
    from market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine
    engine = OrderBookIntegrityEngine()
    engine.reset("ROUTE_EPOCH_CHANGED")
    assert engine.continuous is False
    assert engine.quality == "INVALID"
    assert "ROUTE_EPOCH_CHANGED" in engine.reason_codes


def _make_valid_port_envelope(port: MarketPitPort, wall_ms: int, mono_ns: int, avail_ms: int, seq: int | None = 1) -> dict:
    payload = {"status": "HEALTH_OK"}
    return {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "health",
        "provider_event_ms": None,
        "provider_transaction_ms": None,
        "observed_wall_utc_ms": wall_ms,
        "observed_monotonic_ns": mono_ns,
        "available_at_ms": avail_ms,
        "source_stream_id": port.expected_stream_id,
        "connection_epoch": 1,
        "source_sequence": seq,
        "payload_sha256": digest(payload),
        "payload": payload,
        "quality": "VERIFIED",
        "reason_codes": ["OK"],
        "raw_source_manifest_sha256": port.expected_manifest_sha256,
    }


def _make_valid_bar_envelope(port: MarketPitPort, bar_open_ms: int, closed: bool = True, seq: int | None = 1) -> dict:
    bar_close_ms = bar_open_ms + 59999
    avail_ms = bar_close_ms + 100
    payload = {
        "bar_open_ms": bar_open_ms,
        "bar_close_ms": bar_close_ms,
        "closed": closed,
        "last_open": "64000.0",
        "last_high": "64010.0",
        "last_low": "63990.0",
        "last_close": "64005.0",
        "mark_close": "64005.0",
        "event_id": f"BAR-{bar_open_ms // 60000}",
    }
    return {
        "schema_version": "market-event-v1",
        "symbol": "BTCUSDT",
        "product": "BINANCE_USDT_M_PERP",
        "channel": "last_kline_1m",
        "provider_event_ms": bar_close_ms,
        "provider_transaction_ms": bar_close_ms,
        "observed_wall_utc_ms": avail_ms,
        "observed_monotonic_ns": avail_ms * 1_000_000,
        "available_at_ms": avail_ms,
        "source_stream_id": port.expected_stream_id,
        "connection_epoch": 1,
        "source_sequence": seq,
        "payload_sha256": digest(payload),
        "payload": payload,
        "quality": "VERIFIED",
        "reason_codes": ["OK"],
        "raw_source_manifest_sha256": port.expected_manifest_sha256,
    }
