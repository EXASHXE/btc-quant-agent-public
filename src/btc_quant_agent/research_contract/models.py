from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .canonical import FrozenDict, canonical_json, canonical_sha256, thaw_json

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
P6_PENDING = "P6_PENDING"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} cannot be empty")


def _require_sha256(value: str, field_name: str) -> None:
    if SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 hex digest")


def _validate_timestamp(value: str, field_name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")


class DecisionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    REGISTERED = "REGISTERED"
    STATISTICALLY_QUALIFIED = "STATISTICALLY_QUALIFIED"
    ECONOMICALLY_QUALIFIED = "ECONOMICALLY_QUALIFIED"
    REJECTED = "REJECTED"
    FROZEN_ARCHIVE = "FROZEN_ARCHIVE"


class EvidenceCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    PROHIBITED = "PROHIBITED"


@dataclass(frozen=True)
class VersionedIdentity:
    """Content-bound identity for a protocol dependency."""

    logical_id: str
    version: str
    content_sha256: str

    def __post_init__(self) -> None:
        _require_text(self.logical_id, "logical_id")
        _require_text(self.version, "version")
        _require_sha256(self.content_sha256, "content_sha256")

    @classmethod
    def from_payload(cls, logical_id: str, version: str, payload: Any) -> VersionedIdentity:
        return cls(logical_id, version, canonical_sha256(payload))

    def to_dict(self) -> dict[str, str]:
        return {
            "logical_id": self.logical_id,
            "version": self.version,
            "content_sha256": self.content_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VersionedIdentity:
        if set(data) != {"logical_id", "version", "content_sha256"}:
            raise ValueError("versioned identity schema mismatch")
        return cls(
            logical_id=str(data["logical_id"]),
            version=str(data["version"]),
            content_sha256=str(data["content_sha256"]),
        )


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    name: str
    formula: str
    input_requirements: tuple[str, ...] = field(default_factory=tuple)
    parameters: FrozenDict = field(default_factory=FrozenDict)
    bounds: tuple[float, float] | None = None

    def __post_init__(self) -> None:
        _require_text(self.feature_id, "feature_id")
        _require_text(self.name, "feature name")
        _require_text(self.formula, "feature formula")
        object.__setattr__(
            self, "input_requirements", tuple(str(item) for item in self.input_requirements)
        )
        object.__setattr__(self, "parameters", FrozenDict(self.parameters))
        if self.bounds is not None:
            if len(self.bounds) != 2:
                raise ValueError("feature bounds must contain exactly two values")
            bounds = (float(self.bounds[0]), float(self.bounds[1]))
            if bounds[0] > bounds[1]:
                raise ValueError("feature lower bound cannot exceed upper bound")
            object.__setattr__(self, "bounds", bounds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "name": self.name,
            "formula": self.formula,
            "input_requirements": list(self.input_requirements),
            "parameters": thaw_json(self.parameters),
            "bounds": list(self.bounds) if self.bounds is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> FeatureDefinition:
        expected = {
            "feature_id",
            "name",
            "formula",
            "input_requirements",
            "parameters",
            "bounds",
        }
        if set(data) != expected:
            raise ValueError("feature definition schema mismatch")
        bounds_raw = data.get("bounds")
        bounds = (
            (float(bounds_raw[0]), float(bounds_raw[1]))
            if isinstance(bounds_raw, (list, tuple)) and len(bounds_raw) == 2
            else None
        )
        return cls(
            feature_id=str(data["feature_id"]),
            name=str(data["name"]),
            formula=str(data["formula"]),
            input_requirements=tuple(str(item) for item in data.get("input_requirements", [])),
            parameters=FrozenDict(data.get("parameters", {})),
            bounds=bounds,
        )


@dataclass(frozen=True)
class PredictionTarget:
    target_id: str
    name: str
    horizon_ms: int
    horizon_description: str
    continuous: bool = True
    calculation_rule: str = "future_close - reference_close"

    def __post_init__(self) -> None:
        _require_text(self.target_id, "target_id")
        _require_text(self.name, "target name")
        if self.horizon_ms <= 0:
            raise ValueError("horizon_ms must be positive")
        _require_text(self.horizon_description, "horizon_description")
        _require_text(self.calculation_rule, "calculation_rule")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "name": self.name,
            "horizon_ms": self.horizon_ms,
            "horizon_description": self.horizon_description,
            "continuous": self.continuous,
            "calculation_rule": self.calculation_rule,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PredictionTarget:
        expected = {
            "target_id",
            "name",
            "horizon_ms",
            "horizon_description",
            "continuous",
            "calculation_rule",
        }
        if set(data) != expected:
            raise ValueError("prediction target schema mismatch")
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
    parameters: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        _require_text(self.method_name, "method_name")
        _require_text(self.statistical_test, "statistical_test")
        _require_text(self.fwer_control, "fwer_control")
        if not 0.0 < self.significance_threshold < 1.0:
            raise ValueError("significance_threshold must be between zero and one")
        object.__setattr__(self, "parameters", FrozenDict(self.parameters))

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_name": self.method_name,
            "statistical_test": self.statistical_test,
            "fwer_control": self.fwer_control,
            "significance_threshold": self.significance_threshold,
            "parameters": thaw_json(self.parameters),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvaluationMethod:
        expected = {
            "method_name",
            "statistical_test",
            "fwer_control",
            "significance_threshold",
            "parameters",
        }
        if set(data) != expected:
            raise ValueError("evaluation method schema mismatch")
        return cls(
            method_name=str(data["method_name"]),
            statistical_test=str(data["statistical_test"]),
            fwer_control=str(data.get("fwer_control", "HOLM_BONFERRONI")),
            significance_threshold=float(data.get("significance_threshold", 0.05)),
            parameters=FrozenDict(data.get("parameters", {})),
        )


@dataclass(frozen=True)
class ExperimentMetadata:
    """Deeply immutable semantic protocol plus non-semantic audit metadata.

    ``experiment_id`` is a human family id. The registry identity is
    ``experiment_revision_id``, which binds that family to ``protocol_hash``.
    ``created_at_utc`` and ``metadata`` are deliberately excluded from the hash.
    """

    experiment_id: str
    name: str
    input_contract: VersionedIdentity
    feature_definition: FeatureDefinition
    prediction_target: PredictionTarget
    evaluation_method: EvaluationMethod
    economic_policy: VersionedIdentity
    cost_model: VersionedIdentity
    execution_model: VersionedIdentity
    benchmark: VersionedIdentity | str
    product_scope: tuple[str, ...]
    code_revision: str
    terminal_policy: str
    created_at_utc: str = field(default_factory=utc_now)
    metadata: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        _require_text(self.experiment_id, "experiment_id")
        _require_text(self.name, "experiment name")
        if not isinstance(self.input_contract, VersionedIdentity):
            raise TypeError("input_contract must be a VersionedIdentity")
        if not isinstance(self.economic_policy, VersionedIdentity):
            raise TypeError("economic_policy must be a VersionedIdentity")
        if not isinstance(self.cost_model, VersionedIdentity):
            raise TypeError("cost_model must be a VersionedIdentity")
        if not isinstance(self.execution_model, VersionedIdentity):
            raise TypeError("execution_model must be a VersionedIdentity")
        if not isinstance(self.benchmark, VersionedIdentity) and self.benchmark != P6_PENDING:
            raise ValueError(f"benchmark must be a VersionedIdentity or {P6_PENDING}")
        scope = tuple(str(item) for item in self.product_scope)
        if not scope or any(not item.strip() for item in scope):
            raise ValueError("product_scope must contain non-empty instruments")
        object.__setattr__(self, "product_scope", scope)
        _require_text(self.code_revision, "code_revision")
        _require_text(self.terminal_policy, "terminal_policy")
        _validate_timestamp(self.created_at_utc, "created_at_utc")
        object.__setattr__(self, "metadata", FrozenDict(self.metadata))
        canonical_json(self.semantic_payload())

    def validate(self) -> None:
        """Re-run canonical serialization validation for compatibility callers."""
        canonical_json(self.semantic_payload())

    @property
    def experiment_family(self) -> str:
        return self.experiment_id

    def semantic_payload(self) -> dict[str, Any]:
        benchmark = (
            self.benchmark.to_dict()
            if isinstance(self.benchmark, VersionedIdentity)
            else self.benchmark
        )
        return {
            "experiment_family": self.experiment_id,
            "name": self.name,
            "input_contract": self.input_contract.to_dict(),
            "feature_definition": self.feature_definition.to_dict(),
            "prediction_target": self.prediction_target.to_dict(),
            "evaluation_method": self.evaluation_method.to_dict(),
            "economic_policy": self.economic_policy.to_dict(),
            "cost_model": self.cost_model.to_dict(),
            "execution_model": self.execution_model.to_dict(),
            "benchmark": benchmark,
            "product_scope": list(self.product_scope),
            "code_revision": self.code_revision,
            "terminal_policy": self.terminal_policy,
        }

    @property
    def canonical_semantic_json(self) -> str:
        return canonical_json(self.semantic_payload())

    @property
    def protocol_hash(self) -> str:
        return hashlib.sha256(self.canonical_semantic_json.encode("utf-8")).hexdigest()

    @property
    def experiment_revision_id(self) -> str:
        return f"{self.experiment_id}@{self.protocol_hash}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "experiment_revision_id": self.experiment_revision_id,
            "protocol_hash": self.protocol_hash,
            "semantic_payload": self.semantic_payload(),
            "audit": {
                "created_at_utc": self.created_at_utc,
                "metadata": thaw_json(self.metadata),
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExperimentMetadata:
        expected = {
            "schema_version",
            "experiment_revision_id",
            "protocol_hash",
            "semantic_payload",
            "audit",
        }
        if set(data) != expected:
            raise ValueError("protocol record schema mismatch")
        if data["schema_version"] != "1.0.0":
            raise ValueError("unsupported protocol record schema")
        semantic = data["semantic_payload"]
        audit = data["audit"]
        if not isinstance(semantic, Mapping) or not isinstance(audit, Mapping):
            raise TypeError("protocol semantic_payload and audit must be objects")
        expected_semantic = {
            "experiment_family",
            "name",
            "input_contract",
            "feature_definition",
            "prediction_target",
            "evaluation_method",
            "economic_policy",
            "cost_model",
            "execution_model",
            "benchmark",
            "product_scope",
            "code_revision",
            "terminal_policy",
        }
        if set(semantic) != expected_semantic or set(audit) != {
            "created_at_utc",
            "metadata",
        }:
            raise ValueError("protocol payload schema mismatch")
        benchmark_raw = semantic["benchmark"]
        benchmark = (
            VersionedIdentity.from_dict(benchmark_raw)
            if isinstance(benchmark_raw, Mapping)
            else str(benchmark_raw)
        )
        instance = cls(
            experiment_id=str(semantic["experiment_family"]),
            name=str(semantic["name"]),
            input_contract=VersionedIdentity.from_dict(semantic["input_contract"]),
            feature_definition=FeatureDefinition.from_dict(semantic["feature_definition"]),
            prediction_target=PredictionTarget.from_dict(semantic["prediction_target"]),
            evaluation_method=EvaluationMethod.from_dict(semantic["evaluation_method"]),
            economic_policy=VersionedIdentity.from_dict(semantic["economic_policy"]),
            cost_model=VersionedIdentity.from_dict(semantic["cost_model"]),
            execution_model=VersionedIdentity.from_dict(semantic["execution_model"]),
            benchmark=benchmark,
            product_scope=tuple(str(item) for item in semantic["product_scope"]),
            code_revision=str(semantic["code_revision"]),
            terminal_policy=str(semantic["terminal_policy"]),
            created_at_utc=str(audit["created_at_utc"]),
            metadata=FrozenDict(audit.get("metadata", {})),
        )
        if str(data["protocol_hash"]) != instance.protocol_hash:
            raise ValueError("protocol hash mismatch")
        if str(data["experiment_revision_id"]) != instance.experiment_revision_id:
            raise ValueError("experiment revision identity mismatch")
        return instance

    @classmethod
    def from_json(cls, json_str: str) -> ExperimentMetadata:
        raw = json.loads(json_str)
        if not isinstance(raw, Mapping):
            raise TypeError("protocol JSON must contain an object")
        return cls.from_dict(raw)


@dataclass(frozen=True)
class EvidenceReference:
    evidence_type: str
    logical_id: str
    content_sha256: str
    observed_at_utc: str
    producing_revision_id: str
    producing_code_revision: str
    completeness: EvidenceCompleteness = EvidenceCompleteness.COMPLETE
    path_or_uri: str | None = None
    metadata: FrozenDict = field(default_factory=FrozenDict)

    def __post_init__(self) -> None:
        _require_text(self.evidence_type, "evidence_type")
        _require_text(self.logical_id, "evidence logical_id")
        _require_sha256(self.content_sha256, "evidence content_sha256")
        _validate_timestamp(self.observed_at_utc, "observed_at_utc")
        _require_text(self.producing_revision_id, "producing_revision_id")
        _require_text(self.producing_code_revision, "producing_code_revision")
        if not isinstance(self.completeness, EvidenceCompleteness):
            object.__setattr__(self, "completeness", EvidenceCompleteness(self.completeness))
        if self.path_or_uri is not None:
            _require_text(self.path_or_uri, "path_or_uri")
        object.__setattr__(self, "metadata", FrozenDict(self.metadata))

    def identity_payload(self) -> dict[str, Any]:
        return {
            "evidence_type": self.evidence_type,
            "logical_id": self.logical_id,
            "content_sha256": self.content_sha256,
            "observed_at_utc": self.observed_at_utc,
            "producing_revision_id": self.producing_revision_id,
            "producing_code_revision": self.producing_code_revision,
            "completeness": self.completeness.value,
            "path_or_uri": self.path_or_uri,
            "metadata": thaw_json(self.metadata),
        }

    @property
    def evidence_id(self) -> str:
        return f"{self.logical_id}@{canonical_sha256(self.identity_payload())}"

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        evidence_type: str,
        logical_id: str,
        producing_revision_id: str,
        producing_code_revision: str,
        observed_at_utc: str | None = None,
        completeness: EvidenceCompleteness = EvidenceCompleteness.COMPLETE,
        metadata: Mapping[str, Any] | None = None,
    ) -> EvidenceReference:
        source = Path(path)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        return cls(
            evidence_type=evidence_type,
            logical_id=logical_id,
            content_sha256=digest,
            observed_at_utc=observed_at_utc or utc_now(),
            producing_revision_id=producing_revision_id,
            producing_code_revision=producing_code_revision,
            completeness=completeness,
            path_or_uri=str(source),
            metadata=FrozenDict(metadata),
        )

    def local_path(self) -> Path | None:
        if self.path_or_uri is None:
            return None
        parsed = urlparse(self.path_or_uri)
        if parsed.scheme not in ("", "file"):
            return None
        return Path(unquote(parsed.path if parsed.scheme == "file" else self.path_or_uri))

    def to_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, **self.identity_payload()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> EvidenceReference:
        expected = {
            "evidence_id",
            "evidence_type",
            "logical_id",
            "content_sha256",
            "observed_at_utc",
            "producing_revision_id",
            "producing_code_revision",
            "completeness",
            "path_or_uri",
            "metadata",
        }
        if set(data) != expected:
            raise ValueError("evidence reference schema mismatch")
        instance = cls(
            evidence_type=str(data["evidence_type"]),
            logical_id=str(data["logical_id"]),
            content_sha256=str(data["content_sha256"]),
            observed_at_utc=str(data["observed_at_utc"]),
            producing_revision_id=str(data["producing_revision_id"]),
            producing_code_revision=str(data["producing_code_revision"]),
            completeness=EvidenceCompleteness(str(data["completeness"])),
            path_or_uri=str(data["path_or_uri"]) if data["path_or_uri"] is not None else None,
            metadata=FrozenDict(data["metadata"]),
        )
        if str(data["evidence_id"]) != instance.evidence_id:
            raise ValueError("evidence identity mismatch")
        return instance


@dataclass(frozen=True)
class DecisionEvent:
    sequence: int
    experiment_revision_id: str
    previous_status: DecisionStatus
    new_status: DecisionStatus
    decided_at_utc: str
    evidence_ids: tuple[str, ...]
    reason: str
    actor: str
    source: str
    previous_event_hash: str | None
    statistical_result_id: str | None = None
    economic_result_id: str | None = None

    def __post_init__(self) -> None:
        if self.sequence <= 0:
            raise ValueError("decision sequence must be positive")
        _require_text(self.experiment_revision_id, "experiment_revision_id")
        if not isinstance(self.previous_status, DecisionStatus):
            object.__setattr__(self, "previous_status", DecisionStatus(self.previous_status))
        if not isinstance(self.new_status, DecisionStatus):
            object.__setattr__(self, "new_status", DecisionStatus(self.new_status))
        _validate_timestamp(self.decided_at_utc, "decided_at_utc")
        object.__setattr__(self, "evidence_ids", tuple(str(item) for item in self.evidence_ids))
        _require_text(self.reason, "decision reason")
        _require_text(self.actor, "decision actor")
        _require_text(self.source, "decision source")
        if self.previous_event_hash is not None:
            _require_sha256(self.previous_event_hash, "previous_event_hash")

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "experiment_revision_id": self.experiment_revision_id,
            "previous_status": self.previous_status.value,
            "new_status": self.new_status.value,
            "decided_at_utc": self.decided_at_utc,
            "evidence_ids": list(self.evidence_ids),
            "reason": self.reason,
            "actor": self.actor,
            "source": self.source,
            "previous_event_hash": self.previous_event_hash,
            "statistical_result_id": self.statistical_result_id,
            "economic_result_id": self.economic_result_id,
        }

    @property
    def event_hash(self) -> str:
        return canonical_sha256(self.unsigned_payload())

    def to_dict(self) -> dict[str, Any]:
        return {**self.unsigned_payload(), "event_hash": self.event_hash}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DecisionEvent:
        expected = {
            "sequence",
            "experiment_revision_id",
            "previous_status",
            "new_status",
            "decided_at_utc",
            "evidence_ids",
            "reason",
            "actor",
            "source",
            "previous_event_hash",
            "statistical_result_id",
            "economic_result_id",
            "event_hash",
        }
        if set(data) != expected:
            raise ValueError("decision event schema mismatch")
        instance = cls(
            sequence=int(data["sequence"]),
            experiment_revision_id=str(data["experiment_revision_id"]),
            previous_status=DecisionStatus(str(data["previous_status"])),
            new_status=DecisionStatus(str(data["new_status"])),
            decided_at_utc=str(data["decided_at_utc"]),
            evidence_ids=tuple(str(item) for item in data["evidence_ids"]),
            reason=str(data["reason"]),
            actor=str(data["actor"]),
            source=str(data["source"]),
            previous_event_hash=(
                str(data["previous_event_hash"])
                if data["previous_event_hash"] is not None
                else None
            ),
            statistical_result_id=(
                str(data["statistical_result_id"])
                if data["statistical_result_id"] is not None
                else None
            ),
            economic_result_id=(
                str(data["economic_result_id"])
                if data["economic_result_id"] is not None
                else None
            ),
        )
        if str(data["event_hash"]) != instance.event_hash:
            raise ValueError("decision event hash mismatch")
        return instance
