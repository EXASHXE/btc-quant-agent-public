"""Independent preregistered funding settlement evidence authority (AG-01 repair).

The funding evidence file is the only admissible source of formal funding
events. Caller/job ``funding_events`` lists remain optional assertions that
must exactly equal the events independently reconstructed from this evidence;
they are never the authority. This is the single semantic owner of strict
funding evidence parsing, coverage validation and settlement normalization.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any

from ..research_contract.canonical import canonical_json, canonical_sha256
from ..research_contract.models import EvidenceCompleteness, EvidenceReference
from .funding import FundingSettlement

FORMAL_FUNDING_EVIDENCE_SCHEMA_VERSION = "1.0.0"
FORMAL_FUNDING_EVIDENCE_TYPE = "FORMAL_FUNDING_SETTLEMENT_DATASET"

_FUNDING_EVIDENCE_KEYS = frozenset(
    {"schema_version", "product", "coverage_start_ms", "coverage_end_ms", "events"}
)
_FUNDING_EVENT_KEYS = frozenset({"timestamp_ms", "funding_rate", "mark_price"})


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON value: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _finite_number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be finite")
    if positive and converted <= 0:
        raise ValueError(f"{label} must be strictly positive")
    return converted


@dataclass(frozen=True)
class FundingIntervalIdentity:
    """Deeply immutable identity of one preregistered funding evidence artifact.

    Bound into ``ComparisonContract.funding_interval`` at protocol creation, this
    makes the concrete funding settlement dataset preregistered through the
    protocol benchmark identity instead of caller-supplied at run time.
    """

    evidence_id: str
    content_sha256: str
    coverage_start_ms: int
    coverage_end_ms: int
    event_count: int
    event_set_sha256: str

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("funding evidence_id is required")
        if not _valid_sha256(self.content_sha256):
            raise ValueError("funding content_sha256 must be SHA-256")
        if not _valid_sha256(self.event_set_sha256):
            raise ValueError("funding event_set_sha256 must be SHA-256")
        if (
            type(self.coverage_start_ms) is not int
            or type(self.coverage_end_ms) is not int
            or type(self.event_count) is not int
        ):
            raise TypeError("funding coverage boundaries and event_count must be integers")
        if self.coverage_start_ms <= 0 or self.coverage_end_ms <= self.coverage_start_ms:
            raise ValueError("funding coverage interval must be positive and increasing")
        if self.event_count < 0:
            raise ValueError("funding event_count must be nonnegative")
        canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def funding_event_set_sha256(events: Sequence[FundingSettlement]) -> str:
    """Canonical hash of a normalized funding settlement tuple (timestamp order)."""
    ordered = sorted(events, key=lambda item: item.timestamp_ms)
    return canonical_sha256([asdict(item) for item in ordered])


def load_and_validate_funding_evidence(
    evidence: EvidenceReference,
    *,
    expected_product: str,
    expected_start_ms: int,
    expected_end_ms: int,
    expected_identity: FundingIntervalIdentity,
) -> tuple[FundingSettlement, ...]:
    """Strictly reconstruct authoritative funding events from preregistered evidence.

    Every formal consumer (candidate run, benchmarks, cold execution replay)
    invokes this independently against the comparison's preregistered funding
    authority; no persisted event list is ever trusted as the source of truth.
    """
    if (
        expected_identity.coverage_start_ms != expected_start_ms
        or expected_identity.coverage_end_ms != expected_end_ms
    ):
        raise ValueError("funding interval identity coverage differs from the expected interval")
    if evidence.evidence_type != FORMAL_FUNDING_EVIDENCE_TYPE:
        raise ValueError("funding evidence must be FORMAL_FUNDING_SETTLEMENT_DATASET")
    if evidence.completeness is not EvidenceCompleteness.COMPLETE:
        raise ValueError("funding evidence must be COMPLETE for formal promotion")
    source = evidence.local_path()
    if source is None:
        raise ValueError("funding evidence must be local and replayable")
    raw_bytes = source.read_bytes()
    if hashlib.sha256(raw_bytes).hexdigest() != evidence.content_sha256:
        raise ValueError("funding evidence bytes differ from preregistered content hash")
    if (
        evidence.evidence_id != expected_identity.evidence_id
        or evidence.content_sha256 != expected_identity.content_sha256
    ):
        raise ValueError("funding evidence differs from the preregistered comparison authority")
    document = json.loads(
        raw_bytes.decode("utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )
    if not isinstance(document, dict) or set(document) != _FUNDING_EVIDENCE_KEYS:
        raise ValueError("funding evidence schema mismatch")
    if document["schema_version"] != FORMAL_FUNDING_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("unsupported funding evidence schema version")
    if document["product"] != expected_product:
        raise ValueError("funding evidence product differs from the comparison product")
    coverage_start = document["coverage_start_ms"]
    coverage_end = document["coverage_end_ms"]
    if (
        type(coverage_start) is not int
        or type(coverage_end) is not int
        or type(coverage_start) is bool
        or type(coverage_end) is bool
        or coverage_start <= 0
        or coverage_end <= coverage_start
    ):
        raise ValueError("funding evidence coverage must be a positive increasing interval")
    # Coverage must exactly equal the comparison data interval; supersets are
    # rejected so the evidence preimage cannot drift from the comparison.
    if coverage_start != expected_start_ms or coverage_end != expected_end_ms:
        raise ValueError("funding evidence coverage differs from the comparison interval")
    raw_events = document["events"]
    if not isinstance(raw_events, list):
        raise TypeError("funding evidence events must be a list")
    events: list[FundingSettlement] = []
    previous_timestamp: int | None = None
    for item in raw_events:
        if not isinstance(item, dict) or set(item) != _FUNDING_EVENT_KEYS:
            raise ValueError("funding event schema mismatch")
        timestamp = item["timestamp_ms"]
        if type(timestamp) is not int or type(timestamp) is bool or timestamp <= 0:
            raise ValueError("funding event timestamp must be a positive integer")
        if timestamp < coverage_start or timestamp > coverage_end:
            raise ValueError("funding event lies outside the declared coverage")
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            raise ValueError("funding events must be strictly increasing in time")
        previous_timestamp = timestamp
        events.append(
            FundingSettlement(
                timestamp_ms=timestamp,
                funding_rate=_finite_number(item["funding_rate"], "funding_rate"),
                mark_price=_finite_number(item["mark_price"], "mark_price", positive=True),
            )
        )
    if len(events) != expected_identity.event_count:
        raise ValueError("funding evidence event count differs from preregistered identity")
    if funding_event_set_sha256(events) != expected_identity.event_set_sha256:
        raise ValueError("funding event set differs from the preregistered identity")
    return tuple(events)
