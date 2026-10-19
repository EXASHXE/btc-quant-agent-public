"""Focused tests for DATA-C1 canonical materialization and queries."""

import csv
import hashlib
import json
import sqlite3
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from scripts.data.catalog import materialize_history, normalize, query


@pytest.fixture
def spot_fixture_zip(tmp_path):
    zip_path = tmp_path / "BTCUSDT-1m-2021-01.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        content = "1609459200000,28923.63,28961.66,28913.12,28961.66,27.45,1609459259999,794382.04,1292,16.77,485390.82,0\n"
        content += "1609459260000,28961.67,29017.50,28961.01,29009.91,58.47,1609459319999,1695802.89,1651,33.73,978176.46,0\n"
        z.writestr("BTCUSDT-1m-2021-01.csv", content)
    return zip_path


def test_spot_zip_reconstructs_genuine_ohlc_not_volume_only(spot_fixture_zip, tmp_path):
    source = {
        "source_id": "test_spot_01",
        "path": str(spot_fixture_zip),
        "exchange": "binance",
        "asset": "BTC",
        "symbol": "BTCUSDT",
        "product": "SPOT",
        "family": "spot_klines",
        "interval": "1m",
        "period": "2021-01",
        "calendar_timezone": "UTC",
        "raw_sha256": materialize_history.digest(spot_fixture_zip),
    }

    mat = materialize_history.Materializer(catalog_db=tmp_path / "cat.db", output_dir=tmp_path / "c1")
    rcpt = mat.materialize_one(source)

    assert rcpt["status"] == "SUCCESS"
    assert rcpt["row_count"] == 2

    table = pq.ParquetFile(rcpt["partition_path"]).read()
    pylist = table.to_pylist()
    first = pylist[0]

    assert first["open"] == 28923.63
    assert first["high"] == 28961.66
    assert first["low"] == 28913.12
    assert first["close"] == 28961.66
    assert first["base_volume"] == 27.45
    assert first["quote_volume"] == 794382.04
    assert first["low"] <= first["open"] <= first["high"]
    assert first["low"] <= first["close"] <= first["high"]


def test_duplicated_2026_month_conflict_resolution(tmp_path):
    old_source = {
        "source_id": "old_2026_04",
        "path": "/path/old.parquet",
        "exchange": "binance",
        "asset": "BTC",
        "product": "USD_M_PERPETUAL",
        "family": "candles",
        "interval": "1m",
        "period": "2026-04",
        "priority": 90,
    }
    new_source = {
        "source_id": "new_2026_04",
        "path": "/path/new.zip",
        "exchange": "binance",
        "asset": "BTC",
        "product": "USD_M_PERPETUAL",
        "family": "klines",
        "interval": "1m",
        "period": "2026-04",
        "priority": 100,
    }

    mat = materialize_history.Materializer(catalog_db=tmp_path / "cat.db", output_dir=tmp_path / "c1")
    planned = mat._plan_materialization([old_source, new_source])

    # Only new_source should be planned among perp 1m, old is superseded
    perp_planned = [s for s in planned if s["product"] == "USD_M_PERPETUAL" and s["period"] == "2026-04"]
    assert len(perp_planned) == 1
    assert perp_planned[0]["source_id"] == "new_2026_04"
    assert len(mat.conflict_resolutions) == 1
    conf = mat.conflict_resolutions[0]
    assert conf["preferred_source_id"] == "new_2026_04"
    assert conf["superseded_source_id"] == "old_2026_04"
    assert conf["max_price_diff"] == 0.0


def test_independent_gap_detection_and_consistency(tmp_path):
    zip_path = tmp_path / "gap.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        t0 = 1609459200000  # 00:00
        t1 = 1609459200000 + 5 * 60000  # 00:05 (4 missing minutes)
        content = f"{t0},10,12,9,11,1,{t0+59999},11,1,1,11,0\n"
        content += f"{t1},11,13,10,12,1,{t1+59999},12,1,1,12,0\n"
        z.writestr("gap.csv", content)

    source = {
        "source_id": "gap_test",
        "path": str(zip_path),
        "exchange": "binance",
        "asset": "BTC",
        "symbol": "BTCUSDT",
        "product": "USD_M_PERPETUAL",
        "family": "klines",
        "interval": "1m",
        "period": "2026-04",
        "calendar_timezone": "UTC",
        "raw_sha256": materialize_history.digest(zip_path),
    }

    mat = materialize_history.Materializer(catalog_db=tmp_path / "cat.db", output_dir=tmp_path / "c1")
    rcpt = mat.materialize_one(source)

    assert rcpt["row_count"] == 2
    assert rcpt["gaps_count"] == 4
    assert len(mat.missing_intervals) == 1
    assert mat.missing_intervals[0]["missing_intervals_sum"] == 4


def test_multi_clock_granularity_no_fake_upsample():
    # 5m metrics row
    metric_source = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "asset": "BTC",
        "product": "USD_M_PERPETUAL",
        "family": "metrics",
        "interval": "5m",
        "source_id": "m1",
        "raw_sha256": "h",
    }
    m = normalize.normalize(
        metric_source,
        {
            "create_time": "2026-04-02 00:55:00",
            "symbol": "BTCUSDT",
            "sum_open_interest": "1000",
            "sum_toptrader_long_short_ratio": "1.25",
        },
    )
    assert m["interval"] == "5m"
    assert m["base_open_interest"] == 1000.0
    assert m["top_position_long_short_ratio"] == 1.25

    # 8h funding row
    funding_source = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "asset": "BTC",
        "product": "USD_M_PERPETUAL",
        "family": "fundingRate",
        "interval": "8h",
        "source_id": "f1",
        "raw_sha256": "h",
    }
    f = normalize.normalize(
        funding_source,
        {
            "calc_time": "1775088000000",
            "funding_interval_hours": "8",
            "last_funding_rate": "-0.00015",
        },
    )
    assert f["interval"] == "8h"
    assert f["funding_interval_hours"] == 8
    assert f["funding_rate"] == -0.00015


def test_okx_local_day_to_true_utc_event_epoch():
    okx_source = {
        "exchange": "okx",
        "symbol": "BTC-USDT-SWAP",
        "asset": "BTC",
        "product": "OKX_SWAP",
        "family": "candlesticks",
        "interval": "1m",
        "period": "2026-04-01",  # Local UTC+8 file date
        "source_id": "okx1",
        "raw_sha256": "h",
    }
    row = {
        "instrument_name": "BTC-USDT-SWAP",
        "open_time": "1774972800000",  # 2026-03-31 16:00:00 UTC
        "open": "66000",
        "high": "66100",
        "low": "65900",
        "close": "66050",
        "vol": "10",
        "vol_quote": "660000",
        "confirm": "1",
    }
    item = normalize.normalize(okx_source, row)
    start_dt = datetime.fromtimestamp(item["interval_start_utc"] / 10**6, UTC)
    assert start_dt.isoformat() == "2026-03-31T16:00:00+00:00"
    assert item["product_type"] == "OKX_SWAP"


def test_causal_asof_zero_future_funding_or_return_leakage(tmp_path):
    cutoff_dt = datetime(2026, 4, 2, 1, 0, tzinfo=UTC)
    cutoff_us = int(cutoff_dt.timestamp() * 10**6)

    # Future funding settlement at C + 1 minute
    future_funding = {
        "event_ts_utc": datetime.fromtimestamp((cutoff_us + 60 * 10**6) / 10**6, UTC),
        "funding_rate": 0.05,
        "funding_interval_hours": 8,
    }

    engine = query.CanonicalQueryEngine(canonical_root=tmp_path)

    # Monkeypatch query_range to return the future funding
    def mock_query(table, **kwargs):
        if table == "funding_settlements":
            return [future_funding]
        return []

    engine.query_range = mock_query

    slice_result = engine.hourly_asof_slice(["2026-04-02T01:01:00Z"], assets=("BTC",))
    assert len(slice_result) == 1
    r = slice_result[0]
    assert r["latest_prior_funding_settlement_utc"] is None
    assert r["latest_prior_funding_rate"] is None
    assert r["future_funding_or_return_labels_read"] == 0


def test_resumable_atomic_write_and_tamper_rejection(spot_fixture_zip, tmp_path):
    source = {
        "source_id": "atomic_test",
        "path": str(spot_fixture_zip),
        "exchange": "binance",
        "asset": "BTC",
        "symbol": "BTCUSDT",
        "product": "SPOT",
        "family": "spot_klines",
        "interval": "1m",
        "period": "2021-01",
        "calendar_timezone": "UTC",
        "raw_sha256": materialize_history.digest(spot_fixture_zip),
    }

    mat = materialize_history.Materializer(catalog_db=tmp_path / "cat.db", output_dir=tmp_path / "c1")
    rcpt1 = mat.materialize_one(source)
    assert rcpt1["row_count"] == 2
    assert not list((tmp_path / "c1").rglob("*.partial"))

    # Rerun with resume
    rcpt2 = mat.materialize_one(source)
    assert rcpt2.get("skipped_resumed") is True

    # Tamper with source raw hash
    source_tampered = dict(source, raw_sha256="0" * 64)
    with pytest.raises(ValueError, match="SOURCE_CHANGED_DURING_MATERIALIZATION"):
        mat.materialize_one(source_tampered, force=True)


def test_readonly_source_immutability(spot_fixture_zip, tmp_path):
    stat_before = spot_fixture_zip.stat()
    sha_before = hashlib.sha256(spot_fixture_zip.read_bytes()).hexdigest()

    source = {
        "source_id": "immutable_test",
        "path": str(spot_fixture_zip),
        "exchange": "binance",
        "asset": "BTC",
        "symbol": "BTCUSDT",
        "product": "SPOT",
        "family": "spot_klines",
        "interval": "1m",
        "period": "2021-01",
        "calendar_timezone": "UTC",
        "raw_sha256": sha_before,
    }

    mat = materialize_history.Materializer(catalog_db=tmp_path / "cat.db", output_dir=tmp_path / "c1")
    mat.materialize_one(source)

    stat_after = spot_fixture_zip.stat()
    sha_after = hashlib.sha256(spot_fixture_zip.read_bytes()).hexdigest()

    assert stat_before.st_mtime_ns == stat_after.st_mtime_ns
    assert stat_before.st_size == stat_after.st_size
    assert sha_before == sha_after
