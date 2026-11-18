# QUANT v0.8.0 — Project Home and Baseline (2026-11-18)

Status: R1 and B1 SCOPED_ACCEPTED_OFFLINE_ONLY; Astra architecture audit accepted; B2 scope approved for Owner forwarding, not started. Real Binance market/API activation remains disabled.
Product: Personal Trading Decision Support.
Local root: /root/workspace/project/quant-0.8.0/
Executable code/runtime branch: v0.8.0 in EXASHXE/btc-quant-agent-public.
Canonical project documentation branch: docs/engineering. All project, role, architecture, roadmap, task-card, handoff and new-chat documentation is maintained there; same-path documentation copies on v0.8.0 are non-authoritative.

## Canonical v0.8.0 documents — all maintained on docs/engineering

- [Owner decision](V080_OWNER_REBASELINE_DECISION_20261118.md)
- [Three-layer API architecture](../architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md)
- [Binance API endpoint matrix](../architecture/V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md)
- [Roadmap and gates](V080_ROADMAP_AND_GATES_20261118.md)
- [One-time public operating scope](V080_PERSONAL_PUBLIC_MARKET_OPERATING_SCOPE_20261118.md)
- [Canonical documentation branch policy](V080_DOCUMENTATION_BRANCH_POLICY_20261118.md)
- [Prompt copy-card standard](V080_PROMPT_COPY_CARD_STANDARD_20261118.md)
- [Baseline migration record](V080_BASELINE_MIGRATION_RECORD_20261118.md)
- [Active role matrix](../roles/V080_ACTIVE_ROLE_MATRIX_20261118.md)
- [R1 PUBLIC_MARKET task](../prompts/v0.8/V080_SOL62_PERSONAL_MVP_LAYER1_PUBLIC_IMPLEMENTATION_20261118.md)
- [R2 PRIVATE_USER_DATA draft](../prompts/v0.8/V080_SOL62_PERSONAL_MVP_LAYER2_USER_DATA_DRAFT_20261118.md)
- [R3 account/signal overlay draft](../prompts/v0.8/V080_SOL62_ACCOUNT_SIGNAL_OVERLAY_R3_DRAFT_20261118.md)
- [B1 integrated public runtime task — Controller accepted offline only](../prompts/v0.8/V080_SOL62_PUBLIC_RUNTIME_FOUNDATION_B1_20261118.md)
- [B2 integrated market decision MVP task — Controller scope approved, Owner forwarding pending](../prompts/v0.8/V080_SOL62_MARKET_DECISION_MVP_B2_20261118.md)
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

## Current state — 2026-11-18

| Workstream | Controller-reconciled state | Notes |
|---|---|---|
| Baseline / Program J | VERIFIED | 323 preserved files, source/code baseline pinned |
| R1 PUBLIC_MARKET | **SCOPED_ACCEPTED_OFFLINE_ONLY** | 0-C independently reran 99 targeted and 694 full tests; 367 sealed outputs |
| Astra full-system review | **SCOPED_ACCEPTED_ARCHITECTURE_REVIEW_ONLY** | Evidence-based architecture recommendations; not implementation authorization |
| Narrow Stage 1A | **SUPERSEDED_FOR_FUTURE_FORWARDING / NOT_STARTED** | Original decision preserved; no overlapping workspace found |
| **B1 PUBLIC_RUNTIME_FOUNDATION** | **SCOPED_ACCEPTED_OFFLINE_ONLY** | 89 B1 + 99 inherited targeted tests independently PASS; genuine-public origin remains dormant |
| First live public GET activation | **NOT AUTHORIZED** | Requires accepted B1 and separate completed local operating scope |
| **B2 MARKET_DECISION_MVP** | **SCOPE_APPROVED / AWAITING_OWNER_FORWARD** | Sol Extra High; one integrated offline strategy, risk card, 5/10m reprice and local journal |
| **B3 ACCOUNT_AWARE_DECISION_SUPPORT** | PLANNED / NOT_DISPATCHED | Sol Extra High; merge R2 + R3 offline, after stable B2 episode contracts |
| R5 controlled expansion/notifications | PLANNED | Feishu external activation remains separately gated |
| R6 prospective evaluation | PLANNED | Collect event denominators starting with B2; no Alpha claims |
| Layer 3 TRADE | DISABLED | No trade key, route or worker |

Original R2/R3 draft prompts remain references, not dispatched tasks. B2 is approved for Owner forwarding but has not been independently implemented or accepted. For current execution order and capability-specific gates see [Roadmap and Gates](V080_ROADMAP_AND_GATES_20261118.md).

## Controller evidence (local v0.8.0 workspace only)

- R1 scoped acceptance: controller-decisions/V080_CONTROLLER_R1_LAYER1_PUBLIC_OFFLINE_SCOPED_ACCEPTANCE_20261118.json (SHA-256 32ddbab7a7244852fb6c5948c057b2063c3d01be420d50eb4046ec8696baeefa).
- Astra architecture scoped acceptance: controller-decisions/V080_CONTROLLER_ASTRA_FULL_SYSTEM_ARCH_AUDIT_ACCEPTANCE_20261118.json (SHA-256 0213dcfc3a12419081404923c9d8112cbb532269f6fc537f2403ced9c4990663).
- Supplemental B1 scope approval: controller-decisions/V080_CONTROLLER_SOL62_B1_PUBLIC_RUNTIME_FOUNDATION_FORWARD_APPROVAL_20261118.json. Historical; B1 worker has since delivered and been accepted offline only.
- **B1 offline acceptance:** controller-decisions/V080_CONTROLLER_B1_PUBLIC_RUNTIME_OFFLINE_SCOPED_ACCEPTANCE_20261118.json, SHA-256 b42ad44bc91a5fe89e7e2209ba4682ca5232d6611c5340b2b5febfe356a08cbf. B1 56 artifacts sealed, 89/89 tests independently rerun, 99/99 R1 targeted regression, all 323 Program J files verified.
- **B2 scope approval:** controller-decisions/V080_CONTROLLER_SOL62_B2_MARKET_DECISION_MVP_FORWARD_APPROVAL_20261118.json; this is not worker execution or acceptance.

## Next action

Owner may forward the [Controller-approved B2 integrated offline market decision MVP prompt](../prompts/v0.8/V080_SOL62_MARKET_DECISION_MVP_B2_20261118.md) to GPT-6.2 Sol. Its entire 4H/1H/15m/5m strategy, net-R/risk card, immutable episode, 5/10-minute reprice and local journal is one consolidated implementation package and one future independent Controller acceptance.

In parallel with B2 engineering planning, the first real public scan requires a separately completed Owner-controlled operating scope and a **new reviewed real-origin binding/activation**, because the accepted B1 wheel deliberately returns LIVE_CAPABILITY_DORMANT. This activation is not authorized by B1 acceptance or B2 dispatch. R2/R3 are merged conceptually into a future B3 offline package after B2 contracts stabilize; real private Futures permission remains unproved. Layer 3 remains disabled.
