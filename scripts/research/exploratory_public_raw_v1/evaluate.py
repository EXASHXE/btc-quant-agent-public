"""Fixed entry-notional, single-short-per-arm, partial execution-cost sensitivity."""

import math
from collections import Counter
from datetime import UTC, datetime
from statistics import mean

from . import require
from .contract import POLICY, window
from .native import HOUR, MINUTE


def payoff(entry, exit_price, scenario):
    require(all(math.isfinite(x) and x > 0 for x in (entry, exit_price)), 'INVALID_PRICE')
    gross = 1-exit_price/entry
    fee = scenario['fee_roundtrip_bp']/10000
    slip = scenario['slippage_roundtrip_bp']/10000
    # Deliberate aggregate sensitivity on fixed entry notional, not modeled actual fills.
    return {'gross_return': gross, 'fee_return': fee, 'slippage_return': slip,
            'partial_cost_adjusted_return': gross-fee-slip}


def evaluate(registration, tables, masks):
    bars = tables['price_1m']
    ledger, reasons = [], Counter()
    arms = ['X_full'] + (['X_common', 'XZ_common'] if registration['use_oi'] else [])
    for arm in arms:
        busy_until = -1
        for mask in masks:
            valid = mask['x_valid'] if arm == 'X_full' else mask['common_valid']
            if not valid:
                reasons[(arm, 'FEATURE_UNAVAILABLE')] += 1
                continue
            if not mask['x'] or (arm == 'XZ_common' and not mask['z']):
                reasons[(arm, 'NO_SIGNAL')] += 1
                continue
            entry_t = mask['cutoff']+2*MINUTE
            exit_t = entry_t+8*HOUR
            if entry_t < busy_until:
                reasons[(arm, 'CONCURRENT_POSITION')] += 1
                continue
            entry, exit_row = bars.get(entry_t), bars.get(exit_t)
            if entry is None or exit_row is None:
                reasons[(arm, 'MISSING_EXACT_ENTRY_OR_EXIT')] += 1
                continue
            if any(t not in bars for t in range(entry_t, exit_t+MINUTE, MINUTE)):
                reasons[(arm, 'MISSING_HOLDING_BAR')] += 1
                continue
            baseline = payoff(entry['open'], exit_row['open'], POLICY['baseline'])
            stress = payoff(entry['open'], exit_row['open'], POLICY['stress'])
            ledger.append({'arm': arm, 'origin_ms': mask['origin'], 'entry_ms': entry_t,
                           'exit_ms': exit_t, 'entry_open': entry['open'],
                           'exit_open': exit_row['open'], **baseline,
                           'stress_partial_return': stress['partial_cost_adjusted_return'],
                           'stress_fee_return': stress['fee_return'],
                           'stress_slippage_return': stress['slippage_return'],
                           'funding_return': None, 'modeled_net_return': None,
                           'cost_status': 'COST_INCOMPLETE', 'regime': mask['regime']})
            busy_until = exit_t
    ledger.sort(key=lambda r: (r['entry_ms'], r['arm']))
    summaries = {a: metrics([r for r in ledger if r['arm'] == a], registration) for a in arms}
    losses = [{'arm': a, 'reason': reason, 'count': count}
              for (a, reason), count in sorted(reasons.items())]
    return ledger, summaries, losses


def return_stats(values):
    winners, losers = [x for x in values if x > 0], [x for x in values if x < 0]
    equity, peak, dd = 0, 0, 0
    for x in values:
        equity += x
        peak = max(peak, equity)
        dd = min(dd, equity-peak)
    avg_win = mean(winners) if winners else None
    avg_loss = mean(losers) if losers else None
    tail_count = max(1, math.ceil(len(values)*0.05))
    return {'trades': len(values), 'sum_return': sum(values),
            'win_rate': len(winners)/len(values) if values else None,
            'winner_mean': avg_win, 'loser_mean': avg_loss,
            'payoff': avg_win/-avg_loss if winners and losers else None,
            'profit_factor': sum(winners)/-sum(losers) if losers else None,
            'expectancy': mean(values) if values else None,
            'max_realized_additive_drawdown': dd,
            'worst_trade': min(values) if values else None,
            'worst_5pct_mean': mean(sorted(values)[:tail_count]) if values else None,
            'undefined_ratios_are_null': True}


def metrics(rows, registration):
    left, right = window(registration['origins'])
    years, weeks, regimes = Counter(), Counter(), Counter()
    for row in rows:
        dt = datetime.fromtimestamp(row['entry_ms']/1000, UTC)
        years[str(dt.year)] += 1
        weeks[dt.strftime('%G-W%V')] += 1
        regimes[row['regime']] += 1
    return {'gross': return_stats([r['gross_return'] for r in rows]),
            'baseline_partial': return_stats([r['partial_cost_adjusted_return'] for r in rows]),
            'stress_partial': return_stats([r['stress_partial_return'] for r in rows]),
            'exposure_hours': len(rows)*8,
            'exposure_fraction_of_possible_entry_to_last_exit_span': len(rows)*8*HOUR/
                (right-left+7*HOUR),
            'years': dict(years), 'iso_week_counts': dict(weeks), 'regimes': dict(regimes),
            'year_partial_returns': {y: sum(r['partial_cost_adjusted_return'] for r in rows
                if str(datetime.fromtimestamp(r['entry_ms']/1000, UTC).year) == y) for y in years},
            'regime_partial_returns': {g: sum(r['partial_cost_adjusted_return'] for r in rows
                if r['regime'] == g) for g in regimes},
            'nonoverlapping_events_per_arm': len(rows),
            'statistically_independent_blocks': None,
            'independence_status': 'NONOVERLAP_DOES_NOT_PROVE_INDEPENDENCE',
            'drawdown_basis': 'CLOSED_TRADE_UNIT_NOTIONAL_ADDITIVE_NOT_INTRATRADE'}
