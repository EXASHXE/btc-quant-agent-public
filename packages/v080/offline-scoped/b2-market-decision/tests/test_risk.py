from dataclasses import replace
from decimal import Context, localcontext

import pytest
from test_strategy import SYMBOL, after, system

from quant_personal_decision_b2.fixtures import AFTER_TRIGGER, EARLY, PULLBACK
from quant_personal_decision_b2.model import DEFAULT_POLICY, HOUR, D
from quant_personal_decision_b2.risk import (
    filters,
    path_net,
    reference_vwap,
    round_grid,
)


@pytest.mark.parametrize("sign,entry,exit_price,expected", [
    (1, "100", "110", "9.695"),
    (-1, "100", "90", "9.705"),
    (1, "100", "90", "-10.295"),
])
def test_path_cash_is_hand_checkable(sign, entry, exit_price, expected):
    assert path_net(sign, D(entry), D(exit_price), D("0.0005"), D("0.2")) == D(expected)


def test_tick_and_joint_step_with_no_quantity_increase():
    spec = filters({"filters": {
        "PRICE_FILTER": {"tickSize": "0.05", "minPrice": "0.05", "maxPrice": "10000"},
        "LOT_SIZE": {"stepSize": "0.003", "minQty": "0.009", "maxQty": "100"},
        "MARKET_LOT_SIZE": {"stepSize": "0.002", "minQty": "0.004", "maxQty": "99"},
        "MIN_NOTIONAL": {"notional": "12"},
    }})
    assert spec.step == D("0.006") and spec.min_qty == D(".009") and spec.max_qty == D("99")
    assert round_grid(D("0.095"), spec.step, up=False) == D(".090")
    assert round_grid(D("100.03"), spec.tick, up=True) == D("100.05")
    assert round_grid(D("100.03"), spec.tick, up=False) == D("100.00")
    assert reference_vwap([["100", "0.10"], ["101", "0.10"]], D("0.15"))[0] == D("15.05") / D(".15")
    assert reference_vwap([["100", "0.10"]], D("0.15")) == (None, D("0.10"))


@pytest.mark.parametrize("direction,funding_charge", [("LONG", D(".00010")), ("SHORT", D(".001"))])
def test_funding_crossing_negative_rate_with_partial_paths(tmp_path, direction, funding_charge):
    feed, engine = system(tmp_path, EARLY, direction)
    engine.evaluate(SYMBOL)
    feed.funding_rate = "-0.001"
    result = after(feed, engine, variant="funding")
    plan = result["plan"]
    funding = plan["funding"]
    assert funding["modeled_crossings"] == 1 and funding["inferred_cadence_ms"] == 8 * HOUR
    assert D(funding["adverse_rate_used"]) == funding_charge
    assert D(funding["stress_cost_usdt_per_base"]) == D(funding["basis_usdt_per_base"]) * funding_charge
    sign = result["episode"]["sign"]
    fill = D(plan["entry_fill"])
    sl = D(plan["expected_stop_stress_fill"])
    hard = D(plan["hard_stop"])
    assert sign * sl < sign * hard
    fee, carry = D(plan["fee_rate_each_side"]), D(funding["stress_cost_usdt_per_base"])
    total_stop = -path_net(sign, fill, sl, fee, carry)
    assert total_stop == D(plan["unit_stop_loss_usdt"])
    tp1 = plan["targets"][0]
    p1 = path_net(sign, fill, D(tp1["exit_fill"]), fee, carry)
    assert p1 == D(tp1["net_usdt_per_base"])
    partial = plan["conditional_paths"][1]
    assert partial["name"] == "TP1_THEN_STOP"
    assert D(partial["net_usdt_per_base"]) == D(".5") * (p1 - total_stop)
    with localcontext(Context(prec=40)):
        assert D(partial["net_r"]) == D(partial["net_usdt_per_base"]) / total_stop
    assert plan["statistical_expected_value"] == "UNKNOWN"


def test_missing_reference_liquidity_blocks_eligibility(tmp_path):
    source, engine = system(tmp_path)
    engine.evaluate(SYMBOL)
    source.reference_size = "0.01"
    card = after(source, engine)
    assert card["market_status"] == "WATCH"
    assert "REFERENCE_DEPTH_INSUFFICIENT" in card["reasons"]
    assert not card["plan"]["reference_depth_sufficient"]


def test_reference_min_notional_never_increases_size(tmp_path):
    policy = replace(DEFAULT_POLICY, reference_base=D(".0031"))
    source, engine = system(tmp_path, policy=policy)
    engine.evaluate(SYMBOL)
    card = after(source, engine)
    assert card["market_status"] == "WATCH"
    assert "REFERENCE_INSTRUMENT_MINIMUM" in card["reasons"]
    assert D(card["plan"]["reference_rounded_base"]) == D(".003")


def test_oi_gap_is_not_reported_as_regular_participation(tmp_path):
    source, engine = system(tmp_path, PULLBACK)
    engine.evaluate(SYMBOL)
    source.scan(AFTER_TRIGGER + 5000, "oi_gap")
    card = engine.evaluate(SYMBOL)
    assert card["market_status"] == "EXECUTABLE"
    assert card["plan"]["oi_omitted_periods"]
    assert card["plan"]["oi_participation"] == "UNKNOWN_GAP_OR_WARMUP"
    assert card["plan"]["oi_period_change_fraction"] is None


def test_spread_reprice_retains_nominal_targets_and_increases_stressed_risk(tmp_path):
    source, engine = system(tmp_path)
    engine.evaluate(SYMBOL)
    start = after(source, engine)
    wider = after(source, engine, 5, "spread", start["episode_id"])
    assert wider["market_status"] == "WATCH"
    assert wider["first_targets"] == start["first_targets"]
    assert D(wider["plan"]["unit_stop_loss_usdt"]) > D(start["plan"]["unit_stop_loss_usdt"])
    assert D(wider["plan"]["targets"][0]["net_r"]) < D(start["plan"]["targets"][0]["net_r"])
