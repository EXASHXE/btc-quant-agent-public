"""Independent no-market-data contract witnesses and MTM interface checks."""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.metrics import (
    calculate_candidate_metrics,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_preflight import preflight
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.run_wave import execute_wave


def test_frozen_24_contract_stops_before_source_access():
    result = preflight()
    assert result["registered_candidate_ids_verified"] == 24
    assert result["parameter_checks_passed"] == 72
    assert result["signal_function_ast_unchanged"]
    assert len(result["method_conflicts"]) == 3
    assert result["source_bodies_read_this_task"] == 0
    assert result["terminal"] == "CORRECTION_INCOMPLETE_FAIL_CLOSED"


def test_h4_index_selects_old_hours_not_last_four_hours():
    # Invented 4h bar index 30 maps to completed hour 123. Original code reads
    # hours 27..30, whereas recent four hours are 120..123.
    signed_volume = np.zeros(124)
    signed_volume[27:31] = -10
    signed_volume[120:124] = 20
    assert signed_volume[30 - 3:30 + 1].sum() == -40
    assert signed_volume[123 - 3:123 + 1].sum() == 80


def test_sum_ratios_does_not_equal_sign_of_signed_volume():
    volumes = np.array([1000., 1., 1., 1.])
    flow_ratios = np.array([-.1, .5, .5, .5])
    assert flow_ratios.sum() > 0
    assert (volumes * flow_ratios).sum() < 0


def test_horizon_bar_open_and_close_cannot_be_substituted():
    # Same frozen horizon, invented divergent open and close yields 100bp.
    assert 10_000 * (101 - 100) / 100 == 100


def test_original_artifacts_cannot_be_overwritten():
    with pytest.raises(RuntimeError, match="Original wave artifacts are immutable"):
        execute_wave("WAVE_01", "not-a-commit")


def test_mtm_two_column_interface_uses_equity_not_clocks():
    folds = [{"minute_equity_curve": np.array([[59999, 1000.], [119999, 800.], [179999, 1000.]])}]
    result = calculate_candidate_metrics([], "STRESS", fold_metrics=folds)
    assert result["max_mtm_drawdown_pct"] == 20
    assert result["mean_net_bps"] is None


def test_overlapping_mtm_clock_fail_closed():
    with pytest.raises(ValueError, match="Overlapping"):
        calculate_candidate_metrics([], "STRESS", fold_metrics=[
            {"minute_equity_curve": np.array([[59999, 1000.]])},
            {"minute_equity_curve": np.array([[59999, 1000.]])},
        ])


def test_inner_pass_binds_each_candidate_explicitly():
    source = Path("scripts/strategy_research/g2_gemini_goal_trend_flow_r1/run_wave.py").read_text()
    tree = ast.parse(source)
    inner = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_pass")
    bindings = dict(zip([a.arg for a in inner.args.args][-len(inner.args.defaults):],
                        [ast.unparse(n) for n in inner.args.defaults], strict=True))
    assert bindings["cand"] == "cand"
    assert bindings["cand_id"] == "cand_id"


def test_second_open_is_sixty_seconds_later_than_frozen_next_open():
    round_time = 900000
    last_bar_start = round_time - 60000
    source_available = last_bar_start + 59999
    frozen_entry = last_bar_start + 60000
    implemented_entry = round_time + 60000
    assert frozen_entry > source_available
    assert implemented_entry - frozen_entry == 60000
