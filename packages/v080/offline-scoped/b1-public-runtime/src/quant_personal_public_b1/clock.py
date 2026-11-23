"""Bracket exchange time with request/receipt observations and project by monotonic time."""

import time
from dataclasses import dataclass
from typing import Protocol

from .policy import Policy, require


@dataclass(frozen=True)
class Sample:
    wall_ms: int
    mono_ms: int


class Clock(Protocol):
    def sample(self) -> Sample: ...


class SystemClock:
    def sample(self) -> Sample:
        return Sample(time.time_ns() // 1_000_000, time.monotonic_ns() // 1_000_000)


@dataclass(frozen=True)
class VenueTime:
    anchor: Sample
    lower_ms: int
    upper_ms: int

    @classmethod
    def bracket(cls, sent: Sample, received: Sample, venue_ms: int, policy: Policy) -> "VenueTime":
        check_elapsed(sent, received, policy)
        # Millisecond sampling/quantization at both ends gets a conservative margin.
        elapsed = received.mono_ms - sent.mono_ms
        result = cls(received, venue_ms - 1, venue_ms + elapsed + 2)
        result.check_width(policy)
        return result

    def projected(self, point: Sample, policy: Policy) -> "VenueTime":
        elapsed = point.mono_ms - self.anchor.mono_ms
        drift = (abs(elapsed) * policy.max_clock_drift_ppm + 999_999) // 1_000_000
        return VenueTime(point, self.lower_ms + elapsed - drift, self.upper_ms + elapsed + drift)

    def reconcile(self, other: "VenueTime", policy: Policy) -> "VenueTime":
        check_elapsed(self.anchor, other.anchor, policy)
        projected = self.projected(other.anchor, policy)
        lo, hi = max(projected.lower_ms, other.lower_ms), min(projected.upper_ms, other.upper_ms)
        require(lo <= hi, "CLOCK_BRACKETS_DISAGREE")
        return VenueTime(other.anchor, lo, hi)

    def check_width(self, policy: Policy) -> None:
        require(self.upper_ms - self.lower_ms <= 2 * policy.max_clock_uncertainty_ms, "CLOCK_UNCERTAIN")

    def evidence(self) -> dict[str, int]:
        return {
            "wall_ms": self.anchor.wall_ms, "monotonic_ms": self.anchor.mono_ms,
            "venue_lower_ms": self.lower_ms, "venue_upper_ms": self.upper_ms,
            "wall_offset_lower_ms": self.lower_ms - self.anchor.wall_ms,
            "wall_offset_upper_ms": self.upper_ms - self.anchor.wall_ms,
            "uncertainty_ms": (self.upper_ms - self.lower_ms + 1) // 2,
        }


def check_elapsed(sent: Sample, received: Sample, policy: Policy) -> None:
    elapsed = received.mono_ms - sent.mono_ms
    require(elapsed >= 0, "MONOTONIC_CLOCK_REGRESSED")
    require(abs(received.wall_ms - sent.wall_ms - elapsed) <= policy.max_wall_step_ms, "WALL_CLOCK_DISCONTINUITY")
