# QUANT v0.8.0 — Active Agent Instructions

## Current baseline
The active product baseline is v0.8.0. Read first:
1. docs/project/V080_PROJECT_HOME_20261118.md
2. docs/project/V080_OWNER_REBASELINE_DECISION_20261118.md
3. docs/architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md
4. docs/architecture/V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md
5. docs/project/V080_ROADMAP_AND_GATES_20261118.md
6. docs/roles/V080_ACTIVE_ROLE_MATRIX_20261118.md

Local working root: /root/workspace/project/quant-0.8.0/.

## Authority and role separation
- Owner controls product direction and local credential configuration.
- Controller 0-C is the sole engineering queue owner, dispatcher and independent acceptance authority.
- GPT-6.2 Astra performs complex architecture/strategy analysis and independent challenge; it does not dispatch or accept.
- GPT-6.2 Sol is the primary engineering executor. Sol Max is the high-intensity lane for cross-module work, not a separate controller.
- Gemini 4 Hydrogen handles simple bounded engineering, fixtures, documentation and mechanical QA.
- ChatGPT 1-A is an independent Owner-facing advisor, not Controller 0-C.
- No Orchestrator role. A worker never accepts its own work.

## Personal three-layer API boundary
- Layer 1 PUBLIC_MARKET: public GET only, no personal account key.
- Layer 2 PRIVATE_USER_DATA: separate local read-only key, signed GET allowlist only. No credential is shared with a worker or chat.
- Layer 3 TRADE_EXECUTION: disabled and unreachable. Do not implement order placement, cancellation, modification, leverage, margin, transfer or withdrawal.
- Do not use POST/PUT/DELETE for private user-data stream lifecycle in the current GET-only Layer 2.
- If the current Binance key UI requires a Futures permission whose TRADE implications are not proven read-only, stop. Do not widen permissions to make an endpoint pass.

## Existing Owner attestation
OWNER_STANDING_M2_AUTHORIZATION_20261024.md is reusable as OWNER_ATTESTED for the same personal, noncommercial, private/local, read-only public-market-data research scope. Do not repeatedly ask for the same statement or fabricate third-party legal certification. This does not authorize region/proxy circumvention, commercial redistribution, private-account access, trading or withdrawals.

## Data and research invariants
- Personal data is labeled PERSONAL_PUBLIC_MARKET or PERSONAL_PRIVATE_ACCOUNT.
- Strict Research, protected history and holdout rules remain unchanged. Personal data is never silently promoted into Strict Source/E1, Strict Shadow or economic validation.
- Never use forming candles as completed setup/trigger evidence. No lookahead. Preserve gaps, revisions, freshness and provenance.
- No synthetic fallback in live mode.
- TLS verification, rate-limit accounting, bounded retries, hard stop/position risk, fees, funding, spread and slippage remain mandatory.
- Private account data remains local by default and is excluded from controller evidence bundles and Feishu.
- A market-side EXECUTABLE state is advisory only; account-context availability is a separate dimension.

## Task execution
All new local implementation tasks, worktrees, evidence and handoffs belong under /root/workspace/project/quant-0.8.0/. Treat baseline/program-j/ as read-only. New code goes in a task-specific isolated workspace under workspaces/. Never modify accepted Program J/v0.7.0 source in place.

A task prompt is not a Controller dispatch. The R1 prompt is pending Controller 0-C review; do not start it until 0-C verifies the baseline and issues the dispatch. R2 remains draft until R1 scoped acceptance.

## Prompt integrity
Every worker/new-chat prompt must be complete, bounded, and include exact baseline, allowed/prohibited paths, offline/mock constraints, test matrix, stop conditions, deliverables and reviewer. Do not use an excerpt as a substitute for the full task card.
