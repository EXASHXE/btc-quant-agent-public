"""OKX USDT-SWAP (and Spot Basis Control) Data Acquisition Module.

Acquires, verifies, and indexes OKX historical data for BTC-USDT-SWAP and ETH-USDT-SWAP.
Handles native 1m OHLCV, 8h funding rate histories, 1-day tick trade flow samples,
and 1-day high-resolution L2 400lv order book sample.
Explicitly records publisher checksum absence and validates schemas and timestamps.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.data.common import (
    Budget,
    SafeFetcher,
    generate_date_range,
    get_okx_utc_window_for_day,
)
from tools.data.qc import qc_okx_l2_archive, qc_zip_archive

OKX_PORTAL = "https://www.okx.com/historical-data"
OKX_CDN_BASE = "https://static.okx.com/cdn"

SWAP_SYMBOLS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")
SPOT_SYMBOLS = ("BTC-USDT", "ETH-USDT")

INTERVAL_1M_MS = 60 * 1000
INTERVAL_8H_MS = 8 * 3600 * 1000

DAYS_Q3 = generate_date_range("2026-07-01", "2026-09-30", end_inclusive=True)
SAMPLE_DAYS_Q3 = ("2026-07-01",)


def get_okx_tasks(
    start_date: str | None = None,
    end_date: str | None = None,
    sample_days: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Build task list for OKX USDT-SWAP, Funding Rates, Spot control, and L2 Sample.

    If start_date and end_date are provided, uses explicit date range [start_date, end_date) exclusive.
    Otherwise defaults to Q3 2026.
    """
    if start_date is not None and end_date is not None:
        days = generate_date_range(start_date, end_date, end_inclusive=False)
        sample_days_list = list(sample_days) if sample_days is not None else ([days[0]] if days else [])
    else:
        days = list(DAYS_Q3)
        sample_days_list = list(sample_days) if sample_days is not None else list(SAMPLE_DAYS_Q3)

    tasks = []

    # 1. Daily Candlesticks (1m native OHLCV) for SWAPs
    for sym in SWAP_SYMBOLS:
        for d in days:
            ymd = d.replace("-", "")
            url = f"{OKX_CDN_BASE}/okex/traderecords/candlesticks/daily/{ymd}/{sym}-candlesticks-{d}.zip?v=1001"
            start_w, end_w = get_okx_utc_window_for_day(d)
            tasks.append({
                "venue": "okx",
                "market": "swap",
                "family": "candlesticks",
                "symbol": sym,
                "interval": "1m",
                "period": d,
                "calendar_day_utc8": d,
                "utc_event_window": f"{start_w} to {end_w}",
                "url": url,
                "expected_interval_ms": INTERVAL_1M_MS,
                "archive_type": "zip",
            })

    # 2. Daily Candlesticks (1m native OHLCV) for Spot basis control
    for sym in SPOT_SYMBOLS:
        for d in days:
            ymd = d.replace("-", "")
            url = f"{OKX_CDN_BASE}/okex/traderecords/candlesticks/daily/{ymd}/{sym}-candlesticks-{d}.zip?v=1001"
            start_w, end_w = get_okx_utc_window_for_day(d)
            tasks.append({
                "venue": "okx",
                "market": "spot",
                "family": "spot_candlesticks",
                "symbol": sym,
                "interval": "1m",
                "period": d,
                "calendar_day_utc8": d,
                "utc_event_window": f"{start_w} to {end_w}",
                "url": url,
                "expected_interval_ms": INTERVAL_1M_MS,
                "archive_type": "zip",
            })

    # 3. Daily Funding Rates (allswap-fundingrates: covers BTC and ETH swaps)
    for d in days:
        ymd = d.replace("-", "")
        url = f"{OKX_CDN_BASE}/okex/traderecords/swaprates/daily/{ymd}/allswap-fundingrates-{d}.zip?v=1001"
        start_w, end_w = get_okx_utc_window_for_day(d)
        tasks.append({
            "venue": "okx",
            "market": "swap",
            "family": "funding_rates",
            "symbol": "ALL_SWAPS",
            "interval": "8h",
            "period": d,
            "calendar_day_utc8": d,
            "utc_event_window": f"{start_w} to {end_w}",
            "url": url,
            "expected_interval_ms": INTERVAL_8H_MS,
            "archive_type": "zip",
        })

    # 4. Tick Trades sample (1-day sample)
    for sym in SWAP_SYMBOLS:
        for d in sample_days_list:
            ymd = d.replace("-", "")
            url = f"{OKX_CDN_BASE}/okex/traderecords/trades/daily/{ymd}/{sym}-trades-{d}.zip?v=1001"
            start_w, end_w = get_okx_utc_window_for_day(d)
            tasks.append({
                "venue": "okx",
                "market": "swap",
                "family": "trades",
                "symbol": sym,
                "interval": "tick",
                "period": d,
                "calendar_day_utc8": d,
                "utc_event_window": f"{start_w} to {end_w}",
                "url": url,
                "expected_interval_ms": None,
                "archive_type": "zip",
            })

    # 5. T1: High-resolution L2 Order Book (400lv 1-day sample: BTC-USDT-SWAP)
    for d in sample_days_list:
        ymd = d.replace("-", "")
        url = f"{OKX_CDN_BASE}/okx/match/orderbook/pro/L2/400lv/daily/{ymd}/BTC-USDT-SWAP-L2orderbook-400lv-{d}.tar.gz"
        start_w, end_w = get_okx_utc_window_for_day(d)
        tasks.append({
            "venue": "okx",
            "market": "swap",
            "family": "orderbook",
            "symbol": "BTC-USDT-SWAP",
            "interval": "tick_l2_400lv",
            "period": d,
            "calendar_day_utc8": d,
            "utc_event_window": f"{start_w} to {end_w}",
            "url": url,
            "expected_interval_ms": None,
            "archive_type": "tar.gz",
        })

    return tasks


def run_okx_expansion(
    output_root: Path,
    budget: Budget,
    action: str = "acquire",
    start_date: str | None = None,
    end_date: str | None = None,
    tranche_id: str | None = None,
) -> dict[str, Any]:
    """Execute OKX data acquisition and QC."""
    data_dir = output_root / "data"
    reports_dir = output_root

    fetcher = SafeFetcher(budget, rate_limit_delay=0.08)
    tasks = get_okx_tasks(start_date=start_date, end_date=end_date)

    records = []
    coverage_by_series: dict[str, Any] = {}
    total_newly_acquired = 0
    total_reused = 0
    failed_objects = []

    for task in tasks:
        fam = task["family"]
        sym = task["symbol"]
        url = task["url"]
        period = task["period"]
        expected_interval_ms = task["expected_interval_ms"]
        archive_type = task["archive_type"]

        folder = data_dir / fam
        folder.mkdir(parents=True, exist_ok=True)
        filename = url.split("?")[0].rsplit("/", 1)[1]
        data_path = folder / filename

        rec: dict[str, Any] = {
            "venue": "okx",
            "market": task["market"],
            "family": fam,
            "symbol": sym,
            "interval": task["interval"],
            "period": period,
            "calendar_day_utc8": task.get("calendar_day_utc8"),
            "utc_event_window": task.get("utc_event_window"),
            "url": url,
            "local_path": str(data_path.relative_to(output_root)),
        }

        if action == "acquire":
            data_meta = fetcher.fetch_file(url, data_path)
            if data_meta is None:
                rec["verdict"] = "OBJECT_NOT_FOUND"
                failed_objects.append(rec)
                records.append(rec)
                continue

            if data_meta.get("reused", False):
                total_reused += 1
            else:
                total_newly_acquired += 1

            rec["fetch"] = data_meta
            local_sha = data_meta["sha256"]
            etag = data_meta.get("etag")
        else:
            if not data_path.exists():
                rec["verdict"] = "MISSING_LOCAL_FILE"
                failed_objects.append(rec)
                records.append(rec)
                continue
            with data_path.open("rb") as f:
                local_sha = hashlib.file_digest(f, "sha256").hexdigest()
            etag = "LOCAL"

        rec["local_sha256"] = local_sha
        rec["publisher_checksum"] = None
        rec["publisher_checksum_verified"] = False
        rec["publisher_checksum_absent"] = True
        rec["etag"] = etag

        # Offline QC based on file type
        if archive_type == "zip":
            qc_res = qc_zip_archive(data_path, fam, "okx", budget, expected_interval_ms)
        elif archive_type == "tar.gz":
            qc_res = qc_okx_l2_archive(data_path, budget)
        else:
            qc_res = {"verdict": "FAIL", "error": "UNKNOWN_ARCHIVE_TYPE"}

        rec.update(qc_res)
        records.append(rec)

        # Update coverage tracking
        series_key = f"{fam}_{sym}_{task['interval']}"
        if series_key not in coverage_by_series:
            coverage_by_series[series_key] = {
                "venue": "okx",
                "market": task["market"],
                "family": fam,
                "symbol": sym,
                "interval": task["interval"],
                "total_files": 0,
                "passed_files": 0,
                "total_rows": 0,
                "start_utc": None,
                "end_utc": None,
                "total_gaps": 0,
                "total_duplicates": 0,
            }

        s_cov = coverage_by_series[series_key]
        s_cov["total_files"] += 1
        if qc_res.get("verdict") in ("PASS", "PARTIAL_PASS"):
            s_cov["passed_files"] += 1
            s_cov["total_rows"] += qc_res.get("rows", qc_res.get("records_sampled", 0))
            s_cov["total_gaps"] += qc_res.get("gaps", 0)
            s_cov["total_duplicates"] += qc_res.get("duplicates", 0)
            if s_cov["start_utc"] is None or (qc_res.get("start_utc") and qc_res["start_utc"] < s_cov["start_utc"]):
                s_cov["start_utc"] = qc_res.get("start_utc")
            if s_cov["end_utc"] is None or (qc_res.get("end_utc") and qc_res["end_utc"] > s_cov["end_utc"]):
                s_cov["end_utc"] = qc_res.get("end_utc")

    # Generate Manifest
    disk_usage = budget.check_disk()
    terminal = "DATA_TRANCHE_VERIFIED" if len(failed_objects) == 0 else "DATA_PARTIAL_WITH_NEXT_BATCH"

    task_name = f"V065-DATA-R3_OKX_SWAP_{tranche_id.upper()}" if tranche_id else "V065-DATA-R2_OKX_SWAP_EXPANSION"
    tranche_aim = (
        f"{start_date} through {end_date} exclusive"
        if start_date and end_date
        else "2026-07-01 through 2026-10-01 exclusive (base series Q3 2026)"
    )
    next_batch = (
        "2026-01-01 through 2026-04-01 (progressing backward)"
        if (tranche_id == "2026q2" or (start_date and "2026-04-01" in start_date))
        else "2026-04-01 through 2026-07-01 (progressing backward)"
    )

    manifest = {
        "manifest_version": "1.0",
        "publisher": "OKX Historical Market Data",
        "publisher_url": OKX_PORTAL,
        "venue": "okx",
        "task": task_name,
        "tranche_id": tranche_id,
        "start_date": start_date,
        "end_date": end_date,
        "terminal": terminal,
        "tranche_aim": tranche_aim,
        "next_resumable_batch": next_batch,
        "calendar_day_semantics": "OKX daily files represent UTC+8 calendar days (00:00:00 to 23:59:59 CST), spanning [T-1 16:00:00 UTC, T 15:59:59 UTC]",
        "disk_measurement": disk_usage,
        "budget_usage": {
            "compressed_bytes_consumed": budget.compressed_bytes,
            "expanded_bytes_consumed": budget.expanded_bytes,
            "requests_made": budget.requests_made,
            "compressed_cap": budget.compressed_cap,
            "expanded_cap": budget.expanded_cap,
            "request_cap": budget.request_cap,
        },
        "inventory": {
            "total_tasks": len(tasks),
            "total_evaluated": len(records),
            "newly_acquired": total_newly_acquired,
            "reused_local": total_reused,
            "failed_objects_count": len(failed_objects),
            "passed_objects_count": sum(1 for r in records if r.get("verdict") in ("PASS", "PARTIAL_PASS")),
        },
        "coverage_summary": coverage_by_series,
        "failed_objects": failed_objects,
        "records": records,
    }

    # Save manifest.json, coverage.json, qc.json
    manifest_path = reports_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")

    coverage_doc = {
        "manifest_version": "1.0",
        "venue": "okx",
        "terminal": terminal,
        "coverage": coverage_by_series,
    }
    with (reports_dir / "coverage.json").open("w", encoding="utf-8") as f:
        json.dump(coverage_doc, f, indent=2, sort_keys=True)
        f.write("\n")

    qc_doc = {
        "manifest_version": "1.0",
        "venue": "okx",
        "terminal": terminal,
        "qc_summary": {
            "total_records": len(records),
            "pass_count": sum(1 for r in records if r.get("verdict") == "PASS"),
            "partial_pass_count": sum(1 for r in records if r.get("verdict") == "PARTIAL_PASS"),
            "fail_count": len(failed_objects),
        },
        "qc_records": [
            {
                "local_path": r.get("local_path"),
                "family": r.get("family"),
                "symbol": r.get("symbol"),
                "period": r.get("period"),
                "verdict": r.get("verdict"),
                "rows": r.get("rows", r.get("records_sampled")),
                "start_utc": r.get("start_utc"),
                "end_utc": r.get("end_utc"),
                "publisher_checksum_absent": r.get("publisher_checksum_absent"),
                "publisher_checksum_verified": r.get("publisher_checksum_verified"),
                "gaps": r.get("gaps"),
                "duplicates": r.get("duplicates"),
                "compressed_bytes": r.get("compressed_bytes"),
                "expanded_bytes": r.get("expanded_bytes"),
            }
            for r in records
        ],
    }
    with (reports_dir / "qc.json").open("w", encoding="utf-8") as f:
        json.dump(qc_doc, f, indent=2, sort_keys=True)
        f.write("\n")

    return manifest
