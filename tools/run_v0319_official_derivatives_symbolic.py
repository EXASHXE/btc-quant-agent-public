from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow.parquet as pq

from btc_quant_agent.data.official_derivatives_features import (
    NEW_FEATURE_IDS,
    OfficialHourlyInputs,
    build_official_derivatives_features,
    feature_availability_audit,
)
from btc_quant_agent.symbolic_alpha.dsl import Operator
from btc_quant_agent.symbolic_alpha.evaluate import (
    EvaluationFirewall,
    evaluate_formula,
    forward_returns,
)
from btc_quant_agent.symbolic_alpha.gates import (
    CandidateGateConfig,
    FormulaGateEvidence,
    GateStatus,
    evaluate_candidate_gates,
)
from btc_quant_agent.symbolic_alpha.proposal import (
    ProposalConstraints,
    RandomGrammarProposalEngine,
)
from btc_quant_agent.symbolic_alpha.registry import FeatureDefinition, formula_entry, write_registry
from btc_quant_agent.symbolic_alpha.search import run_discovery_search
from btc_quant_agent.symbolic_alpha.vm import FormulaVM, Series

if __package__:
    from tools.run_historical_symbolic_factory import (
        _forward_snapshot,
        _indices,
        _multiple_testing,
        build_features,
    )
else:
    from run_historical_symbolic_factory import (  # type: ignore[no-redef]
        _forward_snapshot,
        _indices,
        _multiple_testing,
        build_features,
    )


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_new_features(path: Path) -> tuple[list[int], dict[str, Series], dict[str, Any]]:
    records = [OfficialHourlyInputs(**row) for row in pq.read_table(path).to_pylist()]
    features = build_official_derivatives_features(records)
    return (
        [row.timestamp_ms for row in records],
        features,
        feature_availability_audit(features, records),
    )


def _correlations(
    formulas: list[Any], features: dict[str, Series], indices: range
) -> dict[str, float]:
    vm = FormulaVM()
    signals: list[np.ndarray[Any, Any]] = []
    for formula in formulas:
        result = vm.execute(formula, features)
        if result.failure or result.values is None:
            raise RuntimeError(f"frozen candidate VM failed: {result.failure}")
        signals.append(
            np.asarray(
                [
                    np.nan if result.values[index] is None else np.sign(float(result.values[index]))
                    for index in indices
                ]
            )
        )
    output: dict[str, float] = {}
    for left, formula in enumerate(formulas):
        correlations: list[float] = []
        for right in range(len(formulas)):
            if left == right:
                continue
            valid = np.isfinite(signals[left]) & np.isfinite(signals[right])
            if (
                np.sum(valid) > 2
                and np.std(signals[left][valid]) > 0
                and np.std(signals[right][valid]) > 0
            ):
                correlations.append(
                    abs(float(np.corrcoef(signals[left][valid], signals[right][valid])[0, 1]))
                )
        output[formula.formula_hash] = max(correlations, default=0.0)
    return output


def run(root: Path, data_root: Path, artifact: Path, preregistration_sha: str) -> dict[str, Any]:
    protocol_path = root / "configs/research/v0.3.19_official_derivatives_symbolic_protocol.json"
    protocol = json.loads(protocol_path.read_text())
    raw_manifest_path = data_root / "raw_data_manifest.json"
    raw_manifest = json.loads(raw_manifest_path.read_text())
    if (
        raw_manifest["request_count"] != 366
        or raw_manifest["verified_count"] != 366
        or raw_manifest["missing_count"]
    ):
        raise RuntimeError("formal run requires all 366 official archives checksum-verified")
    if raw_manifest["final_holdout_rows"] != 0:
        raise PermissionError("Final Holdout archive rows are forbidden")
    artifact.mkdir(parents=True, exist_ok=True)
    _write(artifact / "raw_data_manifests/raw_data_manifest.json", raw_manifest)
    start_forward = _forward_snapshot()
    timestamps, old_features, close, old_audit = build_features(
        root / "data/research/BTCUSDT", root / "data/research/BTCUSDT_SPOT"
    )
    new_timestamps, new_features, new_audit = _load_new_features(
        data_root / "hourly_inputs.parquet"
    )
    if timestamps != new_timestamps:
        raise RuntimeError(
            "new official feature timeline does not match canonical research timeline"
        )
    features = {**old_features, **new_features}
    returns = forward_returns(close, protocol["labels"]["primary_horizon_hours"])
    lookbacks = {
        **{name: 24 if "24H" in name else 4 if "4H" in name else 1 for name in old_features},
        **{
            name: 24 if "Z_24H" in name else 4 if "CHANGE_4H" in name else 1
            for name in new_features
        },
    }
    definitions = {
        name: FeatureDefinition(
            name,
            "OFFICIAL_HISTORICAL_TIMESTAMPED"
            if name in NEW_FEATURE_IDS
            else "CANONICAL_HISTORICAL",
            lookbacks[name],
            "available only after the complete source hour closed; missing remains unavailable",
        )
        for name in features
    }
    search_config = protocol["formula_search"]
    constraints = ProposalConstraints(
        maximum_tokens=search_config["maximum_postfix_tokens"],
        maximum_lookback=search_config["maximum_total_lookback_hours"],
        windows=tuple(search_config["allowed_window_parameters"]),
        operators=tuple(Operator(name) for name in search_config["allowed_operators"]),
        required_features=NEW_FEATURE_IDS,
    )
    discovery_indices = _indices(timestamps, protocol["scope"]["discovery_window"], 8)
    validation_indices = _indices(timestamps, protocol["scope"]["validation_window"], 8)
    pseudo_indices = _indices(timestamps, protocol["scope"]["pseudo_forward_window"], 8)
    search = run_discovery_search(
        RandomGrammarProposalEngine(),
        search_config["valid_unique_formula_budget"],
        lookbacks,
        search_config["seed"],
        constraints,
        features,
        returns,
        discovery_indices,
        search_config["complexity_penalty_per_operator"],
    )
    if search.accounting["formula_evaluations"] != search_config["reward_evaluation_budget"]:
        raise RuntimeError("reward evaluation budget accounting mismatch")
    usage = {name: 0 for name in sorted(NEW_FEATURE_IDS)}
    for item in search.ranked:
        for name in set(item.formula.input_features) & NEW_FEATURE_IDS:
            usage[name] += 1
    selected = list(search.ranked[: search_config["top_k_selected_for_validation"]])
    gate_config = CandidateGateConfig.from_dict(protocol["candidate_gate"])
    cost = (gate_config.fees_bps_round_trip + gate_config.slippage_bps_round_trip) / 10_000
    validation: list[dict[str, Any]] = []
    for item in selected:
        metrics = evaluate_formula(
            item.formula,
            features,
            returns,
            validation_indices,
            cost_rate=cost,
            bootstrap_seed=search_config["seed"],
            bootstrap_resamples=protocol["resampling_and_inference"]["bootstrap_resamples"],
            bootstrap_block_hours=protocol["resampling_and_inference"]["bootstrap_block_hours"],
            sample_step_hours=protocol["scope"]["sample_step_hours"],
        )
        validation.append(
            {"formula": item.formula, "discovery": item.metrics, "validation": metrics}
        )
    validation.sort(
        key=lambda row: (-(row["validation"].net_mean_return or -1e9), row["formula"].formula_hash)
    )
    frozen = validation[: search_config["top_k_frozen_before_pseudo_forward"]]
    firewall = EvaluationFirewall()
    hashes = firewall.freeze_top_k([row["formula"] for row in frozen])
    freeze = {
        "preregistration_sha": preregistration_sha,
        "formula_hashes": hashes,
        "selection_rule": "top validation net mean after frozen costs; no pseudo-forward viewed",
        "pseudo_forward_touches_before_freeze": 0,
    }
    _write(artifact / "pseudo_forward_top_k_freeze.json", freeze)
    correlations = _correlations([row["formula"] for row in frozen], features, validation_indices)
    for row in frozen:
        firewall.authorize_pseudo_forward(row["formula"])
        row["pseudo_forward"] = evaluate_formula(
            row["formula"],
            features,
            returns,
            pseudo_indices,
            cost_rate=cost,
            bootstrap_seed=search_config["seed"] + 1,
            bootstrap_resamples=protocol["resampling_and_inference"]["bootstrap_resamples"],
            bootstrap_block_hours=protocol["resampling_and_inference"]["bootstrap_block_hours"],
            sample_step_hours=protocol["scope"]["sample_step_hours"],
        )
    multiple = _multiple_testing(
        [item.formula for item in search.ranked],
        features,
        returns,
        discovery_indices,
        search_config["seed"],
        block_hours=protocol["resampling_and_inference"]["bootstrap_block_hours"],
        sample_step_hours=protocol["scope"]["sample_step_hours"],
        permutations=protocol["resampling_and_inference"]["permutations"],
    )
    results: list[dict[str, Any]] = []
    for row in frozen:
        discovery = row["discovery"]
        validation_metrics = row["validation"]
        pseudo = row["pseudo_forward"]
        evidence = FormulaGateEvidence(
            discovery.event_count,
            validation_metrics.event_count,
            pseudo.event_count,
            pseudo.long_fraction,
            discovery.net_mean_return,
            validation_metrics.net_mean_return,
            pseudo.net_mean_return,
            validation_metrics.bootstrap_ci_low,
            pseudo.bootstrap_ci_low,
            sum(
                value is not None and value > 0
                for value in validation_metrics.chronological_fold_means
            ),
            sum(value is not None and value > 0 for value in pseudo.chronological_fold_means),
            multiple["passed_0_05"],
            correlations[row["formula"].formula_hash],
        )
        gate_audit = evaluate_candidate_gates(gate_config, evidence, None)
        if all(item.status == GateStatus.PASS for item in gate_audit.results[:15]):
            raise RuntimeError(
                "formula survivor requires the preregistered TP/BR event replay before "
                "sandbox gates can be evaluated"
            )
        results.append(
            {
                "formula_hash": row["formula"].formula_hash,
                "formula": json.loads(row["formula"].canonical_json()),
                "new_features": sorted(set(row["formula"].input_features) & NEW_FEATURE_IDS),
                "discovery": asdict(discovery),
                "validation": asdict(validation_metrics),
                "pseudo_forward": asdict(pseudo),
                "maximum_pairwise_candidate_correlation": correlations[row["formula"].formula_hash],
                "gate_audit": {
                    "results": [asdict(item) for item in gate_audit.results],
                    "consumed_protocol_keys": gate_audit.consumed_protocol_keys,
                    "passed_all": gate_audit.passed_all,
                },
            }
        )
    registry_entries = []
    by_hash = {row["formula_hash"]: row for row in results}
    for rank, item in enumerate(search.ranked[:20], 1):
        result = by_hash.get(item.formula.formula_hash)
        registry_entries.append(
            formula_entry(
                item.formula,
                definitions,
                formula_id=f"V0319_RANDOM_{rank:03d}",
                proposal_engine="RANDOM_GRAMMAR_SEARCH_NEW_FEATURE_CONSTRAINED",
                search_run_id=artifact.name,
                search_seed=search_config["seed"],
                search_budget=search_config["reward_evaluation_budget"],
                discovery_window=protocol["scope"]["discovery_window"],
                validation_window=protocol["scope"]["validation_window"],
                pseudo_forward_window=protocol["scope"]["pseudo_forward_window"],
                metrics_by_fold=result or {"discovery": asdict(item.metrics)},
                correlation_to_existing_candidates=(result or {}).get(
                    "maximum_pairwise_candidate_correlation"
                ),
                status="FAILED_VALIDATION",
                research_eligibility=False,
            )
        )
    registry_path = root / "configs/formula_registry_v0319.json"
    write_registry(registry_path, registry_entries)
    end_forward = _forward_snapshot()
    feature_manifest = {
        "raw_manifest_path": str(raw_manifest_path),
        "raw_manifest_sha256": _digest(raw_manifest_path),
        "hourly_input_path": str(data_root / "hourly_inputs.parquet"),
        "hourly_input_sha256": raw_manifest["hourly_input_sha256"],
        "new_feature_ids": sorted(NEW_FEATURE_IDS),
        "formal_role": "OFFICIAL_HISTORICAL_TIMESTAMPED",
        "final_holdout_rows": 0,
    }
    recommendation = (
        "CONTINUE_OFFICIAL_DERIVATIVES_SYMBOLIC_NO_CANDIDATE"
        if multiple["passed_0_05"]
        else "STOP_OFFICIAL_DERIVATIVES_SYMBOLIC_FAMILY"
    )
    search_audit = {
        "preregistration_sha": preregistration_sha,
        "protocol_sha256": _digest(protocol_path),
        "accounting": search.accounting,
        "new_feature_usage_distribution": usage,
        "formal_multiple_testing_universe": search.accounting["formula_evaluations"],
        "top_20_discovery": search.audit_dict()["ranked"][:20],
        "validation_candidates": len(selected),
        "frozen_top_k": len(frozen),
        "pseudo_forward_touches": firewall.pseudo_forward_touches,
        "multiple_testing": multiple,
        "candidate_results": results,
        "candidate_exists": False,
        "provisional_shadow_started": False,
        "recommendation": recommendation,
    }
    outputs = {
        "protocol.json": protocol,
        "feature_manifest.json": feature_manifest,
        "feature_availability_audit.json": {"old": old_audit, "new": new_audit},
        "symbolic_search_audit.json": search_audit,
        "multiple_testing.json": multiple,
        "validation_results.json": [
            {"formula_hash": row["formula_hash"], "validation": row["validation"]}
            for row in results
        ],
        "pseudo_forward_results.json": [
            {"formula_hash": row["formula_hash"], "pseudo_forward": row["pseudo_forward"]}
            for row in results
        ],
        "candidate_gate_audit.json": [
            {"formula_hash": row["formula_hash"], "gate_audit": row["gate_audit"]}
            for row in results
        ],
        "sandbox_trade_results.json": {
            "status": "NOT_APPLICABLE",
            "reason": "ALL_FROZEN_CANDIDATES_FAILED_UPSTREAM_FORMULA_GATES",
            "trades": [],
        },
        "forward_status_start.json": start_forward,
        "forward_status_end.json": end_forward,
    }
    for name, payload in outputs.items():
        _write(artifact / name, payload)
    manifest = {
        "run_id": artifact.name,
        "created_at_ms": int(time.time() * 1000),
        "preregistration_sha": preregistration_sha,
        "files": {
            str(path.relative_to(artifact)): _digest(path)
            for path in sorted(artifact.rglob("*.json"))
        },
        "historical_writes_to_forward_stores": 0,
        "final_holdout_rows_loaded": 0,
    }
    _write(artifact / "artifact_manifest.json", manifest)
    return {
        "artifact": str(artifact),
        "artifact_manifest_sha256": _digest(artifact / "artifact_manifest.json"),
        "search_accounting": search.accounting,
        "multiple_testing": multiple,
        "candidate_exists": False,
        "recommendation": search_audit["recommendation"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--preregistration-sha", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(
                args.root.resolve(),
                args.data_root.resolve(),
                args.artifact.resolve(),
                args.preregistration_sha,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
