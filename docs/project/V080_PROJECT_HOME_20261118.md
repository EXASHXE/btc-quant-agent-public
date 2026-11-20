# QUANT v0.8.0 — Project Home and Baseline (updated 2026-11-20)

Status: R1/B1 SCOPED_ACCEPTED_OFFLINE_ONLY; B2 SCOPED_ACCEPTED_OFFLINE_INTEGRATED_ONLY; B3 SCOPED_ACCEPTED_OFFLINE_ACCOUNT_AWARE_ONLY; B4 SCOPED_ACCEPTED_OFFLINE_PUBLIC_BRIDGE_ONLY. B5 Phase A offline engineering scope approved / awaiting Owner forwarding; Phase B genuine scan NOT AUTHORIZED. Genuine-public physical origin, real-private access, external messaging and trading remain disabled.
Product: Personal Trading Decision Support.
Local root: /root/workspace/project/quant-0.8.0/
Executable code/runtime branch: v0.8.0 in EXASHXE/btc-quant-agent-public.
Canonical project documentation branch: docs/engineering. All project, role, architecture, roadmap, task-card, handoff and new-chat documentation is maintained there; same-path documentation copies on v0.8.0 are non-authoritative.

## Canonical v0.8.0 documents — all maintained on docs/engineering

- [Owner decision](V080_OWNER_REBASELINE_DECISION_20261118.md)
- [Three-layer API architecture](../architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md)
- [Binance API endpoint matrix](../architecture/V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md)
- [Roadmap and gates](V080_ROADMAP_AND_GATES_20261118.md)
- [Owner model-routing policy](V080_MODEL_ROUTING_POLICY_20261119.md)
- [One-time public operating scope](V080_PERSONAL_PUBLIC_MARKET_OPERATING_SCOPE_20261118.md)
- [Canonical documentation branch policy](V080_DOCUMENTATION_BRANCH_POLICY_20261118.md)
- [Prompt copy-card standard](V080_PROMPT_COPY_CARD_STANDARD_20261118.md)
- [Baseline migration record](V080_BASELINE_MIGRATION_RECORD_20261118.md)
- [Active role matrix](../roles/V080_ACTIVE_ROLE_MATRIX_20261118.md)
- [R1 PUBLIC_MARKET task](../prompts/v0.8/V080_SOL62_PERSONAL_MVP_LAYER1_PUBLIC_IMPLEMENTATION_20261118.md)
- [R2 PRIVATE_USER_DATA draft](../prompts/v0.8/V080_SOL62_PERSONAL_MVP_LAYER2_USER_DATA_DRAFT_20261118.md)
- [R3 account/signal overlay draft](../prompts/v0.8/V080_SOL62_ACCOUNT_SIGNAL_OVERLAY_R3_DRAFT_20261118.md)
- [B1 integrated public runtime task — Controller accepted offline only](../prompts/v0.8/V080_SOL62_PUBLIC_RUNTIME_FOUNDATION_B1_20261118.md)
- [B2 integrated market decision MVP task — Controller accepted offline-integrated only](../prompts/v0.8/V080_SOL62_MARKET_DECISION_MVP_B2_20261118.md)
- [B3 consolidated account-aware decision support — Gemini Neon delivered, Controller accepted offline only](../prompts/v0.8/V080_PERSONAL_MVP_ACCOUNT_AWARE_DECISION_SUPPORT_B3_20261119.md)
- [B4 public-source bridge — Controller accepted offline only; live remains disabled](../prompts/v0.8/V080_PUBLIC_SOURCE_BRIDGE_B4_20261120.md)
- [B5 genuine public source + first bounded scan — Phase A only approved for Owner forwarding](../prompts/v0.8/V080_LIVE_PUBLIC_FIRST_BOUNDED_SCAN_B5_20261120.md)
- [1-A new chat](../prompts/v0.8/V080_NEW_CHAT_1A_20261118.md)
- [0-C new chat](../prompts/v0.8/V080_NEW_CHAT_CONTROLLER_0C_20261118.md)

The local scope template, Owner directive and Program J hash manifest remain local operational artifacts in the v0.8.0 workspace. They are not copied to this docs-only branch unless separately reviewed for publication.

## What changed
v0.8.0 is a product rebaseline, not an API note appended to v0.7.0:
1. Public market data and private account data are separate layers with separate permission and storage boundaries.
2. The Owner's existing public-data statement is reused as OWNER_ATTESTED; it is not represented as an independent legal opinion or venue certification.
3. Private USER_DATA is a new optional, local-only, signed GET layer using a dedicated read-only API key.
4. TRADE_EXECUTION remains disabled and unreachable.
5. Personal operating rules are lighter than Strict Research, but candle finality, no-lookahead, TLS, freshness, rate limits, cost-aware risk and private-data protection remain mandatory.
6. The 2–12h trading decision cadence is retained: 1D / 4H / 1H / 15m / 5m.

## Source lineage and branch
The GitHub v0.8.0 branch is the executable code/runtime baseline derived from the executable v0.7.0 branch. The canonical project-document source is docs/engineering; any matching Markdown retained on v0.8.0 is a historical or implementation-time mirror. The local code workspace is separately prepared at the exact requested path.

baseline/program-j/ is a read-only local copy of the accepted Program J source, tests, configs, contracts, tools and release locks. Exact hashes are in baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json. The source is not edited in place. New implementation must happen in a task-specific isolated workspace.

## Reusable Owner evidence
OWNER_STANDING_M2_AUTHORIZATION_20261024.md is preserved byte-identically. Its provenance remains CURRENT_USER_DIRECT_MESSAGE / OWNER_ATTESTED. It is reusable for the same personal, noncommercial, private/local, read-only public-market-data scope. Do not ask the Owner to repeat it.

This attestation does not claim Binance legal approval, third-party legal certification, or permission for a different region, commercial use, redistribution, private account access or trading. Program N's one-shot invocation remains consumed and must not be replayed.

## Current state — 2026-11-19

| Workstream | Controller-reconciled state | Notes |
|---|---|---|
| Baseline / Program J | VERIFIED | 323 preserved files, source/code baseline pinned |
| R1 PUBLIC_MARKET | **SCOPED_ACCEPTED_OFFLINE_ONLY** | 0-C independently reran 99 targeted and 694 full tests; 367 sealed outputs |
| Astra full-system review | **SCOPED_ACCEPTED_ARCHITECTURE_REVIEW_ONLY** | Evidence-based architecture recommendations; not implementation authorization |
| Narrow Stage 1A | **SUPERSEDED_FOR_FUTURE_FORWARDING / NOT_STARTED** | Original decision preserved; no overlapping workspace found |
| **B1 PUBLIC_RUNTIME_FOUNDATION** | **SCOPED_ACCEPTED_OFFLINE_ONLY** | 89 B1 + 99 inherited targeted tests independently PASS; genuine-public origin remains dormant |
| **B4 PUBLIC_SOURCE_BRIDGE** | **SCOPED_ACCEPTED_OFFLINE_PUBLIC_BRIDGE_ONLY** | gpt-6.2-sol xhigh; Controller independent B4/B1/B2 28/89/54 tests PASS; 50 sealed files; real physical origin still absent |
| **B5 GENUINE_PUBLIC_SOURCE + FIRST BOUNDED SCAN** | **PHASE_A_APPROVED / AWAITING_OWNER_FORWARD** | Sol Extra High primary, Gemini Neon XHigh fallback; genuine-source code and gates offline first; actual one-shot network phase requires separate Owner+Controller activation |
| First live public GET activation | **NOT AUTHORIZED** | Requires accepted B1 and separate completed local operating scope |
| **B2 MARKET_DECISION_MVP** | **SCOPED_ACCEPTED_OFFLINE_INTEGRATED_ONLY** | Sol Extra High; Controller independently reran 54/54 B2 + 89/89 B1 tests, installed both wheels and recalculated 24 paths; genuine market integration remains dormant |
| **B3 ACCOUNT_AWARE_DECISION_SUPPORT** | **SCOPED_ACCEPTED_OFFLINE_ACCOUNT_AWARE_ONLY** | Gemini 4 Neon XHigh; 51 B3 + 54 inherited B2 independent PASS; 183/183 sealed files, 17 synthetic scenarios, no live credentials/API |
| R5 controlled expansion/notifications | PLANNED | Feishu external activation remains separately gated |
| R6 prospective evaluation | PLANNED | Collect event denominators starting with B2; no Alpha claims |
| Layer 3 TRADE | DISABLED | No trade key, route or worker |

Original R2/R3 draft prompts remain references, not dispatched tasks. B2 has now passed the independent 0-C offline-integrated acceptance. A separate reviewed real-origin source bridge and operating scope are necessary before a live market decision workflow. For current execution order and capability-specific gates see [Roadmap and Gates](V080_ROADMAP_AND_GATES_20261118.md).

## Controller evidence (local v0.8.0 workspace only)

- R1 scoped acceptance: controller-decisions/V080_CONTROLLER_R1_LAYER1_PUBLIC_OFFLINE_SCOPED_ACCEPTANCE_20261118.json (SHA-256 32ddbab7a7244852fb6c5948c057b2063c3d01be420d50eb4046ec8696baeefa).
- Astra architecture scoped acceptance: controller-decisions/V080_CONTROLLER_ASTRA_FULL_SYSTEM_ARCH_AUDIT_ACCEPTANCE_20261118.json (SHA-256 0213dcfc3a12419081404923c9d8112cbb532269f6fc537f2403ced9c4990663).
- Supplemental B1 scope approval: controller-decisions/V080_CONTROLLER_SOL62_B1_PUBLIC_RUNTIME_FOUNDATION_FORWARD_APPROVAL_20261118.json. Historical; B1 worker has since delivered and been accepted offline only.
- **B1 offline acceptance:** controller-decisions/V080_CONTROLLER_B1_PUBLIC_RUNTIME_OFFLINE_SCOPED_ACCEPTANCE_20261118.json, SHA-256 b42ad44bc91a5fe89e7e2209ba4682ca5232d6611c5340b2b5febfe356a08cbf. B1 56 artifacts sealed, 89/89 tests independently rerun, 99/99 R1 targeted regression, all 323 Program J files verified.
- **B2 scope approval:** controller-decisions/V080_CONTROLLER_SOL62_B2_MARKET_DECISION_MVP_FORWARD_APPROVAL_20261118.json (historical pre-execution approval).
- **Neon policy adoption:** controller-decisions/V080_CONTROLLER_GEMINI_NEON_ROUTING_ADOPTION_20261119.json (Owner-directed routing only; no new worker or permission).
- **B4 offline forward approval (historical):** controller-decisions/V080_CONTROLLER_B4_PUBLIC_SOURCE_BRIDGE_OFFLINE_FORWARD_APPROVAL_20261120.json. Owner subsequently forwarded the task to gpt-6.2-sol xhigh; B4 has completed and been independently accepted for offline scope only.
- **B5 Phase A offline forward scope approval:** controller-decisions/V080_CONTROLLER_B5_LIVE_PUBLIC_TWO_PHASE_FORWARD_APPROVAL_20261120.json. One B5 task combines offline source binding and conditional first genuine scan; only Phase A is forwardable now, Phase B remains NOT_AUTHORIZED and requires separate actual Owner+0-C scope activation.
- **B4 offline scoped acceptance:** controller-decisions/V080_CONTROLLER_B4_PUBLIC_SOURCE_BRIDGE_OFFLINE_SCOPED_ACCEPTANCE_20261120.json, SHA-256 095dc79a730b843257947f6d77760a741efb67a6973880c4f9a806ef9ec86b58. Independently reran 28 B4 + 89 B1 + 54 B2, checked 50/50 B4 seals, rebuilt wheel, 16 cards/8 reprices and recalculated 36 Decimal conditional paths; genuine-public entry exits code 3. No authentic live market data or trading capability authorized.
- **B3 offline account-aware acceptance:** controller-decisions/V080_CONTROLLER_B3_ACCOUNT_AWARE_OFFLINE_SCOPED_ACCEPTANCE_20261120.json, SHA-256 0d3b88ea3bcedeab9f8d18d8118929be4610ecfa433d2bd35cd6fc7f96b8d7a0. Controller independently verified 183/183 B3 sealed files, 51/51 B3 and 54/54 inherited B2 offline tests, 17 synthetic scenarios and exact 183-file byte identity with pre-seal evidence. Prior HOLD_SEAL_MISSING closed. Real private/public access remains disabled.
- **B2 offline-integrated acceptance:** controller-decisions/V080_CONTROLLER_B2_MARKET_DECISION_OFFLINE_INTEGRATED_ACCEPTANCE_20261119.json, SHA-256 7de93eed45541d09a3b65b3e8452033c894ad402a169306bd97e4952929ac48d. Controller reran 54 B2 and 89 B1 tests, verified 93 B2, 56 B1, 367 R1 and 323 Program J hashes, checked clean install and recomputed 24 Decimal conditional paths. The first isolated review-copy test attempt needed an explicit B1 DB path; its rerun passed 54/54. Account context and real-source eligibility remain unavailable.

## Next action

**B4 is complete and independently accepted offline only.** B5 is now the single consolidated follow-on task; Owner can forward [the full B5 prompt](../prompts/v0.8/V080_LIVE_PUBLIC_FIRST_BOUNDED_SCAN_B5_20261120.md) to Sol Extra High (Neon XHigh if unavailable) to complete **Phase A offline physical-source integration**, then hand off READY_FOR_ACTIVATION_REVIEW. B5 Phase B is a separate Owner+Controller one-shot activation under the same task ID; no real Binance requests are authorized by Phase A forwarding. No duplicate B4 or new microtask is needed.

B2 has been independently accepted for offline synthetic decision integration. It is no longer awaiting Controller review, and no duplicate B2 worker is needed. For the first genuine public-market decision workflow, separately review the Owner-controlled operating scope AND the B1/B2 genuine-origin binding and activation change; existing B1 and B2 wheels deliberately refuse genuine-public operation.

B3 remains **SCOPED_ACCEPTED_OFFLINE_ACCOUNT_AWARE_ONLY** and fully separate from B4. Private Futures USER_DATA permission feasibility remains unproved. The public-data first scan is the immediate product-utility dependency, but even after B4 acceptance it requires a reviewed physical host binding, completed Owner region/route and retention scope, official rate-weight validation, and a new activation decision. Layer 3 remains disabled.

## Owner model-routing update — 2026-11-19

Gemini Neon is an Owner-designated peer-level model to GPT-6.2 Sol for complex engineering. For B3, the Owner selected Neon and the package was delivered under the Gemini 4 Neon XHigh worker label. Sol Extra High was the unused fallback. For other tasks, use the model-routing policy and Controller-approved non-overlapping work scopes. Hydrogen remains for simple bounded work; Astra remains the architecture advisor. Historical Gemini Argon records are not rewritten.
