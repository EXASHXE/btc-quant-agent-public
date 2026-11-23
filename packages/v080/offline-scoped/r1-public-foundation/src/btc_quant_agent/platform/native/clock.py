"""Actual paired startup/refresh probes and sticky monotonic clock epoch checks."""

from __future__ import annotations

import time

from .contract import digest, require


class Clock:
    def __init__(self):
        self.anchor = None
        self.last = None
        self.failed = None
        self.estimate = None
        self.probes = []
        self.failure_evidence = None

    def pair(self):
        before = time.monotonic_ns() // 1000000
        wall = time.time_ns() // 1000000
        after = time.monotonic_ns() // 1000000
        return {"wall_ms": wall, "mono_before_ms": before, "mono_after_ms": after}

    def sample(self):
        s = self.pair()
        if self.anchor is None:
            self.anchor = s
        a = self.anchor
        low = s["wall_ms"] - s["mono_after_ms"] - (a["wall_ms"] - a["mono_before_ms"]) - 1
        high = s["wall_ms"] - s["mono_before_ms"] - (a["wall_ms"] - a["mono_after_ms"]) + 1
        reason = None
        proven_step = low > 50 or high < -50
        span = s["mono_after_ms"] - s["mono_before_ms"]
        if proven_step:
            reason = "CLOCK_50MS_DISCONTINUITY"
        elif span > 5 or span < 0:
            reason = "CLOCK_BRACKET_UNCERTAIN"
        elif self.last is not None and s["mono_before_ms"] < self.last:
            reason = "MONOTONIC_REGRESSION"
        elif low < -50 or high > 50:
            reason = "CLOCK_50MS_DISCONTINUITY_UNCERTAIN"
        if reason and self.failed is None:
            self.failure_evidence = {
                "sample": dict(s),
                "anchor": dict(a),
                "offset_change_low_ms": low,
                "offset_change_high_ms": high,
                "sample_span_ms": span,
                "proven_wall_step": proven_step,
                "reason": reason,
                "threshold_ms": 50,
            }
        self.last = s["mono_after_ms"]
        self.failed = self.failed or reason
        require(self.failed is None, self.failed)
        return s

    def refresh(self, transport, grant, journal):
        retained: list[dict] = []
        for _ in range(2):
            # Strict temporal ordering and independent requests, never choose best RTT.
            time.sleep(0.002)
            request = self.sample()
            server, wire = transport.probe()
            receive = self.sample()
            row = {
                "request": request,
                "receive": receive,
                "server_ms": server,
                "wire_sha256": digest(wire),
                "wire_record": wire,
                "scope_sha256": digest(grant.model_dump(mode="json")),
            }
            require(
                not retained
                or (
                    request["mono_before_ms"] > retained[-1]["receive"]["mono_after_ms"]
                    and server > retained[-1]["server_ms"]
                ),
                "CLOCK_PROBES_NOT_INDEPENDENT",
            )
            retained.append(row)
        low = min(p["server_ms"] - p["receive"]["mono_after_ms"] - 1 for p in retained)
        high = max(p["server_ms"] - p["request"]["mono_before_ms"] + 1 for p in retained)
        require((high - low) / 2 <= 100, "CLOCK_UNCERTAINTY_ABOVE_100MS")
        for p in retained:
            require(abs(p["receive"]["wall_ms"] - p["server_ms"]) <= 100, "LOCAL_UTC_UNVERIFIED")
        self.estimate = {
            "low": low,
            "high": high,
            "uncertainty_ms": (high - low) / 2,
            "at_mono_ms": retained[-1]["receive"]["mono_after_ms"],
            "scope_sha256": digest(grant.model_dump(mode="json")),
            "probes": retained,
        }
        self.probes.extend(retained)
        with journal.db() as db:
            journal.append(db, grant.session_id, "CLOCK_PROBES", self.estimate)
        return self.estimate

    def check(self, grant, require_probes=True):
        sample = self.sample()
        require(grant.start_ms <= sample["wall_ms"] < grant.end_ms, "WINDOW_END_OR_NOT_OPEN")
        if require_probes:
            require(self.estimate is not None, "CLOCK_PROBES_MISSING")
            assert self.estimate is not None
            age = sample["mono_after_ms"] - self.estimate["at_mono_ms"]
            require(0 <= age <= 300000, "CLOCK_PROBES_STALE")
            require(self.estimate["uncertainty_ms"] <= 100, "CLOCK_UNCERTAINTY_ABOVE_100MS")
        return sample

    def event(self, native_ms, receive):
        require(self.estimate is not None, "CLOCK_PROBES_MISSING")
        # Bound native event in the same monotonic domain; never rebase source UTC.
        assert self.estimate is not None
        lower = receive["mono_before_ms"] + self.estimate["low"]
        upper = receive["mono_after_ms"] + self.estimate["high"]
        require(native_ms <= upper and lower - native_ms <= 300000, "NATIVE_EVENT_STALE_OR_FUTURE")
