from __future__ import annotations

from pathlib import Path

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.execution_model import ExecutionModel
from btc_quant_agent.economic.fee_model import FeeModel, SlippageMode
from btc_quant_agent.economic.funding import FundingModel, FundingSettlement
from btc_quant_agent.economic.policy import (
    EntryRule,
    ExitRule,
    MarketStateFilter,
    OrderType,
    PositionSizing,
    SizingType,
    TradePolicy,
)
from btc_quant_agent.economic.portfolio import Portfolio
from btc_quant_agent.economic.signal import InformationSignal
from btc_quant_agent.economic.simulator import EconomicSimulationEngine
from btc_quant_agent.economic.trade_event import TradeAction
from btc_quant_agent.research_contract.models import (
    P6_PENDING,
    DecisionStatus,
    EvaluationMethod,
    EvidenceReference,
    ExperimentMetadata,
    FeatureDefinition,
    PredictionTarget,
    VersionedIdentity,
)
from btc_quant_agent.research_contract.registry import ResearchContractRegistry


def _create_synthetic_candles(
    count: int = 100,
    start_time_ms: int = 1_700_000_000_000,
    start_price: float = 50_000.0,
    drift_bps: float = 0.0,
    interval_ms: int = 900_000,
) -> list[Candle]:
    candles: list[Candle] = []
    price = start_price
    for i in range(count):
        t_open = start_time_ms + i * interval_ms
        t_close = t_open + interval_ms - 1
        price_change = price * (drift_bps / 10_000.0)
        open_p = price
        close_p = price + price_change
        high_p = max(open_p, close_p) + 20.0
        low_p = min(open_p, close_p) - 20.0
        candles.append(
            Candle(
                symbol="BTCUSDT",
                interval="15m",
                open_time_ms=t_open,
                close_time_ms=t_close,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=100.0,
                quote_volume=100.0 * price,
                taker_buy_base_volume=50.0,
                trades=1000,
                closed=True,
            )
        )
        price = close_p
    return candles


# =====================================================================
# 1. RESEARCH CONTRACT TESTS
# =====================================================================


def test_research_contract_metadata_lifecycle(tmp_path: Path) -> None:
    exp = ExperimentMetadata(
        experiment_id="EXP-V04-001",
        name="H39 order-flow experiment",
        input_contract=VersionedIdentity.from_payload(
            "H39_REQUIRED_INPUT", "V1", {"contract": "label-free"}
        ),
        feature_definition=FeatureDefinition(
            feature_id="F_OFI_5M",
            name="Order Flow Imbalance 5m",
            formula="sum(trades_buy) - sum(trades_sell)",
            input_requirements=["agg_trades"],
        ),
        prediction_target=PredictionTarget(
            target_id="TARGET_60M_RETURN",
            name="Future 60m Continuous Return",
            horizon_ms=3_600_000,
            horizon_description="60 minutes",
        ),
        evaluation_method=EvaluationMethod(
            method_name="FWL_CONDITIONAL_OLS_BARTLETT_HAC",
            statistical_test="OLS_T_STATISTIC",
            fwer_control="HOLM_BONFERRONI",
        ),
        economic_policy=VersionedIdentity.from_payload(
            "POLICY_MOMENTUM_TREND_60M", "V1", {"policy": "momentum"}
        ),
        cost_model=VersionedIdentity.from_payload(
            "BINANCE_VIP0_PERP", "V1", {"fee_bps": 5.0}
        ),
        execution_model=VersionedIdentity.from_payload(
            "CAUSAL_NEXT_OPEN", "V1", {"timing": "next_open"}
        ),
        benchmark=P6_PENDING,
        product_scope=("BTCUSDT-PERP",),
        code_revision="test-revision",
        terminal_policy="EXCLUDE_INCOMPLETE_HORIZONS",
    )
    assert exp.protocol_hash
    reg = ResearchContractRegistry(storage_path=tmp_path / "contracts.json")
    reg.register_experiment(exp)

    # Retrieval
    retrieved = reg.get_experiment(exp.experiment_revision_id)
    assert retrieved.experiment_id == "EXP-V04-001"
    assert retrieved.prediction_target.horizon_ms == 3_600_000
    assert reg.get_status(exp.experiment_revision_id) == DecisionStatus.REGISTERED

    # Status progression
    evidence_path = tmp_path / "statistical-result.json"
    evidence_path.write_text('{"status":"qualified"}\n', encoding="utf-8")
    evidence = EvidenceReference.from_file(
        evidence_path,
        evidence_type="STATISTICAL_RESULT",
        logical_id="EXP-V04-001-statistical-result",
        producing_revision_id=exp.experiment_revision_id,
        producing_code_revision="test-revision",
    )
    updated = reg.update_decision_status(
        exp.experiment_revision_id,
        DecisionStatus.STATISTICALLY_QUALIFIED,
        evidence_references=[evidence],
        reason="deterministic synthetic qualification fixture",
        actor="pytest",
        source="test_v040",
        statistical_result_id=evidence.evidence_id,
    )
    assert updated.new_status == DecisionStatus.STATISTICALLY_QUALIFIED

    # Persistence
    reg2 = ResearchContractRegistry(storage_path=tmp_path / "contracts.json")
    assert len(reg2.list_experiments()) == 1
    assert (
        reg2.get_status(exp.experiment_revision_id)
        == DecisionStatus.STATISTICALLY_QUALIFIED
    )


def test_research_contract_validation_rejects_empty_fields() -> None:
    fd = FeatureDefinition("f1", "feat1", "formula1")
    pt = PredictionTarget("t1", "target1", 3600000, "60m")
    em = EvaluationMethod("m1", "test1")

    with pytest.raises(ValueError, match="experiment_id cannot be empty"):
        ExperimentMetadata(
            experiment_id="",
            name="empty family fixture",
            input_contract=VersionedIdentity.from_payload("c1", "v1", {}),
            feature_definition=fd,
            prediction_target=pt,
            evaluation_method=em,
            economic_policy=VersionedIdentity.from_payload("p1", "v1", {}),
            cost_model=VersionedIdentity.from_payload("c1", "v1", {}),
            execution_model=VersionedIdentity.from_payload("e1", "v1", {}),
            benchmark=P6_PENDING,
            product_scope=("BTCUSDT-PERP",),
            code_revision="test-revision",
            terminal_policy="EXCLUDE_INCOMPLETE_HORIZONS",
        )


# =====================================================================
# 2. SIGNAL VS POLICY DECOUPLING TESTS
# =====================================================================


def test_signal_strictly_decoupled_from_execution() -> None:
    sig = InformationSignal(
        signal_id="SIG_001",
        experiment_id="EXP_001",
        timestamp_ms=1_700_000_000_000,
        direction=1,
        strength=2.35,
        horizon_ms=3_600_000,
    )
    # Verifies signal carries no trade execution baggage
    assert not hasattr(sig, "stop_loss")
    assert not hasattr(sig, "take_profit")
    assert not hasattr(sig, "notional")
    assert not hasattr(sig, "fee_usdt")
    assert sig.is_actionable


def test_trade_policy_sizing_and_market_filters() -> None:
    policy = TradePolicy(
        policy_id="POL_001",
        name="Fixed Notional with Spread Filter",
        entry_rule=EntryRule(min_signal_strength=1.5),
        position_sizing=PositionSizing(
            sizing_type=SizingType.FIXED_NOTIONAL,
            target_notional=25_000.0,
        ),
        market_filter=MarketStateFilter(max_spread_bps=5.0),
    )

    weak_sig = InformationSignal(
        signal_id="SIG_W",
        experiment_id="EXP_1",
        timestamp_ms=1000,
        direction=1,
        strength=1.0,  # below 1.5 threshold
    )
    strong_sig = InformationSignal(
        signal_id="SIG_S",
        experiment_id="EXP_1",
        timestamp_ms=1000,
        direction=1,
        strength=2.0,
    )

    # Weak signal rejected by policy
    assert not policy.should_enter(weak_sig, current_spread_bps=1.0)
    # Strong signal accepted under tight spread
    assert policy.should_enter(strong_sig, current_spread_bps=1.0)
    # Strong signal rejected if spread too wide
    assert not policy.should_enter(strong_sig, current_spread_bps=8.0)

    # Sizing
    qty = policy.calculate_quantity(current_price=50_000.0, portfolio_equity=100_000.0)
    assert qty == 0.5  # 25,000 / 50,000


# =====================================================================
# 3. EXECUTION MODEL TESTS (Signal Delay, Fill Deviation, Missing Fill)
# =====================================================================


def test_execution_model_signal_delay_and_timestamps() -> None:
    exec_model = ExecutionModel(
        decision_latency_ms=400,
        exchange_latency_ms=100,
    )
    candles = _create_synthetic_candles(count=5, start_time_ms=1_000_000, interval_ms=1000)

    sig_time = 1_000_000
    res = exec_model.simulate_order(
        signal_timestamp_ms=sig_time,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.MARKET,
        future_candles=candles,
    )

    assert res.is_filled
    assert res.signal_timestamp_ms == 1_000_000
    assert res.order_timestamp_ms == 1_000_400  # signal + 400ms decision latency
    assert res.fill_timestamp_ms >= 1_000_500  # order + 100ms exchange latency
    assert res.signal_timestamp_ms <= res.order_timestamp_ms <= res.fill_timestamp_ms


def test_execution_model_fill_deviation_slippage() -> None:
    fee_model = FeeModel(
        slippage_mode=SlippageMode.FIXED_BPS,
        fixed_slippage_bps=10.0,  # 10 bps slippage
    )
    exec_model = ExecutionModel(fee_model=fee_model)
    candles = _create_synthetic_candles(count=5, start_price=50_000.0)

    # Buy order fill price must deviate upwards
    buy_res = exec_model.simulate_order(
        signal_timestamp_ms=candles[0].open_time_ms,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.MARKET,
        future_candles=candles,
    )
    assert buy_res.fill_price > 50_000.0
    assert buy_res.slippage_usdt > 0.0

    # Sell order fill price must deviate downwards
    sell_res = exec_model.simulate_order(
        signal_timestamp_ms=candles[0].open_time_ms,
        side=-1,
        desired_quantity=1.0,
        order_type=OrderType.MARKET,
        future_candles=candles,
    )
    assert sell_res.fill_price < 50_000.0
    assert sell_res.slippage_usdt > 0.0


def test_execution_model_missing_fill_on_unreached_limit() -> None:
    exec_model = ExecutionModel(limit_fill_prob_on_touch=0.0)
    # Price is 50,000 +/- 20; low never reaches 49,000
    candles = _create_synthetic_candles(count=5, start_price=50_000.0)

    res = exec_model.simulate_order(
        signal_timestamp_ms=candles[0].open_time_ms,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=candles,
        limit_price=49_000.0,  # deeply unreached limit price
        time_in_force_ms=60_000,
    )
    assert not res.is_filled
    assert res.rejection_reason == "LIMIT_EXPIRED_UNFILLED"
    assert res.fill_price == 0.0


# =====================================================================
# 4. COST MODEL TESTS (Zero Fee, Normal Fee, High Slippage)
# =====================================================================


def test_cost_model_zero_fee_equals_gross() -> None:
    zero_fee = FeeModel(maker_fee_rate=0.0, taker_fee_rate=0.0, slippage_mode=SlippageMode.ZERO)
    assert zero_fee.calculate_fee(10_000.0) == 0.0
    p = zero_fee.effective_fill_price(50_000.0, quantity=1.0, side=1)
    assert p == 50_000.0


def test_cost_model_normal_vs_high_slippage() -> None:
    normal_fee = FeeModel(taker_fee_rate=0.0005, fixed_slippage_bps=2.0)
    high_slip = FeeModel(taker_fee_rate=0.0005, fixed_slippage_bps=50.0)

    p_norm = normal_fee.effective_fill_price(50_000.0, quantity=1.0, side=1)
    p_high = high_slip.effective_fill_price(50_000.0, quantity=1.0, side=1)

    assert p_high > p_norm
    assert (p_high - 50_000.0) == pytest.approx(250.0)  # 50 bps on 50,000 = $250 slippage


# =====================================================================
# 5. FUNDING MODEL TESTS (Positive, Negative, Prorated Window)
# =====================================================================


def test_funding_model_positive_and_negative_rates() -> None:
    funding = FundingModel()

    # Positive funding rate: Long pays short
    long_cf = funding.calculate_cashflow(position_quantity=2.0, mark_price=50_000.0, funding_rate=0.0001)
    assert long_cf == -10.0  # -2 * 50000 * 0.0001 = -$10 paid

    # Positive funding rate: Short receives from long
    short_cf = funding.calculate_cashflow(position_quantity=-2.0, mark_price=50_000.0, funding_rate=0.0001)
    assert short_cf == +10.0

    # Negative funding rate: Short pays long
    short_cf_neg = funding.calculate_cashflow(position_quantity=-2.0, mark_price=50_000.0, funding_rate=-0.0002)
    assert short_cf_neg == -20.0


def test_funding_window_accumulation() -> None:
    funding = FundingModel()
    events = [
        FundingSettlement(timestamp_ms=1000, funding_rate=0.0001, mark_price=50_000.0),
        FundingSettlement(timestamp_ms=2000, funding_rate=0.0002, mark_price=50_000.0),
        FundingSettlement(timestamp_ms=3000, funding_rate=0.0001, mark_price=50_000.0),
    ]

    # Holding between 1500 and 2500 only catches event at 2000
    cf, settled = funding.accumulate_funding_during_window(
        position_quantity=1.0,
        entry_ms=1500,
        exit_ms=2500,
        funding_events=events,
    )
    assert len(settled) == 1
    assert settled[0].timestamp_ms == 2000
    assert cf == -10.0  # -1 * 50000 * 0.0002


# =====================================================================
# 6. PORTFOLIO SIMULATION & TRADE EVENT TESTS (Multiple positions, Drawdown)
# =====================================================================


def test_portfolio_trade_event_atomic_accounting() -> None:
    port = Portfolio(initial_cash=100_000.0)

    # 1. Open Long 1.0 BTC at 50,000 with $25 fee
    ev1 = port.apply_trade(
        timestamp_ms=1000,
        action=TradeAction.OPEN_LONG,
        asset="BTCUSDT",
        price=50_000.0,
        quantity=1.0,
        fee_usdt=25.0,
    )
    assert ev1.action == TradeAction.OPEN_LONG
    assert ev1.position_after == 1.0
    assert ev1.cash_after == 99_975.0
    assert port.total_equity({"BTCUSDT": 50_000.0}) == 99_975.0

    # 2. Close Long 1.0 BTC at 52,000 with $26 fee (Realized PnL: +$2000)
    ev2 = port.apply_trade(
        timestamp_ms=2000,
        action=TradeAction.CLOSE_LONG,
        asset="BTCUSDT",
        price=52_000.0,
        quantity=1.0,
        fee_usdt=26.0,
    )
    assert ev2.action == TradeAction.CLOSE_LONG
    assert ev2.position_after == 0.0
    assert ev2.realized_pnl_usdt == 2000.0
    assert ev2.cash_after == 99_975.0 + 2000.0 - 26.0
    assert port.total_equity({"BTCUSDT": 52_000.0}) == 101_949.0


def test_simulation_drawdown_and_exit_rules() -> None:
    candles = _create_synthetic_candles(count=20, start_price=50_000.0, drift_bps=-50.0)
    # Price steadily drifts downwards: 50,000 -> 45,000
    policy = TradePolicy(
        policy_id="POL_SL",
        name="Long with Stop Loss",
        exit_rule=ExitRule(stop_loss_pct=0.01),  # 1% stop loss
    )
    sig = InformationSignal(
        signal_id="SIG_001",
        experiment_id="EXP_001",
        timestamp_ms=candles[0].open_time_ms,
        direction=1,
        strength=2.0,
    )
    sim = EconomicSimulationEngine(policy=policy, initial_cash=100_000.0)
    summary = sim.simulate(candles=candles, signals=[sig])

    assert summary.total_trades == 1
    assert summary.losing_trades == 1
    assert summary.net_pnl_usdt < 0.0
    assert summary.max_drawdown_pct > 0.0
    # Stop loss strictly limited loss to approximately 1% plus fees/slippage
    assert summary.max_drawdown_pct < 0.03


# =====================================================================
# 8. LEGACY COMPATIBILITY TEST
# =====================================================================


def test_legacy_modules_remain_importable_and_intact() -> None:
    from btc_quant_agent.backtest import resolve_signal
    from btc_quant_agent.h39_input import check_h39_required_input
    from btc_quant_agent.h39_statistics import conditional_incremental_ols_hac
    from btc_quant_agent.microstructure_research import H39OneShotUnblindGatekeeper

    assert callable(resolve_signal)
    assert callable(check_h39_required_input)
    assert callable(conditional_incremental_ols_hac)
    assert H39OneShotUnblindGatekeeper is not None


def test_simulation_overlapping_signals_and_reversal_exit() -> None:
    """Tests that overlapping opposite signals trigger clean early reversal exit."""
    candles = _create_synthetic_candles(count=20, start_price=50_000.0)
    policy = TradePolicy(
        policy_id="POL_REV",
        name="Signal Reversal Exit Policy",
        exit_rule=ExitRule(decay_exit_on_signal_reversal=True, max_holding_ms=7_200_000),
    )
    # Long signal at bar 0, followed by Short signal at bar 2
    sig_long = InformationSignal(
        signal_id="SIG_L",
        experiment_id="EXP_REV",
        timestamp_ms=candles[0].open_time_ms,
        direction=1,
    )
    sig_short = InformationSignal(
        signal_id="SIG_S",
        experiment_id="EXP_REV",
        timestamp_ms=candles[2].open_time_ms,
        direction=-1,
    )

    sim = EconomicSimulationEngine(policy=policy, initial_cash=100_000.0)
    summary = sim.simulate(candles=candles, signals=[sig_long, sig_short])

    # The short signal at bar 2 should have closed the initial long trade
    assert summary.total_trades >= 1
    actions = [ev.action for ev in summary.trade_events]
    assert TradeAction.OPEN_LONG in actions
    assert TradeAction.CLOSE_LONG in actions


def test_simulation_multiple_sequential_positions() -> None:
    """Tests multiple consecutive trades updating cash and position state accurately."""
    candles = _create_synthetic_candles(count=30, start_price=50_000.0)
    policy = TradePolicy(
        policy_id="POL_SEQ",
        name="Sequential Trades Policy",
        exit_rule=ExitRule(max_holding_ms=1_800_000),  # 2 bars holding
    )
    signals = [
        InformationSignal("SIG_1", "EXP_SEQ", candles[0].open_time_ms, direction=1),
        InformationSignal("SIG_2", "EXP_SEQ", candles[5].open_time_ms, direction=1),
        InformationSignal("SIG_3", "EXP_SEQ", candles[10].open_time_ms, direction=1),
    ]

    sim = EconomicSimulationEngine(policy=policy, initial_cash=100_000.0)
    summary = sim.simulate(candles=candles, signals=signals)

    assert summary.total_trades == 3
    assert len(summary.trade_events) == 6  # 3 opens + 3 closes
