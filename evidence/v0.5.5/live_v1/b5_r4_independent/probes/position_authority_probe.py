"""Independent, local-only R4 authority and outbox probes."""

import asyncio
import json
from unittest.mock import Mock

import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_position_supervisor import NOW, market_case, observation
from test_live_v1_runtime_r2 import _runtime

from btc_quant_agent.decision.models import CasePackageV1
from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor import (
    PositionEventV1,
    PositionObservationV1,
    PositionSupervisor,
)


def triggers(events):
    return {event.trigger for event in events}


@pytest.mark.parametrize("trigger,first,second", [
    ("STOP_NEAR", {"mark_price": 91}, {"mark_price": 91.1}),
    ("LIQUIDITY_DETERIORATION", {"spread_bps": 12}, {"spread_bps": 13}),
])
def test_two_accounts_independent_and_same_account_cools_after_restart(tmp_path, trigger, first, second):
    path = tmp_path / "live.db"
    supervisor = PositionSupervisor(path)
    a = supervisor.evaluate(observation(account_id="A", **first), NOW)
    b = supervisor.evaluate(observation(account_id="B", observed_at_ms=NOW + 1, **first), NOW + 1)
    assert trigger in triggers(a) and trigger in triggers(b)
    assert trigger not in triggers(PositionSupervisor(path).evaluate(
        observation(account_id="A", observed_at_ms=NOW + 2, **second), NOW + 2))
    assert trigger not in triggers(PositionSupervisor(path).evaluate(
        observation(account_id="B", observed_at_ms=NOW + 3, **second), NOW + 3))
    assert a[0].event_hash != b[0].event_hash


def test_cooldown_full_scope_trigger_symbol_namespace_and_legacy(tmp_path):
    path = tmp_path / "live.db"
    s = PositionSupervisor(path)
    assert "STOP_NEAR" in triggers(s.evaluate(observation(account_id="A", mark_price=91), NOW))
    assert "TP_NEAR" in triggers(s.evaluate(observation(account_id="A", mark_price=109,
        observed_at_ms=NOW + 1), NOW + 1))
    assert "STOP_NEAR" in triggers(s.evaluate(observation(account_id="A", symbol="ETHUSDT",
        mark_price=91, observed_at_ms=NOW + 2), NOW + 2))
    assert "STOP_NEAR" in triggers(s.evaluate(observation(account_id="A", environment="TESTNET",
        credential_namespace="NS_A", mark_price=91, observed_at_ms=NOW + 3), NOW + 3))
    assert "STOP_NEAR" in triggers(s.evaluate(observation(account_id="A", environment="TESTNET",
        credential_namespace="NS_B", mark_price=91, observed_at_ms=NOW + 4), NOW + 4))
    with connection(path) as db:
        db.execute("INSERT INTO live_position_events (event_id,event_hash,trigger,symbol,source_hash,observed_at_ms,payload) VALUES (?,?,?,?,?,?,?)",
                   ("legacy", "legacy-hash", "STOP_NEAR", "LTCUSDT", "old", NOW, "{}"))
    assert "STOP_NEAR" in triggers(s.evaluate(observation(account_id="A", symbol="LTCUSDT",
        mark_price=91, observed_at_ms=NOW + 5), NOW + 5))


def test_lifecycle_flat_reopen_namespace_isolation_and_replay_rejection(tmp_path):
    path = tmp_path / "live.db"
    s = PositionSupervisor(path)
    assert "POSITION_OPENED" in triggers(s.evaluate(observation(quantity=-1), NOW))
    assert "POSITION_OPENED" in triggers(s.evaluate(observation(environment="TESTNET",
        credential_namespace="NS_A", quantity=-1, observed_at_ms=NOW + 1), NOW + 1))
    assert "POSITION_OPENED" in triggers(s.evaluate(observation(environment="TESTNET",
        credential_namespace="NS_B", quantity=-1, observed_at_ms=NOW + 2), NOW + 2))
    assert "POSITION_CLOSED" in triggers(s.evaluate(observation(environment="TESTNET",
        credential_namespace="NS_A", quantity=0, observed_at_ms=NOW + 3), NOW + 3))
    s = PositionSupervisor(path)
    assert "POSITION_OPENED" in triggers(s.evaluate(observation(environment="TESTNET",
        credential_namespace="NS_A", quantity=-0.5, observed_at_ms=NOW + 4), NOW + 4))
    assert s.current_quantity("DEFAULT_ACCOUNT", "BTCUSDT", "DRY_RUN", "NONE") == -1
    assert s.current_quantity("DEFAULT_ACCOUNT", "BTCUSDT", "TESTNET", "NS_B") == -1
    payload = json.loads(observation().canonical_json())
    payload["environment"], payload["credential_namespace"] = "TESTNET", "NS_A"
    with pytest.raises(ValueError, match="observation hash mismatch"):
        PositionObservationV1.model_validate_json(json.dumps(payload))


def test_unbound_legacy_dry_run_blocks_without_rebinding_testnet(tmp_path):
    path = tmp_path / "live.db"
    s = PositionSupervisor(path)
    with connection(path) as db:
        db.execute("INSERT INTO live_position_lifecycle VALUES (?,?,?,?,?,?,?,?,?)",
                   ("DEFAULT_ACCOUNT", "BTCUSDT", "BOTH", 1, 1, "POSITION_OPENED", NOW, NOW, "old"))
    with pytest.raises(ValueError, match="LEGACY_POSITION_LIFECYCLE_AUTHORITY_UNBOUND"):
        s.evaluate(observation(observed_at_ms=NOW + 1), NOW + 1)
    assert "POSITION_OPENED" in triggers(s.evaluate(observation(environment="TESTNET",
        credential_namespace="NS_A", observed_at_ms=NOW + 1), NOW + 1))
    with connection(path) as db:
        assert db.execute("SELECT COUNT(*) FROM live_position_lifecycle WHERE account_id='DEFAULT_ACCOUNT'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM live_position_lifecycle_v2").fetchone()[0] == 1


def test_event_storage_authority_and_hash_must_agree(tmp_path):
    path = tmp_path / "live.db"
    s = PositionSupervisor(path)
    event = s.evaluate(observation(mark_price=91), NOW)[0]
    assert s.get_event(event.event_id) == event
    with connection(path) as db:
        db.execute("UPDATE live_position_events SET account_id='B' WHERE event_id=?", (event.event_id,))
    with pytest.raises(ValueError, match="storage authority mismatch"):
        s.get_event(event.event_id)
    payload = json.loads(event.canonical_json())
    payload["account_id"] = "B"
    with pytest.raises(ValueError):
        PositionEventV1.model_validate(payload)


def test_outbox_two_accounts_frozen_identity_once_and_restart(tmp_path):
    path = tmp_path / "live.db"
    seen = []

    class Analyze:
        async def analyze_case(self, case):
            seen.append(case)

    s = PositionSupervisor(path, analysis_service=Analyze(), fresh_market_case=lambda _: market_case())
    events = [e for account, time in (("A", NOW), ("B", NOW + 1))
              for e in s.evaluate(observation(account_id=account, mark_price=91, observed_at_ms=time), time)
              if e.trigger == "STOP_NEAR"]
    assert len(events) == 2
    asyncio.run(s.drain_pending_dispatches(NOW + 2))
    hashes = {e.event_hash for e in events}
    cases = [case for case in seen if case.position_event_hash in hashes]
    assert len(cases) == 2 and len({case.case_hash for case in cases}) == 2
    frozen = [s.get_dispatch(e.event_id)["position_case_json"] for e in events]
    assert all(frozen)
    asyncio.run(PositionSupervisor(path, analysis_service=Analyze(),
        fresh_market_case=lambda _: market_case()).drain_pending_dispatches(NOW + 3))
    assert len([case for case in seen if case.position_event_hash in hashes]) == 2
    assert all(s.get_dispatch(e.event_id)["state"] == "DONE" for e in events)


def test_expired_lease_does_not_call_analysis(tmp_path):
    path = tmp_path / "live.db"
    event = PositionSupervisor(path).evaluate(observation(), NOW)[0]
    seen = []

    class Analyze:
        async def analyze_case(self, case):
            seen.append(case)

    ticks = iter((NOW, NOW + 500, NOW + 1001))
    s = PositionSupervisor(path, analysis_service=Analyze(),
        fresh_market_case=lambda _: market_case(), lease_clock_ms=lambda: next(ticks, NOW + 1001))
    asyncio.run(s.drain_pending_dispatches(NOW, lease_ms=1000))
    assert seen == []
    assert s.get_dispatch(event.event_id)["state"] == "DISPATCHING"
    assert s.get_dispatch(event.event_id)["position_case_json"]


def test_dispatch_rejects_symbol_mismatch_between_event_and_outbox(tmp_path):
    path = tmp_path / "live.db"
    seen = []

    class Analyze:
        async def analyze_case(self, case):
            seen.append(case)

    def case_for(symbol):
        data = market_case().model_dump(mode="python", exclude={"case_hash"})
        data["symbol"] = symbol
        return CasePackageV1.build(**data)

    s = PositionSupervisor(path, analysis_service=Analyze(), fresh_market_case=case_for)
    event = next(e for e in s.evaluate(observation(), NOW) if e.trigger == "POSITION_OPENED")
    with connection(path) as db:
        db.execute("UPDATE live_position_case_dispatches SET symbol='ETHUSDT' WHERE event_id=?",
                   (event.event_id,))
    asyncio.run(s.drain_pending_dispatches(NOW))
    assert all(case.position_event_hash != event.event_hash for case in seen)
    assert s.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"


def test_runtime_readiness_rejects_verified_other_account_namespace():
    runtime = _runtime(mode="TESTNET")
    runtime._started = True
    runtime.accepting_risk = True
    snapshot = runtime.account_watch.latest_snapshot.return_value
    snapshot.account_id = "OTHER_ACCOUNT"
    snapshot.verify = Mock()
    assert runtime._readiness_reason() == "POSITION_ACCOUNT_AUTHORITY_MISMATCH"


def test_runtime_readiness_rejects_invalid_snapshot_hash():
    runtime = _runtime(mode="DRY_RUN")
    runtime._started = True
    runtime.accepting_risk = True
    runtime.account_watch.latest_snapshot.return_value.verify = Mock(side_effect=ValueError("hash mismatch"))
    assert runtime._readiness_reason() == "POSITION_ACCOUNT_AUTHORITY_MISMATCH"


def test_start_does_not_accept_other_account_after_rest_reconciliation():
    runtime = _runtime(mode="TESTNET")
    runtime.account_watch.latest_snapshot.return_value = sample_snapshot(
        account_id="OTHER_ACCOUNT", environment="TESTNET",
        credential_namespace="BINANCE_TESTNET", rest_base_url="https://testnet.binancefuture.com",
        positions=(), orders=())

    async def run():
        try:
            await runtime.start()
            assert not runtime.accepting_risk
        finally:
            await runtime.stop()

    asyncio.run(run())


def test_runtime_delegates_intent_with_wrong_account_snapshot():
    runtime = _runtime(mode="TESTNET")
    runtime._started = True
    runtime.accepting_risk = True
    runtime.account_watch.latest_snapshot.return_value = sample_snapshot(
        account_id="OTHER_ACCOUNT", environment="TESTNET",
        credential_namespace="BINANCE_TESTNET", rest_base_url="https://testnet.binancefuture.com",
        positions=(), orders=())
    runtime.intent_store.get_intent = Mock(return_value=Mock(symbol=runtime.config.symbol))
    asyncio.run(runtime.execute_intent("intent-1"))
    runtime.execution_service.execute_approved_intent.assert_not_awaited()
