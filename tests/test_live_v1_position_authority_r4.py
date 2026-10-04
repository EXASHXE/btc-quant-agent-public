"""R4 position authority must survive cooldowns and database reuse."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_position_supervisor import NOW, market_case, observation
from test_live_v1_runtime_r2 import _run, _runtime

from btc_quant_agent.decision.models import content_hash
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor import (
    PositionEventV1,
    PositionObservationV1,
    PositionSupervisor,
    position_case_from_event,
)


def _triggers(events):
    return [event.trigger for event in events]


def test_new_position_event_requires_complete_authority():
    with pytest.raises(ValueError, match="position event authority incomplete"):
        PositionEventV1.build(event_id="new", trigger="STOP_NEAR", symbol="BTCUSDT",
                              source_hash="a" * 64, observed_at_ms=NOW, details={})


def test_stop_near_cooldown_is_scoped_to_account_and_namespace(tmp_path):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    first = supervisor.evaluate(observation(account_id="A", mark_price=91), NOW)
    second = supervisor.evaluate(observation(account_id="B", mark_price=91,
                                              observed_at_ms=NOW + 1), NOW + 1)
    assert "STOP_NEAR" in _triggers(first)
    assert "STOP_NEAR" in _triggers(second)
    assert "STOP_NEAR" not in _triggers(supervisor.evaluate(
        observation(account_id="B", mark_price=91.1, observed_at_ms=NOW + 2), NOW + 2))
    restarted = PositionSupervisor(path)
    assert "STOP_NEAR" not in _triggers(restarted.evaluate(
        observation(account_id="A", mark_price=91.2, observed_at_ms=NOW + 3), NOW + 3))


def test_two_account_stop_events_dispatch_distinct_frozen_cases_once(tmp_path):
    path = tmp_path / "live.db"
    analyzed = []

    class Analysis:
        async def analyze_case(self, case):
            analyzed.append(case)

    supervisor = PositionSupervisor(path, analysis_service=Analysis(),
                                    fresh_market_case=lambda _: market_case())
    events = supervisor.evaluate(observation(account_id="A", mark_price=91), NOW)
    events += supervisor.evaluate(observation(account_id="B", mark_price=91,
                                              observed_at_ms=NOW + 1), NOW + 1)
    stops = [event for event in events if event.trigger == "STOP_NEAR"]
    assert {event.account_id for event in stops} == {"A", "B"}
    asyncio.run(supervisor.drain_pending_dispatches(NOW + 1))
    stop_cases = [case for case in analyzed if case.position_event_hash in
                  {event.event_hash for event in stops}]
    assert len(stop_cases) == 2
    assert len({case.case_hash for case in stop_cases}) == 2
    restarted = PositionSupervisor(path, analysis_service=Analysis(),
                                   fresh_market_case=lambda _: market_case())
    assert asyncio.run(restarted.drain_pending_dispatches(NOW + 2)) == ()
    assert all(restarted.get_dispatch(event.event_id)["state"] == "DONE" for event in stops)
    assert len(analyzed) == len(events)


def test_dry_run_state_cannot_suppress_testnet_open(tmp_path):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    supervisor.evaluate(observation(quantity=1), NOW)
    testnet = observation(environment="TESTNET", credential_namespace="BINANCE_TESTNET",
                          quantity=1, observed_at_ms=NOW + 1)
    opened = PositionSupervisor(path).evaluate(testnet, NOW + 1)
    assert "POSITION_OPENED" in _triggers(opened)
    assert PositionSupervisor(path).current_quantity("DEFAULT_ACCOUNT", "BTCUSDT",
        "DRY_RUN", "NONE") == 1
    assert PositionSupervisor(path).current_quantity("DEFAULT_ACCOUNT", "BTCUSDT",
        "TESTNET", "BINANCE_TESTNET") == 1


def test_credential_namespace_and_account_are_distinct_authorities(tmp_path):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    first = supervisor.evaluate(observation(account_id="A", mark_price=91), NOW)
    other_namespace = observation(account_id="A", environment="TESTNET",
        credential_namespace="BINANCE_TESTNET", mark_price=91,
        observed_at_ms=NOW + 1)
    second = supervisor.evaluate(other_namespace, NOW + 1)
    assert "STOP_NEAR" in _triggers(first)
    assert "STOP_NEAR" in _triggers(second)
    assert "POSITION_OPENED" in _triggers(second)


def test_distinct_testnet_namespace_does_not_share_cooldown(tmp_path):
    supervisor = PositionSupervisor(tmp_path / "live.db")
    first = supervisor.evaluate(observation(environment="TESTNET",
        credential_namespace="TESTNET_A", account_id="A", mark_price=91), NOW)
    second = supervisor.evaluate(observation(environment="TESTNET",
        credential_namespace="TESTNET_B", account_id="A", mark_price=91,
        observed_at_ms=NOW + 1), NOW + 1)
    assert "STOP_NEAR" in _triggers(first)
    assert "STOP_NEAR" in _triggers(second)


def test_cooldown_key_keeps_symbol_and_trigger_independent(tmp_path):
    supervisor = PositionSupervisor(tmp_path / "live.db")
    first = supervisor.evaluate(observation(mark_price=91), NOW)
    by_trigger = supervisor.evaluate(observation(mark_price=109,
        observed_at_ms=NOW + 1), NOW + 1)
    by_symbol = supervisor.evaluate(observation(symbol="ETHUSDT", mark_price=91,
        observed_at_ms=NOW + 2), NOW + 2)
    assert "STOP_NEAR" in _triggers(first)
    assert "TP_NEAR" in _triggers(by_trigger)
    assert "STOP_NEAR" in _triggers(by_symbol)


def test_observation_hash_cannot_replay_under_changed_environment():
    valid = observation()
    payload = json.loads(valid.canonical_json())
    payload["environment"] = "TESTNET"
    payload["credential_namespace"] = "BINANCE_TESTNET"
    with pytest.raises(ValueError, match="observation hash mismatch"):
        PositionObservationV1.model_validate_json(json.dumps(payload))


def test_legacy_unscoped_cooldown_does_not_suppress_scoped_event(tmp_path):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    with connection(path) as db:
        db.execute("INSERT INTO live_position_events (event_id, event_hash, trigger, symbol, "
                   "source_hash, observed_at_ms, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   ("legacy", "legacy-hash", "STOP_NEAR", "BTCUSDT", "legacy-source", NOW,
                    "{}"))
    events = supervisor.evaluate(observation(mark_price=91, observed_at_ms=NOW + 1), NOW + 1)
    assert "STOP_NEAR" in _triggers(events)


def test_flat_reopen_is_durable_with_complete_authority(tmp_path):
    path = tmp_path / "live.db"
    first = PositionSupervisor(path)
    first.evaluate(observation(environment="TESTNET", credential_namespace="BINANCE_TESTNET",
        quantity=-1), NOW)
    first.evaluate(observation(environment="TESTNET", credential_namespace="BINANCE_TESTNET",
        quantity=0, observed_at_ms=NOW + 1), NOW + 1)
    reopened = PositionSupervisor(path).evaluate(observation(
        environment="TESTNET", credential_namespace="BINANCE_TESTNET",
        quantity=-0.5, observed_at_ms=NOW + 2), NOW + 2)
    assert _triggers(reopened).count("POSITION_OPENED") == 1


def test_old_unscoped_lifecycle_row_cannot_suppress_testnet_open(tmp_path):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    with connection(path) as db:
        db.execute("INSERT INTO live_position_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("DEFAULT_ACCOUNT", "BTCUSDT", "BOTH", 1.0, 1, "POSITION_OPENED",
             NOW, NOW, "legacy-source"))
    opened = supervisor.evaluate(observation(environment="TESTNET",
        credential_namespace="BINANCE_TESTNET", quantity=1, observed_at_ms=NOW + 1), NOW + 1)
    assert "POSITION_OPENED" in _triggers(opened)


@pytest.mark.parametrize(("old_quantity", "new_quantity"), [(1.0, 1.0), (1.0, 0.0), (0.0, 1.0)])
def test_unbound_legacy_lifecycle_blocks_dry_run_transition(
    tmp_path, old_quantity, new_quantity,
):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    with connection(path) as db:
        db.execute("INSERT INTO live_position_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("DEFAULT_ACCOUNT", "BTCUSDT", "BOTH", old_quantity, int(old_quantity != 0),
             "POSITION_OPENED" if old_quantity else "POSITION_CLOSED", NOW, NOW,
             "legacy-source"))
    with pytest.raises(ValueError, match="LEGACY_POSITION_LIFECYCLE_AUTHORITY_UNBOUND"):
        supervisor.evaluate(observation(quantity=new_quantity, observed_at_ms=NOW + 1), NOW + 1)
    with connection(path) as db:
        assert db.execute("SELECT 1 FROM live_position_lifecycle_v2").fetchone() is None
        assert db.execute("SELECT 1 FROM live_position_events").fetchone() is None
        assert db.execute("SELECT 1 FROM live_position_observed_sources").fetchone() is None


def test_runtime_blocks_new_risk_on_unbound_dry_run_lifecycle(tmp_path):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    with connection(path) as db:
        db.execute("INSERT INTO live_position_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("DEFAULT_ACCOUNT", "BTCUSDT", "BOTH", 1.0, 1, "POSITION_OPENED",
             NOW, NOW, "legacy-source"))
    runtime = _runtime(mode="DRY_RUN")
    runtime.supervisor = supervisor
    runtime.accepting_risk = True
    runtime.account_watch.latest_snapshot.return_value = sample_snapshot(
        account_id="DEFAULT_ACCOUNT", environment="DRY_RUN", credential_namespace="NONE",
        rest_base_url="local://paper", positions=(), orders=())
    runtime.market_stream.latest_observation = Mock(return_value=Mock(
        symbol="BTCUSDT", observation_hash="market-source", mark_price=60500.0,
        spread_bps=1.0))
    _run(runtime.poll_positions(NOW + 1))
    assert not runtime.accepting_risk
    assert runtime.blocked_reason == "LEGACY_POSITION_LIFECYCLE_AUTHORITY_UNBOUND"
    runtime._started = True
    runtime.accepting_risk = True  # REST reconciliation must not override the local block.
    assert runtime._readiness_reason() == "LEGACY_POSITION_LIFECYCLE_AUTHORITY_UNBOUND"


def test_runtime_start_blocks_unbound_legacy_lifecycle(tmp_path):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    with connection(path) as db:
        db.execute("INSERT INTO live_position_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("DEFAULT_ACCOUNT", "BTCUSDT", "BOTH", 1.0, 1, "POSITION_OPENED",
             NOW, NOW, "legacy-source"))
    runtime = _runtime(mode="DRY_RUN")
    runtime.supervisor = supervisor
    with pytest.raises(ExecutionBlocked, match="LEGACY_POSITION_LIFECYCLE_AUTHORITY_UNBOUND"):
        asyncio.run(runtime.start())
    assert not runtime.accepting_risk
    assert not runtime.tasks


def test_rest_reconcile_cannot_reenable_unbound_legacy_lifecycle(tmp_path):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    with connection(path) as db:
        db.execute("INSERT INTO live_position_lifecycle VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("DEFAULT_ACCOUNT", "BTCUSDT", "BOTH", 1.0, 1, "POSITION_OPENED",
             NOW, NOW, "legacy-source"))
    runtime = _runtime(mode="DRY_RUN")
    runtime.supervisor = supervisor

    class OneCycleStop:
        stopped = False

        def is_set(self):
            return self.stopped

        async def wait(self):
            raise TimeoutError

        def set(self):
            self.stopped = True

    runtime._stop_event = OneCycleStop()

    async def one_reconcile():
        runtime._stop_event.set()
        return runtime.account_watch.latest_snapshot()

    runtime.account_watch.reconcile_rest_async.side_effect = one_reconcile
    _run(runtime._rest_loop())
    assert not runtime.accepting_risk
    assert runtime.blocked_reason == "LEGACY_POSITION_LIFECYCLE_AUTHORITY_UNBOUND"


def test_runtime_poll_uses_verified_account_environment_and_namespace(tmp_path):
    path = tmp_path / "live.db"
    PositionSupervisor(path).evaluate(observation(quantity=1), NOW)
    runtime = _runtime(mode="TESTNET")
    runtime.supervisor = PositionSupervisor(path)
    position = sample_snapshot(account_id="DEFAULT_ACCOUNT", orders=()).positions[0]
    snapshot = sample_snapshot(account_id="DEFAULT_ACCOUNT", positions=(position,), orders=())
    runtime.account_watch.latest_snapshot = Mock(return_value=snapshot)
    runtime.market_stream.latest_observation = Mock(return_value=Mock(
        symbol="BTCUSDT", observation_hash="market-source", mark_price=60500.0, spread_bps=1.0))
    _run(runtime.poll_positions(NOW + 1))
    assert runtime.supervisor.current_quantity(
        "DEFAULT_ACCOUNT", "BTCUSDT", "TESTNET", "BINANCE_TESTNET") == 0.1
    assert runtime.supervisor.current_quantity(
        "DEFAULT_ACCOUNT", "BTCUSDT", "DRY_RUN", "NONE") == 1
    with connection(path) as db:
        rows = db.execute("SELECT environment, credential_namespace FROM live_position_events "
                          "WHERE trigger='POSITION_OPENED' ORDER BY observed_at_ms").fetchall()
    assert [(row["environment"], row["credential_namespace"]) for row in rows] == [
        ("DRY_RUN", "NONE"), ("TESTNET", "BINANCE_TESTNET")]


def test_invalid_account_snapshot_blocks_runtime_risk():
    runtime = _runtime(mode="DRY_RUN")
    runtime.accepting_risk = True
    runtime.account_watch.latest_snapshot.return_value.verify.side_effect = ValueError(
        "snapshot hash mismatch")
    _run(runtime.poll_positions(NOW))
    assert not runtime.accepting_risk
    assert runtime.blocked_reason == "POSITION_ACCOUNT_AUTHORITY_MISMATCH"


def test_runtime_rejects_snapshot_from_other_environment():
    runtime = _runtime(mode="TESTNET")
    runtime.accepting_risk = True
    snapshot = runtime.account_watch.latest_snapshot.return_value
    snapshot.environment = "DRY_RUN"
    snapshot.credential_namespace = "NONE"
    _run(runtime.poll_positions(NOW))
    assert not runtime.accepting_risk
    assert runtime.blocked_reason == "POSITION_ACCOUNT_AUTHORITY_MISMATCH"


def test_outbox_fails_closed_if_event_authority_row_disagrees_with_payload(tmp_path):
    path = tmp_path / "live.db"
    calls = []

    class Analysis:
        async def analyze_case(self, case):
            calls.append(case)

    supervisor = PositionSupervisor(path, analysis_service=Analysis(),
                                    fresh_market_case=lambda _: market_case())
    event = supervisor.evaluate(observation(mark_price=91), NOW)[0]
    with connection(path) as db:
        db.execute("DROP TRIGGER IF EXISTS trg_live_position_events_immutable_update")
        db.execute("UPDATE live_position_events SET account_id='other-account' WHERE event_id=?",
                   (event.event_id,))
    dispatched = asyncio.run(supervisor.drain_pending_dispatches(NOW))
    assert all(item.event_id != event.event_id for item in dispatched)
    assert all(case.position_event_hash != event.event_hash for case in calls)
    assert supervisor.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"


def test_legacy_frozen_position_case_dispatch_retains_exact_event_hash(tmp_path):
    path = tmp_path / "live.db"
    analyzed = []

    class Analysis:
        async def analyze_case(self, case):
            analyzed.append(case)

    supervisor = PositionSupervisor(path, analysis_service=Analysis(),
                                    fresh_market_case=lambda _: market_case())
    old_payload = {"schema_version": "POSITION_EVENT_V1", "event_id": "legacy-event",
                   "trigger": "STOP_NEAR", "symbol": "BTCUSDT", "source_hash": "a" * 64,
                   "observed_at_ms": NOW, "details": {}}
    old_payload["event_hash"] = content_hash(old_payload)
    event = PositionEventV1.model_validate_json(json.dumps(old_payload))
    frozen = position_case_from_event(market_case(), event)
    with connection(path) as db:
        db.execute("INSERT INTO live_position_events (event_id, event_hash, trigger, symbol, "
                   "source_hash, observed_at_ms, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (event.event_id, event.event_hash, event.trigger, event.symbol,
                    event.source_hash, event.observed_at_ms, json.dumps(old_payload)))
        db.execute("INSERT INTO live_position_case_dispatches "
                   "(event_id, event_hash, position_case_id, position_case_hash, "
                   "position_case_json, case_hash, symbol, state, created_at_ms, updated_at_ms) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)",
                   (event.event_id, event.event_hash, frozen.case_id, frozen.case_hash,
                    frozen.canonical_json(), frozen.case_hash, event.symbol, NOW, NOW))
    assert asyncio.run(supervisor.drain_pending_dispatches(NOW)) == (event,)
    assert len(analyzed) == 1
    assert analyzed[0].canonical_json() == frozen.canonical_json()
