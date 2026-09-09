from __future__ import annotations

import math

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.execution_model import ExecutionModel
from btc_quant_agent.economic.fee_model import FeeModel, SlippageMode
from btc_quant_agent.economic.funding import FundingSettlement
from btc_quant_agent.economic.policy import (
    EntryRule,
    ExitRule,
    OrderType,
    PositionSizing,
    RiskBudget,
    TradePolicy,
)
from btc_quant_agent.economic.signal import InformationSignal
from btc_quant_agent.economic.simulator import (
    AmbiguousExitRejectionError,
    EconomicSimulationEngine,
    SimulationSummary,
)
from btc_quant_agent.economic.trade_event import TradeAction


def _bar(
    timestamp_ms: int,
    *,
    open_price: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    close: float = 100.0,
    volume: float = 1_000.0,
) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        interval="1s",
        open_time_ms=timestamp_ms,
        close_time_ms=timestamp_ms + 999,
        open=open_price,
        high=max(open_price, close, high if high is not None else open_price),
        low=min(open_price, close, low if low is not None else open_price),
        close=close,
        volume=volume,
    )


def _signal(
    *,
    direction: int = 1,
    timestamp_ms: int = 1_000,
    metadata: dict[str, float] | None = None,
) -> InformationSignal:
    return InformationSignal(
        signal_id=f"SIG_{timestamp_ms}_{direction}",
        experiment_id="C2",
        timestamp_ms=timestamp_ms,
        asset="BTCUSDT",
        direction=direction,
        strength=1.0,
        metadata=metadata or {},
    )


ZERO_COST = FeeModel(
    maker_fee_rate=0.0,
    taker_fee_rate=0.0,
    slippage_mode=SlippageMode.ZERO,
)
DEFAULT_ENTRY_RULE = EntryRule()


def _simulate(
    *,
    bars: list[Candle],
    exit_rule: ExitRule,
    direction: int = 1,
    fee_model: FeeModel = ZERO_COST,
    entry_rule: EntryRule = DEFAULT_ENTRY_RULE,
    funding: list[FundingSettlement] | None = None,
    signal_metadata: dict[str, float] | None = None,
) -> SimulationSummary:
    policy = TradePolicy(
        policy_id="C2_POLICY",
        name="C2 policy",
        entry_rule=entry_rule,
        exit_rule=exit_rule,
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_gross_exposure_usdt=1_000.0),
    )
    execution = ExecutionModel(
        fee_model=fee_model,
        decision_latency_ms=0,
        exchange_latency_ms=0,
        limit_fill_prob_on_touch=1.0,
    )
    return EconomicSimulationEngine(
        policy=policy,
        execution_model=execution,
        fee_model=fee_model,
        initial_cash=10_000.0,
    ).simulate(
        candles=bars,
        signals=[_signal(direction=direction, metadata=signal_metadata)],
        funding_events=funding or [],
    )


@pytest.mark.parametrize(
    ("direction", "trigger_bar", "expected_price", "close_action"),
    [
        (1, _bar(2_000, high=101.0, low=90.0, close=100.0), 95.0, TradeAction.CLOSE_LONG),
        (
            -1,
            _bar(2_000, high=110.0, low=99.0, close=100.0),
            105.0,
            TradeAction.CLOSE_SHORT,
        ),
    ],
)
def test_stop_recovery_bar_uses_standing_level_for_both_sides(
    direction: int,
    trigger_bar: Candle,
    expected_price: float,
    close_action: TradeAction,
) -> None:
    result = _simulate(
        bars=[_bar(1_000), trigger_bar],
        exit_rule=ExitRule(stop_loss_pct=0.05),
        direction=direction,
    )

    exit_event = result.trade_events[-1]
    assert exit_event.action == close_action
    assert exit_event.price == expected_price
    assert exit_event.price != trigger_bar.close or expected_price == trigger_bar.close
    assert exit_event.metadata["ref_price"] == expected_price
    assert exit_event.metadata["trigger_time_semantics"] == "INTRABAR_UNKNOWN"
    assert exit_event.observation_timestamp_ms == result.trade_events[0].timestamp_ms
    assert exit_event.timestamp_ms == trigger_bar.close_time_ms


@pytest.mark.parametrize(
    ("direction", "trigger_bar", "expected_price"),
    [
        (1, _bar(2_000, high=110.0, low=99.0, close=100.0), 105.0),
        (-1, _bar(2_000, high=101.0, low=90.0, close=100.0), 95.0),
    ],
)
def test_take_profit_retrace_uses_standing_target(
    direction: int, trigger_bar: Candle, expected_price: float
) -> None:
    result = _simulate(
        bars=[_bar(1_000), trigger_bar],
        exit_rule=ExitRule(take_profit_pct=0.05),
        direction=direction,
    )
    assert result.trade_events[-1].price == expected_price
    assert result.trade_events[-1].metadata["ref_price"] == expected_price


@pytest.mark.parametrize(
    ("direction", "setup_bar", "trigger_bar", "expected_price"),
    [
        (
            1,
            _bar(1_000, high=120.0, low=100.0, close=120.0),
            _bar(2_000, open_price=120.0, high=121.0, low=110.0, close=120.0),
            114.0,
        ),
        (
            -1,
            _bar(1_000, high=100.0, low=80.0, close=80.0),
            _bar(2_000, open_price=80.0, high=90.0, low=79.0, close=80.0),
            84.0,
        ),
    ],
)
def test_trailing_stop_retrace_uses_prior_causal_extreme(
    direction: int,
    setup_bar: Candle,
    trigger_bar: Candle,
    expected_price: float,
) -> None:
    result = _simulate(
        bars=[setup_bar, trigger_bar],
        exit_rule=ExitRule(trailing_stop_pct=0.05),
        direction=direction,
    )
    exit_event = result.trade_events[-1]
    assert exit_event.price == expected_price
    assert exit_event.metadata["ref_price"] == expected_price
    assert exit_event.metadata["standing_order_armed_ms"] == setup_bar.close_time_ms


@pytest.mark.parametrize(
    ("direction", "gap_open", "expected_price"),
    [(1, 90.0, 89.91), (-1, 110.0, 110.11)],
)
def test_gap_stop_uses_actual_open_plus_adverse_cost(
    direction: int, gap_open: float, expected_price: float
) -> None:
    fees = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.FIXED_BPS,
        fixed_slippage_bps=10.0,
    )
    result = _simulate(
        bars=[_bar(1_000), _bar(2_000, open_price=gap_open, close=gap_open)],
        exit_rule=ExitRule(stop_loss_pct=0.05),
        direction=direction,
        fee_model=fees,
    )
    exit_event = result.trade_events[-1]
    assert exit_event.price == pytest.approx(expected_price)
    assert exit_event.metadata["ref_price"] == gap_open
    assert exit_event.metadata["trigger_time_semantics"] == "BAR_OPEN_KNOWN"
    assert exit_event.timestamp_ms == 2_000


@pytest.mark.parametrize("direction", [1, -1])
def test_sl_tp_collision_is_adverse_or_rejected(direction: int) -> None:
    collision_bar = _bar(2_000, high=110.0, low=90.0, close=100.0)
    conservative = _simulate(
        bars=[_bar(1_000), collision_bar],
        exit_rule=ExitRule(
            stop_loss_pct=0.05,
            take_profit_pct=0.05,
            ambiguous_exit_handling="CONSERVATIVE_STOP_FIRST",
        ),
        direction=direction,
    )
    expected_stop = 95.0 if direction == 1 else 105.0
    assert conservative.trade_events[-1].price == expected_stop
    assert "COLLISION" in conservative.trade_events[-1].trade_id

    with pytest.raises(AmbiguousExitRejectionError, match="Ambiguous exit collision"):
        _simulate(
            bars=[_bar(1_000), collision_bar],
            exit_rule=ExitRule(
                stop_loss_pct=0.05,
                take_profit_pct=0.05,
                ambiguous_exit_handling="REJECT_AMBIGUOUS",
            ),
            direction=direction,
        )


def test_funding_inside_unknown_trigger_bar_fails_closed_before_cashflow() -> None:
    funding = [FundingSettlement(timestamp_ms=2_500, funding_rate=0.01, mark_price=100.0)]
    with pytest.raises(AmbiguousExitRejectionError, match="trigger/funding ordering"):
        _simulate(
            bars=[_bar(1_000), _bar(2_000, high=101.0, low=90.0, close=100.0)],
            exit_rule=ExitRule(stop_loss_pct=0.05),
            funding=funding,
        )


@pytest.mark.parametrize("side", [1, -1])
def test_spread_impact_actual_fill_is_clamped_to_exact_declared_cap(side: int) -> None:
    fees = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        impact_coefficient=100.0,
        max_slippage_bps=25.0,
    )
    raw_bps = fees.calculate_slippage_bps(
        quantity=1.0,
        price=100.0,
        current_spread_bps=1_000.0,
        bar_volume_base=1.0,
    )
    fill = fees.effective_fill_price(
        reference_price=100.0,
        quantity=1.0,
        side=side,
        current_spread_bps=1_000.0,
        bar_volume_base=1.0,
    )
    assert raw_bps == 25.0
    assert fill == pytest.approx(100.0 * (1.0 + side * 0.0025))


@pytest.mark.parametrize("direction", [1, -1])
def test_every_admitted_bounded_market_fill_stays_within_reservation(direction: int) -> None:
    fees = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        impact_coefficient=100.0,
        max_slippage_bps=25.0,
    )
    result = _simulate(
        bars=[_bar(1_000, volume=1.0)],
        exit_rule=ExitRule(),
        direction=direction,
        fee_model=fees,
        signal_metadata={"spread_bps": 1_000.0},
    )
    entry = result.trade_events[0]
    reservation = entry.metadata["reservation_notional"]
    assert entry.quantity * entry.price <= reservation + 1e-12
    assert reservation == pytest.approx(100.25)


@pytest.mark.parametrize("direction", [1, -1])
def test_price_movement_reduces_base_fill_instead_of_breaching_reservation(
    direction: int,
) -> None:
    policy = TradePolicy(
        policy_id="C2_DELAYED_RESERVATION",
        name="C2 delayed reservation",
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_gross_exposure_usdt=100.0),
    )
    engine = EconomicSimulationEngine(
        policy=policy,
        execution_model=ExecutionModel(
            fee_model=ZERO_COST,
            decision_latency_ms=200,
            exchange_latency_ms=100,
        ),
        fee_model=ZERO_COST,
        initial_cash=10_000.0,
    )
    result = engine.simulate(
        candles=[_bar(1_000, open_price=100.0, high=200.0, close=200.0)],
        signals=[_signal(direction=direction)],
    )
    entry = result.trade_events[0]
    reservation = entry.metadata["reservation_notional"]
    assert entry.price == 200.0
    assert entry.quantity == pytest.approx(0.5)
    assert entry.price * entry.quantity <= reservation + 1e-12
    assert entry.metadata["requested_quantity"] == 1.0
    assert entry.metadata["notional_cap_applied"] is True


@pytest.mark.parametrize(
    "exit_bar",
    [
        _bar(2_000, high=101.0, low=90.0, close=100.0),
        _bar(2_000, open_price=90.0, close=90.0),
    ],
    ids=["intrabar-stop", "gap-stop"],
)
def test_spread_sensitive_conditional_exit_without_evidence_fails_closed(
    exit_bar: Candle,
) -> None:
    fees = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        max_slippage_bps=None,
    )
    entry_rule = EntryRule(order_type=OrderType.LIMIT)
    with pytest.raises(ValueError, match="standing conditionals require"):
        _simulate(
            bars=[
                _bar(1_000, low=99.0),
                exit_bar,
            ],
            exit_rule=ExitRule(stop_loss_pct=0.05),
            fee_model=fees,
            entry_rule=entry_rule,
        )


def test_spread_sensitive_reversal_without_evidence_fails_closed() -> None:
    fees = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        max_slippage_bps=None,
    )
    policy = TradePolicy(
        policy_id="C2_REVERSAL",
        name="C2 reversal",
        entry_rule=EntryRule(order_type=OrderType.LIMIT),
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_gross_exposure_usdt=1_000.0),
    )
    engine = EconomicSimulationEngine(
        policy=policy,
        execution_model=ExecutionModel(
            fee_model=fees,
            decision_latency_ms=0,
            exchange_latency_ms=0,
            limit_fill_prob_on_touch=1.0,
        ),
        fee_model=fees,
        initial_cash=10_000.0,
    )
    with pytest.raises(ValueError, match="requires causal current_spread_bps"):
        engine.simulate(
            candles=[_bar(1_000, low=99.0), _bar(2_000)],
            signals=[_signal(), _signal(direction=-1, timestamp_ms=2_000)],
        )


def test_reversal_uses_causal_signal_spread_when_available() -> None:
    fees = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        impact_coefficient=0.0,
        max_slippage_bps=None,
    )
    policy = TradePolicy(
        policy_id="C2_REVERSAL_SPREAD",
        name="C2 reversal spread",
        entry_rule=EntryRule(order_type=OrderType.LIMIT),
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_gross_exposure_usdt=1_000.0),
    )
    engine = EconomicSimulationEngine(
        policy=policy,
        execution_model=ExecutionModel(
            fee_model=fees,
            decision_latency_ms=0,
            exchange_latency_ms=0,
            limit_fill_prob_on_touch=1.0,
        ),
        fee_model=fees,
        initial_cash=10_000.0,
    )
    result = engine.simulate(
        candles=[_bar(1_000, low=99.0), _bar(2_000)],
        signals=[
            _signal(),
            _signal(direction=-1, timestamp_ms=2_000, metadata={"spread_bps": 20.0}),
        ],
    )
    exit_event = result.trade_events[-1]
    assert exit_event.action == TradeAction.CLOSE_LONG
    assert exit_event.price == pytest.approx(99.9)
    assert exit_event.metadata["spread_evidence"] == "CAUSAL_SPREAD"


def test_declared_cap_is_used_as_explicit_missing_spread_adverse_scenario() -> None:
    fees = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        max_slippage_bps=50.0,
    )
    result = _simulate(
        bars=[
            _bar(1_000, low=99.0),
            _bar(2_000, high=101.0, low=90.0, close=100.0),
        ],
        exit_rule=ExitRule(stop_loss_pct=0.05),
        fee_model=fees,
        entry_rule=EntryRule(order_type=OrderType.LIMIT),
    )
    exit_event = result.trade_events[-1]
    assert exit_event.price == pytest.approx(95.0 * (1.0 - 0.005))
    assert exit_event.metadata["spread_evidence"] == "DECLARED_MAX_SLIPPAGE_SCENARIO"


@pytest.mark.parametrize(
    "fees",
    [
        ZERO_COST,
        FeeModel(
            maker_fee_rate=0.0,
            taker_fee_rate=0.0,
            slippage_mode=SlippageMode.FIXED_BPS,
            fixed_slippage_bps=10.0,
        ),
    ],
)
def test_zero_and_fixed_modes_do_not_require_spread_metadata(fees: FeeModel) -> None:
    result = _simulate(
        bars=[_bar(1_000), _bar(2_000, high=101.0, low=90.0, close=100.0)],
        exit_rule=ExitRule(stop_loss_pct=0.05),
        fee_model=fees,
    )
    assert len(result.trade_events) == 2
    assert result.trade_events[-1].metadata["spread_evidence"] == "NOT_USED"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maker_fee_rate", -0.1),
        ("taker_fee_rate", math.nan),
        ("fixed_slippage_bps", -1.0),
        ("impact_coefficient", math.inf),
        ("max_slippage_bps", -1.0),
        ("max_slippage_bps", math.nan),
    ],
)
def test_fee_parameters_reject_negative_or_nonfinite_values(field: str, value: float) -> None:
    with pytest.raises(ValueError, match=field):
        FeeModel(**{field: value})
