from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvidenceEpoch:
    epoch_id: str
    symbol: str
    created_from_git_sha: str
    epoch_start_ms: int
    epoch_start_rule: str
    cadence_minutes: int
    post_boundary_delay_seconds: int
    required_fields: tuple[str, ...]
    minimum_days: int
    minimum_fully_available_snapshots: int
    minimum_required_field_availability: float
    maximum_consecutive_failed_or_missing_scheduled_slots: int
    manual_runs_count_for_eligibility: bool
    legacy_runs_count_for_eligibility: bool
    backfill_allowed: bool
    final_holdout_access: bool

    @classmethod
    def load(cls, path: str | Path) -> EvidenceEpoch:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        epoch = cls(
            epoch_id=str(raw["epoch_id"]),
            symbol=str(raw["symbol"]),
            created_from_git_sha=str(raw["created_from_git_sha"]),
            epoch_start_ms=int(raw["epoch_start_ms"]),
            epoch_start_rule=str(raw["epoch_start_rule"]),
            cadence_minutes=int(raw["cadence_minutes"]),
            post_boundary_delay_seconds=int(raw["post_boundary_delay_seconds"]),
            required_fields=tuple(str(value) for value in raw["required_fields"]),
            minimum_days=int(raw["minimum_days"]),
            minimum_fully_available_snapshots=int(raw["minimum_fully_available_snapshots"]),
            minimum_required_field_availability=float(raw["minimum_required_field_availability"]),
            maximum_consecutive_failed_or_missing_scheduled_slots=int(
                raw["maximum_consecutive_failed_or_missing_scheduled_slots"]
            ),
            manual_runs_count_for_eligibility=bool(raw["manual_runs_count_for_eligibility"]),
            legacy_runs_count_for_eligibility=bool(raw["legacy_runs_count_for_eligibility"]),
            backfill_allowed=bool(raw["backfill_allowed"]),
            final_holdout_access=bool(raw["final_holdout_access"]),
        )
        if (
            epoch.cadence_minutes != 15
            or epoch.minimum_days != 30
            or epoch.minimum_fully_available_snapshots != 2_500
            or epoch.minimum_required_field_availability != 0.95
            or epoch.maximum_consecutive_failed_or_missing_scheduled_slots != 4
            or epoch.manual_runs_count_for_eligibility
            or epoch.legacy_runs_count_for_eligibility
            or epoch.backfill_allowed
            or epoch.final_holdout_access
        ):
            raise ValueError("evidence epoch weakens frozen eligibility or safety gates")
        if epoch.epoch_start_ms % (epoch.cadence_minutes * 60_000):
            raise ValueError("evidence epoch must start on a cadence boundary")
        return epoch
