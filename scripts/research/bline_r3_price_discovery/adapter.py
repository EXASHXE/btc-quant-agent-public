"""Month-scoped, receipt-pinned native C1 bars, with no other source access."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from .contracts import C1, MINUTE, digest, us

SCHEMA = {
    "exchange",
    "native_symbol",
    "canonical_underlying",
    "quote_asset",
    "product_type",
    "contract_identity",
    "price_unit",
    "base_qty_unit",
    "event_ts_utc",
    "interval_start_utc",
    "interval_end_utc",
    "interval",
    "source_native_ts",
    "source_time_unit",
    "exchange_published_at",
    "local_ingested_at",
    "receiver_first_known_at",
    "source_id",
    "raw_sha256",
    "schema_version",
    "qc_flags",
    "open",
    "high",
    "low",
    "close",
    "base_volume",
    "native_volume",
    "native_volume_unit",
    "quote_volume",
}
TIME = ["interval_start_utc", "interval_end_utc", "event_ts_utc"]
COLUMNS = TIME + [
    "exchange",
    "native_symbol",
    "canonical_underlying",
    "quote_asset",
    "product_type",
    "contract_identity",
    "price_unit",
    "interval",
    "source_native_ts",
    "source_time_unit",
    "source_id",
    "raw_sha256",
    "open",
    "high",
    "low",
    "close",
    "base_volume",
    "quote_volume",
    "qc_flags",
]


@dataclass(frozen=True)
class Bar:
    start: int
    end: int
    close: float
    fingerprint: tuple
    source_id: str
    raw_sha256: str


def native_bar(row, product, receipt):
    identity = (
        row["exchange"],
        row["native_symbol"],
        row["canonical_underlying"],
        row["quote_asset"],
        row["product_type"],
        row["contract_identity"],
        row["price_unit"],
        row["interval"],
    )
    if identity != (
        "binance",
        "BTCUSDT",
        "BTC",
        "USDT",
        product,
        "SPOT" if product == "SPOT" else "BTCUSDT",
        "USDT/BTC",
        "1m",
    ):
        raise ValueError("BAR_VENUE_CONTRACT_SOURCE_FAMILY_MISMATCH")
    family = "spot_klines" if product == "SPOT" else "candles"
    if (receipt["table"], receipt["family"], receipt["interval"], receipt["product"]) != (
        "bars",
        family,
        "1m",
        product,
    ):
        raise ValueError("SOURCE_FAMILY_MISMATCH")
    if (row["source_id"], row["raw_sha256"]) != (receipt["source_id"], receipt["source_sha256"]):
        raise ValueError("UNRECEIPTED_NATIVE_SOURCE")
    start, end = row["interval_start_utc"], row["interval_end_utc"]
    scale = {"ms": 1000, "us": 1}.get(row["source_time_unit"])
    if (
        not isinstance(start, int)
        or not isinstance(end, int)
        or start % MINUTE
        or end != start + MINUTE
        or row["event_ts_utc"] != end
        or scale is None
        or int(row["source_native_ts"]) * scale != start
    ):
        raise ValueError("NATIVE_BAR_UTC_CLOCK_INVALID")
    expected_unit = "us" if product == "SPOT" and receipt["period"] >= "2025-01" else "ms"
    if row["source_time_unit"] != expected_unit:
        raise ValueError("NATIVE_TIMESTAMP_UNIT_MISMATCH")
    prices = tuple(row[n] for n in ["open", "high", "low", "close"])
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in prices):
        raise ValueError("INVALID_NATIVE_PRICE")
    if (
        not row["low"]
        <= min(row["open"], row["close"])
        <= max(row["open"], row["close"])
        <= row["high"]
    ):
        raise ValueError("INVALID_NATIVE_OHLC")
    volumes = tuple(row[n] for n in ["base_volume", "quote_volume"])
    if any(v is None or not math.isfinite(v) or v < 0 for v in volumes):
        raise ValueError("INVALID_NATIVE_VOLUME")
    return Bar(start, end, row["close"], prices + volumes, row["source_id"], row["raw_sha256"])


def insert_bar(bars, conflicts, refs, bar):
    prior = bars.get(bar.end)
    duplicate = prior is not None
    if prior is not None and prior.fingerprint != bar.fingerprint:
        conflicts.add(bar.end)
    elif prior is None:
        bars[bar.end] = bar
    refs.setdefault(bar.end, set()).add((bar.source_id, bar.raw_sha256))
    return duplicate


def load_month(receipts, product, month, left, right):
    """Exact month file list, unlike a dataset scan that discovers held-year footers."""
    bars, conflicts, refs, sources, flags = {}, set(), {}, [], set()
    physical_rows = duplicates = 0
    for rec in receipts:
        if rec["product"] != product or rec["period"] != month:
            continue
        from pathlib import Path

        path = Path(rec["partition_path"])
        expected_parent = (
            C1 / "table=bars/exchange=binance/asset=BTC" / f"product={product}" / f"period={month}"
        )
        if path.parent != expected_parent or path.is_symlink() or path.resolve() != path:
            raise ValueError("CANONICAL_MONTH_PATH_MISMATCH")
        if rec["status"] != "SUCCESS" or digest(path) != rec["partition_sha256"]:
            raise ValueError("CANONICAL_RECEIPT_SHA_MISMATCH")
        parquet = pq.ParquetFile(path)
        if set(parquet.schema_arrow.names) != SCHEMA:
            raise ValueError("NO_OUTCOME_INPUT_SCHEMA_REQUIRED")
        for name in TIME:
            if parquet.schema_arrow.field(name).type != pa.timestamp("us", tz="UTC"):
                raise ValueError("NATIVE_UTC_SCHEMA_REQUIRED")
        table = parquet.read(columns=COLUMNS)
        if table.num_rows != rec["row_count"]:
            raise ValueError("RECEIPT_ROW_COUNT_MISMATCH")
        for name in TIME:
            idx = table.schema.get_field_index(name)
            table = table.set_column(idx, name, pc.cast(table[name], pa.int64()))
        data = table.to_pydict()
        for i in range(table.num_rows):
            row = {k: data[k][i] for k in COLUMNS}
            bar = native_bar(row, product, rec)
            if not left <= bar.start < right:
                raise ValueError("NATIVE_MONTH_PERIOD_MISMATCH")
            duplicates += insert_bar(bars, conflicts, refs, bar)
            flags.add(row["qc_flags"])
        physical_rows += table.num_rows
        sources.append(
            {
                "source_id": rec["source_id"],
                "canonical_path": str(path),
                "canonical_sha256": rec["partition_sha256"],
                "raw_source_sha256_pin": rec["source_sha256"],
                "family": rec["family"],
                "receipt_qa_flags": rec["qa_flags"],
            }
        )
    expected = (right - left) // MINUTE
    coverage = {
        "product": product,
        "month": month,
        "expected_native_minutes": expected,
        "physical_rows": physical_rows,
        "unique_native_minutes": len(bars),
        "missing_native_minutes": expected - len(bars),
        "identical_or_conflicting_duplicate_rows": duplicates,
        "conflicting_minutes": len(conflicts),
        "usable_native_minutes": len(bars) - len(conflicts),
        "source_ids": sorted(s["source_id"] for s in sources),
        "sources": sources,
        "row_qc_flags_observed": sorted(flags),
        "qc_flag_caveat": "Legacy SAMPLED_PREFIX row flags persist in some FULL receipt-pinned partitions. Full-file SHA/row counts checked; flags not rewritten.",
        "receiver_first_known": None,
        "PIT": "UNKNOWN",
    }
    return bars, conflicts, refs, coverage


def aligned_window(spot, perp, spot_conflicts, perp_conflicts, cutoff):
    ends = [cutoff - (16 - j) * MINUTE for j in range(16)]
    reasons = []
    if any(t not in spot for t in ends):
        reasons.append("SPOT_MINUTE_MISSING")
    if any(t not in perp for t in ends):
        reasons.append("PERP_MINUTE_MISSING")
    if any(t in spot_conflicts or t in perp_conflicts for t in ends):
        reasons.append("CONFLICTING_NATIVE_MINUTE")
    if reasons:
        return None, reasons
    for t in ends:
        if (
            spot[t].end != perp[t].end
            or spot[t].end != t
            or t >= cutoff
            or spot[t].start != t - MINUTE
            or perp[t].start != t - MINUTE
        ):
            raise ValueError("ALIGNMENT_CAUSAL_CLOCK_INVALID")
    return ([spot[t].close for t in ends], [perp[t].close for t in ends]), []


def displacement(spot, perp):
    if len(spot) != 16 or len(perp) != 16:
        raise ValueError("EXACT_16_CLOSES_REQUIRED")
    s = [math.log(v / spot[0]) for v in spot]
    p = [math.log(v / perp[0]) for v in perp]
    ts = next((j for j in range(1, 16) if s[j] <= -0.001), None)
    tp = next((j for j in range(1, 16) if p[j] <= -0.001), None)
    gap = p[ts] - s[ts] if ts is not None else None
    remaining = (p[-1] - s[-1]) / gap if gap is not None and gap > 0 else None
    order = ts is not None and tp is not None and ts <= 5 and ts < tp
    lead = ts is not None and p[ts] > -0.0005 and gap >= 0.0005
    recovery = remaining is not None and 0.25 <= remaining <= 0.75 and p[-1] < p[ts]
    persistent = ts is not None and s[-1] <= -0.001 and abs(s[-1] - s[ts]) <= 0.0005
    conditions = {
        "SPOT_FIRST_ORDER_NOT_OBSERVED": order,
        "EARLY_PERP_LAG_NOT_OBSERVED": lead,
        "PARTIAL_PERP_RECOVERY_NOT_OBSERVED": recovery,
        "SPOT_PERSISTENCE_NOT_OBSERVED": persistent,
    }
    return {
        "spot_log_displacement": s,
        "perp_log_displacement": p,
        "first_spot_cross_index": ts,
        "first_perp_cross_index": tp,
        "initial_relative_displacement": gap,
        "remaining_fraction": remaining,
        "Z_condition": bool(all(conditions.values())),
    }, [k for k, v in conditions.items() if not v]


def month_bounds(month):
    y, m = map(int, month.split("-"))
    return us(month + "-01T00:00:00Z"), us(f"{y + m // 12}-{m % 12 + 1:02}-01T00:00:00Z")
