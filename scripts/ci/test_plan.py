"""Fail-closed, path-aware B-line CI planner. No protected source or exchange access."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KNOWN_EXE001 = {
    "scripts/rc1/tactical_quality/run_wp_b_replay.py",
    "scripts/rc2/tactical_quality/run_successor_r1_evidence.py",
    "scripts/rc2/validation/run_harness_qualification_r2.py",
    "scripts/rc2/validation/run_holdout_r1_1.py",
    "scripts/rc2/validation/run_holdout_r3.py",
    "tests/test_rc2_tactical_successor_r1.py",
}


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True, check=False)


def changed_paths(before: str, event: str) -> list[str] | None:
    if event == "pull_request":
        base = "HEAD^1"
    elif re.fullmatch(r"[a-f0-9]{40}", before) and before != "0" * 40:
        base = before
    elif before == "0" * 40:
        base = "HEAD^"
    else:
        return None
    if git("cat-file", "-e", base + "^{commit}").returncode:
        return None
    out = git("diff", "--name-only", "--diff-filter=ACMRT", base, "HEAD")
    return out.stdout.splitlines() if out.returncode == 0 else None


def files(pattern: str) -> list[str]:
    return [str(f.relative_to(ROOT)) for f in sorted(ROOT.glob(pattern)) if f.is_file()]


def classify(changed: list[str] | None) -> dict[str, object]:
    if changed is None:
        return {"mode": "full", "tests": [], "changed": [], "reason": "unknown-base-fail-closed"}
    found: set[str] = set()
    full = False
    for name in changed:
        if name in ("pyproject.toml", "pytest.ini", "tests/conftest.py"):
            full = True
        elif name.startswith(("docs/", "evidence/", "reviews/", "prompts/")) or name.endswith(".md"):
            continue
        elif name.startswith((".github/workflows/", "scripts/ci/")):
            found.update(files("tests/test_ci_*.py"))
        elif name.startswith("tests/test_") and name.endswith(".py") and (ROOT / name).is_file():
            found.add(name)
        elif name.startswith("scripts/rc2/validation/"):
            found.update(files("tests/test_rc2*.py"))
        elif name.startswith("src/btc_quant_agent/market_watch/"):
            for pat in ("tests/test_market_watch.py", "tests/test_shadow.py", "tests/test_tactical*.py", "tests/test_live_v1_decision*.py"):
                found.update(files(pat))
        elif name.startswith("src/btc_quant_agent/live_v1/"):
            found.update(files("tests/test_live_v1_*.py"))
        else:
            full = True  # unknown executable change must not mean no tests
    return {"mode": "full" if full else "focused" if found else "none", "tests": sorted(found), "changed": changed, "reason": "risk-mapped"}


def lint_baseline(changed: list[str]) -> None:
    # Every non-EXE001 rule stays enabled. EXE001 has a strictly bounded legacy debt list.
    subprocess.run(["ruff", "check", ".", "--ignore", "EXE001"], cwd=ROOT, check=True)
    result = subprocess.run(
        ["ruff", "check", ".", "--select", "EXE001", "--output-format", "json"],
        cwd=ROOT, text=True, capture_output=True, check=False,
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


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["plan", "lint", "run"])
    p.add_argument("--before", default="")
    p.add_argument("--event", default="push")
    p.add_argument("--profile", choices=["focused", "integration", "full"], default="focused")
    args = p.parse_args()
    plan_path = ROOT / "ci-test-plan.json"
    if args.action == "plan":
        plan = classify(changed_paths(args.before, args.event))
        plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(plan))
        return
    if not plan_path.exists():
        raise RuntimeError("CI test plan missing: fail closed")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if args.action == "lint":
        lint_baseline(plan["changed"])
        return
    mode = args.profile if args.profile != "focused" else plan["mode"]
    if mode == "none":
        print("Docs/CI-only: tests not required; static checks enforced.")
        return
    if mode == "integration":
        chosen = [x for x in [
            "tests/test_live_v1_day2_e2e.py", "tests/test_market_watch.py",
            "tests/test_live_v1_execution_intent.py", "tests/test_live_v1_position_supervisor.py",
        ] if (ROOT / x).is_file()]
    elif mode == "focused":
        chosen = plan["tests"]
    else:
        chosen = []
    if mode != "full" and not chosen:
        raise RuntimeError("EMPTY_RISK_SELECTED_SUITE_FAIL_CLOSED")
    cmd = ["pytest", "-q", "--durations=20", "--junitxml=ci-junit.xml", *chosen]
    print("PROFILE", mode, "CMD", cmd, flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
