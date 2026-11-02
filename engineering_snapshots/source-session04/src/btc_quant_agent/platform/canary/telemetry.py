"""Bounded out-of-band runtime timings. No source timestamps or evidence bytes change.

Client elapsed times include scheduler pauses. SQLite commit elapsed is NOT an
attribution of SQLite's internal fsync. No metric performs telemetry I/O.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import deque
from contextlib import contextmanager
from functools import wraps
import math
from queue import Queue, Full
import threading
import time

VERSION = "L4_RUNTIME_TIMINGS_V1"
BOUNDS = (0, *(m * 10**e for e in range(3, 11) for m in (1, 2, 5)), 10**12)
STAGES = (
    "ws.recv_call",
    "ws.capture",
    "ws.parse_validate",
    "ws.guard_lock_wait",
    "ws.guard",
    "queue.enqueue_call",
    "queue.residence",
    "queue.dequeue_call",
    "queue.consumer_service",
    "budget.precheck",
    "budget.charge",
    "sqlite.connect",
    "sqlite.begin_immediate",
    "sqlite.query",
    "sqlite.prune",
    "sqlite.context_commit",
    "sqlite.context_rollback",
    "sqlite.context_no_transaction",
    "sqlite.explicit_commit",
    "journal.encode",
    "journal.gzip",
    "journal.fsync_file",
    "journal.fsync_directory",
    "journal.raw_commit",
    "journal.normalized_commit",
    "engine.ingest",
    "engine.normalize_first",
    "engine.normalize_second",
    "engine.flush",
    "engine.apply",
    "engine.checkpoint",
    "record.ingest_to_checkpoint",
    "record.receive_to_checkpoint",
    "record.source_receive_to_decision",
)
COUNTERS = (
    "observations",
    "invalid_observations",
    "unknown_metric",
    "enqueue_attempts",
    "enqueued",
    "enqueue_full",
    "dequeued",
    "budget_ws_charged",
    "sqlite_connections",
    "sqlite_statements",
    "sqlite_commits",
    "sqlite_rollbacks",
    "ingest_started",
    "ingest_accepted",
    "durable_records",
    "timing_missing",
    "timing_identity_mismatch",
    "measurement_calls",
)


class Histogram:
    def __init__(self, bounds=BOUNDS):
        self.bounds = bounds
        self.counts = [0] * (len(bounds) + 1)
        self.count = self.total = 0
        self.minimum = self.maximum = None

    def add(self, value):
        self.counts[bisect_left(self.bounds, value)] += 1
        self.count += 1
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def quantile(self, p):
        if not self.count:
            return None
        rank = math.ceil(self.count * p)
        seen = 0
        for index, count in enumerate(self.counts):
            seen += count
            if seen >= rank:
                return self.bounds[index] if index < len(self.bounds) else self.maximum
        raise AssertionError("HISTOGRAM_COUNT_MISMATCH")

    def snapshot(self):
        return {
            "count": self.count,
            "sum": self.total,
            "min": self.minimum,
            "max": self.maximum,
            "p50_upper": self.quantile(0.50),
            "p95_upper": self.quantile(0.95),
            "p99_upper": self.quantile(0.99),
            "buckets": list(self.counts),
        }


class RuntimeTelemetry:
    def __init__(self, *, enabled=True):
        self.enabled = enabled
        self.lock = threading.Lock()
        self.histograms = {name: Histogram() for name in STAGES}
        self.pending_histogram = Histogram(tuple(range(129)))
        self.counters = dict.fromkeys(COUNTERS, 0)
        self.high_water = 0
        self.overhead_ns = 0
        self.first_stop = None

    def count(self, name, amount=1):
        if not self.enabled:
            return
        started = time.perf_counter_ns()
        with self.lock:
            if name in self.counters:
                self.counters[name] += amount
            else:
                self.counters["unknown_metric"] += 1
            self.overhead_ns += time.perf_counter_ns() - started

    def observe(self, name, elapsed_ns):
        if not self.enabled:
            return
        started = time.perf_counter_ns()
        with self.lock:
            if type(elapsed_ns) is not int or elapsed_ns < 0:
                self.counters["invalid_observations"] += 1
            elif name not in self.histograms:
                self.counters["unknown_metric"] += 1
            else:
                self.histograms[name].add(elapsed_ns)
                self.counters["observations"] += 1
            self.overhead_ns += time.perf_counter_ns() - started

    def pending(self, value):
        if not self.enabled:
            return
        with self.lock:
            if type(value) is int and 0 <= value <= 128:
                self.pending_histogram.add(value)
            else:
                self.counters["invalid_observations"] += 1

    def highwater(self, value):
        if self.enabled:
            with self.lock:
                self.high_water = max(self.high_water, value)

    def stop(self, stage, reason, pending=None):
        if self.enabled:
            with self.lock:
                if self.first_stop is None:
                    self.first_stop = {
                        "stage": stage,
                        "reason": reason,
                        "pending": pending,
                        "observed_perf_ns": time.perf_counter_ns(),
                    }

    @contextmanager
    def measure(self, name):
        if not self.enabled:
            yield
            return
        self.count("measurement_calls")
        started = time.perf_counter_ns()
        try:
            yield
        finally:
            self.observe(name, time.perf_counter_ns() - started)

    def snapshot(self):
        with self.lock:
            return {
                "version": VERSION,
                "enabled": self.enabled,
                "duration_unit": "nanoseconds",
                "quantile_method": "nearest-rank fixed-bucket upper bound; min/max are exact",
                "bucket_upper_bounds_ns": list(BOUNDS),
                "durations": {name: value.snapshot() for name, value in self.histograms.items()},
                "counters": dict(self.counters),
                "pending_at_guard": self.pending_histogram.snapshot(),
                "queue_high_water": self.high_water,
                "first_stop": self.first_stop,
                "measured_observation_update_elapsed_ns": self.overhead_ns,
                "memory_bound": {
                    "duration_metrics": len(STAGES),
                    "counter_names": len(COUNTERS),
                    "samples_stored": 0,
                    "queue_timing_slots_max": 128,
                    "engine_timing_slots_max": 64,
                },
                "limitations": "Spans overlap; update elapsed excludes timer/context overhead. No syscall, kernel-buffer or external scheduler attribution.",
            }


NULL = RuntimeTelemetry(enabled=False)


def timed(stage):
    def decorate(method):
        @wraps(method)
        def call(self, *args, **kwargs):
            with self.telemetry.measure(stage):
                return method(self, *args, **kwargs)

        return call

    return decorate


class TimedConnection:
    """Transparent timing proxy; raw connection context still owns commit/rollback."""

    def __init__(self, connection, telemetry):
        self.connection, self.telemetry = connection, telemetry

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        active = self.connection.in_transaction
        label = (
            "sqlite.context_commit"
            if active and args[0] is None
            else ("sqlite.context_rollback" if active else "sqlite.context_no_transaction")
        )
        with self.telemetry.measure(label):
            result = self.connection.__exit__(*args)
        if active:
            self.telemetry.count("sqlite_commits" if args[0] is None else "sqlite_rollbacks")
        return result

    def execute(self, sql, *args, **kwargs):
        text = sql.lstrip().upper()
        name = (
            "sqlite.begin_immediate"
            if text.startswith("BEGIN IMMEDIATE")
            else ("sqlite.prune" if text.startswith("DELETE FROM CANARY_BUDGET") else "sqlite.query")
        )
        self.telemetry.count("sqlite_statements")
        with self.telemetry.measure(name):
            return self.connection.execute(sql, *args, **kwargs)

    def executemany(self, *args, **kwargs):
        self.telemetry.count("sqlite_statements")
        with self.telemetry.measure("sqlite.query"):
            return self.connection.executemany(*args, **kwargs)

    def commit(self):
        with self.telemetry.measure("sqlite.explicit_commit"):
            result = self.connection.commit()
        self.telemetry.count("sqlite_commits")
        return result


class TimedQueue(Queue):
    """Same 128-slot FIFO plus at most 128 timestamp tuples, never payload buffering."""

    def __init__(self, telemetry, *, maxsize=128):
        super().__init__(maxsize=maxsize)
        self.telemetry = telemetry
        self.stamps: deque[tuple[int | None, int]] = deque()
        self.local = threading.local()

    def put_wire(self, item, received_ns):
        self.local.received_ns = received_ns
        try:
            self.put_nowait(item)
        finally:
            self.local.received_ns = None

    def put(self, item, block=True, timeout=None):
        self.telemetry.count("enqueue_attempts")
        try:
            with self.telemetry.measure("queue.enqueue_call"):
                return super().put(item, block=block, timeout=timeout)
        except Full:
            self.telemetry.count("enqueue_full")
            self.telemetry.stop("queue.enqueue", "QUEUE_FULL", self.qsize())
            raise

    def _put(self, item):
        super()._put(item)
        self.stamps.append((getattr(self.local, "received_ns", None), time.perf_counter_ns()))
        self.telemetry.count("enqueued")
        self.telemetry.highwater(len(self.queue))

    def _get(self):
        item = super()._get()
        received, enqueued = self.stamps.popleft()
        dequeued = time.perf_counter_ns()
        self.local.last = (
            id(item),
            {"received_ns": received, "enqueued_ns": enqueued, "dequeued_ns": dequeued},
        )
        self.telemetry.count("dequeued")
        self.telemetry.observe("queue.residence", dequeued - enqueued)
        return item

    def take_timing(self, item):
        value = getattr(self.local, "last", None)
        self.local.last = None
        if value and value[0] == id(item):
            return value[1]
        self.telemetry.count("timing_identity_mismatch")
        return None
