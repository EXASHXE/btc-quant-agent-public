from __future__ import annotations

import datetime
import time
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
    build_formal_replay_input_bundle,
    execute_bound_run,
    validate_formal_replay_input_bundle,
)
from btc_quant_agent.economic.acceptance_verifier import (
    build_formal_decision_input_binding,
    validate_persisted_decision_input_bindings,
)
from btc_quant_agent.economic.signal_producer import (
    _runtime_candle_payload,
)
from btc_quant_agent.research_contract.canonical import canonical_sha256


def _b04_context(
    tmp_path: Path,
    *,
    first_input_available_at_ms: int | None = None,
    future_suffix_delta: float = 0.0,
) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    candles = list(p6._candles())
    signal_time = candles[2].open_time_ms
    if first_input_available_at_ms is not None:
        candles[0] = replace(candles[0], available_at_ms=first_input_available_at_ms)
    if future_suffix_delta:
        last = candles[-1]
        candles[-1] = replace(
            last,
            close=last.close + future_suffix_delta,
            high=last.high + future_suffix_delta,
            volume=last.volume + 100_000.0,
            quote_volume=last.quote_volume + 10_000_000.0,
        )
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
    protocol = p6._protocol(comparison, engine)
    signal = InformationSignal(
        signal_id="B04-SIGNAL-1",
        experiment_id=protocol.experiment_revision_id,
        timestamp_ms=signal_time,
        direction=1,
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


def _build_bundle(
    context: dict[str, Any],
    *,
    signal: InformationSignal | None = None,
    input_candles: tuple[Candle, ...] | None = None,
    rule: str = "FIXED_DIRECTION",
    direction: int = 1,
    strength: float = 1.0,
    producer_identity: str = "SYNTHETIC_FIXED_SIGNAL_PRODUCER",
    producer_version: str = "1.0.0",
    producer_contract_id: str | None = None,
    min_lookback: int = 1,
) -> ReplayInputBundle:
    target_signal = signal or context["signal"]
    # R05B: the authoritative required window for the fixture's signal
    # timestamp is candles[1] (latest eligible row); default to it.
    inputs = input_candles or (context["candles"][1],)
    open_times = [c.open_time_ms for c in inputs]
    preimage_hash = canonical_sha256([_runtime_candle_payload(c) for c in inputs])
    contract_id = producer_contract_id or (
        "SYNTHETIC_FIXED_DIRECTION_V1"
        if rule == "FIXED_DIRECTION"
        else f"CANONICAL_{rule}_V1"
    )
    contract: dict[str, Any] = {
        "rule": rule,
        "direction": direction,
        "strength": strength,
        "producer_contract_id": contract_id,
        "min_lookback_bars": min_lookback,
        "material_input_open_times_ms": open_times,
        "expected_preimage_sha256": preimage_hash,
    }
    if rule == "PRICE_BREAKOUT":
        contract["breakout_level"] = inputs[-1].open  # breakout if close > open
    decision_inputs = [
        {
            "signal_id": target_signal.signal_id,
            "signal_timestamp_ms": target_signal.timestamp_ms,
            "signal_payload": target_signal.to_dict(),
            "producer_identity": producer_identity,
            "producer_version": producer_version,
            "producer_contract_id": contract_id,
            "observation_open_times_ms": open_times,
            "generation_contract": contract,
        }
    ]
    return build_formal_replay_input_bundle(
        protocol=context["protocol"],
        dataset_evidence=context["dataset"],
        candles=context["candles"],
        signals=(target_signal,),
        decision_inputs=decision_inputs,
    )


# ==============================================================================
# 18. Required Attack Tests (T1 - T16)
# ==============================================================================


def test_b04_t1_unrelated_valid_input_substitution_rejected(tmp_path: Path) -> None:
    """T1: True producer uses Candle 1; attacker bundle substitutes Candle 0.

    Candle 0 is valid, available on time, and from the same dataset, but fails
    producer preimage / open time verification.
    """
    ctx = _b04_context(tmp_path)
    # True signal relies on candle 1
    candle_1 = ctx["candles"][1]
    candle_0 = ctx["candles"][0]
    true_bundle = _build_bundle(ctx, input_candles=(candle_1,))

    # Attacker crafts bundle with candle_0 in input_references, but leaves generation contract targeting candle_1
    tampered = true_bundle.to_dict()
    tampered_entry = dict(tampered["decision_inputs"][0])
    # Replace input reference with candle_0
    c0_hash = canonical_sha256(_runtime_candle_payload(candle_0))
    tampered_entry["input_references"] = [
        {
            "source_type": "CANONICAL_CANDLE",
            "dataset_evidence_id": ctx["dataset"].evidence_id,
            "open_time_ms": candle_0.open_time_ms,
            "close_time_ms": candle_0.close_time_ms,
            "available_at_ms": candle_0.available_at_ms,
            "row_content_sha256": c0_hash,
        }
    ]
    tampered_entry["input_set_sha256"] = canonical_sha256(tampered_entry["input_references"])
    tampered["decision_inputs"] = [tampered_entry]
    tampered["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered.items() if k != "bundle_sha256"}
    )

    with pytest.raises(
        ValueError,
        match="input open times do not match generation contract|input preimage hash mismatch|persisted input references",
    ):
        validate_formal_replay_input_bundle(
            tampered,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(ctx["signal"],),
        )


def test_b04_t2_hidden_future_input_rejected(tmp_path: Path) -> None:
    """T2: Producer actually requires candle available after signal timestamp.

    Must fail closed with availability error.
    """
    signal_time = p6._candles()[2].open_time_ms
    ctx = _b04_context(tmp_path, first_input_available_at_ms=signal_time + 60_000)
    # R05B: explicitly assert the stale candle 0 window so the availability
    # rejection (not the exact-window rejection) is exercised.
    with pytest.raises(ValueError, match="was not available by signal timestamp"):
        _build_bundle(ctx, input_candles=(ctx["candles"][0],))


def test_b04_t3_missing_replay_bundle_fails_closed(tmp_path: Path) -> None:
    """T3: Non-empty formal signals without a replay bundle must fail closed."""
    ctx = _b04_context(tmp_path)
    with pytest.raises(ValueError, match="requires a verified ReplayInputBundle"):
        execute_bound_run(
            protocol=ctx["protocol"],
            comparison=ctx["comparison"],
            dataset_evidence=ctx["dataset"],
            engine=ctx["engine"],
            candles=ctx["candles"],
            signals=(ctx["signal"],),
            replay_input_bundle=None,
        )


def test_b04_t4_legacy_decision_binding_only_attack_cannot_become_complete(
    tmp_path: Path,
) -> None:
    """T4: Supplying only legacy decision-input bindings cannot authorize formal COMPLETE."""
    ctx = _b04_context(tmp_path)
    legacy_binding = build_formal_decision_input_binding(
        ctx["signal"],
        dataset_evidence=ctx["dataset"],
        input_contract=ctx["protocol"].input_contract.to_dict(),
        candles=ctx["candles"],
        material_input_open_times_ms=(ctx["candles"][0].open_time_ms,),
    )
    # Attempting to execute with only legacy decision bindings must be rejected
    with pytest.raises(
        ValueError, match="formal run requires a verified ReplayInputBundle; legacy decision-input bindings alone cannot authorize formal economic qualification"
    ):
        execute_bound_run(
            protocol=ctx["protocol"],
            comparison=ctx["comparison"],
            dataset_evidence=ctx["dataset"],
            engine=ctx["engine"],
            candles=ctx["candles"],
            signals=(ctx["signal"],),
            decision_input_bindings=(legacy_binding,),
            replay_input_bundle=None,
        )

    # Furthermore, persisted verifier rejects candidate claiming COMPLETE without bundle
    fake_accounting = {
        "formal_decision_input_schema_version": "1.0.0",
        "formal_decision_input_bindings": [legacy_binding],
        "formal_decision_input_set_sha256": canonical_sha256({"schema_version": "1.0.0", "bindings": [legacy_binding]}),
    }
    fake_identity = {
        "completeness": "COMPLETE",
        "dataset_evidence_id": ctx["dataset"].evidence_id,
        "dataset_content_sha256": ctx["dataset"].content_sha256,
        "input_contract": ctx["protocol"].input_contract.to_dict(),
        "signal_set_sha256": canonical_sha256([ctx["signal"].to_dict()]),
        "decision_input_set_sha256": fake_accounting["formal_decision_input_set_sha256"],
    }
    with pytest.raises(
        ValueError, match="persisted candidate claims COMPLETE but lacks verified ReplayInputBundle"
    ):
        validate_persisted_decision_input_bindings(
            fake_accounting,
            candles=ctx["candles"],
            run_identity=fake_identity,
        )


def test_b04_t5_dataset_hash_mismatch_rejected(tmp_path: Path) -> None:
    """T5: Replay bundle bound to Dataset A is rejected when executed against Dataset B."""
    ctx = _b04_context(tmp_path)
    bundle = _build_bundle(ctx)

    other_evidence = replace(ctx["dataset"], content_sha256="1" * 64)
    with pytest.raises(ValueError, match="replay input bundle dataset (evidence id|content hash) mismatch"):
        validate_formal_replay_input_bundle(
            bundle.to_dict(),
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=other_evidence,
            expected_signals=(ctx["signal"],),
        )


def test_b04_t6_row_content_tamper_rejected(tmp_path: Path) -> None:
    """T6: Candle open_time_ms preserved, but OHLCV content modified; rejected on row hash mismatch."""
    ctx = _b04_context(tmp_path)
    bundle = _build_bundle(ctx)

    # Modify underlying candle content (volume changed, OHLC bounds still valid)
    # R05B: candle 1 is the authoritative required row for this fixture, so
    # tamper that row to exercise the row-content hash check.
    tampered_candles = list(ctx["candles"])
    tampered_candles[1] = replace(tampered_candles[1], volume=tampered_candles[1].volume + 1000.0)

    with pytest.raises(ValueError, match="candle row content sha256 mismatch"):
        validate_formal_replay_input_bundle(
            bundle.to_dict(),
            candles=tampered_candles,
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(ctx["signal"],),
        )


def test_b04_t7_availability_tamper_rejected(tmp_path: Path) -> None:
    """T7: Asserted availability in bundle reference forged to differ from true candle availability."""
    ctx = _b04_context(tmp_path)
    bundle = _build_bundle(ctx)
    tampered = bundle.to_dict()
    ref = tampered["decision_inputs"][0]["input_references"][0]
    ref["available_at_ms"] = int(ref["available_at_ms"]) - 10_000
    tampered["decision_inputs"][0]["input_set_sha256"] = canonical_sha256(
        tampered["decision_inputs"][0]["input_references"]
    )
    tampered["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered.items() if k != "bundle_sha256"}
    )

    with pytest.raises(ValueError, match="asserted availability timestamp mismatch"):
        validate_formal_replay_input_bundle(
            tampered,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(ctx["signal"],),
        )


def test_b04_t8_producer_identity_or_version_mismatch_rejected(tmp_path: Path) -> None:
    """T8: Producer identity / version unknown or mismatched fails closed (Mode B: NOT_TESTABLE)."""
    ctx = _b04_context(tmp_path)
    bundle = _build_bundle(ctx)
    tampered = bundle.to_dict()
    tampered["decision_inputs"][0]["producer_identity"] = "ROGUE_UNREGISTERED_PRODUCER"
    tampered["bundle_sha256"] = canonical_sha256(
        {k: v for k, v in tampered.items() if k != "bundle_sha256"}
    )

    with pytest.raises(ValueError, match="unregistered or non-replayable signal producer"):
        validate_formal_replay_input_bundle(
            tampered,
            candles=ctx["candles"],
            expected_protocol=ctx["protocol"],
            expected_dataset_evidence=ctx["dataset"],
            expected_signals=(ctx["signal"],),
        )


def test_b04_t9_producer_replay_direction_mismatch_rejected(tmp_path: Path) -> None:
    """T9: Signal producer replays direction -1, but candidate signal claims +1; rejected."""
    ctx = _b04_context(tmp_path)
    assert ctx["signal"].direction == 1
    # Building bundle where contract generates direction -1 for direction +1 signal fails closed
    with pytest.raises(ValueError, match="replayed signal direction mismatch"):
        _build_bundle(ctx, direction=-1)


def test_b04_t10_strength_mismatch_rejected(tmp_path: Path) -> None:
    """T10: Replayed strength does not match candidate signal strength; rejected."""
    ctx = _b04_context(tmp_path)
    assert ctx["signal"].strength == 1.0
    # Building bundle where contract generates strength 0.5 for strength 1.0 signal fails closed
    with pytest.raises(ValueError, match="replayed signal strength mismatch"):
        _build_bundle(ctx, strength=0.5)


def test_b04_t11_future_suffix_invariance(tmp_path: Path) -> None:
    """T11: Changing future simulation candles (after signal boundary) preserves signal bundle identity."""
    ctx_base = _b04_context(tmp_path / "base")
    bundle_base = _build_bundle(ctx_base)

    # Create modified future candles (strictly after signal at candle 2)
    tampered_candles = list(ctx_base["candles"])
    tampered_candles[-1] = replace(
        tampered_candles[-1],
        volume=tampered_candles[-1].volume + 50_000.0,
        quote_volume=tampered_candles[-1].quote_volume + 5_000_000.0,
    )

    # Validating the exact same bundle against the modified future timeline must succeed
    validated = validate_formal_replay_input_bundle(
        bundle_base.to_dict(),
        candles=tampered_candles,
        expected_protocol=ctx_base["protocol"],
        expected_dataset_evidence=ctx_base["dataset"],
        expected_signals=(ctx_base["signal"],),
    )
    assert validated["bundle_sha256"] == bundle_base.bundle_sha256


def test_b04_t12_multiple_signals_exact_coverage(tmp_path: Path) -> None:
    """T12: Formal run with 2 signals must enforce exact 1:1 coverage (missing, dup, extra, swapped rejected)."""
    ctx = _b04_context(tmp_path)
    sig1 = ctx["signal"]
    sig2 = InformationSignal(
        signal_id="B04-SIGNAL-2",
        experiment_id=ctx["protocol"].experiment_revision_id,
        timestamp_ms=ctx["candles"][3].open_time_ms,
        direction=1,
        strength=1.0,
    )

    # R05B: each signal's authoritative required window is its latest
    # eligible row (candles[1] for sig1, candles[2] for sig2).
    in1 = (ctx["candles"][1],)
    in2 = (ctx["candles"][2],)
    open1 = [c.open_time_ms for c in in1]
    open2 = [c.open_time_ms for c in in2]

    entry1 = {
        "signal_id": sig1.signal_id,
        "signal_timestamp_ms": sig1.timestamp_ms,
        "signal_payload": sig1.to_dict(),
        "producer_identity": "SYNTHETIC_FIXED_SIGNAL_PRODUCER",
        "producer_version": "1.0.0",
        "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
        "observation_open_times_ms": open1,
        "generation_contract": {
            "rule": "FIXED_DIRECTION",
            "direction": 1,
            "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
            "material_input_open_times_ms": open1,
            "expected_preimage_sha256": canonical_sha256([_runtime_candle_payload(c) for c in in1]),
        },
    }
    entry2 = {
        "signal_id": sig2.signal_id,
        "signal_timestamp_ms": sig2.timestamp_ms,
        "signal_payload": sig2.to_dict(),
        "producer_identity": "SYNTHETIC_FIXED_SIGNAL_PRODUCER",
        "producer_version": "1.0.0",
        "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
        "observation_open_times_ms": open2,
        "generation_contract": {
            "rule": "FIXED_DIRECTION",
            "direction": 1,
            "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
            "material_input_open_times_ms": open2,
            "expected_preimage_sha256": canonical_sha256([_runtime_candle_payload(c) for c in in2]),
        },
    }

    # Attack 1: Missing sig2
    with pytest.raises(ValueError, match="replay input bundle (decision inputs do not exactly cover signals|signal_set_sha256 mismatch)"):
        build_formal_replay_input_bundle(
            protocol=ctx["protocol"],
            dataset_evidence=ctx["dataset"],
            candles=ctx["candles"],
            signals=(sig1, sig2),
            decision_inputs=[entry1],
        )

    # Attack 2: Duplicate sig1
    with pytest.raises(ValueError, match="duplicate decision input entry for signal"):
        build_formal_replay_input_bundle(
            protocol=ctx["protocol"],
            dataset_evidence=ctx["dataset"],
            candles=ctx["candles"],
            signals=(sig1, sig2),
            decision_inputs=[entry1, entry1],
        )

    # Attack 3: Extra unrequested signal
    sig3 = InformationSignal(
        signal_id="B04-SIGNAL-3",
        experiment_id=ctx["protocol"].experiment_revision_id,
        timestamp_ms=ctx["candles"][4].open_time_ms,
        direction=1,
        strength=1.0,
    )
    in3 = (ctx["candles"][3],)
    open3 = [c.open_time_ms for c in in3]
    entry3 = {
        "signal_id": sig3.signal_id,
        "signal_timestamp_ms": sig3.timestamp_ms,
        "signal_payload": sig3.to_dict(),
        "producer_identity": "SYNTHETIC_FIXED_SIGNAL_PRODUCER",
        "producer_version": "1.0.0",
        "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
        "observation_open_times_ms": open3,
        "generation_contract": {
            "rule": "FIXED_DIRECTION",
            "direction": 1,
            "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
            "material_input_open_times_ms": open3,
            "expected_preimage_sha256": canonical_sha256([_runtime_candle_payload(c) for c in in3]),
        },
    }
    with pytest.raises(ValueError, match="replay input bundle (decision inputs do not exactly cover signals|signal_set_sha256 mismatch)"):
        build_formal_replay_input_bundle(
            protocol=ctx["protocol"],
            dataset_evidence=ctx["dataset"],
            candles=ctx["candles"],
            signals=(sig1, sig2),
            decision_inputs=[entry1, entry2, entry3],
        )


def test_b04_t13_incomplete_lookback_rejected(tmp_path: Path) -> None:
    """T13: Producer contract requires 3 lookback bars; bundle only supplies 2; rejected.

    R05B tightening: caller lookback assertions are no longer authority; the
    registered contract's selector requires exactly the latest 1 eligible
    row, so a 2-row caller window is rejected as a non-authoritative window
    before lookback accounting is even consulted.
    """
    ctx = _b04_context(tmp_path)
    inputs_2 = (ctx["candles"][0], ctx["candles"][1])
    with pytest.raises(
        ValueError,
        match="caller-selected material window for B04-SIGNAL-1 does not equal the authoritative required input window",
    ):
        _build_bundle(ctx, input_candles=inputs_2, min_lookback=3)


def test_b04_t14_reordered_input_references_rejected(tmp_path: Path) -> None:
    """T14: Input references not in strictly increasing chronological order; rejected.

    R05B tightening: a reordered caller window is rejected as a
    non-authoritative required window — the selector always yields the
    strictly increasing latest-eligible window, so the assertion can never
    legitimately disagree with it.
    """
    ctx = _b04_context(tmp_path)
    inputs = (ctx["candles"][1], ctx["candles"][0])  # descending order
    with pytest.raises(
        ValueError,
        match="caller-selected material window for B04-SIGNAL-1 does not equal the authoritative required input window",
    ):
        _build_bundle(ctx, input_candles=inputs)


def test_b04_t15_historical_wall_clock_independence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T15: Verification and execution must have zero dependency on wall clock."""
    ctx = _b04_context(tmp_path)
    bundle = _build_bundle(ctx)

    monkeypatch.setattr(time, "time", lambda: (_ for _ in ()).throw(AssertionError("wall clock accessed")))
    monkeypatch.setattr(
        datetime, "datetime", type("MockDT", (datetime.datetime,), {"now": staticmethod(lambda *args: (_ for _ in ()).throw(AssertionError("datetime.now accessed")))})
    )

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


def test_b04_t16_b02_cost_provenance_retained_in_bundle(tmp_path: Path) -> None:
    """T16: B02 causal execution inputs (liquidity volume, availability, source) retained in replay bundle."""
    artifacts = p6._formal_artifacts(tmp_path)
    run = artifacts["run"]
    bundle_payload = run.accounting.get("formal_replay_input_bundle")
    assert bundle_payload is not None
    assert "causal_execution_inputs" in bundle_payload
    # Candidate trade generated causal liquidity inputs
    assert len(bundle_payload["causal_execution_inputs"]) > 0
    first_exec = bundle_payload["causal_execution_inputs"][0]
    assert "liquidity_evidence" in first_exec
    assert "causal_liquidity_volume_base" in first_exec
    assert "causal_liquidity_available_at_ms" in first_exec


# ==============================================================================
# 19. Positive Controls (P1 - P4)
# ==============================================================================


def test_b04_p1_valid_deterministic_candidate_allowed(tmp_path: Path) -> None:
    """P1: Valid deterministic candidate with verified replay bundle achieves COMPLETE."""
    ctx = _b04_context(tmp_path)
    bundle = _build_bundle(ctx)

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
    assert run.accounting["formal_replay_input_bundle_schema_version"] == "1.0.0"
    assert (
        run.accounting["formal_replay_input_bundle_sha256"]
        == run.accounting["formal_replay_input_bundle"]["bundle_sha256"]
    )
    validate_persisted_decision_input_bindings(
        run.accounting,
        candles=ctx["candles"],
        run_identity=run.identity.to_dict(),
    )


def test_b04_p2_exact_availability_boundary_allowed(tmp_path: Path) -> None:
    """P2: input.available_at_ms == signal.timestamp_ms is causality-legal and achieves COMPLETE."""
    signal_time = p6._candles()[2].open_time_ms
    ctx = _b04_context(tmp_path, first_input_available_at_ms=signal_time)
    bundle = _build_bundle(ctx)

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


def test_b04_p3_future_outcome_candles_allowed(tmp_path: Path) -> None:
    """P3: Dataset candles occurring strictly after signal timestamp are allowed in simulation."""
    ctx = _b04_context(tmp_path)
    # Signal is at candle 2; dataset has candles 3, 4, 5...
    assert any(c.available_at_ms > ctx["signal"].timestamp_ms for c in ctx["candles"][3:])
    bundle = _build_bundle(ctx)

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


def test_b04_p4_multiple_valid_signals_complete(tmp_path: Path) -> None:
    """P4: Multiple valid signals each with independent verified preimage achieves COMPLETE."""
    ctx = _b04_context(tmp_path)
    sig1 = ctx["signal"]
    sig2 = InformationSignal(
        signal_id="B04-MULTI-2",
        experiment_id=ctx["protocol"].experiment_revision_id,
        timestamp_ms=ctx["candles"][3].open_time_ms,
        direction=1,
        strength=1.0,
    )

    # R05B: each signal's authoritative required window is its latest
    # eligible row (candles[1] for sig1, candles[2] for sig2).
    in1 = (ctx["candles"][1],)
    in2 = (ctx["candles"][2],)
    open1 = [c.open_time_ms for c in in1]
    open2 = [c.open_time_ms for c in in2]

    entry1 = {
        "signal_id": sig1.signal_id,
        "signal_timestamp_ms": sig1.timestamp_ms,
        "signal_payload": sig1.to_dict(),
        "producer_identity": "SYNTHETIC_FIXED_SIGNAL_PRODUCER",
        "producer_version": "1.0.0",
        "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
        "observation_open_times_ms": open1,
        "generation_contract": {
            "rule": "FIXED_DIRECTION",
            "direction": 1,
            "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
            "material_input_open_times_ms": open1,
            "expected_preimage_sha256": canonical_sha256([_runtime_candle_payload(c) for c in in1]),
        },
    }
    entry2 = {
        "signal_id": sig2.signal_id,
        "signal_timestamp_ms": sig2.timestamp_ms,
        "signal_payload": sig2.to_dict(),
        "producer_identity": "SYNTHETIC_FIXED_SIGNAL_PRODUCER",
        "producer_version": "1.0.0",
        "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
        "observation_open_times_ms": open2,
        "generation_contract": {
            "rule": "FIXED_DIRECTION",
            "direction": 1,
            "producer_contract_id": "SYNTHETIC_FIXED_DIRECTION_V1",
            "material_input_open_times_ms": open2,
            "expected_preimage_sha256": canonical_sha256([_runtime_candle_payload(c) for c in in2]),
        },
    }

    bundle = build_formal_replay_input_bundle(
        protocol=ctx["protocol"],
        dataset_evidence=ctx["dataset"],
        candles=ctx["candles"],
        signals=(sig1, sig2),
        decision_inputs=[entry1, entry2],
    )
    run = execute_bound_run(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"],
        engine=ctx["engine"],
        candles=ctx["candles"],
        signals=(sig1, sig2),
        replay_input_bundle=bundle,
    )
    assert run.identity.completeness.value == "COMPLETE"
    assert len(run.accounting["formal_decision_input_bindings"]) == 2
