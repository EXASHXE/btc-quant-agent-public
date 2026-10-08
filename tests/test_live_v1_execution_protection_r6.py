from __future__ import annotations

import math
from typing import Any

import pytest
from test_live_v1_execution_protection_r3 import _backend

from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.protection import (
    protective_bool_field,
    protective_numeric_field,
    protective_status_field,
    protective_text_field,
)

NOW = 1_700_000_000_000


def exact(client, intent, **changes: Any) -> dict[str, Any]:
    args = client.place_protective_order.call_args.kwargs
    return {
        "algoId": "r6-stop",
        "clientAlgoId": args["clientAlgoId"],
        "symbol": intent.symbol,
        "side": "SELL",
        "orderType": "STOP_MARKET",
        "positionSide": "BOTH",
        "reduceOnly": True,
        "triggerPrice": intent.stop_loss,
        "quantity": "0.1",
        "algoStatus": "NEW",
        "algoType": "CONDITIONAL",
        "workingType": "MARK_PRICE",
        "priceProtect": True,
        "closePosition": False,
        **changes,
    }


# --- R6-01 Unit Attacks: Direct Helper Validation ---


@pytest.mark.parametrize(
    "payload",
    [
        {"quantity": 1.0, "origQty": True},
        {"quantity": True, "origQty": 1.0},
        {"quantity": False, "origQty": False},
        {"quantity": 1.0, "origQty": False},
        {"quantity": True},
        {"origQty": False},
    ],
)
def test_protective_numeric_field_rejects_boolean(payload: dict[str, Any]) -> None:
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_numeric_field(payload, "quantity", "origQty")


@pytest.mark.parametrize(
    "invalid_val",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        "NaN",
        "Infinity",
        "-Infinity",
        "nan",
        "",
        "   ",
        [],
        {},
        [1.0],
        {"val": 1.0},
        None,
    ],
)
def test_protective_numeric_field_rejects_nan_inf_unsupported(invalid_val: Any) -> None:
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_numeric_field({"quantity": invalid_val}, "quantity")
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_numeric_field({"quantity": 1.0, "origQty": invalid_val}, "quantity", "origQty")


def test_protective_numeric_field_canonical_equivalence() -> None:
    # Decimal string vs float
    val = protective_numeric_field({"quantity": 0.1, "origQty": "0.100"}, "quantity", "origQty")
    assert math.isclose(val, 0.1)

    # String integer vs int
    val2 = protective_numeric_field({"quantity": "100", "origQty": 100}, "quantity", "origQty")
    assert val2 == 100.0

    # Exponential string notation
    val3 = protective_numeric_field({"quantity": "1e-1", "origQty": "0.10"}, "quantity", "origQty")
    assert math.isclose(val3, 0.1)


def test_protective_numeric_field_rejects_conflicts() -> None:
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_numeric_field({"quantity": "0.100", "origQty": "0.200"}, "quantity", "origQty")
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_numeric_field({"quantity": 1.0, "origQty": 1.0001}, "quantity", "origQty")


def test_protective_text_and_status_fields() -> None:
    # Text rejects non-string types
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_text_field({"orderType": "STOP_MARKET", "type": True}, "orderType", "type")
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_text_field({"orderType": "STOP_MARKET", "type": 123}, "orderType", "type")
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_text_field({"orderType": "STOP_MARKET", "type": "TAKE_PROFIT_MARKET"}, "orderType", "type")

    # Status rejects non-string types and disallowed values
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_status_field(
            {"algoStatus": "NEW", "status": True}, "algoStatus", "status", allowed_statuses=frozenset({"NEW"})
        )
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_status_field(
            {"algoStatus": "NEW", "status": "FILLED"}, "algoStatus", "status", allowed_statuses=frozenset({"NEW"})
        )
    assert (
        protective_status_field(
            {"algoStatus": "NEW", "status": "NEW"}, "algoStatus", "status", allowed_statuses=frozenset({"NEW"})
        )
        == "NEW"
    )


def test_protective_bool_field() -> None:
    # Bool field rejects integer/coercive types
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_bool_field({"priceProtect": True, "protectPrice": 1}, "priceProtect", "protectPrice")
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_bool_field({"priceProtect": False, "protectPrice": 0}, "priceProtect", "protectPrice")
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        protective_bool_field({"priceProtect": "invalid"}, "priceProtect")
    assert protective_bool_field({"priceProtect": True, "protectPrice": True}, "priceProtect", "protectPrice") is True
    assert protective_bool_field({"priceProtect": "true", "protectPrice": True}, "priceProtect", "protectPrice") is True


# --- R6-01 Backend Integration Attacks ---


@pytest.mark.parametrize(
    "corrupt_change",
    [
        {"quantity": 1.0, "origQty": True},
        {"quantity": True, "origQty": 1.0},
        {"triggerPrice": 50000.0, "stopPrice": False},
        {"triggerPrice": False, "stopPrice": 50000.0},
        {"origQty": float("nan")},
        {"origQty": float("inf")},
        {"origQty": "NaN"},
        {"origQty": ""},
        {"origQty": {}},
        {"origQty": [0.1]},
        {"origQty": "0.200", "quantity": "0.100"},
        {"type": True},
        {"status": False},
        {"priceProtect": 1},
        {"closePosition": 0},
    ],
)
def test_backend_reconciliation_rejects_malformed_aliases(tmp_path, corrupt_change: dict[str, Any]) -> None:
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "r6-stop"}
    client.query_protective_order.side_effect = lambda _: exact(client, intent, **corrupt_change)

    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        backend._reconcile_protective_stop(intent, 0.1, NOW)

    owner = backend.protections.get_owner(intent)
    assert owner is not None
    assert owner.status != "ACTIVE"
    assert not kill.allows_new_risk()


def test_valid_equivalent_aliases_confirms_active_once(tmp_path) -> None:
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "r6-stop"}
    client.query_protective_order.side_effect = lambda _: exact(
        client,
        intent,
        quantity="0.100",
        origQty=0.1,
        triggerPrice=str(intent.stop_loss),
        stopPrice=intent.stop_loss,
    )

    result = backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert result == "r6-stop"
    owner = backend.protections.get_owner(intent)
    assert owner is not None
    assert owner.status == "ACTIVE"
    assert kill.allows_new_risk()


def test_cross_finding_valid_primary_with_boolean_alias_trips_kill_switch(tmp_path) -> None:
    """Cross-finding: Valid primary quantity + boolean origQty alias fails closed."""
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "r6-stop"}
    client.query_protective_order.side_effect = lambda _: exact(
        client, intent, quantity=0.1, origQty=True
    )

    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)

    assert not kill.allows_new_risk()
    assert backend.protections.get_owner(intent).status != "ACTIVE"
