import json
import os
import signal
import subprocess
import sys
import time
import pytest

from btc_quant_agent.platform.canary.public_policy import ROOT, START, END, Window, PublicStop
from btc_quant_agent.platform.canary.public_network import DirectSockets
from .fixtures import Clock


def child(mode, path):
    return subprocess.run(
        [sys.executable, str(ROOT / "tools/public_canary_worker.py"), mode, str(path)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=15,
    )


def test_actual_process_orphan_recovery_and_native_shape_replay(tmp_path):
    p = child("crash-rename", tmp_path)
    assert p.returncode == 67, p.stderr
    p = child("recover", tmp_path)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout)
    assert r["status"] == "INCOMPLETE" and r["unpaired_raw_chunks"] == 1
    p = child("complete", tmp_path)
    assert p.returncode == 0, p.stderr
    r = json.loads(p.stdout)
    assert r["status"] == "PARITY_VERIFIED" and r["checked_pairs"] == 1
    assert json.loads(child("recover", tmp_path).stdout)["checked_pairs"] == 1


def test_sigint_stops_own_finite_process_without_native_network(tmp_path):
    p = subprocess.Popen(
        [sys.executable, str(ROOT / "tools/public_canary_worker.py"), "run-until-stop", str(tmp_path)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        until = time.monotonic() + 10
        while not (tmp_path / "worker_ready").exists() and time.monotonic() < until:
            if p.poll() is not None:
                break
            time.sleep(0.02)
        assert (tmp_path / "worker_ready").exists()
        p.send_signal(signal.SIGINT)
        out, err = p.communicate(timeout=10)
        assert p.returncode == 0, (out, err)
        r = json.loads(out)
        assert "EMERGENCY_STOP" in r["stop_reason"]
        assert r["sockets_closed"] and r["threads_stopped"] and r["native_market_requests"] == 0
    finally:
        if p.poll() is None:
            p.kill()
            p.communicate(timeout=5)


def test_no_tcp_socket_after_dns_returns_past_window(monkeypatch):
    clock = Clock(END - 10)
    window = Window(clock)
    calls = []

    def resolve(*a, **kw):
        clock.set(END + 1)
        return [(2, 1, 6, "", ("8.8.8.8", 443))]

    monkeypatch.setattr("socket.getaddrinfo", resolve)
    monkeypatch.setattr("socket.socket", lambda *a, **kw: calls.append("socket"))
    network = DirectSockets(window.check)
    with pytest.raises(PublicStop, match="EXPIRED"):
        network.connect_tcp("fapi.binance.com", 443)
    assert not calls


def test_private_resolution_and_unix_routes_are_denied(monkeypatch):
    network = DirectSockets(Window(Clock()).check)
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(PublicStop, match="PRIVATE"):
        network.connect_tcp("fapi.binance.com", 443)
    with pytest.raises(PublicStop, match="UNIX"):
        network.connect_unix_socket("/tmp/fake")


def test_deadline_latches_even_when_wall_clock_moves_back():
    clock = Clock(END - 1)
    window = Window(clock)
    clock.set(END)
    with pytest.raises(PublicStop, match="EXPIRED"):
        window.check()
    clock.set(START)
    with pytest.raises(PublicStop, match="EXPIRED"):
        window.check()


def test_utc_uncertainty_keeps_requests_inside_true_window():
    clock = Clock(START + 10)
    clock.utc_uncertainty_ms = 100
    with pytest.raises(PublicStop, match="NOT_OPEN"):
        Window(clock).check()
    clock.set(END - 50)
    with pytest.raises(PublicStop, match="EXPIRED"):
        Window(clock).check()


def test_missing_receiver_clock_sync_is_technical_stop():
    clock = Clock()
    clock.sync_evidence = {"status": "UNVERIFIED"}
    clock.refresh_sync = lambda: None
    with pytest.raises(PublicStop, match="CLOCK_SYNC_UNVERIFIED"):
        Window(clock).check()
