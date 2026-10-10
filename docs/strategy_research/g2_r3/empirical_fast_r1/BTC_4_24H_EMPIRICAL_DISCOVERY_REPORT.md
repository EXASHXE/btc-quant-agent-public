# BTC 4–24h public empirical discovery: measured decision

**Terminal: `NO_STRATEGY_CLEARS_COST_AND_SUPPORT_GATE`. Shortlist: [].**

No frozen candidate clears the joint cost, support and uncertainty gate. This is a finite developmental screen of five April windows, not a claim that all BTC strategies lack an edge. No entry recommendation or effective preregistration results from this experiment.

## Authority and chronology

Task `V06_G2_BTC_PUBLIC_EMPIRICAL_FAST_DISCOVERY_R1`. Controller `4259846a64a422c3eced029bb791ed7e29dc9265`; immutable Prompt `7717b229a5d600170b1e33947eec200c997d3221`; clean code base `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`. Dedicated branch `feature/v06-bline-g2-btc-public-empirical-fast-r1`.

The signed outcome-blind roster and all five windows were committed and pushed at `21ee4c11b789d54aca6c602ce5c84426a3944fde` before the first CSV price-body read (2026-10-10T16:52:24.374713+00:00). Registry SHA256 `79fc9e020f258c410b5612b44c60e94563df8c659053ff15aba89efd4daf7b35`. Both registry and signature ledger remain exact bytes of the first commit. Ephemeral Ed25519 signatures bind the registry and timestamp/hash payload; they are self-generated research signatures, not an external identity or trusted-time certificate. The remote first push supplies the observable sequence.

Requested root model: Codex GPT-6 Sol High; actual root model and effort are NOT_EXPOSED. Two bounded implementation workers handled signals and replay using the observable implementer tool role (GPT-6 Sol, Medium); the parent froze the experiment, checked semantics, ran actual data, inferred results and owns this decision. Workers used synthetic inputs only.

## Independently downloaded input and rights

Only official Binance Vision USD-M BTCUSDT perpetual trade-price 1m ZIPs for March and April 2021–2025 were downloaded, with their .CHECKSUM files. All ten now pass SHA256, exact CSV member/schema, finite ordered OHLC/volume, close=open+59,999ms and exact dense UTC minute calendar checks. The first 2023-04 ZIP attempt had a TLS transport failure (HTTP 0, curl 35); the same authorized URL was retried successfully, preserving the original attempt. No year or month was substituted.

Verified 439,200 price rows; duplicate/gap/out-of-order counts all zero. Each March contributes 44,640 warmup rows, each April 43,200. Scores are exactly [April 2 00:00, April 30 00:00) UTC (40,320 minutes per era), after 24h purge at each April edge. Every planned hold must fit the window; tails and intervening years are neither scored nor exposed. 'Year' below means that year's selected April screen, never full-year performance or an annualized projection.

Exact URLs, response headers, HTTP versions, archive and CSV digests, row counts, parser fields, UTC extrema and retrieval clocks are in SOURCE_TIME_VERSION_MANIFEST.json. Current corrected archive bytes are not historical publication/known-at proof: this is event-time reconstruction with +60s availability, not source-PIT admission. Spot and Coin-M were not mixed in. True-minute Mark and signed known-at/ownership Funding are NOT_ACQUIRED/UNKNOWN; historical fees, lot/tick filters and source-PIT publication clocks remain unproved.

Provider attribution: [Binance public data](https://github.com/binance/binance-public-data) / Binance Vision. Observed [Terms v1.0, 2026-08-26](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md) license data and derived analytical artifacts under CC BY-NC-SA 4.0 for this noncommercial, personal, nonproduction research. Commercial/live signal use requires separate rights. Raw prices/ZIPs/full account and trade ledgers remain in task-owned /tmp scratch and are not rehosted in Git; derived evidence/report carry the stated attribution/license. Generic code does not turn the dataset into MIT-licensed data.

## Measurement and original-protocol distinction

The frozen registry contains 12 policy variants: original structural-continuation and closed-retest LONG/SHORT ×4h/12h, plus four fixed bidirectional challengers (three 8h, one 24h). Same-trigger horizons are dependent trials, not independent samples. No parameter fit, grid, extra direction trial, alternative window or outcome-driven retune was used. Retest trend timing ambiguity is explicitly recorded: the BTC price shadow checks trend at breakout and confirmation; this is not a silent grant to rewrite original protocol identity.

Original8 full protocol is NOT_EVALUABLE and cannot enter the shortlist: true Mark/Funding, fee/filter/PIT source and three-asset support are missing, and BTC-only 100% fails the original <=60% single-asset positive screen. Price-shadow results below retain their original IDs/formula geometry and are diagnostic only. The original 12h unknown-hourly stress geometry needs stop >=2×(44+8×12+tick buffer)>280bp against the frozen 250bp cap; it is ineligible, not an empirically losing 12h strategy. Original4h can be geometrically feasible, but no stops are widened to create trades.

Signals observe completed UTC 15m/1h/4h bars; 60 completed 4h bars precede eligibility. Event is the exclusive bar end, decision=end+60s, fill=end+120s next minute open. One position per candidate/cost account, no capital pooling or leverage multiplier. Gap veto is 0.25 current hour ATR. Stop fixed at the registered formula, target rounded conservatively at 2R; both protections hit in one minute -> stop first. Adverse stop gap uses worse open (including horizon expiry), favorable target gap is capped; normal expiry uses the first eligible open. Delayed ACK prevents reusing closing cash; original cooldown is4h, challengers1h except24h compression4h.

BASE proxies 6bp fee+2bp spread+3bp slippage each leg (nominal22bp roundtrip); STRESS 12+4+6 each leg (44bp). Fees use actual executed notional once per leg; spread/slippage are embedded once in adverse tick-rounded execution. Changing exit notional and rounding make realized cost slightly different from nominal22/44bp. These are assumptions, not actual Binance achieved economics. Funding is excluded from these reported account returns, never credited. Lot .001BTC, tick .1USDT, minnotional5USDT are assumed historical proxies.

Each book starts at1,000USDT with5% equity reserve; original books allocate at most1/3 and carry cash/highwater across eras, challengers reset independently per era. Quantity includes conservative entry, 1.10 exit-cost and 1.10 adverse hourly-funding reserves (reserving is not pretending to know a settled bill); no cash debit is manufactured for unknown Funding. A100USDT drawdown threshold uses the last available trade-price close (i-2) and queues next-open liquidation/disable. The threshold can overshoot because of causal delay and gaps. Dense MTM is a trade-close liquidation-cost proxy, not true Mark or native margin. R is net after proxy costs / fixed effective initial stop risk; bps and account returns use entry notional and cash, never leveraged margin return.

Minute account equity/exposure and daily PnL are computed from all scored1m prices. Trade-close drawdown samples only settled trade economics, dense MTM uses each close and exit costs; original overall DD carries across folds, challenger overall DD is max per independent era. MAE/MFE are full touched-minute high/low envelopes including possibly later price inside the exit minute, not an asserted observed path. Gross turnover uses full original quantity at final price; if a partial reduction occurs it would be an approximation, explicitly recorded (see ledger partial_reductions).

## All variants: pooled trade diagnostics and equal-era economics

Pooled mean/median below weight trades; equal-era mean weights each available era equally and is undefined if any era has zero trades. The gate uses STRESS equal-era mean, not whichever averaging looks better. Counts in BASE/STRESS can differ because equity, stops/targets rounded from effective entry, sizing and causal drawdown disable are recomputed per cost book.

| Variant | Horizon | N BASE/STRESS | Mean net bp BASE/STRESS | Median STRESS bp | Equal-era STRESS bp | STRESS PF / win% | STRESS mean R | Max close/dense DD% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| STRUCTURAL_CONTINUATION_LONG_04H | 4 | 0/0 | NA/NA | NA | NA | NA/NA | NA | 0.00/0.00 |
| STRUCTURAL_CONTINUATION_LONG_12H | 12 | 0/0 | NA/NA | NA | NA | NA/NA | NA | 0.00/0.00 |
| STRUCTURAL_CONTINUATION_SHORT_04H | 4 | 0/0 | NA/NA | NA | NA | NA/NA | NA | 0.00/0.00 |
| STRUCTURAL_CONTINUATION_SHORT_12H | 12 | 0/0 | NA/NA | NA | NA | NA/NA | NA | 0.00/0.00 |
| CLOSED_RETEST_LONG_04H | 4 | 4/4 | -85.27/-107.21 | -92.35 | NA | 0.00/0.00 | -0.58 | 1.19/1.39 |
| CLOSED_RETEST_LONG_12H | 12 | 0/0 | NA/NA | NA | NA | NA/NA | NA | 0.00/0.00 |
| CLOSED_RETEST_SHORT_04H | 4 | 3/3 | -5.64/-27.63 | -18.11 | NA | 0.33/33.33 | -0.10 | 0.35/0.99 |
| CLOSED_RETEST_SHORT_12H | 12 | 0/0 | NA/NA | NA | NA | NA/NA | NA | 0.00/0.00 |
| TREND_PULLBACK_08H | 8 | 89/73 | -50.62/-72.03 | -61.67 | -79.11 | 0.16/17.81 | -0.53 | 10.14/10.20 |
| RANGE_EXPANSION_08H | 8 | 147/126 | -18.56/-31.41 | -79.76 | -34.30 | 0.57/34.13 | -0.27 | 9.95/10.02 |
| FAILED_BREAKOUT_08H | 8 | 133/83 | -40.99/-67.69 | -89.54 | -69.42 | 0.17/16.87 | -0.88 | 9.99/10.12 |
| IMPULSE_COMPRESSION_24H | 24 | 0/0 | NA/NA | NA | NA | NA/NA | NA | 0.00/0.00 |

PAUSE has zero trades, fees, exposure and USDT yield/return; R and mean trade bps are undefined. Range expansion has a positive increment over a weak balanced control but negative absolute net in every STRESS era; that is not a profitable opportunity.

## Per-variant, per-era complete results

NA denotes undefined with zero trades. win/L are percentages, PF is net-USDT profit factor; duration is median minutes. Full min/q25/median/q75/max duration, side proportions, per-day PnL/exposure, fees, MAE/MFE, tails, WAIT reasons and gross metrics are in AGGREGATE_RESULTS.json. No excluded or empty era is omitted.

### STRUCTURAL_CONTINUATION_LONG_04H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2021 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |

**Frozen gate failures (STRESS):** ORIGINAL_PROTOCOL_NOT_EVALUABLE_NOT_POSITIVE, INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, TAIL_LOSS, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### STRUCTURAL_CONTINUATION_LONG_12H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2021 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |

**Frozen gate failures (STRESS):** ORIGINAL_PROTOCOL_NOT_EVALUABLE_NOT_POSITIVE, INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, TAIL_LOSS, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### STRUCTURAL_CONTINUATION_SHORT_04H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2021 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |

**Frozen gate failures (STRESS):** ORIGINAL_PROTOCOL_NOT_EVALUABLE_NOT_POSITIVE, INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, TAIL_LOSS, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### STRUCTURAL_CONTINUATION_SHORT_12H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2021 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |

**Frozen gate failures (STRESS):** ORIGINAL_PROTOCOL_NOT_EVALUABLE_NOT_POSITIVE, INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, TAIL_LOSS, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### CLOSED_RETEST_LONG_04H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 2 | -136.30 | -136.30 | 0.00 | 0.00 | -0.77 | -0.74 | 0.74/0.74 | 0.86 | 100.00 | 173.50 |
| 2022 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | BASE | 1 | -16.46 | -16.46 | 0.00 | 0.00 | -0.09 | -0.05 | 0.05/0.30 | 0.60 | 100.00 | 240.00 |
| 2024 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | BASE | 1 | -52.04 | -52.04 | 0.00 | 0.00 | -0.26 | -0.15 | 0.15/0.37 | 0.60 | 100.00 | 240.00 |
| 2021 | STRESS | 2 | -158.18 | -158.18 | 0.00 | 0.00 | -0.86 | -0.86 | 0.86/0.86 | 0.86 | 100.00 | 173.50 |
| 2022 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | STRESS | 1 | -38.47 | -38.47 | 0.00 | 0.00 | -0.21 | -0.12 | 0.12/0.37 | 0.60 | 100.00 | 240.00 |
| 2024 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | STRESS | 1 | -74.01 | -74.01 | 0.00 | 0.00 | -0.36 | -0.21 | 0.21/0.41 | 0.60 | 100.00 | 240.00 |

**Frozen gate failures (STRESS):** ORIGINAL_PROTOCOL_NOT_EVALUABLE_NOT_POSITIVE, INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### CLOSED_RETEST_LONG_12H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2021 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |

**Frozen gate failures (STRESS):** ORIGINAL_PROTOCOL_NOT_EVALUABLE_NOT_POSITIVE, INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, TAIL_LOSS, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### CLOSED_RETEST_SHORT_04H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 1 | 3.86 | 3.86 | 100.00 | NA | 0.02 | 0.01 | 0.00/0.77 | 0.60 | 0.00 | 240.00 |
| 2022 | BASE | 1 | 69.93 | 69.93 | 100.00 | NA | 0.33 | 0.20 | 0.00/0.47 | 0.60 | 0.00 | 240.00 |
| 2023 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | BASE | 1 | -90.71 | -90.71 | 0.00 | 0.00 | -0.37 | -0.28 | 0.28/0.43 | 0.60 | 0.00 | 240.00 |
| 2025 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2021 | STRESS | 1 | -18.11 | -18.11 | 0.00 | 0.00 | -0.07 | -0.05 | 0.05/0.77 | 0.60 | 0.00 | 240.00 |
| 2022 | STRESS | 1 | 48.03 | 48.03 | 100.00 | NA | 0.22 | 0.13 | 0.00/0.47 | 0.60 | 0.00 | 240.00 |
| 2023 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | STRESS | 1 | -112.80 | -112.80 | 0.00 | 0.00 | -0.46 | -0.35 | 0.35/0.50 | 0.60 | 0.00 | 240.00 |
| 2025 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |

**Frozen gate failures (STRESS):** ORIGINAL_PROTOCOL_NOT_EVALUABLE_NOT_POSITIVE, INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### CLOSED_RETEST_SHORT_12H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2021 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |

**Frozen gate failures (STRESS):** ORIGINAL_PROTOCOL_NOT_EVALUABLE_NOT_POSITIVE, INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, TAIL_LOSS, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### TREND_PULLBACK_08H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 16 | -71.30 | -83.67 | 25.00 | 0.23 | -0.41 | -9.90 | 9.90/10.04 | 15.61 | 75.00 | 480.00 |
| 2022 | BASE | 24 | -38.18 | -60.03 | 20.83 | 0.36 | -0.36 | -8.17 | 8.54/9.87 | 22.18 | 8.33 | 480.00 |
| 2023 | BASE | 22 | -20.68 | -28.44 | 31.82 | 0.47 | -0.26 | -4.12 | 5.01/5.40 | 24.46 | 59.09 | 480.00 |
| 2024 | BASE | 14 | -69.71 | -49.32 | 28.57 | 0.11 | -0.37 | -8.64 | 8.64/9.88 | 12.88 | 28.57 | 480.00 |
| 2025 | BASE | 13 | -78.26 | -80.41 | 15.38 | 0.24 | -0.49 | -8.87 | 9.54/10.04 | 11.12 | 61.54 | 369.00 |
| 2021 | STRESS | 14 | -84.77 | -134.60 | 21.43 | 0.18 | -0.52 | -10.14 | 10.14/10.14 | 13.39 | 85.71 | 480.00 |
| 2022 | STRESS | 15 | -66.06 | -78.09 | 13.33 | 0.12 | -0.64 | -8.73 | 8.73/9.92 | 14.80 | 6.67 | 480.00 |
| 2023 | STRESS | 22 | -42.00 | -50.45 | 22.73 | 0.24 | -0.44 | -8.21 | 8.32/9.09 | 24.46 | 59.09 | 480.00 |
| 2024 | STRESS | 13 | -83.04 | -74.58 | 15.38 | 0.06 | -0.46 | -9.22 | 9.22/10.18 | 12.21 | 30.77 | 480.00 |
| 2025 | STRESS | 9 | -119.69 | -145.68 | 11.11 | 0.21 | -0.67 | -9.46 | 9.90/10.20 | 7.33 | 44.44 | 311.00 |

**Frozen gate failures (STRESS):** INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, TRADE_CLOSE_DRAWDOWN, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### RANGE_EXPANSION_08H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 24 | -43.98 | -83.63 | 37.50 | 0.43 | -0.28 | -9.26 | 9.62/10.07 | 21.86 | 58.33 | 480.00 |
| 2022 | BASE | 35 | 10.48 | -44.28 | 40.00 | 1.17 | 0.02 | 3.07 | 5.47/6.57 | 28.30 | 51.43 | 370.00 |
| 2023 | BASE | 30 | -33.70 | -71.11 | 26.67 | 0.50 | -0.39 | -9.06 | 9.95/9.95 | 21.03 | 40.00 | 260.50 |
| 2024 | BASE | 23 | -11.35 | -42.34 | 47.83 | 0.82 | 0.09 | -2.92 | 8.87/9.67 | 17.25 | 39.13 | 322.00 |
| 2025 | BASE | 35 | -21.95 | -28.40 | 31.43 | 0.62 | -0.28 | -6.64 | 8.96/9.84 | 26.56 | 45.71 | 377.00 |
| 2021 | STRESS | 19 | -54.96 | -113.66 | 36.84 | 0.34 | -0.40 | -9.32 | 9.50/9.96 | 18.49 | 63.16 | 480.00 |
| 2022 | STRESS | 35 | -8.47 | -66.27 | 40.00 | 0.86 | -0.14 | -3.05 | 7.88/8.83 | 28.83 | 51.43 | 370.00 |
| 2023 | STRESS | 27 | -38.44 | -86.29 | 25.93 | 0.46 | -0.44 | -9.30 | 9.95/10.02 | 19.97 | 40.74 | 302.00 |
| 2024 | STRESS | 22 | -21.84 | -33.17 | 40.91 | 0.73 | 0.01 | -4.43 | 9.05/9.64 | 16.90 | 40.91 | 326.50 |
| 2025 | STRESS | 23 | -47.78 | -38.82 | 26.09 | 0.31 | -0.44 | -9.41 | 9.41/9.95 | 19.48 | 34.78 | 480.00 |

**Frozen gate failures (STRESS):** INSUFFICIENT_PER_ERA_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### FAILED_BREAKOUT_08H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 23 | -46.11 | -66.26 | 21.74 | 0.33 | -0.62 | -9.15 | 9.81/9.99 | 9.55 | 47.83 | 139.00 |
| 2022 | BASE | 22 | -50.28 | -63.03 | 18.18 | 0.18 | -0.74 | -9.65 | 9.65/10.04 | 9.85 | 59.09 | 98.00 |
| 2023 | BASE | 32 | -34.66 | -59.23 | 18.75 | 0.32 | -0.56 | -9.77 | 9.77/10.00 | 16.31 | 59.38 | 157.00 |
| 2024 | BASE | 25 | -40.42 | -56.62 | 32.00 | 0.39 | -0.40 | -8.94 | 9.46/9.91 | 13.60 | 56.00 | 122.00 |
| 2025 | BASE | 31 | -37.58 | -67.05 | 22.58 | 0.33 | -0.64 | -10.03 | 10.03/10.19 | 11.82 | 48.39 | 112.00 |
| 2021 | STRESS | 19 | -55.86 | -87.71 | 26.32 | 0.30 | -0.74 | -9.22 | 9.83/10.02 | 8.75 | 36.84 | 174.00 |
| 2022 | STRESS | 13 | -85.96 | -88.70 | 15.38 | 0.06 | -1.11 | -9.77 | 9.77/10.00 | 5.72 | 53.85 | 125.00 |
| 2023 | STRESS | 15 | -75.83 | -89.74 | 6.67 | 0.03 | -1.14 | -9.99 | 9.99/10.12 | 8.29 | 46.67 | 175.00 |
| 2024 | STRESS | 20 | -57.82 | -74.65 | 25.00 | 0.25 | -0.58 | -9.86 | 9.86/10.07 | 12.24 | 60.00 | 162.00 |
| 2025 | STRESS | 16 | -71.63 | -93.94 | 6.25 | 0.14 | -1.02 | -9.91 | 9.91/10.01 | 6.08 | 43.75 | 110.50 |

**Frozen gate failures (STRESS):** INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

### IMPULSE_COMPRESSION_24H

| Year | Cost | N | Mean bp | Median bp | win% | PF | meanR | Cash return% | Close/dense DD% | active% | LONG% | duration median min |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | BASE | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2021 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2022 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2023 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2024 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |
| 2025 | STRESS | 0 | NA | NA | NA | NA | NA | 0.00 | 0.00/0.00 | 0.00 | NA | NA |

**Frozen gate failures (STRESS):** INSUFFICIENT_PER_ERA_SUPPORT, INSUFFICIENT_TOTAL_SUPPORT, NOT_ROBUST_ACROSS_ERAS, STRESS_EQUAL_ERA_MEAN, STRESS_MEDIAN, STRESS_PROFIT_FACTOR, TAIL_LOSS, WEEK_ADJUSTED_NET_LCB_BPS, WEEK_ADJUSTED_INCREMENTAL_LCB_BPS, 14DAY_ADJUSTED_NET_LCB_BPS, 14DAY_ADJUSTED_INCREMENTAL_LCB_BPS.

## Controls, dependence and uncertainty

At each filled parent timestamp, the no-signal LONG and SHORT episodes use the same raw stop-distance magnitude, quantity, horizon and cost book; balanced control is their mean on the same parent entry-notional denominator. Episodes are unfunded, overlap freely and do not use parent drawdown disable: this is a paired entry-time benchmark, not a tradable control portfolio or a randomized causal treatment. No control clock is selected from later prices. Full paired outcomes are in the private trade ledger, aggregate long/short/balanced and parent increments in results.

10,000 deterministic resamples, seed17012025, shared UTC Monday week calendars within era, equal-era estimand; no-trade calendar weeks remain. Dependence from overlapping positions/signals is clustered by entry week. Fixed14d blocks from each score start are a coarser dependence sensitivity; max24h tails can cross a week, so neither estimate proves independence. Two estimands ×12 variants=24 familywise comparisons, one-sided lower quantile .05/24, plus95% intervals. No permutation p-value or IID trade t-test is claimed.

If a resample has a zero-trade era, its equal-era mean is undefined. For conservative lower bounds this mass is assigned -infinity; JSON null at such a bound means UNBOUNDED_BELOW_FROM_UNDEFINED_RESAMPLE, never a zero or omitted favorable estimate. Original zero-trade eras have undefined inference and support failure. Low support remains a failure even if a descriptive bound happens to be finite.

| STRESS variant with trades | Equal-era net / incremental bp | Net95% interval | Week adjusted net/increment LCB | Undefined week draws% | 14d adjusted net/increment LCB |
|---|---:|---|---:|---:|---:|
| CLOSED_RETEST_LONG_04H | NA/NA | None | NA/NA | NA | NA/NA |
| CLOSED_RETEST_SHORT_04H | NA/NA | None | NA/NA | NA | NA/NA |
| TREND_PULLBACK_08H | -79.11/-32.32 | [None, -65.6834433061884] | NA/NA | 3.00 | NA/NA |
| RANGE_EXPANSION_08H | -34.30/10.01 | [None, -18.628046244487912] | NA/NA | 2.99 | -61.28/-15.01 |
| FAILED_BREAKOUT_08H | -69.42/-22.78 | [None, -57.311832696771475] | NA/NA | 4.93 | NA/NA |

Frozen shortlist requires >=3 complete eras, >=20 trades in EACH era (>=100 total for these five), >=80% nonnegative STRESS eras, equal-era mean>=5bp, median>=-5bp, PF>=1.1, max trade-close DD<=10%, worst5% mean>=-300bp, both adjusted absolute/incremental lower bounds>0 for weeks and14d. Original8 cannot inherit a BTC positive claim. No candidate satisfies all conditions; the favorable BASE range-expansion 2022 subfold is explicitly retained, but selecting it after seeing all years would violate the freeze.

## Adverse regime and funding sensitivities

ATR/hour volatility bins (<50bp,50–100bp,>=100bp) are descriptive post-freeze units only, not entry filters, optimized regimes or shortlist inputs. Every populated bin is shown in JSON; negative bins were not discarded. All observed gap-stop losses and gross losses beyond raw stop due to gap are counted, not inferred from drawdown. These counts are zero in the present filled sample; this does not prove future gap safety.

| STRESS variant with trades | Mean MAE/MFE bp | Worst5% mean bp | Gap losses / beyond-stop gap losses | Net mean after UTC8h adverse4/8bp | Net mean after unknown-hourly4/8bp |
|---|---:|---:|---:|---:|---:|
| CLOSED_RETEST_LONG_04H | -117.42/20.73 | -205.66 | 0/0 | -110.20/-113.19 | -120.16/-133.12 |
| CLOSED_RETEST_SHORT_04H | -88.80/156.23 | -112.80 | 0/0 | -28.95/-30.28 | -43.63/-59.63 |
| TREND_PULLBACK_08H | -88.58/89.75 | -264.06 | 0/0 | -75.21/-78.39 | -98.51/-124.99 |
| RANGE_EXPANSION_08H | -83.05/117.03 | -216.90 | 0/0 | -34.24/-37.06 | -53.13/-74.86 |
| FAILED_BREAKOUT_08H | -65.98/65.65 | -175.60 | 0/0 | -69.19/-70.68 | -80.76/-93.83 |

Funding sensitivities are ex-post arithmetic debits, not guessed historical settlements or a second cash/liquidation replay. Settlement eligibility uses worst ownership within UTC boundary ±15s; notional uses the touched-minute high envelope and original quantity conservatively even after a partial reduction. Positive/negative actual rates and side ownership are unknown; no fake credits are taken. Adverse4/8bp can only lower these episode nets. The UTC8h schedule is an assumption, never a verified cadence; unknown hourly is separately displayed.

| Maximum hold | Worst possible UTC8h windows incl ±15s | Unknown-hourly windows incl ±15s |
|---:|---:|---:|
| 12h | 2 | 13 |
| 24h | 4 | 25 |
| 4h | 1 | 5 |
| 8h | 2 | 9 |

A horizon aligned at both endpoints can conservatively touch two settlement boundaries; hence8h may count2,24h4. Original static cost geometry retains its frozen hourly maxhold bound, while this explicit ownership uncertainty sensitivity includes endpoint windows; neither is a verified actual bill.

## Audit, reproducibility and delivery evidence

Executed 665 candidate/cost trade observations (BASE/STRESS are dependent replays, not independent unique trades), 12 variants×2 costs×5 complete eras. Full trade and decision/WAIT ledgers plus 120 dense account archives are outside Git; every digest/size is in the aggregate ledger_manifest. Trade ledger SHA256 `4071ebf70f4b2b9635af8f653b8209ed90908e1c98cf820e270a950340f95d77`. The complete aggregate and all ledger hashes reproduce byte-for-byte on a second identical execution, with no policy changes between the two final runs.

Three actual episodes are selected deterministically: earliest simple LONG, earliest simple SHORT, earliest gap-stop else first remaining simple episode. Independent Decimal tick/execution, each-leg fees and first-hit minute walkthrough call no replay helpers and all pass; DRAWDOWN_KILL/partial-reduction episodes are excluded from this small arithmetic audit and not claimed certified by it. Synthetic assertions separately test causal drawdown, overlap, ACK, filters, same-bar stop-first, adverse gaps, expiry, cost-once, clocks, coverage, determinism and source corruption. Exact local commands/counts, dependency versions and code hashes are in EXECUTION_RECEIPT.json.

Implementation-to-freeze review corrected ATR first-TR seeding and pending retest handling/strict failed-breakout comparison; these are implementation repairs to pre-pushed constants, not outcome-driven rule changes. The final deterministic run pair uses the repaired frozen semantics. Initial import collection with a bare pytest executable lacked repository root on sys.path; task test modules now bootstrap their repo-relative path, and final bare pytest plus python-m invocation are checked. No existing tests, CI, strategy formulas or Controller documents were changed.

Only the four allowed task file namespaces are committed; no reviews/, market rows, ZIP/CSV/npy/npz/full ledger, original owner data, protected2026/forward/H39-H41/A-line outcome or private exchange API was accessed. No P1/P2 engine or security repair was imported. Focused checks suffice for this task; repository CI starts on push and its exact current status is reported externally with the final SHA, without repeatedly waiting for full historical CI or waiving H40.

## Decision and next authority

Terminal NO_STRATEGY_CLEARS_COST_AND_SUPPORT_GATE applies only to these fixed rules, clocks, proxy costs and five finite developmental April windows. Three filled8h challengers are net-negative; the24h variant is unsupported because it never triggers, not proved economically negative. Original4h retest shadows have only a few trades and incomplete protocol; structural/12h rows are zero or ineligible. There are zero hypothesis cards to promote. Do not change thresholds/horizons/windows using these observed losses under this one-shot authority.

Any next experiment needs separate Controller authority, prospectively different identity and fresh finite budget/validation. True Mark/Funding, source known-at rights, exchange historical fees/filters, out-of-sample replication and actual execution would still need independent admission. P2 source/perpetual economics UNKNOWN; P3 effective prereg, P4, testnet/live and real funds remain unauthorized. This measured screen provides an evidence-based stop rather than an unmeasured plan.

Derived report/evidence: Binance Vision attribution, CC BY-NC-SA4.0, noncommercial nonproduction research.
