"""Append-only independently verifiable qualification evidence and exact plans."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time
from typing import Literal

from ..native.contract import Strict, canonical, digest, require, strict, verify_key

SCHEMA_PATH = Path(__file__).parent / "schema.json"
STAGES = strict(SCHEMA_PATH.read_bytes())["stages"]
SCHEMA_HASH = digest(strict(SCHEMA_PATH.read_bytes()))


class Plan(Strict):
    schema_version: Literal["F_AVAILABILITY_PLAN_V1"] = "F_AVAILABILITY_PLAN_V1"
    evidence_class: Literal["GENUINE_NATIVE", "SYNTHETIC_NETWORK_QA"]
    source_sha256: str
    executable_sha256: str
    config_sha256: str
    rights_sha256: str
    created_ms: int
    start_ms: int
    availability_start_ms: int
    end_ms: int
    required_symbols: list[str]
    auditor_key_id: str


class PlanEnvelope(Strict):
    grant: Plan
    key_id: str
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_base64: str


class TimedAuditBody(Strict):
    schema_version: Literal["F_CAPTURE_AUDIT_V1"] = "F_CAPTURE_AUDIT_V1"
    session_id: str
    terminal_sha256: str
    terminal_event_sha256: str
    grant_sha256: str
    raw_normalized_prefix_sha256: str
    independently_verified_reference: str
    audited_ms: int
    host_admission_sha256: str


class TimedAuditEnvelope(Strict):
    grant: TimedAuditBody
    key_id: str
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_base64: str


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        require(
            not any(p.is_symlink() for p in (self.path, *self.path.absolute().parents)),
            "QUALIFICATION_PATH_UNTRUSTED",
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""CREATE TABLE IF NOT EXISTS evidence(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,
               body BLOB NOT NULL,previous TEXT NOT NULL,hash TEXT UNIQUE NOT NULL);
               CREATE TRIGGER IF NOT EXISTS evidence_u BEFORE UPDATE ON evidence BEGIN SELECT RAISE(ABORT,'IMMUTABLE');END;
               CREATE TRIGGER IF NOT EXISTS evidence_d BEFORE DELETE ON evidence BEGIN SELECT RAISE(ABORT,'IMMUTABLE');END;""")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA synchronous=FULL")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def append(self, kind, value):
        if kind == "BLOCKED" and value in self.values("BLOCKED"):
            return digest(value)
        self.verify()
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT hash FROM evidence ORDER BY seq DESC LIMIT 1").fetchone()
            previous = row[0] if row else "0" * 64
            identity = digest([kind, previous, value])
            db.execute(
                "INSERT INTO evidence(kind,body,previous,hash) VALUES(?,?,?,?)",
                (kind, canonical(value), previous, identity),
            )
        return identity

    def verify(self):
        previous = "0" * 64
        with self.db() as db:
            for kind, raw, parent, identity in db.execute(
                "SELECT kind,body,previous,hash FROM evidence ORDER BY seq"
            ):
                require(
                    parent == previous and digest([kind, parent, strict(raw)]) == identity,
                    "QUALIFICATION_CHAIN_TAMPER",
                )
                previous = identity
        return previous

    def values(self, kind):
        self.verify()
        with self.db() as db:
            return [
                strict(raw)
                for (raw,) in db.execute("SELECT body FROM evidence WHERE kind=? ORDER BY seq", (kind,))
            ]

    def register(self, owner, auditor, roots, *, qa=False, observed_ms=None):
        p = owner.grant
        require(not self.values("PLAN"), "PLAN_ALREADY_REGISTERED")
        require(
            p.evidence_class == ("SYNTHETIC_NETWORK_QA" if qa else "GENUINE_NATIVE"),
            "EVIDENCE_CLASS_MISMATCH",
        )
        key1 = verify_key(owner, roots.get("owner", {}))
        key2 = verify_key(auditor, roots.get("auditor", {}))
        require(
            owner.grant == auditor.grant and key1 != key2 and auditor.key_id == p.auditor_key_id,
            "PLAN_INDEPENDENT_SIGNATURES",
        )
        persisted = observed_ms if qa else time.time_ns() // 1000000
        require(
            type(persisted) is int
            and 0 < p.created_ms <= persisted < p.start_ms <= p.availability_start_ms < p.end_ms,
            "PLAN_NOT_PREDECLARED",
        )
        require(
            p.end_ms - p.availability_start_ms == 7 * 86400000
            and p.required_symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "AVAILABILITY_DENOMINATOR_SCOPE",
        )
        return self.append(
            "PLAN",
            {
                "owner": owner.model_dump(mode="json"),
                "auditor": auditor.model_dump(mode="json"),
                "persisted_ms": persisted,
                "evidence_class": p.evidence_class,
            },
        )

    def attach_audit(self, journal, envelope, roots, *, qa=False):
        from ..native.audit import verify_capture_audit

        session = envelope.grant.session_id
        verify_capture_audit(journal, session, envelope, roots, synthetic=qa)
        return self.append(
            "CAPTURE_AUDIT", {"session": session, "envelope": envelope.model_dump(mode="json")}
        )

    def transition(self, cohort, stage, proof, evidence_class):
        require(stage in STAGES, "UNKNOWN_STAGE")
        existing = [r for r in self.values("TRANSITION") if r["cohort"] == cohort]
        wanted = {
            "cohort": cohort,
            "stage": stage,
            "proof_sha256": digest(proof),
            "evidence_class": evidence_class,
        }
        for row in existing:
            if row["stage"] == stage:
                require(row == wanted, "IMMUTABLE_QUALIFICATION_CONFLICT")
                return
        require(len(existing) == STAGES.index(stage), "QUALIFICATION_STAGE_SKIP")
        self.append("TRANSITION", wanted)

    def attach_host(self, journal, session, envelope, roots, *, qa=False):
        from ..native.contract import Grant
        from .admission import verify_host

        with journal.db() as db:
            g = Grant.model_validate_json(
                db.execute("SELECT grant_json FROM sessions WHERE id=?", (session,)).fetchone()[0]
            )
        verify_host(
            envelope,
            roots,
            g,
            envelope.grant.native_clock_probes[-1]["receive_wall_ms"] + 1,
            qa=qa,
            historical=True,
        )
        return self.append(
            "HOST_ADMISSION", {"session": session, "envelope": envelope.model_dump(mode="json")}
        )
