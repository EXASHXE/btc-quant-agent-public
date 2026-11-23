from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from btc_quant_agent.platform.native.contract import authorize, Policy, source_hash
from btc_quant_agent.platform.native.journal import Journal
from btc_quant_agent.platform.native.runtime import run_native
from helpers import QAClock, authority
from btc_quant_agent.platform.rc_fixture import TRIGGER


@pytest.mark.parametrize(
    "change", ["signature", "source", "executable", "scope", "window", "owner", "auditor", "key", "rights"]
)
def test_authority_denies_before_network(tmp_path, change):
    policy = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, env, audit, roots = authority(policy, tmp_path / "out", TRIGGER)
    values = dict(
        source_hash=source_hash(), executable_hash="a" * 64, now_ms=TRIGGER, exposure="SYNTHETIC_NETWORK"
    )
    if change == "signature":
        env = env.model_copy(update={"signature_base64": "eA=="})
    if change == "source":
        values["source_hash"] = "c" * 64
    if change == "executable":
        values["executable_hash"] = "c" * 64
    if change == "scope":
        policy = policy.model_copy(update={"streams": ["btcusdt@bookTicker"]})
    if change == "window":
        values["now_ms"] = g.end_ms
    if change == "owner":
        roots["owner"] = {}
    if change == "auditor":
        roots["auditor"] = {}
    if change == "key":
        roots["owner"][env.key_id]["public_key_sha256"] = "c" * 64
    if change == "rights":
        roots["rights_sha256"] = "c" * 64
    with pytest.raises(ValueError):
        authorize(env, audit, roots, policy, **values)
    assert not Path(g.output).exists()


@pytest.mark.parametrize(
    "fault",
    ["before_reservation", "after_reservation", "before_frame_write", "before_commit", "after_commit"],
)
def test_durable_fault_and_single_use(tmp_path, fault):
    policy = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, *_ = authority(policy, tmp_path / "out", TRIGGER)
    journal = Journal(tmp_path / "registry.sqlite")

    def inject(phase):
        if phase == fault:
            raise OSError("INJECTED_DURABLE_FAILURE")

    if fault in {"before_reservation", "after_reservation"}:
        journal.fault = inject
        with pytest.raises(OSError):
            journal.reserve(g)
    else:
        journal.reserve(g)
        journal.fault = inject
        with pytest.raises(OSError):
            journal.receive(g, b"{}", TRIGGER, 0)
    journal.fault = lambda _: None
    journal.recover()
    journal.verify()
    with journal.db() as db:
        consumed = db.execute("SELECT count(*) FROM sessions").fetchone()[0]
    if fault != "before_reservation":
        assert consumed == 1
    assert not (tmp_path / "out/terminal.json").exists()


@pytest.mark.parametrize("depth", [96, 128])
def test_actual_queue_guard(tmp_path, depth):
    policy = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, *_ = authority(policy, tmp_path / "out", TRIGGER)
    j = Journal(tmp_path / "registry.sqlite")
    j.reserve(g)
    with pytest.raises(ValueError, match="QUEUE"):
        j.receive(g, b"{}", TRIGGER, depth)
    assert j.usage(g.session_id)["incoming"] == 0


@pytest.mark.parametrize("budget", ["requests", "incoming", "outgoing", "storage", "disk"])
def test_budget_and_disk_failure(tmp_path, monkeypatch, budget):
    policy = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, *_ = authority(policy, tmp_path / "out", TRIGGER, messages_max=1)
    j = Journal(tmp_path / "registry.sqlite")
    j.reserve(g)
    with pytest.raises((ValueError, OSError)):
        if budget == "incoming":
            j.receive(g, b"{}", TRIGGER, 0)
            j.receive(g, b"{}", TRIGGER, 0)
        elif budget in {"requests", "outgoing"}:
            j.charge(g, budget, 1, {})
            j.charge(g, budget, 1, {})
        elif budget == "storage":
            j.check_space(g, g.storage_bytes_max)
        else:
            from types import SimpleNamespace

            monkeypatch.setattr("shutil.disk_usage", lambda _: SimpleNamespace(free=0))
            j.receive(g, b"{}", TRIGGER, 0)
    j.verify()


def test_clock_age_and_uncertainty(tmp_path):
    p = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, *_ = authority(p, tmp_path / "out", TRIGGER, end_ms=TRIGGER + 1000000)
    c = QAClock(TRIGGER)
    c.sample()
    c.estimate = {"at_mono_ms": c.mono - 300001, "uncertainty_ms": 1}
    with pytest.raises(ValueError, match="STALE"):
        c.check(g)
    c.estimate = {"at_mono_ms": c.mono, "uncertainty_ms": 101}
    with pytest.raises(ValueError, match="UNCERTAINTY"):
        c.check(g)


@pytest.mark.parametrize("phase", ["before_reservation", "after_reservation", "after_frame_write"])
def test_process_crash_no_restart(tmp_path, phase):
    policy = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, *_ = authority(policy, tmp_path / "out", TRIGGER)
    root = Path(__file__).resolve().parents[2]
    script = """import os,json
from btc_quant_agent.platform.native.contract import Grant
from btc_quant_agent.platform.native.journal import Journal
g=Grant.model_validate_json(os.environ['E_QA_GRANT'])
j=Journal(os.environ['E_QA_REGISTRY'])
def fault(phase):
 if phase==os.environ['E_QA_FAULT']:os._exit(73)
j.fault=fault
j.reserve(g)
j.receive(g,b'{}',g.start_ms+10,0)
"""
    env = {
        **os.environ,
        "PYTHONPATH": str(root / "src"),
        "E_QA_GRANT": g.model_dump_json(),
        "E_QA_REGISTRY": str(tmp_path / "registry.sqlite"),
        "E_QA_FAULT": phase,
    }
    result = subprocess.run([sys.executable, "-B", "-c", script], env=env, cwd=root, timeout=10)
    assert result.returncode == 73
    journal = Journal(tmp_path / "registry.sqlite")
    journal.recover()
    assert journal.verify()["frames"] == (1 if phase == "after_frame_write" else 0)
    if phase != "before_reservation":
        assert journal.usage(g.session_id)["status"] == "CRASHED"


def test_actual_native_entry_has_no_worker_authority(tmp_path):
    policy = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, env, audit, _ = authority(policy, tmp_path / "out", TRIGGER, exposure="NATIVE_UNQUALIFIED")
    for name, value in [("grant", env), ("audit", audit), ("config", policy)]:
        (tmp_path / name).write_text(value.model_dump_json())
    with pytest.raises(ValueError, match="TRUST"):
        run_native(
            tmp_path / "grant",
            tmp_path / "audit",
            tmp_path / "config",
            tmp_path / "missing-wheel",
            tmp_path / "registry",
        )
    assert not (tmp_path / "registry").exists()


def test_transport_requires_verified_capability(tmp_path):
    from btc_quant_agent.platform.native.transport import Transport

    p = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, *_ = authority(p, tmp_path / "out", TRIGGER)
    j = Journal(tmp_path / "registry.sqlite")
    with pytest.raises(ValueError, match="AUTHORIZATION_CAPABILITY"):
        Transport(p, g, j, QAClock(TRIGGER), qa_proxy=True)


def test_exclusive_worker_lock_and_failed_terminal(tmp_path):
    from btc_quant_agent.platform.native.runtime import exclusive

    with exclusive(tmp_path / "worker.lock"):
        with pytest.raises(OSError):
            with exclusive(tmp_path / "worker.lock"):
                raise AssertionError("Lock must be exclusive")
    p = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, *_ = authority(p, tmp_path / "out", TRIGGER)
    j = Journal(tmp_path / "registry.sqlite")
    j.reserve(g)
    report = j.terminal(g, "SOCKET_CLOSE_FAILED", False)
    assert report["transport_closed"] is False
    assert j.usage(g.session_id)["status"] == "FAILED_CLOSURE"


def test_receipt_mutation_detected(tmp_path):
    from test_runtime import run, message

    _, j, g, _, _ = run(tmp_path, [message()])
    with j.db() as db:
        db.execute("DROP TRIGGER immutable_receipts_u")
        db.execute("UPDATE receipts SET value=x'7b7d'")
    with pytest.raises(ValueError, match="TAMPER"):
        j.records(g.session_id)


def test_durable_request_counter_tamper_rejected(tmp_path):
    p = Policy(proxy_ip="127.0.0.1", proxy_port=1234)
    g, *_ = authority(p, tmp_path / "out", TRIGGER)
    j = Journal(tmp_path / "registry.sqlite")
    j.reserve(g)
    j.charge(g, "requests", g.requests_max, {})
    with j.db() as db:
        db.execute("UPDATE sessions SET requests=0 WHERE id=?", (g.session_id,))
    with pytest.raises(ValueError, match="ACCOUNTING_TAMPER"):
        j.charge(g, "requests", g.requests_max, {})


def test_ping_pong_deadline_and_identity():
    from types import SimpleNamespace
    from collections import deque
    from websockets.frames import Frame, Opcode
    from btc_quant_agent.platform.native.transport import Transport

    clock = QAClock(TRIGGER)
    clock.estimate = {"at_mono_ms": clock.mono, "uncertainty_ms": 1}
    g = SimpleNamespace(start_ms=TRIGGER - 100, end_ms=TRIGGER + 1000000)
    t = object.__new__(Transport)
    t.clock, t.grant = clock, g
    t.last_activity_mono = clock.mono - 180000
    t.awaiting_pong = None
    sent = []
    t.protocol = SimpleNamespace(send_ping=lambda value: sent.append(value))
    t.flush = lambda: None
    t.heartbeat()
    assert len(sent) == 1
    clock.wall += 10001
    clock.mono += 10001
    with pytest.raises(ValueError, match="PONG_TIMEOUT"):
        t.heartbeat()
    t.pending = deque([(Frame(Opcode.PONG, b"wrong"), clock.sample())])
    with pytest.raises(ValueError, match="PONG_IDENTITY"):
        t.next_event()


def test_independent_capture_audit_binding(tmp_path):
    from test_runtime import run, message
    from helpers import key, sign
    from btc_quant_agent.platform.native.audit import (
        challenge,
        verify_capture_audit,
        CaptureAuditBody,
        CaptureAuditEnvelope,
    )

    _, j, g, _, _ = run(tmp_path, [message()])
    fields = challenge(j, g.session_id)
    private, trust = key(g.auditor_key_id)
    roots = {"auditor": trust}
    body = CaptureAuditBody(**fields, independently_verified_reference="FABRICATED_QA_NOT_REAL_PROVENANCE")
    envelope = sign(body, g.auditor_key_id, private, CaptureAuditEnvelope)
    assert verify_capture_audit(j, g.session_id, envelope, roots, synthetic=True)["source_qualified"] is False
    changed = body.model_copy(update={"terminal_sha256": "c" * 64})
    envelope = sign(changed, g.auditor_key_id, private, CaptureAuditEnvelope)
    with pytest.raises(ValueError, match="BINDING"):
        verify_capture_audit(j, g.session_id, envelope, roots, synthetic=True)


@pytest.mark.parametrize("depth", [97, 128])
def test_receiver_batch_overflow_stops_without_silent_admission(depth):
    from types import SimpleNamespace
    from collections import deque
    from websockets.frames import Frame, Opcode
    from btc_quant_agent.platform.native.transport import Transport

    t = object.__new__(Transport)
    t.pending = deque()
    t.guard = lambda *_: 1
    t.policy = SimpleNamespace(max_frame_bytes=65536)
    t.clock = QAClock(TRIGGER)
    t.sock = SimpleNamespace(settimeout=lambda _: None, recv=lambda _: b"fabricated_batch")
    t.protocol = SimpleNamespace(
        receive_data=lambda _: None, events_received=lambda: [Frame(Opcode.PING, b"x") for _ in range(depth)]
    )
    with pytest.raises(ValueError, match="QUEUE"):
        t.next_event()
    assert len(t.pending) == 0


def test_optional_hourly_scope_requires_all_mandatory_series():
    from btc_quant_agent.platform.native.contract import REQUIRED_STREAMS

    assert Policy(proxy_ip="127.0.0.1", proxy_port=1234, streams=REQUIRED_STREAMS).streams == REQUIRED_STREAMS
    with pytest.raises(ValueError, match="EXACT_STREAM_SCOPE"):
        Policy(proxy_ip="127.0.0.1", proxy_port=1234, streams=REQUIRED_STREAMS[:-1])
