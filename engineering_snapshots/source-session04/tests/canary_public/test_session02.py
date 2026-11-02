"""Session 02 OFFLINE preparation: ephemeral signing keys and fabricated transports.

No private exchange/account material, native grant file or native output is created.
"""

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from btc_quant_agent.platform.canary import session02 as s
from btc_quant_agent.platform.canary.clock_domain import ClockEpoch
from btc_quant_agent.platform.canary.public_policy import START, END, PublicStop, SYMBOLS
from btc_quant_agent.platform.canary.public_runtime import run_public
from btc_quant_agent.platform.core import fingerprint
from .fixtures import meta_payload
from .test_clock_domain import scenario
from btc_quant_agent.platform.canary.public_data import normalize


class Clock:
    def __init__(self, wall=START + 1_000_000):
        self.w, self.m = wall, 1_000_000
        self.lock = threading.RLock()
        self.epoch = ClockEpoch("FABRICATED_SESSION02_EPOCH")
        self.utc_uncertainty_ms = 1
        self.sample()

    def advance(self, ms, step=0):
        with self.lock:
            self.w += ms + step
            self.m += ms

    def wall(self):
        with self.lock:
            return self.w

    def mono(self):
        with self.lock:
            return self.m

    def sample(self):
        with self.lock:
            self.sync_evidence = {"status": "SYNC_OBSERVED", "uncertainty_ms": 1, "sample_mono_ms": self.m}
            return self.epoch.capture(self.w, self.m, self.m, self.sync_evidence)

    def pair(self):
        x = self.sample()
        return x["wall_ms"], x["mono_after_ms"]

    def sleep(self, seconds):
        self.advance(round(seconds * 1000))
        time.sleep(0.001)


def body(clock, duration=30000):
    base = s.load_scope()
    return {
        "version": "L4_SESSION02_GRANT_V1",
        "session_id": s.SESSION_ID,
        "authorization_reference": "OWNER-V070-L4-SESSION02-FABRICATED_UNIT",
        "provider": "binance",
        "market": "USD_M_USDT_LINEAR_PERPETUAL",
        "permitted_use": "OWNER_CONFIRMED_PERSONAL_NONCOMMERCIAL_PUBLIC_READONLY",
        "symbols": list(SYMBOLS),
        "endpoint_ids": list(s.ENDPOINTS),
        "endpoint_fields": {
            id: next(e for e in base.document["endpoints"] if e["id"] == id)["fields"] for id in s.ENDPOINTS
        },
        "output_path": str(s.SESSION_OUTPUT),
        "issued_utc_ms": clock.wall() - 2000,
        "start_utc_ms": clock.wall() - 1000,
        "end_utc_ms": clock.wall() - 1000 + duration,
        "source_sha256_fingerprint": fingerprint(s.source_hashes()),
        "canonical_documentation_head": s.HEAD,
        "documentation_fingerprint": base.grant.documentation_fingerprint,
        "clock_contract": "L4_CLOCK_DOMAIN_V2",
        "wall_jump_ms": 50,
        "max_offset_uncertainty_ms": 100,
        "max_probe_age_ms": 300000,
        "startup_independent_probes": 2,
        "startup_probe_gap_ms": 10,
        "subsequent_probe_interval_ms": 120000,
        "rest_weight_per_minute": 60,
        "retry_reserve_weight_per_minute": 10,
        "time_calls_per_minute": 2,
        "controls_per_second": 2,
        "connections": 1,
        "subscriptions": 3,
        "reconnects_per_hour": 3,
        "raw_retention_hours": 36,
        "normalized_retention_hours": 168,
        "raw_bytes": 8 * 1024**3,
        "auxiliary_bytes": 4 * 1024**3,
        "external_notifications": False,
        "account_or_order_operations": False,
    }


def signed_file(tmp_path, payload):
    key = Ed25519PrivateKey.generate()
    parsed = s.GrantBody.model_validate_json(json.dumps(payload))
    envelope = {
        "grant": payload,
        "key_id": "FABRICATED_MEMORY_KEY",
        "signature_algorithm": "Ed25519",
        "signature_base64": base64.b64encode(key.sign(s.signed_bytes(parsed))).decode(),
    }
    path = tmp_path / "FABRICATED_GRANT_NEVER_NATIVE.json"
    path.write_text(json.dumps(envelope))
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    keys = {
        envelope["key_id"]: {
            "public_key_base64": public,
            "verified_owner_reference": "FABRICATED_TEST_ONLY_NOT_OWNER_AUTH",
        }
    }
    return path, keys, envelope


def prepared(tmp_path, clock=None, duration=30000):
    clock = clock or Clock()
    p, keys, _ = signed_file(tmp_path, body(clock, duration))
    return clock, s.load_session02(p, clock.wall(), fabricated_keys=keys)


def test_shipped_preparation_has_no_grant_or_native_trust(tmp_path):
    assert s.read_owner_keys() == {}
    assert not s.SESSION_OUTPUT.exists()
    with pytest.raises(PublicStop, match="OWNER_GRANT_ABSENT"):
        s.load_session02(tmp_path / "ABSENT", Clock().wall())
    p, _, _ = signed_file(tmp_path, body(Clock()))
    with pytest.raises(PublicStop, match="OWNER_AUTHORIZATION_NOT_PROVISIONED"):
        s.load_session02(p, Clock().wall())
    assert s.requirements()["status"] == "PREPARED_BUT_NOT_AUTHORIZED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", "session01"),
        ("symbols", ["BTCUSDT"]),
        ("endpoint_ids", list(s.ENDPOINTS) + ["binance_usdm_oi"]),
        ("output_path", str(s.SESSION_OUTPUT.parent / "run")),
        ("wall_jump_ms", 900),
        ("max_offset_uncertainty_ms", 101),
        ("max_probe_age_ms", 300001),
        ("rest_weight_per_minute", 61),
        ("connections", 2),
        ("subscriptions", 9),
        ("raw_retention_hours", 24),
        ("normalized_retention_hours", 24),
        ("external_notifications", True),
        ("account_or_order_operations", True),
        ("canonical_documentation_head", "0" * 40),
        ("authorization_reference", "OWNER-V070-L4-WINDOW-20261030"),
    ],
)
def test_exact_scope_schema_cannot_expand(field, value, tmp_path):
    payload = body(Clock())
    payload[field] = value
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps(
            {"grant": payload, "key_id": "x", "signature_algorithm": "Ed25519", "signature_base64": ""}
        )
    )
    with pytest.raises(PublicStop, match="SCHEMA_OR_BINDING_INVALID"):
        s.load_session02(p, Clock().wall())


@pytest.mark.parametrize(
    "fault", ["duration", "outer_end", "fields", "source", "documentation", "signature", "unsigned_flag"]
)
def test_authorization_binding_and_signature_fail_closed(tmp_path, fault):
    c = Clock()
    payload = body(c)
    if fault == "duration":
        payload["end_utc_ms"] = payload["start_utc_ms"] + 180001
    elif fault == "outer_end":
        payload["start_utc_ms"] = END - 1000
        payload["end_utc_ms"] = END + 1
    if fault in ("duration", "outer_end"):
        with pytest.raises(ValueError):
            s.GrantBody.model_validate_json(json.dumps(payload))
        return
    if fault == "fields":
        payload["endpoint_fields"][s.ENDPOINTS[-1]] = []
    elif fault == "source":
        payload["source_sha256_fingerprint"] = "0" * 64
    elif fault == "documentation":
        payload["documentation_fingerprint"] = "0" * 64
    p, keys, envelope = signed_file(tmp_path, payload)
    if fault == "signature":
        envelope["signature_base64"] = base64.b64encode(b"x" * 64).decode()
    elif fault == "unsigned_flag":
        envelope["native_authorized"] = True
    p.write_text(json.dumps(envelope))
    with pytest.raises(PublicStop):
        s.load_session02(p, c.wall(), fabricated_keys=keys)


@pytest.mark.parametrize("when", ["before", "equality", "expired"])
def test_exact_grant_window_without_wait(tmp_path, when):
    c = Clock()
    p, keys, envelope = signed_file(tmp_path, body(c))
    b = envelope["grant"]
    now = b["start_utc_ms"] - 1 if when == "before" else b["end_utc_ms"] + (1 if when == "expired" else 0)
    with pytest.raises(PublicStop, match="WINDOW_NOT_OPEN|GRANT_EXPIRED"):
        s.load_session02(p, now, fabricated_keys=keys)


def test_fabricated_authority_cannot_activate_native_transport(tmp_path):
    c, scope = prepared(tmp_path)
    with pytest.raises(PublicStop, match="FABRICATED_AUTHORITY_CANNOT_ACTIVATE_NATIVE"):
        scope.require_authority(c.wall(), native=True)
    for id in ("binance_usdm_oi", "binance_usdm_klines_rest", "private"):
        with pytest.raises(PublicStop):
            scope.validate_request(id, {}, c.wall())
    with pytest.raises(PublicStop):
        scope.streams("market")
    with pytest.raises(PublicStop):
        scope.validate_request(s.ENDPOINTS[0], {"symbol": "ADAUSDT"}, c.wall())


def test_verified_grant_or_code_cannot_change_before_start(tmp_path, monkeypatch):
    c, scope = prepared(tmp_path)
    original = s.source_hashes()
    monkeypatch.setattr(s, "source_hashes", lambda: {**original, "unexpected.py": "0" * 64})
    with pytest.raises(PublicStop, match="CURRENT_SOURCE_HASH_MISMATCH"):
        scope.preflight(c, native=False)
    scope.authorization.grant.endpoint_fields[s.ENDPOINTS[-1]] = ()
    with pytest.raises(PublicStop, match="AUTHORIZATION_MUTATED"):
        scope.require_authority(c.wall(), native=False)


def test_exact_session_deadline_not_outer_deadline_and_no_wall_extension(tmp_path):
    c, scope = prepared(tmp_path)
    w = scope.make_window(c)
    deadline = w.mono_end
    c.advance(scope.end_ms - c.wall(), step=-49)
    assert c.wall() < scope.end_ms < END
    with pytest.raises(PublicStop, match="GRANT_WINDOW_EXPIRED"):
        w.check()
    assert w.mono_end <= deadline


def test_mixed_epoch_stops_window_and_never_auto_recovers(tmp_path):
    c, scope = prepared(tmp_path)
    window = scope.make_window(c)
    original = c.epoch
    c.advance(10)
    c.epoch = ClockEpoch("FOREIGN_FABRICATED_EPOCH")
    with pytest.raises(PublicStop, match="CLOCK_EPOCH_MIXING"):
        window.check()
    c.epoch = original
    with pytest.raises(PublicStop, match="CLOCK_EPOCH_MIXING"):
        window.check()


def test_record_admission_obeys_narrow_session_window():
    _, record = scenario(846)
    receive = record["wire"]["receive_wall"]
    record["scope_window_ms"] = [receive + 1, receive + 1000]
    result = normalize(record)
    assert result["status"] == "INADMISSIBLE" and not result["quote"]
    assert "SOURCE_RECEIVE_OUTSIDE_GRANTED_WINDOW" in result["reasons"]
    record["scope_window_ms"] = [receive - 100, receive + 1]
    result = normalize(record)
    assert not result["quote"] and "QUOTE_GRANT_WINDOW_EXPIRED" in result["reasons"]


class Connection:
    def __init__(self, backend):
        self.backend = backend
        self.closed = False
        self.sequence = 0

    def recv(self, timeout):
        if self.closed:
            raise OSError("closed")
        b = self.backend
        c = b.clock
        time.sleep(0.004)
        c.advance(60)
        self.sequence += 1
        if b.step and self.sequence == 12:
            c.advance(0, 900)
        symbol = SYMBOLS[(self.sequence - 1) % 3]
        event = c.wall() + b.offset - 50
        return json.dumps(
            {
                "stream": symbol.lower() + "@bookTicker",
                "data": {
                    "e": "bookTicker",
                    "s": symbol,
                    "st": 1,
                    "u": self.sequence,
                    "E": event,
                    "T": event - 2,
                    "b": "100.00",
                    "a": "100.02",
                    "B": "5",
                    "A": "6",
                },
            }
        )

    def close(self):
        self.closed = True

    def abort(self):
        self.closed = True


class Backend:
    exposure = "SYNTHETIC"

    def __init__(self, clock, offset=0, denial=0, step=False):
        self.clock, self.offset, self.denial, self.step = clock, offset, denial, step
        self.calls = []
        self.urls = []
        self.connections = []

    def get(self, url, params, timeout, clock):
        self.calls.append(url)
        clock.advance(10)
        first = clock.pair()
        payload = (
            meta_payload() if url.endswith("exchangeInfo") else {"serverTime": clock.wall() + self.offset}
        )
        clock.advance(10)
        return self.denial or 200, json.dumps(payload), first

    def connect(self, url, timeout, on_control):
        self.urls.append(url)
        conn = Connection(self)
        self.connections.append(conn)
        return conn

    def close(self):
        for c in self.connections:
            c.close()


@pytest.mark.parametrize("offset", [0, 846, -846])
def test_finite_clock_only_replay_isolated_and_no_action(tmp_path, offset):
    c, scope = prepared(tmp_path)
    backend = Backend(c, offset=offset)
    original_run = Path(
        os.environ.get("L4_SEALED_NATIVE_RUN", str(s.ROOT / "artifacts/live_public_canary_20261030/run"))
    )
    first = original_run / "started.json"
    old = first.read_bytes()
    result = run_public(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "session02")
    assert result["session_id"] == s.SESSION_ID
    assert result["clock_validation_evidence"]["independent_probes"] >= 2, result
    assert set(
        result["model"]["quote_counts"]
        if "quote_counts" in result["model"]
        else result["clock_validation_evidence"]["distinct_qualified_quotes"]
    ) == set(SYMBOLS)
    assert result["model"]["counts"]["admitted"] > 0, result["model"]["reasons"]
    assert result["replay"]["status"] == "PARITY_VERIFIED"
    assert result["transport_metrics"]["rest_weight"] == 3
    assert scope.budget_policy().ip_weight_per_minute == 60
    assert scope.budget_policy().max_connections == 1 and scope.budget_policy().max_subscriptions == 3
    assert result["actionable_quotes"] == 0 and result["native_market_requests"] == 0
    assert not result["source_qualified"] and not result["shadow_advisory_qualified"]
    assert result["sockets_closed"] and result["receiver_threads_stopped"]
    assert result["operator_monotonic_elapsed_ms"] <= 31000
    assert len(backend.calls) == 3 and len(backend.urls) == 1
    assert "/public/" in backend.urls[0] and not any("market/" in u for u in backend.urls)
    assert first.read_bytes() == old and not s.SESSION_OUTPUT.exists()
    marker = (tmp_path / "session02/started.json").read_bytes()
    fresh = Clock()
    with pytest.raises(PublicStop, match="ALREADY_CLAIMED"):
        run_public(scope, enabled=True, clock=fresh, backend=Backend(fresh), output=tmp_path / "session02")
    assert (tmp_path / "session02/started.json").read_bytes() == marker


@pytest.mark.parametrize("status", [403, 451, 429, 418])
def test_provider_denial_or_rate_stop_no_retry_storm(tmp_path, status):
    c, scope = prepared(tmp_path)
    backend = Backend(c, denial=status)
    result = run_public(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "fault")
    assert len(backend.calls) == 1 and not backend.urls
    assert result["status"] == "BLOCKED" and result["sockets_closed"]
    assert result["native_market_requests"] == 0


def test_900ms_step_latches_epoch_and_closes_finite_session(tmp_path):
    c, scope = prepared(tmp_path)
    backend = Backend(c, offset=846, step=True)
    result = run_public(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "step")
    assert "LOCAL_WALL_CLOCK_JUMP" in result["stop_reason"], result
    assert result["model"]["clock_epoch_failure"] == "LOCAL_WALL_CLOCK_JUMP"
    assert result["sockets_closed"] and result["receiver_threads_stopped"]
    assert not result["source_qualified"] and result["actionable_quotes"] == 0
    assert result["replay"]["status"] == "PARITY_VERIFIED"


def test_cli_preparation_is_default_denied_and_no_output_created():
    p = subprocess.run(
        [sys.executable, "tools/launch_clock_session02.py", "run"], capture_output=True, text=True, timeout=10
    )
    assert p.returncode == 2
    value = json.loads(p.stdout)
    assert value["status"] == "PREPARED_BUT_NOT_AUTHORIZED"
    assert value["native_market_requests_this_failed_launch"] == 0
    assert not s.SESSION_OUTPUT.exists()
