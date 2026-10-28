# v0.7.0 Advisory Delivery Roadmap

> **Canonical:** GitHub `docs/engineering`. [Documentation Branch Policy](V070_DOCUMENTATION_BRANCH_POLICY.md). Matching `v0.7.0` documents are historical copies.
Status: proposed by current Owner direction (2026-10-28); stages are not permissions and no gate is declared passed by this document.

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

## Immediate task sequencing
1. **V070-ADVISORY-FOUNDATION-01**: narrow isolated engineering patch; documentation at V070_ADVISORY_FOUNDATION_TASK.md.
2. **V070-TRADEPLAN-LIFECYCLE-01**: one playbook, plan identity, user-reported fill and synthetic full replay.
3. **V070-MANAGEMENT-ALERTS-01**: wired position signals, management actions, breach/reversal and notification correctness.

Run T2B canonical repair integration before any accepted modeled execution depends on it. Its isolated tests passed but the original worktree is not patched. F0B remains only synthetic-validated and is integrated only if that particular L2 source is actually needed. No generic new source-readiness audit loop.

## Research allocation
- PRIMARY budget last checked 3/6 used; never auto-register a replacement. Preserve 2021–2023 exposure, 2024+ seal and 2026 FINAL_HOLDOUT.
- No broad fixed-horizon parameter sweeps or maker-fill assumptions on OHLCV.
- Compare entry-location incremental value separately from dynamic-exit incremental value; then evaluate full portfolio path. Keep NO_FILL, missing funding, open positions and time occupancy.
- Product engineering acceptance does not require 80% power for a future economic hypothesis. Confirmatory economic claims do.

## Explicit deferred items
No Jesse/LEAN/Hummingbot/advanced multi-engine migration, live auto-execution, 85/70/60 win-probability marketing, universal news-driven trading, new L2 research campaigns or full-market scale until the small advisory loop works reliably.
