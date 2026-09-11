"""B02 regressions for opening-fill causal liquidity and H3."""

from __future__ import annotations

from typing import Any

import pytest
from helpers_v042_semantic_goldens import case_by_id, load_goldens

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.execution_model import (
    CAUSAL_LIQUIDITY_NOT_YET_AVAILABLE,
    CAUSAL_LIQUIDITY_UNAVAILABLE,
    ExecutionModel,
)
from btc_quant_agent.economic.fee_model import FeeModel, SlippageMode
from btc_quant_agent.economic.policy import OrderType


def _bar(*, volume: float) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        interval="15m",
        open_time_ms=1_000,
        close_time_ms=900_999,
        open=100.0,
        high=110.0,
        low=90.0,
        close=100.0,
        volume=volume,
        quote_volume=volume * 100.0,
    )


def _model(*, cap_bps: float | None = 100.0, impact: float = 0.1) -> ExecutionModel:
    fees = FeeModel(
        maker_fee_rate=0.0002,
        taker_fee_rate=0.001,
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        impact_coefficient=impact,
        max_slippage_bps=cap_bps,
    )
    return ExecutionModel(fee_model=fees, decision_latency_ms=0, exchange_latency_ms=0)


def _simulate(
    *,
    order_type: OrderType,
    side: int,
    future_volume: float,
    liquidity: float | None = 500.0,
    available_at_ms: int | None = 1_000,
    model: ExecutionModel | None = None,
) -> Any:
    kwargs: dict[str, Any] = {}
    if order_type is OrderType.LIMIT:
        kwargs.update(
            limit_price=101.0 if side == 1 else 99.0,
            observable_open_executable_price=100.0,
            observable_open_executable_timestamp_ms=1_000,
        )
    return (model or _model()).simulate_order(
        signal_timestamp_ms=1_000,
        side=side,
        desired_quantity=1.0,
        order_type=order_type,
        future_candles=[_bar(volume=future_volume)],
        current_spread_bps=10.0,
        max_fill_notional=102.0,
        causal_liquidity_volume_base=liquidity,
        causal_liquidity_available_at_ms=available_at_ms,
        **kwargs,
    )


@pytest.mark.parametrize("side", [1, -1])
def test_d_h3_market_suffix_volume_is_invariant(side: int) -> None:
    golden = case_by_id(load_goldens(), "D-H3-FUTURE-VOLUME-INVARIANCE")
    common = golden["inputs"]["common_prior_state"]
    small = _simulate(
        order_type=OrderType.MARKET,
        side=side,
        future_volume=float(golden["inputs"]["run_a_future_suffix_volume"]),
        liquidity=float(common["prior_timestamped_liquidity"]),
        available_at_ms=int(common["order_time_ms"]),
    )
    large = _simulate(
        order_type=OrderType.MARKET,
        side=side,
        future_volume=float(golden["inputs"]["run_b_future_suffix_volume"]),
        liquidity=float(common["prior_timestamped_liquidity"]),
        available_at_ms=int(common["order_time_ms"]),
    )
    assert golden["expected"]["correct_behavior"] == "OPENING_FILL_PRICE_AND_COST_IDENTICAL"
    assert small.is_filled and large.is_filled
    assert (small.fill_price, small.slippage_usdt, small.fee_usdt) == (
        large.fill_price,
        large.slippage_usdt,
        large.fee_usdt,
    )
    assert small.metadata["liquidity_evidence"] == "TIMESTAMPED_CAUSAL_LIQUIDITY"
    assert small.metadata["causal_liquidity_volume_base"] == float(
        common["prior_timestamped_liquidity"]
    )
    assert small.metadata["causal_liquidity_available_at_ms"] == int(
        common["order_time_ms"]
    )


@pytest.mark.parametrize("side", [1, -1])
def test_marketable_limit_uses_same_suffix_invariant_taker_path(side: int) -> None:
    small = _simulate(order_type=OrderType.LIMIT, side=side, future_volume=1.0)
    large = _simulate(order_type=OrderType.LIMIT, side=side, future_volume=1_000_000.0)
    assert small.is_filled and large.is_filled
    assert not small.is_maker and not large.is_maker
    assert (small.fill_price, small.slippage_usdt, small.fee_usdt) == (
        large.fill_price,
        large.slippage_usdt,
        large.fee_usdt,
    )
    assert small.slippage_usdt > 0
    assert small.fee_usdt == pytest.approx(small.fill_price * 0.001)


def test_different_available_liquidity_legitimately_changes_impact() -> None:
    thin = _simulate(
        order_type=OrderType.MARKET,
        side=1,
        future_volume=5_000.0,
        liquidity=10.0,
    )
    deep = _simulate(
        order_type=OrderType.MARKET,
        side=1,
        future_volume=5_000.0,
        liquidity=1_000.0,
    )
    assert thin.is_filled and deep.is_filled
    assert thin.fill_price > deep.fill_price


def test_liquidity_exactly_at_fill_is_allowed_and_plus_one_ms_is_rejected() -> None:
    exact = _simulate(
        order_type=OrderType.MARKET,
        side=1,
        future_volume=10_000.0,
        available_at_ms=1_000,
    )
    future = _simulate(
        order_type=OrderType.MARKET,
        side=1,
        future_volume=10_000.0,
        available_at_ms=1_001,
    )
    assert exact.is_filled
    assert not future.is_filled
    assert future.rejection_reason == CAUSAL_LIQUIDITY_NOT_YET_AVAILABLE


@pytest.mark.parametrize("liquidity", [0.0, -1.0, float("nan"), float("inf")])
def test_malformed_liquidity_fails_closed(liquidity: float) -> None:
    with pytest.raises(ValueError, match="causal liquidity volume"):
        _simulate(
            order_type=OrderType.MARKET,
            side=1,
            future_volume=10_000.0,
            liquidity=liquidity,
        )


def test_partial_liquidity_observation_is_rejected() -> None:
    with pytest.raises(ValueError, match="required together"):
        _simulate(
            order_type=OrderType.MARKET,
            side=1,
            future_volume=10_000.0,
            liquidity=None,
            available_at_ms=1_000,
        )


@pytest.mark.parametrize("side", [1, -1])
def test_missing_liquidity_uses_bound_adverse_scenario_not_future_volume(side: int) -> None:
    small = _simulate(
        order_type=OrderType.MARKET,
        side=side,
        future_volume=1.0,
        liquidity=None,
        available_at_ms=None,
    )
    large = _simulate(
        order_type=OrderType.MARKET,
        side=side,
        future_volume=1_000_000.0,
        liquidity=None,
        available_at_ms=None,
    )
    assert small.is_filled and large.is_filled
    assert small.fill_price == large.fill_price == pytest.approx(100.0 * (1 + side * 0.01))
    assert small.metadata["liquidity_evidence"] == "DECLARED_MAX_SLIPPAGE_SCENARIO"
    assert small.metadata["spread_evidence"] == "DECLARED_MAX_SLIPPAGE_SCENARIO"
    assert small.metadata["declared_max_slippage_bps"] == 100.0


def test_missing_liquidity_without_adverse_scenario_is_typed_refusal() -> None:
    result = _simulate(
        order_type=OrderType.MARKET,
        side=1,
        future_volume=10_000.0,
        liquidity=None,
        available_at_ms=None,
        model=_model(cap_bps=None),
    )
    assert not result.is_filled
    assert result.rejection_reason == CAUSAL_LIQUIDITY_UNAVAILABLE


def test_marketable_limit_refuses_impact_price_outside_limit() -> None:
    result = _simulate(
        order_type=OrderType.LIMIT,
        side=1,
        future_volume=10_000.0,
        liquidity=None,
        available_at_ms=None,
        model=_model(cap_bps=200.0),
    )
    assert not result.is_filled
    assert result.rejection_reason == "MARKETABLE_LIMIT_LIQUIDITY_INSUFFICIENT"


def test_fixed_bps_opening_fill_does_not_require_or_read_bar_volume() -> None:
    fees = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.FIXED_BPS,
        fixed_slippage_bps=10.0,
    )
    model = ExecutionModel(fee_model=fees, decision_latency_ms=0, exchange_latency_ms=0)
    empty = _simulate(
        order_type=OrderType.MARKET,
        side=1,
        future_volume=0.0,
        liquidity=None,
        available_at_ms=None,
        model=model,
    )
    suffix = _simulate(
        order_type=OrderType.MARKET,
        side=1,
        future_volume=1_000_000.0,
        liquidity=None,
        available_at_ms=None,
        model=model,
    )
    assert empty.is_filled and suffix.is_filled
    assert empty.fill_price == suffix.fill_price == pytest.approx(100.1)
