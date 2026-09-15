"""Formal replay orchestration; arithmetic belongs exclusively to the canonical engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from ..research_contract.canonical import canonical_sha256, thaw_json
from ..research_contract.models import EvidenceReference, ExperimentMetadata
from .acceptance_verifier import (
    decode_runtime_market_data,
    validate_persisted_decision_input_bindings,
)
from .execution_model import ExecutionModel
from .fee_model import FeeModel
from .funding import FundingModel, FundingSettlement
from .funding_evidence import load_and_validate_funding_evidence
from .policy import EntryRule, ExitRule, MarketStateFilter, PositionSizing, RiskBudget, TradePolicy
from .signal import InformationSignal
from .simulator import EconomicSimulationEngine

EXECUTION_REPLAY_SCHEMA_VERSION = "1.1.0"


def execution_replay_inputs(
    protocol: ExperimentMetadata, dataset: EvidenceReference,
    engine: EconomicSimulationEngine, funding_evidence: EvidenceReference,
    funding: Sequence[FundingSettlement],
) -> dict[str, Any]:
    record = protocol.to_dict()
    # Audit creation time is not an economic input or a replay identity.
    record["audit"] = {"created_at_utc": "1970-01-01T00:00:00+00:00", "metadata": {}}
    return {
        "schema_version": EXECUTION_REPLAY_SCHEMA_VERSION,
        "protocol": record,
        "dataset_evidence": dataset.to_dict(),
        "funding_evidence": funding_evidence.to_dict(),
        "policy": engine.policy.to_dict(),
        "fee_model": asdict(engine.fee_model),
        "execution_fee_model": asdict(engine.execution_model.fee_model),
        "execution_model": {
            "decision_latency_ms": engine.execution_model.decision_latency_ms,
            "exchange_latency_ms": engine.execution_model.exchange_latency_ms,
            "order_submission_latency_ms": engine.execution_model.order_submission_latency_ms,
            "limit_fill_prob_on_touch": engine.execution_model.limit_fill_prob_on_touch,
        },
        "funding_model": asdict(engine.funding_model),
        "funding_events": [asdict(item) for item in sorted(funding, key=lambda item: item.timestamp_ms)],
    }


def require_replay_equality(observed: Any, expected: Any, label: str) -> None:
    """Exact, canonical economic equality, without trusting submitted derived values."""
    if canonical_sha256(observed) != canonical_sha256(expected):
        raise ValueError(f"{label} canonical replay mismatch")


def verify_execution_replay(
    semantic: Mapping[str, Any], *, protocol: ExperimentMetadata | None = None,
    comparison: Any, dataset_evidence: EvidenceReference | None = None,
    expected_role: str = "CANDIDATE",
) -> tuple[Any, EconomicSimulationEngine, Any, EvidenceReference, tuple[FundingSettlement, ...]]:
    from .qualification import execute_bound_run

    accounting = semantic["accounting"]
    identity = semantic["run_identity"]
    if identity.get("run_role") != expected_role:
        raise ValueError("execution replay role differs from expected authority")
    raw = thaw_json(accounting.get("formal_execution_replay_inputs"))
    if not isinstance(raw, dict) or raw.get("schema_version") != EXECUTION_REPLAY_SCHEMA_VERSION:
        raise ValueError("execution replay inputs missing/unsupported: NOT_TESTABLE")
    if set(raw) != {
        "schema_version", "protocol", "dataset_evidence", "funding_evidence", "policy",
        "fee_model", "execution_fee_model", "execution_model", "funding_model",
        "funding_events",
    }:
        raise ValueError("execution replay input schema mismatch")
    recorded_protocol = ExperimentMetadata.from_dict(raw["protocol"])
    if protocol is not None and recorded_protocol.protocol_hash != protocol.protocol_hash:
        raise ValueError("execution replay protocol differs from frozen authority")
    protocol = protocol or recorded_protocol
    recorded_dataset = EvidenceReference.from_dict(raw["dataset_evidence"])
    dataset = dataset_evidence or recorded_dataset
    if dataset.evidence_id != recorded_dataset.evidence_id:
        raise ValueError("execution replay dataset differs from external evidence")
    policy = dict(raw["policy"])
    for name, kind in (
        ("entry_rule", EntryRule), ("exit_rule", ExitRule), ("position_sizing", PositionSizing),
        ("risk_budget", RiskBudget), ("market_filter", MarketStateFilter),
    ):
        policy[name] = kind(**policy[name])
    fees = FeeModel(**raw["fee_model"])
    engine = EconomicSimulationEngine(
        policy=TradePolicy(**policy), fee_model=fees,
        execution_model=ExecutionModel(
            fee_model=FeeModel(**raw["execution_fee_model"]), **raw["execution_model"],
        ),
        funding_model=FundingModel(**raw["funding_model"]), initial_cash=comparison.initial_capital,
    )
    recorded_funding_evidence = EvidenceReference.from_dict(raw["funding_evidence"])
    if (
        identity.get("funding_evidence_id") != recorded_funding_evidence.evidence_id
        or identity.get("funding_evidence_content_sha256")
        != recorded_funding_evidence.content_sha256
    ):
        raise ValueError("execution replay funding evidence differs from run identity")
    # Independent authoritative reload: the persisted funding_evidence reference
    # is validated against the preregistered comparison authority and its bytes
    # are parsed fresh; a persisted event list is only a compatibility assertion
    # and can never replace the evidence file as the source of truth.
    funding = load_and_validate_funding_evidence(
        recorded_funding_evidence,
        expected_product=protocol.product_scope[0],
        expected_start_ms=comparison.data_interval.start_ms,
        expected_end_ms=comparison.data_interval.end_ms,
        expected_identity=comparison.funding_interval,
    )
    funding_hash = canonical_sha256([asdict(item) for item in funding])
    persisted_funding = tuple(FundingSettlement(**item) for item in raw["funding_events"])
    if canonical_sha256([asdict(item) for item in persisted_funding]) != funding_hash:
        raise ValueError("persisted funding events differ from preregistered funding evidence")
    if funding_hash != identity["funding_event_set_sha256"]:
        raise ValueError("execution replay funding input identity mismatch")
    candles = decode_runtime_market_data(accounting, protocol.product_scope[0])
    validate_persisted_decision_input_bindings(accounting, candles=candles, run_identity=identity)
    bundle = accounting.get("formal_replay_input_bundle")
    signals = () if bundle is None else tuple(
        InformationSignal.from_dict(item["signal_payload"]) for item in bundle["decision_inputs"]
    )
    if bundle is not None and bundle.get("funding_input_identity") not in (
        funding_hash, None if not funding else funding_hash,
    ):
        raise ValueError("execution replay funding preimage disagrees with verified bundle")
    result = execute_bound_run(
        protocol=recorded_protocol, comparison=comparison, dataset_evidence=dataset,
        engine=engine, candles=candles, signals=signals, replay_input_bundle=bundle,
        funding_evidence=recorded_funding_evidence, funding_events=funding,
        run_role=expected_role,
    )
    require_replay_equality(semantic, result.semantic_payload(), "economic execution")
    return result, engine, candles, dataset, funding


def verify_benchmark_replay(
    candidate: Mapping[str, Any], suite: Mapping[str, Any], *,
    protocol: ExperimentMetadata | None, comparison: Any,
    dataset_evidence: EvidenceReference | None = None,
) -> None:
    from .qualification import (
        EligibleOpportunity,
        _cash_benchmark,
        _random_matched_benchmark,
        eligible_opportunity_set_sha256,
    )

    run, engine, candles, dataset, funding = verify_execution_replay(
        candidate, protocol=protocol, comparison=comparison, dataset_evidence=dataset_evidence,
    )
    protocol = protocol or ExperimentMetadata.from_dict(
        run.accounting["formal_execution_replay_inputs"]["protocol"]
    )
    if suite.get("cash") is not None:
        require_replay_equality(suite["cash"], _cash_benchmark(comparison, candles).to_dict(), "CASH")
    distribution = suite.get("random")
    if distribution is not None:
        provenance = distribution.get("provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError("random experiment provenance missing: NOT_TESTABLE")
        opportunities = tuple(EligibleOpportunity(**item) for item in provenance["opportunities"])
        if eligible_opportunity_set_sha256(opportunities) != comparison.eligible_opportunity_set_sha256:
            raise ValueError("random opportunity preimage differs from frozen comparison")
        expected = _random_matched_benchmark(
            protocol, comparison, dataset, run, engine,
            EvidenceReference.from_dict(
                thaw_json(run.accounting["formal_execution_replay_inputs"])["funding_evidence"]
            ),
            candles, opportunities, funding,
        )
        # Same canonical execution/equality mechanism as B05, not a second PRNG or engine.
        require_replay_equality(distribution, expected.to_dict(), "random experiment")
