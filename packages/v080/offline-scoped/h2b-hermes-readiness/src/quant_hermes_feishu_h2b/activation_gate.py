"""Default-deny capability gates, detached Owner/Controller binding, and local revocation for H2-B."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quant_hermes_feishu_h1.contract import canonical_json_strict, canonical_sha256_strict

from .constants import (
    ACCEPTED_H1_WHEEL_SHA256,
    H2B_CAPABILITIES,
    H2B_TASK_ID,
    LIVE_CAPABILITY_ERROR,
    LIVE_CAPABILITY_EXIT_CODE,
    LIVE_FEISHU_ERROR,
    LIVE_MODEL_ERROR,
)

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    HAS_ED25519 = True
except ImportError:
    HAS_ED25519 = False
    InvalidSignature = Exception  # type: ignore[misc, assignment]
    Ed25519PublicKey = None  # type: ignore[misc, assignment]

ENROLLMENT_LINE_PREFIX = "H2B_ENROLLMENT_V1 "
OWNER_SIGN_DOMAIN = "QUANT-H2B-V1/owner:"
CONTROLLER_SIGN_DOMAIN = "QUANT-H2B-V1/controller:"

FORBIDDEN_BYPASS_ENV_VARS: tuple[str, ...] = (
    "QUANT_H2B_ALLOW_LIVE",
    "QUANT_H2B_BYPASS_GATE",
    "HERMES_BYPASS_FEISHU_GATE",
    "FEISHU_LIVE_OVERRIDE",
)


class GateDenialError(RuntimeError):
    """Fail-closed exception raised when any live Feishu, model, or capability gate is denied."""

    def __init__(self, code: str, message: str, *, exit_code: int = LIVE_CAPABILITY_EXIT_CODE) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


@dataclass(frozen=True)
class H2BTrustRoot:
    """Compiled-in or test-scoped trust root binding exact release, identities, principal, and anchor."""

    live_enabled: bool = False
    release_wheel_sha256: str | None = None
    h1_wheel_sha256: str = ACCEPTED_H1_WHEEL_SHA256
    app_id: str | None = None
    tenant_key: str | None = None
    owner_open_id: str | None = None
    authorized_dm_chat_id: str | None = None
    runtime_uid: int | None = None
    sender_id: str | None = None
    outbox_db_path: str | None = None
    revocation_db_path: str | None = None
    kill_switch_path: str | None = None
    enrollment_anchor_path: str | None = None
    enrollment_anchor_sha256: str | None = None
    owner_ed25519_public_hex: str | None = None
    controller_ed25519_public_hex: str | None = None
    require_ed25519_signatures: bool = True
    allowed_capabilities: frozenset[str] = frozenset()
    allowed_model_auth_scope: str = "NONE"


# Shipping trust root is deliberately inactive (default-deny).
PRODUCTION_TRUST_ROOT = H2BTrustRoot()


@dataclass(frozen=True)
class H2BApprovalClaim:
    """Canonical claim jointly reviewed by Owner and Controller 0-C for a bounded live grant."""

    capability: str
    run_id: str
    task_id: str = H2B_TASK_ID
    release_wheel_sha256: str = ""
    h1_wheel_sha256: str = ACCEPTED_H1_WHEEL_SHA256
    app_id: str = ""
    tenant_key: str = ""
    owner_open_id: str = ""
    authorized_dm_chat_id: str = ""
    runtime_uid: int = -1
    sender_id: str = ""
    outbox_db_path: str = ""
    model_auth_scope: str = "NONE"
    not_before_ms: int = 0
    expires_ms: int = 0
    max_outbound_messages: int = 1
    max_inbound_turns: int = 0
    single_smoke_test_only: bool = True

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "authorized_dm_chat_id": self.authorized_dm_chat_id,
            "capability": self.capability,
            "expires_ms": self.expires_ms,
            "h1_wheel_sha256": self.h1_wheel_sha256,
            "max_inbound_turns": self.max_inbound_turns,
            "max_outbound_messages": self.max_outbound_messages,
            "model_auth_scope": self.model_auth_scope,
            "not_before_ms": self.not_before_ms,
            "outbox_db_path": self.outbox_db_path,
            "owner_open_id": self.owner_open_id,
            "release_wheel_sha256": self.release_wheel_sha256,
            "run_id": self.run_id,
            "runtime_uid": self.runtime_uid,
            "sender_id": self.sender_id,
            "single_smoke_test_only": self.single_smoke_test_only,
            "task_id": self.task_id,
            "tenant_key": self.tenant_key,
        }

    def digest_sha256(self) -> str:
        return canonical_sha256_strict(self.canonical_dict())


@dataclass(frozen=True)
class H2BActivationGrant:
    """Bounded grant carrying distinct Owner and Controller approvals over an immutable claim."""

    claim: H2BApprovalClaim
    owner_approval_hex: str | None = None
    controller_approval_hex: str | None = None
    owner_claim_sha256: str | None = None
    controller_claim_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class H2BRevocationStore:
    """Persistent append-only local revocation ledger and bounded grant consumption counter."""

    def __init__(self, db_path: Path, *, kill_switch_path: Path | None = None) -> None:
        self.db_path = Path(db_path).resolve()
        self.kill_switch_path = Path(kill_switch_path).resolve() if kill_switch_path else None
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.db_path.parent, 0o700)
        except OSError:
            pass
        with self._connect(write=True) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS h2b_revocations (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    revoked_by TEXT NOT NULL,
                    revoked_at_ms INTEGER NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS h2b_grant_usage (
                    run_id TEXT PRIMARY KEY,
                    capability TEXT NOT NULL,
                    max_count INTEGER NOT NULL,
                    used_count INTEGER NOT NULL,
                    first_used_ms INTEGER NOT NULL,
                    last_used_ms INTEGER NOT NULL
                )"""
            )
            for op in ("UPDATE", "DELETE"):
                db.execute(
                    f"CREATE TRIGGER IF NOT EXISTS lock_h2b_revocations_{op} "
                    f"BEFORE {op} ON h2b_revocations "
                    "BEGIN SELECT RAISE(ABORT, 'H2B_REVOCATION_APPEND_ONLY'); END"
                )
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    @contextmanager
    def _connect(self, *, write: bool = False):
        conn = sqlite3.connect(str(self.db_path), timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            if write:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = FULL")
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            if write:
                conn.execute("COMMIT")
        except BaseException:
            if write and conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def write_kill_switch(self, *, reason: str, ts_ms: int) -> Path:
        """Persist an emergency local kill-switch file that disables live Feishu operations immediately."""
        if self.kill_switch_path is None:
            raise GateDenialError(LIVE_FEISHU_ERROR, "Kill switch path is not configured")
        self.kill_switch_path.parent.mkdir(parents=True, exist_ok=True)
        payload = canonical_json_strict({"disabled": True, "reason": reason, "ts_ms": ts_ms}) + "\n"
        self.kill_switch_path.write_text(payload, encoding="utf-8")
        try:
            os.chmod(self.kill_switch_path, 0o600)
        except OSError:
            pass
        return self.kill_switch_path

    def revoke(self, *, scope: str, target_id: str, reason: str, revoked_by: str, ts_ms: int) -> None:
        with self._lock, self._connect(write=True) as db:
            db.execute(
                "INSERT INTO h2b_revocations(scope, target_id, reason, revoked_by, revoked_at_ms) "
                "VALUES (?, ?, ?, ?, ?)",
                (scope, target_id, reason, revoked_by, ts_ms),
            )

    def is_revoked(self, *, run_id: str, app_id: str, capability: str) -> str | None:
        if self.kill_switch_path is not None and self.kill_switch_path.exists():
            return f"KILL_SWITCH_ACTIVE:{self.kill_switch_path.name}"
        with self._lock, self._connect(write=False) as db:
            row = db.execute(
                """SELECT scope, target_id, reason FROM h2b_revocations
                   WHERE (scope = 'GLOBAL' AND target_id = '*')
                      OR (scope = 'RUN' AND target_id = ?)
                      OR (scope = 'APP' AND target_id = ?)
                      OR (scope = 'CAPABILITY' AND target_id = ?)
                   ORDER BY seq DESC LIMIT 1""",
                (run_id, app_id, capability),
            ).fetchone()
            if row is not None:
                return f"REVOKED:{row['scope']}:{row['reason']}"
        return None

    def consume_run_quota(self, *, run_id: str, capability: str, max_count: int, now_ms: int) -> int:
        if max_count <= 0:
            raise GateDenialError(LIVE_CAPABILITY_ERROR, f"Zero quota configured for capability {capability}")
        with self._lock, self._connect(write=True) as db:
            row = db.execute(
                "SELECT used_count, max_count FROM h2b_grant_usage WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO h2b_grant_usage(run_id, capability, max_count, used_count, first_used_ms, last_used_ms) "
                    "VALUES (?, ?, ?, 1, ?, ?)",
                    (run_id, capability, max_count, now_ms, now_ms),
                )
                return 1
            used = int(row["used_count"])
            limit = min(int(row["max_count"]), max_count)
            if used >= limit:
                raise GateDenialError(
                    LIVE_CAPABILITY_ERROR,
                    f"Grant run_id={run_id} exhausted ({used}/{limit}); one smoke test never grants recurring access",
                )
            new_used = used + 1
            db.execute(
                "UPDATE h2b_grant_usage SET used_count = ?, last_used_ms = ? WHERE run_id = ?",
                (new_used, now_ms, run_id),
            )
            return new_used


def reject_consumer_subscription_entitlement(provider_claim: str) -> None:
    """Explicitly reject consumer ChatGPT/Google AI Pro subscriptions as API/OAuth entitlements."""
    lower = provider_claim.strip().lower()
    if any(
        tok in lower
        for tok in ("chatgpt_plus", "chatgpt_pro", "google_ai_pro", "consumer_subscription", "plus_subscription")
    ):
        raise GateDenialError(
            LIVE_MODEL_ERROR,
            "Consumer ChatGPT or Google AI Pro subscription does not grant provider API or OAuth entitlement",
        )


def _error_code_for_capability(capability: str) -> str:
    if capability == "MODEL_EXPLANATION_OPTIONAL":
        return LIVE_MODEL_ERROR
    if capability.startswith("FEISHU_"):
        return LIVE_FEISHU_ERROR
    return LIVE_CAPABILITY_ERROR


def verify_enrollment_anchor(anchor_path: Path, expected_sha256: str) -> None:
    """Verify protected regular enrollment anchor file exists, is not symlink/world-writable, and matches SHA-256."""
    if anchor_path.is_symlink() or not anchor_path.exists() or not anchor_path.is_file():
        raise GateDenialError(LIVE_FEISHU_ERROR, f"Enrollment anchor invalid or missing: {anchor_path}")
    mode = stat.S_IMODE(anchor_path.stat().st_mode)
    if mode & 0o077:
        raise GateDenialError(LIVE_FEISHU_ERROR, f"Enrollment anchor permissions too permissive: {oct(mode)}")
    raw = anchor_path.read_bytes()
    first_line = raw.decode("utf-8").splitlines()[0] + "\n"
    if not first_line.startswith(ENROLLMENT_LINE_PREFIX):
        raise GateDenialError(LIVE_FEISHU_ERROR, "Enrollment anchor missing H2B_ENROLLMENT_V1 header")
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha256:
        raise GateDenialError(LIVE_FEISHU_ERROR, "Enrollment anchor SHA-256 mismatch")


def _verify_detached_approvals(trust_root: H2BTrustRoot, grant: H2BActivationGrant) -> None:
    claim_sha = grant.claim.digest_sha256()
    if trust_root.require_ed25519_signatures:
        if not HAS_ED25519:
            raise GateDenialError(
                LIVE_FEISHU_ERROR,
                "Ed25519 verification library (cryptography) unavailable for dual-signature gate",
            )
        if not trust_root.owner_ed25519_public_hex or not trust_root.controller_ed25519_public_hex:
            raise GateDenialError(LIVE_FEISHU_ERROR, "Production public verification keys not provisioned")
        if trust_root.owner_ed25519_public_hex == trust_root.controller_ed25519_public_hex:
            raise GateDenialError(LIVE_FEISHU_ERROR, "Owner and Controller public keys must be distinct")
        if not grant.owner_approval_hex or not grant.controller_approval_hex:
            raise GateDenialError(LIVE_FEISHU_ERROR, "Missing detached Owner or Controller Ed25519 signature")
        try:
            owner_pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(trust_root.owner_ed25519_public_hex))
            ctrl_pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(trust_root.controller_ed25519_public_hex))
            owner_pub.verify(bytes.fromhex(grant.owner_approval_hex), f"{OWNER_SIGN_DOMAIN}{claim_sha}".encode("ascii"))
            ctrl_pub.verify(
                bytes.fromhex(grant.controller_approval_hex),
                f"{CONTROLLER_SIGN_DOMAIN}{claim_sha}".encode("ascii"),
            )
        except (ValueError, InvalidSignature) as exc:
            raise GateDenialError(LIVE_FEISHU_ERROR, f"Detached dual signature verification failed: {exc}") from exc
    else:
        if grant.owner_claim_sha256 != claim_sha or grant.controller_claim_sha256 != claim_sha:
            raise GateDenialError(LIVE_FEISHU_ERROR, "Detached Owner/Controller approval digest mismatch")


class H2BActivationGate:
    """Default-deny gate binding H2-B release, identities, dual approvals, quotas, and local revocation."""

    def __init__(
        self,
        *,
        trust_root: H2BTrustRoot = PRODUCTION_TRUST_ROOT,
        grant: H2BActivationGrant | None = None,
        revocation_store: H2BRevocationStore | None = None,
        observed_release_wheel_sha256: str | None = None,
        observed_h1_wheel_sha256: str = ACCEPTED_H1_WHEEL_SHA256,
    ) -> None:
        self._trust_root = trust_root
        self._grant = grant
        self._revocation_store = revocation_store
        self._observed_release_wheel_sha256 = observed_release_wheel_sha256
        self._observed_h1_wheel_sha256 = observed_h1_wheel_sha256

    def authorize_capability(
        self,
        capability: str,
        *,
        app_id: str,
        tenant_key: str,
        recipient_open_id: str,
        chat_id: str,
        sender_id: str,
        outbox_path: Path | str,
        now_ms: int | None = None,
        model_auth_scope: str = "NONE",
        consume_quota: bool = False,
    ) -> dict[str, Any]:
        """Verify all trust-root, claim, dual-approval, expiry, revocation, and quota bounds."""
        err_code = _error_code_for_capability(capability)
        if capability not in H2B_CAPABILITIES:
            raise GateDenialError(LIVE_CAPABILITY_ERROR, f"Unknown H2-B capability: {capability!r}")

        # Environment variables never bypass a disabled trust root; log/fail closed unconditionally.
        if not self._trust_root.live_enabled:
            raise GateDenialError(
                err_code,
                f"Live capability {capability} denied: PRODUCTION_TRUST_ROOT is inactive (default-deny)",
            )

        if capability == "MODEL_EXPLANATION_OPTIONAL" and model_auth_scope == "NONE":
            raise GateDenialError(LIVE_MODEL_ERROR, "Model explanation gate requires an explicit model_auth_scope")
        if model_auth_scope != "NONE":
            reject_consumer_subscription_entitlement(model_auth_scope)

        tr = self._trust_root
        if capability not in tr.allowed_capabilities:
            raise GateDenialError(err_code, f"Capability {capability} not enabled in trust root")
        if self._grant is None:
            raise GateDenialError(err_code, "No detached Owner/Controller grant supplied")
        if not tr.release_wheel_sha256 or tr.release_wheel_sha256 != self._observed_release_wheel_sha256:
            raise GateDenialError(err_code, "H2-B release wheel SHA-256 mismatch or unprovisioned")
        if tr.h1_wheel_sha256 != ACCEPTED_H1_WHEEL_SHA256 or tr.h1_wheel_sha256 != self._observed_h1_wheel_sha256:
            raise GateDenialError(err_code, "H1 baseline wheel SHA-256 mismatch")

        current_uid = os.getuid()
        if tr.runtime_uid is None or tr.runtime_uid != current_uid:
            raise GateDenialError(err_code, f"Runtime UID {current_uid} does not match provisioned UID {tr.runtime_uid}")

        resolved_outbox = str(Path(outbox_path).resolve())
        claim = self._grant.claim
        expected_pairs = (
            ("capability", claim.capability, capability),
            ("app_id", tr.app_id, app_id),
            ("claim.app_id", claim.app_id, app_id),
            ("tenant_key", tr.tenant_key, tenant_key),
            ("claim.tenant_key", claim.tenant_key, tenant_key),
            ("owner_open_id", tr.owner_open_id, recipient_open_id),
            ("claim.owner_open_id", claim.owner_open_id, recipient_open_id),
            ("authorized_dm_chat_id", tr.authorized_dm_chat_id, chat_id),
            ("claim.authorized_dm_chat_id", claim.authorized_dm_chat_id, chat_id),
            ("sender_id", tr.sender_id, sender_id),
            ("claim.sender_id", claim.sender_id, sender_id),
            ("outbox_db_path", tr.outbox_db_path, resolved_outbox),
            ("claim.outbox_db_path", claim.outbox_db_path, resolved_outbox),
            ("release_wheel_sha256", claim.release_wheel_sha256, tr.release_wheel_sha256),
            ("h1_wheel_sha256", claim.h1_wheel_sha256, tr.h1_wheel_sha256),
            ("runtime_uid", claim.runtime_uid, tr.runtime_uid),
            ("model_auth_scope", claim.model_auth_scope, model_auth_scope),
            ("root.model_auth_scope", tr.allowed_model_auth_scope, model_auth_scope),
        )
        for label, left, right in expected_pairs:
            if left is None or left == "" or left != right:
                raise GateDenialError(err_code, f"Binding check failed on {label}")

        ts = now_ms if now_ms is not None else time.time_ns() // 1_000_000
        if ts < claim.not_before_ms or ts >= claim.expires_ms:
            raise GateDenialError(err_code, "Activation grant outside authorized validity window")

        if tr.kill_switch_path and Path(tr.kill_switch_path).exists():
            raise GateDenialError(err_code, f"Emergency kill switch active at {tr.kill_switch_path}")
        if not tr.enrollment_anchor_path or not tr.enrollment_anchor_sha256:
            raise GateDenialError(err_code, "Enrollment anchor not provisioned")
        verify_enrollment_anchor(Path(tr.enrollment_anchor_path), tr.enrollment_anchor_sha256)

        _verify_detached_approvals(tr, self._grant)

        if self._revocation_store is None:
            raise GateDenialError(err_code, "Revocation ledger is mandatory when live_enabled=True")
        rev_reason = self._revocation_store.is_revoked(run_id=claim.run_id, app_id=app_id, capability=capability)
        if rev_reason is not None:
            raise GateDenialError(err_code, f"Capability revoked locally: {rev_reason}")

        used = None
        if consume_quota:
            max_cnt = claim.max_outbound_messages if capability == "FEISHU_OUTBOUND_DM_ONCE" else claim.max_inbound_turns
            used = self._revocation_store.consume_run_quota(
                run_id=claim.run_id,
                capability=capability,
                max_count=max_cnt,
                now_ms=ts,
            )

        return {
            "authorized": True,
            "capability": capability,
            "run_id": claim.run_id,
            "claim_sha256": claim.digest_sha256(),
            "quota_used": used,
        }
