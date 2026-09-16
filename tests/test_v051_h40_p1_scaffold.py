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
    H40SplitManifest,
)
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
# 2. Unprotected Source-Authority Manifest Tests
# ==============================================================================

def test_source_manifest_default_inventory() -> None:
    """Default manifest inventories verified, unverified, diagnostic, and forbidden sources."""
    proto = H40ProtocolIdentity.default()
    manifest = H40SourceManifest.build_default(proto.protocol_hash)

    # Check verified sources
    btc_kline = manifest.get_source("BTCUSDT_USD_M_1H")
    assert btc_kline.status == H40SourceStatus.VERIFIED
    eth_kline = manifest.get_source("ETHUSDT_USD_M_1H")
    assert eth_kline.status == H40SourceStatus.VERIFIED
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


def test_source_manifest_detects_hash_tampering(tmp_path: Path) -> None:
    """Tampering with source file content raises SOURCE_HASH_MISMATCH."""
    proto = H40ProtocolIdentity.default()
    test_file = tmp_path / "test_kline.parquet"
    test_file.write_bytes(b"original data")
    orig_hash = hashlib.sha256(b"original data").hexdigest()

    rec = H40SourceRecord(
        source_id="CUSTOM_SOURCE",
        status=H40SourceStatus.VERIFIED,
        locator="test_kline.parquet",
        file_sha256=orig_hash,
    )
    manifest = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(rec,),
    )

    # Initial check passes
    manifest.verify_file_integrity(tmp_path, "CUSTOM_SOURCE")

    # Tamper with file
    test_file.write_bytes(b"tampered data")
    with pytest.raises(H40GuardError) as exc_info:
        manifest.verify_file_integrity(tmp_path, "CUSTOM_SOURCE")
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


def test_source_manifest_detects_missing_file(tmp_path: Path) -> None:
    """Missing source file raises SOURCE_MISSING."""
    proto = H40ProtocolIdentity.default()
    rec = H40SourceRecord(
        source_id="MISSING_SOURCE",
        status=H40SourceStatus.VERIFIED,
        locator="non_existent.parquet",
        file_sha256="abc",
    )
    manifest = H40SourceManifest(
        protocol_identity_hash=proto.protocol_hash,
        sources=(rec,),
    )
    with pytest.raises(H40GuardError) as exc_info:
        manifest.verify_file_integrity(tmp_path, "MISSING_SOURCE")
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_MISSING


# ==============================================================================
# 3. Split Manifest Tests
# ==============================================================================

def test_split_manifest_counts_and_boundaries() -> None:
    """Split manifest calculates exact 43,825 timestamps and verifies half-open partition counts."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    split_manifest = H40SplitManifest.build_default(proto.protocol_hash, src_manifest.manifest_hash)

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


def test_confirmation_timestamps_strictly_isolated() -> None:
    """Confirmation holdout timestamps do not overlap with any training or calibration partition."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    split_manifest = H40SplitManifest.build_default(proto.protocol_hash, src_manifest.manifest_hash)

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
    split_manifest = H40SplitManifest.build_default(proto.protocol_hash, src_manifest.manifest_hash)
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
# 5. Access Guards & Lifecycle Tests
# ==============================================================================

def test_confirmation_guard_metadata_vs_outcomes() -> None:
    """Confirmation guard permits metadata inspection but strictly blocks outcome values."""
    guard = H40ConfirmationGuard(is_confirmation_ready=False)
    # Metadata access succeeds
    guard.assert_metadata_accessible()

    # Outcome / return / price evaluation fails closed
    with pytest.raises(H40GuardError) as exc_info:
        guard.assert_outcomes_accessible()
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_protected_surface_guard_blocks_h39_and_final_holdout() -> None:
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
# 6. Adversarial Serialization & Re-Hashing Tests
# ==============================================================================

def test_adversarial_serialized_manifest_tampering() -> None:
    """Crafting or tampering with a serialized JSON manifest and attempting to verify causes mismatch."""
    proto = H40ProtocolIdentity.default()
    src_manifest = H40SourceManifest.build_default(proto.protocol_hash)
    original_dict = src_manifest.to_dict()
    original_hash = src_manifest.manifest_hash

    # Attacker modifies JSON serialized payload to forge status of FORBIDDEN source
    tampered_dict = copy.deepcopy(original_dict)
    for src in tampered_dict["sources"]:
        if src["source_id"] == "H39_PROTECTED":
            src["status"] = "VERIFIED"  # Attempt to forge forbidden source to verified

    tampered_canonical_json = canonical_json(tampered_dict)
    assert tampered_canonical_json
    tampered_hash = canonical_sha256(tampered_dict)

    # Hashes cannot match
    assert tampered_hash != original_hash

    # Reconstructed manifest will carry the new hash and fail any verification against preregistered identity
    reconstructed_sources = tuple(H40SourceRecord.from_dict(s) for s in tampered_dict["sources"])
    reconstructed_manifest = H40SourceManifest(
        protocol_identity_hash=tampered_dict["protocol_identity_hash"],
        sources=reconstructed_sources,
    )
    assert reconstructed_manifest.manifest_hash == tampered_hash
    assert reconstructed_manifest.manifest_hash != original_hash
