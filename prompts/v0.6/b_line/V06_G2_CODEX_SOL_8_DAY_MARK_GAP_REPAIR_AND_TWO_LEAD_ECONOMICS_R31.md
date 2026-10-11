# GPT-6 Codex Sol High — R3.1 fixed 8-day BTC Mark gap repair + ACTUAL two-lead Funding/Mark economics

**TASK_ID:** \`V06_G2_BTC_TWO_FIXED_12H_MARK_MISSING_8_DAYS_GAP_REPAIR_AND_REAL_FUNDING_REPLAY_R31\`
**CONTROLLER_DISPATCH_SHA:** \`6b08af95335a4d577e1367a9b0652258bad1ca35\`
**READ Controller binding completely:** https://github.com/EXASHXE/btc-quant-agent-public/blob/6b08af95335a4d577e1367a9b0652258bad1ca35/reviews/v0.6/b_line/V06_G2_R3_REAL_FUNDING_SOURCE_ACCEPT_MARK_GAP_REPAIR_AUTHORITY_R31.md
**Repository** \`EXASHXE/btc-quant-agent-public\`
**Controller-created branch:** \`feature/v06-bline-btc-two-lead-mark-gap-repair-r31\`
**EXACT branch start/parent:** \`057c47a4bfd248131f4fd94d12d3deef73c65e1f\`, verify git remote and exact clean branch. No reset/force push or touches to other worktrees.
**New isolated worktree:** \`/root/workspace/project/quant-v0.6/btc-two-lead-mark-gap-r31\`; do not touch old R3 worktree or historical frozen reports.

## Critical priority: finish the science, not another data-source architecture document

The previous Sol R3 branch was not a strategy failure. It verified **36 last-price ZIPs (1,576,800 rows)** and **36 genuine funding-rate ZIPs (3285 signed settlement events)**, but authenticated official **monthly Mark archive contained 11,520 absent minute rows** in **EIGHT exact UTC days**. This task specifically authorizes new sources to fill **ONLY** those gaps. The original R3 \`MARK_FUNDING_SOURCE_OR_CAUSALITY_BLOCKED\` is valid and immutable, but must not be reused as a reason to stop again before attempting both the frozen official DAILY and official public API routes.

Read these paths before editing:
- \`docs/strategy_research/g2_r3/two_lead_funding_mark_r3/R3_OBSERVED_FUNDING_MARK_SOURCE_BLOCK_REPORT.md\`
- \`evidence/v0.6/b_line/g2_btc_two_lead_funding_mark_r3/R3_INDEPENDENT_MARK_GAP_WITNESSES.json\`
- \`evidence/v0.6/b_line/g2_btc_two_lead_funding_mark_r3/R3_OBSERVED_FUNDING_SOURCE_DIAGNOSTIC.json\`
- \`scripts/strategy_research/g2_btc_two_lead_funding_mark_r3/{sources,economics,run}.py\` READ-ONLY
- R2 original two-lead \`docs/strategy_research/g2_r3/gemini_goal_trend_flow_r1/REANALYSIS_R2_ACTUAL_PRICE_REPORT.md\`.

**Explicit, precise Mark gap UTC days:** \`2021-07-01\`, \`2021-07-24\`, \`2021-07-25\`, \`2021-07-26\`, \`2021-07-27\`, \`2022-07-31\`, \`2022-10-02\`, \`2023-02-24\` = 8 ×1440 = **11,520 missing minutes**. All within authorized 2021–23 and known from source freeze (no new strategy search). Other monthly source rows are immutable. **Source repair ≠ retroactive 2021 historical known-at authenticity.**

## Commitment order / fixed source precedence

MAX TWO git commits, nonforce push:
**Commit 1** \`R31_FROZEN_MISSING_MARK_SOURCE_ROUTE_CONTRACT.json\` plus source adapter, tests/fixture-only, a documented code/economics inheritance + exactly 8 missing UTC ranges. Commit and PUSH exact SHA **BEFORE any new DAILY/API Mark result body is inspected**. No new candidate, loss-driven signal filter, excluded month, spread tweak or hidden performance iteration. Freeze daily-before-API precedence, fail-closed duplicate/gap/overlap agreement, error handling and source SHA capture. Public provider documentation reading before commit is fine; 2024+ data bodies/headers/listings are forbidden.

**Commit 2** after actual 2021–23 R3.1 data acquisition/replay, one new set of source receipts, audited economic ledger/summary and report, terminal. No invisible third tuning/test wave. If truly blocked, commit observed precise source failures and *funding-first* partial ledger as described below, not a generic "can not proceed".

**Allowed NEW paths only:** \`scripts/strategy_research/g2_btc_two_lead_mark_gap_r31/**\`, \`tests/test_v06_g2_btc_two_lead_mark_gap_r31_*.py\`, \`docs/strategy_research/g2_r3/two_lead_mark_gap_r31/**\`, \`evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31/**\`. Existing R3 scripts/algorithms and all original strategy registration/results untouched, including \`g2_btc_two_lead_funding_mark_r3/**\`, R2 frozen code/evidence, other branches, CI/roles/reviews/controller files. New sidecar may IMPORT old R3 \`economics.py\` and \`sources.py\`, CALL reusable \`run.study\` only after complete authenticated arrays; do not invoke original \`run.run()\` if its source gate forces the old R3 monthly-only rule. New sidecar must have its OWN output directory, not modify old task scratch/evidence.

### Fixed source contract (enforced before any URL, stat or network)

1. Primary: provider official USD-M BTCUSDT daily Mark archive, URL schema exactly
   \`https://data.binance.vision/data/futures/um/daily/markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM-DD.zip\`
   plus \`.CHECKSUM\`. Request **ONLY these eight pre-named missing UTC dates**, read ZIP SHA256/CHECKSUM, ensure one expected CSV, exact 1440 UTC 1m bars with high/low/open/close positivity, minute clock and close-time and byte-size guard. For daily source itself incomplete, record missing smaller windows.
2. Secondary only for still missing minutes: provider public \`GET https://fapi.binance.com/fapi/v1/markPriceKlines?symbol=BTCUSDT&interval=1m&startTime=...&endTime=...&limit=...\`, deterministic request times (limit at most 1500). Record every request, response hash/status/content type, rate-limit/transport evidence and pagination; no future-2024+ access. API value is \`SECONDARY_PROVIDER_API_NOT_SHA_ZIP\`, not equivalent authentication to the daily ZIP. Cross-check API/daily vs *overlapping existing monthly Mark at neighbor minutes* when possible; if not possible, explicitly lower provenance class and do not claim equal-source certainty. For any source conflicts or unexplained kline zero, fail closed, no cherry-picked row. No multi-exchange/third-party fills.
3. Compose monthly verified 1,565,280 existing rows + exactly 11,520 independently sourced missing rows; recompute exactly 1,576,800 minute clocks, strict no duplicates, no sorting assumptions, positive mark and exact UTC; use **monthly as authority for already present minutes**, never overwrite existing values. Source receipts per month/gap and composite SHA per algorithm. Month CSV monthly SHA original preserved; source priority frozen before value access.
4. For speed, permitted read-only reuse of the R3 **task-owned public** \`/tmp/btc-two-lead-funding-mark-r3\` only if present, exact archive bytes satisfy R3 signed checksums+machine manifest and paths resolved inside this narrow scratch. If absent, re-download exact 2021–23 official original monthly last/funding/mark. DO NOT use scratch from other projects/agents, private \`/root/workspace/project/Quant-agent/data\`, \`Quant-agent-sanitized\` even stat, Forward/H39/H40/H41 or public data 2024–26. Caution: original R3 complete Funding and last-price already exist; **do not rerun 108 archive downloads unnecessarily** if verifiable.
5. All historic funding must remain the verified **actual 3285 signed events** with exact UTC chronology (observed ~8h), no future settled Funding signals. At settled timestamp value, reconcile as-of Mark not yet future, trade LONG pays when funding rate positive and SHORT receives, sign reverses for negative. Actual rate unit is Decimal fraction, ×10000 bp; cap no invented event. Fees/slippage BASE22/STRESS44 unchanged.

## Full *actual* two fixed 12h strategy reanalysis (if composite admitted)

\`W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H\` and \`W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H\` ONLY. Reuse prior R3 frozen \`economics.py\` and R2 original code-as-executed 12h signals: 2021Jan warmup, 35 score months Feb2021–Dec2023, old 24h purge, old extra1m entry lag, TIME_CAP first horizon minute **OPEN**, same stop/target/ATR/timeframes/directions/partial lot/5% reserve/1x admission/ACK and matched control. Read R2 reference STRESS trades n34 and n55, means +11.504/+19.132bp WITHOUT funding. Confirm R3.1 **no-funding baseline** against those exact values and source/trade ID digests before overlay. Explain any missing rounded lots/data effect, never fix by optimizing params.
- Overlay observed settlement signed funding on fixed trades, and separately replay funding-aware cash sizes with conserved book.
- Mark is risk/MTM and funding notional as-of source, NEVER replace executable last-trade prices, order-book fills, time cap or strategies.
- Report BASE22/STRESS44 before/after observed funding, per-year/side/month N, net bp, R, actual cash account end-return & minute Mark DD, funding cash debits/credits and count per trade, paired PAUSE/balanced counterfactual and 48 joint historical familywise 7/14d UTC bootstrap with no-trade blocks; 2023 loss explained quantitatively. Historic posted maker/taker fees/L2 impact still UNKNOWN; fee sensitivity ±2/±5/±10bp without posthoc choice. All positive numbers remain **EX_POST_EXPOSED_DEV_ONLY**, no 2024–25 holdout access.
- Independent Decimal minimum FIVE real funding event episodes including LONG, SHORT, 2022/2023 and settlement-boundary ±60sec. Cause analysis if 2021 positive dominates. No data-driven trial/candidate choice, no 8h strategy or 2024–26 fetch.

## Mandatory useful partial science if gap source genuinely remains unavailable

**DO NOT make entire R3.1 result empty just because one required Mark minute cannot be retrieved.** Separately compute and publish a measured **funding coverage and exposure ledger** using verified complete actual 2021–23 funding archives + the same frozen two R2 trade-price executions. For event/trade pairs where settlement-time Mark is authenticated (including monthly known rows and/or authenticated daily), compute observed signed Funding by frozen formula; where settlement Mark unavailable, label \`UNKNOWN_REQUIRED_MARK\`, do not invent zero or last-trade substituted Mark. Report exact coverage n/%, missing trade/event IDs, signed cash for fully covered trades, per-year/side and range of unresolved cash if bounded without inventing source. **Do not publish a full-period adjusted mean as actual measured** when any trade requires unknown Mark. Show true \`Mark_MTM_STATUS=INCOMPLETE\`; no conditional dropping of bad months for favorable results.
If a failed month cannot be downloaded at all, source status and sign-only theoretical bound clearly separated. This is real partial measured work, not full economic promotion.

**Terminal**: \`R31_TWO_LEAD_OBSERVED_FUNDING_MARK_COMPLETE_DEVELOPMENT_ONLY\`, or \`R31_MARK_GAPS_REMAIN_FUNDING_PARTIAL_ONLY\`, or \`R31_FAIL_CLOSED_SOURCE_OR_ACCOUNTING\`. CI tests local scoped synthetic >=15 for authentic/day/API/dup/mismatch/time/sign/cash/PIT, provider checksum receipts, historical 8 days independent gap proof, ≥5 real signed funding Decimal audits if full, compile + Ruff, optional configured CI. CI status after push, no false green. Do not touch H40/old baseline, no blanket new strategy/refactor, no TESTNET/LIVE or real money.

Deliver exact branch SHA/parent/manifest and TWO-LEAD comparison plus remaining blockers. Target first complete R3.1 via **provider DAILY** (official supported) before API. Actual authenticity matters more than making an artificial positive result.
