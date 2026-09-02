from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SandboxDecision(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    WAIT = "WAIT"


@dataclass(frozen=True)
class ProvisionalSignal:
    signal_id: str
    decision_timestamp_ms: int
    decision: SandboxDecision
    formula_hash: str
    source: str
    entry_price: float | None
    stop_price: float | None
    take_profit_price: float | None
    size: float
    runtime_actionable: bool = False
    execution: str = "DISABLED"
    validation_status: str = "PROVISIONAL_SANDBOX_ONLY"

    def __post_init__(self) -> None:
        if self.runtime_actionable or self.execution != "DISABLED":
            raise ValueError("provisional signals must remain non-actionable and execution-disabled")
        if self.source not in {
            "HISTORICAL_PROXY",
            "CANONICAL_HISTORICAL",
            "OFFICIAL_HISTORICAL_TIMESTAMPED",
        }:
            raise ValueError("provisional signal source must be an audited historical role")
        if self.decision == SandboxDecision.WAIT:
            if any(value is not None for value in (self.entry_price, self.stop_price, self.take_profit_price)):
                raise ValueError("WAIT cannot carry entry, stop, or target")
            if self.size != 0:
                raise ValueError("WAIT size must be zero")


def assert_shadow_start_is_valid(freeze_commit_time_ms: int, start_time_ms: int) -> None:
    if start_time_ms <= freeze_commit_time_ms:
        raise ValueError("candidate shadow start must be future-fixed after formula freeze")

