from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from .trade_event import TradeAction, TradeEvent


def _finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class Position:
    asset: str
    quantity: float  # signed linear-contract quantity
    average_entry_price: float
    entry_timestamp_ms: int

    def __post_init__(self) -> None:
        _finite(self.quantity, "quantity")
        _finite(self.average_entry_price, "average_entry_price")
        if not self.asset.strip() or self.quantity == 0 or self.average_entry_price <= 0:
            raise ValueError("Position requires asset, nonzero quantity and positive entry price")
        if type(self.entry_timestamp_ms) is not int or self.entry_timestamp_ms <= 0:
            raise ValueError("entry_timestamp_ms must be a positive integer")

    def unrealized_pnl(self, current_price: float) -> float:
        _finite(current_price, "current_price")
        if current_price <= 0:
            raise ValueError("current_price must be positive")
        result = self.quantity * (current_price - self.average_entry_price)
        _finite(result, "unrealized_pnl")
        return result


@dataclass
class Portfolio:
    """Single-writer linear-contract cash ledger, not a margin/liquidation model.

    New accounts always start at initial_cash. Restore through from_events(),
    never by injecting cash/positions without their cashflow history. Equal-time
    events follow caller order; backwards events fail before any mutation.
    """

    initial_cash: float = 100_000.0
    cash: float = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict, init=False)
    trade_history: list[TradeEvent] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        _finite(self.initial_cash, "initial_cash")
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.cash = self.initial_cash

    def _validate_event_input(self, timestamp_ms: int, asset: str) -> None:
        if type(timestamp_ms) is not int or timestamp_ms <= 0:
            raise ValueError("timestamp_ms must be a positive integer")
        if self.trade_history and timestamp_ms < self.trade_history[-1].timestamp_ms:
            raise ValueError("Backwards ledger timestamp")
        if not isinstance(asset, str) or not asset.strip():
            raise ValueError("asset cannot be empty")

    def get_position_quantity(self, asset: str = "BTCUSDT") -> float:
        pos = self.positions.get(asset)
        return pos.quantity if pos else 0.0

    def total_equity(self, mark_prices: dict[str, float]) -> float:
        eq = self.cash
        for asset, pos in self.positions.items():
            if asset not in mark_prices:
                raise ValueError(f"Missing mark price for {asset}")
            eq += pos.unrealized_pnl(mark_prices[asset])
        _finite(eq, "equity")
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
        observation_timestamp_ms: int | None = None,
        decision_timestamp_ms: int | None = None,
        order_timestamp_ms: int | None = None,
        settlement_timestamp_ms: int | None = None,
    ) -> TradeEvent:
        self._validate_event_input(timestamp_ms, asset)
        action = TradeAction(action)
        if action == TradeAction.FUNDING_SETTLEMENT:
            raise ValueError("Use apply_funding for funding settlements")
        for name, value in (("quantity", quantity), ("price", price), ("fee_usdt", fee_usdt)):
            _finite(value, name)
        if quantity <= 0 or price <= 0 or fee_usdt < 0:
            raise ValueError("Trade requires positive quantity/price and nonnegative fee")

        current = self.positions.get(asset)
        curr_qty = current.quantity if current else 0.0
        curr_entry = current.average_entry_price if current else 0.0
        opening = action in (TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT)
        direction = 1 if action in (TradeAction.OPEN_LONG, TradeAction.CLOSE_LONG) else -1
        realized = 0.0

        if opening:
            if curr_qty * direction < 0:
                raise ValueError("Close the opposite position before opening")
            size = abs(curr_qty) + quantity
            if size == abs(curr_qty):
                raise ValueError("Quantity increment is below floating-point resolution")
            new_qty = direction * size
            new_entry = curr_entry * (abs(curr_qty) / size) + price * (quantity / size)
        else:
            if curr_qty * direction <= 0:
                raise ValueError("Close action does not match an open position")
            if quantity > abs(curr_qty):
                raise ValueError("Close quantity exceeds the open position")
            new_qty = direction * (abs(curr_qty) - quantity)
            if new_qty == curr_qty:
                raise ValueError("Close quantity is below floating-point resolution")
            new_entry = curr_entry
            realized = direction * quantity * (price - curr_entry)

        new_cash = self.cash + realized - fee_usdt
        new_position = (
            Position(
                asset, new_qty, new_entry, current.entry_timestamp_ms if current else timestamp_ms
            )
            if new_qty != 0
            else None
        )
        # Validate the proposed state and event BEFORE committing either.
        event = TradeEvent(
            timestamp_ms=timestamp_ms,
            action=action,
            price=price,
            quantity=quantity,
            fee_usdt=fee_usdt,
            funding_usdt=0.0,
            position_after=new_qty,
            cash_after=new_cash,
            realized_pnl_usdt=realized,
            trade_id=trade_id,
            signal_id=signal_id,
            observation_timestamp_ms=observation_timestamp_ms,
            decision_timestamp_ms=decision_timestamp_ms,
            order_timestamp_ms=order_timestamp_ms,
            settlement_timestamp_ms=settlement_timestamp_ms,
            metadata={"asset": asset},
        )
        if new_position is None:
            self.positions.pop(asset, None)
        else:
            self.positions[asset] = new_position
        self.cash = new_cash
        self.trade_history.append(event)
        return event

    def apply_funding(
        self,
        timestamp_ms: int,
        asset: str,
        cashflow_usdt: float,
        mark_price: float,
    ) -> TradeEvent:
        self._validate_event_input(timestamp_ms, asset)
        _finite(cashflow_usdt, "cashflow_usdt")
        qty = self.get_position_quantity(asset)
        if qty == 0 and cashflow_usdt != 0:
            raise ValueError("Nonzero funding requires an open position")
        event = TradeEvent(
            timestamp_ms=timestamp_ms,
            action=TradeAction.FUNDING_SETTLEMENT,
            price=mark_price,
            quantity=abs(qty),
            fee_usdt=0.0,
            funding_usdt=cashflow_usdt,
            position_after=qty,
            cash_after=self.cash + cashflow_usdt,
            realized_pnl_usdt=0.0,
            metadata={"asset": asset, "funding_cashflow": cashflow_usdt},
        )
        self.cash = event.cash_after
        self.trade_history.append(event)
        return event

    @classmethod
    def from_events(cls, initial_cash: float, events: Sequence[TradeEvent]) -> Portfolio:
        """Restore by verified replay, preserving zero or negative cash.

        Snapshots are checked, not trusted; failed replay returns no account.
        """
        result = cls(initial_cash=initial_cash)
        for event in events:
            asset = event.metadata.get("asset")
            if not isinstance(asset, str) or not asset.strip():
                raise TypeError("Restored event requires an asset string")
            if event.action == TradeAction.FUNDING_SETTLEMENT:
                actual = result.apply_funding(
                    event.timestamp_ms, asset, event.funding_usdt, event.price
                )
            else:
                actual = result.apply_trade(
                    event.timestamp_ms,
                    event.action,
                    asset,
                    event.price,
                    event.quantity,
                    event.fee_usdt,
                    event.signal_id,
                    event.trade_id,
                    observation_timestamp_ms=event.observation_timestamp_ms,
                    decision_timestamp_ms=event.decision_timestamp_ms,
                    order_timestamp_ms=event.order_timestamp_ms,
                    settlement_timestamp_ms=event.settlement_timestamp_ms,
                )
            if actual.to_dict() != event.to_dict():
                raise ValueError("Restored event disagrees with replayed ledger")
        return result
