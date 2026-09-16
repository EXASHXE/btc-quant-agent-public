"""Adversarial tests for H40-P1 Data, Split, and Protocol-Identity Scaffold.

Verifies strict pre-outcome immutability, canonical hashing, source access guards,
half-open split boundaries, 168-slot ledger budget cap, and fail-closed protections.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from btc_quant_agent.h40 import (
    ALLOWED_DEPTH_TWO_PAIRS,
    BASE_ELIGIBLE_COUNT,
    BASE_ELIGIBLE_END_UTC,
    BASE_ELIGIBLE_START_UTC,
    MAX_CONFIGURATION_SLOTS,
    H40CanonicalSourceSpec,
    H40ConfigurationLedger,
    H40ConfigurationSlot,
    H40ConfirmationGuard,
    H40ExecutionGuard,
    H40Family,
    H40GuardError,
    H40LifecycleState,
    H40LifecycleStateMachine,
    H40Partition,
    H40ProtectedSurfaceGuard,
    H40ProtocolIdentity,
    H40ReasonCode,
    H40SourceManifest,
    H40SourceRecord,
    H40SourceStatus,
    H40SourceValidationReceipt,
    H40SplitAttestation,
    H40SplitManifest,
    assert_canonical_source_record,
    get_canonical_source_spec,
    materialize_verified_manifest,
    validate_source_artifact,
)
from btc_quant_agent.h40.split_manifest import generate_hourly_range, iso_to_ms
from btc_quant_agent.research_contract.canonical import canonical_json, canonical_sha256

# ==============================================================================
# 1. Protocol Identity Tests
# ==============================================================================

def test_protocol_identity_determinism() -> None:
    """Identical preimages produce identical canonical JSON and SHA-256 hashes."""
    proto1 = H40ProtocolIdentity.default()
    proto2 = H40ProtocolIdentity.default()
    assert proto1.protocol_hash == proto2.protocol_hash
    assert proto1.canonical_json() == proto2.canonical_json()


def test_protocol_identity_immutability_against_caller_mutation() -> None:
    """Mutating caller-owned mutable collections passed to constructor does not mutate identity."""
    mutable_products = ["BTCUSDT", "ETHUSDT"]
    mutable_interval = {"start_utc": "2025-02-01T00:00:00Z", "end_utc": "2026-02-01T00:00:00Z"}
    proto = H40ProtocolIdentity(
        products=mutable_products,
        confirmation_interval=mutable_interval,
    )
    original_hash = proto.protocol_hash

    # Caller mutates external collections
    mutable_products.append("SOLUSDT")
    mutable_interval["start_utc"] = "2024-01-01T00:00:00Z"

    assert proto.protocol_hash == original_hash
    assert "SOLUSDT" not in proto.products
    assert proto.confirmation_interval["start_utc"] == "2025-02-01T00:00:00Z"


def test_protocol_identity_serialization_round_trip() -> None:
    """Serialization to dict and deserialization preserves identical canonical hash."""
    proto = H40ProtocolIdentity.default()
    serialized = proto.to_dict()
    deserialized = H40ProtocolIdentity.from_dict(serialized)
    assert deserialized.protocol_hash == proto.protocol_hash
    assert deserialized.to_dict() == serialized


def test_protocol_identity_changes_on_parameter_divergence() -> None:
    """Any alteration to commit SHAs, search budget, or horizons alters the protocol hash."""
    default_proto = H40ProtocolIdentity.default()
    base_hash = default_proto.protocol_hash

    # Changed kernel SHA
    p_kernel = H40ProtocolIdentity(frozen_kernel_sha="0000000000000000000000000000000000000000")
    assert p_kernel.protocol_hash != base_hash

    # Changed amendment R2 commit
    p_r2 = H40ProtocolIdentity(amendment_r2_commit="1111111111111111111111111111111111111111")
    assert p_r2.protocol_hash != base_hash

    # Changed search budget
    p_budget = H40ProtocolIdentity(search_budget=169)
    assert p_budget.protocol_hash != base_hash

    # Changed primary horizons
    p_horizons = H40ProtocolIdentity(primary_horizons=("4h", "8h"))
    assert p_horizons.protocol_hash != base_hash


# ==============================================================================
# 2. Unprotected Source-Authority Manifest & Receipt Tests (Repair B & C)
# ==============================================================================

def test_source_manifest_default_inventory() -> None:
    """Default manifest inventories unverified reference, not_testable, diagnostic, and forbidden sources."""
    proto = H40ProtocolIdentity.default()
    manifest = H40SourceManifest.build_default(proto.protocol_hash)

    # In preregistered reference, candidate sources are UNVERIFIED pending local validation receipt
    btc_kline = manifest.get_source("BTCUSDT_USD_M_1H")
    assert btc_kline.status == H40SourceStatus.UNVERIFIED
    eth_kline = manifest.get_source("ETHUSDT_USD_M_1H")
    assert eth_kline.status == H40SourceStatus.UNVERIFIED
    assert eth_kline.row_count == 44568

    # Check unverified / NOT_TESTABLE
    eth_deriv = manifest.get_source("ETHUSDT_DERIVATIVES_FLOW")
    assert eth_deriv.status == H40SourceStatus.NOT_TESTABLE
    assert eth_deriv.reason_code == H40ReasonCode.SOURCE_UNVERIFIED

    # Check diagnostic sources
    fwd_store = manifest.get_source("LOCAL_FORWARD_STORE")
    assert fwd_store.status == H40SourceStatus.DIAGNOSTIC_ONLY

    # Check forbidden sources
    h39 = manifest.get_source("H39_PROTECTED")
    assert h39.status == H40SourceStatus.FORBIDDEN
    assert h39.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    final_holdout = manifest.get_source("FINAL_HOLDOUT")
    assert final_holdout.status == H40SourceStatus.FORBIDDEN
    assert final_holdout.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_source_manifest_denies_forbidden_and_unverified_discovery() -> None:
    """Accessing forbidden or NOT_TESTABLE sources for discovery raises fail-closed H40GuardError."""
    proto = H40ProtocolIdentity.default()
    manifest = H40SourceManifest.build_default(proto.protocol_hash)

    with pytest.raises(H40GuardError) as exc_info:
        manifest.validate_source_admissibility("H39_PROTECTED", purpose="discovery")
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    with pytest.raises(H40GuardError) as exc_info:
        manifest.validate_source_admissibility("FINAL_HOLDOUT", purpose="discovery")
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    with pytest.raises(H40GuardError) as exc_info:
        manifest.validate_source_admissibility("ETHUSDT_DERIVATIVES_FLOW", purpose="discovery")
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED

    with pytest.raises(H40GuardError) as exc_info:
        manifest.validate_source_admissibility("LOCAL_FORWARD_STORE", purpose="discovery")
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_verified_source_record_requires_valid_receipt() -> None:
    """A source record cannot claim VERIFIED status without an explicit valid receipt."""
    with pytest.raises(H40GuardError) as exc_info:
        H40SourceRecord(
            source_id="UNBACKED_SOURCE",
            status=H40SourceStatus.VERIFIED,
            locator="data/research/some_file.parquet",
            receipt=None,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_source_validation_receipt_detects_hash_tampering(tmp_path: Path) -> None:
    """Tampering with source file content causes validation receipt to record SOURCE_HASH_MISMATCH."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    test_file = tmp_path / "test_kline.parquet"
    timestamps = [1609459200000 + i * 3600000 for i in range(10)]
    tab = pa.Table.from_arrays([pa.array(timestamps)], names=["open_time_ms"])
    pq.write_table(tab, test_file)

    orig_hash = hashlib.sha256(test_file.read_bytes()).hexdigest()
    rec = H40SourceRecord(
        source_id="CUSTOM_SOURCE",
        status=H40SourceStatus.UNVERIFIED,
        locator="test_kline.parquet",
        product="BTCUSDT",
        cadence="1h",
        file_sha256=orig_hash,
    )

    # Initial validation succeeds
    receipt = validate_source_artifact(tmp_path, rec, expected_product="BTCUSDT", expected_cadence="1h")
    assert isinstance(receipt, H40SourceValidationReceipt)
    assert receipt.status == H40SourceStatus.VERIFIED
    assert receipt.timestamp_count == 10

    # Tamper with file
    test_file.write_bytes(b"tampered content not matching original hash")
    receipt_tampered = validate_source_artifact(tmp_path, rec, expected_product="BTCUSDT", expected_cadence="1h")
    assert receipt_tampered.status == H40SourceStatus.NOT_TESTABLE
    assert receipt_tampered.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


def test_source_validation_receipt_detects_missing_file(tmp_path: Path) -> None:
    """Missing source file records SOURCE_MISSING in validation receipt."""
    rec = H40SourceRecord(
        source_id="MISSING_SOURCE",
        status=H40SourceStatus.UNVERIFIED,
        locator="non_existent.parquet",
        file_sha256="abc",
    )
    receipt = validate_source_artifact(tmp_path, rec)
    assert receipt.status == H40SourceStatus.NOT_TESTABLE
    assert receipt.reason_code == H40ReasonCode.SOURCE_MISSING


def test_source_validation_receipt_detects_wrong_product(tmp_path: Path) -> None:
    """Validating a source with a mismatched product fails closed."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    test_file = tmp_path / "eth_kline.parquet"
    timestamps = [1609459200000 + i * 3600000 for i in range(5)]
    products = ["ETHUSDT"] * 5
    tab = pa.Table.from_arrays([pa.array(timestamps), pa.array(products)], names=["open_time_ms", "product"])
    pq.write_table(tab, test_file)

    rec = H40SourceRecord(
        source_id="ETH_AS_BTC",
        status=H40SourceStatus.UNVERIFIED,
        locator="eth_kline.parquet",
        product="ETHUSDT",
    )
    # Expected product is BTCUSDT, but file/record is ETHUSDT
    receipt = validate_source_artifact(tmp_path, rec, expected_product="BTCUSDT")
    assert receipt.status == H40SourceStatus.NOT_TESTABLE
    assert receipt.reason_code == H40ReasonCode.PRODUCT_MISMATCH


def test_source_validation_receipt_detects_wrong_cadence(tmp_path: Path) -> None:
    """Validating a source with 15m cadence when 1h is expected fails closed."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    test_file = tmp_path / "kline_15m.parquet"
    # 15m intervals (900_000 ms)
    timestamps = [1609459200000 + i * 900000 for i in range(10)]
    tab = pa.Table.from_arrays([pa.array(timestamps)], names=["open_time_ms"])
    pq.write_table(tab, test_file)

    rec = H40SourceRecord(
        source_id="SOURCE_15M",
        status=H40SourceStatus.UNVERIFIED,
        locator="kline_15m.parquet",
        cadence="15m",
    )
    receipt = validate_source_artifact(tmp_path, rec, expected_cadence="1h")
    assert receipt.status == H40SourceStatus.NOT_TESTABLE
    assert receipt.reason_code == H40ReasonCode.INTERVAL_MISMATCH


def test_source_validation_receipt_detects_duplicate_timestamps(tmp_path: Path) -> None:
    """Duplicate timestamps in an artifact are detected and fail closed."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    test_file = tmp_path / "dup_kline.parquet"
    # Duplicate timestamp at index 1 and 2
    timestamps = [1609459200000, 1609462800000, 1609462800000, 1609466400000]
    tab = pa.Table.from_arrays([pa.array(timestamps)], names=["open_time_ms"])
    pq.write_table(tab, test_file)

    rec = H40SourceRecord(
        source_id="DUP_SOURCE",
        status=H40SourceStatus.UNVERIFIED,
        locator="dup_kline.parquet",
    )
    receipt = validate_source_artifact(tmp_path, rec, expected_cadence="1h")
    assert receipt.status == H40SourceStatus.NOT_TESTABLE
    assert receipt.reason_code == H40ReasonCode.DUPLICATE_TIMESTAMP
    assert receipt.duplicate_count == 1


def test_source_validation_receipt_persists_gaps(tmp_path: Path) -> None:
    """A missing hour between timestamps is detected and recorded as an explicit gap."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    test_file = tmp_path / "gap_kline.parquet"
    # Skip hour 1609462800000 (missing 1 hour)
    timestamps = [1609459200000, 1609466400000]
    tab = pa.Table.from_arrays([pa.array(timestamps)], names=["open_time_ms"])
    pq.write_table(tab, test_file)

    rec = H40SourceRecord(
        source_id="GAP_SOURCE",
        status=H40SourceStatus.UNVERIFIED,
        locator="gap_kline.parquet",
    )
    receipt = validate_source_artifact(tmp_path, rec, expected_cadence="1h")
    assert receipt.gap_count == 1
    assert receipt.gaps[0]["missing_hours"] == 1


def test_materialize_verified_manifest_on_real_local_artifacts() -> None:
    """Materializes verified manifest from actual repository artifacts without reading OHLC."""
    proto = H40ProtocolIdentity.default()
    manifest = materialize_verified_manifest(Path("."), proto.protocol_hash)

    eth_path = Path("data/research/cross_asset_1h/ETHUSDT.parquet")
    eth = manifest.get_source("ETHUSDT_USD_M_1H")
    if eth_path.exists():
        assert eth.status == H40SourceStatus.VERIFIED
        assert eth.row_count == 44568
        assert eth.receipt is not None
        assert eth.receipt.status == H40SourceStatus.VERIFIED
    else:
        assert eth.status == H40SourceStatus.NOT_TESTABLE
        assert eth.receipt is not None
        assert eth.receipt.status == H40SourceStatus.NOT_TESTABLE
        assert eth.receipt.reason_code == H40ReasonCode.SOURCE_MISSING

    deriv_path = Path("data/research/v0.3.19_official_derivatives/hourly_inputs.parquet")
    deriv = manifest.get_source("BTCUSDT_OFFICIAL_DERIVATIVES")
    if deriv_path.exists():
        assert deriv.status == H40SourceStatus.VERIFIED
        assert deriv.row_count == 44568
        assert deriv.receipt is not None
        assert deriv.receipt.status == H40SourceStatus.VERIFIED
    else:
        assert deriv.status == H40SourceStatus.NOT_TESTABLE
        assert deriv.receipt is not None
        assert deriv.receipt.status == H40SourceStatus.NOT_TESTABLE
        assert deriv.receipt.reason_code == H40ReasonCode.SOURCE_MISSING


# ==============================================================================
# 3. Split Manifest & Materialized Authority Tests (Repair C & P1RR Attestation)
# ==============================================================================

def _create_synthetic_parquet(
    file_path: Path,
    product: str,
    timestamps_iso: list[str],
) -> tuple[str, str, int]:
    """Writes a synthetic parquet table and returns (file_sha256, membership_sha256, count)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    file_path.parent.mkdir(parents=True, exist_ok=True)
    ms_list = [iso_to_ms(t) for t in timestamps_iso]
    tab = pa.Table.from_arrays(
        [pa.array(ms_list), pa.array([product] * len(ms_list))],
        names=["open_time_ms", "product"],
    )
    pq.write_table(tab, file_path)
    file_sha = hashlib.sha256(file_path.read_bytes()).hexdigest()
    membership_sha = hashlib.sha256(",".join(timestamps_iso).encode("utf-8")).hexdigest()
    return file_sha, membership_sha, len(timestamps_iso)


def _setup_synthetic_source_manifest(
    tmp_path: Path,
    proto_hash: str,
    btc_timestamps: list[str],
    eth_timestamps: list[str],
    btc_locator: str = "btc_1h.parquet",
    eth_locator: str = "eth_1h.parquet",
) -> tuple[H40SourceManifest, H40SourceRecord, H40SourceRecord]:
    """Sets up synthetic parquet artifacts and verified source records."""
    btc_file = tmp_path / btc_locator
    eth_file = tmp_path / eth_locator

    btc_sha, _btc_mem, btc_cnt = _create_synthetic_parquet(btc_file, "BTCUSDT", btc_timestamps)
    eth_sha, _eth_mem, eth_cnt = _create_synthetic_parquet(eth_file, "ETHUSDT", eth_timestamps)

    btc_rec_unverified = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator=btc_locator,
        product="BTCUSDT",
        cadence="1h",
    )
    eth_rec_unverified = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator=eth_locator,
        product="ETHUSDT",
        cadence="1h",
    )

    btc_receipt = validate_source_artifact(tmp_path, btc_rec_unverified, expected_product="BTCUSDT", expected_cadence="1h")
    eth_receipt = validate_source_artifact(tmp_path, eth_rec_unverified, expected_product="ETHUSDT", expected_cadence="1h")

    assert btc_receipt.status == H40SourceStatus.VERIFIED
    assert eth_receipt.status == H40SourceStatus.VERIFIED

    btc_rec = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator=btc_locator,
        product="BTCUSDT",
        cadence="1h",
        row_count=btc_cnt,
        file_sha256=btc_sha,
        receipt=btc_receipt,
    )
    eth_rec = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator=eth_locator,
        product="ETHUSDT",
        cadence="1h",
        row_count=eth_cnt,
        file_sha256=eth_sha,
        receipt=eth_receipt,
    )

    src_manifest = H40SourceManifest(
        protocol_identity_hash=proto_hash,
        sources=(btc_rec, eth_rec),
    )
    return src_manifest, btc_rec, eth_rec


def test_split_manifest_preregistered_schedule_is_not_authoritative(tmp_path: Path) -> None:
    """Preregistered schedule is reference only (is_authoritative=False) and fails assert_authoritative."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    split_manifest = H40SplitManifest.build_preregistered_schedule(proto.protocol_hash, src_manifest.manifest_hash)

    assert not split_manifest.is_authoritative
    assert split_manifest.base_eligible_count == BASE_ELIGIBLE_COUNT
    assert split_manifest.base_eligible_start_utc == BASE_ELIGIBLE_START_UTC
    assert split_manifest.base_eligible_end_utc == BASE_ELIGIBLE_END_UTC

    # Walk-Forward 1
    wf1_train = split_manifest.get_partition("WF1_TRAIN")
    assert wf1_train.count == 15312
    wf1_p1 = split_manifest.get_partition("WF1_PURGE_1")
    assert wf1_p1.count == 24
    wf1_calib = split_manifest.get_partition("WF1_CALIBRATION")
    assert wf1_calib.count == 2184
    wf1_p2 = split_manifest.get_partition("WF1_PURGE_2")
    assert wf1_p2.count == 24
    wf1_val = split_manifest.get_partition("WF1_VALIDATION")
    assert wf1_val.count == 4320

    # Confirmation Split
    conf_train = split_manifest.get_partition("CONFIRMATION_TRAIN")
    assert conf_train.count == 35064
    conf_purge = split_manifest.get_partition("CONFIRMATION_PURGE")
    assert conf_purge.count == 24
    conf_holdout = split_manifest.get_partition("CONFIRMATION_HOLDOUT")
    assert conf_holdout.count == 8737

    # Exclusions
    assert split_manifest.exclusion_counts[H40ReasonCode.LOOKBACK_RESERVED.value] == 720
    assert split_manifest.exclusion_counts[H40ReasonCode.HORIZON_TRUNCATED.value] == 23
    assert split_manifest.exclusion_counts[H40ReasonCode.PURGE_BOUNDARY.value] == 216
    assert split_manifest.exclusion_counts[H40ReasonCode.SOURCE_GAP.value] == 0

    with pytest.raises(H40GuardError) as exc_info:
        split_manifest.assert_authoritative(source_manifest=src_manifest, repo_root=tmp_path)
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


# --- Mandatory Adversarial & Invariant Tests ---

def test_build_materialized_from_caller_arrays_is_not_authoritative(tmp_path: Path) -> None:
    """1. Caller array cannot produce authoritative split: build_materialized returns is_authoritative=False."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)

    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    split = H40SplitManifest.build_materialized(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        btc_timestamps=full_ts,
        eth_timestamps=full_ts,
    )

    assert not split.is_authoritative
    assert split.attestation is None
    assert split.base_eligible_count == BASE_ELIGIBLE_COUNT
    assert split.get_partition("WF1_TRAIN").count == 15312

    with pytest.raises(H40GuardError) as exc_info:
        split.assert_authoritative(source_manifest=src_manifest, repo_root=tmp_path)
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_authoritative_materialization_fails_omitted_btc_receipt(tmp_path: Path) -> None:
    """2. Authoritative materialization fails closed if source manifest lacks verified BTC receipt."""
    proto = H40ProtocolIdentity.default()
    btc_rec = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="btc.parquet",
        product="BTCUSDT",
        cadence="1h",
        receipt=None,
    )
    eth_rec = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="eth.parquet",
        product="ETHUSDT",
        cadence="1h",
        receipt=None,
    )
    src_manifest = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(btc_rec, eth_rec),
    )

    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.materialize_authoritative(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_authoritative_materialization_fails_omitted_eth_receipt(tmp_path: Path) -> None:
    """3. Authoritative materialization fails closed if source manifest lacks verified ETH receipt."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    _src_manifest, btc_rec, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    unverified_eth = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="eth_1h.parquet",
        product="ETHUSDT",
        cadence="1h",
        receipt=None,
    )
    bad_manifest = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(btc_rec, unverified_eth),
    )

    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.materialize_authoritative(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest=bad_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_authoritative_materialization_fails_forged_receipt_wrong_file_sha(tmp_path: Path) -> None:
    """4. Authoritative materialization fails closed if disk artifact file SHA-256 does not match receipt."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    _src_manifest, btc_rec, eth_rec = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    tampered_receipt = copy.deepcopy(btc_rec.receipt)
    assert tampered_receipt is not None
    object.__setattr__(tampered_receipt, "file_sha256", "0" * 64)

    tampered_btc = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator=btc_rec.locator,
        product=btc_rec.product,
        cadence=btc_rec.cadence,
        row_count=btc_rec.row_count,
        file_sha256="0" * 64,
        receipt=tampered_receipt,
    )
    tampered_manifest = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(tampered_btc, eth_rec),
    )

    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.materialize_synthetic_validator_split(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest=tampered_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


def test_authoritative_materialization_fails_forged_receipt_wrong_membership_hash(tmp_path: Path) -> None:
    """5. Authoritative materialization fails closed if disk artifact timestamp membership hash does not match receipt."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    _src_manifest, btc_rec, eth_rec = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    tampered_receipt = copy.deepcopy(btc_rec.receipt)
    assert tampered_receipt is not None
    object.__setattr__(tampered_receipt, "timestamp_membership_hash", "f" * 64)

    tampered_btc = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator=btc_rec.locator,
        product=btc_rec.product,
        cadence=btc_rec.cadence,
        row_count=btc_rec.row_count,
        file_sha256=btc_rec.file_sha256,
        receipt=tampered_receipt,
    )
    tampered_manifest = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(tampered_btc, eth_rec),
    )

    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.materialize_synthetic_validator_split(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest=tampered_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


def test_authoritative_materialization_fails_receipt_metadata_mismatch(tmp_path: Path) -> None:
    """6. Authoritative materialization fails closed on product or cadence mismatch in receipt."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    _src_manifest, btc_rec, eth_rec = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    tampered_receipt = copy.deepcopy(btc_rec.receipt)
    assert tampered_receipt is not None
    object.__setattr__(tampered_receipt, "product", "ETHUSDT")

    tampered_btc = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator=btc_rec.locator,
        product="ETHUSDT",
        cadence=btc_rec.cadence,
        row_count=btc_rec.row_count,
        file_sha256=btc_rec.file_sha256,
        receipt=tampered_receipt,
    )
    tampered_manifest = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(tampered_btc, eth_rec),
    )

    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.materialize_synthetic_validator_split(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest=tampered_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.PRODUCT_MISMATCH


def test_authoritative_split_rejects_substituted_source_manifest_hash(tmp_path: Path) -> None:
    """7. Synthetic validator split rejects assertion if source manifest hash does not match attestation."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest_1, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest_1,
        repo_root=tmp_path,
    )

    src_manifest_2 = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(),
    )

    with pytest.raises(H40GuardError) as exc_info:
        split.assert_synthetic_validator_split(
            source_manifest=src_manifest_2,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_direct_construction_with_authoritative_true_fails_verification(tmp_path: Path) -> None:
    """8. Direct constructor call with is_authoritative=True lacks valid attestation and fails assert_authoritative."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    forged_split = H40SplitManifest(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        base_eligible_start_utc=BASE_ELIGIBLE_START_UTC,
        base_eligible_end_utc=BASE_ELIGIBLE_END_UTC,
        base_eligible_count=BASE_ELIGIBLE_COUNT,
        partitions=(),
        exclusion_counts={},
        is_authoritative=True,
        attestation=None,
    )

    with pytest.raises(H40GuardError) as exc_info:
        forged_split.assert_authoritative(source_manifest=src_manifest, repo_root=tmp_path)
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_serialized_manifest_with_authoritative_true_fails_verification(tmp_path: Path) -> None:
    """9. Serialized/deserialized JSON with missing/invalid attestation fails assert_synthetic_validator_split."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )
    data = split.to_dict()
    data["attestation"] = None

    tampered_split = H40SplitManifest.from_dict(data)
    with pytest.raises(H40GuardError) as exc_info:
        tampered_split.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_mutating_source_timestamp_rejects_split_authority(tmp_path: Path) -> None:
    """10. Attestation tampering (modifying timestamp count or attestation hash) fails cold assertion."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )
    assert split.attestation is not None

    # Case A: Attestation self-hash tampered
    tampered_att_data = split.attestation.to_dict()
    tampered_att_data["attestation_hash"] = "9" * 64
    tampered_att = H40SplitAttestation.from_dict(tampered_att_data)
    tampered_split = H40SplitManifest(
        protocol_identity_hash=split.protocol_identity_hash,
        source_manifest_hash=split.source_manifest_hash,
        base_eligible_start_utc=split.base_eligible_start_utc,
        base_eligible_end_utc=split.base_eligible_end_utc,
        base_eligible_count=split.base_eligible_count,
        partitions=split.partitions,
        exclusion_counts=split.exclusion_counts,
        is_authoritative=False,
        attestation=tampered_att,
    )
    with pytest.raises(H40GuardError) as exc_info:
        tampered_split.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH

    # Case B: Tampering btc_timestamp_count in attestation
    tampered_att_data2 = split.attestation.to_dict()
    tampered_att2 = H40SplitAttestation.create(
        protocol_identity_hash=tampered_att_data2["protocol_identity_hash"],
        source_manifest_hash=tampered_att_data2["source_manifest_hash"],
        split_hash=tampered_att_data2["split_hash"],
        btc_source_id=tampered_att_data2["btc_source_id"],
        btc_locator=tampered_att_data2["btc_locator"],
        btc_file_sha256=tampered_att_data2["btc_file_sha256"],
        btc_membership_sha256=tampered_att_data2["btc_membership_sha256"],
        btc_timestamp_count=999,
        eth_source_id=tampered_att_data2["eth_source_id"],
        eth_locator=tampered_att_data2["eth_locator"],
        eth_file_sha256=tampered_att_data2["eth_file_sha256"],
        eth_membership_sha256=tampered_att_data2["eth_membership_sha256"],
        eth_timestamp_count=tampered_att_data2["eth_timestamp_count"],
        is_production_canonical=False,
    )
    tampered_split2 = H40SplitManifest(
        protocol_identity_hash=split.protocol_identity_hash,
        source_manifest_hash=split.source_manifest_hash,
        base_eligible_start_utc=split.base_eligible_start_utc,
        base_eligible_end_utc=split.base_eligible_end_utc,
        base_eligible_count=split.base_eligible_count,
        partitions=split.partitions,
        exclusion_counts=split.exclusion_counts,
        is_authoritative=False,
        attestation=tampered_att2,
    )
    with pytest.raises(H40GuardError) as exc_info2:
        tampered_split2.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info2.value.reason_code == H40ReasonCode.INTERVAL_MISMATCH


def test_source_gap_persists_in_membership_without_boundary_shifts(tmp_path: Path) -> None:
    """11. Real gap handling: a source with synthetic gaps correctly records SOURCE_GAP and preserves rigid boundaries."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    gapped_ts = [t for t in full_ts if not ("2021-03-01T10:00:00Z" <= t <= "2021-03-01T14:00:00Z")]

    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, gapped_ts, gapped_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    wf1 = split.get_partition("WF1_TRAIN")
    assert wf1.start_utc == "2021-01-31T00:00:00Z"
    assert wf1.end_utc == "2022-10-31T00:00:00Z"
    assert wf1.count == 15312 - 5
    assert split.exclusion_counts[H40ReasonCode.SOURCE_GAP.value] == 5

    split.assert_synthetic_validator_split(
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )


def test_missing_local_artifact_fails_closed_not_testable(tmp_path: Path) -> None:
    """12. Missing local artifact on disk during cold verification fails closed."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    (tmp_path / "btc_1h.parquet").unlink()

    with pytest.raises(H40GuardError) as exc_info:
        split.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_MISSING


def test_positive_synthetic_chain_succeeds_and_passes_verification(tmp_path: Path) -> None:
    """13. Positive end-to-end synthetic chain: valid artifacts -> source manifest -> materialize_synthetic_validator_split -> assert_synthetic_validator_split."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _btc_rec, _eth_rec = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    assert not split.is_authoritative
    assert split.attestation is not None
    assert split.attestation.attestation_hash == split.attestation.compute_attestation_hash()
    assert not split.attestation.is_production_canonical
    assert split.base_eligible_count == BASE_ELIGIBLE_COUNT
    assert split.get_partition("WF1_TRAIN").count == 15312
    assert split.get_partition("CONFIRMATION_HOLDOUT").count == 8737
    assert split.exclusion_counts[H40ReasonCode.LOOKBACK_RESERVED.value] == 720
    assert split.exclusion_counts[H40ReasonCode.HORIZON_TRUNCATED.value] == 23
    assert split.exclusion_counts[H40ReasonCode.PURGE_BOUNDARY.value] == 216
    assert split.exclusion_counts[H40ReasonCode.SOURCE_GAP.value] == 0

    split.assert_synthetic_validator_split(
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    # Must fail closed if presented to assert_authoritative
    with pytest.raises(H40GuardError) as exc_info:
        split.assert_authoritative(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_positive_split_round_trip_and_cold_verification(tmp_path: Path) -> None:
    """14. Positive split round-trip: serialization to JSON and back preserves attestation and passes assert_synthetic_validator_split with cold verification."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    json_str = split.canonical_json()
    roundtrip_split = H40SplitManifest.from_dict(json.loads(json_str))

    assert not roundtrip_split.is_authoritative
    assert roundtrip_split.attestation == split.attestation
    assert roundtrip_split.split_hash == split.split_hash
    assert roundtrip_split.canonical_json() == json_str

    roundtrip_split.assert_synthetic_validator_split(
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )


def test_assert_authoritative_without_cold_data_root_fails(tmp_path: Path) -> None:
    """Calling assertion methods without a cold data root is impossible or fails closed."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    # 1. Calling with repo_root=None explicitly fails closed with SOURCE_UNVERIFIED
    with pytest.raises(H40GuardError) as exc_info:
        split.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root=None,
        )  # type: ignore[arg-type]
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED

    # 2. Calling with empty string repo_root fails closed with SOURCE_UNVERIFIED
    with pytest.raises(H40GuardError) as exc_info_empty:
        split.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root="",
        )
    assert exc_info_empty.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED

    # 3. Calling without repo_root parameter is impossible at call time (TypeError)
    with pytest.raises(TypeError):
        split.assert_synthetic_validator_split(source_manifest=src_manifest)  # type: ignore[call-arg]


def test_offline_self_consistent_forged_chain_cannot_acquire_authority(tmp_path: Path) -> None:
    """A completely forged but self-consistent chain cannot acquire authority without real matching artifacts."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)

    fake_file_sha = "a" * 64
    fake_mem_sha = hashlib.sha256(",".join(full_ts).encode("utf-8")).hexdigest()

    btc_receipt = H40SourceValidationReceipt(
        source_id="BTCUSDT_USD_M_1H",
        locator="non_existent_btc.parquet",
        file_sha256=fake_file_sha,
        product="BTCUSDT",
        cadence="1h",
        timestamp_field="open_time_ms",
        timestamp_count=len(full_ts),
        first_timestamp_utc=full_ts[0],
        last_timestamp_utc=full_ts[-1],
        duplicate_count=0,
        gap_count=0,
        gaps=(),
        timestamp_membership_hash=fake_mem_sha,
        status=H40SourceStatus.VERIFIED,
    )
    eth_receipt = H40SourceValidationReceipt(
        source_id="ETHUSDT_USD_M_1H",
        locator="non_existent_eth.parquet",
        file_sha256=fake_file_sha,
        product="ETHUSDT",
        cadence="1h",
        timestamp_field="open_time_ms",
        timestamp_count=len(full_ts),
        first_timestamp_utc=full_ts[0],
        last_timestamp_utc=full_ts[-1],
        duplicate_count=0,
        gap_count=0,
        gaps=(),
        timestamp_membership_hash=fake_mem_sha,
        status=H40SourceStatus.VERIFIED,
    )

    btc_rec = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="non_existent_btc.parquet",
        product="BTCUSDT",
        cadence="1h",
        row_count=len(full_ts),
        file_sha256=fake_file_sha,
        receipt=btc_receipt,
    )
    eth_rec = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="non_existent_eth.parquet",
        product="ETHUSDT",
        cadence="1h",
        row_count=len(full_ts),
        file_sha256=fake_file_sha,
        receipt=eth_receipt,
    )

    forged_source_manifest = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(btc_rec, eth_rec),
    )

    split_ref = H40SplitManifest.build_preregistered_schedule(
        proto.protocol_hash,
        forged_source_manifest.manifest_hash,
    )
    candidate_split = H40SplitManifest(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=forged_source_manifest.manifest_hash,
        base_eligible_start_utc=split_ref.base_eligible_start_utc,
        base_eligible_end_utc=split_ref.base_eligible_end_utc,
        base_eligible_count=split_ref.base_eligible_count,
        partitions=split_ref.partitions,
        exclusion_counts=split_ref.exclusion_counts,
        is_authoritative=True,
        attestation=None,
    )
    forged_att = H40SplitAttestation.create(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=forged_source_manifest.manifest_hash,
        split_hash=candidate_split.split_hash,
        btc_source_id=btc_rec.source_id,
        btc_locator=btc_rec.locator,
        btc_file_sha256=fake_file_sha,
        btc_membership_sha256=fake_mem_sha,
        btc_timestamp_count=len(full_ts),
        eth_source_id=eth_rec.source_id,
        eth_locator=eth_rec.locator,
        eth_file_sha256=fake_file_sha,
        eth_membership_sha256=fake_mem_sha,
        eth_timestamp_count=len(full_ts),
    )
    forged_split = H40SplitManifest(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=forged_source_manifest.manifest_hash,
        base_eligible_start_utc=split_ref.base_eligible_start_utc,
        base_eligible_end_utc=split_ref.base_eligible_end_utc,
        base_eligible_count=split_ref.base_eligible_count,
        partitions=split_ref.partitions,
        exclusion_counts=split_ref.exclusion_counts,
        is_authoritative=True,
        attestation=forged_att,
    )

    with pytest.raises(H40GuardError) as exc_info:
        forged_split.assert_authoritative(source_manifest=forged_source_manifest, repo_root=tmp_path)
    assert exc_info.value.reason_code in {H40ReasonCode.SOURCE_MISSING, H40ReasonCode.NOT_TESTABLE, H40ReasonCode.SOURCE_UNVERIFIED}


def test_forged_receipts_plus_unrelated_artifact_bytes_fails(tmp_path: Path) -> None:
    """Forged receipts plus unrelated artifact bytes fail cold validation."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)

    _create_synthetic_parquet(tmp_path / "btc_1h.parquet", "BTCUSDT", full_ts[:100])
    _create_synthetic_parquet(tmp_path / "eth_1h.parquet", "ETHUSDT", full_ts[:100])

    fake_sha = "c" * 64
    fake_mem = "d" * 64
    btc_receipt = H40SourceValidationReceipt(
        source_id="BTCUSDT_USD_M_1H",
        locator="btc_1h.parquet",
        file_sha256=fake_sha,
        product="BTCUSDT",
        cadence="1h",
        timestamp_field="open_time_ms",
        timestamp_count=len(full_ts),
        first_timestamp_utc=full_ts[0],
        last_timestamp_utc=full_ts[-1],
        duplicate_count=0,
        gap_count=0,
        gaps=(),
        timestamp_membership_hash=fake_mem,
        status=H40SourceStatus.VERIFIED,
    )
    eth_receipt = H40SourceValidationReceipt(
        source_id="ETHUSDT_USD_M_1H",
        locator="eth_1h.parquet",
        file_sha256=fake_sha,
        product="ETHUSDT",
        cadence="1h",
        timestamp_field="open_time_ms",
        timestamp_count=len(full_ts),
        first_timestamp_utc=full_ts[0],
        last_timestamp_utc=full_ts[-1],
        duplicate_count=0,
        gap_count=0,
        gaps=(),
        timestamp_membership_hash=fake_mem,
        status=H40SourceStatus.VERIFIED,
    )
    btc_rec = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="btc_1h.parquet",
        product="BTCUSDT",
        cadence="1h",
        row_count=len(full_ts),
        file_sha256=fake_sha,
        receipt=btc_receipt,
    )
    eth_rec = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="eth_1h.parquet",
        product="ETHUSDT",
        cadence="1h",
        row_count=len(full_ts),
        file_sha256=fake_sha,
        receipt=eth_receipt,
    )
    forged_src = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(btc_rec, eth_rec),
    )
    split_ref = H40SplitManifest.build_preregistered_schedule(proto.protocol_hash, forged_src.manifest_hash)
    candidate_split = H40SplitManifest(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=forged_src.manifest_hash,
        base_eligible_start_utc=split_ref.base_eligible_start_utc,
        base_eligible_end_utc=split_ref.base_eligible_end_utc,
        base_eligible_count=split_ref.base_eligible_count,
        partitions=split_ref.partitions,
        exclusion_counts=split_ref.exclusion_counts,
        is_authoritative=True,
        attestation=None,
    )
    att = H40SplitAttestation.create(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=forged_src.manifest_hash,
        split_hash=candidate_split.split_hash,
        btc_source_id=btc_rec.source_id,
        btc_locator=btc_rec.locator,
        btc_file_sha256=fake_sha,
        btc_membership_sha256=fake_mem,
        btc_timestamp_count=len(full_ts),
        eth_source_id=eth_rec.source_id,
        eth_locator=eth_rec.locator,
        eth_file_sha256=fake_sha,
        eth_membership_sha256=fake_mem,
        eth_timestamp_count=len(full_ts),
    )
    forged_split = H40SplitManifest(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=forged_src.manifest_hash,
        base_eligible_start_utc=split_ref.base_eligible_start_utc,
        base_eligible_end_utc=split_ref.base_eligible_end_utc,
        base_eligible_count=split_ref.base_eligible_count,
        partitions=split_ref.partitions,
        exclusion_counts=split_ref.exclusion_counts,
        is_authoritative=True,
        attestation=att,
    )

    with pytest.raises(H40GuardError) as exc_info:
        forged_split.assert_authoritative(
            source_manifest=forged_src,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_persisted_partition_tampering_with_recomputed_attestation_fails_cold_reconstruction(tmp_path: Path) -> None:
    """Persisted split partition tampering followed by recomputing split/attestation hashes fails cold reconstruction."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, btc_rec, eth_rec = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    valid_split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    # Attacker tampers with WF1_TRAIN count in partitions
    tampered_parts = list(valid_split.partitions)
    p0 = tampered_parts[0]
    tampered_parts[0] = H40Partition(
        partition_id=p0.partition_id,
        fold=p0.fold,
        partition_type=p0.partition_type,
        start_utc=p0.start_utc,
        end_utc=p0.end_utc,
        count=p0.count - 10,
        first_timestamp_utc=p0.first_timestamp_utc,
        last_timestamp_utc=p0.last_timestamp_utc,
        timestamps_sha256="tampered_ts_hash",
    )

    # Attacker recomputes split_hash over the tampered partitions
    candidate_tampered = H40SplitManifest(
        protocol_identity_hash=valid_split.protocol_identity_hash,
        source_manifest_hash=valid_split.source_manifest_hash,
        base_eligible_start_utc=valid_split.base_eligible_start_utc,
        base_eligible_end_utc=valid_split.base_eligible_end_utc,
        base_eligible_count=valid_split.base_eligible_count,
        partitions=tuple(tampered_parts),
        exclusion_counts=valid_split.exclusion_counts,
        is_authoritative=False,
        attestation=None,
    )
    tampered_split_hash = candidate_tampered.split_hash

    # Attacker crafts a fresh attestation matching the tampered split_hash and real source receipts
    assert btc_rec.receipt is not None and eth_rec.receipt is not None
    tampered_att = H40SplitAttestation.create(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        split_hash=tampered_split_hash,
        btc_source_id=btc_rec.source_id,
        btc_locator=btc_rec.locator,
        btc_file_sha256=btc_rec.receipt.file_sha256,
        btc_membership_sha256=btc_rec.receipt.timestamp_membership_hash,
        btc_timestamp_count=btc_rec.receipt.timestamp_count,
        eth_source_id=eth_rec.source_id,
        eth_locator=eth_rec.locator,
        eth_file_sha256=eth_rec.receipt.file_sha256,
        eth_membership_sha256=eth_rec.receipt.timestamp_membership_hash,
        eth_timestamp_count=eth_rec.receipt.timestamp_count,
        is_production_canonical=False,
    )

    tampered_split = H40SplitManifest(
        protocol_identity_hash=valid_split.protocol_identity_hash,
        source_manifest_hash=valid_split.source_manifest_hash,
        base_eligible_start_utc=valid_split.base_eligible_start_utc,
        base_eligible_end_utc=valid_split.base_eligible_end_utc,
        base_eligible_count=valid_split.base_eligible_count,
        partitions=tuple(tampered_parts),
        exclusion_counts=valid_split.exclusion_counts,
        is_authoritative=False,
        attestation=tampered_att,
    )

    # In an offline check, tampered_split has matching split_hash, valid attestation, matching source receipts.
    # But assert_synthetic_validator_split cold-reconstructs the true partitions from disk and fails closed!
    with pytest.raises(H40GuardError) as exc_info:
        tampered_split.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


def test_mutate_one_artifact_byte_after_serialization_fails_cold_assertion(tmp_path: Path) -> None:
    """Mutating one byte in the artifact after serialization causes cold assert_synthetic_validator_split to fail."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )
    json_str = split.canonical_json()
    roundtrip = H40SplitManifest.from_dict(json.loads(json_str))

    # Before mutation: passes
    roundtrip.assert_synthetic_validator_split(
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    # Mutate 1 byte of btc artifact on disk
    btc_path = tmp_path / "btc_1h.parquet"
    raw_bytes = bytearray(btc_path.read_bytes())
    raw_bytes[-1] = (raw_bytes[-1] + 1) % 256
    btc_path.write_bytes(bytes(raw_bytes))

    # After mutation: cold verification detects hash tampering
    with pytest.raises(H40GuardError) as exc_info:
        roundtrip.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


def test_mutate_one_source_timestamp_after_serialization_fails_cold_assertion(tmp_path: Path) -> None:
    """Mutating one timestamp in the artifact after serialization causes cold assert_synthetic_validator_split to fail."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )
    json_str = split.canonical_json()
    roundtrip = H40SplitManifest.from_dict(json.loads(json_str))

    # Mutate one timestamp in ETH artifact
    mutated_ts = list(full_ts)
    mutated_ts[500] = "2021-01-21T21:00:00Z"
    _create_synthetic_parquet(tmp_path / "eth_1h.parquet", "ETHUSDT", mutated_ts)

    with pytest.raises(H40GuardError) as exc_info:
        roundtrip.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code in {H40ReasonCode.SOURCE_HASH_MISMATCH, H40ReasonCode.DUPLICATE_TIMESTAMP}


# --- Additional Structural Partition Logic Tests ---

def test_pooled_btc_eth_intersection_drops_missing_timestamps() -> None:
    """Timestamps present in BTC but missing in ETH (or vice versa) are dropped from the common base set."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)

    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    missing_eth_ts = "2021-06-15T12:00:00Z"
    eth_ts = [t for t in full_ts if t != missing_eth_ts]

    split = H40SplitManifest.build_materialized(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        btc_timestamps=full_ts,
        eth_timestamps=eth_ts,
    )

    wf1_train = split.get_partition("WF1_TRAIN")
    assert wf1_train.count == 15311
    assert split.exclusion_counts[H40ReasonCode.SOURCE_GAP.value] == 1


def test_split_count_and_hash_changes_when_timestamp_removed() -> None:
    """Removing even one valid timestamp changes partition counts and changes the split manifest hash."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)

    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    split_full = H40SplitManifest.build_materialized(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        btc_timestamps=full_ts,
        eth_timestamps=full_ts,
    )

    dropped_hour = "2023-06-01T10:00:00Z"
    pruned_ts = [t for t in full_ts if t != dropped_hour]

    split_pruned = H40SplitManifest.build_materialized(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        btc_timestamps=pruned_ts,
        eth_timestamps=pruned_ts,
    )

    assert split_pruned.split_hash != split_full.split_hash
    assert split_pruned.get_partition("WF2_CALIBRATION").count == split_full.get_partition("WF2_CALIBRATION").count - 1
    assert split_pruned.exclusion_counts[H40ReasonCode.SOURCE_GAP.value] == 1


def test_confirmation_endpoint_constraint_removes_uncovered_timestamps() -> None:
    """Confirmation endpoint constraint drops timestamps lacking 24h future coverage and records HORIZON_TRUNCATED."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)

    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    split = H40SplitManifest.build_materialized(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        btc_timestamps=full_ts,
        eth_timestamps=full_ts,
    )

    assert split.exclusion_counts[H40ReasonCode.HORIZON_TRUNCATED.value] == 23
    conf_holdout = split.get_partition("CONFIRMATION_HOLDOUT")
    assert conf_holdout.count == 8737


def test_no_boundary_shifts_occur_after_gaps() -> None:
    """Gaps decrease partition counts but partition boundaries remain strictly fixed."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)

    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    gapped_ts = [t for t in full_ts if not ("2021-03-01T10:00:00Z" <= t <= "2021-03-01T14:00:00Z")]

    split = H40SplitManifest.build_materialized(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        btc_timestamps=gapped_ts,
        eth_timestamps=gapped_ts,
    )

    wf1 = split.get_partition("WF1_TRAIN")
    assert wf1.start_utc == "2021-01-31T00:00:00Z"
    assert wf1.end_utc == "2022-10-31T00:00:00Z"
    assert wf1.count == 15312 - 5
    assert split.exclusion_counts[H40ReasonCode.SOURCE_GAP.value] == 5


def test_builder_cannot_return_authoritative_split_from_constants_alone(tmp_path: Path) -> None:
    """Default or preregistered schedule builder cannot claim authoritative verified split status."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    split_default = H40SplitManifest.build_default(proto.protocol_hash, src_manifest.manifest_hash)

    assert not split_default.is_authoritative
    with pytest.raises(H40GuardError) as exc_info:
        split_default.assert_authoritative(source_manifest=src_manifest, repo_root=tmp_path)
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED

    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.build_materialized(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest_hash=src_manifest.manifest_hash,
            btc_timestamps=[],
            eth_timestamps=[],
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_confirmation_timestamps_strictly_isolated() -> None:
    """Confirmation holdout timestamps do not overlap with any training or calibration partition."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    split_manifest = H40SplitManifest.build_preregistered_schedule(proto.protocol_hash, src_manifest.manifest_hash)

    conf_holdout = split_manifest.get_partition("CONFIRMATION_HOLDOUT")
    conf_train = split_manifest.get_partition("CONFIRMATION_TRAIN")
    conf_purge = split_manifest.get_partition("CONFIRMATION_PURGE")

    assert conf_train.end_utc == conf_purge.start_utc
    assert conf_purge.end_utc == conf_holdout.start_utc
    assert conf_holdout.start_utc == "2025-02-01T00:00:00Z"
    assert conf_purge.count == 24


def test_split_manifest_hash_changes_on_membership_tampering() -> None:
    """Altering partition timestamp count or range alters the split manifest hash."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    split_manifest = H40SplitManifest.build_preregistered_schedule(proto.protocol_hash, src_manifest.manifest_hash)
    base_hash = split_manifest.split_hash

    parts = list(split_manifest.partitions)
    p0 = parts[0]
    tampered_p0 = H40Partition(
        partition_id=p0.partition_id,
        fold=p0.fold,
        partition_type=p0.partition_type,
        start_utc=p0.start_utc,
        end_utc=p0.end_utc,
        count=p0.count - 1,
        first_timestamp_utc=p0.first_timestamp_utc,
        last_timestamp_utc=p0.last_timestamp_utc,
        timestamps_sha256="tampered",
    )
    parts[0] = tampered_p0

    tampered_split = H40SplitManifest(
        protocol_identity_hash=split_manifest.protocol_identity_hash,
        source_manifest_hash=split_manifest.source_manifest_hash,
        base_eligible_start_utc=split_manifest.base_eligible_start_utc,
        base_eligible_end_utc=split_manifest.base_eligible_end_utc,
        base_eligible_count=split_manifest.base_eligible_count,
        partitions=tuple(parts),
        exclusion_counts=split_manifest.exclusion_counts,
        is_authoritative=False,
    )
    assert tampered_split.split_hash != base_hash


# ==============================================================================
# 4. Configuration Ledger Tests
# ==============================================================================

def test_ledger_search_budget_exhaustion_at_168() -> None:
    """Ledger allows exactly 168 slots; slot 169 is rejected with SEARCH_BUDGET_EXHAUSTED."""
    ledger = H40ConfigurationLedger()
    assert ledger.MAX_CAPACITY == MAX_CONFIGURATION_SLOTS

    for i in range(MAX_CONFIGURATION_SLOTS):
        slot = H40ConfigurationSlot.create(
            slot_index=i,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
            hyperparameters={"index": i},
        )
        assigned = ledger.register_slot(slot)
        assert assigned == i

    assert ledger.slot_count == 168
    assert ledger.remaining_budget == 0

    # 169th attempt
    slot_169 = H40ConfigurationSlot.create(
        slot_index=168,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
        hyperparameters={"index": 168},
    )
    with pytest.raises(H40GuardError) as exc_info:
        ledger.register_slot(slot_169)
    assert exc_info.value.reason_code == H40ReasonCode.SEARCH_BUDGET_EXHAUSTED


def test_ledger_slot_dropping_does_not_replenish_budget() -> None:
    """Dropping or failing a slot consumes budget permanently; slots are never recycled."""
    ledger = H40ConfigurationLedger()
    slot0 = H40ConfigurationSlot.create(
        slot_index=0,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
        hyperparameters={"tag": "slot0"},
    )
    ledger.register_slot(slot0)
    assert ledger.slot_count == 1

    # Drop slot 0
    ledger.drop_slot(0, reason_code=H40ReasonCode.NOT_TESTABLE, notes="Data unverified")
    assert ledger.slots[0].status == "DROPPED"
    assert ledger.slots[0].reason_code == H40ReasonCode.NOT_TESTABLE
    assert ledger.slot_count == 1  # Still 1 slot consumed

    # Next registered slot must be index 1
    slot1 = H40ConfigurationSlot.create(
        slot_index=1,
        family_combination=[H40Family.D2_BREAKOUT_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="8h",
        action_threshold=0.60,
    )
    ledger.register_slot(slot1)
    assert ledger.slot_count == 2
    assert ledger.remaining_budget == 166


def test_ledger_rejects_unauthorized_families_and_pairs() -> None:
    """Only D1..D5 and the 4 authorized depth-two combinations are accepted."""
    # Authorized depth 1
    for fam in H40Family:
        slot = H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[fam],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
        )
        assert slot.family_combination == (fam,)

    # Authorized depth 2 pairs: D1+D4, D1+D5, D2+D4, D3+D5
    for pair in ALLOWED_DEPTH_TWO_PAIRS:
        fams = list(pair)
        slot = H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=fams,
            asset_scope=["BTCUSDT"],
            primary_horizon="8h",
            action_threshold=0.60,
        )
        assert len(slot.family_combination) == 2

    # Unauthorized depth 2 pair: D1+D2
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION, H40Family.D2_BREAKOUT_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.FAMILY_PAIR_RESTRICTED

    # Depth 3 rejected
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[
                H40Family.D1_TREND_CONTINUATION,
                H40Family.D4_BTC_ETH_CONFIRM_DIVERGE,
                H40Family.D5_FUNDING_DIRECTION_INTERACTION,
            ],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.FAMILY_PAIR_RESTRICTED


def test_ledger_rejects_invalid_horizon_threshold_or_asset() -> None:
    """Primary horizons, thresholds, and asset scopes outside preregistered sets fail closed."""
    # Invalid horizon
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="24h",  # 24h is diagnostic only, not allowed as primary
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.INTERVAL_MISMATCH

    # Invalid threshold
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["BTCUSDT"],
            primary_horizon="4h",
            action_threshold=0.70,  # not in {0.55, 0.60, 0.65}
        )
    assert exc_info.value.reason_code == H40ReasonCode.THRESHOLD_UNMET

    # Invalid asset
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfigurationSlot.create(
            slot_index=0,
            family_combination=[H40Family.D1_TREND_CONTINUATION],
            asset_scope=["SOLUSDT"],
            primary_horizon="4h",
            action_threshold=0.55,
        )
    assert exc_info.value.reason_code == H40ReasonCode.PRODUCT_MISMATCH


def test_ledger_rejects_forbidden_performance_metrics_in_hyperparameters() -> None:
    """Pre-outcome hyperparameters cannot include outcome or performance metric fields."""
    for bad_key in ["sharpe", "profit_factor", "return", "pnl", "win_rate"]:
        with pytest.raises(H40GuardError) as exc_info:
            H40ConfigurationSlot.create(
                slot_index=0,
                family_combination=[H40Family.D1_TREND_CONTINUATION],
                asset_scope=["BTCUSDT"],
                primary_horizon="4h",
                action_threshold=0.55,
                hyperparameters={bad_key: 1.5},
            )
        assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_ledger_config_identity_conflict_detection() -> None:
    """Re-registering same config ID at different slot raises CONFIG_IDENTITY_CONFLICT."""
    ledger = H40ConfigurationLedger()
    slot0 = H40ConfigurationSlot.create(
        slot_index=0,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
        hyperparameters={"param_a": 10},
    )
    ledger.register_slot(slot0)

    # Identical config attempted at slot 1
    slot1_same = H40ConfigurationSlot.create(
        slot_index=1,
        family_combination=[H40Family.D1_TREND_CONTINUATION],
        asset_scope=["BTCUSDT"],
        primary_horizon="4h",
        action_threshold=0.55,
        hyperparameters={"param_a": 10},
    )
    with pytest.raises(H40GuardError) as exc_info:
        ledger.register_slot(slot1_same)
    assert exc_info.value.reason_code == H40ReasonCode.CONFIG_IDENTITY_CONFLICT


# ==============================================================================
# 5. Access Guards & Lifecycle Tests (Repair A & B)
# ==============================================================================

def test_confirmation_guard_metadata_vs_outcomes() -> None:
    """Confirmation guard permits metadata inspection but strictly blocks outcome values."""
    guard = H40ConfirmationGuard()
    # Metadata access succeeds
    guard.assert_metadata_accessible()

    # Outcome / return / price evaluation fails closed
    with pytest.raises(H40GuardError) as exc_info:
        guard.assert_outcomes_accessible()
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_confirmation_guard_unlocked_construction_impossible() -> None:
    """Confirmation guard has no parameters to enable outcome access; construction is always locked."""
    guard = H40ConfirmationGuard()
    assert not guard.is_ready
    with pytest.raises(H40GuardError) as exc_info:
        guard.assert_outcomes_accessible()
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_confirmation_guard_forging_readiness_fails() -> None:
    """Attempting to forge readiness on confirmation guard fails to unlock outcomes."""
    guard = H40ConfirmationGuard()
    # Attempt to monkeypatch or attribute assign fails
    with pytest.raises((AttributeError, TypeError)):
        guard.is_ready = True  # type: ignore[misc]
    # Guard method assert_outcomes_accessible must still fail closed
    with pytest.raises(H40GuardError) as exc_info:
        guard.assert_outcomes_accessible()
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_lifecycle_cannot_construct_at_confirmation_ready() -> None:
    """Initializing lifecycle state machine directly at H40_CONFIRMATION_READY fails closed."""
    with pytest.raises(H40GuardError) as exc_info:
        H40LifecycleStateMachine(initial_state=H40LifecycleState.H40_CONFIRMATION_READY)
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_lifecycle_cannot_construct_at_confirmation_evaluated_once() -> None:
    """Initializing lifecycle state machine directly at H40_CONFIRMATION_EVALUATED_ONCE fails closed."""
    with pytest.raises(H40GuardError) as exc_info:
        H40LifecycleStateMachine(initial_state=H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE)
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_lifecycle_cannot_construct_at_post_scaffold_states() -> None:
    """Initializing lifecycle state machine directly at post-scaffold states fails closed."""
    for state in [
        H40LifecycleState.H40_DISCOVERY,
        H40LifecycleState.H40_CANDIDATE_LOCKED,
        H40LifecycleState.H40_WALK_FORWARD_VALIDATED,
        H40LifecycleState.H40_NO_GO,
    ]:
        with pytest.raises(H40GuardError) as exc_info:
            H40LifecycleStateMachine(initial_state=state)
        assert exc_info.value.reason_code == H40ReasonCode.NOT_TESTABLE


def test_protected_source_guard_blocks_h39_and_final_holdout() -> None:
    """Protected surface guard fails closed on any path referencing H39 or Final Holdout."""
    for forbidden_path in [
        "data/research/h39_validation/results.parquet",
        "artifacts/final_holdout/data.csv",
        "data/v0323_h39/labels.json",
    ]:
        with pytest.raises(H40GuardError) as exc_info:
            H40ProtectedSurfaceGuard.assert_surface_allowed(forbidden_path)
        assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    # Unprotected path succeeds
    H40ProtectedSurfaceGuard.assert_surface_allowed("data/research/cross_asset_1h/ETHUSDT.parquet")


def test_execution_guard_permanently_denied() -> None:
    """Execution guard fails closed asserting execution is disabled."""
    with pytest.raises(H40GuardError) as exc_info:
        H40ExecutionGuard.assert_execution_disabled()
    assert exc_info.value.reason_code == H40ReasonCode.EXECUTION_DISABLED


def test_lifecycle_state_machine_p1_boundary() -> None:
    """P1 initializes in H40_P1_SCAFFOLDED and cannot jump to CONFIRMATION_READY or out-of-order."""
    sm = H40LifecycleStateMachine(initial_state=H40LifecycleState.H40_P1_SCAFFOLDED)
    assert sm.current_state == H40LifecycleState.H40_P1_SCAFFOLDED

    # Illegal jump to CONFIRMATION_READY
    with pytest.raises(H40GuardError) as exc_info:
        sm.transition_to(H40LifecycleState.H40_CONFIRMATION_READY)
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY

    # Legal transition to DISCOVERY
    sm.transition_to(H40LifecycleState.H40_DISCOVERY)
    assert sm.current_state == H40LifecycleState.H40_DISCOVERY


# ==============================================================================
# 6. Adversarial Security & Relabel Attack Tests (Repair B)
# ==============================================================================

def test_protected_source_relabel_attack_fails_before_read() -> None:
    """A caller relabelling an H39 protected source as VERIFIED fails before any read occurs."""
    with pytest.raises(H40GuardError) as exc_info:
        H40SourceRecord(
            source_id="H39_ATTACK",
            status=H40SourceStatus.VERIFIED,
            locator="data/research/h39_validation/results.parquet",
        )
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    with pytest.raises(H40GuardError) as exc_info:
        H40SourceRecord(
            source_id="H39_ATTACK",
            status=H40SourceStatus.UNVERIFIED,
            locator="data/research/h39_validation/results.parquet",
        )
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    # Validation also fails closed before read
    rec = H40SourceRecord(
        source_id="ALLOWED_SOURCE",
        status=H40SourceStatus.UNVERIFIED,
        locator="some_safe_file.parquet",
    )
    object.__setattr__(rec, "locator", "data/research/h39_validation/results.parquet")
    with pytest.raises(H40GuardError) as exc_info:
        validate_source_artifact(Path("."), rec)
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_final_holdout_relabel_attack_fails_before_read() -> None:
    """A caller relabelling a Final Holdout source as VERIFIED fails before any read occurs."""
    with pytest.raises(H40GuardError) as exc_info:
        H40SourceRecord(
            source_id="FINAL_HOLDOUT_ATTACK",
            status=H40SourceStatus.VERIFIED,
            locator="artifacts/final_holdout/data.parquet",
        )
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    with pytest.raises(H40GuardError) as exc_info:
        H40SourceRecord(
            source_id="FINAL_HOLDOUT_ATTACK",
            status=H40SourceStatus.UNVERIFIED,
            locator="artifacts/final_holdout/data.parquet",
        )
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    rec = H40SourceRecord(
        source_id="ALLOWED_SOURCE",
        status=H40SourceStatus.UNVERIFIED,
        locator="some_safe_file.parquet",
    )
    object.__setattr__(rec, "locator", "artifacts/final_holdout/data.parquet")
    with pytest.raises(H40GuardError) as exc_info:
        validate_source_artifact(Path("."), rec)
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_serialized_manifest_relabel_forbidden_to_verified_fails() -> None:
    """Tampering with serialized manifest to change FORBIDDEN source to VERIFIED fails upon deserialization."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    d = src_manifest.to_dict()

    for s in d["sources"]:
        if s["source_id"] == "H39_PROTECTED":
            s["status"] = "VERIFIED"

    with pytest.raises(H40GuardError) as exc_info:
        tuple(H40SourceRecord.from_dict(s) for s in d["sources"])
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_protected_surface_normalized_and_relative_path_attack() -> None:
    """Relative path traversal and non-canonical paths to protected surfaces fail closed."""
    traversal_paths = [
        "data/research/../research/h39_validation/file.parquet",
        "./artifacts/final_holdout/data.csv",
        "data/research/cross_asset_1h/../../research/h39_validation/x.parquet",
        "data/v0323_h39/../v0323_h39/labels.json",
    ]
    for p in traversal_paths:
        with pytest.raises(H40GuardError) as exc_info:
            H40ProtectedSurfaceGuard.assert_path_allowed(p)
        assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_protected_surface_symlink_attack_synthetic_temp_path(tmp_path: Path) -> None:
    """Symlink pointing to a protected substring is resolved and blocked before access."""
    fake_protected_dir = tmp_path / "h39_validation"
    fake_protected_dir.mkdir()
    fake_file = fake_protected_dir / "secret.parquet"
    fake_file.write_bytes(b"forbidden_data")

    benign_dir = tmp_path / "benign"
    benign_dir.mkdir()
    symlink_file = benign_dir / "harmless.parquet"

    try:
        symlink_file.symlink_to(fake_file)
    except (OSError, NotImplementedError):
        pytest.skip("Filesystem does not support symlinks in this environment")

    # Raw name is harmless.parquet, but resolved path points to h39_validation
    with pytest.raises(H40GuardError) as exc_info:
        H40ProtectedSurfaceGuard.assert_path_allowed(symlink_file)
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_adversarial_serialized_manifest_tampering() -> None:
    """Crafting or tampering with an allowed source in serialized JSON manifest alters its hash."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    original_dict = src_manifest.to_dict()
    original_hash = src_manifest.manifest_hash

    # Attacker modifies JSON serialized payload for an allowed unverified source
    tampered_dict = copy.deepcopy(original_dict)
    for src in tampered_dict["sources"]:
        if src["source_id"] == "ETHUSDT_DERIVATIVES_FLOW":
            src["locator"] = "data/research/cross_asset_1h/tampered.parquet"

    tampered_canonical_json = canonical_json(tampered_dict)
    assert tampered_canonical_json
    tampered_hash = canonical_sha256(tampered_dict)

    # Hashes cannot match
    assert tampered_hash != original_hash

    reconstructed_sources = tuple(H40SourceRecord.from_dict(s) for s in tampered_dict["sources"])
    reconstructed_manifest = H40SourceManifest(
        protocol_identity_hash=tampered_dict["protocol_identity_hash"],
        sources=reconstructed_sources,
    )
    assert reconstructed_manifest.manifest_hash == tampered_hash
    assert reconstructed_manifest.manifest_hash != original_hash


# ==============================================================================
# 13. Canonical Source Root Binding Adversarial Tests (P1R4)
# ==============================================================================

def test_noncanonical_locator_cannot_obtain_production_authority(tmp_path: Path) -> None:
    """1. Non-canonical locators cannot obtain production authority even if file is valid/verified."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    # Calling materialize_authoritative with default authority policy (production) MUST fail
    # because synthetic locators (btc_1h.parquet) do not match canonical spec
    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.materialize_authoritative(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED
    assert "locator mismatch" in str(exc_info.value)


def test_caller_manifest_cannot_redefine_canonical_btc_locator(tmp_path: Path) -> None:
    """2. Caller custom manifest pointing BTC to arbitrary path cannot obtain production split authority."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    _create_synthetic_parquet(tmp_path / "data/research/custom_btc.parquet", "BTCUSDT", full_ts)
    _create_synthetic_parquet(tmp_path / "data/research/cross_asset_1h/ETHUSDT.parquet", "ETHUSDT", full_ts)

    custom_btc = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/custom_btc.parquet",
        product="BTCUSDT",
        cadence="1h",
    )
    custom_eth = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/cross_asset_1h/ETHUSDT.parquet",
        product="ETHUSDT",
        cadence="1h",
    )
    btc_receipt = validate_source_artifact(tmp_path, custom_btc, expected_product="BTCUSDT", expected_cadence="1h")
    eth_receipt = validate_source_artifact(tmp_path, custom_eth, expected_product="ETHUSDT", expected_cadence="1h")
    assert btc_receipt.status == H40SourceStatus.VERIFIED
    assert eth_receipt.status == H40SourceStatus.VERIFIED

    custom_src = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(
            H40SourceRecord(
                source_id="BTCUSDT_USD_M_1H",
                status=H40SourceStatus.VERIFIED,
                locator=custom_btc.locator,
                product=custom_btc.product,
                cadence=custom_btc.cadence,
                receipt=btc_receipt,
            ),
            H40SourceRecord(
                source_id="ETHUSDT_USD_M_1H",
                status=H40SourceStatus.VERIFIED,
                locator=custom_eth.locator,
                product=custom_eth.product,
                cadence=custom_eth.cadence,
                receipt=eth_receipt,
            ),
        ),
    )

    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.materialize_authoritative(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest=custom_src,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED
    assert "locator mismatch" in str(exc_info.value)


def test_caller_manifest_cannot_redefine_canonical_eth_locator(tmp_path: Path) -> None:
    """3. Caller custom manifest pointing ETH to arbitrary path cannot obtain production split authority."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    _create_synthetic_parquet(tmp_path / "data/research/custom_eth.parquet", "ETHUSDT", full_ts)

    custom_eth = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/custom_eth.parquet",
        product="ETHUSDT",
        cadence="1h",
    )
    eth_receipt = validate_source_artifact(tmp_path, custom_eth, expected_product="ETHUSDT", expected_cadence="1h")
    assert eth_receipt.status == H40SourceStatus.VERIFIED

    verified_eth = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator=custom_eth.locator,
        product=custom_eth.product,
        cadence=custom_eth.cadence,
        receipt=eth_receipt,
    )

    with pytest.raises(H40GuardError) as exc_info:
        assert_canonical_source_record(verified_eth, proto.protocol_hash)
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED
    assert "locator mismatch" in str(exc_info.value)


def test_wrong_product_or_cadence_rejected_in_canonical_spec() -> None:
    """4. Records with mismatched product or cadence fail canonical source specification check."""
    proto = H40ProtocolIdentity.default()

    # Case A: Wrong BTC product
    btc_wrong_product = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/BTCUSDT/data_manifest.json",
        product="BTCUSDC",
        cadence="1h",
    )
    with pytest.raises(H40GuardError) as exc_a:
        assert_canonical_source_record(btc_wrong_product, proto.protocol_hash)
    assert exc_a.value.reason_code == H40ReasonCode.PRODUCT_MISMATCH

    # Case B: Wrong BTC cadence
    btc_wrong_cadence = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/BTCUSDT/data_manifest.json",
        product="BTCUSDT",
        cadence="1m",
    )
    with pytest.raises(H40GuardError) as exc_b:
        assert_canonical_source_record(btc_wrong_cadence, proto.protocol_hash)
    assert exc_b.value.reason_code == H40ReasonCode.INTERVAL_MISMATCH

    # Case C: Wrong ETH product
    eth_wrong_product = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/cross_asset_1h/ETHUSDT.parquet",
        product="ETHBTC",
        cadence="1h",
    )
    with pytest.raises(H40GuardError) as exc_c:
        assert_canonical_source_record(eth_wrong_product, proto.protocol_hash)
    assert exc_c.value.reason_code == H40ReasonCode.PRODUCT_MISMATCH

    # Case D: Wrong ETH cadence
    eth_wrong_cadence = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/cross_asset_1h/ETHUSDT.parquet",
        product="ETHUSDT",
        cadence="1d",
    )
    with pytest.raises(H40GuardError) as exc_d:
        assert_canonical_source_record(eth_wrong_cadence, proto.protocol_hash)
    assert exc_d.value.reason_code == H40ReasonCode.INTERVAL_MISMATCH


def test_unauthorized_source_id_fails_canonical_spec() -> None:
    """5. Unknown or non-canonical source_id fails canonical source spec lookup and assertion."""
    proto = H40ProtocolIdentity.default()

    with pytest.raises(H40GuardError) as exc_info:
        get_canonical_source_spec(proto.protocol_hash, "SOLUSDT_USD_M_1H")
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED

    unauthorized_record = H40SourceRecord(
        source_id="SOLUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/SOLUSDT.parquet",
        product="SOLUSDT",
        cadence="1h",
    )
    with pytest.raises(H40GuardError) as exc_rec:
        assert_canonical_source_record(unauthorized_record, proto.protocol_hash)
    assert exc_rec.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_tampered_archive_checksum_fails_canonical_spec() -> None:
    """6. Records with mismatched archive_set_sha256 or frozen reference file SHA fail closed."""
    proto = H40ProtocolIdentity.default()
    eth_spec = get_canonical_source_spec(proto.protocol_hash, "ETHUSDT_USD_M_1H")
    assert isinstance(eth_spec, H40CanonicalSourceSpec)
    assert eth_spec.archive_set_sha256 is not None

    # Tampered archive set SHA
    eth_tampered_archive = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/cross_asset_1h/ETHUSDT.parquet",
        product="ETHUSDT",
        cadence="1h",
        archive_set_sha256="0" * 64,
    )
    with pytest.raises(H40GuardError) as exc_a:
        assert_canonical_source_record(eth_tampered_archive, proto.protocol_hash)
    assert exc_a.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH

    # Tampered file SHA for ETH
    assert eth_spec.reference_file_sha256 is not None
    eth_tampered_file_sha = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/cross_asset_1h/ETHUSDT.parquet",
        product="ETHUSDT",
        cadence="1h",
        archive_set_sha256=eth_spec.archive_set_sha256,
        file_sha256="1" * 64,
    )
    with pytest.raises(H40GuardError) as exc_b:
        assert_canonical_source_record(eth_tampered_file_sha, proto.protocol_hash)
    assert exc_b.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


def test_caller_replacement_reference_cannot_redefine_production_authority(tmp_path: Path) -> None:
    """7. Caller-provided replacement reference manifest cannot redefine canonical production H40 authority."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)

    # Caller creates an alternative reference manifest pointing to custom files
    _create_synthetic_parquet(tmp_path / "custom_btc.parquet", "BTCUSDT", full_ts)
    _create_synthetic_parquet(tmp_path / "custom_eth.parquet", "ETHUSDT", full_ts)

    custom_ref = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(
            H40SourceRecord(
                source_id="BTCUSDT_USD_M_1H",
                status=H40SourceStatus.UNVERIFIED,
                locator="custom_btc.parquet",
                product="BTCUSDT",
                cadence="1h",
            ),
            H40SourceRecord(
                source_id="ETHUSDT_USD_M_1H",
                status=H40SourceStatus.UNVERIFIED,
                locator="custom_eth.parquet",
                product="ETHUSDT",
                cadence="1h",
            ),
        ),
    )

    caller_manifest = materialize_verified_manifest(
        repo_root=tmp_path,
        protocol_identity_hash=proto.protocol_hash,
        reference_manifest=custom_ref,
    )

    # When trying to obtain production split authority with this manifest:
    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.materialize_authoritative(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest=caller_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED
    assert "locator mismatch" in str(exc_info.value)


def test_real_repo_btc_artifact_yields_not_testable_and_fails_closed() -> None:
    """8. Real repository BTC manifest evaluated under 1h cadence yields NOT_TESTABLE and fails closed."""
    proto = H40ProtocolIdentity.default()
    ref = H40SourceManifest.build_preregistered_reference(proto.protocol_hash)
    btc_ref = ref.get_source("BTCUSDT_USD_M_1H")

    # Evaluate real repo artifact at data/research/BTCUSDT/data_manifest.json
    receipt = validate_source_artifact(
        repo_root=Path("."),
        record=btc_ref,
        expected_product="BTCUSDT",
        expected_cadence="1h",
    )
    assert receipt.status == H40SourceStatus.NOT_TESTABLE
    assert receipt.reason_code in {H40ReasonCode.INTERVAL_MISMATCH, H40ReasonCode.SOURCE_MISSING}
    if receipt.reason_code == H40ReasonCode.INTERVAL_MISMATCH:
        assert "1m" in receipt.notes

    # Materializing on real repo results in NOT_TESTABLE for BTC
    real_manifest = materialize_verified_manifest(
        repo_root=Path("."),
        protocol_identity_hash=proto.protocol_hash,
    )
    btc_real = real_manifest.get_source("BTCUSDT_USD_M_1H")
    assert btc_real.status == H40SourceStatus.NOT_TESTABLE

    # Production authoritative split materialization must fail closed
    with pytest.raises(H40GuardError) as exc_info:
        H40SplitManifest.materialize_authoritative(
            protocol_identity_hash=proto.protocol_hash,
            source_manifest=real_manifest,
            repo_root=Path("."),
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_protected_h39_final_holdout_substitution_denied_before_read() -> None:
    """9. Attempting to use an H39 or final holdout path as a source root fails closed before disk read."""
    protected_locators = [
        "artifacts/final_holdout/data.csv",
        "data/research/h39_validation/raw.parquet",
        "data/v0323_h39/labels.json",
        "artifacts/v0.3.23_holdout/data.parquet",
        "data/research/h39_protected/signals.parquet",
    ]
    for loc in protected_locators:
        with pytest.raises(H40GuardError) as exc_info:
            H40SourceRecord(
                source_id="BTCUSDT_USD_M_1H",
                status=H40SourceStatus.UNVERIFIED,
                locator=loc,
                product="BTCUSDT",
                cadence="1h",
            )
        assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED

    # Attempting to use forbidden source_id fails closed before read
    forbidden_source_ids = ["H39_PRIMARY", "FINAL_HOLDOUT_BTC"]
    for sid in forbidden_source_ids:
        with pytest.raises(H40GuardError) as exc_id:
            H40SourceRecord(
                source_id=sid,
                status=H40SourceStatus.UNVERIFIED,
                locator="data/research/BTCUSDT/data_manifest.json",
                product="BTCUSDT",
                cadence="1h",
            )
        assert exc_id.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_offline_forgery_attacks_remain_closed(tmp_path: Path) -> None:
    """10. Offline forgery attacks claiming production authority are rejected by cold verification."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)

    fake_file_sha = "e" * 64
    fake_mem_sha = hashlib.sha256(",".join(full_ts).encode("utf-8")).hexdigest()

    btc_rec = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="data/research/BTCUSDT/data_manifest.json",
        product="BTCUSDT",
        cadence="1h",
        row_count=len(full_ts),
        file_sha256=fake_file_sha,
        receipt=H40SourceValidationReceipt(
            source_id="BTCUSDT_USD_M_1H",
            locator="data/research/BTCUSDT/data_manifest.json",
            file_sha256=fake_file_sha,
            product="BTCUSDT",
            cadence="1h",
            timestamp_field="open_time_ms",
            timestamp_count=len(full_ts),
            first_timestamp_utc=full_ts[0],
            last_timestamp_utc=full_ts[-1],
            duplicate_count=0,
            gap_count=0,
            gaps=(),
            timestamp_membership_hash=fake_mem_sha,
            status=H40SourceStatus.VERIFIED,
        ),
    )
    eth_rec = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="data/research/cross_asset_1h/ETHUSDT.parquet",
        product="ETHUSDT",
        cadence="1h",
        row_count=len(full_ts),
        file_sha256=fake_file_sha,
        receipt=H40SourceValidationReceipt(
            source_id="ETHUSDT_USD_M_1H",
            locator="data/research/cross_asset_1h/ETHUSDT.parquet",
            file_sha256=fake_file_sha,
            product="ETHUSDT",
            cadence="1h",
            timestamp_field="open_time_ms",
            timestamp_count=len(full_ts),
            first_timestamp_utc=full_ts[0],
            last_timestamp_utc=full_ts[-1],
            duplicate_count=0,
            gap_count=0,
            gaps=(),
            timestamp_membership_hash=fake_mem_sha,
            status=H40SourceStatus.VERIFIED,
        ),
    )
    forged_manifest = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(btc_rec, eth_rec),
    )

    split_ref = H40SplitManifest.build_preregistered_schedule(proto.protocol_hash, forged_manifest.manifest_hash)
    candidate_split = H40SplitManifest(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=forged_manifest.manifest_hash,
        base_eligible_start_utc=split_ref.base_eligible_start_utc,
        base_eligible_end_utc=split_ref.base_eligible_end_utc,
        base_eligible_count=split_ref.base_eligible_count,
        partitions=split_ref.partitions,
        exclusion_counts=split_ref.exclusion_counts,
        is_authoritative=True,
        attestation=None,
    )
    forged_att = H40SplitAttestation.create(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=forged_manifest.manifest_hash,
        split_hash=candidate_split.split_hash,
        btc_source_id=btc_rec.source_id,
        btc_locator=btc_rec.locator,
        btc_file_sha256=fake_file_sha,
        btc_membership_sha256=fake_mem_sha,
        btc_timestamp_count=len(full_ts),
        eth_source_id=eth_rec.source_id,
        eth_locator=eth_rec.locator,
        eth_file_sha256=fake_file_sha,
        eth_membership_sha256=fake_mem_sha,
        eth_timestamp_count=len(full_ts),
        is_production_canonical=True,
    )
    forged_split = H40SplitManifest(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=forged_manifest.manifest_hash,
        base_eligible_start_utc=split_ref.base_eligible_start_utc,
        base_eligible_end_utc=split_ref.base_eligible_end_utc,
        base_eligible_count=split_ref.base_eligible_count,
        partitions=split_ref.partitions,
        exclusion_counts=split_ref.exclusion_counts,
        is_authoritative=True,
        attestation=forged_att,
    )

    with pytest.raises(H40GuardError) as exc_info:
        forged_split.assert_authoritative(
            source_manifest=forged_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code in {H40ReasonCode.SOURCE_MISSING, H40ReasonCode.SOURCE_HASH_MISMATCH, H40ReasonCode.NOT_TESTABLE, H40ReasonCode.SOURCE_UNVERIFIED}


def test_persisted_split_rehash_attack_remains_closed(tmp_path: Path) -> None:
    """11. Persisted split partition tampering with rehashed attestation fails cold partition reconstruction."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, btc_rec, eth_rec = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    valid_split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    # Tamper with partition count
    tampered_parts = list(valid_split.partitions)
    p0 = tampered_parts[0]
    tampered_parts[0] = H40Partition(
        partition_id=p0.partition_id,
        fold=p0.fold,
        partition_type=p0.partition_type,
        start_utc=p0.start_utc,
        end_utc=p0.end_utc,
        count=p0.count - 100,
        first_timestamp_utc=p0.first_timestamp_utc,
        last_timestamp_utc=p0.last_timestamp_utc,
        timestamps_sha256="rehashed_part_sha",
    )
    tampered_split_cand = H40SplitManifest(
        protocol_identity_hash=valid_split.protocol_identity_hash,
        source_manifest_hash=valid_split.source_manifest_hash,
        base_eligible_start_utc=valid_split.base_eligible_start_utc,
        base_eligible_end_utc=valid_split.base_eligible_end_utc,
        base_eligible_count=valid_split.base_eligible_count,
        partitions=tuple(tampered_parts),
        exclusion_counts=valid_split.exclusion_counts,
        is_authoritative=False,
        attestation=None,
    )
    assert btc_rec.receipt is not None and eth_rec.receipt is not None
    tampered_att = H40SplitAttestation.create(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        split_hash=tampered_split_cand.split_hash,
        btc_source_id=btc_rec.source_id,
        btc_locator=btc_rec.locator,
        btc_file_sha256=btc_rec.receipt.file_sha256,
        btc_membership_sha256=btc_rec.receipt.timestamp_membership_hash,
        btc_timestamp_count=btc_rec.receipt.timestamp_count,
        eth_source_id=eth_rec.source_id,
        eth_locator=eth_rec.locator,
        eth_file_sha256=eth_rec.receipt.file_sha256,
        eth_membership_sha256=eth_rec.receipt.timestamp_membership_hash,
        eth_timestamp_count=eth_rec.receipt.timestamp_count,
        is_production_canonical=False,
    )
    tampered_split = H40SplitManifest(
        protocol_identity_hash=valid_split.protocol_identity_hash,
        source_manifest_hash=valid_split.source_manifest_hash,
        base_eligible_start_utc=valid_split.base_eligible_start_utc,
        base_eligible_end_utc=valid_split.base_eligible_end_utc,
        base_eligible_count=valid_split.base_eligible_count,
        partitions=tuple(tampered_parts),
        exclusion_counts=valid_split.exclusion_counts,
        is_authoritative=False,
        attestation=tampered_att,
    )

    with pytest.raises(H40GuardError) as exc_info:
        tampered_split.assert_synthetic_validator_split(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


# ==============================================================================
# 11. Mandatory Adversarial Tests for P1R5
# ==============================================================================

def test_mandatory_1_caller_cannot_pass_policy_to_production_apis() -> None:
    """1. Caller cannot pass authority_policy or test_synthetic to production split APIs."""
    import inspect

    mat_params = inspect.signature(H40SplitManifest.materialize_authoritative).parameters
    assert "authority_policy" not in mat_params
    assert "policy" not in mat_params

    assert_params = inspect.signature(H40SplitManifest.assert_authoritative).parameters
    assert "authority_policy" not in assert_params
    assert "policy" not in assert_params


def test_mandatory_2_synthetic_1h_btc_json_at_canonical_locator_cannot_acquire_production_authority(tmp_path: Path) -> None:
    """2. A synthetic 1h BTC JSON written at canonical BTC locator cannot acquire production authority under H40_PROTOCOL_V1_R2."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)

    # Caller creates synthetic 1h JSON file at canonical locator
    btc_path = tmp_path / "data/research/BTCUSDT/data_manifest.json"
    btc_path.parent.mkdir(parents=True, exist_ok=True)
    btc_path.write_text(json.dumps({
        "symbol": "BTCUSDT",
        "timeframe": "1h",
        "timestamps": full_ts,
    }), encoding="utf-8")

    btc_rec_unverified = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.UNVERIFIED,
        locator="data/research/BTCUSDT/data_manifest.json",
        product="BTCUSDT",
        cadence="1h",
    )
    receipt = validate_source_artifact(tmp_path, btc_rec_unverified, expected_product="BTCUSDT", expected_cadence="1h")
    assert receipt.status == H40SourceStatus.VERIFIED

    btc_rec = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="data/research/BTCUSDT/data_manifest.json",
        product="BTCUSDT",
        cadence="1h",
        row_count=receipt.timestamp_count,
        file_sha256=receipt.file_sha256,
        receipt=receipt,
    )

    # Even though file exists and is valid 1h JSON, production canonical assertion MUST reject it
    with pytest.raises(H40GuardError) as exc_info:
        assert_canonical_source_record(btc_rec, proto.protocol_hash)
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED
    assert "production authority is NOT_TESTABLE" in str(exc_info.value)


def test_mandatory_3_caller_computed_btc_sha_cannot_acquire_production_authority(tmp_path: Path) -> None:
    """3. Same canonical locator + caller-computed new BTC SHA cannot acquire production authority."""
    proto = H40ProtocolIdentity.default()
    new_sha = hashlib.sha256(b"custom_btc_content").hexdigest()

    btc_rec = H40SourceRecord(
        source_id="BTCUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="data/research/BTCUSDT/data_manifest.json",
        product="BTCUSDT",
        cadence="1h",
        row_count=43825,
        file_sha256=new_sha,
        receipt=H40SourceValidationReceipt(
            source_id="BTCUSDT_USD_M_1H",
            locator="data/research/BTCUSDT/data_manifest.json",
            file_sha256=new_sha,
            product="BTCUSDT",
            cadence="1h",
            timestamp_field="open_time_ms",
            timestamp_count=43825,
            first_timestamp_utc="2021-01-31T00:00:00Z",
            last_timestamp_utc="2026-01-31T00:00:00Z",
            duplicate_count=0,
            gap_count=0,
            gaps=(),
            timestamp_membership_hash="m" * 64,
            status=H40SourceStatus.VERIFIED,
        ),
    )

    with pytest.raises(H40GuardError) as exc_info:
        assert_canonical_source_record(btc_rec, proto.protocol_hash)
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_mandatory_4_canonical_source_spec_encodes_authority_availability() -> None:
    """4. Canonical source spec explicitly encodes production_authority_state."""
    proto = H40ProtocolIdentity.default()

    btc_spec = get_canonical_source_spec(proto.protocol_hash, "BTCUSDT_USD_M_1H")
    assert btc_spec.production_authority_state == H40SourceStatus.NOT_TESTABLE
    assert btc_spec.allowed_role == "PRIMARY_SPLIT_INPUT"

    eth_spec = get_canonical_source_spec(proto.protocol_hash, "ETHUSDT_USD_M_1H")
    assert eth_spec.production_authority_state == H40SourceStatus.VERIFIED
    assert eth_spec.allowed_role == "PRIMARY_SPLIT_INPUT"


def test_mandatory_5_eth_canonical_checks_remain_enforced() -> None:
    """5. ETH canonical checks remain strictly enforced."""
    proto = H40ProtocolIdentity.default()

    mock_receipt = H40SourceValidationReceipt(
        source_id="ETHUSDT_USD_M_1H",
        locator="data/research/cross_asset_1h/ETHUSDT.parquet",
        file_sha256="563a1a4d927ec2a007481783be9bd76896e1be57198af80c4b2a30608e124608",
        product="ETHUSDT",
        cadence="1h",
        timestamp_field="open_time_ms",
        timestamp_count=44568,
        first_timestamp_utc="2021-01-01T00:00:00Z",
        last_timestamp_utc="2026-01-31T23:00:00Z",
        duplicate_count=0,
        gap_count=0,
        gaps=(),
        timestamp_membership_hash="m" * 64,
        status=H40SourceStatus.VERIFIED,
    )

    # Wrong archive set SHA
    bad_eth_archive = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="data/research/cross_asset_1h/ETHUSDT.parquet",
        product="ETHUSDT",
        cadence="1h",
        archive_set_sha256="wrong_archive_sha",
        receipt=mock_receipt,
    )
    with pytest.raises(H40GuardError) as exc_archive:
        assert_canonical_source_record(bad_eth_archive, proto.protocol_hash)
    assert exc_archive.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH

    # Wrong reference file SHA
    bad_eth_file = H40SourceRecord(
        source_id="ETHUSDT_USD_M_1H",
        status=H40SourceStatus.VERIFIED,
        locator="data/research/cross_asset_1h/ETHUSDT.parquet",
        product="ETHUSDT",
        cadence="1h",
        archive_set_sha256="1efde37a765de90e33fd509bd1bcb729351beafa79314f684b3558665b19226c",
        file_sha256="0" * 64,
        receipt=mock_receipt,
    )
    with pytest.raises(H40GuardError) as exc_file:
        assert_canonical_source_record(bad_eth_file, proto.protocol_hash)
    assert exc_file.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


def test_mandatory_10_synthetic_validator_output_remains_strictly_non_authoritative(tmp_path: Path) -> None:
    """10. Synthetic validator split output is strictly non-authoritative and rejected by assert_authoritative."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    src_manifest, _, _ = _setup_synthetic_source_manifest(tmp_path, proto.protocol_hash, full_ts, full_ts)

    synth_split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    # Verified invariants
    assert synth_split.is_authoritative is False
    assert synth_split.attestation is not None
    assert synth_split.attestation.is_production_canonical is False

    # Synthetic validator assertion succeeds
    synth_split.assert_synthetic_validator_split(
        source_manifest=src_manifest,
        repo_root=tmp_path,
    )

    # Production assertion strictly fails
    with pytest.raises(H40GuardError) as exc_auth:
        synth_split.assert_authoritative(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_auth.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED

    # Forged is_authoritative=True still rejected because is_production_canonical is False
    forged_auth = H40SplitManifest(
        protocol_identity_hash=synth_split.protocol_identity_hash,
        source_manifest_hash=synth_split.source_manifest_hash,
        base_eligible_start_utc=synth_split.base_eligible_start_utc,
        base_eligible_end_utc=synth_split.base_eligible_end_utc,
        base_eligible_count=synth_split.base_eligible_count,
        partitions=synth_split.partitions,
        exclusion_counts=synth_split.exclusion_counts,
        is_authoritative=True,
        attestation=synth_split.attestation,
    )
    with pytest.raises(H40GuardError) as exc_forged:
        forged_auth.assert_authoritative(
            source_manifest=src_manifest,
            repo_root=tmp_path,
        )
    assert exc_forged.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED
    assert "TEST_ONLY" in str(exc_forged.value)


def test_mandatory_11_hermetic_scaffold_passes_without_repo_artifacts(tmp_path: Path) -> None:
    """11. Scaffold tests run hermetically in isolated tmp_path without requiring repo data."""
    proto = H40ProtocolIdentity.default()
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)

    isolated_root = tmp_path / "hermetic_sandbox"
    isolated_root.mkdir()

    src_manifest, _, _ = _setup_synthetic_source_manifest(isolated_root, proto.protocol_hash, full_ts, full_ts)
    split = H40SplitManifest.materialize_synthetic_validator_split(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest=src_manifest,
        repo_root=isolated_root,
    )
    split.assert_synthetic_validator_split(
        source_manifest=src_manifest,
        repo_root=isolated_root,
    )
    assert split.base_eligible_count == BASE_ELIGIBLE_COUNT
