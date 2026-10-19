from dataclasses import replace

import pytest

from scripts.research.strategy_eval.costs import (
    BASELINE, STRESS, US, Outcome, Settlement, economics, funding_long_debit, policy_action,
)


def label(*, price=110.0, rate=0.001):
    return Outcome(120, 120 + 8 * 3600, 100.0, price,
                   (Settlement(3600 * US, rate, 105.0),), (3600 * US,),
                   (120 * US, (120 + 8 * 3600) * US))


def test_per_leg_exit_notional_and_itemization():
    result = economics(label(), 1, 8)
    assert BASELINE.nominal_round_trip_bp == 16
    assert STRESS.nominal_round_trip_bp == 32
    assert result["entry_fee"] == pytest.approx(0.0005)
    assert result["exit_fee"] == pytest.approx(0.0005 * 1.1)
    assert result["exit_spread"] == pytest.approx(0.0001 * 1.1)
    assert result["exit_slippage"] == pytest.approx(0.0002 * 1.1)
    assert result["total_cost"] == pytest.approx(0.0008 * (1 + 1.1))
    assert result["funding_debit"] == pytest.approx(0.00105)
    assert result["net_return"] == pytest.approx(0.1 - 0.00105 - 0.00168)
    assert result["sleeve_pnl"] == pytest.approx(result["net_return"] / 8)
    assert result["turnover"] == pytest.approx(2.1 / 8)
    assert result["break_even_cost_bp"] == pytest.approx((0.1 - 0.00105) * 10000)


@pytest.mark.parametrize("price", [80, 100, 130])
@pytest.mark.parametrize("action", [-1, 1])
def test_costs_scale_both_directions_and_stress_monotonic(price, action):
    base = economics(label(price=price), action, 8)
    stress = economics(label(price=price), action, 8, STRESS)
    assert base["total_cost"] == pytest.approx(0.0008 * (1 + price / 100))
    assert stress["total_cost"] == pytest.approx(2 * base["total_cost"])
    assert stress["net_return"] < base["net_return"]


@pytest.mark.parametrize("rate", [-0.001, 0, 0.001])
def test_funding_long_short_sign(rate):
    long = economics(label(rate=rate), 1, 8)
    short = economics(label(rate=rate), -1, 8)
    assert long["funding_debit"] == pytest.approx(rate * 105 / 100)
    assert short["funding_debit"] == pytest.approx(-rate * 105 / 100)


def test_funding_entry_excluded_exit_included_and_future_ignored():
    value = label()
    entry, exit_t = value.entry_t * US, value.exit_t * US
    events = tuple(Settlement(t, rate, 100) for t, rate in (
        (entry, 10), (entry + 1, 0.001), (exit_t, 0.002), (exit_t + 1, 10)))
    value = replace(value, settlements=events,
                    expected_settlements_us=(entry, entry + 1, exit_t),
                    funding_coverage_us=(entry, exit_t))
    debit, reason = funding_long_debit(value)
    assert reason == "RESOLVED" and debit == pytest.approx(0.003)


@pytest.mark.parametrize("mutation,reason", [
    ({"funding_coverage_us": None}, "UNRESOLVED_FUNDING_COVERAGE"),
    ({"expected_settlements_us": None}, "UNRESOLVED_FUNDING_COVERAGE"),
    ({"settlements": ()}, "UNRESOLVED_FUNDING_SETTLEMENT"),
    ({"settlements": (Settlement(3600 * US, None, 100),)}, "UNRESOLVED_FUNDING_RATE_OR_MARK"),
    ({"settlements": (Settlement(3600 * US, 0.1, None),)}, "UNRESOLVED_FUNDING_RATE_OR_MARK"),
    ({"settlements": (Settlement(3600 * US, 0.1, 100),) * 2}, "FUNDING_CHRONOLOGY_INVALID"),
    ({"settlements": (Settlement(7200 * US, 0.1, 100), Settlement(3600 * US, 0.1, 100))}, "FUNDING_CHRONOLOGY_INVALID"),
    ({"expected_settlements_us": (3600 * US,) * 2}, "FUNDING_CALENDAR_INVALID"),
])
def test_missing_or_malformed_funding_is_unresolved(mutation, reason):
    result = economics(replace(label(), **mutation), 1, 8)
    assert result["status"] == "UTILITY_UNRESOLVED"
    assert result["reason"] == reason
    assert result["sleeve_pnl"] is None


def test_empty_calendar_is_zero_only_with_complete_interval_attestation():
    value = replace(label(), settlements=(), expected_settlements_us=())
    assert economics(value, 1, 8)["funding_debit"] == 0
    assert economics(replace(value, funding_coverage_us=None), 1, 8)["sleeve_pnl"] is None


@pytest.mark.parametrize("field", ["entry_price", "exit_price"])
@pytest.mark.parametrize("bad", [None, 0, float("nan"), float("inf")])
def test_missing_prices_do_not_become_cash(field, bad):
    assert economics(replace(label(), **{field: bad}), 1, 8)["net_return"] is None


def test_missing_component_and_no_action():
    missing = replace(BASELINE, exit_slippage_bp=None)
    result = economics(label(), 1, 8, missing)
    assert result["reason"] == "UNRESOLVED_COST_ASSUMPTION"
    assert economics(None, 0, 8, missing)["sleeve_pnl"] == 0


def test_maker_without_queue_is_strict_no_action_not_fractional_taker_pnl():
    result = economics(label(), 1, 8, maker=True)
    assert result["status"] == "NO_ACTION"
    assert result["reason"] == "FILL_UNKNOWN" and result["action"] == 0
    assert result["fill_model_utility"] is None


def test_policy_uses_assumed_cost_carry_and_edge_buffer_only():
    threshold = (16 + 5 * 8 / 24 + 1) / 10000
    assert policy_action(threshold, 8) == policy_action(-threshold, 8) == 0
    assert policy_action(threshold + 1e-9, 8) == 1
    assert policy_action(-threshold - 1e-9, 8) == -1
    assert policy_action(0.002, 8, STRESS) == 0
