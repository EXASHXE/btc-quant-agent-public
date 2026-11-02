"""R8 SQL completion fabrication seal regressions."""

from __future__ import annotations

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_live_v1_position_outbox_r7 import _worker
from test_live_v1_position_supervisor import NOW, observation

from btc_quant_agent.live_db import connection
from btc_quant_agent.position_supervisor import PositionSupervisor

TABLE = "live_position_case_dispatches"
BLANK = {
    "event_id": "synthetic-event", "event_hash": "synthetic-hash",
    "symbol": "BTCUSDT", "state": "PENDING", "created_at_ms": NOW,
    "updated_at_ms": NOW,
}
PROTECTED = (
    "dispatch_authority_json", "dispatch_authority_hash", "analysis_admission_hash",
    "position_case_id", "position_case_hash", "position_case_json", "case_hash",
)


def _insert(db, values, verb="INSERT INTO"):
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    return db.execute(f"{verb} {TABLE} ({columns}) VALUES ({placeholders})", tuple(values.values()))


def _row(path, event_id):
    with connection(path) as db:
        row = db.execute(f"SELECT * FROM {TABLE} WHERE event_id=?", (event_id,)).fetchone()
        return None if row is None else dict(row)


@pytest.mark.parametrize("change", [
    {"state": "DONE", "analysis_completed": 1},
    {"state": "PENDING", "analysis_completed": 1},
    {"state": "DONE"},
    *[{field: "prepopulated"} for field in PROTECTED],
    {"lease_token": "prepopulated"},
    {"lease_expires_at_ms": NOW + 1000},
])
def test_insert_requires_blank_pending_authority(tmp_path, change):
    path = tmp_path / "live.db"
    PositionSupervisor(path)
    with pytest.raises(sqlite3.IntegrityError), connection(path) as db:
        _insert(db, {**BLANK, **change})
    assert _row(path, BLANK["event_id"]) is None


def test_normal_pending_insert_and_connection_durability(tmp_path):
    path = tmp_path / "live.db"
    PositionSupervisor(path)
    with connection(path) as db:
        assert db.execute("PRAGMA recursive_triggers").fetchone()[0] == 1
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        _insert(db, BLANK)
    row = _row(path, BLANK["event_id"])
    assert row["state"] == "PENDING" and row["analysis_completed"] == 0
    assert all(row[field] == "" for field in PROTECTED)


@pytest.mark.parametrize("verb", ["INSERT OR REPLACE INTO", "REPLACE INTO"])
@pytest.mark.parametrize("receipt", ["frozen", "admitted", "completed"])
@pytest.mark.parametrize("replacement", ["blank", "fabricated"])
def test_replace_cannot_erase_authority_row(tmp_path, verb, receipt, replacement):
    path = tmp_path / "live.db"
    async def provider_failure(_case):
        raise RuntimeError("provider completion unknown")

    worker, _, _ = _worker(path, on_analysis=provider_failure if receipt == "admitted" else None)
    event = worker.evaluate(observation(), NOW)[0]
    if receipt == "completed":
        assert len(asyncio.run(worker.drain_pending_dispatches(NOW))) == 1
    elif receipt == "admitted":
        assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
        assert _row(path, event.event_id)["analysis_admission_hash"]
        assert _row(path, event.event_id)["analysis_completed"] == 0
    else:
        with connection(path) as db:
            db.execute(f"UPDATE {TABLE} SET position_case_id='frozen' WHERE event_id=?", (event.event_id,))
    original = _row(path, event.event_id)
    values = {**BLANK, "event_id": event.event_id, "event_hash": event.event_hash}
    if replacement == "fabricated":
        values.update(state="DONE", analysis_completed=1)
    with pytest.raises(sqlite3.IntegrityError), connection(path) as db:
        _insert(db, values, verb)
    assert _row(path, event.event_id) == original


@pytest.mark.parametrize("operation", [
    "UPDATE live_position_case_dispatches SET dispatch_authority_hash='changed' WHERE event_id=?",
    "DELETE FROM live_position_case_dispatches WHERE event_id=?",
    "INSERT INTO live_position_case_dispatches (event_id,event_hash,symbol,state,created_at_ms,updated_at_ms) VALUES (?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET dispatch_authority_hash='changed'",
])
def test_updates_deletes_and_upserts_cannot_fabricate_completed_receipt(tmp_path, operation):
    path = tmp_path / "live.db"
    worker, _, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    assert len(asyncio.run(worker.drain_pending_dispatches(NOW))) == 1
    original = _row(path, event.event_id)
    params = ((event.event_id, "upsert-attempt-hash", event.symbol, "PENDING", NOW, NOW)
              if "INSERT INTO" in operation else (event.event_id,))
    with pytest.raises(sqlite3.DatabaseError), connection(path) as db:
        db.execute(operation, params)
    assert _row(path, event.event_id) == original


@pytest.mark.parametrize("state", ["PENDING", "DISPATCHING"])
@pytest.mark.parametrize("operation", ["UPDATE", "UPSERT"])
def test_completion_update_and_upsert_rejected_before_provider(tmp_path, state, operation):
    path = tmp_path / "live.db"
    worker, _, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    if state == "DISPATCHING":
        with connection(path) as db:
            db.execute(f"UPDATE {TABLE} SET state='DISPATCHING', lease_token='worker', "
                       "lease_expires_at_ms=? WHERE event_id=?", (NOW + 1000, event.event_id))
    original = _row(path, event.event_id)
    with pytest.raises(sqlite3.DatabaseError), connection(path) as db:
        if operation == "UPDATE":
            db.execute(f"UPDATE {TABLE} SET state='DONE', analysis_completed=1 WHERE event_id=?",
                       (event.event_id,))
        else:
            db.execute(f"INSERT INTO {TABLE} "
                       "(event_id,event_hash,symbol,state,created_at_ms,updated_at_ms) "
                       "VALUES (?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET "
                       "state='DONE', analysis_completed=1",
                       (event.event_id, "upsert-attempt-hash", event.symbol, "PENDING", NOW, NOW))
    assert _row(path, event.event_id) == original


def test_existing_r7_admission_trigger_receives_state_only_done_guard(tmp_path):
    path = tmp_path / "live.db"
    worker, _, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    with connection(path) as db:
        db.execute("DROP TRIGGER trg_live_position_dispatch_admission_immutable")
        db.execute("DROP TRIGGER trg_live_position_dispatch_blank_insert")
        db.execute("DROP TRIGGER IF EXISTS trg_live_position_dispatch_done_requires_completion")
        db.execute("""
            CREATE TRIGGER trg_live_position_dispatch_admission_immutable
            BEFORE UPDATE ON live_position_case_dispatches
            FOR EACH ROW
            BEGIN
                SELECT RAISE(ABORT, 'DISPATCH_ADMISSION_IMMUTABLE')
                WHERE (OLD.analysis_admission_hash != '' OR OLD.dispatch_authority_hash != '')
                  AND (OLD.dispatch_authority_json IS NOT NEW.dispatch_authority_json
                    OR OLD.dispatch_authority_hash IS NOT NEW.dispatch_authority_hash
                    OR OLD.analysis_admission_hash IS NOT NEW.analysis_admission_hash
                    OR OLD.position_case_id IS NOT NEW.position_case_id
                    OR OLD.position_case_hash IS NOT NEW.position_case_hash
                    OR OLD.position_case_json IS NOT NEW.position_case_json
                    OR OLD.case_hash IS NOT NEW.case_hash);
                SELECT RAISE(ABORT, 'ANALYSIS_COMPLETION_IMMUTABLE')
                WHERE OLD.analysis_completed = 1 AND NEW.analysis_completed IS NOT 1;
            END
        """)
        legacy = db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' "
                            "AND name='trg_live_position_dispatch_admission_immutable'").fetchone()[0]
    PositionSupervisor(path)
    with connection(path) as db:
        assert db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' "
                          "AND name='trg_live_position_dispatch_admission_immutable'").fetchone()[0] == legacy
    original = _row(path, event.event_id)
    with pytest.raises(sqlite3.IntegrityError), connection(path) as db:
        db.execute(f"UPDATE {TABLE} SET state='DONE' WHERE event_id=?", (event.event_id,))
    assert _row(path, event.event_id) == original


def test_state_only_done_update_cannot_complete_frozen_pending_row(tmp_path):
    path = tmp_path / "live.db"
    worker, _, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    with connection(path) as db:
        db.execute(f"UPDATE {TABLE} SET position_case_id='frozen' WHERE event_id=?", (event.event_id,))
    original = _row(path, event.event_id)
    with pytest.raises(sqlite3.IntegrityError), connection(path) as db:
        db.execute(f"UPDATE {TABLE} SET state='DONE' WHERE event_id=?", (event.event_id,))
    assert _row(path, event.event_id) == original


def test_legitimate_completion_once_and_recovery_unchanged(tmp_path):
    path = tmp_path / "live.db"
    worker, calls, _ = _worker(path)
    event = worker.evaluate(observation(), NOW)[0]
    assert len(asyncio.run(worker.drain_pending_dispatches(NOW))) == 1
    completed = _row(path, event.event_id)
    assert completed["state"] == "DONE" and completed["analysis_completed"] == 1
    assert len(calls) == 1
    restarted, replay_calls, _ = _worker(path)
    assert asyncio.run(restarted.drain_pending_dispatches(NOW + 1)) == ()
    assert replay_calls == []
    assert _row(path, event.event_id) == completed


def test_terminal_abort_rolls_back_done_and_marker(tmp_path):
    path = tmp_path / "live.db"

    async def abort(_case):
        with connection(path) as db:
            db.execute(f"""CREATE TRIGGER abort_r8_terminal AFTER UPDATE ON {TABLE}
                FOR EACH ROW WHEN NEW.state='DONE' AND NEW.analysis_completed=1
                BEGIN SELECT RAISE(ABORT, 'R8_TERMINAL_ABORT'); END""")

    worker, calls, _ = _worker(path, on_analysis=abort)
    event = worker.evaluate(observation(), NOW)[0]
    assert asyncio.run(worker.drain_pending_dispatches(NOW)) == ()
    assert len(calls) == 1
    receipt = _row(path, event.event_id)
    assert receipt["state"] == "FAILED_CLOSED" and receipt["analysis_completed"] == 0


def test_connections_after_concurrent_constructors_enable_recursive_triggers(tmp_path):
    path = tmp_path / "live.db"
    PositionSupervisor(path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: PositionSupervisor(path), range(8)))
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: _recursive_setting(path), range(8)))
    assert values == [1] * 8


def _recursive_setting(path):
    with connection(path) as db:
        return db.execute("PRAGMA recursive_triggers").fetchone()[0]


def test_connection_fails_closed_if_recursive_triggers_cannot_be_enabled(tmp_path, monkeypatch):
    from btc_quant_agent import live_db

    original_connect = live_db.sqlite3.connect

    class RefusingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=(), /):
            if sql == "PRAGMA recursive_triggers=ON":
                return super().execute("PRAGMA recursive_triggers=OFF")
            return super().execute(sql, parameters)

    def refusing_connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=RefusingConnection)

    monkeypatch.setattr(live_db.sqlite3, "connect", refusing_connect)
    with pytest.raises(RuntimeError, match="LIVE_RECURSIVE_TRIGGERS_REQUIRED"), connection(tmp_path / "live.db"):
        pytest.fail("connection yielded without recursive triggers")
