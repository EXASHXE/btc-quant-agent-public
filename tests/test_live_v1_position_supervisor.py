from __future__ import annotations

import json

import pytest

from btc_quant_agent.decision.models import CasePackageV1
from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor import (
    PositionObservationV1,
    PositionSupervisor,
    position_case_from_event,
)

NOW = 1_700_000_000_000
HASH = "a" * 64


def observation(**changes: object) -> PositionObservationV1:
    values: dict[str, object] = {
        "account_snapshot_hash": HASH, "market_source_hash": "b" * 64,
        "symbol": "BTCUSDT", "observed_at_ms": NOW, "quantity": 1.0,
        "previous_quantity": 0.0, "entry_price": 100.0, "mark_price": 100.0,
        "unrealized_pnl_usdt": 0.0, "realized_pnl_usdt": 0.0,
        "margin_usdt": 20.0, "stop_price": 90.0, "take_profit_price": 110.0,
        "funding_rate": 0.0, "oi_change_pct": 0.0, "volatility_percentile": 0.2,
        "spread_bps": 1.0, "tactical_regime": "BULLISH", "grid_boundary_breached": False,
        "order_status": "FILLED", "order_filled_quantity": 1.0,
        "order_observed_at_ms": NOW, "evidence_id": "c" * 64,
        "signal_identity": "new-signal", "prior_evidence_ids": ("d" * 64,),
        "prior_signal_identities": ("old-signal",), "add_opportunity": False,
    }
    values.update(changes)
    return PositionObservationV1.build(**values)


def market_case() -> CasePackageV1:
    return CasePackageV1.build(
        case_id="base", created_at_ms=NOW, observed_at_ms=NOW,
        expires_at_ms=NOW + 60_000, symbol="BTCUSDT", trigger="MARKET_WATCH",
        strategy="BREAKOUT", strategy_version="v1", direction="LONG",
        evidence_id="c" * 64, snapshot_hash="snapshot", signal_identity="new-signal",
        price=100.0, entry_low=99.0, entry_high=101.0, stop_loss=90.0,
        take_profit_1=110.0, take_profit_2=120.0, atr=1.0,
        data_quality="OK", spread_bps=1.0, liquidity_usdt=100_000.0,
    )


@pytest.mark.parametrize(("change", "trigger"), [
    ({"previous_quantity": 0.0}, "POSITION_OPENED"),
    ({"previous_quantity": 1.0, "order_status": "PARTIALLY_FILLED",
      "order_observed_at_ms": NOW - 31_000}, "PARTIAL_FILL_STALE"),
    ({"previous_quantity": 1.0, "mark_price": 91.0}, "STOP_NEAR"),
    ({"previous_quantity": 1.0, "mark_price": 109.0}, "TP_NEAR"),
    ({"previous_quantity": 1.0, "tactical_regime": "BEARISH"}, "REGIME_REVERSAL"),
    ({"previous_quantity": 1.0, "oi_change_pct": 0.25}, "OI_SHOCK"),
    ({"previous_quantity": 1.0, "funding_rate": 0.002}, "FUNDING_SHOCK"),
    ({"previous_quantity": 1.0, "volatility_percentile": 0.95}, "VOLATILITY_SPIKE"),
    ({"previous_quantity": 1.0, "spread_bps": 12.0}, "LIQUIDITY_DETERIORATION"),
    ({"previous_quantity": 1.0, "grid_boundary_breached": True}, "GRID_BOUNDARY_BREACH"),
    ({"previous_quantity": 1.0, "add_opportunity": True}, "ADD_OPPORTUNITY"),
])
def test_each_trigger_persists_with_source_identity(tmp_path, change, trigger):
    supervisor = PositionSupervisor(tmp_path / "live.db")
    events = supervisor.evaluate(observation(**change), NOW)
    found = next(event for event in events if event.trigger == trigger)
    assert found.source_hash == observation(**change).observation_hash
    found.verify()
    assert supervisor.get_event(found.event_id) == found


def test_restart_dedupes_identical_source_and_cools_new_ticks(tmp_path):
    path = tmp_path / "live.db"
    first = PositionSupervisor(path).evaluate(observation(), NOW)
    assert first
    restarted = PositionSupervisor(path)
    assert restarted.evaluate(observation(), NOW + 1) == ()
    assert restarted.evaluate(observation(mark_price=101.0), NOW + 2) == ()
    assert restarted.evaluate(observation(mark_price=102.0), NOW + 60_001) == ()


def test_add_requires_independent_market_evidence(tmp_path):
    supervisor = PositionSupervisor(tmp_path / "live.db")
    assert not any(e.trigger == "ADD_OPPORTUNITY" for e in supervisor.evaluate(
        observation(previous_quantity=1.0, add_opportunity=True,
                    evidence_id="d" * 64), NOW))


def test_position_case_links_fresh_verified_market_identity(tmp_path):
    event = PositionSupervisor(tmp_path / "live.db").evaluate(observation(), NOW)[0]
    base = market_case()
    case = position_case_from_event(base, event, now_ms=NOW)
    case.verify()
    assert case.evidence_id == base.evidence_id
    assert case.signal_identity == base.signal_identity
    assert case.base_case_hash == base.case_hash
    assert case.position_event_hash == event.event_hash
    assert case.case_hash != base.case_hash


import asyncio


def test_only_material_new_event_invokes_existing_analysis(tmp_path):
    async def run() -> None:
        calls: list[str] = []

        class Spy:
            async def analyze_case(self, case: CasePackageV1) -> None:
                calls.append(case.case_hash)

        supervisor = PositionSupervisor(
            tmp_path / "live.db", analysis_service=Spy(), fresh_market_case=lambda _: market_case(),
        )
        ordinary = observation(previous_quantity=1.0)
        assert await supervisor.process(ordinary, NOW) == ()
        assert not calls
        assert await supervisor.process(observation(), NOW)
        assert len(calls) == 1
        assert await supervisor.process(observation(), NOW + 1) == ()
        assert len(calls) == 1

    asyncio.run(run())


def test_r1_06_short_position_opened_and_reopen_cycle(tmp_path):
    supervisor = PositionSupervisor(tmp_path / "live.db")

    # 1. 0 -> negative opens short
    short_obs = observation(previous_quantity=0.0, quantity=-0.5)
    events1 = supervisor.evaluate(short_obs, NOW)
    assert any(e.trigger == "POSITION_OPENED" for e in events1)

    # 2. Repeated same observation dedupes
    events2 = supervisor.evaluate(short_obs, NOW + 1)
    assert events2 == ()

    # 3. Close position
    close_obs = observation(previous_quantity=-0.5, quantity=0.0)
    events3 = supervisor.evaluate(close_obs, NOW + 10_000)
    assert not any(e.trigger == "POSITION_OPENED" for e in events3)

    # 4. Reopen short works correctly after cooldown
    reopen_short_obs = observation(previous_quantity=0.0, quantity=-0.8)
    events4 = supervisor.evaluate(reopen_short_obs, NOW + 70_000)
    assert any(e.trigger == "POSITION_OPENED" for e in events4)

    # 5. Close and reopen long works correctly
    close_obs2 = observation(previous_quantity=-0.8, quantity=0.0)
    supervisor.evaluate(close_obs2, NOW + 80_000)
    reopen_long_obs = observation(previous_quantity=0.0, quantity=1.0)
    events5 = supervisor.evaluate(reopen_long_obs, NOW + 150_000)
    assert any(e.trigger == "POSITION_OPENED" for e in events5)


def test_r1_05_unavailable_data_does_not_fire_triggers(tmp_path):
    supervisor = PositionSupervisor(tmp_path / "live.db")

    # When optional data fields are None (unavailable), data-dependent triggers must NOT fire
    obs_unavailable = observation(
        previous_quantity=1.0,
        funding_rate=None,
        oi_change_pct=None,
        volatility_percentile=None,
        tactical_regime=None,
        spread_bps=None,
        evidence_id=None,
        signal_identity=None,
        add_opportunity=True,
    )
    events = supervisor.evaluate(obs_unavailable, NOW)
    triggers = {e.trigger for e in events}
    assert "FUNDING_SHOCK" not in triggers
    assert "OI_SHOCK" not in triggers
    assert "VOLATILITY_SPIKE" not in triggers
    assert "REGIME_REVERSAL" not in triggers
    assert "LIQUIDITY_DETERIORATION" not in triggers
    assert "ADD_OPPORTUNITY" not in triggers

    # When verified source data is provided, corresponding trigger fires
    obs_funding = observation(previous_quantity=1.0, funding_rate=0.002)
    events_funding = supervisor.evaluate(obs_funding, NOW + 65_000)
    assert any(e.trigger == "FUNDING_SHOCK" for e in events_funding)

    obs_regime = observation(previous_quantity=1.0, quantity=1.0, tactical_regime="BEARISH")
    events_regime = supervisor.evaluate(obs_regime, NOW + 130_000)
    assert any(e.trigger == "REGIME_REVERSAL" for e in events_regime)


def test_r1_05_restart_does_not_duplicate_position_case_analysis(tmp_path):
    async def run() -> None:
        calls: list[str] = []

        class Spy:
            async def analyze_case(self, case: CasePackageV1) -> None:
                calls.append(case.case_hash)

        db_file = tmp_path / "live.db"
        supervisor1 = PositionSupervisor(
            db_file, analysis_service=Spy(), fresh_market_case=lambda _: market_case(),
        )
        obs = observation(previous_quantity=0.0, quantity=1.0)
        events = await supervisor1.process(obs, NOW)
        assert len(events) >= 1
        assert len(calls) == 1

        # Simulate restart on same DB
        supervisor2 = PositionSupervisor(
            db_file, analysis_service=Spy(), fresh_market_case=lambda _: market_case(),
        )
        # Even if process is called with the observation again, dispatches table prevents duplicate analysis
        await supervisor2.process(obs, NOW)
        assert len(calls) == 1

    asyncio.run(run())


def test_r1_1_01_crash_after_event_persistence_restart_drains_it(tmp_path):
    async def run() -> None:
        calls: list[str] = []

        class Spy:
            async def analyze_case(self, case: CasePackageV1) -> None:
                calls.append(case.case_hash)

        db_file = tmp_path / "live.db"
        # 1. Supervisor evaluates event without dispatching (simulating crash right after persistence)
        supervisor1 = PositionSupervisor(db_file)
        events = supervisor1.evaluate(observation(), NOW)
        assert len(events) >= 1
        assert not calls

        with connection(db_file) as db:
            row = db.execute(
                "SELECT state FROM live_position_case_dispatches WHERE event_id=?",
                (events[0].event_id,),
            ).fetchone()
        assert row is not None
        assert row["state"] == "PENDING"

        # 2. Restarted supervisor drains pending dispatch
        supervisor2 = PositionSupervisor(
            db_file, analysis_service=Spy(), fresh_market_case=lambda _: market_case(),
        )
        drained = await supervisor2.drain_pending_dispatches(NOW + 5_000)
        assert len(drained) == len(events)
        assert len(calls) == 1

        with connection(db_file) as db:
            row_after = db.execute(
                "SELECT state, case_hash FROM live_position_case_dispatches WHERE event_id=?",
                (events[0].event_id,),
            ).fetchone()
        assert row_after["state"] == "DONE"
        assert row_after["case_hash"] == calls[0]

    asyncio.run(run())


def test_r1_1_01_crash_after_claim_lease_recovery(tmp_path):
    async def run() -> None:
        calls: list[str] = []

        class Spy:
            async def analyze_case(self, case: CasePackageV1) -> None:
                calls.append(case.case_hash)

        db_file = tmp_path / "live.db"
        supervisor = PositionSupervisor(
            db_file, analysis_service=Spy(), fresh_market_case=lambda _: market_case(),
        )
        events = supervisor.evaluate(observation(), NOW)
        assert len(events) >= 1
        event = events[0]

        # Simulate crash while DISPATCHING under active lease
        lease_expiry = NOW + 10_000
        with connection(db_file) as db:
            db.execute(
                """
                UPDATE live_position_case_dispatches
                SET state = 'DISPATCHING',
                    lease_token = 'crashed-worker-token',
                    lease_expires_at_ms = ?,
                    retry_count = 1
                WHERE event_id = ?
                """,
                (lease_expiry, event.event_id),
            )

        # Before lease expires: cannot claim
        drained_early = await supervisor.drain_pending_dispatches(NOW + 5_000)
        assert len(drained_early) == 0
        assert not calls

        # After lease expires: lease recovery claims and finishes
        drained_recovered = await supervisor.drain_pending_dispatches(NOW + 15_000)
        assert len(drained_recovered) == 1
        assert len(calls) == 1

        with connection(db_file) as db:
            row = db.execute(
                "SELECT state, retry_count, lease_token FROM live_position_case_dispatches WHERE event_id=?",
                (event.event_id,),
            ).fetchone()
        assert row["state"] == "DONE"
        assert row["retry_count"] == 2
        assert row["lease_token"] is None

    asyncio.run(run())


def test_r1_1_01_deterministic_case_identity_across_retries(tmp_path):
    event = PositionSupervisor(tmp_path / "live.db").evaluate(observation(), NOW)[0]
    base = market_case()

    case_t1 = position_case_from_event(base, event, now_ms=NOW)
    case_t2 = position_case_from_event(base, event, now_ms=NOW + 500_000)

    assert case_t1.case_id == case_t2.case_id
    assert case_t1.case_hash == case_t2.case_hash
    assert case_t1.created_at_ms == event.observed_at_ms
    assert case_t2.created_at_ms == event.observed_at_ms


def test_r1_1_01_retry_after_downstream_case_reservation_does_not_reissue_primary_provider(tmp_path):
    async def run() -> None:
        from types import SimpleNamespace

        from test_live_v1_decision_models import sample_analysis

        from btc_quant_agent.approval.store import LiveStore
        from btc_quant_agent.decision.backends import ResponsesBackend
        from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
        from btc_quant_agent.decision.service import TacticalLiveService

        calls = []

        async def parse(**kwargs):
            calls.append(kwargs)
            case_data = json.loads(kwargs["input"][1]["content"])
            validated = CasePackageV1.model_validate_json(json.dumps(case_data))
            return SimpleNamespace(
                status="completed", output=[], model="configured-model",
                id="response-1", output_parsed=sample_analysis(validated),
            )

        db_file = tmp_path / "live.db"
        store = LiveStore(str(db_file))
        backend = ResponsesBackend(
            "configured-model", 1,
            client=SimpleNamespace(responses=SimpleNamespace(parse=parse)),
            clock_ms=lambda: NOW,
        )
        service = TacticalLiveService(
            store, backend, RiskCompilerV1(RiskPolicyV1()), clock_ms=lambda: NOW,
        )

        supervisor = PositionSupervisor(
            db_file, analysis_service=service, fresh_market_case=lambda _: market_case(),
        )

        # 1. Process event: triggers analyze_case -> primary LLM called (call count = 1)
        events = await supervisor.process(observation(), NOW)
        assert len(events) >= 1
        assert len(calls) == 1

        # 2. Simulate worker crash before marking DONE: reset dispatch to PENDING
        with connection(db_file) as db:
            db.execute(
                "UPDATE live_position_case_dispatches SET state='PENDING' WHERE event_id=?",
                (events[0].event_id,),
            )

        # 3. Retry dispatch: case was already reserved in LiveStore, so primary provider is NOT reissued!
        drained = await supervisor.drain_pending_dispatches(NOW + 1000)
        assert len(drained) == 1
        assert len(calls) == 1  # Primary provider NOT re-called!

        with connection(db_file) as db:
            row = db.execute(
                "SELECT state FROM live_position_case_dispatches WHERE event_id=?",
                (events[0].event_id,),
            ).fetchone()
        assert row["state"] == "DONE"

    asyncio.run(run())


def test_r1_1_01_done_never_dispatches_twice(tmp_path):
    async def run() -> None:
        calls: list[str] = []

        class Spy:
            async def analyze_case(self, case: CasePackageV1) -> None:
                calls.append(case.case_hash)

        db_file = tmp_path / "live.db"
        supervisor = PositionSupervisor(
            db_file, analysis_service=Spy(), fresh_market_case=lambda _: market_case(),
        )
        events = await supervisor.process(observation(), NOW)
        assert len(events) >= 1
        assert len(calls) == 1

        # Calling drain_pending_dispatches again does nothing
        drained = await supervisor.drain_pending_dispatches(NOW + 1000)
        assert len(drained) == 0
        assert len(calls) == 1

    asyncio.run(run())


def test_r1_1_01_no_event_silently_disappears_due_to_source_hash_dedupe(tmp_path):
    async def run() -> None:
        calls: list[str] = []

        class Spy:
            async def analyze_case(self, case: CasePackageV1) -> None:
                calls.append(case.case_hash)

        db_file = tmp_path / "live.db"
        obs = observation()

        # 1. Event generated and persisted, but process crashes before analysis
        supervisor1 = PositionSupervisor(db_file)
        events1 = supervisor1.evaluate(obs, NOW)
        assert len(events1) >= 1

        # 2. Same observation arrives again after restart
        supervisor2 = PositionSupervisor(
            db_file, analysis_service=Spy(), fresh_market_case=lambda _: market_case(),
        )
        # evaluate() returns () because source_hash is already present
        events2 = supervisor2.evaluate(obs, NOW + 1000)
        assert events2 == ()

        # But process() or drain_pending_dispatches() drains unfinished dispatches; event was not lost!
        await supervisor2.drain_pending_dispatches(NOW + 1000)
        assert len(calls) == 1

    asyncio.run(run())
