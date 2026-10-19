"""Small-batch typed Parquet transforms from selected immutable raw sources."""

from __future__ import annotations

import csv
import io
import math
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from . import SCHEMA_VERSION
from .inventory import digest


UTC_TS = pa.timestamp("us", tz="UTC")
COMMON = [
    ("exchange", pa.string()), ("native_symbol", pa.string()),
    ("canonical_underlying", pa.string()), ("quote_asset", pa.string()),
    ("product_type", pa.string()), ("contract_identity", pa.string()),
    ("price_unit", pa.string()), ("base_qty_unit", pa.string()),
    ("event_ts_utc", UTC_TS), ("interval_start_utc", UTC_TS),
    ("interval_end_utc", UTC_TS), ("interval", pa.string()),
    ("source_native_ts", pa.string()), ("source_time_unit", pa.string()),
    ("exchange_published_at", UTC_TS), ("local_ingested_at", UTC_TS),
    ("receiver_first_known_at", UTC_TS), ("source_id", pa.string()),
    ("raw_sha256", pa.string()), ("schema_version", pa.string()),
    ("qc_flags", pa.string()),
]
SCHEMAS = {
    "bars": pa.schema(COMMON + [("open", pa.float64()), ("high", pa.float64()),
        ("low", pa.float64()), ("close", pa.float64()), ("base_volume", pa.float64()),
        ("native_volume", pa.float64()), ("native_volume_unit", pa.string()),
        ("quote_volume", pa.float64())]),
    "position_state": pa.schema(COMMON + [("base_open_interest", pa.float64()),
        ("top_position_long_short_ratio", pa.float64())]),
    "funding_settlements": pa.schema(COMMON + [("funding_rate", pa.float64()),
        ("funding_interval_hours", pa.int32())]),
}
SCHEMAS["mark_prices"] = SCHEMAS["bars"]
SCHEMAS["index_prices"] = SCHEMAS["bars"]
SCHEMAS["premium_index"] = SCHEMAS["bars"]
SCHEMAS["premium_index_prices"] = SCHEMAS["bars"]
SCHEMAS["trades"] = pa.schema(COMMON + [("trade_id", pa.string()),
    ("price", pa.float64()), ("native_quantity", pa.float64()),
    ("native_quantity_unit", pa.string()), ("aggressor_side", pa.string())])
SCHEMAS["l2_snapshots"] = pa.schema(COMMON + [("level", pa.int32()),
    ("side", pa.string()), ("price", pa.float64()), ("native_size", pa.float64())])
SCHEMAS["l2_deltas"] = pa.schema(COMMON + [("level", pa.int32()),
    ("side", pa.string()), ("price", pa.float64()), ("native_size", pa.float64()),
    ("operation", pa.string())])
SCHEMAS["feature_mart"] = pa.schema(COMMON + [("origin_utc", UTC_TS),
    ("feature_name", pa.string()), ("feature_value", pa.float64()),
    ("readiness_reason", pa.string())])
FLOW_FIELDS = [
    ("event_count", pa.int64()), ("volume_base", pa.float64()),
    ("volume_quote", pa.float64()), ("signed_flow_base", pa.float64()),
    ("signed_flow_quote", pa.float64()), ("buy_volume_base", pa.float64()),
    ("buy_volume_quote", pa.float64()), ("sell_volume_base", pa.float64()),
    ("sell_volume_quote", pa.float64()), ("buy_event_count", pa.int64()),
    ("sell_event_count", pa.int64()), ("vwap", pa.float64()),
    ("trade_open", pa.float64()), ("trade_high", pa.float64()),
    ("trade_low", pa.float64()), ("trade_close", pa.float64()),
    ("first_trade_id", pa.int64()), ("last_trade_id", pa.int64()),
]
SCHEMAS["trade_flow_1m"] = pa.schema(COMMON + FLOW_FIELDS)
BAR_FAMILIES = {"candles", "klines", "spot_klines", "candlesticks",
                "spot_candlesticks", "markPriceKlines", "markPriceKlines_1m",
                "indexPriceKlines_1m", "premiumIndexKlines_1m"}
BINANCE_FIELDS = ("open_time", "open", "high", "low", "close", "volume", "close_time",
                  "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore")


def kind(source: dict[str, Any]) -> str | None:
    family = source["family"]
    if family in ("markPriceKlines", "markPriceKlines_1m"):
        return "mark_prices"
    if family in ("indexPriceKlines", "indexPriceKlines_1m"):
        return "index_prices"
    if family in ("premiumIndexKlines", "premiumIndexKlines_1m"):
        return "premium_index"
    if family in BAR_FAMILIES:
        return "bars"
    if family == "metrics":
        return "position_state"
    if family in ("fundingRate", "funding_rates"):
        return "funding_settlements"
    return None


def _us(native: str | int) -> tuple[int, str]:
    value = int(native)
    if 10**15 <= abs(value) < 10**18:
        return value, "us"
    if 10**12 <= abs(value) < 10**15:
        return value * 1000, "ms"
    raise ValueError("NATIVE_TIMESTAMP_UNIT_UNKNOWN")


def _finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("NONFINITE_SOURCE_VALUE")
    return number


def _csv_rows(path: Path, maximum: int) -> Iterator[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        members = [x for x in archive.infolist() if not x.is_dir()]
        if len(members) != 1 or members[0].file_size > 80 * 1024**2:
            raise ValueError("ZIP_MEMBER_BUDGET_OR_COUNT")
        with archive.open(members[0]) as binary, io.TextIOWrapper(binary, encoding="utf-8", newline="") as text:
            reader = csv.reader(text)
            first = next(reader, None)
            if first is None:
                return
            if first[0] in ("open_time", "create_time", "instrument_name", "calc_time"):
                header = first
            elif first[0].isdigit() and len(first) == 12:
                header = BINANCE_FIELDS
                yield dict(zip(header, first))
                maximum -= 1
            else:
                raise ValueError("SOURCE_CSV_SCHEMA_UNKNOWN")
            for i, values in enumerate(reader):
                if i >= maximum:
                    break
                if len(values) != len(header):
                    raise ValueError("SOURCE_CSV_ROW_WIDTH_INVALID")
                yield dict(zip(header, values))


def _source_rows(source: dict[str, Any], maximum: int) -> Iterator[dict[str, Any]]:
    path = Path(source["path"])
    if path.suffix == ".parquet":
        pf = pq.ParquetFile(path)
        count = 0
        for batch in pf.iter_batches(batch_size=min(256, maximum), use_threads=False):
            for row in batch.to_pylist():
                if count >= maximum:
                    return
                count += 1
                yield row
    elif path.suffix == ".zip":
        yield from _csv_rows(path, maximum)
    else:
        raise ValueError("UNSUPPORTED_TRANSFORM_SOURCE")


def _common(source: dict[str, Any], native: Any, event_us: int, start_us: int,
            end_us: int, unit: str) -> dict[str, Any]:
    asset = source["asset"]
    return {"exchange": source["exchange"], "native_symbol": source["symbol"],
        "canonical_underlying": asset, "quote_asset": "USDT",
        "product_type": source["product"],
        "contract_identity": source["symbol"] if source["product"] != "SPOT" else "SPOT",
        "price_unit": f"USDT/{asset}",
        "base_qty_unit": asset if source["product"] != "OKX_SWAP" else "UNKNOWN_CONTRACT_CONVERSION",
        "event_ts_utc": event_us, "interval_start_utc": start_us,
        "interval_end_utc": end_us, "interval": source["interval"],
        "source_native_ts": str(native), "source_time_unit": unit,
        "exchange_published_at": None, "local_ingested_at": None,
        "receiver_first_known_at": None, "source_id": source["source_id"],
        "raw_sha256": source["raw_sha256"], "schema_version": SCHEMA_VERSION,
        "qc_flags": "HISTORICAL_OFFLINE|PIT_UNKNOWN|SOURCE_NOT_ADMITTED|SAMPLED_PREFIX"}


def normalize(source: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    family = source["family"]
    if family == "metrics":
        native = row["create_time"]
        t = int(datetime.strptime(native, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp() * 10**6)
        if row.get("symbol") != source["symbol"]:
            raise ValueError("SOURCE_SYMBOL_MISMATCH")
        return _common(source, native, t, t, t, "UTC_TEXT") | {
            "base_open_interest": _finite(row["sum_open_interest"]),
            "top_position_long_short_ratio": _finite(row["sum_toptrader_long_short_ratio"])}
    if family in ("fundingRate", "funding_rates"):
        if family == "funding_rates":
            native = row["funding_time"]
            t, unit = _us(native)
            interval_h = 8
            rate = _finite(row["funding_rate"])
        else:
            native = row["calc_time"]
            t, unit = _us(native)
            interval_h = int(row["funding_interval_hours"])
            if interval_h <= 0 or interval_h > 24:
                raise ValueError("FUNDING_INTERVAL_INVALID")
            rate = _finite(row["last_funding_rate"])
        return _common(source, native, t, t - interval_h * 3600 * 10**6, t, unit) | {
            "funding_rate": rate,
            "funding_interval_hours": interval_h}
    if family not in BAR_FAMILIES:
        raise ValueError("UNSUPPORTED_SOURCE_FAMILY")
    if source["exchange"] == "okx":
        if row.get("instrument_name") != source["symbol"] or row.get("confirm") != "1":
            raise ValueError("OKX_MARKET_OR_CONFIRM_INVALID")
        native = row["open_time"]
        start_us, unit = _us(native)
        native_volume = _finite(row["vol"])
        base_volume = native_volume if source["product"] == "SPOT" else None
        volume_unit = source["asset"] if source["product"] == "SPOT" else "OKX_CONTRACTS"
        quote_volume = _finite(row["vol_quote"])
    elif source["path"].endswith(".parquet"):
        native = row["open_time_ms"]
        start_us, unit = _us(native)
        native_volume = _finite(row["volume"])
        base_volume, volume_unit = native_volume, source["asset"]
        quote_volume = _finite(row["quote_volume"]) if "quote_volume" in row else None
    else:
        native = row["open_time"]
        start_us, unit = _us(native)
        native_volume = _finite(row["volume"])
        base_volume, volume_unit = native_volume, source["asset"]
        quote_volume = _finite(row["quote_volume"])
    step = 3600 if source["interval"] == "1h" else 60
    end_us = start_us + step * 10**6
    if family in BAR_FAMILIES:
        close_native = row.get("close_time_ms") if "close_time_ms" in row else row.get("close_time")
        if close_native is not None:
            close_us, _ = _us(close_native)
            if not start_us <= close_us < end_us:
                raise ValueError("BAR_CLOSE_CLOCK_INVALID")
    values = {k: _finite(row[k]) for k in ("open", "high", "low", "close")}
    if not (values["low"] <= values["open"] <= values["high"] and
            values["low"] <= values["close"] <= values["high"]):
        raise ValueError("BAR_OHLC_INVALID")
    return _common(source, native, end_us, start_us, end_us, unit) | values | {
        "base_volume": base_volume, "native_volume": native_volume,
        "native_volume_unit": volume_unit, "quote_volume": quote_volume}


def write_sample(source: dict[str, Any], output: Path, maximum: int = 3000) -> dict[str, Any]:
    table_kind = kind(source)
    if table_kind is None or source["qa_level"] not in (
        "MANIFEST_PINNED_FOOTER_READ_RAW_NOT_REHASHED", "PASS_MANIFEST_QC_PINNED_RAW_NOT_REHASHED"):
        raise ValueError("SOURCE_NOT_SELECTED_FOR_TRANSFORM")
    if not 1 <= maximum <= 10000:
        raise ValueError("SCAN_BUDGET_INVALID")
    path = Path(source["path"])
    if path.is_symlink() or not path.is_file() or not source["raw_sha256"]:
        raise ValueError("SOURCE_PATH_OR_HASH_UNSAFE")
    before = digest(path)
    if before != source["raw_sha256"]:
        raise ValueError("SOURCE_HASH_MISMATCH")
    partition = output / "partitions" / f"table={table_kind}" / f"exchange={source['exchange']}" / \
        f"asset={source['asset']}" / f"product={source['product']}" / f"period={source['period']}"
    partition.mkdir(parents=True, exist_ok=True)
    target = partition / f"{source['source_id']}.parquet"
    temporary = target.with_suffix(".parquet.partial")
    if temporary.exists():
        temporary.unlink()
    writer = None
    count = 0
    minimum = maximum_ts = None
    previous = None
    try:
        buffer = []
        for raw in _source_rows(source, maximum):
            item = normalize(source, raw)
            t = item["interval_start_utc"]
            if previous is not None and t <= previous:
                raise ValueError("SOURCE_TIMESTAMP_ORDER_OR_DUPLICATE")
            previous = t
            minimum = t if minimum is None else min(minimum, t)
            maximum_ts = t if maximum_ts is None else max(maximum_ts, t)
            buffer.append(item)
            if len(buffer) >= 512:
                if writer is None:
                    writer = pq.ParquetWriter(temporary, SCHEMAS[table_kind], compression="zstd")
                writer.write_table(pa.Table.from_pylist(buffer, schema=SCHEMAS[table_kind]))
                count += len(buffer); buffer.clear()
        if buffer:
            if writer is None:
                writer = pq.ParquetWriter(temporary, SCHEMAS[table_kind], compression="zstd")
            writer.write_table(pa.Table.from_pylist(buffer, schema=SCHEMAS[table_kind]))
            count += len(buffer)
        if writer is None:
            raise ValueError("EMPTY_TRANSFORM_SAMPLE")
        writer.close(); writer = None
        if digest(path) != before:
            raise ValueError("SOURCE_CHANGED_DURING_TRANSFORM")
        os.replace(temporary, target)
    except BaseException:
        if writer is not None:
            writer.close()
        temporary.unlink(missing_ok=True)
        raise
    return {"source_id": source["source_id"], "source_path": str(path), "source_sha256": before,
            "exchange": source["exchange"], "asset": source["asset"],
            "product": source["product"], "family": source["family"],
            "table": table_kind, "sample_rows": count, "sample_start_utc_us": minimum,
            "sample_last_start_utc_us": maximum_ts, "sampled_prefix_not_full_coverage": True,
            "partition_path": str(target), "partition_sha256": digest(target)}
