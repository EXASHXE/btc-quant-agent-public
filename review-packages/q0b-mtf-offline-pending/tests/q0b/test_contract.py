from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import jsonschema
import pytest

from q0b import VERSION
from q0b.examples import SETUP_END, artifacts
from q0b.planner import Request, plan_collection
from q0b.schema import Policy, STATES
from q0b.transport import decode_fixture

ROOT = Path(__file__).resolve().parents[2]


def read(relative):
    return json.loads((ROOT / relative).read_text())


def json_value(value):
    return json.loads(json.dumps(value, allow_nan=False))


def test_contract_constants_and_predeclared_budget_match_runtime():
    contract = read("Q0B_CONTRACT.json")
    assert contract["strategy_version"] == VERSION
    assert tuple(contract["states"]) == STATES
    policy = asdict(Policy())
    assert policy["holding_hours"] == contract["time_policy"]["holding_hours"]["default"]
    assert policy["response_minutes"] == contract["time_policy"]["expected_human_response_minutes"]["default"]
    for count in (3, 10, 50):
        plan = plan_collection(SETUP_END+5_000, [f"COIN{i:02}USDT" for i in range(count)]).to_dict()
        expected = contract["collector"][f"bootstrap_{count}_symbols"]
        assert expected == {"requests": plan["request_count"], "weight": plan["request_weight"]}


def test_versioned_card_schema_and_deterministic_artifacts():
    schema = read("q0b/card.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)
    generated = artifacts()
    assert json_value(generated) == json_value(artifacts())
    for name, value in generated.items():
        assert read("artifacts/"+name) == json_value(value)
    for pair in generated["paired_comparison.json"]["pairs"]:
        validator.validate(json_value(pair["mtf"]))
        validator.validate(json_value(pair["control"]))
    for card in generated["synthetic_cards.json"]["cards"]:
        validator.validate(json_value(card.get("card", card)))


def test_schema_refuses_cached_ready_in_nonready_card():
    schema = read("q0b/card.schema.json")
    ready = json_value(artifacts()["paired_comparison.json"]["pairs"][1]["mtf"])
    ready["state"] = "EXPIRED"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(ready, schema)


def test_transport_receipt_schema_is_separate_from_strategy_card():
    schema = read("q0b/transport.schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
    request = Request("/fapi/v1/ticker/bookTicker", {"symbol": "BTCUSDT"}, "BTCUSDT")
    wire = {"symbol": "BTCUSDT", "bidPrice": "100", "askPrice": "101", "bidQty": "10",
            "askQty": "10", "time": SETUP_END}
    _, receipt = decode_fixture(request, wire, received_ms=SETUP_END+100,
                                available_ms=SETUP_END+200, exchange_lower_ms=SETUP_END)
    jsonschema.validate(receipt, schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(receipt, read("q0b/card.schema.json"))


def test_readonly_accepted_source_and_configuration_byte_unchanged():
    baseline = read("artifacts/readonly_baseline.json")
    for relative, expected in baseline["files"].items():
        assert sha256((ROOT / relative).read_bytes()).hexdigest() == expected, relative
    current = {str(p.relative_to(ROOT)) for root in baseline["roots"]
               for p in (ROOT / root).rglob("*") if p.is_file()}
    assert current == set(baseline["files"]) - {"pyproject.toml"}
