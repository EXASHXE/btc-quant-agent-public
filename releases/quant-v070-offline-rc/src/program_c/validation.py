"""Fail-closed export contracts. Hash integrity never grants source authority."""

from __future__ import annotations

import math
from typing import Any

from .integrity import (
    B_EXPORT,
    B_ROW_HASH,
    B_SELF_HASH,
    PINS,
    RESOURCE_ROOT,
    digest,
    is_digest,
    milliseconds,
    number,
    parse,
    require,
    sha,
    without,
)
from .protocol import HOUR, OUTCOMES, load_protocol, next_review

B_SCHEMA = "V070_B_PROGRAM_C_EPISODE_EXPORT_V1"
C_SCHEMA = "C_SOURCE_NEUTRAL_EPISODE_EXPORT_V1"
EXANTE_FIELDS = (
    "strategy_version", "symbol", "direction", "regime", "volatility_bucket", "source_path_id",
    "source_facts", "source_manifest_sha256", "causal_prefix_sha256", "trigger_close_ms", "decision_ms",
    "scheduled_review_ms", "reviewed_ms", "entry_region", "structural_stop", "volatility_buffer",
    "execution_buffer", "fixed_preobservable_target_zones", "expiry_ms", "holding_horizon_hours",
    "interval_hours", "price_unit", "costs", "entry_premise", "administrative_censor_ms",
)
EPISODE_FIELDS = set(EXANTE_FIELDS) | {
    "episode_id", "decision_digest", "row_sha256", "path", "coverage_start_ms", "coverage_end_ms",
    "right_censored", "source_kind", "fixture_name",
}
FACT_FIELDS = {
    "symbol", "price_unit", "open_ms", "end_ms", "interval_hours", "closed", "revision",
    "source_event_ms", "received_ms", "available_ms", "durable_ms", "open", "high", "low", "close",
    "fact_sha256",
}
COST_FIELDS = {
    "unit", "known_at_ms", "maker_fee_each_side_bps", "taker_fee_each_side_bps", "entry_fee_mode",
    "exit_fee_mode", "spread_round_trip_bps", "entry_slippage_bps", "exit_slippage_bps",
    "funding_bps_per_cadence", "funding_cadence_hours", "carrying_bps_per_day", "financing_bps_per_day",
    "impact_bps_at_reference", "reference_notional_quote", "assumed_notional_quote", "available_capacity_quote",
    "instrument_tick", "instrument_multiplier", "instrument_type", "calibration",
}


def decision_digest(row: dict) -> str:
    return digest({key: row[key] for key in EXANTE_FIELDS})


def seal_episode(row: dict) -> dict:
    row["source_manifest_sha256"] = digest(row["source_facts"])
    row["causal_prefix_sha256"] = digest(row["source_facts"])
    row["episode_id"] = digest([row["symbol"], row["strategy_version"], row["trigger_close_ms"],
                                row["causal_prefix_sha256"]])
    row["decision_digest"] = decision_digest(row)
    row["row_sha256"] = digest(without(row, "row_sha256"))
    return row


def validate_costs(costs: Any, decision_ms: int) -> None:
    if costs is None:
        return  # Explicit UNKNOWN; cannot produce a numeric payoff/executable R.
    require(isinstance(costs, dict) and set(costs) == COST_FIELDS, "COST_FIELDS_INVALID")
    require(costs["unit"] == "BPS_OF_QUOTE_NOTIONAL" and costs["instrument_type"] == "LINEAR_QUOTE_BASE",
            "COST_OR_INSTRUMENT_UNITS_INVALID")
    require(costs["calibration"] == "UNCALIBRATED_SYNTHETIC_DEFAULT", "COST_AUTHORITY_UNVERIFIED")
    require(milliseconds(costs["known_at_ms"]) and costs["known_at_ms"] <= decision_ms,
            "FUTURE_COST_INFORMATION")
    for key in COST_FIELDS - {"unit", "known_at_ms", "entry_fee_mode", "exit_fee_mode", "calibration",
                              "instrument_type", "available_capacity_quote"}:
        require(number(costs[key]), "COST_PARAMETER_INVALID:" + key)
    for key in ["instrument_tick", "instrument_multiplier", "reference_notional_quote", "assumed_notional_quote",
                "funding_cadence_hours"]:
        require(number(costs[key], positive=True), "COST_PARAMETER_NONPOSITIVE:" + key)
    require(costs["available_capacity_quote"] is None or number(costs["available_capacity_quote"], positive=True),
            "CAPACITY_INVALID")
    require(costs["entry_fee_mode"] in {"MAKER", "TAKER"} and costs["exit_fee_mode"] in {"MAKER", "TAKER"},
            "FEE_MODE_INVALID")


def validate_fact(fact: dict, row: dict, asof_ms: int, source: bool, protocol: dict) -> None:
    require(isinstance(fact, dict) and set(fact) == FACT_FIELDS, "FACT_FIELDS_INVALID")
    require(fact["fact_sha256"] == digest(without(fact, "fact_sha256")), "FACT_HASH_INVALID")
    require(fact["symbol"] == row["symbol"] and fact["price_unit"] == "USDT_PER_BASE", "FACT_SYMBOL_OR_UNIT")
    require(fact["closed"] is True, "OPEN_BAR_FORBIDDEN")
    require(type(fact["revision"]) is int and fact["revision"] == 0, "REVISION_REQUIRES_NEW_VERSION")
    require(type(fact["interval_hours"]) is int and fact["interval_hours"] in {1, 4, 24}, "BAR_INTERVAL_INVALID")
    clocks = [fact[k] for k in ["open_ms", "end_ms", "source_event_ms", "received_ms", "available_ms", "durable_ms"]]
    require(all(milliseconds(t) for t in clocks) and clocks == sorted(clocks) and clocks[0] < clocks[1],
            "BAR_CLOCK_ORDER_INVALID")
    require(clocks[1] - clocks[0] == fact["interval_hours"] * HOUR
            and clocks[0] % (fact["interval_hours"] * HOUR) == 0, "BAR_INTERVAL_OR_ALIGNMENT")
    require(clocks[-1] <= asof_ms, "FUTURE_RECEIPT_AFTER_ASOF")
    require(fact["source_event_ms"] - fact["end_ms"] <= protocol["max_clock_drift_ms"], "CLOCK_DRIFT")
    require(fact["available_ms"] - fact["end_ms"] <= protocol["maximum_observation_staleness_ms"], "STALE_OBSERVATION")
    require(all(number(fact[k], positive=True) for k in ["open", "high", "low", "close"]), "PRICE_INVALID")
    require(fact["low"] <= min(fact["open"], fact["close"]) <= max(fact["open"], fact["close"]) <= fact["high"],
            "OHLC_CONTRADICTION")
    if source:
        require(fact["durable_ms"] <= row["decision_ms"] and fact["end_ms"] <= row["trigger_close_ms"],
                "FUTURE_SOURCE_FACT_AT_DECISION")
    else:
        require(fact["open_ms"] >= row["decision_ms"], "FUTURE_PATH_OVERLAPS_DECISION")
        require(fact["interval_hours"] == row["interval_hours"], "PATH_INTERVAL_MIXED")


def validate_episode(row: dict, envelope: dict, protocol: dict) -> None:
    require(isinstance(row, dict) and set(row) == EPISODE_FIELDS, "EPISODE_FIELDS_INVALID")
    require(row["row_sha256"] == digest(without(row, "row_sha256")), "ROW_HASH_INVALID")
    require(row["source_kind"] == envelope["source_kind"], "SOURCE_CLASS_CONTRADICTION")
    require(row["strategy_version"] == protocol["strategy_version"], "INACTIVE_STRATEGY")
    require(row["symbol"] in protocol["symbols"] and row["direction"] in {"LONG", "SHORT"}, "SYMBOL_OR_DIRECTION")
    require(row["regime"] in {"TREND_UP", "TREND_DOWN"} and row["volatility_bucket"] in {"LOW", "MEDIUM", "HIGH"},
            "REGIME_OR_VOLATILITY_STRATUM")
    require(row["price_unit"] == "USDT_PER_BASE", "PRICE_UNIT_INVALID")
    require(isinstance(row["source_path_id"], str) and bool(row["source_path_id"]), "SOURCE_PATH_ID_INVALID")
    clocks = [row[k] for k in ["trigger_close_ms", "decision_ms", "scheduled_review_ms", "expiry_ms"]]
    require(all(milliseconds(t) for t in clocks) and clocks == sorted(clocks) and clocks[1] < clocks[-1],
            "EPISODE_CLOCK_INVALID")
    require(row["scheduled_review_ms"] == next_review(row["decision_ms"]), "REVIEW_SCHEDULE_INVALID")
    require(row["reviewed_ms"] is None or (milliseconds(row["reviewed_ms"])
            and row["scheduled_review_ms"] <= row["reviewed_ms"] <= envelope["evaluation_asof_ms"]),
            "REVIEW_TIMESTAMP_INVALID")
    require(row["decision_ms"] <= envelope["evaluation_asof_ms"], "DECISION_AFTER_EVALUATION_ASOF")
    require(type(row["holding_horizon_hours"]) is int and 4 <= row["holding_horizon_hours"] <= 120,
            "HORIZON_INVALID")
    require(type(row["interval_hours"]) is int and row["interval_hours"] in {1, 4, 24}, "INTERVAL_INVALID")
    require(type(row["right_censored"]) is bool, "CENSORING_BOOLEAN_INVALID")
    require(row["administrative_censor_ms"] is None or (milliseconds(row["administrative_censor_ms"])
            and row["administrative_censor_ms"] >= row["decision_ms"]), "CENSORING_TIMESTAMP_INVALID")
    require(row["right_censored"] == (row["administrative_censor_ms"] is not None), "CENSORING_CONTRADICTION")
    require(row["entry_premise"] == "CONDITIONAL_ONLY_NOT_A_FILL", "ENTRY_EVIDENCE_INVALID")
    region, targets = row["entry_region"], row["fixed_preobservable_target_zones"]
    require(isinstance(region, list) and len(region) == 2 and all(number(x, positive=True) for x in region)
            and region[0] <= region[1], "ENTRY_REGION_INVALID")
    require(isinstance(targets, list) and bool(targets) and all(number(x, positive=True) for x in targets),
            "TARGETS_INVALID")
    require(number(row["structural_stop"], positive=True) and number(row["volatility_buffer"])
            and number(row["execution_buffer"]), "STOP_BUFFER_INVALID")
    if row["direction"] == "LONG":
        require(row["structural_stop"] < region[0] <= region[1] < min(targets), "LONG_GEOMETRY_INVALID")
    else:
        require(max(targets) < region[0] <= region[1] < row["structural_stop"], "SHORT_GEOMETRY_INVALID")
    worst_entry = region[1] if row["direction"] == "LONG" else region[0]
    require(worst_entry - 4 * abs(worst_entry - row["structural_stop"]) > 0,
            "PREDECLARED_MIRRORED_CONTROL_PRICE_NONPOSITIVE")
    validate_costs(row["costs"], row["decision_ms"])
    require(isinstance(row["source_facts"], list) and bool(row["source_facts"]), "SOURCE_PREFIX_EMPTY")
    require(row["source_manifest_sha256"] == row["causal_prefix_sha256"] == digest(row["source_facts"]),
            "CAUSAL_PREFIX_HASH_INVALID")
    require(row["episode_id"] == digest([row["symbol"], row["strategy_version"], row["trigger_close_ms"],
                                        row["causal_prefix_sha256"]]), "EPISODE_IDENTITY_INVALID")
    require(row["decision_digest"] == decision_digest(row), "DECISION_DIGEST_INVALID")
    require(isinstance(row["path"], list), "PATH_LIST_REQUIRED")
    for source, facts in [(True, row["source_facts"]), (False, row["path"])]:
        starts = []
        for fact in facts:
            validate_fact(fact, row, envelope["evaluation_asof_ms"], source, protocol)
            starts.append(fact["open_ms"])
        require(starts == sorted(set(starts)), "DUPLICATE_OR_UNORDERED_BARS")
    require(milliseconds(row["coverage_start_ms"]) and milliseconds(row["coverage_end_ms"])
            and row["coverage_start_ms"] <= row["coverage_end_ms"] <= envelope["evaluation_asof_ms"],
            "COVERAGE_CLOCK_INVALID")
    if row["path"]:
        require(row["coverage_start_ms"] == row["path"][0]["open_ms"]
                and row["coverage_end_ms"] == row["path"][-1]["end_ms"], "COVERAGE_ENDPOINT_CONTRADICTION")
    if row["right_censored"]:
        require(row["coverage_end_ms"] <= row["administrative_censor_ms"] <= envelope["evaluation_asof_ms"],
                "CENSORING_END_INVALID")


def validate_c(value: dict, protocol: dict) -> dict:
    fields = {"schema_version", "protocol_sha256", "source_kind", "native_admission", "synthetic_manifest",
              "evaluation_asof_ms", "historical_bounded", "episodes", "control_pool", "no_setup_decision_count",
              "export_sha256"}
    require(set(value) == fields and value["schema_version"] == C_SCHEMA, "C_EXPORT_SCHEMA_INVALID")
    require(value["export_sha256"] == digest(without(value, "export_sha256")), "EXPORT_HASH_INVALID")
    require(value["protocol_sha256"] == protocol["protocol_sha256"], "EXPORT_PROTOCOL_MISMATCH")
    require(value["historical_bounded"] is False, "HISTORICAL_BOUNDED_EMBARGO")
    require(value["source_kind"] in protocol["source_classes"], "SOURCE_CLASS_INVALID")
    if value["source_kind"] == "NATIVE_QUALIFIED":
        admission = value["native_admission"]
        require(isinstance(admission, dict) and digest(admission) in protocol["trusted_native_admission_roots"],
                "NATIVE_ADMISSION_UNAVAILABLE")
    else:
        require(value["native_admission"] is None, "UNVERIFIED_SOURCE_AUTHORITY")
    manifest = value["synthetic_manifest"]
    require(isinstance(manifest, dict) and manifest.get("origin") == "FABRICATED_QA_NO_MARKET_DATA"
            and type(manifest.get("seed")) is int and manifest.get("clock") == "FABRICATED_2030_UTC",
            "QA_SOURCE_MANIFEST_INVALID")
    require(milliseconds(value["evaluation_asof_ms"]), "EVALUATION_ASOF_MISSING")
    require(type(value["no_setup_decision_count"]) is int and value["no_setup_decision_count"] >= 0,
            "NO_SETUP_DENOMINATOR_INVALID")
    require(isinstance(value["episodes"], list) and isinstance(value["control_pool"], list), "EPISODES_LIST_REQUIRED")
    identities, triggers = set(), set()
    for row in value["episodes"] + value["control_pool"]:
        validate_episode(row, value, protocol)
        require(row["episode_id"] not in identities, "DUPLICATE_EPISODE")
        key = (row["symbol"], row["strategy_version"], row["trigger_close_ms"])
        require(key not in triggers, "REVISION_OR_DUPLICATE_TRIGGER")
        identities.add(row["episode_id"])
        triggers.add(key)
    return value


def _bindings(bindings: list, expected: str) -> None:
    require(isinstance(bindings, list) and bool(bindings)
            and all(isinstance(b, list) and len(b) == 3 and all(is_digest(x) for x in b) for b in bindings),
            "B_RECEIPT_BINDINGS_INVALID")
    require(len({b[0] for b in bindings}) == len(bindings) and digest(bindings) == expected,
            "B_RECEIPT_MANIFEST_HASH")


def validate_b(value: dict, raw: bytes) -> dict:
    # This adapter consumes exactly the Controller-pinned export, never a refreshed B file.
    require(value.get("export_sha256") == digest(without(value, "export_sha256")), "B_EXPORT_SELF_HASH")
    require(sha(raw) == PINS[B_EXPORT] and value["export_sha256"] == B_SELF_HASH, "B_FROZEN_EXPORT_CHANGED")
    schema_raw = (RESOURCE_ROOT / "inputs/B_episode_schema.original.json").read_bytes()
    require(sha(schema_raw) == PINS["active_project/contracts/b_program_c_episode_export_v1.json"], "B_SCHEMA_CHANGED")
    schema = parse(schema_raw)
    require(value["schema_version"] == B_SCHEMA and value["contract_sha256"] == PINS[
        "active_project/contracts/program_c_evaluation_v1.json"] and value["export_schema_sha256"] == sha(schema_raw),
        "B_CONTRACT_BINDING")
    require(value["source_neutral"] is True and value["study_created"] is False and value["evaluator_run"] is False,
            "B_AUTHORITY_CHANGED")
    require(value["opportunity_count"] == len(value["rows"]) == 1 and value["no_setup_decision_count"] == 2,
            "B_DENOMINATORS_CHANGED")
    row = value["rows"][0]
    require(set(row) == set(schema["required_episode_fields"]), "B_ROW_FIELDS")
    require(row["row_sha256"] == B_ROW_HASH == digest(without(row, "row_sha256")), "B_ROW_CANONICAL_HASH")
    _bindings(row["source_receipt_bindings"], row["source_manifest_sha256"])
    clocks = [row[k] for k in ["source_closed_through_ms", "source_event_ms", "received_ms", "available_ms",
                              "durable_ms", "decision_ms", "scheduled_review_ms"]]
    require(all(milliseconds(t) for t in clocks) and clocks == sorted(clocks), "B_DECISION_CLOCKS")
    require(row["scheduled_review_ms"] == next_review(row["decision_ms"]), "B_REVIEW_SCHEDULE")
    require(row["executable_R"] is None and row["executable_R_status"] == "UNKNOWN"
            and row["economic_evidence"] is False, "B_EXECUTION_NOT_ESTABLISHED")
    require(row["review_delay_ms"] is None and row["review_delay_status"] == "NOT_MEASURED", "B_REVIEW_NOT_OBSERVED")
    require(row["source_type"] == "SYNTHETIC_COMPLETED_CANDLES", "B_SOURCE_CLASS")
    require(row["cost_assumptions"]["base_costs_bps"] == load_protocol()["uncalibrated_B_defaults_bps"], "B_COST_BINDING")
    for obs in row["observation_history"]:
        rec = obs["observation_record"]
        require(obs["observation_sha256"] == digest(rec) and rec["decision_digest"] == row["decision_digest"]
                and rec["episode_id"] == row["episode_id"], "B_OBSERVATION_HASH_OR_IDENTITY")
        _bindings(obs["future_receipt_bindings"], obs["future_receipt_manifest_sha256"])
        require([b[0] for b in obs["future_receipt_bindings"]] == rec["future_receipt_ids"], "B_OBSERVATION_RECEIPTS")
        ts = [obs[k] for k in ["source_event_ms", "received_ms", "available_ms", "durable_ms", "asof_ms"]]
        require(ts == sorted(ts) and ts[0] > row["decision_ms"], "B_OBSERVATION_CLOCKS")
        require(obs["outcome"] == rec["outcome"] == row["observation_outcome"] and obs["outcome"] in OUTCOMES,
                "B_OUTCOME_PROJECTION")
    snapshot = parse((RESOURCE_ROOT / "inputs/B_decision_snapshot.original.json").read_bytes())
    decisions = snapshot["decisions"]
    decision = next(d for d in decisions if d["episode_id"] == row["episode_id"])
    require(digest(decision) == row["decision_digest"] and decision["prefix_sha256"] == row["causal_prefix_sha256"],
            "B_DECISION_LINEAGE")
    require(sum(d["market_state"] == "NO_SETUP" for d in decisions) == 2, "B_NO_SETUP_LINEAGE")
    entry = row["entry_region"][1]
    risk = entry - row["structural_stop"]
    gross = (min(row["fixed_preobservable_target_zones"]) - entry) / risk
    cost = row["planned_cost_per_unit"]
    b_net = (gross * risk - cost) / (risk + cost)
    require(math.isclose(gross, row["planned_R"], rel_tol=1e-12)
            and math.isclose(b_net, row["modeled_after_cost_R"], rel_tol=1e-12), "B_R_GEOMETRY_MISMATCH")
    return value


def default_costs(decision_ms: int) -> dict:
    return {
        "unit": "BPS_OF_QUOTE_NOTIONAL", "known_at_ms": decision_ms,
        "maker_fee_each_side_bps": 5.0, "taker_fee_each_side_bps": 5.0,
        "entry_fee_mode": "TAKER", "exit_fee_mode": "TAKER", "spread_round_trip_bps": 4.0,
        "entry_slippage_bps": 5.0, "exit_slippage_bps": 5.0,
        "funding_bps_per_cadence": 3.0, "funding_cadence_hours": 24,
        "carrying_bps_per_day": 0.0, "financing_bps_per_day": 0.0,
        "impact_bps_at_reference": 1.0, "reference_notional_quote": 1000.0,
        "assumed_notional_quote": 100.0, "available_capacity_quote": None,
        "instrument_tick": 0.01, "instrument_multiplier": 1.0,
        "instrument_type": "LINEAR_QUOTE_BASE", "calibration": "UNCALIBRATED_SYNTHETIC_DEFAULT",
    }


def adapt_b(value: dict, protocol: dict) -> dict:
    b = value["rows"][0]
    row = {key: b[key] for key in ["episode_id", "strategy_version", "symbol", "direction", "regime",
            "source_manifest_sha256", "causal_prefix_sha256", "trigger_close_ms", "decision_ms",
            "scheduled_review_ms", "entry_region", "structural_stop", "volatility_buffer", "execution_buffer",
            "fixed_preobservable_target_zones", "expiry_ms", "holding_horizon_hours", "decision_digest", "row_sha256"]}
    row.update({"source_kind": "SOURCE_SYNTHETIC", "reviewed_ms": None, "source_facts": [], "path": [],
                "coverage_start_ms": b["decision_ms"], "coverage_end_ms": b["observation_coverage_end_ms"],
                "right_censored": b["right_censored"], "administrative_censor_ms": None,
                "interval_hours": 1, "price_unit": "USDT_PER_BASE", "volatility_bucket": "UNKNOWN",
                "source_path_id": b["source_manifest_sha256"], "entry_premise": "CONDITIONAL_ONLY_NOT_A_FILL",
                "costs": default_costs(b["decision_ms"]), "fixture_name": "FROZEN_B_SYNTHETIC",
                "producer_outcome": b["observation_outcome"], "producer_planned_R": b["planned_R"],
                "producer_projected_after_cost_R": b["modeled_after_cost_R"],
                "producer_projected_after_cost_R_semantics": b["modeled_after_cost_R_semantics"]})
    return {"schema_version": C_SCHEMA, "origin_schema": B_SCHEMA, "protocol_sha256": protocol["protocol_sha256"],
            "source_kind": "SOURCE_SYNTHETIC", "evaluation_asof_ms": b["observation_asof_ms"],
            "episodes": [row], "control_pool": [], "no_setup_decision_count": value["no_setup_decision_count"],
            "input_export_sha256": value["export_sha256"]}


def validate(raw: bytes, protocol: dict) -> dict:
    value = parse(raw)
    if value.get("schema_version") == B_SCHEMA:
        return adapt_b(validate_b(value, raw), protocol)
    return validate_c(value, protocol)
