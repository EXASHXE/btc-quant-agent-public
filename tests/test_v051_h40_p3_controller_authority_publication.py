"""V0.5.1 H40 P3 Controller Authority Publication and Discovery Readiness Tests.

Verifies:
- P3-01: Exact accepted constant published and stage state invariants verified
- P3-02: Exact typed P3 controller authority reconstructs accepted hash
- P3-03: Wrong acceptance commit and path rejected
- P3-04: Wrong implementation authority hash rejected
- P3-05: Frozen scientific, structural, lifecycle, provenance hashes fail closed
- P3-06: Permitted partitions and execution_disabled constraints fail closed
- P3-07: Production service accepts exact typed authority objects directly without monkeypatch
- P3-08: Historical and synthetic controller authorities rejected by production service
- P3-09: Stale service anchors fail closed upon superseded controller constant
- P3-10: Synthetic evidence verifier and synthetic seal cannot satisfy production authority
- P3-11: Production-shaped readiness chain succeeds with real non-protected local data (18/150/168)
- P3-12: DiscoveryRunGrant negative bindings fail closed
- P3-13: Absolute absence of Discovery authorization receipt, ranking, or lock
- P3-14: Protected surface guard and execution environment invariants preserved
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.execution.environment import (
    ACCEPTED_EXECUTION_WRITE_AUTHORITY,
    CURRENT_EXECUTION_POLICY,
)
from btc_quant_agent.h40.guards import (
    H40GuardError,
    H40ProtectedSurfaceGuard,
    H40ReasonCode,
)
from btc_quant_agent.h40.lifecycle import (
    H40LifecycleState,
    H40LifecycleStateMachine,
)
from btc_quant_agent.h40.lifecycle_authority import (
    ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH,
    ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH,
    DISCOVERY_PROVENANCE_CONTRACT_HASH,
    DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
    EXPECTED_LIFECYCLE_CHILD_HASHES,
    EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
    EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH,
    H40DiscoveryRunGrant,
    H40LifecycleAuthorityService,
    H40LifecycleImplementationAuthority,
    H40P3ControllerAuthority,
    H40RequiredTestCIEvidenceIdentity,
    H40RunAuthority,
    H40RuntimeSnapshotSeal,
    H40SyntheticEvidenceVerifier,
    _synthesize_controller_authority,
    compute_lifecycle_governance_authority_hash,
    compute_lifecycle_semantic_root_hash,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    materialize_runtime_source_split_authority,
)
from btc_quant_agent.h40.protocol import H40ProtocolIdentity
from btc_quant_agent.h40.protocol_authority import (
    EXPECTED_PROTOCOL_AUTHORITY_HASH,
    EXPECTED_SEMANTIC_ROOT_HASH,
    EXPECTED_STRUCTURAL_LEDGER_HASH,
)
from btc_quant_agent.h40.search_space import materialize_h40_search_space_production
from btc_quant_agent.h40.source_manifest import (
    H40SourceStatus,
    materialize_verified_manifest,
)

# ---------------------------------------------------------------------------
# Canonical Stage Constants
# ---------------------------------------------------------------------------

EXACT_ACCEPTED_CONTROLLER_HASH = (
    "37b6ea92ff61b90c07f38cadea58087a8dc91c67d3beabe34dc7792988ff3e3a"
)
EXACT_ACCEPTED_IMPLEMENTATION_HASH = (
    "088b1210c17171141e232219345fa890e182282445fd9b2a70804b177d808b96"
)

EXACT_CONTROLLER_ACCEPTANCE_COMMIT = "9afd71f0adedfbf99b48773064fd0b3977805c9d"
EXACT_CONTROLLER_ACCEPTANCE_PATH = (
    "reviews/v0.5/V0.5.1_ARCHITECTURE_AND_DATA_BASELINE_R2_R1_CONTROLLER_FINAL_ACCEPTANCE.md"
)

EXACT_IMPLEMENTATION_COMMIT = "f3678676265ba53e1d874e27bc0c922c7783acaa"
EXACT_IMPLEMENTATION_ACCEPTANCE_COMMIT = "8ae06121d1e83db8df612951914629c62ed70c4b"
EXACT_IMPLEMENTATION_ACCEPTANCE_PATH = (
    "reviews/v0.5/V0.5.1_H40_PRE_P3_CLOSURE_EXACT_SHA_CONTROLLER_ACCEPTANCE.md"
)
EXACT_EVIDENCE_MANIFEST_PATH = (
    "evidence/v0.5/h40/V0.5.1_H40_PRE_P3_CLOSURE_EXACT_SHA_EVIDENCE_f3678676_R1.json"
)
EXACT_EVIDENCE_MANIFEST_SHA256 = (
    "609632e06c280adfa20ae5db5b0b3d0736792252ac07de93b1bf1e368ea210be"
)

HISTORICAL_P3_SYNTHETIC_COMMIT = "2229d44c5cc9b88ba515d0b2931d20f05936c7e8"
HISTORICAL_P3_SYNTHETIC_PATH = (
    "reviews/v0.5/V0.5.1_H40_PRE_DISCOVERY_REPAIR_CONTRACT_CONTROLLER_ACCEPTANCE.md"
)


def _exact_controller_authority_dict() -> dict[str, Any]:
    return {
        "schema_id": "H40_P3_CONTROLLER_AUTHORITY_V1",
        "authorization_scope": "H40_P3_DISCOVERY_V1",
        "controller_acceptance_artifact_path": EXACT_CONTROLLER_ACCEPTANCE_PATH,
        "controller_acceptance_commit_sha": EXACT_CONTROLLER_ACCEPTANCE_COMMIT,
        "protocol_authority_hash": EXPECTED_PROTOCOL_AUTHORITY_HASH,
        "scientific_semantic_root_hash": EXPECTED_SEMANTIC_ROOT_HASH,
        "structural_ledger_hash": EXPECTED_STRUCTURAL_LEDGER_HASH,
        "lifecycle_semantic_root_hash": EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH,
        "lifecycle_governance_authority_hash": EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
        "lifecycle_implementation_authority_hash": EXACT_ACCEPTED_IMPLEMENTATION_HASH,
        "discovery_provenance_contract_hash": DISCOVERY_PROVENANCE_CONTRACT_HASH,
        "discovery_selection_correction_contract_hash": DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        "permitted_partitions": ["WF1_TRAIN", "WF1_CALIBRATION"],
        "transition_source_state": "H40_P1_SCAFFOLDED",
        "transition_target_state": "H40_DISCOVERY",
        "execution_disabled": True,
    }


def _exact_controller_authority() -> H40P3ControllerAuthority:
    return H40P3ControllerAuthority.from_dict(_exact_controller_authority_dict())


def _exact_implementation_authority() -> H40LifecycleImplementationAuthority:
    evidence_id = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path=EXACT_EVIDENCE_MANIFEST_PATH,
        evidence_manifest_sha256=EXACT_EVIDENCE_MANIFEST_SHA256,
        tested_commit_sha=EXACT_IMPLEMENTATION_COMMIT,
    )
    return H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
        f01_implementation_acceptance_artifact_path=EXACT_IMPLEMENTATION_ACCEPTANCE_PATH,
        f01_implementation_acceptance_commit_sha=EXACT_IMPLEMENTATION_ACCEPTANCE_COMMIT,
        f01_implementation_commit_sha=EXACT_IMPLEMENTATION_COMMIT,
        required_test_ci_evidence_identity=evidence_id,
        schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_p3_01_constants_and_stage_state() -> None:
    """P3-01: Verify published controller constant, implementation constant, and frozen identities."""
    assert ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH == EXACT_ACCEPTED_CONTROLLER_HASH
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH == EXACT_ACCEPTED_IMPLEMENTATION_HASH

    assert CURRENT_EXECUTION_POLICY == "RESEARCH_DISABLED_V1"
    assert ACCEPTED_EXECUTION_WRITE_AUTHORITY is None

    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH
    assert compute_semantic_root_hash() == EXPECTED_SEMANTIC_ROOT_HASH
    assert (
        materialize_h40_search_space_production().structural_ledger_hash
        == EXPECTED_STRUCTURAL_LEDGER_HASH
    )
    assert compute_lifecycle_semantic_root_hash() == EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH
    assert (
        compute_lifecycle_governance_authority_hash()
        == EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH
    )
    assert len(EXPECTED_LIFECYCLE_CHILD_HASHES) == 9


def test_p3_02_exact_typed_controller_authority_reconstructs_hash() -> None:
    """P3-02: Verify exact typed H40P3ControllerAuthority reconstructs the published hash."""
    ctrl = _exact_controller_authority()
    assert ctrl.controller_authority_hash == EXACT_ACCEPTED_CONTROLLER_HASH

    reconstructed = H40P3ControllerAuthority.from_dict(ctrl.to_dict())
    assert reconstructed.controller_authority_hash == EXACT_ACCEPTED_CONTROLLER_HASH
    assert reconstructed == ctrl


def test_p3_03_wrong_acceptance_commit_and_path_rejected() -> None:
    """P3-03: Verify wrong acceptance commit or path fails closed."""
    base_dict = _exact_controller_authority_dict()

    # Invalid commit SHA regex
    bad_commit = copy.deepcopy(base_dict)
    bad_commit["controller_acceptance_commit_sha"] = "not-a-valid-sha"
    with pytest.raises(ValueError, match="controller_acceptance_commit_sha must be an exact lowercase 40-hex commit SHA"):
        H40P3ControllerAuthority.from_dict(bad_commit)

    # Valid commit format but wrong commit -> produces different hash
    wrong_commit = copy.deepcopy(base_dict)
    wrong_commit["controller_acceptance_commit_sha"] = "0" * 40
    ctrl_wrong_commit = H40P3ControllerAuthority.from_dict(wrong_commit)
    assert ctrl_wrong_commit.controller_authority_hash != EXACT_ACCEPTED_CONTROLLER_HASH

    # Wrong artifact path -> produces different hash
    wrong_path = copy.deepcopy(base_dict)
    wrong_path["controller_acceptance_artifact_path"] = HISTORICAL_P3_SYNTHETIC_PATH
    ctrl_wrong_path = H40P3ControllerAuthority.from_dict(wrong_path)
    assert ctrl_wrong_path.controller_authority_hash != EXACT_ACCEPTED_CONTROLLER_HASH

    # Empty artifact path
    empty_path = copy.deepcopy(base_dict)
    empty_path["controller_acceptance_artifact_path"] = ""
    with pytest.raises(ValueError, match="controller_acceptance_artifact_path must be a non-empty string"):
        H40P3ControllerAuthority.from_dict(empty_path)


def test_p3_04_wrong_implementation_authority_hash_rejected() -> None:
    """P3-04: Verify controller authority binding wrong implementation authority fails closed."""
    base_dict = _exact_controller_authority_dict()

    # Invalid sha format
    bad_sha = copy.deepcopy(base_dict)
    bad_sha["lifecycle_implementation_authority_hash"] = "short-hash"
    with pytest.raises(ValueError, match="lifecycle_implementation_authority_hash must be an exact lowercase SHA-256 hex digest"):
        H40P3ControllerAuthority.from_dict(bad_sha)

    # Historical implementation authority hash (e.g. a23ceec...)
    hist_impl = copy.deepcopy(base_dict)
    hist_impl["lifecycle_implementation_authority_hash"] = "a" * 64
    ctrl_hist = H40P3ControllerAuthority.from_dict(hist_impl)
    assert ctrl_hist.controller_authority_hash != EXACT_ACCEPTED_CONTROLLER_HASH


def test_p3_05_frozen_hashes_validation_fails_closed() -> None:
    """P3-05: Verify constructor validates all frozen root hashes strictly."""
    base_dict = _exact_controller_authority_dict()

    frozen_fields = [
        ("protocol_authority_hash", "controller authority protocol_authority_hash mismatch"),
        ("scientific_semantic_root_hash", "controller authority scientific_semantic_root_hash mismatch"),
        ("structural_ledger_hash", "controller authority structural_ledger_hash mismatch"),
        ("lifecycle_semantic_root_hash", "controller authority lifecycle_semantic_root_hash mismatch"),
        ("lifecycle_governance_authority_hash", "controller authority lifecycle_governance_authority_hash mismatch"),
        ("discovery_provenance_contract_hash", "controller authority discovery_provenance_contract_hash mismatch"),
        ("discovery_selection_correction_contract_hash", "controller authority discovery_selection_correction_contract_hash mismatch"),
    ]

    for field_name, err_match in frozen_fields:
        bad = copy.deepcopy(base_dict)
        bad[field_name] = "0" * 64
        with pytest.raises(ValueError, match=err_match):
            H40P3ControllerAuthority.from_dict(bad)


def test_p3_06_permitted_partitions_and_execution_disabled_constraints() -> None:
    """P3-06: Verify permitted_partitions and execution_disabled constraints are strictly enforced."""
    base_dict = _exact_controller_authority_dict()

    # Partitions missing CALIBRATION
    bad_p1 = copy.deepcopy(base_dict)
    bad_p1["permitted_partitions"] = ["WF1_TRAIN"]
    with pytest.raises(ValueError, match="permitted_partitions mismatch"):
        H40P3ControllerAuthority.from_dict(bad_p1)

    # Partitions containing holdout / test
    bad_p2 = copy.deepcopy(base_dict)
    bad_p2["permitted_partitions"] = ["WF1_TRAIN", "WF1_CALIBRATION", "WF1_TEST"]
    with pytest.raises(ValueError, match="permitted_partitions mismatch"):
        H40P3ControllerAuthority.from_dict(bad_p2)

    # execution_disabled is False
    bad_exec = copy.deepcopy(base_dict)
    bad_exec["execution_disabled"] = False
    with pytest.raises(ValueError, match="execution_disabled must be boolean true"):
        H40P3ControllerAuthority.from_dict(bad_exec)

    # transition states mismatch
    bad_state1 = copy.deepcopy(base_dict)
    bad_state1["transition_source_state"] = "UNSCAFFOLDED"
    with pytest.raises(ValueError, match="transition_source_state mismatch"):
        H40P3ControllerAuthority.from_dict(bad_state1)

    bad_state2 = copy.deepcopy(base_dict)
    bad_state2["transition_target_state"] = "H40_WF1"
    with pytest.raises(ValueError, match="transition_target_state mismatch"):
        H40P3ControllerAuthority.from_dict(bad_state2)


def test_p3_07_production_service_accepts_exact_objects_without_monkeypatch() -> None:
    """P3-07: Verify production service accepts exact typed implementation + controller objects."""
    impl = _exact_implementation_authority()
    ctrl = _exact_controller_authority()

    service = H40LifecycleAuthorityService.production(
        implementation_authority=impl,
        controller_authority=ctrl,
    )

    assert service.current_implementation_authority_hash == EXACT_ACCEPTED_IMPLEMENTATION_HASH
    assert service.current_controller_authority_hash == EXACT_ACCEPTED_CONTROLLER_HASH
    assert service.synthetic_test_mode is False

    # Production anchors check passes for both implementation and controller
    service._assert_current_anchors(require_controller=False)
    service._assert_current_anchors(require_controller=True)


def test_p3_08_historical_and_synthetic_controller_authorities_rejected() -> None:
    """P3-08: Verify historical and synthetic controller authorities are rejected in production."""
    impl = _exact_implementation_authority()

    # Synthetic controller produced by helper (points to 2229d44c... acceptance commit)
    synth_ctrl = _synthesize_controller_authority(impl)
    assert synth_ctrl.controller_authority_hash != EXACT_ACCEPTED_CONTROLLER_HASH

    with pytest.raises(ValueError, match="controller authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=impl,
            controller_authority=synth_ctrl,
        )


def test_p3_09_stale_service_anchors_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """P3-09: Verify a service instantiated before P3 publication fails closed upon require_controller."""
    # Stale service created when controller hash was None
    with monkeypatch.context() as m:
        m.setattr(
            "btc_quant_agent.h40.lifecycle_authority.ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH",
            None,
        )
        stale_service = H40LifecycleAuthorityService.production(
            implementation_authority=_exact_implementation_authority(),
        )

    # After P3 publication, the stale service fails anchor checks
    with pytest.raises(H40GuardError) as exc_info:
        stale_service._assert_current_anchors(require_controller=True)
    assert exc_info.value.reason_code == H40ReasonCode.CONFIG_IDENTITY_CONFLICT
    assert "service controller authority anchor has been superseded" in str(exc_info.value)


def test_p3_10_synthetic_verifier_and_seal_cannot_satisfy_production_service() -> None:
    """P3-10: Verify synthetic verifier and synthetic seal cannot satisfy production authority."""
    impl = _exact_implementation_authority()
    ctrl = _exact_controller_authority()

    # Synthetic evidence verifier cannot be passed to production service
    synth_verifier = H40SyntheticEvidenceVerifier({})
    with pytest.raises(ValueError, match="production service cannot use a synthetic/test-only verifier"):
        H40LifecycleAuthorityService.production(
            implementation_authority=impl,
            controller_authority=ctrl,
            evidence_verifier=synth_verifier,
        )

    # Synthetic seal verification against accepted ledger
    synth_seal = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash="0" * 64,
        source_manifest_hash="1" * 64,
        split_manifest_hash="2" * 64,
        split_attestation_hash="3" * 64,
        roster=(),
        not_testable_slot_count=168,
    )
    with pytest.raises(H40GuardError) as exc_seal:
        synth_seal.verify_against_accepted_ledger()
    assert exc_seal.value.reason_code == H40ReasonCode.CONFIG_IDENTITY_CONFLICT


LOCAL_ETH_PATH = Path("data/research/cross_asset_1h/ETHUSDT.parquet")


@pytest.mark.skipif(
    not LOCAL_ETH_PATH.exists(),
    reason="Requires non-protected local ETHUSDT.parquet (omitted from git / remote CI)",
)
def test_p3_11_production_readiness_chain_with_real_local_data() -> None:
    """P3-11: Verify complete production readiness chain using actual local non-protected ETH data."""
    repo_root = Path.cwd()
    protocol_id = H40ProtocolIdentity.default()

    # Step 1: Materialize verified source manifest from real local data
    source_manifest = materialize_verified_manifest(
        repo_root=repo_root,
        protocol_identity_hash=protocol_id.protocol_hash,
    )
    eth_source = source_manifest.get_source("ETHUSDT_USD_M_1H")
    assert eth_source.status == H40SourceStatus.VERIFIED
    assert eth_source.row_count == 44568
    assert eth_source.file_sha256 == "563a1a4d927ec2a007481783be9bd76896e1be57198af80c4b2a30608e124608"
    assert eth_source.archive_set_sha256 == "1efde37a765de90e33fd509bd1bcb729351beafa79314f684b3558665b19226c"

    # Step 2: Cold-materialize runtime source/split authority
    split_manifest, attestation = materialize_runtime_source_split_authority(
        source_manifest=source_manifest,
        repo_root=repo_root,
    )
    assert len(split_manifest.split_hash) == 64
    assert len(attestation.attestation_hash) == 64

    # Step 3: Materialize production snapshot seal and verify against ledger
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source_manifest,
        split_manifest=split_manifest,
        runtime_attestation=attestation,
        repo_root=repo_root,
    )
    seal.verify_against_accepted_ledger()

    assert seal.total_slot_count == 168
    assert seal.registered_slot_count == 18
    assert seal.not_testable_slot_count == 150
    assert seal.runtime_authority_snapshot_hash == "733b57a347259794e552a2bc47ecf80712d0e6b54b2d3e2b90c7d52d7a0883d2"
    assert seal.sealed_registered_roster_hash == "78af704fff5210beddd7427a1624cae4c1fbc1415da1fdbc6fcfa8a3228179da"

    # Step 4: Materialize run authority
    run_auth = H40RunAuthority.from_seal(seal, EXACT_ACCEPTED_IMPLEMENTATION_HASH)
    assert run_auth.run_authority_id == "1c6a9942c961867524d1c9b9b0092fc9fc05ed54f0bf8e2b1e90863fa4b3a1bf"
    assert run_auth.materialized_run_authority_hash == "b39534c47e3f965e2857da309bf29ba14122db7ee01bc5d6d00a52bf75a0e952"

    # Step 5: Construct readiness-only DiscoveryRunGrant
    ctrl = _exact_controller_authority()
    audit_ts = "2026-09-27T08:45:00Z"
    grant = H40DiscoveryRunGrant.from_controller_and_run(
        controller_authority=ctrl,
        run_authority=run_auth,
        seal=seal,
        authorized_at_utc=audit_ts,
    )
    assert grant.discovery_run_grant_hash == "7163c0b5c8708e6a9b301d634430d34fc49dc548f0ea2f750a7766962dd21b0a"
    assert grant.execution_disabled is True
    assert grant.permitted_partitions == ("WF1_TRAIN", "WF1_CALIBRATION")


@pytest.mark.skipif(
    not LOCAL_ETH_PATH.exists(),
    reason="Requires non-protected local ETHUSDT.parquet (omitted from git / remote CI)",
)
def test_p3_12_run_grant_negative_bindings_fail_closed() -> None:
    """P3-12: Verify DiscoveryRunGrant fails closed on any mismatched identity."""
    repo_root = Path.cwd()
    protocol_id = H40ProtocolIdentity.default()
    source_manifest = materialize_verified_manifest(repo_root=repo_root, protocol_identity_hash=protocol_id.protocol_hash)
    split_manifest, attestation = materialize_runtime_source_split_authority(
        source_manifest=source_manifest,
        repo_root=repo_root,
    )
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source_manifest,
        split_manifest=split_manifest,
        runtime_attestation=attestation,
        repo_root=repo_root,
    )
    valid_run = H40RunAuthority.from_seal(seal, EXACT_ACCEPTED_IMPLEMENTATION_HASH)
    ctrl = _exact_controller_authority()

    # Wrong run authority (e.g. constructed with different implementation hash)
    wrong_run = H40RunAuthority.from_seal(seal, "a" * 64)
    with pytest.raises(H40GuardError) as exc_impl:
        H40DiscoveryRunGrant.from_controller_and_run(
            controller_authority=ctrl,
            run_authority=wrong_run,
            seal=seal,
            authorized_at_utc="2026-09-27T08:45:00Z",
        )
    assert exc_impl.value.reason_code == H40ReasonCode.CONFIG_IDENTITY_CONFLICT

    # Wrong seal with valid run authority
    wrong_seal = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash="0" * 64,
        source_manifest_hash="1" * 64,
        split_manifest_hash="2" * 64,
        split_attestation_hash="3" * 64,
        roster=(),
        not_testable_slot_count=168,
    )
    with pytest.raises(H40GuardError) as exc_seal:
        H40DiscoveryRunGrant.from_controller_and_run(
            controller_authority=ctrl,
            run_authority=valid_run,
            seal=wrong_seal,
            authorized_at_utc="2026-09-27T08:45:00Z",
        )
    assert exc_seal.value.reason_code == H40ReasonCode.CONFIG_IDENTITY_CONFLICT


def test_p3_13_no_discovery_authorization_receipt_created() -> None:
    """P3-13: Prove no Discovery authorization receipt was created or persisted in this stage."""
    machine = H40LifecycleStateMachine()
    assert machine.current_state == H40LifecycleState.H40_P1_SCAFFOLDED

    # Ensure no discovery authorization receipt files exist anywhere in artifacts or evidence
    receipt_files = list(Path("artifacts").glob("**/H40_RECEIPT_DISCOVERY_AUTH_V3*"))
    assert len(receipt_files) == 0

    evidence_receipts = list(Path("evidence").glob("**/H40_RECEIPT_DISCOVERY_AUTH_V3*"))
    assert len(evidence_receipts) == 0


def test_p3_14_protected_surface_guard_and_execution_environment_invariants() -> None:
    """P3-14: Verify protected surfaces remain strictly inaccessible and execution policy remains disabled."""
    # Forbidden / protected surfaces fail closed
    forbidden_paths = [
        "artifacts/h39_protected/result",
        "artifacts/final_holdout/result",
        "data/research/h39_validation/",
    ]
    for path in forbidden_paths:
        with pytest.raises(H40GuardError):
            H40ProtectedSurfaceGuard.assert_surface_allowed(path)

    # Non-protected research source is allowed
    H40ProtectedSurfaceGuard.assert_surface_allowed("data/research/cross_asset_1h/ETHUSDT.parquet")

    # Execution remains disabled
    assert CURRENT_EXECUTION_POLICY == "RESEARCH_DISABLED_V1"
    assert ACCEPTED_EXECUTION_WRITE_AUTHORITY is None
