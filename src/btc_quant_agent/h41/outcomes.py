"""Post-event economic reference marks, isolated from candidate generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol
from weakref import WeakKeyDictionary

import numpy as np

from .authority import CANDIDATES, CANDIDATES_BY_ID, canonical_sha256
from .provenance import H41ProvenanceEventBatch, H41VerifiedSourceContext, _outcome_source
from .science import HOUR_MS, PARTITIONS, EventBatch


class OpenReferenceMarks(Protocol):
    """A separate, post-commit mark interface; never an event-generator input."""

    def open_at(self, symbol: str, open_time_ms: int) -> Decimal: ...


@dataclass(frozen=True, slots=True)
class EventOutcome:
    decision_time_ms: int
    primary_net: float
    stress_net_diagnostic: float


def materialize_outcomes(batch: EventBatch, marks: OpenReferenceMarks) -> tuple[EventOutcome, ...]:
    """Non-authoritative scalar helper; production uses materialize_context_outcomes."""
    if type(batch) is not EventBatch:
        raise TypeError("synthetic EventBatch required by scalar outcome helper")
    candidate = CANDIDATES_BY_ID[batch.candidate_id]
    results: list[EventOutcome] = []
    for event in batch.events:
        entry = marks.open_at(candidate.target_asset, event.decision_time_ms)
        exit_ = marks.open_at(candidate.target_asset,
                              event.decision_time_ms + event.horizon_hours * HOUR_MS)
        if not (entry.is_finite() and exit_.is_finite() and entry > 0 and exit_ > 0):
            raise ValueError("missing or invalid economic reference Open")
        signed = float(event.side * (exit_ / entry - Decimal(1)))
        results.append(EventOutcome(event.decision_time_ms, signed - .0012,
                                    signed - .0024))
    return tuple(results)


def _outcome_hash(values: tuple[EventOutcome, ...]) -> str:
    return canonical_sha256([
        (value.decision_time_ms, value.primary_net.hex(), value.stress_net_diagnostic.hex())
        for value in values
    ])


@dataclass(frozen=True, slots=True, eq=False, weakref_slot=True, init=False)
class H41ProvenanceOutcomeBatch:
    candidate_id: str
    partition: str
    authority_kind: str
    source_context_id: str
    event_population_hash: str
    outcome_population_hash: str
    outcomes: tuple[EventOutcome, ...]
    _context: H41VerifiedSourceContext = field(repr=False)
    _batch: H41ProvenanceEventBatch = field(repr=False)

    def assert_intact(self) -> None:
        if type(self) is not H41ProvenanceOutcomeBatch:
            raise TypeError("exact H41 outcome population required")
        recorded = _OUTCOME_REGISTRY.get(self)
        if recorded is None or _outcome_fields(self) != recorded:
            raise ValueError("unregistered or altered H41 outcome population")
        H41VerifiedSourceContext.assert_intact(self._context)
        H41ProvenanceEventBatch.assert_intact(self._batch)
        if (self._context is not self._batch._context
                or self.source_context_id != self._batch.source_context_id
                or self.event_population_hash != self._batch.event_population_hash
                or self.outcome_population_hash != _outcome_hash(self.outcomes)):
            raise ValueError("H41 outcome source or population integrity mismatch")


def _outcome_fields(batch: H41ProvenanceOutcomeBatch) -> tuple[object, ...]:
    return (batch.candidate_id, batch.partition, batch.authority_kind,
            batch.source_context_id, batch.event_population_hash,
            batch.outcome_population_hash, batch.outcomes, batch._context, batch._batch)


_OUTCOME_REGISTRY: WeakKeyDictionary[
    H41ProvenanceOutcomeBatch, tuple[object, ...]
] = WeakKeyDictionary()


def materialize_context_outcomes(
    batch: H41ProvenanceEventBatch, context: H41VerifiedSourceContext,
) -> H41ProvenanceOutcomeBatch:
    """Read both Open marks from the exact source that committed the event mask."""
    if type(batch) is not H41ProvenanceEventBatch:
        raise TypeError("source-bound event population required")
    if type(context) is not H41VerifiedSourceContext:
        raise TypeError("verified outcome source context required")
    H41ProvenanceEventBatch.assert_intact(batch)
    H41VerifiedSourceContext.assert_intact(context)
    if batch._context is not context or batch.source_context_id != context.source_context_id:
        raise ValueError("event and outcome source context mismatch")
    values = materialize_outcomes(batch.batch, _outcome_source(context))
    H41VerifiedSourceContext.assert_intact(context)
    result = object.__new__(H41ProvenanceOutcomeBatch)
    for name, value in (
        ("candidate_id", batch.candidate_id), ("partition", batch.partition),
        ("authority_kind", batch.authority_kind),
        ("source_context_id", batch.source_context_id),
        ("event_population_hash", batch.event_population_hash),
        ("outcome_population_hash", _outcome_hash(values)),
        ("outcomes", values), ("_context", context), ("_batch", batch),
    ):
        object.__setattr__(result, name, value)
    _OUTCOME_REGISTRY[result] = _outcome_fields(result)
    H41ProvenanceOutcomeBatch.assert_intact(result)
    return result


def calibration_matrices(
    batches: tuple[EventBatch, ...], outcomes: tuple[tuple[EventOutcome, ...], ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Build frozen shared-clock Z/A matrices from already committed events."""
    if len(batches) != 20 or len(outcomes) != 20:
        raise ValueError("complete frozen 20-candidate roster required")
    if any(type(batch) is not EventBatch for batch in batches):
        raise TypeError("synthetic EventBatch required by scalar matrix helper")
    start, end = PARTITIONS["WF1_CALIBRATION"]
    t_hours = (end - start) // HOUR_MS
    if t_hours != 2184:
        raise ValueError("frozen calibration clock drift")
    z = np.zeros((20, t_hours), dtype=np.float64)
    a = np.zeros((20, t_hours), dtype=np.float64)
    for index, (candidate, batch, values) in enumerate(zip(CANDIDATES, batches, outcomes, strict=True)):
        if batch.candidate_id != candidate.candidate_id or batch.partition != "WF1_CALIBRATION":
            raise ValueError("candidate order or partition mismatch")
        if len(batch.events) != len(values):
            raise ValueError("outcome population mismatch")
        for event, value in zip(batch.events, values, strict=True):
            if event.decision_time_ms != value.decision_time_ms or not np.isfinite(value.primary_net):
                raise ValueError("outcome lineage or value mismatch")
            clock = (event.decision_time_ms - start) // HOUR_MS
            z[index, clock] = value.primary_net
            a[index, clock] = 1
    return z, a


def calibration_context_matrices(
    batches: tuple[H41ProvenanceEventBatch, ...],
    outcomes: tuple[H41ProvenanceOutcomeBatch, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Check one source/fit lineage before materializing the frozen 20x2184 clock."""
    if len(batches) != 20 or len(outcomes) != 20:
        raise ValueError("complete frozen provenance roster required")
    context = batches[0]._context
    fit_id: str | None = None
    for candidate, batch, result in zip(CANDIDATES, batches, outcomes, strict=True):
        if type(batch) is not H41ProvenanceEventBatch or type(result) is not H41ProvenanceOutcomeBatch:
            raise TypeError("source-bound event and outcome populations required")
        H41ProvenanceEventBatch.assert_intact(batch)
        H41ProvenanceOutcomeBatch.assert_intact(result)
        if (batch.candidate_id != candidate.candidate_id
                or batch.partition != "WF1_CALIBRATION"
                or result.candidate_id != candidate.candidate_id
                or result.partition != "WF1_CALIBRATION"
                or batch._context is not context or result._context is not context
                or batch.source_context_id != context.source_context_id
                or batch.frozen_semantic_root != context.frozen_semantic_root
                or batch.candidate_ledger_hash != context.candidate_ledger_hash
                or result.event_population_hash != batch.event_population_hash):
            raise ValueError("calibration source context, roster, or partition mismatch")
        if batch.train_fit_seal_id is not None:
            if fit_id is None:
                fit_id = batch.train_fit_seal_id
            elif batch.train_fit_seal_id != fit_id:
                raise ValueError("mixed calibration TRAIN fit authority")
    H41VerifiedSourceContext.assert_intact(context)
    return calibration_matrices(tuple(batch.batch for batch in batches),
                                tuple(result.outcomes for result in outcomes))
