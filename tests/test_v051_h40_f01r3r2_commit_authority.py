"""Focused tests for H40 F01R3R2 commit authority seal targeted repairs.

Covers R30 through R45:
- R30: raw commit without VerifiedLifecycleAuthorization is rejected/impossible
- R31: forged typed Discovery envelope cannot create genesis
- R32: forged typed WF receipt cannot jump Discovery -> WF
- R33: forged termination source_state mismatch cannot commit
- R34: persist_authorization no longer accepts arbitrary revalidate callable
- R35: foreign lifecycle service cannot persist another service's authorization
- R36: stale cached production-shaped authorization fails persistence after source invalidation
- R37: successor authorization.source_state must equal current durable head state
- R38: F02 target cannot commit at storage boundary
- R39: empty legacy head_hash fails closed
- R40: valid synthetic Discovery persists via exact issuing synthetic service
- R41: valid synthetic Candidate persists only after Discovery head
- R42: two valid sibling VerifiedLifecycleAuthorizations race; exactly one commits
- R43: valid terminal authorization remains absorbing after restart
- R44: persist exact retry is idempotent only after service revalidation
- R45: current hashes remain exact and unchanged
"""

from __future__ import annotations

import concurrent.futures
import inspect
from pathlib import Path

import pytest

import btc_quant_agent.h40.lifecycle_authority as lifecycle_authority_module
from btc_quant_agent.h40 import (
    EXPECTED_PROTOCOL_AUTHORITY_HASH,
    EXPECTED_SEMANTIC_ROOT_HASH,
    EXPECTED_STRUCTURAL_LEDGER_HASH,
    H40GuardError,
    H40LifecycleArtifactStore,
    H40LifecycleAuthorityService,
    H40ReasonCode,
    H40RunAuthority,
    H40RuntimeSnapshotSeal,
    TEST_COMMIT_TOKEN,
    VerifiedLifecycleAuthorization,
    compute_lifecycle_child_hashes,
    compute_lifecycle_governance_authority_hash,
    compute_lifecycle_semantic_root_hash,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    materialize_h40_search_space_production,
)

import sys

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from test_v051_h40_f01_lifecycle_authority import (  # noqa: E402
    TS,
    _ProductionEvidenceVerifier,
    _build_discovery_chain,
    _build_wf_chain,
    _hash,
    _implementation_authority,
    _make_mock_discovery_receipt,
    _make_mock_termination_receipt,
    _make_mock_wf_receipt,
    _publish_mock_envelope,
    _typed_production_authority_fixture,
)


def test_r30_raw_commit_without_verified_authorization_rejected(tmp_path: Path) -> None:
    """R30: Raw commit without VerifiedLifecycleAuthorization is rejected fail-closed."""
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = _hash("run-r30")
    disc = _make_mock_discovery_receipt(run_id)
    h = _publish_mock_envelope(store, disc)

    # Calling advance_run_head without _test_token fails closed
    with pytest.raises(
        H40GuardError,
        match="raw durable-head advance without VerifiedLifecycleAuthorization is prohibited in production",
    ):
        store.advance_run_head(
            run_authority_id=run_id,
            receipt_hash=h,
            target_state="H40_DISCOVERY",
            predecessor_receipt_hash=None,
        )

    # Calling private _advance_verified_run_head without VerifiedLifecycleAuthorization fails type check
    with pytest.raises(TypeError, match="authorization must be VerifiedLifecycleAuthorization"):
        store._advance_verified_run_head(authorization="not-an-auth-object")  # type: ignore[arg-type]


def test_r31_forged_typed_discovery_envelope_cannot_create_genesis(tmp_path: Path) -> None:
    """R31: Forged typed Discovery envelope cannot create genesis."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    # Forged envelope written directly to disk
    forged_disc = _make_mock_discovery_receipt(run_id)
    h = _publish_mock_envelope(store, forged_disc)

    # Calling persist_authorization with non-VerifiedLifecycleAuthorization fails
    with pytest.raises(TypeError, match="only verified lifecycle authorization can be persisted"):
        store.persist_authorization("01_disc", {"not": "verified"}, service=chain.service)  # type: ignore[arg-type]

    # VerifiedLifecycleAuthorization cannot be directly constructed by callers
    with pytest.raises(TypeError, match="verified lifecycle authorization cannot be caller-constructed"):
        VerifiedLifecycleAuthorization(
            receipt=forged_disc,
            source_state="H40_P1_SCAFFOLDED",
            target_state="H40_DISCOVERY",
            run_authority_id=run_id,
            upstream_receipt_hash=None,
            context={},
            issuer_id=object(),
            synthetic_only=True,
            token=object(),
        )

    # Forged authorization object via object.__new__ fails revalidation
    forged_auth = object.__new__(VerifiedLifecycleAuthorization)
    object.__setattr__(forged_auth, "_receipt_hash", h)
    object.__setattr__(forged_auth, "_run_authority_id", run_id)
    object.__setattr__(forged_auth, "_issuer_id", object())
    with pytest.raises(H40GuardError, match="foreign verifier authority"):
        store.persist_authorization("01_disc", forged_auth, service=chain.service)

    committed = store.get_committed_run_head(run_id)
    assert committed is None


def test_r32_forged_typed_wf_receipt_cannot_jump_discovery_to_wf(tmp_path: Path) -> None:
    """R32: Forged typed WF receipt cannot jump Discovery -> WF."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    r0 = chain.discovery.receipt_hash
    run_id = chain.run.run_authority_id

    # Create mock WF receipt pointing directly to Discovery receipt as predecessor
    wf_receipt = _make_mock_wf_receipt(run_id, r0, slot_index=1)
    wf_hash = _publish_mock_envelope(store, wf_receipt)

    with pytest.raises(
        H40GuardError,
        match="transition source state 'H40_CANDIDATE_LOCKED' does not match current durable head state 'H40_DISCOVERY'",
    ):
        store.advance_run_head(
            run_authority_id=run_id,
            receipt_hash=wf_hash,
            target_state="H40_WALK_FORWARD_VALIDATED",
            predecessor_receipt_hash=r0,
            _test_token=TEST_COMMIT_TOKEN,
        )


def test_r33_forged_termination_source_state_mismatch_cannot_commit(tmp_path: Path) -> None:
    """R33: Forged termination source_state mismatch cannot commit."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    r0 = chain.discovery.receipt_hash
    run_id = chain.run.run_authority_id

    # Termination receipt claims source_state='H40_CANDIDATE_LOCKED', but current head is 'H40_DISCOVERY'
    term_receipt = _make_mock_termination_receipt(
        run_id,
        r0,
        source_state="H40_CANDIDATE_LOCKED",
        target_state="H40_NO_GO",
    )
    t_hash = _publish_mock_envelope(store, term_receipt)

    with pytest.raises(
        H40GuardError,
        match="transition source state 'H40_CANDIDATE_LOCKED' does not match current durable head state 'H40_DISCOVERY'",
    ):
        store.advance_run_head(
            run_authority_id=run_id,
            receipt_hash=t_hash,
            target_state="H40_NO_GO",
            predecessor_receipt_hash=r0,
            _test_token=TEST_COMMIT_TOKEN,
        )


def test_r34_persist_authorization_rejects_arbitrary_revalidate_callable(tmp_path: Path) -> None:
    """R34: persist_authorization no longer accepts arbitrary revalidate callable."""
    sig = inspect.signature(H40LifecycleArtifactStore.persist_authorization)
    assert "revalidate" not in sig.parameters
    assert "service" in sig.parameters
    assert sig.parameters["service"].kind == inspect.Parameter.KEYWORD_ONLY

    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    with pytest.raises(TypeError):
        store.persist_authorization(  # type: ignore[call-arg]
            "01_discovery_authorization",
            chain.discovery,
            revalidate=lambda _: None,
        )


def test_r35_foreign_lifecycle_service_cannot_persist_another_service_authorization(tmp_path: Path) -> None:
    """R35: Foreign lifecycle service cannot persist another service's authorization."""
    chain_a = _build_discovery_chain()
    chain_b = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)

    # Attempt to persist chain_a's discovery with chain_b's service
    with pytest.raises(H40GuardError, match="foreign verifier authority"):
        store.persist_authorization(
            "01_discovery_authorization",
            chain_a.discovery,
            service=chain_b.service,
        )

    committed = store.get_committed_run_head(chain_a.run.run_authority_id)
    assert committed is None


def test_r36_stale_cached_production_authorization_fails_after_invalidation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R36: Stale cached production-shaped authorization fails persistence after source invalidation."""
    source_manifest, split_manifest, attestation, cold_state = _typed_production_authority_fixture(monkeypatch)
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source_manifest,
        split_manifest=split_manifest,
        runtime_attestation=attestation,
        repo_root=tmp_path,
    )
    authority = _implementation_authority()
    monkeypatch.setattr(
        lifecycle_authority_module,
        "ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH",
        authority.lifecycle_implementation_authority_hash,
    )
    run = H40RunAuthority.from_seal(seal, authority.lifecycle_implementation_authority_hash)
    store = H40LifecycleArtifactStore(tmp_path)
    verifier = _ProductionEvidenceVerifier()
    service = H40LifecycleAuthorityService.production(
        implementation_authority=authority,
        evidence_verifier=verifier,
    )

    discovery = service.authorize_discovery(
        implementation_authority=authority,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
    )

    # Invalidate source after authorization issued
    cold_state["available"] = False

    # Persist must fail during revalidation
    with pytest.raises(H40GuardError, match="failed cold validation"):
        store.persist_authorization(
            "01_discovery_authorization",
            discovery,
            service=service,
        )

    committed = store.get_committed_run_head(run.run_authority_id)
    assert committed is None


def test_r37_successor_source_state_must_equal_current_head_state(tmp_path: Path) -> None:
    """R37: Successor authorization.source_state must equal current durable head state."""
    chain = _build_discovery_chain()
    wf_chain = _build_wf_chain(chain)
    wf_auth = wf_chain.wf
    assert wf_auth.source_state == "H40_CANDIDATE_LOCKED"

    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    head = store.get_committed_run_head(chain.run.run_authority_id)
    assert head is not None
    assert head.head_state == "H40_DISCOVERY"

    # Attempting to persist WF authorization directly on Discovery head fails closed
    with pytest.raises(
        H40GuardError,
        match="predecessor receipt hash mismatch|transition source state .* does not match current durable head state",
    ):
        store.persist_authorization("03_wf_validation", wf_auth, service=chain.service)


def test_r38_f02_target_cannot_commit_at_storage_boundary(tmp_path: Path) -> None:
    """R38: F02 target cannot commit at storage boundary."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    with pytest.raises(H40GuardError, match="F02 confirmation evaluated once is sealed and prohibited"):
        store.advance_run_head(
            run_authority_id=run_id,
            receipt_hash=_hash("dummy-hash"),
            target_state="H40_CONFIRMATION_EVALUATED_ONCE",
            predecessor_receipt_hash=None,
            _test_token=TEST_COMMIT_TOKEN,
        )


def test_r39_empty_legacy_head_hash_fails_closed(tmp_path: Path) -> None:
    """R39: Empty legacy head_hash fails closed on authoritative read."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    run_id = chain.run.run_authority_id

    # Tamper with head_hash in SQLite to set it to empty string
    conn = store._get_sqlite_conn()
    conn.execute(
        "UPDATE h40_lifecycle_run_heads SET head_hash = '' WHERE run_authority_id = ?",
        (run_id,),
    )
    conn.close()

    with pytest.raises(H40GuardError, match="durable head row lacks authoritative head_hash integrity column"):
        store.get_committed_run_head(run_id)


def test_r40_valid_synthetic_discovery_persists_via_issuing_service(tmp_path: Path) -> None:
    """R40: Valid synthetic Discovery persists via exact issuing synthetic service."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    p = store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    assert p.is_file()

    head = store.get_committed_run_head(chain.run.run_authority_id)
    assert head is not None
    assert head.transition_sequence == 0
    assert head.head_state == "H40_DISCOVERY"
    assert head.head_receipt_hash == chain.discovery.receipt_hash
    assert not head.terminal


def test_r41_valid_synthetic_candidate_persists_only_after_discovery(tmp_path: Path) -> None:
    """R41: Valid synthetic Candidate persists only after Discovery head."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)

    # Persisting Candidate before Discovery head fails closed
    with pytest.raises(H40GuardError, match="non-null predecessor cannot commit as sequence zero genesis|cannot be genesis"):
        store.persist_authorization("02_candidate_lock", chain.candidate, service=chain.service)

    # Persist Discovery first
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)

    # Now Candidate succeeds
    p = store.persist_authorization("02_candidate_lock", chain.candidate, service=chain.service)
    assert p.is_file()

    head = store.get_committed_run_head(chain.run.run_authority_id)
    assert head is not None
    assert head.transition_sequence == 1
    assert head.head_state == "H40_CANDIDATE_LOCKED"
    assert head.head_receipt_hash == chain.candidate.receipt_hash
    assert not head.terminal


def test_r42_two_valid_sibling_authorizations_race_exactly_one_commits(tmp_path: Path) -> None:
    """R42: Two valid sibling VerifiedLifecycleAuthorizations race; exactly one commits."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)

    # Sibling 1: candidate lock (Discovery -> Candidate Locked)
    cand_1 = chain.candidate
    # Sibling 2: termination (Discovery -> No Go)
    cand_2 = chain.service.authorize_termination(
        prior_authority=chain.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="sibling termination",
        terminated_at_utc=TS,
    )
    assert cand_1.receipt_hash != cand_2.receipt_hash
    assert cand_1.source_state == "H40_DISCOVERY"
    assert cand_2.source_state == "H40_DISCOVERY"

    def try_persist(auth: VerifiedLifecycleAuthorization, key: str) -> tuple[str, bool, str]:
        s = H40LifecycleArtifactStore(tmp_path)
        try:
            s.persist_authorization(key, auth, service=chain.service)
            return (auth.receipt_hash, True, "")
        except H40GuardError as exc:
            return (auth.receipt_hash, False, str(exc))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(try_persist, cand_1, "02_candidate_lock")
        f2 = executor.submit(try_persist, cand_2, "02_termination")
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


def test_r43_valid_terminal_authorization_remains_absorbing_after_restart(tmp_path: Path) -> None:
    """R43: Valid terminal authorization remains absorbing after restart."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)

    term_auth = chain.service.authorize_termination(
        prior_authority=chain.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="terminal failure",
        terminated_at_utc=TS,
    )
    store.persist_authorization("term", term_auth, service=chain.service)

    fresh_store = H40LifecycleArtifactStore(tmp_path)
    committed = fresh_store.get_committed_run_head(chain.run.run_authority_id)
    assert committed is not None
    assert committed.terminal
    assert committed.head_state == "H40_NO_GO"

    with pytest.raises(H40GuardError, match="terminal state .* no forward commits allowed"):
        fresh_store.persist_authorization("02_candidate_lock", chain.candidate, service=chain.service)


def test_r44_persist_exact_retry_idempotent_only_after_service_revalidation(tmp_path: Path) -> None:
    """R44: Persist exact retry is idempotent only after service revalidation."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    calls = 0

    orig_reval = chain.service.revalidate_authorization

    def spy_reval(auth: VerifiedLifecycleAuthorization) -> None:
        nonlocal calls
        calls += 1
        orig_reval(auth)

    chain.service.revalidate_authorization = spy_reval

    p1 = store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    p2 = store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)
    assert p1 == p2
    assert calls == 2

    # If service revalidation fails, retry fails closed and does not return idempotent success
    def fail_reval(auth: VerifiedLifecycleAuthorization) -> None:
        raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "revalidation injected failure")

    chain.service.revalidate_authorization = fail_reval
    with pytest.raises(H40GuardError, match="revalidation injected failure"):
        store.persist_authorization("01_discovery_authorization", chain.discovery, service=chain.service)


def test_r45_current_hashes_remain_exact_and_unchanged() -> None:
    """R45: Current canonical hashes remain exact and unchanged."""
    child_hashes = compute_lifecycle_child_hashes()
    assert (
        child_hashes["persistence_replay_contract"]
        == "5f014b867be17019c2be91ff48f8e23a43ed29678fc5589430ba174046fceaae"
    )
    assert (
        compute_lifecycle_semantic_root_hash()
        == "f0aa35eb91055a76129eae5c00be38174fcc13ae9fe08521d9202e93dc5d43d4"
    )
    assert (
        compute_lifecycle_governance_authority_hash()
        == "72924dd22b3c9283964cdf368f7a754bd6f703a110989187620b36076a25a511"
    )
    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH
    assert compute_semantic_root_hash() == EXPECTED_SEMANTIC_ROOT_HASH
    assert (
        materialize_h40_search_space_production().structural_ledger_hash
        == EXPECTED_STRUCTURAL_LEDGER_HASH
    )
