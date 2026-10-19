"""Bounded read-only expansion-v1 adapter and clocked ten-control dataset.

Native integers/units and source records survive normalization. Historical
inspection builds features only: it has no path to price/funding outcome labels.
No data producer, collector, verify action, tick or L2 reader is imported.
"""

from __future__ import annotations

import bisect
import csv
import hashlib
import itertools
import json
import math
import re
import stat
import zipfile
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from . import DAY, HORIZONS, LABELS
from .costs import US, finite

JULY_START = int(datetime(2026, 7, 1, tzinfo=UTC).timestamp())
JULY_END = JULY_START + 31 * DAY
PROTECTED_PARTS = {
    ".git", ".aws", ".agents", ".codex", "history", "forward", "oos", "holdout",
    "protected", "production", "services", "accounts", "quant-agent", "quant-agent-sanitized",
}
BARS_SCHEMA = (
    "open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
    "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
)
METRICS_SCHEMA = (
    "create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio",
)
OKX_SCHEMA = (
    "instrument_name", "open", "high", "low", "close", "vol", "vol_ccy", "vol_quote",
    "open_time", "confirm",
)


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def safe_directory(path: Path, *, missing: bool = False) -> Path:
    path = Path(path).absolute()
    require(not any(p.casefold() in PROTECTED_PARTS or p == ".." for p in path.parts),
            "PROTECTED_OR_TRAVERSAL_PATH")
    for component in (*reversed(path.parents), path):
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            require(missing, "REQUIRED_DIRECTORY_MISSING")
            continue
        require(not stat.S_ISLNK(mode), "UNSAFE_DIRECTORY_SYMLINK")
        require(stat.S_ISDIR(mode), "UNSAFE_DIRECTORY_TYPE")
    return path


def prepare_output(path: Path) -> Path:
    path = safe_directory(path, missing=True)
    require(path.is_relative_to(Path("/tmp")) and path != Path("/tmp"), "OUTPUT_MUST_BE_TMP")
    if path.exists():
        require(not any(path.iterdir()), "OUTPUT_DIRECTORY_NOT_EMPTY")
    else:
        path.mkdir(parents=True)
    return safe_directory(path)


def safe_file(root: Path, relative: str, limit: int) -> Path:
    require(type(relative) is str and bool(relative), "UNSAFE_OBJECT_PATH")
    rel = Path(relative)
    require(not rel.is_absolute() and ".." not in rel.parts, "UNSAFE_OBJECT_PATH")
    root = safe_directory(root)
    path = root / rel
    safe_directory(path.parent)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "UNSAFE_OBJECT_TYPE")
    require(0 < info.st_size <= limit, "OBJECT_SIZE_LIMIT")
    return path


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _nonfinite(value: str) -> None:
    raise ValueError("NONFINITE_JSON")


def read_json(path: Path, limit: int = 2 * 1024**2) -> Any:
    path = safe_file(path.parent, path.name, limit)
    return json.loads(path.read_bytes(), object_pairs_hook=_unique, parse_constant=_nonfinite)


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(slots=True)
class Budget:
    compressed_cap: int = 64 * 1024**2
    expanded_cap: int = 128 * 1024**2
    compressed: int = 0
    expanded: int = 0
    objects: int = 0

    def compressed_object(self, size: int) -> None:
        require(self.compressed + size <= self.compressed_cap and self.objects < 96,
                "COMPRESSED_OR_OBJECT_BUDGET_EXCEEDED")
        self.compressed += size
        self.objects += 1

    def expanded_bytes(self, size: int) -> None:
        require(self.expanded + size <= self.expanded_cap, "EXPANDED_BUDGET_EXCEEDED")
        self.expanded += size


@dataclass(frozen=True, slots=True)
class Bar:
    open_us: int
    close_us: int
    opening: float
    high: float
    low: float
    closing: float
    volume: float
    quote_volume: float
    buy_quote: float | None
    symbol: str = "BTCUSDT"
    market: str = "futures_um"
    venue: str = "binance"
    interval_verified: bool = True

    @property
    def t(self) -> int:
        return self.open_us // US


@dataclass(frozen=True, slots=True)
class Stock:
    t: int
    base_oi: float | None
    top_position_ls: float | None
    interval_s: int = 300
    symbol: str = "BTCUSDT"
    market: str = "futures_um"
    native_timestamp: str | int | None = None
    native_unit: str = "UTC_TEXT_SECONDS"


@dataclass(slots=True)
class Source:
    root: Path
    record: dict[str, Any]
    qc: dict[str, Any]
    actual_sha256: str
    native_unit: str | None = None
    normalized_rows: int = 0
    first_native_timestamp: str | int | None = None
    last_native_timestamp: str | int | None = None
    normalization_status: str = "NOT_READ"
    archive_first_native_timestamp: str | int | None = None
    archive_last_native_timestamp: str | int | None = None
    native_backward_transitions: int = 0

    def inventory(self) -> dict[str, Any]:
        return {
            "source_schema": "EXPANSION_STRING_1.0", "original_record": self.record,
            "original_qc_record": self.qc, "actual_sha256": self.actual_sha256,
            "native_timestamp_unit": self.native_unit,
            "first_native_timestamp": self.first_native_timestamp,
            "last_native_timestamp": self.last_native_timestamp,
            "normalized_rows": self.normalized_rows, "normalization_status": self.normalization_status,
            "archive_first_native_timestamp": self.archive_first_native_timestamp,
            "archive_last_native_timestamp": self.archive_last_native_timestamp,
            "native_backward_transitions": self.native_backward_transitions,
            "stock_order_policy": "BOUNDED_DAILY_EVENT_TIME_SORT_NOT_RECEIVER_ORDER" if self.record["family"] == "metrics" else "NATIVE_STREAM_ORDER",
            "labels": list(LABELS), "exposure": "HISTORICAL_OFFLINE_COVERAGE_ONLY",
        }


FAMILY_IDENTITIES = {
    "binance": {
        "klines": ("BTCUSDT", "futures_um", "1m"),
        "spot_klines": ("BTCUSDT", "spot", "1m"),
        "metrics": ("BTCUSDT", "futures_um", "5m"),
    },
    "okx": {
        "candlesticks": ("BTC-USDT-SWAP", "swap", "1m"),
        "spot_candlesticks": ("BTC-USDT", "spot", "1m"),
    },
}


def expansion_sources(root: Path, venue: str, budget: Budget) -> tuple[list[Source], dict[str, Any]]:
    """Dispatch exactly string-v1; integer P0-v2 is deliberately not relabelled."""
    root = safe_directory(root)
    manifest = read_json(root / "manifest.json")
    qc = read_json(root / "qc.json")
    for doc in (manifest, qc):
        require(type(doc) is dict and type(doc.get("manifest_version")) is str
                and doc["manifest_version"] == "1.0", "EXPANSION_SCHEMA_VERSION_INVALID")
        require(doc.get("venue") == venue, "SOURCE_VENUE_MISMATCH")
    records = manifest.get("records")
    checks = qc.get("qc_records")
    require(type(records) is list and len(records) <= 1000
            and type(checks) is list and len(checks) <= 1000, "MANIFEST_RECORDS_INVALID")
    require(all(type(r) is dict for r in records + checks), "MANIFEST_RECORD_INVALID")
    paths = [r.get("local_path") for r in records]
    qpaths = [r.get("local_path") for r in checks]
    require(all(type(p) is str for p in paths + qpaths)
            and len(set(paths)) == len(paths) and len(set(qpaths)) == len(qpaths),
            "MANIFEST_DUPLICATE_OR_INVALID_IDENTITY")
    qc_by_path = {r["local_path"]: r for r in checks}
    selected = []
    excluded = Counter()
    identities = FAMILY_IDENTITIES[venue]
    for record in records:
        family = record.get("family")
        period = record.get("period")
        if (family not in identities or record.get("symbol") != identities[family][0]
                or type(period) is not str or not period.startswith("2026-07")):
            excluded[str(family)] += 1
            continue
        symbol, market, interval = identities[family]
        require(record.get("venue") == venue and record.get("symbol") == symbol
                and record.get("market") == market and record.get("interval") == interval,
                "SOURCE_MARKET_OR_INTERVAL_MISMATCH")
        daily = family in ("metrics", "candlesticks", "spot_candlesticks")
        require(bool(re.fullmatch(r"2026-07-(0[1-9]|[12][0-9]|3[01])" if daily else
                                  r"2026-07", period)), "SOURCE_PERIOD_INVALID")
        check = qc_by_path.get(record["local_path"])
        require(check is not None, "QC_RECORD_MISSING")
        for key in ("family", "symbol", "period", "verdict", "rows", "start_utc", "end_utc",
                    "gaps", "duplicates", "compressed_bytes", "expanded_bytes",
                    "publisher_checksum_verified"):
            require(key in record and key in check and type(record[key]) is type(check[key])
                    and record[key] == check[key], "MANIFEST_QC_MISMATCH")
        require(record["verdict"] == "PASS" and record["gaps"] == 0
                and record["duplicates"] == 0 and record.get("malformed_rows") == 0,
                "SOURCE_QC_NOT_COMPLETE_PASS")
        require(type(record["rows"]) is int and 0 < record["rows"] <= 50000
                and type(record["expanded_bytes"]) is int
                and 0 < record["expanded_bytes"] <= 12 * 1024**2, "SOURCE_ROW_OR_SIZE_LIMIT")
        path = safe_file(root, record["local_path"], 16 * 1024**2)
        require(path.stat().st_size == record["compressed_bytes"], "SOURCE_SIZE_MISMATCH")
        budget.compressed_object(path.stat().st_size)
        actual = digest_file(path)
        require(type(record.get("local_sha256")) is str
                and actual == record["local_sha256"], "SOURCE_DIGEST_MISMATCH")
        selected.append(Source(root, record, check, actual))
    require(set(r.record["family"] for r in selected) == set(identities),
            "REQUIRED_BTC_FEATURE_SERIES_MISSING")
    selected.sort(key=lambda s: (s.record["family"], s.record["period"]))
    return selected, {
        "venue": venue, "manifest_version": "1.0", "manifest_sha256": digest_file(root / "manifest.json"),
        "qc_sha256": digest_file(root / "qc.json"), "manifest_records": len(records),
        "selected_objects": len(selected), "excluded_family_counts": dict(excluded),
        "selection": "2026-07_BTC_FEATURE_FAMILIES_ONLY", "ticks_l2_opened": 0,
    }


def _csv(source: Source, budget: Budget) -> Iterator[list[str]]:
    record = source.record
    path = safe_file(source.root, record["local_path"], 16 * 1024**2)
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        require(len(members) == 1, "ZIP_MEMBER_COUNT_INVALID")
        member = members[0]
        require(member.filename == record.get("member_filename")
                and Path(member.filename).name == member.filename
                and member.filename.endswith(".csv") and not member.is_dir()
                and not member.flag_bits & 1
                and not stat.S_ISLNK(member.external_attr >> 16), "ZIP_MEMBER_UNSAFE")
        require(member.file_size == record["expanded_bytes"]
                and member.file_size <= 12 * 1024**2, "ZIP_EXPANSION_LIMIT")
        with archive.open(member) as raw:
            def lines() -> Iterator[str]:
                total = 0
                while True:
                    line = raw.readline(16385)
                    if not line:
                        break
                    total += len(line)
                    require(len(line) <= 16384 and total <= member.file_size, "CSV_LINE_OR_SIZE_LIMIT")
                    budget.expanded_bytes(len(line))
                    yield line.decode("utf-8")
                require(total == member.file_size, "ZIP_EXPANDED_SIZE_MISMATCH")
            yield from csv.reader(lines())


def _header_rows(source: Source, budget: Budget, schema: tuple[str, ...],
                 *, headerless: bool = False) -> Iterator[list[str]]:
    rows = _csv(source, budget)
    first = next(rows, None)
    require(first is not None, "CSV_EMPTY")
    if tuple(first) == schema:
        yield from rows
    else:
        require(headerless and len(first) == len(schema) and first[0].isdigit(), "CSV_SCHEMA_MISMATCH")
        yield first
        yield from rows


def _bar_valid(bar: Bar, *, x_control: bool = False) -> bool:
    prices = (bar.opening, bar.high, bar.low, bar.closing)
    return (bar.interval_verified and type(bar.open_us) is int and type(bar.close_us) is int
            and bar.open_us % (60 * US) == 0
            and bar.open_us + 59 * US <= bar.close_us < bar.open_us + 60 * US
            and all(finite(v) and v > 0 for v in prices)
            and bar.low <= min(bar.opening, bar.closing) <= max(bar.opening, bar.closing) <= bar.high
            and finite(bar.volume) and bar.volume >= 0
            and finite(bar.quote_volume) and bar.quote_volume >= 0
            and (not x_control or finite(bar.buy_quote)
                 and 0 <= bar.buy_quote <= bar.quote_volume))


def source_bars(source: Source, budget: Budget) -> Iterator[Bar]:
    record = source.record
    venue = record["venue"]
    unit = "us" if record["family"] == "spot_klines" else "ms"
    source.native_unit = unit
    schema = BARS_SCHEMA if venue == "binance" else OKX_SCHEMA
    previous = None
    first_t = last_t = None
    count = 0
    for cells in _header_rows(source, budget, schema, headerless=record["family"] == "spot_klines"):
        require(len(cells) == len(schema), "CSV_SCHEMA_MISMATCH")
        try:
            if venue == "binance":
                native_open, native_close = int(cells[0]), int(cells[6])
                factor = 1 if unit == "us" else 1000
                require(native_close - native_open == 60 * US // factor - 1, "NATIVE_1M_INTERVAL_INVALID")
                bar = Bar(native_open * factor, native_close * factor,
                          *map(float, cells[1:6]), float(cells[7]), float(cells[10]),
                          record["symbol"], record["market"], venue)
            else:
                require(cells[0] == record["symbol"], "CSV_SYMBOL_MISMATCH")
                require(cells[9] == "1", "CANDLE_NOT_CONFIRMED")
                native_open = int(cells[8])
                bar = Bar(native_open * 1000, native_open * 1000 + 60 * US - 1,
                          *map(float, cells[1:6]), float(cells[7]), None,
                          record["symbol"], record["market"], venue)
            require(_bar_valid(bar, x_control=record["family"] == "klines"), "BAR_NUMERIC_OR_INTERVAL_INVALID")
            require(previous is None or bar.t == previous + 60, "SOURCE_1M_GAP_OR_ORDER_INVALID")
            label = datetime.fromisoformat(record["period"] + ("-01" if len(record["period"]) == 7 else "")).replace(tzinfo=UTC)
            left = int(label.timestamp()) - (8 * 3600 if venue == "okx" else 0)
            right = left + (DAY if venue == "okx" else 31 * DAY)
            require(left <= bar.t < right, "NATIVE_TIMESTAMP_UNIT_OR_FILE_WINDOW_INVALID")
        except (TypeError, OverflowError):
            raise ValueError("BAR_SCHEMA_INVALID") from None
        count += 1
        require(count <= record["rows"], "SOURCE_ROW_LIMIT")
        if first_t is None:
            first_t = bar.t
            source.first_native_timestamp = native_open
        last_t = previous = bar.t
        source.last_native_timestamp = native_open
        yield bar
    _finish_source(source, count, first_t, last_t)


def _finish_source(source: Source, count: int, first_t: int | None, last_t: int | None) -> None:
    record = source.record
    require(count == record["rows"], "SOURCE_ROW_COUNT_MISMATCH")
    require(first_t == int(datetime.fromisoformat(record["start_utc"]).timestamp())
            and last_t == int(datetime.fromisoformat(record["end_utc"]).timestamp()),
            "SOURCE_TIME_BOUNDS_MISMATCH")
    source.normalized_rows = count
    source.normalization_status = "COMPLETE_BOUNDED_FEATURE_QC"


def source_stocks(source: Source, budget: Budget) -> Iterator[Stock]:
    record = source.record
    require(record["family"] == "metrics", "Z_NATIVE_FAMILY_INVALID")
    source.native_unit = "UTC_TEXT_SECONDS"
    require(record["rows"] <= 288, "Z_DAILY_ROW_LIMIT")
    parsed = []
    previous = None
    for cells in _header_rows(source, budget, METRICS_SCHEMA):
        require(len(cells) == 8, "CSV_SCHEMA_MISMATCH")
        require(cells[1] == "BTCUSDT", "CSV_SYMBOL_MISMATCH")
        instant = datetime.strptime(cells[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        t = int(instant.timestamp())
        require(t % 300 == 0, "Z_NATIVE_INTERVAL_INVALID")
        require(cells[0].startswith(record["period"]), "Z_FILE_WINDOW_INVALID")
        # Invalid stock values remain unavailable at their fixed origins.
        try:
            oi, ratio = float(cells[2]), float(cells[5])
        except ValueError:
            oi = ratio = None
        require(len(parsed) < record["rows"], "SOURCE_ROW_LIMIT")
        if not parsed:
            source.archive_first_native_timestamp = cells[0]
        source.archive_last_native_timestamp = cells[0]
        source.native_backward_transitions += int(previous is not None and t < previous)
        previous = t
        parsed.append(Stock(t, oi, ratio, native_timestamp=cells[0]))
    # Native daily metrics can be physically unordered. This bounded stock-state
    # projection sorts event time only, preserving the raw hash/order evidence;
    # it neither constructs nor claims receiver-first-known chronology.
    parsed.sort(key=lambda stock: stock.t)
    require(all(b.t - a.t == 300 for a, b in zip(parsed, parsed[1:])), "Z_NATIVE_INTERVAL_INVALID")
    if parsed:
        source.first_native_timestamp = parsed[0].native_timestamp
        source.last_native_timestamp = parsed[-1].native_timestamp
    _finish_source(source, len(parsed), parsed[0].t if parsed else None, parsed[-1].t if parsed else None)
    yield from parsed


def select_z(stocks: dict[int, Stock], times: list[int], cutoff: int) -> dict[str, Any]:
    index = bisect.bisect_right(times, cutoff - 300) - 1
    base = {"z": None, "z_t": None, "z_4h_exact": False, "raw_z_present": False,
            "z_status": "UNAVAILABLE", "z_reason": "MISSING_Z"}
    if index < 0:
        if times and times[0] <= cutoff:
            base.update(raw_z_present=True, z_reason="Z_FUTURE_OR_TOO_RECENT", z_t=times[0])
        return base
    sample = stocks[times[index]]
    base.update(raw_z_present=True, z_t=sample.t)
    if not cutoff - 600 <= sample.t <= cutoff - 300:
        base["z_reason"] = "Z_STALE"
        return base
    if sample.interval_s != 300 or sample.t % 300:
        base["z_reason"] = "Z_NATIVE_INTERVAL_INVALID"
        return base
    if sample.symbol != "BTCUSDT" or sample.market != "futures_um":
        base["z_reason"] = "Z_SOURCE_IDENTITY_INVALID"
        return base
    predecessor = stocks.get(sample.t - 4 * 3600)
    if predecessor is None:
        base["z_reason"] = "Z_4H_PREDECESSOR_MISSING"
        return base
    if (predecessor.interval_s != 300 or predecessor.t != sample.t - 14400
            or predecessor.symbol != sample.symbol or predecessor.market != sample.market):
        base["z_reason"] = "Z_4H_PREDECESSOR_INVALID"
        return base
    if not all(finite(v) and v > 0 for v in (sample.base_oi, predecessor.base_oi, sample.top_position_ls)):
        base["z_reason"] = "Z_INVALID_STOCK"
        return base
    z = [math.log(sample.base_oi) - math.log(predecessor.base_oi), math.log(sample.top_position_ls)]
    if not all(finite(v) for v in z):
        base["z_reason"] = "Z_INVALID_STOCK"
        return base
    base.update(z=z, z_4h_exact=True, z_status="OBSERVED", z_reason="READY")
    return base


def controls(futures: list[Bar], spot: list[Bar], cutoff: int) -> tuple[list[float] | None, str]:
    if len(futures) != 1441 or len(spot) != 1441:
        return None, "MISSING_X_1M_WINDOW"
    expected = range(cutoff - DAY - 60, cutoff, 60)
    if any(a.t != t or b.t != t for a, b, t in zip(futures, spot, expected)):
        return None, "MISSING_X_1M_WINDOW"
    for a, b in zip(futures, spot):
        if (a.venue != "binance" or b.venue != "binance" or a.symbol != "BTCUSDT"
                or b.symbol != "BTCUSDT" or a.market != "futures_um" or b.market != "spot"):
            return None, "X_SOURCE_IDENTITY_INVALID"
        if a.close_us >= cutoff * US or b.close_us >= cutoff * US:
            return None, "X_BAR_NOT_STRICTLY_CLOSED"
        if not _bar_valid(a, x_control=True) or not _bar_valid(b):
            return None, "X_INVALID_BAR_OR_NATIVE_INTERVAL"
    closes = [b.closing for b in futures]
    increments = [math.log(b) - math.log(a) for a, b in zip(closes, closes[1:])]
    hour, day = futures[-60:], futures[-1440:]
    volume_h, volume_d = sum(b.volume for b in hour), sum(b.volume for b in day)
    quote = sum(b.quote_volume for b in hour)
    low, high = min(b.low for b in day), max(b.high for b in day)
    if min(volume_h, volume_d, quote, high - low) <= 0:
        return None, "X_ZERO_DENOMINATOR"
    x = [math.log(closes[-1]) - math.log(closes[-1 - h * 60]) for h in (1, 4, 24)]
    x.extend((math.sqrt(sum(v * v for v in increments[-60:])),
              math.sqrt(sum(v * v for v in increments)), math.log1p(quote),
              math.log(volume_h / (volume_d / 24)),
              2 * sum(b.buy_quote for b in hour) / quote - 1,
              (closes[-1] - low) / (high - low) - 0.5,
              sum(math.log(a.closing) - math.log(b.closing)
                  for a, b in zip(futures[-60:], spot[-60:])) / 60))
    return (x, "READY") if all(finite(v) for v in x) else (None, "X_NONFINITE")


def feature_grid(futures: Iterable[Bar], spot: Iterable[Bar], stocks: dict[int, Stock],
                 start: int, end: int) -> list[dict[str, Any]]:
    require(type(start) is int and type(end) is int and start % DAY == 0
            and end > start and end % DAY == 0, "GRID_WINDOW_INVALID")
    streams = [iter(futures), iter(spot)]
    heads = [next(s, None) for s in streams]
    windows = [deque(maxlen=1441), deque(maxlen=1441)]
    previous = [None, None]
    times = sorted(stocks)
    require(all(type(t) is int and stocks[t].t == t for t in times), "Z_TIMESTAMP_INVALID")
    result = []
    for cutoff in range(start, end, 3600):
        for k in (0, 1):
            while heads[k] is not None and heads[k].open_us < cutoff * US:
                bar = heads[k]
                require(previous[k] is None or bar.open_us > previous[k], "BAR_ORDER_INVALID")
                previous[k] = bar.open_us
                if bar.t >= cutoff - DAY - 60:
                    windows[k].append(bar)
                heads[k] = next(streams[k], None)
            while windows[k] and windows[k][0].t < cutoff - DAY - 60:
                windows[k].popleft()
        x, reason = controls(list(windows[0]), list(windows[1]), cutoff)
        if x is None and cutoff - start < DAY + 60:
            reason = "WARMUP_X_24H"
        result.append({
            "t": cutoff + 60, "cutoff": cutoff, "entry_t": cutoff + 120,
            "x": x, "x_complete": x is not None, "x_reason": reason,
            "x_end_us": windows[0][-1].close_us if windows[0] else None,
            **select_z(stocks, times, cutoff),
        })
    # Exhaust selected bounded archives so QC includes their final rows and CRCs.
    for k in (0, 1):
        for bar in itertools.chain(() if heads[k] is None else (heads[k],), streams[k]):
            require(previous[k] is None or bar.open_us > previous[k], "BAR_ORDER_INVALID")
            previous[k] = bar.open_us
    return result


def ready(row: dict[str, Any]) -> tuple[bool, bool]:
    t = row.get("t")
    require(type(t) is int and t % 3600 == 60, "NON_FIXED_CLOCK")
    cutoff = t - 60
    x = row.get("x")
    xok = (type(x) is list and len(x) == 10 and all(finite(v) for v in x)
           and row.get("x_complete") is True and type(row.get("x_end_us")) is int
           and row["x_end_us"] < cutoff * US)
    z = row.get("z")
    zok = (row.get("z_status") == "OBSERVED" and type(z) is list and len(z) == 2
           and all(finite(v) for v in z) and type(row.get("z_t")) is int
           and cutoff - 600 <= row["z_t"] <= cutoff - 300
           and row["z_t"] % 300 == 0 and row.get("z_4h_exact") is True)
    return xok, xok and zok


def validate_grid(rows: list[dict[str, Any]], start: int) -> None:
    require(type(start) is int and start % DAY == 0 and type(rows) is list and bool(rows), "GRID_WINDOW_INVALID")
    require(len(rows) <= 92 * 24, "GRID_ROW_LIMIT")
    for i, row in enumerate(rows):
        require(type(row) is dict and row.get("t") == start + i * 3600 + 60,
                "GRID_ROWS_MUST_INCLUDE_UNAVAILABLE_ORIGINS")
        ready(row)


def inspect_panel(binance_root: Path, okx_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    budget = Budget()
    binance, bmeta = expansion_sources(binance_root, "binance", budget)
    okx, ometa = expansion_sources(okx_root, "okx", budget)
    stocks = {}
    for source in binance:
        if source.record["family"] == "metrics":
            for stock in source_stocks(source, budget):
                require(stock.t not in stocks, "Z_DUPLICATE_TIMESTAMP")
                stocks[stock.t] = stock
    def bars(sources: list[Source], family: str) -> Iterator[Bar]:
        for source in sources:
            if source.record["family"] == family:
                yield from source_bars(source, budget)
    rows = feature_grid(bars(binance, "klines"), bars(binance, "spot_klines"), stocks,
                        JULY_START, JULY_END)
    for row in rows:
        row["clock_verdict"] = {"status": "PIT_UNKNOWN", "evidence": "ARCHIVE_EVENT_TIME_ONLY_NO_RECEIVER_CLOCKS"}
    okx_coverage = {}
    for family in FAMILY_IDENTITIES["okx"]:
        count = inside = 0
        first = last = previous = None
        for bar in bars(okx, family):
            require(previous is None or bar.t > previous, "OKX_SOURCE_ORDER_INVALID")
            if first is None:
                first = bar.t
            previous = last = bar.t
            count += 1
            inside += JULY_START <= bar.t < JULY_END
        okx_coverage[family] = {
            "rows": count, "rows_in_utc_july": inside, "first_utc_s": first, "last_utc_s": last,
            "file_day_timezone": "UTC+08:00", "epoch_shift_applied_s": 0,
            "leading_minutes_outside_utc_july": (JULY_START - first) // 60 if first is not None and first < JULY_START else 0,
            "trailing_minutes_missing_utc_july": (JULY_END - 60 - last) // 60 if last is not None and last < JULY_END - 60 else 0,
            "Z": "UNAVAILABLE_NO_OKX_POSITION_STOCK_ADAPTER",
        }
    inventory = {
        "mode": "HISTORICAL_OFFLINE_FEATURE_COVERAGE_ONLY", "labels": list(LABELS),
        "outcomes_evaluated": 0, "market_requests": 0, "ticks_l2_opened": 0,
        "window_utc_s": [JULY_START, JULY_END], "roots": [bmeta, ometa],
        "sources": [s.inventory() for s in binance + okx],
        "budget": {"compressed_bytes": budget.compressed, "expanded_bytes": budget.expanded,
                   "objects": budget.objects, "compressed_cap": budget.compressed_cap,
                   "expanded_cap": budget.expanded_cap}, "okx_coverage": okx_coverage,
    }
    return rows, inventory
