# v0.7.0 Advisory Delivery Roadmap

> **Canonical:** GitHub `docs/engineering`. [Documentation Branch Policy](V070_DOCUMENTATION_BRANCH_POLICY.md). Matching `v0.7.0` documents are historical copies.
Status: proposed by current Owner direction (2026-10-28); stages are not permissions and no gate is declared passed by this document.

## Research priority update — Owner manual response 1–5 min (2026-10-28)

The Owner reports **1–5 minutes from receiving an alert to manually submitting an order**. Read the [M1 delay and revised research-priority decision](V070_M1_MANUAL_DELAY_RESEARCH_PRIORITIES_20261028.md) before commissioning new mechanism work.

- **R0 first:** source/clock/independent-support feasibility for *forced-deleveraging reversion* (M1), strictly **without outcome-data access**. Do not assume a 5-minute human response implies a 5-minute total event-to-fill delay.
- **R1 conditional:** if evidence and exact Owner authorization permit, test the residual feasible move and cost-aware execution with 1, 3, 5 min manual delays plus 10–15 min total-latency stress. The 5-minute case matters for real advisory usability.
- **R2 low-cost exploratory control:** the existing pullback/retest structural playbooks versus matched placebos if separately authorized.
- **R3:** medium/slow trend + structural execution as a product-aligned alternative. **R4:** low-turnover hedged carry only if the Owner wants a distinct two-leg capital-management product.
- Risk copilot and plan/claim ledger engineering can proceed independently of Alpha research once the existing Foundation contract issues are accepted. RESEARCH / CANDIDATE / VALIDATED must not imply an already proven tradeable edge.

This is an Owner-input planning update, not authorization to read market outcomes, launch workers or consume protected data.

## Strategy
Build a narrow real-time advisory vertical slice by reusing existing deterministic modules. Preserve fixed-horizon E0 research as a frozen benchmark; new plans use event-driven structural exits and do not claim Alpha. The first demonstration covers one playbook and a small liquid-universe subset, then expands on measured evidence.

| Phase | Scope and main existing assets | Acceptance / stop condition | Dependencies |
|---|---|---|---|
| P0 Baseline and correctness | Choose R/M/Q integration source; preserve original owner changes; validated T2B patch available. Review current scanner, quote, time, alert and risk behavior. | File/hash baseline; source of truth selected; no silent overwrites. | Owner-approved task scope |
| P1 Advisory Foundation | Reuse market_watch scanner/service, state, decision persistence, notify; fix derivative-degraded exception, received/available/decision clocks, stale veto, executable quote separation, tick-size handling, and persist-before-notify outbox. | Synthetic tests for failures, cross-symbol timing, crash/replay, notify=False and exact prices; no network or production writes. | P0 |
| P2 TradePlan Lifecycle | Reuse confirmed pivots and TREND_PULLBACK first; optional BREAKOUT_RETEST second. Add versioned plan/entry/expiry/cancel, structure-target vs projected-target types, open-ended trailing. | Deterministic candidate→committed plan→user report→closed/invalidated replay; no fabricated fill, no hindsight or hidden loosened stop. | P1 |
| P3 Position Management | Reuse PositionSupervisor/decision evidence. Wire observed risk fields, STOP_BREACHED, user-reported/manual adjustment, partial close, deterministic management compiler and priority-deduplicated alerts. | Stop gap, reversal confirmation, stale data, conflicting actions, manual adjustments, restart/resend tests. | P2 |
| P4 Bounded Forward Advisory | Use existing collectors only where data health and authorized read interfaces genuinely qualify; deploy separate read-only shadow if explicitly approved. F0B health publisher is conditional, not a universal prerequisite. | Committed-before-entry, observed slot and missingness metrics, delivery latency, replay parity and delayed results; no order execution. | P1–P3; separate access/deploy approval |
| P5 Economic Validation and Enhancements | Event-driven lifecycle backtest with honest fills, modeled/full-net distinction, portfolio occupancy, paired entry/management studies; expand universe/derivatives only on incremental information; future news-risk ingestion/calibration. | Registered estimand, support/power preflight for confirmatory work, sensitivity, risk-adjusted net and uncertainty; no OOS misuse. | Data/source approval and prior product readiness |

## Immediate task sequencing — reconciled 2026-10-28
1. **V070-ADVISORY-FOUNDATION-CONTRACT-RECONCILIATION-01**: **single next task**, not automatically authorized. Foundation-01 and Completion-01 are both PARTIAL isolated packages. Completion's original 175 cases passed 173/175, new continuation cases 35/35 and independent E2E 6/7. Preserve the three original legacy-contract failures; reconcile fixture expectations to the current ACTION fail-closed / WATCH-RISK preservation semantics and demonstrate transparent passing replacements before any ACCEPT. No integration or deployment.
2. **User-reported Position Risk Copilot, bounded thin slice**: after Foundation ACCEPT and specific Owner engineering approval, reuse existing supervisor/decision primitives for manually asserted positions, STOP_BREACHED, unresolved execution, regime/derivatives risk and risk-first advice. This standalone read-only risk slice must not require a validated opportunity playbook, exchange account connection, or a fabricated fill.
3. **V070-TRADEPLAN-LIFECYCLE-01**: versioned claim/plan identity, entry/expiry/confirmation and user-reported fill/adjustment ledger; connect it to the risk slice and synthetic replay. Existing structural playbooks remain unvalidated research templates.
4. **V070-MANAGEMENT-ALERTS-01**: integrate committed claims, priority/deduplicated durable outbox, deterministic management actions and risk notifications, reusing Foundation outbox rather than building a second framework.
5. **Bounded forward advisory shadow**: only with separate exact data-read and deploy authorization, measure clocks, missingness, delivery and non-execution outcomes.

Run T2B canonical repair integration before any accepted modeled execution depends on it. Its isolated tests passed but the original worktree is not patched. F0B remains only synthetic-validated and is integrated only if that particular L2 source is actually needed. No generic new source-readiness audit loop.

## Research allocation
- PRIMARY budget last checked 3/6 used; never auto-register a replacement. Preserve 2021–2023 exposure, 2024+ seal and 2026 FINAL_HOLDOUT.
- No broad fixed-horizon parameter sweeps or maker-fill assumptions on OHLCV.
- Compare entry-location incremental value separately from dynamic-exit incremental value; then evaluate full portfolio path. Keep NO_FILL, missing funding, open positions and time occupancy.
- Product engineering acceptance does not require 80% power for a future economic hypothesis. Confirmatory economic claims do.

## Explicit deferred items
No Jesse/LEAN/Hummingbot/advanced multi-engine migration, live auto-execution, 85/70/60 win-probability marketing, universal news-driven trading, new L2 research campaigns or full-market scale until the small advisory loop works reliably.
