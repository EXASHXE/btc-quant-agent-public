from __future__ import annotations

import copy
import json

import pytest
from conftest import reseal
from make_fixtures import seal_fact
from program_c.integrity import (
    B_EXPORT,
    PINS,
    WORKSPACE,
    ContractError,
    canonical,
    digest,
    parse,
    sha,
    without,
)
from program_c.protocol import HOUR
from program_c.validation import validate


def test_exact_frozen_b_external_canonical_row_and_decision(protocol):
    raw = (WORKSPACE / "inputs/B_episode_export.original.json").read_bytes()
    obj = parse(raw)
    assert sha(raw) == PINS[B_EXPORT]
    assert digest(without(obj, "export_sha256")) == obj["export_sha256"]
    row = obj["rows"][0]
    assert digest(without(row, "row_sha256")) == row["row_sha256"]
    adapted = validate(raw, protocol)
    assert len(adapted["episodes"]) == 1
    assert adapted["no_setup_decision_count"] == 2
    assert adapted["episodes"][0]["reviewed_ms"] is None
    assert adapted["episodes"][0]["path"] == []


@pytest.mark.parametrize("layer", ["row", "export", "rehash_all", "reformat"])
def test_b_tampering_and_byte_changes_rejected(protocol, layer):
    raw = (WORKSPACE / "inputs/B_episode_export.original.json").read_bytes()
    value = parse(raw)
    if layer != "reformat":
        value["rows"][0]["entry_region"][1] += 1
    if layer == "rehash_all":
        r = value["rows"][0]
        r["row_sha256"] = digest(without(r, "row_sha256"))
        value["export_sha256"] = digest(without(value, "export_sha256"))
    with pytest.raises(ContractError, match="B_EXPORT_SELF_HASH|B_FROZEN_EXPORT_CHANGED"):
        validate(canonical(value), protocol)


@pytest.mark.parametrize("field,value,reason", [
    ("direction", "UP", "SYMBOL_OR_DIRECTION"),
    ("symbol", "DOGEUSDT", "SYMBOL_OR_DIRECTION"),
    ("strategy_version", "S2", "INACTIVE_STRATEGY"),
    ("price_unit", "BTC_PER_USDT", "PRICE_UNIT_INVALID"),
    ("holding_horizon_hours", 3, "HORIZON_INVALID"),
    ("holding_horizon_hours", 121, "HORIZON_INVALID"),
    ("holding_horizon_hours", True, "HORIZON_INVALID"),
    ("entry_region", [101, 99], "ENTRY_REGION_INVALID"),
    ("structural_stop", 101, "LONG_GEOMETRY_INVALID"),
    ("volatility_buffer", -1, "STOP_BUFFER_INVALID"),
    ("interval_hours", 0.05, "INTERVAL_INVALID"),
    ("scheduled_review_ms", 100, "EPISODE_CLOCK_INVALID"),
])
def test_exante_contract_fail_closed(protocol, fixture_export, field, value, reason):
    obj = fixture_export("precise_time_stop")
    obj["episodes"][0][field] = value
    with pytest.raises(ContractError, match=reason):
        validate(reseal(obj), protocol)


@pytest.mark.parametrize("field,value,reason", [
    ("unit", "PERCENT", "COST_OR_INSTRUMENT_UNITS_INVALID"),
    ("taker_fee_each_side_bps", -1, "COST_PARAMETER_INVALID"),
    ("funding_bps_per_cadence", -3, "COST_PARAMETER_INVALID"),
    ("funding_cadence_hours", 0, "COST_PARAMETER_NONPOSITIVE"),
    ("instrument_type", "INVERSE", "COST_OR_INSTRUMENT_UNITS_INVALID"),
    ("entry_fee_mode", "FREE", "FEE_MODE_INVALID"),
    ("available_capacity_quote", -1, "CAPACITY_INVALID"),
])
def test_cost_parameters_fail_closed(protocol, fixture_export, field, value, reason):
    obj = fixture_export("precise_time_stop")
    obj["episodes"][0]["costs"][field] = value
    with pytest.raises(ContractError, match=reason):
        validate(reseal(obj), protocol)


def test_future_costs_fail_closed(protocol, fixture_export):
    obj = fixture_export("precise_time_stop")
    row = obj["episodes"][0]
    row["costs"]["known_at_ms"] = row["decision_ms"] + 1
    with pytest.raises(ContractError, match="FUTURE_COST_INFORMATION"):
        validate(reseal(obj), protocol)


@pytest.mark.parametrize("name,reason", [
    ("future_leaking_receipt", "FUTURE_RECEIPT_AFTER_ASOF"),
    ("corrected_revision", "REVISION_REQUIRES_NEW_VERSION"),
    ("open_bar", "OPEN_BAR_FORBIDDEN"),
    ("duplicate_bars", "DUPLICATE_OR_UNORDERED_BARS"),
    ("stale_observation", "STALE_OBSERVATION"),
    ("clock_drift", "CLOCK_DRIFT"),
    ("historical_bounded_embargo", "HISTORICAL_BOUNDED_EMBARGO"),
    ("native_string_not_authority", "NATIVE_ADMISSION_UNAVAILABLE"),
])
def test_invalid_fixture_reasons(protocol, fixture_export, name, reason):
    with pytest.raises(ContractError, match=reason):
        validate(canonical(fixture_export(name)), protocol)


def test_missing_timestamp_is_not_defaulted(protocol, fixture_export):
    obj = fixture_export("precise_time_stop")
    del obj["episodes"][0]["path"][0]["available_ms"]
    with pytest.raises(ContractError, match="FACT_FIELDS_INVALID"):
        validate(reseal(obj), protocol)


def test_causal_fact_after_decision_is_rejected(protocol, fixture_export):
    obj = fixture_export("precise_time_stop")
    source = obj["episodes"][0]["source_facts"][0]
    for key in ["open_ms", "end_ms", "source_event_ms", "received_ms", "available_ms", "durable_ms"]:
        source[key] += 2 * HOUR
    seal_fact(source)
    with pytest.raises(ContractError, match="FUTURE_SOURCE_FACT_AT_DECISION"):
        validate(reseal(obj), protocol)


def test_duplicate_and_revised_episode_not_new_sample(protocol, fixture_export):
    obj = fixture_export("precise_time_stop")
    obj["episodes"].append(copy.deepcopy(obj["episodes"][0]))
    with pytest.raises(ContractError, match="DUPLICATE_EPISODE"):
        validate(reseal(obj), protocol)
    row = obj["episodes"][1]
    row["source_facts"][0]["close"] = 99.5
    seal_fact(row["source_facts"][0])
    with pytest.raises(ContractError, match="REVISION_OR_DUPLICATE_TRIGGER"):
        validate(reseal(obj), protocol)


@pytest.mark.parametrize("layer", ["export", "row", "fact", "decision", "prefix"])
def test_c_hash_lineage_tampering(protocol, fixture_export, layer):
    obj = fixture_export("precise_time_stop")
    row = obj["episodes"][0]
    if layer == "export":
        obj["no_setup_decision_count"] += 1
    elif layer == "row":
        row["entry_region"][0] = 98
        obj["export_sha256"] = digest(without(obj, "export_sha256"))
    else:
        key = {"fact": "fact_sha256", "decision": "decision_digest", "prefix": "causal_prefix_sha256"}[layer]
        target = row["path"][0] if layer == "fact" else row
        target[key] = "0" * 64
        row["row_sha256"] = digest(without(row, "row_sha256"))
        obj["export_sha256"] = digest(without(obj, "export_sha256"))
    with pytest.raises(ContractError):
        validate(canonical(obj), protocol)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'[]'])
def test_strict_json(raw):
    with pytest.raises(ContractError):
        parse(raw)


def test_hash_algorithms_distinguish_bytes_and_semantics():
    first, second = b'{"a":1}', b'{ "a" : 1 }\n'
    assert sha(first) != sha(second)
    assert digest(json.loads(first)) == digest(json.loads(second))


def test_review_after_asof_is_contradictory(protocol, fixture_export):
    obj = fixture_export("precise_time_stop")
    obj["episodes"][0]["reviewed_ms"] = obj["evaluation_asof_ms"] + 1
    with pytest.raises(ContractError, match="REVIEW_TIMESTAMP_INVALID"):
        validate(reseal(obj), protocol)
