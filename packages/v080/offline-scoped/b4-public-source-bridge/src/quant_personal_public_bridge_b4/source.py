"""Local source ledger and post-commit B4 publication envelopes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from quant_personal_public_b1.clock import Sample
from quant_personal_public_b1.policy import require
from quant_personal_public_b1.session import RunIdentity
from quant_personal_public_b1.store import Store, encode, sha
from quant_personal_public_b1.wire import FIXTURE as B1_FIXTURE, LOOPBACK as B1_LOOPBACK

from .live import open_live
from .routes import CONTRACT
from .transport import FIXTURE, GENUINE, LOOPBACK, WARNINGS

SCHEMA = "B4_PUBLIC_SOURCE_PUBLICATION_V1"
RECEIPT = "B4_PUBLIC_SOURCE_RECEIPT_V1"
STORE_ID = "B4_SOURCE_LEDGER_V1"
ORIGINS = {FIXTURE: B1_FIXTURE, LOOPBACK: B1_LOOPBACK}


def digest(value: object) -> str:
    return sha(encode(value).encode())


class Ledger:
    def __init__(self, path: Path, origin: str, *, create: bool = False) -> None:
        if origin == GENUINE:
            open_live()
        require(origin in ORIGINS, "UNQUALIFIED_SOURCE_ORIGIN")
        self.origin = origin
        self.store = Store(path, ORIGINS[origin], "b4-" + origin, create=create)
        with self.store.connect(write=create) as db:
            if create:
                db.execute("CREATE TABLE IF NOT EXISTS b4_identity (schema TEXT, origin TEXT, lineage TEXT)")
                db.execute("CREATE TABLE IF NOT EXISTS b4_sends "
                           "(attempt INTEGER PRIMARY KEY REFERENCES attempts(id), stamp TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS b4_visibility (scan_id INTEGER PRIMARY KEY "
                           "REFERENCES publications(scan_id), stamp TEXT NOT NULL, upper_ms INTEGER)")
                if not db.execute("SELECT 1 FROM b4_identity").fetchone():
                    db.execute("INSERT INTO b4_identity VALUES (?,?,?)", (STORE_ID, origin, uuid4().hex))
            rows = db.execute("SELECT schema,origin,lineage FROM b4_identity").fetchall()
            require(len(rows) == 1 and tuple(rows[0])[:2] == (STORE_ID, origin), "LEDGER_ORIGIN_MISMATCH")
            self.lineage = rows[0]["lineage"]

    def start(self, stamp) -> int:
        with self.store.connect() as db:
            # A crash after dispatch may have lost a venue denial. Fail closed on that ambiguity.
            require(not db.execute("SELECT 1 FROM attempts WHERE response IS NULL LIMIT 1").fetchone(),
                    "DISPATCH_OUTCOME_UNKNOWN")
        return self.store.start(stamp)

    def sent(self, ident: int, identity: RunIdentity, sample: Sample) -> None:
        with self.store.connect(write=True) as db:
            db.execute("INSERT INTO b4_sends VALUES (?,?)", (ident, encode(identity.stamp(sample).data())))

    def record_visibility(self, scan, stamp, upper_ms):
        with self.store.connect(write=True) as db:
            last = db.execute("SELECT MAX(upper_ms) FROM b4_visibility").fetchone()[0]
            require(last is None or upper_ms is None or upper_ms > last, "PUBLICATION_TIME_REGRESSION")
            db.execute("INSERT INTO b4_visibility VALUES (?,?,?)", (scan, encode(stamp.data()), upper_ms))

    def publication(self, scan: int | None = None, as_of_ms: int | None = None, *, db=None):
        if db is None:
            with self.store.connect() as conn:
                return self.publication(scan, as_of_ms, db=conn)
        query = ("SELECT p.*,s.staged,v.stamp AS visible_stamp,v.upper_ms AS visible_upper "
                 "FROM publications p JOIN scans s ON s.id=p.scan_id "
                 "JOIN b4_visibility v ON v.scan_id=p.scan_id WHERE 1=1")
        args: list[int] = []
        if scan is not None:
            query += " AND p.scan_id=?"
            args.append(scan)
        if as_of_ms is not None:
            query += " AND v.upper_ms<=?"
            args.append(as_of_ms)
        row = db.execute(query + " ORDER BY p.scan_id DESC LIMIT 1", args).fetchone()
        if row is None:
            return None
        require(row["sha256"] == sha(row["payload"].encode()), "PUBLICATION_DIGEST_MISMATCH")
        value = json.loads(row["payload"])
        require(value.get("schema") == SCHEMA and value.get("origin") == self.origin
                and value.get("warnings") == list(WARNINGS) and value.get("contract") == CONTRACT
                and value.get("lineage") == self.lineage and value.get("scan_id") == row["scan_id"],
                "UNQUALIFIED_SOURCE_PUBLICATION")
        staged = row["staged"]
        require(isinstance(staged, str) and value.get("stage_sha256") == sha(staged.encode())
                and value.get("stage") == json.loads(staged), "STAGE_DIGEST_MISMATCH")
        require(value.get("visible_venue_upper_ms") == row["visible_venue_upper_ms"]
                and value["publication_started"]["wall_ms"] == row["published_wall_ms"], "PUBLICATION_TIME_MISMATCH")
        visible_stamp = json.loads(row["visible_stamp"])
        require((row["visible_upper"] is None) == (row["visible_venue_upper_ms"] is None)
                and (row["visible_upper"] is None or row["visible_upper"] >= row["visible_venue_upper_ms"]),
                "PUBLICATION_VISIBILITY_MISMATCH")
        return {**value, "published": visible_stamp, "visible_venue_upper_ms": row["visible_upper"]}, digest(
            [row["sha256"], visible_stamp, row["visible_upper"]])

    def tail(self, symbol: str, frame: str, start: int, end: int) -> dict[int, dict[str, Any]]:
        with self.store.connect() as db:
            rows = db.execute(
                """SELECT data,open_ms,scan_id FROM (
                     SELECT b.*,ROW_NUMBER() OVER (PARTITION BY open_ms ORDER BY b.scan_id DESC) AS newest
                     FROM bars b JOIN b4_visibility p ON p.scan_id=b.scan_id
                     WHERE symbol=? AND frame=? AND open_ms>=? AND open_ms<?
                       AND p.upper_ms IS NOT NULL)
                   WHERE newest=1 ORDER BY open_ms""", (symbol, frame, start, end),
            )
            return {r["open_ms"]: json.loads(r["data"]) for r in rows}

    def prior_observations(self, symbol: str) -> dict:
        with self.store.connect() as db:
            row = db.execute(
                """SELECT p.scan_id FROM publications p JOIN b4_visibility v ON v.scan_id=p.scan_id
                   WHERE v.upper_ms IS NOT NULL
                   AND json_extract(payload,?) IS NULL AND json_type(payload,?)='object'
                   ORDER BY p.scan_id DESC LIMIT 1""",
                (f"$.stage.markets.{symbol}.issue", f"$.stage.markets.{symbol}.observations"),
            ).fetchone()
            found = self.publication(row[0], db=db) if row else None
            return found[0]["stage"]["markets"][symbol]["observations"] if found else {}
