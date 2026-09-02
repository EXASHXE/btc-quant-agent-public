from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .dsl import Formula


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    data_role: str
    base_lookback_hours: int
    availability_rule: str


@dataclass(frozen=True)
class FormulaRegistryEntry:
    formula_id: str
    formula_hash: str
    formula_tokens_or_ast: list[dict[str, Any]]
    input_feature_ids: list[str]
    input_data_roles: list[str]
    operator_set: list[str]
    max_lookback: int
    proposal_engine: str
    search_run_id: str
    search_seed: int
    search_budget: int
    complexity: int
    discovery_window: str
    validation_window: str
    pseudo_forward_window: str
    metrics_by_fold: dict[str, Any]
    correlation_to_existing_candidates: float | None
    status: str
    research_eligibility: bool
    runtime_eligibility: bool

    def __post_init__(self) -> None:
        if self.runtime_eligibility:
            raise ValueError("research symbolic formulas cannot be Runtime eligible")
        allowed = {
            "DISCOVERY_ONLY",
            "FAILED_VALIDATION",
            "REJECTED_REDUNDANT",
            "REJECTED_UNSTABLE",
            "PROVISIONAL_SANDBOX_CANDIDATE",
            "PROVISIONAL_FORWARD_SHADOW",
        }
        if self.status not in allowed:
            raise ValueError(f"invalid symbolic formula status: {self.status}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def formula_entry(
    formula: Formula,
    features: dict[str, FeatureDefinition],
    **values: Any,
) -> FormulaRegistryEntry:
    return FormulaRegistryEntry(
        formula_hash=formula.formula_hash,
        formula_tokens_or_ast=[token.as_dict() for token in formula.tokens],
        input_feature_ids=list(formula.input_features),
        input_data_roles=sorted({features[name].data_role for name in formula.input_features}),
        operator_set=sorted(
            {str(token.value) for token in formula.tokens if token.kind.value == "OPERATOR"}
        ),
        max_lookback=formula.max_lookback(
            {name: definition.base_lookback_hours for name, definition in features.items()}
        ),
        complexity=formula.complexity,
        runtime_eligibility=False,
        **values,
    )


def write_registry(path: str | Path, entries: list[FormulaRegistryEntry]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "safety": {
            "strategy": "EXPERIMENTAL",
            "qualified_direction_engine": "NONE",
            "runtime_maximum": "OPPORTUNITY_ONLY",
            "execution": "DISABLED",
            "final_holdout": "SEALED",
        },
        "formulas": [entry.as_dict() for entry in entries],
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
