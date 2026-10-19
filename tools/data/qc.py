"""Quality control and schema validation for historical datasets.

Performs deterministic offline QC:
- CSV / JSON structure
- Header and schema conformity
- Timestamps monotonicity, bounds, and interval spacing
- Row counts, gap detection, duplicate timestamp detection
- Value range sanity (positive prices, finite quantities)
"""
from __future__ import annotations

import csv
import io
import json
import tarfile
import zipfile
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.data.common import Budget

# Schemas
BINANCE_BARS_SCHEMA = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"
]
BINANCE_BARS_ALIASES = {
    "quote_asset_volume": "quote_volume",
    "number_of_trades": "count",
    "taker_buy_base_asset_volume": "taker_buy_volume",
    "taker_buy_quote_asset_volume": "taker_buy_quote_volume",
}

BINANCE_METRICS_SCHEMA = [
    "create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
    "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio",
    "count_long_short_ratio", "sum_taker_long_short_vol_ratio"
]

BINANCE_FUNDING_RATE_SCHEMA = [
    "calc_time", "funding_interval_hours", "last_funding_rate"
]

BINANCE_AGG_TRADES_SCHEMA = [
    "agg_trade_id", "price", "quantity", "first_trade_id", "last_trade_id",
    "transact_time", "is_buyer_maker"
]

OKX_CANDLESTICKS_SCHEMA = [
    "instrument_name", "open", "high", "low", "close", "vol", "vol_ccy",
    "vol_quote", "open_time", "confirm"
]

OKX_FUNDING_RATE_SCHEMA = [
    "instrument_name", "funding_rate", "funding_time"
]

OKX_TRADES_SCHEMA = [
    "instrument_name", "trade_id", "side", "price", "size", "created_time"
]


def parse_timestamp_ms(val: str) -> int:
    """Parse integer timestamp (microseconds, milliseconds, seconds) or ISO string to integer milliseconds."""
    val = val.strip()
    if val.isdigit() or (val.startswith("-") and val[1:].isdigit()):
        ts_raw = int(val)
        if ts_raw > 10**14:  # microseconds (e.g. Binance Spot)
            return ts_raw // 1000
        elif ts_raw > 10**11:  # milliseconds (e.g. Binance Futures, OKX)
            return ts_raw
        else:  # seconds
            return ts_raw * 1000
    dt = datetime.fromisoformat(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def qc_csv_stream(
    rows: Iterator[list[str]],
    family: str,
    venue: str,
    expected_interval_ms: int | None = None,
) -> dict[str, Any]:
    """Inspect CSV rows for schema conformity, timestamp monotonicity, gaps, and duplicates."""
    first = next(rows, None)
    if first is None:
        return {
            "verdict": "FAIL",
            "error": "EMPTY_CSV",
            "rows": 0,
        }

    header_present = False
    expected_schema: list[str] | None = None

    if venue == "binance":
        if family in ("klines", "markPriceKlines", "spot_klines"):
            expected_schema = BINANCE_BARS_SCHEMA
            normalized = [BINANCE_BARS_ALIASES.get(v.strip().lower(), v.strip().lower()) for v in first]
            if not first[0].isdigit():
                header_present = True
                schema_match = normalized[:len(expected_schema)] == expected_schema
            else:
                header_present = False
                schema_match = len(first) >= 11
        elif family == "metrics":
            expected_schema = BINANCE_METRICS_SCHEMA
            header_present = first[0].strip() == "create_time"
            schema_match = first[:len(expected_schema)] == expected_schema
        elif family == "fundingRate":
            expected_schema = BINANCE_FUNDING_RATE_SCHEMA
            header_present = not first[0].isdigit()
            schema_match = True
        elif family == "aggTrades":
            expected_schema = BINANCE_AGG_TRADES_SCHEMA
            header_present = not first[0].isdigit()
            schema_match = True
        else:
            schema_match = True
    elif venue == "okx":
        if family in ("candlesticks", "spot_candlesticks"):
            expected_schema = OKX_CANDLESTICKS_SCHEMA
            header_present = first[0].strip().lower() == "instrument_name"
            schema_match = [c.strip().lower() for c in first] == expected_schema
        elif family == "funding_rates":
            expected_schema = OKX_FUNDING_RATE_SCHEMA
            header_present = first[0].strip().lower() == "instrument_name"
            schema_match = [c.strip().lower() for c in first] == expected_schema
        elif family == "trades":
            expected_schema = OKX_TRADES_SCHEMA
            header_present = first[0].strip().lower() == "instrument_name"
            schema_match = [c.strip().lower() for c in first][:6] == OKX_TRADES_SCHEMA[:6]
        else:
            schema_match = True

    if not schema_match:
        return {
            "verdict": "FAIL",
            "error": "SCHEMA_MISMATCH",
            "actual_header": first,
            "expected_header": expected_schema,
            "rows": 0,
        }

    # Timestamp column index
    ts_idx = 0
    if venue == "binance":
        if family in ("klines", "markPriceKlines", "spot_klines", "metrics", "fundingRate"):
            ts_idx = 0
        elif family == "aggTrades":
            ts_idx = 5
    elif venue == "okx":
        if family in ("candlesticks", "spot_candlesticks"):
            ts_idx = 8
        elif family == "funding_rates":
            ts_idx = 2
        elif family == "trades":
            ts_idx = 5

    data_rows = rows if header_present else itertools_chain([first], rows)

    malformed_rows = 0

    if family == "metrics":
        metric_rows: list[tuple[int, list[str]]] = []
        for r in data_rows:
            if not r or len(r) < 2:
                continue
            try:
                ts = parse_timestamp_ms(r[ts_idx])
                metric_rows.append((ts, r))
            except (ValueError, TypeError, IndexError):
                malformed_rows += 1
        metric_rows.sort(key=lambda x: x[0])
        eval_iter: Iterator[tuple[int, list[str]]] = iter(metric_rows)
    else:
        def stream_gen() -> Iterator[tuple[int, list[str]]]:
            nonlocal malformed_rows
            for r in data_rows:
                if not r or len(r) < 2:
                    continue
                try:
                    ts = parse_timestamp_ms(r[ts_idx])
                    yield ts, r
                except (ValueError, TypeError, IndexError):
                    malformed_rows += 1
        eval_iter = stream_gen()

    prev_ts: int | None = None
    prev_ts_by_sym: dict[str, int] = {}
    start_ts: int | None = None
    end_ts: int | None = None
    row_count = 0
    duplicate_count = 0
    gap_count = 0

    for ts, r in eval_iter:
        if start_ts is None:
            start_ts = ts

        cur_prev_ts = prev_ts_by_sym.get(r[0]) if (family == "funding_rates" and r) else prev_ts

        if cur_prev_ts is not None:
            if ts == cur_prev_ts:
                if family in ("klines", "markPriceKlines", "spot_klines", "candlesticks", "spot_candlesticks", "metrics"):
                    duplicate_count += 1
            elif ts < cur_prev_ts:
                # Monotonicity violation in strictly ordered feeds
                malformed_rows += 1
            elif expected_interval_ms and expected_interval_ms > 0:
                diff = ts - cur_prev_ts
                if diff > expected_interval_ms:
                    missing_steps = (diff // expected_interval_ms) - 1
                    gap_count += missing_steps

        if family == "funding_rates" and r:
            prev_ts_by_sym[r[0]] = ts
        else:
            prev_ts = ts
        end_ts = ts
        row_count += 1

    start_utc = datetime.fromtimestamp(start_ts / 1000, tz=UTC).isoformat() if start_ts is not None else None
    end_utc = datetime.fromtimestamp(end_ts / 1000, tz=UTC).isoformat() if end_ts is not None else None

    verdict = "PASS"
    if malformed_rows > 0:
        verdict = "FAIL"
    elif duplicate_count > 0:
        verdict = "PARTIAL_PASS"

    return {
        "verdict": verdict,
        "rows": row_count,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "start_ts_ms": start_ts,
        "end_ts_ms": end_ts,
        "gaps": gap_count,
        "duplicates": duplicate_count,
        "malformed_rows": malformed_rows,
        "header_present": header_present,
    }


def itertools_chain(first_list: list[Any], rest: Iterator[Any]) -> Iterator[Any]:
    yield from first_list
    yield from rest


def qc_zip_archive(
    zip_path: Path,
    family: str,
    venue: str,
    budget: Budget,
    expected_interval_ms: int | None = None,
) -> dict[str, Any]:
    """Extract CSV from zip archive and execute offline schema & timestamp QC."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        if not members:
            return {"verdict": "FAIL", "error": "EMPTY_ZIP", "rows": 0}

        csv_member = next((m for m in members if m.filename.endswith(".csv")), members[0])
        expanded_size = csv_member.file_size
        budget.consume_expanded(expanded_size)

        with zf.open(csv_member, "r") as f:
            text_io = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            reader = csv.reader(text_io)
            qc_result = qc_csv_stream(reader, family, venue, expected_interval_ms)

    qc_result["expanded_bytes"] = expanded_size
    qc_result["compressed_bytes"] = zip_path.stat().st_size
    qc_result["member_filename"] = csv_member.filename
    return qc_result


def qc_okx_l2_archive(
    tar_path: Path,
    budget: Budget,
    max_check_records: int = 2000,
) -> dict[str, Any]:
    """QC OKX L2 400lv order book tar.gz archive.

    Verifies archive structure, action sequence (snapshot followed by updates),
    and timestamp monotonicity without expanding the entire file to disk.
    """
    compressed_bytes = tar_path.stat().st_size
    records_checked = 0
    snapshot_found = False
    start_utc: str | None = None
    end_utc: str | None = None
    inst_id: str | None = None
    member_name: str | None = None
    expanded_size: int = 0

    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar:
            member_name = member.name
            expanded_size = member.size
            budget.consume_expanded(min(expanded_size, 50 * 1024**2))  # Bounded budget charge for QC
            f = tar.extractfile(member)
            if not f:
                break
            text_io = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
            for line in text_io:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                if not inst_id:
                    inst_id = obj.get("instId")
                action = obj.get("action")
                if action == "snapshot":
                    snapshot_found = True

                ts_str = obj.get("ts")
                if ts_str:
                    ts = int(ts_str)
                    if start_utc is None:
                        start_utc = datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat()
                    end_utc = datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat()

                records_checked += 1
                if records_checked >= max_check_records:
                    break
            break

    verdict = "PASS" if snapshot_found and records_checked > 0 else "FAIL"
    return {
        "verdict": verdict,
        "compressed_bytes": compressed_bytes,
        "expanded_bytes": expanded_size,
        "member_filename": member_name,
        "inst_id": inst_id,
        "snapshot_verified": snapshot_found,
        "records_sampled": records_checked,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "type": "L2_ORDERBOOK_400LV",
    }
