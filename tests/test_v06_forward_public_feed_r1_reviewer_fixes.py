"""Automated verification tests for reviewer fixes and attacked edge cases:
- OrderBook: reversed IDs (U > u), duplicate/backwards sequence IDs (u <= pu), intra-frame mutation contradictions
- OrderBook: contiguous first delta bridging (U == lastUpdateId + 1) without pu
- OrderBook: empty book sides and completely empty book degradation
- TimeAuthority: exchange clock offset tracking and negative transit latency diagnostics
- TimeAuthority: Point-in-Time Mark/Last cross-channel join and causality violations
- Durability: Segregated RawSegmentWriter / RawSegmentReader with hash chain verification
- Durability: SegmentWriter crash-restart idempotence without hash chain break
- Durability: Clock uncertainty recorded in segment manifest
- Health: require_settled_funding gating, consumer ingress queue drop degradation, exchange access denial
- Connector: symbol allowlist enforcement on provider payload, payload shape validation, rebootstrap
- Contracts: trade aggressor side extraction (BUY / SELL based on m)
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.connector import BinancePublicFeedClient
from market_data.forward_public_feed_r1.contracts import (
    ALLOWED_PRODUCT,
    ContractValidationError,
    MarketEventV1,
    compute_sha256,
    get_aggressor_side,
)
from market_data.forward_public_feed_r1.durability import (
    RawSegmentReader,
    RawSegmentWriter,
    SegmentReader,
    SegmentWriter,
    canonical_json_bytes,
)
from market_data.forward_public_feed_r1.fixture import DeterministicExchangeFixture
from market_data.forward_public_feed_r1.health import HealthSupervisor
from market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine
from market_data.forward_public_feed_r1.replay import ReplayEngine
from market_data.forward_public_feed_r1.time_authority import (
    PointInTimeViolationError,
    TimeAuthority,
    join_mark_and_last,
)

# --- 1. Order Book Edge Cases ---


def test_order_book_rejects_reversed_sequence_ids() -> None:
    """Reversed sequence IDs (U > u) must fail closed with REVERSED_SEQUENCE_IDS."""
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)

    # Delta with U=1006, u=1002 (reversed!)
    delta = {"e": "depthUpdate", "U": 1006, "u": 1002, "pu": 1000, "b": [], "a": []}
    receipt = engine.apply_delta(delta, observed_wall_ms=1010)

    assert receipt.quality == "INVALID"
    assert receipt.continuous is False
    assert any("REVERSED_SEQUENCE_IDS" in r for r in receipt.reason_codes)
    assert engine.needs_rebootstrap is True


def test_order_book_rejects_backwards_final_update_id() -> None:
    """Updates where u <= pu must fail closed with DUPLICATE_OR_BACKWARDS_UPDATE."""
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)

    # First delta bridges to 1005
    d1 = {"e": "depthUpdate", "U": 1000, "u": 1005, "pu": 999, "b": [], "a": []}
    r1 = engine.apply_delta(d1, observed_wall_ms=1010)
    assert r1.quality == "VERIFIED"

    # Next delta has u=1004 <= prev_u=1005
    d2 = {"e": "depthUpdate", "U": 1004, "u": 1004, "pu": 1005, "b": [], "a": []}
    r2 = engine.apply_delta(d2, observed_wall_ms=1020)

    assert r2.quality == "INVALID"
    assert any("DUPLICATE_OR_BACKWARDS_UPDATE" in r for r in r2.reason_codes)


def test_order_book_rejects_intra_frame_duplicate_price_levels() -> None:
    """Duplicate price levels in same delta mutation must fail closed with DEPTH_MUTATION_CONTRADICTION."""
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)

    # Delta with duplicate bid prices
    delta = {
        "e": "depthUpdate",
        "U": 1001,
        "u": 1005,
        "pu": 1000,
        "b": [["64999.00", "1.500"], ["64999.00", "2.000"]],
        "a": [],
    }
    receipt = engine.apply_delta(delta, observed_wall_ms=1010)

    assert receipt.quality == "INVALID"
    assert any("DEPTH_MUTATION_CONTRADICTION" in r for r in receipt.reason_codes)


def test_order_book_bridges_contiguous_first_delta_without_pu() -> None:
    """First delta without pu having U == lastUpdateId + 1 must bridge successfully."""
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)

    # First delta has U=1001, u=1005, pu is None
    delta = {"e": "depthUpdate", "U": 1001, "u": 1005, "b": [["65000.00", "1.200"]], "a": []}
    receipt = engine.apply_delta(delta, observed_wall_ms=1010)

    assert receipt.quality == "VERIFIED"
    assert receipt.continuous is True
    assert receipt.first_update_id == 1001
    assert receipt.final_update_id == 1005


def test_order_book_first_delta_pu_gap_triggers_reset() -> None:
    """First delta with pu > lastUpdateId indicates missing intermediate updates and must reset."""
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)

    delta = {"e": "depthUpdate", "U": 1001, "u": 1005, "pu": 2000, "b": [], "a": []}
    receipt = engine.apply_delta(delta, observed_wall_ms=1010)

    assert receipt.quality == "INVALID"
    assert any("GAP_SNAPSHOT_TO_STREAM" in r for r in receipt.reason_codes)


def test_order_book_completely_empty_book_degrades_quality() -> None:
    """When both bids and asks are completely depleted, book quality becomes DEGRADED."""
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)

    delta = {
        "e": "depthUpdate",
        "U": 1001,
        "u": 1005,
        "pu": 1000,
        "b": [["65000.00", "0.000"]],
        "a": [["65001.00", "0.000"]],
    }
    receipt = engine.apply_delta(delta, observed_wall_ms=1010)

    assert receipt.quality == "DEGRADED"
    assert any("EMPTY_BOOK" in r for r in receipt.reason_codes)


# --- 2. Time Authority & Causality ---


def test_time_authority_records_exchange_clock_offset() -> None:
    """TimeAuthority must record exchange clock offset diagnostics."""
    ta = TimeAuthority()
    # Provider clock is 250ms ahead of receiver wall
    ta.record_transit_latency(provider_event_ms=1_000_250, observed_wall_ms=1_000_000)
    # Provider clock is 100ms behind receiver wall
    ta.record_transit_latency(provider_event_ms=999_900, observed_wall_ms=1_000_000)

    diag = ta.get_diagnostics()
    assert "exchange_offset" in diag
    assert diag["exchange_offset"]["sample_count"] == 2
    assert diag["exchange_offset"]["latest_ms"] == -100
    assert diag["exchange_offset"]["mean_ms"] == 75.0


def test_point_in_time_mark_last_join_success() -> None:
    """Valid PIT join when both Mark and Last are VERIFIED and available_at <= decision_at."""
    ta = TimeAuthority(connection_epoch="ep-join")
    ing1 = ta.capture_ingress(override_wall_ms=1000)
    ing2 = ta.capture_ingress(override_wall_ms=1050)

    m_payload = {"p": "65100.00", "i": "65095.00", "r": "0.00010000", "T": 1728748800000}
    k_payload = {"k": {"t": 960000, "T": 1019999, "s": "BTCUSDT", "i": "1m", "o": "65000", "c": "65150.00", "h": "65200", "l": "64950", "v": "10", "x": True}}

    m_ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="mark_price",
        provider_event_ms=990,
        provider_transaction_ms=None,
        observed_wall_utc_ms=ing1.observed_wall_utc_ms,
        observed_monotonic_ns=ing1.observed_monotonic_ns,
        available_at_ms=ing1.available_at_ms,
        source_stream_id="btcusdt@markPrice",
        connection_epoch="ep-join",
        source_sequence=None,
        payload_sha256=compute_sha256(m_payload),
        payload=m_payload,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="0" * 64,
    )

    k_ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="last_kline_1m",
        provider_event_ms=1020,
        provider_transaction_ms=None,
        observed_wall_utc_ms=ing2.observed_wall_utc_ms,
        observed_monotonic_ns=ing2.observed_monotonic_ns,
        available_at_ms=ing2.available_at_ms,
        source_stream_id="btcusdt@kline_1m",
        connection_epoch="ep-join",
        source_sequence=1,
        payload_sha256=compute_sha256(k_payload),
        payload=k_payload,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="0" * 64,
    )

    joined = join_mark_and_last(m_ev, k_ev, decision_at_ms=1100)
    assert joined["symbol"] == "BTCUSDT"
    assert joined["mark_price"] == "65100.00"
    assert joined["kline_close"] == "65150.00"
    assert joined["mark_last_basis"] == "50.00"
    assert joined["feature_known_at_ms"] == 1050
    assert joined["decision_at_ms"] == 1100


def test_point_in_time_mark_last_join_rejects_future_data() -> None:
    """Causality violation: join must fail if any input was observed after decision_at."""
    ta = TimeAuthority(connection_epoch="ep-join")
    ing = ta.capture_ingress(override_wall_ms=1200)

    m_payload = {"p": "65100.00", "i": "65095.00", "r": "0.00010000", "T": 1728748800000}
    k_payload = {"k": {"t": 960000, "T": 1019999, "s": "BTCUSDT", "i": "1m", "o": "65000", "c": "65150.00", "h": "65200", "l": "64950", "v": "10", "x": True}}

    m_ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="mark_price",
        provider_event_ms=990,
        provider_transaction_ms=None,
        observed_wall_utc_ms=ing.observed_wall_utc_ms,
        observed_monotonic_ns=ing.observed_monotonic_ns,
        available_at_ms=1200,  # Arrived at 1200ms
        source_stream_id="btcusdt@markPrice",
        connection_epoch="ep-join",
        source_sequence=None,
        payload_sha256=compute_sha256(m_payload),
        payload=m_payload,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="0" * 64,
    )

    k_ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="last_kline_1m",
        provider_event_ms=1020,
        provider_transaction_ms=None,
        observed_wall_utc_ms=1000,
        observed_monotonic_ns=1000,
        available_at_ms=1000,
        source_stream_id="btcusdt@kline_1m",
        connection_epoch="ep-join",
        source_sequence=1,
        payload_sha256=compute_sha256(k_payload),
        payload=k_payload,
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="0" * 64,
    )

    # Decision at 1100ms cannot see mark_ev arriving at 1200ms
    with pytest.raises(PointInTimeViolationError, match="Causality violation"):
        join_mark_and_last(m_ev, k_ev, decision_at_ms=1100)


# --- 3. Durability & Segregated Raw Logging ---


def test_raw_segment_writer_and_reader_roundtrip() -> None:
    """Raw incoming provider wire frames must be logged in dedicated raw segments."""
    with tempfile.TemporaryDirectory() as td:
        rw = RawSegmentWriter(base_dir=td, epoch="ep-raw-test")
        raw1 = '{"e":"aggTrade","s":"BTCUSDT","p":"65000.00","q":"0.1"}'
        raw2 = '{"e":"markPriceUpdate","s":"BTCUSDT","p":"65005.00"}'

        _h1, man_sha1 = rw.append_raw_frame(raw1, received_wall_ms=1000, received_monotonic_ns=1_000_000_000)
        _h2, man_sha2 = rw.append_raw_frame(raw2, received_wall_ms=1010, received_monotonic_ns=1_010_000_000)
        rw.close()

        assert len(man_sha1) == 64
        assert len(man_sha2) == 64

        seg_path = Path(td) / "raw_segment_ep-raw-test_000001.jsonl"
        entries, head_h = RawSegmentReader.read_raw_segment(seg_path)
        assert len(entries) == 2
        assert entries[0]["raw_payload"] == raw1
        assert entries[1]["raw_payload"] == raw2
        assert head_h == _h2


def test_segment_writer_crash_restart_idempotence() -> None:
    """Restarting SegmentWriter with an existing segment file must resume without corrupting hash chain."""
    with tempfile.TemporaryDirectory() as td:
        # First process session
        w1 = SegmentWriter(base_dir=td, epoch="ep-restart")
        p1 = {"p": "65000"}
        ev1 = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="agg_trade",
            provider_event_ms=1000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1000,
            observed_monotonic_ns=1000,
            available_at_ms=1000,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="ep-restart",
            source_sequence=1,
            payload_sha256=compute_sha256(p1),
            payload=p1,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="0" * 64,
        )
        w1.append_event(ev1)
        w1.close()

        # Simulated process restart with same directory and epoch
        w2 = SegmentWriter(base_dir=td, epoch="ep-restart")
        p2 = {"p": "65005"}
        ev2 = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="agg_trade",
            provider_event_ms=2000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=2000,
            observed_monotonic_ns=2000,
            available_at_ms=2000,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="ep-restart",
            source_sequence=2,
            payload_sha256=compute_sha256(p2),
            payload=p2,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="0" * 64,
        )
        w2.append_event(ev2)
        w2.close()

        # Read back and verify unbroken hash chain across restart
        seg_file = Path(td) / "segment_ep-restart_000001.jsonl"
        events, _head_hash = SegmentReader.read_segment(seg_file)
        assert len(events) == 2
        assert events[0].source_sequence == 1
        assert events[1].source_sequence == 2


def test_segment_manifest_includes_clock_uncertainty() -> None:
    """Atomic segment manifest must record clock uncertainty count and status."""
    with tempfile.TemporaryDirectory() as td:
        writer = SegmentWriter(base_dir=td, epoch="ep-clock-man")
        writer.set_clock_uncertainty(3)
        p = {"p": "65000"}
        ev = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="agg_trade",
            provider_event_ms=1000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1000,
            observed_monotonic_ns=1000,
            available_at_ms=1000,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="ep-clock-man",
            source_sequence=1,
            payload_sha256=compute_sha256(p),
            payload=p,
            quality="DEGRADED",
            reason_codes=["CLOCK_UNCERTAIN"],
            raw_source_manifest_sha256="0" * 64,
        )
        writer.append_event(ev)
        writer.close()

        man_path = Path(td) / "manifest_ep-clock-man_000001.json"
        man = SegmentReader.read_manifest(man_path)
        assert "clock_uncertainty" in man
        assert man["clock_uncertainty"]["uncertain_count"] == 3
        assert man["clock_uncertainty"]["status"] == "CLOCK_UNCERTAIN"


# --- 4. Health Supervision & Ingestion Validation ---


def test_health_supervisor_requires_settled_funding() -> None:
    """If require_settled_funding=True, unknown settled funding must trigger LAST_SETTLED_FUNDING_UNKNOWN."""
    hs = HealthSupervisor(symbol="BTCUSDT")
    current_ms = 1_000_000

    hs.record_book_status(quality="VERIFIED", continuous=True, reason_codes=["OK"])
    hs.record_channel_event("mark_price", current_ms - 1000, {"p": "65000", "r": "0.0001"}, "VERIFIED")
    hs.record_channel_event("depth_delta", current_ms - 500, {"u": 100}, "VERIFIED")

    gate, reasons = hs.evaluate_source_gate(current_wall_ms=current_ms, require_settled_funding=True)
    assert gate == "SOURCE_DEGRADED"
    assert "LAST_SETTLED_FUNDING_UNKNOWN" in reasons

    # Now record official settled funding
    hs.record_channel_event("funding_settled", current_ms - 3600_000, {"fundingRate": "0.0001"}, "VERIFIED")
    gate2, reasons2 = hs.evaluate_source_gate(current_wall_ms=current_ms, require_settled_funding=True)
    assert gate2 == "SOURCE_READY"
    assert reasons2 == ["OK"]


def test_health_supervisor_ingress_drops_degrade_gate() -> None:
    """Consumer ingress queue drops must degrade the source gate."""
    ta = TimeAuthority()
    ta.increment_dropped_ingress(5)

    hs = HealthSupervisor(symbol="BTCUSDT", time_authority=ta)
    current_ms = 1_000_000

    hs.record_book_status(quality="VERIFIED", continuous=True, reason_codes=["OK"])
    hs.record_channel_event("mark_price", current_ms - 1000, {"p": "65000"}, "VERIFIED")
    hs.record_channel_event("depth_delta", current_ms - 500, {"u": 100}, "VERIFIED")

    gate, reasons = hs.evaluate_source_gate(current_wall_ms=current_ms)
    assert gate == "SOURCE_DEGRADED"
    assert any("CONSUMER_INGRESS_DROPS" in r for r in reasons)


def test_health_supervisor_access_denial_causes_unavailable() -> None:
    """Exchange access denial immediately transitions source to SOURCE_UNAVAILABLE."""
    hs = HealthSupervisor(symbol="BTCUSDT")
    hs.record_access_denial("HTTP 403 Forbidden")

    gate, reasons = hs.evaluate_source_gate(current_wall_ms=1000)
    assert gate == "SOURCE_UNAVAILABLE"
    assert "EXCHANGE_ACCESS_DENIED" in reasons


def test_connector_rejects_alien_symbol_in_provider_frame() -> None:
    """Provider frames for symbols other than BTCUSDT must be strictly rejected."""
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")
    alien_frame = '{"e":"aggTrade","s":"ETHUSDT","a":123,"p":"2500.00","q":"1.0","m":false}'

    with pytest.raises(ContractValidationError, match="does not match allowed"):
        client.map_raw_frame_to_event(
            alien_frame,
            observed_wall_ms=1000,
            observed_monotonic_ns=1000,
            raw_manifest_sha256="0" * 64,
        )


def test_trade_aggressor_side_mapping() -> None:
    """Binance aggTrade 'm' field must correctly map to BUY/SELL aggressor direction."""
    # m is True -> buyer was maker -> seller was aggressor -> SELL
    assert get_aggressor_side({"m": True}) == "SELL"
    # m is False -> buyer was taker -> buyer was aggressor -> BUY
    assert get_aggressor_side({"m": False}) == "BUY"
    # m missing
    assert get_aggressor_side({}) == "UNKNOWN"


def test_replay_engine_supports_multi_epoch_and_epoch_filtering() -> None:
    """ReplayEngine must handle independent genesis epochs in the same directory and filter by epoch."""
    with tempfile.TemporaryDirectory() as td:
        # Epoch 1: writes 2 events starting at genesis
        w1 = SegmentWriter(base_dir=td, epoch="epoch-alpha")
        ev1 = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="agg_trade",
            provider_event_ms=1000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=1000,
            observed_monotonic_ns=1000,
            available_at_ms=1000,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-alpha",
            source_sequence=1,
            payload_sha256=compute_sha256({"t": 1}),
            payload={"t": 1},
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256=w1.manifest_sha256,
        )
        w1.append_event(ev1)
        w1.close()

        # Epoch 2: completely separate run starting at genesis
        w2 = SegmentWriter(base_dir=td, epoch="epoch-beta")
        ev2 = MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="agg_trade",
            provider_event_ms=2000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=2000,
            observed_monotonic_ns=2000,
            available_at_ms=2000,
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="epoch-beta",
            source_sequence=2,
            payload_sha256=compute_sha256({"t": 2}),
            payload={"t": 2},
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256=w2.manifest_sha256,
        )
        w2.append_event(ev2)
        w2.close()

        # Replay all should replay both epochs seamlessly
        engine_all = ReplayEngine(data_dir=td)
        events_all, witness_all = engine_all.replay_all()
        assert len(events_all) == 2
        assert witness_all.events_replayed == 2

        # Replay with epoch filter should replay only the requested epoch
        engine_alpha = ReplayEngine(data_dir=td, epoch="epoch-alpha")
        events_alpha, witness_alpha = engine_alpha.replay_all()
        assert len(events_alpha) == 1
        assert events_alpha[0].connection_epoch == "epoch-alpha"
        assert witness_alpha.events_replayed == 1

        engine_beta = ReplayEngine(data_dir=td, epoch="epoch-beta")
        events_beta, witness_beta = engine_beta.replay_all()
        assert len(events_beta) == 1
        assert events_beta[0].connection_epoch == "epoch-beta"
        assert witness_beta.events_replayed == 1


# --- 7. Deep Reviewer Hardening & Attacked Edge Cases ---


def test_book_integrity_rejects_nan_and_inf_prices() -> None:
    """BookIntegrityV1 must reject NaN, Inf, and non-numeric price strings with ContractValidationError."""
    from market_data.forward_public_feed_r1.contracts import BookIntegrityV1

    invalid_prices = ["NaN", "nan", "Infinity", "-Infinity", "inf", "-inf", "not_a_number"]
    for bad_price in invalid_prices:
        with pytest.raises(ContractValidationError):
            BookIntegrityV1(
                snapshot_update_id=1000,
                first_update_id=1001,
                final_update_id=1005,
                previous_final_update_id=1000,
                continuous=True,
                best_bid=bad_price,
                best_ask="65000.50",
                observed_depth_levels=2,
                stale_age_ms=10,
                quality="VERIFIED",
            )

        with pytest.raises(ContractValidationError):
            BookIntegrityV1(
                snapshot_update_id=1000,
                first_update_id=1001,
                final_update_id=1005,
                previous_final_update_id=1000,
                continuous=True,
                best_bid="65000.00",
                best_ask=bad_price,
                observed_depth_levels=2,
                stale_age_ms=10,
                quality="VERIFIED",
            )


def test_order_book_snapshot_duplicate_levels_fails_closed() -> None:
    """Duplicate price levels in snapshot must fail closed immediately."""
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap_dup_bid = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"], ["65000.00", "2.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    receipt = engine.apply_snapshot(snap_dup_bid, observed_wall_ms=1000)
    assert receipt.quality == "INVALID"
    assert receipt.continuous is False
    assert any("INVALID_SNAPSHOT_PARSE_ERROR" in r for r in receipt.reason_codes)

    engine_ask = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap_dup_ask = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"], ["65001.00", "3.000"]],
    }
    receipt_ask = engine_ask.apply_snapshot(snap_dup_ask, observed_wall_ms=1000)
    assert receipt_ask.quality == "INVALID"
    assert receipt_ask.continuous is False


def test_order_book_one_sided_empty_records_empty_book_side_reason() -> None:
    """When only one side of the book is depleted, EMPTY_BOOK_SIDE is recorded in reason codes."""
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.00", "1.000"]],
        "asks": [["65001.00", "1.000"]],
    }
    engine.apply_snapshot(snap, observed_wall_ms=1000)

    delta = {
        "e": "depthUpdate",
        "U": 1000,
        "u": 1001,
        "pu": 999,
        "b": [["65000.00", "0.000"]],
        "a": [],
    }
    receipt = engine.apply_delta(delta, observed_wall_ms=1010)
    assert "EMPTY_BOOK_SIDE" in receipt.reason_codes
    assert receipt.best_bid is None
    assert receipt.best_ask == "65001.00"


def test_durability_manifest_tmp_crash_recovery() -> None:
    """If process terminates right after writing manifest .tmp before replace, recovery promotes it."""
    with tempfile.TemporaryDirectory() as td:
        epoch = "ep-tmp-recovery"
        man_data = {
            "epoch": epoch,
            "feed_id": "BTCUSDT_BINANCE_USDT_M_PERP",
            "segment_index": 1,
            "record_count": 0,
            "first_index": None,
            "last_index": None,
            "first_wall_utc_ms": None,
            "last_wall_utc_ms": None,
            "head_hash": "0" * 64,
            "clock_uncertainty": {"uncertain_count": 0, "status": "CLOCK_SYNCHRONIZED"},
            "segment_filename": f"segment_{epoch}_000001.jsonl",
        }
        man_sha = hashlib.sha256(canonical_json_bytes(man_data)).hexdigest()
        man_data["manifest_sha256"] = man_sha

        # Write only the .tmp file
        tmp_path = Path(td) / f"manifest_{epoch}_000001.tmp"
        tmp_path.write_text(canonical_json_bytes(man_data).decode("utf-8"), encoding="utf-8")

        json_path = Path(td) / f"manifest_{epoch}_000001.json"
        assert not json_path.exists()

        # SegmentReader.read_manifest should auto-promote .tmp
        data = SegmentReader.read_manifest(json_path)
        assert data["manifest_sha256"] == man_sha
        assert json_path.exists()
        assert not tmp_path.exists()


def test_durability_raw_manifest_tmp_crash_recovery() -> None:
    """If process terminates right after writing raw manifest .tmp, RawSegmentWriter resumes cleanly."""
    with tempfile.TemporaryDirectory() as td:
        epoch = "ep-raw-tmp"
        seg_path = Path(td) / f"raw_segment_{epoch}_000001.jsonl"
        seg_path.write_text("", encoding="utf-8")

        man_data = {
            "epoch": epoch,
            "feed_id": "BTCUSDT_BINANCE_USDT_M_PERP_RAW",
            "segment_index": 1,
            "record_count": 0,
            "first_index": None,
            "last_index": None,
            "first_wall_utc_ms": None,
            "last_wall_utc_ms": None,
            "head_hash": "0" * 64,
            "segment_filename": f"raw_segment_{epoch}_000001.jsonl",
        }
        man_sha = hashlib.sha256(canonical_json_bytes(man_data)).hexdigest()
        man_data["manifest_sha256"] = man_sha

        tmp_path = Path(td) / f"raw_manifest_{epoch}_000001.tmp"
        tmp_path.write_text(canonical_json_bytes(man_data).decode("utf-8"), encoding="utf-8")

        rw = RawSegmentWriter(base_dir=td, epoch=epoch)
        json_path = Path(td) / f"raw_manifest_{epoch}_000001.json"
        assert json_path.exists()
        assert not tmp_path.exists()
        rw.close()


def test_raw_segment_reader_torn_write_quarantine() -> None:
    """RawSegmentReader with auto_repair_torn_write must isolate corrupt trailing line to quarantine."""
    with tempfile.TemporaryDirectory() as td:
        rw = RawSegmentWriter(base_dir=td, epoch="ep-torn-raw")
        rw.append_raw_frame('{"e":"aggTrade","s":"BTCUSDT","p":"65000"}', 1000, 1000)
        rw.append_raw_frame('{"e":"aggTrade","s":"BTCUSDT","p":"65001"}', 1010, 1010)
        rw.close()

        seg_path = Path(td) / "raw_segment_ep-torn-raw_000001.jsonl"
        # Simulate torn trailing write
        with open(seg_path, "a", encoding="utf-8") as f:
            f.write('{"index": 2, "prev_hash": "truncated_broken_line\n')

        entries, _head = RawSegmentReader.read_raw_segment(seg_path, auto_repair_torn_write=True)
        assert len(entries) == 2

        quar_path = seg_path.with_suffix(".quarantine")
        assert quar_path.exists()
        assert "truncated_broken_line" in quar_path.read_text(encoding="utf-8")


def test_connector_map_raw_frame_depth_snapshot_and_funding() -> None:
    """map_raw_frame_to_event must parse REST depth snapshot and settled funding records."""
    client = BinancePublicFeedClient(symbol="BTCUSDT", network_mode="disabled")

    # REST depth snapshot
    snap_frame = {
        "lastUpdateId": 5000,
        "E": 1728720000000,
        "T": 1728719999999,
        "bids": [["65000.00", "1.500"]],
        "asks": [["65001.00", "2.000"]],
    }
    snap_ev = client.map_raw_frame_to_event(
        json.dumps(snap_frame),
        observed_wall_ms=1728720000010,
        observed_monotonic_ns=1000,
        raw_manifest_sha256="msha",
    )
    assert snap_ev is not None
    assert snap_ev.channel == "depth_snapshot"
    assert snap_ev.source_sequence == 5000
    assert snap_ev.book is not None
    assert snap_ev.book.continuous is True

    # REST settled funding
    fund_frame = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00010000",
        "fundingTime": 1728720000000,
        "markPrice": "65000.00",
    }
    fund_ev = client.map_raw_frame_to_event(
        json.dumps(fund_frame),
        observed_wall_ms=1728720000020,
        observed_monotonic_ns=2000,
        raw_manifest_sha256="msha",
    )
    assert fund_ev is not None
    assert fund_ev.channel == "funding_settled"
    assert fund_ev.provider_event_ms == 1728720000000


def test_replay_engine_raw_segment_replay_workflow() -> None:
    """ReplayEngine.replay_raw reads raw segment files, verifies hash chains, and asserts continuous depth."""
    with tempfile.TemporaryDirectory() as td:
        epoch = "ep-raw-replay-test"
        rw = RawSegmentWriter(base_dir=td, epoch=epoch)
        fix = DeterministicExchangeFixture(symbol="BTCUSDT")

        # 1. Depth snapshot
        snap = fix.generate_depth_snapshot_frame(levels=10, last_update_id=1000)
        rw.append_raw_frame(json.dumps(snap), 1000, 1000000)

        # 2. Settled funding
        fund = fix.generate_settled_funding_frame()
        rw.append_raw_frame(json.dumps(fund), 1010, 1010000)

        # 3. Stream frames
        for i in range(10):
            fix.current_time_ms += 100
            mod = i % 4
            if mod == 0:
                frame = fix.generate_depth_delta_frame(span=2)
            elif mod == 1:
                frame = fix.generate_agg_trade_frame()
            elif mod == 2:
                frame = fix.generate_mark_price_frame()
            else:
                frame = fix.generate_kline_frame(closed=(i == 9))
            rw.append_raw_frame(json.dumps(frame), 1020 + i * 10, 1020000 + i * 10000)

        rw.close()

        # Replay directly from raw segments
        engine = ReplayEngine(data_dir=td, epoch=epoch)
        events, witness = engine.replay_raw()
        assert len(events) == 12
        assert witness.events_replayed == 12
        assert witness.depth_continuous is True
        assert witness.first_wall_utc_ms == 1000
        assert witness.last_wall_utc_ms == 1110
        assert witness.channel_counts["depth_snapshot"] == 1
        assert witness.channel_counts["funding_settled"] == 1


def test_replay_engine_auto_source_fallback_to_raw() -> None:
    """When only raw segments exist, replay_all(source='auto') automatically falls back to raw replay."""
    with tempfile.TemporaryDirectory() as td:
        epoch = "ep-auto-fallback"
        rw = RawSegmentWriter(base_dir=td, epoch=epoch)
        fix = DeterministicExchangeFixture(symbol="BTCUSDT")
        snap = fix.generate_depth_snapshot_frame(levels=5, last_update_id=1000)
        rw.append_raw_frame(json.dumps(snap), 1000, 1000)
        rw.close()

        engine = ReplayEngine(data_dir=td, epoch=epoch)
        events, witness = engine.replay_all(source="auto")
        assert len(events) == 1
        assert witness.depth_continuous is True


def test_join_mark_and_last_symbol_mismatch_fails_closed() -> None:
    """join_mark_and_last must raise PointInTimeViolationError when events have differing symbols."""
    ta = TimeAuthority()
    ing1 = ta.capture_ingress(override_wall_ms=1000)
    ing2 = ta.capture_ingress(override_wall_ms=1010)

    m_ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="mark_price",
        provider_event_ms=990,
        provider_transaction_ms=None,
        observed_wall_utc_ms=ing1.observed_wall_utc_ms,
        observed_monotonic_ns=ing1.observed_monotonic_ns,
        available_at_ms=ing1.available_at_ms,
        source_stream_id="btcusdt@markPrice",
        connection_epoch="ep-sym",
        source_sequence=None,
        payload_sha256=compute_sha256({"p": "65000", "i": "65000", "r": "0.0001", "T": 1728748800000}),
        payload={"p": "65000", "i": "65000", "r": "0.0001", "T": 1728748800000},
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="0" * 64,
    )

    k_ev = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="last_kline_1m",
        provider_event_ms=1000,
        provider_transaction_ms=None,
        observed_wall_utc_ms=ing2.observed_wall_utc_ms,
        observed_monotonic_ns=ing2.observed_monotonic_ns,
        available_at_ms=ing2.available_at_ms,
        source_stream_id="btcusdt@kline_1m",
        connection_epoch="ep-sym",
        source_sequence=1,
        payload_sha256=compute_sha256({"k": {"t": 1, "T": 2, "s": "BTCUSDT", "i": "1m", "o": "1", "c": "1", "h": "1", "l": "1", "v": "1", "x": True}}),
        payload={"k": {"t": 1, "T": 2, "s": "BTCUSDT", "i": "1m", "o": "1", "c": "1", "h": "1", "l": "1", "v": "1", "x": True}},
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256="0" * 64,
    )

    # Subvert symbol on kline object for test
    object.__setattr__(k_ev, "symbol", "ETHUSDT")

    with pytest.raises(PointInTimeViolationError, match="Cannot join: mark_event symbol 'BTCUSDT' != last_kline symbol 'ETHUSDT'"):
        join_mark_and_last(m_ev, k_ev, decision_at_ms=2000)


