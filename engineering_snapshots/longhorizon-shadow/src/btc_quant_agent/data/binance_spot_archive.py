from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any

from .binance_archive import _download_verified, _months, _sha256, _write_parquet, _zip_rows

SPOT_ARCHIVE_ROOT = "https://data.binance.vision/data/spot/monthly/klines"
MICROSECOND_THRESHOLD = 10**15


def normalize_archive_timestamp(value: str | int) -> tuple[int, str]:
    """Normalize Binance archive timestamps to milliseconds without guessing by date."""
    timestamp = int(value)
    if timestamp < 0:
        raise ValueError("archive timestamp must be non-negative")
    if timestamp >= MICROSECOND_THRESHOLD:
        return timestamp // 1_000, "microseconds"
    return timestamp, "milliseconds"


def parse_spot_flow_rows(
    rows: Sequence[Sequence[str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    units: Counter[str] = Counter()
    invalid_volume = zero_volume = 0
    for row in rows:
        if len(row) < 12:
            raise ValueError("malformed Binance spot kline row")
        open_time_ms, open_unit = normalize_archive_timestamp(row[0])
        close_time_ms, close_unit = normalize_archive_timestamp(row[6])
        units.update((open_unit, close_unit))
        volume = float(row[5])
        taker_buy = float(row[9])
        invalid_volume += int(volume < 0 or taker_buy < 0 or taker_buy > volume + 1e-9)
        zero_volume += int(volume == 0)
        parsed.append(
            {
                "open_time_ms": open_time_ms,
                "close_time_ms": close_time_ms,
                "volume": volume,
                "taker_buy_base_volume": taker_buy,
            }
        )
    opens = [int(row["open_time_ms"]) for row in parsed]
    return parsed, {
        "invalid_volume": invalid_volume,
        "zero_volume": zero_volume,
        "duplicates": len(opens) - len(set(opens)),
        "out_of_order": int(opens != sorted(opens)),
        "timestamp_value_units": dict(sorted(units.items())),
    }


def _dataset_checksum(partition_checksums: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name, checksum in sorted(partition_checksums.items()):
        digest.update(f"{name}:{checksum}\n".encode())
    return digest.hexdigest()


def build_spot_market_flow_dataset(
    root: str | Path,
    start: datetime,
    end: datetime,
    *,
    symbol: str = "BTCUSDT",
) -> dict[str, Any]:
    if start.tzinfo != UTC or end.tzinfo != UTC:
        raise ValueError("spot research dataset boundaries must be UTC")
    if end <= start:
        raise ValueError("spot dataset end must follow start")
    target = Path(root)
    start_ms = int(start.timestamp() * 1_000)
    end_ms = int(end.timestamp() * 1_000)
    archive_checksums: dict[str, str] = {}
    partition_checksums: dict[str, str] = {}
    timestamps: list[int] = []
    audit: Counter[str] = Counter()
    timestamp_units: Counter[str] = Counter()
    monthly_rows: dict[str, int] = {}
    for year, month in _months(start, end):
        suffix = f"{year:04d}-{month:02d}"
        filename = f"{symbol}-1m-{suffix}.zip"
        url = f"{SPOT_ARCHIVE_ROOT}/{symbol}/1m/{filename}"
        archive = target / "raw" / "klines" / filename
        archive_checksums[url] = _download_verified(url, archive)
        parsed, month_audit = parse_spot_flow_rows(_zip_rows(archive))
        selected = [row for row in parsed if start_ms <= int(row["open_time_ms"]) < end_ms]
        monthly_rows[suffix] = len(selected)
        timestamps.extend(int(row["open_time_ms"]) for row in selected)
        for key in ("invalid_volume", "zero_volume", "duplicates", "out_of_order"):
            audit[key] += int(month_audit[key])
        timestamp_units.update(month_audit["timestamp_value_units"])
        partition = target / "1m" / f"year={year:04d}" / f"month={month:02d}" / "data.parquet"
        _write_parquet(partition, selected)
        partition_checksums[str(partition.relative_to(target))] = _sha256(partition)

    ordered = sorted(timestamps)
    gaps = [
        {
            "after_ms": left,
            "before_ms": right,
            "missing": (right - left) // 60_000 - 1,
        }
        for left, right in pairwise(ordered)
        if right - left != 60_000
    ]
    expected = (end_ms - start_ms) // 60_000
    manifest = {
        "dataset_id": "BTCUSDT_SPOT_1M_BINANCE_V0312_DEV_20210101_20260201",
        "source": "Binance Public Data, Spot monthly kline archives",
        "source_root": SPOT_ARCHIVE_ROOT,
        "retrieved_at_ms": int(time.time() * 1_000),
        "symbol": symbol,
        "market": "SPOT",
        "timeframe": "1m",
        "timezone": "UTC",
        "start_ms": start_ms,
        "end_ms_exclusive": end_ms,
        "row_count": len(ordered),
        "expected_bars": expected,
        "missing_count": expected - len(ordered),
        "duplicate_count": len(ordered) - len(set(ordered)),
        "out_of_order_count": int(audit["out_of_order"]),
        "invalid_volume_count": int(audit["invalid_volume"]),
        "zero_volume_count": int(audit["zero_volume"]),
        "largest_gap_missing_bars": max((int(row["missing"]) for row in gaps), default=0),
        "known_gaps": gaps,
        "synthetic_rows": 0,
        "timestamp_normalization": {
            "rule": "values >= 10^15 are integer-divided by 1000; smaller values are milliseconds",
            "normalized_unit": "milliseconds",
            "source_value_counts": dict(sorted(timestamp_units.items())),
        },
        "columns": [
            "open_time_ms",
            "close_time_ms",
            "volume",
            "taker_buy_base_volume",
        ],
        "monthly_row_counts": monthly_rows,
        "checksum_sha256": _dataset_checksum(partition_checksums),
        "partition_checksums": partition_checksums,
        "official_archive_checksums": archive_checksums,
    }
    target.mkdir(parents=True, exist_ok=True)
    (target / "data_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def read_spot_flow_rows(
    root: str | Path,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> list[dict[str, Any]]:
    import importlib

    dataset_module = importlib.import_module("pyarrow.dataset")
    dataset = dataset_module.dataset(str(Path(root) / "1m"), format="parquet", partitioning="hive")
    expression = None
    if start_ms is not None:
        expression = dataset_module.field("open_time_ms") >= start_ms
    if end_ms is not None:
        upper = dataset_module.field("open_time_ms") < end_ms
        expression = upper if expression is None else expression & upper
    rows = dataset.to_table(filter=expression).to_pylist()
    return sorted(
        (
            {
                "open_time_ms": int(row["open_time_ms"]),
                "close_time_ms": int(row["close_time_ms"]),
                "volume": float(row["volume"]),
                "taker_buy_base_volume": float(row["taker_buy_base_volume"]),
            }
            for row in rows
        ),
        key=lambda row: int(row["open_time_ms"]),
    )
