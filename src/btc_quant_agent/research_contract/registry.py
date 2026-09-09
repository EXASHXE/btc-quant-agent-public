from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .canonical import canonical_json, canonical_sha256
from .models import (
    DecisionEvent,
    DecisionStatus,
    EvidenceCompleteness,
    EvidenceReference,
    ExperimentMetadata,
    utc_now,
)

REGISTRY_SCHEMA_VERSION = "1.0.0"


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")

LEGAL_TRANSITIONS: Mapping[DecisionStatus, frozenset[DecisionStatus]] = {
    DecisionStatus.PROPOSED: frozenset({DecisionStatus.REGISTERED}),
    DecisionStatus.REGISTERED: frozenset(
        {
            DecisionStatus.STATISTICALLY_QUALIFIED,
            DecisionStatus.REJECTED,
            DecisionStatus.FROZEN_ARCHIVE,
        }
    ),
    DecisionStatus.STATISTICALLY_QUALIFIED: frozenset(
        {
            DecisionStatus.ECONOMICALLY_QUALIFIED,
            DecisionStatus.REJECTED,
            DecisionStatus.FROZEN_ARCHIVE,
        }
    ),
    DecisionStatus.ECONOMICALLY_QUALIFIED: frozenset({DecisionStatus.FROZEN_ARCHIVE}),
    DecisionStatus.REJECTED: frozenset({DecisionStatus.FROZEN_ARCHIVE}),
    DecisionStatus.FROZEN_ARCHIVE: frozenset(),
}


class ResearchContractError(ValueError):
    pass


class RegistryCorruptionError(ResearchContractError):
    pass


class StaleRegistryError(ResearchContractError):
    pass


class InvalidTransitionError(ResearchContractError):
    pass


class EvidenceValidationError(ResearchContractError):
    pass


class ResearchContractRegistry:
    """Local content-addressed experiment registry with append-only decisions.

    Commits use an advisory lock, generation compare-and-swap, complete-state hash,
    fsynced same-directory temporary file, atomic ``os.replace``, and directory fsync.
    This is deliberately a local single-file contract, not a distributed database.
    """

    def __init__(
        self,
        storage_path: Path | str | None = None,
        *,
        before_replace: Callable[[Path], None] | None = None,
    ) -> None:
        self.storage_path = Path(storage_path) if storage_path is not None else None
        self._protocols: dict[str, ExperimentMetadata] = {}
        self._evidence: dict[str, EvidenceReference] = {}
        self._events: list[DecisionEvent] = []
        self._generation = 0
        self._content_hash: str | None = None
        self._before_replace = before_replace
        if self.storage_path is not None and self.storage_path.exists():
            self.load()

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def content_hash(self) -> str | None:
        return self._content_hash

    def register_experiment(
        self,
        experiment: ExperimentMetadata,
        allow_update: bool | None = None,
        *,
        actor: str = "research_contract_registry",
        source: str = "P5_PROTOCOL_REGISTRATION",
        registered_at_utc: str | None = None,
    ) -> ExperimentMetadata:
        """Register one semantic revision; exact duplicates are idempotent.

        ``allow_update=True`` is explicitly rejected. Changed semantics naturally
        produce a different content-addressed revision and preserve the prior one.
        """
        if allow_update:
            raise ResearchContractError(
                "allow_update semantic overwrite is forbidden; register a new revision"
            )
        if not isinstance(experiment, ExperimentMetadata):
            raise TypeError("experiment must be ExperimentMetadata")
        revision_id = experiment.experiment_revision_id
        existing = self._protocols.get(revision_id)
        if existing is not None:
            if existing.semantic_payload() != experiment.semantic_payload():
                raise RegistryCorruptionError("protocol hash collision with different semantics")
            return existing

        protocols = dict(self._protocols)
        protocols[revision_id] = experiment
        events = list(self._events)
        events.append(
            DecisionEvent(
                sequence=len(events) + 1,
                experiment_revision_id=revision_id,
                previous_status=DecisionStatus.PROPOSED,
                new_status=DecisionStatus.REGISTERED,
                decided_at_utc=registered_at_utc or utc_now(),
                evidence_ids=(),
                reason="immutable protocol revision registered",
                actor=actor,
                source=source,
                previous_event_hash=events[-1].event_hash if events else None,
            )
        )
        self._commit(protocols, dict(self._evidence), events)
        return experiment

    def get_experiment(self, experiment_revision_id: str) -> ExperimentMetadata:
        try:
            return self._protocols[experiment_revision_id]
        except KeyError as exc:
            raise KeyError(f"Experiment revision {experiment_revision_id} not found") from exc

    def list_revisions(self, experiment_family: str) -> list[ExperimentMetadata]:
        return sorted(
            (
                protocol
                for protocol in self._protocols.values()
                if protocol.experiment_family == experiment_family
            ),
            key=lambda item: item.experiment_revision_id,
        )

    def list_experiments(
        self, status: DecisionStatus | str | None = None
    ) -> list[ExperimentMetadata]:
        protocols = sorted(
            self._protocols.values(), key=lambda item: item.experiment_revision_id
        )
        if status is None:
            return protocols
        expected = status if isinstance(status, DecisionStatus) else DecisionStatus(status)
        statuses = self.reconstruct_statuses()
        return [item for item in protocols if statuses[item.experiment_revision_id] == expected]

    def register_evidence(self, evidence: EvidenceReference) -> EvidenceReference:
        if not isinstance(evidence, EvidenceReference):
            raise TypeError("evidence must be EvidenceReference")
        self._validate_evidence(
            evidence,
            verify_local=evidence.completeness is not EvidenceCompleteness.PROHIBITED,
            require_complete=False,
        )
        existing = self._evidence.get(evidence.evidence_id)
        if existing is not None:
            if existing != evidence:
                raise RegistryCorruptionError("evidence hash collision")
            return existing
        records = dict(self._evidence)
        records[evidence.evidence_id] = evidence
        self._commit(dict(self._protocols), records, list(self._events))
        return evidence

    def get_evidence(self, evidence_id: str) -> EvidenceReference:
        try:
            return self._evidence[evidence_id]
        except KeyError as exc:
            raise KeyError(f"Evidence {evidence_id} not found") from exc

    def update_decision_status(
        self,
        experiment_revision_id: str,
        new_status: DecisionStatus | str,
        *,
        evidence_references: Sequence[EvidenceReference | str],
        reason: str,
        actor: str,
        source: str,
        decided_at_utc: str | None = None,
        statistical_result_id: str | None = None,
        economic_result_id: str | None = None,
    ) -> DecisionEvent:
        """Append one legal decision event and atomically bind its evidence."""
        if experiment_revision_id not in self._protocols:
            raise KeyError(f"Experiment revision {experiment_revision_id} not found")
        target = new_status if isinstance(new_status, DecisionStatus) else DecisionStatus(new_status)
        current = self.get_status(experiment_revision_id)
        if target not in LEGAL_TRANSITIONS[current]:
            raise InvalidTransitionError(f"illegal decision transition {current} -> {target}")
        if target is DecisionStatus.ECONOMICALLY_QUALIFIED:
            raise InvalidTransitionError(
                "ECONOMICALLY_QUALIFIED is disabled until the P6 evidence contract exists"
            )
        if not evidence_references:
            raise EvidenceValidationError("decision transition requires immutable evidence")
        if not reason.strip() or not actor.strip() or not source.strip():
            raise InvalidTransitionError("decision reason, actor, and source are required")

        evidence = dict(self._evidence)
        evidence_ids: list[str] = []
        for reference in evidence_references:
            item = evidence.get(reference) if isinstance(reference, str) else reference
            if item is None:
                raise EvidenceValidationError(f"unknown evidence reference: {reference}")
            self._validate_evidence(item, verify_local=True, require_complete=True)
            previous = evidence.get(item.evidence_id)
            if previous is not None and previous != item:
                raise RegistryCorruptionError("evidence hash collision")
            evidence[item.evidence_id] = item
            evidence_ids.append(item.evidence_id)
        if len(set(evidence_ids)) != len(evidence_ids):
            raise EvidenceValidationError("duplicate evidence in decision transition")
        for result_id, label in (
            (statistical_result_id, "statistical_result_id"),
            (economic_result_id, "economic_result_id"),
        ):
            if result_id is not None and result_id not in evidence_ids:
                raise EvidenceValidationError(f"{label} must be included in evidence_references")

        events = list(self._events)
        event = DecisionEvent(
            sequence=len(events) + 1,
            experiment_revision_id=experiment_revision_id,
            previous_status=current,
            new_status=target,
            decided_at_utc=decided_at_utc or utc_now(),
            evidence_ids=tuple(evidence_ids),
            reason=reason,
            actor=actor,
            source=source,
            previous_event_hash=events[-1].event_hash if events else None,
            statistical_result_id=statistical_result_id,
            economic_result_id=economic_result_id,
        )
        events.append(event)
        self._commit(dict(self._protocols), evidence, events)
        return event

    transition_decision = update_decision_status

    def get_status(self, experiment_revision_id: str) -> DecisionStatus:
        if experiment_revision_id not in self._protocols:
            raise KeyError(f"Experiment revision {experiment_revision_id} not found")
        return self.reconstruct_statuses()[experiment_revision_id]

    def decision_events(self, experiment_revision_id: str | None = None) -> tuple[DecisionEvent, ...]:
        if experiment_revision_id is None:
            return tuple(self._events)
        if experiment_revision_id not in self._protocols:
            raise KeyError(f"Experiment revision {experiment_revision_id} not found")
        return tuple(
            event
            for event in self._events
            if event.experiment_revision_id == experiment_revision_id
        )

    def reconstruct_statuses(self) -> dict[str, DecisionStatus]:
        return self._validate_state(self._protocols, self._evidence, self._events)

    def to_dict(self) -> dict[str, Any]:
        statuses = self.reconstruct_statuses()
        return {
            "generation": self._generation,
            "content_hash": self._content_hash,
            "protocols": {
                key: value.to_dict() for key, value in sorted(self._protocols.items())
            },
            "evidence": {key: value.to_dict() for key, value in sorted(self._evidence.items())},
            "decision_events": [event.to_dict() for event in self._events],
            "current_statuses": {key: value.value for key, value in sorted(statuses.items())},
        }

    def save(self) -> None:
        self._commit(dict(self._protocols), dict(self._evidence), list(self._events))

    def load(self) -> None:
        if self.storage_path is None:
            raise ResearchContractError("cannot load a registry without storage_path")
        if not self.storage_path.exists():
            raise RegistryCorruptionError("registry file is missing")
        protocols, evidence, events, generation, content_hash = self._read_state(
            self.storage_path
        )
        self._protocols = protocols
        self._evidence = evidence
        self._events = events
        self._generation = generation
        self._content_hash = content_hash

    def _commit(
        self,
        protocols: dict[str, ExperimentMetadata],
        evidence: dict[str, EvidenceReference],
        events: list[DecisionEvent],
    ) -> None:
        self._validate_state(protocols, evidence, events)
        next_generation = self._generation + 1
        payload = self._payload(protocols, evidence, events)
        envelope = self._envelope(next_generation, payload)
        content_hash = str(envelope["content_hash"])
        encoded = (canonical_json(envelope) + "\n").encode("utf-8")

        if self.storage_path is not None:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with self._locked():
                actual_generation = 0
                if self.storage_path.exists():
                    *_, actual_generation, _ = self._read_state(self.storage_path)
                if actual_generation != self._generation:
                    raise StaleRegistryError(
                        f"stale registry generation {self._generation}; "
                        f"committed generation is {actual_generation}"
                    )
                self._atomic_replace(encoded)

        self._protocols = protocols
        self._evidence = evidence
        self._events = events
        self._generation = next_generation
        self._content_hash = content_hash

    @contextmanager
    def _locked(self) -> Iterator[None]:
        if self.storage_path is None:
            yield
            return
        lock_path = self.storage_path.with_name(f".{self.storage_path.name}.lock")
        descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)

    def _atomic_replace(self, encoded: bytes) -> None:
        if self.storage_path is None:
            return
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{self.storage_path.name}.",
            suffix=".tmp",
            dir=self.storage_path.parent,
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            if self._before_replace is not None:
                self._before_replace(temp_path)
            os.replace(temp_path, self.storage_path)
            self._fsync_directory(self.storage_path.parent)
        except BaseException:
            temp_path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(directory, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _payload(
        protocols: Mapping[str, ExperimentMetadata],
        evidence: Mapping[str, EvidenceReference],
        events: Sequence[DecisionEvent],
    ) -> dict[str, Any]:
        return {
            "protocols": {key: value.to_dict() for key, value in sorted(protocols.items())},
            "evidence": {key: value.to_dict() for key, value in sorted(evidence.items())},
            "decision_events": [event.to_dict() for event in events],
        }

    @staticmethod
    def _envelope(generation: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        core = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "generation": generation,
            "payload": dict(payload),
        }
        return {**core, "content_hash": canonical_sha256(core)}

    @classmethod
    def _read_state(
        cls, path: Path
    ) -> tuple[
        dict[str, ExperimentMetadata],
        dict[str, EvidenceReference],
        list[DecisionEvent],
        int,
        str,
    ]:
        try:
            raw = json.loads(
                path.read_text(encoding="utf-8"), parse_constant=_reject_json_constant
            )
        except (OSError, UnicodeError, ValueError) as exc:
            raise RegistryCorruptionError(f"registry is unreadable: {exc}") from exc
        if not isinstance(raw, dict) or set(raw) != {
            "schema_version",
            "generation",
            "payload",
            "content_hash",
        }:
            raise RegistryCorruptionError("registry envelope schema mismatch")
        if raw["schema_version"] != REGISTRY_SCHEMA_VERSION:
            raise RegistryCorruptionError("unsupported registry schema")
        generation = raw["generation"]
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise RegistryCorruptionError("registry generation must be a positive integer")
        payload = raw["payload"]
        if not isinstance(payload, dict) or set(payload) != {
            "protocols",
            "evidence",
            "decision_events",
        }:
            raise RegistryCorruptionError("registry payload schema mismatch")
        expected_hash = canonical_sha256(
            {
                "schema_version": raw["schema_version"],
                "generation": generation,
                "payload": payload,
            }
        )
        if raw["content_hash"] != expected_hash:
            raise RegistryCorruptionError("registry content hash mismatch")
        try:
            protocols_raw = payload["protocols"]
            evidence_raw = payload["evidence"]
            events_raw = payload["decision_events"]
            if not isinstance(protocols_raw, dict) or not isinstance(evidence_raw, dict):
                raise TypeError("protocols and evidence must be objects")
            if not isinstance(events_raw, list):
                raise TypeError("decision_events must be a list")
            protocols = {
                str(key): ExperimentMetadata.from_dict(value)
                for key, value in protocols_raw.items()
            }
            evidence = {
                str(key): EvidenceReference.from_dict(value)
                for key, value in evidence_raw.items()
            }
            events = [DecisionEvent.from_dict(value) for value in events_raw]
            if any(key != value.experiment_revision_id for key, value in protocols.items()):
                raise ValueError("protocol map key does not match revision identity")
            if any(key != value.evidence_id for key, value in evidence.items()):
                raise ValueError("evidence map key does not match evidence identity")
            cls._validate_state(protocols, evidence, events)
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, RegistryCorruptionError):
                raise
            raise RegistryCorruptionError(f"invalid registry state: {exc}") from exc
        return protocols, evidence, events, generation, expected_hash

    @staticmethod
    def _validate_evidence(
        evidence: EvidenceReference, *, verify_local: bool, require_complete: bool
    ) -> None:
        if require_complete and evidence.completeness is not EvidenceCompleteness.COMPLETE:
            raise EvidenceValidationError(
                f"evidence {evidence.logical_id} is not complete: {evidence.completeness}"
            )
        if not verify_local:
            return
        path = evidence.local_path()
        if path is None:
            return
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise EvidenceValidationError(
                f"local evidence is unavailable: {evidence.path_or_uri}"
            ) from exc
        if digest != evidence.content_sha256:
            raise EvidenceValidationError(
                f"local evidence hash mismatch: {evidence.path_or_uri}"
            )

    @staticmethod
    def _validate_state(
        protocols: Mapping[str, ExperimentMetadata],
        evidence: Mapping[str, EvidenceReference],
        events: Sequence[DecisionEvent],
    ) -> dict[str, DecisionStatus]:
        statuses = {key: DecisionStatus.PROPOSED for key in protocols}
        registration_counts = {key: 0 for key in protocols}
        prior_hash: str | None = None
        for expected_sequence, event in enumerate(events, start=1):
            if event.sequence != expected_sequence:
                raise RegistryCorruptionError("decision event sequence is not contiguous")
            if event.previous_event_hash != prior_hash:
                raise RegistryCorruptionError("decision event hash chain is broken")
            if event.experiment_revision_id not in protocols:
                raise RegistryCorruptionError("decision event references unknown protocol")
            current = statuses[event.experiment_revision_id]
            if event.previous_status is not current:
                raise RegistryCorruptionError("decision event previous status is inconsistent")
            if event.new_status not in LEGAL_TRANSITIONS[current]:
                raise RegistryCorruptionError("decision event contains an illegal transition")
            if event.new_status is DecisionStatus.ECONOMICALLY_QUALIFIED:
                raise RegistryCorruptionError(
                    "P5 registry cannot contain ECONOMICALLY_QUALIFIED state"
                )
            if event.new_status is DecisionStatus.REGISTERED:
                if event.evidence_ids:
                    raise RegistryCorruptionError("registration event cannot bind result evidence")
                registration_counts[event.experiment_revision_id] += 1
            elif not event.evidence_ids:
                raise RegistryCorruptionError("decision event is missing required evidence")
            if len(set(event.evidence_ids)) != len(event.evidence_ids):
                raise RegistryCorruptionError("decision event contains duplicate evidence")
            if any(evidence_id not in evidence for evidence_id in event.evidence_ids):
                raise RegistryCorruptionError("decision event references unknown evidence")
            if any(
                evidence[evidence_id].completeness is not EvidenceCompleteness.COMPLETE
                for evidence_id in event.evidence_ids
            ):
                raise RegistryCorruptionError("decision event references incomplete evidence")
            for result_id in (event.statistical_result_id, event.economic_result_id):
                if result_id is not None and result_id not in event.evidence_ids:
                    raise RegistryCorruptionError("result reference is not bound to decision event")
            statuses[event.experiment_revision_id] = event.new_status
            prior_hash = event.event_hash
        if any(count != 1 for count in registration_counts.values()):
            raise RegistryCorruptionError("every protocol requires exactly one registration event")
        return statuses
