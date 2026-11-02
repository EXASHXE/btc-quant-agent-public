"""Owner-signed flexible launch window; ONE foreground clock-only acquisition.

No dates, Owner grant or trusted signer are shipped. Session02 keys are not trusted.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core import fingerprint
from .clock_domain import capture
from .public_policy import (
    PublicScope,
    PublicStop,
    Window,
    SYMBOLS,
    ROOT,
    current_source_hashes,
    load_scope,
    preflight,
    sha,
    DEFAULT_GRANT,
    SOURCE_BINDING,
    ENDPOINT_DOCUMENT,
)
from .session02 import GrantEnvelope as PreviousEnvelope, verify_signature

SESSION_ID = "L4-NATIVE-CLOCK-V2-FLEX-SESSION03"
VERSION = "L4_FLEX_SESSION03_GRANT_V2"
LAUNCH_LIMITS = {"L4_FLEX_SESSION03_GRANT_V1": 6 * 3600_000, VERSION: 8 * 3600_000}
HEAD = "caf9af0489ca5002c2c6deb17305efc591f2e32e"
SESSION_OUTPUT = ROOT / "artifacts/live_public_canary_flex/session_03_clock_v2"
OWNER_KEYS = ROOT / "configs/canary/session03_owner_keys.json"
SCHEMA_V1 = ROOT / "L4_FLEX_SESSION03_GRANT_SCHEMA.json"
SCHEMA = ROOT / "L4_FLEX_SESSION03_GRANT_SCHEMA_V2.json"
ENDPOINTS = ("binance_usdm_exchange_info", "binance_usdm_server_time", "binance_usdm_bbo_ws")
HOSTS = ("fapi.binance.com", "fstream.binance.com")
MAX_LAUNCH_MS = LAUNCH_LIMITS[VERSION]
MAX_ACQUISITION_MS = 180_000
# 3 REST deadlines + 1 WS handshake (5s each), plus 5s observation headroom.
MIN_STARTUP_MS = 25_000


def source_hashes():
    files = current_source_hashes()
    for p in (
        ROOT / "tools/launch_clock_session03.py",
        ROOT / "tools/demo_session03_v2_offline.py",
        OWNER_KEYS,
        SCHEMA,
        SCHEMA_V1,
        DEFAULT_GRANT,
        SOURCE_BINDING,
        ENDPOINT_DOCUMENT,
    ):
        files[str(p.relative_to(ROOT))] = sha(p)
    return dict(sorted(files.items()))


class GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal["L4_FLEX_SESSION03_GRANT_V1", "L4_FLEX_SESSION03_GRANT_V2"]
    session_id: Literal["L4-NATIVE-CLOCK-V2-FLEX-SESSION03"]
    authorization_reference: str = Field(pattern=r"^OWNER-V070-L4-FLEX-SESSION03-[A-Z0-9_-]+$")
    authorized_operator_key_id: str = Field(min_length=1, max_length=128)
    provider: Literal["binance"]
    market: Literal["USD_M_USDT_LINEAR_PERPETUAL"]
    permitted_use: Literal["OWNER_CONFIRMED_PERSONAL_NONCOMMERCIAL_PUBLIC_READONLY"]
    symbols: tuple[str, ...]
    endpoint_ids: tuple[str, ...]
    endpoint_fields: dict[str, tuple[str, ...]]
    allowed_hostnames: tuple[str, ...]
    output_path: str
    issued_utc_ms: int = Field(gt=0)
    launch_window_start_utc_ms: int = Field(gt=0)
    launch_window_end_utc_ms: int = Field(gt=0)
    max_acquisition_ms: Literal[180000]
    minimum_startup_ms: Literal[25000]
    source_sha256_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_documentation_head: Literal["caf9af0489ca5002c2c6deb17305efc591f2e32e"]
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
        if self.symbols != SYMBOLS or self.endpoint_ids != ENDPOINTS or self.allowed_hostnames != HOSTS:
            raise ValueError("SESSION03_SOURCE_SCOPE_MISMATCH")
        if self.output_path != str(SESSION_OUTPUT):
            raise ValueError("SESSION03_EXACT_OUTPUT_REQUIRED")
        start, end = self.launch_window_start_utc_ms, self.launch_window_end_utc_ms
        if not self.issued_utc_ms <= start < end or not 0 < end - start <= LAUNCH_LIMITS[self.version]:
            raise ValueError("SESSION03_AUTHORIZATION_PERIOD_INVALID")
        return self


class GrantEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    grant: GrantBody
    key_id: str = Field(min_length=1, max_length=128)
    signature_algorithm: Literal["Ed25519"]
    signature_base64: str


def read_owner_keys():
    if OWNER_KEYS.is_symlink():
        raise PublicStop("SESSION03_UNTRUSTED_OWNER_KEY_STORE")
    value = json.loads(OWNER_KEYS.read_text())
    if set(value) != {"version", "keys"} or value["version"] != "L4_SESSION03_OWNER_KEYS_V1":
        raise PublicStop("SESSION03_OWNER_KEY_STORE_SCHEMA_INVALID")
    if not isinstance(value["keys"], dict):
        raise PublicStop("SESSION03_OWNER_KEY_STORE_SCHEMA_INVALID")
    return value["keys"]


def verify_owner(envelope, keys):
    body = envelope.grant
    entry = keys.get(envelope.key_id)
    required = {
        "public_key_base64",
        "public_key_sha256",
        "verified_owner_reference",
        "session_id",
        "launch_window_start_utc_ms",
        "launch_window_end_utc_ms",
    }
    if not entry or set(entry) != required:
        raise PublicStop("SESSION03_INDEPENDENT_OWNER_KEY_AUTHORIZATION_REQUIRED")
    if (
        envelope.key_id != body.authorized_operator_key_id
        or entry["verified_owner_reference"] != body.authorization_reference
        or entry["session_id"] != SESSION_ID
        or entry["launch_window_start_utc_ms"] != body.launch_window_start_utc_ms
        or entry["launch_window_end_utc_ms"] != body.launch_window_end_utc_ms
    ):
        raise PublicStop("SESSION03_KEY_SCOPE_OR_PERIOD_MISMATCH")
    try:
        digest = hashlib.sha256(base64.b64decode(entry["public_key_base64"], validate=True)).hexdigest()
    except (ValueError, TypeError) as exc:
        raise PublicStop("SESSION03_PUBLIC_KEY_INVALID") from exc
    if digest != entry["public_key_sha256"]:
        raise PublicStop("SESSION03_PUBLIC_KEY_FINGERPRINT_MISMATCH")
    # Reuse the existing canonical Ed25519 verifier; the full new body is signed.
    verify_signature(
        cast(PreviousEnvelope, envelope),
        {
            envelope.key_id: {
                "public_key_base64": entry["public_key_base64"],
                "verified_owner_reference": entry["verified_owner_reference"],
            }
        },
    )


def check_path(path):
    for p in (path, *path.parents):
        if p.is_symlink():
            raise PublicStop("SESSION03_SYMLINK_OUTPUT_FORBIDDEN")


def durable_json(path, value):
    with path.open("x") as f:
        f.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@dataclass(frozen=True)
class Session03Scope(PublicScope):
    authorization: GrantEnvelope
    fabricated_authority: bool
    authorization_digest: str
    activation: dict = field(default_factory=dict, compare=False, repr=False)
    run_profile: str = "CLOCK_VALIDATION_ONLY"
    allowed_hostnames: tuple[str, ...] = HOSTS

    @property
    def start_ms(self):
        return self.activation.get("actual_start_ms", self.authorization.grant.launch_window_start_utc_ms)

    @property
    def end_ms(self):
        return self.activation.get("actual_end_ms", self.authorization.grant.launch_window_end_utc_ms)

    @property
    def outer_end_ms(self):
        return self.authorization.grant.launch_window_end_utc_ms

    @property
    def actual_start_ms(self):
        return self.activation["actual_start_ms"]

    @property
    def actual_start_mono(self):
        return self.activation["actual_start_mono"]

    @property
    def output_path(self):
        return SESSION_OUTPUT

    def source_hashes(self):
        return source_hashes()

    def require_authority(self, now, *, native):
        if fingerprint(self.authorization) != self.authorization_digest:
            raise PublicStop("SESSION03_AUTHORIZATION_MUTATED")
        if native and self.fabricated_authority:
            raise PublicStop("SESSION03_FABRICATED_AUTHORITY_CANNOT_ACTIVATE_NATIVE")
        if now < self.authorization.grant.issued_utc_ms:
            raise PublicStop("SESSION03_OWNER_GRANT_FROM_FUTURE")
        if now < self.start_ms:
            raise PublicStop("SESSION03_WINDOW_NOT_OPEN")
        if now >= self.end_ms:
            raise PublicStop("SESSION03_WINDOW_EXPIRED")

    def make_window(self, clock):
        if self.activation:
            if clock is not self.activation["clock"]:
                raise PublicStop("SESSION03_CLOCK_INSTANCE_CHANGED")
            return self.activation["window"]
        body = self.authorization.grant
        return Window(
            clock,
            start_ms=self.start_ms,
            end_ms=self.end_ms,
            authorized_bounds=(body.launch_window_start_utc_ms, body.launch_window_end_utc_ms),
        )

    def preflight(self, clock, *, native):
        self.require_authority(clock.wall(), native=native)
        if self.activation:
            raise PublicStop("SESSION03_ALREADY_CONSUMED_NEVER_RESET")
        if fingerprint(source_hashes()) != self.authorization.grant.source_sha256_fingerprint:
            raise PublicStop("SESSION03_CURRENT_SOURCE_HASH_MISMATCH")
        if native:
            verify_owner(self.authorization, read_owner_keys())
            check_path(self.output_path)
            if self.output_path.exists():
                raise PublicStop("SESSION03_ALREADY_CONSUMED_NEVER_RESET")
        self.make_window(clock).check()
        if self.end_ms - clock.wall() - getattr(clock, "utc_uncertainty_ms", 0) < MIN_STARTUP_MS:
            raise PublicStop("INSUFFICIENT_REMAINING_WINDOW")
        result = preflight(self, clock, native=native)
        result.update(session_id=SESSION_ID, maximum_acquisition_ms=MAX_ACQUISITION_MS)
        return result

    def reserve_launch(self, clock, root, *, native):
        self.preflight(clock, native=native)
        if native and root != self.output_path:
            raise PublicStop("SESSION03_EXACT_OUTPUT_REQUIRED")
        check_path(root)
        wall, mono, sample = capture(clock)
        end = min(wall + MAX_ACQUISITION_MS, self.outer_end_ms)
        if end - wall - getattr(clock, "utc_uncertainty_ms", 0) < MIN_STARTUP_MS:
            raise PublicStop("INSUFFICIENT_REMAINING_WINDOW")
        window = Window(
            clock, start_ms=self.start_ms, end_ms=end, authorized_bounds=(self.start_ms, self.outer_end_ms)
        )
        window.mono_end = min(window.mono_end, mono + MAX_ACQUISITION_MS)
        window.check()
        root.parent.mkdir(parents=False, exist_ok=True)
        try:
            root.mkdir(exist_ok=False)
        except FileExistsError:
            raise PublicStop("SESSION03_ALREADY_CONSUMED_NEVER_RESET") from None
        # Even an empty directory after a crash permanently consumes the capability.
        sync_directory(root.parent)
        self.activation.update(
            actual_start_ms=wall,
            actual_end_ms=end,
            actual_start_mono=mono,
            window=window,
            clock=clock,
            sample=sample,
        )
        durable_json(
            root / "launch_reservation.json",
            {
                "version": "L4_SESSION03_RESERVATION_V1",
                "session_id": SESSION_ID,
                "authorization_digest": self.authorization_digest,
                "scope_hash": self.hash,
                "actual_start_ms": wall,
                "actual_start_mono_ms": mono,
                "actual_end_ms": end,
                "monotonic_deadline_ms": window.mono_end,
                "clock_sample": sample,
                "fabricated_authority": self.fabricated_authority,
                "request_count": None,
                "status": "RESERVED_EXECUTION_UNKNOWN_UNTIL_SEALED",
            },
        )
        durable_json(root / "owner_signed_grant.json", self.authorization.model_dump(mode="json"))
        sync_directory(root)
        self.activation["durable"] = True

    def require_execution_reservation(self):
        if not self.activation.get("durable"):
            raise PublicStop("SESSION03_DURABLE_LAUNCH_RESERVATION_REQUIRED")

    def record_window(self):
        return {
            "version": self.authorization.grant.version,
            "session_id": SESSION_ID,
            "scope_hash": self.hash,
            "authorization_digest": self.authorization_digest,
            "source_fingerprint": self.authorization.grant.source_sha256_fingerprint,
            "launch_start_ms": self.authorization.grant.launch_window_start_utc_ms,
            "launch_end_ms": self.outer_end_ms,
            "acquisition_start_ms": self.start_ms,
            "acquisition_end_ms": self.end_ms,
        }

    def validate_request(self, id, params, now):
        self.require_authority(now, native=False)
        if id not in ENDPOINTS[:2] or params:
            raise PublicStop("SESSION03_ENDPOINT_OR_PARAMETERS_FORBIDDEN")
        return super().validate_request(id, params, now)

    def endpoint(self, id):
        if id not in ENDPOINTS:
            raise PublicStop("SESSION03_ENDPOINT_FORBIDDEN")
        return super().endpoint(id)

    def streams(self, group):
        if group != "public":
            raise PublicStop("SESSION03_ONLY_BBO_STREAM_ALLOWED")
        return super().streams(group)

    def budget_policy(self):
        return (
            super()
            .budget_policy()
            .model_copy(
                update={
                    "endpoint_ids": ENDPOINTS,
                    "synthetic_start_ms": self.start_ms,
                    "duration_ms": min(MAX_ACQUISITION_MS, self.end_ms - self.start_ms),
                    "max_connections": 1,
                    "max_subscriptions": 3,
                    "endpoint_calls_per_minute": {ENDPOINTS[0]: 3, ENDPOINTS[1]: 2},
                }
            )
        )


def load_session03(path, now, *, fabricated_keys=None):
    path = Path(path)
    if not path.is_file():
        raise PublicStop("SESSION03_OWNER_GRANT_ABSENT")
    if path.is_symlink() or path.stat().st_size > 65536:
        raise PublicStop("SESSION03_UNTRUSTED_GRANT_FILE")
    try:
        envelope = GrantEnvelope.model_validate_json(path.read_text())
    except ValueError as exc:
        raise PublicStop("SESSION03_GRANT_SCHEMA_OR_BINDING_INVALID") from exc
    body = envelope.grant
    base = load_scope()
    if body.source_sha256_fingerprint != fingerprint(source_hashes()):
        raise PublicStop("SESSION03_CURRENT_SOURCE_HASH_MISMATCH")
    if body.documentation_fingerprint != base.grant.documentation_fingerprint:
        raise PublicStop("SESSION03_DOCUMENTATION_FINGERPRINT_MISMATCH")
    fields = {
        id: tuple(next(e for e in base.document["endpoints"] if e["id"] == id)["fields"]) for id in ENDPOINTS
    }
    if body.endpoint_fields != fields:
        raise PublicStop("SESSION03_FIELD_SCOPE_MISMATCH")
    verify_owner(envelope, read_owner_keys() if fabricated_keys is None else fabricated_keys)
    raw = {
        **base.raw,
        "activation_status": "SESSION03_SIGNATURE_VERIFIED",
        "session_id": SESSION_ID,
        "owner_session03_envelope": envelope.model_dump(mode="json"),
    }
    grant = base.grant.model_copy(
        update={
            "grant_id": body.authorization_reference,
            "endpoint_ids": ENDPOINTS,
            "fields": fields,
            "start_utc_ms": body.launch_window_start_utc_ms,
            "end_utc_ms": body.launch_window_end_utc_ms,
            "output_path": body.output_path,
            "connections": 1,
            "subscriptions": 3,
            "policy_hash": fingerprint(body),
            "approval_source_reference": body.authorization_reference,
            "endpoint_calls_per_minute": {ENDPOINTS[0]: 3, ENDPOINTS[1]: 2},
        }
    )
    scope = Session03Scope(
        grant, raw, base.document, path, envelope, fabricated_keys is not None, fingerprint(envelope)
    )
    scope.require_authority(now, native=fabricated_keys is None)
    return scope


def validate_record_window(record):
    """Replay a recorded signed-kernel window; clock evidence separately binds scope_hash."""
    c = record["flex_window_contract"]
    if not isinstance(c, dict):
        raise ValueError("FLEX_WINDOW_BINDING_INVALID")
    if (
        c.get("version") not in LAUNCH_LIMITS
        or c.get("session_id") != SESSION_ID
        or c.get("scope_hash") != record.get("scope_hash")
        or record.get("clock_contract_version") != "L4_CLOCK_DOMAIN_V2"
    ):
        raise ValueError("FLEX_WINDOW_BINDING_INVALID")
    values = [
        c.get(k) for k in ("launch_start_ms", "launch_end_ms", "acquisition_start_ms", "acquisition_end_ms")
    ]
    if any(type(v) is not int or v <= 0 for v in values):
        raise ValueError("FLEX_WINDOW_BOUNDS_INVALID")
    lo, hi, start, end = cast(list[int], values)
    if (
        not lo <= start < end <= hi
        or hi - lo > LAUNCH_LIMITS[c["version"]]
        or end - start > MAX_ACQUISITION_MS
        or record.get("scope_window_ms") != [start, end]
    ):
        raise ValueError("FLEX_WINDOW_BOUNDS_INVALID")
    for key in ("scope_hash", "authorization_digest", "source_fingerprint"):
        value = c.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(x not in "0123456789abcdef" for x in value):
            raise ValueError("FLEX_WINDOW_BINDING_INVALID")


def reconcile(root=SESSION_OUTPUT):
    """Read-only crash inspection; never restart, infer zero requests or repair a marker."""
    root = Path(root)
    check_path(root)
    if not root.exists():
        return {"status": "NOT_CONSUMED", "request_count": 0, "retry_authorized": False}
    report, seal = root / "report.json", root / "receipt_seal.json"
    if report.is_file() and seal.is_file() and not report.is_symlink() and not seal.is_symlink():
        try:
            sealed = json.loads(seal.read_text())
            required = {"report.json", "launch_reservation.json", "owner_signed_grant.json"}
            valid = isinstance(sealed, dict) and required <= set(sealed)
            if valid:
                valid = all(
                    isinstance(n, str)
                    and Path(n).name == n
                    and not (root / n).is_symlink()
                    and sha(root / n) == h
                    for n, h in sealed.items()
                )
            if valid:
                value = json.loads(report.read_text())
                return {
                    "status": "CONSUMED_SEALED",
                    "request_count": value.get("native_market_requests"),
                    "retry_authorized": False,
                }
        except (OSError, ValueError, TypeError):
            pass
    return {"status": "CONSUMED_EXECUTION_UNKNOWN", "request_count": None, "retry_authorized": False}


def run_session03(scope, *, enabled=False, clock=None, backend=None, output=None):
    from .public_runtime import run_public, save_reports

    root = Path(output) if output is not None else scope.output_path
    try:
        return run_public(scope, enabled=enabled, clock=clock, backend=backend, output=output)
    except Exception as exc:
        # Startup can fail after reservation but before a transport object exists.
        if (
            scope.activation
            and root.is_dir()
            and (root / "launch_reservation.json").is_file()
            and not (root / "report.json").exists()
        ):
            result = {
                "status": "BLOCKED",
                "session_id": SESSION_ID,
                "stop_reason": str(exc),
                "native_market_requests": None,
                "request_count_status": "UNKNOWN",
                "replay": {"status": "NOT_AVAILABLE_STARTUP_FAILURE"},
                "source_qualified": False,
                "shadow_advisory_qualified": False,
                "economically_validated": False,
                "external_notifications": 0,
                "account_or_order_operations": 0,
                "retry_authorized": False,
            }
            save_reports(root, result)
            return result
        raise


def requirements():
    return {
        "status": "PREPARED_BUT_NOT_AUTHORIZED",
        "session_id": SESSION_ID,
        "grant_version": VERSION,
        "supported_version_launch_limits_ms": LAUNCH_LIMITS,
        "maximum_launch_window_ms": MAX_LAUNCH_MS,
        "maximum_acquisition_ms": MAX_ACQUISITION_MS,
        "minimum_startup_ms": MIN_STARTUP_MS,
        "output_path": str(SESSION_OUTPUT),
        "source_sha256_fingerprint": fingerprint(source_hashes()),
        "source_files": source_hashes(),
        "canonical_documentation_head": HEAD,
        "owner_keys_installed": bool(read_owner_keys()),
        "owner_grant_created": False,
        "native_market_requests": 0,
        "source_qualified": False,
        "shadow_advisory_qualified": False,
        "economically_validated": False,
        "no_inherited_dates_or_session02_authority": True,
    }
