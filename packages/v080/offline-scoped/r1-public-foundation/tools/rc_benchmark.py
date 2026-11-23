"""Predeclared finite low-rate workload; neither native capacity nor economic evidence."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import threading
import time

from btc_quant_agent.platform.core import fingerprint
from btc_quant_agent.platform.rc_fixture import DECISION, SEED, TRIGGER, fixture
from btc_quant_agent.platform.rc_models import frozen_contract
from btc_quant_agent.platform.rc_source import SYMBOLS, admit_stream
from btc_quant_agent.platform.rc_store import RCStore
from btc_quant_agent.platform.reporting import source_identity


def quantiles(values):
    ordered = sorted(values)
    def q(fraction):
        return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]
    return {"n": len(ordered), "p50": q(0.50), "p95": q(0.95), "p99": q(0.99), "max": ordered[-1]}


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    spec = frozen_contract()["workload_predeclaration"]
    rows = fixture()
    warmup = tuple(r for r in rows if r.bar.end_ms != TRIGGER)
    closes = tuple(r for r in rows if r.bar.end_ms == TRIGGER)
    assert len(closes) == 9 and SEED == spec["seed"]
    timings, restart_times, admissions, details = [], [], [], []
    for iteration in range(30):
        path = output / f"run-{iteration:02d}.sqlite"
        if path.exists():
            raise ValueError("BENCHMARK_OUTPUT_ALREADY_EXISTS")
        store = RCStore(path)
        warm_count = admit_stream(store, warmup)
        locked, release = threading.Event(), threading.Event()
        thread = timer = None
        if iteration == 0:
            def contender():
                with store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    locked.set()
                    release.wait(2)
            thread = threading.Thread(target=contender)
            thread.start()
            assert locked.wait(2)
            timer = threading.Timer(0.03, release.set)
            timer.start()
        started = time.perf_counter_ns()
        close_count = admit_stream(store, closes, burst=9)
        digests = []
        for symbol in SYMBOLS:
            d = store.compile(symbol, TRIGGER, DECISION)
            digests.append(store.commit(d))
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        if thread:
            thread.join(2)
            timer.join(2)
        started = time.perf_counter_ns()
        restarted = RCStore(path, readonly=True)
        counts = restarted.verify()
        replay = [fingerprint(d.model_dump(mode="json")) for d in restarted.decisions()]
        restart_times.append((time.perf_counter_ns() - started) / 1_000_000)
        duplicate_admissions = admit_stream(store, rows)
        assert duplicate_admissions == 0 and replay == digests
        for d in store.decisions():
            assert store.commit(d) == fingerprint(d.model_dump(mode="json"))
        assert counts["receipts"] == len(rows) and counts["decisions"] == 3
        timings.append(elapsed)
        admissions.append(warm_count + close_count)
        details.append({"iteration": iteration, "processing_ms": elapsed, "counts": counts,
                        "admitted": warm_count + close_count, "duplicate_admissions": duplicate_admissions,
                        "coincident_close_bars": close_count, "replay_digest_parity": replay == digests,
                        "sqlite_contention_injected": iteration == 0})
    measured = quantiles(timings)
    modeled_close = quantiles([120 + t for t in timings])
    restart = quantiles(restart_times)
    thresholds = spec["thresholds_ms"]
    passed = (measured["p99"] <= thresholds["available_to_decision_p99"]
              and measured["max"] <= thresholds["available_to_decision_max"]
              and modeled_close["max"] <= thresholds["close_to_decision_max"]
              and restart["max"] <= thresholds["restart_max"]
              and sum(admissions) == 30 * len(rows))
    result = {"schema": "PROGRAM_A_LOW_RATE_PERFORMANCE_V1", "assessment": "PASS" if passed else "PARTIAL",
              "exposure": "SYNTHETIC", "native_qualification": False,
              "workload_predeclared_in": "A1_FROZEN_INTEGRATION_CONTRACT.json",
              "workload": spec, "producer_sha256": source_identity(),
              "fixture_rows_per_run": len(rows), "warmup_rows": len(warmup), "coincident_closes": len(closes),
              "runs": details, "expected_admissions": 30 * len(rows), "actual_admissions": sum(admissions),
              "admitted_loss": 0, "duplicate_decisions": 0, "replay_digest_parity": True,
              "processing_and_available_to_decision_ms": measured,
              "modeled_close_to_decision_ms": modeled_close,
              "restart_verify_ms": restart,
              "declared_simulator_clock_close_to_decision_ms": quantiles([1000.0] * 30),
              "declared_simulator_clock_available_to_decision_ms": quantiles([880.0] * 30),
              "measurement": "perf_counter_ns covers final 9 source admissions, both S1 compilation and durable commits for all 3 symbols, including contention on run0. Modeled close latency adds declared 120ms synthetic availability delay. Warmup generation is excluded and separately counted. Simulator event/decision clocks remain fixed, not native timestamps.",
              "limits": ["Finite local workload; no sustained native throughput claim", "No M1B150/s requalification",
                         "No seven-day source availability or economic inference", "Platform-specific directory fsync exercised on Linux only"],
              "thresholds_ms": thresholds}
    (output / "performance.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({k: result[k] for k in ["assessment", "actual_admissions", "admitted_loss",
                                           "processing_and_available_to_decision_ms", "modeled_close_to_decision_ms", "restart_verify_ms"]}))
    raise SystemExit(0 if result["assessment"] == "PASS" else 1)
