"""Independent canonical execution is required at candidate promotion."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
import test_v041_p6_metrics_benchmarks_qualification as p6
import test_v042_b04r4_random_benchmark_authority_boundary as r4
from helpers_v042_economic_replay import coherent_forgery, context, persisted_qualification

from btc_quant_agent.economic import EconomicRunRole, execute_bound_run
from btc_quant_agent.economic.acceptance_verifier import validate_persisted_qualification_semantics
from btc_quant_agent.economic.execution_replay import verify_execution_replay
from btc_quant_agent.economic.qualification import _validate_candidate_run_binding
from btc_quant_agent.research_contract.canonical import (
    FrozenDict,
    canonical_json,
    canonical_sha256,
    thaw_json,
)
from btc_quant_agent.research_contract.registry import EvidenceValidationError


@pytest.mark.parametrize("attack", ["price", "fee", "funding", "quantity"])
def test_b05_t1_t2_t3_t6_fully_rehashed_coherent_ledger_rejected(tmp_path: Path, attack: str) -> None:
    ctx = context(tmp_path)
    options = {
        "price": {"price": 1.0}, "fee": {"fee_delta": 2.0},
        "funding": {"funding_delta": 3.0}, "quantity": {"quantity_scale": 0.5},
    }
    forged = coherent_forgery(ctx, **options[attack])
    assert forged.result_id != ctx["run"].result_id
    with pytest.raises(ValueError, match="mismatch"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], forged)


def test_b05_t4_signal_substitution_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    identity = replace(ctx["run"].identity, signal_set_sha256=canonical_sha256([]))
    accounting = thaw_json(ctx["run"].accounting)
    accounting["formal_run_identity"] = identity.to_dict()
    forged = replace(ctx["run"], identity=identity, accounting=FrozenDict(accounting))
    with pytest.raises(ValueError, match="signal|mismatch"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], forged)


def test_b05_t5_terminal_valuation_substitution_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    accounting = thaw_json(ctx["run"].accounting)
    accounting["final_equity"] += 100.0
    forged = replace(ctx["run"], accounting=FrozenDict(accounting))
    with pytest.raises(ValueError, match="canonical replay mismatch"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], forged)


def test_b05_t7_consumed_liquidity_substitution_rejected(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    accounting = thaw_json(ctx["run"].accounting)
    event = next(item for item in accounting["trade_events"] if item["metadata"].get("causal_liquidity_volume_base"))
    event["metadata"]["causal_liquidity_volume_base"] *= 2
    forged = replace(ctx["run"], accounting=FrozenDict(accounting))
    with pytest.raises(ValueError, match="canonical replay mismatch"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], forged)


def test_b05_t8_empty_signal_evidence_stripping_cannot_retain_trades(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    empty = execute_bound_run(
        protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
        engine=ctx["engine"], candles=ctx["candles"], signals=(), funding_events=ctx["funding"],
    )
    accounting = thaw_json(ctx["run"].accounting)
    for key in list(accounting):
        if key.startswith("formal_"):
            del accounting[key]
    accounting.update({key: thaw_json(value) for key, value in empty.accounting.items() if key.startswith("formal_")})
    forged = replace(ctx["run"], identity=empty.identity, accounting=FrozenDict(accounting))
    with pytest.raises(ValueError, match="canonical replay mismatch"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], forged)


def test_b05_t9_synchronized_random_role_identity_rewrite_rejected(tmp_path: Path) -> None:
    ctx = r4._b04r4_context(tmp_path)
    random = execute_bound_run(
        protocol=ctx["protocol"], comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
        engine=ctx["engine"], candles=ctx["candles"], signals=(ctx["signal"],),
        replay_input_bundle=r4._build_random_benchmark_bundle(ctx), run_role=EconomicRunRole.RANDOM_BENCHMARK,
    )
    identity = replace(random.identity, run_role=EconomicRunRole.CANDIDATE,
                       signal_producer_contract=ctx["contract"].to_versioned_identity())
    accounting = thaw_json(random.accounting)
    accounting["formal_run_identity"] = identity.to_dict()
    forged = replace(random, identity=identity, accounting=FrozenDict(accounting))
    with pytest.raises(ValueError, match="producer contract.*mismatch"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], forged)


def test_b05_t10_nonzero_cost_funding_positive_persisted_replay(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    run = ctx["run"]
    assert run.accounting["total_fees_usdt"] > 0
    assert run.accounting["total_funding_usdt"] != 0
    reloaded = json.loads(canonical_json(run.semantic_payload()))
    actual, *_ = verify_execution_replay(reloaded, protocol=ctx["protocol"], comparison=ctx["comparison"])
    assert actual.result_id == run.result_id


def test_legacy_replay_context_missing_is_not_testable(tmp_path: Path) -> None:
    ctx = context(tmp_path)
    accounting = thaw_json(ctx["run"].accounting)
    del accounting["formal_execution_replay_inputs"]
    forged = replace(ctx["run"], accounting=FrozenDict(accounting))
    with pytest.raises(ValueError, match="NOT_TESTABLE"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], forged)


def test_nonzero_cost_funding_candidate_can_be_promoted(tmp_path: Path) -> None:
    artifacts = persisted_qualification(context(tmp_path), tmp_path)
    registry, _ = p6._statistically_qualified_registry(tmp_path, artifacts["protocol"])
    generation = registry.generation
    registry.record_economic_qualification(
        artifacts["qualification"].decision_attestation(artifacts["result_evidence"]),
        evidence_references=tuple(artifacts[name] for name in (
            "dataset", "run_evidence", "suite_evidence", "result_evidence",
        )), reason="canonical nonzero fee and funding replay", actor="pytest",
        decided_at_utc=p6.FIXED_TIME,
    )
    assert registry.generation == generation + 1


def test_fully_rehashed_impossible_price_registry_attack_is_atomic(tmp_path: Path) -> None:
    artifacts = p6._formal_artifacts(tmp_path / "base")
    ctx = {**artifacts, "run": artifacts["run"]}
    forged = coherent_forgery(ctx, price=1.0)
    artifact = json.loads(canonical_json(artifacts["qualification"].to_dict()))
    semantic = artifact["semantic_payload"]
    semantic["run_result"] = forged.to_dict()
    semantic["run_result_id"] = forged.result_id
    semantic["metric_values"]["net_return_pct"] = forged.accounting["net_return_pct"]
    semantic["gates"][0]["observed_value"] = forged.accounting["net_return_pct"]
    suite = semantic["benchmark_suite"]
    suite["candidate_run_result_id"] = forged.result_id
    p6._refresh_suite_identity(suite)
    semantic["benchmark_suite_id"] = suite["suite_id"]
    semantic["benchmark_result_ids"] = p6._suite_result_ids(suite)
    with pytest.raises(ValueError, match="mismatch"):
        validate_persisted_qualification_semantics(semantic, artifacts["dataset"], protocol=artifacts["protocol"])
    forged_dir = tmp_path / "forged"
    forged_dir.mkdir()
    attestation, evidence = p6._write_forged_registry_artifacts(
        forged_dir, artifacts, artifact, run_changed=True, suite_changed=True,
    )
    registry_dir = tmp_path / "registry"
    registry_dir.mkdir()
    registry, _ = p6._statistically_qualified_registry(registry_dir, artifacts["protocol"])
    before = registry.storage_path.read_bytes()
    generation = registry.generation
    with pytest.raises(EvidenceValidationError, match="semantic replay.*mismatch"):
        registry.record_economic_qualification(attestation, evidence_references=evidence,
                                               reason="impossible fully rehashed fill", actor="pytest")
    assert registry.generation == generation
    assert registry.storage_path.read_bytes() == before
