"""Four finite local commands. No network, collection, signing or strategy activation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import ledger
from .integrity import (
    RESOURCE_ROOT,
    ContractError,
    digest,
    fresh_directory,
    parse,
    read_input,
    require,
    sha,
    without,
    write_json,
)
from .protocol import FLAGS, load_protocol
from .reporting import evaluate, write_ledger
from .statistics import power_plan, summarize
from .validation import validate


def run_scenarios(raw: bytes, output: Path, protocol: dict) -> dict:
    suite = parse(raw)
    require(suite.get("schema_version") == "C_FABRICATED_FIXTURE_SUITE_V1"
            and suite.get("protocol_sha256") == protocol["protocol_sha256"]
            and suite.get("manifest_sha256") == digest(without(suite, "manifest_sha256")), "FIXTURE_SUITE_MANIFEST")
    results, all_rows = [], []
    for item in suite["fixtures"]:
        fixture_raw = (RESOURCE_ROOT / item["path"]).read_bytes()
        require(sha(fixture_raw) == item["sha256"], "FIXTURE_FILE_HASH")
        try:
            envelope = validate(fixture_raw, protocol)
            rows = ledger(envelope, protocol)
            summary = summarize(envelope, rows, protocol)
            outcomes = sorted(set(r.outcome for r in rows if r.target_geometry == "FROZEN"
                                  and r.cost_case == "BASE" and r.delay_ms == 0))
            status = "VALID"
            all_rows.extend(rows)
        except ContractError as exc:
            status, outcomes, summary = str(exc), [], None
        passed = status == item["expected_validation"] and outcomes == item["expected_outcomes"]
        results.append({"fixture": item["name"], "validation": status, "outcomes": outcomes,
                        "expected_validation": item["expected_validation"], "expected_outcomes": item["expected_outcomes"],
                        "PASS": passed, "summary_QA_only": summary})
    result: dict = {"schema_version": "C_SYNTHETIC_SCENARIO_MATRIX_V1", "source": "FABRICATED_QA_NO_MARKET_DATA",
              "status": "PASS" if all(x["PASS"] for x in results) else "FAIL", "fixture_count": len(results),
              "results": results, "native_economic_support": 0, "scientific_decision": "INSUFFICIENT_SUPPORT"}
    write_json(output / "scenario_matrix.json", result)
    write_json(output / "protocol.json", protocol)
    write_json(output / "status.json", {"status": result["status"], "purpose": "QA_ONLY_NOT_EVIDENCE", **FLAGS})
    write_ledger(output, all_rows)
    (output / "scientific_report.md").write_text(
        "# Fabricated Program C QA scenarios\n\n" + result["status"] + f"; {len(results)} fabricated cases.\n\n"
        "Each fixture is a separate controlled QA experiment; do not pool its outcomes as a strategy study. "
        "Native economic observations and support are zero. Scientific decision: INSUFFICIENT_SUPPORT.\n",
        encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["validate", "evaluate", "scenarios", "plan"]:
        command = sub.add_parser(name)
        command.add_argument("--output", type=Path, required=True)
        command.add_argument("--fixtures" if name == "scenarios" else "--protocol" if name == "plan" else "--input",
                             type=Path, required=True)
    args = parser.parse_args(argv)
    output = None
    try:
        output = fresh_directory(args.output)
        protocol = load_protocol()
        if args.command == "plan":
            protocol = load_protocol(read_input(args.protocol))
            result = power_plan(protocol)
            write_json(output / "support_and_power_plan.json", result)
            write_json(output / "protocol.json", protocol)
            write_json(output / "status.json", {"status": "PROSPECTIVE_TEST_READY_METHOD",
                                               "scientific_decision": "INSUFFICIENT_SUPPORT", **FLAGS})
            write_ledger(output, [])
            (output / "scientific_report.md").write_text(
                "# Prospective methodology only\n\nINSUFFICIENT_SUPPORT. No trial or PRIMARY registration created.\n\n"
                + f"Conditional required clusters per family: {result['required_independent_clusters_per_family_under_assumptions']}. "
                "Actual native observations: zero; payoff bounds and independence unverified.\n", encoding="utf-8")
        elif args.command == "scenarios":
            result = run_scenarios(read_input(args.fixtures), output, protocol)
            if result["status"] != "PASS":
                print(json.dumps({"status": "FAIL", "output": str(output)}))
                return 1
        else:
            raw = read_input(args.input)
            envelope = validate(raw, protocol)
            result = evaluate(envelope, protocol, output, raw)
            write_json(output / "validation.json", {"status": "VALID_SOURCE_NEUTRAL_NOT_NATIVE_ADMISSION",
                                                  "input_external_sha256": sha(raw),
                                                  "source_class": envelope["source_kind"],
                                                  "command": args.command})
        print(json.dumps({"status": "PASS", "scientific_decision": "INSUFFICIENT_SUPPORT", "output": str(output)}, sort_keys=True))
        return 0
    except (ContractError, KeyError, TypeError, ValueError, OSError, StopIteration) as exc:
        reason = str(exc) if isinstance(exc, ContractError) else "INVALID_SCHEMA_OR_LOCAL_IO: " + type(exc).__name__
        failure = {"status": "BLOCKED_CONTRACT_OR_PROVENANCE", "reason": reason,
                   "scientific_decision": "INSUFFICIENT_SUPPORT", **FLAGS}
        if output is not None:
            error_path = output / "failure.json"
            if not error_path.exists():
                write_json(error_path, failure)
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
