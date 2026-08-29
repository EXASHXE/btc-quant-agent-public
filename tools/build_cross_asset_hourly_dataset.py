from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from btc_quant_agent.data.binance_archive import (
    ARCHIVE_ROOT,
    _download_verified,
    _parse_klines,
    _sha256,
    _write_parquet,
    _zip_rows,
)

BASKET = ("ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "LTCUSDT")


def months(start: datetime, end: datetime) -> list[str]:
    output: list[str] = []
    year, month = start.year, start.month
    while (year, month) < (end.year, end.month):
        output.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/research/cross_asset_1h")
    args = parser.parse_args()
    root = Path(args.output)
    start = datetime(2021, 1, 1, tzinfo=UTC)
    end = datetime(2026, 2, 1, tzinfo=UTC)
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    manifest: dict[str, object] = {
        "source": "Binance Public Data, USD-M Futures monthly 1h kline archives",
        "source_root": ARCHIVE_ROOT,
        "retrieved_at_ms": int(time.time() * 1000),
        "timeframe": "1h",
        "start_ms": start_ms,
        "end_ms_exclusive": end_ms,
        "basket": list(BASKET),
        "symbols": {},
    }
    symbols = manifest["symbols"]
    assert isinstance(symbols, dict)
    for symbol in BASKET:
        all_rows: list[dict[str, object]] = []
        checksums: dict[str, str] = {}
        audit = {
            "invalid_ohlc": 0,
            "negative_volume": 0,
            "zero_volume": 0,
            "duplicates": 0,
            "out_of_order": 0,
        }
        for suffix in months(start, end):
            filename = f"{symbol}-1h-{suffix}.zip"
            url = f"{ARCHIVE_ROOT}/klines/{symbol}/1h/{filename}"
            archive = root / "raw" / symbol / filename
            checksums[url] = _download_verified(url, archive)
            rows, block = _parse_klines(_zip_rows(archive))
            all_rows.extend(row for row in rows if start_ms <= int(row["open_time_ms"]) < end_ms)
            for key in audit:
                audit[key] += int(block[key])
        all_rows.sort(key=lambda row: int(row["open_time_ms"]))
        opens = [int(row["open_time_ms"]) for row in all_rows]
        gaps = [
            {"after_ms": left, "before_ms": right, "missing": (right - left) // 3_600_000 - 1}
            for left, right in pairwise(opens)
            if right - left != 3_600_000
        ]
        path = root / f"{symbol}.parquet"
        _write_parquet(path, all_rows)
        digest = hashlib.sha256(
            "\n".join(f"{key}:{value}" for key, value in sorted(checksums.items())).encode()
        ).hexdigest()
        symbols[symbol] = {
            "first_open_ms": opens[0],
            "last_open_ms": opens[-1],
            "expected_rows": (end_ms - start_ms) // 3_600_000,
            "actual_rows": len(opens),
            "missing_count": (end_ms - start_ms) // 3_600_000 - len(opens),
            "gaps": gaps,
            "duplicates": len(opens) - len(set(opens)),
            "invalid_ohlc": audit["invalid_ohlc"],
            "negative_volume": audit["negative_volume"],
            "zero_volume": audit["zero_volume"],
            "parquet_sha256": _sha256(path),
            "archive_set_sha256": digest,
            "official_archive_checksums": checksums,
        }
        print(symbol, len(opens), len(gaps), flush=True)
    (root / "basket_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
