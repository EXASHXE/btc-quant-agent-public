# R8-7 — X-only Historical Economics Priority Update

**Date:** 2026-10-21. **Owner/Controller handoff:** Owner reports that Controller B has already accepted separate R8-7 authorization to calculate historical price outcomes for the specifically frozen public X-only discovery sample. This document records the reported authorization; it is not a new blanket grant for other datasets or outcomes.

**Code reference:** Last independently observed executable remote `v0.6.5@40c70c740f352d1b444decb75276196d17a72dd2`. Documentation branch is separate. Refresh and use the actual active experiment registration, frozen hashes and task receipts before execution.

## Verified predecessor state

- Local R8-5 artifact: `/root/workspace/project/crypto-data/lakehouse/r8-5-public-h1-support-20261021/R8_5_DECISION.md` and `R8_5_RUN_RECEIPT.json`.
- Exact public price sample is 36 whole monthly BTCUSDT 1m public archives from [2021-01-01T00:00:00Z, 2024-01-01T00:00:00Z); previous feature-stage check verified 1,576,800 native minute rows and 36 source archives. Underlying event evaluation begins only after the frozen calibration / embargo rules.
- Frozen shared X calendar: **545 distinct X-selected slots**, each separated from the next by at least **24 hours**; 275 LONG / 270 SHORT. Year counts: 2021=150 (69 LONG / 81 SHORT), 2022=215 (122 LONG / 93 SHORT), 2023=180 (84 LONG / 96 SHORT). X calendar has 140 acted-event ISO weeks. Fixed planned holding is 8h; this timing separation excludes planned 8h holding-window overlap, but does not imply statistically independent returns or guaranteed fills.
- R8-5 raw candidate counts: 3,599 raw X signals and 19 raw X+Z H1 signals; 3,138 evaluation-eligible raw X signal instances. These raw signals are **not** 545 independent trades.
- Local R8-6 closeout: `/root/workspace/project/crypto-data/lakehouse/r8-6-h1-gate-closeout-20261021/R8_6_CONTROLLER_DECISION.md`. **`H1_RETIRED_FEATURE_SUPPORT_NO_GO`** means only four selected X+Z H1 events on the same 545-slot calendar (2021/2022/2023: 1/2/1), insufficient for its frozen support floors. This is **not evidence that X-only is unprofitable**, and no H1 economic run occurred.
- R8-5 and R8-6 reported zero price-return or economic labels, no realized trades and no net PnL. R8-7 is the first separately approved X-only discovery economics question; authorization is **reported by Controller/Owner**, while no R8-7 execution or completion receipt has been observed in the bounded local review as of this update.
- The Owner reports that the final X-only signal was 2023-12-29 17:00 UTC and its fixed entry-plus-8h exit lies in 2023. Record this against the exact frozen event manifest during R8-7, rather than recomputing/reselecting signals.

## Controller B priority — make real economic evidence, not more feature tests

**P0 / NOW: R8-7 PUBLIC X-ONLY EXPLORATORY ECONOMIC STUDY.**

1. Reuse the R8-5 **unchanged** 545-slot frozen X-only calendar, signals, directions, source references, time rules and hashes. Do not recreate or optimize events after viewing returns. Confirm the registration/manifest links and exact authorized public input range once.
2. For each slot, derive the reference entry at the existing `t+2m` rule (or the exact prior locked execution contract) and the original fixed 8h exit. Track no-fill/no-price/missingness explicitly; compare entry and exit in strictly causal order. Do not add dynamic exits, hard stops, ATR trail or MACD exits in R8-7; those require a *separate* exit experiment and changed opportunity set.
3. Produce gross signed trade return, side/year grouping, modeled round-trip fees and slippage, and funding transfers only where source/calendar actually supports them. Compare at least the existing baseline and stress cost assumptions if present in the locked registration; if missing, disclose **gross** and `modeled_net_excluding_missing_components` separately rather than claiming fully net profitability.
4. Deliver per-event ledger and summary: count of eligible/excluded/completed hypothetical trades, LONG/SHORT breakdown, mean/median and dispersion, win rate, average gain/loss, payoff ratio, Profit Factor, per-trade expectancy, compounded/equity-path assumptions, max drawdown, exposure/time in market, fee/funding breakdown, year/month/regime concentration and simple uncertainty from non-overlapping events. Reproduce with exact executable command and source/config hash receipts.
5. Interpret as **2021–2023 discovery-stage exploratory economics**, not independent validation/confirmed Alpha. Do not inspect or reclassify 2024 rolling-selection, 2025 locked validation or the existing 2026-02-01 to 2026-08-01 FINAL_HOLDOUT. Do not revisit H1 support or original private partitions.
6. If R8-7 is already running, do not redispatch. Check its actual receipt, complete that job, then publish one succinct economic verdict. If not yet running, dispatch the scoped Codex study now under the separately accepted Controller R8-7 card. Do not mark RUNNING/COMPLETED without a job/output receipt.

## After the R8-7 result

- If X-only has positive modeled net expectancy after stated cost assumptions and tolerable drawdown, prioritize stability checks and 2024 chronological rolling selection before any candidate upgrade. Do not retroactively optimize the 545 events or unseal 2025/2026.
- If X-only is negative or fragile, use the trade ledger to classify loss modes and launch a **new separately registered** strategy hypothesis from the existing four price families (trend, breakout/retest, conditional mean reversion, volatility compression/expansion) and a separately budgeted exit experiment (fixed horizon vs dynamic signal/ATR exit with hard stops). Negative X-only PnL does not invalidate other price-only families.
- Use EMA/MACD(DIF/DEA)/KDJ/volume/ATR/ADX/VWAP as candidate **causal state features**, not a large all-indicator Boolean conjunction. Dynamic exits can be researched in a separate paired study with frozen initial entry events and a non-optional protective hard stop; do not change R8-7 after reading economic outcomes.
- Preserve the overall R8 time split: 2021–2023 discovery, 2024 rolling selection, 2025 one-shot locked validation only if prior exposure supports independence, 2026 existing final holdout sealed until preregistered final evaluation.
- Controller B should not dispatch more governance reviews, broad data inventories, repeated feature scans, CI cleanups or routine multi-agent audits unless a **specific defect** invalidates the current result.

**Milestone status:** `R8_5_FEATURE_SUPPORT_REPORTED_AND_VERIFIED`; `R8_6_H1_RETIRED_FEATURE_SUPPORT_NO_GO`; `R8_7_OWNER_AUTHORIZED_EXECUTION_NOT_YET_VERIFIED`; `X_ONLY_EXPLORATORY_NET_PNL_PENDING`; `NO_ALPHA_ESTABLISHED`. No real order/funds operation.
