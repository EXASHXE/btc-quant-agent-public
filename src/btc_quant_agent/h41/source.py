"""Same-buffer native Binance USD-M 1h source parsing and projection.

This module does not fetch archives.  Accepted archive digests are frozen
metadata; a later authorized run must supply matching local bytes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .authority import SOURCE_BINDING, canonical_json
from .science import HOUR_MS, CompletedBar, CompletedPairView

OFFICIAL_ROOT = "https://data.binance.vision/data/futures/um/monthly/klines"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
_MONTH = re.compile(r"20[0-9]{2}-(?:0[1-9]|1[0-2])\Z")


def _number(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("malformed numeric source field") from exc
    if not value.is_finite():
        raise ValueError("nonfinite numeric source field")
    return value


def canonical_number(value: Decimal) -> str:
    """Exact source-closure numeric representation, including signed zero."""
    return format(value.normalize(), "f") if value else "0"


def _bounds(month: str) -> tuple[int, int]:
    if _MONTH.fullmatch(month) is None:
        raise ValueError("invalid UTC archive month")
    year, number = map(int, month.split("-"))
    start = datetime(year, number, 1, tzinfo=UTC)
    end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=UTC)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


@dataclass(frozen=True, slots=True, repr=False)
class EconomicBar:
    symbol: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal
    trades: int
    taker_buy_base_volume: Decimal
    taker_buy_quote_volume: Decimal

    def projection(self) -> dict[str, str | int]:
        return {
            "symbol": self.symbol, "market": "USD-M PERPETUAL", "interval": "1h",
            "open_time_ms": self.open_time_ms, "close_time_ms": self.close_time_ms,
            "open": canonical_number(self.open), "high": canonical_number(self.high),
            "low": canonical_number(self.low), "close": canonical_number(self.close),
            "volume": canonical_number(self.volume),
            "quote_volume": canonical_number(self.quote_volume), "trades": self.trades,
            "taker_buy_base_volume": canonical_number(self.taker_buy_base_volume),
            "taker_buy_quote_volume": canonical_number(self.taker_buy_quote_volume),
        }

    def completed(self) -> CompletedBar:
        return CompletedBar(self.open_time_ms, float(self.high), float(self.low),
                            float(self.close))


@dataclass(frozen=True, slots=True, repr=False)
class ParsedArchive:
    symbol: str
    month: str
    archive_sha256: str
    raw_csv_sha256: str
    projection_sha256: str
    timestamp_membership_sha256: str
    bars: tuple[EconomicBar, ...]


def _parse_archive(path: Path, symbol: str, month: str, expected_sha256: str,
                   *, require_full_month: bool) -> ParsedArchive:
    if symbol not in SYMBOLS:
        raise ValueError("unsupported symbol")
    expected_name = f"{symbol}-1h-{month}.zip"
    if path.is_symlink() or not path.is_file() or path.name != expected_name:
        raise ValueError("wrong native archive path, product, or symbol")
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValueError("missing archive checksum")
    archive_bytes = path.read_bytes()
    archive_hash = hashlib.sha256(archive_bytes).hexdigest()
    if archive_hash != expected_sha256:
        raise ValueError("archive checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if len(members) != 1 or members[0].filename != f"{symbol}-1h-{month}.csv":
            raise ValueError("archive member does not match native kline identity")
        csv_bytes = archive.read(members[0])
    try:
        rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    except UnicodeDecodeError as exc:
        raise ValueError("invalid archive encoding") from exc
    if rows and not rows[0][0].isdigit():
        rows = rows[1:]
    lower, upper = _bounds(month)
    bars: list[EconomicBar] = []
    projection = hashlib.sha256()
    for row in rows:
        if len(row) != 12:
            raise ValueError("malformed Binance USD-M kline row")
        try:
            t, close_t, trades = int(row[0]), int(row[6]), int(row[8])
        except ValueError as exc:
            raise ValueError("malformed kline timestamp or trade count") from exc
        if not lower <= t < upper or t % HOUR_MS or close_t != t + HOUR_MS - 1:
            raise ValueError("timestamp, UTC alignment, or finalization mismatch")
        prices = tuple(_number(row[i]) for i in (1, 2, 3, 4))
        volumes = tuple(_number(row[i]) for i in (5, 7, 9, 10))
        op, hi, lo, cl = prices
        if not (lo > 0 and lo <= op <= hi and lo <= cl <= hi):
            raise ValueError("invalid OHLC row")
        if trades < 0 or any(value < 0 for value in volumes):
            raise ValueError("invalid volume or trade row")
        if bars and t != bars[-1].open_time_ms + HOUR_MS:
            raise ValueError("duplicate, unsorted, or missing source hour")
        bar = EconomicBar(symbol, t, close_t, op, hi, lo, cl,
                          volumes[0], volumes[1], trades, volumes[2], volumes[3])
        projection.update(canonical_json(bar.projection()) + b"\n")
        bars.append(bar)
    if not bars:
        raise ValueError("empty source archive")
    if require_full_month and (bars[0].open_time_ms != lower
                               or bars[-1].open_time_ms != upper - HOUR_MS):
        raise ValueError("incomplete native monthly archive")
    timestamps = [bar.open_time_ms for bar in bars]
    return ParsedArchive(symbol, month, archive_hash, hashlib.sha256(csv_bytes).hexdigest(),
                         projection.hexdigest(), hashlib.sha256(canonical_json(timestamps)).hexdigest(),
                         tuple(bars))


def load_synthetic_archive(path: Path, symbol: str, month: str,
                           checksum_sha256: str) -> ParsedArchive:
    """Exercise exact parser/projection on explicitly synthetic local bytes."""
    return _parse_archive(path, symbol, month, checksum_sha256, require_full_month=False)


def load_accepted_archive(path: Path, symbol: str, month: str) -> ParsedArchive:
    """Future read path, pinned to the accepted official archive record."""
    asset = symbol.removesuffix("USDT")
    records = SOURCE_BINDING["archive_records"].get(asset)
    if records is None:
        raise ValueError("source asset absent from accepted authority")
    name = f"{symbol}-1h-{month}.zip"
    record = next((row for row in records if row["archive_name"] == name), None)
    if record is None:
        raise ValueError("archive absent from accepted authority")
    expected_url = f"{OFFICIAL_ROOT}/{symbol}/1h/{name}"
    if (record["archive_url"] != expected_url
            or record["official_checksum_url"] != expected_url + ".CHECKSUM"
            or record["official_archive_checksum"] != record["local_archive_sha256"]):
        raise ValueError("accepted archive record product or checksum mismatch")
    result = _parse_archive(path, symbol, month, record["official_archive_checksum"],
                            require_full_month=True)
    if (result.raw_csv_sha256 != record["raw_csv_sha256"]
            or result.projection_sha256 != record["canonical_projection_hash"]
            or result.timestamp_membership_sha256 != record["timestamp_membership_hash"]
            or len(result.bars) != record["row_count"]):
        raise ValueError("accepted economic row projection mismatch")
    return result


@dataclass(frozen=True, slots=True, repr=False)
class SynchronizedSource:
    """Economic rows retained separately from completed feature views."""

    btc: tuple[EconomicBar, ...]
    eth: tuple[EconomicBar, ...]

    def __post_init__(self) -> None:
        if len(self.btc) != len(self.eth) or not self.btc:
            raise ValueError("missing synchronized source")
        for i, (btc, eth) in enumerate(zip(self.btc, self.eth, strict=True)):
            if btc.symbol != "BTCUSDT" or eth.symbol != "ETHUSDT":
                raise ValueError("source symbol contamination")
            if btc.open_time_ms != eth.open_time_ms:
                raise ValueError("BTC/ETH timestamp membership mismatch")
            if i and btc.open_time_ms != self.btc[i - 1].open_time_ms + HOUR_MS:
                raise ValueError("source gap or duplicate")

    def completed_view(self, decision_time_ms: int, lookback: int) -> CompletedPairView:
        first = self.btc[0].open_time_ms
        offset = (decision_time_ms - first) // HOUR_MS
        if decision_time_ms % HOUR_MS or offset < lookback + 1 or offset > len(self.btc):
            raise ValueError("incomplete completed-bar history")
        btc = tuple(bar.completed() for bar in reversed(self.btc[offset - lookback - 1:offset]))
        eth = tuple(bar.completed() for bar in reversed(self.eth[offset - lookback - 1:offset]))
        return CompletedPairView(decision_time_ms, btc, eth)

    def open_at(self, symbol: str, open_time_ms: int) -> Decimal:
        bars = self.btc if symbol == "BTCUSDT" else self.eth if symbol == "ETHUSDT" else None
        if bars is None:
            raise ValueError("unknown source symbol")
        first = bars[0].open_time_ms
        offset = (open_time_ms - first) // HOUR_MS
        if (open_time_ms % HOUR_MS or offset < 0 or offset >= len(bars)
                or bars[offset].open_time_ms != open_time_ms):
            raise ValueError("missing reference Open")
        return bars[offset].open


def projection_sha256(archives: tuple[ParsedArchive, ...]) -> str:
    """Replay the source audit's newline-delimited 14-field row projection."""
    digest = hashlib.sha256()
    for archive in archives:
        for bar in archive.bars:
            digest.update(canonical_json(bar.projection()) + b"\n")
    return digest.hexdigest()


def verify_accepted_projection(archives: tuple[ParsedArchive, ...], symbol: str) -> None:
    asset = symbol.removesuffix("USDT")
    if any(archive.symbol != symbol for archive in archives):
        raise ValueError("cross-symbol archive")
    if projection_sha256(archives) != SOURCE_BINDING["projection_hashes"][asset]:
        raise ValueError("accepted full-range projection mismatch")


def load_accepted_pair(archive_root: Path) -> SynchronizedSource:
    """Future read path for the exact accepted 28-month BTC/ETH source pair.

    Caller authorization belongs to the later execution stage.  This function
    is exercised only with synthetic data in the implementation stage.
    """
    if archive_root.is_symlink() or not archive_root.is_dir():
        raise ValueError("archive root must be a real directory")
    loaded: dict[str, tuple[EconomicBar, ...]] = {}
    for asset in ("BTC", "ETH"):
        symbol = f"{asset}USDT"
        symbol_dir = archive_root / symbol
        if symbol_dir.is_symlink() or not symbol_dir.is_dir():
            raise ValueError("symbol archive directory must be real")
        records = SOURCE_BINDING["archive_records"][asset]
        archives = tuple(load_accepted_archive(symbol_dir / row["archive_name"], symbol,
                                               row["archive_name"][-11:-4])
                         for row in records)
        verify_accepted_projection(archives, symbol)
        bars = tuple(bar for archive in archives for bar in archive.bars)
        timestamps = [bar.open_time_ms for bar in bars]
        if (len(bars) != 20_400
                or timestamps[0] != 1_609_459_200_000
                or timestamps[-1] != 1_682_895_600_000
                or hashlib.sha256(canonical_json(timestamps)).hexdigest()
                != SOURCE_BINDING["membership_hashes"][asset]):
            raise ValueError("accepted full-range timestamp membership mismatch")
        loaded[asset] = bars
    return SynchronizedSource(loaded["BTC"], loaded["ETH"])
