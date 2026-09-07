from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class DecisionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    REGISTERED = "REGISTERED"
    STATISTICALLY_QUALIFIED = "STATISTICALLY_QUALIFIED"
    ECONOMICALLY_QUALIFIED = "ECONOMICALLY_QUALIFIED"
    REJECTED = "REJECTED"
    FROZEN_ARCHIVE = "FROZEN_ARCHIVE"


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    name: str
    formula: str
    input_requirements: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    bounds: tuple[float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureDefinition:
        b = data.get("bounds")
        bounds_tuple = tuple(b) if isinstance(b, (list, tuple)) and len(b) == 2 else None
        return cls(
            feature_id=str(data["feature_id"]),
            name=str(data["name"]),
            formula=str(data["formula"]),
            input_requirements=list(data.get("input_requirements", [])),
            parameters=dict(data.get("parameters", {})),
            bounds=bounds_tuple,
        )


@dataclass(frozen=True)
class PredictionTarget:
    target_id: str
    name: str
    horizon_ms: int
    horizon_description: str
    continuous: bool = True
    calculation_rule: str = "future_close - reference_close"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PredictionTarget:
        return cls(
            target_id=str(data["target_id"]),
            name=str(data["name"]),
            horizon_ms=int(data["horizon_ms"]),
            horizon_description=str(data.get("horizon_description", "")),
            continuous=bool(data.get("continuous", True)),
            calculation_rule=str(data.get("calculation_rule", "future_close - reference_close")),
        )


@dataclass(frozen=True)
class EvaluationMethod:
    method_name: str
    statistical_test: str
    fwer_control: str = "HOLM_BONFERRONI"
    significance_threshold: float = 0.05
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvaluationMethod:
        return cls(
            method_name=str(data["method_name"]),
            statistical_test=str(data["statistical_test"]),
            fwer_control=str(data.get("fwer_control", "HOLM_BONFERRONI")),
            significance_threshold=float(data.get("significance_threshold", 0.05)),
            parameters=dict(data.get("parameters", {})),
        )


@dataclass(frozen=True)
class ExperimentMetadata:
    """Standardized research experiment contract defining metadata across the qualification lifecycle."""

    experiment_id: str
    input_contract: str
    feature_definition: FeatureDefinition
    prediction_target: PredictionTarget
    evaluation_method: EvaluationMethod
    economic_policy: str
    cost_model: str
    benchmark: str
    decision_status: DecisionStatus = DecisionStatus.PROPOSED
    created_at_utc: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.experiment_id or not self.experiment_id.strip():
            raise ValueError("experiment_id cannot be empty")
        if not self.input_contract or not self.input_contract.strip():
            raise ValueError("input_contract cannot be empty")
        if not self.economic_policy or not self.economic_policy.strip():
            raise ValueError("economic_policy cannot be empty")
        if not self.cost_model or not self.cost_model.strip():
            raise ValueError("cost_model cannot be empty")
        if not self.benchmark or not self.benchmark.strip():
            raise ValueError("benchmark cannot be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "input_contract": self.input_contract,
            "feature_definition": self.feature_definition.to_dict(),
            "prediction_target": self.prediction_target.to_dict(),
            "evaluation_method": self.evaluation_method.to_dict(),
            "economic_policy": self.economic_policy,
            "cost_model": self.cost_model,
            "benchmark": self.benchmark,
            "decision_status": self.decision_status.value,
            "created_at_utc": self.created_at_utc,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentMetadata:
        fd_raw = data["feature_definition"]
        fd = fd_raw if isinstance(fd_raw, FeatureDefinition) else FeatureDefinition.from_dict(fd_raw)

        pt_raw = data["prediction_target"]
        pt = pt_raw if isinstance(pt_raw, PredictionTarget) else PredictionTarget.from_dict(pt_raw)

        em_raw = data["evaluation_method"]
        em = em_raw if isinstance(em_raw, EvaluationMethod) else EvaluationMethod.from_dict(em_raw)

        status_raw = data.get("decision_status", DecisionStatus.PROPOSED)
        status = status_raw if isinstance(status_raw, DecisionStatus) else DecisionStatus(status_raw)

        return cls(
            experiment_id=str(data["experiment_id"]),
            input_contract=str(data["input_contract"]),
            feature_definition=fd,
            prediction_target=pt,
            evaluation_method=em,
            economic_policy=str(data["economic_policy"]),
            cost_model=str(data["cost_model"]),
            benchmark=str(data["benchmark"]),
            decision_status=status,
            created_at_utc=str(data.get("created_at_utc", datetime.now(UTC).isoformat())),
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def from_json(cls, json_str: str) -> ExperimentMetadata:
        return cls.from_dict(json.loads(json_str))
