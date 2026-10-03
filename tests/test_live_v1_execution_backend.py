"""Adversarial tests for ExecutionCapabilityPolicyV1, DryRunExecutionBackend, and TestnetExecutionBackend."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_execution_intent import setup_approved_state
from test_live_v1_execution_validator import sample_market_obs

from btc_quant_agent.execution.authorization import AuthorizationStore
from btc_quant_agent.execution.backend import DryRunExecutionBackend, TestnetExecutionBackend
from btc_quant_agent.execution.binance_signed import (
    BinanceExecutionError,
    BinanceSignedClient,
    CredentialAuthority,
    create_testnet_signed_client,
)
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import IntentStore, build_trade_intent
from btc_quant_agent.execution.policy import ExecutionCapabilityPolicyV1
from btc_quant_agent.execution.validator import PreExecutionValidator
from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor.kill_switch import KillSwitch

NOW = 1_700_000_000_000


def make_mock_testnet_client(
    base_url: str = "https://testnet.binancefuture.com",
    environment: str = "TESTNET",
    credential_namespace: str = "BINANCE_TESTNET",
    position_amt: float | None = None,
) -> MagicMock:
    mock_client = MagicMock(spec=BinanceSignedClient)
    mock_client.base_url = base_url
    mock_client.environment = environment
    mock_client.credential_namespace = credential_namespace
    mock_client.authority = CredentialAuthority(
        environment=environment,
        credential_namespace=credential_namespace,
        rest_base_url=base_url,
    )
    mock_client.position_mode.return_value = {"dualSidePosition": False}
    amt = position_amt if position_amt is not None else 1000.0
    mock_client.positions.return_value = [
        {"symbol": "BTCUSDT", "positionSide": "BOTH", "positionAmt": str(amt)}
    ]
    mock_client.open_protective_orders.return_value = []
    return mock_client


def authorize_testnet_intent(backend, store, intent, kill_switch, *, claimed=False):
    """Persist and validate the entry before exercising a fake TESTNET client."""
    intent_store = IntentStore(backend.path)
    intent_store.save_intent(intent)
    validator = PreExecutionValidator(
        store,
        intent_store,
        kill_switch,
        tactical_validity_provider=lambda _symbol, _now: True,
    )
    backend.validator = validator
    current_account = sample_snapshot(
        observed_at_ms=NOW,
        last_rest_at_ms=NOW,
        positions=(),
        orders=(),
    )
    backend.clock_ms = lambda: NOW
    backend.account_provider = lambda: current_account
    backend.market_provider = lambda now: sample_market_obs(
        mark_price=intent.price, source_timestamp_ms=now, receipt_timestamp_ms=now
    )
    receipt = validator.authorize(
        intent.intent_id,
        sample_market_obs(mark_price=intent.price),
        current_account,
        NOW,
    )
    if claimed:
        assert AuthorizationStore(backend.path).claim(receipt, NOW)
        backend.protections.reserve_owner(intent, NOW)
    return receipt.authorization_id


def test_live_execution_permanently_blocked(monkeypatch):
    # Even if environment variables attempt to allow LIVE, policy must fail closed
    monkeypatch.setenv("BTC_QUANT_LIVE_CONFIRM", "I_UNDERSTAND_REAL_ORDERS")
    monkeypatch.setenv("ALLOW_LIVE", "true")
    monkeypatch.setenv("BTC_QUANT_EXECUTION_MODE", "live")

    assert not ExecutionCapabilityPolicyV1.is_allowed("LIVE")
    assert not ExecutionCapabilityPolicyV1.is_allowed("AUTONOMOUS")

    with pytest.raises(ExecutionBlocked, match="LIVE execution is permanently blocked"):
        ExecutionCapabilityPolicyV1.check_capability("LIVE", "ORDER_SUBMIT")

    with pytest.raises(ExecutionBlocked, match="LIVE execution is permanently blocked"):
        ExecutionCapabilityPolicyV1.check_capability("AUTONOMOUS", "ORDER_SUBMIT")


def test_testnet_authority_isolation():
    # TESTNET cannot bind to LIVE endpoint
    with pytest.raises(ExecutionBlocked, match="not allowlisted for TESTNET"):
        ExecutionCapabilityPolicyV1.check_capability(
            "TESTNET",
            "ORDER_SUBMIT",
            env_id="binance_usdm_testnet",
            cred_ns="BINANCE_TESTNET",
            rest_url="https://fapi.binance.com",
        )

    # TESTNET with wrong credential namespace fails closed
    with pytest.raises(ExecutionBlocked, match="credential namespace mismatch"):
        ExecutionCapabilityPolicyV1.check_capability(
            "TESTNET",
            "ORDER_SUBMIT",
            env_id="binance_usdm_testnet",
            cred_ns="NONE",
            rest_url="https://testnet.binancefuture.com",
        )


def test_dry_run_backend_exactly_once_and_protective_stop(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    db_path = tmp_path / "live.db"
    backend = DryRunExecutionBackend(db_path)

    # First submit
    report1 = backend.submit_intent(intent, NOW)
    assert report1.status == "FILLED"
    assert report1.filled_qty == intent.quantity
    assert report1.protective_stop_id is not None

    # Idempotent second submit returns the same order record without duplicating
    report2 = backend.submit_intent(intent, NOW + 1000)
    assert report2.order_id == report1.order_id
    assert report2.reason == "IDEMPOTENT_REPLAY"


def test_testnet_transport_uncertainty_queries_before_retry(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    mock_client = make_mock_testnet_client()
    kill_switch = KillSwitch(tmp_path / "live.db")

    # Simulate place_order timing out / raising network error
    mock_client.place_order.side_effect = BinanceExecutionError("Connection timeout")

    # But query_order_by_client_id finds the order was actually received by Binance!
    mock_client.query_order_by_client_id.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "987654",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(intent.quantity),
        "avgPrice": str(intent.price),
        "updateTime": NOW + 200,
    }
    mock_client.place_protective_order.return_value = {"algoId": "algo-stop-1"}

    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    authorization_id = authorize_testnet_intent(
        backend,
        store,
        intent,
        kill_switch,
        claimed=False,
    )
    report = backend.submit_authorized(authorization_id, NOW)

    # Proves transport uncertainty was resolved by querying clientOrderId
    assert report.order_id == "987654"
    assert report.status == "FILLED"
    assert report.filled_qty == intent.quantity
    mock_client.query_order_by_client_id.assert_called_once_with(
        intent.symbol, intent.client_order_id
    )


def test_testnet_transport_uncertainty_fails_closed_when_query_fails(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    mock_client = make_mock_testnet_client()
    kill_switch = KillSwitch(tmp_path / "live.db")

    # Simulate place_order timing out AND query timing out
    mock_client.place_order.side_effect = BinanceExecutionError("Connection reset")
    mock_client.query_order_by_client_id.side_effect = BinanceExecutionError("Query timeout")

    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    authorization_id = authorize_testnet_intent(
        backend,
        store,
        intent,
        kill_switch,
        claimed=False,
    )

    # Must FAIL CLOSED! Never blindly retry
    with pytest.raises(ExecutionBlocked, match="Transport uncertainty"):
        backend.submit_authorized(authorization_id, NOW)


def test_testnet_protective_stop_failure_activates_kill_switch(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    mock_client = make_mock_testnet_client()
    kill_switch = KillSwitch(tmp_path / "live.db")

    # Entry succeeds
    mock_client.place_order.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "111222",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(intent.quantity),
        "avgPrice": str(intent.price),
        "updateTime": NOW,
    }

    # Protective stop fails
    mock_client.place_protective_order.side_effect = BinanceExecutionError(
        "Insufficient balance for algo order"
    )

    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    authorization_id = authorize_testnet_intent(
        backend,
        store,
        intent,
        kill_switch,
        claimed=False,
    )

    # Placing fails closed
    with pytest.raises(ExecutionBlocked, match="failed to place required protective stop"):
        backend.submit_authorized(authorization_id, NOW)

    # Kill switch must now be tripped and block any new risk!
    assert not kill_switch.allows_new_risk()


def test_r1_02_backend_rejects_missing_or_mismatched_authority(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )
    kill_switch = KillSwitch(tmp_path / "live.db")

    # 1. Missing authority completely
    client_no_auth = MagicMock(spec=BinanceSignedClient)
    client_no_auth.authority = None
    backend1 = TestnetExecutionBackend(tmp_path / "live1.db", client_no_auth, kill_switch)
    with pytest.raises(ExecutionBlocked, match="missing credential authority"):
        backend1.submit_intent(intent, NOW)

    # 2. Wrong namespace (LIVE namespace attempted on testnet)
    client_wrong_ns = make_mock_testnet_client(credential_namespace="BINANCE_LIVE")
    backend2 = TestnetExecutionBackend(tmp_path / "live2.db", client_wrong_ns, kill_switch)
    with pytest.raises(ExecutionBlocked, match="credential namespace mismatch for TESTNET"):
        backend2.submit_intent(intent, NOW)

    # 3. Wrong endpoint (Live URL attempted with testnet namespace)
    client_wrong_url = make_mock_testnet_client(base_url="https://fapi.binance.com")
    backend3 = TestnetExecutionBackend(tmp_path / "live3.db", client_wrong_url, kill_switch)
    with pytest.raises(ExecutionBlocked, match="is not allowlisted for TESTNET"):
        backend3.submit_intent(intent, NOW)

    # 4. Wrong environment (LIVE environment attempted)
    client_wrong_env = make_mock_testnet_client(environment="LIVE")
    backend4 = TestnetExecutionBackend(tmp_path / "live4.db", client_wrong_env, kill_switch)
    with pytest.raises(ExecutionBlocked, match="LIVE execution is permanently blocked"):
        backend4.submit_intent(intent, NOW)


def test_r1_02_no_live_credential_source_consumed_by_factory(monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "real_live_key_should_not_be_used")
    monkeypatch.setenv("BINANCE_SECRET_KEY", "real_live_secret_should_not_be_used")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "testnet_key_123")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "testnet_secret_456")

    client = create_testnet_signed_client()
    assert client.api_key == "testnet_key_123"
    assert client.api_secret == "testnet_secret_456"
    assert client.authority.environment == "TESTNET"
    assert client.authority.credential_namespace == "BINANCE_TESTNET"
    assert client.authority.rest_base_url == "https://testnet.binancefuture.com"


def test_r1_04_delayed_partial_fill_and_resizing_protection(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    mock_client = make_mock_testnet_client()
    kill_switch = KillSwitch(tmp_path / "live.db")

    # 1. Initial submission returns NEW (0 filled)
    mock_client.place_order.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "ord-100",
        "clientOrderId": intent.client_order_id,
        "status": "NEW",
        "executedQty": "0.0",
        "avgPrice": "0.0",
        "updateTime": NOW,
    }
    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    authorization_id = authorize_testnet_intent(
        backend,
        store,
        intent,
        kill_switch,
        claimed=False,
    )
    rep1 = backend.submit_authorized(authorization_id, NOW)
    assert rep1.status == "NEW"
    assert rep1.filled_qty == 0.0
    assert rep1.protective_stop_id is None
    mock_client.place_protective_order.assert_not_called()

    # 2. Later reconcile: order is now PARTIALLY_FILLED with 0.05
    partial_qty = intent.quantity / 2.0
    mock_client.query_order_by_client_id.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "ord-100",
        "clientOrderId": intent.client_order_id,
        "status": "PARTIALLY_FILLED",
        "executedQty": str(partial_qty),
        "avgPrice": str(intent.price),
        "updateTime": NOW + 10_000,
    }
    mock_client.open_protective_orders.return_value = []
    mock_client.place_protective_order.return_value = {"algoId": "stop-part-1"}

    rep2 = backend.reconcile_authorized(intent.intent_id, NOW + 10_000)
    assert rep2.status == "PARTIALLY_FILLED"
    assert rep2.filled_qty == partial_qty
    assert rep2.protective_stop_id == "stop-part-1"
    mock_client.place_protective_order.assert_called_once()
    assert mock_client.place_protective_order.call_args.kwargs["quantity"] == partial_qty

    # 3. Later reconcile: order is now FILLED with full intent.quantity (e.g. 0.1)
    full_qty = intent.quantity
    mock_client.query_order_by_client_id.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "ord-100",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(full_qty),
        "avgPrice": str(intent.price),
        "updateTime": NOW + 20_000,
    }
    # Exchange reports open protective order for the earlier partial qty
    mock_client.open_protective_orders.return_value = [
        {
            "symbol": intent.symbol,
            "side": "SELL",
            "orderType": "STOP_MARKET",
            "positionSide": "BOTH",
            "reduceOnly": True,
            "triggerPrice": intent.stop_loss,
            "algoId": "stop-part-1",
            "clientAlgoId": backend.protections.get_owner(intent).protective_client_id,
            "quantity": str(partial_qty),
        }
    ]
    mock_client.cancel_protective_order.return_value = {
        "algoId": "stop-part-1",
        "status": "CANCELED",
    }
    mock_client.place_protective_order.reset_mock()
    mock_client.place_protective_order.return_value = {"algoId": "stop-full-2"}

    rep3 = backend.reconcile_authorized(intent.intent_id, NOW + 20_000)
    assert rep3.status == "FILLED"
    assert rep3.filled_qty == full_qty
    assert rep3.protective_stop_id == "stop-full-2"
    # Proves smaller protective order was cancelled and replaced with resized full order
    mock_client.cancel_protective_order.assert_called_once_with(intent.symbol, "stop-part-1")
    mock_client.place_protective_order.assert_called_once()
    assert mock_client.place_protective_order.call_args.kwargs["quantity"] == full_qty


def test_r1_04_reconciliation_replay_idempotence(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    mock_client = make_mock_testnet_client()
    kill_switch = KillSwitch(tmp_path / "live.db")
    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    authorize_testnet_intent(
        backend,
        store,
        intent,
        kill_switch,
        claimed=True,
    )

    full_qty = intent.quantity
    mock_client.query_order_by_client_id.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "ord-200",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(full_qty),
        "avgPrice": str(intent.price),
        "updateTime": NOW,
    }
    # A prior run persisted exact ownership of this exchange stop.
    backend.protections.reserve_owner(intent, NOW)
    owned_client_id = backend.protections.next_client_id(intent, NOW)
    backend.protections.record_stop(intent, owned_client_id, "stop-full-200", full_qty, NOW)
    mock_client.open_protective_orders.return_value = [
        {
            "symbol": intent.symbol,
            "side": "SELL",
            "orderType": "STOP_MARKET",
            "positionSide": "BOTH",
            "reduceOnly": True,
            "triggerPrice": intent.stop_loss,
            "algoId": "stop-full-200",
            "clientAlgoId": owned_client_id,
            "quantity": str(full_qty),
        }
    ]

    rep = backend.reconcile_authorized(intent.intent_id, NOW)
    assert rep.status == "FILLED"
    assert rep.filled_qty == full_qty
    assert rep.protective_stop_id == "stop-full-200"
    # Neither cancel nor place was called on replay
    mock_client.cancel_protective_order.assert_not_called()
    mock_client.place_protective_order.assert_not_called()


def test_r1_04_protective_query_uncertainty_fails_closed(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    mock_client = make_mock_testnet_client()
    kill_switch = KillSwitch(tmp_path / "live.db")
    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    authorize_testnet_intent(
        backend,
        store,
        intent,
        kill_switch,
        claimed=True,
    )

    mock_client.query_order_by_client_id.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "ord-300",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(intent.quantity),
        "avgPrice": str(intent.price),
        "updateTime": NOW,
    }
    # Open protective orders query fails with network/gateway error
    mock_client.open_protective_orders.side_effect = BinanceExecutionError("504 Gateway Timeout")

    with pytest.raises(ExecutionBlocked, match="protective query uncertainty"):
        backend.reconcile_authorized(intent.intent_id, NOW)

    # Must trip kill switch and block new risk!
    assert not kill_switch.allows_new_risk()


def test_r1_04_dry_run_reconciliation_delayed_and_resized(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    from btc_quant_agent.live_db import connection

    db_path = tmp_path / "live.db"
    backend = DryRunExecutionBackend(db_path)

    # Manually insert NEW order with 0 fills (simulating pending limit order)
    with connection(db_path) as db:
        db.execute(
            "INSERT INTO live_execution_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "sim-delayed-1",
                intent.intent_id,
                intent.client_order_id,
                intent.symbol,
                intent.side,
                "NEW",
                intent.quantity,
                0.0,
                0.0,
                None,
                0,
                0,
                NOW,
                NOW,
                "{}",
            ),
        )

    # Reconcile when 0 filled: no protective stop
    rep1 = backend.reconcile_intent(intent, NOW)
    assert rep1.status == "NEW"
    assert rep1.filled_qty == 0.0
    assert rep1.protective_stop_id is None

    # Simulate transition to PARTIALLY_FILLED
    partial_qty = intent.quantity / 2.0
    with connection(db_path) as db:
        db.execute(
            "UPDATE live_execution_orders SET status='PARTIALLY_FILLED', filled_qty=? WHERE client_order_id=?",
            (partial_qty, intent.client_order_id),
        )

    rep2 = backend.reconcile_intent(intent, NOW + 5000)
    assert rep2.status == "PARTIALLY_FILLED"
    assert rep2.filled_qty == partial_qty
    assert rep2.protective_stop_id == f"sim-stop-{intent.intent_id}"

    # Verify protective stop row was created with partial_qty
    with connection(db_path) as db:
        stop_row = db.execute(
            "SELECT * FROM live_execution_orders WHERE intent_id=? AND is_protective=1",
            (intent.intent_id,),
        ).fetchone()
    assert stop_row is not None
    assert stop_row["requested_qty"] == partial_qty

    # Simulate transition to FILLED
    with connection(db_path) as db:
        db.execute(
            "UPDATE live_execution_orders SET status='FILLED', filled_qty=? WHERE client_order_id=?",
            (intent.quantity, intent.client_order_id),
        )

    rep3 = backend.reconcile_intent(intent, NOW + 10_000)
    assert rep3.status == "FILLED"
    assert rep3.filled_qty == intent.quantity
    assert rep3.protective_stop_id == f"sim-stop-{intent.intent_id}"

    # Verify protective stop row was resized to full quantity
    with connection(db_path) as db:
        stop_row2 = db.execute(
            "SELECT * FROM live_execution_orders WHERE intent_id=? AND is_protective=1",
            (intent.intent_id,),
        ).fetchone()
    assert stop_row2 is not None
    assert stop_row2["requested_qty"] == intent.quantity


def test_r1_1_03_signed_client_default_unbound_fails_capability(tmp_path):
    client = BinanceSignedClient(
        base_url="https://testnet.binancefuture.com", api_key="key", api_secret="secret"
    )
    assert client.authority.environment == "UNBOUND"
    assert client.authority.credential_namespace == "UNBOUND"
    assert not ExecutionCapabilityPolicyV1.is_allowed("UNBOUND")

    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )
    kill_switch = KillSwitch(tmp_path / "live.db")
    backend = TestnetExecutionBackend(tmp_path / "live.db", client, kill_switch)

    with pytest.raises(
        ExecutionBlocked, match="unknown or unhandled execution capability: 'UNBOUND'"
    ):
        backend.submit_intent(intent, NOW)


def test_r1_1_03_create_testnet_client_credential_gates(monkeypatch):
    monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_API_SECRET", raising=False)

    # Missing credentials must fail closed
    with pytest.raises(BinanceExecutionError, match="missing required BINANCE_TESTNET_API_KEY"):
        create_testnet_signed_client()

    # Presence of LIVE variables must NOT self-authorize testnet
    monkeypatch.setenv("BINANCE_API_KEY", "live-key")
    monkeypatch.setenv("BINANCE_API_SECRET", "live-secret")
    with pytest.raises(BinanceExecutionError, match="missing required BINANCE_TESTNET_API_KEY"):
        create_testnet_signed_client()

    # Valid testnet credentials via factory mint TESTNET authority
    client = create_testnet_signed_client(api_key="test-key", api_secret="test-secret")
    assert client.authority.environment == "TESTNET"
    assert client.authority.credential_namespace == "BINANCE_TESTNET"


def test_r1_1_02_protection_limited_to_actual_open_position(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    # Entry filled 0.1, but current open position has been reduced to 0.04
    entry_fill = intent.quantity  # e.g. 0.1
    current_open = entry_fill * 0.4  # 0.04
    mock_client = make_mock_testnet_client(position_amt=current_open)
    kill_switch = KillSwitch(tmp_path / "live.db")
    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    authorize_testnet_intent(
        backend,
        store,
        intent,
        kill_switch,
        claimed=True,
    )

    mock_client.query_order_by_client_id.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "ord-reduced",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(entry_fill),
        "avgPrice": str(intent.price),
        "updateTime": NOW,
    }
    mock_client.open_protective_orders.return_value = []
    mock_client.place_protective_order.return_value = {"algoId": "stop-reduced-1"}

    rep = backend.reconcile_authorized(intent.intent_id, NOW)
    assert rep.status == "FILLED"
    assert rep.protective_stop_id == "stop-reduced-1"
    # Sized to current_open, NEVER exceeding actual open position!
    mock_client.place_protective_order.assert_called_once()
    assert mock_client.place_protective_order.call_args.kwargs["quantity"] == pytest.approx(
        current_open
    )


def test_r1_1_02_flat_position_cancels_stale_protection(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    # Current open position is 0.0 (flat after stop/TP)
    mock_client = make_mock_testnet_client(position_amt=0.0)
    kill_switch = KillSwitch(tmp_path / "live.db")
    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    authorize_testnet_intent(
        backend,
        store,
        intent,
        kill_switch,
        claimed=True,
    )

    mock_client.query_order_by_client_id.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "ord-flat",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(intent.quantity),
        "avgPrice": str(intent.price),
        "updateTime": NOW,
    }
    # Exchange has a stop with exact persisted ownership.
    backend.protections.reserve_owner(intent, NOW)
    owned_client_id = backend.protections.next_client_id(intent, NOW)
    backend.protections.record_stop(
        intent, owned_client_id, "stop-stale-flat", intent.quantity, NOW
    )
    mock_client.open_protective_orders.return_value = [
        {
            "symbol": intent.symbol,
            "side": "SELL",
            "orderType": "STOP_MARKET",
            "positionSide": "BOTH",
            "reduceOnly": True,
            "triggerPrice": intent.stop_loss,
            "algoId": "stop-stale-flat",
            "clientAlgoId": owned_client_id,
            "quantity": str(intent.quantity),
        }
    ]
    mock_client.cancel_protective_order.return_value = {
        "algoId": "stop-stale-flat",
        "status": "CANCELED",
    }

    rep = backend.reconcile_authorized(intent.intent_id, NOW)
    assert rep.status == "FILLED"
    assert rep.protective_stop_id is None
    # Stale order cancelled
    mock_client.cancel_protective_order.assert_called_once_with(intent.symbol, "stop-stale-flat")
    # No new order placed
    mock_client.place_protective_order.assert_not_called()


def test_r1_1_02_position_query_uncertainty_trips_kill_switch(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    mock_client = make_mock_testnet_client()
    kill_switch = KillSwitch(tmp_path / "live.db")
    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    authorize_testnet_intent(
        backend,
        store,
        intent,
        kill_switch,
        claimed=True,
    )

    mock_client.query_order_by_client_id.return_value = {"symbol": intent.symbol, "side": intent.side,
        "orderId": "ord-pos-fail",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(intent.quantity),
        "avgPrice": str(intent.price),
        "updateTime": NOW,
    }
    # Position query fails with network uncertainty
    mock_client.positions.side_effect = BinanceExecutionError(
        "Network timeout on /fapi/v3/positionRisk"
    )

    with pytest.raises(ExecutionBlocked, match="position query uncertainty"):
        backend.reconcile_authorized(intent.intent_id, NOW)

    assert not kill_switch.allows_new_risk()


def test_r1_1_02_dry_run_backend_open_position_provider(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    db_path = tmp_path / "live.db"
    open_pos = 0.05
    backend = DryRunExecutionBackend(
        db_path,
        open_position_provider=lambda sym, side: open_pos,
    )

    with connection(db_path) as db:
        db.execute(
            "INSERT INTO live_execution_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "sim-ord-1",
                intent.intent_id,
                intent.client_order_id,
                intent.symbol,
                intent.side,
                "FILLED",
                intent.quantity,
                intent.quantity,
                intent.price,
                None,
                0,
                0,
                NOW,
                NOW,
                "{}",
            ),
        )

    # 1. Reconcile with open position = 0.05 (< filled 0.1)
    rep1 = backend.reconcile_intent(intent, NOW)
    assert rep1.protective_stop_id is not None
    with connection(db_path) as db:
        stop_row = db.execute(
            "SELECT * FROM live_execution_orders WHERE intent_id=? AND is_protective=1",
            (intent.intent_id,),
        ).fetchone()
    assert stop_row["requested_qty"] == 0.05

    # 2. Position closes (flat)
    open_pos = 0.0
    rep2 = backend.reconcile_intent(intent, NOW + 1000)
    assert rep2.protective_stop_id is None
    with connection(db_path) as db:
        stop_row2 = db.execute(
            "SELECT * FROM live_execution_orders WHERE intent_id=? AND is_protective=1",
            (intent.intent_id,),
        ).fetchone()
    assert stop_row2["status"] == "CANCELED"
