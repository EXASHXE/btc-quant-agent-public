import base64
import json
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from btc_quant_agent.platform.canary import longhorizon as lh
from btc_quant_agent.platform.canary.public_policy import PublicStop, END
from btc_quant_agent.platform.canary.public_runtime import run_public
from canary_public.test_session02 import Clock
from .fixtures import START, body, scope


@pytest.mark.parametrize("field,value", [
    ("symbols", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]), ("endpoint_ids", ["private"]),
    ("wall_jump_ms", 51), ("rest_weight_per_minute", 61), ("raw_retention_hours", 24),
    ("normalized_retention_hours", 36), ("automatic_restart", True), ("subscriptions", 10),
    ("connections", 3), ("account_or_order_operations", True), ("external_notifications", True),
    ("end_utc_ms", START + lh.MAX_DURATION + 1), ("issued_utc_ms", START + 1),
    ("egress_route", {"egress_mode": "IMPLICIT_PROXY"}), ("output_relative_path", "../session02")])
def test_exact_new_contract_rejects_expansion(field, value):
    b = body()
    b[field] = value
    with pytest.raises(ValueError):
        lh.GrantBody.model_validate_json(json.dumps(b))


def test_new_48h_bounds_are_independent_of_expired_session02():
    s = scope()
    assert s.start_ms > END and s.end_ms - s.start_ms == lh.MAX_DURATION
    s.make_window(Clock(START + 10)).check()
    with pytest.raises(PublicStop, match="FABRICATED_AUTHORITY"):
        s.require_authority(START + 10, native=True)


@pytest.mark.parametrize("shift", [-900, -51, 51, 900])
def test_wall_epoch_fault_is_sticky(shift):
    c = Clock(START + 10)
    w = scope().make_window(c)
    c.advance(100, step=shift)
    with pytest.raises(PublicStop, match="WALL_CLOCK_JUMP"):
        w.check()
    c.advance(100, step=-shift)
    with pytest.raises(PublicStop, match="WALL_CLOCK_JUMP"):
        w.check()


def test_exact_end_and_early_start_exit_without_wait():
    with pytest.raises(PublicStop, match="WINDOW_NOT_OPEN"):
        scope().make_window(Clock(START - 10)).check()
    c = Clock(START + 10)
    s = scope()
    w = s.make_window(c)
    c.advance(s.end_ms - c.wall(), step=-49)
    with pytest.raises(PublicStop, match="WINDOW_EXPIRED"):
        w.check()


@pytest.mark.parametrize("endpoint,params", [
    ("binance_usdm_bbo_rest", {"symbol": "BTCUSDT"}), ("binance_usdm_oi", {"symbol": "ADAUSDT"}),
    ("binance_usdm_server_time", {"apiKey": "forbidden"}),
    ("binance_usdm_klines_rest", {"symbol": "BTCUSDT", "interval": "1m", "startTime": START - 60000,
                                 "endTime": START - 1, "limit": 1}),
    ("binance_usdm_klines_rest", {"symbol": "BTCUSDT", "interval": "1m", "startTime": START,
                                 "endTime": START + 6000000 - 1, "limit": 99})])
def test_requests_cannot_read_history_or_expand_source(endpoint, params):
    with pytest.raises(PublicStop):
        scope().validate_request(endpoint, params, START + 10_000_000)


def test_signature_source_binding_and_missing_clock_qualification(tmp_path, monkeypatch):
    b = lh.GrantBody.model_validate_json(json.dumps(body()))
    key = Ed25519PrivateKey.generate()
    trust = tmp_path / "test_keys.json"
    trust.write_text(json.dumps({"version": "L4_LONGHORIZON_OWNER_KEYS_V1", "keys": {"EPHEMERAL": {
        "public_key_base64": base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode(),
        "verified_owner_reference": b.authorization_reference}}}))
    monkeypatch.setattr(lh, "TRUST", trust)
    envelope = lh.GrantEnvelope(grant=b, key_id="EPHEMERAL", signature_algorithm="Ed25519",
        signature_base64=base64.b64encode(key.sign(lh.signed_bytes(b))).decode())
    lh.verify_signature(envelope)
    s = lh.make_scope(envelope)
    check = s.preflight(Clock(START + 10), native=True)
    assert "CQUAL_BUNDLE_MISSING" in check["reasons"]
    with pytest.raises(PublicStop, match="SIGNATURE_INVALID"):
        lh.verify_signature(envelope.model_copy(update={"signature_base64": base64.b64encode(b"x" * 64).decode()}))
    original = lh.source_hashes()
    monkeypatch.setattr(lh, "source_hashes", lambda: {**original, "mutation": "0" * 64})
    with pytest.raises(PublicStop, match="SOURCE_HASH_MISMATCH"):
        s.preflight(Clock(START + 10), native=False)


def test_mutated_nested_grant_is_rejected():
    s = scope()
    s.authorization.grant.endpoint_fields[lh.IDS[0]] = ()
    with pytest.raises(PublicStop, match="AUTHORIZATION_MUTATED"):
        s.require_authority(START + 10, native=False)


def test_shipped_launcher_denies_native_before_output_or_network():
    r = subprocess.run([sys.executable, "tools/launch_longhorizon.py", "run", "--enable-public-network"],
                       capture_output=True, text=True)
    assert r.returncode == 2
    value = json.loads(r.stdout)
    assert value["status"] == "NO_GO_NATIVE_SOURCE" and value["native_market_requests_this_failed_launch"] == 0
    assert not lh.OUTPUT.exists()
    assert not json.loads(lh.TRUST.read_text())["keys"]


def test_native_backend_cannot_use_fabricated_grant(tmp_path):
    class NeverCalled:
        exposure = "PUBLIC_CANARY"
    with pytest.raises(PublicStop, match="FABRICATED_AUTHORITY"):
        run_public(scope(), enabled=True, clock=Clock(START + 10), backend=NeverCalled(), output=tmp_path / "unused")
    assert not (tmp_path / "unused").exists()
