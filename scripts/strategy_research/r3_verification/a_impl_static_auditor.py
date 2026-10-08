"""Static Immutable Commit Auditor for Role A (`A_IMPL_SHA`) without Live Worktree Reads."""

from __future__ import annotations

import ast
import fnmatch
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from scripts.strategy_research.r3_verification.oracle_specs import (
    CANDIDATE_REGISTRY_IDS,
    FROZEN_CODE_BASE_SHA,
    RC2_PROTECTED_SYMBOLS,
)

ROLE_A_BRANCH = "feature/v06-bline-g2-overnight-discovery-a"
ROLE_A_ALLOWED_GLOBS: tuple[str, ...] = (
    "src/btc_quant_agent/strategy_research/r3_overnight/*",
    "src/btc_quant_agent/strategy_research/r3_overnight/**",
    "tests/test_strategy_research_r3_*.py",
    "docs/strategy_research/g2_r3/prep_a/*",
    "docs/strategy_research/g2_r3/prep_a/**",
    "evidence/v0.6/b_line/g2_overnight_p0_a/*",
    "evidence/v0.6/b_line/g2_overnight_p0_a/**",
)

FORBIDDEN_IMPORT_MODULES: frozenset[str] = frozenset(
    {
        "urllib.request",
        "httpx",
        "requests",
        "websockets",
        "aiohttp",
        "socket",
        "sqlite3",
        "pyarrow.parquet",
        "zipfile",
    }
)

FORBIDDEN_SYMBOL_NAMES: frozenset[str] = frozenset(
    {
        "BinanceSignedClient",
        "urlopen",
    }
)

SHA40_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class AImplAuditResult:
    """Result of static audit of immutable remote `A_IMPL_SHA`."""

    a_impl_sha: str | None
    remote_branch: str
    audit_performed: bool
    passed: bool
    terminal_status: str
    changed_files_count: int
    changed_files: tuple[str, ...]
    candidate_ids_verified: tuple[str, ...]
    discrepancies: tuple[str, ...]
    reproduction_steps: tuple[str, ...]
    live_a_worktree_reads: int = 0


def is_role_a_path_allowed(rel_path: str) -> bool:
    norm = rel_path.strip().replace("\\", "/")
    if norm.startswith("src/btc_quant_agent/strategy_research/r3_overnight/"):
        return True
    if norm.startswith("docs/strategy_research/g2_r3/prep_a/"):
        return True
    if norm.startswith("evidence/v0.6/b_line/g2_overnight_p0_a/"):
        return True
    return fnmatch.fnmatch(norm, "tests/test_strategy_research_r3_*.py")


def resolve_remote_a_impl_sha(
    repo_root: Path,
    *,
    remote_name: str = "origin",
    branch_name: str = ROLE_A_BRANCH,
) -> str | None:
    """Query remote git server for Role A's branch SHA without touching A's worktree."""
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "ls-remote", "--heads", remote_name, branch_name],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    first_token = proc.stdout.strip().split()[0]
    if SHA40_RE.match(first_token):
        return first_token
    return None


def audit_a_impl_file_map(
    *,
    a_impl_sha: str | None,
    file_contents: dict[str, str],
    remote_branch: str = ROLE_A_BRANCH,
) -> AImplAuditResult:
    """Statically audit a map of `{rel_path: content}` from an immutable `A_IMPL_SHA`."""
    if not a_impl_sha:
        return AImplAuditResult(
            a_impl_sha=None,
            remote_branch=remote_branch,
            audit_performed=False,
            passed=True,
            terminal_status="P0_B_READY_WAITING_A_IMPL_SHA",
            changed_files_count=0,
            changed_files=(),
            candidate_ids_verified=(),
            discrepancies=(),
            reproduction_steps=(
                f"git ls-remote --heads origin {remote_branch} -> empty (A_IMPL_SHA not yet pushed)",
            ),
            live_a_worktree_reads=0,
        )

    if not SHA40_RE.match(a_impl_sha):
        return AImplAuditResult(
            a_impl_sha=a_impl_sha,
            remote_branch=remote_branch,
            audit_performed=True,
            passed=False,
            terminal_status="P0_B_DISCREPANCY_BLOCKED",
            changed_files_count=0,
            changed_files=(),
            candidate_ids_verified=(),
            discrepancies=(f"INVALID_A_IMPL_SHA_FORMAT:{a_impl_sha}",),
            reproduction_steps=(f"Validate SHA format of {a_impl_sha}",),
            live_a_worktree_reads=0,
        )

    discrepancies: list[str] = []
    changed_paths = tuple(sorted(file_contents.keys()))

    if not changed_paths:
        discrepancies.append("EMPTY_A_IMPL_DIFF_AGAINST_BASE")

    for rel_path in changed_paths:
        if not is_role_a_path_allowed(rel_path):
            discrepancies.append(f"ROLE_A_PATH_OUTSIDE_ALLOWLIST:{rel_path}")

    combined_source_text = "\n".join(file_contents.values())

    # Check all 8 frozen candidate IDs are present across A's implementation/docs/evidence
    found_candidates: list[str] = []
    for cid in CANDIDATE_REGISTRY_IDS:
        if cid in combined_source_text:
            found_candidates.append(cid)
        else:
            discrepancies.append(f"MISSING_FROZEN_CANDIDATE_ID:{cid}")

    # AST and JSON inspection per file
    for rel_path, content in sorted(file_contents.items()):
        if rel_path.endswith(".py"):
            try:
                tree = ast.parse(content, filename=rel_path)
            except SyntaxError as exc:
                discrepancies.append(f"PYTHON_SYNTAX_ERROR:{rel_path}:{exc.lineno}")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in FORBIDDEN_IMPORT_MODULES or any(
                            alias.name.startswith(m + ".") for m in FORBIDDEN_IMPORT_MODULES
                        ):
                            discrepancies.append(
                                f"FORBIDDEN_IMPORT:{rel_path}:{alias.name}"
                            )
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    for alias in node.names:
                        full_name = f"{mod}.{alias.name}" if mod else alias.name
                        if (
                            mod in FORBIDDEN_IMPORT_MODULES
                            or full_name in FORBIDDEN_IMPORT_MODULES
                            or alias.name in FORBIDDEN_SYMBOL_NAMES
                        ):
                            discrepancies.append(
                                f"FORBIDDEN_IMPORT_FROM:{rel_path}:{full_name}"
                            )
                elif isinstance(node, ast.Name) and node.id in FORBIDDEN_SYMBOL_NAMES:
                    discrepancies.append(f"FORBIDDEN_SYMBOL_REFERENCE:{rel_path}:{node.id}")

        elif rel_path.endswith(".json"):
            try:
                parsed = json.loads(content)
            except ValueError as exc:
                discrepancies.append(f"INVALID_JSON_ARTIFACT:{rel_path}:{exc}")
                continue
            if isinstance(parsed, dict):
                rf_auth = parsed.get("real_funds_write_authority")
                if rf_auth is not None and rf_auth != "NONE":
                    discrepancies.append(
                        f"INVALID_REAL_FUNDS_AUTHORITY:{rel_path}:{rf_auth}"
                    )
                # Ensure no RC2 protected symbols are claimed as evaluated candidates
                symbols_field = parsed.get("symbols")
                if isinstance(symbols_field, list):
                    for sym in symbols_field:
                        if str(sym).upper() in RC2_PROTECTED_SYMBOLS:
                            discrepancies.append(
                                f"RC2_PROTECTED_SYMBOL_IN_JSON:{rel_path}:{sym}"
                            )
                manifest_summary = parsed.get("manifest_summary")
                if isinstance(manifest_summary, dict):
                    reported_rows = manifest_summary.get("reported_row_count")
                    if reported_rows is not None and int(reported_rows) != 2_934_720:
                        discrepancies.append(
                            f"DISCREPANCY_A02_MANIFEST_ROW_COUNT_MISMATCH:{rel_path}:"
                            f"reported={reported_rows},expected=2934720"
                        )

    # Semantic contract checks on Role A's ledger.py, signals.py, and replay_engine.py
    ledger_src = file_contents.get(
        "src/btc_quant_agent/strategy_research/r3_overnight/ledger.py", ""
    )
    signals_src = file_contents.get(
        "src/btc_quant_agent/strategy_research/r3_overnight/signals.py", ""
    )
    replay_src = file_contents.get(
        "src/btc_quant_agent/strategy_research/r3_overnight/replay_engine.py", ""
    )

    if ledger_src:
        if "max_hold_ms=0" in ledger_src and "self.positions[fill.symbol] = Position(" in ledger_src:
            discrepancies.append(
                "DISCREPANCY_A03_STAGE1_FILL_ACK_OVERWRITES_POSITION_MAX_HOLD_MS_ZERO:"
                "src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L280-L294"
            )
        if (
            "def _stage_2_account_risk" in ledger_src
            and "self.last_available_marks[sym] = (mbar.close, mbar.timestamp_ms, mbar.available_at_ms)"
            in ledger_src
        ):
            discrepancies.append(
                "DISCREPANCY_A06_STAGE2_MARK_UPDATE_AND_BAR_OPEN_TIMESTAMP_AGE_CHECK:"
                "src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L147,L331-L341"
            )
        if "self.cooldown_until_ms[trade.symbol] = open_time_ms + COOLDOWN_DURATION_MS" in ledger_src:
            discrepancies.append(
                "DISCREPANCY_A07A_COOLDOWN_ANCHORED_TO_ACK_TIME_INSTEAD_OF_ECONOMIC_EXIT_CEIL:"
                "src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L139,L309"
            )
        if (
            "cost_commitment_exit_usdt=RESERVE_BUFFER_MULTIPLIER" in ledger_src
            and "* (self.cost_model.fee_rate + self.cost_model.friction_rate)\n                * order.quantity"
            in ledger_src
        ):
            discrepancies.append(
                "DISCREPANCY_A08_STAGE5_EXIT_COMMITMENT_OMITS_TICK_SIZE_TERM:"
                "src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L556-L559"
            )

    if signals_src and replay_src:
        if (
            "self.signal_generator = SignalGenerator()" in replay_src
            and "key = (symbol, candidate.direction)" in signals_src
        ):
            discrepancies.append(
                "DISCREPANCY_A04_SHARED_SIGNAL_GENERATOR_CORRUPTS_RETEST_STATE_ACROSS_04H_AND_12H:"
                "src/btc_quant_agent/strategy_research/r3_overnight/replay_engine.py:L42,signals.py:L260"
            )
        if (
            "sig = self.signal_generator.evaluate_hourly_decision(" in replay_src
            and "last_exit_time_ms=" not in replay_src
            and "last_entry_4h_time_ms=" not in replay_src
        ):
            discrepancies.append(
                "DISCREPANCY_A07B_REPLAY_ENGINE_OMITS_COOLDOWN_AND_4H_DEDUP_ARGS:"
                "src/btc_quant_agent/strategy_research/r3_overnight/replay_engine.py:L129-L134"
            )

    if signals_src and (
        'current_1h.high >= breakout.boundary - Decimal("0.25") * breakout.frozen_atr'
        in signals_src
        or "min(breakout.intermediate_lows)" in signals_src
        or "max(breakout.intermediate_highs)" in signals_src
    ):
        discrepancies.append(
            "DISCREPANCY_A05_CLOSED_RETEST_TOUCH_ZONE_INEQUALITY_AND_STOP_EXTREMUM_OMITS_BREAKOUT_BAR:"
            "src/btc_quant_agent/strategy_research/r3_overnight/signals.py:L295-L307,L323-L335"
        )

    passed = len(discrepancies) == 0
    return AImplAuditResult(
        a_impl_sha=a_impl_sha,
        remote_branch=remote_branch,
        audit_performed=True,
        passed=passed,
        terminal_status=(
            "P0_B_ORACLE_READY_FOR_CONTROLLER"
            if passed
            else "P0_B_DISCREPANCY_BLOCKED"
        ),
        changed_files_count=len(changed_paths),
        changed_files=changed_paths,
        candidate_ids_verified=tuple(found_candidates),
        discrepancies=tuple(discrepancies),
        reproduction_steps=(
            f"git fetch --no-tags origin {a_impl_sha}",
            f"git diff --name-only {FROZEN_CODE_BASE_SHA}..{a_impl_sha}",
            f"Run static AST/contract audit on {len(changed_paths)} changed files at {a_impl_sha}",
        ),
        live_a_worktree_reads=0,
    )


def audit_remote_a_impl_commit(
    repo_root: Path,
    *,
    a_impl_sha: str | None = None,
    base_sha: str = FROZEN_CODE_BASE_SHA,
) -> AImplAuditResult:
    """Inspect immutable remote `A_IMPL_SHA` from Git objects only (never reading A's worktree)."""
    resolved_sha = (
        a_impl_sha
        if a_impl_sha is not None
        else resolve_remote_a_impl_sha(repo_root)
    )
    if resolved_sha is None:
        return audit_a_impl_file_map(a_impl_sha=None, file_contents={})

    # Ensure object is present locally via read-only git cat-file or fetch by SHA
    cat_proc = subprocess.run(
        ["git", "-C", str(repo_root), "cat-file", "-e", f"{resolved_sha}^{{commit}}"],
        text=True,
        capture_output=True,
        check=False,
    )
    if cat_proc.returncode != 0:
        subprocess.run(
            ["git", "-C", str(repo_root), "fetch", "--no-tags", "origin", resolved_sha],
            text=True,
            capture_output=True,
            check=False,
        )

    diff_proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--no-renames",
            "--name-only",
            base_sha,
            resolved_sha,
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if diff_proc.returncode != 0:
        return AImplAuditResult(
            a_impl_sha=resolved_sha,
            remote_branch=ROLE_A_BRANCH,
            audit_performed=True,
            passed=False,
            terminal_status="P0_B_DISCREPANCY_BLOCKED",
            changed_files_count=0,
            changed_files=(),
            candidate_ids_verified=(),
            discrepancies=(f"UNABLE_TO_DIFF_A_IMPL_SHA:{resolved_sha}",),
            reproduction_steps=(
                f"git -C {repo_root} diff --name-only {base_sha} {resolved_sha}",
            ),
            live_a_worktree_reads=0,
        )

    file_map: dict[str, str] = {}
    for rel_path in diff_proc.stdout.splitlines():
        rel_path = rel_path.strip()
        if not rel_path:
            continue
        show_proc = subprocess.run(
            ["git", "-C", str(repo_root), "show", f"{resolved_sha}:{rel_path}"],
            text=True,
            capture_output=True,
            check=False,
        )
        if show_proc.returncode == 0:
            file_map[rel_path] = show_proc.stdout

    return audit_a_impl_file_map(a_impl_sha=resolved_sha, file_contents=file_map)
