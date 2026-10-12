"""Deterministic synthetic test suite for G2 Conditional Exit R1 1x account, cooldown, and 35-fold embargo."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime

import numpy as np
import pytest

from scripts.strategy_research.g2_conditional_exit_r1.account import (
    path_eligible,
    replay_fold,
    size_position,
)
from scripts.strategy_research.g2_conditional_exit_r1.conditional_book import PartialIneligibleError
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import BASE, HOUR, MINUTE, STRESS
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.sources import get_monthly_folds


def make_account_fixture(
    start_ms: int = 1_612_137_600_000,  # 2021-02-01 00:00:00 UTC
    total_minutes: int = 2400,
    base_price: float = 1000.0,
) -> tuple[np.ndarray, np.ndarray, dict, dict, dict]:
    last = np.column_stack((
        start_ms + np.arange(total_minutes, dtype=np.int64) * MINUTE,
        np.full((total_minutes, 4), base_price, dtype=float),
    ))
    mark = last.copy()
    entry_at = start_ms + 300 * MINUTE  # +5 hours into fold so >=240 completed bars exist
    event = {
        "event_time": entry_at - 2 * MINUTE,
        "decision_at": entry_at - MINUTE,
        "entry_at": entry_at,
        "decision_close": base_price,
        "atr_hour": 100.0,
        "side": 1,
        "stop": base_price - 100.0,
        "event_id": "syn_acc_1",
    }
    cand = {
        "id": "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
        "horizon_hours": 12,
        "target_R": 2.0,
        "cooldown_hours": 6,
    }
    fold = {"year": 2021, "month": 2, "start_ms": start_ms, "end_ms": start_ms + total_minutes * MINUTE}
    return last, mark, event, cand, fold


def test_account_1x_5pct_reserve_and_lot_sizing() -> None:
    last, _, event, cand, _ = make_account_fixture()
    q, reserve = size_position(last, event, cand, STRESS, 1000.0)
    assert reserve["budget"] == pytest.approx(950.0)
    assert q > 0
    assert abs(round(q / 0.001) * 0.001 - q) < 1e-12
    assert q * 1000.0 <= 950.0


def test_account_min_notional_rejection_when_cash_too_small() -> None:
    last, _, event, cand, _ = make_account_fixture()
    with pytest.raises(PartialIneligibleError, match="SIZE_OR_MIN_NOTIONAL"):
        size_position(last, event, cand, STRESS, 4.0)


def test_account_recomputes_different_accepted_signals_when_x1_extends_to_18h() -> None:
    last, mark, ev1, cand, fold = make_account_fixture(total_minutes=3000)
    # ev1 enters at +5h (minute 300).
    # Under E0: exits at +17h (12h hold), cooldown 6h -> next_allowed = +23h (minute 1380).
    # Under X1 (when Mark at +17h-1m is profitable): extends to +23h (18h hold), cooldown 6h -> next_allowed = +29h (minute 1740).
    idx_12h = 300 + 12 * 60
    mark[idx_12h - 1, 1:5] = 1030.0

    # ev2 arrives at +24h (minute 1440): accepted under E0, blocked under extended X1!
    ev2_entry = fold["start_ms"] + 1440 * MINUTE
    ev2 = {
        **ev1,
        "event_id": "syn_acc_2_at_24h",
        "event_time": ev2_entry - 2 * MINUTE,
        "decision_at": ev2_entry - MINUTE,
        "entry_at": ev2_entry,
    }
    # ev3 arrives at +30h (minute 1800): blocked under E0 (since ev2 is open until +36h), accepted under X1!
    ev3_entry = fold["start_ms"] + 1800 * MINUTE
    ev3 = {
        **ev1,
        "event_id": "syn_acc_3_at_30h",
        "event_time": ev3_entry - 2 * MINUTE,
        "decision_at": ev3_entry - MINUTE,
        "entry_at": ev3_entry,
    }

    book_e0 = replay_fold(last, mark, [], [ev1, ev2, ev3], cand, fold, STRESS, "E0", 1000.0)
    book_x1 = replay_fold(
        last, mark, [], [ev1, ev2, ev3], cand, fold, STRESS, "X1_NET_POSITIVE_AT_12H", 1000.0
    )

    assert [t["event_id"] for t in book_e0["trades"]] == ["syn_acc_1", "syn_acc_2_at_24h"]
    assert [t["event_id"] for t in book_x1["trades"]] == ["syn_acc_1", "syn_acc_3_at_30h"]
    assert book_x1["fates"]["POSITION_ACK_OR_COOLDOWN"] == 1
    assert book_x1["skipped_event_ids"][0]["event_id"] == "syn_acc_2_at_24h"


def test_partial_cash_never_reopens_position_gate_before_flat_ack() -> None:
    last, mark, ev1, cand, fold = make_account_fixture()
    # Trigger TP1 at +1h after entry
    last[300 + 60, 2] = 1120.0
    ev2_entry = ev1["entry_at"] + 2 * HOUR
    ev2 = {
        **ev1,
        "event_id": "syn_during_partial",
        "event_time": ev2_entry - 2 * MINUTE,
        "decision_at": ev2_entry - MINUTE,
        "entry_at": ev2_entry,
    }
    book = replay_fold(
        last,
        mark,
        [],
        [ev1, ev2],
        cand,
        fold,
        BASE,
        "X1_NET_POSITIVE_AT_12H",
        1000.0,
        partial_tp1_fraction=0.5,
    )
    assert len(book["trades"]) == 1
    assert len(book["trades"][0]["tiers"]) == 2
    assert book["fates"]["POSITION_ACK_OR_COOLDOWN"] == 1


@pytest.mark.parametrize(
    "year,month,start_iso,end_iso",
    [
        (2021, 2, "2021-02-01T00:00:00+00:00", "2021-03-01T00:00:00+00:00"),
        (2023, 12, "2023-12-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
    ],
)
def test_2021_and_2023_month_edge_censoring_prevents_month_crossing(
    year: int, month: int, start_iso: str, end_iso: str
) -> None:
    end_ms = int(datetime.fromisoformat(end_iso).timestamp() * 1000)
    # A trade entering 17 hours before month end could cross month boundary if extended to 18h
    late_entry = end_ms - 17 * HOUR
    assert path_eligible(late_entry, end_ms, hours=12) is True
    assert path_eligible(late_entry, end_ms, hours=18) is False

    # Exact 18h + 1m boundary is censored (equality censored)
    exact_boundary_entry = end_ms - 18 * HOUR - MINUTE
    assert path_eligible(exact_boundary_entry, end_ms, hours=18) is False
    assert path_eligible(exact_boundary_entry - MINUTE, end_ms, hours=18) is True


def test_prospective_fold_censor_in_replay_fold_for_x1_and_x2() -> None:
    last, mark, ev1, cand, fold = make_account_fixture(total_minutes=1500)
    # Place entry 15 hours before fold end -> eligible for 12h E0, prospectively censored for 18h X1/X2
    late_entry = fold["end_ms"] - 15 * HOUR
    ev_late = {
        **ev1,
        "event_id": "syn_late_fold",
        "event_time": late_entry - 2 * MINUTE,
        "decision_at": late_entry - MINUTE,
        "entry_at": late_entry,
    }
    b_e0 = replay_fold(last, mark, [], [ev_late], cand, fold, STRESS, "E0", 1000.0)
    b_x1 = replay_fold(
        last, mark, [], [ev_late], cand, fold, STRESS, "X1_NET_POSITIVE_AT_12H", 1000.0
    )
    b_x2 = replay_fold(
        last, mark, [], [ev_late], cand, fold, STRESS, "X2_COMPLETED_4H_TREND_AT_12H", 1000.0
    )
    assert len(b_e0["trades"]) == 1
    assert len(b_x1["trades"]) == 0 and b_x1["fates"]["PROSPECTIVE_FOLD_CENSOR"] == 1
    assert len(b_x2["trades"]) == 0 and b_x2["fates"]["PROSPECTIVE_FOLD_CENSOR"] == 1


def test_35_monthly_folds_and_24h_embargo_structure() -> None:
    folds = get_monthly_folds()
    assert len(folds) == 35
    assert (folds[0]["year"], folds[0]["month"]) == (2021, 2)
    assert (folds[0]["prev_year"], folds[0]["prev_month"]) == (2021, 1)
    assert (folds[-1]["year"], folds[-1]["month"]) == (2023, 12)
    for f in folds:
        # 24h edge embargo at start and end of each scored month
        assert f["embargo_start_ms"] == f["start_ms"] + 24 * HOUR
        assert f["embargo_end_ms"] == f["end_ms"] - 24 * HOUR


def test_quarter_atr_gap_veto_recorded_as_entry_rejected() -> None:
    last, mark, ev1, cand, fold = make_account_fixture()
    # Set entry bar open > 0.25 * atr_hour (25.0) away from decision_close (1000.0)
    last[300, 1:5] = 1030.0
    b = replay_fold(last, mark, [], [ev1], cand, fold, STRESS, "X1_NET_POSITIVE_AT_12H", 1000.0)
    assert len(b["trades"]) == 0
    assert b["fates"]["ENTRY_OR_SIZE_REJECTED"] == 1
    assert b["ending_equity"] == 1000.0


def test_optimized_python_rejected_before_source_read() -> None:
    p = subprocess.run(
        [
            sys.executable,
            "-O",
            "-c",
            "from scripts.strategy_research.g2_conditional_exit_r1.sources import load_sources; load_sources()",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode != 0
    assert "Optimized Python forbidden" in p.stderr
