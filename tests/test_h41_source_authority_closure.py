"""Source-only checks for H41 canonical Binance archive authority."""

import csv
import copy
import importlib.util
import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch

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
    assert mod.partition_hours() == {
        "WF1_TRAIN": 16032,
        "WF1_PURGE_1": 24,
        "WF1_CALIBRATION": 2184,
        "WF1_PURGE_2": 24,
        "WF1_VALIDATION": 2112,
    }
    assert mod.partition_hours()["WF1_CALIBRATION"] == mod.FROZEN_CALIBRATION_HOURS


def test_boundary_open_previous_close_semantics(tmp_path: Path) -> None:
    assert _audit(tmp_path)["row_count"] == 3
    assert _audit(tmp_path, boundary_mismatch=True)["invalid_ohlc_count"] == 0
    assert "boundary_mismatch_count" not in _audit(tmp_path, boundary_mismatch=True)


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


@pytest.fixture(scope="module")
def full_synthetic_root(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, bytes]]:
    root = tmp_path_factory.mktemp("h41_synthetic_source")
    grouped: dict[tuple[str, str], list[list[str]]] = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        for timestamp in range(mod.SOURCE_START_MS, mod.SOURCE_END_MS, mod.HOUR_MS):
            month = datetime.fromtimestamp(timestamp / 1000, tz=UTC).strftime("%Y-%m")
            grouped.setdefault((symbol, month), []).append([
                str(timestamp), "101", "102", "99", "100", "2",
                str(timestamp + mod.HOUR_MS - 1), "200", "3", "1", "100", "0",
            ])
    checksums: dict[str, bytes] = {}
    for (symbol, month), rows in grouped.items():
        name = f"{symbol}-1h-{month}.zip"
        output = io.StringIO()
        csv.writer(output, lineterminator="\n").writerows(rows)
        path = root / symbol / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(name.replace(".zip", ".csv"), output.getvalue())
        checksums[f"{mod.OFFICIAL_ROOT}/{symbol}/1h/{name}.CHECKSUM"] = (
            f"{mod.sha256(path.read_bytes())}  {name}\n".encode()
        )
    return root, checksums


def test_full_source_all_invariants_and_deterministic_root(
    full_synthetic_root: tuple[Path, dict[str, bytes]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, checksums = full_synthetic_root
    monkeypatch.setattr(mod, "_fetch_official_checksum", checksums.__getitem__)
    first = mod.audit_pair(root)
    second = mod.audit_pair(root)
    assert set(first["invariants"]) == {f"S{i:02d}" for i in range(1, 17)}
    assert set(first["invariants"].values()) == {"PASS"}
    assert first["source_authority_root"] == second["source_authority_root"]
    assert first["btc"]["row_count"] == 20400
    assert first["eth"]["row_count"] == 20400
    assert first["btc"]["gap_timestamps"] == []
    assert first["eth"]["gap_timestamps"] == []
    assert first["btc_receipt_sha256"] == mod.sha256(mod.canonical_json(first["btc"]))
    assert first["eth_receipt_sha256"] == mod.sha256(mod.canonical_json(first["eth"]))
    assert first["btc"]["source_authority_status"] == "CLOSED_PENDING_CONTROLLER_ACCEPTANCE"
    assert first["joint"]["btc_only_count"] == first["joint"]["eth_only_count"] == 0
    assert "open" not in json.dumps(first)


def test_fresh_checksum_failure_has_no_authority_root(
    full_synthetic_root: tuple[Path, dict[str, bytes]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, checksums = full_synthetic_root
    wrong = dict(checksums)
    key = next(iter(wrong))
    wrong[key] = b"0" * 64 + wrong[key][64:]
    monkeypatch.setattr(mod, "_fetch_official_checksum", wrong.__getitem__)
    result = mod.audit_pair(root)
    assert result["source_authority_status"] == "SOURCE_CHECKSUM_UNVERIFIED"
    assert result["source_authority_root"] is None


def test_source_mutation_has_no_authority_root(
    full_synthetic_root: tuple[Path, dict[str, bytes]], monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import shutil

    root, checksums = full_synthetic_root
    copy = tmp_path / "source"
    shutil.copytree(root, copy)
    path = copy / "BTCUSDT" / "BTCUSDT-1h-2021-01.zip"
    path.write_bytes(path.read_bytes() + b"mutation")
    monkeypatch.setattr(mod, "_fetch_official_checksum", checksums.__getitem__)
    result = mod.audit_pair(copy)
    assert result["source_authority_root"] is None
    assert result["source_authority_status"] == "SOURCE_CHECKSUM_UNVERIFIED"


def test_missing_archive_publishes_failure_receipt_without_root(
    full_synthetic_root: tuple[Path, dict[str, bytes]], monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import shutil

    root, checksums = full_synthetic_root
    copy = tmp_path / "source"
    shutil.copytree(root, copy)
    (copy / "ETHUSDT" / "ETHUSDT-1h-2023-04.zip").unlink()
    monkeypatch.setattr(mod, "_fetch_official_checksum", checksums.__getitem__)
    result = mod.audit_pair(copy)
    assert result["source_authority_status"] == "SOURCE_BYTES_MISSING"
    assert result["eth"]["source_authority_status"] == "SOURCE_BYTES_MISSING"
    assert result["source_authority_root"] is None
    assert '"open":' not in json.dumps(result)


@pytest.fixture(scope="module")
def full_synthetic_audits(full_synthetic_root: tuple[Path, dict[str, bytes]]) -> tuple[dict, dict]:
    root, checksums = full_synthetic_root
    with patch.object(mod, "_fetch_official_checksum", checksums.__getitem__):
        return mod._audit_asset(root, "BTCUSDT"), mod._audit_asset(root, "ETHUSDT")


@pytest.mark.parametrize("invariant", [f"S{i:02d}" for i in range(1, 17)])
def test_each_source_invariant_fails_closed(full_synthetic_audits: tuple[dict, dict], invariant: str) -> None:
    btc, eth = copy.deepcopy(full_synthetic_audits)
    mutations = {
        "S01": lambda: btc.update(official_checksum_origin_independently_verified=False),
        "S02": lambda: btc.update(source_mode="SPOT"),
        "S03": lambda: btc.update(symbol="OTHER"),
        "S04": lambda: btc.update(row_count=20399),
        "S05": lambda: btc.update(alignment_errors=1),
        "S06": lambda: btc.update(close_time_errors=1),
        "S07": lambda: btc.update(monotonic_errors=1),
        "S08": lambda: btc.update(duplicate_count=1),
        "S09": lambda: btc.update(gap_count=1),
        "S10": lambda: btc.update(invalid_ohlc_count=1),
        "S11": lambda: btc.update(invalid_volume_count=1),
        "S12": lambda: btc["archive_records"][0].update(local_archive_sha256="0" * 64),
        "S13": lambda: btc.update(same_buffer_hash_parse=False),
        "S14": lambda: btc.update(projection_replay=False),
        "S15": lambda: eth["timestamps_ms"].pop(),
        "S16": lambda: btc["partition_membership_counts"].update(WF1_CALIBRATION=2185),
    }
    mutations[invariant]()
    assert mod.evaluate_invariants(btc, eth, full_coverage=True)[invariant] == "FAIL"


def test_projection_replay_mutation_fails_closed(
    full_synthetic_root: tuple[Path, dict[str, bytes]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, checksums = full_synthetic_root
    original = mod.audit_archive
    calls = 0

    def altered_replay(*args: object, **kwargs: object) -> dict:
        nonlocal calls
        calls += 1
        audit = original(*args, **kwargs)
        if calls == 29:
            audit["projection_hash"] = "0" * 64
        return audit

    monkeypatch.setattr(mod, "_fetch_official_checksum", checksums.__getitem__)
    monkeypatch.setattr(mod, "audit_archive", altered_replay)
    result = mod.audit_pair(root)
    assert result["source_authority_status"] == "SOURCE_PROJECTION_NONDETERMINISTIC"
    assert result["source_authority_root"] is None


def test_official_checksum_fetch_retries_transient_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def flaky_open(url: str, timeout: int) -> io.BytesIO:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise URLError("transient")
        return io.BytesIO(b"a" * 64 + b"  BTCUSDT-1h-2021-01.zip\n")

    monkeypatch.setattr(mod, "urlopen", flaky_open)
    url = f"{mod.OFFICIAL_ROOT}/BTCUSDT/1h/BTCUSDT-1h-2021-01.zip.CHECKSUM"
    assert mod._fetch_official_checksum(url).startswith(b"a" * 64)
    assert attempts == 2
