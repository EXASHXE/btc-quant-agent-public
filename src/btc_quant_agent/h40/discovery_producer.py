"""Deterministic Discovery evidence production; no selection or authorization.

Callers must supply an already authorized production context. This module never
creates lifecycle authorization, reads non-Discovery outcomes, or selects a slot.
"""

from __future__ import annotations

import ctypes
import hashlib
import math
import os
import stat
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from ..research_contract.canonical import canonical_json, canonical_sha256
from . import discovery_evidence as science
from . import lifecycle_authority as lifecycle
from .discovery_evidence import _fail
from .guards import H40GuardError, H40ProtectedSurfaceGuard, H40ReasonCode
from .lifecycle_authority import (
    H40CandidateResultEntry,
    H40DiscoveryAuthorizationReceipt,
    H40DiscoveryResultEvidence,
    H40DiscoveryRunGrant,
    H40LifecycleImplementationAuthority,
    H40P3ControllerAuthority,
    H40RunAuthority,
    H40RuntimeRosterEntry,
    H40RuntimeSnapshotSeal,
)
from .protocol_authority import compute_protocol_authority_hash
from .search_space import materialize_h40_search_space_production
from .source_manifest import H40SourceStatus
from .split_manifest import H40SplitManifest


def _rename_noreplace(directory_fd: int, source: str, target: str) -> None:
    """Atomic rename with no overwrite, including a concurrently created target."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        _fail("atomic no-replace rename is unavailable", H40ReasonCode.NOT_TESTABLE)
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(directory_fd, os.fsencode(source), directory_fd, os.fsencode(target), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), target)


class H40DiscoveryEvidenceWriter:
    """Canonical, durable, no-clobber writes beneath one real approved directory."""

    __slots__ = ("_identity", "_root")

    def __init__(self, approved_root: Path | str) -> None:
        self._root = _safe_directory(Path(approved_root))
        info = self._root.stat()
        self._identity = (info.st_dev, info.st_ino)

    def __setattr__(self, name: str, value: object) -> None:
        if hasattr(self, name):
            _fail("evidence writer authority is write-once")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        _fail("evidence writer authority cannot be deleted")

    @property
    def approved_root(self) -> Path:
        return self._root

    def _check_location(self, root_fd: int, shard_fd: int, shard: str) -> None:
        current_root = _open_directory(self._root)
        try:
            info = os.fstat(current_root)
            if (info.st_dev, info.st_ino) != self._identity:
                _fail("approved evidence root identity changed")
            current_shard = os.open(shard, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                actual, expected = os.fstat(current_shard), os.fstat(shard_fd)
                if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                    _fail("evidence shard namespace changed")
            finally:
                os.close(current_shard)
        finally:
            os.close(current_root)

    def write(self, payload: Mapping[str, Any]) -> str:
        data = canonical_json(payload).encode("utf-8")
        # Hash the same canonical snapshot we write, even if the caller mutates
        # its mapping concurrently. This equals canonical_sha256(exact object).
        digest = hashlib.sha256(data).hexdigest()
        _safe_directory(self._root)
        temporary = f".{uuid.uuid4().hex}.tmp"
        target = f"{digest}.json"
        root_fd: int | None = None
        shard_fd: int | None = None
        own_identity: tuple[int, int] | None = None
        complete = False
        try:
            root_fd = _open_directory(self._root)
            info = os.fstat(root_fd)
            if (info.st_dev, info.st_ino) != self._identity:
                _fail("approved evidence root identity changed")
            try:
                os.mkdir(digest[:2], dir_fd=root_fd)
            except FileExistsError:
                pass
            shard_fd = os.open(digest[:2], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            os.fsync(root_fd)
            self._check_location(root_fd, shard_fd, digest[:2])
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=shard_fd)
            with os.fdopen(descriptor, "wb") as stream:
                info = os.fstat(stream.fileno())
                own_identity = (info.st_dev, info.st_ino)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self._check_location(root_fd, shard_fd, digest[:2])
            try:
                _rename_noreplace(shard_fd, temporary, target)
            except FileExistsError:
                descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=shard_fd)
                with os.fdopen(descriptor, "rb") as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode) or stream.read() != data:
                        _fail("conflicting or noncanonical content at evidence digest")
                    os.fsync(stream.fileno())
            self._check_location(root_fd, shard_fd, digest[:2])
            os.fsync(shard_fd)
            self._check_location(root_fd, shard_fd, digest[:2])
            complete = True
        except OSError as exc:
            raise H40GuardError(
                H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "unsafe or unwritable evidence path",
            ) from exc
        finally:
            if shard_fd is not None:
                try:
                    # If the namespace moved during publication, revoke only
                    # our own inode. Never remove another writer's existing file.
                    if not complete and own_identity is not None:
                        try:
                            info = os.stat(target, dir_fd=shard_fd, follow_symlinks=False)
                            if (info.st_dev, info.st_ino) == own_identity:
                                os.unlink(target, dir_fd=shard_fd)
                                os.fsync(shard_fd)
                        except FileNotFoundError:
                            pass
                    try:
                        os.unlink(temporary, dir_fd=shard_fd)
                    except FileNotFoundError:
                        pass
                finally:
                    os.close(shard_fd)
            if root_fd is not None:
                os.close(root_fd)
        return digest



def _policies() -> dict[str, dict[str, str]]:
    return {name: {"policy_id": value[0], "policy_hash": value[1]}
            for name, value in science._POLICIES.items()}


def _safe_directory(path: Path) -> Path:
    H40ProtectedSurfaceGuard.assert_path_allowed(path)
    if "confirmation" in str(path).lower():
        _fail("Discovery evidence cannot use a Confirmation directory", H40ReasonCode.PROTECTED_SURFACE_DENIED)
    if ".." in path.parts or any(part.is_symlink() for part in (path, *path.parents)):
        _fail("authority directory cannot escape or traverse a symlink")
    if not path.is_dir():
        _fail("authority directory must exist")
    return path.resolve(strict=True)


def _open_directory(path: Path) -> int:
    """Traverse every absolute component using directory descriptors, never symlinks."""
    absolute = path.absolute()
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for component in absolute.parts[1:]:
            next_descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@dataclass(frozen=True)
class H40DiscoveryProductionResult:
    evidence: H40DiscoveryResultEvidence
    entries: tuple[H40CandidateResultEntry, ...]
    approved_evidence_root: Path
    dependency_digests: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class H40ProductionDiscoveryEvidenceProducer:
    """Produce the complete sealed roster's evidence without selecting a winner.

    Authorization is supplied by the Controller lifecycle. Sources are cold
    verified at entry and again before publication of the typed final object.
    """

    implementation_authority: H40LifecycleImplementationAuthority
    controller_authority: H40P3ControllerAuthority
    authorization_receipt: H40DiscoveryAuthorizationReceipt
    run_authority: H40RunAuthority
    seal: H40RuntimeSnapshotSeal
    split_manifest: H40SplitManifest
    approved_evidence_root: Path
    repo_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "approved_evidence_root", _safe_directory(Path(self.approved_evidence_root)))
        object.__setattr__(self, "repo_root", _safe_directory(Path(self.repo_root)))
        self._validate_authority()

    def _validate_authority(self) -> None:
        for value, accepted_type in (
            (self.implementation_authority, H40LifecycleImplementationAuthority),
            (self.controller_authority, H40P3ControllerAuthority),
            (self.authorization_receipt, H40DiscoveryAuthorizationReceipt),
            (self.run_authority, H40RunAuthority), (self.seal, H40RuntimeSnapshotSeal),
            (self.split_manifest, H40SplitManifest),
        ):
            if type(value) is not accepted_type:
                _fail("producer requires exact typed production authority")
        # Decode snapshots through the schemas, so caller-supplied instance
        # delegates cannot provide authority hashes or survive into production.
        for field, authority_type in (
            ("implementation_authority", H40LifecycleImplementationAuthority),
            ("controller_authority", H40P3ControllerAuthority),
            ("authorization_receipt", H40DiscoveryAuthorizationReceipt),
            ("run_authority", H40RunAuthority),
        ):
            value = getattr(self, field)
            if "to_dict" in vars(value):
                _fail("shadowed authority serialization is forbidden")
            authority_type.from_dict(authority_type.to_dict(value))
        implementation = self.implementation_authority.lifecycle_implementation_authority_hash
        controller = self.controller_authority
        receipt = self.authorization_receipt
        if (
            implementation != lifecycle.ACCEPTED_LIFECYCLE_IMPLEMENTATION_AUTHORITY_HASH
            or controller.controller_authority_hash != lifecycle.ACCEPTED_H40_P3_CONTROLLER_AUTHORITY_HASH
            or controller.lifecycle_implementation_authority_hash != implementation
            or receipt.receipt_schema_id != "H40_RECEIPT_DISCOVERY_AUTH_V3"
            or receipt.execution_disabled is not True
            or receipt.upstream_receipt_hash is not None
            or self.seal.synthetic_only
        ):
            _fail("producer authority is unaccepted, synthetic, or not V3")
        _safe_directory(self.repo_root)
        _safe_directory(self.approved_evidence_root)
        # Check locators before cold verification can read any source bytes.
        if self.seal._source_manifest_context is None or self.seal._runtime_attestation_context is None:
            _fail("production seal lacks source context")
        for source_id in self.seal._runtime_attestation_context.active_required_source_ids:
            record = self.seal._source_manifest_context.get_source(source_id)
            locator = Path(record.locator)
            path = self.repo_root / locator
            H40ProtectedSurfaceGuard.assert_path_allowed(path, source_id=source_id)
            if locator.is_absolute() or ".." in locator.parts or any(
                part.is_symlink() for part in (path, *path.parents)
            ):
                _fail("source locator cannot escape or traverse a symlink")
        if (
            self.seal._split_manifest_context is None
            or self.split_manifest.to_dict() != self.seal._split_manifest_context.to_dict()
            or self.seal._repo_root_context is None
            or self.repo_root != self.seal._repo_root_context.resolve()
            or self.seal._runtime_attestation_context is None
            or self.seal._runtime_attestation_context.active_required_source_ids != ("ETHUSDT_USD_M_1H",)
            or self.seal._runtime_attestation_context.sealed_registered_roster_hash != self.seal.sealed_registered_roster_hash
            or (self.seal.registered_slot_count, self.seal.not_testable_slot_count) != (18, 150)
        ):
            _fail("producer source, split, root, or roster does not match production seal")
        expected_roster = sorted([
            {"structural_configuration_hash": slot.structural_configuration_hash,
             "family_id": "+".join(family.value for family in slot.family_combination),
             "slot_hash": slot.slot_hash, "slot_index": slot.slot_index}
            for slot in materialize_h40_search_space_production().slots if slot.status == "REGISTERED"
        ], key=lambda entry: str(entry["structural_configuration_hash"]))
        if any(type(entry) is not H40RuntimeRosterEntry for entry in self.seal.roster) or [
            H40RuntimeRosterEntry.to_dict(entry) for entry in self.seal.roster
        ] != expected_roster:
            _fail("producer roster metadata differs from the exact accepted 18 slots")
        expected_run = H40RunAuthority.from_seal(self.seal, implementation)
        if self.run_authority != expected_run:
            _fail("producer run does not match accepted authority and seal")
        grant = H40DiscoveryRunGrant.from_controller_and_run(
            controller_authority=controller, run_authority=expected_run, seal=self.seal,
            authorized_at_utc=receipt.authorized_at_utc,
        )
        expected = {
            **{key: getattr(expected_run, key) for key in H40RunAuthority._KEYS - {"schema_id"}},
            "run_authority_id": expected_run.run_authority_id,
            "controller_authority_hash": controller.controller_authority_hash,
            "discovery_run_grant_hash": grant.discovery_run_grant_hash,
            "registered_slot_count": 18, "not_testable_slot_count": 150, "total_slot_count": 168,
        }
        if any(getattr(receipt, key) != value for key, value in expected.items()):
            _fail("Discovery V3 receipt does not bind the exact production run")
        H40RuntimeSnapshotSeal.verify_against_accepted_ledger(self.seal)

    def _source(self) -> tuple[dict[str, Any], dict[tuple[datetime, str], science._Bar],
                              dict[str, list[tuple[datetime, str]]]]:
        source = self.seal._source_manifest_context
        attestation = self.seal._runtime_attestation_context
        assert source is not None and attestation is not None
        record = source.get_source("ETHUSDT_USD_M_1H")
        assert record.receipt is not None
        attested = next(item for item in attestation.active_source_evidence if item.source_id == record.source_id)
        locator = Path(record.locator)
        path = self.repo_root / locator
        if (
            locator.is_absolute() or ".." in locator.parts
            or any(part.is_symlink() for part in (path, *path.parents))
            or record.product != "ETHUSDT" or record.cadence != "1h"
            or record.receipt.status != H40SourceStatus.VERIFIED
            or canonical_sha256(record.to_dict()) != attested.source_record_hash
            or canonical_sha256(record.receipt.to_dict()) != attested.source_validation_receipt_hash
        ):
            _fail("source locator or attested source identity mismatch")
        H40ProtectedSurfaceGuard.assert_path_allowed(path, source_id=record.source_id)
        directory = _open_directory(path.parent)
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    _fail("source must be a regular file")
                raw = stream.read()
        finally:
            os.close(directory)
        if hashlib.sha256(raw).hexdigest() != record.file_sha256 or record.file_sha256 != attested.file_sha256:
            _fail("canonical source bytes changed")
        extracted, economic = science._extract_economic_rows(
            path, raw, record.product, record.cadence, record.receipt.timestamp_field,
        )
        bars = {(bar.timestamp, bar.product): bar for bar in extracted}
        universes: dict[str, list[tuple[datetime, str]]] = {}
        for partition in ("WF1_TRAIN", "WF1_CALIBRATION"):
            start, end, _ = science._partition_bounds(partition)
            keys = sorted(key for key in bars if start <= key[0] < end)
            timestamps = sorted({t.strftime("%Y-%m-%dT%H:%M:%SZ") for t, _ in keys})
            sealed = self.split_manifest.get_partition(partition)
            if (sealed.count != len(timestamps) or sealed.timestamps_sha256 != hashlib.sha256(
                    ",".join(timestamps).encode()).hexdigest()):
                _fail("source-derived base membership differs from sealed split")
            universes[partition] = keys
        payload = {
            "schema_id": "H40_P3B_SOURCE_DERIVATION_V2",
            "run_authority_id": self.run_authority.run_authority_id,
            "source_manifest_hash": self.seal.source_manifest_hash,
            "split_manifest_hash": self.seal.split_manifest_hash,
            "split_attestation_hash": self.seal.split_attestation_hash,
            "provenance_contract_hash": lifecycle.DISCOVERY_PROVENANCE_CONTRACT_HASH,
            "policies": _policies(),
            "source_support": {"start_utc": "2021-01-01T00:00:00Z",
                               "end_utc_exclusive": "2023-02-01T00:00:00Z"},
            "active_source_derivations": [{
                "source_id": record.source_id, "product": record.product, "cadence": record.cadence,
                "locator": record.locator, "source_file_sha256": record.file_sha256,
                "source_validation_receipt_sha256": attested.source_validation_receipt_hash,
                "timestamp_field": record.receipt.timestamp_field,
                "economic_row_count": len(economic), "economic_rows_sha256": canonical_sha256(economic),
            }],
            "base_eligible_membership": {partition: [
                {"timestamp": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "product": product}
                for t, product in keys
            ] for partition, keys in universes.items()},
        }
        return payload, bars, universes

    def produce(self) -> H40DiscoveryProductionResult:
        self._validate_authority()
        writer = H40DiscoveryEvidenceWriter(self.approved_evidence_root)
        dependencies: set[str] = set()

        def store(payload: Mapping[str, Any]) -> str:
            digest = writer.write(payload)
            dependencies.add(digest)
            return digest

        common = {"run_authority_id": self.run_authority.run_authority_id,
                  "sealed_registered_roster_hash": self.seal.sealed_registered_roster_hash,
                  "policies": _policies()}
        lineage = {"source_manifest_hash": self.seal.source_manifest_hash,
                   "split_manifest_hash": self.seal.split_manifest_hash}
        source, bars, universes = self._source()
        source_hash = store(source)
        roster = self.seal.roster
        slots = {slot.structural_configuration_hash: slot
                 for slot in materialize_h40_search_space_production().slots}
        groups: dict[str, list[str]] = {family: [] for family in science._FAMILIES}
        for item in roster:
            slot = slots[item.structural_configuration_hash]
            if tuple(slot.asset_scope) != ("ETHUSDT",) or len(slot.family_combination) != 1:
                _fail("producer roster contains an unsupported scientific slot")
            groups[item.family_id].append(item.structural_configuration_hash)
        correction_hash = store({
            **common, **lineage, "schema_id": "H40_P3B_DISCOVERY_CORRECTION_MANIFEST_V1",
            "discovery_authorization_receipt_hash": self.authorization_receipt.receipt_sha256,
            "materialized_run_authority_hash": self.seal.materialized_run_authority_hash,
            "discovery_partition": "WF1_CALIBRATION",
            "discovery_selection_correction_contract_hash": lifecycle.DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
            "candidate_configuration_hashes": [item.structural_configuration_hash for item in roster],
            "metric_universes": {"PRECISION": groups, "NET_EXPECTANCY": groups},
        })
        decisions = {
            item.structural_configuration_hash: {
                partition: tuple(science._derive_source_decision(
                    candidate_id=item.structural_configuration_hash,
                    slot=slots[item.structural_configuration_hash], partition_id=partition,
                    timestamp=t, product=product,
                    horizon=int(slots[item.structural_configuration_hash].primary_horizon.rstrip("h")),
                    bars=bars, source_evidence_hash=source_hash,
                ) for t, product in keys)
                for partition, keys in universes.items()
            } for item in roster
        }
        geometry = science._geometry_training_rows([
            (slots[item.structural_configuration_hash], decisions[item.structural_configuration_hash]["WF1_TRAIN"])
            for item in roster
        ])
        entries: list[H40CandidateResultEntry] = []
        for item in roster:
            candidate_id = item.structural_configuration_hash
            slot = slots[candidate_id]
            candidate_common = {**common, "structural_configuration_hash": candidate_id}
            rows = decisions[candidate_id]
            fit = None
            reason = None
            try:
                fit = science.h40_fit_calibrator(slot.calibration_contract_id, [
                    (row.raw_score, int(row.label == "LONG_LABEL"))
                    for row in rows["WF1_CALIBRATION"] if row.prefit_eligible and row.label != "NEUTRAL_LABEL"
                ])
            except H40GuardError as exc:
                if exc.reason_code != H40ReasonCode.NOT_TESTABLE:
                    raise
                reason = exc.message
            status = "COMPLETE" if fit is not None else "FIT_INVALID"
            calibrated: list[science._Decision] = []
            for row in rows["WF1_CALIBRATION"]:
                probability = None
                action = "NO_TRADE"
                net = None
                if fit is not None and row.prefit_eligible:
                    probability = science.h40_predict_calibrated(fit, row.raw_score)
                    if science._geometry_pass(row, slot, geometry):
                        action = science.h40_side_preserving_action(row.raw_score, probability, slot.action_threshold)
                    if action != "NO_TRADE":
                        net = science.h40_proxy_net_return(action, str(row.p0), str(row.ch))[1]
                calibrated.append(replace(row, supplied_p_up=probability, supplied_action=action, supplied_r_net=net))
            rows["WF1_CALIBRATION"] = tuple(calibrated)
            decision_hashes = {partition: store({
                **candidate_common, **lineage, "schema_id": "H40_P3B_RAW_DECISIONS_V2",
                "source_evidence_hash": source_hash, "partition_id": partition,
                "provenance_contract_hash": lifecycle.DISCOVERY_PROVENANCE_CONTRACT_HASH,
                "rows": [{
                    "timestamp": row.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"), "product": row.product,
                    "p_up": None if row.supplied_p_up is None else repr(row.supplied_p_up),
                    "final_action": row.supplied_action, "r_h": repr(row.r_h),
                    "r_net": None if row.supplied_r_net is None else repr(row.supplied_r_net),
                } for row in partition_rows],
            }) for partition, partition_rows in rows.items()}
            input_lineage = {"source_evidence_hash": source_hash,
                             "training_evidence_hash": decision_hashes["WF1_TRAIN"],
                             "calibration_evidence_hash": decision_hashes["WF1_CALIBRATION"]}
            audit = None if fit is None else science.h40_discovery_coverage_audit(
                sum(row.supplied_action in ("LONG", "SHORT") for row in calibrated), len(calibrated),
            ).to_dict()
            gates = {gate: store({
                **candidate_common, **input_lineage, "schema_id": "H40_P3B_HARD_GATE_INPUT_V1",
                "gate_id": gate, "audit": audit if gate == "COVERAGE" else None,
            }) for gate in sorted(science._HARD_GATES)}
            metrics: dict[str, str] = {}
            for metric in ("PRECISION", "NET_EXPECTANCY"):
                payload: dict[str, Any] = {**candidate_common, "metric_id": metric,
                           "correction_manifest_hash": correction_hash, "fit_status": status}
                if fit is None:
                    payload.update(schema_id="H40_P3B_INVALID_METRIC_INPUT_V1", fit_failure_reason=reason)
                else:
                    seed = science.h40_bootstrap_seed(candidate_id, metric)
                    low, high, _ = science._partition_bounds("WF1_CALIBRATION")
                    hours = int((high - low).total_seconds() // 3600)
                    _, matrix_hash = science.h40_bootstrap_starts(seed.seed, hours)
                    payload.update(
                        schema_id="H40_P3B_METRIC_BOOTSTRAP_V1",
                        calibration_evidence_hash=input_lineage["calibration_evidence_hash"],
                        seed_identity_policy_id=science._POLICIES["seed_identity"][0],
                        seed_identity_policy_hash=science._POLICIES["seed_identity"][1],
                        bootstrap_start_sampler_policy_id=science._POLICIES["bootstrap_start_sampler"][0],
                        bootstrap_start_sampler_policy_hash=science._POLICIES["bootstrap_start_sampler"][1],
                        protocol_id=compute_protocol_authority_hash(), candidate_id=candidate_id,
                        partition_id="WF1_CALIBRATION", canonical_seed_preimage=seed.canonical_seed_preimage,
                        seed_digest_sha256=seed.seed_digest_sha256, raw_u64=seed.raw_u64, seed=seed.seed,
                        numpy_version=np.__version__, bit_generator="PCG64", H=hours, L=science._L,
                        S=hours-science._L+1, B=math.ceil(hours/science._L), M=science._M,
                        start_matrix_hash=matrix_hash,
                    )
                metrics[metric] = store(payload)
            result_hash = store({
                **candidate_common, **lineage, **input_lineage,
                "schema_id": "H40_P3B_CANDIDATE_RESULT_INPUT_V1",
                "slot_hash": item.slot_hash, "slot_index": item.slot_index,
                "fit_status": status, "fit_failure_reason": reason,
                "hard_gate_input_evidence_hashes": gates,
                "precision_input_evidence_hash": metrics["PRECISION"],
                "net_expectancy_input_evidence_hash": metrics["NET_EXPECTANCY"],
            })
            entries.append(H40CandidateResultEntry(
                candidate_result_input_evidence_hash=result_hash, complexity=len(slot.family_combination),
                family_id=item.family_id, hard_gate_input_evidence_hashes=gates,
                precision_input_evidence_hash=metrics["PRECISION"], net_expectancy_input_evidence_hash=metrics["NET_EXPECTANCY"],
                slot_hash=item.slot_hash, slot_index=item.slot_index, structural_configuration_hash=candidate_id,
            ))
        self._validate_authority()
        evidence = H40DiscoveryResultEvidence(
            candidate_result_entries=tuple(entries), correction_input_evidence_manifest_hash=correction_hash,
            created_at_utc=self.authorization_receipt.authorized_at_utc,
            discovery_authorization_receipt_hash=self.authorization_receipt.receipt_sha256,
            materialized_run_authority_hash=self.seal.materialized_run_authority_hash,
            run_authority_id=self.run_authority.run_authority_id,
            sealed_registered_roster_hash=self.seal.sealed_registered_roster_hash,
        )
        evidence_hash = store(evidence.to_dict())
        if evidence_hash != evidence.evidence_sha256:
            _fail("published Discovery evidence identity mismatch")
        return H40DiscoveryProductionResult(evidence, tuple(entries), writer.approved_root, tuple(sorted(dependencies)))
