"""Cross-finding local recovery checks; every exchange method is a fake."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from test_live_v1_execution_authorization_r2 import authorized_backend
from test_live_v1_execution_placement_r3 import fresh_account, placement
from test_live_v1_execution_validator import NOW, sample_market_obs

from btc_quant_agent.execution.backend import DryRunExecutionBackend, TestnetExecutionBackend
from btc_quant_agent.execution.binance_signed import BinanceExecutionError
from btc_quant_agent.execution.executor import LiveExecutionService
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.live_db import connection


def recovered_service(tmp_path, *, filled=False):
    old, validator, intent, _snapshot, client, receipt = authorized_backend(tmp_path)
    assert old.authorizations.claim(receipt, NOW)
    old.protections.reserve_owner(intent, NOW)
    qty = intent.quantity / 2 if filled else 0.0
    client.query_order_by_client_id.return_value = {
        "clientOrderId": intent.client_order_id,
        "symbol": intent.symbol,
        "side": intent.side,
        "orderId": "persisted-exchange-entry",
        "status": "PARTIALLY_FILLED" if filled else "NEW",
        "executedQty": str(qty),
        "avgPrice": str(intent.price if filled else 0),
    }
    client.positions.return_value = [
        {"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": str(qty)}
    ]
    client.open_protective_orders.return_value = []
    client.place_protective_order.return_value = {"algoId": "recovered-owned-stop"}
    backend = TestnetExecutionBackend(
        old.path,
        client,
        old.kill_switch,
        validator=validator,
        clock_ms=lambda: intent.expires_at_ms + 1,
    )
    watch, market = MagicMock(), MagicMock()
    watch.latest_snapshot.return_value = None
    market.latest_observation.return_value = None
    service = LiveExecutionService(
        validator.intent_store,
        validator.live_store,
        watch,
        market,
        validator,
        old.kill_switch,
        DryRunExecutionBackend(old.path),
        backend,
    )
    return service, backend, intent, client


@pytest.mark.parametrize("filled", [False, True])
def test_restart_expired_authority_reconciles_active_order_and_protection(tmp_path, filled):
    service, backend, intent, client = recovered_service(tmp_path, filled=filled)
    backend.validator.tactical_validity_provider = lambda _symbol, _now: False
    backend.kill_switch.allows_new_risk = lambda: False
    report = asyncio.run(
        service.execute_approved_intent(intent.intent_id, intent.expires_at_ms + 1)
    )
    assert report.status == ("PARTIALLY_FILLED" if filled else "NEW")
    client.query_order_by_client_id.assert_called_once_with(intent.symbol, intent.client_order_id)
    client.place_order.assert_not_called()
    client.change_margin_type.assert_not_called()
    if filled:
        assert report.protective_stop_id == "recovered-owned-stop"
        assert client.place_protective_order.call_args.kwargs["quantity"] == intent.quantity / 2
    else:
        client.place_protective_order.assert_not_called()
    assert intent.intent_id in backend.validator.intent_store.unfinished_intent_ids()


def test_claimed_absent_entry_expired_receipt_never_resubmits(tmp_path):
    service, backend, intent, client = recovered_service(tmp_path)
    client.query_order_by_client_id.side_effect = BinanceExecutionError(
        "-2013 Order does not exist"
    )
    report = asyncio.run(
        service.execute_approved_intent(intent.intent_id, intent.expires_at_ms + 1)
    )
    assert report.reason == "ENTRY_PROVEN_ABSENT_NO_NEW_PLACEMENT"
    assert report.status == "UNKNOWN"
    client.place_order.assert_not_called()
    client.change_leverage.assert_not_called()
    assert backend.validator.intent_store.has_existing_side_effect(intent.intent_id)


def test_legacy_aborted_claim_is_not_forgotten(tmp_path):
    service, backend, intent, client = recovered_service(tmp_path)
    backend.validator.intent_store.update_status(
        intent.intent_id, "ABORTED", reason="OLD_STALE_GATE", now_ms=NOW
    )
    assert intent.intent_id in backend.validator.intent_store.unfinished_intent_ids()
    assert (
        asyncio.run(
            service.execute_approved_intent(intent.intent_id, intent.expires_at_ms + 1)
        ).status
        == "NEW"
    )
    client.place_order.assert_not_called()


@pytest.mark.parametrize("component", ["mark", "book", "kline"])
def test_recent_composite_cannot_mask_stale_required_component_at_placement(tmp_path, component):
    backend, _, _, _, client, receipt, _ = placement(tmp_path)
    backend.market_provider.return_value = sample_market_obs(
        **{f"{component}_source_timestamp_ms": NOW - 20_000}
    )
    with pytest.raises(ExecutionBlocked, match=f"MARKET_{component.upper()}_STALE"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.place_order.assert_not_called()
    client.change_margin_type.assert_not_called()


def test_forced_changed_safe_snapshot_receives_new_immutable_receipt(tmp_path):
    backend, _, intent, snapshot, client, receipt, _ = placement(tmp_path)
    changed = fresh_account(snapshot, available_balance_usdt=snapshot.available_balance_usdt - 1)
    backend.account_provider.return_value = changed
    backend.submit_authorized(receipt.authorization_id, NOW)
    latest_id = backend.authorizations.for_claimed_intent(intent.intent_id)
    latest, _, account, _ = backend.authorizations.load(latest_id)
    assert latest_id != receipt.authorization_id
    assert account.snapshot_hash == changed.snapshot_hash
    assert latest.expires_at_ms == receipt.expires_at_ms
    assert backend.authorizations.load(receipt.authorization_id)[0] == receipt
    client.place_order.assert_called_once()
    with connection(backend.path) as db:
        assert db.execute("SELECT COUNT(*) FROM live_execution_claims").fetchone()[0] == 1


def test_delayed_receipt_plus_account_change_is_rejected_before_fake_entry(tmp_path):
    backend, _, _, snapshot, client, receipt, clock = placement(tmp_path)
    backend.account_provider.return_value = fresh_account(snapshot, available_balance_usdt=0)
    clock["now"] = receipt.expires_at_ms + 1
    with pytest.raises(ExecutionBlocked, match="AUTHORIZATION_EXPIRED"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.place_order.assert_not_called()
    client.change_margin_type.assert_not_called()


@pytest.mark.parametrize("missing", ["clientOrderId", "symbol", "side"])
def test_incomplete_entry_identity_is_not_adopted(tmp_path, missing):
    backend, _, _, _, client, receipt, _ = placement(tmp_path)
    del client.place_order.return_value[missing]
    with pytest.raises(ExecutionBlocked, match="ORDER_IDENTITY_CONFLICT"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.place_protective_order.assert_not_called()
    with connection(backend.path) as db:
        assert db.execute("SELECT COUNT(*) FROM live_execution_orders").fetchone()[0] == 0


def test_manual_same_side_position_cannot_create_aggregate_risk_owner(tmp_path):
    from btc_quant_agent.account_watch import PositionV1
    backend, _, _, snapshot, client, receipt, _ = placement(tmp_path)
    backend.account_provider.return_value = fresh_account(snapshot, positions=(PositionV1(
        symbol="BTCUSDT", quantity=0.5, entry_price=100, mark_price=100,
        unrealized_pnl_usdt=0, leverage=2, liquidation_price=None,
        margin_type="ISOLATED", observed_at_ms=NOW,
    ),))
    with pytest.raises(ExecutionBlocked, match="CURRENT_POSITION_OWNER_CONFLICT"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.place_order.assert_not_called()
    client.change_margin_type.assert_not_called()


def test_repeated_cancellation_keeps_request_owned_until_durable_result(tmp_path):
    import threading
    backend, validator, intent, snapshot, client, _ = authorized_backend(tmp_path)
    started, finish = threading.Event(), threading.Event()
    def place(**_kwargs):
        started.set()
        assert finish.wait(5)
        return {"orderId": "double-cancel-entry", "clientOrderId": intent.client_order_id,
                "symbol": intent.symbol, "side": intent.side, "status": "NEW", "executedQty": "0"}
    client.place_order.side_effect = place
    watch, market = MagicMock(), MagicMock()
    watch.latest_snapshot.return_value = snapshot
    market.latest_observation.return_value = sample_market_obs()
    service = LiveExecutionService(validator.intent_store, validator.live_store, watch, market,
                                   validator, backend.kill_switch, DryRunExecutionBackend(backend.path), backend)
    async def run():
        task = asyncio.create_task(service.execute_approved_intent(intent.intent_id, NOW))
        assert await asyncio.to_thread(started.wait, 3)
        for _ in range(2):
            task.cancel()
            await asyncio.sleep(0.01)
            assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    with connection(backend.path) as db:
        assert db.execute("SELECT status FROM live_trade_intents WHERE intent_id=?", (intent.intent_id,)).fetchone()[0] == "NEW"
        assert db.execute("SELECT COUNT(*) FROM live_execution_orders WHERE is_protective=0").fetchone()[0] == 1
    client.place_order.assert_called_once()


def test_settled_owner_never_claims_a_later_same_symbol_position(tmp_path):
    service, backend, intent, client = recovered_service(tmp_path, filled=True)
    report = asyncio.run(service.reconcile_intent(intent.intent_id, NOW))
    owner = backend.protections.get_owner(intent)
    client.open_protective_orders.return_value = [{
        "algoId": report.protective_stop_id, "clientAlgoId": owner.protective_client_id,
        "symbol": intent.symbol, "side": "SELL", "orderType": "STOP_MARKET", "positionSide": "BOTH",
        "reduceOnly": True, "triggerPrice": intent.stop_loss, "quantity": intent.quantity / 2,
    }]
    client.query_order_by_client_id.return_value.update(status="FILLED", executedQty=str(intent.quantity))
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "0"}]
    asyncio.run(service.reconcile_intent(intent.intent_id, NOW + 1))
    assert backend.protections.get_owner(intent).status == "RELEASED"
    assert intent.intent_id not in backend.validator.intent_store.unfinished_intent_ids()
    client.positions.return_value = [{"symbol": intent.symbol, "positionSide": "BOTH", "positionAmt": "2"}]
    client.positions.reset_mock()
    client.cancel_protective_order.reset_mock()
    client.place_protective_order.reset_mock()
    assert backend.reconcile_authorized(intent.intent_id, NOW + 2).protective_stop_id is None
    client.positions.assert_not_called()
    client.cancel_protective_order.assert_not_called()
    client.place_protective_order.assert_not_called()


def test_proven_pre_entry_abort_releases_owner_only_after_absence_and_flat(tmp_path):
    backend, _, intent, snapshot, client, receipt, _ = placement(tmp_path)
    backend.account_provider.side_effect = [snapshot, fresh_account(snapshot, available_balance_usdt=0.01)]
    with pytest.raises(ExecutionBlocked, match="INSUFFICIENT_MARGIN"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.place_order.assert_not_called()
    assert backend.protections.get_owner(intent).status == "RESERVED"
    client.query_order_by_client_id.side_effect = BinanceExecutionError("-2013 Order does not exist")
    assert backend.reconcile_authorized(intent.intent_id, NOW).reason == "PROVEN_PRE_ENTRY_ABORTED"
    assert backend.protections.get_owner(intent).status == "RELEASED"
    assert intent.intent_id not in backend.validator.intent_store.unfinished_intent_ids()


@pytest.mark.parametrize("terminal", ["CANCELED", "EXPIRED", "REJECTED"])
def test_zero_fill_terminal_order_retires_exact_owner(tmp_path, terminal):
    service, backend, intent, client = recovered_service(tmp_path)
    client.query_order_by_client_id.return_value["status"] = terminal
    report = asyncio.run(service.reconcile_intent(intent.intent_id, NOW))
    assert report.status == terminal
    assert backend.protections.get_owner(intent).status == "RELEASED"
    assert intent.intent_id not in backend.validator.intent_store.unfinished_intent_ids()
    client.place_order.assert_not_called()
    client.place_protective_order.assert_not_called()
