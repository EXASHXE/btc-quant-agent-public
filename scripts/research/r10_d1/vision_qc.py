"""Frozen R10-D1 acquisition/QC. Python stdlib only; never print source rows."""
from __future__ import annotations

import argparse
import csv
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
from datetime import date, datetime, timedelta, UTC
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

ORIGIN = "https://data.binance.vision"
DAYS = tuple((date(2022, 9, 15) + timedelta(days=i)).isoformat() for i in range(7))
FAMILIES = ("klines", "markPriceKlines", "metrics")
COMPRESSED_CAP = 100 * 1024**2
EXPANDED_CAP = 300 * 1024**2
TERMS_BLOB = "87d04e216f62c86a2c797fbb7637404d6d602687"
METRICS = ["create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
           "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
           "count_long_short_ratio", "sum_taker_long_short_vol_ratio"]
BARS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
ALIASES = {"quote_asset_volume": "quote_volume", "number_of_trades": "count",
           "taker_buy_base_asset_volume": "taker_buy_volume",
           "taker_buy_quote_asset_volume": "taker_buy_quote_volume"}
GATES = ("R9_L1_PAUSE_NEW_ALPHA_RESEARCH_PENDING_EXTERNAL_SOURCE_EVIDENCE / "
         "SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / "
         "G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE")


class SafetyError(Exception):
    """Only sanitized constant reason codes may leave the local process."""


def require(ok, code):
    if not ok:
        raise SafetyError(code)


def object_url(family, day):
    require(family in FAMILIES and day in DAYS, "SOURCE_SCOPE")
    prefix = f"{ORIGIN}/data/futures/um/daily/{family}/BTCUSDT/"
    name = f"BTCUSDT-metrics-{day}.zip" if family == "metrics" else f"BTCUSDT-1m-{day}.zip"
    return prefix + ("" if family == "metrics" else "1m/") + name


def validate_url(url):
    parts = urlsplit(url)
    allowed = {object_url(f, d) + suffix for f in FAMILIES for d in DAYS
               for suffix in ("", ".CHECKSUM")}
    require(parts.scheme == "https" and parts.netloc == "data.binance.vision"
            and not parts.query and not parts.fragment and url in allowed, "SOURCE_SCOPE")
    return url


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Reject even same-origin redirects: only the frozen exact objects are needed.
        raise SafetyError("REDIRECT_REFUSED")


class Budget:
    def __init__(self, compressed=COMPRESSED_CAP, expanded=EXPANDED_CAP):
        require(0 < compressed <= COMPRESSED_CAP and 0 < expanded <= EXPANDED_CAP,
                "BUDGET_CONFIGURATION")
        self.compressed_cap = compressed
        self.expanded_cap = expanded
        self.compressed = 0  # Includes discarded partial/retried ZIP response bytes.
        self.expanded = 0
        self.zip_urls = set()
        self.checksum_urls = set()

    def register(self, url):
        validate_url(url)
        urls = self.checksum_urls if url.endswith(".CHECKSUM") else self.zip_urls
        require(url not in urls, "OBJECT_ALREADY_REQUESTED")
        require(len(urls) < 21, "OBJECT_BUDGET")
        urls.add(url)

    def consume(self, n):
        require(0 <= n <= self.compressed_cap - self.compressed, "COMPRESSED_BUDGET")
        self.compressed += n

    def expand(self, n):
        require(0 <= n <= self.expanded_cap - self.expanded, "EXPANDED_BUDGET")
        self.expanded += n


class Fetcher:
    def __init__(self, budget):
        self.budget = budget
        self.opener = build_opener(NoRedirect())  # Honors configured HTTPS proxy.
        self.attempts = {}

    def get(self, url, path):
        self.budget.register(url)
        checksum = url.endswith(".CHECKSUM")
        require(not path.exists() and not path.is_symlink(), "OUTPUT_EXISTS")
        for attempt in range(3):  # initial request + at most two transient retries
            self.attempts[url] = attempt + 1
            try:
                req = Request(url, headers={"User-Agent": "R10-D1-offline-QC/1",
                                            "Accept-Encoding": "identity"})
                with self.opener.open(req, timeout=30) as response:
                    require(response.status == 200, "HTTP_STATUS")
                    require(response.geturl() == url, "REDIRECT_REFUSED")
                    require(response.headers.get("Content-Encoding", "identity") == "identity",
                            "HTTP_ENCODING")
                    cap = 4096 if checksum else self.budget.compressed_cap - self.budget.compressed
                    length = response.headers.get("Content-Length")
                    if length is not None:
                        require(length.isdigit() and 0 < int(length) <= cap, "HTTP_SIZE_BUDGET")
                    total = 0
                    with path.open("xb") as out:
                        while True:
                            # Never read or persist beyond the remaining source-byte allowance.
                            remaining = 4096 - total if checksum else (
                                self.budget.compressed_cap - self.budget.compressed)
                            require(remaining > 0, "HTTP_SIZE_BUDGET")
                            chunk = response.read(min(65536, remaining))
                            if not chunk:
                                break
                            if not checksum:
                                self.budget.consume(len(chunk))
                            out.write(chunk)
                            total += len(chunk)
                            if length is not None and total == int(length):
                                break
                    require(total > 0 and (length is None or total == int(length)), "HTTP_TRUNCATED")
                    return {"uri": url, "bytes": total, "fetched_at_utc": utc_now(),
                            "last_modified": response.headers.get("Last-Modified"),
                            "etag": response.headers.get("ETag"), "attempts": attempt + 1}
            except IncompleteRead as exc:
                if not checksum:
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


def utc_now():
    return datetime.now(UTC).isoformat()


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat()


def day_ms(day):
    require(day in DAYS, "SOURCE_DATE")
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)


def verify_checksum(path, checksum_path):
    raw = checksum_path.read_bytes()
    require(len(raw) <= 4096, "CHECKSUM_FORMAT")
    try:
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]([^\r\n]+)\s*", raw.decode("ascii"))
    except UnicodeDecodeError:
        raise SafetyError("CHECKSUM_FORMAT") from None
    require(match is not None and match[2].strip() == path.name, "CHECKSUM_IDENTITY")
    with path.open("rb") as src:
        digest = hashlib.file_digest(src, "sha256").hexdigest()
    require(digest == match[1].lower(), "PUBLISHER_CHECKSUM_MISMATCH")
    return digest


def metric_clock(label, stock_time, flow_start, flow_end):
    require(stock_time == label and flow_end == label and flow_start == label - 300000,
            "STOCK_FLOW_TIME_MISALIGNED")
    return {str(lag): iso(flow_end + lag * 60000) for lag in (5, 10, 15)}


def number(value):
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise SafetyError("NUMERIC_TYPE") from None
    require(result.is_finite() and result >= 0, "NUMERIC_TYPE")
    return result


def integer(value):
    require(re.fullmatch(r"\d+", value) is not None, "INTEGER_TYPE")
    return int(value)


def qc_rows(rows, family, day):
    require(family in FAMILIES and day in DAYS, "SOURCE_SCOPE")
    expected = METRICS if family == "metrics" else BARS
    first = next(rows, None)
    require(first is not None, "EMPTY_CSV")
    require(len(first) == len(expected), "CSV_SHAPE")
    normalized = [ALIASES.get(v, v) for v in first]
    header = not first[0].isdigit() if family != "metrics" else first[0] == "create_time"
    if header:
        require(normalized == expected, "SCHEMA_DRIFT")
        schema = first
    else:
        require(family != "metrics", "METRICS_HEADER_MISSING")
        schema = BARS
        import itertools
        rows = itertools.chain([first], rows)
    labels = []
    start = day_ms(day)
    malformed = 0
    seen = 0
    complete = 0
    missing_fields = {}
    invalid_fields = {}
    for row in rows:
        require(seen < 2000, "CSV_ROW_BUDGET")
        seen += 1
        try:
            require(len(row) == len(expected), "CSV_SHAPE")
            if family == "metrics":
                require(row[1] == "BTCUSDT", "INSTRUMENT")
                dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                label = int(dt.timestamp() * 1000)
                require(start - 300000 <= label <= start + 86400000 + 300000,
                        "SOURCE_TIME_WINDOW")
                labels.append(label)
                bad_fields = False
                for col, v in zip(METRICS[2:], row[2:], strict=True):
                    if not v.strip():
                        missing_fields[col] = missing_fields.get(col, 0) + 1
                        bad_fields = True
                    else:
                        try:
                            number(v)
                        except SafetyError:
                            invalid_fields[col] = invalid_fields.get(col, 0) + 1
                            bad_fields = True
                require(not bad_fields, "METRICS_FIELD_INCOMPLETE")
            else:
                label = integer(row[0])
                require(start - 300000 <= label <= start + 86400000 + 300000,
                        "SOURCE_TIME_WINDOW")
                labels.append(label)
                require(integer(row[6]) == label + 59999, "BAR_CLOSE_TIME")
                integer(row[8])
                vals = {i: number(row[i]) for i in (1, 2, 3, 4, 5, 7, 9, 10, 11)}
                require(0 < vals[3] <= min(vals[1], vals[4])
                        <= max(vals[1], vals[4]) <= vals[2], "OHLC_RELATION")
                require(vals[9] <= vals[5] and vals[10] <= vals[7], "TAKER_VOLUME")
            complete += 1
        except (SafetyError, ValueError, OverflowError):
            malformed += 1
    start = day_ms(day)
    step = 300000 if family == "metrics" else 60000
    # End-labelled metrics is a predeclared candidate, never proof of content timing.
    expected_labels = set(range(start + step, start + 86400001, step)) if family == "metrics" else (
        set(range(start, start + 86400000, step)))
    actual = set(labels)
    errors = []
    duplicates = len(labels) - len(actual)
    missing = len(expected_labels - actual)
    extra = len(actual - expected_labels)
    if malformed:
        errors.append("MALFORMED_ROW")
    if duplicates:
        errors.append("DUPLICATE_TIMESTAMP")
    if missing:
        errors.append("GRID_HOLE")
    if extra:
        errors.append("OFF_GRID_OR_DATE")
    if labels != sorted(labels):
        errors.append("NONMONOTONIC_TIMESTAMP")
    if family == "metrics" and actual == set(range(start, start + 86400000, step)):
        errors.append("SHIFTED_START_VS_END_LABEL")
    observed_holes = (len(set(range(min(labels), max(labels) + 1, step)) - actual)
                      if labels and max(labels)-min(labels) <= 86400000
                      and all((t-min(labels)) % step == 0 for t in labels) else None)
    result = {"schema": schema, "header_present": header, "rows": seen, "valid_rows": complete,
              "timestamp_rows": len(labels), "missing_field_counts": missing_fields,
              "invalid_field_counts": invalid_fields,
              "malformed_rows": malformed, "expected_rows": len(expected_labels),
              "duplicate_timestamps": duplicates, "missing_intervals": missing,
              "observed_internal_grid_holes": observed_holes,
              "unexpected_timestamps": extra,
              "label_min_utc": iso(min(labels)) if labels else None,
              "label_max_utc": iso(max(labels)) if labels else None,
              "errors": errors, "qc": "PASS" if not errors else "FAIL"}
    if family == "metrics" and labels:
        result["time_contract"] = {
            "classification": "OI_STOCK_SNAPSHOT;TAKER_RATIO_INTERVAL_FLOW",
            "candidate_label": "END_OF_PERIOD_UNPROVEN",
            "observed_grid": ("START_GRID" if actual == set(range(start, start + 86400000, step))
                              else "END_GRID" if actual == expected_labels else "IRREGULAR"),
            "true_observation_close": "UNKNOWN", "official_first_publication": "UNKNOWN",
            "original_receiver_first_known": "UNKNOWN", "pit": "PIT_UNKNOWN",
            "end_label_hypothesis": "stock=T;flow=[T-5m,T);assumed_close=T",
            "start_label_hypothesis": "stock=T+5m;flow=[T,T+5m);assumed_close=T+5m",
            "proxy_lags_after_assumed_close_minutes": [5, 10, 15],
            "end_hypothesis_proxy_first_utc": metric_clock(
                min(labels), min(labels), min(labels)-step, min(labels)),
            "end_hypothesis_proxy_last_utc": metric_clock(
                max(labels), max(labels), max(labels)-step, max(labels)),
            # Conservative envelope across BOTH unproven label hypotheses.
            "proxy_first_utc": metric_clock(
                min(labels)+step, min(labels)+step, min(labels), min(labels)+step),
            "proxy_last_utc": metric_clock(
                max(labels)+step, max(labels)+step, max(labels), max(labels)+step),
        }
    return result


def qc_zip(path, checksum_path, family, day, budget):
    digest = verify_checksum(path, checksum_path)
    try:
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            require(len(members) == 1, "ZIP_MEMBER_COUNT")
            m = members[0]
            require(m.filename == path.with_suffix(".csv").name
                    and "/" not in m.filename and "\\" not in m.filename
                    and not stat.S_ISLNK(m.external_attr >> 16) and not m.is_dir()
                    and not m.flag_bits & 1, "ZIP_UNSAFE_MEMBER")
            require(m.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "ZIP_COMPRESSION")
            require(m.file_size > 0 and m.file_size <= max(m.compress_size, 1) * 200,
                    "ZIP_EXPANSION_RATIO")
            budget.expand(m.file_size)
            # A single member is bounded above before inflation; CRC is checked at EOF.
            with archive.open(m) as src, io.TextIOWrapper(
                src, encoding="utf-8", errors="strict", newline=""
            ) as text:
                result = qc_rows(iter(csv.reader(text, strict=True)), family, day)
            result.update({"sha256": digest, "checksum_algorithm": "SHA256",
                           "publisher_checksum": "VERIFIED", "expanded_bytes": m.file_size})
            return result
    except (zipfile.BadZipFile, EOFError, UnicodeError, csv.Error, NotImplementedError):
        raise SafetyError("ZIP_OR_CSV_INTEGRITY") from None


def safe_workspace(path):
    require(path.is_absolute(), "ABSOLUTE_WORKSPACE_REQUIRED")
    for p in (path, *path.parents):
        require(not p.is_symlink(), "WORKSPACE_SYMLINK")
    require(path.is_dir() and (path / "repo/.git").is_dir()
            and not (path / "repo").is_symlink() and not (path / "repo/.git").is_symlink(),
            "WORKSPACE_LAYOUT")
    for name in ("data", "tmp", "reports"):
        p = path / name
        require(p.is_dir() and not p.is_symlink() and os.access(p, os.W_OK), "WORKSPACE_LAYOUT")
    require(shutil.disk_usage(path).free >= 1024**3, "DISK_BUDGET")
    require(not (path / "tmp/official-terms-current.md").is_symlink(), "WORKSPACE_SYMLINK")
    b = (path / "tmp/official-terms-current.md").read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()
    require(digest == TERMS_BLOB, "TERMS_CHANGED_REVIEW_REQUIRED")


def execute(workspace, acquire):
    safe_workspace(workspace)
    data = workspace / "data"
    manifest_path = workspace / "reports/acquisition.json"
    qc_path = workspace / "reports/offline-qc.json"
    if acquire:
        require(not manifest_path.exists() and not manifest_path.is_symlink(), "OUTPUT_EXISTS")
    budget = Budget()
    fetcher = Fetcher(budget)
    records = []
    if acquire:
        require(not any(data.iterdir()), "DATA_DIRECTORY_NOT_EMPTY")
    else:
        require(not manifest_path.is_symlink(), "OUTPUT_SYMLINK")
        previous = json.loads(manifest_path.read_text())
    terminal = "R10_D1_LOCAL_DEV_QC_PASS_WITH_LIMITS"
    safety_code = None
    try:
        for family in FAMILIES:
            for day in DAYS:
                url = object_url(family, day)
                name = url.rsplit("/", 1)[1]
                # Family-prefixed dirs avoid same-name kline/mark object collisions.
                folder = data / family
                if acquire:
                    folder.mkdir(exist_ok=True)
                require(folder.is_dir() and not folder.is_symlink(), "DATA_SYMLINK")
                path, check = folder / name, folder / (name + ".CHECKSUM")
                require(not path.is_symlink() and not check.is_symlink(), "DATA_SYMLINK")
                record = {"family": family, "day": day, "uri": url}
                records.append(record)
                if acquire:
                    checksum_meta = fetcher.get(url + ".CHECKSUM", check)
                    if checksum_meta is None:
                        record["checksum_status"] = "UNVERIFIED"
                    # Optional absence is established by the exact ZIP's own HTTP 404.
                    meta = fetcher.get(url, path)
                    record.update({"object": meta, "checksum_object": checksum_meta})
                    if meta is None:
                        record["qc"] = "MISSING_OBJECT"
                        if family == "klines":
                            terminal = "R10_D1_LOCAL_DEV_QC_PARTIAL_STOP"
                        continue
                    require(checksum_meta is not None, "PUBLISHER_CHECKSUM_UNVERIFIED")
                else:
                    old = next(r for r in previous["records"] if r["uri"] == url)
                    if old.get("qc") == "MISSING_OBJECT":
                        record["qc"] = "MISSING_OBJECT"
                        if family == "klines":
                            terminal = "R10_D1_LOCAL_DEV_QC_PARTIAL_STOP"
                        continue
                    budget.consume(path.stat().st_size)
                record.update(qc_zip(path, check, family, day, budget))
                schemas = [r["schema"] for r in records if r["family"] == family and "schema" in r]
                if any(s != schemas[0] for s in schemas):
                    record["errors"].append("CROSS_DAY_SCHEMA_DRIFT")
                    record["qc"] = "FAIL"
                if record["qc"] != "PASS":
                    terminal = "R10_D1_LOCAL_DEV_QC_PARTIAL_STOP"
    except SafetyError as exc:
        safety_code = str(exc)
        terminal = "R10_D1_LOCAL_AUTHORITY_RIGHTS_OR_INTEGRITY_STOP"
    except (OSError, ValueError, KeyError, StopIteration):
        safety_code = "LOCAL_INPUT_OR_IO_STOP"
        terminal = "R10_D1_LOCAL_AUTHORITY_RIGHTS_OR_INTEGRITY_STOP"
    receipt = {"terminal": terminal, "safety_code": safety_code, "records": records,
               "compressed_bytes_consumed": budget.compressed, "expanded_bytes": budget.expanded,
               "compressed_cap": COMPRESSED_CAP, "expanded_cap": EXPANDED_CAP,
               "zip_objects_requested": len(budget.zip_urls),
               "checksum_objects_requested": len(budget.checksum_urls),
               "request_attempts": fetcher.attempts, "gates": GATES,
               "smoke": "SMOKE_SKIPPED_INPUT_INCOMPLETE"}
    destination = manifest_path if acquire else qc_path
    require(not destination.is_symlink(), "OUTPUT_SYMLINK")
    if destination.exists():
        require(not acquire and json.loads(destination.read_text()) == receipt,
                "REPRODUCIBILITY_MISMATCH")
        print("OFFLINE_RECEIPT_IDENTICAL")
    else:
        with destination.open("x") as out:
            json.dump(receipt, out, indent=2, sort_keys=True)
            out.write("\n")
    print(json.dumps({k: receipt[k] for k in ("terminal", "safety_code",
                     "compressed_bytes_consumed", "expanded_bytes", "zip_objects_requested",
                     "checksum_objects_requested")}))
    return 0 if terminal.endswith("PASS_WITH_LIMITS") else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("acquire", "verify"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--owner-authorized", required=True, action="store_true")
    args = parser.parse_args()
    try:
        return execute(args.workspace, args.mode == "acquire")
    except (SafetyError, OSError):
        print("R10_D1_LOCAL_AUTHORITY_RIGHTS_OR_INTEGRITY_STOP: PREFLIGHT_OR_OUTPUT")
        return 2


if __name__ == "__main__":
    sys.exit(main())
