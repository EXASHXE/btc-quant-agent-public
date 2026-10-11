"""Frozen eight-day BTCUSDT USD-M Mark gap source route.

No market I/O at import. Daily Vision ZIP with its provider checksum precedes
the bounded public API, which is used only for minutes absent from that ZIP.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3 import sources as r3

ALLOWED_DAYS = (
    "2021-07-01", "2021-07-24", "2021-07-25", "2021-07-26",
    "2021-07-27", "2022-07-31", "2022-10-02", "2023-02-24",
)
SCRATCH = Path("/tmp/btc-two-lead-mark-gap-r31")
VISION = "https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/"
API = "https://fapi.binance.com/fapi/v1/markPriceKlines"
DAY_MS = 86_400_000
MINUTE_MS = 60_000
MAX_ZIP_BYTES = 4_000_000
MAX_CSV_BYTES = 6_000_000
MAX_API_BYTES = 1_000_000
API_LIMIT = 1440
ABS_TOL = 1e-8
REL_TOL = 1e-12


def day_plan(day: str) -> dict:
    """Scope guard MUST precede path, network or date-derived URL construction."""
    if type(day) is not str or day not in ALLOWED_DAYS:
        raise ValueError("R3.1 admits exactly eight frozen 2021-23 Mark UTC days")
    start = int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)
    stem = f"BTCUSDT-1m-{day}"
    url = VISION + stem + ".zip"
    return {"day": day, "start_ms": start, "end_ms": start + DAY_MS,
            "zip_name": stem + ".zip", "csv_name": stem + ".csv",
            "zip_url": url, "checksum_url": url + ".CHECKSUM"}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _integer_ms(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"invalid {label}")
    raw = str(value)
    if len(raw) != 13 or not raw.isascii() or not raw.isdecimal():
        raise ValueError(f"invalid {label}")
    return int(raw)


def _price(value: object, label: str) -> float:
    try:
        dec = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid {label}") from exc
    if not dec.is_finite() or dec <= 0:
        raise ValueError(f"invalid {label}")
    out = float(dec)
    if not math.isfinite(out) or out <= 0:
        raise ValueError(f"unrepresentable {label}")
    return out


def _bar(fields: list | tuple, start: int, end: int) -> tuple[float, ...]:
    if len(fields) != 12:
        raise ValueError("Mark kline must contain twelve fields")
    stamp = _integer_ms(fields[0], "open_time")
    close = _integer_ms(fields[6], "close_time")
    if not (start <= stamp < end and (stamp - start) % MINUTE_MS == 0
            and close == stamp + MINUTE_MS - 1):
        raise ValueError("Mark minute clock or close-time invalid")
    o, h, lo, c = (_price(fields[i], f"OHLC[{i}]") for i in range(1, 5))
    if not (lo <= min(o, c) <= max(o, c) <= h):
        raise ValueError("Mark OHLC envelope invalid")
    return float(stamp), o, h, lo, c


def _array(rows: list[tuple[float, ...]]) -> np.ndarray:
    return np.asarray(rows, dtype=np.float64).reshape((-1, 5))


def parse_daily(raw_zip: bytes, raw_checksum: bytes, day: str) -> tuple[np.ndarray, dict]:
    """A checksum-authenticated daily archive may be sparse, but never reordered."""
    plan = day_plan(day)
    if len(raw_zip) > MAX_ZIP_BYTES:
        raise ValueError("daily ZIP byte budget exceeded")
    digest = _sha(raw_zip)
    try:
        words = raw_checksum.decode("ascii").strip().split()
    except UnicodeDecodeError as exc:
        raise ValueError("non-ASCII daily CHECKSUM") from exc
    if len(words) != 2 or words[0].lower() != digest or words[1].lstrip("*") != plan["zip_name"]:
        raise ValueError("daily ZIP/CHECKSUM mismatch")
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
        members = archive.infolist()
        if len(members) != 1 or members[0].filename != plan["csv_name"] or members[0].is_dir():
            raise ValueError("daily ZIP member mismatch")
        if members[0].file_size > MAX_CSV_BYTES:
            raise ValueError("daily CSV byte budget exceeded")
        raw_csv = archive.read(members[0])
    if len(raw_csv) > MAX_CSV_BYTES:
        raise ValueError("daily CSV byte budget exceeded")
    try:
        content = raw_csv.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("daily CSV is not UTF-8") from exc
    rows = []
    previous = plan["start_ms"] - MINUTE_MS
    header = None
    for line, fields in enumerate(csv.reader(io.StringIO(content, newline=""), strict=True), 1):
        if line == 1 and fields and fields[0] == "open_time":
            if tuple(fields) not in r3.KLINE_HEADERS and tuple(fields) != (
                "open_time", "open", "high", "low", "close", "ignore", "close_time",
                "ignore", "ignore", "ignore", "ignore", "ignore",
            ):
                raise ValueError("unrecognized daily Mark header")
            header = fields
            continue
        row = _bar(fields, plan["start_ms"], plan["end_ms"])
        stamp = int(row[0])
        if stamp <= previous:
            raise ValueError(f"daily duplicate/out-of-order minute at row {line}")
        rows.append(row)
        previous = stamp
    result = _array(rows)
    return result, {
        "provenance": "PROVIDER_DAILY_ZIP_SHA256_AUTHENTICATED",
        "zip_sha256": digest, "checksum_sha256": _sha(raw_checksum),
        "csv_sha256": _sha(raw_csv), "csv_bytes": len(raw_csv), "rows": len(rows),
        "header": header, "source_url": plan["zip_url"],
        "missing_minutes": 1440 - len(rows),
    }


def parse_api(raw: bytes, day: str, start_ms: int, end_ms: int) -> tuple[np.ndarray, dict]:
    """Parse one exact missing subrange; response rows cannot exceed request."""
    plan = day_plan(day)
    if not (plan["start_ms"] <= start_ms < end_ms <= plan["end_ms"]
            and start_ms % MINUTE_MS == 0 and end_ms % MINUTE_MS == 0
            and (end_ms - start_ms) // MINUTE_MS <= API_LIMIT):
        raise ValueError("API request is outside frozen day or limit")
    if len(raw) > MAX_API_BYTES:
        raise ValueError("API response byte budget exceeded")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid Mark API JSON") from exc
    if not isinstance(payload, list) or len(payload) > (end_ms - start_ms) // MINUTE_MS:
        raise ValueError("Mark API response shape/count invalid")
    rows = []
    previous = start_ms - MINUTE_MS
    for fields in payload:
        if not isinstance(fields, list):
            raise TypeError("Mark API kline is not array")
        row = _bar(fields, start_ms, end_ms)
        stamp = int(row[0])
        if stamp <= previous:
            raise ValueError("Mark API duplicate/out-of-order minute")
        rows.append(row)
        previous = stamp
    return _array(rows), {"provenance": "PROVIDER_API_SECONDARY_NOT_ZIP_AUTHENTICATED",
                          "raw_sha256": _sha(raw), "rows": len(rows),
                          "first_open_ms": int(rows[0][0]) if rows else None,
                          "last_open_ms": int(rows[-1][0]) if rows else None}


def missing_ranges(rows: np.ndarray, day: str) -> list[dict]:
    plan = day_plan(day)
    observed = set(map(int, rows[:, 0]))
    if len(observed) != len(rows) or not all(
        plan["start_ms"] <= x < plan["end_ms"] and (x - plan["start_ms"]) % MINUTE_MS == 0
        for x in observed
    ):
        raise ValueError("rows not unique/frozen-day aligned")
    absent = [plan["start_ms"] + i * MINUTE_MS for i in range(1440)
              if plan["start_ms"] + i * MINUTE_MS not in observed]
    ranges = []
    for stamp in absent:
        if ranges and ranges[-1]["end_exclusive_ms"] == stamp:
            ranges[-1]["end_exclusive_ms"] += MINUTE_MS
            ranges[-1]["minutes"] += 1
        else:
            ranges.append({"start_ms": stamp, "end_exclusive_ms": stamp + MINUTE_MS,
                           "minutes": 1})
    return ranges


def compare_overlap(existing: np.ndarray, replacement: np.ndarray) -> dict:
    """Fail closed on material cross-source disagreement; existing never changes."""
    known = {int(row[0]): row for row in existing}
    count = 0
    for row in replacement:
        old = known.get(int(row[0]))
        if old is not None:
            if not all(math.isclose(float(a), float(b), rel_tol=REL_TOL, abs_tol=ABS_TOL)
                       for a, b in zip(old[1:], row[1:], strict=True)):
                raise ValueError(f"monthly/daily/API Mark overlap conflicts at {int(row[0])}")
            count += 1
    return {"overlap_rows": count, "tolerance_abs": ABS_TOL, "tolerance_rel": REL_TOL,
            "provenance_when_no_overlap": "LOWER_NO_DIRECT_CROSS_SOURCE_MATCH" if count == 0
            else "CROSS_SOURCE_AGREEMENT_OBSERVED"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect outside frozen exact request", headers, fp)


def _guard_cache_path(path: Path) -> None:
    if SCRATCH not in path.parents:
        raise ValueError("cache path outside task-owned scratch")
    for part in [SCRATCH, *reversed([p for p in path.parents if SCRATCH in p.parents]), path]:
        if part.is_symlink():
            raise ValueError("symlinked task cache is inadmissible")


def _fetch(url: str, dest: Path, *, max_bytes: int, allowed_host: str) -> dict:
    """Bounded HTTPS GET, preserving failure status and never accepting redirects elsewhere."""
    _guard_cache_path(dest)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != allowed_host:
        raise ValueError("source URL host/scheme outside frozen contract")
    attempts = []
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "r31-mark-gap-research/1"})
            with urllib.request.build_opener(_NoRedirect()).open(req, timeout=25) as response:
                final_url = response.geturl()
                final = urllib.parse.urlsplit(final_url)
                if (final.scheme != "https" or final.netloc != allowed_host
                        or final.path != parsed.path or final.query != parsed.query):
                    raise ValueError("source redirected outside exact admitted URL")
                status = response.status
                content_type = response.headers.get("Content-Type", "")
                raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError("source byte budget exceeded")
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            dest.write_bytes(raw)
            return {"requested_url": url, "returned_url": final_url, "status": status,
                    "content_type": content_type, "bytes": len(raw), "sha256": _sha(raw),
                    "attempts": attempts + [{"status": status}]}
        except urllib.error.HTTPError as exc:
            failure_body = exc.read(min(max_bytes, 4096) + 1)
            attempts.append({
                "status": exc.code, "reason": str(exc.reason),
                "content_type": exc.headers.get("Content-Type", ""),
                "response_sha256": _sha(failure_body),
                "response_bytes_read": len(failure_body),
                "response_body_truncated": len(failure_body) > min(max_bytes, 4096),
            })
            if exc.code == 404:
                return {"requested_url": url, "status": 404, "attempts": attempts,
                        "source_status": "UNAVAILABLE_404"}
            if exc.code not in {429, 500, 502, 503, 504}:
                break
        except (urllib.error.URLError, TimeoutError) as exc:
            attempts.append({"transport_error": type(exc).__name__, "reason": str(exc)})
        if attempt < 2:
            time.sleep(min(2 ** attempt, 2))
    return {"requested_url": url, "attempts": attempts, "source_status": "UNKNOWN_FETCH_FAILED"}


def _load(url: str, path: Path, *, allow_download: bool, max_bytes: int,
          allowed_host: str) -> tuple[bytes | None, dict]:
    _guard_cache_path(path)
    if path.is_file():
        raw = path.read_bytes()
        if len(raw) > max_bytes:
            raise ValueError("cached source byte budget exceeded")
        return raw, {"requested_url": url, "cache": True, "bytes": len(raw), "sha256": _sha(raw)}
    if not allow_download:
        return None, {"requested_url": url, "source_status": "CACHE_ABSENT_DOWNLOAD_DISABLED"}
    result = _fetch(url, path, max_bytes=max_bytes, allowed_host=allowed_host)
    if result.get("status") == 200:
        return path.read_bytes(), result
    return None, result


def gather_day(day: str, *, allow_download: bool = False) -> tuple[np.ndarray, dict]:
    """Return exact-day Mark observations and all route/failure receipts.

    Any structurally invalid authenticated source raises ValueError. Missing
    source responses leave explicit unresolved minute ranges for partial science.
    """
    plan = day_plan(day)
    folder = SCRATCH / day
    zip_path = folder / plan["zip_name"]
    check_path = folder / (plan["zip_name"] + ".CHECKSUM")
    raw_zip, zip_fetch = _load(plan["zip_url"], zip_path, allow_download=allow_download,
                               max_bytes=MAX_ZIP_BYTES, allowed_host="data.binance.vision")
    raw_check, check_fetch = _load(plan["checksum_url"], check_path, allow_download=allow_download,
                                   max_bytes=512, allowed_host="data.binance.vision")
    receipt = {"day": day, "daily_fetch": {"zip": zip_fetch, "checksum": check_fetch},
               "daily_parse": None, "api_requests": []}
    if raw_zip is not None and raw_check is not None:
        daily, receipt["daily_parse"] = parse_daily(raw_zip, raw_check, day)
    else:
        daily = _array([])
        receipt["daily_status"] = "SOURCE_UNAVAILABLE_OR_INCOMPLETE_PAIR"
    observed = {int(row[0]): row for row in daily}
    provenance = {stamp: "PROVIDER_DAILY_ZIP_SHA256_AUTHENTICATED" for stamp in observed}
    for interval in missing_ranges(daily, day):
        # An eight-day scope means every range is at most 1440 minutes.
        start = interval["start_ms"]
        end = interval["end_exclusive_ms"]
        while start < end:
            page_end = min(start + API_LIMIT * MINUTE_MS, end)
            params = urllib.parse.urlencode({
                "symbol": "BTCUSDT", "interval": "1m",
                "startTime": start, "endTime": page_end - 1, "limit": API_LIMIT,
            })
            url = API + "?" + params
            path = folder / f"api-{start}-{page_end}.json"
            raw, fetch = _load(url, path, allow_download=allow_download,
                               max_bytes=MAX_API_BYTES, allowed_host="fapi.binance.com")
            page_receipt = {"start_ms": start, "end_exclusive_ms": page_end, "fetch": fetch}
            if raw is not None:
                rows, parsed = parse_api(raw, day, start, page_end)
                page_receipt["parse"] = parsed
                for row in rows:
                    stamp = int(row[0])
                    if stamp in observed:
                        compare_overlap(_array([tuple(observed[stamp])]), _array([tuple(row)]))
                    else:
                        observed[stamp] = row
                        provenance[stamp] = "PROVIDER_API_SECONDARY_NOT_ZIP_AUTHENTICATED"
            receipt["api_requests"].append(page_receipt)
            start = page_end
    result = _array([tuple(observed[t]) for t in sorted(observed)])
    receipt["rows"] = len(result)
    receipt["unresolved_ranges"] = missing_ranges(result, day)
    receipt["provenance_counts"] = {name: sum(v == name for v in provenance.values())
                                     for name in sorted(set(provenance.values()))}
    receipt["source_spans"] = [
        {"open_ms": stamp, "provenance": provenance[stamp]} for stamp in sorted(provenance)
    ]
    return result, receipt


def compose_gap_month(monthly: np.ndarray, added: list[np.ndarray], year: int,
                      month: int) -> tuple[np.ndarray, dict]:
    """Monthly rows stay authoritative; only frozen missing minutes may be added."""
    start, end = r3.month_bounds(year, month)
    known = {int(row[0]): row for row in monthly}
    if len(known) != len(monthly):
        raise ValueError("monthly Mark duplicate minute")
    monthly_stamps = set(known)
    additions = 0
    for array in added:
        compare_overlap(monthly, array)
        for row in array:
            stamp = int(row[0])
            if stamp not in known:
                if not (start <= stamp < end and
                        datetime.fromtimestamp(stamp / 1000, tz=UTC).date().isoformat()
                        in ALLOWED_DAYS):
                    raise ValueError("added Mark minute outside frozen gap day/month")
                known[stamp] = row
                additions += 1
            elif stamp not in monthly_stamps:
                raise ValueError(f"duplicate replacement Mark minute at {stamp}")
    result = _array([tuple(known[t]) for t in sorted(known)])
    expected = (end - start) // MINUTE_MS
    dense = len(result) == expected and np.array_equal(
        result[:, 0], np.arange(start, end, MINUTE_MS, dtype=np.float64))
    return result, {"monthly_rows": len(monthly), "added_rows": additions,
                    "expected_rows": expected, "observed_rows": len(result), "dense": bool(dense),
                    "composite_sha256": _sha(result.astype("<f8", copy=False).tobytes())}
