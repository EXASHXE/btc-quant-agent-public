"""Independent arithmetic controls, not backtest or engine acceptance tests."""

from __future__ import annotations

import hashlib
import json
import sys
from decimal import Context, localcontext
from decimal import Decimal as D
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts/strategy_research/postp1_science_algebra"
sys.path.insert(0, str(SCRIPTS))
import algebra
import run as experiment

INPUTS = json.loads((SCRIPTS / "scenario_inputs.json").read_text())


def test_frozen_inputs_identity():
    data = (SCRIPTS / "scenario_inputs.json").read_bytes()
    assert hashlib.sha256(data).hexdigest() == (SCRIPTS / "scenario_inputs.sha256").read_text().strip()
    assert len(INPUTS["payoff_cases"]) >= 64
    assert len({r["id"] for r in INPUTS["payoff_cases"]}) == len(INPUTS["payoff_cases"])


@pytest.mark.parametrize("row", INPUTS["payoff_cases"], ids=lambda r: r["id"])
def test_each_physical_payoff_against_independent_identity(row):
    # Explicit interval intersection and a direct bridge independent of function calls.
    n = sum(row["start_ms"]-15000 <= s <= row["end_ms"]+15000
            for s in row["synthetic_settlements_ms"])
    gross = row["side"] * D(row["market_move_bp"])
    if row["cap_target"]:
        gross = min(gross, 2*D(row["stop_bp"]))
    cost = 2*(D(row["fee_bp"])+D(row["spread_bp"])+D(row["slip_bp"]))
    cost += D(row["tick_bound_bp"])
    cost += n*D(row["funding_rate_bp"])*D(row["funding_mark_multiplier"])
    observed = algebra.nominal_payoff(
        D(row["market_move_bp"]), row["side"], D(row["stop_bp"]), D(row["fee_bp"]),
        D(row["spread_bp"]), D(row["slip_bp"]), D(row["funding_rate_bp"]), n,
        D(row["notional_usdt"]), D(row["tick_bound_bp"]),
        D(row["funding_mark_multiplier"]), row["cap_target"],
    )
    assert D(observed["net_bp"]) == gross-cost
    assert D(observed["net_usdt"]) == (gross-cost)/10  # N=1000, not funded equity
    exact = algebra.two_price_payoff(row, n)
    bridge = (D(exact["raw_gross_usdt"])-D(exact["embedded_drag_usdt"])
              -D(exact["fees_usdt"])-D(exact["funding_usdt"]))
    assert abs(D(exact["net_usdt"])-bridge) <= D("0.000000000002")
    assert D(exact["embedded_drag_usdt"]) >= 0


@pytest.mark.parametrize("case", INPUTS["falsifiers"], ids=lambda r: r["id"])
def test_handcrafted_falsifier_rejects_wrong_claim(case):
    assert algebra.claim_valid(case["kind"], case["valid"])
    assert not algebra.claim_valid(case["kind"], case["hostile"])


@pytest.mark.parametrize("mutant", experiment.mutation_checks(), ids=lambda r: r["id"])
def test_live_mutant_detection(mutant):
    assert mutant["mutant_rejected"]
    assert mutant["ordinary_observed"] != mutant["mutant_observed"]


def test_hand_calculated_cash_bps_and_R():
    x = algebra.nominal_payoff(D(200), 1, D(100), D(6), D(2), D(3), D(4), 2)
    assert D(x["net_bp"]) == 170
    assert D(x["net_usdt"]) == 17
    assert D(x["net_R"]) == D("1.7")
    assert D(x["ideal_binary_p_BE"]) == D("0.433333333333")


def test_actual_notional_fee_differs_from_nominal_bridge():
    row = dict(INPUTS["payoff_cases"][0], market_move_bp="100", fee_bp="6",
               spread_bp="0", slip_bp="0", price_tick="0.01")
    x = algebra.two_price_payoff(row, 0)
    assert D(x["fees_usdt"]) == D("1.206")  # entry1000 + exit1010, times.0006
    assert D(x["net_usdt"]) == D("8.794")


@pytest.mark.parametrize("side", [1, -1])
def test_handcrafted_exact_half_tick_rounds_adversely(side):
    # Frozen scenario labels mentioning half ticks are not themselves proof of a tie.
    row = dict(INPUTS["payoff_cases"][0], entry_price="10.005", price_tick="0.01",
               market_move_bp="0", fee_bp="0", spread_bp="0", slip_bp="0", side=side)
    x = algebra.two_price_payoff(row, 0)
    entry, exit_ = ("10.01", "10.00") if side == 1 else ("10.00", "10.01")
    assert D(x["effective_entry"]) == D(entry)
    assert D(x["effective_exit"]) == D(exit_)
    assert D(x["net_usdt"]) < 0


def test_endpoint_window_ties_and_proof_floor():
    assert algebra.eligible_settlements(15000, 100000, [0]) == [0]
    assert algebra.eligible_settlements(15001, 100000, [0]) == []
    assert algebra.eligible_settlements(0, 45000, [60000]) == [60000]
    assert algebra.eligible_settlements(0, 44999, [60000]) == []
    assert algebra.funding_proof_floor(0) == 120000
    assert algebra.funding_proof_floor(0, 180000) == 180000
    with pytest.raises(ValueError):
        algebra.eligible_settlements(0, 1, [0, 0])


def test_geometry_equalities_not_retuned():
    assert algebra.geometry(D(88), 0)["eligible"]
    assert not algebra.geometry(D("87.999999999999"), 0)["eligible"]
    assert algebra.geometry(D(168), 5)["eligible"]
    assert not algebra.geometry(D(250), 13)["eligible"]
    assert not algebra.geometry(D("250.000000000001"), 0)["eligible"]


def test_decimal_context_cannot_change_algebra():
    row = INPUTS["payoff_cases"][1]
    a = algebra.two_price_payoff(row, 1)
    with localcontext(Context(prec=4)):
        assert algebra.two_price_payoff(row, 1) == a
        assert algebra.nominal_payoff(D(200), 1, D(200), D(6), D(2), D(3), D(4), 1)[
            "net_usdt"] == "17.400000000000"


@pytest.mark.parametrize("p", INPUTS["power_cases"], ids=lambda p: p["id"])
def test_power_more_information_more_power(p):
    args = {k: v for k, v in p.items() if k != "id"}
    x = algebra.mean_power(**args)
    y = algebra.mean_power(**dict(args, n=args["n"]*2))
    assert 0 < x["power_approx"] < 1
    assert y["power_approx"] > x["power_approx"]
    assert y["MDE_at_80pct_bp"] < x["MDE_at_80pct_bp"]


def test_independent_power_controls_and_multiplicity():
    assert algebra.mean_power(5, 5, 16, 1, 12)["n_for_80pct_approx"] == 13
    assert algebra.mean_power(10, 5, 16, 1, 12)["n_for_80pct_approx"] == 52
    assert algebra.mean_power(20, 5, 16, 1, 12)["n_for_80pct_approx"] == 205
    assert algebra.proportion_n(.4, .5, 16) > algebra.proportion_n(.4, .5, 1)
    assert algebra.proportion_n(.4, .45, 16) > algebra.proportion_n(.4, .5, 16)
    assert algebra.effective_n(12, 0) == 12
    assert 4 < algebra.effective_n(12, .5) < 5


@pytest.mark.parametrize("args", [(0, 5, 16, 1, 12), (5, 0, 16, 1, 12),
                                 (5, 5, 0, 1, 12), (5, 5, 16, 3, 12),
                                 (5, 5, 16, 1, 0)])
def test_invalid_power_inputs_fail_closed(args):
    with pytest.raises(ValueError):
        algebra.mean_power(*args)


def test_invalid_probability_and_dependence_inputs():
    for p0, p1 in [(0, .5), (.4, 1), (.4, .4)]:
        with pytest.raises(ValueError):
            algebra.proportion_n(p0, p1, 16)
    for n, rho in [(0, .5), (12, 1), (12, -.1)]:
        with pytest.raises(ValueError):
            algebra.effective_n(n, rho)
