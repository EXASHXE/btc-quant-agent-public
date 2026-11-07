"""FABRICATED OFFLINE identities only; no independently trusted native authority."""
import base64
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from btc_quant_agent.platform.core import fingerprint
from btc_quant_agent.platform.native_preflight import (
    AuditBody, AuditEnvelope, ENDPOINT, Envelope, Grant, SYMBOLS, TIMEFRAMES, preflight,
)
from btc_quant_agent.platform.owner_verifier import signed_bytes


def identity(key_id):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return key, {key_id: {"public_key_base64": base64.b64encode(public).decode(),
                         "public_key_sha256": hashlib.sha256(public).hexdigest(),
                         "verified_owner_reference": "SYNTHETIC_QA_NOT_AUTHORITY",
                         "independently_verified": True}}


def sign(body, key_id, key, cls):
    return cls(grant=body, key_id=key_id, signature_algorithm="Ed25519",
               signature_base64=base64.b64encode(key.sign(signed_bytes(body))).decode())


@pytest.fixture
def qa():
    owner, owner_trust = identity("SYNTHETIC_OWNER")
    auditor, auditor_trust = identity("SYNTHETIC_AUDITOR")
    grant = Grant(schema_version="D_CANDLE_PREFLIGHT_NON_EXECUTING_V1", venue="BINANCE_USDM_FUTURES",
                  endpoint=ENDPOINT, symbols=list(SYMBOLS), timeframes=list(TIMEFRAMES),
                  source_sha256="a"*64, config_sha256="b"*64, session_id="SYNTHETIC_SESSION_001",
                  output="synthetic_unused", issued_utc_ms=1000, start_utc_ms=2000, end_utc_ms=10000,
                  requests_max=9, storage_bytes_max=10000, retention_seconds_max=3600,
                  rights_reference="SYNTHETIC_QA_ONLY", retrospective_rest=False, auditor_key_id="SYNTHETIC_AUDITOR")
    runtime = {k: True for k in ("rights_verified", "output_unused", "proxy_qualified", "target_tls_verified",
               "clock_qualified", "durable_accounting", "budget_journal_healthy", "terminal_stop_verified",
               "previous_terminal_closed")}
    runtime.update(clock_uncertainty_ms=1, wall_discontinuity_ms=0, queue_depth=0,
                   requests_used=0, storage_used=0, free_storage_bytes=100000)
    def call(grant_changes=None, runtime_changes=None, option_changes=None):
        g = grant.model_copy(update=grant_changes or {})
        r = {**runtime, **(runtime_changes or {})}
        signed = sign(g, "SYNTHETIC_OWNER", owner, Envelope)
        attestation = sign(AuditBody(grant_sha256=fingerprint(g.model_dump(mode="json")),
                                    runtime_sha256=fingerprint(r), checked_utc_ms=3000),
                           "SYNTHETIC_AUDITOR", auditor, AuditEnvelope)
        options = dict(owner_trust=owner_trust, auditor_trust=auditor_trust, auditor=attestation,
                       expected_source="a"*64, expected_config="b"*64, now_ms=3000,
                       runtime=r, used_sessions=set(), used_outputs=set())
        options.update(option_changes or {})
        return preflight(signed, **options)
    return call


def test_synthetic_preflight_is_non_authorizing(qa):
    assert qa()["status"] == "OFFLINE_PREFLIGHT_CONTRACT_VALID_NOT_AUTHORIZATION"


@pytest.mark.parametrize("changes,reason", [
    ({"endpoint": "https://fapi.binance.com/fapi/v1/klines"}, "ENDPOINT_UNAUTHORIZED"),
    ({"symbols": ["XRPUSDT"]}, "SYMBOL_UNAUTHORIZED"),
    ({"timeframes": ["1m"]}, "TIMEFRAME_UNAUTHORIZED"),
    ({"source_sha256": "c"*64}, "SOURCE_FINGERPRINT_CHANGED"),
    ({"config_sha256": "c"*64}, "CONFIG_FINGERPRINT_CHANGED"),
    ({"start_utc_ms": 4000}, "UTC_WINDOW_INVALID"),
    ({"end_utc_ms": 2500}, "UTC_WINDOW_INVALID"),
])
def test_signed_scope_rejections(qa, changes, reason):
    with pytest.raises(ValueError, match=reason):
        qa(grant_changes=changes)


@pytest.mark.parametrize("changes,reason", [
    ({"proxy_qualified": False}, "PROXY_QUALIFIED_REQUIRED"),
    ({"target_tls_verified": False}, "TARGET_TLS_VERIFIED_REQUIRED"),
    ({"clock_qualified": False}, "CLOCK_QUALIFIED_REQUIRED"),
    ({"clock_uncertainty_ms": 1001}, "CLOCK_UNCERTAINTY"),
    ({"clock_uncertainty_ms": float('nan')}, "Out of range float|CLOCK_UNCERTAINTY"),
    ({"wall_discontinuity_ms": 50}, "CLOCK_50MS_DISCONTINUITY"),
    ({"queue_depth": 128}, "QUEUE_128_HARD_STOP"),
    ({"durable_accounting": False}, "DURABLE_ACCOUNTING_REQUIRED"),
    ({"budget_journal_healthy": False}, "BUDGET_JOURNAL_HEALTHY_REQUIRED"),
    ({"requests_used": 9}, "REQUEST_BUDGET_EXHAUSTED"),
    ({"storage_used": 10000}, "STORAGE_EXHAUSTED"),
    ({"free_storage_bytes": 0}, "STORAGE_EXHAUSTED"),
    ({"previous_terminal_closed": False}, "PREVIOUS_TERMINAL_CLOSED_REQUIRED"),
    ({"terminal_stop_verified": False}, "TERMINAL_STOP_VERIFIED_REQUIRED"),
    ({"rights_verified": False}, "SOURCE_RIGHTS_UNKNOWN"),
    ({"output_unused": False}, "OUTPUT_ALREADY_USED"),
])
def test_runtime_stop_rejections(qa, changes, reason):
    with pytest.raises(ValueError, match=reason):
        qa(runtime_changes=changes)


@pytest.mark.parametrize("changes,reason", [
    ({"owner_trust": {}}, "INDEPENDENT_TRUST_MISSING"),
    ({"auditor_trust": {}}, "INDEPENDENT_TRUST_MISSING"),
    ({"auditor": None}, "AUDITOR_MISSING"),
    ({"used_sessions": {"SYNTHETIC_SESSION_001"}}, "DUPLICATE_SESSION"),
    ({"used_outputs": {"synthetic_unused"}}, "OUTPUT_ALREADY_USED"),
])
def test_authority_and_reuse_rejections(qa, changes, reason):
    with pytest.raises(ValueError, match=reason):
        qa(option_changes=changes)


def test_original_verifier_invalid_signature_and_untrusted_fingerprint():
    from types import SimpleNamespace
    from btc_quant_agent.platform.native_preflight import _verify
    body = AuditBody(grant_sha256="a"*64, runtime_sha256="b"*64, checked_utc_ms=3000)
    key, trust = identity("SYNTHETIC")
    envelope = sign(body, "SYNTHETIC", key, AuditEnvelope)
    changed = SimpleNamespace(key_id=envelope.key_id, grant=body,
                              signature_base64=base64.b64encode(b'x'*64).decode())
    with pytest.raises(ValueError, match="SIGNATURE_INVALID"):
        _verify(changed, trust)
    trust["SYNTHETIC"]["public_key_sha256"] = '0'*64
    with pytest.raises(ValueError, match="FINGERPRINT_MISMATCH"):
        _verify(envelope, trust)
