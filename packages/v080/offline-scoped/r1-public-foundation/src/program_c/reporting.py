"""Deterministic files and a plain scientific report, confined to Program C."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .engine import LedgerRow, ledger
from .integrity import sha, write_json
from .protocol import FLAGS
from .statistics import power_plan, summarize


def scientific_report(summary: dict, rows: list[LedgerRow]) -> str:
    d = summary["denominators"]
    text = [
        "# Program C offline scientific report", "",
        "Scientific decision: **INSUFFICIENT_SUPPORT**.", "",
        "METHOD_IMPLEMENTED_SYNTHETICALLY_TESTED; EMPIRICAL_SUPPORT_INSUFFICIENT.", "",
        f"Source: {summary['source_class']}. Real market observations: **0**; native economic effective samples: **0**.", "",
        f"Candidates: {d['all_candidate_trigger_decisions']}; eligible episodes: {d['eligible_setup_episodes']}; "
        f"NO_SETUP decisions: {d['NO_SETUP_decisions']}; actually actionable: {d['actually_actionable_at_review']}.", "",
        f"Synthetic QA clusters: {d['independent_clusters_QA']}; native independent clusters/weeks: 0/0. "
        f"Unknown path fraction: {summary['unknown_path_fraction']}; censored/short-followup fraction: {summary['censored_fraction']}.", "",
        "| Episode | Planned geometric R | B projected after-cost R | Independent outcome | Executable R | Realized R |",
        "| --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in rows:
        if row.target_geometry == "FROZEN" and row.cost_case == "BASE" and row.delay_ms == 0:
            b = "UNKNOWN" if row.producer_projected_after_cost_R is None else f"{row.producer_projected_after_cost_R:.6f}"
            text.append(f"| {row.episode_id[:12]} | {row.planned_R:.6f} | {b} | {row.outcome} | UNKNOWN | UNKNOWN |")
    text += ["", "B's projected after-cost R is **EX_ANTE_GEOMETRY_NOT_OBSERVED_RETURN**. "
             "Its producer outcome is retained in the ledger, never promoted to independent price-path proof.", "",
             "All path payoffs are conditional synthetic models under a hypothetical entry premise. "
             "An OHLC touch never establishes a fill. Missing, ambiguous, censored and non-entry paths have unknown returns. "
             "Uncapped gaps have no finite lower execution bound.", "",
             "C cost projections use the original buffered price-risk denominator. B's separately reported projection "
             "uses risk plus its projected cost in the denominator. Those quantities are not interchangeable.", "",
             "Matched random-direction controls use the same path, entry premise, barrier distances, costs and coverage. "
             "Fixed-seed timing controls retain incomplete outcomes; unavailable control pools remain UNKNOWN. "
             "Scenario/control alternatives contribute no additional independent episodes.", "",
             "Source FALSE; Shadow FALSE; Economic FALSE; Account UNKNOWN/VETO. S2 and S3 remain RESEARCH_ONLY_DISABLED. "
             "No alpha, realized/executable PnL, OOS, native qualification, or economic support is established.", "",
             "Prospective support requires the frozen 200/50/40 floors plus the conditional power and uncertainty gates. "
             "Opportunity frequency and accumulation time remain UNKNOWN. Synthetic weeks are QA only.", "",
             "Controller 0-C alone decides scoped engineering acceptance. No new research trial is created.", ""]
    return "\n".join(text)


def write_ledger(output: Path, rows: list[LedgerRow]) -> None:
    values = [r.to_dict() for r in rows]
    write_json(output / "scenario_ledger.json", {"schema_version": "C_TYPED_SCENARIO_LEDGER_V1", "rows": values})
    columns = list(LedgerRow.__dataclass_fields__)
    with (output / "scenario_ledger.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in values:
            writer.writerow({k: json.dumps(v, sort_keys=True, separators=(",", ":"), allow_nan=False)
                             if isinstance(v, (list, dict)) else "UNKNOWN" if v is None else v for k, v in row.items()})


def evaluate(envelope: dict, protocol: dict, output: Path, input_raw: bytes) -> dict:
    rows = ledger(envelope, protocol)
    summary = summarize(envelope, rows, protocol)
    summary["input_external_sha256"] = sha(input_raw)
    summary["protocol_sha256"] = protocol["protocol_sha256"]
    write_ledger(output, rows)
    write_json(output / "summary.json", summary)
    write_json(output / "protocol.json", protocol)
    write_json(output / "status.json", {"status": "PROGRAM_C_OFFLINE_EVALUATOR_READY_INSUFFICIENT_SUPPORT",
                                       "controller_acceptance": "PENDING_CONTROLLER_0C",
                                       "scientific_decision": "INSUFFICIENT_SUPPORT", **FLAGS})
    (output / "scientific_report.md").write_text(scientific_report(summary, rows), encoding="utf-8", newline="\n")
    write_json(output / "support_and_power_plan.json", power_plan(protocol))
    return summary
