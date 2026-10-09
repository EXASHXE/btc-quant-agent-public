"""Evaluate frozen invented inputs and hostile arithmetic mutants, offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from decimal import Decimal as D
from pathlib import Path

from algebra import (
    claim_valid,
    effective_n,
    eligible_settlements,
    funding_cashflow,
    funding_knowledge,
    geometry,
    mean_power,
    nominal_payoff,
    proportion_n,
    two_price_payoff,
)

HERE = Path(__file__).resolve().parent


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def mutation_checks() -> list[dict]:
    records = []

    def check(name, ordinary, mutant, predicate, control):
        assert predicate(ordinary), (name, "ordinary expression failed", ordinary)
        caught = False
        try:
            assert predicate(mutant)
        except AssertionError:
            caught = True
        assert caught, (name, "mutant escaped", mutant)
        records.append({"id": f"M{len(records)+1:02}", "property": name,
                        "handcrafted_control": control, "ordinary_observed": str(ordinary),
                        "mutant_observed": str(mutant), "mutant_rejected": caught,
                        "status": "PASS_SYNTHETIC_ALGEBRA_ONLY"})

    def net(**updates):
        p = {"market_move_bp": D(100), "side": 1, "stop_bp": D(200), "fee": D(6),
             "spread": D(2), "slip": D(3), "funding_bp": D(4), "events": 1}
        p.update(updates)
        return D(nominal_payoff(**p)["net_bp"])

    base = net()  # 100-22-4 = 74bp
    check("fee_up_cannot_improve", net(fee=D(7)), base+2, lambda x: x < base, "72 < 74")
    check("slippage_up_cannot_improve", net(slip=D(4)), base+2,
          lambda x: x < base, "72 < 74")
    check("more_adverse_funding_cannot_improve", net(events=2), base+4,
          lambda x: x < base, "70 < 74")
    check("outside_window_not_charged", len(eligible_settlements(0, 1000, [16001])), 1,
          lambda x: x == 0, "16,001ms is outside hold +15,000ms")
    check("window_equality_included", len(eligible_settlements(0, 1000, [16000])), 0,
          lambda x: x == 1, "16,000ms window left edge equals exit1,000ms")
    check("upfront_direction_sign", net(side=-1), net(side=1),
          lambda x: x == D(-126), "SHORT raw move+100: -100-22-4=-126")
    check("signed_funding_reversal", funding_cashflow(-1, D(1000), D(4)), D("-.4"),
          lambda x: x == D(".4"), "positive actual rate credits SHORT; proxies never credit")
    check("identical_input_deterministic", (net(), net()), (net(), net()+1),
          lambda x: x[0] == x[1], "two exact evaluations are equal")
    check("cover_110pct_expected_model", D("1.1")*D(".4"), D(".9")*D(".4"),
          lambda x: x >= D(".4"), ".44 covers .40 at constant invented Mark")
    check("adverse_gap_not_beneficial", net(market_move_bp=D(-230)), net(market_move_bp=D(-200)),
          lambda x: x < net(market_move_bp=D(-200)), "-256 < -226")
    capped = nominal_payoff(D(500), 1, D(200), D(6), D(2), D(3), D(4), 1,
                            cap_target=True)
    check("target_cap", D(capped["gross_bp"]), D(500), lambda x: x == D(400),
          "2R=400 even when invented favorable move=500")
    check("constant_notional_exact_cost", D(1000)*D(22)/D(10000), D("4.4"),
          lambda x: x == D("2.2"), "2.2 USDT on 1000; no leverage multiplier")
    check("missing_funding_proof_unknown", funding_knowledge(False, None), "ZERO",
          lambda x: x == "UNKNOWN", "no measured event proof is not zero events")
    check("12h_hourly_stress_ineligible", geometry(D(250), 13)["eligible"], True,
          lambda x: x is False, "44+13*8=148; 2C=296 >250")
    check("loss_not_clipped_at_one_R", net(market_move_bp=D(-300)), D(-200),
          lambda x: x < D(-200), "-326bp includes gap beyond200 stop")
    check("cover_not_guarantee_under_mark_shock", D(".44") >= D(".48"), True,
          lambda x: x is False, "1.20 mark shock exceeds1.10 buffer")
    return records


def evaluate(inputs: dict, digest: str) -> dict:
    cases = []
    for row in inputs["payoff_cases"]:
        times = eligible_settlements(row["start_ms"], row["end_ms"],
                                     row["synthetic_settlements_ms"])
        nominal = nominal_payoff(
            D(row["market_move_bp"]), row["side"], D(row["stop_bp"]),
            D(row["fee_bp"]), D(row["spread_bp"]), D(row["slip_bp"]),
            D(row["funding_rate_bp"]), len(times), D(row["notional_usdt"]),
            D(row["tick_bound_bp"]), D(row["funding_mark_multiplier"]), row["cap_target"],
        )
        # Independently specified constant-notional identity, every physical result.
        independent_gross = D(row["side"])*D(row["market_move_bp"])
        if row["cap_target"]:
            independent_gross = min(independent_gross, 2*D(row["stop_bp"]))
        independent_cost = 2*(D(row["fee_bp"])+D(row["spread_bp"])+D(row["slip_bp"]))
        independent_cost += D(row["tick_bound_bp"])
        independent_cost += len(times)*D(row["funding_rate_bp"])*D(row["funding_mark_multiplier"])
        assert D(nominal["net_bp"]) == independent_gross-independent_cost
        cases.append({"id": row["id"], "input": row, "eligible_synthetic_times": times,
                      "event_count": len(times), "nominal_observed": nominal,
                      "two_price_observed": two_price_payoff(row, len(times)),
                      "fixed_stop_stress_geometry": geometry(D(row["stop_bp"]), len(times),
                                                             D(row["tick_bound_bp"])),
                      "independent_identity_checked": True})
    hostile = []
    for case in inputs["falsifiers"]:
        valid = claim_valid(case["kind"], case["valid"])
        bad = claim_valid(case["kind"], case["hostile"])
        assert valid and not bad, case["id"]
        hostile.append({**case, "valid_control_accepted": valid, "hostile_claim_accepted": bad,
                        "status": "FALSIFIER_DETECTS_SYNTHETIC_CONTRACT_VIOLATION",
                        "enforcement_scope": "AUDIT_PREDICATE_NOT_ENGINE_ENFORCEMENT"})
    power = [{"input": p, "observed": mean_power(**{k: v for k, v in p.items() if k != "id"})}
             for p in inputs["power_cases"]]
    proportions = [{"input": p, "observed_n_approx": proportion_n(
        **{k: v for k, v in p.items() if k != "id"})} for p in inputs["proportion_cases"]]
    dependence = [{"input": p, "effective_n_approx": effective_n(p["n"], p["rho"])}
                  for p in inputs["dependence_cases"]]
    mutations = mutation_checks()
    return {"schema": "POSTP1_EXECUTED_SYNTHETIC_ALGEBRA_V1", "input_sha256": digest,
            "payoff_cases": cases, "power_cases": power, "proportion_cases": proportions,
            "dependence_cases": dependence, "mutation_checks": mutations,
            "mechanism_falsifiers": hostile,
            "observed_counts": {"payoff_cases": len(cases), "mean_power_cases": len(power),
                                "proportion_power_cases": len(proportions),
                                "dependence_cases": len(dependence),
                                "mutants_rejected": sum(r["mutant_rejected"] for r in mutations),
                                "mechanism_falsifiers_rejected": sum(
                                    not r["hostile_claim_accepted"] for r in hostile)},
            "economic_claim": "STRUCTURAL_ALGEBRA_ONLY_NO_EMPIRICAL_EXPECTANCY",
            "funding_counts": "EXPLICIT_SYNTHETIC_SCHEDULES_NOT_EXCHANGE_EVENT_BOUNDS"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = (HERE / "scenario_inputs.json").read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == (HERE / "scenario_inputs.sha256").read_text().strip(), "input drift"
    result = evaluate(json.loads(data), digest)
    output = canonical(result)
    args.output.write_bytes(output)
    print(json.dumps({"input_sha256": digest, "output_sha256": hashlib.sha256(output).hexdigest(),
                      "counts": result["observed_counts"]}, sort_keys=True))


if __name__ == "__main__":
    main()
