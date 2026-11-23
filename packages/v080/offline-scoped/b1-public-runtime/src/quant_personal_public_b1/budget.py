"""Atomic durable dispatch reservations and restart-safe cooling for one local egress."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import replace
from email.utils import parsedate_to_datetime
from typing import Any

from .policy import FUNDING, OI_HISTORY, QUOTE, SourceBlocked, require
from .store import Stamp, Store, encode, sha
from .wire import WEIGHT_HEADER, Reply, Request

MAX_WINDOW = 86_400_000
FIVE_MIN = 300_000
FAMILY_RULES = {FUNDING: ("FUNDING_SHARED", 500), OI_HISTORY: ("OI_HISTORY", 1000)}
REGION = re.compile(
    rb"restricted location|restricted jurisdiction|region restriction|country restriction|"
    rb"not available in your (country|region)|eligibility.{0,80}restricted", re.I,
)


def retry_after(headers: Mapping[str, str], wall_ms: int) -> int:
    raw = headers.get("retry-after", "").strip()
    if re.fullmatch(r"[0-9]{1,10}", raw):
        return int(raw) * 1000
    try:
        until = parsedate_to_datetime(raw)
        if until.tzinfo is None:
            return 60_000
        if "date" in headers:
            base = parsedate_to_datetime(headers["date"])
            return max(0, int((until - base).total_seconds() * 1000) + 1000)
        return max(60_000, int(until.timestamp() * 1000) - wall_ms + 1000)
    except (TypeError, ValueError, OverflowError, OSError):
        return 60_000


class Budget:
    def __init__(self, store: Store, *, bootstrap: int) -> None:
        self.store = store
        self.bootstrap = bootstrap

    def epoch(self, db: sqlite3.Connection, stamp: Stamp) -> sqlite3.Row:
        old = db.execute("SELECT * FROM budget_epoch WHERE singleton=1").fetchone()
        now = stamp.monotonic_ms
        if old is None:
            db.execute("INSERT INTO budget_epoch VALUES (1,?,?,0,0,NULL,?)", (stamp.boot, now, self.bootstrap))
        elif old["boot"] != stamp.boot:
            # Without a same-boot monotonic proof, retain every then-unexpired charge for a fresh window.
            for table in ("attempts", "headers"):
                db.execute(f"UPDATE {table} SET accounted_mono=NULL WHERE accounted_mono<=?",
                           (old["last_mono"] - MAX_WINDOW,))
                db.execute(f"UPDATE {table} SET accounted_mono=? WHERE accounted_mono IS NOT NULL", (now,))
            hold = old["cooldown_hold"] if old["cooldown_until"] > old["last_mono"] else 0
            db.execute("UPDATE budget_epoch SET boot=?,last_mono=?,cooldown_until=?,cooldown_hold=? WHERE singleton=1",
                       (stamp.boot, now, now + hold, hold))
        else:
            require(now >= old["last_mono"], "BUDGET_MONOTONIC_REGRESSION")
            db.execute("UPDATE budget_epoch SET last_mono=? WHERE singleton=1", (now,))
        db.execute("UPDATE budget_epoch SET bootstrap=MIN(bootstrap,?) WHERE singleton=1", (self.bootstrap,))
        row = db.execute("SELECT * FROM budget_epoch WHERE singleton=1").fetchone()
        assert row is not None
        return row

    def configure(self, limits: dict[tuple[str, int], int]) -> None:
        with self.store.connect(write=True) as db:
            db.executemany("INSERT INTO rules VALUES (?,?,?) ON CONFLICT(family,window_ms) DO UPDATE "
                           "SET ceiling=MIN(rules.ceiling,excluded.ceiling)",
                           ((kind, width, limit) for (kind, width), limit in limits.items()))

    def reserve(self, scan: int, logical: int, retry: int, request: Request, stamp: Stamp) -> int:
        weight, _ = request.validate()
        blocked = None
        ident = None
        with self.store.connect(write=True) as db:
            e = self.epoch(db, stamp)
            now = stamp.monotonic_ms
            if e["stop"]:
                blocked = e["stop"]
            elif now < e["cooldown_until"]:
                blocked = "RETRY_AFTER_ACTIVE"
            else:
                family, family_cap = FAMILY_RULES.get(request.route, ("GENERAL", 0))
                rules = {(kind, width): cap for kind, width, cap in db.execute("SELECT * FROM rules")}
                rules.setdefault(("REQUEST_WEIGHT", 60_000), e["bootstrap"])
                if family_cap:
                    rules[family, FIVE_MIN] = family_cap
                blocked = self.check_windows(db, now, rules, weight)
                if not blocked:
                    try:
                        cursor = db.execute(
                            "INSERT INTO attempts(scan_id,logical_request,retry,route,weight,family,egress,request,"
                            "reserved,accounted_mono) VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (scan, logical, retry, request.route, weight, family, self.store.egress,
                             encode({"host": request.host, "port": request.port, "method": request.method,
                                     "params": dict(request.params)}), encode(stamp.data()), now),
                        )
                    except sqlite3.IntegrityError as exc:
                        raise SourceBlocked("RESERVATION_IDENTITY_REUSED") from exc
                    ident = cursor.lastrowid
        # Commit the epoch even on denials, so repeated restarts cannot reset the hold window.
        if blocked:
            raise SourceBlocked(blocked)
        assert ident is not None
        return ident

    @staticmethod
    def check_windows(db: sqlite3.Connection, now: int,
                      rules: dict[tuple[str, int], int], weight: int) -> str | None:
        for (kind, width), ceiling in rules.items():
            limit_start = now - width
            if kind == "REQUEST_WEIGHT":
                used = db.execute("SELECT COALESCE(SUM(weight),0) FROM attempts WHERE accounted_mono>?",
                                  (limit_start,)).fetchone()[0]
                h = db.execute(
                    """SELECT MAX(h.used + (SELECT COALESCE(SUM(a.weight),0) FROM attempts a
                       WHERE a.id>h.attempt AND a.accounted_mono IS NOT NULL))
                       FROM headers h WHERE h.window_ms=? AND h.accounted_mono>?""", (width, limit_start),
                ).fetchone()[0]
                if max(used, h or 0) + weight > ceiling:
                    return "VENUE_WEIGHT_LIMIT"
            elif kind == "RAW_REQUESTS":
                used = db.execute("SELECT COUNT(*) FROM attempts WHERE accounted_mono>?", (limit_start,)).fetchone()[0]
                if used + 1 > ceiling:
                    return "VENUE_RAW_LIMIT"
            else:
                used = db.execute("SELECT COUNT(*) FROM attempts WHERE accounted_mono>? AND family=?",
                                  (limit_start, kind)).fetchone()[0]
                if used + 1 > ceiling:
                    return "ENDPOINT_FAMILY_LIMIT"
        return None

    def settle(self, ident: int, stamp: Stamp, reply: Reply | None, error: str | None = None) -> str | None:
        """Commit raw evidence and any sticky denial in one transaction before returning to a caller."""
        with self.store.connect(write=True) as db:
            previous = db.execute("SELECT boot,last_mono FROM budget_epoch WHERE singleton=1").fetchone()
            now = max(stamp.monotonic_ms, previous["last_mono"]) if previous and previous["boot"] == stamp.boot else stamp.monotonic_ms
            self.epoch(db, replace(stamp, monotonic_ms=now))
            row = db.execute("SELECT * FROM attempts WHERE id=? AND response IS NULL", (ident,)).fetchone()
            if row is None:
                raise SourceBlocked("ATTEMPT_ALREADY_SETTLED")
            headers = dict(reply.headers) if reply else {}
            status = reply.status if reply else None
            raw = reply.body if reply and reply.complete else None
            encoded = reply.encoded_body if reply else None
            metadata: dict[str, Any] = {"receipt": stamp.data(), "status": status, "headers": headers,
                                        "error": error or (reply.issue if reply else None), "wire_bytes": (
                                            reply.wire_bytes if reply else None),
                                        "body_sha256": sha(raw) if raw is not None else None,
                                        "encoded_sha256": sha(encoded) if encoded is not None else None,
                                        "tls": reply.tls if reply else None}
            db.execute("UPDATE attempts SET response=?,raw=?,encoded=?,accounted_mono=? WHERE id=?",
                       (encode(metadata), raw, encoded, now, ident))
            if row["route"] != QUOTE:
                for name, text in headers.items():
                    match = WEIGHT_HEADER.fullmatch(name)
                    if match is None or re.fullmatch(r"[0-9]{1,10}", text) is None:
                        continue
                    window = int(match[1][:-1]) * {"s": 1000, "m": 60_000, "h": 3_600_000, "d": MAX_WINDOW}[name[-1]]
                    if 0 < window <= MAX_WINDOW:
                        db.execute("INSERT INTO headers VALUES (?,?,?,?)", (ident, window, int(text), now))
            stop = None
            if status in {403, 418, 451}:
                stop = f"HTTP_{status}"
            elif raw and REGION.search(raw):
                stop = "VENUE_RESTRICTED"
            if stop:
                db.execute("UPDATE budget_epoch SET stop=COALESCE(stop,?) WHERE singleton=1", (stop,))
                return stop
            if status == 429:
                hold = retry_after(headers, stamp.wall_ms)
                db.execute("UPDATE budget_epoch SET cooldown_until=MAX(cooldown_until,?),"
                           "cooldown_hold=MAX(cooldown_hold,?) WHERE singleton=1",
                           (now + hold, hold))
                return "HTTP_429"
            return None

    def evidence(self, scan: int) -> list[dict[str, Any]]:
        with self.store.connect() as db:
            return [{
                "receipt_id": row["id"], "route": row["route"], "family": row["family"], "weight": row["weight"],
                "retry": row["retry"], "egress": row["egress"],
                "request": json.loads(row["request"]), "reservation": json.loads(row["reserved"]),
                "response": json.loads(row["response"]) if row["response"] else None,
            } for row in db.execute("SELECT * FROM attempts WHERE scan_id=? ORDER BY id", (scan,))]
