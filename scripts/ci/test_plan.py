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
BLINE_H40_BASE_SHA = "13e3a710b137efeec2e21e3002f748834ec0cc22"
H40_QUARANTINED_NODE = (
    "tests/test_v051_h40_m3a_production_discovery_producer.py"
    "::test_p09_through_p18_exact_scientific_graph"
)
# Strict finite allowlist: independently verifiable B-line source and its unit suite.
# Never infer H40 isolation from a branch name, filename prefix or directory glob.
BLINE_H40_OWNED_FILES = frozenset({
    "scripts/strategy_research/g2_sparse_inference_synthetic_calibration_r1.py",
    "tests/test_v06_g2_sparse_inference_synthetic_calibration_r1.py",
})
H40_CONTROLLER_AUTHORITY = "c9b3663bbac6f5d5d5d7ece718d4974ec4888791"
H40_UNRESOLVED_FAILURE = (
    "https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38513033356"
)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)


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
    return [str(f.relative_to(ROOT)) for f in sorted(ROOT.glob(pattern)) if f.is_file()]


def classify(changed: list[str] | None) -> dict[str, object]:
    """Classify changed files into test execution plan."""
    if changed is None:
        return {"mode": "full", "tests": [], "changed": [], "reason": "unknown-base-fail-closed"}
    if not changed:
        return {"mode": "none", "tests": [], "changed": [], "reason": "empty-diff"}

    found: set[str] = set()
    full = False

    for name in changed:
        # Critical build and testing harness configs require full suite
        if name in ("pyproject.toml", "pytest.ini", "tests/conftest.py"):
            full = True
        # Documentation and evidence only changes do not trigger business test suites
        elif name.startswith(("docs/", "evidence/", "reviews/", "prompts/")) or name.endswith(".md"):
            continue
        # CI workflows and planner scripts select CI planner unit tests
        elif name.startswith((".github/workflows/", "scripts/ci/")):
            found.update(files("tests/test_ci_*.py"))
        # Python tests changed directly
        elif name.startswith("tests/test_") and name.endswith(".py"):
            if (ROOT / name).is_file():
                found.add(name)
            else:
                # Deleted or renamed test file must not pass silently
                full = True
        # MarketWatch and Tactical subsystem
        elif name.startswith("src/btc_quant_agent/market_watch/"):
            for pat in ("tests/test_market_watch.py", "tests/test_shadow.py", "tests/test_tactical*.py"):
                found.update(files(pat))
        # Shared configuration changes map to broader configuration and tactical suites
        elif name.startswith("configs/") or name == "src/btc_quant_agent/config.py":
            found.update(files("tests/test_config*.py"))
            found.update(files("tests/test_market_watch.py"))
            found.update(files("tests/test_tactical*.py"))
        # Shared data layer changes map to data and consumer suites
        elif name.startswith("src/btc_quant_agent/data/"):
            found.update(files("tests/test_binance*.py"))
            found.update(files("tests/test_derivatives*.py"))
            found.update(files("tests/test_forward_derivatives*.py"))
            found.update(files("tests/test_data_manifest*.py"))
            found.update(files("tests/test_market_watch.py"))
        # Shared notify layer
        elif name.startswith("src/btc_quant_agent/notify/"):
            found.update(files("tests/test_notify*.py"))
            found.update(files("tests/test_market_watch.py"))
        # Shared CLI and catalog tooling
        elif name in ("src/btc_quant_agent/cli.py", "tools/catalog_surfaces.py"):
            found.update(files("tests/test_explain*.py"))
            found.update(files("tests/test_market_watch.py"))
            found.update(files("tests/test_tactical*.py"))
        # Shared domain models
        elif name == "src/btc_quant_agent/domain.py":
            found.update(files("tests/test_structure*.py"))
            found.update(files("tests/test_derivatives*.py"))
            found.update(files("tests/test_market_watch.py"))
            found.update(files("tests/test_tactical*.py"))
        # Validation scripts
        elif name.startswith("scripts/rc2/validation/"):
            found.update(files("tests/test_rc2*.py"))
        else:
            # Unmapped executable or source change must fail closed to full suite
            full = True

    return {
        "mode": "full" if full else ("focused" if found else "none"),
        "tests": sorted(found),
        "changed": changed,
        "reason": "risk-mapped",
    }



def eligible_bline_h40_quarantine(paths: list[str] | None) -> bool:
    """Only the two listed, nonempty B-line paths qualify; unknown is unsafe."""
    return bool(paths) and all(
        isinstance(path, str) and path in BLINE_H40_OWNED_FILES
        for path in paths
    )


def verified_bline_delta(changed: list[str] | None) -> list[str] | None:
    """Proof of complete changes since the controlled, fetched v0.6 integration base.

    Current CI self-patch must fail this gate; eligible descendant branches only
    become possible after Controller integration of the independently reviewed patch.
    """
    if not eligible_bline_h40_quarantine(changed):
        return None
    baseline = git("rev-parse", "--verify", "refs/remotes/origin/v0.6")
    if baseline.returncode != 0 or not re.fullmatch(r"[a-f0-9]{40}", baseline.stdout.strip()):
        return None
    base_sha = baseline.stdout.strip()
    if git("merge-base", "--is-ancestor", base_sha, "HEAD").returncode != 0:
        return None
    result = git("diff", "--no-renames", "--name-status", base_sha, "HEAD")
    if result.returncode != 0 or not result.stdout.strip():
        return None
    paths: list[str] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or parts[0] not in ("A", "M"):
            return None
        paths.append(parts[1])
    if sorted(paths) != sorted(changed or []):
        return None
    if not all(
        (ROOT / path).is_file() and not (ROOT / path).is_symlink()
        for path in paths
    ):
        return None
    return paths


def engineering_mode(changed: list[str] | None) -> str:
    """Preserve docs fast path; only verified full-tree owner diffs quarantine."""
    if changed is not None and classify(changed)["mode"] == "none":
        return "none"
    if not changed:
        return "full"
    return "B_LINE_ENGINEERING" if verified_bline_delta(changed) is not None else "full"


def checked_plan_paths(plan: dict[str, object]) -> list[str] | None:
    """Require GitHub-provided event identity and recomputed Git-diff equality."""
    if plan.get("schema_version") != "B_LINE_CI_PLAN_V1":
        raise RuntimeError("CI_PLAN_SCHEMA_UNVERIFIED")
    sha = git("rev-parse", "HEAD")
    if (
        sha.returncode != 0 or
        not re.fullmatch(r"[a-f0-9]{40}", sha.stdout.strip()) or
        plan.get("code_sha") != sha.stdout.strip()
    ):
        raise RuntimeError("CI_PLAN_SHA_IDENTITY_MISMATCH")
    git_env = {
        "event": "CI_EVENT_NAME",
        "before": "CI_BEFORE_SHA",
        "base_ref": "CI_BASE_REF",
        "pr_base_sha": "CI_PR_BASE_SHA",
    }
    for key, env_name in git_env.items():
        authoritative = os.environ.get(env_name)
        if authoritative is None or plan.get(key) != authoritative:
            raise RuntimeError("CI_PLAN_EVENT_IDENTITY_MISMATCH")
    if plan["event"] not in ("push", "pull_request"):
        return None
    changed = changed_paths(
        before=str(plan["before"]), event=str(plan["event"]),
        base_ref=str(plan["base_ref"]) or None,
        pr_base_sha=str(plan["pr_base_sha"]) or None,
    )
    expected = classify(changed)
    if any(plan.get(key) != expected[key] for key in ("mode", "tests", "changed", "reason")):
        raise RuntimeError("CI_PLAN_CHANGED_PATHS_MISMATCH")
    return changed


def deselection_count(output: str) -> int | None:
    """One and only one pytest terminal deselection summary is required."""
    counts = re.findall(r"(?<![A-Za-z0-9])(\d+) deselected\b", output)
    return int(counts[0]) if len(counts) == 1 else None


def exact_h40_collectible(env: dict[str, str]) -> bool:
    """Fail closed if the exact H40 node was renamed or no longer collects."""
    result = subprocess.run(
        ["pytest", "--collect-only", "-q", H40_QUARANTINED_NODE],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )
    exact = [line.strip() for line in result.stdout.splitlines()
             if line.strip() == H40_QUARANTINED_NODE]
    return result.returncode == 0 and exact == [H40_QUARANTINED_NODE]


def pytest_command(mode: str, junit: Path, chosen: list[str]) -> list[str]:
    command = ["pytest", "-q", "--durations=20", f"--junitxml={junit.name}", *chosen]
    if mode == "B_LINE_ENGINEERING":
        command.append(f"--deselect={H40_QUARANTINED_NODE}")
    return command


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
    observed = {str(Path(f["filename"]).resolve().relative_to(ROOT)) for f in findings}
    forbidden = observed - KNOWN_EXE001
    touched = observed.intersection(changed)
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
    p.add_argument("action", choices=["plan", "lint", "run"])
    p.add_argument("--before", default="")
    p.add_argument("--event", default="push")
    p.add_argument("--base-ref", default="")
    p.add_argument("--pr-base-sha", default="")
    p.add_argument("--profile", choices=["focused", "integration", "full", "B_LINE_ENGINEERING"], default="focused")
    args = p.parse_args()

    plan_path = ROOT / "ci-test-plan.json"
    junit_path = ROOT / "ci-junit.xml"

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
    if args.profile == "B_LINE_ENGINEERING":
        mode = engineering_mode(checked_plan_paths(plan))
    else:
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

    if mode not in ("full", "B_LINE_ENGINEERING") and not chosen:
        raise RuntimeError("EMPTY_RISK_SELECTED_SUITE_FAIL_CLOSED")

    cmd = pytest_command(mode, junit_path, chosen)

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

    if mode == "B_LINE_ENGINEERING" and not exact_h40_collectible(test_env):
        raise RuntimeError("H40_EXACT_NODE_NOT_COLLECTIBLE")
    junit_path.unlink(missing_ok=True)
    start_time = time.time()
    proc = subprocess.run(
        cmd, cwd=ROOT, env=test_env, check=False,
        text=True, capture_output=True,
    )
    elapsed = time.time() - start_time
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    junit_summary = parse_junit_xml(junit_path)
    deselected = (
        deselection_count(proc.stdout + "\n" + proc.stderr)
        if mode == "B_LINE_ENGINEERING" else 0
    )
    evidence_ok = junit_path.is_file() and int(junit_summary["total"]) > 0
    if mode == "B_LINE_ENGINEERING":
        evidence_ok = evidence_ok and deselected == 1
    passed = proc.returncode == 0 and evidence_ok
    if mode == "B_LINE_ENGINEERING":
        status = (
            "B_LINE_ENGINEERING_PASS_H40_QUARANTINED"
            if passed else "B_LINE_ENGINEERING_FAIL"
        )
    elif mode == "full":
        status = "FULL_REPO_PASS" if passed else "FULL_REPO_FAIL"
    else:
        status = f"{mode.upper()}_PASS" if passed else f"{mode.upper()}_FAIL"

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
        "status": status,
        "deselected_count": deselected,
        "quarantine": {
            "node_id": H40_QUARANTINED_NODE,
            "deselected_count": deselected,
            "code_sha": git("rev-parse", "HEAD").stdout.strip(),
            "authority_sha": H40_CONTROLLER_AUTHORITY,
            "unresolved_a_line_failure": H40_UNRESOLVED_FAILURE,
            "owner": "A-line H40",
            "reason": "Finite B-line code-diff ownership; one exact node only",
            "verified_owned_changes": verified_bline_delta(checked_plan_paths(plan)),
        } if mode == "B_LINE_ENGINEERING" else None,
    }
    plan_path.write_text(json.dumps(durable_receipt, indent=2) + "\n", encoding="utf-8")
    print("CI_STATUS", status, "DESELECTED", deselected, flush=True)

    if not passed:
        raise RuntimeError(
            f"CI_FAIL_CLOSED: {status}; pytest_rc={proc.returncode}; "
            f"junit_ok={evidence_ok}; deselected={deselected}"
        )


if __name__ == "__main__":
    main()
