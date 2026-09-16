"""Adversarial tests for H40-P1 Data, Split, and Protocol-Identity Scaffold.

Verifies strict pre-outcome immutability, canonical hashing, source access guards,
half-open split boundaries, 168-slot ledger budget cap, and fail-closed protections.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from btc_quant_agent.h40 import (
    ALLOWED_DEPTH_TWO_PAIRS,
    BASE_ELIGIBLE_COUNT,
    BASE_ELIGIBLE_END_UTC,
    BASE_ELIGIBLE_START_UTC,
    MAX_CONFIGURATION_SLOTS,
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
    H40SplitManifest,
    materialize_verified_manifest,
    validate_source_artifact,
)
from btc_quant_agent.h40.split_manifest import generate_hourly_range
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

    # ETHUSDT.parquet and official derivatives hourly_inputs.parquet exist locally and are verified
    eth = manifest.get_source("ETHUSDT_USD_M_1H")
    assert eth.status == H40SourceStatus.VERIFIED
    assert eth.row_count == 44568
    assert eth.receipt is not None
    assert eth.receipt.status == H40SourceStatus.VERIFIED

    deriv = manifest.get_source("BTCUSDT_OFFICIAL_DERIVATIVES")
    assert deriv.status == H40SourceStatus.VERIFIED
    assert deriv.row_count == 44568
    assert deriv.receipt is not None
    assert deriv.receipt.status == H40SourceStatus.VERIFIED


# ==============================================================================
# 3. Split Manifest & Materialized Authority Tests (Repair C)
# ==============================================================================

def test_split_manifest_preregistered_schedule_is_not_authoritative() -> None:
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
        split_manifest.assert_authoritative()
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_materialized_split_authoritative_with_full_timestamps() -> None:
    """Authoritative split materialized from verified continuous timestamps matches exact partition counts."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)

    # Generate full 44,568 hours from 2021-01-01T00:00:00Z to 2026-01-31T23:00:00Z
    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    assert len(full_ts) == 44568

    split = H40SplitManifest.build_materialized(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        btc_timestamps=full_ts,
        eth_timestamps=full_ts,
    )

    assert split.is_authoritative
    split.assert_authoritative()

    assert split.base_eligible_count == BASE_ELIGIBLE_COUNT
    assert split.get_partition("WF1_TRAIN").count == 15312
    assert split.get_partition("CONFIRMATION_HOLDOUT").count == 8737
    assert split.exclusion_counts[H40ReasonCode.LOOKBACK_RESERVED.value] == 720
    assert split.exclusion_counts[H40ReasonCode.HORIZON_TRUNCATED.value] == 23
    assert split.exclusion_counts[H40ReasonCode.PURGE_BOUNDARY.value] == 216
    assert split.exclusion_counts[H40ReasonCode.SOURCE_GAP.value] == 0


def test_pooled_btc_eth_intersection_drops_missing_timestamps() -> None:
    """Timestamps present in BTC but missing in ETH (or vice versa) are dropped from the common base set."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)

    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    # Remove one timestamp from ETH
    missing_eth_ts = "2021-06-15T12:00:00Z"
    eth_ts = [t for t in full_ts if t != missing_eth_ts]

    split = H40SplitManifest.build_materialized(
        protocol_identity_hash=proto.protocol_hash,
        source_manifest_hash=src_manifest.manifest_hash,
        btc_timestamps=full_ts,
        eth_timestamps=eth_ts,
    )

    # Missing hour in ETH drops from the pooled intersection
    wf1_train = split.get_partition("WF1_TRAIN")
    assert wf1_train.count == 15311  # was 15312
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

    # Drop one hour in WF2_CALIBRATION (e.g. 2023-06-01T10:00:00Z)
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

    # 23 timestamps from 2026-01-31T01:00:00Z to 2026-01-31T23:00:00Z lack 24h future coverage
    assert split.exclusion_counts[H40ReasonCode.HORIZON_TRUNCATED.value] == 23
    conf_holdout = split.get_partition("CONFIRMATION_HOLDOUT")
    assert conf_holdout.count == 8737


def test_no_boundary_shifts_occur_after_gaps() -> None:
    """Gaps decrease partition counts but partition boundaries remain strictly fixed."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)

    full_ts = generate_hourly_range("2021-01-01T00:00:00Z", "2026-01-31T23:00:00Z", inclusive_end=True)
    # Remove 5 hours inside WF1_TRAIN
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


def test_builder_cannot_return_authoritative_split_from_constants_alone() -> None:
    """Default or preregistered schedule builder cannot claim authoritative verified split status."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    split_default = H40SplitManifest.build_default(proto.protocol_hash, src_manifest.manifest_hash)

    assert not split_default.is_authoritative
    with pytest.raises(H40GuardError) as exc_info:
        split_default.assert_authoritative()
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED

    # build_materialized without timestamp inputs fails closed
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

    # Check temporal boundaries
    assert conf_train.end_utc == conf_purge.start_utc
    assert conf_purge.end_utc == conf_holdout.start_utc
    assert conf_holdout.start_utc == "2025-02-01T00:00:00Z"

    # Verify purge is exactly 24 hours
    assert conf_purge.count == 24


def test_split_manifest_hash_changes_on_membership_tampering() -> None:
    """Altering partition timestamp count or range alters the split manifest hash."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    split_manifest = H40SplitManifest.build_preregistered_schedule(proto.protocol_hash, src_manifest.manifest_hash)
    base_hash = split_manifest.split_hash

    # Craft altered partitions tuple
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
