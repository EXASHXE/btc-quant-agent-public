"""Execute only the frozen stage; no unseen validation access on dev no-go."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1 import replay
from scripts.strategy_research.g2_btc_empirical_fast_r1.metrics import describe
from scripts.strategy_research.g2_btc_empirical_fast_r1.run import (
    account_measurements,
    funding_sensitivity,
)
from scripts.strategy_research.g2_btc_empirical_fast_r1.sources import ms, validate_zip_checksum

from . import metrics, signals, sources

FREEZE='644f573c3d982ef97fc4317018eaa349fa403796'


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(value) -> bytes:
    return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()


def run(stage: str, tag: str, promotion_sha: str | None = None) -> dict:
    roster,split=sources.verify_freeze(FREEZE)
    if stage=='VALIDATION':
        if not promotion_sha:raise ValueError('validation needs exact pushed promotion SHA')
        promotion=sources.verify_promotion(promotion_sha,FREEZE,roster)
        candidates=[c for c in roster['candidates'] if c['id'] in promotion['promoted_ids']]
    elif stage=='DEVELOPMENT' and promotion_sha is None:
        candidates=roster['candidates']
    else:
        raise ValueError('invalid finite stage')
    manifest_path=sources.EVIDENCE/f'SOURCE_MANIFEST_{stage}.json'
    manifest=json.loads(manifest_path.read_text())
    if manifest['gate']!='PASS_PUBLIC_TRADE_PRICE_ONLY':
        raise ValueError('source coverage/integrity gate failed')
    folds=[dict(f,start_ms=ms(f['score_start']),end_ms=ms(f['score_end']))
           for f in split['folds'] if f['stage']==stage and f['id'] in manifest['complete_folds']]
    target=sources.SCRATCH/f'{stage.lower()}-{tag}';target.mkdir(exist_ok=True)
    rows=[];all_trades=[];accounts=[];diagnostics=[];ledger_paths=[]
    trade_path=target/'trade_ledger.jsonl';event_path=target/'event_fates.jsonl'
    grouped={(c['id'],cost):[] for c in candidates for cost in ['BASE','STRESS']}
    with trade_path.open('wb') as ledger,event_path.open('wb') as event_ledger:
        for fold in folds:
            year=fold['year'];arrays=[]
            for month in [fold['warmup_month'],fold['month']]:
                record=next(r for r in manifest['records'] if r['year']==year and r['month']==month)
                raw_path=sources.SCRATCH/f'BTCUSDT-1m-{year}-{month:02}.zip'
                raw=raw_path.read_bytes();checksum=Path(str(raw_path)+'.CHECKSUM')
                assert validate_zip_checksum(raw,checksum.read_text(),raw_path.name)==record['zip_sha256']
                parsed,meta=sources.parse_month(raw,year,month)
                assert meta['csv_sha256']==record['csv_sha256']
                cache=sources.SCRATCH/f'validated-{year}-{month:02}.npy'
                assert digest(cache)==record['validated_npy_sha256']
                cached=np.load(cache,allow_pickle=False);assert np.array_equal(parsed,cached)
                assert record.get('taker_rounding_clamps_at_most_1e_8_BTC',0)==0
                arrays.append(parsed)
            data=np.concatenate(arrays);price=data[:,:6]
            assert np.all(np.diff(data[:,0])==60000)
            counts={};events=signals.generate(data,roster,counts)
            if stage=='VALIDATION':
                counts['candidates']={k:v for k,v in counts['candidates'].items() if k in {c['id'] for c in candidates}}
            diagnostics.append(dict(counts,fold=fold['id']))
            for candidate in candidates:
                source_events=events[candidate['id']]
                # ACK must fit even a position held all the way to its cap.
                accepted=[];precluded=[]
                for event in source_events:
                    if event['entry_at']+candidate['horizon_hours']*3600000+60000>fold['end_ms']:
                        precluded.append({'event_id':event['event_id'],'decision_at':event['decision_at'],
                            'entry_at':event['entry_at'],'result':'PURGED_MAX_HOLD_AND_ACK_EDGE'})
                    else:accepted.append(event)
                by_id={e['event_id']:e for e in accepted}
                for cost_name in ['BASE','STRESS']:
                    cost=roster['execution']['costs'][cost_name]
                    result=replay.simulate(price,accepted,candidate,fold,cost)
                    result['event_log'].extend(precluded)
                    result['waits']['PURGED_MAX_HOLD_AND_ACK_EDGE']=len(precluded)
                    assert len(result['event_log'])==len(source_events)
                    assert len({(e['event_id'],e['entry_at']) for e in result['event_log']})==len(source_events)
                    for trade in result['trades']:
                        assert fold['start_ms']<=trade['entry_at']<trade['exit_at']<fold['end_ms']
                        assert trade['exit_ack_at']<=fold['end_ms']
                        assert trade['decision_at']>=trade['event_time']+60000
                        assert trade['entry_at']>=trade['decision_at']+60000
                        # A fixed standing target cannot receive a windfall gap.
                        if trade['side']*(trade['raw_exit']-trade['target'])>1e-6:
                            raise RuntimeError('BLOCKED_REPLAY_SEMANTICS: exit beyond fixed target')
                        ev=by_id[trade['event_id']]
                        controls=[replay.episode(price,ev,candidate,cost,trade['quantity'],
                                  side_override=s,control='NO_SIGNAL_LONG' if s==1 else 'NO_SIGNAL_SHORT') for s in [1,-1]]
                        trade.update(cost_case=cost_name,stage=stage,
                            matched_long_bps=controls[0]['net_usdt']/trade['entry_notional']*10000,
                            matched_short_bps=controls[1]['net_usdt']/trade['entry_notional']*10000,
                            funding_sensitivity=funding_sensitivity(price,trade))
                        trade['balanced_control_bps']=(trade['matched_long_bps']+trade['matched_short_bps'])/2
                        trade['incremental_vs_balanced_bps']=trade['net_bps']-trade['balanced_control_bps']
                        ledger.write(json.dumps(trade,sort_keys=True,allow_nan=False).encode()+b'\n')
                    for event in result['event_log']:
                        event_ledger.write(json.dumps(dict(event,candidate=candidate['id'],fold=fold['id'],
                            cost_case=cost_name,stage=stage),sort_keys=True).encode()+b'\n')
                    grouped[candidate['id'],cost_name].extend(result['trades']);all_trades.extend(result['trades'])
                    m=describe(result['trades']);account,exposure=account_measurements(price,result,fold['start_ms'],fold['end_ms'],1000.)
                    m.update(account,fold=fold['id'],candidate=candidate['id'],cost_case=cost_name,
                        waits=result['waits'],generated_signals=len(source_events),
                        sides={name:describe([t for t in result['trades'] if t['side']==side]) for name,side in [('LONG',1),('SHORT',-1)]})
                    accounts.append(m)
                    p=target/f"account-{candidate['id']}-{cost_name}-{fold['id']}.npz"
                    np.savez_compressed(p,equity=result['curve'],exposure=exposure,start_ms=fold['start_ms'],step_ms=60000)
                    ledger_paths.append(p)
            print(json.dumps({'phase':'replay','stage':stage,'fold':fold['id'],
                'signals':{c['id']:len(events[c['id']]) for c in candidates}}),flush=True)
    for candidate in candidates:
        for cost_name in ['BASE','STRESS']:
            ts=grouped[candidate['id'],cost_name];books=[a for a in accounts if a['candidate']==candidate['id'] and a['cost_case']==cost_name]
            s=describe(ts);years=metrics.year_statistics(ts,folds,books);represented=[y for y in years if y['trades']]
            s.update(candidate=candidate['id'],horizon_hours=candidate['horizon_hours'],cost_case=cost_name,
                stage=stage,folds=books,years=years,
                equal_year_mean_net_bps=float(np.mean([y['mean_net_bps'] for y in represented])) if represented else None,
                equal_year_mean_incremental_bps=float(np.mean([y['mean_incremental_bps'] for y in represented])) if represented else None,
                equal_year_mean_month_account_return_pct=float(np.mean([y['mean_independent_month_account_return_pct'] for y in represented])) if represented else None,
                max_close_and_MTM_DD_pct=max(max(a['trade_close_drawdown_pct'],a['dense_trade_price_MTM_drawdown_pct']) for a in books),
                std_net_bps=float(np.std([t['net_bps'] for t in ts],ddof=1)) if len(ts)>1 else None,
                sides={name:describe([t for t in ts if t['side']==side]) for name,side in [('LONG',1),('SHORT',-1)]},
                weekly_uncertainty=metrics.block_uncertainty(ts,folds,roster['inference'],stage),
                fortnight_uncertainty=metrics.block_uncertainty(ts,folds,roster['inference'],stage,14),
                mean_matched_long_bps=float(np.mean([t['matched_long_bps'] for t in ts])) if ts else None,
                mean_matched_short_bps=float(np.mean([t['matched_short_bps'] for t in ts])) if ts else None,
                mean_balanced_control_bps=float(np.mean([t['balanced_control_bps'] for t in ts])) if ts else None,
                unique_filled_events=len({(t['candidate'],t['fold'],t['event_id']) for t in ts}))
            s['funding_sensitivity']={cadence:{'adverse'+str(rate)+'bp_mean_net_bps':float(np.mean([
                    t['net_bps']-t['funding_sensitivity'][cadence][f'adverse{rate}bp_usdt']/t['entry_notional']*10000 for t in ts])) if ts else None
                for rate in [4,8]} for cadence in ['UTC8H_ASSUMED_SCHEDULE','UNKNOWN_HOURLY_STRESS']}
            s['gate_failures']=metrics.decide(s,stage,roster) if cost_name=='STRESS' else ['GATE_USES_STRESS_ONLY']
            s['ranking_score']=min(s['equal_year_mean_net_bps'],s['equal_year_mean_month_account_return_pct']*100)/max(1.,s['max_close_and_MTM_DD_pct']) if represented else None
            if cost_name=='STRESS' and not s['gate_failures']:
                ci=s['weekly_uncertainty']['net_ci95']
                s['uncertainty_label']='UNCERTAIN_EXPLORATORY' if ci is None or ci[0] is None or ci[0]<=0 else 'EXPLORATORY_NONPRISTINE_POSITIVE_INTERVAL_NOT_ALPHA'
            rows.append(s)
            print(json.dumps({'phase':'summary','candidate':candidate['id'],'cost':cost_name,'n':s['trades'],
                'mean_net_bps':s['mean_net_bps'],'equal_year_net_bps':s['equal_year_mean_net_bps'],
                'failures':s['gate_failures']}),flush=True)
    passed=[s for s in rows if s['cost_case']=='STRESS' and not s['gate_failures']]
    passed.sort(key=lambda s:(-s['ranking_score'],-s['unique_filled_events'],s['candidate']))
    promoted=[s['candidate'] for s in passed[:2]] if stage=='DEVELOPMENT' else []
    terminal=('DEVELOPMENT_PROMOTION_PENDING_RESERVED_VALIDATION' if promoted else 'DEVELOPMENT_NO_GO') if stage=='DEVELOPMENT' else ('VALIDATION_EXPLORATORY_SETUP_FOUND_NOT_ALPHA' if passed else 'VALIDATION_NO_GO')
    outcome={'schema':'R2_FINITE_STAGE_RESULTS_V1','stage':stage,'freeze_sha':FREEZE,'promotion_sha':promotion_sha,
        'source_manifest_sha256':digest(manifest_path),'full_folds':[f['id'] for f in folds],'folds':folds,
        'rows':rows,'feature_diagnostics':diagnostics,'promoted_ids':promoted,
        'validation_pass_ids':[s['candidate'] for s in passed] if stage=='VALIDATION' else [],
        'terminal':terminal,'observations':len(all_trades),'independent_sample_claim':False,
        'pause':{'trades':0,'net_usdt':0,'return_pct':0,'exposure':0},
        'economic_grade':'EXPLORATORY_COST_PROXY_ONLY_NOT_ALPHA','mark_funding_fees_filters_PIT':'UNKNOWN',
        'ledger_manifest':[{'name':p.name,'sha256':digest(p),'bytes':p.stat().st_size} for p in [trade_path,event_path,*ledger_paths]],
        'protected_owner_or_account_access':0,'reserved_body_access_in_development':0,
        'sampled_account_identity':'INDEPENDENT1000_MONTHLYBOOKS_NO_CONTINUOUS_YEAR_ROI',
        'rights':roster['source_rights']}
    (target/'results.json').write_bytes(dump(outcome))
    return outcome


def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['DEVELOPMENT','VALIDATION'],required=True)
    p.add_argument('--tag',choices=['run1','run2'],required=True);p.add_argument('--promotion')
    a=p.parse_args();r=run(a.stage,a.tag,a.promotion);print(json.dumps({'terminal':r['terminal'],'promoted_ids':r['promoted_ids']}))


if __name__=='__main__':main()
