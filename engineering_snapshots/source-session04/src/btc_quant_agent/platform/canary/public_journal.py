"""Bounded compressed native receipts on the existing SQLite advisory store.

Raw bytes and normalization results are separate immutable, hash-chained chunks.
This codec is separate from the sealed Phase A JSON-chunk codec; no old evidence is rewritten.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil

from ..core import primitive, fingerprint
from .storage import StorageBlocked, encode
from .telemetry import NULL


class PublicJournal:
    def __init__(
        self,
        root,
        store,
        clock,
        *,
        exposure="PUBLIC_CANARY",
        raw_cap=8 * 1024**3,
        aux_cap=4 * 1024**3,
        reserve=2 * 1024**3,
        chunk_cap=1024**2,
        crash_hook=None,
        telemetry=None,
    ):
        self.root, self.store, self.clock = Path(root), store, clock
        self.telemetry = telemetry or getattr(store, "telemetry", NULL)
        self.exposure, self.raw_cap, self.aux_cap, self.reserve = exposure, raw_cap, aux_cap, reserve
        self.chunk_cap, self.crash_hook = chunk_cap, crash_hook
        if exposure not in ("PUBLIC_CANARY", "SYNTHETIC"):
            raise StorageBlocked("UNSUPPORTED_RECEIPT_EXPOSURE")
        for p in (self.root, *self.root.parents):
            if p.is_symlink():
                raise StorageBlocked("UNTRUSTED_JOURNAL_PATH")
        self.root.mkdir(parents=True, exist_ok=True)
        for kind in ("raw", "normalized"):
            if (self.root / kind).is_symlink():
                raise StorageBlocked("UNTRUSTED_JOURNAL_PATH")
            (self.root / kind).mkdir(exist_ok=True)
        with store._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS public_chunks (
              ordinal INTEGER PRIMARY KEY,sha TEXT UNIQUE,previous_sha TEXT,kind TEXT,symbols TEXT,
              start_ms INTEGER,end_ms INTEGER,expires_ms INTEGER,bytes INTEGER,allocated INTEGER,
              raw_sha TEXT,commit_observed_ms INTEGER,exposure TEXT);
            CREATE INDEX IF NOT EXISTS public_chunks_kind ON public_chunks(kind);
            CREATE TABLE IF NOT EXISTS public_expired (sha TEXT PRIMARY KEY,expired_ms INTEGER);
            CREATE TABLE IF NOT EXISTS public_pairs (raw_sha TEXT PRIMARY KEY,normalized_sha TEXT);
            """)
        self.recover()

    def _path(self, kind, sha):
        return self.root / kind / (sha + ".json.gz")

    def rows(self):
        with self.store._connect() as db:
            return db.execute("SELECT * FROM public_chunks ORDER BY ordinal").fetchall()

    def used(self):
        with self.store._connect() as db:
            totals = dict(
                db.execute(
                    "SELECT kind,COALESCE(SUM(allocated),0) FROM public_chunks WHERE sha NOT IN (SELECT sha FROM public_expired) GROUP BY kind"
                )
            )
        # State/index/log/control bytes are counted separately from native compressed files.
        other = 0
        for d in (self.root, self.root.parent):
            for p in d.iterdir():
                if p.is_symlink():
                    if d == self.root:
                        raise StorageBlocked("UNTRUSTED_JOURNAL_PATH")
                    continue
                if p.is_file():
                    other += p.stat().st_blocks * 512 if hasattr(p.stat(), "st_blocks") else p.stat().st_size
        if self.exposure == "PUBLIC_CANARY":
            for child in self.root.parent.iterdir():
                if child == self.root or not child.is_dir() or child.is_symlink():
                    continue
                for file in child.rglob("*"):
                    if file.is_symlink():
                        raise StorageBlocked("UNTRUSTED_JOURNAL_PATH")
                    if file.is_file():
                        other += (
                            file.stat().st_blocks * 512
                            if hasattr(file.stat(), "st_blocks")
                            else file.stat().st_size
                        )
        return {"raw": totals.get("raw", 0), "auxiliary": totals.get("normalized", 0) + other}

    def write(self, kind, records, *, raw_sha=None):
        stage = "journal.raw_commit" if kind == "raw" else "journal.normalized_commit"
        with self.telemetry.measure(stage):
            return self._write(kind, records, raw_sha=raw_sha)

    def _write(self, kind, records, *, raw_sha=None):
        if kind not in ("raw", "normalized") or not records:
            raise ValueError("CHUNK_KIND_OR_RECORDS_INVALID")
        if any(r.get("exposure") != self.exposure for r in records):
            raise StorageBlocked("MIXED_OR_FALSE_RECEIPT_EXPOSURE")
        times = [r["received_wall_ms"] for r in records]
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM public_chunks").fetchone()[0] >= 200000:
                raise StorageBlocked("MANIFEST_COUNT_CAP_EXCEEDED")
            prior = db.execute("SELECT sha FROM public_chunks ORDER BY ordinal DESC LIMIT 1").fetchone()
            value = {
                "format": "L4-PUBLIC-GZIP-1",
                "normalizer": "L4-PUBLIC-NORMALIZER-1",
                "exposure": self.exposure,
                "kind": kind,
                "previous_sha": prior[0] if prior else None,
                "raw_sha": raw_sha,
                "start_ms": min(times),
                "end_ms": max(times),
                "expires_ms": max(times) + (36 if kind == "raw" else 168) * 3600000,
                "records": records,
            }
            with self.telemetry.measure("journal.encode"):
                encoded = encode(value)
            if len(encoded) > 16 * self.chunk_cap:
                raise StorageBlocked("UNCOMPRESSED_CHUNK_CAP")
            with self.telemetry.measure("journal.gzip"):
                data = gzip.compress(encoded, mtime=0)
            if len(data) > self.chunk_cap:
                raise StorageBlocked("COMPRESSED_CHUNK_CAP")
            identity = hashlib.sha256(data).hexdigest()
            needed = ((len(data) + 4095) // 4096) * 4096
            used = self.used()
            cap = self.raw_cap if kind == "raw" else self.aux_cap
            overhead = 65536  # conservative SQLite manifest/journal growth per chunk
            if (
                used["raw" if kind == "raw" else "auxiliary"]
                + needed
                + (overhead if kind == "normalized" else 0)
                > cap
                or used["auxiliary"] + overhead > self.aux_cap
            ):
                raise StorageBlocked("STORAGE_SCOPE_BLOCKED")
            if shutil.disk_usage(self.root).free < needed + overhead + self.reserve:
                raise StorageBlocked("DISK_RESERVE_BLOCKED")
            path = self._path(kind, identity)
            part = path.with_suffix(".part")
            with part.open("xb") as f:
                f.write(data)
                f.flush()
                self._sync(f.fileno(), "journal.fsync_file")
            os.replace(part, path)
            fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                self._sync(fd, "journal.fsync_directory")
            finally:
                os.close(fd)
            if self.crash_hook:
                self.crash_hook("AFTER_RENAME")
            alloc = path.stat().st_blocks * 512 if hasattr(path.stat(), "st_blocks") else len(data)
            db.execute(
                "INSERT INTO public_chunks(sha,previous_sha,kind,symbols,start_ms,end_ms,expires_ms,bytes,allocated,raw_sha,exposure) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identity,
                    value["previous_sha"],
                    kind,
                    json.dumps(sorted({r.get("symbol", "*") for r in records})),
                    value["start_ms"],
                    value["end_ms"],
                    value["expires_ms"],
                    len(data),
                    alloc,
                    raw_sha,
                    self.exposure,
                ),
            )
        observed = self.clock.wall()
        with self.store._connect() as db:
            db.execute("UPDATE public_chunks SET commit_observed_ms=? WHERE sha=?", (observed, identity))
            if kind == "normalized":
                db.execute("INSERT INTO public_pairs VALUES (?,?)", (raw_sha, identity))
        return identity, observed

    def _sync(self, fd, stage):
        with self.telemetry.measure(stage):
            os.fsync(fd)

    def recover(self):
        rows = self.rows()
        with self.store._connect() as db:
            expired = {r[0] for r in db.execute("SELECT sha FROM public_expired")}
        for row in rows:
            if row[1] in expired and self._path(row[3], row[1]).exists():
                self.read(row)
                self._path(row[3], row[1]).unlink()
        known = {r[1] for r in rows}
        previous = rows[-1][1] if rows else None
        pending = [
            p
            for kind in ("raw", "normalized")
            for p in (self.root / kind).glob("*.json.gz")
            if p.name[:-8] not in known
        ]
        if any(list((self.root / k).glob("*.part")) for k in ("raw", "normalized")):
            raise StorageBlocked("INCOMPLETE_CHUNK_REQUIRES_OPERATOR_RECONCILIATION")
        while pending:
            progress = False
            for p in list(pending):
                data = p.read_bytes()
                identity = hashlib.sha256(data).hexdigest()
                if identity != p.name[:-8]:
                    raise StorageBlocked("ORPHAN_HASH_MISMATCH")
                value = json.loads(gzip.decompress(data))
                if value["previous_sha"] != previous:
                    continue
                if value["format"] != "L4-PUBLIC-GZIP-1" or value["exposure"] != self.exposure:
                    raise StorageBlocked("ORPHAN_SCHEMA_EXPOSURE_INVALID")
                alloc = p.stat().st_blocks * 512 if hasattr(p.stat(), "st_blocks") else len(data)
                with self.store._connect() as db:
                    db.execute(
                        "INSERT INTO public_chunks(sha,previous_sha,kind,symbols,start_ms,end_ms,expires_ms,bytes,allocated,raw_sha,exposure) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            identity,
                            previous,
                            value["kind"],
                            "[]",
                            value["start_ms"],
                            value["end_ms"],
                            value["expires_ms"],
                            len(data),
                            alloc,
                            value["raw_sha"],
                            self.exposure,
                        ),
                    )
                    if value["kind"] == "normalized":
                        db.execute(
                            "INSERT OR IGNORE INTO public_pairs VALUES (?,?)", (value["raw_sha"], identity)
                        )
                pending.remove(p)
                previous = identity
                progress = True
            if not progress:
                raise StorageBlocked("ORPHAN_CHAIN_CONFLICT")

    def read(self, row):
        p = self._path(row[3], row[1])
        if p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != row[1]:
            raise StorageBlocked("RECEIPT_HASH_MISMATCH")
        value = json.loads(gzip.decompress(p.read_bytes()))
        if (
            value["previous_sha"],
            value["kind"],
            value["start_ms"],
            value["end_ms"],
            value["expires_ms"],
            value["raw_sha"],
            value["exposure"],
        ) != (row[2], row[3], row[5], row[6], row[7], row[10], row[12]):
            raise StorageBlocked("MANIFEST_HEADER_MISMATCH")
        return value

    def audit_replay(self, normalizer):
        rows = self.rows()
        mapping = {r[1]: r for r in rows}
        previous = None
        checked = 0
        unpaired = 0
        with self.store._connect() as db:
            expired = {r[0] for r in db.execute("SELECT sha FROM public_expired")}
        for r in rows:
            if r[2] != previous:
                raise StorageBlocked("CHAIN_ORDER_MISMATCH")
            previous = r[1]
            if r[1] in expired:
                continue
            v = self.read(r)
            if r[3] == "normalized":
                raw = mapping.get(r[10])
                if raw is None:
                    raise StorageBlocked("RAW_REFERENCE_MISSING")
                if raw[1] in expired:
                    continue
                expected = [primitive(normalizer(x)) for x in self.read(raw)["records"]]
                if encode(expected) != encode(v["records"]):
                    raise StorageBlocked("NATIVE_REPLAY_MISMATCH")
                checked += 1
        # Verify compact metadata projections against their original native raw receipt.
        checked_origins = set()
        for raw in rows:
            if raw[3] != "raw" or raw[1] in expired:
                continue
            for record in self.read(raw)["records"]:
                m = record.get("metadata") or {}
                origin = m.get("source_raw_chunk_sha")
                if not origin:
                    continue
                if origin not in mapping:
                    raise StorageBlocked("METADATA_ORIGIN_MISSING")
                if origin in expired:
                    continue
                key = (origin, m["projection_source_wire_sha"], fingerprint(m["wire"]))
                if key in checked_origins:
                    continue
                source = next(
                    (
                        r["wire"]
                        for r in self.read(mapping[origin])["records"]
                        if fingerprint(r.get("wire")) == m["projection_source_wire_sha"]
                    ),
                    None,
                )
                if source is None:
                    raise StorageBlocked("METADATA_ORIGIN_WIRE_MISSING")
                native = json.loads(source["payload_text"])
                projected = json.loads(m["wire"]["payload_text"])
                for item in projected["symbols"]:
                    matches = [x for x in native["symbols"] if x.get("symbol") == item.get("symbol")]
                    if matches != [item]:
                        raise StorageBlocked("METADATA_PROJECTION_MISMATCH")
                checked_origins.add(key)
        paired = {r[10] for r in rows if r[3] == "normalized"}
        unpaired = sum(r[3] == "raw" and r[1] not in paired for r in rows)
        return {
            "checked_pairs": checked,
            "unpaired_raw_chunks": unpaired,
            "status": "PARITY_VERIFIED"
            if checked and not unpaired
            else "INCOMPLETE"
            if unpaired
            else "NO_RECEIPTS",
            "exposure": self.exposure,
            "expired_chunks": len(expired),
            "complete_retained_raw_replay": bool(checked and not unpaired and not expired),
            "manifest": [
                {
                    "sha256": r[1],
                    "previous_sha256": r[2],
                    "kind": r[3],
                    "start_ms": r[5],
                    "end_ms": r[6],
                    "expires_ms": r[7],
                    "bytes": r[8],
                    "raw_sha": r[10],
                    "commit_observed_ms": r[11],
                }
                for r in rows
            ],
        }

    def expire(self, now):
        removed = []
        for r in self.rows():
            if now < r[7]:
                continue
            with self.store._connect() as db:
                old = db.execute("SELECT 1 FROM public_expired WHERE sha=?", (r[1],)).fetchone()
                if old:
                    continue
                self.read(r)
                db.execute("INSERT INTO public_expired VALUES (?,?)", (r[1], now))
            self._path(r[3], r[1]).unlink()
            removed.append(r[1])
        return {"expired": removed, "limitation": "EARLIEST_RAW_NOT_RETAINED" if removed else None}
