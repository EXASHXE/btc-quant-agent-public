from __future__ import annotations

import asyncio
import sqlite3

import pytest
from test_live_v1_position_supervisor import NOW, market_case, observation

from btc_quant_agent.decision.models import CasePackageV1
from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor import PositionSupervisor
from btc_quant_agent.position_supervisor.supervisor import position_case_from_event


def _worker(path, *, on_fresh=None, on_analyze=None):
    analyzed: list[CasePackageV1] = []
    market_symbols: list[str] = []

    class Analysis:
        async def analyze_case(self, case: CasePackageV1) -> None:
            if on_analyze is not None:
                await on_analyze(case)
            analyzed.append(case)

    def fresh(symbol: str) -> CasePackageV1:
        if on_fresh is not None:
            on_fresh(symbol)
        market_symbols.append(symbol)
        return market_case()

    supervisor = PositionSupervisor(path, analysis_service=Analysis(), fresh_market_case=fresh)
    return supervisor, analyzed, market_symbols


# --- R6-03 Schema-Level Immutability Fences ---


@pytest.mark.parametrize(
    "field",
    [
        "event_hash",
        "symbol",
        "environment",
        "credential_namespace",
        "account_id",
        "position_side",
        "position_authority_key",
    ],
)
def test_schema_triggers_prevent_direct_update_of_events_authority(tmp_path, field: str) -> None:
    path = tmp_path / "live.db"
    worker, _, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]

    with connection(path) as db, pytest.raises(sqlite3.IntegrityError, match=r"(?i)immutable"):
        db.execute(
            f"UPDATE live_position_events SET {field}='corrupted' WHERE event_id=?",
            (event.event_id,),
        )


def test_schema_triggers_prevent_direct_delete_of_events_and_dispatches(tmp_path) -> None:
    path = tmp_path / "live.db"
    worker, _, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]

    with connection(path) as db:
        with pytest.raises(sqlite3.IntegrityError, match=r"(?i)blocked|immutable"):
            db.execute("DELETE FROM live_position_events WHERE event_id=?", (event.event_id,))

        with pytest.raises(sqlite3.IntegrityError, match=r"(?i)blocked|immutable"):
            db.execute("DELETE FROM live_position_case_dispatches WHERE event_id=?", (event.event_id,))


@pytest.mark.parametrize(
    "field",
    [
        "event_id",
        "event_hash",
        "symbol",
    ],
)
def test_schema_triggers_prevent_direct_update_of_dispatch_authority(tmp_path, field: str) -> None:
    path = tmp_path / "live.db"
    worker, _, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]

    with connection(path) as db, pytest.raises(sqlite3.IntegrityError, match=r"(?i)blocked|immutable"):
        db.execute(
            f"UPDATE live_position_case_dispatches SET {field}='corrupted' WHERE event_id=?",
            (event.event_id,),
        )


# --- R6-03 Deterministic Mutation Attacks Across 5 Lifecycle Windows ---


@pytest.mark.parametrize(
    "field",
    [
        "event_hash",
        "symbol",
        "environment",
        "credential_namespace",
        "account_id",
        "position_side",
        "position_authority_key",
    ],
)
def test_mutation_during_fresh_market_fails_closed_without_analysis(tmp_path, field: str) -> None:
    """Window 1: Mutation attempted during fresh_market_case materialization."""
    path = tmp_path / "live.db"

    def mutate_during_fresh(symbol: str) -> None:
        with connection(path) as db:
            # Bypass triggers to simulate low-level / concurrent writer corruption
            db.execute("DROP TRIGGER IF EXISTS trg_live_position_events_immutable_update")
            db.execute("DROP TRIGGER IF EXISTS trg_live_position_dispatches_immutable_authority")
            db.execute(
                f"UPDATE live_position_events SET {field}='corrupted_during_market' WHERE symbol=?",
                (symbol,),
            )

    worker, analyzed, _market_symbols = _worker(path, on_fresh=mutate_during_fresh)
    event = worker.evaluate(observation(), NOW)[0]

    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    dispatch = worker.get_dispatch(event.event_id)
    assert dispatch["state"] == "FAILED_CLOSED"
    assert analyzed == []


@pytest.mark.parametrize(
    "field",
    [
        "event_hash",
        "symbol",
        "environment",
        "credential_namespace",
        "account_id",
        "position_side",
        "position_authority_key",
    ],
)
def test_mutation_after_case_freeze_fails_closed(tmp_path, field: str) -> None:
    """Window 2 & 3: Mutation attempted after case freeze and before analysis."""
    path = tmp_path / "live.db"
    worker, analyzed, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]

    # Pre-freeze valid case
    frozen = position_case_from_event(market_case(), event)
    with connection(path) as db:
        db.execute(
            "UPDATE live_position_case_dispatches SET position_case_id=?, position_case_hash=?, "
            "position_case_json=?, case_hash=? WHERE event_id=?",
            (frozen.case_id, frozen.case_hash, frozen.canonical_json(), frozen.case_hash, event.event_id),
        )
        db.execute("DROP TRIGGER IF EXISTS trg_live_position_events_immutable_update")
        db.execute(
            f"UPDATE live_position_events SET {field}='corrupted_after_freeze' WHERE event_id=?",
            (event.event_id,),
        )

    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    dispatch = worker.get_dispatch(event.event_id)
    assert dispatch["state"] == "FAILED_CLOSED"
    assert analyzed == []


@pytest.mark.parametrize(
    "field",
    [
        "event_hash",
        "symbol",
        "environment",
        "credential_namespace",
        "account_id",
        "position_side",
        "position_authority_key",
    ],
)
def test_mutation_during_analysis_fails_closed_before_done(tmp_path, field: str) -> None:
    """Window 4 & 5: Mutation attempted during analysis call before DONE transition."""
    path = tmp_path / "live.db"

    async def mutate_during_analysis(_case: CasePackageV1) -> None:
        with connection(path) as db:
            db.execute("DROP TRIGGER IF EXISTS trg_live_position_events_immutable_update")
            db.execute("DROP TRIGGER IF EXISTS trg_live_position_dispatches_immutable_authority")
            db.execute(
                f"UPDATE live_position_events SET {field}='corrupted_during_analysis' WHERE event_id=?",
                (event.event_id,),
            )

    worker, _analyzed, _ = _worker(path, on_analyze=mutate_during_analysis)
    event = worker.evaluate(observation(), NOW)[0]

    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    dispatch = worker.get_dispatch(event.event_id)
    # The post-analysis boundary check detects the corruption and marks FAILED_CLOSED
    assert dispatch["state"] == "FAILED_CLOSED"


# --- R6-03 Lifecycle and Concurrency Guarantees ---


def test_static_corruption_before_claim_fails_closed(tmp_path) -> None:
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]

    with connection(path) as db:
        db.execute("DROP TRIGGER IF EXISTS trg_live_position_events_immutable_update")
        db.execute("UPDATE live_position_events SET event_hash='corrupt_hash' WHERE event_id=?", (event.event_id,))

    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert worker.get_dispatch(event.event_id)["state"] == "FAILED_CLOSED"
    assert analyzed == market_symbols == []


def test_valid_frozen_retry_stays_exactly_once(tmp_path) -> None:
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]

    # Pre-freeze a case as if prior worker froze it
    frozen = position_case_from_event(market_case(), event)
    with connection(path) as db:
        db.execute(
            "UPDATE live_position_case_dispatches SET position_case_id=?, position_case_hash=?, "
            "position_case_json=?, case_hash=? WHERE event_id=?",
            (frozen.case_id, frozen.case_hash, frozen.canonical_json(), frozen.case_hash, event.event_id),
        )

    # Draining now should NOT invoke fresh_market_case again
    completed = asyncio.run(worker.drain_pending_dispatches(NOW))
    assert len(completed) == 1
    assert completed[0].event_id == event.event_id
    assert market_symbols == []  # Fresh market case was NOT called because already frozen!
    assert len(analyzed) == 1
    assert worker.get_dispatch(event.event_id)["state"] == "DONE"

    # Second drain does nothing (stays exactly once)
    assert asyncio.run(worker.drain_pending_dispatches(NOW + 1000)) == ()
    assert len(analyzed) == 1


def test_expired_stale_worker_cannot_complete_done(tmp_path) -> None:
    """Stale worker whose lease was superseded cannot commit DONE transition."""
    path = tmp_path / "live.db"
    worker, _analyzed, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]

    # Worker 1 claims but its lease expires
    with connection(path) as db:
        db.execute(
            "UPDATE live_position_case_dispatches SET state='DISPATCHING', lease_token='worker-1', "
            "lease_expires_at_ms=? WHERE event_id=?",
            (NOW - 1000, event.event_id),  # Expired lease
        )

    # Worker 2 claims the expired lease and completes
    completed = asyncio.run(worker.drain_pending_dispatches(NOW))
    assert len(completed) == 1
    assert worker.get_dispatch(event.event_id)["state"] == "DONE"

    # Attempting to commit DONE using the stale worker-1 lease updates 0 rows
    with connection(path) as db:
        stale_update = db.execute(
            "UPDATE live_position_case_dispatches SET state='DONE' "
            "WHERE event_id=? AND lease_token='worker-1'",
            (event.event_id,),
        )
        assert stale_update.rowcount == 0


def test_normal_valid_dispatch_reaches_done_exactly_once(tmp_path) -> None:
    path = tmp_path / "live.db"
    worker, analyzed, market_symbols = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]

    completed = asyncio.run(worker.drain_pending_dispatches(NOW))
    assert len(completed) == 1
    assert completed[0].event_id == event.event_id
    assert len(analyzed) == 1
    assert market_symbols == [event.symbol]
    assert worker.get_dispatch(event.event_id)["state"] == "DONE"

    # Subsequent drain does nothing
    assert asyncio.run(worker.drain_pending_dispatches(NOW + 1000)) == ()
    assert len(analyzed) == 1
