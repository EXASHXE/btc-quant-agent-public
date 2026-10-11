"""Independent stdlib CSV/ZIP/Decimal checks; no production economics calls."""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

import numpy as np

from .sources import GAP, OLD, SCRATCH, guarded


def D(v):
    return Decimal(str(v))


def member(path,sha):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Independent archive SHA mismatch')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.namelist())!=1:raise ValueError('Independent ZIP member failure')
        return z.read(z.namelist()[0]).decode()


def effective(raw,side,cost,entry):
    direction=side if entry else -side
    adverse=(D(cost['spread_bps'])/2+D(cost['slip_bps']))/10000
    value=D(raw)*(1+direction*adverse)
    units=value/D('.1')
    # Same mathematical tick rule, computed independently in Decimal.
    return units.to_integral_value(rounding=ROUND_CEILING if direction>0 else ROUND_FLOOR)*D('.1')


def independent_audit(trades,source):
    ordered=sorted(trades,key=lambda t:(t['entry_at'],t['candidate'],t['scheme'],0 if t['cost']=='STRESS' else 1))
    partial=[t for t in ordered if t['funding_settlements'] and any(x['reason'].startswith('TP1') for x in t['tiers'])]
    chosen={};groups=set()
    for t in partial:
        group=t['candidate'],t['side'],datetime.fromtimestamp(t['entry_at']/1000,UTC).year,t['cost']
        if group not in groups:
            chosen[t['candidate'],t['event_id'],t['scheme'],t['cost']]=t;groups.add(group)
    for sign in (-1,1):
        t=next((t for t in partial if any(sign*D(x['source_rate_fraction'])>0 for x in t['funding_settlements'])),None)
        if t:chosen[t['candidate'],t['event_id'],t['scheme'],t['cost']]=t
    # Actual nearest TP1/Funding example is selected deterministically for
    # auditing only, never as an exit choice or favorable-result filter.
    funding={}
    for ref in source['successful_sources']:
        if ref['kind']!='funding':continue
        name=f"funding-BTCUSDT-fundingRate-{ref['year']}-{ref['month']:02d}.zip"
        text=member(guarded(OLD/name,OLD),ref['zip_sha256'])
        for row in csv.DictReader(io.StringIO(text)):
            at=int(row['calc_time'])
            if at in funding:raise ValueError('Independent duplicate Funding timestamp')
            funding[at]=D(row['last_funding_rate'])
    if len(funding)!=3285:raise ValueError('Independent funding count')
    nearest=None
    for t in partial:
        for tier in t['tiers']:
            if tier['reason'].startswith('TP1'):
                for at in funding:
                    value=(abs(at-tier['exit_at']),at,t['event_id'],tier['exit_at'])
                    if nearest is None or value<nearest[0]:nearest=(value,t)
    if nearest:
        t=nearest[1];chosen[t['candidate'],t['event_id'],t['scheme'],t['cost']]=t
    needed=set()
    for t in chosen.values():
        stages={t['entry_at'],*[x['exit_at'] for x in t['tiers']],*[x['exit_ack_at'] for x in t['tiers']],*[at for at in funding if t['entry_at']<=at<t['exit_at']]}
        for clock in stages:
            needed.add(((clock-59999)//60000)*60000)
            needed.add((clock//60000)*60000)
        needed.update(((at-59999)//60000)*60000 for at in funding if t['entry_at']<=at<t['exit_at'])
    marks={}
    for ref in source['successful_sources']:
        if ref['kind']!='mark':continue
        y,m=ref['year'],ref['month']
        targets={at for at in needed if (datetime.fromtimestamp(at/1000,UTC).year,datetime.fromtimestamp(at/1000,UTC).month)==(y,m)}
        if not targets:continue
        name=f'mark-BTCUSDT-1m-{y}-{m:02d}.zip'
        for row in csv.reader(io.StringIO(member(guarded(OLD/name,OLD),ref['zip_sha256']))):
            if row[0]=='open_time':continue
            at=int(row[0])
            if at in targets:marks[at]=(D(row[4]),int(row[6]),'MONTHLY_AUTHORITY')
    # source carries original DAILY receipts so no unproven replacement value.
    for day in source['daily_receipts']:
        d=day['day'];start=int(datetime.strptime(d,'%Y-%m-%d').replace(tzinfo=UTC).timestamp()*1000)
        if not any(start<=at<start+86400000 and at not in marks for at in needed):continue
        folder=GAP/d;name=f'BTCUSDT-1m-{d}.zip'
        for row in csv.reader(io.StringIO(member(guarded(folder/name,folder),day['daily_parse']['zip_sha256']))):
            if row[0]=='open_time':continue
            at=int(row[0])
            if at in needed:
                if at in marks:raise ValueError('Independent overlapping Mark replacement')
                marks[at]=(D(row[4]),int(row[6]),'DAILY_SHA_AUTHENTICATED')
    if not needed<=set(marks):raise ValueError('Independent required settlement Mark unavailable')
    episodes=[]
    for t in chosen.values():
        cost={'fee_bps':6 if t['cost']=='BASE' else 12,'spread_bps':4 if t['cost']=='BASE' else 8,'slip_bps':3 if t['cost']=='BASE' else 6}
        q=D(t['quantity']);side=D(t['side']);entry=effective(t['raw_entry'],t['side'],cost,True)
        if abs(entry-D(t['effective_entry']))>D('0.000001'):raise ValueError('Independent entry tick mismatch')
        fees=entry*q*D(cost['fee_bps'])/10000;gross=D(0);drag=D(0);tierproof=[]
        for x in t['tiers']:
            qty=D(x['quantity']);exitp=effective(x['raw_exit'],t['side'],cost,False)
            fee=exitp*qty*D(cost['fee_bps'])/10000;fees+=fee
            rawpnl=side*(D(x['raw_exit'])-D(t['raw_entry']))*qty
            execution_drag=side*(entry-D(t['raw_entry'])+D(x['raw_exit'])-exitp)*qty
            gross+=rawpnl;drag+=execution_drag
            if abs(exitp-D(x['effective_exit']))>D('0.000001') or abs(fee-D(x['fee_exit']))>D('0.00000001'):raise ValueError('Independent tier fill/fee mismatch')
            if x['exit_ack_at']<=x['exit_at']:raise ValueError('Independent ACK not causal')
            tierproof.append({'quantity':str(qty),'raw_exit':str(x['raw_exit']),'independent_effective_exit':str(exitp),
                'independent_fee_exit':str(fee),'exit_at':x['exit_at'],'ACK_at':x['exit_ack_at'],'reason':x['reason']})
        if abs(sum(D(x['quantity']) for x in t['tiers'])-q)>D('1e-12'):raise ValueError('Independent inventory mismatch')
        total=D(0);bills=[]
        for at,rate in sorted(funding.items()):
            if not t['entry_at']<=at<t['exit_at']:continue
            openq=q-sum((D(x['quantity']) for x in t['tiers'] if x['exit_at']<=at),D(0))
            stamp=((at-59999)//60000)*60000;price,close,origin=marks[stamp]
            if openq<0 or not close<=at or at-close>=60000:raise ValueError('Independent inventory/as-of failure')
            bill=-side*openq*price*rate;total+=bill
            bills.append({'settlement_at':at,'remaining_quantity':str(openq),'rate_fraction':str(rate),
                'Mark_close_at':close,'Mark_close':str(price),'Mark_source':origin,'signed_cash_usdt':str(bill)})
        net=gross-drag-fees+total
        if abs(total-D(t['funding_cash_usdt']))>D('1e-8') or abs(net-D(t['net_after_funding_usdt']))>D('1e-7'):raise ValueError('Independent net/funding drift')
        if abs(sum(D(j['cash_delta']) for j in t['journal'])-net)>D('1e-7'):raise ValueError('Independent cash journal drift')
        for j in t['journal']:
            if j['kind']=='EXIT_PNL_ACK' and not any(j['timestamp']==x['exit_ack_at'] for x in t['tiers']):raise ValueError('Independent premature cash ACK')
        curve_path=Path(t['curve_path'])
        if curve_path.parent!=SCRATCH or curve_path.is_symlink() or hashlib.sha256(curve_path.read_bytes()).hexdigest()!=t['curve_sha256']:
            raise ValueError('Independent full-account curve identity failure')
        with np.load(curve_path) as archive:curve=archive['curve']
        stageproof=[]
        clocks=sorted({t['entry_at'],*[x['exit_at'] for x in t['tiers']],*[x['exit_ack_at'] for x in t['tiers']],*[x['settlement_at'] for x in bills]})
        for clock in clocks:
            # Independent cash availability and liquidation at actual stage,
            # then compare its minute-close recognition with full account curve.
            def state(at,mark_price,*,t=t,entry=entry,q=q,cost=cost,side=side,bills=bills):
                cash=D(t['cash_before_entry'])-entry*q*D(cost['fee_bps'])/10000
                remain=q;pending=D(0)
                for x in t['tiers']:
                    qty=D(x['quantity']);xp=effective(x['raw_exit'],t['side'],cost,False);pnl=side*(xp-entry)*qty
                    if x['exit_at']<=at:
                        remain-=qty;cash-=xp*qty*D(cost['fee_bps'])/10000
                        if x['exit_ack_at']<=at:cash+=pnl
                        else:pending+=pnl
                cash+=sum((D(b['signed_cash_usdt']) for b in bills if b['settlement_at']<=at),D(0))
                observed=D(t['cash_before_entry'])+sum((D(j['cash_delta']) for j in t['journal'] if j['timestamp']<=at),D(0))
                if abs(cash-observed)>D('1e-7') or remain<D('-1e-12'):raise ValueError('Independent stage cash/inventory divergence')
                remain=max(D(0),remain);liq=effective(mark_price,t['side'],cost,False)
                equity=cash+pending+side*(liq-entry)*remain-liq*remain*D(cost['fee_bps'])/10000
                return cash,remain,equity
            stamp=((clock-59999)//60000)*60000;mp,mc,_=marks[stamp]
            cash,remain,equity=state(clock,mp)
            close=clock//60000*60000+59999;mpc=marks[close-59999][0]
            _cc,_cq,ce=state(close,mpc);ix=int(np.searchsorted(curve[:,0],close))
            if ix>=len(curve) or int(curve[ix,0])!=close or abs(ce-D(curve[ix,1]))>D('1e-6'):
                raise ValueError('Independent stage Mark liquidation curve mismatch')
            stageproof.append({'stage_at':clock,'available_cash':str(cash),'remaining_quantity':str(remain),
                'asof_Mark_close_at':mc,'asof_Mark':str(mp),'equity_including_pending_ACK_receivable':str(equity),
                'minute_close':close,'independent_close_equity':str(ce),'account_curve_equity':str(curve[ix,1]),'status':'PASS'})
        episodes.append({'candidate':t['candidate'],'scheme':t['scheme'],'cost':t['cost'],'event_id':t['event_id'],
            'side':t['side'],'year':datetime.fromtimestamp(t['entry_at']/1000,UTC).year,'quantity':str(q),
            'tiers':tierproof,'settlements':bills,'stage_cash_quantity_Mark_checks':stageproof,'independent_entry_fee':str(entry*q*D(cost['fee_bps'])/10000),
            'independent_price_PnL':str(gross),'independent_execution_drag':str(drag),'independent_all_fees':str(fees),
            'independent_funding_cash':str(total),'independent_net_cash':str(net),'status':'PASS'})
    enough=sum(e['cost']=='STRESS' for e in episodes)>=5 and {e['side'] for e in episodes}=={-1,1} and {2022,2023}<={e['year'] for e in episodes}
    residual=sum(any(b['settlement_at']>=min(x['exit_at'] for x in t['tiers'] if x['reason'].startswith('TP1')) and D(b['quantity'])<D(t['quantity']) for b in t['funding_settlements']) for t in chosen.values())
    rate_signs={1 if D(b['rate_fraction'])>0 else -1 if D(b['rate_fraction'])<0 else 0 for e in episodes for b in e['settlements']}
    enough=enough and residual>0 and {-1,1}<=rate_signs
    return {'status':'PASS' if enough else 'INSUFFICIENT_SUPPORT','support_requirements':'atleast5STRESSfundedpartials, LONG/SHORT2022/23, postTP1residualFunding and positive/negative rates','post_TP1_residual_funding_episodes':residual,'observed_rate_signs':sorted(rate_signs),'method':'independent stdlib CSV/ZIP/Decimal; no production fill/funding/cash helpers',
        'episodes':episodes,'n':len(episodes),'per_cost_n':{c:sum(e['cost']==c for e in episodes) for c in ('STRESS','BASE')},'rate_events':len(funding),
        'actual_TP1_nearest_settlement':{'distance_ms':nearest[0][0],'settlement_at':nearest[0][1],'event_id':nearest[0][2],'TP1_at':nearest[0][3]} if nearest else None,
        'actual_TP1_within_60sec_supported':nearest is not None and nearest[0][0]<=60000,
        'boundary_support_policy':'If no actual TP1within60s, report measured absence and DIAGNOSTIC_INSUFFICIENT_SUPPORT; never retime a real fill',
        'raw_source':'R3/R31 signed public cache only','scratch':str(SCRATCH)}
