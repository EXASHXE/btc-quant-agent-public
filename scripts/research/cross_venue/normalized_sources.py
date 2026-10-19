"""Expansion string-v1 readers with bounded streaming and native provenance.

Only final manifest/QC names and records that are PASS in both are read. ZIPs
are hashed and streamed through the same descriptor, never extracted. A stable
archive event clock is not evidence of receiver time or prior publication.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import os
import re
import stat
import zipfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, BinaryIO

from . import DAY, US

DATA_PARENT = Path("/root/workspace/project/crypto-data/historical")
ROOT_NAMES = {
    ("Q3", "binance"): "binance-usdm-expansion",
    ("Q3", "okx"): "okx-swap-expansion",
    ("Q2", "binance"): "binance-usdm-2026q2",
    ("Q2", "okx"): "okx-swap-2026q2",
}
PROTECTED = {
    ".git", ".aws", ".agents", ".codex", "history", "histories", "forward", "oos",
    "holdout", "protected", "production", "prod", "services", "accounts",
    "quant-agent", "quant-agent-sanitized",
}
BAR_FAMILIES = {"klines", "spot_klines", "markPriceKlines", "candlesticks", "spot_candlesticks"}
FEATURE_FAMILIES = BAR_FAMILIES | {"metrics", "fundingRate", "funding_rates"}
BARS_SCHEMA = (
    "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
    "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
)
BAR_ALIASES = {
    "quote_asset_volume": "quote_volume", "number_of_trades": "count",
    "taker_buy_base_asset_volume": "taker_buy_volume",
    "taker_buy_quote_asset_volume": "taker_buy_quote_volume",
}
METRICS_SCHEMA = (
    "create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
)
OKX_SCHEMA = (
    "instrument_name", "open", "high", "low", "close", "vol", "vol_ccy", "vol_quote",
    "open_time", "confirm",
)
FUNDING_SCHEMAS = {
    "binance": ("calc_time", "funding_interval_hours", "last_funding_rate"),
    "okx": ("instrument_name", "funding_rate", "funding_time"),
}


class BridgeError(ValueError):
    def __init__(self, code: str, **details: Any):
        self.code, self.details = code, details
        super().__init__(code)


def require(condition: bool, code: str, **details: Any) -> None:
    if not condition:
        raise BridgeError(code, **details)


def finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode("ascii")


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY", key=key)
        result[key] = value
    return result


def _bad_constant(value: str) -> None:
    raise BridgeError("NONFINITE_JSON", value=value)


def utc_us(value: str) -> int:
    try:
        dt = datetime.fromisoformat(value)
        require(dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0,
                "NON_UTC_METADATA_TIME")
        return calendar.timegm(dt.utctimetuple()) * US + dt.microsecond
    except (TypeError, AttributeError, ValueError) as exc:
        if isinstance(exc, BridgeError):
            raise
        raise BridgeError("INVALID_METADATA_TIME") from None


def iso_us(value: int) -> str:
    seconds, micros = divmod(value, US)
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%S") + f".{micros:06d}Z"


def quarter_window(quarter: str) -> tuple[int, int]:
    require(quarter in ("Q2", "Q3"), "UNSUPPORTED_QUARTER")
    month = 4 if quarter == "Q2" else 7
    return (calendar.timegm((2026, month, 1, 0, 0, 0)),
            calendar.timegm((2026, month + 3, 1, 0, 0, 0)))


def safe_path(path: Path) -> Path:
    path = Path(path)
    require(".." not in path.parts, "UNSAFE_TRAVERSAL_PATH")
    path = path.absolute()
    for part in path.parts:
        lower = part.casefold()
        require(lower not in PROTECTED and not any(
            lower.startswith(p + sep) for p in PROTECTED for sep in ("-", "_", ".")
        ), "PROTECTED_PATH", component=part)
        require(not (lower.endswith((".part", ".partial", ".tmp"))
                     or lower in {"staging", ".staging"}), "UNPUBLISHED_PATH")
    return path


@contextmanager
def directory_fd(path: Path) -> Iterator[int]:
    """Walk every component using openat/O_NOFOLLOW, including ancestors."""
    path = safe_path(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except OSError as exc:
                raise BridgeError("UNSAFE_OR_MISSING_DIRECTORY", path=str(path), errno=exc.errno) from None
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def safe_directory(path: Path) -> Path:
    path = safe_path(path)
    with directory_fd(path):
        pass
    return path


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


@contextmanager
def published_file(path: Path, limit: int) -> Iterator[BinaryIO]:
    path = safe_path(path)
    with directory_fd(path.parent) as parent:
        try:
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except OSError as exc:
            raise BridgeError("UNSAFE_OR_MISSING_FILE", path=str(path), errno=exc.errno) from None
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                    "UNSAFE_FILE_TYPE_OR_HARDLINK", path=str(path))
            require(0 < before.st_size <= limit, "FILE_SIZE_LIMIT", path=str(path))
            try:
                yield stream
            finally:
                try:
                    after = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    raise BridgeError("INPUT_CHANGED", path=str(path)) from None
                require(_signature(before) == _signature(os.fstat(stream.fileno()))
                        == _signature(after), "INPUT_CHANGED", path=str(path))


def _metadata(path: Path) -> tuple[bytes, tuple[int, ...]]:
    with published_file(path, 4 * 1024**2) as stream:
        signature = _signature(os.fstat(stream.fileno()))
        return stream.read(), signature


@dataclass(slots=True)
class Snapshot:
    root: Path
    venue: str
    quarter: str
    documents: dict[str, Any] = field(default_factory=dict)
    before: dict[str, str] = field(default_factory=dict)
    after: dict[str, str | None] = field(default_factory=dict)
    signatures: dict[str, tuple[int, ...]] = field(default_factory=dict)
    unchanged: bool = False

    @classmethod
    def capture(cls, root: Path, venue: str, quarter: str) -> Snapshot:
        root = safe_directory(root)
        require((quarter, venue) in ROOT_NAMES, "UNSUPPORTED_ROOT_IDENTITY")
        require(root == DATA_PARENT / ROOT_NAMES[quarter, venue]
                or root.is_relative_to(Path("/tmp")), "INPUT_ROOT_NOT_ALLOWLISTED")
        result = cls(root, venue, quarter)
        # Register both hashes before JSON/schema dispatch; malformed moving input
        # is still distinguishable from an immutable schema error.
        raws = {}
        for name in ("manifest.json", "qc.json"):
            raw, signature = _metadata(root / name)
            result.before[name] = hashlib.sha256(raw).hexdigest()
            result.signatures[name] = signature
            raws[name] = raw
        result.verify()
        for name, raw in raws.items():
            try:
                result.documents[name] = json.loads(raw, object_pairs_hook=_unique,
                                                   parse_constant=_bad_constant)
            except (UnicodeError, json.JSONDecodeError):
                raise BridgeError("INVALID_METADATA_JSON", document=name) from None
        return result

    def verify(self) -> None:
        changed = []
        for name in ("manifest.json", "qc.json"):
            try:
                raw, signature = _metadata(self.root / name)
                self.after[name] = hashlib.sha256(raw).hexdigest()
                if self.after[name] != self.before[name] or signature != self.signatures[name]:
                    changed.append(name)
            except (OSError, BridgeError):
                self.after[name] = None
                changed.append(name)
        self.unchanged = not changed
        require(not changed, "INPUT_CHANGED", root=str(self.root), documents=changed)

    def receipt(self) -> dict[str, Any]:
        return {"quarter": self.quarter, "venue": self.venue, "root": str(self.root),
                "sha256_before": self.before, "sha256_after": self.after,
                "unchanged": self.unchanged,
                "publication_evidence": "FINAL_REGULAR_FILES_STABLE_BEFORE_AFTER"}


@dataclass(slots=True)
class Budget:
    compressed_cap: int = 128 * 1024**2
    expanded_cap: int = 384 * 1024**2
    object_cap: int = 1500
    row_cap: int = 4_000_000
    reserved_compressed: int = 0
    reserved_expanded: int = 0
    reserved_objects: int = 0
    reserved_rows: int = 0
    compressed_read: int = 0
    expanded_read: int = 0
    rows_read: int = 0

    def reserve(self, record: dict[str, Any]) -> bool:
        c, e, n = (record[k] for k in ("compressed_bytes", "expanded_bytes", "rows"))
        if (self.reserved_compressed + c > self.compressed_cap
                or self.reserved_expanded + e > self.expanded_cap
                or self.reserved_objects + 1 > self.object_cap
                or self.reserved_rows + n > self.row_cap):
            return False
        self.reserved_compressed += c
        self.reserved_expanded += e
        self.reserved_rows += n
        self.reserved_objects += 1
        return True

    def receipt(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(slots=True)
class Source:
    snapshot: Snapshot
    record: dict[str, Any]
    qc: dict[str, Any] | None
    selected: bool = False
    scan: dict[str, Any] = field(default_factory=lambda: {"status": "NOT_SCANNED"})
    actual_sha256: str | None = None

    @property
    def source_id(self) -> str:
        r = self.record
        return "/".join((self.snapshot.quarter, self.snapshot.venue, r["family"], r["symbol"], r["period"]))

    def provenance(self, native_sample: str | int, native_unit: str,
                   event_us: int, native_close: int | None = None) -> dict[str, Any]:
        r = self.record
        return {"source_id": self.source_id, "raw_source_sha256": self.actual_sha256,
                "venue": self.snapshot.venue, "market": r["market"], "contract": r["symbol"],
                "family": r["family"], "native_sample": native_sample,
                "native_close": native_close, "native_time_unit": native_unit,
                "event_utc_us": event_us, "event_utc": iso_us(event_us),
                "file_calendar_label": r["period"],
                "file_calendar_timezone": "UTC+08:00" if self.snapshot.venue == "okx" else "UTC",
                "receiver_pit": "PIT_UNKNOWN"}

    def inventory(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "schema": "EXPANSION_STRING_1.0",
                "quarter": self.snapshot.quarter, "venue": self.snapshot.venue,
                "original_record": self.record, "original_qc_record": self.qc,
                "selected": self.selected, "actual_raw_sha256": self.actual_sha256,
                "scan": self.scan, "source_admission": "SOURCE_NOT_ADMITTED"}


def expected_identity(venue: str, family: str, symbol: str) -> tuple[str, str, str]:
    """Return (asset, native market, interval); reject cross-family relabelling."""
    if venue == "binance":
        require(symbol in ("BTCUSDT", "ETHUSDT"), "SOURCE_FAMILY_IDENTITY_MISMATCH")
        require(family in {"klines", "markPriceKlines", "spot_klines", "metrics", "fundingRate"},
                "SOURCE_FAMILY_IDENTITY_MISMATCH")
        return symbol[:-4], "spot" if family == "spot_klines" else "futures_um", (
            "5m" if family == "metrics" else "8h" if family == "fundingRate" else "1m")
    require(venue == "okx", "SOURCE_VENUE_MISMATCH")
    if family == "funding_rates":
        require(symbol == "ALL_SWAPS", "SOURCE_FAMILY_IDENTITY_MISMATCH")
        return "ALL", "swap", "8h"  # Producer label only; never a calendar rule.
    require(family in {"candlesticks", "spot_candlesticks"}, "SOURCE_FAMILY_IDENTITY_MISMATCH")
    spot = family == "spot_candlesticks"
    allowed = {f"{asset}-USDT" + ("" if spot else "-SWAP"): asset for asset in ("BTC", "ETH")}
    require(symbol in allowed, "SOURCE_FAMILY_IDENTITY_MISMATCH")
    return allowed[symbol], "spot" if spot else "swap", "1m"


def expected_filename(record: dict[str, Any], venue: str) -> str:
    family, symbol, period = (record[k] for k in ("family", "symbol", "period"))
    if venue == "binance":
        stem = f"{symbol}-{'1m' if family in BAR_FAMILIES else family}-{period}"
    elif family == "funding_rates":
        stem = f"allswap-fundingrates-{period}"
    else:
        stem = f"{symbol}-candlesticks-{period}"
    return stem


def file_window(record: dict[str, Any], venue: str) -> tuple[int, int]:
    period = record["period"]
    daily = venue == "okx" or record["family"] == "metrics"
    require(bool(re.fullmatch(r"2026-\d{2}-\d{2}" if daily else r"2026-\d{2}", period)),
            "FILE_CALENDAR_LABEL_INVALID")
    try:
        dt = datetime.strptime(period, "%Y-%m-%d" if daily else "%Y-%m").replace(tzinfo=UTC)
    except ValueError:
        raise BridgeError("FILE_CALENDAR_LABEL_INVALID") from None
    left = calendar.timegm(dt.utctimetuple()) - (8 * 3600 if venue == "okx" else 0)
    length = DAY if daily else calendar.monthrange(dt.year, dt.month)[1] * DAY
    return left * US, (left + length) * US


def expansion_sources(snapshot: Snapshot, budget: Budget) -> list[Source]:
    manifest, qc = (snapshot.documents[n] for n in ("manifest.json", "qc.json"))
    for doc in (manifest, qc):
        require(type(doc) is dict and type(doc.get("manifest_version")) is str
                and doc["manifest_version"] == "1.0", "EXPANSION_SCHEMA_VERSION_INVALID")
        require(doc.get("venue") == snapshot.venue, "SOURCE_VENUE_MISMATCH")
    records, checks = manifest.get("records"), qc.get("qc_records")
    require(type(records) is list and type(checks) is list
            and len(records) <= 1000 and len(checks) <= 1000, "MANIFEST_RECORD_LIMIT_OR_TYPE")
    for rows in (records, checks):
        require(all(type(r) is dict and all(type(r.get(k)) is str and r[k]
                    for k in ("local_path", "family", "symbol", "period")) for r in rows),
                "MANIFEST_RECORD_IDENTITY_INVALID")
        require(len({r["local_path"] for r in rows}) == len(rows)
                and len({(r["family"], r["symbol"], r["period"]) for r in rows}) == len(rows),
                "DUPLICATE_SOURCE_IDENTITY")
    by_path = {r["local_path"]: r for r in checks}
    require(set(by_path) == {r["local_path"] for r in records}, "MANIFEST_QC_RECORD_SET_MISMATCH")
    result = []
    for record in sorted(records, key=lambda r: (r["family"], r["symbol"], r["period"])):
        check = by_path[record["local_path"]]
        source = Source(snapshot, record, check)
        result.append(source)
        for key in ("family", "symbol", "period", "verdict"):
            require(record.get(key) == check.get(key), "MANIFEST_QC_MISMATCH", source=source.source_id, field=key)
        if record.get("verdict") != "PASS":
            source.scan = {"status": "NOT_PASS_NOT_OPENED", "verdict": record.get("verdict")}
            continue
        if record["family"] not in FEATURE_FAMILIES:
            source.scan = {"status": "EXCLUDED_NON_FEATURE_FAMILY_NOT_OPENED"}
            if record["family"] == "orderbook":
                source.scan["producer_qc_scope"] = "PREFIX_ONLY_NOT_FULL_L2_CONTINUITY"
                source.scan["producer_sampled_messages"] = record.get("records_sampled")
            continue
        asset, market, interval = expected_identity(snapshot.venue, record["family"], record["symbol"])
        require(record.get("venue") == snapshot.venue and record.get("market") == market
                and record.get("interval") == interval, "SOURCE_FAMILY_IDENTITY_MISMATCH", source=source.source_id)
        stem = expected_filename(record, snapshot.venue)
        require(record["local_path"] == f"data/{record['family']}/{stem}.zip"
                and record.get("member_filename") == stem + ".csv", "SOURCE_PATH_FAMILY_MISMATCH")
        left, right = file_window(record, snapshot.venue)
        start, end = quarter_window(snapshot.quarter)
        calendar_shift = 8 * 3600 if snapshot.venue == "okx" else 0
        require((start - calendar_shift) * US <= left < right <= (end - calendar_shift) * US,
                "SOURCE_QUARTER_MISMATCH")
        for key in ("rows", "start_utc", "end_utc", "gaps", "duplicates", "compressed_bytes", "expanded_bytes",
                    "publisher_checksum_verified"):
            require(key in record and key in check and type(record[key]) is type(check[key])
                    and record[key] == check[key], "MANIFEST_QC_MISMATCH", source=source.source_id, field=key)
        require(record["duplicates"] == 0 and record.get("malformed_rows") == 0,
                "PASS_WITH_DUPLICATES_OR_MALFORMED_ROWS")
        require(all(type(record[k]) is int and 0 < record[k] <= limit for k, limit in
                    (("rows", 50000), ("compressed_bytes", 8 * 1024**2), ("expanded_bytes", 12 * 1024**2))),
                "SOURCE_OBJECT_BUDGET_OR_SIZE_INVALID")
        require(type(record["gaps"]) is int and record["gaps"] >= 0, "SOURCE_GAP_COUNT_INVALID")
        require(left <= utc_us(record["start_utc"]) <= utc_us(record["end_utc"]) < right,
                "METADATA_FILE_WINDOW_MISMATCH")
        sha = record.get("local_sha256")
        require(type(sha) is str and re.fullmatch(r"[a-f0-9]{64}", sha) is not None,
                "SOURCE_SHA_MISSING_OR_INVALID")
        if "fetch" in record:
            require(record["fetch"].get("sha256") == sha, "SOURCE_SHA_IDENTITY_MISMATCH")
        if snapshot.venue == "binance":
            require(record["publisher_checksum_verified"] is True
                    and record.get("publisher_checksum") == sha, "BINANCE_PUBLISHER_CHECKSUM_UNVERIFIED")
        if not budget.reserve(record):
            source.scan = {"status": "SKIPPED_SCAN_BUDGET", "asset": asset}
            continue
        source.selected = True
        source.scan = {"status": "PLANNED_FULL_STREAM_SCAN", "asset": asset}
    return result


def _csv_rows(source: Source, budget: Budget, schema: tuple[str, ...],
              *, headerless: bool = False) -> Iterator[list[str]]:
    require(source.selected and source.record["verdict"] == source.qc["verdict"] == "PASS",
            "SOURCE_NOT_SELECTED_PASS")
    record = source.record
    path = source.snapshot.root / record["local_path"]
    with published_file(path, 8 * 1024**2) as stream:
        require(os.fstat(stream.fileno()).st_size == record["compressed_bytes"], "SOURCE_SIZE_MISMATCH")
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
            budget.compressed_read += len(block)
        source.actual_sha256 = digest.hexdigest()
        require(source.actual_sha256 == record["local_sha256"], "RAW_SOURCE_SHA_MISMATCH", source=source.source_id)
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            members = archive.infolist()
            require(len(members) == 1, "ZIP_MEMBER_COUNT_INVALID")
            member = members[0]
            require(member.filename == record["member_filename"] and Path(member.filename).name == member.filename
                    and not member.is_dir() and not member.flag_bits & 1
                    and not stat.S_ISLNK(member.external_attr >> 16), "UNSAFE_ZIP_MEMBER")
            require(member.file_size == record["expanded_bytes"], "ZIP_EXPANDED_SIZE_MISMATCH")
            total = 0
            with archive.open(member) as raw:
                def lines() -> Iterator[str]:
                    nonlocal total
                    while True:
                        line = raw.readline(16385)
                        if not line:
                            break
                        total += len(line)
                        budget.expanded_read += len(line)
                        require(len(line) <= 16384 and total <= member.file_size
                                and budget.expanded_read <= budget.expanded_cap, "CSV_SCAN_BUDGET_EXCEEDED")
                        yield line.decode("utf-8")
                reader = csv.reader(lines(), strict=True)
                first = next(reader, None)
                require(first is not None, "CSV_EMPTY")
                normalized_header = tuple(BAR_ALIASES.get(c, c) for c in first) if schema == BARS_SCHEMA else tuple(first)
                if normalized_header != schema:
                    require(headerless and len(first) == len(schema) and first[0].isdigit(), "CSV_FAMILY_SCHEMA_MISMATCH")
                    yield first
                for cells in reader:
                    require(len(cells) == len(schema), "CSV_FAMILY_SCHEMA_MISMATCH")
                    yield cells
            require(total == member.file_size, "ZIP_EXPANDED_SIZE_MISMATCH")
            source.scan["expanded_bytes_read"] = total
            source.scan["compressed_bytes_hashed"] = record["compressed_bytes"]


@dataclass(frozen=True, slots=True)
class Bar:
    asset: str
    venue: str
    market: str
    family: str
    symbol: str
    open_us: int
    end_us: int
    opening: float
    high: float
    low: float
    closing: float
    native_volume: float
    quote_volume: float
    provenance: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {**self.provenance, "asset": self.asset, "price_unit": f"USDT_PER_{self.asset}",
                "price_role": "MARK_VALUATION" if self.family == "markPriceKlines" else "LAST_TRADE_BAR",
                "open": self.opening, "high": self.high, "low": self.low, "close": self.closing,
                "native_volume": self.native_volume, "quote_volume_usdt": self.quote_volume,
                "native_volume_unit": "CONTRACTS" if self.venue == "okx" and self.market == "swap" else self.asset,
                "bar_end_utc_us": self.end_us,
                "close_time_evidence": "DERIVED_1M_END_CONFIRMED_BAR" if self.venue == "okx" else "NATIVE_CLOSE_TIME",
                "executable_fill": "UNKNOWN"}


def _finish(source: Source, count: int, first_us: int | None, last_us: int | None,
            budget: Budget, **extra: Any) -> None:
    require(count == source.record["rows"], "SOURCE_ROW_COUNT_MISMATCH", source=source.source_id)
    require(first_us == utc_us(source.record["start_utc"]) and last_us == utc_us(source.record["end_utc"]),
            "SOURCE_TIME_BOUNDS_MISMATCH", source=source.source_id)
    source.scan.update(status="FULL_STREAM_SCAN", rows=count, first_event_utc_us=first_us,
                       last_event_utc_us=last_us, **extra)
    budget.rows_read += count
    require(budget.rows_read <= budget.row_cap, "ROW_SCAN_BUDGET_EXCEEDED")


def source_bars(source: Source, budget: Budget) -> Iterator[Bar]:
    r, venue = source.record, source.snapshot.venue
    require(r["family"] in BAR_FAMILIES, "BAR_FAMILY_MISMATCH")
    asset, _, _ = expected_identity(venue, r["family"], r["symbol"])
    schema = BARS_SCHEMA if venue == "binance" else OKX_SCHEMA
    left, right = file_window(r, venue)
    unit = "us" if r["family"] == "spot_klines" else "ms"
    factor = 1 if unit == "us" else 1000
    previous = first = last = None
    first_native = last_native = None
    count = gaps = 0
    for cells in _csv_rows(source, budget, schema, headerless=r["family"] == "spot_klines"):
        if venue == "binance":
            native_open, native_close = int(cells[0]), int(cells[6])
            open_us, end_us = native_open * factor, native_close * factor
            require(native_close - native_open == 60 * US // factor - 1, "NATIVE_BAR_INTERVAL_INVALID")
            opening, high, low, closing, volume = map(float, cells[1:6])
            quote = float(cells[7])
        else:
            require(cells[0] == r["symbol"], "CSV_SYMBOL_FAMILY_MISMATCH")
            require(cells[9] == "1", "OKX_BAR_NOT_CLOSED")
            native_open, native_close = int(cells[8]), None
            open_us = native_open * 1000
            end_us = open_us + 60 * US - 1
            opening, high, low, closing, volume = map(float, cells[1:6])
            quote = float(cells[7])
        require(open_us % (60 * US) == 0 and left <= open_us < right,
                "NATIVE_TIME_OR_CALENDAR_WINDOW_INVALID")
        require(all(finite(v) and v > 0 for v in (opening, high, low, closing))
                and low <= min(opening, closing) <= max(opening, closing) <= high
                and all(finite(v) and v >= 0 for v in (volume, quote)), "INVALID_BAR_VALUE")
        require(previous is None or open_us > previous, "DUPLICATE_OR_BACKWARD_BAR")
        if previous is not None:
            gaps += (open_us - previous) // (60 * US) - 1
        if first is None:
            first, first_native = open_us, native_open
        last, last_native, previous = open_us, native_open, open_us
        count += 1
        require(count <= r["rows"], "SOURCE_ROW_LIMIT")
        yield Bar(asset, venue, r["market"], r["family"], r["symbol"], open_us, end_us,
                  opening, high, low, closing, volume, quote,
                  source.provenance(native_open, unit, open_us, native_close))
    _finish(source, count, first, last, budget, missing_minutes=gaps,
            first_native_sample=first_native, last_native_sample=last_native,
            native_time_unit=unit, epoch_shift_applied_us=0)


@dataclass(frozen=True, slots=True)
class Stock:
    asset: str
    t_us: int
    base_oi: float | None
    top_position_ls: float | None
    provenance: dict[str, Any]
    interval_s: int = 300
    venue: str = "binance"
    market: str = "futures_um"

    def as_dict(self) -> dict[str, Any]:
        return {**self.provenance, "base_oi": self.base_oi, "base_oi_unit": self.asset,
                "top_position_long_short_ratio": self.top_position_ls,
                "ratio_unit": "DIMENSIONLESS", "native_interval_s": self.interval_s}


def _optional_number(value: str) -> float | None:
    try:
        result = float(value)
    except ValueError:
        return None
    return result if finite(result) else None


def source_stocks(source: Source, budget: Budget) -> Iterator[Stock]:
    require(source.record["family"] == "metrics" and source.snapshot.venue == "binance", "STOCK_FAMILY_MISMATCH")
    r = source.record
    require(r["rows"] <= 288, "DAILY_STOCK_ROW_LIMIT")
    left, right = file_window(r, "binance")
    parsed = []
    previous = None
    backwards = 0
    for cells in _csv_rows(source, budget, METRICS_SCHEMA):
        require(cells[1] == r["symbol"], "CSV_SYMBOL_FAMILY_MISMATCH")
        try:
            dt = datetime.strptime(cells[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            raise BridgeError("STOCK_NATIVE_TIME_INVALID") from None
        t = calendar.timegm(dt.utctimetuple()) * US
        require(t % (300 * US) == 0 and left <= t < right, "STOCK_NATIVE_TIME_INVALID")
        backwards += int(previous is not None and t < previous)
        previous = t
        parsed.append(Stock(r["symbol"][:-4], t, _optional_number(cells[2]), _optional_number(cells[5]),
                            source.provenance(cells[0], "UTC_TEXT_SECONDS", t)))
        require(len(parsed) <= r["rows"], "SOURCE_ROW_LIMIT")
    parsed.sort(key=lambda row: row.t_us)
    require(all(b.t_us > a.t_us for a, b in pairwise(parsed)), "DUPLICATE_STOCK_TIMESTAMP")
    _finish(source, len(parsed), parsed[0].t_us if parsed else None, parsed[-1].t_us if parsed else None,
            budget, native_backward_transitions=backwards,
            order_policy="BOUNDED_DAILY_EVENT_SORT_NOT_RECEIVER_ORDER", native_time_unit="UTC_TEXT_SECONDS")
    yield from parsed


@dataclass(frozen=True, slots=True)
class Funding:
    asset: str
    venue: str
    t_us: int
    rate: float | None
    provenance: dict[str, Any]
    native_interval_hours: float | None = None

    def as_dict(self) -> dict[str, Any]:
        instrument = f"{self.asset}USDT" if self.venue == "binance" else f"{self.asset}-USDT-SWAP"
        return {**self.provenance, "instrument": instrument, "contract": instrument,
                "container_contract": self.provenance["contract"],
                "asset": self.asset, "settled_rate": self.rate, "rate_unit": "FRACTION",
                "native_interval_hours": self.native_interval_hours,
                "evidence": "ACTUAL_SETTLEMENT_NOT_FORECAST_OR_FIRST_KNOWN_TIME"}


def source_funding(source: Source, budget: Budget) -> Iterator[Funding]:
    r, venue = source.record, source.snapshot.venue
    require(r["family"] == ("fundingRate" if venue == "binance" else "funding_rates"), "FUNDING_FAMILY_MISMATCH")
    left, right = file_window(r, venue)
    observed = set()
    selected = []
    count = 0
    invalid_rate_rows = 0
    first = last = None
    physical_first = physical_last = None
    for cells in _csv_rows(source, budget, FUNDING_SCHEMAS[venue]):
        if venue == "binance":
            instrument, native, rate = r["symbol"], int(cells[0]), _optional_number(cells[2])
            interval = float(cells[1])
            require(finite(interval) and interval > 0, "FUNDING_NATIVE_INTERVAL_INVALID")
            asset = instrument[:-4]
        else:
            instrument, native, rate, interval = cells[0], int(cells[2]), _optional_number(cells[1]), None
            asset = {"BTC-USDT-SWAP": "BTC", "ETH-USDT-SWAP": "ETH"}.get(instrument)
        t = native * 1000
        require(left <= t < right, "FUNDING_NATIVE_TIME_INVALID")
        invalid_rate_rows += int(rate is None)
        require((instrument, t) not in observed, "DUPLICATE_FUNDING_SETTLEMENT")
        observed.add((instrument, t))
        first, last = (t if first is None else min(first, t)), (t if last is None else max(last, t))
        physical_first = t if physical_first is None else physical_first
        physical_last = t
        count += 1
        require(count <= r["rows"], "SOURCE_ROW_LIMIT")
        if asset is not None:
            provenance = source.provenance(native, "ms", t)
            provenance["native_instrument"] = instrument
            selected.append(Funding(asset, venue, t, rate, provenance, interval))
    # Expansion QC records physical first/last rows. ALL_SWAPS is grouped by
    # instrument and these are not necessarily its minimum/maximum event times.
    # Preserve that producer convention and publish measured extrema separately.
    _finish(source, count, physical_first, physical_last, budget,
            retained_btc_eth_settlements=len(selected), observed_min_event_utc_us=first,
            observed_max_event_utc_us=last, producer_time_fields="PHYSICAL_FIRST_LAST_NOT_CALENDAR_EXTREMA",
            invalid_rate_rows=invalid_rate_rows,
            retained_invalid_rate_rows=sum(e.rate is None for e in selected),
            calendar_policy="OBSERVED_PER_INSTRUMENT_NO_INFERRED_CADENCE", native_time_unit="ms")
    yield from sorted(selected, key=lambda row: (row.asset, row.t_us))


def inventory_counts(sources: list[Source]) -> dict[str, Any]:
    return {"records": len(sources), "published_pass_records": sum(s.record.get("verdict") == "PASS" for s in sources),
            "verdicts": dict(sorted(Counter(s.record.get("verdict", "MISSING") for s in sources).items())),
            "scan_states": dict(sorted(Counter(s.scan["status"] for s in sources).items()))}
