"""Artificial fixtures only; the test catalog is explicitly not owner acceptance."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

from . import MODE, SCHEMA, require
from .contract import ARTIFICIAL_BYTES, ARTIFICIAL_HASH, IDENTITY, LABELS, Trust, digest
from .runner import check_fixture, publish_fixture
from .safeio import directory_fd, publish_new, safe_path, signature


def artificial_fixture(base: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Trust]:
    """Create fresh artificial bytes and synthetic-only pins, without any source discovery."""
    base = safe_path(str(base))
    require(base.is_relative_to(Path("/tmp")) and base != Path("/tmp"), "TEMP_FIXTURE_REQUIRED")
    inputs, outputs = base / "inputs", base / "outputs"
    with directory_fd(base) as parent:
        os.mkdir("inputs", 0o700, dir_fd=parent)
        os.mkdir("outputs", 0o700, dir_fd=parent)
    source = inputs / "coordinate.json"
    publish_new(source, ARTIFICIAL_BYTES)
    manifest = {"schema": SCHEMA, "sources": [{
        "path": str(source), "root": str(inputs), "classification": "SYNTHETIC_RAW",
        "identity": deepcopy(IDENTITY), "sha256": ARTIFICIAL_HASH, "size": len(ARTIFICIAL_BYTES),
        "file_signature": list(signature(source.stat())),
    }]}
    registration = {
        "schema": SCHEMA, "mode": MODE, "experiment_id": str(uuid4()), "version": "1",
        "hypothesis": "The artificial coordinate equals seven.",
        "falsification": "Any coordinate other than seven falsifies this fixture hypothesis.",
        "registered_at": "2000-01-01T00:00:00Z",
        "windows": {
            "source": ["2000-01-01T00:00:00Z", "2000-01-03T00:00:00Z"],
            "feature": ["2000-01-01T00:00:00Z", "2000-01-01T01:00:00Z"],
            "entry": ["2000-01-01T01:00:00Z", "2000-01-01T02:00:00Z"],
            "exit": ["2000-01-01T02:00:00Z", "2000-01-01T03:00:00Z"],
            "settlement": ["2000-01-01T01:00:00Z", "2000-01-01T03:00:00Z"],
        },
        "features": {"coordinate": "Fixed artificial integer; no market interpretation."},
        "parameters": {"expected": 7}, "entry_rule": "No orders; structural timestamp only.",
        "exit_rule": "No orders; one-hour structural offset only.",
        "settlement_rule": "No funding; structural half-open time window only.",
        "outcome_horizon_seconds": 3600,
        "cost_assumptions": {"fees": None, "slippage": None, "funding": None, "borrow": None,
                             "fill_policy": "NO_FILLS_SYNTHETIC_STRUCTURE_ONLY"},
        "manifest_sha256": digest(manifest), "output_path": str(outputs / "receipt.json"),
        "labels": dict(LABELS),
    }
    scope = {
        "schema": SCHEMA, "mode": MODE, "registration_sha256": digest(registration),
        "manifest_sha256": digest(manifest), "input_paths": [str(source)],
        "output_path": registration["output_path"], "purpose": "STRUCTURAL_SYNTHETIC_ONLY",
    }
    trust = Trust(((registration["experiment_id"], "1", digest(registration)),),
                  ((digest(scope), "2000-01-01T00:01:00Z"),), (str(inputs),), str(outputs))
    return registration, scope, manifest, trust


def self_check() -> dict[str, Any]:
    """The CLI accepts no data paths, trust catalogs, registrations or output locations."""
    with TemporaryDirectory(prefix="erv1-", dir="/tmp") as directory:
        r, s, m, t = artificial_fixture(Path(directory))
        return publish_fixture(check_fixture(r, s, m, t, enabled=True))
