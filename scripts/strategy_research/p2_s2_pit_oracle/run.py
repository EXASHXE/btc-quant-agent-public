"""Run only frozen invented fixtures, emitting an auditable source-science receipt."""

from __future__ import annotations

import argparse
import ast
import calendar
import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from itertools import permutations
from math import ceil, sqrt
from pathlib import Path
from statistics import NormalDist

import oracle

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parents[2] / (
    "evidence/v0.6/b_line/p2_s2_pit_science_r1/"
    "SYNTHETIC_MARK_FUNDING_CLOCK_ORACLE_RESULTS.json"
)


def planning(inputs: dict) -> dict:
    normal = NormalDist()
    z = normal.inv_cdf(1-inputs["alpha"]/inputs["comparisons"])
    zb = normal.inv_cdf(inputs["target_power"])
    power = []
    for sigma in inputs["sigma_block_bp"]:
        power.append({"sigma_block_bp": sigma,
                      "n_for_80pct_approx": ceil(((z+zb)*sigma/inputs["delta_bp"])**2),
                      "power_at_12_independent_weeks": 1-normal.cdf(
                          z-inputs["delta_bp"]*sqrt(inputs["independent_weeks"])/sigma)})
    minutes = [{"year": y, "month": m, "calendar_expected_minutes":
                calendar.monthrange(y, m)[1]*1440} for y, m in inputs["partitions"]]
    return {"input": inputs, "normal_known_variance_toys": power,
            "support_density": [{"filled_per_day": rate, "expected_per_fold":
                                 inputs["eligible_days_per_April_fold"]*rate}
                                for rate in inputs["filled_per_day"]],
            "calendar_partitions": minutes,
            "calendar_expected_minutes_total": sum(p["calendar_expected_minutes"] for p in minutes),
            "scope": "Not measured rates/variance/coverage; calendar count does not prove any file rows"}


def metamorphic(controls: dict) -> list[dict]:
    observations = []

    def checked(name: str, condition: bool, actual: object, expected: object):
        assert condition, (name, actual, expected)
        observations.append({"id": f"I{len(observations)+1:02}", "property": name,
                             "actual": actual, "expected": expected,
                             "status": "PASS_SYNTHETIC_ONLY"})

    v = oracle.visibility(controls["visibility"])
    later = oracle.visibility(dict(controls["visibility"], available=200000))
    checked("Later availability cannot improve eligibility",
            v["code"] == "VISIBLE_SYNTHETIC" and later["code"] == "LOOKAHEAD",
            [v["code"], later["code"]], ["VISIBLE_SYNTHETIC", "LOOKAHEAD"])
    mark = deepcopy(controls["mark"])
    before = oracle.mark_asof(mark)
    mark["observations"].append(controls["correction"])
    after = oracle.mark_asof(mark)
    checked("Future correction cannot change old asof", before == after,
            [before["prices"], after["prices"]], {"60000": "100"})
    first = deepcopy(mark["observations"][0])
    conflict = dict(first, id="malicious", price="101")
    codes = [oracle.mark_asof(dict(mark, observations=list(p)))["code"]
             for p in permutations([first, conflict])]
    checked("Same source-close contradiction fail closed in both permutations",
            set(codes) == {"CONFLICT_SOURCE_FAIL_CLOSED"}, codes, "CONFLICT_SOURCE_FAIL_CLOSED")
    a = oracle.funding(controls["funding"])
    b = oracle.funding(dict(controls["funding"], rate_bp="8"))
    checked("More adverse funding cannot improve net cashflow",
            Decimal(b["cashflow"]) < Decimal(a["cashflow"]),
            [a["cashflow"], b["cashflow"]], ["-.4", "-.8"])
    fee = oracle.funding(dict(controls["funding"], knowledge=180000,
                              owed_fee="2", terminal_clear_claim=True))
    checked("Terminal unpaid fees cannot disappear", fee["code"] == "UNPAID_TERMINAL",
            fee["code"], "UNPAID_TERMINAL")
    sparse = oracle.geometry(dict(controls["geometry"], synthetic_times=[4*oracle.HOUR]))
    checked("Unknown cadence cannot silently use an8h sparse grid",
            sparse["code"] == "METHOD_CONFLICT", sparse["code"], "METHOD_CONFLICT")
    btc = oracle.semantic({"kind": "BTC_POSITIVE", "single_asset_fraction": 1})
    checked("BTC-only cannot inherit three-asset positive", btc["code"] == "METHOD_CONFLICT",
            btc["code"], "METHOD_CONFLICT")
    hourly = oracle.geometry(dict(controls["geometry"], end=12*oracle.HOUR,
                                  synthetic_times=[i*oracle.HOUR for i in range(13)], stop_bp="250"))
    known = oracle.geometry(dict(controls["geometry"], end=12*oracle.HOUR,
                                 cadence="KNOWN_SYNTHETIC_8H", synthetic_times=[4*oracle.HOUR,
                                                                              12*oracle.HOUR]))
    checked("12h hourly stress ineligible, known8h only conditionally feasible",
            hourly["minimum_stop_bp"] == "296.000000000000" and
            known["minimum_stop_bp"] == "120.000000000000" and
            hourly["code"] == "STRESS_COST_GEOMETRY_INELIGIBLE",
            [hourly, known], "296>250,120<=200; neither proves actual schedule")
    flows = [oracle.funding(dict(controls["funding"], side=side, rate_bp=rate))["cashflow"]
             for side, rate in [(1, "4"), (-1, "4"), (1, "-4"), (-1, "-4")]]
    checked("Signed negative rates reverse payment directions",
            list(map(Decimal, flows)) == list(map(Decimal, ["-.4", ".4", ".4", "-.4"])),
            flows, ["-.4", ".4", ".4", "-.4"])
    ack_before = oracle.funding(dict(controls["funding"], knowledge=179999))
    ack_at = oracle.funding(dict(controls["funding"], knowledge=180000))
    checked("Cash is unacknowledged until true ACK equality",
            Decimal(ack_before["acknowledged_cash"]) == 0 and
            Decimal(ack_at["acknowledged_cash"]) == Decimal("-.4") and
            Decimal(ack_at["liability"]) == 0 and Decimal(ack_at["reserve"]) == 0,
            [ack_before, ack_at], "pending debit.4 -> cash-.4, owed0 at180000ms")
    outputs = [oracle.mark_asof(dict(mark, observations=list(p)))
               for p in permutations(mark["observations"])]
    checked("Legal source input permutation deterministic", all(o == outputs[0] for o in outputs),
            outputs, "same old100 snapshot, independent of list order")
    edge = [oracle.settlement_count(15000, 100000, [0]),
            oracle.settlement_count(15001, 100000, [0]),
            oracle.settlement_count(0, 45000, [60000]),
            oracle.settlement_count(0, 44999, [60000])]
    checked("Ownership +/-15s equality versus1ms outside", edge == [1, 0, 1, 0],
            edge, [1, 0, 1, 0])
    scope = oracle.semantic({"kind": "SCOPE", "claimed_real_body_access": True})
    imports = []
    for node in ast.walk(ast.parse((HERE / "oracle.py").read_text())):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module)
    checked("Synthetic oracle has no real-body/network reader",
            set(imports) == {"__future__", "decimal"} and scope["code"] == "METHOD_CONFLICT",
            {"imports": imports, "body_capability_claim": scope["code"]},
            "Only scalar stdlib Decimal imports; task tools separately record zero-body scope")
    return observations


def execute(fixtures: dict, digest: str) -> dict:
    cases = []
    for case in fixtures["cases"]:
        observed = oracle.evaluate(case)
        assert observed["code"] == case["expected_code"], (case["id"], observed)
        for key, value in case["expected_values"].items():
            assert observed[key] == value, (case["id"], key, observed[key], value)
        cases.append({**case, "observed": observed, "assertion": "PASS_SYNTHETIC_EXPECTATION"})
    invariants = metamorphic(fixtures["hand_controls"])
    return {"schema": "P2_S2_ACTUALLY_EXECUTED_SYNTHETIC_ORACLE_V1", "input_sha256": digest,
            "cases": cases, "metamorphic_invariants": invariants,
            "counts": {"cases": len(cases), "hostile_witnesses": sum(c["hostile"] for c in cases),
                       "metamorphic_invariants": len(invariants),
                       "assertions_passed": len(cases)+len(invariants)},
            "source_rights_cadence_actual_outcomes": "UNKNOWN_NOT_TESTED",
            "scientific_scope": "Invented clocks/scalar economics only; no source/reader/engine admission",
            "terminal": "P2_S2_PIT_SCIENCE_AND_DIAGNOSTIC_PREREG_DESIGNED_PENDING_CONTROLLER"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stdout", action="store_true", help="Emit synthetic JSON instead of fixed artifact")
    args = parser.parse_args()
    data = (HERE / "fixtures.json").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == (HERE / "fixtures.sha256").read_text().strip(), "frozen fixture drift"
    planning_data = (HERE / "planning_inputs.json").read_bytes()
    planning_digest = hashlib.sha256(planning_data).hexdigest()
    assert planning_digest == (HERE / "planning_inputs.sha256").read_text().strip()
    evaluated = execute(json.loads(data), digest)
    evaluated["planning"] = planning(json.loads(planning_data))
    evaluated["planning_sha256"] = planning_digest
    output = (json.dumps(evaluated, indent=2, sort_keys=True)+"\n").encode()
    if args.stdout:
        print(output.decode(), end="")
    else:
        OUTPUT.write_bytes(output)
        print(json.dumps({"output_sha256": hashlib.sha256(output).hexdigest(),
                          "counts": json.loads(output)["counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
