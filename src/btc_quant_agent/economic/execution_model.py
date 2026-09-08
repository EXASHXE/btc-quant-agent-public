from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..domain import Candle
from .fee_model import FeeModel
from .policy import OrderType


def _finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


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
    observation_timestamp_ms: int | None = None
    decision_timestamp_ms: int | None = None
    settlement_timestamp_ms: int | None = None
    is_maker: bool = False
    fee_usdt: float = 0.0
    slippage_usdt: float = 0.0
    rejection_reason: str | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        obs = self.observation_timestamp_ms if self.observation_timestamp_ms is not None else self.signal_timestamp_ms
        dec = self.decision_timestamp_ms if self.decision_timestamp_ms is not None else self.order_timestamp_ms
        settle = self.settlement_timestamp_ms if self.settlement_timestamp_ms is not None else self.fill_timestamp_ms

        if self.observation_timestamp_ms is None:
            object.__setattr__(self, "observation_timestamp_ms", obs)
        if self.decision_timestamp_ms is None:
            object.__setattr__(self, "decision_timestamp_ms", dec)
        if self.settlement_timestamp_ms is None:
            object.__setattr__(self, "settlement_timestamp_ms", settle)

        # Monotonic timeline validation
        if not (obs <= dec <= self.order_timestamp_ms):
            raise ValueError(
                f"Timestamp ordering violation: observation ({obs}) <= "
                f"decision ({dec}) <= order ({self.order_timestamp_ms})"
            )

        if self.is_filled:
            if not (self.order_timestamp_ms <= self.fill_timestamp_ms <= settle):
                raise ValueError(
                    f"Timestamp ordering violation: order ({self.order_timestamp_ms}) <= "
                    f"fill ({self.fill_timestamp_ms}) <= settlement ({settle})"
                )
            _finite(self.fill_price, "fill_price")
            _finite(self.filled_quantity, "filled_quantity")
            if self.fill_price <= 0:
                raise ValueError(f"fill_price must be positive; got {self.fill_price}")
            if self.filled_quantity <= 0:
                raise ValueError(f"filled_quantity must be positive; got {self.filled_quantity}")
        else:
            if self.fill_timestamp_ms < self.order_timestamp_ms:
                raise ValueError(
                    f"fill_timestamp_ms ({self.fill_timestamp_ms}) cannot be before "
                    f"order_timestamp_ms ({self.order_timestamp_ms})"
                )


class ExecutionModel:
    """Execution simulator modeling decision latency, exchange delays, slippage, and limit queueing."""

    def __init__(
        self,
        fee_model: FeeModel | None = None,
        decision_latency_ms: int = 500,
        exchange_latency_ms: int = 150,
        limit_fill_prob_on_touch: float = 0.20,  # on mere touch, queue fill probability (requires 1.0 for certainty)
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
        observation_timestamp_ms: int | None = None,
    ) -> ExecutionResult:
        obs_ts = observation_timestamp_ms if observation_timestamp_ms is not None else signal_timestamp_ms
        if obs_ts > signal_timestamp_ms:
            raise ValueError(
                f"observation_timestamp_ms ({obs_ts}) cannot be after signal_timestamp_ms ({signal_timestamp_ms})"
            )

        order_timestamp_ms = signal_timestamp_ms + self.decision_latency_ms
        dec_ts = order_timestamp_ms
        earliest_fill_ms = order_timestamp_ms + self.exchange_latency_ms
        expiration_ms = order_timestamp_ms + time_in_force_ms

        if desired_quantity <= 0:
            return ExecutionResult(
                signal_timestamp_ms=signal_timestamp_ms,
                order_timestamp_ms=order_timestamp_ms,
                fill_timestamp_ms=earliest_fill_ms,
                fill_price=0.0,
                filled_quantity=0.0,
                is_filled=False,
                side=side,
                observation_timestamp_ms=obs_ts,
                decision_timestamp_ms=dec_ts,
                settlement_timestamp_ms=earliest_fill_ms,
                rejection_reason="INVALID_QUANTITY",
            )

        if side not in (1, -1):
            return ExecutionResult(
                signal_timestamp_ms=signal_timestamp_ms,
                order_timestamp_ms=order_timestamp_ms,
                fill_timestamp_ms=earliest_fill_ms,
                fill_price=0.0,
                filled_quantity=0.0,
                is_filled=False,
                side=side,
                observation_timestamp_ms=obs_ts,
                decision_timestamp_ms=dec_ts,
                settlement_timestamp_ms=earliest_fill_ms,
                rejection_reason="INVALID_SIDE",
            )

        if not future_candles:
            return ExecutionResult(
                signal_timestamp_ms=signal_timestamp_ms,
                order_timestamp_ms=order_timestamp_ms,
                fill_timestamp_ms=earliest_fill_ms,
                fill_price=0.0,
                filled_quantity=0.0,
                is_filled=False,
                side=side,
                observation_timestamp_ms=obs_ts,
                decision_timestamp_ms=dec_ts,
                settlement_timestamp_ms=earliest_fill_ms,
                rejection_reason="NO_MARKET_DATA",
            )

        if order_type == OrderType.MARKET:
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
                    observation_timestamp_ms=obs_ts,
                    decision_timestamp_ms=dec_ts,
                    settlement_timestamp_ms=earliest_fill_ms,
                    rejection_reason="MARKET_DATA_EXHAUSTED",
                )

            # Liquidity check
            if fill_bar.volume <= 0:
                return ExecutionResult(
                    signal_timestamp_ms=signal_timestamp_ms,
                    order_timestamp_ms=order_timestamp_ms,
                    fill_timestamp_ms=earliest_fill_ms,
                    fill_price=0.0,
                    filled_quantity=0.0,
                    is_filled=False,
                    side=side,
                    observation_timestamp_ms=obs_ts,
                    decision_timestamp_ms=dec_ts,
                    settlement_timestamp_ms=earliest_fill_ms,
                    rejection_reason="INSUFFICIENT_LIQUIDITY",
                )

            # Causal execution: if arrived before/at open, fill at open price at bar.open_time_ms
            # If arrived intra-bar, close price cannot be used until bar.close_time_ms!
            if fill_bar.open_time_ms >= earliest_fill_ms:
                ref_price = fill_bar.open
                actual_fill_time_ms = max(earliest_fill_ms, fill_bar.open_time_ms)
            else:
                ref_price = fill_bar.close
                actual_fill_time_ms = max(earliest_fill_ms, fill_bar.close_time_ms)

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
                observation_timestamp_ms=obs_ts,
                decision_timestamp_ms=dec_ts,
                settlement_timestamp_ms=actual_fill_time_ms,
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
                    observation_timestamp_ms=obs_ts,
                    decision_timestamp_ms=dec_ts,
                    settlement_timestamp_ms=earliest_fill_ms,
                    rejection_reason="INVALID_LIMIT_PRICE",
                )

            # If order already expired before it could reach the exchange
            if earliest_fill_ms > expiration_ms:
                return ExecutionResult(
                    signal_timestamp_ms=signal_timestamp_ms,
                    order_timestamp_ms=order_timestamp_ms,
                    fill_timestamp_ms=expiration_ms,
                    fill_price=0.0,
                    filled_quantity=0.0,
                    is_filled=False,
                    side=side,
                    observation_timestamp_ms=obs_ts,
                    decision_timestamp_ms=dec_ts,
                    settlement_timestamp_ms=expiration_ms,
                    rejection_reason="LIMIT_EXPIRED_UNFILLED",
                )

            for bar in future_candles:
                if bar.open_time_ms > expiration_ms:
                    break
                if bar.close_time_ms < earliest_fill_ms:
                    continue

                # Causal boundary: if bar began before order arrived on exchange,
                # OHLC extreme cannot establish whether it occurred post-arrival.
                if bar.open_time_ms < earliest_fill_ms:
                    continue

                # Liquidity check
                if bar.volume <= 0:
                    continue

                if side == 1:  # BUY LIMIT
                    # Trades strictly through limit price (low < limit_price)
                    if bar.low < limit_price - 1e-8:
                        fill_time = max(earliest_fill_ms, bar.open_time_ms)
                        if fill_time > expiration_ms:
                            break
                        notional = limit_price * desired_quantity
                        fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=True)
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
                            observation_timestamp_ms=obs_ts,
                            decision_timestamp_ms=dec_ts,
                            settlement_timestamp_ms=fill_time,
                            metadata={"traded_through": True, "bar_low": bar.low},
                        )
                    # Touching exact price (bar.low == limit_price): requires certain queue fill
                    elif abs(bar.low - limit_price) <= 1e-8 and self.limit_fill_prob_on_touch >= 1.0:
                        fill_time = max(earliest_fill_ms, bar.open_time_ms)
                        if fill_time > expiration_ms:
                            break
                        notional = limit_price * desired_quantity
                        fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=True)
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
                            observation_timestamp_ms=obs_ts,
                            decision_timestamp_ms=dec_ts,
                            settlement_timestamp_ms=fill_time,
                            metadata={"traded_touch": True},
                        )

                else:  # SELL LIMIT
                    # Trades strictly through limit price (high > limit_price)
                    if bar.high > limit_price + 1e-8:
                        fill_time = max(earliest_fill_ms, bar.open_time_ms)
                        if fill_time > expiration_ms:
                            break
                        notional = limit_price * desired_quantity
                        fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=True)
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
                            observation_timestamp_ms=obs_ts,
                            decision_timestamp_ms=dec_ts,
                            settlement_timestamp_ms=fill_time,
                            metadata={"traded_through": True, "bar_high": bar.high},
                        )
                    elif abs(bar.high - limit_price) <= 1e-8 and self.limit_fill_prob_on_touch >= 1.0:
                        fill_time = max(earliest_fill_ms, bar.open_time_ms)
                        if fill_time > expiration_ms:
                            break
                        notional = limit_price * desired_quantity
                        fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=True)
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
                            observation_timestamp_ms=obs_ts,
                            decision_timestamp_ms=dec_ts,
                            settlement_timestamp_ms=fill_time,
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
                observation_timestamp_ms=obs_ts,
                decision_timestamp_ms=dec_ts,
                settlement_timestamp_ms=expiration_ms,
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
            observation_timestamp_ms=obs_ts,
            decision_timestamp_ms=dec_ts,
            settlement_timestamp_ms=earliest_fill_ms,
            rejection_reason=f"UNSUPPORTED_ORDER_TYPE_{order_type}",
        )
