from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .binance_archive import _download_verified, _sha256, _zip_rows

BINANCE_DATA_ROOT = "https://data.binance.vision/data"
MICROSECOND_THRESHOLD = 10**15


@dataclass(frozen=True)
class ArchiveDatasetSpec:
    market_path: str
    dataset: str
    symbol: str = "BTCUSDT"
    interval: str | None = None

    def monthly_url(self, month: str) -> str:
        middle = f"/{self.interval}" if self.interval else ""
        filename_middle = f"-{self.interval or self.dataset}"
        filename = f"{self.symbol}{filename_middle}-{month}.zip"
        return (
            f"{BINANCE_DATA_ROOT}/{self.market_path}/monthly/{self.dataset}/"
            f"{self.symbol}{middle}/{filename}"
        )

    def daily_url(self, day: str) -> str:
        middle = f"/{self.interval}" if self.interval else ""
        filename_middle = f"-{self.interval or self.dataset}"
        filename = f"{self.symbol}{filename_middle}-{day}.zip"
        return (
            f"{BINANCE_DATA_ROOT}/{self.market_path}/daily/{self.dataset}/"
            f"{self.symbol}{middle}/{filename}"
        )


OFFICIAL_SPECS = {
    "spot_aggTrades": ArchiveDatasetSpec("spot", "aggTrades"),
    "perp_aggTrades": ArchiveDatasetSpec("futures/um", "aggTrades"),
    "spot_klines_1m": ArchiveDatasetSpec("spot", "klines", interval="1m"),
    "perp_klines_1m": ArchiveDatasetSpec("futures/um", "klines", interval="1m"),
    "markPriceKlines_1m": ArchiveDatasetSpec(
        "futures/um", "markPriceKlines", interval="1m"
    ),
    "indexPriceKlines_1m": ArchiveDatasetSpec(
        "futures/um", "indexPriceKlines", interval="1m"
    ),
    "premiumIndexKlines_1m": ArchiveDatasetSpec(
        "futures/um", "premiumIndexKlines", interval="1m"
    ),
    "fundingRate": ArchiveDatasetSpec("futures/um", "fundingRate"),
}


def normalize_timestamp(value: str | int) -> tuple[int, str]:
    raw = int(value)
    if raw < 0:
        raise ValueError("archive timestamp must be non-negative")
    if raw >= MICROSECOND_THRESHOLD:
        return raw // 1_000, "microseconds"
    return raw, "milliseconds"


def aggressor_side(buyer_is_maker: str | bool) -> str:
    value = buyer_is_maker if isinstance(buyer_is_maker, bool) else buyer_is_maker.lower() == "true"
    return "SELL" if value else "BUY"


def parse_agg_trades(
    rows: Sequence[Sequence[str]], *, market: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    units: dict[str, int] = {"milliseconds": 0, "microseconds": 0}
    for row in rows:
        if len(row) < 7:
            raise ValueError("malformed Binance aggTrade row")
        raw_timestamp = int(row[5])
        timestamp_ms, unit = normalize_timestamp(raw_timestamp)
        units[unit] += 1
        parsed.append(
            {
                "aggregate_trade_id": int(row[0]),
                "price": float(row[1]),
                "quantity": float(row[2]),
                "first_trade_id": int(row[3]),
                "last_trade_id": int(row[4]),
                "raw_timestamp": raw_timestamp,
                "timestamp_ms": timestamp_ms,
                "source_timestamp_unit": unit,
                "buyer_is_maker": str(row[6]).lower() == "true",
                "aggressor_side": aggressor_side(row[6]),
                "market": market,
            }
        )
    ids = [int(item["aggregate_trade_id"]) for item in parsed]
    timestamps = [int(item["timestamp_ms"]) for item in parsed]
    return parsed, {
        "rows": len(parsed),
        "duplicate_aggregate_trade_ids": len(ids) - len(set(ids)),
        "out_of_order_ids": int(ids != sorted(ids)),
        "out_of_order_timestamps": int(timestamps != sorted(timestamps)),
        "invalid_price_or_quantity": sum(
            float(item["price"]) <= 0 or float(item["quantity"]) <= 0 for item in parsed
        ),
        "timestamp_units": {key: value for key, value in units.items() if value},
        "synthetic_rows": 0,
    }


def aggregate_flow(
    rows: Iterable[dict[str, Any]], *, bucket_ms: int = 3_600_000
) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, Any]] = {}
    for row in rows:
        timestamp = int(row["timestamp_ms"])
        bucket = timestamp - timestamp % bucket_ms
        item = buckets.setdefault(
            bucket,
            {
                "open_time_ms": bucket,
                "buy_notional": 0.0,
                "sell_notional": 0.0,
                "buy_count": 0,
                "sell_count": 0,
                "trade_count": 0,
            },
        )
        side = str(row["aggressor_side"])
        notional = float(row["price"]) * float(row["quantity"])
        item[f"{side.lower()}_notional"] += notional
        item[f"{side.lower()}_count"] += 1
        item["trade_count"] += 1
    output: list[dict[str, Any]] = []
    for item in sorted(buckets.values(), key=lambda row: int(row["open_time_ms"])):
        total = float(item["buy_notional"]) + float(item["sell_notional"])
        count = int(item["trade_count"])
        output.append(
            {
                **item,
                "net_taker_flow": float(item["buy_notional"]) - float(item["sell_notional"]),
                "notional_imbalance": (
                    (float(item["buy_notional"]) - float(item["sell_notional"])) / total
                    if total > 0
                    else None
                ),
                "trade_count_imbalance": (
                    (int(item["buy_count"]) - int(item["sell_count"])) / count
                    if count > 0
                    else None
                ),
                "mean_trade_size": total / count if count > 0 else None,
            }
        )
    return output


def probe_official_archives(months: Sequence[str]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for name, spec in OFFICIAL_SPECS.items():
        for month in months:
            url = spec.monthly_url(month)
            checksum_url = url + ".CHECKSUM"
            try:
                with urllib.request.urlopen(checksum_url, timeout=30) as response:
                    body = response.read().decode("utf-8")
                checksum = body.split()[0]
                status = "AVAILABLE"
            except (urllib.error.URLError, TimeoutError, OSError, IndexError):
                checksum = None
                status = "MISSING_OR_UNREACHABLE"
            results.append(
                {
                    "dataset": name,
                    "month": month,
                    "url": url,
                    "checksum_url": checksum_url,
                    "status": status,
                    "official_sha256": checksum,
                }
            )
    canonical = json.dumps(results, sort_keys=True, separators=(",", ":"))
    return {
        "months": list(months),
        "requests": results,
        "available": sum(item["status"] == "AVAILABLE" for item in results),
        "missing_or_unreachable": sum(
            item["status"] != "AVAILABLE" for item in results
        ),
        "manifest_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
    }


def download_agg_trade_month(
    spec: ArchiveDatasetSpec, month: str, target: str | Path
) -> dict[str, Any]:
    url = spec.monthly_url(month)
    path = Path(target)
    official_checksum = _download_verified(url, path)
    rows, audit = parse_agg_trades(_zip_rows(path), market=spec.market_path)
    return {
        "url": url,
        "path": str(path),
        "official_checksum": official_checksum,
        "local_checksum": _sha256(path),
        "audit": audit,
        "rows": rows,
    }


def read_zip_sample(path: str | Path, limit: int = 1000) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != 1:
            raise ValueError("expected exactly one CSV member")
        with archive.open(names[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8"))
            rows: list[list[str]] = []
            for row in reader:
                if not rows and row and not row[0].isdigit():
                    continue
                rows.append(row)
                if len(rows) >= limit:
                    break
    return rows


def write_manifest(path: str | Path, payload: dict[str, Any]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    canonical = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target.write_text(canonical, encoding="utf-8")
    return _sha256(target)
