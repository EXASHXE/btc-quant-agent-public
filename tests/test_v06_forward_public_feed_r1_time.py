"""Tests for TimeAuthority Point-in-Time semantics, clock rollback detection, and latencies."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from market_data.forward_public_feed_r1.time_authority import TimeAuthority


def test_time_authority_initialization() -> None:
    ta = TimeAuthority(connection_epoch="test-epoch-1")
    assert ta.connection_epoch == "test-epoch-1"
    assert ta.last_observed_wall_ms is None
    assert ta.last_observed_monotonic_ns is None
    assert ta.clock_uncertain_count == 0


def test_capture_ingress_normal_advance() -> None:
    ta = TimeAuthority(connection_epoch="test-epoch-1")
    t1 = ta.capture_ingress(override_wall_ms=1000, override_monotonic_ns=1_000_000_000)
    assert t1.quality == "VERIFIED"
    assert t1.observed_wall_utc_ms == 1000
    assert t1.observed_monotonic_ns == 1_000_000_000
    assert t1.available_at_ms >= 1000

    t2 = ta.capture_ingress(override_wall_ms=1100, override_monotonic_ns=1_100_000_000)
    assert t2.quality == "VERIFIED"
    assert t2.observed_wall_utc_ms == 1100
    assert t2.observed_monotonic_ns == 1_100_000_000


def test_clock_rollback_detection() -> None:
    ta = TimeAuthority(connection_epoch="test-epoch-1")
    ta.capture_ingress(override_wall_ms=5000, override_monotonic_ns=5_000_000_000)

    # Monotonic clock advances, but wall clock steps backward (rollback)
    t_rollback = ta.capture_ingress(override_wall_ms=4500, override_monotonic_ns=5_100_000_000)
    assert t_rollback.quality == "DEGRADED"
    assert "CLOCK_UNCERTAIN" in t_rollback.reason_codes
    assert ta.clock_uncertain_count == 1


def test_monotonic_regression_detection() -> None:
    ta = TimeAuthority(connection_epoch="test-epoch-1")
    ta.capture_ingress(override_wall_ms=1000, override_monotonic_ns=2_000_000_000)

    # Monotonic clock goes backwards (extreme system failure)
    t_bad_mono = ta.capture_ingress(override_wall_ms=1010, override_monotonic_ns=1_900_000_000)
    assert t_bad_mono.quality == "DEGRADED"
    assert "MONOTONIC_REGRESSION" in t_bad_mono.reason_codes
    assert ta.monotonic_violation_count == 1


def test_extreme_clock_divergence_detection() -> None:
    ta = TimeAuthority(connection_epoch="test-epoch-1", max_clock_divergence_ms=2_000)
    ta.capture_ingress(override_wall_ms=1000, override_monotonic_ns=1_000_000_000)

    # Monotonic advances 10ms, but wall jumps 10,000ms
    t_jump = ta.capture_ingress(override_wall_ms=11000, override_monotonic_ns=1_010_000_000)
    assert t_jump.quality == "DEGRADED"
    assert "CLOCK_UNCERTAIN" in t_jump.reason_codes
    assert ta.clock_uncertain_count == 1


def test_available_at_never_earlier_than_wall() -> None:
    ta = TimeAuthority()
    ts = ta.capture_ingress()
    assert ts.available_at_ms >= ts.observed_wall_utc_ms


def test_epoch_isolation() -> None:
    ta1 = TimeAuthority()
    ta2 = TimeAuthority()
    assert ta1.connection_epoch != ta2.connection_epoch


def test_latency_percentiles_calculation() -> None:
    ta = TimeAuthority()
    # Add samples: 10, 20, 30, ..., 100
    for latency in range(10, 101, 10):
        ta.record_transit_latency(provider_event_ms=1000, observed_wall_ms=1000 + latency)

    pct = ta.get_latency_percentiles()
    assert pct["sample_count"] == 10
    assert pct["p50_ms"] == 55.0
    assert pct["p90_ms"] == 91.0
    assert pct["p99_ms"] > 95.0


def test_empty_latency_percentiles() -> None:
    ta = TimeAuthority()
    pct = ta.get_latency_percentiles()
    assert pct["sample_count"] == 0
    assert pct["p50_ms"] == 0.0


def test_dropped_ingress_counter() -> None:
    ta = TimeAuthority()
    assert ta.dropped_ingress_count == 0
    ta.increment_dropped_ingress(5)
    assert ta.dropped_ingress_count == 5


def test_time_authority_diagnostics() -> None:
    ta = TimeAuthority(connection_epoch="diag-epoch")
    ta.increment_dropped_ingress(2)
    diag = ta.get_diagnostics()
    assert diag["connection_epoch"] == "diag-epoch"
    assert diag["dropped_ingress_count"] == 2
    assert diag["clock_status"] == "CLOCK_SYNCHRONIZED"

    # Trigger clock uncertain
    ta.capture_ingress(override_wall_ms=5000, override_monotonic_ns=5_000_000_000)
    ta.capture_ingress(override_wall_ms=4000, override_monotonic_ns=5_100_000_000)
    diag2 = ta.get_diagnostics()
    assert diag2["clock_status"] == "CLOCK_UNCERTAIN"
