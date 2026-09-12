"""Seed labels cannot substitute for reconstruction of the full random experiment."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import test_v041_p6_metrics_benchmarks_qualification as p6
from helpers_v042_economic_replay import assert_registry_rejects_atomic, coherent_forgery, context

from btc_quant_agent.economic import (
    EconomicRunRole, EligibleOpportunity, InformationSignal, SignalProducerRegistry,
    build_formal_replay_input_bundle, execute_bound_run,
)
from btc_quant_agent.economic.execution_replay import verify_benchmark_replay
from btc_quant_agent.economic.qualification import (
    EconomicRunResult, _matching_diagnostics, _random_matched_benchmark,
)
from btc_quant_agent.research_contract.canonical import FrozenDict, canonical_json, canonical_sha256, thaw_json


def _verify(ctx, suite):
    verify_benchmark_replay(ctx["run"].semantic_payload(), suite,
                            protocol=ctx["protocol"], comparison=ctx["comparison"])


def _random_run(ctx, signals):
    bundle = build_formal_replay_input_bundle(
        protocol=ctx["protocol"], dataset_evidence=ctx["dataset"], candles=ctx["candles"],
        signals=signals, decision_inputs=tuple(
            p6._decision_input_binding(signal, ctx["dataset"], ctx["candles"], ctx["protocol"])
            for signal in signals
        ), funding_events=ctx["funding"], authority_role=EconomicRunRole.RANDOM_BENCHMARK,
    )
    return execute_bound_run(
        protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
        engine=ctx["engine"], candles=ctx["candles"], signals=signals, replay_input_bundle=bundle,
        funding_events=ctx["funding"], run_role=EconomicRunRole.RANDOM_BENCHMARK,
    )


def _replace_trial(ctx, suite, run):
    trial = suite["random"]["trials"][0]
    diagnostics, comparable = _matching_diagnostics(ctx["run"], run, ctx["comparison"].matching_rules)
    trial.update(accounting=thaw_json(run.accounting), run_result_id=run.result_id,
                 matching_diagnostics=diagnostics, comparable=comparable)
    returns = [item["accounting"]["net_return_pct"] for item in suite["random"]["trials"]]
    suite["random"]["aggregate"] = dict(mean_net_return_pct=sum(returns) / len(returns),
                                       minimum_net_return_pct=min(returns), maximum_net_return_pct=max(returns))
    suite["random"]["comparable"] = all(item["comparable"] for item in suite["random"]["trials"])
    p6._refresh_suite_identity(suite)


def test_b06_t1_candidate_cloned_random_trial_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    suite = ctx["suite"].to_dict()
    clone = _random_run(ctx, ctx["signals"])
    _replace_trial(ctx, suite, clone)
    with pytest.raises(ValueError, match="random experiment canonical replay mismatch"):
        _verify(ctx, suite)


def test_b06_t2_post_hoc_sample_substitution_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    suite = ctx["suite"].to_dict()
    signals = tuple(replace(signal, timestamp_ms=ctx["candles"][i].open_time_ms, signal_id=f"POSTHOC-{i}")
                    for i, signal in zip((2, 5), ctx["signals"], strict=True))
    _replace_trial(ctx, suite, _random_run(ctx, signals))
    with pytest.raises(ValueError, match="random experiment canonical replay mismatch"):
        _verify(ctx, suite)


def test_b06_t3_opportunity_metadata_tamper_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    suite = ctx["suite"].to_dict()
    provenance = suite["random"]["provenance"]
    provenance["opportunities"][0]["metadata"]["decision_input_open_times_ms"] = [ctx["candles"][2].open_time_ms]
    provenance["opportunity_set_sha256"] = canonical_sha256(provenance["opportunities"])
    p6._refresh_suite_identity(suite)
    with pytest.raises(ValueError, match="frozen comparison"):
        _verify(ctx, suite)


def test_b06_t4_trial_seed_reassignment_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    suite = ctx["suite"].to_dict()
    first, second = suite["random"]["trials"][:2]
    first["seed"], second["seed"] = second["seed"], first["seed"]
    p6._refresh_suite_identity(suite)
    with pytest.raises(ValueError, match="random experiment canonical replay mismatch"):
        _verify(ctx, suite)


def test_b06_t5_direction_permutation_substitution_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    suite = ctx["suite"].to_dict()
    entries = suite["random"]["trials"][0]["accounting"]["formal_replay_input_bundle"]["decision_inputs"]
    signals = tuple(replace(InformationSignal.from_dict(item["signal_payload"]),
                            direction=-item["signal_payload"]["direction"]) for item in entries)
    _replace_trial(ctx, suite, _random_run(ctx, signals))
    with pytest.raises(ValueError, match="random experiment canonical replay mismatch"):
        _verify(ctx, suite)


def test_b06_t6_equal_timestamp_insertion_order_is_semantically_stable(tmp_path: Path) -> None:
    candles = p6._candles()
    opportunities = tuple(EligibleOpportunity(
        name, candles[2].open_time_ms,
        FrozenDict({"decision_input_open_times_ms": (candles[0].open_time_ms,)}),
    ) for name in ("C", "A", "B"))
    ctx = context(tmp_path, nonzero=False, opportunities=opportunities)
    expected = ctx["suite"].random.to_dict()
    actual = _random_matched_benchmark(
        ctx["protocol"], ctx["comparison"], ctx["dataset"], ctx["run"], ctx["engine"],
        ctx["candles"], tuple(reversed(opportunities)), ctx["funding"],
    )
    assert actual.to_dict() == expected
    _verify(ctx, ctx["suite"].to_dict())


def test_b06_t7_correct_draw_with_fully_rehashed_execution_tamper_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    suite = ctx["suite"].to_dict()
    accounting = suite["random"]["trials"][0]["accounting"]
    raw = accounting["formal_run_identity"]
    contract = SignalProducerRegistry.get_contract("CANONICAL_RANDOM_BENCHMARK_V1")
    identity = replace(ctx["run"].identity, run_role=EconomicRunRole.RANDOM_BENCHMARK,
                       signal_producer_contract=contract.to_versioned_identity(),
                       signal_set_sha256=raw["signal_set_sha256"],
                       decision_input_set_sha256=raw["decision_input_set_sha256"],
                       replay_input_bundle_sha256=raw["replay_input_bundle_sha256"])
    trial = EconomicRunResult(identity, FrozenDict(accounting))
    forged = coherent_forgery({**ctx, "run": trial}, fee_delta=2.0)
    _replace_trial(ctx, suite, forged)
    with pytest.raises(ValueError, match="random experiment canonical replay mismatch"):
        _verify(ctx, suite)


@pytest.mark.parametrize("count,trials", [(8, 4), (32, 12)])
def test_b06_t8_t9_fixed_and_larger_positive_replay(tmp_path: Path, count: int, trials: int) -> None:
    ctx = context(tmp_path, count=count, trials=trials)
    _verify(ctx, ctx["suite"].to_dict())
    again = _random_matched_benchmark(
        ctx["protocol"], ctx["comparison"], ctx["dataset"], ctx["run"], ctx["engine"],
        ctx["candles"], p6._opportunities(ctx["candles"]), ctx["funding"],
    )
    assert again.to_dict() == ctx["suite"].random.to_dict()


def test_random_seed_reassignment_cannot_mutate_registry(tmp_path: Path) -> None:
    import json

    artifacts = p6._formal_artifacts(tmp_path / "base")
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    trials = artifact["semantic_payload"]["benchmark_suite"]["random"]["trials"]
    trials[0]["seed"], trials[1]["seed"] = trials[1]["seed"], trials[0]["seed"]
    assert_registry_rejects_atomic(tmp_path, artifacts, artifact, "semantic replay")
