"""Frozen source-neutral episode export; this module does not evaluate episodes."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from .core import fingerprint
from .rc_dashboard import _publish
from .rc_models import frozen_contract

SCHEMA = "V070_B_PROGRAM_C_EPISODE_EXPORT_V1"
CONTRACT = "PROGRAM_C_OPPORTUNITY_EVALUATION_HANDOFF_V1"
OUTCOMES = frozenset({"TARGET_FIRST", "STOP_FIRST", "TIME_STOP", "NO_FILL", "MISSED_ENTRY",
                      "AMBIGUOUS_OHLC_ORDER_UNKNOWN", "MISSING_COVERAGE", "RIGHT_CENSORED",
                      "INSUFFICIENT_FUTURE_HORIZON"})


def _manifest(receipts):
    return fingerprint([[r.identity, r.raw_sha256, r.normalized_sha256] for r in receipts])


def _observation_export(item, receipt_index):
    ids = item["future_receipt_ids"]
    missing = set(ids) - set(receipt_index)
    if missing:
        raise ValueError("PROGRAM_C_OBSERVATION_RECEIPT_MISSING")
    receipts = [receipt_index[identity] for identity in ids]
    return {
        "observation_sha256": fingerprint(item),
        "observation_record": item,
        "asof_ms": item["asof_ms"],
        "outcome": item["outcome"],
        "future_prefix_sha256": item["future_prefix_sha256"],
        "future_receipt_bindings": [[r.identity, r.raw_sha256, r.normalized_sha256] for r in receipts],
        "future_receipt_manifest_sha256": _manifest(receipts),
        "future_receipt_count": len(receipts),
        "source_event_ms": max((r.bar.source_event_ms for r in receipts), default=None),
        "received_ms": max((r.bar.received_ms for r in receipts), default=None),
        "available_ms": max((r.bar.available_ms for r in receipts), default=None),
        "durable_ms": max((r.bar.durable_ms for r in receipts), default=None),
        "coverage_end_ms": item["coverage_end_ms"],
        "required_end_ms": item["required_end_ms"],
        "right_censored": item["right_censored"],
        "entry_condition_observed": item["entry_condition_observed"],
        "reasons": list(item["reasons"]),
    }


def _select_observation_history(observations):
    """Keep all distinct observations in as-of order; conflicting ties are ambiguous."""
    by_episode = defaultdict(list)
    for item in observations:
        by_episode[item["episode_id"]].append(item)
    selected = {}
    for episode_id, items in by_episode.items():
        by_asof = {}
        for item in items:
            digest = fingerprint(item)
            old = by_asof.get(item["asof_ms"])
            if old is not None and old[0] != digest:
                raise ValueError("PROGRAM_C_OBSERVATION_ASOF_CONFLICT")
            by_asof[item["asof_ms"]] = (digest, item)
        selected[episode_id] = [value[1] for _, value in sorted(by_asof.items())]
    return selected


def build_export(store):
    store.verify()
    receipt_index = {r.identity: r for r in store.receipts()}
    histories = _select_observation_history(store.observations())
    rows = []
    decisions = store.decisions()
    for decision in decisions:
        opportunity = decision.opportunity
        if opportunity is None or decision.episode_id is None:
            continue
        missing = set(decision.receipt_ids) - set(receipt_index)
        if missing:
            raise ValueError("PROGRAM_C_SOURCE_MANIFEST_RECEIPT_MISSING")
        receipts = [receipt_index[identity] for identity in decision.receipt_ids]
        history = [_observation_export(item, receipt_index)
                   for item in histories.get(decision.episode_id, [])]
        latest = history[-1] if history else None
        source_closed_through = max(r.bar.end_ms for r in receipts)
        source_event = max(r.bar.source_event_ms for r in receipts)
        received = max(r.bar.received_ms for r in receipts)
        available = max(r.bar.available_ms for r in receipts)
        durable = max(r.bar.durable_ms for r in receipts)
        if not source_closed_through <= source_event <= received <= available <= durable <= decision.decision_ms:
            raise ValueError("PROGRAM_C_DECISION_SOURCE_CLOCK_INVALID")
        cost_assumptions = _expected_cost_assumptions()
        cost_sensitivity = {
            "status": "NOT_EVALUATED",
            "base_assumptions": cost_assumptions,
            "predeclared_adverse_cases": [
                {"case": "DOUBLE_SPREAD_AND_SLIPPAGE", "status": "NOT_RUN",
                 "multipliers": {"spread_round_trip": 2.0, "slippage_each_side": 2.0}},
                {"case": "DOUBLE_CARRY_AND_FEES", "status": "NOT_RUN",
                 "multipliers": {"funding_and_carry_per_day": 2.0, "fee_each_side": 2.0}},
            ],
        }
        source_latency = decision.decision_ms - source_closed_through
        available_latency = decision.decision_ms - available
        row = {
            "episode_id": decision.episode_id,
            "strategy_version": decision.strategy_version,
            "symbol": decision.symbol,
            "direction": opportunity.direction,
            "regime": opportunity.regime,
            "source_type": decision.source_type,
            "source_manifest_sha256": _manifest(receipts),
            "source_receipt_bindings": [[r.identity, r.raw_sha256, r.normalized_sha256] for r in receipts],
            "causal_prefix_sha256": decision.prefix_sha256,
            "bar_interval_convention": "UTC half-open [open,end); close_time_ms=end-1",
            "source_closed_through_ms": source_closed_through,
            "source_event_ms": source_event,
            "received_ms": received,
            "available_ms": available,
            "durable_ms": durable,
            "trigger_close_ms": decision.trigger_close_ms,
            "decision_ms": decision.decision_ms,
            "decision_digest": fingerprint(decision.model_dump(mode="json")),
            "scheduled_review_ms": decision.scheduled_review_ms,
            "review_delay_ms": None,
            "review_delay_status": "NOT_MEASURED",
            "processing_close_to_decision_latency_ms": source_latency,
            "processing_available_to_decision_latency_ms": available_latency,
            "scheduled_human_review_delay_ms": None,
            "scheduled_human_review_delay_status": "NOT_MEASURED",
            "entry_region": list(opportunity.entry_region),
            "structural_stop": opportunity.buffered_stop,
            "volatility_buffer": opportunity.atr_buffer,
            "execution_buffer": opportunity.execution_buffer,
            "fixed_preobservable_target_zones": list(opportunity.target_zones),
            "expiry_ms": opportunity.expires_ms,
            "holding_horizon_hours": opportunity.holding_hours,
            "account_veto": decision.account,
            "rule_reasons": list(decision.reasons),
            "coverage_gaps": list(decision.gaps),
            "planned_R": decision.diagnostics["planned_gross_r"],
            "planned_gross_R": decision.diagnostics["planned_gross_r"],
            "planned_after_cost_R": opportunity.planned_after_cost_r,
            "modeled_after_cost_R": opportunity.planned_after_cost_r,
            "modeled_after_cost_R_semantics": "EX_ANTE_GEOMETRY_NOT_OBSERVED_RETURN",
            "executable_R": None,
            "executable_R_status": "UNKNOWN",
            "cost_assumption": opportunity.cost_assumption,
            "planned_cost_per_unit": opportunity.planned_cost_per_unit,
            "cost_assumptions": cost_assumptions,
            "cost_sensitivity": cost_sensitivity,
            "confidence": decision.confidence,
            "observation_status": "APPENDED" if latest else "NOT_RUN",
            "observation_history": history,
            "observation_outcome": latest["outcome"] if latest else None,
            "observation_asof_ms": latest["asof_ms"] if latest else None,
            "observation_prefix_sha256": latest["future_prefix_sha256"] if latest else None,
            "observation_receipt_manifest_sha256": latest["future_receipt_manifest_sha256"] if latest else None,
            "observation_source_event_ms": latest["source_event_ms"] if latest else None,
            "observation_received_ms": latest["received_ms"] if latest else None,
            "observation_available_ms": latest["available_ms"] if latest else None,
            "observation_durable_ms": latest["durable_ms"] if latest else None,
            "observation_coverage_end_ms": latest["coverage_end_ms"] if latest else None,
            "observation_required_end_ms": latest["required_end_ms"] if latest else None,
            "right_censored": latest["right_censored"] if latest else None,
            "observation_reasons": latest["reasons"] if latest else [],
            "economic_evidence": False,
        }
        row["row_sha256"] = fingerprint(row)
        rows.append(row)
    root = Path(__file__).resolve().parents[1] / "resources"
    parent_path = root / "contracts/program_c_evaluation_v1.json"
    schema_path = root / "contracts/b_program_c_episode_export_v1.json"
    value = {
        "schema_version": SCHEMA,
        "contract_schema": CONTRACT,
        "contract_sha256": hashlib.sha256(parent_path.read_bytes()).hexdigest(),
        "export_schema_sha256": hashlib.sha256(schema_path.read_bytes()).hexdigest(),
        "source_neutral": True,
        "evaluator_run": False,
        "study_created": False,
        "rows": rows,
        "opportunity_count": len(rows),
        "no_setup_decision_count": sum(d.market_state == "NO_SETUP" for d in decisions),
        "outcome_taxonomy": sorted(OUTCOMES),
    }
    value["export_sha256"] = fingerprint(value)
    validate_export(value)
    return value


def _expected_contract_digests():
    root = Path(__file__).resolve().parents[1] / "resources" / "contracts"
    parent = root / "program_c_evaluation_v1.json"
    schema = root / "b_program_c_episode_export_v1.json"
    return (hashlib.sha256(parent.read_bytes()).hexdigest(),
            hashlib.sha256(schema.read_bytes()).hexdigest(),
            json.loads(schema.read_text()))


def _expected_cost_assumptions():
    root = Path(__file__).resolve().parents[1] / "resources" / "contracts/rc_v1.json"
    contract = frozen_contract()
    return {
        "schema_version": "V070_B_COST_ASSUMPTIONS_V1",
        "source_contract_sha256": hashlib.sha256(root.read_bytes()).hexdigest(),
        "method": contract["strategy"]["cost_method"],
        "base_costs_bps": contract["strategy"]["costs_bps"],
    }


def _positive_ms(value):
    return type(value) is int and value > 0


def _finite_positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _digest(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate_observation_history(row):
    history = row["observation_history"]
    if row["observation_status"] == "NOT_RUN":
        if history or any(row[k] is not None for k in (
                "observation_outcome", "observation_asof_ms", "observation_prefix_sha256",
                "observation_receipt_manifest_sha256", "observation_source_event_ms",
                "observation_received_ms", "observation_available_ms", "observation_durable_ms",
                "observation_coverage_end_ms", "observation_required_end_ms", "right_censored")):
            raise ValueError("PROGRAM_C_UNOBSERVED_ROW_HAS_OBSERVATION_FIELDS")
        return
    if row["observation_status"] != "APPENDED" or not history:
        raise ValueError("PROGRAM_C_OBSERVATION_STATUS_INVALID")
    times = [item["asof_ms"] for item in history]
    if times != sorted(set(times)) or times[0] < row["decision_ms"]:
        raise ValueError("PROGRAM_C_OBSERVATION_HISTORY_ORDER_INVALID")
    latest = history[-1]
    pairs = {
        "observation_outcome": "outcome",
        "observation_asof_ms": "asof_ms",
        "observation_prefix_sha256": "future_prefix_sha256",
        "observation_receipt_manifest_sha256": "future_receipt_manifest_sha256",
        "observation_source_event_ms": "source_event_ms",
        "observation_received_ms": "received_ms",
        "observation_available_ms": "available_ms",
        "observation_durable_ms": "durable_ms",
        "observation_coverage_end_ms": "coverage_end_ms",
        "observation_required_end_ms": "required_end_ms",
        "right_censored": "right_censored",
    }
    if any(row[field] != latest[source] for field, source in pairs.items()):
        raise ValueError("PROGRAM_C_LATEST_OBSERVATION_PROJECTION_MISMATCH")
    for item in history:
        record = item["observation_record"]
        if (fingerprint(record) != item["observation_sha256"]
                or record["episode_id"] != row["episode_id"]
                or record["decision_digest"] != row["decision_digest"]
                or record["asof_ms"] != item["asof_ms"]
                or record["outcome"] != item["outcome"]
                or record["future_prefix_sha256"] != item["future_prefix_sha256"]
                or record["future_receipt_ids"] is None):
            raise ValueError("PROGRAM_C_OBSERVATION_RECORD_BINDING_INVALID")
        if item["outcome"] not in OUTCOMES or not _positive_ms(item["asof_ms"]):
            raise ValueError("PROGRAM_C_OBSERVATION_OUTCOME_OR_TIME_INVALID")
        if not _digest(item["observation_sha256"]) or not _digest(item["future_prefix_sha256"]):
            raise ValueError("PROGRAM_C_OBSERVATION_DIGEST_INVALID")
        if not _digest(item["future_receipt_manifest_sha256"]):
            raise ValueError("PROGRAM_C_OBSERVATION_MANIFEST_INVALID")
        bindings = item["future_receipt_bindings"]
        if (len(bindings) != item["future_receipt_count"]
                or any(not isinstance(binding, list) or len(binding) != 3
                       or not _digest(binding[0]) or not _digest(binding[1]) or not _digest(binding[2])
                       for binding in bindings)
                or fingerprint(bindings) != item["future_receipt_manifest_sha256"]
                or [binding[0] for binding in bindings] != record["future_receipt_ids"]):
            raise ValueError("PROGRAM_C_OBSERVATION_RECEIPT_BINDING_INVALID")
        if type(item["right_censored"]) is not bool or type(item["entry_condition_observed"]) is not bool:
            raise ValueError("PROGRAM_C_OBSERVATION_BOOLEAN_INVALID")
        count = item["future_receipt_count"]
        clocks = [item[k] for k in ("source_event_ms", "received_ms", "available_ms", "durable_ms")]
        if type(count) is not int or count < 0:
            raise ValueError("PROGRAM_C_OBSERVATION_RECEIPT_COUNT_INVALID")
        if count == 0:
            if any(clock is not None for clock in clocks):
                raise ValueError("PROGRAM_C_EMPTY_OBSERVATION_HAS_SOURCE_CLOCKS")
        elif (not all(_positive_ms(t) for t in clocks)
              or not row["decision_ms"] < clocks[0] <= clocks[1] <= clocks[2] <= clocks[3] <= item["asof_ms"]):
            raise ValueError("PROGRAM_C_OBSERVATION_SOURCE_CLOCK_INVALID")


def validate_export(value):
    expected_contract_sha, expected_schema_sha, schema = _expected_contract_digests()
    if (value.get("schema_version") != SCHEMA or value.get("contract_schema") != CONTRACT
            or value.get("contract_sha256") != expected_contract_sha
            or value.get("export_schema_sha256") != expected_schema_sha
            or value.get("source_neutral") is not True or value.get("evaluator_run") is not False
            or value.get("study_created") is not False
            or type(value.get("opportunity_count")) is not int
            or value["opportunity_count"] != len(value.get("rows", []))
            or type(value.get("no_setup_decision_count")) is not int
            or value["no_setup_decision_count"] < 0
            or value.get("outcome_taxonomy") != sorted(OUTCOMES)):
        raise ValueError("PROGRAM_C_EXPORT_ENVELOPE_INVALID")
    if value.get("export_sha256") != fingerprint({k: v for k, v in value.items() if k != "export_sha256"}):
        raise ValueError("PROGRAM_C_EXPORT_DIGEST_MISMATCH")
    if len({r.get("episode_id") for r in value["rows"]}) != len(value["rows"]):
        raise ValueError("PROGRAM_C_EXPORT_EPISODE_DUPLICATE")
    cost_assumptions = _expected_cost_assumptions()
    seen = set()
    for row in value["rows"]:
        if set(row) != set(schema["required_episode_fields"]):
            raise ValueError("PROGRAM_C_EXPORT_ROW_SCHEMA_MISMATCH")
        if row["episode_id"] in seen or not _digest(row["decision_digest"]):
            raise ValueError("PROGRAM_C_EXPORT_EPISODE_OR_DECISION_INVALID")
        seen.add(row["episode_id"])
        if (row["source_type"] != "SYNTHETIC_COMPLETED_CANDLES"
                or row["symbol"] not in {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
                or row["direction"] not in {"LONG", "SHORT"}
                or row["regime"] not in {"TREND_UP", "TREND_DOWN"}
                or row["account_veto"] != "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
                or row["economic_evidence"] is not False
                or row["confidence"] != "RULE_EVIDENCE_ONLY_NOT_PROBABILITY"):
            raise ValueError("PROGRAM_C_EXPORT_AUTHORITY_OR_ECONOMIC_FIELDS_INVALID")
        if not all(_digest(row[k]) for k in ("source_manifest_sha256", "causal_prefix_sha256")):
            raise ValueError("PROGRAM_C_EXPORT_SOURCE_BINDING_INVALID")
        source_bindings = row["source_receipt_bindings"]
        if (not source_bindings
                or any(not isinstance(binding, list) or len(binding) != 3
                       or not _digest(binding[0]) or not _digest(binding[1]) or not _digest(binding[2])
                       for binding in source_bindings)
                or fingerprint(source_bindings) != row["source_manifest_sha256"]):
            raise ValueError("PROGRAM_C_SOURCE_RECEIPT_BINDING_INVALID")
        clock_keys = ["source_closed_through_ms", "source_event_ms", "received_ms",
                      "available_ms", "durable_ms", "decision_ms", "scheduled_review_ms"]
        clocks = [row[k] for k in clock_keys]
        if (not all(_positive_ms(t) for t in clocks)
                or not clocks[0] <= clocks[1] <= clocks[2] <= clocks[3] <= clocks[4] <= clocks[5] <= clocks[6]
                or row["trigger_close_ms"] > row["decision_ms"]):
            raise ValueError("PROGRAM_C_DECISION_SOURCE_CLOCK_INVALID")
        if (row["processing_close_to_decision_latency_ms"] != row["decision_ms"] - row["source_closed_through_ms"]
                or row["processing_available_to_decision_latency_ms"] != row["decision_ms"] - row["available_ms"]
                or row["review_delay_ms"] is not None or row["review_delay_status"] != "NOT_MEASURED"
                or row["scheduled_human_review_delay_ms"] is not None
                or row["scheduled_human_review_delay_status"] != "NOT_MEASURED"):
            raise ValueError("PROGRAM_C_LATENCY_AND_HUMAN_REVIEW_MUST_BE_SEPARATE")
        if not (row["decision_ms"] < row["expiry_ms"] and type(row["holding_horizon_hours"]) is int
                and 4 <= row["holding_horizon_hours"] <= 120):
            raise ValueError("PROGRAM_C_RISK_HORIZON_INVALID")
        entry = row["entry_region"]
        targets = row["fixed_preobservable_target_zones"]
        if (not isinstance(entry, list) or len(entry) != 2 or not all(_finite_positive(x) for x in entry)
                or entry[0] > entry[1] or not targets or not all(_finite_positive(x) for x in targets)
                or not _finite_positive(row["structural_stop"])
                or not _finite_positive(row["volatility_buffer"])
                or not _finite_positive(row["execution_buffer"])):
            raise ValueError("PROGRAM_C_RISK_GEOMETRY_INVALID")
        if row["direction"] == "LONG" and not row["structural_stop"] < entry[0] < min(targets):
            raise ValueError("PROGRAM_C_LONG_GEOMETRY_INVALID")
        if row["direction"] == "SHORT" and not row["structural_stop"] > entry[1] > max(targets):
            raise ValueError("PROGRAM_C_SHORT_GEOMETRY_INVALID")
        if (not _finite_positive(row["planned_R"]) or row["planned_R"] != row["planned_gross_R"]
                or not _finite_positive(row["modeled_after_cost_R"])
                or row["modeled_after_cost_R"] != row["planned_after_cost_R"]
                or row["modeled_after_cost_R_semantics"] != "EX_ANTE_GEOMETRY_NOT_OBSERVED_RETURN"
                or row["executable_R"] is not None or row["executable_R_status"] != "UNKNOWN"):
            raise ValueError("PROGRAM_C_RISK_MEASUREMENT_SEPARATION_INVALID")
        if row["cost_assumptions"] != cost_assumptions:
            raise ValueError("PROGRAM_C_BASE_COST_ASSUMPTIONS_MISMATCH")
        sensitivity = row["cost_sensitivity"]
        if (sensitivity.get("status") != "NOT_EVALUATED"
                or sensitivity.get("base_assumptions") != row["cost_assumptions"]
                or not sensitivity.get("predeclared_adverse_cases")):
            raise ValueError("PROGRAM_C_COST_SENSITIVITY_ENVELOPE_INVALID")
        if row["row_sha256"] != fingerprint({k: v for k, v in row.items() if k != "row_sha256"}):
            raise ValueError("PROGRAM_C_EXPORT_ROW_DIGEST_MISMATCH")
        _validate_observation_history(row)
    return value


def write_export(output, value):
    validate_export(value)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    name = f"program-c-episode-export-{value['export_sha256']}.json"
    target = output / name
    if target.exists():
        if target.read_text(encoding="utf-8") != encoded:
            raise ValueError("PROGRAM_C_EXPORT_IMMUTABLE_CONFLICT")
    else:
        _publish(output, name, encoded, immutable=True)
    _publish(output, "latest-program-c-episode-export.json", encoded)
    return target
