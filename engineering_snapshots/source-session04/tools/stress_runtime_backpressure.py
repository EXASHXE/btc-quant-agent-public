"""Real bounded FIFO/durable SQLite stress using the accepted 9156-record prefix.

Original record clocks never change. Guard timestamps use a separately labeled
offline execution monotonic domain. No network/client or acquisition authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from queue import Empty, Full
import threading
import time

from benchmark_runtime_backpressure import inputs, output_path, setup, quantiles, telemetry_module
from diagnose_session03_backpressure import offline, CAPTURE


def stress(output, profile):
    from btc_quant_agent.platform.canary.control import CircuitOpen
    from btc_quant_agent.platform.canary.public_data import normalize
    from btc_quant_agent.platform.canary.storage import encode

    out = output_path(output)
    chunks = inputs()
    jobs = [
        (record, index == len(records) - 1)
        for _, _, records, _ in chunks
        for index, record in enumerate(records)
    ]
    assert len(jobs) == 9156
    assert all(not row[0]["wire"]["stream"] for row in jobs[:3])
    assert all(row[0]["wire"]["stream"] for row in jobs[3:])
    telemetry, clock, store, guard, journal, engine = setup(out, chunks)
    queue = telemetry_module().TimedQueue(telemetry, maxsize=128)
    marker = {
        "mode": "OFFLINE_ACCEPTED_PREFIX_STRESS_NOT_ACQUISITION",
        "profile": profile,
        "native_requests": 0,
        "qualification": False,
        "original_records": 9156,
        "origin": str(CAPTURE),
        "harness_version": 2,
        "startup_contract": "Three original REST records applied synchronously before starting WS producer, as in run_public",
    }
    (out / "OFFLINE_REPLAY_ONLY.json").write_text(json.dumps(marker, indent=2) + "\n")
    done = threading.Event()
    terminal = {"reason": "DRAINED", "queue_depth_at_stop": None}
    count = {"accepted": 0, "processed": 0, "ws_charged": 0}
    injections = []
    lag: list[float] = []
    latencies: list[float] = []
    arrivals: list[int] = []
    pending_starts = []
    injected = False
    first = jobs[3][0]["wire"]["receive_mono"]
    factor = {"observed": 1, "2x": 2, "4x": 4}.get(profile, 4)
    whole_started = time.perf_counter_ns()
    ws_index = 0
    if profile == "disk-500":
        original = journal._sync

        def slow_sync(fd, stage):
            nonlocal injected
            if not injected and count["processed"] >= 64:
                injected = True
                begin = time.perf_counter_ns()
                time.sleep(0.5)
                telemetry.observe(stage, time.perf_counter_ns() - begin)
                injections.append(
                    {
                        "kind": "SIMULATED_DISK_PAUSE_WHILE_WRITER_TRANSACTION_OPEN",
                        "begin_perf_ns": begin,
                        "elapsed_ms": (time.perf_counter_ns() - begin) / 1e6,
                    }
                )
            return original(fd, stage)

        journal._sync = slow_sync
    if profile == "commit-250":
        original = store._connect

        class Delayed:
            def __init__(self, db):
                self.db = db

            def __getattr__(self, name):
                return getattr(self.db, name)

            def __enter__(self):
                self.db.__enter__()
                return self

            def __exit__(self, *args):
                nonlocal injected
                if not injected and count["ws_charged"] >= 100 and self.db.in_transaction:
                    injected = True
                    begin = time.perf_counter_ns()
                    time.sleep(0.25)
                    injections.append(
                        {
                            "kind": "SIMULATED_CONTEXT_EXIT_DELAY",
                            "begin_perf_ns": begin,
                            "elapsed_ms": (time.perf_counter_ns() - begin) / 1e6,
                        }
                    )
                return self.db.__exit__(*args)

        def delayed_connection():
            db = original()
            # Delay inside the existing timing proxy so context-exit elapsed
            # includes this explicitly labeled injected pause exactly once.
            db.connection = Delayed(db.connection)
            return db

        store._connect = delayed_connection

    def produce():
        nonlocal ws_index
        try:
            for record, boundary in jobs[3:]:
                if record["wire"]["stream"]:
                    if profile in ("150", "199"):
                        target = ws_index * 1e9 / int(profile)
                    elif profile == "burst150":
                        cycle, point = divmod(ws_index, 150)
                        target = cycle * 1e9 + (point * 5e6 if point < 100 else 5e8 + (point - 100) * 1e7)
                    else:
                        target = max(0, record["wire"]["receive_mono"] - first) * 1e6 / factor
                    ws_index += 1
                    remaining = (started + target - time.perf_counter_ns()) / 1e9
                    if remaining > 0:
                        time.sleep(remaining)
                    received = time.perf_counter_ns()
                    lag.append(max(0, (received - started - target) / 1e6))
                    execution_mono = 1_000_000_000 + (received - started) // 1_000_000
                    guard.data_message(execution_mono, queue.qsize())
                    count["ws_charged"] += 1
                    arrivals.append(received)
                else:
                    received = time.perf_counter_ns()
                queue.put_wire((record, boundary), received)
                count["accepted"] += 1
        except (CircuitOpen, Full) as exc:
            terminal["reason"] = "BACKPRESSURE_BLOCKED" if isinstance(exc, Full) else str(exc)
            terminal["queue_depth_at_stop"] = queue.qsize()
            telemetry.stop("stress.producer", terminal["reason"], queue.qsize())
        except BaseException as exc:
            terminal["reason"] = "UNEXPECTED_PRODUCER_FAILURE:" + type(exc).__name__
            terminal["queue_depth_at_stop"] = queue.qsize()
        finally:
            done.set()

    producer = threading.Thread(target=produce, name="offline-accepted-source-prefix")
    # Native run_public ingests metadata and both clock probes BEFORE opening
    # the WS. Do not invent startup overlap and attribute its pressure to WS.
    for record, boundary in jobs[:3]:
        clock.observed = record["decision_sample"]
        begin = time.perf_counter_ns()
        with telemetry.measure("engine.normalize_first"):
            normalize(record)
        with telemetry.measure("engine.normalize_second"):
            result = normalize(record)
        engine.pending.append((record, result))
        if hasattr(engine, "pending_timings"):
            engine.pending_timings.append((begin, None))
        pending_starts.append(begin)
        count["accepted"] += 1
        count["processed"] += 1
        if boundary:
            engine.flush()
            ended = time.perf_counter_ns()
            latencies.extend((ended - x) / 1e6 for x in pending_starts)
            pending_starts = []
    assert not engine.pending and not pending_starts and queue.empty()
    started = time.perf_counter_ns()
    producer.start()
    try:
        while not done.is_set() or not queue.empty():
            if profile in ("pause-200", "pause-2000") and count["processed"] == 3 and not injected:
                injected = True
                pause = 0.2 if profile == "pause-200" else 2
                begin = time.perf_counter_ns()
                time.sleep(pause)
                injections.append(
                    {
                        "kind": "SIMULATED_CONSUMER_PAUSE_NO_SQLITE_LOCK",
                        "begin_perf_ns": begin,
                        "elapsed_ms": (time.perf_counter_ns() - begin) / 1e6,
                    }
                )
            try:
                item = queue.get(timeout=0.05)
            except Empty:
                continue
            timing = queue.take_timing(item)
            record, boundary = item
            if profile == "cpu-250" and count["processed"] == 3 and not injected:
                injected = True
                begin = time.perf_counter_ns()
                value = 0
                while time.perf_counter_ns() - begin < 250_000_000:
                    value = (value + 1) % 104729
                injections.append(
                    {
                        "kind": "SIMULATED_BOUNDED_CPU_CONTENTION",
                        "begin_perf_ns": begin,
                        "elapsed_ms": (time.perf_counter_ns() - begin) / 1e6,
                    }
                )
            if profile == "lock-500" and count["processed"] == 64 and not injected:
                import sqlite3

                injected = True
                db = sqlite3.connect(out / "state.sqlite", check_same_thread=False)
                db.execute("BEGIN IMMEDIATE")
                begin = time.perf_counter_ns()

                def release():
                    time.sleep(0.5)
                    db.rollback()
                    db.close()

                releaser = threading.Thread(target=release)
                releaser.start()
                injections.append(
                    {
                        "kind": "SIMULATED_EXTERNAL_SQLITE_WRITER_LOCK",
                        "requested_ms": 500,
                        "begin_perf_ns": begin,
                    }
                )
            clock.observed = record["decision_sample"]
            begin = time.perf_counter_ns()
            with telemetry.measure("engine.normalize_first"):
                normalize(record)
            with telemetry.measure("engine.normalize_second"):
                result = normalize(record)
            engine.pending.append((record, result))
            if hasattr(engine, "pending_timings"):
                engine.pending_timings.append((begin, timing))
            pending_starts.append(timing["received_ns"])
            count["processed"] += 1
            if boundary:
                engine.flush()
                ended = time.perf_counter_ns()
                latencies.extend((ended - x) / 1e6 for x in pending_starts)
                pending_starts = []
            telemetry.observe("queue.consumer_service", time.perf_counter_ns() - timing["dequeued_ns"])
        engine.flush()
        ended = time.perf_counter_ns()
        latencies.extend((ended - x) / 1e6 for x in pending_starts)
    finally:
        producer.join(timeout=35)
    assert not producer.is_alive(), "OFFLINE_PRODUCER_DID_NOT_STOP"
    assert count["accepted"] == count["processed"] == engine.counts["received"]
    assert not engine.pending and queue.empty()
    replay = journal.audit_replay(normalize)
    assert replay["status"] == "PARITY_VERIFIED" and replay["unpaired_raw_chunks"] == 0
    output_records = [
        record for row in journal.rows() if row[3] == "raw" for record in journal.read(row)["records"]
    ]
    assert encode(output_records) == encode([r for r, _ in jobs[: count["accepted"]]])
    elapsed = (time.perf_counter_ns() - whole_started) / 1e9
    measured_rate = (len(arrivals) - 1) * 1e9 / (arrivals[-1] - arrivals[0]) if len(arrivals) > 1 else None
    snapshot = telemetry.snapshot()
    result = {
        **marker,
        **count,
        "stop_reason": terminal["reason"],
        "queue_depth_at_stop": terminal["queue_depth_at_stop"],
        "queue_high_water": snapshot["queue_high_water"],
        "retained_queue_after_finalization": queue.qsize(),
        "queue_limit": 128,
        "ws_message_cap_per_s": 200,
        "elapsed_seconds_including_final_audit": elapsed,
        "actual_receiver_guarded_rate_per_second": measured_rate,
        "producer_schedule_lag_ms": quantiles(lag),
        "received_to_checkpoint_ms": quantiles(latencies),
        "injections": injections,
        "injections_precede_first_stop": all(
            row["begin_perf_ns"] < snapshot["first_stop"]["observed_perf_ns"]
            for row in injections
        ) if snapshot["first_stop"] else None,
        "admitted_prefix_order_and_content_unchanged": True,
        "unapplied_records": 0,
        "replay_pairs": replay["checked_pairs"],
        "unpaired_raw_chunks": 0,
        "telemetry": snapshot,
        "requested_profile_sustained_in_realtime": bool(lag) and max(lag) < 250,
        "budget_clock_domain": "Separately labeled OFFLINE execution monotonic; original E/T/receiver/decision samples never changed",
        "circuit": store.get_value("circuit"),
        "qualification_claim": False,
        "history_attribution": "Simulation only, not original native stall attribution",
    }
    if terminal["reason"] == "DRAINED" and lag and max(lag) >= 250:
        result["performance_outcome"] = (
            "DRAINED_WITH_PRODUCER_SCHEDULE_LAG_NOT_PROOF_OF_SUSTAINED_TARGET_RATE"
        )
    elif terminal["reason"] == "DRAINED":
        result["performance_outcome"] = "OFFLINE_PROFILE_DRAINED"
    else:
        result["performance_outcome"] = "TERMINAL_HARD_STOP_RETAINED"
    (out / "stress.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "profile",
                    "accepted",
                    "processed",
                    "stop_reason",
                    "queue_high_water",
                    "actual_receiver_guarded_rate_per_second",
                    "requested_profile_sustained_in_realtime",
                    "performance_outcome",
                ]
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    offline()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile",
        choices=[
            "observed",
            "2x",
            "4x",
            "199",
            "150",
            "burst150",
            "pause-200",
            "pause-2000",
            "commit-250",
            "lock-500",
            "disk-500",
            "cpu-250",
        ],
        required=True,
    )
    args = parser.parse_args()
    stress(args.output, args.profile)
