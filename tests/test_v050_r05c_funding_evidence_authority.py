"""R05C T1-T20: independent preregistered funding settlement evidence authority.

AG-01 HIGH repair proof: the funding evidence file is the only admissible
source of formal funding events. Candidate swaps (sign, delete, add, mark,
rate), zero-event stripping, coverage drift, persisted replay forgeries and
relabelled identities are all rejected; benchmarks and cold replay reload the
evidence independently. All inputs use explicit relative paths under a
per-test chdir so the authority chain is exercised as a local, replayable
filesystem root.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import test_v041_p6_metrics_benchmarks_qualification as p6

from btc_quant_agent.economic import (
    BenchmarkKind,
    EconomicSimulationEngine,
    ExecutionModel,
    FeeModel,
    FundingIntervalIdentity,
    FundingSettlement,
    InformationSignal,
    SlippageMode,
    build_formal_benchmark_suite,
    build_formal_replay_input_bundle,
    evaluate_formal_economic_qualification,
    execute_bound_run,
    funding_event_set_sha256,
    load_and_validate_funding_evidence,
)
from btc_quant_agent.economic.acceptance_verifier import (
    validate_persisted_qualification_semantics,
)
from btc_quant_agent.economic.execution_replay import (
    verify_benchmark_replay,
    verify_execution_replay,
)
from btc_quant_agent.formal_research import (
    FormalResearchJobSpec,
    run_formal_job,
)
from btc_quant_agent.research_contract import (
    DecisionStatus,
    EvidenceValidationError,
)
from btc_quant_agent.research_contract.canonical import (
    canonical_json,
    canonical_sha256,
    thaw_json,
)
from btc_quant_agent.research_contract.models import (
    EvidenceCompleteness,
    EvidenceReference,
)

FUNDING_TYPE = "FORMAL_FUNDING_SETTLEMENT_DATASET"


def _context(tmp_path: Path, monkeypatch, *, nonzero: bool = True) -> dict:
    """Full relative-path context; evidence files resolve under tmp_path."""
    monkeypatch.chdir(tmp_path)
    candles = p6._candles()
    base = p6._zero_cost_engine()
    fee = FeeModel(
        taker_fee_rate=0.0005 if nonzero else 0.0, maker_fee_rate=0.0,
        slippage_mode=SlippageMode.SPREAD_AND_IMPACT if nonzero else SlippageMode.ZERO,
        max_slippage_bps=20.0,
    )
    engine = EconomicSimulationEngine(
        policy=base.policy, fee_model=fee, initial_cash=base.initial_cash,
        execution_model=ExecutionModel(fee_model=fee, decision_latency_ms=0, exchange_latency_ms=0),
    )
    dataset = p6._dataset_evidence(Path("."), candles)
    funding = (FundingSettlement(candles[1].open_time_ms + 1000, 0.001, 101.0),) if nonzero else ()
    funding_evidence = p6._funding_evidence(Path("."), candles, funding)
    comparison = p6._comparison(
        dataset, candles, engine, required=(BenchmarkKind.CASH, BenchmarkKind.RANDOM_MATCHED),
        descriptive=(), funding_events=funding,
    )
    protocol = p6._protocol(comparison, engine)
    signals = tuple(InformationSignal(
        f"R05C-{index}", protocol.experiment_revision_id, candles[index].open_time_ms,
        direction=direction,
        metadata={
            "spread_bps": 2.0, "liquidity_volume_base": 1000.0,
            "liquidity_available_at_ms": candles[index - 1].close_time_ms,
        } if nonzero else {},
    ) for index, direction in ((1, 1), (4, -1)))
    bundle = build_formal_replay_input_bundle(
        protocol=protocol, dataset_evidence=dataset, candles=candles, signals=signals,
        decision_inputs=tuple(
            p6._decision_input_binding(signal, dataset, candles, protocol) for signal in signals
        ), funding_events=funding,
    )
    run = execute_bound_run(
        protocol=protocol, comparison=comparison, dataset_evidence=dataset, candles=candles,
        engine=engine, signals=signals, replay_input_bundle=bundle,
        funding_evidence=funding_evidence,
    )
    return {"candles": candles, "engine": engine, "dataset": dataset, "funding": funding,
            "funding_evidence": funding_evidence, "comparison": comparison,
            "protocol": protocol, "signals": signals, "run": run}


def _rerun(ctx):
    """Re-execute the candidate run with the current funding evidence bytes."""
    bundle = build_formal_replay_input_bundle(
        protocol=ctx["protocol"], dataset_evidence=ctx["dataset"], candles=ctx["candles"],
        signals=ctx["signals"], decision_inputs=tuple(
            p6._decision_input_binding(signal, ctx["dataset"], ctx["candles"], ctx["protocol"])
            for signal in ctx["signals"]
        ), funding_events=ctx["funding"],
    )
    return execute_bound_run(
        protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
        candles=ctx["candles"], engine=ctx["engine"], signals=ctx["signals"],
        replay_input_bundle=bundle, funding_evidence=ctx["funding_evidence"],
    )


def _rewrite_funding_file(events=(), *, coverage_start_ms: int | None = None,
                          coverage_end_ms: int | None = None, raw: str | None = None) -> None:
    """Overwrite ./funding.json with attacker-chosen bytes (same path as authority)."""
    if raw is None:
        raw = canonical_json({
            "schema_version": "1.0.0", "product": "BTCUSDT",
            "coverage_start_ms": coverage_start_ms,
            "coverage_end_ms": coverage_end_ms,
            "events": [asdict(item) for item in events],
        }) + "\n"
    Path("funding.json").write_text(raw, encoding="utf-8")


def _matching_identity(evidence: EvidenceReference, candles, events=()) -> FundingIntervalIdentity:
    return FundingIntervalIdentity(
        evidence_id=evidence.evidence_id, content_sha256=evidence.content_sha256,
        coverage_start_ms=candles[0].open_time_ms, coverage_end_ms=candles[-1].close_time_ms,
        event_count=len(events), event_set_sha256=funding_event_set_sha256(events),
    )


def _load_authoritative(evidence, candles, expected_identity):
    return load_and_validate_funding_evidence(
        evidence, expected_product="BTCUSDT", expected_start_ms=candles[0].open_time_ms,
        expected_end_ms=candles[-1].close_time_ms, expected_identity=expected_identity,
    )


# ---------------------------------------------------------------------------
# T1-T6: in-place funding file tampering is rejected by content binding
# ---------------------------------------------------------------------------


def test_t1_funding_sign_swap_rejected_by_content_binding(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    settlement = ctx["funding"][0]
    _rewrite_funding_file((FundingSettlement(settlement.timestamp_ms, -0.001, 101.0),))
    with pytest.raises(ValueError, match="bytes differ from preregistered content hash"):
        _rerun(ctx)
    with pytest.raises(ValueError, match="bytes differ from preregistered content hash"):
        _load_authoritative(
            ctx["funding_evidence"], ctx["candles"], ctx["comparison"].funding_interval,
        )


def test_t2_funding_event_deletion_rejected_by_content_binding(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    _rewrite_funding_file(())
    with pytest.raises(ValueError, match="bytes differ from preregistered content hash"):
        _rerun(ctx)


def test_t3_funding_event_addition_rejected_by_content_binding(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    candles = ctx["candles"]
    forged = (*ctx["funding"], FundingSettlement(candles[3].open_time_ms + 1000, -0.0005, 100.5))
    _rewrite_funding_file(forged)
    with pytest.raises(ValueError, match="bytes differ from preregistered content hash"):
        _rerun(ctx)


def test_t4_funding_timestamp_modification_rejected(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    settlement = ctx["funding"][0]
    _rewrite_funding_file((FundingSettlement(settlement.timestamp_ms + 1, 0.001, 101.0),))
    with pytest.raises(ValueError, match="bytes differ from preregistered content hash"):
        _rerun(ctx)


def test_t5_funding_mark_price_modification_rejected(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    settlement = ctx["funding"][0]
    _rewrite_funding_file((FundingSettlement(settlement.timestamp_ms, 0.001, 999.0),))
    with pytest.raises(ValueError, match="bytes differ from preregistered content hash"):
        _rerun(ctx)


def test_t6_funding_rate_magnitude_modification_rejected(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    settlement = ctx["funding"][0]
    _rewrite_funding_file((FundingSettlement(settlement.timestamp_ms, 0.002, 101.0),))
    with pytest.raises(ValueError, match="bytes differ from preregistered content hash"):
        _rerun(ctx)


# ---------------------------------------------------------------------------
# T7-T8: caller lists are assertions; zero events require full-interval proof
# ---------------------------------------------------------------------------


def test_t7_caller_empty_list_is_not_no_settlements(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    bundle = build_formal_replay_input_bundle(
        protocol=ctx["protocol"], dataset_evidence=ctx["dataset"], candles=ctx["candles"],
        signals=ctx["signals"], decision_inputs=tuple(
            p6._decision_input_binding(signal, ctx["dataset"], ctx["candles"], ctx["protocol"])
            for signal in ctx["signals"]
        ), funding_events=ctx["funding"],
    )
    with pytest.raises(ValueError, match="submitted funding events differ"):
        execute_bound_run(
            protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
            candles=ctx["candles"], engine=ctx["engine"], signals=ctx["signals"],
            replay_input_bundle=bundle, funding_evidence=ctx["funding_evidence"],
            funding_events=(),
        )
    # The exact caller list is accepted as an assertion only.
    assert _rerun(ctx).result_id == ctx["run"].result_id


def test_t8_zero_event_evidence_requires_full_interval_coverage(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=False)
    assert _load_authoritative(
        ctx["funding_evidence"], ctx["candles"], ctx["comparison"].funding_interval,
    ) == ()
    assert ctx["run"].accounting["total_funding_usdt"] == 0.0
    # A zero-event artifact that does not cover the comparison interval is invalid.
    candles = ctx["candles"]
    _rewrite_funding_file((), coverage_start_ms=candles[0].open_time_ms + 1,
                          coverage_end_ms=candles[-1].close_time_ms)
    reference = EvidenceReference.from_file(
        Path("funding.json"), evidence_type=FUNDING_TYPE, logical_id="p6-funding-dataset",
        producing_revision_id="DATASET-PIPELINE@v1", producing_code_revision="dataset-code-v1",
        observed_at_utc=p6.FIXED_TIME,
    )
    forged_interval = _matching_identity(reference, candles)
    with pytest.raises(ValueError, match="coverage differs from the comparison interval"):
        _load_authoritative(reference, candles, forged_interval)


# ---------------------------------------------------------------------------
# T9-T10: completeness and content-hash authority
# ---------------------------------------------------------------------------


def test_t9_partial_funding_evidence_rejected(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    partial = replace(ctx["funding_evidence"], completeness=EvidenceCompleteness.PARTIAL)
    with pytest.raises(ValueError, match="must be COMPLETE for formal promotion"):
        _load_authoritative(partial, ctx["candles"], ctx["comparison"].funding_interval)


def test_t10_content_hash_mismatch_rejected(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    tampered = replace(ctx["funding_evidence"], content_sha256="f" * 64)
    with pytest.raises(ValueError, match="bytes differ from preregistered content hash"):
        _load_authoritative(tampered, ctx["candles"], ctx["comparison"].funding_interval)


# ---------------------------------------------------------------------------
# T11: relabelled candidate funding identity is not authority
# ---------------------------------------------------------------------------


def test_t11_candidate_identity_swap_rejected_by_suite_builder(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    Path("attack").mkdir()
    other = p6._funding_evidence(Path("attack"), ctx["candles"], ())
    with pytest.raises(ValueError, match="candidate run is not bound to the preregistered funding evidence"):
        build_formal_benchmark_suite(
            protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
            candidate_run=ctx["run"], engine=ctx["engine"], candles=ctx["candles"],
            eligible_opportunities=p6._opportunities(ctx["candles"]), funding_evidence=other,
        )


# ---------------------------------------------------------------------------
# T12-T14: file-level strict validation (chronology, numerics, window)
# ---------------------------------------------------------------------------


def test_t12_chronology_violation_rejected(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    candles = ctx["candles"]
    first = FundingSettlement(candles[1].open_time_ms + 1000, 0.001, 101.0)
    second = FundingSettlement(candles[3].open_time_ms + 1000, -0.0005, 100.5)
    _rewrite_funding_file((second, first), coverage_start_ms=candles[0].open_time_ms,
                          coverage_end_ms=candles[-1].close_time_ms)
    reference = EvidenceReference.from_file(
        Path("funding.json"), evidence_type=FUNDING_TYPE, logical_id="p6-funding-dataset",
        producing_revision_id="DATASET-PIPELINE@v1", producing_code_revision="dataset-code-v1",
        observed_at_utc=p6.FIXED_TIME,
    )
    with pytest.raises(ValueError, match="strictly increasing in time"):
        _load_authoritative(reference, candles, _matching_identity(reference, candles, (second, first)))


def test_t13_non_finite_numerics_rejected(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    candles = ctx["candles"]
    _rewrite_funding_file(raw=(
        '{"schema_version": "1.0.0", "product": "BTCUSDT", '
        f'"coverage_start_ms": {candles[0].open_time_ms}, '
        f'"coverage_end_ms": {candles[-1].close_time_ms}, '
        '"events": [{"timestamp_ms": %d, "funding_rate": NaN, "mark_price": 101.0}]}'
        % (candles[1].open_time_ms + 1000,)
    ))
    reference = EvidenceReference.from_file(
        Path("funding.json"), evidence_type=FUNDING_TYPE, logical_id="p6-funding-dataset",
        producing_revision_id="DATASET-PIPELINE@v1", producing_code_revision="dataset-code-v1",
        observed_at_utc=p6.FIXED_TIME,
    )
    with pytest.raises(ValueError, match="nonfinite JSON value"):
        _load_authoritative(reference, candles, _matching_identity(reference, candles))


def test_t14_out_of_window_event_rejected(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    candles = ctx["candles"]
    outside = FundingSettlement(candles[-1].close_time_ms + 1, 0.001, 101.0)
    _rewrite_funding_file((outside,), coverage_start_ms=candles[0].open_time_ms,
                          coverage_end_ms=candles[-1].close_time_ms)
    reference = EvidenceReference.from_file(
        Path("funding.json"), evidence_type=FUNDING_TYPE, logical_id="p6-funding-dataset",
        producing_revision_id="DATASET-PIPELINE@v1", producing_code_revision="dataset-code-v1",
        observed_at_utc=p6.FIXED_TIME,
    )
    with pytest.raises(ValueError, match="outside the declared coverage"):
        _load_authoritative(reference, candles, _matching_identity(reference, candles, (outside,)))


# ---------------------------------------------------------------------------
# T15: persisted replay forgery is rejected by independent authoritative reload
# ---------------------------------------------------------------------------


def test_t15_persisted_forgery_rejected_by_independent_reload(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    reloaded = json.loads(canonical_json(ctx["run"].semantic_payload()))
    inputs = reloaded["accounting"]["formal_execution_replay_inputs"]
    inputs["funding_events"][0]["funding_rate"] = -0.001
    if inputs.get("bundle_sha256"):
        inputs["bundle_sha256"] = canonical_sha256(
            {key: value for key, value in inputs.items() if key != "bundle_sha256"}
        )
    with pytest.raises(ValueError, match="persisted funding events differ"):
        verify_execution_replay(reloaded, protocol=ctx["protocol"], comparison=ctx["comparison"])
    # A forged file with an updated reference cannot survive the identity cross-check either.
    settlement = ctx["funding"][0]
    _rewrite_funding_file(
        (FundingSettlement(settlement.timestamp_ms, -0.001, 101.0),),
        coverage_start_ms=ctx["candles"][0].open_time_ms,
        coverage_end_ms=ctx["candles"][-1].close_time_ms,
    )
    forged_reference = replace(
        ctx["funding_evidence"],
        content_sha256=hashlib.sha256(Path("funding.json").read_bytes()).hexdigest(),
    )
    forged_identity = replace(
        ctx["comparison"].funding_interval,
        content_sha256=forged_reference.content_sha256,
        evidence_id=forged_reference.evidence_id,
    )
    with pytest.raises(ValueError, match="preregistered"):
        _load_authoritative(forged_reference, ctx["candles"], forged_identity)


# ---------------------------------------------------------------------------
# T16: candidate, passive and random benchmarks share one funding root
# ---------------------------------------------------------------------------


def test_t16_common_funding_root_across_benchmarks(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=True)
    suite = build_formal_benchmark_suite(
        protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
        candidate_run=ctx["run"], engine=ctx["engine"], candles=ctx["candles"],
        eligible_opportunities=p6._opportunities(ctx["candles"]),
        funding_evidence=ctx["funding_evidence"],
    )
    # The suite replays end-to-end from the same independently reloaded evidence.
    verify_benchmark_replay(
        ctx["run"].semantic_payload(), suite.to_dict(), protocol=ctx["protocol"],
        comparison=ctx["comparison"],
    )
    for trial in suite.random.trials:
        identity = thaw_json(trial.accounting)["formal_run_identity"]
        assert identity["funding_evidence_id"] == ctx["funding_evidence"].evidence_id
        assert identity["funding_evidence_content_sha256"] == ctx["funding_evidence"].content_sha256
    # A different funding root cannot bind the candidate.
    Path("attack").mkdir()
    other = p6._funding_evidence(Path("attack"), ctx["candles"], ())
    with pytest.raises(ValueError, match="candidate run is not bound"):
        build_formal_benchmark_suite(
            protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
            candidate_run=ctx["run"], engine=ctx["engine"], candles=ctx["candles"],
            eligible_opportunities=p6._opportunities(ctx["candles"]), funding_evidence=other,
        )


# ---------------------------------------------------------------------------
# T17: qualification evidence chain carries the funding authority
# ---------------------------------------------------------------------------


def test_t17_qualification_evidence_chain_carries_funding_authority(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=False)
    suite = build_formal_benchmark_suite(
        protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
        candidate_run=ctx["run"], engine=ctx["engine"], candles=ctx["candles"],
        eligible_opportunities=p6._opportunities(ctx["candles"]),
        funding_evidence=ctx["funding_evidence"],
    )
    qualification = evaluate_formal_economic_qualification(
        protocol=ctx["protocol"], comparison=ctx["comparison"], candidate_run=ctx["run"],
        benchmarks=suite,
        required_evidence_ids=(ctx["dataset"].evidence_id, ctx["funding_evidence"].evidence_id),
        generated_at_utc=p6.FIXED_TIME,
    )
    semantic = json.loads(canonical_json(qualification.semantic_payload()))
    validate_persisted_qualification_semantics(semantic, ctx["dataset"], protocol=ctx["protocol"])
    assert ctx["run"].identity.funding_evidence_id == ctx["funding_evidence"].evidence_id
    assert ctx["run"].identity.funding_evidence_content_sha256 == ctx["funding_evidence"].content_sha256
    assert suite.comparison_contract_id == ctx["comparison"].contract_id
    # The qualification semantic payload embeds the preregistered funding interval.
    payload = ctx["comparison"].semantic_payload()
    assert payload["funding_interval"]["evidence_id"] == ctx["funding_evidence"].evidence_id


# ---------------------------------------------------------------------------
# T18-T19: legacy inputs and protected paths are refused
# ---------------------------------------------------------------------------


def test_t18_legacy_job_and_legacy_comparison_refused(tmp_path, monkeypatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=False)
    legacy_comparison = {
        key: value for key, value in ctx["comparison"].semantic_payload().items()
        if key != "funding_interval"
    }
    with pytest.raises(ValueError, match="NOT_TESTABLE"):
        type(ctx["comparison"]).from_payload(legacy_comparison)


def test_t19_protected_paths_rejected_before_use(tmp_path, monkeypatch) -> None:
    _context(tmp_path, monkeypatch, nonzero=False)
    with pytest.raises(ValueError):
        FormalResearchJobSpec.load(tmp_path / "final_holdout/job.json")
    with pytest.raises(ValueError):
        FormalResearchJobSpec.load(tmp_path / "h39_canonical_1m_candles.sqlite3")


# ---------------------------------------------------------------------------
# T20: cold job replay is idempotent and carries the funding authority
# ---------------------------------------------------------------------------


def _job_spec(ctx):
    return FormalResearchJobSpec(
        protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
        funding_evidence=ctx["funding_evidence"],
        engine=ctx["engine"], candles=ctx["candles"], signals=ctx["signals"],
        decision_inputs=tuple(
            p6._decision_input_binding(signal, ctx["dataset"], ctx["candles"], ctx["protocol"])
            for signal in ctx["signals"]
        ), eligible_opportunities=p6._opportunities(ctx["candles"]),
        funding_events=ctx["funding"], observed_at_utc=p6.FIXED_TIME,
    )


def test_t20_cold_job_replay(tmp_path, monkeypatch) -> None:
    if sys.platform == "win32":
        # Windows cannot open directories for fsync (no O_DIRECTORY support);
        # CI/Linux exercises the real durability path.
        monkeypatch.setattr(
            "btc_quant_agent.publication.fsync_directory", lambda directory: None,
        )
    ctx = _context(tmp_path, monkeypatch, nonzero=False)
    spec = _job_spec(ctx)
    # A one-character output directory keeps the qualification artifact lock
    # file path under the Windows MAX_PATH limit.
    result = run_formal_job(spec, output_directory=tmp_path / "o")
    assert result.run.to_dict() == ctx["run"].to_dict()
    funding_ids = [item.evidence_id for item in result.evidence]
    assert ctx["funding_evidence"].evidence_id in funding_ids
    assert ctx["dataset"].evidence_id in funding_ids
    assert result.status()["execution"] == "DISABLED"
    again = run_formal_job(spec, output_directory=tmp_path / "o")
    assert again.run.to_dict() == result.run.to_dict()
    assert again.benchmarks.to_dict() == result.benchmarks.to_dict()
    assert again.qualification.to_dict() == result.qualification.to_dict()


# ---------------------------------------------------------------------------
# T21-T29: R05CR funding evidence-chain closure and coverage identity tests
# ---------------------------------------------------------------------------


def test_t21_evaluator_omission_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=False)
    suite = build_formal_benchmark_suite(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        candidate_run=ctx["run"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        eligible_opportunities=p6._opportunities(ctx["candles"]),
        funding_evidence=ctx["funding_evidence"],
    )
    with pytest.raises(
        ValueError, match="qualification required evidence omits bound funding evidence"
    ):
        evaluate_formal_economic_qualification(
            protocol=ctx["protocol"],
            comparison=ctx["comparison"],
            candidate_run=ctx["run"],
            benchmarks=suite,
            required_evidence_ids=(ctx["dataset"].evidence_id,),
            generated_at_utc=p6.FIXED_TIME,
        )

    qualification = evaluate_formal_economic_qualification(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        candidate_run=ctx["run"],
        benchmarks=suite,
        required_evidence_ids=(ctx["dataset"].evidence_id, ctx["funding_evidence"].evidence_id),
        generated_at_utc=p6.FIXED_TIME,
    )
    assert qualification.verdict is not None


def test_t22_direct_result_construction_omission_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=False)
    suite = build_formal_benchmark_suite(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        candidate_run=ctx["run"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        eligible_opportunities=p6._opportunities(ctx["candles"]),
        funding_evidence=ctx["funding_evidence"],
    )
    qualification = evaluate_formal_economic_qualification(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        candidate_run=ctx["run"],
        benchmarks=suite,
        required_evidence_ids=(ctx["dataset"].evidence_id, ctx["funding_evidence"].evidence_id),
        generated_at_utc=p6.FIXED_TIME,
    )
    with pytest.raises(
        ValueError, match="qualification required evidence omits bound funding evidence"
    ):
        replace(qualification, required_evidence_ids=(ctx["dataset"].evidence_id,))


def test_t23_persisted_qualification_full_rehash_omission_attack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=False)
    suite = build_formal_benchmark_suite(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        candidate_run=ctx["run"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        eligible_opportunities=p6._opportunities(ctx["candles"]),
        funding_evidence=ctx["funding_evidence"],
    )
    qualification = evaluate_formal_economic_qualification(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        candidate_run=ctx["run"],
        benchmarks=suite,
        required_evidence_ids=(ctx["dataset"].evidence_id, ctx["funding_evidence"].evidence_id),
        generated_at_utc=p6.FIXED_TIME,
    )
    payload = qualification.semantic_payload()
    assert ctx["funding_evidence"].evidence_id in payload["required_evidence_ids"]
    payload["required_evidence_ids"] = [
        eid
        for eid in payload["required_evidence_ids"]
        if eid != ctx["funding_evidence"].evidence_id
    ]
    attack_semantic = json.loads(canonical_json(payload))
    with pytest.raises(
        ValueError, match="qualification required evidence omits bound funding evidence"
    ):
        validate_persisted_qualification_semantics(
            attack_semantic, ctx["dataset"], protocol=ctx["protocol"]
        )


def test_t24_registry_atomic_omission_rejection(tmp_path: Path) -> None:
    artifacts = p6._formal_artifacts(tmp_path)
    qualification = artifacts["qualification"]
    protocol = artifacts["protocol"]
    registry, _ = p6._statistically_qualified_registry(tmp_path, protocol)

    initial_generation = registry.generation
    initial_status = registry.get_status(protocol.experiment_revision_id)
    initial_events_count = len(registry.decision_events())
    initial_bytes = registry.storage_path.read_bytes() if registry.storage_path else b""

    attestation = qualification.decision_attestation(artifacts["result_evidence"])
    with pytest.raises(EvidenceValidationError):
        registry.record_economic_qualification(
            attestation,
            evidence_references=(
                artifacts["dataset"],
                artifacts["run_evidence"],
                artifacts["suite_evidence"],
                artifacts["result_evidence"],
            ),
            reason="omitting funding evidence must fail atomically",
            actor="pytest",
            decided_at_utc=p6.FIXED_TIME,
        )

    assert registry.generation == initial_generation
    assert registry.get_status(protocol.experiment_revision_id) == initial_status
    assert len(registry.decision_events()) == initial_events_count
    assert (registry.storage_path.read_bytes() if registry.storage_path else b"") == initial_bytes


def test_t25_unrelated_complete_evidence_replacement(tmp_path: Path) -> None:
    artifacts = p6._formal_artifacts(tmp_path)
    qualification = artifacts["qualification"]
    protocol = artifacts["protocol"]
    registry, _ = p6._statistically_qualified_registry(tmp_path, protocol)

    initial_generation = registry.generation
    initial_status = registry.get_status(protocol.experiment_revision_id)
    initial_events_count = len(registry.decision_events())
    initial_bytes = registry.storage_path.read_bytes() if registry.storage_path else b""

    unrelated_file = tmp_path / "unrelated_complete_evidence.json"
    unrelated_file.write_text('{"unrelated": true}\n', encoding="utf-8")
    unrelated_evidence = EvidenceReference.from_file(
        unrelated_file,
        evidence_type="UNRELATED_EVIDENCE_TYPE",
        logical_id="unrelated-evidence",
        producing_revision_id=protocol.experiment_revision_id,
        producing_code_revision=protocol.code_revision,
        observed_at_utc=p6.FIXED_TIME,
    )

    attestation = qualification.decision_attestation(artifacts["result_evidence"])
    with pytest.raises(EvidenceValidationError):
        registry.record_economic_qualification(
            attestation,
            evidence_references=(
                artifacts["dataset"],
                unrelated_evidence,
                artifacts["run_evidence"],
                artifacts["suite_evidence"],
                artifacts["result_evidence"],
            ),
            reason="unrelated evidence replacement must fail atomically",
            actor="pytest",
            decided_at_utc=p6.FIXED_TIME,
        )

    assert registry.generation == initial_generation
    assert registry.get_status(protocol.experiment_revision_id) == initial_status
    assert len(registry.decision_events()) == initial_events_count
    assert (registry.storage_path.read_bytes() if registry.storage_path else b"") == initial_bytes


def test_t26_valid_chain_positive_control(tmp_path: Path) -> None:
    artifacts = p6._formal_artifacts(tmp_path)
    qualification = artifacts["qualification"]
    protocol = artifacts["protocol"]
    registry, _ = p6._statistically_qualified_registry(tmp_path, protocol)

    event = registry.record_economic_qualification(
        qualification.decision_attestation(artifacts["result_evidence"]),
        evidence_references=(
            artifacts["dataset"],
            artifacts["funding_evidence"],
            artifacts["run_evidence"],
            artifacts["suite_evidence"],
            artifacts["result_evidence"],
        ),
        reason="normal formal workflow positive control",
        actor="pytest",
        decided_at_utc=p6.FIXED_TIME,
    )
    assert event is not None
    assert event.new_status is DecisionStatus.ECONOMICALLY_QUALIFIED
    assert (
        registry.get_status(protocol.experiment_revision_id)
        is DecisionStatus.ECONOMICALLY_QUALIFIED
    )


def test_t27_comparison_coverage_identity_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=False)
    valid_comparison = ctx["comparison"]
    data_interval = valid_comparison.data_interval
    funding_interval = valid_comparison.funding_interval

    bad_start_funding = replace(
        funding_interval,
        coverage_start_ms=data_interval.start_ms + 1000,
    )
    with pytest.raises(
        ValueError, match="funding_interval coverage must equal data_interval"
    ):
        replace(valid_comparison, funding_interval=bad_start_funding)

    bad_end_funding = replace(
        funding_interval,
        coverage_end_ms=data_interval.end_ms + 1000,
    )
    with pytest.raises(
        ValueError, match="funding_interval coverage must equal data_interval"
    ):
        replace(valid_comparison, funding_interval=bad_end_funding)


def test_t28_loader_expected_identity_coverage_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _context(tmp_path, monkeypatch, nonzero=False)
    comparison = ctx["comparison"]
    funding_evidence = ctx["funding_evidence"]
    product = comparison.product_scope[0]
    start_ms = comparison.data_interval.start_ms
    end_ms = comparison.data_interval.end_ms
    valid_identity = comparison.funding_interval

    bad_identity_start = replace(valid_identity, coverage_start_ms=start_ms + 1000)
    with pytest.raises(
        ValueError,
        match="funding interval identity coverage differs from the expected interval",
    ):
        load_and_validate_funding_evidence(
            funding_evidence,
            expected_product=product,
            expected_start_ms=start_ms,
            expected_end_ms=end_ms,
            expected_identity=bad_identity_start,
        )

    bad_identity_end = replace(valid_identity, coverage_end_ms=end_ms + 1000)
    with pytest.raises(
        ValueError,
        match="funding interval identity coverage differs from the expected interval",
    ):
        load_and_validate_funding_evidence(
            funding_evidence,
            expected_product=product,
            expected_start_ms=start_ms,
            expected_end_ms=end_ms,
            expected_identity=bad_identity_end,
        )


def test_t29_exact_positive_coverage_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nonzero_dir = tmp_path / "nonzero"
    nonzero_dir.mkdir()
    ctx_nonzero = _context(nonzero_dir, monkeypatch, nonzero=True)
    events_nonzero = load_and_validate_funding_evidence(
        ctx_nonzero["funding_evidence"],
        expected_product=ctx_nonzero["comparison"].product_scope[0],
        expected_start_ms=ctx_nonzero["comparison"].data_interval.start_ms,
        expected_end_ms=ctx_nonzero["comparison"].data_interval.end_ms,
        expected_identity=ctx_nonzero["comparison"].funding_interval,
    )
    assert len(events_nonzero) > 0

    zero_dir = tmp_path / "zero"
    zero_dir.mkdir()
    ctx_zero = _context(zero_dir, monkeypatch, nonzero=False)
    events_zero = load_and_validate_funding_evidence(
        ctx_zero["funding_evidence"],
        expected_product=ctx_zero["comparison"].product_scope[0],
        expected_start_ms=ctx_zero["comparison"].data_interval.start_ms,
        expected_end_ms=ctx_zero["comparison"].data_interval.end_ms,
        expected_identity=ctx_zero["comparison"].funding_interval,
    )
    assert events_zero == ()
