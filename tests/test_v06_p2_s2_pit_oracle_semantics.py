"""Independent controls for invented-clock oracle, no actual source acceptance."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from decimal import Context, localcontext
from decimal import Decimal as D
from itertools import permutations
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "scripts/strategy_research/p2_s2_pit_oracle"
SPEC = importlib.util.spec_from_file_location("p2_s2_synthetic_oracle", HERE / "oracle.py")
assert SPEC and SPEC.loader
ORACLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ORACLE)
FIXTURES = json.loads((HERE / "fixtures.json").read_text())
CONTROLS = FIXTURES["hand_controls"]


@pytest.mark.parametrize("case", FIXTURES["cases"], ids=lambda c: c["id"])
def test_each_frozen_case_against_predeclared_expected(case):
    out = ORACLE.evaluate(case)
    assert out["code"] == case["expected_code"]
    for key, expected in case["expected_values"].items():
        assert out[key] == expected


def test_ack_floor_equality_and_signed_four_way_hand_control():
    for side, rate, expected in [(1, "4", "-.4"), (-1, "4", ".4"),
                                 (1, "-4", ".4"), (-1, "-4", "-.4")]:
        pending = ORACLE.funding(dict(CONTROLS["funding"], side=side, rate_bp=rate,
                                       knowledge=179999))
        paid = ORACLE.funding(dict(CONTROLS["funding"], side=side, rate_bp=rate,
                                    knowledge=180000))
        assert D(pending["cashflow"]) == D(expected)
        assert D(pending["acknowledged_cash"]) == 0
        assert D(paid["acknowledged_cash"]) == D(expected)
        assert D(paid["liability"]) == 0
        assert D(paid["reserve"]) == 0
        if D(expected) > 0:
            assert D(pending["reserve"]) == 0  # Final known credit is no longer a possible debit.


def test_derived_feature_proof_max_and_first_hour_clock():
    # H=0: signal at60s, earliest execution120s. Entry-minute full proof240s.
    assert ORACLE.visibility({"event": 60000, "observed": 60000, "available": 60000,
                              "proof_floor": 180000, "decision": 120000})["code"] == "LOOKAHEAD"
    assert ORACLE.visibility({"event": 120000, "observed": 180000, "available": 180000,
                              "proof_floor": 240000, "decision": 240000})["code"] == "LOOKAHEAD"
    assert ORACLE.visibility({"event": 120000, "observed": 240000, "available": 240000,
                              "proof_floor": 240000, "decision": 240000})[
                                  "code"] == "VISIBLE_SYNTHETIC"


@pytest.mark.parametrize("order", list(permutations([0, 1])))
def test_conflict_always_rejected_and_future_revision_preserves_past(order):
    m = deepcopy(CONTROLS["mark"])
    base = m["observations"][0]
    conflicting = [base, dict(base, id="evil", price="101")]
    m["observations"] = [conflicting[i] for i in order]
    assert ORACLE.mark_asof(m)["code"] == "CONFLICT_SOURCE_FAIL_CLOSED"
    m["observations"] = [[base, CONTROLS["correction"]][i] for i in order]
    assert ORACLE.mark_asof(m)["prices"] == {"60000": "100"}
    assert ORACLE.mark_asof(dict(m, decision=300000))["prices"] == {"60000": "101"}


def test_funding_correction_clock_cannot_backdate_entry():
    x = dict(CONTROLS["funding"], purpose="FEATURE", rate_corrected=240000,
             rate_available=120000, rate_observed=120000, decision=180000)
    assert ORACLE.funding(x)["code"] == "LOOKAHEAD"
    assert ORACLE.funding(dict(x, rate_corrected=None))["code"] == "SOURCE_UNPROVEN"
    assert ORACLE.funding(dict(x, rate_available=240000))["code"] == "LOOKAHEAD"


def test_funding_proof_floor_and_boundary_intersection():
    assert ORACLE.funding_floor(0) == 120000
    assert ORACLE.funding_floor(45000) == 180000  # +15s touches next minute boundary
    assert ORACLE.settlement_count(15000, 100000, [0]) == 1
    assert ORACLE.settlement_count(15001, 100000, [0]) == 0
    assert ORACLE.settlement_count(0, 45000, [60000]) == 1
    assert ORACLE.settlement_count(0, 44999, [60000]) == 0
    with pytest.raises(ValueError):
        ORACLE.settlement_count(0, 1000, [0, 0])


def test_extra_ack_delay_is_not_ignored():
    assert ORACLE.funding(dict(CONTROLS["funding"], extra_delay_until=240000))[
        "code"] == "LOOKAHEAD"


def test_reserve_shortfall_and_fee_terminal_not_cleared():
    x = ORACLE.funding(dict(CONTROLS["funding"], mark_multiplier="1.2"))
    assert D(x["reserve"]) == D(".44")
    assert D(x["liability"]) == D(".48")
    assert D(x["shortfall"]) == D(".04")
    assert ORACLE.funding(dict(CONTROLS["funding"], knowledge=180000,
                               owed_fee="2", terminal_clear_claim=True))["code"] == "UNPAID_TERMINAL"
    assert ORACLE.funding(dict(CONTROLS["funding"], side=-1, terminal_clear_claim=True))[
        "code"] == "UNPAID_TERMINAL"  # UnACKed gain is still unresolved.


def test_geometry_13_vs_2_events_is_not_economic_return():
    x = dict(CONTROLS["geometry"], end=12*3600000,
             synthetic_times=[i*3600000 for i in range(13)], stop_bp="250")
    assert ORACLE.geometry(x)["minimum_stop_bp"] == "296.000000000000"
    assert ORACLE.geometry(dict(x, cadence="KNOWN_SYNTHETIC_8H",
                                synthetic_times=[4*3600000, 12*3600000]))[
                                    "minimum_stop_bp"] == "120.000000000000"
    assert ORACLE.geometry(dict(x, synthetic_times=[4*3600000]))["code"] == "METHOD_CONFLICT"


def test_global_decimal_context_cannot_change_projection():
    x = ORACLE.funding(CONTROLS["funding"])
    with localcontext(Context(prec=3)):
        assert ORACLE.funding(CONTROLS["funding"]) == x
        assert ORACLE.geometry(CONTROLS["geometry"])["minimum_stop_bp"] == "168.000000000000"


def test_real_cli_has_no_data_root_input_and_stdout_is_synthetic():
    completed = subprocess.run([sys.executable, str(HERE / "run.py"), "--stdout"],
                               check=True, capture_output=True, text=True)
    out = json.loads(completed.stdout)
    assert out["counts"] == {"cases": 52, "hostile_witnesses": 39,
                              "metamorphic_invariants": 13, "assertions_passed": 65}
    assert out["planning"]["calendar_expected_minutes_total"] == 263520
    assert [p["n_for_80pct_approx"] for p in out["planning"]["normal_known_variance_toys"]] == [
        13, 52, 205]
    rejected = subprocess.run([sys.executable, str(HERE / "run.py"), "--data-root", "/invented"],
                              capture_output=True, text=True, check=False)
    assert rejected.returncode == 2  # argparse rejects, no owner-root callable exists.


def test_outcome_codes_do_not_grant_source_prereg_or_alpha():
    for case in FIXTURES["cases"]:
        code = ORACLE.evaluate(case)["code"]
        assert code not in {"SOURCE_ADMITTED", "PREREG_EFFECTIVE", "ALPHA_FOUND", "P4_AUTHORIZED"}


@pytest.mark.parametrize("update", [{"notional": "-1"}, {"mark_multiplier": "0"},
                                    {"owed_fee": "-1"}])
def test_invalid_monetary_domain_fails_closed(update):
    with pytest.raises(ValueError):
        ORACLE.funding(dict(CONTROLS["funding"], **update))


def test_mark_symbol_and_nonpositive_price_cannot_be_substituted():
    for update in [{"symbol": "ETHUSDT"}, {"price": "0"}]:
        x = deepcopy(CONTROLS["mark"])
        x["observations"][0].update(update)
        assert ORACLE.mark_asof(x)["code"] == "SOURCE_UNPROVEN"


def test_invalid_adverse_tick_bound_not_used_to_improve_geometry():
    with pytest.raises(ValueError):
        ORACLE.geometry(dict(CONTROLS["geometry"], tick_bound="-100"))
