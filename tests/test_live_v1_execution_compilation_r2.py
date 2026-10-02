"""Approval equivalence must survive recomputation of a local intent self-hash."""
from __future__ import annotations

import pytest
from test_live_v1_execution_validator import NOW, sample_market_obs, setup_validator_and_intent

from btc_quant_agent.execution.intents import TradeIntentV1


@pytest.mark.parametrize("field,value", [
    ("quantity", 3.2944), ("stop_loss", 1.0), ("take_profit_1", 110.0),
    ("take_profit_2", 120.0), ("leverage", 3), ("order_type", "MARKET"),
    ("price", 100.01), ("side", "SELL"), ("symbol", "ETHUSDT"),
])
def test_recomputed_self_hash_cannot_change_approved_executable_contract(tmp_path, field, value):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    payload = intent.model_dump(exclude={"intent_hash"})
    payload[field] = value
    if field == "quantity":
        payload[field] = intent.quantity * 2
    elif field in {"take_profit_1", "take_profit_2"}:
        payload[field] = getattr(intent, field) + 0.1
    altered = TradeIntentV1.build(**payload)
    result = validator.validate(altered, sample_market_obs(), snapshot, NOW)
    assert not result.is_valid
    assert result.reason == "EXECUTABLE_CONTRACT_MISMATCH"


def test_unchanged_approved_executable_contract_is_valid(tmp_path):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    result = validator.validate(intent, sample_market_obs(), snapshot, NOW)
    assert result.is_valid
