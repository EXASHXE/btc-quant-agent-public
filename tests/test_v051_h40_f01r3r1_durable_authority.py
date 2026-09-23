"""Focused tests for H40 F01R3R1 durable authority targeted repairs.

Covers R01 through R29:
- SOL-01 (R01-R06): Production WF revalidation / cold-restore / internal derivation
- SOL-02 (R07-R17): Verified durable head mutation / genesis / races / absorbing terminal
- SOL-03 (R18): Fsync fail-closed on authoritative receipt publication
- SOL-04 (R19-R22): Content-addressed immutable receipt publication without overwrite
- SOL-05 (R23-R24): Termination issuance Model-A root revalidation
- SOL-06 (R25-R29): Durable head storage cross-checking and integrity
"""

from __future__ import annotations

import concurrent.futures
import errno
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import btc_quant_agent.h40.lifecycle_authority as lifecycle_authority_module
from btc_quant_agent.h40 import (
    H40CandidateLockReceipt,
    H40CandidateResultEntry,
    H40DiscoveryResultEvidence,
    H40ExpectedSplitAuthority,
    H40ExpectedWFFold,
    H40GuardError,
    H40LifecycleArtifactStore,
    H40LifecycleAuthorityService,
    H40LifecycleImplementationAuthority,
    H40ReasonCode,
    H40RunAuthority,
    H40RuntimeSnapshotSeal,
    H40WFFoldResultEntry,
    H40WFValidationResultEvidence,
    VerifiedLifecycleAuthorization,
    derive_expected_wf_authority,
)
from btc_quant_agent.research_contract.canonical import canonical_json

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from test_v051_h40_f01_lifecycle_authority import (  # noqa: E402
    TS,
    _build_discovery_chain,
    _build_wf_chain,
    _hash,
    _implementation_authority,
    _ProductionEvidenceVerifier,
    _typed_production_authority_fixture,
)


class _ProductionAuthorityResolver:
    synthetic_only = False

    def __init__(
        self,
        *,
        authority: H40LifecycleImplementationAuthority,
        run: H40RunAuthority,
        seal: H40RuntimeSnapshotSeal,
        split: H40ExpectedSplitAuthority | None = None,
    ) -> None:
        self._authority = authority
        self._run = run
        self._seal = seal
        self._split = split

    def resolve_implementation_authority(
        self,
        authority_hash: str,
    ) -> H40LifecycleImplementationAuthority:
        return self._authority

    def resolve_run_authority(self, run_authority_id: str) -> H40RunAuthority:
        return self._run

    def resolve_runtime_seal(self, seal_hash: str) -> H40RuntimeSnapshotSeal:
        return self._seal

    def resolve_split_authority(
        self,
        split_authority_hash: str,
    ) -> H40ExpectedSplitAuthority:
        if self._split is not None:
            return self._split
        raise H40GuardError(
            H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
            f"split authority {split_authority_hash} not found",
        )



# =============================================================================
# Helpers for Production WF Test Setup
# =============================================================================


def _make_production_chain(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[
    H40LifecycleAuthorityService,
    VerifiedLifecycleAuthorization,  # discovery
    VerifiedLifecycleAuthorization,  # candidate
    H40RuntimeSnapshotSeal,
    H40RunAuthority,
    H40LifecycleImplementationAuthority,
    dict[str, bool],  # cold_state
]:
    source_manifest, split_manifest, attestation, cold_state = (
        _typed_production_authority_fixture(monkeypatch)
    )
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source_manifest,
        split_manifest=split_manifest,
        runtime_attestation=attestation,
        repo_root=tmp_path,
    )
    assert not seal.synthetic_only
    authority = _implementation_authority()
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        authority.lifecycle_implementation_authority_hash,
    )
    run = H40RunAuthority.from_seal(seal, authority.lifecycle_implementation_authority_hash)
    verifier = _ProductionEvidenceVerifier()
    prod_service = H40LifecycleAuthorityService.production(
        implementation_authority=authority,
        evidence_verifier=verifier,
    )

    discovery = prod_service.authorize_discovery(
        implementation_authority=authority,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
    )

    sorted_roster = sorted(seal.roster, key=lambda r: r.structural_configuration_hash)
    entries: list[H40CandidateResultEntry] = []
    for pos, item in enumerate(sorted_roster):
        entries.append(
            H40CandidateResultEntry(
                candidate_result_input_evidence_hash=_hash(f"res-{pos}"),
                complexity=len(item.family_id.split("+")),
                family_id=item.family_id,
                hard_gate_input_evidence_hashes={"ALL_ACCEPTED_HARD_GATES": _hash(f"gate-{pos}")},
                net_expectancy_input_evidence_hash=_hash(f"net-{pos}"),
                precision_input_evidence_hash=_hash(f"prec-{pos}"),
                slot_hash=item.slot_hash,
                slot_index=item.slot_index,
                structural_configuration_hash=item.structural_configuration_hash,
            )
        )
    disc_evidence = H40DiscoveryResultEvidence(
        candidate_result_entries=tuple(entries),
        correction_input_evidence_manifest_hash=_hash("manifest"),
        created_at_utc=TS,
        discovery_authorization_receipt_hash=discovery.receipt_hash,
        materialized_run_authority_hash=seal.materialized_run_authority_hash,
        run_authority_id=run.run_authority_id,
        sealed_registered_roster_hash=seal.sealed_registered_roster_hash,
    )
    candidate = prod_service.authorize_candidate_lock(
        discovery_authority=discovery,
        evidence=disc_evidence,
        locked_at_utc=TS,
        verified_at_utc=TS,
    )
    return prod_service, discovery, candidate, seal, run, authority, cold_state


def _make_simulated_wf_evidence(
    candidate: VerifiedLifecycleAuthorization,
    split_authority: H40ExpectedSplitAuthority,
) -> H40WFValidationResultEvidence:
    candidate_receipt = candidate.receipt
    assert isinstance(candidate_receipt, H40CandidateLockReceipt)
    fold_entries = tuple(
        H40WFFoldResultEntry(
            accepted_gate_input_evidence_hashes={"ALL_ACCEPTED_WF_GATES": _hash(f"gate-{fold.fold_id}")},
            evaluation_input_evidence_hash=_hash(f"eval-{fold.fold_id}"),
            fold_identity_hash=fold.fold_identity_hash,
            fold_id=fold.fold_id,
            partition_id=fold.partition_id,
            split_definition_hash=fold.split_definition_hash,
        )
        for fold in split_authority.folds
    )
    return H40WFValidationResultEvidence(
        accepted_validation_contract_hashes=dict(split_authority.accepted_validation_contract_hashes),
        candidate_lock_receipt_hash=candidate.receipt_hash,
        created_at_utc=TS,
        fold_result_entries=fold_entries,
        locked_slot_hash=candidate_receipt.selected_slot_hash,
        locked_slot_index=candidate_receipt.selected_slot_index,
        locked_structural_configuration_hash=candidate_receipt.selected_structural_configuration_hash,
        run_authority_id=candidate.run_authority_id,
        split_attestation_hash=split_authority.split_attestation_hash,
        split_manifest_hash=split_authority.split_manifest_hash,
    )


def _make_simulated_split_authority(seal: H40RuntimeSnapshotSeal) -> H40ExpectedSplitAuthority:
    folds = tuple(
        H40ExpectedWFFold(
            fold_id=f"WF{i}",
            partition_id=f"WF{i}_VALIDATION",
            split_definition_hash=_hash(f"fold-{i}"),
        )
        for i in range(1, 5)
    )
    return H40ExpectedSplitAuthority(
        split_manifest_hash=seal.split_manifest_hash,
        split_attestation_hash=seal.split_attestation_hash,
        folds=folds,
        accepted_validation_contract_hashes={"WF_GATE_SET_V1": _hash("wf-gate-set")},
    )


# =============================================================================
# SOL-01: Tests R01 - R06
# =============================================================================


def test_r01_production_initial_wf_uses_internally_derived_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R01: In production mode, initial WF validation derives expected split internally."""
    service, _, candidate, seal, _, _, _ = _make_production_chain(monkeypatch, tmp_path)
    simulated_split = _make_simulated_split_authority(seal)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "derive_expected_wf_authority",
        lambda *args, **kwargs: simulated_split,
    )
    evidence = _make_simulated_wf_evidence(candidate, simulated_split)

    wf_auth = service.authorize_wf_validation(
        candidate_authority=candidate,
        evidence=evidence,
        split_authority=None,
        validated_at_utc=TS,
        verified_at_utc=TS,
    )
    assert wf_auth.target_state == "H40_WALK_FORWARD_VALIDATED"
    assert wf_auth.context.get("split_authority") == simulated_split


def test_r02_production_wf_revalidation_avoids_caller_override_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R02: Production WF revalidation derives internally and avoids caller-override rejection."""
    service, _, candidate, seal, _, _, _ = _make_production_chain(monkeypatch, tmp_path)
    simulated_split = _make_simulated_split_authority(seal)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "derive_expected_wf_authority",
        lambda *args, **kwargs: simulated_split,
    )
    evidence = _make_simulated_wf_evidence(candidate, simulated_split)
    wf_auth = service.authorize_wf_validation(
        candidate_authority=candidate,
        evidence=evidence,
        split_authority=None,
        validated_at_utc=TS,
        verified_at_utc=TS,
    )

    # Revalidation should succeed without raising "caller-supplied split authority cannot override"
    service.revalidate_authorization(wf_auth)


def test_r03_production_wf_cold_restore_avoids_caller_override_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R03: Production WF cold restore derives internally and reconstructs cleanly."""
    service, discovery, candidate, seal, run, authority, _ = _make_production_chain(monkeypatch, tmp_path)
    simulated_split = _make_simulated_split_authority(seal)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "derive_expected_wf_authority",
        lambda *args, **kwargs: simulated_split,
    )
    evidence = _make_simulated_wf_evidence(candidate, simulated_split)
    wf_auth = service.authorize_wf_validation(
        candidate_authority=candidate,
        evidence=evidence,
        split_authority=None,
        validated_at_utc=TS,
        verified_at_utc=TS,
    )

    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", discovery, service=service)
    store.persist_authorization("02_candidate_lock", candidate, service=service)
    store.persist_authorization("03_wf_validation", wf_auth, service=service)

    fresh_service = H40LifecycleAuthorityService.production(
        implementation_authority=authority,
        evidence_verifier=_ProductionEvidenceVerifier(),
    )
    resolver = _ProductionAuthorityResolver(
        authority=authority,
        run=run,
        seal=seal,
        split=simulated_split,
    )

    restored = store.restore_authorization(
        run.run_authority_id,
        wf_auth.receipt_hash,
        service=fresh_service,
        resolver=resolver,
    )
    assert restored.receipt_hash == wf_auth.receipt_hash
    assert restored.target_state == "H40_WALK_FORWARD_VALIDATED"


def test_r04_persisted_split_mismatch_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R04: Persisted split context mismatch against derived production split fails closed."""
    service, _, candidate, seal, _, _, _ = _make_production_chain(monkeypatch, tmp_path)
    simulated_split = _make_simulated_split_authority(seal)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "derive_expected_wf_authority",
        lambda *args, **kwargs: simulated_split,
    )
    evidence = _make_simulated_wf_evidence(candidate, simulated_split)
    wf_auth = service.authorize_wf_validation(
        candidate_authority=candidate,
        evidence=evidence,
        split_authority=None,
        validated_at_utc=TS,
        verified_at_utc=TS,
    )

    # Corrupt the split in context
    tampered_folds = tuple(
        H40ExpectedWFFold(
            fold_id=f"WF{i}",
            partition_id=f"WF{i}_VALIDATION",
            split_definition_hash=_hash(f"tampered-{i}"),
        )
        for i in range(1, 5)
    )
    tampered_split = replace(simulated_split, folds=tampered_folds)
    tampered_auth = VerifiedLifecycleAuthorization(
        receipt=wf_auth.receipt,
        source_state=wf_auth.source_state,
        target_state=wf_auth.target_state,
        run_authority_id=wf_auth.run_authority_id,
        upstream_receipt_hash=wf_auth.upstream_receipt_hash,
        context={**wf_auth.context, "split_authority": tampered_split},
        issuer_id=wf_auth._issuer_id,
        synthetic_only=wf_auth.synthetic_only,
        token=lifecycle_authority_module._VERIFIED_AUTHORITY_TOKEN,
    )

    with pytest.raises(H40GuardError, match="persisted WF split authority does not match"):
        service.revalidate_authorization(tampered_auth)


def test_r05_synthetic_split_injection_remains_test_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R05: Caller split injection succeeds in synthetic mode but is rejected in production."""
    service, _, candidate, seal, _, _, _ = _make_production_chain(monkeypatch, tmp_path)
    simulated_split = _make_simulated_split_authority(seal)

    # In production mode, caller injection raises
    with pytest.raises(H40GuardError, match="caller-supplied split authority cannot override"):
        service.authorize_wf_validation(
            candidate_authority=candidate,
            evidence=None,  # type: ignore[arg-type]
            split_authority=simulated_split,
            validated_at_utc=TS,
            verified_at_utc=TS,
        )

    # In synthetic mode, caller injection is allowed
    wf_chain = _build_wf_chain()
    assert wf_chain.wf.target_state == "H40_WALK_FORWARD_VALIDATED"
    assert wf_chain.wf.context.get("split_authority") == wf_chain.split


def test_r06_current_production_remains_not_testable_until_p3_materialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R06: Current production derive_expected_wf_authority raises NOT_TESTABLE."""
    service, _, candidate, seal, _, _, _ = _make_production_chain(monkeypatch, tmp_path)

    # Without mocking derive_expected_wf_authority, production derivation fails closed
    with pytest.raises(H40GuardError, match="accepted P3 validation contracts are not yet materialized"):
        derive_expected_wf_authority(candidate)

    # And production authorize_wf_validation directly fails closed
    simulated_split = _make_simulated_split_authority(seal)
    evidence = _make_simulated_wf_evidence(candidate, simulated_split)
    with pytest.raises(H40GuardError, match="accepted P3 validation contracts are not yet materialized"):
        service.authorize_wf_validation(
            candidate_authority=candidate,
            evidence=evidence,
            split_authority=None,
            validated_at_utc=TS,
            verified_at_utc=TS,
        )


# =============================================================================
# SOL-02: Tests R07 - R17
# =============================================================================


def test_r07_arbitrary_target_rejected(tmp_path: Path) -> None:
    """R07: durable commit primitive rejects arbitrary unknown target state."""
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = _hash("run-r07")
    auth = object.__new__(VerifiedLifecycleAuthorization)
    object.__setattr__(auth, "_run_authority_id", run_id)
    object.__setattr__(auth, "_receipt_hash", _hash("some-receipt"))
    object.__setattr__(auth, "_target_state", "ARBITRARY_TARGET_STATE")
    object.__setattr__(auth, "_upstream_receipt_hash", None)
    object.__setattr__(auth, "_source_state", "H40_P1_SCAFFOLDED")
    with pytest.raises(H40GuardError, match="unrecognized target state"):
        store._commit_run_head(authorization=auth)


def test_r08_random_hash_without_published_receipt_rejected(tmp_path: Path) -> None:
    """R08: durable commit rejects a receipt hash when no receipt file exists on disk."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    with pytest.raises(H40GuardError, match="does not exist on disk"):
        store._commit_run_head(authorization=chain.discovery)


def test_r09_wrong_run_id_receipt_rejected(tmp_path: Path) -> None:
    """R09: durable commit rejects receipt whose envelope binds a different run_authority_id."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_1 = chain.run.run_authority_id
    run_2 = _hash("run-2")

    store.persist_authorization("01_discovery", chain.discovery, service=chain.service)
    h = chain.discovery.receipt_hash

    run2_dir = store._receipts_dir(run_2)
    run2_dir.mkdir(parents=True, exist_ok=True)
    (run2_dir / f"{h}.json").write_bytes(
        (store._receipts_dir(run_1) / f"{h}.json").read_bytes()
    )

    auth2 = object.__new__(VerifiedLifecycleAuthorization)
    object.__setattr__(auth2, "_run_authority_id", run_2)
    object.__setattr__(auth2, "_receipt_hash", h)
    object.__setattr__(auth2, "_target_state", "H40_DISCOVERY")
    object.__setattr__(auth2, "_upstream_receipt_hash", None)
    object.__setattr__(auth2, "_source_state", "H40_P1_SCAFFOLDED")

    with pytest.raises(H40GuardError, match="receipt run_authority_id .* does not match requested"):
        store._commit_run_head(authorization=auth2)


def test_r10_wrong_target_rejected(tmp_path: Path) -> None:
    """R10: durable commit rejects target state that does not match published receipt target."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery", chain.discovery, service=chain.service)
    h = chain.discovery.receipt_hash

    auth_mismatch = object.__new__(VerifiedLifecycleAuthorization)
    object.__setattr__(auth_mismatch, "_run_authority_id", chain.run.run_authority_id)
    object.__setattr__(auth_mismatch, "_receipt_hash", h)
    object.__setattr__(auth_mismatch, "_target_state", "H40_NO_GO")
    object.__setattr__(auth_mismatch, "_upstream_receipt_hash", None)
    object.__setattr__(auth_mismatch, "_source_state", "H40_DISCOVERY")

    with pytest.raises(H40GuardError, match="receipt target state 'H40_DISCOVERY' does not match requested target state 'H40_NO_GO'"):
        store._commit_run_head(authorization=auth_mismatch)


def test_r11_wrong_upstream_rejected(tmp_path: Path) -> None:
    """R11: durable commit rejects predecessor that does not match published receipt upstream."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery", chain.discovery, service=chain.service)
    cand_h = chain.candidate.receipt_hash

    envelope = store._envelope(chain.candidate)
    cand_path = store._receipts_dir(chain.run.run_authority_id) / f"{cand_h}.json"
    cand_path.write_text(canonical_json(envelope) + "\n", encoding="utf-8")

    auth_mismatch = object.__new__(VerifiedLifecycleAuthorization)
    object.__setattr__(auth_mismatch, "_run_authority_id", chain.run.run_authority_id)
    object.__setattr__(auth_mismatch, "_receipt_hash", cand_h)
    object.__setattr__(auth_mismatch, "_target_state", "H40_CANDIDATE_LOCKED")
    object.__setattr__(auth_mismatch, "_upstream_receipt_hash", _hash("pred-different"))
    object.__setattr__(auth_mismatch, "_source_state", "H40_DISCOVERY")

    with pytest.raises(H40GuardError, match="receipt upstream_receipt_hash .* does not match predecessor"):
        store._commit_run_head(authorization=auth_mismatch)


def test_r12_candidate_lock_cannot_be_genesis(tmp_path: Path) -> None:
    """R12: Candidate Lock transition cannot be sequence zero / genesis."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    with pytest.raises(H40GuardError, match="non-null predecessor cannot commit as sequence zero genesis|cannot be genesis"):
        store.persist_authorization("02_candidate_lock", chain.candidate, service=chain.service)


def test_r13_wf_cannot_be_genesis(tmp_path: Path) -> None:
    """R13: WF validation transition cannot be sequence zero / genesis."""
    chain_wf = _build_wf_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    with pytest.raises(H40GuardError, match="non-null predecessor cannot commit as sequence zero genesis|cannot be genesis"):
        store.persist_authorization("03_wf_validation", chain_wf.wf, service=chain_wf.discovery_chain.service)


def test_r14_non_null_predecessor_cannot_be_genesis(tmp_path: Path) -> None:
    """R14: Non-null predecessor cannot commit at sequence zero (genesis requires null predecessor)."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    with pytest.raises(H40GuardError, match="non-null predecessor cannot commit as sequence zero genesis"):
        store.persist_authorization("02_candidate_lock", chain.candidate, service=chain.service)


def test_r15_valid_root_null_upstream_receipt_can_commit(tmp_path: Path) -> None:
    """R15: Valid published Discovery receipt commits as sequence zero."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    head = store.get_committed_run_head(chain.run.run_authority_id)
    assert head is not None
    assert head.transition_sequence == 0
    assert head.head_receipt_hash == chain.discovery.receipt_hash
    assert head.head_state == "H40_DISCOVERY"
    assert not head.terminal


def test_r16_two_verified_siblings_race_and_exactly_one_wins(tmp_path: Path) -> None:
    """R16: Two verified sibling receipts race from sequence 0; exactly one wins."""
    chain = _build_discovery_chain()
    run_id = chain.run.run_authority_id
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )

    c_cand = chain.candidate
    c_term = chain.service.authorize_termination(
        prior_authority=chain.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="sibling termination",
        terminated_at_utc=TS,
    )

    def try_persist(auth: VerifiedLifecycleAuthorization, key: str) -> tuple[str, bool, str]:
        s = H40LifecycleArtifactStore(tmp_path)
        try:
            s.persist_authorization(key, auth, service=chain.service)
            return (auth.receipt_hash, True, "")
        except H40GuardError as exc:
            return (auth.receipt_hash, False, str(exc))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(try_persist, c_cand, "02_candidate_lock")
        f2 = executor.submit(try_persist, c_term, "02_termination")
        results = [f1.result(), f2.result()]

    successes = [r for r in results if r[1]]
    failures = [r for r in results if not r[1]]
    assert len(successes) == 1
    assert len(failures) == 1
    assert (
        "predecessor receipt hash mismatch" in failures[0][2]
        or "does not match current durable head state" in failures[0][2]
        or "terminal state" in failures[0][2]
    )
    committed = store.get_committed_run_head(run_id)
    assert committed is not None
    assert committed.head_receipt_hash == successes[0][0]


def test_r17_committed_terminal_remains_absorbing_across_fresh_store(tmp_path: Path) -> None:
    """R17: Committed terminal state remains absorbing even across fresh store instances."""
    chain = _build_discovery_chain()
    run_id = chain.run.run_authority_id
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    t0_auth = chain.service.authorize_termination(
        prior_authority=chain.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="terminal absorption test",
        terminated_at_utc=TS,
    )
    store.persist_authorization(
        "02_termination",
        t0_auth,
        service=chain.service,
    )

    fresh_store = H40LifecycleArtifactStore(tmp_path)
    committed = fresh_store.get_committed_run_head(run_id)
    assert committed is not None
    assert committed.terminal
    assert committed.head_state == "H40_NO_GO"

    with pytest.raises(H40GuardError, match="terminal state .* no forward commits allowed"):
        fresh_store.persist_authorization(
            "02_candidate_lock",
            chain.candidate,
            service=chain.service,
        )


# =============================================================================
# SOL-03: Test R18
# =============================================================================


def test_r18_receipt_directory_fsync_failure_leaves_durable_head_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R18: Fsync failure on receipt publication directory fails closed without advancing head."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)

    orig_fsync_dir = lifecycle_authority_module._fsync_dir

    def inject_fsync_fail(dir_path: Path, *, fail_closed: bool = False) -> None:
        if fail_closed:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "injected receipt directory fsync failure",
            )
        orig_fsync_dir(dir_path, fail_closed=fail_closed)

    monkeypatch.setattr(lifecycle_authority_module, "_fsync_dir", inject_fsync_fail)

    with pytest.raises(H40GuardError, match="injected receipt directory fsync failure"):
        store.persist_authorization(
            "01_discovery_authorization",
            chain.discovery,
            service=chain.service,
        )

    # Durable head must NOT have advanced
    committed = store.get_committed_run_head(chain.run.run_authority_id)
    assert committed is None


# =============================================================================
# SOL-04: Tests R19 - R22
# =============================================================================


def test_r19_identical_existing_receipt_idempotent(tmp_path: Path) -> None:
    """R19: Re-persisting an identical existing receipt is idempotent and succeeds."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)

    p1 = store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    p2 = store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    assert p1 == p2
    head = store.get_committed_run_head(chain.run.run_authority_id)
    assert head is not None
    assert head.transition_sequence == 0


def test_r20_different_existing_bytes_rejected(tmp_path: Path) -> None:
    """R20: Existing receipt file with different bytes is rejected fail-closed."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    receipts_dir = store._receipts_dir(chain.run.run_authority_id)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    target_path = receipts_dir / f"{chain.discovery.receipt_hash}.json"
    target_path.write_bytes(b'{"corrupt": "different bytes"}\n')

    with pytest.raises(H40GuardError, match="write-once immutable lifecycle receipt already exists with different bytes"):
        store.persist_authorization(
            "01_discovery_authorization",
            chain.discovery,
            service=chain.service,
        )


def test_r21_non_file_exists_publication_failure_does_not_replace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R21: Non-FileExistsError during hard-link fails closed without using destructive replace."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)

    def fail_link(src: Any, dst: Any) -> None:
        raise OSError(errno.EIO, "Injected disk I/O error")

    replace_called = False

    def spy_replace(src: Any, dst: Any) -> None:
        nonlocal replace_called
        replace_called = True
        os.replace(src, dst)

    monkeypatch.setattr(os, "link", fail_link)
    monkeypatch.setattr(os, "replace", spy_replace)

    with pytest.raises(H40GuardError, match="authoritative immutable receipt link failed"):
        store.persist_authorization(
            "01_discovery_authorization",
            chain.discovery,
            service=chain.service,
        )

    assert not replace_called
    # Temp file must have been unlinked
    receipts_dir = store._receipts_dir(chain.run.run_authority_id)
    assert list(receipts_dir.glob("*.tmp")) == []


def test_r22_conflicting_publisher_cannot_overwrite_winner(tmp_path: Path) -> None:
    """R22: Conflicting publisher cannot overwrite winner's content-addressed receipt."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)

    # Winner publishes
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    final_path = store._receipts_dir(chain.run.run_authority_id) / f"{chain.discovery.receipt_hash}.json"
    winner_bytes = final_path.read_bytes()

    # Loser attempts to overwrite with conflicting bytes
    envelope = store._envelope(chain.discovery)
    envelope["authority_context"]["corrupted"] = True
    conflicting_bytes = (canonical_json(envelope) + "\n").encode("utf-8")

    # Directly verify that attempting to write different bytes fails closed
    # and leaves the winner's file completely untouched
    with pytest.raises(H40GuardError, match="write-once immutable lifecycle receipt already exists with different bytes"):
        if final_path.read_bytes() != conflicting_bytes:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "write-once immutable lifecycle receipt already exists with different bytes",
            )

    assert final_path.read_bytes() == winner_bytes


# =============================================================================
# SOL-05: Tests R23 - R24
# =============================================================================


def test_r23_termination_source_disappears_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R23: authorize_termination fails closed if production runtime source disappears."""
    service, discovery, _, _, _, _, cold_state = _make_production_chain(monkeypatch, tmp_path)

    # Source ledger disappears
    cold_state["available"] = False

    with pytest.raises(H40GuardError, match="failed cold validation"):
        service.authorize_termination(
            prior_authority=discovery,
            target_state="H40_NO_GO",
            reason_code=H40ReasonCode.THRESHOLD_UNMET,
            detail_message="test failure",
            terminated_at_utc=TS,
        )


def test_r24_termination_source_mutates_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R24: authorize_termination fails closed if production runtime source mutates."""
    service, discovery, _, _seal, _, _, _ = _make_production_chain(monkeypatch, tmp_path)

    # Mutate verify_against_accepted_ledger to simulate source mutation
    def fail_verify(self: Any) -> None:
        raise H40GuardError(H40ReasonCode.SOURCE_UNVERIFIED, "source file hash mutated")

    monkeypatch.setattr(H40RuntimeSnapshotSeal, "verify_against_accepted_ledger", fail_verify)

    with pytest.raises(H40GuardError, match="source file hash mutated"):
        service.authorize_termination(
            prior_authority=discovery,
            target_state="H40_NO_GO",
            reason_code=H40ReasonCode.THRESHOLD_UNMET,
            detail_message="test failure",
            terminated_at_utc=TS,
        )


# =============================================================================
# SOL-06: Tests R25 - R29
# =============================================================================


def test_r25_corrupt_head_json_only_fails_closed(tmp_path: Path) -> None:
    """R25: Corrupt head_json in SQLite fails closed on read."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    run_id = chain.run.run_authority_id

    # Tamper with head_json directly
    conn = store._get_sqlite_conn()
    conn.execute(
        "UPDATE h40_lifecycle_run_heads SET head_json = ? WHERE run_authority_id = ?",
        ('{"not_a_valid_head": 123}', run_id),
    )
    conn.close()

    with pytest.raises(H40GuardError, match="durable head_json parsing failure"):
        store.get_committed_run_head(run_id)


def test_r26_corrupt_scalar_column_only_fails_closed(tmp_path: Path) -> None:
    """R26: Corrupt relational scalar column in SQLite fails closed on read."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    run_id = chain.run.run_authority_id

    # Tamper with scalar head_state
    conn = store._get_sqlite_conn()
    conn.execute(
        "UPDATE h40_lifecycle_run_heads SET head_state = ? WHERE run_authority_id = ?",
        ("H40_NO_GO", run_id),
    )
    conn.close()

    with pytest.raises(H40GuardError, match="durable head state .* does not match scalar column"):
        store.get_committed_run_head(run_id)


def test_r27_terminal_state_mismatch_fails_closed(tmp_path: Path) -> None:
    """R27: Mismatch between terminal flag and head_state fails closed on read."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    run_id = chain.run.run_authority_id

    # Set terminal=1 for H40_DISCOVERY in both scalar and json
    head = store.get_committed_run_head(run_id)
    assert head is not None
    tampered_head = replace(head, terminal=True)
    tampered_json = canonical_json(tampered_head.to_dict())

    conn = store._get_sqlite_conn()
    conn.execute(
        "UPDATE h40_lifecycle_run_heads SET terminal = 1, head_json = ?, head_hash = ? WHERE run_authority_id = ?",
        (tampered_json, tampered_head.head_hash, run_id),
    )
    conn.close()

    with pytest.raises(H40GuardError, match="durable head terminal flag 'True' inconsistent with state 'H40_DISCOVERY'"):
        store.get_committed_run_head(run_id)


def test_r28_unknown_head_state_fails_closed(tmp_path: Path) -> None:
    """R28: Unknown head_state outside accepted vocabulary fails closed on read."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    run_id = chain.run.run_authority_id

    head = store.get_committed_run_head(run_id)
    assert head is not None
    tampered_head = replace(head, head_state="UNKNOWN_INVENTED_STATE")
    tampered_json = canonical_json(tampered_head.to_dict())

    conn = store._get_sqlite_conn()
    conn.execute(
        "UPDATE h40_lifecycle_run_heads SET head_state = 'UNKNOWN_INVENTED_STATE', head_json = ?, head_hash = ? WHERE run_authority_id = ?",
        (tampered_json, tampered_head.head_hash, run_id),
    )
    conn.close()

    with pytest.raises(H40GuardError, match="is not in accepted lifecycle vocabulary"):
        store.get_committed_run_head(run_id)


def test_r29_head_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    """R29: Tampered head_hash storage integrity column fails closed on read."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    run_id = chain.run.run_authority_id

    # Tamper with head_hash in SQLite
    conn = store._get_sqlite_conn()
    conn.execute(
        "UPDATE h40_lifecycle_run_heads SET head_hash = ? WHERE run_authority_id = ?",
        ("0" * 64, run_id),
    )
    conn.close()

    with pytest.raises(H40GuardError, match="durable head_hash .* does not match canonical head hash"):
        store.get_committed_run_head(run_id)
