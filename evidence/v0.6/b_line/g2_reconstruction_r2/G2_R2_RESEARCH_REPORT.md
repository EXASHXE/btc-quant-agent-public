# G2 R2 perpetual development reconstruction report

**Terminal: G2_R2_DIAGNOSTIC_ONLY. No shortlist, alpha acceptance, release or execution authority.**

Eight frozen directional candidates were evaluated on authentic Binance BTC/ETH/SOL USDT-M perpetual 1m archives. All eight had negative mean net R under base and doubled friction. All also fell below the preregistered 100 trades per chronological partition, and exact funding schedule uncertainty forced the uniform adverse proxy. The frozen NO_GO conditions therefore are not met; these are unfavorable diagnostic results rather than a supported universal negative verdict.

| Candidate | Trades | Gross mean R | Base mean net R | 2x mean net R | Fold counts |
|---|---:|---:|---:|---:|---|
| BREAKOUT_LONG_04H | 153 | -0.052 | -0.329 | -0.606 | 44, 45, 64 |
| BREAKOUT_LONG_12H | 137 | -0.063 | -0.354 | -0.644 | 42, 41, 54 |
| BREAKOUT_SHORT_04H | 166 | -0.056 | -0.274 | -0.492 | 51, 66, 49 |
| BREAKOUT_SHORT_12H | 143 | +0.023 | -0.210 | -0.442 | 47, 60, 36 |
| TREND_PULLBACK_LONG_04H | 125 | -0.061 | -0.278 | -0.496 | 44, 46, 35 |
| TREND_PULLBACK_LONG_12H | 104 | +0.002 | -0.241 | -0.484 | 36, 38, 30 |
| TREND_PULLBACK_SHORT_04H | 92 | -0.012 | -0.214 | -0.416 | 30, 39, 23 |
| TREND_PULLBACK_SHORT_12H | 77 | +0.091 | -0.129 | -0.349 | 25, 32, 20 |

## Method and immutable provenance

Method first push: `66aad50500bf6e860e76bf3ae8c0ef70799d5f47`; parent/code start `a56cc413d87a71111f2be02f10052dced9ff0275`. Method SHA256 `30245c01d445eaa1336faabd99140b791eb66b38a3ba4604ef6cbd30f25e0948`. Controller dispatch `fdcac0bfc7126f9715c4db3ba84581eb7a93256c`. Implementation `d38f7b45983cd74dc9e28439ebfb2fa60971122a` is the exact immutable code used by the final replay. The first remote HEAD was queried before any selected price/funding bodies were downloaded. Frozen candidates, windows, lag, fees, risk, scoring and support did not change.

April 2026 is warm-up only; May, June and July are three chronological developmental partitions. All are PRIOR_EXPOSED_OR_DEVELOPMENT, not fresh holdout. There are 527,040/527,040 authentic minutes (129,600 warm-up and 397,440 exploratory), 12 complete symbol-month price arrays, zero duplicate/gapped minutes, and 21 officially checksum-verified price/funding archives. No August extension or parameter fitting occurred.

Source manifest digest: `94bbecd5144705a2998198a9a48f29979e66b92e872cd40b59c50546c5525a77`. Scientific result digest: `888e60749be7ceb9a5236eae95f4f90c02dc885e2eb139a4f6fc5597b8710192`. Every archive/CSV/checksum URL, hash, retrieval UTC, publisher HTTP date, coverage and event bounds appears in SOURCE_AND_EXPOSURE_LEDGER.json. Raw files remain solely in the new task-specific /tmp cache; only reproducible derived observations are committed.

Eight candidates produced 997 trade observations in alternative strategy experiments; this is not 997 independent observations pooled across strategies. The evidence includes 79,488 decisions and 9,233 derived trade/control/latency rows. All configurations, failed screens, WAIT decisions and controls are retained. Natural observation identity is role + parent candidate + trade identity.

NO_GRID was frozen before prices and relinquishes four of the twelve possible slots. No grid, maker queue, paired-profit, inventory or underwater-performance inference is offered. OHLCV alone cannot establish realistic passive fill priority. R1 remains immutable/source-blocked, its code was not imported, and no R1 or G1 worktree was edited.

## Causality, costs and funding limitation

All data are ARCHIVAL_EVENT_TIME_RECONSTRUCTED. Completed earlier bars receive an assumed 60s availability lag; signals at hourly end+60s enter at the following minute (end+120s). There is no claim that those features were historically received live. Fifteen-minute, hourly and four-hour bars are epoch-aligned from authentic completed 1m inputs; only hourly features drive the frozen rules. No funding/OI input is used as a predictor.

Breakout and trend-pullback variants were fixed for LONG/SHORT and 4h/12h. ATR24 risk is 1.5 ATR, target 2R; 12h purge/embargo is applied at both fold edges. Candidate and unconditional-control positions do not overlap within a symbol. Stops resolve before targets on ambiguous minutes; stop gaps worsen execution, target gaps give no favorable extra credit. Zero-volume entry minutes veto fills; stale open paths hard-stop. Latest available lagged quote volume limits participation.

Research reference equity is 1,000 USDT with fixed 333.333333333333 USDT entry notional per asset; there is no leverage multiplication, compounding, martingale or borrow income. Returns and realized drawdown are fixed-notional research statistics, not a self-financing/live margin account or full minute MTM equity. Exchange tick/lot execution, queue depth, spread and latency are not measured.

All entries and exits, including targets, incur taker fees. Base per leg: taker6bp, half-spread2bp, slippage3bp (22bp round trip); stress12/4/6bp (44bp round trip). Maker2/4bp rates were frozen but unused; maker fees/fills are zero. Fees apply to modeled adverse entry/exit prices. Cost components, gross/net R and USDT PnL are disclosed per candidate, symbol, regime and fold.

All nine funding archives are authentic and contain 276 calculation records per asset. Some public calc_time timestamps differ from exact eight-hour boundaries by milliseconds (e.g. +5ms). The parser preserves those timestamps; it never snaps them or invents receipt proof. Exact schedule completeness under the frozen contract fails, so the entire campaign uses PROXY_STRESS_ONLY: adverse4bp at each intersected UTC00/08/16h boundary,8bp in stress, with quantity times max(entry,settlement-minute high) as funding-notional proxy. Positive funding benefits are never presumed. These are not measured mark-price funding payments.

The initial funding-admission attempt failed before candidate replay because the decoder incorrectly imposed price-minute alignment on funding calculation timestamps. Correcting that format error preserved the publisher clock and activated the already frozen proxy rule. It did not change any candidate or economic threshold. A frozen wording conflict on invalid funding checksums was resolved conservatively in favor of HARD_STOP; no checksum failure actually occurred.

## Interpretation and against-claim alternatives

Three configurations had slightly positive gross mean R, but none survived the frozen frictions. The least negative base result (trend-pullback SHORT12h) was -0.129R, with only77 trades and25/32/20 per fold; it is not a selected candidate. Even the dollar PnL decomposition excluding funding charges remains negative for every configuration: taker fees/spread/slippage already exceed gross dollar profits. This decomposition is explanatory, not another selection/cost scenario.

The strongest failure explanations are false breakouts, insufficient trend continuation, stop-first churn and a small gross signal relative to short-horizon trading friction. Resolved stop-before-target fractions range roughly65–89%. Broader asset trends, common shocks, unmeasured execution and funding assumptions compete with any story of directional skill. Symbol/regime/fold improvements cannot rescue the negative pooled screen.

Unconditional matched-accounting naïve LONG/SHORT controls are published. Matched LONG/SHORT at each candidate entry are paired counterfactual event-study episodes, not separately funded portfolios; those episodes can overlap across events and must not be added as achievable capital returns. Their incremental comparisons are exploratory. The historical Tactical reference is NOT_COMPUTABLE without matching derivative and reference-universe inputs; RC1 remains its accepted valid hard FAIL, and RC2 has no valid protected quality verdict.

Each candidate spans13 observed seven-day time blocks. The fixed2,000-draw common-shock block bootstrap groups assets by UTC entry week and discloses95% intervals plus a one-sided Bonferroni lower quantile0.003125 across eight candidates/two screens. Its stationarity assumptions, few blocks, correlated candidate returns and previously exposed cohort prevent confirmatory alpha claims. Every fold has fewer than100 trades for every candidate. No support threshold, horizon or subgroup was adjusted after outcomes.

## Validation and publication

Final local L1: **52 passed,0 failed,0 skipped on canonical Python3.12.3**; changed-scope Ruff, compileall and mypy passed. Independent read-only review passed10 focused negative regressions and inspected no market outcomes. Synthetic fixed-context trade/feature/bootstrap scientific digests match Python3.12 and3.13. This is scoped engineering certification, not release certification.

The exact implementation replay took17.5229s. Three identical-input computational passes returned byte-identical result JSON and compressed derived rows; these are determinism checks of one fixed campaign, not three searches. All candidate trade IDs are unique and no same-strategy/symbol positions overlap. TEST_RECEIPT.json gives exact commands, timings, code/data/hash linkage and applicable/N_A test selection.

Shared CI/workflows were not modified. The implementation CI URL/status is recorded without converting local tests into a remote success claim. Existing ENTRY, G1, R1 and reviewer worktree branch/HEAD/dirty-untracked counts match preflight. No protected source/outcome, signed exchange endpoint, provider smoke, TESTNET, live advice or funds write was accessed.

## Separate prospective R3 suggestion

Recommend CONTROLLER_L2_G2_R2_RESEARCH_REVIEW. Do not promote any of the eight current formulas or execute them in G1. If research continues, first freeze and independently verify public funding calculation-to-settlement mapping, mark-price notional, fee/tick conventions and feed-availability receipts. That is a new protocol; R2 must not be rewritten or silently reranked with cheaper costs.

A separately authorized R3 could freeze at most two scientifically justified formulas before seeing its demonstrably unexposed forward cohort. R2 provides zero qualifying nominees. Propose360 fixed forward UTC days, three120-day partitions, no outcome-dependent extension, >=100 unique trades per partition, >=26 shared seven-day blocks, complete feature/trade minute paths and <=60% single-asset exposure. Insufficient support remains diagnostic-only.

Precommit nulls: expected higher-cost net R<=0 and incremental matched-exposure net R<=0. Require both multiplicity-adjusted lower block-bootstrap bounds>0, positive base/stress means, stress mean>=+0.05R, stress median>=-0.05R and at least two nonnegative partition stress means. Controller must review these proposed thresholds and control design, independently authorize the source/exposure safeguards and define release gates. No forward collection, alpha approval or execution permission is granted or started by this report.

Executor profile SOL_HIGH completed method freeze, bounded implementation, authentic historical price replay, comprehensive diagnostic evidence, independent engineering review and proactive branch publication. Not completed: measured live receipt/fill/funding proof, grid inference, sufficient partition support or independent strategy-quality validation. REAL_FUNDS_WRITE_AUTHORITY=NONE; TESTNET=NOT_AUTHORIZED; PROTECTED_RC2_RETRY=FORBIDDEN; exchange writes0; protected reads0; G1/R1/shared source changes0.

## Full CI scope blocker

The exact implementation's fail-closed broader CI completed with **2,819 passed,
1 failed,2 skipped**,8 warnings in527.81s; the job elapsed558s. Static checks passed.
The failure is `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`, an exact graph-hash mismatch.
Only bounded hermetic CI failure-summary metadata was inspected, not H40 archives
or protected market outcomes. H40 source/tests are unchanged on this branch.
The cause is not adjudicated; do not label it harmless or claim full regression PASS.
H40 tests/source and shared CI are forbidden edit surfaces for G2 R2. No expected
hash was updated and no skip was added. Controller must separately triage this
integration blocker; CI_RESULT_AND_SCOPE_BLOCKER.json preserves exact hashes,
counts, timing and URL. The fixed R2 research remains DIAGNOSTIC_ONLY, with local
canonical52-test L1 passing and no strategy-quality or integration acceptance claimed.
