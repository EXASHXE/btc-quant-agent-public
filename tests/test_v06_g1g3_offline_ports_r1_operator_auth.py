"""32 deterministic tests for AuthenticatedHumanPort (Ed25519 operator authority & trust translation)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts.g1_offline_preview_r1.fixtures import bar as g1_bar
from scripts.g1_offline_preview_r1.model import SafetyViolation, digest, initial_state
from scripts.g1_offline_preview_r1.reducer import transition
from scripts.g1g3_offline_ports_r1.authenticated_human_port import (
    APPROVAL_CLASS,
    DEFAULT_ROUTE_ID,
    DEFAULT_WORKTREE_ID,
    REJECTION_CLASS,
    AuthenticatedHumanPort,
    compute_operator_context_hash,
    sign_synthetic_operator_decision,
)
from scripts.g1g3_offline_ports_r1.crypto_ed25519 import SYNTHETIC_TEST_OPERATOR_SEEDS


def _sample_context(
    *,
    side: str = "LONG",
    qty: str = "0.01",
    worktree_id: str = DEFAULT_WORKTREE_ID,
    route_id: str = DEFAULT_ROUTE_ID,
    process_epoch: int = 1,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], str]:
    b = g1_bar(0, side=side)
    sign = 1 if side == "LONG" else -1
    prop = {
        "schema_version": 1,
        "signal_id": f"sig-{side.lower()}-1",
        "source_hash": digest(b),
        "source_close_at": 59999,
        "decision_at": 60000,
        "side": side,
        "quantity": qty,
        "stop": str(30000 - sign * 300),
        "tp1": str(30000 + sign * 300),
        "tp2": str(30000 + sign * 600),
        "horizon_hours": 24,
        "exit_identity": "OFFLINE_TP1_BE_TIME_CAP_V1",
        "expires_at": 180000,
        "version": 1,
    }
    analysis = {
        "schema_version": 1,
        "signal_id": prop["signal_id"],
        "proposal_hash": digest(prop),
        "source_hash": digest(b),
        "as_of": 60000,
        "summary": "Bounded descriptive risk note; no order authority",
        "risk": "DESCRIPTIVE_ONLY",
    }
    ctx_hash = compute_operator_context_hash(
        source_hash=prop["source_hash"],
        proposal_hash=digest(prop),
        analysis_hash=digest(analysis),
        worktree_id=worktree_id,
        route_id=route_id,
        process_epoch=process_epoch,
    )
    return b, prop, analysis, ctx_hash


def _valid_decision(
    prop: dict[str, Any],
    ctx_hash: str,
    *,
    token_id: str = "tok-alpha-1",
    nonce: str = "nonce-alpha-001",
    operator_id: str = "op-alpha",
    key_id: str = "ed25519-offline-op-alpha-v1",
    issued_at: int = 60002,
    expires_at: int = 160000,
    environment: str = "OFFLINE_PREVIEW",
    decision_class: str = APPROVAL_CLASS,
    seed_override: bytes | None = None,
) -> dict[str, Any]:
    return sign_synthetic_operator_decision(
        token_id=token_id,
        signal_id=prop["signal_id"],
        proposal_hash=digest(prop),
        version=prop["version"],
        side=prop["side"],
        quantity=prop["quantity"],
        issued_at=issued_at,
        expires_at=expires_at,
        operator_id=operator_id,
        key_id=key_id,
        environment=environment,
        context_hash=ctx_hash,
        approval_nonce=nonce,
        decision_class=decision_class,
        seed_override=seed_override,
    )


def test_01_valid_operator_alpha_signature_verifies_and_translates(tmp_path: Path) -> None:
    b, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash)
    receipt = port.verify_decision(
        decision,
        proposal=prop,
        analysis=analysis,
        analysis_at=60001,
        approve_at=60002,
    )
    assert receipt["approved"] is True
    assert receipt["operator_id"] == "op-alpha"
    assert receipt["key_id"] == "ed25519-offline-op-alpha-v1"
    assert receipt["translated_g1_token"]["issuer"] == "TRUSTED_HUMAN_FIXTURE"
    assert receipt["translated_g1_token"]["proposal_hash"] == digest(prop)
    # Materialize sealed fixture and run G1 pure reducer through APPROVE -> PLACE
    untrusted = {"schema_version": 1, "trusted_approvals": [], "events": []}
    sealed, sealed_path, seal_manifest = port.materialize_sealed_fixture(untrusted, receipt)
    assert (sealed_path.stat().st_mode & 0o777) == 0o400
    assert seal_manifest["production_identity_control"] is False
    s = initial_state(sealed["trusted_approvals"])
    s = transition(s, {"id": "BAR-0", "kind": "BAR", "at": 59999, "payload": b})
    s = transition(s, {"id": "PROPOSE-60000", "kind": "PROPOSE", "at": 60000, "payload": prop})
    s = transition(s, {"id": "ANALYZE-60001", "kind": "ANALYZE", "at": 60001, "payload": analysis})
    s = transition(
        s,
        {"id": "APPROVE-60002", "kind": "APPROVE", "at": 60002, "payload": {"token_id": "tok-alpha-1"}},
    )
    s = transition(s, {"id": "PLACE-60003", "kind": "PLACE", "at": 60003, "payload": {}})
    assert s["phase"] == "PLACED"


def test_02_multiple_operators_valid_beta_operator(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context(side="SHORT", qty="0.02")
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(
        prop,
        ctx_hash,
        token_id="tok-beta-1",
        nonce="nonce-beta-001",
        operator_id="op-beta",
        key_id="ed25519-offline-op-beta-v1",
    )
    receipt = port.verify_decision(
        decision,
        proposal=prop,
        analysis=analysis,
        analysis_at=60001,
        approve_at=60002,
    )
    assert receipt["approved"] is True
    assert receipt["operator_id"] == "op-beta"
    assert receipt["side"] == "SHORT"
    assert receipt["quantity"] == "0.02"


def test_03_forged_signature_bit_flip_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash)
    sig_bytes = bytearray.fromhex(decision["signature"])
    sig_bytes[0] ^= 0x01
    decision["signature"] = bytes(sig_bytes).hex()
    with pytest.raises(SafetyViolation, match="APPROVAL_SIGNATURE_INVALID"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_04_wrong_private_seed_for_pinned_key_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(
        prop,
        ctx_hash,
        operator_id="op-alpha",
        key_id="ed25519-offline-op-alpha-v1",
        seed_override=SYNTHETIC_TEST_OPERATOR_SEEDS["ed25519-offline-op-beta-v1"],
    )
    with pytest.raises(SafetyViolation, match="APPROVAL_SIGNATURE_INVALID"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_05_unknown_key_id_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash)
    decision["key_id"] = "ed25519-untrusted-key-v99"
    with pytest.raises(SafetyViolation, match="APPROVAL_KEY_UNTRUSTED"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_06_revoked_key_id_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(
        prop,
        ctx_hash,
        operator_id="op-revoked",
        key_id="ed25519-offline-op-revoked-v1",
    )
    with pytest.raises(SafetyViolation, match="APPROVAL_KEY_REVOKED"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_07_operator_id_key_id_mismatch_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(
        prop,
        ctx_hash,
        operator_id="op-beta",
        key_id="ed25519-offline-op-alpha-v1",
    )
    with pytest.raises(SafetyViolation, match="APPROVAL_OPERATOR_KEY_MISMATCH"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_08_one_use_nonce_replay_in_same_process_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    d1 = _valid_decision(prop, ctx_hash, token_id="tok-1", nonce="nonce-unique-1")
    port.verify_decision(d1, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002)
    d2 = _valid_decision(prop, ctx_hash, token_id="tok-2", nonce="nonce-unique-1")
    with pytest.raises(SafetyViolation, match="APPROVAL_NONCE_REPLAYED"):
        port.verify_decision(
            d2, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60003
        )


def test_09_nonce_replay_after_process_restart_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port1 = AuthenticatedHumanPort(tmp_path, temporary=True)
    d1 = _valid_decision(prop, ctx_hash, token_id="tok-1", nonce="nonce-persisted-1")
    port1.verify_decision(d1, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002)

    # Simulate fresh process restart on same durable storage directory
    port2 = AuthenticatedHumanPort(tmp_path, temporary=True)
    _, prop2, analysis2, ctx_hash2 = _sample_context(side="SHORT")
    d2 = _valid_decision(prop2, ctx_hash2, token_id="tok-2", nonce="nonce-persisted-1")
    with pytest.raises(SafetyViolation, match="APPROVAL_NONCE_REPLAYED"):
        port2.verify_decision(
            d2, proposal=prop2, analysis=analysis2, analysis_at=60001, approve_at=60002
        )


def test_10_cross_worktree_decision_rejected(tmp_path: Path) -> None:
    _, prop, analysis, foreign_ctx_hash = _sample_context(worktree_id="other-agent-worktree")
    port = AuthenticatedHumanPort(tmp_path, worktree_id=DEFAULT_WORKTREE_ID, temporary=True)
    decision = _valid_decision(prop, foreign_ctx_hash)
    with pytest.raises(SafetyViolation, match="APPROVAL_CONTEXT_HASH_MISMATCH"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_11_explicit_cross_worktree_parameter_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, worktree_id=DEFAULT_WORKTREE_ID, temporary=True)
    decision = _valid_decision(prop, ctx_hash)
    with pytest.raises(SafetyViolation, match="APPROVAL_ROUTE_OR_WORKTREE_MISMATCH"):
        port.verify_decision(
            decision,
            proposal=prop,
            analysis=analysis,
            analysis_at=60001,
            approve_at=60002,
            decision_worktree_id="gemini-forward-public-feed-r1",
        )


def test_12_approval_after_route_rebind_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context(route_id="route-initial-v1")
    port = AuthenticatedHumanPort(tmp_path, route_id="route-initial-v1", temporary=True)
    decision = _valid_decision(prop, ctx_hash)
    # Route rebinds after operator signed for route-initial-v1
    port.rebind_route("route-rebound-v2")
    with pytest.raises(SafetyViolation, match="APPROVAL_CONTEXT_HASH_MISMATCH"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_13_tampered_quantity_post_signing_fails_signature(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context(qty="0.01")
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash)
    decision["quantity"] = "0.02"
    with pytest.raises(SafetyViolation, match="APPROVAL_SIGNATURE_INVALID"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_14_signed_quantity_mismatch_against_proposal_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context(qty="0.01")
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = sign_synthetic_operator_decision(
        token_id="tok-qty-drift",
        signal_id=prop["signal_id"],
        proposal_hash=digest(prop),
        version=1,
        side=prop["side"],
        quantity="0.02",
        issued_at=60002,
        expires_at=160000,
        operator_id="op-alpha",
        key_id="ed25519-offline-op-alpha-v1",
        context_hash=ctx_hash,
        approval_nonce="nonce-qty-drift",
    )
    with pytest.raises(SafetyViolation, match="APPROVAL_PROPOSAL_DRIFT"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_15_signed_side_mismatch_against_proposal_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context(side="LONG")
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = sign_synthetic_operator_decision(
        token_id="tok-side-drift",
        signal_id=prop["signal_id"],
        proposal_hash=digest(prop),
        version=1,
        side="SHORT",
        quantity=prop["quantity"],
        issued_at=60002,
        expires_at=160000,
        operator_id="op-alpha",
        key_id="ed25519-offline-op-alpha-v1",
        context_hash=ctx_hash,
        approval_nonce="nonce-side-drift",
    )
    with pytest.raises(SafetyViolation, match="APPROVAL_PROPOSAL_DRIFT"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_16_token_expiry_at_or_after_expires_at_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash, issued_at=60002, expires_at=100000)
    with pytest.raises(SafetyViolation, match="APPROVAL_CLOCK_OR_EXPIRY_INVALID"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=100000
        )


def test_17_proposal_expiry_exceeded_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash, issued_at=60002, expires_at=200000)
    with pytest.raises(SafetyViolation, match="APPROVAL_CLOCK_OR_EXPIRY_INVALID"):
        port.verify_decision(
            decision,
            proposal=prop,
            analysis=analysis,
            analysis_at=60001,
            approve_at=prop["expires_at"],
        )


def test_18_stale_clock_issued_before_analysis_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash, issued_at=60000, expires_at=160000)
    with pytest.raises(SafetyViolation, match="APPROVAL_CLOCK_OR_EXPIRY_INVALID"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_19_approve_at_before_issued_at_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash, issued_at=60005, expires_at=160000)
    with pytest.raises(SafetyViolation, match="APPROVAL_CLOCK_OR_EXPIRY_INVALID"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60004
        )


@pytest.mark.parametrize("bad_env", ["LIVE", "TESTNET", "PRODUCTION", "UNKNOWN_ENV"])
def test_20_to_23_wrong_environment_rejected(tmp_path: Path, bad_env: str) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash, environment=bad_env)
    with pytest.raises(SafetyViolation, match="APPROVAL_ENVIRONMENT_INVALID"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_24_prior_process_sequence_epoch_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash_epoch1 = _sample_context(process_epoch=1)
    port = AuthenticatedHumanPort(tmp_path, process_epoch=1, temporary=True)
    decision = _valid_decision(prop, ctx_hash_epoch1)
    port.advance_process_epoch(2)
    with pytest.raises(SafetyViolation, match="APPROVAL_PRIOR_PROCESS_SEQUENCE"):
        port.verify_decision(
            decision,
            proposal=prop,
            analysis=analysis,
            analysis_at=60001,
            approve_at=60002,
            decision_epoch=1,
        )


def test_25_wrong_model_output_failed_analysis_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash)
    failed_analysis = {**analysis, "status": "NO_ACTION_OR_MANUAL_REVIEW"}
    with pytest.raises(SafetyViolation, match="APPROVAL_MODEL_OUTPUT_INVALID"):
        port.verify_decision(
            decision,
            proposal=prop,
            analysis=failed_analysis,
            analysis_at=60001,
            approve_at=60002,
        )


def test_26_wrong_model_output_summary_tampered_after_context_hash_rejected(
    tmp_path: Path,
) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash)
    drifted_analysis = {**analysis, "summary": "Different summary not bound by operator signature"}
    with pytest.raises(SafetyViolation, match="APPROVAL_CONTEXT_HASH_MISMATCH"):
        port.verify_decision(
            decision,
            proposal=prop,
            analysis=drifted_analysis,
            analysis_at=60001,
            approve_at=60002,
        )


def test_27_no_automatic_approval_after_positive_model_output(tmp_path: Path) -> None:
    _, prop, analysis, _ = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    with pytest.raises(SafetyViolation, match="APPROVAL_MISSING_EXPLICIT_HUMAN_SIGNATURE"):
        port.verify_decision(
            None, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_28_raw_trusted_human_fixture_rejected_at_adapter_boundary(tmp_path: Path) -> None:
    _, prop, analysis, _ = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    raw_token = {
        "token_id": "synthetic-explicit-human-long",
        "signal_id": prop["signal_id"],
        "proposal_hash": digest(prop),
        "proposal_version": 1,
        "quantity": "0.01",
        "issued_at": 60002,
        "expires_at": 160000,
        "approved": True,
        "issuer": "TRUSTED_HUMAN_FIXTURE",
    }
    with pytest.raises(SafetyViolation, match="RAW_FIXTURE_TRUST_REJECTED"):
        port.verify_decision(
            raw_token, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )
    with pytest.raises(SafetyViolation, match="RAW_FIXTURE_TRUST_REJECTED"):
        port.reject_unauthenticated_fixture({"trusted_approvals": [raw_token]})


def test_29_explicit_operator_rejection_class_never_materializes_approval(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash, decision_class=REJECTION_CLASS)
    receipt = port.verify_decision(
        decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
    )
    assert receipt["approved"] is False
    assert receipt["translated_g1_token"] is None
    with pytest.raises(SafetyViolation, match="OPERATOR_DECISION_NOT_APPROVED"):
        port.materialize_sealed_fixture({"schema_version": 1, "trusted_approvals": []}, receipt)


def test_30_proposal_version_or_signal_id_drift_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    bad_version_decision = sign_synthetic_operator_decision(
        token_id="tok-v2",
        signal_id=prop["signal_id"],
        proposal_hash=digest(prop),
        version=2,
        side=prop["side"],
        quantity=prop["quantity"],
        issued_at=60002,
        expires_at=160000,
        operator_id="op-alpha",
        key_id="ed25519-offline-op-alpha-v1",
        context_hash=ctx_hash,
        approval_nonce="nonce-v2",
    )
    with pytest.raises(SafetyViolation, match="APPROVAL_PROPOSAL_DRIFT"):
        port.verify_decision(
            bad_version_decision,
            proposal=prop,
            analysis=analysis,
            analysis_at=60001,
            approve_at=60002,
        )


def test_31_secret_in_operator_fields_rejected(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    decision = _valid_decision(prop, ctx_hash, nonce="api_key=LEAKED_SECRET")
    with pytest.raises(SafetyViolation, match="SECRET_IN_OPERATOR_DECISION"):
        port.verify_decision(
            decision, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )


def test_32_recover_or_verify_detects_tampered_replay_and_truncated_wal(tmp_path: Path) -> None:
    _, prop, analysis, ctx_hash = _sample_context()
    port = AuthenticatedHumanPort(tmp_path, temporary=True)
    d1 = _valid_decision(prop, ctx_hash, nonce="nonce-recover-1")
    r1 = port.recover_or_verify_decision(
        d1, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
    )
    # Exact same decision recovers idempotently
    r2 = port.recover_or_verify_decision(
        copy.deepcopy(d1), proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
    )
    assert r1 == r2
    # Mutated decision for same proposal fails closed
    d_mut = _valid_decision(prop, ctx_hash, token_id="tok-other", nonce="nonce-recover-2")
    with pytest.raises(SafetyViolation, match="SIDECAR_APPROVAL_REPLAY_MISMATCH"):
        port.recover_or_verify_decision(
            d_mut, proposal=prop, analysis=analysis, analysis_at=60001, approve_at=60002
        )
    # Truncate operator WAL and verify fail-closed on restart
    raw = port.wal_path.read_bytes()
    port.wal_path.write_bytes(raw[:-1])
    with pytest.raises(SafetyViolation, match="OPERATOR_WAL_TRUNCATED"):
        AuthenticatedHumanPort(tmp_path, temporary=True)
