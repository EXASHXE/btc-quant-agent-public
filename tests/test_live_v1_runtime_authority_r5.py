from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from test_live_v1_runtime_r2 import _runtime

from btc_quant_agent.execution.guard import ExecutionBlocked


def _snapshot(runtime, **changes):
    values = vars(runtime.account_watch.latest_snapshot()).copy()
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("change", [
    {"environment": "TESTNET"},
    {"credential_namespace": "BINANCE_TESTNET"},
    {"account_id": "other-account"},
    {"reconciled": False},
    {"quality": "STALE"},
    {"positions": (SimpleNamespace(symbol="ETHUSDT", quantity=1.0),)},
])
def test_startup_rejects_invalid_rest_authority(change):
    runtime = _runtime()
    runtime.account_watch.latest_snapshot.return_value = _snapshot(runtime, **change)

    async def run():
        with pytest.raises(ExecutionBlocked):
            await runtime.start()

    asyncio.run(run())
    assert not runtime.accepting_risk
    assert not runtime.tasks


def test_startup_rejects_invalid_snapshot_hash():
    runtime = _runtime()
    runtime.account_watch.latest_snapshot.return_value = _snapshot(
        runtime, verify=Mock(side_effect=ValueError("snapshot hash mismatch")))
    with pytest.raises(ExecutionBlocked):
        asyncio.run(runtime.start())
    assert not runtime.tasks


@pytest.mark.parametrize("change", [
    {"environment": "TESTNET"},
    {"credential_namespace": "BINANCE_TESTNET"},
    {"account_id": "other-account"},
    {"reconciled": False},
    {"quality": "STALE"},
    {"positions": (SimpleNamespace(symbol="ETHUSDT", quantity=1.0),)},
])
def test_readiness_and_execute_block_invalid_current_snapshot_before_orchestration(change):
    runtime = _runtime()
    runtime._started = True
    runtime.accepting_risk = True
    runtime.account_watch.latest_snapshot.return_value = _snapshot(runtime, **change)
    assert runtime.status()["accepting_risk"] is False
    with pytest.raises(ExecutionBlocked):
        asyncio.run(runtime.execute_intent("intent-1"))
    runtime.execution_service.execute_approved_intent.assert_not_awaited()


def test_execute_preserves_existing_side_effect_recovery_with_invalid_snapshot():
    runtime = _runtime()
    runtime.account_watch.latest_snapshot.return_value = _snapshot(runtime, account_id="other")
    runtime.intent_store.has_existing_side_effect.return_value = True
    runtime.execution_service.reconcile_intent = AsyncMock(return_value="RECOVERED")
    assert asyncio.run(runtime.execute_intent("intent-1")) == "RECOVERED"


def test_invalid_snapshot_hash_blocks_new_execution():
    runtime = _runtime()
    runtime._started = True
    runtime.accepting_risk = True
    runtime.account_watch.latest_snapshot.return_value = _snapshot(
        runtime, verify=Mock(side_effect=ValueError("snapshot hash mismatch")))
    with pytest.raises(ExecutionBlocked):
        asyncio.run(runtime.execute_intent("intent-1"))
    runtime.execution_service.execute_approved_intent.assert_not_awaited()


def test_poll_rejects_unreconciled_snapshot_before_observation():
    runtime = _runtime()
    runtime.account_watch.latest_snapshot.return_value = _snapshot(runtime, reconciled=False)
    runtime.market_stream.latest_observation.return_value = SimpleNamespace(symbol="BTCUSDT")
    runtime.supervisor.process = AsyncMock()
    asyncio.run(runtime.poll_positions(1_700_000_000_000))
    assert not runtime.accepting_risk
    runtime.supervisor.process.assert_not_awaited()


def test_periodic_rest_cannot_reenable_invalid_authority():
    runtime = _runtime()
    runtime.config = SimpleNamespace(**{**vars(runtime.config), "rest_reconcile_seconds": 0.001})
    runtime.account_watch.latest_snapshot.return_value = _snapshot(runtime, account_id="other")

    async def reconcile():
        runtime._stop_event.set()
        return runtime.account_watch.latest_snapshot()

    runtime.account_watch.reconcile_rest_async.side_effect = reconcile
    runtime.accepting_risk = True
    asyncio.run(runtime._rest_loop())
    assert not runtime.accepting_risk
