from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


@dataclass(frozen=True)
class EvidenceEpochLifecycle:
    epoch_id: str
    config_path: str
    start_ms: int
    status: str
    terminal_reason: str | None
    terminal_at_ms: int | None
    superseded_by: str | None
    formal_eligibility_role: str
    immutable_history: bool


@dataclass(frozen=True)
class EvidenceEpochRegistry:
    entries: tuple[EvidenceEpochLifecycle, ...]

    @classmethod
    def load(cls, path: str | Path) -> EvidenceEpochRegistry:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        entries = tuple(
            EvidenceEpochLifecycle(
                epoch_id=str(item["epoch_id"]),
                config_path=str(item["config_path"]),
                start_ms=int(item["start_ms"]),
                status=str(item["status"]),
                terminal_reason=(
                    str(item["terminal_reason"])
                    if item.get("terminal_reason") is not None
                    else None
                ),
                terminal_at_ms=(
                    int(item["terminal_at_ms"])
                    if item.get("terminal_at_ms") is not None
                    else None
                ),
                superseded_by=(
                    str(item["superseded_by"]) if item.get("superseded_by") is not None else None
                ),
                formal_eligibility_role=str(item["formal_eligibility_role"]),
                immutable_history=bool(item["immutable_history"]),
            )
            for item in raw["epochs"]
        )
        if len({entry.epoch_id for entry in entries}) != len(entries):
            raise ValueError("duplicate derivatives evidence epoch id")
        if any(not entry.immutable_history for entry in entries):
            raise ValueError("evidence epoch registry cannot weaken immutable history")
        return cls(entries)

    def formal_lifecycle(self, now_ms: int) -> EvidenceEpochLifecycle:
        successor = [
            entry
            for entry in self.entries
            if entry.formal_eligibility_role in {"FORMAL_ACTIVE", "FORMAL_SUCCESSOR_PENDING"}
            and entry.start_ms <= now_ms
            and entry.status not in {"FAILED_GAP_GATE_TERMINAL", "CANCELLED_BEFORE_START"}
        ]
        if successor:
            return max(successor, key=lambda entry: entry.start_ms)
        terminal = [
            entry
            for entry in self.entries
            if entry.formal_eligibility_role == "FORMAL_TERMINAL"
        ]
        if not terminal:
            raise ValueError("no formal derivatives evidence epoch is available")
        return max(terminal, key=lambda entry: entry.start_ms)

    def formal_epoch(self, now_ms: int) -> tuple[EvidenceEpoch, EvidenceEpochLifecycle]:
        lifecycle = self.formal_lifecycle(now_ms)
        epoch = EvidenceEpoch.load(lifecycle.config_path)
        if epoch.epoch_id != lifecycle.epoch_id or epoch.epoch_start_ms != lifecycle.start_ms:
            raise ValueError("evidence epoch registry/config identity mismatch")
        return epoch, lifecycle

    def active_lifecycle(self, now_ms: int | None = None) -> EvidenceEpochLifecycle | None:
        candidates = [
            entry
            for entry in self.entries
            if entry.formal_eligibility_role in {"FORMAL_ACTIVE", "FORMAL_SUCCESSOR_PENDING"}
            and entry.status not in {"FAILED_GAP_GATE_TERMINAL", "CANCELLED_BEFORE_START"}
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda entry: entry.start_ms)

    def active_epoch(self, now_ms: int | None = None) -> tuple[EvidenceEpoch, EvidenceEpochLifecycle] | None:
        lifecycle = self.active_lifecycle(now_ms)
        if lifecycle is None:
            return None
        epoch = EvidenceEpoch.load(lifecycle.config_path)
        if epoch.epoch_id != lifecycle.epoch_id or epoch.epoch_start_ms != lifecycle.start_ms:
            raise ValueError("evidence epoch registry/config identity mismatch")
        return epoch, lifecycle

    def as_dict(self) -> list[dict[str, Any]]:
        return [entry.__dict__.copy() for entry in self.entries]


def resolve_formal_epoch(
    now_ms: int,
    *,
    registry_path: str | Path = "configs/forward/derivatives_evidence_epochs.json",
    fallback_epoch_path: str | Path = "configs/forward/v0.3.14_derivatives_evidence_epoch.json",
) -> tuple[EvidenceEpoch, EvidenceEpochLifecycle | None]:
    registry = Path(registry_path)
    if registry.exists():
        return EvidenceEpochRegistry.load(registry).formal_epoch(now_ms)
    return EvidenceEpoch.load(fallback_epoch_path), None


def resolve_active_derivatives_epoch(
    *,
    registry_path: str | Path = "configs/forward/derivatives_evidence_epochs.json",
    now_ms: int | None = None,
) -> tuple[EvidenceEpoch, EvidenceEpochLifecycle] | None:
    registry = Path(registry_path)
    if not registry.exists():
        return None
    return EvidenceEpochRegistry.load(registry).active_epoch(now_ms)
