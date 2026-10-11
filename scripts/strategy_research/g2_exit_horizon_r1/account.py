"""Frozen single-position sidecar account; partial cash never reopens signal gate."""
from __future__ import annotations

import math
from collections import Counter

import numpy as np

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    HOUR,
    LOT,
    MIN_NOTIONAL,
    MINUTE,
    _effective,
    _fee,
    _index,
    _proposed,
    _slippage,
)

from .book import PartialIneligible, position


def path_eligible(entry, end, hours=24):
    # Prospective full deadline OPEN plus ACK; equality is censored.
    return entry + hours*HOUR + MINUTE < end


def size(last,event,candidate,cost,cash):
    # Exactly original R3 12h admission, including reservation. Only the exit
    # deadline changes; no horizon-dependent new sizing formula is introduced.
    p=_proposed(last,event,candidate,cost)
    budget=.95*min(cash,1000.)
    raw=p['raw_entry']
    worst=max(p['effective_entry'],_effective(raw+.25*float(event['atr_hour']),1,cost,True))
    fee=worst*cost['fee_bps']/10000
    reserve=1.10*worst*(cost['fee_bps']+.5*cost['spread_bps']+_slippage(cost))/10000
    fund=1.10*raw*8.*int(candidate['horizon_hours'])/10000
    per_unit=worst+fee+reserve+fund
    q=math.floor(budget/per_unit/LOT+1e-10)*LOT
    if q<=0 or q*raw<MIN_NOTIONAL:raise PartialIneligible('SIZE_OR_MIN_NOTIONAL')
    assert q*p['effective_entry']+_fee(p['effective_entry'],q,cost)<=budget+1e-8
    return q,{'budget':budget,'per_unit':per_unit,'reserved_notional':q*worst,
              'exit_cost_reserve':q*reserve,'funding_reserve':q*fund}


def mark_curve(trades,mark,start,end,cash0,cost):
    first=_index(mark,start);last=_index(mark,end-MINUTE)
    close_clocks=mark[first:last+1,0]+MINUTE-1
    values=np.full(len(close_clocks),cash0,dtype=float)
    peak_exposure=0.;breaches=0;occupied=0;cash=cash0;cursor=0
    for t in trades:
        ie=_index(mark,t['entry_at'])-first
        assert ie>=cursor and t['exit_ack_at']<end
        values[cursor:ie]=cash
        final=_index(mark,t['exit_ack_at']//MINUTE*MINUTE)-first
        for i in range(ie,final+1):
            clock=int(close_clocks[i]);settled=cash+sum(float(j['cash_delta']) for j in t['journal'] if j['timestamp']<=clock)
            remaining=t['quantity']-sum(x['quantity'] for x in t['tiers'] if x['exit_at']<=clock)
            assert remaining>=-1e-10
            pending=sum(t['side']*(x['effective_exit']-t['effective_entry'])*x['quantity'] for x in t['tiers'] if x['exit_at']<=clock<x['exit_ack_at'])
            if remaining>1e-10:
                raw=float(mark[first+i,4]);liq=_effective(raw,t['side'],cost,False)
                value=settled+pending+t['side']*(liq-t['effective_entry'])*remaining-_fee(liq,remaining,cost)
                occupied+=1;ratio=raw*remaining/value
                peak_exposure=max(peak_exposure,ratio);breaches+=ratio>1+1e-9
            else:value=settled+pending
            if value<=0:raise ValueError('Nonpositive marked account equity')
            values[i]=value
        cash+=float(t['net_after_funding_usdt'])
        assert abs(values[final]-cash)<1e-7
        cursor=final+1
    values[cursor:]=cash
    peaks=np.maximum.accumulate(np.r_[cash0,values])
    return {'curve':np.column_stack((close_clocks,values)), 'ending_equity':cash,
            'min_mark_equity':float(np.min(values)),
            'max_mtm_drawdown_pct':float(np.max((peaks-np.r_[cash0,values])/peaks)*100),
            'max_exposure_ratio':peak_exposure,'exposure_above_1x_minutes':int(breaches),
            'occupied_minutes':occupied,'occupancy_fraction':occupied/len(values)}


def replay(last,mark,rates,signals,candidate,fold,cost,scheme,cash0):
    if scheme not in ('H1','H2','E1','E2'):
        raise ValueError('Legacy E0 must use inherited exact study, never new curve arithmetic')
    cash=cash0;next_allowed=fold['start_ms'];trades=[];fates=Counter();rejected=[]
    for e in sorted(signals,key=lambda x:(x['entry_at'],x['event_id'])):
        if e['entry_at']<next_allowed:
            fates['POSITION_ACK_OR_COOLDOWN']+=1;rejected.append({'event_id':e['event_id'],'reason':'POSITION_ACK_OR_COOLDOWN'});continue
        hours={'H1':18,'H2':24}.get(scheme,12)
        if not path_eligible(e['entry_at'],fold['end_ms'],hours):
            fates['PROSPECTIVE_FOLD_CENSOR']+=1;rejected.append({'event_id':e['event_id'],'reason':'PROSPECTIVE_FOLD_CENSOR'});continue
        try:q,reserve=size(last,e,candidate,cost,cash)
        except ValueError as exc:
            expected=('late entry breached quarter-hour-ATR gap veto', 'Stop is on wrong side of entry', 'Effective stop risk is nonpositive')
            if not isinstance(exc,PartialIneligible) and str(exc) not in expected:
                raise
            reason='ENTRY_OR_SIZE_REJECTED';fates[reason]+=1;rejected.append({'event_id':e['event_id'],'reason':reason,'detail':str(exc)});continue
        try:t=position(last,mark,rates,e,candidate,cost,scheme,q)
        except PartialIneligible as exc:
            fates['INELIGIBLE_PARTIAL_SIZE']+=1;rejected.append({'event_id':e['event_id'],'reason':'INELIGIBLE_PARTIAL_SIZE','detail':str(exc)});continue
        if t['exit_ack_at']>=fold['end_ms']:raise ValueError('Full path admitted but ACK leaked fold')
        assert abs(sum(float(j['cash_delta']) for j in t['journal'])-float(t['net_after_funding_usdt']))<1e-7
        after=cash+float(t['net_after_funding_usdt'])
        if after<=0:raise ValueError('Nonpositive closing cash')
        t.update({'cash_before_entry':cash,'cash_after_ack':after,'reserve':reserve})
        trades.append(t);cash=after;fates['FILLED']+=1
        next_allowed=max(t['exit_ack_at'],t['exit_at']+int(candidate.get('cooldown_hours',4))*HOUR)
    account=mark_curve(trades,mark,fold['start_ms'],fold['end_ms'],cash0,cost)
    assert abs(account['ending_equity']-cash)<1e-7
    return {'trades':trades,'fates':dict(fates),'skipped_event_ids':rejected,**account}
