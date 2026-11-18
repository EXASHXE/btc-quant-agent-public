# QUANT v0.8.0 — Project Home and Baseline (2026-11-18)

Status: Owner-directed new project baseline; Controller 0-C review pending.
Product: Personal Trading Decision Support.
Local root: /root/workspace/project/quant-0.8.0/
GitHub branch: v0.8.0 in EXASHXE/btc-quant-agent-public.

## Canonical v0.8.0 documents
- Owner decision: V080_OWNER_REBASELINE_DECISION_20261118.md
- Architecture: V080_THREE_LAYER_API_ARCHITECTURE_20261118.md
- API endpoint matrix: V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md
- Roadmap: V080_ROADMAP_AND_GATES_20261118.md
- Roles: V080_ACTIVE_ROLE_MATRIX_20261118.md
- R1 task: V080_SOL62_PERSONAL_MVP_LAYER1_PUBLIC_IMPLEMENTATION_20261118.md
- R2 draft: V080_SOL62_PERSONAL_MVP_LAYER2_USER_DATA_DRAFT_20261118.md
- R3 draft: V080_SOL62_ACCOUNT_SIGNAL_OVERLAY_R3_DRAFT_20261118.md
- 1-A new chat: V080_NEW_CHAT_1A_20261118.md
- 0-C new chat: V080_NEW_CHAT_CONTROLLER_0C_20261118.md

## What changed
v0.8.0 is a product rebaseline, not an API note appended to v0.7.0:
1. Public market data and private account data are separate layers with separate permission and storage boundaries.
2. The Owner's existing public-data statement is reused as OWNER_ATTESTED; it is not represented as an independent legal opinion or venue certification.
3. Private USER_DATA is a new optional, local-only, signed GET layer using a dedicated read-only API key.
4. TRADE_EXECUTION remains disabled and unreachable.
5. Personal operating rules are lighter than Strict Research, but candle finality, no-lookahead, TLS, freshness, rate limits, cost-aware risk and private-data protection remain mandatory.
6. The 2–12h trading decision cadence is retained: 1D / 4H / 1H / 15m / 5m.

## Source lineage and branch
The GitHub v0.8.0 branch is based on the executable v0.7.0 branch and merges the current docs/engineering documentation history. The repository branch therefore contains the code lineage plus v0.8 documentation. The local working directory is separately prepared at the exact requested path.

baseline/program-j/ is a read-only local copy of the accepted Program J source, tests, configs, contracts, tools and release locks. Exact hashes are in baseline/PROGRAM_J_BASELINE_MANIFEST_20261118.json. The source is not edited in place. New implementation must happen in a task-specific isolated workspace.

## Reusable Owner evidence
OWNER_STANDING_M2_AUTHORIZATION_20261024.md is preserved byte-identically. Its provenance remains CURRENT_USER_DIRECT_MESSAGE / OWNER_ATTESTED. It is reusable for the same personal, noncommercial, private/local, read-only public-market-data scope. Do not ask the Owner to repeat it.

This attestation does not claim Binance legal approval, third-party legal certification, or permission for a different region, commercial use, redistribution, private account access or trading. Program N's one-shot invocation remains consumed and must not be replayed.

## Current state — 2026-11-18
| Workstream | State | Notes |
|---|---|---|
| v0.8.0 baseline | Prepared | GitHub branch and local root created |
| Program J source baseline | Copied and hashed | 323 files, read-only snapshot |
| Owner standing public-data attestation | Reused | OWNER_ATTESTED; no duplicate request |
| R1 PUBLIC_MARKET | Pending 0-C review | New v0.8 task card; offline/mock implementation only |
| R2 PRIVATE_USER_DATA | Draft | Starts only after R1 independent acceptance |
| R3 account/signal overlay | Draft | Starts after R1 and R2 acceptance |
| R4 local MVP vertical slice | Planned | No dispatch |
| R5 symbol expansion / market-only alert | Planned | No dispatch |
| R6 prospective evaluation | Planned | No profitability claim |
| Layer 3 TRADE | Disabled | No task or key |

The prior v0.7.0 dispatch record for V070-SOL62-PERSONAL-MVP-LAYER1-PUBLIC-01 says worker_execution_status=NOT_STARTED and work_root_created=false. It is historical. v0.8.0 uses a new task ID and work root; no duplicate worker is assumed to exist.

## Next action
Controller 0-C independently reviews the new baseline, Program J manifest, API matrix and R1 prompt. If the scope and tests are sound, 0-C dispatches R1 to GPT-6.2 Sol. No real Binance request or credential use occurs during implementation.
