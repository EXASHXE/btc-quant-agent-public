"""Versioned exact candle capability and canonical integrity helpers; no I/O."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..owner_verifier import verify_signature

ENDPOINT: Literal["wss://fstream.binance.com/market/stream"] = "wss://fstream.binance.com/market/stream"
CLOCK_ENDPOINT: Literal["https://fapi.binance.com/fapi/v1/time"] = "https://fapi.binance.com/fapi/v1/time"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
INTERVALS = ["1h", "4h", "1d"]
STREAMS = [f"{s.lower()}@kline_{i}" for s in SYMBOLS for i in INTERVALS]
REQUIRED_STREAMS = [f"{s.lower()}@kline_{i}" for s in SYMBOLS for i in ("4h", "1d")]


_PERMITS: dict[int, tuple[object, str, str, dict]] = {}


class Stop(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Stop(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def strict(raw):
    def pairs(values):
        result = {}
        for k, v in values:
            require(k not in result, "DUPLICATE_JSON_KEY")
            result[k] = v
        return result

    def invalid(_):
        raise Stop("NONFINITE_JSON")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    require(isinstance(value, dict), "JSON_OBJECT_REQUIRED")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")


class Policy(Strict):
    schema_version: Literal["E_CANDLE_CONFIG_V1"] = "E_CANDLE_CONFIG_V1"
    endpoint: Literal["wss://fstream.binance.com/market/stream"] = ENDPOINT
    clock_endpoint: Literal["https://fapi.binance.com/fapi/v1/time"] = CLOCK_ENDPOINT
    streams: list[str] = Field(default_factory=lambda: list(STREAMS))
    proxy_ip: str
    proxy_port: int = Field(ge=1, le=65535)
    max_frame_bytes: int = Field(default=65536, ge=1024, le=65536)
    queue_high: Literal[96] = 96
    queue_hard: Literal[128] = 128
    uncertainty_max_ms: Literal[100] = 100
    clock_age_ms: Literal[300000] = 300000
    clock_refresh_ms: Literal[120000] = 120000
    wall_step_ms: Literal[50] = 50
    no_reconnect: Literal[True] = True

    @model_validator(mode="after")
    def scope(self):
        import ipaddress

        ipaddress.ip_address(self.proxy_ip)  # No unbounded proxy DNS or alternate-address retries.
        require(self.streams in (STREAMS, REQUIRED_STREAMS), "EXACT_STREAM_SCOPE_REQUIRED")
        return self


class Grant(Strict):
    schema_version: Literal["E_CANDLE_GRANT_V1"] = "E_CANDLE_GRANT_V1"
    exposure: Literal["NATIVE_UNQUALIFIED", "SYNTHETIC_NETWORK"]
    venue: Literal["BINANCE_USDM_FUTURES"] = "BINANCE_USDM_FUTURES"
    endpoint: str
    clock_endpoint: str
    streams: list[str]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    executable_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rights_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{12,100}$")
    output: str
    issued_ms: int
    start_ms: int
    end_ms: int
    messages_max: int = Field(gt=0, le=1000000)
    requests_max: int = Field(ge=3, le=10000)
    outgoing_frames_max: int = Field(ge=2, le=100000)
    storage_bytes_max: int = Field(ge=1048576, le=1073741824)
    retention_seconds: int = Field(gt=0, le=7776000)
    retrospect_REST: Literal[False] = False
    auditor_key_id: str


class Envelope(Strict):
    grant: Grant
    key_id: str
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_base64: str


class AuditBody(Strict):
    schema_version: Literal["E_INDEPENDENT_ADMISSION_V1"] = "E_INDEPENDENT_ADMISSION_V1"
    grant_sha256: str
    rights_sha256: str
    independent_reference: str = Field(min_length=1)


class AuditEnvelope(Strict):
    grant: AuditBody
    key_id: str
    signature_algorithm: Literal["Ed25519"] = "Ed25519"
    signature_base64: str


def verify_key(envelope, roots):
    import base64

    entry = roots.get(envelope.key_id)
    require(
        isinstance(entry, dict) and entry.get("independently_verified") is True, "INDEPENDENT_TRUST_REQUIRED"
    )
    public = base64.b64decode(entry["public_key_base64"], validate=True)
    require(hashlib.sha256(public).hexdigest() == entry.get("public_key_sha256"), "PUBLIC_KEY_FINGERPRINT")
    verify_signature(
        envelope,
        {
            envelope.key_id: {
                "public_key_base64": entry["public_key_base64"],
                "verified_owner_reference": entry.get("verified_owner_reference"),
            }
        },
    )
    return public


def authorize(envelope, audit, roots, policy, *, source_hash, executable_hash, now_ms, exposure):
    owner = verify_key(envelope, roots.get("owner", {}))
    auditor = verify_key(audit, roots.get("auditor", {}))
    g = envelope.grant
    require(owner != auditor and envelope.key_id != audit.key_id == g.auditor_key_id, "AUDITOR_INDEPENDENCE")
    require(
        audit.grant.grant_sha256 == digest(g.model_dump(mode="json"))
        and audit.grant.rights_sha256 == g.rights_sha256 == roots.get("rights_sha256"),
        "AUDITOR_OR_RIGHTS_BINDING",
    )
    require(
        g.endpoint == policy.endpoint
        and g.clock_endpoint == policy.clock_endpoint
        and g.streams == policy.streams,
        "ENDPOINT_OR_STREAM_SCOPE",
    )
    require(g.exposure == exposure, "EXPOSURE_SCOPE")
    require(
        g.source_sha256 == source_hash
        and g.executable_sha256 == executable_hash
        and g.config_sha256 == digest(policy.model_dump(mode="json")),
        "FINAL_BUILD_BINDING",
    )
    require(
        0 < g.issued_ms < g.start_ms <= now_ms < g.end_ms and 0 < g.end_ms - g.start_ms <= 86400000,
        "UTC_WINDOW_CLOSED_OR_INVALID",
    )
    output = Path(g.output)
    require(
        output.is_absolute() and not any(p.is_symlink() for p in (output, *output.parents)),
        "OUTPUT_PATH_UNTRUSTED",
    )
    require(not output.exists(), "OUTPUT_ALREADY_USED")
    if exposure == "NATIVE_UNQUALIFIED":
        installed = strict((Path(__file__).parent / "authority_roots.json").read_bytes())
        require(roots == installed, "INSTALLED_INDEPENDENT_TRUST_REQUIRED")
    _PERMITS[id(g)] = (
        g,
        digest(policy.model_dump(mode="json")),
        source_hash,
        {
            "owner_envelope": envelope.model_dump(mode="json"),
            "admission_auditor": audit.model_dump(mode="json"),
            "independent_trust_sha256": digest(roots),
        },
    )
    return g


def check_permit(grant, policy, local_qa):
    permitted = _PERMITS.get(id(grant))
    require(
        permitted is not None
        and permitted[0] is grant
        and permitted[1] == digest(policy.model_dump(mode="json")),
        "NO_VERIFIED_AUTHORIZATION_CAPABILITY",
    )
    assert permitted is not None
    if grant.exposure == "SYNTHETIC_NETWORK":
        import ipaddress

        require(local_qa and ipaddress.ip_address(policy.proxy_ip).is_loopback, "QA_LOOPBACK_ONLY")
    else:
        require(not local_qa and permitted[2] == source_hash(), "RUNTIME_SOURCE_CHANGED")


def authorization_proof(grant):
    record = _PERMITS.get(id(grant))
    require(record is not None and record[0] is grant, "NO_VERIFIED_AUTHORIZATION_CAPABILITY")
    assert record is not None
    return record[3]


def source_hash():
    root = Path(__file__).resolve().parents[2]
    return digest(
        {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*"))
            if p.is_file() and p.suffix in {".py", ".json", ".yaml", ".jsonl"}
        }
    )
