"""Immutable data models, records, and enums for r3_alt_engine."""

from collections.abc import Mapping
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


class OwnerPhase(Enum):
    FLAT = "FLAT"
    RESERVED = "RESERVED"
    UNACKED_OPEN = "UNACKED_OPEN"
    ACKED_OPEN = "ACKED_OPEN"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED_UNSETTLED = "CLOSED_UNSETTLED"
    COOLDOWN = "COOLDOWN"


class ExitReason(Enum):
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    EXPIRY = "EXPIRY"
    DRAWDOWN_KILL = "DRAWDOWN_KILL"
    MARK_STALENESS = "MARK_STALENESS"
    PRO_RATA_REDUCTION = "PRO_RATA_REDUCTION"


class FundingPhase(Enum):
    CONDITIONAL = "CONDITIONAL"
    FINAL = "FINAL"


class AccountType(Enum):
    CASH = "CASH"
    TRADE_RECEIVABLE = "TRADE_RECEIVABLE"
    TRADE_PAYABLE = "TRADE_PAYABLE"
    FEE_PAYABLE = "FEE_PAYABLE"
    FUNDING_PAYABLE = "FUNDING_PAYABLE"
    REALIZED_GAIN = "REALIZED_GAIN"
    REALIZED_LOSS = "REALIZED_LOSS"
    FEE_EXPENSE = "FEE_EXPENSE"
    FUNDING_EXPENSE = "FUNDING_EXPENSE"
    OPENING_EQUITY = "OPENING_EQUITY"


class MemoAccountType(Enum):
    ENC_NOTIONAL = "ENC_NOTIONAL"
    ENC_FEE = "ENC_FEE"
    ENC_EXIT_FEE = "ENC_EXIT_FEE"
    ENC_FUNDING = "ENC_FUNDING"
    ENC_SHORTFALL = "ENC_SHORTFALL"
    MEMO_CONTRA = "MEMO_CONTRA"


class EventKind(Enum):
    OBSERVED_MINUTE_BAR = "ObservedMinuteBar"
    OBSERVED_MARK = "ObservedMark"
    SIGNAL_AT_DECISION = "SignalAtDecision"
    ORDER_RESERVED = "OrderReserved"
    ECONOMIC_FILL = "EconomicFill"
    FILL_ACK = "FillAck"
    ECONOMIC_EXIT = "EconomicExit"
    EXIT_ACK = "ExitAck"
    FUNDING_OBLIGATION = "FundingObligation"
    FUNDING_ACK = "FundingAck"
    RISK_KILL = "RiskKill"
    END_OF_MINUTE_REPORT = "EndOfMinuteReport"


@dataclass(frozen=True)
class SymbolFilters:
    """Exchange tick size and lot size filters."""
    symbol: str
    tick_size: Decimal
    step_size: Decimal  # Lot size
    min_notional: Decimal = Decimal("5.0")


@dataclass(frozen=True)
class Bar1m:
    """Canonical 1-minute OHLCV bar."""
    timestamp_ms: int
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
    timestamp_ms: int
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
    timestamp_ms: int
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
    available_at_ms: int
    source_id: str = "SYNTHETIC_MARK"

    @property
    def close_ms(self) -> int:
        return self.timestamp_ms + 60_000


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


@dataclass(frozen=True)
class OwnerKey:
    """Unique financial owner coordinate."""
    book_id: str
    position_id: str
    settlement_id: str = ""

    def __str__(self) -> str:
        if self.settlement_id:
            return f"{self.book_id}:{self.position_id}:{self.settlement_id}"
        return f"{self.book_id}:{self.position_id}"


@dataclass(frozen=True)
class PendingExitSlice:
    """One discrete exit slice under an owner."""
    slice_id: str
    quantity: Decimal
    raw_price: Decimal
    effective_price: Decimal
    gross_pnl: Decimal
    exit_fee: Decimal
    exit_time_ms: int
    available_at_ms: int
    exit_reason: ExitReason
    is_loss: bool
    is_acknowledged: bool = False


@dataclass(frozen=True)
class Posting:
    """Immutable double-entry balance journal entry."""
    dr_account: AccountType | MemoAccountType
    cr_account: AccountType | MemoAccountType
    amount: Decimal
    owner_key: OwnerKey
    event_id: str
    is_memo: bool = False
    timestamp_ms: int = 0
    cause_id: str = ""


@dataclass(frozen=True)
class Event:
    """Immutable event envelope with strict causal identity."""
    event_id: str
    kind: EventKind
    book_id: str
    candidate_id: str
    symbol: str
    owner_key: OwnerKey
    order_id: str
    position_id: str
    fill_id: str
    settlement_id: str
    source_id: str
    cause_id: str
    economic_at_ms: int
    available_at_ms: int
    payload: Mapping[str, Any]
    payload_digest: str


@dataclass(frozen=True)
class OwnerLedger:
    """Owner-scoped financial and exposure subledger."""
    owner_key: OwnerKey
    candidate_id: str
    symbol: str
    direction: Direction | None
    phase: OwnerPhase
    cash_settled: Decimal = Decimal(0)
    trade_receivable: Decimal = Decimal(0)
    trade_payable: Decimal = Decimal(0)
    fee_payable: Decimal = Decimal(0)
    funding_payable: Decimal = Decimal(0)
    realized_gain: Decimal = Decimal(0)
    realized_loss: Decimal = Decimal(0)
    fee_expense: Decimal = Decimal(0)
    funding_expense: Decimal = Decimal(0)
    enc_notional: Decimal = Decimal(0)
    enc_fee: Decimal = Decimal(0)
    enc_exit_fee: Decimal = Decimal(0)
    enc_funding_future: Decimal = Decimal(0)
    enc_funding_dedicated: Decimal = Decimal(0)
    enc_shortfall: Decimal = Decimal(0)
    quantity: Decimal = Decimal(0)
    entry_price: Decimal = Decimal(0)
    entry_time_ms: int = 0
    initial_stop: Decimal = Decimal(0)
    target: Decimal = Decimal(0)
    max_hold_ms: int = 0
    pending_exit_slices: tuple[PendingExitSlice, ...] = ()
    is_tombstone: bool = False
    retest_event_id: str | None = None


@dataclass(frozen=True)
class RetestState:
    """Immutable state of an ongoing or completed breakout retest."""
    event_id: str
    symbol: str
    direction: Direction
    breakout_hour_ms: int
    boundary: Decimal
    frozen_atr: Decimal
    breakout_high: Decimal
    breakout_low: Decimal
    bars_since_breakout: int = 0
    intermediate_highs: tuple[Decimal, ...] = ()
    intermediate_lows: tuple[Decimal, ...] = ()
    confirmed: bool = False
    canceled: bool = False
    expired: bool = False
    last_advanced_hour_ms: int = 0
    consumed_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class Projection:
    """As-of capital, encumbrance, and risk valuation."""
    as_of_ms: int
    cash: Decimal
    acknowledged_live_mtm: Decimal
    unacked_live_mtm: Decimal
    visible_unpaid_exit_losses: Decimal
    visible_unpaid_fees: Decimal
    E_d: Decimal
    E_c: Decimal
    P_f: Decimal
    E_r: Decimal
    C_o: Decimal
    R_f: Decimal
    L_f: Decimal
    A_raw: Decimal
    A: Decimal
    B: Decimal
    peak_E_r: Decimal
    drawdown: Decimal
    killed: bool


@dataclass(frozen=True)
class SignalEvent:
    """Signal produced at an hourly decision close."""
    candidate_id: str
    symbol: str
    direction: Direction
    decision_time_ms: int
    available_at_ms: int
    decision_close: Decimal
    hourly_atr20: Decimal
    proposed_stop: Decimal
    earliest_entry_ms: int
    event_id: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VirtualOrder:
    """Order submitted to the execution engine."""
    order_id: str
    candidate_id: str
    symbol: str
    direction: Direction
    quantity: Decimal
    target_fill_time_ms: int
    created_at_ms: int
    expected_entry_bound: Decimal
    initial_stop: Decimal
    target: Decimal
    cost_commitment_usdt: Decimal
    funding_reserve_usdt: Decimal
    decision_close: Decimal = Decimal(0)
    hourly_atr20: Decimal = Decimal(0)
    retest_event_id: str | None = None


@dataclass(frozen=True)
class VirtualFill:
    """Trade fill execution."""
    fill_id: str
    order_id: str
    candidate_id: str
    symbol: str
    direction: Direction
    quantity: Decimal
    raw_price: Decimal
    effective_price: Decimal
    fee_usdt: Decimal
    fill_time_ms: int
    available_at_ms: int
    initial_stop: Decimal
    target: Decimal
    retest_event_id: str | None = None


@dataclass(frozen=True)
class CompletedTrade:
    """Closed trade record with economic reconciliation."""
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
    position_id: str = ""


@dataclass(frozen=True)
class EngineState:
    """Root immutable state of the replay engine."""
    clock_ms: int
    latest_mark_close_ms: int
    latest_marks: Mapping[str, Decimal] = field(default_factory=dict)
    owner_ledgers: Mapping[OwnerKey, OwnerLedger] = field(default_factory=dict)
    postings: tuple[Posting, ...] = ()
    retest_states: Mapping[tuple[str, str, Direction], RetestState] = field(default_factory=dict)
    cooldown_until: Mapping[tuple[str, str], int] = field(default_factory=dict)
    killed_latches: Mapping[str, bool] = field(default_factory=dict)
    peak_E_r: Mapping[str, Decimal] = field(default_factory=dict)
    journal_chain_hash: str = "0000000000000000000000000000000000000000000000000000000000000000"
    event_registry: Mapping[str, str] = field(default_factory=dict)  # event_id -> payload_digest
    source_close_marks: Mapping[tuple[str, str, int], Decimal] = field(default_factory=dict)
    consumed_retest_events: Mapping[str, frozenset[str]] = field(default_factory=dict)
    completed_trades: tuple[CompletedTrade, ...] = ()
    last_entry_4h_time_ms: Mapping[str, int] = field(default_factory=dict)
    opening_equity_posted: Mapping[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayConfig:
    """Configuration for synthetic simulation replay."""
    candidates: tuple[str, ...]
    cost_scenario: CostScenario
    initial_cash: Decimal = Decimal("1000.000000000000")
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    funding_rate_override: Decimal | None = None
    known_funding_schedule: tuple[int, ...] | None = None


@dataclass(frozen=True)
class ReplayReport:
    """Final reconciliation and audit report of synthetic simulation."""
    source: str
    clock_start_ms: int
    clock_end_ms: int
    event_sequence_hash: str
    candidate_outcomes: Mapping[str, Mapping[str, Any]]
    book_balances: Mapping[str, Mapping[str, Decimal]]
    completed_trades: tuple[CompletedTrade, ...]
    invariants_checked_counts: Mapping[str, int]
    terminal_all_zero: bool
