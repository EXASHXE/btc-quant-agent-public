# QUANT v0.8.0 — Roadmap, Task Ownership and Exit Gates

Status: Controller-reconciled integrated delivery plan · 2026-11-20; B1 accepted OFFLINE ONLY, B2 accepted OFFLINE INTEGRATED ONLY and B3 accepted OFFLINE ACCOUNT-AWARE ONLY.
Current model routing: [V080 Model Routing Policy](V080_MODEL_ROUTING_POLICY_20261119.md).
Owner directive: V080-OWNER-0C-CONSOLIDATED-DELIVERY-REPLAN-20261118.
Executable branch: v0.8.0 · canonical documentation: docs/engineering.
This plan consolidates engineering implementation and audit cycles; it does **not** consolidate or waive separate permissions for live public market API or private account access.

| Capability | Worker / scope | Current state | Exit / activation boundary |
|---|---|---|---|
| R0 baseline and Program J preservation | Owner / 0-C | Verified baseline; 323 protected Program J files | Historical evidence preserved |
| R1 PUBLIC_MARKET fixture-only foundation | GPT-6.2 Sol / 0-C | **SCOPED_ACCEPTED_OFFLINE_ONLY** | 99 targeted and 694 full offline tests independently passed; 367 sealed R1 artifacts; NO live permission |
| Full-system architecture audit | GPT-6.2 Astra / 0-C | **SCOPED_ACCEPTED_ARCHITECTURE_REVIEW_ONLY** | Five sealed reports, 97 independently checked cited source hashes; recommendations are advisory |
| Original narrow Stage 1A | GPT-6.2 Sol | **SUPERSEDED_FOR_FUTURE_FORWARDING / NOT_STARTED** | Existing Controller record retained unchanged; only the integrated B1 task is forwardable |
| **B1 PUBLIC_RUNTIME_FOUNDATION** | **GPT-6.2 Sol High** | **SCOPED_ACCEPTED_OFFLINE_ONLY** | 89 B1 tests and 99 inherited targeted tests independently PASS; no real API; live composition dormant |
| First bounded live PUBLIC_MARKET scan | Owner local scope / 0-C capability activation | **NOT AUTHORIZED** | Only after B1 acceptance and separate region/route, endpoint, cadence, budget, retention and stop-condition review |
| **B2 MARKET_DECISION_MVP** | **GPT-6.2 Sol Extra High** | **SCOPED_ACCEPTED_OFFLINE_INTEGRATED_ONLY** | 54 B2 + 89 B1 independently rerun PASS; 16 synthetic cards/8 reprices, 24 independent path calculations; real market access/economic proof excluded |
| **B3 ACCOUNT_AWARE_DECISION_SUPPORT** | **Gemini 4 Neon XHigh** | **SCOPED_ACCEPTED_OFFLINE_ACCOUNT_AWARE_ONLY** | 51 B3 + 54 inherited B2 independently PASS; 183 files sealed, 17 synthetic scenarios, zero private live activation |
| R5 universe expansion and market-only alerts | Sol or Gemini Neon / optional Hydrogen QA | PLANNED / NOT_DISPATCHED | B2 usable public market workflow plus scoped source/rate review; external Feishu separately authorized |
| R6 prospective evaluation | Sol or Gemini Neon / Astra challenge / 0-C | PLANNED / NOT_DISPATCHED | Capture signal/response denominators beginning with B2; economics require independently sufficient real evidence |
| Layer 3 TRADE_EXECUTION | No assigned worker | **DISABLED / EXCLUDED** | No route, trade key, auto order or automatic future stage |

## Current dispatch and accepted evidence

- R1 scoped acceptance: local code workspace controller-decisions/V080_CONTROLLER_R1_LAYER1_PUBLIC_OFFLINE_SCOPED_ACCEPTANCE_20261118.json, SHA-256 32ddbab7a7244852fb6c5948c057b2063c3d01be420d50eb4046ec8696baeefa.
- Astra scoped architecture acceptance: controller-decisions/V080_CONTROLLER_ASTRA_FULL_SYSTEM_ARCH_AUDIT_ACCEPTANCE_20261118.json, SHA-256 0213dcfc3a12419081404923c9d8112cbb532269f6fc537f2403ced9c4990663.
- Narrow 1A forward approval: controller-decisions/V080_CONTROLLER_SOL62_STAGE1A_BOUNDARY_CAUSALITY_FORWARD_APPROVAL_20261118.json. Worker not started at the Controller's latest local check. The record is historical and remains intact.
- Integrated B1 supplemental approval: controller-decisions/V080_CONTROLLER_SOL62_B1_PUBLIC_RUNTIME_FOUNDATION_FORWARD_APPROVAL_20261118.json. Historical pre-execution approval; B1 has since completed.
- **B1 independent offline acceptance:** controller-decisions/V080_CONTROLLER_B1_PUBLIC_RUNTIME_OFFLINE_SCOPED_ACCEPTANCE_20261118.json (SHA-256 b42ad44bc91a5fe89e7e2209ba4682ca5232d6611c5340b2b5febfe356a08cbf). Verified 56 B1 sealed files, 89 B1 plus 99 inherited R1 PASS, Program J 323 original files unchanged.
- **B2 supplemental scope approval:** controller-decisions/V080_CONTROLLER_SOL62_B2_MARKET_DECISION_MVP_FORWARD_APPROVAL_20261118.json. Owner forwarding and worker execution subsequently occurred.
- **B3 independent offline-only acceptance:** controller-decisions/V080_CONTROLLER_B3_ACCOUNT_AWARE_OFFLINE_SCOPED_ACCEPTANCE_20261120.json, SHA-256 0d3b88ea3bcedeab9f8d18d8118929be4610ecfa433d2bd35cd6fc7f96b8d7a0. B3 seal corrected (183/183 hashes), compared byte-for-byte with the pre-seal copy, 51/51 B3 + 54/54 B2 independent tests PASS; previous HOLD_SEAL_MISSING closed. No private API, real credentials, Feishu, deployment or trading authority.
- **B2 independent offline-integrated acceptance:** controller-decisions/V080_CONTROLLER_B2_MARKET_DECISION_OFFLINE_INTEGRATED_ACCEPTANCE_20261119.json, SHA-256 7de93eed45541d09a3b65b3e8452033c894ad402a169306bd97e4952929ac48d. Controller independently reran 54/54 B2 and 89/89 B1 tests, reinstalled the pinned wheels, checked 93 B2/56 B1/367 R1/323 Program J hashes and recalculated 24 conditional Decimal paths. Nonblocking review-copy test path dependency was resolved with explicit B1 database configuration.
- Canonical complete B2 task: [V080 Sol B2 Market Decision MVP](../prompts/v0.8/V080_SOL62_MARKET_DECISION_MVP_B2_20261118.md). Historical assigned executor remains Sol; Neon routing does not retroactively reassign it.
- **Neon routing adoption:** controller-decisions/V080_CONTROLLER_GEMINI_NEON_ROUTING_ADOPTION_20261119.json; B3 executor is Owner-selected as Gemini Neon; GPT-6.2 Sol Extra High is the fallback if Neon capacity is insufficient.
- B1 canonical full task card: [V080 Sol B1 Public Runtime Foundation](../prompts/v0.8/V080_SOL62_PUBLIC_RUNTIME_FOUNDATION_B1_20261118.md).
- Original R2/R3 task cards remain **historical drafts**, not active worker dispatches. Their scope was consolidated into [B3 Account-Aware Decision Support](../prompts/v0.8/V080_PERSONAL_MVP_ACCOUNT_AWARE_DECISION_SUPPORT_B3_20261119.md), implemented by Gemini 4 Neon XHigh and independently accepted offline only. Historical prompt and original worker attribution are preserved.

## One consolidated package = one independent implementation acceptance

**B1:** Isolated PERSONAL_MVP install/entrypoint and no legacy execution reachability; causal snapshot V2 and NOT_EVALUATED; offline mock/loopback TLS HTTPS transport with exact unsigned GET allowlist, no redirects or response overrun; restart-safe request budgets and restrictions; funding/OI/public schema fixtures, bounded incremental warmup, separate slow/fast input refresh and crash recovery. Sol may implement and correct internal substeps under this one scope. Clean-install E2E, deterministic negative tests, hashes, QA, and one 0-C final offline acceptance. **Never send a real Binance request in B1.**

**B1/B2 → first live public scan:** B1 is accepted offline and B2 is accepted offline integrated; B1 live entrypoint deliberately exits with LIVE_CAPABILITY_DORMANT and the B2 adapter admits only fixture/loopback QA origins. A genuine-public workflow requires separately reviewed origin binding in BOTH relevant layers and a separate capability activation, not merely a config flag. B1 implementation acceptance alone grants no external access. Owner completes one local operating scope with approved actual region/route, ten GET endpoints, initial BTC/ETH/SOL five timeframes, budgets, cadence, retention and stop conditions. Controller independently reviews before any expressly enabled bounded run. Existing Owner public-data attestation is reused; no duplicate attestation. On restriction, TLS or regional denial stop rather than route around it.

**B2:** Single larger strategy decision delivery: 4H regime, 1H setup (standard pullback + early continuation), independent completed 15m trigger, 5m actionability, 4H/1D obstacle and net R, hard SL/TP1–3, OI/funding/mark/depth, explicit WATCH/INVALID/NO_SETUP/SOURCE_BLOCKED/EXECUTABLE and reasons, versioned episode, local card, +5/+10m action-time reprice and journal. B2 is **SCOPED_ACCEPTED_OFFLINE_INTEGRATED_ONLY** and is not yet a live decision-ready MVP. Account unavailable means unit-risk/manual account check, not a fabricated safe trade size. Old simulation budgets are not personal approved limits.

**B3 (ACCEPTED OFFLINE ONLY):** Gemini 4 Neon delivered an independent fake-signed GET/private-fixture store, ordinary/Algo orders, positions/fills/income/fees/funding, pagination/checkpoints, hedge protection and multi-to-many signal matching. The Controller validated 51/51 B3 tests, 54/54 inherited B2 regressions, hash-pinned install, 17 synthetic cases and 183/183 SHA seals. **Private real access remains separate** and DISCONNECTED unless strictly read-only Futures USER_DATA permissions are proven without a trade-capable setting. The public market decision engine runs without Layer 2.

## Single engineering queue and review protocol

1. Controller approves one bounded implementation package; Owner forwards the complete worker prompt.
2. Gemini Neon is the Owner-selected primary core engineering writer for B3, at the same project task-complexity tier as GPT-6.2 Sol. GPT-6.2 Sol Extra High is the fallback if Neon quota/capacity is insufficient. For other packages, routing remains task-specific and must not be inferred from this B3 assignment.
3. Use one primary writer per work package. Do not allow Sol and Neon to edit the same files or shared mutable integration surface concurrently. B3 is one integrated accounting/matching package and is assigned to a single core writer. Hydrogen remains for bounded mechanical fixtures/QA; Astra reviews material architecture/math forks. Neither worker model dispatches or self-accepts.
4. Controller independently checks installed artifact, provenance, targeted adversarial tests, representative regressions and seal hashes **once at package completion**, not after every internal step. Do not impose arbitrary test-count quotas or repeat full R1 reacceptance absent changed risk.
5. External capability activation (first live public scan, real private read, external notification, any financial action) is independent. Only actual Controller acceptance and applicable Owner authorization permit progression.

PERSONAL_MVP remains separate from STRICT_RESEARCH. No economic or profitability qualification is implied by a test suite, deterministic fixtures or a single real scan.

## Owner model-routing update — 2026-11-19

Gemini Neon replaces Gemini Argon for future complex engineering execution. Neon is routed at the same project task-complexity tier as GPT-6.2 Sol, especially for Sol quota fallback or Controller-approved independent parallel work. This is not a universal benchmark claim. Record the exact execution-interface model ID. Historical Argon reviews remain unchanged. See [V080 Model Routing Policy](V080_MODEL_ROUTING_POLICY_20261119.md).
