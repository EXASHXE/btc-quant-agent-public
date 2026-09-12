"""v0.4.2 B04R3 acceptance repair tests: protocol producer contract fail-closed.

Tests T1 through T7:
- T1: Missing protocol contract + valid registered bundle contract -> REJECT.
- T2: Direct verifier bypass attack -> REJECT.
- T3: execute_bound_run non-empty signal without protocol producer contract -> REJECT.
- T4: Persisted COMPLETE artifact strips run-identity producer contract -> REJECT.
- T5: Bundle cannot backfill missing run authority -> REJECT.
- T6: Zero-signal CASH positive control -> PASS.
- T7: Normal protocol-bound candidate positive control -> PASS / COMPLETE.
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
    InformationSignal,
    ReplayInputBundle,
    ResultCompleteness,
    SignalProducerContract,
    SignalProducerRegistry,
    build_formal_replay_input_bundle,
    execute_bound_run,
    validate_formal_replay_input_bundle,
)
from btc_quant_agent.economic.acceptance_verifier import (
    validate_persisted_decision_input_bindings,
)
from btc_quant_agent.economic.signal_producer import _runtime_candle_payload
from btc_quant_agent.research_contract.canonical import canonical_sha256, thaw_json


def _b04r3_context(
    tmp_path: Path,
    producer_contract: SignalProducerContract | None = None,
) -> dict[str, Any]:
    """Setup test context with optional protocol-bound producer contract."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    candles = list(p6._candles())
    frozen_candles: tuple[Candle, ...] = tuple(candles)
    engine = p6._zero_cost_engine()
    dataset = p6._dataset_evidence(tmp_path, frozen_candles)
    comparison = p6._comparison(
        dataset,
        frozen_candles,
        engine,
        required=(BenchmarkKind.CASH,),
        descriptive=(),
    )
    base_protocol = p6._protocol(comparison, engine)
    protocol = replace(
        base_protocol,
        signal_producer_contract=producer_contract,
    )

    c1 = candles[1]
    direction = 1 if c1.close > c1.open else (-1 if c1.close < c1.open else 0)
    signal_time = candles[2].open_time_ms
    signal = InformationSignal(
        signal_id="B04R3-SIGNAL-1",
        experiment_id=protocol.experiment_revision_id,
        timestamp_ms=signal_time,
        direction=direction,
        strength=1.0,
    )
    return {
        "candles": frozen_candles,
        "engine": engine,
        "dataset": dataset,
        "comparison": comparison,
        "protocol": protocol,
        "signal": signal,
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
    )


# ==============================================================================
# T1 — Missing protocol contract + valid registered bundle contract
# ==============================================================================


def test_t1_missing_protocol_contract_with_valid_bundle_contract_rejected(
    tmp_path: Path,
) -> None:
    """T1: Protocol without signal_producer_contract cannot build bundle even with valid registered contract."""
    ctx = _b04r3_context(tmp_path, producer_contract=None)
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None

    with pytest.raises(
        ValueError,
        match="bundle producer contract CANONICAL_RETURN_SIGN_V1 cannot be authorized by candidate",
    ):
        _build_candidate_bundle(ctx, contract)


# ==============================================================================
# T2 — Direct verifier bypass attack
# ==============================================================================


def test_t2_direct_verifier_bypass_attack_rejected(tmp_path: Path) -> None:
    """T2: validate_formal_replay_input_bundle rejects when expected_protocol has no signal_producer_contract."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx_valid = _b04r3_context(tmp_path, producer_contract=contract)
    valid_bundle = _build_candidate_bundle(ctx_valid, contract)

    # Attacker synthesizes an internally valid bundle referencing a valid registry contract
    # but claiming to be bound to a protocol that lacks signal_producer_contract
    protocol_without_contract = replace(ctx_valid["protocol"], signal_producer_contract=None)
    bundle_dict = valid_bundle.to_dict()
    bundle_dict["experiment_revision_id"] = protocol_without_contract.experiment_revision_id
    bundle_dict["protocol_hash"] = protocol_without_contract.protocol_hash
    semantic_payload = {k: bundle_dict[k] for k in bundle_dict if k != "bundle_sha256"}
    bundle_dict["bundle_sha256"] = canonical_sha256(semantic_payload)

    with pytest.raises(
        ValueError,
        match="lacks required signal_producer_contract for non-empty decision inputs",
    ):
        validate_formal_replay_input_bundle(
            bundle_dict,
            candles=ctx_valid["candles"],
            expected_protocol=protocol_without_contract,
            expected_dataset_evidence=ctx_valid["dataset"],
            expected_signals=(ctx_valid["signal"],),
        )


# ==============================================================================
# T3 — execute_bound_run non-empty signal without protocol producer contract
# ==============================================================================


def test_t3_execute_bound_run_missing_protocol_contract_rejected(
    tmp_path: Path,
) -> None:
    """T3: execute_bound_run fails closed before economic qualification if protocol lacks producer contract."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx_valid = _b04r3_context(tmp_path, producer_contract=contract)
    valid_bundle = _build_candidate_bundle(ctx_valid, contract)

    protocol_without_contract = replace(ctx_valid["protocol"], signal_producer_contract=None)
    sig = replace(
        ctx_valid["signal"],
        experiment_id=protocol_without_contract.experiment_revision_id,
    )

    with pytest.raises(
        ValueError,
        match="formal run with signals requires protocol.signal_producer_contract",
    ):
        execute_bound_run(
            protocol=protocol_without_contract,
            comparison=ctx_valid["comparison"],
            dataset_evidence=ctx_valid["dataset"],
            engine=ctx_valid["engine"],
            candles=ctx_valid["candles"],
            signals=(sig,),
            replay_input_bundle=valid_bundle,
        )


# ==============================================================================
# T4 — Persisted COMPLETE artifact strips run-identity producer contract
# ==============================================================================


def test_t4_persisted_complete_artifact_strips_run_identity_contract_rejected(
    tmp_path: Path,
) -> None:
    """T4: Persisted verifier rejects COMPLETE run with signals if signal_producer_contract is stripped from run_identity."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r3_context(tmp_path, producer_contract=contract)
    bundle = _build_candidate_bundle(ctx, contract)

    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
    )
    assert run.identity.completeness == ResultCompleteness.COMPLETE

    identity_dict = run.identity.to_dict()
    assert "signal_producer_contract" in identity_dict
    del identity_dict["signal_producer_contract"]

    accounting_dict = thaw_json(run.accounting)
    with pytest.raises(
        ValueError,
        match="persisted candidate claims COMPLETE with signals but lacks signal_producer_contract in run_identity",
    ):
        validate_persisted_decision_input_bindings(
            accounting_dict,
            candles=ctx["candles"],
            run_identity=identity_dict,
        )


# ==============================================================================
# T5 — Bundle cannot backfill missing run authority
# ==============================================================================


def test_t5_bundle_cannot_backfill_missing_run_authority(tmp_path: Path) -> None:
    """T5: Valid bundle referencing registered contract cannot substitute for missing run_identity producer contract."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r3_context(tmp_path, producer_contract=contract)
    bundle = _build_candidate_bundle(ctx, contract)

    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
    )
    identity_dict = run.identity.to_dict()
    identity_dict["signal_producer_contract"] = None

    accounting_dict = thaw_json(run.accounting)
    assert accounting_dict["formal_replay_input_bundle"]["decision_inputs"][0]["producer_contract_id"] == contract.contract_id

    with pytest.raises(
        ValueError,
        match="persisted candidate claims COMPLETE with signals but lacks signal_producer_contract in run_identity",
    ):
        validate_persisted_decision_input_bindings(
            accounting_dict,
            candles=ctx["candles"],
            run_identity=identity_dict,
        )


# ==============================================================================
# T6 — Zero-signal positive control
# ==============================================================================


def test_t6_zero_signal_positive_control(tmp_path: Path) -> None:
    """T6: Legitimate CASH / zero-signal COMPLETE run succeeds without signal_producer_contract."""
    ctx = _b04r3_context(tmp_path, producer_contract=None)
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(),
        replay_input_bundle=None,
    )
    assert run.identity.completeness == ResultCompleteness.COMPLETE
    assert run.identity.signal_set_sha256 == canonical_sha256([])
    assert run.identity.signal_producer_contract is None

    # Persisted validation passes for legitimate zero-signal run
    validate_persisted_decision_input_bindings(
        run.accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )


# ==============================================================================
# T7 — Normal protocol-bound candidate positive control
# ==============================================================================


def test_t7_normal_protocol_bound_candidate_positive_control(tmp_path: Path) -> None:
    """T7: Protocol-bound candidate with CANONICAL_RETURN_SIGN_V1 succeeds end-to-end."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert contract is not None
    ctx = _b04r3_context(tmp_path, producer_contract=contract)
    bundle = _build_candidate_bundle(ctx, contract)

    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
    )
    assert run.identity.completeness == ResultCompleteness.COMPLETE
    assert run.identity.signal_producer_contract is not None
    assert run.identity.signal_producer_contract.logical_id == contract.contract_id

    # Persisted validation passes cleanly
    validate_persisted_decision_input_bindings(
        run.accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )
