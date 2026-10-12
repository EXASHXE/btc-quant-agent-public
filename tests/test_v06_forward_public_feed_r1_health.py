"""Tests for HealthSupervisor, channel staleness evaluation, and SOURCE_READY gating."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.health import HealthSupervisor
from market_data.forward_public_feed_r1.time_authority import TimeAuthority


def test_health_initial_state_awaiting_snapshot() -> None:
    hs = HealthSupervisor(symbol="BTCUSDT")
    gate, reasons = hs.evaluate_source_gate(current_wall_ms=1000)
    assert gate == "SOURCE_UNAVAILABLE"
    assert "BOOK_AWAITING_SNAPSHOT" in reasons


def test_health_source_ready_when_all_channels_fresh_and_book_verified() -> None:
    hs = HealthSupervisor(symbol="BTCUSDT")
    current_ms = 1_000_000

    hs.record_book_status(quality="VERIFIED", continuous=True, reason_codes=["OK"])
    hs.record_channel_event("mark_price", current_ms - 1000, {"p": "65000", "r": "0.0001"}, "VERIFIED")
    hs.record_channel_event("depth_delta", current_ms - 500, {"u": 100}, "VERIFIED")
    hs.record_channel_event("last_kline_1m", current_ms - 10_000, {"x": True}, "VERIFIED")

    gate, reasons = hs.evaluate_source_gate(current_wall_ms=current_ms)
    assert gate == "SOURCE_READY"
    assert reasons == ["OK"]


def test_health_stale_mark_price_causes_degraded() -> None:
    hs = HealthSupervisor(symbol="BTCUSDT")
    current_ms = 1_000_000

    hs.record_book_status(quality="VERIFIED", continuous=True, reason_codes=["OK"])
    # mark price is 15s old (> 10s threshold)
    hs.record_channel_event("mark_price", current_ms - 15_000, {"p": "65000"}, "VERIFIED")
    hs.record_channel_event("depth_delta", current_ms - 500, {"u": 100}, "VERIFIED")

    gate, reasons = hs.evaluate_source_gate(current_wall_ms=current_ms)
    assert gate == "SOURCE_DEGRADED"
    assert any("STALE_MARK_PRICE" in r for r in reasons)


def test_health_missing_depth_delta_causes_unavailable() -> None:
    hs = HealthSupervisor(symbol="BTCUSDT")
    current_ms = 1_000_000

    hs.record_book_status(quality="VERIFIED", continuous=True, reason_codes=["OK"])
    hs.record_channel_event("mark_price", current_ms - 1000, {"p": "65000"}, "VERIFIED")
    # depth_delta never recorded

    gate, reasons = hs.evaluate_source_gate(current_wall_ms=current_ms)
    assert gate == "SOURCE_UNAVAILABLE"
    assert "MISSING_DEPTH_DELTA" in reasons


def test_health_book_invalid_causes_unavailable() -> None:
    hs = HealthSupervisor(symbol="BTCUSDT")
    current_ms = 1_000_000

    hs.record_book_status(quality="INVALID", continuous=False, reason_codes=["GAP_DETECTED"])
    hs.record_channel_event("mark_price", current_ms - 1000, {"p": "65000"}, "VERIFIED")
    hs.record_channel_event("depth_delta", current_ms - 500, {"u": 100}, "VERIFIED")

    gate, reasons = hs.evaluate_source_gate(current_wall_ms=current_ms)
    assert gate == "SOURCE_UNAVAILABLE"
    assert "BOOK_DISCONTINUOUS_OR_INVALID" in reasons
    assert hs.book_gap_count == 1


def test_health_clock_uncertain_causes_degraded() -> None:
    ta = TimeAuthority(connection_epoch="test-epoch")
    # Force clock rollback
    ta.capture_ingress(override_wall_ms=5000, override_monotonic_ns=5_000_000_000)
    ta.capture_ingress(override_wall_ms=4000, override_monotonic_ns=5_100_000_000)

    hs = HealthSupervisor(symbol="BTCUSDT", time_authority=ta)
    current_ms = 10_000

    hs.record_book_status(quality="VERIFIED", continuous=True, reason_codes=["OK"])
    hs.record_channel_event("mark_price", current_ms - 1000, {"p": "65000"}, "VERIFIED")
    hs.record_channel_event("depth_delta", current_ms - 500, {"u": 100}, "VERIFIED")

    gate, reasons = hs.evaluate_source_gate(current_wall_ms=current_ms)
    assert gate == "SOURCE_DEGRADED"
    assert "CLOCK_UNCERTAIN" in reasons


def test_health_distinguishes_settled_from_estimated_funding() -> None:
    hs = HealthSupervisor(symbol="BTCUSDT")
    hs.record_channel_event(
        "funding_settled",
        wall_ms=1000,
        payload={"fundingRate": "0.00010000", "fundingTime": 1728720000000},
        quality="VERIFIED",
    )
    hs.record_channel_event(
        "mark_price",
        wall_ms=1050,
        payload={"r": "0.00015000", "T": 1728748800000},
        quality="VERIFIED",
    )

    assert hs.last_settled_funding_rate == "0.00010000"
    assert hs.latest_estimated_funding_rate == "0.00015000"

    event = hs.create_health_event(current_wall_ms=2000, raw_manifest_sha256="msha")
    assert event.channel == "health"
    payload = event.payload
    assert payload["settled_funding"]["rate"] == "0.00010000"
    assert payload["estimated_funding"]["rate"] == "0.00015000"
    assert payload["estimated_funding"]["status"] == "ESTIMATED_NOT_SETTLED"
