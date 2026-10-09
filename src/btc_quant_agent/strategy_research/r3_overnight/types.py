"""Type definitions for G2 R3 overnight discovery research sidecar."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any


class Direction(Enum):
    LONG = 1
    SHORT = -1

    @property
    def sign(self) -> int:
        return self.value


class CandidateFamily(Enum):
    STRUCTURAL_CONTINUATION = "STRUCTURAL_CONTINUATION"
    CLOSED_RETEST = "CLOSED_RETEST"


class Horizon(Enum):
    H4 = "04H"
    H12 = "12H"

    @property
    def holding_hours(self) -> int:
        return 4 if self == Horizon.H4 else 12

    @property
    def holding_minutes(self) -> int:
        return self.holding_hours * 60

    @property
    def holding_ms(self) -> int:
        return self.holding_minutes * 60_000


class CostScenario(Enum):
    BASE = "BASE"
    STRESS = "STRESS"


class ExitReason(Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    EXPIRY = "EXPIRY"
    DRAWDOWN_KILL = "DRAWDOWN_KILL"
    MARK_STALENESS = "MARK_STALENESS"
    PRO_RATA_REDUCTION = "PRO_RATA_REDUCTION"


@dataclass(frozen=True)
class Bar1m:
    """Canonical 1-minute OHLCV bar."""
    timestamp_ms: int  # Bar open epoch millisecond
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    symbol: str

    @property
    def close_ms(self) -> int:
        return self.timestamp_ms + 60_000


@dataclass(frozen=True)
class Bar1h:
    """Canonical 1-hour OHLCV bar aggregated from 60 1m bars."""
    timestamp_ms: int  # Hour open epoch millisecond
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    symbol: str
    bar_count: int

    @property
    def close_ms(self) -> int:
        return self.timestamp_ms + 3_600_000


@dataclass(frozen=True)
class Bar4h:
    """Canonical 4-hour OHLCV bar aggregated from 240 1m bars."""
    timestamp_ms: int  # 4h open epoch millisecond
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    symbol: str
    bar_count: int

    @property
    def close_ms(self) -> int:
        return self.timestamp_ms + 14_400_000


@dataclass(frozen=True)
class MarkBar1m:
    """Mark price 1-minute bar for mark-to-market valuation."""
    timestamp_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    symbol: str
    available_at_ms: int  # When this mark became available to the book

    @property
    def close_ms(self) -> int:
        return self.timestamp_ms + 60_000


@dataclass(frozen=True)
class SymbolFilters:
    """Exchange tick size and lot size filters."""
    symbol: str
    tick_size: Decimal
    step_size: Decimal  # Lot size
    min_notional: Decimal = Decimal("5.0")


@dataclass(frozen=True)
class CandidateDefinition:
    """Static configuration of one of the 8 candidates."""
    id: str
    family: CandidateFamily
    direction: Direction
    horizon: Horizon
    symbols: tuple[str, ...]
    status: str = "PROPOSED_NOT_REGISTERED_NOT_EVALUATED"

    @property
    def holding_minutes(self) -> int:
        return self.horizon.holding_minutes

    @property
    def holding_ms(self) -> int:
        return self.horizon.holding_ms


@dataclass
class SignalEvent:
    """Signal produced at an hourly decision close."""
    candidate_id: str
    symbol: str
    direction: Direction
    decision_time_ms: int  # Exclusive hour end
    available_at_ms: int  # decision_time_ms + 60s
    decision_close: Decimal
    hourly_atr20: Decimal
    proposed_stop: Decimal
    earliest_entry_ms: int  # decision_time_ms + 120s (following minute open)
    event_id: str  # Unique event identity (symbol, direction, timestamp)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class VirtualOrder:
    """Order submitted to the virtual execution book."""
    order_id: str
    candidate_id: str
    symbol: str
    direction: Direction
    quantity: Decimal
    target_fill_time_ms: int  # Minute open when order is due
    created_at_ms: int  # When order was created (<= target_fill_time - 60s)
    expected_entry_bound: Decimal  # Adverse price bound X
    initial_stop: Decimal
    target: Decimal
    cost_commitment_usdt: Decimal
    funding_reserve_usdt: Decimal
    decision_close: Decimal = Decimal(0)
    hourly_atr20: Decimal = Decimal(0)
    retest_event_id: str | None = None


@dataclass
class VirtualFill:
    """Executed trade fill."""
    fill_id: str
    order_id: str
    candidate_id: str
    symbol: str
    direction: Direction
    quantity: Decimal
    raw_price: Decimal
    effective_price: Decimal  # Includes embedded spread + slippage
    fee_usdt: Decimal  # Taker fee debited separately
    fill_time_ms: int
    available_at_ms: int  # fill_time_ms + 60s
    initial_stop: Decimal
    target: Decimal
    retest_event_id: str | None = None


@dataclass
class Position:
    """Active open position in virtual book."""
    position_id: str
    candidate_id: str
    symbol: str
    direction: Direction
    quantity: Decimal
    effective_entry: Decimal
    entry_time_ms: int
    entry_available_at_ms: int
    stop: Decimal
    target: Decimal
    max_hold_ms: int
    cost_commitment_exit_usdt: Decimal
    retest_event_id: str | None = None
    funding_reserves_usdt: Decimal = Decimal(0)
    total_funding_charged_usdt: Decimal = Decimal(0)
    is_acknowledged: bool = False

    @property
    def expiry_time_ms(self) -> int:
        return self.entry_time_ms + self.max_hold_ms


@dataclass
class CompletedTrade:
    """Closed trade record with full economic reconciliation."""
    trade_id: str
    candidate_id: str
    symbol: str
    direction: Direction
    quantity: Decimal
    effective_entry: Decimal
    raw_entry: Decimal
    effective_exit: Decimal
    raw_exit: Decimal
    entry_time_ms: int
    exit_time_ms: int
    holding_minutes: int
    exit_reason: ExitReason
    entry_fee_usdt: Decimal
    exit_fee_usdt: Decimal
    total_fees_usdt: Decimal
    total_funding_usdt: Decimal
    gross_pnl_usdt: Decimal
    net_pnl_usdt: Decimal
    entry_notional_usdt: Decimal
    initial_risk_dollars: Decimal
    net_bps: Decimal
    net_r: Decimal | None
    retest_event_id: str | None = None


@dataclass
class FundingEventRecord:
    """Historical or proxy funding settlement charge."""
    event_id: str
    symbol: str
    settlement_time_ms: int
    rate: Decimal
    settlement_mark: Decimal
    position_quantity: Decimal
    cashflow_debit_usdt: Decimal
    charged_at_ms: int
    available_at_ms: int
