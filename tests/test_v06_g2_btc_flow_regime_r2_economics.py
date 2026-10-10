"""Literal promotion boundaries, block inference and inherited fee/PIT semantics."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from scripts.strategy_research.g2_btc_empirical_fast_r1 import replay
from scripts.strategy_research.g2_btc_flow_regime_r2 import metrics

ROSTER=json.loads((Path(__file__).resolve().parents[1]/'evidence/v0.6/b_line/g2_btc_flow_regime_r2/FROZEN_R2_ROSTER.json').read_text())


def summary(stage='DEVELOPMENT'):
    years=[{'year':2021,'trades':25,'represented_months':3,'mean_net_bps':10},
           {'year':2022,'trades':25,'represented_months':3,'mean_net_bps':10},
           {'year':2023,'trades':0,'represented_months':0,'mean_net_bps':None}]
    if stage=='VALIDATION':
        years=[{'year':2024,'trades':15,'represented_months':2,'mean_net_bps':20},
               {'year':2025,'trades':15,'represented_months':2,'mean_net_bps':-10}]
    return {'cost_case':'STRESS','trades':50 if stage=='DEVELOPMENT' else 30,'years':years,
        'equal_year_mean_net_bps':10,'equal_year_mean_incremental_bps':1,
        'profit_factor':1.01 if stage=='DEVELOPMENT' else 1.05,'max_close_and_MTM_DD_pct':15,
        'weekly_uncertainty':{'one_sided_net_LCB_bps':-100}}


def test_development_does_not_secretly_require_positive_ci_or_third_active_year():
    assert metrics.decide(summary(),'DEVELOPMENT',ROSTER)==[]


@pytest.mark.parametrize('key,value,expected',[
    ('trades',49,'TRADE_SUPPORT'),('profit_factor',1.0,'NET_PROFIT_FACTOR'),
    ('equal_year_mean_net_bps',0,'NONPOSITIVE_EQUAL_YEAR_NET'),
    ('equal_year_mean_incremental_bps',0,'NONPOSITIVE_PAIRED_INCREMENT'),
    ('max_close_and_MTM_DD_pct',15.00001,'ACCOUNT_DRAWDOWN')])
def test_development_literal_failure_boundaries(key,value,expected):
    s=summary();s[key]=value
    assert expected in metrics.decide(s,'DEVELOPMENT',ROSTER)


def test_validation_exact_pf_and_year_floor_are_inclusive():
    assert metrics.decide(summary('VALIDATION'),'VALIDATION',ROSTER)==[]


def test_validation_under_minus10_cannot_inherit_positive_other_year():
    s=summary('VALIDATION');s['years'][1]['mean_net_bps']=-10.0001
    assert 'YEAR_FLOOR' in metrics.decide(s,'VALIDATION',ROSTER)


def test_equal_year_bootstrap_ignores_trade_count_imbalance():
    folds=[{'id':f'{y}-02','year':y,'start_ms':0,'end_ms':28*86400000} for y in [2021,2022]]
    trades=[{'fold':f'{y}-02','entry_at':k*86400000,'net_bps':val,
             'incremental_vs_balanced_bps':1} for y,val in [(2021,10),(2022,30)] for k in range(28)]
    trades.extend([dict(t) for t in trades if t['fold']=='2021-02'])
    a=metrics.block_uncertainty(trades,folds,ROSTER['inference'],'DEVELOPMENT')
    assert a['equal_year_net_bps']==20
    assert a==metrics.block_uncertainty(trades,folds,ROSTER['inference'],'DEVELOPMENT')
    assert a['trial_count']==6 and a['one_sided_q']==pytest.approx(.05/6)


def test_zero_trade_year_has_no_invented_zero_or_positive_bound():
    a=metrics.block_uncertainty([],[],ROSTER['inference'],'VALIDATION')
    assert a['equal_year_net_bps'] is None and a['one_sided_net_LCB_bps'] is None


def test_missing_first_year_does_not_change_shared_second_year_draws():
    folds=[{'id':f'{y}-02','year':y,'start_ms':0,'end_ms':28*86400000} for y in [2021,2022]]
    active=[{'fold':'2022-02','entry_at':k*86400000,'net_bps':k*10.,
             'incremental_vs_balanced_bps':k*5.} for k in range(28)]
    zero=[dict(t,fold='2021-02',net_bps=0.,incremental_vs_balanced_bps=0.) for t in active]
    paired=metrics.block_uncertainty(active+zero,folds,ROSTER['inference'],'DEVELOPMENT')
    lone=metrics.block_uncertainty(active,folds,ROSTER['inference'],'DEVELOPMENT')
    assert lone['net_ci95']==pytest.approx([2*v for v in paired['net_ci95']])
    assert lone['one_sided_net_LCB_bps']==pytest.approx(2*paired['one_sided_net_LCB_bps'])


def toy():
    data=np.zeros((300,6));data[:,0]=np.arange(300)*60000;data[:,1:5]=1000.;data[:,5]=1
    event={'event_time':60000,'decision_at':120000,'entry_at':180000,'side':1,
           'stop':980.,'decision_close':1000.,'atr_hour':100.,'event_id':'invented'}
    candidate={'id':'FLOW','family':'FLOW_CONFIRMED_TREND','horizon_hours':4,'target_R':2}
    return data,event,candidate


def test_inherited_native_fees_once_plus_embedded_drag_once():
    data,event,candidate=toy()
    t=replay.episode(data,event,candidate,ROSTER['execution']['costs']['BASE'])
    assert t['fee_usdt']==pytest.approx(1.2)
    assert t['execution_drag_usdt']==pytest.approx(1.)
    assert t['net_bps']==pytest.approx(-22.)
    assert t['exit_ack_at']>t['exit_at']


def test_inherited_stop_first_and_closed_bar_entry_delay():
    data,event,candidate=toy();data[3,2:4]=[1060,970]
    t=replay.episode(data,event,candidate,ROSTER['execution']['costs']['STRESS'])
    assert t['exit_reason']=='STOP' and t['raw_exit']==980.
    event['entry_at']=event['decision_at']
    with pytest.raises(ValueError,match='delay'):
        replay.episode(data,event,candidate,ROSTER['execution']['costs']['STRESS'])
