"""Fixed rubric evaluation; priorities are conditional designs, never returns."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rank(rows: list[dict], rubric: dict, cost: str, state: str,
         omit: str | None = None) -> list[dict]:
    weights = {k: v for k, v in rubric["weights"].items() if k != omit}
    observations = []
    for row in rows:
        scores = dict(row["score_inputs"])
        scores["economics"] = rubric["economics_scores"][str(row["horizon_hours"])][cost]
        if state == "MULTIASSET_INCOMPLETE" and row["kind"] == "ORIGINAL_EIGHT_UNCHANGED":
            scores["source"] = 0  # Cannot quietly replace the frozen universe.
        total = sum(weights[k]*scores[k] for k in weights)
        value = 100*total/(4*sum(weights.values()))
        observations.append({"id": row["id"], "scores": scores, "weighted_score": value,
                             "source_status": "SOURCE_BLOCKED_PENDING_P2",
                             "eligible_for_execution": False})
    observations.sort(key=lambda x: (-x["weighted_score"], x["id"]))
    for index, row in enumerate(observations):
        row["display_index"] = index+1
        row["tied_rank"] = 1+sum(x["weighted_score"] > row["weighted_score"]
                                 for x in observations)
    return observations


def evaluate(rubric: dict, inputs: dict) -> dict:
    base = []
    sensitivity = []
    for state in rubric["source_states"]:
        for cost in rubric["cost_assumptions"]:
            ranking = rank(inputs["rows"], rubric, cost, state)
            top = {r["id"] for r in ranking[:4]}
            base.append({"source_state": state, "cost": cost, "ranked": ranking,
                         "top4_conditional_only": sorted(top)})
            for dimension in rubric["weights"]:
                altered = rank(inputs["rows"], rubric, cost, state, dimension)
                other_top = {r["id"] for r in altered[:4]}
                sensitivity.append({"source_state": state, "cost": cost, "omitted": dimension,
                                    "ranked": altered, "top4_members_changed": top != other_top,
                                    "entering_top4": sorted(other_top-top),
                                    "leaving_top4": sorted(top-other_top),
                                    "interpretation": "Rubric-choice instability, not return evidence"})
    return {"schema": "POSTP1_TEST_PRIORITY_SENSITIVITY_V1", "rubric": rubric,
            "score_inputs": inputs, "base_rankings": base, "leave_one_dimension_out": sensitivity,
            "actual_source_admission_count": 0, "actual_empirical_rank": None,
            "ranking_instability_count": sum(s["top4_members_changed"] for s in sensitivity),
            "observed_computations": {"base_rankings": len(base), "sensitivity_rankings": len(sensitivity),
                                      "base_rows": len(base)*len(inputs["rows"]),
                                      "sensitivity_rows": len(sensitivity)*len(inputs["rows"])},
            "terminal": "R4_SCIENCE_PRIORITIES_DESIGNED_PENDING_CONTROLLER_AND_P2",
            "readiness": "DESIGN_COMPLETE_ALL_HYPOTHESES_SOURCE_BLOCKED_NOT_SCIENCE_EXECUTION_READY",
            "priority_scope": "Mechanistic future research priorities; original eight campaign budget unchanged",
            "not_preregistration": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = (HERE / "priority_inputs.json").read_bytes()
    expected = (HERE / "priority_inputs.sha256").read_text().strip()
    assert hashlib.sha256(data).hexdigest() == expected
    rubric_data = (HERE / "priority_rubric.json").read_bytes()
    result = evaluate(json.loads(rubric_data), json.loads(data))
    result["input_sha256"] = expected
    result["rubric_sha256"] = hashlib.sha256(rubric_data).hexdigest()
    output = (json.dumps(result, sort_keys=True, indent=2)+"\n").encode()
    args.output.write_bytes(output)
    print(json.dumps({"output_sha256": hashlib.sha256(output).hexdigest(),
                      "observed_computations": result["observed_computations"],
                      "top4_instabilities": result["ranking_instability_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
