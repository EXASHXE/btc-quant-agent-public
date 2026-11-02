"""Predeclared diagnostic gate; never full Source/Shadow qualification.

This pure checker also runs in the independently authenticated LONG verifier.
Missing, malformed and non-native evidence cannot pass.
"""

from __future__ import annotations

SESSION = "L4-NATIVE-RUNTIME-V1-SESSION04"
SPEC = "L4_SESSION04_NATIVE_ACCEPTANCE_V1"
LATENCY_NS = {"p50_upper": 500_000_000, "p95_upper": 1_000_000_000, "p99_upper": 2_000_000_000}
CLEAN_STOPS = {"AUTHORIZED_UTC_END", "GRANT_WINDOW_EXPIRED", "SESSION04_WINDOW_EXPIRED"}


def evaluate(report):
    reasons = []

    def need(ok, reason):
        if not ok:
            reasons.append(reason)

    def integer(value):
        return type(value) is int and value >= 0

    try:
        need(report["session_id"] == SESSION and report["exposure"] == "PUBLIC_CANARY", "NATIVE_ORIGIN_REQUIRED")
        need(report["stop_reason"] in CLEAN_STOPS, "UNCLEAN_STOP")
        need(report["sockets_closed"] is True and report["receiver_threads_stopped"] is True
             and report["safe_terminal_evidence"] is True, "UNSAFE_TERMINAL")
        need(report["finalization_errors"] == [] and report["uncommitted_or_unapplied_frames"] == 0
             and report["retained_queue_depth_at_finalization"] == 0
             and report["durably_charged_ws_records_not_enqueued"] == 0, "ADMITTED_OR_DURABLE_LOSS")
        replay = report["replay"]
        need(replay["status"] == "PARITY_VERIFIED" and replay["unpaired_raw_chunks"] == 0
             and replay["expired_chunks"] == 0 and replay["checked_pairs"] > 0, "REPLAY_INCOMPLETE")
        elapsed = report["operator_monotonic_elapsed_ms"]
        expected = report["authorized_end_exclusive_ms"] - report["started_wall_ms"]
        need(integer(elapsed) and 25000 <= expected <= 180000 and expected - 1000 <= elapsed <= expected + 1000,
             "INCOMPLETE_INCLUSIVE_CAPTURE")
        timing = report["runtime_telemetry"]
        need(timing["version"] == "L4_RUNTIME_TIMINGS_V1" and timing["enabled"] is True
             and timing["duration_unit"] == "nanoseconds", "TIMING_SCHEMA_INVALID")
        need(integer(timing["queue_high_water"]) and timing["queue_high_water"] <= 96,
             "QUEUE_MARGIN_BELOW_32")
        need(timing["first_stop"] is None or timing["first_stop"].get("reason") in CLEAN_STOPS, "STICKY_RUNTIME_FAULT")
        counts = timing["counters"]
        for name in ("enqueue_full", "timing_missing", "timing_identity_mismatch", "invalid_observations", "unknown_metric"):
            need(counts[name] == 0, "COUNTER_FAULT:" + name)
        need(integer(counts["ingest_started"]) and counts["ingest_started"] > 3
             and counts["ingest_started"] == counts["ingest_accepted"] == counts["durable_records"], "DURABLE_COUNT_MISMATCH")
        transport = report["transport_metrics"]
        need(type(transport["rest_requests"]) is int and 3 <= transport["rest_requests"] <= 4,
             "REST_ATTEMPT_CONTRACT")
        need(integer(transport["ws_frames"]) and transport["ws_frames"] > 0
             and transport["ws_frames"] == transport["ws_data_enqueued"] == counts["enqueued"] == counts["dequeued"],
             "WS_ADMITTED_LOSS")
        need(transport["ws_connections"] == 1 and transport["reconnects"] == 0, "CONNECTION_CONTINUITY_FAILED")
        for stage in ("record.source_receive_to_decision", "record.receive_to_checkpoint"):
            h = timing["durations"][stage]
            expected_count = counts["durable_records"] if stage.endswith("decision") else counts["dequeued"]
            need(integer(h["count"]) and h["count"] == expected_count, "LATENCY_COVERAGE:" + stage)
            for q, limit in LATENCY_NS.items():
                need(integer(h[q]) and h[q] <= limit, "LATENCY_BOUND:" + stage + ":" + q)
        clock = report["clock_validation_evidence"]
        estimate = report["model"]["clock_estimate"]
        probes = estimate["probes"]
        need(clock["clock_fault"] is None and not report["model"]["clock_epoch_failure"]
             and clock["independent_probes"] >= 2 and len(probes) >= 2
             and estimate["uncertainty_ms"] <= 100, "CLOCK_UNQUALIFIED")
        need(0 <= report["stopped_wall_ms"] - max(p["available"]["wall_ms"] for p in probes) <= 300000,
             "CLOCK_STALE")
        need(all(type(clock["distinct_qualified_quotes"].get(s)) is int
                 and clock["distinct_qualified_quotes"][s] > 0 for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")),
             "THREE_SYMBOL_ADMITTED_BBO_REQUIRED")
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        reasons.append("MISSING_OR_MALFORMED_EVIDENCE")
    return {"version": SPEC, "passed": not reasons,
            "completion": "DIAGNOSTIC_ONLY" if not reasons else "PARTIAL_OR_UNSAFE",
            "reasons": reasons, "source_qualified": False, "shadow_advisory_qualified": False,
            "long_acquisition_authorized": False}
