# V070-ADVISORY-FOUNDATION-01 — Codex Task Proposal

> **Canonical:** GitHub `docs/engineering`. [Documentation Branch Policy](V070_DOCUMENTATION_BRANCH_POLICY.md). Matching `v0.7.0` documents are historical copies.
Status: PROPOSAL_ONLY, pending an explicit Owner implementation authorization. Prepared 2026-10-28.

## Objective
Deliver the smallest safe advisory integration foundation in an isolated checkout: valid input snapshots, consistent known-at/decision clocks, honest price and source status, and a durable plan/notification path. Do not build the full position-management feature in this task.

## Preflight
1. Inspect R, M and Q Git heads, dirty work and relevant source/test bytes. Choose one source baseline and explain branch reconciliation. Preserve all pre-existing changes.
2. Inspect existing scanner/service, decision.case/service, market_watch state/alerting, notification and domain schemas and existing tests. Reuse tested functions.
3. Decide exact small files to change. Do not merge whole branches or create another framework.
4. Use an isolated code checkout/worktree. Never overwrite existing task or user work.

## Bounded implementation
- Fix derivatives-collection exception degradation and uninitialized optional fields, retaining explicit UNKNOWN/DEGRADED.
- Distinguish closed-bar analytic price from timely actionable quote, and record source event, received, available, decision and commit clocks. Bind cross-symbol/benchmark input timestamps to one decision.
- Implement a deterministic source-freshness/actionability veto, including missing required fields; preserve watch-only results on degradation.
- Normalize instrument prices via exchange tick-size and quantity steps where inputs are admitted; never round a tiny valid level to an invalid zero or suppress an actual price change through a two-decimal fingerprint.
- Persist candidate/plan evidence before notification, record attempts and failures, ensure notify=False never marks sent, and make crash/restart idempotent with the existing state/decision primitives.
- Avoid inventing user fills, dynamic exit profit claims, market quotes or calibrated probabilities.
- Do not implement news, live account access, real orders, multi-framework adapters, complete management compiler or production scoring.

## Acceptance tests (synthetic or deterministic fixtures only)
- Derivatives total failure and partial failure never crash scanning.
- Missing/stale quote, late closed candle, cross-symbol clock skew fail closed for ACTION but retain WATCH where appropriate.
- Entry/stop/target prices preserve tick semantics for BTC and low-priced examples.
- notify=False does not consume alert dedup; failed send remains eligible for retry; crash after commit cannot create conflicting plan identity.
- No uncommitted external alert; duplicate process/restart yields one durable event identity.
- No direct real network calls, forward/historical payload reads or external notifications.
- Show targeted test results, diff and original worktree/registry preservation receipts.

## Exclusions and future work
- T2B canonical fix is validated but remains isolated; only integrate it under a separate exact scope before canonical execution backtests. Do not copy it silently into this task.
- F0B publisher is conditionally useful only if MVP relies on that microstructure source; do not deploy it as a prerequisite here.
- Follow-on tasks: TRADEPLAN-LIFECYCLE-01 and MANAGEMENT-ALERTS-01.
- Any code integration, historical outcome study, access to protected forward payload, service restart/deployment, private account or order operation requires its own Owner approval.

## Controller reporting
Respond in Chinese to the Owner with: actual source baseline, findings, exact files changed, focused tests, preserved changes, known limitations, and ONE next recommendation. This task card alone is not approval.
