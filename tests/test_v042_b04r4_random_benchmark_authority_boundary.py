"""v0.4.2 B04R4 acceptance repair tests: Random Benchmark Authority Boundary.

Tests T1 through T9:
- T1: Candidate random-contract substitution -> REJECT.
- T2: Direct verifier random escape attack -> REJECT.
- T3: execute_bound_run candidate with random bundle -> REJECT.
- T4: Persisted candidate + random bundle mismatch -> REJECT.
- T5: Benchmark-role artifact cannot be reused as candidate -> REJECT.
- T6: Random benchmark positive control -> PASS (identifiable as RANDOM_BENCHMARK).
- T7: Benchmark role with non-random producer rejected -> REJECT.
- T8: Normal candidate positive control -> PASS / COMPLETE.
- T9: Zero-signal/CASH unchanged -> PASS.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import test_v041_p6_metrics_benchmarks_qualification as p6

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic import (
    BenchmarkKind,
    EconomicRunRole,
    EligibleOpportunity,
    FormalBenchmarkSuite,
    InformationSignal,
    ReplayInputBundle,
    ResultCompleteness,
    SignalProducerContract,
    SignalProducerRegistry,
    build_formal_benchmark_suite,
    build_formal_replay_input_bundle,
    evaluate_formal_economic_qualification,
    execute_bound_run,
    validate_formal_replay_input_bundle,
)
from btc_quant_agent.economic.acceptance_verifier import (
    validate_persisted_decision_input_bindings,
)
from btc_quant_agent.economic.qualification import (
    _random_matched_benchmark,
    _validate_candidate_run_binding,
)
from btc_quant_agent.economic.signal_producer import _runtime_candle_payload
from btc_quant_agent.research_contract.canonical import (
    FrozenDict,
    canonical_sha256,
    thaw_json,
)


def _b04r4_context(
    tmp_path: Path,
    producer_contract: SignalProducerContract | None = None,
) -> dict[str, Any]:
    """Setup test context with protocol-bound producer contract."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    candles = list(p6._candles())
    frozen_candles: tuple[Candle, ...] = tuple(candles)
    engine = p6._zero_cost_engine()
    dataset = p6._dataset_evidence(tmp_path, frozen_candles)
    funding_evidence = p6._default_funding_evidence(dataset, frozen_candles)
    comparison = p6._comparison(
        dataset,
        frozen_candles,
        engine,
        required=(BenchmarkKind.CASH, BenchmarkKind.RANDOM_MATCHED),
        descriptive=(),
    )
    contract = producer_contract or SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    base_protocol = p6._protocol(comparison, engine)
    protocol = replace(
        base_protocol,
        signal_producer_contract=contract,
    )

    c1 = candles[1]
    direction = 1 if c1.close > c1.open else (-1 if c1.close < c1.open else 0)
    signal_time = candles[2].open_time_ms
    signal = InformationSignal(
        signal_id="B04R4-SIGNAL-1",
        experiment_id=protocol.experiment_revision_id,
        timestamp_ms=signal_time,
        direction=direction,
        strength=1.0,
    )
    return {
        "candles": frozen_candles,
        "engine": engine,
        "dataset": dataset,
        "funding_evidence": funding_evidence,
        "comparison": comparison,
        "protocol": protocol,
        "signal": signal,
        "contract": contract,
    }


def _build_candidate_bundle(
    ctx: dict[str, Any],
    contract: SignalProducerContract,
    *,
    signal: InformationSignal | None = None,
) -> ReplayInputBundle:
    target_signal = signal or ctx["signal"]
    inputs = (ctx["candles"][1],)
    open_times = [c.open_time_ms for c in inputs]
    preimage_hash = canonical_sha256([_runtime_candle_payload(c) for c in inputs])

    decision_inputs = [
        {
            "signal_id": target_signal.signal_id,
            "signal_timestamp_ms": target_signal.timestamp_ms,
            "signal_payload": target_signal.to_dict(),
            "producer_identity": contract.producer_identity,
            "producer_version": contract.producer_version,
            "producer_contract_id": contract.contract_id,
            "producer_contract_hash": contract.contract_hash,
            "observation_open_times_ms": open_times,
            "generation_contract": {
                "rule": contract.rule,
                "producer_contract_id": contract.contract_id,
                "producer_contract_hash": contract.contract_hash,
                "direction": target_signal.direction,
                "strength": target_signal.strength,
                "horizon_ms": target_signal.horizon_ms,
                "asset": target_signal.asset,
                "material_input_open_times_ms": open_times,
                "expected_preimage_sha256": preimage_hash,
            },
        }
    ]
    return build_formal_replay_input_bundle(
        protocol=ctx["protocol"],
        dataset_evidence=ctx["dataset"],
        candles=ctx["candles"],
        signals=(target_signal,),
        decision_inputs=decision_inputs,
        authority_role=EconomicRunRole.CANDIDATE,
    )


def _build_random_benchmark_bundle(
    ctx: dict[str, Any],
    *,
    signal: InformationSignal | None = None,
) -> ReplayInputBundle:
    target_signal = signal or ctx["signal"]
    inputs = (ctx["candles"][1],)
    open_times = [c.open_time_ms for c in inputs]
    preimage_hash = canonical_sha256([_runtime_candle_payload(c) for c in inputs])
    random_contract = SignalProducerRegistry.get_contract("CANONICAL_RANDOM_BENCHMARK_V1")
    assert random_contract is not None

    decision_inputs = [
        {
            "signal_id": target_signal.signal_id,
            "signal_timestamp_ms": target_signal.timestamp_ms,
            "signal_payload": target_signal.to_dict(),
            "producer_identity": "RANDOM_BENCHMARK_PRODUCER",
            "producer_version": "1.0.0",
            "producer_contract_id": "CANONICAL_RANDOM_BENCHMARK_V1",
            "observation_open_times_ms": open_times,
            "generation_contract": {
                "rule": "RANDOM_MATCHED_OPPORTUNITY",
                "producer_contract_id": "CANONICAL_RANDOM_BENCHMARK_V1",
                "direction": target_signal.direction,
                "strength": target_signal.strength,
                "horizon_ms": target_signal.horizon_ms,
                "asset": target_signal.asset,
                "material_input_open_times_ms": open_times,
                "expected_preimage_sha256": preimage_hash,
            },
        }
    ]
    return build_formal_replay_input_bundle(
        protocol=ctx["protocol"],
        dataset_evidence=ctx["dataset"],
        candles=ctx["candles"],
        signals=(target_signal,),
        decision_inputs=decision_inputs,
        authority_role=EconomicRunRole.RANDOM_BENCHMARK,
    )


# ==============================================================================
# T1 — Candidate random-contract substitution
# ==============================================================================


def test_t1_candidate_random_contract_substitution_rejected(tmp_path: Path) -> None:
    """T1: Candidate bundle construction rejects random benchmark producer contract substitution."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r4_context(tmp_path, producer_contract=contract)

    target_signal = ctx["signal"]
    inputs = (ctx["candles"][1],)
    open_times = [c.open_time_ms for c in inputs]
    preimage_hash = canonical_sha256([_runtime_candle_payload(c) for c in inputs])

    # Candidate attempts to declare CANONICAL_RANDOM_BENCHMARK_V1 in candidate role
    decision_inputs = [
        {
            "signal_id": target_signal.signal_id,
            "signal_timestamp_ms": target_signal.timestamp_ms,
            "signal_payload": target_signal.to_dict(),
            "producer_identity": "RANDOM_BENCHMARK_PRODUCER",
            "producer_version": "1.0.0",
            "producer_contract_id": "CANONICAL_RANDOM_BENCHMARK_V1",
            "observation_open_times_ms": open_times,
            "generation_contract": {
                "rule": "RANDOM_MATCHED_OPPORTUNITY",
                "producer_contract_id": "CANONICAL_RANDOM_BENCHMARK_V1",
                "direction": target_signal.direction,
                "strength": target_signal.strength,
                "horizon_ms": target_signal.horizon_ms,
                "asset": target_signal.asset,
                "material_input_open_times_ms": open_times,
                "expected_preimage_sha256": preimage_hash,
            },
        }
    ]

    with pytest.raises(
        ValueError,
        match="bundle producer contract CANONICAL_RANDOM_BENCHMARK_V1 does not match protocol-bound authoritative contract CANONICAL_RETURN_SIGN_V1",
    ):
        build_formal_replay_input_bundle(
            protocol=ctx["protocol"],
            dataset_evidence=ctx["dataset"],
            candles=ctx["candles"],
            signals=(target_signal,),
            decision_inputs=decision_inputs,
            authority_role=EconomicRunRole.CANDIDATE,
        )


# ==============================================================================
# T2 — Direct verifier random escape attack
# ==============================================================================


def test_t2_direct_verifier_random_escape_attack_rejected(tmp_path: Path) -> None:
    """T2: validate_formal_replay_input_bundle in candidate context rejects random benchmark contract."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r4_context(tmp_path, producer_contract=contract)

    # Valid random benchmark bundle
    random_bundle = _build_random_benchmark_bundle(ctx)

    # Attacker calls verifier in candidate authority context with candidate protocol
    with pytest.raises(
        ValueError,
        match="bundle producer contract CANONICAL_RANDOM_BENCHMARK_V1 does not match protocol-bound authoritative contract CANONICAL_RETURN_SIGN_V1",
    ):
        validate_formal_replay_input_bundle(
            random_bundle.to_dict(),
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(ctx["signal"],),
            expected_role=EconomicRunRole.CANDIDATE,
        )


# ==============================================================================
# T3 — execute_bound_run candidate with random bundle
# ==============================================================================


def test_t3_execute_bound_run_candidate_with_random_bundle_rejected(tmp_path: Path) -> None:
    """T3: execute_bound_run in candidate role rejects random benchmark bundle before COMPLETE evidence can be produced."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r4_context(tmp_path, producer_contract=contract)

    random_bundle = _build_random_benchmark_bundle(ctx)

    with pytest.raises(
        ValueError,
        match="bundle producer contract CANONICAL_RANDOM_BENCHMARK_V1 does not match protocol-bound authoritative contract CANONICAL_RETURN_SIGN_V1",
    ):
        execute_bound_run(
            protocol=ctx["protocol"],
            comparison=ctx["comparison"],
            dataset_evidence=ctx["dataset"],
            engine=ctx["engine"],
            candles=ctx["candles"],
            signals=(ctx["signal"],),
            replay_input_bundle=random_bundle,
            funding_evidence=ctx["funding_evidence"],
            run_role=EconomicRunRole.CANDIDATE,
        )


# ==============================================================================
# T4 — Persisted candidate + random bundle mismatch
# ==============================================================================


def test_t4_persisted_candidate_random_bundle_mismatch_rejected(tmp_path: Path) -> None:
    """T4: validate_persisted_decision_input_bindings rejects candidate run paired with random bundle."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r4_context(tmp_path, producer_contract=contract)
    valid_candidate_bundle = _build_candidate_bundle(ctx, contract)

    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=valid_candidate_bundle,
        funding_evidence=ctx["funding_evidence"],
        run_role=EconomicRunRole.CANDIDATE,
    )
    assert run.identity.completeness == ResultCompleteness.COMPLETE
    assert run.identity.run_role == EconomicRunRole.CANDIDATE

    # Attacker attaches a random benchmark bundle to the candidate run
    random_bundle = _build_random_benchmark_bundle(ctx)
    random_bundle_dict = random_bundle.to_dict()

    accounting_dict = thaw_json(run.accounting)
    accounting_dict["formal_replay_input_bundle"] = random_bundle_dict
    accounting_dict["formal_replay_input_bundle_sha256"] = random_bundle_dict["bundle_sha256"]

    identity_dict = run.identity.to_dict()
    identity_dict["replay_input_bundle_sha256"] = random_bundle_dict["bundle_sha256"]

    with pytest.raises(
        ValueError,
        match="replay input bundle producer contract CANONICAL_RANDOM_BENCHMARK_V1 mismatch with run_identity signal_producer_contract CANONICAL_RETURN_SIGN_V1",
    ):
        validate_persisted_decision_input_bindings(
            accounting_dict,
            candles=ctx["candles"],
            run_identity=identity_dict,
        )


# ==============================================================================
# T5 — Benchmark-role artifact cannot be reused as candidate
# ==============================================================================


def test_t5_benchmark_role_artifact_cannot_be_reused_as_candidate(tmp_path: Path) -> None:
    """T5: An EconomicRunResult with role RANDOM_BENCHMARK is strictly rejected when supplied as candidate_run."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r4_context(tmp_path, producer_contract=contract)

    # Valid random benchmark run produced through benchmark path
    random_bundle = _build_random_benchmark_bundle(ctx)
    benchmark_run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=random_bundle,
        funding_evidence=ctx["funding_evidence"],
        run_role=EconomicRunRole.RANDOM_BENCHMARK,
    )
    assert benchmark_run.identity.run_role == EconomicRunRole.RANDOM_BENCHMARK

    # Attempt 1: Direct validation through _validate_candidate_run_binding
    with pytest.raises(
        ValueError,
        match="candidate run cannot have role RANDOM_BENCHMARK; benchmark trial cannot authorize candidate economic qualification",
    ):
        _validate_candidate_run_binding(
            ctx["protocol"],
            ctx["comparison"],
            benchmark_run,
        )

    # Attempt 2: Through evaluate_formal_economic_qualification
    benchmarks = FormalBenchmarkSuite(
        comparison_contract_id=ctx["comparison"].contract_id,
        candidate_run_result_id=benchmark_run.result_id,
        eligible_opportunity_set_sha256=None,
        cash=None,
        passive=None,
        random=None,
    )
    with pytest.raises(
        ValueError,
        match="candidate run cannot have role RANDOM_BENCHMARK; benchmark trial cannot authorize candidate economic qualification",
    ):
        evaluate_formal_economic_qualification(
            protocol=ctx["protocol"],
            comparison=ctx["comparison"],
            candidate_run=benchmark_run,
            benchmarks=benchmarks,
            required_evidence_ids=(),
        )

    # Attempt 3: Through build_formal_benchmark_suite
    with pytest.raises(
        ValueError,
        match="candidate run cannot have role RANDOM_BENCHMARK; benchmark trial cannot authorize candidate economic qualification",
    ):
        build_formal_benchmark_suite(
            protocol=ctx["protocol"],
            comparison=ctx["comparison"],
            dataset_evidence=ctx["dataset"],
            candidate_run=benchmark_run,
            engine=ctx["engine"],
            candles=ctx["candles"],
            eligible_opportunities=(),
            funding_evidence=ctx["funding_evidence"],
        )


# ==============================================================================
# T6 — Random benchmark positive control
# ==============================================================================


def test_t6_random_benchmark_positive_control(tmp_path: Path) -> None:
    """T6: Actual RANDOM_MATCHED benchmark construction succeeds and produces runs identifiable as RANDOM_BENCHMARK."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r4_context(tmp_path, producer_contract=contract)
    candidate_bundle = _build_candidate_bundle(ctx, contract)

    candidate_run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=candidate_bundle,
        funding_evidence=ctx["funding_evidence"],
        run_role=EconomicRunRole.CANDIDATE,
    )

    c0 = ctx["candles"][0]
    opportunity = EligibleOpportunity(
        opportunity_id="OPP-1",
        timestamp_ms=ctx["signal"].timestamp_ms,
        metadata=FrozenDict({
            "decision_input_open_times_ms": (c0.open_time_ms,),
        }),
    )

    distribution = _random_matched_benchmark(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        candidate_run=candidate_run,
        engine=ctx["engine"],
        funding_evidence=ctx["funding_evidence"],
        candles=ctx["candles"],
        opportunities=(opportunity,),
        funding_events=(),
    )

    assert len(distribution.trials) == ctx["comparison"].random_trials
    for trial in distribution.trials:
        assert trial.benchmark_kind == BenchmarkKind.RANDOM_MATCHED
        trial_accounting = thaw_json(trial.accounting)
        run_identity = trial_accounting["formal_run_identity"]
        assert run_identity["run_role"] == EconomicRunRole.RANDOM_BENCHMARK.value
        assert (
            run_identity["signal_producer_contract"]["logical_id"]
            == "CANONICAL_RANDOM_BENCHMARK_V1"
        )
        # Verify deterministic replay of the trial artifact
        validate_persisted_decision_input_bindings(
            trial_accounting,
            candles=ctx["candles"],
            run_identity=run_identity,
        )


# ==============================================================================
# T7 — Benchmark role with non-random producer rejected
# ==============================================================================


def test_t7_benchmark_role_with_non_random_producer_rejected(tmp_path: Path) -> None:
    """T7: Benchmark authority context rejects non-random producer contract (e.g. CANONICAL_RETURN_SIGN_V1)."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r4_context(tmp_path, producer_contract=contract)

    target_signal = ctx["signal"]
    inputs = (ctx["candles"][1],)
    open_times = [c.open_time_ms for c in inputs]
    preimage_hash = canonical_sha256([_runtime_candle_payload(c) for c in inputs])

    # Caller passes CANONICAL_RETURN_SIGN_V1 to build_formal_replay_input_bundle with RANDOM_BENCHMARK role
    decision_inputs = [
        {
            "signal_id": target_signal.signal_id,
            "signal_timestamp_ms": target_signal.timestamp_ms,
            "signal_payload": target_signal.to_dict(),
            "producer_identity": contract.producer_identity,
            "producer_version": contract.producer_version,
            "producer_contract_id": contract.contract_id,
            "producer_contract_hash": contract.contract_hash,
            "observation_open_times_ms": open_times,
            "generation_contract": {
                "rule": contract.rule,
                "producer_contract_id": contract.contract_id,
                "producer_contract_hash": contract.contract_hash,
                "direction": target_signal.direction,
                "strength": target_signal.strength,
                "horizon_ms": target_signal.horizon_ms,
                "asset": target_signal.asset,
                "material_input_open_times_ms": open_times,
                "expected_preimage_sha256": preimage_hash,
            },
        }
    ]

    with pytest.raises(
        ValueError,
        match="benchmark role requires CANONICAL_RANDOM_BENCHMARK_V1; received CANONICAL_RETURN_SIGN_V1",
    ):
        build_formal_replay_input_bundle(
            protocol=ctx["protocol"],
            dataset_evidence=ctx["dataset"],
            candles=ctx["candles"],
            signals=(target_signal,),
            decision_inputs=decision_inputs,
            authority_role=EconomicRunRole.RANDOM_BENCHMARK,
        )

    # Also test that validate_formal_replay_input_bundle in RANDOM_BENCHMARK role rejects candidate bundle
    candidate_bundle = _build_candidate_bundle(ctx, contract)
    with pytest.raises(
        ValueError,
        match="benchmark role requires CANONICAL_RANDOM_BENCHMARK_V1 producer contract; received CANONICAL_RETURN_SIGN_V1",
    ):
        validate_formal_replay_input_bundle(
            candidate_bundle.to_dict(),
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(target_signal,),
            expected_role=EconomicRunRole.RANDOM_BENCHMARK,
        )


# ==============================================================================
# T8 — Normal candidate positive control
# ==============================================================================


def test_t8_normal_candidate_positive_control(tmp_path: Path) -> None:
    """T8: Normal protocol-bound candidate run succeeds end-to-end with CANDIDATE role and COMPLETE qualification."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r4_context(tmp_path, producer_contract=contract)
    candidate_bundle = _build_candidate_bundle(ctx, contract)

    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=candidate_bundle,
        funding_evidence=ctx["funding_evidence"],
        run_role=EconomicRunRole.CANDIDATE,
    )

    assert run.identity.completeness == ResultCompleteness.COMPLETE
    assert run.identity.run_role == EconomicRunRole.CANDIDATE
    assert run.identity.signal_producer_contract is not None
    assert run.identity.signal_producer_contract.logical_id == "CANONICAL_RETURN_SIGN_V1"

    accounting = thaw_json(run.accounting)
    validate_persisted_decision_input_bindings(
        accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )


# ==============================================================================
# T9 — Zero-signal/CASH unchanged
# ==============================================================================


def test_t9_zero_signal_cash_unchanged(tmp_path: Path) -> None:
    """T9: Legitimate zero-signal CASH run continues to qualify cleanly under CANDIDATE role without producer contract."""
    ctx = _b04r4_context(tmp_path, producer_contract=None)
    proto_without_contract = replace(ctx["protocol"], signal_producer_contract=None)

    run = execute_bound_run(
        protocol=proto_without_contract,
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(),
        replay_input_bundle=None,
        funding_evidence=ctx["funding_evidence"],
        run_role=EconomicRunRole.CANDIDATE,
    )

    assert run.identity.completeness == ResultCompleteness.COMPLETE
    assert run.identity.signal_set_sha256 == canonical_sha256([])
    assert run.identity.signal_producer_contract is None
    assert run.identity.run_role == EconomicRunRole.CANDIDATE

    accounting = thaw_json(run.accounting)
    validate_persisted_decision_input_bindings(
        accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )
