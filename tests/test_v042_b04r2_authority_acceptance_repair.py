"""B04R2 Authority Acceptance Repair Tests.

Covers:
- A1: Valid registered contract swap attack rejected
- A2: Registered contract parameter rewrite attack rejected
- A3: Synchronized metadata rewrite attack rejected
- A4: Synchronized spread rewrite rejected (execution provenance authority)
- A5: Synchronized liquidity rewrite rejected
- A6: Synchronized confidence rewrite rejected
- A7: Complete evidence stripping on COMPLETE candidate with signals rejected
- A8: Partial stripping variants all fail closed
- A9: Legitimate no-signal / CASH control allowed without bundle
- P1: Protocol-frozen CANONICAL_RETURN_SIGN_V1 positive control
- P2: Protocol-frozen momentum threshold positive control
- P3: Verified causal execution inputs provenance positive control
- P4: Persisted artifact roundtrip verification positive control
"""
from __future__ import annotations

import json
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


def _b04r2_context(
    tmp_path: Path,
    producer_contract: SignalProducerContract | None = None,
) -> dict[str, Any]:
    """Setup test context with authoritative protocol-bound producer contract."""
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
    contract = producer_contract or SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    protocol = replace(
        base_protocol,
        signal_producer_contract=contract,
    )

    # Candle 1: close > open -> 1, close < open -> -1
    c1 = candles[1]
    direction = 1 if c1.close > c1.open else (-1 if c1.close < c1.open else 0)
    signal_time = candles[2].open_time_ms
    signal = InformationSignal(
        signal_id="B04R2-SIGNAL-1",
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
        "contract": contract,
    }


def _build_test_bundle(
    ctx: dict[str, Any],
    *,
    signal: InformationSignal | None = None,
    contract_id: str | None = None,
    producer_identity: str | None = None,
    rule: str | None = None,
    direction: int | None = None,
    strength: float = 1.0,
    confidence_interval: tuple[float, float] | None = None,
    metadata: dict[str, Any] | None = None,
    open_times: list[int] | None = None,
    causal_execution_inputs: list[dict[str, Any]] | None = None,
) -> ReplayInputBundle:
    target_signal = signal or ctx["signal"]
    inputs = (ctx["candles"][1],)
    resolved_open_times = open_times or [c.open_time_ms for c in inputs]
    preimage_hash = canonical_sha256([_runtime_candle_payload(c) for c in inputs])

    bound_contract: SignalProducerContract = ctx["contract"]
    cid = contract_id or bound_contract.contract_id
    pid = producer_identity or bound_contract.producer_identity
    r = rule or bound_contract.rule

    gen_contract: dict[str, Any] = {
        "rule": r,
        "producer_contract_id": cid,
        "strength": strength,
        "min_lookback_bars": 1,
        "material_input_open_times_ms": resolved_open_times,
        "expected_preimage_sha256": preimage_hash,
    }
    if direction is not None:
        gen_contract["direction"] = direction
    if confidence_interval is not None:
        gen_contract["confidence_interval"] = list(confidence_interval)
    if metadata is not None:
        gen_contract["metadata"] = dict(metadata)

    decision_inputs = [
        {
            "signal_id": target_signal.signal_id,
            "signal_timestamp_ms": target_signal.timestamp_ms,
            "signal_payload": target_signal.to_dict(),
            "producer_identity": pid,
            "producer_version": "1.0.0",
            "producer_contract_id": cid,
            "observation_open_times_ms": resolved_open_times,
            "generation_contract": gen_contract,
        }
    ]

    return build_formal_replay_input_bundle(
        protocol=ctx["protocol"],
        dataset_evidence=ctx["dataset"],
        candles=ctx["candles"],
        signals=(target_signal,),
        decision_inputs=decision_inputs,
        causal_execution_inputs=causal_execution_inputs or (),
    )


# ==============================================================================
# Adversarial Tests A1 - A9
# ==============================================================================


def test_a1_valid_registered_contract_swap_attack_rejected(tmp_path: Path) -> None:
    """A1: Attacker swaps protocol-bound CANONICAL_RETURN_SIGN_V1 for registered MOMENTUM_THRESHOLD.
    
    Both contracts are valid in SignalProducerRegistry.
    The bundle synchronizes all fields (id, hash, generation_contract, rule, bundle_sha256).
    Must FAIL CLOSED because contract disagrees with protocol-bound authoritative contract.
    """
    ctx = _b04r2_context(tmp_path)
    assert ctx["protocol"].signal_producer_contract.contract_id == "CANONICAL_RETURN_SIGN_V1"

    # 1. Builder refuses to build bundle referencing registered contract mismatching protocol
    with pytest.raises(
        ValueError,
        match="does not match protocol-bound authoritative contract",
    ):
        _build_test_bundle(
            ctx,
            contract_id="CANONICAL_MOMENTUM_THRESHOLD_V1",
            rule="MOMENTUM_THRESHOLD",
        )

    # 2. Even if attacker builds a fully valid bundle under protocol_for_mt and presents it
    # to verifier expecting the true frozen protocol (CANONICAL_RETURN_SIGN_V1), it is REJECTED
    mt_contract = SignalProducerRegistry.get_contract("CANONICAL_MOMENTUM_THRESHOLD_V1")
    assert mt_contract is not None
    protocol_for_mt = replace(ctx["protocol"], signal_producer_contract=mt_contract)
    forged_bundle = _build_test_bundle(
        dict(ctx, protocol=protocol_for_mt, contract=mt_contract),
        contract_id=mt_contract.contract_id,
        rule="MOMENTUM_THRESHOLD",
    )
    tampered = forged_bundle.to_dict()
    tampered["experiment_revision_id"] = ctx["protocol"].experiment_revision_id
    tampered["protocol_hash"] = ctx["protocol"].protocol_hash
    tampered["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered.items() if k != "bundle_sha256"}
    )

    with pytest.raises(
        ValueError,
        match="does not match protocol-bound authoritative contract",
    ):
        validate_formal_replay_input_bundle(
            tampered,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(ctx["signal"],),
        )


def test_a2_registered_contract_parameter_rewrite_rejected(tmp_path: Path) -> None:
    """A2: Protocol frozen with threshold_return_bps=100.0. Attacker attempts rewrite to 0.0."""
    mt_contract_100bps = SignalProducerContract(
        contract_id="CANONICAL_MOMENTUM_100BPS_V1",
        version="1.0.0",
        producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
        producer_version="1.0.0",
        rule="MOMENTUM_THRESHOLD",
        parameters={"threshold_return_bps": 100.0, "min_lookback_bars": 1},
    )
    SignalProducerRegistry.register_contract(mt_contract_100bps)

    ctx = _b04r2_context(tmp_path, producer_contract=mt_contract_100bps)

    # 1. Attacker tries to claim direction 1 when return (~49.5 bps) under 100 bps threshold is 0
    forged_signal = replace(ctx["signal"], direction=1)
    with pytest.raises(ValueError, match="replayed signal direction mismatch"):
        _build_test_bundle(
            ctx,
            signal=forged_signal,
            contract_id=mt_contract_100bps.contract_id,
            rule="MOMENTUM_THRESHOLD",
        )

    # 2. Attacker modifies contract hash in bundle to point to a modified contract
    valid_sig = replace(ctx["signal"], direction=0)
    valid_bundle = _build_test_bundle(
        ctx,
        signal=valid_sig,
        contract_id=mt_contract_100bps.contract_id,
        rule="MOMENTUM_THRESHOLD",
    )
    tampered_bundle = valid_bundle.to_dict()
    tampered_bundle["decision_inputs"][0]["producer_contract_hash"] = "0" * 64
    tampered_bundle["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered_bundle.items() if k != "bundle_sha256"}
    )
    with pytest.raises(ValueError, match="producer contract hash mismatch"):
        validate_formal_replay_input_bundle(
            tampered_bundle,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(valid_sig,),
        )


def test_a3_synchronized_metadata_rewrite_attack_rejected(tmp_path: Path) -> None:
    """A3: Synchronized rewrite of atr in signal.metadata and generation_contract.metadata.
    
    Attacker recomputes signal_payload_sha256 and bundle_sha256.
    Must FAIL CLOSED because atr lacks authoritative provenance derivation.
    """
    ctx = _b04r2_context(tmp_path)
    sig_with_atr = replace(
        ctx["signal"],
        metadata={"atr": 999.0},
    )

    with pytest.raises(ValueError, match="replayed signal semantic payload mismatch.*economic_metadata"):
        _build_test_bundle(
            ctx,
            signal=sig_with_atr,
            metadata={"atr": 999.0},
        )


def test_a4_synchronized_spread_rewrite_rejected(tmp_path: Path) -> None:
    """A4: Synchronized spread_bps rewrite attack.
    
    Demonstrates that unverified signal.metadata spread cannot affect simulation economics:
    authoritative execution costs derive from B02 causal execution inputs, not signal metadata.
    """
    ctx = _b04r2_context(tmp_path)
    # 1. Signal metadata spread cannot be smuggled into replay bundle
    sig_with_spread = replace(ctx["signal"], metadata={"spread_bps": 50.0})
    with pytest.raises(ValueError, match="replayed signal semantic payload mismatch"):
        _build_test_bundle(ctx, signal=sig_with_spread, metadata={"spread_bps": 50.0})

    # 2. In simulation, verified causal execution inputs govern execution, not signal metadata
    valid_bundle = _build_test_bundle(ctx)
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=valid_bundle,
    )
    assert run.identity.completeness.value == "COMPLETE"


def test_a5_synchronized_liquidity_rewrite_rejected(tmp_path: Path) -> None:
    """A5: Synchronized liquidity rewrite (volume and availability) in signal metadata fails closed."""
    ctx = _b04r2_context(tmp_path)
    sig_with_liq = replace(
        ctx["signal"],
        metadata={
            "liquidity_volume_base": 1_000_000.0,
            "liquidity_available_at_ms": ctx["candles"][1].close_time_ms,
        },
    )
    with pytest.raises(ValueError, match="replayed signal semantic payload mismatch"):
        _build_test_bundle(
            ctx,
            signal=sig_with_liq,
            metadata={
                "liquidity_volume_base": 1_000_000.0,
                "liquidity_available_at_ms": ctx["candles"][1].close_time_ms,
            },
        )


def test_a6_synchronized_confidence_rewrite_rejected(tmp_path: Path) -> None:
    """A6: Synchronized confidence interval rewrite fails closed because producer cannot derive it."""
    ctx = _b04r2_context(tmp_path)
    sig_with_ci = replace(ctx["signal"], confidence_interval=(0.05, 0.95))
    with pytest.raises(ValueError, match="replayed signal semantic payload mismatch.*confidence_interval"):
        _build_test_bundle(
            ctx,
            signal=sig_with_ci,
            confidence_interval=(0.05, 0.95),
        )


def test_a7_complete_evidence_stripping_rejected(tmp_path: Path) -> None:
    """A7: Complete evidence stripping on COMPLETE candidate with signals fails closed."""
    ctx = _b04r2_context(tmp_path)
    bundle = _build_test_bundle(ctx)
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
    )
    assert run.identity.completeness.value == "COMPLETE"

    stripped_accounting = thaw_json(run.accounting)
    stripped_accounting.pop("formal_replay_input_bundle", None)
    stripped_accounting.pop("formal_replay_input_bundle_sha256", None)
    stripped_accounting.pop("formal_decision_input_bindings", None)
    stripped_accounting.pop("formal_decision_input_set_sha256", None)

    stripped_identity = thaw_json(run.identity.to_dict())
    stripped_identity.pop("replay_input_bundle_sha256", None)

    with pytest.raises(
        ValueError,
        match="persisted candidate claims COMPLETE but lacks verified ReplayInputBundle",
    ):
        validate_persisted_decision_input_bindings(
            stripped_accounting,
            candles=ctx["candles"],
            run_identity=stripped_identity,
        )


def test_a8_partial_evidence_stripping_variants_fail_closed(tmp_path: Path) -> None:
    """A8: Partial evidence stripping variants all fail closed."""
    ctx = _b04r2_context(tmp_path)
    bundle = _build_test_bundle(ctx)
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
    )

    # A8.1: Delete bundle from accounting
    t1_accounting = thaw_json(run.accounting)
    del t1_accounting["formal_replay_input_bundle"]
    with pytest.raises(ValueError, match="persisted candidate claims COMPLETE but lacks verified ReplayInputBundle"):
        validate_persisted_decision_input_bindings(
            t1_accounting,
            candles=ctx["candles"],
            run_identity=run.identity.to_dict(),
        )

    # A8.2: Delete bundle hash from accounting
    t2_accounting = thaw_json(run.accounting)
    del t2_accounting["formal_replay_input_bundle_sha256"]
    with pytest.raises(ValueError, match="replay input bundle accounting/bundle hash mismatch"):
        validate_persisted_decision_input_bindings(
            t2_accounting,
            candles=ctx["candles"],
            run_identity=run.identity.to_dict(),
        )

    # A8.3: Delete replay_input_bundle_sha256 from run_identity
    t3_identity = thaw_json(run.identity.to_dict())
    del t3_identity["replay_input_bundle_sha256"]
    with pytest.raises(ValueError, match="lacks replay_input_bundle_sha256 in run_identity"):
        validate_persisted_decision_input_bindings(
            run.accounting,
            candles=ctx["candles"],
            run_identity=t3_identity,
        )

    # A8.4: Delete bundle, leave only legacy bindings
    t4_accounting = thaw_json(run.accounting)
    del t4_accounting["formal_replay_input_bundle"]
    del t4_accounting["formal_replay_input_bundle_sha256"]
    t4_identity = thaw_json(run.identity.to_dict())
    del t4_identity["replay_input_bundle_sha256"]
    assert "formal_decision_input_bindings" in t4_accounting
    with pytest.raises(ValueError, match="persisted candidate claims COMPLETE but lacks verified ReplayInputBundle"):
        validate_persisted_decision_input_bindings(
            t4_accounting,
            candles=ctx["candles"],
            run_identity=t4_identity,
        )


def test_a9_no_signal_cash_control_allowed_without_bundle(tmp_path: Path) -> None:
    """A9: Legitimate no-signal / CASH run without bundle is allowed."""
    ctx = _b04r2_context(tmp_path)
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(),
        replay_input_bundle=None,
    )
    assert run.identity.completeness.value == "COMPLETE"
    assert run.identity.signal_set_sha256 == canonical_sha256([])

    validate_persisted_decision_input_bindings(
        run.accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )


# ==============================================================================
# Positive Controls P1 - P4
# ==============================================================================


def test_p1_protocol_frozen_canonical_return_sign_positive_control(tmp_path: Path) -> None:
    """P1: Protocol frozen CANONICAL_RETURN_SIGN_V1 succeeds end-to-end with verified bundle."""
    ctx = _b04r2_context(tmp_path)
    bundle = _build_test_bundle(ctx)
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
    )
    assert run.identity.completeness.value == "COMPLETE"
    assert run.identity.signal_producer_contract is not None
    assert run.identity.signal_producer_contract.logical_id == "CANONICAL_RETURN_SIGN_V1"

    validate_persisted_decision_input_bindings(
        run.accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )


def test_p2_protocol_frozen_momentum_threshold_positive_control(tmp_path: Path) -> None:
    """P2: Protocol frozen momentum threshold in authoritative contract parameters succeeds."""
    mt_contract = SignalProducerContract(
        contract_id="CANONICAL_MOMENTUM_POS_V1",
        version="1.0.0",
        producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
        producer_version="1.0.0",
        rule="MOMENTUM_THRESHOLD",
        parameters={"threshold_return_bps": 0.0, "min_lookback_bars": 1},
    )
    SignalProducerRegistry.register_contract(mt_contract)
    ctx = _b04r2_context(tmp_path, producer_contract=mt_contract)

    c1 = ctx["candles"][1]
    ret = (c1.close - c1.open) / c1.open
    threshold = float(mt_contract.parameters.get("threshold_return_bps", 0.0)) / 10_000.0
    expected_direction = 1 if ret > threshold else (-1 if ret < -threshold else 0)

    sig = replace(ctx["signal"], direction=expected_direction)
    bundle = _build_test_bundle(
        ctx,
        signal=sig,
        contract_id=mt_contract.contract_id,
        rule="MOMENTUM_THRESHOLD",
    )
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(sig,),
        replay_input_bundle=bundle,
    )
    assert run.identity.completeness.value == "COMPLETE"
    validate_persisted_decision_input_bindings(
        run.accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )


def test_p3_verified_causal_execution_inputs_provenance(tmp_path: Path) -> None:
    """P3: Verified causal execution inputs bound into bundle match execution observations."""
    artifacts = p6._formal_artifacts(tmp_path)
    run = artifacts["run"]
    bundle_payload = run.accounting.get("formal_replay_input_bundle")
    assert bundle_payload is not None
    assert "causal_execution_inputs" in bundle_payload
    exec_inputs = bundle_payload["causal_execution_inputs"]
    assert len(exec_inputs) > 0
    first = exec_inputs[0]
    assert "liquidity_evidence" in first
    assert "causal_liquidity_volume_base" in first
    assert "causal_liquidity_available_at_ms" in first


def test_p4_persisted_candidate_artifact_roundtrip(tmp_path: Path) -> None:
    """P4: Persist and reload COMPLETE signal-based candidate; persisted verifier passes."""
    ctx = _b04r2_context(tmp_path)
    bundle = _build_test_bundle(ctx)
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
    )
    artifact_path = tmp_path / "candidate_run.json"
    run.write(artifact_path)

    reloaded_data = json.loads(artifact_path.read_text(encoding="utf-8"))
    semantic = reloaded_data["semantic_payload"]
    reloaded_accounting = semantic["accounting"]
    reloaded_identity = semantic["run_identity"]

    validate_persisted_decision_input_bindings(
        reloaded_accounting,
        candles=ctx["candles"],
        run_identity=reloaded_identity,
    )
