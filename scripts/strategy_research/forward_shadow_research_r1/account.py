"""Paper account, cash ledger, funding accruals, and risk-neutral 1x reserve management.

Under B-line Controller Authority:
TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .contract import SettledFundingData, canonical_json, sha256_hex


class CostCompleteness(str, Enum):
    COST_COMPLETE = "COST_COMPLETE"
    PARTIAL_ECONOMICS_UNKNOWN = "PARTIAL_ECONOMICS_UNKNOWN"


class PositionStatus(str, Enum):
    PENDING_ENTRY = "PENDING_ENTRY"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    RIGHT_CENSORED = "RIGHT_CENSORED"
    UNFILLABLE = "UNFILLABLE"


class ExitReason(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    PROFIT_TARGET = "PROFIT_TARGET"
    TIME_CAP_HORIZON = "TIME_CAP_HORIZON"
    STREAM_END_RIGHT_CENSORED = "STREAM_END_RIGHT_CENSORED"


@dataclass(frozen=True)
class FundingReceipt:
    settlement_time_ms: int
    observed_at_ms: int
    rate: float
    mark_price: float
    position_qty: float
    direction: int  # +1 for long, -1 for short
    cash_flow_usdt: float
    receipt_sha256: str


@dataclass
class ShadowPosition:
    position_id: str
    cell_id: str
    direction: int  # +1 for long, -1 for short
    entry_decision_ms: int
    entry_fill_ms: int
    entry_price: float
    entry_base_quote: float
    entry_slippage_usdt: float
    entry_fee_usdt: float
    qty_btc: float
    entry_notional_usdt: float
    stop_price: float
    target_price: float
    horizon_ms: int
    max_exit_ms: int
    status: PositionStatus = PositionStatus.OPEN
    exit_fill_ms: int | None = None
    exit_price: float | None = None
    exit_base_quote: float | None = None
    exit_slippage_usdt: float | None = None
    exit_fee_usdt: float | None = None
    exit_reason: ExitReason | None = None
    gross_pnl_usdt: float = 0.0
    funding_receipts: list[FundingReceipt] = field(default_factory=list)
    total_funding_usdt: float = 0.0
    net_pnl_usdt: float = 0.0
    net_bps: float = 0.0
    max_adverse_excursion_bps: float = 0.0
    cost_completeness: CostCompleteness = CostCompleteness.COST_COMPLETE
    receipt_sha256: str = ""

    def update_mae(self, current_mark_price: float) -> None:
        """Track Maximum Adverse Excursion in bps relative to entry."""
        if self.direction == 1:
            unrealized_bps = ((current_mark_price - self.entry_price) / self.entry_price) * 10000.0
        else:
            unrealized_bps = ((self.entry_price - current_mark_price) / self.entry_price) * 10000.0

        self.max_adverse_excursion_bps = min(self.max_adverse_excursion_bps, unrealized_bps)

    def apply_funding(self, funding_data: SettledFundingData, observed_at_ms: int) -> FundingReceipt | None:
        """Apply settled official realized funding cash flow."""
        if not funding_data.settled:
            # Prohibited from realized cash journal
            return None

        # Cash flow:
        # Long pays when funding_rate > 0: - qty * mark * rate
        # Short receives when funding_rate > 0: + qty * mark * rate
        cash_flow = - float(self.direction) * self.qty_btc * funding_data.mark_price * funding_data.funding_rate

        receipt_dict = {
            "position_id": self.position_id,
            "settlement_time_ms": funding_data.funding_time_ms,
            "observed_at_ms": observed_at_ms,
            "rate": funding_data.funding_rate,
            "mark_price": funding_data.mark_price,
            "qty_btc": self.qty_btc,
            "direction": self.direction,
            "cash_flow_usdt": cash_flow,
        }
        r_sha = sha256_hex(canonical_json(receipt_dict))

        receipt = FundingReceipt(
            settlement_time_ms=funding_data.funding_time_ms,
            observed_at_ms=observed_at_ms,
            rate=funding_data.funding_rate,
            mark_price=funding_data.mark_price,
            position_qty=self.qty_btc,
            direction=self.direction,
            cash_flow_usdt=cash_flow,
            receipt_sha256=r_sha,
        )
        self.funding_receipts.append(receipt)
        self.total_funding_usdt += cash_flow
        return receipt

    def close(
        self,
        exit_fill_ms: int,
        exit_price: float,
        exit_base_quote: float,
        exit_slippage_usdt: float,
        exit_fee_usdt: float,
        exit_reason: ExitReason,
    ) -> None:
        """Close the position and compute final economic figures."""
        self.exit_fill_ms = exit_fill_ms
        self.exit_price = exit_price
        self.exit_base_quote = exit_base_quote
        self.exit_slippage_usdt = exit_slippage_usdt
        self.exit_fee_usdt = exit_fee_usdt
        self.exit_reason = exit_reason
        self.status = PositionStatus.CLOSED

        if self.direction == 1:
            self.gross_pnl_usdt = self.qty_btc * (exit_price - self.entry_price)
        else:
            self.gross_pnl_usdt = self.qty_btc * (self.entry_price - exit_price)

        total_fees = self.entry_fee_usdt + self.exit_fee_usdt
        self.net_pnl_usdt = self.gross_pnl_usdt - total_fees + self.total_funding_usdt
        if self.entry_notional_usdt > 0:
            self.net_bps = (self.net_pnl_usdt / self.entry_notional_usdt) * 10000.0

        # Verify scheduled funding completeness:
        # Binance settles at multiples of 8h (28,800,000 ms)
        fund_interval = 8 * 3600 * 1000
        first_fund = ((self.entry_fill_ms // fund_interval) + 1) * fund_interval
        expected_settlements = []
        t = first_fund
        while t <= exit_fill_ms:
            expected_settlements.append(t)
            t += fund_interval

        actual_settlements = {r.settlement_time_ms for r in self.funding_receipts}
        missing_settlements = set(expected_settlements) - actual_settlements
        if missing_settlements:
            self.cost_completeness = CostCompleteness.PARTIAL_ECONOMICS_UNKNOWN
        else:
            self.cost_completeness = CostCompleteness.COST_COMPLETE

        payload = self.to_dict()
        self.receipt_sha256 = sha256_hex(canonical_json(payload))

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_id": self.position_id,
            "cell_id": self.cell_id,
            "direction": self.direction,
            "entry_decision_ms": self.entry_decision_ms,
            "entry_fill_ms": self.entry_fill_ms,
            "entry_price": self.entry_price,
            "entry_base_quote": self.entry_base_quote,
            "entry_slippage_usdt": self.entry_slippage_usdt,
            "entry_fee_usdt": self.entry_fee_usdt,
            "qty_btc": self.qty_btc,
            "entry_notional_usdt": self.entry_notional_usdt,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "horizon_ms": self.horizon_ms,
            "max_exit_ms": self.max_exit_ms,
            "status": self.status.value,
            "exit_fill_ms": self.exit_fill_ms,
            "exit_price": self.exit_price,
            "exit_base_quote": self.exit_base_quote,
            "exit_slippage_usdt": self.exit_slippage_usdt,
            "exit_fee_usdt": self.exit_fee_usdt,
            "exit_reason": self.exit_reason.value if self.exit_reason else None,
            "gross_pnl_usdt": self.gross_pnl_usdt,
            "total_funding_usdt": self.total_funding_usdt,
            "net_pnl_usdt": self.net_pnl_usdt,
            "net_bps": self.net_bps,
            "max_adverse_excursion_bps": self.max_adverse_excursion_bps,
            "cost_completeness": self.cost_completeness.value,
            "funding_receipts": [
                {
                    "settlement_time_ms": r.settlement_time_ms,
                    "observed_at_ms": r.observed_at_ms,
                    "rate": r.rate,
                    "mark_price": r.mark_price,
                    "cash_flow_usdt": r.cash_flow_usdt,
                    "receipt_sha256": r.receipt_sha256,
                }
                for r in self.funding_receipts
            ],
        }


class PaperAccount:
    """Risk-neutral 1x synthetic cash account with 5% reserve and 6h cooldown."""

    def __init__(
        self,
        initial_capital_usdt: float = 1000.0,
        reserve_fraction: float = 0.05,
        lot_step_btc: float = 0.001,
        cooldown_hours: int = 6,
        taker_fee_bps: float = 5.0,
        adverse_slippage_bps: float = 0.5,
    ):
        self.initial_capital_usdt = initial_capital_usdt
        self.cash_usdt = initial_capital_usdt
        self.reserve_fraction = reserve_fraction
        self.lot_step_btc = lot_step_btc
        self.cooldown_ms = cooldown_hours * 3600 * 1000
        self.taker_fee_bps = taker_fee_bps
        self.adverse_slippage_bps = adverse_slippage_bps

        self.active_position: ShadowPosition | None = None
        self.last_exit_ms: int = -1
        self.closed_positions: list[ShadowPosition] = []

    @property
    def reserve_usdt(self) -> float:
        """5% reserve buffer."""
        return self.cash_usdt * self.reserve_fraction

    @property
    def usable_capital_usdt(self) -> float:
        """95% usable equity for position notional."""
        return max(0.0, self.cash_usdt - self.reserve_usdt)

    def is_in_cooldown(self, current_time_ms: int) -> bool:
        """Check if account is within 6h post-exit cooldown."""
        if self.last_exit_ms < 0:
            return False
        return (current_time_ms - self.last_exit_ms) < self.cooldown_ms

    def calculate_lot_size(self, entry_price: float) -> float:
        """Calculate step-aligned BTC lot size using 1x usable equity."""
        if entry_price <= 0:
            return 0.0
        usable = self.usable_capital_usdt
        raw_btc = usable / entry_price
        steps = math.floor(raw_btc / self.lot_step_btc)
        lot = steps * self.lot_step_btc
        return max(0.0, round(lot, 6))

    def open_shadow_position(
        self,
        cell_id: str,
        direction: int,
        entry_decision_ms: int,
        entry_fill_ms: int,
        best_bid: float,
        best_ask: float,
        stop_price: float,
        target_price: float,
        horizon_ms: int,
    ) -> ShadowPosition | None:
        """Open a 1x shadow paper position with conservative taker quotes and slippage."""
        # Max one active position invariant
        if self.active_position is not None:
            return None

        # Cooldown invariant
        if self.is_in_cooldown(entry_fill_ms):
            return None

        # Check crossed spread or non-positive quotes
        if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
            return None

        # Executable quote:
        # Long enters at best_ask + slippage
        # Short enters at best_bid - slippage
        if direction == 1:
            base_quote = best_ask
            slippage = base_quote * (self.adverse_slippage_bps / 10000.0)
            executed_price = base_quote + slippage
        elif direction == -1:
            base_quote = best_bid
            slippage = base_quote * (self.adverse_slippage_bps / 10000.0)
            executed_price = base_quote - slippage
        else:
            return None

        qty = self.calculate_lot_size(executed_price)
        if qty < self.lot_step_btc:
            return None

        notional = executed_price * qty
        fee = notional * (self.taker_fee_bps / 10000.0)
        slippage_usdt = slippage * qty

        pos_id = f"pos_{cell_id}_{entry_fill_ms}_{len(self.closed_positions)}"
        pos = ShadowPosition(
            position_id=pos_id,
            cell_id=cell_id,
            direction=direction,
            entry_decision_ms=entry_decision_ms,
            entry_fill_ms=entry_fill_ms,
            entry_price=executed_price,
            entry_base_quote=base_quote,
            entry_slippage_usdt=slippage_usdt,
            entry_fee_usdt=fee,
            qty_btc=qty,
            entry_notional_usdt=notional,
            stop_price=stop_price,
            target_price=target_price,
            horizon_ms=horizon_ms,
            max_exit_ms=entry_fill_ms + horizon_ms,
        )

        self.active_position = pos
        return pos

    def close_shadow_position(
        self,
        exit_fill_ms: int,
        best_bid: float,
        best_ask: float,
        exit_reason: ExitReason,
    ) -> ShadowPosition | None:
        """Close active shadow position with conservative same-side taker quotes and fees."""
        pos = self.active_position
        if pos is None:
            return None

        # Same-side conservative quote:
        # Long exits by selling at best_bid - slippage
        # Short exits by buying to cover at best_ask + slippage
        if pos.direction == 1:
            base_quote = best_bid
            slippage = base_quote * (self.adverse_slippage_bps / 10000.0)
            executed_price = base_quote - slippage
        else:
            base_quote = best_ask
            slippage = base_quote * (self.adverse_slippage_bps / 10000.0)
            executed_price = base_quote + slippage

        exit_notional = executed_price * pos.qty_btc
        fee = exit_notional * (self.taker_fee_bps / 10000.0)
        slippage_usdt = slippage * pos.qty_btc

        pos.close(
            exit_fill_ms=exit_fill_ms,
            exit_price=executed_price,
            exit_base_quote=base_quote,
            exit_slippage_usdt=slippage_usdt,
            exit_fee_usdt=fee,
            exit_reason=exit_reason,
        )

        # Update cash
        self.cash_usdt += pos.net_pnl_usdt
        self.last_exit_ms = exit_fill_ms
        self.closed_positions.append(pos)
        self.active_position = None
        return pos
