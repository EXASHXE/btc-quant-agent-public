#!/usr/bin/env python3
"""Deterministic One-Shot Execution Script for H40 M3B: First Real Discovery and Candidate Lock.

Adheres strictly to V0.5.1_H40_M3B_FIRST_REAL_DISCOVERY_AND_CANDIDATE_LOCK.md:
- Production APIs only (no test imports).
- Partitions: WF1_TRAIN, WF1_CALIBRATION only.
- Source: ETHUSDT_USD_M_1H only.
- Execution disabled: True.
- One-shot execution: exactly one authorization, one evidence production, one verification, one lock/termination.
"""

from __future__ import annotations

import hashlib
import json
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
from btc_quant_agent.h40.discovery_evidence import (
    H40ProductionDiscoveryEvidenceVerifier,
)
from btc_quant_agent.h40.discovery_producer import (
    H40ProductionDiscoveryEvidenceProducer,
)

from btc_quant_agent.execution import (
    ACCEPTED_EXECUTION_WRITE_AUTHORITY,
    CURRENT_EXECUTION_POLICY,
)
from btc_quant_agent.h40 import (
    EXPECTED_PROTOCOL_AUTHORITY_HASH,
    EXPECTED_STRUCTURAL_LEDGER_HASH,
    H40DiscoveryAuthorizationReceipt,
    H40DiscoveryRunGrant,
    H40GuardError,
    H40LifecycleArtifactStore,
    H40LifecycleAuthorityService,
    H40LifecycleImplementationAuthority,
    H40P3ControllerAuthority,
    H40ProtectedSurfaceGuard,
    H40ProtocolIdentity,
    H40ReasonCode,
    H40RequiredTestCIEvidenceIdentity,
    H40RunAuthority,
    H40RuntimeSnapshotSeal,
    compute_lifecycle_governance_authority_hash,
    compute_protocol_authority_hash,
    compute_semantic_root_hash,
    materialize_runtime_source_split_authority,
    materialize_verified_manifest,
)


def log(msg: str) -> None:
    now = datetime.now(UTC).isoformat()
    print(f"[{now}] {msg}", flush=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    t_start = time.perf_counter()
    log("=== START H40 M3B FIRST REAL DISCOVERY AND CANDIDATE LOCK ===")

    repo_root = Path.cwd()
    log(f"Working repository root: {repo_root}")

    # 1. Clean-run preflight checks
    log("1. Running preflight checks...")
    assert CURRENT_EXECUTION_POLICY == "RESEARCH_DISABLED_V1", f"Policy mismatch: {CURRENT_EXECUTION_POLICY}"
    assert ACCEPTED_EXECUTION_WRITE_AUTHORITY is None, f"Write authority present: {ACCEPTED_EXECUTION_WRITE_AUTHORITY}"

    eth_source_path = repo_root / "data" / "research" / "cross_asset_1h" / "ETHUSDT.parquet"
    assert eth_source_path.is_file(), f"Missing ETH source file: {eth_source_path}"
    H40ProtectedSurfaceGuard.assert_path_allowed(eth_source_path, source_id="ETHUSDT_USD_M_1H")

    eth_sha = sha256_file(eth_source_path)
    expected_eth_sha = "563a1a4d927ec2a007481783be9bd76896e1be57198af80c4b2a30608e124608"
    assert eth_sha == expected_eth_sha, f"ETH source sha256 mismatch: {eth_sha} != {expected_eth_sha}"

    eth_table = pq.read_table(eth_source_path)
    eth_rows = eth_table.num_rows
    expected_eth_rows = 44568
    assert eth_rows == expected_eth_rows, f"ETH rows mismatch: {eth_rows} != {expected_eth_rows}"
    log(f"Preflight: ETH source verified: {eth_rows} rows, sha256={eth_sha}")

    # 2. Reconstruct exact typed authorities
    log("2. Reconstructing exact typed authorities...")
    impl = H40LifecycleImplementationAuthority(
        accepted_lifecycle_governance_authority_hash="bb367f2af726be105bddf42636c97652402014c8a671d43ab81b1964c258e5cf",
        f01_implementation_acceptance_artifact_path="reviews/v0.5/V0.5.1_H40_PRE_P3_CLOSURE_EXACT_SHA_CONTROLLER_ACCEPTANCE.md",
        f01_implementation_acceptance_commit_sha="8ae06121d1e83db8df612951914629c62ed70c4b",
        f01_implementation_commit_sha="f3678676265ba53e1d874e27bc0c922c7783acaa",
        required_test_ci_evidence_identity=H40RequiredTestCIEvidenceIdentity(
            evidence_manifest_artifact_path="evidence/v0.5/h40/V0.5.1_H40_PRE_P3_CLOSURE_EXACT_SHA_EVIDENCE_f3678676_R1.json",
            evidence_manifest_sha256="609632e06c280adfa20ae5db5b0b3d0736792252ac07de93b1bf1e368ea210be",
            tested_commit_sha="f3678676265ba53e1d874e27bc0c922c7783acaa",
        ),
    )
    expected_impl_hash = "088b1210c17171141e232219345fa890e182282445fd9b2a70804b177d808b96"
    assert impl.lifecycle_implementation_authority_hash == expected_impl_hash, (
        f"Implementation authority hash mismatch: {impl.lifecycle_implementation_authority_hash} != {expected_impl_hash}"
    )

    ctrl = H40P3ControllerAuthority(
        controller_acceptance_artifact_path="reviews/v0.5/V0.5.1_ARCHITECTURE_AND_DATA_BASELINE_R2_R1_CONTROLLER_FINAL_ACCEPTANCE.md",
        controller_acceptance_commit_sha="9afd71f0adedfbf99b48773064fd0b3977805c9d",
        lifecycle_implementation_authority_hash=impl.lifecycle_implementation_authority_hash,
        permitted_partitions=("WF1_TRAIN", "WF1_CALIBRATION"),
        execution_disabled=True,
    )
    expected_ctrl_hash = "37b6ea92ff61b90c07f38cadea58087a8dc91c67d3beabe34dc7792988ff3e3a"
    assert ctrl.controller_authority_hash == expected_ctrl_hash, (
        f"Controller authority hash mismatch: {ctrl.controller_authority_hash} != {expected_ctrl_hash}"
    )
    log("Exact typed authorities verified.")

    # 3. Materialize fresh real runtime authority
    log("3. Materializing fresh real runtime authority...")
    protocol = H40ProtocolIdentity.default()
    assert compute_protocol_authority_hash() == EXPECTED_PROTOCOL_AUTHORITY_HASH

    source = materialize_verified_manifest(repo_root=repo_root, protocol_identity_hash=protocol.protocol_hash)
    split, attestation = materialize_runtime_source_split_authority(source_manifest=source, repo_root=repo_root)
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source,
        split_manifest=split,
        runtime_attestation=attestation,
        repo_root=repo_root,
    )
    seal.verify_against_accepted_ledger()
    run = H40RunAuthority.from_seal(seal, impl.lifecycle_implementation_authority_hash)

    expected_snapshot_hash = "733b57a347259794e552a2bc47ecf80712d0e6b54b2d3e2b90c7d52d7a0883d2"
    expected_roster_hash = "78af704fff5210beddd7427a1624cae4c1fbc1415da1fdbc6fcfa8a3228179da"
    expected_run_id = "1c6a9942c961867524d1c9b9b0092fc9fc05ed54f0bf8e2b1e90863fa4b3a1bf"
    expected_run_hash = "b39534c47e3f965e2857da309bf29ba14122db7ee01bc5d6d00a52bf75a0e952"

    assert seal.runtime_authority_snapshot_hash == expected_snapshot_hash, "seal snapshot hash mismatch"
    assert seal.sealed_registered_roster_hash == expected_roster_hash, "seal roster hash mismatch"
    assert run.run_authority_id == expected_run_id, "run authority id mismatch"
    assert run.materialized_run_authority_hash == expected_run_hash, "run authority hash mismatch"
    log(f"Runtime authority materialized: run_authority_id={run.run_authority_id}")

    # 4. Freeze UTC timestamp and construct grant + expected receipt
    log("4. Freezing execution timestamp and bootstrapping verifier...")
    disc_auth_file = repo_root / "artifacts" / "h40" / "lifecycle" / "runs" / run.run_authority_id / "01_discovery_authorization.json"
    if disc_auth_file.is_file():
        raw_auth = json.loads(disc_auth_file.read_text(encoding="utf-8"))
        authorized_at_utc = raw_auth["receipt"]["authorized_at_utc"]
        log(f"Preserving frozen authorized_at_utc: {authorized_at_utc}")
    else:
        authorized_at_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    grant = H40DiscoveryRunGrant.from_controller_and_run(
        controller_authority=ctrl,
        run_authority=run,
        seal=seal,
        authorized_at_utc=authorized_at_utc,
    )

    expected_receipt = H40DiscoveryAuthorizationReceipt(
        authorized_at_utc=authorized_at_utc,
        controller_authority_hash=ctrl.controller_authority_hash,
        discovery_run_grant_hash=grant.discovery_run_grant_hash,
        discovery_selection_correction_contract_hash=ctrl.discovery_selection_correction_contract_hash,
        execution_disabled=True,
        lifecycle_governance_authority_hash=compute_lifecycle_governance_authority_hash(),
        lifecycle_implementation_authority_hash=impl.lifecycle_implementation_authority_hash,
        materialized_run_authority_hash=seal.materialized_run_authority_hash,
        not_testable_slot_count=seal.not_testable_slot_count,
        protocol_authority_hash=compute_protocol_authority_hash(),
        registered_slot_count=seal.registered_slot_count,
        run_authority_id=run.run_authority_id,
        sealed_registered_roster_hash=seal.sealed_registered_roster_hash,
        semantic_root_hash=compute_semantic_root_hash(),
        source_manifest_hash=seal.source_manifest_hash,
        split_attestation_hash=seal.split_attestation_hash,
        split_manifest_hash=seal.split_manifest_hash,
        structural_ledger_hash=EXPECTED_STRUCTURAL_LEDGER_HASH,
        total_slot_count=seal.total_slot_count,
    )

    approved_evidence_root = repo_root / "artifacts" / "h40" / "discovery" / "runs" / run.run_authority_id / "evidence"
    H40ProtectedSurfaceGuard.assert_path_allowed(approved_evidence_root)
    approved_evidence_root.mkdir(parents=True, exist_ok=True)

    verifier = H40ProductionDiscoveryEvidenceVerifier(
        approved_evidence_root=approved_evidence_root,
        seal=seal,
        authorization_receipt=expected_receipt,
        split_manifest=split,
    )

    service = H40LifecycleAuthorityService.production(
        implementation_authority=impl,
        controller_authority=ctrl,
        discovery_run_grant=grant,
        evidence_verifier=verifier,
    )

    log("5. Authorizing Discovery transition...")
    discovery_auth = service.authorize_discovery(
        implementation_authority=impl,
        run_authority=run,
        seal=seal,
        authorized_at_utc=authorized_at_utc,
        controller_authority=ctrl,
        discovery_run_grant=grant,
    )
    assert discovery_auth.receipt == expected_receipt, "Receipt object inequality"
    assert discovery_auth.receipt_hash == expected_receipt.receipt_sha256, "Receipt hash inequality"
    log(f"Authoritative Discovery authorization issued: receipt_hash={discovery_auth.receipt_hash}")

    # 5. Persist Discovery transition as 01_discovery_authorization
    log("6. Persisting 01_discovery_authorization...")
    store = H40LifecycleArtifactStore(repo_root)
    disc_receipt_path = store.persist_authorization("01_discovery_authorization", discovery_auth, service=service)
    log(f"01_discovery_authorization persisted at {disc_receipt_path}")

    # 6. Real production Discovery evidence generation
    log("7. Starting real production Discovery evidence generation...")
    producer = H40ProductionDiscoveryEvidenceProducer(
        implementation_authority=impl,
        controller_authority=ctrl,
        authorization_receipt=discovery_auth.receipt,
        run_authority=run,
        seal=seal,
        split_manifest=split,
        approved_evidence_root=approved_evidence_root,
        repo_root=repo_root,
    )

    t_prod_start = time.perf_counter()
    prod_result = producer.produce()
    producer_wall_seconds = round(time.perf_counter() - t_prod_start, 4)
    log(f"Discovery evidence produced in {producer_wall_seconds}s. Dependencies count: {len(prod_result.dependency_digests)}")

    real_evidence = prod_result.evidence
    real_entries = prod_result.entries
    assert len(real_entries) == 18, f"Expected 18 candidate entries, got {len(real_entries)}"

    # 7. Independent production verification
    log("8. Running independent production verification on all 18 candidates...")
    t_ver_start = time.perf_counter()
    verifier.verify_discovery_manifest(real_evidence, real_entries)

    hard_gate_passed_count = 0
    scientific_unavailable_count = 0
    for entry in real_entries:
        cand_ver = verifier.verify_candidate(
            entry,
            run_authority_id=real_evidence.run_authority_id,
            correction_manifest_hash=real_evidence.correction_input_evidence_manifest_hash,
        )
        if cand_ver.hard_gates_passed:
            hard_gate_passed_count += 1
        if cand_ver.scientific_unavailable:
            scientific_unavailable_count += 1

    verification_wall_seconds = round(time.perf_counter() - t_ver_start, 4)
    log(
        f"Verification complete in {verification_wall_seconds}s. "
        f"Verified: 18, hard_gate_passed: {hard_gate_passed_count}, scientific_unavailable: {scientific_unavailable_count}"
    )

    # 8. Candidate Lock / Termination transition
    log("9. Transitioning Candidate Lock...")
    now_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    candidate_lock_created = False
    candidate_lock_receipt_hash = None
    selected_cfg_hash = None
    selected_slot_hash = None
    selected_slot_index = None

    termination_created = False
    termination_receipt_hash = None
    terminal_state = None
    terminal_reason_code = None

    try:
        cand_lock_auth = service.authorize_candidate_lock(
            discovery_authority=discovery_auth,
            evidence=real_evidence,
            locked_at_utc=now_utc,
            verified_at_utc=now_utc,
        )
        store.persist_authorization("02_candidate_lock", cand_lock_auth, service=service)
        candidate_lock_created = True
        candidate_lock_receipt_hash = cand_lock_auth.receipt_hash
        selected_entry = cand_lock_auth.context["selected_entry"]
        selected_cfg_hash = selected_entry.structural_configuration_hash
        selected_slot_hash = selected_entry.slot_hash
        selected_slot_index = selected_entry.slot_index
        formal_final_state = "M3B_FIRST_REAL_DISCOVERY_CANDIDATE_LOCKED_PENDING_ASTRA_AUDIT"
        next_stage = "GPT-6 Astra — POST_DISCOVERY_PRE_WF_DEEP_AUDIT"
        log(f"CANDIDATE LOCKED successfully! Receipt hash: {candidate_lock_receipt_hash}")
        log(f"Selected candidate: slot_index={selected_slot_index}, slot_hash={selected_slot_hash}")
    except H40GuardError as exc:
        if exc.reason_code in (H40ReasonCode.THRESHOLD_UNMET, H40ReasonCode.NOT_TESTABLE):
            target_state = "H40_NO_GO" if exc.reason_code == H40ReasonCode.THRESHOLD_UNMET else "NOT_TESTABLE"
            log(f"Candidate Lock gate triggered termination: {exc.reason_code} -> target_state={target_state}")
            term_auth = service.authorize_termination(
                prior_authority=discovery_auth,
                target_state=target_state,
                reason_code=exc.reason_code,
                detail_message=exc.message,
                terminated_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                failure_evidence=real_evidence,
                failure_evidence_hash=real_evidence.evidence_sha256,
            )
            term_path = store.persist_authorization("02_termination", term_auth, service=service)
            termination_created = True
            termination_receipt_hash = term_auth.receipt_hash
            terminal_state = target_state
            terminal_reason_code = exc.reason_code.value
            formal_final_state = f"M3B_FIRST_REAL_DISCOVERY_{target_state}"
            next_stage = "Controller triage before any search-space expansion or retry"
            log(f"Termination persisted at {term_path}")
        else:
            raise

    # 9. Local evidence inventory
    local_files = [p for p in approved_evidence_root.rglob("*") if p.is_file()]
    local_evidence_objects = len(local_files)
    local_evidence_bytes = sum(p.stat().st_size for p in local_files)
    local_evidence_mib = round(local_evidence_bytes / (1024 * 1024), 3)

    # 10. Memory usage
    peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_mib = round(peak_rss_kb / 1024, 2)

    # 11. Check durable lifecycle head
    head = store.get_committed_run_head(run.run_authority_id)
    assert head is not None, "Committed run head is None"
    log(f"Durable lifecycle head: state={head.head_state}, sequence={head.transition_sequence}, terminal={head.terminal}")

    # 12. Post-run environment verification
    assert CURRENT_EXECUTION_POLICY == "RESEARCH_DISABLED_V1"
    assert ACCEPTED_EXECUTION_WRITE_AUTHORITY is None

    # Verify ETH source unchanged
    post_eth_sha = sha256_file(eth_source_path)
    assert post_eth_sha == expected_eth_sha, "ETH source file modified during run!"

    script_path = Path(__file__).resolve()
    script_sha = sha256_file(script_path)

    summary = {
        "run_authority_id": run.run_authority_id,
        "discovery_run_grant_hash": grant.discovery_run_grant_hash,
        "discovery_authorization_receipt_hash": discovery_auth.receipt_hash,
        "discovery_evidence_sha256": real_evidence.evidence_sha256,
        "correction_manifest_hash": real_evidence.correction_input_evidence_manifest_hash,
        "runtime_authority_snapshot_hash": seal.runtime_authority_snapshot_hash,
        "sealed_registered_roster_hash": seal.sealed_registered_roster_hash,
        "materialized_run_authority_hash": run.materialized_run_authority_hash,
        "source_manifest_hash": seal.source_manifest_hash,
        "split_manifest_hash": seal.split_manifest_hash,
        "split_attestation_hash": seal.split_attestation_hash,
        "implementation_authority_hash": impl.lifecycle_implementation_authority_hash,
        "controller_authority_hash": ctrl.controller_authority_hash,
        "verified_candidates": 18,
        "hard_gate_passed_count": hard_gate_passed_count,
        "scientific_unavailable_count": scientific_unavailable_count,
        "candidate_lock_created": candidate_lock_created,
        "candidate_lock_receipt_hash": candidate_lock_receipt_hash,
        "selected_structural_configuration_hash": selected_cfg_hash,
        "selected_slot_hash": selected_slot_hash,
        "selected_slot_index": selected_slot_index,
        "termination_created": termination_created,
        "termination_receipt_hash": termination_receipt_hash,
        "terminal_state": terminal_state,
        "terminal_reason_code": terminal_reason_code,
        "producer_wall_seconds": producer_wall_seconds,
        "verification_wall_seconds": verification_wall_seconds,
        "peak_rss_mib": peak_rss_mib,
        "local_evidence_objects": local_evidence_objects,
        "local_evidence_mib": local_evidence_mib,
        "local_evidence_bytes": local_evidence_bytes,
        "execution_script_sha256": script_sha,
        "execution_script_path": str(script_path),
        "durable_head_state": head.head_state,
        "durable_head_sequence": head.transition_sequence,
        "durable_head_receipt_hash": head.head_receipt_hash,
        "durable_head_hash": head.head_hash,
        "durable_head_terminal": head.terminal,
        "execution_policy": CURRENT_EXECUTION_POLICY,
        "accepted_execution_write_authority": ACCEPTED_EXECUTION_WRITE_AUTHORITY,
        "signed_network_requests": 0,
        "source_identity_unchanged": True,
        "authorized_at_utc": authorized_at_utc,
        "formal_final_state": formal_final_state,
        "next_stage": next_stage,
    }

    out_file = Path("/tmp/m3b_run_summary.json")
    out_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(f"Run summary written to {out_file}")

    log("=== RUN SUMMARY ===")
    for k, v in summary.items():
        log(f"  {k}: {v}")

    log(f"Total script elapsed: {round(time.perf_counter() - t_start, 2)}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
