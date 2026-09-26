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
    "a23ceec50ff5703f4dff703a7b44e715501164a48ec9be48ae096f8bd4d51fca"
)
EXACT_IMPLEMENTATION_COMMIT = "7413c96301067c59b9663d8eeaeddf975facb976"
EXACT_ACCEPTANCE_COMMIT = "32421f6f25fdff6e2b8d9373e5440e286833014e"
EXACT_ACCEPTANCE_PATH = (
    "reviews/v0.5/V0.5.1_H40_AB_CUMULATIVE_EXACT_SHA_CONTROLLER_ACCEPTANCE.md"
)
EXACT_EVIDENCE_MANIFEST_PATH = (
    "evidence/v0.5/h40/V0.5.1_H40_AB_CUMULATIVE_EXACT_SHA_EVIDENCE_7413c963.json"
)
EXACT_EVIDENCE_MANIFEST_SHA256 = (
    "46bce0d3406103f1ee05baef31b3bf006b38d5e46c38842802a798b57b58718f"
)
EXACT_GOVERNANCE_HASH = EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH

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


def test_p01_exact_accepted_constant() -> None:
    """P01: Verify production implementation constant is published while P3 controller remains None."""
    assert (
        ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH
        == EXACT_ACCEPTED_HASH
    )
    assert ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH is None


def test_p02_exact_typed_authority_reconstructs_accepted_hash() -> None:
    """P02: Verify exact typed authority object reconstructs the accepted hash."""
    authority = _exact_authority()
    assert authority.lifecycle_implementation_authority_hash == EXACT_ACCEPTED_HASH


def test_p03_production_service_accepts_exact_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    """P03: Verify production service accepts exact authority directly without monkeypatching, and fails closed when unconfigured."""
    authority = _exact_authority()
    # A production service supplied with the exact typed implementation authority
    # must be accepted without monkeypatching the implementation accepted hash.
    service = H40LifecycleAuthorityService.production(
        implementation_authority=authority,
    )
    assert service._implementation_authority == authority
    assert service._accepted_implementation_authority_hash == EXACT_ACCEPTED_HASH

    # When unconfigured (None), production service fails closed
    with monkeypatch.context() as m:
        m.setattr(
            "btc_quant_agent.h40.lifecycle_authority.ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
            None,
        )
        with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
            H40LifecycleAuthorityService.production(
                implementation_authority=authority,
            )


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
    """P11: Verify previous published authority object/hash is rejected by production service."""
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
    assert (
        historical_authority.lifecycle_implementation_authority_hash
        != EXACT_ACCEPTED_HASH
    )

    with pytest.raises(
        ValueError, match="implementation authority object/hash mismatch"
    ):
        H40LifecycleAuthorityService.production(
            implementation_authority=historical_authority,
        )


def test_p12_critical_negative_paths() -> None:
    """P12: Prove critical negative paths after publication:
    - implementation authority published = YES
    - P3 controller authority published = NO
    - Discovery authorization without controller = fail-closed / NOT_TESTABLE
    - synthetic authority cannot satisfy production controller requirement
    - stale/foreign implementation authority rejected
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

    authority = _exact_authority()
    service = H40LifecycleAuthorityService.production(
        implementation_authority=authority,
    )

    # 3. Discovery authorization without controller = fail-closed / NOT_TESTABLE
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

    # 4. Synthetic authority cannot satisfy production controller requirement
    synthetic_ctrl = _synthesize_controller_authority(authority)
    with pytest.raises(ValueError, match="controller authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=authority,
            controller_authority=synthetic_ctrl,
        )

    # 5. Stale / foreign implementation authority rejected
    foreign_evidence = H40RequiredTestCIEvidenceIdentity(
        evidence_manifest_artifact_path=EXACT_EVIDENCE_MANIFEST_PATH,
        evidence_manifest_sha256=EXACT_EVIDENCE_MANIFEST_SHA256,
        tested_commit_sha="f" * 40,
    )
    foreign_authority = H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=EXACT_GOVERNANCE_HASH,
        f01_implementation_acceptance_artifact_path=EXACT_ACCEPTANCE_PATH,
        f01_implementation_acceptance_commit_sha=EXACT_ACCEPTANCE_COMMIT,
        f01_implementation_commit_sha="f" * 40,
        required_test_ci_evidence_identity=foreign_evidence,
        schema_id="H40_LIFECYCLE_IMPLEMENTATION_AUTHORITY_V1",
    )
    with pytest.raises(ValueError, match="implementation authority object/hash mismatch"):
        H40LifecycleAuthorityService.production(
            implementation_authority=foreign_authority,
        )

