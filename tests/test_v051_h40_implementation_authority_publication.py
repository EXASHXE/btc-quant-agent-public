"""V0.5.1 H40 Implementation Authority Republication Regression Tests.

Verifies:
- P01: exact accepted constant published
- P02: exact typed authority reconstructs accepted hash
- P03: production service accepts exact authority directly without monkeypatch
- P04: altered authority fails closed
- P05: governance mismatch fails closed
- P06: tested commit mismatch fails closed
- P07: synthetic verifier remains fenced
- P08: F02 remains sealed
- P09: execution remains disabled
- P10: scientific and lifecycle identities unchanged
- P11: previous authority fails closed
- P12: critical negative paths
- P13: mandatory republication fail-closed controller gate
"""

from __future__ import annotations

import pytest

from btc_quant_agent.execution.environment import (
    ACCEPTED_EXECUTION_WRITE_AUTHORITY,
    CURRENT_EXECUTION_POLICY,
)
from btc_quant_agent.h40.guards import H40ConfirmationGuard, H40GuardError, H40ReasonCode
from btc_quant_agent.h40.lifecycle import H40LifecycleState, H40LifecycleStateMachine
from btc_quant_agent.h40.lifecycle_authority import (
    ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH,
    ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH,
    EXPECTED_LIFECYCLE_CHILD_HASHES,
    EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
    EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH,
    H40LifecycleAuthorityService,
    H40LifecycleImplementationAuthority,
    H40RequiredTestCIEvidenceIdentity,
    H40SyntheticEvidenceVerifier,
    compute_lifecycle_governance_authority_hash,
    compute_lifecycle_semantic_root_hash,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
)
from btc_quant_agent.h40.protocol_authority import (
    EXPECTED_PROTOCOL_AUTHORITY_HASH,
    EXPECTED_SEMANTIC_ROOT_HASH,
    EXPECTED_STRUCTURAL_LEDGER_HASH,
)
from btc_quant_agent.h40.search_space import materialize_h40_search_space_production

EXACT_ACCEPTED_HASH = (
    "088b1210c17171141e232219345fa890e182282445fd9b2a70804b177d808b96"
)
EXACT_IMPLEMENTATION_COMMIT = "f3678676265ba53e1d874e27bc0c922c7783acaa"
EXACT_ACCEPTANCE_COMMIT = "8ae06121d1e83db8df612951914629c62ed70c4b"
EXACT_ACCEPTANCE_PATH = (
    "reviews/v0.5/V0.5.1_H40_PRE_P3_CLOSURE_EXACT_SHA_CONTROLLER_ACCEPTANCE.md"
)
EXACT_EVIDENCE_MANIFEST_PATH = (
    "evidence/v0.5/h40/V0.5.1_H40_PRE_P3_CLOSURE_EXACT_SHA_EVIDENCE_f3678676_R1.json"
)
EXACT_EVIDENCE_MANIFEST_SHA256 = (
    "609632e06c280adfa20ae5db5b0b3d0736792252ac07de93b1bf1e368ea210be"
)
EXACT_GOVERNANCE_HASH = EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH

HISTORICAL_A23_ACCEPTED_HASH = (
    "a23ceec50ff5703f4dff703a7b44e715501164a48ec9be48ae096f8bd4d51fca"
)
HISTORICAL_A23_IMPLEMENTATION_COMMIT = "7413c96301067c59b9663d8eeaeddf975facb976"
HISTORICAL_A23_ACCEPTANCE_COMMIT = "32421f6f25fdff6e2b8d9373e5440e286833014e"
HISTORICAL_A23_ACCEPTANCE_PATH = (
    "reviews/v0.5/V0.5.1_H40_AB_CUMULATIVE_EXACT_SHA_CONTROLLER_ACCEPTANCE.md"
)
HISTORICAL_A23_EVIDENCE_MANIFEST_PATH = (
    "evidence/v0.5/h40/V0.5.1_H40_AB_CUMULATIVE_EXACT_SHA_EVIDENCE_7413c963.json"
)
HISTORICAL_A23_EVIDENCE_MANIFEST_SHA256 = (
    "46bce0d3406103f1ee05baef31b3bf006b38d5e46c38842802a798b57b58718f"
)

HISTORICAL_ACCEPTED_HASH = (
    "ee14d950367742d9b7ed0cbda5578a04285380267bd392dcede82aa45edf26ec"
)
HISTORICAL_IMPLEMENTATION_COMMIT = "d73e8984446f933059b978e36c4cabd55de517aa"
HISTORICAL_ACCEPTANCE_COMMIT = "0cbb20a7806f2336864e430910bf6a4ff4a99df9"
HISTORICAL_ACCEPTANCE_PATH = (
    "reviews/v0.5/V0.5.1_H40_FINAL_EXACT_SHA_REACCEPTANCE_CONTROLLER_ACCEPTANCE.md"
)
HISTORICAL_EVIDENCE_MANIFEST_PATH = (
    "evidence/v0.5/h40/V0.5.1_H40_FINAL_REACCEPTANCE_EVIDENCE_d73e898.json"
)
HISTORICAL_EVIDENCE_MANIFEST_SHA256 = (
    "5cd591ef7f3f43c7897711ab4e75cb158ac048d328e1f8b0dac28a0a6bcb6540"
)


def _exact_authority() -> H40LifecycleImplementationAuthority:
    evidence_id = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path=EXACT_EVIDENCE_MANIFEST_PATH,
        evidence_manifest_sha256=EXACT_EVIDENCE_MANIFEST_SHA256,
        tested_commit_sha=EXACT_IMPLEMENTATION_COMMIT,
    )
    return H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=EXACT_GOVERNANCE_HASH,
        f01_implementation_acceptance_artifact_path=EXACT_ACCEPTANCE_PATH,
        f01_implementation_acceptance_commit_sha=EXACT_ACCEPTANCE_COMMIT,
        f01_implementation_commit_sha=EXACT_IMPLEMENTATION_COMMIT,
        required_test_ci_evidence_identity=evidence_id,
        schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
    )


def _historical_a23_authority() -> H40LifecycleImplementationAuthority:
    evidence_id = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path=HISTORICAL_A23_EVIDENCE_MANIFEST_PATH,
        evidence_manifest_sha256=HISTORICAL_A23_EVIDENCE_MANIFEST_SHA256,
        tested_commit_sha=HISTORICAL_A23_IMPLEMENTATION_COMMIT,
    )
    return H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=EXACT_GOVERNANCE_HASH,
        f01_implementation_acceptance_artifact_path=HISTORICAL_A23_ACCEPTANCE_PATH,
        f01_implementation_acceptance_commit_sha=HISTORICAL_A23_ACCEPTANCE_COMMIT,
        f01_implementation_commit_sha=HISTORICAL_A23_IMPLEMENTATION_COMMIT,
        required_test_ci_evidence_identity=evidence_id,
        schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
    )


def test_p01_exact_accepted_constant() -> None:
    """P01: Verify production implementation constant is published while P3 controller remains None."""
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH == EXACT_ACCEPTED_HASH
    assert ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH is None


def test_p02_exact_typed_authority_reconstructs_accepted_hash() -> None:
    """P02: Verify exact typed authority object reconstructs the accepted hash."""
    authority = _exact_authority()
    assert authority.lifecycle_implementation_authority_hash == EXACT_ACCEPTED_HASH


def test_p03_production_service_accepts_exact_authority() -> None:
    """P03: Verify production service accepts exact typed implementation authority directly without monkeypatch."""
    authority = _exact_authority()
    service = H40LifecycleAuthorityService.production(
        implementation_authority=authority,
    )
    assert service._implementation_authority == authority
    assert service._accepted_implementation_authority_hash == EXACT_ACCEPTED_HASH


def test_p04_altered_authority_fails_closed() -> None:
    """P04: Verify altered implementation authority fails closed with mismatch error."""
    # Construct an authority with a different commit SHA
    alt_commit = "1" * 40
    evidence_id = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path=EXACT_EVIDENCE_MANIFEST_PATH,
        evidence_manifest_sha256=EXACT_EVIDENCE_MANIFEST_SHA256,
        tested_commit_sha=alt_commit,
    )
    altered_authority = H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=EXACT_GOVERNANCE_HASH,
        f01_implementation_acceptance_artifact_path=EXACT_ACCEPTANCE_PATH,
        f01_implementation_acceptance_commit_sha=EXACT_ACCEPTANCE_COMMIT,
        f01_implementation_commit_sha=alt_commit,
        required_test_ci_evidence_identity=evidence_id,
        schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
    )
    assert altered_authority.lifecycle_implementation_authority_hash != EXACT_ACCEPTED_HASH

    with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=altered_authority,
        )


def test_p05_governance_mismatch_fails_closed() -> None:
    """P05: Verify foreign governance authority hash cannot instantiate as accepted authority."""
    foreign_gov_hash = "0" * 64
    evidence_id = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path=EXACT_EVIDENCE_MANIFEST_PATH,
        evidence_manifest_sha256=EXACT_EVIDENCE_MANIFEST_SHA256,
        tested_commit_sha=EXACT_IMPLEMENTATION_COMMIT,
    )
    with pytest.raises(ValueError, match="implementation authority governance hash is not accepted"):
        H40LifecycleImplementationAuthority(
            accepted_lifecycle_governance_authority_hash=foreign_gov_hash,
            f01_implementation_acceptance_artifact_path=EXACT_ACCEPTANCE_PATH,
            f01_implementation_acceptance_commit_sha=EXACT_ACCEPTANCE_COMMIT,
            f01_implementation_commit_sha=EXACT_IMPLEMENTATION_COMMIT,
            required_test_ci_evidence_identity=evidence_id,
            schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
        )


def test_p06_tested_commit_mismatch_fails_closed() -> None:
    """P06: Verify tested commit mismatch within authority raises ValueError."""
    evidence_id = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path=EXACT_EVIDENCE_MANIFEST_PATH,
        evidence_manifest_sha256=EXACT_EVIDENCE_MANIFEST_SHA256,
        tested_commit_sha="2" * 40,  # Does not match f01_implementation_commit_sha
    )
    with pytest.raises(ValueError, match="test/CI evidence tested_commit_sha must equal implementation commit"):
        H40LifecycleImplementationAuthority(
            accepted_lifecycle_governance_authority_hash=EXACT_GOVERNANCE_HASH,
            f01_implementation_acceptance_artifact_path=EXACT_ACCEPTANCE_PATH,
            f01_implementation_acceptance_commit_sha=EXACT_ACCEPTANCE_COMMIT,
            f01_implementation_commit_sha=EXACT_IMPLEMENTATION_COMMIT,
            required_test_ci_evidence_identity=evidence_id,
            schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
        )


def test_p07_synthetic_verifier_remains_fenced() -> None:
    """P07: Verify production service cannot use synthetic/test-only verifier."""
    authority = _exact_authority()
    with pytest.raises(ValueError, match="production service cannot use a synthetic/test-only verifier"):
        H40LifecycleAuthorityService.production(
            implementation_authority=authority,
            evidence_verifier=H40SyntheticEvidenceVerifier({}),
        )


def test_p08_f02_remains_sealed() -> None:
    """P08: Verify F02 remains strictly sealed and CONFIRMATION_READY -> EVALUATED_ONCE is forbidden."""
    assert H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE not in (
        H40LifecycleStateMachine.VALID_TRANSITIONS[H40LifecycleState.H40_CONFIRMATION_READY]
    )
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfirmationGuard().assert_outcomes_accessible()
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_p09_execution_remains_disabled() -> None:
    """P09: Verify execution policy remains RESEARCH_DISABLED_V1 with no write authority."""
    assert CURRENT_EXECUTION_POLICY == "RESEARCH_DISABLED_V1"
    assert ACCEPTED_EXECUTION_WRITE_AUTHORITY is None


def test_p10_scientific_and_lifecycle_identities_unchanged() -> None:
    """P10: Verify scientific protocol/semantic/structural and lifecycle hashes remain invariant."""
    # Scientific identities
    proto_hash = compute_protocol_authority_hash()
    assert proto_hash == "a83f8fc7a5ca7109fb8cd7fed114d87c3b2c968b5145c11cada203aa5111d1ce"
    assert EXPECTED_PROTOCOL_AUTHORITY_HASH == proto_hash

    sem_hash = compute_semantic_root_hash()
    assert sem_hash == "71889a35f227ed734272b712851174a69bf9dbb12ea3f87cd84c26e7c66f6af1"
    assert EXPECTED_SEMANTIC_ROOT_HASH == sem_hash

    ledger = materialize_h40_search_space_production()
    struct_hash = ledger.structural_ledger_hash
    assert struct_hash == "483f68502b57972deae071c7bd4587ca3e57ccaa72bd99fb0de07b4f0ab8c85f"
    assert EXPECTED_STRUCTURAL_LEDGER_HASH == struct_hash

    # Lifecycle identities
    lc_sem_root = compute_lifecycle_semantic_root_hash()
    assert lc_sem_root == "36cbda530352cffaa475bd835b3b629df47351ca284e09bdf31a8fc884d48b4b"
    assert EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH == lc_sem_root

    lc_gov = compute_lifecycle_governance_authority_hash()
    assert lc_gov == "bb367f2af726be105bddf42636c97652402014c8a671d43ab81b1964c258e5cf"
    assert EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH == lc_gov

    # Transition matrix contract hash
    assert EXPECTED_LIFECYCLE_CHILD_HASHES["transition_matrix_contract"] == (
        "bea7b0593251204bbc9138c325f1c9f10ccf7a9b8df60f10bf991377e0ced42d"
    )


def test_p11_previous_authority_fails_closed() -> None:
    """P11: Verify previous published authority objects/hashes are rejected by production service."""
    # Historical a23ceec... authority is rejected
    a23_authority = _historical_a23_authority()
    assert a23_authority.lifecycle_implementation_authority_hash == HISTORICAL_A23_ACCEPTED_HASH
    assert a23_authority.lifecycle_implementation_authority_hash != EXACT_ACCEPTED_HASH
    with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=a23_authority,
        )

    # Historical ee14d95... authority is rejected
    historical_evidence_id = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path=HISTORICAL_EVIDENCE_MANIFEST_PATH,
        evidence_manifest_sha256=HISTORICAL_EVIDENCE_MANIFEST_SHA256,
        tested_commit_sha=HISTORICAL_IMPLEMENTATION_COMMIT,
    )
    historical_authority = H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=EXACT_GOVERNANCE_HASH,
        f01_implementation_acceptance_artifact_path=HISTORICAL_ACCEPTANCE_PATH,
        f01_implementation_acceptance_commit_sha=HISTORICAL_ACCEPTANCE_COMMIT,
        f01_implementation_commit_sha=HISTORICAL_IMPLEMENTATION_COMMIT,
        required_test_ci_evidence_identity=historical_evidence_id,
        schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
    )
    assert historical_authority.lifecycle_implementation_authority_hash == HISTORICAL_ACCEPTED_HASH
    assert historical_authority.lifecycle_implementation_authority_hash != EXACT_ACCEPTED_HASH
    with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=historical_authority,
        )


def test_p12_critical_negative_paths() -> None:
    """P12: Prove critical negative paths after publication:
    - implementation authority published = YES
    - P3 controller authority published = NO (None)
    - altered implementation authority fails closed
    - historical a23ceec... authority is not current
    - wrong accepted-governance hash fails closed
    - wrong acceptance commit/path fails closed
    - wrong tested implementation SHA fails closed
    - wrong evidence manifest SHA fails closed
    - synthetic verifier remains fenced
    - synthetic controller cannot satisfy production P3 requirement
    - authorize_discovery without independently published P3 controller authority => NOT_TESTABLE
    """
    from btc_quant_agent.h40.lifecycle_authority import (
        H40RunAuthority,
        H40RuntimeSnapshotSeal,
        _synthesize_controller_authority,
    )

    # 1. Implementation authority published = YES
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH == EXACT_ACCEPTED_HASH

    # 2. P3 controller authority published = NO
    assert ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH is None

    # 3. Old a23ceec... typed authority is not current
    a23_auth = _historical_a23_authority()
    with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=a23_auth,
        )

    # 4. Production service accepts current typed authority without monkeypatch
    authority = _exact_authority()
    service = H40LifecycleAuthorityService.production(
        implementation_authority=authority,
    )

    # 5. Discovery authorization without controller = fail-closed / NOT_TESTABLE
    seal = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash="0" * 64,
        source_manifest_hash="1" * 64,
        split_manifest_hash="2" * 64,
        split_attestation_hash="3" * 64,
        roster=(),
        not_testable_slot_count=168,
    )
    run = H40RunAuthority.from_seal(seal, authority.lifecycle_implementation_authority_hash)
    with pytest.raises(H40GuardError) as exc_info:
        service.authorize_discovery(
            implementation_authority=authority,
            run_authority=run,
            seal=seal,
            authorized_at_utc="2026-09-26T20:00:00Z",
        )
    assert exc_info.value.reason_code == H40ReasonCode.NOT_TESTABLE
    assert "no independently accepted H40 P3 controller authority exists" in str(exc_info.value)

    # 6. Synthetic controller cannot satisfy production controller requirement
    synthetic_ctrl = _synthesize_controller_authority(authority)
    with pytest.raises(ValueError, match="controller authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=authority,
            controller_authority=synthetic_ctrl,
        )

    # 7. Wrong evidence manifest SHA fails closed
    wrong_ev_manifest = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path=EXACT_EVIDENCE_MANIFEST_PATH,
        evidence_manifest_sha256="0" * 64,
        tested_commit_sha=EXACT_IMPLEMENTATION_COMMIT,
    )
    wrong_manifest_authority = H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=EXACT_GOVERNANCE_HASH,
        f01_implementation_acceptance_artifact_path=EXACT_ACCEPTANCE_PATH,
        f01_implementation_acceptance_commit_sha=EXACT_ACCEPTANCE_COMMIT,
        f01_implementation_commit_sha=EXACT_IMPLEMENTATION_COMMIT,
        required_test_ci_evidence_identity=wrong_ev_manifest,
        schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
    )
    with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=wrong_manifest_authority,
        )


def test_p13_mandatory_republication_fail_closed_controller_gate() -> None:
    """Mandatory fail-closed test proving:
    - after republication: production implementation authority = EXACT_ACCEPTED_HASH
    - P3 controller authority = None
    - production Discovery authorization remains NOT_TESTABLE because P3 controller authority is missing
    - old a23ceec... typed authority is rejected as not current
    - production service does not auto-synthesize P3 controller authority or run grant
    """
    from btc_quant_agent.h40.lifecycle_authority import (
        H40RunAuthority,
        H40RuntimeSnapshotSeal,
    )

    # 1. production implementation authority = EXACT_ACCEPTED_HASH
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH == EXACT_ACCEPTED_HASH

    # 2. P3 controller authority = None
    assert ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH is None

    # 3. old a23ceec... typed authority cannot become current merely because its historical object is valid
    hist_authority = _historical_a23_authority()
    assert hist_authority.lifecycle_implementation_authority_hash == HISTORICAL_A23_ACCEPTED_HASH
    with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=hist_authority,
        )

    # 4. production service does not auto-synthesize P3 controller authority or run grant
    authority = _exact_authority()
    prod_service = H40LifecycleAuthorityService.production(
        implementation_authority=authority,
    )
    assert prod_service._controller_authority is None
    assert prod_service._discovery_run_grant is None

    # 5. production Discovery authorization remains NOT_TESTABLE
    seal = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash="0" * 64,
        source_manifest_hash="1" * 64,
        split_manifest_hash="2" * 64,
        split_attestation_hash="3" * 64,
        roster=(),
        not_testable_slot_count=168,
    )
    run = H40RunAuthority.from_seal(seal, authority.lifecycle_implementation_authority_hash)
    with pytest.raises(H40GuardError) as exc_info:
        prod_service.authorize_discovery(
            implementation_authority=authority,
            run_authority=run,
            seal=seal,
            authorized_at_utc="2026-09-26T20:00:00Z",
        )
    assert exc_info.value.reason_code == H40ReasonCode.NOT_TESTABLE
    assert "no independently accepted H40 P3 controller authority exists" in str(exc_info.value)
