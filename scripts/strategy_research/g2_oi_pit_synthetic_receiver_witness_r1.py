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
MAX_RAW_BYTES = 4096
MAX_QUANTITY_DIGITS = 32
MAX_QUANTITY_SCALE = 18


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
    """Half-open local observation mask, not coverage inferred from a REST label.

    Every field is invented. Unknown completeness fails closed; OI masks must
    name their bucket end. known_at_ms is the mask's safe completion receipt.
    """
    source: Literal["X", "QUOTE", "OI"]
    start_ms: int
    end_ms: int
    missing: bool = False
    censored: bool = False
    complete_observation: bool | None = None
    period_end_ms: int | None = None
    known_at_ms: int | None = None


@dataclass(frozen=True)
class ObservationWindow:
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class DecisionWindows:
    """Predeclared X confirmation and decision-quote contracts, never inferred.

    quote_max_age_ms is an invented fixture limit, not a production threshold.
    The two complete 15m OI windows are derived separately from bucket identity.
    """
    x_confirmation: ObservationWindow
    decision_quote: ObservationWindow
    quote_max_age_ms: int


@dataclass(frozen=True)
class Verdict:
    pit_status: str
    source_status: str
    diagnostic: str
    selected_versions: tuple[str, ...] = ()
    synthetic_label: str = "SYNTHETIC_ONLY"


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("DUPLICATE_JSON_MEMBER")
        obj[key] = value
    return obj


def _reject_constant(value: str) -> None:
    raise ValueError("NON_JSON_NUMERIC_CONSTANT")


def _decode(a: Attempt) -> tuple[tuple[str, str, str, str, str, int], Decimal] | None:
    if (
        a.contract_version != CONTRACT or a.unit != UNIT or a.parser_version != PARSER
        or a.venue != VENUE or a.endpoint != ENDPOINT or a.period != "15m"
        or len(a.raw_body) > MAX_RAW_BYTES
    ):
        return None
    try:
        obj = json.loads(a.raw_body.decode("utf-8"), object_pairs_hook=_unique_members,
                         parse_constant=_reject_constant)
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
        literal = obj["sumOpenInterest"]
        parts = literal.split(".")
        # Bounded ASCII fixed-point only: no signs, exponents, whitespace,
        # underscores, nonfinite tokens or context-dependent rounding.
        if (len(parts) > 2 or not all(p.isascii() and p.isdigit() for p in parts)
                or sum(map(len, parts)) > MAX_QUANTITY_DIGITS
                or (len(parts) == 2 and len(parts[1]) > MAX_QUANTITY_SCALE)):
            return None
        qty = Decimal(literal)
        if end <= 0 or end > 2**63 - 1 or end % PERIOD_MS or not qty.is_finite() or qty < 0:
            return None
        return (a.venue, a.endpoint, "BTCUSDT", a.contract_version, a.unit, end), qty
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidOperation, TypeError,
            ValueError, RecursionError):
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
            if parsed is not None:
                body_safe = a.clock.safe_upper(a.body_last_byte_ns)
                if body_safe is None or body_safe < parsed[0][-1] or safe < parsed[0][-1]:
                    kind = "PERIOD_RECEIPT_ORDER_UNKNOWN"
                    parsed = None  # Reject before clamping against any earlier ACK.
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
    required_windows: DecisionWindows | None = None,
) -> Verdict:
    """Internal time diagnostic only; NEVER source/PIT admission."""
    def stop(reason: str) -> Verdict:
        return Verdict("PIT_UNKNOWN", "SOURCE_NOT_ADMITTED", reason)

    if not rights_receipt or not origin_receipt:
        return stop("RIGHTS_OR_ORIGIN_UNVERIFIED")
    if type(newest_period_end_ms) is not int or type(decision_ms) is not int:
        return stop("PERIOD_NOT_PIT")
    if any(type(span.start_ms) is not int or type(span.end_ms) is not int
           or span.start_ms < 0 or span.start_ms >= span.end_ms or span.end_ms > decision_ms
           or span.missing is not False or span.censored is not False for span in evidence):
        return stop("SOURCE_GAP")
    if {"X", "QUOTE", "OI"} != {s.source for s in evidence}:
        return stop("SOURCE_GAP")
    ends = (newest_period_end_ms - PERIOD_MS, newest_period_end_ms)
    if ends[0] < PERIOD_MS or ends[1] % PERIOD_MS or ends[1] >= decision_ms:
        return stop("PERIOD_NOT_PIT")
    if not isinstance(required_windows, DecisionWindows):
        return stop("SOURCE_EVIDENCE_UNKNOWN")
    x, quote = required_windows.x_confirmation, required_windows.decision_quote
    if (not all(isinstance(w, ObservationWindow) for w in (x, quote))
            or any(type(t) is not int for w in (x, quote) for t in (w.start_ms, w.end_ms))
            or not 0 <= x.start_ms < x.end_ms < decision_ms
            or newest_period_end_ms > x.end_ms
            or not 0 <= quote.start_ms < quote.end_ms < decision_ms
            or type(required_windows.quote_max_age_ms) is not int
            or required_windows.quote_max_age_ms <= 0
            or decision_ms - quote.start_ms > required_windows.quote_max_age_ms):
        return stop("SOURCE_GAP")
    required = {
        ("X", None): x, ("QUOTE", None): quote,
        **{("OI", end): ObservationWindow(end - PERIOD_MS, end) for end in ends},
    }
    if any((s.source, s.period_end_ms) not in required
           or (s.source == "OI" and type(s.period_end_ms) is not int) for s in evidence):
        return stop("SOURCE_GAP")
    if any(s.complete_observation is not True or type(s.known_at_ms) is not int
           or s.known_at_ms < s.end_ms or s.known_at_ms >= decision_ms for s in evidence):
        return stop("SOURCE_EVIDENCE_UNKNOWN")
    for identity, window in required.items():
        masks = sorted((s for s in evidence if (s.source, s.period_end_ms) == identity),
                       key=lambda s: s.start_ms)
        cursor = window.start_ms
        for mask in masks:
            if mask.start_ms != cursor or mask.end_ms > window.end_ms:
                return stop("SOURCE_GAP")
            cursor = mask.end_ms
        if cursor != window.end_ms:
            return stop("SOURCE_GAP")
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
