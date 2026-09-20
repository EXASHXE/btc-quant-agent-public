"""Synthetic/governance adversarial tests for accepted H40 FSA-F01."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

import pytest

from btc_quant_agent.h40 import (
    ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH,
    DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
    EXPECTED_LIFECYCLE_CHILD_HASHES,
    EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH,
    EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH,
    EXPECTED_PROTOCOL_AUTHORITY_HASH,
    EXPECTED_SEMANTIC_ROOT_HASH,
    EXPECTED_STRUCTURAL_LEDGER_HASH,
    H40CandidateLockReceipt,
    H40CandidateResultEntry,
    H40CandidateVerification,
    H40ConfirmationGuard,
    H40DiscoveryResultEvidence,
    H40ExpectedSplitAuthority,
    H40ExpectedWFFold,
    H40GuardError,
    H40LifecycleArtifactStore,
    H40LifecycleAuthorityService,
    H40LifecycleEvidenceVerifier,
    H40LifecycleImplementationAuthority,
    H40LifecycleState,
    H40LifecycleStateMachine,
    H40ProtectedSurfaceGuard,
    H40ProtocolIdentity,
    H40ReasonCode,
    H40RequiredTestCIEvidenceIdentity,
    H40RunAuthority,
    H40RuntimeRosterEntry,
    H40RuntimeSnapshotSeal,
    H40SourceManifest,
    H40SplitAttestation,
    H40SplitManifest,
    H40SyntheticAuthorityResolver,
    H40SyntheticEvidenceVerifier,
    H40WFFoldResultEntry,
    H40WFValidationResultEvidence,
    VerifiedLifecycleAuthorization,
    compute_lifecycle_child_hashes,
    compute_lifecycle_governance_authority_hash,
    compute_lifecycle_semantic_root_hash,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    current_p1_authority_snapshot,
    lifecycle_governance_authority_object,
    lifecycle_semantic_contracts,
    materialize_h40_search_space_production,
    normalize_audit_timestamp,
)
from btc_quant_agent.research_contract.canonical import canonical_json, canonical_sha256

TS = "2026-09-20T00:00:00Z"


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _implementation_authority() -> H40LifecycleImplementationAuthority:
    return H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash=(
            EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH
        ),
        f01_implementation_acceptance_artifact_path="synthetic/f01_acceptance.md",
        f01_implementation_acceptance_commit_sha="b" * 40,
        f01_implementation_commit_sha="a" * 40,
        required_test_ci_evidence_identity=H40RequiredTestCIEvidenceIdentity(
            evidence_manifest_artifact_path="synthetic/local_evidence.json",
            evidence_manifest_sha256=_hash("local evidence"),
            tested_commit_sha="a" * 40,
        ),
    )


def _complete_synthetic_seal(snapshot_suffix: str = "base") -> H40RuntimeSnapshotSeal:
    ledger = materialize_h40_search_space_production()
    roster = tuple(sorted((
        H40RuntimeRosterEntry(
            family_id="+".join(family.value for family in slot.family_combination),
            slot_hash=slot.slot_hash,
            slot_index=slot.slot_index,
            structural_configuration_hash=slot.structural_configuration_hash,
        )
        for slot in ledger.slots
        if slot.status == "REGISTERED"
    ), key=lambda item: item.structural_configuration_hash))
    snapshot_hash = (
        current_p1_authority_snapshot().runtime_authority_snapshot_hash
        if snapshot_suffix == "base"
        else _hash(f"snapshot-{snapshot_suffix}")
    )
    return H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=snapshot_hash,
        source_manifest_hash=_hash(f"source-{snapshot_suffix}"),
        split_manifest_hash=_hash("split"),
        split_attestation_hash=_hash("attestation"),
        roster=roster,
        not_testable_slot_count=ledger.slot_count - len(roster),
    )


@dataclass(frozen=True)
class _DiscoveryChain:
    authority: H40LifecycleImplementationAuthority
    verifier: H40SyntheticEvidenceVerifier
    service: H40LifecycleAuthorityService
    seal: H40RuntimeSnapshotSeal
    run: H40RunAuthority
    discovery: VerifiedLifecycleAuthorization
    evidence: H40DiscoveryResultEvidence
    candidate: VerifiedLifecycleAuthorization


def _build_discovery_chain(
    *,
    seal: H40RuntimeSnapshotSeal | None = None,
    score_overrides: dict[int, tuple[str, str]] | None = None,
    failed_slots: frozenset[int] = frozenset(),
) -> _DiscoveryChain:
    authority = _implementation_authority()
    verifier = H40SyntheticEvidenceVerifier({})
    service = H40LifecycleAuthorityService.synthetic_for_tests(authority, verifier)
    active_seal = seal or _complete_synthetic_seal()
    run = H40RunAuthority.from_seal(
        active_seal,
        authority.lifecycle_implementation_authority_hash,
    )
    discovery = service.authorize_discovery(
        implementation_authority=authority,
        run_authority=run,
        seal=active_seal,
        authorized_at_utc=TS,
    )
    manifest_hash = verifier.add_payload_for_tests({
        "candidate_structural_configuration_hashes": [
            item.structural_configuration_hash for item in active_seal.roster
        ],
        "discovery_selection_correction_contract_hash": (
            DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH
        ),
        "roster_hash": active_seal.sealed_registered_roster_hash,
        "run_authority_id": run.run_authority_id,
        "schema_id": "H40_SYNTHETIC_CORRECTION_MANIFEST_V1",
    })
    entries: list[H40CandidateResultEntry] = []
    for position, roster_entry in enumerate(active_seal.roster):
        gate_id = "ALL_ACCEPTED_HARD_GATES"
        gate_hash = verifier.add_payload_for_tests({
            "gate_id": gate_id,
            "passed": roster_entry.slot_index not in failed_slots,
            "run_authority_id": run.run_authority_id,
            "schema_id": "H40_SYNTHETIC_CANDIDATE_GATE_EVIDENCE_V1",
            "structural_configuration_hash": roster_entry.structural_configuration_hash,
        })
        net, precision = (
            score_overrides.get(roster_entry.slot_index, (str(1000 - position), str(500 - position)))
            if score_overrides is not None
            else (str(1000 - position), str(500 - position))
        )
        net_hash = verifier.add_payload_for_tests({
            "adjusted_lcb": net,
            "correction_manifest_hash": manifest_hash,
            "metric_id": "NET_EXPECTANCY",
            "run_authority_id": run.run_authority_id,
            "schema_id": "H40_SYNTHETIC_CANDIDATE_METRIC_EVIDENCE_V1",
            "structural_configuration_hash": roster_entry.structural_configuration_hash,
        })
        precision_hash = verifier.add_payload_for_tests({
            "adjusted_lcb": precision,
            "correction_manifest_hash": manifest_hash,
            "metric_id": "PRECISION",
            "run_authority_id": run.run_authority_id,
            "schema_id": "H40_SYNTHETIC_CANDIDATE_METRIC_EVIDENCE_V1",
            "structural_configuration_hash": roster_entry.structural_configuration_hash,
        })
        gate_hashes = {gate_id: gate_hash}
        result_hash = verifier.add_payload_for_tests({
            "hard_gate_input_evidence_hashes": gate_hashes,
            "net_expectancy_input_evidence_hash": net_hash,
            "precision_input_evidence_hash": precision_hash,
            "run_authority_id": run.run_authority_id,
            "schema_id": "H40_SYNTHETIC_CANDIDATE_RESULT_INPUT_V1",
            "slot_hash": roster_entry.slot_hash,
            "slot_index": roster_entry.slot_index,
            "structural_configuration_hash": roster_entry.structural_configuration_hash,
        })
        entries.append(H40CandidateResultEntry(
            candidate_result_input_evidence_hash=result_hash,
            complexity=len(roster_entry.family_id.split("+")),
            family_id=roster_entry.family_id,
            hard_gate_input_evidence_hashes=gate_hashes,
            net_expectancy_input_evidence_hash=net_hash,
            precision_input_evidence_hash=precision_hash,
            slot_hash=roster_entry.slot_hash,
            slot_index=roster_entry.slot_index,
            structural_configuration_hash=roster_entry.structural_configuration_hash,
        ))
    evidence = H40DiscoveryResultEvidence(
        candidate_result_entries=tuple(entries),
        correction_input_evidence_manifest_hash=manifest_hash,
        created_at_utc=TS,
        discovery_authorization_receipt_hash=discovery.receipt_hash,
        materialized_run_authority_hash=active_seal.materialized_run_authority_hash,
        run_authority_id=run.run_authority_id,
        sealed_registered_roster_hash=active_seal.sealed_registered_roster_hash,
    )
    candidate = service.authorize_candidate_lock(
        discovery_authority=discovery,
        evidence=evidence,
        locked_at_utc=TS,
        verified_at_utc=TS,
    )
    return _DiscoveryChain(
        authority=authority,
        verifier=verifier,
        service=service,
        seal=active_seal,
        run=run,
        discovery=discovery,
        evidence=evidence,
        candidate=candidate,
    )


@dataclass(frozen=True)
class _WFChain:
    discovery_chain: _DiscoveryChain
    split: H40ExpectedSplitAuthority
    evidence: H40WFValidationResultEvidence
    wf: VerifiedLifecycleAuthorization


def _build_wf_chain(
    chain: _DiscoveryChain | None = None,
    *,
    failed_fold: str | None = None,
) -> _WFChain:
    active = chain or _build_discovery_chain()
    candidate_receipt = active.candidate.receipt
    assert isinstance(candidate_receipt, H40CandidateLockReceipt)
    folds = tuple(
        H40ExpectedWFFold(
            fold_id=f"WF{index}",
            partition_id=f"WF{index}_VALIDATION",
            split_definition_hash=_hash(f"fold-{index}"),
        )
        for index in range(1, 5)
    )
    contracts = {"WF_GATE_SET_V1": _hash("wf-gate-set")}
    split = H40ExpectedSplitAuthority(
        split_manifest_hash=active.seal.split_manifest_hash,
        split_attestation_hash=active.seal.split_attestation_hash,
        folds=folds,
        accepted_validation_contract_hashes=contracts,
    )
    fold_entries: list[H40WFFoldResultEntry] = []
    for fold in folds:
        gate_id = "ALL_ACCEPTED_WF_GATES"
        gate_hash = active.verifier.add_payload_for_tests({
            "fold_identity_hash": fold.fold_identity_hash,
            "gate_id": gate_id,
            "locked_structural_configuration_hash": (
                candidate_receipt.selected_structural_configuration_hash
            ),
            "passed": fold.fold_id != failed_fold,
            "run_authority_id": active.run.run_authority_id,
            "schema_id": "H40_SYNTHETIC_WF_GATE_EVIDENCE_V1",
            "split_attestation_hash": active.seal.split_attestation_hash,
            "split_manifest_hash": active.seal.split_manifest_hash,
        })
        gate_hashes = {gate_id: gate_hash}
        evaluation_hash = active.verifier.add_payload_for_tests({
            "accepted_gate_input_evidence_hashes": gate_hashes,
            "fold_identity_hash": fold.fold_identity_hash,
            "locked_structural_configuration_hash": (
                candidate_receipt.selected_structural_configuration_hash
            ),
            "run_authority_id": active.run.run_authority_id,
            "schema_id": "H40_SYNTHETIC_WF_EVALUATION_INPUT_V1",
            "split_attestation_hash": active.seal.split_attestation_hash,
            "split_manifest_hash": active.seal.split_manifest_hash,
        })
        fold_entries.append(H40WFFoldResultEntry(
            accepted_gate_input_evidence_hashes=gate_hashes,
            evaluation_input_evidence_hash=evaluation_hash,
            fold_identity_hash=fold.fold_identity_hash,
            fold_id=fold.fold_id,
            partition_id=fold.partition_id,
            split_definition_hash=fold.split_definition_hash,
        ))
    evidence = H40WFValidationResultEvidence(
        accepted_validation_contract_hashes=contracts,
        candidate_lock_receipt_hash=active.candidate.receipt_hash,
        created_at_utc=TS,
        fold_result_entries=tuple(fold_entries),
        locked_slot_hash=candidate_receipt.selected_slot_hash,
        locked_slot_index=candidate_receipt.selected_slot_index,
        locked_structural_configuration_hash=(
            candidate_receipt.selected_structural_configuration_hash
        ),
        run_authority_id=active.run.run_authority_id,
        split_attestation_hash=active.seal.split_attestation_hash,
        split_manifest_hash=active.seal.split_manifest_hash,
    )
    wf = active.service.authorize_wf_validation(
        candidate_authority=active.candidate,
        evidence=evidence,
        split_authority=split,
        validated_at_utc=TS,
        verified_at_utc=TS,
    )
    return _WFChain(active, split, evidence, wf)


def _typed_production_authority_fixture() -> tuple[H40SourceManifest, H40SplitManifest]:
    protocol_hash = H40ProtocolIdentity.default().protocol_hash
    source_manifest = H40SourceManifest.build_default(protocol_hash)
    reference = H40SplitManifest.build_preregistered_schedule(
        protocol_hash,
        source_manifest.manifest_hash,
    )
    candidate = replace(reference, is_authoritative=True)
    attestation = H40SplitAttestation.create(
        protocol_identity_hash=protocol_hash,
        source_manifest_hash=source_manifest.manifest_hash,
        split_hash=candidate.split_hash,
        btc_source_id="BTCUSDT_USD_M_1H",
        btc_locator="synthetic/btc.parquet",
        btc_file_sha256=_hash("btc file"),
        btc_membership_sha256=_hash("btc membership"),
        btc_timestamp_count=1,
        eth_source_id="ETHUSDT_USD_M_1H",
        eth_locator="synthetic/eth.parquet",
        eth_file_sha256=_hash("eth file"),
        eth_membership_sha256=_hash("eth membership"),
        eth_timestamp_count=1,
        is_production_canonical=True,
    )
    return source_manifest, replace(candidate, attestation=attestation)


def _persist_candidate_chain(
    tmp_path: Path,
    chain: _DiscoveryChain,
) -> H40LifecycleArtifactStore:
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        revalidate=chain.service.revalidate_authorization,
    )
    store.persist_authorization(
        "02_candidate_lock",
        chain.candidate,
        revalidate=chain.service.revalidate_authorization,
    )
    return store


def _fresh_synthetic_restore_authority(
    chain: _DiscoveryChain,
    *,
    split_authorities: Sequence[H40ExpectedSplitAuthority] = (),
) -> tuple[
    H40LifecycleAuthorityService,
    H40SyntheticAuthorityResolver,
    H40SyntheticEvidenceVerifier,
]:
    verifier = H40SyntheticEvidenceVerifier(chain.verifier.export_payloads_for_tests())
    service = H40LifecycleAuthorityService.synthetic_for_tests(chain.authority, verifier)
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(chain.authority,),
        run_authorities=(chain.run,),
        runtime_seals=(chain.seal,),
        split_authorities=split_authorities,
    )
    return service, resolver, verifier


def _rewrite_context_field(path: Path, field_name: str, value: object) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["authority_context"][field_name] = value
    path.write_text(canonical_json(raw) + "\n", encoding="utf-8")


def test_t01_accepted_hash_tree() -> None:
    assert compute_lifecycle_child_hashes() == dict(EXPECTED_LIFECYCLE_CHILD_HASHES)
    assert compute_lifecycle_semantic_root_hash() == EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH


@pytest.mark.parametrize("child_name", sorted(EXPECTED_LIFECYCLE_CHILD_HASHES))
def test_t02_semantic_mutation_propagation(child_name: str) -> None:
    contracts = lifecycle_semantic_contracts()
    contracts[child_name]["schema_id"] += "_MUTATED"
    assert compute_lifecycle_child_hashes(contracts)[child_name] != EXPECTED_LIFECYCLE_CHILD_HASHES[child_name]
    assert compute_lifecycle_semantic_root_hash(contracts) != EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH


def test_t03_scientific_hashes_unchanged() -> None:
    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH
    assert compute_semantic_root_hash() == EXPECTED_SEMANTIC_ROOT_HASH
    assert materialize_h40_search_space_production().structural_ledger_hash == EXPECTED_STRUCTURAL_LEDGER_HASH


def test_t04_governance_authority() -> None:
    assert lifecycle_governance_authority_object()["schema_id"] == "H40_LIFECYCLE_GOVERNANCE_AUTHORITY_V2"
    assert compute_lifecycle_governance_authority_hash() == EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH


def test_t05_adjacency_alone_denied() -> None:
    machine = H40LifecycleStateMachine()
    with pytest.raises(H40GuardError, match="Direct lifecycle adjacency"):
        machine.transition_to(H40LifecycleState.H40_DISCOVERY)
    assert machine.current_state is H40LifecycleState.H40_P1_SCAFFOLDED


@pytest.mark.parametrize("forged", [True, "AUTHORIZED", Path("receipt.json"), {}, {"receipt_schema_id": "x"}])
def test_t06_primitive_dict_path_denied(forged: object) -> None:
    machine = H40LifecycleStateMachine()
    with pytest.raises(TypeError):
        machine.transition_with_verified_authority(forged)  # type: ignore[arg-type]


def test_t07_implementation_authority_required() -> None:
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH is None
    service = H40LifecycleAuthorityService.production()
    authority = _implementation_authority()
    seal = _complete_synthetic_seal()
    run = H40RunAuthority.from_seal(seal, authority.lifecycle_implementation_authority_hash)
    with pytest.raises(H40GuardError) as exc_info:
        service.authorize_discovery(
            implementation_authority=authority,
            run_authority=run,
            seal=seal,
            authorized_at_utc=TS,
        )
    assert exc_info.value.reason_code == H40ReasonCode.NOT_TESTABLE


def test_t08_historical_sha_not_current_head_equality() -> None:
    chain = _build_discovery_chain()
    assert "code_commit_sha" not in chain.run.to_dict()
    assert chain.discovery.target_state == "H40_DISCOVERY"


def test_t09_deterministic_run_authority_and_label_independence() -> None:
    authority = _implementation_authority()
    seal = _complete_synthetic_seal()
    run = H40RunAuthority.from_seal(seal, authority.lifecycle_implementation_authority_hash)
    assert run.run_authority_id == canonical_sha256(run.to_dict())
    assert "label" not in inspect.signature(H40RunAuthority.from_seal).parameters
    for field_name in H40RunAuthority._KEYS - {"schema_id"}:
        mutated = replace(run, **{field_name: _hash(field_name)})
        assert mutated.run_authority_id != run.run_authority_id


def test_t10_roster_complete_and_sealed() -> None:
    seal = _complete_synthetic_seal()
    assert seal.total_slot_count == 168
    assert seal.registered_slot_count == 18
    seal.verify_against_accepted_ledger()
    incomplete = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=seal.runtime_authority_snapshot_hash,
        source_manifest_hash=seal.source_manifest_hash,
        split_manifest_hash=seal.split_manifest_hash,
        split_attestation_hash=seal.split_attestation_hash,
        roster=seal.roster[:-1],
        not_testable_slot_count=151,
    )
    with pytest.raises(H40GuardError, match="exact complete"):
        incomplete.verify_against_accepted_ledger()
    with pytest.raises(ValueError):
        H40RuntimeSnapshotSeal.synthetic_for_tests(
            runtime_authority_snapshot_hash=seal.runtime_authority_snapshot_hash,
            source_manifest_hash=seal.source_manifest_hash,
            split_manifest_hash=seal.split_manifest_hash,
            split_attestation_hash=seal.split_attestation_hash,
            roster=seal.roster + (seal.roster[0],),
            not_testable_slot_count=149,
        )


def test_t11_post_seal_source_change() -> None:
    authority = _implementation_authority()
    old = _complete_synthetic_seal()
    with pytest.raises((AttributeError, TypeError)):
        old.roster += (old.roster[0],)  # type: ignore[misc]
    new = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=_hash("promoted snapshot"),
        source_manifest_hash=old.source_manifest_hash,
        split_manifest_hash=old.split_manifest_hash,
        split_attestation_hash=old.split_attestation_hash,
        roster=old.roster,
        not_testable_slot_count=old.not_testable_slot_count,
    )
    old_run = H40RunAuthority.from_seal(old, authority.lifecycle_implementation_authority_hash)
    new_run = H40RunAuthority.from_seal(new, authority.lifecycle_implementation_authority_hash)
    assert old_run.run_authority_id != new_run.run_authority_id
    assert old_run.semantic_root_hash == new_run.semantic_root_hash == EXPECTED_SEMANTIC_ROOT_HASH


@pytest.mark.parametrize(
    "bad",
    [
        "2026-09-20T00:00:00+00:00", "2026-09-20T00:00:00.000000Z",
        "2026-09-20T00:00:00", "2026-02-29T00:00:00Z",
        "2026-09-20T00:00:60Z", "２０２６-09-20T00:00:00Z",
    ],
)
def test_t12_exact_timestamp_parser(bad: str) -> None:
    assert normalize_audit_timestamp(TS) == TS
    with pytest.raises(ValueError):
        normalize_audit_timestamp(bad)


@pytest.mark.parametrize("mode", ["missing", "extra", "duplicate"])
def test_t13_candidate_evidence_completeness(mode: str) -> None:
    chain = _build_discovery_chain()
    entries = list(chain.evidence.candidate_result_entries)
    if mode == "missing":
        entries.pop()
    elif mode == "extra":
        entries.append(entries[-1])
    else:
        entries[1] = entries[0]
    entries.sort(key=lambda item: item.structural_configuration_hash)
    altered = replace(chain.evidence, candidate_result_entries=tuple(entries))
    with pytest.raises(H40GuardError):
        chain.service.authorize_candidate_lock(
            discovery_authority=chain.discovery,
            evidence=altered,
            locked_at_utc=TS,
            verified_at_utc=TS,
        )


def test_t14_forged_candidate_denied() -> None:
    chain = _build_discovery_chain()
    receipt = chain.candidate.receipt
    assert isinstance(receipt, H40CandidateLockReceipt)
    forged = replace(receipt, selected_slot_index=(receipt.selected_slot_index + 1) % 168)
    with pytest.raises(H40GuardError, match="Synthetic lifecycle authority"):
        H40LifecycleStateMachine().transition_with_verified_authority(chain.discovery)
    machine = H40LifecycleStateMachine.synthetic_for_tests()
    machine.transition_with_verified_authority(chain.discovery)
    with pytest.raises(TypeError):
        machine.transition_with_verified_authority(forged)  # type: ignore[arg-type]
    assert "selection_rank" not in H40DiscoveryResultEvidence._KEYS


def test_t15_final_candidate_selection_order_mechanics() -> None:
    """Covers final ordering only; statistical correction science remains deferred."""
    ledger = materialize_h40_search_space_production()
    chosen_slots = (
        ledger.slots[0], ledger.slots[1], ledger.slots[2], ledger.slots[3],
        ledger.slots[4], ledger.slots[120],
    )
    roster = tuple(sorted((
        H40RuntimeRosterEntry(
            family_id="+".join(f.value for f in slot.family_combination),
            slot_hash=slot.slot_hash,
            slot_index=slot.slot_index,
            structural_configuration_hash=slot.structural_configuration_hash,
        )
        for slot in chosen_slots
    ), key=lambda item: item.structural_configuration_hash))
    seal = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=_hash("synthetic snapshot"),
        source_manifest_hash=_hash("synthetic source"),
        split_manifest_hash=_hash("synthetic split"),
        split_attestation_hash=_hash("synthetic attestation"),
        roster=roster,
        not_testable_slot_count=162,
    )
    scores = {
        0: ("100", "100"),  # rejected by hard gate despite dominant scores
        1: ("8", "100"),    # loses on net-expectancy LCB
        2: ("10", "8"),     # loses on precision LCB
        3: ("10", "10"),    # tied single-family finalist
        4: ("10", "10"),    # tied single-family finalist
        120: ("10", "10"),  # loses to single-family finalists on complexity
    }
    chain = _build_discovery_chain(
        seal=seal,
        score_overrides=scores,
        failed_slots=frozenset({0}),
    )
    receipt = chain.candidate.receipt
    assert isinstance(receipt, H40CandidateLockReceipt)
    eligible_tied = [item for item in seal.roster if item.slot_index in {3, 4}]
    expected = min(
        eligible_tied,
        key=lambda item: (len(item.family_id.split("+")), item.structural_configuration_hash),
    )
    assert receipt.selected_structural_configuration_hash == expected.structural_configuration_hash


def test_t16_no_runner_up() -> None:
    chain = _build_discovery_chain()
    termination = chain.service.authorize_termination(
        prior_authority=chain.candidate,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="synthetic locked-candidate failure",
        terminated_at_utc=TS,
    )
    machine = H40LifecycleStateMachine.synthetic_for_tests()
    machine.transition_with_verified_authority(chain.discovery)
    machine.transition_with_verified_authority(chain.candidate)
    machine.transition_with_verified_authority(termination)
    assert machine.current_state is H40LifecycleState.H40_NO_GO
    with pytest.raises(H40GuardError):
        machine.transition_with_verified_authority(chain.candidate)


def test_t17_cross_run_candidate_replay_denied() -> None:
    chain = _build_discovery_chain()
    altered = replace(chain.evidence, run_authority_id=_hash("foreign run"))
    with pytest.raises(H40GuardError, match="lineage"):
        chain.service.authorize_candidate_lock(
            discovery_authority=chain.discovery,
            evidence=altered,
            locked_at_utc=TS,
            verified_at_utc=TS,
        )


def test_t18_cross_roster_replay_denied() -> None:
    chain = _build_discovery_chain()
    altered = replace(chain.evidence, sealed_registered_roster_hash=_hash("foreign roster"))
    with pytest.raises(H40GuardError, match="lineage"):
        chain.service.authorize_candidate_lock(
            discovery_authority=chain.discovery,
            evidence=altered,
            locked_at_utc=TS,
            verified_at_utc=TS,
        )


def test_t19_bare_wf_boolean_denied() -> None:
    wf = _build_wf_chain()
    payload = wf.evidence.to_dict()
    payload["all_wf_gates_passed"] = True
    with pytest.raises(ValueError, match="extra"):
        H40WFValidationResultEvidence.from_dict(payload)
    with pytest.raises(TypeError):
        wf.discovery_chain.service.authorize_wf_validation(
            candidate_authority=wf.discovery_chain.candidate,
            evidence=True,  # type: ignore[arg-type]
            split_authority=wf.split,
            validated_at_utc=TS,
            verified_at_utc=TS,
        )


@pytest.mark.parametrize("mode", ["missing", "duplicate", "extra", "reordered"])
def test_t20_incomplete_wf_fold_set_denied(mode: str) -> None:
    wf = _build_wf_chain()
    folds = list(wf.evidence.fold_result_entries)
    if mode == "missing":
        folds.pop()
    elif mode == "duplicate":
        folds[1] = folds[0]
    elif mode == "extra":
        folds.append(folds[-1])
    else:
        folds.reverse()
    altered = replace(wf.evidence, fold_result_entries=tuple(folds))
    with pytest.raises(H40GuardError, match="fold set"):
        wf.discovery_chain.service.authorize_wf_validation(
            candidate_authority=wf.discovery_chain.candidate,
            evidence=altered,
            split_authority=wf.split,
            validated_at_utc=TS,
            verified_at_utc=TS,
        )


def test_t21_cross_candidate_wf_replay_denied() -> None:
    wf = _build_wf_chain()
    altered = replace(wf.evidence, locked_structural_configuration_hash=_hash("foreign candidate"))
    with pytest.raises(H40GuardError, match="lineage"):
        wf.discovery_chain.service.authorize_wf_validation(
            candidate_authority=wf.discovery_chain.candidate,
            evidence=altered,
            split_authority=wf.split,
            validated_at_utc=TS,
            verified_at_utc=TS,
        )


def test_t22_cross_split_wf_replay_denied() -> None:
    wf = _build_wf_chain()
    altered = replace(wf.evidence, split_attestation_hash=_hash("foreign attestation"))
    with pytest.raises(H40GuardError, match="lineage"):
        wf.discovery_chain.service.authorize_wf_validation(
            candidate_authority=wf.discovery_chain.candidate,
            evidence=altered,
            split_authority=wf.split,
            validated_at_utc=TS,
            verified_at_utc=TS,
        )


def test_t23_failed_wf_gate_terminates() -> None:
    wf = _build_wf_chain(failed_fold="WF2")
    assert wf.wf.target_state == "H40_NO_GO"
    assert wf.wf.receipt.receipt_schema_id == "H40_RECEIPT_TERMINATION_V2"
    assert not hasattr(wf.wf.receipt, "wf_validation_result_evidence_hash")


@pytest.mark.parametrize("tamper_target", ["receipt", "evidence"])
def test_t24_persistence_tamper(tmp_path: Path, tamper_target: str) -> None:
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    path = store.persist_authorization(
        "02_candidate_lock",
        chain.candidate,
        revalidate=chain.service.revalidate_authorization,
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if tamper_target == "receipt":
        raw["receipt"]["locked_at_utc"] = "2026-09-20T00:00:01Z"
    else:
        raw["bound_evidence"]["created_at_utc"] = "2026-09-20T00:00:01Z"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(H40GuardError, match="content hash"):
        store.restore_receipt(chain.run.run_authority_id, "02_candidate_lock")


def test_t25_upstream_receipt_substitution() -> None:
    first = _build_discovery_chain()
    second = _build_discovery_chain(seal=_complete_synthetic_seal("other"))
    machine = H40LifecycleStateMachine.synthetic_for_tests()
    machine.transition_with_verified_authority(first.discovery)
    with pytest.raises(H40GuardError):
        machine.transition_with_verified_authority(second.candidate)


def test_t26_idempotent_persistence_revalidates(tmp_path: Path) -> None:
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    calls = 0

    def revalidate(authority: VerifiedLifecycleAuthorization) -> None:
        nonlocal calls
        calls += 1
        chain.service.revalidate_authorization(authority)

    first = store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        revalidate=revalidate,
    )
    second = store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        revalidate=revalidate,
    )
    assert first == second
    assert calls == 3
    fresh_service = H40LifecycleAuthorityService.synthetic_for_tests(
        chain.authority,
        H40SyntheticEvidenceVerifier(chain.verifier.export_payloads_for_tests()),
    )
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(chain.authority,),
        run_authorities=(chain.run,),
        runtime_seals=(chain.seal,),
    )
    restored = store.restore_authorization(
        chain.run.run_authority_id,
        "01_discovery_authorization",
        service=fresh_service,
        resolver=resolver,
    )
    assert restored.receipt_hash == chain.discovery.receipt_hash
    assert restored is not chain.discovery


def test_t27_confirmation_ready_is_waiting_only() -> None:
    wf = _build_wf_chain()
    ready = wf.discovery_chain.service.authorize_confirmation_ready(
        wf_authority=wf.wf,
        prepared_at_utc=TS,
    )
    machine = H40LifecycleStateMachine.synthetic_for_tests()
    machine.transition_with_verified_authority(wf.discovery_chain.discovery)
    machine.transition_with_verified_authority(wf.discovery_chain.candidate)
    machine.transition_with_verified_authority(wf.wf)
    machine.transition_with_verified_authority(ready)
    assert machine.current_state is H40LifecycleState.H40_CONFIRMATION_READY
    assert not hasattr(ready.receipt, "outcomes")
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfirmationGuard().assert_outcomes_accessible()
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_t28_f02_transition_denied() -> None:
    machine = H40LifecycleStateMachine.synthetic_for_tests()
    with pytest.raises(H40GuardError) as exc_info:
        machine.transition_to(H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE)
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY
    assert H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE not in (
        H40LifecycleStateMachine.VALID_TRANSITIONS[H40LifecycleState.H40_CONFIRMATION_READY]
    )


@pytest.mark.parametrize("target", ["H40_NO_GO", "NOT_TESTABLE"])
def test_t29_terminal_states_absorbing(target: str) -> None:
    chain = _build_discovery_chain()
    termination = chain.service.authorize_termination(
        prior_authority=chain.discovery,
        target_state=target,
        reason_code=H40ReasonCode.NOT_TESTABLE,
        detail_message="synthetic terminal",
        terminated_at_utc=TS,
    )
    machine = H40LifecycleStateMachine.synthetic_for_tests()
    machine.transition_with_verified_authority(chain.discovery)
    machine.transition_with_verified_authority(termination)
    assert machine.current_state.value == target
    with pytest.raises(H40GuardError):
        machine.transition_with_verified_authority(chain.candidate)


def test_t30_protected_surfaces_remain_protected() -> None:
    for path in ("artifacts/h39_protected/results.json", "artifacts/final_holdout/data.parquet"):
        with pytest.raises(H40GuardError) as exc_info:
            H40ProtectedSurfaceGuard.assert_surface_allowed(path)
        assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED


def test_a00_production_seal_derives_typed_verified_authority(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_manifest, split_manifest = _typed_production_authority_fixture()
    calls: list[tuple[H40SourceManifest, Path | str]] = []

    def assert_verified(
        self: H40SplitManifest,
        source: H40SourceManifest,
        repo_root: Path | str,
    ) -> None:
        assert self is split_manifest
        calls.append((source, repo_root))

    monkeypatch.setattr(H40SplitManifest, "assert_authoritative", assert_verified)
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source_manifest,
        split_manifest=split_manifest,
        repo_root=tmp_path,
    )
    assert calls == [(source_manifest, tmp_path)]
    assert not seal.synthetic_only
    assert seal.source_manifest_hash == source_manifest.manifest_hash
    assert seal.split_manifest_hash == split_manifest.split_hash
    assert split_manifest.attestation is not None
    assert seal.split_attestation_hash == split_manifest.attestation.attestation_hash
    seal.verify_against_accepted_ledger()


def test_a01_arbitrary_source_manifest_hash_cannot_create_production_seal() -> None:
    parameters = inspect.signature(H40RuntimeSnapshotSeal.from_verified_authority).parameters
    assert "source_manifest_hash" not in parameters
    assert not hasattr(H40RuntimeSnapshotSeal, "from_current_production_authority")


def test_a02_arbitrary_split_manifest_hash_cannot_create_production_seal() -> None:
    parameters = inspect.signature(H40RuntimeSnapshotSeal.from_verified_authority).parameters
    assert "split_manifest_hash" not in parameters


def test_a03_arbitrary_split_attestation_hash_cannot_create_production_seal() -> None:
    parameters = inspect.signature(H40RuntimeSnapshotSeal.from_verified_authority).parameters
    assert "split_attestation_hash" not in parameters


def test_a04_unverified_typed_source_split_cannot_create_production_seal(
    tmp_path: Path,
) -> None:
    protocol_hash = H40ProtocolIdentity.default().protocol_hash
    source_manifest = H40SourceManifest.build_default(protocol_hash)
    split_manifest = H40SplitManifest.build_preregistered_schedule(
        protocol_hash,
        source_manifest.manifest_hash,
    )
    with pytest.raises(H40GuardError) as exc_info:
        H40RuntimeSnapshotSeal.from_verified_authority(
            source_manifest=source_manifest,
            split_manifest=split_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_UNVERIFIED


def test_a05_split_assert_authoritative_failure_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_manifest, split_manifest = _typed_production_authority_fixture()

    def reject(
        self: H40SplitManifest,
        source: H40SourceManifest,
        repo_root: Path | str,
    ) -> None:
        del self, source, repo_root
        raise H40GuardError(H40ReasonCode.SOURCE_HASH_MISMATCH, "cold authority rejected")

    monkeypatch.setattr(H40SplitManifest, "assert_authoritative", reject)
    with pytest.raises(H40GuardError, match="cold authority rejected") as exc_info:
        H40RuntimeSnapshotSeal.from_verified_authority(
            source_manifest=source_manifest,
            split_manifest=split_manifest,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_HASH_MISMATCH


def test_a06_incomplete_registered_roster_fails() -> None:
    seal = _complete_synthetic_seal()
    incomplete = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=seal.runtime_authority_snapshot_hash,
        source_manifest_hash=seal.source_manifest_hash,
        split_manifest_hash=seal.split_manifest_hash,
        split_attestation_hash=seal.split_attestation_hash,
        roster=seal.roster[:-1],
        not_testable_slot_count=151,
    )
    with pytest.raises(H40GuardError, match="exact complete"):
        incomplete.verify_against_accepted_ledger()


def test_a07_extra_registered_roster_entry_fails() -> None:
    seal = _complete_synthetic_seal()
    extra_slot = next(
        slot for slot in materialize_h40_search_space_production().slots
        if slot.status == "NOT_TESTABLE"
    )
    extra = H40RuntimeRosterEntry(
        family_id="+".join(family.value for family in extra_slot.family_combination),
        slot_hash=extra_slot.slot_hash,
        slot_index=extra_slot.slot_index,
        structural_configuration_hash=extra_slot.structural_configuration_hash,
    )
    oversized = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=seal.runtime_authority_snapshot_hash,
        source_manifest_hash=seal.source_manifest_hash,
        split_manifest_hash=seal.split_manifest_hash,
        split_attestation_hash=seal.split_attestation_hash,
        roster=seal.roster + (extra,),
        not_testable_slot_count=149,
    )
    with pytest.raises(H40GuardError, match="exact complete"):
        oversized.verify_against_accepted_ledger()


def test_a08_duplicate_roster_entry_fails() -> None:
    seal = _complete_synthetic_seal()
    with pytest.raises(ValueError, match="duplicate"):
        H40RuntimeSnapshotSeal.synthetic_for_tests(
            runtime_authority_snapshot_hash=seal.runtime_authority_snapshot_hash,
            source_manifest_hash=seal.source_manifest_hash,
            split_manifest_hash=seal.split_manifest_hash,
            split_attestation_hash=seal.split_attestation_hash,
            roster=seal.roster + (seal.roster[0],),
            not_testable_slot_count=149,
        )


def test_a09_substituted_roster_entry_fails() -> None:
    seal = _complete_synthetic_seal()
    substitute_slot = next(
        slot for slot in materialize_h40_search_space_production().slots
        if slot.status == "NOT_TESTABLE"
    )
    substitute = H40RuntimeRosterEntry(
        family_id="+".join(family.value for family in substitute_slot.family_combination),
        slot_hash=substitute_slot.slot_hash,
        slot_index=substitute_slot.slot_index,
        structural_configuration_hash=substitute_slot.structural_configuration_hash,
    )
    altered = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=seal.runtime_authority_snapshot_hash,
        source_manifest_hash=seal.source_manifest_hash,
        split_manifest_hash=seal.split_manifest_hash,
        split_attestation_hash=seal.split_attestation_hash,
        roster=seal.roster[:-1] + (substitute,),
        not_testable_slot_count=150,
    )
    with pytest.raises(H40GuardError, match="exact complete"):
        altered.verify_against_accepted_ledger()


def test_a10_arbitrary_runtime_snapshot_hash_fails() -> None:
    seal = _complete_synthetic_seal("foreign")
    with pytest.raises(H40GuardError, match="runtime authority snapshot"):
        seal.verify_against_accepted_ledger()


def test_a11_caller_selected_production_counts_fail() -> None:
    seal = _complete_synthetic_seal()
    parameters = inspect.signature(H40RuntimeSnapshotSeal.from_verified_authority).parameters
    assert "registered_slot_count" not in parameters
    assert "not_testable_slot_count" not in parameters
    with pytest.raises(ValueError, match="must equal total"):
        H40RuntimeSnapshotSeal.synthetic_for_tests(
            runtime_authority_snapshot_hash=seal.runtime_authority_snapshot_hash,
            source_manifest_hash=seal.source_manifest_hash,
            split_manifest_hash=seal.split_manifest_hash,
            split_attestation_hash=seal.split_attestation_hash,
            roster=seal.roster,
            not_testable_slot_count=149,
        )


def test_a12_direct_constructor_cannot_manufacture_production_authority() -> None:
    seal = _complete_synthetic_seal()
    with pytest.raises(TypeError, match="must be issued"):
        H40RuntimeSnapshotSeal(
            runtime_authority_snapshot_hash=seal.runtime_authority_snapshot_hash,
            source_manifest_hash=seal.source_manifest_hash,
            split_manifest_hash=seal.split_manifest_hash,
            split_attestation_hash=seal.split_attestation_hash,
            roster=seal.roster,
            registered_slot_count=seal.registered_slot_count,
            not_testable_slot_count=seal.not_testable_slot_count,
        )


def test_a13_synthetic_seal_remains_test_only() -> None:
    seal = _complete_synthetic_seal()
    assert seal.synthetic_only
    assert "SYNTHETIC_TEST_ONLY" in canonical_json({
        "kind": "SYNTHETIC_TEST_ONLY",
        "seal_hash": seal.authority_context_hash,
    })


def test_a14_cold_restore_without_original_authorization_object(tmp_path: Path) -> None:
    chain = _build_discovery_chain()
    store = _persist_candidate_chain(tmp_path, chain)
    expected_hash = chain.candidate.receipt_hash
    service, resolver, _ = _fresh_synthetic_restore_authority(chain)
    del chain
    restored = store.restore_authorization(
        next((tmp_path / "artifacts/h40/lifecycle/runs").iterdir()).name,
        "02_candidate_lock",
        service=service,
        resolver=resolver,
    )
    assert restored.receipt_hash == expected_hash


def test_a15_cold_restore_detects_predecessor_substitution(tmp_path: Path) -> None:
    chain = _build_discovery_chain()
    store = _persist_candidate_chain(tmp_path, chain)
    service, resolver, _ = _fresh_synthetic_restore_authority(chain)
    path = store._path(chain.run.run_authority_id, "02_candidate_lock")
    _rewrite_context_field(path, "predecessor_receipt_hash", _hash("foreign predecessor"))
    with pytest.raises(H40GuardError, match="predecessor context"):
        store.restore_authorization(
            chain.run.run_authority_id,
            "02_candidate_lock",
            service=service,
            resolver=resolver,
        )


def test_a16_cold_restore_detects_run_authority_substitution(tmp_path: Path) -> None:
    chain = _build_discovery_chain()
    store = _persist_candidate_chain(tmp_path, chain)
    service, resolver, _ = _fresh_synthetic_restore_authority(chain)
    path = store._path(chain.run.run_authority_id, "02_candidate_lock")
    _rewrite_context_field(path, "run_authority_id", _hash("foreign run"))
    with pytest.raises(H40GuardError, match="storage boundary"):
        store.restore_authorization(
            chain.run.run_authority_id,
            "02_candidate_lock",
            service=service,
            resolver=resolver,
        )


def test_a17_cold_restore_detects_runtime_seal_substitution(tmp_path: Path) -> None:
    chain = _build_discovery_chain()
    store = _persist_candidate_chain(tmp_path, chain)
    service, resolver, _ = _fresh_synthetic_restore_authority(chain)
    path = store._path(chain.run.run_authority_id, "02_candidate_lock")
    _rewrite_context_field(path, "runtime_seal_hash", _hash("foreign seal"))
    with pytest.raises(H40GuardError, match="runtime seal"):
        store.restore_authorization(
            chain.run.run_authority_id,
            "02_candidate_lock",
            service=service,
            resolver=resolver,
        )


def test_a18_cold_restore_detects_split_authority_substitution(tmp_path: Path) -> None:
    wf = _build_wf_chain()
    store = _persist_candidate_chain(tmp_path, wf.discovery_chain)
    path = store.persist_authorization(
        "03_wf_validation",
        wf.wf,
        revalidate=wf.discovery_chain.service.revalidate_authorization,
    )
    service, resolver, _ = _fresh_synthetic_restore_authority(
        wf.discovery_chain,
        split_authorities=(wf.split,),
    )
    _rewrite_context_field(path, "split_authority_hash", _hash("foreign split authority"))
    with pytest.raises(H40GuardError, match="split authority"):
        store.restore_authorization(
            wf.discovery_chain.run.run_authority_id,
            "03_wf_validation",
            service=service,
            resolver=resolver,
        )


def test_a19_cold_restore_reruns_verifier_result(tmp_path: Path) -> None:
    chain = _build_discovery_chain()
    store = _persist_candidate_chain(tmp_path, chain)
    service, resolver, verifier = _fresh_synthetic_restore_authority(chain)
    assert verifier.verification_count == 0
    store.restore_authorization(
        chain.run.run_authority_id,
        "02_candidate_lock",
        service=service,
        resolver=resolver,
    )
    assert verifier.verification_count > 0


def test_a20_synthetic_verifier_rejected_by_production_service() -> None:
    with pytest.raises(ValueError, match="synthetic/test-only"):
        H40LifecycleAuthorityService.production(
            evidence_verifier=H40SyntheticEvidenceVerifier({})
        )


def test_a21_typed_future_non_synthetic_verifier_seam_exists() -> None:
    class FutureProductionVerifier:
        synthetic_only = False

        def verify_discovery_manifest(
            self,
            evidence: H40DiscoveryResultEvidence,
            entries: Sequence[H40CandidateResultEntry],
        ) -> None:
            del evidence, entries

        def verify_candidate(
            self,
            entry: H40CandidateResultEntry,
            *,
            run_authority_id: str,
            correction_manifest_hash: str,
        ) -> H40CandidateVerification:
            del entry, run_authority_id, correction_manifest_hash
            return H40CandidateVerification(True, Decimal(0), Decimal(0))

        def verify_wf_fold(
            self,
            entry: H40WFFoldResultEntry,
            *,
            evidence: H40WFValidationResultEvidence,
        ) -> bool:
            del entry, evidence
            return False

    verifier = FutureProductionVerifier()
    assert isinstance(verifier, H40LifecycleEvidenceVerifier)
    service = H40LifecycleAuthorityService.production(evidence_verifier=verifier)
    assert not service.synthetic_test_mode


def test_a22_production_without_accepted_verifier_remains_fail_closed() -> None:
    authority = _implementation_authority()
    seal = _complete_synthetic_seal()
    run = H40RunAuthority.from_seal(
        seal,
        authority.lifecycle_implementation_authority_hash,
    )
    with pytest.raises(H40GuardError) as exc_info:
        H40LifecycleAuthorityService.production().authorize_discovery(
            implementation_authority=authority,
            run_authority=run,
            seal=seal,
            authorized_at_utc=TS,
        )
    assert exc_info.value.reason_code == H40ReasonCode.NOT_TESTABLE


def test_a23_final_selection_order_mechanics_is_accurately_scoped() -> None:
    assert "r3r4" not in test_t15_final_candidate_selection_order_mechanics.__name__
    verifier = H40SyntheticEvidenceVerifier({})
    assert isinstance(verifier, H40LifecycleEvidenceVerifier)
    assert verifier.synthetic_only


def test_a24_p2_scientific_hashes_unchanged() -> None:
    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH
    assert compute_semantic_root_hash() == EXPECTED_SEMANTIC_ROOT_HASH
    assert materialize_h40_search_space_production().structural_ledger_hash == EXPECTED_STRUCTURAL_LEDGER_HASH


def test_a25_lifecycle_semantic_governance_hashes_unchanged() -> None:
    assert compute_lifecycle_semantic_root_hash() == EXPECTED_LIFECYCLE_SEMANTIC_ROOT_HASH
    assert compute_lifecycle_governance_authority_hash() == EXPECTED_LIFECYCLE_GOVERNANCE_AUTHORITY_HASH


def test_a26_f02_remains_sealed() -> None:
    assert H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE not in (
        H40LifecycleStateMachine.VALID_TRANSITIONS[H40LifecycleState.H40_CONFIRMATION_READY]
    )
    with pytest.raises(H40GuardError) as exc_info:
        H40ConfirmationGuard().assert_outcomes_accessible()
    assert exc_info.value.reason_code == H40ReasonCode.CONFIRMATION_NOT_READY


def test_a27_h39_and_final_holdout_remain_protected() -> None:
    for path in ("artifacts/h39_protected/results.json", "artifacts/final_holdout/data.parquet"):
        with pytest.raises(H40GuardError) as exc_info:
            H40ProtectedSurfaceGuard.assert_surface_allowed(path)
        assert exc_info.value.reason_code == H40ReasonCode.PROTECTED_SURFACE_DENIED
