from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
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
        if self.timestamp_ms <= 0:
            raise ValueError(f"timestamp_ms must be positive; got {self.timestamp_ms}")
        if self.price < 0:
            raise ValueError(f"price cannot be negative; got {self.price}")
        if self.quantity < 0:
            raise ValueError(f"quantity cannot be negative; got {self.quantity}")
        if self.fee_usdt < 0:
            raise ValueError(f"fee_usdt cannot be negative; got {self.fee_usdt}")

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
            timestamp_ms=int(data["timestamp_ms"]),
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
