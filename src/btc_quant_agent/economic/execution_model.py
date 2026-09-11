from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..domain import Candle
from .fee_model import FeeModel, SlippageMode
from .policy import OrderType


def _finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


class ConditionalTriggerTime(StrEnum):
    """The only trigger-time claims supported by the OHLC execution contract."""

    BAR_OPEN_KNOWN = "BAR_OPEN_KNOWN"
    INTRABAR_UNKNOWN = "INTRABAR_UNKNOWN"


LIMIT_INTRABAR_TOUCH_AMBIGUOUS = "LIMIT_INTRABAR_TOUCH_AMBIGUOUS_NOT_TESTABLE"
CAUSAL_LIQUIDITY_UNAVAILABLE = "CAUSAL_LIQUIDITY_UNAVAILABLE"
CAUSAL_LIQUIDITY_NOT_YET_AVAILABLE = "CAUSAL_LIQUIDITY_NOT_YET_AVAILABLE"


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
        order_submission_latency_ms: int = 0,
    ) -> None:
        self.fee_model = fee_model or FeeModel()
        self.decision_latency_ms = decision_latency_ms
        self.exchange_latency_ms = exchange_latency_ms
        self.limit_fill_prob_on_touch = limit_fill_prob_on_touch
        if (
            type(order_submission_latency_ms) is not int
            or order_submission_latency_ms < 0
        ):
            raise ValueError("order_submission_latency_ms must be a nonnegative integer")
        self.order_submission_latency_ms = order_submission_latency_ms

    def _taker_fill_price(
        self,
        *,
        reference_price: float,
        quantity: float,
        side: int,
        fill_timestamp_ms: int,
        current_spread_bps: float | None,
        causal_liquidity_volume_base: float | None,
        causal_liquidity_available_at_ms: int | None,
        completed_volume_base: float | None = None,
    ) -> tuple[float | None, str, str | None]:
        """Price a taker fill from information available at the fill boundary."""
        if self.fee_model.slippage_mode != SlippageMode.SPREAD_AND_IMPACT:
            price = self.fee_model.effective_fill_price(
                reference_price=reference_price,
                quantity=quantity,
                side=side,
                is_maker=False,
                current_spread_bps=current_spread_bps,
            )
            return price, "NOT_USED", None
        if self.fee_model.impact_coefficient == 0:
            price = self.fee_model.effective_fill_price(
                reference_price=reference_price,
                quantity=quantity,
                side=side,
                is_maker=False,
                current_spread_bps=current_spread_bps,
            )
            return price, "NOT_REQUIRED_ZERO_IMPACT", None

        liquidity = causal_liquidity_volume_base
        liquidity_source = "TIMESTAMPED_CAUSAL_LIQUIDITY"
        if liquidity is not None:
            assert causal_liquidity_available_at_ms is not None
            if causal_liquidity_available_at_ms > fill_timestamp_ms:
                return None, "FUTURE_LIQUIDITY_REJECTED", CAUSAL_LIQUIDITY_NOT_YET_AVAILABLE
        elif completed_volume_base is not None:
            if completed_volume_base <= 0:
                return None, "COMPLETED_AT_FILL", "INSUFFICIENT_LIQUIDITY"
            liquidity = completed_volume_base
            liquidity_source = "COMPLETED_AT_FILL"
        elif self.fee_model.max_slippage_bps is not None:
            # With no causal participation denominator, force the already-bound
            # adverse cap instead of silently treating impact as zero.
            price = self.fee_model.effective_fill_price(
                reference_price=reference_price,
                quantity=quantity,
                side=side,
                is_maker=False,
                current_spread_bps=None,
            )
            return price, "DECLARED_MAX_SLIPPAGE_SCENARIO", None
        else:
            return None, "MISSING", CAUSAL_LIQUIDITY_UNAVAILABLE

        price = self.fee_model.effective_fill_price(
            reference_price=reference_price,
            quantity=quantity,
            side=side,
            is_maker=False,
            current_spread_bps=current_spread_bps,
            bar_volume_base=liquidity,
        )
        return price, liquidity_source, None

    def simulate_conditional_market_fill(
        self,
        *,
        armed_timestamp_ms: int,
        trigger_observation_timestamp_ms: int,
        side: int,
        desired_quantity: float,
        reference_price: float,
        trigger_bar: Candle,
        trigger_time: ConditionalTriggerTime,
        current_spread_bps: float | None = None,
    ) -> ExecutionResult:
        """Fill a standing stop/target without converting it to a close-time order.

        The order/decision timestamp is when the conditional was armed. For an
        OHLC-only intrabar touch, the exact trigger time is deliberately not
        reconstructed: the bar close is used as the latest observable fill
        timestamp while the economic fill reference remains the standing trigger
        level. A gap trigger has known bar-open time and uses the actual open.
        """
        trigger_time = ConditionalTriggerTime(trigger_time)
        if type(armed_timestamp_ms) is not int or armed_timestamp_ms <= 0:
            raise ValueError("armed_timestamp_ms must be a positive integer")
        if (
            type(trigger_observation_timestamp_ms) is not int
            or trigger_observation_timestamp_ms <= 0
        ):
            raise ValueError("trigger_observation_timestamp_ms must be a positive integer")
        if armed_timestamp_ms > trigger_bar.open_time_ms:
            raise ValueError("standing conditional must be armed no later than trigger bar open")
        if not math.isfinite(reference_price) or reference_price <= 0:
            raise ValueError("reference_price must be finite and positive")
        if current_spread_bps is not None and (
            not math.isfinite(current_spread_bps) or current_spread_bps < 0
        ):
            raise ValueError("current_spread_bps must be finite and nonnegative when provided")

        if trigger_time == ConditionalTriggerTime.BAR_OPEN_KNOWN:
            if trigger_observation_timestamp_ms != trigger_bar.open_time_ms:
                raise ValueError("BAR_OPEN_KNOWN trigger must be observed at bar open")
            if not math.isclose(reference_price, trigger_bar.open, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("BAR_OPEN_KNOWN trigger must use the actual bar open")
        elif trigger_observation_timestamp_ms != trigger_bar.close_time_ms:
            raise ValueError("INTRABAR_UNKNOWN trigger must be observed at bar close")

        fill_timestamp_ms = trigger_observation_timestamp_ms
        if desired_quantity <= 0 or not math.isfinite(desired_quantity):
            return ExecutionResult(
                signal_timestamp_ms=armed_timestamp_ms,
                order_timestamp_ms=armed_timestamp_ms,
                fill_timestamp_ms=fill_timestamp_ms,
                fill_price=0.0,
                filled_quantity=0.0,
                is_filled=False,
                side=side,
                observation_timestamp_ms=armed_timestamp_ms,
                decision_timestamp_ms=armed_timestamp_ms,
                settlement_timestamp_ms=fill_timestamp_ms,
                rejection_reason="INVALID_QUANTITY",
            )
        if side not in (-1, 1):
            return ExecutionResult(
                signal_timestamp_ms=armed_timestamp_ms,
                order_timestamp_ms=armed_timestamp_ms,
                fill_timestamp_ms=fill_timestamp_ms,
                fill_price=0.0,
                filled_quantity=0.0,
                is_filled=False,
                side=side,
                observation_timestamp_ms=armed_timestamp_ms,
                decision_timestamp_ms=armed_timestamp_ms,
                settlement_timestamp_ms=fill_timestamp_ms,
                rejection_reason="INVALID_SIDE",
            )
        if not math.isfinite(trigger_bar.volume) or trigger_bar.volume <= 0:
            return ExecutionResult(
                signal_timestamp_ms=armed_timestamp_ms,
                order_timestamp_ms=armed_timestamp_ms,
                fill_timestamp_ms=fill_timestamp_ms,
                fill_price=0.0,
                filled_quantity=0.0,
                is_filled=False,
                side=side,
                observation_timestamp_ms=armed_timestamp_ms,
                decision_timestamp_ms=armed_timestamp_ms,
                settlement_timestamp_ms=fill_timestamp_ms,
                rejection_reason="INSUFFICIENT_LIQUIDITY",
            )

        execution_spread_bps = current_spread_bps
        if self.fee_model.slippage_mode == SlippageMode.SPREAD_AND_IMPACT:
            # Exact trigger-time liquidity/impact is unavailable in OHLC data.
            # Use the declared all-in adverse scenario rather than allowing the
            # completed bar's future volume to make a standing fill cheaper.
            if self.fee_model.max_slippage_bps is None:
                raise ValueError(
                    "SPREAD_AND_IMPACT standing conditionals require a declared "
                    "max_slippage_bps adverse scenario"
                )
            execution_spread_bps = None

        fill_price = self.fee_model.effective_fill_price(
            reference_price=reference_price,
            quantity=desired_quantity,
            side=side,
            is_maker=False,
            current_spread_bps=execution_spread_bps,
            bar_volume_base=trigger_bar.volume,
        )
        slippage_cost = abs(fill_price - reference_price) * desired_quantity
        fee_usdt = self.fee_model.calculate_fee(fill_price * desired_quantity, is_maker=False)
        spread_source = (
            "DECLARED_MAX_SLIPPAGE_SCENARIO"
            if self.fee_model.slippage_mode == SlippageMode.SPREAD_AND_IMPACT
            else "NOT_USED"
        )

        return ExecutionResult(
            signal_timestamp_ms=armed_timestamp_ms,
            order_timestamp_ms=armed_timestamp_ms,
            fill_timestamp_ms=fill_timestamp_ms,
            fill_price=fill_price,
            filled_quantity=desired_quantity,
            is_filled=True,
            side=side,
            observation_timestamp_ms=armed_timestamp_ms,
            decision_timestamp_ms=armed_timestamp_ms,
            settlement_timestamp_ms=fill_timestamp_ms,
            is_maker=False,
            fee_usdt=fee_usdt,
            slippage_usdt=slippage_cost,
            metadata={
                "ref_price": reference_price,
                "standing_order_armed_ms": armed_timestamp_ms,
                "trigger_observation_timestamp_ms": trigger_observation_timestamp_ms,
                "trigger_time_semantics": trigger_time.value,
                "spread_evidence": spread_source,
                "causal_spread_bps": current_spread_bps,
            },
        )

    def simulate_order(
        self,
        signal_timestamp_ms: int,
        side: int,  # +1 = BUY, -1 = SELL
        desired_quantity: float,
        order_type: OrderType,
        future_candles: Sequence[Candle],
        limit_price: float | None = None,
        time_in_force_ms: int = 60_000,
        current_spread_bps: float | None = None,
        observation_timestamp_ms: int | None = None,
        max_fill_notional: float | None = None,
        observable_open_executable_price: float | None = None,
        observable_open_executable_timestamp_ms: int | None = None,
        causal_liquidity_volume_base: float | None = None,
        causal_liquidity_available_at_ms: int | None = None,
    ) -> ExecutionResult:
        obs_ts = observation_timestamp_ms if observation_timestamp_ms is not None else signal_timestamp_ms
        if obs_ts > signal_timestamp_ms:
            raise ValueError(
                f"observation_timestamp_ms ({obs_ts}) cannot be after signal_timestamp_ms ({signal_timestamp_ms})"
            )
        if max_fill_notional is not None and (
            not math.isfinite(max_fill_notional) or max_fill_notional <= 0
        ):
            raise ValueError("max_fill_notional must be finite and positive when provided")

        if (observable_open_executable_price is None) != (
            observable_open_executable_timestamp_ms is None
        ):
            raise ValueError(
                "observable opening executable price and timestamp must be provided together"
            )
        if observable_open_executable_price is not None and (
            not math.isfinite(observable_open_executable_price)
            or observable_open_executable_price <= 0
        ):
            raise ValueError("observable opening executable price must be finite and positive")
        if observable_open_executable_timestamp_ms is not None and (
            type(observable_open_executable_timestamp_ms) is not int
            or observable_open_executable_timestamp_ms <= 0
        ):
            raise ValueError("observable opening executable timestamp must be a positive integer")
        if (causal_liquidity_volume_base is None) != (
            causal_liquidity_available_at_ms is None
        ):
            raise ValueError("causal liquidity value and availability timestamp are required together")
        if causal_liquidity_volume_base is not None and (
            not math.isfinite(causal_liquidity_volume_base)
            or causal_liquidity_volume_base <= 0
        ):
            raise ValueError("causal liquidity volume must be finite and positive")
        if causal_liquidity_available_at_ms is not None and (
            type(causal_liquidity_available_at_ms) is not int
            or causal_liquidity_available_at_ms <= 0
        ):
            raise ValueError("causal liquidity availability timestamp must be a positive integer")

        dec_ts = signal_timestamp_ms + self.decision_latency_ms
        order_timestamp_ms = dec_ts + self.order_submission_latency_ms
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

            # Causal execution: if arrived before/at open, fill at open price at bar.open_time_ms
            # If arrived intra-bar, close price cannot be used until bar.close_time_ms!
            if fill_bar.open_time_ms >= earliest_fill_ms:
                ref_price = fill_bar.open
                actual_fill_time_ms = max(earliest_fill_ms, fill_bar.open_time_ms)
                completed_volume_base = None
            else:
                ref_price = fill_bar.close
                actual_fill_time_ms = max(earliest_fill_ms, fill_bar.close_time_ms)
                completed_volume_base = fill_bar.volume

            fill_price, liquidity_source, liquidity_rejection = self._taker_fill_price(
                reference_price=ref_price,
                quantity=desired_quantity,
                side=side,
                fill_timestamp_ms=actual_fill_time_ms,
                current_spread_bps=current_spread_bps,
                causal_liquidity_volume_base=causal_liquidity_volume_base,
                causal_liquidity_available_at_ms=causal_liquidity_available_at_ms,
                completed_volume_base=completed_volume_base,
            )
            if liquidity_rejection is not None:
                return ExecutionResult(
                    signal_timestamp_ms=signal_timestamp_ms,
                    order_timestamp_ms=order_timestamp_ms,
                    fill_timestamp_ms=actual_fill_time_ms,
                    fill_price=0.0,
                    filled_quantity=0.0,
                    is_filled=False,
                    side=side,
                    observation_timestamp_ms=obs_ts,
                    decision_timestamp_ms=dec_ts,
                    settlement_timestamp_ms=actual_fill_time_ms,
                    rejection_reason=liquidity_rejection,
                    metadata={"liquidity_evidence": liquidity_source},
                )
            assert fill_price is not None
            filled_quantity = desired_quantity
            notional_cap_applied = False
            if (
                max_fill_notional is not None
                and fill_price * filled_quantity > max_fill_notional
            ):
                # The economic order is bounded by the notional reserved at
                # admission. Price movement may reduce filled base quantity,
                # but can never turn an admitted order into a gross-cap breach.
                filled_quantity = max_fill_notional / fill_price
                notional_cap_applied = True

            slippage_cost = abs(fill_price - ref_price) * filled_quantity
            notional = fill_price * filled_quantity
            fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=False)
            if self.fee_model.slippage_mode == SlippageMode.SPREAD_AND_IMPACT:
                spread_source = (
                    "DECLARED_MAX_SLIPPAGE_SCENARIO"
                    if liquidity_source == "DECLARED_MAX_SLIPPAGE_SCENARIO"
                    else (
                        "CAUSAL_SPREAD"
                        if current_spread_bps is not None
                        else "DECLARED_MAX_SLIPPAGE_SCENARIO"
                    )
                )
            else:
                spread_source = "NOT_USED"

            return ExecutionResult(
                signal_timestamp_ms=signal_timestamp_ms,
                order_timestamp_ms=order_timestamp_ms,
                fill_timestamp_ms=actual_fill_time_ms,
                fill_price=fill_price,
                filled_quantity=filled_quantity,
                is_filled=True,
                side=side,
                is_maker=False,
                fee_usdt=fee_usdt,
                slippage_usdt=slippage_cost,
                observation_timestamp_ms=obs_ts,
                decision_timestamp_ms=dec_ts,
                settlement_timestamp_ms=actual_fill_time_ms,
                metadata={
                    "ref_price": ref_price,
                    "candle_open_ms": fill_bar.open_time_ms,
                    "spread_evidence": spread_source,
                    "liquidity_evidence": liquidity_source,
                    "causal_liquidity_available_at_ms": causal_liquidity_available_at_ms,
                    "requested_quantity": desired_quantity,
                    "max_fill_notional": max_fill_notional,
                    "notional_cap_applied": notional_cap_applied,
                },
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

                # A bar open is the only price in this OHLC contract whose
                # timestamp is known exactly.  If the order was executable at
                # that instant, marketability is observable without consulting
                # the completed bar's later high/low.  Expiry is inclusive:
                # fill_time == expiration_ms is valid, while a later fill is not.
                opening_executable_price = bar.open
                opening_price_evidence = "OHLC_OPEN"
                if observable_open_executable_timestamp_ms == bar.open_time_ms:
                    assert observable_open_executable_price is not None
                    opening_executable_price = observable_open_executable_price
                    opening_price_evidence = "TIMESTAMPED_EXECUTABLE_QUOTE"

                open_marketable = (
                    side == 1 and opening_executable_price <= limit_price + 1e-8
                ) or (
                    side == -1 and opening_executable_price >= limit_price - 1e-8
                )
                if open_marketable:
                    fill_time = bar.open_time_ms
                    if fill_time > expiration_ms:
                        break
                    fill_price, liquidity_source, liquidity_rejection = (
                        self._taker_fill_price(
                            reference_price=opening_executable_price,
                            quantity=desired_quantity,
                            side=side,
                            fill_timestamp_ms=fill_time,
                            current_spread_bps=current_spread_bps,
                            causal_liquidity_volume_base=causal_liquidity_volume_base,
                            causal_liquidity_available_at_ms=(
                                causal_liquidity_available_at_ms
                            ),
                        )
                    )
                    if liquidity_rejection is not None:
                        return ExecutionResult(
                            signal_timestamp_ms=signal_timestamp_ms,
                            order_timestamp_ms=order_timestamp_ms,
                            fill_timestamp_ms=fill_time,
                            fill_price=0.0,
                            filled_quantity=0.0,
                            is_filled=False,
                            side=side,
                            observation_timestamp_ms=obs_ts,
                            decision_timestamp_ms=dec_ts,
                            settlement_timestamp_ms=fill_time,
                            rejection_reason=liquidity_rejection,
                            metadata={"liquidity_evidence": liquidity_source},
                        )
                    assert fill_price is not None
                    limit_respected = (side == 1 and fill_price <= limit_price + 1e-8) or (
                        side == -1 and fill_price >= limit_price - 1e-8
                    )
                    if not limit_respected:
                        return ExecutionResult(
                            signal_timestamp_ms=signal_timestamp_ms,
                            order_timestamp_ms=order_timestamp_ms,
                            fill_timestamp_ms=fill_time,
                            fill_price=0.0,
                            filled_quantity=0.0,
                            is_filled=False,
                            side=side,
                            observation_timestamp_ms=obs_ts,
                            decision_timestamp_ms=dec_ts,
                            settlement_timestamp_ms=fill_time,
                            rejection_reason="MARKETABLE_LIMIT_LIQUIDITY_INSUFFICIENT",
                            metadata={"liquidity_evidence": liquidity_source},
                        )
                    filled_quantity = desired_quantity
                    notional_cap_applied = False
                    if (
                        max_fill_notional is not None
                        and fill_price * filled_quantity > max_fill_notional
                    ):
                        filled_quantity = max_fill_notional / fill_price
                        notional_cap_applied = True
                    notional = fill_price * filled_quantity
                    fee_usdt = self.fee_model.calculate_fee(notional=notional, is_maker=False)
                    slippage_cost = abs(fill_price - opening_executable_price) * filled_quantity
                    return ExecutionResult(
                        signal_timestamp_ms=signal_timestamp_ms,
                        order_timestamp_ms=order_timestamp_ms,
                        fill_timestamp_ms=fill_time,
                        fill_price=fill_price,
                        filled_quantity=filled_quantity,
                        is_filled=True,
                        side=side,
                        is_maker=False,
                        fee_usdt=fee_usdt,
                        slippage_usdt=slippage_cost,
                        observation_timestamp_ms=obs_ts,
                        decision_timestamp_ms=dec_ts,
                        settlement_timestamp_ms=fill_time,
                        metadata={
                            "limit_price": limit_price,
                            "observable_open": bar.open,
                            "opening_executable_price": opening_executable_price,
                            "opening_executable_timestamp_ms": bar.open_time_ms,
                            "opening_price_evidence": opening_price_evidence,
                            "liquidity_evidence": liquidity_source,
                            "causal_liquidity_available_at_ms": (
                                causal_liquidity_available_at_ms
                            ),
                            "execution_time_semantics": "BAR_OPEN_MARKETABLE",
                            "requested_quantity": desired_quantity,
                            "max_fill_notional": max_fill_notional,
                            "notional_cap_applied": notional_cap_applied,
                        },
                    )

                if side == 1:
                    traded_through = bar.low < limit_price - 1e-8
                    exact_touch = abs(bar.low - limit_price) <= 1e-8
                    observed_extreme = bar.low
                else:
                    traded_through = bar.high > limit_price + 1e-8
                    exact_touch = abs(bar.high - limit_price) <= 1e-8
                    observed_extreme = bar.high

                # A completed-bar extremum proves only that a touch occurred
                # somewhere in [open, close].  It cannot timestamp that touch
                # relative to expiry, funding, or another material event.  A
                # deterministic exact-touch fill remains eligible only when the
                # declared queue rule is certain; otherwise the historical
                # no-fill queue behavior is preserved.
                deterministic_touch = exact_touch and self.limit_fill_prob_on_touch >= 1.0
                if traded_through or deterministic_touch:
                    outcome_time = min(expiration_ms, bar.close_time_ms)
                    return ExecutionResult(
                        signal_timestamp_ms=signal_timestamp_ms,
                        order_timestamp_ms=order_timestamp_ms,
                        fill_timestamp_ms=outcome_time,
                        fill_price=0.0,
                        filled_quantity=0.0,
                        is_filled=False,
                        side=side,
                        observation_timestamp_ms=obs_ts,
                        decision_timestamp_ms=dec_ts,
                        settlement_timestamp_ms=outcome_time,
                        rejection_reason=LIMIT_INTRABAR_TOUCH_AMBIGUOUS,
                        metadata={
                            "limit_price": limit_price,
                            "observed_extreme": observed_extreme,
                            "ambiguity_window_open_ms": bar.open_time_ms,
                            "ambiguity_window_close_ms": bar.close_time_ms,
                            "expiration_ms": expiration_ms,
                            "touch_kind": "THROUGH" if traded_through else "EXACT_TOUCH",
                            "execution_time_semantics": "INTRABAR_UNKNOWN",
                        },
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
