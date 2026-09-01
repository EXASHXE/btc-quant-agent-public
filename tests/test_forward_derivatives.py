from __future__ import annotations

import sqlite3
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from btc_quant_agent.config import DataConfig
from btc_quant_agent.data.binance import BinanceDataError, BinancePublicClient, DerivativeCollection
from btc_quant_agent.data.derivatives import HistoricalDerivativeStore
from btc_quant_agent.data.forward_store import (
    CADENCE_MS,
    POST_BOUNDARY_DELAY_MS,
    ForwardDerivativeRecord,
    ForwardDerivativeStore,
    ForwardStoreConflict,
    next_collection_time_ms,
)
from btc_quant_agent.domain import DerivativesSnapshot


def _payload(path: str) -> object:
    payloads: dict[str, object] = {
        "/fapi/v1/premiumIndex": {
            "markPrice": "100.5",
            "indexPrice": "100.0",
            "lastFundingRate": "0.0001",
            "time": 900,
        },
        "/fapi/v1/openInterest": {"openInterest": "1234.5", "time": 901},
        "/futures/data/openInterestHist": [
            {"sumOpenInterest": "1000", "timestamp": 800},
            {"sumOpenInterest": "1100", "timestamp": 900},
        ],
        "/futures/data/takerlongshortRatio": [{"buySellRatio": "1.2", "timestamp": 902}],
        "/futures/data/globalLongShortAccountRatio": [{"longShortRatio": "1.1", "timestamp": 903}],
        "/futures/data/basis": [{"basisRate": "0.001", "timestamp": 904}],
        "/fapi/v1/depth": {
            "E": 905,
            "bids": [["100", "2"]],
            "asks": [["101", "1"]],
        },
    }
    return payloads[path]


def _collection(observed_at_ms: int = 900_000) -> DerivativeCollection:
    snapshot = DerivativesSnapshot(
        observed_at_ms=observed_at_ms,
        mark_price=100.5,
        index_price=100.0,
        premium_bps=50.0,
        funding_rate=0.0001,
        funding_time_ms=observed_at_ms - 5,
        open_interest=1234.5,
        open_interest_time_ms=observed_at_ms - 4,
        open_interest_change_pct=0.1,
        taker_buy_sell_ratio=1.2,
        taker_time_ms=observed_at_ms - 3,
        basis_rate=0.001,
        basis_time_ms=observed_at_ms - 2,
        long_short_account_ratio=1.1,
        long_short_time_ms=observed_at_ms - 1,
    )
    availability = {
        "mark_price": True,
        "index_price": True,
        "premium_bps": True,
        "funding_rate": True,
        "open_interest": True,
        "open_interest_change_pct": True,
        "taker_buy_sell_ratio": True,
        "basis_rate": True,
        "long_short_account_ratio": True,
        "order_book_imbalance": False,
        "spread_bps": False,
    }
    return DerivativeCollection(
        observed_at_ms - 10,
        observed_at_ms,
        snapshot,
        tuple(availability),
        availability,
        {},
    )


def _record(observed_at_ms: int = 900_000, collection_id: str = "run-1") -> ForwardDerivativeRecord:
    return ForwardDerivativeRecord.from_collection(
        "BTCUSDT", collection_id, _collection(observed_at_ms)
    )


def test_snapshot_observed_at_is_after_collection_completion() -> None:
    client = BinancePublicClient(DataConfig())
    calls: list[str] = []

    def get(path: str, _params: object) -> object:
        calls.append(path)
        return _payload(path)

    with (
        patch.object(client, "_get", side_effect=get),
        patch("btc_quant_agent.data.binance.time.time", side_effect=[1.0, 2.0]),
    ):
        collection = client.collect_derivatives("BTCUSDT")
    assert len(calls) == 6
    assert collection.collection_started_at_ms == 1_000
    assert collection.observed_at_ms == 2_000
    assert collection.snapshot.observed_at_ms == 2_000


def test_source_timestamps_are_preserved() -> None:
    client = BinancePublicClient(DataConfig())
    with (
        patch.object(client, "_get", side_effect=lambda path, _params: _payload(path)),
        patch("btc_quant_agent.data.binance.time.time", side_effect=[1.0, 2.0]),
    ):
        snapshot = client.collect_derivatives("BTCUSDT").snapshot
    assert snapshot.funding_time_ms == 900
    assert snapshot.open_interest_time_ms == 901
    assert snapshot.taker_time_ms == 902
    assert snapshot.long_short_time_ms == 903
    assert snapshot.basis_time_ms == 904


def test_partial_endpoint_failure_is_recorded() -> None:
    client = BinancePublicClient(DataConfig())

    def get(path: str, _params: object) -> object:
        if path == "/fapi/v1/openInterest":
            raise BinanceDataError("OI unavailable")
        return _payload(path)

    with (
        patch.object(client, "_get", side_effect=get),
        patch("btc_quant_agent.data.binance.time.time", side_effect=[1.0, 2.0]),
    ):
        collection = client.collect_derivatives("BTCUSDT")
    assert collection.snapshot.open_interest is None
    assert collection.field_availability["open_interest"] is False
    assert "open_interest" in collection.endpoint_errors


def test_order_book_collection_default_off() -> None:
    client = BinancePublicClient(DataConfig())
    paths: list[str] = []

    def get(path: str, _params: object) -> object:
        paths.append(path)
        return _payload(path)

    with (
        patch.object(client, "_get", side_effect=get),
        patch("btc_quant_agent.data.binance.time.time", side_effect=[1.0, 2.0]),
    ):
        collection = client.collect_derivatives("BTCUSDT")
    assert "/fapi/v1/depth" not in paths
    assert "order_book_imbalance" not in collection.attempted_fields
    assert collection.snapshot.order_book_imbalance is None


def test_forward_store_is_append_only_and_wal(tmp_path: Path) -> None:
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    assert store.append(_record())
    with sqlite3.connect(store.path) as connection:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        row = connection.execute(
            "SELECT mark_price FROM derivative_snapshots WHERE symbol='BTCUSDT'"
        ).fetchone()
    assert str(mode).lower() == "wal"
    assert row == (100.5,)


def test_forward_store_duplicate_exact_row_is_idempotent(tmp_path: Path) -> None:
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    assert store.append(_record(collection_id="run-1"))
    assert store.append(_record(collection_id="run-2")) is False
    assert store.count() == 1


def test_forward_store_conflicting_duplicate_fails(tmp_path: Path) -> None:
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    original = _collection()
    store.append(ForwardDerivativeRecord.from_collection("BTCUSDT", "run-1", original))
    changed = replace(original, snapshot=replace(original.snapshot, mark_price=101.0))
    with pytest.raises(ForwardStoreConflict, match="existing row preserved"):
        store.append(ForwardDerivativeRecord.from_collection("BTCUSDT", "run-2", changed))
    assert store.audit()["conflict_count"] == 1


def test_forward_store_ordering(tmp_path: Path) -> None:
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    store.append(_record(1_800_000, "later"))
    store.append(_record(900_000, "earlier"))
    report = store.audit()
    assert report["timestamp_ordered"] is True
    assert report["duplicate_count"] == 0


def test_forward_store_export_is_backward_asof_compatible(tmp_path: Path) -> None:
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    store.append(_record())
    csv_path = tmp_path / "derivatives.csv"
    manifest_path = tmp_path / "manifest.json"
    manifest = store.export(csv_path, manifest_path)
    historical = HistoricalDerivativeStore.from_csv(csv_path)
    assert historical.as_snapshots()[0] == _collection().snapshot
    assert manifest["row_count"] == 1
    assert len(manifest["checksum_sha256"]) == 64


def test_derivative_audit_detects_gap_and_never_backfills(tmp_path: Path) -> None:
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    store.append(_record(CADENCE_MS, "run-1"))
    store.append(_record(CADENCE_MS * 4, "run-2"))
    report = store.audit()
    assert report["gap_count"] == 1
    assert report["largest_gap_slots"] == 2
    assert report["backfilled_rows"] == 0
    assert store.count() == 2


def test_status_reports_field_coverage(tmp_path: Path) -> None:
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    store.append(_record())
    status = store.status(scheduler={"detected": True, "active": False})
    assert status["required_field_coverage"]["funding_rate"] == 1.0
    assert status["required_field_coverage"]["open_interest"] == 1.0
    assert status["scheduler_detected"] is True
    assert status["scheduler_active"] is False
    assert status["health"] == "DEGRADED"
    assert status["research_eligibility"] == "FAILED_GAP_GATE_TERMINAL"
    assert status["research_gate"]["minimum_days"] == 30
    assert status["research_gate"]["minimum_snapshots"] == 2_500


def test_boundary_scheduler_computes_next_utc_quarter_hour() -> None:
    assert next_collection_time_ms(0) == CADENCE_MS + POST_BOUNDARY_DELAY_MS
    assert next_collection_time_ms(CADENCE_MS - 1) == CADENCE_MS + POST_BOUNDARY_DELAY_MS
    assert next_collection_time_ms(CADENCE_MS) == 2 * CADENCE_MS + POST_BOUNDARY_DELAY_MS


def test_no_market_data_is_committed_to_git() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "data"], check=True, capture_output=True, text=True
    ).stdout
    assert tracked == ""
