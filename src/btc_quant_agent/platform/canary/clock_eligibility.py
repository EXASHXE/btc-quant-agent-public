"""Authenticated clock handoff, never acquisition authority.

Historical reports are insufficient by themselves. A distinct, independently
provisioned capture auditor must attest the immutable original capture bundle.
No signing, key provisioning, network access or historical relabeling occurs here.
"""

from __future__ import annotations

import base64
from enum import Enum
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..core import fingerprint, primitive
from . import clock_domain as domain
from .public_policy import ROOT, SYMBOLS, START, END

TRUST = ROOT / "configs/longhorizon/clock_qualification_keys.json"
TRUST_V2 = ROOT / "configs/longhorizon/session04_qualification_keys_v2.json"
DIGEST = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
FAMILIES = {
    "SESSION02_CLOCK_V2_V1": ("L4-NATIVE-CLOCK-V2-SESSION02-20261030", "L4_SESSION02_GRANT_V1", 180000),
    "SESSION03_CLOCK_V2_V1": ("L4-NATIVE-CLOCK-V2-FLEX-SESSION03", "L4_FLEX_SESSION03_GRANT_V1", 21600000),
    "SESSION03_CLOCK_V2_V2": ("L4-NATIVE-CLOCK-V2-FLEX-SESSION03", "L4_FLEX_SESSION03_GRANT_V2", 28800000),
}
FAMILIES_V2 = {
    "SESSION04_RUNTIME_V1": ("L4-NATIVE-RUNTIME-V1-SESSION04", "L4_RUNTIME_SESSION04_GRANT_V1", 28800000),
}
CLOCK_ENDPOINTS = ("binance_usdm_exchange_info", "binance_usdm_server_time", "binance_usdm_bbo_ws")
MAX_BUNDLE_BYTES = 64 * 1024**2


class Reason(str, Enum):
    MISSING = "CQUAL_BUNDLE_MISSING"
    FORMAT = "CQUAL_FORMAT_INVALID"
    FAMILY = "CQUAL_SESSION_VERSION_NOT_ALLOWED"
    ORIGIN = "CQUAL_NATIVE_ACQUISITION_ORIGIN_REQUIRED"
    TRUST = "CQUAL_INDEPENDENT_CAPTURE_TRUST_MISSING"
    OWNER = "CQUAL_EXACT_OWNER_GRANT_NOT_AUTHENTICATED"
    SIGNATURE = "CQUAL_SIGNATURE_INVALID"
    BINDING = "CQUAL_TARGET_SESSION_BINDING_MISMATCH"
    STALE = "CQUAL_EXPIRED_OR_STALE"
    ARTIFACT = "CQUAL_IMMUTABLE_ARTIFACT_MISMATCH"
    SCOPE = "CQUAL_SOURCE_CONFIG_OR_FINGERPRINT_MISMATCH"
    INCOMPLETE = "CQUAL_INCOMPLETE_CAPTURE"
    LINEAGE = "CQUAL_RAW_NORMALIZED_LINEAGE_INVALID"
    CLOCK = "CQUAL_CLOCK_EPOCH_FAULT"
    PROBES = "CQUAL_INDEPENDENT_NATIVE_PROBES_INVALID"
    BBO = "CQUAL_ADMITTED_ORIGINAL_NATIVE_BBO_MISSING"


class QualificationError(ValueError):
    def __init__(self, reason: Reason):
        self.reason = reason
        super().__init__(reason.value)


def require(condition, reason):
    if not condition:
        raise QualificationError(reason)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Key(Strict):
    public_key_base64: str
    public_key_sha256: DIGEST


class OwnerKey(Key):
    family: str
    verified_owner_reference: str
    owner_grant_sha256: DIGEST


class CaptureKey(Key):
    purpose: Literal["INDEPENDENT_NATIVE_CAPTURE_AUDITOR"]
    family: str
    original_receipt_sha256: DIGEST
    receipt_seal_sha256: DIGEST
    owner_grant_sha256: DIGEST
    expires_utc_ms: int = Field(gt=0)


class TrustStore(Strict):
    version: Literal["L4_CLOCK_QUALIFICATION_TRUST_V1"]
    owner_keys: dict[str, OwnerKey]
    capture_keys: dict[str, CaptureKey]


class TrustStoreV2(TrustStore):
    # Deliberate closed discriminator replacement for a separate wire protocol.
    version: Literal["L4_CLOCK_QUALIFICATION_TRUST_V2"]  # type: ignore[assignment]


class BundleBody(Strict):
    version: Literal["L4_CLOCK_QUALIFICATION_BUNDLE_V1"]
    family: str
    source_session_id: str
    grant_version: str
    acquisition_origin: Literal["NATIVE_PUBLIC_CANARY_CAPTURE"]
    exposure: Literal["PUBLIC_CANARY"]
    clock_contract: Literal["L4_CLOCK_DOMAIN_V2"]
    scope_hash: DIGEST
    owner_grant_sha256: DIGEST
    original_receipt_sha256: DIGEST
    receipt_seal_sha256: DIGEST
    source_config_sha256: DIGEST
    source_sha256_fingerprint: DIGEST
    target_binding_sha256: DIGEST
    capture_end_utc_ms: int = Field(gt=0)
    issued_utc_ms: int = Field(gt=0)
    expires_utc_ms: int = Field(gt=0)
    artifacts: dict[str, DIGEST] = Field(min_length=8, max_length=4096)


class Bundle(Strict):
    attestation: BundleBody
    capture_key_id: str
    signature_algorithm: Literal["Ed25519"]
    signature_base64: str


class BundleBodyV2(BundleBody):
    version: Literal["L4_CLOCK_QUALIFICATION_BUNDLE_V2"]  # type: ignore[assignment]
    family: Literal["SESSION04_RUNTIME_V1"]
    predeclared_acceptance_sha256: DIGEST


class BundleV2(Bundle):
    attestation: BundleBodyV2


def canonical(value):
    return json.dumps(primitive(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def family_contract(family, session_id, version, *, bundle_version="L4_CLOCK_QUALIFICATION_BUNDLE_V1"):
    """Pure compatibility lookup. Its result is not native qualification."""
    families = FAMILIES_V2 if bundle_version == "L4_CLOCK_QUALIFICATION_BUNDLE_V2" else FAMILIES
    spec = families.get(family)
    require(spec is not None and spec[:2] == (session_id, version), Reason.FAMILY)
    return spec


def target_binding(grant):
    body = grant.model_dump(mode="json")
    body.pop("clock_qualification_receipt_sha256")
    return fingerprint(body)


def safe_read(path, limit):
    require(not any(p.is_symlink() for p in (path, *path.parents)), Reason.ARTIFACT)
    require(path.is_file() and path.stat().st_size <= limit, Reason.ARTIFACT)
    with path.open("rb") as f:
        data = f.read(limit + 1)
    require(len(data) <= limit, Reason.ARTIFACT)
    return data


def json_value(data):
    def unique(pairs):
        value = {}
        for k, v in pairs:
            require(k not in value, Reason.FORMAT)
            value[k] = v
        return value

    return json.loads(data, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(QualificationError(Reason.FORMAT)))


def verify_sig(key, signature, value):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        raw = base64.b64decode(key.public_key_base64, validate=True)
        require(digest(raw) == key.public_key_sha256, Reason.SIGNATURE)
        Ed25519PublicKey.from_public_bytes(raw).verify(base64.b64decode(signature, validate=True), canonical(value))
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise QualificationError(Reason.SIGNATURE) from exc


def validate_flex_window(record):
    c = record.get("flex_window_contract", {})
    if c.get("version") == "L4_RUNTIME_SESSION04_GRANT_V1":
        return validate_session04_window(record)
    family = {v[1]: k for k, v in FAMILIES.items() if k.startswith("SESSION03")}.get(c.get("version"))
    spec = family_contract(family, c.get("session_id"), c.get("version"))
    values = [c.get(k) for k in ("launch_start_ms", "launch_end_ms", "acquisition_start_ms", "acquisition_end_ms")]
    require(all(type(v) is int and v > 0 for v in values), Reason.SCOPE)
    lo, hi, start, end = values
    require(lo <= start < end <= hi and hi - lo <= spec[2] and end - start <= 180000, Reason.SCOPE)
    require(record.get("scope_window_ms") == [start, end] and c.get("scope_hash") == record.get("scope_hash")
            and record.get("clock_contract_version") == domain.VERSION, Reason.SCOPE)
    for name in ("scope_hash", "authorization_digest", "source_fingerprint"):
        value = c.get(name)
        require(isinstance(value, str) and len(value) == 64 and all(x in "0123456789abcdef" for x in value),
                Reason.SCOPE)


def validate_session04_window(record):
    """Explicit replay compatibility; it grants no capture or eligibility authority."""
    c = record.get("flex_window_contract", {})
    family_contract("SESSION04_RUNTIME_V1", c.get("session_id"), c.get("version"),
                    bundle_version="L4_CLOCK_QUALIFICATION_BUNDLE_V2")
    values = [c.get(k) for k in ("launch_start_ms", "launch_end_ms", "acquisition_start_ms", "acquisition_end_ms")]
    require(all(type(v) is int and v > 0 for v in values), Reason.SCOPE)
    lo, hi, start, end = values
    require(lo <= start < end <= hi and hi - lo <= 28800000 and end - start <= 180000
            and record.get("scope_window_ms") == [start, end] and c.get("scope_hash") == record.get("scope_hash")
            and record.get("clock_contract_version") == domain.VERSION, Reason.SCOPE)
    for name in ("scope_hash", "authorization_digest", "source_fingerprint"):
        value = c.get(name)
        require(isinstance(value, str) and len(value) == 64 and all(x in "0123456789abcdef" for x in value), Reason.SCOPE)


def native_probe_estimate(probes, scope_hash):
    """Recompute the entire conservative retained probe envelope."""
    try:
        estimate = domain.estimate(probes, scope_hash, "PUBLIC_CANARY")
        require(estimate["uncertainty_ms"] <= 100 and
                probes[1]["request"]["mono_before_ms"] - probes[0]["available"]["mono_after_ms"] >= 10,
                Reason.PROBES)
        return estimate
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise QualificationError(Reason.PROBES) from exc


def verify_bundle(path, target_grant, now):
    """Fail closed; all trust is read from the independently provisioned store.

    There is deliberately no fabricated-key/test-authority argument. Offline fake
    captures can exercise parsing/rejection but cannot authorize native preflight.
    """
    if path is None:
        raise QualificationError(Reason.MISSING)
    try:
        return _verify(Path(path), target_grant, now)
    except QualificationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
        raise QualificationError(Reason.FORMAT) from exc


def _verify(path, target, now):
    encoded = safe_read(path, 1024**2)
    require(digest(encoded) == target.clock_qualification_receipt_sha256, Reason.ARTIFACT)
    raw = json_value(encoded)
    a = raw.get("attestation", {})
    require(a.get("acquisition_origin") == "NATIVE_PUBLIC_CANARY_CAPTURE"
            and a.get("exposure") == "PUBLIC_CANARY", Reason.ORIGIN)
    v2 = a.get("version") == "L4_CLOCK_QUALIFICATION_BUNDLE_V2"
    bundle = BundleV2.model_validate_json(encoded) if v2 else Bundle.model_validate_json(encoded)
    b = bundle.attestation
    family_contract(b.family, b.source_session_id, b.grant_version, bundle_version=b.version)
    require(b.target_binding_sha256 == target_binding(target), Reason.BINDING)
    require(b.capture_end_utc_ms <= b.issued_utc_ms <= now < b.expires_utc_ms
            and b.expires_utc_ms - b.capture_end_utc_ms <= 300000, Reason.STALE)
    trust = (TrustStoreV2.model_validate_json(safe_read(TRUST_V2, 65536)) if v2
             else TrustStore.model_validate_json(safe_read(TRUST, 65536)))
    auditor = trust.capture_keys.get(bundle.capture_key_id)
    require(auditor is not None, Reason.TRUST)
    assert auditor is not None
    require(auditor.family == b.family and auditor.original_receipt_sha256 == b.original_receipt_sha256
            and auditor.receipt_seal_sha256 == b.receipt_seal_sha256
            and auditor.owner_grant_sha256 == b.owner_grant_sha256
            and b.expires_utc_ms <= auditor.expires_utc_ms, Reason.TRUST)
    verify_sig(auditor, bundle.signature_base64, b)
    files = {}
    total = 0
    for name, expected in b.artifacts.items():
        relative = PurePosixPath(name)
        require(name == relative.as_posix() and not relative.is_absolute() and ".." not in relative.parts
                and "\\" not in name and len(relative.parts) <= 2, Reason.ARTIFACT)
        data = safe_read(path.parent / name, 16 * 1024**2)
        total += len(data)
        require(total <= MAX_BUNDLE_BYTES and digest(data) == expected, Reason.ARTIFACT)
        files[name] = data
    for name, expected in {"report.json": b.original_receipt_sha256,
                           "receipt_seal.json": b.receipt_seal_sha256,
                           "owner_signed_grant.json": b.owner_grant_sha256,
                           "source_grant.json": b.source_config_sha256}.items():
        require(name in files and digest(files[name]) == expected, Reason.ARTIFACT)
    seal = json_value(files["receipt_seal.json"])
    required = {"report.json", "started.json", "source_grant.json", "source_sha256.json", "endpoint_policy.json",
                "replay_manifest.json"}
    if b.family.startswith(("SESSION03", "SESSION04")):
        required |= {"launch_reservation.json", "owner_signed_grant.json"}
    require(required <= set(seal) and all(name in files and digest(files[name]) == h for name, h in seal.items()),
            Reason.ARTIFACT)
    original = json_value(files["owner_signed_grant.json"])
    grant = original["grant"]
    owner = trust.owner_keys.get(original["key_id"])
    require(owner is not None, Reason.OWNER)
    assert owner is not None
    require(owner.family == b.family and owner.owner_grant_sha256 == b.owner_grant_sha256
            and owner.verified_owner_reference == grant["authorization_reference"]
            and owner.public_key_sha256 != auditor.public_key_sha256
            and original["key_id"] != bundle.capture_key_id
            and original["signature_algorithm"] == "Ed25519", Reason.OWNER)
    verify_sig(owner, original["signature_base64"], grant)
    verify_capture(b, grant, original, files, target, now)
    return {"status": "AUTHENTICATED_CLOCK_ELIGIBILITY_ONLY", "family": b.family,
            "original_receipt_sha256": b.original_receipt_sha256, "native_acquisition_authorized": False}


def verify_capture(b, grant, envelope, files, target, now):
    from .public_data import normalize

    spec = family_contract(b.family, grant["session_id"], grant["version"], bundle_version=b.version)
    flex = b.family.startswith(("SESSION03", "SESSION04"))
    session04 = b.family == "SESSION04_RUNTIME_V1"
    source = json_value(files["source_grant.json"])
    started = json_value(files["started.json"])
    report = json_value(files["report.json"])
    policy = json_value(files["endpoint_policy.json"])
    hashes = json_value(files["source_sha256.json"])
    require(fingerprint(hashes) == b.source_sha256_fingerprint == grant["source_sha256_fingerprint"]
            and fingerprint(grant) == b.scope_hash == source["policy_hash"] == started["scope_hash"], Reason.SCOPE)
    require(grant["provider"] == target.provider == source["provider"] == "binance"
            and grant["market"] == target.market == "USD_M_USDT_LINEAR_PERPETUAL"
            and source["market"] == "USD_M" and tuple(grant["symbols"]) == tuple(source["symbols"]) == SYMBOLS
            and tuple(grant["endpoint_ids"]) == tuple(source["endpoint_ids"]) == CLOCK_ENDPOINTS
            and grant["endpoint_fields"] == source["fields"]
            and grant["output_path"] == source["output_path"]
            and source["grant_id"] == started["owner"] == grant["authorization_reference"]
            and started["session_id"] == report["session_id"] == b.source_session_id
            and started["owner_authorization_digest"] == fingerprint(envelope)
            and policy["session_id"] == b.source_session_id
            and policy["owner_session04_envelope" if session04 else "owner_session03_envelope" if flex else
                       "owner_session02_envelope"] == envelope
            and started["egress_route"] == report["transport_metrics"]["egress_route"]
            and all(started["egress_route"].get(k) == v for k, v in target.egress_route.items()), Reason.SCOPE)
    approved = policy["policy"]["egress"]
    require(started["egress_route"].get("egress_mode") == "CONTROLLED_EGRESS_PROXY"
            and all(started["egress_route"].get(k) == approved[k] for k in ("proxy_host", "proxy_port"))
            and started["egress_route"]["tunnel_type"] in approved["tunnel_types"], Reason.SCOPE)
    constants = {"clock_contract": domain.VERSION, "wall_jump_ms": 50, "max_offset_uncertainty_ms": 100,
                 "max_probe_age_ms": 300000, "startup_independent_probes": 2, "startup_probe_gap_ms": 10,
                 "subsequent_probe_interval_ms": 120000, "rest_weight_per_minute": 60,
                 "retry_reserve_weight_per_minute": 10, "time_calls_per_minute": 2, "controls_per_second": 2,
                 "connections": 1, "subscriptions": 3, "reconnects_per_hour": 3,
                 "raw_retention_hours": 36, "normalized_retention_hours": 168,
                 "raw_bytes": 8589934592, "auxiliary_bytes": 4294967296,
                 "account_or_order_operations": False, "external_notifications": False}
    if session04:
        from .session04_acceptance import evaluate

        constants.update(trial_purpose="DIAGNOSTIC_RUNTIME_ONLY",
                         unresolved_native_reliability_explicitly_accepted=True,
                         ws_messages_per_second=200, pending_records=128, automatic_restart=False,
                         automatic_request_retry=False, automatic_reconnect=False)
        require(evaluate(report)["passed"] and report["status"] == "DIAGNOSTIC_ONLY", Reason.INCOMPLETE)
        require(isinstance(b, BundleBodyV2)
                and grant["predeclared_acceptance_sha256"] == b.predeclared_acceptance_sha256
                and hashes.get("SESSION04_PREDECLARED_NATIVE_ACCEPTANCE.json") == b.predeclared_acceptance_sha256
                and grant["egress_route"] == target.egress_route
                and grant["canonical_documentation_head"] == "caf9af0489ca5002c2c6deb17305efc591f2e32e"
                and grant["documentation_fingerprint"] == source["documentation_fingerprint"]
                and Path(grant["output_path"]).parts[-3:] == ("artifacts", "live_public_canary_runtime_v1", "session_04")
                and json_value(files["launch_reservation.json"])["version"] == "L4_SESSION04_RESERVATION_V1", Reason.SCOPE)
    require(all(type(grant.get(k)) is type(v) and grant[k] == v for k, v in constants.items()), Reason.SCOPE)
    variable = {"version", "session_id", "authorization_reference", "provider", "market", "permitted_use",
                "symbols", "endpoint_ids", "endpoint_fields", "output_path", "issued_utc_ms",
                "source_sha256_fingerprint", "canonical_documentation_head", "documentation_fingerprint"}
    if session04:
        variable |= {"predeclared_acceptance_sha256", "egress_route"}
    specific = ({"authorized_operator_key_id", "allowed_hostnames", "launch_window_start_utc_ms",
                 "launch_window_end_utc_ms", "max_acquisition_ms", "minimum_startup_ms"}
                if flex else {"start_utc_ms", "end_utc_ms"})
    require(set(grant) == variable | specific | set(constants)
            and grant["permitted_use"] == target.permitted_use
            and source["ip_weight_per_minute"] == 60 and source["connections"] == 1
            and source["subscriptions"] == 3 and source["bytes_total"] == 12 * 1024**3
            and source["raw_retention_hours"] == 36 and source["normalized_retention_hours"] == 168, Reason.SCOPE)
    start, end = started["started_wall_ms"], started["end_unchanged"]
    if flex:
        lo, hi = grant["launch_window_start_utc_ms"], grant["launch_window_end_utc_ms"]
        reservation = json_value(files["launch_reservation.json"])
        require(reservation["fabricated_authority"] is False, Reason.ORIGIN)
        require(grant["authorized_operator_key_id"] == envelope["key_id"]
                and grant["allowed_hostnames"] == ["fapi.binance.com", "fstream.binance.com"]
                and reservation["scope_hash"] == b.scope_hash and reservation["authorization_digest"] == fingerprint(envelope)
                and reservation["actual_start_ms"] == start and reservation["actual_end_ms"] == end
                and end == min(start + 180000, hi) and grant["max_acquisition_ms"] == 180000
                and grant["minimum_startup_ms"] == 25000, Reason.SCOPE)
    else:
        lo, hi = grant["start_utc_ms"], grant["end_utc_ms"]
        require(START <= grant["issued_utc_ms"] <= lo < hi <= END, Reason.SCOPE)
    require(grant["issued_utc_ms"] <= lo <= start < end <= hi and 0 < hi - lo <= spec[2]
            and end - start <= 180000 and report["stopped_wall_ms"] == b.capture_end_utc_ms
            and source["start_utc_ms"] == lo and source["end_utc_ms"] == hi
            and report["scope_hash"] == b.scope_hash and report["owner"] == grant["authorization_reference"]
            and report["started_wall_ms"] == start and report["authorized_end_exclusive_ms"] == end
            and report["authorized_start_ms"] == (start if flex else lo), Reason.SCOPE)
    require(started["exposure"] == report["exposure"] == "PUBLIC_CANARY", Reason.ORIGIN)
    evidence = report["clock_validation_evidence"]
    require(evidence["clock_fault"] is None and not report.get("model", {}).get("clock_epoch_failure"), Reason.CLOCK)
    require(report["sockets_closed"] is True and report["receiver_threads_stopped"] is True
            and not report["finalization_errors"] and not report["uncommitted_or_unapplied_frames"]
            and report["stop_reason"] in ("AUTHORIZED_UTC_END", "GRANT_WINDOW_EXPIRED", "SESSION02_GRANT_EXPIRED",
                                          "SESSION03_WINDOW_EXPIRED", "SESSION04_WINDOW_EXPIRED"), Reason.INCOMPLETE)
    replay = json_value(files["replay_manifest.json"])
    require(replay == report["replay"] and replay["status"] == "PARITY_VERIFIED"
            and replay["unpaired_raw_chunks"] == 0 and replay["expired_chunks"] == 0, Reason.INCOMPLETE)
    previous = None
    chunks: set[str] = set()
    raw_chunks: dict[str, dict] = {}
    probes: dict[str, dict] = {}
    quotes: list[dict] = []
    samples: list[dict] = []
    paired = set()
    record_count = expanded_total = 0
    for row in replay["manifest"]:
        h, kind = row["sha256"], row["kind"]
        require(h not in chunks and row["previous_sha256"] == previous and kind in ("raw", "normalized"),
                Reason.LINEAGE)
        name = kind + "/" + h + ".json.gz"
        require(name in files and digest(files[name]) == h, Reason.LINEAGE)
        require(len(files[name]) == row["bytes"] and row["bytes"] <= 1024**2, Reason.LINEAGE)
        with gzip.GzipFile(fileobj=io.BytesIO(files[name])) as f:
            expanded = f.read(16 * 1024**2 + 1)
        expanded_total += len(expanded)
        require(len(expanded) <= 16 * 1024**2 and expanded_total <= MAX_BUNDLE_BYTES, Reason.LINEAGE)
        chunk = json_value(expanded)
        require(chunk["kind"] == kind and chunk["previous_sha"] == previous
                and chunk["exposure"] == "PUBLIC_CANARY" and chunk["format"] == "L4-PUBLIC-GZIP-1"
                and chunk["normalizer"] == "L4-PUBLIC-NORMALIZER-1"
                and all(chunk[k] == row[k] for k in ("start_ms", "end_ms", "expires_ms")), Reason.LINEAGE)
        chunks.add(h)
        previous = h
        if kind == "normalized":
            raw = raw_chunks.get(row["raw_sha"])
            if raw is None:
                raise QualificationError(Reason.LINEAGE)
            require(chunk["raw_sha"] == row["raw_sha"] and row["raw_sha"] not in paired, Reason.LINEAGE)
            require(primitive([normalize(r) for r in raw["records"]]) == chunk["records"], Reason.LINEAGE)
            paired.add(row["raw_sha"])
            continue
        raw_chunks[h] = chunk
        for record in chunk["records"]:
            record_count += 1
            require(record_count <= 50000, Reason.INCOMPLETE)
            wire = record["wire"]
            require(record["exposure"] == wire["exposure"] == "PUBLIC_CANARY", Reason.ORIGIN)
            require(record["scope_hash"] == b.scope_hash and record["scope_window_ms"] == [start, end]
                    and record["clock_contract_version"] == domain.VERSION, Reason.SCOPE)
            if flex:
                validate_flex_window(record)
                require(record["flex_window_contract"]["authorization_digest"] == fingerprint(envelope)
                        and record["flex_window_contract"]["source_fingerprint"] == b.source_sha256_fingerprint,
                        Reason.SCOPE)
            # First-byte clock evidence is explicitly optional in the native
            # wire schema. Required receive/available/request clocks still pass
            # through normalize and probe verification below.
            samples.extend([*(v for k, v in wire["clock_samples"].items() if k != "first" or v is not None), record["decision_sample"],
                            record["normalization_sample"]])
            require(domain.same_epoch(samples) is None, Reason.CLOCK)
            samples = samples[:1]
            result = normalize(record)
            require(not any("CLOCK" in reason or "EPOCH" in reason for reason in result["reasons"]), Reason.CLOCK)
            if wire["endpoint_id"] == CLOCK_ENDPOINTS[1]:
                require(result["status"] == "SERVER_CLOCK_SAMPLE", Reason.PROBES)
                p = {"request": wire["clock_samples"]["request"], "receive": wire["clock_samples"]["receive"],
                     "available": record["normalization_sample"], "server_ms": result["serverTime"],
                     "scope_hash": b.scope_hash, "wire_id": fingerprint(wire), "exposure": "PUBLIC_CANARY"}
                require(p["wire_id"] not in probes, Reason.PROBES)
                probes[p["wire_id"]] = p
            if result.get("quote"):
                clock = record["clock"]
                retained = [p for p in probes.values() if
                            record["decision_mono_ms"] - p["available"]["mono_before_ms"] <= 300000]
                require(clock["probes"] == retained, Reason.PROBES)
                estimate = native_probe_estimate(clock["probes"], b.scope_hash)
                require(estimate == clock, Reason.PROBES)
                payload = json_value(wire["payload_text"])["data"]
                require(payload["E"] == result["quote"]["provenance"]["exchange_event_ts"]
                        and payload["T"] == result["native_transaction_ms"], Reason.BBO)
                quotes.append(record)
    require(set(raw_chunks) == paired and len(paired) == replay["checked_pairs"], Reason.LINEAGE)
    pp = list(probes.values())
    native_probe_estimate(pp, b.scope_hash)
    require(quotes and sum(evidence["distinct_qualified_quotes"].values()) >= 1, Reason.BBO)
    require(0 <= now - max(p["available"]["wall_ms"] for p in pp) <= 300000, Reason.STALE)
    # Every projected instrument must trace to an original immutable metadata wire.
    for chunk in raw_chunks.values():
        for r in chunk["records"]:
            m = r.get("metadata")
            if not m:
                continue
            origin = raw_chunks.get(m.get("source_raw_chunk_sha"))
            if origin is None:
                raise QualificationError(Reason.LINEAGE)
            original = [x["wire"] for x in origin["records"]
                        if fingerprint(x["wire"]) == m.get("projection_source_wire_sha")]
            require(len(original) == 1, Reason.LINEAGE)
            native = json_value(original[0]["payload_text"])
            projection = json_value(m["wire"]["payload_text"])
            require(all([x for x in native["symbols"] if x.get("symbol") == item.get("symbol")] == [item]
                        for item in projection["symbols"]), Reason.LINEAGE)
