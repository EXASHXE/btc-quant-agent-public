"""25 Pytest unit tests for L2 depth, order book bridging, Top-10 ladders, and P2 imbalance."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

_B_DIR = "/root/workspace/project/quant-v0.6/gemini-forward-shadow-research-r1"
if _B_DIR not in sys.path and Path(_B_DIR).exists():
    sys.path.insert(0, _B_DIR)

from market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine

from scripts.integration.market_event_bridge_r2.book_ladder import (
    OrderBookLadderAdapter,
)


def _make_sample_snapshot(snap_id: int = 1000, levels: int = 20) -> dict:
    base = 64000.0
    bids = [[f"{base - 0.5 * i:.2f}", "1.5"] for i in range(1, levels + 1)]
    asks = [[f"{base + 0.5 * i:.2f}", "1.5"] for i in range(1, levels + 1)]
    return {
        "lastUpdateId": snap_id,
        "bids": bids,
        "asks": asks,
        "symbol": "BTCUSDT",
    }


def test_depth_snapshot_bootstrapping_success() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=20)
    receipt = engine.apply_snapshot(snap, 1728720000000)
    assert receipt.continuous is True
    assert receipt.quality == "VERIFIED"
    assert engine.is_bootstrapped is True
    assert engine.final_update_id == 1000


def test_depth_snapshot_missing_last_update_id_resets() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {"bids": [["64000.00", "1.0"]], "asks": [["64001.00", "1.0"]]}
    receipt = engine.apply_snapshot(snap, 1728720000000)
    assert receipt.continuous is False
    assert receipt.quality == "INVALID"
    assert "INVALID_SNAPSHOT_MISSING_LAST_UPDATE_ID" in receipt.reason_codes


def test_depth_snapshot_negative_price_resets() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["-64000.00", "1.0"]],
        "asks": [["64001.00", "1.0"]],
    }
    receipt = engine.apply_snapshot(snap, 1728720000000)
    assert receipt.continuous is False
    assert receipt.quality == "INVALID"


def test_depth_snapshot_negative_quantity_resets() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["64000.00", "-1.0"]],
        "asks": [["64001.00", "1.0"]],
    }
    receipt = engine.apply_snapshot(snap, 1728720000000)
    assert receipt.continuous is False
    assert receipt.quality == "INVALID"


def test_depth_first_update_bridging_success() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    # First update: U <= 1000 <= u
    delta = {
        "U": 995,
        "u": 1005,
        "pu": 994,
        "b": [["63990.00", "2.0"]],
        "a": [["64010.00", "2.0"]],
    }
    receipt = engine.apply_delta(delta, 1728720000100)
    assert receipt.continuous is True
    assert receipt.quality == "VERIFIED"
    assert engine.final_update_id == 1005


def test_depth_first_update_gap_resets() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    # Gap: U > 1001 (e.g. U=1010)
    delta = {
        "U": 1010,
        "u": 1020,
        "pu": 1009,
        "b": [],
        "a": [],
    }
    receipt = engine.apply_delta(delta, 1728720000100)
    assert receipt.continuous is False
    assert receipt.quality == "INVALID"
    assert any("GAP_SNAPSHOT_TO_STREAM" in r for r in receipt.reason_codes)


def test_depth_subsequent_pu_mismatch_resets() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    d1 = {"U": 995, "u": 1005, "pu": 994, "b": [], "a": []}
    engine.apply_delta(d1, 1728720000100)

    # Second delta has pu != 1005 (e.g. pu=1007)
    d2 = {"U": 1008, "u": 1015, "pu": 1007, "b": [], "a": []}
    receipt = engine.apply_delta(d2, 1728720000200)
    assert receipt.continuous is False
    assert receipt.quality == "INVALID"
    assert any("GAP_DETECTED" in r for r in receipt.reason_codes)


def test_depth_subsequent_u_less_equal_pu_resets() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    d1 = {"U": 995, "u": 1005, "pu": 994, "b": [], "a": []}
    engine.apply_delta(d1, 1728720000100)

    # u <= pu (e.g. u=1005 <= pu=1005)
    d2 = {"U": 1005, "u": 1005, "pu": 1005, "b": [], "a": []}
    receipt = engine.apply_delta(d2, 1728720000200)
    assert receipt.continuous is False
    assert receipt.quality == "INVALID"
    assert any("DUPLICATE_OR_BACKWARDS_UPDATE" in r for r in receipt.reason_codes)


def test_depth_quantity_zero_removes_level() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["64000.00", "1.5"]],
        "asks": [["64001.00", "1.5"]],
    }
    engine.apply_snapshot(snap, 1728720000000)
    assert Decimal("64000.00") in engine.bids

    # Remove bid level
    delta = {"U": 1000, "u": 1001, "pu": 1000, "b": [["64000.00", "0"]], "a": []}
    engine.apply_delta(delta, 1728720000100)
    assert Decimal("64000.00") not in engine.bids


def test_depth_quantity_positive_updates_level() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["64000.00", "1.5"]],
        "asks": [["64001.00", "1.5"]],
    }
    engine.apply_snapshot(snap, 1728720000000)

    # Update bid quantity to 5.0
    delta = {"U": 1000, "u": 1001, "pu": 1000, "b": [["64000.00", "5.0"]], "a": []}
    engine.apply_delta(delta, 1728720000100)
    assert engine.bids[Decimal("64000.00")] == Decimal("5.0")


def test_depth_crossed_spread_detected_and_reset() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["64000.00", "1.5"]],
        "asks": [["64001.00", "1.5"]],
    }
    engine.apply_snapshot(snap, 1728720000000)

    # Delta crosses book: bid 64002 >= ask 64001
    delta = {"U": 1000, "u": 1001, "pu": 1000, "b": [["64002.00", "1.0"]], "a": []}
    receipt = engine.apply_delta(delta, 1728720000100)
    assert receipt.continuous is False
    assert receipt.quality == "INVALID"
    assert any("CROSSED_BOOK" in r for r in receipt.reason_codes)


def test_depth_ladder_extraction_sorts_bids_descending() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    bid_prices = [p for p, _q in snapshot.bids]
    assert bid_prices == sorted(bid_prices, reverse=True)


def test_depth_ladder_extraction_sorts_asks_ascending() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    ask_prices = [p for p, _q in snapshot.asks]
    assert ask_prices == sorted(ask_prices)


def test_depth_ladder_extraction_exact_top10_levels() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=20)
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    assert len(snapshot.bids) == 10
    assert len(snapshot.asks) == 10
    assert snapshot.quality == "VERIFIED"


def test_depth_ladder_extraction_less_than_10_degraded() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=5)  # only 5 levels
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    assert len(snapshot.bids) == 5
    assert len(snapshot.asks) == 5
    assert snapshot.quality == "DEGRADED"
    assert any("INCOMPLETE_L2_DEPTH" in r for r in snapshot.reason_codes)


def test_depth_ladder_stale_over_1s_degraded() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    # Wall clock is 1500ms ahead (> 1000ms stale limit)
    snapshot = adapter.extract_atomic_snapshot(1728720001500)
    assert snapshot.quality == "DEGRADED"
    assert any("DEPTH_STALE_OVER_1S" in r for r in snapshot.reason_codes)


def test_depth_ladder_top10_imbalance_calculation() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    # Skew bids heavier than asks
    base = 64000.0
    bids = [[f"{base - 0.5 * i:.2f}", "3.0"] for i in range(1, 15)]
    asks = [[f"{base + 0.5 * i:.2f}", "1.0"] for i in range(1, 15)]
    snap = {"lastUpdateId": 1000, "bids": bids, "asks": asks, "symbol": "BTCUSDT"}
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    imb = snapshot.top_10_imbalance()
    assert imb is not None
    assert imb > 0.0  # Bid notional is greater, positive imbalance


def test_depth_ladder_top10_imbalance_none_when_degraded() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=5)  # <10 levels
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    assert snapshot.top_10_imbalance() is None


def test_depth_ladder_top10_imbalance_none_when_invalid() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    # Not bootstrapped
    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    assert snapshot.top_10_imbalance() is None


def test_depth_ladder_top10_sha256_deterministic() -> None:
    engine1 = OrderBookIntegrityEngine(symbol="BTCUSDT")
    engine2 = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine1.apply_snapshot(snap, 1728720000000)
    engine2.apply_snapshot(snap, 1728720000000)

    s1 = OrderBookLadderAdapter(engine1).extract_atomic_snapshot(1728720000050)
    s2 = OrderBookLadderAdapter(engine2).extract_atomic_snapshot(1728720000050)
    assert s1.top10_ladder_sha256 == s2.top10_ladder_sha256


def test_depth_ladder_top10_sha256_detects_mutation() -> None:
    engine1 = OrderBookIntegrityEngine(symbol="BTCUSDT")
    engine2 = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap1 = _make_sample_snapshot(1000, levels=15)
    snap2 = _make_sample_snapshot(1000, levels=15)
    snap2["bids"][0][1] = "99.9"  # Mutate first bid quantity
    engine1.apply_snapshot(snap1, 1728720000000)
    engine2.apply_snapshot(snap2, 1728720000000)

    s1 = OrderBookLadderAdapter(engine1).extract_atomic_snapshot(1728720000050)
    s2 = OrderBookLadderAdapter(engine2).extract_atomic_snapshot(1728720000050)
    assert s1.top10_ladder_sha256 != s2.top10_ladder_sha256


def test_depth_ladder_converts_to_b_book_integrity_dict() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    b_dict = snapshot.to_b_book_dict()
    assert "bids" in b_dict
    assert "asks" in b_dict
    assert len(b_dict["bids"]) == 10
    assert len(b_dict["asks"]) == 10


def test_depth_b_book_integrity_ingestion() -> None:
    from scripts.strategy_research.forward_shadow_research_r1.contract import (
        BookIntegrityV1 as BBook,
    )
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    b_dict = snapshot.to_b_book_dict()

    b_book = BBook(
        snapshot_update_id=b_dict["snapshot_update_id"],
        first_update_id=b_dict["first_update_id"],
        final_update_id=b_dict["final_update_id"],
        previous_final_update_id=b_dict["previous_final_update_id"],
        continuous=b_dict["continuous"],
        best_bid=b_dict["best_bid"],
        best_ask=b_dict["best_ask"],
        bids=tuple((p, q) for p, q in b_dict["bids"]),
        asks=tuple((p, q) for p, q in b_dict["asks"]),
        observed_depth_levels=b_dict["observed_depth_levels"],
        stale_age_ms=b_dict["stale_age_ms"],
        quality=b_dict["quality"],
        reason_codes=tuple(b_dict["reason_codes"]),
    )
    assert b_book.top_n_imbalance(10) is not None


def test_depth_ladder_uncrossed_best_bid_less_than_best_ask() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    snapshot = adapter.extract_atomic_snapshot(1728720000050)
    assert Decimal(snapshot.best_bid) < Decimal(snapshot.best_ask)


def test_depth_ladder_route_epoch_isolated() -> None:
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = _make_sample_snapshot(1000, levels=15)
    engine.apply_snapshot(snap, 1728720000000)

    adapter = OrderBookLadderAdapter(engine)
    s1 = adapter.extract_atomic_snapshot(1728720000050, route_epoch="ep-001")
    s2 = adapter.extract_atomic_snapshot(1728720000050, route_epoch="ep-002")
    assert s1.route_epoch == "ep-001"
    assert s2.route_epoch == "ep-002"
    assert s1.top10_ladder_sha256 != s2.top10_ladder_sha256
