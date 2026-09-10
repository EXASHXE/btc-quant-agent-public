"""A04 semantic goldens: independent truth, not current-behavior snapshots."""

from __future__ import annotations

from decimal import Decimal

import pytest

from btc_quant_agent.data.quality import validate_candles
from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.benchmarks import BenchmarkEngine
from btc_quant_agent.economic.fee_model import FeeModel, SlippageMode
from btc_quant_agent.economic.metrics import ResultCompleteness, TerminalPolicy, summarize_ledger
from btc_quant_agent.economic.portfolio import Portfolio
from btc_quant_agent.economic.trade_event import TradeAction
from helpers_v042_semantic_goldens import (
    case_by_id,
    decimal,
    funding_cashflow,
    linear_realized_pnl,
    load_goldens,
    preregistered_random_draws,
)

ABS_TOL = 1e-8
ASSET = "BTCUSDT"


def _assert_float_decimal(actual: float, expected: str) -> None:
    assert actual == pytest.approx(float(decimal(expected)), rel=0.0, abs=ABS_TOL)


def _candle(value: dict[str, object]) -> Candle:
    return Candle(
        symbol=str(value["symbol"]),
        interval=str(value["interval"]),
        open_time_ms=int(value["open_time_ms"]),
        close_time_ms=int(value["close_time_ms"]),
        open=float(value["open"]),
        high=float(value["high"]),
        low=float(value["low"]),
        close=float(value["close"]),
        volume=float(value["volume"]),
        quote_volume=float(value["quote_volume"]),
        closed=bool(value["closed"]),
    )


def test_golden_schema_is_unique_complete_and_versioned() -> None:
    document = load_goldens()
    assert document["schema_version"] == "1.0.0"
    assert document["generated_from_git_sha"] == "3aad7b1e055fdca978ab35a67c534664f67978b8"
    assert document["numeric_policy"]["production_float_comparison_absolute_tolerance"] == (
        "0.00000001"
    )
    cases = document["cases"]
    case_ids = [case["case_id"] for case in cases]
    assert len(case_ids) == len(set(case_ids))
    assert len(cases) == 23
    required = {
        "case_id",
        "domain",
        "status",
        "rationale",
        "inputs",
        "expected",
        "independent_derivation",
        "future_task_owner",
    }
    for case in cases:
        assert required <= set(case)
        assert case["status"] in {
            "VALID_GOLDEN",
            "KNOWN_DEFECT_EXPECT_REJECTION",
            "CHARACTERIZATION_ONLY",
        }
        assert case["independent_derivation"]


@pytest.mark.parametrize(
    ("case_id", "opening", "closing"),
    [
        ("G01-LONG-ACCOUNTING", TradeAction.OPEN_LONG, TradeAction.CLOSE_LONG),
        ("G02-SHORT-ACCOUNTING", TradeAction.OPEN_SHORT, TradeAction.CLOSE_SHORT),
    ],
)
def test_g01_g02_linear_accounting_uses_decimal_oracle_then_current_control(
    case_id: str,
    opening: TradeAction,
    closing: TradeAction,
) -> None:
    case = case_by_id(load_goldens(), case_id)
    inputs = case["inputs"]
    expected = case["expected"]
    realized = linear_realized_pnl(
        side=inputs["side"],
        quantity=inputs["quantity"],
        open_price=inputs["open_price"],
        close_price=inputs["close_price"],
    )
    net_change = realized - decimal(inputs["entry_fee"]) - decimal(inputs["exit_fee"])
    final_cash = decimal(inputs["initial_cash"]) + net_change
    assert realized == decimal(expected["realized_pnl"])
    assert net_change == decimal(expected["net_cash_change"])
    assert final_cash == decimal(expected["final_cash"])

    portfolio = Portfolio(initial_cash=float(inputs["initial_cash"]))
    portfolio.apply_trade(
        1000,
        opening,
        ASSET,
        float(inputs["open_price"]),
        float(inputs["quantity"]),
        float(inputs["entry_fee"]),
    )
    close = portfolio.apply_trade(
        2000,
        closing,
        ASSET,
        float(inputs["close_price"]),
        float(inputs["quantity"]),
        float(inputs["exit_fee"]),
    )
    _assert_float_decimal(close.realized_pnl_usdt, expected["realized_pnl"])
    _assert_float_decimal(portfolio.cash, expected["final_cash"])
    _assert_float_decimal(portfolio.total_equity({}), expected["final_equity"])
    assert portfolio.get_position_quantity(ASSET) == 0.0


def test_g03_partial_weighted_roundtrip_is_hand_derived() -> None:
    case = case_by_id(load_goldens(), "G03-PARTIAL-WEIGHTED-ROUNDTRIP")
    events = case["inputs"]["events"]
    expected = case["expected"]
    quantities = [decimal(events[index]["quantity"]) for index in (0, 1)]
    weighted = sum(
        decimal(events[index]["price"]) * quantities[index] for index in (0, 1)
    ) / sum(quantities)
    total_entry_cost = sum(
        decimal(events[index]["price"]) * quantities[index] for index in (0, 1)
    )
    total_quantity = sum(quantities)
    partial_quantity = decimal(events[2]["quantity"])
    partial_cost_basis = total_entry_cost * partial_quantity / total_quantity
    partial_realized = partial_quantity * decimal(events[2]["price"]) - partial_cost_basis
    remaining = total_quantity - partial_quantity
    remaining_cost_basis = total_entry_cost - partial_cost_basis
    unrealized = (
        remaining * decimal(case["inputs"]["intermediate_mark_price"])
        - remaining_cost_basis
    )
    fees_before_final = sum(decimal(item["fee"]) for item in events[:3])
    partial_cash = decimal(case["inputs"]["initial_cash"]) + partial_realized - fees_before_final
    second_realized = (
        decimal(events[3]["quantity"]) * decimal(events[3]["price"])
        - remaining_cost_basis
    )
    total_fees = sum(decimal(item["fee"]) for item in events)
    final_cash = (
        decimal(case["inputs"]["initial_cash"])
        + partial_realized
        + second_realized
        - total_fees
    )
    assert weighted == decimal(expected["weighted_entry_price"])
    assert partial_realized == decimal(expected["after_partial_close"]["realized_pnl"])
    assert partial_cash == decimal(expected["after_partial_close"]["cash"])
    assert unrealized == decimal(expected["after_partial_close"]["unrealized_pnl"])
    assert partial_cash + unrealized == decimal(expected["after_partial_close"]["equity"])
    assert second_realized == decimal(
        expected["completed_round_trip"]["second_close_realized_pnl"]
    )
    assert final_cash == decimal(expected["completed_round_trip"]["final_cash"])

    portfolio = Portfolio(initial_cash=float(case["inputs"]["initial_cash"]))
    actions = (
        TradeAction.OPEN_LONG,
        TradeAction.OPEN_LONG,
        TradeAction.CLOSE_LONG,
        TradeAction.CLOSE_LONG,
    )
    for sequence, (event, action) in enumerate(zip(events, actions, strict=True), start=1):
        portfolio.apply_trade(
            sequence * 1000,
            action,
            ASSET,
            float(event["price"]),
            float(event["quantity"]),
            float(event["fee"]),
        )
        if sequence == 3:
            _assert_float_decimal(portfolio.cash, expected["after_partial_close"]["cash"])
            assert portfolio.positions[ASSET].average_entry_price == pytest.approx(float(weighted))
            _assert_float_decimal(
                portfolio.get_position_quantity(ASSET),
                expected["after_partial_close"]["remaining_quantity"],
            )
            _assert_float_decimal(
                portfolio.total_equity(
                    {ASSET: float(case["inputs"]["intermediate_mark_price"])}
                ),
                expected["after_partial_close"]["equity"],
            )
    _assert_float_decimal(portfolio.cash, expected["completed_round_trip"]["final_cash"])
    assert portfolio.get_position_quantity(ASSET) == 0.0


def test_g04_funding_sign_zero_position_and_equal_time_order() -> None:
    case = case_by_id(load_goldens(), "G04-FUNDING-SIGN-TIE")
    inputs = case["inputs"]
    expected = case["expected"]
    for signed_quantity, key in (
        (inputs["long_quantity"], "long_cashflow"),
        (inputs["short_quantity"], "short_cashflow"),
        ("0", "flat_cashflow"),
    ):
        assert funding_cashflow(
            signed_quantity=signed_quantity,
            mark_price=inputs["mark_price"],
            funding_rate=inputs["funding_rate"],
        ) == decimal(expected[key])

    long_book = Portfolio(initial_cash=1000)
    long_book.apply_trade(1000, TradeAction.OPEN_LONG, ASSET, 100, 2, 0)
    funding = long_book.apply_funding(2000, ASSET, -2, 100)
    close = long_book.apply_trade(2000, TradeAction.CLOSE_LONG, ASSET, 100, 2, 0)
    assert [funding.action.value, close.action.value] == expected["tie_order"]
    assert funding.position_after == 2
    assert long_book.cash == 998

    short_book = Portfolio(initial_cash=1000)
    short_book.apply_trade(1000, TradeAction.OPEN_SHORT, ASSET, 100, 2, 0)
    short_book.apply_funding(2000, ASSET, 2, 100)
    assert short_book.cash == 1002
    flat_book = Portfolio(initial_cash=1000)
    flat_book.apply_funding(1000, ASSET, 0, 100)
    assert flat_book.cash == 1000


def test_g05_terminal_modes_match_independent_mark_and_flat_arithmetic() -> None:
    case = case_by_id(load_goldens(), "G05-TERMINAL-POLICIES")
    expected = case["expected"]
    open_book = Portfolio(initial_cash=1000)
    open_book.apply_trade(1000, TradeAction.OPEN_LONG, ASSET, 100, 2, 0.2)
    open_events = tuple(open_book.trade_history)
    marked = summarize_ledger(
        initial_cash=1000,
        events=open_events,
        equity_curve=((1000, 999.8), (3000, 1019.8)),
        final_asset=ASSET,
        final_mark_price=110,
        interval_start_ms=1000,
        interval_end_ms=3000,
        notional_curve=((1000, 200), (3000, 220)),
        terminal_policy=TerminalPolicy.MARK_TO_MARKET_OPEN,
    )
    marked_expected = expected["MARK_TO_MARKET_OPEN"]
    _assert_float_decimal(marked.final_cash or 0, marked_expected["final_cash"])
    _assert_float_decimal(
        marked.terminal_unrealized_pnl_usdt or 0,
        marked_expected["terminal_unrealized_pnl"],
    )
    _assert_float_decimal(marked.final_equity, marked_expected["final_equity"])
    assert marked.completeness.value == marked_expected["completeness"]

    unsupported = summarize_ledger(
        initial_cash=1000,
        events=open_events,
        equity_curve=((1000, 999.8), (3000, 1019.8)),
        final_asset=ASSET,
        final_mark_price=110,
        interval_start_ms=1000,
        interval_end_ms=3000,
        notional_curve=((1000, 200), (3000, 220)),
        terminal_policy=TerminalPolicy.REQUIRE_FLAT,
    )
    assert unsupported.completeness is ResultCompleteness.UNSUPPORTED_TERMINAL_STATE

    open_book.apply_trade(3000, TradeAction.CLOSE_LONG, ASSET, 110, 2, 0.22)
    flat = summarize_ledger(
        initial_cash=1000,
        events=tuple(open_book.trade_history),
        equity_curve=((1000, 999.8), (3000, 1019.58)),
        final_asset=ASSET,
        final_mark_price=110,
        interval_start_ms=1000,
        interval_end_ms=3000,
        notional_curve=((1000, 200), (3000, 0)),
        terminal_policy=TerminalPolicy.REQUIRE_FLAT,
    )
    flat_expected = expected["REQUIRE_FLAT"]
    _assert_float_decimal(flat.final_cash or 0, flat_expected["final_cash"])
    _assert_float_decimal(flat.final_equity, flat_expected["final_equity"])
    assert flat.terminal_position_quantity == 0
    assert flat.completeness.value == flat_expected["completeness"]


def test_g06_cash_is_exact_no_trade_and_current_diagnostic_control_agrees() -> None:
    case = case_by_id(load_goldens(), "G06-CASH-NO-TRADE")
    expected = case["expected"]
    assert expected["trade_events"] == []
    for key in (
        "trade_count",
        "fill_count",
        "fees",
        "funding",
        "turnover",
        "time_exposure",
        "notional_exposure",
        "realized_pnl",
        "unrealized_pnl",
        "position_quantity",
    ):
        assert decimal(expected[key]) == 0
    result = BenchmarkEngine().simulate_cash_benchmark(
        float(case["inputs"]["initial_equity"]), case["inputs"]["mark_timestamps_ms"]
    )
    assert result.equity_curve == [(1000, 1000.0), (2000, 1000.0), (3000, 1000.0)]
    assert result.final_equity == 1000
    assert result.net_pnl_usdt == result.net_return_pct == 0


def test_g07_passive_zero_cost_is_hand_computed_before_production_comparison() -> None:
    case = case_by_id(load_goldens(), "G07-PASSIVE-SIMPLE-ZERO-COST")
    inputs = case["inputs"]
    expected = case["expected"]
    quantity = decimal(inputs["initial_cash"]) / decimal(inputs["entry_price"])
    exit_notional = quantity * decimal(inputs["terminal_price"])
    gross_pnl = exit_notional - decimal(inputs["initial_cash"])
    assert quantity == decimal(expected["quantity"])
    assert exit_notional == decimal(expected["exit_notional"])
    assert gross_pnl == decimal(expected["gross_pnl"])
    assert gross_pnl / decimal(inputs["initial_cash"]) == decimal(expected["net_return"])

    candles = (
        Candle(ASSET, "1m", 1000, 60999, 100, 105, 99, 105, 10),
        Candle(ASSET, "1m", 61000, 120999, 105, 111, 104, 110, 10),
    )
    fee_model = FeeModel(
        maker_fee_rate=0,
        taker_fee_rate=0,
        slippage_mode=SlippageMode.ZERO,
        fixed_slippage_bps=0,
    )
    result = BenchmarkEngine(fee_model).simulate_passive_btc(1000, candles)
    _assert_float_decimal(result.final_equity, expected["final_equity"])
    _assert_float_decimal(result.net_pnl_usdt, expected["gross_pnl"])
    _assert_float_decimal(result.net_return_pct, expected["net_return"])


def test_g08_random_seed_and_draws_are_independently_replayed() -> None:
    case = case_by_id(load_goldens(), "G08-DETERMINISTIC-RANDOM-PRIMITIVE")
    inputs = case["inputs"]
    observed = preregistered_random_draws(
        master_seed=inputs["master_seed"],
        ordered_opportunities=inputs["ordered_opportunities"],
        sample_count=inputs["sample_count"],
        direction_template=inputs["direction_template"],
        trial_count=inputs["trial_count"],
    )
    assert observed == case["expected"]["trials"]


def test_causal_order_and_limit_contrast_do_not_invent_intrabar_order() -> None:
    document = load_goldens()
    order_case = case_by_id(document, "G09-CAUSAL-EVENT-ORDER")
    times = order_case["inputs"]
    assert times["market_available_ms"] <= times["signal_observation_ms"]
    assert times["signal_observation_ms"] <= times["decision_ms"] <= times["order_ms"]
    assert times["order_ms"] <= times["funding_ms"] == times["fill_ms"]
    assert order_case["expected"]["tie_break"] == "FUNDING_BEFORE_FILL"
    ambiguous = case_by_id(document, "D-B2-LIMIT-TOUCH-UNRESOLVED")
    assert ambiguous["expected"]["correct_behavior"] == "AMBIGUOUS_NOT_TESTABLE"
    marketable = case_by_id(document, "G10-MARKETABLE-LIMIT-AT-OPEN")
    assert decimal(marketable["inputs"]["limit_price"]) >= decimal(
        marketable["inputs"]["observable_open_ask"]
    )
    assert marketable["expected"]["outcome"] == "FILL_AT_OPEN_ALLOWED"


def test_p7_defects_are_rejection_specs_not_blessed_outputs() -> None:
    document = load_goldens()
    required_defects = {
        "D-B1-FORGED-CANDIDATE-REPLAY": "B04/B05",
        "D-B2-LIMIT-TOUCH-UNRESOLVED": "B01",
        "D-H3-FUTURE-VOLUME-INVARIANCE": "B02",
        "D-H4-CLOSED-FALSE-NOT-COMPLETE": "B03",
        "D-H1-CLONED-RANDOM-TRIALS": "B06",
        "D-H2-TRADED-CASH": "B07",
    }
    for case_id, owner in required_defects.items():
        case = case_by_id(document, case_id)
        assert case["status"] == "KNOWN_DEFECT_EXPECT_REJECTION"
        assert case["future_task_owner"] == owner
        assert "current_characterization" in case
        corrected = str(case["expected"].get("correct_behavior", ""))
        assert corrected
        assert not corrected.startswith("ACCEPT")
    forged = case_by_id(document, "D-B1-FORGED-CANDIDATE-REPLAY")
    forged_inputs = forged["inputs"]
    forged_open, forged_close = forged_inputs["forged_events"]
    forged_realized = linear_realized_pnl(
        side="LONG",
        quantity=forged_open["quantity"],
        open_price=forged_open["price"],
        close_price=forged_close["price"],
    )
    assert forged_realized == decimal(forged_close["realized_pnl"])
    assert decimal(forged_inputs["initial_cash"]) + forged_realized == decimal(
        forged_close["cash_after"]
    )
    assert decimal(forged_open["price"]) < decimal(forged_inputs["candle"]["low"])
    assert set(forged["inputs"]["variants"]) == {
        "altered_fee",
        "altered_funding",
        "altered_quantity_or_risk_cap",
        "altered_signal_direction_or_time",
        "altered_terminal_event",
    }
    traded_cash = case_by_id(document, "D-H2-TRADED-CASH")
    attack = traded_cash["inputs"]["attack"]
    assert sum(
        decimal(event["price"]) * decimal(event["quantity"])
        for event in attack["trade_events"]
    ) == decimal(attack["summary"]["turnover"])
    assert attack["summary"]["final_equity"] == traded_cash["inputs"]["initial_cash"]
    assert attack["summary"]["fill_count"] == 2
    assert len(traded_cash["inputs"]["variants"]) == 4


def test_pit_contract_distinguishes_event_close_availability_and_decision_time() -> None:
    document = load_goldens()
    positive = case_by_id(document, "PIT-01-CLOSED-POSITIVE")
    candles = tuple(_candle(item) for item in positive["inputs"]["candles"])
    assert validate_candles(
        candles, "1m", now_ms=positive["inputs"]["decision_time_ms"]
    ).valid
    for item in positive["inputs"]["candles"]:
        assert int(item["open_time_ms"]) < int(item["close_time_ms"])
        assert int(item["available_at_ms"]) <= positive["inputs"]["decision_time_ms"]

    closed_false = case_by_id(document, "D-H4-CLOSED-FALSE-NOT-COMPLETE")
    unavailable_candle = _candle(closed_false["inputs"]["candles"][0])
    assert not validate_candles((unavailable_candle,), "1m").valid
    unavailable = case_by_id(document, "PIT-07-NOT-YET-AVAILABLE")
    assert unavailable["inputs"]["available_at_ms"] > unavailable["inputs"]["decision_time_ms"]
    assert unavailable["inputs"]["later_wall_clock_ms"] > unavailable["inputs"]["available_at_ms"]


def test_b01_b07_consumer_map_references_existing_exact_cases() -> None:
    document = load_goldens()
    case_ids = {case["case_id"] for case in document["cases"]}
    assert set(document["consumer_map"]) == {f"B0{index}" for index in range(1, 8)}
    for task, consumed in document["consumer_map"].items():
        assert consumed, task
        assert set(consumed) <= case_ids


def test_decimal_oracle_does_not_hide_binary_float_rounding() -> None:
    assert decimal("0.1") + decimal("0.2") == Decimal("0.3")
    assert 0.1 + 0.2 != float(Decimal("0.3"))
