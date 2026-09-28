"""Source-only checks for H41 canonical Binance archive authority."""

import csv
import importlib.util
import io
import json
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/v0.5/h41_source_authority_closure.py"
SPEC = importlib.util.spec_from_file_location("h41_source_authority_closure", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def _archive(
    symbol: str = "BTCUSDT", *, gap: bool = False, duplicate: bool = False,
    invalid: bool = False, boundary_mismatch: bool = False,
) -> bytes:
    rows = []
    for i in (0, 2) if gap else (0, 1, 2):
        open_price = "101" if i == 1 and boundary_mismatch else "100"
        low = "102" if i == 1 and invalid else "99"
        rows.append([
            str(mod.SOURCE_START_MS + i * mod.HOUR_MS), open_price, "102", low,
            "100", "2", str(mod.SOURCE_START_MS + (i + 1) * mod.HOUR_MS - 1),
            "200", "3", "1", "100", "0",
        ])
    if duplicate:
        rows.append(rows[-1])
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(f"{symbol}-1h-2021-01.csv", output.getvalue())
    return data.getvalue()


def _audit(tmp_path: Path, symbol: str = "BTCUSDT", **kwargs: bool) -> dict:
    path = tmp_path / f"{symbol}-1h-2021-01.zip"
    raw = _archive(symbol, **kwargs)
    path.write_bytes(raw)
    return mod.audit_archive(path, symbol, "2021-01", mod.sha256(raw))


def test_source_product_identity(tmp_path: Path) -> None:
    audit = _audit(tmp_path)
    assert audit["symbol"] == "BTCUSDT"
    assert audit["market"] == "USD-M PERPETUAL"
    with pytest.raises(ValueError):
        mod.audit_archive(tmp_path / "BTCUSDT-1h-2021-01.zip", "ETHUSDT", "2021-01", "0" * 64)


def test_hourly_utc_alignment(tmp_path: Path) -> None:
    assert _audit(tmp_path)["alignment_errors"] == 0


def test_no_duplicate_timestamps(tmp_path: Path) -> None:
    assert _audit(tmp_path, duplicate=True)["duplicate_count"] == 1


def test_gap_fail_closed(tmp_path: Path) -> None:
    assert _audit(tmp_path, gap=True)["gap_count"] == 1


def test_ohlc_invariants(tmp_path: Path) -> None:
    assert _audit(tmp_path, invalid=True)["invalid_ohlc_count"] == 1


def test_same_buffer_hash_parse(tmp_path: Path) -> None:
    path = tmp_path / "BTCUSDT-1h-2021-01.zip"
    raw = _archive()
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="checksum"):
        mod.audit_archive(path, "BTCUSDT", "2021-01", "0" * 64)


def test_canonical_projection_replay(tmp_path: Path) -> None:
    first = _audit(tmp_path)
    second = _audit(tmp_path)
    assert first["projection_hash"] == second["projection_hash"]
    assert first["timestamp_membership_hash"] == second["timestamp_membership_hash"]


def test_btc_eth_timestamp_synchronization(tmp_path: Path) -> None:
    btc = _audit(tmp_path, "BTCUSDT")
    eth = _audit(tmp_path, "ETHUSDT")
    assert mod.synchronize(btc["timestamps_ms"], eth["timestamps_ms"])["btc_only_count"] == 0
    assert mod.synchronize(btc["timestamps_ms"], eth["timestamps_ms"])["eth_only_count"] == 0


def test_protected_receipt_redaction(tmp_path: Path) -> None:
    audit = _audit(tmp_path)
    receipt = mod.public_receipt(audit)
    serialized = json.dumps(receipt)
    assert "timestamps_ms" not in serialized
    assert '"open"' not in serialized
    assert '"close"' not in serialized


def test_partition_boundary_mapping() -> None:
    assert mod.partition_hours()["WF1_TRAIN"] == 16056
    assert mod.partition_hours()["WF1_CALIBRATION"] == 2208
    assert mod.partition_hours()["WF1_VALIDATION"] == 2136
    assert mod.partition_hours()["WF1_CALIBRATION"] != mod.FROZEN_CALIBRATION_HOURS


def test_boundary_open_previous_close_semantics(tmp_path: Path) -> None:
    assert _audit(tmp_path)["boundary_mismatch_count"] == 0
    assert _audit(tmp_path, boundary_mismatch=True)["boundary_mismatch_count"] == 1


def test_authority_root_replay(tmp_path: Path) -> None:
    btc = mod.public_receipt(_audit(tmp_path, "BTCUSDT"))
    eth = mod.public_receipt(_audit(tmp_path, "ETHUSDT"))
    joint = mod.synchronize([1, 2], [1, 2])["joint_timestamp_membership_hash"]
    assert mod.authority_root(btc, eth, joint) == mod.authority_root(btc, eth, joint)


def test_all_sixteen_invariants_materialized(tmp_path: Path) -> None:
    audit = _audit(tmp_path)
    statuses = mod.evaluate_invariants(audit, audit, full_coverage=False)
    assert set(statuses) == {f"S{i:02d}" for i in range(1, 17)}
    assert statuses["S16"] == "FAIL"
