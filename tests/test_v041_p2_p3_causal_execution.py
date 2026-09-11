from __future__ import annotations

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.execution_model import (
    LIMIT_INTRABAR_TOUCH_AMBIGUOUS,
    ExecutionModel,
    ExecutionResult,
)
from btc_quant_agent.economic.fee_model import FeeModel, SlippageMode
from btc_quant_agent.economic.funding import FundingSettlement
from btc_quant_agent.economic.order import Order
from btc_quant_agent.economic.policy import (
    EntryRule,
    ExitRule,
    OrderType,
    PositionSizing,
    RiskBudget,
    SizingType,
    TradePolicy,
)
from btc_quant_agent.economic.signal import InformationSignal
from btc_quant_agent.economic.simulator import EconomicSimulationEngine
from btc_quant_agent.economic.trade_event import TradeAction, TradeEvent


def _bar(
    open_time_ms: int = 1000,
    o: float = 100.0,
    h: float | None = None,
    low: float | None = None,
    c: float = 100.0,
    volume: float = 1000.0,
    duration: int = 1000,
    symbol: str = "BTCUSDT",
    interval: str = "15m",
) -> Candle:
    high = max(h if h is not None else max(o, c), o, c)
    low_price = min(low if low is not None else min(o, c), o, c)
    return Candle(
        symbol=symbol,
        interval=interval,
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + duration - 1,
        open=o,
        high=high,
        low=low_price,
        close=c,
        volume=volume,
    )


def _sig(
    timestamp_ms: int = 1000,
    direction: int = 1,
    strength: float = 1.0,
    signal_id: str = "SIG_1",
    asset: str = "BTCUSDT",
) -> InformationSignal:
    return InformationSignal(
        signal_id=signal_id,
        experiment_id="EXP_TEST",
        timestamp_ms=timestamp_ms,
        asset=asset,
        direction=direction,
        strength=strength,
    )


ZERO_FEE = FeeModel(maker_fee_rate=0.0, taker_fee_rate=0.0, slippage_mode=SlippageMode.ZERO)
ZERO_LATENCY_EXEC = ExecutionModel(fee_model=ZERO_FEE, decision_latency_ms=0, exchange_latency_ms=0)
DEFAULT_POLICY = TradePolicy(
    policy_id="POL_BASE",
    name="Base Test Policy",
    position_sizing=PositionSizing(sizing_type=SizingType.FIXED_NOTIONAL, target_notional=100.0),
    risk_budget=RiskBudget(max_gross_exposure_usdt=100_000.0, max_open_positions=1),
)


# =====================================================================
# 1. TIMELINE VALIDATION TESTS (P2)
# =====================================================================


def test_timeline_decision_before_observation_fails_closed() -> None:
    """Decision timestamp cannot occur before observation timestamp."""
    with pytest.raises(ValueError, match="decision.*cannot.*before.*observation"):
        Order(
            order_id="ORD_1",
            asset="BTCUSDT",
            side=1,
            desired_quantity=1.0,
            order_type=OrderType.MARKET,
            observation_timestamp_ms=2000,
            decision_timestamp_ms=1000,
            order_timestamp_ms=2000,
        )

    with pytest.raises(ValueError, match="decision.*cannot occur before.*observation"):
        TradeEvent(
            timestamp_ms=3000,
            action=TradeAction.OPEN_LONG,
            price=100.0,
            quantity=1.0,
            fee_usdt=0.0,
            funding_usdt=0.0,
            position_after=1.0,
            cash_after=100_000.0,
            observation_timestamp_ms=2000,
            decision_timestamp_ms=1000,
        )


def test_timeline_order_before_decision_fails_closed() -> None:
    """Order timestamp cannot occur before decision timestamp."""
    with pytest.raises(ValueError, match="order.*cannot.*before.*decision"):
        Order(
            order_id="ORD_2",
            asset="BTCUSDT",
            side=1,
            desired_quantity=1.0,
            order_type=OrderType.MARKET,
            observation_timestamp_ms=1000,
            decision_timestamp_ms=2000,
            order_timestamp_ms=1500,
        )

    with pytest.raises(ValueError, match="order.*cannot occur before.*decision"):
        TradeEvent(
            timestamp_ms=3000,
            action=TradeAction.OPEN_LONG,
            price=100.0,
            quantity=1.0,
            fee_usdt=0.0,
            funding_usdt=0.0,
            position_after=1.0,
            cash_after=100_000.0,
            observation_timestamp_ms=1000,
            decision_timestamp_ms=2000,
            order_timestamp_ms=1500,
        )


def test_timeline_fill_before_order_fails_closed() -> None:
    """Fill timestamp cannot occur before order timestamp."""
    with pytest.raises(ValueError, match="fill.*cannot.*before.*order"):
        Order(
            order_id="ORD_3",
            asset="BTCUSDT",
            side=1,
            desired_quantity=1.0,
            order_type=OrderType.MARKET,
            observation_timestamp_ms=1000,
            decision_timestamp_ms=1000,
            order_timestamp_ms=2000,
            fill_timestamp_ms=1500,
        )

    with pytest.raises(ValueError, match="fill timestamp.*cannot occur before.*order"):
        TradeEvent(
            timestamp_ms=1500,
            action=TradeAction.OPEN_LONG,
            price=100.0,
            quantity=1.0,
            fee_usdt=0.0,
            funding_usdt=0.0,
            position_after=1.0,
            cash_after=100_000.0,
            order_timestamp_ms=2000,
        )

    with pytest.raises(ValueError, match="Timestamp ordering violation.*order.*fill"):
        ExecutionResult(
            signal_timestamp_ms=1000,
            order_timestamp_ms=2000,
            fill_timestamp_ms=1500,
            fill_price=100.0,
            filled_quantity=1.0,
            is_filled=True,
            side=1,
        )


def test_timeline_settlement_before_fill_fails_closed() -> None:
    """Settlement timestamp cannot occur before fill timestamp."""
    with pytest.raises(ValueError, match="settlement.*cannot.*before.*fill"):
        Order(
            order_id="ORD_4",
            asset="BTCUSDT",
            side=1,
            desired_quantity=1.0,
            order_type=OrderType.MARKET,
            observation_timestamp_ms=1000,
            decision_timestamp_ms=1000,
            order_timestamp_ms=1000,
            fill_timestamp_ms=2000,
            settlement_timestamp_ms=1500,
        )

    with pytest.raises(ValueError, match="settlement.*cannot occur before.*fill"):
        TradeEvent(
            timestamp_ms=2000,
            action=TradeAction.OPEN_LONG,
            price=100.0,
            quantity=1.0,
            fee_usdt=0.0,
            funding_usdt=0.0,
            position_after=1.0,
            cash_after=100_000.0,
            settlement_timestamp_ms=1500,
        )

    with pytest.raises(ValueError, match="Timestamp ordering violation.*fill.*settlement"):
        ExecutionResult(
            signal_timestamp_ms=1000,
            order_timestamp_ms=1000,
            fill_timestamp_ms=2000,
            settlement_timestamp_ms=1500,
            fill_price=100.0,
            filled_quantity=1.0,
            is_filled=True,
            side=1,
        )


def test_timeline_deterministic_equal_timestamps_funding_before_fill() -> None:
    """Explicit tie-break rule: FundingSettlement -> Order/Fill -> MarkUpdate at equal timestamp.

    If funding occurs at timestamp 2000 and trade opens at timestamp 2000,
    funding settles BEFORE the fill, so funding is NOT charged on the new position.
    """
    bars = [_bar(1000), _bar(2000), _bar(3000)]
    # Signal at 2000 with 0 latency fills at 2000
    sig = _sig(2000)
    # Funding at 2000
    funding = [FundingSettlement(timestamp_ms=2000, mark_price=100.0, funding_rate=0.01)]

    sim = EconomicSimulationEngine(
        policy=DEFAULT_POLICY,
        execution_model=ZERO_LATENCY_EXEC,
        fee_model=ZERO_FEE,
        initial_cash=100_000.0,
    )
    res = sim.simulate(candles=bars, signals=[sig], funding_events=funding)

    # Funding was 0 because position was 0 before 2000 fill
    assert res.total_funding_usdt == 0.0
    # Exactly one trade event at 2000
    assert len(res.trade_events) == 1
    assert res.trade_events[0].timestamp_ms == 2000


# =====================================================================
# 2. CAUSAL EXECUTION & FILL SEMANTICS (P2 / P3 / B2 / H2)
# =====================================================================


def test_execution_no_retrospective_price_leakage_future_close() -> None:
    """Intra-bar market order cannot back-date future candle close to arrival time.

    Bar is [1000, 1999] with c=120. Order arrives at 1650.
    Fill timestamp cannot be 1650; it must be at or after close_time_ms (1999).
    """
    ex = ExecutionModel(fee_model=ZERO_FEE, decision_latency_ms=500, exchange_latency_ms=150)
    bar = _bar(open_time_ms=1000, duration=1000, o=100.0, c=120.0)

    # Signal at 1000 -> order at 1500 -> arrives at exchange at 1650
    result = ex.simulate_order(
        signal_timestamp_ms=1000,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.MARKET,
        future_candles=[bar],
    )

    assert result.is_filled
    assert result.fill_price == 120.0
    # Fill timestamp must NOT be 1650 (back-dated close). It must be bar close time 1999!
    assert result.fill_timestamp_ms == 1999
    assert result.fill_timestamp_ms >= bar.close_time_ms


def test_execution_limit_extreme_cannot_precede_arrival() -> None:
    """Limit order arriving intra-bar cannot claim execution on that bar's prior extreme.

    Bar is [1000, 2999] with low=90. Order arrives at 2350 (limit=95).
    OHLC cannot prove low occurred after 2350 without intra-bar data.
    """
    ex = ExecutionModel(fee_model=ZERO_FEE, decision_latency_ms=500, exchange_latency_ms=150)
    bar = _bar(open_time_ms=1000, duration=2000, h=105.0, low=90.0)

    result = ex.simulate_order(
        signal_timestamp_ms=1700,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[bar],
        limit_price=95.0,
    )

    # Must NOT fill on a bar that started before arrival
    assert not result.is_filled
    assert result.rejection_reason == "LIMIT_EXPIRED_UNFILLED"


def test_execution_limit_fill_after_expiry_rejected() -> None:
    """Limit order cannot fill after expiration."""
    ex = ExecutionModel(fee_model=ZERO_FEE, decision_latency_ms=500, exchange_latency_ms=150)
    bar = _bar(open_time_ms=1000, low=90.0)

    # Order time 1500, time_in_force 100 -> expires at 1600. Earliest fill is 1650.
    result = ex.simulate_order(
        signal_timestamp_ms=1000,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[bar],
        limit_price=95.0,
        time_in_force_ms=100,
    )

    assert not result.is_filled
    assert result.rejection_reason == "LIMIT_EXPIRED_UNFILLED"


def test_execution_zero_suffix_volume_does_not_gate_open_but_rejects_close_fill() -> None:
    """Future zero volume is unavailable at open; completed zero volume rejects at close."""
    ex = ExecutionModel(fee_model=ZERO_FEE, decision_latency_ms=0, exchange_latency_ms=0)
    zero_vol_bar = _bar(open_time_ms=1000, low=90.0, volume=0.0)

    res_limit = ex.simulate_order(
        signal_timestamp_ms=1000,
        side=1,
        desired_quantity=10.0,
        order_type=OrderType.LIMIT,
        future_candles=[zero_vol_bar],
        limit_price=95.0,
    )
    assert not res_limit.is_filled
    assert res_limit.rejection_reason == "LIMIT_EXPIRED_UNFILLED"

    res_market = ex.simulate_order(
        signal_timestamp_ms=1000,
        side=1,
        desired_quantity=10.0,
        order_type=OrderType.MARKET,
        future_candles=[zero_vol_bar],
    )
    assert res_market.is_filled

    res_market_at_close = ex.simulate_order(
        signal_timestamp_ms=1001,
        side=1,
        desired_quantity=10.0,
        order_type=OrderType.MARKET,
        future_candles=[zero_vol_bar],
    )
    assert not res_market_at_close.is_filled
    assert res_market_at_close.rejection_reason == "INSUFFICIENT_LIQUIDITY"


def test_execution_touch_probability_deterministic_queue_rule() -> None:
    """A certain queue touch still cannot invent the intrabar touch timestamp."""
    ex_default = ExecutionModel(fee_model=ZERO_FEE, decision_latency_ms=0, exchange_latency_ms=0, limit_fill_prob_on_touch=0.20)
    ex_99 = ExecutionModel(fee_model=ZERO_FEE, decision_latency_ms=0, exchange_latency_ms=0, limit_fill_prob_on_touch=0.99)
    ex_100 = ExecutionModel(fee_model=ZERO_FEE, decision_latency_ms=0, exchange_latency_ms=0, limit_fill_prob_on_touch=1.0)

    touch_bar = _bar(open_time_ms=1000, low=95.0)

    assert not ex_default.simulate_order(1000, 1, 1.0, OrderType.LIMIT, [touch_bar], limit_price=95.0).is_filled
    assert not ex_99.simulate_order(1000, 1, 1.0, OrderType.LIMIT, [touch_bar], limit_price=95.0).is_filled
    certain = ex_100.simulate_order(
        1000, 1, 1.0, OrderType.LIMIT, [touch_bar], limit_price=95.0
    )
    assert not certain.is_filled
    assert certain.rejection_reason == LIMIT_INTRABAR_TOUCH_AMBIGUOUS


def test_execution_signal_without_fill_leaves_ledger_unchanged() -> None:
    """Signal that produces no fill leaves portfolio cash and positions unchanged."""
    bars = [_bar(1000, low=100.0)]
    sig = _sig(1000)
    policy = TradePolicy(
        policy_id="POL_NOFILL",
        name="No Fill Policy",
        entry_rule=EntryRule(order_type=OrderType.LIMIT, limit_offset_bps=500),  # buy limit at 95; low is 100
        position_sizing=PositionSizing(sizing_type=SizingType.FIXED_NOTIONAL, target_notional=100.0),
    )

    sim = EconomicSimulationEngine(policy=policy, initial_cash=100_000.0)
    res = sim.simulate(candles=bars, signals=[sig])

    assert res.total_trades == 0
    assert len(res.trade_events) == 0
    assert res.final_equity == 100_000.0
    assert res.net_pnl_usdt == 0.0


def test_execution_future_marketable_open_fill_remains_pending_until_timestamp() -> None:
    """A later observable marketable open may schedule a causal future fill."""
    bars = [
        _bar(1000, low=100.0),
        _bar(2000, o=110.0, low=100.0, c=110.0),
        _bar(3000, o=100.0, low=90.0, c=95.0),
    ]
    sig = _sig(1000)
    policy = TradePolicy(
        policy_id="POL_PENDING",
        name="Pending Fill Policy",
        entry_rule=EntryRule(order_type=OrderType.LIMIT, time_in_force_ms=10_000),
        exit_rule=ExitRule(take_profit_pct=0.01),
        position_sizing=PositionSizing(sizing_type=SizingType.FIXED_NOTIONAL, target_notional=100.0),
    )

    sim = EconomicSimulationEngine(policy=policy, fee_model=ZERO_FEE, initial_cash=100_000.0)
    res = sim.simulate(candles=bars, signals=[sig])

    assert len(res.trade_events) >= 1
    assert res.trade_events[0].timestamp_ms == 3000
    assert res.trade_events[0].metadata["execution_time_semantics"] == (
        "BAR_OPEN_MARKETABLE"
    )
    assert res.equity_curve[0][1] == 100_000.0
    assert res.equity_curve[1][1] == 100_000.0


def test_execution_signal_asset_mismatch_rejected() -> None:
    """Signal for ETHUSDT on BTCUSDT data fails closed and executes zero trades."""
    bars = [_bar(1000, symbol="BTCUSDT")]
    sig = _sig(1000, asset="ETHUSDT")

    sim = EconomicSimulationEngine(policy=DEFAULT_POLICY, initial_cash=100_000.0)
    res = sim.simulate(candles=bars, signals=[sig])

    assert res.total_trades == 0
    assert len(res.trade_events) == 0


def test_execution_limit_offset_bps_applied_correctly() -> None:
    """Entry rule limit_offset_bps shifts buy limit passively."""
    policy = TradePolicy(
        policy_id="POL_OFFSET",
        name="Offset Policy",
        entry_rule=EntryRule(order_type=OrderType.LIMIT, limit_offset_bps=500),  # 5% passive buy: 100 * 0.95 = 95
        position_sizing=PositionSizing(sizing_type=SizingType.FIXED_NOTIONAL, target_notional=100.0),
    )
    # Low is 99, so buy limit at 95 does NOT fill
    bars = [_bar(1000, o=100.0, low=99.0)]
    sig = _sig(1000)

    sim = EconomicSimulationEngine(policy=policy, initial_cash=100_000.0)
    res = sim.simulate(candles=bars, signals=[sig])

    assert len(res.trade_events) == 0
    assert res.total_trades == 0


# =====================================================================
# 3. EXIT SEMANTICS & BOUNDARIES (P3 / B3)
# =====================================================================


def test_exit_ambiguous_stop_target_collision_conservative_stop_first_long() -> None:
    """When both SL and TP are breached in same candle for LONG, conservative stop is taken.

    Entry at 100. SL 5% (95), TP 5% (105).
    Bar 2 has high=110 (+10%) and low=90 (-10%).
    Simulation MUST take Stop Loss (loss), never falsely report profit (+20).
    """
    collision_policy = TradePolicy(
        policy_id="POL_COLLISION",
        name="Collision Policy",
        exit_rule=ExitRule(stop_loss_pct=0.05, take_profit_pct=0.05),
        position_sizing=PositionSizing(sizing_type=SizingType.FIXED_NOTIONAL, target_notional=100.0),
    )
    bars = [
        _bar(1000, o=100.0, c=100.0),
        _bar(2000, o=100.0, h=110.0, low=90.0, c=95.0),
        _bar(3000, o=120.0, c=120.0),
    ]
    sig = _sig(1000)

    sim = EconomicSimulationEngine(
        policy=collision_policy,
        execution_model=ZERO_LATENCY_EXEC,
        fee_model=ZERO_FEE,
        initial_cash=100_000.0,
    )
    res = sim.simulate(candles=bars, signals=[sig])

    assert res.total_trades == 1
    assert res.losing_trades == 1
    assert res.winning_trades == 0
    # Exited at stop loss 95, losing 5 on 1 unit
    assert res.trade_events[-1].action == TradeAction.CLOSE_LONG
    assert res.trade_events[-1].price == 95.0
    assert res.net_pnl_usdt == -5.0


def test_exit_ambiguous_stop_target_collision_conservative_stop_first_short() -> None:
    """When both SL and TP are breached in same candle for SHORT, conservative stop is taken.

    Entry short at 100. SL 5% (105), TP 5% (95).
    Bar 2 has high=110 and low=90.
    Must take Stop Loss at 105, not Take Profit at 95.
    """
    collision_policy = TradePolicy(
        policy_id="POL_COLLISION_SHORT",
        name="Collision Short Policy",
        exit_rule=ExitRule(stop_loss_pct=0.05, take_profit_pct=0.05),
        position_sizing=PositionSizing(sizing_type=SizingType.FIXED_NOTIONAL, target_notional=100.0),
    )
    bars = [
        _bar(1000, o=100.0, c=100.0),
        _bar(2000, o=100.0, h=110.0, low=90.0, c=105.0),
        _bar(3000, o=80.0, c=80.0),
    ]
    sig = _sig(1000, direction=-1)

    sim = EconomicSimulationEngine(
        policy=collision_policy,
        execution_model=ZERO_LATENCY_EXEC,
        fee_model=ZERO_FEE,
        initial_cash=100_000.0,
    )
    res = sim.simulate(candles=bars, signals=[sig])

    assert res.total_trades == 1
    assert res.losing_trades == 1
    assert res.trade_events[-1].action == TradeAction.CLOSE_SHORT
    assert res.trade_events[-1].price == 105.0
    assert res.net_pnl_usdt == -5.0


def test_exit_gap_stop_executed_at_gap_open_not_fabricated_price() -> None:
    """Gap protection: market opens below stop loss price.

    Entry at 100. Stop loss is 95.
    Next bar opens at 80 (low=80, high=80, close=80).
    Execution price MUST be 80, NEVER the fabricated 95 where no liquidity traded.
    """
    sl_policy = TradePolicy(
        policy_id="POL_GAP",
        name="Gap SL Policy",
        exit_rule=ExitRule(stop_loss_pct=0.05),
        position_sizing=PositionSizing(sizing_type=SizingType.FIXED_NOTIONAL, target_notional=100.0),
    )
    bars = [
        _bar(1000, o=100.0, c=100.0),
        _bar(2000, o=80.0, h=80.0, low=80.0, c=80.0),
    ]
    sig = _sig(1000)

    sim = EconomicSimulationEngine(
        policy=sl_policy,
        execution_model=ZERO_LATENCY_EXEC,
        fee_model=ZERO_FEE,
        initial_cash=100_000.0,
    )
    res = sim.simulate(candles=bars, signals=[sig])

    assert res.total_trades == 1
    close_event = res.trade_events[-1]
    assert close_event.action == TradeAction.CLOSE_LONG
    # Gap execution: price must be 80, not 95!
    assert close_event.price == 80.0
    assert res.net_pnl_usdt == -20.0


def test_exit_entry_bar_stop_target_evaluated_when_opened_at_open() -> None:
    """Entry at bar open exposes the position to stop/target on the SAME entry bar.

    Zero latency entry at 1000 open (100). Same bar has high=110, low=90.
    Position MUST be evaluated and stopped out on this bar.
    """
    collision_policy = TradePolicy(
        policy_id="POL_ENTRY_BAR",
        name="Entry Bar Collision Policy",
        exit_rule=ExitRule(stop_loss_pct=0.05, take_profit_pct=0.05),
        position_sizing=PositionSizing(sizing_type=SizingType.FIXED_NOTIONAL, target_notional=100.0),
    )
    bars = [_bar(1000, o=100.0, h=110.0, low=90.0, c=95.0)]
    sig = _sig(1000)

    sim = EconomicSimulationEngine(
        policy=collision_policy,
        execution_model=ZERO_LATENCY_EXEC,
        fee_model=ZERO_FEE,
        initial_cash=100_000.0,
    )
    res = sim.simulate(candles=bars, signals=[sig])

    assert res.total_trades == 1
    assert len(res.trade_events) == 2  # 1 OPEN + 1 CLOSE
    assert res.trade_events[0].action == TradeAction.OPEN_LONG
    assert res.trade_events[1].action == TradeAction.CLOSE_LONG
    assert res.trade_events[1].price == 95.0
    assert res.net_pnl_usdt == -5.0


def test_exit_funding_temporal_causality_entry_and_exit() -> None:
    """Funding settlements are charged only while holding the position.

    Entry at 1000, Exit at 2000.
    Funding at 1500 is charged.
    Funding at 2500 (after exit) is NOT charged.
    """
    bars = [
        _bar(1000, o=100.0, c=100.0),
        _bar(2000, o=80.0, c=80.0),  # Gaps down, exits on open at 2000
        _bar(3000, o=80.0, c=80.0),
    ]
    sig = _sig(1000)
    funding = [
        FundingSettlement(timestamp_ms=1500, mark_price=100.0, funding_rate=0.01),  # -1 USDT paid
        FundingSettlement(timestamp_ms=2500, mark_price=80.0, funding_rate=0.01),   # 0 charged (already exited)
    ]
    policy = TradePolicy(
        policy_id="POL_FUND_CAUSAL",
        name="Funding Causality Policy",
        exit_rule=ExitRule(stop_loss_pct=0.05),
        position_sizing=PositionSizing(sizing_type=SizingType.FIXED_NOTIONAL, target_notional=100.0),
    )

    sim = EconomicSimulationEngine(
        policy=policy,
        execution_model=ZERO_LATENCY_EXEC,
        fee_model=ZERO_FEE,
        initial_cash=100_000.0,
    )
    res = sim.simulate(candles=bars, signals=[sig], funding_events=funding)

    # Only 1500 funding is charged (-1), 2500 funding is NOT charged (0)
    assert res.total_funding_usdt == -1.0
