from __future__ import annotations

import hashlib
import math
import os
import random
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..domain import Candle
from ..research_contract.canonical import (
    FrozenDict,
    canonical_json,
    canonical_sha256,
    thaw_json,
)
from ..research_contract.models import (
    P6_PENDING,
    EconomicDecisionAttestation,
    EvidenceCompleteness,
    EvidenceReference,
    ExperimentMetadata,
    VersionedIdentity,
    utc_now,
)
from .acceptance_verifier import (
    FORMAL_DECISION_INPUT_SCHEMA_VERSION,
    PassiveBenchmarkReplayError,
    bind_runtime_market_data,
    build_passive_benchmark_accounting,
    validate_persisted_decision_input_bindings,
    validate_runtime_dataset_binding,
    verify_formal_accounting,
)
from .execution_model import ExecutionModel
from .fee_model import FeeModel
from .funding import FundingModel, FundingSettlement
from .metrics import (
    ResultCompleteness,
    ReturnMetricsContract,
    TerminalPolicy,
    summarize_ledger,
)
from .policy import TradePolicy
from .replay_bundle import (
    FORMAL_REPLAY_INPUT_BUNDLE_SCHEMA_VERSION,
    ReplayInputBundle,
    build_formal_replay_input_bundle,
    validate_formal_replay_input_bundle,
)
from .signal import InformationSignal
from .signal_producer import SignalProducerRegistry, _runtime_candle_payload
from .simulator import EconomicSimulationEngine
from .trade_event import TradeAction

P6_RESULT_SCHEMA_VERSION = "1.1.0"
P6_RESULT_EVIDENCE_TYPE = "P6_ECONOMIC_QUALIFICATION_RESULT"
P6_RUN_EVIDENCE_TYPE = "P6_ECONOMIC_RUN"
P6_BENCHMARK_EVIDENCE_TYPE = "P6_BENCHMARK_SUITE"


class BenchmarkKind(StrEnum):
    CASH = "CASH"
    PASSIVE_PERPETUAL = "PASSIVE_PERPETUAL"
    RANDOM_MATCHED = "RANDOM_MATCHED"


class EconomicRunRole(StrEnum):
    CANDIDATE = "CANDIDATE"
    RANDOM_BENCHMARK = "RANDOM_BENCHMARK"


class QualificationVerdict(StrEnum):
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"
    NOT_TESTABLE = "NOT_TESTABLE"


class GateOperator(StrEnum):
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="


def _mapping_copy(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    copied = thaw_json(value)
    if not isinstance(copied, dict):
        raise TypeError(f"{label} must be a JSON object")
    return copied


def _accounting_copy(
    result: EconomicRunResult | FormalBenchmarkResult,
) -> dict[str, Any]:
    return _mapping_copy(result.accounting, "economic accounting")


def _finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{label} must be finite")
    return converted


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


@dataclass(frozen=True)
class DataIntervalIdentity:
    dataset_evidence_id: str
    dataset_content_sha256: str
    start_ms: int
    end_ms: int
    observation_count: int

    def __post_init__(self) -> None:
        if not self.dataset_evidence_id.strip():
            raise ValueError("dataset_evidence_id is required")
        if not _valid_sha256(self.dataset_content_sha256):
            raise ValueError("dataset_content_sha256 must be SHA-256")
        if type(self.start_ms) is not int or type(self.end_ms) is not int:
            raise TypeError("data interval boundaries must be integers")
        if self.start_ms <= 0 or self.end_ms <= self.start_ms:
            raise ValueError("data interval must be positive and increasing")
        if type(self.observation_count) is not int or self.observation_count <= 0:
            raise ValueError("observation_count must be positive")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkMatchingRules:
    match_entry_count: bool
    match_direction_counts: bool
    maximum_mean_holding_error_fraction: float | None
    maximum_time_exposure_error_fraction: float | None
    maximum_average_notional_error_fraction: float | None

    def __post_init__(self) -> None:
        if (
            type(self.match_entry_count) is not bool
            or type(self.match_direction_counts) is not bool
        ):
            raise TypeError("benchmark count matching flags must be booleans")
        for name in (
            "maximum_mean_holding_error_fraction",
            "maximum_time_exposure_error_fraction",
            "maximum_average_notional_error_fraction",
        ):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"{name} must be finite and nonnegative when specified")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EconomicHurdle:
    gate_id: str
    metric: str
    operator: GateOperator
    threshold: float
    random_quantile: float | None = None

    def __post_init__(self) -> None:
        if not self.gate_id.strip() or not self.metric.strip():
            raise ValueError("hurdle gate_id and metric are required")
        allowed_metrics = {
            "NET_RETURN_PCT",
            "MAX_DRAWDOWN_PCT",
            "PROFIT_FACTOR",
            "SHARPE_RATIO",
            "EXCESS_RETURN_VS_CASH",
            "EXCESS_RETURN_VS_PASSIVE",
            "EXCESS_RETURN_VS_RANDOM_QUANTILE",
        }
        if self.metric not in allowed_metrics:
            raise ValueError(f"unsupported economic hurdle metric: {self.metric}")
        if not isinstance(self.operator, GateOperator):
            object.__setattr__(self, "operator", GateOperator(self.operator))
        if not math.isfinite(self.threshold):
            raise ValueError("hurdle threshold must be finite")
        if self.metric == "EXCESS_RETURN_VS_RANDOM_QUANTILE":
            if self.random_quantile is None or not 0.0 <= self.random_quantile <= 1.0:
                raise ValueError("random comparison hurdle requires an explicit quantile")
        elif self.random_quantile is not None:
            raise ValueError("random_quantile is only valid for random comparison hurdles")

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "metric": self.metric,
            "operator": self.operator.value,
            "threshold": self.threshold,
            "random_quantile": self.random_quantile,
        }


@dataclass(frozen=True)
class ComparisonContract:
    """Deeply immutable, preregistered formal benchmark and hurdle contract."""

    contract_name: str
    contract_version: str
    product_scope: tuple[str, ...]
    benchmark_vehicle: str
    initial_capital: float
    data_interval: DataIntervalIdentity
    candidate_policy: VersionedIdentity
    cost_model: VersionedIdentity
    execution_model: VersionedIdentity
    funding_model: VersionedIdentity
    metrics_contract: ReturnMetricsContract
    terminal_policy: TerminalPolicy
    required_benchmarks: tuple[BenchmarkKind, ...]
    descriptive_benchmarks: tuple[BenchmarkKind, ...]
    randomization_unit: str
    eligible_opportunity_set_sha256: str | None
    random_seed: int
    random_trials: int
    matching_rules: BenchmarkMatchingRules
    hurdles: tuple[EconomicHurdle, ...]
    evidence_requirements: tuple[str, ...]
    result_schema_version: str = P6_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.contract_name.strip() or not self.contract_version.strip():
            raise ValueError("comparison contract name and version are required")
        scope = tuple(str(item) for item in self.product_scope)
        if not scope or any(not item.strip() for item in scope):
            raise ValueError("comparison product_scope is required")
        object.__setattr__(self, "product_scope", scope)
        if len(scope) != 1:
            raise ValueError("formal P6 comparison supports exactly one product")
        if self.benchmark_vehicle != f"{scope[0]}_LINEAR_PERPETUAL":
            raise ValueError("benchmark_vehicle must match the sole product scope")
        if not math.isfinite(self.initial_capital) or self.initial_capital <= 0:
            raise ValueError("initial_capital must be finite and positive")
        if not isinstance(self.terminal_policy, TerminalPolicy):
            object.__setattr__(self, "terminal_policy", TerminalPolicy(self.terminal_policy))
        required = tuple(BenchmarkKind(item) for item in self.required_benchmarks)
        descriptive = tuple(BenchmarkKind(item) for item in self.descriptive_benchmarks)
        if len(set(required)) != len(required) or len(set(descriptive)) != len(descriptive):
            raise ValueError("benchmark lists cannot contain duplicates")
        if set(required) & set(descriptive):
            raise ValueError("a benchmark cannot be both required and descriptive")
        object.__setattr__(self, "required_benchmarks", required)
        object.__setattr__(self, "descriptive_benchmarks", descriptive)
        if not self.randomization_unit.strip():
            raise ValueError("randomization_unit must be explicitly declared")
        if BenchmarkKind.RANDOM_MATCHED in set(required + descriptive):
            if self.eligible_opportunity_set_sha256 is None or not _valid_sha256(
                self.eligible_opportunity_set_sha256
            ):
                raise ValueError("random benchmark requires a bound eligible opportunity-set hash")
        elif self.eligible_opportunity_set_sha256 is not None and not _valid_sha256(
            self.eligible_opportunity_set_sha256
        ):
            raise ValueError("eligible opportunity-set hash must be SHA-256")
        if type(self.random_seed) is not int:
            raise TypeError("random_seed must be an integer")
        if type(self.random_trials) is not int or self.random_trials < 0:
            raise ValueError("random_trials must be a nonnegative integer")
        if BenchmarkKind.RANDOM_MATCHED in set(required + descriptive) and self.random_trials <= 0:
            raise ValueError("random benchmark requires a positive preregistered trial count")
        if not self.hurdles:
            raise ValueError("formal comparison requires explicitly preregistered hurdles")
        hurdles = tuple(self.hurdles)
        if any(not isinstance(item, EconomicHurdle) for item in hurdles):
            raise TypeError("comparison hurdles must be EconomicHurdle instances")
        if len({item.gate_id for item in hurdles}) != len(hurdles):
            raise ValueError("comparison hurdle gate ids must be unique")
        object.__setattr__(self, "hurdles", hurdles)
        if not isinstance(self.data_interval, DataIntervalIdentity):
            raise TypeError("data_interval must be DataIntervalIdentity")
        for name in (
            "candidate_policy",
            "cost_model",
            "execution_model",
            "funding_model",
        ):
            if not isinstance(getattr(self, name), VersionedIdentity):
                raise TypeError(f"{name} must be VersionedIdentity")
        if not isinstance(self.metrics_contract, ReturnMetricsContract):
            raise TypeError("metrics_contract must be ReturnMetricsContract")
        if not isinstance(self.matching_rules, BenchmarkMatchingRules):
            raise TypeError("matching_rules must be BenchmarkMatchingRules")
        selected = set(required + descriptive)
        benchmark_metrics = {
            "EXCESS_RETURN_VS_CASH": BenchmarkKind.CASH,
            "EXCESS_RETURN_VS_PASSIVE": BenchmarkKind.PASSIVE_PERPETUAL,
            "EXCESS_RETURN_VS_RANDOM_QUANTILE": BenchmarkKind.RANDOM_MATCHED,
        }
        for hurdle in hurdles:
            dependency = benchmark_metrics.get(hurdle.metric)
            if dependency is not None and dependency not in selected:
                raise ValueError(
                    f"hurdle {hurdle.gate_id} requires selected benchmark {dependency.value}"
                )
        requirements = tuple(str(item) for item in self.evidence_requirements)
        if not requirements or any(not item.strip() for item in requirements):
            raise ValueError("evidence_requirements must be explicit")
        object.__setattr__(self, "evidence_requirements", requirements)
        if self.result_schema_version != P6_RESULT_SCHEMA_VERSION:
            raise ValueError("unsupported qualification result schema")
        canonical_json(self.semantic_payload())

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "result_schema_version": self.result_schema_version,
            "contract_name": self.contract_name,
            "contract_version": self.contract_version,
            "product_scope": list(self.product_scope),
            "benchmark_vehicle": self.benchmark_vehicle,
            "initial_capital": self.initial_capital,
            "data_interval": self.data_interval.to_dict(),
            "candidate_policy": self.candidate_policy.to_dict(),
            "cost_model": self.cost_model.to_dict(),
            "execution_model": self.execution_model.to_dict(),
            "funding_model": self.funding_model.to_dict(),
            "metrics_contract": self.metrics_contract.to_dict(),
            "terminal_policy": self.terminal_policy.value,
            "required_benchmarks": [item.value for item in self.required_benchmarks],
            "descriptive_benchmarks": [item.value for item in self.descriptive_benchmarks],
            "randomization_unit": self.randomization_unit,
            "eligible_opportunity_set_sha256": self.eligible_opportunity_set_sha256,
            "random_seed": self.random_seed,
            "random_trials": self.random_trials,
            "matching_rules": self.matching_rules.to_dict(),
            "hurdles": [item.to_dict() for item in self.hurdles],
            "evidence_requirements": list(self.evidence_requirements),
        }

    @property
    def contract_hash(self) -> str:
        return canonical_sha256(self.semantic_payload())

    @property
    def contract_id(self) -> str:
        return f"{self.contract_name}@{self.contract_hash}"

    @property
    def versioned_identity(self) -> VersionedIdentity:
        return VersionedIdentity(self.contract_name, self.contract_version, self.contract_hash)


@dataclass(frozen=True)
class EligibleOpportunity:
    opportunity_id: str
    timestamp_ms: int
    metadata: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        if not self.opportunity_id.strip():
            raise ValueError("opportunity_id is required")
        if type(self.timestamp_ms) is not int or self.timestamp_ms <= 0:
            raise ValueError("opportunity timestamp must be positive")
        object.__setattr__(self, "metadata", FrozenDict(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "timestamp_ms": self.timestamp_ms,
            "metadata": thaw_json(self.metadata),
        }


def eligible_opportunity_set_sha256(
    opportunities: Sequence[EligibleOpportunity],
) -> str:
    ordered = sorted(opportunities, key=lambda item: (item.timestamp_ms, item.opportunity_id))
    return canonical_sha256([item.to_dict() for item in ordered])


@dataclass(frozen=True)
class EconomicRunIdentity:
    experiment_revision_id: str
    protocol_hash: str
    input_contract: VersionedIdentity
    dataset_evidence_id: str
    dataset_content_sha256: str
    interval_start_ms: int
    interval_end_ms: int
    observation_count: int
    signal_set_sha256: str
    decision_input_set_sha256: str
    funding_event_set_sha256: str
    product_scope: tuple[str, ...]
    initial_capital: float
    economic_policy: VersionedIdentity
    cost_model: VersionedIdentity
    execution_model: VersionedIdentity
    funding_model: VersionedIdentity
    comparison_contract_id: str
    comparison_contract_hash: str
    terminal_policy: TerminalPolicy
    metrics_contract_id: str
    metrics_contract_hash: str
    code_revision: str
    completeness: ResultCompleteness
    replay_input_bundle_sha256: str | None = None
    signal_producer_contract: VersionedIdentity | None = None
    run_role: EconomicRunRole | str = EconomicRunRole.CANDIDATE

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_scope", tuple(self.product_scope))
        if not isinstance(self.terminal_policy, TerminalPolicy):
            object.__setattr__(self, "terminal_policy", TerminalPolicy(self.terminal_policy))
        if not isinstance(self.completeness, ResultCompleteness):
            object.__setattr__(self, "completeness", ResultCompleteness(self.completeness))
        if not isinstance(self.run_role, EconomicRunRole):
            try:
                object.__setattr__(self, "run_role", EconomicRunRole(self.run_role))
            except ValueError as exc:
                raise ValueError(f"unsupported economic run role: {self.run_role}") from exc
        for value, label in (
            (self.protocol_hash, "protocol_hash"),
            (self.dataset_content_sha256, "dataset_content_sha256"),
            (self.signal_set_sha256, "signal_set_sha256"),
            (self.decision_input_set_sha256, "decision_input_set_sha256"),
            (self.funding_event_set_sha256, "funding_event_set_sha256"),
            (self.comparison_contract_hash, "comparison_contract_hash"),
            (self.metrics_contract_hash, "metrics_contract_hash"),
        ):
            if not _valid_sha256(value):
                raise ValueError(f"{label} must be SHA-256")
        if self.replay_input_bundle_sha256 is not None and not _valid_sha256(
            self.replay_input_bundle_sha256
        ):
            raise ValueError("replay_input_bundle_sha256 must be SHA-256")
        for value, label in (
            (self.experiment_revision_id, "experiment_revision_id"),
            (self.dataset_evidence_id, "dataset_evidence_id"),
            (self.comparison_contract_id, "comparison_contract_id"),
            (self.metrics_contract_id, "metrics_contract_id"),
            (self.code_revision, "code_revision"),
        ):
            if not value.strip():
                raise ValueError(f"{label} is required")
        if (
            type(self.interval_start_ms) is not int
            or type(self.interval_end_ms) is not int
            or self.interval_start_ms <= 0
            or self.interval_end_ms <= self.interval_start_ms
        ):
            raise ValueError("run interval must be positive and increasing")
        if type(self.observation_count) is not int or self.observation_count <= 0:
            raise ValueError("run observation_count must be positive")
        if not math.isfinite(self.initial_capital) or self.initial_capital <= 0:
            raise ValueError("run initial capital must be finite and positive")
        if not self.product_scope or any(not item.strip() for item in self.product_scope):
            raise ValueError("run product_scope is required")
        canonical_json(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "experiment_revision_id": self.experiment_revision_id,
            "protocol_hash": self.protocol_hash,
            "input_contract": self.input_contract.to_dict(),
            "dataset_evidence_id": self.dataset_evidence_id,
            "dataset_content_sha256": self.dataset_content_sha256,
            "interval_start_ms": self.interval_start_ms,
            "interval_end_ms": self.interval_end_ms,
            "observation_count": self.observation_count,
            "signal_set_sha256": self.signal_set_sha256,
            "decision_input_set_sha256": self.decision_input_set_sha256,
            "funding_event_set_sha256": self.funding_event_set_sha256,
            "product_scope": list(self.product_scope),
            "initial_capital": self.initial_capital,
            "economic_policy": self.economic_policy.to_dict(),
            "cost_model": self.cost_model.to_dict(),
            "execution_model": self.execution_model.to_dict(),
            "funding_model": self.funding_model.to_dict(),
            "comparison_contract_id": self.comparison_contract_id,
            "comparison_contract_hash": self.comparison_contract_hash,
            "terminal_policy": self.terminal_policy.value,
            "metrics_contract_id": self.metrics_contract_id,
            "metrics_contract_hash": self.metrics_contract_hash,
            "code_revision": self.code_revision,
            "completeness": self.completeness.value,
            "replay_input_bundle_sha256": self.replay_input_bundle_sha256,
            "run_role": EconomicRunRole(self.run_role).value,
        }
        if self.signal_producer_contract is not None:
            payload["signal_producer_contract"] = self.signal_producer_contract.to_dict()
        return payload

    @property
    def run_id(self) -> str:
        return f"economic-run@{canonical_sha256(self.to_dict())}"


@dataclass(frozen=True)
class EconomicRunResult:
    identity: EconomicRunIdentity
    accounting: FrozenDict

    def __post_init__(self) -> None:
        if not isinstance(self.identity, EconomicRunIdentity):
            raise TypeError("identity must be EconomicRunIdentity")
        object.__setattr__(self, "accounting", FrozenDict(self.accounting))
        canonical_json(self.semantic_payload())

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "run_identity": self.identity.to_dict(),
            "accounting": thaw_json(self.accounting),
        }

    @property
    def result_hash(self) -> str:
        return canonical_sha256(self.semantic_payload())

    @property
    def result_id(self) -> str:
        return f"economic-run-result@{self.result_hash}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "P6_ECONOMIC_RUN",
            "schema_version": P6_RESULT_SCHEMA_VERSION,
            "result_id": self.result_id,
            "semantic_payload": self.semantic_payload(),
        }

    def write(self, path: str | Path) -> Path:
        return _atomic_write_json(path, self.to_dict())


@dataclass(frozen=True)
class FormalBenchmarkResult:
    benchmark_kind: BenchmarkKind
    vehicle: str
    accounting: FrozenDict
    comparable: bool
    matching_diagnostics: FrozenDict
    trial_id: int | None = None
    seed: int | None = None
    run_result_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.benchmark_kind, BenchmarkKind):
            object.__setattr__(self, "benchmark_kind", BenchmarkKind(self.benchmark_kind))
        if not self.vehicle.strip():
            raise ValueError("benchmark vehicle is required")
        object.__setattr__(self, "accounting", FrozenDict(self.accounting))
        object.__setattr__(self, "matching_diagnostics", FrozenDict(self.matching_diagnostics))
        if type(self.comparable) is not bool:
            raise TypeError("benchmark comparable flag must be boolean")
        if self.trial_id is not None and (type(self.trial_id) is not int or self.trial_id < 0):
            raise ValueError("benchmark trial_id must be nonnegative")
        if self.seed is not None and type(self.seed) is not int:
            raise TypeError("benchmark seed must be an integer")
        canonical_json(self.semantic_payload())

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "benchmark_kind": self.benchmark_kind.value,
            "vehicle": self.vehicle,
            "accounting": thaw_json(self.accounting),
            "comparable": self.comparable,
            "matching_diagnostics": thaw_json(self.matching_diagnostics),
            "trial_id": self.trial_id,
            "seed": self.seed,
            "run_result_id": self.run_result_id,
        }

    @property
    def result_id(self) -> str:
        return f"benchmark-result@{canonical_sha256(self.semantic_payload())}"

    def to_dict(self) -> dict[str, Any]:
        return {"result_id": self.result_id, **self.semantic_payload()}


@dataclass(frozen=True)
class RandomBenchmarkDistribution:
    seed: int
    trials: tuple[FormalBenchmarkResult, ...]

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("random distribution seed must be an integer")
        values = tuple(self.trials)
        if any(item.benchmark_kind is not BenchmarkKind.RANDOM_MATCHED for item in values):
            raise ValueError("random distribution can only contain random trials")
        if any(item.trial_id != index for index, item in enumerate(values)):
            raise ValueError("random trial ids must be contiguous from zero")
        object.__setattr__(self, "trials", values)
        canonical_json(self.to_dict())

    @property
    def comparable(self) -> bool:
        return bool(self.trials) and all(item.comparable for item in self.trials)

    @property
    def net_returns(self) -> tuple[float, ...]:
        return tuple(
            _finite_float(_accounting_copy(item).get("net_return_pct"), "net_return_pct")
            for item in self.trials
        )

    def quantile(self, probability: float) -> float | None:
        if not self.trials or not 0.0 <= probability <= 1.0:
            return None
        values = sorted(self.net_returns)
        position = probability * (len(values) - 1)
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return values[lower]
        weight = position - lower
        return values[lower] * (1.0 - weight) + values[upper] * weight

    def to_dict(self) -> dict[str, Any]:
        returns = self.net_returns
        return {
            "distribution_id": self.distribution_id,
            "seed": self.seed,
            "trial_count": len(self.trials),
            "comparable": self.comparable,
            "aggregate": {
                "mean_net_return_pct": sum(returns) / len(returns) if returns else None,
                "minimum_net_return_pct": min(returns) if returns else None,
                "maximum_net_return_pct": max(returns) if returns else None,
            },
            "trials": [item.to_dict() for item in self.trials],
        }

    @property
    def distribution_id(self) -> str:
        payload = {
            "seed": self.seed,
            "trials": [item.to_dict() for item in self.trials],
        }
        return f"random-distribution@{canonical_sha256(payload)}"


@dataclass(frozen=True)
class FormalBenchmarkSuite:
    comparison_contract_id: str
    candidate_run_result_id: str
    eligible_opportunity_set_sha256: str | None
    cash: FormalBenchmarkResult | None
    passive: FormalBenchmarkResult | None
    random: RandomBenchmarkDistribution | None

    def __post_init__(self) -> None:
        if not self.comparison_contract_id.strip() or not self.candidate_run_result_id.strip():
            raise ValueError("benchmark suite binding identities are required")
        if self.eligible_opportunity_set_sha256 is not None and not _valid_sha256(
            self.eligible_opportunity_set_sha256
        ):
            raise ValueError("benchmark suite opportunity-set hash must be SHA-256")
        if self.cash is not None and self.cash.benchmark_kind is not BenchmarkKind.CASH:
            raise ValueError("cash benchmark slot contains the wrong benchmark kind")
        if (
            self.passive is not None
            and self.passive.benchmark_kind is not BenchmarkKind.PASSIVE_PERPETUAL
        ):
            raise ValueError("passive benchmark slot contains the wrong benchmark kind")
        if self.random is not None and any(
            item.benchmark_kind is not BenchmarkKind.RANDOM_MATCHED for item in self.random.trials
        ):
            raise ValueError("random benchmark slot contains the wrong benchmark kind")
        canonical_json(self.to_dict())

    def result_ids(self) -> tuple[str, ...]:
        values: list[str] = []
        if self.cash is not None:
            values.append(self.cash.result_id)
        if self.passive is not None:
            values.append(self.passive.result_id)
        if self.random is not None:
            values.append(self.random.distribution_id)
            values.extend(item.result_id for item in self.random.trials)
        return tuple(values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "P6_BENCHMARK_SUITE",
            "schema_version": P6_RESULT_SCHEMA_VERSION,
            "suite_id": self.suite_id,
            "comparison_contract_id": self.comparison_contract_id,
            "candidate_run_result_id": self.candidate_run_result_id,
            "eligible_opportunity_set_sha256": self.eligible_opportunity_set_sha256,
            "cash": self.cash.to_dict() if self.cash is not None else None,
            "passive": self.passive.to_dict() if self.passive is not None else None,
            "random": self.random.to_dict() if self.random is not None else None,
        }

    @property
    def suite_id(self) -> str:
        payload = {
            "comparison_contract_id": self.comparison_contract_id,
            "candidate_run_result_id": self.candidate_run_result_id,
            "eligible_opportunity_set_sha256": self.eligible_opportunity_set_sha256,
            "cash": self.cash.to_dict() if self.cash is not None else None,
            "passive": self.passive.to_dict() if self.passive is not None else None,
            "random": self.random.to_dict() if self.random is not None else None,
        }
        return f"benchmark-suite@{canonical_sha256(payload)}"

    def write(self, path: str | Path) -> Path:
        return _atomic_write_json(path, self.to_dict())


@dataclass(frozen=True)
class QualificationGateResult:
    gate_id: str
    metric: str
    observed_value: float | None
    operator: GateOperator
    hurdle: float
    testable: bool
    passed: bool | None
    reason_code: str

    def __post_init__(self) -> None:
        if not self.gate_id.strip() or not self.metric.strip() or not self.reason_code.strip():
            raise ValueError("qualification gate identifiers and reason are required")
        if not isinstance(self.operator, GateOperator):
            object.__setattr__(self, "operator", GateOperator(self.operator))
        if not math.isfinite(self.hurdle):
            raise ValueError("qualification gate hurdle must be finite")
        if self.observed_value is not None and not math.isfinite(self.observed_value):
            raise ValueError("qualification observed value must be finite when available")
        if type(self.testable) is not bool:
            raise TypeError("qualification gate testable must be boolean")
        if self.testable and type(self.passed) is not bool:
            raise ValueError("testable qualification gates require a boolean result")
        if not self.testable and self.passed is not None:
            raise ValueError("untestable qualification gates cannot pass or fail")

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "metric": self.metric,
            "observed_value": self.observed_value,
            "operator": self.operator.value,
            "hurdle": self.hurdle,
            "testable": self.testable,
            "passed": self.passed,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class EconomicQualificationResult:
    experiment_revision_id: str
    protocol_hash: str
    comparison_contract_id: str
    comparison_contract_hash: str
    comparison_contract: FrozenDict
    run_result: EconomicRunResult
    benchmark_suite: FormalBenchmarkSuite
    gates: tuple[QualificationGateResult, ...]
    verdict: QualificationVerdict
    reason_codes: tuple[str, ...]
    required_evidence_ids: tuple[str, ...]
    code_revision: str
    product_scope: tuple[str, ...]
    terminal_policy: TerminalPolicy
    generated_at_utc: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_contract", FrozenDict(self.comparison_contract))
        object.__setattr__(self, "gates", tuple(self.gates))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "required_evidence_ids", tuple(self.required_evidence_ids))
        object.__setattr__(self, "product_scope", tuple(self.product_scope))
        if not isinstance(self.verdict, QualificationVerdict):
            object.__setattr__(self, "verdict", QualificationVerdict(self.verdict))
        if not isinstance(self.terminal_policy, TerminalPolicy):
            object.__setattr__(self, "terminal_policy", TerminalPolicy(self.terminal_policy))
        if not _valid_sha256(self.protocol_hash) or not _valid_sha256(
            self.comparison_contract_hash
        ):
            raise ValueError("qualification protocol/comparison hashes must be SHA-256")
        if canonical_sha256(thaw_json(self.comparison_contract)) != (self.comparison_contract_hash):
            raise ValueError("qualification comparison contract content/hash mismatch")
        if self.run_result.identity.experiment_revision_id != self.experiment_revision_id:
            raise ValueError("qualification run experiment binding mismatch")
        if self.run_result.identity.protocol_hash != self.protocol_hash:
            raise ValueError("qualification run protocol binding mismatch")
        if self.run_result.identity.comparison_contract_id != self.comparison_contract_id:
            raise ValueError("qualification run comparison binding mismatch")
        if self.benchmark_suite.comparison_contract_id != self.comparison_contract_id:
            raise ValueError("qualification benchmark comparison binding mismatch")
        if self.benchmark_suite.candidate_run_result_id != self.run_result.result_id:
            raise ValueError("qualification benchmark candidate binding mismatch")
        if not self.reason_codes or any(not item.strip() for item in self.reason_codes):
            raise ValueError("qualification reason codes are required")
        if not self.required_evidence_ids or len(set(self.required_evidence_ids)) != len(
            self.required_evidence_ids
        ):
            raise ValueError("qualification required evidence ids must be non-empty and unique")
        if self.verdict is QualificationVerdict.QUALIFIED and not all(
            gate.testable and gate.passed is True for gate in self.gates
        ):
            raise ValueError("QUALIFIED verdict requires every gate to pass")
        if self.verdict is QualificationVerdict.REJECTED and not (
            all(gate.testable for gate in self.gates)
            and any(gate.passed is False for gate in self.gates)
        ):
            raise ValueError("REJECTED verdict requires a testable failed gate")
        if (
            self.verdict is QualificationVerdict.NOT_TESTABLE
            and all(gate.testable for gate in self.gates)
            and self.run_result.identity.completeness is ResultCompleteness.COMPLETE
        ):
            selected = {
                BenchmarkKind.CASH: self.benchmark_suite.cash,
                BenchmarkKind.PASSIVE_PERPETUAL: self.benchmark_suite.passive,
                BenchmarkKind.RANDOM_MATCHED: self.benchmark_suite.random,
            }
            contract = thaw_json(self.comparison_contract)
            if not isinstance(contract, dict):
                raise ValueError("qualification comparison contract must be an object")
            required = contract.get("required_benchmarks")
            if isinstance(required, list) and all(
                selected.get(BenchmarkKind(item)) is not None
                and bool(getattr(selected[BenchmarkKind(item)], "comparable", False))
                for item in required
            ):
                raise ValueError("NOT_TESTABLE verdict requires an explicit testability failure")
        canonical_json(self.to_dict())

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "experiment_revision_id": self.experiment_revision_id,
            "protocol_hash": self.protocol_hash,
            "comparison_contract_id": self.comparison_contract_id,
            "comparison_contract_hash": self.comparison_contract_hash,
            "comparison_contract": thaw_json(self.comparison_contract),
            "run_result_id": self.run_result.result_id,
            "run_result": self.run_result.to_dict(),
            "benchmark_suite_id": self.benchmark_suite.suite_id,
            "benchmark_result_ids": list(self.benchmark_suite.result_ids()),
            "benchmark_suite": self.benchmark_suite.to_dict(),
            "metric_values": _candidate_metrics(self.run_result),
            "gates": [item.to_dict() for item in self.gates],
            "verdict": self.verdict.value,
            "reason_codes": list(self.reason_codes),
            "required_evidence_ids": list(self.required_evidence_ids),
            "code_revision": self.code_revision,
            "product_scope": list(self.product_scope),
            "terminal_policy": self.terminal_policy.value,
        }

    @property
    def result_hash(self) -> str:
        return canonical_sha256(self.semantic_payload())

    @property
    def result_id(self) -> str:
        return f"economic-qualification@{self.result_hash}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": P6_RESULT_EVIDENCE_TYPE,
            "schema_version": P6_RESULT_SCHEMA_VERSION,
            "result_id": self.result_id,
            "semantic_payload": self.semantic_payload(),
            "audit": {"generated_at_utc": self.generated_at_utc},
        }

    def write(self, path: str | Path) -> Path:
        return _atomic_write_json(path, self.to_dict())

    def decision_attestation(
        self, result_evidence: EvidenceReference
    ) -> EconomicDecisionAttestation:
        """Describe the exact P6 artifact for the registry's generic boundary."""
        if result_evidence.evidence_type != P6_RESULT_EVIDENCE_TYPE:
            raise ValueError("qualification result evidence has the wrong evidence type")
        return EconomicDecisionAttestation(
            experiment_revision_id=self.experiment_revision_id,
            protocol_hash=self.protocol_hash,
            result_evidence_id=result_evidence.evidence_id,
            result_artifact_sha256=result_evidence.content_sha256,
            result_id=self.result_id,
            result_hash=self.result_hash,
            result_schema_version=P6_RESULT_SCHEMA_VERSION,
            verdict=self.verdict.value,
            comparison_contract_id=self.comparison_contract_id,
            comparison_contract_hash=self.comparison_contract_hash,
            run_result_id=self.run_result.result_id,
            benchmark_suite_id=self.benchmark_suite.suite_id,
            benchmark_result_ids=self.benchmark_suite.result_ids(),
            required_evidence_ids=self.required_evidence_ids,
            code_revision=self.code_revision,
            product_scope=self.product_scope,
            terminal_policy=self.terminal_policy.value,
        )


def policy_identity(policy: TradePolicy, version: str) -> VersionedIdentity:
    return VersionedIdentity.from_payload(policy.policy_id, version, policy.to_dict())


def fee_model_identity(model: FeeModel, logical_id: str, version: str) -> VersionedIdentity:
    return VersionedIdentity.from_payload(logical_id, version, asdict(model))


def execution_model_identity(
    model: ExecutionModel, logical_id: str, version: str
) -> VersionedIdentity:
    payload = {
        "decision_latency_ms": model.decision_latency_ms,
        "exchange_latency_ms": model.exchange_latency_ms,
        "limit_fill_prob_on_touch": model.limit_fill_prob_on_touch,
        "fee_model_sha256": canonical_sha256(asdict(model.fee_model)),
    }
    if model.order_submission_latency_ms != 0:
        payload["order_submission_latency_ms"] = model.order_submission_latency_ms
    return VersionedIdentity.from_payload(logical_id, version, payload)


def funding_model_identity(model: FundingModel, logical_id: str, version: str) -> VersionedIdentity:
    return VersionedIdentity.from_payload(logical_id, version, asdict(model))


def execute_bound_run(
    *,
    protocol: ExperimentMetadata,
    comparison: ComparisonContract,
    dataset_evidence: EvidenceReference,
    engine: EconomicSimulationEngine,
    candles: Sequence[Candle],
    signals: Sequence[InformationSignal],
    replay_input_bundle: ReplayInputBundle | Mapping[str, Any] | None = None,
    decision_input_bindings: Sequence[Mapping[str, Any]] = (),
    funding_events: Sequence[FundingSettlement] = (),
    run_role: EconomicRunRole | str = EconomicRunRole.CANDIDATE,
) -> EconomicRunResult:
    _validate_protocol_and_runtime(protocol, comparison, dataset_evidence, engine, candles)
    if not isinstance(run_role, EconomicRunRole):
        try:
            effective_role = EconomicRunRole(run_role)
        except ValueError as exc:
            raise ValueError(f"unsupported economic run role: {run_role}") from exc
    else:
        effective_role = run_role

    if any(signal.experiment_id != protocol.experiment_revision_id for signal in signals):
        raise ValueError("formal signals must bind the exact experiment revision")
    if any(
        signal.timestamp_ms < comparison.data_interval.start_ms
        or signal.timestamp_ms > comparison.data_interval.end_ms
        for signal in signals
    ):
        raise ValueError("formal signal lies outside the comparison interval")
    if any(
        event.timestamp_ms < comparison.data_interval.start_ms
        or event.timestamp_ms > comparison.data_interval.end_ms
        for event in funding_events
    ):
        raise ValueError("funding event lies outside the comparison interval")
    signal_payload = [
        item.to_dict()
        for item in sorted(signals, key=lambda item: (item.timestamp_ms, item.signal_id))
    ]

    validated_bundle: dict[str, Any] | None = None
    if signals:
        if effective_role == EconomicRunRole.CANDIDATE:
            if protocol.signal_producer_contract is None:
                raise ValueError(
                    "formal run with signals requires protocol.signal_producer_contract; "
                    "missing protocol contract cannot authorize formal economic qualification"
                )
        if replay_input_bundle is not None:
            bundle_dict = (
                replay_input_bundle.to_dict()
                if isinstance(replay_input_bundle, ReplayInputBundle)
                else dict(replay_input_bundle)
            )
            validated_bundle = validate_formal_replay_input_bundle(
                bundle_dict,
                candles=candles,
                expected_protocol=protocol,
                expected_dataset_evidence=dataset_evidence,
                expected_signals=signals,
                expected_role=effective_role,
            )
            normalized_decision_inputs = ReplayInputBundle(**validated_bundle).legacy_decision_bindings()
            decision_input_set_sha256 = canonical_sha256(
                {
                    "schema_version": FORMAL_DECISION_INPUT_SCHEMA_VERSION,
                    "bindings": normalized_decision_inputs,
                }
            )
        elif decision_input_bindings:
            # Legacy decision bindings provided without verified replay bundle (T4 attack)
            raise ValueError(
                "formal run requires a verified ReplayInputBundle; legacy decision-input bindings alone cannot authorize formal economic qualification"
            )
        else:
            # Missing replay bundle completely (T3)
            raise ValueError(
                "formal run with signals requires a verified ReplayInputBundle; proofs do not exactly cover signals"
            )
    else:
        decision_input_set_sha256 = canonical_sha256(
            {"schema_version": FORMAL_REPLAY_INPUT_BUNDLE_SCHEMA_VERSION, "empty": True}
        )
        normalized_decision_inputs = []

    funding_payload = [
        asdict(item) for item in sorted(funding_events, key=lambda item: item.timestamp_ms)
    ]
    summary = engine.simulate(
        candles,
        signals,
        funding_events,
        metrics_contract=comparison.metrics_contract,
        terminal_policy=comparison.terminal_policy,
    )

    causal_execution_inputs = []
    for event in summary.trade_events:
        evidence = event.metadata.get("liquidity_evidence")
        if evidence:
            causal_execution_inputs.append(
                {
                    "trade_id": event.trade_id,
                    "timestamp_ms": event.timestamp_ms,
                    "action": event.action.value,
                    "quantity": event.quantity,
                    "price": event.price,
                    "liquidity_evidence": evidence,
                    "causal_liquidity_volume_base": event.metadata.get("causal_liquidity_volume_base"),
                    "causal_liquidity_available_at_ms": event.metadata.get(
                        "causal_liquidity_available_at_ms"
                    ),
                    "completed_liquidity_volume_base": event.metadata.get(
                        "completed_liquidity_volume_base"
                    ),
                    "declared_max_slippage_bps": event.metadata.get("declared_max_slippage_bps"),
                }
            )

    bundle_payload: dict[str, Any] | None = None
    replay_input_bundle_sha256: str | None = None
    if validated_bundle is not None:
        bundle_payload = dict(validated_bundle)
        if causal_execution_inputs:
            declared_exec_inputs = bundle_payload.get("causal_execution_inputs")
            if declared_exec_inputs:
                if list(declared_exec_inputs) != list(causal_execution_inputs):
                    raise ValueError(
                        "bundle causal_execution_inputs mismatch with actual simulation execution observations"
                    )
            else:
                bundle_payload["causal_execution_inputs"] = tuple(causal_execution_inputs)
                recomputed = ReplayInputBundle(
                    schema_version=bundle_payload["schema_version"],
                    experiment_revision_id=bundle_payload["experiment_revision_id"],
                    protocol_hash=bundle_payload["protocol_hash"],
                    dataset_evidence_id=bundle_payload["dataset_evidence_id"],
                    dataset_content_sha256=bundle_payload["dataset_content_sha256"],
                    input_contract_identity=bundle_payload["input_contract_identity"],
                    signal_set_sha256=bundle_payload["signal_set_sha256"],
                    decision_inputs=tuple(bundle_payload["decision_inputs"]),
                    causal_execution_inputs=tuple(bundle_payload["causal_execution_inputs"]),
                    funding_input_identity=bundle_payload["funding_input_identity"],
                )
                bundle_payload = recomputed.to_dict()
        replay_input_bundle_sha256 = bundle_payload["bundle_sha256"]

    if effective_role == EconomicRunRole.RANDOM_BENCHMARK:
        random_contract = SignalProducerRegistry.get_contract("CANONICAL_RANDOM_BENCHMARK_V1")
        if random_contract is None:
            raise ValueError("CANONICAL_RANDOM_BENCHMARK_V1 contract not found in registry")
        spc_identity = random_contract.to_versioned_identity()
    else:
        spc = protocol.signal_producer_contract
        spc_identity = None
        if spc is not None:
            if isinstance(spc, VersionedIdentity):
                spc_identity = spc
            elif hasattr(spc, "to_versioned_identity"):
                spc_identity = spc.to_versioned_identity()

    identity = EconomicRunIdentity(
        experiment_revision_id=protocol.experiment_revision_id,
        protocol_hash=protocol.protocol_hash,
        input_contract=protocol.input_contract,
        dataset_evidence_id=dataset_evidence.evidence_id,
        dataset_content_sha256=dataset_evidence.content_sha256,
        interval_start_ms=comparison.data_interval.start_ms,
        interval_end_ms=comparison.data_interval.end_ms,
        observation_count=len(candles),
        signal_set_sha256=canonical_sha256(signal_payload),
        decision_input_set_sha256=decision_input_set_sha256,
        funding_event_set_sha256=canonical_sha256(funding_payload),
        product_scope=protocol.product_scope,
        initial_capital=engine.initial_cash,
        economic_policy=protocol.economic_policy,
        cost_model=protocol.cost_model,
        execution_model=protocol.execution_model,
        funding_model=comparison.funding_model,
        comparison_contract_id=comparison.contract_id,
        comparison_contract_hash=comparison.contract_hash,
        terminal_policy=comparison.terminal_policy,
        metrics_contract_id=comparison.metrics_contract.contract_id,
        metrics_contract_hash=comparison.metrics_contract.contract_hash,
        code_revision=protocol.code_revision,
        completeness=summary.completeness,
        replay_input_bundle_sha256=replay_input_bundle_sha256,
        signal_producer_contract=spc_identity,
        run_role=effective_role,
    )
    accounting = bind_runtime_market_data(summary.to_dict(), candles)
    accounting["formal_decision_input_schema_version"] = (
        FORMAL_DECISION_INPUT_SCHEMA_VERSION
    )
    accounting["formal_decision_input_bindings"] = normalized_decision_inputs
    accounting["formal_decision_input_set_sha256"] = decision_input_set_sha256
    if bundle_payload is not None:
        accounting["formal_replay_input_bundle_schema_version"] = (
            FORMAL_REPLAY_INPUT_BUNDLE_SCHEMA_VERSION
        )
        accounting["formal_replay_input_bundle"] = bundle_payload
        accounting["formal_replay_input_bundle_sha256"] = bundle_payload["bundle_sha256"]
    accounting["formal_run_identity"] = identity.to_dict()
    verify_formal_accounting(
        accounting,
        product=protocol.product_scope[0],
        initial_cash=comparison.initial_capital,
        interval_start_ms=comparison.data_interval.start_ms,
        interval_end_ms=comparison.data_interval.end_ms,
        terminal_policy=comparison.terminal_policy,
        metrics_contract=comparison.metrics_contract,
    )
    return EconomicRunResult(identity=identity, accounting=FrozenDict(accounting))


def build_formal_benchmark_suite(
    *,
    protocol: ExperimentMetadata,
    comparison: ComparisonContract,
    dataset_evidence: EvidenceReference,
    candidate_run: EconomicRunResult,
    engine: EconomicSimulationEngine,
    candles: Sequence[Candle],
    eligible_opportunities: Sequence[EligibleOpportunity],
    funding_events: Sequence[FundingSettlement] = (),
) -> FormalBenchmarkSuite:
    _validate_candidate_run_binding(protocol, comparison, candidate_run)
    validate_persisted_decision_input_bindings(
        _accounting_copy(candidate_run),
        candles=candles,
        run_identity=candidate_run.identity.to_dict(),
    )
    opportunity_hash = eligible_opportunity_set_sha256(eligible_opportunities)
    if (
        BenchmarkKind.RANDOM_MATCHED
        in set(comparison.required_benchmarks + comparison.descriptive_benchmarks)
        and opportunity_hash != comparison.eligible_opportunity_set_sha256
    ):
        raise ValueError("eligible opportunity set does not match comparison contract")
    funding_payload = [
        asdict(item) for item in sorted(funding_events, key=lambda item: item.timestamp_ms)
    ]
    if canonical_sha256(funding_payload) != candidate_run.identity.funding_event_set_sha256:
        raise ValueError("benchmark funding-event set differs from candidate run")
    selected = set(comparison.required_benchmarks + comparison.descriptive_benchmarks)
    cash = (
        _cash_benchmark(comparison, candidate_run, candles)
        if BenchmarkKind.CASH in selected
        else None
    )
    passive = (
        _passive_perpetual_benchmark(comparison, candidate_run, engine, candles, funding_events)
        if BenchmarkKind.PASSIVE_PERPETUAL in selected
        else None
    )
    random_distribution = (
        _random_matched_benchmark(
            protocol,
            comparison,
            dataset_evidence,
            candidate_run,
            engine,
            candles,
            eligible_opportunities,
            funding_events,
        )
        if BenchmarkKind.RANDOM_MATCHED in selected
        else None
    )
    return FormalBenchmarkSuite(
        comparison_contract_id=comparison.contract_id,
        candidate_run_result_id=candidate_run.result_id,
        eligible_opportunity_set_sha256=(
            opportunity_hash if BenchmarkKind.RANDOM_MATCHED in selected else None
        ),
        cash=cash,
        passive=passive,
        random=random_distribution,
    )


def evaluate_formal_economic_qualification(
    *,
    protocol: ExperimentMetadata,
    comparison: ComparisonContract,
    candidate_run: EconomicRunResult,
    benchmarks: FormalBenchmarkSuite,
    required_evidence_ids: Sequence[str],
    generated_at_utc: str | None = None,
) -> EconomicQualificationResult:
    if protocol.benchmark == P6_PENDING or not isinstance(protocol.benchmark, VersionedIdentity):
        raise ValueError("P6_PENDING protocol cannot enter formal qualification")
    if protocol.benchmark != comparison.versioned_identity:
        raise ValueError("protocol benchmark identity does not match comparison contract")
    _validate_candidate_run_binding(protocol, comparison, candidate_run)
    if benchmarks.comparison_contract_id != comparison.contract_id:
        raise ValueError("benchmark suite is bound to a different comparison contract")
    if benchmarks.candidate_run_result_id != candidate_run.result_id:
        raise ValueError("benchmark suite is bound to a different candidate run")
    if BenchmarkKind.RANDOM_MATCHED in set(
        comparison.required_benchmarks + comparison.descriptive_benchmarks
    ) and benchmarks.eligible_opportunity_set_sha256 != (
        comparison.eligible_opportunity_set_sha256
    ):
        raise ValueError("benchmark suite opportunity set differs from comparison")

    reasons: list[str] = []
    if candidate_run.identity.completeness is not ResultCompleteness.COMPLETE:
        reasons.append("CANDIDATE_RUN_INCOMPLETE")
    available: dict[BenchmarkKind, bool] = {
        BenchmarkKind.CASH: benchmarks.cash is not None,
        BenchmarkKind.PASSIVE_PERPETUAL: benchmarks.passive is not None,
        BenchmarkKind.RANDOM_MATCHED: benchmarks.random is not None,
    }
    comparable: dict[BenchmarkKind, bool] = {
        BenchmarkKind.CASH: benchmarks.cash is not None and benchmarks.cash.comparable,
        BenchmarkKind.PASSIVE_PERPETUAL: (
            benchmarks.passive is not None
            and benchmarks.passive.comparable
            and benchmarks.passive.vehicle == comparison.benchmark_vehicle
        ),
        BenchmarkKind.RANDOM_MATCHED: (
            benchmarks.random is not None
            and benchmarks.random.comparable
            and benchmarks.random.seed == comparison.random_seed
            and len(benchmarks.random.trials) == comparison.random_trials
        ),
    }
    for kind in comparison.required_benchmarks:
        if not available[kind]:
            reasons.append(f"REQUIRED_BENCHMARK_MISSING:{kind.value}")
        elif not comparable[kind]:
            reasons.append(f"REQUIRED_BENCHMARK_INCOMPARABLE:{kind.value}")

    gates = tuple(_evaluate_hurdle(item, candidate_run, benchmarks) for item in comparison.hurdles)
    if any(not item.testable for item in gates):
        reasons.append("ECONOMIC_GATE_NOT_TESTABLE")
    if reasons:
        verdict = QualificationVerdict.NOT_TESTABLE
    elif all(item.passed is True for item in gates):
        verdict = QualificationVerdict.QUALIFIED
        reasons.append("ALL_PREREGISTERED_HURDLES_PASSED")
    else:
        verdict = QualificationVerdict.REJECTED
        reasons.append("PREREGISTERED_HURDLE_FAILED")
    evidence_ids = tuple(str(item) for item in required_evidence_ids)
    if not evidence_ids or len(set(evidence_ids)) != len(evidence_ids):
        raise ValueError("required evidence ids must be non-empty and unique")
    return EconomicQualificationResult(
        experiment_revision_id=protocol.experiment_revision_id,
        protocol_hash=protocol.protocol_hash,
        comparison_contract_id=comparison.contract_id,
        comparison_contract_hash=comparison.contract_hash,
        comparison_contract=FrozenDict(comparison.semantic_payload()),
        run_result=candidate_run,
        benchmark_suite=benchmarks,
        gates=gates,
        verdict=verdict,
        reason_codes=tuple(reasons),
        required_evidence_ids=evidence_ids,
        code_revision=protocol.code_revision,
        product_scope=protocol.product_scope,
        terminal_policy=comparison.terminal_policy,
        generated_at_utc=generated_at_utc or utc_now(),
    )


def make_artifact_evidence(
    artifact_path: str | Path,
    *,
    evidence_type: str,
    logical_id: str,
    protocol: ExperimentMetadata,
    observed_at_utc: str | None = None,
) -> EvidenceReference:
    return EvidenceReference.from_file(
        artifact_path,
        evidence_type=evidence_type,
        logical_id=logical_id,
        producing_revision_id=protocol.experiment_revision_id,
        producing_code_revision=protocol.code_revision,
        observed_at_utc=observed_at_utc,
    )


def _validate_protocol_and_runtime(
    protocol: ExperimentMetadata,
    comparison: ComparisonContract,
    dataset_evidence: EvidenceReference,
    engine: EconomicSimulationEngine,
    candles: Sequence[Candle],
) -> None:
    if not isinstance(protocol.benchmark, VersionedIdentity) or protocol.benchmark != (
        comparison.versioned_identity
    ):
        raise ValueError("formal run requires the concrete preregistered comparison identity")
    if protocol.product_scope != comparison.product_scope:
        raise ValueError("protocol and comparison product scope differ")
    if len(protocol.product_scope) != 1:
        raise ValueError("formal P6 simulation supports exactly one product")
    if protocol.terminal_policy != comparison.terminal_policy.value:
        raise ValueError("protocol and comparison terminal policies differ")
    if engine.initial_cash != comparison.initial_capital:
        raise ValueError("engine and comparison initial capital differ")
    if protocol.economic_policy != comparison.candidate_policy:
        raise ValueError("protocol and comparison economic policy identities differ")
    if protocol.cost_model != comparison.cost_model:
        raise ValueError("protocol and comparison cost model identities differ")
    if protocol.execution_model != comparison.execution_model:
        raise ValueError("protocol and comparison execution identities differ")
    if policy_identity(engine.policy, protocol.economic_policy.version) != protocol.economic_policy:
        raise ValueError("runtime policy content does not match protocol identity")
    actual_fee = fee_model_identity(
        engine.fee_model, protocol.cost_model.logical_id, protocol.cost_model.version
    )
    if actual_fee != protocol.cost_model:
        raise ValueError("runtime fee model content does not match protocol identity")
    actual_execution = execution_model_identity(
        engine.execution_model,
        protocol.execution_model.logical_id,
        protocol.execution_model.version,
    )
    if actual_execution != protocol.execution_model:
        raise ValueError("runtime execution model content does not match protocol identity")
    actual_funding = funding_model_identity(
        engine.funding_model,
        comparison.funding_model.logical_id,
        comparison.funding_model.version,
    )
    if actual_funding != comparison.funding_model:
        raise ValueError("runtime funding model content does not match comparison identity")
    if dataset_evidence.completeness is not EvidenceCompleteness.COMPLETE:
        raise ValueError("formal run requires COMPLETE dataset evidence")
    if dataset_evidence.evidence_id != comparison.data_interval.dataset_evidence_id:
        raise ValueError("dataset evidence id does not match comparison interval")
    if dataset_evidence.content_sha256 != comparison.data_interval.dataset_content_sha256:
        raise ValueError("dataset content hash does not match comparison interval")
    _verify_local_evidence(dataset_evidence)
    if not candles:
        raise ValueError("formal run requires non-empty candles")
    validate_runtime_dataset_binding(dataset_evidence, candles, protocol.product_scope[0])
    if len({candle.symbol for candle in candles}) != 1:
        raise ValueError("formal run cannot mix candle instruments")
    if len(candles) != comparison.data_interval.observation_count:
        raise ValueError("candle count does not match preregistered interval")
    if candles[0].open_time_ms != comparison.data_interval.start_ms:
        raise ValueError("candle start does not match preregistered interval")
    if candles[-1].close_time_ms != comparison.data_interval.end_ms:
        raise ValueError("candle end does not match preregistered interval")
    if any(
        candles[index].open_time_ms <= candles[index - 1].open_time_ms
        or candles[index].close_time_ms <= candles[index].open_time_ms
        for index in range(1, len(candles))
    ):
        raise ValueError("formal candle timestamps must be monotonic")


def _validate_candidate_run_binding(
    protocol: ExperimentMetadata,
    comparison: ComparisonContract,
    candidate_run: EconomicRunResult,
) -> None:
    identity = candidate_run.identity
    candidate_role = getattr(identity, "run_role", None)
    role_str = str(getattr(candidate_role, "value", candidate_role)) if candidate_role else "CANDIDATE"
    if role_str != EconomicRunRole.CANDIDATE.value:
        raise ValueError(
            f"candidate run cannot have role {role_str}; "
            "benchmark trial cannot authorize candidate economic qualification"
        )
    expected = {
        "experiment_revision_id": protocol.experiment_revision_id,
        "protocol_hash": protocol.protocol_hash,
        "input_contract": protocol.input_contract,
        "dataset_evidence_id": comparison.data_interval.dataset_evidence_id,
        "dataset_content_sha256": comparison.data_interval.dataset_content_sha256,
        "interval_start_ms": comparison.data_interval.start_ms,
        "interval_end_ms": comparison.data_interval.end_ms,
        "observation_count": comparison.data_interval.observation_count,
        "product_scope": protocol.product_scope,
        "initial_capital": comparison.initial_capital,
        "economic_policy": protocol.economic_policy,
        "cost_model": protocol.cost_model,
        "execution_model": protocol.execution_model,
        "funding_model": comparison.funding_model,
        "comparison_contract_id": comparison.contract_id,
        "comparison_contract_hash": comparison.contract_hash,
        "terminal_policy": comparison.terminal_policy,
        "metrics_contract_id": comparison.metrics_contract.contract_id,
        "metrics_contract_hash": comparison.metrics_contract.contract_hash,
        "code_revision": protocol.code_revision,
    }
    for name, value in expected.items():
        if getattr(identity, name) != value:
            raise ValueError(f"candidate run {name} binding mismatch")
    accounting = _accounting_copy(candidate_run)
    if accounting.get("completeness") != identity.completeness.value:
        raise ValueError("candidate run completeness disagrees with accounting")
    if accounting.get("terminal_policy") != comparison.terminal_policy.value:
        raise ValueError("candidate accounting terminal policy mismatch")
    if accounting.get("metrics_contract_id") != comparison.metrics_contract.contract_id:
        raise ValueError("candidate accounting metrics contract mismatch")
    if _finite_float(accounting.get("initial_cash"), "candidate initial cash") != (
        comparison.initial_capital
    ):
        raise ValueError("candidate accounting initial capital mismatch")


def _verify_local_evidence(evidence: EvidenceReference) -> None:
    path = evidence.local_path()
    if path is None:
        return
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError("local evidence is unavailable") from exc
    if digest != evidence.content_sha256:
        raise ValueError("local evidence hash mismatch")


def _cash_benchmark(
    comparison: ComparisonContract,
    candidate_run: EconomicRunResult,
    candles: Sequence[Candle],
) -> FormalBenchmarkResult:
    accounting = _accounting_copy(candidate_run)
    curve_value = accounting.get("equity_curve")
    if not isinstance(curve_value, list):
        raise TypeError("candidate equity_curve must be a JSON array")
    timestamps = [int(point[0]) for point in curve_value]
    curve = [(timestamp, comparison.initial_capital) for timestamp in timestamps]
    summary = summarize_ledger(
        initial_cash=comparison.initial_capital,
        events=(),
        equity_curve=curve,
        final_asset=candles[-1].symbol,
        final_mark_price=candles[-1].close,
        interval_start_ms=comparison.data_interval.start_ms,
        interval_end_ms=comparison.data_interval.end_ms,
        notional_curve=[(timestamp, 0.0) for timestamp in timestamps],
        terminal_policy=comparison.terminal_policy,
        metrics_contract=comparison.metrics_contract,
    )
    return FormalBenchmarkResult(
        benchmark_kind=BenchmarkKind.CASH,
        vehicle="USDT_CASH_NO_TRADE",
        accounting=FrozenDict(bind_runtime_market_data(summary.to_dict(), candles)),
        comparable=summary.formal_complete,
        matching_diagnostics=FrozenDict(
            {
                "same_interval": True,
                "same_initial_capital": True,
                "same_metric_timestamps": True,
                "compatible_terminal_treatment": True,
            }
        ),
    )


def _passive_perpetual_benchmark(
    comparison: ComparisonContract,
    candidate_run: EconomicRunResult,
    engine: EconomicSimulationEngine,
    candles: Sequence[Candle],
    funding_events: Sequence[FundingSettlement],
) -> FormalBenchmarkResult:
    if comparison.benchmark_vehicle != "BTCUSDT_LINEAR_PERPETUAL":
        return FormalBenchmarkResult(
            benchmark_kind=BenchmarkKind.PASSIVE_PERPETUAL,
            vehicle=comparison.benchmark_vehicle,
            accounting=FrozenDict({}),
            comparable=False,
            matching_diagnostics=FrozenDict({"reason": "UNSUPPORTED_BENCHMARK_VEHICLE"}),
        )
    try:
        accounting = build_passive_benchmark_accounting(
            candidate_identity=candidate_run.identity.to_dict(),
            product=candles[0].symbol,
            initial_cash=comparison.initial_capital,
            candles=candles,
            fee_model=engine.fee_model,
            execution_model=engine.execution_model,
            funding_model=engine.funding_model,
            funding_events=funding_events,
            interval_start_ms=comparison.data_interval.start_ms,
            interval_end_ms=comparison.data_interval.end_ms,
            terminal_policy=comparison.terminal_policy,
            metrics_contract=comparison.metrics_contract,
        )
    except PassiveBenchmarkReplayError as exc:
        return FormalBenchmarkResult(
            benchmark_kind=BenchmarkKind.PASSIVE_PERPETUAL,
            vehicle=comparison.benchmark_vehicle,
            accounting=FrozenDict({}),
            comparable=False,
            matching_diagnostics=FrozenDict({"reason": exc.reason_code}),
        )
    return FormalBenchmarkResult(
        benchmark_kind=BenchmarkKind.PASSIVE_PERPETUAL,
        vehicle=comparison.benchmark_vehicle,
        accounting=FrozenDict(accounting),
        comparable=accounting.get("completeness") == ResultCompleteness.COMPLETE.value,
        matching_diagnostics=FrozenDict(
            {
                "same_interval": True,
                "same_cost_model": True,
                "same_execution_model": True,
                "same_funding_model": True,
                "same_terminal_policy": True,
            }
        ),
    )


def _random_matched_benchmark(
    protocol: ExperimentMetadata,
    comparison: ComparisonContract,
    dataset_evidence: EvidenceReference,
    candidate_run: EconomicRunResult,
    engine: EconomicSimulationEngine,
    candles: Sequence[Candle],
    opportunities: Sequence[EligibleOpportunity],
    funding_events: Sequence[FundingSettlement],
) -> RandomBenchmarkDistribution:
    candidate_events = _accounting_copy(candidate_run).get("trade_events")
    if not isinstance(candidate_events, list):
        raise TypeError("candidate trade_events must be a JSON array")
    opens = [
        event
        for event in candidate_events
        if event["action"] in (TradeAction.OPEN_LONG.value, TradeAction.OPEN_SHORT.value)
    ]
    direction_template = [
        1 if event["action"] == TradeAction.OPEN_LONG.value else -1 for event in opens
    ]
    ordered_opportunities = sorted(
        opportunities, key=lambda item: (item.timestamp_ms, item.opportunity_id)
    )
    if len({item.opportunity_id for item in ordered_opportunities}) != len(ordered_opportunities):
        raise ValueError("eligible opportunity ids must be unique")
    if any(
        item.timestamp_ms < comparison.data_interval.start_ms
        or item.timestamp_ms > comparison.data_interval.end_ms
        for item in ordered_opportunities
    ):
        raise ValueError("eligible opportunity lies outside the comparison interval")
    if len(ordered_opportunities) < len(opens):
        return RandomBenchmarkDistribution(seed=comparison.random_seed, trials=())
    master = random.Random(comparison.random_seed)
    trials: list[FormalBenchmarkResult] = []
    for trial_id in range(comparison.random_trials):
        trial_seed = master.randrange(0, 2**63)
        rng = random.Random(trial_seed)
        selected = rng.sample(ordered_opportunities, len(opens))
        selected.sort(key=lambda item: item.timestamp_ms)
        directions = list(direction_template)
        rng.shuffle(directions)
        signals = [
            InformationSignal(
                signal_id=f"P6_RANDOM_{trial_id}_{item.opportunity_id}",
                experiment_id=protocol.experiment_revision_id,
                timestamp_ms=item.timestamp_ms,
                direction=direction,
                strength=max(engine.policy.entry_rule.min_signal_strength, 1.0),
                metadata=thaw_json(item.metadata),
            )
            for item, direction in zip(selected, directions, strict=True)
        ]
        decision_inputs = []
        candles_by_open = {c.open_time_ms: c for c in candles}
        for signal, opportunity in zip(signals, selected, strict=True):
            open_times = opportunity.metadata.get("decision_input_open_times_ms")
            if not isinstance(open_times, tuple) or not open_times:
                raise ValueError(
                    "formal random opportunity lacks exact decision-input provenance"
                )
            ref_candles = [candles_by_open[ot] for ot in open_times]
            preimage_hash = canonical_sha256([_runtime_candle_payload(c) for c in ref_candles])
            decision_inputs.append(
                {
                    "signal_id": signal.signal_id,
                    "signal_timestamp_ms": signal.timestamp_ms,
                    "signal_payload": signal.to_dict(),
                    "producer_identity": "RANDOM_BENCHMARK_PRODUCER",
                    "producer_version": "1.0.0",
                    "producer_contract_id": "CANONICAL_RANDOM_BENCHMARK_V1",
                    "observation_open_times_ms": list(open_times),
                    "generation_contract": {
                        "rule": "RANDOM_MATCHED_OPPORTUNITY",
                        "producer_contract_id": "CANONICAL_RANDOM_BENCHMARK_V1",
                        "direction": signal.direction,
                        "strength": signal.strength,
                        "horizon_ms": signal.horizon_ms,
                        "asset": signal.asset,
                        "confidence_interval": (
                            list(signal.confidence_interval)
                            if signal.confidence_interval is not None
                            else None
                        ),
                        "metadata": dict(signal.metadata),
                        "material_input_open_times_ms": list(open_times),
                        "expected_preimage_sha256": preimage_hash,
                    },
                }
            )
        trial_bundle = build_formal_replay_input_bundle(
            protocol=protocol,
            dataset_evidence=dataset_evidence,
            candles=candles,
            signals=signals,
            decision_inputs=decision_inputs,
            funding_events=funding_events,
            authority_role=EconomicRunRole.RANDOM_BENCHMARK,
        )
        run = execute_bound_run(
            protocol=protocol,
            comparison=comparison,
            dataset_evidence=dataset_evidence,
            engine=engine,
            candles=candles,
            signals=signals,
            replay_input_bundle=trial_bundle,
            funding_events=funding_events,
            run_role=EconomicRunRole.RANDOM_BENCHMARK,
        )
        diagnostics, is_comparable = _matching_diagnostics(
            candidate_run, run, comparison.matching_rules
        )
        trials.append(
            FormalBenchmarkResult(
                benchmark_kind=BenchmarkKind.RANDOM_MATCHED,
                vehicle=comparison.benchmark_vehicle,
                accounting=run.accounting,
                comparable=is_comparable,
                matching_diagnostics=FrozenDict(diagnostics),
                trial_id=trial_id,
                seed=trial_seed,
                run_result_id=run.result_id,
            )
        )
    return RandomBenchmarkDistribution(seed=comparison.random_seed, trials=tuple(trials))


def _matching_diagnostics(
    candidate: EconomicRunResult,
    trial: EconomicRunResult,
    rules: BenchmarkMatchingRules,
) -> tuple[dict[str, Any], bool]:
    candidate_accounting = _accounting_copy(candidate)
    trial_accounting = _accounting_copy(trial)
    candidate_events = candidate_accounting.get("trade_events")
    trial_events = trial_accounting.get("trade_events")

    def directions(events: Any) -> tuple[int, int, int]:
        long_count = sum(event["action"] == TradeAction.OPEN_LONG.value for event in events)
        short_count = sum(event["action"] == TradeAction.OPEN_SHORT.value for event in events)
        return long_count + short_count, long_count, short_count

    candidate_count, candidate_long, candidate_short = directions(candidate_events)
    trial_count, trial_long, trial_short = directions(trial_events)
    count_pass = not rules.match_entry_count or trial_count == candidate_count
    direction_pass = not rules.match_direction_counts or (
        trial_long == candidate_long and trial_short == candidate_short
    )

    candidate_holding = _mean_holding(candidate_accounting.get("round_trips"))
    trial_holding = _mean_holding(trial_accounting.get("round_trips"))
    holding_error = _relative_error(trial_holding, candidate_holding)
    holding_pass = rules.maximum_mean_holding_error_fraction is None or (
        holding_error is not None and holding_error <= rules.maximum_mean_holding_error_fraction
    )
    exposure_error = abs(
        _finite_float(trial_accounting.get("time_exposure_fraction"), "trial time exposure")
        - _finite_float(
            candidate_accounting.get("time_exposure_fraction"),
            "candidate time exposure",
        )
    )
    exposure_pass = (
        rules.maximum_time_exposure_error_fraction is None
        or exposure_error <= rules.maximum_time_exposure_error_fraction
    )
    notional_error = _relative_error(
        _finite_float(
            trial_accounting.get("average_notional_exposure_usdt"),
            "trial average notional",
        ),
        _finite_float(
            candidate_accounting.get("average_notional_exposure_usdt"),
            "candidate average notional",
        ),
    )
    notional_pass = rules.maximum_average_notional_error_fraction is None or (
        notional_error is not None
        and notional_error <= rules.maximum_average_notional_error_fraction
    )
    complete = trial.identity.completeness is ResultCompleteness.COMPLETE
    same_policy_cost_execution_funding = (
        trial.identity.economic_policy == candidate.identity.economic_policy
        and trial.identity.cost_model == candidate.identity.cost_model
        and trial.identity.execution_model == candidate.identity.execution_model
        and trial.identity.funding_model == candidate.identity.funding_model
    )
    same_interval = (
        trial.identity.interval_start_ms == candidate.identity.interval_start_ms
        and trial.identity.interval_end_ms == candidate.identity.interval_end_ms
        and trial.identity.observation_count == candidate.identity.observation_count
    )
    same_terminal_policy = trial.identity.terminal_policy == candidate.identity.terminal_policy
    diagnostics = {
        "candidate_entry_count": candidate_count,
        "trial_entry_count": trial_count,
        "entry_count_match": count_pass,
        "candidate_long_count": candidate_long,
        "candidate_short_count": candidate_short,
        "trial_long_count": trial_long,
        "trial_short_count": trial_short,
        "direction_count_match": direction_pass,
        "candidate_mean_holding_ms": candidate_holding,
        "trial_mean_holding_ms": trial_holding,
        "mean_holding_error_fraction": holding_error,
        "mean_holding_match": holding_pass,
        "time_exposure_error_fraction": exposure_error,
        "time_exposure_match": exposure_pass,
        "average_notional_error_fraction": notional_error,
        "average_notional_match": notional_pass,
        "same_policy_cost_execution_funding": same_policy_cost_execution_funding,
        "same_interval": same_interval,
        "same_terminal_policy": same_terminal_policy,
        "trial_complete": complete,
    }
    return diagnostics, all(
        (
            count_pass,
            direction_pass,
            holding_pass,
            exposure_pass,
            notional_pass,
            same_policy_cost_execution_funding,
            same_interval,
            same_terminal_policy,
            complete,
        )
    )


def _mean_holding(round_trips: Any) -> float:
    if not isinstance(round_trips, list):
        raise TypeError("round_trips must be a JSON array")
    values = [float(item["holding_duration_ms"]) for item in round_trips]
    return sum(values) / len(values) if values else 0.0


def _relative_error(observed: float, target: float) -> float | None:
    if target == 0.0:
        return 0.0 if observed == 0.0 else None
    return abs(observed - target) / abs(target)


def _candidate_metrics(run: EconomicRunResult) -> dict[str, float | None]:
    accounting = _accounting_copy(run)
    return {
        "net_return_pct": _finite_float(accounting.get("net_return_pct"), "net_return_pct"),
        "max_drawdown_pct": _finite_float(accounting.get("max_drawdown_pct"), "max_drawdown_pct"),
        "profit_factor": (
            _finite_float(accounting.get("profit_factor"), "profit_factor")
            if accounting.get("profit_factor") is not None
            else None
        ),
        "sharpe_ratio": (
            _finite_float(accounting.get("sharpe_ratio"), "sharpe_ratio")
            if accounting.get("sharpe_ratio") is not None
            else None
        ),
    }


def _evaluate_hurdle(
    hurdle: EconomicHurdle,
    candidate: EconomicRunResult,
    benchmarks: FormalBenchmarkSuite,
) -> QualificationGateResult:
    metric = hurdle.metric
    candidate_metrics = _candidate_metrics(candidate)
    observed: float | None
    if metric == "NET_RETURN_PCT":
        observed = candidate_metrics["net_return_pct"]
    elif metric == "MAX_DRAWDOWN_PCT":
        observed = candidate_metrics["max_drawdown_pct"]
    elif metric == "PROFIT_FACTOR":
        observed = candidate_metrics["profit_factor"]
    elif metric == "SHARPE_RATIO":
        observed = candidate_metrics["sharpe_ratio"]
    elif metric == "EXCESS_RETURN_VS_CASH":
        observed = _excess_return(candidate, benchmarks.cash)
    elif metric == "EXCESS_RETURN_VS_PASSIVE":
        observed = _excess_return(candidate, benchmarks.passive)
    elif metric == "EXCESS_RETURN_VS_RANDOM_QUANTILE":
        quantile = (
            benchmarks.random.quantile(hurdle.random_quantile)
            if benchmarks.random is not None
            and benchmarks.random.comparable
            and hurdle.random_quantile is not None
            else None
        )
        observed = (
            candidate_metrics["net_return_pct"] - quantile
            if candidate_metrics["net_return_pct"] is not None and quantile is not None
            else None
        )
    else:
        raise AssertionError(f"unsupported validated economic hurdle metric: {metric}")
    if observed is None or not math.isfinite(observed):
        return QualificationGateResult(
            hurdle.gate_id,
            metric,
            None,
            hurdle.operator,
            hurdle.threshold,
            False,
            None,
            "METRIC_UNAVAILABLE",
        )
    passed = _compare(observed, hurdle.operator, hurdle.threshold)
    return QualificationGateResult(
        hurdle.gate_id,
        metric,
        observed,
        hurdle.operator,
        hurdle.threshold,
        True,
        passed,
        "GATE_PASSED" if passed else "GATE_FAILED",
    )


def _excess_return(
    candidate: EconomicRunResult, benchmark: FormalBenchmarkResult | None
) -> float | None:
    if benchmark is None or not benchmark.comparable:
        return None
    return _finite_float(
        _accounting_copy(candidate).get("net_return_pct"), "candidate net return"
    ) - _finite_float(_accounting_copy(benchmark).get("net_return_pct"), "benchmark net return")


def _compare(observed: float, operator: GateOperator, threshold: float) -> bool:
    if operator is GateOperator.GREATER_THAN:
        return observed > threshold
    if operator is GateOperator.GREATER_THAN_OR_EQUAL:
        return observed >= threshold
    if operator is GateOperator.LESS_THAN:
        return observed < threshold
    return observed <= threshold


def _atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = (canonical_json(payload) + "\n").encode("utf-8")
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_descriptor = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return target
