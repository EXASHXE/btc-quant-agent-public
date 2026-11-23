"""Detached independent capture-auditor verification; never grants Source qualification."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from .contract import Strict, digest, require, strict, verify_key


class CaptureAuditBody(Strict):
    schema_version: Literal["E_CAPTURE_AUDIT_V1"] = "E_CAPTURE_AUDIT_V1"
    session_id: str
    terminal_sha256: str
    terminal_event_sha256: str
    grant_sha256: str
    raw_normalized_prefix_sha256: str
    independently_verified_reference: str


class CaptureAuditEnvelope(Strict):
    grant: CaptureAuditBody
    key_id: str
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_base64: str


def challenge(journal, session):
    journal.verify()
    with journal.db() as db:
        grant_json = db.execute("SELECT grant_json FROM sessions WHERE id=?", (session,)).fetchone()
        require(grant_json is not None, "SESSION_MISSING")
        grant = strict(grant_json[0])
        terminal = db.execute(
            "SELECT hash FROM events WHERE session=? AND kind='TERMINAL' ORDER BY seq DESC LIMIT 1",
            (session,),
        ).fetchone()
        require(terminal is not None, "TERMINAL_MISSING")
    path = Path(grant["output"]) / "terminal.json"
    require(path.is_file() and not path.is_symlink(), "TERMINAL_REPORT_UNTRUSTED")
    records = journal.records(session)
    return {
        "session_id": session,
        "terminal_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "terminal_event_sha256": terminal[0],
        "grant_sha256": digest(grant),
        "raw_normalized_prefix_sha256": digest(records),
    }


def verify_capture_audit(journal, session, envelope, roots, *, synthetic=False):
    if not synthetic:
        installed = strict((Path(__file__).parent / "authority_roots.json").read_bytes())
        require(roots == installed, "INSTALLED_INDEPENDENT_TRUST_REQUIRED")
    public = verify_key(envelope, roots.get("auditor", {}))
    require(
        public and envelope.grant.independently_verified_reference, "INDEPENDENT_CAPTURE_REFERENCE_REQUIRED"
    )
    with journal.db() as db:
        grant = strict(db.execute("SELECT grant_json FROM sessions WHERE id=?", (session,)).fetchone()[0])
    require(envelope.key_id == grant["auditor_key_id"], "CAPTURE_AUDITOR_SCOPE_MISMATCH")
    expected = challenge(journal, session)
    value = envelope.grant.model_dump(mode="json")
    require(all(value[k] == v for k, v in expected.items()), "CAPTURE_AUDIT_BINDING_MISMATCH")
    return {
        "status": "INDEPENDENT_AUDIT_SIGNATURE_VALID_SYNTHETIC_ONLY"
        if synthetic
        else "INDEPENDENT_AUDIT_SIGNATURE_VALID",
        "source_qualified": False,
        "shadow_qualified": False,
        "economically_validated": False,
        "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
    }
