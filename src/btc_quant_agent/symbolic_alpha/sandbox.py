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
    planned_entry_reference: float | None
    stop_price: float | None
    take_profit_price: float | None
    size: float
    runtime_actionable: bool = False
    execution: str = "DISABLED"
    validation_status: str = "PROVISIONAL_SANDBOX_ONLY"

    def __post_init__(self) -> None:
        if self.runtime_actionable or self.execution != "DISABLED":
            raise ValueError(
                "provisional signals must remain non-actionable and execution-disabled"
            )
        if self.source not in {
            "HISTORICAL_PROXY",
            "CANONICAL_HISTORICAL",
            "OFFICIAL_HISTORICAL_TIMESTAMPED",
        }:
            raise ValueError("provisional signal source must be an audited historical role")
        if self.decision == SandboxDecision.WAIT:
            if any(
                value is not None
                for value in (
                    self.planned_entry_reference,
                    self.stop_price,
                    self.take_profit_price,
                )
            ):
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
    planned_entry_reference: float
    raw_entry_price: float
    executed_entry_price: float
    raw_exit_price: float
    executed_exit_price: float
    exit_reason: str
    gross_r: float
    fees_r: float
    slippage_r: float
    funding_r: float
    net_r: float
    size: float
    pnl_quote: float


@dataclass(frozen=True)
class SettledFunding:
    timestamp_ms: int
    rate: float


def replay_signal(
    signal: ProvisionalSignal,
    bars: list[ReplayBar],
    *,
    fee_rate: float,
    slippage_rate: float,
    funding_events: tuple[SettledFunding, ...] = (),
) -> SandboxTrade | None:
    """Replay a frozen signal using only bars strictly after its decision timestamp."""
    if signal.decision == SandboxDecision.WAIT:
        return None
    if (
        signal.planned_entry_reference is None
        or signal.stop_price is None
        or signal.take_profit_price is None
    ):
        raise ValueError("directional signal requires frozen entry, stop, and take-profit")
    eligible = [bar for bar in bars if bar.open_time_ms > signal.decision_timestamp_ms]
    if not eligible:
        return None
    side = 1.0 if signal.decision == SandboxDecision.LONG else -1.0
    entry_bar = eligible[0]
    raw_entry = entry_bar.open
    executed_entry = raw_entry * (1 + side * slippage_rate)
    risk = abs(executed_entry - signal.stop_price)
    if risk <= 0:
        raise ValueError("actual executed entry and frozen stop define zero risk")
    raw_exit = eligible[-1].close
    exit_time = eligible[-1].close_time_ms
    reason = "END_OF_REPLAY"
    gap_through = raw_entry <= signal.stop_price if side > 0 else raw_entry >= signal.stop_price
    if gap_through:
        raw_exit = raw_entry
        exit_time = entry_bar.open_time_ms
        reason = "GAP_THROUGH_STOP_AT_FIRST_OPEN"
    for bar in eligible:
        if gap_through:
            break
        stop_hit = bar.low <= signal.stop_price if side > 0 else bar.high >= signal.stop_price
        target_hit = (
            bar.high >= signal.take_profit_price
            if side > 0
            else bar.low <= signal.take_profit_price
        )
        if stop_hit:
            raw_exit = signal.stop_price
            exit_time = bar.close_time_ms
            reason = "STOP" if not target_hit else "STOP_AND_TARGET_SAME_BAR_CONSERVATIVE_STOP"
            break
        if target_hit:
            raw_exit = signal.take_profit_price
            exit_time = bar.close_time_ms
            reason = "TAKE_PROFIT"
            break
    executed_exit = raw_exit * (1 - side * slippage_rate)
    gross_r = side * (raw_exit - raw_entry) / risk
    fees_r = fee_rate * (executed_entry + executed_exit) / risk
    slippage_r = side * ((executed_entry - raw_entry) + (raw_exit - executed_exit)) / risk
    funding_r = sum(
        side * event.rate * executed_entry / risk
        for event in funding_events
        if entry_bar.open_time_ms < event.timestamp_ms <= exit_time
    )
    net_r = gross_r - fees_r - slippage_r - funding_r
    pnl_quote = net_r * risk * signal.size
    return SandboxTrade(
        signal.signal_id,
        signal.decision.value,
        entry_bar.open_time_ms,
        exit_time,
        signal.planned_entry_reference,
        raw_entry,
        executed_entry,
        raw_exit,
        executed_exit,
        reason,
        gross_r,
        fees_r,
        slippage_r,
        funding_r,
        net_r,
        signal.size,
        pnl_quote,
    )


def assert_shadow_start_is_valid(freeze_commit_time_ms: int, start_time_ms: int) -> None:
    if start_time_ms <= freeze_commit_time_ms:
        raise ValueError("candidate shadow start must be future-fixed after formula freeze")
