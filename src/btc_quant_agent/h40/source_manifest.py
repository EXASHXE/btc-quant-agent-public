"""Unprotected source-authority manifest for H40.

Inventories verified, unverified, diagnostic, and forbidden data sources in
compliance with BASE Section 4 and H40_PROTOCOL_V1_R2.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ..research_contract.canonical import canonical_json, canonical_sha256
from .guards import H40GuardError, H40ReasonCode


class H40SourceStatus(str, Enum):
    """Availability and admissibility status of a data source."""

    VERIFIED = "VERIFIED"
    NOT_TESTABLE = "NOT_TESTABLE"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    FORBIDDEN = "FORBIDDEN"


@dataclass(frozen=True)
class H40SourceRecord:
    """Canonical descriptor for a single candidate or diagnostic data source."""

    source_id: str
    status: H40SourceStatus
    locator: str
    cadence: str = "1h"
    row_count: int | None = None
    start_utc: str | None = None
    end_utc: str | None = None
    file_sha256: str | None = None
    archive_set_sha256: str | None = None
    gap_count: int = 0
    gaps: tuple[dict[str, Any], ...] = ()
    reason_code: H40ReasonCode | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serializes source record to dictionary."""
        return {
            "source_id": self.source_id,
            "status": self.status.value,
            "locator": self.locator,
            "cadence": self.cadence,
            "row_count": self.row_count,
            "start_utc": self.start_utc,
            "end_utc": self.end_utc,
            "file_sha256": self.file_sha256,
            "archive_set_sha256": self.archive_set_sha256,
            "gap_count": self.gap_count,
            "gaps": list(self.gaps),
            "reason_code": self.reason_code.value if self.reason_code else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40SourceRecord:
        """Deserializes from a mapping."""
        reason = (
            H40ReasonCode(str(data["reason_code"]))
            if data.get("reason_code") is not None
            else None
        )
        return cls(
            source_id=str(data["source_id"]),
            status=H40SourceStatus(str(data["status"])),
            locator=str(data["locator"]),
            cadence=str(data.get("cadence", "1h")),
            row_count=int(data["row_count"]) if data.get("row_count") is not None else None,
            start_utc=str(data["start_utc"]) if data.get("start_utc") is not None else None,
            end_utc=str(data["end_utc"]) if data.get("end_utc") is not None else None,
            file_sha256=str(data["file_sha256"]) if data.get("file_sha256") is not None else None,
            archive_set_sha256=(
                str(data["archive_set_sha256"])
                if data.get("archive_set_sha256") is not None
                else None
            ),
            gap_count=int(data.get("gap_count", 0)),
            gaps=tuple(data.get("gaps", ())),
            reason_code=reason,
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class H40SourceManifest:
    """Canonical inventory of data sources bound to an H40 protocol identity."""

    protocol_identity_hash: str
    sources: tuple[H40SourceRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serializes source manifest to dictionary."""
        return {
            "protocol_identity_hash": self.protocol_identity_hash,
            "sources": [s.to_dict() for s in self.sources],
        }

    def canonical_json(self) -> str:
        """Returns deterministic RFC-8259 canonical JSON."""
        return canonical_json(self.to_dict())

    @property
    def manifest_hash(self) -> str:
        """Returns SHA-256 hash over canonical JSON identity."""
        return canonical_sha256(self.to_dict())

    def get_source(self, source_id: str) -> H40SourceRecord:
        """Retrieves a source record by source ID or raises KeyError."""
        for s in self.sources:
            if s.source_id == source_id:
                return s
        raise KeyError(f"Source '{source_id}' not found in H40SourceManifest.")

    def validate_source_admissibility(self, source_id: str, purpose: str = "discovery") -> None:
        """Validates whether a source may be accessed for a specific purpose."""
        record = self.get_source(source_id)
        if record.status == H40SourceStatus.FORBIDDEN:
            raise H40GuardError(
                H40ReasonCode.PROTECTED_SURFACE_DENIED,
                f"Source '{source_id}' is FORBIDDEN ({record.notes}). Access denied.",
            )
        if record.status == H40SourceStatus.NOT_TESTABLE:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"Source '{source_id}' is NOT_TESTABLE ({record.notes}).",
            )
        if purpose == "discovery" and record.status == H40SourceStatus.DIAGNOSTIC_ONLY:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"Source '{source_id}' is marked DIAGNOSTIC_ONLY. Inadmissible for primary discovery.",
            )

    def verify_file_integrity(self, repo_root: Path | str, source_id: str) -> None:
        """Verifies disk file existence and SHA-256 match for a verified source."""
        record = self.get_source(source_id)
        if record.status != H40SourceStatus.VERIFIED:
            self.validate_source_admissibility(source_id, purpose="read")
            return

        file_path = Path(repo_root) / record.locator
        if not file_path.exists():
            raise H40GuardError(
                H40ReasonCode.SOURCE_MISSING,
                f"Required source file for '{source_id}' does not exist at {file_path}.",
            )

        if record.file_sha256 is not None:
            actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
            if actual_hash != record.file_sha256:
                raise H40GuardError(
                    H40ReasonCode.SOURCE_HASH_MISMATCH,
                    f"File hash mismatch for '{source_id}': expected {record.file_sha256}, got {actual_hash}.",
                )

    @classmethod
    def build_default(cls, protocol_identity_hash: str) -> H40SourceManifest:
        """Constructs the canonical preregistered unprotected source manifest."""
        sources: list[H40SourceRecord] = [
            H40SourceRecord(
                source_id="BTCUSDT_USD_M_1H",
                status=H40SourceStatus.VERIFIED,
                locator="data/research/BTCUSDT/data_manifest.json",
                cadence="1h",
                row_count=44568,
                start_utc="2021-01-01T00:00:00Z",
                end_utc="2026-01-31T23:00:00Z",
                file_sha256="928e913f41e74077359cbdf804aaf95d452ee1e1b80d5f05d28eafe4e0b639f2",
                gap_count=0,
                notes="BTCUSDT USD-M 1h klines verified against archive manifest and timeframe audit.",
            ),
            H40SourceRecord(
                source_id="ETHUSDT_USD_M_1H",
                status=H40SourceStatus.VERIFIED,
                locator="data/research/cross_asset_1h/ETHUSDT.parquet",
                cadence="1h",
                row_count=44568,
                start_utc="2021-01-01T00:00:00Z",
                end_utc="2026-01-31T23:00:00Z",
                file_sha256="563a1a4d927ec2a007481783be9bd76896e1be57198af80c4b2a30608e124608",
                archive_set_sha256="1efde37a765de90e33fd509bd1bcb729351beafa79314f684b3558665b19226c",
                gap_count=0,
                notes="ETHUSDT USD-M 1h klines from cross_asset_1h basket manifest.",
            ),
            H40SourceRecord(
                source_id="BTCUSDT_OFFICIAL_DERIVATIVES",
                status=H40SourceStatus.VERIFIED,
                locator="data/research/v0.3.19_official_derivatives/hourly_inputs.parquet",
                cadence="1h",
                file_sha256="77a8ad63fa0f1ead7c8481197661caa24171c7cf856c9b3326d72e376e0fcaed",
                gap_count=0,
                notes="Official BTCUSDT funding and derivative hourly records.",
            ),
            H40SourceRecord(
                source_id="BTCUSDT_SPOT_FLOW",
                status=H40SourceStatus.VERIFIED,
                locator="data/research/BTCUSDT_SPOT/data_manifest.json",
                cadence="1h",
                file_sha256="59bab3914fef973aaae04592540a51894e72c1d74e780c3dd830fbedc4b4acfa",
                gap_count=0,
                notes="Official BTCUSDT spot flow records.",
            ),
            H40SourceRecord(
                source_id="ETHUSDT_DERIVATIVES_FLOW",
                status=H40SourceStatus.NOT_TESTABLE,
                locator="data/research/cross_asset_1h/raw",
                cadence="1h",
                reason_code=H40ReasonCode.SOURCE_UNVERIFIED,
                notes="ETHUSDT derivatives, crowding, and flow inputs unverified in BASE Section 4.1.",
            ),
            H40SourceRecord(
                source_id="LOCAL_FORWARD_STORE",
                status=H40SourceStatus.DIAGNOSTIC_ONLY,
                locator="artifacts/forward_store",
                cadence="1h",
                notes="Local forward store admissible only for diagnostic checks, not primary discovery.",
            ),
            H40SourceRecord(
                source_id="HISTORICAL_RESEARCH_OUTPUTS",
                status=H40SourceStatus.DIAGNOSTIC_ONLY,
                locator="artifacts/research_registry.jsonl",
                cadence="1h",
                notes="Historical research outputs admissible only for diagnostic reference.",
            ),
            H40SourceRecord(
                source_id="H39_PROTECTED",
                status=H40SourceStatus.FORBIDDEN,
                locator="data/research/h39_validation/",
                reason_code=H40ReasonCode.PROTECTED_SURFACE_DENIED,
                notes="H39 protected outcome validation surface permanently sealed.",
            ),
            H40SourceRecord(
                source_id="FINAL_HOLDOUT",
                status=H40SourceStatus.FORBIDDEN,
                locator="artifacts/final_holdout",
                reason_code=H40ReasonCode.PROTECTED_SURFACE_DENIED,
                notes="Final holdout surface permanently sealed.",
            ),
        ]
        return cls(
            protocol_identity_hash=protocol_identity_hash,
            sources=tuple(sources),
        )
