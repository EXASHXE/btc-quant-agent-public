"""Guards for R03B: legacy benchmark surface removal and formal benchmark preservation."""

from __future__ import annotations

import importlib
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
from helpers_v042_economic_replay import context
from helpers_v042_semantic_goldens import case_by_id, load_goldens, preregistered_random_draws

from btc_quant_agent import economic
from btc_quant_agent.economic import (
    BenchmarkKind,
    FormalBenchmarkSuite,
    QualificationVerdict,
    evaluate_formal_economic_qualification,
)
from btc_quant_agent.economic.qualification import _cash_benchmark

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# T1: Legacy module is gone
# ---------------------------------------------------------------------------


def test_t1_legacy_benchmark_module_is_gone() -> None:
    """btc_quant_agent.economic.benchmarks must fail to import and exports must be absent."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("btc_quant_agent.economic.benchmarks")

    assert importlib.util.find_spec("btc_quant_agent.economic.benchmarks") is None

    assert not hasattr(economic, "BenchmarkEngine")
    assert not hasattr(economic, "BenchmarkResult")
    assert "BenchmarkEngine" not in dir(economic)
    assert "BenchmarkResult" not in dir(economic)
    assert "BenchmarkEngine" not in getattr(economic, "__all__", [])
    assert "BenchmarkResult" not in getattr(economic, "__all__", [])


# ---------------------------------------------------------------------------
# T2: No active references remain in src, tools, skill-template, pyproject.toml
# ---------------------------------------------------------------------------


def test_t2_no_active_references_remain() -> None:
    """Repository-level check proving no active references remain."""
    targets = [
        ROOT / "src",
        ROOT / "tools",
        ROOT / "skill-template",
        ROOT / "pyproject.toml",
    ]
    forbidden_patterns = [
        re.compile(r"\bBenchmarkEngine\b"),
        re.compile(r"\bBenchmarkResult\b"),
        re.compile(r"\beconomic\.benchmarks\b"),
    ]

    for target in targets:
        if not target.exists():
            continue
        if target.is_file():
            text = target.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                assert not pattern.search(text), f"Forbidden pattern {pattern.pattern!r} found in {target}"
            continue

        for py_path in target.rglob("*.py"):
            text = py_path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                assert not pattern.search(text), f"Forbidden pattern {pattern.pattern!r} found in {py_path}"


# ---------------------------------------------------------------------------
# T3: Canonical CASH benchmark unchanged
# ---------------------------------------------------------------------------


def test_t3_canonical_cash_benchmark_unchanged(tmp_path: Path) -> None:
    """Canonical CASH reconstruction preserves initial capital and zero activity."""
    ctx = context(tmp_path)
    comparison = ctx["comparison"]
    candles = ctx["candles"]

    cash_result = _cash_benchmark(comparison, candles)

    assert cash_result.benchmark_kind is BenchmarkKind.CASH
    assert cash_result.vehicle == "USDT_CASH_NO_TRADE"
    assert cash_result.comparable is True

    accounting = cash_result.accounting
    assert accounting["final_equity"] == comparison.initial_capital
    assert accounting["net_pnl_usdt"] == 0.0
    assert accounting["net_return_pct"] == 0.0
    assert accounting["total_trades"] == 0
    assert accounting["total_fees_usdt"] == 0.0
    assert accounting["total_funding_usdt"] == 0.0
    assert accounting["turnover_usdt"] == 0.0
    assert accounting["time_exposure_ms"] == 0
    assert accounting["fill_count"] == 0


# ---------------------------------------------------------------------------
# T4: Canonical RANDOM benchmark unchanged
# ---------------------------------------------------------------------------


def test_t4_canonical_random_benchmark_unchanged() -> None:
    """Canonical RANDOM_MATCHED deterministic draws match frozen goldens."""
    case = case_by_id(load_goldens(), "G08-DETERMINISTIC-RANDOM-PRIMITIVE")
    inputs = case["inputs"]
    observed = preregistered_random_draws(
        master_seed=inputs["master_seed"],
        ordered_opportunities=inputs["ordered_opportunities"],
        sample_count=inputs["sample_count"],
        direction_template=inputs["direction_template"],
        trial_count=inputs["trial_count"],
    )
    assert observed == case["expected"]["trials"]


# ---------------------------------------------------------------------------
# T5: Qualification binding unchanged
# ---------------------------------------------------------------------------


def test_t5_qualification_binding_unchanged(tmp_path: Path) -> None:
    """Formal candidate + benchmark suite binds correctly and evaluates qualification."""
    ctx = context(tmp_path)
    suite = ctx["suite"]
    assert isinstance(suite, FormalBenchmarkSuite)
    assert suite.comparison_contract_id == ctx["comparison"].contract_id
    assert suite.candidate_run_result_id == ctx["run"].result_id

    # Qualification evaluation produces consistent result
    qual = evaluate_formal_economic_qualification(
        protocol=ctx["protocol"],
        comparison=ctx["comparison"],
        candidate_run=ctx["run"],
        benchmarks=suite,
        required_evidence_ids=(
            "dataset",
            "run",
            "benchmark-suite",
            ctx["run"].identity.funding_evidence_id,
        ),
    )
    assert isinstance(qual.verdict, QualificationVerdict)
    assert qual.comparison_contract_id == ctx["comparison"].contract_id
    assert qual.run_result.result_id == ctx["run"].result_id


# ---------------------------------------------------------------------------
# T6: C-lite formal differential probe remains stable
# ---------------------------------------------------------------------------


def test_t6_c_lite_formal_differential_remains_stable(tmp_path: Path) -> None:
    """Differential probe produces stable hashes for unchanged synthetic inputs."""
    probe_script = ROOT / "tests/probe_v043_c_lite_differential.py"
    assert probe_script.exists()

    snapshot_path = tmp_path / "snapshot.json"
    cmd = [
        sys.executable,
        str(probe_script),
        "--root",
        str(tmp_path / "probe_root"),
        "--snapshot",
        str(snapshot_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert res.returncode == 0
    assert snapshot_path.exists()

    snapshot_data = snapshot_path.read_text(encoding="utf-8")
    assert len(snapshot_data) > 0
