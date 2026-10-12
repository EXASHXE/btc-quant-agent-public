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


# ---------------------------------------------------------------------------
# Fast-Path R1 Risk-Mapped Ownership & Fail-Closed Guard Suite (>=35 new cases)
# ---------------------------------------------------------------------------


def _assert_feed_and_bridge_focused(res: dict[str, object]) -> None:
    from scripts.ci.test_plan import OWNER_BRIDGE_MATRIX, OWNER_FEED_MATRIX

    assert res["mode"] == "focused"
    tests = list(res["tests"])  # type: ignore[arg-type]
    assert tests == sorted(set(tests))
    for req in OWNER_FEED_MATRIX["expected_owned_tests"]:  # type: ignore[union-attr]
        assert req in tests
    for req in OWNER_BRIDGE_MATRIX["expected_owned_tests"]:  # type: ignore[union-attr]
        assert req in tests
    for probe in OWNER_BRIDGE_MATRIX["downstream_consumer_probe_tests"]:  # type: ignore[union-attr]
        assert probe in tests
    assert not any("h40" in t or "h41" in t or "h39" in t for t in tests)


def test_13_feed_connector_2026_ws_routing_selects_feed_and_bridge() -> None:
    """FEED 2026 Binance /public and /market websocket connector selects FEED + BRIDGE."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/market_data/forward_public_feed_r1/connector.py"])
    )


def test_14_feed_proxy_route_selects_feed_and_bridge() -> None:
    """FEED proxy_route selects FEED + BRIDGE suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/market_data/forward_public_feed_r1/proxy_route.py"])
    )


def test_15_feed_order_book_selects_feed_and_bridge() -> None:
    """FEED order_book selects FEED + BRIDGE suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/market_data/forward_public_feed_r1/order_book.py"])
    )


def test_16_feed_contracts_selects_feed_and_bridge() -> None:
    """FEED contracts selects FEED + BRIDGE suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/market_data/forward_public_feed_r1/contracts.py"])
    )


def test_17_feed_health_selects_feed_and_bridge() -> None:
    """FEED health supervisor selects FEED + BRIDGE suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/market_data/forward_public_feed_r1/health.py"])
    )


def test_18_feed_time_authority_selects_feed_and_bridge() -> None:
    """FEED time_authority selects FEED + BRIDGE suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/market_data/forward_public_feed_r1/time_authority.py"])
    )


def test_19_feed_replay_selects_feed_and_bridge() -> None:
    """FEED replay selects FEED + BRIDGE suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/market_data/forward_public_feed_r1/replay.py"])
    )


def test_20_feed_durability_selects_feed_and_bridge() -> None:
    """FEED durability selects FEED + BRIDGE suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/market_data/forward_public_feed_r1/durability.py"])
    )


def test_21_feed_cli_fixture_and_init_select_feed_and_bridge() -> None:
    """FEED cli.py, fixture.py, and __init__.py each select FEED + BRIDGE suites."""
    for mod in (
        "scripts/market_data/forward_public_feed_r1/cli.py",
        "scripts/market_data/forward_public_feed_r1/fixture.py",
        "scripts/market_data/forward_public_feed_r1/__init__.py",
    ):
        _assert_feed_and_bridge_focused(classify([mod]))


def test_22_bridge_engine_selects_bridge_and_feed_and_probes() -> None:
    """BRIDGE bridge_engine.py selects BRIDGE + FEED suites and downstream B/C probes."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/integration/market_event_bridge_r2/bridge_engine.py"])
    )


def test_23_bridge_portable_ci_refs_selects_bridge_and_feed() -> None:
    """BRIDGE portable_ci_refs.py selects BRIDGE + FEED suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/integration/market_event_bridge_r2/portable_ci_refs.py"])
    )


def test_24_bridge_mark_aggregator_selects_bridge_and_feed() -> None:
    """BRIDGE mark_aggregator.py selects BRIDGE + FEED suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/integration/market_event_bridge_r2/mark_aggregator.py"])
    )


def test_25_bridge_book_ladder_selects_bridge_and_feed() -> None:
    """BRIDGE book_ladder.py selects BRIDGE + FEED suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/integration/market_event_bridge_r2/book_ladder.py"])
    )


def test_26_bridge_funding_adapter_selects_bridge_and_feed() -> None:
    """BRIDGE funding_adapter.py selects BRIDGE + FEED suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/integration/market_event_bridge_r2/funding_adapter.py"])
    )


def test_27_bridge_source_qualification_selects_bridge_and_feed() -> None:
    """BRIDGE source_qualification.py selects BRIDGE + FEED suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/integration/market_event_bridge_r2/source_qualification.py"])
    )


def test_28_bridge_cli_c_composite_and_helpers_select_bridge_and_feed() -> None:
    """BRIDGE cli, c_composite_bar, fixtures, generate_r3_evidence, __init__, __main__ select both."""
    for mod in (
        "scripts/integration/market_event_bridge_r2/cli.py",
        "scripts/integration/market_event_bridge_r2/c_composite_bar.py",
        "scripts/integration/market_event_bridge_r2/fixtures.py",
        "scripts/integration/market_event_bridge_r2/generate_r3_evidence.py",
        "scripts/integration/market_event_bridge_r2/__init__.py",
        "scripts/integration/market_event_bridge_r2/__main__.py",
    ):
        _assert_feed_and_bridge_focused(classify([mod]))


def test_29_new_python_file_inside_known_feed_and_bridge_roots_survives() -> None:
    """Adding a new Python file inside known FEED or BRIDGE owner roots maps to both suites."""
    _assert_feed_and_bridge_focused(
        classify(["scripts/market_data/forward_public_feed_r1/new_ws_channel_router.py"])
    )
    _assert_feed_and_bridge_focused(
        classify(["scripts/integration/market_event_bridge_r2/new_settlement_verifier.py"])
    )


def test_30_non_python_file_inside_owner_roots_fails_closed_to_full() -> None:
    """Non-Python files inside FEED or BRIDGE roots must fail closed to full."""
    assert classify(["scripts/market_data/forward_public_feed_r1/run.sh"])["mode"] == "full"
    assert classify(["scripts/integration/market_event_bridge_r2/config.yaml"])["mode"] == "full"
    assert classify(["scripts/integration/market_event_bridge_r2/Makefile"])["mode"] == "full"


def test_31_narrow_unmapped_script_namespaces_fail_closed_to_full() -> None:
    """Other script namespaces with no guaranteed owning map remain FULL (no scripts/** exemption)."""
    assert classify(["scripts/strategy_research/g2_btc_empirical_fast_r1/run.py"])["mode"] == "full"
    assert classify(["scripts/strategy_research/g2_exit_horizon_r1/run.py"])["mode"] == "full"
    assert classify(["scripts/rc1/tactical_quality/run_wp_b_replay.py"])["mode"] == "full"
    assert classify(["scripts/market_data/unmapped_feed/client.py"])["mode"] == "full"
    assert classify(["scripts/integration/unmapped_bridge/engine.py"])["mode"] == "full"


def test_32_direct_feed_test_change_selects_coupled_feed_and_bridge_suites() -> None:
    """Directly changing a FEED test file selects the entire coupled FEED + BRIDGE suite."""
    res = classify(["tests/test_v06_forward_public_feed_r1_book.py"])
    _assert_feed_and_bridge_focused(res)
    assert len(res["tests"]) == 21  # type: ignore[arg-type]


def test_33_direct_bridge_test_change_selects_coupled_bridge_and_feed_suites() -> None:
    """Directly changing a BRIDGE test file selects the entire coupled BRIDGE + FEED suite."""
    res = classify(["tests/test_v06_market_event_bridge_r2_funding_pit_provenance.py"])
    _assert_feed_and_bridge_focused(res)
    assert len(res["tests"]) == 21  # type: ignore[arg-type]


def test_34_same_commit_feed_bridge_and_changed_tests_union_dedup_order() -> None:
    """Same-commit FEED + BRIDGE + planner + test changes produce stable deduplicated sorted union."""
    diff_a = [
        "scripts/integration/market_event_bridge_r2/bridge_engine.py",
        "scripts/market_data/forward_public_feed_r1/order_book.py",
        "tests/test_v06_forward_public_feed_r1_book.py",
        "tests/test_v06_market_event_bridge_r2_portable_ci.py",
        "scripts/ci/test_plan.py",
        "tests/test_ci_test_plan.py",
    ]
    diff_b = list(reversed(diff_a))
    res_a = classify(diff_a)
    res_b = classify(diff_b)
    assert res_a["mode"] == "focused"
    assert res_b["mode"] == "focused"
    assert res_a["tests"] == res_b["tests"]
    tests = list(res_a["tests"])  # type: ignore[arg-type]
    assert len(tests) == 22
    assert "tests/test_ci_test_plan.py" in tests
    _assert_feed_and_bridge_focused(res_a)


def test_35_windows_backslash_separators_normalized_identically() -> None:
    """Windows backslash paths normalize cleanly and match POSIX classification."""
    win_res = classify([
        r"scripts\market_data\forward_public_feed_r1\cli.py",
        r"scripts\integration\market_event_bridge_r2\bridge_engine.py",
        r"docs\engineering\ci_fastpath_r1\MAPPING_AND_SAFETY_RATIONALE.md",
    ])
    posix_res = classify([
        "scripts/market_data/forward_public_feed_r1/cli.py",
        "scripts/integration/market_event_bridge_r2/bridge_engine.py",
        "docs/engineering/ci_fastpath_r1/MAPPING_AND_SAFETY_RATIONALE.md",
    ])
    assert win_res["mode"] == "focused"
    assert win_res["tests"] == posix_res["tests"]
    assert all("\\" not in t for t in win_res["tests"])  # type: ignore[union-attr]


def test_36_path_traversal_and_malformed_paths_fail_closed_to_full() -> None:
    """Path traversal, absolute paths, drive letters, and malformed strings fail closed to full."""
    for bad_path in (
        "docs/../src/btc_quant_agent/engine.py",
        "scripts/market_data/forward_public_feed_r1/../../strategy_research/run.py",
        "../outside_repo.py",
        "/etc/passwd",
        r"C:\Windows\System32\cmd.exe",
        "scripts/market_data/forward_public_feed_r1//cli.py",
        "scripts/market_data/forward_public_feed_r1/",
        "",
        "   ",
        " scripts/ci/test_plan.py",
    ):
        res = classify([bad_path])
        assert res["mode"] == "full", f"Expected full for {bad_path!r}"
        assert res["tests"] == []


def test_37_code_changed_plus_test_removed_forces_full() -> None:
    """Code changed alongside a deleted test file must force FULL and clear partial test list."""
    res = classify([
        "scripts/integration/market_event_bridge_r2/bridge_engine.py",
        "tests/test_v06_market_event_bridge_r2_deleted_test.py",
    ])
    assert res["mode"] == "full"
    assert res["tests"] == []


def test_38_missing_baseline_owner_test_on_disk_forces_full() -> None:
    """If any expected baseline FEED or BRIDGE test file is missing on disk, planner forces FULL."""
    from scripts.ci import test_plan as planner

    orig_is_file = Path.is_file

    def fake_is_file(self: Path) -> bool:
        if self.name == "test_v06_market_event_bridge_r2_portable_ci.py":
            return False
        return orig_is_file(self)

    with patch.object(Path, "is_file", fake_is_file):
        res = planner.classify(["scripts/market_data/forward_public_feed_r1/cli.py"])
        assert res["mode"] == "full"
        assert res["tests"] == []


def test_39_deleted_or_renamed_known_feed_or_bridge_source_forces_full() -> None:
    """If a known FEED or BRIDGE production module is deleted/renamed on disk, planner forces FULL."""
    from scripts.ci import test_plan as planner

    orig_is_file = Path.is_file

    def fake_is_file(self: Path) -> bool:
        if self.name in ("order_book.py", "bridge_engine.py"):
            return False
        return orig_is_file(self)

    with patch.object(Path, "is_file", fake_is_file):
        assert planner.classify(["scripts/market_data/forward_public_feed_r1/order_book.py"])["mode"] == "full"
        assert planner.classify(["scripts/integration/market_event_bridge_r2/bridge_engine.py"])["mode"] == "full"


def test_40_test_subdirectory_deletion_or_modification_forces_full() -> None:
    """Changes or deletions in test subdirectories (e.g., tests/h41/* or tests/goldens/*) force FULL."""
    assert classify(["tests/h41/test_authority_and_signals.py"])["mode"] == "full"
    assert classify(["tests/h41/deleted_test.py"])["mode"] == "full"
    assert classify(["tests/goldens/v042_semantic_goldens.json"])["mode"] == "full"


def test_41_shared_schemas_clock_wallet_execution_h40_h41_force_full() -> None:
    """Broad shared schemas, clock/time_boundary, wallet/account, execution, H40, H41 force FULL."""
    for critical_shared in (
        "src/btc_quant_agent/sqlite_schema.py",
        "src/btc_quant_agent/time_boundary.py",
        "src/btc_quant_agent/account_watch/service.py",
        "src/btc_quant_agent/execution/service.py",
        "src/btc_quant_agent/economic/simulator.py",
        "src/btc_quant_agent/h40/protocol.py",
        "src/btc_quant_agent/h41/science.py",
        "src/btc_quant_agent/live_db.py",
        "src/btc_quant_agent/storage.py",
    ):
        res = classify([critical_shared])
        assert res["mode"] == "full", f"Expected full for {critical_shared}"


def test_42_critical_harness_files_mixed_with_feed_or_docs_force_full() -> None:
    """pyproject.toml, pytest.ini, tests/conftest.py mixed with FEED or docs force FULL."""
    for harness_file in ("pyproject.toml", "pytest.ini", "tests/conftest.py", "mypy.ini"):
        res = classify([
            "scripts/market_data/forward_public_feed_r1/cli.py",
            "docs/README.md",
            harness_file,
        ])
        assert res["mode"] == "full"
        assert res["tests"] == []


def test_43_shared_config_and_domain_do_not_escape_and_fail_closed_if_deleted() -> None:
    """Shared config/domain map to their dependent suites and fail closed to full if deleted."""
    res = classify([
        "src/btc_quant_agent/domain.py",
        "scripts/integration/market_event_bridge_r2/bridge_engine.py",
    ])
    assert res["mode"] == "focused"
    assert "tests/test_structure.py" in res["tests"]  # type: ignore[operator]
    assert "tests/test_v06_market_event_bridge_r2_portable_ci.py" in res["tests"]  # type: ignore[operator]

    # Nonexistent config file (deleted config) must fail closed to full
    assert classify(["configs/deleted_nonexistent.toml"])["mode"] == "full"


def test_44_malformed_git_baseline_and_unknown_event_fail_closed() -> None:
    """Unknown event types, uppercase SHAs, or failed git diff return None -> classify full."""
    assert changed_paths(before="", event="unknown_webhook_event") is None
    assert changed_paths(before="ABCDEF" + "0" * 34, event="push") is None
    assert classify(None)["mode"] == "full"
    assert classify("not-a-list")["mode"] == "full"  # type: ignore[arg-type]


def test_45_dry_run_fixture_bridge_engine_and_cli_selects_both_excludes_h40_h41() -> None:
    """Executable dry-run plan for modified bridge_engine + cli selects FEED+BRIDGE and no H40/H41."""
    from scripts.ci.test_plan import build_dry_run_plan

    receipt = build_dry_run_plan([
        "scripts/integration/market_event_bridge_r2/bridge_engine.py",
        "scripts/market_data/forward_public_feed_r1/cli.py",
    ])
    assert receipt["schema_version"] == "B_LINE_CI_PLAN_V1"
    assert len(str(receipt["code_sha"])) == 40
    assert receipt["mode"] == "focused"
    assert receipt["selected_test_file_count"] == 21
    assert receipt["includes_feed_suite"] is True
    assert receipt["includes_bridge_suite"] is True
    assert receipt["includes_h40_h41"] is False


def test_46_dry_run_fixture_unknown_source_selects_full() -> None:
    """Executable dry-run plan for unknown source selects full mode and includes H40/H41."""
    from scripts.ci.test_plan import build_dry_run_plan

    receipt = build_dry_run_plan(["src/btc_quant_agent/engine.py"])
    assert receipt["mode"] == "full"
    assert receipt["tests"] == []
    assert receipt["includes_h40_h41"] is True


def test_47_forced_profile_full_overrides_focused_plan_to_entire_suite() -> None:
    """Forced PROFILE=full overrides focused classification to run the entire unfiltered suite."""
    from scripts.ci.test_plan import build_dry_run_plan

    receipt = build_dry_run_plan(
        ["scripts/integration/market_event_bridge_r2/bridge_engine.py"],
        profile="full",
    )
    assert receipt["classified_mode"] == "focused"
    assert receipt["mode"] == "full"
    assert receipt["tests"] == []
    assert receipt["reason"] == "forced-profile-full"
    assert receipt["includes_h40_h41"] is True


def test_48_workflow_yaml_retains_weekly_schedule_manual_full_and_compatibility_matrix() -> None:
    """Verify .github/workflows/ci.yml preserves weekly full schedule and manual full gates."""
    wf_text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in wf_text
    assert "options: [focused, integration, full]" in wf_text
    assert 'cron: "21 3 * * 1"' in wf_text
    assert "cancel-in-progress: true" in wf_text
    assert "github.event_name == 'schedule' && 'full'" in wf_text
    assert "github.event_name == 'workflow_dispatch' && inputs.profile == 'full'" in wf_text
    assert 'python-version: ["3.11", "3.13"]' in wf_text


def test_49_evidence_and_docs_only_fastpath_and_smuggled_py_rejection() -> None:
    """Evidence/docs additions return mode 'none', but .py smuggled into docs/evidence forces full."""
    res = classify([
        "docs/engineering/ci_fastpath_r1/MAPPING_AND_SAFETY_RATIONALE.md",
        "docs/engineering/ci_fastpath_r1/BENCHMARK_AND_RELEASE_GATES.md",
        "evidence/v0.6/b_line/ci_fastpath_r1/BEFORE_AFTER_RISK_PLAN.json",
        "evidence/v0.6/b_line/ci_fastpath_r1/TEST_AND_CI_EXACT_SHA.json",
    ])
    assert res["mode"] == "none"
    assert res["tests"] == []

    # Smuggled Python script inside docs/ or evidence/ or src/*.md must fail closed to full
    assert classify(["docs/engineering/hidden_exec.py"])["mode"] == "full"
    assert classify(["evidence/v0.6/b_line/script.py"])["mode"] == "full"
    assert classify(["src/btc_quant_agent/ disguised.md"])["mode"] == "full"


def test_50_ci_only_fastpath_selects_only_planner_tests() -> None:
    """Touched scripts/ci/test_plan.py + tests/test_ci_test_plan.py + docs/evidence selects only CI tests."""
    res = classify([
        "scripts/ci/test_plan.py",
        "tests/test_ci_test_plan.py",
        "docs/engineering/ci_fastpath_r1/MAPPING_AND_SAFETY_RATIONALE.md",
        "evidence/v0.6/b_line/ci_fastpath_r1/BEFORE_AFTER_RISK_PLAN.json",
    ])
    assert res["mode"] == "focused"
    assert res["tests"] == ["tests/test_ci_test_plan.py"]


def test_51_cli_dry_run_and_matrix_subcommands_emit_valid_json() -> None:
    """CLI dry-run and matrix actions execute deterministically and output valid JSON receipts."""
    import json

    proc_dry = subprocess.run(
        [
            sys.executable,
            "scripts/ci/test_plan.py",
            "dry-run",
            "--synthetic-changed",
            "scripts/integration/market_event_bridge_r2/bridge_engine.py",
            "scripts/market_data/forward_public_feed_r1/cli.py",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    data_dry = json.loads(proc_dry.stdout)
    assert data_dry["mode"] == "focused"
    assert data_dry["selected_test_file_count"] == 21
    assert data_dry["includes_h40_h41"] is False

    proc_mat = subprocess.run(
        [sys.executable, "scripts/ci/test_plan.py", "matrix"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    data_mat = json.loads(proc_mat.stdout)
    assert data_mat["schema_version"] == "B_LINE_CI_RISK_OWNERSHIP_MATRIX_V1"
    assert "FEED" in data_mat["owners"]
    assert "BRIDGE" in data_mat["owners"]


def test_52_exported_risk_ownership_matrix_files_exist_on_disk() -> None:
    """Every known module and expected test file in FEED and BRIDGE matrices exists on disk."""
    from scripts.ci.test_plan import export_risk_ownership_matrix

    matrix = export_risk_ownership_matrix()
    assert len(str(matrix["code_sha"])) == 40
    owners = matrix["owners"]  # type: ignore[index]
    for owner_name in ("FEED", "BRIDGE"):
        entry = owners[owner_name]  # type: ignore[index]
        for mod_path in entry["known_modules"]:
            assert (ROOT / mod_path).is_file(), f"Missing known module: {mod_path}"
        for test_path in entry["expected_owned_tests"]:
            assert (ROOT / test_path).is_file(), f"Missing expected test: {test_path}"
        for probe_path in entry["downstream_consumer_probe_tests"]:
            assert (ROOT / probe_path).is_file(), f"Missing probe test: {probe_path}"

