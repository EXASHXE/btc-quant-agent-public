from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .policy import OrderType


class OrderState(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


def _finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


@dataclass
class Order:
    """Explicit order representation separating signal, order submission, fill, and settlement."""

    order_id: str
    asset: str
    side: int  # +1 = BUY, -1 = SELL
    desired_quantity: float
    order_type: OrderType
    observation_timestamp_ms: int
    decision_timestamp_ms: int
    order_timestamp_ms: int
    signal_id: str = ""
    limit_price: float | None = None
    time_in_force_ms: int = 60_000
    state: OrderState = OrderState.PENDING
    rejection_reason: str | None = None
    filled_quantity: float = 0.0
    fill_price: float = 0.0
    fill_timestamp_ms: int | None = None
    settlement_timestamp_ms: int | None = None
    fee_usdt: float = 0.0
    is_maker: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.order_id:
            raise ValueError("order_id cannot be empty")
        if not self.asset.strip():
            raise ValueError("asset cannot be empty")
        if self.side not in (1, -1):
            raise ValueError(f"side must be 1 (BUY) or -1 (SELL); got {self.side}")
        _finite(self.desired_quantity, "desired_quantity")
        if self.desired_quantity <= 0:
            raise ValueError("desired_quantity must be positive")
        if self.time_in_force_ms <= 0:
            raise ValueError("time_in_force_ms must be positive")

        # Monotonic timeline validation: observation <= decision <= order
        for name, ts in (
            ("observation_timestamp_ms", self.observation_timestamp_ms),
            ("decision_timestamp_ms", self.decision_timestamp_ms),
            ("order_timestamp_ms", self.order_timestamp_ms),
        ):
            if type(ts) is not int or ts <= 0:
                raise ValueError(f"{name} must be a positive integer")

        if self.decision_timestamp_ms < self.observation_timestamp_ms:
            raise ValueError(
                f"decision_timestamp_ms ({self.decision_timestamp_ms}) cannot be before "
                f"observation_timestamp_ms ({self.observation_timestamp_ms})"
            )
        if self.order_timestamp_ms < self.decision_timestamp_ms:
            raise ValueError(
                f"order_timestamp_ms ({self.order_timestamp_ms}) cannot be before "
                f"decision_timestamp_ms ({self.decision_timestamp_ms})"
            )

        if self.fill_timestamp_ms is not None:
            if type(self.fill_timestamp_ms) is not int or self.fill_timestamp_ms <= 0:
                raise ValueError("fill_timestamp_ms must be a positive integer")
            if self.fill_timestamp_ms < self.order_timestamp_ms:
                raise ValueError(
                    f"fill_timestamp_ms ({self.fill_timestamp_ms}) cannot be before "
                    f"order_timestamp_ms ({self.order_timestamp_ms})"
                )

        if self.settlement_timestamp_ms is not None:
            if type(self.settlement_timestamp_ms) is not int or self.settlement_timestamp_ms <= 0:
                raise ValueError("settlement_timestamp_ms must be a positive integer")
            ref_fill = self.fill_timestamp_ms if self.fill_timestamp_ms is not None else self.order_timestamp_ms
            if self.settlement_timestamp_ms < ref_fill:
                raise ValueError(
                    f"settlement_timestamp_ms ({self.settlement_timestamp_ms}) cannot be before "
                    f"fill_timestamp_ms ({ref_fill})"
                )

        if self.limit_price is not None:
            _finite(self.limit_price, "limit_price")
            if self.limit_price <= 0:
                raise ValueError("limit_price must be positive")

    @property
    def is_active(self) -> bool:
        return self.state in (OrderState.PENDING, OrderState.ACCEPTED, OrderState.PARTIALLY_FILLED)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["order_type"] = self.order_type.value
        d["state"] = self.state.value
        return d
