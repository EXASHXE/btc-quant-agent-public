"""V0.5.1 H40 Implementation Authority Publication Regression Tests.

Verifies:
- P01: exact accepted constant published
- P02: exact typed authority reconstructs accepted hash
- P03: production service accepts exact authority
- P04: altered authority fails closed
- P05: governance mismatch fails closed
- P06: tested commit mismatch fails closed
- P07: synthetic verifier remains fenced
- P08: F02 remains sealed
- P09: execution remains disabled
- P10: scientific and lifecycle identities unchanged
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
    "6d61054a6a8d9bdaaf7e7d648cb941bbb893b67a1fb6a0ed0742a0cdd40697e5"
)
EXACT_IMPLEMENTATION_COMMIT = "d0e1fe0d87d4595640edc4d7ecfa5f287640f0aa"
EXACT_ACCEPTANCE_COMMIT = "5deb937bcb84c18165de8f1938d0cac65300f1e4"
EXACT_ACCEPTANCE_PATH = (
    "reviews/v0.5/V0.5.1_POST_SANITIZATION_SOL_INDEPENDENT_ACCEPTANCE.md"
)
EXACT_EVIDENCE_MANIFEST_PATH = (
    "evidence/v0.5/h40/V0.5.1_H40_F01_POST_SANITIZATION_AGGREGATE_IMPLEMENTATION_EVIDENCE.json"
)
EXACT_EVIDENCE_MANIFEST_SHA256 = (
    "8b839f6b8ddbe433be6df069928f28f0c07a6a3b966c159af26d04b561e7da24"
)
EXACT_GOVERNANCE_HASH = (
    "7e9433aa2ee706dda61871c6ad2b1a1aee4cf7a8f9b6365351942096b5347c84"
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


def test_p01_exact_accepted_constant() -> None:
    """P01: Verify ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH is published with exact hash."""
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH is not None
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH == EXACT_ACCEPTED_HASH


def test_p02_exact_typed_authority_reconstructs_accepted_hash() -> None:
    """P02: Verify exact typed authority object reconstructs the accepted hash."""
    authority = _exact_authority()
    assert authority.lifecycle_implementation_authority_hash == EXACT_ACCEPTED_HASH
    assert authority.lifecycle_implementation_authority_hash == ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH


def test_p03_production_service_accepts_exact_authority() -> None:
    """P03: Verify production service successfully constructs when supplied the exact authority."""
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
    assert lc_sem_root == "846591f8eac0e1abbedaeeff4c2b0bb7648fe51bdaf981e3309c6f6c440aba8e"
    assert EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH == lc_sem_root

    lc_gov = compute_lifecycle_governance_authority_hash()
    assert lc_gov == "7e9433aa2ee706dda61871c6ad2b1a1aee4cf7a8f9b6365351942096b5347c84"
    assert EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH == lc_gov

    # Transition matrix contract hash
    assert EXPECTED_LIFECYCLE_CHILD_HASHES["transition_matrix_contract"] == (
        "a4df11b3a0f3fabef1fa2b28e0a9f38500dcd6bb9111c4afdd9000bb238d0ddc"
    )
