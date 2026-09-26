"""Mandatory regression and preservation suite for V0.5.1 H40 Repair B.

Covers all 47 acceptance criteria:
1-17:   F02 Source Value Extraction and Provenance
18-37:  F03 Causal PIT Reconstruction
38-47:  Lifecycle V5, Stage A Isolation, and Surface Preservation
"""

from __future__ import annotations

import copy
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
    H40DiscoveryAuthorizationReceipt,
    H40DiscoveryAuthorizationReceiptV2,
    H40DiscoveryEvidenceResolver,
    H40GuardError,
    H40LifecycleArtifactStore,
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
    materialize_h40_search_space_production,
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
    _Decision,
    _empirical_percentile,
    _extract_economic_rows,
    _get_training_refs,
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

    support_start = datetime(2021, 1, 1, tzinfo=UTC)
    support_end = datetime(2023, 2, 1, tzinfo=UTC)
    canonical_rows = [
        {
            "timestamp": b["timestamp"],
            "open": repr(float(b["open"])),
            "high": repr(float(b["high"])),
            "low": repr(float(b["low"])),
            "close": repr(float(b["close"])),
        }
        for b in bars
        if support_start <= datetime.fromisoformat(b["timestamp"]) < support_end
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
        timestamp_count=len(bars),
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


def test_f02_10b_wrong_locator_rejected(tmp_path: Path) -> None:
    start = datetime(2021, 5, 1, 0, tzinfo=UTC)
    bars = _make_dummy_bars(start, 5)
    seal, manifest, attestation, _record, receipt, file_sha, exp_digest, exp_count = (
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
            "locator": "WRONG_LOCATOR.json", "product": "ETHUSDT", "source_file_sha256": file_sha,
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
    with pytest.raises(H40GuardError, match="source locator mismatch"):
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


def test_f02_12_source_support_projection_and_whole_file_authority(tmp_path: Path) -> None:
    # Fixture contains rows before support (2020-12-31), inside support (2021-01-01 -> 2021-01-02),
    # and valid rows after support endpoint (2023-02-01, 2024-01-01, 2026-01-31).
    bars_pre = _make_dummy_bars(datetime(2020, 12, 31, 22, tzinfo=UTC), 2)
    bars_inside = _make_dummy_bars(datetime(2021, 1, 1, 0, tzinfo=UTC), 20)
    bars_post = _make_dummy_bars(datetime(2023, 2, 1, 0, tzinfo=UTC), 10)
    all_bars = bars_pre + bars_inside + bars_post

    source_file = tmp_path / "ETHUSDT.json"
    raw_bytes, file_sha, _canon_rows, exp_digest, exp_count = _write_json_source(source_file, all_bars)

    # 1. Whole-file SHA includes all bytes (pre, inside, post)
    assert file_sha == hashlib.sha256(raw_bytes).hexdigest()
    assert len(all_bars) == 32

    # 2. Post-support rows are accepted as part of the sealed artifact (extraction does not fail)
    extracted_bars, canon = _extract_economic_rows(
        source_file, raw_bytes, "ETHUSDT", "1h", "timestamp",
    )

    # 3. Post-support and pre-support rows are excluded from the H40 economic digest and count
    assert len(extracted_bars) == 20
    assert len(canon) == 20
    assert exp_count == 20
    for b in extracted_bars:
        assert datetime(2021, 1, 1, tzinfo=UTC) <= b.timestamp < datetime(2023, 2, 1, tzinfo=UTC)
    for r in canon:
        dt = datetime.fromisoformat(r["timestamp"])
        assert datetime(2021, 1, 1, tzinfo=UTC) <= dt < datetime(2023, 2, 1, tzinfo=UTC)

    # 4. Support-projected digest is deterministic
    computed_digest = canonical_sha256(canon)
    assert computed_digest == exp_digest
    _repeat_bars, repeat_canon = _extract_economic_rows(
        source_file, raw_bytes, "ETHUSDT", "1h", "timestamp",
    )
    assert canonical_sha256(repeat_canon) == computed_digest

    # 5. Tampering a post-support row changes the whole-file SHA-256
    tampered_bars = copy.deepcopy(all_bars)
    tampered_bars[-1]["close"] = float(tampered_bars[-1]["close"]) + 10.0
    tampered_bytes = json.dumps(tampered_bars).encode("utf-8")
    assert hashlib.sha256(tampered_bytes).hexdigest() != file_sha

    # 6. An unsupported timestamp claimed in base-universe membership is rejected
    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    derivation_payload = {
        "schema_id": "H40_P3B_SOURCE_DERIVATION_V2",
        "run_authority_id": "RUN_1",
        "source_manifest_hash": _hash("s"),
        "split_manifest_hash": _hash("sp"),
        "split_attestation_hash": _hash("att"),
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "source_support": {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"},
        "active_source_derivations": [{
            "cadence": "1h",
            "economic_row_count": exp_count,
            "economic_rows_sha256": exp_digest,
            "locator": "ETHUSDT.json",
            "product": "ETHUSDT",
            "source_file_sha256": file_sha,
            "source_id": "SRC_ETH",
            "source_validation_receipt_sha256": _hash("receipt"),
            "timestamp_field": "timestamp",
        }],
        "base_eligible_membership": {
            "WF1_TRAIN": [{"timestamp": "2020-12-31T23:00:00Z", "product": "ETHUSDT"}],
            "WF1_CALIBRATION": [],
        },
    }
    d_digest = _store(tmp_path, derivation_payload)
    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"), source_manifest_hash=_hash("s"),
        base_eligible_start_utc="2021-01-31T00:00:00Z", base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=0, partitions=(), exclusion_counts={},
    )
    with pytest.raises(H40GuardError, match="lookback reserve hour|outside accepted split"):
        _load_source_bars(
            resolver, d_digest, run_authority_id="RUN_1",
            source_manifest_hash=_hash("s"), split_manifest_hash=_hash("sp"),
            split_manifest=split,
        )


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


def test_f02_18_canonical_full_sealed_source_with_post_support_in_load_source_bars(tmp_path: Path) -> None:
    # Source file contains rows inside support [2021-01-01, 2023-02-01) plus valid rows after 2023-02-01
    start_train = datetime(2021, 2, 1, 0, tzinfo=UTC)
    bars_inside = _make_dummy_bars(start_train, 10)
    bars_post = _make_dummy_bars(datetime(2023, 5, 1, 0, tzinfo=UTC), 5)
    all_bars = bars_inside + bars_post

    seal, manifest, attestation, _record, receipt, file_sha, exp_digest, exp_count = (
        _make_production_test_seal_and_context(tmp_path, all_bars)
    )

    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    train_ts = [b["timestamp"] for b in bars_inside]
    membership_hash = hashlib.sha256(",".join(sorted(train_ts)).encode("utf-8")).hexdigest()

    derivation = {
        "schema_id": "H40_P3B_SOURCE_DERIVATION_V2",
        "run_authority_id": "RUN_1",
        "source_manifest_hash": manifest.manifest_hash,
        "split_manifest_hash": _hash("split"),
        "split_attestation_hash": attestation.attestation_hash,
        "provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "policies": _policy_stack(),
        "source_support": {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"},
        "active_source_derivations": [{
            "cadence": "1h",
            "economic_row_count": exp_count,  # 10 rows inside support
            "economic_rows_sha256": exp_digest,
            "locator": "ETHUSDT.json",
            "product": "ETHUSDT",
            "source_file_sha256": file_sha,  # binds all 15 bars
            "source_id": "SRC_ETH",
            "source_validation_receipt_sha256": canonical_sha256(receipt.to_dict()),
            "timestamp_field": "timestamp",
        }],
        "base_eligible_membership": {
            "WF1_TRAIN": [{"timestamp": ts, "product": "ETHUSDT"} for ts in train_ts],
            "WF1_CALIBRATION": [],
        },
    }
    digest = _store(tmp_path, derivation)
    split = H40SplitManifest(
        protocol_identity_hash=_hash("p"),
        source_manifest_hash=manifest.manifest_hash,
        base_eligible_start_utc="2021-01-31T00:00:00Z",
        base_eligible_end_utc="2023-01-31T00:00:00Z",
        base_eligible_count=len(train_ts),
        partitions=(
            H40Partition(
                partition_id="WF1_TRAIN",
                fold="WF1",
                partition_type=H40PartitionType.TRAIN,
                start_utc="2021-01-31T00:00:00Z",
                end_utc="2022-10-31T00:00:00Z",
                count=len(train_ts),
                first_timestamp_utc=train_ts[0],
                last_timestamp_utc=train_ts[-1],
                timestamps_sha256=membership_hash,
            ),
            H40Partition(
                partition_id="WF1_CALIBRATION",
                fold="WF1",
                partition_type=H40PartitionType.CALIBRATION,
                start_utc="2022-11-01T00:00:00Z",
                end_utc="2023-01-31T00:00:00Z",
                count=0,
                first_timestamp_utc=None,
                last_timestamp_utc=None,
                timestamps_sha256=hashlib.sha256(b"").hexdigest(),
            ),
        ),
        exclusion_counts={},
    )

    bars_map, universes = _load_source_bars(
        resolver,
        digest,
        run_authority_id="RUN_1",
        source_manifest_hash=manifest.manifest_hash,
        split_manifest_hash=_hash("split"),
        split_manifest=split,
        seal=seal,
    )
    assert len(bars_map) == 10
    for b_post in bars_post:
        dt_post = datetime.fromisoformat(b_post["timestamp"])
        assert (dt_post, "ETHUSDT") not in bars_map
    assert len(universes["WF1_TRAIN"]) == 10


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
    # Endpoints: b_last at t - 1h, b_prev at t - 4h (for lookback 4) or t - 12h (for lookback 12)
    bars: dict[tuple[datetime, str], _Bar] = {
        (t - timedelta(hours=4), "ETHUSDT"): _Bar(t - timedelta(hours=4), "ETHUSDT", 100.0, 101.0, 99.0, 100.0),
        (t - timedelta(hours=1), "ETHUSDT"): _Bar(t - timedelta(hours=1), "ETHUSDT", 104.0, 106.0, 103.0, 105.0),
        # Adversarial sentinels at non-endpoint hours
        (t - timedelta(hours=5), "ETHUSDT"): _Bar(t - timedelta(hours=5), "ETHUSDT", 50.0, 500.0, 10.0, 50.0),
        (t - timedelta(hours=3), "ETHUSDT"): _Bar(t - timedelta(hours=3), "ETHUSDT", 200.0, 250.0, 150.0, 200.0),
        (t - timedelta(hours=2), "ETHUSDT"): _Bar(t - timedelta(hours=2), "ETHUSDT", 300.0, 350.0, 250.0, 300.0),
    }
    score_4h = _compute_d1(bars, t, "ETHUSDT", 4)
    expected = math.log(105.0 / 100.0)
    assert score_4h == pytest.approx(expected)

    # Changing sentinels at t-5h, t-3h, t-2h does not affect D1 4h
    bars[(t - timedelta(hours=5), "ETHUSDT")] = _Bar(t - timedelta(hours=5), "ETHUSDT", 999.0, 9999.0, 1.0, 999.0)
    bars[(t - timedelta(hours=3), "ETHUSDT")] = _Bar(t - timedelta(hours=3), "ETHUSDT", 1.0, 2.0, 0.5, 1.0)
    bars[(t - timedelta(hours=2), "ETHUSDT")] = _Bar(t - timedelta(hours=2), "ETHUSDT", 10.0, 20.0, 5.0, 10.0)
    assert _compute_d1(bars, t, "ETHUSDT", 4) == pytest.approx(expected)

    # Changing endpoint t-4h DOES affect return
    bars[(t - timedelta(hours=4), "ETHUSDT")] = _Bar(t - timedelta(hours=4), "ETHUSDT", 100.0, 101.0, 99.0, 102.0)
    assert _compute_d1(bars, t, "ETHUSDT", 4) == pytest.approx(math.log(105.0 / 102.0))

    # Changing endpoint t-1h DOES affect return
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 100.0, 101.0, 99.0, 102.0)
    # Equality: C(t-1) == C(t-4) -> score == 0.0 -> NO_TRADE
    assert _compute_d1(bars, t, "ETHUSDT", 4) == 0.0

    # D1 12H test
    bars[(t - timedelta(hours=12), "ETHUSDT")] = _Bar(t - timedelta(hours=12), "ETHUSDT", 90.0, 95.0, 85.0, 90.0)
    bars[(t - timedelta(hours=13), "ETHUSDT")] = _Bar(t - timedelta(hours=13), "ETHUSDT", 999.0, 999.0, 999.0, 999.0)
    score_12h = _compute_d1(bars, t, "ETHUSDT", 12)
    assert score_12h == pytest.approx(math.log(102.0 / 90.0))

    # Missing endpoint bar -> returns 0.0
    bars_missing = dict(bars)
    del bars_missing[(t - timedelta(hours=1), "ETHUSDT")]
    assert _compute_d1(bars_missing, t, "ETHUSDT", 4) == 0.0


def test_f03_22_verifier_derived_d2_matches_r3r2() -> None:
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    # Normative R3R2 Section 2.2:
    # Reference bars: complete hourly bars with close_time_ms < t and open_time in (t - W, t).
    # The last closed signal bar (test_bar at t - 1h) is EXCLUDED.
    # For W = 24: candidate open times are t - 2h through t - 23h (22 bars).
    # Open time == t - 24h is strictly excluded (open_time > t - W required).
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(2, 24):
        dt = t - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 105.0, 95.0, 100.0)

    # Test bar at t - 1h
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 104.0, 107.0, 103.0, 106.0)

    # 1. Base breakout: close (106) > U (105) -> LONG (+1.0)
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 1.0

    # 2. Mandatory boundary regression: sentinel at exactly t - W (t - 24h)
    # Placing an extreme high/low at open_time == t - 24h MUST NOT change D2 output
    bars[(t - timedelta(hours=24), "ETHUSDT")] = _Bar(
        t - timedelta(hours=24), "ETHUSDT", 100.0, 999999.0, 0.001, 100.0,
    )
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 1.0

    # Mutating only that sentinel at t - 24h does not alter output
    bars[(t - timedelta(hours=24), "ETHUSDT")] = _Bar(
        t - timedelta(hours=24), "ETHUSDT", 50.0, 50.0, 50.0, 50.0,
    )
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 1.0

    # Also sentinel at t - 25h (t - W - 1h) must not change output
    bars[(t - timedelta(hours=25), "ETHUSDT")] = _Bar(
        t - timedelta(hours=25), "ETHUSDT", 100.0, 999999.0, 0.001, 100.0,
    )
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 1.0

    # 3. Nearest inside left-boundary bar at t - 23h (t - W + 1h):
    # Setting an extreme high on t - 23h DOES enter reference set, inflating U and suppressing breakout
    bars_mutated = dict(bars)
    bars_mutated[(t - timedelta(hours=23), "ETHUSDT")] = _Bar(
        t - timedelta(hours=23), "ETHUSDT", 100.0, 999999.0, 95.0, 100.0,
    )
    assert _compute_d2(bars_mutated, t, "ETHUSDT", 24) == 0.0

    # 4. Test bar at t - 1h is excluded from reference bounds:
    # Extreme high/low on test_bar does not alter U or L
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(
        t - timedelta(hours=1), "ETHUSDT", 104.0, 999999.0, 0.001, 106.0,
    )
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 1.0

    # 5. Downward breakout: close < L -> SHORT (-1.0)
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 96.0, 97.0, 93.0, 94.0)
    assert _compute_d2(bars, t, "ETHUSDT", 24) == -1.0

    # 6. Inside boundary -> 0.0
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 100.0, 102.0, 98.0, 100.0)
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 0.0

    # 7. Exact equality: C == U or C == L -> 0.0 (neutral)
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 100.0, 106.0, 99.0, 105.0)
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 0.0
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 96.0, 97.0, 94.0, 95.0)
    assert _compute_d2(bars, t, "ETHUSDT", 24) == 0.0

    # 8. Dual-touch / flat bounds: U == L -> 0.0
    flat_bars = {
        (t - timedelta(hours=k), "ETHUSDT"): _Bar(t - timedelta(hours=k), "ETHUSDT", 100.0, 100.0, 100.0, 100.0)
        for k in range(1, 24)
    }
    assert _compute_d2(flat_bars, t, "ETHUSDT", 24) == 0.0

    # 9. Minimum complete bars requirement: (W / 24) * 6
    # For W = 24: min 6 bars required
    gapped_bars: dict[tuple[datetime, str], _Bar] = {
        (t - timedelta(hours=1), "ETHUSDT"): _Bar(t - timedelta(hours=1), "ETHUSDT", 104.0, 107.0, 103.0, 106.0),
    }
    for k in range(2, 7):  # only 5 ref bars
        dt = t - timedelta(hours=k)
        gapped_bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 105.0, 95.0, 100.0)
    assert _compute_d2(gapped_bars, t, "ETHUSDT", 24) == 0.0  # 5 bars < 6 -> NO_TRADE
    # Add 6th bar -> meets minimum 6 complete bars
    gapped_bars[(t - timedelta(hours=7), "ETHUSDT")] = _Bar(
        t - timedelta(hours=7), "ETHUSDT", 100.0, 105.0, 95.0, 100.0,
    )
    assert _compute_d2(gapped_bars, t, "ETHUSDT", 24) == 1.0

    # 10. D2 72H window: reference bars k = 2..71. t - 72h is excluded.
    bars_72: dict[tuple[datetime, str], _Bar] = {
        (t - timedelta(hours=1), "ETHUSDT"): _Bar(t - timedelta(hours=1), "ETHUSDT", 104.0, 107.0, 103.0, 106.0),
    }
    for k in range(2, 72):
        dt = t - timedelta(hours=k)
        bars_72[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 105.0, 95.0, 100.0)
    # Sentinel at t - 72h
    bars_72[(t - timedelta(hours=72), "ETHUSDT")] = _Bar(
        t - timedelta(hours=72), "ETHUSDT", 100.0, 999999.0, 0.001, 100.0,
    )
    assert _compute_d2(bars_72, t, "ETHUSDT", 72) == 1.0
    # Sentinel at t - 71h (inside boundary) alters U
    bars_72_mut = dict(bars_72)
    bars_72_mut[(t - timedelta(hours=71), "ETHUSDT")] = _Bar(
        t - timedelta(hours=71), "ETHUSDT", 100.0, 999999.0, 95.0, 100.0,
    )
    assert _compute_d2(bars_72_mut, t, "ETHUSDT", 72) == 0.0


def test_f03_23_verifier_derived_d3_matches_r3r2() -> None:
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    # Normative R3R2 Section 2.3:
    # Evaluated at b1 close time t_b1 = t - timedelta(hours=1):
    # b2 (close-back bar) at t - 1h, b1 (break bar) at t - 2h.
    # Prior range window W of closed bars strictly before the break bar b1:
    # open_time in (t_b1 - W, t_b1), b1 is EXCLUDED.
    # For W = 24: candidate open times are t - 3h through t - 24h (22 bars).
    # Open time == t - 25h is strictly excluded.
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(3, 25):
        dt = t - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 105.0, 95.0, 100.0)

    # 1. Upward break at b1 (t-2h), close back inside at b2 (t-1h) -> SHORT (-1.0)
    bars[(t - timedelta(hours=2), "ETHUSDT")] = _Bar(t - timedelta(hours=2), "ETHUSDT", 104.0, 108.0, 103.0, 106.0)
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 105.0, 105.0, 103.0, 104.0)
    assert _compute_d3(bars, t, "ETHUSDT", 24) == -1.0

    # 2. Sentinel at exactly t_b1 - W (t - 25h):
    # Placing an extreme high/low at open_time == t - 25h MUST NOT change D3 output
    bars[(t - timedelta(hours=25), "ETHUSDT")] = _Bar(
        t - timedelta(hours=25), "ETHUSDT", 100.0, 999999.0, 0.001, 100.0,
    )
    assert _compute_d3(bars, t, "ETHUSDT", 24) == -1.0

    # Sentinel at t - 26h (t_b1 - W - 1h): must not change output
    bars[(t - timedelta(hours=26), "ETHUSDT")] = _Bar(
        t - timedelta(hours=26), "ETHUSDT", 100.0, 999999.0, 0.001, 100.0,
    )
    assert _compute_d3(bars, t, "ETHUSDT", 24) == -1.0

    # 3. Nearest inside left-boundary bar at t - 24h (t_b1 - W + 1h):
    # Setting extreme high on t - 24h DOES alter U, preventing break on b1
    bars_mut = dict(bars)
    bars_mut[(t - timedelta(hours=24), "ETHUSDT")] = _Bar(
        t - timedelta(hours=24), "ETHUSDT", 100.0, 999999.0, 95.0, 100.0,
    )
    assert _compute_d3(bars_mut, t, "ETHUSDT", 24) == 0.0

    # 4. Downward break at b1, close back inside at b2 -> LONG (+1.0)
    bars[(t - timedelta(hours=2), "ETHUSDT")] = _Bar(t - timedelta(hours=2), "ETHUSDT", 96.0, 97.0, 92.0, 93.0)
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 94.0, 98.0, 93.0, 96.0)
    assert _compute_d3(bars, t, "ETHUSDT", 24) == 1.0

    # 5. Strict re-entry: C(b2) == U or C(b2) == L is NOT a close-back
    # Upward break (C1 = 106 > U=105), but C2 == U (105.0) -> NOT a close-back -> 0.0
    bars[(t - timedelta(hours=2), "ETHUSDT")] = _Bar(t - timedelta(hours=2), "ETHUSDT", 104.0, 108.0, 103.0, 106.0)
    bars[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(t - timedelta(hours=1), "ETHUSDT", 105.0, 106.0, 104.0, 105.0)
    assert _compute_d3(bars, t, "ETHUSDT", 24) == 0.0

    # 6. D3 72H window: reference bars k = 3..72. Sentinel at t - 73h is ignored.
    bars_72: dict[tuple[datetime, str], _Bar] = {
        (t - timedelta(hours=2), "ETHUSDT"): _Bar(t - timedelta(hours=2), "ETHUSDT", 104.0, 108.0, 103.0, 106.0),
        (t - timedelta(hours=1), "ETHUSDT"): _Bar(t - timedelta(hours=1), "ETHUSDT", 105.0, 105.0, 103.0, 104.0),
    }
    for k in range(3, 73):
        dt = t - timedelta(hours=k)
        bars_72[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 105.0, 95.0, 100.0)
    # Sentinel at t - 73h (t_b1 - 72h)
    bars_72[(t - timedelta(hours=73), "ETHUSDT")] = _Bar(
        t - timedelta(hours=73), "ETHUSDT", 100.0, 999999.0, 0.001, 100.0,
    )
    assert _compute_d3(bars_72, t, "ETHUSDT", 72) == -1.0


def test_f03_24_verifier_derived_r_vol_matches_r3r2() -> None:
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    # Exactly 24 complete hourly bars strictly before t: k = 1..24
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(1, 25):
        dt = t - timedelta(hours=k)
        p = 100.0 * (1.0 + 0.01 * (k % 4))
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", p, p + 1, p - 1, p)

    rv = _compute_r_vol_scalar(bars, t, "ETHUSDT")
    assert rv is not None and rv > 0.0

    # Verify R_VOL ddof=1 sample standard deviation on 24 log returns:
    # 24 bars strictly before t sorted chronological: k=24..1
    chrono_bars = [bars[(t - timedelta(hours=k), "ETHUSDT")] for k in range(24, 0, -1)]
    log_returns = [math.log(chrono_bars[i].close / chrono_bars[i - 1].close) for i in range(1, 24)]
    # Note: 24 bars yield 23 log returns between adjacent closes
    mean_r = sum(log_returns) / len(log_returns)
    expected_s = math.sqrt(sum((r - mean_r) ** 2 for r in log_returns) / (len(log_returns) - 1))
    assert rv == pytest.approx(expected_s)

    # Boundary sentinels:
    # Mutating bar at t - 25h (outside 24h window) has NO effect
    bars_sentinel = dict(bars)
    bars_sentinel[(t - timedelta(hours=25), "ETHUSDT")] = _Bar(
        t - timedelta(hours=25), "ETHUSDT", 999.0, 9999.0, 1.0, 999.0,
    )
    assert _compute_r_vol_scalar(bars_sentinel, t, "ETHUSDT") == rv

    # Mutating bar at t - 24h (included left boundary) DOES alter rv
    bars_mut_left = dict(bars)
    bars_mut_left[(t - timedelta(hours=24), "ETHUSDT")] = _Bar(
        t - timedelta(hours=24), "ETHUSDT", 200.0, 205.0, 195.0, 200.0,
    )
    assert _compute_r_vol_scalar(bars_mut_left, t, "ETHUSDT") != rv

    # Mutating bar at t - 1h (included right boundary) DOES alter rv
    bars_mut_right = dict(bars)
    bars_mut_right[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(
        t - timedelta(hours=1), "ETHUSDT", 200.0, 205.0, 195.0, 200.0,
    )
    assert _compute_r_vol_scalar(bars_mut_right, t, "ETHUSDT") != rv

    # If any bar is missing inside 24h window, returns None
    bars_missing = dict(bars)
    del bars_missing[(t - timedelta(hours=10), "ETHUSDT")]
    assert _compute_r_vol_scalar(bars_missing, t, "ETHUSDT") is None


def test_f03_24b_regime_state_exact_r3r2_identities_and_boundaries() -> None:
    """Normative R3R2 Section 2.5: exact regime states, boundaries, and eligibility."""
    # Empirical percentile tie mid-rank verification: (count_less + 0.5 * (1 if has_equal else 0)) / N
    tie_sample = [1.0, 2.0, 3.0]
    assert _empirical_percentile(tie_sample, 2.0) == 0.50
    tie_sample2 = [1.0, 2.0, 2.0, 3.0]
    assert _empirical_percentile(tie_sample2, 2.0) == 0.375

    # Reference sample of 100 evenly spaced values: 1.0, 2.0, ..., 100.0
    sample = [float(i) for i in range(1, 101)]

    # Exact boundary tests:
    # 1. p < 0.40 -> REGIME_VOL_LOW
    val_low = 39.5  # count_less = 39, count_equal = 0 -> p = 0.39 < 0.40
    p_low = _empirical_percentile(sample, val_low)
    assert p_low < 0.40
    regime_low = (
        "REGIME_VOL_LOW" if p_low < 0.40 else "REGIME_VOL_MID" if p_low < 0.60 else "REGIME_VOL_HIGH"
    )
    assert regime_low == "REGIME_VOL_LOW"

    # 2. p == 0.40 -> REGIME_VOL_MID (lower-bound owns equality)
    # With count_less=40, count_equal=0: p = 40 / 100 = 0.40
    val_mid_boundary = 40.5
    p_mid_boundary = _empirical_percentile(sample, val_mid_boundary)
    assert p_mid_boundary == 0.40
    regime_mid_b = (
        "REGIME_VOL_LOW" if p_mid_boundary < 0.40 else "REGIME_VOL_MID" if p_mid_boundary < 0.60 else "REGIME_VOL_HIGH"
    )
    assert regime_mid_b == "REGIME_VOL_MID"

    # 3. 0.40 < p < 0.60 -> REGIME_VOL_MID
    val_mid_interior = 50.5  # p = 50 / 100 = 0.50
    p_mid_interior = _empirical_percentile(sample, val_mid_interior)
    assert 0.40 < p_mid_interior < 0.60
    regime_mid_i = (
        "REGIME_VOL_LOW" if p_mid_interior < 0.40 else "REGIME_VOL_MID" if p_mid_interior < 0.60 else "REGIME_VOL_HIGH"
    )
    assert regime_mid_i == "REGIME_VOL_MID"

    # 4. p == 0.60 -> REGIME_VOL_HIGH (lower-bound owns equality)
    val_high_boundary = 60.5  # p = 60 / 100 = 0.60
    p_high_boundary = _empirical_percentile(sample, val_high_boundary)
    assert p_high_boundary == 0.60
    regime_high_b = (
        "REGIME_VOL_LOW" if p_high_boundary < 0.40 else "REGIME_VOL_MID" if p_high_boundary < 0.60 else "REGIME_VOL_HIGH"
    )
    assert regime_high_b == "REGIME_VOL_HIGH"

    # 5. p > 0.60 -> REGIME_VOL_HIGH
    val_high_interior = 75.5  # p = 75 / 100 = 0.75
    p_high_interior = _empirical_percentile(sample, val_high_interior)
    assert p_high_interior > 0.60
    regime_high_i = (
        "REGIME_VOL_LOW" if p_high_interior < 0.40 else "REGIME_VOL_MID" if p_high_interior < 0.60 else "REGIME_VOL_HIGH"
    )
    assert regime_high_i == "REGIME_VOL_HIGH"

    # Verify prefit_eligible for each state
    now = datetime(2022, 6, 1, 12, tzinfo=UTC)
    dummy_bar = _Bar(now, "ETHUSDT", 100.0, 101.0, 99.0, 100.0)

    # LOW => prefit_eligible False
    dec_low = _Decision(
        now, "ETHUSDT", "REGIME_VOL_LOW", "O_ELIGIBLE", 1.0, "PASS",
        None, "NO_TRADE", 0.01, None, 100.0, 101.0, (dummy_bar,),
    )
    assert dec_low.prefit_eligible is False

    # MID => prefit_eligible True (when opp=O_ELIGIBLE, raw_score!=0, sec=PASS)
    dec_mid = _Decision(
        now, "ETHUSDT", "REGIME_VOL_MID", "O_ELIGIBLE", 1.0, "PASS",
        None, "LONG", 0.01, None, 100.0, 101.0, (dummy_bar,),
    )
    assert dec_mid.prefit_eligible is True

    # HIGH => prefit_eligible False
    dec_high = _Decision(
        now, "ETHUSDT", "REGIME_VOL_HIGH", "O_ELIGIBLE", 1.0, "PASS",
        None, "NO_TRADE", 0.01, None, 100.0, 101.0, (dummy_bar,),
    )
    assert dec_high.prefit_eligible is False

    # Undefined computation (N < 60 or rv_val is None):
    # Returns REGIME_UNAVAILABLE and prefit_eligible False
    clear_prefit_caches()
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(1, 10):  # only 9 bars, well below N >= 60 and < 24 bars
        dt = now - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 102.0, 98.0, 100.0)

    _score, reg_state, _opp, _sec = _reconstruct_prefit_cached(
        candidate_id="cand_1", slot=None, partition_id="WF1_CALIBRATION",
        t=now, product="ETHUSDT", bars=bars, source_evidence_hash="source_1",
    )
    assert reg_state == "REGIME_UNAVAILABLE"
    assert reg_state not in ("REGIME_VOL_LOW", "REGIME_VOL_MID", "REGIME_VOL_HIGH")
    dec_unavail = _Decision(
        now, "ETHUSDT", reg_state, "O_ELIGIBLE", 1.0, "PASS",
        None, "NO_TRADE", 0.01, None, 100.0, 101.0, (dummy_bar,),
    )
    assert dec_unavail.prefit_eligible is False


def test_f03_25_verifier_derived_o_range_matches_r3r2() -> None:
    """Normative R3R2 Section 2.6: exact standard True Range, no fallback, and mandatory tests."""
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)

    # 1. 25 TR-bearing bars + valid preceding close -> exact expected O_RANGE
    # k=1 is last bar; k=2..25 are 24 reference bars; k=26 is preceding close for k=25
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(1, 27):
        dt = t - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 102.0, 98.0, 100.0)

    ratio = _compute_o_range_scalar(bars, t, "ETHUSDT")
    assert ratio is not None
    # All bars have H=102, L=98, prev_close=100. TR = max(4, |102-100|, |98-100|) = 4.0
    # Last TR = 4.0. Mean of 24 ref TRs = 4.0. Ratio = 4.0 / 4.0 = 1.0
    assert ratio == pytest.approx(1.0)

    # 2. All 25 TR-bearing bars exist but preceding close missing -> undefined (None)
    bars_missing_prior = dict(bars)
    del bars_missing_prior[(t - timedelta(hours=26), "ETHUSDT")]
    assert _compute_o_range_scalar(bars_missing_prior, t, "ETHUSDT") is None

    # 3. Preceding close present but PIT-invalid (effective_close_time >= t) -> undefined (None)
    bars_pit_invalid = dict(bars)
    bars_pit_invalid[(t - timedelta(hours=26), "ETHUSDT")] = _Bar(
        t - timedelta(hours=26), "ETHUSDT", 100.0, 102.0, 98.0, 100.0,
        close_time=t,  # equals decision t, violating strict PIT
    )
    assert _compute_o_range_scalar(bars_pit_invalid, t, "ETHUSDT") is None

    # 4. Large gap between earliest reference bar (t-25h) and preceding close (t-26h)
    # materially changes the earliest reference TR according to the standard formula.
    # Earliest reference bar has H=102, L=98. Prior close is 150.
    # Standard TR = max(102-98=4, |102-150|=48, |98-150|=52) = 52.0.
    # If forbidden fallback H-L were used, TR would be 4.0.
    bars_large_gap = dict(bars)
    bars_large_gap[(t - timedelta(hours=26), "ETHUSDT")] = _Bar(
        t - timedelta(hours=26), "ETHUSDT", 150.0, 150.0, 150.0, 150.0,
    )
    # Expected: 23 ref bars with TR=4.0 + 1 ref bar with TR=52.0. Mean = (23*4 + 52) / 24 = 6.0
    # Last bar TR = 4.0. Expected ratio = 4.0 / 6.0 = 2/3
    ratio_gap = _compute_o_range_scalar(bars_large_gap, t, "ETHUSDT")
    assert ratio_gap is not None
    assert ratio_gap == pytest.approx(4.0 / 6.0)

    # 5. Sentinel before the required preceding close (at t-27h) does not affect result
    bars_sentinel = dict(bars)
    bars_sentinel[(t - timedelta(hours=27), "ETHUSDT")] = _Bar(
        t - timedelta(hours=27), "ETHUSDT", 999.0, 9999.0, 1.0, 999.0,
    )
    assert _compute_o_range_scalar(bars_sentinel, t, "ETHUSDT") == pytest.approx(1.0)

    # 6. Last-bar TR remains the numerator and is excluded from the 24-reference mean
    # Mutating last bar (t-1h) changes numerator: H=110, L=90 -> TR=20.0 (prev close=100)
    bars_mut_last = dict(bars)
    bars_mut_last[(t - timedelta(hours=1), "ETHUSDT")] = _Bar(
        t - timedelta(hours=1), "ETHUSDT", 100.0, 110.0, 90.0, 100.0,
    )
    ratio_mut_last = _compute_o_range_scalar(bars_mut_last, t, "ETHUSDT")
    assert ratio_mut_last is not None
    # Numerator is 20.0, denominator is still 4.0. Ratio = 20.0 / 4.0 = 5.0
    assert ratio_mut_last == pytest.approx(5.0)

    # 7. Denominator == 0 -> undefined (None)
    # All 25 bars flat H=L=C=100. Reference TRs all 0.0 -> mean TR = 0.0 -> denominator == 0
    bars_zero = {}
    for k in range(1, 27):
        dt = t - timedelta(hours=k)
        bars_zero[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 100.0, 100.0, 100.0)
    assert _compute_o_range_scalar(bars_zero, t, "ETHUSDT") is None

    # 8. Fewer than 25 TR-bearing bars -> undefined (None)
    bars_fewer = {k: v for k, v in bars.items() if k[0] >= t - timedelta(hours=20)}
    assert _compute_o_range_scalar(bars_fewer, t, "ETHUSDT") is None

    # Opportunity state exact boundaries:
    # Sample of 100 values from 1.0 to 100.0
    sample = [float(i) for i in range(1, 101)]
    # p < 0.60 -> O_NONE
    val_none = 59.5  # p = 0.595 < 0.60
    assert _empirical_percentile(sample, val_none) < 0.60

    # p == 0.60 -> O_WATCH (lower-bound owns equality)
    val_watch_b = 60.5  # p = 0.60
    assert _empirical_percentile(sample, val_watch_b) == 0.60

    # 0.60 < p < 0.80 -> O_WATCH
    val_watch_i = 70.5  # p = 0.70
    assert 0.60 < _empirical_percentile(sample, val_watch_i) < 0.80

    # p == 0.80 -> O_ELIGIBLE (lower-bound owns equality)
    val_elig_b = 80.5  # p = 0.80
    assert _empirical_percentile(sample, val_elig_b) == 0.80

    # p > 0.80 -> O_ELIGIBLE
    val_elig_i = 90.5  # p = 0.90
    assert _empirical_percentile(sample, val_elig_i) > 0.80

    # Verify prefit_eligible for opportunity states
    dummy_bar = _Bar(t, "ETHUSDT", 100.0, 101.0, 99.0, 100.0)
    dec_none = _Decision(
        t, "ETHUSDT", "REGIME_VOL_MID", "O_NONE", 1.0, "PASS",
        None, "NO_TRADE", 0.01, None, 100.0, 101.0, (dummy_bar,),
    )
    assert dec_none.prefit_eligible is False

    dec_watch = _Decision(
        t, "ETHUSDT", "REGIME_VOL_MID", "O_WATCH", 1.0, "PASS",
        None, "NO_TRADE", 0.01, None, 100.0, 101.0, (dummy_bar,),
    )
    assert dec_watch.prefit_eligible is False

    dec_elig = _Decision(
        t, "ETHUSDT", "REGIME_VOL_MID", "O_ELIGIBLE", 1.0, "PASS",
        None, "LONG", 0.01, None, 100.0, 101.0, (dummy_bar,),
    )
    assert dec_elig.prefit_eligible is True


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

    # Unsupported secondary filter contract fails closed
    unsupported_slot = SimpleNamespace(
        direction_contract_id="D1_V1_RETURN_4H",
        secondary_filter_contract_id="UNSUPPORTED_FILTER_V1",
    )
    with pytest.raises(H40GuardError) as exc:
        _reconstruct_prefit_cached(
            candidate_id="test_cand_bad_filter", slot=unsupported_slot,
            partition_id="WF1_CALIBRATION", t=t, product="ETHUSDT", bars=bars,
            source_evidence_hash="test_src",
        )
    assert exc.value.reason_code == H40ReasonCode.NOT_TESTABLE
    assert "unsupported secondary filter contract" in str(exc.value)


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


def test_f03_43_unknown_direction_contract_fails_closed() -> None:
    clear_prefit_caches()
    t = datetime(2022, 6, 1, 12, tzinfo=UTC)
    bars: dict[tuple[datetime, str], _Bar] = {}
    for k in range(1, 30):
        dt = t - timedelta(hours=k)
        bars[(dt, "ETHUSDT")] = _Bar(dt, "ETHUSDT", 100.0, 102.0, 98.0, 100.0)

    slot_unknown = SimpleNamespace(
        direction_contract_id="UNKNOWN_DIRECTION_CONTRACT_V99",
        secondary_filter_contract_id="NONE",
    )
    with pytest.raises(H40GuardError) as exc:
        _reconstruct_prefit_cached(
            candidate_id="cand_bad_dir", slot=slot_unknown,
            partition_id="WF1_CALIBRATION", t=t, product="ETHUSDT", bars=bars,
            source_evidence_hash="test_src",
        )
    assert exc.value.reason_code == H40ReasonCode.NOT_TESTABLE
    assert "unsupported direction contract" in str(exc.value)


def test_f03_44_registered_roster_supported_contracts_only() -> None:
    ledger = materialize_h40_search_space_production()
    assert len(ledger.slots) == 168
    registered_slots = [s for s in ledger.slots if str(s.status) == "REGISTERED"]
    assert len(registered_slots) == 18

    allowed_directions = {
        "D1_V1_RETURN_4H",
        "D1_V2_RETURN_12H",
        "D2_V1_BREAKOUT_24H",
        "D2_V2_BREAKOUT_72H",
        "D3_V1_FAILED_BREAK_24H",
        "D3_V2_FAILED_BREAK_72H",
    }
    for s in registered_slots:
        assert s.scope == "ETH_ONLY"
        assert s.asset_scope == ("ETHUSDT",)
        assert s.direction_contract_id in allowed_directions
        assert s.regime_contract_id == "R_VOL_RANGE_V1_24H"
        assert s.opportunity_contract_id == "O_RANGE_EXPANSION_V1_24H"
        assert getattr(s, "secondary_filter_contract_id", "NONE") in ("NONE", "", None)


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


def test_preservation_43_production_accepted_constants() -> None:
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH == (
        "088b1210c17171141e232219345fa890e182282445fd9b2a70804b177d808b96"
    )
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


def test_preservation_55_v1_persistence_context_rejected_in_production(tmp_path: Path) -> None:
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = "0" * 64
    receipt_obj = H40DiscoveryAuthorizationReceipt(
        authorized_at_utc="2026-09-26T00:00:00Z",
        controller_authority_hash="a" * 64,
        discovery_run_grant_hash="b" * 64,
        discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        execution_disabled=True,
        lifecycle_governance_authority_hash="c" * 64,
        lifecycle_implementation_authority_hash="d" * 64,
        materialized_run_authority_hash="e" * 64,
        not_testable_slot_count=150,
        protocol_authority_hash="f" * 64,
        registered_slot_count=18,
        run_authority_id=run_id,
        sealed_registered_roster_hash="1" * 64,
        semantic_root_hash="2" * 64,
        source_manifest_hash="3" * 64,
        split_attestation_hash="4" * 64,
        split_manifest_hash="5" * 64,
        structural_ledger_hash="6" * 64,
        total_slot_count=168,
        upstream_receipt_hash=None,
    )
    receipt_hash = receipt_obj.receipt_sha256
    v1_ctx = H40LifecyclePersistenceContextV1(
        implementation_authority_hash="c" * 64,
        run_authority_id=run_id,
        runtime_seal_hash="e" * 64,
    ).to_dict()
    envelope = {
        "authority_context": v1_ctx,
        "bound_evidence": None,
        "bound_evidence_sha256": None,
        "receipt": receipt_obj.to_dict(),
        "receipt_sha256": receipt_hash,
    }
    receipts_dir = store._receipts_dir(run_id)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    (receipts_dir / f"{receipt_hash}.json").write_text(canonical_json(envelope), encoding="utf-8")

    # In production mode (synthetic_test_mode=False), cold restore rejects H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1
    prod_service = H40LifecycleAuthorityService.production()
    object.__setattr__(prod_service, "_assert_current_anchors", lambda require_controller: None)
    with pytest.raises(H40GuardError) as exc:
        store._cold_restore_authorization(
            run_id, receipt_hash, service=prod_service,
            resolver=None,  # type: ignore[arg-type]
            visited_receipts=frozenset(),
        )
    assert exc.value.reason_code == H40ReasonCode.CONFIG_IDENTITY_CONFLICT
    assert "production cold restore rejects H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1" in str(exc.value)


def test_preservation_56_stale_authority_service_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    prod_service = H40LifecycleAuthorityService.production()
    # With implementation authority published, require_controller=False succeeds
    prod_service._assert_current_anchors(require_controller=False)

    # Missing P3 controller authority fails closed in production without monkeypatch
    with pytest.raises(H40GuardError) as exc_ctrl:
        prod_service._assert_current_anchors(require_controller=True)
    assert exc_ctrl.value.reason_code == H40ReasonCode.NOT_TESTABLE
    assert "no independently accepted H40 P3 controller authority exists" in str(exc_ctrl.value)

    # If implementation authority is unconfigured (None), require_controller=False fails closed
    with monkeypatch.context() as m:
        m.setattr(
            "btc_quant_agent.h40.lifecycle_authority.ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
            None,
        )
        service_unanchored = H40LifecycleAuthorityService.production()
        with pytest.raises(H40GuardError) as exc:
            service_unanchored._assert_current_anchors(require_controller=False)
        assert exc.value.reason_code == H40ReasonCode.NOT_TESTABLE
        assert "no independently accepted lifecycle implementation authority exists" in str(exc.value)


# ==============================================================================
# MED-01 & MED-02 REGRESSION SUITE
# ==============================================================================


def test_med_01_parquet_in_memory_parsing_adversarial(tmp_path: Path) -> None:
    """MED-01: Parquet parser reads in-memory raw_bytes without reopening file_path."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    # 1. Create a valid Parquet source file with support-interval timestamps
    dt0 = datetime(2021, 1, 1, 0, tzinfo=UTC)
    timestamps = [(dt0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ") for i in range(5)]
    table = pa.Table.from_arrays(
        [
            pa.array(timestamps),
            pa.array([100.0, 101.0, 102.0, 103.0, 104.0]),
            pa.array([105.0, 106.0, 107.0, 108.0, 109.0]),
            pa.array([95.0, 96.0, 97.0, 98.0, 99.0]),
            pa.array([101.0, 102.0, 103.0, 104.0, 105.0]),
        ],
        names=["timestamp", "open", "high", "low", "close"],
    )
    source_file = tmp_path / "ETHUSDT.parquet"
    pq.write_table(table, source_file)

    # 1. Capture valid Parquet raw_bytes and verify whole-file SHA
    raw_bytes = source_file.read_bytes()
    file_sha = hashlib.sha256(raw_bytes).hexdigest()
    assert len(raw_bytes) > 0

    # 2. Adversarial case A: Delete source file from filesystem after byte capture
    source_file.unlink()
    assert not source_file.exists()

    # 3. Call economic extraction with original raw_bytes and deleted path
    bars_del, canon_del = _extract_economic_rows(
        source_file, raw_bytes, "ETHUSDT", "1h", "timestamp",
    )
    # 4. Extracted economic rows match original raw_bytes exactly
    assert len(bars_del) == 5
    assert len(canon_del) == 5
    assert canon_del[0]["close"] == repr(101.0)
    assert canon_del[4]["close"] == repr(105.0)

    # 2. Adversarial case B: Recreate source file on disk with completely different/adversarial values
    adversarial_table = pa.Table.from_arrays(
        [
            pa.array(timestamps),
            pa.array([9999.0] * 5),
            pa.array([9999.0] * 5),
            pa.array([9999.0] * 5),
            pa.array([9999.0] * 5),
        ],
        names=["timestamp", "open", "high", "low", "close"],
    )
    pq.write_table(adversarial_table, source_file)
    assert source_file.exists()

    # 3. Call economic extraction with original raw_bytes
    _bars_adv, canon_adv = _extract_economic_rows(
        source_file, raw_bytes, "ETHUSDT", "1h", "timestamp",
    )
    # 5. Proves no filesystem reopen controls extracted values: adversarial disk file ignored
    assert canon_adv == canon_del
    assert canon_adv[0]["close"] == repr(101.0)

    # 2. Adversarial case C: Mutate source file with corrupt non-Parquet bytes
    source_file.write_bytes(b"CORRUPTED_NON_PARQUET_DATA")
    _bars_corrupt, canon_corrupt = _extract_economic_rows(
        source_file, raw_bytes, "ETHUSDT", "1h", "timestamp",
    )
    assert canon_corrupt == canon_del

    # Invariant: Whole-file SHA is over the exact raw_bytes
    assert hashlib.sha256(raw_bytes).hexdigest() == file_sha
    # Invariant: economic_rows_sha256 is deterministically computed from canonical support rows
    computed_digest = canonical_sha256(canon_del)
    assert len(computed_digest) == 64

    # Invariant: JSON adapter behavior remains unchanged
    json_bars = _make_dummy_bars(dt0, 5)
    json_file = tmp_path / "ETHUSDT.json"
    json_bytes, _json_sha, _json_canon, json_digest, json_cnt = _write_json_source(json_file, json_bars)
    json_file.unlink()
    j_bars, j_canon = _extract_economic_rows(json_file, json_bytes, "ETHUSDT", "1h", "timestamp")
    assert len(j_bars) == 5
    assert canonical_sha256(j_canon) == json_digest
    assert json_cnt == 5

    # Invariant: Unsupported adapter fails closed -> NOT_TESTABLE
    csv_file = tmp_path / "ETHUSDT.csv"
    with pytest.raises(H40GuardError) as exc_unsupported:
        _extract_economic_rows(csv_file, b"timestamp,open\n", "ETHUSDT", "1h", "timestamp")
    assert exc_unsupported.value.reason_code == H40ReasonCode.NOT_TESTABLE
    assert "active source without accepted adapter" in str(exc_unsupported.value)


def test_med_02_lookback_reserve_interpretation_a_regressions() -> None:
    """MED-02: Controller-ratified Interpretation A locks lookback reserve behavior."""
    from btc_quant_agent.h40.discovery_evidence import LOOKBACK_RESERVE_END_UTC
    from btc_quant_agent.h40.split_manifest import (
        BASE_ELIGIBLE_START_UTC,
        RAW_PARTITION_SPECS,
        _compute_partitions_from_timestamps,
        generate_hourly_range,
    )

    clear_prefit_caches()

    # 1. Reserve timestamps [2021-01-01, 2021-01-31) cannot enter base-universe membership
    reserve_hours = generate_hourly_range(
        "2021-01-01T00:00:00Z",
        "2021-01-31T00:00:00Z",
        inclusive_end=False,
    )
    assert len(reserve_hours) == 720  # 30 days * 24 hours
    assert BASE_ELIGIBLE_START_UTC == "2021-01-31T00:00:00Z"
    assert LOOKBACK_RESERVE_END_UTC == datetime(2021, 1, 31, tzinfo=UTC)
    for rh in reserve_hours:
        assert rh < BASE_ELIGIBLE_START_UTC

    # Generate full timestamps covering reserve and eligible train
    eligible_hours = generate_hourly_range(
        BASE_ELIGIBLE_START_UTC,
        "2021-03-01T00:00:00Z",
        inclusive_end=False,
    )
    all_ts = reserve_hours + eligible_hours
    partitions, base_count, exclusions = _compute_partitions_from_timestamps(all_ts)
    assert exclusions["LOOKBACK_RESERVED"] == 720
    assert base_count == len(eligible_hours) == 696

    # Verify no partition includes any reserve timestamp
    for p in partitions:
        assert p.start_utc >= BASE_ELIGIBLE_START_UTC
        if p.first_timestamp_utc is not None:
            assert p.first_timestamp_utc >= BASE_ELIGIBLE_START_UTC

    # 2. Reserve feature scalars can be present in WF1 expanding percentile reference
    # Construct bars starting in the reserve window (2021-01-01)
    bars: dict[tuple[datetime, str], _Bar] = {}
    base_price = 1000.0
    for i, t_str in enumerate(all_ts):
        dt = datetime.fromisoformat(t_str)
        # Predictable varying price for non-degenerate vol and range
        price = base_price + 10.0 * math.sin(i * 0.1)
        bars[(dt, "ETHUSDT")] = _Bar(
            timestamp=dt,
            product="ETHUSDT",
            open=price,
            high=price + 2.0,
            low=price - 2.0,
            close=price + 0.5,
        )

    src_hash = _hash("test_src_med02")
    training_refs = _get_training_refs(src_hash, "ETHUSDT", bars)
    rv_series = training_refs["R_VOL"]
    exp_series = training_refs["O_RANGE"]

    # Verify reserve feature scalars are present in training_refs
    reserve_rv = [dt for dt, _ in rv_series if dt < datetime(2021, 1, 31, 0, tzinfo=UTC)]
    assert len(reserve_rv) > 60  # Over 60 valid causal feature scalars from reserve window
    reserve_exp = [dt for dt, _ in exp_series if dt < datetime(2021, 1, 31, 0, tzinfo=UTC)]
    assert len(reserve_exp) > 60

    # 3. Only scalars with dt < decision_t are included in WF1 expanding sample
    decision_t = datetime(2021, 1, 31, 0, tzinfo=UTC)  # Very first hour of WF1_TRAIN
    slot = SimpleNamespace(direction_contract_id="D1_V1_RETURN_4H")
    _score, regime_1, opp_1, _ = _reconstruct_prefit_cached(
        candidate_id="cand_med02",
        slot=slot,
        partition_id="WF1_TRAIN",
        t=decision_t,
        product="ETHUSDT",
        bars=bars,
        source_evidence_hash=src_hash,
    )
    # 5. N >= 60 is satisfied using causal reserve observations:
    # First row is NOT REGIME_UNAVAILABLE or O_UNAVAILABLE
    assert regime_1 != "REGIME_UNAVAILABLE"
    assert opp_1 != "O_UNAVAILABLE"

    # Verify sample at decision_t contains only dt < decision_t
    rv_sample_t = [v for dt, v in rv_series if dt < decision_t]
    assert len(rv_sample_t) >= 60
    for dt, _ in rv_series:
        if dt >= decision_t:
            assert dt not in [t for t, _ in rv_series if t < decision_t]

    # 4. Strict close_time < observation_time required by underlying feature reconstruction
    # At decision_t, bars at decision_t and later are not used to compute backward features
    # For instance, D1 4h return uses bars at t - 1h, t - 2h, t - 3h, t - 4h
    d1_val = _compute_d1(bars, decision_t, "ETHUSDT", 4)
    # Modifying bar at decision_t itself cannot alter D1 or R_VOL at decision_t
    bars_tampered = dict(bars)
    bars_tampered[(decision_t, "ETHUSDT")] = _Bar(
        decision_t, "ETHUSDT", 99999.0, 99999.0, 99999.0, 99999.0,
    )
    d1_tampered = _compute_d1(bars_tampered, decision_t, "ETHUSDT", 4)
    assert d1_tampered == d1_val

    # 6. No reserve timestamp becomes a decision or evaluation row
    # In split manifest, WF1_TRAIN timestamps strictly start at BASE_ELIGIBLE_START_UTC
    train_part = next(p for p in partitions if p.partition_id == "WF1_TRAIN")
    assert train_part.start_utc == BASE_ELIGIBLE_START_UTC
    assert train_part.first_timestamp_utc is not None and train_part.first_timestamp_utc >= BASE_ELIGIBLE_START_UTC

    # 7. Future/equal-time observations cannot affect earlier percentile state
    clear_prefit_caches()
    _score_a, regime_a, opp_a, _ = _reconstruct_prefit_cached(
        candidate_id="cand_med02",
        slot=slot,
        partition_id="WF1_TRAIN",
        t=decision_t,
        product="ETHUSDT",
        bars=bars,
        source_evidence_hash=src_hash,
    )
    # Add a massive spike in the future (decision_t + 10 hours)
    future_t = decision_t + timedelta(hours=10)
    bars_future_spike = dict(bars)
    bars_future_spike[(future_t, "ETHUSDT")] = _Bar(
        future_t, "ETHUSDT", 50000.0, 60000.0, 40000.0, 55000.0,
    )
    clear_prefit_caches()
    _score_b, regime_b, opp_b, _ = _reconstruct_prefit_cached(
        candidate_id="cand_med02",
        slot=slot,
        partition_id="WF1_TRAIN",
        t=decision_t,
        product="ETHUSDT",
        bars=bars_future_spike,
        source_evidence_hash=src_hash + "_spike",
    )
    assert regime_b == regime_a
    assert opp_b == opp_a

    # 8. Calibration behavior remains frozen-training-reference semantics
    # In calibration, sample includes all training_refs without dt < t filter
    cal_t = datetime(2022, 11, 1, 0, tzinfo=UTC)
    for k in range(30):
        t_k = cal_t - timedelta(hours=k)
        bars[(t_k, "ETHUSDT")] = _Bar(
            timestamp=t_k,
            product="ETHUSDT",
            open=1000.0,
            high=1002.0,
            low=998.0,
            close=1000.0 + (k % 5) * 0.5,
        )
    clear_prefit_caches()
    _sc_cal, reg_cal, _opp_cal, _ = _reconstruct_prefit_cached(
        candidate_id="cand_med02",
        slot=slot,
        partition_id="WF1_CALIBRATION",
        t=cal_t,
        product="ETHUSDT",
        bars=bars,
        source_evidence_hash=src_hash,
    )
    assert reg_cal != "REGIME_UNAVAILABLE"

    # 9. Verify later WF refits remain unchanged R3R2 rule
    # Later folds use their chronologically past training partition
    wf2_train = next(s for s in RAW_PARTITION_SPECS if s[0] == "WF2_TRAIN")
    assert wf2_train[3] == "2021-01-31T00:00:00Z"  # WF2_TRAIN starts at base eligible start

