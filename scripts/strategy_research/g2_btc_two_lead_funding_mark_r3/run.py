"""Frozen source admission then one two-lead observed-Funding/Mark study."""
from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.metrics import (
    block_bootstrap,
    calculate_candidate_metrics,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_controls import (
    matched_control,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_run import (
    canonical,
    eligible_events,
    verify_identity,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    STRESS,
    simulate_fold,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.signals import generate_wave_signals
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.sources import get_monthly_folds

from .economics import funded_fold, funding_overlay, mark_account_curve
from .sources import (
    SCRATCH,
    _archive_csv,
    load_funding_month,
    load_month,
    source_plan,
    verify_funding_continuity,
)

ROOT = Path(__file__).resolve().parents[3]
START = 'd2477c1aaff601e0740a6899e60d85224c75a4dc'
IDS = ('W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H', 'W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H')
GRADE = 'COST_PROXY_LAST_TRADE_PLUS_OBSERVED_FUNDING_AND_MARK_DEV_ONLY'
EP = ROOT / 'evidence/v0.6/b_line/g2_btc_two_lead_funding_mark_r3'
OLD_EP = ROOT / 'evidence/v0.6/b_line/g2_gemini_goal_trend_flow_r1'


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_code(code_sha):
    parent = subprocess.check_output(['git','rev-parse',code_sha+'^'],cwd=ROOT,text=True).strip()
    if parent != START:
        raise ValueError('First frozen R3 code must directly parent exact R2 start')
    for prefix in ('scripts/strategy_research/g2_btc_two_lead_funding_mark_r3',
                   'scripts/strategy_research/g2_gemini_goal_trend_flow_r1'):
        paths = subprocess.check_output(['git','ls-tree','-r','--name-only',code_sha,'--',prefix],cwd=ROOT,text=True).splitlines()
        for path in paths:
            if (ROOT/path).read_bytes() != subprocess.check_output(['git','show',code_sha+':'+path],cwd=ROOT):
                raise ValueError('Frozen implementation bytes differ: '+path)
    candidates, identity = verify_identity()
    selected = [c for c in candidates if c['id'] in IDS]
    assert {c['id'] for c in selected} == set(IDS)
    return selected, identity


def failure_provenance(year, month, kind, exception):
    plan = source_plan(year,month,kind)
    files = {}
    for p in (SCRATCH/(kind+'-'+plan['zip_name']),SCRATCH/(kind+'-'+plan['zip_name']+'.CHECKSUM')):
        if p.exists() and not p.is_symlink():
            files[p.name] = {'bytes':p.stat().st_size,'sha256':sha(p)}
        headers = p.with_suffix(p.suffix+'.headers')
        if headers.exists() and not headers.is_symlink():
            files[headers.name] = {'text':headers.read_text(),'sha256':sha(headers)}
    diagnostic = None
    archive=SCRATCH/(kind+'-'+plan['zip_name']);check=SCRATCH/(kind+'-'+plan['zip_name']+'.CHECKSUM')
    if archive.exists() and check.exists() and not archive.is_symlink() and not check.is_symlink():
        try:
            body, proof=_archive_csv(archive.read_bytes(),check.read_bytes(),plan)
            diagnostic={'archive_authentication':proof}
            if kind in ('last','mark'):
                rows=list(csv.reader(io.StringIO(body.decode('utf-8-sig'))))
                clocks=[int(row[0]) for row in rows if row and row[0].isascii() and row[0].isdecimal()]
                start=int(datetime(year,month,1,tzinfo=UTC).timestamp()*1000)
                days=calendar.monthrange(year,month)[1]
                expected=set(range(start,start+days*86400000,60000));observed=set(clocks)
                diagnostic.update({'observed_rows':len(clocks),'expected_rows':days*1440,
                    'missing_minute_count':len(expected-observed),'first_missing_utc_ms':sorted(expected-observed)[:12],
                    'duplicates':len(clocks)-len(observed),'out_of_scope_minute_count':len(observed-expected)})
        except (ValueError,OSError):
            diagnostic={'independent_archive_authentication':'FAILED'}
    return {'year':year,'month':month,'kind':kind,'plan':plan,'diagnostic':diagnostic,'failure':str(exception),
            'exception':type(exception).__name__,'task_owned_source_files':files}


def acquire():
    arrays = {'last':{},'mark':{}}; funding = {}; receipt = {'scientific_grade':GRADE,'successful_sources':[],'blockers':[]}
    for year in range(2021,2024):
        for month in range(1,13):
            for kind in ('last','mark','funding'):
                try:
                    if kind == 'funding':
                        data, row = load_funding_month(year,month,allow_download=True)
                        row['continuity'] = verify_funding_continuity(data,year,month)
                        funding[year,month] = data
                    else:
                        data, row = load_month(year,month,kind,allow_download=True)
                        arrays[kind][year,month] = data
                    row.update({'year':year,'month':month,'kind':kind})
                    receipt['successful_sources'].append(row)
                    print(f'SOURCE {kind} {year}-{month:02d} {len(data)} PASS',flush=True)
                except (ValueError,OSError) as exc:
                    receipt['blockers'].append(failure_provenance(year,month,kind,exc))
                    print(f'SOURCE {kind} {year}-{month:02d} BLOCKED {str(exc)[:220]}',flush=True)
                dump(SCRATCH/'R3_SOURCE_ADMISSION_RESULTS.json',receipt)
    if not receipt['blockers']:
        flat = [e for key in sorted(funding) for e in funding[key]]
        clocks = [e['settlement_at'] for e in flat]
        if clocks != sorted(set(clocks)):
            receipt['blockers'].append({'kind':'funding','failure':'Cross-month duplicate/unordered settlement'})
        for left,right in pairwise(flat):
            if (right.get('interval_hours') is not None
                    and abs((right['settlement_at']-left['settlement_at'])/3600000-float(right['interval_hours']))>60/3600):
                    receipt['blockers'].append({'kind':'funding','failure':'Cross-month observed cadence inconsistency',
                        'left_ms':left['settlement_at'],'right_ms':right['settlement_at']})
    receipt['last_complete_months'] = len(arrays['last'])
    receipt['mark_complete_months'] = len(arrays['mark'])
    receipt['funding_complete_months'] = len(funding)
    receipt['source_manifest_sha256'] = hashlib.sha256(canonical(receipt['successful_sources'])).hexdigest()
    dump(SCRATCH/'R3_SOURCE_ADMISSION_RESULTS.json',receipt)
    return arrays,funding,receipt


def adjusted_trade(trade, overlay):
    updated = {**trade,'funding_settlements':overlay['settlements'],'funding_cash_usdt':overlay['funding_cash_usdt'],
               'pre_funding_net_usdt':trade['net_usdt'],'pre_funding_net_bps':trade['net_bps']}
    return updated


def metrics(trades,curve,cost):
    values = [{**t,'net_usdt':t['net_usdt']+float(t.get('funding_cash_usdt',0)),
               'net_bps':t['net_bps']+10000*float(t.get('funding_cash_usdt',0))/t['entry_notional']} for t in trades]
    result = calculate_candidate_metrics(values,cost,minute_equity_curve=[1000.,*curve[:,1].tolist()])
    result.update({'scientific_grade':GRADE,'ending_usdt':float(curve[-1,1]),
        'cash_return_pct':100*(float(curve[-1,1])/1000-1),'funding_signed_usdt':sum(float(t.get('funding_cash_usdt',0)) for t in trades),
        'funding_debits_usdt':sum(-float(s['signed_cash_usdt']) for t in trades for s in t.get('funding_settlements',[]) if float(s['signed_cash_usdt'])<0),
        'funding_credits_usdt':sum(float(s['signed_cash_usdt']) for t in trades for s in t.get('funding_settlements',[]) if float(s['signed_cash_usdt'])>0),
        'settlement_attributions':sum(len(t.get('funding_settlements',[])) for t in trades),
        'no_settlement_trades':sum(not t.get('funding_settlements') for t in trades),
        'additional_roundtrip_drag_mean_net_bps':{str(d):result['mean_net_bps']-d if trades else None for d in (-10,-5,-2,2,5,10)},
        'descriptive_gross_break_even_friction_bps':result['mean_gross_bps']+float(np.mean([10000*float(t.get('funding_cash_usdt',0))/t['entry_notional'] for t in trades])) if trades else None,
        'maker_acceptance':'UNPROVEN;additionalcost sensitivities do not claim maker fills',
        'bootstrap_7d':block_bootstrap(values,block_days=7),'bootstrap_14d':block_bootstrap(values,block_days=14)})
    result['side']={}
    for sign,label in ((1,'LONG'),(-1,'SHORT')):
        st=[t for t in values if t['side']==sign]
        sm=calculate_candidate_metrics(st,cost)
        net_r=[t['net_usdt']/(sign*(t['effective_entry']-t['stop'])*t['quantity']) for t in st]
        drawdowns=[]
        for t in st:
            selected_curve=curve[(curve[:,0]>=t['entry_at']-60000)&(curve[:,0]<=t['exit_at']+59999),1]
            if len(selected_curve):
                peaks=np.maximum.accumulate(selected_curve)
                drawdowns.append(float(np.max((peaks-selected_curve)/peaks)*100))
        result['side'][label]={'scientific_grade':GRADE,'n':len(st),'mean_gross_bps':sm['mean_gross_bps'],
            'mean_net_bps':sm['mean_net_bps'],'net_profit_factor':sm['net_profit_factor'],
            'mean_net_R':float(np.mean(net_r)) if net_r else None,
            'max_within_trade_mark_mtm_dd_pct':max(drawdowns,default=None),
            'side_risk_basis':'actualaccountwithintrade conditionalDD;notseparatelyfundedsideportfolio'}
    risk_ratios=[t['net_usdt']/(t['side']*(t['effective_entry']-t['stop'])*t['quantity']) for t in values]
    result['mean_net_R']=float(np.mean(risk_ratios)) if risk_ratios else None
    for y, annual in result['yearly_breakdown'].items():
        selected = [t for t in values if datetime.fromtimestamp(t['entry_at']/1000,UTC).year==int(y)]
        annual.update({'scientific_grade':GRADE,'gross_mean_bps':float(np.mean([t['gross_bps'] for t in selected])),
            'funding_signed_usdt':sum(float(t.get('funding_cash_usdt',0)) for t in selected),
            'long_n':sum(t['side']==1 for t in selected),'short_n':sum(t['side']==-1 for t in selected),
            'net_profit_factor':calculate_candidate_metrics(selected,cost)['net_profit_factor'],
            'mean_net_R':float(np.mean([t['net_usdt']/(t['side']*(t['effective_entry']-t['stop'])*t['quantity']) for t in selected]))})
    return result


def independent_funding_audit(trade,mark,events):
    # Independent Decimal arithmetic and Mark clock lookup, no economics helper.
    q=Decimal(str(trade['quantity']));total=Decimal(0);rows=[]
    for event in events:
        at=event['settlement_at']
        if not trade['entry_at'] <= at < trade['exit_at']:
            continue
        if event.get('mark_price') is not None:
            assert event.get('mark_price_source_proven');price=Decimal(event['mark_price']);close=None
        else:
            ix=int(np.searchsorted(mark[:,0]+59999,at,side='right'))-1
            assert ix>=0;close=int(mark[ix,0])+59999;assert close<=at
            price=Decimal(str(mark[ix,4]))
        rate=Decimal(event['rate']);cash=-Decimal(trade['side'])*q*price*rate;total+=cash
        rows.append({'settlement_at':at,'rate_fraction':str(rate),'rate_bps':str(rate*10000),
                     'asof_mark_close_at':close,'mark':str(price),'independent_signed_cash':str(cash)})
    assert abs(total-Decimal(str(trade['funding_cash_usdt'])))<Decimal('0.00000001')
    return {'candidate':trade['candidate'],'side':trade['side'],'year':datetime.fromtimestamp(trade['entry_at']/1000,UTC).year,
            'event_id':trade['event_id'],'total_funding_cash':str(total),'settlements':rows,'assertions':'PASS'}


def study(candidates,arrays,funding,code_sha,source_receipt):
    old=json.loads((OLD_EP/'REANALYSIS_R2_RESULTS.json').read_text())
    old_sources=json.loads((OLD_EP/'REANALYSIS_R2_SOURCE_RECEIPT.json').read_text())
    expected_sources={(m['year'],m['month']):m for m in old_sources['months']}
    for row in source_receipt['successful_sources']:
        if row['kind']=='last':
            assert row['csv_sha256']==expected_sources[row['year'],row['month']]['csv_sha256'],'True last-trade source revision requires explicit blocker'
    result={'scientific_grade':GRADE,'code_sha':code_sha,'source_sha256':source_receipt['source_manifest_sha256'],
            'original_R2_sha':START,'candidates':{},'automatic_promotions':[],'matched_control_grade':'NONTRADABLE_EVENT_PAIRED',
            'funding_notional_basis':'API source-proven exact settlement Mark if available, otherwise latest completed1mMark close approximation',
            'historical_rate_publication_known_at':'UNKNOWN;rates never affect entrysignals'}
    audit_witnesses={};folds=get_monthly_folds()
    for candidate in candidates:
        cid=candidate['id'];result['candidates'][cid]={'scientific_grade':GRADE,'candidate':candidate,'costs':{}}
        events_by_fold={}
        for fold in folds:
            key=(fold['year'],fold['month']);prev=(fold['prev_year'],fold['prev_month'])
            last=np.vstack([arrays['last'][prev],arrays['last'][key]])
            events=generate_wave_signals(last,cid,fold['embargo_start_ms'],fold['embargo_end_ms'])
            events_by_fold[key]=eligible_events(events,candidate,fold)[0]
        for cost_name,cost in (('BASE',BASE),('STRESS',STRESS)):
            cash_baseline=cash_overlay=cash_funded=1000.;baseline=[];overlay_trades=[];funded_trades=[]
            last_curves=[];mark_curves=[];funded_curves=[];monthly=[];baseline_ledger=bytearray();row_ledgers=[]
            for fold in folds:
                key=(fold['year'],fold['month']);prev=(fold['prev_year'],fold['prev_month'])
                last=np.vstack([arrays['last'][prev],arrays['last'][key]]);mark=np.vstack([arrays['mark'][prev],arrays['mark'][key]])
                rates=[*funding[prev],*funding[key]];signals=events_by_fold[key];lookup={s['event_id']:s for s in signals}
                before_baseline,before_overlay,before_funded=cash_baseline,cash_overlay,cash_funded
                b=simulate_fold(last,signals,candidate,fold,cost,initial_equity=cash_baseline)
                month_overlay=[]
                for tr in b['trades']:
                    ctrl=matched_control(last,lookup[tr['event_id']],candidate,cost,tr)
                    tr['control_net_bps']=ctrl['balanced_net_bps'];tr['paired_increment_bps']=ctrl['paired_increment_bps'];tr['pause_net_bps']=0.
                    baseline_ledger.extend(canonical({'trade':tr,'event':lookup[tr['event_id']],'control':ctrl}))
                    ov=funding_overlay(tr,mark,rates);updated=adjusted_trade(tr,ov)
                    long_f=funding_overlay(ctrl['long'],mark,rates);short_f=funding_overlay(ctrl['short'],mark,rates)
                    control_after=ctrl['balanced_net_bps']+10000*(float(long_f['funding_cash_usdt'])+float(short_f['funding_cash_usdt']))/tr['entry_notional']
                    updated['control_net_bps']=control_after
                    updated['paired_increment_bps']=float(ov['net_after_funding_bps'])-control_after
                    updated['timing_boundary_sensitivity']={f'{a},{z}':funding_overlay(tr,mark,rates,shift_entry_ms=a,shift_exit_ms=z)['funding_cash_usdt'] for a,z in ((-60000,-60000),(60000,60000),(-60000,60000),(60000,-60000))}
                    month_overlay.append(updated)
                    if ov['settlement_count']:
                        witness=(tr['side'],datetime.fromtimestamp(tr['entry_at']/1000,UTC).year)
                        if witness not in audit_witnesses:
                            audit_witnesses[witness]=independent_funding_audit(updated,mark,rates)
                    row_ledgers.append({'trade':updated,'source_sha256':source_receipt['source_manifest_sha256']})
                overlay=mark_account_curve(month_overlay,mark,fold['start_ms'],fold['end_ms'],cash_overlay,cost)
                f= funded_fold(last,mark,rates,signals,candidate,fold,cost,initial_equity=cash_funded)
                for tr in f['trades']:
                    ctrl=matched_control(last,lookup[tr['event_id']],candidate,cost,tr)
                    lf=funding_overlay(ctrl['long'],mark,rates);sf=funding_overlay(ctrl['short'],mark,rates)
                    tr['control_net_bps']=ctrl['balanced_net_bps']+10000*(float(lf['funding_cash_usdt'])+float(sf['funding_cash_usdt']))/tr['entry_notional']
                    tr['paired_increment_bps']=float(tr['net_after_funding_bps'])-tr['control_net_bps']
                cash_baseline=b['ending_equity'];cash_overlay=overlay['ending_equity'];cash_funded=f['ending_equity']
                baseline.extend(b['trades']);overlay_trades.extend(month_overlay);funded_trades.extend(f['trades'])
                last_curves.append(b['minute_equity_curve']);mark_curves.append(overlay['minute_equity_curve']);funded_curves.append(f['minute_equity_curve'])
                monthly.append({'scientific_grade':GRADE,'year':key[0],'month':key[1],
                    'baseline_n':len(b['trades']),'overlay_n':len(month_overlay),'funded_n':len(f['trades']),
                    'baseline_start':before_baseline,'baseline_end':cash_baseline,'overlay_start':before_overlay,'overlay_end':cash_overlay,
                    'funded_start':before_funded,'funded_end':cash_funded,'funding_signed_cash_overlay':sum(float(t['funding_cash_usdt']) for t in month_overlay),
                    'mark_dd_overlay_within_month':overlay['max_mtm_drawdown_pct'],'mark_dd_funded_within_month':f['max_mtm_drawdown_pct'],
                    'funded_event_fates':f['event_fates'],'marked_exposure_ratio':f['max_position_notional_to_marked_equity']})
            baseline_sha=hashlib.sha256(baseline_ledger).hexdigest()
            expected=old['candidates'][cid]['scenarios'][cost_name]
            assert baseline_sha==expected['trade_ledger']['sha256'],'R2 baseline full trade/event/control ledger identity mismatch'
            assert len(baseline)==expected['metrics']['trade_count']
            assert abs(float(np.mean([t['net_bps'] for t in baseline]))-expected['metrics']['mean_net_bps'])<1e-8
            assert hashlib.sha256(np.vstack(last_curves).tobytes()).hexdigest()==expected['minute_equity_ledger']['uncompressed_curve_sha256']
            record={'scientific_grade':GRADE,'R2_baseline_ledger_sha256_matched':baseline_sha,'baseline':expected['metrics'],
                'cash_neutral_same_trade_overlay':metrics(overlay_trades,np.vstack(mark_curves),cost_name),
                'funding_aware_funded_replay':metrics(funded_trades,np.vstack(funded_curves),cost_name),
                'monthly':monthly,'overlay_funded_same_event_ids':[t['event_id'] for t in overlay_trades]==[t['event_id'] for t in funded_trades]}
            # Full records and minute curves stay outside Git.
            ledger_path=SCRATCH/f'{cid}_{cost_name}_full_attribution.jsonl'
            ledger_path.write_bytes(b''.join(canonical(row) for row in row_ledgers))
            record['attribution_ledger']={'path':str(ledger_path),'sha256':sha(ledger_path),'rows':len(row_ledgers)}
            funded_path=SCRATCH/f'{cid}_{cost_name}_funded_full_attribution.jsonl'
            funded_path.write_bytes(b''.join(canonical(t) for t in funded_trades))
            record['funded_attribution_ledger']={'path':str(funded_path),'sha256':sha(funded_path),'rows':len(funded_trades)}
            record['trade_funding_receipts']=[{'event_id':t['event_id'],'side':t['side'],'entry_at':t['entry_at'],
                'exit_at':t['exit_at'],'settlement_count':len(t['funding_settlements']),
                'funding_cash_usdt':t['funding_cash_usdt'],'pre_funding_net_bps':t['net_bps'],
                'after_funding_net_bps':t['net_bps']+10000*float(t['funding_cash_usdt'])/t['entry_notional'],
                'boundary_sensitivity':t.get('timing_boundary_sensitivity')} for t in overlay_trades]
            for view,curve in (('cash_neutral_same_trade_overlay',np.vstack(mark_curves)),('funding_aware_funded_replay',np.vstack(funded_curves))):
                for year,yearrow in record[view]['yearly_breakdown'].items():
                    st=int(datetime(int(year),1,1,tzinfo=UTC).timestamp()*1000)
                    en=int(datetime(int(year)+1,1,1,tzinfo=UTC).timestamp()*1000)
                    yc=curve[(curve[:,0]>=st)&(curve[:,0]<en),1]
                    prefix='overlay' if view=='cash_neutral_same_trade_overlay' else 'funded'
                    ms=[m for m in monthly if m['year']==int(year)]
                    before=ms[0][prefix+'_start'];after=ms[-1][prefix+'_end']
                    peaks=np.maximum.accumulate(np.r_[before,yc])
                    yearrow['mark_mtm_dd_pct']=float(np.max((peaks-np.r_[before,yc])/peaks)*100)
                    yearrow['cash_return_pct']=100*(after/before-1)
            curves_path=SCRATCH/f'{cid}_{cost_name}_equity.npz'
            np.savez_compressed(curves_path,baseline=np.vstack(last_curves),overlay=np.vstack(mark_curves),funded=np.vstack(funded_curves))
            record['minute_curves']={'path':str(curves_path),'sha256':sha(curves_path)}
            result['candidates'][cid]['costs'][cost_name]=record
            print(f"RESULT {cid} {cost_name} baseline={expected['metrics']['mean_net_bps']:.4f} observedfunding={record['cash_neutral_same_trade_overlay']['mean_net_bps']:.4f} funded={record['funding_aware_funded_replay']['mean_net_bps']:.4f}",flush=True)
    assert len(audit_witnesses)>=5 and {a['year'] for a in audit_witnesses.values()}=={2021,2022,2023}
    result['independent_decimal_funding_events']=list(audit_witnesses.values())
    result['terminal']='TWO_LEAD_REAL_FUNDING_MARK_ECONOMICS_COMPLETE_DEVELOPMENT_ONLY'
    return result


def run(code_sha):
    candidates,identity=verify_code(code_sha)
    if SCRATCH.is_symlink():raise ValueError('Task scratch symlink')
    SCRATCH.mkdir(exist_ok=True)
    if (SCRATCH/'R3_ECONOMIC_RESULTS.json').exists():raise ValueError('Bounded study already completed')
    arrays,funding,receipt=acquire()
    if receipt['blockers']:
        result={'scientific_grade':GRADE,'code_sha':code_sha,'source_sha256':receipt['source_manifest_sha256'],
            'terminal':'MARK_FUNDING_SOURCE_OR_CAUSALITY_BLOCKED','blockers':receipt['blockers'],
            'economic_results':None,'observed_funding_adjusted_profit':None,'Mark_MTM':None,
            'baseline_reference_R2_only':{cid:{cost:json.loads((OLD_EP/'REANALYSIS_R2_RESULTS.json').read_text())['candidates'][cid]['scenarios'][cost]['metrics']['mean_net_bps'] for cost in ('BASE','STRESS')} for cid in IDS},
            'actual_body_access_after_freeze':True,'identity':identity}
    else:
        try:
            result=study(candidates,arrays,funding,code_sha,receipt)
        except (ValueError,AssertionError,OSError) as exc:
            result={'scientific_grade':GRADE,'code_sha':code_sha,'terminal':'MARK_FUNDING_SOURCE_OR_CAUSALITY_BLOCKED',
                'blockers':[{'kind':'account_or_baseline_identity','error':str(exc),'exception':type(exc).__name__}],
                'economic_results':None,'observed_funding_adjusted_profit':None}
    dump(SCRATCH/'R3_ECONOMIC_RESULTS.json',result)
    print(result['terminal'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--code-sha',required=True);run(p.parse_args().code_sha)
