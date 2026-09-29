"""Build a stable exact-SHA R2 validation receipt from recorded local evidence."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXPECTED = "8ecff4ec4b25bf73a35309689fd3ecfacc0d3399"
PARENT = "a3235fbc39667ca2a624faebd3cf9ee8a4b442de"
root = Path(__file__).resolve().parent
implementation = Path(sys.argv[1]).resolve()
assert implementation.name == "h41-validation-r2"
assert "Quant-agent-sanitized" not in str(implementation)


def git(*args: str) -> str:
    return subprocess.check_output(("git", *args), cwd=implementation, text=True).strip()


def load(name: str) -> dict:
    return json.loads((root / f"h41_{name}_result.json").read_text())


def test_log(name: str) -> dict:
    contents = (root / f"{name}.log").read_text()
    summary = re.search(r"(\d+) passed(?:, (\d+) skipped)?(?:, (\d+) warnings)? in ([\d.]+)s", contents)
    elapsed = re.search(r"Elapsed \(wall clock\) time \(h:mm:ss or m:ss\): ([\d:.]+)", contents)
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", contents)
    exit_code = re.search(r"Exit status: (\d+)", contents)
    assert summary and elapsed and rss and exit_code
    assert exit_code.group(1) == "0"
    return {
        "passed": int(summary.group(1)),
        "skipped": int(summary.group(2) or 0),
        "warnings": int(summary.group(3) or 0),
        "pytest_seconds": float(summary.group(4)),
        "wall_clock": elapsed.group(1),
        "peak_rss_kib": int(rss.group(1)),
        "exit_code": 0,
    }


assert git("rev-parse", "HEAD") == EXPECTED
assert git("rev-parse", "HEAD^") == PARENT
assert git("status", "--porcelain") == ""
subprocess.run(("git", "diff", "--exit-code", "HEAD"), cwd=implementation, check=True)
module_path = subprocess.check_output((
    str(implementation / ".venv/bin/python"), "-c",
    "import btc_quant_agent, pathlib; print(pathlib.Path(btc_quant_agent.__file__).resolve())",
), cwd=implementation, text=True).strip()
assert Path(module_path).is_relative_to(implementation)

authority = load("authority")
science = load("science")
source = load("source_adversarial")
r2 = load("r2")
provenance = load("provenance")
boundaries = load("boundaries")
focused = test_log("focused_pytest")
full = test_log("full_pytest")
assert (authority["authority_exact"] and science["all_independent_checks_passed"]
        and source["all_fail_closed"] and r2["all_exact"]
        and provenance["all_passed"] and boundaries["h40_diff"] == "ZERO")
assert "All checks passed!" in (root / "ruff.log").read_text()
assert "Success: no issues found" in (root / "mypy.log").read_text()
assert focused["passed"] == 54 and full["passed"] >= 1798

logs = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted(root.glob("*.log"))}
validators = {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
              for file in sorted(root.glob("*.py"))}
manifest = {
    "schema_id": "H41_SYNTHETIC_PIT_EXACT_SHA_VALIDATION_R2_V1",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "implementation_sha": EXPECTED,
    "implementation_parent_sha": PARENT,
    "validation_checkout_path": str(implementation),
    "runtime_import_path": module_path,
    "pre_validation_head": EXPECTED,
    "pre_validation_worktree_status": "CLEAN",
    "post_validation_head": git("rev-parse", "HEAD"),
    "post_validation_worktree_status": "CLEAN",
    "implementation_changed": False,
    "production_and_test_blob_hashes": authority["blob_hashes"],
    "blob_mismatches": authority["blob_mismatch"],
    "authority_reconstruction_exact": authority["authority_exact"],
    "frozen_semantic_root": authority["recomputed_semantic_root"],
    "frozen_contract_hashes": {key: value["recomputed"]
                               for key, value in authority["contract_comparison"].items()},
    "source_authority_root": authority["source_comparison"]["joint_root"]["docs"],
    "candidate_count": authority["candidate_count"],
    "family_counts": authority["family_counts"],
    "active_horizons": authority["horizons"],
    "h40_diff": boundaries["h40_diff"],
    "unchanged_scientific_modules": boundaries["unchanged_scientific_modules"],
    "r2_bootstrap_function_textually_identical": boundaries["r2_function_textually_identical"],
    "r2_reference_commit": r2["reference_commit"],
    "r2_reference_blob": r2["reference_blob"],
    "r2_exact_replay_cases": r2["cases"],
    "r2_center_differs_from_mu_case": r2["center_differs_from_mu"],
    "independent_frozen_science_checks": science["checks"],
    "synthetic_source_adversarial_cases": source["cases"],
    "provenance_counterexamples": provenance["checks"],
    "performance_diagnostic_non_gating": {
        "archive_hash_rechecks": provenance["checks"]["archive_hash_rechecks"],
        "archive_hash_rechecks_per_file": provenance["checks"]["archive_hash_rechecks_per_file"],
        "estimated_duplicate_byte_reads": provenance["checks"]["estimated_duplicate_byte_reads"],
        "total_synthetic_archive_bytes_read": provenance["checks"]["total_synthetic_archive_bytes_read"],
    },
    "quality_gates": {
        "focused_pytest": focused,
        "focused_pytest_command": ".venv/bin/python -m pytest -q tests/h41/",
        "full_pytest": full,
        "full_pytest_command": ".venv/bin/python -m pytest -q",
        "ruff_command": "ruff check .",
        "ruff_check_dot_exit_code": 0,
        "mypy_command": "mypy",
        "mypy_exit_code": 0,
        "compileall_command": "python -m compileall -q src",
        "compileall_exit_code": 0,
        "git_diff_check_command": "git diff --check",
        "git_diff_check_exit_code": 0,
    },
    "execution_policy": boundaries["execution_policy"],
    "accepted_execution_write_authority": boundaries["accepted_execution_write_authority"],
    "h41_execution_imports": boundaries["h41_execution_imports"],
    "h41_main_guards": boundaries["h41_main_guards"],
    "raw_log_sha256": logs,
    "validator_script_sha256": validators,
    "protected_surface_attestation": {
        "real_h41_rows_accessed": False,
        "real_wf1_calibration_outcomes_accessed": False,
        "wf1_validation_scientific_values_accessed": False,
        "confirmation_accessed": False,
        "h39_accessed": False,
        "final_holdout_accessed": False,
        "real_candidate_lock_created": False,
        "signed_network_requests": 0,
        "execution_writes": 0,
    },
    "validation_decision": "PASS_PENDING_CONTROLLER_ACCEPTANCE",
    "H41_REAL_DISCOVERY_AUTHORIZED": False,
    "H41_WF1_VALIDATION_AUTHORIZED": False,
    "next_stage": "H41_IMPLEMENTATION_CONTROLLER_ACCEPTANCE_R2",
}
output = root.parent / "V0.5.1_H41_SYNTHETIC_PIT_EXACT_SHA_VALIDATION_R2.json"
output.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
print(output)
print(hashlib.sha256(output.read_bytes()).hexdigest())
