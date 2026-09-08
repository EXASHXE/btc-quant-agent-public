from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import math
from typing import Any


class TradeAction(StrEnum):
    OPEN_LONG = "OPEN_LONG"
    CLOSE_LONG = "CLOSE_LONG"
    OPEN_SHORT = "OPEN_SHORT"
    CLOSE_SHORT = "CLOSE_SHORT"
    FUNDING_SETTLEMENT = "FUNDING_SETTLEMENT"


@dataclass(frozen=True)
class TradeEvent:
    """Unified atomic economic transaction event across simulation, shadow, and backtest."""

    timestamp_ms: int
    action: TradeAction
    price: float
    quantity: float
    fee_usdt: float
    funding_usdt: float
    position_after: float
    cash_after: float
    realized_pnl_usdt: float = 0.0
    trade_id: str = ""
    signal_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", TradeAction(self.action))
        if type(self.timestamp_ms) is not int or self.timestamp_ms <= 0:
            raise ValueError("timestamp_ms must be a positive integer")
        for name in (
            "price",
            "quantity",
            "fee_usdt",
            "funding_usdt",
            "position_after",
            "cash_after",
            "realized_pnl_usdt",
        ):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if self.price <= 0 or self.quantity < 0 or self.fee_usdt < 0:
            raise ValueError("Event requires positive price and nonnegative quantity/fee")
        if self.action == TradeAction.FUNDING_SETTLEMENT:
            if self.fee_usdt != 0 or self.realized_pnl_usdt != 0:
                raise ValueError("Funding events cannot contain trading fees or realized PnL")
        elif self.quantity <= 0 or self.funding_usdt != 0:
            raise ValueError("Trade events require positive quantity and zero funding")

    @property
    def net_cashflow_usdt(self) -> float:
        """Net cash impact of this event on the portfolio."""
        return self.realized_pnl_usdt - self.fee_usdt + self.funding_usdt

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action"] = self.action.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TradeEvent:
        act = data["action"]
        action_enum = act if isinstance(act, TradeAction) else TradeAction(act)
        return cls(
            timestamp_ms=data["timestamp_ms"],
            action=action_enum,
            price=float(data.get("price", 0.0)),
            quantity=float(data.get("quantity", 0.0)),
            fee_usdt=float(data.get("fee_usdt", 0.0)),
            funding_usdt=float(data.get("funding_usdt", 0.0)),
            position_after=float(data["position_after"]),
            cash_after=float(data["cash_after"]),
            realized_pnl_usdt=float(data.get("realized_pnl_usdt", 0.0)),
            trade_id=str(data.get("trade_id", "")),
            signal_id=str(data.get("signal_id", "")),
            metadata=dict(data.get("metadata", {})),
        )
