"""Batch B-A integration checks at the formal information-set boundary."""

from __future__ import annotations

from dataclasses import replace

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic import (
    CausalLiquidityRejectionError,
    EconomicSimulationEngine,
    EntryRule,
    ExecutionModel,
    FeeModel,
    InformationSignal,
    OrderType,
    PositionSizing,
    SlippageMode,
    TradePolicy,
)
from btc_quant_agent.economic.acceptance_verifier import bind_runtime_market_data


def _bar() -> Candle:
    return Candle(
        symbol="BTCUSDT",
        interval="15m",
        open_time_ms=1_000,
        close_time_ms=900_999,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=10_000.0,
        quote_volume=1_000_000.0,
        closed=True,
        available_at_ms=901_000,
    )


def test_future_liquidity_fails_before_complete_economic_result() -> None:
    fees = FeeModel(
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        impact_coefficient=0.01,
        max_slippage_bps=None,
    )
    engine = EconomicSimulationEngine(
        policy=TradePolicy(
            policy_id="BA_FUTURE_LIQUIDITY",
            name="B-A future liquidity refusal",
            entry_rule=EntryRule(order_type=OrderType.LIMIT, limit_offset_bps=-100.0),
            position_sizing=PositionSizing(target_notional=100.0),
        ),
        fee_model=fees,
        execution_model=ExecutionModel(
            fee_model=fees,
            decision_latency_ms=0,
            exchange_latency_ms=0,
        ),
    )
    signal = InformationSignal(
        signal_id="BA_FUTURE_LIQ",
        experiment_id="BA",
        timestamp_ms=1_000,
        asset="BTCUSDT",
        direction=1,
        strength=1.0,
        metadata={
            "spread_bps": 1.0,
            "liquidity_volume_base": 1_000.0,
            "liquidity_available_at_ms": 1_001,
        },
    )
    with pytest.raises(CausalLiquidityRejectionError, match="timestamped liquidity"):
        engine.simulate([_bar()], [signal])


def test_unclosed_input_cannot_cross_formal_binding_even_if_economics_complete() -> None:
    candle = replace(_bar(), closed=False)
    summary = EconomicSimulationEngine(
        policy=TradePolicy(policy_id="BA_CLOSED", name="B-A closed boundary")
    ).simulate([candle], [])
    assert summary.formal_complete
    with pytest.raises(ValueError, match="not explicitly closed"):
        bind_runtime_market_data(summary.to_dict(), [candle])
