"""Eligible timestamp universe and walk-forward split manifest for H40.

Implements the half-open split schedule with purge isolation and strict
pre-outcome partitioning under H40_PROTOCOL_V1_R2.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ..research_contract.canonical import canonical_json, canonical_sha256
from .guards import H40GuardError, H40ReasonCode

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
class H40SplitManifest:
    """Preregistered split schedule and timestamp authority for H40."""

    protocol_identity_hash: str
    source_manifest_hash: str
    base_eligible_start_utc: str
    base_eligible_end_utc: str
    base_eligible_count: int
    partitions: tuple[H40Partition, ...]
    exclusion_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        """Serializes split manifest to dictionary."""
        return {
            "protocol_identity_hash": self.protocol_identity_hash,
            "source_manifest_hash": self.source_manifest_hash,
            "base_eligible_start_utc": self.base_eligible_start_utc,
            "base_eligible_end_utc": self.base_eligible_end_utc,
            "base_eligible_count": self.base_eligible_count,
            "partitions": [p.to_dict() for p in self.partitions],
            "exclusion_counts": dict(sorted(self.exclusion_counts.items())),
        }

    def canonical_json(self) -> str:
        """Returns RFC-8259 canonical JSON representation."""
        return canonical_json(self.to_dict())

    @property
    def split_hash(self) -> str:
        """Returns SHA-256 hash over canonical JSON identity."""
        return canonical_sha256(self.to_dict())

    def get_partition(self, partition_id: str) -> H40Partition:
        """Retrieves a partition by ID or raises KeyError."""
        for p in self.partitions:
            if p.partition_id == partition_id:
                return p
        raise KeyError(f"Partition '{partition_id}' not found in H40SplitManifest.")

    @classmethod
    def get_base_eligible_timestamps(cls) -> list[str]:
        """Returns the full list of 43,825 base-eligible hourly timestamps."""
        return generate_hourly_range(
            BASE_ELIGIBLE_START_UTC,
            BASE_ELIGIBLE_END_UTC,
            inclusive_end=True,
        )

    @classmethod
    def build_default(
        cls,
        protocol_identity_hash: str,
        source_manifest_hash: str,
    ) -> H40SplitManifest:
        """Constructs the canonical preregistered split schedule."""
        all_eligible = cls.get_base_eligible_timestamps()
        if len(all_eligible) != BASE_ELIGIBLE_COUNT:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                f"Eligible timestamp count mismatch: expected {BASE_ELIGIBLE_COUNT}, got {len(all_eligible)}.",
            )

        eligible_set = set(all_eligible)

        raw_specs: list[tuple[str, str, H40PartitionType, str, str]] = [
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
        ]

        partitions: list[H40Partition] = []
        for part_id, fold, part_type, s_utc, e_utc in raw_specs:
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

        # Exclusions breakdown
        # Lookback reserved: 720 hours (2021-01-01T00:00:00Z to 2021-01-31T00:00:00Z)
        # Horizon truncated: 23 hours (2026-01-31T01:00:00Z to 2026-01-31T23:00:00Z)
        # Confirmation holdout truncated at dataset edge: 24 * 1 - 1 = 23h (or 24h between 2026-01-31T00:00:00Z and 2026-02-01T00:00:00Z is 24h)
        # Purge intervals: 8 * 24h (WF purges) + 1 * 24h (confirmation purge) = 216h
        exclusion_counts: dict[str, int] = {
            H40ReasonCode.LOOKBACK_RESERVED.value: 720,
            H40ReasonCode.HORIZON_TRUNCATED.value: 23,
            H40ReasonCode.PURGE_BOUNDARY.value: 216,
        }

        return cls(
            protocol_identity_hash=protocol_identity_hash,
            source_manifest_hash=source_manifest_hash,
            base_eligible_start_utc=BASE_ELIGIBLE_START_UTC,
            base_eligible_end_utc=BASE_ELIGIBLE_END_UTC,
            base_eligible_count=BASE_ELIGIBLE_COUNT,
            partitions=tuple(partitions),
            exclusion_counts=exclusion_counts,
        )
