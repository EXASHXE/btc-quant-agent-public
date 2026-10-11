"""Synthetic full-account gates and Mark/ACK conservation."""
import subprocess
import sys

import numpy as np
import pytest

from scripts.strategy_research.g2_exit_horizon_r1.account import replay
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import BASE


def fixture():
    a=np.column_stack((np.arange(1500)*60000,np.full((1500,4),100.)))
    e={'event_time':0,'decision_at':60000,'entry_at':120000,'decision_close':100.,'atr_hour':20.,'side':1,'stop':90.,'event_id':'synthetic_account'}
    c={'id':'W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H','horizon_hours':12,'target_R':2.,'cooldown_hours':6}
    return a,a.copy(),e,c,{'start_ms':0,'end_ms':1500*60000}


def test_full_mark_cash_and_month_end_conservation():
    a,m,e,c,f=fixture();b=replay(a,m,[],[e],c,f,BASE,'H1',1000.)
    assert len(b['trades'])==1
    assert np.isclose(b['ending_equity'],b['curve'][-1,1])
    assert b['occupied_minutes']==18*60 and b['occupancy_fraction']>0


def test_partial_cash_does_not_reopen_position_gate():
    a,m,e,c,f=fixture();a[3,2]=112.
    second={**e,'event_id':'synthetic_second','event_time':240000,'decision_at':300000,'entry_at':360000}
    b=replay(a,m,[],[e,second],c,f,BASE,'E1',1000.)
    assert len(b['trades'])==1 and len(b['trades'][0]['tiers'])==2
    assert b['fates']['POSITION_ACK_OR_COOLDOWN']==1


def test_availability_failure_not_silent_rejection():
    a,m,e,c,f=fixture();e['decision_at']=0
    with pytest.raises(ValueError,match='Availability'):replay(a,m,[],[e],c,f,BASE,'E1',1000.)


def test_quarter_atr_gap_remains_expected_rejection():
    a,m,e,c,f=fixture();a[2,1:]=106.
    b=replay(a,m,[],[e],c,f,BASE,'E1',1000.)
    assert b['fates']['ENTRY_OR_SIZE_REJECTED']==1 and b['ending_equity']==1000.


def test_e0_cannot_use_new_curve_arithmetic():
    a,m,e,c,f=fixture()
    with pytest.raises(ValueError,match='Legacy E0'):replay(a,m,[],[e],c,f,BASE,'E0',1000.)


def test_optimized_source_gate_before_any_source_read():
    p=subprocess.run([sys.executable,'-O','-c','from scripts.strategy_research.g2_exit_horizon_r1.sources import load; load()'],capture_output=True,text=True,check=False)
    assert p.returncode!=0 and 'Optimized Python forbidden' in p.stderr
