"""B-AR adversarial coverage for decision-input proof at formal promotion."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import test_v041_p6_metrics_benchmarks_qualification as p6
from helpers_v042_semantic_goldens import case_by_id, load_goldens

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic import (
    BenchmarkKind,
    EconomicRunResult,
    InformationSignal,
    build_formal_replay_input_bundle,
    execute_bound_run,
)
from btc_quant_agent.economic.acceptance_verifier import (
    build_formal_decision_input_binding,
    validate_persisted_qualification_semantics,
)
from btc_quant_agent.research_contract.canonical import canonical_json, thaw_json


def _formal_context(
    tmp_path: Path,
    *,
    first_input_available_at_ms: int | None = None,
    future_suffix_delta: float = 0.0,
) -> dict[str, Any]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    candles = list(p6._candles())
    signal_time = candles[1].open_time_ms
    if first_input_available_at_ms is not None:
        candles[0] = replace(
            candles[0], available_at_ms=first_input_available_at_ms
        )
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
        signal_id="BAR-CANDIDATE",
        experiment_id=protocol.experiment_revision_id,
        timestamp_ms=signal_time,
        direction=1,
        strength=1.0,
    )
    proof = build_formal_decision_input_binding(
        signal,
        dataset_evidence=dataset,
        input_contract=protocol.input_contract.to_dict(),
        candles=frozen_candles,
        material_input_open_times_ms=(frozen_candles[0].open_time_ms,),
    )
    return {
        "candles": frozen_candles,
        "engine": engine,
        "dataset": dataset,
        "comparison": comparison,
        "protocol": protocol,
        "signal": signal,
        "proof": proof,
    }


def _execute(
    context: dict[str, Any],
    *,
    proof: Any | None = None,
    bundle: Any | None = None,
) -> EconomicRunResult:
    chosen_proof = context["proof"] if proof is None else proof
    replay_bundle = bundle
    if replay_bundle is None:
        replay_bundle = build_formal_replay_input_bundle(
            protocol=context["protocol"],
            dataset_evidence=context["dataset"],
            candles=context["candles"],
            signals=(context["signal"],),
            decision_inputs=(chosen_proof,),
        )
    return execute_bound_run(
        protocol=context["protocol"],
        comparison=context["comparison"],
        dataset_evidence=context["dataset"],
        engine=context["engine"],
        candles=context["candles"],
        signals=(context["signal"],),
        replay_input_bundle=replay_bundle,
    )


def test_ar_t1_end_to_end_formal_run_rejects_unavailable_material_input(
    tmp_path: Path,
) -> None:
    golden = case_by_id(load_goldens(), "PIT-07-NOT-YET-AVAILABLE")
    context_time = p6._candles()[1].open_time_ms + 1
    context = _formal_context(
        tmp_path,
        first_input_available_at_ms=context_time,
    )
    assert context_time > context["signal"].timestamp_ms
    assert golden["expected"]["correct_behavior"] == (
        "REJECT_OR_NOT_TESTABLE_AT_ORIGINAL_DECISION"
    )
    with pytest.raises(ValueError, match="not available by signal timestamp"):
        _execute(context)


def test_ar_t2_exact_availability_boundary_is_formally_complete(tmp_path: Path) -> None:
    signal_time = p6._candles()[1].open_time_ms
    context = _formal_context(
        tmp_path,
        first_input_available_at_ms=signal_time,
    )
    run = _execute(context)
    assert run.identity.completeness.value == "COMPLETE"
    assert run.accounting["formal_decision_input_bindings"][0][
        "decision_boundary_ms"
    ] == signal_time


def test_ar_t3_future_simulation_suffix_remains_legal(tmp_path: Path) -> None:
    baseline = _formal_context(tmp_path / "baseline")
    changed = _formal_context(tmp_path / "changed", future_suffix_delta=0.25)
    assert any(
        candle.available_at_ms > baseline["signal"].timestamp_ms
        for candle in baseline["candles"][1:]
    )
    first = _execute(baseline)
    second = _execute(changed)
    assert first.identity.completeness.value == "COMPLETE"
    assert second.identity.completeness.value == "COMPLETE"
    assert (
        first.accounting["formal_decision_input_bindings"][0][
            "material_input_set_sha256"
        ]
        == second.accounting["formal_decision_input_bindings"][0][
            "material_input_set_sha256"
        ]
    )


def test_ar_t4_missing_decision_input_proof_fails_closed(tmp_path: Path) -> None:
    context = _formal_context(tmp_path)
    with pytest.raises(ValueError, match="do not exactly cover signals"):
        execute_bound_run(
            protocol=context["protocol"],
            comparison=context["comparison"],
            dataset_evidence=context["dataset"],
            engine=context["engine"],
            candles=context["candles"],
            signals=(context["signal"],),
        )


def test_ar_t5_forged_availability_claim_cannot_survive_persisted_acceptance(
    tmp_path: Path,
) -> None:
    artifacts = p6._formal_artifacts(tmp_path)
    semantic = json.loads(canonical_json(artifacts["qualification"].semantic_payload()))
    accounting = semantic["run_result"]["semantic_payload"]["accounting"]
    binding = accounting["formal_decision_input_bindings"][0]
    binding["available_at_ms"] = binding["decision_boundary_ms"]
    with pytest.raises(ValueError, match="decision input binding schema mismatch"):
        validate_persisted_qualification_semantics(semantic, artifacts["dataset"])

    original = thaw_json(artifacts["run"].accounting)
    original["formal_decision_input_bindings"][0][
        "material_input_set_sha256"
    ] = "0" * 64
    with pytest.raises(ValueError, match="content binding mismatch"):
        validate_persisted_qualification_semantics(
            {
                **artifacts["qualification"].semantic_payload(),
                "run_result": {
                    **artifacts["qualification"].run_result.to_dict(),
                    "semantic_payload": {
                        "run_identity": artifacts["run"].identity.to_dict(),
                        "accounting": original,
                    },
                },
            },
            artifacts["dataset"],
        )


def test_ar_t6_historical_formal_replay_has_no_wall_clock_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = _formal_context(tmp_path)
    monkeypatch.setattr(
        time,
        "time",
        lambda: (_ for _ in ()).throw(AssertionError("wall clock accessed")),
    )
    assert _execute(context).identity.completeness.value == "COMPLETE"


def test_ar_t7_directly_consumes_all_frozen_a04_pit_cases() -> None:
    goldens = load_goldens()
    expected = {
        "D-H4-CLOSED-FALSE-NOT-COMPLETE",
        "PIT-01-CLOSED-POSITIVE",
        "PIT-02-PRODUCT-MISMATCH",
        "PIT-03-INTERVAL-MISMATCH",
        "PIT-04-OVERLAP",
        "PIT-05-GAP",
        "PIT-06-NONFINITE",
        "PIT-07-NOT-YET-AVAILABLE",
    }
    assert set(goldens["consumer_map"]["B03"]) == expected
    for case_id in expected:
        assert case_by_id(goldens, case_id)["future_task_owner"] == "B03"
