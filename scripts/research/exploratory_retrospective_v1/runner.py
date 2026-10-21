"""Disabled execution boundary and opt-in fixed-artificial-payload checks only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import MODE, SCHEMA, GateError, require
from .contract import LABELS, Trust, canonical, digest, validate
from .safeio import fingerprint, publish_new, safe_path


def execute(*args: Any, **kwargs: Any) -> None:
    """No metadata, environment variable or caller switch enables research."""
    raise GateError("REAL_EXECUTION_DISABLED")


@dataclass(frozen=True)
class CheckedFixture:
    registration: bytes
    scope: bytes
    manifest: bytes
    trust: Trust
    signatures: tuple[tuple[int, ...], ...]


def check_fixture(registration: dict[str, Any], scope: dict[str, Any],
                  manifest: dict[str, Any], trust: Trust, *, enabled: bool = False) -> CheckedFixture:
    require(enabled is True, "MODE_DISABLED_BY_DEFAULT")
    # Copy once so subsequent caller mutations cannot alter the accepted snapshot.
    r, s, m = (canonical(v) for v in (registration, scope, manifest))
    registration, scope, manifest = (json.loads(v) for v in (r, s, m))
    validate(registration, scope, manifest, trust)
    signatures = tuple(fingerprint(safe_path(row["path"]), row["size"], row["sha256"],
                                   row["file_signature"])
                       for row in manifest["sources"])
    return CheckedFixture(r, s, m, trust, signatures)


def publish_fixture(checked: CheckedFixture) -> dict[str, Any]:
    registration, scope, manifest = (json.loads(v) for v in
                                     (checked.registration, checked.scope, checked.manifest))
    validate(registration, scope, manifest, checked.trust)
    current = tuple(fingerprint(safe_path(row["path"]), row["size"], row["sha256"],
                                row["file_signature"])
                    for row in manifest["sources"])
    require(current == checked.signatures, "SOURCE_MUTATED_AFTER_ACCEPTANCE")
    result = {
        "schema": SCHEMA, "mode": MODE, "labels": dict(LABELS),
        "registration_sha256": digest(registration), "scope_sha256": digest(scope),
        "manifest_sha256": digest(manifest), "synthetic_files_checked": len(current),
        "outcomes_computed": False, "real_source_authority": False,
    }
    publish_new(Path(scope["output_path"]), canonical(result))
    return result
