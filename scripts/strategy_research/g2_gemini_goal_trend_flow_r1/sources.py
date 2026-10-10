"""Official Binance Vision 1m archive reader, validator, and data source pipeline for BTCUSDT."""
from __future__ import annotations

import calendar
import csv
import hashlib
import io
import math
from pathlib import Path
import zipfile
import numpy as np

DATA_DIR = Path("/tmp/gemini_goal_trend_flow_r1")


def validate_zip_checksum(zip_path: Path, checksum_path: Path) -> bool:
    """Validate sha256 checksum against official .CHECKSUM file."""
    if not zip_path.exists() or not checksum_path.exists():
        return False
    expected = checksum_path.read_text().strip().split()[0].lower()
    actual = hashlib.sha256(zip_path.read_bytes()).hexdigest().lower()
    return expected == actual


def parse_and_validate_month(year: int, month: int) -> np.ndarray:
    """Parse monthly 1m ZIP archive, validate OHLCV integrity, and cache as npy."""
    cached_path = DATA_DIR / f"validated-{year}-{month:02d}.npy"
    if cached_path.exists():
        return np.load(cached_path)

    zip_name = f"BTCUSDT-1m-{year}-{month:02d}.zip"
    zip_path = DATA_DIR / zip_name
    checksum_path = DATA_DIR / f"{zip_name}.CHECKSUM"

    if not validate_zip_checksum(zip_path, checksum_path):
        raise ValueError(f"Checksum validation failed for {zip_name}")

    csv_name = f"BTCUSDT-1m-{year}-{month:02d}.csv"
    with zipfile.ZipFile(zip_path) as zf:
        if csv_name not in zf.namelist():
            raise ValueError(f"CSV {csv_name} not found in {zip_name}")
        body = zf.read(csv_name).decode("utf-8-sig")

    reader = csv.reader(io.StringIO(body))
    rows = []
    expected_rows = calendar.monthrange(year, month)[1] * 1440

    for lineno, r in enumerate(reader, start=1):
        if lineno == 1 and not r[0].isdigit():
            # Header line
            continue
        if len(r) != 12:
            raise ValueError(f"Invalid field count at line {lineno} in {csv_name}: {len(r)}")

        t = int(r[0])
        o = float(r[1])
        h = float(r[2])
        l = float(r[3])
        c = float(r[4])
        v = float(r[5])
        close_t = int(r[6])
        tbv = float(r[9])

        if not (0 < l <= min(o, c) <= max(o, c) <= h):
            raise ValueError(f"Invalid OHLC relationship at line {lineno} in {csv_name}")
        if close_t != t + 59999:
            raise ValueError(f"Invalid close_time at line {lineno} in {csv_name}")
        if v < 0 or tbv < 0 or tbv > v + 1e-4:
            raise ValueError(f"Invalid volume or taker_buy_volume at line {lineno} in {csv_name}")

        rows.append([float(t), o, h, l, c, v, tbv])

    arr = np.asarray(rows, dtype=np.float64)
    if arr.shape != (expected_rows, 7):
        raise ValueError(f"Row count mismatch in {csv_name}: got {arr.shape[0]}, expected {expected_rows}")

    # Check strict 60000 ms increments
    diffs = np.diff(arr[:, 0].astype(np.int64))
    if not np.all(diffs == 60000):
        raise ValueError(f"Non-contiguous timestamps detected in {csv_name}")

    np.save(cached_path, arr)
    return arr


def load_month(year: int, month: int) -> np.ndarray:
    """Load validated monthly array (year between 2021 and 2023)."""
    if year < 2021 or year > 2023:
        raise ValueError(f"Year {year} outside authorized development range 2021-2023")
    return parse_and_validate_month(year, month)


def get_monthly_folds() -> list[dict]:
    """Return 35 monthly folds (2021-02 to 2023-12) with warmup metadata and 24h edge embargo."""
    folds = []
    # 2021-01 is warmup only. Scored months start at 2021-02.
    all_months = []
    for y in range(2021, 2024):
        for m in range(1, 13):
            all_months.append((y, m))

    for idx in range(1, len(all_months)):
        scored_y, scored_m = all_months[idx]
        prev_y, prev_m = all_months[idx - 1]

        days_in_month = calendar.monthrange(scored_y, scored_m)[1]
        start_ms = int(calendar.timegm((scored_y, scored_m, 1, 0, 0, 0, 0, 0, 0)) * 1000)
        end_ms = start_ms + days_in_month * 1440 * 60000

        # 24h embargo boundaries for trade entries
        embargo_start_ms = start_ms + 24 * 3600 * 1000
        embargo_end_ms = end_ms - 24 * 3600 * 1000

        folds.append({
            "year": scored_y,
            "month": scored_m,
            "prev_year": prev_y,
            "prev_month": prev_m,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "embargo_start_ms": embargo_start_ms,
            "embargo_end_ms": embargo_end_ms,
        })
    return folds
