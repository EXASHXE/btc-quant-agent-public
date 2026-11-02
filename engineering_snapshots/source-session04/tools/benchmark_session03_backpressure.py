"""Replay unchanged sealed bytes offline; no transport, authority, or new acquisition."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import gzip
import json
from pathlib import Path
import sqlite3
import threading
import time
from types import SimpleNamespace
from queue import Queue, Empty, Full

from diagnose_session03_backpressure import CAPTURE, offline, offline_output


def queue_model(arrivals, service_ms, limit=128):
    """Deterministic FIFO capacity model, not measured native queue telemetry."""
    waiting: deque[float] = deque()
    finished = 0.0
    peak = 0
    for index, (arrived, duration) in enumerate(zip(arrivals, service_ms, strict=True)):
        while waiting and waiting[0] <= arrived:
            waiting.popleft()
        if len(waiting) >= limit:
            return {"status": "BACKPRESSURE_BLOCKED", "accepted": index, "peak_queue": peak}
        start = max(arrived, finished)
        if start > arrived:
            waiting.append(start)
        peak = max(peak, len(waiting))
        finished = start + duration
    return {"status": "DRAINED", "accepted": len(arrivals), "peak_queue": peak}


class ReplayClock:
    """Only original observed decision samples; never represents a new UTC observation."""

    def __init__(self, sample):
        self.observed = sample

    def sample(self):
        return self.observed

    def wall(self):
        return self.observed["wall_ms"]

    def mono(self):
        return self.observed["mono_after_ms"]


def benchmark(output, candidate=None):
    from btc_quant_agent.platform.canary.control import BudgetGuard, CanaryStore
    from btc_quant_agent.platform.canary.public_data import normalize
    from btc_quant_agent.platform.canary.public_journal import PublicJournal
    from btc_quant_agent.platform.canary.public_policy import load_scope
    from btc_quant_agent.platform.canary.public_runtime import PublicEngine
    from btc_quant_agent.platform.canary.storage import encode

    output = offline_output(output)
    output.mkdir(parents=True, exist_ok=False)
    marker = {"mode": "OFFLINE_REPLAY_ONLY_NOT_ACQUISITION", "origin": str(CAPTURE), "process_local_candidate": candidate,
              "native_requests": 0, "owner_authority": None, "qualification": False}
    (output / "OFFLINE_REPLAY_ONLY.json").write_text(json.dumps(marker, indent=2) + "\n")
    manifest = json.loads((CAPTURE / "replay_manifest.json").read_text())["manifest"]
    # Input preparation is excluded from throughput; all raw/normalized objects stay unchanged.
    chunks = []
    for raw_row, normal_row in zip(manifest[::2], manifest[1::2], strict=True):
        raw = json.loads(gzip.decompress((CAPTURE / "raw" / (raw_row["sha256"] + ".json.gz")).read_bytes()))
        normal = json.loads(gzip.decompress((CAPTURE / "normalized" / (normal_row["sha256"] + ".json.gz")).read_bytes()))
        chunks.append((raw_row, normal_row, raw["records"], normal["records"]))
    clock = ReplayClock(chunks[0][2][0]["decision_sample"])
    sql: Counter[str] = Counter()
    commit_seconds = 0.0

    class Connection(sqlite3.Connection):
        def __exit__(self, *args):
            nonlocal commit_seconds
            started = time.perf_counter()
            try:
                return super().__exit__(*args)
            finally:
                commit_seconds += time.perf_counter() - started
                sql["transaction_context_exits"] += 1

    class Store(CanaryStore):
        def _connect(self):
            connection = sqlite3.connect(self.db_path, timeout=30, factory=Connection)
            sql["connections"] += 1
            connection.set_trace_callback(lambda statement: sql.update([statement.split()[0].upper()]))
            return connection

    store = Store(output / "state.sqlite", clock_ms=clock.wall)
    guard = BudgetGuard(store, load_scope().budget_policy())
    journal = PublicJournal(output / "replayed_chunks", store, clock, exposure="PUBLIC_CANARY")
    engine = PublicEngine(SimpleNamespace(hash=chunks[0][2][0]["scope_hash"]), clock, store, journal, "PUBLIC_CANARY")
    engine.advisory_enabled = False
    stages: defaultdict[str, float] = defaultdict(float)
    services, arrivals = [], []
    total = 0
    sql.clear()
    started, cpu_started = time.perf_counter(), time.process_time()
    for raw_row, normal_row, raw_records, expected in chunks:
        results = []
        for record in raw_records:
            clock.observed = record["decision_sample"]
            arrivals.append(record["wire"]["receive_mono"])
            start = time.perf_counter()
            if record["wire"]["stream"]:
                guard.data_message(record["wire"]["receive_mono"], 0)
            stages["receiver_durable_budget_seconds"] += time.perf_counter() - start
            start = time.perf_counter()
            # Native ingest performs two normalization passes around availability capture.
            # Both use the unchanged original record here; no new clocks are manufactured.
            normalize(record)
            result = normalize(record)
            elapsed = time.perf_counter() - start
            stages["two_pass_normalizer_seconds"] += elapsed
            services.append(elapsed * 1000)
            results.append(result)
        assert encode(results) == encode(expected), "NORMALIZED_PARITY_FAILED"
        engine.pending = list(zip(raw_records, results, strict=True))
        start = time.perf_counter()
        engine.flush()
        elapsed = time.perf_counter() - start
        stages["durable_pair_apply_checkpoint_seconds"] += elapsed
        services[-1] += elapsed * 1000
        written = journal.rows()[-2:]
        assert [row[1] for row in written] == [raw_row["sha256"], normal_row["sha256"]], "CHUNK_BYTE_PARITY_FAILED"
        total += len(raw_records)
    seconds, cpu = time.perf_counter() - started, time.process_time() - cpu_started
    arrival_zero = arrivals[0]
    arrivals = [float(a - arrival_zero) for a in arrivals]
    models = {
        "original_observed_receive_profile": queue_model(arrivals, services),
        "observed_receive_profile_2x": queue_model([a / 2 for a in arrivals], services),
        "observed_receive_profile_4x": queue_model([a / 4 for a in arrivals], services),
        "sustained_199_per_second": queue_model([i * 1000 / 199 for i in range(total)], services),
        "instant_130": queue_model([0.0] * 130, services[:130]),
        "one_2_second_consumer_stall": queue_model(arrivals, [s + (2000 if i == 1024 else 0) for i, s in enumerate(services)]),
    }
    result = {
        **marker, "records": total, "pairs": len(chunks), "wall_seconds": seconds, "cpu_seconds": cpu,
        "records_per_second": total / seconds, "stages": dict(stages),
        "sqlite": {"statements": dict(sql), "context_exit_commit_seconds": commit_seconds,
                   "journal_mode": "delete", "synchronous": "SQLite default FULL; unchanged"},
        "raw_and_normalized_compressed_byte_parity": True, "applied_records": engine.counts["received"],
        "pending_after_flush": len(engine.pending), "queue_limit": 128,
        "queue_models_not_native_telemetry": models,
        "limits": "No network/receiver scheduling; original chunk boundaries; two unchanged-record normalization passes; original decision samples; isolated local replay throughput is not native capacity proof.",
    }
    (output / "benchmark.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (output / "service_fixture.json").write_text(json.dumps({"arrival_ms": arrivals, "consumer_service_ms": services}) + "\n")
    print(json.dumps(result, indent=2))


def concurrent_tail(output, profile, candidate=None):
    """Real 128-slot queue, durable guard and consumer; unchanged observed tail records."""
    from btc_quant_agent.platform.canary.control import BudgetGuard, CanaryStore, CircuitOpen
    from btc_quant_agent.platform.canary.public_data import normalize
    from btc_quant_agent.platform.canary.public_journal import PublicJournal
    from btc_quant_agent.platform.canary.public_policy import load_scope
    from btc_quant_agent.platform.canary.public_runtime import PublicEngine
    from btc_quant_agent.platform.canary.storage import encode

    output = offline_output(output)
    output.mkdir(parents=True, exist_ok=False)
    marker = {"mode": "OFFLINE_CONCURRENT_REPLAY_NOT_ACQUISITION", "profile": profile, "process_local_candidate": candidate,
              "native_requests": 0, "qualification": False, "origin": str(CAPTURE)}
    (output / "OFFLINE_REPLAY_ONLY.json").write_text(json.dumps(marker, indent=2) + "\n")
    rows = json.loads((CAPTURE / "replay_manifest.json").read_text())["manifest"]
    raw_rows = [row for row in rows if row["kind"] == "raw"]
    selected = raw_rows[:3] + raw_rows[-8:]
    jobs = []
    for row in selected:
        value = json.loads(gzip.decompress((CAPTURE / "raw" / (row["sha256"] + ".json.gz")).read_bytes()))
        for index, record in enumerate(value["records"]):
            jobs.append((record, index == len(value["records"]) - 1))
    clock = ReplayClock(jobs[0][0]["decision_sample"])
    store = CanaryStore(output / "state.sqlite", clock_ms=clock.wall)
    guard = BudgetGuard(store, load_scope().budget_policy())
    journal = PublicJournal(output / "replayed_chunks", store, clock, exposure="PUBLIC_CANARY")
    engine = PublicEngine(SimpleNamespace(hash=jobs[0][0]["scope_hash"]), clock, store, journal, "PUBLIC_CANARY")
    engine.advisory_enabled = False

    class MeasuredQueue(Queue):
        peak = 0

        def _put(self, item):
            super()._put(item)
            self.peak = max(self.peak, len(self.queue))

    queue = MeasuredQueue(maxsize=128)
    done = threading.Event()
    metrics: Counter[str] = Counter()
    normalizer_seconds = 0.0
    terminal = {"reason": "DRAINED"}
    first_tail = jobs[3][0]["wire"]["receive_mono"]
    started = time.perf_counter()

    def produce():
        try:
            for record, boundary in jobs:
                due = 0 if profile == "burst-tail" else max(0, record["wire"]["receive_mono"] - first_tail) / 1000
                wait = started + due - time.perf_counter()
                if wait > 0:
                    time.sleep(wait)
                if record["wire"]["stream"]:
                    guard.data_message(record["wire"]["receive_mono"], queue.qsize())
                queue.put_nowait((record, boundary))
                metrics["accepted"] += 1
        except (CircuitOpen, Full) as exc:
            terminal["reason"] = "BACKPRESSURE_BLOCKED" if isinstance(exc, Full) else str(exc)
        except BaseException as exc:
            terminal["reason"] = "PRODUCER_ERROR:" + repr(exc)
        finally:
            done.set()

    producer = threading.Thread(target=produce, name="offline-sealed-replay-producer")
    producer.start()
    try:
        while not done.is_set() or not queue.empty():
            if profile == "stall-tail" and metrics["processed"] == 3:
                time.sleep(2)
                metrics["injected_consumer_stall_ms"] = 2000
            try:
                record, boundary = queue.get(timeout=.05)
            except Empty:
                continue
            clock.observed = record["decision_sample"]
            start = time.perf_counter()
            normalize(record)
            result = normalize(record)
            normalizer_seconds += time.perf_counter() - start
            engine.pending.append((record, result))
            metrics["max_engine_pending"] = max(metrics["max_engine_pending"], len(engine.pending))
            if boundary:
                engine.flush()
            metrics["processed"] += 1
        engine.flush()
    finally:
        producer.join(timeout=15)
    assert not producer.is_alive() and metrics["processed"] == metrics["accepted"]
    assert engine.counts["received"] == metrics["processed"] and not engine.pending
    replay = journal.audit_replay(normalize)
    assert replay["status"] == "PARITY_VERIFIED"
    output_records = []
    for row in journal.rows():
        if row[3] == "raw":
            output_records.extend(journal.read(row)["records"])
    assert encode(output_records) == encode([job[0] for job in jobs[:metrics["accepted"]]])
    result = {**marker, **dict(metrics), "normalizer_seconds": normalizer_seconds,
              "stop_reason": terminal["reason"], "queue_limit": 128,
              "peak_queue": queue.peak, "fixture_records": len(jobs), "queue_drained": queue.empty(),
              "replay_pairs": replay["checked_pairs"], "unpaired_raw_chunks": replay["unpaired_raw_chunks"],
              "unchanged_raw_record_order_and_content": True, "normalization_replay_parity": True,
              "elapsed_seconds_including_replay_audit": time.perf_counter() - started,
              "budget_clock": "Original observed receive monotonic values, unchanged; accelerated replay is not a new native rate observation.",
              "circuit": store.get_value("circuit")}
    (output / "benchmark.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    offline()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", choices=["scalar-fastpath"], help="Process-local experiment; production source is never patched")
    parser.add_argument("--profile", choices=["observed-tail", "burst-tail", "stall-tail"])
    args = parser.parse_args()
    if args.candidate:
        from btc_quant_agent.platform import core

        original = core.primitive

        def scalar_fastpath(value):
            if value is None or type(value) in (str, int, float, bool):
                return value
            return original(value)

        core.primitive = scalar_fastpath
        print("PROCESS_LOCAL_EXPERIMENT_ONLY: scalar-fastpath; no runtime files changed", flush=True)
    if args.profile:
        concurrent_tail(args.output, args.profile, args.candidate)
    else:
        benchmark(args.output, args.candidate)
