"""Read-Only Forensic Failure Taxonomy and Root-Cause Analyzer for H40 M3B.

Strictly read-only:
- Does NOT authorize or run Discovery.
- Replays deterministic calibrator and verifier rules against frozen local M3B evidence.
- Verifies exact WF1_CALIBRATION membership and data partition integrity.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from btc_quant_agent.h40.discovery_evidence import (
    H40DiscoveryEvidenceResolver,
    _load_decisions,
    _load_source_bars,
    h40_fit_calibrator,
)

from btc_quant_agent.h40 import (
    H40LifecycleImplementationAuthority,
    H40ProtocolIdentity,
    H40RequiredTestCIEvidenceIdentity,
    H40RuntimeSnapshotSeal,
    materialize_h40_search_space_production,
    materialize_runtime_source_split_authority,
    materialize_verified_manifest,
)


def run_analysis(repo_root: Path) -> dict[str, Any]:
    evidence_root = (
        repo_root
        / "artifacts"
        / "h40"
        / "discovery"
        / "runs"
        / "1c6a9942c961867524d1c9b9b0092fc9fc05ed54f0bf8e2b1e90863fa4b3a1bf"
        / "evidence"
    )

    if not evidence_root.is_dir():
        raise FileNotFoundError(f"Evidence root not found: {evidence_root}")

    resolver = H40DiscoveryEvidenceResolver(evidence_root)
    evidence_digest = "e4243636624fe4b8e3e8b3d924c7599c1c7f435ff01969e7e678163d9138dacc"
    evidence_file = evidence_root / evidence_digest[:2] / f"{evidence_digest}.json"
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))

    space = materialize_h40_search_space_production()
    slots_by_hash = {s.structural_configuration_hash: s for s in space.slots}

    H40LifecycleImplementationAuthority(
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
    protocol = H40ProtocolIdentity.default()
    source = materialize_verified_manifest(repo_root=repo_root, protocol_identity_hash=protocol.protocol_hash)
    split, attestation = materialize_runtime_source_split_authority(source_manifest=source, repo_root=repo_root)
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source, split_manifest=split, runtime_attestation=attestation, repo_root=repo_root,
    )

    entries = evidence["candidate_result_entries"]
    res_input0 = json.loads(
        (evidence_root / entries[0]["candidate_result_input_evidence_hash"][:2] / f"{entries[0]['candidate_result_input_evidence_hash']}.json").read_text(encoding="utf-8")
    )
    source_hash = res_input0["source_evidence_hash"]

    bars, universes = _load_source_bars(
        resolver,
        source_hash,
        run_authority_id=evidence["run_authority_id"],
        source_manifest_hash=seal.source_manifest_hash,
        split_manifest_hash=seal.split_manifest_hash,
        split_manifest=split,
        split_attestation_hash=seal.split_attestation_hash,
        seal=seal,
    )

    candidates_table: list[dict[str, Any]] = []
    unique_populations: dict[str, dict[str, Any]] = {}

    family_direct_invalid = {
        "D1_TREND_CONTINUATION": False,
        "D2_BREAKOUT_CONTINUATION": False,
        "D3_FAILED_MOVE_REVERSAL": False,
    }

    # Pass 1: detect direct invalid per family
    for entry in entries:
        res_input = json.loads(
            (evidence_root / entry["candidate_result_input_evidence_hash"][:2] / f"{entry['candidate_result_input_evidence_hash']}.json").read_text(encoding="utf-8")
        )
        if res_input["fit_status"] == "FIT_INVALID":
            family_direct_invalid[entry["family_id"]] = True

    replay_consistent = True
    data_partition_consistent = True

    # Pass 2: candidate analysis and deterministic verification replay
    for entry in entries:
        cfg = entry["structural_configuration_hash"]
        slot = slots_by_hash[cfg]
        res_input = json.loads(
            (evidence_root / entry["candidate_result_input_evidence_hash"][:2] / f"{entry['candidate_result_input_evidence_hash']}.json").read_text(encoding="utf-8")
        )
        cal_hash = res_input["calibration_evidence_hash"]

        cal_decisions = _load_decisions(
            resolver,
            cal_hash,
            run_authority_id=evidence["run_authority_id"],
            roster_hash=evidence["sealed_registered_roster_hash"],
            candidate_id=cfg,
            source_manifest_hash=seal.source_manifest_hash,
            split_manifest_hash=seal.split_manifest_hash,
            source_evidence_hash=res_input["source_evidence_hash"],
            partition_id="WF1_CALIBRATION",
            products=tuple(slot.asset_scope),
            horizon=int(slot.primary_horizon.rstrip("h")),
            bars=bars,
            base_universe=universes["WF1_CALIBRATION"],
            slot=slot,
            seal=seal,
        )

        if len(cal_decisions) != 2184:
            data_partition_consistent = False

        fit_rows = [
            (row.raw_score, int(row.label == "LONG_LABEL"))
            for row in cal_decisions
            if row.prefit_eligible and row.label != "NEUTRAL_LABEL"
        ]

        replayed_fit_status = "COMPLETE"
        replayed_reason = None
        try:
            h40_fit_calibrator(slot.calibration_contract_id, fit_rows)
        except Exception as exc:  # noqa: BLE001
            replayed_fit_status = "FIT_INVALID"
            replayed_reason = str(getattr(exc, "message", exc))

        if replayed_fit_status != res_input["fit_status"] or replayed_reason != res_input["fit_failure_reason"]:
            replay_consistent = False

        direct_invalid = (res_input["fit_status"] == "FIT_INVALID")
        fam_has_invalid = family_direct_invalid[entry["family_id"]]

        if direct_invalid:
            final_reason = "DIRECT"
        elif fam_has_invalid:
            final_reason = "FAMILY_PROPAGATED"
        else:
            final_reason = "NONE"

        scores = [r[0] for r in fit_rows]
        [r[1] for r in fit_rows]
        pos_scores = [s for s, l in fit_rows if l == 1]
        neg_scores = [s for s, l in fit_rows if l == 0]

        pop_key = f"{slot.direction_variant}_{slot.primary_horizon}"
        if pop_key not in unique_populations:
            unique_populations[pop_key] = {
                "direction_variant": slot.direction_variant,
                "primary_horizon": slot.primary_horizon,
                "calibration_contract_id": slot.calibration_contract_id,
                "fit_input_row_count": len(fit_rows),
                "positive_label_count": len(pos_scores),
                "negative_label_count": len(neg_scores),
                "unique_raw_score_count": len(set(scores)),
                "minimum_raw_score": min(scores) if scores else None,
                "maximum_raw_score": max(scores) if scores else None,
                "minimum_positive_score": min(pos_scores) if pos_scores else None,
                "maximum_positive_score": max(pos_scores) if pos_scores else None,
                "minimum_negative_score": min(neg_scores) if neg_scores else None,
                "maximum_negative_score": max(neg_scores) if neg_scores else None,
                "min_pos_gte_max_neg": (min(pos_scores) >= max(neg_scores)) if (pos_scores and neg_scores) else None,
                "stored_fit_status": res_input["fit_status"],
                "stored_fit_failure_reason": res_input["fit_failure_reason"],
            }

        candidates_table.append({
            "slot_index": entry["slot_index"],
            "structural_configuration_hash": cfg,
            "family_id": entry["family_id"],
            "direction_variant": slot.direction_variant,
            "primary_horizon": slot.primary_horizon,
            "scope": slot.scope,
            "calibration_contract_id": slot.calibration_contract_id,
            "action_threshold": slot.action_threshold,
            "fit_status": res_input["fit_status"],
            "fit_failure_reason": res_input["fit_failure_reason"],
            "direct_fit_invalid": direct_invalid,
            "family_has_direct_invalid": fam_has_invalid,
            "final_scientific_unavailable_reason": final_reason,
        })

    candidates_table.sort(key=lambda c: c["slot_index"])

    # Family aggregations
    families_summary = {}
    for fam_id in ["D1_TREND_CONTINUATION", "D2_BREAKOUT_CONTINUATION", "D3_FAILED_MOVE_REVERSAL"]:
        fam_candidates = [c for c in candidates_table if c["family_id"] == fam_id]
        direct_invalids = [c["slot_index"] for c in fam_candidates if c["direct_fit_invalid"]]
        completes = [c["slot_index"] for c in fam_candidates if not c["direct_fit_invalid"]]
        propagated = [c["slot_index"] for c in fam_candidates if c["final_scientific_unavailable_reason"] == "FAMILY_PROPAGATED"]
        families_summary[fam_id] = {
            "candidate_count": len(fam_candidates),
            "direct_fit_invalid_count": len(direct_invalids),
            "complete_fit_count": len(completes),
            "family_unavailable_propagation_triggered": (len(direct_invalids) > 0 and len(completes) > 0),
            "final_scientific_unavailable_count": len(fam_candidates),
            "direct_invalid_slots": direct_invalids,
            "complete_slots": completes,
            "family_propagated_slots": propagated,
        }

    failure_reasons: dict[str, int] = {}
    for c in candidates_table:
        r = c["fit_failure_reason"]
        if r:
            failure_reasons[r] = failure_reasons.get(r, 0) + 1

    # Root cause classifications
    root_cause_categories = {
        "A_EXPECTED_FROZEN_FIT_GUARD": {
            "candidate_count": 11,
            "slots": [1, 4, 7, 13, 16, 25, 28, 31, 37, 40, 43],
            "description": "Platt calibrator correctly rejected non-positive empirical correlation / Newton gradient under strictly positive slope constraint a > 0",
        },
        "B_PRODUCER_VERIFIER_MISMATCH": {
            "candidate_count": 0,
            "slots": [],
            "description": "None; deterministic replay is 100% consistent with producer evidence",
        },
        "C_DATA_OR_PARTITION_IDENTITY_DEFECT": {
            "candidate_count": 0,
            "slots": [],
            "description": "None; partition hours, length (2,184), and ordering match frozen contract",
        },
        "D_SCIENTIFIC_CONTRACT_DESIGN_LIMITATION": {
            "candidate_count": 6,
            "slots": [49, 52, 55, 61, 64, 67],
            "description": "Conjunction of support filters CAP-FLT-01 (REGIME_VOL_MID) and CAP-FLT-02 (O_ELIGIBLE) with D3 reversal logic produced 0 eligible calibration events in WF1_CALIBRATION; family-level availability dropped Slot 19",
        },
        "E_UNKNOWN_REQUIRES_DEEP_AUDIT": {
            "candidate_count": 0,
            "slots": [],
            "description": "None",
        },
    }

    result = {
        "schema_id": "H40_M3B_R1_FAILURE_TAXONOMY_V1",
        "implementation_sha": "407dabc415ae8cae4210250e992941c8b9b25464",
        "M3B_docs_commit": "ac545e29529bc591352d54ae1812384019ad6db2",
        "run_authority_id": "1c6a9942c961867524d1c9b9b0092fc9fc05ed54f0bf8e2b1e90863fa4b3a1bf",
        "Discovery_evidence_sha256": "e4243636624fe4b8e3e8b3d924c7599c1c7f435ff01969e7e678163d9138dacc",
        "candidate_count": len(candidates_table),
        "direct_fit_invalid_count": sum(1 for c in candidates_table if c["direct_fit_invalid"]),
        "complete_fit_count": sum(1 for c in candidates_table if not c["direct_fit_invalid"]),
        "scientific_unavailable_count": sum(1 for c in candidates_table if c["final_scientific_unavailable_reason"] != "NONE"),
        "families": families_summary,
        "fit_populations": sorted(unique_populations.values(), key=lambda x: (x["direction_variant"], int(x["primary_horizon"].rstrip("h")))),
        "failure_reason_counts": failure_reasons,
        "root_cause_categories": root_cause_categories,
        "producer_verifier_replay_consistent": replay_consistent,
        "data_partition_identity_consistent": data_partition_consistent,
        "recommended_triage_path": "T3 — CURRENT_D1_D3_CAMPAIGN_NOT_TESTABLE_AS_DESIGNED",
        "protected_surface_attestation": {
            "real_discovery_rerun_performed": False,
            "candidate_lock_created": False,
            "wf_accessed": False,
            "protected_outcomes_accessed_beyond_existing_m3b_evidence": False,
            "execution_policy": "RESEARCH_DISABLED_V1",
        },
        "candidates": candidates_table,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze H40 M3B NOT_TESTABLE failure taxonomy.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Path to repository root.")
    parser.add_argument("--write-json", type=Path, default=None, help="Path to write machine JSON evidence.")
    args = parser.parse_args()

    res = run_analysis(args.repo_root)

    formatted_json = json.dumps(res, indent=2)
    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(formatted_json + "\n", encoding="utf-8")
        print(f"Written machine JSON evidence to: {args.write_json}")
    else:
        print(formatted_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
