# Quant v0.7.0 — Intraday MVP Acceleration Roadmap (2026-11-09)

> **SUPERSEDING MULTI-SYMBOL NOTIFICATION PLAN — 2026-11-09:** [New MTF+Feishu roadmap](V070_MULTISYMBOL_MTF_FEISHU_ROADMAP_20261109.md) · [Handoff Home](V070_HANDOFF_HOME_20261109.md). Prior 1H-only and twice-daily manual review assumptions below are obsolete; preserve them as dated planning history.\n\n**Status:** Proposed Owner product direction and Controller 0-C next execution contract. Not a representation that code has already been changed or native source admitted.

## Product boundary

A read-only crypto trading-opportunity assistant optimized for **2–12h** holding (optional planned overnight extension, never beyond a justified 24h review horizon), scheduled manual use and explicit NO_SETUP. No account access, order routing, real-money trading or background collectors under this mandate.

## Signal clocking

| Layer | Target role | Requirements |
| --- | --- | --- |
| 1D | Higher-timeframe context | Macro direction, major levels, event/overnight risk; no unconditional 1D-close entry gate |
| 4H | Regime and structure | Trend/range, volatility state, directional structure and contextual invalidation |
| 1H | Main setup decision | Closed-bar confirmation, executable planned entry, stop/targets, review validity |
| 15m | Optional tactics | Subordinate confirmation and execution-quality refinement only, not standalone signal |

Closed-candle availability is based on venue timestamps plus qualified receiver/host time evidence and complete source lineage. Revalidate later at manual review. The 1H/4H/1D requirements are a future versioned contract, NOT retroactive qualification for O/J/L.

## Immediate execution gates

**Gate 0: Evidence and host decision.** Controller independently accepts the P2 stop/rollback, verifies no active writer and excludes expired native approvals. Do not repeat failed host interventions without explicit new authorization. Evaluate a stable, permission-compliant execution environment with the full clock/UTC/native tests. No unqualified source can be silently promoted.

**Gate 1: Operational MVP real vertical slice.** Using only a separately approved finite source scope, retrieve actual valid warmup and recent 1H/4H bars for BTC/ETH/SOL, emit real S1 or NO_SETUP, append durable Shadow state, render existing local HTML and re-open it after restart. Demonstrate future review-time revalidation, freshness and stop behavior. A real NO_SETUP is a successful software outcome.

**Gate 2: Liquid symbol universe.** First enable 10–20 eligible USD-M perpetual symbols after real Source/clock proof. Use venue exchangeInfo/ticker/klines only within verified jurisdiction, permissions, request weight, clock and retention limits. Staged filters: listed/trading state; 24h quote volume; narrow spread and depth for intended hypothetical size; completed-bar history/coverage; source quality; cost-adjusted capacity. Example 20M USDT/day threshold is an *untested starting hypothesis*, not accepted science. All-symbol 24h ticker may carry substantial weight; first produce an explicit budget/caching contract, then test 20–50 candidates, not an unconditional unbounded scan.

**Gate 3: Market Regime Router (research gated).** Deterministic two-axis classification: trend (up/down/range/unknown) × volatility (low/normal/high/dislocated) using predeclared 4H and supporting 1H measures. Primary admitted strategy remains S1 trend pullback; S2 breakout/retest and S3 range mean reversion / structural reversal are challenger hypotheses only. Dislocated, low-liquidity, ambiguous or conflicting states veto. Avoid optimizing thresholds on protected samples and avoid data-dependent backtest shopping.

**Gate 4: Prospective economic evaluation.** Record actionability, no-fill, entry validity, stop-first/target-first/ambiguous OHLC, time exit, spread, fees, funding, synthetic-vs-real differences, paired null and cluster-level uncertainty. Predeclare 2R,3R,4R and validity by 2/4/8/12/24h, with conservative first passage. No profit/Alpha claim until independent sample sufficiency and economic support.

## Sequencing / definition of done

- **Milestone M0 — Evidence clean:** P2 independent closure, N retention audit, one frozen O-derived source package in review branch; Controller acceptance unambiguous.
- **M1 — True source and first card:** host, legality and signed grant admitted; a finite real scan with actual card or NO_SETUP, append-only ledger, generated HTML, restart/readback, no request-account-order excess.
- **M2 — Wider scan:** dynamically sorted eligible universe; predictable bounded request plan and measured freshness/coverage; qualified 10–20 symbol analysis with no batch contamination.
- **M3 — Adaptive research:** deterministic regime and challenger research-only metrics; no auto-activation and no retrospective claims.
- **M4 — Evidence cycle:** sufficient independent prospective follow-up and after-cost, uncertainty-aware strategy decision.

M0/M1 are the shortest route to a working product. M2 and M3 can have *small offline design tasks* in parallel, but should not delay M1. M4 is research, not a blocker for an honest operational MVP.

## Explicit non-goals and unchanged guards

No orders, leverage engine, private accounts, alerts, testnet execution, new exchange keys, autonomous strategy selection, uncontrolled web acquisition or deployment. Existing queue 128, 50ms sticky clock stop and research/source evidence controls may not be bypassed. Protected history, original negative findings and 2026-02-01→2026-08-01 FINAL_HOLDOUT are not to be opened. Any new source path must independently meet its declared qualification; separate exploratory review status from strict research status.

## Suggested task discipline for Controller 0-C

A single bounded source/host closure task, a single real product verification task once eligible, and a small independent offline universe/regime specification task. Use explicit isolated writers, code hashes, proof-based acceptance and stop on unknown rights/clock/lineage. No large platform refactor until the first genuine end-to-end result and reviewer findings exist.
