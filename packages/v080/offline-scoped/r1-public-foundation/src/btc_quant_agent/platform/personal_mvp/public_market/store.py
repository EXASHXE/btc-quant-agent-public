"""Local transactional cache for PERSONAL_PUBLIC_MARKET fixture evidence."""

import base64
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Mapping

from .adapter import Params
from .clock import Sample
from .policy import SourceBlocked, require

APPLICATION_ID = 0x5231504D  # R1PM
SCHEMA_VERSION = 1
EVIDENCE_CLASS = "PERSONAL_PUBLIC_MARKET"
FIXTURE_CLASS = "DETERMINISTIC_OFFLINE_FIXTURE"
SNAPSHOT_SCHEMA = "PERSONAL_PUBLIC_MARKET_SNAPSHOT_V1"

SCHEMA = (
    """CREATE TABLE scans (
        id INTEGER PRIMARY KEY,
        snapshot TEXT
    )""",
    """CREATE TABLE responses (
        scan_id INTEGER NOT NULL REFERENCES scans(id),
        seq INTEGER NOT NULL,
        metadata TEXT NOT NULL,
        raw BLOB,
        PRIMARY KEY (scan_id, seq)
    )""",
    """CREATE TABLE candles (
        symbol TEXT NOT NULL,
        interval TEXT NOT NULL,
        open_ms INTEGER NOT NULL,
        scan_id INTEGER NOT NULL,
        response_seq INTEGER NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY (symbol, interval, open_ms),
        FOREIGN KEY (scan_id, response_seq) REFERENCES responses(scan_id, seq)
    )""",
)


def decimal_json(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"unsupported public-market value: {type(value).__name__}")


def encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=decimal_json, allow_nan=False)


class Cache:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        if write:
            db = sqlite3.connect(self.path, timeout=1)
        else:
            db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=1)
        try:
            db.execute("PRAGMA foreign_keys = ON")
            if write:
                db.execute("BEGIN IMMEDIATE")
            application_id = db.execute("PRAGMA application_id").fetchone()[0]
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if write and (application_id, version) == (0, 0):
                require(not db.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone(), "CACHE_WRONG_SCHEMA")
                for statement in SCHEMA:
                    db.execute(statement)
                db.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            else:
                require((application_id, version) == (APPLICATION_ID, SCHEMA_VERSION), "CACHE_WRONG_SCHEMA")
            yield db
            if write:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def run(self, max_body_bytes: int) -> Iterator["ScanTransaction"]:
        with self.connect(write=True) as db:
            yield ScanTransaction(db, max_body_bytes)

    def load_snapshot(self, scan_id: int | None = None) -> dict[str, object]:
        with self.connect() as db:
            row = (db.execute("SELECT snapshot FROM scans ORDER BY id DESC LIMIT 1").fetchone()
                   if scan_id is None else db.execute("SELECT snapshot FROM scans WHERE id=?", (scan_id,)).fetchone())
            if row is None or row[0] is None:
                raise SourceBlocked("SNAPSHOT_NOT_FOUND")
            payload = json.loads(row[0])
            require(payload.get("schema") == SNAPSHOT_SCHEMA and payload.get("evidence_class") == EVIDENCE_CLASS
                    and payload.get("data_origin") == FIXTURE_CLASS, "WRONG_EVIDENCE_CLASS")
            return payload

    def load_receipts(self, scan_id: int) -> list[dict[str, object]]:
        """Export audit rows with the exact raw bytes encoded as base64."""
        with self.connect() as db:
            return [{**json.loads(metadata), "raw_base64": None if raw is None else base64.b64encode(raw).decode()}
                    for metadata, raw in db.execute(
                        "SELECT metadata, raw FROM responses WHERE scan_id=? ORDER BY seq", (scan_id,)
                    )]


class ScanTransaction:
    def __init__(self, db: sqlite3.Connection, max_body_bytes: int) -> None:
        self.db = db
        self.max_body_bytes = max_body_bytes
        scan_id = db.execute("INSERT INTO scans DEFAULT VALUES").lastrowid
        assert scan_id is not None
        self.scan_id = scan_id
        self.seq = 0

    def audit(self, route: str, params: Params, sent: Sample, received: Sample, status: int | None,
              headers: Mapping[str, str], body: bytes | None, error: str | None) -> int:
        self.seq += 1
        metadata = {
            "sequence": self.seq, "endpoint": route, "method": "GET", "params": params,
            "http_status": status, "headers": headers, "request": vars(sent), "receive": vars(received),
            "raw_sha256": None if body is None else hashlib.sha256(body).hexdigest(),
            "raw_bytes": None if body is None else len(body),
            "raw_complete": body is not None and len(body) <= self.max_body_bytes, "transport_error": error,
        }
        raw = body if metadata["raw_complete"] else None
        self.db.execute("INSERT INTO responses VALUES (?, ?, ?, ?)", (self.scan_id, self.seq, encode(metadata), raw))
        return self.seq

    def prior(self, symbol: str, interval: str, opened: int) -> dict[str, object] | None:
        row = self.db.execute("SELECT payload FROM candles WHERE symbol=? AND interval=? AND open_ms=?",
                              (symbol, interval, opened)).fetchone()
        return None if row is None else json.loads(row[0])

    def candle_tail(self, symbol: str, interval: str, limit: int) -> list[dict[str, object]]:
        values = list(self.db.execute("SELECT payload FROM candles WHERE symbol=? AND interval=? "
                                      "ORDER BY open_ms DESC LIMIT ?", (symbol, interval, limit)))
        return [json.loads(row[0]) for row in reversed(values)]

    def persist_candles(self, entries: list[tuple[str, str, int, int, dict[str, object]]]) -> None:
        self.db.executemany("INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?)",
                            ((symbol, interval, opened, self.scan_id, seq, encode(value))
                             for symbol, interval, opened, seq, value in entries))

    def finish(self, snapshot: dict[str, object]) -> dict[str, object]:
        payload = encode(snapshot)
        self.db.execute("UPDATE scans SET snapshot=? WHERE id=?", (payload, self.scan_id))
        return json.loads(payload)
