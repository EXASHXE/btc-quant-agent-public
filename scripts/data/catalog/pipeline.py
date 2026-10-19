"""Build a source-preserving multi-year SQLite catalog and bounded Parquet examples.

python3 -m scripts.data.catalog.pipeline build --output-dir /root/workspace/project/crypto-data/lakehouse
The catalog is metadata/feature infrastructure, never historical outcome authority.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa

try:
    import resource
except ImportError:  # Windows catalog builds still work without POSIX RSS.
    resource = None

from . import SCHEMA_VERSION
from .alignment import asof_example
from .inventory import coverage, digest, inventory, issues
from .normalize import SCHEMAS, kind, write_sample

ORIGINAL = Path("/root/workspace/project/Quant-agent/data/research")
HISTORICAL = Path("/root/workspace/project/crypto-data/historical")
FORWARD = Path("/root/workspace/project/Quant-agent/data/forward/BTCUSDT")
LAKEHOUSE = Path("/root/workspace/project/crypto-data/lakehouse")


def _rss_kb() -> tuple[int | None, int | None]:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None
    try:
        resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
        current = resident_pages * os.sysconf("SC_PAGE_SIZE") // 1024
    except (OSError, IndexError, ValueError):
        current = None
    return peak, current


def safe_output(path: Path, sources: tuple[Path, ...]) -> Path:
    path = path.absolute()
    if path != LAKEHOUSE and not path.is_relative_to(LAKEHOUSE) and not path.is_relative_to(Path("/tmp")):
        raise ValueError("OUTPUT_OUTSIDE_LAKEHOUSE_OR_TMP")
    if path in (Path("/tmp"), LAKEHOUSE.parent):
        raise ValueError("OUTPUT_ROOT_TOO_BROAD")
    for source in sources:
        source = source.absolute()
        if path.is_relative_to(source) or source.is_relative_to(path):
            raise ValueError("OUTPUT_INPUT_ALIAS")
    for component in (*reversed(path.parents), path):
        if component.is_symlink():
            raise ValueError("OUTPUT_SYMLINK_FORBIDDEN")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode()


def write_json(path: Path, value: Any) -> str:
    temporary = path.with_name("." + path.name + ".partial")
    with temporary.open("wb") as stream:
        raw = _bytes(value)
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    return hashlib.sha256(raw).hexdigest()


def _create_sqlite(path: Path, rows: list[dict[str, Any]], matrix: list[dict[str, Any]],
                   exclusions: list[dict[str, Any]]) -> None:
    temporary = path.with_name("." + path.name + ".partial")
    temporary.unlink(missing_ok=True)
    connection = sqlite3.connect(temporary)
    try:
        connection.executescript("""
        PRAGMA journal_mode=DELETE;
        CREATE TABLE source_files(source_id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE,
            exchange TEXT, asset TEXT, symbol TEXT, product TEXT, family TEXT, interval TEXT,
            period TEXT, calendar_timezone TEXT, start_utc TEXT, end_utc_exclusive TEXT,
            observed_rows INTEGER, gaps INTEGER, duplicates INTEGER, raw_sha256 TEXT,
            manifest_sha256 TEXT, qc_sha256 TEXT, qa_level TEXT, study_scope TEXT,
            priority INTEGER, bytes INTEGER, mtime_ns INTEGER, receiver_pit TEXT,
            forward_state TEXT,
            metadata_json TEXT NOT NULL);
        CREATE TABLE datasets(dataset_id TEXT PRIMARY KEY, exchange TEXT, asset TEXT,
            product TEXT, family TEXT, interval TEXT, source_count INTEGER,
            first_utc TEXT, last_utc_exclusive TEXT);
        CREATE TABLE dataset_coverage(exchange TEXT, asset TEXT, product TEXT, family TEXT,
            interval TEXT, calendar_month TEXT, source_files INTEGER, physical_rows_sum INTEGER,
            reported_gaps_sum INTEGER, utc_start_min TEXT, utc_end_max_exclusive TEXT,
            preferred_source_ids_json TEXT, qa_levels_json TEXT,
            PRIMARY KEY(exchange,asset,product,family,interval,calendar_month));
        CREATE TABLE canonical_instruments(exchange TEXT, native_symbol TEXT, asset TEXT,
            quote_asset TEXT, product TEXT, contract_identity TEXT,
            PRIMARY KEY(exchange,native_symbol,product));
        CREATE TABLE integrity_status(source_id TEXT PRIMARY KEY, qa_level TEXT,
            raw_sha256 TEXT, manifest_sha256 TEXT, receiver_pit TEXT);
        CREATE TABLE exclusion_scope_metadata(name TEXT PRIMARY KEY, dates_utc TEXT,
            policy TEXT, catalog_reads_allowed INTEGER, outcome_authorized INTEGER);
        CREATE TABLE schema_registry(table_name TEXT PRIMARY KEY, schema_version TEXT,
            arrow_schema TEXT, time_semantics TEXT);
        CREATE INDEX idx_source_identity_time ON source_files(exchange,asset,product,family,period);
        """)
        connection.executemany("INSERT INTO source_files VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["source_id"], r["path"], r["exchange"], r["asset"], r["symbol"], r["product"],
              r["family"], r["interval"], r["period"], r["calendar_timezone"],
              r["start_utc"], r["end_utc_exclusive"], r["rows"], r["gaps"], r["duplicates"],
              r["raw_sha256"], r["manifest_sha256"], r.get("qc_sha256"), r["qa_level"],
              r["study_scope"], r["priority"], r["bytes"], r["mtime_ns"], r["receiver_pit"],
              r.get("forward_state"),
              _bytes(r).decode()) for r in rows])
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for r in rows:
            groups.setdefault(tuple(r[k] for k in ("exchange", "asset", "product", "family", "interval")), []).append(r)
        connection.executemany("INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?)",
            [(hashlib.sha256("|".join(key).encode()).hexdigest()[:24], *key, len(group),
              min((r["start_utc"] for r in group if r["start_utc"]), default=None),
              max((r["end_utc_exclusive"] for r in group if r["end_utc_exclusive"]), default=None))
             for key, group in sorted(groups.items())])
        connection.executemany("INSERT INTO dataset_coverage VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["exchange"], r["asset"], r["product"], r["family"], r["interval"], r["calendar_month"],
              r["source_files"], r["physical_rows_sum"], r["reported_gaps_sum"],
              r["utc_start_min"], r["utc_end_max_exclusive"], json.dumps(r["preferred_source_ids"]),
              json.dumps(r["qa_levels"])) for r in matrix])
        instruments = sorted({(r["exchange"], r["symbol"], r["asset"], "USDT", r["product"],
                              r["symbol"] if r["product"] != "SPOT" else "SPOT") for r in rows})
        connection.executemany("INSERT INTO canonical_instruments VALUES (?,?,?,?,?,?)", instruments)
        connection.executemany("INSERT INTO integrity_status VALUES (?,?,?,?,?)",
            [(r["source_id"], r["qa_level"], r["raw_sha256"], r["manifest_sha256"],
              r["receiver_pit"]) for r in rows])
        connection.executemany("INSERT INTO exclusion_scope_metadata VALUES (?,?,?,?,?)",
            [(r["name"], r["dates_utc"], r["policy"], 1, 0) for r in exclusions])
        connection.executemany("INSERT INTO schema_registry VALUES (?,?,?,?)",
            [(name, SCHEMA_VERSION, str(schema),
              "UTC event/sample time separate from unknown receiver first-known")
             for name, schema in sorted(SCHEMAS.items())])
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("CATALOG_SQLITE_INTEGRITY_FAILED")
    finally:
        connection.close()
    os.replace(temporary, path)


def _select_samples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = []
    for row in rows:
        path = row["path"]
        if row["qa_level"] not in ("MANIFEST_PINNED_FOOTER_READ_RAW_NOT_REHASHED",
                                     "PASS_MANIFEST_QC_PINNED_RAW_NOT_REHASHED"):
            continue
        if "/Quant-agent/data/research/BTCUSDT/1m/year=2021/month=01/" in path:
            selected.append(row); continue
        if path.endswith("/cross_asset_1h/ETHUSDT.parquet"):
            selected.append(row); continue
        if "/binance-usdm-2026q2/" in path:
            if (row["period"] == "2026-04" and
                    row["family"] in ("klines", "spot_klines", "markPriceKlines", "fundingRate") and
                    row["asset"] in ("BTC", "ETH")):
                selected.append(row)
            elif row["period"] in ("2026-04-01", "2026-04-02") and row["family"] == "metrics" and row["asset"] in ("BTC", "ETH"):
                selected.append(row)
        if "/okx-swap-2026q2/" in path and row["period"] in ("2026-04-01", "2026-04-02") and \
                row["family"] in ("candlesticks", "spot_candlesticks") and row["asset"] in ("BTC", "ETH"):
            selected.append(row)
    return selected


def _overlap(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = {}
    for r in rows:
        if r["product"] == "FORWARD_PROTECTED":
            continue
        family = "bars" if r["family"] in ("candles", "klines", "candlesticks") else r["family"]
        key = (r["exchange"], r["asset"], r["product"], family, r["period"][:7])
        groups.setdefault(key, []).append(r)
    result = []
    for key, items in sorted(groups.items()):
        priorities = {i["priority"] for i in items}
        if len(priorities) > 1:
            result.append({"identity": key, "source_ids": [i["source_id"] for i in items],
                "preferred_priority": max(priorities), "resolution": "PRIORITY_ONLY_NO_RAW_MERGE"})
    return result


def _q3_intersections(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for asset in ("BTC", "ETH"):
        boundaries = []
        for marker, family in (("/binance-usdm-expansion/", "klines"),
                               ("/okx-swap-expansion/", "candlesticks")):
            selected = [r for r in rows if marker in r["path"] and r["asset"] == asset
                        and r["family"] == family and r["start_utc"] and r["end_utc_exclusive"]
                        and r["qa_level"] == "PASS_MANIFEST_QC_PINNED_RAW_NOT_REHASHED"]
            if not selected:
                break
            boundaries.append((min(datetime.fromisoformat(r["start_utc"]) for r in selected),
                               max(datetime.fromisoformat(r["end_utc_exclusive"]) for r in selected),
                               sum(r["gaps"] or 0 for r in selected)))
        if len(boundaries) == 2:
            left = max(x[0] for x in boundaries)
            right = min(x[1] for x in boundaries)
            result.append({"asset": asset, "intersection_start_utc": left.isoformat(),
                "intersection_end_utc_exclusive": right.isoformat(),
                "intersection_minutes_envelope": max(0, int((right - left).total_seconds() // 60)),
                "reported_source_gaps": {"binance": boundaries[0][2], "okx": boundaries[1][2]},
                "basis": "NATIVE_UTC_SOURCE_WINDOWS_NOT_OKX_FILENAME_DAY"})
    return result


def build(output: Path, original: Path = ORIGINAL, historical: Path = HISTORICAL,
          forward: Path = FORWARD, max_rows_per_source: int = 3000) -> dict[str, Any]:
    started = time.monotonic()
    initial_peak, initial_current = _rss_kb()
    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    output = safe_output(output, (original, historical, forward))
    if not 1 <= max_rows_per_source <= 10000:
        raise ValueError("SCAN_BUDGET_INVALID")
    manifest_paths = [original / "BTCUSDT/data_manifest.json", original / "BTCUSDT_SPOT/data_manifest.json",
        original / "v0.3.19_official_derivatives/raw_data_manifest.json",
        original / "cross_asset_1h/basket_manifest.json"] + [historical / name / file
        for name in ("binance-usdm-2026q2", "binance-usdm-expansion", "okx-swap-2026q2", "okx-swap-expansion")
        for file in ("manifest.json", "qc.json")]
    before = {str(p): digest(p) for p in manifest_paths if p.is_file()}
    rows = inventory(original, historical, forward)
    rss_stages = {"initial_peak_kb": initial_peak, "initial_current_kb": initial_current,
                  "after_inventory_kb": _rss_kb()[1]}
    matrix, gap_report, overlap = coverage(rows), issues(rows), _overlap(rows)
    exclusions = [{"name": name, "dates_utc": dates, "policy": "SCIENTIFIC_OUTCOME_SCOPE_UNRESOLVED"}
                  for name, dates in (("H39", "2026-09-01/2026-10-01"),
                                      ("A_LINE", "UNKNOWN_PRIVATE"), ("FINAL_HOLDOUT", "UNKNOWN_PRIVATE"),
                                      ("FORWARD", "ACTIVE_METADATA_ONLY"), ("OOS", "UNKNOWN_PRIVATE"),
                                      ("H40", "UNKNOWN"))]
    _create_sqlite(output / "catalog.sqlite", rows, matrix, exclusions)
    rss_stages["after_sqlite_kb"] = _rss_kb()[1]
    partitions = []
    for source in _select_samples(rows):
        partitions.append(write_sample(source, output, max_rows_per_source))
        pa.default_memory_pool().release_unused()
    rss_stages["after_parquet_samples_kb"] = _rss_kb()[1]
    asof_rows, asof = asof_example(partitions)
    rss_stages["after_asof_kb"] = _rss_kb()[1]
    if {str(p): digest(p) for p in manifest_paths if p.is_file()} != before:
        raise ValueError("SOURCE_MANIFEST_CHANGED_DURING_BUILD")
    inventory_sha = write_json(output / "source_inventory.json", rows)
    write_json(output / "dataset_coverage_matrix.json", matrix)
    write_json(output / "source_overlap_and_gaps.json", {"overlaps": overlap, "gaps_and_conflicts": gap_report,
        "q3_binance_okx_1m_intersections": _q3_intersections(rows),
        "selection_precedence": "PASS_2026_EXPANSION_OVER_OLDER_OR_PILOT; ORIGINAL_2021_2025_PRIMARY; FORWARD_NEVER_SELECTED",
        "unresolved": ["OLD_BTC_SPOT_PARQUET_VOLUME_ONLY_PRICE_ABSENT",
                        "OLDER_YEARS_OI_NOT_ESTABLISHED", "OKX_DEPTH_NOT_FULL_YEAR",
                        "PRIVATE_RESEARCH_HOLDOUT_DATES_UNKNOWN"]})
    write_json(output / "canonical_schema.json", {"schema_version": SCHEMA_VERSION,
        "tables": {name: str(schema) for name, schema in SCHEMAS.items()},
        "bar_event_rule": "event_ts_utc=exclusive interval end; receiver_first_known_at=NULL",
        "funding_event_rule": "actual settlement timestamp only; not future forecast",
        "price_unit": "USDT per base asset", "okx_swap_native_volume_unit": "contracts; no unverified base conversion"})
    write_json(output / "sample_partitions.json", partitions)
    with (output / "dataset_coverage_matrix.csv").open("w", newline="", encoding="utf-8") as stream:
        names = ("exchange", "asset", "product", "family", "interval", "calendar_month", "source_files",
                 "physical_rows_sum", "reported_gaps_sum", "utc_start_min", "utc_end_max_exclusive",
                 "overlap_or_duplicate_candidate")
        writer = csv.DictWriter(stream, fieldnames=names, extrasaction="ignore")
        writer.writeheader(); writer.writerows(matrix)
    with (output / "asof_features.jsonl").open("w", encoding="utf-8") as stream:
        for row in asof_rows:
            stream.write(_bytes(row).decode())
    write_json(output / "asof_summary.json", asof)
    # Volatile machine metadata is kept out of deterministic scientific artifacts.
    summary = {"status": "DATA_C0_CATALOG_AND_ALIGNMENT_READY", "source_files": len(rows),
        "datasets": len({(r["exchange"], r["asset"], r["product"], r["family"], r["interval"]) for r in rows}),
        "coverage_rows": len(matrix), "sample_partitions": len(partitions),
        "sample_rows": sum(p["sample_rows"] for p in partitions),
        "forward_metadata_files": sum(r["product"] == "FORWARD_PROTECTED" for r in rows),
        "forward_states": dict(sorted(Counter(r.get("forward_state") for r in rows
                                    if r["product"] == "FORWARD_PROTECTED").items())),
        "asof": asof, "real_outcome_labels_read": 0,
        "forward_db_connections": 0, "raw_source_writes": 0,
        "qa_levels": dict(sorted(Counter(r["qa_level"] for r in rows).items())),
        "artifact_sha256": {name: digest(output / name) for name in
            ("catalog.sqlite", "dataset_coverage_matrix.csv", "source_inventory.json",
             "sample_partitions.json", "asof_features.jsonl", "asof_summary.json")},
        "sample_partition_sha256": {p["partition_path"]: p["partition_sha256"] for p in partitions},
        "source_manifests_sha256": before, "runtime_wall_s": round(time.monotonic() - started, 3),
        "max_rss_kb": _rss_kb()[0]}
    summary["rss_stages"] = rss_stages
    write_json(output / "run_receipt.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("build")
    command.add_argument("--output-dir", type=Path, required=True)
    command.add_argument("--original-root", type=Path, default=ORIGINAL)
    command.add_argument("--historical-root", type=Path, default=HISTORICAL)
    command.add_argument("--forward-root", type=Path, default=FORWARD)
    command.add_argument("--max-rows-per-source", type=int, default=3000)
    args = parser.parse_args(argv)
    try:
        result = build(args.output_dir, args.original_root, args.historical_root,
                       args.forward_root, args.max_rows_per_source)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(f"DATA_C0_PARTIAL {exc}", file=sys.stderr)
        return 2
    print(f"{result['status']} source_files={result['source_files']} partitions={result['sample_partitions']} asof_rows={result['asof']['scheduled_origin_asset_rows']} real_outcomes=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
