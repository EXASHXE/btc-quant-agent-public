from __future__ import annotations

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
    TradePolicy,
)
from btc_quant_agent.economic.signal import InformationSignal
from btc_quant_agent.economic.simulator import (
    AmbiguousExitRejectionError,
    EconomicSimulationEngine,
)
from btc_quant_agent.economic.trade_event import TradeAction


def _bar(
    open_time_ms: int = 1000,
    o: float = 100.0,
    h: float | None = None,
    l: float | None = None,
    c: float = 100.0,
    volume: float = 1000.0,
    quote_volume: float = 0.0,
    duration: int = 1000,
    symbol: str = "BTCUSDT",
) -> Candle:
    high = max(h if h is not None else max(o, c), o, c)
    low = min(l if l is not None else min(o, c), o, c)
    return Candle(
        symbol=symbol,
        interval="1s",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + duration - 1,
        open=o,
        high=high,
        low=low,
        close=c,
        volume=volume,
        quote_volume=quote_volume,
        closed=True,
    )


def _sig(
    timestamp_ms: int = 1000,
    direction: int = 1,
    strength: float = 1.0,
    signal_id: str = "SIG_1",
    asset: str = "BTCUSDT",
    metadata: dict | None = None,
) -> InformationSignal:
    return InformationSignal(
        signal_id=signal_id,
        experiment_id="EXP_TEST",
        timestamp_ms=timestamp_ms,
        asset=asset,
        direction=direction,
        strength=strength,
        metadata=metadata or {},
    )


ZERO_FEES = FeeModel(maker_fee_rate=0.0, taker_fee_rate=0.0, slippage_mode=SlippageMode.ZERO)
ZERO_LATENCY = ExecutionModel(fee_model=ZERO_FEES, decision_latency_ms=0, exchange_latency_ms=0)


# =====================================================================
# AR1 — MISSING SPREAD MUST NOT SILENTLY BECOME ZERO
# =====================================================================


def test_ar1_missing_spread_when_enforced_fails_closed() -> None:
    """If max_spread_bps is binding, missing spread evidence in signal rejects entry."""
    policy = TradePolicy(
        policy_id="AR1_MISSING",
        name="Missing Spread Fail Closed",
        market_filter=MarketStateFilter(max_spread_bps=5.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    bar = _bar(1000)
    # Signal has no spread_bps in metadata
    sig_no_spread = _sig(1000, metadata={})
    summary = engine.simulate(candles=[bar], signals=[sig_no_spread])
    assert len(summary.trade_events) == 0
    assert summary.total_trades == 0


def test_ar1_nonfinite_and_negative_spread_fails_closed() -> None:
    """Non-finite (NaN, inf) and negative spread values are rejected fail closed."""
    policy = TradePolicy(
        policy_id="AR1_NONFINITE",
        name="Nonfinite Spread Fail Closed",
        market_filter=MarketStateFilter(max_spread_bps=5.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    bar = _bar(1000)

    for bad_spread in (float("nan"), float("inf"), float("-inf"), -1.0, -0.01):
        sig = _sig(1000, metadata={"spread_bps": bad_spread})
        summary = engine.simulate(candles=[bar], signals=[sig])
        assert len(summary.trade_events) == 0


def test_ar1_spread_over_and_under_cap() -> None:
    """Valid spread under cap is accepted; spread over cap is rejected."""
    policy = TradePolicy(
        policy_id="AR1_CAP",
        name="Spread Cap Check",
        market_filter=MarketStateFilter(max_spread_bps=5.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)

    # Over cap (6 bps > 5 bps) -> rejected
    bar1 = _bar(1000)
    sig_over = _sig(1000, metadata={"spread_bps": 6.0})
    assert len(engine.simulate(candles=[bar1], signals=[sig_over]).trade_events) == 0

    # Under cap (3 bps <= 5 bps) -> accepted
    bar2 = _bar(2000)
    sig_under = _sig(2000, metadata={"spread_bps": 3.0})
    assert len(engine.simulate(candles=[bar2], signals=[sig_under]).trade_events) == 1


def test_ar1_spread_filter_disabled_allows_missing_spread() -> None:
    """When max_spread_bps is None (explicitly disabled), missing spread does not block entry."""
    policy = TradePolicy(
        policy_id="AR1_DISABLED",
        name="Spread Disabled",
        market_filter=MarketStateFilter(max_spread_bps=None),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    bar = _bar(1000)
    sig = _sig(1000, metadata={})
    summary = engine.simulate(candles=[bar], signals=[sig])
    assert len(summary.trade_events) == 1


# =====================================================================
# AR2 — DO NOT USE CURRENT-BAR COMPLETED VOLUME AT BAR OPEN
# =====================================================================


def test_ar2_changing_current_bar_future_volume_does_not_change_entry_at_open() -> None:
    """Changing only the future remainder of current candle's volume does not alter entry at open."""
    policy = TradePolicy(
        policy_id="AR2_CAUSAL_VOL",
        name="Causal Volume Policy",
        market_filter=MarketStateFilter(min_volume_usdt_15m=10_000.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)

    # Prior bar had low volume (5,000 < 10,000)
    prior_bar = _bar(open_time_ms=1000, quote_volume=5000.0)

    # Path A: Current bar at t=2000 has modest volume (2,000)
    bar2_a = _bar(open_time_ms=2000, quote_volume=2000.0)
    sig_a = _sig(2000)
    summary_a = engine.simulate(candles=[prior_bar, bar2_a], signals=[sig_a])

    # Path B: Current bar at t=2000 has huge future completed volume (1,000,000)
    bar2_b = _bar(open_time_ms=2000, quote_volume=1_000_000.0)
    sig_b = _sig(2000)
    summary_b = engine.simulate(candles=[prior_bar, bar2_b], signals=[sig_b])

    # Both must be rejected because at t=2000, only prior bar volume (5,000 < 10,000) was causally known!
    assert len(summary_a.trade_events) == 0
    assert len(summary_b.trade_events) == 0


def test_ar2_causal_volume_from_prior_candle_or_metadata_admitted() -> None:
    """Causal volume can be supplied via prior closed candle or explicit signal metadata."""
    policy = TradePolicy(
        policy_id="AR2_SOURCES",
        name="Causal Volume Sources",
        market_filter=MarketStateFilter(min_volume_usdt_15m=10_000.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)

    # Source 1: Prior closed candle had sufficient quote volume (15,000 >= 10,000)
    prior_bar = _bar(open_time_ms=1000, quote_volume=15_000.0)
    curr_bar = _bar(open_time_ms=2000, quote_volume=0.0)
    summary_prior = engine.simulate(candles=[prior_bar, curr_bar], signals=[_sig(2000)])
    assert len(summary_prior.trade_events) == 1

    # Source 2: Explicit causal volume in signal metadata (20,000 >= 10,000) on candle 0
    bar0 = _bar(open_time_ms=1000, quote_volume=0.0)
    sig_meta = _sig(1000, metadata={"volume_usdt": 20_000.0})
    summary_meta = engine.simulate(candles=[bar0], signals=[sig_meta])
    assert len(summary_meta.trade_events) == 1


# =====================================================================
# AR3 — RISK ADMISSION MUST NOT INSPECT FUTURE FILL RESULTS
# =====================================================================


def test_ar3_future_price_path_divergence_does_not_affect_order_time_admission() -> None:
    """Two future price paths diverging after order submission have identical order-time admission."""
    policy = TradePolicy(
        policy_id="AR3_DIVERGE",
        name="Path Divergence Test",
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_gross_exposure_usdt=150.0),
    )
    exec_model = ExecutionModel(fee_model=ZERO_FEES, decision_latency_ms=200, exchange_latency_ms=100)
    engine = EconomicSimulationEngine(policy=policy, execution_model=exec_model, fee_model=ZERO_FEES)

    # Order time: t=1000 open at 100. Fill happens at close t=1999.
    # Path A: close surges to 140
    path_a = [_bar(open_time_ms=1000, o=100.0, c=140.0), _bar(open_time_ms=2000)]
    # Path B: close drops to 70
    path_b = [_bar(open_time_ms=1000, o=100.0, c=70.0), _bar(open_time_ms=2000)]

    res_a = engine.simulate(candles=path_a, signals=[_sig(1000)])
    res_b = engine.simulate(candles=path_b, signals=[_sig(1000)])

    # Both orders must be accepted at order time because order-time inputs (open=100, notional=100) are identical!
    assert len(res_a.trade_events) >= 1
    assert len(res_b.trade_events) >= 1
    assert res_a.trade_events[0].order_timestamp_ms == res_b.trade_events[0].order_timestamp_ms


def test_ar3_pending_reservation_uses_ex_ante_bounds_not_realized_fill() -> None:
    """Pending reservations store ex-ante bounds, not realized future fill price."""
    policy = TradePolicy(
        policy_id="AR3_EX_ANTE",
        name="Ex-Ante Reservation Policy",
        entry_rule=EntryRule(order_type=OrderType.MARKET),
        position_sizing=PositionSizing(target_notional=100.0),  # qty = 1.0 @ 100
        risk_budget=RiskBudget(max_gross_exposure_usdt=205.0),
    )
    # Fixed slippage 500 bps (5%): ex-ante bound = 100 * 1.05 = 105.0 -> reserved = 105.0
    fee_model = FeeModel(
        maker_fee_rate=0.0,
        taker_fee_rate=0.0,
        slippage_mode=SlippageMode.FIXED_BPS,
        fixed_slippage_bps=500.0,
    )
    exec_model = ExecutionModel(fee_model=fee_model, decision_latency_ms=200, exchange_latency_ms=100)
    engine = EconomicSimulationEngine(policy=policy, execution_model=exec_model, fee_model=fee_model)

    # Bar 1: t=1000..1999. Sig 1 at 1000 reserves 105 gross.
    # Sig 2 at 1500 candidate gross = 105.
    # active (0) + pending (105) + order (105) = 210 > 205 -> Sig 2 must be rejected ex-ante!
    bars = [
        _bar(open_time_ms=1000, o=100.0, c=100.0),
        _bar(open_time_ms=2000, o=100.0, c=100.0),
    ]
    signals = [_sig(1000), _sig(1500)]
    summary = engine.simulate(candles=bars, signals=signals)

    # Exactly 1 trade admitted
    assert len([e for e in summary.trade_events if e.action == TradeAction.OPEN_LONG]) == 1


# =====================================================================
# AR4 — NEVER ERASE AN ALREADY-ACCEPTED FILL
# =====================================================================


def test_ar4_order_accepted_before_later_drawdown_halt_still_books() -> None:
    """Order accepted before a later drawdown halt must still book when the fill matures."""
    policy = TradePolicy(
        policy_id="AR4_HALT_BOOK",
        name="Halt Does Not Delete Fill",
        entry_rule=EntryRule(order_type=OrderType.MARKET),
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_drawdown_stop_pct=0.001),  # tight 0.1% halt
    )
    # 650 ms latency: order at 1000 fills at 1650 (bar close 1999)
    exec_model = ExecutionModel(fee_model=ZERO_FEES, decision_latency_ms=500, exchange_latency_ms=150)
    engine = EconomicSimulationEngine(policy=policy, execution_model=exec_model, fee_model=ZERO_FEES)

    # Bar 1: Signal at 1000 admitted under 0 drawdown.
    # Pending fill scheduled at 1999.
    # Bar 2: Second signal at 2000 arrives while drawdown halt may have triggered.
    bars = [
        _bar(open_time_ms=1000, o=100.0, c=90.0),  # price drops, inducing unrealized loss
        _bar(open_time_ms=2000, o=90.0, c=90.0),
    ]
    signals = [_sig(1000)]
    summary = engine.simulate(candles=bars, signals=signals)

    # The scheduled pending fill from signal 1 MUST book at 1999
    assert len(summary.trade_events) == 1
    assert summary.trade_events[0].action == TradeAction.OPEN_LONG
    assert summary.trade_events[0].timestamp_ms == 1999


def test_ar4_unsupported_unbounded_market_fill_rejected_before_submission() -> None:
    """Market orders under unbounded slippage models fail closed ex-ante before submission."""
    # SPREAD_AND_IMPACT without max_slippage_bps has no finite ex-ante bound
    unbounded_fees = FeeModel(
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        max_slippage_bps=None,
    )
    policy = TradePolicy(
        policy_id="AR4_UNBOUNDED",
        name="Unbounded Fail Closed",
        entry_rule=EntryRule(order_type=OrderType.MARKET),
        risk_budget=RiskBudget(max_gross_exposure_usdt=10_000.0),
    )
    engine = EconomicSimulationEngine(policy=policy, fee_model=unbounded_fees)
    summary = engine.simulate(candles=[_bar(1000)], signals=[_sig(1000)])

    # Fails closed before submission -> 0 trades
    assert len(summary.trade_events) == 0


def test_ar4_bounded_market_fill_with_max_slippage_cap_admitted() -> None:
    """Market orders under SPREAD_AND_IMPACT with explicit max_slippage_bps cap are admitted."""
    bounded_fees = FeeModel(
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT,
        max_slippage_bps=50.0,  # explicit finite 50 bps cap
    )
    policy = TradePolicy(
        policy_id="AR4_BOUNDED_CAP",
        name="Bounded Cap Admitted",
        entry_rule=EntryRule(order_type=OrderType.MARKET),
        position_sizing=PositionSizing(target_notional=100.0),
        risk_budget=RiskBudget(max_gross_exposure_usdt=10_000.0),
    )
    engine = EconomicSimulationEngine(policy=policy, fee_model=bounded_fees)
    summary = engine.simulate(candles=[_bar(1000, volume=1000.0)], signals=[_sig(1000)])

    # Finite bound exists and is within cap -> admitted
    assert len(summary.trade_events) == 1


# =====================================================================
# AR5 — AMBIGUOUS EXIT HANDLING ENFORCEMENT
# =====================================================================


def test_ar5_ambiguous_collision_reject_ambiguous_long() -> None:
    """Under REJECT_AMBIGUOUS, simultaneous SL and TP touch in LONG raises AmbiguousExitRejectionError."""
    policy = TradePolicy(
        policy_id="AR5_REJECT_LONG",
        name="Reject Ambiguous Long",
        exit_rule=ExitRule(
            stop_loss_pct=0.05,
            take_profit_pct=0.05,
            ambiguous_exit_handling="REJECT_AMBIGUOUS",
        ),
        position_sizing=PositionSizing(target_notional=100.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    bars = [
        _bar(1000, o=100.0, c=100.0),
        _bar(2000, o=100.0, h=110.0, l=90.0, c=95.0),  # both 105 TP and 95 SL touched
    ]
    with pytest.raises(AmbiguousExitRejectionError, match="Ambiguous exit collision"):
        engine.simulate(candles=bars, signals=[_sig(1000, direction=1)])


def test_ar5_ambiguous_collision_reject_ambiguous_short() -> None:
    """Under REJECT_AMBIGUOUS, simultaneous SL and TP touch in SHORT raises AmbiguousExitRejectionError."""
    policy = TradePolicy(
        policy_id="AR5_REJECT_SHORT",
        name="Reject Ambiguous Short",
        exit_rule=ExitRule(
            stop_loss_pct=0.05,
            take_profit_pct=0.05,
            ambiguous_exit_handling="REJECT_AMBIGUOUS",
        ),
        position_sizing=PositionSizing(target_notional=100.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    bars = [
        _bar(1000, o=100.0, c=100.0),
        _bar(2000, o=100.0, h=110.0, l=90.0, c=105.0),  # short: 95 TP and 105 SL touched
    ]
    with pytest.raises(AmbiguousExitRejectionError, match="Ambiguous exit collision"):
        engine.simulate(candles=bars, signals=[_sig(1000, direction=-1)])


def test_ar5_ambiguous_collision_conservative_stop_first_both_sides() -> None:
    """Under CONSERVATIVE_STOP_FIRST, Stop Loss is evaluated first for both LONG and SHORT."""
    policy = TradePolicy(
        policy_id="AR5_CONSERVATIVE",
        name="Conservative Stop First",
        exit_rule=ExitRule(
            stop_loss_pct=0.05,
            take_profit_pct=0.05,
            ambiguous_exit_handling="CONSERVATIVE_STOP_FIRST",
        ),
        position_sizing=PositionSizing(target_notional=100.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)

    # Long collision: closes as CLOSE_LONG with stop loss
    bars_long = [
        _bar(1000, o=100.0, c=100.0),
        _bar(2000, o=100.0, h=110.0, l=90.0, c=95.0),
    ]
    res_long = engine.simulate(candles=bars_long, signals=[_sig(1000, direction=1)])
    assert res_long.total_trades == 1
    assert res_long.losing_trades == 1
    assert res_long.trade_events[-1].action == TradeAction.CLOSE_LONG

    # Short collision: closes as CLOSE_SHORT with stop loss
    bars_short = [
        _bar(1000, o=100.0, c=100.0),
        _bar(2000, o=100.0, h=110.0, l=90.0, c=105.0),
    ]
    res_short = engine.simulate(candles=bars_short, signals=[_sig(1000, direction=-1)])
    assert res_short.total_trades == 1
    assert res_short.losing_trades == 1
    assert res_short.trade_events[-1].action == TradeAction.CLOSE_SHORT


# =====================================================================
# AR6 — UNIFIED EXIT EXECUTION ADAPTER
# =====================================================================


def test_ar6_all_six_exit_types_traverse_execution_adapter() -> None:
    """All 6 exit paths traverse ExecutionModel and produce monotonic TradeEvents."""
    # 1. Signal Reversal Exit
    p_rev = TradePolicy(policy_id="EXIT_1", name="Reversal", exit_rule=ExitRule(decay_exit_on_signal_reversal=True))
    eng_rev = EconomicSimulationEngine(policy=p_rev, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    res_rev = eng_rev.simulate(
        candles=[_bar(1000), _bar(2000)],
        signals=[_sig(1000, direction=1), _sig(2000, direction=-1)],
    )
    assert len(res_rev.trade_events) == 2
    assert res_rev.trade_events[1].action == TradeAction.CLOSE_LONG

    # 2. Gap Stop Exit
    p_gap = TradePolicy(policy_id="EXIT_2", name="Gap", exit_rule=ExitRule(stop_loss_pct=0.05))
    eng_gap = EconomicSimulationEngine(policy=p_gap, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    res_gap = eng_gap.simulate(
        candles=[_bar(1000, o=100.0, c=100.0), _bar(2000, o=80.0, c=80.0)],
        signals=[_sig(1000)],
    )
    assert len(res_gap.trade_events) == 2
    assert res_gap.trade_events[1].price == 80.0

    # 3. Stop Loss Exit
    p_sl = TradePolicy(policy_id="EXIT_3", name="SL", exit_rule=ExitRule(stop_loss_pct=0.05))
    eng_sl = EconomicSimulationEngine(policy=p_sl, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    res_sl = eng_sl.simulate(
        candles=[_bar(1000, o=100.0, c=100.0), _bar(2000, o=100.0, l=90.0, c=95.0)],
        signals=[_sig(1000)],
    )
    assert len(res_sl.trade_events) == 2
    assert res_sl.trade_events[1].price == 95.0

    # 4. Take Profit Exit
    p_tp = TradePolicy(policy_id="EXIT_4", name="TP", exit_rule=ExitRule(take_profit_pct=0.05))
    eng_tp = EconomicSimulationEngine(policy=p_tp, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    res_tp = eng_tp.simulate(
        candles=[_bar(1000, o=100.0, c=100.0), _bar(2000, o=100.0, h=110.0, c=105.0)],
        signals=[_sig(1000)],
    )
    assert len(res_tp.trade_events) == 2
    assert res_tp.trade_events[1].price == 105.0

    # 5. Trailing Stop Exit
    p_ts = TradePolicy(policy_id="EXIT_5", name="TS", exit_rule=ExitRule(trailing_stop_pct=0.05))
    eng_ts = EconomicSimulationEngine(policy=p_ts, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    res_ts = eng_ts.simulate(
        candles=[
            _bar(1000, o=100.0, c=120.0),  # Peak = 120
            _bar(2000, o=120.0, l=110.0, c=114.0),  # Trailing stop 5% of 120 = 114
        ],
        signals=[_sig(1000)],
    )
    assert len(res_ts.trade_events) == 2
    assert res_ts.trade_events[1].price == 114.0

    # 6. Max Holding Exit
    p_hold = TradePolicy(policy_id="EXIT_6", name="Hold", exit_rule=ExitRule(max_holding_ms=1000))
    eng_hold = EconomicSimulationEngine(policy=p_hold, execution_model=ZERO_LATENCY, fee_model=ZERO_FEES)
    res_hold = eng_hold.simulate(
        candles=[_bar(1000, o=100.0, duration=1000), _bar(2000, o=100.0, duration=1000, c=102.0)],
        signals=[_sig(1000)],
    )
    assert len(res_hold.trade_events) == 2
    assert res_hold.trade_events[1].price == 102.0

    # Monotonicity check across all events
    for res in (res_rev, res_gap, res_sl, res_tp, res_ts, res_hold):
        entry_ev = res.trade_events[0]
        exit_ev = res.trade_events[1]
        assert exit_ev.timestamp_ms >= entry_ev.timestamp_ms
        assert exit_ev.observation_timestamp_ms is not None
        assert exit_ev.decision_timestamp_ms is not None
        assert exit_ev.order_timestamp_ms is not None
        assert exit_ev.settlement_timestamp_ms is not None
        assert (
            exit_ev.observation_timestamp_ms
            <= exit_ev.decision_timestamp_ms
            <= exit_ev.order_timestamp_ms
            <= exit_ev.timestamp_ms
            <= exit_ev.settlement_timestamp_ms
        )


def test_ar6_exit_slippage_and_fee_applied_through_execution_model() -> None:
    """Exit orders suffer actual slippage and taker fees through ExecutionModel exactly once."""
    fee_model = FeeModel(
        maker_fee_rate=0.0002,
        taker_fee_rate=0.0005,  # 5 bps
        slippage_mode=SlippageMode.FIXED_BPS,
        fixed_slippage_bps=10.0,  # 10 bps slippage
    )
    policy = TradePolicy(
        policy_id="AR6_FEES",
        name="Exit Fee Test",
        exit_rule=ExitRule(stop_loss_pct=0.05),
        position_sizing=PositionSizing(target_notional=100.0),
    )
    engine = EconomicSimulationEngine(
        policy=policy,
        execution_model=ExecutionModel(fee_model=fee_model, decision_latency_ms=0, exchange_latency_ms=0),
        fee_model=fee_model,
    )
    bars = [
        _bar(1000, o=100.0, c=100.0),
        _bar(2000, o=100.0, l=90.0, c=95.0),
    ]
    summary = engine.simulate(candles=bars, signals=[_sig(1000)])

    assert len(summary.trade_events) == 2
    exit_event = summary.trade_events[1]
    # LONG exit sells: price suffers downward slippage 95 * (1 - 0.001) = 94.905
    assert exit_event.price == pytest.approx(94.905, abs=1e-3)
    # Taker fee is charged on exit notional
    expected_fee = exit_event.price * exit_event.quantity * 0.0005
    assert exit_event.fee_usdt == pytest.approx(expected_fee, abs=1e-4)


def test_ar6_exit_latency_shifts_exit_fill_timestamp() -> None:
    """Exit latency causally shifts the exit fill timestamp to a future candle."""
    exec_model = ExecutionModel(
        fee_model=ZERO_FEES,
        decision_latency_ms=500,
        exchange_latency_ms=150,  # total 650 ms
    )
    policy = TradePolicy(
        policy_id="AR6_LATENCY",
        name="Exit Latency Test",
        exit_rule=ExitRule(stop_loss_pct=0.05),
        position_sizing=PositionSizing(target_notional=100.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=exec_model, fee_model=ZERO_FEES)
    # Bar 1: t=1000..1999 (entry fills at 1999)
    # Bar 2: t=2000..2999 (SL triggers at 2999, order timestamp 3499, earliest fill 3649)
    # Bar 3: t=3000..3999 (candle covers 3649; fills at 3649)
    bars = [
        _bar(open_time_ms=1000, o=100.0, c=100.0),
        _bar(open_time_ms=2000, o=100.0, l=90.0, c=95.0),
        _bar(open_time_ms=3000, o=95.0, c=95.0),
    ]
    summary = engine.simulate(candles=bars, signals=[_sig(1000)])

    assert len(summary.trade_events) == 2
    entry_ev = summary.trade_events[0]
    exit_ev = summary.trade_events[1]
    assert entry_ev.timestamp_ms == 1999
    # Exit was triggered at 2999; with 650 ms latency it filled in bar 3 at or after 3649!
    assert exit_ev.timestamp_ms >= 3649
    assert exit_ev.timestamp_ms > entry_ev.timestamp_ms


def test_ar6_no_exit_trade_event_without_confirmed_execution_result() -> None:
    """If market data is exhausted when exit triggers, no fabricated TradeEvent is committed."""
    exec_model = ExecutionModel(
        fee_model=ZERO_FEES,
        decision_latency_ms=500,
        exchange_latency_ms=150,  # 650 ms latency
    )
    policy = TradePolicy(
        policy_id="AR6_EXHAUST",
        name="Market Data Exhaustion",
        exit_rule=ExitRule(stop_loss_pct=0.05),
        position_sizing=PositionSizing(target_notional=100.0),
    )
    engine = EconomicSimulationEngine(policy=policy, execution_model=exec_model, fee_model=ZERO_FEES)
    # Only 2 bars; exit triggers at 2999 and needs data at 3649, but no bar 3 exists!
    bars = [
        _bar(open_time_ms=1000, o=100.0, c=100.0),
        _bar(open_time_ms=2000, o=100.0, l=90.0, c=95.0),
    ]
    summary = engine.simulate(candles=bars, signals=[_sig(1000)])

    # Entry occurred at 1999, but exit could not execute due to market data exhaustion
    assert len(summary.trade_events) == 1
    assert summary.trade_events[0].action == TradeAction.OPEN_LONG
