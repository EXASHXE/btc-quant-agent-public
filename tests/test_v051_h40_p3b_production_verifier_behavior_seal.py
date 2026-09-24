"""Adversarial checks for constructor-bound production verifier behavior."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from test_v051_h40_f01r3r1_durable_authority import (
    _make_synthetic_chain_with_production_seal,
    _ProductionAuthorityResolver,
)
from test_v051_h40_p3b_production_discovery_verifier import _invalid_fixture
from test_v051_h40_p3b_production_verifier_identity_seal import _candidate_lock_attempt

from btc_quant_agent.h40 import (
    ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH,
    H40CandidateVerification,
    H40LifecycleArtifactStore,
    H40LifecycleAuthorityService,
    H40ProductionDiscoveryEvidenceVerifier,
    compute_lifecycle_governance_authority_hash,
    compute_lifecycle_semantic_root_hash,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    materialize_h40_search_space_production,
)
from btc_quant_agent.h40.discovery_evidence import H40DiscoveryEvidenceResolver
from btc_quant_agent.h40.guards import H40GuardError


def test_b01_b10_normal_science_and_mutable_caches(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path)
    verifier = fixture.verifier
    verifier.assert_runtime_integrity()
    verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    assert verifier._manifest_hash == fixture.evidence.correction_input_evidence_manifest_hash
    assert verifier._evidence_hash == fixture.evidence.evidence_sha256
    assert verifier._verified and verifier._dependencies and verifier._entries_by_id
    verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    assert len(verifier._verified) == 18


def test_mutated_scientific_result_cache_cannot_select_candidate(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path)
    verifier = fixture.verifier
    verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    entry = fixture.entries[0]
    verifier._verified[entry.structural_configuration_hash] = H40CandidateVerification(
        True, Decimal(999), Decimal(999),
    )
    with pytest.raises(H40GuardError, match="scientific results changed"):
        verifier.verify_candidate(
            entry, run_authority_id=fixture.run_id,
            correction_manifest_hash=fixture.evidence.correction_input_evidence_manifest_hash,
        )


@pytest.mark.parametrize("method", [
    "verify_discovery_manifest", "verify_candidate", "verify_wf_fold",
])
def test_b02_instance_method_shadow_rejected(tmp_path: Path, method: str) -> None:
    verifier = _invalid_fixture(tmp_path).verifier
    with pytest.raises(AttributeError):
        setattr(verifier, method, lambda *args, **kwargs: True)
    with pytest.raises(AttributeError):
        object.__setattr__(verifier, method, lambda *args, **kwargs: True)
    verifier.assert_runtime_integrity()


def test_b03_b04_new_and_partial_init_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    real = fixture.verifier
    forged = object.__new__(H40ProductionDiscoveryEvidenceVerifier)
    with pytest.raises(H40GuardError, match="constructor integrity"):
        _candidate_lock_attempt(forged, fixture, monkeypatch)
    for name in ("_resolver", "_seal", "_receipt", "_split"):
        object.__setattr__(forged, name, getattr(real, name))
    object.__setattr__(forged, "_verified", {
        entry.structural_configuration_hash: True for entry in fixture.entries
    })
    with pytest.raises(H40GuardError, match="constructor integrity"):
        _candidate_lock_attempt(forged, fixture, monkeypatch)


@pytest.mark.parametrize("field", ["_resolver", "_seal", "_receipt", "_split"])
def test_b05_b07_b09_authority_replacement_rejected(
    tmp_path: Path, field: str,
) -> None:
    verifier = _invalid_fixture(tmp_path).verifier
    with pytest.raises(AttributeError, match="write-once"):
        setattr(verifier, field, object())
    verifier.assert_runtime_integrity()
    original = getattr(verifier, field)
    object.__setattr__(verifier, field, object())
    with pytest.raises(H40GuardError, match="runtime authority"):
        verifier.assert_runtime_integrity()
    object.__setattr__(verifier, field, original)


def test_b06_resolver_root_transitive_mutation_rejected(tmp_path: Path) -> None:
    verifier = _invalid_fixture(tmp_path).verifier
    resolver = verifier._resolver
    assert type(resolver) is H40DiscoveryEvidenceResolver
    with pytest.raises(AttributeError, match="write-once"):
        resolver._root = tmp_path / "attacker"
    object.__setattr__(resolver, "_root", tmp_path / "attacker")
    with pytest.raises(H40GuardError, match="runtime authority"):
        verifier.assert_runtime_integrity()


def test_seal_transitive_authority_context_mutation_rejected(tmp_path: Path) -> None:
    verifier = _invalid_fixture(tmp_path).verifier
    seal = verifier._seal
    object.__setattr__(seal, "_repo_root_context", tmp_path / "redirected")
    with pytest.raises(H40GuardError, match="runtime authority"):
        verifier.assert_runtime_integrity()


def test_mutable_split_contents_cannot_change_authority(tmp_path: Path) -> None:
    verifier = _invalid_fixture(tmp_path).verifier
    verifier._split.exclusion_counts["attacker"] = 1
    with pytest.raises(H40GuardError, match="runtime authority"):
        verifier.assert_runtime_integrity()


def test_class_method_replacement_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _invalid_fixture(tmp_path).verifier
    monkeypatch.setattr(
        H40ProductionDiscoveryEvidenceVerifier, "verify_candidate",
        lambda self, *args, **kwargs: True,
    )
    with pytest.raises(H40GuardError, match="runtime authority"):
        verifier.assert_runtime_integrity()


def test_class_validator_and_science_replacement_rejected_at_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    monkeypatch.setattr(
        H40ProductionDiscoveryEvidenceVerifier, "assert_runtime_integrity",
        lambda self, **kwargs: None,
    )
    monkeypatch.setattr(
        H40ProductionDiscoveryEvidenceVerifier, "verify_discovery_manifest",
        lambda self, evidence, entries: None,
    )
    with pytest.raises(H40GuardError, match="runtime authority"):
        _candidate_lock_attempt(fixture.verifier, fixture, monkeypatch)


def test_b15_cold_restore_rejects_tampered_exact_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, discovery, candidate, seal, run, authority, _ = _make_synthetic_chain_with_production_seal(
        monkeypatch, tmp_path,
    )
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", discovery, service=service)
    store.persist_authorization("02_candidate_lock", candidate, service=service)
    split = seal._split_manifest_context
    assert split is not None
    root = tmp_path / "bounded-evidence"
    root.mkdir()
    verifier = H40ProductionDiscoveryEvidenceVerifier(
        approved_evidence_root=root, seal=seal,
        authorization_receipt=discovery.receipt, split_manifest=split,
    )
    verifier.assert_runtime_integrity()
    object.__setattr__(verifier._resolver, "_root", tmp_path / "redirected")
    replay = H40LifecycleAuthorityService.production(
        implementation_authority=authority, evidence_verifier=verifier,
    )
    resolver = _ProductionAuthorityResolver(authority=authority, run=run, seal=seal)
    with pytest.raises(H40GuardError, match="runtime authority"):
        store.restore_authorization(
            run.run_authority_id, candidate.receipt_hash,
            service=replay, resolver=resolver,
        )


def test_b18_frozen_identities_exact() -> None:
    assert compute_protocol_authority_hash() == (
        "a83f8fc7a5ca7109fb8cd7fed114d87c3b2c968b5145c11cada203aa5111d1ce"
    )
    assert compute_semantic_root_hash() == (
        "71889a35f227ed734272b712851174a69bf9dbb12ea3f87cd84c26e7c66f6af1"
    )
    assert materialize_h40_search_space_production().structural_ledger_hash == (
        "483f68502b57972deae071c7bd4587ca3e57ccaa72bd99fb0de07b4f0ab8c85f"
    )
    assert compute_lifecycle_semantic_root_hash() == (
        "846591f8eac0e1abbedaeeff4c2b0bb7648fe51bdaf981e3309c6f6c440aba8e"
    )
    assert compute_lifecycle_governance_authority_hash() == (
        "7e9433aa2ee706dda61871c6ad2b1a1aee4cf7a8f9b6365351942096b5347c84"
    )
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH == (
        "d3a304ddc6bcb7b7fc398ccf45a751a0afa3f91634a09ddff8e199af1970e440"
    )
