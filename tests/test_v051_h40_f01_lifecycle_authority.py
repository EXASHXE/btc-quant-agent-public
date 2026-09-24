"""Synthetic/governance adversarial tests for accepted H40 FSA-F01."""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

import btc_quant_agent.h40.lifecycle_authority as lifecycle_authority_module
import btc_quant_agent.h40.search_space as search_space_module
import btc_quant_agent.h40.split_manifest as split_manifest_module
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
    H40DiscoveryAuthorizationReceipt,
    H40DiscoveryResultEvidence,
    H40DurableRunHead,
    H40ExecutionGuard,
    H40ExpectedSplitAuthority,
    H40ExpectedWFFold,
    H40GuardError,
    H40LifecycleArtifactStore,
    H40LifecycleAuthorityService,
    H40LifecycleEvidenceVerifier,
    H40LifecycleImplementationAuthority,
    H40LifecycleState,
    H40LifecycleStateMachine,
    H40ProductionDiscoveryEvidenceVerifier,
    H40ProtectedSurfaceGuard,
    H40ProtocolIdentity,
    H40ReasonCode,
    H40RequiredTestCIEvidenceIdentity,
    H40RunAuthority,
    H40RuntimeRosterEntry,
    H40RuntimeSnapshotSeal,
    H40RuntimeSourceSplitAttestation,
    H40SourceManifest,
    H40SourceRecord,
    H40SourceStatus,
    H40SourceValidationReceipt,
    H40SplitAttestation,
    H40SplitManifest,
    H40SyntheticAuthorityResolver,
    H40SyntheticEvidenceVerifier,
    H40TerminationReceipt,
    H40WFFoldResultEntry,
    H40WFValidationReceipt,
    H40WFValidationResultEvidence,
    VerifiedLifecycleAuthorization,
    assert_canonical_source_identity,
    compute_lifecycle_child_hashes,
    compute_lifecycle_governance_authority_hash,
    compute_lifecycle_semantic_root_hash,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    current_p1_authority_snapshot,
    derive_expected_wf_authority,
    derive_required_sources_for_slot,
    lifecycle_governance_authority_object,
    lifecycle_semantic_contracts,
    materialize_h40_search_space_production,
    materialize_runtime_source_split_authority,
    normalize_audit_timestamp,
)
from btc_quant_agent.h40.split_manifest import generate_hourly_range
from btc_quant_agent.h40.configuration_ledger import H40ConfigurationLedger
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


def _publish_mock_envelope(
    store: H40LifecycleArtifactStore,
    receipt: Any,
) -> str:
    h = receipt.receipt_sha256
    envelope = {
        "authority_context": {},
        "bound_evidence": None,
        "bound_evidence_sha256": None,
        "receipt": receipt.to_dict(),
        "receipt_sha256": h,
    }
    p = store._receipts_dir(receipt.run_authority_id) / f"{h}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(canonical_json(envelope) + "\n", encoding="utf-8")
    return h


def _make_mock_discovery_receipt(
    run_id: str,
    *,
    authorized_at_utc: str = TS,
) -> H40DiscoveryAuthorizationReceipt:
    return H40DiscoveryAuthorizationReceipt(
        authorized_at_utc=authorized_at_utc,
        discovery_selection_correction_contract_hash=_hash("correction"),
        execution_disabled=True,
        lifecycle_governance_authority_hash=_hash("gov"),
        lifecycle_implementation_authority_hash=_hash("impl"),
        materialized_run_authority_hash=_hash("run_auth"),
        not_testable_slot_count=150,
        protocol_authority_hash=_hash("proto"),
        registered_slot_count=18,
        run_authority_id=run_id,
        sealed_registered_roster_hash=_hash("roster"),
        semantic_root_hash=_hash("semantic"),
        source_manifest_hash=_hash("source"),
        split_attestation_hash=_hash("attest"),
        split_manifest_hash=_hash("split"),
        structural_ledger_hash=_hash("structural"),
        total_slot_count=168,
        upstream_receipt_hash=None,
    )


def _make_mock_candidate_receipt(
    run_id: str,
    upstream_receipt_hash: str,
    *,
    slot_index: int = 0,
    locked_at_utc: str = TS,
) -> H40CandidateLockReceipt:
    return H40CandidateLockReceipt(
        discovery_authorization_receipt_hash=upstream_receipt_hash,
        discovery_result_evidence_hash=_hash(f"evidence-{slot_index}"),
        locked_at_utc=locked_at_utc,
        materialized_run_authority_hash=_hash("run_auth"),
        run_authority_id=run_id,
        selected_slot_hash=_hash(f"slot-{slot_index}"),
        selected_slot_index=slot_index,
        selected_structural_configuration_hash=_hash(f"struct-{slot_index}"),
        upstream_receipt_hash=upstream_receipt_hash,
        verified_at_utc=locked_at_utc,
    )


def _make_mock_wf_receipt(
    run_id: str,
    upstream_receipt_hash: str,
    *,
    slot_index: int = 0,
    validated_at_utc: str = TS,
) -> H40WFValidationReceipt:
    return H40WFValidationReceipt(
        candidate_lock_receipt_hash=upstream_receipt_hash,
        locked_slot_hash=_hash(f"slot-{slot_index}"),
        locked_slot_index=slot_index,
        locked_structural_configuration_hash=_hash(f"struct-{slot_index}"),
        run_authority_id=run_id,
        upstream_receipt_hash=upstream_receipt_hash,
        validated_at_utc=validated_at_utc,
        verified_at_utc=validated_at_utc,
        wf_validation_result_evidence_hash=_hash("wf_evidence"),
    )


def _make_mock_termination_receipt(
    run_id: str,
    upstream_receipt_hash: str | None,
    *,
    source_state: str = "H40_DISCOVERY",
    target_state: str = "H40_NO_GO",
    reason_code: H40ReasonCode = H40ReasonCode.THRESHOLD_UNMET,
    terminated_at_utc: str = TS,
) -> H40TerminationReceipt:
    return H40TerminationReceipt(
        detail_message="mock termination",
        failure_evidence_hash=None,
        reason_code=reason_code,
        run_authority_id=run_id,
        source_state=source_state,
        target_state=target_state,
        terminated_at_utc=terminated_at_utc,
        upstream_receipt_hash=upstream_receipt_hash,
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


def _typed_production_authority_fixture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    cached_calendar: bool = True,
) -> tuple[
    H40SourceManifest,
    H40SplitManifest,
    H40RuntimeSourceSplitAttestation,
    dict[str, bool],
]:
    if cached_calendar:
        # The source/split algorithm still runs on every cold verification.
        # Only fixed, pure calendar and search-space inputs reuse templates.
        monkeypatch.setattr(split_manifest_module, "generate_hourly_range", _fresh_calendar_copy)
        monkeypatch.setattr(
            search_space_module, "materialize_h40_search_space_production", _fresh_ledger_copy,
        )
        monkeypatch.setattr(
            lifecycle_authority_module, "_accepted_production_roster", _immutable_roster_template,
        )
    protocol_hash = H40ProtocolIdentity.default().protocol_hash
    reference = H40SourceManifest.build_default(protocol_hash)
    timestamps = generate_hourly_range(
        "2021-01-01T00:00:00Z",
        "2026-02-01T00:00:00Z",
    )
    membership_hash = hashlib.sha256(",".join(timestamps).encode()).hexdigest()
    eth_reference = reference.get_source("ETHUSDT_USD_M_1H")
    assert eth_reference.file_sha256 is not None
    receipt = H40SourceValidationReceipt(
        source_id=eth_reference.source_id,
        locator=eth_reference.locator,
        file_sha256=eth_reference.file_sha256,
        product=eth_reference.product,
        cadence=eth_reference.cadence,
        timestamp_field="open_time",
        timestamp_count=len(timestamps),
        first_timestamp_utc=timestamps[0],
        last_timestamp_utc=timestamps[-1],
        duplicate_count=0,
        gap_count=0,
        gaps=(),
        timestamp_membership_hash=membership_hash,
        status=H40SourceStatus.VERIFIED,
        archive_set_sha256=eth_reference.archive_set_sha256,
        notes="synthetic governance timestamp evidence",
    )
    runtime_sources: list[H40SourceRecord] = []
    snapshot = current_p1_authority_snapshot()
    for record in reference.sources:
        state = snapshot.per_source_states.get(record.source_id)
        if state == "VERIFIED":
            runtime_sources.append(replace(
                record,
                status=H40SourceStatus.VERIFIED,
                row_count=receipt.timestamp_count,
                start_utc=receipt.first_timestamp_utc,
                end_utc=receipt.last_timestamp_utc,
                gap_count=0,
                gaps=(),
                reason_code=None,
                notes=receipt.notes,
                receipt=receipt,
            ))
        elif state == "NOT_TESTABLE":
            runtime_sources.append(replace(
                record,
                status=H40SourceStatus.NOT_TESTABLE,
                reason_code=H40ReasonCode.NOT_TESTABLE,
                receipt=None,
            ))
        else:
            runtime_sources.append(record)
    source_manifest = H40SourceManifest(
        protocol_identity_hash=protocol_hash,
        sources=tuple(runtime_sources),
    )
    cold_state = {"available": True}

    def cold_validate(
        repo_root: Path | str,
        record: H40SourceRecord,
        expected_product: str | None = None,
        expected_cadence: str = "1h",
    ) -> H40SourceValidationReceipt:
        del repo_root, expected_product, expected_cadence
        assert record.source_id == "ETHUSDT_USD_M_1H"
        if not cold_state["available"]:
            return replace(
                receipt,
                status=H40SourceStatus.NOT_TESTABLE,
                reason_code=H40ReasonCode.SOURCE_MISSING,
            )
        return receipt

    def cold_timestamps(
        repo_root: Path | str,
        record: H40SourceRecord,
        expected_product: str | None = None,
        expected_cadence: str = "1h",
    ) -> list[str]:
        del repo_root, expected_product, expected_cadence
        assert record.source_id == "ETHUSDT_USD_M_1H"
        if not cold_state["available"]:
            raise H40GuardError(H40ReasonCode.SOURCE_MISSING, "synthetic source disappeared")
        return list(timestamps)

    monkeypatch.setattr(lifecycle_authority_module, "validate_source_artifact", cold_validate)
    monkeypatch.setattr(
        lifecycle_authority_module,
        "extract_verified_source_timestamps",
        cold_timestamps,
    )
    split_manifest, runtime_attestation = materialize_runtime_source_split_authority(
        source_manifest=source_manifest,
        repo_root=Path("synthetic-repository"),
    )
    return source_manifest, split_manifest, runtime_attestation, cold_state


_ORIGINAL_GENERATE_HOURLY_RANGE = generate_hourly_range
_ORIGINAL_MATERIALIZE_SEARCH_SPACE = search_space_module.materialize_h40_search_space_production
_ORIGINAL_ACCEPTED_ROSTER = lifecycle_authority_module._accepted_production_roster


@lru_cache(maxsize=None)
def _immutable_calendar_template(
    start_utc: str, end_utc: str, inclusive_end: bool,
) -> tuple[str, ...]:
    return tuple(_ORIGINAL_GENERATE_HOURLY_RANGE(start_utc, end_utc, inclusive_end))


def _fresh_calendar_copy(
    start_utc: str, end_utc: str, inclusive_end: bool = False,
) -> list[str]:
    return list(_immutable_calendar_template(start_utc, end_utc, inclusive_end))


@lru_cache(maxsize=1)
def _immutable_ledger_template() -> str:
    return canonical_json(_ORIGINAL_MATERIALIZE_SEARCH_SPACE().to_dict())


def _fresh_ledger_copy() -> H40ConfigurationLedger:
    return H40ConfigurationLedger.from_dict(json.loads(_immutable_ledger_template()))


@lru_cache(maxsize=1)
def _immutable_roster_template() -> tuple[tuple[H40RuntimeRosterEntry, ...], int, int, str]:
    return _ORIGINAL_ACCEPTED_ROSTER()


def test_cached_calendar_preserves_full_cold_authority_and_state_isolation(
    tmp_path: Path,
) -> None:
    def build(*, cached_calendar: bool) -> tuple[
        H40SourceManifest, H40SplitManifest, H40RuntimeSourceSplitAttestation,
        H40RuntimeSnapshotSeal, dict[str, bool], str,
    ]:
        with pytest.MonkeyPatch.context() as patch:
            source, split, attestation, cold_state = _typed_production_authority_fixture(
                patch, cached_calendar=cached_calendar,
            )
            seal = H40RuntimeSnapshotSeal.from_verified_authority(
                source_manifest=source,
                split_manifest=split,
                runtime_attestation=attestation,
                repo_root=tmp_path,
            )
            seal.verify_against_accepted_ledger()
            if cached_calendar:
                cold_state["available"] = False
                with pytest.raises(H40GuardError, match="failed cold validation"):
                    seal.verify_against_accepted_ledger()
                cold_state["available"] = True
                seal.verify_against_accepted_ledger()
            discovery_hash = _build_discovery_chain(seal=seal).discovery.receipt_hash
            return source, split, attestation, seal, cold_state, discovery_hash

    full_source, full_split, full_attestation, full_seal, full_state, full_discovery_hash = build(
        cached_calendar=False,
    )
    cached_source, cached_split, cached_attestation, cached_seal, cached_state, cached_discovery_hash = build(
        cached_calendar=True,
    )
    assert full_source is not cached_source
    assert full_split is not cached_split
    assert full_attestation is not cached_attestation
    assert full_seal is not cached_seal
    assert full_state is not cached_state
    assert full_source.manifest_hash == cached_source.manifest_hash
    assert full_split.split_hash == cached_split.split_hash
    assert full_attestation.attestation_hash == cached_attestation.attestation_hash
    assert full_seal.runtime_authority_snapshot_hash == cached_seal.runtime_authority_snapshot_hash
    assert full_seal.roster == cached_seal.roster
    assert full_seal.sealed_registered_roster_hash == cached_seal.sealed_registered_roster_hash
    assert full_seal.registered_slot_count == cached_seal.registered_slot_count
    assert full_seal.not_testable_slot_count == cached_seal.not_testable_slot_count
    authority_hash = _implementation_authority().lifecycle_implementation_authority_hash
    assert H40RunAuthority.from_seal(full_seal, authority_hash).run_authority_id == (
        H40RunAuthority.from_seal(cached_seal, authority_hash).run_authority_id
    )
    assert full_discovery_hash == cached_discovery_hash
    first = _fresh_calendar_copy("2021-01-01T00:00:00Z", "2021-01-01T02:00:00Z")
    second = _fresh_calendar_copy("2021-01-01T00:00:00Z", "2021-01-01T02:00:00Z")
    assert first == second
    assert first is not second
    first.clear()
    assert len(second) == 2
    first_ledger = _fresh_ledger_copy()
    second_ledger = _fresh_ledger_copy()
    assert first_ledger is not second_ledger
    assert first_ledger.structural_ledger_hash == second_ledger.structural_ledger_hash
    assert first_ledger.slots[0] is not second_ledger.slots[0]
    original_slot_status = second_ledger.slots[0].status
    first_ledger.drop_slot(0, H40ReasonCode.CONFIG_IDENTITY_CONFLICT)
    assert second_ledger.slots[0].status == original_slot_status
    assert _immutable_roster_template() == _ORIGINAL_ACCEPTED_ROSTER()


def _persist_candidate_chain(
    tmp_path: Path,
    chain: _DiscoveryChain,
) -> H40LifecycleArtifactStore:
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    store.persist_authorization(
        "02_candidate_lock",
        chain.candidate,
        service=chain.service,
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
    assert lifecycle_governance_authority_object()["schema_id"] == "H40_LIFECYCLE_GOVERNANCE_AUTHORITY_V4"
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
    assert (
        ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH
        == "d3a304ddc6bcb7b7fc398ccf45a751a0afa3f91634a09ddff8e199af1970e440"
    )
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
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    path = store.persist_authorization(
        "02_candidate_lock",
        chain.candidate,
        service=chain.service,
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

    orig_revalidate = chain.service.revalidate_authorization

    def spy_revalidate(authority: VerifiedLifecycleAuthorization) -> None:
        nonlocal calls
        calls += 1
        orig_revalidate(authority)

    chain.service.revalidate_authorization = spy_revalidate

    first = store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    second = store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    assert first == second
    assert calls == 2
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
    source_manifest, split_manifest, runtime_attestation, _ = (
        _typed_production_authority_fixture(monkeypatch, cached_calendar=False)
    )
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source_manifest,
        split_manifest=split_manifest,
        runtime_attestation=runtime_attestation,
        repo_root=tmp_path,
    )
    assert not seal.synthetic_only
    assert seal.source_manifest_hash == source_manifest.manifest_hash
    assert seal.split_manifest_hash == split_manifest.split_hash
    assert split_manifest.attestation is None
    assert seal.split_attestation_hash == runtime_attestation.attestation_hash
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
    with pytest.raises(TypeError, match="RuntimeSourceSplitAttestation"):
        H40RuntimeSnapshotSeal.from_verified_authority(
            source_manifest=source_manifest,
            split_manifest=split_manifest,
            runtime_attestation=None,  # type: ignore[arg-type]
            repo_root=tmp_path,
        )


def test_a05_split_assert_authoritative_failure_propagates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_manifest, split_manifest, runtime_attestation, cold_state = (
        _typed_production_authority_fixture(monkeypatch, cached_calendar=False)
    )
    cold_state["available"] = False
    with pytest.raises(H40GuardError, match="failed cold validation") as exc_info:
        H40RuntimeSnapshotSeal.from_verified_authority(
            source_manifest=source_manifest,
            split_manifest=split_manifest,
            runtime_attestation=runtime_attestation,
            repo_root=tmp_path,
        )
    assert exc_info.value.reason_code == H40ReasonCode.SOURCE_MISSING


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
        service=wf.discovery_chain.service,
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


# F01R2 acceptance matrix.  The R labels correspond one-for-one to the task's
# mandatory adversarial list; closely related mutations share a parametrized test.


def test_r01_r04_amended_authority_hashes_and_science_are_exact() -> None:
    assert (
        compute_lifecycle_child_hashes()["runtime_snapshot_seal_contract"]
        == "76a0732742707c78f65da26263076bed7b586ea67d4f5ddd2dac33761e37e612"
    )
    assert compute_lifecycle_semantic_root_hash() == (
        "846591f8eac0e1abbedaeeff4c2b0bb7648fe51bdaf981e3309c6f6c440aba8e"
    )
    assert compute_lifecycle_governance_authority_hash() == (
        "7e9433aa2ee706dda61871c6ad2b1a1aee4cf7a8f9b6365351942096b5347c84"
    )
    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH
    assert compute_semantic_root_hash() == EXPECTED_SEMANTIC_ROOT_HASH
    assert materialize_h40_search_space_production().structural_ledger_hash == (
        EXPECTED_STRUCTURAL_LEDGER_HASH
    )


def test_r05_r07_runtime_projection_and_active_union_are_derived() -> None:
    ledger = materialize_h40_search_space_production()
    registered = tuple(slot for slot in ledger.slots if slot.status == "REGISTERED")
    assert len(registered) == 18
    assert len(ledger.slots) - len(registered) == 150
    active = sorted({
        source_id
        for slot in registered
        for source_id in derive_required_sources_for_slot(slot)
    })
    assert active == ["ETHUSDT_USD_M_1H"]
    source = inspect.getsource(materialize_runtime_source_split_authority)
    assert "ETHUSDT_USD_M_1H" not in source


def test_r08_r10_btc_identity_does_not_grant_runtime_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_manifest, _, _, _ = _typed_production_authority_fixture(monkeypatch)
    btc = source_manifest.get_source("BTCUSDT_USD_M_1H")
    assert_canonical_source_identity(btc, source_manifest.protocol_identity_hash)
    assert btc.status == H40SourceStatus.NOT_TESTABLE
    assert current_p1_authority_snapshot().per_source_states[btc.source_id] == "NOT_TESTABLE"
    eth_receipt = source_manifest.get_source("ETHUSDT_USD_M_1H").receipt
    assert eth_receipt is not None
    promoted = replace(btc, status=H40SourceStatus.VERIFIED, receipt=eth_receipt)
    forged_manifest = replace(
        source_manifest,
        sources=tuple(promoted if item.source_id == btc.source_id else item for item in source_manifest.sources),
    )
    with pytest.raises(H40GuardError, match="accepted snapshot state"):
        materialize_runtime_source_split_authority(
            source_manifest=forged_manifest,
            repo_root=Path("synthetic-repository"),
        )


def test_r11_r16_runtime_snapshot_and_state_schema_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, attestation, _ = _typed_production_authority_fixture(monkeypatch)
    raw = attestation.to_dict()
    mutations: list[dict[str, object]] = []
    missing = json.loads(json.dumps(raw))
    missing["source_authority_state_entries"] = missing["source_authority_state_entries"][1:]
    mutations.append(missing)
    extra = json.loads(json.dumps(raw))
    extra["source_authority_state_entries"].append({
        "source_id": "EXTRA",
        "production_authority_state": "NOT_TESTABLE",
    })
    mutations.append(extra)
    duplicate = json.loads(json.dumps(raw))
    duplicate["source_authority_state_entries"].append(
        duplicate["source_authority_state_entries"][0]
    )
    mutations.append(duplicate)
    reordered = json.loads(json.dumps(raw))
    reordered["source_authority_state_entries"] = list(
        reversed(reordered["source_authority_state_entries"])
    )
    mutations.append(reordered)
    wrong_not_testable = json.loads(json.dumps(raw))
    wrong_not_testable["not_testable_source_ids"] = []
    mutations.append(wrong_not_testable)
    foreign_snapshot = json.loads(json.dumps(raw))
    foreign_snapshot["runtime_authority_snapshot_hash"] = _hash("foreign snapshot")
    parsed_foreign = H40RuntimeSourceSplitAttestation.from_dict(foreign_snapshot)
    assert parsed_foreign != attestation
    for mutation in mutations:
        with pytest.raises((TypeError, ValueError)):
            H40RuntimeSourceSplitAttestation.from_dict(mutation)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("source_record_hash", "0" * 64, id="R19-record-hash"),
        pytest.param("source_validation_receipt_hash", "1" * 64, id="R20-receipt-hash"),
        pytest.param("file_sha256", "2" * 64, id="R21-file-hash"),
        pytest.param("timestamp_membership_hash", "3" * 64, id="R22-membership-hash"),
        pytest.param("timestamp_count", 1, id="R23-timestamp-count"),
    ],
)
def test_r17_r23_active_evidence_exactness_and_tamper_rejection(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    source_manifest, split_manifest, attestation, _ = (
        _typed_production_authority_fixture(monkeypatch)
    )
    raw = attestation.to_dict()
    missing = json.loads(json.dumps(raw))
    missing["active_source_evidence"] = []
    with pytest.raises(ValueError):
        H40RuntimeSourceSplitAttestation.from_dict(missing)
    extra = json.loads(json.dumps(raw))
    extra["active_source_evidence"].append({
        **extra["active_source_evidence"][0],
        "source_id": "BTCUSDT_USD_M_1H",
    })
    with pytest.raises(ValueError):
        H40RuntimeSourceSplitAttestation.from_dict(extra)
    tampered = json.loads(json.dumps(raw))
    tampered["active_source_evidence"][0][field] = value
    typed = H40RuntimeSourceSplitAttestation.from_dict(tampered)
    with pytest.raises(H40GuardError, match="attestation"):
        lifecycle_authority_module.verify_runtime_source_split_authority(
            source_manifest=source_manifest,
            split_manifest=split_manifest,
            runtime_attestation=typed,
            repo_root=Path("synthetic-repository"),
        )


def test_r24_r26_legacy_synthetic_and_schedule_only_authority_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_manifest, split_manifest, attestation, _ = (
        _typed_production_authority_fixture(monkeypatch)
    )
    legacy = H40SplitAttestation.create(
        protocol_identity_hash=source_manifest.protocol_identity_hash,
        source_manifest_hash=source_manifest.manifest_hash,
        split_hash=split_manifest.split_hash,
        btc_source_id="BTCUSDT_USD_M_1H",
        btc_locator="synthetic/btc",
        btc_file_sha256=_hash("btc"),
        btc_membership_sha256=_hash("btc membership"),
        btc_timestamp_count=1,
        eth_source_id="ETHUSDT_USD_M_1H",
        eth_locator="synthetic/eth",
        eth_file_sha256=_hash("eth"),
        eth_membership_sha256=_hash("eth membership"),
        eth_timestamp_count=1,
    )
    with pytest.raises(TypeError):
        H40RuntimeSnapshotSeal.from_verified_authority(
            source_manifest=source_manifest,
            split_manifest=split_manifest,
            runtime_attestation=legacy,  # type: ignore[arg-type]
            repo_root=tmp_path,
        )
    synthetic = replace(attestation, source_manifest_hash=_hash("synthetic"))
    with pytest.raises(H40GuardError):
        lifecycle_authority_module.verify_runtime_source_split_authority(
            source_manifest=source_manifest,
            split_manifest=split_manifest,
            runtime_attestation=synthetic,
            repo_root=tmp_path,
        )
    schedule = H40SplitManifest.build_preregistered_schedule(
        source_manifest.protocol_identity_hash,
        source_manifest.manifest_hash,
    )
    with pytest.raises(H40GuardError):
        lifecycle_authority_module.verify_runtime_source_split_authority(
            source_manifest=source_manifest,
            split_manifest=schedule,
            runtime_attestation=attestation,
            repo_root=tmp_path,
        )


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param("boundary", id="R27-boundary"),
        pytest.param("fold", id="R28-fold"),
        pytest.param("count", id="R29-count"),
        pytest.param("membership", id="R30-membership"),
    ],
)
def test_r27_r30_runtime_split_mutations_rejected(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    source_manifest, split_manifest, attestation, _ = (
        _typed_production_authority_fixture(monkeypatch)
    )
    part = split_manifest.partitions[0]
    if mutation == "boundary":
        changed = replace(part, start_utc="2021-02-01T00:00:00Z")
    elif mutation == "fold":
        changed = replace(part, fold="FOREIGN")
    elif mutation == "count":
        changed = replace(part, count=part.count + 1)
    else:
        changed = replace(part, timestamps_sha256=_hash("foreign membership"))
    tampered = replace(split_manifest, partitions=(changed, *split_manifest.partitions[1:]))
    with pytest.raises(H40GuardError, match="runtime split"):
        lifecycle_authority_module.verify_runtime_source_split_authority(
            source_manifest=source_manifest,
            split_manifest=tampered,
            runtime_attestation=attestation,
            repo_root=Path("synthetic-repository"),
        )


def test_r31_r33_cross_source_split_attestation_and_roster_pairs_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_manifest, split_manifest, attestation, _ = (
        _typed_production_authority_fixture(monkeypatch)
    )
    mutations = (
        replace(attestation, source_manifest_hash=_hash("foreign source manifest")),
        replace(attestation, split_manifest_hash=_hash("foreign split manifest")),
        replace(attestation, sealed_registered_roster_hash=_hash("foreign roster")),
    )
    for mutation in mutations:
        with pytest.raises(H40GuardError):
            lifecycle_authority_module.verify_runtime_source_split_authority(
                source_manifest=source_manifest,
                split_manifest=split_manifest,
                runtime_attestation=mutation,
                repo_root=Path("synthetic-repository"),
            )


def test_r34_r36_seal_is_fixed_and_new_snapshot_changes_run_not_science() -> None:
    first = _complete_synthetic_seal()
    later = _complete_synthetic_seal("later-accepted-snapshot")
    authority_hash = _implementation_authority().lifecycle_implementation_authority_hash
    assert H40RunAuthority.from_seal(first, authority_hash).run_authority_id != (
        H40RunAuthority.from_seal(later, authority_hash).run_authority_id
    )
    assert first.roster == tuple(first.roster)
    assert first.registered_slot_count == 18
    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH
    assert compute_semantic_root_hash() == EXPECTED_SEMANTIC_ROOT_HASH


def test_r35_r37_r38_production_cold_restore_and_active_source_change_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_manifest, split_manifest, attestation, cold_state = (
        _typed_production_authority_fixture(monkeypatch)
    )
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source_manifest,
        split_manifest=split_manifest,
        runtime_attestation=attestation,
        repo_root=tmp_path,
    )
    authority = _implementation_authority()
    verifier = H40SyntheticEvidenceVerifier({})
    service = H40LifecycleAuthorityService.synthetic_for_tests(authority, verifier)
    run = H40RunAuthority.from_seal(seal, authority.lifecycle_implementation_authority_hash)
    discovery = service.authorize_discovery(
        implementation_authority=authority,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
    )
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization(
        "01_discovery_authorization",
        discovery,
        service=service,
    )
    fresh_service = H40LifecycleAuthorityService.synthetic_for_tests(
        authority,
        H40SyntheticEvidenceVerifier({}),
    )
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(authority,),
        run_authorities=(run,),
        runtime_seals=(seal,),
    )
    restored = store.restore_authorization(
        run.run_authority_id,
        "01_discovery_authorization",
        service=fresh_service,
        resolver=resolver,
    )
    assert restored.receipt_hash == discovery.receipt_hash
    cold_state["available"] = False
    with pytest.raises(H40GuardError, match="failed cold validation"):
        store.restore_authorization(
            run.run_authority_id,
            "01_discovery_authorization",
            service=fresh_service,
            resolver=resolver,
        )


def test_r39_r43_substitution_replay_and_constructor_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_manifest, split_manifest, attestation, _ = (
        _typed_production_authority_fixture(monkeypatch)
    )
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source_manifest,
        split_manifest=split_manifest,
        runtime_attestation=attestation,
        repo_root=tmp_path,
    )
    assert not seal.synthetic_only
    assert inspect.signature(H40RuntimeSnapshotSeal.from_verified_authority).parameters[
        "runtime_attestation"
    ]
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
    assert _complete_synthetic_seal().synthetic_only


def test_r44_r46_f02_h39_and_final_holdout_remain_sealed() -> None:
    assert H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE not in (
        H40LifecycleStateMachine.VALID_TRANSITIONS[
            H40LifecycleState.H40_CONFIRMATION_READY
        ]
    )
    with pytest.raises(H40GuardError):
        H40ConfirmationGuard().assert_outcomes_accessible()
    for path in ("artifacts/h39_protected/result", "artifacts/final_holdout/result"):
        with pytest.raises(H40GuardError):
            H40ProtectedSurfaceGuard.assert_surface_allowed(path)


# =============================================================================
# F01R3 Mandatory Adversarial Tests (A01 - A45)
# =============================================================================


def _ProductionEvidenceVerifier(root: Path) -> H40ProductionDiscoveryEvidenceVerifier:
    """Real constructor fixture for governance tests that stop before P3B science."""
    from test_v051_h40_p3b_production_discovery_verifier import _invalid_fixture

    return _invalid_fixture(root).verifier


def test_production_verifier_fixture_keeps_evidence_and_resolver_per_test(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = _ProductionEvidenceVerifier(first_root)
    second = _ProductionEvidenceVerifier(second_root)
    assert first is not second
    assert first._resolver is not second._resolver
    assert first._resolver._root == first_root.resolve()
    assert second._resolver._root == second_root.resolve()
    first.assert_runtime_integrity()
    second.assert_runtime_integrity()
    first_file = next(first_root.rglob("*.json"))
    second_file = second_root / first_file.relative_to(first_root)
    original_bytes = second_file.read_bytes()
    assert first_file.read_bytes() == original_bytes
    first_file.write_bytes(b"per-test mutation")
    assert second_file.read_bytes() == original_bytes


def test_a01_through_a07_derived_wf_authority(tmp_path: Path) -> None:
    # A04: exact derived WF universe == WF1..WF4 validation only
    chain = _build_discovery_chain()
    derived = derive_expected_wf_authority(seal=chain.seal)
    assert derived.fold_names == ("WF1", "WF2", "WF3", "WF4")
    assert derived.validation_partition_names == (
        "WF1_VALIDATION",
        "WF2_VALIDATION",
        "WF3_VALIDATION",
        "WF4_VALIDATION",
    )
    assert derived.split_manifest_hash == chain.seal.split_manifest_hash
    assert derived.split_attestation_hash == chain.seal.split_attestation_hash

    # A01: paired fold shrink + evidence shrink rejected
    folds_3 = tuple(
        H40ExpectedWFFold(
            fold_id=f"WF{i}",
            partition_id=f"WF{i}_VALIDATION",
            split_definition_hash=_hash(f"fold-{i}"),
        )
        for i in range(1, 4)
    )
    with pytest.raises(ValueError, match="must contain exactly 4 WF validation folds"):
        H40ExpectedSplitAuthority(
            split_manifest_hash=chain.seal.split_manifest_hash,
            split_attestation_hash=chain.seal.split_attestation_hash,
            folds=folds_3,
            accepted_validation_contract_hashes={"WF_GATE_SET_V1": _hash("wf-gate-set")},
        )

    # A02: paired validation-contract shrink + evidence shrink rejected
    folds_4 = tuple(
        H40ExpectedWFFold(
            fold_id=f"WF{i}",
            partition_id=f"WF{i}_VALIDATION",
            split_definition_hash=_hash(f"fold-{i}"),
        )
        for i in range(1, 5)
    )
    with pytest.raises(ValueError, match="accepted_validation_contract_hashes"):
        H40ExpectedSplitAuthority(
            split_manifest_hash=chain.seal.split_manifest_hash,
            split_attestation_hash=chain.seal.split_attestation_hash,
            folds=folds_4,
            accepted_validation_contract_hashes={},
        )

    # A03: extra fabricated fold + matching evidence rejected
    folds_5 = tuple(
        H40ExpectedWFFold(
            fold_id=f"WF{i}",
            partition_id=f"WF{i}_VALIDATION",
            split_definition_hash=_hash(f"fold-{i}"),
        )
        for i in range(1, 6)
    )
    with pytest.raises(ValueError, match="must contain exactly 4 WF validation folds"):
        H40ExpectedSplitAuthority(
            split_manifest_hash=chain.seal.split_manifest_hash,
            split_attestation_hash=chain.seal.split_attestation_hash,
            folds=folds_5,
            accepted_validation_contract_hashes={"WF_GATE_SET_V1": _hash("wf-gate-set")},
        )

    # A05: Confirmation partition cannot enter WF universe
    assert "CONFIRMATION" not in " ".join(derived.validation_partition_names)
    with pytest.raises(ValueError, match="fold_id"):
        H40ExpectedWFFold(
            fold_id="CONFIRMATION",
            partition_id="CONFIRMATION_EVALUATION",
            split_definition_hash=_hash("conf"),
        )

    # A06: missing WF2 or reordered WF3/WF4 rejected
    reordered_folds = (
        folds_4[0],
        folds_4[1],
        folds_4[3],
        folds_4[2],
    )
    with pytest.raises(ValueError, match="must be strictly sorted"):
        H40ExpectedSplitAuthority(
            split_manifest_hash=chain.seal.split_manifest_hash,
            split_attestation_hash=chain.seal.split_attestation_hash,
            folds=reordered_folds,
            accepted_validation_contract_hashes={"WF_GATE_SET_V1": _hash("wf-gate-set")},
        )

    # A07: caller-supplied expected authority cannot replace production derivation
    prod_service = H40LifecycleAuthorityService(
        implementation_authority=chain.authority,
        accepted_implementation_authority_hash=chain.authority.lifecycle_implementation_authority_hash,
        evidence_verifier=_ProductionEvidenceVerifier(tmp_path / "verifier"),
        synthetic_test_mode=False,
        _construction_token=lifecycle_authority_module._VERIFIED_AUTHORITY_TOKEN,
    )
    with pytest.raises(H40GuardError, match="caller-supplied split authority cannot override"):
        prod_service.authorize_wf_validation(
            candidate_authority=chain.candidate,
            evidence=None,  # type: ignore[arg-type]
            split_authority=derived,
            validated_at_utc=TS,
            verified_at_utc=TS,
        )


def test_a08_through_a14_durable_single_run_head(tmp_path: Path) -> None:
    store = H40LifecycleArtifactStore(tmp_path)
    chain = _build_discovery_chain()
    run_id = chain.run.run_authority_id

    # Sequence 0 commit via persist_authorization with exact issuing service
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    head0 = store.get_committed_run_head(run_id)
    assert isinstance(head0, H40DurableRunHead)
    assert head0.transition_sequence == 0
    assert head0.head_receipt_hash == chain.discovery.receipt_hash
    assert not head0.terminal

    # A08: two candidate-lock writers from same Discovery -> exactly one committed successor
    # Sibling 1: candidate lock
    # Sibling 2: sibling termination from discovery
    cand_term = chain.service.authorize_termination(
        prior_authority=chain.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="sibling termination",
        terminated_at_utc=TS,
    )
    store.persist_authorization(
        "02_candidate_lock",
        chain.candidate,
        service=chain.service,
    )
    head1 = store.get_committed_run_head(run_id)
    assert head1 is not None
    assert head1.transition_sequence == 1
    assert head1.head_receipt_hash == chain.candidate.receipt_hash

    # Writer B attempts to advance from stale discovery receipt
    with pytest.raises(H40GuardError, match="predecessor receipt hash mismatch"):
        store.persist_authorization(
            "02_termination",
            cand_term,
            service=chain.service,
        )
    assert store.get_committed_run_head(run_id).head_receipt_hash == chain.candidate.receipt_hash

    # A09: WF success vs NO_GO from same candidate -> exactly one committed successor
    chain_wf = _build_wf_chain()
    store_wf = H40LifecycleArtifactStore(tmp_path / "wf_run")
    store_wf.persist_authorization(
        "01_discovery_authorization",
        chain_wf.discovery_chain.discovery,
        service=chain_wf.discovery_chain.service,
    )
    store_wf.persist_authorization(
        "02_candidate_lock",
        chain_wf.discovery_chain.candidate,
        service=chain_wf.discovery_chain.service,
    )
    wf_term = chain_wf.discovery_chain.service.authorize_termination(
        prior_authority=chain_wf.discovery_chain.candidate,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="wf rejected termination",
        terminated_at_utc=TS,
    )
    store_wf.persist_authorization(
        "03_wf_validation",
        chain_wf.wf,
        service=chain_wf.discovery_chain.service,
    )
    head2 = store_wf.get_committed_run_head(chain_wf.discovery_chain.run.run_authority_id)
    assert head2 is not None
    assert head2.head_receipt_hash == chain_wf.wf.receipt_hash
    with pytest.raises(H40GuardError, match="predecessor receipt hash mismatch"):
        store_wf.persist_authorization(
            "03_termination",
            wf_term,
            service=chain_wf.discovery_chain.service,
        )

    # A10: terminal then stale success rejected
    chain_term = _build_discovery_chain()
    term_run_id = chain_term.run.run_authority_id
    store_term = H40LifecycleArtifactStore(tmp_path / "term_run")
    store_term.persist_authorization(
        "01_discovery_authorization",
        chain_term.discovery,
        service=chain_term.service,
    )
    t0_auth = chain_term.service.authorize_termination(
        prior_authority=chain_term.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="terminal run termination",
        terminated_at_utc=TS,
    )
    store_term.persist_authorization(
        "02_termination",
        t0_auth,
        service=chain_term.service,
    )
    assert store_term.get_committed_run_head(term_run_id).terminal
    with pytest.raises(H40GuardError, match="terminal state .* no forward commits allowed"):
        store_term.persist_authorization(
            "02_candidate_lock",
            chain_term.candidate,
            service=chain_term.service,
        )

    # A11: success then stale terminal sibling rejected
    # In store_wf: candidate -> WF already succeeded; attempting to persist candidate terminal sibling failed in A09.

    # A12: two concurrent processes/transactions -> one winner
    import concurrent.futures

    concurrent_chain = _build_discovery_chain()
    concurrent_run_id = concurrent_chain.run.run_authority_id
    store_conc = H40LifecycleArtifactStore(tmp_path / "conc_run")
    store_conc.persist_authorization(
        "01_discovery_authorization",
        concurrent_chain.discovery,
        service=concurrent_chain.service,
    )
    c_cand = concurrent_chain.candidate
    c_term = concurrent_chain.service.authorize_termination(
        prior_authority=concurrent_chain.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="concurrent sibling termination",
        terminated_at_utc=TS,
    )

    def try_persist(auth: VerifiedLifecycleAuthorization, key: str) -> tuple[str, bool, str]:
        s = H40LifecycleArtifactStore(tmp_path / "conc_run")
        try:
            s.persist_authorization(key, auth, service=concurrent_chain.service)
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
    committed = store_conc.get_committed_run_head(concurrent_run_id)
    assert committed is not None
    assert committed.head_receipt_hash == successes[0][0]

    # A13 & A14: restore non-head sibling rejected, arbitrary filename/key confers no authority
    chain_a13 = _build_discovery_chain()
    store_a13 = H40LifecycleArtifactStore(tmp_path / "a13_run")
    store_a13.persist_authorization(
        "01_discovery_authorization",
        chain_a13.discovery,
        service=chain_a13.service,
    )
    store_a13.persist_authorization(
        "02_candidate_lock",
        chain_a13.candidate,
        service=chain_a13.service,
    )
    orphan_envelope = {
        "authority_context": {
            "implementation_authority_hash": chain_a13.authority.lifecycle_implementation_authority_hash,
            "predecessor_receipt_hash": chain_a13.discovery.receipt_hash,
            "run_authority_id": chain_a13.run.run_authority_id,
            "runtime_seal_hash": chain_a13.seal.authority_context_hash,
            "split_authority_hash": None,
        },
        "bound_evidence": None,
        "bound_evidence_sha256": None,
        "receipt": {
            "authorized_at_utc": TS,
            "discovery_result_evidence_hash": _hash("other-ev"),
            "locked_at_utc": TS,
            "receipt_schema_id": "H40_CANDIDATE_LOCK_RECEIPT_V1",
            "run_authority_id": chain_a13.run.run_authority_id,
            "selected_slot_hash": _hash("other-slot"),
            "selected_slot_index": 2,
            "selected_structural_configuration_hash": _hash("other-cfg"),
            "target_state": "H40_CANDIDATE_LOCKED",
            "upstream_receipt_hash": chain_a13.discovery.receipt_hash,
            "verified_at_utc": TS,
        },
    }
    orphan_envelope["receipt_sha256"] = canonical_sha256(orphan_envelope["receipt"])
    orphan_path = store_a13._receipts_dir(chain_a13.run.run_authority_id) / f"{orphan_envelope['receipt_sha256']}.json"
    orphan_path.write_text(canonical_json(orphan_envelope) + "\n", encoding="utf-8")

    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(chain_a13.authority,),
        run_authorities=(chain_a13.run,),
        runtime_seals=(chain_a13.seal,),
    )
    # A13: restore non-head sibling rejected
    with pytest.raises(H40GuardError, match="not in committed run head lineage"):
        store_a13.restore_authorization(
            chain_a13.run.run_authority_id,
            str(orphan_envelope["receipt_sha256"]),
            service=chain_a13.service,
            resolver=resolver,
        )

    # A14: arbitrary filename/key confers no authority
    fake_legacy_path = store_a13._run_dir(chain_a13.run.run_authority_id) / "99_fabricated.json"
    fake_legacy_path.write_text(canonical_json(orphan_envelope) + "\n", encoding="utf-8")
    with pytest.raises(H40GuardError, match="not in committed run head lineage"):
        store_a13.restore_authorization(
            chain_a13.run.run_authority_id,
            "99_fabricated",
            service=chain_a13.service,
            resolver=resolver,
        )


def test_a15_through_a20_receipt_publication_and_crash_protocol(tmp_path: Path) -> None:
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(chain.authority,),
        run_authorities=(chain.run,),
        runtime_seals=(chain.seal,),
    )

    # A15: partial temp receipt confers no authority
    receipts_dir = store._receipts_dir(chain.run.run_authority_id)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    temp_receipt = receipts_dir / "receipt.12345.tmp"
    temp_receipt.write_text("partial content", encoding="utf-8")
    with pytest.raises(H40GuardError):
        store.restore_authorization(
            chain.run.run_authority_id,
            "receipt.12345.tmp",
            service=chain.service,
            resolver=resolver,
        )

    # Persist discovery
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    head_after_disc = store.get_committed_run_head(chain.run.run_authority_id)
    assert head_after_disc is not None
    assert head_after_disc.transition_sequence == 0

    # A16: complete orphan receipt with old head confers no authority (crash C3: receipt published, head not advanced)
    orphan_envelope = store._envelope(chain.candidate)
    orphan_path = receipts_dir / f"{chain.candidate.receipt_hash}.json"
    orphan_path.write_text(canonical_json(orphan_envelope) + "\n", encoding="utf-8")
    current_head = store.get_committed_run_head(chain.run.run_authority_id)
    assert current_head is not None
    assert current_head.head_receipt_hash == chain.discovery.receipt_hash
    with pytest.raises(H40GuardError, match="not in committed run head lineage"):
        store.restore_authorization(
            chain.run.run_authority_id,
            chain.candidate.receipt_hash,
            service=chain.service,
            resolver=resolver,
        )

    # A17: head transaction abort keeps old head
    forged_auth = object.__new__(VerifiedLifecycleAuthorization)
    object.__setattr__(forged_auth, "_receipt_hash", _hash("failing-receipt"))
    object.__setattr__(forged_auth, "_run_authority_id", chain.run.run_authority_id)
    object.__setattr__(forged_auth, "_issuer_id", object())
    with pytest.raises(H40GuardError):
        store.persist_authorization("02_invalid", forged_auth, service=chain.service)
    after_abort_head = store.get_committed_run_head(chain.run.run_authority_id)
    assert after_abort_head is not None
    assert after_abort_head.head_receipt_hash == chain.discovery.receipt_hash

    # A18: exact retry idempotent after full reverification
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
    head_after_retry = store.get_committed_run_head(chain.run.run_authority_id)
    assert head_after_retry is not None
    assert head_after_retry.transition_sequence == 0

    # A19: conflicting retry rejected
    chain_wf = _build_wf_chain()
    with pytest.raises(H40GuardError, match="predecessor receipt hash mismatch"):
        store.persist_authorization(
            "03_wf_validation",
            chain_wf.wf,
            service=chain_wf.discovery_chain.service,
        )

    # A20: immutable receipt different-byte overwrite rejected
    tampered_bytes = b'{"receipt": "tampered"}\n'
    orphan_path.write_bytes(tampered_bytes)
    with pytest.raises(H40GuardError, match="write-once immutable lifecycle receipt already exists with different bytes"):
        store.persist_authorization(
            "02_candidate_lock",
            chain.candidate,
            service=chain.service,
        )




def test_a21_through_a29_model_a_capability_lifetime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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
    store = H40LifecycleArtifactStore(tmp_path)
    verifier = _ProductionEvidenceVerifier(tmp_path / "verifier")
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
    assert discovery.receipt_hash

    # A28: root seal reverified on production transition consumption
    machine = H40LifecycleStateMachine.synthetic_for_tests()
    machine.transition_with_verified_authority(discovery)
    assert machine.current_state == H40LifecycleState.H40_DISCOVERY

    # A21: source disappears after Discovery; cached Candidate transition rejected
    cold_state["available"] = False
    with pytest.raises(H40GuardError, match="failed cold validation"):
        prod_service.authorize_candidate_lock(
            discovery_authority=discovery,
            evidence=None,  # type: ignore[arg-type]
            locked_at_utc=TS,
            verified_at_utc=TS,
        )

    # Restore cold_state
    cold_state["available"] = True
    candidate_chain = _build_discovery_chain(seal=seal)
    candidate = candidate_chain.candidate
    candidate_service = candidate_chain.service

    # A22: source disappears after Candidate Lock; WF transition rejected
    cold_state["available"] = False
    with pytest.raises(H40GuardError, match="failed cold validation"):
        candidate_service.authorize_wf_validation(
            candidate_authority=candidate,
            evidence=None,  # type: ignore[arg-type]
            validated_at_utc=TS,
            verified_at_utc=TS,
        )

    # Also check A28 with candidate on machine
    with pytest.raises(H40GuardError, match="failed cold validation"):
        machine.transition_with_verified_authority(candidate)

    # A23: source mutates after Candidate Lock; WF transition rejected
    cold_state["available"] = True
    orig_validate = lifecycle_authority_module.validate_source_artifact

    def mutated_validate(repo_root: Path | str, record: H40SourceRecord, expected_product: str | None = None, expected_cadence: str = "1h") -> H40SourceValidationReceipt:
        r = orig_validate(repo_root, record, expected_product, expected_cadence)
        return replace(r, file_sha256=_hash("mutated-source-bytes"))

    monkeypatch.setattr(lifecycle_authority_module, "validate_source_artifact", mutated_validate)
    with pytest.raises(H40GuardError, match="active source 'ETHUSDT_USD_M_1H' receipt does not equal cold validation receipt"):
        candidate_service.authorize_wf_validation(
            candidate_authority=candidate,
            evidence=None,  # type: ignore[arg-type]
            validated_at_utc=TS,
            verified_at_utc=TS,
        )

    # Restore validation function
    monkeypatch.setattr(lifecycle_authority_module, "validate_source_artifact", orig_validate)

    test_disc_chain = _build_discovery_chain(seal=seal)
    test_wf_chain = _build_wf_chain(test_disc_chain)
    wf = test_wf_chain.wf
    test_service = test_disc_chain.service
    derived_split = test_wf_chain.split

    store.persist_authorization("01_discovery_authorization", test_disc_chain.discovery, service=test_service)
    store.persist_authorization("02_candidate_lock", test_disc_chain.candidate, service=test_service)
    store.persist_authorization("03_wf_validation", wf, service=test_service)

    # A25: cached WF after invalidation cannot reach Confirmation Ready
    cold_state["available"] = False
    with pytest.raises(H40GuardError, match="failed cold validation"):
        test_service.authorize_confirmation_ready(
            wf_authority=wf,
            prepared_at_utc=TS,
        )

    # A26: cold-restored WF after invalidation also rejected
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(authority,),
        run_authorities=(test_disc_chain.run,),
        runtime_seals=(seal,),
        split_authorities=(derived_split,),
    )
    with pytest.raises(H40GuardError, match="failed cold validation"):
        store.restore_authorization(
            test_disc_chain.run.run_authority_id,
            wf.receipt_hash,
            service=test_service,
            resolver=resolver,
        )

    # A27: cached/cold result equivalence
    cold_state["available"] = True
    restored = store.restore_authorization(
        test_disc_chain.run.run_authority_id,
        wf.receipt_hash,
        service=test_service,
        resolver=resolver,
    )
    assert restored.receipt_hash == wf.receipt_hash
    assert restored.receipt.to_dict() == wf.receipt.to_dict()
    assert restored.target_state == wf.target_state

    # A24: runtime source state changes after seal; cached transition rejected
    cold_state["available"] = False
    with pytest.raises(H40GuardError, match="failed cold validation"):
        test_service.revalidate_authorization(wf)

    # A29: synthetic authority remains isolated from production root verifier
    synth_chain = _build_discovery_chain()
    assert synth_chain.discovery.synthetic_only
    synth_chain.service.revalidate_authorization(synth_chain.discovery)
    with pytest.raises(H40GuardError, match="synthetic runtime seal is non-authoritative"):
        prod_service.authorize_discovery(
            implementation_authority=authority,
            run_authority=synth_chain.run,
            seal=synth_chain.seal,
            authorized_at_utc=TS,
        )


def test_a30_through_a41_frozen_identities_and_invariants() -> None:
    # A30: persistence child V2 hash exact
    child_hashes = compute_lifecycle_child_hashes()
    assert child_hashes["persistence_replay_contract"] == "5f014b867be17019c2be91ff48f8e23a43ed29678fc5589430ba174046fceaae"

    # A31: lifecycle root V3 exact
    assert compute_lifecycle_semantic_root_hash() == "846591f8eac0e1abbedaeeff4c2b0bb7648fe51bdaf981e3309c6f6c440aba8e"

    # A32: governance V4 exact
    assert compute_lifecycle_governance_authority_hash() == "7e9433aa2ee706dda61871c6ad2b1a1aee4cf7a8f9b6365351942096b5347c84"

    # A33: all other eight lifecycle child hashes unchanged
    for name, expected in EXPECTED_LIFECYCLE_CHILD_HASHES.items():
        assert child_hashes[name] == expected, f"child hash mismatch for {name}"

    # A34: three scientific hashes unchanged
    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH
    assert compute_semantic_root_hash() == EXPECTED_SEMANTIC_ROOT_HASH
    assert materialize_h40_search_space_production().structural_ledger_hash == EXPECTED_STRUCTURAL_LEDGER_HASH

    # A35: 168/18/150 unchanged
    ledger = materialize_h40_search_space_production()
    assert len(ledger.slots) == 168
    registered = [s for s in ledger.slots if s.status == "REGISTERED"]
    assert len(registered) == 18
    assert len(ledger.slots) - len(registered) == 150

    # A36: BTC remains NOT_TESTABLE
    btc_slots = [s for s in ledger.slots if any("BTC" in asset for asset in s.asset_scope)]
    assert len(btc_slots) > 0
    for s in btc_slots:
        assert s.status != "REGISTERED"

    # A37: active source union remains derived ETH-only
    active_sources = sorted({src for slot in registered for src in derive_required_sources_for_slot(slot)})
    assert active_sources == ["ETHUSDT_USD_M_1H"]

    # A38: F02 remains sealed
    assert H40LifecycleState.H40_CONFIRMATION_EVALUATED_ONCE not in H40LifecycleStateMachine.VALID_TRANSITIONS[H40LifecycleState.H40_CONFIRMATION_READY]

    # A39: H39 protected
    with pytest.raises(H40GuardError):
        H40ProtectedSurfaceGuard.assert_surface_allowed("artifacts/h39_protected/result")

    # A40: Final Holdout sealed
    with pytest.raises(H40GuardError):
        H40ProtectedSurfaceGuard.assert_surface_allowed("artifacts/final_holdout/result")

    # A41: EXECUTION_DISABLED unaffected
    with pytest.raises(H40GuardError):
        H40ExecutionGuard.assert_execution_disabled()


def test_a42_through_a45_generic_source_descriptor_equality(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_manifest, _split_manifest, attestation, _ = (
        _typed_production_authority_fixture(monkeypatch)
    )
    eth_record = source_manifest.get_source("ETHUSDT_USD_M_1H")
    assert eth_record.receipt is not None

    # A42: active row_count contradiction rejected
    tampered_row_sources = tuple(
        replace(s, row_count=s.row_count + 1) if s.source_id == "ETHUSDT_USD_M_1H" else s
        for s in source_manifest.sources
    )
    tampered_row_manifest = replace(source_manifest, sources=tampered_row_sources)
    with pytest.raises(H40GuardError, match="record row count"):
        materialize_runtime_source_split_authority(
            source_manifest=tampered_row_manifest,
            repo_root=tmp_path,
        )

    # A43: active gap_count contradiction rejected
    tampered_gap_sources = tuple(
        replace(s, gap_count=1) if s.source_id == "ETHUSDT_USD_M_1H" else s
        for s in source_manifest.sources
    )
    tampered_gap_manifest = replace(source_manifest, sources=tampered_gap_sources)
    with pytest.raises(H40GuardError, match="record gap count"):
        materialize_runtime_source_split_authority(
            source_manifest=tampered_gap_manifest,
            repo_root=tmp_path,
        )

    # A44: active start/end contradiction rejected
    tampered_start_sources = tuple(
        replace(s, start_utc="2020-01-01T00:00:00Z") if s.source_id == "ETHUSDT_USD_M_1H" else s
        for s in source_manifest.sources
    )
    tampered_start_manifest = replace(source_manifest, sources=tampered_start_sources)
    with pytest.raises(H40GuardError, match="record start timestamp"):
        materialize_runtime_source_split_authority(
            source_manifest=tampered_start_manifest,
            repo_root=tmp_path,
        )

    # A45: NOT_TESTABLE descriptive data cannot grant authority
    assert "BTCUSDT_USD_M_1H" not in attestation.active_required_source_ids
    assert "BTCUSDT_USD_M_1H" in attestation.not_testable_source_ids
    assert not any(e.source_id == "BTCUSDT_USD_M_1H" for e in attestation.active_source_evidence)
    btc_record = source_manifest.get_source("BTCUSDT_USD_M_1H")
    assert btc_record.status == H40SourceStatus.NOT_TESTABLE
    assert btc_record.receipt is None
