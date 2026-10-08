"""Hermetic test planner guards and synthetic test cases."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ci.test_plan import (
    IMMUTABLE_V06_BASE_SHA,
    KNOWN_EXE001,
    changed_paths,
    classify,
    lint_baseline,
)


def test_01_docs_only_none() -> None:
    """Docs and evidence changes must result in mode 'none' (fast path)."""
    assert classify(["docs/project/a.md"])["mode"] == "none"
    assert classify(["README.md", "docs/MARKET_WATCH_FEISHU.md"])["mode"] == "none"
    assert classify(["evidence/v0.6/b_line/receipt.json", "prompts/v0.6/dev.md"])["mode"] == "none"
    res = classify(["reviews/v0.5/review.md"])
    assert res["mode"] == "none"
    assert res["tests"] == []


def test_02_ci_only_selects_planner_tests() -> None:
    """CI workflow and planner script changes select CI planner tests."""
    res_wf = classify([".github/workflows/ci.yml"])
    assert res_wf["mode"] == "focused"
    assert "tests/test_ci_test_plan.py" in res_wf["tests"]

    res_script = classify(["scripts/ci/test_plan.py"])
    assert res_script["mode"] == "focused"
    assert "tests/test_ci_test_plan.py" in res_script["tests"]


def test_03_market_watch_selects_tactical_focused() -> None:
    """MarketWatch subsystem changes select Tactical focused suite."""
    res = classify(["src/btc_quant_agent/market_watch/scanner.py"])
    assert res["mode"] == "focused"
    assert "tests/test_market_watch.py" in res["tests"]
    assert "tests/test_tactical_feature_evidence_v2.py" in res["tests"]
    assert "tests/test_tactical_policy_b0.py" in res["tests"]


def test_04_shared_config_data_selects_broader_suites() -> None:
    """Shared config, data, notify, CLI and domain map to appropriate broader suites."""
    # Shared configs
    res_cfg = classify(["configs/default.toml"])
    assert res_cfg["mode"] == "focused"
    assert "tests/test_config.py" in res_cfg["tests"]
    assert "tests/test_market_watch.py" in res_cfg["tests"]

    res_cfg_py = classify(["src/btc_quant_agent/config.py"])
    assert res_cfg_py["mode"] == "focused"
    assert "tests/test_config.py" in res_cfg_py["tests"]
    assert "tests/test_market_watch.py" in res_cfg_py["tests"]

    # Shared data
    res_data = classify(["src/btc_quant_agent/data/binance.py"])
    assert res_data["mode"] == "focused"
    assert "tests/test_binance_archive.py" in res_data["tests"]
    assert "tests/test_derivatives.py" in res_data["tests"]
    assert "tests/test_market_watch.py" in res_data["tests"]

    # Shared notify
    res_notify = classify(["src/btc_quant_agent/notify/feishu.py"])
    assert res_notify["mode"] == "focused"
    assert "tests/test_notify.py" in res_notify["tests"]
    assert "tests/test_market_watch.py" in res_notify["tests"]

    # Shared CLI
    res_cli = classify(["src/btc_quant_agent/cli.py"])
    assert res_cli["mode"] == "focused"
    assert "tests/test_explain.py" in res_cli["tests"]
    assert "tests/test_market_watch.py" in res_cli["tests"]

    # Shared domain
    res_dom = classify(["src/btc_quant_agent/domain.py"])
    assert res_dom["mode"] == "focused"
    assert "tests/test_structure.py" in res_dom["tests"]
    assert "tests/test_derivatives.py" in res_dom["tests"]


def test_05_unknown_executable_dependency_fails_closed_to_full() -> None:
    """Unmapped source and critical test harness files fail closed to full suite."""
    assert classify(["src/btc_quant_agent/unknown_module.py"])["mode"] == "full"
    assert classify(["pyproject.toml"])["mode"] == "full"
    assert classify(["tests/conftest.py"])["mode"] == "full"
    assert classify(["pytest.ini"])["mode"] == "full"


def test_06_first_branch_push_with_multiple_commits() -> None:
    """On first branch push (before is 0*40), merge-base against v0.6 is used."""
    # When before is 0*40 and base_ref is v0.6, it resolves merge-base
    paths = changed_paths(before="0" * 40, event="push", base_ref="v0.6")
    # In this git worktree, merge-base against v0.6 exists, so paths is a list (not None)
    assert paths is not None
    assert isinstance(paths, list)


def test_07_missing_unfetched_merge_base_fails_closed_to_full() -> None:
    """When merge-base is missing or unfetched, planner fails closed to full."""
    # Null diff result
    plan_none = classify(None)
    assert plan_none["mode"] == "full"
    assert plan_none["reason"] == "unknown-base-fail-closed"

    # Nonexistent SHA for normal push
    assert changed_paths(before="1" * 40, event="push") is None

    # Invalid event / before
    assert changed_paths(before="invalid_sha", event="push") is None

    # First push with missing base ref and unresolvable v0.6
    with patch("scripts.ci.test_plan.git") as mock_git:
        # Simulate all git calls failing or returning non-zero
        mock_git.return_value = subprocess.CompletedProcess(
            args=["git"], returncode=128, stdout="", stderr="fatal"
        )
        assert changed_paths(before="0" * 40, event="push") is None


def test_08_pr_merge_rename_delete_non_silent() -> None:
    """Deleted test files and PR diffs are non-silent and fail closed or resolve."""
    # If a test file was deleted (does not exist on disk), it must fail closed to full
    res_del_test = classify(["tests/test_nonexistent_deleted_synthetic.py"])
    assert res_del_test["mode"] == "full"

    # PR with valid pr_base_sha resolves merge-base
    pr_paths = changed_paths(
        before="",
        event="pull_request",
        pr_base_sha=IMMUTABLE_V06_BASE_SHA,
    )
    assert pr_paths is not None

    # PR with invalid pr_base_sha and unresolvable base fails closed
    with patch("scripts.ci.test_plan.git") as mock_git:
        mock_git.return_value = subprocess.CompletedProcess(
            args=["git"], returncode=1, stdout="", stderr=""
        )
        assert changed_paths(
            before="",
            event="pull_request",
            pr_base_sha="2" * 40,
        ) is None


def test_09_changed_existing_test_selected() -> None:
    """Directly changed existing test is selected."""
    res = classify(["tests/test_ci_test_plan.py"])
    assert res["mode"] == "focused"
    assert "tests/test_ci_test_plan.py" in res["tests"]


def test_10_exe001_inherited_allowlist_shrinks_and_fails_on_new() -> None:
    """EXE001 allowlist contains only existing files and shrinks; new violations fail."""
    for p in KNOWN_EXE001:
        assert (ROOT / p).is_file()

    # Touching a non-allowlisted violation raises RuntimeError
    with patch("subprocess.run") as mock_run:
        # Mock ruff check json finding a violation not in KNOWN_EXE001
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=["ruff"], returncode=0),  # non-EXE001
            subprocess.CompletedProcess(
                args=["ruff"],
                returncode=1,
                stdout='[{"filename": "src/new_script.py"}]',
                stderr="",
            ),
        ]
        import pytest
        with pytest.raises(RuntimeError, match="New/touched EXE001 violation"):
            lint_baseline(["src/new_script.py"])

def test_11_git_rename_from_test_to_docs_must_not_skip_original_path(tmp_path: Path) -> None:
    """A rename with an innocuous destination must preserve the deleted test path."""
    from scripts.ci import test_plan as planner

    repo = tmp_path / "rename-fixture"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CI Renames"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "ci-renames@example.invalid"], cwd=repo, check=True)
    (repo / "tests").mkdir()
    old_file = repo / "tests/test_critical.py"
    old_file.write_text("def test_critical(): assert True\\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", "tests/test_critical.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "baseline critical test"], cwd=repo, check=True, capture_output=True)
    oldsha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "docs").mkdir()
    subprocess.run(["git", "mv", "tests/test_critical.py", "docs/suppressed.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "rename test into docs"], cwd=repo, check=True, capture_output=True)

    with patch.object(planner, "ROOT", repo):
        changed = planner.changed_paths(before=oldsha, event="push")
        assert changed is not None
        assert "docs/suppressed.md" in changed
        assert "tests/test_critical.py" in changed
        assert planner.classify(changed)["mode"] == "full"


def test_12_git_rename_from_source_to_docs_must_not_skip_original_path(tmp_path: Path) -> None:
    """A source file renamed to docs must not be treated as docs-only."""
    from scripts.ci import test_plan as planner

    repo = tmp_path / "source-rename-fixture"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CI Renames"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "ci-renames@example.invalid"], cwd=repo, check=True)
    source_dir = repo / "src/btc_quant_agent"
    source_dir.mkdir(parents=True)
    (source_dir / "safety.py").write_text("SAFETY = True\\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", "src/btc_quant_agent/safety.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "baseline safety module"], cwd=repo, check=True, capture_output=True)
    oldsha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    (repo / "docs").mkdir()
    subprocess.run(["git", "mv", "src/btc_quant_agent/safety.py", "docs/safety.md"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "rename source into docs"], cwd=repo, check=True, capture_output=True)

    with patch.object(planner, "ROOT", repo):
        changed = planner.changed_paths(before=oldsha, event="push")
        assert changed is not None
        assert "docs/safety.md" in changed
        assert "src/btc_quant_agent/safety.py" in changed
        assert planner.classify(changed)["mode"] == "full"
