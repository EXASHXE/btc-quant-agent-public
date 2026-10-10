"""Fixed equal-year inference and literal development/validation gates."""
from __future__ import annotations

import math

import numpy as np

from scripts.strategy_research.g2_btc_empirical_fast_r1.metrics import DAY, MONDAY_ORIGIN


def year_statistics(trades: list[dict], folds: list[dict], accounts: list[dict]) -> list[dict]:
    rows=[]
    for year in sorted({f['year'] for f in folds}):
        ts=[t for t in trades if int(t['fold'][:4])==year]
        books=[a for a in accounts if int(a['fold'][:4])==year]
        rows.append({'year':year,'trades':len(ts),'represented_months':len({t['fold'] for t in ts}),
            'mean_net_bps':float(np.mean([t['net_bps'] for t in ts])) if ts else None,
            'mean_gross_bps':float(np.mean([t['gross_bps'] for t in ts])) if ts else None,
            'mean_incremental_bps':float(np.mean([t['incremental_vs_balanced_bps'] for t in ts])) if ts else None,
            'mean_independent_month_account_return_pct':float(np.mean([a['account_return_pct'] for a in books])),
            'sum_net_usdt_over_separate_monthly_books':sum(t['net_usdt'] for t in ts),
            'initial_capital_sum_usdt':1000.*len(books),
            'months_admitted':len(books),'cash_return_identity':'MEAN_OF_INDEPENDENT_1000_MONTH_BOOKS_NOT_CONTINUOUS_YEAR'})
    return rows


def block_uncertainty(trades: list[dict], folds: list[dict], inference: dict,
                      stage: str, days: int = 7) -> dict:
    """Calendar block sampling within year, retaining empty eligible blocks.

    Each monthly interval is a separate measurement book. Monday UTC block IDs
    may span the selected month edge, but exposures never cross that edge.
    Four season months supply per-year trade means; years are equally weighted.
    """
    n=int(inference['bootstrap_resamples']);rng=np.random.default_rng(inference['seed'])
    years=sorted({int(t['fold'][:4]) for t in trades})
    frames=[];bootstrap=np.zeros((n,2));undefined=np.zeros(n,dtype=bool);point=[]
    if not years:
        return {'status':'ZERO_SUPPORT_UNDEFINED','represented_years':[],
                'net_ci95':None,'increment_ci95':None,'one_sided_net_LCB_bps':None,
                'one_sided_increment_LCB_bps':None,'equal_year_net_bps':None,
                'equal_year_increment_bps':None}
    # Draw for every source year even if this candidate has no trades there.
    # This keeps the same calendar draws for a year across all six candidates.
    for year in sorted({f['year'] for f in folds}):
        fs=[f for f in folds if f['year']==year];keys=[];lookup={}
        for fold in fs:
            origin=MONDAY_ORIGIN if days==7 else fold['start_ms'];width=days*DAY
            lo=(fold['start_ms']-origin)//width;hi=(fold['end_ms']-1-origin)//width
            for k in range(lo,hi+1):
                key=(fold['id'],k);lookup[key]=len(keys);keys.append(key)
        draws=rng.integers(0,len(keys),size=(n,len(keys)))
        counts=np.zeros(len(keys));sums=np.zeros((len(keys),2))
        for t in trades:
            if int(t['fold'][:4])!=year:
                continue
            fold=next(f for f in fs if f['id']==t['fold'])
            origin=MONDAY_ORIGIN if days==7 else fold['start_ms']
            k=lookup[t['fold'],(t['entry_at']-origin)//(days*DAY)]
            counts[k]+=1;sums[k]+=[t['net_bps'],t['incremental_vs_balanced_bps']]
        frames.append({'year':year,'calendar_blocks':len(keys),'nonempty_blocks':int(sum(counts>0)),
                       'trades':int(counts.sum()),'full_months':len(fs)})
        if counts.sum()==0:
            continue
        point.append(sums.sum(axis=0)/counts.sum())
        den=counts[draws].sum(axis=1);undefined|=den==0
        bootstrap+=np.divide(sums[draws].sum(axis=1),den[:,None],
            out=np.zeros((n,2)),where=den[:,None]>0)/len(years)
    bootstrap[undefined]=-np.inf
    def q(col,p):
        value=np.sort(col)[min(n-1,max(0,math.floor(p*n)))]
        return float(value) if np.isfinite(value) else None
    alpha=inference['development_one_sided_q' if stage=='DEVELOPMENT' else 'validation_one_sided_q']
    return {'status':'FIXED_BLOCK_BOOTSTRAP','stage':stage,'days':days,'seed':inference['seed'],
        'resamples':n,'represented_years':years,'calendar_frames':frames,
        'undefined_sample_fraction':float(undefined.mean()),
        'lower_null_identity':'UNBOUNDED_BELOW_FROM_UNDEFINED_YEAR_RESAMPLE_NOT_ZERO',
        'equal_year_net_bps':float(np.mean(point,axis=0)[0]),
        'equal_year_increment_bps':float(np.mean(point,axis=0)[1]),
        'net_ci95':[q(bootstrap[:,0],p) for p in inference['ci95']],
        'increment_ci95':[q(bootstrap[:,1],p) for p in inference['ci95']],
        'one_sided_q':alpha,'trial_count':6 if stage=='DEVELOPMENT' else 2,
        'one_sided_net_LCB_bps':q(bootstrap[:,0],alpha),
        'one_sided_increment_LCB_bps':q(bootstrap[:,1],alpha)}


def decide(summary: dict, stage: str, roster: dict) -> list[str]:
    """Gate uses STRESS only; no CI-lower requirement added to development."""
    assert summary['cost_case']=='STRESS'
    g=roster['development_gate' if stage=='DEVELOPMENT' else 'validation_gate']
    failed=[];years=[y for y in summary['years'] if y['trades']]
    for value,key,name in [(summary['trades'],'stress_trades_min','TRADE_SUPPORT'),
                           (len(years),'years_with_trades_min','YEAR_SUPPORT'),
                           (sum(y['represented_months'] for y in years),'months_with_trades_min','MONTH_SUPPORT')]:
        if value<g[key]:failed.append(name)
    for value,name in [(summary['equal_year_mean_net_bps'],'NONPOSITIVE_EQUAL_YEAR_NET'),
                       (summary['equal_year_mean_incremental_bps'],'NONPOSITIVE_PAIRED_INCREMENT')]:
        if value is None or value<=0:failed.append(name)
    if stage=='DEVELOPMENT':
        if sum(y['mean_net_bps']>=0 for y in years)<g['nonnegative_year_means_min']:
            failed.append('INSUFFICIENT_NONNEGATIVE_YEARS')
        if summary['profit_factor'] is None or summary['profit_factor']<=g['net_USDT_profit_factor_strict_gt']:
            failed.append('NET_PROFIT_FACTOR')
    else:
        if sum(y['mean_net_bps']>0 for y in years)<g['positive_year_means_min']:
            failed.append('NO_POSITIVE_YEAR')
        if len(years)!=2 or any(y['mean_net_bps']<g['neither_year_mean_below_bps'] for y in years):
            failed.append('YEAR_FLOOR')
        if summary['profit_factor'] is None or summary['profit_factor']<g['net_USDT_profit_factor_ge']:
            failed.append('NET_PROFIT_FACTOR')
    if summary['max_close_and_MTM_DD_pct']>g['max_each_account_close_and_MTM_DD_pct_le']:
        failed.append('ACCOUNT_DRAWDOWN')
    return failed
