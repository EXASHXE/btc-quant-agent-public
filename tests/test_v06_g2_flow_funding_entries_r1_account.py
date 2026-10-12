"""Synthetic tests for account replay, sizing, cash reserve, cooldown, and 24h fold embargo."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategy_research.g2_flow_funding_entries_r1.account import (
    compute_marked_equity_curve,
    compute_size,
    get_folds,
    path_eligible,
    replay_account,
)
from scripts.strategy_research.g2_flow_funding_entries_r1.book import (
    BASE,
    HOUR,
    LOT,
    MINUTE,
)


def _mock_continuous_path(n_hours: int = 50, base_price: float = 30000.0) -> tuple[np.ndarray, np.ndarray]:
    n_1m = n_hours * 60
    t0 = 1612137600000  # 2021-02-01 00:00:00 UTC (Fold 1 start)
    times = t0 + np.arange(n_1m, dtype=np.int64) * MINUTE
    last = np.empty((n_1m, 7), dtype=np.float64)
    last[:, 0] = times
    last[:, 1] = base_price
    last[:, 2] = base_price + 10.0
    last[:, 3] = base_price - 10.0
    last[:, 4] = base_price
    last[:, 5] = 100.0
    last[:, 6] = 50.0

    mark = np.empty((n_1m, 5), dtype=np.float64)
    mark[:, 0] = times
    mark[:, 1] = base_price
    mark[:, 2] = base_price + 10.0
    mark[:, 3] = base_price - 10.0
    mark[:, 4] = base_price

    return last, mark


def test_compute_size_enforces_reserve_and_lot() -> None:
    """compute_size enforces 5% reserve and 0.001 LOT discretization."""
    last, _ = _mock_continuous_path(n_hours=5)
    t0 = int(last[0, 0])
    event = {
        "event_time": t0 + 2 * MINUTE,
        "decision_at": t0 + 3 * MINUTE,
        "entry_at": t0 + 4 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    cand = {"horizon_hours": 12, "target_r": 2.0}
    cash = 1000.0

    q, reserve_info = compute_size(last, event, cand, BASE, cash)

    # Lot discretization
    assert abs(q - round(q / LOT) * LOT) < 1e-9
    # Budget cap at 95% of cash
    assert reserve_info["budget"] <= 0.95 * cash + 1e-8
    # Quantity * entry price fits in budget
    assert q * 30000.0 <= reserve_info["budget"]
    # No negative reserves
    assert reserve_info["exit_cost_reserve"] > 0
    assert reserve_info["funding_reserve"] > 0
    assert reserve_info["budget"] > 0


def test_zero_volume_flow_stability() -> None:
    """Zero volume bars do not cause division by zero in sizing or flow."""
    last, _ = _mock_continuous_path(n_hours=2)
    last[:, 5] = 0.0  # zero volume
    last[:, 6] = 0.0
    # Sizing still functions without division by zero
    event = {
        "event_time": int(last[0, 0]) + 2 * MINUTE,
        "decision_at": int(last[0, 0]) + 3 * MINUTE,
        "entry_at": int(last[0, 0]) + 4 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    cand = {"horizon_hours": 12, "target_r": 2.0}
    q, _ = compute_size(last, event, cand, BASE, 1000.0)
    assert q > 0


def test_compute_size_fails_on_min_notional() -> None:
    """compute_size fails if available cash is too low to meet MIN_NOTIONAL (5 USDT)."""
    last, _ = _mock_continuous_path(n_hours=5)
    t0 = int(last[0, 0])
    event = {
        "event_time": t0 + 2 * MINUTE,
        "decision_at": t0 + 3 * MINUTE,
        "entry_at": t0 + 4 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    cand = {"horizon_hours": 12, "target_r": 2.0}
    # Cash only 1 USDT -> cannot purchase minimum 0.001 BTC (30 USDT)
    with pytest.raises(ValueError, match="SIZE_OR_MIN_NOTIONAL"):
        compute_size(last, event, cand, BASE, cash=1.0)


def test_folds_count_and_range() -> None:
    """Folds generator returns exactly 35 monthly folds from 2021-02 to 2023-12."""
    folds = get_folds()
    assert len(folds) == 35
    assert folds[0]["name"] == "2021-02"
    assert folds[-1]["name"] == "2023-12"
    for f in folds:
        assert f["end_ms"] > f["start_ms"]
        assert f["start_ms"] % 86_400_000 == 0


def test_path_eligible_embargo() -> None:
    """path_eligible censors trades within 24h of fold end."""
    fold_end = 1614556800000  # End of Feb 2021
    # 25 hours before fold end: eligible
    t_entry_ok = fold_end - 25 * HOUR
    assert path_eligible(t_entry_ok, fold_end, hours=24) is True

    # 23 hours before fold end: censored
    t_entry_bad = fold_end - 23 * HOUR
    assert path_eligible(t_entry_bad, fold_end, hours=24) is False


def test_replay_account_single_position_constraint() -> None:
    """Concurrent signals while in a position are rejected with POSITION_ACK_OR_COOLDOWN."""
    last, mark = _mock_continuous_path(n_hours=40)
    t0 = int(last[0, 0])
    fold = {
        "fold_index": 0,
        "year": 2021,
        "month": 2,
        "name": "2021-02",
        "start_ms": t0,
        "end_ms": t0 + 40 * HOUR,
    }
    cand = {"id": "test_c", "horizon_hours": 12, "cooldown_hours": 4, "target_r": 2.0}

    # Signal 1 at hour 1
    # Signal 2 at hour 2 (while signal 1 is still open)
    sig1 = {
        "event_id": "sig1",
        "event_time": t0 + 1 * HOUR,
        "decision_at": t0 + 1 * HOUR + MINUTE,
        "entry_at": t0 + 1 * HOUR + 2 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    sig2 = {
        "event_id": "sig2",
        "event_time": t0 + 2 * HOUR,
        "decision_at": t0 + 2 * HOUR + MINUTE,
        "entry_at": t0 + 2 * HOUR + 2 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }

    res = replay_account(last, mark, [], [sig1, sig2], cand, [fold], BASE)
    assert res["total_trades"] == 1
    assert res["fates"].get("POSITION_ACK_OR_COOLDOWN") == 1
    assert res["trades"][0]["event_id"] == "sig1"


def test_replay_account_cooldown_enforcement() -> None:
    """Signals arriving within 4h cooldown after trade exit are rejected."""
    last, mark = _mock_continuous_path(n_hours=100)
    t0 = int(last[0, 0])
    fold = {
        "fold_index": 0,
        "year": 2021,
        "month": 2,
        "name": "2021-02",
        "start_ms": t0,
        "end_ms": t0 + 100 * HOUR,
    }
    cand = {"id": "test_c", "horizon_hours": 12, "cooldown_hours": 4, "target_r": 2.0}

    # Signal 1 at hour 1 (will exit at hour 13 via TIME_CAP, cooldown until hour 17)
    sig1 = {
        "event_id": "sig1",
        "event_time": t0 + 1 * HOUR,
        "decision_at": t0 + 1 * HOUR + MINUTE,
        "entry_at": t0 + 1 * HOUR + 2 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    # Signal 2 at hour 15 (within 4h cooldown)
    sig2 = {
        "event_id": "sig2",
        "event_time": t0 + 15 * HOUR,
        "decision_at": t0 + 15 * HOUR + MINUTE,
        "entry_at": t0 + 15 * HOUR + 2 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }
    # Signal 3 at hour 18 (after cooldown has expired)
    sig3 = {
        "event_id": "sig3",
        "event_time": t0 + 18 * HOUR,
        "decision_at": t0 + 18 * HOUR + MINUTE,
        "entry_at": t0 + 18 * HOUR + 2 * MINUTE,
        "decision_close": 30000.0,
        "atr_hour": 100.0,
        "stop": 29850.0,
        "side": 1,
    }

    res = replay_account(last, mark, [], [sig1, sig2, sig3], cand, [fold], BASE)
    assert res["total_trades"] == 2
    assert res["fates"].get("POSITION_ACK_OR_COOLDOWN") == 1
    accepted_ids = [t["event_id"] for t in res["trades"]]
    assert accepted_ids == ["sig1", "sig3"]


def test_marked_equity_drawdown_calculation() -> None:
    """compute_marked_equity_curve accurately tracks cash curve and max MTM drawdown."""
    _, mark = _mock_continuous_path(n_hours=5)
    t0 = int(mark[0, 0])
    tend = t0 + 5 * HOUR

    # Empty trade list -> constant equity at cash0
    metrics = compute_marked_equity_curve([], mark, t0, tend, cash0=1000.0, cost=BASE)
    assert metrics["ending_equity"] == 1000.0
    assert metrics["min_mark_equity"] == 1000.0
    assert metrics["max_mtm_drawdown_pct"] == 0.0
    assert metrics["occupied_minutes"] == 0
