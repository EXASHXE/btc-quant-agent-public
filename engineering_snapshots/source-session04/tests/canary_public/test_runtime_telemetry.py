"""Bounded runtime timings and durable, fail-closed negative cases; no network."""

import json
from pathlib import Path
from queue import Full
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from btc_quant_agent.platform.canary.control import BudgetGuard, CanaryStore, CircuitOpen
from btc_quant_agent.platform.canary.policy import Policy
from btc_quant_agent.platform.canary.telemetry import Histogram, RuntimeTelemetry, TimedQueue
from btc_quant_agent.platform.canary.public_io import Wire
from btc_quant_agent.platform.core import primitive


def policy():
    return Policy(endpoint_ids=("binance_usdm_bbo_ws",))


def test_nearest_rank_percentiles_counts_and_exact_maximum():
    h = Histogram(tuple(range(101)))
    for value in range(100):
        h.add(value)
    got = h.snapshot()
    assert (got["count"], got["p50_upper"], got["p95_upper"], got["p99_upper"], got["max"]) == (
        100,
        49,
        94,
        98,
        99,
    )
    assert got["sum"] == 4950 and sum(got["buckets"]) == 100


def test_empty_metrics_are_missing_not_fabricated_zero_latency():
    snap = RuntimeTelemetry().snapshot()
    assert snap["durations"]["budget.charge"]["p99_upper"] is None
    assert snap["durations"]["budget.charge"]["max"] is None


def test_fixed_histograms_and_unknown_names_cannot_grow_memory():
    t = RuntimeTelemetry()
    before = t.snapshot()["memory_bound"]
    for i in range(10000):
        t.observe("untrusted_" + str(i), i)
        t.observe("budget.charge", i)
    after = t.snapshot()
    assert after["memory_bound"] == before
    assert after["counters"]["unknown_metric"] == 10000
    assert len(after["durations"]) == before["duration_metrics"]


@pytest.mark.parametrize("value", [-1, None, True, 1.5, "UNKNOWN"])
def test_invalid_or_missing_time_never_becomes_zero(value):
    t = RuntimeTelemetry()
    t.observe("budget.charge", value)
    a = t.snapshot()
    assert a["counters"]["invalid_observations"] == 1
    assert a["durations"]["budget.charge"]["count"] == 0


def test_queue_high_water_fifo_and_full_terminal_cause():
    t = RuntimeTelemetry()
    q = TimedQueue(t)
    objects = [object() for _ in range(128)]
    for item in objects:
        q.put_wire(item, time.perf_counter_ns())
    with pytest.raises(Full):
        q.put_nowait(object())
    assert len(q.stamps) == q.qsize() == 128
    for item in objects:
        assert q.get_nowait() is item
        timing = q.take_timing(item)
        assert timing["enqueued_ns"] <= timing["dequeued_ns"]
    a = t.snapshot()
    assert a["queue_high_water"] == 128 and not q.stamps
    assert a["counters"]["enqueue_attempts"] == 129
    assert a["counters"]["enqueued"] == a["counters"]["dequeued"] == 128
    assert a["first_stop"]["stage"] == "queue.enqueue" and a["first_stop"]["pending"] == 128


def test_telemetry_never_modifies_wire_or_normalized_evidence():
    w = Wire("binance_usdm_bbo_ws", "BTCUSDT", {}, "{}", None, None, 1000, 10, 1001, 11, exposure="SYNTHETIC")
    before = w.record()
    primitive_before = primitive(w)
    t = RuntimeTelemetry()
    q = TimedQueue(t)
    q.put_wire(w, time.perf_counter_ns())
    assert q.get_nowait() is w
    q.take_timing(w)
    assert w.record() == before and primitive(w) == primitive_before


def test_timing_identity_mismatch_is_explicit_and_bounded():
    t = RuntimeTelemetry()
    q = TimedQueue(t)
    item = object()
    q.put_nowait(item)
    q.get_nowait()
    assert q.take_timing(object()) is None
    assert t.snapshot()["counters"]["timing_identity_mismatch"] == 1


def test_counters_and_histograms_are_thread_safe():
    t = RuntimeTelemetry()

    def run():
        for _ in range(500):
            t.observe("budget.charge", 1000)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for x in threads:
        x.start()
    for x in threads:
        x.join()
    assert t.snapshot()["durations"]["budget.charge"]["count"] == 2000


def test_pending_guard_circuit_is_durable_and_primary_cause(tmp_path):
    t = RuntimeTelemetry()
    store = CanaryStore(tmp_path / "state.sqlite", telemetry=t)
    guard = BudgetGuard(store, policy(), telemetry=t)
    guard.data_message(1, 127)
    with pytest.raises(CircuitOpen, match="BACKPRESSURE_BLOCKED"):
        guard.data_message(2, 128)
    q = TimedQueue(t)
    for _ in range(128):
        q.put_nowait(object())
    with pytest.raises(Full):
        q.put_nowait(object())
    a = t.snapshot()
    assert a["first_stop"]["stage"] == "budget.pending_precheck" and a["first_stop"]["pending"] == 128
    assert a["pending_at_guard"]["max"] == 128 and a["counters"]["budget_ws_charged"] == 1
    fresh = BudgetGuard(CanaryStore(tmp_path / "state.sqlite"), policy())
    with pytest.raises(CircuitOpen, match="BACKPRESSURE_BLOCKED"):
        fresh.data_message(3, 0)


def test_sqlite_context_commit_and_rollback_are_measured_without_policy_change(tmp_path):
    t = RuntimeTelemetry()
    store = CanaryStore(tmp_path / "state.sqlite", telemetry=t)
    with store._connect() as db:
        db.execute("INSERT INTO canary_values VALUES ('committed','1')")
    with pytest.raises(RuntimeError):
        with store._connect() as db:
            db.execute("INSERT INTO canary_values VALUES ('rolled_back','1')")
            raise RuntimeError("FABRICATED_BEFORE_COMMIT")
    fresh = CanaryStore(tmp_path / "state.sqlite")
    assert fresh.get_value("committed") == 1 and fresh.get_value("rolled_back") is None
    a = t.snapshot()
    assert a["counters"]["sqlite_commits"] > 0 and a["counters"]["sqlite_rollbacks"] == 1
    assert a["durations"]["sqlite.context_commit"]["max"] is not None


def test_real_lock_wait_is_measured_separately_from_commit(tmp_path):
    t = RuntimeTelemetry()
    store = CanaryStore(tmp_path / "state.sqlite", telemetry=t)
    owner = sqlite3.connect(tmp_path / "state.sqlite", check_same_thread=False)
    owner.execute("BEGIN IMMEDIATE")
    ready = threading.Event()

    def release():
        ready.set()
        time.sleep(0.05)
        owner.rollback()
        owner.close()

    thread = threading.Thread(target=release)
    thread.start()
    ready.wait()
    BudgetGuard(store, policy(), telemetry=t).data_message(1, 0)
    thread.join()
    assert t.snapshot()["durations"]["sqlite.begin_immediate"]["max"] >= 30_000_000


@pytest.mark.parametrize("phase,expected", [("before", 0), ("after", 1)])
def test_genuine_process_exit_before_after_commit_preserves_exact_prefix(tmp_path, phase, expected):
    db = tmp_path / "state.sqlite"
    CanaryStore(db)
    worker = """
import os,sqlite3,sys
from btc_quant_agent.platform.canary.control import CanaryStore,BudgetGuard
from btc_quant_agent.platform.canary.policy import Policy
from btc_quant_agent.platform.canary.telemetry import RuntimeTelemetry,TimedConnection
class Connection(sqlite3.Connection):
 def __exit__(self,*args):
  active=self.in_transaction
  if active and sys.argv[2]=='before':os._exit(31)
  result=super().__exit__(*args)
  if active and sys.argv[2]=='after':os._exit(32)
  return result
store=CanaryStore(sys.argv[1]);t=RuntimeTelemetry()
store._connect=lambda:TimedConnection(sqlite3.connect(sys.argv[1],factory=Connection),t)
BudgetGuard(store,Policy(endpoint_ids=('binance_usdm_bbo_ws',))).data_message(1,0)
"""
    p = subprocess.run([sys.executable, "-c", worker, str(db), phase], capture_output=True, text=True)
    assert p.returncode == (31 if phase == "before" else 32), p.stderr
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM canary_budget").fetchone()[0] == expected
    assert CanaryStore(db).get_value("budget_clock") == (1 if expected else None)


def test_disabled_measurement_stays_empty():
    t = RuntimeTelemetry(enabled=False)
    with t.measure("budget.charge"):
        pass
    assert t.snapshot()["counters"]["observations"] == 0


@pytest.mark.parametrize(
    "circuit,backoff,mono,reason",
    [
        (None, 0, 1, None),
        (False, 0, 1, None),
        ({}, 0, 1, None),
        (0, 0, 1, None),
        (None, 100, 99, "BOUNDED_BACKOFF_ACTIVE"),
        (None, 100, 100, None),
        ({"reason": "PERSISTED_TEST_CIRCUIT"}, 100, 1, "PERSISTED_TEST_CIRCUIT"),
    ],
)
def test_precheck_preserves_values_boundaries_and_priority(tmp_path, circuit, backoff, mono, reason):
    store = CanaryStore(tmp_path / "state.sqlite")
    store.set_value("circuit", circuit)
    store.set_value("next_allowed_mono", backoff)
    guard = BudgetGuard(store, policy())
    if reason:
        with pytest.raises(CircuitOpen, match=reason):
            guard.precheck(mono)
    else:
        guard.precheck(mono)


def test_expiry_index_preserves_exact_durable_charge_and_prune(tmp_path):
    store = CanaryStore(tmp_path / "state.sqlite")
    guard = BudgetGuard(store, policy())
    with store._connect() as db:
        # Candidate stays process-local. Its sequential speedup did not prove
        # reliable real-queue relief, so production bootstrap must not add it.
        assert not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='canary_budget_expiry'"
        ).fetchone()
        db.execute("CREATE INDEX canary_budget_expiry ON canary_budget(mono_ms)")
        db.executemany(
            "INSERT INTO canary_budget(scope,mono_ms,amount) VALUES (?,?,?)",
            [("EXPIRED", 1, 1), ("BOUNDARY", 2, 1), ("UNRELATED", 3, 1)],
        )
        plan = str(
            db.execute("EXPLAIN QUERY PLAN DELETE FROM canary_budget WHERE mono_ms<?", (2,)).fetchall()
        )
    assert "SEARCH" in plan and "canary_budget_expiry" in plan
    guard.data_message(3_600_002, 0)
    with store._connect() as db:
        rows = db.execute("SELECT scope,mono_ms,amount FROM canary_budget ORDER BY id").fetchall()
    assert rows == [("BOUNDARY", 2, 1), ("UNRELATED", 3, 1), ("WS_DATA", 3_600_002, 1)]
    assert store.get_value("budget_clock") == 3_600_002


def test_original_consumed_reconcile_never_authorizes_retry():
    from btc_quant_agent.platform.canary import session03 as s

    # Inspect only the accepted prospective capture; never open account/private keys.
    root = Path(__file__).resolve().parents[2]
    actual = root / "artifacts/live_public_canary_flex/session_03_clock_v2"
    # Source-only fixtures receive this path through explicit environment binding.
    import os

    capture = Path(os.environ.get("L4_ACCEPTED_SESSION03_CAPTURE", str(actual)))
    result = s.reconcile(capture)
    assert result == {"status": "CONSUMED_SEALED", "request_count": 3, "retry_authorized": False}
    assert json.loads((capture / "report.json").read_text())["stop_reason"] == "BACKPRESSURE_BLOCKED"


@pytest.mark.parametrize(
    "route,allowed",
    [
        ({"egress_mode": "DIRECT"}, False),
        ({"egress_mode": "CONTROLLED_EGRESS_PROXY", "tunnel_type": "SOCKS5"}, False),
        ({"egress_mode": "CONTROLLED_EGRESS_PROXY", "tunnel_type": "HTTP_CONNECT"}, True),
    ],
)
def test_native_active_transport_requires_approved_http_connect_without_network(scope, tmp_path, route, allowed):
    from btc_quant_agent.platform.canary.public_io import PublicTransport
    from btc_quant_agent.platform.canary.public_policy import PublicStop
    from .fixtures import Backend, Clock

    # Fabricated gate-only input, never an authorization or a real transport.
    scope.raw["activation_status"] = "FABRICATED_ROUTE_GATE_TEST_ONLY"
    clock = Clock()
    backend = Backend(scope, clock)
    backend.exposure = "PUBLIC_CANARY"
    backend.route_info = route
    telemetry = RuntimeTelemetry()
    transport = PublicTransport(
        scope,
        clock,
        BudgetGuard(CanaryStore(tmp_path / "state.sqlite"), scope.budget_policy()),
        enabled=True,
        backend=backend,
        telemetry=telemetry,
    )
    if allowed:
        assert transport.active() > 0
    else:
        with pytest.raises(PublicStop, match="APPROVED_HTTP_CONNECT_EGRESS_REQUIRED"):
            transport.active()
        assert telemetry.snapshot()["first_stop"]["stage"] == "transport.egress"
    assert not backend.calls and not backend.connections
