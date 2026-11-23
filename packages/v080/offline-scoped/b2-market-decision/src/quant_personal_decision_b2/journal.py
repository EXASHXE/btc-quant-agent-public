"""Append-only, transactionally published local B2 decision and operator journal."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .model import DecisionError, Policy, check, digest, encode, integer

APP_ID = 0x51423244
SCHEMA = (
    "CREATE TABLE identity (policy TEXT NOT NULL)",
    """CREATE TABLE episodes (
        id TEXT PRIMARY KEY, symbol TEXT NOT NULL, group_id TEXT NOT NULL UNIQUE, immutable TEXT NOT NULL,
        payload_sha TEXT NOT NULL
    )""",
    """CREATE TABLE cards (
        id TEXT PRIMARY KEY, symbol TEXT NOT NULL, as_of INTEGER NOT NULL, lineage TEXT,
        episode_id TEXT REFERENCES episodes(id), structural_state TEXT, payload TEXT NOT NULL, payload_sha TEXT NOT NULL,
        UNIQUE(symbol,as_of)
    )""",
    "CREATE INDEX episode_cards ON cards(episode_id,as_of DESC)",
    """CREATE TABLE events (
        seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, card_id TEXT NOT NULL REFERENCES cards(id),
        episode_id TEXT REFERENCES episodes(id), kind TEXT NOT NULL, evidence TEXT NOT NULL, payload TEXT NOT NULL,
        prior_sha TEXT, sha TEXT NOT NULL
    )""",
)
MANUAL_ACTIONS = {"WATCH", "SKIP", "INTENDED_ACTION", "NOTE"}


class Journal:
    def __init__(self, path: Path, *, create: bool = False, policy: Policy | None = None) -> None:
        self.path = path.resolve()
        with self.connect(write=create) as db:
            app = db.execute("PRAGMA application_id").fetchone()[0]
            if create and app == 0:
                check(policy is not None, "JOURNAL_POLICY_REQUIRED")
                check(not db.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone(), "JOURNAL_WRONG_SCHEMA")
                for statement in SCHEMA:
                    db.execute(statement)
                for table in ("identity", "episodes", "cards", "events"):
                    for op in ("UPDATE", "DELETE"):
                        db.execute(f"CREATE TRIGGER lock_{table}_{op} BEFORE {op} ON {table} "
                                   "BEGIN SELECT RAISE(ABORT,'B2_APPEND_ONLY'); END")
                db.execute(f"PRAGMA application_id={APP_ID}")
                db.execute("PRAGMA user_version=1")
                assert policy is not None
                db.execute("INSERT INTO identity VALUES (?)", (encode(policy.data()),))
                app = APP_ID
            check(app == APP_ID and db.execute("PRAGMA user_version").fetchone()[0] == 1, "JOURNAL_WRONG_SCHEMA")
            configs = db.execute("SELECT policy FROM identity").fetchall()
            check(len(configs) == 1 and (policy is None or configs[0][0] == encode(policy.data())),
                  "JOURNAL_POLICY_CONFLICT")
            self.policy_json = str(configs[0][0])

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        target = str(self.path) if write else self.path.as_uri() + "?mode=ro"
        with contextmanager_connection(target, write) as connection:
            yield connection

    @staticmethod
    def unpack(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = json.loads(row["payload"])
        check(digest(data) == row["payload_sha"], "JOURNAL_CARD_DIGEST")
        return data

    @staticmethod
    def episode(db: sqlite3.Connection, ident: str) -> dict[str, Any]:
        row = db.execute("SELECT immutable,payload_sha FROM episodes WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise DecisionError("EPISODE_UNKNOWN")
        value = json.loads(row["immutable"])
        check(digest(value) == row["payload_sha"], "JOURNAL_EPISODE_DIGEST")
        return value

    @staticmethod
    def add_episode(db: sqlite3.Connection, episode: dict[str, Any]) -> None:
        data = encode(episode)
        db.execute("INSERT INTO episodes VALUES (?,?,?,?,?)",
                   (episode["episode_id"], episode["symbol"], episode["group_id"], data, digest(episode)))

    @staticmethod
    def add_event(db: sqlite3.Connection, kind: str, card: dict[str, Any], detail: dict[str, Any], *,
                  identity: str | None = None, evidence: str = "SYNTHETIC_QA_ONLY") -> None:
        prior = db.execute("SELECT sha FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        prev = prior["sha"] if prior else None
        ident = identity or digest([card["card_id"], kind])
        full = {"id": ident, "kind": kind, "card_id": card["card_id"], "episode_id": card["episode_id"],
                "evidence": evidence, "detail": detail, "prior_sha": prev}
        db.execute("INSERT INTO events(event_id,card_id,episode_id,kind,evidence,payload,prior_sha,sha) "
                   "VALUES (?,?,?,?,?,?,?,?)", (ident, card["card_id"], card["episode_id"], kind, evidence,
                                                encode(detail), prev, digest(full)))

    def publish(self, db: sqlite3.Connection, card: dict[str, Any],
                events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
        payload = encode(card)
        receipt = card["evaluation_receipt"] or {}
        db.execute("INSERT INTO cards VALUES (?,?,?,?,?,?,?,?)",
                   (card["card_id"], card["symbol"], card["evaluated_ms"], receipt.get("source_lineage"),
                    card["episode_id"], card["episode_state"], payload, digest(card)))
        for kind, detail in events:
            self.add_event(db, kind, card, detail)
        return json.loads(payload)

    def read(self, *, card_id: str | None = None, episode_id: str | None = None,
             as_of_ms: int | None = None) -> dict[str, Any] | None:
        clauses, args = [], []
        for column, op, value in (("id", "=", card_id), ("episode_id", "=", episode_id), ("as_of", "<=", as_of_ms)):
            if value is not None:
                clauses.append(column + op + "?")
                args.append(value)
        sql = "SELECT payload,payload_sha FROM cards" + (" WHERE " + " AND ".join(clauses) if clauses else "")
        with self.connect() as conn:
            row = conn.execute(sql + " ORDER BY as_of DESC,id DESC LIMIT 1", tuple(args)).fetchone()
            return self.unpack(row)

    def manual(self, *, card_id: str, operator_id: str, action: str, time_ms: int, note: str = "") -> dict[str, Any]:
        check(action in MANUAL_ACTIONS and 0 < len(operator_id) <= 120 and len(note) <= 2000, "INVALID_OPERATOR_EVENT")
        integer(time_ms, "owner_reported_venue_ms", minimum=1)
        key = digest(["OWNER_ENTERED", operator_id])
        reported = {"operator_event_id": operator_id, "action": action, "owner_reported_venue_ms": time_ms, "note": note,
                    "exchange_fill_status": "UNKNOWN"}
        with self.connect(write=True) as db:
            card = self.unpack(db.execute("SELECT payload,payload_sha FROM cards WHERE id=?", (card_id,)).fetchone())
            if card is None:
                raise DecisionError("CARD_UNKNOWN")
            check(time_ms >= card["evaluated_ms"], "OPERATOR_EVENT_PREDATES_CARD")
            existing = db.execute("SELECT card_id,payload FROM events WHERE event_id=?", (key,)).fetchone()
            if existing:
                result = json.loads(existing["payload"])
                check(existing["card_id"] == card_id and all(result[k] == v for k, v in reported.items()),
                      "OPERATOR_IDEMPOTENCY_CONFLICT")
                return result
            result = {**reported, "recorded_wall_ms": time.time_ns() // 1_000_000, "evidence": "OWNER_ENTERED"}
            self.add_event(db, "MANUAL", card, result, identity=key, evidence="OWNER_ENTERED")
            return result

    def events(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            result = []
            prior = None
            for row in db.execute("SELECT * FROM events ORDER BY seq"):
                content = {key: row[key] for key in ("kind", "card_id", "episode_id", "evidence", "prior_sha")}
                content.update(id=row["event_id"], detail=json.loads(row["payload"]))
                check(row["prior_sha"] == prior and digest(content) == row["sha"], "JOURNAL_EVENT_DIGEST")
                prior = row["sha"]
                result.append({**content, "sha256": prior, "sequence": row["seq"]})
            return result


@contextmanager
def contextmanager_connection(path: str, write: bool) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path, uri=not write, timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        if write:
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if write:
            conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
