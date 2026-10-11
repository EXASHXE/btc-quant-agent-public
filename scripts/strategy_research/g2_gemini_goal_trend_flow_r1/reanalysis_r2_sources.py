"""Independent, bounded Binance Vision source check for the R2 development replay."""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import subprocess
import zipfile
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np

SCRATCH_ROOT = Path("/tmp/gemini_goal_trend_flow_r1")
DATA_DIR = SCRATCH_ROOT
BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/"
MAX_CSV_BYTES = 30_000_000
FIELDS = (
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
)
HEADER_ALIASES = (
    FIELDS,
    (*FIELDS[:8], "number_of_trades", *FIELDS[9:]),
    (*FIELDS[:9], "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"),
    (*FIELDS[:8], "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"),
)


def _authorized(year: int, month: int) -> None:
    # This guard must precede *all* path creation, stat and network activity.
    if not (2021 <= year <= 2023 and 1 <= month <= 12):
        raise ValueError("month outside authorized 2021-01..2023-12 development source scope")


def _names(year: int, month: int) -> tuple[str, str]:
    stem = f"BTCUSDT-1m-{year}-{month:02d}"
    return f"{stem}.zip", f"{stem}.csv"


def _decimal(value: str, label: str, line: int) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid {label} at CSV line {line}") from exc
    if not number.is_finite():
        raise ValueError(f"nonfinite {label} at CSV line {line}")
    return number


def _millis(value: str, label: str, line: int) -> int:
    if not value.isascii() or not value.isdecimal() or len(value) != 13:
        raise ValueError(f"invalid millisecond {label} at CSV line {line}")
    return int(value)


def validate_archive_bytes(raw_zip: bytes, raw_checksum: bytes, year: int, month: int) -> tuple[np.ndarray, dict]:
    """Parse every invented or public CSV row; never trust an existing derived .npy."""
    _authorized(year, month)
    zip_name, csv_name = _names(year, month)
    zip_digest = hashlib.sha256(raw_zip).hexdigest()
    try:
        check_words = raw_checksum.decode("ascii").strip().split()
    except UnicodeDecodeError as exc:
        raise ValueError("non-ASCII provider CHECKSUM") from exc
    if (len(check_words) != 2 or check_words[0].lower() != zip_digest
            or check_words[1].lstrip("*") != zip_name):
        raise ValueError("provider ZIP SHA-256 or filename mismatch")

    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != csv_name or members[0].is_dir():
            raise ValueError("ZIP must contain exactly the expected monthly CSV")
        if members[0].file_size > MAX_CSV_BYTES:
            raise ValueError("uncompressed CSV exceeds 30 MB source budget")
        raw_csv = archive.read(members[0])
    if len(raw_csv) > MAX_CSV_BYTES:
        raise ValueError("actual CSV exceeds 30 MB source budget")
    try:
        text = raw_csv.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV is not UTF-8") from exc

    start_ms = calendar.timegm((year, month, 1, 0, 0, 0)) * 1000
    expected_rows = calendar.monthrange(year, month)[1] * 1440
    data: list[tuple[float, ...]] = []
    header: list[str] | None = None
    zero_volume = 0
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    for line, row in enumerate(reader, 1):
        if len(row) != 12:
            raise ValueError(f"expected 12 CSV fields at line {line}")
        if line == 1 and (not row[0].isascii() or not row[0].isdecimal()):
            if tuple(row) not in HEADER_ALIASES:
                raise ValueError("unrecognized or reordered 12-field CSV header")
            header = row
            continue
        if len(data) >= expected_rows:
            raise ValueError("extra CSV price row")
        timestamp = _millis(row[0], "open_time", line)
        close_time = _millis(row[6], "close_time", line)
        expected_open = start_ms + len(data) * 60_000
        if timestamp != expected_open or close_time != timestamp + 59_999:
            raise ValueError(f"non-UTC-minute, duplicate, gap or wrong close clock at line {line}")
        o, h, lo, c, v = (_decimal(row[i], FIELDS[i], line) for i in range(1, 6))
        q = _decimal(row[7], FIELDS[7], line)
        trades = _decimal(row[8], FIELDS[8], line)
        buy = _decimal(row[9], FIELDS[9], line)
        buy_quote = _decimal(row[10], FIELDS[10], line)
        _decimal(row[11], FIELDS[11], line)
        if not (0 < lo <= min(o, c) <= max(o, c) <= h):
            raise ValueError(f"invalid OHLC at line {line}")
        if not (v >= 0 and q >= 0 and trades >= 0 and trades == trades.to_integral_value()
                and 0 <= buy <= v and 0 <= buy_quote <= q):
            raise ValueError(f"invalid volume, trade count or signed-flow base units at line {line}")
        values = (float(timestamp), float(o), float(h), float(lo), float(c), float(v), float(buy))
        if not all(np.isfinite(x) for x in values):
            raise ValueError(f"unrepresentable float field at line {line}")
        data.append(values)
        zero_volume += int(v == 0)
    if len(data) != expected_rows:
        raise ValueError(f"incomplete month: {len(data)} of {expected_rows} minute rows")
    array = np.asarray(data, dtype=np.float64)
    return array, {
        "status": "VERIFIED_COMPLETE_PUBLIC_TRADE_PRICE_MONTH",
        "year": year, "month": month, "price_rows": len(data),
        "csv_member": csv_name, "csv_bytes": len(raw_csv),
        "csv_sha256": hashlib.sha256(raw_csv).hexdigest(),
        "zip_sha256": zip_digest,
        "checksum_sha256": hashlib.sha256(raw_checksum).hexdigest(),
        "header": header, "field_layout": list(FIELDS),
        "first_open_ms": start_ms,
        "last_open_ms": start_ms + (expected_rows - 1) * 60_000,
        "last_close_ms": start_ms + expected_rows * 60_000 - 1,
        "expected_rows": expected_rows,
        "gaps": 0, "duplicates": 0, "out_of_order": 0,
        "zero_volume_minutes": zero_volume,
        "source_grade": "PUBLIC_TRADE_PRICE_ONLY_NOT_MARK_FUNDING_OR_HISTORICAL_AS_OF",
    }


def _fetch(url: str, path: Path) -> dict:
    if not url.startswith(BASE_URL):
        raise ValueError("URL outside fixed Binance Vision USD-M prefix")
    partial = path.with_name(path.name + ".r2-partial")
    headers_path = path.with_name(path.name + ".r2-headers")
    cmd = ["curl", "--silent", "--show-error", "--location", "--max-redirs", "2",
           "--proto", "=https", "--connect-timeout", "20", "--max-time", "120",
           "--retry", "2", "--max-filesize", str(MAX_CSV_BYTES),
           "--dump-header", str(headers_path), "--output", str(partial),
           "--write-out", "%{http_code}\n%{url_effective}\n%{http_version}", url]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    lines = result.stdout.splitlines()
    status = int(lines[0]) if lines and lines[0].isdecimal() else 0
    returned = lines[1] if len(lines) > 1 else ""
    metadata = {
        "requested_url": url, "returned_url": returned, "http_status": status,
        "http_version": lines[2] if len(lines) > 2 else None,
        "curl_exit": result.returncode,
        "download_utc": datetime.now(UTC).isoformat(),
        "response_headers": headers_path.read_text(errors="replace") if headers_path.exists() else "",
        "error": result.stderr[:1000] if result.returncode else None,
    }
    if result.returncode or status != 200 or not returned.startswith(BASE_URL):
        partial.unlink(missing_ok=True)
        raise ValueError(f"official archive fetch failed: {metadata}")
    partial.replace(path)
    return metadata


def load_validated_month(year: int, month: int, *, allow_download: bool = False, refresh_provider_checksum: bool = False) -> tuple[np.ndarray, dict]:
    """Check one authorized month from A-owned scratch or explicitly fetch official bytes."""
    _authorized(year, month)
    scratch = DATA_DIR
    if scratch.resolve() != SCRATCH_ROOT:
        raise ValueError("source scratch must be the A task-owned /tmp directory")
    zip_name, _ = _names(year, month)
    zip_path = scratch / zip_name
    checksum_path = scratch / f"{zip_name}.CHECKSUM"
    if zip_path.is_symlink() or checksum_path.is_symlink():
        raise ValueError("symlinked source file is outside the bounded A scratch contract")
    zip_url = BASE_URL + zip_name
    check_url = zip_url + ".CHECKSUM"
    downloads: dict[str, dict] = {}
    if allow_download:
        scratch.mkdir(mode=0o700, exist_ok=True)
    for kind, path, url in (("zip", zip_path, zip_url), ("checksum", checksum_path, check_url)):
        if path.exists():
            downloads[kind] = {"origin": "EXISTING_A_OWNED_SCRATCH", "requested_url": url}
        elif allow_download:
            downloads[kind] = {"origin": "FETCHED_OFFICIAL_BINANCE_VISION", **_fetch(url, path)}
        else:
            raise FileNotFoundError(f"missing authorized source file: {path.name}")
    if refresh_provider_checksum:
        if not allow_download:
            raise ValueError("Refreshing official checksum requires authorized download flag")
        live_check = scratch / f"{zip_name}.r2-provider.CHECKSUM"
        downloads["checksum"] = {"origin": "FRESH_OFFICIAL_PROVIDER_CHECKSUM", **_fetch(check_url, live_check)}
        raw_zip = zip_path.read_bytes()
        raw_check = live_check.read_bytes()
        advertised = raw_check.decode("ascii").strip().split()[0]
        if hashlib.sha256(raw_zip).hexdigest() != advertised:
            downloads["zip"] = {"origin": "REFETCH_AFTER_PROVIDER_REVISION_OR_BAD_CACHE", **_fetch(zip_url, zip_path)}
        checksum_path = live_check
    array, receipt = validate_archive_bytes(zip_path.read_bytes(), checksum_path.read_bytes(), year, month)
    receipt.update({
        "zip_path": str(zip_path), "checksum_path": str(checksum_path),
        "zip_url": zip_url, "checksum_url": check_url,
        "source_files": downloads,
        "rechecked_full_csv_bytes": True,
        "derived_npy_cache_trusted": False,
    })
    return array, receipt
