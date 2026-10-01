"""Adversarial tests for ExecutionCapabilityPolicyV1, DryRunExecutionBackend, and TestnetExecutionBackend."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_execution_intent import setup_approved_state

from btc_quant_agent.execution.backend import DryRunExecutionBackend, TestnetExecutionBackend
from btc_quant_agent.execution.binance_signed import BinanceExecutionError, BinanceSignedClient
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import build_trade_intent
from btc_quant_agent.execution.policy import ExecutionCapabilityPolicyV1
from btc_quant_agent.position_supervisor.kill_switch import KillSwitch

NOW = 1_700_000_000_000


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

    mock_client = MagicMock(spec=BinanceSignedClient)
    mock_client.base_url = "https://testnet.binancefuture.com"
    kill_switch = KillSwitch(tmp_path / "live.db")

    # Simulate place_order timing out / raising network error
    mock_client.place_order.side_effect = BinanceExecutionError("Connection timeout")

    # But query_order_by_client_id finds the order was actually received by Binance!
    mock_client.query_order_by_client_id.return_value = {
        "orderId": "987654",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(intent.quantity),
        "avgPrice": str(intent.price),
        "updateTime": NOW + 200,
    }
    mock_client.place_protective_order.return_value = {"algoId": "algo-stop-1"}

    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)
    report = backend.submit_intent(intent, NOW)

    # Proves transport uncertainty was resolved by querying clientOrderId
    assert report.order_id == "987654"
    assert report.status == "FILLED"
    assert report.filled_qty == intent.quantity
    mock_client.query_order_by_client_id.assert_called_once_with(intent.symbol, intent.client_order_id)


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

    mock_client = MagicMock(spec=BinanceSignedClient)
    mock_client.base_url = "https://testnet.binancefuture.com"
    kill_switch = KillSwitch(tmp_path / "live.db")

    # Simulate place_order timing out AND query timing out
    mock_client.place_order.side_effect = BinanceExecutionError("Connection reset")
    mock_client.query_order_by_client_id.side_effect = BinanceExecutionError("Query timeout")

    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)

    # Must FAIL CLOSED! Never blindly retry
    with pytest.raises(ExecutionBlocked, match="Transport uncertainty"):
        backend.submit_intent(intent, NOW)


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

    mock_client = MagicMock(spec=BinanceSignedClient)
    mock_client.base_url = "https://testnet.binancefuture.com"
    kill_switch = KillSwitch(tmp_path / "live.db")

    # Entry succeeds
    mock_client.place_order.return_value = {
        "orderId": "111222",
        "clientOrderId": intent.client_order_id,
        "status": "FILLED",
        "executedQty": str(intent.quantity),
        "avgPrice": str(intent.price),
        "updateTime": NOW,
    }

    # Protective stop fails
    mock_client.place_protective_order.side_effect = BinanceExecutionError("Insufficient balance for algo order")

    backend = TestnetExecutionBackend(tmp_path / "live.db", mock_client, kill_switch)

    # Placing fails closed
    with pytest.raises(ExecutionBlocked, match="failed to place required protective stop"):
        backend.submit_intent(intent, NOW)

    # Kill switch must now be tripped and block any new risk!
    assert not kill_switch.allows_new_risk()
