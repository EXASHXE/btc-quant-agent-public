"""One fixed public BTC experiment, with private ledgers outside tracked Git."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from . import metrics, replay, signals
from .sources import EVIDENCE, ms, parse_month, validate_zip_checksum, verify_freeze

FREEZE = '21ee4c11b789d54aca6c602ce5c84426a3944fde'


def dump(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def funding_sensitivity(data, trade: dict) -> dict:
    out = {}
    for cadence, hours in [('UTC8H_ASSUMED_SCHEDULE',8),('UNKNOWN_HOURLY_STRESS',1)]:
        clocks = metrics.possible_settlements(trade['entry_at'],trade['exit_at'],hours)
        notional = 0.0
        for clock in clocks:
            lo = max(trade['entry_at'],clock-15_000)
            hi = min(trade['exit_at'],clock+15_000)
            a = int(np.searchsorted(data[:,0],lo,side='right'))-1
            b = int(np.searchsorted(data[:,0],hi,side='right'))-1
            # A conservative ex-post high envelope, never entry information.
            notional += trade['quantity']*float(np.max(data[max(0,a):b+1,2]))
        out[cadence] = {'possible_settlements':len(clocks),
            'adverse4bp_usdt':notional*4/10000,'adverse8bp_usdt':notional*8/10000}
    return out


def account_measurements(data, result: dict, start: int, end: int, equity: float) -> tuple[dict,np.ndarray]:
    first = int(np.searchsorted(data[:,0],start)); last = int(np.searchsorted(data[:,0],end))
    curve = result['curve']; exposure = np.zeros(len(curve))
    for t in result['trades']:
        a = int(np.searchsorted(data[:,0],t['entry_at']))-first
        # An open-time exit leaves zero exposure through the remaining minute.
        b = int(np.searchsorted(data[:,0],t['exit_at'],side='right'))-first
        if t['exit_at'] % replay.MINUTE == 0:
            b -= 1
        qty = t['quantity']; previous = a
        for reduction in t['partial_reductions']:
            k = int(np.searchsorted(data[:,0],reduction['at']))-first
            exposure[previous:k] = data[first+previous:first+k,4]*qty
            qty -= reduction['quantity']; previous = k
        exposure[previous:b] = data[first+previous:first+b,4]*qty
    fraction = np.divide(exposure,curve,out=np.zeros(len(curve)),where=curve > 0)
    trade_curve = [equity]
    for t in result['trades']:
        trade_curve.append(trade_curve[-1]+t['net_usdt'])
    daily = []
    for a in range(0,len(curve),1440):
        b = min(a+1440,len(curve)); prior = equity if a == 0 else curve[a-1]
        daily.append({'utc_day_start_ms':start+a*replay.MINUTE,'closing_equity_usdt':float(curve[b-1]),
                      'daily_pnl_usdt':float(curve[b-1]-prior),
                      'active_minutes':int(np.sum(exposure[a:b] > 0)),
                      'max_gross_exposure_usdt':float(exposure[a:b].max())})
    assert np.isclose(curve[-1],result['ending_equity'],atol=1e-8)
    assert np.isclose(result['ending_equity'],equity+sum(t['net_usdt'] for t in result['trades']),atol=1e-8)
    return {'initial_equity_usdt':equity,'ending_equity_usdt':float(result['ending_equity']),
            'account_return_pct':float((result['ending_equity']/equity-1)*100),
            'dense_trade_price_MTM_drawdown_pct':metrics.drawdown(np.r_[equity,curve]),
            'trade_close_drawdown_pct':metrics.drawdown(trade_curve),
            'active_minutes_pct':float(np.mean(exposure > 0)*100),
            'max_exposure_equity_ratio':float(fraction.max()),
            'exposure_above_1x_minutes':int(np.sum(fraction > 1+1e-9)),
            'daily_account':daily,'minute_count':last-first}, exposure


def run(scratch: Path, tag: str) -> dict:
    if scratch.resolve() != Path('/tmp/g2-btc-public-empirical-fast-r1'):
        raise ValueError('fixed task scratch only')
    registry = verify_freeze(FREEZE)
    manifest = json.loads((EVIDENCE/'SOURCE_TIME_VERSION_MANIFEST.json').read_text())
    if manifest['gate'] != 'PASS_PUBLIC_TRADE_PRICE_ONLY':
        raise ValueError('source gate not passed')
    output = scratch/tag
    output.mkdir(exist_ok=True)
    years = manifest['complete_era_years']
    folds = [dict(f,start_ms=ms(f['score_start']),end_ms=ms(f['score_end']))
             for f in registry['folds'] if f['year'] in years]
    datasets = {}; generated = {}
    for fold in folds:
        y = fold['year']; months = []
        for month in (3,4):
            record = next(r for r in manifest['records'] if r['year']==y and r['month']==month)
            raw = scratch/f'BTCUSDT-1m-{y}-{month:02}.zip'
            checksum = Path(str(raw)+'.CHECKSUM')
            assert validate_zip_checksum(raw.read_bytes(),checksum.read_text(),raw.name)==record['zip_sha256']
            path = scratch/f'validated-{y}-{month:02}.npy'
            a = np.load(path,allow_pickle=False)
            source_array, _ = parse_month(raw.read_bytes(),y,month)
            assert np.array_equal(a,source_array), 'parser cache/source mismatch'
            # Validate the parser cache against source-recorded minute range.
            assert len(a)==record['price_rows'] and a[0,0]==ms(record['min_open_utc'])
            assert a[-1,0]+replay.MINUTE==record['end_exclusive_ms']
            months.append(a)
        data = np.concatenate(months)
        assert np.all(np.diff(data[:,0])==replay.MINUTE)
        datasets[fold['id']] = data
        generated[fold['id']] = signals.generate(data,registry)
        print(json.dumps({'phase':'signals','year':y,'events':{k:len(v) for k,v in generated[fold['id']].items()}}),flush=True)
    trade_file = output/'trade_ledger.jsonl'; event_file = output/'decision_event_ledger.jsonl'
    rows = []; all_trades = []; account_files = []
    with trade_file.open('wb') as ledger, event_file.open('wb') as decisions:
        for candidate in registry['candidates']:
            for cost_name in ['BASE','STRESS']:
                cost = registry['costs'][cost_name]; capital=1000.; highwater=1000.; disabled=False
                folded = []; book_trades=[]; waits=Counter(); dense_curves=[]
                for fold in folds:
                    data = datasets[fold['id']]; source_events=generated[fold['id']][candidate['id']]
                    original = not candidate['eligible_for_shortlist']
                    initial = capital if original else 1000.
                    result = replay.simulate(data,[] if original and disabled else source_events,candidate,
                                             fold,cost,initial,highwater if original else None)
                    if original and disabled:
                        result['disabled']=True
                        result['waits']['CARRIED_DISABLED']=len(source_events)
                        result['event_log']=[{'event_id':e['event_id'],'decision_at':e['decision_at'],
                            'entry_at':e['entry_at'],'result':'CARRIED_DISABLED'} for e in source_events]
                    by_id = {str(e['event_id']):e for e in source_events}
                    for trade in result['trades']:
                        event=by_id[trade['event_id']]
                        controls = [replay.episode(data,event,candidate,cost,trade['quantity'],
                            side_override=side,control='NO_SIGNAL_LONG' if side==1 else 'NO_SIGNAL_SHORT')
                            for side in [1,-1]]
                        # The denominator is the SAME raw parent entry notional.
                        trade['cost_case']=cost_name
                        trade['matched_long_bps']=controls[0]['net_usdt']/trade['entry_notional']*10000
                        trade['matched_short_bps']=controls[1]['net_usdt']/trade['entry_notional']*10000
                        trade['balanced_control_bps']=(trade['matched_long_bps']+trade['matched_short_bps'])/2
                        trade['incremental_vs_balanced_bps']=trade['net_bps']-trade['balanced_control_bps']
                        trade['funding_sensitivity']=funding_sensitivity(data,trade)
                        ledger.write(json.dumps(trade,sort_keys=True,allow_nan=False).encode()+b'\n')
                    for event in result['event_log']:
                        decisions.write(json.dumps(dict(event,candidate=candidate['id'],fold=fold['id'],cost_case=cost_name),sort_keys=True).encode()+b'\n')
                    m = metrics.describe(result['trades']); m['fold']=fold['id']
                    account, exposure = account_measurements(data,result,fold['start_ms'],fold['end_ms'],initial)
                    m.update(account); m['waits']=result['waits'];m['source_signal_events_including_warmup']=len(source_events)
                    p=output/f"account-{candidate['id']}-{cost_name}-{fold['id']}.npz"
                    np.savez_compressed(p,equity=result['curve'],exposure=exposure,
                                        start_ms=fold['start_ms'],step_ms=replay.MINUTE)
                    account_files.append(p)
                    folded.append(m);book_trades.extend(result['trades']);waits.update(result['waits'])
                    dense_curves.append(result['curve'])
                    capital=float(result['ending_equity']);highwater=result['highwater'];disabled=result['disabled']
                summary=metrics.describe(book_trades)
                summary.update(candidate=candidate['id'],cost_case=cost_name,folds=folded,
                    horizon_hours=candidate['horizon_hours'],measurement_identity=candidate['measurement_identity'],
                    protocol_status=candidate.get('original_protocol_economic_status','EXPLORATORY_COST_PROXY_ONLY'),
                    weekly_bootstrap=metrics.blocked_ci(book_trades,folds,registry['inference']),
                    two_week_bootstrap=metrics.blocked_ci(book_trades,folds,registry['inference'],14),
                    waits=dict(waits),max_trade_close_drawdown_pct=max(x['trade_close_drawdown_pct'] for x in folded),
                    max_dense_MTM_drawdown_pct=max(x['dense_trade_price_MTM_drawdown_pct'] for x in folded),
                    pooled_ACCOUNT_return_status='NOT_DEFINED_ACROSS_RESET_ERAS' if not original else 'CARRIED_BOOK',
                    original_carry_total_return_pct=(capital/1000-1)*100 if original else None,
                    mean_matched_long_bps=float(np.mean([t['matched_long_bps'] for t in book_trades])) if book_trades else None,
                    mean_matched_short_bps=float(np.mean([t['matched_short_bps'] for t in book_trades])) if book_trades else None,
                    mean_balanced_control_bps=float(np.mean([t['balanced_control_bps'] for t in book_trades])) if book_trades else None)
                summary['funding_sensitivity']={}
                if original:
                    summary['max_trade_close_drawdown_pct']=metrics.drawdown(
                        np.r_[1000.,1000.+np.cumsum([t['net_usdt'] for t in book_trades])])
                    summary['max_dense_MTM_drawdown_pct']=metrics.drawdown(np.r_[1000.,np.concatenate(dense_curves)])
                for cadence in ['UTC8H_ASSUMED_SCHEDULE','UNKNOWN_HOURLY_STRESS']:
                    debits={rate:sum(t['funding_sensitivity'][cadence][f'adverse{rate}bp_usdt'] for t in book_trades) for rate in [4,8]}
                    summary['funding_sensitivity'][cadence]={'debit_usdt':{str(k):v for k,v in debits.items()},
                        'mean_net_after_adverse_bps':{str(rate):float(np.mean([
                            t['net_bps']-t['funding_sensitivity'][cadence][f'adverse{rate}bp_usdt']/t['entry_notional']*10000
                            for t in book_trades])) if book_trades else None for rate in [4,8]}}
                # Descriptive bins chosen from ATR units, never entry filters or ranking.
                summary['descriptive_volatility_regimes']={label:metrics.describe([t for t in book_trades
                    if lo<=t['regime_vol_bps']<hi]) for label,lo,hi in [('ATR_lt50bp',0,50),('ATR_50_100bp',50,100),('ATR_ge100bp',100,float('inf'))]}
                summary['shortlist_failures']=metrics.select(candidate,summary,folds,registry['inference']) if cost_name=='STRESS' else ['SELECTION_USES_STRESS_ONLY']
                rows.append(summary);all_trades.extend(book_trades)
                print(json.dumps({'phase':'replay','candidate':candidate['id'],'cost':cost_name,'trades':summary['trades'],
                                  'mean_net_bps':summary['mean_net_bps'],'failures':summary['shortlist_failures']}),flush=True)
    eligible=[r for r in rows if r['cost_case']=='STRESS' and not r['shortlist_failures']]
    eligible.sort(key=lambda r:(-min(r['weekly_bootstrap']['adjusted_net_LCB_bps'],r['weekly_bootstrap']['adjusted_incremental_LCB_bps']),
                               r['max_trade_close_drawdown_pct'],r['candidate']))
    answer={'schema':'FIXED_BTC_EMPIRICAL_RESULTS_V1','freeze_sha':FREEZE,
            'source_manifest_sha256':digest(EVIDENCE/'SOURCE_TIME_VERSION_MANIFEST.json'),
            'registry_sha256':digest(EVIDENCE/'FROZEN_STRATEGY_REGISTRY.json'),
            'full_years':years,'folds':folds,'cost_grade':'EXPLORATORY_COST_PROXY_ONLY',
            'funding_and_mark':'UNKNOWN_NOT_MEASURED','pause':{'trades':0,'net_usdt':0,'return_pct':0,'active_minutes':0},
            'rows':rows,'shortlisted':[r['candidate'] for r in eligible[:registry['inference']['max_cards']]],
            'terminal':'EMPIRICAL_DISCOVERY_COMPLETED_EXPLORATORY_CANDIDATES_FOUND' if eligible else 'NO_STRATEGY_CLEARS_COST_AND_SUPPORT_GATE',
            'total_candidate_cost_trades':len(all_trades),
            'funding_max_boundary_counts':{str(h):{'UTC8H':(h*3600000+30000)//(8*3600000)+1,
                'UNKNOWN_HOURLY':(h*3600000+30000)//3600000+1} for h in [4,8,12,24]},
            'ledger_manifest':[{'name':p.name,'sha256':digest(p),'bytes':p.stat().st_size}
                               for p in [trade_file,event_file,*account_files]],
            'raw_and_full_ledgers_location':'TASK_OWNED_TMP_OUTSIDE_GIT_NO_REHOSTING',
            'regime_bins':'DESCRIPTIVE_ONLY_POSTFREEZE_FIXED_UNITS_NOT_SELECTION_INPUT',
            'rights':registry['rights']}
    (output/'aggregate_results.json').write_bytes(dump(answer))
    return answer


def main():
    p=argparse.ArgumentParser();p.add_argument('--scratch',type=Path,required=True);p.add_argument('--tag',choices=['run1','run2'],required=True)
    args=p.parse_args();result=run(args.scratch,args.tag)
    print(json.dumps({'terminal':result['terminal'],'shortlisted':result['shortlisted']}),flush=True)


if __name__=='__main__':
    main()
