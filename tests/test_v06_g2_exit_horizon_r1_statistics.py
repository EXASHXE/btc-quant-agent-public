import numpy as np
import pytest

from scripts.strategy_research.g2_exit_horizon_r1.account import path_eligible
from scripts.strategy_research.g2_exit_horizon_r1.statistics import max_t
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.metrics import CALENDAR_START_MS


def registry():
    return [(str(j),[{'entry_at':CALENDAR_START_MS+i*7*86400000,'delta_bps':float((i%5)-2+j*.2)} for i in range(40)]) for j in range(8)]


def test_max_t_deterministic_empty_calendar_blocks():
    a=max_t(registry(),7,draws=100);b=max_t(registry(),7,draws=100)
    assert a==b and a['contrasts'][0]['zero_trade_blocks']>0
    assert a['contrasts'][0]['simultaneous_LCB_bps']<a['contrasts'][0]['mean_delta_bps']


def test_joint_shared_deltas_preserve_shift():
    a=max_t(registry(),14,draws=100)['contrasts']
    assert np.isclose(a[1]['mean_delta_bps']-a[0]['mean_delta_bps'],.2)
    assert np.isclose(a[1]['bootstrap_SE_bps'],a[0]['bootstrap_SE_bps'])


def test_empty_family_not_false_positive():
    assert max_t([(str(i),[]) for i in range(8)],7)['status']=='INSUFFICIENT_SUPPORT'


def test_non_family_rejected():
    with pytest.raises(ValueError):max_t([],7)


def test_fullpath_ack_equality_censored():
    at=1000000000000;end=at+24*3600000+60000
    assert not path_eligible(at,end)
    assert path_eligible(at,end+60000)


def test_invalid_clock_rejected():
    x=registry();x[0][1][0]['entry_at']=CALENDAR_START_MS-1
    with pytest.raises(ValueError):max_t(x,7,draws=10)
