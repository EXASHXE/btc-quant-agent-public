"""Independent, offline R4 protection probes against the checked-out production code.

Run with PYTHONPATH=/tmp/b5-r4-independent-code/src:/tmp/b5-r4-independent-code/tests
pytest -q /tmp/b5-r4-evidence/protection/test_independent_protection_probe.py
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_live_v1_execution_protection_r3 import _backend

from btc_quant_agent.execution.backend import TestnetExecutionBackend
from btc_quant_agent.execution.binance_signed import BinanceExecutionError
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.protection import ProtectionStore, parse_protective_exchange_id
from btc_quant_agent.live_db import connection

NOW = 1_700_000_000_000


def exact(client, intent, **changes):
    params = client.place_protective_order.call_args.kwargs
    return {
        "algoId": "independent-stop", "clientAlgoId": params["clientAlgoId"],
        "symbol": intent.symbol, "side": "SELL", "orderType": "STOP_MARKET",
        "positionSide": "BOTH", "reduceOnly": True, "triggerPrice": intent.stop_loss,
        "quantity": str(params["quantity"]), "algoStatus": "NEW", **changes,
    }


@pytest.mark.parametrize("raw", [
    {}, {"algoId": None}, {"orderId": None}, {"algoId": False}, {"algoId": True},
    {"algoId": 0}, {"algoId": -1}, {"algoId": 1.25}, {"algoId": ""},
    {"algoId": " "}, {"algoId": " 1"}, {"algoId": "1 "},
    {"algoId": "None"}, {"algoId": "none"}, {"algoId": "null"},
    {"algoId": []}, {"algoId": {}}, {"algoId": "a/b"},
    {"algoId": "a b"}, {"algoId": "a", "orderId": "b"},
])
def test_malformed_provider_id_is_never_authority(raw):
    with pytest.raises(ExecutionBlocked):
        parse_protective_exchange_id(raw)


@pytest.mark.parametrize("raw,expected", [
    ({"algoId": 12}, "12"), ({"orderId": "A_1-2"}, "A_1-2"),
    ({"algoId": "x", "orderId": "x"}, "x"),
])
def test_valid_provider_aliases(raw, expected):
    assert parse_protective_exchange_id(raw) == expected


@pytest.mark.parametrize("change", [
    {"clientAlgoId": "foreign"}, {"symbol": "ETHUSDT"}, {"side": "BUY"},
    {"orderType": "TAKE_PROFIT_MARKET"}, {"positionSide": "LONG"},
    {"reduceOnly": False}, {"reduceOnly": 1}, {"triggerPrice": 99},
    {"quantity": "0.05"}, {"quantity": "0.2"}, {"quantity": "nan"},
    {"algoStatus": "CANCELED"}, {"algoId": "foreign"},
    {"algoId": None}, {"algoId": "x", "orderId": "y"},
])
def test_post_success_wrong_exact_confirmation_stays_pending(tmp_path, change):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "independent-stop"}
    client.query_protective_order.side_effect = lambda _id: exact(client, intent, **change)
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    owner = backend.protections.get_owner(intent)
    assert owner.status == "PENDING_CONFIRMATION"
    assert owner.exchange_id == "independent-stop"
    assert not kill.allows_new_risk()
    client.query_protective_order.assert_called_once_with("independent-stop")
    with connection(backend.path) as db:
        assert db.execute("SELECT COUNT(*) FROM live_execution_orders WHERE is_protective=1").fetchone()[0] == 0


def test_post_success_query_not_found_keeps_exact_claim_and_blocks_replay(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "independent-stop"}
    client.query_protective_order.side_effect = BinanceExecutionError("-2013 order absent")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    owner = backend.protections.get_owner(intent)
    assert owner.status == "PENDING_CONFIRMATION"
    assert owner.exchange_id == "independent-stop"
    assert not kill.allows_new_risk()
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW + 1)
    assert client.place_protective_order.call_count == 1


def test_exact_confirmation_and_restart_are_idempotent(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "independent-stop"}
    client.query_protective_order.side_effect = lambda _id: exact(client, intent)
    assert backend._reconcile_protective_stop(intent, 0.1, NOW) == "independent-stop"
    with connection(backend.path) as db:
        row = db.execute("SELECT * FROM live_execution_orders WHERE order_id=?", ("independent-stop",)).fetchone()
        assert row["is_protective"] == 1 and row["requested_qty"] == 0.1
    restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
    client.open_protective_orders.return_value = [exact(client, intent)]
    assert restarted._reconcile_protective_stop(intent, 0.1, NOW + 1) == "independent-stop"
    assert client.place_protective_order.call_count == 1
    assert restarted.protections.get_owner(intent).status == "ACTIVE"


@pytest.mark.parametrize("omit_status", [False, True])
def test_pending_restart_promotes_from_open_list_without_exact_query(tmp_path, omit_status):
    """Observed restart behavior: open-list data alone promotes a pending POST."""
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "independent-stop"}
    client.query_protective_order.side_effect = BinanceExecutionError("exact query unavailable")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert backend.protections.get_owner(intent).status == "PENDING_CONFIRMATION"
    assert client.query_protective_order.call_count == 1
    listing = exact(client, intent)
    if omit_status:
        del listing["algoStatus"]
    client.open_protective_orders.return_value = [listing]
    restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
    assert restarted._reconcile_protective_stop(intent, 0.1, NOW + 1) == "independent-stop"
    assert restarted.protections.get_owner(intent).status == "ACTIVE"
    assert client.query_protective_order.call_count == 1
    assert client.place_protective_order.call_count == 1


def test_remote_success_local_insert_failure_rolls_back_and_recovers(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "independent-stop"}
    client.query_protective_order.side_effect = lambda _id: exact(client, intent)
    with connection(backend.path) as db:
        db.execute("CREATE TRIGGER independent_fail_insert BEFORE INSERT ON live_execution_orders "
                   "WHEN NEW.is_protective=1 BEGIN SELECT RAISE(ABORT, 'disk write failure'); END")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert backend.protections.get_owner(intent).status == "PENDING_CONFIRMATION"
    assert not kill.allows_new_risk()
    with connection(backend.path) as db:
        assert db.execute("SELECT COUNT(*) FROM live_execution_orders WHERE is_protective=1").fetchone()[0] == 0
        db.execute("DROP TRIGGER independent_fail_insert")
    client.open_protective_orders.return_value = [exact(client, intent)]
    restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
    assert restarted._reconcile_protective_stop(intent, 0.1, NOW + 1) == "independent-stop"
    assert client.place_protective_order.call_count == 1


@pytest.mark.parametrize("change", [
    {"workingType": "CONTRACT_PRICE"},
    {"priceProtect": False},
    {"closePosition": True},
    {"algoType": "OTHER"},
])
def test_explicitly_wrong_exchange_settings_are_currently_confirmed(tmp_path, change):
    """Observed gap: exact query contains settings that differ from the submitted stop."""
    backend, client, _kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "independent-stop"}
    client.query_protective_order.side_effect = lambda _id: exact(client, intent, **change)
    assert backend._reconcile_protective_stop(intent, 0.1, NOW) == "independent-stop"
    assert backend.protections.get_owner(intent).status == "ACTIVE"


def test_remote_cancel_local_update_failure_keeps_pending_owner(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "independent-stop"}
    client.query_protective_order.side_effect = lambda _id: exact(client, intent)
    backend._reconcile_protective_stop(intent, 0.1, NOW)
    client.open_protective_orders.return_value = [exact(client, intent)]
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0.05"}]
    with connection(backend.path) as db:
        db.execute("CREATE TRIGGER independent_fail_cancel BEFORE UPDATE ON live_execution_orders "
                   "WHEN NEW.is_protective=1 AND NEW.status='CANCELED' "
                   "BEGIN SELECT RAISE(ABORT, 'disk write failure'); END")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW + 1)
    assert client.cancel_protective_order.call_count == 1
    assert backend.protections.get_owner(intent).status == "PENDING_CONFIRMATION"
    assert client.place_protective_order.call_count == 1
    assert not kill.allows_new_risk()


def test_foreign_and_duplicate_open_stops_block_without_mutation(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.open_protective_orders.return_value = [{"clientAlgoId": "foreign", "algoId": "independent-stop"}]
    with pytest.raises(ExecutionBlocked, match="PROTECTION_ORDER_UNKNOWN"):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert not kill.allows_new_risk()
    client.cancel_protective_order.assert_not_called()
    client.place_protective_order.assert_not_called()


def test_pending_unknown_stop_is_released_when_position_goes_flat(tmp_path):
    """Regression probe: this documents a current authority loss, not a desired contract."""
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "independent-stop"}
    client.query_protective_order.side_effect = BinanceExecutionError("query timeout")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    pending = backend.protections.get_owner(intent)
    assert pending.status == "PENDING_CONFIRMATION" and pending.exchange_id == "independent-stop"
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0"}]
    client.open_protective_orders.return_value = []
    assert backend._reconcile_protective_stop(intent, 0.1, NOW + 1) is None
    released = backend.protections.get_owner(intent)
    assert released.status == "RELEASED" and released.exchange_id is None
    assert released.protective_client_id == pending.protective_client_id
    assert not kill.allows_new_risk()


def test_symbol_owner_conflict_survives_pending_and_restart(tmp_path):
    store = ProtectionStore(tmp_path / "owner.db")
    first = SimpleNamespace(intent_id="a", intent_hash="a" * 64, symbol="BTCUSDT", side="BUY")
    second = SimpleNamespace(intent_id="b", intent_hash="b" * 64, symbol="BTCUSDT", side="BUY")
    store.reserve_owner(first, NOW)
    store.next_client_id(first, NOW, 0.1)
    restarted = ProtectionStore(tmp_path / "owner.db")
    with pytest.raises(ExecutionBlocked, match="PROTECTION_OWNER_CONFLICT"):
        restarted.reserve_owner(second, NOW + 1)
