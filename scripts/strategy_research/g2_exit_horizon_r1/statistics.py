"""Frozen descriptive metrics and simultaneous eight-contrast calendar bootstrap."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

import numpy as np

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.metrics import (
    CALENDAR_END_MS,
    CALENDAR_START_MS,
    calculate_candidate_metrics,
)

CONTRASTS = (('H1','E0'),('H2','E0'),('E1','E0'),('E2','E1'))


def mean(values):
    return float(np.mean(values)) if values else None


def fee_stress(t,d):
    tiers=t.get('tiers',[{'effective_exit':t['effective_exit'],'quantity':t['quantity']}])
    charged=t['effective_entry']*t['quantity']+sum(x['effective_exit']*x['quantity'] for x in tiers)
    return float(t['net_after_funding_bps'])-d*.5*charged/t['entry_notional']


def descriptive(trades,cost,curve=None,monthly=None):
    values=[{**t,'net_usdt':float(t['net_after_funding_usdt']),
             'net_bps':float(t['net_after_funding_bps'])} for t in trades]
    result=calculate_candidate_metrics(values,cost,
        minute_equity_curve=[1000.,*curve[:,1].tolist()] if curve is not None else None)
    risk=[t['net_usdt']/(t['quantity']*t.get('initial_risk',t['side']*(t['effective_entry']-t['stop']))) for t in values]
    result.update({'mean_net_R':mean(risk),'median_net_R':float(np.median(risk)) if risk else None,
        'funding_signed_usdt':sum(float(t['funding_cash_usdt']) for t in trades),
        'funding_events':sum(len(t['funding_settlements']) for t in trades),
        'funding_debits_usdt':sum(-float(x['signed_cash_usdt']) for t in trades for x in t['funding_settlements'] if float(x['signed_cash_usdt'])<0),
        'funding_credits_usdt':sum(float(x['signed_cash_usdt']) for t in trades for x in t['funding_settlements'] if float(x['signed_cash_usdt'])>0),
        'partial_trade_count':sum(len(t.get('tiers',[]))>1 for t in trades),
        'mean_weighted_exit_age_minutes':mean([t.get('weighted_exit_age_minutes',t['duration_minutes']) for t in trades]),
        'touch_no_fill_count':sum(t.get('touch_no_fill_count',0) for t in trades),
        'fee_entry_usdt':sum(t['fee_entry'] for t in trades),
        'fee_exit_usdt':sum(t['fee_exit'] for t in trades),
        'exit_tier_reason_counts':dict(Counter(x['reason'] for t in trades for x in t.get('tiers',[{'reason':t['exit_reason']}]))),
        'additional_per_tier_roundtrip_fee_sensitivity_mean_bps':{str(d):mean([fee_stress(t,d) for t in trades]) for d in (-10,-5,-2,2,5,10)},
        'PAUSE_control_bps':0.,'matched_balanced_mean_bps':mean([t['control_net_bps'] for t in trades if t.get('control_net_bps') is not None]),
        'matched_balanced_qualified_n':sum(t.get('control_net_bps') is not None for t in trades)})
    counts=result['exit_reasons'];n=len(trades)
    result['exit_reason_shares']={k:v/n for k,v in counts.items()} if n else {}
    result['side']={}
    for side,label in ((1,'LONG'),(-1,'SHORT')):
        st=[t for t in values if t['side']==side]
        result['side'][label]={'n':len(st),'mean_net_bps':mean([t['net_bps'] for t in st]),
            'net_cash_usdt':sum(t['net_usdt'] for t in st),
            'account_start_normalized_pnl_pct':sum(t['net_usdt'] for t in st)/10,
            'basis':'conditional attribution; no separately funded side strategy'}
    for y,row in result['yearly_breakdown'].items():
        st=[t for t in values if datetime.fromtimestamp(t['entry_at']/1000,UTC).year==int(y)]
        row.update({'gross_mean_bps':mean([t['gross_bps'] for t in st]),
                    'funding_usdt':sum(float(t['funding_cash_usdt']) for t in st),
                    'fee_usdt':sum(t['fee_entry']+t['fee_exit'] for t in st)})
        if monthly is not None:
            months=[m for m in monthly if m['year']==int(y)]
            if months:row['cash_return_pct']=100*(months[-1]['ending_cash']/months[0]['starting_cash']-1)
    if curve is not None:
        result.update({'ending_cash_usdt':float(curve[-1,1]),'cash_return_pct':100*(float(curve[-1,1])/1000-1),
                       'min_mark_equity_usdt':float(np.min(curve[:,1]))})
    return result


def max_t(registry,block_days,*,draws=10000,seed=42):
    """Shared UTC draws including empty blocks; centered two-sided max-|T|.

    Event-weighted ratio means; bootstrap SD is the frozen plug-in standard
    error for each contrast. No claim of IID trades or selection adjustment56.
    """
    if len(registry)!=8 or block_days not in (7,14):raise ValueError('Exact eight contrast calendar family required')
    duration=block_days*86400000
    blocks=(CALENDAR_END_MS-CALENDAR_START_MS+duration-1)//duration
    sums=np.zeros((blocks,8));counts=np.zeros((blocks,8),dtype=int)
    for j,(_,rows) in enumerate(registry):
        for row in rows:
            at=int(row['entry_at']);value=float(row['delta_bps'])
            if not CALENDAR_START_MS<=at<CALENDAR_END_MS or not np.isfinite(value):raise ValueError('Invalid paired clock/value')
            i=(at-CALENDAR_START_MS)//duration;sums[i,j]+=value;counts[i,j]+=1
    n=counts.sum(axis=0)
    if np.any(n==0):return {'status':'INSUFFICIENT_SUPPORT','block_days':block_days,'empty_contrasts':[registry[j][0] for j in np.where(n==0)[0]]}
    center=sums.sum(axis=0)/n
    sample=np.random.default_rng(seed).integers(0,blocks,size=(draws,blocks))
    ns=counts[sample].sum(axis=1);ss=sums[sample].sum(axis=1)
    valid=np.all(ns>0,axis=1);estimate=ss[valid]/ns[valid]
    if len(estimate)<draws*.99:return {'status':'INSUFFICIENT_SUPPORT','block_days':block_days,'valid_draws':len(estimate)}
    se=estimate.std(axis=0,ddof=1)
    if np.any(se<=1e-12):return {'status':'INSUFFICIENT_SUPPORT','block_days':block_days,'degenerate_contrasts':[registry[j][0] for j in np.where(se<=1e-12)[0]]}
    null_t=(estimate-center)/se
    critical=float(np.quantile(np.max(np.abs(null_t),axis=1),.95))
    out=[]
    for j,(name,_) in enumerate(registry):
        out.append({'contrast':name,'qualified_n':int(n[j]),'mean_delta_bps':float(center[j]),
            'bootstrap_SE_bps':float(se[j]),'simultaneous_LCB_bps':float(center[j]-critical*se[j]),
            'simultaneous_UCB_bps':float(center[j]+critical*se[j]),
            'nonempty_calendar_blocks':int(np.count_nonzero(counts[:,j])),
            'total_calendar_blocks':blocks,'zero_trade_blocks':int(np.count_nonzero(counts[:,j]==0))})
    return {'status':'MEASURED_CONDITIONAL_ON_EXPOSED_SELECTED_LEADS','method':'centered two-sided max-|T|; fixed bootstrap SD studentizer',
        'block_days':block_days,'draws':draws,'valid_joint_draws':int(valid.sum()),'seed':seed,
        'critical_95_maxT':critical,'contrasts':out,'joint56':'NOT_RECONSTRUCTED; prior48 outcomes exposed; no Alpha inference'}
