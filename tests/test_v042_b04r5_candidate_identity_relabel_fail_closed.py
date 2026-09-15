"""Candidate authority cannot be acquired by relabelling formal identities."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import test_v042_b04r4_random_benchmark_authority_boundary as r4

from btc_quant_agent.economic import (
    EconomicRunRole,
    ResultCompleteness,
    SignalProducerRegistry,
    execute_bound_run,
)
from btc_quant_agent.economic.acceptance_verifier import validate_persisted_decision_input_bindings
from btc_quant_agent.economic.qualification import _validate_candidate_run_binding
from btc_quant_agent.research_contract.canonical import FrozenDict, thaw_json


def _run(tmp_path: Path, *, random: bool = False, empty: bool = False):
    ctx = r4._b04r4_context(tmp_path)
    bundle = None if empty else (
        r4._build_random_benchmark_bundle(ctx)
        if random else r4._build_candidate_bundle(ctx, ctx["contract"])
    )
    run = execute_bound_run(
        protocol=ctx["protocol"], comparison=ctx["comparison"],
        dataset_evidence=ctx["dataset"], engine=ctx["engine"],
        candles=ctx["candles"], signals=() if empty else (ctx["signal"],),
        replay_input_bundle=bundle,
        funding_evidence=ctx["funding_evidence"],
        run_role=EconomicRunRole.RANDOM_BENCHMARK if random else EconomicRunRole.CANDIDATE,
    )
    return ctx, run


def _synchronized(run, identity):
    accounting = thaw_json(run.accounting)
    accounting["formal_run_identity"] = identity.to_dict()
    return replace(run, identity=identity, accounting=FrozenDict(accounting))


def test_t1_random_outer_role_relabel_rejected(tmp_path: Path) -> None:
    _, run = _run(tmp_path, random=True)
    identity = replace(run.identity, run_role=EconomicRunRole.CANDIDATE)
    with pytest.raises(ValueError, match="outer identity differs"):
        replace(run, identity=identity)


def test_t2_random_role_and_producer_relabel_rejected(tmp_path: Path) -> None:
    ctx, run = _run(tmp_path, random=True)
    identity = replace(
        run.identity, run_role=EconomicRunRole.CANDIDATE,
        signal_producer_contract=ctx["contract"].to_versioned_identity(),
    )
    with pytest.raises(ValueError, match="outer identity differs"):
        replace(run, identity=identity)
    # Even synchronizing the embedded identity cannot authorize the random bundle.
    forged = _synchronized(run, identity)
    with pytest.raises(ValueError, match="producer contract.*mismatch"):
        validate_persisted_decision_input_bindings(
            thaw_json(forged.accounting), candles=ctx["candles"],
            run_identity=forged.identity.to_dict(),
        )


def test_t3_candidate_producer_must_match_protocol(tmp_path: Path) -> None:
    ctx, run = _run(tmp_path)
    contract = SignalProducerRegistry.get_contract("CANONICAL_MOMENTUM_THRESHOLD_V1")
    assert contract is not None
    forged = _synchronized(run, replace(
        run.identity, signal_producer_contract=contract.to_versioned_identity(),
    ))
    with pytest.raises(ValueError, match="differs from protocol authority"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], forged)


def test_t4_candidate_random_producer_rejected(tmp_path: Path) -> None:
    ctx, run = _run(tmp_path, random=True)
    forged = _synchronized(run, replace(run.identity, run_role=EconomicRunRole.CANDIDATE))
    with pytest.raises(ValueError, match="random benchmark producer"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], forged)


@pytest.mark.parametrize("field", ["run_role", "signal_producer_contract"])
def test_t5_embedded_identity_tamper_rejected(tmp_path: Path, field: str) -> None:
    _, run = _run(tmp_path)
    accounting = thaw_json(run.accounting)
    accounting["formal_run_identity"][field] = (
        "RANDOM_BENCHMARK" if field == "run_role" else None
    )
    with pytest.raises(ValueError, match="outer identity differs"):
        replace(run, accounting=FrozenDict(accounting))


@pytest.mark.parametrize("field", ["run_role", "signal_producer_contract", "replay_input_bundle_sha256"])
def test_t6_outer_identity_tamper_rejected(tmp_path: Path, field: str) -> None:
    _, run = _run(tmp_path)
    value = {
        "run_role": EconomicRunRole.RANDOM_BENCHMARK,
        "signal_producer_contract": None,
        "replay_input_bundle_sha256": "0" * 64,
    }[field]
    with pytest.raises(ValueError, match="outer identity differs"):
        replace(run, identity=replace(run.identity, **{field: value}))


def test_t7_valid_candidate_complete(tmp_path: Path) -> None:
    ctx, run = _run(tmp_path)
    _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], run)
    assert run.identity.completeness == ResultCompleteness.COMPLETE


def test_t8_valid_random_benchmark_only(tmp_path: Path) -> None:
    ctx, run = _run(tmp_path, random=True)
    validate_persisted_decision_input_bindings(
        thaw_json(run.accounting), candles=ctx["candles"], run_identity=run.identity.to_dict(),
    )
    assert run.identity.completeness == ResultCompleteness.COMPLETE
    with pytest.raises(ValueError, match="candidate run cannot have role RANDOM_BENCHMARK"):
        _validate_candidate_run_binding(ctx["protocol"], ctx["comparison"], run)


def test_t9_zero_signal_candidate_without_contract(tmp_path: Path) -> None:
    ctx, run = _run(tmp_path, empty=True)
    protocol = replace(ctx["protocol"], signal_producer_contract=None)
    run = execute_bound_run(
        protocol=protocol, comparison=ctx["comparison"], dataset_evidence=ctx["dataset"],
        engine=ctx["engine"], candles=ctx["candles"], signals=(),
        funding_evidence=ctx["funding_evidence"],
    )
    _validate_candidate_run_binding(protocol, ctx["comparison"], run)
    assert run.identity.completeness == ResultCompleteness.COMPLETE
