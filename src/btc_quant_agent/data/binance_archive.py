from __future__ import annotations

import csv
import hashlib
import importlib
import io
import json
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

from ..domain import Candle

ARCHIVE_ROOT = "https://data.binance.vision/data/futures/um/monthly"
KLINE_COLUMNS = (
    "open_time_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time_ms",
    "quote_volume",
    "trades",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "ignore",
)


def _months(start: datetime, end: datetime) -> list[tuple[int, int]]:
    if end <= start:
        return []
    cursor = datetime(start.year, start.month, 1, tzinfo=UTC)
    last_included = end - timedelta(microseconds=1)
    final = datetime(last_included.year, last_included.month, 1, tzinfo=UTC)
    output: list[tuple[int, int]] = []
    while cursor <= final:
        output.append((cursor.year, cursor.month))
        cursor = datetime(
            cursor.year + (1 if cursor.month == 12 else 0),
            1 if cursor.month == 12 else cursor.month + 1,
            1,
            tzinfo=UTC,
        )
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _download_verified(url: str, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    checksum_url = url + ".CHECKSUM"
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(checksum_url, timeout=60) as response:
                expected = str(response.read().decode("utf-8").split()[0])
            if not target.exists() or _sha256(target) != expected:
                temporary = target.with_suffix(target.suffix + ".part")
                temporary.unlink(missing_ok=True)
                with (
                    urllib.request.urlopen(url, timeout=120) as response,
                    temporary.open("wb") as handle,
                ):
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                if _sha256(temporary) != expected:
                    temporary.unlink(missing_ok=True)
                    raise ValueError(f"official archive checksum mismatch: {url}")
                temporary.replace(target)
            return expected
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def _zip_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise ValueError(f"expected one CSV in {path}")
        with archive.open(names[0]) as raw:
            rows = list(csv.reader(io.TextIOWrapper(raw, encoding="utf-8")))
    if rows and not rows[0][0].isdigit():
        rows = rows[1:]
    return rows


def _parse_klines(rows: list[list[str]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    invalid_ohlc = negative_volume = zero_volume = 0
    for row in rows:
        if len(row) < 12:
            raise ValueError("malformed Binance kline row")
        item = {
            "open_time_ms": int(row[0]),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "close_time_ms": int(row[6]),
            "quote_volume": float(row[7]),
            "trades": int(row[8]),
            "taker_buy_base_volume": float(row[9]),
        }
        invalid_ohlc += int(
            not (
                item["low"] <= item["open"] <= item["high"]
                and item["low"] <= item["close"] <= item["high"]
                and item["high"] >= item["low"]
            )
        )
        negative_volume += int(item["volume"] < 0)
        zero_volume += int(item["volume"] == 0)
        parsed.append(item)
    opens = [int(item["open_time_ms"]) for item in parsed]
    return parsed, {
        "invalid_ohlc": invalid_ohlc,
        "negative_volume": negative_volume,
        "zero_volume": zero_volume,
        "duplicates": len(opens) - len(set(opens)),
        "out_of_order": int(opens != sorted(opens)),
    }


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    pa = importlib.import_module("pyarrow")
    pq = importlib.import_module("pyarrow.parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")


def _read_mark_prices(path: Path) -> dict[int, float]:
    rows, _ = _parse_klines(_zip_rows(path))
    return {int(item["open_time_ms"]): float(item["open"]) for item in rows}


def build_official_dataset(
    root: str | Path,
    start: datetime,
    end: datetime,
    *,
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    if start.tzinfo != UTC or end.tzinfo != UTC:
        raise ValueError("research dataset boundaries must be UTC")
    if end <= start:
        raise ValueError("dataset end must follow start")
    target = Path(root)
    archive_checksums: dict[str, str] = {}
    parquet_checksums: dict[str, str] = {}
    all_opens: list[int] = []
    audit = {
        "invalid_ohlc": 0,
        "negative_volume": 0,
        "zero_volume": 0,
        "duplicates": 0,
        "out_of_order": 0,
    }
    funding_events: list[dict[str, Any]] = []
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    for year, month in _months(start, end):
        suffix = f"{year:04d}-{month:02d}"
        filename = f"{symbol}-1m-{suffix}.zip"
        kline_url = f"{ARCHIVE_ROOT}/klines/{symbol}/1m/{filename}"
        kline_archive = target / "raw" / "klines" / filename
        archive_checksums[kline_url] = _download_verified(kline_url, kline_archive)
        parsed, monthly_audit = _parse_klines(_zip_rows(kline_archive))
        parsed = [item for item in parsed if start_ms <= int(item["open_time_ms"]) < end_ms]
        for key in audit:
            audit[key] += int(monthly_audit[key])
        all_opens.extend(int(item["open_time_ms"]) for item in parsed)
        partition = target / "1m" / f"year={year:04d}" / f"month={month:02d}" / "data.parquet"
        _write_parquet(partition, parsed)
        parquet_checksums[str(partition.relative_to(target))] = _sha256(partition)

        funding_name = f"{symbol}-fundingRate-{suffix}.zip"
        funding_url = f"{ARCHIVE_ROOT}/fundingRate/{symbol}/{funding_name}"
        funding_archive = target / "raw" / "funding" / funding_name
        archive_checksums[funding_url] = _download_verified(funding_url, funding_archive)
        mark_url = f"{ARCHIVE_ROOT}/markPriceKlines/{symbol}/1m/{filename}"
        mark_archive = target / "raw" / "mark_price" / filename
        archive_checksums[mark_url] = _download_verified(mark_url, mark_archive)
        marks = _read_mark_prices(mark_archive)
        for row in _zip_rows(funding_archive):
            timestamp = int(row[0])
            if start_ms <= timestamp < end_ms:
                funding_events.append(
                    {
                        "timestamp_ms": timestamp,
                        "funding_rate": float(row[2]),
                        "mark_price": marks.get(timestamp),
                    }
                )

    all_opens.sort()
    gaps = [
        {"after_ms": previous, "before_ms": current, "missing": (current - previous) // 60_000 - 1}
        for previous, current in pairwise(all_opens)
        if current - previous != 60_000
    ]
    funding_events.sort(key=lambda item: int(item["timestamp_ms"]))
    funding_path = target / "funding_events.csv"
    with funding_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("timestamp_ms", "funding_rate", "mark_price"))
        writer.writeheader()
        writer.writerows(funding_events)
    expected = (end_ms - start_ms) // 60_000
    missing_count = expected - len(all_opens)
    dataset_digest = hashlib.sha256()
    for name, checksum in sorted(parquet_checksums.items()):
        dataset_digest.update(f"{name}:{checksum}\n".encode())
    dataset_digest.update(f"funding_events.csv:{_sha256(funding_path)}\n".encode())
    funding_timestamps = [int(item["timestamp_ms"]) for item in funding_events]
    manifest = {
        "source": "Binance Public Data, USD-M Futures monthly archives",
        "source_root": ARCHIVE_ROOT,
        "retrieved_at_ms": int(time.time() * 1000),
        "symbol": symbol,
        "market": "USD-M PERPETUAL",
        "timeframe": "1m",
        "timezone": "UTC",
        "start_ms": start_ms,
        "end_ms_exclusive": end_ms,
        "row_count": len(all_opens),
        "expected_bars": expected,
        "missing_count": missing_count,
        "duplicate_count": len(all_opens) - len(set(all_opens)),
        "out_of_order_count": audit["out_of_order"],
        "invalid_ohlc_count": audit["invalid_ohlc"],
        "negative_volume_count": audit["negative_volume"],
        "zero_volume_count": audit["zero_volume"],
        "largest_gap_missing_bars": max((int(gap["missing"]) for gap in gaps), default=0),
        "known_gaps": gaps,
        "synthetic_rows": 0,
        "checksum_sha256": dataset_digest.hexdigest(),
        "partition_checksums": parquet_checksums,
        "official_archive_checksums": archive_checksums,
        "funding": {
            "row_count": len(funding_events),
            "start_ms": funding_timestamps[0] if funding_timestamps else None,
            "end_ms": funding_timestamps[-1] if funding_timestamps else None,
            "duplicate_count": len(funding_timestamps) - len(set(funding_timestamps)),
            "missing_mark_prices": sum(item["mark_price"] is None for item in funding_events),
            "checksum_sha256": _sha256(funding_path),
            "mark_price_semantics": "official 1m mark-price candle open at settlement timestamp",
        },
    }
    (target / "data_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def read_parquet_candles(
    root: str | Path,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
    symbol: str = "BTCUSDT",
) -> list[Candle]:
    dataset_module = importlib.import_module("pyarrow.dataset")
    dataset = dataset_module.dataset(str(Path(root) / "1m"), format="parquet", partitioning="hive")
    expression = None
    if start_ms is not None:
        expression = dataset_module.field("open_time_ms") >= start_ms
    if end_ms is not None:
        upper = dataset_module.field("open_time_ms") < end_ms
        expression = upper if expression is None else expression & upper
    rows = dataset.to_table(filter=expression).to_pylist()
    return [
        Candle(
            symbol=symbol,
            interval="1m",
            open_time_ms=int(row["open_time_ms"]),
            close_time_ms=int(row["close_time_ms"]),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            quote_volume=float(row["quote_volume"]),
            taker_buy_base_volume=float(row["taker_buy_base_volume"]),
            trades=int(row["trades"]),
        )
        for row in rows
    ]


def candle_rows(candles: list[Candle]) -> list[dict[str, Any]]:
    return [asdict(candle) for candle in candles]
