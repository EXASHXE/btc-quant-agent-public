"""Offline-only candle admission checks using the original Owner verifier.

No socket, capture path or installed trust is provided. Passing a synthetic test
never authorizes native acquisition. Owner and auditor stores are external inputs.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .owner_verifier import PublicStop, verify_signature

ENDPOINT = "wss://fstream.binance.com/market/stream"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
TIMEFRAMES = ("1h", "4h", "1d")


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal["D_CANDLE_PREFLIGHT_NON_EXECUTING_V1"]
    venue: Literal["BINANCE_USDM_FUTURES"]
    endpoint: str
    symbols: list[str]
    timeframes: list[str]
    source_sha256: str
    config_sha256: str
    session_id: str = Field(min_length=10)
    output: str = Field(min_length=1)
    start_utc_ms: int
    end_utc_ms: int
    issued_utc_ms: int
    requests_max: int = Field(gt=0)
    storage_bytes_max: int = Field(gt=0)
    retention_seconds_max: int = Field(gt=0)
    rights_reference: str = Field(min_length=1)
    retrospective_rest: Literal[False]
    auditor_key_id: str


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    grant: Grant
    key_id: str
    signature_algorithm: Literal["Ed25519"]
    signature_base64: str


class AuditBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    grant_sha256: str
    runtime_sha256: str
    checked_utc_ms: int


class AuditEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    grant: AuditBody
    key_id: str
    signature_algorithm: Literal["Ed25519"]
    signature_base64: str


def _require(condition, reason):
    if not condition:
        raise PublicStop(reason)


def _verify(envelope, store):
    entry = store.get(envelope.key_id)
    _require(isinstance(entry, dict), "INDEPENDENT_TRUST_MISSING")
    raw = base64.b64decode(entry.get("public_key_base64", ""), validate=True)
    _require(len(raw) == 32 and hashlib.sha256(raw).hexdigest() == entry.get("public_key_sha256"),
             "PUBLIC_KEY_FINGERPRINT_MISMATCH")
    _require(entry.get("independently_verified") is True, "INDEPENDENT_TRUST_UNVERIFIED")
    verify_signature(envelope, {envelope.key_id: {
        "public_key_base64": entry["public_key_base64"],
        "verified_owner_reference": entry.get("verified_owner_reference")}})
    return raw


def preflight(envelope, *, owner_trust, auditor_trust, auditor, expected_source,
              expected_config, now_ms, runtime, used_sessions, used_outputs):
    from .core import fingerprint
    owner = _verify(envelope, owner_trust)
    g = envelope.grant
    _require(g.endpoint == ENDPOINT and g.venue == "BINANCE_USDM_FUTURES", "ENDPOINT_UNAUTHORIZED")
    _require(g.symbols == list(SYMBOLS), "SYMBOL_UNAUTHORIZED")
    _require(g.timeframes == list(TIMEFRAMES), "TIMEFRAME_UNAUTHORIZED")
    _require(len(expected_source) == 64 and g.source_sha256 == expected_source, "SOURCE_FINGERPRINT_CHANGED")
    _require(len(expected_config) == 64 and g.config_sha256 == expected_config, "CONFIG_FINGERPRINT_CHANGED")
    _require(0 < g.issued_utc_ms < g.start_utc_ms <= now_ms < g.end_utc_ms
             and g.end_utc_ms - g.start_utc_ms <= 86_400_000, "UTC_WINDOW_INVALID")
    _require(g.session_id not in used_sessions, "DUPLICATE_SESSION")
    _require(g.output not in used_outputs and runtime.get("output_unused") is True, "OUTPUT_ALREADY_USED")
    _require(runtime.get("rights_verified") is True, "SOURCE_RIGHTS_UNKNOWN")
    _require(auditor is not None and auditor.key_id == g.auditor_key_id, "AUDITOR_MISSING")
    audit_key = _verify(auditor, auditor_trust)
    _require(audit_key != owner and auditor.key_id != envelope.key_id, "AUDITOR_NOT_INDEPENDENT")
    _require(auditor.grant.grant_sha256 == fingerprint(g.model_dump(mode="json"))
             and auditor.grant.runtime_sha256 == fingerprint(runtime)
             and g.start_utc_ms <= auditor.grant.checked_utc_ms <= now_ms
             and now_ms - auditor.grant.checked_utc_ms <= 60_000, "AUDITOR_BINDING_OR_FRESHNESS")
    for key in ("proxy_qualified", "target_tls_verified", "clock_qualified", "durable_accounting",
                "budget_journal_healthy", "terminal_stop_verified", "previous_terminal_closed"):
        _require(runtime.get(key) is True, key.upper() + "_REQUIRED")
    _require(type(runtime.get("clock_uncertainty_ms")) in (int, float)
             and 0 <= runtime["clock_uncertainty_ms"] <= 1000, "CLOCK_UNCERTAINTY")
    _require(type(runtime.get("wall_discontinuity_ms")) in (int, float)
             and 0 <= runtime["wall_discontinuity_ms"] < 50, "CLOCK_50MS_DISCONTINUITY")
    _require(type(runtime.get("queue_depth")) is int and 0 <= runtime["queue_depth"] < 128, "QUEUE_128_HARD_STOP")
    _require(type(runtime.get("requests_used")) is int and 0 <= runtime["requests_used"] < g.requests_max,
             "REQUEST_BUDGET_EXHAUSTED")
    _require(type(runtime.get("storage_used")) is int and 0 <= runtime["storage_used"] < g.storage_bytes_max
             and type(runtime.get("free_storage_bytes")) is int
             and runtime["free_storage_bytes"] >= g.storage_bytes_max - runtime["storage_used"], "STORAGE_EXHAUSTED")
    return {"status": "OFFLINE_PREFLIGHT_CONTRACT_VALID_NOT_AUTHORIZATION", "native_market_requests": 0,
            "collector": "ABSENT", "source_qualified": False}
