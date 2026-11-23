"""Reproducible offline B3 QA runner, inherited B2 verification, build/audit driver, and baseline preservation verifier."""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import platform
import shlex
import shutil
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

B3_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = B3_ROOT.parents[1]
DOCS_ROOT = PROJECT_ROOT.parent / "quant-docs-engineering"
EVIDENCE = B3_ROOT / "evidence"
QPY = sys.executable

B2_ROOT = PROJECT_ROOT / "workspaces" / "lt-v080-sol62-personal-mvp-market-decision-b2-01"
B1_ROOT = PROJECT_ROOT / "workspaces" / "lt-v080-sol62-personal-mvp-public-runtime-foundation-b1-01"
R1_ROOT = PROJECT_ROOT / "workspaces" / "lt-v080-sol62-personal-mvp-layer1-public-01"
ASTRA_ROOT = PROJECT_ROOT / "workspaces" / "lt-v080-astra-full-system-arch-audit-roadmap-01"
PROGRAM_J_MANIFEST = PROJECT_ROOT / "baseline" / "PROGRAM_J_BASELINE_MANIFEST_20261118.json"
B2_ACCEPTANCE = PROJECT_ROOT / "controller-decisions" / "V080_CONTROLLER_B2_MARKET_DECISION_OFFLINE_INTEGRATED_ACCEPTANCE_20261119.json"
B1_ACCEPTANCE = PROJECT_ROOT / "controller-decisions" / "V080_CONTROLLER_B1_PUBLIC_RUNTIME_OFFLINE_SCOPED_ACCEPTANCE_20261118.json"
NEON_ADOPTION = PROJECT_ROOT / "controller-decisions" / "V080_CONTROLLER_GEMINI_NEON_ROUTING_ADOPTION_20261119.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sha256sums_manifest(workspace_root: Path) -> tuple[int, str]:
    manifest = workspace_root / "SHA256SUMS"
    manifest_sha = sha256_file(manifest)
    count = 0
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split("  ", 1)
        actual = sha256_file(workspace_root / rel)
        if actual != expected:
            raise AssertionError(f"Hash mismatch in {workspace_root.name}/{rel}: {actual} != {expected}")
        count += 1
    return count, manifest_sha


def verify_program_j_manifest() -> tuple[int, str]:
    manifest_sha = sha256_file(PROGRAM_J_MANIFEST)
    data = json.loads(PROGRAM_J_MANIFEST.read_text(encoding="utf-8"))
    dest_root = Path(data["destination_root"])
    files = data["files"]
    for entry in files:
        rel = entry["path"] if "path" in entry else entry["relative_path"]
        expected = entry["sha256"]
        actual = sha256_file(dest_root / rel)
        if actual != expected:
            raise AssertionError(f"Program J file mutated: {rel}")
    return len(files), manifest_sha


def git_state(repo: Path) -> dict[str, Any]:
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    branch = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()
    status = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True).strip()
    return {"branch": branch, "head": head, "clean": status == ""}


def run_logged(cmd: list[str], *, cwd: Path, log_path: Path, env: dict[str, str] | None = None) -> int:
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=180)
    combined = f"$ {shlex.join(cmd)}\n\n{proc.stdout}"
    if proc.stderr:
        combined += f"\n[stderr]\n{proc.stderr}"
    combined += f"\nexit_code={proc.returncode}\n"
    log_path.write_text(combined, encoding="utf-8")
    if proc.returncode != 0:
        print(combined, file=sys.stderr)
        raise SystemExit(proc.returncode)
    return proc.returncode


def parse_junit_counts(xml_path: Path) -> dict[str, int]:
    root = ET.parse(xml_path).getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    assert suite is not None
    tests = int(suite.attrib.get("tests", "0"))
    failures = int(suite.attrib.get("failures", "0"))
    errors = int(suite.attrib.get("errors", "0"))
    skipped = int(suite.attrib.get("skipped", "0"))
    passed = tests - failures - errors - skipped
    return {"pass": passed, "fail": failures, "error": errors, "skip": skipped, "total": tests}


def run_inherited_b2_regression() -> dict[str, int]:
    """Run accepted B2 tests on a disposable read-only copy inside unshare -n with explicit B2_ACCEPTED_B1_DB."""
    b1_demo_db = B1_ROOT / "evidence" / "demo" / "fixture.sqlite"
    assert b1_demo_db.is_file(), f"Missing accepted B1 demo DB: {b1_demo_db}"
    b1_wheel = EVIDENCE / "dependencies" / "quant_personal_public_b1-0.8.0b1-py3-none-any.whl"
    with tempfile.TemporaryDirectory(prefix="b3-inherited-b2-") as tmp:
        b2_copy = Path(tmp) / "b2_copy"
        shutil.copytree(B2_ROOT / "src", b2_copy / "src", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(B2_ROOT / "tests", b2_copy / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copyfile(B2_ROOT / "pyproject.toml", b2_copy / "pyproject.toml")
        env = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "PYTHONPATH": f"{b2_copy / 'src'}:{b1_wheel}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "B2_ACCEPTED_B1_DB": str(b1_demo_db),
            "B2_CRASH_EVIDENCE": str(Path(tmp) / "b2_crash.json"),
        }
        cmd = [
            "unshare",
            "-n",
            "--",
            QPY,
            "-B",
            "-m",
            "pytest",
            "-q",
            "tests",
            "-p",
            "no:cacheprovider",
            f"--basetemp={tmp}/cases",
            f"--junitxml={EVIDENCE / 'pytest_inherited_b2.xml'}",
        ]
        run_logged(cmd, cwd=b2_copy, log_path=EVIDENCE / "pytest_inherited_b2.log", env=env)
    return parse_junit_counts(EVIDENCE / "pytest_inherited_b2.xml")


def main() -> None:
    # Remove disposable build outputs before fresh clean generation.
    for old_dir in (EVIDENCE / "wheel", EVIDENCE / "demo"):
        if old_dir.exists():
            shutil.rmtree(old_dir)
    for pycache in B3_ROOT.rglob("__pycache__"):
        shutil.rmtree(pycache)

    # 1. Verify upstream baselines BEFORE running.
    b2_count_pre, b2_manifest_sha = verify_sha256sums_manifest(B2_ROOT)
    b1_count_pre, b1_manifest_sha = verify_sha256sums_manifest(B1_ROOT)
    r1_count_pre, r1_manifest_sha = verify_sha256sums_manifest(R1_ROOT)
    astra_count_pre, astra_manifest_sha = verify_sha256sums_manifest(ASTRA_ROOT)
    pj_count_pre, pj_manifest_sha = verify_program_j_manifest()

    # 2. Static checks: ruff, mypy, compileall (bytecode directed to temp dir).
    run_logged(
        [QPY, "-B", "-m", "ruff", "check", "--no-cache", "src", "tests", "tools"],
        cwd=B3_ROOT,
        log_path=EVIDENCE / "ruff.log",
    )
    run_logged(
        [QPY, "-B", "-m", "mypy", "--no-incremental", "--cache-dir=/dev/null", "src"],
        cwd=B3_ROOT,
        log_path=EVIDENCE / "mypy.log",
    )
    with tempfile.TemporaryDirectory(prefix="b3-pyc-") as pyc_tmp:
        compile_env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONPYCACHEPREFIX": pyc_tmp}
        run_logged(
            [QPY, "-m", "compileall", "-q", "-f", "src", "tests", "tools"],
            cwd=B3_ROOT,
            log_path=EVIDENCE / "compileall.log",
            env=compile_env,
        )

    # 3. Full B3 offline pytest inside unshare -n.
    b1_whl = EVIDENCE / "dependencies" / "quant_personal_public_b1-0.8.0b1-py3-none-any.whl"
    b2_whl = EVIDENCE / "dependencies" / "quant_personal_decision_b2-0.8.0b2-py3-none-any.whl"
    with tempfile.TemporaryDirectory(prefix="b3-pytest-") as pt_tmp:
        pt_env = {
            "PATH": "/usr/bin:/bin",
            "LANG": "C.UTF-8",
            "PYTHONPATH": f"src:{b2_whl}:{b1_whl}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        }
        run_logged(
            [
                "unshare",
                "-n",
                "--",
                QPY,
                "-B",
                "-m",
                "pytest",
                "-v",
                "tests",
                "-p",
                "no:cacheprovider",
                f"--basetemp={pt_tmp}/cases",
                "--junitxml=evidence/pytest_b3.xml",
            ],
            cwd=B3_ROOT,
            log_path=EVIDENCE / "pytest_b3.log",
            env=pt_env,
        )
    b3_counts = parse_junit_counts(EVIDENCE / "pytest_b3.xml")

    # 4. Inherited targeted B2 offline regression inside unshare -n.
    b2_counts = run_inherited_b2_regression()

    # 5. Wheel build, hash-pinned cold install, installed demo/replay, crash recovery, and mixed install inside unshare -n.
    build_env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PIP_NO_INDEX": "1"}
    run_logged(
        ["unshare", "-n", "--", QPY, "-B", "tools/build_and_audit.py"],
        cwd=B3_ROOT,
        log_path=EVIDENCE / "build_and_audit.log",
        env=build_env,
    )

    # 6. Verify upstream baselines AFTER all execution.
    b2_count_post, b2_manifest_sha_post = verify_sha256sums_manifest(B2_ROOT)
    b1_count_post, b1_manifest_sha_post = verify_sha256sums_manifest(B1_ROOT)
    r1_count_post, r1_manifest_sha_post = verify_sha256sums_manifest(R1_ROOT)
    astra_count_post, astra_manifest_sha_post = verify_sha256sums_manifest(ASTRA_ROOT)
    pj_count_post, pj_manifest_sha_post = verify_program_j_manifest()
    assert (b2_count_pre, b2_manifest_sha) == (b2_count_post, b2_manifest_sha_post)
    assert (b1_count_pre, b1_manifest_sha) == (b1_count_post, b1_manifest_sha_post)
    assert (r1_count_pre, r1_manifest_sha) == (r1_count_post, r1_manifest_sha_post)
    assert (astra_count_pre, astra_manifest_sha) == (astra_count_post, astra_manifest_sha_post)
    assert (pj_count_pre, pj_manifest_sha) == (pj_count_post, pj_manifest_sha_post)

    code_git = git_state(PROJECT_ROOT)
    docs_git = git_state(DOCS_ROOT)
    b3_wheel, = (EVIDENCE / "wheel").glob("*.whl")
    b3_wheel_sha = sha256_file(b3_wheel)
    canonical_card = DOCS_ROOT / "docs" / "prompts" / "v0.8" / "V080_PERSONAL_MVP_ACCOUNT_AWARE_DECISION_SUPPORT_B3_20261119.md"

    env_info = {
        "kernel": platform.release(),
        "arch": platform.machine(),
        "python": sys.version,
        "python_executable": QPY,
        "ssl": ssl.OPENSSL_VERSION,
        "sqlite": sqlite3.sqlite_version,
        "executor_model_interface_label": "Gemini 4 Neon (XHigh)",
        "executor_reasoning_setting": "XHigh",
        "tooling": {
            pkg: metadata.version(pkg)
            for pkg in ("pytest", "ruff", "mypy", "pip", "wheel", "setuptools")
        },
    }
    (EVIDENCE / "ENVIRONMENT.json").write_text(json.dumps(env_info, indent=2) + "\n", encoding="utf-8")

    inputs_info = {
        "task_id": "V080-PERSONAL-MVP-ACCOUNT-AWARE-B3-01",
        "activation": "Owner forwarded complete B3 prompt to Gemini Neon",
        "code_head": code_git["head"],
        "docs_head": docs_git["head"],
        "docs_baseline_before_b3_assignment": "373dd96bc5bb1d12b8663965deb8d639b93fcf3c",
        "canonical_card": {
            "branch": "docs/engineering",
            "path": "docs/prompts/v0.8/V080_PERSONAL_MVP_ACCOUNT_AWARE_DECISION_SUPPORT_B3_20261119.md",
            "sha256": sha256_file(canonical_card),
        },
        "routing_adoption": {
            "path": "controller-decisions/V080_CONTROLLER_GEMINI_NEON_ROUTING_ADOPTION_20261119.json",
            "sha256": sha256_file(NEON_ADOPTION),
        },
        "upstream": {
            "B2_controller_acceptance": "controller-decisions/V080_CONTROLLER_B2_MARKET_DECISION_OFFLINE_INTEGRATED_ACCEPTANCE_20261119.json",
            "B2_controller_acceptance_sha256": sha256_file(B2_ACCEPTANCE),
            "B2_manifest_sha256": b2_manifest_sha,
            "B2_wheel_sha256": sha256_file(b2_whl),
            "B1_controller_acceptance_sha256": sha256_file(B1_ACCEPTANCE),
            "B1_manifest_sha256": b1_manifest_sha,
            "B1_wheel_sha256": sha256_file(b1_whl),
            "R1_manifest_sha256": r1_manifest_sha,
            "Astra_manifest_sha256": astra_manifest_sha,
            "Program_J_manifest_sha256": pj_manifest_sha,
        },
        "B2_files_verified": b2_count_pre,
        "B1_files_verified": b1_count_pre,
        "R1_files_verified": r1_count_pre,
        "Astra_files_verified": astra_count_pre,
        "Program_J_files_verified": pj_count_pre,
    }
    (EVIDENCE / "INPUTS.json").write_text(json.dumps(inputs_info, indent=2) + "\n", encoding="utf-8")

    demo_summary = json.loads((EVIDENCE / "demo" / "summary.json").read_text(encoding="utf-8"))
    preservation = {
        "status": "PASS",
        "branches": {"v0.8.0": code_git, "docs/engineering": docs_git},
        "B2": {
            "sealed_files": b2_count_post,
            "manifest_sha256": b2_manifest_sha_post,
            "wheel_sha256": sha256_file(b2_whl),
            "controller_acceptance_sha256": sha256_file(B2_ACCEPTANCE),
        },
        "B1": {
            "sealed_files": b1_count_post,
            "manifest_sha256": b1_manifest_sha_post,
            "wheel_sha256": sha256_file(b1_whl),
            "controller_acceptance_sha256": sha256_file(B1_ACCEPTANCE),
        },
        "R1": {"sealed_files": r1_count_post, "manifest_sha256": r1_manifest_sha_post},
        "Astra": {"sealed_files": astra_count_post, "manifest_sha256": astra_manifest_sha_post},
        "Program_J": {"protected_files": pj_count_post, "manifest_sha256": pj_manifest_sha_post},
        "tests": {"pytest_b3": b3_counts, "pytest_inherited_b2": b2_counts},
        "B3_wheel_name": b3_wheel.name,
        "B3_wheel_sha256": b3_wheel_sha,
        "demo": {
            "scenario_count": demo_summary["scenario_count"],
            "b2_journal_immutable": demo_summary["b2_journal_immutable"],
            "all_replays_equal": demo_summary["all_replays_equal"],
            "real_account_connected": demo_summary["real_account_connected"],
        },
    }
    (EVIDENCE / "PRESERVATION.json").write_text(json.dumps(preservation, indent=2) + "\n", encoding="utf-8")

    # Clean any stray pycache directories before finishing.
    for pycache in B3_ROOT.rglob("__pycache__"):
        shutil.rmtree(pycache)

    print(json.dumps({"status": "ALL_GATES_PASS", "b3_tests": b3_counts, "b2_inherited_tests": b2_counts, "b3_wheel_sha256": b3_wheel_sha}, indent=2))


if __name__ == "__main__":
    main()
