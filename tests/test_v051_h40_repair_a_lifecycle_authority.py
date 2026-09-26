"""Mandatory deterministic adversarial suite for V0.5.1 H40 Repair A.

Covers all 48 acceptance criteria:
1-6:   V5 identity and hash derivation
7-15:  H40P3ControllerAuthority
16-25: H40DiscoveryRunGrant
26-31: H40DiscoveryAuthorizationReceipt (V3)
32-38: Persistence Context V2 and Cold Restore
39-44: Service Lifetime and Transition Enforcement
45-48: Protected and Frozen Behavior
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import btc_quant_agent.h40.lifecycle_authority as lifecycle_authority_module
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
    EXPECTED_PROTOCOL_AUTHORITY_HASH,
    EXPECTED_SEMANTIC_ROOT_HASH,
    EXPECTED_STRUCTURAL_LEDGER_HASH,
    H40ConfirmationGuard,
    H40DiscoveryAuthorizationReceipt,
    H40DiscoveryAuthorizationReceiptV2,
    H40DiscoveryRunGrant,
    H40GuardError,
    H40LifecycleArtifactStore,
    H40LifecycleAuthorityService,
    H40LifecycleImplementationAuthority,
    H40LifecyclePersistenceContext,
    H40LifecyclePersistenceContextV1,
    H40LifecycleState,
    H40LifecycleStateMachine,
    H40P3ControllerAuthority,
    H40ProtectedSurfaceGuard,
    H40ReasonCode,
    H40RequiredTestCIEvidenceIdentity,
    H40RunAuthority,
    H40RuntimeSnapshotSeal,
    H40SplitManifest,
    H40SyntheticAuthorityResolver,
    H40SyntheticEvidenceVerifier,
    compute_lifecycle_child_hashes,
    compute_lifecycle_governance_authority_hash,
    compute_lifecycle_semantic_root_hash,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    lifecycle_governance_authority_object,
    materialize_h40_search_space_production,
)
from btc_quant_agent.research_contract.canonical import canonical_json

TS = "2026-09-23T00:00:00Z"


def _hash(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _make_dummy_impl_authority(
    gov_hash: str = EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
    commit_sha: str = "d73e8984446f933059b978e36c4cabd55de517aa",
) -> H40LifecycleImplementationAuthority:
    evidence_id = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path="evidence/v0.5/h40/V0.5.1_H40_FINAL_REACCEPTANCE_EVIDENCE_d73e898.json",
        evidence_manifest_sha256="5cd591ef7f3f43c7897711ab4e75cb158ac048d328e1f8b0dac28a0a6bcb6540",
        tested_commit_sha=commit_sha,
    )
    return H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=gov_hash,
        f01_implementation_acceptance_artifact_path="reviews/v0.5/V0.5.1_H40_FINAL_EXACT_SHA_REACCEPTANCE_CONTROLLER_ACCEPTANCE.md",
        f01_implementation_acceptance_commit_sha="0cbb20a7806f2336864e430910bf6a4ff4a99df9",
        f01_implementation_commit_sha=commit_sha,
        required_test_ci_evidence_identity=evidence_id,
        schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
    )


def _make_dummy_controller_authority(
    impl: H40LifecycleImplementationAuthority | None = None,
    commit_sha: str = "2229d44c5cc9b88ba515d0b2931d20f05936c7e8",
) -> H40P3ControllerAuthority:
    if impl is None:
        impl = _make_dummy_impl_authority()
    return H40P3ControllerAuthority(
        schema_id="H40_P3_CONTROLLER_AUTHORITY_V1",
        authorization_scope="H40_P3_DISCOVERY_V1",
        controller_acceptance_artifact_path="reviews/v0.5/V0.5.1_H40_PRE_DISCOVERY_REPAIR_CONTRACT_CONTROLLER_ACCEPTANCE.md",
        controller_acceptance_commit_sha=commit_sha,
        protocol_authority_hash=EXPECTED_PROTOCOL_AUTHORITY_HASH,
        scientific_semantic_root_hash=EXPECTED_SEMANTIC_ROOT_HASH,
        structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
        lifecycle_semantic_root_hash=EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH,
        lifecycle_governance_authority_hash=EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
        lifecycle_implementation_authority_hash=impl.lifecycle_implementation_authority_hash,
        discovery_provenance_contract_hash=DISCOVERY_PROVENANCE_CONTRACT_HASH,
        discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        permitted_partitions=("WF1_TRAIN", "WF1_CALIBRATION"),
        transition_source_state="H40_P1_SCAFFOLDED",
        transition_target_state="H40_DISCOVERY",
        execution_disabled=True,
    )


def _make_dummy_seal() -> H40RuntimeSnapshotSeal:
    expected, _registered_count, not_testable_count, snapshot_hash = (
        lifecycle_authority_module._accepted_production_roster()
    )
    split = H40SplitManifest(
        protocol_identity_hash=EXPECTED_PROTOCOL_AUTHORITY_HASH,
        source_manifest_hash=_hash("source"),
        base_eligible_start_utc="2021-01-31T00:00:00Z",
        base_eligible_end_utc="2026-01-31T00:00:00Z",
        base_eligible_count=2,
        partitions=(),
        exclusion_counts={},
    )
    return H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=snapshot_hash,
        source_manifest_hash=_hash("source"),
        split_manifest_hash=split.split_hash,
        split_attestation_hash=_hash("attestation"),
        roster=expected,
        not_testable_slot_count=not_testable_count,
    )


def _make_dummy_run_grant(
    ctrl: H40P3ControllerAuthority,
    run: H40RunAuthority,
    seal: H40RuntimeSnapshotSeal,
) -> H40DiscoveryRunGrant:
    return H40DiscoveryRunGrant.from_controller_and_run(
        controller_authority=ctrl,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
    )


# =============================================================================
# 1-6: V5 Identity and Hash Derivation
# =============================================================================


def test_01_child_hash_computation_matches_exact_v5_values() -> None:
    child_hashes = compute_lifecycle_child_hashes()
    assert len(child_hashes) == 9
    assert child_hashes == EXPECTED_LIFECYCLE_CHILD_HASHES


def test_02_semantic_root_hash_computation_equals_v5() -> None:
    child_hashes = compute_lifecycle_child_hashes()
    assert child_hashes["discovery_authorization_receipt_contract"] == (
        "3dd91827d4a26441bd5218dc299f196841c471eb60f20e03881d2ad56ce36898"
    )
    assert child_hashes["transition_matrix_contract"] == (
        "bea7b0593251204bbc9138c325f1c9f10ccf7a9b8df60f10bf991377e0ced42d"
    )
    assert child_hashes["persistence_replay_contract"] == (
        "51e4fe6155d388c076dd1788a100265eb17b232300481a3fbcf00150f1432de1"
    )


def test_03_six_expected_children_remain_exact() -> None:
    child_hashes = compute_lifecycle_child_hashes()
    assert child_hashes["candidate_lock_receipt_contract"] == (
        "96756dfebab636baa1abb33364e307d99d90a61572b813c6a60504283d3d42df"
    )
    assert child_hashes["wf_validation_receipt_contract"] == (
        "bb5698a85daec1a5b9dcd169bde3d575befe8c0a1d73c2e87136cf35afb4001b"
    )
    assert child_hashes["confirmation_ready_receipt_contract"] == (
        "7ab0ae0c8acb17340eccaa2bb737a5300e679b8de7497a539bdc44e93d3109be"
    )
    assert child_hashes["termination_receipt_contract"] == (
        "b45c7021db1c63a447ddb22a1f9cb787ce71a5048c824ce38d40f19f755ecb48"
    )
    assert child_hashes["runtime_snapshot_seal_contract"] == (
        "76a0732742707c78f65da26263076bed7b586ea67d4f5ddd2dac33761e37e612"
    )
    assert child_hashes["f02_boundary_contract"] == (
        "5678d8bd6b83bb69e1a1ad2cf78af8ddbaece625a5a34b7018b0a5e6368756f4"
    )


def test_04_governance_authority_schema_id_is_v5() -> None:
    sem_root = compute_lifecycle_semantic_root_hash()
    assert sem_root == "36cbda530352cffaa475bd835b3b629df47351ca284e09bdf31a8fc884d48b4b"
    assert sem_root == EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH


def test_05_governance_v5_equals_expected() -> None:
    gov_hash = compute_lifecycle_governance_authority_hash()
    assert gov_hash == "bb367f2af726be105bddf42636c97652402014c8a671d43ab81b1964c258e5cf"
    assert gov_hash == EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH


def test_06_discovery_provenance_contract_hash_exact() -> None:
    obj = lifecycle_governance_authority_object()
    assert obj["schema_id"] == "H40_LIFECYCLE_GOVERNANCE_AUTHORITY_V5"
    assert obj["lifecycle_semantic_root_hash"] == EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH
    assert obj["pre_discovery_repair_contract_acceptance_identity"]["commit_sha"] == (
        "2229d44c5cc9b88ba515d0b2931d20f05936c7e8"
    )
    assert obj["pre_discovery_repair_contract_acceptance_identity"]["artifact_path"] == (
        "reviews/v0.5/V0.5.1_H40_PRE_DISCOVERY_REPAIR_CONTRACT_CONTROLLER_ACCEPTANCE.md"
    )
    assert DISCOVERY_PROVENANCE_CONTRACT_HASH == "31fc3930e44149e6b3af54ddd3b11c630f95cbbd3f152b3d0d5e614690dcf7ae"


# =============================================================================
# 7-15: H40P3ControllerAuthority
# =============================================================================


def test_07_controller_authority_canonical_json_and_hash_fixture() -> None:
    ctrl = _make_dummy_controller_authority()
    d = ctrl.to_dict()
    assert d["schema_id"] == "H40_P3_CONTROLLER_AUTHORITY_V1"
    assert len(ctrl.controller_authority_hash) == 64
    assert ctrl.controller_authority_hash == hashlib.sha256(canonical_json(d).encode("utf-8")).hexdigest()


def test_08_controller_authority_mutation_changes_hash() -> None:
    ctrl = _make_dummy_controller_authority()
    base_hash = ctrl.controller_authority_hash
    d = ctrl.to_dict()
    d["controller_acceptance_commit_sha"] = "1" * 40
    mutated = H40P3ControllerAuthority.from_dict(d)
    assert mutated.controller_authority_hash != base_hash


def test_09_controller_authority_wrong_schema_rejected() -> None:
    ctrl = _make_dummy_controller_authority()
    d = ctrl.to_dict()
    d["schema_id"] = "WRONG_SCHEMA_V1"
    with pytest.raises(ValueError, match="schema"):
        H40P3ControllerAuthority.from_dict(d)


def test_10_controller_authority_non_hex_or_bad_length_hash_rejected() -> None:
    ctrl = _make_dummy_controller_authority()
    d = ctrl.to_dict()
    d["protocol_authority_hash"] = "not-a-hash"
    with pytest.raises(ValueError, match="must be an exact lowercase SHA-256 hex digest"):
        H40P3ControllerAuthority.from_dict(d)

    d2 = ctrl.to_dict()
    d2["protocol_authority_hash"] = "A" * 64
    with pytest.raises(ValueError, match="must be an exact lowercase SHA-256 hex digest"):
        H40P3ControllerAuthority.from_dict(d2)


def test_11_controller_authority_negative_or_non_integer_sequence_rejected() -> None:
    ctrl = _make_dummy_controller_authority()
    d = ctrl.to_dict()
    d["execution_disabled"] = "not-a-bool"
    with pytest.raises(TypeError, match="must be boolean"):
        H40P3ControllerAuthority.from_dict(d)


def test_12_controller_authority_non_utc_or_non_z_timestamp_rejected() -> None:
    ctrl = _make_dummy_controller_authority()
    d = ctrl.to_dict()
    d["permitted_partitions"] = "not-a-tuple"
    with pytest.raises(TypeError, match="must be a sequence"):
        H40P3ControllerAuthority.from_dict(d)


def test_13_controller_authority_governance_hash_mismatch_rejected() -> None:
    ctrl = _make_dummy_controller_authority()
    d = ctrl.to_dict()
    d["lifecycle_governance_authority_hash"] = "0" * 64
    with pytest.raises(ValueError, match="lifecycle_governance_authority_hash mismatch"):
        H40P3ControllerAuthority.from_dict(d)


def test_14_controller_authority_round_trip_serialization() -> None:
    ctrl = _make_dummy_controller_authority()
    d = ctrl.to_dict()
    restored = H40P3ControllerAuthority.from_dict(d)
    assert restored == ctrl
    assert restored.controller_authority_hash == ctrl.controller_authority_hash


def test_15_controller_authority_missing_required_field_rejected() -> None:
    ctrl = _make_dummy_controller_authority()
    d = ctrl.to_dict()
    del d["authorization_scope"]
    with pytest.raises(ValueError, match="schema mismatch"):
        H40P3ControllerAuthority.from_dict(d)


# =============================================================================
# 16-25: H40DiscoveryRunGrant
# =============================================================================


def test_16_run_grant_canonical_json_and_hash_fixture() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)
    d = grant.to_dict()
    assert d["schema_id"] == "H40_DISCOVERY_RUN_GRANT_V1"
    assert len(grant.discovery_run_grant_hash) == 64
    assert grant.discovery_run_grant_hash == hashlib.sha256(canonical_json(d).encode("utf-8")).hexdigest()


def test_17_run_grant_mutation_changes_hash() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)
    base_hash = grant.discovery_run_grant_hash
    d = grant.to_dict()
    d["authorized_at_utc"] = "2026-09-24T00:00:00Z"
    mutated = H40DiscoveryRunGrant.from_dict(d)
    assert mutated.discovery_run_grant_hash != base_hash


def test_18_run_grant_wrong_schema_rejected() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)
    d = grant.to_dict()
    d["schema_id"] = "WRONG_SCHEMA_V1"
    with pytest.raises(ValueError, match="schema"):
        H40DiscoveryRunGrant.from_dict(d)


def test_19_run_grant_non_hex_or_bad_length_hash_rejected() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)
    d = grant.to_dict()
    d["run_authority_id"] = "bad"
    with pytest.raises(ValueError, match="must be an exact lowercase SHA-256 hex digest"):
        H40DiscoveryRunGrant.from_dict(d)


def test_20_run_grant_split_attestation_mismatch_fails() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    bad_run = copy.copy(run)
    object.__setattr__(bad_run, "split_attestation_hash", "f" * 64)
    with pytest.raises(H40GuardError, match="run authority does not match"):
        H40DiscoveryRunGrant.from_controller_and_run(
            controller_authority=ctrl,
            run_authority=bad_run,
            seal=seal,
            authorized_at_utc=TS,
        )


def test_21_run_grant_roster_hash_mismatch_fails() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    bad_run = copy.copy(run)
    object.__setattr__(bad_run, "sealed_registered_roster_hash", "e" * 64)
    with pytest.raises(H40GuardError, match="run authority does not match"):
        H40DiscoveryRunGrant.from_controller_and_run(
            controller_authority=ctrl,
            run_authority=bad_run,
            seal=seal,
            authorized_at_utc=TS,
        )


def test_22_run_grant_controller_authority_hash_mismatch_fails() -> None:
    impl = _make_dummy_impl_authority()
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    other_impl = _make_dummy_impl_authority(commit_sha="0" * 40)
    bad_ctrl = _make_dummy_controller_authority(impl=other_impl)
    with pytest.raises(H40GuardError, match="controller authority implementation hash mismatch"):
        H40DiscoveryRunGrant.from_controller_and_run(
            controller_authority=bad_ctrl,
            run_authority=run,
            seal=seal,
            authorized_at_utc=TS,
        )


def test_23_run_grant_negative_or_non_integer_sequence_rejected() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)
    d = grant.to_dict()
    d["execution_disabled"] = "bad-type"
    with pytest.raises(TypeError, match="must be boolean"):
        H40DiscoveryRunGrant.from_dict(d)


def test_24_run_grant_round_trip_serialization() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)
    d = grant.to_dict()
    restored = H40DiscoveryRunGrant.from_dict(d)
    assert restored == grant
    assert restored.discovery_run_grant_hash == grant.discovery_run_grant_hash


def test_25_run_grant_missing_required_field_rejected() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)
    d = grant.to_dict()
    del d["discovery_provenance_contract_hash"]
    with pytest.raises(ValueError, match="schema mismatch"):
        H40DiscoveryRunGrant.from_dict(d)


# =============================================================================
# 26-31: H40DiscoveryAuthorizationReceipt (V3)
# =============================================================================


def test_26_discovery_receipt_schema_id_is_v3() -> None:
    receipt = H40DiscoveryAuthorizationReceipt(
        authorized_at_utc=TS,
        controller_authority_hash=_hash("ctrl"),
        discovery_run_grant_hash=_hash("grant"),
        discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        execution_disabled=True,
        lifecycle_governance_authority_hash=_hash("gov"),
        lifecycle_implementation_authority_hash=_hash("impl"),
        materialized_run_authority_hash=_hash("run"),
        not_testable_slot_count=150,
        protocol_authority_hash=EXPECTED_PROTOCOL_AUTHORITY_HASH,
        registered_slot_count=18,
        run_authority_id=_hash("run_id"),
        sealed_registered_roster_hash=_hash("roster"),
        semantic_root_hash=EXPECTED_SEMANTIC_ROOT_HASH,
        source_manifest_hash=_hash("source"),
        split_attestation_hash=_hash("attest"),
        split_manifest_hash=_hash("split"),
        structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
        total_slot_count=168,
    )
    d = receipt.to_dict()
    assert d["receipt_schema_id"] == "H40_RECEIPT_DISCOVERY_AUTH_V3"


def test_27_discovery_receipt_requires_controller_and_run_grant_hashes() -> None:
    with pytest.raises(TypeError):
        H40DiscoveryAuthorizationReceipt(  # type: ignore[call-arg]
            authorized_at_utc=TS,
            discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
            execution_disabled=True,
            lifecycle_governance_authority_hash=_hash("gov"),
            lifecycle_implementation_authority_hash=_hash("impl"),
            materialized_run_authority_hash=_hash("run"),
            not_testable_slot_count=150,
            protocol_authority_hash=EXPECTED_PROTOCOL_AUTHORITY_HASH,
            registered_slot_count=18,
            run_authority_id=_hash("run_id"),
            sealed_registered_roster_hash=_hash("roster"),
            semantic_root_hash=EXPECTED_SEMANTIC_ROOT_HASH,
            source_manifest_hash=_hash("source"),
            split_attestation_hash=_hash("attest"),
            split_manifest_hash=_hash("split"),
            structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
            total_slot_count=168,
        )


def test_28_discovery_receipt_hash_mutation_changes_receipt_sha256() -> None:
    receipt = H40DiscoveryAuthorizationReceipt(
        authorized_at_utc=TS,
        controller_authority_hash=_hash("ctrl1"),
        discovery_run_grant_hash=_hash("grant1"),
        discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        execution_disabled=True,
        lifecycle_governance_authority_hash=_hash("gov"),
        lifecycle_implementation_authority_hash=_hash("impl"),
        materialized_run_authority_hash=_hash("run"),
        not_testable_slot_count=150,
        protocol_authority_hash=EXPECTED_PROTOCOL_AUTHORITY_HASH,
        registered_slot_count=18,
        run_authority_id=_hash("run_id"),
        sealed_registered_roster_hash=_hash("roster"),
        semantic_root_hash=EXPECTED_SEMANTIC_ROOT_HASH,
        source_manifest_hash=_hash("source"),
        split_attestation_hash=_hash("attest"),
        split_manifest_hash=_hash("split"),
        structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
        total_slot_count=168,
    )
    base_hash = receipt.receipt_sha256

    mutated_ctrl = copy.copy(receipt)
    object.__setattr__(mutated_ctrl, "controller_authority_hash", _hash("ctrl2"))
    assert mutated_ctrl.receipt_sha256 != base_hash

    mutated_grant = copy.copy(receipt)
    object.__setattr__(mutated_grant, "discovery_run_grant_hash", _hash("grant2"))
    assert mutated_grant.receipt_sha256 != base_hash


def test_29_discovery_receipt_round_trip_serialization_preserves_all_21_fields() -> None:
    receipt = H40DiscoveryAuthorizationReceipt(
        authorized_at_utc=TS,
        controller_authority_hash=_hash("ctrl"),
        discovery_run_grant_hash=_hash("grant"),
        discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        execution_disabled=True,
        lifecycle_governance_authority_hash=_hash("gov"),
        lifecycle_implementation_authority_hash=_hash("impl"),
        materialized_run_authority_hash=_hash("run"),
        not_testable_slot_count=150,
        protocol_authority_hash=EXPECTED_PROTOCOL_AUTHORITY_HASH,
        registered_slot_count=18,
        run_authority_id=_hash("run_id"),
        sealed_registered_roster_hash=_hash("roster"),
        semantic_root_hash=EXPECTED_SEMANTIC_ROOT_HASH,
        source_manifest_hash=_hash("source"),
        split_attestation_hash=_hash("attest"),
        split_manifest_hash=_hash("split"),
        structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
        total_slot_count=168,
        upstream_receipt_hash=None,
    )
    d = receipt.to_dict()
    assert len(d) == 21
    restored = H40DiscoveryAuthorizationReceipt.from_dict(d)
    assert restored == receipt
    assert restored.receipt_sha256 == receipt.receipt_sha256


def test_30_discovery_v2_receipt_cannot_be_created_through_current_constructor() -> None:
    d = {
        "authorized_at_utc": TS,
        "discovery_selection_correction_contract_hash": DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        "execution_disabled": True,
        "lifecycle_governance_authority_hash": _hash("gov"),
        "lifecycle_implementation_authority_hash": _hash("impl"),
        "materialized_run_authority_hash": _hash("run"),
        "not_testable_slot_count": 150,
        "protocol_authority_hash": EXPECTED_PROTOCOL_AUTHORITY_HASH,
        "receipt_schema_id": "H40_RECEIPT_DISCOVERY_AUTH_V2",
        "registered_slot_count": 18,
        "run_authority_id": _hash("run"),
        "sealed_registered_roster_hash": _hash("roster"),
        "semantic_root_hash": EXPECTED_SEMANTIC_ROOT_HASH,
        "source_manifest_hash": _hash("source"),
        "split_attestation_hash": _hash("attest"),
        "split_manifest_hash": _hash("split"),
        "structural_ledger_hash": EXPECTED_STRUCTURAL_LEDGER_HASH,
        "total_slot_count": 168,
        "upstream_receipt_hash": None,
    }
    with pytest.raises(ValueError, match="schema mismatch"):
        H40DiscoveryAuthorizationReceipt.from_dict(d)


def test_31_discovery_v2_receipt_parsed_through_legacy_parser() -> None:
    d = {
        "authorized_at_utc": TS,
        "discovery_selection_correction_contract_hash": DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        "execution_disabled": True,
        "lifecycle_governance_authority_hash": _hash("gov"),
        "lifecycle_implementation_authority_hash": _hash("impl"),
        "materialized_run_authority_hash": _hash("run"),
        "not_testable_slot_count": 150,
        "protocol_authority_hash": EXPECTED_PROTOCOL_AUTHORITY_HASH,
        "receipt_schema_id": "H40_RECEIPT_DISCOVERY_AUTH_V2",
        "registered_slot_count": 18,
        "run_authority_id": _hash("run"),
        "sealed_registered_roster_hash": _hash("roster"),
        "semantic_root_hash": EXPECTED_SEMANTIC_ROOT_HASH,
        "source_manifest_hash": _hash("source"),
        "split_attestation_hash": _hash("attest"),
        "split_manifest_hash": _hash("split"),
        "structural_ledger_hash": EXPECTED_STRUCTURAL_LEDGER_HASH,
        "total_slot_count": 168,
        "upstream_receipt_hash": None,
    }
    v2 = H40DiscoveryAuthorizationReceiptV2.from_dict(d)
    assert isinstance(v2, H40DiscoveryAuthorizationReceiptV2)
    assert v2.receipt_schema_id == "H40_RECEIPT_DISCOVERY_AUTH_V2"


# =============================================================================
# 32-38: Persistence Context V2 and Cold Restore
# =============================================================================


def test_32_persistence_context_schema_id_is_v2() -> None:
    ctx = H40LifecyclePersistenceContext(
        implementation_authority_hash=_hash("impl"),
        controller_authority_hash=_hash("ctrl"),
        discovery_run_grant_hash=_hash("grant"),
        run_authority_id=_hash("run"),
        runtime_seal_hash=_hash("seal"),
        split_authority_hash=_hash("split"),
    )
    assert ctx.schema_id == "H40_LIFECYCLE_PERSISTENCE_CONTEXT_V2"


def test_33_persistence_context_contains_controller_and_grant_hashes() -> None:
    ctx = H40LifecyclePersistenceContext(
        implementation_authority_hash=_hash("impl"),
        controller_authority_hash=_hash("ctrl"),
        discovery_run_grant_hash=_hash("grant"),
        run_authority_id=_hash("run"),
        runtime_seal_hash=_hash("seal"),
    )
    d = ctx.to_dict()
    assert d["controller_authority_hash"] == _hash("ctrl")
    assert d["discovery_run_grant_hash"] == _hash("grant")


def test_34_persistence_context_round_trip_preserves_new_fields() -> None:
    ctx = H40LifecyclePersistenceContext(
        implementation_authority_hash=_hash("impl"),
        controller_authority_hash=_hash("ctrl"),
        discovery_run_grant_hash=_hash("grant"),
        run_authority_id=_hash("run"),
        runtime_seal_hash=_hash("seal"),
        split_authority_hash=None,
    )
    d = ctx.to_dict()
    restored = H40LifecyclePersistenceContext.from_dict(d)
    assert restored == ctx
    assert restored.controller_authority_hash == _hash("ctrl")
    assert restored.discovery_run_grant_hash == _hash("grant")


def test_35_cold_restore_succeeds_with_valid_v2_context_and_matching_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl = _make_dummy_impl_authority()
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        impl.lifecycle_implementation_authority_hash,
    )
    ctrl = _make_dummy_controller_authority(impl)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        ctrl.controller_authority_hash,
    )
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)

    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(impl,),
        run_authorities=(run,),
        runtime_seals=(seal,),
        split_authorities=(),
        controller_authorities=(ctrl,),
        discovery_run_grants=(grant,),
    )
    verifier = H40SyntheticEvidenceVerifier({})
    service = H40LifecycleAuthorityService(
        implementation_authority=impl,
        accepted_implementation_authority_hash=impl.lifecycle_implementation_authority_hash,
        controller_authority=ctrl,
        accepted_controller_authority_hash=ctrl.controller_authority_hash,
        discovery_run_grant=grant,
        evidence_verifier=verifier,
        synthetic_test_mode=True,
        _construction_token=lifecycle_authority_module._VERIFIED_AUTHORITY_TOKEN,
    )
    auth = service.authorize_discovery(
        implementation_authority=impl,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
        controller_authority=ctrl,
        discovery_run_grant=grant,
    )
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", auth, service=service)

    restored = store.restore_authorization(
        run.run_authority_id,
        auth.receipt_hash,
        service=service,
        resolver=resolver,
    )
    assert restored.receipt_hash == auth.receipt_hash


def test_36_cold_restore_fails_if_resolver_returns_mismatched_controller_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl = _make_dummy_impl_authority()
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        impl.lifecycle_implementation_authority_hash,
    )
    ctrl = _make_dummy_controller_authority(impl)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        ctrl.controller_authority_hash,
    )
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)

    mismatched_ctrl = _make_dummy_controller_authority(impl, commit_sha="0" * 40)
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(impl,),
        run_authorities=(run,),
        runtime_seals=(seal,),
        split_authorities=(),
        controller_authorities=(mismatched_ctrl,),
        discovery_run_grants=(grant,),
    )
    verifier = H40SyntheticEvidenceVerifier({})
    service = H40LifecycleAuthorityService(
        implementation_authority=impl,
        accepted_implementation_authority_hash=impl.lifecycle_implementation_authority_hash,
        controller_authority=ctrl,
        accepted_controller_authority_hash=ctrl.controller_authority_hash,
        discovery_run_grant=grant,
        evidence_verifier=verifier,
        synthetic_test_mode=True,
        _construction_token=lifecycle_authority_module._VERIFIED_AUTHORITY_TOKEN,
    )
    auth = service.authorize_discovery(
        implementation_authority=impl,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
        controller_authority=ctrl,
        discovery_run_grant=grant,
    )
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", auth, service=service)

    lifecycle_authority_module._SYNTHETIC_CONTROLLER_REGISTRY.clear()
    with pytest.raises(H40GuardError, match="authoritative resolver has no controller authority"):
        store.restore_authorization(
            run.run_authority_id,
            auth.receipt_hash,
            service=service,
            resolver=resolver,
        )


def test_37_cold_restore_fails_if_resolver_returns_mismatched_discovery_run_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl = _make_dummy_impl_authority()
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        impl.lifecycle_implementation_authority_hash,
    )
    ctrl = _make_dummy_controller_authority(impl)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        ctrl.controller_authority_hash,
    )
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)

    mismatched_grant = H40DiscoveryRunGrant.from_controller_and_run(
        controller_authority=ctrl,
        run_authority=run,
        seal=seal,
        authorized_at_utc="2026-09-24T00:00:00Z",
    )
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(impl,),
        run_authorities=(run,),
        runtime_seals=(seal,),
        split_authorities=(),
        controller_authorities=(ctrl,),
        discovery_run_grants=(mismatched_grant,),
    )
    verifier = H40SyntheticEvidenceVerifier({})
    service = H40LifecycleAuthorityService(
        implementation_authority=impl,
        accepted_implementation_authority_hash=impl.lifecycle_implementation_authority_hash,
        controller_authority=ctrl,
        accepted_controller_authority_hash=ctrl.controller_authority_hash,
        discovery_run_grant=grant,
        evidence_verifier=verifier,
        synthetic_test_mode=True,
        _construction_token=lifecycle_authority_module._VERIFIED_AUTHORITY_TOKEN,
    )
    auth = service.authorize_discovery(
        implementation_authority=impl,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
        controller_authority=ctrl,
        discovery_run_grant=grant,
    )
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", auth, service=service)

    lifecycle_authority_module._SYNTHETIC_GRANT_REGISTRY.clear()
    with pytest.raises(H40GuardError, match="authoritative resolver has no discovery run grant"):
        store.restore_authorization(
            run.run_authority_id,
            auth.receipt_hash,
            service=service,
            resolver=resolver,
        )


def test_38_cold_restore_fails_in_production_if_context_is_v1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl = _make_dummy_impl_authority()
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        impl.lifecycle_implementation_authority_hash,
    )
    ctrl = _make_dummy_controller_authority(impl)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        ctrl.controller_authority_hash,
    )
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)

    verifier = H40SyntheticEvidenceVerifier({})
    synth_service = H40LifecycleAuthorityService(
        implementation_authority=impl,
        accepted_implementation_authority_hash=impl.lifecycle_implementation_authority_hash,
        controller_authority=ctrl,
        accepted_controller_authority_hash=ctrl.controller_authority_hash,
        discovery_run_grant=grant,
        evidence_verifier=verifier,
        synthetic_test_mode=True,
        _construction_token=lifecycle_authority_module._VERIFIED_AUTHORITY_TOKEN,
    )
    auth = synth_service.authorize_discovery(
        implementation_authority=impl,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
        controller_authority=ctrl,
        discovery_run_grant=grant,
    )
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", auth, service=synth_service)

    v1_ctx = H40LifecyclePersistenceContextV1(
        implementation_authority_hash=impl.lifecycle_implementation_authority_hash,
        run_authority_id=run.run_authority_id,
        runtime_seal_hash=seal.authority_context_hash,
    )
    for p in [store._find_receipt_path(run.run_authority_id, "01_discovery_authorization"),
              store._find_receipt_path(run.run_authority_id, auth.receipt_hash)]:
        raw = json.loads(p.read_text(encoding="utf-8"))
        raw["authority_context"] = v1_ctx.to_dict()
        p.write_text(json.dumps(raw), encoding="utf-8")

    prod_service = H40LifecycleAuthorityService.production(
        implementation_authority=impl,
        controller_authority=ctrl,
        discovery_run_grant=grant,
    )
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(impl,),
        run_authorities=(run,),
        runtime_seals=(seal,),
        split_authorities=(),
        controller_authorities=(ctrl,),
        discovery_run_grants=(grant,),
    )
    object.__setattr__(resolver, "synthetic_only", False)
    with pytest.raises(H40GuardError, match="production cold restore rejects H40_LIFECYCLE_PERSISTENCE_CONTEXT_V1"):
        store.restore_authorization(
            run.run_authority_id,
            auth.receipt_hash,
            service=prod_service,
            resolver=resolver,
        )


# =============================================================================
# 39-44: Service Lifetime and Transition Enforcement
# =============================================================================


def test_39_write_once_fields_cannot_be_mutated_after_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    impl = _make_dummy_impl_authority()
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        impl.lifecycle_implementation_authority_hash,
    )
    ctrl = _make_dummy_controller_authority(impl)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        ctrl.controller_authority_hash,
    )
    service = H40LifecycleAuthorityService.production(
        implementation_authority=impl,
        controller_authority=ctrl,
    )
    assert service.current_implementation_authority_hash == impl.lifecycle_implementation_authority_hash
    assert service.current_controller_authority_hash == ctrl.controller_authority_hash


def test_40_production_service_fails_closed_for_dummy_authority() -> None:
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH is None
    assert ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH is None
    impl = _make_dummy_impl_authority()
    with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(implementation_authority=impl)


def test_41_production_service_succeeds_when_matching_accepted_constants_are_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        impl.lifecycle_implementation_authority_hash,
    )
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        ctrl.controller_authority_hash,
    )
    service = H40LifecycleAuthorityService.production(
        implementation_authority=impl,
        controller_authority=ctrl,
    )
    assert service._accepted_implementation_authority_hash == impl.lifecycle_implementation_authority_hash
    assert service._accepted_controller_authority_hash == ctrl.controller_authority_hash


def test_42_production_service_fails_closed_on_superseded_accepted_constants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        impl.lifecycle_implementation_authority_hash,
    )
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        ctrl.controller_authority_hash,
    )
    service = H40LifecycleAuthorityService.production(
        implementation_authority=impl,
        controller_authority=ctrl,
    )
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        "0" * 64,
    )
    with pytest.raises(H40GuardError, match="superseded"):
        service._assert_current_anchors()


def test_43_authorize_discovery_enforces_controller_authority_matches_accepted_constant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        impl.lifecycle_implementation_authority_hash,
    )
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        ctrl.controller_authority_hash,
    )
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)
    service = H40LifecycleAuthorityService.production(
        implementation_authority=impl,
        controller_authority=ctrl,
        discovery_run_grant=grant,
    )
    mismatched_ctrl = _make_dummy_controller_authority(impl, commit_sha="0" * 40)
    with pytest.raises(H40GuardError, match="no independently accepted H40 P3 controller authority exists"):
        service.authorize_discovery(
            implementation_authority=impl,
            run_authority=run,
            seal=seal,
            authorized_at_utc=TS,
            controller_authority=mismatched_ctrl,
            discovery_run_grant=grant,
        )


def test_44_authorize_discovery_enforces_run_grant_binds_matching_controller_authority() -> None:
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    other_ctrl = _make_dummy_controller_authority(impl, commit_sha="0" * 40)
    mismatched_grant = _make_dummy_run_grant(other_ctrl, run, seal)
    verifier = H40SyntheticEvidenceVerifier({})
    service = H40LifecycleAuthorityService(
        implementation_authority=impl,
        accepted_implementation_authority_hash=impl.lifecycle_implementation_authority_hash,
        controller_authority=ctrl,
        accepted_controller_authority_hash=ctrl.controller_authority_hash,
        discovery_run_grant=mismatched_grant,
        evidence_verifier=verifier,
        synthetic_test_mode=True,
        _construction_token=lifecycle_authority_module._VERIFIED_AUTHORITY_TOKEN,
    )
    with pytest.raises(H40GuardError, match="discovery run grant mismatch against active controller and run authority"):
        service.authorize_discovery(
            implementation_authority=impl,
            run_authority=run,
            seal=seal,
            authorized_at_utc=TS,
            controller_authority=ctrl,
            discovery_run_grant=mismatched_grant,
        )


# =============================================================================
# 45-48: Protected and Frozen Behavior
# =============================================================================


def test_45_no_real_outcome_economic_protected_read_occurs_in_authority_negative_tests() -> None:
    with pytest.raises(H40GuardError) as exc_info:
        H40ProtectedSurfaceGuard.assert_path_allowed("h39_validation")
    assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_46_existing_protected_surface_tests_remain_green() -> None:
    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH
    assert compute_semantic_root_hash() == EXPECTED_SEMANTIC_ROOT_HASH
    assert materialize_h40_search_space_production().structural_ledger_hash == EXPECTED_STRUCTURAL_LEDGER_HASH


def test_47_f02_transitions_remain_strictly_sealed() -> None:
    assert H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE not in (
        H40LifecycleStateMachine.VALID_TRANSITIONS[H40LifecycleState.H40_CONFIRMATION_READY]
    )
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfirmationGuard().assert_outcomes_accessible()
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_48_execution_policy_remains_research_disabled_v1() -> None:
    assert CURRENT_EXECUTION_POLICY == "RESEARCH_DISABLED_V1"
    assert ACCEPTED_EXECUTION_WRITE_AUTHORITY is None


def test_49_synthetic_authority_domain_cannot_leak_into_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 1. construct an implementation authority and controller suitable for synthetic/governance testing
    impl = _make_dummy_impl_authority()
    ctrl = _make_dummy_controller_authority(impl)
    seal = _make_dummy_seal()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)
    grant = _make_dummy_run_grant(ctrl, run, seal)
    verifier = H40SyntheticEvidenceVerifier({})

    # 2. call the explicit synthetic path so the synthetic controller is present in _SYNTHETIC_CONTROLLER_REGISTRY
    synth_service = H40LifecycleAuthorityService.synthetic_for_tests(
        implementation_authority=impl,
        evidence_verifier=verifier,
        controller_authority=ctrl,
        discovery_run_grant=grant,
    )
    assert ctrl.controller_authority_hash in lifecycle_authority_module._SYNTHETIC_CONTROLLER_REGISTRY

    # 3. test-locally monkeypatch the accepted implementation/controller constants to matching hashes
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        impl.lifecycle_implementation_authority_hash,
    )
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
        ctrl.controller_authority_hash,
    )

    # 4. call production constructor without explicitly passing controller
    prod_service = H40LifecycleAuthorityService.production(
        implementation_authority=impl,
        controller_authority=None,
        discovery_run_grant=None,
    )

    # 5. assert the production service did NOT import the controller from the synthetic registry
    assert prod_service.controller_authority is None
    assert prod_service._controller_authority is None

    # 6 & 7. attempt production Discovery without explicitly supplying/currently binding the controller; assert fail-closed
    with pytest.raises(H40GuardError) as exc_info:
        prod_service.authorize_discovery(
            implementation_authority=impl,
            run_authority=run,
            seal=seal,
            authorized_at_utc=TS,
            controller_authority=None,
            discovery_run_grant=None,
        )
    assert exc_info.value.reason_code == H40ReasonCode.NOT_TESTABLE
    assert "no independently accepted H40 P3 controller authority exists" in str(exc_info.value)

    # 8. separately show the synthetic service can still use the synthetic controller in its synthetic domain
    synth_auth = synth_service.authorize_discovery(
        implementation_authority=impl,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
    )
    assert synth_auth.synthetic_only is True
    assert isinstance(synth_auth.receipt, H40DiscoveryAuthorizationReceipt)
    assert synth_auth.receipt.controller_authority_hash == ctrl.controller_authority_hash
