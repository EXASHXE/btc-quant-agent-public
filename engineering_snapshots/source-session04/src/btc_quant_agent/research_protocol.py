from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import AppConfig

DEV_START_MS = int(datetime(2021, 1, 1, tzinfo=UTC).timestamp() * 1000)
DEV_END_MS = int(datetime(2026, 2, 1, tzinfo=UTC).timestamp() * 1000)
HOLDOUT_START_MS = DEV_END_MS
HOLDOUT_END_MS = int(datetime(2026, 8, 1, tzinfo=UTC).timestamp() * 1000)
CANDIDATE_TAG = "v0.3.0-candidate-pre-holdout"


def validate_research_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "timezone": "UTC",
        "start_ms": DEV_START_MS,
        "end_ms_exclusive": HOLDOUT_END_MS,
        "missing_count": 0,
        "duplicate_count": 0,
        "out_of_order_count": 0,
        "invalid_ohlc_count": 0,
        "negative_volume_count": 0,
        "synthetic_rows": 0,
    }
    failures = [
        f"{key}={manifest.get(key)!r}"
        for key, expected in required.items()
        if manifest.get(key) != expected
    ]
    if failures:
        raise ValueError("research manifest invariant failure: " + ", ".join(failures))
    funding = manifest.get("funding", {})
    if funding.get("missing_mark_prices") != 0 or funding.get("duplicate_count") != 0:
        raise ValueError("research funding manifest is incomplete or duplicated")
    if not manifest.get("checksum_sha256"):
        raise ValueError("research manifest lacks a dataset checksum")


def freeze_certificate_payload(
    config: AppConfig,
    dataset_checksum: str,
    commit_sha: str,
) -> dict[str, Any]:
    return {
        "candidate_tag": CANDIDATE_TAG,
        "candidate_commit_sha": commit_sha,
        "candidate_config_hash": config.config_hash,
        "candidate_config": asdict(config),
        "dataset_checksum_sha256": dataset_checksum,
        "holdout_start_ms": HOLDOUT_START_MS,
        "holdout_end_ms_exclusive": HOLDOUT_END_MS,
        "frozen_at_ms": int(time.time() * 1000),
        "holdout_consumed_at_ms": None,
    }


def write_freeze_certificate(
    path: str | Path,
    config: AppConfig,
    dataset_checksum: str,
    commit_sha: str,
) -> dict[str, Any]:
    payload = freeze_certificate_payload(config, dataset_checksum, commit_sha)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def _tag_commit(repo: str | Path, tag: str) -> str:
    result = subprocess.run(
        ["git", "rev-list", "-n", "1", tag],
        cwd=repo,
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def consume_holdout_gate(
    certificate_path: str | Path,
    *,
    config: AppConfig,
    dataset_manifest_path: str | Path,
    repo: str | Path = ".",
) -> dict[str, Any]:
    """Authorize exactly one holdout read after config, commit, tag, and data are frozen."""
    path = Path(certificate_path)
    if not path.exists():
        raise PermissionError("holdout is sealed until a candidate freeze certificate exists")
    certificate: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads(Path(dataset_manifest_path).read_text(encoding="utf-8"))
    validate_research_manifest(manifest)
    checks = {
        "candidate_tag": certificate.get("candidate_tag") == CANDIDATE_TAG,
        "config_hash": certificate.get("candidate_config_hash") == config.config_hash,
        "dataset_checksum": certificate.get("dataset_checksum_sha256")
        == manifest.get("checksum_sha256"),
        "holdout_start": certificate.get("holdout_start_ms") == HOLDOUT_START_MS,
        "holdout_end": certificate.get("holdout_end_ms_exclusive") == HOLDOUT_END_MS,
        "tag_commit": _tag_commit(repo, CANDIDATE_TAG)
        == certificate.get("candidate_commit_sha"),
        "not_consumed": certificate.get("holdout_consumed_at_ms") is None,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise PermissionError("holdout gate rejected: " + ", ".join(failed))
    certificate["holdout_consumed_at_ms"] = int(time.time() * 1000)
    path.write_text(
        json.dumps(certificate, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return certificate
