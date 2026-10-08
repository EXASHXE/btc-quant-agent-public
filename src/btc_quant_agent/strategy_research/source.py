"""Typed in-memory source normalization and strict historical availability gates."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
MONTHS = ("2026-05", "2026-06", "2026-07", "2026-08")
MINUTE = 60_000
HOUR = 60 * MINUTE
VERSION = "G2_SOURCE_V1"


class SourceError(ValueError):
    """Invalid provenance, availability, identity or minute coverage."""


def archive_url(symbol: str, month: str) -> str:
    # Validate before constructing a URL, opening any path or issuing a request.
    if symbol not in SYMBOLS or month not in MONTHS:
        raise SourceError("UNREGISTERED_SOURCE")
    return (
        f"https://data.binance.vision/data/spot/monthly/klines/{symbol}/1m/{symbol}-1m-{month}.zip"
    )


def digest(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass(frozen=True)
class SourceManifest:
    symbol: str
    origin: str
    origin_sha256: str
    receipt_ms: int
    purpose: str
    availability_basis: str
    market_type: str = "SPOT"
    version: str = VERSION

    def __post_init__(self) -> None:
        if self.symbol not in SYMBOLS or self.market_type != "SPOT":
            raise SourceError("UNREGISTERED_MARKET_OR_SYMBOL")
        if self.version != VERSION or type(self.receipt_ms) is not int or self.receipt_ms < 0:
            raise SourceError("INVALID_SOURCE_VERSION_OR_RECEIPT")
        if len(self.origin_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.origin_sha256
        ):
            raise SourceError("INVALID_DIGEST")
        if self.purpose == "SYNTHETIC_UNIT_TEST":
            if (
                self.origin != "synthetic://g2-unit-test"
                or self.availability_basis != "SYNTHETIC_TEST"
            ):
                raise SourceError("INVALID_SYNTHETIC_PROVENANCE")
        elif self.purpose == "HISTORICAL_DEVELOPMENT":
            if self.origin not in {archive_url(self.symbol, m) for m in MONTHS}:
                raise SourceError("UNREGISTERED_ORIGIN")
            if self.availability_basis != "ARCHIVE_RECEIPT_ONLY":
                raise SourceError("ARCHIVE_CANNOT_PROVE_CONTEMPORANEOUS_RECEIPT")
        else:
            # A new contemporaneous fixture source needs separate manifest authority.
            raise SourceError("UNKNOWN_SOURCE_PERMISSION")

    @property
    def identity(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class Bar:
    symbol: str
    event_ms: int
    end_ms: int  # exclusive
    receipt_ms: int
    available_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    quote_volume: Decimal
    source_identity: str
    availability_basis: str

    def __post_init__(self) -> None:
        times = (self.event_ms, self.end_ms, self.receipt_ms, self.available_ms)
        if self.symbol not in SYMBOLS or any(type(t) is not int for t in times):
            raise SourceError("INVALID_BAR_IDENTITY")
        if not (0 <= self.event_ms < self.end_ms <= self.receipt_ms <= self.available_ms):
            raise SourceError("INVALID_EVENT_RECEIPT_ORDER")
        values = (self.open, self.high, self.low, self.close, self.quote_volume)
        if any(not v.is_finite() for v in values):
            raise SourceError("NONFINITE_BAR")
        if not (
            0 < self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high
        ):
            raise SourceError("INVALID_OHLC")
        if self.quote_volume < 0 or len(self.source_identity) != 64:
            raise SourceError("INVALID_VOLUME_OR_SOURCE")
        if self.availability_basis not in {"ARCHIVE_RECEIPT_ONLY", "SYNTHETIC_TEST"}:
            raise SourceError("UNKNOWN_AVAILABILITY")


def normalize_csv(data: bytes, manifest: SourceManifest) -> tuple[Bar, ...]:
    """Normalize supplied bytes only; never locate, download or open a source."""
    if hashlib.sha256(data).hexdigest() != manifest.origin_sha256:
        raise SourceError("SOURCE_DIGEST_CHANGED")
    bars = []
    for row in csv.reader(io.StringIO(data.decode("utf-8"))):
        if len(row) != 12:
            raise SourceError("INVALID_ARCHIVE_ROW")
        start_us, close_us = int(row[0]), int(row[6])
        if start_us % 60_000_000 or close_us != start_us + 60_000_000 - 1:
            raise SourceError("INVALID_MICROSECOND_CALENDAR")
        start = start_us // 1000
        end = start + MINUTE
        receipt = end if manifest.purpose == "SYNTHETIC_UNIT_TEST" else manifest.receipt_ms
        bars.append(
            Bar(
                manifest.symbol,
                start,
                end,
                receipt,
                receipt,
                Decimal(row[1]),
                Decimal(row[2]),
                Decimal(row[3]),
                Decimal(row[4]),
                Decimal(row[7]),
                manifest.identity,
                manifest.availability_basis,
            )
        )
    return canonical_minutes(bars)


def canonical_minutes(bars: Iterable[Bar]) -> tuple[Bar, ...]:
    result = tuple(sorted(bars, key=lambda b: (b.symbol, b.event_ms)))
    keys: set[tuple[str, int]] = set()
    for b in result:
        if b.event_ms % MINUTE or b.end_ms - b.event_ms != MINUTE:
            raise SourceError("NOT_ALIGNED_1M")
        key = b.symbol, b.event_ms
        if key in keys:
            raise SourceError("DUPLICATE_MINUTE_IDENTITY")
        keys.add(key)
    return result


def complete_window(bars: Iterable[Bar], symbol: str, start: int, end: int) -> tuple[Bar, ...]:
    if symbol not in SYMBOLS or start % MINUTE or end % MINUTE or end <= start:
        raise SourceError("INVALID_WINDOW")
    selected = canonical_minutes(
        b for b in bars if b.symbol == symbol and start <= b.event_ms < end
    )
    if len(selected) != (end - start) // MINUTE or any(
        b.event_ms != start + i * MINUTE for i, b in enumerate(selected)
    ):
        raise SourceError("MISSING_1M_NO_FILLER")
    return selected


def hourly(bars: Iterable[Bar], symbol: str, start: int, end: int) -> tuple[Bar, ...]:
    if start % HOUR or end % HOUR:
        raise SourceError("INVALID_HOUR_ALIGNMENT")
    minutes = complete_window(bars, symbol, start, end)
    result = []
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)) as arithmetic:
        arithmetic.prec = 28
        for offset in range(0, len(minutes), 60):
            rows = minutes[offset : offset + 60]
            if len({r.availability_basis for r in rows}) != 1:
                raise SourceError("MIXED_AVAILABILITY")
            result.append(
                Bar(
                    symbol,
                    rows[0].event_ms,
                    rows[-1].end_ms,
                    max(r.receipt_ms for r in rows),
                    max(r.available_ms for r in rows),
                    rows[0].open,
                    max(r.high for r in rows),
                    min(r.low for r in rows),
                    rows[-1].close,
                    sum((r.quote_volume for r in rows), Decimal(0)),
                    digest(sorted({r.source_identity for r in rows})),
                    rows[0].availability_basis,
                )
            )
    return tuple(result)


def require_available(bars: Iterable[Bar], decision_ms: int, *, synthetic_test: bool) -> None:
    for b in bars:
        if b.end_ms > decision_ms or b.available_ms > decision_ms:
            raise SourceError("PIT_LATE_OR_FUTURE_INPUT")
        if not synthetic_test or b.availability_basis != "SYNTHETIC_TEST":
            raise SourceError("CONTEMPORANEOUS_RECEIPT_NOT_PROVEN")
