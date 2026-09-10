"""B01 adversarial tests for LIMIT observable-time and expiry causality."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest
from helpers_v042_semantic_goldens import case_by_id, load_goldens

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.execution_model import (
    LIMIT_INTRABAR_TOUCH_AMBIGUOUS,
    ExecutionModel,
)
from btc_quant_agent.economic.fee_model import FeeModel, SlippageMode
from btc_quant_agent.economic.funding import FundingModel, FundingSettlement
from btc_quant_agent.economic.policy import (
    EntryRule,
    ExitRule,
    OrderType,
    PositionSizing,
    TradePolicy,
)
from btc_quant_agent.economic.portfolio import Portfolio
from btc_quant_agent.economic.qualification import execution_model_identity
from btc_quant_agent.economic.signal import InformationSignal
from btc_quant_agent.economic.simulator import (
    AmbiguousEntryRejectionError,
    EconomicSimulationEngine,
)
from btc_quant_agent.research_contract.canonical import canonical_sha256

ZERO_FEE = FeeModel(
    maker_fee_rate=0.0,
    taker_fee_rate=0.0,
    slippage_mode=SlippageMode.ZERO,
)


def _bar(
    *,
    open_time_ms: int = 1_000,
    duration_ms: int = 900_000,
    open_price: float = 100.0,
    high: float = 110.0,
    low: float = 90.0,
    close: float = 100.0,
    volume: float = 1_000.0,
) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        interval="15m",
        open_time_ms=open_time_ms,
        close_time_ms=open_time_ms + duration_ms - 1,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def _execution(*, touch_probability: float = 1.0) -> ExecutionModel:
    return ExecutionModel(
        fee_model=ZERO_FEE,
        decision_latency_ms=0,
        exchange_latency_ms=0,
        limit_fill_prob_on_touch=touch_probability,
    )


def _signal(*, direction: int = 1, timestamp_ms: int = 1_000) -> InformationSignal:
    return InformationSignal(
        signal_id=f"B01_{direction}_{timestamp_ms}",
        experiment_id="B01_SYNTHETIC",
        timestamp_ms=timestamp_ms,
        asset="BTCUSDT",
        direction=direction,
        strength=1.0,
    )


def _limit_policy(
    *,
    offset_bps: float = 500.0,
    tif_ms: int = 60_000,
    exit_rule: ExitRule | None = None,
) -> TradePolicy:
    return TradePolicy(
        policy_id="B01_LIMIT",
        name="B01 synthetic LIMIT",
        entry_rule=EntryRule(
            order_type=OrderType.LIMIT,
            limit_offset_bps=offset_bps,
            time_in_force_ms=tif_ms,
        ),
        exit_rule=exit_rule or ExitRule(),
        position_sizing=PositionSizing(target_notional=100.0),
    )


def _assert_ambiguous(result: Any) -> None:
    assert not result.is_filled
    assert result.fill_price == 0.0
    assert result.filled_quantity == 0.0
    assert result.rejection_reason == LIMIT_INTRABAR_TOUCH_AMBIGUOUS
    assert result.metadata["execution_time_semantics"] == "INTRABAR_UNKNOWN"


def test_b01_01_d_b2_buy_one_ms_expiry_golden_is_closed() -> None:
    case = case_by_id(load_goldens(), "D-B2-LIMIT-TOUCH-UNRESOLVED")
    inputs = case["inputs"]
    order = inputs["order"]
    bar = inputs["bar"]
    expiry_ms = int(order["expiry_time_ms"]) - int(order["submit_time_ms"])

    result = _execution().simulate_order(
        signal_timestamp_ms=int(order["submit_time_ms"]),
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[
            _bar(
                open_time_ms=int(inputs["bar_open_time_ms"]),
                open_price=float(bar["open"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                close=float(bar["close"]),
            )
        ],
        limit_price=float(order["limit_price"]),
        time_in_force_ms=expiry_ms,
    )

    assert case["expected"]["correct_behavior"] == "AMBIGUOUS_NOT_TESTABLE"
    _assert_ambiguous(result)
    assert result.fill_timestamp_ms == int(order["expiry_time_ms"])


def test_b01_02_sell_one_ms_expiry_is_symmetric() -> None:
    result = _execution().simulate_order(
        signal_timestamp_ms=1_000,
        side=-1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[_bar()],
        limit_price=105.0,
        time_in_force_ms=1,
    )

    _assert_ambiguous(result)
    assert result.fill_timestamp_ms == 1_001


@pytest.mark.parametrize(
    ("side", "limit_price", "high", "low", "touch_kind"),
    [
        (1, 95.0, 105.0, 95.0, "EXACT_TOUCH"),
        (1, 95.0, 105.0, 94.0, "THROUGH"),
        (-1, 105.0, 105.0, 95.0, "EXACT_TOUCH"),
        (-1, 105.0, 106.0, 95.0, "THROUGH"),
    ],
    ids=["buy-touch", "buy-through", "sell-touch", "sell-through"],
)
def test_b01_03_touch_and_through_both_sides_never_backdate(
    side: int,
    limit_price: float,
    high: float,
    low: float,
    touch_kind: str,
) -> None:
    result = _execution().simulate_order(
        signal_timestamp_ms=1_000,
        side=side,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[_bar(high=high, low=low)],
        limit_price=limit_price,
        time_in_force_ms=10_000,
    )

    _assert_ambiguous(result)
    assert result.fill_timestamp_ms != 1_000
    assert result.metadata["touch_kind"] == touch_kind


@pytest.mark.parametrize("latent_path", ["TOUCH_BEFORE_EXPIRY", "TOUCH_AFTER_EXPIRY"])
def test_b01_04_identical_ohlc_latent_paths_have_same_not_testable_outcome(
    latent_path: str,
) -> None:
    # The latent label is deliberately not supplied to the OHLC API: both
    # tick paths collapse to the exact same observable candle.
    result = _execution().simulate_order(
        signal_timestamp_ms=1_000,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[_bar()],
        limit_price=95.0,
        time_in_force_ms=1,
    )

    assert latent_path in {"TOUCH_BEFORE_EXPIRY", "TOUCH_AFTER_EXPIRY"}
    _assert_ambiguous(result)


def test_b01_05_funding_inside_ambiguous_window_cannot_receive_position() -> None:
    class FundingSpy(FundingModel):
        calls = 0

        def calculate_cashflow(
            self, position_quantity: float, mark_price: float, funding_rate: float
        ) -> float:
            self.calls += 1
            return super().calculate_cashflow(position_quantity, mark_price, funding_rate)

    funding = FundingSpy()
    engine = EconomicSimulationEngine(
        policy=_limit_policy(tif_ms=5_000),
        execution_model=_execution(),
        fee_model=ZERO_FEE,
        funding_model=funding,
        initial_cash=10_000.0,
    )

    with pytest.raises(AmbiguousEntryRejectionError, match="OHLC extrema cannot timestamp"):
        engine.simulate(
            candles=[_bar(duration_ms=10_000)],
            signals=[_signal()],
            funding_events=[
                FundingSettlement(
                    timestamp_ms=1_500,
                    mark_price=100.0,
                    funding_rate=0.01,
                )
            ],
        )
    assert funding.calls == 0


@pytest.mark.parametrize(
    ("side", "limit_price"),
    [(1, 101.0), (-1, 99.0)],
    ids=["buy", "sell"],
)
@pytest.mark.parametrize(("high", "low"), [(100.0, 100.0), (150.0, 50.0)])
def test_b01_06_g10_marketable_open_ignores_later_bar_suffix(
    side: int, limit_price: float, high: float, low: float
) -> None:
    golden = case_by_id(load_goldens(), "G10-MARKETABLE-LIMIT-AT-OPEN")
    open_price = float(golden["inputs"]["bar_open"])
    observed_ask = float(golden["inputs"]["observable_open_ask"])
    executable_quote = observed_ask if side == 1 else 2 * open_price - observed_ask
    fees = FeeModel(
        maker_fee_rate=0.001,
        taker_fee_rate=0.002,
        slippage_mode=SlippageMode.ZERO,
    )
    result = ExecutionModel(
        fee_model=fees,
        decision_latency_ms=0,
        exchange_latency_ms=0,
        limit_fill_prob_on_touch=1.0,
    ).simulate_order(
        signal_timestamp_ms=int(golden["inputs"]["submit_time_ms"]),
        side=side,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[
            _bar(
                open_price=open_price,
                high=high,
                low=low,
            )
        ],
        limit_price=limit_price,
        time_in_force_ms=1_000,
        observable_open_executable_price=executable_quote,
        observable_open_executable_timestamp_ms=1_000,
    )

    assert float(golden["inputs"]["limit_price"]) >= float(
        golden["inputs"]["observable_open_ask"]
    )
    assert golden["expected"]["outcome"] == "FILL_AT_OPEN_ALLOWED"
    assert result.is_filled
    assert result.fill_timestamp_ms == 1_000
    assert result.fill_price <= float(golden["expected"]["latest_permitted_price"])
    assert result.fill_price == executable_quote
    assert result.is_maker is False
    assert result.fee_usdt == pytest.approx(executable_quote * 0.002)
    assert result.metadata["opening_price_evidence"] == "TIMESTAMPED_EXECUTABLE_QUOTE"
    assert result.metadata["execution_time_semantics"] == "BAR_OPEN_MARKETABLE"


def test_b01_g10_open_mid_below_limit_but_observed_ask_above_limit_does_not_fill() -> None:
    golden = case_by_id(load_goldens(), "G10-MARKETABLE-LIMIT-AT-OPEN")
    result = _execution().simulate_order(
        signal_timestamp_ms=int(golden["inputs"]["submit_time_ms"]),
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[_bar()],
        limit_price=100.1,
        time_in_force_ms=1_000,
        observable_open_executable_price=float(golden["inputs"]["observable_open_ask"]),
        observable_open_executable_timestamp_ms=1_000,
    )

    _assert_ambiguous(result)


def test_b01_marketable_sell_preserves_reserved_notional_cap() -> None:
    result = _execution().simulate_order(
        signal_timestamp_ms=1_000,
        side=-1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[
            _bar(open_price=110.0, high=110.0, low=100.0, close=105.0)
        ],
        limit_price=100.0,
        time_in_force_ms=1_000,
        max_fill_notional=100.0,
    )

    assert result.is_filled
    assert result.fill_price * result.filled_quantity == pytest.approx(100.0)
    assert result.metadata["notional_cap_applied"] is True


def test_b01_07_g09_no_funding_and_equal_time_funding_lifecycles() -> None:
    golden = case_by_id(load_goldens(), "G09-CAUSAL-EVENT-ORDER")
    inputs = golden["inputs"]
    exact_timeline = ExecutionModel(
        fee_model=ZERO_FEE,
        decision_latency_ms=int(inputs["decision_ms"])
        - int(inputs["signal_observation_ms"]),
        exchange_latency_ms=0,
        limit_fill_prob_on_touch=1.0,
        order_submission_latency_ms=int(inputs["order_ms"]) - int(inputs["decision_ms"]),
    ).simulate_order(
        signal_timestamp_ms=int(inputs["signal_observation_ms"]),
        observation_timestamp_ms=int(inputs["signal_observation_ms"]),
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[
            _bar(
                open_time_ms=int(inputs["fill_ms"]),
                duration_ms=int(inputs["terminal_ms"]) - int(inputs["fill_ms"]) + 1,
            )
        ],
        limit_price=101.0,
        time_in_force_ms=int(inputs["fill_ms"]) - int(inputs["order_ms"]),
        observable_open_executable_price=100.0,
        observable_open_executable_timestamp_ms=int(inputs["fill_ms"]),
    )
    assert exact_timeline.observation_timestamp_ms == int(inputs["signal_observation_ms"])
    assert exact_timeline.decision_timestamp_ms == int(inputs["decision_ms"])
    assert exact_timeline.order_timestamp_ms == int(inputs["order_ms"])
    assert exact_timeline.fill_timestamp_ms == int(inputs["fill_ms"])
    assert int(inputs["market_available_ms"]) <= exact_timeline.observation_timestamp_ms

    lifecycle_bar = _bar(
        open_time_ms=int(inputs["fill_ms"]),
        duration_ms=int(inputs["terminal_ms"]) - int(inputs["fill_ms"]) + 1,
    )
    engine = EconomicSimulationEngine(
        policy=_limit_policy(offset_bps=0.0),
        execution_model=ExecutionModel(
            fee_model=ZERO_FEE,
            decision_latency_ms=int(inputs["decision_ms"])
            - int(inputs["signal_observation_ms"]),
            exchange_latency_ms=0,
            limit_fill_prob_on_touch=1.0,
            order_submission_latency_ms=int(inputs["order_ms"])
            - int(inputs["decision_ms"]),
        ),
        fee_model=ZERO_FEE,
        initial_cash=10_000.0,
    )
    no_funding = engine.simulate(
        candles=[lifecycle_bar],
        signals=[_signal(timestamp_ms=int(inputs["signal_observation_ms"]))],
    )
    tied_funding = engine.simulate(
        candles=[lifecycle_bar],
        signals=[_signal(timestamp_ms=int(inputs["signal_observation_ms"]))],
        funding_events=[FundingSettlement(int(inputs["funding_ms"]), 100.0, 0.01)],
    )

    assert golden["expected"]["tie_break"] == "FUNDING_BEFORE_FILL"
    assert golden["expected"]["ordered_events_without_funding"] == [
        "MARKET_AVAILABLE",
        "SIGNAL_OBSERVED",
        "DECISION",
        "ORDER",
        "FILL",
        "TERMINAL",
    ]
    assert no_funding.total_funding_usdt == 0.0
    assert tied_funding.total_funding_usdt == 0.0
    assert len(no_funding.trade_events) == len(tied_funding.trade_events) == 1
    for summary in (no_funding, tied_funding):
        event = summary.trade_events[0]
        assert event.observation_timestamp_ms == int(inputs["signal_observation_ms"])
        assert event.decision_timestamp_ms == int(inputs["decision_ms"])
        assert event.order_timestamp_ms == int(inputs["order_ms"])
        assert event.timestamp_ms == int(inputs["fill_ms"])
        assert summary.equity_curve[-1][0] == int(inputs["terminal_ms"])


def test_b01_submission_latency_identity_is_explicit_and_default_hash_is_compatible() -> None:
    default_model = _execution()
    delayed_model = ExecutionModel(
        fee_model=ZERO_FEE,
        decision_latency_ms=0,
        exchange_latency_ms=0,
        limit_fill_prob_on_touch=1.0,
        order_submission_latency_ms=1,
    )
    legacy_payload = {
        "decision_latency_ms": 0,
        "exchange_latency_ms": 0,
        "limit_fill_prob_on_touch": 1.0,
        "fee_model_sha256": canonical_sha256(asdict(ZERO_FEE)),
    }
    delayed_payload = {**legacy_payload, "order_submission_latency_ms": 1}

    assert execution_model_identity(default_model, "B01_EXEC", "v1").content_sha256 == (
        canonical_sha256(legacy_payload)
    )
    assert execution_model_identity(delayed_model, "B01_EXEC", "v1").content_sha256 == (
        canonical_sha256(delayed_payload)
    )


def test_b01_08_arrival_inside_bar_cannot_consume_earlier_extreme() -> None:
    execution = ExecutionModel(
        fee_model=ZERO_FEE,
        decision_latency_ms=500,
        exchange_latency_ms=150,
        limit_fill_prob_on_touch=1.0,
    )
    result = execution.simulate_order(
        signal_timestamp_ms=1_700,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[
            _bar(open_time_ms=1_000, duration_ms=2_000, low=90.0),
            _bar(open_time_ms=3_000, open_price=94.0, high=100.0, low=90.0, close=95.0),
        ],
        limit_price=95.0,
        time_in_force_ms=5_000,
    )

    assert result.is_filled
    assert result.fill_timestamp_ms == 3_000
    assert result.metadata["observable_open"] == 94.0


def test_b01_09_expiry_boundary_is_inclusive_and_later_fill_is_rejected() -> None:
    equality = _execution().simulate_order(
        signal_timestamp_ms=1_000,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[
            _bar(open_time_ms=1_001, open_price=94.0, high=100.0, low=90.0, close=95.0)
        ],
        limit_price=95.0,
        time_in_force_ms=1,
    )
    after = _execution().simulate_order(
        signal_timestamp_ms=1_000,
        side=1,
        desired_quantity=1.0,
        order_type=OrderType.LIMIT,
        future_candles=[
            _bar(open_time_ms=1_002, open_price=94.0, high=100.0, low=90.0, close=95.0)
        ],
        limit_price=95.0,
        time_in_force_ms=1,
    )

    assert equality.is_filled
    assert equality.fill_timestamp_ms == 1_001
    assert not after.is_filled
    assert after.rejection_reason == "LIMIT_EXPIRED_UNFILLED"


def test_b01_10_unresolved_entry_cannot_trigger_same_bar_exit_or_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied_trades: list[int] = []
    original_apply_trade = Portfolio.apply_trade

    def apply_trade_spy(self: Portfolio, timestamp_ms: int, *args: Any, **kwargs: Any) -> Any:
        applied_trades.append(timestamp_ms)
        return original_apply_trade(self, timestamp_ms, *args, **kwargs)

    monkeypatch.setattr(Portfolio, "apply_trade", apply_trade_spy)
    engine = EconomicSimulationEngine(
        policy=_limit_policy(
            tif_ms=5_000,
            exit_rule=ExitRule(stop_loss_pct=0.01, take_profit_pct=0.01),
        ),
        execution_model=_execution(),
        fee_model=ZERO_FEE,
        initial_cash=10_000.0,
    )

    with pytest.raises(AmbiguousEntryRejectionError):
        engine.simulate(candles=[_bar()], signals=[_signal()])
    assert applied_trades == []
