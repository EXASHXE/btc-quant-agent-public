"""Focused tests for H40 F01R3R4 Lineage and Receipt Durability Closure.

Covers R53 through R62:
- RG-B02-01 (R53-R56): Verified committed lineage before membership and restoration
- RG-H01-01 (R57-R61): Authoritative receipt-directory durability on all commit paths
- Regression (R62): Sibling CAS, terminal absorption, sequence monotonicity, F02 seal
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_v051_h40_f01_lifecycle_authority import (
    TS,
    _build_discovery_chain,
    _build_wf_chain,
    _publish_mock_envelope,
)

import btc_quant_agent.h40.lifecycle_authority as lifecycle_authority_module
from btc_quant_agent.h40 import (
    H40GuardError,
    H40LifecycleArtifactStore,
    H40LifecycleAuthorityService,
    H40ReasonCode,
    H40SyntheticAuthorityResolver,
    H40SyntheticEvidenceVerifier,
)
from btc_quant_agent.research_contract.canonical import canonical_json


def _make_resolvers(chain: Any) -> tuple[H40LifecycleAuthorityService, H40SyntheticAuthorityResolver]:
    fresh_service = H40LifecycleAuthorityService.synthetic_for_tests(
        chain.authority,
        H40SyntheticEvidenceVerifier(chain.verifier.export_payloads_for_tests()),
    )
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(chain.authority,),
        run_authorities=(chain.run,),
        runtime_seals=(chain.seal,),
    )
    return fresh_service, resolver


# =============================================================================
# RG-B02-01: Lineage Verification Before Membership (R53 - R56)
# =============================================================================


def test_r53_corrupted_committed_head_upstream_link_cannot_admit_orphan(tmp_path: Path) -> None:
    """R53: Corrupted committed HEAD receipt upstream link cannot admit a valid orphan into lineage."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    # 1. Commit D (Discovery)
    store.persist_authorization("01_discovery", chain.discovery, service=chain.service)
    # 2. Commit C (CandidateLock)
    store.persist_authorization("02_candidate_lock", chain.candidate, service=chain.service)

    head = store.get_committed_run_head(run_id)
    assert head is not None
    assert head.head_receipt_hash == chain.candidate.receipt_hash

    # 3. Create a valid orphan authorization T from D (e.g. termination from D)
    orphan_auth = chain.service.authorize_termination(
        prior_authority=chain.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.NOT_TESTABLE,
        detail_message="orphan termination",
        terminated_at_utc=TS,
    )
    # Publish orphan T receipt file to disk WITHOUT committing it to SQLite
    _publish_mock_envelope(store, orphan_auth.receipt)

    fresh_service, resolver = _make_resolvers(chain)

    # 4. Verify T restore is rejected before tampering
    with pytest.raises(H40GuardError, match="not in committed run head lineage"):
        store.restore_authorization(
            run_id,
            orphan_auth.receipt_hash,
            service=fresh_service,
            resolver=resolver,
        )

    # 5. Tamper with on-disk C's upstream_receipt_hash to point to T (without recomputing C's hash)
    c_path = store._receipts_dir(run_id) / f"{chain.candidate.receipt_hash}.json"
    envelope = json.loads(c_path.read_text(encoding="utf-8"))
    envelope["receipt"]["upstream_receipt_hash"] = orphan_auth.receipt_hash
    # Write tampered envelope (content hash is now mismatched)
    c_path.write_text(canonical_json(envelope) + "\n", encoding="utf-8")

    # 6. Request T restore: MUST fail closed
    with pytest.raises(H40GuardError, match="content hash mismatch"):
        store.restore_authorization(
            run_id,
            orphan_auth.receipt_hash,
            service=fresh_service,
            resolver=resolver,
        )

    # 7. Durable head remains unchanged in SQLite
    current_head = store.get_committed_run_head(run_id)
    assert current_head is not None
    assert current_head.head_receipt_hash == chain.candidate.receipt_hash


def test_r54_corrupted_non_head_committed_lineage_link_fails_closed(tmp_path: Path) -> None:
    """R54: Corrupted NON-HEAD committed lineage link fails closed for all restores."""
    wf_chain = _build_wf_chain()
    disc_chain = wf_chain.discovery_chain
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = disc_chain.run.run_authority_id

    # Commit 3 levels: D -> C -> W
    store.persist_authorization("01_discovery", disc_chain.discovery, service=disc_chain.service)
    store.persist_authorization("02_candidate_lock", disc_chain.candidate, service=disc_chain.service)
    store.persist_authorization("03_wf_validation", wf_chain.wf, service=disc_chain.service)

    head = store.get_committed_run_head(run_id)
    assert head is not None
    assert head.head_receipt_hash == wf_chain.wf.receipt_hash

    # Tamper with non-head receipt C on disk (level 1 between head W and genesis D)
    c_path = store._receipts_dir(run_id) / f"{disc_chain.candidate.receipt_hash}.json"
    envelope = json.loads(c_path.read_text(encoding="utf-8"))
    envelope["receipt"]["discovery_authorization_receipt_hash"] = "f" * 64
    envelope["receipt"]["upstream_receipt_hash"] = "f" * 64
    c_path.write_text(canonical_json(envelope) + "\n", encoding="utf-8")

    fresh_service = H40LifecycleAuthorityService.synthetic_for_tests(
        disc_chain.authority,
        H40SyntheticEvidenceVerifier(disc_chain.verifier.export_payloads_for_tests()),
    )
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(disc_chain.authority,),
        run_authorities=(disc_chain.run,),
        runtime_seals=(disc_chain.seal,),
    )

    # Restoring legitimate genesis D must fail closed because lineage from head W is corrupted
    with pytest.raises(H40GuardError, match="content hash mismatch"):
        store.restore_authorization(
            run_id,
            disc_chain.discovery.receipt_hash,
            service=fresh_service,
            resolver=resolver,
        )

    # Restoring head W itself must also fail closed because its lineage is corrupted
    with pytest.raises(H40GuardError, match="content hash mismatch"):
        store.restore_authorization(
            run_id,
            wf_chain.wf.receipt_hash,
            service=fresh_service,
            resolver=resolver,
        )


def test_r55_requesting_corrupted_committed_receipt_itself_fails_closed(tmp_path: Path) -> None:
    """R55: Requesting a corrupted committed receipt itself fails closed."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    store.persist_authorization("01_discovery", chain.discovery, service=chain.service)
    store.persist_authorization("02_candidate_lock", chain.candidate, service=chain.service)

    # Corrupt C directly
    c_path = store._receipts_dir(run_id) / f"{chain.candidate.receipt_hash}.json"
    c_path.write_text("{\"invalid\": json}", encoding="utf-8")

    fresh_service, resolver = _make_resolvers(chain)
    with pytest.raises(H40GuardError, match="failed to read lineage receipt"):
        store.restore_authorization(
            run_id,
            chain.candidate.receipt_hash,
            service=fresh_service,
            resolver=resolver,
        )


def test_r56_intact_committed_head_and_legitimate_ancestors_succeed(tmp_path: Path) -> None:
    """R56: Intact committed head and legitimate ancestor restores still succeed."""
    wf_chain = _build_wf_chain()
    disc_chain = wf_chain.discovery_chain
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = disc_chain.run.run_authority_id

    # Commit 4 levels: D -> C -> W -> CR
    conf_ready = disc_chain.service.authorize_confirmation_ready(
        wf_authority=wf_chain.wf,
        prepared_at_utc=TS,
    )
    store.persist_authorization("01_discovery", disc_chain.discovery, service=disc_chain.service)
    store.persist_authorization("02_candidate_lock", disc_chain.candidate, service=disc_chain.service)
    store.persist_authorization("03_wf_validation", wf_chain.wf, service=disc_chain.service)
    store.persist_authorization("04_confirmation_ready", conf_ready, service=disc_chain.service)

    fresh_service = H40LifecycleAuthorityService.synthetic_for_tests(
        disc_chain.authority,
        H40SyntheticEvidenceVerifier(disc_chain.verifier.export_payloads_for_tests()),
    )
    resolver = H40SyntheticAuthorityResolver.for_tests(
        implementation_authorities=(disc_chain.authority,),
        run_authorities=(disc_chain.run,),
        runtime_seals=(disc_chain.seal,),
        split_authorities=(wf_chain.split,),
    )

    # Restore head CR
    r_cr = store.restore_authorization(
        run_id,
        conf_ready.receipt_hash,
        service=fresh_service,
        resolver=resolver,
    )
    assert r_cr.receipt_hash == conf_ready.receipt_hash

    # Restore ancestor W
    r_w = store.restore_authorization(
        run_id,
        wf_chain.wf.receipt_hash,
        service=fresh_service,
        resolver=resolver,
    )
    assert r_w.receipt_hash == wf_chain.wf.receipt_hash

    # Restore ancestor C
    r_c = store.restore_authorization(
        run_id,
        disc_chain.candidate.receipt_hash,
        service=fresh_service,
        resolver=resolver,
    )
    assert r_c.receipt_hash == disc_chain.candidate.receipt_hash

    # Restore ancestor D
    r_d = store.restore_authorization(
        run_id,
        disc_chain.discovery.receipt_hash,
        service=fresh_service,
        resolver=resolver,
    )
    assert r_d.receipt_hash == disc_chain.discovery.receipt_hash


# =============================================================================
# RG-H01-01: Receipt Durability on Every Path (R57 - R61)
# =============================================================================


def test_r57_initial_receipt_dir_fsync_failure_leaves_head_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R57: Initial authoritative receipt-directory fsync failure leaves durable head unchanged."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    orig_fsync_dir = lifecycle_authority_module._fsync_dir

    def inject_fail(dir_path: Path, *, fail_closed: bool = False) -> None:
        if fail_closed and "receipts" in str(dir_path):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "injected initial receipt directory fsync failure",
            )
        orig_fsync_dir(dir_path, fail_closed=fail_closed)

    monkeypatch.setattr(lifecycle_authority_module, "_fsync_dir", inject_fail)

    with pytest.raises(H40GuardError, match="injected initial receipt directory fsync failure"):
        store.persist_authorization("01_discovery", chain.discovery, service=chain.service)

    # Receipt file was linked, but durable head must NOT be committed
    receipt_path = store._receipts_dir(run_id) / f"{chain.discovery.receipt_hash}.json"
    assert receipt_path.is_file()
    assert store.get_committed_run_head(run_id) is None


def test_r58_retry_while_receipt_dir_fsync_continues_failing_leaves_head_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R58: Retry while authoritative receipt-directory fsync continues failing leaves head unchanged."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    orig_fsync_dir = lifecycle_authority_module._fsync_dir

    def inject_fail(dir_path: Path, *, fail_closed: bool = False) -> None:
        if fail_closed and "receipts" in str(dir_path):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "injected continuous receipt directory fsync failure",
            )
        orig_fsync_dir(dir_path, fail_closed=fail_closed)

    monkeypatch.setattr(lifecycle_authority_module, "_fsync_dir", inject_fail)

    # Initial attempt fails at fsync
    with pytest.raises(H40GuardError, match="injected continuous receipt directory fsync failure"):
        store.persist_authorization("01_discovery", chain.discovery, service=chain.service)

    assert store.get_committed_run_head(run_id) is None

    # Retry when receipt already exists: MUST STILL execute fsync and fail closed!
    with pytest.raises(H40GuardError, match="injected continuous receipt directory fsync failure"):
        store.persist_authorization("01_discovery", chain.discovery, service=chain.service)

    # Durable head remains None
    assert store.get_committed_run_head(run_id) is None


def test_r59_retry_after_receipt_dir_fsync_recovers_commits_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R59: Retry after authoritative receipt-directory fsync recovers may commit exactly once."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    orig_fsync_dir = lifecycle_authority_module._fsync_dir
    fail_fsync = True

    def inject_fsync(dir_path: Path, *, fail_closed: bool = False) -> None:
        if fail_fsync and fail_closed and "receipts" in str(dir_path):
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "injected temporary fsync failure",
            )
        orig_fsync_dir(dir_path, fail_closed=fail_closed)

    monkeypatch.setattr(lifecycle_authority_module, "_fsync_dir", inject_fsync)

    # Initial attempt fails
    with pytest.raises(H40GuardError, match="injected temporary fsync failure"):
        store.persist_authorization("01_discovery", chain.discovery, service=chain.service)
    assert store.get_committed_run_head(run_id) is None

    # Fsync recovers
    fail_fsync = False
    p1 = store.persist_authorization("01_discovery", chain.discovery, service=chain.service)
    assert p1.exists()

    committed = store.get_committed_run_head(run_id)
    assert committed is not None
    assert committed.head_receipt_hash == chain.discovery.receipt_hash
    assert committed.transition_sequence == 0

    # Idempotent retry succeeds
    p2 = store.persist_authorization("01_discovery", chain.discovery, service=chain.service)
    assert p2 == p1
    recommitted = store.get_committed_run_head(run_id)
    assert recommitted == committed


def test_r60_concurrent_identical_publishers_require_directory_durability(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """R60: Concurrent identical publisher observing existing receipt cannot commit before its fsync succeeds."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    # Simulate Publisher A pre-linking the exact receipt file, but stopping before dir fsync
    receipts_dir = store._receipts_dir(run_id)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    final_path = receipts_dir / f"{chain.discovery.receipt_hash}.json"
    envelope = store._envelope(chain.discovery)
    encoded = (canonical_json(envelope) + "\n").encode("utf-8")
    final_path.write_bytes(encoded)

    assert store.get_committed_run_head(run_id) is None

    orig_fsync_dir = lifecycle_authority_module._fsync_dir
    fsync_called = False

    def check_fsync(dir_path: Path, *, fail_closed: bool = False) -> None:
        nonlocal fsync_called
        if "receipts" in str(dir_path):
            fsync_called = True
            # Simulate failure during publisher B's fsync
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT,
                "publisher B fsync interrupted",
            )
        orig_fsync_dir(dir_path, fail_closed=fail_closed)

    monkeypatch.setattr(lifecycle_authority_module, "_fsync_dir", check_fsync)

    # Publisher B attempts persist on the existing receipt: MUST call fsync and fail closed!
    with pytest.raises(H40GuardError, match="publisher B fsync interrupted"):
        store.persist_authorization("01_discovery", chain.discovery, service=chain.service)

    assert fsync_called is True
    # Head must NOT have been committed by Publisher B
    assert store.get_committed_run_head(run_id) is None


def test_r61_different_byte_existing_receipt_fails_closed(tmp_path: Path) -> None:
    """R61: Different-byte existing receipt remains rejected and cannot be overwritten."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    receipts_dir = store._receipts_dir(run_id)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    final_path = receipts_dir / f"{chain.discovery.receipt_hash}.json"
    final_path.write_bytes(b"different content bytes\n")

    with pytest.raises(H40GuardError, match="write-once immutable lifecycle receipt already exists with different bytes"):
        store.persist_authorization("01_discovery", chain.discovery, service=chain.service)

    # File was not overwritten
    assert final_path.read_bytes() == b"different content bytes\n"
    assert store.get_committed_run_head(run_id) is None


# =============================================================================
# Regression: Invariants Unchanged (R62)
# =============================================================================


def test_r62_sibling_cas_terminal_and_sequence_invariants_unchanged(tmp_path: Path) -> None:
    """R62: Regression proof of unchanged sibling CAS, terminal absorption, sequence +1, and genesis rules."""
    chain = _build_discovery_chain()
    store = H40LifecycleArtifactStore(tmp_path)
    run_id = chain.run.run_authority_id

    # 1. Commit genesis (sequence 0)
    store.persist_authorization("01_discovery", chain.discovery, service=chain.service)
    h0 = store.get_committed_run_head(run_id)
    assert h0 is not None
    assert h0.transition_sequence == 0
    assert h0.head_state == "H40_DISCOVERY"

    # 2. Commit candidate lock (sequence 1)
    store.persist_authorization("02_candidate_lock", chain.candidate, service=chain.service)
    h1 = store.get_committed_run_head(run_id)
    assert h1 is not None
    assert h1.transition_sequence == 1
    assert h1.head_state == "H40_CANDIDATE_LOCKED"

    # 3. Sibling CAS conflict: create sibling termination from discovery
    # A second transition attempting to branch from genesis D must be rejected
    sibling_term = chain.service.authorize_termination(
        prior_authority=chain.discovery,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.NOT_TESTABLE,
        detail_message="sibling termination",
        terminated_at_utc=TS,
    )
    # Predecessor mismatch against current head (which is now C)
    with pytest.raises(H40GuardError, match="predecessor receipt hash mismatch"):
        store.persist_authorization("02_sibling", sibling_term, service=chain.service)

    # Head remains h1
    assert store.get_committed_run_head(run_id) == h1

    # 4. Terminal absorption: terminate from C
    term_auth = chain.service.authorize_termination(
        prior_authority=chain.candidate,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.NOT_TESTABLE,
        detail_message="terminal absorption test",
        terminated_at_utc=TS,
    )
    store.persist_authorization("03_termination", term_auth, service=chain.service)
    h2 = store.get_committed_run_head(run_id)
    assert h2 is not None
    assert h2.terminal is True
    assert h2.transition_sequence == 2

    # Attempting any transition after terminal state must fail closed
    post_term = chain.service.authorize_termination(
        prior_authority=chain.candidate,
        target_state="H40_NO_GO",
        reason_code=H40ReasonCode.THRESHOLD_UNMET,
        detail_message="post-terminal attempt",
        terminated_at_utc="2026-09-20T00:02:00Z",
    )
    with pytest.raises(H40GuardError, match="is in terminal state"):
        store.persist_authorization("04_post_terminal", post_term, service=chain.service)
