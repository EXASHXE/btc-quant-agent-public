"""Descriptive and fixed block uncertainty; no signal selection or price reader."""
from __future__ import annotations

import math
from collections import Counter

import numpy as np

DAY = 86_400_000
WEEK = 7 * DAY
MONDAY_ORIGIN = 4 * DAY


def drawdown(equity) -> float:
    a = np.asarray(equity, dtype=float)
    if not len(a):
        return 0.0
    high = np.maximum.accumulate(a)
    return float(np.max((high - a) / high) * 100)


def describe(trades: list[dict]) -> dict:
    """All bps use initial raw entry notional, never margin return."""
    if not trades:
        return {"trades": 0, "mean_net_bps": None, "median_net_bps": None,
                "win_rate": None, "profit_factor": None, "mean_net_R": None,
                "mean_gross_bps": None, "net_usdt": 0.0, "fee_usdt": 0.0,
                "execution_drag_usdt": 0.0, "long_share": None,
                "duration_minutes_quantiles": None, "worst5pct_mean_bps": None,
                "mean_mae_bps": None, "mean_mfe_bps": None, "stop_gap_losses": 0,
                "loss_beyond_raw_stop_bps": 0, "exit_reasons": {},
                "turnover_entry_exit_usdt": 0.0}
    a = np.array([t['net_bps'] for t in trades])
    net = np.array([t['net_usdt'] for t in trades])
    profits = float(net[net > 0].sum()); losses = float(-net[net < 0].sum())
    return {
        'trades': len(trades), 'mean_net_bps': float(a.mean()),
        'median_net_bps': float(np.median(a)), 'win_rate': float(np.mean(a > 0)),
        'profit_factor': profits / losses if losses else None,
        'profit_factor_status': 'FINITE' if losses else 'NO_LOSSES_UNBOUNDED_NOT_GATE_PASS',
        'mean_net_R': float(np.mean([t['net_r'] for t in trades])),
        'mean_gross_bps': float(np.mean([t['gross_bps'] for t in trades])),
        'net_usdt': float(net.sum()),
        'fee_usdt': float(sum(t['fee_usdt'] for t in trades)),
        'execution_drag_usdt': float(sum(t['execution_drag_usdt'] for t in trades)),
        'long_share': sum(t['side'] > 0 for t in trades) / len(trades),
        'duration_minutes_quantiles': dict(zip(['min', 'q25', 'median', 'q75', 'max'],
            map(float, np.quantile([t['duration_minutes'] for t in trades], [0,.25,.5,.75,1])), strict=True)),
        'worst5pct_mean_bps': float(np.sort(a)[:max(1, math.ceil(.05*len(a)))].mean()),
        'mean_mae_bps': float(np.mean([t['mae_bps'] for t in trades])),
        'mean_mfe_bps': float(np.mean([t['mfe_bps'] for t in trades])),
        'stop_gap_losses': sum(t['exit_reason'] == 'STOP_GAP' and t['net_bps'] < 0 for t in trades),
        'loss_beyond_raw_stop_bps': sum(t['exit_reason'] == 'STOP_GAP' and
            t['gross_bps'] < -abs(t['raw_entry']-t['stop'])/t['raw_entry']*10000-1e-7 for t in trades),
        'exit_reasons': dict(Counter(t['exit_reason'] for t in trades)),
        'turnover_entry_exit_usdt': sum((t['effective_entry']+t['effective_exit'])*t['quantity'] for t in trades),
    }


def blocked_ci(trades: list[dict], folds: list[dict], inference: dict, days: int = 7) -> dict:
    """Shared calendar draws for all variants; equal era mean, not IID trade SE.

    Empty calendar blocks stay in the sampling frame. Empty sampled eras make
    the estimand undefined; their mass is conservatively assigned -infinity
    for a lower bound. No fictitious zero-return trades are introduced.
    """
    rng = np.random.default_rng(inference['seed'])
    replicates = int(inference['bootstrap_resamples'])
    bootstrap = np.zeros((replicates, 2))
    undefined = np.zeros(replicates, dtype=bool)
    means = []; frames = []
    for fold in folds:
        start, end = fold['start_ms'], fold['end_ms']
        width = days * DAY
        origin = MONDAY_ORIGIN if days == 7 else start
        first = (start-origin)//width; last = (end-1-origin)//width
        counts = np.zeros(last-first+1)
        sums = np.zeros((len(counts), 2))
        selected = [t for t in trades if t['fold'] == fold['id']]
        for t in selected:
            k = (t['entry_at']-origin)//width-first
            counts[k] += 1
            sums[k] += [t['net_bps'], t['incremental_vs_balanced_bps']]
        frames.append({'fold': fold['id'], 'calendar_blocks': len(counts),
                       'nonempty_blocks': int(np.sum(counts > 0)), 'trades': len(selected)})
        if not selected:
            return {'status': 'INSUFFICIENT_SUPPORT_ZERO_TRADE_ERA', 'calendar_frames': frames,
                    'equal_era_net_bps': None, 'equal_era_incremental_bps': None,
                    'net_ci95': None, 'incremental_ci95': None,
                    'adjusted_net_LCB_bps': None, 'adjusted_incremental_LCB_bps': None}
        means.append(sums.sum(axis=0)/counts.sum())
        idx = rng.integers(0, len(counts), size=(replicates, len(counts)))
        n = counts[idx].sum(axis=1)
        undefined |= n == 0
        bootstrap += np.divide(sums[idx].sum(axis=1), n[:,None],
                               out=np.zeros((replicates,2)), where=n[:,None] > 0) / len(folds)
    bootstrap[undefined] = -np.inf
    lower_q = inference['one_sided_lower_quantile']
    # Order statistic avoids interpolating infinities. All bounds are bps.
    def quantile(column, q):
        x = np.sort(column)[max(0, min(replicates-1, math.floor(q*replicates)))]
        return float(x) if np.isfinite(x) else None
    return {'status': 'FINITE_FIXED_BLOCK_BOOTSTRAP', 'seed': inference['seed'],
            'resamples': replicates, 'block_days': days, 'calendar_frames': frames,
            'undefined_sample_fraction': float(undefined.mean()),
            'equal_era_net_bps': float(np.mean(means,axis=0)[0]),
            'equal_era_incremental_bps': float(np.mean(means,axis=0)[1]),
            'net_ci95': [quantile(bootstrap[:,0],q) for q in inference['ci_interval']],
            'incremental_ci95': [quantile(bootstrap[:,1],q) for q in inference['ci_interval']],
            'adjusted_net_LCB_bps': quantile(bootstrap[:,0],lower_q),
            'adjusted_incremental_LCB_bps': quantile(bootstrap[:,1],lower_q),
            'familywise_comparisons': inference['comparisons'], 'one_sided_q': lower_q}


def select(candidate: dict, summary: dict, folds: list[dict], inference: dict) -> list[str]:
    gate = inference['gate']; failures = []
    if not candidate['eligible_for_shortlist']:
        failures.append('ORIGINAL_PROTOCOL_NOT_EVALUABLE_NOT_POSITIVE')
    if len(folds) < gate['minimum_full_era_folds']:
        failures.append('TOO_FEW_FULL_ERAS')
    if any(x['trades'] < gate['minimum_trades_per_full_fold'] for x in summary['folds']):
        failures.append('INSUFFICIENT_PER_ERA_SUPPORT')
    if summary['trades'] < 20*len(folds):
        failures.append('INSUFFICIENT_TOTAL_SUPPORT')
    positive = sum(x['mean_net_bps'] is not None and x['mean_net_bps'] >= 0 for x in summary['folds'])
    if positive/len(folds) < gate['minimum_nonnegative_stress_folds_fraction']:
        failures.append('NOT_ROBUST_ACROSS_ERAS')
    bounds = summary['weekly_bootstrap']
    for key, threshold in [('equal_era_net_bps',gate['stress_equal_era_mean_min_bps'])]:
        if bounds[key] is None or bounds[key] < threshold:
            failures.append('STRESS_EQUAL_ERA_MEAN')
    for key, threshold, name in [
        ('median_net_bps',gate['stress_median_min_bps'],'STRESS_MEDIAN'),
        ('profit_factor',gate['stress_profit_factor_min'],'STRESS_PROFIT_FACTOR'),
        ('worst5pct_mean_bps',gate['worst5pct_trade_mean_min_bps'],'TAIL_LOSS')]:
        if summary[key] is None or summary[key] < threshold:
            failures.append(name)
    if summary['max_trade_close_drawdown_pct'] > gate['max_trade_close_proxy_drawdown_pct']:
        failures.append('TRADE_CLOSE_DRAWDOWN')
    for label, ci in [('WEEK',bounds), ('14DAY',summary['two_week_bootstrap'])]:
        for key in ['adjusted_net_LCB_bps','adjusted_incremental_LCB_bps']:
            if ci[key] is None or ci[key] <= 0:
                failures.append(label+'_'+key.upper())
    return failures


def possible_settlements(entry: int, exit_at: int, interval_hours: int) -> list[int]:
    """Worst ownership within +/-15s of a UTC boundary, including endpoints."""
    step = interval_hours*3_600_000
    first = math.ceil((entry-15_000)/step)*step
    last = math.floor((exit_at+15_000)/step)*step
    return list(range(first,last+1,step)) if last >= first else []
