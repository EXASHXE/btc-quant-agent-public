"""V2 native clock proofs. Raw exchange and receiver clocks are never rebased.

All admission arithmetic uses bounded native-minus-monotonic offsets. A local
wall clock is an auditable UTC reading, not a substitute for the exchange clock.
This module has no I/O and does not authorize native transport.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from ..core import DataProvenance, fingerprint, primitive

VERSION = "L4_CLOCK_DOMAIN_V2"
WALL_STEP_MS = 50  # Existing hard threshold; not a tunable source-admission parameter.
MAX_SAMPLE_SPAN_MS = 5
MAX_PROBE_AGE_MS = 300_000
MAX_UNCERTAINTY_MS = 100
_decision: ContextVar[tuple[dict, str] | None] = ContextVar("l4_clock_decision", default=None)


def sample_reason(s: dict | None) -> str | None:
    if not isinstance(s, dict):
        return "CLOCK_BRACKET_MISSING"
    keys = (
        "wall_ms",
        "mono_before_ms",
        "mono_after_ms",
        "anchor_wall_ms",
        "anchor_before_ms",
        "anchor_after_ms",
    )
    if any(type(s.get(k)) is not int or s[k] <= 0 for k in keys):
        return "CLOCK_SAMPLE_INVALID"
    if not isinstance(s.get("epoch_id"), str) or not s["epoch_id"]:
        return "CLOCK_EPOCH_MISSING"
    if type(s.get("epoch_valid")) is not bool:
        return "CLOCK_EPOCH_INVALID"
    if type(s.get("anchor_utc_uncertainty_ms")) is not int or not 0 <= s["anchor_utc_uncertainty_ms"] <= 1000:
        return "CLOCK_SYNC_UNVERIFIED"
    before, after = s["mono_before_ms"], s["mono_after_ms"]
    ab, aa = s["anchor_before_ms"], s["anchor_after_ms"]
    if not ab <= aa <= after or before > after or before < ab:
        return "CLOCK_MONOTONIC_ORDER_INVALID"
    if max(after - before, aa - ab) > MAX_SAMPLE_SPAN_MS:
        return "CLOCK_SAMPLE_BRACKET_TOO_WIDE"
    # Millisecond quantization is conservative in both directions.
    low = s["wall_ms"] - after - (s["anchor_wall_ms"] - ab) - 1
    high = s["wall_ms"] - before - (s["anchor_wall_ms"] - aa) + 1
    if low > WALL_STEP_MS or high < -WALL_STEP_MS:
        return "LOCAL_WALL_CLOCK_JUMP"
    if low < -WALL_STEP_MS or high > WALL_STEP_MS:
        return "CLOCK_DISCONTINUITY_UNCERTAIN"
    sync = s.get("sync", {})
    if not isinstance(sync, dict):
        return "CLOCK_SYNC_UNVERIFIED"
    if (
        sync.get("status") != "SYNC_OBSERVED"
        or type(sync.get("uncertainty_ms")) is not int
        or not 0 <= sync["uncertainty_ms"] <= 1000
        or type(sync.get("sample_mono_ms")) is not int
        or not 0 <= after - sync["sample_mono_ms"] <= 60_005
    ):
        return "CLOCK_SYNC_UNVERIFIED"
    if not s.get("epoch_valid", False):
        return s.get("epoch_reason") or "CLOCK_EPOCH_INVALID"
    return None


class ClockEpoch:
    """One process epoch. Invalidity is sticky; recovery requires a new instance.

    The caller serializes sample capture, including both monotonic bracket reads.
    A new instance is never automatic recovery or permission to restart a canary.
    """

    def __init__(self, epoch_id: str):
        self.id = epoch_id
        self.anchor: tuple[int, int, int] | None = None
        self.anchor_uncertainty_ms = 1001
        self.reason: str | None = None
        self.last_mono = 0

    def capture(self, wall: int, before: int, after: int, sync: dict) -> dict:
        if self.anchor is None:
            self.anchor = (wall, before, after)
            self.anchor_uncertainty_ms = sync.get("uncertainty_ms", 1001)
        aw, ab, aa = self.anchor
        s = {
            "epoch_id": self.id,
            "wall_ms": wall,
            "mono_before_ms": before,
            "mono_after_ms": after,
            "anchor_wall_ms": aw,
            "anchor_before_ms": ab,
            "anchor_after_ms": aa,
            "anchor_utc_uncertainty_ms": self.anchor_uncertainty_ms,
            "epoch_valid": self.reason is None,
            "epoch_reason": self.reason,
            "sync": dict(sync),
        }
        reason = sample_reason(s)
        if before < self.last_mono:
            reason = "CLOCK_MONOTONIC_ORDER_INVALID"
        self.reason = self.reason or reason
        self.last_mono = max(self.last_mono, after)
        s.update(epoch_valid=self.reason is None, epoch_reason=self.reason)
        return s


def capture(clock) -> tuple[int, int, dict | None]:
    if hasattr(clock, "sample"):
        s = clock.sample()
        return s["wall_ms"], s["mono_after_ms"], s
    wall, mono = clock.pair()
    return wall, mono, None


def same_epoch(samples: list[Any]) -> str | None:
    for s in samples:
        if reason := sample_reason(s):
            return reason
    identities = {
        (
            s["epoch_id"],
            s["anchor_wall_ms"],
            s["anchor_before_ms"],
            s["anchor_after_ms"],
            s["anchor_utc_uncertainty_ms"],
        )
        for s in samples
    }
    return "CLOCK_EPOCH_MIXING" if len(identities) != 1 else None


def estimate(probes: list[dict], scope_hash: str, exposure: str) -> dict:
    """Union every retained probe envelope; never select a favorable midpoint/RTT."""
    if not 2 <= len(probes) <= 16:
        raise ValueError("MULTIPLE_INDEPENDENT_CLOCK_PROBES_REQUIRED")
    lows: list[int] = []
    highs: list[int] = []
    rtts: list[int] = []
    samples: list[dict] = []
    ids: list[str] = []
    last_end = -1
    last_server = -1
    for p in probes:
        request, received, available = p["request"], p["receive"], p["available"]
        if p.get("scope_hash") != scope_hash or p.get("exposure") != exposure:
            raise ValueError("CLOCK_PROBE_SCOPE_OR_EXPOSURE_MISMATCH")
        samples.extend((request, received, available))
        if reason := same_epoch(samples):
            raise ValueError(reason)
        if (
            request["mono_before_ms"] <= last_end
            or request["mono_after_ms"] > received["mono_before_ms"]
            or received["mono_after_ms"] > available["mono_before_ms"]
            or type(p.get("server_ms")) is not int
            or p["server_ms"] <= last_server
            or not isinstance(p.get("wire_id"), str)
            or len(p["wire_id"]) != 64
            or p["wire_id"] in ids
        ):
            raise ValueError("CLOCK_PROBES_NOT_INDEPENDENT_OR_ORDERED")
        last_end, last_server = available["mono_after_ms"], p["server_ms"]
        ids.append(p["wire_id"])
        # Binance server time is generated within the measured request/response.
        # Quantization allowance does not assume symmetric network delays.
        lows.append(p["server_ms"] - received["mono_after_ms"] - 1)
        highs.append(p["server_ms"] - request["mono_before_ms"] + 1)
        rtts.append(received["mono_after_ms"] - request["mono_before_ms"])
    return {
        "version": VERSION,
        "scope_hash": scope_hash,
        "exposure": exposure,
        "epoch_id": samples[0]["epoch_id"],
        "native_minus_monotonic_low_ms": min(lows),
        "native_minus_monotonic_high_ms": max(highs),
        "uncertainty_ms": (max(highs) - min(lows)) / 2,
        "rtt_ms": rtts,
        "available": probes[-1]["available"],
        "probes": probes,
    }


def qualify(
    e: dict | None,
    native: int,
    receive: Any,
    available: Any,
    decision: Any,
    scope_hash: str,
    exposure: str,
    ttl: int,
    semantics: str,
) -> dict:
    reason = None
    delay = age = offset = None
    try:
        if (
            type(native) is not int
            or native <= 0
            or semantics not in ("EVENT_TIME", "TRANSACTION_TIME", "CANDLE_CLOSE", "ROLLING_WINDOW_CLOSE")
        ):
            raise ValueError("NATIVE_TIMESTAMP_OR_SEMANTICS_UNKNOWN")
        if not e or e.get("version") != VERSION:
            raise ValueError("CLOCK_UNCERTAINTY_UNKNOWN")
        verified = estimate(e["probes"], scope_hash, exposure)
        if verified != e:
            raise ValueError("CLOCK_ESTIMATE_EVIDENCE_MISMATCH")
        if reason := same_epoch([receive, available, decision, e["available"]]):
            raise ValueError(reason)
        if not (
            receive["mono_after_ms"]
            <= available["mono_before_ms"]
            <= available["mono_after_ms"]
            <= decision["mono_before_ms"]
            and e["available"]["mono_after_ms"] <= decision["mono_before_ms"]
        ):
            raise ValueError("LOCAL_MONOTONIC_ORDER_INVALID")
        if decision["mono_after_ms"] - e["available"]["mono_before_ms"] > MAX_PROBE_AGE_MS:
            raise ValueError("CLOCK_ESTIMATE_STALE")
        if any(
            decision["mono_after_ms"] - p["available"]["mono_before_ms"] > MAX_PROBE_AGE_MS
            for p in e["probes"]
        ):
            raise ValueError("CLOCK_ESTIMATE_STALE")
        if type(ttl) is not int or ttl <= 0 or e["uncertainty_ms"] > min(MAX_UNCERTAINTY_MS, ttl):
            raise ValueError("CLOCK_UNCERTAINTY_EXCEEDS_LEASE")
        lo, hi = e["native_minus_monotonic_low_ms"], e["native_minus_monotonic_high_ms"]
        if not all(isfinite(x) for x in (lo, hi)):
            raise ValueError("CLOCK_ESTIMATE_NONFINITE")
        delay = [receive["mono_before_ms"] - native + lo, receive["mono_after_ms"] - native + hi]
        age = [decision["mono_before_ms"] - native + lo, decision["mono_after_ms"] - native + hi]
        offset = [
            lo - (receive["wall_ms"] - receive["mono_before_ms"]),
            hi - (receive["wall_ms"] - receive["mono_after_ms"]),
        ]
        if min(delay) < 0 or min(age) < 0:
            raise ValueError("SOURCE_TIME_POTENTIALLY_FUTURE")
        if age[1] > ttl:
            raise ValueError("SOURCE_AGE_UPPER_BOUND_EXCEEDED")
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        reason = str(exc) or "CLOCK_EVIDENCE_INVALID"
    return {
        "version": VERSION,
        "native_event_or_snapshot_ms": native,
        "semantics": semantics,
        "event_to_receive_estimate_bounds_ms": delay,
        "event_age_estimate_bounds_ms": age,
        "native_minus_local_wall_bounds_ms": offset,
        "source_clock_qualified": reason is None,
        "reason": reason,
        "one_way_latency_proven": False,
    }


@contextmanager
def decision_clock(sample: dict, scope_hash: str):
    token = _decision.set((sample, scope_hash))
    try:
        yield
    finally:
        _decision.reset(token)


def current_decision() -> tuple[dict, str] | None:
    return _decision.get()


def decision_at(wall: int, evidence: dict) -> dict:
    """Historical as-of validation, bounded by the same live/replay decision epoch.

    Recorded availability/validation samples remain authoritative. Arbitrary raw
    wall timestamps cannot manufacture a fresh monotonic clock reading.
    """
    context = current_decision()
    if context is None:
        raise ValueError("CLOCK_DECISION_EVIDENCE_MISSING")
    current, scope = context
    if scope != evidence["scope_hash"]:
        raise ValueError("CLOCK_SCOPE_MISMATCH")
    if reason := same_epoch([current, evidence["decision"], evidence["receive"]]):
        raise ValueError(reason)
    for s in (current, evidence["decision"]):
        if wall == s["wall_ms"] and s["mono_after_ms"] <= current["mono_after_ms"]:
            return s
    raise ValueError("UNBRACKETED_DECISION_TIME")


@dataclass(frozen=True)
class NativeProvenance(DataProvenance):
    clock_evidence: dict[str, Any] = field(default_factory=dict)

    def reason(self, decision_ts: int, max_age_ms: int) -> str | None:
        if not self.admissible:
            return "SOURCE_NOT_ADMITTED"
        p = self.clock_evidence
        try:
            if not isinstance(p, dict) or not p or p.get("version") != VERSION:
                return "PUBLIC_CLOCK_EVIDENCE_MISSING"
            expected_id = "L4_PUBLIC:" + p["scope_hash"] + ":" + p["wire_id"]
            if (
                self.provider != p["provider"]
                or self.source_id != expected_id
                or self.exchange_event_ts != p["native_ms"]
                or self.exposure != p["exposure"]
                or self.received_ts != p["receive"]["wall_ms"]
                or self.available_ts != p["available"]["wall_ms"]
                or p["evidence_hash"] != fingerprint({k: v for k, v in p.items() if k != "evidence_hash"})
            ):
                return "CLOCK_PROVENANCE_BINDING_MISMATCH"
            decision = decision_at(decision_ts, p)
            start, end = p["source_window_ms"]
            utc_uncertainty = decision["sync"]["uncertainty_ms"]
            mono_end = (
                decision["anchor_before_ms"]
                + end
                - decision["anchor_wall_ms"]
                - decision["anchor_utc_uncertainty_ms"]
                - 1
            )
            if decision["wall_ms"] - utc_uncertainty < start:
                return "GRANT_WINDOW_NOT_OPEN"
            if decision["wall_ms"] + utc_uncertainty >= end or decision["mono_after_ms"] >= mono_end:
                return "GRANT_WINDOW_EXPIRED"
            ttl = max_age_ms
            if repair := p.get("closed_bar_repair"):
                size = {"1m": 60000, "5m": 300000}.get(repair["params"]["interval"])
                lo, hi = repair["params"]["startTime"], repair["params"]["endTime"]
                request = repair["request"]
                if (p["semantics"] != "CANDLE_CLOSE" or not size
                    or not start <= lo <= self.exchange_event_ts <= hi < end
                    or hi - lo + 1 > 99 * size or lo % size or (hi + 1) % size
                    or not 1 <= repair["params"]["limit"] <= 99
                    or same_epoch([request, p["receive"]])
                    or not 0 <= p["receive"]["mono_after_ms"] - request["mono_before_ms"] <= 5000
                    or decision["mono_after_ms"] - p["available"]["mono_before_ms"] > max_age_ms):
                    return "CLOSED_BAR_REPAIR_PROVENANCE_INVALID_OR_STALE"
                ttl = 100 * size + 5000
            return qualify(
                p["estimate"],
                self.exchange_event_ts,
                p["receive"],
                p["available"],
                decision,
                p["scope_hash"],
                self.exposure,
                ttl,
                p["semantics"],
            )["reason"]
        except (KeyError, TypeError, ValueError) as exc:
            return str(exc) or "CLOCK_EVIDENCE_INVALID"


def provenance(
    base: DataProvenance,
    *,
    record: dict,
    native: int,
    semantics: str,
    admitted: bool,
    source_window: tuple[int, int],
) -> NativeProvenance:
    samples = record["wire"]["clock_samples"]
    p = {
        "version": VERSION,
        "provider": base.provider,
        "scope_hash": record["scope_hash"],
        "wire_id": fingerprint(record["wire"]),
        "exposure": base.exposure,
        "native_ms": native,
        "semantics": semantics,
        "receive": samples["receive"],
        "available": record.get("normalization_sample", samples["available"]),
        "decision": record["decision_sample"],
        "estimate": record.get("clock"),
        "source_window_ms": list(source_window),
    }
    if (record.get("source_contract_version") == "L4_LONGHORIZON_V1"
        and record["wire"]["endpoint_id"] == "binance_usdm_klines_rest"):
        p["closed_bar_repair"] = {"params": record["wire"]["params"], "request": samples["request"]}
    p["evidence_hash"] = fingerprint(p)
    return NativeProvenance(
        **{
            **primitive(base),
            "exchange_event_ts": native,
            "source_id": "L4_PUBLIC:" + p["scope_hash"] + ":" + p["wire_id"],
            "admissible": admitted,
        },
        clock_evidence=p,
    )


def from_record(value: dict) -> DataProvenance:
    return NativeProvenance(**value) if "clock_evidence" in value else DataProvenance(**value)


def native_bounds(p: NativeProvenance, native_ms: int) -> tuple[int, int]:
    """Monotonic occurrence bounds, not a replacement exchange timestamp."""
    e = p.clock_evidence["estimate"]
    return (native_ms - e["native_minus_monotonic_high_ms"], native_ms - e["native_minus_monotonic_low_ms"])


def historical_decision(p: NativeProvenance, native_cutoff: int) -> int:
    """Admit a stored row as-of a native feature cutoff, without future availability."""
    evidence = p.clock_evidence
    wall = evidence["decision"]["wall_ms"]
    recorded = decision_at(wall, evidence)  # Also checks the current epoch/replay scope.
    e = evidence["estimate"]
    if evidence.get("closed_bar_repair") and native_cutoff >= p.exchange_event_ts:
        # A repaired field is available only at its actual recorded receipt.
        # decision_at already rejects any earlier decision context.
        return wall
    if recorded["mono_after_ms"] + e["native_minus_monotonic_high_ms"] > native_cutoff:
        raise ValueError("FIELD_NOT_AVAILABLE_AT_NATIVE_CUTOFF")
    return wall


def bar_decision(bar, requested: int) -> int:
    p = bar.fields[0].provenance
    context = current_decision()
    if context is None:
        raise ValueError("CLOCK_DECISION_EVIDENCE_MISSING")
    if requested == context[0]["wall_ms"] or requested == p.clock_evidence["decision"]["wall_ms"]:
        return requested
    if p.clock_evidence.get("closed_bar_repair") and bar.end <= requested <= bar.end + 1000:
        # Late repairs may enter a NEW decision after receipt, never a past scan.
        recorded = p.clock_evidence["decision"]
        decision_at(recorded["wall_ms"], p.clock_evidence)
        if recorded["mono_after_ms"] > context[0]["mono_before_ms"]:
            raise ValueError("REPAIR_NOT_AVAILABLE_AT_CURRENT_DECISION")
        return recorded["wall_ms"]
    if bar.end <= requested <= bar.end + 1000:
        return historical_decision(p, requested)
    raise ValueError("UNBRACKETED_DECISION_TIME")


def native_before(p: NativeProvenance, native_ms: int, wall: int) -> bool:
    """True only if every point in the native occurrence interval is before decision."""
    try:
        decision = decision_at(wall, p.clock_evidence)
        return native_bounds(p, native_ms)[1] <= decision["mono_before_ms"]
    except (KeyError, TypeError, ValueError):
        return False


def expired(anchors: dict, wall: int) -> bool:
    if "expiry_mono_ms" not in anchors:
        return wall >= anchors["expiry"]
    context = current_decision()
    return bool(
        context
        and context[0]["epoch_id"] == anchors["clock_epoch_id"]
        and context[0]["mono_after_ms"] >= anchors["expiry_mono_ms"]
    )


def post_setup(bar, anchors: dict, known_wall: int | None) -> bool:
    if "known_clock_sample" not in anchors:
        return known_wall is None or bar.start >= known_wall
    p = bar.fields[0].provenance
    known = anchors["known_clock_sample"]
    if not isinstance(p, NativeProvenance) or same_epoch([known, p.clock_evidence["receive"]]):
        return False
    return native_bounds(p, bar.start)[0] >= known["mono_after_ms"]
