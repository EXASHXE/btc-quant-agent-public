"""External Target Seal Contract and Schema Validation for RC2 R3 Repair R2.

Enforces:
- External Controller-created target seal artifact schema.
- Exact SHA256 digest matching before any source/cache access.
- Strict schema validation: rejects unexpected fields, malformed lists, and role overlaps.
- Fails closed before cache/network if seal missing, mismatched, or malformed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

TARGET_SEAL_SCHEMA_VERSION = "RC2_TARGET_SEAL_V1"
ALLOWED_SEAL_KEYS = frozenset(
    {
        "schema_version",
        "task_id",
        "created_at_utc",
        "target_symbols",
        "context_only_references",
    }
)


class TargetSealError(Exception):
    """Base error for target seal issues."""


class TargetSealNotFoundError(TargetSealError, FileNotFoundError):
    """Raised when target seal file does not exist."""


class TargetSealHashMismatchError(TargetSealError, ValueError):
    """Raised when target seal SHA256 does not match Controller authorization."""


class TargetSealSchemaError(TargetSealError, ValueError):
    """Raised when target seal schema is invalid or contains unexpected fields."""


class TargetSealRoleOverlapError(TargetSealError, ValueError):
    """Raised when sealed targets overlap with context-only references."""


def validate_target_seal(
    seal_path: Path,
    expected_sha256: str,
    references: Sequence[str],
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Validate external target seal artifact against frozen contract schema and digest.

    Returns:
        tuple[targets, raw_dict]
    Fails closed on any defect.
    """
    if not re.fullmatch(r"^[0-9a-f]{64}$", expected_sha256):
        raise TargetSealHashMismatchError(
            f"Invalid target seal SHA256 syntax: '{expected_sha256}' (must be 64-char hex)"
        )

    if not seal_path.exists() or not seal_path.is_file():
        raise TargetSealNotFoundError(f"Target seal file missing or not a file: {seal_path}")

    raw_bytes = seal_path.read_bytes()
    computed_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    if computed_sha256 != expected_sha256:
        raise TargetSealHashMismatchError(
            f"Target seal SHA256 mismatch: computed='{computed_sha256}' authorized='{expected_sha256}'"
        )

    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:
        raise TargetSealSchemaError(f"Target seal JSON malformed: {exc}") from exc

    if not isinstance(data, dict):
        raise TargetSealSchemaError("Target seal must be a top-level JSON object")

    # Strict contract schema: reject any unexpected keys
    extra_keys = set(data.keys()) - ALLOWED_SEAL_KEYS
    if extra_keys:
        raise TargetSealSchemaError(
            f"Target seal contains unexpected keys: {sorted(extra_keys)}; strictly violates frozen contract schema"
        )

    if data.get("schema_version") != TARGET_SEAL_SCHEMA_VERSION:
        raise TargetSealSchemaError(
            f"Target seal schema_version mismatch: observed='{data.get('schema_version')}' expected='{TARGET_SEAL_SCHEMA_VERSION}'"
        )

    task_id = data.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise TargetSealSchemaError("Target seal task_id must be a non-empty string")

    created_at = data.get("created_at_utc")
    if not isinstance(created_at, str) or not created_at.strip():
        raise TargetSealSchemaError("Target seal created_at_utc must be a non-empty ISO string")
    try:
        datetime.fromisoformat(created_at)
    except Exception as exc:
        raise TargetSealSchemaError(f"Target seal created_at_utc is not a valid ISO timestamp: {exc}") from exc

    target_symbols = data.get("target_symbols")
    if not isinstance(target_symbols, list) or not target_symbols:
        raise TargetSealSchemaError("Target seal target_symbols must be a non-empty list of strings")

    cleaned_targets: list[str] = []
    seen: set[str] = set()
    for item in target_symbols:
        if not isinstance(item, str) or not item.strip():
            raise TargetSealSchemaError("Target seal contains invalid or empty symbol entry")
        sym = item.strip().upper()
        if not re.fullmatch(r"^[A-Z0-9]+USDT$", sym):
            raise TargetSealSchemaError(
                f"Target symbol '{sym}' does not match expected format ^[A-Z0-9]+USDT$"
            )
        if sym in seen:
            raise TargetSealSchemaError(f"Target seal contains duplicate symbol: '{sym}'")
        seen.add(sym)
        cleaned_targets.append(sym)

    # Disjointness check with references
    ref_set = set(references)
    overlap = seen & ref_set
    if overlap:
        raise TargetSealRoleOverlapError(
            f"Target seal targets overlap with context-only references: {sorted(overlap)}"
        )

    if "context_only_references" in data:
        context_refs = data["context_only_references"]
        if not isinstance(context_refs, list) or list(context_refs) != list(references):
            raise TargetSealSchemaError(
                "Target seal context_only_references does not match frozen references contract"
            )

    return tuple(cleaned_targets), data
