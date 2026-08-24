from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from ..domain import Candle

INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
}


@dataclass(frozen=True)
class QualityReport:
    valid: bool
    issues: tuple[str, ...]


def validate_candles(
    candles: Sequence[Candle], interval: str, now_ms: int | None = None, grace_ms: int = 120_000
) -> QualityReport:
    issues: list[str] = []
    expected = INTERVAL_MS.get(interval)
    if expected is None:
        return QualityReport(False, (f"unsupported interval: {interval}",))
    if not candles:
        return QualityReport(False, ("no candles",))
    opens = [bar.open_time_ms for bar in candles]
    if opens != sorted(opens):
        issues.append("timestamp disorder")
    if len(opens) != len(set(opens)):
        issues.append("duplicate candle")
    for previous, current in pairwise(candles):
        if current.open_time_ms - previous.open_time_ms != expected:
            issues.append(f"missing candle before {current.open_time_ms}")
            break
    if any(not bar.closed for bar in candles):
        issues.append("open candle present")
    if any(bar.interval != interval for bar in candles):
        issues.append("interval mismatch")
    if now_ms is not None:
        if candles[-1].close_time_ms > now_ms:
            issues.append("future candle")
        if now_ms - candles[-1].close_time_ms > expected + grace_ms:
            issues.append("latest candle stale")
    return QualityReport(not issues, tuple(issues))
