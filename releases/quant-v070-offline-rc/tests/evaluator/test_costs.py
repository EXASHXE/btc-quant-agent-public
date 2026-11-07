from __future__ import annotations

import copy
import math

import pytest
from program_c.costs import ExecutionEvidence, cost_projection, hypothetical_executable_r
from program_c.integrity import digest
from program_c.protocol import COST_CASES
from program_c.validation import default_costs


def test_transparent_units_and_cadence():
    costs = default_costs(1000)
    costs["impact_bps_at_reference"] = 0
    r = cost_projection(100, 130, 24, costs, "BASE")
    # fees+slippage=0.23, spread=0.052, funding=0.039 USDT/base.
    assert r["total_per_base"] == pytest.approx(0.321)
    assert r["charged_funding_cadences"] == 1
    assert sum(r["components_per_base"].values()) == r["total_per_base"]
    assert r["executable_status"] == "EXE_COST_UNVERIFIED"


@pytest.mark.parametrize("hours", [4, 24, 25, 48, 120])
def test_holding_cadence_never_grants_funding_credit(hours):
    r = cost_projection(100, 130, hours, default_costs(1000), "BASE")
    assert r["charged_funding_cadences"] == math.ceil(hours / 24)
    assert all(x >= 0 for x in r["components_per_base"].values())


@pytest.mark.parametrize("case", list(COST_CASES))
def test_predeclared_stress_is_adverse(case):
    costs = default_costs(1000)
    base = cost_projection(100, 130, 120, costs, "BASE")
    stress = cost_projection(100, 130, 120, costs, case)
    assert stress["total_per_base"] >= base["total_per_base"]


def test_size_impact_and_capacity_are_explicit():
    costs = default_costs(1000)
    small = cost_projection(100, 130, 24, costs, "BASE")
    costs["assumed_notional_quote"] *= 2
    costs["available_capacity_quote"] = 1
    large = cost_projection(100, 130, 24, costs, "BASE")
    assert large["components_per_base"]["impact_size"] == 2 * small["components_per_base"]["impact_size"]
    assert large["capacity_status"] == "INSUFFICIENT"


def test_maker_taker_each_side_separate():
    costs = default_costs(1000)
    costs.update(maker_fee_each_side_bps=1, taker_fee_each_side_bps=5, entry_fee_mode="MAKER")
    r = cost_projection(100, 130, 24, costs, "BASE")
    assert r["components_per_base"]["entry_fee"] == pytest.approx(0.01)
    assert r["components_per_base"]["exit_fee"] == pytest.approx(0.065)


def test_unknown_cost_is_unknown():
    r = cost_projection(100, 130, 24, None, "BASE")
    assert r["total_per_base"] is None
    assert r["executable_status"] == "EXE_COST_UNVERIFIED"


def qa_execution_payload():
    # Fabricated external verifier simulation, not native qualification.
    return {"source": "NATIVE_QUALIFIED", "symbol": "BTCUSDT", "venue": "FABRICATED_QA",
            "instrument_type": "LINEAR_QUOTE_BASE", "price_unit": "USDT_PER_BASE", "multiplier": 1.0, "tick": 0.01,
            "entry_ms": 1000, "exit_ms": 2000, "entry_bid": 99.0, "entry_ask": 100.0,
            "exit_bid": 130.0, "exit_ask": 131.0, "entry_capacity_quote": 1000.0,
            "exit_capacity_quote": 1000.0, "notional_quote": 100.0, "available_ms": 2010, "durable_ms": 2020,
            "fees_funding_impact_per_base": 1.0, "independently_verified": True}


def test_hypothetical_quote_branch_requires_external_pin():
    p = qa_execution_payload()
    root = digest(p)
    evidence = ExecutionEvidence(root, p)
    assert hypothetical_executable_r(evidence, set(), "LONG", 10, 3000) is None
    assert hypothetical_executable_r(evidence, {root}, "LONG", 10, 3000) == 2.9
    assert hypothetical_executable_r(evidence, {root}, "SHORT", 10, 3000) == -3.3


@pytest.mark.parametrize("field,value", [("exit_capacity_quote", 1), ("durable_ms", 4000),
                                         ("instrument_type", "INVERSE"), ("independently_verified", False),
                                         ("entry_bid", 101), ("fees_funding_impact_per_base", -1)])
def test_incomplete_execution_evidence_blocks(field, value):
    p = copy.deepcopy(qa_execution_payload())
    p[field] = value
    root = digest(p)
    assert hypothetical_executable_r(ExecutionEvidence(root, p), {root}, "LONG", 10, 3000) is None
