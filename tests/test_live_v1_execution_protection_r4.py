"""Protection is installed only after exact exchange confirmation and atomic storage."""

from __future__ import annotations

import pytest
from test_live_v1_execution_protection_r3 import _backend

from btc_quant_agent.execution.backend import TestnetExecutionBackend
from btc_quant_agent.execution.binance_signed import BinanceExecutionError
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.live_db import connection

NOW = 1_700_000_000_000


def confirmation(client, intent, **changes):
    args = client.place_protective_order.call_args.kwargs
    return {
        "algoId": "owned-stop", "clientAlgoId": args["clientAlgoId"],
        "symbol": intent.symbol, "side": "SELL", "orderType": "STOP_MARKET",
        "positionSide": "BOTH", "reduceOnly": True, "triggerPrice": intent.stop_loss,
        "quantity": "0.1", "algoStatus": "CANCELED" if client.cancel_protective_order.called else "NEW",
        "algoType": "CONDITIONAL",
        "workingType": "MARK_PRICE", "priceProtect": True, "closePosition": False, **changes,
    }


@pytest.mark.parametrize("raw", [
    {}, {"algoId": None}, {"algoId": ""}, {"algoId": " "}, {"algoId": True},
    {"algoId": "None"}, {"algoId": "null"}, {"algoId": []}, {"algoId": {}},
    {"algoId": 1.5}, {"algoId": 0}, {"algoId": "id with spaces"},
    {"algoId": "owned-stop", "orderId": "another-stop"},
])
def test_malformed_placement_identity_never_reports_installed_stop(tmp_path, raw):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = raw
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    owner = backend.protections.get_owner(intent)
    assert owner.status == "PENDING_CONFIRMATION"
    assert owner.protective_client_id is not None
    assert owner.exchange_id is None
    assert not kill.allows_new_risk()
    with connection(backend.path) as db:
        assert db.execute("SELECT COUNT(*) FROM live_execution_orders WHERE is_protective=1").fetchone()[0] == 0


@pytest.mark.parametrize("changes", [
    {"symbol": "ETHUSDT"}, {"side": "BUY"}, {"orderType": "TAKE_PROFIT_MARKET"},
    {"positionSide": "LONG"}, {"reduceOnly": False}, {"reduceOnly": 1},
    {"triggerPrice": 99}, {"quantity": "0.2"}, {"quantity": "nan"},
    {"clientAlgoId": "foreign"}, {"algoId": "foreign"}, {"algoStatus": "CANCELED"},
    {"algoId": None},
])
def test_authoritative_wrong_contract_blocks_confirmation(tmp_path, changes):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "owned-stop"}
    client.query_protective_order.side_effect = lambda _id: confirmation(client, intent, **changes)
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert backend.protections.get_owner(intent).status == "PENDING_CONFIRMATION"
    assert not kill.allows_new_risk()


def test_not_found_confirmation_retains_exact_owner_and_blocks_risk(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "owned-stop"}
    client.query_protective_order.side_effect = BinanceExecutionError("-2013 absent")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert not kill.allows_new_risk()
    owner = backend.protections.get_owner(intent)
    assert owner.status == "PENDING_CONFIRMATION"
    assert owner.protective_client_id == client.place_protective_order.call_args.kwargs["clientAlgoId"]


def test_exact_confirmation_atomically_installs_owner_and_order(tmp_path):
    backend, client, _, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "owned-stop"}
    client.query_protective_order.side_effect = lambda _id: confirmation(client, intent)
    assert backend._reconcile_protective_stop(intent, 0.1, NOW) == "owned-stop"
    client.query_protective_order.assert_called_once_with("owned-stop")
    owner = backend.protections.get_owner(intent)
    assert owner.status == "ACTIVE"
    assert owner.exchange_id == "owned-stop"
    with connection(backend.path) as db:
        row = db.execute("SELECT * FROM live_execution_orders WHERE order_id='owned-stop'").fetchone()
        assert row["client_order_id"] == owner.protective_client_id
        assert row["requested_qty"] == 0.1
        assert row["status"] == "NEW"


@pytest.mark.parametrize("interruption", ["query", "persistence"])
def test_restart_recovers_remote_stop_without_second_placement(tmp_path, interruption):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "owned-stop"}
    exact = lambda _id: confirmation(client, intent)
    if interruption == "query":
        client.query_protective_order.side_effect = BinanceExecutionError("query uncertainty")
    else:
        client.query_protective_order.side_effect = exact
        with connection(backend.path) as db:
            db.execute("CREATE TRIGGER fail_protective_insert BEFORE INSERT ON live_execution_orders "
                       "WHEN NEW.is_protective=1 BEGIN SELECT RAISE(ABORT, 'local write failed'); END")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    pending = backend.protections.get_owner(intent)
    assert pending.status == "PENDING_CONFIRMATION"
    assert not kill.allows_new_risk()
    if interruption == "persistence":
        with connection(backend.path) as db:
            db.execute("DROP TRIGGER fail_protective_insert")
            assert db.execute("SELECT COUNT(*) FROM live_execution_orders WHERE is_protective=1").fetchone()[0] == 0
    client.query_protective_order.side_effect = exact
    client.open_protective_orders.return_value = [confirmation(client, intent)]
    restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
    assert restarted._reconcile_protective_stop(intent, 0.1, NOW + 1) == "owned-stop"
    assert restarted.protections.get_owner(intent).status == "ACTIVE"
    assert client.place_protective_order.call_count == 1


def test_pending_missing_owner_stop_cannot_blindly_place_again(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": None}
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW + 1)
    assert client.place_protective_order.call_count == 1
    assert not kill.allows_new_risk()


def test_filled_entry_malformed_stop_is_failed_closed(tmp_path):
    from test_live_v1_execution_authorization_r2 import authorized_backend

    backend, _, intent, _, client, receipt = authorized_backend(tmp_path)
    kill = backend.kill_switch
    client.place_order.return_value = {
        "orderId": "entry-filled", "clientOrderId": intent.client_order_id,
        "symbol": intent.symbol, "side": intent.side, "status": "FILLED",
        "executedQty": str(intent.quantity), "avgPrice": str(intent.price),
    }
    def filled_entry(**_params):
        client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH",
                                          "positionAmt": str(intent.quantity)}]
        return client.place_order.return_value

    client.place_order.side_effect = filled_entry
    client.place_protective_order.return_value = {"algoId": None}
    with pytest.raises(ExecutionBlocked):
        backend.submit_authorized(receipt.authorization_id, NOW)
    assert backend.protections.get_owner(intent).status == "PENDING_CONFIRMATION"
    assert not kill.allows_new_risk()
    with connection(backend.path) as db:
        assert db.execute("SELECT status FROM live_execution_orders WHERE order_id='entry-filled'").fetchone()[0] == "FILLED"
        assert db.execute("SELECT COUNT(*) FROM live_execution_orders WHERE is_protective=1").fetchone()[0] == 0


@pytest.mark.parametrize("failure", ["cancel_persistence", "replacement_reservation"])
def test_remote_cancel_then_local_failure_never_leaves_risk_enabled(tmp_path, failure):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "owned-stop"}
    client.query_protective_order.side_effect = lambda _id: confirmation(client, intent)
    backend._reconcile_protective_stop(intent, 0.1, NOW)
    client.open_protective_orders.return_value = [confirmation(client, intent)]
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0.05"}]
    with connection(backend.path) as db:
        if failure == "cancel_persistence":
            db.execute("CREATE TRIGGER fail_cancel_write BEFORE UPDATE ON live_execution_orders "
                       "WHEN NEW.is_protective=1 AND NEW.status='CANCELED' "
                       "BEGIN SELECT RAISE(ABORT, 'write failed'); END")
        else:
            db.execute("CREATE TRIGGER fail_next_reservation BEFORE UPDATE ON live_protection_owners "
                       "WHEN OLD.protective_client_id IS NULL AND NEW.protective_client_id IS NOT NULL "
                       "BEGIN SELECT RAISE(ABORT, 'write failed'); END")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW + 1)
    client.cancel_protective_order.assert_called_once_with(intent.symbol, "owned-stop")
    assert backend.protections.get_owner(intent).status != "ACTIVE"
    assert not kill.allows_new_risk()
    assert client.place_protective_order.call_count == 1
