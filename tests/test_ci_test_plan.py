"""Hermetic test planner guards and synthetic test cases."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ci.test_plan import (
    H40_QUARANTINED_NODE,
    IMMUTABLE_V06_BASE_SHA,
    KNOWN_EXE001,
    changed_paths,
    checked_plan_paths,
    classify,
    deselection_count,
    eligible_bline_h40_quarantine,
    engineering_mode,
    exact_h40_collectible,
    lint_baseline,
    pytest_command,
    verified_bline_delta,
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


def test_13_exact_finite_bline_ownership_and_full_fallbacks() -> None:
    source = "scripts/strategy_research/g2_sparse_inference_synthetic_calibration_r1.py"
    own_test = "tests/test_v06_g2_sparse_inference_synthetic_calibration_r1.py"
    assert eligible_bline_h40_quarantine([source])
    assert eligible_bline_h40_quarantine([source, own_test])
    for paths in (None, [], ["docs/project/notes.md"],
                  [source, ".github/workflows/ci.yml"],
                  [own_test, "tests/conftest.py"],
                  [source, "scripts/g1_offline_preview_r1/model.py"],
                  [source, "tests/test_v051_h40_m3a_production_discovery_producer.py"],
                  ["src/btc_quant_agent/data/binance.py"],
                  ["scripts/strategy_research/g2_unknown.py"],
                  ["tests/test_v06_arbitrary_safety.py"],
                  ["tests/test_v051_h41_probe.py"]):
        assert not eligible_bline_h40_quarantine(paths)
    assert engineering_mode(None) == "full"
    assert engineering_mode([]) == "full"
    assert engineering_mode(["docs/project/readme.md"]) == "none"


def test_14_complete_first_parent_graph_and_immutable_correction(tmp_path: Path) -> None:
    from scripts.ci import test_plan as planner

    root = planner.BLINE_H40_ROOT_SHA
    patch_sha = "a" * 40
    trial_sha = "b" * 40
    source = "scripts/strategy_research/g2_sparse_inference_synthetic_calibration_r1.py"
    own_test = "tests/test_v06_g2_sparse_inference_synthetic_calibration_r1.py"
    for name in (source, own_test):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# invented fixture\n", encoding="utf-8")

    patch = "".join("M\t" + x + "\n" for x in sorted(planner.H40_R2_CORRECTION_PATHS))
    trial = "A\t" + source + "\nA\t" + own_test + "\n"
    def factory(*, patch_delta=patch, trial_delta=trial,
                parent_ok=True, merge=False, root_ok=True, history_ok=True):
        def fake_git(*args: str):
            if args[0] == "merge-base":
                return subprocess.CompletedProcess(args, 0 if root_ok else 1, "", "")
            if args == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(args, 0, trial_sha + "\n", "")
            if args[0] == "rev-list" and args[1] == "--first-parent":
                chain = patch_sha + "\n" + trial_sha + "\n" if history_ok else patch_sha + "\n"
                return subprocess.CompletedProcess(args, 0, chain, "")
            if args[0] == "rev-list" and args[1] == "--parents":
                at = args[-1]
                p = root if at == patch_sha else patch_sha
                return subprocess.CompletedProcess(
                    args, 0, at + " " + p + (" " + root if merge else "") + "\n"
                    if parent_ok else at + " " + root + "\n", "",
                )
            if args[0] == "diff":
                prev, nxt = args[-2:]
                body = patch_delta if (prev, nxt) == (root, patch_sha) else trial_delta
                return subprocess.CompletedProcess(args, 0, body, "")
            raise AssertionError(f"Unexpected fabricated Git operation: {args}")
        return fake_git

    changed = [source, own_test]
    with patch.object(planner, "git", side_effect=factory()), patch.object(
        planner, "ROOT", tmp_path
    ):
        assert verified_bline_delta(changed) == sorted(changed)
        assert engineering_mode(changed) == "B_LINE_ENGINEERING"
    negative = (
        {"patch_delta": "M\t.github/workflows/ci.yml\n"}, # incomplete corrective patch
        {"patch_delta": patch + "M\ttests/conftest.py\n"},
        {"trial_delta": trial + "M\ttests/conftest.py\n"},
        {"trial_delta": "D\t" + source + "\n"},
        {"trial_delta": "R100\t" + source + "\tdocs/renamed.md\n"},
        {"trial_delta": ""},
        {"root_ok": False},
        {"history_ok": False},
        {"merge": True},
        {"parent_ok": False},
    )
    for kwargs in negative:
        with patch.object(planner, "git", side_effect=factory(**kwargs)), patch.object(
            planner, "ROOT", tmp_path
        ):
            assert verified_bline_delta(changed) is None
            assert engineering_mode(changed) == "full"
    with patch.object(planner, "git", side_effect=factory()), patch.object(
        planner, "ROOT", tmp_path
    ):
        assert verified_bline_delta(None) is None
        assert verified_bline_delta([]) is None
    (tmp_path / source).unlink()
    with patch.object(planner, "git", side_effect=factory()), patch.object(
        planner, "ROOT", tmp_path
    ):
        assert verified_bline_delta(changed) is None


def test_15_plan_integrity_rejects_stale_sha_and_spoofed_metadata() -> None:
    import pytest

    from scripts.ci import test_plan as planner

    fake_plan = {
        "schema_version": "B_LINE_CI_PLAN_V1",
        "code_sha": "a" * 40,
        "event": "push", "before": "b" * 40,
        "base_ref": "", "pr_base_sha": "",
        **classify(["scripts/strategy_research/g2_sparse_inference_synthetic_calibration_r1.py"]),
    }
    with patch.object(planner, "git", return_value=subprocess.CompletedProcess(
        ["git"], 0, "c" * 40 + "\n", ""
    )), pytest.raises(RuntimeError, match="CI_PLAN_SHA_IDENTITY_MISMATCH"):
        checked_plan_paths(fake_plan)
    good_head = subprocess.CompletedProcess(["git"], 0, "a" * 40 + "\n", "")
    with patch.object(planner, "git", return_value=good_head), pytest.raises(
        RuntimeError, match="CI_PLAN_EVENT_IDENTITY_MISMATCH"
    ):
        checked_plan_paths(fake_plan)
    environ = {
        "CI_EVENT_NAME": "push",
        "CI_BEFORE_SHA": "b" * 40,
        "CI_BASE_REF": "",
        "CI_PR_BASE_SHA": "",
    }
    with patch.object(planner, "git", return_value=good_head), patch.dict(
        planner.os.environ, environ
    ), patch.object(
        planner, "changed_paths", return_value=["tests/conftest.py"]
    ), pytest.raises(RuntimeError, match="CI_PLAN_CHANGED_PATHS_MISMATCH"):
        checked_plan_paths(fake_plan)


def test_16_exact_node_only_and_full_command_does_not_deselect() -> None:
    from pathlib import Path
    engineering = pytest_command("B_LINE_ENGINEERING", Path("ci-junit.xml"), [])
    full = pytest_command("full", Path("ci-junit.xml"), [])
    integration = pytest_command("integration", Path("ci-junit.xml"), ["tests/test_notify.py"])
    assert engineering == full + ["--deselect=" + H40_QUARANTINED_NODE]
    assert not any(x.startswith("--deselect") for x in full + integration)
    assert deselection_count("3006 passed, 2 skipped, 1 deselected in 42s") == 1
    assert deselection_count("3006 passed in 42s") is None
    assert deselection_count("3006 passed, 2 deselected in 42s") == 2
    assert deselection_count("1 deselected\n1 deselected") is None
    assert H40_QUARANTINED_NODE.count("::") == 1


def test_17_uncollectible_h40_node_fails_closed() -> None:
    from scripts.ci import test_plan as planner
    ok = subprocess.CompletedProcess(
        ["pytest"], 0, H40_QUARANTINED_NODE + "\n1 test collected\n", ""
    )
    with patch.object(planner.subprocess, "run", return_value=ok):
        assert exact_h40_collectible({})
    other = subprocess.CompletedProcess(
        ["pytest"], 0, H40_QUARANTINED_NODE + "_renamed\n1 test collected\n", ""
    )
    with patch.object(planner.subprocess, "run", return_value=other):
        assert not exact_h40_collectible({})
    missing = subprocess.CompletedProcess(["pytest"], 4, "", "no tests")
    with patch.object(planner.subprocess, "run", return_value=missing):
        assert not exact_h40_collectible({})


def test_18_full_schedule_and_compatibility_profiles_stay_unchanged() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "github.event_name == 'schedule' && 'full'" in workflow
    assert "inputs.profile == 'full'" in workflow
    assert 'python-version: ["3.11", "3.13"]' in workflow
    assert "continue-on-error" not in workflow
    assert "pytest -q --durations=20" in workflow
    assert "G1_CORE_MUTATED" not in workflow
