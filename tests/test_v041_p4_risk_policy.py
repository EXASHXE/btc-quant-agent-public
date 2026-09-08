from __future__ import annotations

from typing import Any

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.execution_model import ExecutionModel
from btc_quant_agent.economic.fee_model import FeeModel, SlippageMode
from btc_quant_agent.economic.policy import (
    EntryRule,
    ExitRule,
    MarketStateFilter,
    OrderType,
    PositionSizing,
    RiskBudget,
    SizingType,
    TradePolicy,
)
from btc_quant_agent.economic.signal import InformationSignal
from btc_quant_agent.economic.simulator import EconomicSimulationEngine
from btc_quant_agent.economic.trade_event import TradeAction


def _create_candle(
    timestamp_ms: int = 1_000_000,
    open_price: float = 100.0,
    high_price: float | None = None,
    low_price: float | None = None,
    close_price: float = 100.0,
    volume: float = 100.0,
    quote_volume: float = 0.0,
    duration_ms: int = 1000,
    symbol: str = "BTCUSDT",
) -> Candle:
    hp = max(open_price, close_price) if high_price is None else high_price
    lp = min(open_price, close_price) if low_price is None else low_price
    return Candle(
        symbol=symbol,
        interval="1s",
        open_time_ms=timestamp_ms,
        close_time_ms=timestamp_ms + duration_ms - 1,
        open=open_price,
        high=hp,
        low=lp,
        close=close_price,
        volume=volume,
        quote_volume=quote_volume,
        closed=True,
    )


def _create_signal(
    timestamp_ms: int = 1_000_000,
    direction: int = 1,
    strength: float = 1.0,
    asset: str = "BTCUSDT",
    metadata: dict[str, Any] | None = None,
) -> InformationSignal:
    return InformationSignal(
        signal_id=f"sig_{timestamp_ms}_{direction}",
        experiment_id="test_exp",
        timestamp_ms=timestamp_ms,
        asset=asset,
        direction=direction,
        strength=strength,
        metadata=metadata or {},
    )


ZERO_FEES = FeeModel(maker_fee_rate=0.0, taker_fee_rate=0.0, slippage_mode=SlippageMode.ZERO)


# =====================================================================
# 1. H1 / P4 INDEPENDENT REVIEW REGRESSIONS
# =====================================================================


def test_ignored_risk_and_filters_full_reproduction() -> None:
    """Direct regression for 'ignored_risk_and_filters' defect.

    In v0.4.0, max_open_positions=0, max_gross_exposure_usdt=1, min_volume_usdt_15m=1e20,
    and allowed_regimes=('FORBIDDEN',) were all ignored, opening a 100 USDT position on a zero-volume bar.
    In v0.4.1C, all constraints are enforced fail-closed, resulting in 0 trades.
    """
    policy = TradePolicy(
        policy_id="test_p4_ignored",
        name="Ignored Risk Regression",
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_gross_exposure_usdt=1.0, max_open_positions=0),
        market_filter=MarketStateFilter(min_volume_usdt_15m=1e20, allowed_regimes=("FORBIDDEN",)),
    )
    bar = _create_candle(volume=0.0)
    sig = _create_signal()

    engine = EconomicSimulationEngine(policy=policy, fee_model=ZERO_FEES, initial_cash=100_000.0)
    summary = engine.simulate(candles=[bar], signals=[sig])

    assert len(summary.trade_events) == 0
    assert summary.total_trades == 0
    assert summary.final_equity == 100_000.0


def test_drawdown_halt_ignored_full_reproduction() -> None:
    """Direct regression for 'drawdown_halt_ignored' defect.

    In v0.4.0, a drawdown halt threshold of 0.00001 (0.001%) was ignored after a 10 USDT loss,
    allowing a 3rd trade to be opened at t=3000.
    In v0.4.1C, sticky drawdown halt blocks all subsequent entries, allowing exactly 2 trade events (open + close).
    """
    dd_policy = TradePolicy(
        policy_id="test_p4_dd",
        name="Drawdown Halt Regression",
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_drawdown_stop_pct=0.00001),
    )
    bars = [
        _create_candle(timestamp_ms=1000, open_price=100.0, close_price=100.0),
        _create_candle(timestamp_ms=2000, open_price=90.0, close_price=90.0),
        _create_candle(timestamp_ms=3000, open_price=90.0, close_price=90.0),
    ]
    signals = [
        _create_signal(timestamp_ms=1000, direction=1),
        _create_signal(timestamp_ms=2000, direction=-1),
        _create_signal(timestamp_ms=3000, direction=1),
    ]

    engine = EconomicSimulationEngine(policy=dd_policy, fee_model=ZERO_FEES, initial_cash=100_000.0)
    summary = engine.simulate(candles=bars, signals=signals)

    # Only first trade (open at 100, close at 90 via reversal) should occur
    assert len(summary.trade_events) == 2
    assert summary.total_trades == 1
    assert summary.trade_events[0].action == TradeAction.OPEN_LONG
    assert summary.trade_events[1].action == TradeAction.CLOSE_LONG
    assert summary.trade_events[1].realized_pnl_usdt == -10.0
    assert summary.max_drawdown_pct >= 0.0001


def test_missing_atr_full_allocation_reproduction() -> None:
    """Direct regression for 'missing_atr_full_allocation' defect.

    In v0.4.0, missing/zero/negative ATR under VOLATILITY_SCALED sizing defaulted to max allocation.
    In v0.4.1C, calculate_quantity raises ValueError for non-positive or non-finite ATR.
    """
    policy = TradePolicy(
        policy_id="test_vol",
        name="Volatility Scaled Test",
        position_sizing=PositionSizing(sizing_type=SizingType.VOLATILITY_SCALED, risk_fraction=0.01),
    )
    for invalid_atr in (None, 0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="VOLATILITY_SCALED sizing requires a finite positive current_atr"):
            policy.calculate_quantity(current_price=100.0, portfolio_equity=1000.0, current_atr=invalid_atr)


def test_risk_fraction_without_stop_loss_reproduction() -> None:
    """Direct regression for 'risk_fraction_without_stop' defect.

    In v0.4.0, RISK_FRACTION sizing defaulted to 0.02 if stop_loss_pct was None.
    In v0.4.1C:
    1. TradePolicy construction with RISK_FRACTION and no/invalid stop_loss_pct raises ValueError.
    2. calculate_quantity raises ValueError if stop_loss_pct is missing or non-positive.
    """
    # Construction check
    with pytest.raises(ValueError, match="RISK_FRACTION sizing requires explicit positive stop_loss_pct"):
        TradePolicy(
            policy_id="test_rf_nostop",
            name="RF No Stop",
            exit_rule=ExitRule(stop_loss_pct=None),
            position_sizing=PositionSizing(sizing_type=SizingType.RISK_FRACTION),
        )

    with pytest.raises(ValueError, match="stop_loss_pct"):
        ExitRule(stop_loss_pct=0.0)


# =====================================================================
# 2. RISK BUDGET ENFORCEMENT (Open Positions, Gross Exposure, Caps)
# =====================================================================


def test_max_open_positions_enforced() -> None:
    """max_open_positions=0 permits 0 trades, max_open_positions=1 allows only 1 concurrent position."""
    # 0 open positions allowed
    policy0 = TradePolicy(
        policy_id="test_p0",
        name="Zero Pos",
        risk_budget=RiskBudget(max_open_positions=0),
    )
    engine0 = EconomicSimulationEngine(policy=policy0, fee_model=ZERO_FEES)
    summary0 = engine0.simulate(
        candles=[_create_candle(timestamp_ms=1000)],
        signals=[_create_signal(timestamp_ms=1000, direction=1)],
    )
    assert len(summary0.trade_events) == 0

    # 1 open position allowed: cannot open a 2nd position while 1st is active
    policy1 = TradePolicy(
        policy_id="test_p1",
        name="One Pos",
        risk_budget=RiskBudget(max_open_positions=1),
        exit_rule=ExitRule(decay_exit_on_signal_reversal=False),  # no reversal exit
    )
    engine1 = EconomicSimulationEngine(policy=policy1, fee_model=ZERO_FEES)
    bars = [
        _create_candle(timestamp_ms=1000),
        _create_candle(timestamp_ms=2000),
    ]
    signals = [
        _create_signal(timestamp_ms=1000, direction=1),
        _create_signal(timestamp_ms=2000, direction=1),  # same direction repeat
    ]
    summary1 = engine1.simulate(candles=bars, signals=signals)
    assert len(summary1.trade_events) == 1  # only first signal executed


def test_max_gross_exposure_pre_order_rejection() -> None:
    """Candidate order whose notional exceeds max_gross_exposure_usdt is rejected pre-order."""
    policy = TradePolicy(
        policy_id="test_gross_pre",
        name="Gross Pre",
        position_sizing=PositionSizing(target_notional=25_000.0),
        risk_budget=RiskBudget(max_gross_exposure_usdt=10_000.0),
    )
    engine = EconomicSimulationEngine(policy=policy, fee_model=ZERO_FEES)
    summary = engine.simulate(
        candles=[_create_candle(timestamp_ms=1000, open_price=100.0)],
        signals=[_create_signal(timestamp_ms=1000, direction=1)],
    )
    assert len(summary.trade_events) == 0


def test_max_gross_exposure_post_fill_rejection() -> None:
    """If actual fill notional exceeds max_gross_exposure_usdt (e.g. slippage / price jump), fill is rejected."""
    policy = TradePolicy(
        policy_id="test_gross_post",
        name="Gross Post",
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_gross_exposure_usdt=105.0),
    )
    # Market order at open=100 with fixed slippage pushing fill price to 110 (notional 110 > 105)
    slippage_fees = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.FIXED_BPS,
        fixed_slippage_bps=1000.0,  # 10% slippage -> 100 * 1.10 = 110
    )
    engine = EconomicSimulationEngine(policy=policy, fee_model=slippage_fees)
    summary = engine.simulate(
        candles=[_create_candle(timestamp_ms=1000, open_price=100.0, high_price=120.0)],
        signals=[_create_signal(timestamp_ms=1000, direction=1)],
    )
    assert len(summary.trade_events) == 0


def test_pending_orders_reserve_risk_preventing_oversubscription() -> None:
    """Pending orders reserve open position count and gross exposure, preventing oversubscription."""
    # Market order with latency so fill happens at bar.close_time_ms (t=1999)
    policy = TradePolicy(
        policy_id="test_pending_risk",
        name="Pending Risk",
        entry_rule=EntryRule(order_type=OrderType.MARKET),
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_open_positions=1, max_gross_exposure_usdt=150.0),
    )
    exec_model = ExecutionModel(fee_model=ZERO_FEES, decision_latency_ms=200, exchange_latency_ms=100)
    engine = EconomicSimulationEngine(policy=policy, execution_model=exec_model, fee_model=ZERO_FEES)

    # Bar 1: t=1000..1999. Signal 1 at t=1000 arrives at t=1300, fill scheduled at t=1999.
    # Signal 2 arrives at t=1500 while Signal 1 is pending.
    bars = [
        _create_candle(timestamp_ms=1000, open_price=100.0, close_price=100.0),
        _create_candle(timestamp_ms=2000, open_price=100.0, close_price=100.0),
    ]
    signals = [
        _create_signal(timestamp_ms=1000, direction=1),
        _create_signal(timestamp_ms=1500, direction=1),
    ]
    summary = engine.simulate(candles=bars, signals=signals)

    # Exactly 1 trade should be opened, Signal 2 must be rejected because Signal 1 has reserved the position slot
    assert len([e for e in summary.trade_events if e.action == TradeAction.OPEN_LONG]) == 1


# =====================================================================
# 3. MARKET STATE FILTERS (Volume, Regime, Spread)
# =====================================================================


def test_market_state_filter_min_volume() -> None:
    """Filter rejects entry when volume is below declared threshold using causal volume evidence."""
    policy = TradePolicy(
        policy_id="test_filter_vol",
        name="Min Volume Filter",
        market_filter=MarketStateFilter(min_volume_usdt_15m=10_000.0),
    )
    engine = EconomicSimulationEngine(policy=policy, fee_model=ZERO_FEES)

    # Causal volume evidence = 5,000 (< 10,000) -> reject
    bar_low_vol = _create_candle(timestamp_ms=1000, quote_volume=5000.0)
    summary_low = engine.simulate(
        candles=[bar_low_vol],
        signals=[_create_signal(timestamp_ms=1000, metadata={"volume_usdt": 5000.0})],
    )
    assert len(summary_low.trade_events) == 0

    # Causal volume evidence = 15,000 (>= 10,000) -> accept
    bar_high_vol = _create_candle(timestamp_ms=2000, quote_volume=15000.0)
    summary_high = engine.simulate(
        candles=[bar_high_vol],
        signals=[_create_signal(timestamp_ms=2000, metadata={"volume_usdt": 15000.0})],
    )
    assert len(summary_high.trade_events) == 1


def test_market_state_filter_allowed_regimes() -> None:
    """Filter rejects entry when regime is not in allowed_regimes or is missing."""
    policy = TradePolicy(
        policy_id="test_filter_regime",
        name="Regime Filter",
        market_filter=MarketStateFilter(allowed_regimes=("TREND_UP", "BREAKOUT")),
    )
    engine = EconomicSimulationEngine(policy=policy, fee_model=ZERO_FEES)
    bar = _create_candle(timestamp_ms=1000)

    # Missing regime in metadata -> reject fail-closed
    summary_none = engine.simulate(candles=[bar], signals=[_create_signal(timestamp_ms=1000, metadata={})])
    assert len(summary_none.trade_events) == 0

    # Forbidden regime -> reject
    summary_range = engine.simulate(
        candles=[bar], signals=[_create_signal(timestamp_ms=1000, metadata={"regime": "RANGE"})]
    )
    assert len(summary_range.trade_events) == 0

    # Allowed regime -> accept
    summary_trend = engine.simulate(
        candles=[bar], signals=[_create_signal(timestamp_ms=1000, metadata={"regime": "TREND_UP"})]
    )
    assert len(summary_trend.trade_events) == 1


def test_market_state_filter_max_spread() -> None:
    """Filter rejects entry when spread exceeds max_spread_bps."""
    policy = TradePolicy(
        policy_id="test_filter_spread",
        name="Spread Filter",
        market_filter=MarketStateFilter(max_spread_bps=5.0),
    )
    engine = EconomicSimulationEngine(policy=policy, fee_model=ZERO_FEES)
    bar = _create_candle(timestamp_ms=1000)

    # Spread 8 bps > 5 bps -> reject
    summary_wide = engine.simulate(
        candles=[bar], signals=[_create_signal(timestamp_ms=1000, metadata={"spread_bps": 8.0})]
    )
    assert len(summary_wide.trade_events) == 0

    # Spread 2 bps <= 5 bps -> accept
    summary_tight = engine.simulate(
        candles=[bar], signals=[_create_signal(timestamp_ms=1000, metadata={"spread_bps": 2.0})]
    )
    assert len(summary_tight.trade_events) == 1


def test_market_state_filter_nonfinite_inputs_fail_closed() -> None:
    """Non-finite or negative spread or volume must fail closed."""
    policy = TradePolicy(policy_id="test_finite", name="Finite Check")
    sig = _create_signal()

    assert not policy.should_enter(sig, current_spread_bps=float("nan"))
    assert not policy.should_enter(sig, current_spread_bps=float("inf"))
    assert not policy.should_enter(sig, current_spread_bps=-1.0)
    assert not policy.should_enter(sig, current_volume_usdt=float("nan"))
    assert not policy.should_enter(sig, current_volume_usdt=float("inf"))
    assert not policy.should_enter(sig, current_volume_usdt=-10.0)


# =====================================================================
# 4. SIGNAL & ASSET VALIDATION
# =====================================================================


def test_wrong_asset_rejection() -> None:
    """Signal asset differing from candle symbol is rejected."""
    policy = TradePolicy(policy_id="test_asset", name="Asset Match")
    engine = EconomicSimulationEngine(policy=policy, fee_model=ZERO_FEES)

    candle = _create_candle(timestamp_ms=1000, symbol="BTCUSDT")
    eth_signal = _create_signal(timestamp_ms=1000, asset="ETHUSDT")

    summary = engine.simulate(candles=[candle], signals=[eth_signal])
    assert len(summary.trade_events) == 0
    assert summary.total_trades == 0


def test_drawdown_halt_permits_existing_position_exit() -> None:
    """While in drawdown halt, existing positions can still exit normally."""
    policy = TradePolicy(
        policy_id="test_exit_during_halt",
        name="Exit During Halt",
        exit_rule=ExitRule(stop_loss_pct=0.05),
        risk_budget=RiskBudget(max_drawdown_stop_pct=0.00001),  # tight halt
    )
    engine = EconomicSimulationEngine(policy=policy, fee_model=ZERO_FEES)
    bars = [
        _create_candle(timestamp_ms=1000, open_price=100.0, close_price=100.0),
        _create_candle(timestamp_ms=2000, open_price=94.0, low_price=94.0, close_price=94.0),
    ]
    signals = [_create_signal(timestamp_ms=1000, direction=1)]

    summary = engine.simulate(candles=bars, signals=signals)
    # Entry at 100, Stop Loss exit at 95 (or 94)
    assert len(summary.trade_events) == 2
    assert summary.total_trades == 1
    assert summary.trade_events[1].action == TradeAction.CLOSE_LONG


# =====================================================================
# 5. INPUT VALIDATION & FAIL-CLOSED CHECKS
# =====================================================================


def test_invalid_policy_configurations_fail_before_mutation() -> None:
    """All dataclasses must validate finiteness, positivity, and legal bounds."""
    # EntryRule
    with pytest.raises(ValueError, match="min_signal_strength"):
        EntryRule(min_signal_strength=-1.0)
    with pytest.raises(ValueError, match="time_in_force_ms"):
        EntryRule(time_in_force_ms=0)
    with pytest.raises(ValueError, match="allowed_directions"):
        EntryRule(allowed_directions=())
    with pytest.raises(ValueError, match="invalid allowed direction"):
        EntryRule(allowed_directions=(2,))

    # ExitRule
    with pytest.raises(ValueError, match="stop_loss_pct"):
        ExitRule(stop_loss_pct=-0.05)
    with pytest.raises(ValueError, match="stop_loss_pct"):
        ExitRule(stop_loss_pct=1.5)
    with pytest.raises(ValueError, match="take_profit_pct"):
        ExitRule(take_profit_pct=-0.1)
    with pytest.raises(ValueError, match="trailing_stop_pct"):
        ExitRule(trailing_stop_pct=0.0)
    with pytest.raises(ValueError, match="max_holding_ms"):
        ExitRule(max_holding_ms=-100)
    with pytest.raises(ValueError, match="ambiguous_exit_handling"):
        ExitRule(ambiguous_exit_handling="INVALID")

    # PositionSizing
    with pytest.raises(ValueError, match="target_notional"):
        PositionSizing(target_notional=0.0)
    with pytest.raises(ValueError, match="risk_fraction"):
        PositionSizing(risk_fraction=0.0)
    with pytest.raises(ValueError, match="risk_fraction"):
        PositionSizing(risk_fraction=1.2)
    with pytest.raises(ValueError, match="max_leverage"):
        PositionSizing(max_leverage=-1.0)

    # RiskBudget
    with pytest.raises(ValueError, match="max_gross_exposure_usdt"):
        RiskBudget(max_gross_exposure_usdt=0.0)
    with pytest.raises(ValueError, match="max_open_positions"):
        RiskBudget(max_open_positions=-1)
    with pytest.raises(ValueError, match="max_drawdown_stop_pct"):
        RiskBudget(max_drawdown_stop_pct=0.0)
    with pytest.raises(ValueError, match="max_drawdown_stop_pct"):
        RiskBudget(max_drawdown_stop_pct=1.5)

    # MarketStateFilter
    with pytest.raises(ValueError, match="min_volume_usdt_15m"):
        MarketStateFilter(min_volume_usdt_15m=-1.0)
    with pytest.raises(ValueError, match="max_spread_bps"):
        MarketStateFilter(max_spread_bps=-5.0)

    # TradePolicy
    with pytest.raises(ValueError, match="policy_id"):
        TradePolicy(policy_id="", name="Empty ID")
    with pytest.raises(ValueError, match="name"):
        TradePolicy(policy_id="test", name="")


def test_limit_offset_bps_remains_effective() -> None:
    """Regression test ensuring limit offset is applied correctly in limit pricing."""
    entry = EntryRule(order_type=OrderType.LIMIT, limit_offset_bps=500.0)  # 5% passive
    buy_limit = entry.calculate_limit_price(reference_price=100.0, side=1)
    sell_limit = entry.calculate_limit_price(reference_price=100.0, side=-1)
    assert buy_limit == pytest.approx(95.0)
    assert sell_limit == pytest.approx(105.0)


def test_reentry_after_clean_exit_allowed_if_risk_permits() -> None:
    """After a position is closed and pending fills are empty, a new entry is allowed if not in drawdown halt."""
    policy = TradePolicy(
        policy_id="test_reentry",
        name="Re-entry Test",
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_open_positions=1, max_drawdown_stop_pct=0.20),
    )
    engine = EconomicSimulationEngine(policy=policy, fee_model=ZERO_FEES)
    bars = [
        _create_candle(timestamp_ms=1000, open_price=100.0, close_price=100.0),
        _create_candle(timestamp_ms=2000, open_price=110.0, close_price=110.0),
        _create_candle(timestamp_ms=3000, open_price=110.0, close_price=110.0),
        _create_candle(timestamp_ms=4000, open_price=120.0, close_price=120.0),
    ]
    signals = [
        _create_signal(timestamp_ms=1000, direction=1),
        _create_signal(timestamp_ms=2000, direction=-1),  # closes 1st position with profit
        _create_signal(timestamp_ms=3000, direction=1),   # enters 2nd position
        _create_signal(timestamp_ms=4000, direction=-1),  # closes 2nd position with profit
    ]
    summary = engine.simulate(candles=bars, signals=signals)
    assert summary.total_trades == 2
    assert summary.winning_trades == 2
    assert summary.net_pnl_usdt > 0
