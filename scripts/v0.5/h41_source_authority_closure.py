"""Blind, source-only audit of official Binance USD-M 1h kline archives.

This tool emits hashes and integrity counts. It never emits economic row values.
An archive checksum supplied by a historical manifest is recorded as such; it
does not replace independent retrieval of Binance's official .CHECKSUM file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

HOUR_MS = 3_600_000
SOURCE_START_MS = 1609459200000
SOURCE_END_MS = 1682899200000
FROZEN_CALIBRATION_HOURS = 2184
SOURCE_REQUIREMENTS_HASH = "73560ed5acdb2f176c4aed125d841fdf92dff477fb73f4fa86a7847a42e4828c"
FROZEN_SEMANTIC_ROOT = "682e50dcb68563a6ab5e1d7d228827c0886a7ad2bba030c419f1602b1c31e118"
PARTITIONS = {
    "WF1_TRAIN": ("2021-01-01", "2022-11-01"),
    "WF1_CALIBRATION": ("2022-11-01", "2023-02-01"),
    "WF1_VALIDATION": ("2023-02-01", "2023-05-01"),
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


def audit_archive(path: Path, symbol: str, month: str, expected_sha256: str) -> dict[str, Any]:
    """Hash one byte buffer, then parse precisely that buffer; never print OHLC."""
    if symbol not in {"BTCUSDT", "ETHUSDT"}:
        raise ValueError("unsupported symbol")
    expected_name = f"{symbol}-1h-{month}.zip"
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
    monotonic_errors = boundary_mismatch = boundary_pairs = 0
    max_precision = 0
    projection = hashlib.sha256()
    previous_time: int | None = None
    previous_close: Decimal | None = None
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
            if timestamp == previous_time + HOUR_MS and previous_close is not None:
                boundary_pairs += 1
                boundary_mismatch += int(op != previous_close)
                max_precision = max(
                    max_precision, -op.as_tuple().exponent,
                    -previous_close.as_tuple().exponent,
                )
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
        projection.update(canonical_json(projection_row) + b"\n")
        seen.add(timestamp)
        timestamps.append(timestamp)
        previous_time, previous_close = timestamp, cl
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
        "monotonic_errors": monotonic_errors, "boundary_pairs_checked": boundary_pairs,
        "boundary_mismatch_count": boundary_mismatch,
        "maximum_comparison_precision_decimal_places": max_precision,
        "same_buffer_hash_parse": True, "projection_replay": True,
        "official_checksum_origin_independently_verified": False,
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
    """Drop internal membership and all economic values from published receipt."""
    receipt = {key: value for key, value in audit.items() if key != "timestamps_ms"}
    receipt.update({
        "schema_id": "H41CanonicalSourceReceiptV1",
        "asset": "BTC" if audit["symbol"] == "BTCUSDT" else "ETH",
        "venue": "Binance Futures", "product": "USD-M PERPETUAL",
        "interval": "1h", "timezone": "UTC",
        "raw_archive_root": f"{OFFICIAL_ROOT}/{audit['symbol']}/1h",
        "source_archive_set_hash": sha256(canonical_json([{
            "archive_url": audit["archive_url"], "sha256": audit["local_archive_sha256"],
        }])),
        "canonical_projection_hash": audit["projection_hash"],
        "protected_value_exposure": "ZERO",
        "source_finalization_semantics": "T_k + 1h; historical archive has no local receipt time",
        "revision_semantics": "versioned archive bytes only; future replacement changes digest",
        "source_authority_status": "PROTOCOL_SOURCE_SEMANTIC_CONFLICT"
        if audit["boundary_mismatch_count"] else "INCOMPLETE_DIAGNOSTIC_ONLY",
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
        and audit["timestamps_ms"][0] == SOURCE_START_MS
        and audit["timestamps_ms"][-1] == SOURCE_END_MS - HOUR_MS
        for audit in audits
    )
    checks = {
        "S01": all(a["official_checksum_origin_independently_verified"] for a in audits),
        "S02": all(a["market"] == "USD-M PERPETUAL" for a in audits),
        "S03": btc["symbol"] == "BTCUSDT" and eth["symbol"] == "ETHUSDT",
        "S04": full and all(a["gap_count"] == 0 for a in audits),
        "S05": all(a["alignment_errors"] == 0 for a in audits),
        "S06": all(a["close_time_errors"] == 0 for a in audits),
        "S07": all(a["monotonic_errors"] == 0 for a in audits),
        "S08": all(a["duplicate_count"] == 0 for a in audits),
        "S09": full and all(a["gap_count"] == 0 for a in audits),
        "S10": all(a["invalid_ohlc_count"] == 0 for a in audits),
        "S11": all(a["invalid_volume_count"] == 0 for a in audits),
        "S12": all(
            a["official_archive_checksum"] == a["local_archive_sha256"]
            and a["official_checksum_origin_independently_verified"] for a in audits
        ),
        "S13": all(a["same_buffer_hash_parse"] for a in audits),
        "S14": all(a["projection_replay"] for a in audits),
        "S15": full and joint["btc_only_count"] == joint["eth_only_count"] == 0,
        "S16": full and partition_hours()["WF1_CALIBRATION"] == FROZEN_CALIBRATION_HOURS
        and all(a["boundary_mismatch_count"] == 0 for a in audits),
    }
    return {key: "PASS" if result else "FAIL" for key, result in checks.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--btc-archive", type=Path, required=True)
    parser.add_argument("--btc-sha256", required=True)
    parser.add_argument("--eth-archive", type=Path, required=True)
    parser.add_argument("--eth-sha256", required=True)
    parser.add_argument("--month", default="2021-01")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    btc = audit_archive(args.btc_archive, "BTCUSDT", args.month, args.btc_sha256)
    eth = audit_archive(args.eth_archive, "ETHUSDT", args.month, args.eth_sha256)
    joint = synchronize(btc["timestamps_ms"], eth["timestamps_ms"])
    checks = evaluate_invariants(btc, eth, full_coverage=False)
    result = {
        "schema_id": "H41_SOURCE_ONLY_DIAGNOSTIC_V1",
        "docs_start_sha": "9ad24476720699b397ba9788b8293a360a32e9ff",
        "implementation_sha": "407dabc415ae8cae4210250e992941c8b9b25464",
        "frozen_semantic_root": FROZEN_SEMANTIC_ROOT,
        "source_requirements_hash": SOURCE_REQUIREMENTS_HASH,
        "candidate_ledger_hash": "d2ee1551ab4778e8ce34e83e053aba17ebb6be240aed812a4beedb218548b7e0",
        "source_authority_status": "PROTOCOL_SOURCE_SEMANTIC_CONFLICT"
        if btc["boundary_mismatch_count"] or eth["boundary_mismatch_count"]
        or partition_hours()["WF1_CALIBRATION"] != FROZEN_CALIBRATION_HOURS
        else "SOURCE_BYTES_MISSING",
        "diagnostic_month": args.month, "full_coverage_audited": False,
        "btc": public_receipt(btc), "eth": public_receipt(eth),
        "joint": joint, "invariants": checks, "partition_hours": partition_hours(),
        "frozen_calibration_hours": FROZEN_CALIBRATION_HOURS,
        "protected_value_exposure": "ZERO",
        "H41_IMPLEMENTATION_AUTHORIZED": "NO", "H41_REAL_DISCOVERY_AUTHORIZED": "NO",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json(result) + b"\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
