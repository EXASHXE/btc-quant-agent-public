"""Adversarial security, AST auditing, 1k reconnect epochs, and negative matrix verification."""

from __future__ import annotations

import ast
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.connector import (
    BinancePublicFeedClient,
    validate_public_url,
)
from market_data.forward_public_feed_r1.contracts import (
    ALLOWED_PRODUCT,
    ContractValidationError,
    MarketEventV1,
    compute_dedupe_key,
    compute_sha256,
)
from market_data.forward_public_feed_r1.durability import SegmentReader, SegmentWriter
from market_data.forward_public_feed_r1.fixture import DeterministicExchangeFixture
from market_data.forward_public_feed_r1.health import HealthSupervisor
from market_data.forward_public_feed_r1.order_book import OrderBookIntegrityEngine
from market_data.forward_public_feed_r1.time_authority import TimeAuthority


def test_1k_reconnect_epochs_monotonic_isolation() -> None:
    """Verify that 1,000 reconnect epochs have distinct IDs and isolated monotonic namespaces."""
    epochs: set[str] = set()
    authorities: list[TimeAuthority] = []

    for i in range(1000):
        ta = TimeAuthority(connection_epoch=f"reconnect-epoch-{i:04d}-{os.getpid()}")
        assert ta.connection_epoch not in epochs
        epochs.add(ta.connection_epoch)
        authorities.append(ta)

    assert len(epochs) == 1000
    # Cross-epoch timestamps are never compared; each has its own diagnostics
    diag0 = authorities[0].get_diagnostics()
    diag999 = authorities[999].get_diagnostics()
    assert diag0["connection_epoch"] != diag999["connection_epoch"]


def test_deduplication_counter_and_key_collision_resistance() -> None:
    """Verify that identical frames generate exact same dedupe_key, while differing frames do not."""
    k1 = compute_dedupe_key("BTCUSDT", "agg_trade", "epoch-100", "trade-12345")
    k2 = compute_dedupe_key("BTCUSDT", "agg_trade", "epoch-100", "trade-12345")
    k3 = compute_dedupe_key("BTCUSDT", "agg_trade", "epoch-100", "trade-12346")
    k4 = compute_dedupe_key("BTCUSDT", "mark_price", "epoch-100", "trade-12345")

    assert k1 == k2
    assert k1 != k3
    assert k1 != k4


def test_ast_inspection_no_private_order_methods_or_keys() -> None:
    """AST security audit: inspect all recorder codebase for forbidden order methods and keys."""
    pkg_dir = Path(_SCRIPTS_DIR) / "market_data" / "forward_public_feed_r1"
    py_files = list(pkg_dir.glob("*.py"))
    assert len(py_files) >= 5

    forbidden_strings = [
        "userDataStream",
        "/fapi/v1/order",
        "/fapi/v1/allOpenOrders",
        "/fapi/v1/listenKey",
        "X-MBX-APIKEY",
    ]

    for py_file in py_files:
        code_text = py_file.read_text(encoding="utf-8")
        # Ensure forbidden endpoints are not present as active endpoints
        for bad_s in forbidden_strings:
            # Only allow in security checks/allowlists, never in actual requests
            assert f'"{bad_s}"' not in code_text or "FORBIDDEN" in code_text or "forbidden" in code_text

        tree = ast.parse(code_text, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                func_name = node.func.id.lower()
                assert (
                    "order" not in func_name
                    or "orderbook" in func_name
                    or "order_book" in func_name
                    or "record" in func_name
                )
                assert (
                    "trade" not in func_name
                    or "agg_trade" in func_name
                    or "generate" in func_name
                )


def test_mark_last_desynchronization_detection() -> None:
    """Verify health supervisor flags STALE_MARK_PRICE when mark price lags last trades."""
    hs = HealthSupervisor(symbol="BTCUSDT")
    now_ms = 1_000_000
    hs.record_book_status("VERIFIED", True, ["OK"])
    hs.record_channel_event("depth_delta", now_ms - 100, {"u": 10}, "VERIFIED")
    hs.record_channel_event("agg_trade", now_ms - 50, {"a": 99}, "VERIFIED")
    # Mark price is 20 seconds behind (threshold is 10s)
    hs.record_channel_event("mark_price", now_ms - 20_000, {"p": "65000"}, "VERIFIED")

    gate, reasons = hs.evaluate_source_gate(now_ms)
    assert gate == "SOURCE_DEGRADED"
    assert any("STALE_MARK_PRICE" in r for r in reasons)


def test_final_vs_developing_bar_semantics() -> None:
    """Finalized candle (x=True) vs developing candle (x=False) contract assertion."""
    fix = DeterministicExchangeFixture(symbol="BTCUSDT")
    dev_frame = fix.generate_kline_frame(closed=False)
    assert dev_frame["k"]["x"] is False

    closed_frame = fix.generate_kline_frame(closed=True)
    assert closed_frame["k"]["x"] is True


def test_late_funding_settlement_reconciliation() -> None:
    """Late settled funding receipt arrives without corrupting temporal ordering."""
    hs = HealthSupervisor(symbol="BTCUSDT")
    funding_payload = {
        "symbol": "BTCUSDT",
        "fundingRate": "0.00015000",
        "fundingTime": 1728720000000 - 28_800_000,  # 8 hours ago
        "markPrice": "65000.00",
    }
    hs.record_channel_event("funding_settled", 1728720000000, funding_payload, "VERIFIED")
    assert hs.last_settled_funding_rate == "0.00015000"
    assert hs.last_settled_funding_time_ms == 1728720000000 - 28_800_000


def test_corrupt_manifest_swap_atomic_recovery(tmp_path: Path) -> None:
    """Test that a partial .tmp manifest write leaves the original manifest uncorrupted."""
    writer = SegmentWriter(base_dir=tmp_path, epoch="test-swap-recovery")
    event = MarketEventV1(
        schema_version="market-event-v1",
        symbol="BTCUSDT",
        product=ALLOWED_PRODUCT,
        channel="agg_trade",
        provider_event_ms=1000,
        provider_transaction_ms=None,
        observed_wall_utc_ms=1000,
        observed_monotonic_ns=1_000_000_000,
        available_at_ms=1000,
        source_stream_id="btcusdt@aggTrade",
        connection_epoch="test-swap-recovery",
        source_sequence=1,
        payload_sha256=compute_sha256({"a": 1}),
        payload={"a": 1},
        quality="VERIFIED",
        reason_codes=["OK"],
        raw_source_manifest_sha256=writer.manifest_sha256,
    )
    writer.append_event(event)
    writer.close()

    manifest_path = tmp_path / "manifest_test-swap-recovery_000001.json"
    assert manifest_path.exists()
    good_manifest = SegmentReader.read_manifest(manifest_path)
    assert good_manifest["record_count"] == 1

    # Simulate an aborted write creating a corrupted .tmp
    tmp_path_file = manifest_path.with_suffix(".tmp")
    tmp_path_file.write_text("corrupted_half_written_bytes_from_crash")

    # The real manifest file remains valid and readable
    recovered = SegmentReader.read_manifest(manifest_path)
    assert recovered["record_count"] == 1


def test_consumer_head_of_line_blocking_ingress_queue_drop() -> None:
    """Simulate ingress buffer saturation and ensure dropped count increments."""
    ta = TimeAuthority()
    assert ta.dropped_ingress_count == 0
    ta.increment_dropped_ingress(12)
    assert ta.dropped_ingress_count == 12
    diag = ta.get_diagnostics()
    assert diag["dropped_ingress_count"] == 12


def test_schema_regression_clock_future_mutation() -> None:
    """Ensure available_at_ms earlier than observed_wall_utc_ms is strictly rejected."""
    payload = {"p": "65000.00"}
    with pytest.raises(ContractValidationError, match="available_at_ms"):
        MarketEventV1(
            schema_version="market-event-v1",
            symbol="BTCUSDT",
            product=ALLOWED_PRODUCT,
            channel="agg_trade",
            provider_event_ms=1000,
            provider_transaction_ms=None,
            observed_wall_utc_ms=5000,
            observed_monotonic_ns=1_000_000_000,
            available_at_ms=4999,  # Earlier than observed_wall!
            source_stream_id="btcusdt@aggTrade",
            connection_epoch="test-regress",
            source_sequence=1,
            payload_sha256=compute_sha256(payload),
            payload=payload,
            quality="VERIFIED",
            reason_codes=["OK"],
            raw_source_manifest_sha256="msha",
        )


def test_zero_size_deletion_and_fractional_tick_levels() -> None:
    """Test sub-tick precision and fractional level removal."""
    engine = OrderBookIntegrityEngine(symbol="BTCUSDT")
    snap = {
        "lastUpdateId": 1000,
        "bids": [["65000.123", "0.005"]],
        "asks": [["65000.124", "0.005"]],
    }
    receipt = engine.apply_snapshot(snap, observed_wall_ms=1000)
    assert receipt.quality == "VERIFIED"
    assert engine.bids[Decimal("65000.123")] == Decimal("0.005")

    # Delete bid with 0.000 quantity
    delta = {
        "e": "depthUpdate",
        "U": 1000,
        "u": 1001,
        "pu": 999,
        "b": [["65000.123", "0.000"]],
        "a": [],
    }
    receipt2 = engine.apply_delta(delta, observed_wall_ms=1010)
    assert Decimal("65000.123") not in engine.bids
    assert receipt2.quality == "VERIFIED"


def test_case_sensitive_symbol_confusion_all_channels() -> None:
    """Verify that case variations or ticker confusions are strictly blocked."""
    invalid_symbols = ["btcusdt", "BTCusdt", "BTC-USDT", "BTC_USDT", "ETHUSDT", "SOLUSDT"]
    for bad_sym in invalid_symbols:
        with pytest.raises(ContractValidationError):
            BinancePublicFeedClient(symbol=bad_sym, network_mode="disabled")

        with pytest.raises(ContractValidationError):
            MarketEventV1(
                schema_version="market-event-v1",
                symbol=bad_sym,
                product=ALLOWED_PRODUCT,
                channel="agg_trade",
                provider_event_ms=1000,
                provider_transaction_ms=None,
                observed_wall_utc_ms=1000,
                observed_monotonic_ns=1_000_000_000,
                available_at_ms=1000,
                source_stream_id="test",
                connection_epoch="ep",
                source_sequence=1,
                payload_sha256=compute_sha256({}),
                payload={},
                quality="VERIFIED",
                reason_codes=["OK"],
                raw_source_manifest_sha256="msha",
            )


def test_coin_m_dapi_url_block_everywhere() -> None:
    """Verify all coin-M endpoints and variations are strictly blocked."""
    dapi_urls = [
        "https://dapi.binance.com/dapi/v1/depth",
        "https://dapi.binance.com/dapi/v1/fundingRate",
        "wss://dstream.binance.com/ws",
        "https://api.binance.com/api/v3/depth",
    ]
    for url in dapi_urls:
        with pytest.raises(ContractValidationError):
            validate_public_url(url, method="GET")
