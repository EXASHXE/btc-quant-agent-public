"""Native archive clocks and identity checks; no returns or strategy labels."""
from __future__ import annotations

import csv
import io
import math
import zipfile
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from tools.data.qc import BINANCE_METRICS_SCHEMA

CHANGE_DAY = "2026-06-25"


def epoch_us(value: str) -> int:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    if dt.utcoffset() != timedelta(0):
        raise ValueError("NATIVE_UTC_REQUIRED")
    delta = dt-datetime(1970,1,1,tzinfo=UTC)
    return (delta.days*86400+delta.seconds)*1_000_000+delta.microseconds


def scan_archive(path: Path, task: dict, sha256: str, metrics_output: Path | None = None) -> dict:
    family = task["family"]
    rows, metrics, times = 0, [], []
    missing_values = missing_oi = missing_position = offgrid = 0
    native_unit = None
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if (len(members) != 1 or "/" in members[0].filename or "\\" in members[0].filename
                or members[0].file_size > 512*1024**2 or not members[0].filename.endswith(".csv")):
            raise ValueError("UNSAFE_OR_EXPANDED_ARCHIVE_LIMIT")
        with archive.open(members[0]) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            first = next(reader)
            if family == "metrics":
                if first != BINANCE_METRICS_SCHEMA:
                    raise ValueError("METRICS_SCHEMA_MISMATCH")
                data = reader
                native_unit = "UTC_TEXT_LABEL_CONTENT_TIME_UNCONFIRMED"
            else:
                import itertools
                data = reader if not first[0].isdigit() else itertools.chain([first], reader)
            for values in data:
                if not values:
                    continue
                rows += 1
                if family == "metrics":
                    if len(values) != 8 or values[1] != task["symbol"]:
                        raise ValueError("METRICS_CONTRACT_IDENTITY_MISMATCH")
                    t = epoch_us(values[0])
                    numbers = []
                    for value in values[2:]:
                        try:
                            v = float(value)
                        except ValueError:
                            v = math.nan
                        numbers.append(v if math.isfinite(v) and v > 0 else None)
                    offgrid += t % 300_000_000 != 0
                    valid = numbers[0] is not None and numbers[3] is not None and t % 300_000_000 == 0
                    missing_values += not valid
                    missing_oi += numbers[0] is None
                    missing_position += numbers[3] is None
                    metrics.append({"native_label_us":t, "native_create_time":values[0],
                        "content_upper_us_conservative":t+300_000_000,
                        "base_open_interest":numbers[0],"open_interest_notional":numbers[1],
                        "top_account_long_short_ratio":numbers[2],"top_position_long_short_ratio":numbers[3],
                        "global_account_long_short_ratio":numbers[4],"taker_long_short_volume_ratio":numbers[5],
                        "valid_oi_position":valid, "archive_sha256":sha256, "native_symbol":values[1]})
                elif task["venue"] == "binance":
                    if family == "fundingRate":
                        t = int(values[0])*1000
                        native_unit = "ms_EVENT"
                    else:
                        scale = 1 if family == "spot_klines" and task["period"] >= "2025-01" else 1000
                        t = int(values[0])*scale
                        native_unit = "us_INTERVAL_OPEN" if scale == 1 else "ms_INTERVAL_OPEN"
                        if len(values) < 11:
                            raise ValueError("BAR_SCHEMA_MISMATCH")
                elif family == "funding_rates":
                    # Native OKX funding timestamp is the third field; keep all
                    # swap contracts in the raw archive, select no price labels.
                    raw_ts = values[2]
                    t = int(raw_ts)*1000 if raw_ts.isdigit() else epoch_us(raw_ts)
                    native_unit = "ms_EVENT_OR_UTC_TEXT"
                else:
                    continue
                times.append(t)
    if not times or (family == "metrics" and not metrics):
        raise ValueError("EMPTY_NATIVE_TIME_SERIES")
    distinct = sorted(set(times))
    step = 300_000_000 if family == "metrics" else 60_000_000
    gap_slots = sum(max(0,(b-a)//step-1) for a,b in pairwise(distinct)) if family != "fundingRate" and family != "funding_rates" else None
    report = {"rows":rows, "first_native_us":min(times),"last_native_us":max(times),
        "unique_native_timestamps":len(distinct),"duplicate_native_labels":len(times)-len(distinct),
        "internal_missing_grid_slots":gap_slots,"off_grid_rows":offgrid,"missing_oi_position_rows":missing_values,
        "missing_base_oi_rows":missing_oi,"missing_top_position_ratio_rows":missing_position,
        "native_timestamp_unit":native_unit,"receiver_first_known_at":None,"receiver_pit":"PIT_UNKNOWN",
        "price_or_return_labels_computed":0,"zip_crc_full_stream_verified":True}
    if family == "metrics":
        start = epoch_us(task["period"]+"T00:00:00Z")
        offset_first = (min(times)-start)//1_000_000
        offset_last = (max(times)-start)//1_000_000
        pattern = ("END_LABEL_PATTERN" if len(distinct) == 288 and offset_first == 300 and offset_last == 86400 else
                   "START_LABEL_PATTERN" if len(distinct) == 288 and offset_first == 0 and offset_last == 86100 else "PARTIAL_OR_AMBIGUOUS_PATTERN")
        report.update(observed_label_pattern=pattern,first_offset_seconds=offset_first,
            last_offset_seconds=offset_last, reported_change_day=CHANGE_DAY,
            semantics="Pattern observed; 2026-06-25 issue #491 is not provider confirmation. No blind relabeling.",
            conservative_content_end_rule="native_label+5m for every vintage; receiver PIT remains unknown")
        if min(times) < start-300_000_000 or max(times) > start+86_700_000_000:
            raise ValueError("NATIVE_METRICS_DAY_LABEL_MISMATCH")
        if metrics_output is not None:
            metrics_output.parent.mkdir(parents=True, exist_ok=True)
            if not metrics_output.exists():
                pq.write_table(pa.Table.from_pylist(metrics), metrics_output, compression="zstd")
    return report
