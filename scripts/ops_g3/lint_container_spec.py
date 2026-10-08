#!/usr/bin/env python3
"""Static container linter for v0.6 B-line G3 Operational Readiness.

Enforces:
1. Dockerfile base image: Python 3.12 slim
2. Non-root user execution: USER quant
3. Canonical startup command: single-worker uvicorn (--workers 1)
4. docker-compose.yml: single-worker, no auto-scaling replicas
5. docker-compose.yml: strict safety authority variables
   (REAL_FUNDS_WRITE_AUTHORITY: NONE, LIVE_APPROVAL_ONLY: NOT_AUTHORIZED, AUTONOMOUS_LIVE: FORBIDDEN)
6. Probes host Docker daemon availability without failing closed on absence.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def lint_dockerfile(dockerfile_path: Path) -> list[str]:
    errors = []
    if not dockerfile_path.exists():
        return [f"Dockerfile missing at {dockerfile_path}"]
    content = dockerfile_path.read_text(encoding="utf-8")
    if "python:3.12" not in content:
        errors.append("Dockerfile must use python:3.12 base image")
    if "USER quant" not in content:
        errors.append("Dockerfile must specify non-root USER quant")
    if "--workers" not in content or '"1"' not in content:
        errors.append("Dockerfile CMD must specify exactly 1 uvicorn worker (--workers 1)")
    return errors


def lint_docker_compose(compose_path: Path) -> list[str]:
    errors = []
    if not compose_path.exists():
        return [f"docker-compose.yml missing at {compose_path}"]
    content = compose_path.read_text(encoding="utf-8")
    if "--workers" not in content or '"1"' not in content:
        errors.append("docker-compose command must specify --workers 1")
    if "REAL_FUNDS_WRITE_AUTHORITY: NONE" not in content:
        errors.append("docker-compose must set REAL_FUNDS_WRITE_AUTHORITY: NONE")
    if "LIVE_APPROVAL_ONLY: NOT_AUTHORIZED" not in content:
        errors.append("docker-compose must set LIVE_APPROVAL_ONLY: NOT_AUTHORIZED")
    if "AUTONOMOUS_LIVE: FORBIDDEN" not in content:
        errors.append("docker-compose must set AUTONOMOUS_LIVE: FORBIDDEN")
    if "deploy:" in content and "replicas:" in content:
        errors.append("docker-compose must not configure multi-worker replica auto-scaling")
    return errors


def check_host_docker() -> tuple[str, str]:
    which_res = subprocess.run(["which", "docker"], capture_output=True, text=True, check=False)
    if which_res.returncode != 0:
        return "CONTAINER_NOT_VERIFIED", "docker executable not found on host"
    info_res = subprocess.run(["docker", "info"], capture_output=True, text=True, check=False)
    if info_res.returncode != 0:
        return "CONTAINER_NOT_VERIFIED", "docker daemon not running or socket inaccessible"
    return "CONTAINER_VERIFIED", "docker daemon active and accessible"


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent
    dockerfile_errors = lint_dockerfile(repo_root / "Dockerfile")
    compose_errors = lint_docker_compose(repo_root / "docker-compose.yml")
    container_status, container_reason = check_host_docker()

    report = {
        "schema_version": "G3_CONTAINER_SPEC_LINT_V1",
        "dockerfile_valid": len(dockerfile_errors) == 0,
        "dockerfile_errors": dockerfile_errors,
        "docker_compose_valid": len(compose_errors) == 0,
        "docker_compose_errors": compose_errors,
        "container_status": container_status,
        "container_reason": container_reason,
    }
    print(json.dumps(report, indent=2))
    return 0 if (len(dockerfile_errors) == 0 and len(compose_errors) == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
