"""One bounded, real-price, unchanged-23-code development replay sidecar."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .metrics import (
    block_bootstrap,
    calculate_candidate_metrics,
    compute_drawdown,
    evaluate_promotion_gate,
)
from .reanalysis_r2_audit import audit_episode
from .reanalysis_r2_controls import funding_sensitivity, matched_control
from .reanalysis_r2_sources import load_validated_month
from .replay import BASE, HOUR, MINUTE, STRESS, simulate_fold
from .signals import generate_wave_signals
from .sources import get_monthly_folds

ROOT = Path(__file__).resolve().parents[3]
OUT = Path('/tmp/gemini-a-code-identity-replay-r2')
EP = ROOT / 'evidence/v0.6/b_line/g2_gemini_goal_trend_flow_r1'
START = 'd1f9f4316a2485f5d09ee1c910d7797ecfc6be7e'
ORIGINAL = 'a37721eaa1f3cd176146df6bdb63fbd17746189e'
TASK = 'V06_G2_GEMINI_A_CODE_AS_EXECUTED_23_TRIAL_ACTUAL_MARKET_REPLAY_R2'
GRADE = 'EX_POST_CODE_AS_EXECUTED_DEV_ONLY_NOT_REGISTERED_TEXT_METHOD'
CONTROLLER_GRADE = 'EX_POST_CODE_AS_EXECUTED_REANALYSIS_EXPOSED_DEV_ONLY__NOT_PREREG_CONFIRMED'
INVALID = 'W1_C06_PERSISTENT_TREND_24H'


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_bytes(json.dumps(value, indent=2, allow_nan=False).encode() + b'\n')


def git_bytes(sha: str, relative: str) -> bytes:
    return subprocess.check_output(['git', 'show', f'{sha}:{relative}'], cwd=ROOT)


def verify_identity(code_sha: str | None = None) -> tuple[list[dict], dict]:
    if code_sha is not None:
        parent = subprocess.check_output(['git', 'rev-parse', code_sha + '^'], cwd=ROOT, text=True).strip()
        if parent != START:
            raise ValueError('Corrected implementation must be direct child of exact R2 start')
        # Every implementation byte used for this run must match the frozen code.
        paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', code_sha, '--',
            'scripts/strategy_research/g2_gemini_goal_trend_flow_r1'], cwd=ROOT, text=True).splitlines()
        for path in paths:
            if (ROOT / path).read_bytes() != git_bytes(code_sha, path):
                raise ValueError('Implementation byte mismatch: ' + path)
    signal_path = 'scripts/strategy_research/g2_gemini_goal_trend_flow_r1/signals.py'
    original_tree = ast.parse(git_bytes(ORIGINAL, signal_path))
    local_tree = ast.parse((ROOT / signal_path).read_text())
    def functions(tree):
        return [ast.dump(n) for n in tree.body if isinstance(n, ast.FunctionDef)]
    if functions(original_tree) != functions(local_tree):
        raise ValueError('Original signal implementation function AST changed')
    candidates, registry_receipts = [], []
    for wave in range(1, 5):
        path = f'evidence/v0.6/b_line/g2_gemini_goal_trend_flow_r1/WAVE_{wave:02d}_FROZEN_REGISTRY.json'
        raw = (ROOT / path).read_bytes()
        if raw != git_bytes(ORIGINAL, path) or raw != git_bytes(START, path):
            raise ValueError('Registry changed')
        registry = json.loads(raw)
        assert len(registry['candidates']) == 6
        candidates.extend(registry['candidates'])
        registry_receipts.append({'wave': wave, 'path': path, 'sha256': hashlib.sha256(raw).hexdigest()})
    assert len(candidates) == len({c['id'] for c in candidates}) == 24
    valid = [c for c in candidates if c['id'] != INVALID]
    assert len(valid) == 23 and sum(c['id'] == INVALID for c in candidates) == 1
    fingerprints = {}
    for node in ast.walk(original_tree):
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            test = node.test
            if isinstance(test.left, ast.Name) and test.left.id == 'cand_id':
                candidate_id = ast.literal_eval(test.comparators[0])
                fingerprints[candidate_id] = hashlib.sha256(ast.dump(
                    ast.Module(body=node.body, type_ignores=[])).encode()).hexdigest()
    return valid, {'original_code_sha': ORIGINAL, 'exact_start_sha': START,
        'corrected_code_sha': code_sha, 'signal_function_ast_sha256': hashlib.sha256(
            canonical(functions(original_tree))).hexdigest(),
        'candidate_branch_ast_sha256': {c['id']: fingerprints[c['id']] for c in valid},
        'unchanged_registries': registry_receipts,
        'excluded': {'id': INVALID, 'status': 'METHOD_INVALID_EXCLUDED_FROM_PROMOTION', 'numeric_rerun': False},
        'entry_clock': 'event_time=t_round-60000;decision_at=t_round;entry_at=t_round+60000',
        'time_cap': 'first minute-open at/after entry+horizon, capped at target, original priority',
        'controller_dispatch_sha': 'bfe9f5df1bf55e7738cfbff58ce32e674edab683',
        'prompt_sha': '681087557fb774a110500282fcd5e20fa17bc949',
        'scientific_grade': GRADE, 'controller_scientific_grade': CONTROLLER_GRADE}


def eligible_events(events: list[dict], candidate: dict, fold: dict) -> tuple[list[dict], int]:
    # Ex ante bound: do not retain a late entry merely because its future stop
    # would happen to exit before score-end. This is cash/PIT boundary correction.
    limit = int(fold['end_ms'])
    accepted = [e for e in events if int(e['entry_at']) + int(candidate['horizon_hours']) * HOUR + MINUTE < limit]
    return accepted, len(events) - len(accepted)


def side_summary(trades: list[dict], side: int) -> dict:
    selected = [t for t in trades if t['side'] == side]
    return {'n': len(selected), 'mean_gross_bps': float(np.mean([t['gross_bps'] for t in selected])) if selected else None,
        'mean_net_bps': float(np.mean([t['net_bps'] for t in selected])) if selected else None,
        'net_usdt': sum(t['net_usdt'] for t in selected)}


def funding_summary(trades: list[dict]) -> dict:
    result = {}
    for cadence in (8, 1):
        for rate in (4, 8):
            for offset in (-15, 0, 15):
                scenarios = [funding_sensitivity(t, rate, cadence_hours=cadence,
                    offset_seconds=offset, adverse_only=True) for t in trades]
                key = f'adverse_{rate}bp_{cadence}h_offset_{offset}s'
                result[key] = {'hypothetical_only': True,
                    'settlement_count': sum(int(s['settlement_count']) for s in scenarios),
                    'mean_net_after_funding_bps': float(np.mean([s['net_after_funding_bps'] for s in scenarios])) if scenarios else None,
                    'funding_cash_usdt': sum(float(s['funding_cash_usdt']) for s in scenarios)}
    for rate in (-8, -4, 4, 8):
        scenarios = [funding_sensitivity(t, rate, cadence_hours=8) for t in trades]
        result[f'signed_{rate}bp_8h'] = {'hypothetical_only': True,
            'mean_net_after_funding_bps': float(np.mean([s['net_after_funding_bps'] for s in scenarios])) if scenarios else None,
            'signed_funding_cash_usdt': sum(float(s['funding_cash_usdt']) for s in scenarios)}
    return result


def run(code_sha: str, *, refresh_provider: bool = True) -> dict:
    candidates, identity = verify_identity(code_sha)
    if OUT.is_symlink() or OUT.resolve().parent != Path('/tmp'):
        raise ValueError('Invalid task scratch')
    OUT.mkdir(exist_ok=True)
    if (OUT / 'REANALYSIS_R2_RESULTS.json').exists():
        raise ValueError('Bounded full recomputation already completed; do not rerun/search')
    started = datetime.now(UTC).isoformat()
    arrays, sources = {}, []
    for year in range(2021, 2024):
        for month in range(1, 13):
            array, receipt = load_validated_month(year, month, allow_download=True,
                refresh_provider_checksum=refresh_provider)
            arrays[year, month] = array
            sources.append(receipt)
            print(f'SOURCE {year}-{month:02d} {len(array)} verified', flush=True)
    source_receipt = {'task_id': TASK, 'scientific_grade': GRADE, 'identity': identity,
        'months': sources, 'archives_verified': len(sources),
        'minute_rows': sum(len(a) for a in arrays.values()), 'price_scope': '2021-01..2023-12',
        'score_scope': '2021-02..2023-12;35 monthly folds;24h signal purge',
        'fresh_provider_checksums': refresh_provider, 'source_sha256': digest(sources),
        'price_is_not_mark': True, 'historical_known_at': 'UNPROVEN',
        'protected_or_owner_private_access': False}
    write_json(OUT / 'REANALYSIS_R2_SOURCE_RECEIPT.json', source_receipt)
    folds = get_monthly_folds()
    assert len(folds) == 35
    outcome = {'task_id': TASK, 'scientific_grade': GRADE, 'controller_scientific_grade': CONTROLLER_GRADE,
        'economic_grade': 'COST_PROXY_DEV_ONLY', 'identity': identity, 'started_at_utc': started,
        'source_sha256': source_receipt['source_sha256'], 'minute_rows': source_receipt['minute_rows'],
        'archives_verified': 36, 'score_folds': 35, 'costs': {'BASE': BASE, 'STRESS': STRESS},
        'candidates': {}, 'excluded': identity['excluded'], 'automatic_promotion_ids': [],
        'pause': {'initial_usdt': 1000, 'ending_usdt': 1000, 'cash_return_pct': 0, 'mtm_dd_pct': 0}}
    audits, audit_keys, reproduction = [], set(), []
    witness_candidates = {candidates[0]['id'], candidates[len(candidates)//2]['id'], candidates[-1]['id']}
    for candidate in candidates:
        cid = candidate['id']; events_per_fold = {}
        for fold in folds:
            key = (fold['year'], fold['month'])
            data = np.vstack([arrays[fold['prev_year'], fold['prev_month']], arrays[key]])
            events = generate_wave_signals(data, cid, fold['embargo_start_ms'], fold['embargo_end_ms'])
            assert all(e['candidate_id'] == cid and e['horizon_hours'] == candidate['horizon_hours'] for e in events)
            assert all(e['decision_at'] == e['event_time'] + MINUTE and e['entry_at'] == e['decision_at'] + MINUTE for e in events)
            assert len({e['event_id'] for e in events}) == len(events)
            events_per_fold[key] = events
        candidate_out = {'scientific_grade': GRADE, 'controller_scientific_grade': CONTROLLER_GRADE,
            'candidate': candidate, 'signal_events': sum(len(e) for e in events_per_fold.values()),
            'signal_events_sha256': digest(events_per_fold_as_json(events_per_fold)), 'scenarios': {}}
        for cost_name, cost in (('BASE', BASE), ('STRESS', STRESS)):
            equity = 1000.; trades, controls, month_summaries, curves = [], [], [], []
            fates = Counter(); year_cash = {}; repeated_this_scenario = False
            ledger_path = OUT / f'{cid}_{cost_name}_trades.jsonl'
            with ledger_path.open('wb') as ledger:
                for fold in folds:
                    key = (fold['year'], fold['month'])
                    data = np.vstack([arrays[fold['prev_year'], fold['prev_month']], arrays[key]])
                    events, boundary_rejected = eligible_events(events_per_fold[key], candidate, fold)
                    event_lookup = {e['event_id']: e for e in events}
                    initial = equity
                    book = simulate_fold(data, events, candidate, fold, cost, initial_equity=initial)
                    core_digest = digest(book['trades'])
                    if cid in witness_candidates and cost_name == 'STRESS' and book['trades'] and not repeated_this_scenario:
                        again = simulate_fold(data, events, candidate, fold, cost, initial_equity=initial)
                        assert core_digest == digest(again['trades'])
                        assert np.array_equal(book['minute_equity_curve'], again['minute_equity_curve'])
                        reproduction.append({'candidate': cid, 'cost': cost_name, 'year': fold['year'], 'month': fold['month'],
                            'trade_count': len(book['trades']), 'trades_sha256': core_digest,
                            'minute_curve_sha256': hashlib.sha256(book['minute_equity_curve'].tobytes()).hexdigest(), 'exact_match': True})
                        repeated_this_scenario = True
                    previous_ack = 0
                    for tr in book['trades']:
                        assert tr['entry_at'] >= previous_ack
                        previous_ack = tr['exit_ack_at']
                        assert tr['entry_at'] + candidate['horizon_hours'] * HOUR + MINUTE < fold['end_ms']
                        assert tr['effective_exit'] > 0 and tr['exit_ack_at'] > tr['exit_at']
                        control = matched_control(data, event_lookup[tr['event_id']], candidate, cost, tr)
                        assert control['pair_entry_cash_proxy_usdt'] <= 0.95 * min(tr['cash_before_entry'], 1000.) + 1e-7
                        tr['control_net_bps'] = control['balanced_net_bps']
                        tr['paired_increment_bps'] = control['paired_increment_bps']
                        tr['pause_net_bps'] = 0.
                        controls.append(control)
                        witness_key = (tr['side'], tr['exit_reason'])
                        if cost_name == 'STRESS' and witness_key not in audit_keys and len(audits) < 12:
                            audits.append(audit_episode(data, event_lookup[tr['event_id']], candidate, cost, tr))
                            audit_keys.add(witness_key)
                        ledger.write(canonical({'trade': tr, 'event': event_lookup[tr['event_id']], 'control': control}))
                    assert abs(initial + sum(t['net_usdt'] for t in book['trades']) - book['ending_equity']) < 1e-7
                    equity = book['ending_equity']
                    curves.append(book['minute_equity_curve'])
                    fates.update(book['event_fates']); fates['MAX_HOLD_AND_ACK_OUTSIDE_FOLD'] += boundary_rejected
                    trades.extend(book['trades'])
                    ym = {'scientific_grade': GRADE, 'year': fold['year'], 'month': fold['month'],
                        'generated_events': len(events_per_fold[key]), 'event_fates': {**book['event_fates'], 'MAX_HOLD_AND_ACK_OUTSIDE_FOLD': boundary_rejected},
                        'initial_usdt': initial, 'ending_usdt': equity, 'net_usdt': equity-initial,
                        'month_cash_return_pct': 100*(equity/initial-1), 'n': len(book['trades']),
                        'mean_gross_bps': float(np.mean([t['gross_bps'] for t in book['trades']])) if book['trades'] else None,
                        'mean_net_bps': float(np.mean([t['net_bps'] for t in book['trades']])) if book['trades'] else None,
                        'median_gross_bps': float(np.median([t['gross_bps'] for t in book['trades']])) if book['trades'] else None,
                        'median_net_bps': float(np.median([t['net_bps'] for t in book['trades']])) if book['trades'] else None,
                        'net_profit_factor': calculate_candidate_metrics(book['trades'], cost_name)['net_profit_factor'],
                        'within_month_mtm_dd_pct': book['max_mtm_drawdown_pct'],
                        'max_marked_exposure_ratio': book['max_position_notional_to_marked_equity'],
                        'marked_exposure_breach_minutes': book['marked_exposure_breach_minutes'],
                        'long': side_summary(book['trades'], 1), 'short': side_summary(book['trades'], -1),
                        'mean_paired_increment_bps': float(np.mean([t['paired_increment_bps'] for t in book['trades']])) if book['trades'] else None}
                    month_summaries.append(ym)
                    year_cash.setdefault(fold['year'], {'initial_usdt': initial, 'ending_usdt': equity})['ending_usdt'] = equity
            joined = np.vstack(curves)
            metrics = calculate_candidate_metrics(trades, cost_name, minute_equity_curve=[1000., *joined[:, 1].tolist()])
            for y, cash in year_cash.items():
                cash['cash_return_pct'] = 100 * (cash['ending_usdt'] / cash['initial_usdt'] - 1)
                if y not in metrics['yearly_breakdown']:
                    metrics['yearly_breakdown'][y] = {'n_trades': 0, 'mean_net_bps': None}
                metrics['yearly_breakdown'][y]['funded_account'] = cash
                annual_trades = [t for t in trades if datetime.fromtimestamp(t['entry_at']/1000, UTC).year == y]
                annual = calculate_candidate_metrics(annual_trades, cost_name)
                for field in ('mean_gross_bps', 'median_gross_bps', 'median_net_bps', 'net_profit_factor', 'gross_profit_factor'):
                    metrics['yearly_breakdown'][y][field] = annual[field]
                year_start = int(datetime(y, 1, 1, tzinfo=UTC).timestamp()*1000)
                year_end = int(datetime(y+1, 1, 1, tzinfo=UTC).timestamp()*1000)
                annual_curve = joined[(joined[:,0] >= year_start) & (joined[:,0] < year_end), 1]
                metrics['yearly_breakdown'][y]['within_year_mtm_dd_pct'] = compute_drawdown([cash['initial_usdt'], *annual_curve.tolist()])
                metrics['yearly_breakdown'][y]['long'] = side_summary(annual_trades, 1)
                metrics['yearly_breakdown'][y]['short'] = side_summary(annual_trades, -1)
            metrics['duration_minutes'] = {'median': float(np.median([t['duration_minutes'] for t in trades])) if trades else None,
                'minimum': min((t['duration_minutes'] for t in trades), default=None),
                'maximum': max((t['duration_minutes'] for t in trades), default=None)}
            metrics['ending_usdt'] = equity; metrics['cash_return_pct'] = 100*(equity/1000.-1)
            metrics['active_weeks_7d'] = block_bootstrap(trades, n_iter=1)['nonempty_block_count']
            metrics['side'] = {'long': side_summary(trades, 1), 'short': side_summary(trades, -1)}
            metrics['month_abs_pnl_dominance_fraction'] = max((abs(m['net_usdt']) for m in month_summaries), default=0.) / max(sum(abs(m['net_usdt']) for m in month_summaries), 1e-9)
            metrics['max_marked_exposure_ratio'] = max(m['max_marked_exposure_ratio'] for m in month_summaries)
            metrics['marked_exposure_breach_minutes'] = sum(m['marked_exposure_breach_minutes'] for m in month_summaries)
            curve_path = OUT / f'{cid}_{cost_name}_minute_equity.npz'
            np.savez_compressed(curve_path, minute_equity=joined)
            boot7 = block_bootstrap(trades, block_days=7)
            boot14 = block_bootstrap(trades, block_days=14)
            contrast_trades = [{**t, 'net_bps': t['paired_increment_bps']} for t in trades]
            paired_boot7 = block_bootstrap(contrast_trades, block_days=7)
            paired_boot14 = block_bootstrap(contrast_trades, block_days=14)
            gate = evaluate_promotion_gate(metrics, boot7, boot14)
            gate['verdict'] = 'DESCRIPTIVE_GATE_PASS_NO_AUTOMATIC_PROMOTION' if gate['all_passed'] else 'DESCRIPTIVE_GATE_NOT_CLEARED'
            ctrl_end = [max(c['long']['exit_at'], c['short']['exit_at']) for c in controls]
            overlap = sum(int(c['entry_at'] < max(ctrl_end[:i], default=0)) for i, c in enumerate(controls))
            scenario = {'scientific_grade': GRADE, 'cost_model': cost_name, 'metrics': metrics,
                'months': month_summaries, 'event_fates': dict(fates), 'bootstrap_7d': boot7, 'bootstrap_14d': boot14,
                'paired_increment_bootstrap_7d': paired_boot7, 'paired_increment_bootstrap_14d': paired_boot14,
                'descriptive_gate': gate, 'funding_sensitivity': funding_summary(trades),
                'controls': {'classification': 'NONTRADABLE_EVENT_MATCHED_50_50;NOT_A_POOLED_FUNDED_ACCOUNT',
                    'pause_mean_bps': 0., 'balanced_mean_net_bps': float(np.mean([c['balanced_net_bps'] for c in controls])) if controls else None,
                    'mean_paired_increment_bps': metrics['mean_paired_increment_bps'],
                    'overlapping_pair_entries': overlap, 'matched_pair_count': len(controls),
                    'max_individual_pair_mtm_dd_pct_on_1000': max((float(c['pair_max_mtm_drawdown_pct_on_1000_usdt']) for c in controls), default=0.)},
                'trade_ledger': {'path_outside_git': str(ledger_path), 'sha256': hashlib.sha256(ledger_path.read_bytes()).hexdigest()},
                'minute_equity_ledger': {'path_outside_git': str(curve_path), 'sha256': hashlib.sha256(curve_path.read_bytes()).hexdigest(),
                    'uncompressed_curve_sha256': hashlib.sha256(joined.tobytes()).hexdigest()}}
            assert sum(fates.values()) == candidate_out['signal_events'], 'Generated event fate conservation failed'
            candidate_out['scenarios'][cost_name] = scenario
            print(f'RESULT {cid} {cost_name} n={len(trades)} net={metrics["mean_net_bps"]} cash={metrics["cash_return_pct"]:.4f}% MTM={metrics["max_mtm_drawdown_pct"]:.4f}%', flush=True)
        outcome['candidates'][cid] = candidate_out
        write_json(OUT / 'REANALYSIS_R2_PROGRESS.json', outcome)
    assert len(audits) >= 5 and {'STOP','TIME_CAP','TARGET'} <= {a['reason'] for a in audits}
    assert {1, -1} <= {a['side'] for a in audits}
    assert len(reproduction) == 3
    positive = [{'id': cid, 'cost': cost, 'n': scenario['metrics']['trade_count'], 'mean_net_bps': scenario['metrics']['mean_net_bps'],
        'label': 'EXPLORATORY_POSITIVE_LEAD_NEEDS_NEW_PROSPECTIVE_FREEZE_AND_INDEPENDENT_VALIDATION'}
        for cid, result in outcome['candidates'].items() for cost, scenario in result['scenarios'].items()
        if scenario['metrics']['mean_net_bps'] is not None and scenario['metrics']['mean_net_bps'] > 0]
    outcome['positive_descriptive_rows'] = positive
    outcome['terminal'] = 'ACTUAL_23_EXECUTABLE_DEV_REANALYSIS_POSITIVE_LEAD_UNVALIDATED' if positive else 'ACTUAL_23_EXECUTABLE_DEV_REANALYSIS_COMPLETED_NEGATIVE'
    outcome['finished_at_utc'] = datetime.now(UTC).isoformat()
    outcome['scenario_count'] = 46
    outcome['candidate_cost_fold_books'] = 23 * 2 * 35
    outcome['base_stress_trade_observations_not_independent'] = sum(s['metrics']['trade_count'] for c in outcome['candidates'].values() for s in c['scenarios'].values())
    write_json(OUT / 'REANALYSIS_R2_DECIMAL_AUDITS.json', {'scientific_grade': GRADE, 'real_checks': len(audits), 'checks': audits})
    write_json(OUT / 'REANALYSIS_R2_DETERMINISM.json', {'scientific_grade': GRADE, 'selected_real_fold_reruns': reproduction})
    write_json(OUT / 'REANALYSIS_R2_RESULTS.json', outcome)
    return outcome


def events_per_fold_as_json(events_per_fold):
    return {f'{y}-{m:02d}': events for (y, m), events in events_per_fold.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code-sha', required=True)
    args = parser.parse_args()
    try:
        run(args.code_sha)
    except (ValueError, AssertionError, FileNotFoundError, OSError) as exc:
        OUT.mkdir(exist_ok=True)
        failure = {'task_id': TASK, 'scientific_grade': GRADE, 'terminal': 'REAL_REANALYSIS_STOP_SOURCE_OR_ACCOUNTING_INTEGRITY',
                   'exception': type(exc).__name__, 'counterexample': str(exc), 'code_sha': args.code_sha}
        write_json(OUT / 'REANALYSIS_R2_HARD_BLOCKER.json', failure)
        raise


if __name__ == '__main__':
    main()
