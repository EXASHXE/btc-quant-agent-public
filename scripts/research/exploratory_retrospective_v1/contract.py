"""Strict metadata contract and separately pinned synthetic-only authority.

Hashes establish integrity against a trusted catalog, not human authentication.
There is deliberately no real-source policy, signer, evaluator or adapter here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from . import MODE, SCHEMA, require
from .safeio import absent_output, safe_path

ARTIFICIAL_BYTES = b'{"kind":"ARTIFICIAL_COORDINATE_ONLY","value":7}\n'
ARTIFICIAL_HASH = hashlib.sha256(ARTIFICIAL_BYTES).hexdigest()
IDENTITY = {
    "source": "ARTIFICIAL_GENERATOR_V1", "venue": "SYNTHETIC", "product": "TEST_COORDINATE",
    "symbol": "ARTIFICIAL", "fields": ["value"], "rights": "GENERATED_TEST_FIXTURE_ONLY",
}
LABELS = {
    "classification": "EXPLORATORY",
    "holdout_relationship": "UNKNOWN_OR_POSSIBLE_OVERLAP",
    "selection_status": "SELECTION_CONTAMINATED_OR_UNKNOWN",
    "pit_status": "PIT_UNKNOWN", "cost_status": "COST_INCOMPLETE",
    "source_status": "SOURCE_NOT_ADMITTED", "authority": "SYNTHETIC_STRUCTURAL_CHECK_ONLY",
    "promotion": "BLOCKED", "complete_net_pnl": False,
    "real_execution_enabled": False,
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False,
                       ensure_ascii=True) + "\n").encode("ascii")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def keys(value: Any, expected: str) -> None:
    require(type(value) is dict and set(value) == set(expected.split()), "CONTRACT_FIELDS")


def text(value: Any) -> None:
    require(isinstance(value, str) and bool(value.strip()), "TEXT_REQUIRED")


def sha(value: Any) -> None:
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            "HASH_REQUIRED")


def utc(value: Any) -> datetime:
    require(isinstance(value, str)
            and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value) is not None,
            "EXACT_UTC_REQUIRED")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Trust:
    """Out-of-band immutable pins. Synthetic facts confer no owner/source authority.

    Duplicate experiment IDs, including alternative versions, are rejected.
    Never construct this catalog from untrusted registration/scope claims.
    """

    registrations: tuple[tuple[str, str, str], ...]  # experiment ID, version, digest
    acceptances: tuple[tuple[str, str], ...]  # scope digest, accepted_at UTC
    input_roots: tuple[str, ...]
    output_root: str


def enforce_labels(labels: dict[str, Any]) -> None:
    require(canonical(labels) == canonical(LABELS), "UNSUPPORTED_CLAIM_OR_PROMOTION")


def validate(registration: dict[str, Any], scope: dict[str, Any], manifest: dict[str, Any],
             trust: Trust) -> None:
    """Validate ALL metadata and paths before any source descriptor is opened."""
    keys(registration, "schema mode experiment_id version hypothesis falsification registered_at "
         "windows features parameters entry_rule exit_rule settlement_rule outcome_horizon_seconds "
         "cost_assumptions manifest_sha256 output_path labels")
    require(registration["schema"] == SCHEMA and registration["mode"] == MODE, "SCHEMA_MODE")
    for name in ("experiment_id", "version", "hypothesis", "falsification", "entry_rule",
                 "exit_rule", "settlement_rule"):
        text(registration[name])
    ids = [row[0] for row in trust.registrations]
    require(len(ids) == len(set(ids)), "DUPLICATE_REGISTRATION")
    require((registration["experiment_id"], registration["version"], digest(registration))
            in trust.registrations, "MISSING_OR_MUTATED_REGISTRATION")
    registered = utc(registration["registered_at"])
    keys(scope, "schema mode registration_sha256 manifest_sha256 input_paths output_path purpose")
    require(scope["schema"] == SCHEMA and scope["mode"] == MODE, "SCHEMA_MODE")
    require(scope["purpose"] == "STRUCTURAL_SYNTHETIC_ONLY", "REAL_EXECUTION_DISABLED")
    for name in ("registration_sha256", "manifest_sha256"):
        sha(scope[name])
    require(scope["registration_sha256"] == digest(registration), "REGISTRATION_HASH_MISMATCH")
    matches = [t for h, t in trust.acceptances if h == digest(scope)]
    require(len(matches) == 1, "SEPARATE_ACCEPTANCE_REQUIRED")
    require(registered < utc(matches[0]) <= datetime.now(UTC).replace(tzinfo=None),
            "REGISTRATION_MUST_PREEXIST_ACCEPTANCE")
    sha(registration["manifest_sha256"])
    require(scope["manifest_sha256"] == registration["manifest_sha256"] == digest(manifest),
            "MANIFEST_HASH_MISMATCH")
    enforce_labels(registration["labels"])
    keys(registration["windows"], "source feature entry exit settlement")
    windows = {}
    for role, bounds in registration["windows"].items():
        require(type(bounds) is list and len(bounds) == 2, "BOUNDED_UTC_SCOPE_REQUIRED")
        start, end = map(utc, bounds)
        require(start < end, "EMPTY_TIME_SCOPE")
        windows[role] = (start, end)
    lo, hi = windows["source"]
    require(all(lo <= start < end <= hi for start, end in windows.values()), "TIME_SCOPE")
    horizon = registration["outcome_horizon_seconds"]
    require(type(horizon) is int and 0 < horizon <= 366 * 86400, "OUTCOME_HORIZON")
    require(tuple(t + timedelta(seconds=horizon) for t in windows["entry"]) == windows["exit"],
            "ENTRY_EXIT_HORIZON")
    require(windows["feature"][1] <= windows["entry"][0]
            and windows["entry"][0] <= windows["settlement"][0]
            and windows["settlement"][1] <= windows["exit"][1], "ROLE_TIME_SCOPE")
    require(type(registration["features"]) is dict and bool(registration["features"]),
            "FEATURE_DEFINITIONS_REQUIRED")
    for name, definition in registration["features"].items():
        text(name)
        text(definition)
    require(type(registration["parameters"]) is dict and bool(registration["parameters"]),
            "PARAMETERS_REQUIRED")
    # Missing costs remain explicit nulls. No net economics are computed by this mode.
    keys(registration["cost_assumptions"], "fees slippage funding borrow fill_policy")
    for name, assumption in registration["cost_assumptions"].items():
        if name == "fill_policy":
            text(assumption)
        else:
            require(assumption is None or isinstance(assumption, str), "COST_ASSUMPTIONS")
            if assumption is not None:
                text(assumption)
    keys(manifest, "schema sources")
    require(manifest["schema"] == SCHEMA, "SCHEMA_MODE")
    sources = manifest["sources"]
    require(type(sources) is list and 0 < len(sources) <= 8, "EXACT_MANIFEST_REQUIRED")
    roots = tuple(safe_path(r) for r in trust.input_roots)
    require(bool(roots) and len(roots) == len(set(roots)), "CLASSIFIED_ROOT_REQUIRED")
    require(all(r.is_relative_to(safe_path("/tmp")) and r != safe_path("/tmp") for r in roots),
            "ONLY_TEMPORARY_SYNTHETIC_ROOTS_ALLOWED")
    output_root = safe_path(trust.output_root)
    require(all(not output_root.is_relative_to(r) and not r.is_relative_to(output_root)
                for r in roots), "INPUT_OUTPUT_OVERLAP")
    paths = []
    for source in sources:
        keys(source, "path root classification identity sha256 size file_signature")
        path, root = safe_path(source["path"]), safe_path(source["root"])
        require(root in roots and path.is_relative_to(root) and path != root,
                "UNCLASSIFIED_OR_UNAUTHORIZED_ROOT")
        require(source["classification"] == "SYNTHETIC_RAW", "SOURCE_CLASSIFICATION")
        require(source["identity"] == IDENTITY, "UNAPPROVED_SOURCE_IDENTITY")
        sha(source["sha256"])
        require(source["sha256"] == ARTIFICIAL_HASH
                and type(source["size"]) is int and source["size"] == len(ARTIFICIAL_BYTES),
                "ONLY_FIXED_ARTIFICIAL_PAYLOAD_ALLOWED")
        sig = source["file_signature"]
        require(type(sig) is list and len(sig) == 5
                and all(type(v) is int and v >= 0 for v in sig), "FILE_SIGNATURE_REQUIRED")
        paths.append(str(path))
    require(len(paths) == len(set(paths)), "DUPLICATE_INPUT")
    require(type(scope["input_paths"]) is list and scope["input_paths"] == paths,
            "EXACT_ALLOWLIST_REQUIRED")
    output = safe_path(scope["output_path"])
    require(str(output) == registration["output_path"] and output.parent == output_root,
            "EXACT_OUTPUT_REQUIRED")
    require(all(not output.is_relative_to(r) and not r.is_relative_to(output) for r in roots),
            "INPUT_OUTPUT_OVERLAP")
    absent_output(output)
