# v0.7.0 Advisory Delivery Roadmap

> **Canonical:** GitHub `docs/engineering`. [Documentation Branch Policy](V070_DOCUMENTATION_BRANCH_POLICY.md). Matching `v0.7.0` documents are historical copies.
Status: proposed by current Owner direction (2026-10-28); stages are not permissions and no gate is declared passed by this document.

## L4 canary advanced to tomorrow — Owner decision 2026-10-29

Controller 0-C records \`OWNER-V070-L4-WINDOW-20261030\`: **26h finite source acquisition on 2026-10-30 00:00Z to 2026-10-31 02:00Z (exclusive)**, equivalently 2026-10-30 08:00 to 2026-10-31 10:00 Beijing/Hong Kong. This NEW window supersedes the formerly authorized 2026-11-01/02 window; no operation under the old date. New isolated dated output \`artifacts/live_public_canary_20261030/\`, old blocked preflight preserved.

The same L4 B/C owner scope and self-attestation remain valid. Three Binance public USD-M symbols, nine already-approved public endpoint IDs, <=60 REST IP weight/min including retry, native stream quotas, minimum 36h raw/168h normalized retention and capped disk space remain unchanged. L4 Phase A is ACCEPT (590 pass, 3 old red, 204/204 fabricated replay). B/C native transport, source timing and finite launcher are NOT YET delivered. Prioritize engineering and simulated tests NOW, then a technical go/no-go and one operator-started finite canary in the exact new UTC window. No premature network requests, cron, sleep/background daemon, second engineering queue, original integration, accounts, orders, alerts or PRIMARY. If not ready by start, only shorten within current window; never extend beyond the end. A completed canary yields source/shadow qualification metrics, not Alpha.

## Latest Owner decision — 2026-10-29, L4 internal region gate lifted

Owner attests they have reviewed applicable regional/terms restrictions and authorize personal non-commercial public read-only market-data research: \`OWNER-V070-L4-REGION-ATTESTED-20261029\`. Controller 0-C accepts this as sufficient **for internal project dispatch**, replacing the earlier repeated demand for independent host-jurisdiction proof. It does not establish a legal opinion, excuse a known venue restriction, authorize VPN/proxy evasion or alter the strict source/clock/budget/time/retention controls. The older L4 B/C BLOCKED receipt remains preserved as historical state, not a current duplicate-review prerequisite.

Next action is the original **L4 B/C continuation only**, in the same isolated codebase: implement source-read-only REST/WS transport and one-shot operator launcher, test with simulated responses, verify endpoint-native timestamps/units/rate/actual disk/retention, and conduct a finite public-source/shadow canary **only inside the previously approved [2026-11-01T00:00Z, 2026-11-02T02:00Z) window** when technical gates pass. Do not schedule or make an early market request. No other worker/audit queue, private API, original integration, alerts, accounts, trading or economics.

## L4 B/C preflight terminal — 2026-10-29 22:14 Asia/Shanghai

The existing approved, finite Binance Global public USD-M source scope is **not rescinded**; `OWNER-V070-L4-3SYM-20261029` remains recorded. L4 B/C executor exited **BLOCKED — REGION_OR_TERMS_UNVERIFIED** before native transport implementation or any public market request. No market data, account actions, notifications or scheduled collection occurred. New 65 passing tests are prior-suite subset; Phase A's 590 unique pass / 3 legacy-red and 204/204 fabricated replay receipts remain unchanged. Original worktrees and 695 recorded Phase A files were preserved. No verified legal execution-host region/provider terms eligibility evidence exists in the current handoff. Do not guess from user UI location or route around restrictions.

The existing L4 B/C mandate is the ONLY potential continuation, after trusted host-jurisdiction and official permitted-use evidence plus endpoint/time/clock/cap/storage preflight. If host eligibility is prohibited/unverifiable, keep no-requests block. A materially different provider, region or acquisition window requires distinct Owner consent. No new worker/reviewer/collector or automatic rescheduling; the original [2026-11-01T00:00Z, 2026-11-02T02:00Z) window remains bounded and unscheduled.

## L4 Phase A milestone — 2026-10-29 19:38 Asia/Shanghai

Controller 0-C verifies `l4-readonly-source-canary-01` Phase A **ACCEPT / OFFLINE_READY_PENDING_AUTH**. Exact `L4_ACCEPTANCE.json`: 590 unique passes including 108 new L4 tests, 3 unchanged known-red legacy assertions (separate safety replacements pass), 0 skips/xfails, 204/204 fabricated raw-to-normalized replay pairs. Source transport calls, external notifications, account/order actions, deployed services and scheduled collectors: **0**. R/M/Q and the L23/Bridge/Platform isolated base hashes match within the preservation receipt's declared scope.

**Important newly evidenced bottlenecks:** 22-row endpoint policy only, no live transport or native source qualification; 36h raw receipt volume is estimated near **4.17 GB**, whereas the 16 MiB synthetic quota is insufficient. A future public-source run must specify sufficient disk quota/retention and verified per-endpoint weight/WS limits, legal/region/terms status, clock semantics, symbols and UTC acquisition window. Three-symbol source integrity may qualify while 10-symbol percentile ranks, >=201 aligned 5m bars for beta and other warmups remain disabled. No real-market/economic qualification follows.

**Queue:** L4 Phase A closes. Phases B/C in the **existing L4 A/B/C mandate** remain `BLOCKED_PENDING_OWNER_AUTH`; do not create a parallel task or worker. An exact Owner grant is required before implementing/enabling real public transport and before any source read. Without grant: terminate normally; do not wait, schedule or run in background. No original integration/deployment/notifications/credentials/accounts/orders/PRIMARY. One future phase-end source/shadow acceptance only.

## Controller 0-C L23 milestone — 2026-10-29

`l23-selector-evaluation-01` has reached **ACCEPT for isolated offline synthetic engineering**: 482 unique passing tests, three unchanged old-contract failures, zero skipped/xfail, plus four genuine multi-process tests. The deterministic V1 selector and source fields, 5m/1m monitoring, entry/limit lifecycle, conservative risk reservations, user-reported positions, shared exit policy, and episode funnel are implemented in a separate worktree. Its synthetic 26 scenario rows depend on three structural episodes and cannot establish market Alpha. The original R/M/Q trees are unintegrated and live source access remains BLOCKED_PENDING_OWNER_AUTH.

**Next major dependency:** [L4 Read-only Public-Source Canary](V070_L4_READONLY_SOURCE_CANARY_MANDATE_20261029.md). It has one safe offline preparation subphase under existing engineering permissions; ANY real public market network read requires a single explicit Owner approval fixing provider, symbols, endpoints/fields, UTC window, frequency/rate limits, retention and path. The proposed 2026-11-01 through 2026-11-02 UTC window is unapproved, not scheduled. No Q collector operations, deployment, external notifications, historical economic trial, PRIMARY, account connection or trading authority follows from this roadmap. Do not send a duplicate worker until current task ownership is checked.

## Controller 0-C Owner mandate — 2026-10-29

The Owner has assigned Controller 0-C sole responsibility for the delivery queue, phase grouping and evidence-based phase acceptance. The independent Strategic Advisor is a single concentrated audit option after a substantial phase, not a routine controller or approval gate. Ordinary Owner-authorized isolated engineering and offline synthetic tests may be autonomous within the stated safe scope. Do not imply approval for live data, original-worktree integration, services, protected studies, accounts or trades.

**Verified newer engineering baseline:** `/root/workspace/project/quant-0.7.0/multi-strategy-platform-01`, an isolated **WORKING_BASELINE (SYNTHETIC)** with 69 registered factors, 21 directional strategies, 7 research portfolio strategies, 158/158 new platform tests, 250/250 affected inherited regressions and 9/9 demos. The unchanged legacy contract suite remains **175 passed / 3 failed**. Only 3 strategies are `SYNTHETIC_VALIDATED`; 25 are `IMPLEMENTED_UNTESTED`. The prior Foundation Completion and unreconciled legacy fixture failures are historical engineering evidence, not reasons to discard this new platform; equally they do NOT establish an all-green integrated release or economic edge.

**Roadmap L1+L2:** One autonomous [offline source-contract + end-to-end multi-strategy advisory mandate](V070_L12_OFFLINE_MULTISTRATEGY_ADVISORY_MANDATE_20261029.md), executed only after verifying no overlapping active build session. L1 includes provider-neutral timestamps/quote/filter admission and a clear offline-to-live authorization boundary; L2 proves scan -> rank -> setup -> gated entry/expiry -> USER_REPORTED position -> risk recommendations -> durable fake notifications -> restart. No live Binance/OKX activation. Preserve all existing code and actual completed demos.
**Roadmap L3:** only after L1+L2 phase acceptance and exact data authorization if needed, strategy/factor comparison, entry-versus-exit ablation, no-fill/cost/funding and walk-forward ML challengers. Synthetic-only safe parts can be implemented without historical outcome reads.
**Roadmap L4:** conditional additional providers/equity market rules, richer UI and advanced ML or performance once safe L1+L2 behavior is demonstrated.

**Concurrency checkpoint:** at 2026-10-29 10:03 Asia/Shanghai, Codex platform-build thread `01a18378-9a0f-7e50-892c-9748674ed639` and Astra specialist thread `01a1855f-9b30-7e52-baab-c78573a3f6fd` were `inProgress`. The L1+L2 worker is **NOT DISPATCHED** until actual ownership/overlap is resolved. No repeat Opus/Astra program or micro-approval chain.

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

## Historical 2026-10-28 task sequencing (superseded for new work by the 2026-10-29 L1+L2 Owner mandate)
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
