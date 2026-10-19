"""Focused C0 source-clock, catalog, and bounded-write tests."""

import csv
import hashlib
import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from scripts.data.catalog import alignment, inventory, normalize, pipeline


def source(path, **changes):
    base = {"source_id": "fixture-source", "path": str(path), "exchange": "binance",
        "symbol": "BTCUSDT", "asset": "BTC", "product": "USD_M_PERPETUAL",
        "family": "klines", "interval": "1m", "period": "2026-04",
        "qa_level": "PASS_MANIFEST_QC_PINNED_RAW_NOT_REHASHED",
        "raw_sha256": None, "priority": 100}
    return base | changes


def test_native_utc_and_utc8_archive_label_are_distinct():
    b = source("/tmp/fake.zip", family="spot_klines", product="SPOT")
    raw = dict(zip(normalize.BINANCE_FIELDS, ["1775001600000000", "10", "12", "9", "11", "2",
        "1775001659999999", "22", "1", "1", "11", "0"]))
    item = normalize.normalize(b, raw)
    assert item["source_time_unit"] == "us"
    assert item["interval_start_utc"] == 1775001600000000
    assert item["event_ts_utc"] == item["interval_end_utc"] == 1775001660000000
    assert item["product_type"] == "SPOT"
    assert item["receiver_first_known_at"] is None
    o = source("/tmp/fake.zip", exchange="okx", symbol="BTC-USDT-SWAP",
               product="OKX_SWAP", family="candlesticks", period="2026-04-01")
    row = {"instrument_name": "BTC-USDT-SWAP", "open_time": "1774972800000",
        "open": "10", "high": "12", "low": "9", "close": "11", "vol": "100",
        "vol_quote": "1000", "confirm": "1"}
    okx = normalize.normalize(o, row)
    assert datetime.fromtimestamp(okx["interval_start_utc"] / 10**6, UTC).isoformat() == "2026-03-31T16:00:00+00:00"
    assert okx["base_volume"] is None and okx["native_volume_unit"] == "OKX_CONTRACTS"
    assert okx["product_type"] == "OKX_SWAP"
    with pytest.raises(ValueError, match="OKX_MARKET_OR_CONFIRM_INVALID"):
        normalize.normalize(o, row | {"instrument_name": "BTC-USDT"})


def test_position_and_funding_events_keep_distinct_clocks():
    metric = source("/tmp/fake.zip", family="metrics", interval="5m")
    m = normalize.normalize(metric, {"create_time": "2026-04-02 00:55:00",
        "symbol": "BTCUSDT", "sum_open_interest": "1000", "sum_toptrader_long_short_ratio": "1.2"})
    assert m["event_ts_utc"] == m["interval_start_utc"]
    assert m["top_position_long_short_ratio"] == 1.2
    funding = source("/tmp/fake.zip", family="fundingRate", interval="8h")
    f = normalize.normalize(funding, {"calc_time": "1775088000000",
        "funding_interval_hours": "8", "last_funding_rate": "-0.0001"})
    assert f["event_ts_utc"] - f["interval_start_utc"] == 8 * 3600 * 10**6
    assert f["funding_rate"] == -0.0001
    with pytest.raises(ValueError, match="FUNDING_INTERVAL_INVALID"):
        normalize.normalize(funding, {"calc_time": "1775088000000",
            "funding_interval_hours": "0", "last_funding_rate": "0"})


def test_bounded_zip_sample_hash_and_raw_immutability(tmp_path):
    raw = tmp_path / "small.zip"
    with zipfile.ZipFile(raw, "w") as archive:
        content = ",".join(normalize.BINANCE_FIELDS) + "\n"
        for i in range(4):
            t = 1775001600000 + i * 60000
            content += f"{t},10,12,9,11,2,{t + 59999},22,1,1,11,0\n"
        archive.writestr("small.csv", content)
    before = hashlib.sha256(raw.read_bytes()).hexdigest()
    receipt = normalize.write_sample(source(raw, raw_sha256=before), tmp_path / "out", maximum=2)
    assert receipt["sample_rows"] == 2
    assert pq.ParquetFile(receipt["partition_path"]).metadata.num_rows == 2
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == before
    assert not list((tmp_path / "out").rglob("*.partial"))
    with pytest.raises(ValueError, match="SOURCE_HASH_MISMATCH"):
        normalize.write_sample(source(raw, raw_sha256="0" * 64), tmp_path / "other", maximum=2)


def test_sqlite_catalog_rerun_is_idempotent(tmp_path):
    path = tmp_path / "raw.parquet"
    path.write_bytes(b"metadata fixture")
    r = inventory.record(path, exchange="binance", symbol="BTCUSDT", asset="BTC",
        product="USD_M_PERPETUAL", family="candles", interval="1m", period="2021-01",
        start_utc="2021-01-01T00:00:00+00:00", end_utc_exclusive="2021-02-01T00:00:00+00:00",
        rows=44640, gaps=0, qa_level="TEST", priority=90)
    db = tmp_path / "catalog.sqlite"
    for _ in range(2):
        pipeline._create_sqlite(db, [r], inventory.coverage([r]),
            [{"name": "H39", "dates_utc": "2026-09", "policy": "NO_OUTCOME"}])
        connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        assert connection.execute("SELECT COUNT(*) FROM source_files").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM dataset_coverage").fetchone()[0] == 1
        assert connection.execute("SELECT outcome_authorized FROM exclusion_scope_metadata").fetchone()[0] == 0
        connection.close()


def test_old_new_precedence_and_gap_are_explicit(tmp_path):
    old = inventory.record(tmp_path / "old", exchange="binance", symbol="BTCUSDT", asset="BTC",
        product="USD_M_PERPETUAL", family="candles", interval="1m", period="2026-04",
        rows=100, gaps=3, qa_level="MANIFEST", priority=90)
    new = inventory.record(tmp_path / "new", exchange="binance", symbol="BTCUSDT", asset="BTC",
        product="USD_M_PERPETUAL", family="candles", interval="1m", period="2026-04",
        rows=100, gaps=0, qa_level="PASS", priority=100)
    cov = inventory.coverage([old, new])[0]
    assert cov["source_files"] == 2 and cov["preferred_source_ids"] == [new["source_id"]]
    assert cov["physical_rows_sum"] == 200  # Physical overlap, not 200 unique minutes.
    assert any(x["kind"] == "REPORTED_GAPS" for x in inventory.issues([old, new]))


def test_q3_intersection_uses_event_utc_not_okx_day_label(tmp_path):
    common = {"asset": "BTC", "qa_level": "PASS_MANIFEST_QC_PINNED_RAW_NOT_REHASHED", "gaps": 0}
    b = common | {"path": str(tmp_path / "binance-usdm-expansion/data/BTC.zip"),
        "family": "klines", "start_utc": "2026-07-01T00:00:00+00:00",
        "end_utc_exclusive": "2026-10-01T00:00:00+00:00"}
    o = common | {"path": str(tmp_path / "okx-swap-expansion/data/BTC.zip"),
        "family": "candlesticks", "start_utc": "2026-06-30T16:00:00+00:00",
        "end_utc_exclusive": "2026-09-30T16:00:00+00:00"}
    result = pipeline._q3_intersections([b, o])[0]
    assert result["intersection_minutes_envelope"] == 132000
    assert result["intersection_start_utc"] == "2026-07-01T00:00:00+00:00"


def test_forward_is_stat_only_and_output_confinement(tmp_path, monkeypatch):
    forward = tmp_path / "forward"
    day = forward / "microstructure"
    day.mkdir(parents=True)
    (day / "microstructure-2026-10-18.sqlite3").write_bytes(b"never connect")
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: pytest.fail("Forward DB opened"))
    found = inventory.forward_metadata(forward)
    assert len(found) == 1 and found[0]["qa_level"] == "STAT_ONLY_NO_DB_ATTACH_OR_ROW_READ"
    assert found[0]["study_scope"] == "FORWARD_PROTECTED_METADATA_ONLY"
    with pytest.raises(ValueError, match="OUTPUT_INPUT_ALIAS"):
        pipeline.safe_output(day / "lake", (forward,))
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="OUTPUT_SYMLINK_FORBIDDEN"):
        pipeline.safe_output(alias / "lake", ())


def test_h39_and_old_sample_metadata_never_open_payload(tmp_path, monkeypatch):
    for relative in ("h39_validation/h39_blind_ledger.sqlite3",
                     "v0.3.18_official_samples/perp_aggTrades/BTCUSDT-2024-01.zip"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"protected fixture")
    original_open = Path.open
    def guarded(path, *args, **kwargs):
        if path.is_relative_to(tmp_path):
            pytest.fail("Protected research payload opened")
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    rows = inventory.protected_research_metadata(tmp_path)
    assert len(rows) == 2
    assert all(r["qa_level"] == "STAT_ONLY_PROTECTED_NO_ROW_READ" for r in rows)


def test_asof_never_uses_future_funding_and_retains_no_action(monkeypatch):
    cutoff = int(datetime(2026, 4, 2, 1, tzinfo=UTC).timestamp() * 10**6)
    minute = 60 * 10**6
    last = cutoff - 2 * minute
    end = datetime.fromtimestamp((last + minute) / 10**6, UTC)
    fake_bar = {"interval_end_utc": end, "close": 100.0}
    price = {last: fake_bar}
    future_funding = {cutoff + minute: {"funding_rate": 0.9}}
    def load(_, *, asset, exchange, product, table):
        if table == "funding_settlements":
            return future_funding
        if table == "position_state":
            return {}  # Exact predecessor unavailable.
        return price
    monkeypatch.setattr(alignment, "_load", load)
    rows, summary = alignment.asof_example([], hours=1)
    assert len(rows) == 2 and summary["no_action_rows"] == 2
    assert all(r["latest_prior_funding_settlement_utc"] is None for r in rows)
    assert all(r["z_exact_4h_predecessor"] is False for r in rows)
    assert all(r["future_funding_or_return_labels_read"] == 0 for r in rows)
