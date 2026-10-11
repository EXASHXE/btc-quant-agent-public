"""Bounded public USD-M BTC source admission for the two fixed R3 leads.

No I/O is performed at import time. Historical source access is guarded before
any path or URL is formed. Raw bytes remain under this task's private /tmp tree.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import io
import json
import math
import subprocess
import zipfile
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from pathlib import Path

import numpy as np

SCRATCH = Path("/tmp/btc-two-lead-funding-mark-r3")
VISION = "https://data.binance.vision/data/futures/um/monthly/"
FUNDING_API = "https://fapi.binance.com/fapi/v1/fundingRate"
MAX_ZIP_BYTES = 32_000_000
MAX_CSV_BYTES = 40_000_000
MAX_API_BYTES = 1_000_000
KLINE_FIELDS = (
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
)
KLINE_HEADERS = (
    KLINE_FIELDS,
    (*KLINE_FIELDS[:8], "number_of_trades", *KLINE_FIELDS[9:]),
    (*KLINE_FIELDS[:9], "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"),
    (*KLINE_FIELDS[:8], "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"),
)
FUNDING_HEADER = ("calc_time", "funding_interval_hours", "last_funding_rate")


def authorize_month(year: int, month: int) -> None:
    """Call before even stat/list/header requests, including cache checks."""
    if type(year) is not int or type(month) is not int or not (2021 <= year <= 2023 and 1 <= month <= 12):
        raise ValueError("R3 source scope permits only 2021-01 through 2023-12 UTC")


def month_bounds(year: int, month: int) -> tuple[int, int]:
    authorize_month(year, month)
    start = calendar.timegm((year, month, 1, 0, 0, 0)) * 1000
    return start, start + calendar.monthrange(year, month)[1] * 86_400_000


def source_plan(year: int, month: int, kind: str) -> dict:
    authorize_month(year, month)
    if kind not in {"last", "mark", "funding"}:
        raise ValueError("unknown admitted R3 source kind")
    stem = f"BTCUSDT-1m-{year}-{month:02d}" if kind != "funding" else f"BTCUSDT-fundingRate-{year}-{month:02d}"
    segment = "klines/BTCUSDT/1m/" if kind == "last" else (
        "markPriceKlines/BTCUSDT/1m/" if kind == "mark" else "fundingRate/BTCUSDT/"
    )
    url = VISION + segment + stem + ".zip"
    return {"kind": kind, "year": year, "month": month, "zip_name": stem + ".zip",
            "csv_name": stem + ".csv", "zip_url": url, "checksum_url": url + ".CHECKSUM"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _decimal(value: str, label: str, line: int) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid {label} at row {line}") from exc
    if not number.is_finite():
        raise ValueError(f"nonfinite {label} at row {line}")
    return number


def _millis(value: str | int, label: str, line: int) -> int:
    raw = str(value)
    if not raw.isascii() or not raw.isdecimal() or len(raw) != 13:
        raise ValueError(f"invalid millisecond {label} at row {line}")
    return int(raw)


def _archive_csv(raw_zip: bytes, raw_checksum: bytes, plan: dict) -> tuple[bytes, dict]:
    if len(raw_zip) > MAX_ZIP_BYTES:
        raise ValueError("ZIP exceeds admitted byte budget")
    digest = _sha(raw_zip)
    try:
        words = raw_checksum.decode("ascii").strip().split()
    except UnicodeDecodeError as exc:
        raise ValueError("provider CHECKSUM is not ASCII") from exc
    if len(words) != 2 or words[0].lower() != digest or words[1].lstrip("*") != plan["zip_name"]:
        raise ValueError("provider SHA-256 or ZIP basename mismatch")
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != plan["csv_name"] or members[0].is_dir():
            raise ValueError("ZIP member does not match exact admitted CSV basename")
        if members[0].file_size > MAX_CSV_BYTES:
            raise ValueError("CSV exceeds admitted uncompressed budget")
        raw_csv = archive.read(members[0])
    if len(raw_csv) > MAX_CSV_BYTES:
        raise ValueError("CSV exceeds admitted byte budget")
    return raw_csv, {"zip_sha256": digest, "checksum_sha256": _sha(raw_checksum),
                     "csv_sha256": _sha(raw_csv), "csv_bytes": len(raw_csv),
                     "csv_member": plan["csv_name"]}


def validate_kline_archive_bytes(raw_zip: bytes, raw_checksum: bytes, year: int, month: int, *, kind: str) -> tuple[np.ndarray, dict]:
    """Return Nx7 last (time,O,H,L,C,V,buy) or Nx5 mark (time,O,H,L,C)."""
    plan = source_plan(year, month, kind)
    if kind not in {"last", "mark"}:
        raise ValueError("kline kind must be last or mark")
    raw_csv, receipt = _archive_csv(raw_zip, raw_checksum, plan)
    try:
        text = raw_csv.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("non-UTF-8 kline CSV") from exc
    first_ms, end_ms = month_bounds(year, month)
    expected = (end_ms - first_ms) // 60_000
    rows: list[tuple[float, ...]] = []
    header: tuple[str, ...] | None = None
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    for line, row in enumerate(reader, 1):
        if len(row) != 12:
            raise ValueError(f"expected twelve {kind} fields at row {line}")
        if line == 1 and (not row[0].isascii() or not row[0].isdecimal()):
            mark_header = ("open_time", "open", "high", "low", "close", "ignore", "close_time", "ignore", "ignore", "ignore", "ignore", "ignore")
            if tuple(row) not in KLINE_HEADERS and not (kind == "mark" and tuple(row) == mark_header):
                raise ValueError("unrecognized or reordered 12-field kline header")
            header = tuple(row)
            continue
        if len(rows) >= expected:
            raise ValueError("extra kline minute")
        observed = _millis(row[0], "open_time", line)
        close_ms = _millis(row[6], "close_time", line)
        target = first_ms + len(rows) * 60_000
        if observed != target or close_ms != target + 59_999:
            raise ValueError(f"duplicate/gap/out-of-order/wrong minute close at row {line}: expected_open={target}; observed_open={observed}; observed_close={close_ms}; delta_ms={observed-target}")
        o, h, lo, c = (_decimal(row[i], KLINE_FIELDS[i], line) for i in range(1, 5))
        if not (0 < lo <= min(o, c) <= max(o, c) <= h):
            raise ValueError(f"invalid {kind} OHLC at row {line}")
        if kind == "last":
            volume = _decimal(row[5], "volume", line)
            quote = _decimal(row[7], "quote_volume", line)
            count = _decimal(row[8], "count", line)
            buy = _decimal(row[9], "taker_buy_volume", line)
            buy_quote = _decimal(row[10], "taker_buy_quote_volume", line)
            _decimal(row[11], "ignore", line)
            if not (volume >= 0 and quote >= 0 and count >= 0 and count == count.to_integral_value()
                    and 0 <= buy <= volume and 0 <= buy_quote <= quote):
                raise ValueError(f"invalid last-trade volume/flow at row {line}")
            values = (float(observed), float(o), float(h), float(lo), float(c), float(volume), float(buy))
        else:
            # Mark prices are not flow bars; ignored API/CSV columns are not interpreted as volume.
            values = (float(observed), float(o), float(h), float(lo), float(c))
        if not all(math.isfinite(x) for x in values):
            raise ValueError(f"unrepresentable {kind} numeric at row {line}")
        rows.append(values)
    if len(rows) != expected:
        raise ValueError(f"incomplete {kind} minute month: {len(rows)} of {expected}")
    receipt.update({"kind": kind, "source_url": plan["zip_url"], "header": header,
                    "rows": expected, "first_open_ms": first_ms, "last_close_ms": end_ms - 1,
                    "gaps": 0, "duplicates": 0, "source_identity": "BINANCE_USDM_LAST_TRADE" if kind == "last" else "BINANCE_USDM_MARK_PRICE"})
    return np.asarray(rows, dtype=np.float64), receipt


def _funding_event(stamp: str | int, rate: str, interval: str | None, line: int) -> dict:
    when = _millis(stamp, "fundingTime/calc_time", line)
    number = _decimal(rate, "signed funding fraction", line)
    if abs(number) >= 1:
        raise ValueError("funding rate outside fractional unit range")
    hours = None
    if interval is not None:
        parsed = _decimal(interval, "funding_interval_hours", line)
        if parsed <= 0 or parsed > 24:
            raise ValueError("invalid observed funding interval")
        hours = str(parsed)
    return {"settlement_at": when, "rate": str(number), "interval_hours": hours, "mark_price": None}


def validate_funding_archive_bytes(raw_zip: bytes, raw_checksum: bytes, year: int, month: int) -> tuple[list[dict], dict]:
    plan = source_plan(year, month, "funding")
    raw_csv, receipt = _archive_csv(raw_zip, raw_checksum, plan)
    try:
        text = raw_csv.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("non-UTF-8 funding CSV") from exc
    start, end = month_bounds(year, month)
    events: list[dict] = []
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    for line, row in enumerate(reader, 1):
        if line == 1 and tuple(row) == FUNDING_HEADER:
            continue
        if len(row) != 3:
            raise ValueError("unsupported funding archive schema")
        event = _funding_event(row[0], row[2], row[1], line)
        stamp = event["settlement_at"]
        if not (start <= stamp < end):
            raise ValueError("funding settlement outside admitted month")
        if events and stamp <= events[-1]["settlement_at"]:
            raise ValueError("funding archive has duplicate or unordered settlement")
        events.append(event)
    if not events:
        raise ValueError("empty funding archive cannot prove zero funding")
    receipt.update({"kind": "funding", "source_url": plan["zip_url"], "header": list(FUNDING_HEADER),
                    "rows": len(events), "first_settlement_ms": events[0]["settlement_at"],
                    "last_settlement_ms": events[-1]["settlement_at"], "source_identity": "BINANCE_USDM_FUNDING_ARCHIVE",
                    "publication_at_historical": "UNKNOWN_CURRENT_ARCHIVE_IS_RETROSPECTIVE"})
    return events, receipt


def parse_funding_api_pages(pages: list[tuple[int, int, bytes]], year: int, month: int) -> tuple[list[dict], dict]:
    """Validate strict bounded pages: (requested_start_ms, requested_end_inclusive, raw JSON)."""
    start, end = month_bounds(year, month)
    cursor = start
    events: list[dict] = []
    page_receipts = []
    for index, (requested_start, requested_end, raw) in enumerate(pages):
        if requested_start != cursor or requested_end != end - 1:
            raise ValueError("API page does not continue exact bounded cursor")
        if len(raw) > MAX_API_BYTES:
            raise ValueError("API page exceeds byte budget")
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("malformed funding API response") from exc
        if not isinstance(payload, list) or not payload or len(payload) > 1000:
            raise ValueError("empty/error/oversized funding API page")
        last = cursor - 1
        for item in payload:
            if (not isinstance(item, dict) or not {"symbol", "fundingTime", "fundingRate", "markPrice"} <= set(item)
                    or set(item) - {"symbol", "fundingTime", "fundingRate", "markPrice", "rateType"}
                    or item.get("rateType", "Regular") != "Regular"):
                raise ValueError("unsupported funding API record schema")
            if item["symbol"] != "BTCUSDT":
                raise ValueError("foreign funding symbol")
            event = _funding_event(item["fundingTime"], item["fundingRate"], None, index + 1)
            when = event["settlement_at"]
            mark = _decimal(str(item["markPrice"]), "funding API markPrice", index + 1)
            if mark <= 0:
                raise ValueError("invalid funding API markPrice")
            if not (cursor <= when < end) or when <= last:
                raise ValueError("API funding page has out-of-scope/duplicate/unordered stamp")
            event["mark_price"] = str(mark)
            event["mark_price_source_proven"] = True
            events.append(event)
            last = when
        page_receipts.append({"requested_start_ms": requested_start, "requested_end_ms": requested_end,
                              "raw_sha256": _sha(raw), "count": len(payload), "last_settlement_ms": last})
        cursor = last + 1
        if len(payload) < 1000:
            break
    else:
        raise ValueError("API pagination ended without proving final page")
    if not events or page_receipts[-1]["count"] == 1000:
        raise ValueError("API funding coverage is incomplete")
    return events, {"kind": "funding", "source_identity": "BINANCE_USDM_FUNDING_API",
                    "source_url": FUNDING_API, "pages": page_receipts, "rows": len(events),
                    "first_settlement_ms": events[0]["settlement_at"],
                    "last_settlement_ms": events[-1]["settlement_at"],
                    "publication_at_historical": "UNKNOWN_ENDPOINT_HISTORY_IS_RETROSPECTIVE"}


def verify_funding_continuity(events: list[dict], year: int, month: int, *, previous: dict | None = None,
                              following: dict | None = None) -> dict:
    """Require observed interval metadata or bracketing settlements, never infer 8h."""
    start, end = month_bounds(year, month)
    if not events:
        raise ValueError("no observed funding settlements")
    times = [e["settlement_at"] for e in events]
    if times != sorted(set(times)) or not all(start <= t < end for t in times):
        raise ValueError("funding event order/month mismatch")
    if all(e.get("interval_hours") is not None for e in events):
        for left, right in pairwise(events):
            elapsed = (right["settlement_at"] - left["settlement_at"]) / 3_600_000
            if abs(elapsed - float(Decimal(str(right["interval_hours"])))) > 60/3600:
                raise ValueError("funding interval metadata contradicts settlement chronology")
        first_hours = Decimal(str(events[0]["interval_hours"]))
        if events[0]["settlement_at"] - int(first_hours * 3_600_000) > start + 60000:
            raise ValueError("unproved missing early-month funding settlement")
        last_hours = Decimal(str(events[-1]["interval_hours"]))
        if events[-1]["settlement_at"] + int(last_hours * 3_600_000) < end - 60000:
            raise ValueError("unproved missing late-month funding settlement")
        method = "OBSERVED_ARCHIVE_INTERVAL_METADATA"
    elif all(e.get("api_exhausted_bounded_query", False) for e in events):
        observed_days = {(e["settlement_at"] - start) // 86400000 for e in events}
        expected_days = set(range((end-start)//86400000))
        if observed_days != expected_days:
            raise ValueError("API no-event UTC day is UNKNOWN, not zero funding")
        method = "OFFICIAL_EXHAUSTED_BOUNDED_QUERY_ALL_UTC_DAYS_OBSERVED;NO_ASSUMED_CADENCE"
    else:
        raise ValueError("funding interval and boundary coverage unproven")
    return {"coverage": "PROVEN_BY_OBSERVED_INTERVALS", "method": method,
            "rows": len(events), "first_settlement_ms": times[0], "last_settlement_ms": times[-1]}


def _fetch(url: str, dest: Path, *, max_bytes: int, allowed_prefix: str) -> dict:
    if not url.startswith(allowed_prefix) or dest.parent != SCRATCH:
        raise ValueError("source URL or destination outside admitted R3 route")
    if dest.is_symlink():
        raise ValueError("symlinked source cache is inadmissible")
    part = dest.with_suffix(dest.suffix + ".partial")
    headers = dest.with_suffix(dest.suffix + ".headers")
    if part.is_symlink() or headers.is_symlink():
        raise ValueError("symlinked download sidecar is inadmissible")
    command = ["curl", "--silent", "--show-error", "--max-redirs", "0", "--proto", "=https",
               "--connect-timeout", "20", "--max-time", "120", "--retry", "2", "--max-filesize", str(max_bytes),
               "--dump-header", str(headers), "--output", str(part),
               "--write-out", "%{http_code}\n%{url_effective}\n%{http_version}", url]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    output = result.stdout.splitlines()
    status = int(output[0]) if output and output[0].isascii() and output[0].isdecimal() else 0
    effective = output[1] if len(output) > 1 else ""
    receipt = {"requested_url": url, "returned_url": effective, "http_status": status,
               "http_version": output[2] if len(output) > 2 else None, "curl_exit": result.returncode,
               "response_headers": headers.read_text(errors="replace") if headers.exists() else "",
               "fetched_at_utc": datetime.now(UTC).isoformat(),
               "stderr": result.stderr[:500] if result.returncode else None}
    if result.returncode or status != 200 or not effective.startswith(allowed_prefix):
        part.unlink(missing_ok=True)
        receipt["status"] = "FETCH_FAILED"
        return receipt
    part.replace(dest)
    receipt["status"] = "FETCHED"
    receipt["raw_sha256"] = _sha(dest.read_bytes())
    return receipt


def load_month(year: int, month: int, kind: str, *, allow_download: bool = False) -> tuple[np.ndarray, dict]:
    plan = source_plan(year, month, kind)
    if kind not in {"last", "mark"}:
        raise ValueError("load_month requires last or mark")
    if SCRATCH.is_symlink():
        raise ValueError("symlinked task scratch is inadmissible")
    SCRATCH.mkdir(mode=0o700, exist_ok=True) if allow_download else None
    local = SCRATCH / (kind + "-" + plan["zip_name"])
    check = SCRATCH / (kind + "-" + plan["zip_name"] + ".CHECKSUM")
    downloads = {}
    for label, path, url, budget in (("zip", local, plan["zip_url"], MAX_ZIP_BYTES),
                                     ("checksum", check, plan["checksum_url"], 4096)):
        if path.is_symlink():
            raise ValueError("symlinked source cache is inadmissible")
        if path.exists():
            downloads[label] = {"status": "EXISTING_TASK_SCRATCH", "requested_url": url}
        elif allow_download:
            downloads[label] = _fetch(url, path, max_bytes=budget, allowed_prefix=VISION)
            if downloads[label]["status"] != "FETCHED":
                raise ValueError(f"source {kind} {year}-{month:02d} {label} unavailable: {downloads[label]}")
        else:
            raise FileNotFoundError(path)
    data, receipt = validate_kline_archive_bytes(local.read_bytes(), check.read_bytes(), year, month, kind=kind)
    receipt["downloads"] = downloads
    return data, receipt


def load_funding_month(year: int, month: int, *, allow_download: bool = False) -> tuple[list[dict], dict]:
    """Prefer verified archive; fallback only after explicit provider 404."""
    plan = source_plan(year, month, "funding")
    if SCRATCH.is_symlink():
        raise ValueError("symlinked task scratch is inadmissible")
    SCRATCH.mkdir(mode=0o700, exist_ok=True) if allow_download else None
    local = SCRATCH / ("funding-" + plan["zip_name"])
    check = SCRATCH / ("funding-" + plan["zip_name"] + ".CHECKSUM")
    downloads = {}
    for label, path, url, budget in (("zip", local, plan["zip_url"], MAX_ZIP_BYTES),
                                     ("checksum", check, plan["checksum_url"], 4096)):
        if path.is_symlink():
            raise ValueError("symlinked source cache is inadmissible")
        if path.exists():
            downloads[label] = {"status": "EXISTING_TASK_SCRATCH", "requested_url": url}
        elif allow_download:
            downloads[label] = _fetch(url, path, max_bytes=budget, allowed_prefix=VISION)
            if downloads[label]["status"] != "FETCHED":
                if downloads[label]["http_status"] == 404:
                    return load_funding_api_month(year, month, allow_download=True, archive_404=downloads)
                raise ValueError(f"funding archive {year}-{month:02d} {label} unavailable: {downloads[label]}")
        else:
            raise FileNotFoundError(path)
    events, receipt = validate_funding_archive_bytes(local.read_bytes(), check.read_bytes(), year, month)
    receipt["downloads"] = downloads
    return events, receipt


def load_funding_api_month(year: int, month: int, *, allow_download: bool = False,
                           archive_404: dict | None = None) -> tuple[list[dict], dict]:
    """Public API route only after observed archive 404; no protected-month query."""
    start, end = month_bounds(year, month)
    if archive_404 is None or not any(item.get("http_status") == 404 for item in archive_404.values()):
        raise ValueError("API fallback requires recorded official archive HTTP 404")
    if not allow_download:
        raise ValueError("API fallback download is disabled")
    if SCRATCH.is_symlink():
        raise ValueError("symlinked task scratch is inadmissible")
    SCRATCH.mkdir(mode=0o700, exist_ok=True)
    pages: list[tuple[int, int, bytes]] = []
    requests: list[dict] = []
    cursor = start
    for index in range(16):  # 16,000 records far above any observed monthly cadence.
        if cursor >= end:
            raise ValueError("No pagination request beyond admitted month endpoint")
        url = (f"{FUNDING_API}?symbol=BTCUSDT&startTime={cursor}&endTime={end-1}&limit=1000")
        dest = SCRATCH / f"funding-api-{year}-{month:02d}-page-{index:02d}.json"
        response = _fetch(url, dest, max_bytes=MAX_API_BYTES, allowed_prefix=FUNDING_API + "?")
        requests.append(response)
        if response["status"] != "FETCHED":
            raise ValueError(f"funding API page unavailable: {response}")
        raw = dest.read_bytes()
        pages.append((cursor, end - 1, raw))
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("malformed funding API response") from exc
        if not isinstance(payload, list) or not payload or len(payload) > 1000:
            raise ValueError("empty/error/oversized funding API page")
        last = _millis(payload[-1].get("fundingTime"), "fundingTime", index + 1)
        if len(payload) < 1000:
            break
        if last < cursor or last >= end:
            raise ValueError("funding API cursor outside requested month")
        cursor = last + 1
    else:
        raise ValueError("funding API exceeded bounded monthly page count")
    events, receipt = parse_funding_api_pages(pages, year, month)
    receipt["requests"] = requests
    receipt["archive_404"] = archive_404
    for event in events:
        event["api_exhausted_bounded_query"] = True
    receipt["coverage_status"] = verify_funding_continuity(events, year, month)
    return events, receipt
