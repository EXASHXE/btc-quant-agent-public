"""Exact, signed Session 02 capability. Shipped trust store is EMPTY: no native grant.

An authorization flag or self-created JSON cannot grant access. A future Owner /
Owner-authorized Controller key must be independently installed before signing
the exact scope, including that trust store's current source fingerprint.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core import fingerprint
from .policy import ROOT
from .public_policy import (
    PublicScope,
    PublicStop,
    START,
    END,
    OUTPUT,
    SYMBOLS,
    HEAD,
    Window,
    current_source_hashes,
    load_scope,
    preflight,
    sha,
    DEFAULT_GRANT,
    SOURCE_BINDING,
    ENDPOINT_DOCUMENT,
)

SESSION_ID = "L4-NATIVE-CLOCK-V2-SESSION02-20261030"
SESSION_OUTPUT = OUTPUT / "session_02_clock_v2"
ENDPOINTS = ("binance_usdm_exchange_info", "binance_usdm_server_time", "binance_usdm_bbo_ws")
OWNER_KEYS = ROOT / "configs/canary/session02_owner_keys.json"
SCHEMA = ROOT / "configs/canary/session02_grant.schema.json"
MAX_DURATION_MS = 180_000


def source_hashes():
    files = current_source_hashes()
    for p in (
        ROOT / "tools/launch_clock_session02.py",
        OWNER_KEYS,
        SCHEMA,
        DEFAULT_GRANT,
        SOURCE_BINDING,
        ENDPOINT_DOCUMENT,
    ):
        files[str(p.relative_to(ROOT))] = sha(p)
    return dict(sorted(files.items()))


class GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal["L4_SESSION02_GRANT_V1"]
    session_id: Literal["L4-NATIVE-CLOCK-V2-SESSION02-20261030"]
    authorization_reference: str = Field(pattern=r"^OWNER-V070-L4-SESSION02-[A-Z0-9_-]+$")
    provider: Literal["binance"]
    market: Literal["USD_M_USDT_LINEAR_PERPETUAL"]
    permitted_use: Literal["OWNER_CONFIRMED_PERSONAL_NONCOMMERCIAL_PUBLIC_READONLY"]
    symbols: tuple[str, ...]
    endpoint_ids: tuple[str, ...]
    endpoint_fields: dict[str, tuple[str, ...]]
    output_path: str
    issued_utc_ms: int = Field(gt=0)
    start_utc_ms: int = Field(gt=0)
    end_utc_ms: int = Field(gt=0)
    source_sha256_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_documentation_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    documentation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    clock_contract: Literal["L4_CLOCK_DOMAIN_V2"]
    wall_jump_ms: Literal[50]
    max_offset_uncertainty_ms: Literal[100]
    max_probe_age_ms: Literal[300000]
    startup_independent_probes: Literal[2]
    startup_probe_gap_ms: Literal[10]
    subsequent_probe_interval_ms: Literal[120000]
    rest_weight_per_minute: Literal[60]
    retry_reserve_weight_per_minute: Literal[10]
    time_calls_per_minute: Literal[2]
    controls_per_second: Literal[2]
    connections: Literal[1]
    subscriptions: Literal[3]
    reconnects_per_hour: Literal[3]
    raw_retention_hours: Literal[36]
    normalized_retention_hours: Literal[168]
    raw_bytes: Literal[8589934592]
    auxiliary_bytes: Literal[4294967296]
    external_notifications: Literal[False]
    account_or_order_operations: Literal[False]

    @model_validator(mode="after")
    def exact_scope(self):
        if self.symbols != SYMBOLS or self.endpoint_ids != ENDPOINTS:
            raise ValueError("SESSION02_SYMBOL_OR_ENDPOINT_SCOPE_MISMATCH")
        if self.output_path != str(SESSION_OUTPUT):
            raise ValueError("SESSION02_EXACT_OUTPUT_REQUIRED")
        if not START <= self.issued_utc_ms <= self.start_utc_ms < self.end_utc_ms <= END:
            raise ValueError("SESSION02_UTC_SCOPE_INVALID")
        if self.end_utc_ms - self.start_utc_ms > MAX_DURATION_MS:
            raise ValueError("SESSION02_DURATION_EXCEEDS_180S")
        if self.canonical_documentation_head != HEAD:
            raise ValueError("SESSION02_DOCUMENTATION_HEAD_MISMATCH")
        return self


class GrantEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    grant: GrantBody
    key_id: str = Field(min_length=1, max_length=128)
    signature_algorithm: Literal["Ed25519"]
    signature_base64: str


def signed_bytes(body: GrantBody) -> bytes:
    return json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()


def read_owner_keys():
    if OWNER_KEYS.is_symlink():
        raise PublicStop("SESSION02_UNTRUSTED_OWNER_KEY_STORE")
    data = json.loads(OWNER_KEYS.read_text())
    if set(data) != {"version", "keys"} or data["version"] != "L4_SESSION02_OWNER_KEYS_V1":
        raise PublicStop("SESSION02_OWNER_KEY_STORE_SCHEMA_INVALID")
    if not isinstance(data["keys"], dict):
        raise PublicStop("SESSION02_OWNER_KEY_STORE_SCHEMA_INVALID")
    return data["keys"]


def verify_signature(envelope: GrantEnvelope, keys: dict):
    entry = keys.get(envelope.key_id)
    if not entry:
        raise PublicStop("SESSION02_OWNER_AUTHORIZATION_NOT_PROVISIONED")
    if (
        set(entry) != {"public_key_base64", "verified_owner_reference"}
        or not entry["verified_owner_reference"]
    ):
        raise PublicStop("SESSION02_OWNER_KEY_ATTESTATION_MISSING")
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise PublicStop("SESSION02_SIGNATURE_VERIFIER_UNAVAILABLE") from exc
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(entry["public_key_base64"], validate=True))
        key.verify(base64.b64decode(envelope.signature_base64, validate=True), signed_bytes(envelope.grant))
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise PublicStop("SESSION02_OWNER_SIGNATURE_INVALID") from exc


def check_output_path(path: Path):
    if path != SESSION_OUTPUT:
        raise PublicStop("SESSION02_EXACT_OUTPUT_REQUIRED")
    for p in (path, *path.parents):
        if p.is_symlink():
            raise PublicStop("SESSION02_SYMLINK_OUTPUT_FORBIDDEN")


@dataclass(frozen=True)
class Session02Scope(PublicScope):
    authorization: GrantEnvelope
    fabricated_authority: bool
    authorization_digest: str
    run_profile: str = "CLOCK_VALIDATION_ONLY"

    @property
    def start_ms(self):
        return self.authorization.grant.start_utc_ms

    @property
    def end_ms(self):
        return self.authorization.grant.end_utc_ms

    @property
    def output_path(self):
        return SESSION_OUTPUT

    def require_authority(self, now, *, native):
        if fingerprint(self.authorization) != self.authorization_digest:
            raise PublicStop("SESSION02_AUTHORIZATION_MUTATED")
        if native and self.fabricated_authority:
            raise PublicStop("SESSION02_FABRICATED_AUTHORITY_CANNOT_ACTIVATE_NATIVE")
        if self.authorization.grant.issued_utc_ms > now:
            raise PublicStop("SESSION02_OWNER_GRANT_FROM_FUTURE")
        if now < self.start_ms:
            raise PublicStop("SESSION02_WINDOW_NOT_OPEN")
        if now >= self.end_ms:
            raise PublicStop("SESSION02_GRANT_EXPIRED")

    def make_window(self, clock):
        return Window(clock, start_ms=self.start_ms, end_ms=self.end_ms)

    def preflight(self, clock, *, native):
        self.require_authority(clock.wall(), native=native)
        if fingerprint(source_hashes()) != self.authorization.grant.source_sha256_fingerprint:
            raise PublicStop("SESSION02_CURRENT_SOURCE_HASH_MISMATCH")
        if native:
            verify_signature(self.authorization, read_owner_keys())
            check_output_path(self.output_path)
        result = preflight(self, clock, native=native)
        self.make_window(clock).check()
        return result

    def validate_request(self, id, params, now):
        self.require_authority(now, native=False)
        if id not in ENDPOINTS[:2] or params:
            raise PublicStop("SESSION02_ENDPOINT_OR_PARAMETERS_FORBIDDEN")
        return super().validate_request(id, params, now)

    def streams(self, group):
        if group != "public":
            raise PublicStop("SESSION02_ONLY_BBO_STREAM_ALLOWED")
        return super().streams(group)

    def endpoint(self, id):
        if id not in ENDPOINTS:
            raise PublicStop("SESSION02_ENDPOINT_FORBIDDEN")
        return super().endpoint(id)

    def budget_policy(self):
        return (
            super()
            .budget_policy()
            .model_copy(
                update={
                    "endpoint_ids": ENDPOINTS,
                    "synthetic_start_ms": self.start_ms,
                    "duration_ms": self.end_ms - self.start_ms,
                    "max_connections": 1,
                    "max_subscriptions": 3,
                    "endpoint_calls_per_minute": {
                        "binance_usdm_exchange_info": 3,
                        "binance_usdm_server_time": 2,
                    },
                }
            )
        )


def load_session02(path, now, *, fabricated_keys=None):
    """Only tests inject keys; such a scope is permanently non-native."""
    path = Path(path)
    if not path.is_file():
        raise PublicStop("SESSION02_OWNER_GRANT_ABSENT")
    if path.is_symlink() or path.stat().st_size > 65536:
        raise PublicStop("SESSION02_UNTRUSTED_GRANT_FILE")
    try:
        envelope = GrantEnvelope.model_validate_json(path.read_text())
    except ValueError as exc:
        raise PublicStop("SESSION02_GRANT_SCHEMA_OR_BINDING_INVALID:" + str(exc)) from exc
    base = load_scope()
    body = envelope.grant
    if body.source_sha256_fingerprint != fingerprint(source_hashes()):
        raise PublicStop("SESSION02_CURRENT_SOURCE_HASH_MISMATCH")
    if body.documentation_fingerprint != base.grant.documentation_fingerprint:
        raise PublicStop("SESSION02_DOCUMENTATION_FINGERPRINT_MISMATCH")
    fields = {
        id: tuple(next(e for e in base.document["endpoints"] if e["id"] == id)["fields"]) for id in ENDPOINTS
    }
    if body.endpoint_fields != fields:
        raise PublicStop("SESSION02_FIELD_SCOPE_MISMATCH")
    keys = read_owner_keys() if fabricated_keys is None else fabricated_keys
    verify_signature(envelope, keys)
    raw = {
        **base.raw,
        "activation_status": "SESSION02_SIGNATURE_VERIFIED",
        "session_id": SESSION_ID,
        "owner_session02_envelope": envelope.model_dump(mode="json"),
    }
    grant = base.grant.model_copy(
        update={
            "grant_id": body.authorization_reference,
            "endpoint_ids": ENDPOINTS,
            "fields": fields,
            "start_utc_ms": body.start_utc_ms,
            "end_utc_ms": body.end_utc_ms,
            "output_path": body.output_path,
            "connections": 1,
            "subscriptions": 3,
            "policy_hash": fingerprint(body),
            "approval_source_reference": body.authorization_reference,
            "endpoint_calls_per_minute": {"binance_usdm_exchange_info": 3, "binance_usdm_server_time": 2},
        }
    )
    scope = Session02Scope(
        grant, raw, base.document, path, envelope, fabricated_keys is not None, fingerprint(envelope)
    )
    scope.require_authority(now, native=fabricated_keys is None)
    return scope


def requirements():
    return {
        "status": "PREPARED_BUT_NOT_AUTHORIZED",
        "session_id": SESSION_ID,
        "output_path": str(SESSION_OUTPUT),
        "maximum_duration_ms": MAX_DURATION_MS,
        "absolute_end_utc_ms": END,
        "endpoint_ids": ENDPOINTS,
        "symbols": SYMBOLS,
        "source_sha256_fingerprint": fingerprint(source_hashes()),
        "source_files": source_hashes(),
        "canonical_documentation_head": HEAD,
        "owner_keys_installed": bool(read_owner_keys()),
        "owner_grant_created": False,
        "native_market_requests": 0,
        "required_owner_evidence": "Distinct exact signed Owner authorization. Independently confirm Owner/authorized Controller public key first; then approve current source fingerprint and sign the canonical GrantBody bytes. No private account/exchange key is used.",
        "schema_path": str(SCHEMA),
        "signature_algorithm": "Ed25519",
        "source_qualified": False,
        "shadow_advisory_qualified": False,
        "economically_validated": False,
    }
