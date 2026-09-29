"""Post-event economic reference marks, isolated from candidate generation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

import numpy as np

from .authority import CANDIDATES, CANDIDATES_BY_ID
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


def calibration_matrices(
    batches: tuple[EventBatch, ...], outcomes: tuple[tuple[EventOutcome, ...], ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Build frozen shared-clock Z/A matrices from already committed events."""
    if len(batches) != 20 or len(outcomes) != 20:
        raise ValueError("complete frozen 20-candidate roster required")
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
