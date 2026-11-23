"""Origin-tagged SQLite evidence, single collector, and append-only causal publication."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from .clock import Sample
from .policy import SourceBlocked, require
from .wire import FIXTURE, GENUINE, LOOPBACK

ORIGINS = frozenset({FIXTURE, LOOPBACK, GENUINE})
APP_ID = 0x51423132
VERSION = 1
SCHEMA = (
    "CREATE TABLE identity (origin TEXT NOT NULL, egress TEXT NOT NULL)",
    """CREATE TABLE budget_epoch (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1), boot TEXT NOT NULL, last_mono INTEGER NOT NULL,
        cooldown_until INTEGER NOT NULL, cooldown_hold INTEGER NOT NULL, stop TEXT, bootstrap INTEGER NOT NULL
    )""",
    """CREATE TABLE rules (
        family TEXT NOT NULL, window_ms INTEGER NOT NULL, ceiling INTEGER NOT NULL,
        PRIMARY KEY (family, window_ms)
    )""",
    """CREATE TABLE scans (
        id INTEGER PRIMARY KEY, starting TEXT NOT NULL, staged TEXT, abandoned TEXT
    )""",
    """CREATE TABLE attempts (
        id INTEGER PRIMARY KEY, scan_id INTEGER NOT NULL REFERENCES scans(id), logical_request INTEGER NOT NULL,
        retry INTEGER NOT NULL CHECK (retry IN (0,1)), route TEXT NOT NULL, weight INTEGER NOT NULL,
        family TEXT NOT NULL, egress TEXT NOT NULL, request TEXT NOT NULL, reserved TEXT NOT NULL,
        accounted_mono INTEGER, response TEXT, raw BLOB, encoded BLOB,
        UNIQUE (scan_id, logical_request, retry)
    )""",
    "CREATE INDEX attempts_by_window ON attempts(accounted_mono)",
    "CREATE INDEX attempts_by_family ON attempts(family,accounted_mono)",
    """CREATE TABLE headers (
        attempt INTEGER NOT NULL REFERENCES attempts(id), window_ms INTEGER NOT NULL, used INTEGER NOT NULL,
        accounted_mono INTEGER, PRIMARY KEY (attempt, window_ms)
    )""",
    "CREATE INDEX headers_by_window ON headers(window_ms,accounted_mono)",
    """CREATE TABLE bars (
        scan_id INTEGER NOT NULL REFERENCES scans(id), symbol TEXT NOT NULL, frame TEXT NOT NULL,
        open_ms INTEGER NOT NULL, hash TEXT NOT NULL, version INTEGER NOT NULL, data TEXT NOT NULL,
        PRIMARY KEY (scan_id, symbol, frame, open_ms)
    )""",
    "CREATE INDEX bars_by_identity ON bars(symbol, frame, open_ms, scan_id DESC)",
    """CREATE TABLE publications (
        scan_id INTEGER PRIMARY KEY REFERENCES scans(id), visible_venue_upper_ms INTEGER,
        published_wall_ms INTEGER NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL
    )""",
    "CREATE INDEX publications_by_time ON publications(visible_venue_upper_ms)",
)


def json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(type(value).__name__)


def encode(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=json_default, allow_nan=False)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Stamp:
    boot: str
    session: str
    wall_ms: int
    monotonic_ms: int

    @classmethod
    def capture(cls, boot: str, session: str, sample: Sample) -> Stamp:
        return cls(boot, session, sample.wall_ms, sample.mono_ms)

    def data(self) -> dict[str, str | int]:
        return asdict(self)


class Store:
    def __init__(self, path: Path, origin: str, egress: str, *, create: bool = False) -> None:
        require(origin in ORIGINS, "UNKNOWN_ORIGIN")
        self.path = path.resolve()
        self.origin = origin
        self.egress = egress
        if create:
            require(origin != GENUINE, "LIVE_CAPABILITY_DORMANT")
            with self.connect(write=True) as db:
                app = db.execute("PRAGMA application_id").fetchone()[0]
                if app == 0:
                    require(not db.execute("SELECT name FROM sqlite_master").fetchone(), "DB_UNKNOWN_SCHEMA")
                    for statement in SCHEMA:
                        db.execute(statement)
                    db.execute(f"PRAGMA application_id={APP_ID}")
                    db.execute(f"PRAGMA user_version={VERSION}")
                    db.execute("INSERT INTO identity VALUES (?,?)", (origin, egress))
                self.verify(db)
        else:
            with self.connect() as db:
                self.verify(db)

    @contextmanager
    def connect(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        target = str(self.path) if write else self.path.as_uri() + "?mode=ro"
        db = sqlite3.connect(target, uri=not write, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            if write:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def verify(self, db: sqlite3.Connection) -> None:
        app = db.execute("PRAGMA application_id").fetchone()[0]
        version = db.execute("PRAGMA user_version").fetchone()[0]
        require((app, version) == (APP_ID, VERSION), "DB_UNKNOWN_SCHEMA")
        identities = db.execute("SELECT origin,egress FROM identity").fetchall()
        require(len(identities) == 1 and tuple(identities[0]) == (self.origin, self.egress), "DB_ORIGIN_MISMATCH")

    @contextmanager
    def collector(self) -> Iterator[None]:
        # Dedicated OS-backed SQLite file lock. Budget transactions remain durable in the evidence DB.
        path = self.path.with_name(self.path.name + ".collector-lock")
        lock = sqlite3.connect(path, timeout=0)
        try:
            try:
                lock.execute("BEGIN EXCLUSIVE")
            except sqlite3.OperationalError as exc:
                if exc.sqlite_errorcode in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                    raise SourceBlocked("COLLECTOR_ALREADY_RUNNING") from exc
                raise
            yield
        finally:
            lock.close()

    def start(self, stamp: Stamp) -> int:
        with self.connect(write=True) as db:
            db.execute(
                "UPDATE scans SET abandoned=? WHERE abandoned IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM publications WHERE scan_id=scans.id)", (encode(stamp.data()),),
            )
            row = db.execute("INSERT INTO scans(starting) VALUES (?)", (encode(stamp.data()),))
            assert row.lastrowid is not None
            return row.lastrowid

    def stage(self, scan: int, data: dict[str, Any], bars: list[tuple[str, str, dict[str, Any]]]) -> None:
        with self.connect(write=True) as db:
            result = db.execute("UPDATE scans SET staged=? WHERE id=? AND staged IS NULL AND abandoned IS NULL",
                                (encode(data), scan))
            require(result.rowcount == 1, "SCAN_ALREADY_STAGED")
            db.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?)",
                           ((scan, symbol, frame, bar["open_ms"], bar["source_row_sha256"], bar["revision"],
                             encode(bar)) for symbol, frame, bar in bars))

    def publish(self, scan: int, payload: dict[str, Any], stamp: Stamp, upper_ms: int | None) -> dict[str, Any]:
        written = encode(payload)
        with self.connect(write=True) as db:
            row = db.execute("SELECT staged FROM scans WHERE id=? AND abandoned IS NULL", (scan,)).fetchone()
            require(row is not None and row["staged"] is not None, "SCAN_NOT_DURABLE")
            last = db.execute("SELECT MAX(visible_venue_upper_ms) FROM publications").fetchone()[0]
            require(upper_ms is None or last is None or upper_ms >= last, "PUBLICATION_TIME_REGRESSION")
            db.execute("INSERT INTO publications VALUES (?,?,?,?,?)",
                       (scan, upper_ms, stamp.wall_ms, written, sha(written.encode())))
        return json.loads(written)

    def snapshot(self, *, scan: int | None = None, as_of_ms: int | None = None) -> dict[str, Any] | None:
        require(scan is None or as_of_ms is None, "AMBIGUOUS_REPLAY_SELECTOR")
        query = "SELECT payload,sha256 FROM publications"
        args: tuple[int, ...] = ()
        if scan is not None:
            query += " WHERE scan_id=?"
            args = (scan,)
        if as_of_ms is not None:
            query += " WHERE visible_venue_upper_ms<=?"
            args = (as_of_ms,)
        with self.connect() as db:
            row = db.execute(query + " ORDER BY scan_id DESC LIMIT 1", args).fetchone()
            if row is None:
                return None
            require(sha(row["payload"].encode()) == row["sha256"], "PUBLICATION_DIGEST_MISMATCH")
            result = json.loads(row["payload"])
            require(result.get("source_origin") == self.origin and result.get("schema") == "PERSONAL_PUBLIC_MARKET_SNAPSHOT_V2",
                    "SNAPSHOT_ORIGIN_MISMATCH")
            return result

    def tail(self, symbol: str, frame: str, limit: int) -> list[dict[str, Any]]:
        # The index and correlated lookup avoid scanning every candle revision on each refresh.
        with self.connect() as db:
            rows = db.execute(
                """SELECT b.data, json_extract(p.payload,'$.durable_availability') AS durable
                   FROM bars b JOIN publications p ON p.scan_id=b.scan_id
                   WHERE b.symbol=? AND b.frame=? AND b.scan_id=(
                       SELECT MAX(c.scan_id) FROM bars c JOIN publications q ON q.scan_id=c.scan_id
                       WHERE c.symbol=b.symbol AND c.frame=b.frame AND c.open_ms=b.open_ms
                         AND q.visible_venue_upper_ms IS NOT NULL
                   ) AND p.visible_venue_upper_ms IS NOT NULL
                   ORDER BY b.open_ms DESC LIMIT ?""", (symbol, frame, limit),
            ).fetchall()
        return [{**json.loads(row["data"]), "first_durable_availability": json.loads(row["durable"])}
                for row in reversed(rows)]

    def last_comparable(self) -> dict[str, Any]:
        with self.connect() as db:
            row = db.execute(
                "SELECT p.payload FROM scans s JOIN publications p ON s.id=p.scan_id "
                "WHERE p.visible_venue_upper_ms IS NOT NULL ORDER BY s.id DESC LIMIT 1"
            ).fetchone()
            return {} if row is None else json.loads(row[0])

    def last_venue_upper(self) -> int | None:
        with self.connect() as db:
            return db.execute("SELECT MAX(visible_venue_upper_ms) FROM publications").fetchone()[0]

    def raw(self, attempt: int) -> bytes:
        with self.connect() as db:
            row = db.execute("SELECT response,raw FROM attempts WHERE id=?", (attempt,)).fetchone()
            require(row is not None and row["raw"] is not None, "RAW_UNAVAILABLE")
            require(sha(row["raw"]) == json.loads(row["response"])["body_sha256"], "RAW_DIGEST_MISMATCH")
            return row["raw"]
