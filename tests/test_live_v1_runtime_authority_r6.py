from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_live_v1_runtime_authority_r5 import _snapshot
from test_live_v1_runtime_r2 import _runtime

from btc_quant_agent.execution.backend import TestnetExecutionBackend
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.protection import ProtectionStore
from btc_quant_agent.position_supervisor.kill_switch import KillSwitch

# --- R6-02 Async Runtime Authority Handoff Attacks ---


def test_handoff_rejects_account_change_during_await() -> None:
    runtime = _runtime()
    runtime._started = True
    runtime.accepting_risk = True

    intent = SimpleNamespace(symbol=runtime.config.symbol)
    runtime.intent_store.get_intent = Mock(return_value=intent)

    def mutate_during_loader(_symbol: str) -> SimpleNamespace:
        # Authority changes to a different account during await
        runtime.account_watch.latest_snapshot.return_value = _snapshot(
            runtime, account_id="DIFFERENT_ACCOUNT"
        )
        return SimpleNamespace(verify=Mock())

    runtime._case_loader = mutate_during_loader

    with pytest.raises(ExecutionBlocked, match="POSITION_ACCOUNT_AUTHORITY_MISMATCH"):
        asyncio.run(runtime.execute_intent("intent-1"))

    runtime.execution_service.execute_approved_intent.assert_not_awaited()


def test_handoff_rejects_unconfigured_symbol_during_await() -> None:
    runtime = _runtime()
    runtime._started = True
    runtime.accepting_risk = True

    intent = SimpleNamespace(symbol=runtime.config.symbol)
    runtime.intent_store.get_intent = Mock(return_value=intent)

    def mutate_during_loader(_symbol: str) -> SimpleNamespace:
        # Nonzero unconfigured position appears during await
        runtime.account_watch.latest_snapshot.return_value = _snapshot(
            runtime, positions=(SimpleNamespace(symbol="ETHUSDT", quantity=1.0),)
        )
        return SimpleNamespace(verify=Mock())

    runtime._case_loader = mutate_during_loader

    with pytest.raises(ExecutionBlocked, match="UNCONFIGURED_POSITION_SYMBOL"):
        asyncio.run(runtime.execute_intent("intent-1"))

    runtime.execution_service.execute_approved_intent.assert_not_awaited()


@pytest.mark.parametrize(
    ("env", "ns"),
    [
        ("TESTNET", "BINANCE_TESTNET"),
        ("LIVE", "BINANCE_LIVE"),
    ],
)
def test_handoff_rejects_environment_namespace_change_during_await(env: str, ns: str) -> None:
    runtime = _runtime()  # default is DRY_RUN / NONE
    runtime._started = True
    runtime.accepting_risk = True

    intent = SimpleNamespace(symbol=runtime.config.symbol)
    runtime.intent_store.get_intent = Mock(return_value=intent)

    def mutate_during_loader(_symbol: str) -> SimpleNamespace:
        runtime.account_watch.latest_snapshot.return_value = _snapshot(
            runtime, environment=env, credential_namespace=ns
        )
        return SimpleNamespace(verify=Mock())

    runtime._case_loader = mutate_during_loader

    with pytest.raises(ExecutionBlocked, match="POSITION_ACCOUNT_AUTHORITY_MISMATCH"):
        asyncio.run(runtime.execute_intent("intent-1"))

    runtime.execution_service.execute_approved_intent.assert_not_awaited()


def test_handoff_rejects_kill_switch_trip_during_await() -> None:
    runtime = _runtime()
    runtime._started = True
    runtime.accepting_risk = True

    intent = SimpleNamespace(symbol=runtime.config.symbol)
    runtime.intent_store.get_intent = Mock(return_value=intent)

    def mutate_during_loader(_symbol: str) -> SimpleNamespace:
        runtime.kill_switch.allows_new_risk.return_value = False
        return SimpleNamespace(verify=Mock())

    runtime._case_loader = mutate_during_loader

    with pytest.raises(ExecutionBlocked, match="KILL_SWITCH_ACTIVE"):
        asyncio.run(runtime.execute_intent("intent-1"))

    runtime.execution_service.execute_approved_intent.assert_not_awaited()


def test_periodic_rest_stale_result_cannot_enable_risk_if_latest_becomes_invalid() -> None:
    runtime = _runtime()
    runtime._started = True
    runtime.config = SimpleNamespace(**{**vars(runtime.config), "rest_reconcile_seconds": 0.001})

    # Initially valid
    valid_snap = _snapshot(runtime)
    runtime.account_watch.latest_snapshot.return_value = valid_snap

    def mutate_and_stop(_symbol: str) -> SimpleNamespace:
        # By the time case refresh finishes, latest snapshot is corrupt/unconfigured
        runtime.account_watch.latest_snapshot.return_value = _snapshot(
            runtime, positions=(SimpleNamespace(symbol="ETHUSDT", quantity=1.0),)
        )
        runtime._stop_event.set()
        return SimpleNamespace(verify=Mock())

    runtime._case_loader = mutate_and_stop
    runtime.accepting_risk = True

    asyncio.run(runtime._rest_loop())

    assert not runtime.accepting_risk
    assert runtime.blocked_reason == "UNCONFIGURED_POSITION_SYMBOL"


def test_handoff_succeeds_when_authority_remains_valid() -> None:
    runtime = _runtime()
    runtime._started = True
    runtime.accepting_risk = True

    intent = SimpleNamespace(symbol=runtime.config.symbol)
    runtime.intent_store.get_intent = Mock(return_value=intent)
    runtime._case_loader = lambda _symbol: SimpleNamespace(verify=Mock())
    runtime.execution_service.execute_approved_intent = AsyncMock(return_value="INTENT_EXECUTED")

    result = asyncio.run(runtime.execute_intent("intent-1"))
    assert result == "INTENT_EXECUTED"
    runtime.execution_service.execute_approved_intent.assert_awaited_once_with("intent-1")


def test_existing_side_effect_recovery_allowed_with_invalid_authority_without_new_risk() -> None:
    runtime = _runtime()
    runtime._started = True
    runtime.accepting_risk = True

    # Snapshot has unconfigured position
    runtime.account_watch.latest_snapshot.return_value = _snapshot(
        runtime, positions=(SimpleNamespace(symbol="ETHUSDT", quantity=1.0),)
    )
    runtime.intent_store.has_existing_side_effect.return_value = True
    runtime.execution_service.reconcile_intent = AsyncMock(return_value="RECOVERED")

    result = asyncio.run(runtime.execute_intent("intent-1"))
    assert result == "RECOVERED"
    runtime.execution_service.reconcile_intent.assert_awaited_once_with("intent-1")
    runtime.execution_service.execute_approved_intent.assert_not_awaited()


def test_cross_finding_real_execution_backend_validator_blocks_unconfigured_position(tmp_path) -> None:
    """Cross-finding: Dual defense ensures backend/validator independently blocks unconfigured positions.

    Even if runtime admission passed or backend were called directly, PreExecutionValidator
    rejects the snapshot with unconfigured symbol and zero fake entry POST is made.
    """
    from test_live_v1_account_watch import sample_snapshot
    from test_live_v1_execution_backend import (
        NOW,
        authorize_testnet_intent,
        make_mock_testnet_client,
    )
    from test_live_v1_execution_intent import setup_approved_state

    from btc_quant_agent.account_watch import PositionV1
    from btc_quant_agent.execution.intents import build_trade_intent

    store, _, proposal, event_id, _ = setup_approved_state(tmp_path)
    intent = build_trade_intent(
        store,
        sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW),
        proposal.proposal_hash,
        event_id,
        now_ms=NOW,
    )
    client = make_mock_testnet_client(position_amt=0.0)
    kill = KillSwitch(tmp_path / "live.db")
    backend = TestnetExecutionBackend(tmp_path / "live.db", client, kill)
    backend.protections = ProtectionStore(backend.path)
    auth_id = authorize_testnet_intent(backend, store, intent, kill, claimed=False)

    # Prepare an account snapshot with an unconfigured ETHUSDT position
    invalid_snapshot = sample_snapshot(
        observed_at_ms=NOW,
        last_rest_at_ms=NOW,
        positions=(
            PositionV1(
                symbol="ETHUSDT",
                quantity=1.0,
                entry_price=3000.0,
                mark_price=3000.0,
                liquidation_price=0.0,
                unrealized_pnl_usdt=0.0,
                leverage=1,
                margin_type="cross",
                observed_at_ms=NOW,
            ),
        ),
    )
    backend.account_provider = lambda: invalid_snapshot

    # Test validator directly
    market_obs = SimpleNamespace(
        symbol=intent.symbol,
        mark_price=intent.price,
        best_bid=intent.price - 1.0,
        best_ask=intent.price + 1.0,
        spread_bps=1.0,
        kline_close=intent.price,
        observed_at_ms=NOW,
    )
    val_res = backend.validator.validate(intent, market_obs, invalid_snapshot, NOW)
    assert not val_res.is_valid
    assert val_res.reason == "UNCONFIGURED_POSITION_SYMBOL"

    # Verify that calling submit_authorized on backend with this fresh snapshot fails closed
    with pytest.raises(ExecutionBlocked, match="UNCONFIGURED_POSITION_SYMBOL"):
        backend.submit_authorized(auth_id, NOW)

    # Verify ZERO fake entry POST count
    assert client.place_order.call_count == 0
