"""Deterministic R11-D2 Binance Core Historical Data Foundation Pilot.

Python stdlib only. No external API calls; official Binance Vision only.
Never prints raw data rows. Validates checksums, schemas, time grids,
units, duplicate daily/monthly representations, and PIT semantics.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterator
import csv
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
from http.client import IncompleteRead
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

ORIGIN = "https://data.binance.vision"
TERMS_BLOB = "87d04e216f62c86a2c797fbb7637404d6d602687"

# Instruments
SYMBOLS = ("BTCUSDT", "ETHUSDT")

# Reused R10-D1 dates (2022-09-15..21)
REUSED_DAYS = tuple((date(2022, 9, 15) + timedelta(days=i)).isoformat() for i in range(7))
REUSED_SYMBOLS = ("BTCUSDT",)
REUSED_FAMILIES = ("klines", "markPriceKlines", "metrics")

# Calibration interval (January 2024: 31 days)
CALIB_DAYS = tuple((date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(31))
CALIB_MONTH = "2024-01"

# Core families acquired across calibration interval
DAILY_CORE_FAMILIES = ("klines", "markPriceKlines", "metrics")
MONTHLY_CORE_FAMILIES = ("fundingRate",)

# Representative sample for trades & aggTrades (verified official Vision families)
TRADE_SAMPLE_DAYS = ("2024-01-01",)
TRADE_FAMILIES = ("aggTrades", "trades")

# Monthly klines for daily/monthly duplicate verification
DUPLICATE_CHECK_FAMILIES = ("klines",)

# Byte budgets
COMPRESSED_CAP = 250 * 1024**2   # 250 MiB
EXPANDED_CAP = 1000 * 1024**2    # 1000 MiB (1 GiB)

# Schemas
BARS_SCHEMA = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"
]
BARS_ALIASES = {
    "quote_asset_volume": "quote_volume",
    "number_of_trades": "count",
    "taker_buy_base_asset_volume": "taker_buy_volume",
    "taker_buy_quote_asset_volume": "taker_buy_quote_volume"
}
METRICS_SCHEMA = [
    "create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio"
]
FUNDING_RATE_SCHEMA = [
    "calc_time", "funding_interval_hours", "last_funding_rate"
]
AGG_TRADES_SCHEMA = [
    "agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
    "transact_time", "is_buyer_maker"
]
TRADES_SCHEMA = [
    "id", "price", "qty", "quote_qty", "time", "is_buyer_maker"
]

GATES = (
    "R9_L1_PAUSE_NEW_ALPHA_RESEARCH_PENDING_EXTERNAL_SOURCE_EVIDENCE / "
    "SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / "
    "G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE"
)


class SafetyError(Exception):
    """Sanitized constant reason codes for pipeline stops."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise SafetyError(code)


def object_url(family: str, symbol: str, period: str, is_monthly: bool = False) -> str:
    """Build canonical Binance Vision public data URL."""
    require(symbol in SYMBOLS, "SOURCE_SCOPE_SYMBOL")
    if is_monthly:
        require(period == CALIB_MONTH, "SOURCE_SCOPE_MONTH")
        if family == "fundingRate":
            return f"{ORIGIN}/data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{period}.zip"
        if family == "klines":
            return f"{ORIGIN}/data/futures/um/monthly/klines/{symbol}/1m/{symbol}-1m-{period}.zip"
        raise SafetyError("UNSUPPORTED_MONTHLY_FAMILY")

    # Daily files
    valid_days = REUSED_DAYS if symbol in REUSED_SYMBOLS and period in REUSED_DAYS else CALIB_DAYS
    require(period in valid_days, "SOURCE_SCOPE_DAY")

    if family == "klines":
        return f"{ORIGIN}/data/futures/um/daily/klines/{symbol}/1m/{symbol}-1m-{period}.zip"
    if family == "markPriceKlines":
        return f"{ORIGIN}/data/futures/um/daily/markPriceKlines/{symbol}/1m/{symbol}-1m-{period}.zip"
    if family == "metrics":
        return f"{ORIGIN}/data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{period}.zip"
    if family == "aggTrades":
        return f"{ORIGIN}/data/futures/um/daily/aggTrades/{symbol}/{symbol}-aggTrades-{period}.zip"
    if family == "trades":
        return f"{ORIGIN}/data/futures/um/daily/trades/{symbol}/{symbol}-trades-{period}.zip"

    raise SafetyError("UNSUPPORTED_DAILY_FAMILY")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise SafetyError("REDIRECT_REFUSED")


class Budget:
    def __init__(self, compressed: int = COMPRESSED_CAP, expanded: int = EXPANDED_CAP):
        require(0 < compressed <= COMPRESSED_CAP and 0 < expanded <= EXPANDED_CAP,
                "BUDGET_CONFIGURATION")
        self.compressed_cap = compressed
        self.expanded_cap = expanded
        self.compressed = 0
        self.expanded = 0
        self.requested_urls: set[str] = set()

    def register(self, url: str) -> None:
        parts = urlsplit(url)
        require(parts.scheme == "https" and parts.netloc == "data.binance.vision",
                "SOURCE_SCOPE_ORIGIN")
        require(not parts.query and not parts.fragment, "SOURCE_SCOPE_CLEAN_URL")
        require(url not in self.requested_urls, "OBJECT_ALREADY_REQUESTED")
        self.requested_urls.add(url)

    def consume(self, n: int) -> None:
        require(0 <= n <= self.compressed_cap - self.compressed, "COMPRESSED_BUDGET")
        self.compressed += n

    def expand(self, n: int) -> None:
        require(0 <= n <= self.expanded_cap - self.expanded, "EXPANDED_BUDGET")
        self.expanded += n


class Fetcher:
    def __init__(self, budget: Budget):
        self.budget = budget
        self.opener = build_opener(NoRedirect())
        self.attempts: dict[str, int] = {}

    def get(self, url: str, path: Path) -> dict[str, str | int] | None:
        self.budget.register(url)
        is_checksum = url.endswith(".CHECKSUM")
        if path.exists():
            require(not path.is_symlink(), "OUTPUT_EXISTS_SYMLINK")
            # If already on disk (e.g. reused R10-D1 file), do not redownload
            return {
                "uri": url,
                "bytes": path.stat().st_size,
                "fetched_at_utc": "REUSED_LOCAL_EXISTING",
                "last_modified": "LOCAL",
                "etag": "LOCAL",
                "attempts": 0
            }

        require(not path.is_symlink(), "OUTPUT_IS_SYMLINK")
        for attempt in range(3):
            self.attempts[url] = attempt + 1
            try:
                req = Request(url, headers={"User-Agent": "R11-D2-core-pilot-QC/1",
                                            "Accept-Encoding": "identity"})
                with self.opener.open(req, timeout=45) as resp:
                    require(resp.status == 200, "HTTP_STATUS")
                    require(resp.geturl() == url, "REDIRECT_REFUSED")
                    require(resp.headers.get("Content-Encoding", "identity") == "identity",
                            "HTTP_ENCODING")
                    cap = 4096 if is_checksum else (self.budget.compressed_cap - self.budget.compressed)
                    length = resp.headers.get("Content-Length")
                    if length is not None:
                        require(length.isdigit() and 0 < int(length) <= cap, "HTTP_SIZE_BUDGET")

                    total = 0
                    with path.open("xb") as out:
                        while True:
                            remaining = 4096 - total if is_checksum else (
                                self.budget.compressed_cap - self.budget.compressed)
                            require(remaining > 0, "HTTP_SIZE_BUDGET")
                            chunk = resp.read(min(65536, remaining))
                            if not chunk:
                                break
                            if not is_checksum:
                                self.budget.consume(len(chunk))
                            out.write(chunk)
                            total += len(chunk)
                            if length is not None and total == int(length):
                                break
                    require(total > 0 and (length is None or total == int(length)), "HTTP_TRUNCATED")
                    return {
                        "uri": url,
                        "bytes": total,
                        "fetched_at_utc": datetime.now(UTC).isoformat(),
                        "last_modified": resp.headers.get("Last-Modified", "UNKNOWN"),
                        "etag": resp.headers.get("ETag", "UNKNOWN"),
                        "attempts": attempt + 1
                    }
            except IncompleteRead as exc:
                if not is_checksum:
                    self.budget.consume(len(exc.partial))
            except HTTPError as exc:
                if exc.code == 404:
                    return None
                if exc.code not in (408, 429, 500, 502, 503, 504):
                    raise SafetyError("HTTP_ACCESS_OR_STATUS_STOP") from None
            except (URLError, TimeoutError, ConnectionError, OSError):
                pass

            if path.exists():
                path.unlink()
            require(attempt < 2, "HTTP_RETRIES_EXHAUSTED")
            time.sleep(attempt + 1)

        raise SafetyError("HTTP_RETRIES_EXHAUSTED")


def verify_checksum(path: Path, checksum_path: Path) -> str:
    raw = checksum_path.read_bytes()
    require(len(raw) <= 4096, "CHECKSUM_FORMAT")
    try:
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]([^\r\n]+)\s*", raw.decode("ascii"))
    except UnicodeDecodeError:
        raise SafetyError("CHECKSUM_FORMAT") from None
    if match is None or match.group(2).strip() != path.name:
        raise SafetyError("CHECKSUM_IDENTITY")
    with path.open("rb") as src:
        digest = hashlib.file_digest(src, "sha256").hexdigest()
    if digest != match.group(1).lower():
        raise SafetyError("PUBLISHER_CHECKSUM_MISMATCH")
    return digest


def number(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise SafetyError("NUMERIC_TYPE") from None
    require(result.is_finite(), "NUMERIC_FINITE")
    return result


def integer(value: str) -> int:
    require(re.fullmatch(r"-?\d+", value) is not None, "INTEGER_TYPE")
    return int(value)


def qc_rows(rows: Iterator[list[str]], family: str, symbol: str, period: str, is_monthly: bool) -> dict[str, Any]:
    first = next(rows, None)
    if first is None:
        raise SafetyError("EMPTY_CSV")

    if family in ("klines", "markPriceKlines"):
        expected_schema = BARS_SCHEMA
        normalized = [BARS_ALIASES.get(v, v) for v in first]
        header = not first[0].isdigit()
        if header:
            require(normalized == expected_schema, "SCHEMA_DRIFT")
            schema = first
        else:
            schema = BARS_SCHEMA
            import itertools
            rows = itertools.chain([first], rows)
    elif family == "metrics":
        expected_schema = METRICS_SCHEMA
        header = first[0] == "create_time"
        require(header, "METRICS_HEADER_MISSING")
        require(first == expected_schema, "SCHEMA_DRIFT")
        schema = first
    elif family == "fundingRate":
        expected_schema = FUNDING_RATE_SCHEMA
        header = first[0] == "calc_time"
        require(header, "FUNDING_RATE_HEADER_MISSING")
        require(first == expected_schema, "SCHEMA_DRIFT")
        schema = first
    elif family == "aggTrades":
        expected_schema = AGG_TRADES_SCHEMA
        header = first[0] == "agg_trade_id"
        require(header, "AGG_TRADES_HEADER_MISSING")
        require(first == expected_schema, "SCHEMA_DRIFT")
        schema = first
    elif family == "trades":
        expected_schema = TRADES_SCHEMA
        header = first[0] == "id"
        require(header, "TRADES_HEADER_MISSING")
        require(first == expected_schema, "SCHEMA_DRIFT")
        schema = first
    else:
        raise SafetyError("UNSUPPORTED_QC_FAMILY")

    seen = 0
    complete = 0
    malformed = 0
    timestamps = []
    missing_fields: dict[str, int] = {}
    invalid_fields: dict[str, int] = {}

    start_ms = 0
    end_ms = 0
    if not is_monthly and family in ("klines", "markPriceKlines", "metrics", "aggTrades", "trades"):
        dt = datetime.fromisoformat(period).replace(tzinfo=UTC)
        start_ms = int(dt.timestamp() * 1000)
        end_ms = start_ms + 86400000

    prev_trade_id = -1
    for row in rows:
        seen += 1
        try:
            require(len(row) == len(expected_schema), "CSV_ROW_SHAPE")
            if family in ("klines", "markPriceKlines"):
                ts = integer(row[0])
                timestamps.append(ts)
                close_ts = integer(row[6])
                require(close_ts == ts + 59999, "BAR_CLOSE_TIME")
                cnt = integer(row[8])
                require(cnt >= 0, "COUNT_NONNEGATIVE")
                o, h, l, c = number(row[1]), number(row[2]), number(row[3]), number(row[4])
                require(0 < l <= min(o, c) <= max(o, c) <= h, "OHLC_RELATION")
                vol = number(row[5])
                taker_vol = number(row[9])
                require(0 <= taker_vol <= vol, "TAKER_VOLUME_BOUND")
                if family == "markPriceKlines":
                    require(vol == 0, "MARK_PRICE_VOLUME_ZERO")
            elif family == "metrics":
                require(row[1] == symbol, "INSTRUMENT_MISMATCH")
                dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                ts = int(dt.timestamp() * 1000)
                timestamps.append(ts)
                for col_name, v in zip(METRICS_SCHEMA[2:], row[2:], strict=True):
                    if not v.strip():
                        missing_fields[col_name] = missing_fields.get(col_name, 0) + 1
                    else:
                        try:
                            n = number(v)
                            require(n >= 0, "METRIC_NONNEGATIVE")
                        except SafetyError:
                            invalid_fields[col_name] = invalid_fields.get(col_name, 0) + 1
            elif family == "fundingRate":
                ts = integer(row[0])
                timestamps.append(ts)
                interval_hours = integer(row[1])
                require(interval_hours == 8, "FUNDING_INTERVAL_NOT_8H")
                rate = number(row[2])
                require(abs(rate) < 1, "FUNDING_RATE_MAGNITUDE_BOUND")
            elif family == "aggTrades":
                trade_id = integer(row[0])
                require(trade_id > prev_trade_id, "NONMONOTONIC_AGG_TRADE_ID")
                prev_trade_id = trade_id
                px = number(row[1])
                qty = number(row[2])
                require(px > 0 and qty > 0, "POSITIVE_PRICE_AND_QTY")
                first_id = integer(row[3])
                last_id = integer(row[4])
                require(first_id <= last_id, "TRADE_ID_BOUND")
                ts = integer(row[5])
                timestamps.append(ts)
                require(row[6].lower() in ("true", "false"), "BUYER_MAKER_BOOLEAN")
            elif family == "trades":
                trade_id = integer(row[0])
                require(trade_id > prev_trade_id, "NONMONOTONIC_TRADE_ID")
                prev_trade_id = trade_id
                px = number(row[1])
                qty = number(row[2])
                quote_qty = number(row[3])
                require(px > 0 and qty > 0 and quote_qty > 0, "POSITIVE_PRICE_AND_QTY")
                ts = integer(row[4])
                timestamps.append(ts)
                require(row[5].lower() in ("true", "false"), "BUYER_MAKER_BOOLEAN")

            complete += 1
        except (SafetyError, ValueError, OverflowError):
            malformed += 1

    errors = []
    if malformed:
        errors.append("MALFORMED_ROW")

    duplicates = len(timestamps) - len(set(timestamps))
    if family in ("klines", "markPriceKlines", "metrics", "fundingRate") and duplicates > 0:
        errors.append("DUPLICATE_TIMESTAMPS")

    expected_rows = 0
    missing_intervals = 0
    unexpected_intervals = 0
    observed_grid_type = "UNAPPLICABLE"

    if family in ("klines", "markPriceKlines"):
        if is_monthly:
            expected_rows = 31 * 1440  # 44,640
        else:
            expected_rows = 1440
            expected_set = set(range(start_ms, end_ms, 60000))
            actual_set = set(timestamps)
            missing_intervals = len(expected_set - actual_set)
            unexpected_intervals = len(actual_set - expected_set)
            if missing_intervals:
                errors.append("GRID_HOLE")
            if unexpected_intervals:
                errors.append("OFF_GRID_TIMESTAMP")
    elif family == "metrics":
        expected_rows = 288
        start_grid = set(range(start_ms, end_ms, 300000))
        end_grid = set(range(start_ms + 300000, end_ms + 300001, 300000))
        actual_set = set(timestamps)
        if actual_set == start_grid:
            observed_grid_type = "START_GRID_00:00_TO_23:55"
        elif actual_set == end_grid:
            observed_grid_type = "END_GRID_00:05_TO_00:00"
        else:
            observed_grid_type = "IRREGULAR"
            errors.append("GRID_ANOMALY")
    elif family == "fundingRate":
        expected_rows = 31 * 3  # 93 settlement intervals in 31 days
        step = 8 * 3600 * 1000
        # Check monotonic 8h step (allow publisher settlement engine jitter <= 5000 ms)
        for i in range(1, len(timestamps)):
            diff = timestamps[i] - timestamps[i - 1]
            if abs(diff - step) > 5000:
                errors.append("FUNDING_INTERVAL_GAP")
                break

    min_ts_iso = datetime.fromtimestamp(min(timestamps) / 1000, UTC).isoformat() if timestamps else None
    max_ts_iso = datetime.fromtimestamp(max(timestamps) / 1000, UTC).isoformat() if timestamps else None

    qc_status = "PASS" if not errors and not missing_fields else "PARTIAL_PASS" if not errors else "FAIL"

    res = {
        "family": family,
        "symbol": symbol,
        "period": period,
        "is_monthly": is_monthly,
        "schema": schema,
        "header_present": header,
        "total_rows": seen,
        "valid_rows": complete,
        "malformed_rows": malformed,
        "expected_rows": expected_rows,
        "duplicate_timestamps": duplicates,
        "missing_field_counts": missing_fields,
        "invalid_field_counts": invalid_fields,
        "missing_intervals": missing_intervals,
        "unexpected_intervals": unexpected_intervals,
        "timestamp_min_utc": min_ts_iso,
        "timestamp_max_utc": max_ts_iso,
        "observed_grid_type": observed_grid_type,
        "errors": errors,
        "qc": qc_status
    }

    if family == "metrics":
        res["pit_provenance"] = {
            "stock_snapshot_fields": ["sum_open_interest", "sum_open_interest_value"],
            "interval_flow_fields": ["sum_taker_long_short_vol_ratio"],
            "trader_ratio_fields": ["count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio", "count_long_short_ratio"],
            "economic_period_end": "UNPROVEN_FROM_ARCHIVE_LABEL",
            "publisher_label": "YYYY-MM-DD HH:MM:SS UTC",
            "archive_publication_time": "T+1_FOLLOWING_DAY",
            "receiver_first_known": "UNKNOWN",
            "pit_terminal": "PIT_UNKNOWN"
        }

    return res


def qc_zip(path: Path, check_path: Path, family: str, symbol: str, period: str,
           is_monthly: bool, budget: Budget) -> dict[str, Any]:
    digest = verify_checksum(path, check_path)
    with zipfile.ZipFile(path) as zf:
        members = zf.infolist()
        require(len(members) == 1, "ZIP_MEMBER_COUNT")
        m = members[0]
        require(m.filename == path.with_suffix(".csv").name, "ZIP_MEMBER_NAME")
        require("/" not in m.filename and "\\" not in m.filename, "ZIP_TRAVERSAL")
        require(not stat.S_ISLNK(m.external_attr >> 16) and not m.is_dir(), "ZIP_UNSAFE_MEMBER")
        require(m.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "ZIP_COMPRESSION")
        require(0 < m.file_size <= max(m.compress_size, 1) * 200, "ZIP_EXPANSION_RATIO")
        budget.expand(m.file_size)

        with zf.open(m) as f, io.TextIOWrapper(f, encoding="utf-8", errors="strict", newline="") as text:
            reader = csv.reader(text, strict=True)
            res = qc_rows(reader, family, symbol, period, is_monthly)

        res.update({
            "sha256": digest,
            "compressed_bytes": path.stat().st_size,
            "expanded_bytes": m.file_size,
            "publisher_checksum": "VERIFIED"
        })
        return res


def compare_daily_vs_monthly(daily_paths: list[Path], monthly_path: Path) -> dict[str, Any]:
    """Verifies that the union of 31 daily files exactly equals the monthly archive."""
    with zipfile.ZipFile(monthly_path) as zf:
        m = zf.infolist()[0]
        with zf.open(m) as f, io.TextIOWrapper(f, encoding="utf-8", newline="") as text:
            reader = csv.reader(text)
            monthly_header = next(reader)
            monthly_rows = list(reader)

    daily_rows: list[list[str]] = []
    daily_headers: list[list[str]] = []
    for dp in sorted(daily_paths):
        with zipfile.ZipFile(dp) as zf:
            m = zf.infolist()[0]
            with zf.open(m) as f, io.TextIOWrapper(f, encoding="utf-8", newline="") as text:
                reader = csv.reader(text)
                daily_headers.append(next(reader))
                daily_rows.extend(reader)

    headers_match = all(h == monthly_header for h in daily_headers)
    rows_count_match = len(monthly_rows) == len(daily_rows)
    exact_match = (headers_match and rows_count_match and monthly_rows == daily_rows)

    return {
        "monthly_rows_count": len(monthly_rows),
        "daily_rows_count": len(daily_rows),
        "headers_identical": headers_match,
        "rows_count_identical": rows_count_match,
        "exact_byte_for_byte_rows_identical": exact_match,
        "representation_verdict": "DUPLICATE_IDENTICAL_REPRESENTATION" if exact_match else "DISCREPANCY_DETECTED"
    }


def safe_workspace(workspace: Path) -> None:
    require(workspace.is_absolute(), "ABSOLUTE_WORKSPACE_REQUIRED")
    for p in (workspace, *workspace.parents):
        require(not p.is_symlink(), "WORKSPACE_SYMLINK")
    for d in ("data", "reports", "tmp"):
        p = workspace / d
        require(p.is_dir() and not p.is_symlink() and os.access(p, os.W_OK), "WORKSPACE_LAYOUT")

    # Verify disk space
    usage = shutil.disk_usage(workspace)
    require(usage.free >= 1024**3, "DISK_CAPACITY_INSUFFICIENT")

    # Terms check
    terms_file = workspace / "tmp/official-terms-current.md"
    require(terms_file.exists() and not terms_file.is_symlink(), "TERMS_FILE_MISSING")
    raw = terms_file.read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(blob == TERMS_BLOB, "TERMS_CHANGED_REVIEW_REQUIRED")


def execute(workspace: Path, acquire: bool) -> int:
    safe_workspace(workspace)
    data = workspace / "data"
    reports = workspace / "reports"
    manifest_path = reports / "acquisition.json"
    qc_path = reports / "offline-qc.json"

    budget = Budget()
    fetcher = Fetcher(budget)
    records = []

    disk_info = shutil.disk_usage(workspace)
    disk_measurement = {
        "total_gib": round(disk_info.total / 1024**3, 2),
        "used_gib": round(disk_info.used / 1024**3, 2),
        "free_gib": round(disk_info.free / 1024**3, 2),
        "mount": str(workspace)
    }

    # Define tasks
    tasks = []

    # 1. Reused R10-D1 files (BTCUSDT 2022-09-15..21)
    for fam in REUSED_FAMILIES:
        for day in REUSED_DAYS:
            tasks.append((fam, "BTCUSDT", day, False, True))

    # 2. Calibration interval 2024-01-01..31 for BTCUSDT and ETHUSDT core families
    for sym in SYMBOLS:
        for fam in DAILY_CORE_FAMILIES:
            for day in CALIB_DAYS:
                tasks.append((fam, sym, day, False, False))
        for fam in MONTHLY_CORE_FAMILIES:
            tasks.append((fam, sym, CALIB_MONTH, True, False))

    # 3. Monthly klines for daily vs monthly duplicate check
    for sym in SYMBOLS:
        tasks.append(("klines", sym, CALIB_MONTH, True, False))

    # 4. Representative verified sample for aggTrades and trades (2024-01-01)
    for sym in SYMBOLS:
        for fam in TRADE_FAMILIES:
            for day in TRADE_SAMPLE_DAYS:
                tasks.append((fam, sym, day, False, False))

    terminal = "R11_D2_BINANCE_CORE_PILOT_ACCEPTED_WITH_LIMITS"
    safety_code = None

    try:
        for fam, sym, period, is_monthly, is_reused in tasks:
            url = object_url(fam, sym, period, is_monthly)
            name = url.rsplit("/", 1)[1]
            folder = data / fam
            if acquire:
                folder.mkdir(parents=True, exist_ok=True)
            path = folder / name
            check_path = folder / (name + ".CHECKSUM")

            record = {
                "family": fam,
                "symbol": sym,
                "period": period,
                "is_monthly": is_monthly,
                "is_reused_from_r10_d1": is_reused,
                "uri": url
            }
            records.append(record)

            if acquire:
                check_meta = fetcher.get(url + ".CHECKSUM", check_path)
                obj_meta = fetcher.get(url, path)
                record.update({"object": obj_meta, "checksum_object": check_meta})
                if obj_meta is None:
                    record["qc"] = "MISSING_OBJECT"
                    terminal = "R11_D2_BINANCE_PILOT_STOP"
                    continue
            else:
                budget.consume(path.stat().st_size)

            qc_res = qc_zip(path, check_path, fam, sym, period, is_monthly, budget)
            record.update(qc_res)
            if record["qc"] not in ("PASS", "PARTIAL_PASS"):
                terminal = "R11_D2_BINANCE_PILOT_STOP"

        # Duplicate verification: Monthly vs Daily klines for January 2024
        duplicate_results = {}
        for sym in SYMBOLS:
            daily_klines = [data / "klines" / f"{sym}-1m-{d}.zip" for d in CALIB_DAYS]
            monthly_kline = data / "klines" / f"{sym}-1m-{CALIB_MONTH}.zip"
            dup_res = compare_daily_vs_monthly(daily_klines, monthly_kline)
            duplicate_results[sym] = dup_res
            if not dup_res["exact_byte_for_byte_rows_identical"]:
                terminal = "R11_D2_BINANCE_PILOT_STOP"

    except SafetyError as exc:
        safety_code = str(exc)
        terminal = "R11_D2_BINANCE_PILOT_STOP"
    except Exception as exc:  # noqa: BLE001
        safety_code = f"LOCAL_EXCEPTION_{type(exc).__name__}"
        terminal = "R11_D2_BINANCE_PILOT_STOP"

    receipt = {
        "task": "R11_D2_BINANCE_CORE_HISTORICAL_DATA_FOUNDATION_PILOT",
        "terminal": terminal,
        "safety_code": safety_code,
        "disk_measurement": disk_measurement,
        "compressed_bytes_consumed": budget.compressed,
        "expanded_bytes": budget.expanded,
        "compressed_cap": budget.compressed_cap,
        "expanded_cap": budget.expanded_cap,
        "total_objects_evaluated": len(records),
        "reused_objects_from_r10_d1": len([r for r in records if r.get("is_reused_from_r10_d1")]),
        "newly_acquired_objects": len([r for r in records if not r.get("is_reused_from_r10_d1")]),
        "request_attempts": fetcher.attempts,
        "daily_monthly_duplicate_parity": duplicate_results if "duplicate_results" in locals() else None,
        "records": records,
        "gates": GATES
    }

    dest = manifest_path if acquire else qc_path
    with dest.open("w") as out:
        json.dump(receipt, out, indent=2, sort_keys=True)
        out.write("\n")

    summary = {
        "terminal": receipt["terminal"],
        "safety_code": receipt["safety_code"],
        "compressed_bytes": receipt["compressed_bytes_consumed"],
        "expanded_bytes": receipt["expanded_bytes"],
        "total_objects": receipt["total_objects_evaluated"],
        "reused_objects": receipt["reused_objects_from_r10_d1"],
        "free_gib": disk_measurement["free_gib"]
    }
    print(json.dumps(summary, indent=2))
    return 0 if terminal.endswith("ACCEPTED_WITH_LIMITS") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("acquire", "verify"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--owner-authorized", required=True, action="store_true")
    args = parser.parse_args()
    return int(execute(args.workspace, args.mode == "acquire"))


if __name__ == "__main__":
    sys.exit(main())
