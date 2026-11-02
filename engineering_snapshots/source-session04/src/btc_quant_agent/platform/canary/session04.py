"""Distinct instrumented diagnostic capability. No Owner authority is shipped.

Session03 remains immutable and consumed. Only pure durability/signature helpers
and the existing bounded clock-only runtime are reused.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Literal, cast

from pydantic import Field, model_validator

from ..core import fingerprint
from . import session03 as previous
from .clock_domain import capture
from .public_policy import (
    ROOT, SYMBOLS, PublicStop, Window, load_scope, preflight, sha,
)
from .session02 import GrantEnvelope as SignatureEnvelope, verify_signature

SESSION_ID = "L4-NATIVE-RUNTIME-V1-SESSION04"
VERSION = "L4_RUNTIME_SESSION04_GRANT_V1"
SESSION_OUTPUT = ROOT / "artifacts/live_public_canary_runtime_v1/session_04"
OWNER_KEYS = ROOT / "configs/canary/session04_owner_keys.json"
SCHEMA = ROOT / "configs/canary/session04_grant.schema.json"
ACCEPTANCE = ROOT / "SESSION04_PREDECLARED_NATIVE_ACCEPTANCE.json"
MAX_LAUNCH_MS = 8 * 3600_000
MAX_ACQUISITION_MS = 180_000
MIN_STARTUP_MS = 25_000
APPROVED_ROUTE = {"egress_mode": "CONTROLLED_EGRESS_PROXY", "proxy_host": "127.0.0.1",
                  "proxy_port": 7897, "tunnel_type": "HTTP_CONNECT"}


def source_hashes():
    files = previous.source_hashes()
    for p in (ROOT / "tools/launch_runtime_session04.py", OWNER_KEYS, SCHEMA, ACCEPTANCE):
        files[str(p.relative_to(ROOT))] = sha(p)
    return dict(sorted(files.items()))


class GrantBody(previous.GrantBody):
    # New closed wire discriminators intentionally replace the inherited schema.
    version: Literal["L4_RUNTIME_SESSION04_GRANT_V1"]  # type: ignore[assignment]
    session_id: Literal["L4-NATIVE-RUNTIME-V1-SESSION04"]  # type: ignore[assignment]
    authorization_reference: str = Field(pattern=r"^OWNER-V070-L4-RUNTIME-SESSION04-[A-Z0-9_-]+$")
    trial_purpose: Literal["DIAGNOSTIC_RUNTIME_ONLY"]
    unresolved_native_reliability_explicitly_accepted: Literal[True]
    predeclared_acceptance_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_route: dict
    ws_messages_per_second: Literal[200]
    pending_records: Literal[128]
    automatic_restart: Literal[False]
    automatic_request_retry: Literal[False]
    automatic_reconnect: Literal[False]

    @model_validator(mode="after")
    def exact_scope(self):
        if (self.symbols != SYMBOLS or self.endpoint_ids != previous.ENDPOINTS
                or self.allowed_hostnames != previous.HOSTS):
            raise ValueError("SESSION04_SOURCE_SCOPE_MISMATCH")
        if self.output_path != str(SESSION_OUTPUT):
            raise ValueError("SESSION04_EXACT_OUTPUT_REQUIRED")
        lo, hi = self.launch_window_start_utc_ms, self.launch_window_end_utc_ms
        if not self.issued_utc_ms <= lo < hi or hi - lo > MAX_LAUNCH_MS:
            raise ValueError("SESSION04_AUTHORIZATION_PERIOD_INVALID")
        if self.egress_route != APPROVED_ROUTE:
            raise ValueError("SESSION04_EXACT_CONTROLLED_CONNECT_REQUIRED")
        return self


class GrantEnvelope(previous.GrantEnvelope):
    grant: GrantBody
    key_id: str = Field(min_length=1, max_length=128)
    signature_algorithm: Literal["Ed25519"]
    signature_base64: str


def read_owner_keys():
    previous.check_path(OWNER_KEYS)
    if OWNER_KEYS.stat().st_size > 65536:
        raise PublicStop("SESSION04_OWNER_KEY_STORE_INVALID")
    value = json.loads(OWNER_KEYS.read_text())
    if (set(value) != {"version", "keys"} or value["version"] != "L4_SESSION04_OWNER_KEYS_V1"
            or not isinstance(value["keys"], dict)):
        raise PublicStop("SESSION04_OWNER_KEY_STORE_INVALID")
    return value["keys"]


def verify_owner(envelope, keys):
    body = envelope.grant
    entry = keys.get(envelope.key_id)
    required = {"public_key_base64", "public_key_sha256", "verified_owner_reference", "session_id",
                "launch_window_start_utc_ms", "launch_window_end_utc_ms"}
    if not isinstance(entry, dict) or set(entry) != required:
        raise PublicStop("SESSION04_INDEPENDENT_OWNER_AUTHORIZATION_REQUIRED")
    if (envelope.key_id != body.authorized_operator_key_id
            or entry["verified_owner_reference"] != body.authorization_reference
            or entry["session_id"] != SESSION_ID
            or type(entry["launch_window_start_utc_ms"]) is not int
            or type(entry["launch_window_end_utc_ms"]) is not int
            or entry["launch_window_start_utc_ms"] != body.launch_window_start_utc_ms
            or entry["launch_window_end_utc_ms"] != body.launch_window_end_utc_ms):
        raise PublicStop("SESSION04_KEY_SCOPE_OR_WINDOW_MISMATCH")
    try:
        digest = hashlib.sha256(base64.b64decode(entry["public_key_base64"], validate=True)).hexdigest()
    except (ValueError, TypeError) as exc:
        raise PublicStop("SESSION04_PUBLIC_KEY_INVALID") from exc
    if digest != entry["public_key_sha256"]:
        raise PublicStop("SESSION04_PUBLIC_KEY_HASH_MISMATCH")
    verify_signature(cast(SignatureEnvelope, envelope), {envelope.key_id: {
        "public_key_base64": entry["public_key_base64"],
        "verified_owner_reference": entry["verified_owner_reference"],
    }})


@dataclass(frozen=True)
class Session04Scope(previous.Session03Scope):
    authorization: GrantEnvelope
    request_retries_allowed = False
    reconnect_allowed = False

    @property
    def output_path(self):
        return SESSION_OUTPUT

    def source_hashes(self):
        return source_hashes()

    def require_authority(self, now, *, native):
        if fingerprint(self.authorization) != self.authorization_digest:
            raise PublicStop("SESSION04_AUTHORIZATION_MUTATED")
        if native and self.fabricated_authority:
            raise PublicStop("SESSION04_OFFLINE_SYNTHETIC_CANNOT_ACTIVATE_NATIVE")
        if now < self.authorization.grant.issued_utc_ms:
            raise PublicStop("SESSION04_OWNER_GRANT_FROM_FUTURE")
        if now < self.start_ms:
            raise PublicStop("SESSION04_WINDOW_NOT_OPEN")
        if now >= self.end_ms:
            raise PublicStop("SESSION04_WINDOW_EXPIRED")

    def preflight(self, clock, *, native):
        self.require_authority(clock.wall(), native=native)
        if self.activation:
            raise PublicStop("SESSION04_ALREADY_CONSUMED_NEVER_RESET")
        if fingerprint(source_hashes()) != self.authorization.grant.source_sha256_fingerprint:
            raise PublicStop("SESSION04_CURRENT_SOURCE_HASH_MISMATCH")
        if sha(ACCEPTANCE) != self.authorization.grant.predeclared_acceptance_sha256:
            raise PublicStop("SESSION04_PREDECLARED_ACCEPTANCE_HASH_MISMATCH")
        previous.check_path(self.output_path)
        if native:
            verify_owner(self.authorization, read_owner_keys())
            if self.output_path.exists():
                raise PublicStop("SESSION04_ALREADY_CONSUMED_NEVER_RESET")
        self.make_window(clock).check()
        if self.end_ms - clock.wall() - getattr(clock, "utc_uncertainty_ms", 0) < MIN_STARTUP_MS:
            raise PublicStop("INSUFFICIENT_REMAINING_WINDOW")
        result = preflight(self, clock, native=native)
        if native:
            from .public_egress import ProxyConfig

            route = (ProxyConfig.parse(os.environ["L4_EGRESS_PROXY_URL"]).receipt()
                     if os.environ.get("L4_CONTROLLED_EGRESS") == "1"
                     and os.environ.get("L4_EGRESS_PROXY_URL") else {})
            if any(route.get(k) != v for k, v in APPROVED_ROUTE.items()):
                result["reasons"].append("SESSION04_EXACT_CONTROLLED_CONNECT_REQUIRED")
                result["status"] = "BLOCKED"
        result.update(session_id=SESSION_ID, maximum_acquisition_ms=MAX_ACQUISITION_MS,
                      trial_purpose="DIAGNOSTIC_RUNTIME_ONLY")
        return result

    def validate_route(self, route):
        if any(route.get(k) != v for k, v in APPROVED_ROUTE.items()):
            raise PublicStop("SESSION04_EXACT_CONTROLLED_CONNECT_REQUIRED")
        return super().validate_route(route)

    def reserve_launch(self, clock, root, *, native):
        self.preflight(clock, native=native)
        root = Path(root)
        if native and root != self.output_path:
            raise PublicStop("SESSION04_EXACT_OUTPUT_REQUIRED")
        previous.check_path(root)
        wall, mono, sample = capture(clock)
        end = min(wall + MAX_ACQUISITION_MS, self.outer_end_ms)
        if end - wall - getattr(clock, "utc_uncertainty_ms", 0) < MIN_STARTUP_MS:
            raise PublicStop("INSUFFICIENT_REMAINING_WINDOW")
        window = Window(clock, start_ms=self.start_ms, end_ms=end,
                        authorized_bounds=(self.start_ms, self.outer_end_ms))
        window.mono_end = min(window.mono_end, mono + MAX_ACQUISITION_MS)
        window.check()
        root.parent.mkdir(parents=False, exist_ok=True)
        try:
            root.mkdir(exist_ok=False)
        except FileExistsError:
            raise PublicStop("SESSION04_ALREADY_CONSUMED_NEVER_RESET") from None
        previous.sync_directory(root.parent)
        self.activation.update(actual_start_ms=wall, actual_end_ms=end, actual_start_mono=mono,
                               window=window, clock=clock, sample=sample)
        previous.durable_json(root / "launch_reservation.json", {
            "version": "L4_SESSION04_RESERVATION_V1", "session_id": SESSION_ID,
            "authorization_digest": self.authorization_digest, "scope_hash": self.hash,
            "actual_start_ms": wall, "actual_start_mono_ms": mono, "actual_end_ms": end,
            "monotonic_deadline_ms": window.mono_end, "clock_sample": sample,
            "fabricated_authority": self.fabricated_authority, "request_count": None,
            "status": "RESERVED_EXECUTION_UNKNOWN_UNTIL_SEALED",
        })
        previous.durable_json(root / "owner_signed_grant.json", self.authorization.model_dump(mode="json"))
        previous.sync_directory(root)
        self.activation["durable"] = True

    def record_window(self):
        value = super().record_window()
        return {**value, "version": VERSION, "session_id": SESSION_ID}


def load_session04(path, now, *, fabricated_keys=None):
    path = Path(path)
    if not path.is_file():
        raise PublicStop("SESSION04_OWNER_GRANT_ABSENT")
    previous.check_path(path)
    if path.stat().st_size > 65536:
        raise PublicStop("SESSION04_UNTRUSTED_GRANT_FILE")
    try:
        envelope = GrantEnvelope.model_validate_json(path.read_text())
    except ValueError as exc:
        raise PublicStop("SESSION04_GRANT_SCHEMA_OR_BINDING_INVALID") from exc
    body = envelope.grant
    base = load_scope()
    if body.source_sha256_fingerprint != fingerprint(source_hashes()):
        raise PublicStop("SESSION04_CURRENT_SOURCE_HASH_MISMATCH")
    if body.predeclared_acceptance_sha256 != sha(ACCEPTANCE):
        raise PublicStop("SESSION04_PREDECLARED_ACCEPTANCE_HASH_MISMATCH")
    if body.documentation_fingerprint != base.grant.documentation_fingerprint:
        raise PublicStop("SESSION04_DOCUMENTATION_FINGERPRINT_MISMATCH")
    fields = {id: tuple(next(e for e in base.document["endpoints"] if e["id"] == id)["fields"])
              for id in previous.ENDPOINTS}
    if body.endpoint_fields != fields:
        raise PublicStop("SESSION04_FIELD_SCOPE_MISMATCH")
    verify_owner(envelope, read_owner_keys() if fabricated_keys is None else fabricated_keys)
    raw = {**base.raw, "activation_status": "SESSION04_SIGNATURE_VERIFIED", "session_id": SESSION_ID,
           "owner_session04_envelope": envelope.model_dump(mode="json")}
    grant = base.grant.model_copy(update={
        "grant_id": body.authorization_reference, "endpoint_ids": previous.ENDPOINTS, "fields": fields,
        "start_utc_ms": body.launch_window_start_utc_ms, "end_utc_ms": body.launch_window_end_utc_ms,
        "output_path": body.output_path, "connections": 1, "subscriptions": 3,
        "policy_hash": fingerprint(body), "approval_source_reference": body.authorization_reference,
        "endpoint_calls_per_minute": {previous.ENDPOINTS[0]: 3, previous.ENDPOINTS[1]: 2},
    })
    scope = Session04Scope(grant, raw, base.document, path, envelope,
                           fabricated_keys is not None, fingerprint(envelope))
    scope.require_authority(now, native=fabricated_keys is None)
    return scope


def validate_record_window(record):
    c = record["flex_window_contract"]
    if c.get("version") != VERSION or c.get("session_id") != SESSION_ID:
        raise ValueError("SESSION04_WINDOW_BINDING_INVALID")
    # Reuse the exact established bounds/hash checks without altering the record.
    proxy = {**record, "flex_window_contract": {**c, "version": previous.VERSION,
                                               "session_id": previous.SESSION_ID}}
    previous.validate_record_window(proxy)


def run_session04(scope, *, enabled=False, clock=None, backend=None, output=None):
    from .public_runtime import run_public, save_reports

    root = Path(output) if output is not None else scope.output_path
    try:
        return run_public(scope, enabled=enabled, clock=clock, backend=backend, output=output)
    except Exception as exc:
        if (scope.activation and (root / "launch_reservation.json").is_file()
                and not (root / "report.json").exists()):
            result = {"status": "BLOCKED", "session_id": SESSION_ID, "stop_reason": str(exc),
                      "native_market_requests": None, "request_count_status": "UNKNOWN",
                      "source_qualified": False, "shadow_advisory_qualified": False,
                      "economically_validated": False, "retry_authorized": False}
            save_reports(root, result)
            return result
        raise


def requirements():
    return {"status": "BLOCKED", "reason": "SEPARATE_EXACT_OWNER_AUTHORIZATION_REQUIRED",
            "session_id": SESSION_ID, "grant_version": VERSION, "output_path": str(SESSION_OUTPUT),
            "source_sha256_fingerprint": fingerprint(source_hashes()), "source_files": source_hashes(),
            "predeclared_acceptance_sha256": sha(ACCEPTANCE), "maximum_launch_window_ms": MAX_LAUNCH_MS,
            "maximum_acquisition_ms": MAX_ACQUISITION_MS, "minimum_startup_ms": MIN_STARTUP_MS,
            "owner_keys_installed": bool(read_owner_keys()), "owner_grant_created": False,
            "trial_purpose": "DIAGNOSTIC_RUNTIME_ONLY", "native_market_requests": 0,
            "source_qualified": False, "shadow_advisory_qualified": False, "long_authorized": False}
