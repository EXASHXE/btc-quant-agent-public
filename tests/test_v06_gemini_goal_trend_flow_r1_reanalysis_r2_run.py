"""Fixed-code identity, original clock, and causal scoring boundaries."""
from __future__ import annotations

import numpy as np
import pytest

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_audit import audit_episode
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_run import (
    INVALID,
    eligible_events,
    verify_identity,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    MINUTE,
    episode,
    simulate_fold,
)


def test_original_ast_23_candidate_identity_and_exclusion():
    candidates, identity = verify_identity()
    assert len(candidates) == len(identity['candidate_branch_ast_sha256']) == 23
    assert INVALID not in {c['id'] for c in candidates}
    assert identity['excluded']['status'] == 'METHOD_INVALID_EXCLUDED_FROM_PROMOTION'
    assert 'extra' not in identity['entry_clock']


def test_score_end_guard_is_causal_not_realized_exit_filter():
    candidate = {'horizon_hours': 24}
    fold = {'end_ms': 100000000}
    events = [{'entry_at': fold['end_ms'] - 24*3600000 - MINUTE - 1},
              {'entry_at': fold['end_ms'] - 24*3600000}]
    selected, rejected = eligible_events(events, candidate, fold)
    assert selected == events[:1] and rejected == 1


def fixture():
    start = 1612137600000
    data = np.array([[start+i*MINUTE, 50000, 50000, 50000, 50000, 100, 50] for i in range(300)], dtype=float)
    event = {'event_id': 'synthetic', 'side': 1, 'event_time': start, 'decision_at': start+MINUTE,
        'entry_at': start+2*MINUTE, 'stop': 49000, 'decision_close': 50000, 'atr_hour': 2000}
    candidate = {'id': 'synthetic', 'horizon_hours': 4, 'target_R': 2, 'cooldown_hours': 4}
    return data, event, candidate


def test_time_cap_original_open_extra_lag_and_independent_decimal():
    data, event, candidate = fixture()
    data[242, 4] = 50100
    data[242, 2] = 50100
    trade = episode(data, event, candidate, BASE, quantity=.013)
    assert trade['exit_reason'] == 'TIME_CAP'
    assert trade['raw_exit'] == 50000
    assert trade['exit_at'] == event['entry_at'] + 4*3600000
    assert audit_episode(data, event, candidate, BASE, trade)['assertions'] == 'PASS'


def test_decimal_path_detects_forged_realized_exit():
    data, event, candidate = fixture()
    trade = episode(data, event, candidate, BASE, quantity=.013)
    trade['raw_exit'] += 1
    with pytest.raises(AssertionError):
        audit_episode(data, event, candidate, BASE, trade)


def test_cash_before_entry_and_reserve_independent_of_future_close():
    data, event, candidate = fixture()
    fold = {'start_ms': int(data[0,0]), 'end_ms': int(data[-1,0])+MINUTE}
    a = simulate_fold(data, [event], candidate, fold, BASE)
    assert len(a['trades']) == 1
    trade = a['trades'][0]
    assert trade['cash_before_entry'] == pytest.approx(1000)
    assert trade['quantity'] * trade['effective_entry'] + trade['fee_entry'] <= 950
    data[-1, 4] = 100000
    b = simulate_fold(data, [event], candidate, fold, BASE)
    assert a['trades'] == b['trades']
