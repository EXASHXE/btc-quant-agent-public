"""FULL-sync SQLite reservation, immutable hash chain and exact durable frame charging."""

from __future__ import annotations

import base64
import os
from pathlib import Path
import shutil
import sqlite3
from contextlib import contextmanager

from .contract import canonical, digest, require, strict


class Journal:
    def __init__(self, path, fault=None):
        self.path = Path(path).absolute()
        require(not any(p.is_symlink() for p in (self.path, *self.path.parents)), "JOURNAL_SYMLINK")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fault = fault or (lambda phase: None)
        with self.db() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, output TEXT UNIQUE, grant_hash TEXT UNIQUE,
                grant_json BLOB NOT NULL, status TEXT NOT NULL, requests INTEGER DEFAULT 0,
                incoming INTEGER DEFAULT 0, outgoing INTEGER DEFAULT 0, charged_bytes INTEGER DEFAULT 0);
              CREATE UNIQUE INDEX IF NOT EXISTS one_active ON sessions((1)) WHERE status='RESERVED';
              CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, session TEXT NOT NULL, kind TEXT NOT NULL,
                body BLOB NOT NULL, previous TEXT NOT NULL, hash TEXT UNIQUE NOT NULL);
              CREATE TABLE IF NOT EXISTS frames(id INTEGER PRIMARY KEY, session TEXT NOT NULL, raw BLOB NOT NULL,
                received_ms INTEGER NOT NULL, event_hash TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS receipts(frame INTEGER PRIMARY KEY, value BLOB NOT NULL);
              CREATE TRIGGER IF NOT EXISTS immutable_receipts_u BEFORE UPDATE ON receipts BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_receipts_d BEFORE DELETE ON receipts BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
              CREATE TABLE IF NOT EXISTS settlements(frame INTEGER PRIMARY KEY, state TEXT NOT NULL, value BLOB NOT NULL);
              CREATE TRIGGER IF NOT EXISTS immutable_events_u BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_events_d BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_frames_u BEFORE UPDATE ON frames BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_frames_d BEFORE DELETE ON frames BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_settle_u BEFORE UPDATE ON settlements BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
              CREATE TRIGGER IF NOT EXISTS immutable_settle_d BEFORE DELETE ON settlements BEGIN SELECT RAISE(ABORT,'IMMUTABLE'); END;
            """)
        self.sync_parent()

    def sync_parent(self):
        if hasattr(os, "O_DIRECTORY"):
            fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA journal_mode=DELETE")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            self.fault("before_commit")
            db.commit()
            self.fault("after_commit")
        finally:
            db.close()

    def append(self, db, session, kind, value):
        previous = db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        previous = previous[0] if previous else "0" * 64
        raw = canonical(value)
        identity = digest([session, kind, previous, value])
        db.execute(
            "INSERT INTO events(session,kind,body,previous,hash) VALUES(?,?,?,?,?)",
            (session, kind, raw, previous, identity),
        )
        return identity

    def reserve(self, grant):
        self.fault("before_reservation")
        self.check_space(grant, 131072)
        with self.db() as db:
            db.execute(
                "INSERT INTO sessions(id,output,grant_hash,grant_json,status) VALUES(?,?,?,?,?)",
                (
                    grant.session_id,
                    grant.output,
                    digest(grant.model_dump(mode="json")),
                    canonical(grant.model_dump(mode="json")),
                    "RESERVED",
                ),
            )
            self.append(db, grant.session_id, "RESERVED_CONSUMED", grant.model_dump(mode="json"))
        self.sync_parent()
        self.fault("after_reservation")
        # Atomic filesystem reservation is intentionally after durable consumption.
        Path(grant.output).mkdir(parents=False, exist_ok=False)
        self.sync_parent()

    def usage(self, session):
        with self.db() as db:
            row = db.execute(
                "SELECT status,requests,incoming,outgoing,charged_bytes FROM sessions WHERE id=?", (session,)
            ).fetchone()
            require(row is not None, "SESSION_MISSING")
            return dict(zip(("status", "requests", "incoming", "outgoing", "charged_bytes"), row))

    def check_space(self, grant, extra):
        actual = self.path.stat().st_size if self.path.exists() else 0
        require(actual + extra + 131072 <= grant.storage_bytes_max, "STORAGE_BUDGET")
        require(shutil.disk_usage(self.path.parent).free >= extra + 262144, "DISK_SPACE")

    def charge(self, grant, field, limit, value):
        require(field in {"requests", "outgoing"}, "BUDGET_FIELD")
        self.check_space(grant, len(canonical(value)) + 16384)
        with self.db() as db:
            row = db.execute(
                f"SELECT status,{field} FROM sessions WHERE id=?", (grant.session_id,)
            ).fetchone()
            charged = db.execute(
                "SELECT count(*) FROM events WHERE session=? AND kind=?", (grant.session_id, field.upper())
            ).fetchone()[0]
            require(row and charged == row[1], "DURABLE_BUDGET_ACCOUNTING_TAMPER")
            require(row and row[0] == "RESERVED" and row[1] < limit, "BUDGET_EXHAUSTED:" + field)
            db.execute(f"UPDATE sessions SET {field}={field}+1 WHERE id=?", (grant.session_id,))
            self.append(db, grant.session_id, field.upper(), value)

    def receive(self, grant, raw, received_ms, queue_depth):
        require(queue_depth < 128, "QUEUE128_HARD_STOP")
        require(queue_depth < 96, "QUEUE96_HIGH_WATER_STOP")
        self.check_space(grant, len(raw) * 3 + 16384)
        self.fault("before_frame_write")
        with self.db() as db:
            row = db.execute(
                "SELECT incoming FROM sessions WHERE id=? AND status='RESERVED'", (grant.session_id,)
            ).fetchone()
            require(row and row[0] < grant.messages_max, "BUDGET_EXHAUSTED:incoming")
            body = {
                "raw_b64": base64.b64encode(raw).decode(),
                "received_ms": received_ms,
                "queue_before": queue_depth,
            }
            identity = self.append(db, grant.session_id, "FRAME_ADMITTED", body)
            cursor = db.execute(
                "INSERT INTO frames(session,raw,received_ms,event_hash) VALUES(?,?,?,?)",
                (grant.session_id, raw, received_ms, identity),
            )
            db.execute(
                "UPDATE sessions SET incoming=incoming+1,charged_bytes=charged_bytes+? WHERE id=?",
                (len(raw), grant.session_id),
            )
            frame_id = cursor.lastrowid
        self.fault("after_frame_write")
        return frame_id

    def settle(self, grant, frame, state, value):
        self.check_space(grant, len(canonical(value)) * 2 + 16384)
        with self.db() as db:
            db.execute(
                "INSERT INTO settlements(frame,state,value) VALUES(?,?,?)", (frame, state, canonical(value))
            )
            self.append(db, grant.session_id, "SETTLED", {"frame": frame, "state": state, "value": value})

    def finalize_receipt(self, grant, frame, value):
        self.check_space(grant, len(canonical(value)) * 2 + 16384)
        with self.db() as db:
            db.execute("INSERT INTO receipts(frame,value) VALUES(?,?)", (frame, canonical(value)))
            self.append(db, grant.session_id, "NORMALIZED_DURABLE_ACK", {"frame": frame, "value": value})

    def terminal(self, grant, reason, transport_closed):
        with self.db() as db:
            pending = db.execute(
                "SELECT count(*) FROM frames f LEFT JOIN settlements s ON s.frame=f.id "
                "WHERE f.session=? AND (s.frame IS NULL OR (s.state='PREPARED' AND NOT EXISTS(SELECT 1 FROM receipts r WHERE r.frame=f.id)))",
                (grant.session_id,),
            ).fetchone()[0]
            report = {
                "session_id": grant.session_id,
                "reason": reason,
                "transport_closed": transport_closed,
                "unsettled_frames": pending,
                "source_qualified": False,
                "economic_validation": False,
            }
            self.append(db, grant.session_id, "TERMINAL", report)
            db.execute(
                "UPDATE sessions SET status=? WHERE id=?",
                ("CLOSED" if transport_closed and not pending else "FAILED_CLOSURE", grant.session_id),
            )
        return report

    def recover(self):
        # Mark a dead capture as failed. Never reconnect or reuse its grant/output.
        with self.db() as db:
            for (session,) in db.execute("SELECT id FROM sessions WHERE status='RESERVED'").fetchall():
                self.append(db, session, "CRASH_RECOVERY_NO_RESTART", {})
                db.execute("UPDATE sessions SET status='CRASHED' WHERE id=?", (session,))
        return self.verify()

    def verify(self):
        with self.db() as db:
            previous = "0" * 64
            count = 0
            for session, kind, body, predecessor, identity in db.execute(
                "SELECT session,kind,body,previous,hash FROM events ORDER BY seq"
            ):
                require(
                    predecessor == previous and digest([session, kind, previous, strict(body)]) == identity,
                    "JOURNAL_CHAIN_TAMPER",
                )
                previous = identity
                count += 1
            for raw, received, identity, body in db.execute(
                "SELECT f.raw,f.received_ms,f.event_hash,e.body FROM frames f JOIN events e ON e.hash=f.event_hash"
            ):
                record = strict(body)
                require(
                    base64.b64decode(record["raw_b64"]) == raw and record["received_ms"] == received,
                    "RAW_FRAME_BINDING_TAMPER",
                )
            for session, incoming, charged in db.execute("SELECT id,incoming,charged_bytes FROM sessions"):
                actual = db.execute(
                    "SELECT count(*),coalesce(sum(length(raw)),0) FROM frames WHERE session=?", (session,)
                ).fetchone()
                require(actual == (incoming, charged), "DURABLE_ACCOUNTING_TAMPER")
            receipt_links = {
                x["frame"]: x["value"]
                for x in (
                    strict(b)
                    for (b,) in db.execute("SELECT body FROM events WHERE kind='NORMALIZED_DURABLE_ACK'")
                )
            }
            settle_links = {
                x["frame"]: (x["state"], x["value"])
                for x in (strict(b) for (b,) in db.execute("SELECT body FROM events WHERE kind='SETTLED'"))
            }
            receipt_rows = db.execute("SELECT frame,value FROM receipts").fetchall()
            settlement_rows = db.execute("SELECT frame,state,value FROM settlements").fetchall()
            require(
                len(receipt_rows) == len(receipt_links) and len(settlement_rows) == len(settle_links),
                "MATERIALIZED_ROW_MISSING",
            )
            for frame, value in receipt_rows:
                require(
                    frame in receipt_links and canonical(receipt_links[frame]) == value,
                    "NORMALIZED_RECEIPT_TAMPER",
                )
            for frame, state, value in settlement_rows:
                require(
                    frame in settle_links
                    and settle_links[frame][0] == state
                    and canonical(settle_links[frame][1]) == value,
                    "SETTLEMENT_TAMPER",
                )
            return {
                "events": count,
                "head": previous,
                "frames": db.execute("SELECT count(*) FROM frames").fetchone()[0],
            }

    def initial_seen(self, exposure, now_ms):
        self.verify()
        with self.db() as db:
            for (raw,) in db.execute("SELECT grant_json FROM sessions"):
                g = strict(raw)
                require(g["exposure"] == exposure, "MIXED_EXPOSURE_JOURNAL_FORBIDDEN")
                require(
                    now_ms <= g["end_ms"] + g["retention_seconds"] * 1000,
                    "RETENTION_EXPIRY_REQUIRES_OWNER_PURGE",
                )
            values = [strict(raw) for (raw,) in db.execute("SELECT value FROM receipts ORDER BY frame")]
        seen: dict[str, str] = {}
        for value in values:
            r = value["record"]
            semantic = digest(
                [
                    r["symbol"],
                    r["interval"],
                    r["open_time_ms"],
                    r["end_time_ms"],
                    r["open"],
                    r["high"],
                    r["low"],
                    r["close"],
                    r["volume"],
                ]
            )
            require(
                value["identity"] not in seen or seen[value["identity"]] == semantic,
                "HISTORICAL_CORRECTION_UNRESOLVED",
            )
            seen[value["identity"]] = semantic
        return seen

    def records(self, session):
        self.verify()
        with self.db() as db:
            return [
                strict(value)
                for (value,) in db.execute(
                    "SELECT r.value FROM frames f JOIN receipts r ON r.frame=f.id WHERE f.session=? ORDER BY f.id",
                    (session,),
                )
            ]
