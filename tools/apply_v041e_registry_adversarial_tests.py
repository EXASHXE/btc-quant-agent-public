from __future__ import annotations

from pathlib import Path


path = Path("tests/test_v041_p6_metrics_benchmarks_qualification.py")
text = path.read_text(encoding="utf-8")
old_import = (
    "from btc_quant_agent.research_contract.canonical import FrozenDict, canonical_json\n"
)
new_import = (
    "from btc_quant_agent.research_contract.canonical import (\n"
    "    FrozenDict,\n"
    "    canonical_json,\n"
    "    canonical_sha256,\n"
    ")\n"
)
if old_import not in text:
    raise RuntimeError("canonical import anchor missing")
text = text.replace(old_import, new_import, 1)
append = r'''

_BENCHMARK_RESULT_PAYLOAD_KEYS = (
    "benchmark_kind",
    "vehicle",
    "accounting",
    "comparable",
    "matching_diagnostics",
    "trial_id",
    "seed",
    "run_result_id",
)


def _refresh_benchmark_record_id(record: dict[str, Any]) -> None:
    payload = {key: record.get(key) for key in _BENCHMARK_RESULT_PAYLOAD_KEYS}
    record["result_id"] = f"benchmark-result@{canonical_sha256(payload)}"


def _refresh_suite_identity(suite: dict[str, Any]) -> None:
    random_record = suite.get("random")
    if isinstance(random_record, dict):
        trials = random_record["trials"]
        for trial in trials:
            _refresh_benchmark_record_id(trial)
        random_record["distribution_id"] = "random-distribution@" + canonical_sha256(
            {"seed": random_record["seed"], "trials": trials}
        )
    suite_payload = {
        key: suite.get(key)
        for key in (
            "comparison_contract_id",
            "candidate_run_result_id",
            "eligible_opportunity_set_sha256",
            "cash",
            "passive",
            "random",
        )
    }
    suite["suite_id"] = f"benchmark-suite@{canonical_sha256(suite_payload)}"


def _suite_result_ids(suite: dict[str, Any]) -> list[str]:
    result: list[str] = []
    if suite.get("cash") is not None:
        result.append(suite["cash"]["result_id"])
    if suite.get("passive") is not None:
        result.append(suite["passive"]["result_id"])
    random_record = suite.get("random")
    if random_record is not None:
        result.append(random_record["distribution_id"])
        result.extend(trial["result_id"] for trial in random_record["trials"])
    return result


def _write_forged_registry_artifacts(
    tmp_path: Path,
    artifacts: dict[str, Any],
    artifact: dict[str, Any],
    *,
    run_changed: bool,
    suite_changed: bool,
) -> tuple[Any, tuple[EvidenceReference, ...]]:
    semantic = artifact["semantic_payload"]
    protocol = artifacts["protocol"]
    run_evidence = artifacts["run_evidence"]
    suite_evidence = artifacts["suite_evidence"]

    if run_changed:
        run_path = tmp_path / "forged-run.json"
        run_path.write_text(canonical_json(semantic["run_result"]) + "\n", encoding="utf-8")
        run_evidence = make_artifact_evidence(
            run_path,
            evidence_type=P6_RUN_EVIDENCE_TYPE,
            logical_id="p6-forged-candidate-run",
            protocol=protocol,
            observed_at_utc=FIXED_TIME,
        )
    if suite_changed:
        suite_path = tmp_path / "forged-suite.json"
        suite_path.write_text(
            canonical_json(semantic["benchmark_suite"]) + "\n", encoding="utf-8"
        )
        suite_evidence = make_artifact_evidence(
            suite_path,
            evidence_type=P6_BENCHMARK_EVIDENCE_TYPE,
            logical_id="p6-forged-benchmark-suite",
            protocol=protocol,
            observed_at_utc=FIXED_TIME,
        )

    semantic["required_evidence_ids"] = [
        artifacts["dataset"].evidence_id,
        run_evidence.evidence_id,
        suite_evidence.evidence_id,
    ]
    result_hash = canonical_sha256(semantic)
    artifact["result_id"] = f"economic-qualification@{result_hash}"
    result_path = tmp_path / "forged-qualification.json"
    result_path.write_text(canonical_json(artifact) + "\n", encoding="utf-8")
    result_evidence = make_artifact_evidence(
        result_path,
        evidence_type=P6_RESULT_EVIDENCE_TYPE,
        logical_id="p6-forged-qualification-result",
        protocol=protocol,
        observed_at_utc=FIXED_TIME,
    )
    original_attestation = artifacts["qualification"].decision_attestation(
        artifacts["result_evidence"]
    )
    attestation = replace(
        original_attestation,
        result_evidence_id=result_evidence.evidence_id,
        result_artifact_sha256=result_evidence.content_sha256,
        result_id=artifact["result_id"],
        result_hash=result_hash,
        verdict=semantic["verdict"],
        run_result_id=semantic["run_result_id"],
        benchmark_suite_id=semantic["benchmark_suite_id"],
        benchmark_result_ids=tuple(semantic["benchmark_result_ids"]),
        required_evidence_ids=tuple(semantic["required_evidence_ids"]),
    )
    return attestation, (
        artifacts["dataset"],
        run_evidence,
        suite_evidence,
        result_evidence,
    )


def test_registry_rejects_rehashed_forged_run_accounting(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    run_artifact = semantic["run_result"]
    accounting = run_artifact["semantic_payload"]["accounting"]
    delta = 100.0
    accounting["final_equity"] += delta
    accounting["final_cash"] += delta
    accounting["gross_pnl_usdt"] += delta
    accounting["realized_gross_pnl_usdt"] += delta
    accounting["net_pnl_usdt"] += delta
    accounting["net_return_pct"] = accounting["net_pnl_usdt"] / accounting["initial_cash"]
    accounting["equity_curve"][-1][1] += delta
    semantic["metric_values"]["net_return_pct"] = accounting["net_return_pct"]
    semantic["gates"][0]["observed_value"] = accounting["net_return_pct"]

    run_semantic = run_artifact["semantic_payload"]
    run_artifact["result_id"] = "economic-run-result@" + canonical_sha256(run_semantic)
    semantic["run_result_id"] = run_artifact["result_id"]
    suite = semantic["benchmark_suite"]
    suite["candidate_run_result_id"] = run_artifact["result_id"]
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=True,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="semantic replay"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged run accounting must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_forged_gate_and_verdict(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base, threshold=1.0)
    assert artifacts["qualification"].verdict is QualificationVerdict.REJECTED
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    gate = semantic["gates"][0]
    gate["observed_value"] = 2.0
    gate["testable"] = True
    gate["passed"] = True
    gate["reason_code"] = "GATE_PASSED"
    semantic["verdict"] = "QUALIFIED"
    semantic["reason_codes"] = ["ALL_PREREGISTERED_HURDLES_PASSED"]

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=False,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="semantic replay"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged qualification gate must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )


def test_registry_rejects_rehashed_forged_random_matching_diagnostics(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    artifacts = _formal_artifacts(base)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    random_record = suite["random"]
    assert random_record is not None
    trial = random_record["trials"][0]
    trial["matching_diagnostics"]["trial_entry_count"] += 1
    _refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = _suite_result_ids(suite)

    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = _write_forged_registry_artifacts(
        forged_dir,
        artifacts,
        artifact,
        run_changed=False,
        suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = _statistically_qualified_registry(registry_dir, artifacts["protocol"])
    with pytest.raises(EvidenceValidationError, match="matching diagnostics"):
        registry.record_economic_qualification(
            attestation,
            evidence_references=evidence,
            reason="forged random comparability must fail closed",
            actor="pytest",
            decided_at_utc=FIXED_TIME,
        )
'''
if "test_registry_rejects_rehashed_forged_run_accounting" in text:
    raise RuntimeError("registry adversarial tests already present")
path.write_text(text.rstrip() + append + "\n", encoding="utf-8")
