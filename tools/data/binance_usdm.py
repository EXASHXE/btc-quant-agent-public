"""Binance USD-M (and Spot Basis Control) Data Acquisition Module.

Acquires, verifies, and indexes Binance Vision historical data for BTCUSDT and ETHUSDT.
Enforces publisher CHECKSUM validation, strict schema checking, and rate-limited downloads.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from tools.data.common import (
    Budget,
    SafeFetcher,
    generate_date_range,
    generate_month_range,
    verify_publisher_checksum,
)
from tools.data.qc import qc_zip_archive

ORIGIN = "https://data.binance.vision"

SYMBOLS = ("BTCUSDT", "ETHUSDT")
MONTHS_Q3 = ("2026-07", "2026-08", "2026-09")
DAYS_Q3 = generate_date_range("2026-07-01", "2026-09-30", end_inclusive=True)
SAMPLE_TRADE_DAYS_Q3 = ("2026-07-01",)

# Expected interval milliseconds
INTERVAL_1M_MS = 60 * 1000
INTERVAL_5M_MS = 5 * 60 * 1000
INTERVAL_8H_MS = 8 * 3600 * 1000


def get_binance_tasks(
    start_date: str | None = None,
    end_date: str | None = None,
    sample_days: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Build task list for Binance USD-M and Spot basis control.

    If start_date and end_date are provided, uses explicit date range [start_date, end_date) exclusive.
    Otherwise defaults to Q3 2026.
    """
    if start_date is not None and end_date is not None:
        months = generate_month_range(start_date, end_date)
        days = generate_date_range(start_date, end_date, end_inclusive=False)
        trade_days = list(sample_days) if sample_days is not None else ([days[0]] if days else [])
    else:
        months = list(MONTHS_Q3)
        days = list(DAYS_Q3)
        trade_days = list(sample_days) if sample_days is not None else list(SAMPLE_TRADE_DAYS_Q3)
    tasks = []

    # 1. Monthly Klines (1m)
    for sym in SYMBOLS:
        for m in months:
            tasks.append({
                "venue": "binance",
                "market": "futures_um",
                "family": "klines",
                "symbol": sym,
                "interval": "1m",
                "period": m,
                "is_monthly": True,
                "url": f"{ORIGIN}/data/futures/um/monthly/klines/{sym}/1m/{sym}-1m-{m}.zip",
                "expected_interval_ms": INTERVAL_1M_MS,
            })

    # 2. Monthly Mark Price Klines (1m)
    for sym in SYMBOLS:
        for m in months:
            tasks.append({
                "venue": "binance",
                "market": "futures_um",
                "family": "markPriceKlines",
                "symbol": sym,
                "interval": "1m",
                "period": m,
                "is_monthly": True,
                "url": f"{ORIGIN}/data/futures/um/monthly/markPriceKlines/{sym}/1m/{sym}-1m-{m}.zip",
                "expected_interval_ms": INTERVAL_1M_MS,
            })

    # 3. Monthly Funding Rate (8h events)
    for sym in SYMBOLS:
        for m in months:
            tasks.append({
                "venue": "binance",
                "market": "futures_um",
                "family": "fundingRate",
                "symbol": sym,
                "interval": "8h",
                "period": m,
                "is_monthly": True,
                "url": f"{ORIGIN}/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{m}.zip",
                "expected_interval_ms": INTERVAL_8H_MS,
            })

    # 4. Spot Monthly Klines (1m basis control)
    for sym in SYMBOLS:
        for m in months:
            tasks.append({
                "venue": "binance",
                "market": "spot",
                "family": "spot_klines",
                "symbol": sym,
                "interval": "1m",
                "period": m,
                "is_monthly": True,
                "url": f"{ORIGIN}/data/spot/monthly/klines/{sym}/1m/{sym}-1m-{m}.zip",
                "expected_interval_ms": INTERVAL_1M_MS,
            })

    # 5. Daily Metrics (OI / Long-Short ratios)
    for sym in SYMBOLS:
        for d in days:
            tasks.append({
                "venue": "binance",
                "market": "futures_um",
                "family": "metrics",
                "symbol": sym,
                "interval": "5m",
                "period": d,
                "is_monthly": False,
                "url": f"{ORIGIN}/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{d}.zip",
                "expected_interval_ms": INTERVAL_5M_MS,
            })

    # 6. Sample AggTrades Flow (1-day sample)
    for sym in SYMBOLS:
        for d in trade_days:
            tasks.append({
                "venue": "binance",
                "market": "futures_um",
                "family": "aggTrades",
                "symbol": sym,
                "interval": "tick",
                "period": d,
                "is_monthly": False,
                "url": f"{ORIGIN}/data/futures/um/daily/aggTrades/{sym}/{sym}-aggTrades-{d}.zip",
                "expected_interval_ms": None,
            })

    return tasks


def run_binance_expansion(
    output_root: Path,
    budget: Budget,
    action: str = "acquire",
    start_date: str | None = None,
    end_date: str | None = None,
    tranche_id: str | None = None,
) -> dict[str, Any]:
    """Execute Binance data acquisition and QC."""
    data_dir = output_root / "data"
    reports_dir = output_root

    fetcher = SafeFetcher(budget, rate_limit_delay=0.04)
    tasks = get_binance_tasks(start_date=start_date, end_date=end_date)

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

        folder = data_dir / fam
        folder.mkdir(parents=True, exist_ok=True)
        filename = url.rsplit("/", 1)[1]
        data_path = folder / filename
        checksum_path = folder / (filename + ".CHECKSUM")

        # Reuse pre-existing raw pilot files (e.g. fundingRate pilot) without re-downloading
        if not data_path.exists():
            pilot_raw = output_root / "raw" / fam / sym / filename
            if not pilot_raw.exists():
                pilot_raw = output_root / "raw" / fam / filename
            if pilot_raw.exists() and pilot_raw.stat().st_size > 0:
                shutil.copy2(pilot_raw, data_path)
                pilot_manifest = output_root / "funding_pilot_manifest.json"
                if pilot_manifest.exists():
                    try:
                        with pilot_manifest.open("r", encoding="utf-8") as pm_f:
                            pm_data = json.load(pm_f)
                            for obj in pm_data.get("objects", []):
                                if obj.get("symbol") == sym and obj.get("calendar_month_utc") == period:
                                    pub_sha = obj.get("publisher_checksum_sha256")
                                    if pub_sha and not checksum_path.exists():
                                        checksum_path.write_text(f"{pub_sha}  {filename}\n", encoding="utf-8")
                                    break
                    except (json.JSONDecodeError, OSError):
                        pass

        rec: dict[str, Any] = {
            "venue": "binance",
            "market": task["market"],
            "family": fam,
            "symbol": sym,
            "interval": task["interval"],
            "period": period,
            "is_monthly": task["is_monthly"],
            "url": url,
            "local_path": str(data_path.relative_to(output_root)),
        }

        if action == "acquire":
            # 1. Fetch checksum
            cs_meta = fetcher.fetch_file(url + ".CHECKSUM", checksum_path, is_checksum_file=True)
            # 2. Fetch data file
            data_meta = fetcher.fetch_file(url, data_path)

            if data_meta is None or cs_meta is None:
                rec["verdict"] = "OBJECT_NOT_FOUND"
                failed_objects.append(rec)
                records.append(rec)
                continue

            if data_meta.get("reused", False):
                total_reused += 1
            else:
                total_newly_acquired += 1

            rec["fetch"] = data_meta
        else:
            # Verify mode
            if not data_path.exists() or not checksum_path.exists():
                rec["verdict"] = "MISSING_LOCAL_FILE"
                failed_objects.append(rec)
                records.append(rec)
                continue

        # Checksum verification
        is_verified, pub_sha, local_sha = verify_publisher_checksum(data_path, checksum_path)
        rec["publisher_checksum"] = pub_sha
        rec["local_sha256"] = local_sha
        rec["publisher_checksum_verified"] = is_verified
        rec["publisher_checksum_absent"] = False

        if not is_verified:
            rec["verdict"] = "CHECKSUM_MISMATCH"
            failed_objects.append(rec)
            records.append(rec)
            continue

        # Offline QC
        qc_res = qc_zip_archive(data_path, fam, "binance", budget, expected_interval_ms)
        rec.update(qc_res)
        records.append(rec)

        # Update coverage tracking
        series_key = f"{fam}_{sym}_{task['interval']}"
        if series_key not in coverage_by_series:
            coverage_by_series[series_key] = {
                "venue": "binance",
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
            s_cov["total_rows"] += qc_res.get("rows", 0)
            s_cov["total_gaps"] += qc_res.get("gaps", 0)
            s_cov["total_duplicates"] += qc_res.get("duplicates", 0)
            if s_cov["start_utc"] is None or (qc_res.get("start_utc") and qc_res["start_utc"] < s_cov["start_utc"]):
                s_cov["start_utc"] = qc_res.get("start_utc")
            if s_cov["end_utc"] is None or (qc_res.get("end_utc") and qc_res["end_utc"] > s_cov["end_utc"]):
                s_cov["end_utc"] = qc_res.get("end_utc")

    # Generate Manifest
    disk_usage = budget.check_disk()
    terminal = "DATA_TRANCHE_VERIFIED" if len(failed_objects) == 0 else "DATA_PARTIAL_WITH_NEXT_BATCH"

    task_name = f"V065-DATA-R3_BINANCE_USDM_{tranche_id.upper()}" if tranche_id else "V065-DATA-R2_BINANCE_USDM_EXPANSION"
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
        "publisher": "Binance Vision",
        "publisher_url": ORIGIN,
        "venue": "binance",
        "task": task_name,
        "tranche_id": tranche_id,
        "start_date": start_date,
        "end_date": end_date,
        "terminal": terminal,
        "tranche_aim": tranche_aim,
        "next_resumable_batch": next_batch,
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
        "venue": "binance",
        "terminal": terminal,
        "coverage": coverage_by_series,
    }
    with (reports_dir / "coverage.json").open("w", encoding="utf-8") as f:
        json.dump(coverage_doc, f, indent=2, sort_keys=True)
        f.write("\n")

    qc_doc = {
        "manifest_version": "1.0",
        "venue": "binance",
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
                "rows": r.get("rows"),
                "start_utc": r.get("start_utc"),
                "end_utc": r.get("end_utc"),
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
