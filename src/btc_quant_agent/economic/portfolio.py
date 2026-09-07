from __future__ import annotations

from dataclasses import dataclass, field

from .trade_event import TradeAction, TradeEvent


@dataclass
class Position:
    asset: str
    quantity: float  # positive for LONG, negative for SHORT
    average_entry_price: float
    entry_timestamp_ms: int

    def unrealized_pnl(self, current_price: float) -> float:
        if abs(self.quantity) < 1e-12 or current_price <= 0:
            return 0.0
        return self.quantity * (current_price - self.average_entry_price)


@dataclass
class Portfolio:
    """Continuous portfolio accounting tracking cash, positions, margin, and TradeEvents."""

    initial_cash: float = 100_000.0
    cash: float = 100_000.0
    positions: dict[str, Position] = field(default_factory=dict)
    trade_history: list[TradeEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError(f"initial_cash must be positive; got {self.initial_cash}")
        if self.cash <= 0:
            self.cash = self.initial_cash

    def get_position_quantity(self, asset: str = "BTCUSDT") -> float:
        pos = self.positions.get(asset)
        return pos.quantity if pos else 0.0

    def total_equity(self, mark_prices: dict[str, float]) -> float:
        eq = self.cash
        for asset, pos in self.positions.items():
            if abs(pos.quantity) > 1e-12:
                mp = mark_prices.get(asset, pos.average_entry_price)
                eq += pos.unrealized_pnl(mp)
        return eq

    def apply_trade(
        self,
        timestamp_ms: int,
        action: TradeAction,
        asset: str,
        price: float,
        quantity: float,
        fee_usdt: float,
        signal_id: str = "",
        trade_id: str = "",
    ) -> TradeEvent:
        if quantity <= 0:
            raise ValueError(f"Trade quantity must be positive; got {quantity}")
        if price <= 0:
            raise ValueError(f"Trade price must be positive; got {price}")

        curr_pos = self.positions.get(asset)
        curr_qty = curr_pos.quantity if curr_pos else 0.0
        curr_entry = curr_pos.average_entry_price if curr_pos else 0.0
        realized_pnl = 0.0

        if action == TradeAction.OPEN_LONG:
            new_qty = curr_qty + quantity
            new_entry = (curr_qty * curr_entry + quantity * price) / new_qty if new_qty > 0 else price
            self.positions[asset] = Position(asset, new_qty, new_entry, timestamp_ms)
            self.cash -= fee_usdt

        elif action == TradeAction.CLOSE_LONG:
            close_qty = min(curr_qty, quantity)
            realized_pnl = close_qty * (price - curr_entry)
            new_qty = max(0.0, curr_qty - close_qty)
            if new_qty < 1e-12:
                self.positions.pop(asset, None)
            else:
                self.positions[asset] = Position(asset, new_qty, curr_entry, curr_pos.entry_timestamp_ms if curr_pos else timestamp_ms)
            self.cash += realized_pnl - fee_usdt

        elif action == TradeAction.OPEN_SHORT:
            new_qty = curr_qty - quantity
            new_entry = (abs(curr_qty) * curr_entry + quantity * price) / abs(new_qty) if abs(new_qty) > 0 else price
            self.positions[asset] = Position(asset, new_qty, new_entry, timestamp_ms)
            self.cash -= fee_usdt

        elif action == TradeAction.CLOSE_SHORT:
            close_qty = min(abs(curr_qty), quantity)
            realized_pnl = close_qty * (curr_entry - price)
            new_qty = curr_qty + close_qty  # moving towards zero from negative
            if abs(new_qty) < 1e-12:
                self.positions.pop(asset, None)
            else:
                self.positions[asset] = Position(asset, new_qty, curr_entry, curr_pos.entry_timestamp_ms if curr_pos else timestamp_ms)
            self.cash += realized_pnl - fee_usdt

        pos_after = self.get_position_quantity(asset)
        event = TradeEvent(
            timestamp_ms=timestamp_ms,
            action=action,
            price=price,
            quantity=quantity,
            fee_usdt=fee_usdt,
            funding_usdt=0.0,
            position_after=pos_after,
            cash_after=self.cash,
            realized_pnl_usdt=realized_pnl,
            trade_id=trade_id,
            signal_id=signal_id,
            metadata={"asset": asset},
        )
        self.trade_history.append(event)
        return event

    def apply_funding(
        self,
        timestamp_ms: int,
        asset: str,
        cashflow_usdt: float,
        mark_price: float,
    ) -> TradeEvent:
        self.cash += cashflow_usdt
        pos_after = self.get_position_quantity(asset)
        event = TradeEvent(
            timestamp_ms=timestamp_ms,
            action=TradeAction.FUNDING_SETTLEMENT,
            price=mark_price,
            quantity=abs(pos_after),
            fee_usdt=0.0,
            funding_usdt=cashflow_usdt,
            position_after=pos_after,
            cash_after=self.cash,
            realized_pnl_usdt=0.0,
            metadata={"asset": asset, "funding_cashflow": cashflow_usdt},
        )
        self.trade_history.append(event)
        return event
