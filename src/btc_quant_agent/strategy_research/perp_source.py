"""Verified allowlisted Binance USDT-M archival inputs; never live PIT evidence."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Any

D = Decimal
MINUTE = 60_000
HOUR = 60 * MINUTE
DAY = 24 * HOUR
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
MONTHS = ("2026-04", "2026-05", "2026-06", "2026-07")
GRADE = "ARCHIVAL_EVENT_TIME_RECONSTRUCTED"
CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)


class SourceError(ValueError):
    """Invalid source, registry, checksum, clock or coverage; fail closed."""


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def epoch(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp()) * 1000


def month_bounds(month: str) -> tuple[int, int]:
    if month not in MONTHS:
        raise SourceError("UNREGISTERED_MONTH")
    year, m = map(int, month.split("-"))
    start = datetime(year, m, 1, tzinfo=UTC)
    end = datetime(year + (m == 12), m % 12 + 1, 1, tzinfo=UTC)
    return int(start.timestamp()) * 1000, int(end.timestamp()) * 1000


def source_url(kind: str, symbol: str, month: str) -> str:
    if symbol not in SYMBOLS or month not in MONTHS or kind not in {"price", "funding"}:
        raise SourceError("UNREGISTERED_SOURCE_BEFORE_ACCESS")
    if kind == "funding" and month == "2026-04":
        raise SourceError("UNREGISTERED_FUNDING_WINDOW")
    suffix = (
        f"klines/{symbol}/1m/{symbol}-1m-{month}.zip"
        if kind == "price"
        else (f"fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip")
    )
    return "https://data.binance.vision/data/futures/um/monthly/" + suffix


def verified_csv(archive: bytes, checksum: bytes, expected_name: str) -> bytes:
    parts = checksum.decode("ascii").strip().split()
    if len(parts) != 2 or parts[1].lstrip("*") != expected_name:
        raise SourceError("OFFICIAL_CHECKSUM_IDENTITY")
    if hashlib.sha256(archive).hexdigest() != parts[0]:
        raise SourceError("ARCHIVE_CHECKSUM_CHANGED")
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        names = z.namelist()
        expected_csv = expected_name.removesuffix(".zip") + ".csv"
        if names != [expected_csv] or z.getinfo(names[0]).file_size > 50_000_000:
            raise SourceError("UNCLASSIFIABLE_ARCHIVE_MEMBER")
        return z.read(names[0])


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    t: int
    end: int
    o: Decimal
    h: Decimal
    l: Decimal
    c: Decimal
    qv: Decimal
    source: str
    grade: str = GRADE
    lag: int = MINUTE

    def __post_init__(self) -> None:
        if self.symbol not in SYMBOLS or self.grade not in {GRADE, "SYNTHETIC_TEST"}:
            raise SourceError("UNKNOWN_SYMBOL_OR_GRADE")
        if type(self.t) is not int or type(self.end) is not int or self.t < 0 or self.end <= self.t:
            raise SourceError("INVALID_CLOCK")
        if self.lag != MINUTE or len(self.source) != 64:
            raise SourceError("INVALID_AVAILABILITY_OR_LINEAGE")
        if any(not x.is_finite() for x in (self.o, self.h, self.l, self.c, self.qv)):
            raise SourceError("NONFINITE_ROW")
        if not (0 < self.l <= min(self.o, self.c) <= max(self.o, self.c) <= self.h) or self.qv < 0:
            raise SourceError("CORRUPT_OHLCV")

    @property
    def available(self) -> int:
        return self.end + self.lag


def canonical(bars: list[Bar] | tuple[Bar, ...], *, strict: bool = True) -> tuple[Bar, ...]:
    result = tuple(sorted(bars, key=lambda b: b.t))
    if not result or len({b.symbol for b in result}) != 1:
        raise SourceError("EMPTY_OR_MIXED_SYMBOL")
    for i, b in enumerate(result):
        if b.t % MINUTE or b.end != b.t + MINUTE:
            raise SourceError("NOT_1M_CALENDAR")
        if i and b.t == result[i - 1].t:
            raise SourceError("DUPLICATE_BAR")
        if strict and i and b.t != result[i - 1].end:
            raise SourceError("MISSING_1M_NO_FILLER")
    return result


def parse_prices(raw: bytes, symbol: str, month: str) -> tuple[Bar, ...]:
    source_url("price", symbol, month)
    start, end = month_bounds(month)
    sha = hashlib.sha256(raw).hexdigest()
    rows = list(csv.reader(io.StringIO(raw.decode())))
    if rows and rows[0][0] == "open_time":
        rows = rows[1:]
    bars = []
    for r in rows:
        if len(r) != 12:
            raise SourceError("INVALID_KLINE_SHAPE")
        t = int(r[0])
        if int(r[6]) != t + MINUTE - 1 or not start <= t < end:
            raise SourceError("WRONG_TIMESTAMP_UNIT_MONTH_OR_CLOSE")
        bars.append(Bar(symbol, t, t + MINUTE, D(r[1]), D(r[2]), D(r[3]), D(r[4]), D(r[7]), sha))
    result = canonical(bars)
    if result[0].t != start or result[-1].end != end or len(result) != (end - start) // MINUTE:
        raise SourceError("INCOMPLETE_MONTH")
    return result


def resample(bars: tuple[Bar, ...], minutes: int) -> tuple[Bar, ...]:
    if minutes not in {1, 15, 60, 240}:
        raise SourceError("UNREGISTERED_TIMEFRAME")
    rows = canonical(bars)
    span = minutes * MINUTE
    if rows[0].t % span or rows[-1].end % span:
        raise SourceError("RESAMPLE_EPOCH_ALIGNMENT")
    result = []
    with localcontext(CONTEXT):
        for i in range(0, len(rows), minutes):
            block = rows[i : i + minutes]
            if len(block) != minutes or len({b.grade for b in block}) != 1:
                raise SourceError("MISSING_OR_MIXED_RESAMPLE")
            result.append(
                Bar(
                    block[0].symbol,
                    block[0].t,
                    block[-1].end,
                    block[0].o,
                    max(b.h for b in block),
                    min(b.l for b in block),
                    block[-1].c,
                    sum((b.qv for b in block), D(0)),
                    digest(sorted({b.source for b in block})),
                    block[0].grade,
                )
            )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class Funding:
    t: int
    interval: Decimal
    rate: Decimal


def parse_funding(raw: bytes, symbol: str, month: str) -> tuple[Funding, ...]:
    source_url("funding", symbol, month)
    start, end = month_bounds(month)
    reader = csv.DictReader(io.StringIO(raw.decode()))
    if set(reader.fieldnames or ()) != {"calc_time", "funding_interval_hours", "last_funding_rate"}:
        raise SourceError("UNKNOWN_FUNDING_SCHEMA")
    result = tuple(
        sorted(
            (
                Funding(
                    int(r["calc_time"]), D(r["funding_interval_hours"]), D(r["last_funding_rate"])
                )
                for r in reader
            ),
            key=lambda f: f.t,
        )
    )
    if any(
        not start <= f.t < end
        or not f.rate.is_finite()
        or not f.interval.is_finite()
        or not 0 < f.interval <= 8
        for f in result
    ):
        raise SourceError("INVALID_FUNDING_EVENT")
    if len({f.t for f in result}) != len(result):
        raise SourceError("DUPLICATE_FUNDING")
    return result


def funding_complete(rows: tuple[Funding, ...], start: int, end: int) -> bool:
    return (
        bool(rows)
        and rows[0].t == start
        and end - rows[-1].t <= int(rows[-1].interval * HOUR)
        and all(
            rows[i].t - rows[i - 1].t == int(rows[i].interval * HOUR) for i in range(1, len(rows))
        )
    )


def validate_manifest(records: list[dict[str, Any]], first_push_utc: str) -> None:
    expected = {
        source_url(k, s, m)
        for k in ("price", "funding")
        for s in SYMBOLS
        for m in (MONTHS if k == "price" else MONTHS[1:])
    }
    if len(records) != 21 or {r["url"] for r in records} != expected:
        raise SourceError("MANIFEST_SOURCE_SET_CHANGED")
    first = datetime.fromisoformat(first_push_utc)
    for r in records:
        if r["url"] != source_url(r["kind"], r["symbol"], r["month"]) or (
            r["market_type"] != "USDT_M_PERPETUAL_FUTURES"
            or r["grade"] != GRADE
            or r["exposure"] != "PRIOR_EXPOSED_OR_DEVELOPMENT"
        ):
            raise SourceError("MANIFEST_PRODUCT_PROVENANCE_CHANGED")
        if datetime.fromisoformat(r["retrieved_utc"]) < first:
            raise SourceError("OUTCOMES_BEFORE_FIRST_PUSH")
        if r["status"] != 200:
            if r["kind"] != "funding" or r["status"] != 404:
                raise SourceError("UNAVAILABLE_PRICE_OR_RATE_LIMIT")
            continue
        for key in ("archive_sha256", "csv_sha256", "checksum_sha256"):
            value = r[key]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise SourceError("INVALID_SOURCE_DIGEST")
