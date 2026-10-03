"""Safety assertions for independently reproduced protection defects; failures are evidence."""
import pytest
from test_live_v1_execution_protection_r3 import _backend
from test_live_v1_execution_protection_r4 import NOW, confirmation

from btc_quant_agent.execution.backend import TestnetExecutionBackend
from btc_quant_agent.execution.binance_signed import BinanceExecutionError
from btc_quant_agent.execution.guard import ExecutionBlocked


@pytest.mark.parametrize("omit_status", [False, True])
def test_pending_restart_requires_successful_exact_id_query(tmp_path, omit_status):
    backend, client, kill, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "owned-stop"}
    client.query_protective_order.side_effect = BinanceExecutionError("exact query unavailable")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert backend.protections.get_owner(intent).status == "PENDING_CONFIRMATION"
    listing = confirmation(client, intent)
    if omit_status:
        listing.pop("algoStatus")
    client.open_protective_orders.return_value = [listing]
    restarted = TestnetExecutionBackend(backend.path, client, kill, validator=backend.validator)
    with pytest.raises(ExecutionBlocked):
        restarted._reconcile_protective_stop(intent, 0.1, NOW + 1)
    assert restarted.protections.get_owner(intent).status != "ACTIVE"


@pytest.mark.parametrize("changed", [
    {"workingType": "CONTRACT_PRICE"}, {"priceProtect": False},
    {"closePosition": True}, {"algoType": "OTHER"},
])
def test_exact_confirmation_must_preserve_submitted_stop_semantics(tmp_path, changed):
    backend, client, _, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "owned-stop"}
    client.query_protective_order.side_effect = lambda _: confirmation(client, intent, **changed)
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    assert backend.protections.get_owner(intent).status != "ACTIVE"


def test_flat_position_must_retain_unresolved_exact_stop_identity(tmp_path):
    backend, client, _, intent = _backend(tmp_path, 0.1)
    client.place_protective_order.return_value = {"algoId": "owned-stop"}
    client.query_protective_order.side_effect = BinanceExecutionError("exact query unavailable")
    with pytest.raises(ExecutionBlocked):
        backend._reconcile_protective_stop(intent, 0.1, NOW)
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0"}]
    client.open_protective_orders.return_value = []
    backend._reconcile_protective_stop(intent, 0.1, NOW + 1)
    owner = backend.protections.get_owner(intent)
    assert owner.status == "PENDING_CONFIRMATION"
    assert owner.exchange_id == "owned-stop"
