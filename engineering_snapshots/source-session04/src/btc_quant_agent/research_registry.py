from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any


class RegistryError(ValueError):
    pass


class ResearchStatus(StrEnum):
    REJECTED = "REJECTED"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    SUPPORTED_MOVEMENT = "SUPPORTED_MOVEMENT"
    INCONCLUSIVE = "INCONCLUSIVE"
    CANDIDATE = "CANDIDATE"
    FROZEN = "FROZEN"
    VALIDATED_OOS = "VALIDATED_OOS"
    VALIDATED_FORWARD = "VALIDATED_FORWARD"


class RuntimeEligibility(StrEnum):
    BLOCKED = "BLOCKED"
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    SHADOW_ONLY = "SHADOW_ONLY"
    PAPER_TESTNET_ONLY = "PAPER_TESTNET_ONLY"
    LIVE_ELIGIBLE = "LIVE_ELIGIBLE"


COMPONENT_TYPES = {"FEATURE", "DETECTOR", "DIRECTION_ENGINE", "STRATEGY", "REGIME"}
ROLES = {"OPPORTUNITY", "DIRECTION", "REGIME", "RISK", "EXECUTION", "DIAGNOSTIC"}
REQUIRED_COMPONENT_FIELDS = {
    "component_id",
    "component_type",
    "feature_family",
    "role",
    "version",
    "research_status",
    "runtime_eligibility",
    "hypothesis_ids",
    "versions_tested",
    "development_window",
    "dataset_ids",
    "development_reuse_count",
    "final_holdout_accessed",
    "evidence_paths",
    "reason",
    "stopped_family",
    "eligible_for_reuse",
    "last_updated",
}
OPTIONAL_COMPONENT_FIELDS = {"state", "legacy_directional_role"}


@dataclass(frozen=True)
class RegistryComponent:
    component_id: str
    component_type: str
    feature_family: str
    role: str
    version: str
    research_status: ResearchStatus
    runtime_eligibility: RuntimeEligibility
    hypothesis_ids: tuple[str, ...]
    versions_tested: tuple[str, ...]
    development_window: str
    dataset_ids: tuple[str, ...]
    development_reuse_count: int
    final_holdout_accessed: bool
    evidence_paths: tuple[str, ...]
    reason: str
    stopped_family: bool
    eligible_for_reuse: bool
    last_updated: str
    state: str | None = None
    legacy_directional_role: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RegistryComponent:
        missing = REQUIRED_COMPONENT_FIELDS - raw.keys()
        unknown = raw.keys() - REQUIRED_COMPONENT_FIELDS - OPTIONAL_COMPONENT_FIELDS
        if missing or unknown:
            raise RegistryError(
                f"component schema mismatch missing={sorted(missing)} unknown={sorted(unknown)}"
            )
        values = dict(raw)
        try:
            values["research_status"] = ResearchStatus(values["research_status"])
            values["runtime_eligibility"] = RuntimeEligibility(values["runtime_eligibility"])
        except ValueError as exc:
            raise RegistryError(str(exc)) from exc
        for key in ("hypothesis_ids", "versions_tested", "dataset_ids", "evidence_paths"):
            values[key] = tuple(str(item) for item in values[key])
        return cls(**values)

    @property
    def actionable(self) -> bool:
        return self.runtime_eligibility in {
            RuntimeEligibility.SHADOW_ONLY,
            RuntimeEligibility.PAPER_TESTNET_ONLY,
            RuntimeEligibility.LIVE_ELIGIBLE,
        }


@dataclass(frozen=True)
class ResearchRegistry:
    schema_version: str
    registry_version: str
    final_holdout: str
    runtime_maximum_stage: str
    components: dict[str, RegistryComponent]
    source_path: Path

    @classmethod
    def load(cls, path: str | Path = "configs/research_registry.json") -> ResearchRegistry:
        source = Path(path)
        try:
            raw: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"registry unavailable: {exc}") from exc
        expected = {
            "schema_version",
            "registry_version",
            "final_holdout",
            "runtime_maximum_stage",
            "components",
        }
        if set(raw) != expected:
            raise RegistryError(f"registry top-level schema mismatch: {sorted(raw)}")
        if raw["schema_version"] != "1.0.0":
            raise RegistryError(f"unsupported registry schema: {raw['schema_version']}")
        if not isinstance(raw["components"], list):
            raise RegistryError("registry components must be a list")
        try:
            parsed = [RegistryComponent.from_dict(item) for item in raw["components"]]
        except (KeyError, TypeError) as exc:
            raise RegistryError(f"invalid registry component: {exc}") from exc
        identifiers = [item.component_id for item in parsed]
        if len(set(identifiers)) != len(identifiers):
            raise RegistryError("duplicate component_id")
        registry = cls(
            str(raw["schema_version"]),
            str(raw["registry_version"]),
            str(raw["final_holdout"]),
            str(raw["runtime_maximum_stage"]),
            {item.component_id: item for item in parsed},
            source,
        )
        registry.validate()
        return registry

    def validate(self, repo_root: str | Path = ".") -> None:
        if self.final_holdout != "SEALED":
            raise RegistryError("Final Holdout must remain SEALED")
        root = Path(repo_root)
        for item in self.components.values():
            if item.component_type not in COMPONENT_TYPES or item.role not in ROLES:
                raise RegistryError(f"invalid component type/role: {item.component_id}")
            if item.final_holdout_accessed:
                raise RegistryError(f"Holdout access is forbidden: {item.component_id}")
            if not item.evidence_paths or any(
                not (root / path).is_file() for path in item.evidence_paths
            ):
                raise RegistryError(f"missing evidence path: {item.component_id}")
            if item.research_status == ResearchStatus.REJECTED and item.actionable:
                raise RegistryError(f"REJECTED component is actionable: {item.component_id}")
            if (
                item.research_status == ResearchStatus.SUPPORTED_MOVEMENT
                and item.role == "DIRECTION"
            ):
                raise RegistryError(f"movement evidence cannot be directional: {item.component_id}")
            if (
                item.runtime_eligibility == RuntimeEligibility.LIVE_ELIGIBLE
                and item.research_status != ResearchStatus.VALIDATED_FORWARD
            ):
                raise RegistryError(
                    f"LIVE_ELIGIBLE requires VALIDATED_FORWARD: {item.component_id}"
                )

    def get(self, component_id: str) -> RegistryComponent:
        try:
            return self.components[component_id]
        except KeyError as exc:
            raise RegistryError(f"unknown component fails closed: {component_id}") from exc

    @property
    def qualified_direction_engine_count(self) -> int:
        return sum(
            item.role == "DIRECTION" and item.actionable for item in self.components.values()
        )

    def status(self) -> dict[str, Any]:
        qualified = [
            item.component_id
            for item in self.components.values()
            if item.role == "DIRECTION" and item.actionable
        ]
        return {
            "schema_version": self.schema_version,
            "registry_version": self.registry_version,
            "component_count": len(self.components),
            "qualified_direction_engine": qualified or "NONE",
            "qualified_direction_engine_count": self.qualified_direction_engine_count,
            "runtime_maximum_stage": self.runtime_maximum_stage,
            "final_holdout": self.final_holdout,
            "components": {
                key: {
                    "role": value.role,
                    "research_status": value.research_status.value,
                    "runtime_eligibility": value.runtime_eligibility.value,
                    "state": value.state,
                    "reason": value.reason,
                }
                for key, value in self.components.items()
            },
        }


@lru_cache(maxsize=4)
def load_registry(path: str = "configs/research_registry.json") -> ResearchRegistry:
    return ResearchRegistry.load(path)
