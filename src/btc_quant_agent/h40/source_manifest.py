"""Unprotected source-authority manifest for H40.

Inventories verified, unverified, diagnostic, and forbidden data sources in
compliance with BASE Section 4 and H40_PROTOCOL_V1_R2.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from itertools import pairwise
from pathlib import Path
from typing import Any

from ..research_contract.canonical import canonical_json, canonical_sha256
from .guards import H40GuardError, H40ProtectedSurfaceGuard, H40ReasonCode
from .protocol import H40ProtocolIdentity


def _iso_to_ms(iso_str: str) -> int:
    dt = datetime.fromisoformat(iso_str)
    return int(dt.timestamp() * 1000)


def _ms_to_iso(ms: int) -> str:
    dt = datetime.fromtimestamp(ms / 1000, tz=UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class H40SourceStatus(str, Enum):
    """Availability and admissibility status of a data source."""

    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    NOT_TESTABLE = "NOT_TESTABLE"
    DIAGNOSTIC_ONLY = "DIAGNOSTIC_ONLY"
    FORBIDDEN = "FORBIDDEN"


@dataclass(frozen=True)
class H40SourceValidationReceipt:
    """Explicit local byte and timestamp validation receipt for a data source."""

    source_id: str
    locator: str
    file_sha256: str
    product: str
    cadence: str
    timestamp_field: str
    timestamp_count: int
    first_timestamp_utc: str | None
    last_timestamp_utc: str | None
    duplicate_count: int
    gap_count: int
    gaps: tuple[dict[str, Any], ...]
    timestamp_membership_hash: str
    status: H40SourceStatus
    archive_set_sha256: str | None = None
    reason_code: H40ReasonCode | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serializes receipt to dictionary."""
        return {
            "source_id": self.source_id,
            "locator": self.locator,
            "file_sha256": self.file_sha256,
            "product": self.product,
            "cadence": self.cadence,
            "timestamp_field": self.timestamp_field,
            "timestamp_count": self.timestamp_count,
            "first_timestamp_utc": self.first_timestamp_utc,
            "last_timestamp_utc": self.last_timestamp_utc,
            "duplicate_count": self.duplicate_count,
            "gap_count": self.gap_count,
            "gaps": [dict(g) for g in self.gaps],
            "timestamp_membership_hash": self.timestamp_membership_hash,
            "status": self.status.value,
            "archive_set_sha256": self.archive_set_sha256,
            "reason_code": self.reason_code.value if self.reason_code else None,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40SourceValidationReceipt:
        """Deserializes receipt from dictionary."""
        reason = (
            H40ReasonCode(str(data["reason_code"]))
            if data.get("reason_code") is not None
            else None
        )
        return cls(
            source_id=str(data["source_id"]),
            locator=str(data["locator"]),
            file_sha256=str(data["file_sha256"]),
            product=str(data.get("product", "")),
            cadence=str(data.get("cadence", "1h")),
            timestamp_field=str(data.get("timestamp_field", "")),
            timestamp_count=int(data.get("timestamp_count", 0)),
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
            duplicate_count=int(data.get("duplicate_count", 0)),
            gap_count=int(data.get("gap_count", 0)),
            gaps=tuple(dict(g) for g in data.get("gaps", ())),
            timestamp_membership_hash=str(data.get("timestamp_membership_hash", "")),
            status=H40SourceStatus(str(data["status"])),
            archive_set_sha256=(
                str(data["archive_set_sha256"])
                if data.get("archive_set_sha256") is not None
                else None
            ),
            reason_code=reason,
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class H40SourceRecord:
    """Canonical descriptor for a single candidate or diagnostic data source."""

    source_id: str
    status: H40SourceStatus
    locator: str
    cadence: str = "1h"
    product: str = ""
    row_count: int | None = None
    start_utc: str | None = None
    end_utc: str | None = None
    file_sha256: str | None = None
    archive_set_sha256: str | None = None
    gap_count: int = 0
    gaps: tuple[dict[str, Any], ...] = ()
    reason_code: H40ReasonCode | None = None
    notes: str = ""
    receipt: H40SourceValidationReceipt | None = None

    def __post_init__(self) -> None:
        # If status is not explicitly FORBIDDEN, any attempt to reference a protected surface fails closed
        if self.status != H40SourceStatus.FORBIDDEN:
            H40ProtectedSurfaceGuard.assert_path_allowed(self.locator, source_id=self.source_id)

        # Enforce that a source record cannot claim VERIFIED status without a valid receipt
        if self.status == H40SourceStatus.VERIFIED and (
            self.receipt is None or self.receipt.status != H40SourceStatus.VERIFIED
        ):
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"Source '{self.source_id}' cannot claim VERIFIED status without an explicit "
                "validation receipt produced from inspected local bytes/timestamps.",
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes source record to dictionary."""
        return {
            "source_id": self.source_id,
            "status": self.status.value,
            "locator": self.locator,
            "cadence": self.cadence,
            "product": self.product,
            "row_count": self.row_count,
            "start_utc": self.start_utc,
            "end_utc": self.end_utc,
            "file_sha256": self.file_sha256,
            "archive_set_sha256": self.archive_set_sha256,
            "gap_count": self.gap_count,
            "gaps": list(self.gaps),
            "reason_code": self.reason_code.value if self.reason_code else None,
            "notes": self.notes,
            "receipt": self.receipt.to_dict() if self.receipt else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> H40SourceRecord:
        """Deserializes from a mapping."""
        reason = (
            H40ReasonCode(str(data["reason_code"]))
            if data.get("reason_code") is not None
            else None
        )
        receipt = (
            H40SourceValidationReceipt.from_dict(data["receipt"])
            if data.get("receipt") is not None
            else None
        )
        return cls(
            source_id=str(data["source_id"]),
            status=H40SourceStatus(str(data["status"])),
            locator=str(data["locator"]),
            cadence=str(data.get("cadence", "1h")),
            product=str(data.get("product", "")),
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
            receipt=receipt,
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
        # Enforce protected surface authority independently of caller status
        H40ProtectedSurfaceGuard.assert_path_allowed(record.locator, source_id=record.source_id)

        if record.status == H40SourceStatus.FORBIDDEN:
            raise H40GuardError(
                H40ReasonCode.PROTECTED_SURFACE_DENIED,
                f"Source '{source_id}' is FORBIDDEN ({record.notes}). Access denied.",
            )
        if record.status in {H40SourceStatus.NOT_TESTABLE, H40SourceStatus.UNVERIFIED}:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"Source '{source_id}' is {record.status.value} ({record.notes}).",
            )
        if purpose == "discovery" and record.status == H40SourceStatus.DIAGNOSTIC_ONLY:
            raise H40GuardError(
                H40ReasonCode.SOURCE_UNVERIFIED,
                f"Source '{source_id}' is marked DIAGNOSTIC_ONLY. Inadmissible for primary discovery.",
            )

    def verify_file_integrity(self, repo_root: Path | str, source_id: str) -> None:
        """Verifies disk file existence and SHA-256 match for a verified source."""
        record = self.get_source(source_id)

        # Enforce protected surface authority BEFORE any filesystem operation
        H40ProtectedSurfaceGuard.assert_path_allowed(
            record.locator,
            source_id=record.source_id,
            repo_root=repo_root,
        )

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
    def build_preregistered_reference(cls, protocol_identity_hash: str) -> H40SourceManifest:
        """Constructs the preregistered reference inventory of candidate and diagnostic sources."""
        sources: list[H40SourceRecord] = [
            H40SourceRecord(
                source_id="BTCUSDT_USD_M_1H",
                status=H40SourceStatus.UNVERIFIED,
                locator="data/research/BTCUSDT/data_manifest.json",
                cadence="1h",
                product="BTCUSDT",
                row_count=44568,
                start_utc="2021-01-01T00:00:00Z",
                end_utc="2026-01-31T23:00:00Z",
                file_sha256="928e913f41e74077359cbdf804aaf95d452ee1e1b80d5f05d28eafe4e0b639f2",
                gap_count=0,
                notes="BTCUSDT USD-M 1h klines reference; requires local validation receipt.",
            ),
            H40SourceRecord(
                source_id="ETHUSDT_USD_M_1H",
                status=H40SourceStatus.UNVERIFIED,
                locator="data/research/cross_asset_1h/ETHUSDT.parquet",
                cadence="1h",
                product="ETHUSDT",
                row_count=44568,
                start_utc="2021-01-01T00:00:00Z",
                end_utc="2026-01-31T23:00:00Z",
                file_sha256="563a1a4d927ec2a007481783be9bd76896e1be57198af80c4b2a30608e124608",
                archive_set_sha256="1efde37a765de90e33fd509bd1bcb729351beafa79314f684b3558665b19226c",
                gap_count=0,
                notes="ETHUSDT USD-M 1h klines reference; requires local validation receipt.",
            ),
            H40SourceRecord(
                source_id="BTCUSDT_OFFICIAL_DERIVATIVES",
                status=H40SourceStatus.UNVERIFIED,
                locator="data/research/v0.3.19_official_derivatives/hourly_inputs.parquet",
                cadence="1h",
                product="BTCUSDT",
                file_sha256="77a8ad63fa0f1ead7c8481197661caa24171c7cf856c9b3326d72e376e0fcaed",
                gap_count=0,
                notes="Official BTCUSDT funding and derivative hourly records reference.",
            ),
            H40SourceRecord(
                source_id="BTCUSDT_SPOT_FLOW",
                status=H40SourceStatus.UNVERIFIED,
                locator="data/research/BTCUSDT_SPOT/data_manifest.json",
                cadence="1h",
                product="BTCUSDT",
                file_sha256="59bab3914fef973aaae04592540a51894e72c1d74e780c3dd830fbedc4b4acfa",
                gap_count=0,
                notes="Official BTCUSDT spot flow records reference.",
            ),
            H40SourceRecord(
                source_id="ETHUSDT_DERIVATIVES_FLOW",
                status=H40SourceStatus.NOT_TESTABLE,
                locator="data/research/cross_asset_1h/raw",
                cadence="1h",
                product="ETHUSDT",
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

    @classmethod
    def build_default(cls, protocol_identity_hash: str) -> H40SourceManifest:
        """Convenience alias for build_preregistered_reference."""
        return cls.build_preregistered_reference(protocol_identity_hash)


@dataclass(frozen=True)
class H40CanonicalSourceSpec:
    """Immutable canonical specification for an authorized H40 data source."""

    source_id: str
    product: str
    cadence: str
    locator: str
    allowed_role: str
    origin_provenance: str
    production_authority_state: H40SourceStatus = H40SourceStatus.NOT_TESTABLE
    reference_file_sha256: str | None = None
    archive_set_sha256: str | None = None
    protocol_identity_hash: str | None = None


def get_canonical_source_spec(
    protocol_identity_hash: str,
    source_id: str,
) -> H40CanonicalSourceSpec:
    """Retrieves immutable canonical source specification for a protocol-authorized source ID."""
    canonical_ref = H40SourceManifest.build_preregistered_reference(protocol_identity_hash)
    try:
        record = canonical_ref.get_source(source_id)
    except KeyError:
        raise H40GuardError(
            H40ReasonCode.SOURCE_UNVERIFIED,
            f"Source '{source_id}' is not an authorized canonical H40 source.",
        ) from None

    if source_id == "BTCUSDT_USD_M_1H":
        role = "PRIMARY_SPLIT_INPUT"
        provenance = record.notes or "BTCUSDT USD-M 1h klines reference"
        authority_state = H40SourceStatus.NOT_TESTABLE
    elif source_id == "ETHUSDT_USD_M_1H":
        role = "PRIMARY_SPLIT_INPUT"
        provenance = record.notes or "ETHUSDT USD-M 1h klines reference"
        authority_state = H40SourceStatus.VERIFIED
    else:
        role = "DIAGNOSTIC_OR_AUXILIARY"
        provenance = record.notes or "H40 Auxiliary Source"
        authority_state = H40SourceStatus.NOT_TESTABLE

    return H40CanonicalSourceSpec(
        source_id=record.source_id,
        product=record.product,
        cadence=record.cadence,
        locator=record.locator,
        allowed_role=role,
        origin_provenance=provenance,
        production_authority_state=authority_state,
        reference_file_sha256=record.file_sha256,
        archive_set_sha256=record.archive_set_sha256,
        protocol_identity_hash=protocol_identity_hash,
    )


def _assert_canonical_source_identity(
    record: H40SourceRecord,
    protocol_identity_hash: str,
    *,
    require_production_verified: bool,
) -> None:
    if protocol_identity_hash != H40ProtocolIdentity.default().protocol_hash:
        raise H40GuardError(
            H40ReasonCode.SOURCE_UNVERIFIED,
            "source identity is not bound to the accepted H40 protocol identity",
        )
    spec = get_canonical_source_spec(protocol_identity_hash, record.source_id)
    if record.product != spec.product:
        raise H40GuardError(
            H40ReasonCode.PRODUCT_MISMATCH,
            f"Source '{record.source_id}' product mismatch: expected canonical '{spec.product}', got '{record.product}'.",
        )
    if record.cadence != spec.cadence:
        raise H40GuardError(
            H40ReasonCode.INTERVAL_MISMATCH,
            f"Source '{record.source_id}' cadence mismatch: expected canonical '{spec.cadence}', got '{record.cadence}'.",
        )
    if record.locator != spec.locator:
        raise H40GuardError(
            H40ReasonCode.SOURCE_UNVERIFIED,
            f"Source '{record.source_id}' locator mismatch: expected canonical '{spec.locator}', got '{record.locator}'. "
            "Caller cannot substitute non-canonical locators for production H40 authority.",
        )
    if (
        require_production_verified
        and spec.production_authority_state != H40SourceStatus.VERIFIED
    ):
        raise H40GuardError(
            H40ReasonCode.SOURCE_UNVERIFIED,
            f"Source '{record.source_id}' production authority is {spec.production_authority_state.value}: "
            f"canonical 1h production artifact lineage is not yet established by protocol authority.",
        )
    if spec.archive_set_sha256 is not None and (
        not record.archive_set_sha256 or record.archive_set_sha256 != spec.archive_set_sha256
    ):
        raise H40GuardError(
            H40ReasonCode.SOURCE_HASH_MISMATCH,
            f"Source '{record.source_id}' archive set SHA mismatch: expected '{spec.archive_set_sha256}', got '{record.archive_set_sha256}'.",
        )
    if spec.reference_file_sha256 is not None and (
        not record.file_sha256 or record.file_sha256 != spec.reference_file_sha256
    ):
        raise H40GuardError(
            H40ReasonCode.SOURCE_HASH_MISMATCH,
            f"Source '{record.source_id}' file SHA mismatch with frozen reference: "
            f"expected '{spec.reference_file_sha256}', got '{record.file_sha256}'.",
        )


def assert_canonical_source_identity(
    record: H40SourceRecord,
    protocol_identity_hash: str,
) -> None:
    """Verify frozen source identity without granting production availability.

    A locally valid artifact may satisfy these identity checks while its accepted
    ``RuntimeAuthoritySnapshot`` state remains ``NOT_TESTABLE``.  Callers must
    resolve production availability from that snapshot separately.
    """
    _assert_canonical_source_identity(
        record,
        protocol_identity_hash,
        require_production_verified=False,
    )


def assert_canonical_source_record(
    record: H40SourceRecord,
    protocol_identity_hash: str,
) -> None:
    """Verify frozen source identity and accepted production-VERIFIED authority."""
    _assert_canonical_source_identity(
        record,
        protocol_identity_hash,
        require_production_verified=True,
    )



def validate_source_artifact(
    repo_root: Path | str,
    record: H40SourceRecord,
    expected_product: str | None = None,
    expected_cadence: str = "1h",
) -> H40SourceValidationReceipt:
    """Validates local artifact bytes and extracts timestamp series only without reading OHLC/outcomes."""
    # 1. Enforce protected surface authority before touching filesystem
    H40ProtectedSurfaceGuard.assert_path_allowed(
        record.locator,
        source_id=record.source_id,
        repo_root=repo_root,
    )

    file_path = Path(repo_root) / record.locator
    if not file_path.exists():
        return H40SourceValidationReceipt(
            source_id=record.source_id,
            locator=record.locator,
            file_sha256="",
            product=record.product or expected_product or "",
            cadence=expected_cadence,
            timestamp_field="",
            timestamp_count=0,
            first_timestamp_utc=None,
            last_timestamp_utc=None,
            duplicate_count=0,
            gap_count=0,
            gaps=(),
            timestamp_membership_hash="",
            status=H40SourceStatus.NOT_TESTABLE,
            reason_code=H40ReasonCode.SOURCE_MISSING,
            notes=f"Source artifact missing at {file_path}.",
        )

    # 2. Raw byte SHA-256
    file_bytes = file_path.read_bytes()
    actual_hash = hashlib.sha256(file_bytes).hexdigest()
    if record.file_sha256 is not None and actual_hash != record.file_sha256:
        return H40SourceValidationReceipt(
            source_id=record.source_id,
            locator=record.locator,
            file_sha256=actual_hash,
            product=record.product or expected_product or "",
            cadence=expected_cadence,
            timestamp_field="",
            timestamp_count=0,
            first_timestamp_utc=None,
            last_timestamp_utc=None,
            duplicate_count=0,
            gap_count=0,
            gaps=(),
            timestamp_membership_hash="",
            status=H40SourceStatus.NOT_TESTABLE,
            reason_code=H40ReasonCode.SOURCE_HASH_MISMATCH,
            notes=f"Byte SHA-256 mismatch: expected {record.file_sha256}, got {actual_hash}.",
        )

    # 3. Product check
    target_product = record.product or expected_product or ""
    if expected_product and record.product and record.product != expected_product:
        return H40SourceValidationReceipt(
            source_id=record.source_id,
            locator=record.locator,
            file_sha256=actual_hash,
            product=record.product,
            cadence=expected_cadence,
            timestamp_field="",
            timestamp_count=0,
            first_timestamp_utc=None,
            last_timestamp_utc=None,
            duplicate_count=0,
            gap_count=0,
            gaps=(),
            timestamp_membership_hash="",
            status=H40SourceStatus.NOT_TESTABLE,
            reason_code=H40ReasonCode.PRODUCT_MISMATCH,
            notes=f"Product mismatch: expected {expected_product}, got {record.product}.",
        )

    # 4. Extract timestamp column ONLY
    suffix = file_path.suffix.lower()
    timestamps_ms: list[int] = []
    ts_field_name = ""

    if suffix == ".parquet":
        pq = importlib.import_module("pyarrow.parquet")

        schema = pq.read_schema(file_path)
        # Check product column if exists in schema
        for p_col in ["product", "symbol"]:
            if p_col in schema.names and target_product:
                p_tab = pq.read_table(file_path, columns=[p_col])
                vals = p_tab[p_col].to_pylist()
                if vals and any(v != target_product for v in vals[:100]):
                    return H40SourceValidationReceipt(
                        source_id=record.source_id,
                        locator=record.locator,
                        file_sha256=actual_hash,
                        product=str(vals[0]),
                        cadence=expected_cadence,
                        timestamp_field="",
                        timestamp_count=0,
                        first_timestamp_utc=None,
                        last_timestamp_utc=None,
                        duplicate_count=0,
                        gap_count=0,
                        gaps=(),
                        timestamp_membership_hash="",
                        status=H40SourceStatus.NOT_TESTABLE,
                        reason_code=H40ReasonCode.PRODUCT_MISMATCH,
                        notes=f"Product in parquet {vals[0]} mismatches expected {target_product}.",
                    )

        # Identify timestamp column
        for candidate in ["open_time_ms", "timestamp_ms", "open_time", "timestamp"]:
            if candidate in schema.names:
                ts_field_name = candidate
                break
        if not ts_field_name:
            return H40SourceValidationReceipt(
                source_id=record.source_id,
                locator=record.locator,
                file_sha256=actual_hash,
                product=target_product,
                cadence=expected_cadence,
                timestamp_field="",
                timestamp_count=0,
                first_timestamp_utc=None,
                last_timestamp_utc=None,
                duplicate_count=0,
                gap_count=0,
                gaps=(),
                timestamp_membership_hash="",
                status=H40SourceStatus.NOT_TESTABLE,
                reason_code=H40ReasonCode.NOT_TESTABLE,
                notes="No recognized timestamp column found in parquet schema.",
            )

        tab = pq.read_table(file_path, columns=[ts_field_name])
        raw_vals = tab[ts_field_name].to_pylist()
        timestamps_ms = [int(v) for v in raw_vals]

    elif suffix == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            jdata = json.load(f)
        if isinstance(jdata, dict) and "timeframe" in jdata and jdata.get("timeframe") != expected_cadence:
            return H40SourceValidationReceipt(
                source_id=record.source_id,
                locator=record.locator,
                file_sha256=actual_hash,
                product=target_product,
                cadence=str(jdata.get("timeframe")),
                timestamp_field="timeframe",
                timestamp_count=0,
                first_timestamp_utc=None,
                last_timestamp_utc=None,
                duplicate_count=0,
                gap_count=0,
                gaps=(),
                timestamp_membership_hash="",
                status=H40SourceStatus.NOT_TESTABLE,
                reason_code=H40ReasonCode.INTERVAL_MISMATCH,
                notes=f"Manifest timeframe '{jdata.get('timeframe')}' does not match expected cadence '{expected_cadence}'.",
            )
        if isinstance(jdata, dict) and "timestamps" in jdata:
            ts_field_name = "timestamps"
            raw_ts = jdata["timestamps"]
            timestamps_ms = [_iso_to_ms(t) if isinstance(t, str) else int(t) for t in raw_ts]
        else:
            return H40SourceValidationReceipt(
                source_id=record.source_id,
                locator=record.locator,
                file_sha256=actual_hash,
                product=target_product,
                cadence=expected_cadence,
                timestamp_field="",
                timestamp_count=0,
                first_timestamp_utc=None,
                last_timestamp_utc=None,
                duplicate_count=0,
                gap_count=0,
                gaps=(),
                timestamp_membership_hash="",
                status=H40SourceStatus.NOT_TESTABLE,
                reason_code=H40ReasonCode.NOT_TESTABLE,
                notes="JSON artifact does not contain hourly timestamps array.",
            )
    else:
        return H40SourceValidationReceipt(
            source_id=record.source_id,
            locator=record.locator,
            file_sha256=actual_hash,
            product=target_product,
            cadence=expected_cadence,
            timestamp_field="",
            timestamp_count=0,
            first_timestamp_utc=None,
            last_timestamp_utc=None,
            duplicate_count=0,
            gap_count=0,
            gaps=(),
            timestamp_membership_hash="",
            status=H40SourceStatus.NOT_TESTABLE,
            reason_code=H40ReasonCode.NOT_TESTABLE,
            notes=f"Unsupported artifact suffix '{suffix}'.",
        )

    # Analyze duplicates and gaps
    total_count = len(timestamps_ms)
    unique_ms = sorted(set(timestamps_ms))
    duplicate_count = total_count - len(unique_ms)

    # Cadence check
    expected_step_ms = 3600 * 1000 if expected_cadence == "1h" else 0
    gaps: list[dict[str, Any]] = []
    cadence_mismatch = False

    if expected_step_ms > 0 and len(unique_ms) > 1:
        for prev, curr in pairwise(unique_ms):
            delta = curr - prev
            if delta < expected_step_ms:
                cadence_mismatch = True
                break
            elif delta > expected_step_ms:
                if delta % expected_step_ms != 0:
                    cadence_mismatch = True
                    break
                missing_hours = (delta // expected_step_ms) - 1
                gaps.append({
                    "start_utc": _ms_to_iso(prev + expected_step_ms),
                    "end_utc": _ms_to_iso(curr),
                    "missing_hours": missing_hours,
                })

    if cadence_mismatch:
        return H40SourceValidationReceipt(
            source_id=record.source_id,
            locator=record.locator,
            file_sha256=actual_hash,
            product=target_product,
            cadence=record.cadence,
            timestamp_field=ts_field_name,
            timestamp_count=total_count,
            first_timestamp_utc=_ms_to_iso(unique_ms[0]) if unique_ms else None,
            last_timestamp_utc=_ms_to_iso(unique_ms[-1]) if unique_ms else None,
            duplicate_count=duplicate_count,
            gap_count=len(gaps),
            gaps=tuple(gaps),
            timestamp_membership_hash="",
            status=H40SourceStatus.NOT_TESTABLE,
            reason_code=H40ReasonCode.INTERVAL_MISMATCH,
            notes=f"Timestamps cadence mismatch for expected cadence '{expected_cadence}'.",
        )

    if duplicate_count > 0:
        return H40SourceValidationReceipt(
            source_id=record.source_id,
            locator=record.locator,
            file_sha256=actual_hash,
            product=target_product,
            cadence=expected_cadence,
            timestamp_field=ts_field_name,
            timestamp_count=total_count,
            first_timestamp_utc=_ms_to_iso(unique_ms[0]) if unique_ms else None,
            last_timestamp_utc=_ms_to_iso(unique_ms[-1]) if unique_ms else None,
            duplicate_count=duplicate_count,
            gap_count=len(gaps),
            gaps=tuple(gaps),
            timestamp_membership_hash="",
            status=H40SourceStatus.NOT_TESTABLE,
            reason_code=H40ReasonCode.DUPLICATE_TIMESTAMP,
            notes=f"Detected {duplicate_count} duplicate timestamps in source.",
        )

    # Compute timestamp membership hash
    iso_list = [_ms_to_iso(t) for t in unique_ms]
    ts_membership_hash = hashlib.sha256(",".join(iso_list).encode("utf-8")).hexdigest()

    return H40SourceValidationReceipt(
        source_id=record.source_id,
        locator=record.locator,
        file_sha256=actual_hash,
        product=target_product,
        cadence=expected_cadence,
        timestamp_field=ts_field_name,
        timestamp_count=len(iso_list),
        first_timestamp_utc=iso_list[0] if iso_list else None,
        last_timestamp_utc=iso_list[-1] if iso_list else None,
        duplicate_count=0,
        gap_count=len(gaps),
        gaps=tuple(gaps),
        timestamp_membership_hash=ts_membership_hash,
        status=H40SourceStatus.VERIFIED,
        archive_set_sha256=record.archive_set_sha256,
        reason_code=None,
        notes="Validated local artifact bytes and timestamp series.",
    )


def materialize_verified_manifest(
    repo_root: Path | str,
    protocol_identity_hash: str,
    reference_manifest: H40SourceManifest | None = None,
) -> H40SourceManifest:
    """Materializes a source manifest with explicit validation receipts from local artifacts."""
    ref = reference_manifest or H40SourceManifest.build_preregistered_reference(protocol_identity_hash)
    materialized_sources: list[H40SourceRecord] = []
    for s in ref.sources:
        if s.status in {H40SourceStatus.FORBIDDEN, H40SourceStatus.DIAGNOSTIC_ONLY, H40SourceStatus.NOT_TESTABLE}:
            materialized_sources.append(s)
            continue
        receipt = validate_source_artifact(
            repo_root=repo_root,
            record=s,
            expected_product=s.product,
            expected_cadence=s.cadence,
        )
        if receipt.status == H40SourceStatus.VERIFIED:
            materialized_sources.append(
                H40SourceRecord(
                    source_id=s.source_id,
                    status=H40SourceStatus.VERIFIED,
                    locator=s.locator,
                    cadence=s.cadence,
                    product=s.product,
                    row_count=receipt.timestamp_count,
                    start_utc=receipt.first_timestamp_utc,
                    end_utc=receipt.last_timestamp_utc,
                    file_sha256=receipt.file_sha256,
                    archive_set_sha256=s.archive_set_sha256,
                    gap_count=receipt.gap_count,
                    gaps=receipt.gaps,
                    reason_code=None,
                    notes=receipt.notes,
                    receipt=receipt,
                )
            )
        else:
            materialized_sources.append(
                H40SourceRecord(
                    source_id=s.source_id,
                    status=H40SourceStatus.NOT_TESTABLE,
                    locator=s.locator,
                    cadence=s.cadence,
                    product=s.product,
                    row_count=receipt.timestamp_count,
                    start_utc=receipt.first_timestamp_utc,
                    end_utc=receipt.last_timestamp_utc,
                    file_sha256=receipt.file_sha256 or s.file_sha256,
                    archive_set_sha256=s.archive_set_sha256,
                    gap_count=receipt.gap_count,
                    gaps=receipt.gaps,
                    reason_code=receipt.reason_code or H40ReasonCode.NOT_TESTABLE,
                    notes=receipt.notes,
                    receipt=receipt,
                )
            )
    return H40SourceManifest(
        protocol_identity_hash=protocol_identity_hash,
        sources=tuple(materialized_sources),
    )


def extract_verified_source_timestamps(
    repo_root: Path | str,
    record: H40SourceRecord,
    expected_product: str | None = None,
    expected_cadence: str = "1h",
) -> list[str]:
    """Cold-validates source artifact and extracts verified ISO-8601 timestamps list.

    Enforces that:
    1. Protected surface guard checks pass before filesystem access.
    2. Local artifact exists and passes validation into a VERIFIED receipt.
    3. If the source record already has a receipt, the cold validation receipt matches
       the record's receipt (file SHA-256, timestamp count, and membership SHA-256).
    4. Exact timestamps extracted from the artifact produce the exact membership SHA-256.
    """
    cold_receipt = validate_source_artifact(
        repo_root=repo_root,
        record=record,
        expected_product=expected_product,
        expected_cadence=expected_cadence,
    )
    if cold_receipt.status != H40SourceStatus.VERIFIED:
        raise H40GuardError(
            cold_receipt.reason_code or H40ReasonCode.SOURCE_UNVERIFIED,
            f"Source artifact '{record.locator}' failed cold verification: {cold_receipt.notes}",
        )

    # If record has an attached receipt, ensure cold receipt matches
    if record.receipt is not None:
        if record.receipt.status != H40SourceStatus.VERIFIED:
            raise H40GuardError(
                record.receipt.reason_code or H40ReasonCode.SOURCE_UNVERIFIED,
                f"Source record '{record.source_id}' has non-VERIFIED receipt.",
            )
        if record.receipt.file_sha256 != cold_receipt.file_sha256:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                f"Source record '{record.source_id}' receipt file hash {record.receipt.file_sha256} "
                f"mismatches cold artifact hash {cold_receipt.file_sha256}.",
            )
        if record.receipt.timestamp_membership_hash != cold_receipt.timestamp_membership_hash:
            raise H40GuardError(
                H40ReasonCode.SOURCE_HASH_MISMATCH,
                f"Source record '{record.source_id}' timestamp membership hash mismatches cold artifact.",
            )
        if record.receipt.timestamp_count != cold_receipt.timestamp_count:
            raise H40GuardError(
                H40ReasonCode.INTERVAL_MISMATCH,
                f"Source record '{record.source_id}' timestamp count mismatches cold artifact.",
            )

    # Read timestamps from artifact file
    file_path = Path(repo_root) / record.locator
    suffix = file_path.suffix.lower()
    if suffix == ".parquet":
        pq = importlib.import_module("pyarrow.parquet")
        tab = pq.read_table(file_path, columns=[cold_receipt.timestamp_field])
        raw_vals = tab[cold_receipt.timestamp_field].to_pylist()
        unique_ms = sorted({int(v) for v in raw_vals})
        iso_list = [_ms_to_iso(t) for t in unique_ms]
    elif suffix == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            jdata = json.load(f)
        raw_ts = jdata.get("timestamps", [])
        unique_ms = sorted({_iso_to_ms(t) if isinstance(t, str) else int(t) for t in raw_ts})
        iso_list = [_ms_to_iso(t) for t in unique_ms]
    else:
        raise H40GuardError(H40ReasonCode.NOT_TESTABLE, f"Unsupported artifact suffix '{suffix}'.")

    # Verify membership hash matches cold receipt
    actual_hash = hashlib.sha256(",".join(iso_list).encode("utf-8")).hexdigest()
    if actual_hash != cold_receipt.timestamp_membership_hash:
        raise H40GuardError(
            H40ReasonCode.SOURCE_HASH_MISMATCH,
            f"Extracted timestamp membership hash {actual_hash} mismatches receipt {cold_receipt.timestamp_membership_hash}.",
        )
    return iso_list
