"""Exact remote authority must survive pending confirmation, cancellation and restart."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from test_live_v1_execution_protection_r3 import _backend

from btc_quant_agent.execution.backend import TestnetExecutionBackend
from btc_quant_agent.execution.binance_signed import BinanceExecutionError
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.live_db import connection

NOW = 1_700_000_000_000


def exact(client, intent, **changes):
    args = client.place_protective_order.call_args.kwargs
    return {"algoId": "r5-stop", "clientAlgoId": args["clientAlgoId"],
            "symbol": intent.symbol, "side": "SELL", "orderType": "STOP_MARKET",
            "positionSide": "BOTH", "reduceOnly": True, "triggerPrice": intent.stop_loss,
            "quantity": "0.1", "algoStatus": "NEW", "algoType": "CONDITIONAL",
            "workingType": "MARK_PRICE", "priceProtect": True, "closePosition": False,
            **changes}


def pending(tmp_path):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "r5-stop"}
    client.query_protective_order.side_effect = BinanceExecutionError("exact query unavailable")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert backend.protections.get_owner(intent).status == "PENDING_CONFIRMATION"
    return backend, client, kill, intent


@pytest.mark.parametrize("omit_status", [False, True])
def test_restart_matching_listing_cannot_confirm_pending(tmp_path, omit_status):
    backend, client, kill, intent = pending(tmp_path)
    listing = exact(client, intent)
    if omit_status:
        listing.pop("algoStatus")
    client.open_protective_orders.return_value = [listing]
    for offset in (1, 2):
        restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
        with pytest.raises(ExecutionBlocked):
            restarted._reconcile_protective_stop(intent, 0.1, NOW + offset)
        owner = restarted.protections.get_owner(intent)
        assert owner.status == "PENDING_CONFIRMATION" and owner.exchange_id == "r5-stop"
        assert not kill.allows_new_risk()
    assert client.place_protective_order.call_count == 1
    assert client.query_protective_order.call_count == 3


def test_exact_recovery_confirms_once_without_second_post(tmp_path):
    backend, client, kill, intent = pending(tmp_path)
    client.open_protective_orders.return_value = [exact(client, intent)]
    client.query_protective_order.side_effect = lambda _: exact(client, intent)
    for offset in (1, 2):
        restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
        assert restarted._reconcile_protective_stop(intent, 0.1, NOW + offset) == "r5-stop"
    assert restarted.protections.get_owner(intent).status == "ACTIVE"
    assert client.place_protective_order.call_count == 1
    with connection(backend.path) as db:
        assert db.execute("SELECT COUNT(*) FROM live_execution_orders WHERE is_protective=1").fetchone()[0] == 1


@pytest.mark.parametrize("change", [
    {"workingType": "CONTRACT_PRICE"}, {"priceProtect": False}, {"closePosition": True},
    {"algoType": "OTHER"}, {"reduceOnly": 1}, {"priceProtect": 1},
    {"closePosition": 0}, {"algoStatus": "CANCELED"},
    {"status": "CANCELED"}, {"type": "TAKE_PROFIT_MARKET"},
])
def test_exact_confirmation_rejects_changed_semantics(tmp_path, change):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "r5-stop"}
    client.query_protective_order.side_effect = lambda _: exact(client, intent, **change)
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert backend.protections.get_owner(intent).status == "PENDING_CONFIRMATION"
    assert not kill.allows_new_risk()


@pytest.mark.parametrize("field", [
    "algoType", "orderType", "workingType", "priceProtect", "closePosition", "reduceOnly",
    "positionSide", "symbol", "side", "triggerPrice", "quantity", "clientAlgoId", "algoId", "algoStatus",
])
def test_confirmation_requires_every_semantic_field(tmp_path, field):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "r5-stop"}
    def response(_):
        raw = exact(client, intent)
        raw.pop(field)
        return raw
    client.query_protective_order.side_effect = response
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert backend.protections.get_owner(intent).status != "ACTIVE"
    assert not kill.allows_new_risk()


@pytest.mark.parametrize("value", [True, "true", "TRUE", "True"])
def test_explicit_boolean_provider_representations(tmp_path, value):
    backend, client, _, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "r5-stop"}
    client.query_protective_order.side_effect = lambda _: exact(client, intent, reduceOnly=value,
        priceProtect=value, closePosition=False if value is True else "FALSE")
    assert backend._reconcile_protective_stop(intent, 0.1, NOW) == "r5-stop"


def test_flat_uncertain_pending_retains_identity_and_blocks_other_owner(tmp_path):
    backend, client, kill, intent = pending(tmp_path)
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0"}]
    client.open_protective_orders.return_value = []
    restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
    with pytest.raises(ExecutionBlocked):
        restarted._reconcile_protective_stop(intent, 0.1, NOW + 1)
    owner = restarted.protections.get_owner(intent)
    assert owner.status == "PENDING_CONFIRMATION" and owner.exchange_id == "r5-stop"
    assert owner.protective_client_id is not None and not kill.allows_new_risk()
    other = SimpleNamespace(intent_id="later", intent_hash="a" * 64, symbol=intent.symbol, side=intent.side)
    with pytest.raises(ExecutionBlocked, match="PROTECTION_OWNER_CONFLICT"):
        restarted.protections.reserve_owner(other, NOW + 2)
    client.cancel_protective_order.assert_not_called()
    assert client.place_protective_order.call_count == 1


@pytest.mark.parametrize("terminal", ["CANCELED", "EXPIRED"])
def test_flat_exact_terminal_releases_without_cancel(tmp_path, terminal):
    backend, client, kill, intent = pending(tmp_path)
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0"}]
    client.query_protective_order.side_effect = lambda _: exact(client, intent, algoStatus=terminal)
    assert backend._reconcile_protective_stop(intent, 0.1, NOW + 1) is None
    assert backend.protections.get_owner(intent).status == "RELEASED"
    client.cancel_protective_order.assert_not_called()
    assert not kill.allows_new_risk()


def test_flat_active_exact_stop_cancellation_uncertainty_survives_restart(tmp_path):
    backend, client, kill, intent = pending(tmp_path)
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0"}]
    client.query_protective_order.side_effect = [exact(client, intent), BinanceExecutionError("cancel query unavailable")]
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW + 1)
    owner = backend.protections.get_owner(intent)
    assert owner.status == "CANCEL_PENDING" and owner.exchange_id == "r5-stop"
    client.query_protective_order.side_effect = lambda _: exact(client, intent, algoStatus="CANCELED")
    restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
    assert restarted._reconcile_protective_stop(intent, 0.1, NOW + 2) is None
    assert restarted.protections.get_owner(intent).status == "RELEASED"
    assert client.cancel_protective_order.call_count == 1
    assert client.place_protective_order.call_count == 1


def test_release_flat_cannot_bypass_pending_remote_authority(tmp_path):
    backend, _, _, intent = pending(tmp_path)
    with pytest.raises(ExecutionBlocked):
        backend.protections.release_flat(intent, NOW + 1)
    assert backend.protections.get_owner(intent).exchange_id == "r5-stop"


@pytest.mark.parametrize("uncertainty", ["not_found", "missing_status"])
def test_pending_matching_listing_still_requires_complete_exact_query(tmp_path, uncertainty):
    backend, client, kill, intent = pending(tmp_path)
    client.open_protective_orders.return_value = [exact(client, intent)]
    if uncertainty == "not_found":
        client.query_protective_order.side_effect = BinanceExecutionError("absent", code=-2013)
    else:
        raw = exact(client, intent)
        raw.pop("algoStatus")
        client.query_protective_order.side_effect = lambda _: raw
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW + 1)
    assert backend.protections.get_owner(intent).status == "PENDING_CONFIRMATION"
    assert not kill.allows_new_risk()
    assert client.place_protective_order.call_count == 1


@pytest.mark.parametrize("structured", [True, False])
def test_flat_absence_requires_structured_exact_provider_authority(tmp_path, structured):
    backend, client, _, intent = pending(tmp_path)
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0"}]
    client.query_protective_order.side_effect = BinanceExecutionError("-2013 absent", code=-2013 if structured else None)
    if structured:
        assert backend._reconcile_protective_stop(intent, 0.1, NOW + 1) is None
        assert backend.protections.get_owner(intent).status == "RELEASED"
    else:
        with pytest.raises(ExecutionBlocked):
            backend._reconcile_protective_stop(intent, 0.1, NOW + 1)
        assert backend.protections.get_owner(intent).exchange_id == "r5-stop"
    client.cancel_protective_order.assert_not_called()


@pytest.mark.parametrize("interruption", ["still_new", "terminal_persistence"])
def test_cancel_restart_preserves_identity_without_repeating_remote_cancel(tmp_path, interruption):
    backend, client, kill, intent = pending(tmp_path)
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0"}]
    client.query_protective_order.side_effect = lambda _: exact(client, intent,
        algoStatus="CANCELED" if interruption == "terminal_persistence" and client.cancel_protective_order.called else "NEW")
    if interruption == "terminal_persistence":
        with connection(backend.path) as db:
            db.execute("CREATE TRIGGER fail_terminal BEFORE UPDATE ON live_protection_owners "
                       "WHEN NEW.status='TERMINAL_CONFIRMED' BEGIN SELECT RAISE(ABORT, 'disk failed'); END")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW + 1)
    assert backend.protections.get_owner(intent).status == "CANCEL_PENDING"
    assert backend.protections.get_owner(intent).exchange_id == "r5-stop"
    restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
    if interruption == "still_new":
        with pytest.raises(ExecutionBlocked):
            restarted._reconcile_protective_stop(intent, 0.1, NOW + 2)
    else:
        with connection(backend.path) as db:
            db.execute("DROP TRIGGER fail_terminal")
        assert restarted._reconcile_protective_stop(intent, 0.1, NOW + 2) is None
        assert restarted.protections.get_owner(intent).status == "RELEASED"
    assert client.cancel_protective_order.call_count == 1
    assert client.place_protective_order.call_count == 1
    assert not kill.allows_new_risk()


def test_filled_entry_pending_restart_cannot_use_aggregate_confirmation(tmp_path):
    from test_live_v1_execution_authorization_r2 import authorized_backend

    backend, _, intent, _, client, receipt = authorized_backend(tmp_path)
    entry = {"orderId": "r5-entry", "clientOrderId": intent.client_order_id,
             "symbol": intent.symbol, "side": intent.side, "status": "FILLED",
             "executedQty": str(intent.quantity), "avgPrice": str(intent.price)}
    def fill(**_):
        client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH",
                                          "positionAmt": str(intent.quantity)}]
        return entry
    client.place_order.side_effect = fill
    client.query_order_by_client_id.return_value = entry
    client.place_protective_order.return_value = {"algoId": "r5-stop"}
    client.query_protective_order.side_effect = BinanceExecutionError("query unavailable")
    with pytest.raises(ExecutionBlocked):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.open_protective_orders.return_value = [exact(client, intent, quantity=str(intent.quantity))]
    restarted = TestnetExecutionBackend(backend.path, client, backend.kill_switch, validator=backend.validator)
    with pytest.raises(ExecutionBlocked):
        restarted.reconcile_authorized(intent.intent_id, NOW + 1)
    owner = restarted.protections.get_owner(intent)
    assert owner.status == "PENDING_CONFIRMATION" and owner.exchange_id == "r5-stop"
    assert not backend.kill_switch.allows_new_risk()
    assert client.place_order.call_count == client.place_protective_order.call_count == 1


@pytest.mark.parametrize("body,expected", [
    (b'{"code": -2013, "msg": "private provider text"}', -2013),
    (b'{"code": "-2013"}', None), (b'{"code": true}', None), (b'not json', None),
])
def test_signed_error_preserves_only_structured_numeric_code(monkeypatch, body, expected):
    import io
    import urllib.error
    from unittest.mock import MagicMock

    from btc_quant_agent.execution.binance_signed import BinanceSignedClient

    failure = urllib.error.HTTPError("https://example.invalid", 400, "bad request", None, io.BytesIO(body))
    monkeypatch.setattr("urllib.request.urlopen", MagicMock(side_effect=failure))
    client = BinanceSignedClient("https://example.invalid", "fake-key", "fake-secret")
    with pytest.raises(BinanceExecutionError) as error:
        client.query_protective_order("r5-stop")
    assert error.value.code == expected
    assert "private provider text" not in str(error.value)
    assert "fake-secret" not in str(error.value)


@pytest.mark.parametrize("structured", [True, False])
def test_entry_transport_absence_uses_provider_code_without_second_post(tmp_path, structured):
    from test_live_v1_execution_authorization_r2 import authorized_backend

    backend, _, _, _, client, receipt = authorized_backend(tmp_path)
    client.place_order.side_effect = BinanceExecutionError("transport unavailable")
    client.query_order_by_client_id.side_effect = BinanceExecutionError("-2013 text", code=-2013 if structured else None)
    if structured:
        report = backend.submit_authorized(receipt.authorization_id, NOW)
        assert report.status == "ABORTED" and report.reason == "TRANSPORT_FAILURE_PROVEN_ABSENT"
    else:
        with pytest.raises(ExecutionBlocked, match="Transport uncertainty"):
            backend.submit_authorized(receipt.authorization_id, NOW)
    client.place_order.assert_called_once()
    client.query_order_by_client_id.assert_called_once()
    client.place_protective_order.assert_not_called()
