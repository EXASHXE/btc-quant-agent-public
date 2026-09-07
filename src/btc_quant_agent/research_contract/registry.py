from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DecisionStatus, ExperimentMetadata


class ResearchContractRegistry:
    """Registry maintaining experiment metadata contracts without modifying legacy records."""

    def __init__(self, storage_path: Path | str | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self._experiments: dict[str, ExperimentMetadata] = {}
        if self.storage_path is not None and self.storage_path.exists():
            self.load()

    def register_experiment(self, experiment: ExperimentMetadata, allow_update: bool = False) -> None:
        eid = experiment.experiment_id
        if eid in self._experiments and not allow_update:
            raise ValueError(f"Experiment {eid} is already registered. Set allow_update=True to update.")
        experiment.validate()
        self._experiments[eid] = experiment
        if self.storage_path is not None:
            self.save()

    def get_experiment(self, experiment_id: str) -> ExperimentMetadata:
        if experiment_id not in self._experiments:
            raise KeyError(f"Experiment {experiment_id} not found in registry")
        return self._experiments[experiment_id]

    def update_decision_status(self, experiment_id: str, new_status: DecisionStatus | str) -> ExperimentMetadata:
        exp = self.get_experiment(experiment_id)
        st = new_status if isinstance(new_status, DecisionStatus) else DecisionStatus(new_status)
        updated = ExperimentMetadata(
            experiment_id=exp.experiment_id,
            input_contract=exp.input_contract,
            feature_definition=exp.feature_definition,
            prediction_target=exp.prediction_target,
            evaluation_method=exp.evaluation_method,
            economic_policy=exp.economic_policy,
            cost_model=exp.cost_model,
            benchmark=exp.benchmark,
            decision_status=st,
            created_at_utc=exp.created_at_utc,
            metadata={**exp.metadata, "status_updated_at": st.value},
        )
        self.register_experiment(updated, allow_update=True)
        return updated

    def list_experiments(self, status: DecisionStatus | str | None = None) -> list[ExperimentMetadata]:
        if status is None:
            return list(self._experiments.values())
        st = status if isinstance(status, DecisionStatus) else DecisionStatus(status)
        return [e for e in self._experiments.values() if e.decision_status == st]

    def to_dict(self) -> dict[str, Any]:
        return {eid: exp.to_dict() for eid, exp in sorted(self._experiments.items())}

    def save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        self.storage_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def load(self) -> None:
        if self.storage_path is None or not self.storage_path.exists():
            return
        content = self.storage_path.read_text(encoding="utf-8")
        data = json.loads(content)
        self._experiments = {
            eid: ExperimentMetadata.from_dict(item)
            for eid, item in data.items()
        }
