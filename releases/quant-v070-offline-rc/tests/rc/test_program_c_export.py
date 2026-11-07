import json

import pytest

from btc_quant_agent.platform.core import fingerprint
from btc_quant_agent.platform.program_c_export import (
    _select_observation_history, build_export, validate_export, write_export,
)
from btc_quant_agent.platform.rc_fixture import future_fixture
from btc_quant_agent.platform.rc_observe import observe
from btc_quant_agent.platform.rc_source import admit_stream


def test_frozen_source_neutral_episode_export_roundtrip_and_replay(stored, positive, tmp_path):
    first = build_export(stored)
    assert first["opportunity_count"] == 1 and first["source_neutral"] is True
    row = first["rows"][0]
    assert row["executable_R"] is None and row["executable_R_status"] == "UNKNOWN"
    assert row["modeled_after_cost_R"] == positive.opportunity.planned_after_cost_r
    assert row["observation_status"] == "NOT_RUN" and row["observation_outcome"] is None
    assert row["review_delay_ms"] is None
    assert row["processing_close_to_decision_latency_ms"] == positive.decision_ms - positive.trigger_close_ms
    assert row["scheduled_human_review_delay_status"] == "NOT_MEASURED"
    assert row["modeled_after_cost_R_semantics"] == "EX_ANTE_GEOMETRY_NOT_OBSERVED_RETURN"
    assert row["cost_assumptions"]["base_costs_bps"]
    assert row["cost_sensitivity"]["status"] == "NOT_EVALUATED"
    validate_export(first)
    path = write_export(tmp_path, first)
    encoded = path.read_bytes()
    second = build_export(stored)
    assert first == second and write_export(tmp_path, second) == path
    assert path.read_bytes() == encoded
    assert json.loads(encoded)["export_sha256"] == fingerprint({
        k: v for k, v in first.items() if k != "export_sha256"})


def test_frozen_export_binds_later_observation_and_rejects_row_tampering(stored, positive):
    early = observe(positive, stored.receipts(), asof_ms=positive.decision_ms)
    stored.record_observation(early.model_dump(mode="json"))
    later = future_fixture(positive)
    admit_stream(stored, later)
    observation = observe(positive, stored.receipts(), asof_ms=positive.trigger_close_ms + 50 * 3_600_000 + 1000)
    stored.record_observation(observation.model_dump(mode="json"))
    value = build_export(stored)
    row = value["rows"][0]
    assert row["observation_status"] == "APPENDED"
    assert row["observation_outcome"] == observation.outcome
    assert row["observation_prefix_sha256"] == observation.future_prefix_sha256
    assert [item["outcome"] for item in row["observation_history"]] == [
        "INSUFFICIENT_FUTURE_HORIZON", observation.outcome]
    tampered = json.loads(json.dumps(value))
    tampered["rows"][0]["planned_R"] += 1
    tampered["export_sha256"] = fingerprint({k: v for k, v in tampered.items() if k != "export_sha256"})
    with pytest.raises(ValueError, match="PROGRAM_C_RISK_MEASUREMENT_SEPARATION_INVALID"):
        validate_export(tampered)


@pytest.mark.parametrize(("field", "value", "error"), [
    ("contract_sha256", "0" * 64, "PROGRAM_C_EXPORT_ENVELOPE_INVALID"),
    ("economic_evidence", True, "PROGRAM_C_EXPORT_AUTHORITY_OR_ECONOMIC_FIELDS_INVALID"),
    ("source_event_ms", 2_000_000_000_000, "PROGRAM_C_DECISION_SOURCE_CLOCK_INVALID"),
])
def test_export_semantic_gate_survives_self_rehash(field, value, error, stored):
    export = build_export(stored)
    if field == "contract_sha256":
        export[field] = value
    else:
        export["rows"][0][field] = value
        export["rows"][0]["row_sha256"] = fingerprint({
            k: v for k, v in export["rows"][0].items() if k != "row_sha256"})
    export["export_sha256"] = fingerprint({k: v for k, v in export.items() if k != "export_sha256"})
    with pytest.raises(ValueError, match=error):
        validate_export(export)


def test_export_refuses_conflicting_observations_at_same_asof(stored, positive):
    first = observe(positive, stored.receipts(), asof_ms=positive.decision_ms).model_dump(mode="json")
    conflicting = dict(first, outcome="TARGET_FIRST")
    with pytest.raises(ValueError, match="PROGRAM_C_OBSERVATION_ASOF_CONFLICT"):
        _select_observation_history([first, conflicting])
