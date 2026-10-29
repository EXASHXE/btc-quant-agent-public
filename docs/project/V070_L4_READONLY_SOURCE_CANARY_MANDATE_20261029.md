# V070-L4-READONLY-SOURCE-CANARY-01

Role: Codex autonomous Source Admission & Shadow Advisory Engineer.
Controller: Quant v0.7.0 Controller 0-C.
Mandate: one substantial phase, independent safe work and one terminal receipt; do not ask for repeated micro-approvals.
Status: PROPOSAL_ONLY until the Owner separately approves the exact live public-source scope. Current authorization permits isolated offline engineering/synthetic tests, NOT market network reads.

## Baseline and concurrency
- Read current GitHub docs/engineering AGENTS.md, branch policy, mission, roles, roadmap, handoff, and this card.
- Verify /root/workspace/project/quant-0.7.0/l23-selector-evaluation-01/L23_FINAL_DELIVERY.md, L23_ACCEPTANCE.json, L23_TEST_MATRIX.json, L23_PRESERVATION.json, artifacts/final/source_readiness.json, actual source and test artifacts.
- L23 is ACCEPT for isolated synthetic engineering only: 482 distinct passes, three unchanged legacy failures, no skips/xfails, 3 fabricated structural episodes, zero market API reads; original R/M/Q and source baselines were preserved within recorded scope.
- Ensure no other Codex session owns this phase; otherwise stop. Do not alter other task trees.
- Use a new isolated workspace /root/workspace/project/quant-0.7.0/l4-readonly-source-canary-01 only when execution has been granted.

## A. Immediately allowable OFFLINE work
- Record source hashes and preserve R/M/Q dirty work, indexes, existing collectors, baseline isolated projects and research registers.
- Inspect provider documentation/source-contract interface, timestamp/identity/units semantics and L23 readiness proposals without calling public market endpoints.
- Implement a strictly disabled-by-default public read-only transport seam in isolation; test exclusively against fabricated HTTP/socket responses, including timeouts, stale or missing exchange timestamps, endpoint schema drift, multi-symbol consistency, contract changes, rate-limit responses, clock skew, retry/backoff and recovery.
- Explicitly separate actual observed source timestamps from local receive/available timestamps. An absent verifiable exchange quote timestamp must stay UNKNOWN; never use the candle close or guessed event timestamp as an executable quote.
- Add an immutable, local-only observation ledger with configurable source identity, bounded retention, quotas, source health, exclusion reasons and no credential/account dependence.
- Preserve full synthetic L23/Bridge/Platform regression gates and three transparent known-red legacy cases. No source activation, scheduled collector or external alerts.

## B. Conditional future network canary — requires a NEW EXPLICIT OWNER GRANT
Before ANY first real request, require a source-scope file containing explicit Owner approval for:
- provider and venue (recommended Binance USDT-M, with separately selected public spot references),
- exact symbols and endpoints/streams/fields,
- UTC acquisition window (the current L23 proposal is 2026-11-01 00:00 to 2026-11-02 02:00 UTC; NOT authorized by this document),
- polling/stream cadence and hard per-endpoint/IP rate/weight cap,
- raw/normalized receipt retention and new isolated output path,
- no authenticated/private/account/trade endpoint, no live notifications and no interaction with the existing Q collector.
Approve one bounded staged canary under those same limits: first BTCUSDT/ETHUSDT/SOLUSDT to prove schema and clocks; then expand only to the specifically approved remaining symbols (up to the L23 proposed 12-symbol liquid universe) after source-health passes. If no grant or the clock/schema is unqualified, do not run network traffic; end with BLOCKED_PENDING_OWNER_AUTH or SOURCE_CLOCK_BLOCKED plus safe artifacts.
All GET/stream choices must be verified against current official API documentation BEFORE implementation/use. No endpoint is implicitly authorized because it was mentioned in source_readiness.json.
Collect only public market values after explicit approval; do not read 2024-2025 protected history, FINAL_HOLDOUT, or existing protected forward stores. Zero account credentials.

## C. Conditional local shadow advisory
If the canary is separately authorized and succeeds:
- Process genuine received observations using the existing L23 selector, three opt-in playbooks, field-level clock/source gates, typed quotes and risk checks, with actual receive/availability latency.
- Local-only WATCH/ARMED/ENTRY_ELIGIBLE proposals; no push service, no order, no account, no Owner-fill assumption. Real ACTION eligibility requires independent source evidence and current quote authority; otherwise downgrade to WATCH/RISK with explicit veto.
- Measure source availability/missingness, gaps, event-to-receive/decision delay, book freshness, API rate/weight use, 1/3/5-minute post-delivery simulated revalidation and expiration. Label modeled fills and simulated delivery as such; no realized performance claims.
- Maintain a strictly isolated data store and replay from recorded receipts; if the live pilot becomes blocked, preserve accepted offline work and stop network activity.
- Never schedule ongoing collection or run background services without the exact separate operational approval.

## Acceptance and deliverables
- One compact L4_CHECKPOINT.md and one L4_FINAL_DELIVERY.md.
- L4_SOURCE_GRANT_AND_ENDPOINT_MATRIX.json, L4_SOURCE_HEALTH.json, L4_ACCEPTANCE.json, L4_TEST_MATRIX.json, L4_PRESERVATION.json and actual approved scope if any.
- Frozen request/response schema fixtures, changed-source hashes, source/delivery/decision clocks, sample local-only shadow report and exact reproducible commands.
- Exact test counts, 3 known-red legacy assertions separately reported, schema/clock/rate/retention failures, authorization and runtime/collector preservation.
- Terminal status OFFLINE_READY_PENDING_AUTH, READONLY_CANARY_ACCEPT, SOURCE_CLOCK_BLOCKED, PARTIAL or BLOCKED. Never claim economic Alpha, deployment readiness, or verified fills.
- Report to Owner in Chinese at the coherent major milestone. No automatic successor and no recurring external audit.

STOP: Without an explicit source authorization, complete section A only and DO NOT run section B/C. No R/M/Q integration, commit/push, deployment, existing collector operations, real external notification, account/trading action, protected market reads, historical economics or PRIMARY registration.