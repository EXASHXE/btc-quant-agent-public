"""Offline Session03 contract. All grants/signers/transports are FABRICATED."""

import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from btc_quant_agent.platform.canary import session03 as s
from btc_quant_agent.platform.canary import session02
from btc_quant_agent.platform.canary.public_policy import END, PublicStop
from btc_quant_agent.platform.canary.public_io import HttpWsBackend
from btc_quant_agent.platform.canary.public_io import PublicTransport
from btc_quant_agent.platform.canary.control import CanaryStore, BudgetGuard
from btc_quant_agent.platform.canary.clock_domain import ClockEpoch
from btc_quant_agent.platform.core import fingerprint
from .test_session02 import Clock as PreviousClock, Backend, body as previous_body

FIXTURE_START = END + 3600_000  # Fabricated timestamp beyond old scope, not a live proposal.


class Clock(PreviousClock):
    def __init__(self, wall=FIXTURE_START):
        super().__init__(wall)
        self.utc_uncertainty_ms = 0


def body(clock, duration=s.MAX_LAUNCH_MS):
    old = previous_body(clock)
    for name in ("start_utc_ms", "end_utc_ms"):
        old.pop(name)
    old.update(
        version=s.VERSION,
        session_id=s.SESSION_ID,
        authorization_reference="OWNER-V070-L4-FLEX-SESSION03-FABRICATED_TEST",
        authorized_operator_key_id="FABRICATED_SESSION03_KEY",
        allowed_hostnames=list(s.HOSTS),
        output_path=str(s.SESSION_OUTPUT),
        issued_utc_ms=clock.wall() - 1000,
        launch_window_start_utc_ms=clock.wall(),
        launch_window_end_utc_ms=clock.wall() + duration,
        max_acquisition_ms=180000,
        minimum_startup_ms=25000,
        canonical_documentation_head=s.HEAD,
        source_sha256_fingerprint=fingerprint(s.source_hashes()),
    )
    return old


def signed_file(tmp_path, payload):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    model = s.GrantBody.model_validate_json(json.dumps(payload))
    envelope = {
        "grant": payload,
        "key_id": payload["authorized_operator_key_id"],
        "signature_algorithm": "Ed25519",
        "signature_base64": base64.b64encode(private.sign(session02.signed_bytes(model))).decode(),
    }
    keys = {
        envelope["key_id"]: {
            "public_key_base64": base64.b64encode(public).decode(),
            "public_key_sha256": hashlib.sha256(public).hexdigest(),
            "verified_owner_reference": payload["authorization_reference"],
            "session_id": s.SESSION_ID,
            "launch_window_start_utc_ms": payload["launch_window_start_utc_ms"],
            "launch_window_end_utc_ms": payload["launch_window_end_utc_ms"],
        }
    }
    path = tmp_path / "FABRICATED_NOT_NATIVE.json"
    path.write_text(json.dumps(envelope))
    return path, keys, envelope


def prepared(tmp_path, duration=s.MAX_LAUNCH_MS):
    clock = Clock(FIXTURE_START)
    path, keys, _ = signed_file(tmp_path, body(clock, duration))
    return clock, s.load_session03(path, clock.wall(), fabricated_keys=keys)


@pytest.mark.parametrize(
    "when,reason", [("before", "WINDOW_NOT_OPEN"), ("end", "WINDOW_EXPIRED"), ("after", "WINDOW_EXPIRED")]
)
def test_refuse_outside_window_without_sleep_or_output(tmp_path, when, reason):
    c = Clock(FIXTURE_START)
    p, keys, e = signed_file(tmp_path, body(c))
    start, end = e["grant"]["launch_window_start_utc_ms"], e["grant"]["launch_window_end_utc_ms"]
    now = {"before": start - 1, "end": end, "after": end + 1}[when]
    with pytest.raises(PublicStop, match=reason):
        s.load_session03(p, now, fabricated_keys=keys)
    assert not s.SESSION_OUTPUT.exists()


@pytest.mark.parametrize("elapsed", [0, 3 * 3600_000, s.MAX_LAUNCH_MS - 30000])
def test_start_middle_and_truncated_deadline(tmp_path, elapsed):
    c, scope = prepared(tmp_path)
    c.advance(elapsed)
    assert scope.preflight(c, native=False)["reasons"] == []
    scope.reserve_launch(c, tmp_path / "reserved", native=False)
    assert scope.end_ms == min(c.wall() + 180000, scope.outer_end_ms)
    assert 0 < scope.activation["window"].mono_end - c.mono() <= 180000
    assert json.loads((tmp_path / "reserved/launch_reservation.json").read_text())["request_count"] is None
    w = scope.make_window(c)
    c.advance(min(180000, scope.outer_end_ms - c.wall()))
    with pytest.raises(PublicStop, match="EXPIRED"):
        w.check()


def test_insufficient_remaining_window_does_not_consume(tmp_path):
    c, scope = prepared(tmp_path)
    c.advance(s.MAX_LAUNCH_MS - s.MIN_STARTUP_MS + 1)
    with pytest.raises(PublicStop, match="INSUFFICIENT_REMAINING_WINDOW"):
        s.run_session03(scope, enabled=True, clock=c, backend=Backend(c), output=tmp_path / "unused")
    assert not (tmp_path / "unused").exists()


def test_valid_short_authorization_reports_insufficient_startup_time(tmp_path):
    c, scope = prepared(tmp_path, duration=10000)
    backend = Backend(c)
    with pytest.raises(PublicStop, match="INSUFFICIENT_REMAINING_WINDOW"):
        s.run_session03(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "short")
    assert not backend.calls and not (tmp_path / "short").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("session_id", session02.SESSION_ID),
        ("max_acquisition_ms", 180001),
        ("launch_window_end_utc_ms", FIXTURE_START + s.MAX_LAUNCH_MS + 1),
        ("issued_utc_ms", FIXTURE_START + 1),
        ("launch_window_start_utc_ms", FIXTURE_START + s.MAX_LAUNCH_MS),
        ("symbols", ["BTCUSDT"]),
        ("allowed_hostnames", ["developers.binance.com"]),
        ("endpoint_ids", list(s.ENDPOINTS) + ["binance_usdm_oi"]),
        ("output_path", str(session02.SESSION_OUTPUT)),
        ("wall_jump_ms", 900),
        ("max_offset_uncertainty_ms", 101),
        ("max_probe_age_ms", 300001),
        ("rest_weight_per_minute", 61),
        ("time_calls_per_minute", 3),
        ("subscriptions", 4),
        ("raw_retention_hours", 24),
        ("auxiliary_bytes", 8589934592),
        ("external_notifications", True),
        ("account_or_order_operations", True),
        ("canonical_documentation_head", "0" * 40),
    ],
)
def test_exact_versioned_scope_and_no_expansion(tmp_path, field, value):
    b = body(Clock(FIXTURE_START))
    b[field] = value
    with pytest.raises(ValueError):
        s.GrantBody.model_validate_json(json.dumps(b))


@pytest.mark.parametrize(
    "fault",
    [
        "absent",
        "signature",
        "key_id",
        "key_period",
        "key_session",
        "key_reference",
        "key_hash",
        "source",
        "fields",
        "doc",
        "flag",
    ],
)
def test_authorization_source_and_key_binding_fail_closed(tmp_path, fault):
    c = Clock(FIXTURE_START)
    b = body(c)
    if fault == "source":
        b["source_sha256_fingerprint"] = "0" * 64
    if fault == "fields":
        b["endpoint_fields"][s.ENDPOINTS[-1]] = []
    if fault == "doc":
        b["documentation_fingerprint"] = "0" * 64
    p, keys, e = signed_file(tmp_path, b)
    entry = keys[e["key_id"]]
    if fault == "absent":
        keys = {}
    if fault == "signature":
        e["signature_base64"] = base64.b64encode(b"x" * 64).decode()
    if fault == "key_id":
        e["key_id"] = "OTHER"
    if fault == "key_period":
        entry["launch_window_end_utc_ms"] += 1
    if fault == "key_session":
        entry["session_id"] = session02.SESSION_ID
    if fault == "key_reference":
        entry["verified_owner_reference"] = "OWNER-OLD"
    if fault == "key_hash":
        entry["public_key_sha256"] = "0" * 64
    if fault == "flag":
        e["native_authorized"] = True
    p.write_text(json.dumps(e))
    with pytest.raises(PublicStop):
        s.load_session03(p, c.wall(), fabricated_keys=keys)


def test_session02_keys_and_grant_never_authorize_flex(tmp_path, monkeypatch):
    assert s.read_owner_keys() == {}
    monkeypatch.setattr(session02, "read_owner_keys", lambda: {"PREVIOUS_APPROVED_KEY": {}})
    assert session02.read_owner_keys() != {}  # Previous trust does not populate Session03 trust.
    c = Clock()
    old = previous_body(c)
    p = tmp_path / "old.json"
    p.write_text(
        json.dumps({"grant": old, "key_id": "old", "signature_algorithm": "Ed25519", "signature_base64": ""})
    )
    with pytest.raises(PublicStop, match="SCHEMA_OR_BINDING_INVALID"):
        s.load_session03(p, c.wall())


def test_fabricated_proof_never_native_or_arbitrary_hosts(tmp_path):
    c, scope = prepared(tmp_path)
    with pytest.raises(PublicStop, match="FABRICATED_AUTHORITY"):
        scope.preflight(c, native=True)
    backend = HttpWsBackend()
    backend.scope = scope
    with pytest.raises(PublicStop, match="HOST_FORBIDDEN"):
        backend.get("https://developers.binance.com/", {}, 1, c)
    for ep in ("private", "binance_usdm_oi", "binance_usdm_klines_rest"):
        with pytest.raises(PublicStop):
            scope.validate_request(ep, {}, c.wall())


@pytest.mark.parametrize("step", [900, -900])
def test_wall_step_and_epoch_invalidation_are_sticky(tmp_path, step):
    c, scope = prepared(tmp_path)
    scope.reserve_launch(c, tmp_path / "step", native=False)
    window = scope.make_window(c)
    before = window.mono_end
    c.advance(50, step)
    with pytest.raises(PublicStop, match="WALL_CLOCK_JUMP"):
        window.check()
    assert window.mono_end <= before
    c.advance(0, -step)
    with pytest.raises(PublicStop):
        window.check()


def test_epoch_mixing_or_restart_cannot_extend_consumed_run(tmp_path):
    c, scope = prepared(tmp_path)
    scope.reserve_launch(c, tmp_path / "epoch", native=False)
    window = scope.make_window(c)
    c.epoch = ClockEpoch("OTHER_FABRICATED_EPOCH")
    with pytest.raises(PublicStop, match="EPOCH_MIXING"):
        window.check()
    with pytest.raises(PublicStop, match="CLOCK_INSTANCE_CHANGED"):
        scope.make_window(Clock(c.wall()))


@pytest.mark.parametrize("direction", [1, -1])
def test_clock_step_during_collection_closes_and_persists_fault(tmp_path, direction):
    class SteppedClock(Clock):
        def advance(self, ms, step=0):
            super().advance(ms, direction * step)

    c = SteppedClock()
    p, keys, _ = signed_file(tmp_path, body(c))
    scope = s.load_session03(p, c.wall(), fabricated_keys=keys)
    backend = Backend(c, step=True)
    result = s.run_session03(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "stepped")
    assert "WALL_CLOCK_JUMP" in result["stop_reason"], result["stop_reason"]
    assert result["model"]["clock_epoch_failure"] == "LOCAL_WALL_CLOCK_JUMP"
    assert result["sockets_closed"] and result["receiver_threads_stopped"]
    assert result["actionable_quotes"] == 0 and not result["source_qualified"]
    assert result["replay"]["status"] == "PARITY_VERIFIED"


@pytest.mark.parametrize("offset", [0, 846, -846])
def test_finite_runtime_180s_bbo_probes_replay_and_no_action(tmp_path, offset):
    c, scope = prepared(tmp_path, duration=s.MAX_LAUNCH_MS if offset == 0 else 30000)
    backend = Backend(c, offset=offset)
    result = s.run_session03(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "finite")
    assert result["clock_validation_evidence"]["independent_probes"] >= 2, result
    assert result["model"]["counts"]["admitted"] > 0, result["model"]["reasons"]
    assert result["replay"]["status"] == "PARITY_VERIFIED"
    assert result["sockets_closed"] and result["receiver_threads_stopped"]
    assert result["actionable_quotes"] == 0 and not result["source_qualified"]
    assert not result["shadow_advisory_qualified"] and not result["economically_validated"]
    assert result["external_notifications"] == result["account_or_order_operations"] == 0
    assert result["authorized_end_exclusive_ms"] - result["started_wall_ms"] == (
        180000 if offset == 0 else 30000
    )
    assert result["operator_monotonic_elapsed_ms"] <= 180200
    assert len(backend.urls) == 1 and backend.urls[0].count("bookTicker") == 3
    assert 3 <= result["transport_metrics"]["rest_weight"] <= 4
    assert s.reconcile(tmp_path / "finite")["status"] == "CONSUMED_SEALED"
    with pytest.raises(PublicStop, match="ALREADY_CONSUMED"):
        s.run_session03(scope, enabled=True, clock=c, backend=Backend(c), output=tmp_path / "finite")


@pytest.mark.parametrize("status", [451, 418, 429])
def test_provider_denial_rate_stop_single_consumed_attempt(tmp_path, status):
    c, scope = prepared(tmp_path)
    backend = Backend(c, denial=status)
    result = s.run_session03(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "denied")
    assert result["status"] == "BLOCKED" and len(backend.calls) == 1
    assert not backend.urls and result["sockets_closed"]
    assert s.reconcile(tmp_path / "denied")["retry_authorized"] is False


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_existing_output_and_symlinks_fail_without_request(tmp_path, kind):
    c, scope = prepared(tmp_path)
    target = tmp_path / "occupied"
    target.mkdir()
    output = target
    if kind == "symlink":
        output = tmp_path / "alias"
        output.symlink_to(target, target_is_directory=True)
    backend = Backend(c)
    with pytest.raises(PublicStop, match="ALREADY_CONSUMED|SYMLINK"):
        s.run_session03(scope, enabled=True, clock=c, backend=backend, output=output)
    assert not backend.calls


def test_crash_after_durable_reservation_sqlite_restart_is_unknown(tmp_path):
    c = Clock(FIXTURE_START)
    p, keys, _ = signed_file(tmp_path, body(c))
    keyfile = tmp_path / "FABRICATED_PUBLIC_KEYS.json"
    keyfile.write_text(json.dumps(keys))
    root = tmp_path / "crashed"
    worker = """
import json,os,sqlite3,sys
from pathlib import Path
from canary_public.test_session03 import Clock
from btc_quant_agent.platform.canary import session03 as s
c=Clock(int(sys.argv[4]));root=Path(sys.argv[3])
scope=s.load_session03(sys.argv[1],c.wall(),fabricated_keys=json.loads(Path(sys.argv[2]).read_text()))
scope.reserve_launch(c,root,native=False)
with sqlite3.connect(root/'state.sqlite') as db:
 db.execute('CREATE TABLE uncertainty(status TEXT)');db.execute("INSERT INTO uncertainty VALUES ('UNKNOWN')")
os._exit(23)
"""
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(s.ROOT / "src") + os.pathsep + str(s.ROOT / "tests"),
    }
    args = [sys.executable, "-c", worker, str(p), str(keyfile), str(root), str(c.wall())]
    first = subprocess.run(args, env=env, capture_output=True, text=True)
    assert first.returncode == 23, first.stderr
    assert s.reconcile(root) == {
        "status": "CONSUMED_EXECUTION_UNKNOWN",
        "request_count": None,
        "retry_authorized": False,
    }
    before = (root / "launch_reservation.json").read_bytes()
    second = subprocess.run(args, env=env, capture_output=True, text=True)
    assert second.returncode != 23 and "ALREADY_CONSUMED" in second.stderr
    assert (root / "launch_reservation.json").read_bytes() == before
    with sqlite3.connect(root / "state.sqlite") as db:
        assert db.execute("SELECT status FROM uncertainty").fetchone() == ("UNKNOWN",)


def test_cli_default_deny_no_grant_no_network_or_successor():
    result = subprocess.run(
        [sys.executable, str(s.ROOT / "tools/launch_clock_session03.py"), "run"],
        env={**os.environ, "PYTHONPATH": str(s.ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    value = json.loads(result.stdout)
    assert value["native_market_requests_this_failed_launch"] == 0 and not s.SESSION_OUTPUT.exists()
    assert s.requirements()["status"] == "PREPARED_BUT_NOT_AUTHORIZED"


def test_no_transport_operation_before_durable_reservation(tmp_path):
    c, scope = prepared(tmp_path)
    backend = Backend(c)
    guard = BudgetGuard(CanaryStore(tmp_path / "counter.sqlite"), scope.budget_policy())
    transport = PublicTransport(scope, c, guard, enabled=True, backend=backend)
    with pytest.raises(PublicStop, match="DURABLE_LAUNCH_RESERVATION_REQUIRED"):
        transport.request(s.ENDPOINTS[0], {})
    transport.close()
    assert not backend.calls


def test_backend_bbo_scope_does_not_evaluate_forbidden_market_group(tmp_path):
    c, scope = prepared(tmp_path)
    backend = HttpWsBackend()
    backend.scope = scope

    def stopped():
        raise PublicStop("SCOPE_PASSED_NO_NETWORK")

    backend.guard = stopped
    with pytest.raises(PublicStop, match="SCOPE_PASSED_NO_NETWORK"):
        backend.connect(scope.ws_url("public"), 1, lambda x: None)


@pytest.mark.parametrize("mode", ["missing", "duplicate", "uncertainty"])
def test_invalid_native_probe_pair_blocks_bbo_subscription(tmp_path, mode):
    class Fault(Backend):
        def get(self, url, params, timeout, clock):
            if not url.endswith("/time"):
                return super().get(url, params, timeout, clock)
            self.calls.append(url)
            clock.advance(300 if mode == "uncertainty" else 10)
            value = (
                {}
                if mode == "missing"
                else {"serverTime": FIXTURE_START if mode == "duplicate" else clock.wall()}
            )
            first = clock.pair()
            clock.advance(300 if mode == "uncertainty" else 10)
            return 200, json.dumps(value), first

    c, scope = prepared(tmp_path)
    backend = Fault(c)
    result = s.run_session03(scope, enabled=True, clock=c, backend=backend, output=tmp_path / mode)
    assert not backend.urls and not result["source_qualified"] and not result["shadow_advisory_qualified"]
    assert result["clock_validation_evidence"]["distinct_qualified_quotes"] == {}
    assert result["sockets_closed"] and result["receiver_threads_stopped"]


def test_tls_chain_failure_is_hard_stop_without_retry(tmp_path):
    import ssl

    class Fault(Backend):
        def get(self, url, params, timeout, clock):
            self.calls.append(url)
            try:
                raise ssl.SSLCertVerificationError("FABRICATED_UNTRUSTED_CERTIFICATE")
            except ssl.SSLError as exc:
                raise OSError("FABRICATED_WRAPPED_TLS_FAILURE") from exc

    c, scope = prepared(tmp_path)
    backend = Fault(c)
    result = s.run_session03(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "tls")
    assert "TLS_VERIFICATION_FAILED" in result["stop_reason"]
    assert len(backend.calls) == 1 and not backend.urls and result["sockets_closed"]


def test_budget_hard_stop_before_backend_and_consumed_marker(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise ValueError("FABRICATED_REQUEST_WEIGHT_BUDGET_EXCEEDED")

    monkeypatch.setattr(BudgetGuard, "request", denied)
    c, scope = prepared(tmp_path)
    backend = Backend(c)
    result = s.run_session03(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "quota")
    assert "BUDGET_EXCEEDED" in result["stop_reason"] and not backend.calls
    assert s.reconcile(tmp_path / "quota")["retry_authorized"] is False


def test_low_disk_refuses_before_reservation(tmp_path, monkeypatch):
    import shutil
    from collections import namedtuple

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: usage(100, 99, 1))
    c, scope = prepared(tmp_path)
    backend = Backend(c)
    with pytest.raises(PublicStop, match="STORAGE_SCOPE_BLOCKED"):
        s.run_session03(scope, enabled=True, clock=c, backend=backend, output=tmp_path / "low_disk")
    assert not (tmp_path / "low_disk").exists() and not backend.calls


def test_startup_failure_after_reservation_seals_unknown_and_never_retries(tmp_path, monkeypatch):
    import btc_quant_agent.platform.canary.public_runtime as runtime

    def failed(*a, **k):
        raise RuntimeError("FABRICATED_TRANSPORT_CONSTRUCTION_FAILURE")

    monkeypatch.setattr(runtime, "PublicTransport", failed)
    c, scope = prepared(tmp_path)
    backend = Backend(c)
    root = tmp_path / "unknown"
    result = s.run_session03(scope, enabled=True, clock=c, backend=backend, output=root)
    assert result["native_market_requests"] is None and result["request_count_status"] == "UNKNOWN"
    assert s.reconcile(root)["request_count"] is None
    seal = (root / "receipt_seal.json").read_bytes()
    with pytest.raises(PublicStop, match="ALREADY_CONSUMED"):
        s.run_session03(scope, enabled=True, clock=c, backend=backend, output=root)
    assert (root / "receipt_seal.json").read_bytes() == seal and not backend.calls


@pytest.mark.parametrize("fault", ["nondict", "scope", "duration", "source_window", "version"])
def test_replay_window_contract_tampering_rejected(tmp_path, fault):
    c, scope = prepared(tmp_path)
    scope.reserve_launch(c, tmp_path / fault, native=False)
    contract = scope.record_window()
    record = {
        "flex_window_contract": contract,
        "scope_hash": scope.hash,
        "scope_window_ms": [scope.start_ms, scope.end_ms],
        "clock_contract_version": "L4_CLOCK_DOMAIN_V2",
    }
    if fault == "nondict":
        record["flex_window_contract"] = []
    if fault == "scope":
        contract["scope_hash"] = "0" * 64
    if fault == "duration":
        contract["acquisition_end_ms"] = scope.start_ms + 180001
    if fault == "source_window":
        record["scope_window_ms"][1] += 1
    if fault == "version":
        record["clock_contract_version"] = "OLD"
    with pytest.raises(ValueError, match="FLEX_WINDOW"):
        s.validate_record_window(record)


def test_atomic_reservation_with_two_fabricated_processes(tmp_path):
    c = Clock()
    p, keys, _ = signed_file(tmp_path, body(c))
    keyfile = tmp_path / "keys.json"
    keyfile.write_text(json.dumps(keys))
    root = tmp_path / "race"
    worker = """
import json,sys
from pathlib import Path
from canary_public.test_session03 import Clock
from btc_quant_agent.platform.canary import session03 as s
c=Clock();scope=s.load_session03(sys.argv[1],c.wall(),fabricated_keys=json.loads(Path(sys.argv[2]).read_text()))
scope.reserve_launch(c,Path(sys.argv[3]),native=False)
"""
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(s.ROOT / "src") + os.pathsep + str(s.ROOT / "tests"),
    }
    args = [sys.executable, "-c", worker, str(p), str(keyfile), str(root)]
    children = [
        subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(2)
    ]
    outputs = [child.communicate(timeout=30) for child in children]
    assert sorted(child.returncode for child in children) == [0, 1], outputs
    assert any("ALREADY_CONSUMED" in err for _, err in outputs)
    assert s.reconcile(root)["request_count"] is None
