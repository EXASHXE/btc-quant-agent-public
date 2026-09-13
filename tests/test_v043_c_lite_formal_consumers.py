"""Hermetic consumer routing and cold acceptance over the immutable kernel."""

from __future__ import annotations

import importlib.util
import json
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import Mock

import pytest
import test_v041_p6_metrics_benchmarks_qualification as p6
import test_v042_b06_random_experiment_replay as b06
from helpers_v042_economic_replay import coherent_forgery, context

from btc_quant_agent import cli
from btc_quant_agent.config import AppConfig
from btc_quant_agent.data.funding import FundingEvent
from btc_quant_agent.data.resample import resample
from btc_quant_agent.economic import evaluate_formal_economic_qualification, execute_bound_run
from btc_quant_agent.economic.policy import EntryRule, OrderType
from btc_quant_agent.economic.simulator import (
    AmbiguousEntryRejectionError,
    EconomicSimulationEngine,
)
from btc_quant_agent.formal_research import (
    FormalResearchJobSpec,
    run_formal_job,
    run_formal_job_file,
    verify_formal_qualification,
)
from btc_quant_agent.publication import PublicationConflict
from btc_quant_agent.research_contract.canonical import canonical_json, canonical_sha256, thaw_json
from btc_quant_agent.service import QuantService
from btc_quant_agent.shadow import read_legacy_shadow_performance, update_formal_shadow
from btc_quant_agent.storage import Repository


def _spec(ctx):
    return FormalResearchJobSpec(
        protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
        engine=ctx["engine"], candles=ctx["candles"], signals=ctx["signals"],
        decision_inputs=tuple(p6._decision_input_binding(
            signal, ctx["dataset"], ctx["candles"], ctx["protocol"],
        ) for signal in ctx["signals"]), eligible_opportunities=p6._opportunities(ctx["candles"]),
        funding_events=ctx["funding"], observed_at_utc=p6.FIXED_TIME,
    )


def _job(tmp_path, ctx):
    spec = _spec(ctx)
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(canonical_json(spec.protocol.to_dict()), encoding="utf-8")
    payload = {
        "schema_version": "1.0.0", "protocol_path": protocol_path.name,
        "comparison": spec.comparison.semantic_payload(), "dataset_evidence": spec.dataset_evidence.to_dict(),
        "engine": {
            "policy": asdict(spec.engine.policy), "fee_model": asdict(spec.engine.fee_model),
            "execution_model": {
                "fee_model": asdict(spec.engine.execution_model.fee_model),
                "decision_latency_ms": spec.engine.execution_model.decision_latency_ms,
                "exchange_latency_ms": spec.engine.execution_model.exchange_latency_ms,
                "order_submission_latency_ms": spec.engine.execution_model.order_submission_latency_ms,
                "limit_fill_prob_on_touch": spec.engine.execution_model.limit_fill_prob_on_touch,
            },
            "funding_model": asdict(spec.engine.funding_model),
        },
        "candles": [asdict(c) for c in spec.candles],
        "signals": [s.to_dict() for s in spec.signals],
        "decision_inputs": thaw_json(spec.decision_inputs),
        "eligible_opportunities": [o.to_dict() for o in spec.eligible_opportunities],
        "funding_events": [asdict(f) for f in spec.funding_events],
        "observed_at_utc": spec.observed_at_utc,
    }
    path = tmp_path / "job.json"
    path.write_text(canonical_json(payload), encoding="utf-8")
    return path, payload


@pytest.mark.parametrize("nonzero", [False, True])
def test_t6_facade_has_exact_kernel_outputs_and_cold_idempotence(tmp_path, nonzero):
    ctx = context(tmp_path / "input", nonzero=nonzero)
    result = run_formal_job(_spec(ctx), output_directory=tmp_path / "output")
    assert result.run.to_dict() == ctx["run"].to_dict()
    assert result.benchmarks.to_dict() == ctx["suite"].to_dict()
    expected = evaluate_formal_economic_qualification(
        protocol=ctx["protocol"], comparison=ctx["comparison"], candidate_run=ctx["run"],
        benchmarks=ctx["suite"], required_evidence_ids=tuple(
            e.evidence_id for e in result.evidence[:-1]
        ), generated_at_utc=p6.FIXED_TIME,
    )
    assert result.qualification.to_dict() == expected.to_dict()
    again = run_formal_job(_spec(ctx), output_directory=tmp_path / "output")
    assert again.status() == result.status()
    assert result.status()["execution"] == "DISABLED"
    assert not result.registry_decision_recorded


@pytest.mark.parametrize("command", ["backtest", "research", "replay"])
def test_t1_t2_generic_commands_use_formal_without_service_or_legacy(tmp_path, monkeypatch, capsys, command):
    ctx = context(tmp_path / "input")
    job, _ = _job(tmp_path, ctx)
    forbidden = Mock(side_effect=AssertionError("legacy/runtime consumer called"))
    monkeypatch.setattr(cli, "_service", forbidden)
    monkeypatch.setattr(cli, "run_full_suite", forbidden)
    monkeypatch.setattr(cli.BacktestEngine, "run", forbidden)
    assert cli.main([command, "--job", str(job), "--output", str(tmp_path / "output")]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["classification"] == "FORMAL_CURRENT"
    assert status["run_result_id"] == ctx["run"].result_id
    forbidden.assert_not_called()


@pytest.mark.parametrize("command", ["backtest", "research", "replay"])
def test_t1_t2_implicit_legacy_cli_inputs_are_refused(command, monkeypatch):
    forbidden = Mock(side_effect=AssertionError("operational service created"))
    monkeypatch.setattr(cli, "_service", forbidden)
    with pytest.raises(SystemExit) as exc:
        cli.main([command, "old.csv"])
    assert exc.value.code == 2
    forbidden.assert_not_called()


def test_t3_tool_import_and_dispatch_only_formal(tmp_path, capsys):
    ctx = context(tmp_path / "input")
    job, _ = _job(tmp_path, ctx)
    source = Path(__file__).resolve().parents[1] / "tools/run_formal_research.py"
    module_spec = importlib.util.spec_from_file_location("formal_consumer_tool", source)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    assert module.run_formal_job_file is run_formal_job_file
    assert not hasattr(module, "run_full_suite")
    assert module.main(["--job", str(job), "--output", str(tmp_path / "output")]) == 0
    assert json.loads(capsys.readouterr().out)["run_result_id"] == ctx["run"].result_id


def test_t4_shadow_is_canonical_and_default_service_is_refusal(tmp_path, monkeypatch):
    ctx = context(tmp_path / "input")
    forbidden = Mock(side_effect=AssertionError("legacy shadow arithmetic called"))
    monkeypatch.setattr("btc_quant_agent.shadow.resolve_signal", forbidden)
    status = update_formal_shadow(_spec(ctx), output_directory=str(tmp_path / "output"))[0]
    assert status["run_result_id"] == ctx["run"].result_id
    assert status["consumer"] == "FORMAL_SHADOW_V1"
    service = object.__new__(QuantService)
    service.repository = Mock()
    refused = service.update_shadow()
    assert refused[0]["classification"] == "NOT_TESTABLE_FOR_NEW_PROMOTION"
    assert not service.repository.mock_calls
    forbidden.assert_not_called()


@pytest.mark.parametrize("label", ["FORMAL_CURRENT", "FORMAL_SHADOW_V1", "QUALIFIED"])
def test_t5_relabeling_legacy_rows_is_not_authority(tmp_path, label):
    ctx = context(tmp_path / "input")
    legacy_run_semantic = {"run_identity": ctx["run"].identity.to_dict(),
                           "accounting": {"total_r": 99.0, "expectancy_r": 2.0}}
    legacy_run_id = f"economic-run-result@{canonical_sha256(legacy_run_semantic)}"
    semantic = {"protocol_hash": ctx["protocol"].protocol_hash,
                "experiment_revision_id": ctx["protocol"].experiment_revision_id,
                "comparison_contract": ctx["comparison"].semantic_payload(),
                "run_result_id": legacy_run_id,
                "run_result": {"artifact_type": p6.P6_RUN_EVIDENCE_TYPE,
                               "schema_version": "1.1.0", "result_id": legacy_run_id,
                               "semantic_payload": legacy_run_semantic},
                "classification": label, "economic_version": "P6", "metrics": {"net_return_pct": 99}}
    artifact = {"schema_version": "1.1.0", "artifact_type": p6.P6_RESULT_EVIDENCE_TYPE,
                "semantic_payload": semantic,
                "result_id": f"economic-qualification@{canonical_sha256(semantic)}"}
    with pytest.raises(ValueError, match="candidate accounting/run identity binding mismatch"):
        verify_formal_qualification(artifact, protocol=ctx["protocol"], dataset_evidence=ctx["dataset"])


def _refresh(artifact):
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    p6._refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = p6._suite_result_ids(suite)
    artifact["result_id"] = f"economic-qualification@{canonical_sha256(semantic)}"


@pytest.mark.parametrize("attack", ["impossible_fill", "empty_signals", "future_liquidity",
                                  "random_clone", "traded_cash", "seed_swap"])
def test_t7_fully_rehashed_attacks_rejected_by_consumer_acceptance(tmp_path, attack):
    ctx = context(tmp_path / "input")
    result = run_formal_job(_spec(ctx), output_directory=tmp_path / "output")
    artifact = json.loads(canonical_json(result.qualification.to_dict()))
    semantic = artifact["semantic_payload"]
    suite = semantic["benchmark_suite"]
    if attack in {"impossible_fill", "empty_signals", "future_liquidity"}:
        if attack == "impossible_fill":
            forged = coherent_forgery(ctx, price=999.0)
        else:
            accounting = thaw_json(ctx["run"].accounting)
            identity = ctx["run"].identity
            if attack == "empty_signals":
                empty = execute_bound_run(
                    protocol=ctx["protocol"], comparison=ctx["comparison"],
                    dataset_evidence=ctx["dataset"], engine=ctx["engine"], candles=ctx["candles"],
                    signals=(), funding_events=ctx["funding"],
                )
                accounting = {k: v for k, v in accounting.items() if not k.startswith("formal_")}
                accounting.update({k: thaw_json(v) for k, v in empty.accounting.items()
                                   if k.startswith("formal_")})
                identity = empty.identity
            else:
                event = next(e for e in accounting["trade_events"]
                             if e["metadata"].get("causal_liquidity_volume_base"))
                event["metadata"]["causal_liquidity_available_at_ms"] = event["timestamp_ms"] + 1
            from btc_quant_agent.research_contract.canonical import FrozenDict

            forged = replace(ctx["run"], identity=identity, accounting=FrozenDict(accounting))
        semantic["run_result"] = forged.to_dict()
        semantic["run_result_id"] = forged.result_id
        suite["candidate_run_result_id"] = forged.result_id
    elif attack == "random_clone":
        b06._replace_trial(ctx, suite, b06._random_run(ctx, ctx["signals"]))
    elif attack == "traded_cash":
        suite["cash"]["accounting"] = thaw_json(ctx["run"].accounting)
    else:
        first, second = suite["random"]["trials"][:2]
        first["seed"], second["seed"] = second["seed"], first["seed"]
    _refresh(artifact)
    with pytest.raises(ValueError):
        verify_formal_qualification(artifact, protocol=ctx["protocol"], dataset_evidence=ctx["dataset"])


def test_t7_limit_intrabar_ambiguity_survives_facade(tmp_path):
    ctx = context(tmp_path / "input", nonzero=False)
    policy = replace(ctx["engine"].policy, entry_rule=EntryRule(
        order_type=OrderType.LIMIT, limit_offset_bps=5.0, time_in_force_ms=60_000,
    ))
    engine = EconomicSimulationEngine(policy=policy, fee_model=ctx["engine"].fee_model,
                                     execution_model=ctx["engine"].execution_model)
    comparison = p6._comparison(ctx["dataset"], ctx["candles"], engine)
    protocol = p6._protocol(comparison, engine)
    signals = tuple(replace(s, experiment_id=protocol.experiment_revision_id) for s in ctx["signals"])
    updated = {**ctx, "engine": engine, "comparison": comparison, "protocol": protocol,
               "signals": signals}
    with pytest.raises(AmbiguousEntryRejectionError, match="Ambiguous LIMIT entry touch ordering"):
        run_formal_job(_spec(updated), output_directory=tmp_path / "output")


def test_t4_legacy_shadow_reader_remains_legacy_and_unchanged(tmp_path):
    repository = Repository(str(tmp_path / "legacy.db"))
    repository.save_shadow("old-row", {"outcome": "WIN", "r_multiple": 2.0, "exited_at_ms": 1})
    before = (tmp_path / "legacy.db").read_bytes()
    legacy = read_legacy_shadow_performance(repository)
    assert legacy["total_r"] == 2.0
    assert "net_return_pct" not in legacy
    assert legacy["classification"] == "LEGACY_DIAGNOSTIC_ONLY"
    assert not legacy["can_promote"]
    ctx = context(tmp_path / "input")
    update_formal_shadow(_spec(ctx), output_directory=str(tmp_path / "formal"))
    assert (tmp_path / "legacy.db").read_bytes() == before


def test_t11_formal_job_does_not_enable_execution(tmp_path):
    config = AppConfig()
    before = config.execution
    result = run_formal_job(_spec(context(tmp_path / "input")), output_directory=tmp_path / "output")
    assert result.status()["execution"] == "DISABLED"
    assert config.execution == before
    assert config.execution.mode == "disabled"
    assert not config.execution.auto_execute and not config.execution.allow_live


@pytest.mark.parametrize("closed,available", [(False, True), (True, False)])
def test_t7_incomplete_availability_rejected_without_registry_mutation(tmp_path, closed, available):
    ctx = context(tmp_path / "input")
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = p6._statistically_qualified_registry(registry_dir, ctx["protocol"])
    before = registry.storage_path.read_bytes(), registry.generation
    candles = tuple(replace(c, closed=closed, available_at_ms=c.available_at_ms if available else None)
                    for c in ctx["candles"])
    with pytest.raises(ValueError):
        run_formal_job(replace(_spec(ctx), candles=candles), output_directory=tmp_path / "output",
                       registry=registry, record_decision=True)
    assert (registry.storage_path.read_bytes(), registry.generation) == before


def test_t8_type_extraction_retains_aliases_and_gap_behavior():
    from btc_quant_agent.backtest import FundingEvent as CompatibilityFundingEvent
    from btc_quant_agent.backtest import resample as compatibility_resample

    assert CompatibilityFundingEvent is FundingEvent
    assert compatibility_resample is resample
    candles = tuple(replace(c, interval="1m", open_time_ms=i * 60_000,
                            close_time_ms=(i + 1) * 60_000 - 1) for i, c in enumerate(p6._candles(16)))
    assert len(resample(candles, "15m")) == 1
    assert resample(candles[:7] + candles[8:], "15m") == []
    assert resample(candles, "15m")[0].available_at_ms is None


def test_t9_t10_cold_acceptance_failure_never_commits_registry(tmp_path, monkeypatch):
    ctx = context(tmp_path / "input")
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = p6._statistically_qualified_registry(registry_dir, ctx["protocol"])
    before = registry.storage_path.read_bytes(), registry.generation
    reject = Mock(side_effect=ValueError("injected cold verification failure"))
    monkeypatch.setattr("btc_quant_agent.formal_research.verify_formal_qualification", reject)
    with pytest.raises(ValueError, match="cold verification"):
        run_formal_job(_spec(ctx), output_directory=tmp_path / "output", registry=registry,
                       record_decision=True)
    reject.assert_called_once()
    assert (registry.storage_path.read_bytes(), registry.generation) == before


@pytest.mark.parametrize("nonzero", [False, True])
def test_t10_explicit_registry_commit_uses_existing_p5_owner(tmp_path, nonzero):
    ctx = context(tmp_path / "input", nonzero=nonzero)
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = p6._statistically_qualified_registry(registry_dir, ctx["protocol"])
    before = registry.generation
    before_events = len(registry.decision_events())
    result = run_formal_job(_spec(ctx), output_directory=tmp_path / "output", registry=registry,
                            record_decision=True)
    assert result.registry_decision_recorded is (not nonzero)
    assert registry.generation > before
    assert len(registry.decision_events()) == before_events + (0 if nonzero else 1)


@pytest.mark.parametrize("name", ["final_holdout/job.json", "h39_validation/job.json",
                                 "h39_canonical_1m_candles.sqlite3"])
def test_t12_sealed_paths_rejected_before_file_read(tmp_path, name):
    with pytest.raises(ValueError):
        FormalResearchJobSpec.load(tmp_path / name)


@pytest.mark.parametrize("field", ["closed", "available_at_ms"])
def test_loader_never_invents_candle_proof(tmp_path, field):
    ctx = context(tmp_path / "input")
    job, payload = _job(tmp_path, ctx)
    del payload["candles"][0][field]
    job.write_text(canonical_json(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="explicit closed/availability"):
        FormalResearchJobSpec.load(job)


def test_publication_does_not_overwrite_frozen_artifacts(tmp_path):
    ctx = context(tmp_path / "input")
    result = run_formal_job(_spec(ctx), output_directory=tmp_path / "output")
    path = result.directory / "candidate-run.json"
    path.write_text("frozen conflicting bytes", encoding="utf-8")
    with pytest.raises(PublicationConflict):
        run_formal_job(_spec(ctx), output_directory=tmp_path / "output")
    assert path.read_text(encoding="utf-8") == "frozen conflicting bytes"
