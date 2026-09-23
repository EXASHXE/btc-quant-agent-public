"""Synthetic-only adversarial checks for the production verifier identity seal."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_v051_h40_f01_lifecycle_authority import _build_discovery_chain
from test_v051_h40_f01r3r1_durable_authority import (
    _make_synthetic_chain_with_production_seal,
    _ProductionAuthorityResolver,
)
from test_v051_h40_p3b_production_discovery_verifier import _invalid_fixture

from btc_quant_agent.h40 import (
    H40CandidateVerification,
    H40LifecycleArtifactStore,
    H40LifecycleAuthorityService,
    H40LifecycleEvidenceVerifier,
    H40ProductionDiscoveryEvidenceVerifier,
    H40ReasonCode,
    H40SyntheticEvidenceVerifier,
)
from btc_quant_agent.h40.guards import H40GuardError


class RogueVerifier:
    synthetic_only = False

    def __init__(self) -> None:
        self.manifest_calls = 0
        self.candidate_calls = 0

    def verify_discovery_manifest(self, evidence: Any, entries: Any) -> None:
        self.manifest_calls += 1

    def verify_candidate(self, entry: Any, *, run_authority_id: str,
                         correction_manifest_hash: str) -> H40CandidateVerification:
        self.candidate_calls += 1
        return H40CandidateVerification(True, Decimal(999), Decimal(999))

    def verify_wf_fold(self, entry: Any, *, evidence: Any) -> bool:
        return True


class VerifierSubclass(H40ProductionDiscoveryEvidenceVerifier):
    pass


class VerifierProxy:
    synthetic_only = False

    def __init__(self, wrapped: H40ProductionDiscoveryEvidenceVerifier) -> None:
        self.wrapped = wrapped
        self.calls = 0

    def verify_discovery_manifest(self, evidence: Any, entries: Any) -> None:
        self.calls += 1
        self.wrapped.verify_discovery_manifest(evidence, entries)

    def verify_candidate(self, entry: Any, *, run_authority_id: str,
                         correction_manifest_hash: str) -> H40CandidateVerification:
        self.calls += 1
        return self.wrapped.verify_candidate(
            entry, run_authority_id=run_authority_id,
            correction_manifest_hash=correction_manifest_hash,
        )

    def verify_wf_fold(self, entry: Any, *, evidence: Any) -> bool:
        self.calls += 1
        return self.wrapped.verify_wf_fold(entry, evidence=evidence)


def _candidate_lock_attempt(
    verifier: H40LifecycleEvidenceVerifier | None,
    fixture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reach only the candidate-lock identity gate with a synthetic prior fixture."""
    service = H40LifecycleAuthorityService.production(evidence_verifier=verifier)
    monkeypatch.setattr(service, "_require_prior", lambda *args, **kwargs: None)
    receipt = fixture.verifier._receipt
    prior = SimpleNamespace(
        context={"seal": fixture.verifier._seal},
        receipt=receipt,
        receipt_hash=receipt.receipt_sha256,
        run_authority_id=fixture.run_id,
    )
    service.authorize_candidate_lock(
        discovery_authority=prior,  # type: ignore[arg-type]
        evidence=fixture.evidence,
        locked_at_utc="2026-09-23T00:00:00Z",
        verified_at_utc="2026-09-23T00:00:00Z",
    )


def test_a01_real_concrete_verifier_reaches_scientific_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    with pytest.raises(H40GuardError) as exc:
        _candidate_lock_attempt(fixture.verifier, fixture, monkeypatch)
    assert exc.value.reason_code == H40ReasonCode.NOT_TESTABLE
    assert fixture.verifier._manifest_hash == fixture.evidence.correction_input_evidence_manifest_hash


def test_a02_a03_all_pass_rogue_rejected_before_methods(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    rogue = RogueVerifier()
    assert isinstance(rogue, H40LifecycleEvidenceVerifier)
    with pytest.raises(H40GuardError, match="unaccepted production Discovery verifier") as exc:
        _candidate_lock_attempt(rogue, fixture, monkeypatch)
    assert exc.value.reason_code == H40ReasonCode.CONFIG_IDENTITY_CONFLICT
    assert (rogue.manifest_calls, rogue.candidate_calls) == (0, 0)


def test_a04_subclass_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _invalid_fixture(tmp_path)
    subclass = object.__new__(VerifierSubclass)
    with pytest.raises(H40GuardError, match="unaccepted production Discovery verifier"):
        _candidate_lock_attempt(subclass, fixture, monkeypatch)


def test_a05_wrapper_rejected_before_delegation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    proxy = VerifierProxy(fixture.verifier)
    with pytest.raises(H40GuardError, match="unaccepted production Discovery verifier"):
        _candidate_lock_attempt(proxy, fixture, monkeypatch)
    assert proxy.calls == 0


def test_a06_synthetic_verifier_still_rejected_in_production() -> None:
    with pytest.raises(ValueError, match="synthetic/test-only verifier"):
        H40LifecycleAuthorityService.production(
            evidence_verifier=H40SyntheticEvidenceVerifier({}),
        )


def test_a07_synthetic_lifecycle_mode_remains_functional() -> None:
    assert _build_discovery_chain().candidate.target_state == "H40_CANDIDATE_LOCKED"


def test_a08_no_verifier_is_not_testable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    with pytest.raises(H40GuardError, match="no accepted scientific evidence verifier") as exc:
        _candidate_lock_attempt(None, fixture, monkeypatch)
    assert exc.value.reason_code == H40ReasonCode.NOT_TESTABLE


def test_a09_foreign_verifier_cannot_cold_restore_candidate_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, discovery, candidate, seal, run, authority, _ = _make_synthetic_chain_with_production_seal(
        monkeypatch, tmp_path,
    )
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", discovery, service=service)
    store.persist_authorization("02_candidate_lock", candidate, service=service)
    rogue = RogueVerifier()
    foreign_service = H40LifecycleAuthorityService.production(
        implementation_authority=authority, evidence_verifier=rogue,
    )
    resolver = _ProductionAuthorityResolver(authority=authority, run=run, seal=seal)
    with pytest.raises(H40GuardError, match="unaccepted production Discovery verifier"):
        store.restore_authorization(
            run.run_authority_id, candidate.receipt_hash,
            service=foreign_service, resolver=resolver,
        )
    assert (rogue.manifest_calls, rogue.candidate_calls) == (0, 0)


def test_a10_receipt_verifier_id_unchanged_on_exact_type_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, candidate, _, _, _, _ = _make_synthetic_chain_with_production_seal(monkeypatch, tmp_path)
    assert type(_invalid_fixture(tmp_path / "verifier").verifier) is H40ProductionDiscoveryEvidenceVerifier
    assert candidate.receipt.selection_verifier_id == "H40_DISCOVERY_SELECTION_VERIFIER_V1"
