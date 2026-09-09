from __future__ import annotations

import fcntl
import hashlib
import json
import math
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
    EconomicDecisionAttestation,
    EvidenceCompleteness,
    EvidenceReference,
    ExperimentMetadata,
    VersionedIdentity,
    utc_now,
)

REGISTRY_SCHEMA_VERSION = "1.0.0"
P6_DECISION_SOURCE = "P6_FORMAL_ECONOMIC_QUALIFICATION"
P6_RESULT_EVIDENCE_TYPE = "P6_ECONOMIC_QUALIFICATION_RESULT"
P6_RUN_EVIDENCE_TYPE = "P6_ECONOMIC_RUN"
P6_BENCHMARK_EVIDENCE_TYPE = "P6_BENCHMARK_SUITE"
P6_RESULT_SCHEMA_VERSION = "1.1.0"


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

    def record_economic_qualification(
        self,
        attestation: EconomicDecisionAttestation,
        *,
        evidence_references: Sequence[EvidenceReference | str],
        reason: str,
        actor: str,
        decided_at_utc: str | None = None,
    ) -> DecisionEvent | None:
        """Validate and atomically record one formal P6 economic decision.

        ``NOT_TESTABLE`` artifacts are registered as diagnostic evidence without
        creating a lifecycle event.  Promotion and economic rejection are only
        available through this dedicated, artifact-bound path.
        """
        if not isinstance(attestation, EconomicDecisionAttestation):
            raise TypeError("attestation must be EconomicDecisionAttestation")
        if attestation.experiment_revision_id not in self._protocols:
            raise KeyError(
                f"Experiment revision {attestation.experiment_revision_id} not found"
            )
        protocol = self._protocols[attestation.experiment_revision_id]
        current = self.get_status(attestation.experiment_revision_id)
        if current is not DecisionStatus.STATISTICALLY_QUALIFIED:
            raise InvalidTransitionError(
                "economic qualification requires STATISTICALLY_QUALIFIED status"
            )
        if not reason.strip() or not actor.strip():
            raise InvalidTransitionError("economic decision reason and actor are required")
        if not evidence_references:
            raise EvidenceValidationError(
                "economic qualification requires immutable evidence"
            )

        staged_evidence = dict(self._evidence)
        event_evidence_ids: list[str] = []
        for reference in evidence_references:
            item = (
                staged_evidence.get(reference)
                if isinstance(reference, str)
                else reference
            )
            if item is None:
                raise EvidenceValidationError(f"unknown evidence reference: {reference}")
            self._validate_evidence(item, verify_local=True, require_complete=True)
            previous = staged_evidence.get(item.evidence_id)
            if previous is not None and previous != item:
                raise RegistryCorruptionError("evidence hash collision")
            staged_evidence[item.evidence_id] = item
            event_evidence_ids.append(item.evidence_id)
        if len(set(event_evidence_ids)) != len(event_evidence_ids):
            raise EvidenceValidationError("duplicate evidence in economic decision")

        expected_ids = {
            attestation.result_evidence_id,
            *attestation.required_evidence_ids,
        }
        if not expected_ids.issubset(event_evidence_ids):
            raise EvidenceValidationError(
                "economic decision must bind the result and every required evidence id"
            )
        self._validate_economic_attestation(attestation, protocol, staged_evidence)

        events = list(self._events)
        if attestation.verdict == "NOT_TESTABLE":
            self._commit(dict(self._protocols), staged_evidence, events)
            return None
        target = (
            DecisionStatus.ECONOMICALLY_QUALIFIED
            if attestation.verdict == "QUALIFIED"
            else DecisionStatus.REJECTED
        )
        event = DecisionEvent(
            sequence=len(events) + 1,
            experiment_revision_id=attestation.experiment_revision_id,
            previous_status=current,
            new_status=target,
            decided_at_utc=decided_at_utc or utc_now(),
            evidence_ids=tuple(event_evidence_ids),
            reason=reason,
            actor=actor,
            source=P6_DECISION_SOURCE,
            previous_event_hash=events[-1].event_hash if events else None,
            economic_result_id=attestation.result_evidence_id,
        )
        events.append(event)
        self._commit(dict(self._protocols), staged_evidence, events)
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

    @classmethod
    def _validate_economic_attestation(
        cls,
        attestation: EconomicDecisionAttestation,
        protocol: ExperimentMetadata,
        evidence: Mapping[str, EvidenceReference],
    ) -> None:
        """Fail closed on P6 identity, artifact, benchmark, and evidence binding."""

        def require_mapping(value: Any, label: str) -> Mapping[str, Any]:
            if not isinstance(value, Mapping):
                raise EvidenceValidationError(f"{label} must be a JSON object")
            return value

        def require_list(value: Any, label: str) -> list[Any]:
            if not isinstance(value, list):
                raise EvidenceValidationError(f"{label} must be a JSON array")
            return value

        def finite_number(value: Any, label: str) -> float:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EvidenceValidationError(f"{label} must be numeric")
            converted = float(value)
            if not math.isfinite(converted):
                raise EvidenceValidationError(f"{label} must be finite")
            return converted

        def load_local_artifact(
            reference: EvidenceReference, label: str
        ) -> Mapping[str, Any]:
            cls._validate_evidence(reference, verify_local=True, require_complete=True)
            path = reference.local_path()
            if path is None:
                raise EvidenceValidationError(f"{label} must be local and content-hashed")
            try:
                loaded = json.loads(
                    path.read_text(encoding="utf-8"),
                    parse_constant=_reject_json_constant,
                )
            except (OSError, UnicodeError, ValueError) as exc:
                raise EvidenceValidationError(f"{label} is unreadable: {exc}") from exc
            return require_mapping(loaded, label)

        def validate_accounting(value: Any, label: str) -> None:
            accounting = require_mapping(value, label)
            initial = finite_number(accounting.get("initial_cash"), f"{label}.initial_cash")
            final = finite_number(accounting.get("final_equity"), f"{label}.final_equity")
            realized = finite_number(
                accounting.get("realized_gross_pnl_usdt"),
                f"{label}.realized_gross_pnl_usdt",
            )
            unrealized = finite_number(
                accounting.get("terminal_unrealized_pnl_usdt"),
                f"{label}.terminal_unrealized_pnl_usdt",
            )
            fees = finite_number(
                accounting.get("total_fees_usdt"), f"{label}.total_fees_usdt"
            )
            funding = finite_number(
                accounting.get("total_funding_usdt"),
                f"{label}.total_funding_usdt",
            )
            tolerance = finite_number(
                accounting.get("accounting_tolerance"),
                f"{label}.accounting_tolerance",
            )
            if initial <= 0 or tolerance <= 0:
                raise EvidenceValidationError(
                    f"{label} initial cash and tolerance must be positive"
                )
            if not math.isclose(
                final - initial,
                realized + unrealized - fees + funding,
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                raise EvidenceValidationError(f"{label} accounting identity does not reconcile")
            net_pnl = finite_number(
                accounting.get("net_pnl_usdt"), f"{label}.net_pnl_usdt"
            )
            net_return = finite_number(
                accounting.get("net_return_pct"), f"{label}.net_return_pct"
            )
            if not math.isclose(net_pnl, final - initial, rel_tol=0.0, abs_tol=tolerance):
                raise EvidenceValidationError(f"{label} net PnL does not reconcile")
            if not math.isclose(
                net_return,
                net_pnl / initial,
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                raise EvidenceValidationError(f"{label} net return does not reconcile")
            curve = require_list(accounting.get("equity_curve"), f"{label}.equity_curve")
            if not curve:
                raise EvidenceValidationError(f"{label} equity curve is empty")
            last_point = require_list(curve[-1], f"{label}.equity_curve[-1]")
            if len(last_point) != 2 or not math.isclose(
                finite_number(last_point[1], f"{label}.equity_curve[-1].equity"),
                final,
                rel_tol=0.0,
                abs_tol=tolerance,
            ):
                raise EvidenceValidationError(
                    f"{label} terminal equity curve point does not reconcile"
                )

        if attestation.experiment_revision_id != protocol.experiment_revision_id:
            raise EvidenceValidationError("economic attestation revision mismatch")
        if attestation.protocol_hash != protocol.protocol_hash:
            raise EvidenceValidationError("economic attestation protocol hash mismatch")
        if attestation.code_revision != protocol.code_revision:
            raise EvidenceValidationError("economic attestation code revision mismatch")
        if attestation.product_scope != protocol.product_scope:
            raise EvidenceValidationError("economic attestation product scope mismatch")
        if attestation.terminal_policy != protocol.terminal_policy:
            raise EvidenceValidationError("economic attestation terminal policy mismatch")
        if not isinstance(protocol.benchmark, VersionedIdentity):
            raise EvidenceValidationError("P6_PENDING protocol cannot qualify economics")
        if protocol.benchmark.content_sha256 != attestation.comparison_contract_hash:
            raise EvidenceValidationError("protocol benchmark hash mismatch")

        result_reference = evidence.get(attestation.result_evidence_id)
        if result_reference is None:
            raise EvidenceValidationError("economic result evidence is not registered")
        if result_reference.evidence_type != P6_RESULT_EVIDENCE_TYPE:
            raise EvidenceValidationError("economic result evidence type mismatch")
        if result_reference.content_sha256 != attestation.result_artifact_sha256:
            raise EvidenceValidationError("economic result artifact hash mismatch")
        if (
            result_reference.producing_revision_id != protocol.experiment_revision_id
            or result_reference.producing_code_revision != protocol.code_revision
        ):
            raise EvidenceValidationError("economic result provenance mismatch")
        artifact = load_local_artifact(result_reference, "economic result artifact")
        if set(artifact) != {
            "artifact_type",
            "schema_version",
            "result_id",
            "semantic_payload",
            "audit",
        }:
            raise EvidenceValidationError("economic result artifact schema mismatch")
        if (
            artifact.get("artifact_type") != P6_RESULT_EVIDENCE_TYPE
            or artifact.get("schema_version") != P6_RESULT_SCHEMA_VERSION
        ):
            raise EvidenceValidationError("economic result type/schema mismatch")
        semantic = require_mapping(
            artifact.get("semantic_payload"), "economic result semantic payload"
        )
        semantic_hash = canonical_sha256(semantic)
        if semantic_hash != attestation.result_hash:
            raise EvidenceValidationError("economic result semantic hash mismatch")
        if artifact.get("result_id") != attestation.result_id:
            raise EvidenceValidationError("economic result identity mismatch")

        scalar_expectations: tuple[tuple[str, Any], ...] = (
            ("experiment_revision_id", attestation.experiment_revision_id),
            ("protocol_hash", attestation.protocol_hash),
            ("comparison_contract_id", attestation.comparison_contract_id),
            ("comparison_contract_hash", attestation.comparison_contract_hash),
            ("run_result_id", attestation.run_result_id),
            ("benchmark_suite_id", attestation.benchmark_suite_id),
            ("verdict", attestation.verdict),
            ("code_revision", attestation.code_revision),
            ("terminal_policy", attestation.terminal_policy),
        )
        if any(semantic.get(key) != expected for key, expected in scalar_expectations):
            raise EvidenceValidationError("economic result binding mismatch")
        if tuple(require_list(semantic.get("product_scope"), "product_scope")) != (
            attestation.product_scope
        ):
            raise EvidenceValidationError("economic result product scope mismatch")
        if tuple(
            require_list(semantic.get("required_evidence_ids"), "required_evidence_ids")
        ) != attestation.required_evidence_ids:
            raise EvidenceValidationError("economic result required evidence mismatch")
        if tuple(
            require_list(semantic.get("benchmark_result_ids"), "benchmark_result_ids")
        ) != attestation.benchmark_result_ids:
            raise EvidenceValidationError("economic result benchmark identities mismatch")

        comparison = require_mapping(
            semantic.get("comparison_contract"), "comparison contract"
        )
        if canonical_sha256(comparison) != attestation.comparison_contract_hash:
            raise EvidenceValidationError("comparison contract content hash mismatch")
        contract_name = comparison.get("contract_name")
        contract_version = comparison.get("contract_version")
        if (
            not isinstance(contract_name, str)
            or not isinstance(contract_version, str)
            or attestation.comparison_contract_id
            != f"{contract_name}@{attestation.comparison_contract_hash}"
            or protocol.benchmark.logical_id != contract_name
            or protocol.benchmark.version != contract_version
        ):
            raise EvidenceValidationError("comparison contract identity mismatch")
        if comparison.get("candidate_policy") != protocol.economic_policy.to_dict():
            raise EvidenceValidationError("comparison policy identity mismatch")
        if comparison.get("cost_model") != protocol.cost_model.to_dict():
            raise EvidenceValidationError("comparison cost identity mismatch")
        if comparison.get("execution_model") != protocol.execution_model.to_dict():
            raise EvidenceValidationError("comparison execution identity mismatch")
        if tuple(require_list(comparison.get("product_scope"), "comparison product_scope")) != (
            protocol.product_scope
        ):
            raise EvidenceValidationError("comparison product scope mismatch")
        if comparison.get("terminal_policy") != protocol.terminal_policy:
            raise EvidenceValidationError("comparison terminal policy mismatch")
        if comparison.get("result_schema_version") != P6_RESULT_SCHEMA_VERSION:
            raise EvidenceValidationError("comparison result schema mismatch")

        run_artifact = require_mapping(semantic.get("run_result"), "bound run artifact")
        if run_artifact.get("artifact_type") != P6_RUN_EVIDENCE_TYPE:
            raise EvidenceValidationError("bound run artifact type mismatch")
        run_semantic = require_mapping(
            run_artifact.get("semantic_payload"), "bound run semantic payload"
        )
        if (
            run_artifact.get("result_id") != attestation.run_result_id
            or attestation.run_result_id
            != f"economic-run-result@{canonical_sha256(run_semantic)}"
        ):
            raise EvidenceValidationError("bound run identity mismatch")
        run_identity = require_mapping(
            run_semantic.get("run_identity"), "bound run identity"
        )
        for key, expected in (
            ("experiment_revision_id", protocol.experiment_revision_id),
            ("protocol_hash", protocol.protocol_hash),
            ("comparison_contract_id", attestation.comparison_contract_id),
            ("comparison_contract_hash", attestation.comparison_contract_hash),
            ("product_scope", list(protocol.product_scope)),
            ("code_revision", protocol.code_revision),
            ("terminal_policy", protocol.terminal_policy),
            ("economic_policy", protocol.economic_policy.to_dict()),
            ("cost_model", protocol.cost_model.to_dict()),
            ("execution_model", protocol.execution_model.to_dict()),
        ):
            if run_identity.get(key) != expected:
                raise EvidenceValidationError(f"bound run {key} mismatch")
        validate_accounting(run_semantic.get("accounting"), "candidate run")

        benchmark_artifact = require_mapping(
            semantic.get("benchmark_suite"), "benchmark suite artifact"
        )
        if benchmark_artifact.get("artifact_type") != P6_BENCHMARK_EVIDENCE_TYPE:
            raise EvidenceValidationError("benchmark suite artifact type mismatch")
        suite_payload = {
            key: benchmark_artifact.get(key)
            for key in (
                "comparison_contract_id",
                "candidate_run_result_id",
                "eligible_opportunity_set_sha256",
                "cash",
                "passive",
                "random",
            )
        }
        if (
            benchmark_artifact.get("suite_id") != attestation.benchmark_suite_id
            or attestation.benchmark_suite_id
            != f"benchmark-suite@{canonical_sha256(suite_payload)}"
            or suite_payload["comparison_contract_id"]
            != attestation.comparison_contract_id
            or suite_payload["candidate_run_result_id"] != attestation.run_result_id
            or suite_payload["eligible_opportunity_set_sha256"]
            != comparison.get("eligible_opportunity_set_sha256")
        ):
            raise EvidenceValidationError("benchmark suite identity mismatch")

        benchmark_ids: list[str] = []

        def validate_benchmark_record(value: Any, label: str) -> Mapping[str, Any]:
            record = require_mapping(value, label)
            result_id = record.get("result_id")
            benchmark_payload = {
                key: record.get(key)
                for key in (
                    "benchmark_kind",
                    "vehicle",
                    "accounting",
                    "comparable",
                    "matching_diagnostics",
                    "trial_id",
                    "seed",
                    "run_result_id",
                )
            }
            if result_id != f"benchmark-result@{canonical_sha256(benchmark_payload)}":
                raise EvidenceValidationError(f"{label} identity mismatch")
            if not isinstance(result_id, str):
                raise EvidenceValidationError(f"{label} result id is missing")
            benchmark_ids.append(result_id)
            if record.get("comparable") is True:
                validate_accounting(record.get("accounting"), label)
            return record

        for key in ("cash", "passive"):
            value = benchmark_artifact.get(key)
            if value is not None:
                validate_benchmark_record(value, f"{key} benchmark")
        random_value = benchmark_artifact.get("random")
        if random_value is not None:
            random_record = require_mapping(random_value, "random distribution")
            trials = require_list(random_record.get("trials"), "random trials")
            random_payload = {"seed": random_record.get("seed"), "trials": trials}
            distribution_id = random_record.get("distribution_id")
            if distribution_id != f"random-distribution@{canonical_sha256(random_payload)}":
                raise EvidenceValidationError("random distribution identity mismatch")
            if not isinstance(distribution_id, str):
                raise EvidenceValidationError("random distribution id is missing")
            benchmark_ids.append(distribution_id)
            for index, value in enumerate(trials):
                validate_benchmark_record(value, f"random trial {index}")
        if tuple(benchmark_ids) != attestation.benchmark_result_ids:
            raise EvidenceValidationError("benchmark result list does not match suite")

        required_benchmarks = require_list(
            comparison.get("required_benchmarks"), "required benchmarks"
        )
        benchmark_fields = {
            "CASH": benchmark_artifact.get("cash"),
            "PASSIVE_PERPETUAL": benchmark_artifact.get("passive"),
            "RANDOM_MATCHED": benchmark_artifact.get("random"),
        }
        required_comparable = True
        for kind in required_benchmarks:
            record = benchmark_fields.get(kind)
            if not isinstance(record, Mapping) or record.get("comparable") is not True:
                required_comparable = False

        hurdles = require_list(comparison.get("hurdles"), "comparison hurdles")
        gates = require_list(semantic.get("gates"), "qualification gates")
        if len(gates) != len(hurdles):
            raise EvidenceValidationError("qualification gate count mismatch")
        for index, (hurdle_value, gate_value) in enumerate(zip(hurdles, gates, strict=True)):
            hurdle = require_mapping(hurdle_value, f"hurdle {index}")
            gate = require_mapping(gate_value, f"gate {index}")
            for gate_key, hurdle_key in (
                ("gate_id", "gate_id"),
                ("metric", "metric"),
                ("operator", "operator"),
                ("hurdle", "threshold"),
            ):
                if gate.get(gate_key) != hurdle.get(hurdle_key):
                    raise EvidenceValidationError(
                        f"qualification gate {index} does not match preregistration"
                    )
        candidate_complete = run_identity.get("completeness") == "COMPLETE"
        gate_testability = [
            require_mapping(item, f"gate {index}").get("testable") is True
            for index, item in enumerate(gates)
        ]
        gate_passes = [
            require_mapping(item, f"gate {index}").get("passed") is True
            for index, item in enumerate(gates)
        ]
        if attestation.verdict == "QUALIFIED" and not (
            candidate_complete
            and required_comparable
            and all(gate_testability)
            and all(gate_passes)
        ):
            raise EvidenceValidationError("QUALIFIED verdict disagrees with bound gates")
        if attestation.verdict == "REJECTED" and not (
            candidate_complete
            and required_comparable
            and all(gate_testability)
            and not all(gate_passes)
        ):
            raise EvidenceValidationError("REJECTED verdict disagrees with bound gates")
        if attestation.verdict == "NOT_TESTABLE" and (
            candidate_complete and required_comparable and all(gate_testability)
        ):
            raise EvidenceValidationError("NOT_TESTABLE verdict has no testability failure")

        required_ids = set(attestation.required_evidence_ids)
        if any(evidence_id not in evidence for evidence_id in required_ids):
            raise EvidenceValidationError("required economic evidence is not registered")
        required_references = [evidence[evidence_id] for evidence_id in required_ids]
        for reference in required_references:
            cls._validate_evidence(reference, verify_local=True, require_complete=True)
        evidence_requirements = require_list(
            comparison.get("evidence_requirements"), "evidence requirements"
        )
        present_types = {item.evidence_type for item in required_references}
        if any(
            not isinstance(required, str) or required not in present_types
            for required in evidence_requirements
        ):
            raise EvidenceValidationError("comparison evidence requirement is unsatisfied")

        run_references = [
            item for item in required_references if item.evidence_type == P6_RUN_EVIDENCE_TYPE
        ]
        benchmark_references = [
            item
            for item in required_references
            if item.evidence_type == P6_BENCHMARK_EVIDENCE_TYPE
        ]
        if len(run_references) != 1 or len(benchmark_references) != 1:
            raise EvidenceValidationError(
                "formal qualification requires exactly one run and benchmark artifact"
            )
        for reference in (*run_references, *benchmark_references):
            if (
                reference.producing_revision_id != protocol.experiment_revision_id
                or reference.producing_code_revision != protocol.code_revision
            ):
                raise EvidenceValidationError("P6 artifact provenance mismatch")
        if load_local_artifact(run_references[0], "run evidence") != run_artifact:
            raise EvidenceValidationError("run evidence bytes do not match bound run")
        if (
            load_local_artifact(benchmark_references[0], "benchmark evidence")
            != benchmark_artifact
        ):
            raise EvidenceValidationError(
                "benchmark evidence bytes do not match bound benchmark suite"
            )
        dataset_evidence_id = run_identity.get("dataset_evidence_id")
        if not isinstance(dataset_evidence_id, str) or dataset_evidence_id not in required_ids:
            raise EvidenceValidationError("bound dataset evidence is not required")
        dataset_reference = evidence[dataset_evidence_id]
        data_interval = require_mapping(
            comparison.get("data_interval"), "comparison data interval"
        )
        if (
            dataset_reference.content_sha256
            != run_identity.get("dataset_content_sha256")
            or dataset_evidence_id != data_interval.get("dataset_evidence_id")
            or dataset_reference.content_sha256
            != data_interval.get("dataset_content_sha256")
        ):
            raise EvidenceValidationError("dataset identity/hash binding mismatch")
        try:
            from ..economic.acceptance_verifier import (
                validate_persisted_qualification_semantics,
            )
            validate_persisted_qualification_semantics(semantic, dataset_reference)
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceValidationError(
                f"formal P6 semantic replay failed: {exc}"
            ) from exc

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
                if (
                    event.source != P6_DECISION_SOURCE
                    or event.previous_status is not DecisionStatus.STATISTICALLY_QUALIFIED
                    or event.economic_result_id is None
                ):
                    raise RegistryCorruptionError(
                        "economic qualification lacks the dedicated P6 decision binding"
                    )
                result_reference = evidence.get(event.economic_result_id)
                protocol = protocols[event.experiment_revision_id]
                if (
                    result_reference is None
                    or result_reference.evidence_type != P6_RESULT_EVIDENCE_TYPE
                    or result_reference.completeness is not EvidenceCompleteness.COMPLETE
                    or not isinstance(protocol.benchmark, VersionedIdentity)
                ):
                    raise RegistryCorruptionError(
                        "economic qualification references invalid P6 evidence"
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
