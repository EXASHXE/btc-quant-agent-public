"""Bounded offline profiling of the accepted Session03 prefix; never native I/O.

Run with baseline_source/src first on PYTHONPATH for the immutable old code.
Candidates are process-local until a separately tested source patch promotes one.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import resource
import statistics
import time
from types import SimpleNamespace
from typing import Any, cast

from diagnose_session03_backpressure import CAPTURE, ROOT, offline
from benchmark_session03_backpressure import ReplayClock

PHASE = ROOT / "artifacts/source_runtime_backpressure_remediation_02"


def telemetry_module():
    spec = importlib.util.spec_from_file_location(
        "offline_runtime_metrics", ROOT / "src/btc_quant_agent/platform/canary/telemetry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def output_path(value):
    path = Path(value).resolve()
    if not (path.is_relative_to(PHASE) or path.is_relative_to(Path("/tmp"))):
        raise ValueError("OFFLINE_PHASE_OR_TMP_OUTPUT_REQUIRED")
    if path.is_relative_to(CAPTURE.resolve()) or CAPTURE.resolve().is_relative_to(path):
        raise ValueError("ORIGINAL_CAPTURE_IMMUTABLE")
    path.mkdir(parents=True, exist_ok=False)
    return path


def quantiles(values):
    if not values:
        return {"count": 0, "p50": None, "p95": None, "p99": None, "max": None}
    ordered = sorted(values)

    def at(p):
        import math

        return ordered[math.ceil(len(ordered) * p) - 1]

    return {
        "count": len(values),
        "p50": at(0.5),
        "p95": at(0.95),
        "p99": at(0.99),
        "max": ordered[-1],
        "mean": statistics.mean(values),
    }


def inputs():
    manifest = json.loads((CAPTURE / "replay_manifest.json").read_text())["manifest"]
    chunks = []
    for raw, normal in zip(manifest[::2], manifest[1::2], strict=True):
        assert raw["kind"] == "raw" and normal["kind"] == "normalized"
        original = (CAPTURE / "raw" / (raw["sha256"] + ".json.gz")).read_bytes()
        expected = (CAPTURE / "normalized" / (normal["sha256"] + ".json.gz")).read_bytes()
        assert hashlib.sha256(original).hexdigest() == raw["sha256"]
        assert hashlib.sha256(expected).hexdigest() == normal["sha256"]
        chunks.append(
            (
                raw,
                normal,
                json.loads(gzip.decompress(original))["records"],
                json.loads(gzip.decompress(expected))["records"],
            )
        )
    assert sum(len(c[2]) for c in chunks) == 9156 and len(chunks) == 147
    return chunks


def setup(out, chunks, *, candidate="none", enabled=True):
    from btc_quant_agent.platform.canary.control import BudgetGuard, CanaryStore, CircuitOpen
    from btc_quant_agent.platform.canary.public_journal import PublicJournal
    from btc_quant_agent.platform.canary.public_runtime import PublicEngine
    from btc_quant_agent.platform.canary.policy import Policy

    metrics = telemetry_module()
    telemetry = metrics.RuntimeTelemetry(enabled=enabled)
    clock = ReplayClock(chunks[0][2][0]["decision_sample"])
    store = CanaryStore(out / "state.sqlite", clock_ms=clock.wall)
    raw_connect = store._connect

    def connect():
        started = time.perf_counter_ns()
        db = raw_connect()
        telemetry.observe("sqlite.connect", time.perf_counter_ns() - started)
        telemetry.count("sqlite_connections")
        return metrics.TimedConnection(db, telemetry) if enabled else db

    setattr(store, "_connect", connect)
    grant = json.loads((CAPTURE / "source_grant.json").read_text())
    policy = Policy.model_validate(
        {
            "endpoint_ids": tuple(grant["endpoint_ids"]),
            "endpoint_calls_per_minute": grant["endpoint_calls_per_minute"],
            "max_connections": 1,
            "max_subscriptions": 3,
            "max_pending_records": 128,
            "max_messages_per_second": 200,
        }
    )
    modern = "telemetry" in inspect.signature(BudgetGuard.__init__).parameters
    guard = BudgetGuard(store, policy, telemetry=telemetry) if modern else BudgetGuard(store, policy)
    if not modern:
        for name, stage in [("precheck", "budget.precheck"), ("charge", "budget.charge")]:
            method = getattr(guard, name)

            def measured(*args, _method=method, _stage=stage, **kwargs):
                with telemetry.measure(_stage):
                    return _method(*args, **kwargs)

            setattr(guard, name, measured)
    if candidate in ("mono-index", "both"):
        with store._connect() as db:
            db.execute("CREATE INDEX IF NOT EXISTS canary_budget_expiry ON canary_budget(mono_ms)")
    if candidate in ("combined-precheck", "both"):

        def combined(mono):
            with telemetry.measure("budget.precheck"):
                with store._connect() as db:
                    values = dict(
                        db.execute(
                            "SELECT key,value FROM canary_values WHERE key IN ('circuit','next_allowed_mono')"
                        )
                    )
                circuit = json.loads(values["circuit"]) if "circuit" in values else None
                if circuit:
                    raise CircuitOpen(circuit["reason"])
                if mono < json.loads(values.get("next_allowed_mono", "0")):
                    raise CircuitOpen("BOUNDED_BACKOFF_ACTIVE")

        setattr(guard, "precheck", combined)
    journal_mod = cast(
        Any, __import__("btc_quant_agent.platform.canary.public_journal", fromlist=["PublicJournal"])
    )
    modern_journal = "telemetry" in inspect.signature(PublicJournal.__init__).parameters
    journal = (
        PublicJournal(out / "replayed_chunks", store, clock, exposure="PUBLIC_CANARY", telemetry=telemetry)
        if modern_journal
        else PublicJournal(out / "replayed_chunks", store, clock, exposure="PUBLIC_CANARY")
    )
    if not modern_journal:
        old_encode = journal_mod.encode
        old_gzip = journal_mod.gzip.compress
        old_fsync = journal_mod.os.fsync

        def encode(*args, **kwargs):
            with telemetry.measure("journal.encode"):
                return old_encode(*args, **kwargs)

        def compress(*args, **kwargs):
            with telemetry.measure("journal.gzip"):
                return old_gzip(*args, **kwargs)

        def fsync(fd):
            import os
            import stat

            stage = "journal.fsync_directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "journal.fsync_file"
            with telemetry.measure(stage):
                return old_fsync(fd)

        journal_mod.encode = encode
        journal_mod.gzip.compress = compress
        journal_mod.os.fsync = fsync
        old_write = journal.write

        def write(kind, records, **kwargs):
            with telemetry.measure("journal.raw_commit" if kind == "raw" else "journal.normalized_commit"):
                return old_write(kind, records, **kwargs)

        setattr(journal, "write", write)
    scope = SimpleNamespace(hash=chunks[0][2][0]["scope_hash"])
    if "telemetry" in inspect.signature(PublicEngine.__init__).parameters:
        engine = PublicEngine(scope, clock, store, journal, "PUBLIC_CANARY", telemetry=telemetry)
    else:
        engine = PublicEngine(scope, clock, store, journal, "PUBLIC_CANARY")
        old_apply = engine.apply
        old_checkpoint = engine.memory.checkpoint

        def apply(*args, **kwargs):
            with telemetry.measure("engine.apply"):
                return old_apply(*args, **kwargs)

        def checkpoint():
            with telemetry.measure("engine.checkpoint"):
                return old_checkpoint()

        setattr(engine, "apply", apply)
        setattr(engine.memory, "checkpoint", checkpoint)
    engine.advisory_enabled = False
    return telemetry, clock, store, guard, journal, engine


def sequential(output, *, candidate="none", enabled=True):
    from btc_quant_agent.platform.canary.public_data import normalize
    from btc_quant_agent.platform.canary.storage import encode

    out = output_path(output)
    chunks = inputs()
    marker = {
        "mode": "OFFLINE_REPLAY_ONLY_NOT_ACQUISITION",
        "native_requests": 0,
        "qualification": False,
        "origin": str(CAPTURE),
        "candidate_process_local": candidate,
        "telemetry_enabled": enabled,
    }
    (out / "OFFLINE_REPLAY_ONLY.json").write_text(json.dumps(marker, indent=2) + "\n")
    telemetry, clock, store, guard, journal, engine = setup(out, chunks, candidate=candidate, enabled=enabled)
    with store._connect() as db:
        plan = [
            tuple(row)
            for row in db.execute("EXPLAIN QUERY PLAN DELETE FROM canary_budget WHERE mono_ms<?", (0,))
        ]
        journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]
        synchronous = db.execute("PRAGMA synchronous").fetchone()[0]
    services = []
    arrivals = []
    latencies: list[float] = []
    total = 0
    stages = {"budget_ns": 0, "normalize_ns": 0, "pair_apply_checkpoint_ns": 0}
    started = time.perf_counter_ns()
    cpu_started = time.process_time_ns()
    for raw_row, normal_row, records, expected in chunks:
        results = []
        accepted = []
        for record in records:
            begin = time.perf_counter_ns()
            accepted.append(begin)
            clock.observed = record["decision_sample"]
            arrivals.append(record["wire"]["receive_mono"])
            if record["wire"]["stream"]:
                guard.data_message(record["wire"]["receive_mono"], 0)
            after_budget = time.perf_counter_ns()
            stages["budget_ns"] += after_budget - begin
            with telemetry.measure("engine.normalize_first"):
                normalize(record)
            with telemetry.measure("engine.normalize_second"):
                value = normalize(record)
            after_norm = time.perf_counter_ns()
            stages["normalize_ns"] += after_norm - after_budget
            services.append((after_norm - after_budget) / 1e6)
            results.append(value)
        assert encode(results) == encode(expected), "NORMALIZED_PARITY_FAILED"
        engine.pending = list(zip(records, results, strict=True))
        before_flush = time.perf_counter_ns()
        engine.flush()
        after_flush = time.perf_counter_ns()
        stages["pair_apply_checkpoint_ns"] += after_flush - before_flush
        services[-1] += (after_flush - before_flush) / 1e6
        latencies.extend((after_flush - when) / 1e6 for when in accepted)
        assert [row[1] for row in journal.rows()[-2:]] == [raw_row["sha256"], normal_row["sha256"]], (
            "COMPRESSED_CHUNK_PARITY_FAILED"
        )
        total += len(records)
    wall = time.perf_counter_ns() - started
    cpu = time.process_time_ns() - cpu_started
    assert total == 9156 and engine.counts["received"] == 9156 and not engine.pending
    snapshot = telemetry.snapshot()
    result = {
        **marker,
        "records": total,
        "pairs": 147,
        "compressed_chunks_byte_identical": 294,
        "wall_seconds": wall / 1e9,
        "cpu_seconds": cpu / 1e9,
        "records_per_second": total / (wall / 1e9),
        "stages_ns": stages,
        "telemetry": snapshot,
        "sequential_ingest_to_checkpoint_ms": quantiles(latencies),
        "budget_delete_query_plan": plan,
        "sqlite_journal_mode": journal_mode,
        "sqlite_synchronous": synchronous,
        "peak_process_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "source_order_and_provenance_unchanged": True,
        "unapplied_records": 0,
        "limits": "Sequential wall performance includes durable budget+two normalization passes+byte-identical paired journals+application/checkpoint. Not native capacity or historical stall attribution.",
    }
    (out / "benchmark.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (out / "service_fixture.json").write_text(
        json.dumps({"arrival_ms": [x - arrivals[0] for x in arrivals], "consumer_service_ms": services})
        + "\n"
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "mode",
                    "candidate_process_local",
                    "records_per_second",
                    "wall_seconds",
                    "cpu_seconds",
                    "compressed_chunks_byte_identical",
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
        "--candidate", choices=["none", "mono-index", "combined-precheck", "both"], default="none"
    )
    parser.add_argument("--telemetry-off", action="store_true")
    args = parser.parse_args()
    sequential(args.output, candidate=args.candidate, enabled=not args.telemetry_off)
