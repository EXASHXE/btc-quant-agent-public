from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_execution_backend import (
    NOW,
    authorize_testnet_intent,
    make_mock_testnet_client,
)
from test_live_v1_execution_intent import setup_approved_state

from btc_quant_agent.execution.backend import TestnetExecutionBackend
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import build_trade_intent
from btc_quant_agent.execution.protection import ProtectionStore
from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor.kill_switch import KillSwitch


def _intent(identity: str, symbol: str = "BTCUSDT") -> SimpleNamespace:
    return SimpleNamespace(intent_id=identity, intent_hash=identity * 64, symbol=symbol, side="BUY")


def test_reservation_is_atomic_for_same_symbol_and_side(tmp_path):
    store = ProtectionStore(tmp_path / "live.db")
    first = _intent("a")
    second = _intent("b")
    owner = store.reserve_owner(first, 100)
    with pytest.raises(ExecutionBlocked, match="PROTECTION_OWNER_CONFLICT"):
        store.reserve_owner(second, 101)
    assert store.get_owner(first) == owner
    assert store.get_owner(second) is None


def test_client_ids_are_exact_bounded_and_unique(tmp_path):
    store = ProtectionStore(tmp_path / "live.db")
    first = _intent("a")
    second = _intent("b", "ETHUSDT")
    store.reserve_owner(first, 100)
    store.reserve_owner(second, 100)
    first_id = store.next_client_id(first, 101)
    second_id = store.next_client_id(second, 101)
    assert len(first_id) <= 36
    assert first_id != second_id
    with pytest.raises(ExecutionBlocked, match="PROTECTION_STOP_UNCERTAIN"):
        store.next_client_id(first, 102)
    store.record_stop(first, first_id, "stop-1", 0.1, 102)
    with connection(store.path) as db:
        db.execute("CREATE TABLE live_execution_orders (order_id TEXT, intent_id TEXT, client_order_id TEXT, is_protective INTEGER, status TEXT)")
    store.confirm_terminal(first, first_id, "stop-1", "CANCELED", 103)
    store.clear_stop(first, first_id, "stop-1", 103)
    assert first_id != store.next_client_id(first, 104)
    assert ProtectionStore(tmp_path / "live.db").get_owner(first).protective_client_id != second_id


def _backend(tmp_path, position_amt):
    store, _, proposal, event_id, _ = setup_approved_state(tmp_path)
    intent = build_trade_intent(
        store,
        sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW),
        proposal.proposal_hash,
        event_id,
        now_ms=NOW,
    )
    client = make_mock_testnet_client(position_amt=position_amt)
    kill = KillSwitch(tmp_path / "live.db")
    backend = TestnetExecutionBackend(tmp_path / "live.db", client, kill)
    backend.protections = ProtectionStore(backend.path)
    authorize_testnet_intent(backend, store, intent, kill, claimed=True)
    client.open_protective_orders.return_value = []
    return backend, client, kill, intent


def test_unknown_similar_stop_is_never_adopted_or_cancelled(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.open_protective_orders.return_value = [
        {
            "symbol": intent.symbol,
            "side": "SELL",
            "orderType": "STOP_MARKET",
            "positionSide": "BOTH",
            "reduceOnly": True, "algoType": "CONDITIONAL", "workingType": "MARK_PRICE",
            "priceProtect": True, "closePosition": False, "algoStatus": "NEW",
            "triggerPrice": intent.stop_loss,
            "algoId": "foreign",
            "clientAlgoId": f"bqa-stop-{intent.client_order_id[:12]}-0100",
            "quantity": "0.1",
        }
    ]
    with pytest.raises(ExecutionBlocked, match="PROTECTION_ORDER_UNKNOWN"):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    client.cancel_protective_order.assert_not_called()
    client.place_protective_order.assert_not_called()
    assert not kill.allows_new_risk()


def test_claimed_intent_without_ledger_fails_closed(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    with connection(backend.path) as db:
        db.execute("DELETE FROM live_protection_owners WHERE intent_id=?", (intent.intent_id,))
    with pytest.raises(ExecutionBlocked, match="PROTECTION_OWNER_MISSING"):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    client.cancel_protective_order.assert_not_called()
    client.place_protective_order.assert_not_called()
    assert not kill.allows_new_risk()


def test_restart_exact_owner_and_flat_cleanup(tmp_path):
    backend, client, _, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "owned-stop"}
    assert backend._reconcile_protective_stop(intent, 0.1, NOW) == "owned-stop"
    owner = backend.protections.get_owner(intent)
    assert owner.exchange_id == "owned-stop"
    assert (
        owner.protective_client_id == client.place_protective_order.call_args.kwargs["clientAlgoId"]
    )

    restarted = TestnetExecutionBackend(backend.path, client, backend.kill_switch)
    restarted.protections = ProtectionStore(backend.path)
    restarted.validator = backend.validator
    client.open_protective_orders.return_value = [
        {
            "symbol": intent.symbol,
            "side": "SELL",
            "orderType": "STOP_MARKET",
            "positionSide": "BOTH",
            "reduceOnly": True, "algoType": "CONDITIONAL", "workingType": "MARK_PRICE",
            "priceProtect": True, "closePosition": False, "algoStatus": "NEW",
            "triggerPrice": intent.stop_loss,
            "algoId": "owned-stop",
            "clientAlgoId": owner.protective_client_id,
            "quantity": "0.1",
        },
        {
            "symbol": intent.symbol,
            "side": "SELL",
            "orderType": "STOP_MARKET",
            "positionSide": "BOTH",
            "reduceOnly": True, "algoType": "CONDITIONAL", "workingType": "MARK_PRICE",
            "priceProtect": True, "closePosition": False, "algoStatus": "NEW",
            "triggerPrice": intent.stop_loss,
            "algoId": "foreign-stop",
            "clientAlgoId": "bqa-stop-similar",
            "quantity": "0.1",
        },
    ]
    client.positions.return_value = [
        {"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0"}
    ]
    assert restarted._reconcile_protective_stop(intent, 0.1, NOW + 1) is None
    client.cancel_protective_order.assert_called_once_with(intent.symbol, "owned-stop")
    assert restarted.protections.get_owner(intent).status == "RELEASED"
    assert restarted._reconcile_protective_stop(intent, 0.1, NOW + 2) is None
    client.cancel_protective_order.assert_called_once()


@pytest.mark.parametrize("field,value", [
    ("side", "BUY"), ("triggerPrice", 1), ("reduceOnly", False),
    ("positionSide", "LONG"), ("orderType", "TAKE_PROFIT_MARKET"), ("symbol", "ETHUSDT"),
])
def test_exact_owned_id_is_insufficient_without_protective_contract(tmp_path, field, value):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client_id = backend.protections.next_client_id(intent, NOW)
    backend.protections.record_stop(intent, client_id, "owned-algo", 0.1, NOW)
    algo = {"algoId": "owned-algo", "clientAlgoId": client_id, "symbol": intent.symbol,
            "side": "SELL", "orderType": "STOP_MARKET", "positionSide": "BOTH",
            "reduceOnly": True, "triggerPrice": intent.stop_loss, "quantity": "0.1"}
    algo[field] = value
    client.open_protective_orders.return_value = [algo]
    with pytest.raises(ExecutionBlocked, match="PROTECTION_CONTRACT_MISMATCH"):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    client.cancel_protective_order.assert_not_called()
    client.place_protective_order.assert_not_called()
    assert not kill.allows_new_risk()
