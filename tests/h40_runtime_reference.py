"""Slow scientific reference copied verbatim from accepted 16dc102 (test-only)."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast

import numpy as np

from btc_quant_agent.h40 import discovery_evidence as _accepted_helpers
from btc_quant_agent.h40 import discovery_producer as _producer_helpers

# Unchanged helpers remain shared; all refactored reconstruction paths below
# are frozen copies of the accepted parent, including the complete producer loop.
from btc_quant_agent.h40.discovery_evidence import (
    DISCOVERY_PROVENANCE_CONTRACT_HASH,
    H40CandidateResultEntry,
    H40DiscoveryResultEvidence,
    H40GuardError,
    H40ReasonCode,
    _Bar,
    _compute_d1,
    _compute_d2,
    _compute_d3,
    _compute_o_range_scalar,
    _compute_r_vol_scalar,
    _Decision,
    _empirical_percentile,
    _fail,
    _median,
    _partition_bounds,
    compute_protocol_authority_hash,
    materialize_h40_search_space_production,
)

H40DiscoveryEvidenceWriter = _producer_helpers.H40DiscoveryEvidenceWriter
H40DiscoveryProductionResult = _producer_helpers.H40DiscoveryProductionResult
lifecycle = _producer_helpers.lifecycle
_policies = _producer_helpers._policies
_PREFIT_CACHE = {}
_TRAINING_REFS = {}
def _get_training_refs(
    source_evidence_hash: str,
    product: str,
    bars: Mapping[tuple[datetime, str], _Bar],
) -> dict[str, list[tuple[datetime, float]]]:
    cache_key = (source_evidence_hash, product)
    if cache_key in _TRAINING_REFS:
        return _TRAINING_REFS[cache_key]

    rv_list: list[tuple[datetime, float]] = []
    exp_list: list[tuple[datetime, float]] = []
    product_times = sorted([t for t, p in bars if p == product])
    train_end = datetime(2022, 10, 31, tzinfo=UTC)

    for dt in product_times:
        if dt >= train_end:
            break
        rv = _compute_r_vol_scalar(bars, dt, product)
        if rv is not None and math.isfinite(rv):
            rv_list.append((dt, rv))
        exp = _compute_o_range_scalar(bars, dt, product)
        if exp is not None and math.isfinite(exp):
            exp_list.append((dt, exp))

    refs = {"R_VOL": rv_list, "O_RANGE": exp_list}
    _TRAINING_REFS[cache_key] = refs
    return refs

def _reconstruct_prefit_cached(
    *,
    candidate_id: str,
    slot: Any | None,
    partition_id: str,
    t: datetime,
    product: str,
    bars: Mapping[tuple[datetime, str], _Bar],
    source_evidence_hash: str,
) -> tuple[float, str, str, str]:
    cache_key = (
        compute_protocol_authority_hash(),
        DISCOVERY_PROVENANCE_CONTRACT_HASH,
        source_evidence_hash,
        candidate_id,
        partition_id,
        t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        product,
    )
    if cache_key in _PREFIT_CACHE:
        return _PREFIT_CACHE[cache_key]

    dir_contract = str(getattr(slot, "direction_contract_id", None) or getattr(slot, "direction_variant", "D1_V1_RETURN_4H"))
    if "D1_V1" in dir_contract or dir_contract == "D1_V1_RETURN_4H":
        score = _compute_d1(bars, t, product, 4)
    elif "D1_V2" in dir_contract or dir_contract == "D1_V2_RETURN_12H":
        score = _compute_d1(bars, t, product, 12)
    elif "D2_V1" in dir_contract or dir_contract == "D2_V1_BREAKOUT_24H":
        score = _compute_d2(bars, t, product, 24)
    elif "D2_V2" in dir_contract or dir_contract == "D2_V2_BREAKOUT_72H":
        score = _compute_d2(bars, t, product, 72)
    elif "D3_V1" in dir_contract or dir_contract == "D3_V1_FAILED_BREAK_24H":
        score = _compute_d3(bars, t, product, 24)
    elif "D3_V2" in dir_contract or dir_contract == "D3_V2_FAILED_BREAK_72H":
        score = _compute_d3(bars, t, product, 72)
    else:
        _fail(f"unsupported direction contract '{dir_contract}'", H40ReasonCode.NOT_TESTABLE)

    training_refs = _get_training_refs(source_evidence_hash, product, bars)
    rv_series = training_refs["R_VOL"]
    exp_series = training_refs["O_RANGE"]

    if partition_id == "WF1_TRAIN":
        rv_sample = [v for dt, v in rv_series if dt < t]
        exp_sample = [v for dt, v in exp_series if dt < t]
    else:
        rv_sample = [v for _, v in rv_series]
        exp_sample = [v for _, v in exp_series]

    rv_val = _compute_r_vol_scalar(bars, t, product)
    if rv_val is None or len(rv_sample) < 60:
        regime_state = "REGIME_UNAVAILABLE"
    else:
        p_vol = _empirical_percentile(rv_sample, rv_val)
        if p_vol < 0.40:
            regime_state = "REGIME_VOL_LOW"
        elif p_vol < 0.60:
            regime_state = "REGIME_VOL_MID"
        else:
            regime_state = "REGIME_VOL_HIGH"

    exp_val = _compute_o_range_scalar(bars, t, product)
    if exp_val is None or len(exp_sample) < 60:
        opportunity_state = "O_NONE"
    else:
        p_opp = _empirical_percentile(exp_sample, exp_val)
        if p_opp < 0.60:
            opportunity_state = "O_NONE"
        elif p_opp < 0.80:
            opportunity_state = "O_WATCH"
        else:
            opportunity_state = "O_ELIGIBLE"

    sec_filter = str(getattr(slot, "secondary_filter_contract_id", "NONE") or "NONE")
    if sec_filter not in ("NONE", ""):
        _fail(f"unsupported secondary filter contract '{sec_filter}'", H40ReasonCode.NOT_TESTABLE)
    secondary_filter_state = "PASS"

    result = (score, regime_state, opportunity_state, secondary_filter_state)
    _PREFIT_CACHE[cache_key] = result
    return result

def _derive_source_decision(
    *, candidate_id: str, slot: Any, partition_id: str,
    timestamp: datetime, product: str, horizon: int,
    bars: Mapping[tuple[datetime, str], _Bar], source_evidence_hash: str,
) -> _Decision:
    """Shared frozen causal prefit and source-local outcome reconstruction."""
    score, regime, opportunity, secondary = _reconstruct_prefit_cached(
        candidate_id=candidate_id, slot=slot, partition_id=partition_id,
        t=timestamp, product=product, bars=bars, source_evidence_hash=source_evidence_hash,
    )
    _, _, support_end = _partition_bounds(partition_id)
    first = bars.get((timestamp, product))
    exit_time = timestamp + timedelta(hours=horizon - 1)
    if first is None or exit_time >= support_end:
        _fail("missing source-bound entry or unauthorized support endpoint", H40ReasonCode.NOT_TESTABLE)
    path = tuple(bars.get((timestamp + timedelta(hours=index), product)) for index in range(horizon))
    if any(bar is None for bar in path):
        _fail("missing source-local outcome-support hour", H40ReasonCode.NOT_TESTABLE)
    complete_path = tuple(cast(_Bar, bar) for bar in path)
    last = complete_path[-1]
    return _Decision(
        timestamp, product, regime, opportunity, score, secondary, None, None,
        math.log(last.close / first.open), None, first.open, last.close, complete_path,
    )

def _geometry_pass(
    row: _Decision,
    slot: Any,
    owners: Mapping[str, Mapping[tuple[str, str, int, datetime, str, str], tuple[float, float]]],
) -> bool:
    owner = str(slot.direction_contract_id)
    scope = str(slot.scope)
    horizon = int(slot.primary_horizon.rstrip("h"))
    side = row.proposed_action
    records = owners.get(owner, {})
    for level in range(4):
        subset = [
            values for (_, record_scope, record_horizon, _, _, record_side), values in records.items()
            if (
                (level >= 3 or record_scope == scope)
                and (level >= 2 or record_horizon == horizon)
                and (level >= 1 or record_side == side)
            )
        ]
        if len(subset) >= 30:
            mfe = _median([item[0] for item in subset])
            mae = _median([item[1] for item in subset])
            return mfe >= 1.5 * 0.0012 and mfe / max(mae, 0.0012) >= 1.25
    return False

science = SimpleNamespace(**{k: v for k, v in vars(_accepted_helpers).items() if not k.startswith('__')})
science._derive_source_decision = _derive_source_decision
science._geometry_pass = _geometry_pass

def produce(self) -> H40DiscoveryProductionResult:
    self._validate_authority()
    writer = H40DiscoveryEvidenceWriter(self.approved_evidence_root)
    dependencies: set[str] = set()

    def store(payload: Mapping[str, Any]) -> str:
        digest = writer.write(payload)
        dependencies.add(digest)
        return digest

    common = {"run_authority_id": self.run_authority.run_authority_id,
              "sealed_registered_roster_hash": self.seal.sealed_registered_roster_hash,
              "policies": _policies()}
    lineage = {"source_manifest_hash": self.seal.source_manifest_hash,
               "split_manifest_hash": self.seal.split_manifest_hash}
    source, bars, universes = self._source()
    source_hash = store(source)
    roster = self.seal.roster
    slots = {slot.structural_configuration_hash: slot
             for slot in materialize_h40_search_space_production().slots}
    groups: dict[str, list[str]] = {family: [] for family in science._FAMILIES}
    for item in roster:
        slot = slots[item.structural_configuration_hash]
        if tuple(slot.asset_scope) != ("ETHUSDT",) or len(slot.family_combination) != 1:
            _fail("producer roster contains an unsupported scientific slot")
        groups[item.family_id].append(item.structural_configuration_hash)
    correction_hash = store({
        **common, **lineage, "schema_id": "H40_P3B_DISCOVERY_CORRECTION_MANIFEST_V1",
        "discovery_authorization_receipt_hash": self.authorization_receipt.receipt_sha256,
        "materialized_run_authority_hash": self.seal.materialized_run_authority_hash,
        "discovery_partition": "WF1_CALIBRATION",
        "discovery_selection_correction_contract_hash": lifecycle.DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
        "candidate_configuration_hashes": [item.structural_configuration_hash for item in roster],
        "metric_universes": {"PRECISION": groups, "NET_EXPECTANCY": groups},
    })
    decisions = {
        item.structural_configuration_hash: {
            partition: tuple(science._derive_source_decision(
                candidate_id=item.structural_configuration_hash,
                slot=slots[item.structural_configuration_hash], partition_id=partition,
                timestamp=t, product=product,
                horizon=int(slots[item.structural_configuration_hash].primary_horizon.rstrip("h")),
                bars=bars, source_evidence_hash=source_hash,
            ) for t, product in keys)
            for partition, keys in universes.items()
        } for item in roster
    }
    geometry = science._geometry_training_rows([
        (slots[item.structural_configuration_hash], decisions[item.structural_configuration_hash]["WF1_TRAIN"])
        for item in roster
    ])
    entries: list[H40CandidateResultEntry] = []
    for item in roster:
        candidate_id = item.structural_configuration_hash
        slot = slots[candidate_id]
        candidate_common = {**common, "structural_configuration_hash": candidate_id}
        rows = decisions[candidate_id]
        fit = None
        reason = None
        try:
            fit = science.h40_fit_calibrator(slot.calibration_contract_id, [
                (row.raw_score, int(row.label == "LONG_LABEL"))
                for row in rows["WF1_CALIBRATION"] if row.prefit_eligible and row.label != "NEUTRAL_LABEL"
            ])
        except H40GuardError as exc:
            if exc.reason_code != H40ReasonCode.NOT_TESTABLE:
                raise
            reason = exc.message
        status = "COMPLETE" if fit is not None else "FIT_INVALID"
        calibrated: list[science._Decision] = []
        for row in rows["WF1_CALIBRATION"]:
            probability = None
            action = "NO_TRADE"
            net = None
            if fit is not None and row.prefit_eligible:
                probability = science.h40_predict_calibrated(fit, row.raw_score)
                if science._geometry_pass(row, slot, geometry):
                    action = science.h40_side_preserving_action(row.raw_score, probability, slot.action_threshold)
                if action != "NO_TRADE":
                    net = science.h40_proxy_net_return(action, str(row.p0), str(row.ch))[1]
            calibrated.append(replace(row, supplied_p_up=probability, supplied_action=action, supplied_r_net=net))
        rows["WF1_CALIBRATION"] = tuple(calibrated)
        decision_hashes = {partition: store({
            **candidate_common, **lineage, "schema_id": "H40_P3B_RAW_DECISIONS_V2",
            "source_evidence_hash": source_hash, "partition_id": partition,
            "provenance_contract_hash": lifecycle.DISCOVERY_PROVENANCE_CONTRACT_HASH,
            "rows": [{
                "timestamp": row.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"), "product": row.product,
                "p_up": None if row.supplied_p_up is None else repr(row.supplied_p_up),
                "final_action": row.supplied_action, "r_h": repr(row.r_h),
                "r_net": None if row.supplied_r_net is None else repr(row.supplied_r_net),
            } for row in partition_rows],
        }) for partition, partition_rows in rows.items()}
        input_lineage = {"source_evidence_hash": source_hash,
                         "training_evidence_hash": decision_hashes["WF1_TRAIN"],
                         "calibration_evidence_hash": decision_hashes["WF1_CALIBRATION"]}
        audit = None if fit is None else science.h40_discovery_coverage_audit(
            sum(row.supplied_action in ("LONG", "SHORT") for row in calibrated), len(calibrated),
        ).to_dict()
        gates = {gate: store({
            **candidate_common, **input_lineage, "schema_id": "H40_P3B_HARD_GATE_INPUT_V1",
            "gate_id": gate, "audit": audit if gate == "COVERAGE" else None,
        }) for gate in sorted(science._HARD_GATES)}
        metrics: dict[str, str] = {}
        for metric in ("PRECISION", "NET_EXPECTANCY"):
            payload: dict[str, Any] = {**candidate_common, "metric_id": metric,
                       "correction_manifest_hash": correction_hash, "fit_status": status}
            if fit is None:
                payload.update(schema_id="H40_P3B_INVALID_METRIC_INPUT_V1", fit_failure_reason=reason)
            else:
                seed = science.h40_bootstrap_seed(candidate_id, metric)
                low, high, _ = science._partition_bounds("WF1_CALIBRATION")
                hours = int((high - low).total_seconds() // 3600)
                _, matrix_hash = science.h40_bootstrap_starts(seed.seed, hours)
                payload.update(
                    schema_id="H40_P3B_METRIC_BOOTSTRAP_V1",
                    calibration_evidence_hash=input_lineage["calibration_evidence_hash"],
                    seed_identity_policy_id=science._POLICIES["seed_identity"][0],
                    seed_identity_policy_hash=science._POLICIES["seed_identity"][1],
                    bootstrap_start_sampler_policy_id=science._POLICIES["bootstrap_start_sampler"][0],
                    bootstrap_start_sampler_policy_hash=science._POLICIES["bootstrap_start_sampler"][1],
                    protocol_id=compute_protocol_authority_hash(), candidate_id=candidate_id,
                    partition_id="WF1_CALIBRATION", canonical_seed_preimage=seed.canonical_seed_preimage,
                    seed_digest_sha256=seed.seed_digest_sha256, raw_u64=seed.raw_u64, seed=seed.seed,
                    numpy_version=np.__version__, bit_generator="PCG64", H=hours, L=science._L,
                    S=hours-science._L+1, B=math.ceil(hours/science._L), M=science._M,
                    start_matrix_hash=matrix_hash,
                )
            metrics[metric] = store(payload)
        result_hash = store({
            **candidate_common, **lineage, **input_lineage,
            "schema_id": "H40_P3B_CANDIDATE_RESULT_INPUT_V1",
            "slot_hash": item.slot_hash, "slot_index": item.slot_index,
            "fit_status": status, "fit_failure_reason": reason,
            "hard_gate_input_evidence_hashes": gates,
            "precision_input_evidence_hash": metrics["PRECISION"],
            "net_expectancy_input_evidence_hash": metrics["NET_EXPECTANCY"],
        })
        entries.append(H40CandidateResultEntry(
            candidate_result_input_evidence_hash=result_hash, complexity=len(slot.family_combination),
            family_id=item.family_id, hard_gate_input_evidence_hashes=gates,
            precision_input_evidence_hash=metrics["PRECISION"], net_expectancy_input_evidence_hash=metrics["NET_EXPECTANCY"],
            slot_hash=item.slot_hash, slot_index=item.slot_index, structural_configuration_hash=candidate_id,
        ))
    self._validate_authority()
    evidence = H40DiscoveryResultEvidence(
        candidate_result_entries=tuple(entries), correction_input_evidence_manifest_hash=correction_hash,
        created_at_utc=self.authorization_receipt.authorized_at_utc,
        discovery_authorization_receipt_hash=self.authorization_receipt.receipt_sha256,
        materialized_run_authority_hash=self.seal.materialized_run_authority_hash,
        run_authority_id=self.run_authority.run_authority_id,
        sealed_registered_roster_hash=self.seal.sealed_registered_roster_hash,
    )
    evidence_hash = store(evidence.to_dict())
    if evidence_hash != evidence.evidence_sha256:
        _fail("published Discovery evidence identity mismatch")
    return H40DiscoveryProductionResult(evidence, tuple(entries), writer.approved_root, tuple(sorted(dependencies)))
