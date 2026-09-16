"""Eligible timestamp universe and walk-forward split manifest for H40.

Implements the half-open split schedule with purge isolation and strict
pre-outcome partitioning under H40_PROTOCOL_V1_R2.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from ..research_contract.canonical import canonical_json, canonical_sha256
from .guards import H40GuardError, H40ReasonCode
from .source_manifest import (
    H40SourceManifest,
    H40SourceStatus,
    extract_verified_source_timestamps,
    validate_source_artifact,
)

BASE_ELIGIBLE_START_UTC: str = "2021-01-31T00:00:00Z"
BASE_ELIGIBLE_END_UTC: str = "2026-01-31T00:00:00Z"
BASE_ELIGIBLE_COUNT: int = 43825


class H40PartitionType(str, Enum):
    """Semantic classification of split partitions."""

    TRAIN = "TRAIN"
    CALIBRATION = "CALIBRATION"
    VALIDATION = "VALIDATION"
    PURGE = "PURGE"
    CONFIRMATION_TRAIN = "CONFIRMATION_TRAIN"
    CONFIRMATION_PURGE = "CONFIRMATION_PURGE"
    CONFIRMATION_HOLDOUT = "CONFIRMATION_HOLDOUT"


RAW_PARTITION_SPECS: tuple[tuple[str, str, H40PartitionType, str, str], ...] = (
    # WF1
    ("WF1_TRAIN", "WF1", H40PartitionType.TRAIN, "2021-01-31T00:00:00Z", "2022-10-31T00:00:00Z"),
    ("WF1_PURGE_1", "WF1", H40PartitionType.PURGE, "2022-10-31T00:00:00Z", "2022-11-01T00:00:00Z"),
    ("WF1_CALIBRATION", "WF1", H40PartitionType.CALIBRATION, "2022-11-01T00:00:00Z", "2023-01-31T00:00:00Z"),
    ("WF1_PURGE_2", "WF1", H40PartitionType.PURGE, "2023-01-31T00:00:00Z", "2023-02-01T00:00:00Z"),
    ("WF1_VALIDATION", "WF1", H40PartitionType.VALIDATION, "2023-02-01T00:00:00Z", "2023-07-31T00:00:00Z"),
    # WF2
    ("WF2_TRAIN", "WF2", H40PartitionType.TRAIN, "2021-01-31T00:00:00Z", "2023-04-30T00:00:00Z"),
    ("WF2_PURGE_1", "WF2", H40PartitionType.PURGE, "2023-04-30T00:00:00Z", "2023-05-01T00:00:00Z"),
    ("WF2_CALIBRATION", "WF2", H40PartitionType.CALIBRATION, "2023-05-01T00:00:00Z", "2023-07-31T00:00:00Z"),
    ("WF2_PURGE_2", "WF2", H40PartitionType.PURGE, "2023-07-31T00:00:00Z", "2023-08-01T00:00:00Z"),
    ("WF2_VALIDATION", "WF2", H40PartitionType.VALIDATION, "2023-08-01T00:00:00Z", "2024-01-31T00:00:00Z"),
    # WF3
    ("WF3_TRAIN", "WF3", H40PartitionType.TRAIN, "2021-01-31T00:00:00Z", "2023-10-31T00:00:00Z"),
    ("WF3_PURGE_1", "WF3", H40PartitionType.PURGE, "2023-10-31T00:00:00Z", "2023-11-01T00:00:00Z"),
    ("WF3_CALIBRATION", "WF3", H40PartitionType.CALIBRATION, "2023-11-01T00:00:00Z", "2024-01-31T00:00:00Z"),
    ("WF3_PURGE_2", "WF3", H40PartitionType.PURGE, "2024-01-31T00:00:00Z", "2024-02-01T00:00:00Z"),
    ("WF3_VALIDATION", "WF3", H40PartitionType.VALIDATION, "2024-02-01T00:00:00Z", "2024-07-31T00:00:00Z"),
    # WF4
    ("WF4_TRAIN", "WF4", H40PartitionType.TRAIN, "2021-01-31T00:00:00Z", "2024-04-30T00:00:00Z"),
    ("WF4_PURGE_1", "WF4", H40PartitionType.PURGE, "2024-04-30T00:00:00Z", "2024-05-01T00:00:00Z"),
    ("WF4_CALIBRATION", "WF4", H40PartitionType.CALIBRATION, "2024-05-01T00:00:00Z", "2024-07-31T00:00:00Z"),
    ("WF4_PURGE_2", "WF4", H40PartitionType.PURGE, "2024-07-31T00:00:00Z", "2024-08-01T00:00:00Z"),
    ("WF4_VALIDATION", "WF4", H40PartitionType.VALIDATION, "2024-08-01T00:00:00Z", "2025-01-31T00:00:00Z"),
    # Confirmation
    ("CONFIRMATION_TRAIN", "CONFIRMATION", H40PartitionType.CONFIRMATION_TRAIN, "2021-01-31T00:00:00Z", "2025-01-31T00:00:00Z"),
    ("CONFIRMATION_PURGE", "CONFIRMATION", H40PartitionType.CONFIRMATION_PURGE, "2025-01-31T00:00:00Z", "2025-02-01T00:00:00Z"),
    ("CONFIRMATION_HOLDOUT", "CONFIRMATION", H40PartitionType.CONFIRMATION_HOLDOUT, "2025-02-01T00:00:00Z", "2026-02-01T00:00:00Z"),
)


def iso_to_ms(iso_str: str) -> int:
    """Converts ISO 8601 UTC timestamp string to millisecond timestamp."""
    dt = datetime.fromisoformat(iso_str)
    return int(dt.timestamp() * 1000)


def ms_to_iso(ms: int) -> str:
    """Converts millisecond timestamp to ISO 8601 UTC timestamp string."""
    dt = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_hourly_range(start_utc: str, end_utc: str, inclusive_end: bool = False) -> list[str]:
    """Generates hourly ISO 8601 UTC timestamp strings between start and end."""
    start_ms = iso_to_ms(start_utc)
    end_ms = iso_to_ms(end_utc)
    step_ms = 3600 * 1000
    limit_ms = end_ms + 1 if inclusive_end else end_ms
    return [ms_to_iso(t) for t in range(start_ms, limit_ms, step_ms)]


@dataclass(frozen=True)
class H40Partition:
    """Descriptor for an individual dataset partition."""

    partition_id: str
    fold: str
    partition_type: H40PartitionType
    start_utc: str
    end_utc: str
    count: int
    first_timestamp_utc: str | None
    last_timestamp_utc: str | None
    timestamps_sha256: str

    def to_dict(self) -> dict[str, Any]:
        """Serializes partition to dictionary."""
        return {
            "partition_id": self.partition_id,
            "fold": self.fold,
            "partition_type": self.partition_type.value,
            "start_utc": self.start_utc,
            "end_utc": self.end_utc,
            "count": self.count,
            "first_timestamp_utc": self.first_timestamp_utc,
            "last_timestamp_utc": self.last_timestamp_utc,
            "timestamps_sha256": self.timestamps_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40Partition:
        """Deserializes from a mapping."""
        return cls(
            partition_id=str(data["partition_id"]),
            fold=str(data["fold"]),
            partition_type=H40PartitionType(str(data["partition_type"])),
            start_utc=str(data["start_utc"]),
            end_utc=str(data["end_utc"]),
            count=int(data["count"]),
            first_timestamp_utc=(
                str(data["first_timestamp_utc"])
                if data.get("first_timestamp_utc") is not None
                else None
            ),
            last_timestamp_utc=(
                str(data["last_timestamp_utc"])
                if data.get("last_timestamp_utc") is not None
                else None
            ),
            timestamps_sha256=str(data["timestamps_sha256"]),
        )


@dataclass(frozen=True)
class H40SplitAttestation:
    """Cryptographic attestation binding an authoritative split to verified source artifacts and protocol."""

    protocol_identity_hash: str
    source_manifest_hash: str
    split_hash: str
    btc_source_id: str
    btc_locator: str
    btc_file_sha256: str
    btc_membership_sha256: str
    btc_timestamp_count: int
    eth_source_id: str
    eth_locator: str
    eth_file_sha256: str
    eth_membership_sha256: str
    eth_timestamp_count: int
    attestation_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_identity_hash": self.protocol_identity_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "split_hash": self.split_hash,
            "btc_source_id": self.btc_source_id,
            "btc_locator": self.btc_locator,
            "btc_file_sha256": self.btc_file_sha256,
            "btc_membership_sha256": self.btc_membership_sha256,
            "btc_timestamp_count": self.btc_timestamp_count,
            "eth_source_id": self.eth_source_id,
            "eth_locator": self.eth_locator,
            "eth_file_sha256": self.eth_file_sha256,
            "eth_membership_sha256": self.eth_membership_sha256,
            "eth_timestamp_count": self.eth_timestamp_count,
            "attestation_hash": self.attestation_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40SplitAttestation:
        return cls(
            protocol_identity_hash=str(data["protocol_identity_hash"]),
            source_manifest_hash=str(data["source_manifest_hash"]),
            split_hash=str(data["split_hash"]),
            btc_source_id=str(data["btc_source_id"]),
            btc_locator=str(data["btc_locator"]),
            btc_file_sha256=str(data["btc_file_sha256"]),
            btc_membership_sha256=str(data["btc_membership_sha256"]),
            btc_timestamp_count=int(data["btc_timestamp_count"]),
            eth_source_id=str(data["eth_source_id"]),
            eth_locator=str(data["eth_locator"]),
            eth_file_sha256=str(data["eth_file_sha256"]),
            eth_membership_sha256=str(data["eth_membership_sha256"]),
            eth_timestamp_count=int(data["eth_timestamp_count"]),
            attestation_hash=str(data["attestation_hash"]),
        )

    def compute_attestation_hash(self) -> str:
        d = {
            "protocol_identity_hash": self.protocol_identity_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "split_hash": self.split_hash,
            "btc_source_id": self.btc_source_id,
            "btc_locator": self.btc_locator,
            "btc_file_sha256": self.btc_file_sha256,
            "btc_membership_sha256": self.btc_membership_sha256,
            "btc_timestamp_count": self.btc_timestamp_count,
            "eth_source_id": self.eth_source_id,
            "eth_locator": self.eth_locator,
            "eth_file_sha256": self.eth_file_sha256,
            "eth_membership_sha256": self.eth_membership_sha256,
            "eth_timestamp_count": self.eth_timestamp_count,
        }
        return canonical_sha256(d)

    @classmethod
    def create(
        cls,
        protocol_identity_hash: str,
        source_manifest_hash: str,
        split_hash: str,
        btc_source_id: str,
        btc_locator: str,
        btc_file_sha256: str,
        btc_membership_sha256: str,
        btc_timestamp_count: int,
        eth_source_id: str,
        eth_locator: str,
        eth_file_sha256: str,
        eth_membership_sha256: str,
        eth_timestamp_count: int,
    ) -> H40SplitAttestation:
        preimage = {
            "protocol_identity_hash": protocol_identity_hash,
            "source_manifest_hash": source_manifest_hash,
            "split_hash": split_hash,
            "btc_source_id": btc_source_id,
            "btc_locator": btc_locator,
            "btc_file_sha256": btc_file_sha256,
            "btc_membership_sha256": btc_membership_sha256,
            "btc_timestamp_count": btc_timestamp_count,
            "eth_source_id": eth_source_id,
            "eth_locator": eth_locator,
            "eth_file_sha256": eth_file_sha256,
            "eth_membership_sha256": eth_membership_sha256,
            "eth_timestamp_count": eth_timestamp_count,
        }
        att_hash = canonical_sha256(preimage)
        return cls(
            protocol_identity_hash=protocol_identity_hash,
            source_manifest_hash=source_manifest_hash,
            split_hash=split_hash,
            btc_source_id=btc_source_id,
            btc_locator=btc_locator,
            btc_file_sha256=btc_file_sha256,
            btc_membership_sha256=btc_membership_sha256,
            btc_timestamp_count=btc_timestamp_count,
            eth_source_id=eth_source_id,
            eth_locator=eth_locator,
            eth_file_sha256=eth_file_sha256,
            eth_membership_sha256=eth_membership_sha256,
            eth_timestamp_count=eth_timestamp_count,
            attestation_hash=att_hash,
        )


def _compute_partitions_from_timestamps(
    common_timestamps: Sequence[str],
) -> tuple[tuple[H40Partition, ...], int, dict[str, int]]:
    """Pure internal helper computing half-open partitions from validated timestamp sequence."""
    lookback_reserved_ts = [
        t for t in common_timestamps if "2021-01-01T00:00:00Z" <= t < BASE_ELIGIBLE_START_UTC
    ]
    lookback_reserved_count = len(lookback_reserved_ts)

    eligible_candidates = [
        t for t in common_timestamps if t >= BASE_ELIGIBLE_START_UTC
    ]
    eligible_candidate_set = set(eligible_candidates)

    expected_eligible = generate_hourly_range(
        BASE_ELIGIBLE_START_UTC,
        BASE_ELIGIBLE_END_UTC,
        inclusive_end=True,
    )
    expected_eligible_set = set(expected_eligible)
    missing_hours = expected_eligible_set - eligible_candidate_set
    gap_count = len(missing_hours)

    max_dataset_ms = max(iso_to_ms(t) for t in common_timestamps)

    partitions: list[H40Partition] = []
    horizon_truncated_count = 0
    purge_boundary_count = 0

    for part_id, fold, part_type, s_utc, e_utc in RAW_PARTITION_SPECS:
        unfiltered_ts = generate_hourly_range(s_utc, e_utc, inclusive_end=False)
        valid_ts = [t for t in unfiltered_ts if t in eligible_candidate_set]

        if part_type == H40PartitionType.CONFIRMATION_HOLDOUT:
            covered_ts = []
            for t in valid_ts:
                if iso_to_ms(t) + 23 * 3600 * 1000 <= max_dataset_ms:
                    covered_ts.append(t)
                else:
                    horizon_truncated_count += 1
            valid_ts = covered_ts

        if part_type in {H40PartitionType.PURGE, H40PartitionType.CONFIRMATION_PURGE}:
            purge_boundary_count += len(valid_ts)

        ts_str = ",".join(valid_ts)
        ts_hash = hashlib.sha256(ts_str.encode("utf-8")).hexdigest()

        partitions.append(
            H40Partition(
                partition_id=part_id,
                fold=fold,
                partition_type=part_type,
                start_utc=s_utc,
                end_utc=e_utc,
                count=len(valid_ts),
                first_timestamp_utc=valid_ts[0] if valid_ts else None,
                last_timestamp_utc=valid_ts[-1] if valid_ts else None,
                timestamps_sha256=ts_hash,
            )
        )

    base_count = len([t for t in eligible_candidates if t in expected_eligible_set])

    exclusion_counts = {
        H40ReasonCode.LOOKBACK_RESERVED.value: lookback_reserved_count,
        H40ReasonCode.HORIZON_TRUNCATED.value: horizon_truncated_count,
        H40ReasonCode.PURGE_BOUNDARY.value: purge_boundary_count,
        H40ReasonCode.SOURCE_GAP.value: gap_count,
    }
    return tuple(partitions), base_count, exclusion_counts


@dataclass(frozen=True)
class H40SplitManifest:
    """Preregistered split schedule and timestamp authority for H40."""

    protocol_identity_hash: str
    source_manifest_hash: str
    base_eligible_start_utc: str
    base_eligible_end_utc: str
    base_eligible_count: int
    partitions: tuple[H40Partition, ...]
    exclusion_counts: dict[str, int]
    is_authoritative: bool = False
    attestation: H40SplitAttestation | None = None

    def _to_canonical_dict(self) -> dict[str, Any]:
        """Serializes core split partition structure for canonical hash calculation."""
        return {
            "protocol_identity_hash": self.protocol_identity_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "base_eligible_start_utc": self.base_eligible_start_utc,
            "base_eligible_end_utc": self.base_eligible_end_utc,
            "base_eligible_count": self.base_eligible_count,
            "partitions": [p.to_dict() for p in self.partitions],
            "exclusion_counts": dict(sorted(self.exclusion_counts.items())),
            "is_authoritative": self.is_authoritative,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serializes split manifest to dictionary including attestation if present."""
        d = self._to_canonical_dict()
        if self.attestation is not None:
            d["attestation"] = self.attestation.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40SplitManifest:
        """Deserializes from a mapping."""
        att = None
        if "attestation" in data and data["attestation"] is not None:
            att = H40SplitAttestation.from_dict(data["attestation"])
        return cls(
            protocol_identity_hash=str(data["protocol_identity_hash"]),
            source_manifest_hash=str(data["source_manifest_hash"]),
            base_eligible_start_utc=str(data["base_eligible_start_utc"]),
            base_eligible_end_utc=str(data["base_eligible_end_utc"]),
            base_eligible_count=int(data["base_eligible_count"]),
            partitions=tuple(H40Partition.from_dict(p) for p in data["partitions"]),
            exclusion_counts={str(k): int(v) for k, v in data["exclusion_counts"].items()},
            is_authoritative=bool(data.get("is_authoritative", False)),
            attestation=att,
        )

    def canonical_json(self) -> str:
        """Returns RFC-8259 canonical JSON representation."""
        return canonical_json(self.to_dict())

    @property
    def split_hash(self) -> str:
        """Returns SHA-256 hash over canonical JSON identity."""
        return canonical_sha256(self._to_canonical_dict())

    def get_partition(self, partition_id: str) -> H40Partition:
        """Retrieves a partition by ID or raises KeyError."""
        for p in self.partitions:
            if p.partition_id == partition_id:
                return p
        raise KeyError(f"Partition '{partition_id}' not found in H40SplitManifest.")

    def assert_authoritative(
        self,
        source_manifest: H40SourceManifest,
        repo_root: Path | str,
    ) -> None:
        """Verifies split authority against verified source manifest and mandatory cold artifact check.

        Fails closed if:
        - Manifest is not marked authoritative (is_authoritative=False)
        - Attestation is missing or invalid
        - Source manifest is not supplied or manifest hash mismatches
        - repo_root is not supplied or invalid
        - Source manifest does not contain verified BTC and ETH receipts matching attestation
        - Cold validation against repo_root fails or produces differing bytes/timestamps
        - Cold partition reconstruction from artifact timestamps does not match persisted partitions
        """
        if not self.is_authoritative:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Split manifest is not authoritative.",
            )
        if self.attestation is None:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Split manifest lacks an authoritative split attestation.",
            )
        if source_manifest is None:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Split authority cannot be verified without source manifest authority; "
                "supply a verified H40SourceManifest.",
            )
        if repo_root is None or str(repo_root).strip() == "":
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Split authority cannot be verified without a cold artifact repository root; "
                "supply a valid repo_root.",
            )

        # 1. Attestation self-consistency
        if self.attestation.protocol_identity_hash != self.protocol_identity_hash:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Attestation protocol identity hash mismatch.",
            )
        if self.attestation.source_manifest_hash != self.source_manifest_hash:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Attestation source manifest hash mismatch.",
            )
        if self.attestation.split_hash != self.split_hash:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Attestation split hash mismatch with partitions.",
            )

        # 2. Check attestation self-hash
        expected_att_hash = self.attestation.compute_attestation_hash()
        if self.attestation.attestation_hash != expected_att_hash:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "Attestation self-hash is invalid or tampered.",
            )

        # 3. Verify against source_manifest
        if source_manifest.manifest_hash != self.source_manifest_hash:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"Split source_manifest_hash '{self.source_manifest_hash}' does not match "
                f"supplied source manifest hash '{source_manifest.manifest_hash}'.",
            )
        if source_manifest.protocol_identity_hash != self.protocol_identity_hash:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Source manifest protocol identity hash does not match split protocol identity hash.",
            )

        # Verify BTC source record in manifest
        btc_rec = source_manifest.get_source(self.attestation.btc_source_id)
        if (
            btc_rec.status != H40SourceStatus.VERIFIED
            or btc_rec.receipt is None
            or btc_rec.receipt.status != H40SourceStatus.VERIFIED
        ):
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "BTC source record in source manifest is not VERIFIED.",
            )
        if btc_rec.locator != self.attestation.btc_locator:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"BTC locator mismatch: record has '{btc_rec.locator}', attestation has '{self.attestation.btc_locator}'.",
            )
        if btc_rec.receipt.file_sha256 != self.attestation.btc_file_sha256:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "BTC receipt file SHA-256 does not match attestation.",
            )
        if btc_rec.receipt.timestamp_membership_hash != self.attestation.btc_membership_sha256:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "BTC receipt timestamp membership hash does not match attestation.",
            )
        if btc_rec.receipt.timestamp_count != self.attestation.btc_timestamp_count:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                "BTC receipt timestamp count does not match attestation.",
            )

        # Verify ETH source record in manifest
        eth_rec = source_manifest.get_source(self.attestation.eth_source_id)
        if (
            eth_rec.status != H40SourceStatus.VERIFIED
            or eth_rec.receipt is None
            or eth_rec.receipt.status != H40SourceStatus.VERIFIED
        ):
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "ETH source record in source manifest is not VERIFIED.",
            )
        if eth_rec.locator != self.attestation.eth_locator:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"ETH locator mismatch: record has '{eth_rec.locator}', attestation has '{self.attestation.eth_locator}'.",
            )
        if eth_rec.receipt.file_sha256 != self.attestation.eth_file_sha256:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "ETH receipt file SHA-256 does not match attestation.",
            )
        if eth_rec.receipt.timestamp_membership_hash != self.attestation.eth_membership_sha256:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "ETH receipt timestamp membership hash does not match attestation.",
            )
        if eth_rec.receipt.timestamp_count != self.attestation.eth_timestamp_count:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                "ETH receipt timestamp count does not match attestation.",
            )

        # 4. Mandatory cold verification of BTC and ETH artifacts on disk
        btc_cold = validate_source_artifact(
            repo_root,
            btc_rec,
            expected_product="BTCUSDT",
            expected_cadence="1h",
        )
        if btc_cold.status != H40SourceStatus.VERIFIED:
            raise H40GuardError(
                btc_cold.reason_code or H40ReasonCode.NOT_TESTABLE,
                f"BTC artifact cold validation failed: {btc_cold.notes}",
            )
        if btc_cold.file_sha256 != self.attestation.btc_file_sha256:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "BTC artifact on disk does not match attestation file SHA-256.",
            )
        if btc_cold.timestamp_membership_hash != self.attestation.btc_membership_sha256:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "BTC artifact on disk does not match attestation timestamp membership hash.",
            )
        if btc_cold.timestamp_count != self.attestation.btc_timestamp_count:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                "BTC artifact on disk does not match attestation timestamp count.",
            )

        eth_cold = validate_source_artifact(
            repo_root,
            eth_rec,
            expected_product="ETHUSDT",
            expected_cadence="1h",
        )
        if eth_cold.status != H40SourceStatus.VERIFIED:
            raise H40GuardError(
                eth_cold.reason_code or H40ReasonCode.NOT_TESTABLE,
                f"ETH artifact cold validation failed: {eth_cold.notes}",
            )
        if eth_cold.file_sha256 != self.attestation.eth_file_sha256:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "ETH artifact on disk does not match attestation file SHA-256.",
            )
        if eth_cold.timestamp_membership_hash != self.attestation.eth_membership_sha256:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "ETH artifact on disk does not match attestation timestamp membership hash.",
            )
        if eth_cold.timestamp_count != self.attestation.eth_timestamp_count:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                "ETH artifact on disk does not match attestation timestamp count.",
            )

        # 5. Extract verified source timestamps from artifacts and cold-reconstruct split
        btc_timestamps = extract_verified_source_timestamps(
            repo_root=repo_root,
            record=btc_rec,
            expected_product="BTCUSDT",
            expected_cadence="1h",
        )
        eth_timestamps = extract_verified_source_timestamps(
            repo_root=repo_root,
            record=eth_rec,
            expected_product="ETHUSDT",
            expected_cadence="1h",
        )

        common_set = set(btc_timestamps).intersection(set(eth_timestamps))
        if not common_set:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "No overlapping timestamps found between cold BTC and ETH sources.",
            )
        common_timestamps = sorted(common_set)

        reconstructed_partitions, reconstructed_base_count, reconstructed_exclusions = (
            _compute_partitions_from_timestamps(common_timestamps)
        )

        if reconstructed_base_count != self.base_eligible_count:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                f"Reconstructed base eligible count {reconstructed_base_count} does not match "
                f"persisted count {self.base_eligible_count}.",
            )
        if reconstructed_exclusions != self.exclusion_counts:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                "Reconstructed exclusion counts do not match persisted exclusion counts.",
            )
        if reconstructed_partitions != self.partitions:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                "Reconstructed partitions from cold artifacts do not match persisted partitions.",
            )

        reconstructed_manifest = H40SplitManifest(
            protocol_identity_hash=self.protocol_identity_hash,
            source_manifest_hash=self.source_manifest_hash,
            base_eligible_start_utc=self.base_eligible_start_utc,
            base_eligible_end_utc=self.base_eligible_end_utc,
            base_eligible_count=reconstructed_base_count,
            partitions=reconstructed_partitions,
            exclusion_counts=reconstructed_exclusions,
            is_authoritative=True,
            attestation=None,
        )
        if reconstructed_manifest.split_hash != self.split_hash:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                f"Reconstructed split hash '{reconstructed_manifest.split_hash}' does not match "
                f"persisted split hash '{self.split_hash}'.",
            )

    @classmethod
    def get_base_eligible_timestamps(cls) -> list[str]:
        """Returns the full list of 43,825 base-eligible hourly timestamps."""
        return generate_hourly_range(
            BASE_ELIGIBLE_START_UTC,
            BASE_ELIGIBLE_END_UTC,
            inclusive_end=True,
        )

    @classmethod
    def build_preregistered_schedule(
        cls,
        protocol_identity_hash: str,
        source_manifest_hash: str,
    ) -> H40SplitManifest:
        """Constructs the reference preregistered split schedule assuming continuous calendar."""
        all_eligible = cls.get_base_eligible_timestamps()
        if len(all_eligible) != BASE_ELIGIBLE_COUNT:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                f"Eligible timestamp count mismatch: expected {BASE_ELIGIBLE_COUNT}, got {len(all_eligible)}.",
            )

        eligible_set = set(all_eligible)

        partitions: list[H40Partition] = []
        for part_id, fold, part_type, s_utc, e_utc in RAW_PARTITION_SPECS:
            # Half-open hourly generation
            unfiltered_ts = generate_hourly_range(s_utc, e_utc, inclusive_end=False)
            # Intersect with base eligible timestamps
            valid_ts = [t for t in unfiltered_ts if t in eligible_set]
            ts_str = ",".join(valid_ts)
            ts_hash = hashlib.sha256(ts_str.encode("utf-8")).hexdigest()

            partitions.append(
                H40Partition(
                    partition_id=part_id,
                    fold=fold,
                    partition_type=part_type,
                    start_utc=s_utc,
                    end_utc=e_utc,
                    count=len(valid_ts),
                    first_timestamp_utc=valid_ts[0] if valid_ts else None,
                    last_timestamp_utc=valid_ts[-1] if valid_ts else None,
                    timestamps_sha256=ts_hash,
                )
            )

        exclusion_counts: dict[str, int] = {
            H40ReasonCode.LOOKBACK_RESERVED.value: 720,
            H40ReasonCode.HORIZON_TRUNCATED.value: 23,
            H40ReasonCode.PURGE_BOUNDARY.value: 216,
            H40ReasonCode.SOURCE_GAP.value: 0,
        }

        return cls(
            protocol_identity_hash=protocol_identity_hash,
            source_manifest_hash=source_manifest_hash,
            base_eligible_start_utc=BASE_ELIGIBLE_START_UTC,
            base_eligible_end_utc=BASE_ELIGIBLE_END_UTC,
            base_eligible_count=BASE_ELIGIBLE_COUNT,
            partitions=tuple(partitions),
            exclusion_counts=exclusion_counts,
            is_authoritative=False,
        )

    @classmethod
    def build_default(
        cls,
        protocol_identity_hash: str,
        source_manifest_hash: str,
    ) -> H40SplitManifest:
        """Convenience alias for build_preregistered_schedule."""
        return cls.build_preregistered_schedule(protocol_identity_hash, source_manifest_hash)

    @classmethod
    def materialize_authoritative(
        cls,
        protocol_identity_hash: str,
        source_manifest: H40SourceManifest,
        repo_root: Path | str,
        btc_source_id: str = "BTCUSDT_USD_M_1H",
        eth_source_id: str = "ETHUSDT_USD_M_1H",
    ) -> H40SplitManifest:
        """Authoritative split builder: materializes split partitions from verified source authority on disk."""
        if source_manifest.protocol_identity_hash != protocol_identity_hash:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Source manifest protocol identity hash does not match requested protocol identity hash.",
            )

        btc_rec = source_manifest.get_source(btc_source_id)
        if (
            btc_rec.status != H40SourceStatus.VERIFIED
            or btc_rec.receipt is None
            or btc_rec.receipt.status != H40SourceStatus.VERIFIED
        ):
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"Source record '{btc_source_id}' is not verified or lacks verified receipt.",
            )

        eth_rec = source_manifest.get_source(eth_source_id)
        if (
            eth_rec.status != H40SourceStatus.VERIFIED
            or eth_rec.receipt is None
            or eth_rec.receipt.status != H40SourceStatus.VERIFIED
        ):
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"Source record '{eth_source_id}' is not verified or lacks verified receipt.",
            )

        btc_ts = extract_verified_source_timestamps(
            repo_root=repo_root,
            record=btc_rec,
            expected_product="BTCUSDT",
            expected_cadence="1h",
        )
        eth_ts = extract_verified_source_timestamps(
            repo_root=repo_root,
            record=eth_rec,
            expected_product="ETHUSDT",
            expected_cadence="1h",
        )

        btc_set = set(btc_ts)
        eth_set = set(eth_ts)
        common_set = btc_set.intersection(eth_set)
        if not common_set:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "No overlapping timestamps found between BTC and ETH sources.",
            )
        common_timestamps = sorted(common_set)

        partitions, base_count, exclusion_counts = _compute_partitions_from_timestamps(common_timestamps)

        # Build candidate unattested manifest to get canonical split_hash
        candidate_manifest = cls(
            protocol_identity_hash=protocol_identity_hash,
            source_manifest_hash=source_manifest.manifest_hash,
            base_eligible_start_utc=BASE_ELIGIBLE_START_UTC,
            base_eligible_end_utc=BASE_ELIGIBLE_END_UTC,
            base_eligible_count=base_count,
            partitions=partitions,
            exclusion_counts=exclusion_counts,
            is_authoritative=True,
            attestation=None,
        )
        split_hash = candidate_manifest.split_hash

        att_dict = {
            "protocol_identity_hash": protocol_identity_hash,
            "source_manifest_hash": source_manifest.manifest_hash,
            "split_hash": split_hash,
            "btc_source_id": btc_rec.source_id,
            "btc_locator": btc_rec.locator,
            "btc_file_sha256": btc_rec.receipt.file_sha256,
            "btc_membership_sha256": btc_rec.receipt.timestamp_membership_hash,
            "btc_timestamp_count": btc_rec.receipt.timestamp_count,
            "eth_source_id": eth_rec.source_id,
            "eth_locator": eth_rec.locator,
            "eth_file_sha256": eth_rec.receipt.file_sha256,
            "eth_membership_sha256": eth_rec.receipt.timestamp_membership_hash,
            "eth_timestamp_count": eth_rec.receipt.timestamp_count,
        }
        att_hash = canonical_sha256(att_dict)
        attestation = H40SplitAttestation(
            protocol_identity_hash=protocol_identity_hash,
            source_manifest_hash=source_manifest.manifest_hash,
            split_hash=split_hash,
            btc_source_id=btc_rec.source_id,
            btc_locator=btc_rec.locator,
            btc_file_sha256=btc_rec.receipt.file_sha256,
            btc_membership_sha256=btc_rec.receipt.timestamp_membership_hash,
            btc_timestamp_count=btc_rec.receipt.timestamp_count,
            eth_source_id=eth_rec.source_id,
            eth_locator=eth_rec.locator,
            eth_file_sha256=eth_rec.receipt.file_sha256,
            eth_membership_sha256=eth_rec.receipt.timestamp_membership_hash,
            eth_timestamp_count=eth_rec.receipt.timestamp_count,
            attestation_hash=att_hash,
        )

        return cls(
            protocol_identity_hash=protocol_identity_hash,
            source_manifest_hash=source_manifest.manifest_hash,
            base_eligible_start_utc=BASE_ELIGIBLE_START_UTC,
            base_eligible_end_utc=BASE_ELIGIBLE_END_UTC,
            base_eligible_count=base_count,
            partitions=partitions,
            exclusion_counts=exclusion_counts,
            is_authoritative=True,
            attestation=attestation,
        )

    @classmethod
    def build_materialized(
        cls,
        protocol_identity_hash: str,
        source_manifest_hash: str,
        btc_timestamps: Sequence[str],
        eth_timestamps: Sequence[str],
        btc_receipt: Any | None = None,
        eth_receipt: Any | None = None,
    ) -> H40SplitManifest:
        """Constructs a materialized split manifest from caller-provided timestamp arrays.

        NOTE: This constructor returns is_authoritative=False with attestation=None.
        Raw caller-supplied timestamp arrays cannot confer authoritative split status
        under H40 protocol authority. To materialize an authoritative split manifest,
        call `materialize_authoritative(protocol_identity_hash, source_manifest, repo_root)`.
        """
        if not btc_timestamps or not eth_timestamps:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "Split builder requires non-empty timestamp arrays for BTC and ETH.",
            )

        common_set = set(btc_timestamps).intersection(set(eth_timestamps))
        if not common_set:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                "No overlapping timestamps found between BTC and ETH sources.",
            )
        common_timestamps = sorted(common_set)

        partitions, base_count, exclusion_counts = _compute_partitions_from_timestamps(common_timestamps)

        return cls(
            protocol_identity_hash=protocol_identity_hash,
            source_manifest_hash=source_manifest_hash,
            base_eligible_start_utc=BASE_ELIGIBLE_START_UTC,
            base_eligible_end_utc=BASE_ELIGIBLE_END_UTC,
            base_eligible_count=base_count,
            partitions=partitions,
            exclusion_counts=exclusion_counts,
            is_authoritative=False,
            attestation=None,
        )
