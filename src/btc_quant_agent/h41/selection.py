"""Pure deterministic ranking; creates no Candidate Lock or side effect."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from .authority import CANDIDATES_BY_ID


@dataclass(frozen=True, slots=True)
class CandidateInference:
    candidate_id: str
    simultaneous_lcb: float
    event_count_N: int
    mu_hat: float
    occupied_calendar_days_D: int


def rank_positive_lcb(rows: Iterable[CandidateInference]) -> tuple[CandidateInference, ...]:
    seen: set[str] = set()
    eligible: list[CandidateInference] = []
    for row in rows:
        if row.candidate_id not in CANDIDATES_BY_ID or row.candidate_id in seen:
            raise ValueError("foreign or duplicate candidate")
        if row.event_count_N < 0 or row.occupied_calendar_days_D < 0:
            raise ValueError("negative support count")
        seen.add(row.candidate_id)
        if (row.event_count_N >= 60 and row.occupied_calendar_days_D >= 30
                and math.isfinite(row.mu_hat)
                and math.isfinite(row.simultaneous_lcb) and row.simultaneous_lcb > 0):
            eligible.append(row)
    if seen != CANDIDATES_BY_ID.keys():
        raise ValueError("complete frozen candidate roster required")
    return tuple(sorted(eligible, key=lambda row: (-row.simultaneous_lcb,
                                                    -row.event_count_N, row.candidate_id)))
