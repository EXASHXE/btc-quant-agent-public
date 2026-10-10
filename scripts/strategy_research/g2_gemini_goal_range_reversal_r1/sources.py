"""Official Binance Vision USD-M BTCUSDT 1m archive downloader and validator (2021-01 to 2023-12 only).

Strictly enforces:
- Only 2021, 2022, 2023 (36 monthly archives). Any 2024/2025/2026 access raises ValueError.
- Verifies HTTP status, URL prefix, SHA256 against official .CHECKSUM, single CSV member.
- Detects UTC timestamp unit from data (does not assume ms without checking).
- Validates all 12 Binance Vision kline columns including taker_buy_volume <= volume.
- Extracts 7-column float64 array: [open_time_ms, open, high, low, close, volume, taker_buy_volume].
"""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import math
import subprocess
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.sources import (
    BASE,
    FIELDS,
    ms,
    utcnow,
    validate_zip_checksum,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "evidence/v0.6/b_line/g2_gemini_goal_range_reversal_r1"
SCRATCH_DEFAULT = Path("/tmp/g2-gemini-goal-range-reversal-r1")
ALLOWED_YEARS = (2021, 2022, 2023)
ALLOWED_MONTHS = tuple(range(1, 13))


def detect_timestamp_unit(raw_ts: int, expected_start_ms: int) -> tuple[int, str]:
    """Detect timestamp unit (ms, us, or s) against expected UTC month start."""
    if raw_ts == expected_start_ms:
        return 1, "MILLISECONDS_DETECTED"
    if raw_ts == expected_start_ms * 1000:
        return 1000, "MICROSECONDS_DETECTED_CONVERTED_TO_MS"
    if raw_ts * 1000 == expected_start_ms:
        return -1000, "SECONDS_DETECTED_CONVERTED_TO_MS"
    if 1_500_000_000_000 <= raw_ts <= 1_750_000_000_000:
        return 1, "MILLISECONDS_DETECTED"
    if 1_500_000_000_000_000 <= raw_ts <= 1_750_000_000_000_000:
        return 1000, "MICROSECONDS_DETECTED_CONVERTED_TO_MS"
    if 1_500_000_000 <= raw_ts <= 1_750_000_000:
        return -1000, "SECONDS_DETECTED_CONVERTED_TO_MS"
    raise ValueError(f"Unrecognized UTC timestamp unit for value {raw_ts}")


def _to_ms(raw_ts: int, scale: int) -> int:
    if scale == 1:
        return raw_ts
    if scale > 1:
        return raw_ts // scale
    return raw_ts * (-scale)


def parse_month_with_taker(raw: bytes, year: int, month: int) -> tuple[np.ndarray, dict]:
    """Validate 12-column Binance USD-M 1m CSV and return 7-col array [t, o, h, l, c, v, tb_v]."""
    if year not in ALLOWED_YEARS or month not in ALLOWED_MONTHS:
        raise ValueError(f"Forbidden year/month {year}-{month:02d}: only 2021-01..2023-12 permitted")
    name = f"BTCUSDT-1m-{year}-{month:02d}.csv"
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.namelist() != [name]:
            raise ValueError(f"Unexpected ZIP member set: {archive.namelist()}")
        info = archive.getinfo(name)
        if info.file_size > 35_000_000:
            raise ValueError("CSV uncompressed budget exceeded")
        body = archive.read(name)

    expected_rows = calendar.monthrange(year, month)[1] * 1440
    start_ms = ms(f"{year}-{month:02d}-01T00:00:00Z")
    end_ms = start_ms + expected_rows * 60_000

    rows = csv.reader(io.StringIO(body.decode("utf-8-sig")))
    values: list[list[float]] = []
    header: list[str] | None = None
    close_times: list[int] = []
    zero_volume = 0
    extreme_bars = 0
    max_range_bps = 0.0
    total_quote_vol = 0.0
    total_taker_quote_vol = 0.0
    total_trades_count = 0
    detected_unit: str | None = None
    scale = 1

    for lineno, row in enumerate(rows, 1):
        if len(row) != 12:
            raise ValueError(f"CSV field count {len(row)} != 12 at line {lineno}")
        if lineno == 1 and not row[0].isdigit():
            header = row
            if row != FIELDS and row[0] != "open_time":
                raise ValueError(f"Unrecognized CSV header: {row}")
            continue
        raw_open_ts = int(row[0])
        raw_close_ts = int(row[6])
        if detected_unit is None:
            scale, detected_unit = detect_timestamp_unit(raw_open_ts, start_ms)
        timestamp = _to_ms(raw_open_ts, scale)
        close_ts = _to_ms(raw_close_ts, scale)

        nums = [float(v) for v in row]
        if not all(math.isfinite(v) for v in nums):
            raise ValueError(f"Non-finite number at line {lineno}")
        o, h, l, c, v = nums[1:6]
        qv, count_f, tb_v, tb_qv = nums[7], nums[8], nums[9], nums[10]

        if not (0 < l <= min(o, c) <= max(o, c) <= h and v >= 0 and close_ts == timestamp + 59_999):
            raise ValueError(f"Invalid OHLC/volume/close_time at line {lineno}")
        if qv < 0 or count_f < 0 or int(count_f) != count_f or tb_v < 0 or tb_qv < 0:
            raise ValueError(f"Negative or non-integral volume/trade count at line {lineno}")
        if tb_v > v + 1e-6 or tb_qv > qv + 1e-2:
            raise ValueError(
                f"Taker buy volume exceeds total volume at line {lineno}: tb_v={tb_v}, v={v}"
            )
        tb_v_clamped = min(v, max(0.0, tb_v))
        bar_range_bps = (h - l) / l * 10_000.0
        if bar_range_bps > max_range_bps:
            max_range_bps = bar_range_bps
        if bar_range_bps > 1500.0:
            extreme_bars += 1
        zero_volume += int(v == 0.0)
        total_quote_vol += qv
        total_taker_quote_vol += tb_qv
        total_trades_count += int(count_f)
        values.append([float(timestamp), o, h, l, c, v, tb_v_clamped])
        close_times.append(close_ts)

    array = np.asarray(values, dtype=np.float64)
    if array.shape != (expected_rows, 7):
        raise ValueError(f"Month row shape {array.shape} != expected ({expected_rows}, 7)")
    times = array[:, 0].astype(np.int64)
    diff = np.diff(times)
    duplicate = int(np.sum(diff == 0))
    gaps = int(np.sum(diff > 60_000))
    out_of_order = int(np.sum(diff <= 0))
    if duplicate or gaps or out_of_order or not np.array_equal(times, np.arange(start_ms, end_ms, 60_000)):
        raise ValueError("Non-complete, duplicate, gapped, or out-of-order month")

    meta = {
        "csv_member": name,
        "csv_sha256": hashlib.sha256(body).hexdigest(),
        "csv_bytes": len(body),
        "physical_lines": len(body.splitlines()),
        "price_rows": len(values),
        "header": header,
        "field_layout": FIELDS,
        "detected_timestamp_unit": detected_unit,
        "min_open_utc": datetime.fromtimestamp(start_ms / 1000, UTC).isoformat(),
        "max_open_utc": datetime.fromtimestamp(int(times[-1]) / 1000, UTC).isoformat(),
        "max_close_ms": close_times[-1],
        "end_exclusive_ms": end_ms,
        "duplicates": duplicate,
        "gaps": gaps,
        "out_of_order": out_of_order,
        "zero_volume_minutes": zero_volume,
        "extreme_range_gt_1500bps_minutes": extreme_bars,
        "max_1m_range_bps": round(max_range_bps, 4),
        "min_low_price": float(np.min(array[:, 3])),
        "max_high_price": float(np.max(array[:, 2])),
        "total_base_volume": round(float(np.sum(array[:, 5])), 6),
        "total_taker_buy_base_volume": round(float(np.sum(array[:, 6])), 6),
        "taker_buy_share": round(
            float(np.sum(array[:, 6]) / np.sum(array[:, 5])) if np.sum(array[:, 5]) > 0 else 0.0,
            6,
        ),
        "total_quote_volume": round(total_quote_vol, 2),
        "total_taker_buy_quote_volume": round(total_taker_quote_vol, 2),
        "total_trade_count": total_trades_count,
    }
    return array, meta


def fetch_with_timing(url: str, target: Path) -> dict:
    if not url.startswith(BASE):
        raise ValueError(f"Unexpected network source: {url}")
    for forbidden in ("2024-", "2025-", "2026-"):
        if forbidden in url:
            raise ValueError(f"Forbidden year in URL: {url}")
    headers = target.with_suffix(target.suffix + ".headers")
    t0 = time.monotonic()
    completed = subprocess.run(
        [
            "curl",
            "--silent",
            "--show-error",
            "--location",
            "--max-redirs",
            "2",
            "--proto",
            "=https",
            "--connect-timeout",
            "20",
            "--max-time",
            "120",
            "--retry",
            "3",
            "--dump-header",
            str(headers),
            "--output",
            str(target),
            "--write-out",
            "%{http_code}\n%{url_effective}\n%{http_version}\n%{time_total}",
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed_ms = round((time.monotonic() - t0) * 1000.0, 2)
    lines = completed.stdout.splitlines()
    status = int(lines[0]) if lines and lines[0].isdigit() else 0
    returned = lines[1] if len(lines) > 1 else ""
    if returned and not returned.startswith(BASE):
        raise ValueError("Redirect outside authorized official archive prefix")
    return {
        "requested_url": url,
        "returned_url": returned,
        "http_status": status,
        "http_version": lines[2] if len(lines) > 2 else None,
        "curl_time_total_s": float(lines[3]) if len(lines) > 3 and lines[3] else None,
        "wall_elapsed_ms": elapsed_ms,
        "curl_exit": completed.returncode,
        "download_utc": utcnow(),
        "error": completed.stderr[:500] if completed.returncode else None,
    }


def verify_wave_freeze(wave_id: str, freeze_sha: str) -> dict:
    """Verify that WAVE_0x_FROZEN_REGISTRY.json matches its committed git blob at freeze_sha."""
    if len(freeze_sha) != 40 or any(c not in "0123456789abcdef" for c in freeze_sha):
        raise ValueError(f"Exact 40-char hex freeze SHA required, got: {freeze_sha}")
    reg_path = EVIDENCE / f"{wave_id}_FROZEN_REGISTRY.json"
    rel = reg_path.relative_to(ROOT).as_posix()
    committed_bytes = subprocess.check_output(["git", "show", f"{freeze_sha}:{rel}"], cwd=ROOT)
    if committed_bytes != reg_path.read_bytes():
        raise ValueError(f"{reg_path.name} differs from committed freeze blob at {freeze_sha}")
    registry = json.loads(committed_bytes)
    if registry.get("wave_id") != wave_id:
        raise ValueError(f"Registry wave_id mismatch: {registry.get('wave_id')} != {wave_id}")
    if not (1 <= len(registry.get("candidates", [])) <= 6):
        raise ValueError("Wave candidate count must be between 1 and 6")
    return registry


def ensure_2021_2023_sources(scratch: Path, freeze_sha: str, wave_id: str = "WAVE_01") -> dict:
    """Download or verify cached 2021-01..2023-12 (36 months) in task-owned scratch."""
    verify_wave_freeze(wave_id, freeze_sha)
    resolved = scratch.resolve()
    if str(resolved) != str(SCRATCH_DEFAULT.resolve()):
        raise ValueError(f"Only task-owned scratch {SCRATCH_DEFAULT} is allowed, got {resolved}")
    scratch.mkdir(mode=0o700, parents=True, exist_ok=True)

    manifest_path = EVIDENCE / "SOURCE_MANIFEST_2021_2023.json"
    existing_records: dict[tuple[int, int], dict] = {}
    first_read_utc: str | None = None
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        first_read_utc = old.get("first_price_csv_read_at_utc")
        for r in old.get("records", []):
            if r.get("status") == "VERIFIED_COMPLETE_PUBLIC_MONTH":
                existing_records[(int(r["year"]), int(r["month"]))] = r

    records: list[dict] = []
    started_utc = utcnow()

    for year in ALLOWED_YEARS:
        for month in ALLOWED_MONTHS:
            zip_name = f"BTCUSDT-1m-{year}-{month:02d}.zip"
            url = f"{BASE}{zip_name}"
            check_url = f"{url}.CHECKSUM"
            zip_file = scratch / zip_name
            check_file = scratch / f"{zip_name}.CHECKSUM"
            npy_file = scratch / f"validated-{year}-{month:02d}.npy"

            if (
                (year, month) in existing_records
                and zip_file.exists()
                and check_file.exists()
                and npy_file.exists()
            ):
                prev = existing_records[(year, month)]
                raw_bytes = zip_file.read_bytes()
                actual_sha = validate_zip_checksum(raw_bytes, check_file.read_text(), zip_name)
                arr = np.load(npy_file, allow_pickle=False)
                if actual_sha == prev["zip_sha256"] and arr.shape == (prev["price_rows"], 7):
                    records.append(prev)
                    continue

            zip_fetch = fetch_with_timing(url, zip_file)
            check_fetch = fetch_with_timing(check_url, check_file)
            record: dict = {
                "year": year,
                "month": month,
                "zip_fetch": zip_fetch,
                "checksum_fetch": check_fetch,
            }
            if (
                zip_fetch["http_status"] != 200
                or check_fetch["http_status"] != 200
                or zip_fetch["curl_exit"] != 0
                or check_fetch["curl_exit"] != 0
            ):
                record["status"] = "HTTP_SOURCE_MISSING"
                records.append(record)
            else:
                try:
                    raw_bytes = zip_file.read_bytes()
                    record["zip_sha256"] = validate_zip_checksum(
                        raw_bytes, check_file.read_text(), zip_name
                    )
                    record["checksum_sha256"] = hashlib.sha256(check_file.read_bytes()).hexdigest()
                    if first_read_utc is None:
                        first_read_utc = utcnow()
                    array, meta = parse_month_with_taker(raw_bytes, year, month)
                    record.update(meta)
                    record["npy_sha256"] = hashlib.sha256(array.tobytes()).hexdigest()
                    record["status"] = "VERIFIED_COMPLETE_PUBLIC_MONTH"
                    np.save(npy_file, array, allow_pickle=False)
                except (ValueError, zipfile.BadZipFile, UnicodeError) as exc:
                    record["status"] = "SOURCE_INTEGRITY_FAIL"
                    record["error"] = str(exc)
                records.append(record)
            print(
                json.dumps(
                    {
                        "year": year,
                        "month": month,
                        "status": record["status"],
                        "rows": record.get("price_rows"),
                        "taker_buy_share": record.get("taker_buy_share"),
                    }
                ),
                flush=True,
            )

    verified_count = sum(1 for r in records if r["status"] == "VERIFIED_COMPLETE_PUBLIC_MONTH")
    integrity_fails = [r for r in records if r["status"] == "SOURCE_INTEGRITY_FAIL"]
    if (
        manifest_path.exists()
        and verified_count == 36
        and not integrity_fails
        and old.get("gate") == "PASS_PUBLIC_BTC_2021_2023_COMPLETE"
    ):
        return old
    manifest = {
        "schema": "GEMINI_GOAL_B_PUBLIC_BTC_2021_2023_MANIFEST_V1",
        "initial_wave_freeze_sha": freeze_sha,
        "started_at_utc": started_utc,
        "finished_at_utc": utcnow(),
        "first_price_csv_read_at_utc": first_read_utc,
        "authorized_years": list(ALLOWED_YEARS),
        "forbidden_years_accessed": 0,
        "owner_or_protected_body_reads": 0,
        "private_api_or_order_calls": 0,
        "total_months_requested": 36,
        "verified_complete_months": verified_count,
        "total_verified_rows": sum(r.get("price_rows", 0) for r in records),
        "price_grade": "COST_PROXY_DEV_ONLY",
        "mark_source": "NOT_ACQUIRED_UNKNOWN",
        "funding_source": "NOT_ACQUIRED_UNKNOWN",
        "rights": {
            "provider": "Binance Vision",
            "dataset_terms": "https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md",
            "license": "CC BY-NC-SA 4.0 noncommercial research attribution",
            "raw_data_rehosting": False,
        },
        "gate": (
            "PASS_PUBLIC_BTC_2021_2023_COMPLETE"
            if verified_count == 36 and not integrity_fails
            else "BLOCKED_OFFICIAL_SOURCE_OR_INTEGRITY"
        ),
        "records": records,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def load_contiguous_segments(scratch: Path, manifest: dict) -> list[dict]:
    segments: list[dict] = []
    current_arrays: list[np.ndarray] = []
    current_months: list[tuple[int, int]] = []

    for r in sorted(manifest["records"], key=lambda x: (x["year"], x["month"])):
        y, m = int(r["year"]), int(r["month"])
        if r["status"] != "VERIFIED_COMPLETE_PUBLIC_MONTH":
            if current_arrays:
                data = np.concatenate(current_arrays, axis=0)
                segments.append({"months": list(current_months), "data": data})
                current_arrays = []
                current_months = []
            continue
        npy_path = scratch / f"validated-{y}-{m:02d}.npy"
        arr = np.load(npy_path, allow_pickle=False)
        if len(arr) != r["price_rows"]:
            raise ValueError(f"Row count mismatch in cached {npy_path}")
        if current_arrays and int(arr[0, 0]) != int(current_arrays[-1][-1, 0]) + 60_000:
            data = np.concatenate(current_arrays, axis=0)
            segments.append({"months": list(current_months), "data": data})
            current_arrays = []
            current_months = []
        current_arrays.append(arr)
        current_months.append((y, m))

    if current_arrays:
        data = np.concatenate(current_arrays, axis=0)
        segments.append({"months": list(current_months), "data": data})
    return segments


def build_monthly_scoring_folds(manifest: dict) -> list[dict]:
    verified = {
        (int(r["year"]), int(r["month"]))
        for r in manifest["records"]
        if r["status"] == "VERIFIED_COMPLETE_PUBLIC_MONTH"
    }
    ordered = [(y, m) for y in ALLOWED_YEARS for m in ALLOWED_MONTHS]
    folds: list[dict] = []
    contiguous_prior = 0
    for y, m in ordered:
        if (y, m) not in verified:
            contiguous_prior = 0
            continue
        if contiguous_prior >= 1:
            days = calendar.monthrange(y, m)[1]
            m_start = ms(f"{y}-{m:02d}-01T00:00:00Z")
            m_end = m_start + days * 86_400_000
            score_start = m_start + 86_400_000
            score_end = m_end - 86_400_000
            folds.append(
                {
                    "id": f"{y}-{m:02d}",
                    "year": y,
                    "month": m,
                    "month_start_ms": m_start,
                    "month_end_ms": m_end,
                    "start_ms": score_start,
                    "end_ms": score_end,
                    "score_start_utc": datetime.fromtimestamp(score_start / 1000, UTC).isoformat(),
                    "score_end_utc": datetime.fromtimestamp(score_end / 1000, UTC).isoformat(),
                    "purge_hours_each_edge": 24,
                }
            )
        contiguous_prior += 1
    return folds


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scratch", type=Path, default=SCRATCH_DEFAULT)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--wave", default="WAVE_01")
    args = parser.parse_args()
    manifest = ensure_2021_2023_sources(args.scratch, args.freeze, args.wave)
    if manifest["gate"].startswith("BLOCKED"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
