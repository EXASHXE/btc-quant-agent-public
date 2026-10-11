"""Render completed machine results; publication never consumes market bodies."""
from __future__ import annotations

import argparse
import json

from .reanalysis_r2_run import EP, GRADE, ORIGINAL, OUT, ROOT, START, TASK


def f(value, digits=3):
    return 'N/A' if value is None else f'{value:.{digits}f}'


def publish() -> None:
    results = json.loads((OUT / 'REANALYSIS_R2_RESULTS.json').read_text())
    original = {}
    for wave in range(1,5):
        original.update(json.loads((EP / f'WAVE_{wave:02d}_RESULT.json').read_text())['candidates'])
    for name in ('REANALYSIS_R2_RESULTS.json', 'REANALYSIS_R2_SOURCE_RECEIPT.json',
                 'REANALYSIS_R2_DECIMAL_AUDITS.json', 'REANALYSIS_R2_DETERMINISM.json'):
        (EP / name).write_bytes((OUT / name).read_bytes())
    lines = ['# Real BTC fixed-23 code-as-executed economic replay R2', '',
        f'**{GRADE}**', '', f"Terminal: `{results['terminal']}`. **No automatic promotion, holdout access, Alpha or trading authority.**", '',
        f'Task `{TASK}`; original A `{ORIGINAL}`, R2 starting `{START}`; frozen corrected implementation `{results["identity"]["corrected_code_sha"]}`.',
        'Prompt `681087557fb774a110500282fcd5e20fa17bc949`; Controller `bfe9f5df1bf55e7738cfbff58ce32e674edab683`.', '',
        f"Actually verified **36 official ZIPs and fresh provider CHECKSUMs / {results['minute_rows']:,} UTC minute rows**, 2021Jan–2023Dec. 2021Jan warmup; all35 original scoring months Feb2021–Dec2023, original24h signal-edge purge. **23 fixed strategies ×2 costs ×35 funded monthly books =1610 books**, {results['base_stress_trade_observations_not_independent']:,} BASE/STRESS trade observations (dependent replays, not independent sample total).", '',
        'All original signal function ASTs and the23 branch fingerprints match a377. W1_C06 is listed invalid and not rerun or repaired. Extra-minute entry delay and horizon-minute OPEN TIME_CAP follow Controller-selected original code identity. Original parameter objects, directions/filters, horizons, stop/target/cooldown settings and all original/R1 evidence remain unchanged. This is reused exposed development, never a newly blind sample.', '',
        '## Measured before/after economics', '', f'**{GRADE} — all corrected estimates are cost proxies.**', '',
        '| Candidate | Hold h | Old N | Old near80bp net | BASE N/net bp | STRESS N/net bp | Equal-year STRESS bp | Net PF | Minute DD % | Account return % | Paired increment bp | 48FW LCB 7d/14d |',
        '|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---|']
    for cid, candidate in results['candidates'].items():
        b = candidate['scenarios']['BASE']['metrics']; s = candidate['scenarios']['STRESS']['metrics']
        old = original[cid]['stress_metrics']; sc = candidate['scenarios']['STRESS']
        lines.append(f"| `{cid}` | {candidate['candidate']['horizon_hours']} | {old['trade_count']} | {f(old['mean_net_bps'])} | {b['trade_count']}/{f(b['mean_net_bps'])} | {s['trade_count']}/{f(s['mean_net_bps'])} | {f(s['equal_year_net_bps'])} | {f(s['net_profit_factor'])} | {f(s['max_mtm_drawdown_pct'])} | {f(s['cash_return_pct'])} | {f(s['mean_paired_increment_bps'])} | {f(sc['bootstrap_7d']['familywise_lcb_48'])}/{f(sc['bootstrap_14d']['familywise_lcb_48'])} |")
    lines += ['', 'Old reports mislabeled near40/80bp realized transaction friction as22/44, gross PF as net, and settled DD as minute MTM. Those old figures are preserved as untrusted publications; the new account/ACK/reserve/cost implementation changes sizing, feasible targets and which events can fill. The comparison is a complete reanalysis, not an isolated subtraction of18/36bp from old identical trades.', '',
        '## Year, month and direction support', '', f'**{GRADE} — 2021 account year covers Feb–Dec score months; 2022/2023 Jan–Dec.**', '']
    for cid, candidate in results['candidates'].items():
        lines += [f'### {cid}', '', f'**{GRADE}**', '',
            '| Cost | Year | N | Gross mean bp | Net mean bp | Net median bp | Net PF | Funded year return % | Within-year minute DD % |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for cost, scenario in candidate['scenarios'].items():
            m = scenario['metrics']
            for year, annual in sorted(m['yearly_breakdown'].items()):
                lines.append(f"| {cost} | {year} | {annual['n_trades']} | {f(annual['mean_gross_bps'])} | {f(annual['mean_net_bps'])} | {f(annual['median_net_bps'])} | {f(annual['net_profit_factor'])} | {f(annual['funded_account']['cash_return_pct'])} | {f(annual['within_year_mtm_dd_pct'])} |")
            lines += ['', f"{cost}: LONG N={m['side']['long']['n']} net={f(m['side']['long']['mean_net_bps'])}bp; SHORT N={m['side']['short']['n']} net={f(m['side']['short']['mean_net_bps'])}bp. Active weeks={m['active_weeks_7d']}; months={m['months_covered']}; worst-year mean={f(m['worst_year_net_bps'])}bp; trade-close DD={f(m['max_trade_close_drawdown_pct'])}%; largest month's fraction of sum absolute monthly P&L={f(m['month_abs_pnl_dominance_fraction'])}. Exit reasons={m['exit_reasons']}; event fates={scenario['event_fates']}.", '',
                f"Counterfactual balanced mean={f(scenario['controls']['balanced_mean_net_bps'])}bp, PAUSE=0, paired increment={f(m['mean_paired_increment_bps'])}bp. Individual pairs overlap on {scenario['controls']['overlapping_pair_entries']} entries: this is **nontradable event-paired economics**, not a pooled funded control cash curve. Actual strategy continuous1000USDT account is shown separately. Descriptive strict gate={scenario['descriptive_gate']['verdict']}; failing gates={[k for k,v in scenario['descriptive_gate']['gates'].items() if not v['passed']]}. No result automatically promotes.", '',
                '| Month | N | Mean gross bp | Mean net bp | Median net bp | Cash return % | Minute DD % | LONG/SHORT N |',
                '|---|---:|---:|---:|---:|---:|---:|---|']
            for month in scenario['months']:
                lines.append(f"| {month['year']}-{month['month']:02d} | {month['n']} | {f(month['mean_gross_bps'])} | {f(month['mean_net_bps'])} | {f(month['median_net_bps'])} | {f(month['month_cash_return_pct'])} | {f(month['within_month_mtm_dd_pct'])} | {month['long']['n']}/{month['short']['n']} |")
            fs = scenario['funding_sensitivity']
            lines += ['', 'Hypothetical adverse funding mean net bp: '+', '.join(f"{cadence}h/{rate}bp={f(fs[f'adverse_{rate}bp_{cadence}h_offset_0s']['mean_net_after_funding_bps'])}" for cadence in (8,1) for rate in (4,8))+'. Signed ±4/±8bp8h and ±15sec settlement-clock bounds are in machine JSON; hypothetical credits are not observed income.', '']
    lines += ['## Interpretation and limits', '', f'**{GRADE}**', '',
        'A positive BASE or STRESS mean earns only `EXPLORATORY_POSITIVE_LEAD_NEEDS_NEW_PROSPECTIVE_FREEZE_AND_INDEPENDENT_VALIDATION`. Strict descriptive support/gates are separately shown; small N, missing years, negative familywise bounds, adverse funding, or large DD cannot be hidden by positive point estimates. All positive rows are preserved in machine `positive_descriptive_rows`; none authorizes a reserved read. Zero events are N/A and source-supported finite negative results are not universal proof of no edge.', '',
        'The actual strategy account starts1000USDT, remains continuous across all35 months, caps admission at min(settled equity,1000), 5% reserve, no borrowing. Short marked notional can grow above equity after adverse price moves: machine `max_marked_exposure_ratio` and breach minutes disclose this rather than claiming a continuous1x invariant. No unregistered dynamic deleveraging or favorable kill fills were added. Minute trade-price close minus hypothetical liquidation costs is equity, not verified exchange Mark. Exit ACK constrains reusable cash; cooldown remains measured from original exit time with ACK as a floor. An ex ante max-hold+ACK score-end guard prevents future-dependent rejection of late month-end events.', '',
        'BASE each leg6fee+2halfspread+3slip; STRESS12+4+6. Fees charged once on actual executed notional, target fills receive no maker discount. Tick and changing exit notional alter realized nominal bp. Funding reserve1.10×unknown-hourly8bp×hold is a budget reservation, not an observed cash payment. Separate signed/adverse settlement sensitivities use fixed trade notional and exit interval, do not change entries or claim real Funding/Mark/fees/filter histories; changing marks at settlement is unobserved.', '',
        'Inference uses identical calendar7/14d bootstrap draws seed42/10000, all missing/no-trade weeks retained, one-sided alpha0.05/48; zero-support/undefined samples give null bounds. 48 is prior combined A+B experiment multiplicity, not23 convenient comparisons. Paired contrast intervals are descriptive diagnostics, not additional selection trials. Independent week assumptions/market dependence and ex-post implementation identity prevent confirmatory Alpha claims even with positive lower bounds.', '',
        'Source archive SHA/checksum/CSV hashes and provider fetch metadata are recorded. Current official historical archives may incorporate corrections; provider checksum does not prove historical known-at. Binance public-data attribution and noncommercial research rights limits apply; no raw rows, full trade/position or minute equity arrays are in Git. Selected real fold replays and independent Decimal first-hit audits include STOP/TIME/TARGET and both directions. Tests/receipt and original-artifact hashes are recorded separately.', '',
        '## Narrow reproduction', '', '```bash',
        f'python3.12 -m scripts.strategy_research.g2_gemini_goal_trend_flow_r1.reanalysis_r2_run --code-sha {results["identity"]["corrected_code_sha"]}',
        'python3.12 -m pytest -q tests/test_v06_gemini_goal_trend_flow_r1_*.py',
        'ruff check scripts/strategy_research/g2_gemini_goal_trend_flow_r1 tests/test_v06_gemini_goal_trend_flow_r1_*.py',
        '```', '', 'CLI refuses to repeat a completed full task in its existing scratch. Independent replication can use a fresh isolated copy of the same frozen implementation and task scratch; no parameter/month retune. The completed run already includes three selected nonempty deterministic real-fold reruns.', '']
    (ROOT / 'docs/strategy_research/g2_r3/gemini_goal_trend_flow_r1/REANALYSIS_R2_ACTUAL_PRICE_REPORT.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    publish()
