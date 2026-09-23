"""Synthetic-only adversarial checks for the production Discovery verifier."""

from __future__ import annotations

import hashlib
import inspect
import json
import math
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from btc_quant_agent.h40 import (
    ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH,
    DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
    H40CandidateResultEntry,
    H40DiscoveryEvidenceResolver,
    H40DiscoveryAuthorizationReceipt,
    H40DiscoveryResultEvidence,
    H40LifecycleEvidenceVerifier,
    H40ProductionDiscoveryEvidenceVerifier,
    H40RunAuthority,
    H40RuntimeRosterEntry,
    H40RuntimeSnapshotSeal,
    H40SplitManifest,
    materialize_h40_search_space_production,
)
from btc_quant_agent.h40.discovery_evidence import (
    _FAMILIES,
    _POLICIES,
    h40_bootstrap_metric,
    h40_bootstrap_seed,
    h40_bootstrap_starts,
    h40_discovery_coverage,
    h40_discovery_coverage_audit,
    h40_family_adjusted_lcbs,
    h40_holm_fixed_six,
    h40_marginal_p,
    h40_proxy_net_return,
    h40_side_preserving_action,
)
from btc_quant_agent.h40.guards import H40GuardError
from btc_quant_agent.h40.split_manifest import H40Partition, H40PartitionType
from btc_quant_agent.research_contract.canonical import canonical_json, canonical_sha256


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _store(root: Path, payload: dict[str, Any]) -> str:
    digest = canonical_sha256(payload)
    directory = root / digest[:2]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{digest}.json").write_text(canonical_json(payload), encoding="utf-8")
    return digest


def _read(root: Path, digest: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads((root / digest[:2] / f"{digest}.json").read_text(encoding="utf-8")),
    )


def _replace_manifest(
    fixture: _InvalidFixture, change: dict[str, Any],
) -> H40DiscoveryResultEvidence:
    payload = _read(fixture.root, fixture.evidence.correction_input_evidence_manifest_hash)
    payload.update(change)
    digest = _store(fixture.root, payload)
    evidence = replace(fixture.evidence, correction_input_evidence_manifest_hash=digest)
    _store(fixture.root, evidence.to_dict())
    return evidence


def _replace_candidate_decisions(
    fixture: _InvalidFixture, index: int, partition: str,
    mutate: Any,
) -> H40DiscoveryResultEvidence:
    entry = fixture.entries[index]
    result = _read(fixture.root, entry.candidate_result_input_evidence_hash)
    field = "training_evidence_hash" if partition == "WF1_TRAIN" else "calibration_evidence_hash"
    decisions = _read(fixture.root, result[field])
    mutate(decisions)
    new_decisions_hash = _store(fixture.root, decisions)
    result[field] = new_decisions_hash
    gate_hashes: dict[str, str] = {}
    for gate_id, digest in entry.hard_gate_input_evidence_hashes.items():
        gate = _read(fixture.root, digest)
        gate[field] = new_decisions_hash
        gate_hashes[gate_id] = _store(fixture.root, gate)
    result["hard_gate_input_evidence_hashes"] = gate_hashes
    new_result_hash = _store(fixture.root, result)
    new_entry = replace(
        entry,
        candidate_result_input_evidence_hash=new_result_hash,
        hard_gate_input_evidence_hashes=gate_hashes,
    )
    entries = list(fixture.entries)
    entries[index] = new_entry
    evidence = replace(fixture.evidence, candidate_result_entries=tuple(entries))
    _store(fixture.root, evidence.to_dict())
    return evidence


def _policy_stack() -> dict[str, dict[str, str]]:
    return {
        name: {"policy_id": identity[0], "policy_hash": identity[1]}
        for name, identity in _POLICIES.items()
    }


def _partition(partition_id: str, timestamps: list[str]) -> H40Partition:
    timestamp = timestamps[0]
    return H40Partition(
        partition_id=partition_id,
        fold="WF1",
        partition_type=(
            H40PartitionType.TRAIN if partition_id == "WF1_TRAIN"
            else H40PartitionType.CALIBRATION
        ),
        start_utc=timestamp,
        end_utc=(datetime.strptime(timestamps[-1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                 + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        count=len(timestamps),
        first_timestamp_utc=timestamp,
        last_timestamp_utc=timestamps[-1],
        timestamps_sha256=hashlib.sha256(",".join(timestamps).encode()).hexdigest(),
    )


@dataclass
class _InvalidFixture:
    root: Path
    verifier: H40ProductionDiscoveryEvidenceVerifier
    evidence: H40DiscoveryResultEvidence
    entries: tuple[H40CandidateResultEntry, ...]
    run_id: str


def _invalid_fixture(
    root: Path, *, complete_family: bool = False, poison_one_d1: bool = False,
) -> _InvalidFixture:
    slots = [slot for slot in materialize_h40_search_space_production().slots if slot.status == "REGISTERED"]
    roster = tuple(sorted((
        H40RuntimeRosterEntry(
            family_id="+".join(family.value for family in slot.family_combination),
            slot_hash=slot.slot_hash,
            slot_index=slot.slot_index,
            structural_configuration_hash=slot.structural_configuration_hash,
        )
        for slot in slots
    ), key=lambda item: item.structural_configuration_hash))
    train_t = "2022-01-01T00:00:00Z"
    calib_t = "2022-12-01T00:00:00Z"
    calib_start = datetime.strptime(calib_t, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    calib_times = [
        (calib_start + timedelta(hours=index)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for index in range(40 if complete_family else 1)
    ]
    split = H40SplitManifest(
        protocol_identity_hash=_hash("protocol"),
        source_manifest_hash=_hash("source"),
        base_eligible_start_utc="2021-01-31T00:00:00Z",
        base_eligible_end_utc="2026-01-31T00:00:00Z",
        base_eligible_count=2,
        partitions=(
            _partition("WF1_TRAIN", [train_t]),
            _partition("WF1_CALIBRATION", calib_times),
        ),
        exclusion_counts={},
    )
    seal = H40RuntimeSnapshotSeal.synthetic_for_tests(
        runtime_authority_snapshot_hash=_hash("snapshot"),
        source_manifest_hash=_hash("source"),
        split_manifest_hash=split.split_hash,
        split_attestation_hash=_hash("attestation"),
        roster=roster,
        not_testable_slot_count=150,
    )
    assert ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH is not None
    run = H40RunAuthority.from_seal(seal, ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH)
    receipt = H40DiscoveryAuthorizationReceipt(
        authorized_at_utc="2026-09-23T00:00:00Z",
        discovery_selection_correction_contract_hash=DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        execution_disabled=True,
        lifecycle_governance_authority_hash=run.lifecycle_governance_authority_hash,
        lifecycle_implementation_authority_hash=run.lifecycle_implementation_authority_hash,
        materialized_run_authority_hash=run.materialized_run_authority_hash,
        not_testable_slot_count=150,
        protocol_authority_hash=run.protocol_authority_hash,
        registered_slot_count=18,
        run_authority_id=run.run_authority_id,
        sealed_registered_roster_hash=run.sealed_registered_roster_hash,
        semantic_root_hash=run.semantic_root_hash,
        source_manifest_hash=run.source_manifest_hash,
        split_attestation_hash=run.split_attestation_hash,
        split_manifest_hash=run.split_manifest_hash,
        structural_ledger_hash=run.structural_ledger_hash,
        total_slot_count=168,
    )
    policies = _policy_stack()
    bars: list[dict[str, str]] = []
    for timestamp in (train_t, calib_t):
        start = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        count = (len(calib_times) + 12) if timestamp == calib_t and complete_family else 12
        for hour in range(count):
            price = (
                100.0 * (1.0 + 0.02 * math.sin(hour * 1.1))
                if timestamp == calib_t and complete_family
                else 100.0 if hour < 11 else 101.0
            )
            bars.append({
                "timestamp": (start + timedelta(hours=hour)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "product": "ETHUSDT", "open": str(price), "high": str(price),
                "low": str(price), "close": str(price),
            })
    source_hash = _store(root, {
        "schema_id": "H40_P3B_SOURCE_HOURS_V1", "run_authority_id": run.run_authority_id,
        "source_manifest_hash": seal.source_manifest_hash,
        "split_manifest_hash": seal.split_manifest_hash,
        "policies": policies,
        "bars": bars,
        "base_eligible_rows": {
            "WF1_TRAIN": [{"timestamp": train_t, "product": "ETHUSDT"}],
            "WF1_CALIBRATION": [
                {"timestamp": timestamp, "product": "ETHUSDT"}
                for timestamp in calib_times
            ],
        },
    })
    family_groups: dict[str, list[str]] = {family: [] for family in _FAMILIES}
    for item in roster:
        family_groups[item.family_id].append(item.structural_configuration_hash)
    manifest_hash = _store(root, {
        "schema_id": "H40_P3B_DISCOVERY_CORRECTION_MANIFEST_V1",
        "run_authority_id": run.run_authority_id,
        "sealed_registered_roster_hash": seal.sealed_registered_roster_hash,
        "discovery_authorization_receipt_hash": receipt.receipt_sha256,
        "materialized_run_authority_hash": seal.materialized_run_authority_hash,
        "source_manifest_hash": seal.source_manifest_hash,
        "split_manifest_hash": seal.split_manifest_hash,
        "discovery_partition": "WF1_CALIBRATION",
        "discovery_selection_correction_contract_hash": DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        "policies": policies,
        "candidate_configuration_hashes": [item.structural_configuration_hash for item in roster],
        "metric_universes": {"PRECISION": family_groups, "NET_EXPECTANCY": family_groups},
    })
    entries: list[H40CandidateResultEntry] = []
    slots_by_id = {slot.structural_configuration_hash: slot for slot in slots}
    first_d1 = next(item.structural_configuration_hash for item in roster if item.family_id == "D1_TREND_CONTINUATION")
    for item in roster:
        slot = slots_by_id[item.structural_configuration_hash]
        family_complete = (
            complete_family and item.family_id == "D1_TREND_CONTINUATION"
            and not (poison_one_d1 and item.structural_configuration_hash == first_d1)
        )
        def label_and_score(index: int) -> tuple[float, float]:
            horizon = int(slot.primary_horizon.rstrip("h"))
            p0 = 100.0 * (1.0 + 0.02 * math.sin(index * 1.1))
            ch = 100.0 * (1.0 + 0.02 * math.sin((index + horizon - 1) * 1.1))
            r_h = math.log(ch / p0)
            sign = 1.0 if r_h > 0.0012 else -1.0
            if index % 7 == 0:
                sign = -sign
            return r_h, sign

        fit = None
        if family_complete:
            pairs = []
            for index in range(len(calib_times)):
                r_h, score = label_and_score(index)
                if r_h > 0.0012:
                    pairs.append((score, 1))
                elif r_h < -0.0012:
                    pairs.append((score, 0))
            from btc_quant_agent.h40.discovery_evidence import h40_fit_calibrator
            fit = h40_fit_calibrator(slot.calibration_contract_id, pairs)

        def row(timestamp: str, *, train: bool, index: int = 0) -> dict[str, Any]:
            horizon = int(slot.primary_horizon.rstrip("h"))
            if not train and complete_family:
                r_h, calculated_score = label_and_score(index)
                score = calculated_score if family_complete else 1.0
            else:
                ch = 100.0 if horizon < 12 else 101.0
                r_h = math.log(ch / 100.0)
                score = 1.0
            p_up = None
            if fit is not None and not train:
                from btc_quant_agent.h40.discovery_evidence import h40_predict_calibrated
                p_up = str(h40_predict_calibrated(fit, score))
            return {
                "timestamp": timestamp, "product": "ETHUSDT",
                "regime_state": "REGIME_VOL_MID", "opportunity_state": "O_ELIGIBLE",
                "raw_score": str(score), "secondary_filter_state": "PASS", "p_up": p_up,
                "final_action": None if train else "NO_TRADE",
                "r_h": str(r_h), "r_net": None,
            }
        decision_hashes: dict[str, str] = {}
        for partition, timestamp, train in (
            ("WF1_TRAIN", train_t, True), ("WF1_CALIBRATION", calib_t, False),
        ):
            decision_hashes[partition] = _store(root, {
                "schema_id": "H40_P3B_RAW_DECISIONS_V1",
                "run_authority_id": run.run_authority_id,
                "sealed_registered_roster_hash": seal.sealed_registered_roster_hash,
                "structural_configuration_hash": item.structural_configuration_hash,
                "source_manifest_hash": seal.source_manifest_hash,
                "split_manifest_hash": seal.split_manifest_hash,
                "source_evidence_hash": source_hash,
                "partition_id": partition, "policies": policies,
                "rows": (
                    [row(train_t, train=True)] if train else
                    [row(t, train=False, index=index) for index, t in enumerate(calib_times)]
                ),
            })
        gate_hashes = {}
        for gate_id in (
            "COVERAGE", "TRAINING_NEFF", "CALIBRATION_SAMPLE", "GEOMETRY",
            "CALIBRATION_DIAGNOSTICS", "CONFIDENCE",
        ):
            gate_hashes[gate_id] = _store(root, {
                "schema_id": "H40_P3B_HARD_GATE_INPUT_V1",
                "run_authority_id": run.run_authority_id,
                "sealed_registered_roster_hash": seal.sealed_registered_roster_hash,
                "structural_configuration_hash": item.structural_configuration_hash,
                "gate_id": gate_id, "source_evidence_hash": source_hash,
                "training_evidence_hash": decision_hashes["WF1_TRAIN"],
                "calibration_evidence_hash": decision_hashes["WF1_CALIBRATION"],
                "policies": policies,
                "audit": (
                    {"N_accept": 0, "N_base": len(calib_times),
                     "lower_pass": False, "upper_pass": True}
                    if gate_id == "COVERAGE" and family_complete else None
                ),
            })
        metric_hashes = {}
        for metric_id in ("PRECISION", "NET_EXPECTANCY"):
            metric_payload: dict[str, Any] = {
                "schema_id": (
                    "H40_P3B_METRIC_BOOTSTRAP_V1" if family_complete
                    else "H40_P3B_INVALID_METRIC_INPUT_V1"
                ),
                "run_authority_id": run.run_authority_id,
                "sealed_registered_roster_hash": seal.sealed_registered_roster_hash,
                "structural_configuration_hash": item.structural_configuration_hash,
                "metric_id": metric_id,
                "correction_manifest_hash": manifest_hash,
                "fit_status": "COMPLETE" if family_complete else "FIT_INVALID",
                "policies": policies,
            }
            if family_complete:
                from btc_quant_agent.h40.discovery_evidence import h40_bootstrap_starts
                audit = h40_bootstrap_seed(item.structural_configuration_hash, metric_id)
                start_matrix, matrix_hash = h40_bootstrap_starts(audit.seed, 2184)
                assert start_matrix.shape == (10_000, 13)
                metric_payload.update({
                    "calibration_evidence_hash": decision_hashes["WF1_CALIBRATION"],
                    "seed_identity_policy_id": _POLICIES["seed_identity"][0],
                    "seed_identity_policy_hash": _POLICIES["seed_identity"][1],
                    "protocol_id": run.protocol_authority_hash,
                    "candidate_id": item.structural_configuration_hash,
                    "partition_id": "WF1_CALIBRATION",
                    "canonical_seed_preimage": audit.canonical_seed_preimage,
                    "seed_digest_sha256": audit.seed_digest_sha256,
                    "raw_u64": audit.raw_u64, "seed": audit.seed,
                    "numpy_version": np.__version__, "bit_generator": "PCG64",
                    "bootstrap_start_sampler_policy_id": _POLICIES["bootstrap_start_sampler"][0],
                    "bootstrap_start_sampler_policy_hash": _POLICIES["bootstrap_start_sampler"][1],
                    "H": 2184, "L": 168, "S": 2017, "B": 13, "M": 10_000,
                    "start_matrix_hash": matrix_hash,
                })
            else:
                metric_payload["fit_failure_reason"] = "DEGENERATE_CALIBRATION"
            metric_hashes[metric_id] = _store(root, metric_payload)
        result_hash = _store(root, {
            "schema_id": "H40_P3B_CANDIDATE_RESULT_INPUT_V1",
            "run_authority_id": run.run_authority_id,
            "sealed_registered_roster_hash": seal.sealed_registered_roster_hash,
            "structural_configuration_hash": item.structural_configuration_hash,
            "slot_hash": item.slot_hash, "slot_index": item.slot_index,
            "source_manifest_hash": seal.source_manifest_hash,
            "split_manifest_hash": seal.split_manifest_hash,
            "source_evidence_hash": source_hash,
            "training_evidence_hash": decision_hashes["WF1_TRAIN"],
            "calibration_evidence_hash": decision_hashes["WF1_CALIBRATION"],
            "fit_status": "COMPLETE" if family_complete else "FIT_INVALID",
            "fit_failure_reason": None if family_complete else "DEGENERATE_CALIBRATION",
            "policies": policies,
            "hard_gate_input_evidence_hashes": gate_hashes,
            "precision_input_evidence_hash": metric_hashes["PRECISION"],
            "net_expectancy_input_evidence_hash": metric_hashes["NET_EXPECTANCY"],
        })
        entries.append(H40CandidateResultEntry(
            candidate_result_input_evidence_hash=result_hash,
            complexity=1, family_id=item.family_id,
            hard_gate_input_evidence_hashes=gate_hashes,
            net_expectancy_input_evidence_hash=metric_hashes["NET_EXPECTANCY"],
            precision_input_evidence_hash=metric_hashes["PRECISION"],
            slot_hash=item.slot_hash, slot_index=item.slot_index,
            structural_configuration_hash=item.structural_configuration_hash,
        ))
    evidence = H40DiscoveryResultEvidence(
        candidate_result_entries=tuple(entries),
        correction_input_evidence_manifest_hash=manifest_hash,
        created_at_utc="2026-09-23T00:00:00Z",
        discovery_authorization_receipt_hash=receipt.receipt_sha256,
        materialized_run_authority_hash=seal.materialized_run_authority_hash,
        run_authority_id=run.run_authority_id,
        sealed_registered_roster_hash=seal.sealed_registered_roster_hash,
    )
    _store(root, evidence.to_dict())
    verifier = H40ProductionDiscoveryEvidenceVerifier(
        approved_evidence_root=root, seal=seal, authorization_receipt=receipt,
        split_manifest=split,
    )
    return _InvalidFixture(root, verifier, evidence, tuple(entries), run.run_authority_id)


def test_v01_protocol_and_fit_invalid_family(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path)
    assert isinstance(fixture.verifier, H40LifecycleEvidenceVerifier)
    assert fixture.verifier.synthetic_only is False
    fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    for entry in fixture.entries:
        result = fixture.verifier.verify_candidate(
            entry, run_authority_id=fixture.run_id,
            correction_manifest_hash=fixture.evidence.correction_input_evidence_manifest_hash,
        )
        assert result.hard_gates_passed is False
        assert result.scientific_unavailable is True
        assert result.adjusted_lcb_precision is None
        assert result.adjusted_lcb_net_expectancy is None


def test_v26_valid_family_continues_after_other_families_fit_invalid(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path, complete_family=True)
    fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    complete = [entry for entry in fixture.entries if entry.family_id == "D1_TREND_CONTINUATION"]
    poisoned = [entry for entry in fixture.entries if entry.family_id != "D1_TREND_CONTINUATION"]
    assert len(complete) == 6 and len(poisoned) == 12
    for entry in complete:
        result = fixture.verifier.verify_candidate(
            entry, run_authority_id=fixture.run_id,
            correction_manifest_hash=fixture.evidence.correction_input_evidence_manifest_hash,
        )
        assert result.scientific_unavailable is False
        assert result.hard_gates_passed is False
        assert result.adjusted_lcb_precision is not None
        assert result.adjusted_lcb_net_expectancy is not None
    for entry in poisoned:
        result = fixture.verifier.verify_candidate(
            entry, run_authority_id=fixture.run_id,
            correction_manifest_hash=fixture.evidence.correction_input_evidence_manifest_hash,
        )
        assert result.scientific_unavailable is True


def test_v26_v27_one_invalid_registered_member_poisons_full_family(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path, complete_family=True, poison_one_d1=True)
    fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    for entry in fixture.entries:
        if entry.family_id != "D1_TREND_CONTINUATION":
            continue
        result = fixture.verifier.verify_candidate(
            entry, run_authority_id=fixture.run_id,
            correction_manifest_hash=fixture.evidence.correction_input_evidence_manifest_hash,
        )
        assert result.scientific_unavailable is True
        assert result.adjusted_lcb_precision is None
        assert result.adjusted_lcb_net_expectancy is None


@pytest.mark.parametrize("foreign_metric", [None, "0", "NaN", "Infinity", "-Infinity", "1e100"])
def test_v28_fit_invalid_metric_imputation_is_rejected(
    tmp_path: Path, foreign_metric: str | None,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    entry = fixture.entries[0]
    digest = entry.precision_input_evidence_hash
    payload = _read(fixture.root, digest)
    payload["adjusted_lcb"] = foreign_metric
    new_digest = _store(fixture.root, payload)
    result = _read(fixture.root, entry.candidate_result_input_evidence_hash)
    result["precision_input_evidence_hash"] = new_digest
    new_result_digest = _store(fixture.root, result)
    entries = tuple(
        replace(item, precision_input_evidence_hash=new_digest,
                candidate_result_input_evidence_hash=new_result_digest)
        if item == entry else item for item in fixture.entries
    )
    evidence = replace(fixture.evidence, candidate_result_entries=entries)
    _store(fixture.root, evidence.to_dict())
    with pytest.raises(H40GuardError, match="missing or extra schema keys"):
        fixture.verifier.verify_discovery_manifest(evidence, entries)


def test_cov01_cov04_calibration_final_actions_define_coverage_population(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path, complete_family=True)
    entry = next(item for item in fixture.entries if item.family_id == "D1_TREND_CONTINUATION")
    result = _read(fixture.root, entry.candidate_result_input_evidence_hash)
    training = _read(fixture.root, result["training_evidence_hash"])["rows"]
    calibration = _read(fixture.root, result["calibration_evidence_hash"])["rows"]
    assert len(training) == 1 and training[0]["raw_score"] == "1.0"
    assert len(calibration) == 40
    assert all(row["final_action"] == "NO_TRADE" for row in calibration)
    coverage = _read(fixture.root, entry.hard_gate_input_evidence_hashes["COVERAGE"])["audit"]
    assert coverage == {"N_accept": 0, "N_base": 40,
                        "lower_pass": False, "upper_pass": True}
    fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)


@pytest.mark.parametrize("policy_name", list(_POLICIES))
def test_policy_stack_binding_rejects_foreign_hash(tmp_path: Path, policy_name: str) -> None:
    fixture = _invalid_fixture(tmp_path)
    payload = _read(tmp_path, fixture.evidence.correction_input_evidence_manifest_hash)
    payload["policies"][policy_name]["policy_hash"] = "0" * 64
    evidence = _replace_manifest(fixture, {"policies": payload["policies"]})
    with pytest.raises(H40GuardError, match="policy identity mismatch"):
        fixture.verifier.verify_discovery_manifest(evidence, evidence.candidate_result_entries)


@pytest.mark.parametrize("alteration", [
    {"run_authority_id": "0" * 64},
    {"extra_caller_rank": 1},
    {"candidate_configuration_hashes": []},
])
def test_v03_v04_v06_v19_manifest_claims_do_not_authorize(
    tmp_path: Path, alteration: dict[str, Any],
) -> None:
    fixture = _invalid_fixture(tmp_path)
    evidence = _replace_manifest(fixture, alteration)
    with pytest.raises(H40GuardError):
        fixture.verifier.verify_discovery_manifest(evidence, evidence.candidate_result_entries)


def test_v02_missing_or_mutated_object_bytes_fail_closed(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path)
    digest = fixture.evidence.correction_input_evidence_manifest_hash
    path = tmp_path / digest[:2] / f"{digest}.json"
    original = path.read_bytes()
    path.write_bytes(original + b" ")
    with pytest.raises(H40GuardError):
        fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    path.unlink()
    with pytest.raises(H40GuardError):
        fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)


def test_v06_v07_incomplete_duplicate_or_reordered_entry_fails(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path)
    with pytest.raises(H40GuardError):
        fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries[:-1])
    with pytest.raises(ValueError):
        replace(fixture.evidence, candidate_result_entries=fixture.entries[::-1])
    duplicated = tuple(sorted(
        (*fixture.entries[:-1], fixture.entries[0]),
        key=lambda entry: entry.structural_configuration_hash,
    ))
    altered = replace(fixture.evidence, candidate_result_entries=duplicated)
    _store(tmp_path, altered.to_dict())
    with pytest.raises(H40GuardError):
        fixture.verifier.verify_discovery_manifest(altered, altered.candidate_result_entries)


def test_v05_candidate_binding_and_stale_manifest_rejected(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path)
    fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    with pytest.raises(H40GuardError):
        fixture.verifier.verify_candidate(
            replace(fixture.entries[0], family_id="D2_BREAKOUT_CONTINUATION"),
            run_authority_id=fixture.run_id,
            correction_manifest_hash=fixture.evidence.correction_input_evidence_manifest_hash,
        )
    with pytest.raises(H40GuardError):
        fixture.verifier.verify_candidate(
            fixture.entries[0], run_authority_id="0" * 64,
            correction_manifest_hash=fixture.evidence.correction_input_evidence_manifest_hash,
        )


def test_r06_raw_price_derived_log_return_tamper_rejected(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path)
    evidence = _replace_candidate_decisions(
        fixture, 0, "WF1_TRAIN",
        lambda payload: payload["rows"][0].__setitem__("r_h", "0.5"),
    )
    with pytest.raises(H40GuardError, match="log return does not match"):
        fixture.verifier.verify_discovery_manifest(evidence, evidence.candidate_result_entries)


def test_r06_supplied_net_return_tamper_rejected(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path)
    def mutate(payload: dict[str, Any]) -> None:
        payload["rows"][0]["final_action"] = "LONG"
        payload["rows"][0]["r_net"] = "0.0"
    evidence = _replace_candidate_decisions(fixture, 0, "WF1_CALIBRATION", mutate)
    with pytest.raises(H40GuardError, match="proxy net return does not match"):
        fixture.verifier.verify_discovery_manifest(evidence, evidence.candidate_result_entries)


@pytest.mark.parametrize("extra", [{"c_rt": "0.002"}, {"funding": "0.01"}])
def test_r07_r08_wrong_cost_or_funding_cannot_enter_proxy_evidence(
    tmp_path: Path, extra: dict[str, str],
) -> None:
    fixture = _invalid_fixture(tmp_path)
    def mutate(payload: dict[str, Any]) -> None:
        payload["rows"][0].update(extra)
    evidence = _replace_candidate_decisions(fixture, 0, "WF1_CALIBRATION", mutate)
    with pytest.raises(H40GuardError, match="schema keys"):
        fixture.verifier.verify_discovery_manifest(evidence, evidence.candidate_result_entries)


def test_cov12_action_outside_base_universe_fails(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path)
    def mutate(payload: dict[str, Any]) -> None:
        row = dict(payload["rows"][0])
        row["timestamp"] = "2022-12-01T01:00:00Z"
        row["final_action"] = "LONG"
        row["r_net"] = "0.0"
        payload["rows"].append(row)
    evidence = _replace_candidate_decisions(fixture, 0, "WF1_CALIBRATION", mutate)
    with pytest.raises(H40GuardError, match="active-scope partition"):
        fixture.verifier.verify_discovery_manifest(evidence, evidence.candidate_result_entries)


def test_cov14_exact_integer_comparison_avoids_float_boundary() -> None:
    accepted = 10**18
    base = 400 * accepted + 1
    assert float(accepted / base) == 0.0025
    assert h40_discovery_coverage(accepted, base) is False


def test_cov_audit_persists_exact_components_and_rejects_tamper(tmp_path: Path) -> None:
    assert h40_discovery_coverage_audit(1, 400).to_dict() == {
        "N_accept": 1, "N_base": 400, "lower_pass": True, "upper_pass": True,
    }
    fixture = _invalid_fixture(tmp_path, complete_family=True)
    entry = next(item for item in fixture.entries if item.family_id == "D1_TREND_CONTINUATION")
    digest = entry.hard_gate_input_evidence_hashes["COVERAGE"]
    gate = _read(fixture.root, digest)
    gate["audit"]["N_base"] += 1
    new_digest = _store(fixture.root, gate)
    result = _read(fixture.root, entry.candidate_result_input_evidence_hash)
    gates = dict(result["hard_gate_input_evidence_hashes"])
    gates["COVERAGE"] = new_digest
    result["hard_gate_input_evidence_hashes"] = gates
    new_result_digest = _store(fixture.root, result)
    entries = tuple(
        replace(item, hard_gate_input_evidence_hashes=gates,
                candidate_result_input_evidence_hash=new_result_digest)
        if item == entry else item for item in fixture.entries
    )
    evidence = replace(fixture.evidence, candidate_result_entries=entries)
    _store(fixture.root, evidence.to_dict())
    with pytest.raises(H40GuardError, match="coverage audit differs"):
        fixture.verifier.verify_discovery_manifest(evidence, entries)


@pytest.mark.parametrize("score,p_up,expected", [
    (1.0, 0.7, "LONG"), (-1.0, 0.3, "SHORT"),
    (1.0, 0.3, "NO_TRADE"), (-1.0, 0.7, "NO_TRADE"),
])
def test_direction_calibration_never_reverses_owner(
    score: float, p_up: float, expected: str,
) -> None:
    assert h40_side_preserving_action(score, p_up, 0.6) == expected


def test_v20_deterministic_manifest_replay(tmp_path: Path) -> None:
    fixture = _invalid_fixture(tmp_path, complete_family=True)
    fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    first = fixture.verifier.verify_candidate(
        fixture.entries[0], run_authority_id=fixture.run_id,
        correction_manifest_hash=fixture.evidence.correction_input_evidence_manifest_hash,
    )
    fixture.verifier.verify_discovery_manifest(fixture.evidence, fixture.entries)
    second = fixture.verifier.verify_candidate(
        fixture.entries[0], run_authority_id=fixture.run_id,
        correction_manifest_hash=fixture.evidence.correction_input_evidence_manifest_hash,
    )
    assert first == second


def test_v21_resolver_rejects_traversal_and_symlink_escape(tmp_path: Path) -> None:
    resolver = H40DiscoveryEvidenceResolver(tmp_path)
    with pytest.raises(H40GuardError):
        resolver.load("../outside", "X", {"schema_id"})
    digest = "a" * 64
    object_dir = tmp_path / digest[:2]
    object_dir.mkdir()
    outside = tmp_path.parent / "outside-synthetic-evidence.json"
    outside.write_text("{}", encoding="utf-8")
    (object_dir / f"{digest}.json").symlink_to(outside)
    with pytest.raises(H40GuardError, match="symlink"):
        resolver.load(digest, "X", {"schema_id"})


@pytest.mark.parametrize("replacement", [b"{}\n", b'{"schema_id":NaN}'])
def test_v22_noncanonical_or_nonfinite_bytes_rejected(tmp_path: Path, replacement: bytes) -> None:
    payload = {"schema_id": "X"}
    digest = _store(tmp_path, payload)
    (tmp_path / digest[:2] / f"{digest}.json").write_bytes(replacement)
    with pytest.raises(H40GuardError):
        H40DiscoveryEvidenceResolver(tmp_path).load(digest, "X", {"schema_id"})


def test_v23_v24_v25_synthetic_and_protected_surfaces_sealed(tmp_path: Path) -> None:
    from btc_quant_agent.h40 import discovery_evidence
    assert "H40SyntheticEvidenceVerifier" not in inspect.getsource(discovery_evidence)
    fixture = _invalid_fixture(tmp_path)
    with pytest.raises(H40GuardError, match="NOT_TESTABLE"):
        fixture.verifier.verify_wf_fold(None, evidence=None)  # type: ignore[arg-type]
    protected_root = tmp_path / "h39_protected"
    protected_root.mkdir()
    with pytest.raises(H40GuardError, match="PROTECTED_SURFACE_DENIED"):
        H40DiscoveryEvidenceResolver(protected_root)


@pytest.mark.parametrize("action,close,expected", [
    ("LONG", "101", 0.0088), ("SHORT", "101", -0.0112),
    ("LONG", "99", -0.0112), ("SHORT", "99", 0.0088),
    ("LONG", "100", -0.0012), ("SHORT", "100", -0.0012),
])
def test_r01_r04_proxy_golden(action: str, close: str, expected: float) -> None:
    _, net = h40_proxy_net_return(action, "100", close)
    assert net == pytest.approx(expected, abs=1e-14)


def test_r05_log_return_pnl_is_different() -> None:
    r_h, net = h40_proxy_net_return("SHORT", "100", "120")
    assert net != pytest.approx(-r_h - 0.0012)


@pytest.mark.parametrize("accept,base,expected", [
    (1, 400, True), (1, 401, False), (10, 100, True),
    (11, 100, False), (0, 100, False),
])
def test_cov05_cov10_exact_integer_gate(accept: int, base: int, expected: bool) -> None:
    assert h40_discovery_coverage(accept, base) is expected


def test_cov09_zero_denominator() -> None:
    with pytest.raises(H40GuardError, match="NOT_TESTABLE"):
        h40_discovery_coverage(0, 0)


def test_cov11_pooled_count_weighting() -> None:
    # Count-weighted pooled ratio is 10/400, not the mean of 10/20 and 0/380.
    assert h40_discovery_coverage(10 + 0, 20 + 380)
    assert (10 / 20 + 0 / 380) / 2 > 0.10


def test_s01_s06_seed_binding_and_metric_separation() -> None:
    candidate = "0" * 64
    precision = h40_bootstrap_seed(candidate, "PRECISION")
    net = h40_bootstrap_seed(candidate, "NET_EXPECTANCY")
    assert precision.canonical_seed_preimage == canonical_json([
        "a83f8fc7a5ca7109fb8cd7fed114d87c3b2c968b5145c11cada203aa5111d1ce",
        candidate, "WF1_CALIBRATION", "PRECISION",
    ])
    assert precision.seed_digest_sha256 != net.seed_digest_sha256
    assert h40_bootstrap_seed("1" * 64, "PRECISION").seed_digest_sha256 != precision.seed_digest_sha256


def test_s03_s04_seed_ignores_runtime_and_source_split_identity() -> None:
    candidate = "2" * 64
    first_run = _hash("run-a")
    second_run = _hash("run-b")
    first_source = _hash("source-a")
    second_source = _hash("source-b")
    assert first_run != second_run and first_source != second_source
    seed_a = h40_bootstrap_seed(candidate, "PRECISION")
    seed_b = h40_bootstrap_seed(candidate, "PRECISION")
    assert seed_a == seed_b
    assert first_run not in seed_a.canonical_seed_preimage
    assert first_source not in seed_a.canonical_seed_preimage


@pytest.mark.parametrize("wrong_metric", ["precision", "NET_EXPECTANCY_V1", "RANDOM_MATCHED"])
def test_s07_only_exact_discovery_metric_ids(wrong_metric: str) -> None:
    with pytest.raises(H40GuardError):
        h40_bootstrap_seed("0" * 64, wrong_metric)


@pytest.mark.parametrize("field,value", [
    ("numpy_version", "0.0.0-foreign"),
    ("protocol_id", "6533" + "0" * 60),
    ("candidate_id", "0" * 64),
    ("partition_id", "WF1_CALIB"),
    ("metric_id", "precision"),
    ("seed", 0),
    ("start_matrix_hash", "0" * 64),
    ("bit_generator", "MT19937"),
])
def test_s01_s10_samp08_samp09_metric_audit_rejects_foreign_identity(
    tmp_path: Path, field: str, value: Any,
) -> None:
    import btc_quant_agent.h40.discovery_evidence as module
    fixture = _invalid_fixture(tmp_path, complete_family=True)
    entry = next(item for item in fixture.entries if item.family_id == "D1_TREND_CONTINUATION")
    payload = _read(tmp_path, entry.precision_input_evidence_hash)
    payload[field] = value
    mutated_digest = _store(tmp_path, payload)
    altered_entry = replace(entry, precision_input_evidence_hash=mutated_digest)
    slot = next(
        slot for slot in materialize_h40_search_space_production().slots
        if slot.structural_configuration_hash == entry.structural_configuration_hash
    )
    loaded = module._LoadedCandidate(
        altered_entry, slot,
        _read(tmp_path, entry.candidate_result_input_evidence_hash),
        (), (), True,
    )
    with pytest.raises(H40GuardError, match=(
        "REPLAY_ENVIRONMENT_MISMATCH" if field == "numpy_version" else None
    )):
        fixture.verifier._metric_starts(
            loaded, "PRECISION", fixture.evidence.correction_input_evidence_manifest_hash,
        )


def test_samp08_samp12_exact_matrix_replay() -> None:
    seed = h40_bootstrap_seed("0" * 64, "PRECISION").seed
    first, first_hash = h40_bootstrap_starts(seed, 340)
    second, second_hash = h40_bootstrap_starts(seed, 340)
    assert first.shape == (10_000, 3)
    assert np.array_equal(first, second)
    assert first_hash == second_hash == canonical_sha256(first.tolist())


def test_samp01_samp03_exact_single_first_rng_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    real_generator = np.random.Generator

    class Spy:
        def __init__(self, bit_generator: Any) -> None:
            calls.append(("construct", {"bit_generator": type(bit_generator).__name__}))
            self._actual = real_generator(bit_generator)

        def integers(self, **kwargs: Any) -> np.ndarray:
            calls.append(("integers", kwargs))
            return cast(np.ndarray, self._actual.integers(**kwargs))

    monkeypatch.setattr(np.random, "Generator", Spy)
    h40_bootstrap_starts(17, 340)
    assert [name for name, _ in calls] == ["construct", "integers"]
    assert calls[0][1] == {"bit_generator": "PCG64"}
    assert calls[1][1] == {
        "low": 0, "high": 173, "size": (10_000, 3),
        "dtype": np.int64, "endpoint": False,
    }


def test_samp06_samp07_foreign_samplers_do_not_replay() -> None:
    seed = 17
    accepted, accepted_hash = h40_bootstrap_starts(seed, 340)
    foreign_choice = np.random.Generator(np.random.PCG64(seed)).choice(
        np.arange(173, dtype=np.int64)[::-1], size=(10_000, 3), replace=True,
    )
    foreign_raw = np.random.PCG64(seed).random_raw(30_000).reshape(10_000, 3) % 173
    assert not np.array_equal(accepted, foreign_choice)
    assert not np.array_equal(accepted, foreign_raw)
    assert canonical_sha256(foreign_choice.tolist()) != accepted_hash
    assert canonical_sha256(foreign_raw.tolist()) != accepted_hash


def test_samp11_metric_seeds_have_separate_start_matrices() -> None:
    candidate = "0" * 64
    precision, precision_hash = h40_bootstrap_starts(
        h40_bootstrap_seed(candidate, "PRECISION").seed, 340,
    )
    net, net_hash = h40_bootstrap_starts(
        h40_bootstrap_seed(candidate, "NET_EXPECTANCY").seed, 340,
    )
    assert precision_hash != net_hash
    assert not np.array_equal(precision, net)


def test_samp10_short_partition_fails_without_rng() -> None:
    with pytest.raises(H40GuardError, match="NOT_TESTABLE"):
        h40_bootstrap_starts(1, 167)


def test_b04_missing_source_halo_endpoint_fails_closed(tmp_path: Path) -> None:
    import btc_quant_agent.h40.discovery_evidence as module
    fixture = _invalid_fixture(tmp_path)
    slot_by_id = {
        slot.structural_configuration_hash: slot
        for slot in materialize_h40_search_space_production().slots
    }
    entry = next(
        item for item in fixture.entries
        if slot_by_id[item.structural_configuration_hash].primary_horizon == "12h"
    )
    result = _read(tmp_path, entry.candidate_result_input_evidence_hash)
    source = _read(tmp_path, result["source_evidence_hash"])
    bars = {}
    for raw in source["bars"]:
        timestamp = datetime.strptime(raw["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        if raw["timestamp"] == "2022-12-01T11:00:00Z":
            continue
        bars[(timestamp, raw["product"])] = module._Bar(
            timestamp, raw["product"],
            float(raw["open"]), float(raw["high"]),
            float(raw["low"]), float(raw["close"]),
        )
    t = datetime(2022, 12, 1, tzinfo=UTC)
    with pytest.raises(H40GuardError, match="missing source-local outcome-support"):
        module._load_decisions(
            H40DiscoveryEvidenceResolver(tmp_path), result["calibration_evidence_hash"],
            run_authority_id=fixture.run_id,
            roster_hash=fixture.evidence.sealed_registered_roster_hash,
            candidate_id=entry.structural_configuration_hash,
            source_manifest_hash=result["source_manifest_hash"],
            split_manifest_hash=result["split_manifest_hash"],
            source_evidence_hash=result["source_evidence_hash"],
            partition_id="WF1_CALIBRATION", products=("ETHUSDT",), horizon=12,
            bars=bars, base_universe=frozenset({(t, "ETHUSDT")}),
        )


def test_b05_b08_source_hour_occurrence_and_tail_trim() -> None:
    h = 169
    starts = np.zeros((10_000, 2), dtype=np.int64)
    counts = np.zeros(h)
    correct = np.zeros(h)
    net = np.zeros(h)
    counts[0] = 1
    correct[0] = 1
    net[0] = 0.0088
    # First sampled core contributes hour 0; final H trim retains only one
    # position of block 2, which repeats that same source hour.
    result = h40_bootstrap_metric(starts, counts, correct, net, "NET_EXPECTANCY")
    assert np.all(result == pytest.approx(0.0088))


def test_b01_b03_source_bound_endpoint_survives_next_block_jump() -> None:
    h = 336
    starts = np.tile(np.array([[0, 168]], dtype=np.int64), (10_000, 1))
    counts = np.zeros(h)
    correct = np.zeros(h)
    net = np.zeros(h)
    counts[167] = 1
    net[167] = h40_proxy_net_return("LONG", "100", "101")[1]
    original = h40_bootstrap_metric(starts, counts, correct, net, "NET_EXPECTANCY")
    # The next sampled block's price jump cannot be smuggled in as a return
    # for a source hour that did not emit an accepted trade.
    net[168] = -9999.0
    with pytest.raises(H40GuardError, match="aggregates are inconsistent"):
        h40_bootstrap_metric(starts, counts, correct, net, "NET_EXPECTANCY")
    assert np.all(original == pytest.approx(0.0088, abs=1e-14))


def test_b06_post_h_position_does_not_contribute() -> None:
    h = 340
    starts = np.tile(np.array([[100, 100, 0]], dtype=np.int64), (10_000, 1))
    counts = np.zeros(h)
    correct = np.zeros(h)
    net = np.zeros(h)
    counts[4] = 1
    net[4] = 9.0
    result = h40_bootstrap_metric(starts, counts, correct, net, "NET_EXPECTANCY")
    assert np.all(result == 0.0)


def test_b07_b08_duplicate_and_overlapping_hours_keep_multiplicity() -> None:
    h = 169
    counts = np.zeros(h)
    correct = np.zeros(h)
    net = np.zeros(h)
    counts[:2] = 1
    net[0] = 1.0
    duplicate = np.tile(np.array([[0, 0]], dtype=np.int64), (10_000, 1))
    overlap = np.tile(np.array([[0, 1]], dtype=np.int64), (10_000, 1))
    duplicate_result = h40_bootstrap_metric(duplicate, counts, correct, net, "NET_EXPECTANCY")
    overlap_result = h40_bootstrap_metric(overlap, counts, correct, net, "NET_EXPECTANCY")
    assert np.all(duplicate_result == pytest.approx(2 / 3))
    assert np.all(overlap_result == pytest.approx(1 / 3))


def test_b11_joint_asset_hour_uses_one_start_matrix() -> None:
    starts = np.zeros((10_000, 1), dtype=np.int64)
    counts = np.zeros(168)
    correct = np.zeros(168)
    net = np.zeros(168)
    counts[0] = 2  # BTC and ETH same source UTC hour.
    correct[0] = 1
    net[0] = 0.02
    assert np.all(h40_bootstrap_metric(starts, counts, correct, net, "PRECISION") == 0.5)
    assert np.all(h40_bootstrap_metric(starts, counts, correct, net, "NET_EXPECTANCY") == 0.01)


def test_b10_source_identity_not_synthetic_position() -> None:
    h = 336
    first = np.tile(np.array([[0, 168]], dtype=np.int64), (10_000, 1))
    second = np.tile(np.array([[168, 0]], dtype=np.int64), (10_000, 1))
    counts = np.zeros(h)
    correct = np.zeros(h)
    net = np.zeros(h)
    counts[2] = counts[170] = 1
    net[2] = 0.01
    net[170] = -0.02
    first_result = h40_bootstrap_metric(first, counts, correct, net, "NET_EXPECTANCY")
    second_result = h40_bootstrap_metric(second, counts, correct, net, "NET_EXPECTANCY")
    assert np.array_equal(first_result, second_result)


def test_r10_recomputed_proxy_returns_feed_bootstrap() -> None:
    counts = np.zeros(168)
    correct = np.zeros(168)
    net = np.zeros(168)
    counts[0] = counts[1] = 1
    net[0] = h40_proxy_net_return("LONG", "100", "101")[1]
    net[1] = h40_proxy_net_return("SHORT", "100", "99")[1]
    starts = np.zeros((10_000, 1), dtype=np.int64)
    values = h40_bootstrap_metric(starts, counts, correct, net, "NET_EXPECTANCY")
    assert np.all(values == pytest.approx(0.0088, abs=1e-14))


def test_v14_v15_fixed_six_holm_separate_metrics() -> None:
    raw = {family: 1.0 for family in _FAMILIES}
    raw[_FAMILIES[0]] = 0.01
    assert h40_holm_fixed_six(raw)[_FAMILIES[0]] == pytest.approx(0.06)
    raw[_FAMILIES[0]] = 0.001
    assert h40_holm_fixed_six(raw)[_FAMILIES[0]] == pytest.approx(0.006)


def test_v10_v11_family_local_max_stat() -> None:
    points = {"a": 0.1, "b": 0.2}
    vectors = {"a": np.full(10_000, 0.11), "b": np.full(10_000, 0.21)}
    adjusted = h40_family_adjusted_lcbs(points, vectors)
    assert adjusted["a"] == pytest.approx(0.09)
    assert adjusted["b"] == pytest.approx(0.19)


def test_v09_marginal_metric_nulls_are_independent() -> None:
    vector = np.full(10_000, 0.2)
    assert h40_marginal_p(0.2, vector, 0.1) == pytest.approx(1 / 10001)
    assert h40_marginal_p(0.2, vector, 0.2) == 1.0


def _synthetic_correction_results(
    fixture: _InvalidFixture,
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, tuple[bool, float, float, float, float]],
) -> dict[str, Any]:
    """Exercise production correction/selection using synthetic metric vectors."""
    import btc_quant_agent.h40.discovery_evidence as module

    slots = {
        slot.structural_configuration_hash: slot
        for slot in materialize_h40_search_space_production().slots
    }
    candidates = {
        entry.structural_configuration_hash: module._LoadedCandidate(
            entry, slots[entry.structural_configuration_hash], {}, (), (), True,
            module.H40DiscoveryCoverageAudit(0, 40, False, True).to_dict(),
        )
        for entry in fixture.entries
    }
    monkeypatch.setattr(module, "_geometry_rows", lambda _: {})
    monkeypatch.setattr(
        fixture.verifier, "_metric_starts", lambda candidate, metric_id, manifest: np.zeros((10_000, 13), dtype=np.int64),
    )

    def science(candidate: Any, geometry: Any, starts: Any) -> Any:
        cid = candidate.entry.structural_configuration_hash
        hard, precision, net, precision_center, net_center = overrides.get(
            cid, (False, 0.6, 0.01, 0.0, 0.0),
        )
        return module._CandidateScience(
            hard, precision, net,
            np.full(10_000, precision + precision_center),
            np.full(10_000, net + net_center), 0.5,
            module.H40DiscoveryCoverageAudit(0, 40, False, True),
        )

    monkeypatch.setattr(module, "_candidate_science", science)
    fixture.verifier._evaluate_candidates(
        candidates, fixture.evidence.correction_input_evidence_manifest_hash,
    )
    return dict(fixture.verifier._verified)


def test_v12_failed_member_stays_in_family_maxstat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = _invalid_fixture(tmp_path)
    d1 = [entry.structural_configuration_hash for entry in fixture.entries if entry.family_id == "D1_TREND_CONTINUATION"]
    overrides = {
        d1[0]: (True, 0.7, 0.03, 0.0, 0.0),
        d1[1]: (False, 0.6, 0.01, 0.0, 1.0),
    }
    results = _synthetic_correction_results(fixture, monkeypatch, overrides)
    assert float(results[d1[0]].adjusted_lcb_net_expectancy) == pytest.approx(-0.97)
    assert results[d1[1]].hard_gates_passed is False


def test_v13_representative_tie_uses_structural_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    d1 = [entry.structural_configuration_hash for entry in fixture.entries if entry.family_id == "D1_TREND_CONTINUATION"]
    results = _synthetic_correction_results(fixture, monkeypatch, {
        d1[0]: (True, 0.7, 0.03, 0.0, 0.0),
        d1[1]: (True, 0.7, 0.03, 0.0, 0.0),
    })
    assert results[d1[0]].hard_gates_passed is True
    assert results[d1[1]].hard_gates_passed is False


@pytest.mark.parametrize("failed_metric", ["PRECISION", "NET_EXPECTANCY"])
def test_v14_v16_both_metric_holm_controls_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_metric: str,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    d1 = [entry.structural_configuration_hash for entry in fixture.entries if entry.family_id == "D1_TREND_CONTINUATION"]
    precision = 0.5 if failed_metric == "PRECISION" else 0.7
    net = 0.0 if failed_metric == "NET_EXPECTANCY" else 0.03
    results = _synthetic_correction_results(fixture, monkeypatch, {
        d1[0]: (True, precision, net, 0.0, 0.0),
    })
    assert results[d1[0]].hard_gates_passed is False


def test_v09_v10_v11_metric_and_family_corrections_are_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _invalid_fixture(tmp_path)
    d1 = [entry.structural_configuration_hash for entry in fixture.entries if entry.family_id == "D1_TREND_CONTINUATION"]
    d2 = [entry.structural_configuration_hash for entry in fixture.entries if entry.family_id == "D2_BREAKOUT_CONTINUATION"]
    results = _synthetic_correction_results(fixture, monkeypatch, {
        d1[0]: (True, 0.7, 0.03, 0.02, 0.01),
        d2[0]: (True, 0.7, 0.03, 5.0, 7.0),
    })
    assert float(results[d1[0]].adjusted_lcb_precision) == pytest.approx(0.68)
    assert float(results[d1[0]].adjusted_lcb_net_expectancy) == pytest.approx(0.02)
    assert float(results[d2[0]].adjusted_lcb_precision) == pytest.approx(-4.3)
    assert float(results[d2[0]].adjusted_lcb_net_expectancy) == pytest.approx(-6.97)
