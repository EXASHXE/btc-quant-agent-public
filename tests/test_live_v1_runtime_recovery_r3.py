from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_position_supervisor import NOW, observation
from test_live_v1_runtime_r2 import _run, _runtime

from btc_quant_agent import api
from btc_quant_agent.account_watch import AccountStore
from btc_quant_agent.config import LiveV1Config
from btc_quant_agent.live_db import connection
from btc_quant_agent.live_market.models import MarketObservationV1
from btc_quant_agent.live_market.service import MarketStreamService
from btc_quant_agent.position_supervisor import PositionSupervisor


def test_market_components_cannot_refresh_one_another():
    stream = MarketStreamService(clock_ms=lambda: NOW)
    stream.update_simulated(100, 99, 101, 100, NOW - 20_000)
    stream.handle_message('{"e":"bookTicker","E":1700000000000,"b":"99","a":"101"}', NOW)
    market = stream.latest_observation()
    assert market is not None
    assert market.mark_receipt_timestamp_ms == NOW - 20_000
    assert market.book_receipt_timestamp_ms == NOW
    assert market.freshness_reason(NOW, 10_000) == "MARKET_MARK_STALE"


def test_incomplete_market_message_cannot_refresh_old_component():
    stream = MarketStreamService(clock_ms=lambda: NOW)
    stream.update_simulated(100, 99, 101, 100, NOW - 20_000)
    stream.handle_message('{"e":"markPriceUpdate","E":1700000000000}', NOW)
    market = stream.latest_observation()
    assert market is not None
    assert market.mark_receipt_timestamp_ms == NOW - 20_000
    assert market.freshness_reason(NOW, 10_000) == "MARKET_MARK_STALE"


def test_invalid_numeric_market_message_does_not_advance_timestamp():
    stream = MarketStreamService(clock_ms=lambda: NOW)
    stream.update_simulated(100, 99, 101, 100, NOW - 20_000)
    with pytest.raises(ValueError):
        stream.handle_message('{"e":"markPriceUpdate","E":1700000000000,"p":"bad"}', NOW)
    market = stream.latest_observation()
    assert market is not None
    assert market.mark_receipt_timestamp_ms == NOW - 20_000


def test_market_legacy_timestamps_do_not_supply_freshness():
    market = MarketObservationV1.build(
        symbol="BTCUSDT", mark_price=100, best_bid=99, best_ask=101,
        kline_1m_close=100, kline_1m_open_time_ms=NOW - 60_000,
        kline_1m_close_time_ms=NOW, source_timestamp_ms=NOW,
        receipt_timestamp_ms=NOW, spread_bps=200,
    )
    assert market.freshness_reason(NOW, 10_000) == "MARKET_STREAM_DISCONNECTED"


def test_position_close_is_durable_and_reopen_survives_restart(tmp_path):
    path = tmp_path / "live.db"
    first = PositionSupervisor(path)
    assert any(e.trigger == "POSITION_OPENED" for e in first.evaluate(
        observation(quantity=-1, previous_quantity=0), NOW))
    first.evaluate(observation(quantity=0, previous_quantity=-1, observed_at_ms=NOW + 1), NOW + 1)
    with connection(path) as db:
        state = db.execute("SELECT quantity, is_open FROM live_position_lifecycle WHERE account_id=? AND symbol=? AND position_side=?",
                           ("DEFAULT_ACCOUNT", "BTCUSDT", "BOTH")).fetchone()
    assert state["quantity"] == 0
    assert state["is_open"] == 0
    restarted = PositionSupervisor(path)
    assert any(e.trigger == "POSITION_OPENED" for e in restarted.evaluate(
        observation(quantity=1, previous_quantity=1, observed_at_ms=NOW + 70_000), NOW + 70_000))


def test_position_flat_observation_persists_without_event(tmp_path):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    assert supervisor.evaluate(observation(quantity=0, previous_quantity=0), NOW) == ()
    with connection(path) as db:
        row = db.execute("SELECT quantity, source_hash FROM live_position_lifecycle").fetchone()
    assert row["quantity"] == 0
    assert row["source_hash"] == observation(quantity=0, previous_quantity=0).observation_hash


def test_quick_reopen_emits_open_edge_despite_cooldown(tmp_path):
    supervisor = PositionSupervisor(tmp_path / "live.db")
    supervisor.evaluate(observation(quantity=1, observed_at_ms=NOW), NOW)
    supervisor.evaluate(observation(quantity=0, observed_at_ms=NOW + 1), NOW + 1)
    events = supervisor.evaluate(observation(quantity=-1, observed_at_ms=NOW + 2), NOW + 2)
    assert any(event.trigger == "POSITION_OPENED" for event in events)


def test_position_lifecycle_is_separate_by_account(tmp_path):
    supervisor = PositionSupervisor(tmp_path / "live.db")
    first = supervisor.evaluate(observation(account_id="account-a", quantity=1), NOW)
    second = supervisor.evaluate(observation(account_id="account-b", quantity=1), NOW + 1)
    assert any(event.trigger == "POSITION_OPENED" for event in first)
    assert any(event.trigger == "POSITION_OPENED" for event in second)
    assert supervisor.current_quantity("account-a", "BTCUSDT") == 1
    assert supervisor.current_quantity("account-b", "BTCUSDT") == 1


def test_older_position_observation_cannot_revert_ledger(tmp_path):
    supervisor = PositionSupervisor(tmp_path / "live.db")
    supervisor.evaluate(observation(quantity=1, observed_at_ms=NOW + 100), NOW + 100)
    with pytest.raises(ValueError, match="POSITION_OBSERVATION_OUT_OF_ORDER"):
        supervisor.evaluate(observation(quantity=0, observed_at_ms=NOW), NOW + 101)
    assert supervisor.current_quantity("DEFAULT_ACCOUNT", "BTCUSDT") == 1


def test_restart_direct_sign_flip_persists_close_and_open_edges(tmp_path):
    path = tmp_path / "live.db"
    PositionSupervisor(path).evaluate(observation(quantity=1, observed_at_ms=NOW), NOW)
    restarted = PositionSupervisor(path)
    flip = observation(quantity=-0.5, observed_at_ms=NOW + 1)
    events = restarted.evaluate(flip, NOW + 1)
    edges = [event for event in events if event.trigger in {"POSITION_CLOSED", "POSITION_OPENED"}]
    assert [event.trigger for event in edges] == ["POSITION_CLOSED", "POSITION_OPENED"]
    assert len({event.event_hash for event in edges}) == 2
    assert all(event.source_hash == flip.observation_hash for event in edges)
    assert restarted.current_quantity("DEFAULT_ACCOUNT", "BTCUSDT") == -0.5
    assert PositionSupervisor(path).evaluate(flip, NOW + 2) == ()


def _seed_legacy(path, *, is_open: bool, account_id: str | None = "legacy-a") -> str:
    PositionSupervisor(path)
    snapshot_hash = "account-hash"
    if account_id is not None:
        snapshot = sample_snapshot(account_id=account_id, positions=(), orders=())
        AccountStore(path).save(snapshot)
        snapshot_hash = snapshot.snapshot_hash
    with connection(path) as db:
        db.execute("INSERT INTO live_position_active VALUES ('BTCUSDT', ?, ?)",
                   (int(is_open), NOW - 1000))
    return snapshot_hash


def test_legacy_open_is_bound_and_consumed_without_duplicate_open(tmp_path):
    path = tmp_path / "live.db"
    snapshot_hash = _seed_legacy(path, is_open=True)
    supervisor = PositionSupervisor(path)
    events = supervisor.evaluate(observation(account_id="legacy-a",
                                             account_snapshot_hash=snapshot_hash,
                                             quantity=0.25), NOW)
    assert not any(event.trigger == "POSITION_OPENED" for event in events)
    assert supervisor.current_quantity("legacy-a", "BTCUSDT") == 0.25
    with connection(path) as db:
        assert db.execute("SELECT 1 FROM live_position_active").fetchone() is None


def test_legacy_open_first_flat_emits_close_across_restart(tmp_path):
    path = tmp_path / "live.db"
    snapshot_hash = _seed_legacy(path, is_open=True)
    events = PositionSupervisor(path).evaluate(observation(account_id="legacy-a",
        account_snapshot_hash=snapshot_hash, quantity=0), NOW)
    assert any(event.trigger == "POSITION_CLOSED" for event in events)
    assert PositionSupervisor(path).current_quantity("legacy-a", "BTCUSDT") == 0


def test_legacy_flat_first_nonzero_emits_open(tmp_path):
    path = tmp_path / "live.db"
    snapshot_hash = _seed_legacy(path, is_open=False)
    events = PositionSupervisor(path).evaluate(observation(account_id="legacy-a",
        account_snapshot_hash=snapshot_hash, quantity=-0.5), NOW)
    assert any(event.trigger == "POSITION_OPENED" for event in events)


def test_legacy_snapshot_must_be_latest_for_account(tmp_path):
    path = tmp_path / "live.db"
    old_hash = _seed_legacy(path, is_open=True)
    newer = sample_snapshot(account_id="legacy-a", observed_at_ms=NOW + 1,
                            last_rest_at_ms=NOW + 1, positions=(), orders=())
    AccountStore(path).save(newer)
    with pytest.raises(ValueError, match="LEGACY_POSITION_ACCOUNT_BINDING_REQUIRED"):
        PositionSupervisor(path).evaluate(observation(account_id="legacy-a",
            account_snapshot_hash=old_hash, quantity=0.25), NOW)


def test_legacy_unbound_state_fails_closed_without_consumption(tmp_path):
    path = tmp_path / "live.db"
    _seed_legacy(path, is_open=True, account_id=None)
    with pytest.raises(ValueError, match="LEGACY_POSITION_ACCOUNT_BINDING_REQUIRED"):
        PositionSupervisor(path).evaluate(observation(quantity=0.25), NOW)
    with connection(path) as db:
        assert db.execute("SELECT 1 FROM live_position_active").fetchone() is not None
        assert db.execute("SELECT 1 FROM live_position_lifecycle").fetchone() is None


def test_legacy_ambiguous_account_binding_fails_closed(tmp_path):
    path = tmp_path / "live.db"
    snapshot_hash = _seed_legacy(path, is_open=True)
    AccountStore(path).save(sample_snapshot(account_id="other-account", positions=(), orders=()))
    with pytest.raises(ValueError, match="LEGACY_POSITION_ACCOUNT_BINDING_REQUIRED"):
        PositionSupervisor(path).evaluate(observation(account_id="legacy-a",
            account_snapshot_hash=snapshot_hash, quantity=0.25), NOW)


def test_runtime_recovers_intents_before_account_rest():
    runtime = _runtime(pending=("intent-1",))
    calls: list[str] = []
    runtime.execution_service.reconcile_intent.side_effect = lambda _id: calls.append("intent")
    runtime.account_watch.reconcile_rest_async.side_effect = lambda: calls.append("rest")
    async def run():
        await runtime.start()
        await runtime.stop()
    _run(run())
    assert calls[:2] == ["intent", "rest"]


def test_runtime_existing_side_effect_reconciles_despite_new_entry_readiness():
    runtime = _runtime()
    runtime.intent_store.has_existing_side_effect = Mock(return_value=True)
    runtime.execution_service.reconcile_intent = AsyncMock(return_value="RECOVERED")
    assert _run(runtime.execute_intent("intent-1")) is None
    runtime.execution_service.reconcile_intent.assert_awaited_once_with("intent-1")


def test_api_parses_live_config_once_and_rejects_invalid_flag(monkeypatch):
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_RUNTIME_ENABLED", "sometimes")
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_ENABLED", "false")
    with pytest.raises(ValueError, match="BTC_QUANT_LIVE_V1_RUNTIME_ENABLED"):
        api.create_app()


def test_normalized_mode_is_single_config_authority():
    config = LiveV1Config(enabled=True, runtime_enabled=True)
    assert config.normalized_mode == "B4_RUNTIME"


def test_repeated_shutdown_cancellation_waits_for_owned_position_reconciliation():
    async def run():
        runtime = _runtime()
        finish = asyncio.Event()
        async def owned_operation():
            await finish.wait()
        task = asyncio.create_task(owned_operation(), name="live-v1-position")
        runtime.tasks = (task,)
        runtime._started = True
        shutdown = asyncio.create_task(runtime.stop())
        await asyncio.sleep(0)
        for _ in range(2):
            shutdown.cancel()
            await asyncio.sleep(0)
            assert not shutdown.done()
            assert not task.cancelled()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await shutdown
        assert task.done()
        assert not runtime._started
        runtime.account_watch.close_user_stream.assert_awaited_once()
    asyncio.run(run())
