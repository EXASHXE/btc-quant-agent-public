"""OFFLINE_SYNTHETIC fixtures only, ephemeral signers under pytest /tmp roots."""

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from btc_quant_agent.platform.canary import session04 as s
from btc_quant_agent.platform.canary import session02
from btc_quant_agent.platform.canary.public_policy import PublicStop
from btc_quant_agent.platform.canary.session04_acceptance import evaluate
from btc_quant_agent.platform.core import fingerprint
from .test_session03 import Clock, body as previous_body
from .test_session02 import Backend


def signed(tmp_path, clock=None, duration=30000, **updates):
    assert str(tmp_path).startswith('/tmp/'), "OFFLINE_SYNTHETIC_SIGNERS_REQUIRE_TMP"
    clock = clock or Clock()
    b = previous_body(clock, duration)
    b.update(version=s.VERSION, session_id=s.SESSION_ID,
             authorization_reference="OWNER-V070-L4-RUNTIME-SESSION04-OFFLINE_SYNTHETIC",
             authorized_operator_key_id="OFFLINE_SYNTHETIC_SESSION04", output_path=str(s.SESSION_OUTPUT),
             source_sha256_fingerprint=fingerprint(s.source_hashes()),
             trial_purpose="DIAGNOSTIC_RUNTIME_ONLY", unresolved_native_reliability_explicitly_accepted=True,
             predeclared_acceptance_sha256=s.sha(s.ACCEPTANCE), egress_route=s.APPROVED_ROUTE,
             ws_messages_per_second=200, pending_records=128, automatic_restart=False,
             automatic_request_retry=False, automatic_reconnect=False)
    b.update(updates)
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    model = s.GrantBody.model_validate_json(json.dumps(b))
    e = {"grant": b, "key_id": b["authorized_operator_key_id"], "signature_algorithm": "Ed25519",
         "signature_base64": base64.b64encode(private.sign(session02.signed_bytes(model))).decode()}
    path = tmp_path / "OFFLINE_SYNTHETIC_NEVER_OWNER_GRANT.json"
    path.write_text(json.dumps(e))
    keys = {e["key_id"]: {"public_key_base64": base64.b64encode(public).decode(),
                           "public_key_sha256": hashlib.sha256(public).hexdigest(),
                           "verified_owner_reference": b["authorization_reference"], "session_id": s.SESSION_ID,
                           "launch_window_start_utc_ms": b["launch_window_start_utc_ms"],
                           "launch_window_end_utc_ms": b["launch_window_end_utc_ms"]}}
    return clock, path, keys, e


def prepared(tmp_path, **kw):
    c, p, keys, _ = signed(tmp_path, **kw)
    return c, s.load_session04(p, c.wall(), fabricated_keys=keys)


def test_unprovisioned_authority_and_default_disabled_before_any_output(tmp_path):
    c, p, keys, _ = signed(tmp_path)
    assert s.read_owner_keys() == {} and not s.SESSION_OUTPUT.exists()
    with pytest.raises(PublicStop, match="INDEPENDENT_OWNER_AUTHORIZATION_REQUIRED"):
        s.load_session04(p, c.wall())
    scope = s.load_session04(p, c.wall(), fabricated_keys=keys)
    with pytest.raises(PublicStop, match="DEFAULT_DISABLED"):
        s.run_session04(scope, clock=c)
    with pytest.raises(PublicStop, match="OFFLINE_SYNTHETIC_CANNOT_ACTIVATE_NATIVE"):
        scope.preflight(c, native=True)
    assert not s.SESSION_OUTPUT.exists()


@pytest.mark.parametrize("command", [["preflight"], ["run"], ["run", "--enable-public-network"]])
def test_cli_absent_owner_grant_blocks_before_clock_transport_or_network(command):
    completed = subprocess.run([sys.executable, "tools/launch_runtime_session04.py", *command],
                               capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src"})
    result = json.loads(completed.stdout)
    assert completed.returncode == 2 and result["status"] == "BLOCKED"
    assert result["native_market_requests"] == 0 and not result["source_qualified"]
    assert not s.SESSION_OUTPUT.exists()


@pytest.mark.parametrize("fault", ["signature", "signer", "key_hash", "key_session", "key_window", "source", "spec", "docs", "expired"])
def test_forged_signer_hash_session_window_or_expired_authority_fails(tmp_path, fault):
    c, p, keys, e = signed(tmp_path)
    if fault == "signature":
        e["signature_base64"] = base64.b64encode(b'x' * 64).decode()
    elif fault == "signer":
        e["key_id"] = "OFFLINE_SYNTHETIC_OTHER"
    elif fault.startswith("key_"):
        key = {"key_hash": "public_key_sha256", "key_session": "session_id", "key_window": "launch_window_end_utc_ms"}[fault]
        keys[e["key_id"]][key] = 1 if fault == "key_window" else "0" * 64
    elif fault in ("source", "spec", "docs"):
        key = {"source": "source_sha256_fingerprint", "spec": "predeclared_acceptance_sha256", "docs": "documentation_fingerprint"}[fault]
        e["grant"][key] = "0" * 64
    else:
        c.advance(30000)
    p.write_text(json.dumps(e))
    with pytest.raises(PublicStop):
        s.load_session04(p, c.wall(), fabricated_keys=keys)


@pytest.mark.parametrize("field,value", [
    ("session_id", s.previous.SESSION_ID), ("pending_records", 129),
    ("symbols", ["BTCUSDT"]), ("endpoint_ids", ["private_account"]),
    ("external_notifications", True), ("account_or_order_operations", True),
    ("wall_jump_ms", 51), ("automatic_restart", True), ("automatic_request_retry", True),
    ("automatic_reconnect", True), ("unresolved_native_reliability_explicitly_accepted", False),
    ("egress_route", {**s.APPROVED_ROUTE, "proxy_port": 7898}),
])
def test_signed_scope_cannot_expand_or_infer_diagnostic_amendment(tmp_path, field, value):
    with pytest.raises(ValueError):
        signed(tmp_path, **{field: value})


@pytest.mark.parametrize("remaining,allowed", [(25000, True), (24999, False)])
def test_inclusive_startup_margin_and_single_durable_reservation(tmp_path, remaining, allowed):
    c, scope = prepared(tmp_path)
    c.advance(30000 - remaining)
    root = tmp_path / "OFFLINE_SYNTHETIC_RESERVATION"
    if not allowed:
        with pytest.raises(PublicStop, match="INSUFFICIENT_REMAINING_WINDOW"):
            scope.reserve_launch(c, root, native=False)
        assert not root.exists()
        return
    scope.reserve_launch(c, root, native=False)
    marker = json.loads((root / "launch_reservation.json").read_text())
    assert marker["session_id"] == s.SESSION_ID and marker["fabricated_authority"] is True
    assert scope.end_ms - scope.actual_start_ms == 25000
    with pytest.raises(PublicStop, match="CONSUMED"):
        scope.reserve_launch(c, root, native=False)
    assert s.previous.reconcile(root) == {"status": "CONSUMED_EXECUTION_UNKNOWN", "request_count": None, "retry_authorized": False}


def test_crash_after_durable_reservation_consumes_attempt(tmp_path):
    c, p, keys, _ = signed(tmp_path)
    keyfile = tmp_path / "OFFLINE_SYNTHETIC_PUBLIC_FIXTURE.json"
    keyfile.write_text(json.dumps(keys))
    out = tmp_path / "OFFLINE_SYNTHETIC_CRASH"
    code = '''import json,os,sys
from pathlib import Path
from btc_quant_agent.platform.canary.session04 import load_session04
from tests.canary_public.test_session03 import Clock
c=Clock();s=load_session04(sys.argv[1],c.wall(),fabricated_keys=json.loads(Path(sys.argv[2]).read_text()))
s.reserve_launch(c,Path(sys.argv[3]),native=False)
os._exit(73)
'''
    result = subprocess.run([sys.executable, "-c", code, str(p), str(keyfile), str(out)],
                            env={**os.environ, "PYTHONPATH": "src:."})
    assert result.returncode == 73
    assert s.previous.reconcile(out)["status"] == "CONSUMED_EXECUTION_UNKNOWN"
    scope = s.load_session04(p, c.wall(), fabricated_keys=keys)
    with pytest.raises(PublicStop, match="CONSUMED"):
        scope.reserve_launch(c, out, native=False)


def test_existing_consumed_session03_cannot_be_rebound_to_session04(tmp_path):
    _, _, _, e = signed(tmp_path)
    e["grant"]["session_id"] = s.previous.SESSION_ID
    with pytest.raises(ValueError):
        s.GrantEnvelope.model_validate_json(json.dumps(e))
    assert s.previous.reconcile()["retry_authorized"] is False
    assert s.previous.SESSION_ID != s.SESSION_ID and s.previous.SESSION_OUTPUT != s.SESSION_OUTPUT


def test_instrumented_runtime_replays_session04_and_never_promotes_synthetic(tmp_path):
    c, scope = prepared(tmp_path)
    out = tmp_path / "OFFLINE_SYNTHETIC_RUN"
    r = s.run_session04(scope, enabled=True, clock=c, backend=Backend(c), output=out)
    assert r["replay"]["status"] == "PARITY_VERIFIED"
    assert r["session_id"] == s.SESSION_ID and r["flex_window_contract"]["version"] == s.VERSION
    assert r["runtime_telemetry"]["version"] == "L4_RUNTIME_TIMINGS_V1"
    assert not r["native_runtime_acceptance"]["passed"] and not r["source_qualified"]
    assert r["native_market_requests"] == 0
    assert "NATIVE_ORIGIN_REQUIRED" in evaluate(r)["reasons"]
    assert s.previous.reconcile(out)["status"] == "CONSUMED_SEALED"


def test_private_account_and_non_bbo_source_denied(tmp_path):
    c, scope = prepared(tmp_path)
    for endpoint in ("private", "/fapi/v2/account", "binance_usdm_oi", "binance_usdm_klines_rest"):
        with pytest.raises(PublicStop):
            scope.validate_request(endpoint, {}, c.wall())
    with pytest.raises(PublicStop):
        scope.streams("market")
    for route in ({"egress_mode": "DIRECT"}, {**s.APPROVED_ROUTE, "proxy_port": 7898}):
        with pytest.raises(PublicStop):
            scope.validate_route(route)


@pytest.mark.parametrize("status", [451, 418, 429, 503])
def test_denial_rate_and_transient_failure_never_retry_or_qualify(tmp_path, status):
    c, scope = prepared(tmp_path)
    backend = Backend(c, denial=status)
    result = s.run_session04(scope, enabled=True, clock=c, backend=backend,
                            output=tmp_path / "OFFLINE_SYNTHETIC_DENIAL")
    assert len(backend.calls) == 1 and not backend.urls
    assert not result["native_runtime_acceptance"]["passed"] and not result["source_qualified"]
    if status in (451, 418, 429):
        assert result["status"] == "BLOCKED"
    assert result["native_market_requests"] == 0 and result["sockets_closed"]


def test_predeclared_checker_all_boundaries_are_diagnostic_only(tmp_path):
    """Native-looking dict stays isolated OFFLINE_SYNTHETIC, with no signatures/trust."""
    from copy import deepcopy
    from btc_quant_agent.platform.canary.telemetry import RuntimeTelemetry

    timing = RuntimeTelemetry().snapshot()
    timing["queue_high_water"] = 96
    timing["counters"].update(ingest_started=6, ingest_accepted=6, durable_records=6, enqueued=3, dequeued=3)
    for stage, count in (("record.source_receive_to_decision", 6), ("record.receive_to_checkpoint", 3)):
        timing["durations"][stage].update(count=count, p50_upper=500000000, p95_upper=1000000000, p99_upper=2000000000)
    r = {"session_id": s.SESSION_ID, "exposure": "PUBLIC_CANARY", "stop_reason": "AUTHORIZED_UTC_END",
         "sockets_closed": True, "receiver_threads_stopped": True, "safe_terminal_evidence": True,
         "finalization_errors": [], "uncommitted_or_unapplied_frames": 0,
         "retained_queue_depth_at_finalization": 0, "durably_charged_ws_records_not_enqueued": 0,
         "replay": {"status": "PARITY_VERIFIED", "unpaired_raw_chunks": 0, "expired_chunks": 0, "checked_pairs": 1},
         "operator_monotonic_elapsed_ms": 30000, "authorized_end_exclusive_ms": 31000,
         "started_wall_ms": 1000, "stopped_wall_ms": 31000, "runtime_telemetry": timing,
         "transport_metrics": {"rest_requests": 3, "ws_frames": 3, "ws_data_enqueued": 3, "ws_connections": 1, "reconnects": 0},
         "clock_validation_evidence": {"clock_fault": None, "independent_probes": 2,
              "distinct_qualified_quotes": dict.fromkeys(s.SYMBOLS, 1)},
         "model": {"clock_epoch_failure": None, "clock_estimate": {"uncertainty_ms": 100,
                   "probes": [{"available": {"wall_ms": 30000}}, {"available": {"wall_ms": 30020}}]}}}
    result = evaluate(r)
    assert result["passed"] and result["completion"] == "DIAGNOSTIC_ONLY"
    assert not result["source_qualified"] and not result["long_acquisition_authorized"]
    for path, value in [
        (("stop_reason",), "BACKPRESSURE_PENDING_EXCEEDED"),
        (("stop_reason",), "RATE_LIMIT_CIRCUIT_OPEN"),
        (("runtime_telemetry", "queue_high_water"), 97),
        (("runtime_telemetry", "counters", "enqueue_full"), 1),
        (("runtime_telemetry", "counters", "durable_records"), 5),
        (("runtime_telemetry", "durations", "record.source_receive_to_decision", "p99_upper"), 2000000001),
        (("runtime_telemetry", "durations", "record.receive_to_checkpoint", "p95_upper"), None),
        (("clock_validation_evidence", "independent_probes"), 1),
        (("model", "clock_estimate", "uncertainty_ms"), 101),
        (("stopped_wall_ms",), 330021),
        (("sockets_closed",), False), (("safe_terminal_evidence",), False),
    ]:
        bad = deepcopy(r)
        parent = bad
        for key in path[:-1]:
            parent = parent[key]
        parent[path[-1]] = value
        assert not evaluate(bad)["passed"], path
    assert s.read_owner_keys() == {} and not s.SESSION_OUTPUT.exists()


def test_offline_synthetic_signed_handoff_roundtrip_and_tamper(tmp_path, monkeypatch):
    """Exercise both authenticated protocols using ONLY /tmp simulation authority.

    The in-memory native-shaped backend cannot open sockets. Its native-labelled
    counters are simulated, and the outer OFFLINE_SYNTHETIC marker is mandatory.
    No genuine trust file, native output or actual authorizing grant is changed.
    """
    (tmp_path / "OFFLINE_SYNTHETIC_NOT_NATIVE_AUTHORIZATION").write_text("contract simulation only\n")
    output = tmp_path / "artifacts/live_public_canary_runtime_v1/session_04"
    output.parent.mkdir(parents=True)
    monkeypatch.setattr(s, "SESSION_OUTPUT", output)
    c, path, keys, _ = signed(tmp_path)
    monkeypatch.setattr(s, "read_owner_keys", lambda: keys)
    monkeypatch.setenv("L4_CONTROLLED_EGRESS", "1")
    monkeypatch.setenv("L4_EGRESS_PROXY_URL", "http://127.0.0.1:7897")
    scope = s.load_session04(path, c.wall())
    backend = Backend(c)
    backend.exposure = "PUBLIC_CANARY"  # ONLY this isolated, socket-denied simulation.
    backend.route_info = s.APPROVED_ROUTE
    result = s.run_session04(scope, enabled=True, clock=c, backend=backend)
    assert result["native_runtime_acceptance"]["passed"], result["native_runtime_acceptance"]
    assert result["status"] == "DIAGNOSTIC_ONLY" and not result["source_qualified"]
    assert len(backend.calls) == 3
    longroot = Path(os.environ.get("L4_OFFLINE_LONG_WORKSPACE", str(s.ROOT.parent / "l4-longhorizon-source-shadow-01")))
    keypath = tmp_path / "OFFLINE_SYNTHETIC_PUBLIC_FIXTURE.json"
    keypath.write_text(json.dumps(keys))
    code = '''import base64,hashlib,json,sys
def deny(event,args):
 if event in ('socket.connect','socket.getaddrinfo','socket.sendto'):raise AssertionError('OFFLINE_SYNTHETIC_NETWORK_FORBIDDEN')
sys.addaudithook(deny)
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from btc_quant_agent.platform.canary import clock_eligibility as q, longhorizon as lh
from longhorizon.fixtures import body
root=Path(sys.argv[1]); assert str(root).startswith('/tmp/')
assert (root.parents[2]/'OFFLINE_SYNTHETIC_NOT_NATIVE_AUTHORIZATION').is_file()
keys=json.loads(Path(sys.argv[2]).read_text()); owner=json.loads((root/'owner_signed_grant.json').read_text())
r=json.loads((root/'report.json').read_text()); now=r['stopped_wall_ms']+10
target=lh.GrantBody.model_validate_json(json.dumps({**body(start=now,duration=60000),'egress_route':lh.APPROVED_ROUTE}))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
names=['report.json','receipt_seal.json','started.json','source_grant.json','source_sha256.json','endpoint_policy.json','replay_manifest.json','owner_signed_grant.json','launch_reservation.json']
names=list(dict.fromkeys(names+list(json.loads((root/'receipt_seal.json').read_text()))))
names += [x['kind']+'/'+x['sha256']+'.json.gz' for x in r['replay']['manifest']]
b={'version':'L4_CLOCK_QUALIFICATION_BUNDLE_V2','family':'SESSION04_RUNTIME_V1','source_session_id':r['session_id'],
 'grant_version':owner['grant']['version'],'acquisition_origin':'NATIVE_PUBLIC_CANARY_CAPTURE','exposure':'PUBLIC_CANARY',
 'clock_contract':'L4_CLOCK_DOMAIN_V2','scope_hash':r['scope_hash'],'owner_grant_sha256':sha(root/'owner_signed_grant.json'),
 'original_receipt_sha256':sha(root/'report.json'),'receipt_seal_sha256':sha(root/'receipt_seal.json'),
 'source_config_sha256':sha(root/'source_grant.json'),'source_sha256_fingerprint':owner['grant']['source_sha256_fingerprint'],
 'target_binding_sha256':q.target_binding(target),'capture_end_utc_ms':r['stopped_wall_ms'],'issued_utc_ms':now,
 'expires_utc_ms':now+1000,'artifacts':{n:sha(root/n) for n in names},
 'predeclared_acceptance_sha256':owner['grant']['predeclared_acceptance_sha256']}
private=Ed25519PrivateKey.generate(); public=private.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
auditor={'public_key_base64':base64.b64encode(public).decode(),'public_key_sha256':hashlib.sha256(public).hexdigest(),
 'purpose':'INDEPENDENT_NATIVE_CAPTURE_AUDITOR','family':b['family'],'original_receipt_sha256':b['original_receipt_sha256'],
 'receipt_seal_sha256':b['receipt_seal_sha256'],'owner_grant_sha256':b['owner_grant_sha256'],'expires_utc_ms':now+1000}
okey=keys[owner['key_id']]; okey={k:okey[k] for k in ('public_key_base64','public_key_sha256','verified_owner_reference')}
okey.update(family=b['family'],owner_grant_sha256=b['owner_grant_sha256'])
trust={'version':'L4_CLOCK_QUALIFICATION_TRUST_V2','owner_keys':{owner['key_id']:okey},'capture_keys':{'OFFLINE_SYNTHETIC_AUDITOR':auditor}}
trustpath=root/'OFFLINE_SYNTHETIC_TEST_TRUST.json';trustpath.write_text(json.dumps(trust));q.TRUST_V2=trustpath
bundle={'attestation':b,'capture_key_id':'OFFLINE_SYNTHETIC_AUDITOR','signature_algorithm':'Ed25519',
 'signature_base64':base64.b64encode(private.sign(q.canonical(b))).decode()}
p=root/'OFFLINE_SYNTHETIC_BUNDLE.json';p.write_text(json.dumps(bundle))
target=target.model_copy(update={'clock_qualification_receipt_sha256':sha(p)})
result=q.verify_bundle(p,target,now)
assert result['status']=='AUTHENTICATED_CLOCK_ELIGIBILITY_ONLY' and result['native_acquisition_authorized'] is False
files={n:(root/n).read_bytes() for n in names}
bad=dict(r);bad['stop_reason']='BACKPRESSURE_PENDING_EXCEEDED';bad['status']='PARTIAL'
badfiles={**files,'report.json':json.dumps(bad).encode()}
try:q.verify_capture(q.BundleBodyV2.model_validate_json(json.dumps(b)),owner['grant'],owner,badfiles,target,now)
except q.QualificationError as e:assert e.reason==q.Reason.INCOMPLETE
else:raise AssertionError('FAILED_SOURCE_ACCEPTED_FOR_LONG')
original_signature=bundle['signature_base64'];bundle['signature_base64']=base64.b64encode(b'x'*64).decode()
p.write_text(json.dumps(bundle));target=target.model_copy(update={'clock_qualification_receipt_sha256':sha(p)})
try:q.verify_bundle(p,target,now)
except q.QualificationError as e:assert e.reason==q.Reason.SIGNATURE
else:raise AssertionError('FORGED_AUDITOR_SIGNATURE_ACCEPTED')
bundle['signature_base64']=original_signature
bundle['attestation']['expires_utc_ms']=now;p.write_text(json.dumps(bundle))
target=target.model_copy(update={'clock_qualification_receipt_sha256':sha(p)})
try:q.verify_bundle(p,target,now)
except q.QualificationError as e:assert e.reason==q.Reason.STALE
else:raise AssertionError('EXPIRED_FIXTURE_ACCEPTED')
print(json.dumps({'mode':'OFFLINE_SYNTHETIC','actual_network_requests':0,'contract_roundtrip':'PASS'}))
'''
    completed = subprocess.run([sys.executable, "-c", code, str(output), str(keypath)], cwd=longroot,
        env={**os.environ, "PYTHONPATH": "src:tests"}, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout)["actual_network_requests"] == 0
