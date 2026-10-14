"""Pure synthetic OI receiver/PIT witness model; no I/O or source admission.

All envelope times, raw bytes, signatures, clocks and receipts are INVENTED inputs.
An internally coherent witness is not a trusted provider, chrony, storage or rights
attestation. This module has no mechanism that can return admitted PIT/source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Literal

PERIOD_MS = 15 * 60 * 1000
VENUE = "BINANCE_USDM_PERPETUAL_SYNTHETIC"
ENDPOINT = "/futures/data/openInterestHist"
CONTRACT = "INVENTED_BTCUSDT_USDM_CONTRACT_V1"
UNIT = "INVENTED_NATIVE_CONTRACTS"
PARSER = "SYNTHETIC_OI15M_JSON_V1"


def _hash(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _ceil_ms(ns: int) -> int:
    return (ns + 999_999) // 1_000_000


@dataclass(frozen=True)
class ClockWitness:
    epoch: str
    anchor_mono_ns: int
    anchor_utc_upper_ms: int
    coverage_start_ns: int
    coverage_end_ns: int
    max_drift_ms: int
    offset_uncertainty_ms: int
    external_chrony_receipt: str | None
    step_detected: bool = False
    wall_rollback: bool = False
    epoch_bridge_verified: bool = False
    synthetic_signed: bool = False  # A caller-controlled boolean grants nothing.

    def safe_upper(self, *moments: int | None) -> int | None:
        if (
            not self.epoch or not self.external_chrony_receipt
            or self.step_detected or self.wall_rollback
            or self.max_drift_ms < 0 or self.offset_uncertainty_ms > 1000
            or self.offset_uncertainty_ms < 0
            or self.coverage_start_ns > self.anchor_mono_ns
            or self.anchor_mono_ns > self.coverage_end_ns
            or any(v is None or not self.coverage_start_ns <= v <= self.coverage_end_ns
                   for v in moments)
        ):
            return None
        last = max(v for v in moments if v is not None)
        if last < self.anchor_mono_ns:
            return None  # Cannot apply a forward-only bound backwards.
        return (
            self.anchor_utc_upper_ms + _ceil_ms(last - self.anchor_mono_ns)
            + self.max_drift_ms
        )


@dataclass(frozen=True)
class Attempt:
    sequence: int
    attempt_id: str
    request_epoch: str
    headers_epoch: str
    body_epoch: str
    ack_epoch: str
    request_start_ns: int
    headers_received_ns: int | None
    body_last_byte_ns: int | None
    integrity_complete_ns: int | None
    durability_ack_ns: int | None
    raw_body: bytes
    claimed_raw_sha256: str
    claimed_raw_len: int
    body_complete: bool
    append_ack: bool
    fsync_ack: bool
    crash_phase: Literal["NONE", "BEFORE_ACK", "AFTER_ACK"]
    clock: ClockWitness
    contract_version: str = CONTRACT
    unit: str = UNIT
    parser_version: str = PARSER
    period: str = "15m"
    venue: str = VENUE
    endpoint: str = ENDPOINT
    http_status: int = 200
    rights_receipt: str | None = None
    origin_receipt: str | None = None
    synthetic_signed: bool = False


@dataclass(frozen=True)
class Receipt:
    sequence: int
    attempt_id: str
    raw_digest: str
    logical_key: tuple[str, str, str, str, str, int] | None
    quantity: Decimal | None
    first_safe_ms: int | None
    receipt_kind: str
    version: int | None
    version_id: str | None
    corrects_version_id: str | None
    first_known_at_ms: int | None
    synthetic_label: str = "SYNTHETIC_ONLY"


@dataclass(frozen=True)
class ReceiverState:
    receipts: tuple[Receipt, ...] = ()


@dataclass(frozen=True)
class EvidenceSpan:
    source: Literal["X", "QUOTE", "OI"]
    start_ms: int
    end_ms: int
    missing: bool = False
    censored: bool = False


@dataclass(frozen=True)
class Verdict:
    pit_status: str
    source_status: str
    diagnostic: str
    selected_versions: tuple[str, ...] = ()
    synthetic_label: str = "SYNTHETIC_ONLY"


def _decode(a: Attempt) -> tuple[tuple[str, str, str, str, str, int], Decimal] | None:
    if (
        a.contract_version != CONTRACT or a.unit != UNIT or a.parser_version != PARSER
        or a.venue != VENUE or a.endpoint != ENDPOINT or a.period != "15m"
    ):
        return None
    try:
        obj = json.loads(a.raw_body)
        if not isinstance(obj, dict) or set(obj) != {
            "symbol", "period", "timestamp", "sumOpenInterest", "unit", "contractVersion"
        }:
            return None
        if (
            obj["symbol"] != "BTCUSDT" or obj["period"] != "15m"
            or obj["unit"] != UNIT or obj["contractVersion"] != CONTRACT
            or type(obj["timestamp"]) is not int
            or not isinstance(obj["sumOpenInterest"], str)
        ):
            return None
        end = obj["timestamp"]
        qty = Decimal(obj["sumOpenInterest"])
        if end <= 0 or end % PERIOD_MS or not qty.is_finite() or qty < 0:
            return None
        return (a.venue, a.endpoint, "BTCUSDT", a.contract_version, a.unit, end), qty
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidOperation, TypeError, ValueError):
        return None


def append_attempt(state: ReceiverState, a: Attempt) -> ReceiverState:
    """Append one invented trace record, including failures; never edit an old receipt."""
    if a.sequence != len(state.receipts) + 1 or not a.attempt_id:
        raise ValueError("NONCONTIGUOUS_OR_BAD_APPEND_SEQUENCE")
    if any(r.attempt_id == a.attempt_id for r in state.receipts):
        raise ValueError("REUSED_ATTEMPT_ID")
    raw_digest = _hash(a.raw_body)
    last_safe = max((r.first_safe_ms for r in state.receipts if r.first_safe_ms is not None),
                    default=None)
    kind = "SOURCE_WITNESS_INCOMPLETE"
    parsed = None
    safe = None
    if a.http_status != 200:
        kind = "COLLECTOR_PERMIT_INELIGIBLE" if a.http_status in (418, 429) else "HTTP_FAILED"
    elif not (
        a.body_complete and a.raw_body and a.claimed_raw_len == len(a.raw_body)
        and a.claimed_raw_sha256 == raw_digest
        and a.headers_received_ns is not None
        and a.body_last_byte_ns is not None
        and a.integrity_complete_ns is not None
        and a.request_start_ns <= a.headers_received_ns <= a.body_last_byte_ns
        <= a.integrity_complete_ns
    ):
        kind = "BODY_OR_DIGEST_INCOMPLETE"
    elif not (
        a.append_ack and a.fsync_ack and a.durability_ack_ns is not None
        and a.durability_ack_ns >= a.integrity_complete_ns
        and a.crash_phase != "BEFORE_ACK"
    ):
        kind = "LATE_OR_MISSING_DURABILITY"
    elif len({a.request_epoch, a.headers_epoch, a.body_epoch, a.ack_epoch, a.clock.epoch}) != 1:
        kind = "CLOCK_UNKNOWN"
    else:
        safe = a.clock.safe_upper(
            a.request_start_ns, a.headers_received_ns, a.body_last_byte_ns,
            a.integrity_complete_ns, a.durability_ack_ns,
        )
        if safe is None:
            kind = "CLOCK_UNKNOWN"
        else:
            parsed = _decode(a)
            kind = "INVALID_CONTRACT_OR_DECODER" if parsed is None else "NEW_VERSION"
    if parsed is None:
        key, qty = None, None
        safe = None
    else:
        key, qty = parsed
        if last_safe is not None and safe is not None:
            safe = max(safe, last_safe)  # Never retrodate by permuted ACKs.
    previous = tuple(r for r in state.receipts if r.logical_key == key and key is not None
                     and r.version_id is not None)
    version = None
    version_id = None
    corrects = None
    first_known = None
    if key is not None and safe is not None:
        exact = next((r for r in previous if r.raw_digest == raw_digest), None)
        same_value = next((r for r in previous if r.quantity == qty), None)
        if exact is not None:
            kind, version, version_id = "RAW_DUPLICATE", exact.version, exact.version_id
            first_known = exact.first_known_at_ms
        elif same_value is not None:
            kind, version, version_id = (
                "FORMAT_DUPLICATE", same_value.version, same_value.version_id
            )
            first_known = same_value.first_known_at_ms
        else:
            version = max((r.version or 0 for r in previous), default=0) + 1
            corrects = previous[-1].version_id if previous else None
            version_id = _hash(repr((key, version, str(qty))).encode())
            first_known = safe
            kind = "REVISION" if previous else "NEW_VERSION"
    entry = Receipt(
        sequence=a.sequence, attempt_id=a.attempt_id, raw_digest=raw_digest,
        logical_key=key, quantity=qty, first_safe_ms=safe, receipt_kind=kind,
        version=version, version_id=version_id,
        corrects_version_id=corrects, first_known_at_ms=first_known,
    )
    return ReceiverState(state.receipts + (entry,))


def replay(attempts: tuple[Attempt, ...]) -> ReceiverState:
    """Immutable explicit sequence is authority in this *synthetic* replay only."""
    state = ReceiverState()
    for attempt in sorted(attempts, key=lambda a: a.sequence):
        state = append_attempt(state, attempt)
    return state


def evaluate_two_buckets(
    state: ReceiverState, *, newest_period_end_ms: int, decision_ms: int,
    evidence: tuple[EvidenceSpan, ...], rights_receipt: str | None = None,
    origin_receipt: str | None = None,
) -> Verdict:
    """Internal time diagnostic only; NEVER source/PIT admission."""
    def stop(reason: str) -> Verdict:
        return Verdict("PIT_UNKNOWN", "SOURCE_NOT_ADMITTED", reason)

    if not rights_receipt or not origin_receipt:
        return stop("RIGHTS_OR_ORIGIN_UNVERIFIED")
    if any(span.start_ms >= span.end_ms or span.end_ms > decision_ms
           or span.missing or span.censored for span in evidence):
        return stop("SOURCE_GAP")
    if {"X", "QUOTE", "OI"} != {s.source for s in evidence}:
        return stop("SOURCE_GAP")
    ends = (newest_period_end_ms - PERIOD_MS, newest_period_end_ms)
    if ends[0] < 0 or ends[1] >= decision_ms:
        return stop("PERIOD_NOT_PIT")
    selected = []
    for end in ends:
        choices = [r for r in state.receipts if r.logical_key is not None
                   and r.logical_key[-1] == end and r.version_id is not None]
        if not choices:
            return stop("GAP_OR_NONCONSECUTIVE_BUCKET")
        known = [r for r in choices if r.first_known_at_ms is not None
                 and r.first_known_at_ms < decision_ms]
        if not known:
            return stop("LATE_DURABLE_RECEIPT")
        latest = max(known, key=lambda r: (r.first_known_at_ms, r.version or 0))
        if any(r.receipt_kind == "REVISION" and r.first_known_at_ms == latest.first_known_at_ms
               and r.version_id != latest.version_id for r in known):
            return stop("REVISION_ORDER_UNKNOWN")
        selected.append(latest.version_id)
    return Verdict("PIT_UNKNOWN", "SOURCE_NOT_ADMITTED",
                   "SYNTHETIC_TIME_COHERENT_NOT_ADMITTED", tuple(selected))
