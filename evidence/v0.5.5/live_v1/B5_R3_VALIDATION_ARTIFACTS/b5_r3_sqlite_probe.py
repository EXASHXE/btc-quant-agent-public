import sqlite3
from tempfile import TemporaryDirectory
from pathlib import Path
from btc_quant_agent.live_db import connection

with TemporaryDirectory() as d:
    path = Path(d) / 'nested' / 'live.db'
    with connection(path) as db:
        settings = {key: db.execute('PRAGMA ' + key).fetchone()[0] for key in ('journal_mode','synchronous','foreign_keys','busy_timeout')}
        db.execute('CREATE TABLE parent(id INTEGER PRIMARY KEY)')
        db.execute('CREATE TABLE child(id INTEGER PRIMARY KEY,parent_id INTEGER NOT NULL REFERENCES parent(id))')
        db.execute('CREATE TABLE writes(id INTEGER PRIMARY KEY)')
    try:
        with connection(path) as db:
            db.execute('INSERT INTO writes VALUES (1)')
            db.execute('INSERT INTO child VALUES (1,999)')
    except sqlite3.IntegrityError:
        pass
    with connection(path) as db:
        rollback_rows = db.execute('SELECT COUNT(*) FROM writes').fetchone()[0]
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT INTO writes VALUES (2)')
        try:
            with connection(path,busy_timeout_ms=30) as contender:
                contender.execute('BEGIN IMMEDIATE')
                contender.execute('INSERT INTO writes VALUES (3)')
        except sqlite3.OperationalError as e:
            locked = 'locked' in str(e)
        else:
            locked = False
    with connection(path) as db:
        final = [r[0] for r in db.execute('SELECT id FROM writes ORDER BY id')]
    print({'settings':settings,'rollback_rows':rollback_rows,'bounded_lock_rejected':locked,'committed_rows':final})
