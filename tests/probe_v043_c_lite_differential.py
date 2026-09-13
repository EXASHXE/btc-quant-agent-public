"""Isolated cross-checkout probe; all inputs/outputs live in an explicit temp root.

Run this identical probe with the baseline src/tests first on sys.path, then
with the candidate src/tests. It is not an alpha runner or production loader.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from pathlib import Path

import test_v041_p6_metrics_benchmarks_qualification as p6
from helpers_v042_economic_replay import context

from btc_quant_agent.backtest import resample
from btc_quant_agent.data.funding import read_funding_events_csv
from btc_quant_agent.economic import (
    evaluate_formal_economic_qualification,
    make_artifact_evidence,
)
from btc_quant_agent.economic.acceptance_verifier import validate_persisted_qualification_semantics
from btc_quant_agent.research_contract.canonical import canonical_json, canonical_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--facade", action="store_true")
    args = parser.parse_args()
    snapshots = {}
    for nonzero in (False, True):
        root = args.root / ("nonzero" if nonzero else "zero")
        ctx = context(root / "input", nonzero=nonzero)
        registry_root = root / "registry"
        registry_root.mkdir(parents=True, exist_ok=True)
        registry, _ = p6._statistically_qualified_registry(registry_root, ctx["protocol"])
        if args.facade:
            from btc_quant_agent.formal_research import FormalResearchJobSpec, run_formal_job

            spec = FormalResearchJobSpec(
                protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
                engine=ctx["engine"], candles=ctx["candles"], signals=ctx["signals"],
                decision_inputs=tuple(p6._decision_input_binding(
                    signal, ctx["dataset"], ctx["candles"], ctx["protocol"],
                ) for signal in ctx["signals"]),
                eligible_opportunities=p6._opportunities(ctx["candles"]),
                funding_events=ctx["funding"], observed_at_utc=p6.FIXED_TIME,
            )
            result = run_formal_job(spec, output_directory=root / "output", registry=registry,
                                    record_decision=True)
            run, suite, qualification = result.run, result.benchmarks, result.qualification
            evidence = result.evidence
        else:
            run, suite = ctx["run"], ctx["suite"]
            directory = root / "output" / run.result_hash
            directory.mkdir(parents=True, exist_ok=True)
            references = [ctx["dataset"]]
            for name, artifact, kind in (
                ("candidate-run", run, p6.P6_RUN_EVIDENCE_TYPE),
                ("benchmark-suite", suite, p6.P6_BENCHMARK_EVIDENCE_TYPE),
            ):
                path = directory / f"{name}.json"
                artifact.write(path)
                references.append(make_artifact_evidence(
                    path, evidence_type=kind, logical_id=name, protocol=ctx["protocol"],
                    observed_at_utc=p6.FIXED_TIME,
                ))
            qualification = evaluate_formal_economic_qualification(
                protocol=ctx["protocol"], comparison=ctx["comparison"], candidate_run=run,
                benchmarks=suite, required_evidence_ids=tuple(e.evidence_id for e in references),
                generated_at_utc=p6.FIXED_TIME,
            )
            validate_persisted_qualification_semantics(
                qualification.semantic_payload(), ctx["dataset"], protocol=ctx["protocol"],
            )
            path = directory / f"qualification-{qualification.result_hash}.json"
            qualification.write(path)
            result_evidence = make_artifact_evidence(
                path, evidence_type=p6.P6_RESULT_EVIDENCE_TYPE, logical_id="qualification",
                protocol=ctx["protocol"], observed_at_utc=p6.FIXED_TIME,
            )
            references.append(result_evidence)
            evidence = tuple(references)
            registry.record_economic_qualification(
                qualification.decision_attestation(result_evidence), evidence_references=evidence,
                reason="verified formal consumer workflow", actor="formal-research-job",
                decided_at_utc=p6.FIXED_TIME,
            )
        candles = tuple(replace(c, interval="1m", open_time_ms=i * 60_000,
                                close_time_ms=(i + 1) * 60_000 - 1)
                        for i, c in enumerate(p6._candles(31)))
        funding_path = root / "funding.csv"
        funding_path.write_text("timestamp_ms,funding_rate,mark_price\n1,0.001,101\n2,-0.002,\n",
                                encoding="utf-8")
        snapshots[str(nonzero)] = {
            "run": run.to_dict(), "suite": suite.to_dict(), "qualification": qualification.to_dict(),
            "evidence": [e.to_dict() for e in evidence], "registry": registry.to_dict(),
            "registry_bytes_sha256": canonical_sha256(json.loads(registry.storage_path.read_text())),
            "resample": [asdict(c) for c in resample(candles, "15m")],
            "gap_resample": [asdict(c) for c in resample(candles[:7] + candles[8:], "15m")],
            "funding_csv": [asdict(e) for e in read_funding_events_csv(funding_path)],
        }
    args.snapshot.write_text(canonical_json(snapshots) + "\n", encoding="utf-8")
    print(canonical_json({"snapshot_sha256": canonical_sha256(snapshots),
                          "fixtures": len(snapshots)}))


if __name__ == "__main__":
    main()
