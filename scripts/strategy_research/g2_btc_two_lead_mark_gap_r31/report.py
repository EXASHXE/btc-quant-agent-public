"""Render final full or partial measured science, never synthetic price returns."""
from __future__ import annotations

import json

from .gaps import SCRATCH
from .run import EP, GRADE, ROOT


def f(value):
    return 'UNKNOWN' if value is None else f'{float(value):.4f}'


def publish():
    result=json.loads((SCRATCH/'R31_ECONOMIC_RESULTS.json').read_text())
    source=json.loads((SCRATCH/'R31_COMPOSITE_SOURCE_MANIFEST.json').read_text())
    EP.mkdir(parents=True,exist_ok=True)
    for name in ('R31_ECONOMIC_RESULTS.json','R31_COMPOSITE_SOURCE_MANIFEST.json','R31_GAP_SOURCE_RECEIPTS.json'):
        (EP/name).write_bytes((SCRATCH/name).read_bytes())
    full=result['terminal']=='R31_TWO_LEAD_OBSERVED_FUNDING_MARK_COMPLETE_DEVELOPMENT_ONLY'
    lines=['# Fixed two12h BTC leads — gap repair and observed Funding/Mark economics R3.1','',
        '**'+GRADE+'**','',f"Terminal `{result['terminal']}`. **No Alpha, OOS, promotion, later holdout or trading authority.**",'',
        'Frozen implementation `'+result['frozen_code_sha']+'`; Controller `6b08af95335a4d577e1367a9b0652258bad1ca35`; start `057c47a4bfd248131f4fd94d12d3deef73c65e1f`.',
        f"Original authenticated Mark rows1,565,280 preserved; inserted {source['composite_added_rows']:,} gap rows; composite {source['composite_rows']:,}/1,576,800. Actual signed Funding events3285; original Last rows1,576,800. All36 months2021–23 retained; Jan2021warmup and35scoremonths/24hpurge unchanged.",'',
        '## Actual eight-day source recovery','',
        '| UTC gap day | Daily rows | API rows | Still missing | Authentication/cross-source |',
        '|---|---:|---:|---:|---|']
    for d in source['gap_source_receipts']:
        p=d.get('provenance_counts',{});missing=1440-d.get('rows',0)
        lines.append(f"| {d['day']} | {p.get('PROVIDER_DAILY_ZIP_SHA256_AUTHENTICATED',0)} | {p.get('PROVIDER_API_SECONDARY_NOT_ZIP_AUTHENTICATED',0)} | {missing} | No direct same-clock monthly overlap (entire days missing); daily SHA authentic, API has lower transport provenance |")
    lines += ['', 'All daily/API requests were frozen before body inspection. Only exact8days requested, daily first, API only its remaining missing intervals. Existing monthly values were never overwritten; clock-counts, OHLC, duplicates, overlap tolerances and source hashes were checked. API rows are `PROVIDER_API_SECONDARY_NOT_ZIP_AUTHENTICATED`, never equated to provider SHA ZIP. Repair is retrospective and does not establish2021publicationknown-at. R3 public cache was read-only and signature/hash verified; new bodies/ledgers only in R31scratch.','','## Measured two-lead comparison','', '**'+GRADE+'**','']
    if full:
        lines += ['| Candidate | Cost | N baseline/funded | Before Funding bp | Fixed-trade Funding bp | Funded bp | Net PF funded | Mark DD funded % | Funded1000USDT return % | Funding debit/credit USDT | 48FW7/14d LCB funded |', '|---|---|---|---:|---:|---:|---:|---:|---:|---|---|']
        for cid,c in result['candidates'].items():
            for cost,record in c['costs'].items():
                b=record['baseline'];ov=record['cash_neutral_same_trade_overlay'];fd=record['funding_aware_funded_replay']
                lines.append(f"| `{cid}` | {cost} | {b['trade_count']}/{fd['trade_count']} | {f(b['mean_net_bps'])} | {f(ov['mean_net_bps'])} | {f(fd['mean_net_bps'])} | {f(fd['net_profit_factor'])} | {f(fd['max_mtm_drawdown_pct'])} | {f(fd['cash_return_pct'])} | {f(fd['funding_debits_usdt'])}/{f(fd['funding_credits_usdt'])} | {f(fd['bootstrap_7d']['familywise_lcb_48'])}/{f(fd['bootstrap_14d']['familywise_lcb_48'])} |")
        lines += ['', 'No-funding full trade/event/control ledger and uncompressed minute cash curve SHA exactly matched R2. STRESS n34/+11.504bp and n55/+19.132bp precede observed funding. Baseline execution remains Last-price based; repaired Mark never determines entries/stops/targets/fills. Cash-neutral means selection/quantity fixed; its diagnostic cash equity includes funding. Funding-aware uses settled past cash for future quantities; cash reconciliation/month continuity are audited.','']
        for cid,c in result['candidates'].items():
            lines += ['### '+cid,'','**'+GRADE+'**','']
            for cost,record in c['costs'].items():
                for view in ('cash_neutral_same_trade_overlay','funding_aware_funded_replay'):
                    m=record[view];lines += [f'**{cost} / {view} / '+GRADE+'**','',
                        '| Year | N | Gross bp | Net bp | Net R | Net PF | Mark DD % | Funded cash return % | Signed Funding USDT | LONG/SHORT N |',
                        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
                    for year,y in sorted(m['yearly_breakdown'].items()):
                        lines.append(f"| {year} | {y['n_trades']} | {f(y['gross_mean_bps'])} | {f(y['mean_net_bps'])} | {f(y['mean_net_R'])} | {f(y['net_profit_factor'])} | {f(y['mark_mtm_dd_pct'])} | {f(y['cash_return_pct'])} | {f(y['funding_signed_usdt'])} | {y['long_n']}/{y['short_n']} |")
                    lines += ['',f"Matched balanced-control increment={f(m['mean_paired_increment_bps'])}bp; PAUSE=0. Side diagnostics={m['side']}. Signed funding total={f(m['funding_signed_usdt'])}USDT, {m['settlement_attributions']} event/trade attributions; {m['no_settlement_trades']} trades cross no settlement in complete observed stream. Extra roundtrip cost drag sensitivity mean bp={m['additional_roundtrip_drag_mean_net_bps']}; descriptive gross+funding break-even friction={f(m['descriptive_gross_break_even_friction_bps'])}bp. This is not a maker-fill or optimized cost claim.",'']
                lines += [f'**{cost} monthly funded accounts / '+GRADE+'**','',
                    '| Month | Baseline N | Funded N | Overlay funding USDT | Funded end cash | Within-month Mark DD % |','|---|---:|---:|---:|---:|---:|']
                for month in record['monthly']:
                    lines.append(f"| {month['year']}-{month['month']:02d} | {month['baseline_n']} | {month['funded_n']} | {f(month['funding_signed_cash_overlay'])} | {f(month['funded_end'])} | {f(month['mark_dd_funded_within_month'])} |")
                lines += ['']
        lines += ['## Independent settlement audits and timing','','At least5 real independent Decimal funding episodes, both sides and2021/2022/2023, are in machine results. Rates remain signed decimal fractions; positive LONG pays, SHORT credits, negative reverses. Settlements use `[entry,exit)`; each trade also records±60sec boundary sensitivities. Archive funding has no exact associated settlement Mark: latest **completed**1mMark close is a notional approximation, explicitly below exact exchange cash-authenticity. Both funding and Mark historical original publication known-at remain UNPROVEN.','']
    else:
        lines += ['**Mark_MTM_STATUS=INCOMPLETE.** Complete Funding-only known amounts do not imply complete Mark risk or full economic admission. Unknown required Mark is not zero or Last-price substituted Mark.','',
            '| Candidate | Cost | Baseline N | Fully covered trades | Known funding events % | Known signed Funding USDT | Full-period adjusted mean | Mark MTM |','|---|---|---:|---|---:|---:|---:|---|']
        for cid,c in result['candidates'].items():
            for cost,r in c.items():
                m=r['coverage'];lines.append(f"| `{cid}` | {cost} | {m['trade_count']} | {m['fully_covered_trade_count']}/{m['trade_count']} | {f(m['event_coverage_pct'])} | {f(m['known_signed_cash_usdt'])} | {f(m['full_period_after_funding_mean_net_bps'])} | INCOMPLETE |")
                lines += ['',f"{cid}/{cost}: missing trade IDs={m['unknown_trade_ids']}; missing event/trade pairs={m['unknown_event_pairs']}; byyear={r['by_year']}; byside={r['by_side']}. Fully-covered subset values are separate from full-period results and not strategy selection.",'']
        lines += ['', 'Source gaps/failures remain exactly in source receipt request/hash/status logs. Per-trade sign-only amounts are unbounded from admitted source where required Mark is missing; no fabricated price bound. No conditional month dropping.','']
    lines += ['## Scientific limits and immutable inheritance','','The two hypotheses were selected on exposed development;48 historical A+B comparisons are retained in fixed UTC7/14d bootstrap seed42/10000 with empty weeks and undefined lower bounds asnull. Even favorable economics is not confirmatory Alpha or promotion. 2021-driven positives and2023 loss remain visible in yearly tables; no new thresholds, directions, holding periods, costs or trials.','',
        'Fees/spread/slip are unchanged BASE22/STRESS44 proxies; actual fee tiers/L2/maker queue acceptance UNKNOWN.5% reserve and1x admission are enforced; transient marked notional/equity above1x is diagnostic, not an invented liquidation engine. Side Mark risk is within-trade conditional actual-account DD, not a separately funded side strategy. Raw source/full trade/equity arrays are outside Git with SHA; all originalR3/R2 code/report/evidence byte unchanged.','',
        'Binance Vision attribution: derived data artifacts/report under [CCBYNCSA4.0 dataset terms](https://raw.githubusercontent.com/binance/binance-public-data/master/TERMS_AND_CONDITIONS.md), noncommercialnonproduction research. Current source repair supplies no commercial/live rights.','',
        'Focused synthetic checks>=15, Ruff/compile/JSON and independent source/account review are recorded in execution receipt; exact final CI status is observed afterpush, no fullCI/H40loop. Root requestedSolHigh; actual rootmodel/effort not exposed.','','## Narrow reproduction','','```bash',f"python3.12 -m scripts.strategy_research.g2_btc_two_lead_mark_gap_r31.run --code-sha {result['frozen_code_sha']}",'python3.12 -m pytest -q tests/test_v06_g2_btc_two_lead_mark_gap_r31_*.py','ruff check scripts/strategy_research/g2_btc_two_lead_mark_gap_r31 tests/test_v06_g2_btc_two_lead_mark_gap_r31_*.py','```','Completed own scratch refuses repeatfullrun. Independent replication requires unchanged frozenimplementation and fresh task-owned scratch; reuse only verifiedread-onlyR3monthlycache. No new outcome-search wave.','']
    dp=ROOT/'docs/strategy_research/g2_r3/two_lead_mark_gap_r31';dp.mkdir(parents=True,exist_ok=True)
    (dp/'R31_TWO_LEAD_OBSERVED_FUNDING_MARK_REPORT.md').write_text('\n'.join(lines))


if __name__=='__main__':publish()
