"""H41 event construction from completed bars only.

Reference Open marks are deliberately absent from every input type here.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np

from .authority import CANDIDATES_BY_ID, Candidate

HOUR_MS = 3_600_000


def _ms(value: str) -> int:
    return int(datetime.fromisoformat(value).timestamp() * 1000)


PARTITIONS = {
    "WF1_TRAIN": (_ms("2021-01-01T00:00:00Z"), _ms("2022-10-31T00:00:00Z")),
    "WF1_PURGE_1": (_ms("2022-10-31T00:00:00Z"), _ms("2022-11-01T00:00:00Z")),
    "WF1_CALIBRATION": (_ms("2022-11-01T00:00:00Z"), _ms("2023-01-31T00:00:00Z")),
    "WF1_PURGE_2": (_ms("2023-01-31T00:00:00Z"), _ms("2023-02-01T00:00:00Z")),
    "WF1_VALIDATION": (_ms("2023-02-01T00:00:00Z"), _ms("2023-04-30T00:00:00Z")),
    "SOURCE_RESERVE": (_ms("2023-04-30T00:00:00Z"), _ms("2023-05-01T00:00:00Z")),
}


@dataclass(frozen=True, slots=True)
class CompletedBar:
    open_time_ms: int
    high: float
    low: float
    close: float


@dataclass(frozen=True, slots=True)
class CompletedPairView:
    """Newest-first, synchronized completed-bar history at one decision boundary."""

    decision_time_ms: int
    btc: tuple[CompletedBar, ...]
    eth: tuple[CompletedBar, ...]

    def __post_init__(self) -> None:
        if self.decision_time_ms % HOUR_MS:
            raise ValueError("decision boundary is not a UTC hour")
        if len(self.btc) != len(self.eth) or not self.btc:
            raise ValueError("missing synchronized bars")
        for index, (btc, eth) in enumerate(zip(self.btc, self.eth, strict=True)):
            expected = self.decision_time_ms - (index + 1) * HOUR_MS
            if btc.open_time_ms != expected or eth.open_time_ms != expected:
                raise ValueError("missing, future, or nonconsecutive completed bar")
            for bar in (btc, eth):
                if not (math.isfinite(bar.high) and math.isfinite(bar.low)
                        and math.isfinite(bar.close) and 0 < bar.low <= bar.close <= bar.high):
                    raise ValueError("invalid completed OHLC")

    def bars_for(self, asset: str) -> tuple[CompletedBar, ...]:
        if asset == "BTCUSDT":
            return self.btc
        if asset == "ETHUSDT":
            return self.eth
        raise ValueError("unknown asset")


def _score_d1(bars: tuple[CompletedBar, ...], window: int) -> float:
    if len(bars) <= window:
        raise ValueError("incomplete D1 lookback")
    return math.log(bars[0].close / bars[window].close)


def _linear_q80(scores: list[float]) -> float:
    if len(scores) < 500:
        raise ValueError("D1 Q80 requires at least 500 valid TRAIN scores")
    return float(np.quantile(np.asarray(scores), .80, method="linear"))


def train_q80(candidate: Candidate, views: Iterable[CompletedPairView]) -> float:
    """Freeze Q80 over the complete valid WF1_TRAIN decision clock."""
    if candidate.family != "D1_TREND":
        raise ValueError("Q80 applies to D1 only")
    scores: list[float] = []
    expected = PARTITIONS["WF1_TRAIN"][0] + (candidate.lookback_window_hours + 1) * HOUR_MS
    for view in views:
        if view.decision_time_ms != expected or expected >= PARTITIONS["WF1_TRAIN"][1]:
            raise ValueError("Q80 requires complete ordered WF1_TRAIN clock")
        scores.append(abs(_score_d1(view.bars_for(candidate.target_asset),
                                    candidate.lookback_window_hours)))
        expected += HOUR_MS
    if expected != PARTITIONS["WF1_TRAIN"][1]:
        raise ValueError("Q80 requires complete ordered WF1_TRAIN clock")
    return _linear_q80(scores)


def candidate_side(candidate: Candidate, view: CompletedPairView,
                   q80_by_id: Mapping[str, float]) -> int:
    t = view.decision_time_ms
    if not (PARTITIONS["WF1_TRAIN"][0] <= t < PARTITIONS["WF1_TRAIN"][1]
            or PARTITIONS["WF1_CALIBRATION"][0] <= t < PARTITIONS["WF1_CALIBRATION"][1]):
        raise ValueError("protected or source-only partition is not scientific input")
    if CANDIDATES_BY_ID.get(candidate.candidate_id) != candidate:
        raise ValueError("candidate differs from frozen ledger")
    bars = view.bars_for(candidate.target_asset)
    w = candidate.lookback_window_hours
    if candidate.family == "D1_TREND":
        score = _score_d1(bars, w)
        threshold = q80_by_id[candidate.candidate_id]
        if not math.isfinite(threshold) or threshold < 0:
            raise ValueError("invalid frozen Q80")
        return (1 if score > 0 else -1) if score != 0 and abs(score) >= threshold else 0
    if candidate.family == "D2_BREAKOUT":
        if len(bars) <= w:
            raise ValueError("incomplete D2 lookback")
        upper = max(bar.high for bar in bars[1:w + 1])
        lower = min(bar.low for bar in bars[1:w + 1])
        return 1 if bars[0].close > upper else -1 if bars[0].close < lower else 0
    if candidate.family == "D3_FAILED_BREAK":
        if len(bars) <= w + 1:
            raise ValueError("incomplete D3 lookback")
        upper = max(bar.high for bar in bars[2:w + 2])
        lower = min(bar.low for bar in bars[2:w + 2])
        inside = lower < bars[0].close < upper
        return -1 if inside and bars[1].close > upper else 1 if inside and bars[1].close < lower else 0
    if candidate.family == "D4_MODIFIER":
        if candidate.parent_id is None:
            raise ValueError("D4 parent missing from frozen ledger")
        parent_side = candidate_side(CANDIDATES_BY_ID[candidate.parent_id], view, q80_by_id)
        other = view.eth if candidate.target_asset == "BTCUSDT" else view.btc
        if len(other) <= 4:
            raise ValueError("incomplete synchronized other RET4")
        score = math.log(other[0].close / other[4].close)
        other_side = 1 if score > 0 else -1 if score < 0 else 0
        if parent_side == 0 or other_side == 0:
            return 0
        matches = parent_side == other_side
        return parent_side if matches == (candidate.modifier_type == "CONFIRM") else 0
    raise ValueError("unknown frozen candidate family")


@dataclass(frozen=True, slots=True)
class Event:
    decision_time_ms: int
    side: int
    horizon_hours: int

    def __post_init__(self) -> None:
        if self.side not in (-1, 1) or self.horizon_hours not in (4, 8, 24):
            raise ValueError("invalid event side or horizon")


@dataclass(frozen=True, slots=True)
class EventBatch:
    candidate_id: str
    partition: str
    events: tuple[Event, ...]

    def __post_init__(self) -> None:
        candidate = CANDIDATES_BY_ID.get(self.candidate_id)
        if candidate is None or self.partition not in ("WF1_TRAIN", "WF1_CALIBRATION"):
            raise ValueError("unregistered candidate or unavailable scientific partition")
        start, end = PARTITIONS[self.partition]
        seen: set[int] = set()
        for event in self.events:
            if (event.horizon_hours != candidate.horizon_hours
                    or not start <= event.decision_time_ms < end
                    or event.decision_time_ms + event.horizon_hours * HOUR_MS > end
                    or event.decision_time_ms in seen):
                raise ValueError("event outside frozen partition or duplicate")
            seen.add(event.decision_time_ms)
        if tuple(sorted(seen)) != tuple(e.decision_time_ms for e in self.events):
            raise ValueError("events not ordered")


def build_event_batch(candidate: Candidate, views: Iterable[CompletedPairView],
                      q80_by_id: Mapping[str, float], partition: str) -> EventBatch:
    if partition not in ("WF1_TRAIN", "WF1_CALIBRATION"):
        raise ValueError("protected or source-only partition")
    if CANDIDATES_BY_ID.get(candidate.candidate_id) != candidate:
        raise ValueError("candidate differs from frozen ledger")
    start, end = PARTITIONS[partition]
    events: list[Event] = []
    if candidate.family == "D3_FAILED_BREAK":
        oldest_index = candidate.lookback_window_hours + 1
    else:
        oldest_index = candidate.lookback_window_hours
    expected = start if partition == "WF1_CALIBRATION" else start + (oldest_index + 1) * HOUR_MS
    for view in views:
        t = view.decision_time_ms
        if t != expected or expected >= end:
            raise ValueError("event mask requires complete ordered partition clock")
        expected += HOUR_MS
        if t + candidate.horizon_hours * HOUR_MS > end:
            continue
        side = candidate_side(candidate, view, q80_by_id)
        if side:
            events.append(Event(t, side, candidate.horizon_hours))
    if expected != end:
        raise ValueError("event mask requires complete ordered partition clock")
    return EventBatch(candidate.candidate_id, partition, tuple(events))


def occupied_days(batch: EventBatch) -> int:
    return len({datetime.fromtimestamp(e.decision_time_ms / 1000, tz=UTC).date()
                for e in batch.events})
