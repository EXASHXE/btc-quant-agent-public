"""Hermetic test planner guards."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ci.test_plan import classify


def test_docs_only_none() -> None:
    assert classify(["docs/project/a.md"])["mode"] == "none"


def test_missing_diff_fails_closed() -> None:
    assert classify(None)["mode"] == "full"


def test_unmapped_source_fails_closed() -> None:
    assert classify(["src/btc_quant_agent/unknown.py"])["mode"] == "full"


def test_changed_test_selected() -> None:
    assert "tests/test_ci_test_plan.py" in classify(["tests/test_ci_test_plan.py"])["tests"]


def test_ci_workflow_change_selects_planner_test() -> None:
    assert "tests/test_ci_test_plan.py" in classify([".github/workflows/ci.yml"])["tests"]


def test_market_watch_change_requires_tests() -> None:
    assert classify(["src/btc_quant_agent/market_watch/scanner.py"])["mode"] == "focused"
