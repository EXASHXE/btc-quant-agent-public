# QUANT v0.8.0 — Roadmap, Task Ownership and Exit Gates

Status: Controller-reconciled integrated delivery plan · 2026-11-18.
Owner directive: V080-OWNER-0C-CONSOLIDATED-DELIVERY-REPLAN-20261118.
Executable branch: v0.8.0 · canonical documentation: docs/engineering.
This plan consolidates engineering implementation and audit cycles; it does **not** consolidate or waive separate permissions for live public market API or private account access.

| Capability | Worker / scope | Current state | Exit / activation boundary |
|---|---|---|---|
| R0 baseline and Program J preservation | Owner / 0-C | Verified baseline; 323 protected Program J files | Historical evidence preserved |
| R1 PUBLIC_MARKET fixture-only foundation | GPT-6.2 Sol / 0-C | **SCOPED_ACCEPTED_OFFLINE_ONLY** | 99 targeted and 694 full offline tests independently passed; 367 sealed R1 artifacts; NO live permission |
| Full-system architecture audit | GPT-6.2 Astra / 0-C | **SCOPED_ACCEPTED_ARCHITECTURE_REVIEW_ONLY** | Five sealed reports, 97 independently checked cited source hashes; recommendations are advisory |
| Original narrow Stage 1A | GPT-6.2 Sol | **SUPERSEDED_FOR_FUTURE_FORWARDING / NOT_STARTED** | Existing Controller record retained unchanged; only the integrated B1 task is forwardable |
| **B1 PUBLIC_RUNTIME_FOUNDATION** | **GPT-6.2 Sol High** | **CONTROLLER_SCOPE_APPROVED / AWAITING_OWNER_FORWARD** | Single integrated implementation of 1A+1B+G10; independent package acceptance OFFLINE ONLY |
| First bounded live PUBLIC_MARKET scan | Owner local scope / 0-C capability activation | **NOT AUTHORIZED** | Only after B1 acceptance and separate region/route, endpoint, cadence, budget, retention and stop-condition review |
| **B2 MARKET_DECISION_MVP** | **GPT-6.2 Sol Extra High** | **PLANNED / NOT_DISPATCHED** | Full 4H/1H/15m/5m strategy → risk card → episode → 5/10-minute reprice → local journal; offline engine acceptance is not live-operational acceptance |
| **B3 ACCOUNT_AWARE_DECISION_SUPPORT** | **GPT-6.2 Sol Extra High** | **PLANNED / NOT_DISPATCHED** | Consolidate R2 signed-GET offline private connector + R3 reconciliation after stable B2 MarketPlan/SignalEpisode; independent read-only credential activation gate remains CLOSED |
| R5 universe expansion and market-only alerts | Sol / optional Hydrogen QA | PLANNED / NOT_DISPATCHED | B2 usable public market workflow plus scoped source/rate review; external Feishu separately authorized |
| R6 prospective evaluation | Sol / Astra challenge / 0-C | PLANNED / NOT_DISPATCHED | Capture signal/response denominators beginning with B2; economics require independently sufficient real evidence |
| Layer 3 TRADE_EXECUTION | No assigned worker | **DISABLED / EXCLUDED** | No route, trade key, auto order or automatic future stage |

## Current dispatch and accepted evidence

- R1 scoped acceptance: local code workspace controller-decisions/V080_CONTROLLER_R1_LAYER1_PUBLIC_OFFLINE_SCOPED_ACCEPTANCE_20261118.json, SHA-256 32ddbab7a7244852fb6c5948c057b2063c3d01be420d50eb4046ec8696baeefa.
- Astra scoped architecture acceptance: controller-decisions/V080_CONTROLLER_ASTRA_FULL_SYSTEM_ARCH_AUDIT_ACCEPTANCE_20261118.json, SHA-256 0213dcfc3a12419081404923c9d8112cbb532269f6fc537f2403ced9c4990663.
- Narrow 1A forward approval: controller-decisions/V080_CONTROLLER_SOL62_STAGE1A_BOUNDARY_CAUSALITY_FORWARD_APPROVAL_20261118.json. Worker not started at the Controller's latest local check. The record is historical and remains intact.
- Integrated B1 supplemental approval: controller-decisions/V080_CONTROLLER_SOL62_B1_PUBLIC_RUNTIME_FOUNDATION_FORWARD_APPROVAL_20261118.json. Its scope is offline only; actual worker forwarding and execution have NOT occurred.
- B1 canonical full task card: [V080 Sol B1 Public Runtime Foundation](../prompts/v0.8/V080_SOL62_PUBLIC_RUNTIME_FOUNDATION_B1_20261118.md).
- Original R2/R3 task cards remain **historical drafts**, not active worker dispatches; they will be consolidated into a separate B3 task only after B2 contracts stabilize.

## One consolidated package = one independent implementation acceptance

**B1:** Isolated PERSONAL_MVP install/entrypoint and no legacy execution reachability; causal snapshot V2 and NOT_EVALUATED; offline mock/loopback TLS HTTPS transport with exact unsigned GET allowlist, no redirects or response overrun; restart-safe request budgets and restrictions; funding/OI/public schema fixtures, bounded incremental warmup, separate slow/fast input refresh and crash recovery. Sol may implement and correct internal substeps under this one scope. Clean-install E2E, deterministic negative tests, hashes, QA, and one 0-C final offline acceptance. **Never send a real Binance request in B1.**

**B1 → first live public scan:** B1 implementation acceptance alone grants no external access. Owner completes one local operating scope with approved actual region/route, ten GET endpoints, initial BTC/ETH/SOL five timeframes, budgets, cadence, retention and stop conditions. Controller independently reviews before any expressly enabled bounded run. Existing Owner public-data attestation is reused; no duplicate attestation. On restriction, TLS or regional denial stop rather than route around it.

**B2:** Single larger strategy decision delivery: 4H regime, 1H setup (standard pullback + early continuation), independent completed 15m trigger, 5m actionability, 4H/1D obstacle and net R, hard SL/TP1–3, OI/funding/mark/depth, explicit WATCH/INVALID/NO_SETUP/SOURCE_BLOCKED/EXECUTABLE and reasons, versioned episode, local card, +5/+10m action-time reprice and journal. Without separately authorized and validated real public data it can only be **ACCEPTED_OFFLINE_INTEGRATED**, never represented as a live decision-ready MVP. Account unavailable means unit-risk/manual account check, not a fabricated safe trade size. Old simulation budgets are not personal approved limits.

**B3:** One substantial offline private-read + account overlay package after B2 MarketPlan and SignalEpisode are stable. Dedicated signed GET / private store, ordinary and Algo orders, positions/fills/income/fees/funding, non-atomic coverage, pagination/dedup/recovery, hedge legs, position protection and multi-to-many matching. Synthetic-only tests and one 0-C offline acceptance. **Private real access remains separate** and DISCONNECTED unless strictly read-only Futures USER_DATA permissions are proven without a trade-capable setting. Layer 1 and the public decision engine must work without Layer 2.

## Single engineering queue and review protocol

1. Controller approves one bounded implementation package; Owner forwards the complete worker prompt.
2. Sol is the sole core engineering writer, performs internal milestones/fixes/test iterations, and submits one sealed implementation handoff.
3. Hydrogen may do bounded mechanical fixtures/QA when helpful; Astra may review a material architecture/math fork. Neither dispatches engineering or self-accepts.
4. Controller independently checks installed artifact, provenance, targeted adversarial tests, representative regressions and seal hashes **once at package completion**, not after every internal step. Do not impose arbitrary test-count quotas or repeat full R1 reacceptance absent changed risk.
5. External capability activation (first live public scan, real private read, external notification, any financial action) is independent. Only actual Controller acceptance and applicable Owner authorization permit progression.

PERSONAL_MVP remains separate from STRICT_RESEARCH. No economic or profitability qualification is implied by a test suite, deterministic fixtures or a single real scan.
