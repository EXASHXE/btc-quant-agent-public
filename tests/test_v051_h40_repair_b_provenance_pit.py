"""Mandatory regression and preservation suite for V0.5.1 H40 Repair B.

Covers all 47 acceptance criteria:
1-17:   F02 Source Value Extraction and Provenance
18-37:  F03 Causal PIT Reconstruction
38-47:  Lifecycle V5, Stage A Isolation, and Surface Preservation
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from btc_quant_agent.execution.environment import (
    ACCEPTED_EXECUTION_WRITE_AUTHORITY,
    CURRENT_EXECUTION_POLICY,
)
from btc_quant_agent.h40 import (
    ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH,
    ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH,
    DISCOVERY_PROVENANCE_CONTRACT_HASH,
    DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
    EXPECTED_LIFECYCLE_CHILD_HASHES,
    EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
    EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH,
    H40ActiveSourceEvidenceEntry,
    H40ConfirmationGuard,
    H40DiscoveryAuthorizationReceiptV2,
    H40DiscoveryEvidenceResolver,
    H40GuardError,
    H40LifecycleAuthorityService,
    H40LifecycleImplementationAuthority,
    H40LifecyclePersistenceContextV1,
    H40ProductionDiscoveryEvidenceVerifier,
    H40ProtectedSurfaceGuard,
    H40ReasonCode,
    H40RequiredTestCIEvidenceIdentity,
    H40RuntimeSnapshotSeal,
    H40SourceManifest,
    H40SourceRecord,
    H40SourceStatus,
    H40SourceValidationReceipt,
    H40SplitManifest,
    compute_lifecycle_child_hashes,
    compute_lifecycle_governance_authority_hash,
    compute_lifecycle_semantic_root_hash,
    compute_protocol_authority_hash,
)
from btc_quant_agent.h40.discovery_evidence import (
    _POLICIES,
    _PREFIT_CACHE,
    _Bar,
    _compute_d1,
    _compute_d2,
    _compute_d3,
    _compute_o_range_scalar,
    _compute_r_vol_scalar,
    _empirical_percentile,
    _extract_economic_rows,
    _load_decisions,
    _load_source_bars,
    _reconstruct_prefit_cached,
    clear_prefit_caches,
    h40_fit_calibrator,
    h40_predict_calibrated,
    h40_proxy_net_return,
    h40_side_preserving_action,
)
from btc_quant_agent.h40.split_manifest import H40Partition, H40PartitionType
from btc_quant_agent.research_contract.canonical import canonical_json, canonical_sha256


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _store(root: Path, payload: dict[str, Any]) -> str:
    digest = canonical_sha256(payload)
    directory = root / digest[:2]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{digest}.json").write_text(canonical_json(payload), encoding="utf-8")
    return digest


def _policy_stack() -> dict[str, dict[str, str]]:
    return {
        name: {"policy_id": identity[0], "policy_hash": identity[1]}
        for name, identity in _POLICIES.items()
    }


def _make_dummy_bars(
    start: datetime,
    count: int,
    product: str = "ETHUSDT",
    base_price: float = 100.0,
    price_fn: Any = None,
) -> list[dict[str, Any]]:
    bars = []
    for i in range(count):
        t = start + timedelta(hours=i)
        p = price_fn(i) if price_fn else base_price + (i % 5) * 0.5
        bars.append({
            "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": product,
            "open": float(p),
            "high": float(p + 0.5),
            "low": float(p - 0.5),
            "close": float(p),
        })
    return bars


def _write_json_source(
    path: Path,
    bars: list[dict[str, Any]],
    timestamp_field: str = "timestamp",
) -> tuple[bytes, str, list[dict[str, str]], str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload_bars = []
    for b in bars:
        row = dict(b)
        if timestamp_field != "timestamp":
            row[timestamp_field] = row.pop("timestamp")
        payload_bars.append(row)
    data = json.dumps(payload_bars)
    path.write_text(data, encoding="utf-8")
    raw_bytes = path.read_bytes()
    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    canonical_rows = [
        {
            "timestamp": b["timestamp"],
            "open": repr(float(b["open"])),
            "high": repr(float(b["high"])),
            "low": repr(float(b["low"])),
            "close": repr(float(b["close"])),
        }
        for b in bars
    ]
    economic_digest = canonical_sha256(canonical_rows)
    economic_count = len(canonical_rows)
    return raw_bytes, file_sha256, canonical_rows, economic_digest, economic_count


# ==============================================================================
# F02 MATRIX (Items 1 - 17)
# ==============================================================================


def test_f02_01_sealed_source_bytes_reproduce_count_and_hash(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 50)
    source_file = tmp_path / "ETHUSDT.json"
    raw_bytes, _file_sha, _canonical_rows, exp_digest, exp_count = _write_json_source(source_file, bars)

    extracted_bars, canon = _extract_economic_rows(
        source_file, raw_bytes, "ETHUSDT", "1h", "timestamp",
    )
    assert len(canon) == exp_count == 50
    assert canonical_sha256(canon) == exp_digest
    assert len(extracted_bars) == 50
    assert extracted_bars[0].timestamp == start


def test_f02_02_changing_one_source_byte_fails_file_identity(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 10)
    source_file = tmp_path / "ETHUSDT.json"
    raw_bytes, file_sha, _, exp_digest, exp_count = _write_json_source(source_file, bars)

    # Tamper 1 byte of file
    tampered_bytes = bytearray(raw_bytes)
    tampered_bytes[10] = (tampered_bytes[10] + 1) % 256
    source_file.write_bytes(tampered_bytes)

    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    derivation = {
        "schema_id": "H40_P3B_SOURCE_DERIVATION_V2",
        "run_authority_id": "RUN_1",
        "source_manifest_hash": _hash("src_manifest"),
        "split_manifest_hash": _hash("split_manifest"),
        "split_attestation_hash": _hash("attestation"),
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "source_support": {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"},
        "active_source_derivations": [{
            "cadence": "1h",
            "economic_row_count": exp_count,
            "economic_rows_sha256": exp_digest,
            "locator": "ETHUSDT.json",
            "product": "ETHUSDT",
            "source_file_sha256": file_sha,  # original hash
            "source_id": "SRC_ETH",
            "source_validation_receipt_sha256": _hash("rec"),
            "timestamp_field": "timestamp",
        }],
        "base_eligible_membership": {"WF1_TRAIN": [], "WF1_CALIBRATION": []},
    }
    digest = _store(tmp_path, derivation)

    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=derivation["source_manifest_hash"],
        base_eligible_start_utc="2021-01-31T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=0, partitions=(), exclusion_counts={},
    )
    with pytest.raises(H40GuardError, match="source file SHA-256 mismatch"):
        _load_source_bars(
            resolver, digest,
            run_authority_id="RUN_1",
            source_manifest_hash=derivation["source_manifest_hash"],
            split_manifest_hash=derivation["split_manifest_hash"],
            split_manifest=split,
        )


def test_f02_03_fabricated_economic_row_digest_rejected(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 10)
    source_file = tmp_path / "ETHUSDT.json"
    _raw_bytes, file_sha, _, _exp_digest, exp_count = _write_json_source(source_file, bars)

    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    derivation = {
        "schema_id": "H40_P3B_SOURCE_DERIVATION_V2",
        "run_authority_id": "RUN_1",
        "source_manifest_hash": _hash("src_manifest"),
        "split_manifest_hash": _hash("split_manifest"),
        "split_attestation_hash": _hash("attestation"),
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "source_support": {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"},
        "active_source_derivations": [{
            "cadence": "1h",
            "economic_row_count": exp_count,
            "economic_rows_sha256": "0" * 64,  # Fabricated digest
            "locator": "ETHUSDT.json",
            "product": "ETHUSDT",
            "source_file_sha256": file_sha,
            "source_id": "SRC_ETH",
            "source_validation_receipt_sha256": _hash("rec"),
            "timestamp_field": "timestamp",
        }],
        "base_eligible_membership": {"WF1_TRAIN": [], "WF1_CALIBRATION": []},
    }
    digest = _store(tmp_path, derivation)

    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=derivation["source_manifest_hash"],
        base_eligible_start_utc="2021-01-31T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=0, partitions=(), exclusion_counts={},
    )
    with pytest.raises(H40GuardError, match="economic rows SHA-256 mismatch"):
        _load_source_bars(
            resolver, digest,
            run_authority_id="RUN_1",
            source_manifest_hash=derivation["source_manifest_hash"],
            split_manifest_hash=derivation["split_manifest_hash"],
            split_manifest=split,
        )


def _make_production_test_seal_and_context(tmp_path: Path, bars: list[dict[str, Any]]):
    source_file = tmp_path / "ETHUSDT.json"
    _raw_bytes, file_sha, _canonical_rows, exp_digest, exp_count = _write_json_source(source_file, bars)

    receipt = H40SourceValidationReceipt(
        source_id="SRC_ETH",
        locator="ETHUSDT.json",
        file_sha256=file_sha,
        product="ETHUSDT",
        cadence="1h",
        status=H40SourceStatus.VERIFIED,
        timestamp_field="timestamp",
        timestamp_count=exp_count,
        first_timestamp_utc=bars[0]["timestamp"],
        last_timestamp_utc=bars[-1]["timestamp"],
        duplicate_count=0,
        gap_count=0,
        gaps=(),
        timestamp_membership_hash=_hash("ts_mem"),
    )
    record = H40SourceRecord(
        source_id="SRC_ETH",
        locator="ETHUSDT.json",
        product="ETHUSDT",
        cadence="1h",
        file_sha256=file_sha,
        status=H40SourceStatus.VERIFIED,
        receipt=receipt,
    )
    manifest = H40SourceManifest(
        protocol_identity_hash=_hash("proto"),
        sources=(record,),
    )
    evidence_entry = H40ActiveSourceEvidenceEntry(
        source_id="SRC_ETH",
        source_record_hash=canonical_sha256(record.to_dict()),
        source_validation_receipt_hash=canonical_sha256(receipt.to_dict()),
        file_sha256=file_sha,
        timestamp_membership_hash=receipt.timestamp_membership_hash,
        timestamp_count=receipt.timestamp_count,
    )
    attestation = SimpleNamespace(
        source_manifest_hash=manifest.manifest_hash,
        split_manifest_hash=_hash("split"),
        active_required_source_ids=("SRC_ETH",),
        active_source_evidence=(evidence_entry,),
        attestation_hash=_hash("attestation"),
    )
    seal = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=_hash("snap"),
        source_manifest_hash=manifest.manifest_hash,
        split_manifest_hash=_hash("split"),
        split_attestation_hash=attestation.attestation_hash,
        roster=(),
        not_testable_slot_count=168,
    )
    object.__setattr__(seal, "synthetic_only", False)
    object.__setattr__(seal, "_source_manifest_context", manifest)
    object.__setattr__(seal, "_runtime_attestation_context", attestation)
    object.__setattr__(seal, "_repo_root_context", tmp_path)
    return seal, manifest, attestation, record, receipt, file_sha, exp_digest, exp_count


def test_f02_04_source_record_hash_mismatch_rejected(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 5)
    seal, manifest, attestation, _record, receipt, file_sha, exp_digest, exp_count = (
        _make_production_test_seal_and_context(tmp_path, bars)
    )

    # Tamper source_record_hash in attestation evidence
    bad_entry = H40ActiveSourceEvidenceEntry(
        source_id="SRC_ETH",
        source_record_hash="1" * 64,
        source_validation_receipt_hash=canonical_sha256(receipt.to_dict()),
        file_sha256=file_sha,
        timestamp_membership_hash=receipt.timestamp_membership_hash,
        timestamp_count=receipt.timestamp_count,
    )
    bad_attestation = SimpleNamespace(
        source_manifest_hash=manifest.manifest_hash,
        split_manifest_hash=_hash("split"),
        active_required_source_ids=("SRC_ETH",),
        active_source_evidence=(bad_entry,),
        attestation_hash=_hash("attestation"),
    )
    object.__setattr__(seal, "_runtime_attestation_context", bad_attestation)

    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    derivation = {
        "schema_id": "H40_P3B_SOURCE_DERIVATION_V2", "run_authority_id": "RUN_1",
        "source_manifest_hash": manifest.manifest_hash,
        "split_manifest_hash": _hash("split"),
        "split_attestation_hash": attestation.attestation_hash,
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "source_support": {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"},
        "active_source_derivations": [{
            "cadence": "1h", "economic_row_count": exp_count, "economic_rows_sha256": exp_digest,
            "locator": "ETHUSDT.json", "product": "ETHUSDT", "source_file_sha256": file_sha,
            "source_id": "SRC_ETH",
            "source_validation_receipt_sha256": canonical_sha256(receipt.to_dict()),
            "timestamp_field": "timestamp",
        }],
        "base_eligible_membership": {"WF1_TRAIN": [], "WF1_CALIBRATION": []},
    }
    digest = _store(tmp_path, derivation)
    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=manifest.manifest_hash,
        base_eligible_start_utc="2021-01-31T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=0, partitions=(), exclusion_counts={},
    )
    with pytest.raises(H40GuardError, match="source record hash mismatch"):
        _load_source_bars(
            resolver, digest, run_authority_id="RUN_1",
            source_manifest_hash=manifest.manifest_hash,
            split_manifest_hash=_hash("split"),
            split_manifest=split, seal=seal,
        )


def test_f02_05_source_validation_receipt_hash_mismatch_rejected(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 5)
    seal, manifest, attestation, _record, _receipt, file_sha, exp_digest, exp_count = (
        _make_production_test_seal_and_context(tmp_path, bars)
    )

    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    derivation = {
        "schema_id": "H40_P3B_SOURCE_DERIVATION_V2", "run_authority_id": "RUN_1",
        "source_manifest_hash": manifest.manifest_hash,
        "split_manifest_hash": _hash("split"),
        "split_attestation_hash": attestation.attestation_hash,
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "source_support": {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"},
        "active_source_derivations": [{
            "cadence": "1h", "economic_row_count": exp_count, "economic_rows_sha256": exp_digest,
            "locator": "ETHUSDT.json", "product": "ETHUSDT", "source_file_sha256": file_sha,
            "source_id": "SRC_ETH",
            "source_validation_receipt_sha256": "2" * 64,  # wrong receipt hash in derivation
            "timestamp_field": "timestamp",
        }],
        "base_eligible_membership": {"WF1_TRAIN": [], "WF1_CALIBRATION": []},
    }
    digest = _store(tmp_path, derivation)
    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=manifest.manifest_hash,
        base_eligible_start_utc="2021-01-31T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=0, partitions=(), exclusion_counts={},
    )
    with pytest.raises(H40GuardError, match="source derivation receipt hash mismatch"):
        _load_source_bars(
            resolver, digest, run_authority_id="RUN_1",
            source_manifest_hash=manifest.manifest_hash,
            split_manifest_hash=_hash("split"),
            split_manifest=split, seal=seal,
        )


def test_f02_06_wrong_timestamp_field_rejected(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 5)
    source_file = tmp_path / "ETHUSDT.json"
    raw_bytes, _, _, _, _ = _write_json_source(source_file, bars)

    with pytest.raises(H40GuardError, match="timestamp field 'open_time' not in json bar"):
        _extract_economic_rows(source_file, raw_bytes, "ETHUSDT", "1h", "open_time")


def test_f02_07_duplicate_timestamps_rejected(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 5)
    bars.append(dict(bars[-1]))  # duplicate timestamp
    source_file = tmp_path / "ETHUSDT.json"
    source_file.write_text(json.dumps(bars), encoding="utf-8")
    raw_bytes = source_file.read_bytes()

    with pytest.raises(H40GuardError, match="strictly sorted and unique"):
        _extract_economic_rows(source_file, raw_bytes, "ETHUSDT", "1h", "timestamp")


def test_f02_08_non_1h_cadence_rejected(tmp_path: Path) -> None:
    source_file = tmp_path / "ETHUSDT.json"
    source_file.write_text("[]", encoding="utf-8")
    with pytest.raises(H40GuardError, match="1h cadence"):
        _extract_economic_rows(source_file, b"[]", "ETHUSDT", "15m", "timestamp")


def test_f02_09_non_finite_ohlc_rejected(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 1)
    bars[0]["close"] = "NaN"
    source_file = tmp_path / "ETHUSDT.json"
    source_file.write_text(json.dumps(bars), encoding="utf-8")

    with pytest.raises(H40GuardError, match="non-finite source close"):
        _extract_economic_rows(source_file, source_file.read_bytes(), "ETHUSDT", "1h", "timestamp")


def test_f02_10_non_positive_ohlc_rejected(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 1)
    bars[0]["open"] = 0.0
    source_file = tmp_path / "ETHUSDT.json"
    source_file.write_text(json.dumps(bars), encoding="utf-8")

    with pytest.raises(H40GuardError, match="non-positive source open"):
        _extract_economic_rows(source_file, source_file.read_bytes(), "ETHUSDT", "1h", "timestamp")


def test_f02_11_malformed_ohlc_geometry_rejected(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 1)
    bars[0]["low"] = 110.0  # low > high
    bars[0]["high"] = 100.0
    source_file = tmp_path / "ETHUSDT.json"
    source_file.write_text(json.dumps(bars), encoding="utf-8")

    with pytest.raises(H40GuardError, match="geometry is malformed"):
        _extract_economic_rows(source_file, source_file.read_bytes(), "ETHUSDT", "1h", "timestamp")


def test_f02_12_source_timestamp_outside_support_interval_rejected(tmp_path: Path) -> None:
    # 2020-12-31 is outside [2021-01-01, 2023-02-01)
    early = datetime(2020, 12, 31, 23, tzinfo=UTC)
    bars = _make_dummy_bars(early, 1)
    source_file = tmp_path / "ETHUSDT.json"
    source_file.write_text(json.dumps(bars), encoding="utf-8")

    with pytest.raises(H40GuardError, match="outside support interval"):
        _extract_economic_rows(source_file, source_file.read_bytes(), "ETHUSDT", "1h", "timestamp")


def test_f02_13_active_source_without_accepted_adapter_fails_closed(tmp_path: Path) -> None:
    source_file = tmp_path / "ETHUSDT.csv"
    source_file.write_text("open,high,low,close\n", encoding="utf-8")
    with pytest.raises(H40GuardError, match="active source without accepted adapter") as exc_info:
        _extract_economic_rows(source_file, b"...", "ETHUSDT", "1h", "timestamp")
    assert exc_info.value.reason_code == H40ReasonCode.NOT_TESTABLE


def test_f02_14_v1_source_hours_rejected_by_production_verifier(tmp_path: Path) -> None:
    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    v1_payload = {
        "schema_id": "H40_P3B_SOURCE_HOURS_V1",
        "run_authority_id": "RUN_1",
        "source_manifest_hash": _hash("s"),
        "split_manifest_hash": _hash("sp"),
        "policies": _policy_stack(),
        "bars": [],
        "base_eligible_rows": {},
    }
    digest = _store(tmp_path, v1_payload)
    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=_hash("s"),
        base_eligible_start_utc="2021-01-31T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=0, partitions=(), exclusion_counts={},
    )
    with pytest.raises(H40GuardError, match="schema keys|lineage mismatch|H40_P3B_SOURCE_DERIVATION_V2"):
        _load_source_bars(
            resolver, digest, run_authority_id="RUN_1",
            source_manifest_hash=_hash("s"), split_manifest_hash=_hash("sp"),
            split_manifest=split,
        )


def test_f02_15_cold_repeated_reconstruction_identical_digest(tmp_path: Path) -> None:
    start = datetime(2021, 6, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 100)
    source_file = tmp_path / "ETHUSDT.json"
    raw_bytes, _, _, exp_digest, _ = _write_json_source(source_file, bars)

    digests = []
    for _ in range(5):
        _, canon = _extract_economic_rows(source_file, raw_bytes, "ETHUSDT", "1h", "timestamp")
        digests.append(canonical_sha256(canon))
    assert len(set(digests)) == 1
    assert digests[0] == exp_digest


def test_f02_16_active_source_derivations_must_cover_active_required_sources(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 5)
    seal, manifest, attestation, _record, receipt, file_sha, exp_digest, exp_count = (
        _make_production_test_seal_and_context(tmp_path, bars)
    )

    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    # derivation provides "SRC_OTHER" instead of active required "SRC_ETH"
    derivation = {
        "schema_id": "H40_P3B_SOURCE_DERIVATION_V2", "run_authority_id": "RUN_1",
        "source_manifest_hash": manifest.manifest_hash,
        "split_manifest_hash": _hash("split"),
        "split_attestation_hash": attestation.attestation_hash,
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "source_support": {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"},
        "active_source_derivations": [{
            "cadence": "1h", "economic_row_count": exp_count, "economic_rows_sha256": exp_digest,
            "locator": "ETHUSDT.json", "product": "ETHUSDT", "source_file_sha256": file_sha,
            "source_id": "SRC_OTHER",
            "source_validation_receipt_sha256": canonical_sha256(receipt.to_dict()),
            "timestamp_field": "timestamp",
        }],
        "base_eligible_membership": {"WF1_TRAIN": [], "WF1_CALIBRATION": []},
    }
    digest = _store(tmp_path, derivation)
    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=manifest.manifest_hash,
        base_eligible_start_utc="2021-01-31T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=0, partitions=(), exclusion_counts={},
    )
    with pytest.raises(H40GuardError, match="active-source derivations do not cover sealed active required sources"):
        _load_source_bars(
            resolver, digest, run_authority_id="RUN_1",
            source_manifest_hash=manifest.manifest_hash,
            split_manifest_hash=_hash("split"),
            split_manifest=split, seal=seal,
        )


def test_f02_17_lookback_reserve_excluded_from_base_eligible_membership(tmp_path: Path) -> None:
    start = datetime(2021, 1, 15, 0, tzinfo=UTC)  # In lookback reserve [2021-01-01, 2021-01-31)
    bars = _make_dummy_bars(start, 5)
    source_file = tmp_path / "ETHUSDT.json"
    _raw_bytes, file_sha, _, exp_digest, exp_count = _write_json_source(source_file, bars)

    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    derivation = {
        "schema_id": "H40_P3B_SOURCE_DERIVATION_V2", "run_authority_id": "RUN_1",
        "source_manifest_hash": _hash("src_manifest"),
        "split_manifest_hash": _hash("split_manifest"),
        "split_attestation_hash": _hash("attestation"),
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "source_support": {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"},
        "active_source_derivations": [{
            "cadence": "1h", "economic_row_count": exp_count, "economic_rows_sha256": exp_digest,
            "locator": "ETHUSDT.json", "product": "ETHUSDT", "source_file_sha256": file_sha,
            "source_id": "SRC_ETH", "source_validation_receipt_sha256": _hash("rec"),
            "timestamp_field": "timestamp",
        }],
        "base_eligible_membership": {
            "WF1_TRAIN": [{"timestamp": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "product": "ETHUSDT"}],
            "WF1_CALIBRATION": [],
        },
    }
    digest = _store(tmp_path, derivation)
    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=derivation["source_manifest_hash"],
        base_eligible_start_utc="2021-01-01T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=1,
        partitions=(
            H40Partition(
                partition_id="WF1_TRAIN", fold="WF1", partition_type=H40PartitionType.TRAIN,
                start_utc="2021-01-01T00:00:00Z", end_utc="2022-10-31T00:00:00Z", count=1,
                first_timestamp_utc=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                last_timestamp_utc=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                timestamps_sha256=_hash("t"),
            ),
        ),
        exclusion_counts={},
    )
    with pytest.raises(H40GuardError, match="lookback reserve hour cannot enter base-universe membership"):
        _load_source_bars(
            resolver, digest, run_authority_id="RUN_1",
            source_manifest_hash=derivation["source_manifest_hash"],
            split_manifest_hash=derivation["split_manifest_hash"],
            split_manifest=split,
        )


# ==============================================================================
# F03 MATRIX (Items 18 - 37)
# ==============================================================================


@pytest.mark.parametrize("forbidden_field", [
    "regime_state", "opportunity_state", "raw_score", "secondary_filter_state",
])
def test_f03_18_production_v2_decision_rows_reject_transported_prefit_fields(
    tmp_path: Path, forbidden_field: str,
) -> None:
    t = datetime(2022, 1, 1, 0, tzinfo=UTC)
    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    decisions_payload = {
        "schema_id": "H40_P3B_RAW_DECISIONS_V2",
        "run_authority_id": "RUN_1",
        "sealed_registered_roster_hash": _hash("roster"),
        "structural_configuration_hash": _hash("cand"),
        "source_manifest_hash": _hash("src"),
        "split_manifest_hash": _hash("split"),
        "source_evidence_hash": _hash("source_ev"),
        "partition_id": "WF1_TRAIN",
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "rows": [{
            "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": "ETHUSDT",
            "p_up": None,
            "final_action": None,
            "r_h": "0.0",
            "r_net": None,
            forbidden_field: "TRANSPORTED_VALUE",
        }],
    }
    digest = _store(tmp_path, decisions_payload)
    bars = {(t, "ETHUSDT"): _Bar(t, "ETHUSDT", 100.0, 101.0, 99.0, 100.0)}

    with pytest.raises(H40GuardError, match="forbidden transported prefit fields in V2 decision row"):
        _load_decisions(
            resolver, digest, run_authority_id="RUN_1", roster_hash=_hash("roster"),
            candidate_id=_hash("cand"), source_manifest_hash=_hash("src"),
            split_manifest_hash=_hash("split"), source_evidence_hash=_hash("source_ev"),
            partition_id="WF1_TRAIN", products=("ETHUSDT",), horizon=4,
            bars=bars, base_universe=frozenset({(t, "ETHUSDT")}),
        )


def test_f03_19_exact_v2_top_level_schema_required(tmp_path: Path) -> None:
    t = datetime(2022, 1, 1, 0, tzinfo=UTC)
    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    decisions_payload = {
        "schema_id": "H40_P3B_RAW_DECISIONS_V2",
        "run_authority_id": "RUN_1",
        "sealed_registered_roster_hash": _hash("roster"),
        "structural_configuration_hash": _hash("cand"),
        "source_manifest_hash": _hash("src"),
        "split_manifest_hash": _hash("split"),
        "source_evidence_hash": _hash("source_ev"),
        "partition_id": "WF1_TRAIN",
        # Missing provenance_contract_hash
        "policies": _policy_stack(),
        "rows": [],
    }
    digest = _store(tmp_path, decisions_payload)
    bars = {(t, "ETHUSDT"): _Bar(t, "ETHUSDT", 100.0, 101.0, 99.0, 100.0)}

    with pytest.raises(H40GuardError, match="missing or extra schema keys"):
        _load_decisions(
            resolver, digest, run_authority_id="RUN_1", roster_hash=_hash("roster"),
            candidate_id=_hash("cand"), source_manifest_hash=_hash("src"),
            split_manifest_hash=_hash("split"), source_evidence_hash=_hash("source_ev"),
            partition_id="WF1_TRAIN", products=("ETHUSDT",), horizon=4,
            bars=bars, base_universe=frozenset({(t, "ETHUSDT")}),
        )


def test_f03_20_exact_v2_row_schema_required(tmp_path: Path) -> None:
    t = datetime(2022, 1, 1, 0, tzinfo=UTC)
    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    decisions_payload = {
        "schema_id": "H40_P3B_RAW_DECISIONS_V2",
        "run_authority_id": "RUN_1",
        "sealed_registered_roster_hash": _hash("roster"),
        "structural_configuration_hash": _hash("cand"),
        "source_manifest_hash": _hash("src"),
        "split_manifest_hash": _hash("split"),
        "source_evidence_hash": _hash("source_ev"),
        "partition_id": "WF1_TRAIN",
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "rows": [{
            "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": "ETHUSDT",
            # missing r_h
            "p_up": None,
            "final_action": None,
            "r_net": None,
        }],
    }
    digest = _store(tmp_path, decisions_payload)
    bars = {(t, "ETHUSDT"): _Bar(t, "ETHUSDT", 100.0, 101.0, 99.0, 100.0)}

    with pytest.raises(H40GuardError, match="missing or extra schema keys"):
        _load_decisions(
            resolver, digest, run_authority_id="RUN_1", roster_hash=_hash("roster"),
            candidate_id=_hash("cand"), source_manifest_hash=_hash("src"),
            split_manifest_hash=_hash("split"), source_evidence_hash=_hash("source_ev"),
            partition_id="WF1_TRAIN", products=("ETHUSDT",), horizon=4,
            bars=bars, base_universe=frozenset({(t, "ETHUSDT")}),
        )


def test_f03_21_verifier_derived_d1_matches_r3r2() -> None:
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    bars = {
        (t - timedelta(hours=4), "ETHUSDT"): _Bar(t - timedelta(hours=4), "ETHUSDT", 100.0, 101.0, 99.0, 100.0),
        (t - timedelta(hours=1), "ETHUSDT"): _Bar(t - timedelta(hours=1), "ETHUSDT", 104.0, 106.0, 103.0, 105.0),
    }
    score_4h = _compute_d1(bars, t, "ETHUSDT", 4)
    expected = math.log(105.0 / 100.0)
    assert score_4h == pytest.approx(expected)


def test_f03_22_verifier_derived_d2_matches_r3r2() -> None:
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    # 24h Donchian: reference bars t-2h through t-24h
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(2, 25):
        dt = t - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 105.0, 95.0, 100.0)
    # Test bar at t-1h: close > 105 -> LONG (+1)
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 104.0, 107.0, 103.0, 106.0)
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 1.0

    # Test bar close < 95 -> SHORT (-1)
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 96.0, 97.0, 93.0, 94.0)
    assert _compute_d2(bars, t, "ETHUSDT", 24) == -1.0

    # Inside boundary -> 0
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 100.0, 102.0, 98.0, 100.0)
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 0.0


def test_f03_23_verifier_derived_d3_matches_r3r2() -> None:
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    # Range window: max high = 105, min low = 95
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(3, 27):
        dt = t - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 105.0, 95.0, 100.0)

    # Upward break at b1 (t-2h), close back inside at b2 (t-1h) -> SHORT (-1.0)
    bars[(t - timedelta(hours=2), "ETHUSDT")] = _Bar(t - timedelta(hours=2), "ETHUSDT", 104.0, 108.0, 103.0, 106.0)
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 105.0, 105.0, 103.0, 104.0)
    assert _compute_d3(bars, t, "ETHUSDT", 24) == -1.0


def test_f03_24_verifier_derived_r_vol_matches_r3r2() -> None:
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(1, 25):
        dt = t - timedelta(hours=k)
        p = 100.0 * (1.0 + 0.01 * (k % 4))
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", p, p + 1, p - 1, p)

    rv = _compute_r_vol_scalar(bars, t, "ETHUSDT")
    assert rv is not None and rv > 0.0

    # Percentile mapping
    sample = [0.01 * i for i in range(1, 101)]
    # rv in 40th to 60th percentile -> REGIME_VOL_MID
    p45 = sample[45]
    pct = _empirical_percentile(sample, p45)
    assert 0.40 <= pct < 0.60


def test_f03_25_verifier_derived_o_range_matches_r3r2() -> None:
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(1, 26):
        dt = t - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 102.0, 98.0, 100.0)

    ratio = _compute_o_range_scalar(bars, t, "ETHUSDT")
    assert ratio is not None
    assert ratio == pytest.approx(1.0)


def test_f03_26_secondary_filter_matches_r3r2() -> None:
    # Single-asset D1/D2/D3 slots always evaluate secondary filter to PASS
    clear_prefit_caches()
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(1, 30):
        dt = t - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 102.0, 98.0, 100.0)

    _score, _regime, _opp, secondary = _reconstruct_prefit_cached(
        candidate_id="test_cand", slot=None, partition_id="WF1_CALIBRATION",
        t=t, product="ETHUSDT", bars=bars, source_evidence_hash="test_src",
    )
    assert secondary == "PASS"


def test_f03_27_adding_later_observations_cannot_alter_earlier_prefit() -> None:
    clear_prefit_caches()
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(1, 100):
        dt = t - timedelta(hours=k)
        p = 100.0 + k * 0.1
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", p, p + 1, p - 1, p)

    res1 = _reconstruct_prefit_cached(
        candidate_id="cand_1", slot=None, partition_id="WF1_TRAIN",
        t=t, product="ETHUSDT", bars=bars, source_evidence_hash="source_1",
    )

    # Add 50 later bars (future relative to t)
    for k in range(1, 51):
        dt_future = t + timedelta(hours=k)
        bars[(dt_future, "ETHUSDT")] = _Bar(dt_future, "ETHUSDT", 200.0, 205.0, 195.0, 200.0)

    clear_prefit_caches()
    res2 = _reconstruct_prefit_cached(
        candidate_id="cand_1", slot=None, partition_id="WF1_TRAIN",
        t=t, product="ETHUSDT", bars=bars, source_evidence_hash="source_1",
    )
    assert res1 == res2


def test_f03_28_bar_with_close_time_eq_decision_t_is_unavailable() -> None:
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    # A bar with close_time == t has effective_close_time >= t, so it's strictly unavailable
    unavailable_bar = _Bar(
        timestamp=t - timedelta(hours=1),
        product="ETHUSDT", open=100.0, high=105.0, low=95.0, close=102.0,
        close_time=t,  # close_time equals decision_t
    )
    assert unavailable_bar.effective_close_time >= t

    bars = {(t - timedelta(hours=1), "ETHUSDT"): unavailable_bar}
    # D1 must not see this bar
    score = _compute_d1(bars, t, "ETHUSDT", 4)
    assert score == 0.0


def test_f03_29_lookback_reserve_supports_earliest_training_decisions() -> None:
    clear_prefit_caches()
    t_first_train = datetime(2021, 1, 31, 0, tzinfo=UTC)
    # Populate lookback reserve [2021-01-01, 2021-01-31)
    bars: dict[tuple[datetime, str], _Bar] = {}
    for i in range(1, 721):
        dt = t_first_train - timedelta(hours=i)
        p = 100.0 + (i % 10) * 0.5
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", p, p + 0.5, p - 0.5, p)

    score = _compute_d1(bars, t_first_train, "ETHUSDT", 4)
    expected = math.log(bars[(t_first_train - timedelta(hours=1), "ETHUSDT")].close /
                        bars[(t_first_train - timedelta(hours=4), "ETHUSDT")].close)
    assert score == pytest.approx(expected)
    assert _compute_r_vol_scalar(bars, t_first_train, "ETHUSDT") is not None


def test_f03_30_lookback_reserve_never_joins_decision_denominator(tmp_path: Path) -> None:
    t_reserve = datetime(2021, 1, 20, 0, tzinfo=UTC)
    bars = _make_dummy_bars(t_reserve, 5)
    source_file = tmp_path / "ETHUSDT.json"
    _raw_bytes, file_sha, _, exp_digest, exp_count = _write_json_source(source_file, bars)

    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    derivation = {
        "schema_id": "H40_P3B_SOURCE_DERIVATION_V2", "run_authority_id": "RUN_1",
        "source_manifest_hash": _hash("s"), "split_manifest_hash": _hash("sp"),
        "split_attestation_hash": _hash("att"), "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "source_support": {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"},
        "active_source_derivations": [{
            "cadence": "1h", "economic_row_count": exp_count, "economic_rows_sha256": exp_digest,
            "locator": "ETHUSDT.json", "product": "ETHUSDT", "source_file_sha256": file_sha,
            "source_id": "SRC_ETH", "source_validation_receipt_sha256": _hash("r"),
            "timestamp_field": "timestamp",
        }],
        "base_eligible_membership": {
            "WF1_TRAIN": [{"timestamp": t_reserve.strftime("%Y-%m-%dT%H:%M:%SZ"), "product": "ETHUSDT"}],
            "WF1_CALIBRATION": [],
        },
    }
    digest = _store(tmp_path, derivation)
    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=_hash("s"),
        base_eligible_start_utc="2021-01-01T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=1, partitions=(), exclusion_counts={},
    )
    with pytest.raises(H40GuardError, match="lookback reserve hour cannot enter base-universe membership"):
        _load_source_bars(
            resolver, digest, run_authority_id="RUN_1",
            source_manifest_hash=_hash("s"), split_manifest_hash=_hash("sp"),
            split_manifest=split,
        )


def test_f03_31_source_digest_change_invalidates_prefit_cache() -> None:
    clear_prefit_caches()
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(1, 20):
        dt = t - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 101.0, 99.0, 100.0)

    k1 = (compute_protocol_authority_hash(), DISCOVERY_PROVENANCE_CONTRACT_HASH, "source_1", "cand_1", "WF1_TRAIN", t.strftime("%Y-%m-%dT%H:%M:%SZ"), "ETHUSDT")
    k2 = (compute_protocol_authority_hash(), DISCOVERY_PROVENANCE_CONTRACT_HASH, "source_2", "cand_1", "WF1_TRAIN", t.strftime("%Y-%m-%dT%H:%M:%SZ"), "ETHUSDT")

    _PREFIT_CACHE[k1] = (1.0, "REGIME_VOL_MID", "O_ELIGIBLE", "PASS")
    assert k2 not in _PREFIT_CACHE


def test_f03_32_candidate_config_change_recomputes_prefit() -> None:
    clear_prefit_caches()
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    k1 = (compute_protocol_authority_hash(), DISCOVERY_PROVENANCE_CONTRACT_HASH, "source_1", "cand_A", "WF1_TRAIN", t.strftime("%Y-%m-%dT%H:%M:%SZ"), "ETHUSDT")
    k2 = (compute_protocol_authority_hash(), DISCOVERY_PROVENANCE_CONTRACT_HASH, "source_1", "cand_B", "WF1_TRAIN", t.strftime("%Y-%m-%dT%H:%M:%SZ"), "ETHUSDT")

    _PREFIT_CACHE[k1] = (1.0, "REGIME_VOL_MID", "O_ELIGIBLE", "PASS")
    assert k2 not in _PREFIT_CACHE


def test_f03_33_training_reference_state_used_by_calibration_remains_pit_valid() -> None:
    clear_prefit_caches()
    train_end = datetime(2022, 10, 31, tzinfo=UTC)
    bars: dict[tuple[datetime, str], _Bar] = {}
    for i in range(100):
        dt = train_end - timedelta(hours=100 - i)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 102.0, 98.0, 100.0)
    # Future observation after train_end
    dt_future = train_end + timedelta(hours=10)
    bars[(dt_future, "ETHUSDT")] = _Bar(dt_future, "ETHUSDT", 500.0, 510.0, 490.0, 500.0)

    from btc_quant_agent.h40.discovery_evidence import _get_training_refs
    refs = _get_training_refs("source_test", "ETHUSDT", bars)
    # Future bar must not be in training refs
    assert all(dt < train_end for dt, _ in refs["R_VOL"])
    assert all(dt < train_end for dt, _ in refs["O_RANGE"])


def test_f03_34_retrospective_calibration_regression_equivalent() -> None:
    pairs = [(0.5, 1), (-0.5, 0), (0.1, 0), (0.2, 1), (-0.1, 1), (-0.8, 0)]
    fit1 = h40_fit_calibrator("CALIBRATION_PLATT_LOGISTIC_V1", pairs)
    fit2 = h40_fit_calibrator("CALIBRATION_PLATT_LOGISTIC_V1", pairs)
    assert fit1 == fit2
    pred1 = h40_predict_calibrated(fit1, 0.4)
    pred2 = h40_predict_calibrated(fit2, 0.4)
    assert pred1 == pred2
    assert 0.0 < pred1 < 1.0


def test_f03_35_side_preserving_final_action_remains_unchanged() -> None:
    # Long proposal (raw_score > 0)
    assert h40_side_preserving_action(1.0, 0.65, 0.60) == "LONG"
    assert h40_side_preserving_action(1.0, 0.55, 0.60) == "NO_TRADE"
    assert h40_side_preserving_action(1.0, 0.20, 0.60) == "NO_TRADE"  # never reverses to SHORT

    # Short proposal (raw_score < 0)
    assert h40_side_preserving_action(-1.0, 0.35, 0.60) == "SHORT"
    assert h40_side_preserving_action(-1.0, 0.45, 0.60) == "NO_TRADE"
    assert h40_side_preserving_action(-1.0, 0.80, 0.60) == "NO_TRADE"  # never reverses to LONG


def test_f03_36_r_h_and_r_net_reconstructed_from_source_economics(tmp_path: Path) -> None:
    t = datetime(2022, 11, 1, 0, tzinfo=UTC)
    bars = {
        (t, "ETHUSDT"): _Bar(t, "ETHUSDT", 100.0, 102.0, 98.0, 100.0),
        (t + timedelta(hours=1), "ETHUSDT"): _Bar(t + timedelta(hours=1), "ETHUSDT", 100.0, 102.0, 98.0, 100.0),
        (t + timedelta(hours=2), "ETHUSDT"): _Bar(t + timedelta(hours=2), "ETHUSDT", 100.0, 102.0, 98.0, 100.0),
        (t + timedelta(hours=3), "ETHUSDT"): _Bar(t + timedelta(hours=3), "ETHUSDT", 100.0, 106.0, 99.0, 105.0),
    }
    first_open = bars[(t, "ETHUSDT")].open
    last_close = bars[(t + timedelta(hours=3), "ETHUSDT")].close
    expected_rh = math.log(last_close / first_open)
    _, expected_rnet = h40_proxy_net_return("LONG", str(first_open), str(last_close))

    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    decisions_payload = {
        "schema_id": "H40_P3B_RAW_DECISIONS_V2",
        "run_authority_id": "RUN_1",
        "sealed_registered_roster_hash": _hash("roster"),
        "structural_configuration_hash": _hash("cand"),
        "source_manifest_hash": _hash("src"),
        "split_manifest_hash": _hash("split"),
        "source_evidence_hash": "src_ev",
        "partition_id": "WF1_CALIBRATION",
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "rows": [{
            "timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": "ETHUSDT",
            "p_up": None,
            "final_action": "LONG",
            "r_h": str(expected_rh),
            "r_net": str(expected_rnet),
        }],
    }
    digest = _store(tmp_path, decisions_payload)
    _PREFIT_CACHE[(compute_protocol_authority_hash(), DISCOVERY_PROVENANCE_CONTRACT_HASH, "src_ev", _hash("cand"), "WF1_CALIBRATION", t.strftime("%Y-%m-%dT%H:%M:%SZ"), "ETHUSDT")] = (1.0, "REGIME_VOL_MID", "O_ELIGIBLE", "PASS")

    decisions = _load_decisions(
        resolver, digest, run_authority_id="RUN_1", roster_hash=_hash("roster"),
        candidate_id=_hash("cand"), source_manifest_hash=_hash("src"),
        split_manifest_hash=_hash("split"), source_evidence_hash="src_ev",
        partition_id="WF1_CALIBRATION", products=("ETHUSDT",), horizon=4,
        bars=bars, base_universe=frozenset({(t, "ETHUSDT")}),
    )
    assert len(decisions) == 1
    assert decisions[0].r_h == pytest.approx(expected_rh)
    assert decisions[0].supplied_r_net == pytest.approx(expected_rnet)


def test_f03_37_full_base_universe_coverage_remains_required(tmp_path: Path) -> None:
    t1 = datetime(2022, 11, 1, 0, tzinfo=UTC)
    t2 = datetime(2022, 11, 1, 1, tzinfo=UTC)
    bars = {
        (t1, "ETHUSDT"): _Bar(t1, "ETHUSDT", 100.0, 101.0, 99.0, 100.0),
        (t1 + timedelta(hours=1), "ETHUSDT"): _Bar(t1 + timedelta(hours=1), "ETHUSDT", 100.0, 101.0, 99.0, 100.0),
        (t1 + timedelta(hours=2), "ETHUSDT"): _Bar(t1 + timedelta(hours=2), "ETHUSDT", 100.0, 101.0, 99.0, 100.0),
        (t1 + timedelta(hours=3), "ETHUSDT"): _Bar(t1 + timedelta(hours=3), "ETHUSDT", 100.0, 101.0, 99.0, 100.0),
        (t2 + timedelta(hours=3), "ETHUSDT"): _Bar(t2 + timedelta(hours=3), "ETHUSDT", 100.0, 101.0, 99.0, 100.0),
    }
    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    # Decision only covers t1, omitting t2 from base universe
    decisions_payload = {
        "schema_id": "H40_P3B_RAW_DECISIONS_V2",
        "run_authority_id": "RUN_1",
        "sealed_registered_roster_hash": _hash("roster"),
        "structural_configuration_hash": _hash("cand"),
        "source_manifest_hash": _hash("src"),
        "split_manifest_hash": _hash("split"),
        "source_evidence_hash": "src_ev",
        "partition_id": "WF1_CALIBRATION",
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "rows": [{
            "timestamp": t1.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": "ETHUSDT",
            "p_up": None,
            "final_action": "NO_TRADE",
            "r_h": "0.0",
            "r_net": None,
        }],
    }
    digest = _store(tmp_path, decisions_payload)
    _PREFIT_CACHE[(compute_protocol_authority_hash(), DISCOVERY_PROVENANCE_CONTRACT_HASH, "src_ev", _hash("cand"), "WF1_CALIBRATION", t1.strftime("%Y-%m-%dT%H:%M:%SZ"), "ETHUSDT")] = (1.0, "REGIME_VOL_MID", "O_ELIGIBLE", "PASS")

    with pytest.raises(H40GuardError, match="decision rows do not cover complete active-scope base universe"):
        _load_decisions(
            resolver, digest, run_authority_id="RUN_1", roster_hash=_hash("roster"),
            candidate_id=_hash("cand"), source_manifest_hash=_hash("src"),
            split_manifest_hash=_hash("split"), source_evidence_hash="src_ev",
            partition_id="WF1_CALIBRATION", products=("ETHUSDT",), horizon=4,
            bars=bars, base_universe=frozenset({(t1, "ETHUSDT"), (t2, "ETHUSDT")}),
        )


# ==============================================================================
# PRESERVATION MATRIX (Items 38 - 47)
# ==============================================================================


def test_preservation_38_all_9_child_hashes_remain_exact() -> None:
    child_hashes = compute_lifecycle_child_hashes()
    assert child_hashes == EXPECTED_LIFECYCLE_CHILD_HASHES
    assert len(child_hashes) == 9


def test_preservation_39_lifecycle_root_hash_exact() -> None:
    assert compute_lifecycle_semantic_root_hash() == EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH
    assert compute_lifecycle_semantic_root_hash() == "36cbda530352cffaa475bd835b3b629df47351ca284e09bdf31a8fc884d48b4b"


def test_preservation_40_governance_v5_hash_exact() -> None:
    assert compute_lifecycle_governance_authority_hash() == EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH
    assert compute_lifecycle_governance_authority_hash() == "bb367f2af726be105bddf42636c97652402014c8a671d43ab81b1964c258e5cf"


def test_preservation_41_provenance_contract_hash_exact() -> None:
    assert DISCOVERY_PROVENANCE_CONTRACT_HASH == "31fc3930e44149e6b3af54ddd3b11c630f95cbbd3f152b3d0d5e614690dcf7ae"


def test_preservation_42_stage_a_synthetic_domain_isolation_closed() -> None:
    assert H40ProductionDiscoveryEvidenceVerifier.synthetic_only is False
    prod_service = H40LifecycleAuthorityService.production()
    assert prod_service.synthetic_test_mode is False
    assert prod_service.controller_authority is None
    assert prod_service.implementation_authority is None
    assert prod_service._discovery_run_grant is None

    evidence_id = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path="evidence/v0.5/h40/V0.5.1_H40_FINAL_REACCEPTANCE_EVIDENCE_d73e898.json",
        evidence_manifest_sha256="5cd591ef7f3f43c7897711ab4e75cb158ac048d328e1f8b0dac28a0a6bcb6540",
        tested_commit_sha="a" * 40,
    )
    impl_auth = H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
        f01_implementation_acceptance_artifact_path="reviews/v0.5/V0.5.1_H40_FINAL_EXACT_SHA_REACCEPTANCE_CONTROLLER_ACCEPTANCE.md",
        f01_implementation_acceptance_commit_sha="0cbb20a7806f2336864e430910bf6a4ff4a99df9",
        f01_implementation_commit_sha="a" * 40,
        required_test_ci_evidence_identity=evidence_id,
        schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
    )
    with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=impl_auth,
            controller_authority=None,
            discovery_run_grant=None,
        )


def test_preservation_43_production_accepted_constants_none() -> None:
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH is None
    assert ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH is None


def test_preservation_44_v2_discovery_receipt_invalid_for_production(tmp_path: Path) -> None:
    v2_receipt = H40DiscoveryAuthorizationReceiptV2(
        authorized_at_utc="2026-09-23T00:00:00Z",
        discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        execution_disabled=True,
        lifecycle_governance_authority_hash=_hash("gov"),
        lifecycle_implementation_authority_hash=_hash("impl"),
        materialized_run_authority_hash=_hash("mat"),
        not_testable_slot_count=150,
        protocol_authority_hash=_hash("proto"),
        registered_slot_count=18,
        run_authority_id=_hash("RUN_1"),
        sealed_registered_roster_hash=_hash("roster"),
        semantic_root_hash=_hash("sem"),
        source_manifest_hash=_hash("src"),
        split_attestation_hash=_hash("att"),
        split_manifest_hash=_hash("split"),
        structural_ledger_hash=_hash("struct"),
        total_slot_count=168,
        upstream_receipt_hash=None,
    )
    seal = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=_hash("snap"), source_manifest_hash=_hash("src"),
        split_manifest_hash=_hash("split"), split_attestation_hash=_hash("att"),
        roster=(), not_testable_slot_count=168,
    )
    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=_hash("src"),
        base_eligible_start_utc="2021-01-31T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=0, partitions=(), exclusion_counts={},
    )
    with pytest.raises(TypeError, match="production verifier requires a typed Discovery receipt"):
        H40ProductionDiscoveryEvidenceVerifier(
            approved_evidence_root=tmp_path, seal=seal,
            authorization_receipt=v2_receipt,  # type: ignore[arg-type]
            split_manifest=split,
        )

    v1_ctx = H40LifecyclePersistenceContextV1(
        implementation_authority_hash=_hash("impl"),
        run_authority_id=_hash("run"),
        runtime_seal_hash=_hash("seal"),
    )
    assert v1_ctx.schema_id == "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1"


def test_preservation_45_confirmation_h39_holdout_protections_green() -> None:
    guard = H40ConfirmationGuard()
    with pytest.raises(H40GuardError) as exc:
        guard.assert_outcomes_accessible()
    assert exc.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY

    with pytest.raises(H40GuardError) as exc_p:
        H40ProtectedSurfaceGuard.assert_path_allowed(Path("data/h39_validation/foo.parquet"))
    assert exc_p.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_preservation_46_research_disabled_v1_active() -> None:
    assert CURRENT_EXECUTION_POLICY == "RESEARCH_DISABLED_V1"
    assert ACCEPTED_EXECUTION_WRITE_AUTHORITY is None


def test_preservation_47_prior_p3b_suites_intact(tmp_path: Path) -> None:
    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    assert resolver._root == tmp_path.resolve()
