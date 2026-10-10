"""Render measured tables from aggregate JSON, without further policy trials."""
from __future__ import annotations

import json

from .sources import EVIDENCE, ROOT


def f(value, digits=2):
    return 'NA' if value is None else f'{value:.{digits}f}'


def main():
    results=json.loads((EVIDENCE/'AGGREGATE_RESULTS.json').read_text())
    source=json.loads((EVIDENCE/'SOURCE_TIME_VERSION_MANIFEST.json').read_text())
    registry=json.loads((EVIDENCE/'FROZEN_STRATEGY_REGISTRY.json').read_text())
    by={(r['candidate'],r['cost_case']):r for r in results['rows']}
    out=[
        '# BTC 4–24h public empirical discovery: measured decision',
        '',
        f"**Terminal: `{results['terminal']}`. Shortlist: {results['shortlisted']}.**",
        '',
        'No frozen candidate clears the joint cost, support and uncertainty gate. This is a finite developmental screen of five April windows, not a claim that all BTC strategies lack an edge. No entry recommendation or effective preregistration results from this experiment.',
        '',
        '## Authority and chronology',
        '',
        f"Task `{registry['TASK_ID']}`. Controller `{registry['controller_dispatch_sha']}`; immutable Prompt `{registry['prompt_commit_sha']}`; clean code base `{registry['exact_start_sha']}`. Dedicated branch `feature/v06-bline-g2-btc-public-empirical-fast-r1`.",
        '',
        f"The signed outcome-blind roster and all five windows were committed and pushed at `{results['freeze_sha']}` before the first CSV price-body read ({source['first_price_csv_read_at_utc']}). Registry SHA256 `{results['registry_sha256']}`. Both registry and signature ledger remain exact bytes of the first commit. Ephemeral Ed25519 signatures bind the registry and timestamp/hash payload; they are self-generated research signatures, not an external identity or trusted-time certificate. The remote first push supplies the observable sequence.",
        '',
        'Requested root model: Codex GPT-6 Sol High; actual root model and effort are NOT_EXPOSED. Two bounded implementation workers handled signals and replay using the observable implementer tool role (GPT-6 Sol, Medium); the parent froze the experiment, checked semantics, ran actual data, inferred results and owns this decision. Workers used synthetic inputs only.',
        '',
        '## Independently downloaded input and rights',
        '',
        'Only official Binance Vision USD-M BTCUSDT perpetual trade-price 1m ZIPs for March and April 2021–2025 were downloaded, with their .CHECKSUM files. All ten now pass SHA256, exact CSV member/schema, finite ordered OHLC/volume, close=open+59,999ms and exact dense UTC minute calendar checks. The first 2023-04 ZIP attempt had a TLS transport failure (HTTP 0, curl 35); the same authorized URL was retried successfully, preserving the original attempt. No year or month was substituted.',
        '',
        f"Verified {sum(r['price_rows'] for r in source['records']):,} price rows; duplicate/gap/out-of-order counts all zero. Each March contributes 44,640 warmup rows, each April 43,200. Scores are exactly [April 2 00:00, April 30 00:00) UTC (40,320 minutes per era), after 24h purge at each April edge. Every planned hold must fit the window; tails and intervening years are neither scored nor exposed. 'Year' below means that year's selected April screen, never full-year performance or an annualized projection.",
        '',
        'Exact URLs, response headers, HTTP versions, archive and CSV digests, row counts, parser fields, UTC extrema and retrieval clocks are in SOURCE_TIME_VERSION_MANIFEST.json. Current corrected archive bytes are not historical publication/known-at proof: this is event-time reconstruction with +60s availability, not source-PIT admission. Spot and Coin-M were not mixed in. True-minute Mark and signed known-at/ownership Funding are NOT_ACQUIRED/UNKNOWN; historical fees, lot/tick filters and source-PIT publication clocks remain unproved.',
        '',
        'Provider attribution: [Binance public data](https://github.com/binance/binance-public-data) / Binance Vision. Observed [Terms v1.0, 2026-08-26](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md) license data and derived analytical artifacts under CC BY-NC-SA 4.0 for this noncommercial, personal, nonproduction research. Commercial/live signal use requires separate rights. Raw prices/ZIPs/full account and trade ledgers remain in task-owned /tmp scratch and are not rehosted in Git; derived evidence/report carry the stated attribution/license. Generic code does not turn the dataset into MIT-licensed data.',
        '',
        '## Measurement and original-protocol distinction',
        '',
        'The frozen registry contains 12 policy variants: original structural-continuation and closed-retest LONG/SHORT ×4h/12h, plus four fixed bidirectional challengers (three 8h, one 24h). Same-trigger horizons are dependent trials, not independent samples. No parameter fit, grid, extra direction trial, alternative window or outcome-driven retune was used. Retest trend timing ambiguity is explicitly recorded: the BTC price shadow checks trend at breakout and confirmation; this is not a silent grant to rewrite original protocol identity.',
        '',
        'Original8 full protocol is NOT_EVALUABLE and cannot enter the shortlist: true Mark/Funding, fee/filter/PIT source and three-asset support are missing, and BTC-only 100% fails the original <=60% single-asset positive screen. Price-shadow results below retain their original IDs/formula geometry and are diagnostic only. The original 12h unknown-hourly stress geometry needs stop >=2×(44+8×12+tick buffer)>280bp against the frozen 250bp cap; it is ineligible, not an empirically losing 12h strategy. Original4h can be geometrically feasible, but no stops are widened to create trades.',
        '',
        'Signals observe completed UTC 15m/1h/4h bars; 60 completed 4h bars precede eligibility. Event is the exclusive bar end, decision=end+60s, fill=end+120s next minute open. One position per candidate/cost account, no capital pooling or leverage multiplier. Gap veto is 0.25 current hour ATR. Stop fixed at the registered formula, target rounded conservatively at 2R; both protections hit in one minute -> stop first. Adverse stop gap uses worse open (including horizon expiry), favorable target gap is capped; normal expiry uses the first eligible open. Delayed ACK prevents reusing closing cash; original cooldown is4h, challengers1h except24h compression4h.',
        '',
        'BASE proxies 6bp fee+2bp spread+3bp slippage each leg (nominal22bp roundtrip); STRESS 12+4+6 each leg (44bp). Fees use actual executed notional once per leg; spread/slippage are embedded once in adverse tick-rounded execution. Changing exit notional and rounding make realized cost slightly different from nominal22/44bp. These are assumptions, not actual Binance achieved economics. Funding is excluded from these reported account returns, never credited. Lot .001BTC, tick .1USDT, minnotional5USDT are assumed historical proxies.',
        '',
        'Each book starts at1,000USDT with5% equity reserve; original books allocate at most1/3 and carry cash/highwater across eras, challengers reset independently per era. Quantity includes conservative entry, 1.10 exit-cost and 1.10 adverse hourly-funding reserves (reserving is not pretending to know a settled bill); no cash debit is manufactured for unknown Funding. A100USDT drawdown threshold uses the last available trade-price close (i-2) and queues next-open liquidation/disable. The threshold can overshoot because of causal delay and gaps. Dense MTM is a trade-close liquidation-cost proxy, not true Mark or native margin. R is net after proxy costs / fixed effective initial stop risk; bps and account returns use entry notional and cash, never leveraged margin return.',
        '',
        'Minute account equity/exposure and daily PnL are computed from all scored1m prices. Trade-close drawdown samples only settled trade economics, dense MTM uses each close and exit costs; original overall DD carries across folds, challenger overall DD is max per independent era. MAE/MFE are full touched-minute high/low envelopes including possibly later price inside the exit minute, not an asserted observed path. Gross turnover uses full original quantity at final price; if a partial reduction occurs it would be an approximation, explicitly recorded (see ledger partial_reductions).',
        '',
        '## All variants: pooled trade diagnostics and equal-era economics',
        '',
        'Pooled mean/median below weight trades; equal-era mean weights each available era equally and is undefined if any era has zero trades. The gate uses STRESS equal-era mean, not whichever averaging looks better. Counts in BASE/STRESS can differ because equity, stops/targets rounded from effective entry, sizing and causal drawdown disable are recomputed per cost book.',
        '',
        '| Variant | Horizon | N BASE/STRESS | Mean net bp BASE/STRESS | Median STRESS bp | Equal-era STRESS bp | STRESS PF / win% | STRESS mean R | Max close/dense DD% |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for c in registry['candidates']:
        a,b=by[c['id'],'BASE'],by[c['id'],'STRESS']
        out.append(f"| {c['id']} | {c['horizon_hours']} | {a['trades']}/{b['trades']} | {f(a['mean_net_bps'])}/{f(b['mean_net_bps'])} | {f(b['median_net_bps'])} | {f(b['weekly_bootstrap']['equal_era_net_bps'])} | {f(b['profit_factor'])}/{f(None if b['win_rate'] is None else b['win_rate']*100)} | {f(b['mean_net_R'])} | {f(b['max_trade_close_drawdown_pct'])}/{f(b['max_dense_MTM_drawdown_pct'])} |")
    out += ['', 'PAUSE has zero trades, fees, exposure and USDT yield/return; R and mean trade bps are undefined. Range expansion has a positive increment over a weak balanced control but negative absolute net in every STRESS era; that is not a profitable opportunity.', '',
            '## Per-variant, per-era complete results', '',
            'NA denotes undefined with zero trades. win/L are percentages, PF is net-USDT profit factor; duration is median minutes. Full min/q25/median/q75/max duration, side proportions, per-day PnL/exposure, fees, MAE/MFE, tails, WAIT reasons and gross metrics are in AGGREGATE_RESULTS.json. No excluded or empty era is omitted.', '']
    for c in registry['candidates']:
        out += [f"### {c['id']}", '',
                '| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |',
                '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for cost in ['BASE','STRESS']:
            for x in by[c['id'],cost]['folds']:
                out.append(f"| {x['fold']} | {cost} | {x['trades']} | {f(x['mean_net_bps'])} | {f(x['median_net_bps'])} | {f(None if x['win_rate'] is None else x['win_rate']*100)} | {f(x['profit_factor'])} | {f(x['mean_net_R'])} | {f(x['account_return_pct'])} | {f(x['trade_close_drawdown_pct'])}/{f(x['dense_trade_price_MTM_drawdown_pct'])} | {f(x['active_minutes_pct'])} | {f(None if x['long_share'] is None else x['long_share']*100)} | {f(None if x['duration_minutes_quantiles'] is None else x['duration_minutes_quantiles']['median'])} |")
        out += ['', '**Frozen gate failures (STRESS):** '+', '.join(by[c['id'],'STRESS']['shortlist_failures'])+'.', '']
    out += ['## Controls, dependence and uncertainty', '',
            'At each filled parent timestamp, the no-signal LONG and SHORT episodes use the same raw stop-distance magnitude, quantity, horizon and cost book; balanced control is their mean on the same parent entry-notional denominator. Episodes are unfunded, overlap freely and do not use parent drawdown disable: this is a paired entry-time benchmark, not a tradable control portfolio or a randomized causal treatment. No control clock is selected from later prices. Full paired outcomes are in the private trade ledger, aggregate long/short/balanced and parent increments in results.', '',
            '10,000 deterministic resamples, seed17012025, shared UTC Monday week calendars within era, equal-era estimand; no-trade calendar weeks remain. Dependence from overlapping positions/signals is clustered by entry week. Fixed14d blocks from each score start are a coarser dependence sensitivity; max24h tails can cross a week, so neither estimate proves independence. Two estimands ×12 variants=24 familywise comparisons, one-sided lower quantile .05/24, plus95% intervals. No permutation p-value or IID trade t-test is claimed.', '',
            'If a resample has a zero-trade era, its equal-era mean is undefined. For conservative lower bounds this mass is assigned -infinity; JSON null at such a bound means UNBOUNDED_BELOW_FROM_UNDEFINED_RESAMPLE, never a zero or omitted favorable estimate. Original zero-trade eras have undefined inference and support failure. Low support remains a failure even if a descriptive bound happens to be finite.', '',
            '| STRESS variant with trades | Equal-era net / incremental bp | Net95% interval | Week adjusted net/increment LCB | Undefined week draws% | 14d adjusted net/increment LCB |',
            '|---|---:|---|---:|---:|---:|']
    for c in registry['candidates']:
        x=by[c['id'],'STRESS']
        if x['trades']:
            a=x['weekly_bootstrap'];b=x['two_week_bootstrap']
            out.append(f"| {c['id']} | {f(a['equal_era_net_bps'])}/{f(a['equal_era_incremental_bps'])} | {a['net_ci95']} | {f(a['adjusted_net_LCB_bps'])}/{f(a['adjusted_incremental_LCB_bps'])} | {f(None if 'undefined_sample_fraction' not in a else a['undefined_sample_fraction']*100)} | {f(b['adjusted_net_LCB_bps'])}/{f(b['adjusted_incremental_LCB_bps'])} |")
    out += ['', 'Frozen shortlist requires >=3 complete eras, >=20 trades in EACH era (>=100 total for these five), >=80% nonnegative STRESS eras, equal-era mean>=5bp, median>=-5bp, PF>=1.1, max trade-close DD<=10%, worst5% mean>=-300bp, both adjusted absolute/incremental lower bounds>0 for weeks and14d. Original8 cannot inherit a BTC positive claim. No candidate satisfies all conditions; the favorable BASE range-expansion 2022 subfold is explicitly retained, but selecting it after seeing all years would violate the freeze.', '',
            '## Adverse regime and funding sensitivities', '',
            'ATR/hour volatility bins (<50bp,50–100bp,>=100bp) are descriptive post-freeze units only, not entry filters, optimized regimes or shortlist inputs. Every populated bin is shown in JSON; negative bins were not discarded. All observed gap-stop losses and gross losses beyond raw stop due to gap are counted, not inferred from drawdown. These counts are zero in the present filled sample; this does not prove future gap safety.', '',
            '| STRESS variant with trades | Mean MAE/MFE bp | Worst5% mean bp | Gap losses / beyond-stop gap losses | Net mean after UTC8h adverse4/8bp | Net mean after unknown-hourly4/8bp |',
            '|---|---:|---:|---:|---:|---:|']
    for c in registry['candidates']:
        x=by[c['id'],'STRESS']
        if x['trades']:
            a=x['funding_sensitivity']['UTC8H_ASSUMED_SCHEDULE']['mean_net_after_adverse_bps']
            b=x['funding_sensitivity']['UNKNOWN_HOURLY_STRESS']['mean_net_after_adverse_bps']
            out.append(f"| {c['id']} | {f(x['mean_mae_bps'])}/{f(x['mean_mfe_bps'])} | {f(x['worst5pct_mean_bps'])} | {x['stop_gap_losses']}/{x['loss_beyond_raw_stop_bps']} | {f(a['4'])}/{f(a['8'])} | {f(b['4'])}/{f(b['8'])} |")
    out += ['', 'Funding sensitivities are ex-post arithmetic debits, not guessed historical settlements or a second cash/liquidation replay. Settlement eligibility uses worst ownership within UTC boundary ±15s; notional uses the touched-minute high envelope and original quantity conservatively even after a partial reduction. Positive/negative actual rates and side ownership are unknown; no fake credits are taken. Adverse4/8bp can only lower these episode nets. The UTC8h schedule is an assumption, never a verified cadence; unknown hourly is separately displayed.', '',
            '| Maximum hold | Worst possible UTC8h windows incl ±15s | Unknown-hourly windows incl ±15s |',
            '|---:|---:|---:|']
    for h,x in results['funding_max_boundary_counts'].items():
        out.append(f"| {h}h | {x['UTC8H']} | {x['UNKNOWN_HOURLY']} |")
    out += ['', 'A horizon aligned at both endpoints can conservatively touch two settlement boundaries; hence8h may count2,24h4. Original static cost geometry retains its frozen hourly maxhold bound, while this explicit ownership uncertainty sensitivity includes endpoint windows; neither is a verified actual bill.', '',
            '## Audit, reproducibility and delivery evidence', '',
            f"Executed {results['total_candidate_cost_trades']} candidate/cost trade observations (BASE/STRESS are dependent replays, not independent unique trades), 12 variants×2 costs×5 complete eras. Full trade and decision/WAIT ledgers plus 120 dense account archives are outside Git; every digest/size is in the aggregate ledger_manifest. Trade ledger SHA256 `{next(p['sha256'] for p in results['ledger_manifest'] if p['name']=='trade_ledger.jsonl')}`. The complete aggregate and all ledger hashes reproduce byte-for-byte on a second identical execution, with no policy changes between the two final runs.", '',
            'Three actual episodes are selected deterministically: earliest simple LONG, earliest simple SHORT, earliest gap-stop else first remaining simple episode. Independent Decimal tick/execution, each-leg fees and first-hit minute walkthrough call no replay helpers and all pass; DRAWDOWN_KILL/partial-reduction episodes are excluded from this small arithmetic audit and not claimed certified by it. Synthetic assertions separately test causal drawdown, overlap, ACK, filters, same-bar stop-first, adverse gaps, expiry, cost-once, clocks, coverage, determinism and source corruption. Exact local commands/counts, dependency versions and code hashes are in EXECUTION_RECEIPT.json.', '',
            'Implementation-to-freeze review corrected ATR first-TR seeding and pending retest handling/strict failed-breakout comparison; these are implementation repairs to pre-pushed constants, not outcome-driven rule changes. The final deterministic run pair uses the repaired frozen semantics. Initial import collection with a bare pytest executable lacked repository root on sys.path; task test modules now bootstrap their repo-relative path, and final bare pytest plus python-m invocation are checked. No existing tests, CI, strategy formulas or Controller documents were changed.', '',
            'Only the four allowed task file namespaces are committed; no reviews/, market rows, ZIP/CSV/npy/npz/full ledger, original owner data, protected2026/forward/H39-H41/A-line outcome or private exchange API was accessed. No P1/P2 engine or security repair was imported. Focused checks suffice for this task; repository CI starts on push and its exact current status is reported externally with the final SHA, without repeatedly waiting for full historical CI or waiving H40.', '',
            '## Decision and next authority', '',
            'Terminal NO_STRATEGY_CLEARS_COST_AND_SUPPORT_GATE applies only to these fixed rules, clocks, proxy costs and five finite developmental April windows. Three filled8h challengers are net-negative; the24h variant is unsupported because it never triggers, not proved economically negative. Original4h retest shadows have only a few trades and incomplete protocol; structural/12h rows are zero or ineligible. There are zero hypothesis cards to promote. Do not change thresholds/horizons/windows using these observed losses under this one-shot authority.', '',
            'Any next experiment needs separate Controller authority, prospectively different identity and fresh finite budget/validation. True Mark/Funding, source known-at rights, exchange historical fees/filters, out-of-sample replication and actual execution would still need independent admission. P2 source/perpetual economics UNKNOWN; P3 effective prereg, P4, testnet/live and real funds remain unauthorized. This measured screen provides an evidence-based stop rather than an unmeasured plan.', '',
            'Derived report/evidence: Binance Vision attribution, CC BY-NC-SA4.0, noncommercial nonproduction research.', '']
    path=ROOT/'docs/strategy_research/g2_r3/empirical_fast_r1/BTC_4_24H_EMPIRICAL_DISCOVERY_REPORT.md'
    path.write_text('\n'.join(out))


if __name__=='__main__':
    main()
