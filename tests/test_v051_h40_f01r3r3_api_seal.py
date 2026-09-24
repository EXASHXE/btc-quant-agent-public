"""Focused tests for H40 F01R3R3 final API seal repair.

Covers R46 through R52:
- R46: TEST_COMMIT_TOKEN cannot be imported/exported from btc_quant_agent.h40
- R47: H40LifecycleArtifactStore exposes no public raw head-commit method
- R48: Stale cached production authorization cannot directly commit without service revalidation
- R49: Orphan exact receipt cannot be committed merely from authorization possession
- R50: Valid transitions commit only through persist_authorization with exact issuer
- R51: Two valid sibling authorizations racing through persist_authorization yield one winner
- R52: Head-integrity corruption tests do not depend on raw commit authority
"""

from __future__ import annotations

import concurrent.futures
import inspect
import sqlite3
import sys
from pathlib import Path

import pytest

import btc_quant_agent.h40 as h40_module
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
    H40SyntheticAuthorityResolver,
    H40SyntheticEvidenceVerifier,
    VerifiedLifecycleAuthorization,
    compute_lifecycle_child_hashes,
    compute_lifecycle_governance_authority_hash,
    compute_lifecycle_semantic_root_hash,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    materialize_h40_search_space_production,
)
from btc_quant_agent.research_contract.canonical import canonical_json

_TESTS_DIR = str(Path(__file__).resolve().parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from test_v051_h40_f01_lifecycle_authority import (  # noqa: E402
    TS,
    _build_discovery_chain,
    _implementation_authority,
    _ProductionEvidenceVerifier,
    _typed_production_authority_fixture,
)


def test_r46_test_commit_token_cannot_be_imported_or_exported() -> None:
    """R46: TEST_COMMIT_TOKEN cannot be imported/exported from btc_quant_agent.h40 or lifecycle_authority."""
    # Cannot be accessed on btc_quant_agent.h40 package
    assert not hasattr(h40_module, "TEST_COMMIT_TOKEN")
    assert "TEST_COMMIT_TOKEN" not in h40_module.__all__

    # Cannot be accessed on lifecycle_authority module
    assert not hasattr(lifecycle_authority_module, "TEST_COMMIT_TOKEN")
    assert "TEST_COMMIT_TOKEN" not in lifecycle_authority_module.__all__

    # Internal private token must also not exist
    assert not hasattr(lifecycle_authority_module, "_TEST_COMMIT_TOKEN")

    # Dynamic import from package must fail
    with pytest.raises(ImportError):
        from btc_quant_agent.h40 import TEST_COMMIT_TOKEN  # type: ignore[attr-defined]

    # Dynamic import from module must fail
    with pytest.raises(ImportError):
        from btc_quant_agent.h40.lifecycle_authority import (
            TEST_COMMIT_TOKEN,  # type: ignore[attr-defined] # noqa: F401
        )


def test_r47_store_exposes_no_public_raw_head_commit_method() -> None:
    """R47: H40LifecycleArtifactStore exposes no public raw head-commit method."""
    store = H40LifecycleArtifactStore("/tmp/test_r47")

    # No public advance_run_head or commit_run_head methods
    assert not hasattr(store, "advance_run_head")
    assert not hasattr(H40LifecycleArtifactStore, "advance_run_head")
    assert not hasattr(store, "commit_run_head")
    assert not hasattr(H40LifecycleArtifactStore, "commit_run_head")

    # List all public attributes/methods on store
    public_members = [m for m in dir(store) if not m.startswith("_")]
    allowed_public_members = {
        "get_committed_run_head",
        "persist_authorization",
        "restore_authorization",
        "restore_receipt",
        "sqlite_path",
    }
    assert set(public_members).issubset(allowed_public_members)

    # persist_authorization requires exact issuing service and VerifiedLifecycleAuthorization
    sig = inspect.signature(store.persist_authorization)
    assert "service" in sig.parameters
    assert "authorization" in sig.parameters

    # Private _commit_run_head requires VerifiedLifecycleAuthorization
    with pytest.raises(TypeError, match="authorization must be VerifiedLifecycleAuthorization"):
        store._commit_run_head(authorization=None)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="authorization must be VerifiedLifecycleAuthorization"):
        store._commit_run_head(authorization="raw_string")  # type: ignore[arg-type]


def test_r48_stale_cached_production_authorization_cannot_directly_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R48: Stale cached production authorization cannot directly commit without service revalidation."""
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
    verifier = _ProductionEvidenceVerifier(tmp_path / "verifier")
    service = H40LifecycleAuthorityService.production(
        implementation_authority=authority,
        evidence_verifier=verifier,
    )

    # Issue a valid production authorization
    auth = service.authorize_discovery(
        implementation_authority=authority,
        run_authority=run,
        seal=seal,
        authorized_at_utc=TS,
    )
    assert isinstance(auth, VerifiedLifecycleAuthorization)

    # Invalidate source after authorization issued
    cold_state["available"] = False

    # Revalidation fails closed
    with pytest.raises(H40GuardError, match="failed cold validation"):
        service.revalidate_authorization(auth)

    # Caller attempts to persist stale cached authorization: fails closed
    with pytest.raises(H40GuardError, match="failed cold validation"):
        store.persist_authorization(
            "01_discovery_authorization",
            auth,
            service=service,
        )

    # Head was never committed
    head = store.get_committed_run_head(run.run_authority_id)
    assert head is None


def test_r49_orphan_exact_receipt_cannot_be_committed_merely_from_possession(tmp_path: Path) -> None:
    """R49: Orphan exact receipt cannot be committed merely from authorization possession."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    # Simulate orphan receipt written to disk without head advance
    receipts_dir = store._receipts_dir(run_id)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    envelope = store._envelope(chain.discovery)
    receipt_file = receipts_dir / f"{chain.discovery.receipt_hash}.json"
    receipt_file.write_text(canonical_json(envelope) + "\n", encoding="utf-8")

    # Durable head is not committed
    assert store.get_committed_run_head(run_id) is None

    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(chain.authority,),
        run_authorities=(chain.run,),
        runtime_seals=(chain.seal,),
    )

    # Case 1: restore_authorization rejects because no durable run head exists
    with pytest.raises(H40GuardError, match="no committed durable run head found"):
        store.restore_authorization(
            run_id,
            chain.discovery.receipt_hash,
            service=chain.service,
            resolver=resolver,
        )

    # Now legitimately commit discovery
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    assert store.get_committed_run_head(run_id) is not None

    # Case 2: place orphan candidate receipt on disk without committing head
    cand_envelope = store._envelope(chain.candidate)
    cand_file = receipts_dir / f"{chain.candidate.receipt_hash}.json"
    cand_file.write_text(canonical_json(cand_envelope) + "\n", encoding="utf-8")

    # restore_authorization on the uncommitted candidate receipt rejects
    with pytest.raises(H40GuardError, match="not in committed run head lineage"):
        store.restore_authorization(
            run_id,
            chain.candidate.receipt_hash,
            service=chain.service,
            resolver=resolver,
        )

    # Calling persist_authorization without service is impossible
    with pytest.raises(TypeError, match="service must be H40LifecycleAuthorityService"):
        store.persist_authorization(
            "02_candidate_lock",
            chain.candidate,
            service=None,  # type: ignore[arg-type]
        )

    # SQLite head remains at discovery, candidate was not committed
    assert store.get_committed_run_head(run_id).head_receipt_hash == chain.discovery.receipt_hash


def test_r50_valid_transitions_commit_only_through_persist_authorization_with_exact_issuer(tmp_path: Path) -> None:
    """R50: Valid transitions commit only through persist_authorization with exact issuer."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    # Foreign service cannot persist authorization issued by another service
    foreign_service = H40LifecycleAuthorityService.synthetic_for_tests(
        _implementation_authority(),
        H40SyntheticEvidenceVerifier({}),
    )
    with pytest.raises(H40GuardError, match="foreign verifier authority"):
        store.persist_authorization(
            "01_discovery_authorization",
            chain.discovery,
            service=foreign_service,
        )

    assert store.get_committed_run_head(run_id) is None

    # Persisting with exact issuing service succeeds
    p1 = store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    assert p1.exists()

    head1 = store.get_committed_run_head(run_id)
    assert head1 is not None
    assert head1.transition_sequence == 0
    assert head1.head_receipt_hash == chain.discovery.receipt_hash

    # Next step (Candidate Lock) fails with foreign service
    with pytest.raises(H40GuardError, match="foreign verifier authority"):
        store.persist_authorization(
            "02_candidate_lock",
            chain.candidate,
            service=foreign_service,
        )
    assert store.get_committed_run_head(run_id).transition_sequence == 0

    # Succeeds with exact issuing service
    p2 = store.persist_authorization(
        "02_candidate_lock",
        chain.candidate,
        service=chain.service,
    )
    assert p2.exists()

    head2 = store.get_committed_run_head(run_id)
    assert head2 is not None
    assert head2.transition_sequence == 1
    assert head2.head_receipt_hash == chain.candidate.receipt_hash


def test_r51_two_valid_sibling_authorizations_race_through_persist_authorization_yield_one_winner(
    tmp_path: Path,
) -> None:
    """R51: Two valid sibling authorizations racing through persist_authorization yield exactly one winner."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    # Commit genesis discovery
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )

    # Valid sibling 1: candidate lock
    auth_cand = chain.candidate

    # Valid sibling 2: termination from discovery
    auth_term = chain.service.authorize_termination(
        prior_authority=chain.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="sibling termination in race test",
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
        f1 = executor.submit(try_persist, auth_cand, "02_candidate_lock")
        f2 = executor.submit(try_persist, auth_term, "02_termination")
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
    assert committed.transition_sequence == 1


def test_r52_head_integrity_corruption_tests_do_not_depend_on_raw_commit_authority(tmp_path: Path) -> None:
    """R52: Head-integrity corruption tests do not depend on raw commit authority."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    # Commit genesis legally
    store.persist_authorization(
        "01_discovery_authorization",
        chain.discovery,
        service=chain.service,
    )
    valid_head = store.get_committed_run_head(run_id)
    assert valid_head is not None

    # Tamper 1: corrupt head_hash column directly in SQLite
    conn = sqlite3.connect(str(store.sqlite_path))
    conn.execute(
        "UPDATE h40_lifecycle_run_heads SET head_hash = 'corrupted_hash_value' WHERE run_authority_id = ?",
        (run_id,),
    )
    conn.commit()
    conn.close()

    # get_committed_run_head fails closed on tampered head_hash
    with pytest.raises(H40GuardError, match="does not match canonical head hash"):
        store.get_committed_run_head(run_id)

    # Next persist_authorization fails closed
    with pytest.raises(H40GuardError, match="does not match canonical head hash"):
        store.persist_authorization(
            "02_candidate_lock",
            chain.candidate,
            service=chain.service,
        )

    # Tamper 2: empty head_hash fails closed
    conn = sqlite3.connect(str(store.sqlite_path))
    conn.execute(
        "UPDATE h40_lifecycle_run_heads SET head_hash = '' WHERE run_authority_id = ?",
        (run_id,),
    )
    conn.commit()
    conn.close()

    with pytest.raises(H40GuardError, match="lacks authoritative head_hash integrity column"):
        store.get_committed_run_head(run_id)

    # Tamper 3: scalar column mismatch against head_json
    conn = sqlite3.connect(str(store.sqlite_path))
    conn.execute(
        "UPDATE h40_lifecycle_run_heads SET transition_sequence = 99, head_hash = 'x' WHERE run_authority_id = ?",
        (run_id,),
    )
    conn.commit()
    conn.close()

    with pytest.raises(H40GuardError, match="does not match scalar column"):
        store.get_committed_run_head(run_id)


def test_frozen_hashes_exact_and_unchanged() -> None:
    """Verify that the 3 scientific hashes and child hashes remain exact and unchanged."""
    child_hashes = compute_lifecycle_child_hashes()
    assert (
        child_hashes["persistence_replay_contract"]
        == "5f014b867be17019c2be91ff48f8e23a43ed29678fc5589430ba174046fceaae"
    )
    assert (
        compute_lifecycle_semantic_root_hash()
        == "846591f8eac0e1abbedaeeff4c2b0bb7648fe51bdaf981e3309c6f6c440aba8e"
    )
    assert (
        compute_lifecycle_governance_authority_hash()
        == "7e9433aa2ee706dda61871c6ad2b1a1aee4cf7a8f9b6365351942096b5347c84"
    )
    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH
    assert compute_semantic_root_hash() == EXPECTED_SEMANTIC_ROOT_HASH
    assert (
        materialize_h40_search_space_production().structural_ledger_hash
        == EXPECTED_STRUCTURAL_LEDGER_HASH
    )
