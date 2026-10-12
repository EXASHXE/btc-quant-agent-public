"""AuthenticatedHumanPort: Ed25519 cryptographic operator decision verification & trust translation.

Replaces unauthenticated TRUSTED_HUMAN_FIXTURE sidecar input trust with RFC 8032 Ed25519
signature verification against pinned operator public keys, 12-attribute context binding,
and durable fsynced nonce/receipt journaling before materializing a sealed G1 fixture.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

from scripts.g1_offline_preview_r1.model import (
    SafetyViolation,
    canonical,
    decimal,
    digest,
    exact,
    timestamp,
)
from scripts.g1_offline_preview_r1.storage import strict_json

from .crypto_ed25519 import (
    PINNED_OPERATOR_KEYRING,
    SYNTHETIC_TEST_OPERATOR_SEEDS,
    canonical_signing_bytes,
    ed25519_sign,
    ed25519_verify,
)
from .no_order_port import guard_scratch_dir

DEFAULT_WORKTREE_ID = "gemini-g1g3-offline-ports-r1"
DEFAULT_ROUTE_ID = "g1g3-offline-loopback-route-v1"
REQUIRED_ENVIRONMENT = "OFFLINE_PREVIEW"
APPROVAL_CLASS = "OPERATOR_EXPLICIT_APPROVAL_V1"
REJECTION_CLASS = "OPERATOR_EXPLICIT_REJECTION_V1"

SIGNING_BODY_KEYS = {
    "schema_version",
    "token_id",
    "signal_id",
    "proposal_hash",
    "version",
    "side",
    "quantity",
    "issued_at",
    "expires_at",
    "operator_id",
    "environment",
    "context_hash",
    "approval_nonce",
    "key_id",
    "decision_class",
}

DECISION_ENVELOPE_KEYS = SIGNING_BODY_KEYS | {
    "signature_alg",
    "signature",
}


def compute_operator_context_hash(
    *,
    source_hash: str,
    proposal_hash: str,
    analysis_hash: str,
    worktree_id: str = DEFAULT_WORKTREE_ID,
    route_id: str = DEFAULT_ROUTE_ID,
    process_epoch: int = 1,
) -> str:
    """Compute canonical SHA-256 context_hash binding source, proposal, analysis, route, worktree, epoch."""
    if type(process_epoch) is not int or process_epoch < 1:
        raise SafetyViolation("APPROVAL_PRIOR_PROCESS_SEQUENCE")
    return digest(
        {
            "source_hash": source_hash,
            "proposal_hash": proposal_hash,
            "analysis_hash": analysis_hash,
            "worktree_id": worktree_id,
            "route_id": route_id,
            "process_epoch": process_epoch,
        }
    )


def sign_synthetic_operator_decision(
    *,
    token_id: str,
    signal_id: str,
    proposal_hash: str,
    version: int = 1,
    side: str = "LONG",
    quantity: str = "0.01",
    issued_at: int = 60002,
    expires_at: int = 160000,
    operator_id: str = "op-alpha",
    key_id: str = "ed25519-offline-op-alpha-v1",
    environment: str = REQUIRED_ENVIRONMENT,
    context_hash: str,
    approval_nonce: str,
    decision_class: str = APPROVAL_CLASS,
    seed_override: bytes | None = None,
) -> dict[str, Any]:
    """Create a synthetic test-signed SignedOperatorDecisionV1 using ephemeral test seeds."""
    seed = seed_override if seed_override is not None else SYNTHETIC_TEST_OPERATOR_SEEDS.get(key_id)
    if seed is None:
        raise ValueError(f"Unknown synthetic test seed for key_id={key_id}")
    body = {
        "schema_version": 1,
        "token_id": token_id,
        "signal_id": signal_id,
        "proposal_hash": proposal_hash,
        "version": version,
        "side": side,
        "quantity": quantity,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "operator_id": operator_id,
        "environment": environment,
        "context_hash": context_hash,
        "approval_nonce": approval_nonce,
        "key_id": key_id,
        "decision_class": decision_class,
    }
    sig = ed25519_sign(seed, canonical_signing_bytes(body)).hex()
    return {
        **body,
        "signature_alg": "ED25519_RFC8032_V1",
        "signature": sig,
    }


def _text_safe(value: Any, code: str, max_len: int = 128) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len:
        raise SafetyViolation(code)
    lowered = value.lower()
    if any(w in lowered for w in ("api_key", "secret", "password", "bearer ", "token=")):
        raise SafetyViolation("SECRET_IN_OPERATOR_DECISION")
    return value


class AuthenticatedHumanPort:
    """Cryptographic human decision verifier and durable trust-boundary translator."""

    def __init__(
        self,
        storage_dir: str | Path,
        *,
        keyring: dict[str, dict[str, str]] | None = None,
        worktree_id: str = DEFAULT_WORKTREE_ID,
        route_id: str = DEFAULT_ROUTE_ID,
        process_epoch: int = 1,
        temporary: bool = False,
    ) -> None:
        if type(process_epoch) is not int or process_epoch < 1:
            raise SafetyViolation("APPROVAL_PRIOR_PROCESS_SEQUENCE")
        self.root = guard_scratch_dir(storage_dir, temporary=temporary)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.wal_path = self.root / "operator_receipts.wal.jsonl"
        if self.wal_path.is_symlink():
            raise SafetyViolation("PATH_SYMLINK")
        self.keyring = copy.deepcopy(PINNED_OPERATOR_KEYRING if keyring is None else keyring)
        self.worktree_id = worktree_id
        self.route_id = route_id
        self.process_epoch = process_epoch
        self.used_nonces: set[str] = set()
        self.used_token_ids: set[str] = set()
        self.max_seen_epoch: int = process_epoch
        self.receipts_by_proposal: dict[tuple[str, str], dict[str, Any]] = {}
        self.chain: str = digest({"wal": "OPERATOR_AUTH_WAL_V1", "worktree": worktree_id})
        self.seq: int = 0
        self._recover_wal()

    def _recover_wal(self) -> None:
        if not self.wal_path.exists():
            fd = os.open(self.wal_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                header = (
                    canonical({"format": "OPERATOR_AUTH_WAL_V1", "genesis_chain": self.chain})
                    + "\n"
                ).encode("utf-8")
                os.write(fd, header)
                os.fsync(fd)
            finally:
                os.close(fd)
            return

        raw = self.wal_path.read_bytes()
        if not raw.endswith(b"\n"):
            raise SafetyViolation("OPERATOR_WAL_TRUNCATED")
        lines = raw.decode("utf-8").splitlines()
        if not lines or strict_json(lines[0]) != {
            "format": "OPERATOR_AUTH_WAL_V1",
            "genesis_chain": self.chain,
        }:
            raise SafetyViolation("OPERATOR_WAL_GENESIS_MISMATCH")
        for line in lines[1:]:
            rec = strict_json(line)
            exact(
                rec,
                {
                    "seq",
                    "previous",
                    "receipt",
                    "receipt_hash",
                    "record_hash",
                },
                "OPERATOR_WAL_SCHEMA",
            )
            body = {k: v for k, v in rec.items() if k != "record_hash"}
            if (
                rec["seq"] != self.seq + 1
                or rec["previous"] != self.chain
                or digest(body) != rec["record_hash"]
            ):
                raise SafetyViolation("OPERATOR_WAL_CHAIN_CORRUPT")
            receipt = rec["receipt"]
            if digest(receipt) != rec["receipt_hash"]:
                raise SafetyViolation("OPERATOR_WAL_RECEIPT_HASH_MISMATCH")
            nonce = receipt["approval_nonce"]
            if nonce in self.used_nonces:
                raise SafetyViolation("OPERATOR_WAL_DUPLICATE_NONCE")
            self.used_nonces.add(nonce)
            self.used_token_ids.add(receipt["token_id"])
            self.max_seen_epoch = max(self.max_seen_epoch, int(receipt["process_epoch"]))
            self.receipts_by_proposal[(receipt["signal_id"], receipt["proposal_hash"])] = receipt
            self.seq = rec["seq"]
            self.chain = rec["record_hash"]

    def rebind_route(self, new_route_id: str) -> None:
        """Update active route_id (invalidating any previously signed context_hash)."""
        self.route_id = _text_safe(new_route_id, "APPROVAL_ROUTE_OR_WORKTREE_MISMATCH")

    def advance_process_epoch(self, new_epoch: int) -> None:
        if type(new_epoch) is not int or new_epoch <= self.process_epoch:
            raise SafetyViolation("APPROVAL_PRIOR_PROCESS_SEQUENCE")
        self.process_epoch = new_epoch
        self.max_seen_epoch = max(self.max_seen_epoch, new_epoch)

    def reject_unauthenticated_fixture(self, raw_fixture: dict[str, Any]) -> None:
        """Reject any raw input fixture that attempts to smuggle pre-populated trusted_approvals."""
        if not isinstance(raw_fixture, dict):
            raise SafetyViolation("FIXTURE_SCHEMA")
        if raw_fixture.get("trusted_approvals"):
            raise SafetyViolation("RAW_FIXTURE_TRUST_REJECTED")

    def verify_decision(
        self,
        decision: Any,
        *,
        proposal: dict[str, Any],
        analysis: dict[str, Any] | None,
        analysis_at: int | None,
        approve_at: int,
        decision_epoch: int | None = None,
        decision_worktree_id: str | None = None,
        decision_route_id: str | None = None,
        hook: Any | None = None,
    ) -> dict[str, Any]:
        """Verify SignedOperatorDecisionV1 and append durable receipt to operator WAL."""
        if not isinstance(decision, dict):
            raise SafetyViolation("APPROVAL_MISSING_EXPLICIT_HUMAN_SIGNATURE")
        if decision.get("issuer") == "TRUSTED_HUMAN_FIXTURE" and "signature" not in decision:
            raise SafetyViolation("RAW_FIXTURE_TRUST_REJECTED")
        exact(decision, DECISION_ENVELOPE_KEYS, "APPROVAL_SCHEMA_INVALID")

        if type(decision["schema_version"]) is not int or decision["schema_version"] != 1:
            raise SafetyViolation("APPROVAL_SCHEMA_INVALID")

        token_id = _text_safe(decision["token_id"], "APPROVAL_TOKEN_INVALID")
        signal_id = _text_safe(decision["signal_id"], "APPROVAL_PROPOSAL_DRIFT")
        proposal_hash = _text_safe(decision["proposal_hash"], "APPROVAL_PROPOSAL_DRIFT")
        operator_id = _text_safe(decision["operator_id"], "APPROVAL_KEY_UNTRUSTED")
        key_id = _text_safe(decision["key_id"], "APPROVAL_KEY_UNTRUSTED")
        nonce = _text_safe(decision["approval_nonce"], "APPROVAL_NONCE_INVALID")
        env = _text_safe(decision["environment"], "APPROVAL_ENVIRONMENT_INVALID")
        decision_class = _text_safe(decision["decision_class"], "APPROVAL_CLASS_INVALID")

        # 1. Environment check
        if env != REQUIRED_ENVIRONMENT:
            raise SafetyViolation("APPROVAL_ENVIRONMENT_INVALID")

        # 2. Decision class check
        if decision_class not in (APPROVAL_CLASS, REJECTION_CLASS):
            raise SafetyViolation("APPROVAL_CLASS_INVALID")

        # 3. Keyring & operator identity check
        if decision["signature_alg"] != "ED25519_RFC8032_V1":
            raise SafetyViolation("APPROVAL_SIGNATURE_INVALID")
        key_entry = self.keyring.get(key_id)
        if key_entry is None:
            raise SafetyViolation("APPROVAL_KEY_UNTRUSTED")
        if key_entry.get("status") != "ACTIVE":
            raise SafetyViolation("APPROVAL_KEY_REVOKED")
        if key_entry.get("operator_id") != operator_id:
            raise SafetyViolation("APPROVAL_OPERATOR_KEY_MISMATCH")
        if key_entry.get("environment") != REQUIRED_ENVIRONMENT:
            raise SafetyViolation("APPROVAL_ENVIRONMENT_INVALID")

        # 4. Cryptographic Ed25519 signature verification over canonical signing body
        sig_hex = decision["signature"]
        if not isinstance(sig_hex, str) or len(sig_hex) != 128:
            raise SafetyViolation("APPROVAL_SIGNATURE_INVALID")
        try:
            sig_bytes = bytes.fromhex(sig_hex)
            pub_bytes = bytes.fromhex(key_entry["public_key_hex"])
        except ValueError as exc:
            raise SafetyViolation("APPROVAL_SIGNATURE_INVALID") from exc

        signing_body = {k: decision[k] for k in SIGNING_BODY_KEYS}
        if not ed25519_verify(pub_bytes, canonical_signing_bytes(signing_body), sig_bytes):
            raise SafetyViolation("APPROVAL_SIGNATURE_INVALID")

        # 5. Nonce & token_id one-use anti-replay check (in-memory + durable WAL)
        if nonce in self.used_nonces or token_id in self.used_token_ids:
            raise SafetyViolation("APPROVAL_NONCE_REPLAYED")

        # 6. Process sequence / epoch check
        epoch_to_check = self.process_epoch if decision_epoch is None else decision_epoch
        if (
            type(epoch_to_check) is not int
            or epoch_to_check < self.process_epoch
            or epoch_to_check < self.max_seen_epoch
        ):
            raise SafetyViolation("APPROVAL_PRIOR_PROCESS_SEQUENCE")

        # 7. Worktree & route binding check
        wt_to_check = self.worktree_id if decision_worktree_id is None else decision_worktree_id
        rt_to_check = self.route_id if decision_route_id is None else decision_route_id
        if wt_to_check != self.worktree_id or rt_to_check != self.route_id:
            raise SafetyViolation("APPROVAL_ROUTE_OR_WORKTREE_MISMATCH")

        # 8. Model output / analysis state verification
        if (
            not isinstance(analysis, dict)
            or analysis.get("risk") != "DESCRIPTIVE_ONLY"
            or analysis.get("status") == "NO_ACTION_OR_MANUAL_REVIEW"
            or analysis_at is None
        ):
            raise SafetyViolation("APPROVAL_MODEL_OUTPUT_INVALID")

        expected_proposal_hash = digest(proposal)
        if (
            analysis.get("signal_id") != proposal.get("signal_id")
            or analysis.get("proposal_hash") != expected_proposal_hash
            or analysis.get("source_hash") != proposal.get("source_hash")
        ):
            raise SafetyViolation("APPROVAL_MODEL_OUTPUT_INVALID")

        # 9. Proposal binding check (signal_id, proposal_hash, version, side, quantity)
        if (
            type(decision["version"]) is not int
            or decision["version"] != 1
            or decision["version"] != proposal.get("version")
        ):
            raise SafetyViolation("APPROVAL_PROPOSAL_DRIFT")
        if decision["side"] not in ("LONG", "SHORT") or decision["side"] != proposal.get("side"):
            raise SafetyViolation("APPROVAL_PROPOSAL_DRIFT")
        decimal(decision["quantity"], positive=True)
        if (
            signal_id != proposal.get("signal_id")
            or proposal_hash != expected_proposal_hash
            or decision["quantity"] != proposal.get("quantity")
        ):
            raise SafetyViolation("APPROVAL_PROPOSAL_DRIFT")

        # 10. Context hash verification (binds source_hash, proposal_hash, analysis_hash, worktree, route, epoch)
        expected_context_hash = compute_operator_context_hash(
            source_hash=proposal["source_hash"],
            proposal_hash=expected_proposal_hash,
            analysis_hash=digest(analysis),
            worktree_id=self.worktree_id,
            route_id=self.route_id,
            process_epoch=self.process_epoch,
        )
        if decision["context_hash"] != expected_context_hash:
            raise SafetyViolation("APPROVAL_CONTEXT_HASH_MISMATCH")

        # 11. Causal clock & expiry check
        issued_at = timestamp(decision["issued_at"])
        expires_at = timestamp(decision["expires_at"])
        timestamp(approve_at)
        timestamp(analysis_at)
        prop_expires_at = timestamp(proposal["expires_at"])
        if (
            issued_at >= expires_at
            or issued_at < analysis_at
            or approve_at < issued_at
            or approve_at >= expires_at
            or approve_at >= prop_expires_at
        ):
            raise SafetyViolation("APPROVAL_CLOCK_OR_EXPIRY_INVALID")

        # 12. Record durable operator receipt in WAL with fsync
        approved_flag = decision_class == APPROVAL_CLASS
        g1_token = (
            {
                "token_id": token_id,
                "signal_id": signal_id,
                "proposal_hash": expected_proposal_hash,
                "proposal_version": 1,
                "quantity": decision["quantity"],
                "issued_at": issued_at,
                "expires_at": expires_at,
                "approved": True,
                "issuer": "TRUSTED_HUMAN_FIXTURE",
            }
            if approved_flag
            else None
        )
        receipt = {
            "schema_version": 1,
            "decision_hash": digest(decision),
            "token_id": token_id,
            "signal_id": signal_id,
            "proposal_hash": expected_proposal_hash,
            "side": decision["side"],
            "quantity": decision["quantity"],
            "issued_at": issued_at,
            "expires_at": expires_at,
            "approve_at": approve_at,
            "operator_id": operator_id,
            "key_id": key_id,
            "environment": env,
            "context_hash": expected_context_hash,
            "approval_nonce": nonce,
            "decision_class": decision_class,
            "approved": approved_flag,
            "process_epoch": self.process_epoch,
            "worktree_id": self.worktree_id,
            "route_id": self.route_id,
            "signature_sha256": digest(sig_hex),
            "translated_g1_token": g1_token,
        }
        self._append_receipt_wal(receipt, hook=hook)
        return receipt

    def _append_receipt_wal(self, receipt: dict[str, Any], *, hook: Any | None = None) -> None:
        if hook:
            hook("before_operator_receipt_append", receipt)
        body = {
            "seq": self.seq + 1,
            "previous": self.chain,
            "receipt": receipt,
            "receipt_hash": digest(receipt),
        }
        record = {**body, "record_hash": digest(body)}
        raw = (canonical(record) + "\n").encode("utf-8")
        fd = os.open(self.wal_path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
        try:
            offset = 0
            while offset < len(raw):
                offset += os.write(fd, raw[offset:])
            if hook:
                hook("after_operator_receipt_append", receipt)
            os.fsync(fd)
        finally:
            os.close(fd)
        self.used_nonces.add(receipt["approval_nonce"])
        self.used_token_ids.add(receipt["token_id"])
        self.receipts_by_proposal[(receipt["signal_id"], receipt["proposal_hash"])] = receipt
        self.seq = record["seq"]
        self.chain = record["record_hash"]
        if hook:
            hook("after_operator_receipt_fsync", receipt)

    def recover_or_verify_decision(
        self,
        decision: dict[str, Any],
        *,
        proposal: dict[str, Any],
        analysis: dict[str, Any] | None,
        analysis_at: int | None,
        approve_at: int,
        hook: Any | None = None,
    ) -> dict[str, Any]:
        """Idempotently recover an already-fsynced operator receipt on crash restart, or verify fresh."""
        prop_hash = digest(proposal)
        key = (str(proposal.get("signal_id", "")), prop_hash)
        if key in self.receipts_by_proposal:
            existing = self.receipts_by_proposal[key]
            if existing["decision_hash"] != digest(decision):
                raise SafetyViolation("SIDECAR_APPROVAL_REPLAY_MISMATCH")
            return existing
        return self.verify_decision(
            decision,
            proposal=proposal,
            analysis=analysis,
            analysis_at=analysis_at,
            approve_at=approve_at,
            hook=hook,
        )

    def materialize_sealed_fixture(
        self,
        untrusted_fixture: dict[str, Any],
        verified_receipt: dict[str, Any],
    ) -> tuple[dict[str, Any], Path, dict[str, Any]]:
        """Materialize a newly generated, read-only (0o400) sealed fixture for the G1 core."""
        self.reject_unauthenticated_fixture(untrusted_fixture)
        if (
            not verified_receipt.get("approved")
            or verified_receipt.get("translated_g1_token") is None
        ):
            raise SafetyViolation("OPERATOR_DECISION_NOT_APPROVED")
        sealed = copy.deepcopy(untrusted_fixture)
        sealed["trusted_approvals"] = [copy.deepcopy(verified_receipt["translated_g1_token"])]
        sealed_bytes = (canonical(sealed) + "\n").encode("utf-8")
        sealed_sha256 = digest(sealed)
        sealed_path = self.root / f"sealed_fixture_{sealed_sha256[:16]}.json"
        if sealed_path.is_symlink():
            raise SafetyViolation("PATH_SYMLINK")
        if sealed_path.exists():
            if sealed_path.read_bytes() != sealed_bytes:
                raise SafetyViolation("SEALED_FIXTURE_IMMUTABLE_CONFLICT")
        else:
            tmp_path = self.root / f"sealed_fixture_{sealed_sha256[:16]}.tmp"
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            try:
                os.write(fd, sealed_bytes)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.link(tmp_path, sealed_path, follow_symlinks=False)
            tmp_path.unlink()
            os.chmod(sealed_path, 0o400)

        seal_manifest = {
            "schema_version": 1,
            "trust_translation_boundary": "EXTERNAL_ED25519_OPERATOR_TO_G1_TRUSTED_FIXTURE_V1",
            "production_identity_control": False,
            "readiness": "OFFLINE_LOOPBACK_ONLY",
            "untrusted_fixture_sha256": digest(untrusted_fixture),
            "operator_decision_hash": verified_receipt["decision_hash"],
            "operator_id": verified_receipt["operator_id"],
            "operator_key_id": verified_receipt["key_id"],
            "approval_nonce": verified_receipt["approval_nonce"],
            "context_hash": verified_receipt["context_hash"],
            "signature_sha256": verified_receipt["signature_sha256"],
            "sealed_fixture_sha256": sealed_sha256,
            "sealed_fixture_path": str(sealed_path),
        }
        manifest_path = self.root / "SEAL_MANIFEST.json"
        manifest_path.write_text(canonical(seal_manifest) + "\n", encoding="utf-8")
        return sealed, sealed_path, seal_manifest
