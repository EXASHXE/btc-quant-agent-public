"""Independent, signed, finite SourceGrant for the prospective 48-hour pilot.

Nothing in this module authorizes acquisition. The shipped trust store is empty.
Session02's grant, clock qualification and keys are never imported as authority.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import shutil
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core import fingerprint
from . import clock_domain as domain
from .policy import ROOT, SourceGrant
from .public_policy import PublicScope, PublicStop, REST, IDS, SYMBOLS, sha
from .clock_eligibility import verify_bundle, QualificationError, FAMILIES, FAMILIES_V2

HEAD = "79ebe3d2cd9326fc74b44c0c2983abf93444a1ba"
PROFILE = "L4_LONGHORIZON_V1"
SESSION = "L4-LONGHORIZON-SOURCE-SHADOW-01"
OUTPUT = ROOT / "artifacts/prospective_48h/session_01"
CONFIG = ROOT / "configs/longhorizon"
DOCUMENT = ROOT / "configs/canary/public_endpoints_20261030.json"
TRUST = CONFIG / "owner_keys.json"
MAX_DURATION = 48 * 3_600_000
CAPS = {"binance_usdm_exchange_info": 3, "binance_usdm_server_time": 2,
        "binance_usdm_klines_rest": 12, "binance_usdm_oi": 6,
        "binance_usdm_premium": 3, "binance_usdm_funding_info": 2,
        "binance_usdm_turnover": 1}
APPROVED_ROUTE = {"egress_mode": "CONTROLLED_EGRESS_PROXY", "proxy_host": "127.0.0.1",
                  "proxy_port": 7897, "tunnel_type": "HTTP_CONNECT"}


def source_hashes():
    files = [p for p in (ROOT / "src").rglob("*.py")]
    files += list(CONFIG.glob("*.json"))
    files += [ROOT / "tools/launch_longhorizon.py", ROOT / "tools/demo_clock_eligibility.py", ROOT / "pyproject.toml",
              DOCUMENT, ROOT / "configs/canary/endpoints.json"]
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(files)}


class GrantBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal["L4_LONGHORIZON_SOURCE_GRANT_V1"]
    session_id: Literal["L4-LONGHORIZON-SOURCE-SHADOW-01"]
    authorization_reference: str = Field(pattern=r"^OWNER-V070-L4-LONGHORIZON-[A-Z0-9_-]+$")
    provider: Literal["binance"]
    market: Literal["USD_M_USDT_LINEAR_PERPETUAL"]
    permitted_use: Literal["OWNER_CONFIRMED_PERSONAL_NONCOMMERCIAL_PUBLIC_READONLY"]
    symbols: tuple[str, ...]
    endpoint_ids: tuple[str, ...]
    endpoint_fields: dict[str, tuple[str, ...]]
    output_relative_path: Literal["artifacts/prospective_48h/session_01"]
    issued_utc_ms: int = Field(gt=0)
    start_utc_ms: int = Field(gt=0)
    end_utc_ms: int = Field(gt=0)
    source_sha256_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_documentation_head: Literal["79ebe3d2cd9326fc74b44c0c2983abf93444a1ba"]
    documentation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    clock_qualification_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    egress_route: dict
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
    connections: Literal[2]
    subscriptions: Literal[9]
    reconnects_per_hour: Literal[3]
    ws_messages_per_second: Literal[200]
    pending_records: Literal[128]
    max_retries: Literal[3]
    repair_calls_per_minute: Literal[6]
    repair_rows_per_call: Literal[99]
    raw_retention_hours: Literal[36]
    normalized_retention_hours: Literal[168]
    raw_bytes: Literal[8589934592]
    auxiliary_bytes: Literal[4294967296]
    disk_reserve_bytes: Literal[2147483648]
    automatic_restart: Literal[False]
    external_notifications: Literal[False]
    account_or_order_operations: Literal[False]

    @model_validator(mode="after")
    def exact_scope(self):
        if self.symbols != SYMBOLS or self.endpoint_ids != IDS:
            raise ValueError("LONGHORIZON_EXACT_SYMBOLS_AND_NINE_ENDPOINTS_REQUIRED")
        if not self.issued_utc_ms <= self.start_utc_ms < self.end_utc_ms:
            raise ValueError("LONGHORIZON_UTC_SCOPE_INVALID")
        if self.end_utc_ms - self.start_utc_ms > MAX_DURATION:
            raise ValueError("LONGHORIZON_DURATION_EXCEEDS_48H")
        if self.egress_route != {"egress_mode": "DIRECT"}:
            if (set(self.egress_route) != {"egress_mode", "proxy_host", "proxy_port", "tunnel_type"}
                or self.egress_route["egress_mode"] != "CONTROLLED_EGRESS_PROXY"
                or self.egress_route["tunnel_type"] not in ("HTTP_CONNECT", "SOCKS5", "SOCKS5H")
                or not isinstance(self.egress_route["proxy_host"], str)
                or not self.egress_route["proxy_host"]
                or type(self.egress_route["proxy_port"]) is not int
                or not 1 <= self.egress_route["proxy_port"] <= 65535):
                raise ValueError("LONGHORIZON_EXACT_EGRESS_ROUTE_REQUIRED")
        return self


class GrantEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    grant: GrantBody
    key_id: str = Field(min_length=1, max_length=128)
    signature_algorithm: Literal["Ed25519"]
    signature_base64: str


def signed_bytes(body):
    return json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def verify_signature(envelope):
    if TRUST.is_symlink():
        raise PublicStop("LONGHORIZON_UNTRUSTED_OWNER_KEY_STORE")
    trust = json.loads(TRUST.read_text())
    if set(trust) != {"version", "keys"} or trust["version"] != "L4_LONGHORIZON_OWNER_KEYS_V1":
        raise PublicStop("LONGHORIZON_OWNER_KEY_STORE_INVALID")
    entry = trust["keys"].get(envelope.key_id)
    if (not entry or set(entry) != {"public_key_base64", "verified_owner_reference"}
        or entry["verified_owner_reference"] != envelope.grant.authorization_reference):
        raise PublicStop("LONGHORIZON_DISTINCT_OWNER_AUTHORIZATION_NOT_PROVISIONED")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(entry["public_key_base64"], validate=True))
        key.verify(base64.b64decode(envelope.signature_base64, validate=True), signed_bytes(envelope.grant))
    except (KeyError, ValueError, TypeError, InvalidSignature) as exc:
        raise PublicStop("LONGHORIZON_OWNER_SIGNATURE_INVALID") from exc


class FiniteWindow:
    """New bounds with the unchanged 50ms, sticky Clock Domain V2 contract."""
    def __init__(self, clock, start_ms, end_ms):
        if type(start_ms) is not int or type(end_ms) is not int or not 0 < end_ms - start_ms <= MAX_DURATION:
            raise PublicStop("LONGHORIZON_WINDOW_INVALID")
        self.clock, self.start_ms, self.end_ms = clock, start_ms, end_ms
        self.wall0, self.mono0, self.sample0 = domain.capture(clock)
        self.mono_end = self.mono0 + end_ms - self.wall0 - getattr(clock, "utc_uncertainty_ms", 0)
        self.stop_reason = None

    def check(self):
        wall, mono, sample = domain.capture(self.clock)
        uncertainty = getattr(self.clock, "utc_uncertainty_ms", 0)
        self.mono_end = min(self.mono_end, mono + self.end_ms - wall - uncertainty)
        reason = (domain.sample_reason(sample) or domain.same_epoch([self.sample0, sample])
                  if sample is not None else "CLOCK_DOMAIN_V2_REQUIRED")
        if abs((wall - self.wall0) - (mono - self.mono0)) > 50:
            reason = "LOCAL_WALL_CLOCK_JUMP"
        if reason:
            self.stop_reason = self.stop_reason or reason
        if self.stop_reason:
            raise PublicStop(self.stop_reason)
        if wall + uncertainty >= self.end_ms or mono >= self.mono_end:
            self.stop_reason = "GRANT_WINDOW_EXPIRED"
            raise PublicStop(self.stop_reason)
        if wall - uncertainty < self.start_ms:
            raise PublicStop("GRANT_WINDOW_NOT_OPEN")
        return min(self.end_ms - wall - uncertainty, self.mono_end - mono) / 1000


@dataclass(frozen=True)
class LongScope(PublicScope):
    authorization: GrantEnvelope
    fabricated_authority: bool
    authorization_digest: str
    clock_receipt: Path | None = None
    run_profile: str = PROFILE
    native_preflight_digest: str | None = None

    @property
    def start_ms(self):
        return self.authorization.grant.start_utc_ms

    @property
    def end_ms(self):
        return self.authorization.grant.end_utc_ms

    @property
    def output_path(self):
        return OUTPUT

    def make_window(self, clock):
        return FiniteWindow(clock, self.start_ms, self.end_ms)

    def require_authority(self, now, *, native):
        if fingerprint(self.authorization) != self.authorization_digest:
            raise PublicStop("LONGHORIZON_AUTHORIZATION_MUTATED")
        if native and self.fabricated_authority:
            raise PublicStop("FABRICATED_AUTHORITY_CANNOT_ACTIVATE_NATIVE")
        if native and self.native_preflight_digest != fingerprint(self.authorization):
            raise PublicStop("LONGHORIZON_NATIVE_PREFLIGHT_REQUIRED")
        if now < self.start_ms:
            raise PublicStop("GRANT_WINDOW_NOT_OPEN")
        if now >= self.end_ms:
            raise PublicStop("GRANT_WINDOW_EXPIRED")

    def validate_route(self, route):
        declared = self.authorization.grant.egress_route
        if any(route.get(k) != v for k, v in declared.items()):
            raise PublicStop("LONGHORIZON_EGRESS_ROUTE_GRANT_MISMATCH")

    def verify_document_baseline(self):
        if sha(DOCUMENT) != self.authorization.grant.documentation_sha256:
            raise PublicStop("LONGHORIZON_DOCUMENT_HASH_MISMATCH")
        return {"status": "FROZEN_OFFICIAL_SEMANTIC_BASELINE_VERIFIED", "native_source_verified": False,
                "unknowns": self.document["unknowns"], "canonical_head": HEAD}

    def denial_reason(self):
        path = OUTPUT.parent / "source_access_denial.json"
        if path.is_symlink():
            return "SOURCE_ACCESS_STATE_INVALID"
        return "VENUE_ACCESS_DENIED_PERSISTED" if path.exists() else None

    def persist_denial(self, value):
        path = OUTPUT.parent / "source_access_denial.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("x") as f:
                json.dump(value, f, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
        except FileExistsError:
            pass

    def validate_request(self, id, params, now):
        self.require_authority(now, native=False)
        if id not in REST or id not in self.grant.endpoint_ids:
            raise PublicStop("ENDPOINT_FORBIDDEN")
        if id in ("binance_usdm_oi", "binance_usdm_premium", "binance_usdm_turnover"):
            if set(params) != {"symbol"} or params["symbol"] not in SYMBOLS:
                raise PublicStop("SYMBOL_OR_PARAMETER_SCOPE_VIOLATION")
        elif id == "binance_usdm_klines_rest":
            if set(params) != {"symbol", "interval", "startTime", "endTime", "limit"}:
                raise PublicStop("KLINE_SCOPE_VIOLATION")
            size = {"1m": 60000, "5m": 300000}.get(params["interval"])
            lo, hi = params["startTime"], params["endTime"]
            if (params["symbol"] not in SYMBOLS or size is None
                or any(type(params[k]) is not int for k in ("startTime", "endTime", "limit"))
                or not 1 <= params["limit"] <= 99 or not self.start_ms <= lo <= hi < min(now, self.end_ms)
                or lo % size or (hi + 1) % size or hi - lo + 1 > params["limit"] * size):
                raise PublicStop("KLINE_OUTSIDE_PROSPECTIVE_BOUNDED_REPAIR")
        elif params:
            raise PublicStop("UNAPPROVED_PARAMETERS")
        return "https://fapi.binance.com" + REST[id]

    def budget_policy(self):
        return super().budget_policy().model_copy(update={"synthetic_start_ms": self.start_ms,
                                                        "duration_ms": self.end_ms - self.start_ms})

    def preflight(self, clock, *, native):
        if native:
            object.__setattr__(self, "native_preflight_digest", None)
            if self.fabricated_authority:
                raise PublicStop("FABRICATED_AUTHORITY_CANNOT_ACTIVATE_NATIVE")
        self.require_authority(clock.wall(), native=False)
        self.verify_document_baseline()
        if fingerprint(source_hashes()) != self.authorization.grant.source_sha256_fingerprint:
            raise PublicStop("LONGHORIZON_CURRENT_SOURCE_HASH_MISMATCH")
        reasons = []
        if native:
            verify_signature(self.authorization)
            if self.authorization.grant.egress_route != APPROVED_ROUTE:
                reasons.append("LONGHORIZON_APPROVED_CONTROLLED_EGRESS_REQUIRED")
            if denied := self.denial_reason():
                reasons.append(denied)
            try:
                verify_bundle(self.clock_receipt, self.authorization.grant, clock.wall())
            except QualificationError as exc:
                reasons.append(exc.reason.value)
            for name, expected in {"httpx": "0.28.1", "httpcore": "1.0.9", "websockets": "16.1.1"}.items():
                try:
                    actual = version(name)
                except PackageNotFoundError:
                    actual = "MISSING"
                if actual != expected:
                    reasons.append("PUBLIC_DEPENDENCY_VERSION_UNTESTED:" + name)
        for p in (OUTPUT, *OUTPUT.parents):
            if p.is_symlink():
                reasons.append("SYMLINK_OUTPUT_FORBIDDEN")
        if native and OUTPUT.exists():
            reasons.append("LONGHORIZON_ALREADY_CLAIMED_NEVER_RESET")
        usage = shutil.disk_usage(ROOT)
        if usage.free < 14 * 1024**3:
            reasons.append("STORAGE_SCOPE_BLOCKED")
        age = clock.wall() - int(datetime.fromisoformat(self.document["reviewed_utc"]).timestamp() * 1000)
        if not 0 <= age <= 7 * 86400000:
            reasons.append("DOCUMENTATION_REVIEW_EXPIRED")
        self.make_window(clock).check()
        if native and not reasons:
            # Direct transport construction cannot skip signature, native-clock,
            # source, quota and output gates. Grant mutation invalidates this token.
            object.__setattr__(self, "native_preflight_digest", fingerprint(self.authorization))
        return {"status": "BLOCKED" if reasons else "TECHNICAL_PREFLIGHT_PASSED", "reasons": reasons,
                "window_status": "OPEN", "available_disk_bytes": usage.free,
                "required_with_reserve_bytes": 14 * 1024**3, "native_market_calls": 0,
                "source_qualified": False, "shadow_advisory_qualified": False}


def make_scope(envelope, *, fabricated=False, clock_receipt=None):
    body = envelope.grant
    document = json.loads(DOCUMENT.read_text())
    fields = {e["id"]: tuple(e["fields"]) for e in document["endpoints"]}
    if body.endpoint_fields != fields:
        raise PublicStop("LONGHORIZON_EXACT_FIELD_SCOPE_REQUIRED")
    grant = SourceGrant.model_validate({
        "grant_id": body.authorization_reference,
        "authority": "FABRICATED_TEST_GRANT" if fabricated else "OWNER_EXACT_SOURCE_GRANT",
        "provider": "binance", "region": "NOT_INDEPENDENTLY_OBSERVED", "market": "USD_M",
        "hosts": ("https://fapi.binance.com", "wss://fstream.binance.com"), "endpoint_ids": IDS,
        "fields": fields, "symbols": SYMBOLS, "start_utc_ms": body.start_utc_ms,
        "end_utc_ms": body.end_utc_ms, "ip_weight_per_minute": 60, "endpoint_calls_per_minute": CAPS,
        "controls_per_second": 2, "subscriptions": 9, "connections": 2, "reconnects_per_hour": 3,
        "bytes_total": 12 * 1024**3, "raw_retention_hours": 36, "normalized_retention_hours": 168,
        "output_path": str(OUTPUT), "permitted_use_status": "FABRICATED_TEST_ONLY" if fabricated
        else "EXPLICITLY_OWNER_CONFIRMED", "policy_hash": fingerprint(body),
        "documentation_fingerprint": fingerprint(document), "approval_source_reference": body.authorization_reference})
    raw = {"session_id": SESSION, "policy": {}, "storage": {
        "raw_bytes": body.raw_bytes, "auxiliary_bytes": body.auxiliary_bytes,
        "reserve_bytes": body.disk_reserve_bytes}}
    return LongScope(grant, raw, document, CONFIG / "grant.schema.json", envelope, fabricated,
                     fingerprint(envelope), Path(clock_receipt) if clock_receipt else None)


def load_grant(path, clock_receipt=None):
    envelope = GrantEnvelope.model_validate_json(Path(path).read_bytes())
    verify_signature(envelope)
    return make_scope(envelope, clock_receipt=clock_receipt)


def requirements():
    return {"status": "OFFLINE_READY_PENDING_EXACT_OWNER_GRANT", "native_decision": "NO_GO_NATIVE_SOURCE",
            "session_id": SESSION, "max_duration_ms": MAX_DURATION, "owner_grant_created": False,
            "longhorizon_owner_keys_installed": bool(json.loads(TRUST.read_text())["keys"]),
            "source_sha256_fingerprint": fingerprint(source_hashes()), "canonical_head": HEAD,
            "output_relative_path": str(OUTPUT.relative_to(ROOT)), "clock_qualification_required": True,
            "clock_qualification_bundle_version": "L4_CLOCK_QUALIFICATION_BUNDLE_V1",
            "clock_qualification_families": FAMILIES,
            "session04_candidate_bundle_version": "L4_CLOCK_QUALIFICATION_BUNDLE_V2",
            "session04_candidate_families": FAMILIES_V2,
            "source_qualified": False, "shadow_advisory_qualified": False, "alpha_claim": False,
            "native_market_calls": 0, "scheduler_or_automatic_successor": False}
