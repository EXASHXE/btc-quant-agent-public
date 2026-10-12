"""Category 6: C Composite BAR Adapter & G1 State Machine Unit Tests.

Covers:
- C composite BAR schema validation (exact required keys)
- Rejection of missing/extra keys and unclosed bars
- PIT causal invariants: available_at_ms >= bar_close_ms
- Translation of composite envelope to G1 BAR event via MarketPitPort
- G1 state engine ingest, transition immutability, and deterministic WAL replay
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

from scripts.integration.market_event_bridge_r2.c_composite_bar import CCompositeBarBuilder
from scripts.integration.market_event_bridge_r2.mark_aggregator import DerivedMark1MBar

_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from scripts.integration.market_event_bridge_r2.portable_ci_refs import ensure_portable_c_on_path

ensure_portable_c_on_path()


def _make_mock_mark_bar(
    bar_open_ms: int = 1728720000000,
    close: float = 64150.0,
    available_at_ms: int = 1728720060100,
) -> DerivedMark1MBar:
    return DerivedMark1MBar(
        symbol="BTCUSDT",
        bar_open_ms=bar_open_ms,
        bar_close_ms=bar_open_ms + 59999,
        closed=True,
        open=64100.0,
        high=64200.0,
        low=64050.0,
        close=close,
        sample_count=55,
        derived_available_at_ms=available_at_ms,
        feature_known_at_ms=available_at_ms,
        quality="VERIFIED",
        reason_codes=("OK",),
        parent_event_sha256=("sha1", "sha2"),
        raw_source_manifest_sha256="testmarkmanifest",
    )


def test_c_composite_builder_initialization():
    builder_default = CCompositeBarBuilder()
    assert builder_default.stream_id == "SYNTHETIC_LOCAL_PIT_V1"
    assert len(builder_default.manifest_sha256) == 64

    builder_custom = CCompositeBarBuilder(
        stream_id="btcusdt@kline_1m",
        raw_manifest_sha256="custom_manifest_hash_123456",
    )
    assert builder_custom.stream_id == "btcusdt@kline_1m"
    assert builder_custom.manifest_sha256 == "custom_manifest_hash_123456"


def test_c_composite_builder_valid_envelope():
    builder = CCompositeBarBuilder(
        stream_id="btcusdt@kline_1m",
        raw_manifest_sha256="manifest_sha_test",
    )
    raw_kline = {
        "e": "kline",
        "E": 1728720060000,
        "s": "BTCUSDT",
        "k": {
            "t": 1728720000000,
            "T": 1728720059999,
            "s": "BTCUSDT",
            "i": "1m",
            "f": 100,
            "L": 200,
            "o": "64000.00",
            "c": "64100.00",
            "h": "64150.00",
            "l": "63950.00",
            "v": "10.5",
            "x": True,
        },
    }
    mark_bar = _make_mock_mark_bar(1728720000000, close=64080.0)
    env = builder.build_composite_bar_envelope(
        raw_kline_payload=raw_kline,
        derived_mark_bar=mark_bar,
        kline_available_at_ms=1728720060050,
        observed_monotonic_ns=1_000_000,
        connection_epoch=2,
        source_sequence=200,
    )

    assert env["schema_version"] == "market-event-v1"
    assert env["symbol"] == "BTCUSDT"
    assert env["product"] == "BINANCE_USDT_M_PERP"
    assert env["channel"] == "last_kline_1m"
    assert env["connection_epoch"] == 2
    assert env["source_sequence"] == 200
    assert env["quality"] == "VERIFIED"
    assert env["reason_codes"] == ["OK"]


def test_c_composite_payload_exact_keys():
    builder = CCompositeBarBuilder()
    raw_kline = {
        "k": {
            "t": 1728720000000,
            "o": "64000.00",
            "c": "64100.00",
            "h": "64150.00",
            "l": "63950.00",
        }
    }
    mark_bar = _make_mock_mark_bar(1728720000000)
    env = builder.build_composite_bar_envelope(
        raw_kline_payload=raw_kline,
        derived_mark_bar=mark_bar,
        kline_available_at_ms=1728720060000,
        observed_monotonic_ns=1_000_000,
    )
    expected_keys = {
        "bar_open_ms",
        "bar_close_ms",
        "closed",
        "last_open",
        "last_high",
        "last_low",
        "last_close",
        "mark_close",
        "event_id",
    }
    assert set(env["payload"].keys()) == expected_keys
    assert env["payload"]["closed"] is True
    assert env["payload"]["mark_close"] == "64150.0"


def test_c_composite_builder_payload_hash_integrity():
    builder = CCompositeBarBuilder()
    raw_kline = {"k": {"t": 1728720000000, "o": "1", "h": "2", "l": "1", "c": "2"}}
    mark_bar = _make_mock_mark_bar(1728720000000)
    env = builder.build_composite_bar_envelope(
        raw_kline_payload=raw_kline,
        derived_mark_bar=mark_bar,
        kline_available_at_ms=1728720060000,
        observed_monotonic_ns=1_000_000,
    )
    expected_hash = hashlib.sha256(
        json.dumps(env["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert env["payload_sha256"] == expected_hash


def test_c_composite_builder_causal_available_at_ms():
    builder = CCompositeBarBuilder()
    raw_kline = {"k": {"t": 1728720000000}}
    # mark bar available at 1728720060200, kline at 1728720060100, close is 1728720059999
    mark_bar = _make_mock_mark_bar(1728720000000, available_at_ms=1728720060200)
    env = builder.build_composite_bar_envelope(
        raw_kline_payload=raw_kline,
        derived_mark_bar=mark_bar,
        kline_available_at_ms=1728720060100,
        observed_monotonic_ns=1_000_000,
    )
    assert env["available_at_ms"] == 1728720060200
    assert env["observed_wall_utc_ms"] == 1728720060200


def test_c_composite_builder_minute_boundary_alignment():
    builder = CCompositeBarBuilder()
    # If raw kline open is unaligned (e.g. 1728720000123)
    raw_kline = {"k": {"t": 1728720000123}}
    mark_bar = _make_mock_mark_bar(1728720000000)
    env = builder.build_composite_bar_envelope(
        raw_kline_payload=raw_kline,
        derived_mark_bar=mark_bar,
        kline_available_at_ms=1728720060000,
        observed_monotonic_ns=1_000_000,
    )
    assert env["payload"]["bar_open_ms"] == 1728720000000
    assert env["payload"]["bar_close_ms"] == 1728720059999
    assert env["payload"]["bar_open_ms"] % 60000 == 0


def test_c_composite_builder_sequence_and_epoch():
    builder = CCompositeBarBuilder()
    raw_kline = {"k": {"t": 1728720000000}}
    mark_bar = _make_mock_mark_bar(1728720000000)
    env = builder.build_composite_bar_envelope(
        raw_kline_payload=raw_kline,
        derived_mark_bar=mark_bar,
        kline_available_at_ms=1728720060000,
        observed_monotonic_ns=500,
        connection_epoch=7,
        source_sequence=42,
    )
    assert env["connection_epoch"] == 7
    assert env["source_sequence"] == 42


def test_c_market_pit_port_accepts_composite_bar():
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort

    builder = CCompositeBarBuilder(
        stream_id="btcusdt@kline_1m",
        raw_manifest_sha256="manifest_sha_test",
    )
    port = MarketPitPort(
        expected_stream_id="btcusdt@kline_1m",
        expected_manifest_sha256="manifest_sha_test",
    )
    raw_kline = {
        "k": {
            "t": 1728720000000,
            "o": "64000.00",
            "h": "64150.00",
            "l": "63950.00",
            "c": "64100.00",
        }
    }
    mark_bar = _make_mock_mark_bar(1728720000000, close=64080.0)
    env = builder.build_composite_bar_envelope(
        raw_kline_payload=raw_kline,
        derived_mark_bar=mark_bar,
        kline_available_at_ms=1728720060000,
        observed_monotonic_ns=100,
        connection_epoch=1,
        source_sequence=1,
    )

    res = port.ingest_envelope(env)
    assert res["status"] == "ACCEPTED"
    assert res["g1_event"] is not None
    assert res["g1_event"]["kind"] == "BAR"


def test_c_market_pit_port_translates_bar_to_g1_event():
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort

    builder = CCompositeBarBuilder(
        stream_id="btcusdt@kline_1m",
        raw_manifest_sha256="manifest_sha_test",
    )
    port = MarketPitPort(
        expected_stream_id="btcusdt@kline_1m",
        expected_manifest_sha256="manifest_sha_test",
    )
    raw_kline = {
        "k": {
            "t": 1728720000000,
            "o": "64000.00",
            "h": "64200.00",
            "l": "63900.00",
            "c": "64150.00",
        }
    }
    mark_bar = _make_mock_mark_bar(1728720000000, close=64120.0)
    env = builder.build_composite_bar_envelope(
        raw_kline_payload=raw_kline,
        derived_mark_bar=mark_bar,
        kline_available_at_ms=1728720060000,
        observed_monotonic_ns=100,
    )
    res = port.ingest_envelope(env)
    g1 = res["g1_event"]
    assert g1["id"] == "BAR-28812000"
    assert g1["payload"]["source"] == "SYNTHETIC_V1"
    assert g1["payload"]["open_time"] == 1728720000000
    assert g1["payload"]["close_time"] == 1728720059999
    assert g1["payload"]["last_open"] == "64000.00"
    assert g1["payload"]["last_high"] == "64200.00"
    assert g1["payload"]["last_low"] == "63900.00"
    assert g1["payload"]["last_close"] == "64150.00"
    assert g1["payload"]["mark_close"] == "64120.0"


def test_c_market_pit_port_rejects_missing_payload_key():
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort, SafetyViolation

    builder = CCompositeBarBuilder(stream_id="btcusdt@kline_1m", raw_manifest_sha256="m1")
    port = MarketPitPort(expected_stream_id="btcusdt@kline_1m", expected_manifest_sha256="m1")
    raw_kline = {"k": {"t": 1728720000000, "o": "1", "h": "2", "l": "1", "c": "2"}}
    mark_bar = _make_mock_mark_bar(1728720000000)
    env = builder.build_composite_bar_envelope(raw_kline, mark_bar, 1728720060000, 100)
    # Remove required key
    del env["payload"]["mark_close"]
    env["payload_sha256"] = hashlib.sha256(
        json.dumps(env["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    with pytest.raises(SafetyViolation, match="BAR_PAYLOAD_SCHEMA_INVALID"):
        port.ingest_envelope(env)


def test_c_market_pit_port_rejects_unclosed_bar():
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort, SafetyViolation

    builder = CCompositeBarBuilder(stream_id="btcusdt@kline_1m", raw_manifest_sha256="m1")
    port = MarketPitPort(expected_stream_id="btcusdt@kline_1m", expected_manifest_sha256="m1")
    raw_kline = {"k": {"t": 1728720000000, "o": "1", "h": "2", "l": "1", "c": "2"}}
    mark_bar = _make_mock_mark_bar(1728720000000)
    env = builder.build_composite_bar_envelope(raw_kline, mark_bar, 1728720060000, 100)
    env["payload"]["closed"] = False
    env["payload_sha256"] = hashlib.sha256(
        json.dumps(env["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    with pytest.raises(SafetyViolation, match="BAR_INCOMPLETE_UNCLOSED"):
        port.ingest_envelope(env)


def test_c_market_pit_port_rejects_invalid_ohlc():
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort, SafetyViolation

    builder = CCompositeBarBuilder(stream_id="btcusdt@kline_1m", raw_manifest_sha256="m1")
    port = MarketPitPort(expected_stream_id="btcusdt@kline_1m", expected_manifest_sha256="m1")
    # Low > High
    raw_kline = {"k": {"t": 1728720000000, "o": "100", "h": "110", "l": "120", "c": "105"}}
    mark_bar = _make_mock_mark_bar(1728720000000)
    env = builder.build_composite_bar_envelope(raw_kline, mark_bar, 1728720060000, 100)

    with pytest.raises(SafetyViolation, match="BAR_OHLC_INVALID"):
        port.ingest_envelope(env)


def test_c_market_pit_port_rejects_pit_violation():
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort, SafetyViolation

    builder = CCompositeBarBuilder(stream_id="btcusdt@kline_1m", raw_manifest_sha256="m1")
    port = MarketPitPort(expected_stream_id="btcusdt@kline_1m", expected_manifest_sha256="m1")
    raw_kline = {"k": {"t": 1728720000000, "o": "100", "h": "110", "l": "90", "c": "105"}}
    mark_bar = _make_mock_mark_bar(1728720000000)
    env = builder.build_composite_bar_envelope(raw_kline, mark_bar, 1728720060000, 100)
    # Tamper available_at_ms and provider_event_ms to be earlier than bar_close_ms
    env["available_at_ms"] = 1728720050000
    env["observed_wall_utc_ms"] = 1728720050000
    env["provider_event_ms"] = 1728720050000
    env["provider_transaction_ms"] = 1728720050000

    with pytest.raises(SafetyViolation, match="BAR_PIT_INVALID"):
        port.ingest_envelope(env)


def test_g1_reducer_transitions_on_translated_bar():
    from scripts.g1_offline_preview_r1.model import initial_state
    from scripts.g1_offline_preview_r1.reducer import transition
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort

    builder = CCompositeBarBuilder(stream_id="btcusdt@kline_1m", raw_manifest_sha256="m1")
    port = MarketPitPort(expected_stream_id="btcusdt@kline_1m", expected_manifest_sha256="m1")
    raw_kline = {
        "k": {
            "t": 0,
            "o": "60000.00",
            "h": "60100.00",
            "l": "59900.00",
            "c": "60050.00",
        }
    }
    mark_bar = _make_mock_mark_bar(bar_open_ms=0, close=60040.0, available_at_ms=59999)
    env = builder.build_composite_bar_envelope(raw_kline, mark_bar, 59999, 100)
    res = port.ingest_envelope(env)
    g1_event = res["g1_event"]

    s0 = initial_state([])
    s1 = transition(s0, g1_event)

    assert s1["last_at"] == 59999
    assert s1["last_bar"] is not None
    assert s1["last_bar"]["open_time"] == 0
    assert s1["last_bar"]["close_time"] == 59999
    assert s1["last_bar"]["mark_close"] == "60040.0"


def test_g1_state_immutability_and_wal_replay():
    from scripts.g1_offline_preview_r1.model import initial_state
    from scripts.g1_offline_preview_r1.reducer import digest, transition
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort

    builder = CCompositeBarBuilder(stream_id="btcusdt@kline_1m", raw_manifest_sha256="m1")
    port = MarketPitPort(expected_stream_id="btcusdt@kline_1m", expected_manifest_sha256="m1")
    raw_kline = {
        "k": {
            "t": 0,
            "o": "60000.00",
            "h": "60100.00",
            "l": "59900.00",
            "c": "60050.00",
        }
    }
    mark_bar = _make_mock_mark_bar(bar_open_ms=0, close=60040.0, available_at_ms=59999)
    env = builder.build_composite_bar_envelope(raw_kline, mark_bar, 59999, 100)
    res = port.ingest_envelope(env)
    g1_event = res["g1_event"]

    s0 = initial_state([])
    d0_before = digest(s0)
    s1_a = transition(s0, g1_event)
    d0_after = digest(s0)
    # s0 must not have been mutated
    assert d0_before == d0_after

    # Deterministic replay produces bit-for-bit identical state
    s1_b = transition(s0, g1_event)
    assert digest(s1_a) == digest(s1_b)
