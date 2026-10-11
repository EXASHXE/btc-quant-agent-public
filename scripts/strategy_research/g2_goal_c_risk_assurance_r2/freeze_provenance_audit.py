"""C0 & C2.5: Freeze provenance, C R1 3-commit chain static/AST diff, CI skip truth, and read-only source admission.

Verifies:
1. Exact parent chain of Goal C R1 (`55ac4c63 -> 8db2e3ff -> 4c0bac05 -> f381dd73`) and Goal C R2 start.
2. Exact changed files, byte SHA-256 digests, and AST function-by-function comparison between
   `C_R1_FROZEN_SHA` (`8db2e3ff36011c6a65458f8cf4c2ba5e90d5fee2`) and `C_R1_MID_REPAIR_SHA`
   (`4c0bac051767f788e6de173f6563a7b47af2ac69`).
3. Procedural disposition `POST_FREEZE_REPAIR_NOT_PREACCEPTED` for C R1's 3-commit violation and
   truthful disclosure of GitHub Actions CI run `38162845456` docs-only skipped test suites,
   separated from the mathematical usability of untouched `decimal_journal.py` and `collision_matrix.py`.
4. Read-only SHA-256 and row-count admission of all 24 Exit R1 ledgers, 20 `.npz` Mark curves,
   C R1 artifacts, and 108 monthly + 8 daily gap public caches.
"""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from . import (
    C_R1_EVIDENCE_DIR,
    C_R1_FINAL_SHA,
    C_R1_FROZEN_SHA,
    C_R1_MID_REPAIR_SHA,
    EXACT_START_SHA,
    EXIT_R1_EVIDENCE_DIR,
    ORIGINAL_EXIT_R1_FINAL_SHA,
    ORIGINAL_EXIT_R1_FROZEN_SHA,
    ORIGINAL_EXIT_R1_PARENT_SHA,
    R3_CACHE_DIR,
    R3_EVIDENCE_DIR,
    R31_CACHE_DIR,
    R31_EVIDENCE_DIR,
    ROOT,
)


def _git(args: list[str], cwd: Path = ROOT) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _git_bytes(args: list[str], cwd: Path = ROOT) -> bytes:
    return subprocess.check_output(["git", *args], cwd=cwd)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _ast_function_digests(source_text: str) -> dict[str, str]:
    """Compute canonical AST dump SHA-256 for every top-level function/class/assign in a Python module."""
    tree = ast.parse(source_text)
    digests: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            digests[node.name] = sha256_bytes(ast.dump(node, include_attributes=False).encode("utf-8"))
    return digests


def audit_c_r1_three_commit_chain_and_ast_diff() -> dict[str, Any]:
    """Audit C R1's 3-commit chain (`8db2e3f -> 4c0bac0 -> f381dd7`) and prove exact symbol scope of `4c0bac0`."""
    p_freeze = _git(["rev-parse", f"{C_R1_FROZEN_SHA}^"])
    p_repair = _git(["rev-parse", f"{C_R1_MID_REPAIR_SHA}^"])
    p_final = _git(["rev-parse", f"{C_R1_FINAL_SHA}^"])
    p_exit_r1_final = _git(["rev-parse", f"{ORIGINAL_EXIT_R1_FINAL_SHA}^"])
    p_exit_r1_freeze = _git(["rev-parse", f"{ORIGINAL_EXIT_R1_FROZEN_SHA}^"])

    assert p_freeze == ORIGINAL_EXIT_R1_FINAL_SHA
    assert p_repair == C_R1_FROZEN_SHA
    assert p_final == C_R1_MID_REPAIR_SHA
    assert C_R1_FINAL_SHA == EXACT_START_SHA
    assert p_exit_r1_final == ORIGINAL_EXIT_R1_FROZEN_SHA
    assert p_exit_r1_freeze == ORIGINAL_EXIT_R1_PARENT_SHA

    changed_freeze_to_repair = _git(
        ["diff", "--name-only", C_R1_FROZEN_SHA, C_R1_MID_REPAIR_SHA]
    ).splitlines()
    changed_repair_to_final = _git(
        ["diff", "--name-only", C_R1_MID_REPAIR_SHA, C_R1_FINAL_SHA]
    ).splitlines()

    c_r1_tracked_code_and_tests = _git(
        [
            "ls-tree",
            "-r",
            "--name-only",
            C_R1_MID_REPAIR_SHA,
            "--",
            "scripts/strategy_research/g2_goal_execution_assurance_r1",
            "tests/test_v06_g2_goal_execution_assurance_r1_collision_matrix.py",
            "tests/test_v06_g2_goal_execution_assurance_r1_decimal_and_risk.py",
        ]
    ).splitlines()

    module_comparison: list[dict[str, Any]] = []
    untouched_economic_modules: list[str] = []
    modified_modules: list[str] = []

    for rel_path in c_r1_tracked_code_and_tests:
        b_freeze = _git_bytes(["show", f"{C_R1_FROZEN_SHA}:{rel_path}"])
        b_repair = _git_bytes(["show", f"{C_R1_MID_REPAIR_SHA}:{rel_path}"])
        h_freeze = sha256_bytes(b_freeze)
        h_repair = sha256_bytes(b_repair)
        identical = h_freeze == h_repair
        changed_symbols: list[str] = []
        unchanged_symbols: list[str] = []
        if rel_path.endswith(".py"):
            f_freeze = _ast_function_digests(b_freeze.decode("utf-8"))
            f_repair = _ast_function_digests(b_repair.decode("utf-8"))
            all_syms = sorted(set(f_freeze) | set(f_repair))
            for sym in all_syms:
                if f_freeze.get(sym) == f_repair.get(sym):
                    unchanged_symbols.append(sym)
                else:
                    changed_symbols.append(sym)
        if identical:
            untouched_economic_modules.append(rel_path)
        else:
            modified_modules.append(rel_path)
        module_comparison.append({
            "path": rel_path,
            "sha256_at_freeze_8db2e3ff": h_freeze,
            "sha256_at_repair_4c0bac05": h_repair,
            "byte_identical": identical,
            "changed_ast_symbols": changed_symbols,
            "unchanged_ast_symbols": unchanged_symbols,
        })

    return {
        "c_r1_procedural_freeze_status": "POST_FREEZE_REPAIR_NOT_PREACCEPTED",
        "two_commit_rule_violated_in_c_r1": True,
        "c_r1_commit_count_since_exit_r1": 3,
        "commit_chain_verified": {
            "original_exit_r1_parent_sha": ORIGINAL_EXIT_R1_PARENT_SHA,
            "original_exit_r1_frozen_sha": ORIGINAL_EXIT_R1_FROZEN_SHA,
            "original_exit_r1_final_sha": ORIGINAL_EXIT_R1_FINAL_SHA,
            "c_r1_commit_1_frozen_sha": C_R1_FROZEN_SHA,
            "c_r1_commit_1_parent": p_freeze,
            "c_r1_commit_2_mid_repair_sha": C_R1_MID_REPAIR_SHA,
            "c_r1_commit_2_parent": p_repair,
            "c_r1_commit_3_final_evidence_sha": C_R1_FINAL_SHA,
            "c_r1_commit_3_parent": p_final,
            "c_r2_exact_start_sha": EXACT_START_SHA,
        },
        "changed_files_freeze_to_mid_repair": changed_freeze_to_repair,
        "changed_files_mid_repair_to_final": changed_repair_to_final,
        "module_level_byte_and_ast_comparison": module_comparison,
        "untouched_modules_count": len(untouched_economic_modules),
        "modified_modules_count": len(modified_modules),
        "modified_modules_symbol_proof": {
            "scripts/strategy_research/g2_goal_execution_assurance_r1/attestation.py": {
                "changed_symbol": "verify_public_source_caches",
                "exact_change": (
                    "Replaced `ref['zip_name']` with `Path(ref['source_url']).name` because "
                    "`R3_SOURCE_ADMISSION_RECEIPT.json` stores the archive filename at the tail of `source_url` "
                    "rather than under a `zip_name` key."
                ),
                "affects_economic_or_invariant_calculations": False,
            },
            "scripts/strategy_research/g2_goal_execution_assurance_r1/run.py": {
                "changed_symbol": "verify_freeze_commit",
                "exact_change": (
                    "Relaxed `parent_sha != EXACT_START_SHA` to `git merge-base --is-ancestor` so the runner "
                    "would accept the middle repair commit `4c0bac05` as `--code-sha` instead of failing on "
                    "`4c0bac05^ == 8db2e3ff != 55ac4c63`."
                ),
                "affects_economic_or_invariant_calculations": False,
                "procedural_impact": (
                    "Violated the strict two-commit rule (`freeze -> evidence`). Consequently, C R1's procedural "
                    "freeze status is downgraded to `POST_FREEZE_REPAIR_NOT_PREACCEPTED`."
                ),
            },
        },
        "ci_run_38162845456_truth_disclosure": {
            "ci_run_id": 38162845456,
            "head_sha": C_R1_FINAL_SHA,
            "overall_conclusion": "SUCCESS",
            "change_filter_mode": "docs-only",
            "executed_jobs": ["change-filter", "docs-lint"],
            "skipped_jobs": ["lint-and-typecheck", "unit-tests"],
            "pytest_executed_in_final_ci": False,
            "ruff_executed_in_final_ci": False,
            "mypy_executed_in_final_ci": False,
            "audit_disposition": (
                "C R1's final commit `f381dd73` modified only `docs/` and `evidence/`, so GitHub Actions "
                "workflow `ci.yml` (`change-filter`) skipped `lint-and-typecheck` and `unit-tests` on the "
                "final commit (`8db2e3ff` and `4c0bac05` ran full CI where 3088 passed and 1 unrelated "
                "pre-existing H40 graph-hash test failed). C R1's report statement must not be read as "
                "final-commit pytest execution."
            ),
        },
        "bounded_usability_separation": {
            "c_r1_procedural_freeze_gate": "POST_FREEZE_REPAIR_NOT_PREACCEPTED",
            "c_r1_decimal_journal_48_episodes_890_trades": "BOUNDED_USABLE__REVERIFIED_BY_INDEPENDENT_C_R2_DECIMAL_REAUDIT",
            "c_r1_collision_matrix_48_fixtures": "BOUNDED_USABLE__UNTOUCHED_BY_MID_REPAIR",
            "c_r1_risk_envelope_e0_exposure_and_15x_claims": "INVALID__SUPERSEDED_BY_C_R2_RECONCILIATION",
        },
    }


def verify_read_only_sources_and_ledgers() -> dict[str, Any]:
    """Verify read-only SHA-256 digests and row counts of Exit R1 ledgers, C R1 artifacts, and public caches."""
    ledger_manifest = json.loads(
        (EXIT_R1_EVIDENCE_DIR / "COMMITTED_LEDGER_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert len(ledger_manifest) == 24

    verified_ledgers: list[dict[str, Any]] = []
    total_order_rows = 0
    total_paired_rows = 0

    for item in ledger_manifest:
        rel_path = item["committed_path"]
        f_path = ROOT / rel_path
        actual_sha = sha256_file(f_path)
        actual_bytes = f_path.stat().st_size
        rows = len(f_path.read_text(encoding="utf-8").splitlines())
        assert actual_sha == item["sha256"], f"Ledger SHA mismatch for {rel_path}"
        assert rows == int(item["rows"]), f"Ledger row count mismatch for {rel_path}"
        if rel_path.endswith("_orders.jsonl"):
            total_order_rows += rows
        else:
            total_paired_rows += rows
        verified_ledgers.append({
            "committed_path": rel_path,
            "sha256": actual_sha,
            "rows": rows,
            "bytes": actual_bytes,
            "matched": True,
        })

    assert total_order_rows == 890
    assert total_paired_rows == 178

    # Verify 108 monthly cache files in R3_CACHE_DIR and 8 daily gap ZIPs in R31_CACHE_DIR
    source_identity = json.loads(
        (EXIT_R1_EVIDENCE_DIR / "SOURCE_IDENTITY.json").read_text(encoding="utf-8")
    )
    r3_receipt = json.loads(
        (R3_EVIDENCE_DIR / "R3_SOURCE_ADMISSION_RESULTS.json").read_text(encoding="utf-8")
    )
    r31_manifest = json.loads(
        (R31_EVIDENCE_DIR / "R31_COMPOSITE_SOURCE_MANIFEST.json").read_text(encoding="utf-8")
    )

    monthly_verified = 0
    for src in source_identity["successful_sources"]:
        kind = src["kind"]
        zname = Path(src["source_url"]).name
        zpath = R3_CACHE_DIR / f"{kind}-{zname}"
        if not zpath.is_file() or zpath.is_symlink():
            raise ValueError(f"Missing or symlinked R3 cache archive: {zpath}")
        if sha256_file(zpath) != src["zip_sha256"]:
            raise ValueError(f"SHA mismatch on R3 cache archive: {zpath}")
        monthly_verified += 1
    assert monthly_verified == 108

    daily_verified = 0
    for gap in r31_manifest["gap_source_receipts"]:
        day = gap["day"]
        zpath = R31_CACHE_DIR / day / f"BTCUSDT-1m-{day}.zip"
        if not zpath.is_file() or zpath.is_symlink():
            raise ValueError(f"Missing or symlinked R3.1 daily gap archive: {zpath}")
        if sha256_file(zpath) != gap["daily_parse"]["zip_sha256"]:
            raise ValueError(f"SHA mismatch on R3.1 daily gap archive: {zpath}")
        daily_verified += 1
    assert daily_verified == 8

    # Verify 4 E0 .npz curves in R31_CACHE_DIR and 16 H1/H2/E1/E2 .npz curves in EXIT_R1_CACHE_DIR
    r31_econ = json.loads(
        (R31_EVIDENCE_DIR / "R31_ECONOMIC_RESULTS.json").read_text(encoding="utf-8")
    )
    e0_npz_verified = 0
    for c_dict in r31_econ["candidates"].values():
        for cost_dict in c_dict["costs"].values():
            mc = cost_dict["minute_curves"]
            npz_path = Path(mc["path"])
            assert sha256_file(npz_path) == mc["sha256"]
            e0_npz_verified += 1
    assert e0_npz_verified == 4

    r1_results = json.loads(
        (EXIT_R1_EVIDENCE_DIR / "EXIT_R1_RESULTS.json").read_text(encoding="utf-8")
    )
    variant_npz_verified = 0
    for c_dict in r1_results["candidates"].values():
        for cost_dict in c_dict.values():
            for scheme in ("H1", "H2", "E1", "E2"):
                mc = cost_dict["account"][scheme]["curve"]
                npz_path = Path(mc["path"])
                assert sha256_file(npz_path) == mc["sha256"]
                variant_npz_verified += 1
    assert variant_npz_verified == 16

    # Record C R1 artifact digests
    c_r1_artifacts = {}
    for fname in (
        "EXECUTION_ASSURANCE_R1_FROZEN_CONTRACT.json",
        "EXECUTION_ASSURANCE_R1_RESULTS.json",
        "DECIMAL_FORENSIC_EPISODE_AUDIT.json",
        "ADVERSARIAL_COLLISION_MATRIX_RESULTS.json",
        "EXECUTION_SENSITIVITY_AND_ATTRIBUTION.json",
        "SYNTHETIC_MARGIN_AND_LEVERAGE_STRESS.json",
        "SOURCE_VS_ALGO_VS_EXECUTION_UNKNOWN.json",
        "EXECUTION_ASSURANCE_R1_DELIVERY_MANIFEST.json",
    ):
        fpath = C_R1_EVIDENCE_DIR / fname
        c_r1_artifacts[fname] = {
            "sha256": sha256_file(fpath),
            "bytes": fpath.stat().st_size,
        }

    return {
        "status": "PASS",
        "exit_r1_ledgers_verified_n": len(verified_ledgers),
        "total_order_ledger_trades_n": total_order_rows,
        "total_paired_ledger_events_n": total_paired_rows,
        "monthly_public_zips_verified_n": monthly_verified,
        "daily_gap_zips_verified_n": daily_verified,
        "e0_npz_curves_verified_n": e0_npz_verified,
        "variant_npz_curves_verified_n": variant_npz_verified,
        "r3_source_manifest_sha256": r3_receipt["source_manifest_sha256"],
        "r31_source_manifest_sha256": r31_manifest["source_manifest_sha256"],
        "c_r1_evidence_artifact_digests": c_r1_artifacts,
    }
