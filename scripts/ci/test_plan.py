"""Fail-closed, path-aware B-line CI planner. No protected source or exchange access."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Bounded historical allowlist for EXE001 debt.
# The effective allowlist strictly shrinks to existing files only and never expands.
HISTORICAL_EXE001 = {
    "scripts/rc1/tactical_quality/run_wp_b_replay.py",
    "scripts/rc2/tactical_quality/run_successor_r1_evidence.py",
    "scripts/rc2/validation/run_harness_qualification_r2.py",
    "scripts/rc2/validation/run_holdout_r1_1.py",
    "scripts/rc2/validation/run_holdout_r3.py",
    "tests/test_rc2_tactical_successor_r1.py",
}
KNOWN_EXE001 = {p for p in HISTORICAL_EXE001 if (ROOT / p).is_file()}

IMMUTABLE_V06_BASE_SHA = "8ecff4ec4b25bf73a35309689fd3ecfacc0d3399"


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)


OWNER_FEED_MATRIX: dict[str, object] = {
    "owner": "FEED",
    "root_prefix": "scripts/market_data/forward_public_feed_r1/",
    "description": (
        "2026 Binance /public and /market websocket routing, proxy_route, order_book, "
        "contracts, health, time_authority, replay, durability, fixture, and CLI"
    ),
    "known_modules": {
        "scripts/market_data/forward_public_feed_r1/__init__.py": "package_init",
        "scripts/market_data/forward_public_feed_r1/cli.py": "cli",
        "scripts/market_data/forward_public_feed_r1/connector.py": "binance_2026_public_market_ws_routing",
        "scripts/market_data/forward_public_feed_r1/contracts.py": "contracts",
        "scripts/market_data/forward_public_feed_r1/durability.py": "durability",
        "scripts/market_data/forward_public_feed_r1/fixture.py": "fixture",
        "scripts/market_data/forward_public_feed_r1/health.py": "health",
        "scripts/market_data/forward_public_feed_r1/order_book.py": "order_book",
        "scripts/market_data/forward_public_feed_r1/proxy_route.py": "proxy_route",
        "scripts/market_data/forward_public_feed_r1/replay.py": "replay",
        "scripts/market_data/forward_public_feed_r1/time_authority.py": "time_authority",
    },
    "owned_test_glob": "tests/test_v06_forward_public_feed_r1_*.py",
    "dependent_test_globs": (
        "tests/test_v06_forward_public_feed_r1_*.py",
        "tests/test_v06_market_event_bridge_r2_*.py",
    ),
    "expected_owned_tests": (
        "tests/test_v06_forward_public_feed_r1_adversarial.py",
        "tests/test_v06_forward_public_feed_r1_book.py",
        "tests/test_v06_forward_public_feed_r1_connector.py",
        "tests/test_v06_forward_public_feed_r1_contracts.py",
        "tests/test_v06_forward_public_feed_r1_durability.py",
        "tests/test_v06_forward_public_feed_r1_e2e_scenarios.py",
        "tests/test_v06_forward_public_feed_r1_health.py",
        "tests/test_v06_forward_public_feed_r1_proxy_route.py",
        "tests/test_v06_forward_public_feed_r1_replay.py",
        "tests/test_v06_forward_public_feed_r1_reviewer_fixes.py",
        "tests/test_v06_forward_public_feed_r1_source_qualification.py",
        "tests/test_v06_forward_public_feed_r1_time.py",
    ),
    "boundary_planner_test": "tests/test_ci_test_plan.py",
}

OWNER_BRIDGE_MATRIX: dict[str, object] = {
    "owner": "BRIDGE",
    "root_prefix": "scripts/integration/market_event_bridge_r2/",
    "description": (
        "Market event bridge R2/R3 engine, portable_ci_refs pinned B/C harness, "
        "mark_aggregator, book_ladder, funding_adapter, c_composite_bar, "
        "source_qualification, fixtures, evidence generator, and CLI"
    ),
    "known_modules": {
        "scripts/integration/market_event_bridge_r2/__init__.py": "package_init",
        "scripts/integration/market_event_bridge_r2/__main__.py": "module_entrypoint",
        "scripts/integration/market_event_bridge_r2/book_ladder.py": "book",
        "scripts/integration/market_event_bridge_r2/bridge_engine.py": "bridge_engine",
        "scripts/integration/market_event_bridge_r2/c_composite_bar.py": "c_composite_bar",
        "scripts/integration/market_event_bridge_r2/cli.py": "cli",
        "scripts/integration/market_event_bridge_r2/fixtures.py": "fixtures",
        "scripts/integration/market_event_bridge_r2/funding_adapter.py": "funding",
        "scripts/integration/market_event_bridge_r2/generate_r3_evidence.py": "generate_r3_evidence",
        "scripts/integration/market_event_bridge_r2/mark_aggregator.py": "mark",
        "scripts/integration/market_event_bridge_r2/portable_ci_refs.py": "portable_ci_refs",
        "scripts/integration/market_event_bridge_r2/source_qualification.py": "source_qualification",
    },
    "owned_test_glob": "tests/test_v06_market_event_bridge_r2_*.py",
    "dependent_test_globs": (
        "tests/test_v06_market_event_bridge_r2_*.py",
        "tests/test_v06_forward_public_feed_r1_*.py",
    ),
    "downstream_consumer_probe_tests": (
        "tests/test_v06_market_event_bridge_r2_portable_ci.py",
        "tests/test_v06_market_event_bridge_r2_c_composite_g1.py",
        "tests/test_v06_market_event_bridge_r2_settled_funding_ledger.py",
        "tests/test_v06_market_event_bridge_r2_funding_pit_provenance.py",
    ),
    "expected_owned_tests": (
        "tests/test_v06_market_event_bridge_r2_binance_2026_routes.py",
        "tests/test_v06_market_event_bridge_r2_c_composite_g1.py",
        "tests/test_v06_market_event_bridge_r2_clash_proxy_network.py",
        "tests/test_v06_market_event_bridge_r2_depth_ladder_l2.py",
        "tests/test_v06_market_event_bridge_r2_funding_pit_provenance.py",
        "tests/test_v06_market_event_bridge_r2_pit_clock_mark_last.py",
        "tests/test_v06_market_event_bridge_r2_portable_ci.py",
        "tests/test_v06_market_event_bridge_r2_settled_funding_ledger.py",
        "tests/test_v06_market_event_bridge_r2_stress_and_security.py",
    ),
    "boundary_planner_test": "tests/test_ci_test_plan.py",
}

RISK_OWNERSHIP_MATRICES: dict[str, dict[str, object]] = {
    "FEED": OWNER_FEED_MATRIX,
    "BRIDGE": OWNER_BRIDGE_MATRIX,
}

CRITICAL_HARNESS_FILES = frozenset({
    "pyproject.toml",
    "pytest.ini",
    "tests/conftest.py",
    "setup.py",
    "setup.cfg",
    "tox.ini",
    "mypy.ini",
})


def _normalize_changed_path(raw_path: object) -> str | None:
    """Normalize changed path to POSIX relative form; return None on traversal or invalid syntax."""
    if not isinstance(raw_path, str):
        return None
    if not raw_path or raw_path != raw_path.strip() or "\x00" in raw_path:
        return None
    norm = raw_path.replace("\\", "/")
    if norm.startswith("/") or ":" in norm:
        return None
    norm = norm.removeprefix("./")
    if not norm or "//" in norm or norm.endswith("/"):
        return None
    parts = norm.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    try:
        resolved_root = ROOT.resolve()
        (resolved_root / norm).resolve().relative_to(resolved_root)
    except (ValueError, OSError):
        return None
    return norm


def _has_deletion_marker(norm_path: str) -> bool:
    stem_tokens = set(re.split(r"[_\-.]+", Path(norm_path).stem.lower()))
    return bool(stem_tokens.intersection({"deleted", "removed", "missing", "nonexistent", "renamed"}))


def _resolve_feed_bridge_suite() -> list[str] | None:
    """Resolve and verify the coupled FEED + BRIDGE focused test suite.

    Fails closed (returns None) if any expected baseline test file is missing on disk.
    """
    expected_all = (
        *OWNER_FEED_MATRIX["expected_owned_tests"],  # type: ignore[misc]
        *OWNER_BRIDGE_MATRIX["expected_owned_tests"],  # type: ignore[misc]
        *OWNER_BRIDGE_MATRIX["downstream_consumer_probe_tests"],  # type: ignore[misc]
    )
    for req_test in expected_all:
        if not (ROOT / req_test).is_file():
            return None

    selected: set[str] = set()
    for pat in (
        *OWNER_FEED_MATRIX["dependent_test_globs"],  # type: ignore[misc]
        *OWNER_BRIDGE_MATRIX["dependent_test_globs"],  # type: ignore[misc]
    ):
        selected.update(files(pat))
    selected.update(OWNER_BRIDGE_MATRIX["downstream_consumer_probe_tests"])  # type: ignore[arg-type]

    if not selected or not all(req in selected for req in expected_all):
        return None
    return sorted(selected)


def changed_paths(
    before: str = "",
    event: str = "push",
    *,
    base_ref: str | None = None,
    pr_base_sha: str | None = None,
) -> list[str] | None:
    """Resolve changed files between verified merge-base and HEAD.

    Fails closed (returns None) if base or merge-base is missing or invalid.
    Includes added, modified, deleted, and renamed paths (non-silent).
    """
    if event not in ("push", "pull_request", "workflow_dispatch", "schedule"):
        return None
    if git("cat-file", "-e", "HEAD^{commit}").returncode != 0:
        return None

    base: str | None = None

    if event == "pull_request":
        if (
            pr_base_sha
            and re.fullmatch(r"[a-f0-9]{40}", pr_base_sha)
            and pr_base_sha != "0" * 40
            and git("cat-file", "-e", f"{pr_base_sha}^{{commit}}").returncode == 0
        ):
            mb = git("merge-base", pr_base_sha, "HEAD")
            if mb.returncode == 0 and mb.stdout.strip():
                base = mb.stdout.strip()
        if base is None and base_ref:
            for ref in [f"origin/{base_ref}", base_ref]:
                if git("cat-file", "-e", f"{ref}^{{commit}}").returncode == 0:
                    mb = git("merge-base", ref, "HEAD")
                    if mb.returncode == 0 and mb.stdout.strip():
                        base = mb.stdout.strip()
                        break
        if base is None:
            # Check if HEAD is a merge commit (standard GitHub Actions PR checkout)
            parents = git("rev-parse", "HEAD^@").stdout.splitlines()
            if len(parents) >= 2 and git("cat-file", "-e", "HEAD^1^{commit}").returncode == 0:
                base = "HEAD^1"
            else:
                for ref in ["origin/v0.6", "v0.6", IMMUTABLE_V06_BASE_SHA]:
                    if git("cat-file", "-e", f"{ref}^{{commit}}").returncode == 0:
                        mb = git("merge-base", ref, "HEAD")
                        if mb.returncode == 0 and mb.stdout.strip():
                            base = mb.stdout.strip()
                            break

    elif re.fullmatch(r"[a-f0-9]{40}", before) and before != "0" * 40:
        # Standard subsequent push with known prior commit
        if git("cat-file", "-e", f"{before}^{{commit}}").returncode == 0:
            base = before
        else:
            # Pushed commit history unavailable or truncated -> fail closed to full
            return None

    elif before == "0" * 40 or not before:
        # First push of a new branch:
        # Must resolve via explicitly verified merge-base against fetched v0.6 base,
        # ensuring ALL branch commits are diffed, not merely HEAD^ (last commit).
        resolved_base = None
        candidates = []
        if base_ref:
            candidates.extend([f"origin/{base_ref}", base_ref])
        candidates.extend([
            "origin/v0.6",
            "v0.6",
            IMMUTABLE_V06_BASE_SHA,
        ])
        for ref in candidates:
            if git("cat-file", "-e", f"{ref}^{{commit}}").returncode == 0:
                mb = git("merge-base", ref, "HEAD")
                if mb.returncode == 0 and mb.stdout.strip():
                    resolved_base = mb.stdout.strip()
                    break
        if resolved_base:
            base = resolved_base
        else:
            # Missing or unfetched merge-base -> fail closed to full
            return None

    else:
        return None

    if base is None or git("cat-file", "-e", f"{base}^{{commit}}").returncode != 0:
        return None

    # Deliberately disable rename detection: otherwise --name-only returns ONLY the
    # destination for R100 (e.g. tests/test_critical.py -> docs/suppressed.md).
    # Both original deletion and destination addition must be risk-classified.
    # No restrictive --diff-filter: deleted files are security-relevant.
    out = git("diff", "--no-renames", "--name-only", base, "HEAD")
    return out.stdout.splitlines() if out.returncode == 0 else None


def files(pattern: str) -> list[str]:
    return [f.relative_to(ROOT).as_posix() for f in sorted(ROOT.glob(pattern)) if f.is_file()]


def _add_mapped_patterns(found: set[str], patterns: tuple[str, ...]) -> bool:
    """Resolve patterns and add to found; return False if no existing test files matched."""
    matched: list[str] = []
    for pat in patterns:
        matched.extend(files(pat))
    if not matched:
        return False
    found.update(matched)
    return True


def classify(changed: list[str] | None) -> dict[str, object]:
    """Classify changed files into test execution plan."""
    if changed is None or not isinstance(changed, list):
        return {"mode": "full", "tests": [], "changed": [], "reason": "unknown-base-fail-closed"}
    if not changed:
        return {"mode": "none", "tests": [], "changed": [], "reason": "empty-diff"}

    found: set[str] = set()
    full = False

    feed_root = str(OWNER_FEED_MATRIX["root_prefix"])
    feed_known = OWNER_FEED_MATRIX["known_modules"]  # type: ignore[assignment]
    bridge_root = str(OWNER_BRIDGE_MATRIX["root_prefix"])
    bridge_known = OWNER_BRIDGE_MATRIX["known_modules"]  # type: ignore[assignment]

    for raw_name in changed:
        name = _normalize_changed_path(raw_name)
        if name is None:
            full = True
            continue

        # Critical build and testing harness configs require full suite
        if name in CRITICAL_HARNESS_FILES:
            full = True
        # Documentation and evidence only changes do not trigger business test suites
        elif (
            (name.startswith(("docs/", "evidence/", "reviews/", "prompts/")) or ("/" not in name and name.endswith(".md")))
            and not name.endswith((".py", ".sh"))
        ):
            continue
        # CI workflows and planner scripts select CI planner unit tests
        elif name.startswith((".github/workflows/", "scripts/ci/")):
            if not (ROOT / name).is_file() or not _add_mapped_patterns(found, ("tests/test_ci_*.py",)):
                full = True
        # Explicit Owner Matrix 1: FEED (scripts/market_data/forward_public_feed_r1/**)
        elif name.startswith(feed_root):
            if not name.endswith(".py") or _has_deletion_marker(name):
                full = True
            elif name in feed_known and not (ROOT / name).is_file():
                # Deleted or renamed known FEED production module must fail closed
                full = True
            else:
                suite = _resolve_feed_bridge_suite()
                if suite is None:
                    full = True
                else:
                    found.update(suite)
        # Explicit Owner Matrix 2: BRIDGE (scripts/integration/market_event_bridge_r2/**)
        elif name.startswith(bridge_root):
            if not name.endswith(".py") or _has_deletion_marker(name):
                full = True
            elif name in bridge_known and not (ROOT / name).is_file():
                # Deleted or renamed known BRIDGE production module must fail closed
                full = True
            else:
                suite = _resolve_feed_bridge_suite()
                if suite is None:
                    full = True
                else:
                    found.update(suite)
        # Python tests changed directly (top-level tests/test_*.py only)
        elif name.startswith("tests/test_") and name.endswith(".py") and "/" not in name[len("tests/"):]:
            if not (ROOT / name).is_file():
                # Deleted or renamed test file must not pass silently
                full = True
            else:
                found.add(name)
                if name.startswith((
                    "tests/test_v06_forward_public_feed_r1_",
                    "tests/test_v06_market_event_bridge_r2_",
                )):
                    suite = _resolve_feed_bridge_suite()
                    if suite is None:
                        full = True
                    else:
                        found.update(suite)
        # MarketWatch and Tactical subsystem
        elif name.startswith("src/btc_quant_agent/market_watch/"):
            if not (ROOT / name).is_file() or not _add_mapped_patterns(
                found,
                ("tests/test_market_watch.py", "tests/test_shadow.py", "tests/test_tactical*.py"),
            ):
                full = True
        # Shared configuration changes map to broader configuration and tactical suites
        elif name.startswith("configs/") or name == "src/btc_quant_agent/config.py":
            if not (ROOT / name).is_file() or not _add_mapped_patterns(
                found,
                ("tests/test_config*.py", "tests/test_market_watch.py", "tests/test_tactical*.py"),
            ):
                full = True
        # Shared data layer changes map to data and consumer suites
        elif name.startswith("src/btc_quant_agent/data/"):
            if not (ROOT / name).is_file() or not _add_mapped_patterns(
                found,
                (
                    "tests/test_binance*.py",
                    "tests/test_derivatives*.py",
                    "tests/test_forward_derivatives*.py",
                    "tests/test_data_manifest*.py",
                    "tests/test_market_watch.py",
                ),
            ):
                full = True
        # Shared notify layer
        elif name.startswith("src/btc_quant_agent/notify/"):
            if not (ROOT / name).is_file() or not _add_mapped_patterns(
                found,
                ("tests/test_notify*.py", "tests/test_market_watch.py"),
            ):
                full = True
        # Shared CLI and catalog tooling
        elif name in ("src/btc_quant_agent/cli.py", "tools/catalog_surfaces.py"):
            if not (ROOT / name).is_file() or not _add_mapped_patterns(
                found,
                ("tests/test_explain*.py", "tests/test_market_watch.py", "tests/test_tactical*.py"),
            ):
                full = True
        # Shared domain models
        elif name == "src/btc_quant_agent/domain.py":
            if not (ROOT / name).is_file() or not _add_mapped_patterns(
                found,
                (
                    "tests/test_structure*.py",
                    "tests/test_derivatives*.py",
                    "tests/test_market_watch.py",
                    "tests/test_tactical*.py",
                ),
            ):
                full = True
        # Validation scripts
        elif name.startswith("scripts/rc2/validation/"):
            if not (ROOT / name).is_file() or not _add_mapped_patterns(found, ("tests/test_rc2*.py",)):
                full = True
        else:
            # Unmapped executable or source change must fail closed to full suite
            full = True

    if not full and found and not all((ROOT / t).is_file() for t in found):
        full = True

    return {
        "mode": "full" if full else ("focused" if found else "none"),
        "tests": [] if full else sorted(found),
        "changed": changed,
        "reason": "risk-mapped",
    }


def export_risk_ownership_matrix() -> dict[str, object]:
    """Export serializable risk ownership dependency matrix for FEED and BRIDGE."""
    return {
        "schema_version": "B_LINE_CI_RISK_OWNERSHIP_MATRIX_V1",
        "code_sha": git("rev-parse", "HEAD").stdout.strip(),
        "owners": {
            owner_key: {
                "owner": matrix["owner"],
                "root_prefix": matrix["root_prefix"],
                "description": matrix["description"],
                "known_modules": dict(matrix["known_modules"]),  # type: ignore[arg-type]
                "owned_test_glob": matrix["owned_test_glob"],
                "dependent_test_globs": list(matrix["dependent_test_globs"]),  # type: ignore[arg-type]
                "expected_owned_tests": list(matrix["expected_owned_tests"]),  # type: ignore[arg-type]
                "downstream_consumer_probe_tests": list(
                    matrix.get("downstream_consumer_probe_tests", ())  # type: ignore[arg-type]
                ),
                "boundary_planner_test": matrix["boundary_planner_test"],
            }
            for owner_key, matrix in RISK_OWNERSHIP_MATRICES.items()
        },
        "fail_closed_invariants": {
            "unknown_executable_source": "full",
            "deleted_or_renamed_source_or_test": "full",
            "critical_harness_files": sorted(CRITICAL_HARNESS_FILES),
            "unknown_or_missing_merge_base": "full",
            "empty_selected_test_set_for_non_docs": "full_or_runtime_error",
            "forced_profile_full_overrides_focused": True,
        },
    }


def build_dry_run_plan(
    changed: list[str] | None,
    *,
    profile: str = "focused",
    event: str = "push",
) -> dict[str, object]:
    """Build hermetic dry-run plan receipt from synthetic or resolved changed paths."""
    if profile not in ("focused", "integration", "full"):
        raise ValueError(f"Unsupported profile: {profile}")

    plan = classify(changed)
    effective_mode = profile if profile != "focused" else str(plan["mode"])
    if effective_mode == "full":
        selected_tests: list[str] = []
    elif effective_mode == "integration":
        candidates = [
            "tests/test_market_watch.py",
            "tests/test_tactical_feature_evidence_v2.py",
            "tests/test_tactical_grid_shadow_evaluation_v1.py",
            "tests/test_tactical_policy_b0.py",
            "tests/test_tactical_shadow_evaluation_v2.py",
            "tests/test_explain.py",
            "tests/test_notify.py",
            "tests/test_config.py",
        ]
        selected_tests = [x for x in candidates if (ROOT / x).is_file()]
    else:
        selected_tests = list(plan["tests"])  # type: ignore[arg-type]

    feed_expected = set(OWNER_FEED_MATRIX["expected_owned_tests"])  # type: ignore[arg-type]
    bridge_expected = set(OWNER_BRIDGE_MATRIX["expected_owned_tests"])  # type: ignore[arg-type]
    selected_set = set(selected_tests)

    includes_h40_h41 = (
        True
        if effective_mode == "full"
        else any("h40" in t or "h41" in t or "h39" in t for t in selected_tests)
    )

    return {
        "schema_version": "B_LINE_CI_PLAN_V1",
        "code_sha": git("rev-parse", "HEAD").stdout.strip(),
        "event": event,
        "profile_requested": profile,
        "classified_mode": plan["mode"],
        "mode": effective_mode,
        "tests": selected_tests,
        "selected_test_file_count": len(selected_tests),
        "changed": plan["changed"],
        "reason": "forced-profile-full" if (profile == "full" and plan["mode"] != "full") else plan["reason"],
        "includes_feed_suite": effective_mode == "full" or feed_expected.issubset(selected_set),
        "includes_bridge_suite": effective_mode == "full" or bridge_expected.issubset(selected_set),
        "includes_h40_h41": includes_h40_h41,
    }


def lint_baseline(changed: list[str]) -> None:
    # Every non-EXE001 rule stays enabled. EXE001 has a strictly bounded legacy debt list.
    subprocess.run(["ruff", "check", ".", "--ignore", "EXE001"], cwd=ROOT, check=True)
    result = subprocess.run(
        ["ruff", "check", ".", "--select", "EXE001", "--output-format", "json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    findings = json.loads(result.stdout or "[]")
    observed = {Path(f["filename"]).resolve().relative_to(ROOT).as_posix() for f in findings}
    normalized_changed = {
        norm for c in changed if (norm := _normalize_changed_path(c)) is not None
    }
    forbidden = observed - KNOWN_EXE001
    touched = observed.intersection(normalized_changed or set(changed))
    if forbidden or touched:
        raise RuntimeError(f"New/touched EXE001 violation: new={forbidden}, touched={touched}")
    print("EXE001 inherited allowlist (not a lint PASS for these files):", sorted(observed))


def parse_junit_xml(junit_path: Path) -> dict[str, object]:
    """Parse JUnit XML report to accurately separate passed, failed, and skipped fixtures/tests."""
    if not junit_path.is_file():
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "skipped_details": [],
        }
    try:
        tree = ET.parse(junit_path)
        root = tree.getroot()
        total = 0
        failures = 0
        errors = 0
        skipped = 0
        skipped_details: list[dict[str, str]] = []

        for testcase in root.iter("testcase"):
            total += 1
            tc_name = testcase.attrib.get("name", "")
            tc_class = testcase.attrib.get("classname", "")
            fail_el = testcase.find("failure")
            err_el = testcase.find("error")
            skip_el = testcase.find("skipped")
            if fail_el is not None:
                failures += 1
            elif err_el is not None:
                errors += 1
            elif skip_el is not None:
                skipped += 1
                reason = skip_el.attrib.get("message") or (skip_el.text or "").strip()
                skipped_details.append({
                    "name": tc_name,
                    "classname": tc_class,
                    "reason": reason,
                })

        passed = max(0, total - failures - errors - skipped)
        return {
            "total": total,
            "passed": passed,
            "failed": failures,
            "errors": errors,
            "skipped": skipped,
            "skipped_details": skipped_details,
        }
    except (ET.ParseError, OSError, ValueError) as exc:
        print(f"Warning: failed to parse junit xml: {exc}", file=sys.stderr)
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "skipped_details": [],
        }


def main() -> None:
    p = argparse.ArgumentParser(description="Fail-closed, path-aware B-line CI planner")
    p.add_argument("action", choices=["plan", "lint", "run", "dry-run", "matrix"])
    p.add_argument("--before", default="")
    p.add_argument("--event", default="push")
    p.add_argument("--base-ref", default="")
    p.add_argument("--pr-base-sha", default="")
    p.add_argument("--profile", choices=["focused", "integration", "full"], default="focused")
    p.add_argument("--synthetic-changed", nargs="*", default=None)
    args = p.parse_args()

    plan_path = ROOT / "ci-test-plan.json"
    junit_path = ROOT / "ci-junit.xml"

    if args.action == "matrix":
        print(json.dumps(export_risk_ownership_matrix(), indent=2))
        return

    if args.action == "dry-run":
        changed = (
            args.synthetic_changed
            if args.synthetic_changed is not None
            else changed_paths(
                before=args.before,
                event=args.event,
                base_ref=args.base_ref or None,
                pr_base_sha=args.pr_base_sha or None,
            )
        )
        print(json.dumps(build_dry_run_plan(changed, profile=args.profile, event=args.event), indent=2))
        return

    if args.action == "plan":
        changed = changed_paths(
            before=args.before,
            event=args.event,
            base_ref=args.base_ref or None,
            pr_base_sha=args.pr_base_sha or None,
        )
        plan = classify(changed)
        plan_receipt = {
            "schema_version": "B_LINE_CI_PLAN_V1",
            "code_sha": git("rev-parse", "HEAD").stdout.strip(),
            "event": args.event,
            "before": args.before,
            "base_ref": args.base_ref,
            "pr_base_sha": args.pr_base_sha,
            "mode": plan["mode"],
            "tests": plan["tests"],
            "changed": plan["changed"],
            "reason": plan["reason"],
        }
        plan_path.write_text(json.dumps(plan_receipt, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(plan_receipt))
        return

    if not plan_path.exists():
        raise RuntimeError("CI test plan missing: fail closed")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    if args.action == "lint":
        lint_baseline(plan.get("changed", []))
        return

    # Action: run
    mode = args.profile if args.profile != "focused" else plan["mode"]
    if mode == "none":
        print("Docs/CI-only: tests not required; static checks enforced.")
        return

    if mode == "integration":
        candidates = [
            "tests/test_market_watch.py",
            "tests/test_tactical_feature_evidence_v2.py",
            "tests/test_tactical_grid_shadow_evaluation_v1.py",
            "tests/test_tactical_policy_b0.py",
            "tests/test_tactical_shadow_evaluation_v2.py",
            "tests/test_explain.py",
            "tests/test_notify.py",
            "tests/test_config.py",
        ]
        chosen = [x for x in candidates if (ROOT / x).is_file()]
    elif mode == "focused":
        chosen = plan["tests"]
    else:
        chosen = []

    if mode != "full" and not chosen:
        raise RuntimeError("EMPTY_RISK_SELECTED_SUITE_FAIL_CLOSED")

    cmd = ["pytest", "-q", "--durations=20", f"--junitxml={junit_path.name}", *chosen]

    # CI planner self-tests alone have no operational IO and do not need the
    # repository-wide application fixture/import graph. All application tests
    # must retain conftest hermetic guards.
    if mode == "focused" and chosen and all(x.startswith("tests/test_ci_") for x in chosen):
        cmd.insert(1, "--noconftest")

    print("PROFILE", mode, "CMD", cmd, flush=True)

    test_env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
    }

    start_time = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, env=test_env, check=False)
    elapsed = time.time() - start_time

    junit_summary = parse_junit_xml(junit_path)

    ci_run_url = None
    gh_repo = os.getenv("GITHUB_REPOSITORY")
    gh_run_id = os.getenv("GITHUB_RUN_ID")
    if gh_repo and gh_run_id:
        gh_server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
        ci_run_url = f"{gh_server}/{gh_repo}/actions/runs/{gh_run_id}"

    durable_receipt = {
        **plan,
        "schema_version": "B_LINE_CI_TEST_RECEIPT_V1",
        "tested_sha": git("rev-parse", "HEAD").stdout.strip(),
        "profile_executed": mode,
        "python_version": sys.version,
        "pytest_cmd": cmd,
        "elapsed_seconds": round(elapsed, 3),
        "returncode": proc.returncode,
        "protected_reads": 0,
        "ci_run_url": ci_run_url,
        "junit_summary": junit_summary,
    }
    plan_path.write_text(json.dumps(durable_receipt, indent=2) + "\n", encoding="utf-8")

    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


if __name__ == "__main__":
    main()

