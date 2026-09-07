from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..domain import Candle
from .fee_model import FeeModel
from .policy import OrderType


@dataclass(frozen=True)
class ExecutionResult:
    """Disaggregated execution outcome replacing naive price-touch-equals-fill assumptions."""

    signal_timestamp_ms: int
    order_timestamp_ms: int
    fill_timestamp_ms: int
    fill_price: float
    filled_quantity: float
    is_filled: bool
    side: int  # +1 = BUY, -1 = SELL
    is_maker: bool = False
    fee_usdt: float = 0.0
    slippage_usdt: float = 0.0
    rejection_reason: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.is_filled:
            if not (self.signal_timestamp_ms <= self.order_timestamp_ms <= self.fill_timestamp_ms):
                raise ValueError(
                    f"Timestamp ordering violation: signal ({self.signal_timestamp_ms}) <= "
                    f"order ({self.order_timestamp_ms}) <= fill ({self.fill_timestamp_ms})"
                )
            if self.fill_price <= 0:
                raise ValueError(f"fill_price must be positive; got {self.fill_price}")
            if self.filled_quantity <= 0:
                raise ValueError(f"filled_quantity must be positive; got {self.filled_quantity}")


class ExecutionModel:
    """Execution simulator modeling decision latency, exchange delays, slippage, and limit queueing."""

    def __init__(
        self,
        fee_model: FeeModel | None = None,
        decision_latency_ms: int = 500,
        exchange_latency_ms: int = 150,
        limit_fill_prob_on_touch: float = 0.20,  # on mere touch, only 20% queue fill probability
    ) -> None:
        self.fee_model = fee_model or FeeModel()
        self.decision_latency_ms = decision_latency_ms
        self.exchange_latency_ms = exchange_latency_ms
        self.limit_fill_prob_on_touch = limit_fill_prob_on_touch

    def simulate_order(
        self,
        signal_timestamp_ms: int,
        side: int,  # +1 = BUY, -1 = SELL
        desired_quantity: float,
        order_type: OrderType,
        future_candles: Sequence[Candle],
        limit_price: float | None = None,
        time_in_force_ms: int = 60_000,
        current_spread_bps: float = 1.0,
    ) -> ExecutionResult:
        if desired_quantity <= 0:
            return ExecutionResult(
                signal_timestamp_ms=signal_timestamp_ms,
                order_timestamp_ms=signal_timestamp_ms,
                fill_timestamp_ms=signal_timestamp_ms,
                fill_price=0.0,
                filled_quantity=0.0,
                is_filled=False,
                side=side,
                rejection_reason="INVALID_QUANTITY",
            )

        order_timestamp_ms = signal_timestamp_ms + self.decision_latency_ms
        earliest_fill_ms = order_timestamp_ms + self.exchange_latency_ms
        expiration_ms = order_timestamp_ms + time_in_force_ms

        if not future_candles:
            return ExecutionResult(
                signal_timestamp_ms=signal_timestamp_ms,
                order_timestamp_ms=order_timestamp_ms,
                fill_timestamp_ms=earliest_fill_ms,
                fill_price=0.0,
                filled_quantity=0.0,
                is_filled=False,
                side=side,
                rejection_reason="NO_MARKET_DATA",
            )

        if order_type == OrderType.MARKET:
            # Market order executes on first available candle at or after earliest_fill_ms
            fill_bar: Candle | None = None
            for bar in future_candles:
                if bar.close_time_ms >= earliest_fill_ms:
                    fill_bar = bar
                    break

            if fill_bar is None:
                return ExecutionResult(
                    signal_timestamp_ms=signal_timestamp_ms,
                    order_timestamp_ms=order_timestamp_ms,
                    fill_timestamp_ms=earliest_fill_ms,
                    fill_price=0.0,
                    filled_quantity=0.0,
                    is_filled=False,
                    side=side,
                    rejection_reason="MARKET_DATA_EXHAUSTED",
                )

            # Execution happens at open if order arrived before bar, otherwise close/interpolation
            ref_price = fill_bar.open if fill_bar.open_time_ms >= earliest_fill_ms else fill_bar.close
            actual_fill_time_ms = max(earliest_fill_ms, fill_bar.open_time_ms)

            fill_price = self.fee_model.effective_fill_price(
                reference_price=ref_price,
                quantity=desired_quantity,
                side=side,
                is_maker=False,
                current_spread_bps=current_spread_bps,
                bar_volume_base=fill_bar.volume,
            )
            slippage_cost = abs(fill_price - ref_price) * desired_quantity
            notional = fill_price * desired_quantity
            fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=False)

            return ExecutionResult(
                signal_timestamp_ms=signal_timestamp_ms,
                order_timestamp_ms=order_timestamp_ms,
                fill_timestamp_ms=actual_fill_time_ms,
                fill_price=fill_price,
                filled_quantity=desired_quantity,
                is_filled=True,
                side=side,
                is_maker=False,
                fee_usdt=fee_usdt,
                slippage_usdt=slippage_cost,
                metadata={"ref_price": ref_price, "candle_open_ms": fill_bar.open_time_ms},
            )

        elif order_type == OrderType.LIMIT:
            if limit_price is None or limit_price <= 0:
                return ExecutionResult(
                    signal_timestamp_ms=signal_timestamp_ms,
                    order_timestamp_ms=order_timestamp_ms,
                    fill_timestamp_ms=earliest_fill_ms,
                    fill_price=0.0,
                    filled_quantity=0.0,
                    is_filled=False,
                    side=side,
                    rejection_reason="INVALID_LIMIT_PRICE",
                )

            # Limit order requires the market to trade THROUGH the price after order arrives
            # Touching the boundary does NOT guarantee fill due to queue priority
            for bar in future_candles:
                if bar.open_time_ms > expiration_ms:
                    break
                if bar.close_time_ms < earliest_fill_ms:
                    continue

                if side == 1:  # BUY LIMIT at limit_price
                    # Trades strictly through limit price (low < limit_price)
                    if bar.low < limit_price:
                        notional = limit_price * desired_quantity
                        fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=True)
                        fill_time = max(earliest_fill_ms, bar.open_time_ms)
                        return ExecutionResult(
                            signal_timestamp_ms=signal_timestamp_ms,
                            order_timestamp_ms=order_timestamp_ms,
                            fill_timestamp_ms=fill_time,
                            fill_price=limit_price,
                            filled_quantity=desired_quantity,
                            is_filled=True,
                            side=side,
                            is_maker=True,
                            fee_usdt=fee_usdt,
                            slippage_usdt=0.0,
                            metadata={"traded_through": True, "bar_low": bar.low},
                        )
                    # Touching exact price (bar.low == limit_price): queue fill is partial/uncertain
                    elif abs(bar.low - limit_price) < 1e-8 and self.limit_fill_prob_on_touch >= 1.0:
                        notional = limit_price * desired_quantity
                        fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=True)
                        fill_time = max(earliest_fill_ms, bar.open_time_ms)
                        return ExecutionResult(
                            signal_timestamp_ms=signal_timestamp_ms,
                            order_timestamp_ms=order_timestamp_ms,
                            fill_timestamp_ms=fill_time,
                            fill_price=limit_price,
                            filled_quantity=desired_quantity,
                            is_filled=True,
                            side=side,
                            is_maker=True,
                            fee_usdt=fee_usdt,
                            slippage_usdt=0.0,
                            metadata={"traded_touch": True},
                        )
                else:  # SELL LIMIT at limit_price
                    # Trades strictly through limit price (high > limit_price)
                    if bar.high > limit_price:
                        notional = limit_price * desired_quantity
                        fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=True)
                        fill_time = max(earliest_fill_ms, bar.open_time_ms)
                        return ExecutionResult(
                            signal_timestamp_ms=signal_timestamp_ms,
                            order_timestamp_ms=order_timestamp_ms,
                            fill_timestamp_ms=fill_time,
                            fill_price=limit_price,
                            filled_quantity=desired_quantity,
                            is_filled=True,
                            side=side,
                            is_maker=True,
                            fee_usdt=fee_usdt,
                            slippage_usdt=0.0,
                            metadata={"traded_through": True, "bar_high": bar.high},
                        )
                    elif abs(bar.high - limit_price) < 1e-8 and self.limit_fill_prob_on_touch >= 1.0:
                        notional = limit_price * desired_quantity
                        fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=True)
                        fill_time = max(earliest_fill_ms, bar.open_time_ms)
                        return ExecutionResult(
                            signal_timestamp_ms=signal_timestamp_ms,
                            order_timestamp_ms=order_timestamp_ms,
                            fill_timestamp_ms=fill_time,
                            fill_price=limit_price,
                            filled_quantity=desired_quantity,
                            is_filled=True,
                            side=side,
                            is_maker=True,
                            fee_usdt=fee_usdt,
                            slippage_usdt=0.0,
                            metadata={"traded_touch": True},
                        )

            return ExecutionResult(
                signal_timestamp_ms=signal_timestamp_ms,
                order_timestamp_ms=order_timestamp_ms,
                fill_timestamp_ms=expiration_ms,
                fill_price=0.0,
                filled_quantity=0.0,
                is_filled=False,
                side=side,
                rejection_reason="LIMIT_EXPIRED_UNFILLED",
            )

        return ExecutionResult(
            signal_timestamp_ms=signal_timestamp_ms,
            order_timestamp_ms=order_timestamp_ms,
            fill_timestamp_ms=earliest_fill_ms,
            fill_price=0.0,
            filled_quantity=0.0,
            is_filled=False,
            side=side,
            rejection_reason=f"UNSUPPORTED_ORDER_TYPE_{order_type}",
        )
