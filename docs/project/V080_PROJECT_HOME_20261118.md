# QUANT v0.8.0 — Project Home and Baseline (checkpoint updated 2026-11-23)

## Controlling 2026-11-26 update — RC1 and Owner-confirmed T3
The current accepted local source baseline is v1.0-rc1 at 2a40471; P3 closed NO_CANDIDATE_BEATS_B2_V1 (9/24 trials), P4 not run, final OOS sealed; Stage 3 scoped acceptance recorded locally. Operator upgrade pending, remote code/tag publication and hosted CI unverified, S6 unauthorized. Current product is personal trading intelligence / market structure radar; no validated trading strategy. Current research horizon ~4h–5d; frozen B2 V1 remains unchanged.
Both web ChatGPT GPT-6.2 Sol and Gemini 4 Neon remain coequal combined 1-A + Controller 0-C, mutual audit and planning, one queue, one accountable Controller, no Worker self-acceptance. Both may use T3 MCP to inspect local tasks read-only, and launch/send an exact bounded task to Codex or AGY **only after Owner explicitly confirms T3 dispatch in a prompt identifying that task/prompt and executor**. No automatic dispatch, steering, restart, recurring tasks, permission escalation or live operations. Existing Owner-direct bounded offline forwarding (2026-11-24) remains valid without extra EXECUTE. T3 capability is not authorization; a draft/card/peer report does not grant launch authority. Record actual task/thread/run status, use exact provider options, pinned local base and non-overlapping write sets; no public sensitive identifiers. Keep full English copy-button cards and Chinese Owner communication.
See the canonical current checkpoint and T3 dispatch protocol linked below. **All older status, routing and execution restrictions below are historical where inconsistent with this controlling update; historical evidence and restrictions on real operations remain intact.**

- [Current checkpoint and roadmap](V080_CURRENT_CHECKPOINT_AND_ROADMAP_20261126.md)
- [Owner-confirmed T3 remote dispatch](V080_T3_OWNER_CONFIRMED_REMOTE_DISPATCH_20261126.md)

---


## Controlling Owner role decision — 2026-11-24 09:34 +08:00

**ACTIVE Owner decision — 2026-11-24 09:34 +08:00:** **ChatGPT GPT-6.2 Sol (web)** and **Gemini 4 Neon (web)** are coequal, Owner-appointed **combined 1-A + Controller 0-C** role holders. Both independently audit code, strategy, architecture, QA and progress, plan/replan the project, challenge each other's conclusions, route local engineering and produce complete ready-to-forward next-task prompts. Neither is a permanent primary, backup, or review-only role. This supersedes the 2026-11-23 Neon-primary/Sol-review-only arrangement.

**One project queue, two collaborating Controllers:** both may independently propose tasks and scoped dispositions; reconcile the same canonical evidence and unique task IDs before starting work. For each actual dispatched package, identify one accountable 0-C (either web model) and one independent reviewer (normally the other web model); roles may rotate by task, not by model hierarchy. The accountable 0-C records one final scoped disposition after resolving material findings. Neither may overwrite a peer's receipt, manufacture a signature, launch a duplicate task or claim peer agreement not evidenced. Review disagreements remain visible; the Owner decides material unresolved priorities or scope. A missing peer response is not an automatic veto on independently authorized bounded routine OFFLINE work. Do not invent a blanket two-signature requirement or new approval layer; independent QA remains required where the established task contract requires it.

**Local executors unchanged:** local GPT-6.2 Sol is primary complex engineering, local AGY Gemini 4 Neon is peer complex engineering, Gemini 4 Hydrogen handles simple bounded work, GPT-6.2 Astra handles consequential architecture/quantitative-methodology challenges. The web role holders are distinct from local same-family Workers. Favor the other model family for independent review of a Worker package; no Worker self-acceptance and no same-family-only review as evidence of independence for consequential work. Record actual reviewer and author provenance.

**Task and authorization discipline:** both web models can prepare a complete English task prompt, regardless of who reviewed or proposed it; Owner-facing discussion remains Chinese. Each prompt is copyable in full, with exact task ID, executor, scope, tests, evidence, and truthful start mode (PROPOSAL_ONLY / OWNER_DIRECT_OFFLINE_ALLOWED / CONTROLLER_DISPATCHED). Only actual valid dispatch or explicit Owner-direct offline execution starts a Worker. No duplicate dispatch prerequisite for the latter. Startup is read-only, no auto-dispatch; roles do not grant live Binance/Feishu/provider, private USER_DATA, TRADE, privileged operations, or retrospective signing authority. Historical receipts and prior authorship remain unchanged.

**Historical audit checkpoint (2026-11-23; recheck current originals):** Local Neon full-system audit V080-NEON-FULL-SYSTEM-AUDIT-AND-REFACTOR-BLUEPRINT-20261123 was WORKER_REPORTED / READY_FOR_OWNER_AND_INDEPENDENT_ARCHITECTURE_REVIEW; 14 report seals were checked and 12 work packages were ADVISORY_PROPOSAL_NOT_DISPATCHED. Disputed vendor contracts, post6/post7 readiness and risk-cap changes need independent evidence. Role changes do not adopt or dispatch that blueprint.

**Canonical active bootstraps:** [ChatGPT GPT-6.2 Sol — combined 1-A/0-C](../prompts/v0.8/V080_NEW_CHAT_CHATGPT_GPT6_SOL_INDEPENDENT_REVIEW_20261123.md) · [Gemini 4 Neon — combined 1-A/0-C](../prompts/v0.8/V080_GEMINI_NEON_WEB_FUSED_1A_0C_20261123.md). [Sol role definition](../roles/V080_CHATGPT_GPT6_SOL_INDEPENDENT_REVIEWER_20261123.md) · [Shared role matrix](../roles/V080_ACTIVE_ROLE_MATRIX_20261118.md). Existing filenames are retained for link compatibility; legacy standalone 1-A and 0-C entrypoints are not additional roles.




## Source code publication — 2026-11-23

The executable-source branch v0.8.0 now contains a reviewable, source-only
export (commit c35445acfb07e9a8fbcccb51f2a6c860d6af40dc):

- [12 Controller-scoped OFFLINE accepted source snapshots](https://github.com/EXASHXE/btc-quant-agent-public/tree/v0.8.0/packages/v080/offline-scoped) — source, test/tool files, per-file SHA256 manifest and local Controller receipt references.
- [S3 post4 Worker-ready review candidate](https://github.com/EXASHXE/btc-quant-agent-public/tree/v0.8.0/packages/v080/review-candidates/s3-post4) — not independently accepted at source-export time. Its 337 tests/14 default-deny cases were **worker-reported**, not Controller accepted.

**This is a documentation/discovery pointer, not a new runtime build, test acceptance, provider scope or live authorization.** Original sealed workroots, actual Controller JSON, private evidence, production credentials, account data and raw QA logs remain local and were not published. The previously recorded Controller test/code HEAD values refer to their original acceptance baselines; this new export-only commit does not retroactively rewrite those receipts.



## Controlling verified checkpoint — 2026-11-23 02:27 +08:00

**[Full original evidence and next gates](V080_PROGRESS_AND_NEXT_GATES_20261123.md).** P0A default-disabled S2 release-bound transport candidate accepted **OFFLINE** (40 source seals; 61 fresh transport + 55 parent tests), and P0B Owner-local KR/WSL2 evidence accepted **OFFLINE** (19 seals, but venue/egress/headroom/clock trust remain unresolved). Joint Controller receipt confirms both scopes, with real gates held. **Neon S3 zero-retry OFFLINE was formally dispatched at 02:27** to AGY Gemini 4 Neon XHigh; verify actual worker status before claiming acceptance. Real S2/S3 Binance, S4 Feishu, S5 human-use and S6 cadence are not authorized/observed; Layer2 real account and TRADE still disabled.

Use [original canonical 1-A](../prompts/v0.8/V080_NEW_CHAT_1A_20261118.md) and [0-C](../prompts/v0.8/V080_NEW_CHAT_CONTROLLER_0C_20261118.md) new chats, both revised in place; the 2026-11-23 duplicate is retired. **Owner Chinese, agent prompts English, full functional copy-card**, per [standard](V080_PROMPT_COPY_CARD_STANDARD_20261118.md). Older dated sections below remain historical.

**HISTORICAL VERIFIED LOCAL CONTROLLER CHECKPOINT — 2026-11-22 22:23 +08:00 (1-A documentation sync 2026-11-23):** Sol S2 V2 one-run Canary derivative **SCOPED_ACCEPTED_OFFLINE_ONLY** (55 independent PASS, 39/39 sealed; physical production transport absent); Neon optional account-risk CLI **SCOPED_ACCEPTED_OFFLINE_ONLY** (12 PASS, 36/36 sealed, account overlay disabled); Astra S3 admission **SCOPED_ACCEPTED_DOCUMENTARY_RESEARCH_ONLY** (9/9 sealed, fundingRate general-IP debit `d` still UNKNOWN); consolidated 0-C review accepted all three limited scopes. Controller's 22:23 next-stage file is **PLANNING ONLY / new_dispatch_issued=false**. Also accepted: optional Feishu Mode0 Core local CLI / Mode1 Hermes local six reads OFFLINE; Mode2 genuine Feishu disabled. **No real S2 GET, S3 scan, S4 live send, S5 human loop or S6 recurrence authorized/observed.**

**Read the [2026-11-23 evidence and revised next-gates note](V080_PROGRESS_AND_NEXT_GATES_20261123.md) first**, then inspect actual newer Controller decisions. The previously dated 2026-11-21 19:58 H4 checkpoint below remains historical; do not re-open completed offline work. Current next path: Sol default-disabled S2 physical transport offline package **parallel with** minimal Owner/Neon KR-WSL2 evidence and light Owner Feishu prerequisites; independently accept before **separate** genuine S2 one-run approval/2 GET; only then prioritize S3 genuine decisions while preparing pinned S3 zero-retry offline conditionally. Freeze optional risk CLI rather than expanding it now. All Owner-facing task/new-chat prompts require a **complete copyable card with working Copy control when supported**, per the [Prompt Copy Card Standard](V080_PROMPT_COPY_CARD_STANDARD_20261118.md).

- [Canonical Controller 0-C new chat — revised in place 2026-11-23](../prompts/v0.8/V080_NEW_CHAT_CONTROLLER_0C_20261118.md) (Owner-prepared; **not** dispatched).


**HISTORICAL VERIFIED 2026-11-21 19:58 HKT — H4 accepted OFFLINE ONLY:** Controller 0-C independently accepted V080-SOL62-H4-S2S5-CONSOLIDATED-READINESS-01 in controller-decisions/V080_CONTROLLER_H4_S2S5_CONSOLIDATED_OFFLINE_SCOPED_ACCEPTANCE_20261121.json. Status SCOPED_ACCEPTED_H4_S2S5_OFFLINE_INTEGRATION_READINESS_ONLY; **336/336 independent PASS, 103/103 sealed, Python/Node seven goldens each PASS**, two reproducible candidate wheels. S2 real Binance 2 GET is still BLOCKED_PRODUCTION_AND_INPUT_NOT_AUTHORIZED; S3 full scan FUNDING_WEIGHT_UNRESOLVED, S4 Feishu live client/identity/callback BLOCKED, S5 first actual Hermes/QUANT human loop NOT OBSERVED, S6 recurrence NOT AUTHORIZED. Pi P2 OWNER_DEFERRED and QI1/QL1/QB1/QR1 NOT_DISPATCHED. H4 independent acceptance explicitly states new_worker_dispatch_issued=false.

**LATEST OWNER OPERATING RULE:** [Explicit Owner direct OFFLINE task execution](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md). For a named complete offline task explicitly forwarded with EXECUTE, Sol/Neon may start in an isolated workroot even without a second 0-C dispatch JSON, record OWNER_DIRECT_OFFLINE_STARTED and submit one independently reviewable handoff. This grants NO live/privileged rights; Controller remains sole acceptance authority. Historical status lines below are snapshots, not current dispatch gates.

Status: R1/B1 SCOPED_ACCEPTED_OFFLINE_ONLY; B2 SCOPED_ACCEPTED_OFFLINE_INTEGRATED_ONLY; B3 SCOPED_ACCEPTED_OFFLINE_ACCOUNT_AWARE_ONLY; B4 SCOPED_ACCEPTED_OFFLINE_PUBLIC_BRIDGE_ONLY; B5 Phase A SCOPED_ACCEPTED_OFFLINE_PHYSICAL_BINDING_READY. P1 Pi architecture SCOPED_ACCEPTED_ARCHITECTURE_ONLY; H1 Hermes engineering independently reran 54/54 PASS but is HOLD_P0_CONTRACT_SEMANTICS_AND_GOLDEN_EXPORT; corrected H1 P0 reference SCOPED_ACCEPTED_OFFLINE_HERMES_H1_REFERENCE_WITH_P0_FIXED_ONLY (63 independent PASS); P2 remains OWNER_DEFERRED_UNTIL_H_FIELD_TRIAL / NOT_DISPATCHED regardless of draft readiness. B5 Phase B genuine scan, real Feishu, private data and trading remain NOT AUTHORIZED.
**Controlling 2026-11-21 checkpoint:** H2-A, H2-B, H3 Phase A and H3-B Gate A independently accepted **OFFLINE ONLY**. Controller A1 Binance local derivative candidate has WORKER_REPORTED_READY_FOR_CONTROLLER_REVIEW_OFFLINE_CANDIDATE (237 worker PASS, independent acceptance pending at 17:10). Genuine Binance S2/S3 and Feishu S4 remain NOT_AUTHORIZED; S5/S6 actual human-use not started. **Future domain priority after H S5 is QI1 + QL1, then QB1 + QR1; QN1/QM1 deferred.** Pi P2 remains Owner-deferred. The older 2026-11-20 status line above is a historical baseline, not a current real-activation verdict.

Product: Personal Trading Decision Support → Trading Intelligence Platform roadmap.
Local root: /root/workspace/project/quant-0.8.0/
Executable code/runtime branch: v0.8.0 in EXASHXE/btc-quant-agent-public.
Canonical project documentation branch: docs/engineering. All project, role, architecture, roadmap, task-card, handoff and new-chat documentation is maintained there; same-path documentation copies on v0.8.0 are non-authoritative.

## Canonical v0.8.0 documents — all maintained on docs/engineering

- [Owner decision](V080_OWNER_REBASELINE_DECISION_20261118.md)
- [Three-layer API architecture](../architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md)
- [Binance API endpoint matrix](../architecture/V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md)
- [Roadmap and gates](V080_ROADMAP_AND_GATES_20261118.md)
- [**Current Trading Intelligence platform/product roadmap**](V080_TRADING_INTELLIGENCE_PLATFORM_ROADMAP_20261121.md)
- [**Controller 0-C latest evidence and dependency sync — 2026-11-21**](V080_CONTROLLER_TRADING_INTELLIGENCE_ROADMAP_SYNC_20261121.md)
- [Owner→0-C future roadmap sync prompt](../prompts/v0.8/V080_OWNER_0C_TRADING_INTELLIGENCE_ROADMAP_SYNC_20261121.md)
- [Owner model-routing policy](V080_MODEL_ROUTING_POLICY_20261119.md)
- [**Owner direct offline engineering start protocol**](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md)
- [**Worker new-chat bootstrap — Sol / Neon**](../prompts/v0.8/V080_NEW_CHAT_OFFLINE_ENGINEERING_WORKER_20261121.md)
- [**Owner → 0-C H4 progress and dispatch-friction sync prompt**](../prompts/v0.8/V080_OWNER_0C_H4_PROGRESS_OFFLINE_START_SYNC_20261121.md)
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
- [B5 genuine public source + first bounded scan — Phase A accepted offline, Phase B unauthorized](../prompts/v0.8/V080_LIVE_PUBLIC_FIRST_BOUNDED_SCAN_B5_20261120.md)
- [**ACTIVE Owner sequence — Hermes operational first, Pi engineering during field trial**](V080_HERMES_H_FIRST_PI_FIELD_TRIAL_SEQUENCE_20261120.md)
- [Hermes-first + Pi-parallel historical workplan](V080_HERMES_FIRST_PI_PARALLEL_PLAN_20261120.md)
- [Controller-frozen Quant-Agent Contract V1](../architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md)
- [H1 — Hermes + QUANT + Feishu offline original (delivered; P0 HOLD)](../prompts/v0.8/V080_HERMES_QUANT_FEISHU_H1_20261120.md)
- [Controller P0 interoperability dispositions](../architecture/V080_QUANT_AGENT_V1_P0_CONTROLLER_DISPOSITIONS_20261120.md)
- [Controller 7 Python/TS canonical goldens](../architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json)
- [H1 consolidated P0 correction — historically dispatched, corrected reference accepted OFFLINE only](../prompts/v0.8/V080_HERMES_H1_P0_INTEROP_REMEDIATION_20261120.md)
- [P1 — Pi Quant-Agent architecture ADR (Controller accepted ARCHITECTURE_ONLY)](../prompts/v0.8/V080_ASTRA_PI_QUANT_AGENT_ARCHITECTURE_P1_20261120.md)
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

## H4 consolidated offline acceptance and immediate S2 target — 2026-11-21 19:58

| Scope | 0-C outcome | Real-operation boundary |
|---|---|---|
| H4-A / S2 | Accepted OFFLINE post3 two-mock-GET canary; separate rollback witness | Real S2 unauthorized; Owner-local venue eligibility/egress, UID, CA, protected dual-store witness and exact release/signature missing |
| H4-B / S3 | Accepted OFFLINE 39-request plan with known debits plus unresolved fundingRate history weights | Genuine BTC/ETH/SOL full market scan not authorized; fundingRate general IP weight UNKNOWN |
| H4-C / S4 | Accepted OFFLINE Feishu quota/one-sender/unknown-delivery patches | Actual app/tenant/private recipient/client identity and inbound binding not approved |
| H4-D / S5 | Accepted OFFLINE H3+Hermes+Feishu mock integration | No true Feishu/network/human baseline; production 2s cold start unverified |
| S6 continuing operations | NOT AUTHORIZED | One-shot success is not recurring permission |

The first nonprivileged operational work after H4 is **Owner-local S2 A1 readiness**. A later Neon task card named V080-NEON-S2-A1-OWNER-LOCAL-READINESS-01 may be run OFFLINE only if the Owner explicitly forwards it to Neon and directs EXECUTE under the new [offline protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md), or an actual 0-C dispatch is present. The H4 acceptance itself created no new worker dispatch; do not fabricate a receipt or duplicate H4.

## Latest accepted offline expansion / A1 worker handoff — 2026-11-21

| Area | Independently evidenced scope | What remains |
|---|---|---|
| H2-A B5 public activation readiness | SCOPED_ACCEPTED_OFFLINE_H2A_ACTIVATION_READINESS_ONLY | Real Binance release/Canary not activated |
| H2-B Hermes/Feishu readiness | SCOPED_ACCEPTED_OFFLINE_H2B_FEISHU_READINESS_ONLY | Real Feishu app/client, recipient, send/receive not activated |
| H3 Phase A integration | SCOPED_ACCEPTED_H3_PHASE_A_OFFLINE_ONLY | No end-to-end real-market/Feishu run |
| H3-B Gate A | SCOPED_ACCEPTED_H3B_OFFLINE_GATE_A_PREPARATION_ONLY | Owner-local environment, eligibility and future production authorization still blocked |
| **Controller A1 Binance derivative** | **WORKER_REPORTED_READY_FOR_CONTROLLER_REVIEW_OFFLINE_CANDIDATE** | Dispatched 16:52; worker 237 PASS / sealed evidence at 17:10; independently review; NOT live authorized |
| **H S5/S6** | NOT_STARTED | First separately authorized real human loop and ongoing feedback |
| **QI1/QL1 → QB1 → QR1** | PLANNED / NOT_DISPATCHED | Formal business engineering after initial real H baseline; QN1/QM1 deferred |
| **Pi P2** | OWNER_DEFERRED / NOT_DISPATCHED | H actual-use first; no dual-sender |

The original 2026-11-20 table below is retained to preserve the earlier accepted-stage record. For real actions consult the newest Controller receipts and [current stage gates](V080_ROADMAP_AND_GATES_20261118.md). A worker package labeled READY_FOR_CONTROLLER_REVIEW is not accepted, and an offline acceptance does not authorize real network traffic.

## Current state — 2026-11-20

**WORKER HANDOFF (2026-11-23 ~02:52; not Controller acceptance):** Neon S3 isolated workroot has CONTROLLER_HANDOFF.md with READY_FOR_CONTROLLER_REVIEW_S3_ZERO_RETRY_OFFLINE; the worker reports 337/337 test invocations, 14/14 default-deny probes and a byte-reproducible post4 wheel. No later 0-C S3 acceptance was present in the inspected Controller directory. Treat all 337 PASS as WORKER_REPORTED until independent 0-C QA/review; do not redispatch the S3 implementation.

| Workstream | Controller-reconciled state | Notes |
|---|---|---|
| Baseline / Program J | VERIFIED | 323 preserved files, source/code baseline pinned |
| R1 PUBLIC_MARKET | **SCOPED_ACCEPTED_OFFLINE_ONLY** | 0-C independently reran 99 targeted and 694 full tests; 367 sealed outputs |
| Astra full-system review | **SCOPED_ACCEPTED_ARCHITECTURE_REVIEW_ONLY** | Evidence-based architecture recommendations; not implementation authorization |
| Narrow Stage 1A | **SUPERSEDED_FOR_FUTURE_FORWARDING / NOT_STARTED** | Original decision preserved; no overlapping workspace found |
| **B1 PUBLIC_RUNTIME_FOUNDATION** | **SCOPED_ACCEPTED_OFFLINE_ONLY** | 89 B1 + 99 inherited targeted tests independently PASS; genuine-public origin remains dormant |
| **B4 PUBLIC_SOURCE_BRIDGE** | **SCOPED_ACCEPTED_OFFLINE_PUBLIC_BRIDGE_ONLY** | gpt-6.2-sol xhigh; Controller independent B4/B1/B2 28/89/54 tests PASS; 50 sealed files; real physical origin still absent |
| **B5 GENUINE_PUBLIC_SOURCE + FIRST BOUNDED SCAN** | **SCOPED_ACCEPTED_OFFLINE_PHYSICAL_BINDING_READY** | Sol xhigh delivered, 0-C reran B5/B1/B2/B4 27/89/54/28 PASS, 58 files sealed; genuine Phase B NOT AUTHORIZED |
| **H1 HERMES_QUANT_FEISHU** | **HOLD_P0_CONTRACT_SEMANTICS_AND_GOLDEN_EXPORT** | Gemini 4 Neon XHigh delivered; independently reproduced clean17+mixed17+Hermes20 PASS and 57 files sealed, but NO_SETUP/no-episode, pre-evidence ERROR and cross-language fixture P0 blocked final contract acceptance |
| **H1 P0 CORRECTION** | **SCOPED_ACCEPTED_OFFLINE_HERMES_H1_REFERENCE_WITH_P0_FIXED_ONLY** | 0-C accepted post1 package at 18:25 HKT; 71/71 seals, 20 clean + 20 mixed + 23 Hermes PASS, 7 cross-language golden vectors, P0-C01/C02/C03 closed offline; no real Feishu/Binance/LLM authority |
| **P2 PI OFFLINE PROTOTYPE** | **OWNER_DEFERRED_UNTIL_H_FIELD_TRIAL / NOT_DISPATCHED** | H1 corrected reference input is accepted; a Controller-authored READY_FOR_OWNER_FORWARDING draft was briefly observed locally, but latest Owner sequence defers actual P2 engineering until authorized Hermes real-use baseline; Pi uses offline shadow |
| **P1 PI_QUANT_AGENT_ARCH_ADR** | **SCOPED_ACCEPTED_ARCHITECTURE_ONLY** | Astra assigned/reported; seven sealed docs checked; upstream Pi v1.5.2 commit & three package manifests independently verified; no Pi runtime; P2 remains separately blocked |
| OpenClaw | DEFERRED | No active worker or three-way framework re-evaluation |
| First live public GET activation | **NOT AUTHORIZED** | Requires accepted B1 and separate completed local operating scope |
| **B2 MARKET_DECISION_MVP** | **SCOPED_ACCEPTED_OFFLINE_INTEGRATED_ONLY** | Sol Extra High; Controller independently reran 54/54 B2 + 89/89 B1 tests, installed both wheels and recalculated 24 paths; genuine market integration remains dormant |
| **B3 ACCOUNT_AWARE_DECISION_SUPPORT** | **SCOPED_ACCEPTED_OFFLINE_ACCOUNT_AWARE_ONLY** | Gemini 4 Neon XHigh; 51 B3 + 54 inherited B2 independent PASS; 183/183 sealed files, 17 synthetic scenarios, no live credentials/API |
| R5 controlled expansion/notifications | PLANNED | Hermes H1 is offline notification/interaction integration only; actual Feishu and recurring data cadence separately gated |
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
- **B5 Phase A forward approval (historical):** controller-decisions/V080_CONTROLLER_B5_LIVE_PUBLIC_TWO_PHASE_FORWARD_APPROVAL_20261120.json. Sol has delivered B5 Phase A; Controller independently accepted offline physical-binding-ready scope. Phase B remains NOT_AUTHORIZED.
- **B5 Phase A independent acceptance:** controller-decisions/V080_CONTROLLER_B5_PHASE_A_OFFLINE_ACCEPTANCE_20261120.json. B5 27 + B1 89 + B2 54 + B4 28 tests independently PASS, B5 58/58 files sealed, cold/mixed installation, eight rejected live gates; no genuine exchange request.
- **Hermes/Pi Owner direction:** V080-OWNER-0C-HERMES-FIRST-PI-PARALLEL-PLAN-20261120; H1/P1 tasks and frozen V1 contract prepared in docs/engineering. No worker dispatched automatically.
- **H1/P1 historical forwarding approval:** controller-decisions/V080_CONTROLLER_HERMES_H1_PI_P1_PARALLEL_FORWARD_APPROVAL_20261120.json, SHA-256 626a0af67b7264da7d203181cb06d48542681fecb8be9cdebb6f2f7645f09dac. The READY_FOR_OWNER_FORWARDING / NOT_DISPATCHED state applied at the original approval time only: both were subsequently Owner-forwarded and delivered; P1 architecture was accepted, H1 entered P0 HOLD. Real Feishu/market actions remain NOT AUTHORIZED.
- **P1 independent scoped architecture acceptance:** controller-decisions/V080_CONTROLLER_P1_PI_ARCHITECTURE_ACCEPTANCE_20261120.json, SHA-256 c367c8c6188fb6ec51cdc316e4260b2f35486d82781e7eee6c72fcc6e1ba4999. P1 seven files sealed; Pi pinned source and package manifests confirmed; no SDK execution or P2 authorization.
- **H1 independent P0 hold:** controller-decisions/V080_CONTROLLER_H1_INDEPENDENT_P0_HOLD_20261120.json, SHA-256 3293b8d04468ab408a21ba7b284621f32023b81a3f0accf08b655473679093fe. H1 57 sealed files and 54 independent tests PASS but two actual V1 semantic defects plus missing cross-language goldens block acceptance; [P0 findings](../architecture/V080_QUANT_AGENT_V1_P0_CONTROLLER_DISPOSITIONS_20261120.md) and [correction prompt](../prompts/v0.8/V080_HERMES_H1_P0_INTEROP_REMEDIATION_20261120.md).
- **B5 Phase A acceptance hash:** controller-decisions/V080_CONTROLLER_B5_PHASE_A_OFFLINE_ACCEPTANCE_20261120.json, SHA-256 1af049c8b5f2be6570d837dd37055a987e3749e9ef0d9c94dfdccfa5ccbd320f.
- **B4 offline scoped acceptance:** controller-decisions/V080_CONTROLLER_B4_PUBLIC_SOURCE_BRIDGE_OFFLINE_SCOPED_ACCEPTANCE_20261120.json, SHA-256 095dc79a730b843257947f6d77760a741efb67a6973880c4f9a806ef9ec86b58. Independently reran 28 B4 + 89 B1 + 54 B2, checked 50/50 B4 seals, rebuilt wheel, 16 cards/8 reprices and recalculated 36 Decimal conditional paths; genuine-public entry exits code 3. No authentic live market data or trading capability authorized.
- **B3 offline account-aware acceptance:** controller-decisions/V080_CONTROLLER_B3_ACCOUNT_AWARE_OFFLINE_SCOPED_ACCEPTANCE_20261120.json, SHA-256 0d3b88ea3bcedeab9f8d18d8118929be4610ecfa433d2bd35cd6fc7f96b8d7a0. Controller independently verified 183/183 B3 sealed files, 51/51 B3 and 54/54 inherited B2 offline tests, 17 synthetic scenarios and exact 183-file byte identity with pre-seal evidence. Prior HOLD_SEAL_MISSING closed. Real private/public access remains disabled.
- **B2 offline-integrated acceptance:** controller-decisions/V080_CONTROLLER_B2_MARKET_DECISION_OFFLINE_INTEGRATED_ACCEPTANCE_20261119.json, SHA-256 7de93eed45541d09a3b65b3e8452033c894ad402a169306bd97e4952929ac48d. Controller reran 54 B2 and 89 B1 tests, verified 93 B2, 56 B1, 367 R1 and 323 Program J hashes, checked clean install and recomputed 24 Decimal conditional paths. The first isolated review-copy test attempt needed an explicit B1 DB path; its rerun passed 54/54. Account context and real-source eligibility remain unavailable.

## Next action

**Controlling Owner sequence:** [Complete Hermes H first; develop Pi during authorized H field trial](V080_HERMES_H_FIRST_PI_FIELD_TRIAL_SEQUENCE_20261120.md). H1 P0 correction worker has now reported READY_FOR_CONTROLLER_REVIEW in workspaces/lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01/; corrected golden exports and a sealed manifest were observed at 18:06 HKT (manifest SHA256 `90ff56de9175191e771b3de613aedf19267213ee842bec6f87b84817038268d4`). This is not 0-C acceptance. First reconcile Owner forwarding and independently review P0-C01/C02/C03. **Do not launch a duplicate worker.** Then seek separate real B5 public-market and Feishu private-DM activation gates, and begin authorized actual-use telemetry. **Pi P2 remains NOT_DISPATCHED even after H1 offline acceptance, until Hermes field testing has actually started and supplied first operational feedback.** Hermes remains sole sending authority; no real or private/trading permission follows from docs.

B2 has been independently accepted for offline synthetic decision integration. It is no longer awaiting Controller review, and no duplicate B2 worker is needed. For the first genuine public-market decision workflow, separately review the Owner-controlled operating scope AND the B1/B2 genuine-origin binding and activation change; existing B1 and B2 wheels deliberately refuse genuine-public operation.

B3 remains **SCOPED_ACCEPTED_OFFLINE_ACCOUNT_AWARE_ONLY** and fully separate from B4. Private Futures USER_DATA permission feasibility remains unproved. The public-data first scan is the immediate product-utility dependency, but even after B4 acceptance it requires a reviewed physical host binding, completed Owner region/route and retention scope, official rate-weight validation, and a new activation decision. Layer 3 remains disabled.

## Owner model-routing update — 2026-11-19

Gemini Neon is an Owner-designated peer-level model to GPT-6.2 Sol for complex engineering. For B3, the Owner selected Neon and the package was delivered under the Gemini 4 Neon XHigh worker label. Sol Extra High was the unused fallback. For other tasks, use the model-routing policy and Controller-approved non-overlapping work scopes. Hydrogen remains for simple bounded work; Astra remains the architecture advisor. Historical Gemini Argon records are not rewritten.
