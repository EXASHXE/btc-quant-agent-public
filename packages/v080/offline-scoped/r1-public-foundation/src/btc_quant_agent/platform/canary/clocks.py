"""Native source clocks and conservative uncertainty, separate from measured elapsed time."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class Capture:
    request_wall_ms: int
    request_mono_ms: int
    first_wall_ms: int
    first_mono_ms: int
    complete_wall_ms: int
    complete_mono_ms: int
    available_wall_ms: int
    available_mono_ms: int
    decision_wall_ms: int
    decision_mono_ms: int
    commit_wall_ms: int
    commit_mono_ms: int
    sync_evidence: str = "FABRICATED_OFFLINE_CLOCK"

    def reason(self, max_wall_drift_ms: int = 50) -> str | None:
        wall = (
            self.request_wall_ms,
            self.first_wall_ms,
            self.complete_wall_ms,
            self.available_wall_ms,
            self.decision_wall_ms,
            self.commit_wall_ms,
        )
        mono = (
            self.request_mono_ms,
            self.first_mono_ms,
            self.complete_mono_ms,
            self.available_mono_ms,
            self.decision_mono_ms,
            self.commit_mono_ms,
        )
        if any(type(v) is not int or v < 0 for v in (*wall, *mono)):
            return "LOCAL_CLOCK_TYPE_INVALID"
        if any(b < a for values in (wall, mono) for a, b in zip(values, values[1:])):
            return "LOCAL_CLOCK_REGRESSION"
        if not self.sync_evidence:
            return "CLOCK_SYNC_EVIDENCE_MISSING"
        if any(abs((w - wall[0]) - (m - mono[0])) > max_wall_drift_ms for w, m in zip(wall, mono)):
            return "LOCAL_WALL_CLOCK_JUMP"
        return None

    def elapsed(self) -> dict:
        return {
            "measurement": "measured_local_elapsed",
            "request_to_first_ms": self.first_mono_ms - self.request_mono_ms,
            "request_to_complete_ms": self.complete_mono_ms - self.request_mono_ms,
            "parse_ms": self.available_mono_ms - self.complete_mono_ms,
            "available_to_decision_ms": self.decision_mono_ms - self.available_mono_ms,
            "decision_to_commit_ms": self.commit_mono_ms - self.decision_mono_ms,
        }


@dataclass(frozen=True)
class Probe:
    request_wall_ms: int
    receive_wall_ms: int
    request_mono_ms: int
    receive_mono_ms: int
    server_time_ms: int
    server_quantization_ms: int = 1
    exposure: str = "SYNTHETIC"


@dataclass(frozen=True)
class ClockEstimate:
    offset_low_ms: float
    offset_high_ms: float
    rtt_ms: tuple[int, ...]
    available_wall_ms: int
    available_mono_ms: int
    max_probe_age_ms: int = 300_000
    exposure: str = "SYNTHETIC"

    @property
    def uncertainty_ms(self) -> float:
        return (self.offset_high_ms - self.offset_low_ms) / 2

    @property
    def offset_estimate_ms(self) -> float:
        return (self.offset_high_ms + self.offset_low_ms) / 2

    def interval(self, native_time_ms: int, receive_wall_ms: int) -> tuple[float, float]:
        return (
            receive_wall_ms - native_time_ms + self.offset_low_ms,
            receive_wall_ms - native_time_ms + self.offset_high_ms,
        )


def estimate_clock(probes: tuple[Probe, ...], *, max_wall_drift_ms=50, allowed_exposure="SYNTHETIC") -> ClockEstimate:
    if not probes or len(probes) > 16:
        raise ValueError("BOUNDED_CLOCK_PROBE_COUNT_REQUIRED")
    intervals, rtts = [], []
    for p in probes:
        if p.exposure != allowed_exposure or allowed_exposure not in ("SYNTHETIC", "PUBLIC_CANARY"):
            raise ValueError("REAL_PROBE_REQUIRES_OWNER_GRANT_AND_UNIMPLEMENTED_TRANSPORT")
        if any(
            type(v) is not int or v < 0
            for v in (
                p.request_wall_ms,
                p.receive_wall_ms,
                p.request_mono_ms,
                p.receive_mono_ms,
                p.server_time_ms,
                p.server_quantization_ms,
            )
        ):
            raise ValueError("PROBE_CLOCK_TYPE_INVALID")
        rtt = p.receive_mono_ms - p.request_mono_ms
        if rtt < 0 or abs(p.receive_wall_ms - p.request_wall_ms - rtt) > max_wall_drift_ms:
            raise ValueError("PROBE_WALL_CLOCK_DRIFT")
        intervals.append(
            (
                p.server_time_ms - p.receive_wall_ms - p.server_quantization_ms,
                p.server_time_ms - p.request_wall_ms + p.server_quantization_ms,
            )
        )
        rtts.append(rtt)
    # Use the envelope, not a selected fastest/favorable probe. Jitter widens uncertainty.
    return ClockEstimate(
        min(v[0] for v in intervals),
        max(v[1] for v in intervals),
        tuple(rtts),
        max(p.receive_wall_ms for p in probes),
        max(p.receive_mono_ms for p in probes),
        exposure=allowed_exposure,
    )


@dataclass(frozen=True)
class NativeClock:
    field: str | None
    value_ms: int | None
    semantics: str
    documentation_ref: str
    transaction_ms: int | None = None
    publish_ms: int | None = None


def qualify_clock(
    native: NativeClock,
    capture: Capture,
    estimate: ClockEstimate | None,
    lease_ms: int,
    *,
    max_uncertainty_ms=100,
) -> dict:
    result = {
        "native": native,
        "local": capture,
        "elapsed": capture.elapsed(),
        "event_to_receive_estimate_bounds_ms": None,
        "event_age_bounds_ms": None,
        "one_way_latency_proven": False,
        "source_clock_qualified": False,
    }
    reason = capture.reason()
    if reason is None and (
        native.value_ms is None
        or type(native.value_ms) is not int
        or native.value_ms <= 0
        or native.semantics == "UNKNOWN"
        or not native.documentation_ref
    ):
        reason = "NATIVE_TIMESTAMP_OR_SEMANTICS_UNKNOWN"
    if reason is None and estimate is None:
        reason = "CLOCK_UNCERTAINTY_UNKNOWN"
    if reason is None and estimate is not None:
        if (
            not all(isfinite(v) for v in (estimate.offset_low_ms, estimate.offset_high_ms))
            or not estimate.rtt_ms
            or any(type(v) is not int or v < 0 for v in estimate.rtt_ms)
            or estimate.exposure != "SYNTHETIC"
            or estimate.max_probe_age_ms <= 0
            or estimate.offset_high_ms < estimate.offset_low_ms
            or estimate.available_wall_ms > capture.decision_wall_ms
            or estimate.available_mono_ms > capture.decision_mono_ms
        ):
            reason = "CLOCK_ESTIMATE_INVALID_OR_FUTURE"
        elif capture.decision_mono_ms - estimate.available_mono_ms > estimate.max_probe_age_ms:
            reason = "CLOCK_ESTIMATE_STALE"
        elif estimate.uncertainty_ms > min(max_uncertainty_ms, lease_ms):
            reason = "CLOCK_UNCERTAINTY_EXCEEDS_LEASE"
        else:
            assert native.value_ms is not None  # Validated above; explicit narrowing for mypy.
            delay = estimate.interval(native.value_ms, capture.complete_wall_ms)
            age = estimate.interval(native.value_ms, capture.decision_wall_ms)
            result.update(
                event_to_receive_estimate_bounds_ms=delay,
                event_age_bounds_ms=age,
                offset_estimate_ms=estimate.offset_estimate_ms,
                clock_uncertainty_ms=estimate.uncertainty_ms,
                jitter_rtt_range_ms=max(estimate.rtt_ms) - min(estimate.rtt_ms),
            )
            if delay[0] < 0 or age[0] < 0:
                reason = "SOURCE_TIME_POTENTIALLY_FUTURE"
            elif age[1] > lease_ms:
                reason = "SOURCE_AGE_UPPER_BOUND_EXCEEDED"
            elif native.value_ms > capture.complete_wall_ms:
                reason = "L23_NATIVE_CLOCK_ORDER_UNSUPPORTED"
    result.update(reason=reason, source_clock_qualified=reason is None)
    return result
