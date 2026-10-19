"""Metadata-only C0 Forward compatibility and C1/C2 coverage."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

FORWARD_METADATA_ROOT = Path("/root/workspace/project/Quant-agent/data/forward/BTCUSDT/microstructure")
LAKEHOUSE = Path("/root/workspace/project/crypto-data/lakehouse")
MANIFEST_NAMES = ("finalized-partitions.v0316.sha256.json", "closed-partitions.sha256.json")
DAY_NAME = re.compile(r"^microstructure-(20\d{2}-\d{2}-\d{2})\.sqlite3$")
HEX_SHA = re.compile(r"^[0-9a-f]{64}$")


def bounded_json(path: Path, *, maximum: int = 2 * 1024 * 1024) -> tuple[Any, dict[str, Any]]:
    """Reject symlinks and oversized/non-regular JSON before inspection."""
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("MANIFEST_SYMLINK_FORBIDDEN")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        raise ValueError("MANIFEST_NOT_BOUNDED_REGULAR_JSON")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(fd)
        raw = os.read(fd, maximum + 1)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != \
       (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) or \
       (after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns) or \
       len(raw) != before.st_size:
        raise ValueError("MANIFEST_MUTATED_DURING_READ")
    return json.loads(raw), {"path": str(path), "bytes": len(raw), "mtime_ns": before.st_mtime_ns,
                             "sha256": hashlib.sha256(raw).hexdigest()}


def _day(name: str) -> tuple[datetime, datetime] | None:
    match = DAY_NAME.fullmatch(name)
    if not match:
        return None
    start = datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)
    return start, start + timedelta(days=1)


def _valid_final(name: str, item: Any) -> bool:
    day = _day(name)
    return bool(day and isinstance(item, dict) and item.get("immutable") is True and
                isinstance(item.get("sha256"), str) and HEX_SHA.fullmatch(item["sha256"]) and
                isinstance(item.get("eligible_at_ms"), int) and
                isinstance(item.get("finalized_at_ms"), int) and
                item["eligible_at_ms"] >= int(day[1].timestamp() * 1000) and
                item["finalized_at_ms"] >= item["eligible_at_ms"])


def catalog_forward_rows(catalog: Path) -> list[dict[str, Any]]:
    if catalog.suffix != ".sqlite" or FORWARD_METADATA_ROOT in catalog.parents or \
       any(p.is_symlink() for p in (catalog, *catalog.parents)):
        raise ValueError("CATALOG_PATH_INVALID")
    uri = f"file:{catalog}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute("SELECT path,period,raw_sha256,source_id,forward_state,bytes,mtime_ns,"
                          "family,receiver_pit FROM source_files WHERE product='FORWARD_PROTECTED' "
                          "ORDER BY path LIMIT 2001").fetchall()
    if len(rows) > 2000:
        raise ValueError("FORWARD_CATALOG_ROW_BUDGET")
    keys = ("path", "period", "raw_sha256", "source_id", "forward_state", "bytes", "mtime_ns",
            "family", "receiver_pit")
    return [dict(zip(keys, row)) for row in rows]


def _overlaps(start: datetime, end: datetime, coverage: list[dict], *, system: str) -> list[dict]:
    result = []
    for row in coverage:
        if row.get("asset") != "BTC":
            continue
        if system == "C1":
            if row.get("coverage_mode") != "PHYSICAL_FULL_PARTITIONS":
                continue
            a = datetime.fromisoformat(row["utc_start_min"])
            b = datetime.fromisoformat(row["utc_end_max"])
            # Coverage rows report last observed open/event timestamp, not an exclusive bound.
            b += timedelta(minutes=1) if row.get("interval") == "1m" else timedelta(microseconds=1)
            family = row["table"]
            market = (row["exchange"], row["asset"], row["product"])
            gaps = row.get("reported_gaps_sum")
        else:
            if row.get("status") != "COMPLETED" or not row.get("partition_sha256"):
                continue
            a = datetime.fromisoformat(row["month"] + "-01").replace(tzinfo=UTC)
            b = datetime(a.year + a.month // 12, a.month % 12 + 1, 1, tzinfo=UTC)
            family = row["family"]
            market = (row["exchange"], row["asset"], row["product"])
            gaps = None
        left, right = max(start, a), min(end, b)
        if left < right:
            result.append({"system": system, "exchange": market[0], "asset": market[1],
                           "product": market[2], "family": family,
                           "overlap_start_utc": left.isoformat(), "overlap_end_utc_exclusive": right.isoformat(),
                           "reported_gaps": gaps,
                           "overlap_basis": "NOMINAL_FORWARD_UTC_DAY_VS_HISTORICAL_COVERAGE_NOT_PAYLOAD_MATCH"})
    return sorted(result, key=lambda r: (r["system"], r["exchange"], r["product"], r["family"], r["overlap_start_utc"]))


def metadata_matrix(rows: list[dict], final: dict, closed: dict, c1: list[dict], c2: list[dict]) -> list[dict]:
    if not isinstance(final, dict) or not isinstance(final.get("partitions"), dict) or \
       final.get("protocol_id") != "MICROSTRUCTURE_RELIABILITY_V0316_001" or not isinstance(closed, dict):
        raise ValueError("FINALIZATION_SCHEMA_INVALID")
    names = set(final["partitions"]) | set(closed)
    if any(_day(name) is None for name in names):
        raise ValueError("FINALIZATION_PARTITION_NAME_INVALID")
    result = []
    for row in rows:
        path = Path(row["path"])
        day = _day(path.name) if path.parent == FORWARD_METADATA_ROOT else None
        name = path.name if day else None
        claim = final["partitions"].get(name) if name else None
        old_hash = closed.get(name) if name else None
        valid = bool(claim and _valid_final(name, claim) and row["period"] == day[0].date().isoformat())
        cross_hash = bool(valid and old_hash == claim["sha256"])
        c0_hash_match = bool(valid and row["raw_sha256"] == claim["sha256"])
        mismatch = bool(claim and (not valid or (old_hash and old_hash != claim.get("sha256")) or
                                   (row["raw_sha256"] and not c0_hash_match)))
        if mismatch:
            state = "MANIFEST_MISMATCH_DEFAULT_DENY"
        elif cross_hash or c0_hash_match:
            state = "CLOSE_VERIFIED_METADATA_LINKED"
        elif valid:
            state = "FINALIZATION_CLAIM_UNCORROBORATED"
        else:
            state = "C0_STATE_ONLY_UNVERIFIED"
        overlap = _overlaps(*day, c1, system="C1") + _overlaps(*day, c2, system="C2") if day else []
        result.append({"source_id": row["source_id"], "partition_path": row["path"],
                       "partition_date_utc": day[0].date().isoformat() if day else None,
                       "nominal_start_utc": day[0].isoformat() if day else None,
                       "nominal_end_utc_exclusive": day[1].isoformat() if day else None,
                       "c0_forward_state": row["forward_state"], "closed_state": state,
                       "manifest_sha256_claim": claim.get("sha256") if isinstance(claim, dict) else None,
                       "c0_sha256": row["raw_sha256"], "closed_manifest_hash_corroborates": cross_hash,
                       "c0_hash_matches_finalization": c0_hash_match,
                       "finalized_at_utc": datetime.fromtimestamp(claim["finalized_at_ms"] / 1000, UTC).isoformat()
                       if valid else None,
                       "receiver_clock_proof": "UNKNOWN_NO_PAYLOAD_OR_RECEIVER_LOG_INSPECTED",
                       "later_read_access": "DEFAULT_DENY", "rights_state": "SOURCE_NOT_ADMITTED",
                       "historical_overlap": overlap,
                       "unknowns": ["ACTUAL_DB_SHA_NOT_REHASHED", "RECEIVER_FIRST_KNOWN_NOT_PROVEN",
                                    "FORWARD_PAYLOAD_COVERAGE_UNKNOWN", "SOURCE_RIGHTS_UNRESOLVED"]})
    catalog_paths = {r["path"] for r in rows}
    for name in sorted(names):
        if str(FORWARD_METADATA_ROOT / name) not in catalog_paths:
            raise ValueError("FINALIZATION_WITHOUT_C0_PATH_MATCH")
    return result


def write_matrix_csv(path: Path, rows: list[dict]) -> None:
    fields = ("source_id", "partition_path", "partition_date_utc", "c0_forward_state", "closed_state",
              "manifest_sha256_claim", "c0_sha256", "closed_manifest_hash_corroborates",
              "receiver_clock_proof", "later_read_access", "rights_state")
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, data: Any) -> str:
    raw = (json.dumps(data, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    temporary = path.with_name("." + path.name + ".partial")
    temporary.write_bytes(raw)
    os.replace(temporary, path)
    return hashlib.sha256(raw).hexdigest()


def _canonical_clock(row: dict, *, kind: str, stream: str, product: str):
    from .forward_clock import ClockRecord

    native = row.get("source_native_ts")
    return ClockRecord(exchange="binance", instrument="BTCUSDT", product=product,
                       stream=stream, kind=kind, event_ts_utc=row["event_ts_utc"],
                       source_native_ts=int(native) if native is not None else None,
                       source_time_unit=row.get("source_time_unit") if native is not None else None,
                       source_native_clock_role="DERIVED_INTERVAL_OPEN" if kind == "flow" else
                                                "INTERVAL_OPEN" if kind == "bar" else "EVENT_TS",
                       source_id=row["source_id"], raw_sha256=row["raw_sha256"],
                       interval_open=row.get("interval_start_utc"),
                       interval_close=row.get("interval_end_utc"),
                       last_contributing_event=None,
                       receiver_first_known_at=row.get("receiver_first_known_at"),
                       exchange_published_at=row.get("exchange_published_at"),
                       local_ingested_at=row.get("local_ingested_at"),
                       evidence="HISTORY_ARCHIVE", precision=row.get("source_time_unit") or "UNKNOWN")


def demonstration() -> dict:
    """Read bounded C1/C2 feature columns; never query Forward or outcomes."""
    from .flow_query import FlowQueryEngine
    from .forward_clock import ClockRecord, evaluate_asof
    from .query import CanonicalQueryEngine

    history_origin = datetime(2023, 8, 15, 12, 1, tzinfo=UTC)
    cutoff = history_origin - timedelta(minutes=1)
    c1 = CanonicalQueryEngine()
    c2 = FlowQueryEngine()
    columns = ["event_ts_utc", "interval_start_utc", "interval_end_utc", "source_native_ts",
               "source_time_unit", "receiver_first_known_at", "exchange_published_at",
               "local_ingested_at", "source_id", "raw_sha256"]
    bars = c1.query_range("bars", "binance", "BTC", "USD_M_PERPETUAL",
                          cutoff - timedelta(minutes=3), cutoff, columns=columns)
    funding = c1.query_range("funding_settlements", "binance", "BTC", "USD_M_PERPETUAL",
                             cutoff - timedelta(days=1), cutoff, columns=columns)
    flow = c2.query_flow_range("binance", "BTC", "USD_M_PERPETUAL",
                               cutoff - timedelta(hours=1), cutoff, columns=columns)
    cases = [
        ([_canonical_clock(r, kind="bar", stream="bars_1m", product="USD_M_PERPETUAL") for r in bars],
         "bars_1m", "bar", {}),
        ([_canonical_clock(r, kind="funding", stream="funding_settlements", product="USD_M_PERPETUAL") for r in funding],
         "funding_settlements", "funding", {}),
    ]
    for minutes in (1, 5, 60):
        cases.append(([_canonical_clock(r, kind="flow", stream="perp_aggTrades_1m",
                                       product="USD_M_PERPETUAL") for r in flow],
                      "perp_aggTrades_1m", "flow", {"flow_minutes": minutes}))
    historical = {}
    for records, stream, kind, extra in cases:
        historical[stream + (f"_{extra['flow_minutes']}m" if extra else "")] = {
            mode: evaluate_asof(records, origin=history_origin, exchange="binance",
                                instrument="BTCUSDT", product="USD_M_PERPETUAL",
                                stream=stream, kind=kind, mode=mode, **extra)
            for mode in ("DESCRIPTIVE_EVENT_TIME", "RECEIVER_PIT_REQUIRED")}
    synthetic_origin = datetime(2026, 10, 18, 12, 1, tzinfo=UTC)
    synthetic_cutoff = synthetic_origin - timedelta(minutes=1)
    base = {"exchange": "binance", "instrument": "BTCUSDT", "product": "USD_M_PERPETUAL",
            "stream": "bars_1m", "kind": "bar", "source_id": "TEST_ONLY_SYNTHETIC_BAR",
            "raw_sha256": "a" * 64, "interval_open": synthetic_cutoff - timedelta(minutes=2),
            "interval_close": synthetic_cutoff - timedelta(minutes=1),
            "event_ts_utc": synthetic_cutoff - timedelta(minutes=1),
            "source_native_ts": int((synthetic_cutoff - timedelta(minutes=1)).timestamp() * 1000),
            "source_time_unit": "ms", "evidence": "TEST_ONLY_SYNTHETIC",
            "receiver_proof": "TEST_ONLY_SYNTHETIC", "precision": "ms"}
    good = ClockRecord(**base, receiver_first_known_at=synthetic_cutoff + timedelta(seconds=20),
                       local_ingested_at=synthetic_cutoff + timedelta(seconds=30),
                       durable_committed_at=synthetic_cutoff + timedelta(seconds=40))
    late = ClockRecord(**base, receiver_first_known_at=synthetic_origin + timedelta(seconds=10))
    synthetic = {name: evaluate_asof([record], origin=synthetic_origin, exchange="binance",
                                     instrument="BTCUSDT", product="USD_M_PERPETUAL", stream="bars_1m",
                                     kind="bar", mode="RECEIVER_PIT_REQUIRED")
                 for name, record in (("known_before_origin", good), ("arrived_after_origin", late))}
    return {"historical_feature_only_BTC": historical, "synthetic_forward_fixture_TEST_ONLY_SYNTHETIC": synthetic,
            "historical_origin_utc": history_origin.isoformat(),
            "historical_receiver_pit": "UNKNOWN", "historical_oi": "UNAVAILABLE_IN_C1_2023_08",
            "real_outcome_labels_read": 0, "forward_db_connections": 0,
            "interpretation": "Feature timestamps only; no actual Forward source admission or Alpha conclusion"}


def build(output: Path = LAKEHOUSE / "c3", catalog: Path = LAKEHOUSE / "catalog.sqlite",
          forward_root: Path = FORWARD_METADATA_ROOT) -> dict:
    if output != LAKEHOUSE / "c3" and not output.is_relative_to(Path("/tmp")):
        raise ValueError("OUTPUT_SCOPE_INVALID")
    if output.is_symlink():
        raise ValueError("OUTPUT_SYMLINK_FORBIDDEN")
    output.mkdir(parents=True, exist_ok=True)
    final, final_receipt = bounded_json(forward_root / MANIFEST_NAMES[0])
    closed, closed_receipt = bounded_json(forward_root / MANIFEST_NAMES[1])
    c1, c1_receipt = bounded_json(LAKEHOUSE / "c1/actual_full_coverage_matrix.json")
    c2, c2_receipt = bounded_json(LAKEHOUSE / "c2/source_flow_coverage.json")
    c0_rows = catalog_forward_rows(catalog)
    matrix = metadata_matrix(c0_rows, final, closed, c1, c2)
    states = {state: sum(r["closed_state"] == state for r in matrix)
              for state in sorted({r["closed_state"] for r in matrix})}
    hashes = {}
    hashes["forward_metadata_matrix.json"] = _write_json(output / "forward_metadata_matrix.json", matrix)
    write_matrix_csv(output / "forward_metadata_matrix.csv", matrix)
    hashes["forward_metadata_matrix.csv"] = hashlib.sha256((output / "forward_metadata_matrix.csv").read_bytes()).hexdigest()
    schema = {
        "schema_version": "DATA_C3_CLOCK_V1", "timestamp_timezone": "UTC", "timestamp_precision": "native s/ms/us; normalized us",
        "identity": ["exchange", "instrument", "product", "stream", "source_id", "raw_sha256"],
        "native_clocks": {"event_ts_utc": "required UTC event or settlement timestamp",
                          "source_native_ts": "original integer, nullable only when unavailable",
                          "source_native_clock_role": "EVENT_TS or INTERVAL_OPEN; C2 flow uses DERIVED_INTERVAL_OPEN, not raw trade time",
                          "source_time_unit": "s|ms|us, explicit; no mixed group units",
                          "exchange_published_at": "nullable, only if actually present",
                          "receiver_first_known_at": "nullable, measured receiver evidence only",
                          "local_ingested_at": "nullable, actual local ingest time",
                          "durable_committed_at": "nullable, actual durable commit time",
                          "archive_downloaded_at": "nullable, separate from live known-at"},
        "derived_clocks": ["interval_open", "interval_close", "last_contributing_event", "availability_gate"],
        "availability_gate": "max of observed event, close, contributing event, publish, receiver, ingest, durable commit; UNKNOWN if receiver missing",
        "quality_classes": ["ARCHIVE_EVENT_ONLY", "RECEIVER_OBSERVED", "SYNTHETIC_RECEIVER_DEFINED",
                            "FORWARD_CLOSED_MANIFEST_ONLY", "UNKNOWN"],
        "modes": ["DESCRIPTIVE_EVENT_TIME", "RECEIVER_PIT_REQUIRED"],
        "asof": {"origin": "HH:01 UTC", "cutoff": "HH:00 UTC", "bar": "last 1m OHLC end strictly before cutoff",
                 "flow": "1m, 5m, or 60m complete minutes ending at cutoff",
                 "oi": "5m sample in cutoff-10m..cutoff-5m plus exact 4h predecessor",
                 "funding": "latest actual previous settlement strictly before cutoff; no forecast"},
        "provenance": "source archive/download is not receiver availability; OKX trades/kline archive filename dates are UTC+8 labels, actual epoch times remain UTC",
        "unknown_policy": "missing receiver, source gaps, duplicates, stale watermark, late ingest, hash mismatch => NO_ACTION in receiver mode",
        "rights": "SOURCE_NOT_ADMITTED"}
    hashes["clock_contract_schema.json"] = _write_json(output / "clock_contract_schema.json", schema)
    completed_c2 = [r for r in c2 if r.get("status") == "COMPLETED" and r.get("partition_sha256")]
    coverage = {"c1_BTC_full_partition_rows": [r for r in c1 if r.get("asset") == "BTC"],
                "c2_BTC_completed": [{k: r.get(k) for k in ("exchange", "asset", "product", "family", "month",
                                                "minute_rows", "partition_sha256", "status")}
                                     for r in completed_c2 if r.get("asset") == "BTC"],
                "c2_completed_months": sorted({r["month"] for r in completed_c2}),
                "c2_2026_completed_overlap": any(r["month"].startswith("2026-") for r in completed_c2),
                "forward_nominal_day_overlaps": [{"partition_date_utc": r["partition_date_utc"],
                                                  "historical_overlap": r["historical_overlap"]}
                                                 for r in matrix if r["historical_overlap"]],
                "join_rule": "exact exchange, instrument, product and family required; coverage overlap is not payload equivalence",
                "calendar_note": "Forward filenames encode nominal UTC day only; OKX archive file-day names may be UTC+8"}
    hashes["historical_vs_forward_coverage.json"] = _write_json(output / "historical_vs_forward_coverage.json", coverage)
    gap = {"forward_receiver_proof_unknown_count": len(matrix),
           "c0_unverified_count": sum(r["closed_state"] != "CLOSE_VERIFIED_METADATA_LINKED" for r in matrix),
           "c0_missing_database_hash_count": sum(r["partition_date_utc"] is not None and r["c0_sha256"] is None for r in matrix),
           "c1_archive_event_only": True, "c2_archive_event_only": True,
           "historical_2023_08_oi": "UNAVAILABLE", "forward_payload_and_receiver_log": "NOT_READ",
           "gaps_and_dedup": "Source coverage reports can flag reported gaps; no Forward payload gap/dedup proof",
           "receiver_PIT_claim": "PIT_UNKNOWN", "rights": "SOURCE_NOT_ADMITTED"}
    hashes["receiver_pit_gap_report.json"] = _write_json(output / "receiver_pit_gap_report.json", gap)
    demo = demonstration()
    hashes["demo_asof_report.json"] = _write_json(output / "demo_asof_report.json", demo)
    receipt = {"status": "DATA_C3_CLOCK_CONTRACT_READY", "input_json": [final_receipt, closed_receipt,
                                                                          c1_receipt, c2_receipt],
               "c0_catalog": {"path": str(catalog), "sha256": hashlib.sha256(catalog.read_bytes()).hexdigest()},
               "c0_forward_rows": len(c0_rows), "closed_states": states, "output_sha256": hashes,
               "forward_db_connections": 0, "forward_db_payload_reads": 0, "historical_real_outcome_labels_read": 0,
               "access": "P3_ACCESS_SCOPE_HOLD", "source": "SOURCE_NOT_ADMITTED", "pit": "PIT_UNKNOWN",
               "alpha": "NO_ALPHA_ESTABLISHED", "gates": ["G2_ALPHA_NO_GO", "G4_TESTNET_NO_GO", "LIVE_NO_GO",
                                                         "REAL_FUNDS_WRITE_NONE"]}
    _write_json(output / "source_manifest_receipt.json", receipt)
    return receipt


def main() -> int:
    try:
        result = build()
    except (OSError, ValueError, sqlite3.Error, KeyError) as exc:
        print(f"DATA_C3_PARTIAL: {exc}", file=sys.stderr)
        return 2
    print(f"{result['status']} forward_rows={result['c0_forward_rows']} states={result['closed_states']} "
          "forward_db_connections=0 outcome_labels=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
