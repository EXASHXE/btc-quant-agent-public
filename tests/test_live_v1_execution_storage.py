import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_live_v1_decision_models import sample_case

from btc_quant_agent.approval.store import LiveStore
from btc_quant_agent.live_db import connection


def test_live_stores_use_wal_and_concurrent_writers_survive_restart(tmp_path):
    path = tmp_path / 'nested' / 'live.db'
    store = LiveStore(path)
    store.save_case(sample_case())
    with connection(path) as db:
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        assert db.execute('PRAGMA foreign_keys').fetchone()[0] == 1
        db.execute('CREATE TABLE concurrent_events (id INTEGER PRIMARY KEY)')

    def writer(worker):
        for item in range(15):
            with connection(path) as db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('INSERT INTO concurrent_events VALUES (?)', (worker * 15 + item,))

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(writer, range(6)))
    restarted = LiveStore(path)
    assert restarted.get_case(sample_case().case_id) == sample_case()
    with connection(path) as db:
        assert db.execute('SELECT COUNT(*) FROM concurrent_events').fetchone()[0] == 90


def test_busy_timeout_does_not_commit_partial_work_and_restart_recovers(tmp_path):
    path = tmp_path / 'live.db'
    with connection(path) as db:
        db.execute('CREATE TABLE busy_events (id INTEGER PRIMARY KEY)')
    with connection(path) as locked:
        locked.execute('BEGIN IMMEDIATE')
        locked.execute('INSERT INTO busy_events VALUES (1)')
        with (
            pytest.raises(sqlite3.OperationalError, match='locked'),
            connection(path, busy_timeout_ms=25) as contender,
        ):
            contender.execute('BEGIN IMMEDIATE')
            contender.execute('INSERT INTO busy_events VALUES (2)')
    with connection(path) as restarted:
        assert restarted.execute('SELECT id FROM busy_events').fetchall()[0][0] == 1
        restarted.execute('INSERT INTO busy_events VALUES (2)')
    with connection(path) as db:
        assert db.execute('SELECT COUNT(*) FROM busy_events').fetchone()[0] == 2
