"""Persisted validation authority must precede every mocked TESTNET side effect."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest
from test_live_v1_execution_backend import make_mock_testnet_client
from test_live_v1_execution_validator import NOW, sample_market_obs, setup_validator_and_intent

from btc_quant_agent.execution.backend import TestnetExecutionBackend
from btc_quant_agent.execution.guard import ExecutionBlocked


def authorized_backend(tmp_path):
    validator, intent, snapshot, kill = setup_validator_and_intent(tmp_path)
    client = make_mock_testnet_client(position_amt=0.0)
    client.place_order.return_value = {
        "orderId": "local-fake-order", "status": "NEW", "executedQty": "0", "avgPrice": "0",
    }
    backend = TestnetExecutionBackend(tmp_path / "live.db", client, kill, validator=validator)
    receipt = validator.authorize(intent.intent_id, sample_market_obs(), snapshot, NOW)
    return backend, validator, intent, snapshot, client, receipt


def test_unapproved_object_cannot_reach_any_mutation(tmp_path):
    _validator, intent, _snapshot, kill = setup_validator_and_intent(tmp_path)
    client = make_mock_testnet_client()
    client.place_order.return_value = {"orderId": "fake", "status": "NEW", "executedQty": "0"}
    backend = TestnetExecutionBackend(tmp_path / "live.db", client, kill)
    with pytest.raises(ExecutionBlocked, match="AUTHORIZATION_REQUIRED"):
        backend.submit_intent(intent, NOW)
    for name in ("change_margin_type", "change_leverage", "place_order", "cancel_order", "place_protective_order"):
        getattr(client, name).assert_not_called()


def test_valid_authorization_replay_places_one_order(tmp_path):
    backend, _validator, _intent, _snapshot, client, receipt = authorized_backend(tmp_path)
    first = backend.submit_authorized(receipt.authorization_id, NOW)
    second = backend.submit_authorized(receipt.authorization_id, NOW + 1)
    assert first.order_id == second.order_id
    client.place_order.assert_called_once()


def test_concurrent_authorized_calls_do_not_submit_twice(tmp_path):
    backend, _validator, _intent, _snapshot, client, receipt = authorized_backend(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(backend.submit_authorized, receipt.authorization_id, NOW) for _ in range(2)]
        for future in futures:
            try:
                future.result()
            except ExecutionBlocked:
                pass
    client.place_order.assert_called_once()


def test_expired_authorization_precedes_mutation(tmp_path):
    backend, _validator, _intent, _snapshot, client, receipt = authorized_backend(tmp_path)
    with pytest.raises(ExecutionBlocked, match="AUTHORIZATION_EXPIRED"):
        backend.submit_authorized(receipt.authorization_id, receipt.expires_at_ms)
    client.change_margin_type.assert_not_called()
    client.change_leverage.assert_not_called()
    client.place_order.assert_not_called()


def test_unbound_signed_client_is_rejected_before_transport(monkeypatch):
    from btc_quant_agent.execution.binance_signed import BinanceSignedClient
    transport = MagicMock()
    monkeypatch.setattr("urllib.request.urlopen", transport)
    client = BinanceSignedClient("https://example.invalid", "placeholder", "placeholder")
    with pytest.raises(ExecutionBlocked):
        client._signed_request("POST", "/fapi/v1/order", {"symbol": "BTCUSDT"})
    transport.assert_not_called()


@pytest.mark.parametrize("target", ["authorization", "account", "market", "intent"])
def test_persisted_authority_payload_tamper_precedes_all_mutations(tmp_path, target):
    import json

    from btc_quant_agent.live_db import connection
    backend, _validator, intent, _snapshot, client, receipt = authorized_backend(tmp_path)
    tables = {
        "authorization": ("live_pre_execution_authorizations", "authorization_id", receipt.authorization_id, "expires_at_ms"),
        "account": ("live_account_snapshots", "snapshot_hash", receipt.account_snapshot_hash, "equity_usdt"),
        "market": ("live_execution_market_observations", "observation_hash", receipt.market_observation_hash, "mark_price"),
        "intent": ("live_trade_intents", "intent_id", intent.intent_id, "quantity"),
    }
    table, key, identity, field = tables[target]
    with connection(tmp_path / "live.db") as db:
        row = db.execute(f"SELECT payload FROM {table} WHERE {key}=?", (identity,)).fetchone()
        payload = json.loads(row["payload"])
        payload[field] += 1
        db.execute(f"UPDATE {table} SET payload=? WHERE {key}=?", (json.dumps(payload), identity))
    with pytest.raises(ExecutionBlocked):
        backend.submit_authorized(receipt.authorization_id, NOW)
    for name in ("change_margin_type", "change_leverage", "place_order", "cancel_order", "place_protective_order"):
        getattr(client, name).assert_not_called()


def test_missing_local_approval_cannot_issue_authorization(tmp_path):
    from btc_quant_agent.execution.intents import TradeIntentV1
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    values = intent.model_dump(exclude={"intent_hash"})
    values.update(intent_id="local-missing-approval", approval_event_id="nonexistent-local-approval",
                  idempotency_key="local-missing-key", client_order_id="local-missing-client")
    missing = TradeIntentV1.build(**values)
    validator.intent_store.save_intent(missing)
    with pytest.raises(ExecutionBlocked, match="APPROVAL_RECORD_NOT_FOUND"):
        validator.authorize(missing.intent_id, sample_market_obs(), snapshot, NOW)


def test_pending_intent_id_is_not_a_validation_authorization(tmp_path):
    _validator, intent, _snapshot, kill = setup_validator_and_intent(tmp_path)
    client = make_mock_testnet_client()
    backend = TestnetExecutionBackend(tmp_path / "live.db", client, kill)
    with pytest.raises(ExecutionBlocked, match="AUTHORIZATION_NOT_FOUND"):
        backend.submit_authorized(intent.intent_id, NOW)
    client.change_margin_type.assert_not_called()
    client.change_leverage.assert_not_called()
    client.place_order.assert_not_called()


def test_unapproved_fixture_cannot_place_protection(tmp_path):
    _validator, intent, _snapshot, kill = setup_validator_and_intent(tmp_path)
    client = make_mock_testnet_client()
    backend = TestnetExecutionBackend(tmp_path / "live.db", client, kill)
    with pytest.raises(ExecutionBlocked, match="AUTHORIZATION_REQUIRED"):
        backend._place_protective_stop(intent, 0.1, NOW)
    client.place_protective_order.assert_not_called()
    client.cancel_protective_order.assert_not_called()


def test_claimed_authority_cannot_reconcile_missing_approval(tmp_path):
    from btc_quant_agent.execution.intents import TradeIntentV1, compile_executable_intent_fields
    backend, validator, intent, snapshot, client, _ = authorized_backend(tmp_path)
    values = intent.model_dump(exclude={"intent_hash"})
    values.update(intent_id="unapproved-claimed-local", approval_event_id="nonexistent-local-approval",
                  idempotency_key="unapproved-claimed-key", client_order_id="unapproved-claimed-client")
    missing = TradeIntentV1.build(**values)
    validator.intent_store.save_intent(missing)
    compiled = compile_executable_intent_fields(validator.live_store.get_case(intent.case_id),
                                               validator.live_store.get_proposal(intent.proposal_hash), snapshot,
                                               validator.risk_policy)
    receipt = backend.authorizations.issue(missing, snapshot, sample_market_obs(), compiled, NOW, NOW + 1000)
    backend.authorizations.claim(receipt, NOW)
    with pytest.raises(ExecutionBlocked, match="APPROVAL"):
        backend.reconcile_authorized(missing.intent_id, NOW)
    client.query_order_by_client_id.assert_not_called()
    client.place_protective_order.assert_not_called()


def test_restart_reconciles_entry_missing_local_order(tmp_path):
    from btc_quant_agent.live_db import connection
    backend, _validator, intent, _snapshot, client, receipt = authorized_backend(tmp_path)
    backend.authorizations.claim(receipt, NOW)
    client.query_order_by_client_id.return_value = {
        "orderId": "restart-local-order", "status": "NEW", "executedQty": "0", "avgPrice": "0",
    }
    backend.reconcile_authorized(intent.intent_id, NOW + 1)
    with connection(tmp_path / "live.db") as db:
        row = db.execute("SELECT intent_id FROM live_execution_orders WHERE client_order_id=?",
                         (intent.client_order_id,)).fetchone()
    assert row is not None and row["intent_id"] == intent.intent_id
    client.place_order.assert_not_called()


def test_current_tactical_reversal_rejects_unchanged_intent(tmp_path):
    from btc_quant_agent.decision.models import CasePackageV1
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    values = validator.live_store.get_case(intent.case_id).model_dump(exclude={"case_hash"})
    values["direction"] = "SHORT"
    reversed_case = CasePackageV1.build(**values)
    validator.tactical_case_provider = lambda _symbol, _now: reversed_case
    assert validator.validate(intent, sample_market_obs(), snapshot, NOW).reason == "TACTICAL_VALIDITY_INVALID"


def test_disconnected_account_cannot_authorize(tmp_path):
    from btc_quant_agent.account_watch.models import AccountSnapshotV1
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    values = snapshot.model_dump(exclude={"snapshot_hash"})
    values["stream_connected"] = False
    disconnected = AccountSnapshotV1.build(**values)
    with pytest.raises(ExecutionBlocked, match="ACCOUNT_STREAM_DISCONNECTED"):
        validator.authorize(intent.intent_id, sample_market_obs(), disconnected, NOW)


def test_canceled_execution_waits_for_mutation_and_persists_result(tmp_path):
    import asyncio
    import threading

    from btc_quant_agent.execution.backend import DryRunExecutionBackend
    from btc_quant_agent.execution.executor import LiveExecutionService
    from btc_quant_agent.live_db import connection
    backend, validator, intent, snapshot, client, _receipt = authorized_backend(tmp_path)
    started, finish = threading.Event(), threading.Event()
    def place(**_kwargs):
        started.set()
        assert finish.wait(5)
        return {"orderId": "cancel-owned", "status": "NEW", "executedQty": "0"}
    client.place_order.side_effect = place
    watch, market = MagicMock(), MagicMock()
    watch.latest_snapshot.return_value = snapshot
    market.latest_observation.return_value = sample_market_obs()
    service = LiveExecutionService(validator.intent_store, validator.live_store, watch, market,
                                  validator, backend.kill_switch, DryRunExecutionBackend(tmp_path / "live.db"), backend)
    async def run():
        task = asyncio.create_task(service.execute_approved_intent(intent.intent_id, NOW))
        assert await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    with connection(tmp_path / "live.db") as db:
        row = db.execute("SELECT status FROM live_trade_intents WHERE intent_id=?", (intent.intent_id,)).fetchone()
    assert row["status"] == "NEW"
    client.place_order.assert_called_once()
