"""Bounded atomic synthetic receipts, immutable hash chains and explicit retention limits."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

from ..core import primitive
from .control import CanaryStore
from .policy import StoragePolicy


class StorageBlocked(RuntimeError):
    pass


def encode(value) -> bytes:
    return json.dumps(primitive(value), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class ReceiptStorage:
    def __init__(self, root: Path, store: CanaryStore, policy: StoragePolicy, *, crash_hook=None):
        if Path(root).is_symlink():
            raise StorageBlocked("UNTRUSTED_STORAGE_PATH")
        self.root, self.store, self.policy, self.crash_hook = Path(root).resolve(), store, policy, crash_hook
        self.root.mkdir(parents=True, exist_ok=True)
        self.chunks = self.root / "chunks"
        if self.chunks.is_symlink():
            raise StorageBlocked("UNTRUSTED_STORAGE_PATH")
        self.chunks.mkdir(exist_ok=True)
        with store._connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS canary_chunks (
                ordinal INTEGER PRIMARY KEY, sha TEXT UNIQUE NOT NULL, previous_sha TEXT,
                kind TEXT NOT NULL, symbol TEXT NOT NULL,start_ms INTEGER NOT NULL,end_ms INTEGER NOT NULL,
                bytes INTEGER NOT NULL,expires_ms INTEGER NOT NULL,version TEXT NOT NULL,raw_sha TEXT);
              CREATE TABLE IF NOT EXISTS canary_expired (
                sha TEXT PRIMARY KEY,expired_at_ms INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS canary_audits (
                sha TEXT PRIMARY KEY, evidence TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS canary_chunk_logical (
                id TEXT PRIMARY KEY,sha TEXT UNIQUE NOT NULL);
            """)

    def _disk_bytes(self):
        total = 0
        for p in self.root.rglob("*"):
            if p.is_symlink():
                raise StorageBlocked("UNTRUSTED_STORAGE_PATH")
            if p.is_file():
                total += p.stat().st_size
        return total

    def _rows(self):
        with self.store._connect() as db:
            return db.execute(
                "SELECT ordinal,sha,previous_sha,kind,symbol,start_ms,end_ms,bytes,expires_ms,version,raw_sha FROM canary_chunks ORDER BY ordinal"
            ).fetchall()

    def reserve_admission_capacity(self, normalized):
        """Conservative headroom for duplicated SQLite evidence/pages BEFORE admission.

        One bounded Phase A consumer owns a session. Chunk writes still serialize in SQLite.
        The 16x allowance includes captures, per-field bars, indexes and rollback journal.
        """
        required = max(65536, len(encode(normalized)) * 16)
        if (
            self._disk_bytes() + required + self.policy.metadata_base_reserve
            > self.policy.total_disk_quota_bytes
        ):
            raise StorageBlocked("STORAGE_BLOCKED:SQLITE_ADMISSION_HEADROOM")
        if shutil.disk_usage(self.root).free < required:
            raise StorageBlocked("STORAGE_BLOCKED:SQLITE_FREE_SPACE")

    def _quota(self, db, kind, symbol, size):
        if size > self.policy.chunk_bytes:
            raise StorageBlocked("CHUNK_QUOTA_EXCEEDED")
        rows = db.execute(
            "SELECT sha,kind,symbol,bytes FROM canary_chunks WHERE sha NOT IN (SELECT sha FROM canary_expired)"
        ).fetchall()
        if db.execute("SELECT COUNT(*) FROM canary_chunks").fetchone()[0] >= self.policy.max_chunks:
            raise StorageBlocked("MAX_CHUNK_COUNT_EXCEEDED")
        same_kind = sum(r[3] for r in rows if (r[1] == "RAW") == (kind == "RAW"))
        cap = self.policy.raw_quota_bytes if kind == "RAW" else self.policy.normalized_quota_bytes
        if (
            same_kind + size > cap
            or sum(r[3] for r in rows if r[2] == symbol) + size > self.policy.symbol_quota_bytes
        ):
            raise StorageBlocked("PAYLOAD_OR_SYMBOL_QUOTA_EXCEEDED")
        required = size + self.policy.metadata_reserve_per_chunk
        if (
            self._disk_bytes() + required + self.policy.metadata_base_reserve
            > self.policy.total_disk_quota_bytes
        ):
            raise StorageBlocked("TOTAL_DISK_QUOTA_EXCEEDED")
        if shutil.disk_usage(self.root).free < required:
            raise StorageBlocked("FREE_DISK_INSUFFICIENT")

    def write(
        self,
        kind: str,
        symbol: str,
        records: tuple[dict, ...],
        start_ms: int,
        end_ms: int,
        *,
        version="L4-NORMALIZER-1",
        raw_sha=None,
        optional_diagnostic=False,
    ):
        if kind not in {"RAW", "NORMALIZED", "DIAGNOSTIC"} or not records or end_ms < start_ms:
            raise ValueError("CHUNK_CONTRACT_INVALID")
        if any(r.get("exposure") != "SYNTHETIC" for r in records):
            raise ValueError("ONLY_FABRICATED_RECORDS_PERMITTED_IN_PHASE_A")
        hours = self.policy.raw_retention_hours if kind == "RAW" else self.policy.normalized_retention_hours
        logical = hashlib.sha256(
            encode([kind, symbol, records, start_ms, end_ms, end_ms + hours * 3_600_000, version, raw_sha])
        ).hexdigest()
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT sha FROM canary_chunk_logical WHERE id=?", (logical,)).fetchone()
            if old:
                expired = db.execute("SELECT 1 FROM canary_expired WHERE sha=?", (old[0],)).fetchone()
                p = self.chunks / (old[0] + ".json")
                if not expired and (
                    p.is_symlink() or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != old[0]
                ):
                    raise StorageBlocked("DEDUPLICATED_EVIDENCE_INTEGRITY_ERROR")
                return old[0]
            known = {r[0] for r in db.execute("SELECT sha FROM canary_chunks")}
            orphans = [p for p in self.chunks.glob("*.json") if p.stem not in known]
            if orphans or list(self.chunks.glob("*.part")):
                raise StorageBlocked("UNCOMMITTED_CHUNK_RECOVERY_REQUIRED")
            last = db.execute(
                "SELECT ordinal,sha FROM canary_chunks ORDER BY ordinal DESC LIMIT 1"
            ).fetchone()
            previous, ordinal = (last[1], last[0] + 1) if last else (None, 1)
            value = {
                "format": "L4-CHUNK-1",
                "exposure": "SYNTHETIC",
                "kind": kind,
                "symbol": symbol,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "expires_ms": end_ms + hours * 3_600_000,
                "normalizer_version": version,
                "previous_sha": previous,
                "raw_sha": raw_sha,
                "records": records,
            }
            blob = encode(value)
            identity = hashlib.sha256(blob).hexdigest()
            if identity in known:
                return identity
            try:
                self._quota(db, kind, symbol, len(blob))
            except StorageBlocked as exc:
                if kind == "DIAGNOSTIC" and optional_diagnostic:
                    row = db.execute(
                        "SELECT value FROM canary_values WHERE key='diagnostics_shed'"
                    ).fetchone()
                    count = json.loads(row[0]) if row else 0
                    db.execute(
                        "INSERT OR REPLACE INTO canary_values VALUES ('diagnostics_shed',?)",
                        (json.dumps(count + 1),),
                    )
                    return None
                raise StorageBlocked("STORAGE_BLOCKED:" + str(exc)) from exc
            target = self.chunks / (identity + ".json")
            part = self.chunks / (identity + ".part")
            with part.open("xb") as stream:
                stream.write(blob)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(part, target)
            if hasattr(os, "O_DIRECTORY"):
                fd = os.open(self.chunks, os.O_DIRECTORY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            if self.crash_hook:
                self.crash_hook("AFTER_ATOMIC_RENAME")
            db.execute(
                "INSERT INTO canary_chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ordinal,
                    identity,
                    previous,
                    kind,
                    symbol,
                    start_ms,
                    end_ms,
                    len(blob),
                    value["expires_ms"],
                    version,
                    raw_sha,
                ),
            )
            db.execute("INSERT INTO canary_chunk_logical VALUES (?,?)", (logical, identity))
        return identity

    def recover_orphans(self):
        if list(self.chunks.glob("*.part")):
            raise StorageBlocked("PARTIAL_UNCOMMITTED_CHUNK; no qualification evidence admitted")
        recovered = []
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            known = {r[0] for r in db.execute("SELECT sha FROM canary_chunks")}
            pending = [p for p in self.chunks.glob("*.json") if p.stem not in known]
            while pending:
                last = db.execute(
                    "SELECT ordinal,sha FROM canary_chunks ORDER BY ordinal DESC LIMIT 1"
                ).fetchone()
                previous, ordinal = (last[1], last[0] + 1) if last else (None, 1)
                found = False
                for p in list(pending):
                    blob = p.read_bytes()
                    if hashlib.sha256(blob).hexdigest() != p.stem:
                        raise StorageBlocked("ORPHAN_INTEGRITY_ERROR")
                    v = json.loads(blob)
                    if v.get("format") != "L4-CHUNK-1" or v.get("exposure") != "SYNTHETIC":
                        raise StorageBlocked("ORPHAN_SCHEMA_OR_EXPOSURE_INVALID")
                    if v["previous_sha"] != previous:
                        continue
                    db.execute(
                        "INSERT INTO canary_chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            ordinal,
                            p.stem,
                            previous,
                            v["kind"],
                            v["symbol"],
                            v["start_ms"],
                            v["end_ms"],
                            len(blob),
                            v["expires_ms"],
                            v["normalizer_version"],
                            v["raw_sha"],
                        ),
                    )
                    logical = hashlib.sha256(
                        encode(
                            [
                                v["kind"],
                                v["symbol"],
                                v["records"],
                                v["start_ms"],
                                v["end_ms"],
                                v["expires_ms"],
                                v["normalizer_version"],
                                v["raw_sha"],
                            ]
                        )
                    ).hexdigest()
                    db.execute("INSERT INTO canary_chunk_logical VALUES (?,?)", (logical, p.stem))
                    recovered.append(p.stem)
                    pending.remove(p)
                    found = True
                    break
                if not found:
                    raise StorageBlocked("ORPHAN_CHAIN_CONFLICT")
        return recovered

    def expire(self, now_ms: int):
        removed = []
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT sha FROM canary_chunks WHERE expires_ms<=? AND sha NOT IN (SELECT sha FROM canary_expired)",
                (now_ms,),
            ).fetchall()
            for (identity,) in rows:
                p = self.chunks / (identity + ".json")
                if p.is_symlink():
                    raise StorageBlocked("UNTRUSTED_STORAGE_PATH")
                if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != identity:
                    raise StorageBlocked("EXPIRY_INTEGRITY_FAILURE")
                # Persist the expiry intention first. Recovery can repeat this bounded deletion.
                db.execute("INSERT INTO canary_expired VALUES (?,?)", (identity, now_ms))
                removed.append(identity)
            db.commit()
        for identity in removed:
            (self.chunks / (identity + ".json")).unlink(missing_ok=True)
        return removed

    def audit(self):
        rows, previous, errors, retained_raw, expired_raw = self._rows(), None, [], 0, 0
        with self.store._connect() as db:
            expired = {r[0] for r in db.execute("SELECT sha FROM canary_expired")}
        known = {r[1] for r in rows}
        for row in rows:
            _, identity, prev, kind, _, _, _, size, _, _, _ = row
            if prev != previous:
                errors.append("MANIFEST_CHAIN_BROKEN:" + identity)
            previous = identity
            p = self.chunks / (identity + ".json")
            if identity in expired:
                if kind == "RAW":
                    expired_raw += 1
                if p.exists():
                    p.unlink()  # Complete a previously committed expiry after a crash.
                continue
            if (
                not p.is_file()
                or p.is_symlink()
                or p.stat().st_size != size
                or hashlib.sha256(p.read_bytes()).hexdigest() != identity
            ):
                errors.append("CHUNK_INTEGRITY_ERROR:" + identity)
            else:
                content = json.loads(p.read_bytes())
                expected = (prev, kind, row[4], row[5], row[6], row[8], row[9], row[10])
                observed = tuple(
                    content.get(k)
                    for k in (
                        "previous_sha",
                        "kind",
                        "symbol",
                        "start_ms",
                        "end_ms",
                        "expires_ms",
                        "normalizer_version",
                        "raw_sha",
                    )
                )
                if (
                    expected != observed
                    or content.get("format") != "L4-CHUNK-1"
                    or content.get("exposure") != "SYNTHETIC"
                ):
                    errors.append("MANIFEST_HEADER_MISMATCH:" + identity)
                if kind == "RAW":
                    retained_raw += 1
        if any(p.stem not in known for p in self.chunks.glob("*.json")) or list(self.chunks.glob("*.part")):
            errors.append("UNCOMMITTED_CHUNK_PRESENT")
        return {
            "status": "INTEGRITY_OK" if not errors else "INTEGRITY_ERROR",
            "errors": errors,
            "manifest_chunks": len(rows),
            "retained_raw_chunks": retained_raw,
            "expired_raw_chunks": expired_raw,
            "full_raw_replay_available": not errors and expired_raw == 0 and retained_raw > 0,
            "limitations": ["EARLIEST_RAW_NOT_RETAINED"] if expired_raw else [],
            "manifest": [
                {
                    "ordinal": r[0],
                    "sha256": r[1],
                    "previous_sha256": r[2],
                    "kind": r[3],
                    "symbol": r[4],
                    "utc_start_ms": r[5],
                    "utc_end_ms": r[6],
                    "bytes": r[7],
                    "expires_ms": r[8],
                    "normalizer_version": r[9],
                    "raw_sha": r[10],
                }
                for r in rows
            ],
        }

    def replay_crosscheck(self, normalizer):
        audit = self.audit()
        if audit["errors"]:
            raise StorageBlocked("REPLAY_REFUSES_CORRUPTED_OR_INCOMPLETE_EVIDENCE")
        checked, missing, normalized_expired = 0, 0, 0
        for row in self._rows():
            if row[3] != "NORMALIZED" or row[10] is None:
                continue
            raw_path = self.chunks / (row[10] + ".json")
            norm_path = self.chunks / (row[1] + ".json")
            if not norm_path.exists():
                normalized_expired += 1
                continue
            if not raw_path.exists():
                with self.store._connect() as db:
                    expired = db.execute("SELECT 1 FROM canary_expired WHERE sha=?", (row[10],)).fetchone()
                if not expired:
                    raise StorageBlocked("RAW_REFERENCE_NOT_A_RETAINED_OR_EXPIRED_CHUNK")
                missing += 1
                continue
            raw, norm = json.loads(raw_path.read_bytes()), json.loads(norm_path.read_bytes())
            reproduced = [primitive(normalizer(record)) for record in raw["records"]]
            if encode(reproduced) != encode(norm["records"]):
                raise StorageBlocked("NORMALIZATION_REPLAY_MISMATCH")
            checked += 1
        result = {
            "replayed_pairs": checked,
            "raw_expired_pairs_not_replayed": missing,
            "normalized_expired_pairs": normalized_expired,
            "parity": "VERIFIED_FOR_RETAINED_RAW" if checked else "NO_RETAINED_PAIRS",
            "complete_raw_replay": missing == 0 and normalized_expired == 0 and checked > 0,
            "exposure": "SYNTHETIC",
        }
        self.store.set_value("replay_crosscheck", result)
        return result
