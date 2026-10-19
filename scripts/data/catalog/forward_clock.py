"""C3 feature-clock contract. No Forward payload or outcome access."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

Mode = Literal["DESCRIPTIVE_EVENT_TIME", "RECEIVER_PIT_REQUIRED"]
Quality = Literal["ARCHIVE_EVENT_ONLY", "RECEIVER_OBSERVED", "SYNTHETIC_RECEIVER_DEFINED",
                  "FORWARD_CLOSED_MANIFEST_ONLY", "UNKNOWN"]
Kind = Literal["bar", "flow", "oi", "funding"]


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("UTC_CLOCK_REQUIRED")
    return value.astimezone(UTC)


def archive_label_window(filename: str, calendar_timezone: Literal["UTC", "UTC+8"]) -> tuple[datetime, datetime]:
    """Nominal file-day window only; never a measured event or receiver clock."""
    match = re.fullmatch(r"[A-Za-z0-9_-]+-(20\d{2}-\d{2}-\d{2})\.(?:zip|tar\.gz)", filename)
    if not match or calendar_timezone not in ("UTC", "UTC+8"):
        raise ValueError("ARCHIVE_FILENAME_OR_TIMEZONE_INVALID")
    start = datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)
    if calendar_timezone == "UTC+8":
        start -= timedelta(hours=8)
    return start, start + timedelta(days=1)


@dataclass(frozen=True)
class ClockRecord:
    exchange: str
    instrument: str
    product: str
    stream: str
    kind: Kind
    event_ts_utc: datetime
    source_native_ts: int | None
    source_time_unit: Literal["s", "ms", "us"] | None
    source_id: str
    raw_sha256: str | None
    source_native_clock_role: Literal["EVENT_TS", "INTERVAL_OPEN", "DERIVED_INTERVAL_OPEN"] = "EVENT_TS"
    interval_open: datetime | None = None
    interval_close: datetime | None = None
    last_contributing_event: datetime | None = None
    exchange_published_at: datetime | None = None
    receiver_first_known_at: datetime | None = None
    local_ingested_at: datetime | None = None
    durable_committed_at: datetime | None = None
    archive_downloaded_at: datetime | None = None
    evidence: Literal["HISTORY_ARCHIVE", "TEST_ONLY_SYNTHETIC", "FORWARD_MANIFEST_METADATA"] = "HISTORY_ARCHIVE"
    receiver_proof: Literal["NONE", "TEST_ONLY_SYNTHETIC", "ORIGINAL_RECEIVER_RECORD"] = "NONE"
    gap: bool = False
    duplicate: bool = False
    precision: str = "UNKNOWN"
    calendar_timezone: str = "UTC"

    def __post_init__(self) -> None:
        for name in ("event_ts_utc", "interval_open", "interval_close", "last_contributing_event",
                     "exchange_published_at", "receiver_first_known_at", "local_ingested_at",
                     "durable_committed_at", "archive_downloaded_at"):
            value = getattr(self, name)
            if value is not None:
                utc(value)
        if not all((self.exchange, self.instrument, self.product, self.stream, self.source_id)):
            raise ValueError("SOURCE_IDENTITY_REQUIRED")
        if (self.receiver_first_known_at is None) != (self.receiver_proof == "NONE"):
            raise ValueError("RECEIVER_PROOF_MISSING_OR_CONTRADICTORY")
        if self.receiver_proof == "TEST_ONLY_SYNTHETIC" and self.evidence != "TEST_ONLY_SYNTHETIC":
            raise ValueError("SYNTHETIC_PROOF_SOURCE_MISMATCH")
        if self.receiver_proof == "ORIGINAL_RECEIVER_RECORD" and self.evidence != "HISTORY_ARCHIVE":
            raise ValueError("ORIGINAL_RECEIVER_PROOF_SOURCE_MISMATCH")
        if (self.source_native_ts is None) != (self.source_time_unit is None):
            raise ValueError("NATIVE_CLOCK_INCOMPLETE")
        if self.source_native_ts is not None:
            scale = {"s": 1, "ms": 1000, "us": 1000000}[self.source_time_unit]
            seconds, fraction = divmod(self.source_native_ts, scale)
            try:
                native = datetime.fromtimestamp(seconds, UTC) + timedelta(microseconds=fraction * 1000000 // scale)
            except (OverflowError, ValueError) as exc:
                raise ValueError("NATIVE_CLOCK_UNIT_MISMATCH") from exc
            target = self.interval_open if self.source_native_clock_role in ("INTERVAL_OPEN", "DERIVED_INTERVAL_OPEN") else self.event_ts_utc
            if target is None or abs((native - target).total_seconds()) >= 1 / scale:
                raise ValueError("NATIVE_CLOCK_UNIT_MISMATCH")
        if self.interval_open is not None and self.interval_close is not None and \
           not self.interval_open < self.interval_close:
            raise ValueError("INTERVAL_INVALID")
        if self.last_contributing_event and self.interval_close and self.last_contributing_event > self.interval_close:
            raise ValueError("CONTRIBUTOR_AFTER_CLOSE")
        if self.raw_sha256 is not None and (len(self.raw_sha256) != 64 or
                                            any(c not in "0123456789abcdef" for c in self.raw_sha256)):
            raise ValueError("SOURCE_HASH_INVALID")

    @property
    def quality(self) -> Quality:
        if self.evidence == "FORWARD_MANIFEST_METADATA":
            return "FORWARD_CLOSED_MANIFEST_ONLY"
        if self.receiver_proof == "TEST_ONLY_SYNTHETIC":
            return "SYNTHETIC_RECEIVER_DEFINED"
        if self.receiver_proof == "ORIGINAL_RECEIVER_RECORD":
            return "RECEIVER_OBSERVED"
        if self.evidence == "HISTORY_ARCHIVE":
            return "ARCHIVE_EVENT_ONLY"
        return "UNKNOWN"

    @property
    def availability_gate(self) -> datetime | None:
        if self.receiver_first_known_at is None:
            return None
        return max(t for t in (self.event_ts_utc, self.interval_close, self.last_contributing_event,
                               self.exchange_published_at, self.receiver_first_known_at,
                               self.local_ingested_at, self.durable_committed_at) if t is not None)


def _origin(origin: datetime) -> datetime:
    utc(origin)
    if origin.minute != 1 or origin.second or origin.microsecond:
        raise ValueError("ORIGIN_NOT_HH01_UTC")
    return origin - timedelta(minutes=1)


def _validate_group(records: Sequence[ClockRecord], *, exchange: str, instrument: str,
                    product: str, stream: str, kind: Kind, expected_sha256: str | None) -> list[str]:
    blockers: list[str] = []
    if len(records) > 10000:
        raise ValueError("RECORD_BUDGET_EXCEEDED")
    if any((r.exchange, r.instrument, r.product, r.stream, r.kind) !=
           (exchange, instrument, product, stream, kind) for r in records):
        blockers.append("SOURCE_FAMILY_OR_INSTRUMENT_MISMATCH")
    if any(r.gap for r in records):
        blockers.append("SOURCE_GAP_OVERLAP")
    if any(r.duplicate for r in records):
        blockers.append("DUPLICATE_SOURCE_CLOCK")
    if len({(r.source_id, r.event_ts_utc) for r in records}) != len(records):
        blockers.append("DUPLICATE_SOURCE_CLOCK")
    if len({r.source_time_unit for r in records if r.source_time_unit}) > 1:
        blockers.append("MIXED_NATIVE_TIMESTAMP_UNITS")
    if expected_sha256 and any(r.raw_sha256 != expected_sha256 for r in records):
        blockers.append("SOURCE_HASH_MUTATED")
    return sorted(set(blockers))


def evaluate_asof(records: Sequence[ClockRecord], *, origin: datetime, exchange: str,
                  instrument: str, product: str, stream: str, kind: Kind, mode: Mode,
                  flow_minutes: int = 1, expected_sha256: str | None = None,
                  max_receiver_age: timedelta | None = None) -> dict:
    """Return feature-only readiness. Any uncertainty is NO_ACTION."""
    cutoff = _origin(origin)
    if mode not in ("DESCRIPTIVE_EVENT_TIME", "RECEIVER_PIT_REQUIRED"):
        raise ValueError("MODE_INVALID")
    if kind == "flow" and flow_minutes not in (1, 5, 60):
        raise ValueError("FLOW_WINDOW_INVALID")
    blockers = _validate_group(records, exchange=exchange, instrument=instrument,
                               product=product, stream=stream, kind=kind,
                               expected_sha256=expected_sha256)
    if not records:
        blockers.append("SOURCE_WINDOW_MISSING")
    selected: list[ClockRecord] = []
    if kind in ("bar", "flow"):
        count = flow_minutes if kind == "flow" else 1
        expected = {cutoff - timedelta(minutes=i) for i in
                    (range(1, count + 1) if kind == "flow" else (2,))}
        selected = [r for r in records if r.interval_open in expected]
        if {r.interval_open for r in selected} != expected or len(selected) != count:
            blockers.append("INCOMPLETE_CLOSED_WINDOW")
        for r in selected:
            if r.interval_close != r.interval_open + timedelta(minutes=1) or r.interval_close > cutoff:
                blockers.append("OFF_GRID_OR_UNCLOSED_INTERVAL")
            if kind == "bar" and r.interval_close == cutoff:
                blockers.append("BAR_NOT_STRICTLY_PRE_CUTOFF")
    elif kind == "oi":
        candidates = [r for r in records if cutoff - timedelta(minutes=10) <= r.event_ts_utc <=
                      cutoff - timedelta(minutes=5)]
        if candidates:
            z = max(candidates, key=lambda r: r.event_ts_utc)
            selected = [z] + [r for r in records if r.event_ts_utc == z.event_ts_utc - timedelta(hours=4)]
            if len(selected) != 2:
                blockers.append("OI_4H_PREDECESSOR_MISSING")
            if any(r.event_ts_utc.second or r.event_ts_utc.microsecond or r.event_ts_utc.minute % 5
                   for r in selected):
                blockers.append("OI_OFF_5M_GRID")
        else:
            blockers.append("OI_SAMPLE_WINDOW_MISSING")
    else:
        settled = [r for r in records if r.event_ts_utc < cutoff]
        if settled:
            selected = [max(settled, key=lambda r: r.event_ts_utc)]
        else:
            blockers.append("PREVIOUS_FUNDING_SETTLEMENT_MISSING")
    if mode == "RECEIVER_PIT_REQUIRED":
        for r in selected:
            if r.receiver_first_known_at is None or r.availability_gate is None:
                blockers.append("RECEIVER_FIRST_KNOWN_UNKNOWN")
            elif r.availability_gate > origin:
                blockers.append("AVAILABLE_AFTER_ORIGIN")
            elif max_receiver_age and origin - r.receiver_first_known_at > max_receiver_age:
                blockers.append("RECEIVER_WATERMARK_STALE")
    blockers = sorted(set(blockers))
    return {"origin_utc": origin.isoformat(), "cutoff_utc": cutoff.isoformat(), "mode": mode,
            "identity": {"exchange": exchange, "instrument": instrument, "product": product,
                         "stream": stream, "kind": kind}, "selected_source_ids": [r.source_id for r in selected],
            "qualities": sorted({r.quality for r in selected}),
            "availability_gate_utc": max((r.availability_gate for r in selected if r.availability_gate),
                                         default=None).isoformat() if selected and all(r.availability_gate for r in selected) else None,
            "action": "FEATURE_READY_NOT_TRADE" if not blockers else "NO_ACTION",
            "blockers": blockers, "real_outcome_labels_read": 0}
