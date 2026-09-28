"""Blind, source-only audit of official Binance USD-M 1h kline archives.

This tool emits hashes and integrity counts. It never emits economic row values.
Every archive is verified against a freshly retrieved official .CHECKSUM file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import itertools
import json
import re
import time
import zipfile
from bisect import bisect_left
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

HOUR_MS = 3_600_000
SOURCE_START_MS = 1609459200000
SOURCE_END_MS = 1682899200000
FROZEN_CALIBRATION_HOURS = 2184
SOURCE_REQUIREMENTS_HASH = "04845354af6c22f88a55da74aa4fdf8393277e28447c9d57b84a718e8aecb581"
FROZEN_SEMANTIC_ROOT = "f784ce4cfe7ba4d1d5d30582e59ab4811aa7b1e8aed79b00a5f5e0f200c26917"
PARTITIONS = {
    "WF1_TRAIN": ("2021-01-01", "2022-10-31"),
    "WF1_PURGE_1": ("2022-10-31", "2022-11-01"),
    "WF1_CALIBRATION": ("2022-11-01", "2023-01-31"),
    "WF1_PURGE_2": ("2023-01-31", "2023-02-01"),
    "WF1_VALIDATION": ("2023-02-01", "2023-04-30"),
}
OFFICIAL_ROOT = "https://data.binance.vision/data/futures/um/monthly/klines"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _number(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("malformed numeric source field") from exc
    if not value.is_finite():
        raise ValueError("nonfinite numeric source field")
    return value


def _canonical_number(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def partition_hours() -> dict[str, int]:
    return {
        name: int(
            (datetime.fromisoformat(end).replace(tzinfo=UTC)
             - datetime.fromisoformat(start).replace(tzinfo=UTC)).total_seconds() // 3600
        )
        for name, (start, end) in PARTITIONS.items()
    }


def _month_bounds(month: str) -> tuple[int, int]:
    year, number = map(int, month.split("-"))
    start = datetime(year, number, 1, tzinfo=UTC)
    end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=UTC)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def audit_archive(
    path: Path, symbol: str, month: str, expected_sha256: str,
    projection_sink: Any = None,
) -> dict[str, Any]:
    """Hash one byte buffer, then parse precisely that buffer; never print OHLC."""
    if symbol not in {"BTCUSDT", "ETHUSDT"}:
        raise ValueError("unsupported symbol")
    expected_name = f"{symbol}-1h-{month}.zip"
    if not path.exists() and not path.is_symlink():
        raise FileNotFoundError("source archive bytes missing")
    if path.name != expected_name or path.is_symlink() or not path.is_file():
        raise ValueError("wrong archive product, symbol, month, or path type")
    if HEX64.fullmatch(expected_sha256) is None:
        raise ValueError("missing official archive checksum")
    raw = path.read_bytes()
    actual_sha = sha256(raw)
    if actual_sha != expected_sha256:
        raise ValueError("archive checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if len(members) != 1 or members[0].filename != f"{symbol}-1h-{month}.csv":
            raise ValueError("archive member does not match symbol/interval/month")
        csv_bytes = archive.read(members[0])
    try:
        rows = csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig")))
        parsed = list(rows)
    except UnicodeDecodeError as exc:
        raise ValueError("archive CSV encoding invalid") from exc
    if parsed and not parsed[0][0].isdigit():
        parsed = parsed[1:]
    lower, upper = _month_bounds(month)
    timestamps: list[int] = []
    seen: set[int] = set()
    duplicate = gap = invalid_ohlc = invalid_volume = alignment = close_time = 0
    monotonic_errors = 0
    projection = hashlib.sha256()
    previous_time: int | None = None
    for row in parsed:
        if len(row) != 12:
            raise ValueError("malformed Binance USD-M kline row")
        try:
            timestamp = int(row[0])
            row_close_time = int(row[6])
            trades = int(row[8])
        except ValueError as exc:
            raise ValueError("malformed kline timestamp or trade count") from exc
        if not lower <= timestamp < upper:
            raise ValueError("archive contains row outside named UTC month")
        prices = [_number(row[i]) for i in (1, 2, 3, 4)]
        volumes = [_number(row[i]) for i in (5, 7, 9, 10)]
        op, hi, lo, cl = prices
        invalid_ohlc += int(not (lo > 0 and lo <= op <= hi and lo <= cl <= hi))
        invalid_volume += int(trades < 0 or any(value < 0 for value in volumes))
        alignment += int(timestamp % HOUR_MS != 0)
        close_time += int(row_close_time != timestamp + HOUR_MS - 1)
        duplicate += int(timestamp in seen)
        if previous_time is not None:
            monotonic_errors += int(timestamp <= previous_time)
            if timestamp > previous_time + HOUR_MS:
                gap += (timestamp - previous_time) // HOUR_MS - 1
        projection_row = {
            "symbol": symbol, "market": "USD-M PERPETUAL", "interval": "1h",
            "open_time_ms": timestamp, "close_time_ms": row_close_time,
            "open": _canonical_number(op), "high": _canonical_number(hi),
            "low": _canonical_number(lo), "close": _canonical_number(cl),
            "volume": _canonical_number(volumes[0]),
            "quote_volume": _canonical_number(volumes[1]), "trades": trades,
            "taker_buy_base_volume": _canonical_number(volumes[2]),
            "taker_buy_quote_volume": _canonical_number(volumes[3]),
        }
        canonical_row = canonical_json(projection_row) + b"\n"
        projection.update(canonical_row)
        if projection_sink is not None:
            projection_sink.update(canonical_row)
        seen.add(timestamp)
        timestamps.append(timestamp)
        previous_time = timestamp
    return {
        "symbol": symbol, "market": "USD-M PERPETUAL", "provider": "Binance Public Data",
        "source_mode": "OFFICIAL_NATIVE_USDM_1H", "archive_name": expected_name,
        "archive_url": f"{OFFICIAL_ROOT}/{symbol}/1h/{expected_name}",
        "official_archive_checksum": expected_sha256, "local_archive_sha256": actual_sha,
        "raw_csv_sha256": sha256(csv_bytes), "projection_hash": projection.hexdigest(),
        "timestamp_membership_hash": sha256(canonical_json(timestamps)),
        "timestamps_ms": timestamps, "first_timestamp": _iso(timestamps[0]) if timestamps else None,
        "last_timestamp": _iso(timestamps[-1]) if timestamps else None,
        "row_count": len(timestamps), "duplicate_count": duplicate, "gap_count": gap,
        "invalid_ohlc_count": invalid_ohlc, "invalid_volume_count": invalid_volume,
        "alignment_errors": alignment, "close_time_errors": close_time,
        "monotonic_errors": monotonic_errors,
        "same_buffer_hash_parse": True,
    }


def synchronize(btc: list[int], eth: list[int]) -> dict[str, Any]:
    btc_set, eth_set = set(btc), set(eth)
    joint = sorted(btc_set & eth_set)
    return {
        "btc_only_count": len(btc_set - eth_set),
        "eth_only_count": len(eth_set - btc_set),
        "btc_timestamp_membership_hash": sha256(canonical_json(btc)),
        "eth_timestamp_membership_hash": sha256(canonical_json(eth)),
        "joint_timestamp_membership_hash": sha256(canonical_json(joint)),
    }


def public_receipt(audit: dict[str, Any]) -> dict[str, Any]:
    """Publish an explicit allowlist of source metadata; never publish economic rows."""
    allowed = (
        "symbol", "market", "provider", "source_mode", "archive_name", "archive_url",
        "official_archive_checksum", "local_archive_sha256", "raw_csv_sha256",
        "archive_records", "projection_hash", "timestamp_membership_hash",
        "first_timestamp", "last_timestamp", "row_count", "duplicate_count",
        "gap_count", "invalid_ohlc_count", "invalid_volume_count",
        "alignment_errors", "close_time_errors", "monotonic_errors",
        "unexpected_timestamp_count", "gap_timestamps", "gap_timestamp_inventory_hash",
        "partition_membership_counts",
        "same_buffer_hash_parse", "projection_replay",
        "official_checksum_origin_independently_verified",
    )
    receipt = {key: audit[key] for key in allowed if key in audit}
    receipt.update({
        "schema_id": "H41CanonicalSourceReceiptV1",
        "asset": "BTC" if audit["symbol"] == "BTCUSDT" else "ETH",
        "venue": "Binance Futures", "product": "USD-M PERPETUAL",
        "interval": "1h", "timezone": "UTC",
        "raw_archive_root": f"{OFFICIAL_ROOT}/{audit['symbol']}/1h",
        "source_archive_set_hash": sha256(canonical_json(audit.get("archive_records", [{
            "archive_url": audit.get("archive_url"),
            "local_archive_sha256": audit.get("local_archive_sha256"),
        }]))),
        "canonical_projection_hash": audit["projection_hash"],
        "protected_value_exposure": "ZERO",
        "source_finalization_semantics": "Exchange bucket closes at T_k + 1h; no local receipt timestamp",
        "revision_semantics": "exact archive bytes bound by official checksum; replacement changes authority",
        "source_authority_status": audit.get("source_authority_status", "INCOMPLETE_DIAGNOSTIC_ONLY"),
    })
    return receipt


def authority_root(btc: dict[str, Any], eth: dict[str, Any], joint_hash: str) -> str:
    payload = {
        "schema_id": "H41_CANONICAL_SOURCE_AUTHORITY_ROOT_V1",
        "btc_receipt_hash": sha256(canonical_json(btc)),
        "eth_receipt_hash": sha256(canonical_json(eth)),
        "btc_canonical_projection_hash": btc["projection_hash"],
        "eth_canonical_projection_hash": eth["projection_hash"],
        "joint_timestamp_membership_hash": joint_hash,
        "frozen_source_requirements_hash": SOURCE_REQUIREMENTS_HASH,
        "frozen_protocol_semantic_root": FROZEN_SEMANTIC_ROOT,
    }
    return sha256(canonical_json(payload))


def evaluate_invariants(
    btc: dict[str, Any], eth: dict[str, Any], *, full_coverage: bool,
) -> dict[str, str]:
    audits = (btc, eth)
    joint = synchronize(btc["timestamps_ms"], eth["timestamps_ms"])
    exact_count = (SOURCE_END_MS - SOURCE_START_MS) // HOUR_MS
    full = full_coverage and all(
        audit["row_count"] == exact_count
        and bool(audit["timestamps_ms"])
        and audit["timestamps_ms"][0] == SOURCE_START_MS
        and audit["timestamps_ms"][-1] == SOURCE_END_MS - HOUR_MS
        and audit.get("unexpected_timestamp_count", 0) == 0
        for audit in audits
    )
    expected_partition_hours = {
        "WF1_TRAIN": 16032, "WF1_PURGE_1": 24,
        "WF1_CALIBRATION": 2184, "WF1_PURGE_2": 24,
        "WF1_VALIDATION": 2112,
    }
    checks = {
        "S01": all(a.get("provider") == "Binance Public Data" and
                   a.get("official_checksum_origin_independently_verified", False)
                   for a in audits),
        "S02": all(a.get("market") == "USD-M PERPETUAL" and
                   a.get("source_mode") == "OFFICIAL_NATIVE_USDM_1H" for a in audits),
        "S03": btc["symbol"] == "BTCUSDT" and eth["symbol"] == "ETHUSDT",
        "S04": full and all(a["gap_count"] == 0 and a["duplicate_count"] == 0 for a in audits),
        "S05": all(a["alignment_errors"] == 0 for a in audits),
        "S06": all(a["close_time_errors"] == 0 for a in audits),
        "S07": all(a["monotonic_errors"] == 0 for a in audits),
        "S08": all(a["duplicate_count"] == 0 for a in audits),
        "S09": full and all(a["gap_count"] == 0 for a in audits),
        "S10": all(a["invalid_ohlc_count"] == 0 for a in audits),
        "S11": all(a["invalid_volume_count"] == 0 for a in audits),
        "S12": all(
            a.get("official_checksum_origin_independently_verified", False)
            and all(record["official_archive_checksum"] == record["local_archive_sha256"]
                    for record in a.get("archive_records", [])) for a in audits
        ),
        "S13": all(a["same_buffer_hash_parse"] for a in audits),
        "S14": all(a.get("projection_replay", False) for a in audits),
        "S15": full and joint["btc_only_count"] == joint["eth_only_count"] == 0,
        "S16": full and partition_hours() == expected_partition_hours
        and partition_hours()["WF1_CALIBRATION"] == FROZEN_CALIBRATION_HOURS
        and all(a.get("partition_membership_counts") == expected_partition_hours for a in audits),
    }
    return {key: "PASS" if result else "FAIL" for key, result in checks.items()}


def _months() -> list[str]:
    months: list[str] = []
    year, month = 2021, 1
    while (year, month) < (2023, 5):
        months.append(f"{year:04d}-{month:02d}")
        year, month = year + (month == 12), month % 12 + 1
    return months


def _fetch_official_checksum(url: str) -> bytes:
    if not url.startswith(OFFICIAL_ROOT + "/") or not url.endswith(".zip.CHECKSUM"):
        raise ValueError("invalid official checksum URL")
    for attempt in range(3):
        try:
            with urlopen(url, timeout=30) as response:
                return response.read(256)
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(0.25 * (attempt + 1))
    raise AssertionError("unreachable checksum retry state")


def _official_digest(checksum_bytes: bytes, archive_name: str) -> str:
    try:
        checksum = checksum_bytes.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("invalid official checksum encoding") from exc
    match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9-]+\.zip)", checksum)
    if match is None or match.group(2) != archive_name:
        raise ValueError("invalid official checksum record")
    return match.group(1)


def _audit_asset(archive_root: Path, symbol: str) -> dict[str, Any]:
    timestamps: list[int] = []
    records: list[dict[str, Any]] = []
    projection = hashlib.sha256()
    counts = {key: 0 for key in (
        "duplicate_count", "invalid_ohlc_count", "invalid_volume_count",
        "alignment_errors", "close_time_errors", "monotonic_errors",
    )}
    for month in _months():
        name = f"{symbol}-1h-{month}.zip"
        url = f"{OFFICIAL_ROOT}/{symbol}/1h/{name}"
        checksum_bytes = _fetch_official_checksum(url + ".CHECKSUM")
        official_sha = _official_digest(checksum_bytes, name)
        audit = audit_archive(archive_root / symbol / name, symbol, month, official_sha, projection)
        timestamps.extend(audit["timestamps_ms"])
        for key in counts:
            counts[key] += audit[key]
        records.append({
            "archive_name": name, "archive_url": url,
            "official_checksum_url": url + ".CHECKSUM",
            "official_checksum_file_sha256": sha256(checksum_bytes),
            "official_archive_checksum": official_sha,
            "local_archive_sha256": audit["local_archive_sha256"],
            "raw_csv_sha256": audit["raw_csv_sha256"],
            "canonical_projection_hash": audit["projection_hash"],
            "timestamp_membership_hash": audit["timestamp_membership_hash"],
            "row_count": audit["row_count"],
        })
    counts["duplicate_count"] = len(timestamps) - len(set(timestamps))
    counts["monotonic_errors"] = sum(
        left >= right for left, right in itertools.pairwise(timestamps)
    )
    expected = set(range(SOURCE_START_MS, SOURCE_END_MS, HOUR_MS))
    actual = set(timestamps)
    gaps = sorted(expected - actual)
    partition_counts = {
        name: bisect_left(timestamps, _month_or_day_ms(end))
        - bisect_left(timestamps, _month_or_day_ms(start))
        for name, (start, end) in PARTITIONS.items()
    }
    replay = hashlib.sha256()
    for record in records:
        month = record["archive_name"][-11:-4]
        second = audit_archive(
            archive_root / symbol / record["archive_name"], symbol,
            month, record["official_archive_checksum"], replay,
        )
        if second["projection_hash"] != record["canonical_projection_hash"]:
            raise ValueError("source projection replay mismatch")
    if replay.hexdigest() != projection.hexdigest():
        raise ValueError("source projection replay mismatch")
    return {
        "symbol": symbol, "market": "USD-M PERPETUAL", "provider": "Binance Public Data",
        "source_mode": "OFFICIAL_NATIVE_USDM_1H", "archive_records": records,
        "projection_hash": projection.hexdigest(),
        "timestamp_membership_hash": sha256(canonical_json(timestamps)),
        "timestamps_ms": timestamps,
        "first_timestamp": _iso(timestamps[0]) if timestamps else None,
        "last_timestamp": _iso(timestamps[-1]) if timestamps else None,
        "row_count": len(timestamps), "gap_count": len(gaps),
        "gap_timestamps": [_iso(timestamp) for timestamp in gaps],
        "gap_timestamp_inventory_hash": sha256(canonical_json(gaps)),
        "unexpected_timestamp_count": len(actual - expected),
        "partition_membership_counts": partition_counts,
        "same_buffer_hash_parse": True, "projection_replay": True,
        "official_checksum_origin_independently_verified": True,
        **counts,
    }


def _month_or_day_ms(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000)


def _failure_status(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "SOURCE_BYTES_MISSING"
    if isinstance(exc, (URLError, TimeoutError)) or "checksum" in str(exc):
        return "SOURCE_CHECKSUM_UNVERIFIED"
    if "projection replay" in str(exc):
        return "SOURCE_PROJECTION_NONDETERMINISTIC"
    return "SOURCE_INVARIANT_FAILED"


def audit_pair(archive_root: Path) -> dict[str, Any]:
    """Audit both assets from complete monthly archives; never publish economic values."""
    audits: dict[str, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        try:
            audits[symbol] = _audit_asset(archive_root, symbol)
        except (OSError, ValueError, zipfile.BadZipFile, URLError) as exc:
            failures[symbol] = _failure_status(exc)
    if not failures:
        btc, eth = audits["BTCUSDT"], audits["ETHUSDT"]
        checks = evaluate_invariants(btc, eth, full_coverage=True)
        joint = synchronize(btc["timestamps_ms"], eth["timestamps_ms"])
        passed = all(value == "PASS" for value in checks.values())
        status = "CLOSED_PENDING_CONTROLLER_ACCEPTANCE" if passed else (
            "SOURCE_SYNCHRONIZATION_FAILED" if checks["S15"] == "FAIL"
            else "SOURCE_INVARIANT_FAILED"
        )
        btc["source_authority_status"] = status
        eth["source_authority_status"] = status
        btc_receipt, eth_receipt = public_receipt(btc), public_receipt(eth)
        btc_receipt_sha = sha256(canonical_json(btc_receipt))
        eth_receipt_sha = sha256(canonical_json(eth_receipt))
        root = authority_root(btc_receipt, eth_receipt, joint["joint_timestamp_membership_hash"]) if passed else None
    else:
        status = next(iter(failures.values()))
        checks = {f"S{i:02d}": "FAIL" for i in range(1, 17)}
        joint = None
        for audit in audits.values():
            audit["source_authority_status"] = "SOURCE_INVARIANT_FAILED"
        btc_receipt = public_receipt(audits["BTCUSDT"]) if "BTCUSDT" in audits else {
            "schema_id": "H41CanonicalSourceReceiptV1", "asset": "BTC",
            "source_authority_status": failures["BTCUSDT"], "protected_value_exposure": "ZERO",
        }
        eth_receipt = public_receipt(audits["ETHUSDT"]) if "ETHUSDT" in audits else {
            "schema_id": "H41CanonicalSourceReceiptV1", "asset": "ETH",
            "source_authority_status": failures["ETHUSDT"], "protected_value_exposure": "ZERO",
        }
        btc_receipt_sha = sha256(canonical_json(btc_receipt))
        eth_receipt_sha = sha256(canonical_json(eth_receipt))
        root = None
    return {
        "schema_id": "H41_BTC_ETH_CANONICAL_SOURCE_AUTHORITY_R1",
        "implementation_sha": "407dabc415ae8cae4210250e992941c8b9b25464",
        "frozen_semantic_root": FROZEN_SEMANTIC_ROOT,
        "source_requirements_hash": SOURCE_REQUIREMENTS_HASH,
        "candidate_ledger_hash": "d2ee1551ab4778e8ce34e83e053aba17ebb6be240aed812a4beedb218548b7e0",
        "source_authority_status": status,
        "source_authority_root": root,
        "btc_receipt_sha256": btc_receipt_sha,
        "eth_receipt_sha256": eth_receipt_sha,
        "btc": btc_receipt, "eth": eth_receipt,
        "joint": joint, "invariants": checks,
        "partition_hours": partition_hours(),
        "frozen_calibration_hours": FROZEN_CALIBRATION_HOURS,
        "protected_value_exposure": "ZERO",
        "H41_IMPLEMENTATION_AUTHORIZED": "NO", "H41_REAL_DISCOVERY_AUTHORIZED": "NO",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_pair(args.archive_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(result) + b"\n")
    print(json.dumps({
        "status": result["source_authority_status"],
        "invariants_passed": sum(v == "PASS" for v in result["invariants"].values()),
        "source_authority_root": result["source_authority_root"],
    }, sort_keys=True))
    return 0 if result["source_authority_root"] is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
