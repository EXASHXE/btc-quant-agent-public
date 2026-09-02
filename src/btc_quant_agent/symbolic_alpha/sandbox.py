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


@dataclass(frozen=True)
class ReplayBar:
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class SandboxTrade:
    signal_id: str
    direction: str
    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    exit_price: float
    exit_reason: str
    gross_r: float
    fees_r: float
    slippage_r: float
    funding_r: float
    net_r: float


def replay_signal(
    signal: ProvisionalSignal,
    bars: list[ReplayBar],
    *,
    fee_rate: float,
    slippage_rate: float,
    funding_r: float = 0.0,
) -> SandboxTrade | None:
    """Replay a frozen signal using only bars strictly after its decision timestamp."""
    if signal.decision == SandboxDecision.WAIT:
        return None
    if signal.entry_price is None or signal.stop_price is None or signal.take_profit_price is None:
        raise ValueError("directional signal requires frozen entry, stop, and take-profit")
    eligible = [bar for bar in bars if bar.open_time_ms > signal.decision_timestamp_ms]
    if not eligible:
        return None
    side = 1.0 if signal.decision == SandboxDecision.LONG else -1.0
    risk = side * (signal.entry_price - signal.stop_price)
    if risk <= 0:
        raise ValueError("stop must define positive directional risk")
    entry_bar = eligible[0]
    entry = entry_bar.open
    exit_price = eligible[-1].close
    exit_time = eligible[-1].close_time_ms
    reason = "END_OF_REPLAY"
    for bar in eligible:
        stop_hit = bar.low <= signal.stop_price if side > 0 else bar.high >= signal.stop_price
        target_hit = (
            bar.high >= signal.take_profit_price
            if side > 0
            else bar.low <= signal.take_profit_price
        )
        if stop_hit:
            exit_price = signal.stop_price
            exit_time = bar.close_time_ms
            reason = "STOP" if not target_hit else "STOP_AND_TARGET_SAME_BAR_CONSERVATIVE_STOP"
            break
        if target_hit:
            exit_price = signal.take_profit_price
            exit_time = bar.close_time_ms
            reason = "TAKE_PROFIT"
            break
    gross_r = side * (exit_price - entry) / risk
    fees_r = fee_rate * (entry + exit_price) / risk
    slippage_r = slippage_rate * (entry + exit_price) / risk
    net_r = gross_r - fees_r - funding_r
    return SandboxTrade(
        signal.signal_id,
        signal.decision.value,
        entry_bar.open_time_ms,
        exit_time,
        entry,
        exit_price,
        reason,
        gross_r,
        fees_r,
        slippage_r,
        funding_r,
        net_r,
    )


def assert_shadow_start_is_valid(freeze_commit_time_ms: int, start_time_ms: int) -> None:
    if start_time_ms <= freeze_commit_time_ms:
        raise ValueError("candidate shadow start must be future-fixed after formula freeze")
