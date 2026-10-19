"""DATA-C2 & DATA-C2-B1: Unit tests for aggTrades flow materialization, query, and resource gating."""

from __future__ import annotations

import csv
import io
import json
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.data.catalog.flow_materializer import (
    FlowMaterializer,
    ResourceGatedError,
    ResourcePreflight,
)
from scripts.data.catalog.flow_query import FlowQueryEngine
from scripts.data.catalog.normalize import SCHEMAS, _us


def test_trade_flow_schema():
    assert "trade_flow_1m" in SCHEMAS
    schema = SCHEMAS["trade_flow_1m"]
    field_names = schema.names
    expected = [
        "exchange", "native_symbol", "canonical_underlying", "quote_asset",
        "product_type", "contract_identity", "price_unit", "base_qty_unit",
        "event_ts_utc", "interval_start_utc", "interval_end_utc", "interval",
        "source_native_ts", "source_time_unit", "source_id", "raw_sha256",
        "schema_version", "qc_flags", "event_count", "volume_base",
        "volume_quote", "signed_flow_base", "signed_flow_quote",
        "buy_volume_base", "buy_volume_quote", "sell_volume_base",
        "sell_volume_quote", "buy_event_count", "sell_event_count",
        "vwap", "trade_open", "trade_high", "trade_low", "trade_close",
        "first_trade_id", "last_trade_id"
    ]
    for exp in expected:
        assert exp in field_names, f"Missing field: {exp}"


def test_timestamp_us_conversion():
    # 13 digits (millisecond)
    ms_ts = "1692057600123"
    us_val, unit = _us(ms_ts)
    assert unit == "ms"
    assert us_val == 1692057600123000

    # 16 digits (microsecond)
    us_ts = "1735689600123456"
    us_val2, unit2 = _us(us_ts)
    assert unit2 == "us"
    assert us_val2 == 1735689600123456


def test_flow_aggregation_synthetic_month(tmp_path: Path):
    """Test streaming aggregation on synthetic aggTrades ZIP (both perp 7-col and spot 8-col)."""
    # 1. Create synthetic perp zip (7 cols, no header)
    perp_zip = tmp_path / "BTCUSDT-aggTrades-perp.zip"
    t0_ms = 1692057600000  # 2023-08-15 00:00:00
    trades_perp = [
        # trade_id, price, qty, first_id, last_id, time, is_buyer_maker
        [101, 29000.0, 1.5, 101, 101, t0_ms + 1000, "false"],  # Taker BUY 1.5 @ 29000
        [102, 29010.0, 0.5, 102, 102, t0_ms + 5000, "true"],   # Taker SELL 0.5 @ 29010
        [103, 29005.0, 1.0, 103, 103, t0_ms + 25000, "false"], # Taker BUY 1.0 @ 29005
        # Minute 2:
        [104, 29020.0, 2.0, 104, 104, t0_ms + 62000, "true"],  # Taker SELL 2.0 @ 29020
    ]

    with zipfile.ZipFile(perp_zip, "w") as z:
        out = io.StringIO()
        writer = csv.writer(out)
        for r in trades_perp:
            writer.writerow(r)
        z.writestr("BTCUSDT-aggTrades-2023-08.csv", out.getvalue())

    import hashlib
    file_bytes = perp_zip.read_bytes()
    file_sha = hashlib.sha256(file_bytes).hexdigest()

    manifest_data = {
        "requests": [
            {
                "family": "perp_aggTrades",
                "path": str(perp_zip),
                "month": "2023-08",
                "bytes": len(file_bytes),
                "expected_sha256": file_sha,
                "audit": {"row_count": len(trades_perp)},
            }
        ]
    }
    manifest_file = tmp_path / "test_manifest.json"
    manifest_file.write_text(json.dumps(manifest_data))

    out_dir = tmp_path / "lakehouse_c2"
    mat = FlowMaterializer(
        manifest_path=manifest_file,
        output_dir=out_dir,
        min_mem_available_mb=0.0,
        min_swap_free_mb=0.0,
        zero_swap_floor_mb=0.0,
    )
    sources = mat.get_all_sources()
    assert len(sources) == 1

    rcpt = mat.materialize_month(sources[0])
    assert rcpt["status"] == "SUCCESS"
    assert rcpt["minute_rows"] == 2
    assert rcpt["raw_events_count"] == 4

    p_path = Path(rcpt["partition_path"])
    assert p_path.is_file()
    table = pq.ParquetFile(p_path).read()
    assert table.num_rows == 2

    rows = table.to_pylist()
    m1 = rows[0]
    assert m1["event_count"] == 3
    assert m1["volume_base"] == pytest.approx(3.0)
    assert m1["buy_volume_base"] == pytest.approx(2.5)
    assert m1["sell_volume_base"] == pytest.approx(0.5)
    assert m1["signed_flow_base"] == pytest.approx(2.0)
    assert m1["buy_event_count"] == 2
    assert m1["sell_event_count"] == 1
    assert m1["trade_open"] == 29000.0
    assert m1["trade_high"] == 29010.0
    assert m1["trade_low"] == 29000.0
    assert m1["trade_close"] == 29005.0
    assert m1["first_trade_id"] == 101
    assert m1["last_trade_id"] == 103
    assert m1["vwap"] == pytest.approx(87010.0 / 3.0, rel=1e-5)


def test_flow_query_and_causal_asof(tmp_path: Path):
    """Test causal filter and 5m/1h rollups in FlowQueryEngine."""
    flow_dir = tmp_path / "c2" / "minute_flow" / "exchange=binance" / "asset=BTC" / "product=USD_M_PERPETUAL" / "period=2023-08"
    flow_dir.mkdir(parents=True, exist_ok=True)

    records = []
    t_start = datetime(2023, 8, 15, 0, 50, tzinfo=UTC)
    for i in range(12):
        s_dt = t_start + timedelta(minutes=i)
        e_dt = s_dt + timedelta(minutes=1)
        s_us = int(s_dt.timestamp() * 10**6)
        e_us = int(e_dt.timestamp() * 10**6)
        records.append({
            "exchange": "binance",
            "native_symbol": "BTCUSDT",
            "canonical_underlying": "BTC",
            "quote_asset": "USDT",
            "product_type": "USD_M_PERPETUAL",
            "contract_identity": "BTCUSDT",
            "price_unit": "USDT/BTC",
            "base_qty_unit": "BTC",
            "event_ts_utc": e_us,
            "interval_start_utc": s_us,
            "interval_end_utc": e_us,
            "interval": "1m",
            "source_native_ts": str(s_us),
            "source_time_unit": "us",
            "exchange_published_at": None,
            "local_ingested_at": None,
            "receiver_first_known_at": None,
            "source_id": "test_src",
            "raw_sha256": "fake_sha",
            "schema_version": "v1",
            "qc_flags": "TEST",
            "event_count": 100,
            "volume_base": 10.0,
            "volume_quote": 290000.0,
            "signed_flow_base": 2.0,
            "signed_flow_quote": 58000.0,
            "buy_volume_base": 6.0,
            "buy_volume_quote": 174000.0,
            "sell_volume_base": 4.0,
            "sell_volume_quote": 116000.0,
            "buy_event_count": 60,
            "sell_event_count": 40,
            "vwap": 29000.0,
            "trade_open": 28990.0,
            "trade_high": 29010.0,
            "trade_low": 28980.0,
            "trade_close": 29000.0,
            "first_trade_id": i * 100 + 1,
            "last_trade_id": (i + 1) * 100,
        })

    table = pa.Table.from_pylist(records, schema=SCHEMAS["trade_flow_1m"])
    pq.write_table(table, flow_dir / "flow_mock.parquet")

    engine = FlowQueryEngine(c2_root=tmp_path / "c2")

    res = engine.query_flow_range("binance", "BTC", "USD_M_PERPETUAL", "2023-08-15T00:50:00Z", "2023-08-15T01:00:00Z")
    assert len(res) == 10

    asof = engine.hourly_asof_flow_slice(["2023-08-15T01:01:00Z"], asset="BTC")
    assert len(asof) == 1
    slice_data = asof[0]
    assert slice_data["governance"]["future_funding_or_return_labels_read"] == 0
    assert slice_data["governance"]["real_historical_outcomes_evaluated"] == 0
    assert slice_data["governance"]["cutoff_respected"] is True

    assert slice_data["perp_1m_flow"]["volume_base"] == 10.0
    assert slice_data["perp_1m_flow"]["signed_flow_base"] == 2.0

    assert slice_data["perp_5m_flow"]["count_minutes"] == 5
    assert slice_data["perp_5m_flow"]["volume_base"] == 50.0
    assert slice_data["perp_5m_flow"]["signed_flow_base"] == 10.0


def test_spot_microsecond_and_header_parsing(tmp_path: Path):
    """Test spot aggTrades format (8 columns, header, microsecond timestamps)."""
    spot_zip = tmp_path / "BTCUSDT-aggTrades-spot.zip"
    t0_us = 1735689600000000
    trades_spot = [
        ["agg_trade_id", "price", "qty", "first_id", "last_id", "transact_time", "is_buyer_maker", "was_best_price_match"],
        ["2001", "95000.00", "0.20000", "5001", "5001", str(t0_us + 1500000), "False", "True"],
        ["2002", "95050.00", "0.10000", "5002", "5002", str(t0_us + 3500000), "True", "True"],
    ]

    with zipfile.ZipFile(spot_zip, "w") as z:
        out = io.StringIO()
        writer = csv.writer(out)
        for r in trades_spot:
            writer.writerow(r)
        z.writestr("BTCUSDT-aggTrades-2025-01.csv", out.getvalue())

    import hashlib
    file_bytes = spot_zip.read_bytes()
    file_sha = hashlib.sha256(file_bytes).hexdigest()

    manifest_data = {
        "requests": [
            {
                "family": "spot_aggTrades",
                "path": str(spot_zip),
                "month": "2025-01",
                "bytes": len(file_bytes),
                "expected_sha256": file_sha,
                "audit": {"row_count": 2},
            }
        ]
    }
    manifest_file = tmp_path / "test_manifest.json"
    manifest_file.write_text(json.dumps(manifest_data))

    out_dir = tmp_path / "lakehouse_c2"
    mat = FlowMaterializer(
        manifest_path=manifest_file,
        output_dir=out_dir,
        min_mem_available_mb=0.0,
        min_swap_free_mb=0.0,
        zero_swap_floor_mb=0.0,
    )
    sources = mat.get_all_sources()
    assert len(sources) == 1

    rcpt = mat.materialize_month(sources[0])
    assert rcpt["status"] == "SUCCESS"
    assert rcpt["minute_rows"] == 1
    assert rcpt["raw_events_count"] == 2

    table = pq.ParquetFile(rcpt["partition_path"]).read()
    row = table.to_pylist()[0]
    assert row["product_type"] == "SPOT"
    assert row["event_count"] == 2
    assert row["buy_volume_base"] == pytest.approx(0.2)
    assert row["sell_volume_base"] == pytest.approx(0.1)
    assert row["signed_flow_base"] == pytest.approx(0.1)

    rcpt_resume = mat.materialize_month(sources[0])
    assert rcpt_resume.get("skipped_resumed") is True


# ==============================================================================
# DATA-C2-B1 SPECIFIC TESTS
# ==============================================================================

def test_resource_preflight_thresholds_and_zero_swap(tmp_path: Path):
    """Test simulated MemAvailable and SwapFree thresholds and zero-swap risk detection."""
    mock_meminfo = tmp_path / "meminfo_mock"

    # Case 1: Low memory and low swap
    mock_meminfo.write_text(
        "MemTotal:        2000000 kB\n"
        "MemFree:           50000 kB\n"
        "MemAvailable:     150000 kB\n"  # ~146 MB < 384 MB
        "SwapTotal:       5000000 kB\n"
        "SwapFree:         200000 kB\n"  # ~195 MB < 512 MB
    )
    preflight = ResourcePreflight(
        min_mem_available_mb=384.0,
        min_swap_free_mb=512.0,
        zero_swap_floor_mb=32.0,
        meminfo_path=mock_meminfo,
    )
    eval_res = preflight.evaluate()
    assert eval_res["is_safe"] is False
    assert eval_res["verdict"] == "RESOURCE_PRESSURE_BLOCKED"
    assert any("INSUFFICIENT_HEADROOM" in r for r in eval_res["reasons"])

    # Case 2: Zero swap floor violation (< 32 MB)
    mock_meminfo.write_text(
        "MemTotal:        4000000 kB\n"
        "MemFree:         1000000 kB\n"
        "MemAvailable:    1000000 kB\n"  # 976 MB (OK)
        "SwapTotal:       5000000 kB\n"
        "SwapFree:          10000 kB\n"  # 9.7 MB < 32 MB (Zero swap floor violation!)
    )
    eval_res2 = preflight.evaluate()
    assert eval_res2["is_safe"] is False
    assert eval_res2["verdict"] == "RESOURCE_PRESSURE_BLOCKED"
    assert any("ZERO_SWAP_RISK" in r for r in eval_res2["reasons"])

    # Case 3: Adequate headroom
    mock_meminfo.write_text(
        "MemTotal:        8000000 kB\n"
        "MemFree:         3000000 kB\n"
        "MemAvailable:    3500000 kB\n"  # ~3417 MB
        "SwapTotal:       8000000 kB\n"
        "SwapFree:        6000000 kB\n"  # ~5859 MB
    )
    eval_res3 = preflight.evaluate()
    assert eval_res3["is_safe"] is True
    assert eval_res3["verdict"] == "RESOURCE_SAFE"
    assert len(eval_res3["reasons"]) == 0


def test_resource_gate_refuses_to_open_new_source(tmp_path: Path):
    """Verify that when resource gate fails closed, materialize_month raises ResourceGatedError without touching data."""
    mock_meminfo = tmp_path / "meminfo"
    mock_meminfo.write_text(
        "MemTotal: 2000000 kB\nMemAvailable: 50000 kB\nSwapTotal: 5000000 kB\nSwapFree: 0 kB\n"
    )

    dummy_zip = tmp_path / "dummy.zip"
    with zipfile.ZipFile(dummy_zip, "w") as z:
        z.writestr("test.csv", "1,29000,1,1,1,1692057600000,false\n")

    import hashlib
    file_bytes = dummy_zip.read_bytes()
    file_sha = hashlib.sha256(file_bytes).hexdigest()

    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps({
        "requests": [{
            "family": "perp_aggTrades",
            "path": str(dummy_zip),
            "month": "2025-09",
            "bytes": len(file_bytes),
            "expected_sha256": file_sha,
            "audit": {"row_count": 1},
        }]
    }))

    out_dir = tmp_path / "lakehouse_c2"
    mat = FlowMaterializer(
        manifest_path=manifest_file,
        output_dir=out_dir,
        min_mem_available_mb=384.0,
        min_swap_free_mb=512.0,
        meminfo_path=mock_meminfo,
    )
    sources = mat.get_all_sources()

    with pytest.raises(ResourceGatedError) as exc_info:
        mat.materialize_month(sources[0])

    assert "RESOURCE_GATED" in str(exc_info.value)
    # Ensure no partition or partial file was created
    target_p = mat.get_target_partition_path(sources[0])
    assert not target_p.exists()
    assert not target_p.with_suffix(".parquet.partial").exists()


def test_tamper_detection_on_resume(tmp_path: Path):
    """Test that if an output Parquet partition is tampered with, resume rejects it with hash mismatch."""
    perp_zip = tmp_path / "BTCUSDT-perp.zip"
    with zipfile.ZipFile(perp_zip, "w") as z:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow([101, 29000.0, 1.0, 101, 101, 1692057600000, "false"])
        z.writestr("test.csv", out.getvalue())

    import hashlib
    file_bytes = perp_zip.read_bytes()
    file_sha = hashlib.sha256(file_bytes).hexdigest()

    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps({
        "requests": [{
            "family": "perp_aggTrades",
            "path": str(perp_zip),
            "month": "2023-08",
            "bytes": len(file_bytes),
            "expected_sha256": file_sha,
            "audit": {"row_count": 1},
        }]
    }))

    out_dir = tmp_path / "lakehouse_c2"
    mat = FlowMaterializer(
        manifest_path=manifest_file,
        output_dir=out_dir,
        min_mem_available_mb=0.0,
        min_swap_free_mb=0.0,
        zero_swap_floor_mb=0.0,
    )
    source = mat.get_all_sources()[0]

    # First run succeeds
    rcpt = mat.materialize_month(source)
    assert rcpt["status"] == "SUCCESS"

    # Tamper with output Parquet file
    part_p = Path(rcpt["partition_path"])
    part_p.write_bytes(part_p.read_bytes() + b"\x00\x00corrupt")

    # Second run should detect tamper and raise ValueError
    with pytest.raises(ValueError) as exc:
        mat.materialize_month(source)
    assert "PARTITION_HASH_MISMATCH" in str(exc.value)


def test_bounded_batch_candidate_selection_and_ranking(tmp_path: Path):
    """Test candidate batch ranking prioritizing smallest compressed month."""
    manifest_data = {
        "requests": [
            # 2021-02: 700MB + 800MB = 1500MB
            {"family": "perp_aggTrades", "path": "/fake/2021_p.zip", "month": "2021-02", "bytes": 700000000},
            {"family": "spot_aggTrades", "path": "/fake/2021_s.zip", "month": "2021-02", "bytes": 800000000},
            # 2025-09: 300MB + 280MB = 580MB (SMALLEST!)
            {"family": "perp_aggTrades", "path": "/fake/2025_p.zip", "month": "2025-09", "bytes": 300000000},
            {"family": "spot_aggTrades", "path": "/fake/2025_s.zip", "month": "2025-09", "bytes": 280000000},
            # 2022-11: 400MB + 2000MB = 2400MB
            {"family": "perp_aggTrades", "path": "/fake/2022_p.zip", "month": "2022-11", "bytes": 400000000},
            {"family": "spot_aggTrades", "path": "/fake/2022_s.zip", "month": "2022-11", "bytes": 2000000000},
        ]
    }
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data))

    out_dir = tmp_path / "c2"
    mat = FlowMaterializer(
        manifest_path=manifest_file,
        output_dir=out_dir,
        min_mem_available_mb=0.0,
        min_swap_free_mb=0.0,
        zero_swap_floor_mb=0.0,
    )
    decision = mat.evaluate_candidate_batch(candidate_months=("2021-02", "2025-09", "2022-11"))

    # Smallest month ranking
    rankings = decision["month_compressed_ranking"]
    assert rankings[0]["month"] == "2025-09"
    assert rankings[0]["total_bytes"] == 580000000
    assert rankings[1]["month"] == "2021-02"
    assert rankings[2]["month"] == "2022-11"

    # Chosen batch
    assert decision["chosen_next_batch"]["month"] == "2025-09"
    assert len(decision["chosen_next_batch"]["sources"]) == 2


def test_truthful_timing_separation(tmp_path: Path):
    """Test that cumulative conversion wall time is summed from checkpoints and separate from run wall time."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps({"requests": []}))

    out_dir = tmp_path / "c2"
    ckpts_dir = out_dir / "checkpoints"
    ckpts_dir.mkdir(parents=True, exist_ok=True)

    sources = [
        {"month": "2023-08", "family": "perp_aggTrades", "product": "USD_M_PERPETUAL", "exchange": "binance", "asset": "BTC", "bytes": 100, "expected_sha256": None, "source_id": "1"},
        {"month": "2023-08", "family": "spot_aggTrades", "product": "SPOT", "exchange": "binance", "asset": "BTC", "bytes": 100, "expected_sha256": None, "source_id": "2"},
    ]

    mat = FlowMaterializer(manifest_path=manifest_file, output_dir=out_dir)

    p_target = mat.get_target_partition_path(sources[0])
    s_target = mat.get_target_partition_path(sources[1])
    p_target.parent.mkdir(parents=True, exist_ok=True)
    s_target.parent.mkdir(parents=True, exist_ok=True)
    p_target.write_text("p")
    s_target.write_text("s")

    # Write two synthetic checkpoints with explicit conversion wall times: 60.86s and 41.14s
    (ckpts_dir / "2023-08_perp_aggTrades.json").write_text(json.dumps({
        "status": "SUCCESS", "month": "2023-08", "family": "perp_aggTrades",
        "minute_rows": 44640, "raw_events_count": 24000000, "bytes": 5000000,
        "wall_time_s": 60.86, "rss_mb": 79.22,
        "partition_path": str(p_target), "partition_sha256": "fake1"
    }))
    (ckpts_dir / "2023-08_spot_aggTrades.json").write_text(json.dumps({
        "status": "SUCCESS", "month": "2023-08", "family": "spot_aggTrades",
        "minute_rows": 44640, "raw_events_count": 15000000, "bytes": 5500000,
        "wall_time_s": 41.14, "rss_mb": 66.93,
        "partition_path": str(s_target), "partition_sha256": "fake2"
    }))
    mat._write_c2_reports(
        all_sources=sources,
        run_wall_time_s=0.02,  # Short run check
        newly_ingested_count=0,
        peak_rss=150.0,
        run_status="DATA_C2_B1_RESOURCE_GATED_READY",
    )

    receipt = json.loads((out_dir / "actual_data_run_receipt.json").read_text())
    assert receipt["run_wall_time_s"] == 0.02
    assert receipt["cumulative_conversion_wall_time_s"] == pytest.approx(102.0)
    assert receipt["newly_ingested_sources_this_run"] == 0
    assert receipt["completed_sources_count"] == 2
