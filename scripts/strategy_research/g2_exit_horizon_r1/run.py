"""One frozen source-preserving E0 gate, then eight new exit cells exactly once."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_two_lead_funding_mark_r3 import run as prior
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_run import (
    canonical,
    eligible_events,
    verify_identity,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import BASE, HOUR, STRESS
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.signals import generate_wave_signals
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.sources import get_monthly_folds

from .account import path_eligible, replay
from .book import PartialIneligible, position
from .sources import EP, GAP, R31_EP, ROOT, SCRATCH, load
from .statistics import CONTRASTS, descriptive, max_t, mean

START='990c02b5479b3b14996f90fdbf677cb672ada81e'
IDS=tuple(prior.IDS)
SCHEMES=('E0','H1','H2','E1','E2')


def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def freeze_check(sha):
    if not __debug__:
        raise ValueError("Optimized Python forbidden; inherited assertion gates must remain active")
    if subprocess.check_output(['git','rev-parse',sha+'^'],cwd=ROOT,text=True).strip()!=START:
        raise ValueError('Freeze parent differs exact authorized start')
    paths=subprocess.check_output(['git','ls-tree','-r','--name-only',sha,'--','scripts/strategy_research/g2_exit_horizon_r1','tests/test_v06_g2_exit_horizon_r1_'],cwd=ROOT,text=True).splitlines()
    for p in paths:
        assert (ROOT/p).read_bytes()==subprocess.check_output(['git','show',sha+':'+p],cwd=ROOT),'Frozen implementation mutated'
    contract_path=EP/'EXIT_R1_FROZEN_CONTRACT.json'
    assert contract_path.read_bytes()==subprocess.check_output(['git','show',sha+':'+str(contract_path.relative_to(ROOT))],cwd=ROOT),'Frozen contract mutated'
    contract=json.loads(contract_path.read_text())
    for p,h in contract['frozen_implementation_sha256'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
    for p,h in contract['inherited_sha256'].items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
    configs,_=verify_identity()
    selected=[c for c in configs if c['id'] in IDS]
    assert len(selected)==2 and {c['id'] for c in selected}==set(IDS)
    return selected


def e0_gate(configs,arrays,rates,sha,source):
    original=prior.SCRATCH;prior.SCRATCH=SCRATCH
    try:fresh=prior.study(configs,arrays,rates,sha,source)
    finally:prior.SCRATCH=original
    expected=json.loads((R31_EP/'R31_ECONOMIC_RESULTS.json').read_text())
    receipt=[]
    for cid,c in fresh['candidates'].items():
        for cost,record in c['costs'].items():
            ref=expected['candidates'][cid]['costs'][cost]
            assert record['R2_baseline_ledger_sha256_matched']==ref['R2_baseline_ledger_sha256_matched']
            for field in ('attribution_ledger','funded_attribution_ledger'):
                assert record[field]['sha256']==ref[field]['sha256'],'E0 full source/trade/Funding ledger differs'
            q=Path(ref['minute_curves']['path']);assert q.parent==GAP and not q.is_symlink()
            assert hashlib.sha256(q.read_bytes()).hexdigest()==ref['minute_curves']['sha256']
            hashes={}
            with np.load(record['minute_curves']['path']) as actual,np.load(q) as old:
                for mode in ('baseline','overlay','funded'):
                    assert np.array_equal(actual[mode],old[mode]),'E0 full minute curve differs'
                    hashes[mode]=hashlib.sha256(actual[mode].tobytes()).hexdigest()
            receipt.append({'candidate':cid,'cost':cost,'R2_trade_event_control_sha256':record['R2_baseline_ledger_sha256_matched'],
                'R31_funded_trade_sha256':record['funded_attribution_ledger']['sha256'],
                'curve_uncompressed_sha256':hashes,'status':'EXACT_MATCH'})
    assert len(receipt)==4
    dump(SCRATCH/'E0_EXACT_IDENTITY_RECEIPT.json',receipt)
    print('E0 ALL_FOUR_EXACT ledger and all minute curves',flush=True)
    return fresh


def ledger(name,rows):
    path=SCRATCH/name;raw=b''.join(canonical(t) for t in rows);path.write_bytes(raw)
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'rows':len(rows)}


def matched(last,mark,rates,event,candidate,cost,scheme,q):
    try:
        controls=[position(last,mark,rates,event,candidate,cost,scheme,q,side_override=side) for side in (-1,1)]
    except PartialIneligible:
        return {'qualified':False,'reason':'INELIGIBLE_PARTIAL_CONTROL'}
    return {'qualified':True,'balanced_net_bps':mean([float(t['net_after_funding_bps']) for t in controls]),
            'LONG_net_bps':float(controls[1]['net_after_funding_bps']),'SHORT_net_bps':float(controls[0]['net_after_funding_bps']),
            'grade':'NONTRADABLE_SAME_EVENT_PAIRED_REFERENCE_NOT_POOLED_CASH'}


def e0_orders(base,cache,events,candidate,cost):
    rows=[]
    for old in base:
        dt=datetime.fromtimestamp(old['entry_at']/1000,UTC);key=(dt.year,dt.month)
        last,mark,rates,_=cache[key]
        t=position(last,mark,rates,events[key][old['event_id']],candidate,cost,'E0',old['quantity'])
        for key in ('quantity','exit_at','exit_ack_at','exit_reason','raw_exit','effective_exit'):
            assert t[key]==old[key],'Derived E0 journal clock/price/quantity changed'
        for key in ('net_usdt','funding_cash_usdt','net_after_funding_usdt'):
            assert abs(float(t[key])-float(old[key]))<1e-7,'Derived E0 cash differs'
        t.update({'cash_before_entry':old['cash_before_entry'],'cash_after_ack':old['cash_after_ack'],'grade':'DERIVED_ORDER_JOURNAL_EXACT_EXECUTIONS;reference_trade_bytes_separately_pinned'})
        rows.append(t)
    return rows


def path_features(last,mark,event,base):
    entry=base['entry_at'];risk=base['side']*(base['effective_entry']-base['stop']);side=base['side'];out={}
    for label,a,z in (('before12h',0,12),('12to18h',12,18),('18to24h',18,24)):
        bars=last[(last[:,0]>=entry+a*HOUR)&(last[:,0]<entry+z*HOUR)]
        mb=mark[(mark[:,0]>=entry+a*HOUR)&(mark[:,0]<entry+z*HOUR)]
        assert len(bars)==(z-a)*60 and len(mb)==len(bars)
        favorable=bars[:,2] if side>0 else bars[:,3];adverse=bars[:,3] if side>0 else bars[:,2]
        out[label]={'Last_MFE_R':float(np.max(side*(favorable-base['raw_entry'])/risk)),
                    'Last_MAE_R':float(np.min(side*(adverse-base['raw_entry'])/risk)),
                    'Mark_MFE_R':float(np.max(side*(mb[:,4]-base['raw_entry'])/risk)),
                    'Mark_MAE_R':float(np.min(side*(mb[:,4]-base['raw_entry'])/risk)),
                    'basis':'unconditional24h path after frozen entry; may be after actual flat, not entry predictor'}
    return out


def execution_sensitivity(last,mark,rates,event,candidate,cost,q):
    out={}
    for scheme in ('E0','E1','E2'):
        for mode in ('through','delay','unfilled'):
            try:t=position(last,mark,rates,event,candidate,cost,scheme,q,fill_mode=mode)
            except PartialIneligible:out[scheme+'/'+mode]={'ineligible':True};continue
            out[scheme+'/'+mode]={'net_bps':float(t['net_after_funding_bps']),'fees_usdt':t['fee_entry']+t['fee_exit'],
                'exit_at':t['exit_at'],'touch_no_fill':t['touch_no_fill_count'],'tiers':t['tiers']}
    return out


def paired_cell(base,events,cache,candidate,cost_name,cost):
    rows=[];censored=[];ineligible=[];accepted=len(base)
    caps=sum(t['exit_reason']=='TIME_CAP' for t in base);missing_caps=0
    for old in base:
        dt=datetime.fromtimestamp(old['entry_at']/1000,UTC);key=(dt.year,dt.month);last,mark,rates,fold=cache[key]
        if not path_eligible(old['entry_at'],fold['end_ms']):
            censored.append(old['event_id']);missing_caps+=old['exit_reason']=='TIME_CAP';continue
        e=events[key][old['event_id']]
        record={'candidate':candidate['id'],'cost':cost_name,'event_id':old['event_id'],
            'entry_at':old['entry_at'],'side':old['side'],'baseline_time_cap':old['exit_reason']=='TIME_CAP',
            'path24h':path_features(last,mark,e,old),'cells':{},'execution_sensitivity':{}}
        for scheme in SCHEMES:
            try:t=position(last,mark,rates,e,candidate,cost,scheme,old['quantity'])
            except PartialIneligible:
                ineligible.append({'event_id':old['event_id'],'scheme':scheme,'reason':'INELIGIBLE_PARTIAL_SIZE'});continue
            if scheme=='E0':
                assert t['exit_at']==old['exit_at'] and abs(float(t['net_after_funding_usdt'])-float(old['net_after_funding_usdt']))<1e-7
            control=matched(last,mark,rates,e,candidate,cost,scheme,old['quantity'])
            t['control_net_bps']=control.get('balanced_net_bps');t['matched_control']=control
            record['cells'][scheme]=t
        record['execution_sensitivity']=execution_sensitivity(last,mark,rates,e,candidate,cost,old['quantity'])
        rows.append(record)
    support={'E0_accepted_n':accepted,'paired24h_qualified_n':len(rows),'censored_event_ids':censored,
        'ineligible_partials':ineligible,'E0_TIME_CAP_n':caps,'censored_E0_TIME_CAP_n':missing_caps,
        'censored_TIME_CAP_fraction':missing_caps/caps if caps else 0}
    return rows,support


def run(sha):
    configs=freeze_check(sha)
    if SCRATCH.is_symlink():raise ValueError('Task scratch symlink')
    SCRATCH.mkdir(exist_ok=True,mode=0o700)
    marker=SCRATCH/'ONE_SHOT_STARTED'
    if marker.exists():raise ValueError('One-shot already started; rerun prohibited')
    marker.write_text(sha+'\n')
    arrays,rates,source=load();dump(SCRATCH/'SOURCE_IDENTITY.json',source)
    e0=e0_gate(configs,arrays,rates,sha,source)
    folds=get_monthly_folds();cache={};signals={};events={}
    for f in folds:
        key=f['year'],f['month'];prev=f['prev_year'],f['prev_month']
        cache[key]=(np.vstack([arrays['last'][prev],arrays['last'][key]]),
                    np.vstack([arrays['mark'][prev],arrays['mark'][key]]),[*rates[prev],*rates[key]],f)
    for c in configs:
        signals[c['id']]={};events[c['id']]={}
        for key,(last,mark,fund,f) in cache.items():
            full=generate_wave_signals(last,c['id'],f['embargo_start_ms'],f['embargo_end_ms'])
            signals[c['id']][key]=eligible_events(full,c,f)[0]
            events[c['id']][key]={e['event_id']:e for e in signals[c['id']][key]}
    result={'TASK_ID':'V06_G2_POST_R31_EXIT_POLICY_HORIZON_R1_ONE_SHOT','frozen_code_sha':sha,
        'source_manifest_sha256':source['source_manifest_sha256'],'grade':'DEVELOPMENT_ONLY_EX_POST_EXPOSED_SELECTED_LEADS',
        'new_configurations':8,'total_cells':10,'D1_D2':'DESIGN_ONLY_NOT_EXECUTED','candidates':{},'inference':{},'automatic_promotions':[]}
    paired_all={};auditable=[];sparse=False
    for c in configs:
        cid=c['id'];result['candidates'][cid]={}
        for cost_name,cost in (('STRESS',STRESS),('BASE',BASE)):
            original=e0['candidates'][cid]['costs'][cost_name]
            base=[json.loads(line) for line in Path(original['funded_attribution_ledger']['path']).read_text().splitlines()]
            pairs,support=paired_cell(base,events[cid],cache,c,cost_name,cost)
            paired_all[cid,cost_name]=pairs
            sparse |= support['censored_TIME_CAP_fraction']>.1
            account={};paired={}
            for scheme in SCHEMES:
                paired_trades=[row['cells'][scheme] for row in pairs if scheme in row['cells']]
                paired[scheme]=descriptive(paired_trades,cost_name)
                if scheme=='E0':
                    account[scheme]={'metrics':original['funding_aware_funded_replay'],'monthly':original['monthly'],
                        'legacy_identity':'EXACT_R31_FULL_FUNDED_BOOK_AND_MINUTE_CURVES',
                        'journal':ledger(cid+'_'+cost_name+'_E0_orders.jsonl',e0_orders(base,cache,events[cid],c,cost)),
                        'accepted_event_ids':[t['event_id'] for t in base]}
                    continue
                cash=1000.;trades=[];curves=[];monthly=[];fates=[]
                for key,(last,mark,fund,fold) in cache.items():
                    before=cash;book=replay(last,mark,fund,signals[cid][key],c,fold,cost,scheme,cash)
                    for trade in book['trades']:
                        ctrl=matched(last,mark,fund,events[cid][key][trade['event_id']],c,cost,scheme,trade['quantity'])
                        trade['control_net_bps']=ctrl.get('balanced_net_bps');trade['matched_control']=ctrl
                    cash=book['ending_equity'];trades.extend(book['trades']);curves.append(book['curve']);fates.extend(book['skipped_event_ids'])
                    monthly.append({'year':key[0],'month':key[1],'starting_cash':before,'ending_cash':cash,'N':len(book['trades']),
                        'event_fates':book['fates'],'Mark_DD_pct':book['max_mtm_drawdown_pct'],'Mark_min_equity':book['min_mark_equity'],
                        'occupancy_fraction':book['occupancy_fraction'],'occupied_minutes':book['occupied_minutes'],
                        'peak_exposure_ratio':book['max_exposure_ratio'],'exposure_above_1x_minutes':book['exposure_above_1x_minutes']})
                curve=np.vstack(curves);path=SCRATCH/(cid+'_'+cost_name+'_'+scheme+'_Mark_curve.npz');np.savez_compressed(path,curve=curve)
                curve_sha=hashlib.sha256(path.read_bytes()).hexdigest()
                account[scheme]={'metrics':descriptive(trades,cost_name,curve,monthly),'monthly':monthly,
                    'journal':ledger(cid+'_'+cost_name+'_'+scheme+'_orders.jsonl',trades),
                    'skipped_signal_fates':fates,'accepted_event_ids':[t['event_id'] for t in trades],
                    'curve':{'path':str(path),'sha256':curve_sha,'uncompressed_curve_sha256':hashlib.sha256(curve.tobytes()).hexdigest()},
                    'peak_exposure_ratio':max(m['peak_exposure_ratio'] for m in monthly),
                    'occupied_minutes':sum(m['occupied_minutes'] for m in monthly),
                    'opportunity_cost_conflicts':sum(x['reason']=='POSITION_ACK_OR_COOLDOWN' for x in fates)}
                auditable.extend({'cost':cost_name,'curve_path':str(path),'curve_sha256':curve_sha,**t} for t in trades if scheme in ('E1','E2'))
                print('NEW',cid,cost_name,scheme,'N',len(trades),'mean',account[scheme]['metrics']['mean_net_bps'],flush=True)
            result['candidates'][cid][cost_name]={'support':support,'paired':paired,'account':account,
                'paired_ledger':ledger(cid+'_'+cost_name+'_paired.jsonl',pairs),
                'execution_sensitivity_grade':'diagnostic-only fixed-event; raw E1-E0 confounded by changed TP limit-fill assumption'}
    result['paired_contrast_decomposition']={}
    for cost_name in ('STRESS','BASE'):
        registry=[];decomposition=[]
        for c in configs:
            for new,old in CONTRASTS:
                rows=[]
                for p in paired_all[c['id'],cost_name]:
                    if new not in p['cells'] or old not in p['cells']:continue
                    a=p['cells'][new];b=p['cells'][old]
                    rows.append({'entry_at':p['entry_at'],'delta_bps':float(a['net_after_funding_bps'])-float(b['net_after_funding_bps'])})
                name=c['id']+':'+new+'-'+old
                registry.append((name,rows))
                valid=[p for p in paired_all[c['id'],cost_name] if new in p['cells'] and old in p['cells']]
                decomposition.append({'contrast':name,'qualified_n':len(valid),
                    'mean_delta_net_bps':mean([x['delta_bps'] for x in rows]),
                    'mean_delta_funding_usdt':mean([float(p['cells'][new]['funding_cash_usdt'])-float(p['cells'][old]['funding_cash_usdt']) for p in valid]),
                    'mean_delta_fees_usdt':mean([p['cells'][new]['fee_entry']+p['cells'][new]['fee_exit']-p['cells'][old]['fee_entry']-p['cells'][old]['fee_exit'] for p in valid]),
                    'mean_delta_weighted_exit_minutes':mean([p['cells'][new]['weighted_exit_age_minutes']-p['cells'][old]['weighted_exit_age_minutes'] for p in valid]),
                    'year':{str(y):mean([float(p['cells'][new]['net_after_funding_bps'])-float(p['cells'][old]['net_after_funding_bps']) for p in valid if datetime.fromtimestamp(p['entry_at']/1000,UTC).year==y]) for y in (2021,2022,2023)},
                    'side':{str(sign):mean([float(p['cells'][new]['net_after_funding_bps'])-float(p['cells'][old]['net_after_funding_bps']) for p in valid if p['side']==sign]) for sign in (-1,1)},
                    'calendar_mechanism':{str(y):{
                        'gross_delta_bps':mean([p['cells'][new]['gross_bps']-p['cells'][old]['gross_bps'] for p in valid if datetime.fromtimestamp(p['entry_at']/1000,UTC).year==y]),
                        'funding_delta_bps':mean([10000*(float(p['cells'][new]['funding_cash_usdt'])-float(p['cells'][old]['funding_cash_usdt']))/p['cells'][old]['entry_notional'] for p in valid if datetime.fromtimestamp(p['entry_at']/1000,UTC).year==y]),
                        'fee_delta_bps':mean([10000*(p['cells'][new]['fee_entry']+p['cells'][new]['fee_exit']-p['cells'][old]['fee_entry']-p['cells'][old]['fee_exit'])/p['cells'][old]['entry_notional'] for p in valid if datetime.fromtimestamp(p['entry_at']/1000,UTC).year==y]),
                        'weighted_age_delta_minutes':mean([p['cells'][new]['weighted_exit_age_minutes']-p['cells'][old]['weighted_exit_age_minutes'] for p in valid if datetime.fromtimestamp(p['entry_at']/1000,UTC).year==y]),
                        'TIME_CAP_n_new':sum(p['cells'][new]['exit_reason']=='TIME_CAP' for p in valid if datetime.fromtimestamp(p['entry_at']/1000,UTC).year==y),
                        'TIME_CAP_n_reference':sum(p['cells'][old]['exit_reason']=='TIME_CAP' for p in valid if datetime.fromtimestamp(p['entry_at']/1000,UTC).year==y)} for y in (2021,2022,2023)},
                    'raw_E1_E0_fill_confounded':new=='E1' and old=='E0'})
        result['inference'][cost_name]={str(d):max_t(registry,d) for d in (7,14)}
        result['paired_contrast_decomposition'][cost_name]=decomposition
    from .audit import independent_audit
    result['independent_Decimal_audit']=independent_audit(auditable,source)
    if result['independent_Decimal_audit']['status'] not in ('PASS','INSUFFICIENT_SUPPORT'):raise ValueError('Independent real Decimal source/cash audit failure')
    unstable=sparse or result['independent_Decimal_audit']['status']!='PASS' or not result['independent_Decimal_audit']['actual_TP1_within_60sec_supported']
    for d in ('7','14'):
        inf=result['inference']['STRESS'][d]
        if inf['status']=='INSUFFICIENT_SUPPORT':unstable=True;continue
        unstable |= any(x['qualified_n']<20 or x['nonempty_calendar_blocks']<8 or x['simultaneous_LCB_bps']<=0<=x['simultaneous_UCB_bps'] for x in inf['contrasts'])
    result['terminal']='EXIT_R1_DIAGNOSTIC_INSUFFICIENT_SUPPORT' if unstable else 'EXIT_R1_EXPLORATORY_ACCOUNT_AND_PAIRED_COMPLETE_DEVELOPMENT_ONLY'
    dump(SCRATCH/'EXIT_R1_RESULTS.json',result)
    print('TERMINAL',result['terminal'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--code-sha',required=True);args=p.parse_args()
    try:run(args.code_sha)
    except Exception as exc:
        if SCRATCH.is_symlink():
            raise
        SCRATCH.mkdir(exist_ok=True)
        dump(SCRATCH/'EXIT_R1_FAILURE.json',{'terminal':'EXIT_R1_FAIL_CLOSED_EXECUTION_OR_SOURCE',
             'exception':type(exc).__name__,'reason':str(exc),'frozen_code_sha':args.code_sha,
             'new_cell_optimistic_summary_suppressed':True,'rerun_prohibited':True})
        raise
