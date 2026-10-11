"""Publish one-shot evidence; failures suppress all new-cell optimistic P&L."""
from __future__ import annotations

import json
from pathlib import Path

from .run import dump
from .sources import EP, ROOT, SCRATCH
from .statistics import CONTRASTS, mean


def f(v):return 'UNKNOWN' if v is None else f'{float(v):.4f}'


def publish():
    if SCRATCH.is_symlink():raise ValueError("Unsafe scratch report refused")
    EP.mkdir(exist_ok=True,parents=True)
    dp=ROOT/'docs/strategy_research/g2_exit_horizon_r1';dp.mkdir(exist_ok=True,parents=True)
    failure=SCRATCH/'EXIT_R1_FAILURE.json'
    if failure.exists():
        r=json.loads(failure.read_text());dump(EP/'EXIT_R1_FAILURE.json',r)
        for name in ('E0_EXACT_IDENTITY_RECEIPT.json','SOURCE_IDENTITY.json'):
            if (SCRATCH/name).exists():(EP/name).write_bytes((SCRATCH/name).read_bytes())
        (dp/'EXIT_R1_EMPIRICAL_REPORT.md').write_text('# One-shot exit/horizon R1 — fail closed\n\nTerminal `'+r['terminal']+'`.\n\nObserved hard blocker: '+r['exception']+' / '+r['reason']+'.\n\nNo new-cell P&L is published. Frozen implementation was not changed after exposure, and no rerun or optimization occurred. E0/source receipts, where available, are separate from any new exit-policy authorization. No Alpha, policy validation, protected reads or trading.\n')
        return
    r=json.loads((SCRATCH/'EXIT_R1_RESULTS.json').read_text())
    for name in ('EXIT_R1_RESULTS.json','E0_EXACT_IDENTITY_RECEIPT.json','SOURCE_IDENTITY.json'):
        (EP/name).write_bytes((SCRATCH/name).read_bytes())
    ledgers=[]
    for cid,candidate in r['candidates'].items():
        for cost,record in candidate.items():
            for ref in [record['paired_ledger'],*[a['journal'] for a in record['account'].values()]]:
                p=Path(ref['path'])
                if p.parent!=SCRATCH or p.is_symlink():raise ValueError('Outside own journal scratch')
                (EP/p.name).write_bytes(p.read_bytes());ledgers.append({**ref,'committed_path':str((EP/p.name).relative_to(ROOT))})
    dump(EP/'COMMITTED_LEDGER_MANIFEST.json',ledgers)
    lines=['# One-shot BTC exit policy × horizon R1','',f"Terminal `{r['terminal']}`.",'',
        '**DEVELOPMENT_ONLY, selected on exposed prior48 searches. No POLICY_VALIDATED/Alpha/OOS or trading authority.**','',
        'Controller `7293d3f97f2d81167fd6ea17e69e424065e19e41`; design `9a3ba717e0c8eea062d74a038f743f87d7ae1b94`; start `990c02b5479b3b14996f90fdbf677cb672ada81e`; frozen code `'+r['frozen_code_sha']+'`.',
        'Actual observable root model/effort: NOT_EXPOSED; requested GPT-6.1 Sol High. Ten cells, exactly eight new configurations; D1/D2 DESIGN_ONLY and not evaluated.','',
        '## Source and exact E0 gate','',
        'Read-only108 original2021–23 ZIP/checksum archives plus8 authenticatedR31DAILY gaps, no network redownload. Last/Mark1,576,800minutes, Funding3,285signedsettlements; exact compositeSHA per36months. No oldscratch writes or owner/protected source access. Fundingnotional=latest completed1mMark approximation, exact exchangeMark and historicalknown-at UNKNOWN. E0 exact full R2 trade/event/control and R31 funded ledgers plus uncompressed baseline/overlay/funded minute curves pass all four candidate/cost combinations before new cells.','',
        '## Independent full account (STRESS primary; BASE sensitivity)','',
        '| Lead | Cost | Scheme | N | Net bp | Net PF | Mean/median Net R | Account return % | Mark DD % | Funding cash | Fees cash | Weighted exit min |',
        '|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|']
    for cid,c in r['candidates'].items():
        for cost,p in c.items():
            for scheme,a in p['account'].items():
                m=a['metrics'];fees=m.get('fee_entry_usdt',0)+m.get('fee_exit_usdt',0)
                lines.append(f"| {cid} | {cost} | {scheme} | {m['trade_count']} | {f(m['mean_net_bps'])} | {f(m['net_profit_factor'])} | {f(m.get('mean_net_R'))}/{f(m.get('median_net_R'))} | {f(m['cash_return_pct'])} | {f(m['max_mtm_drawdown_pct'])} | {f(m['funding_signed_usdt'])} | {f(fees) if scheme!='E0' else 'see immutable ledger'} | {f(m.get('mean_weighted_exit_age_minutes',m['mean_duration_minutes']))} |")
    lines+=['','Full accounts independently reprocess the entire frozen signal stream. NewH1/H2 only alter deadline; original12h sizing/reservations remain frozen. Partial cash is not a concurrent-entry grant; final flatACK/cooldown gates entry. Cash journal records entryfee once, each tierfee atfill, pricePnL atACK, actualremainingQ Funding atsettlement. Markequity includes pendingfill receivable without making it spendablecash. All actual maker/L2/fee tier histories UNKNOWN; BASE22/STRESS44 conservative proxies.','',
            '## Same-event paired effects and inference','',
            '| Lead | Cost | Contrast | Qualified N | Delta net bp | Delta Funding USDT | Delta fees USDT |',
            '|---|---|---|---:|---:|---:|---:|']
    for cid,c in r['candidates'].items():
        for cost,p in c.items():
            pairs=[json.loads(x) for x in Path(p['paired_ledger']['path']).read_text().splitlines()]
            for new,old in CONTRASTS:
                valid=[x for x in pairs if new in x['cells'] and old in x['cells']]
                delta=mean([float(x['cells'][new]['net_after_funding_bps'])-float(x['cells'][old]['net_after_funding_bps']) for x in valid])
                fund=mean([float(x['cells'][new]['funding_cash_usdt'])-float(x['cells'][old]['funding_cash_usdt']) for x in valid])
                fees=mean([sum(x['cells'][new][k]-x['cells'][old][k] for k in ('fee_entry','fee_exit')) for x in valid])
                lines.append(f'| {cid} | {cost} | {new}-{old} | {len(valid)} | {f(delta)} | {f(fund)} | {f(fees)} |')
            lines+=['',f"{cid}/{cost} support: {p['support']}.",'']
            matched=[]
            for x in pairs:
                a=x['execution_sensitivity'].get('E0/through');b=x['cells'].get('E1')
                if a and b and not a.get('ineligible'):matched.append(float(b['net_after_funding_bps'])-a['net_bps'])
            lines += [f"Execution-matched E1 minus strict-fill E0 diagnostic mean={f(mean(matched))}bp, n={len(matched)}. Raw E1-E0 includes changed limit-fill assumption and is **not a causal policy effect**. Paired ledger contains fixed E0/E1/E2 strict, one-bar-delay and first-confirmation-unfilled sensitivities for every eligible event, plus pre12/12–18/18–24h Last/Mark MFE/MAE; these are not selectable extra strategies.",'']
    lines+=['','| Cost | UTC block days | Contrast | Qualified N | Mean delta bp | Simultaneous LCB/UCB bp | Active/all blocks |',
            '|---|---:|---|---:|---:|---|---|']
    for cost,byblock in r['inference'].items():
        for block,inf in byblock.items():
            for x in inf.get('contrasts',[]):
                lines.append(f"| {cost} | {block} | {x['contrast']} | {x['qualified_n']} | {f(x['mean_delta_bps'])} | {f(x['simultaneous_LCB_bps'])}/{f(x['simultaneous_UCB_bps'])} | {x['nonempty_calendar_blocks']}/{x['total_calendar_blocks']} |")
    lines+=['','Centered two-sided max-|T| simultaneous8contrasts, seed42/10k shared UTC7/14d draws including zero-tradeblocks. Blockcounts describe support, not proved independenttrades. Adjustment is conditional-on-exposed-selected-leads; joint56vectors NOT_RECONSTRUCTED within budget and no confirmatoryAlpha. E2-E0 is additive/decomposition diagnostic only, never ninthselectioncontrast.','',
        '## Calendar, side, exit and account mechanisms','']
    for cid,c in r['candidates'].items():
        for cost,p in c.items():
            lines += [f'### {cid}/{cost}','', '| Scheme | Year | N | Mean net bp | Gross bp | Account return % | Funding cash |','|---|---|---:|---:|---:|---:|---:|']
            for scheme,a in p['account'].items():
                for year,y in a['metrics']['yearly_breakdown'].items():
                    lines.append(f"| {scheme} | {year} | {y['n_trades']} | {f(y['mean_net_bps'])} | {f(y.get('gross_mean_bps'))} | {f(y.get('cash_return_pct'))} | {f(y.get('funding_usdt',y.get('funding_signed_usdt')))} |")
                if scheme!='E0':
                    m=a['metrics'];lines += ['',f"{scheme}: exit shares={m['exit_reason_shares']}; tierreasons={m['exit_tier_reason_counts']}; partialN={m['partial_trade_count']}; touches-no-fill={m['touch_no_fill_count']}; occupiedminutes={a['occupied_minutes']}; peakMarknotional/equity={a['peak_exposure_ratio']}; conflicting-skipped signals={a['opportunity_cost_conflicts']}. Sidecash={m['side']}; per-tier fee sensitivity±2/5/10bp={m['additional_per_tier_roundtrip_fee_sensitivity_mean_bps']}. All35monthlybalances, skippedIDs/fates, reserves and orderjournals are in machine artifacts. Conflict count is measured availability loss, not invented foregonePnL.",'']
    lines+=['','## Paired2023mechanism (fixedevents, not account forecast)','','| Cost | Contrast | 2023 net delta bp | Gross delta bp | Funding delta bp | Fee delta bp | Weighted age delta min | TIME_CAP new/reference |','|---|---|---:|---:|---:|---:|---:|---|']
    for cost,rows in r['paired_contrast_decomposition'].items():
        for row in rows:
            y=row['calendar_mechanism']['2023']
            lines.append(f"| {cost} | {row['contrast']} | {f(row['year']['2023'])} | {f(y['gross_delta_bps'])} | {f(y['funding_delta_bps'])} | {f(y['fee_delta_bps'])} | {f(y['weighted_age_delta_minutes'])} | {y['TIME_CAP_n_new']}/{y['TIME_CAP_n_reference']} |")
    audit=r['independent_Decimal_audit'];lines+=['','## Independent real Decimal audit and scientific stop','',
        f"Independent source CSV/ZIP/Decimal audit: {audit['n']} real partialepisodes, LONG/SHORT and2022/2023; quantity, effective ticks, tierfees, cashjournal, residualquantity atsettlements, completedMark and signedrates independently recomputed. Closest actualTP1/settlement={audit['actual_TP1_nearest_settlement']}; actualwithin60s support={audit['actual_TP1_within_60sec_supported']}. No artificial shift of realTP1 to satisfy support; synthetic boundary cases are separate.",'',
        'Pre-frozen insufficiency includes >10% missing24h TIME_CAPpairs, any primaryqualifiedN<20, activecalendarblocks<8, any simultaneousinterval containingzero, or no actualTP1within60s audit support. Measurements remain reported as finite diagnostics; they do not warrant automaticfutureholdout access. A future independent chronologicaltest is justifiable only afterController source/executionL2 acceptance and a new finite hypothesis/fillprotocol, never selection of the best observed row.','',
        'No outcome-conditioned implementation revision or secondexecution. Source/fill/known-at/selection limitations remain. Dataset attribution: Binance officialpublic archives, noncommercialresearch under inherited providerterms. Finalpush/CIstatus and skips are reported separately aftercommit; a successful artifactCI is not fullregressionvalidation.','']
    (dp/'EXIT_R1_EMPIRICAL_REPORT.md').write_text('\n'.join(lines))


if __name__=='__main__':publish()
