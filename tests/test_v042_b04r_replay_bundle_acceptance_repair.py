"""B04R acceptance repair tests for verified replay-input bundle.

Covers R1 (authoritative producer contracts), R2 (full economic semantic payload verification),
and R3 (top-down run identity binding and legacy projection authority).
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
    CanonicalRuleSignalProducer,
    InformationSignal,
    ReplayInputBundle,
    SignalProducerRegistry,
    build_formal_replay_input_bundle,
    canonical_signal_semantic_payload,
    execute_bound_run,
    validate_formal_replay_input_bundle,
)
from btc_quant_agent.economic.acceptance_verifier import (
    FORMAL_DECISION_INPUT_SCHEMA_VERSION,
    validate_persisted_decision_input_bindings,
)
from btc_quant_agent.economic.signal_producer import _runtime_candle_payload
from btc_quant_agent.research_contract.canonical import canonical_sha256, thaw_json


def _b04r_context(tmp_path: Path, producer_contract: Any = None) -> dict[str, Any]:
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
        required=(BenchmarkKind.CASH,),
        descriptive=(),
    )
    contract = producer_contract or SignalProducerRegistry.get_contract("SYNTHETIC_FIXED_DIRECTION_V1")
    protocol = replace(p6._protocol(comparison, engine), signal_producer_contract=contract)
    signal_time = candles[2].open_time_ms
    signal = InformationSignal(
        signal_id="B04R-SIGNAL-1",
        experiment_id=protocol.experiment_revision_id,
        timestamp_ms=signal_time,
        direction=1,
        strength=1.0,
        confidence_interval=(0.2, 0.8),
        horizon_ms=3_600_000,
        metadata={
            "spread_bps": 2.5,
            "liquidity_volume_base": 15.0,
            "liquidity_available_at_ms": candles[1].close_time_ms,
            "volume_usdt": 100_000.0,
            "regime": "TRENDING",
            "atr": 450.0,
        },
    )
    return {
        "candles": frozen_candles,
        "engine": engine,
        "dataset": dataset,
        "funding_evidence": funding_evidence,
        "comparison": comparison,
        "protocol": protocol,
        "signal": signal,
    }


def _build_b04r_bundle(
    ctx: dict[str, Any],
    *,
    signal: InformationSignal | None = None,
    rule: str = "RETURN_SIGN",
    contract_id: str | None = None,
    producer_identity: str | None = None,
    direction: int | None = None,
    strength: float = 1.0,
    confidence_interval: tuple[float, float] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ReplayInputBundle:
    target_signal = signal or ctx["signal"]
    inputs = (ctx["candles"][1],)  # candle 1 open -> close
    open_times = [c.open_time_ms for c in inputs]
    preimage_hash = canonical_sha256([_runtime_candle_payload(c) for c in inputs])

    if contract_id is None:
        if rule == "RETURN_SIGN":
            contract_id = "CANONICAL_RETURN_SIGN_V1"
            resolved_producer = "CANONICAL_RULE_SIGNAL_PRODUCER"
        elif rule == "FIXED_DIRECTION":
            contract_id = "SYNTHETIC_FIXED_DIRECTION_V1"
            resolved_producer = "SYNTHETIC_FIXED_SIGNAL_PRODUCER"
        else:
            contract_id = f"CANONICAL_{rule}_V1"
            resolved_producer = "CANONICAL_RULE_SIGNAL_PRODUCER"
    else:
        resolved_producer = producer_identity or "CANONICAL_RULE_SIGNAL_PRODUCER"

    if producer_identity is not None:
        resolved_producer = producer_identity

    gen_contract: dict[str, Any] = {
        "rule": rule,
        "producer_contract_id": contract_id,
        "strength": strength,
        "min_lookback_bars": 1,
        "material_input_open_times_ms": open_times,
        "expected_preimage_sha256": preimage_hash,
    }
    if direction is not None:
        gen_contract["direction"] = direction
    elif rule in ("FIXED_DIRECTION", "RANDOM_MATCHED_OPPORTUNITY"):
        gen_contract["direction"] = target_signal.direction

    if confidence_interval is not None:
        gen_contract["confidence_interval"] = list(confidence_interval)
    elif target_signal.confidence_interval is not None:
        gen_contract["confidence_interval"] = list(target_signal.confidence_interval)

    if metadata is not None:
        gen_contract["metadata"] = dict(metadata)
    elif target_signal.metadata:
        gen_contract["metadata"] = dict(target_signal.metadata)

    decision_inputs = [
        {
            "signal_id": target_signal.signal_id,
            "signal_timestamp_ms": target_signal.timestamp_ms,
            "signal_payload": target_signal.to_dict(),
            "producer_identity": resolved_producer,
            "producer_version": "1.0.0",
            "producer_contract_id": contract_id,
            "observation_open_times_ms": open_times,
            "generation_contract": gen_contract,
        }
    ]

    target_protocol = ctx["protocol"]
    if contract_id:
        reg_c = SignalProducerRegistry.get_contract(contract_id)
        if reg_c is not None:
            target_protocol = replace(target_protocol, signal_producer_contract=reg_c)
            ctx["protocol"] = target_protocol

    return build_formal_replay_input_bundle(
        protocol=target_protocol,
        dataset_evidence=ctx["dataset"],
        candles=ctx["candles"],
        signals=(target_signal,),
        decision_inputs=decision_inputs,
    )


# ==============================================================================
# R1 Tests: Authoritative Producer Contracts & Fallback Elimination
# ==============================================================================


def test_b04r_caller_controlled_unregistered_contract_rejected(tmp_path: Path) -> None:
    """R1.1: Unregistered contract ID fails closed."""
    ctx = _b04r_context(tmp_path)
    with pytest.raises(ValueError, match="unregistered or unknown producer contract"):
        _build_b04r_bundle(ctx, contract_id="ROGUE_UNREGISTERED_CONTRACT_V99")


def test_b04r_contract_hash_tampering_rejected(tmp_path: Path) -> None:
    """R1.2: Tampering with producer_contract_hash in decision inputs fails closed."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    tampered = bundle.to_dict()
    tampered["decision_inputs"][0]["producer_contract_hash"] = "0" * 64
    tampered["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered.items() if k != "bundle_sha256"}
    )

    with pytest.raises(ValueError, match="producer contract hash mismatch"):
        validate_formal_replay_input_bundle(
            tampered,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(ctx["signal"],),
        )


def test_b04r_contract_rule_mismatch_rejected(tmp_path: Path) -> None:
    """R1.3: generation_contract rule disagreeing with authoritative contract fails closed."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    tampered = bundle.to_dict()
    tampered["decision_inputs"][0]["generation_contract"]["rule"] = "MOMENTUM_THRESHOLD"
    tampered["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered.items() if k != "bundle_sha256"}
    )

    with pytest.raises(ValueError, match="generation contract rule mismatch"):
        validate_formal_replay_input_bundle(
            tampered,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(ctx["signal"],),
        )


def test_b04r_contract_producer_identity_mismatch_rejected(tmp_path: Path) -> None:
    """R1.4: Producer identity declared in entry mismatching authoritative contract fails closed."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    tampered = bundle.to_dict()
    # Contract specifies SYNTHETIC_FIXED_SIGNAL_PRODUCER, entry tampered to CANONICAL_RULE_SIGNAL_PRODUCER
    tampered["decision_inputs"][0]["producer_identity"] = "CANONICAL_RULE_SIGNAL_PRODUCER"
    tampered["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered.items() if k != "bundle_sha256"}
    )

    with pytest.raises(ValueError, match="producer contract identity mismatch"):
        validate_formal_replay_input_bundle(
            tampered,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(ctx["signal"],),
        )


def test_b04r_fixed_direction_prohibited_for_canonical_rule_producer(tmp_path: Path) -> None:
    """R1.5: FIXED_DIRECTION is strictly prohibited for CanonicalRuleSignalProducer."""
    ctx = _b04r_context(tmp_path)
    producer = CanonicalRuleSignalProducer()
    with pytest.raises(ValueError, match="FIXED_DIRECTION is forbidden in CanonicalRuleSignalProducer"):
        producer.replay_signal(
            signal_id="TEST",
            signal_timestamp_ms=ctx["candles"][2].open_time_ms,
            experiment_id=ctx["protocol"].experiment_revision_id,
            input_candles=(ctx["candles"][1],),
            generation_contract={"rule": "FIXED_DIRECTION", "direction": 1},
        )

    # In build_formal_replay_input_bundle:
    with pytest.raises(ValueError, match="FIXED_DIRECTION is strictly prohibited"):
        build_formal_replay_input_bundle(
            protocol=ctx["protocol"],
            dataset_evidence=ctx["dataset"],
            candles=ctx["candles"],
            signals=(ctx["signal"],),
            decision_inputs=[
                {
                    "signal_id": ctx["signal"].signal_id,
                    "signal_timestamp_ms": ctx["signal"].timestamp_ms,
                    "signal_payload": ctx["signal"].to_dict(),
                    "producer_identity": "CANONICAL_RULE_SIGNAL_PRODUCER",
                    "observation_open_times_ms": [ctx["candles"][1].open_time_ms],
                    "generation_contract": {"rule": "FIXED_DIRECTION", "direction": 1},
                }
            ],
        )


def test_b04r_unverified_fallback_to_fixed_direction_prohibited(tmp_path: Path) -> None:
    """R1.6: Empty/unspecified generation contract cannot fall back to unverified FIXED_DIRECTION."""
    ctx = _b04r_context(tmp_path)
    proto_without_contract = replace(ctx["protocol"], signal_producer_contract=None)
    with pytest.raises(ValueError, match="lacks authoritative producer contract; unverified fallback to FIXED_DIRECTION is strictly prohibited"):
        build_formal_replay_input_bundle(
            protocol=proto_without_contract,
            dataset_evidence=ctx["dataset"],
            candles=ctx["candles"],
            signals=(ctx["signal"],),
            decision_inputs=[
                {
                    "signal_id": ctx["signal"].signal_id,
                    "signal_timestamp_ms": ctx["signal"].timestamp_ms,
                    "signal_payload": ctx["signal"].to_dict(),
                    "producer_identity": "CANONICAL_RULE_SIGNAL_PRODUCER",
                    "observation_open_times_ms": [ctx["candles"][1].open_time_ms],
                    # No producer_contract_id and no rule
                }
            ],
        )


# ==============================================================================
# R2 Tests: Full Economic Semantic Payload & Metadata Verification
# ==============================================================================


def test_b04r_tampered_confidence_interval_rejected(tmp_path: Path) -> None:
    """R2.1: Tampering with confidence_interval fails replay verification."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    tampered = bundle.to_dict()
    # Tamper with confidence_interval on the formal candidate signal payload
    tampered["decision_inputs"][0]["signal_payload"]["confidence_interval"] = [0.99, 0.999]
    tampered["decision_inputs"][0]["signal_payload_sha256"] = canonical_sha256(
        tampered["decision_inputs"][0]["signal_payload"]
    )
    tampered["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered.items() if k != "bundle_sha256"}
    )

    with pytest.raises(ValueError, match="replayed signal semantic payload mismatch.*confidence_interval"):
        validate_formal_replay_input_bundle(
            tampered,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
        )


@pytest.mark.parametrize(
    ("meta_field", "tampered_value"),
    [
        ("spread_bps", 999.0),
        ("liquidity_volume_base", 99999.0),
        ("liquidity_available_at_ms", 12345),
        ("volume_usdt", 0.0),
        ("regime", "EXTREME_VOLATILITY"),
        ("atr", 9999.9),
    ],
)
def test_b04r_tampered_economic_metadata_rejected(
    tmp_path: Path, meta_field: str, tampered_value: Any
) -> None:
    """R2.2: Tampering with economic metadata fields fails replay verification."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    tampered = bundle.to_dict()
    tampered["decision_inputs"][0]["signal_payload"]["metadata"][meta_field] = tampered_value
    tampered["decision_inputs"][0]["signal_payload_sha256"] = canonical_sha256(
        tampered["decision_inputs"][0]["signal_payload"]
    )
    tampered["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered.items() if k != "bundle_sha256"}
    )

    with pytest.raises(ValueError, match=f"replayed signal semantic payload mismatch.*{meta_field}"):
        validate_formal_replay_input_bundle(
            tampered,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
        )


# ==============================================================================
# R3 Tests: Direct Run Identity Binding & Top-Down Authority
# ==============================================================================


def test_b04r_run_identity_missing_replay_bundle_hash_rejected(tmp_path: Path) -> None:
    """R3.1: Complete run lacking replay_input_bundle_sha256 in run_identity fails validation."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
        funding_evidence=ctx["funding_evidence"],
    )
    tampered_identity = run.identity.to_dict()
    tampered_identity["replay_input_bundle_sha256"] = None

    with pytest.raises(ValueError, match="lacks replay_input_bundle_sha256 in run_identity"):
        validate_persisted_decision_input_bindings(
            run.accounting,
            candles=ctx["candles"],
            run_identity=tampered_identity,
        )


def test_b04r_run_identity_bundle_hash_mismatch_rejected(tmp_path: Path) -> None:
    """R3.2: Disagreement between run_identity.replay_input_bundle_sha256 and bundle fails closed."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
        funding_evidence=ctx["funding_evidence"],
    )
    tampered_identity = run.identity.to_dict()
    tampered_identity["replay_input_bundle_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="replay input bundle hash mismatch between run_identity"):
        validate_persisted_decision_input_bindings(
            run.accounting,
            candles=ctx["candles"],
            run_identity=tampered_identity,
        )


def test_b04r_run_identity_protocol_and_dataset_fields_mismatch_rejected(tmp_path: Path) -> None:
    """R3.3: Disagreement between run_identity fields and ReplayInputBundle fails closed."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
        funding_evidence=ctx["funding_evidence"],
    )

    # 1. experiment_revision_id mismatch
    id_mismatch = run.identity.to_dict()
    id_mismatch["experiment_revision_id"] = "OTHER_REV"
    with pytest.raises(ValueError, match="experiment_revision_id mismatch"):
        validate_persisted_decision_input_bindings(
            run.accounting,
            candles=ctx["candles"],
            run_identity=id_mismatch,
        )

    # 2. protocol_hash mismatch
    proto_mismatch = run.identity.to_dict()
    proto_mismatch["protocol_hash"] = "0" * 64
    with pytest.raises(ValueError, match="protocol_hash mismatch"):
        validate_persisted_decision_input_bindings(
            run.accounting,
            candles=ctx["candles"],
            run_identity=proto_mismatch,
        )

    # 3. dataset_evidence_id mismatch
    ds_mismatch = run.identity.to_dict()
    ds_mismatch["dataset_evidence_id"] = "OTHER_DATASET"
    with pytest.raises(ValueError, match="dataset_evidence_id mismatch"):
        validate_persisted_decision_input_bindings(
            run.accounting,
            candles=ctx["candles"],
            run_identity=ds_mismatch,
        )

    # 4. signal_set_sha256 mismatch
    sig_mismatch = run.identity.to_dict()
    sig_mismatch["signal_set_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="signal_set_sha256 mismatch"):
        validate_persisted_decision_input_bindings(
            run.accounting,
            candles=ctx["candles"],
            run_identity=sig_mismatch,
        )


def test_b04r_legacy_bindings_disagreement_with_bundle_projection_rejected(tmp_path: Path) -> None:
    """R3.4: Tampering with legacy formal_decision_input_bindings fails projection check."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
        funding_evidence=ctx["funding_evidence"],
    )
    tampered_accounting = thaw_json(run.accounting)
    # Alter observation_open_times_ms in legacy view to conflict with bundle
    c0_hash = canonical_sha256([_runtime_candle_payload(ctx["candles"][0])])
    tampered_accounting["formal_decision_input_bindings"][0]["observation_open_times_ms"] = [
        ctx["candles"][0].open_time_ms
    ]
    tampered_accounting["formal_decision_input_bindings"][0]["material_input_set_sha256"] = c0_hash
    tampered_accounting["formal_decision_input_set_sha256"] = canonical_sha256(
        {
            "schema_version": FORMAL_DECISION_INPUT_SCHEMA_VERSION,
            "bindings": tampered_accounting["formal_decision_input_bindings"],
        }
    )

    with pytest.raises(ValueError, match="disagrees with authoritative ReplayInputBundle projection|disagrees with ReplayInputBundle projection"):
        validate_persisted_decision_input_bindings(
            tampered_accounting,
            candles=ctx["candles"],
            run_identity=run.identity.to_dict(),
        )


def test_b04r_legacy_bindings_alone_cannot_authorize_qualification(tmp_path: Path) -> None:
    """R3.5: Run claiming COMPLETE with legacy decision bindings but missing ReplayInputBundle fails closed."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
        funding_evidence=ctx["funding_evidence"],
    )
    tampered_accounting = thaw_json(run.accounting)
    del tampered_accounting["formal_replay_input_bundle"]
    del tampered_accounting["formal_replay_input_bundle_sha256"]

    with pytest.raises(ValueError, match="lacks verified ReplayInputBundle"):
        validate_persisted_decision_input_bindings(
            tampered_accounting,
            candles=ctx["candles"],
            run_identity=run.identity.to_dict(),
        )


# ==============================================================================
# Positive Controls
# ==============================================================================


def test_b04r_canonical_return_sign_positive_control(tmp_path: Path) -> None:
    """Positive Control 1: Market-derived RETURN_SIGN rule succeeds end-to-end."""
    contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    ctx = _b04r_context(tmp_path, producer_contract=contract)
    # Determine natural return sign from candle 1: close > open -> +1, else -1
    c1 = ctx["candles"][1]
    expected_direction = 1 if c1.close > c1.open else (-1 if c1.close < c1.open else 0)
    sig = replace(
        ctx["signal"],
        direction=expected_direction,
        confidence_interval=None,
        metadata={},
    )

    bundle = _build_b04r_bundle(ctx, signal=sig, rule="RETURN_SIGN")
    assert bundle.bundle_sha256 is not None

    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(sig,),
        replay_input_bundle=bundle,
        funding_evidence=ctx["funding_evidence"],
    )
    assert run.identity.completeness.value == "COMPLETE"
    assert (
        run.identity.replay_input_bundle_sha256
        == run.accounting["formal_replay_input_bundle"]["bundle_sha256"]
    )

    validate_persisted_decision_input_bindings(
        run.accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )


def test_b04r_synthetic_fixed_direction_positive_control(tmp_path: Path) -> None:
    """Positive Control 2: Synthetic fixed direction succeeds under SyntheticFixedSignalProducer."""
    ctx = _b04r_context(tmp_path)
    bundle = _build_b04r_bundle(ctx, rule="FIXED_DIRECTION")
    assert bundle.decision_inputs[0]["producer_identity"] == "SYNTHETIC_FIXED_SIGNAL_PRODUCER"
    assert bundle.decision_inputs[0]["producer_contract_id"] == "SYNTHETIC_FIXED_DIRECTION_V1"

    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        replay_input_bundle=bundle,
        funding_evidence=ctx["funding_evidence"],
    )
    assert run.identity.completeness.value == "COMPLETE"
    assert (
        run.identity.replay_input_bundle_sha256
        == run.accounting["formal_replay_input_bundle"]["bundle_sha256"]
    )

    validate_persisted_decision_input_bindings(
        run.accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )


def test_b04r_complete_economic_metadata_provenance_roundtrip(tmp_path: Path) -> None:
    """Positive Control 3: All economic metadata fields and confidence interval survive verification."""
    ctx = _b04r_context(tmp_path)
    sig = ctx["signal"]
    payload = canonical_signal_semantic_payload(sig)
    assert payload["confidence_interval"] == [0.2, 0.8]
    assert payload["economic_metadata"]["spread_bps"] == 2.5
    assert payload["economic_metadata"]["regime"] == "TRENDING"
    assert payload["economic_metadata"]["atr"] == 450.0

    bundle = _build_b04r_bundle(ctx, signal=sig, rule="FIXED_DIRECTION")
    assert bundle.decision_inputs[0]["signal_payload"]["confidence_interval"] == [0.2, 0.8]

    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(sig,),
        replay_input_bundle=bundle,
        funding_evidence=ctx["funding_evidence"],
    )
    assert run.identity.completeness.value == "COMPLETE"

    validate_persisted_decision_input_bindings(
        run.accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )
