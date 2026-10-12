"""Tests for OrderBookIntegrityEngine depth bridging, gap detection, and invariants."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.fixture import DeterministicExchangeFixture
from market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine


def test_unbootstrapped_book_state() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    receipt = engine.get_integrity_receipt(current_wall_ms=1000)
    assert receipt.quality == "UNKNOWN"
    assert receipt.continuous is False
    assert receipt.best_bid is None
    assert receipt.best_ask is None
    assert receipt.snapshot_update_id is None
    assert "AWAITING_SNAPSHOT" in receipt.reason_codes


def test_snapshot_application_normal() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT", base_price=Decimal("65000.00"))
    snap = fix.generate_depth_snapshot_frame(levels=10)

    receipt = engine.apply_snapshot(snap, observed_wall_ms=1728720000000)
    assert receipt.quality == "VERIFIED"
    assert receipt.continuous is True
    assert receipt.snapshot_update_id == snap["lastUpdateId"]
    assert receipt.best_bid is not None
    assert receipt.best_ask is not None
    assert Decimal(receipt.best_bid) < Decimal(receipt.best_ask)
    assert receipt.observed_depth_levels == 20


def test_snapshot_crossed_book_fail_closed() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 12345,
        "bids": [["65005.00", "1.0"]],
        "asks": [["65000.00", "1.0"]],  # Best bid > best ask!
    }
    receipt = engine.apply_snapshot(snap, observed_wall_ms=1728720000000)
    assert receipt.quality == "INVALID"
    assert receipt.continuous is False
    assert "SNAPSHOT_CROSSED_BOOK" in receipt.reason_codes


def test_snapshot_negative_price_fail_closed() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 12345,
        "bids": [["-10.00", "1.0"]],
        "asks": [["65000.00", "1.0"]],
    }
    receipt = engine.apply_snapshot(snap, observed_wall_ms=1728720000000)
    assert receipt.quality == "INVALID"
    assert receipt.continuous is False


def test_snapshot_negative_quantity_fail_closed() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 12345,
        "bids": [["64000.00", "-1.0"]],
        "asks": [["65000.00", "1.0"]],
    }
    receipt = engine.apply_snapshot(snap, observed_wall_ms=1728720000000)
    assert receipt.quality == "INVALID"
    assert receipt.continuous is False


def test_snapshot_missing_last_update_id() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "bids": [["64000.00", "1.0"]],
        "asks": [["65000.00", "1.0"]],
    }
    receipt = engine.apply_snapshot(snap, observed_wall_ms=1728720000000)
    assert receipt.quality == "INVALID"
    assert "INVALID_SNAPSHOT_MISSING_LAST_UPDATE_ID" in receipt.reason_codes


def test_buffered_deltas_applied_after_snapshot() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")

    # Generate snap with lastUpdateId = 1000
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)

    # Buffer delta that bridges snapshot
    delta = {
        "e": "depthUpdate",
        "E": 1728720000010,
        "s": "BTCUSDT",
        "U": 1000,
        "u": 1005,
        "pu": 999,
        "b": [["64999.00", "5.000"]],
        "a": [["65001.00", "4.000"]],
    }
    engine.buffer_delta(delta)

    # Now apply snapshot -> should auto drain and bridge delta
    receipt = engine.apply_snapshot(snap, observed_wall_ms=1728720000000)
    assert receipt.quality == "VERIFIED"
    assert receipt.final_update_id == 1005
    assert engine.bids[Decimal("64999.00")] == Decimal("5.000")


def test_delta_stale_dropped_before_snapshot_id() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)
    engine.apply_snapshot(snap, observed_wall_ms=1728720000000)

    # Delta with u < snapshot_update_id
    stale_delta = {
        "e": "depthUpdate",
        "U": 990,
        "u": 995,
        "pu": 989,
        "b": [["64000.00", "1.0"]],
        "a": [],
    }
    receipt = engine.apply_delta(stale_delta, observed_wall_ms=1728720000010)
    assert receipt.final_update_id == 1000  # Not updated
    assert Decimal("64000.00") not in engine.bids


def test_first_delta_bridging_valid_range() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)
    engine.apply_snapshot(snap, observed_wall_ms=1728720000000)

    # First event has U <= 1000 <= u
    delta = {
        "e": "depthUpdate",
        "U": 998,
        "u": 1002,
        "pu": 997,
        "b": [["64998.00", "3.000"]],
        "a": [],
    }
    receipt = engine.apply_delta(delta, observed_wall_ms=1728720000020)
    assert receipt.quality == "VERIFIED"
    assert receipt.final_update_id == 1002
    assert receipt.first_update_id == 998


def test_first_delta_gap_detected() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)
    engine.apply_snapshot(snap, observed_wall_ms=1728720000000)

    # First event has U > lastUpdateId + 1 (e.g. 1005 > 1001) -> gap!
    gap_delta = {
        "e": "depthUpdate",
        "U": 1005,
        "u": 1010,
        "pu": 1004,
        "b": [["64998.00", "3.000"]],
        "a": [],
    }
    receipt = engine.apply_delta(gap_delta, observed_wall_ms=1728720000020)
    assert receipt.quality == "INVALID"
    assert receipt.continuous is False
    assert any("GAP_SNAPSHOT_TO_STREAM" in r for r in receipt.reason_codes)


def test_subsequent_delta_pu_continuity() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)
    engine.apply_snapshot(snap, observed_wall_ms=1728720000000)

    d1 = {"e": "depthUpdate", "U": 1000, "u": 1005, "pu": 999, "b": [], "a": []}
    engine.apply_delta(d1, observed_wall_ms=1728720000010)

    # Subsequent event has pu == 1005
    d2 = {"e": "depthUpdate", "U": 1006, "u": 1010, "pu": 1005, "b": [], "a": []}
    receipt = engine.apply_delta(d2, observed_wall_ms=1728720000020)
    assert receipt.quality == "VERIFIED"
    assert receipt.final_update_id == 1010
    assert receipt.previous_final_update_id == 1005


def test_subsequent_delta_pu_gap_detected() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)
    engine.apply_snapshot(snap, observed_wall_ms=1728720000000)

    d1 = {"e": "depthUpdate", "U": 1000, "u": 1005, "pu": 999, "b": [], "a": []}
    engine.apply_delta(d1, observed_wall_ms=1728720000010)

    # Next event has pu == 1020 != 1005 -> Gap!
    d2 = {"e": "depthUpdate", "U": 1021, "u": 1025, "pu": 1020, "b": [], "a": []}
    receipt = engine.apply_delta(d2, observed_wall_ms=1728720000020)
    assert receipt.quality == "INVALID"
    assert receipt.continuous is False
    assert any("GAP_DETECTED" in r for r in receipt.reason_codes)


def test_price_level_quantity_zero_deletes_level() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "2.500"], ["64999.00", "1.000"]],
        "asks": [["65001.00", "3.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1728720000000)
    assert Decimal("65000.00") in engine.bids

    # Delete 65000.00 level with quantity 0
    delta = {
        "e": "depthUpdate",
        "U": 1000,
        "u": 1001,
        "pu": 999,
        "b": [["65000.00", "0.000"]],
        "a": [],
    }
    receipt = engine.apply_delta(delta, observed_wall_ms=1728720000010)
    assert receipt.quality == "VERIFIED"
    assert Decimal("65000.00") not in engine.bids
    assert receipt.best_bid == "64999.00"


def test_price_level_update_and_insert() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65002.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1728720000000)

    # Insert new ask at 65001.00 and update bid at 65000.00
    delta = {
        "e": "depthUpdate",
        "U": 1000,
        "u": 1001,
        "pu": 999,
        "b": [["65000.00", "5.500"]],
        "a": [["65001.00", "2.000"]],
    }
    receipt = engine.apply_delta(delta, observed_wall_ms=1728720000010)
    assert receipt.best_ask == "65001.00"
    assert engine.bids[Decimal("65000.00")] == Decimal("5.500")


def test_delta_causing_crossed_book_fails_closed() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65002.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1728720000000)

    # Bid update crosses ask (65003 > 65002)
    delta = {
        "e": "depthUpdate",
        "U": 1000,
        "u": 1001,
        "pu": 999,
        "b": [["65003.00", "1.000"]],
        "a": [],
    }
    receipt = engine.apply_delta(delta, observed_wall_ms=1728720000010)
    assert receipt.quality == "INVALID"
    assert receipt.continuous is False
    assert any("CROSSED_BOOK" in r for r in receipt.reason_codes)


def test_stale_age_exceeded_marks_degraded() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT", max_stale_age_ms=300_000)
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)
    # Check receipt 301 seconds later (301,000 ms)
    receipt = engine.get_integrity_receipt(current_wall_ms=1000 + 301_000)
    assert receipt.quality == "DEGRADED"
    assert "STALE_BOOK" in receipt.reason_codes
    assert receipt.stale_age_ms == 301_000


def test_rebootstrap_workflow() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap1 = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap1, observed_wall_ms=1000)

    # Cause gap failure
    gap_delta = {"e": "depthUpdate", "U": 1050, "u": 1055, "pu": 1049, "b": [], "a": []}
    receipt_gap = engine.apply_delta(gap_delta, observed_wall_ms=2000)
    assert receipt_gap.quality == "INVALID"

    # Re-bootstrap with fresh snapshot
    snap2 = {
        "lastUpdateId": 1060,
        "bids": [["65010.00", "2.000"]],
        "asks": [["65012.00", "2.000"]],
    }
    receipt_recovered = engine.apply_snapshot(snap2, observed_wall_ms=3000)
    assert receipt_recovered.quality == "VERIFIED"
    assert receipt_recovered.continuous is True
    assert receipt_recovered.snapshot_update_id == 1060
    assert receipt_recovered.best_bid == "65010.00"


def test_delta_without_pu_uses_contiguous_U() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)

    d1 = {"e": "depthUpdate", "U": 1000, "u": 1005, "b": [], "a": []}
    engine.apply_delta(d1, observed_wall_ms=1010)

    # Next event without pu has U == 1006 (contiguous)
    d2 = {"e": "depthUpdate", "U": 1006, "u": 1010, "b": [], "a": []}
    receipt = engine.apply_delta(d2, observed_wall_ms=1020)
    assert receipt.quality == "VERIFIED"
    assert receipt.final_update_id == 1010
