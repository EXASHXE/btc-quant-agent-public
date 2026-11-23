# QUANT v0.8.0 — Active Role Matrix (Owner role handoff 2026-11-23 21:20 +08:00)


## Current routing checkpoint — 2026-11-23 02:27 +08:00

**WORKER HANDOFF (2026-11-23 ~02:52; not Controller acceptance):** Neon S3 isolated workroot has CONTROLLER_HANDOFF.md with READY_FOR_CONTROLLER_REVIEW_S3_ZERO_RETRY_OFFLINE; the worker reports 337/337 test invocations, 14/14 default-deny probes and a byte-reproducible post4 wheel. No later 0-C S3 acceptance was present in the inspected Controller directory. Treat all 337 PASS as WORKER_REPORTED until independent 0-C QA/review; do not redispatch the S3 implementation.

P0A S2 transport and P0B KR/WSL2 evidence accepted in their **OFFLINE** scopes. **AGY Neon XHigh is the actively dispatched S3 zero-retry offline executor** (Controller decision `V080_CONTROLLER_NEON_S3_ZERO_RETRY_OFFLINE_ENGINEERING_DISPATCH_20261123.json`). Do not reassign to Sol without a new legitimate decision. **Owner has now appointed the separate Gemini 4 Neon WEB CHAT as the fused 1-A/0-C Controller; local AGY Neon stays a Worker. ChatGPT GPT-6 Sol is its independent second reviewer. No worker self-acceptance.** See [verified progress](../project/V080_PROGRESS_AND_NEXT_GATES_20261123.md).

**Mandatory prompt format:** Owner discussion Chinese; every *agent-facing* prompt (including new chats) **English** by default, one functional complete-copy card per prompt, not a summary/link/fake button. No role recommendation grants real provider access.


| Role | Responsibility | Boundary |
|---|---|---|
| Owner | Product and permission authority; may directly START a specifically identified, bounded OFFLINE engineering task by explicitly forwarding it to a worker; separate live/privileged approvals remain mandatory | Do not infer authorization from a draft file or a previous chat; no secrets or automatic trading permission |
| **Gemini 4 Neon WEB CHAT — 1-A + Controller 0-C** | **Active, sole project advisory + Controller queue owner:** product/quant analysis, roadmap, complete worker prompts, task routing, actual Controller dispatch and final scoped evidence acceptance | One queue; obtain independent evidence and ChatGPT Sol challenge; especially no sole acceptance of local Neon-authored work. No automatic live or trade authority |
| **[ChatGPT GPT-6 Sol — Independent Reviewer](V080_CHATGPT_GPT6_SOL_INDEPENDENT_REVIEWER_20261123.md)** | Second-party code, architectural, defect and acceptance challenge of web Neon decisions; independent QA when available | Review-only; separate from local Sol Worker; no queue ownership, dispatch, implementation, self-acceptance or live grants |
| GPT-6.2 Astra | Chief architecture and strategy role; cross-module design, critical technical decisions, threat models and independent challenge of Sol's design | Advises/reviews; does not dispatch, implement by default or self-accept |
| Local GPT-6.2 Sol | Primary engineering executor: public/private API adapters, data engine, strategy implementation, integration and difficult bug fixes | Implements scoped task in isolated workspace; no live calls/credentials during offline task; no self-acceptance |
| Local GPT-6.2 Sol Max | High-intensity implementation lane within the Sol engineering role for cross-module or unusually complex changes | Not a separate queue or controller; same Sol scope and acceptance boundaries |
| Local AGY Gemini Neon | Peer-level alternative complex engineering executor to GPT-6.2 Sol; used when Sol quota/capacity is insufficient or for approved independent parallel packages | Same engineering/evidence/acceptance bar as Sol; isolated worktree and non-overlapping write set; not architecture authority or self-acceptance |
| Gemini 4 Hydrogen | Simple engineering, docs, fixtures, mechanical tests, routine lint/format and QA | Simple bounded work only; not a substitute for Sol/Neon on complex work; does not accept its own work |
| Controller 0-C (role, held by WEB Gemini 4 Neon) | Sole queue/reconciliation, formal dispatch and final scoped disposition after independent QA | Same active web Neon chat as 1-A, not a separate person/model; no self-review of local Neon work; historical Controller receipts unchanged |
| 1-A (function, held by WEB Gemini 4 Neon) | Product, architecture, quantitative strategy and engineering-efficiency review | Same web Neon Controller chat, not a separate ChatGPT adviser queue; advisory finding is not a dispatch by itself |
| Layer 1 | Public market data client | No personal account key |
| Layer 2 | Private signed USER_DATA GET client | Dedicated local read-only key; no non-GET route |
| Layer 3 | Trade execution | Disabled; no key/client/routes |

## Default routing

- Consequential architecture fork → GPT-6.2 Astra.
- Core API/data/strategy/integration implementation → GPT-6.2 Sol by default.
- Complex engineering when Sol quota/capacity is insufficient → Gemini Neon at the same project complexity tier.
- Genuinely independent parallel engineering → Sol + Gemini Neon only with Controller-approved disjoint worktrees/write sets and one integration owner.
- Cross-module high-intensity work when Sol is selected → GPT-6.2 Sol Max lane, still under Sol ownership.
- Small deterministic fixtures/docs/mechanical QA → Gemini 4 Hydrogen.
- Dispatch, queue control and final scoped acceptance → **Gemini 4 Neon WEB CHAT acting as Controller 0-C**, after independent technical review.
- Independent Owner-facing advice → **same Gemini 4 Neon WEB CHAT in the 1-A function**.
- Independent technical/audit review of that fused Controller → **ChatGPT GPT-6 Sol** (not local Sol executor). Start with [reviewer role](V080_CHATGPT_GPT6_SOL_INDEPENDENT_REVIEWER_20261123.md) and [complete English new-chat bootstrap](../prompts/v0.8/V080_NEW_CHAT_CHATGPT_GPT6_SOL_INDEPENDENT_REVIEW_20261123.md).

**Future QI1/QL1/QB1/QR1 routing (NOT_DISPATCHED):** Astra reviews the shared QI1 annotation and QL1 multi-axis event-schema fork and QB1/QR1 quantitative methodology; Sol is the preferred QL1 Core/event-store and H integration owner; Neon or Sol is suitable for the non-overlapping QI1 adapter; Hydrogen can own narrow deterministic fixtures. QB1/QR1 implementation needs separate scope and independent evaluation. See [Controller Trading Intelligence roadmap sync](../project/V080_CONTROLLER_TRADING_INTELLIGENCE_ROADMAP_SYNC_20261121.md). New roles and gates are **not** activated by this future allocation.

**Owner-direct offline execution exception (effective 2026-11-21):** See [controlling offline task start protocol](../project/V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md). When Owner expressly forwards a complete bounded OFFLINE task and tells Sol/Neon/Hydrogen to EXECUTE it, the worker starts in its isolated root despite an absent Controller dispatch receipt. Worker records OWNER_DIRECT_OFFLINE_STARTED (never pretends Controller signed a dispatch); Controller later independently accepts or holds. A draft or card merely present in repo does not authorize work. True live/privileged operations still require exact separate grants.

No Orchestrator role. One primary writer per work package. Sol and Neon may work in parallel only on explicitly non-overlapping packages with frozen interfaces and an identified integration owner. Worker PASS ≠ independent review PASS ≠ Controller acceptance. A **prompt file alone** is not authorization; an **explicit Owner execution instruction** is sufficient solely for bounded offline engineering.

## Documentation authority and prompt presentation

The canonical documentation branch is GitHub docs/engineering. The v0.8.0 branch is the executable code/runtime baseline, not a second writable documentation authority.

All Owner-facing prompts generated by 1-A, 0-C or another prompt-authoring role must follow:

docs/project/V080_PROMPT_COPY_CARD_STANDARD_20261118.md

Every distinct complete prompt must be presented as a compact card with a truthful state, intended executor, purpose and a full-text “复制完整 Prompt / Copy Full Prompt” action. If the current ChatGPT surface cannot provide a dedicated clipboard action, use a complete copyable writing/code block; never fabricate a button or copy only a summary.

A prompt file by itself is not a dispatch. For bounded offline work, Owner may explicitly authorize execution by forwarding the complete task to its worker; Controller remains sole independent scoped acceptance authority. See the [offline-start protocol](../project/V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md).

## Model-routing implementation notes

See [V080 Model Routing Policy](../project/V080_MODEL_ROUTING_POLICY_20261119.md) for quota fallback, parallel execution requirements, exact model-identity recording and historical Argon attribution. The Owner's Neon routing decision applies prospectively; completed Gemini Argon records remain immutable.

## Historical 2026-11-21 H4 engineering queue

H4 S2–S5 consolidated readiness is independently accepted OFFLINE ONLY (336 independent PASS, 103 sealed files). For future Neon local readiness, Controller may prepare a formal dispatch or Owner may explicitly start scoped offline engineering with a full task card; do not impose both administrative paths. S2 genuine Canary remains BLOCKED_PRODUCTION/INPUT, S3 fundingRate history weight UNKNOWN, S4 real Feishu identity/callback blocked, S5 real end-to-end not observed. Pi P2 Owner-deferred. See [Project Home](../project/V080_PROJECT_HOME_20261118.md).

## Historical assignments — 2026-11-22 22:23; superseded by the 02:27 S3 dispatch

The new scope-limited offline acceptances are: Sol S2 V2 (55 PASS / 39 sealed); Neon optional risk CLI (12 PASS / 36 sealed, disabled by default); Astra S3 documentary study (9 sealed, `d` UNKNOWN); plus Neon optional Feishu Mode0/1 local offline onboarding. See [verified progress and next gates](../project/V080_PROGRESS_AND_NEXT_GATES_20261123.md). No live S2/S3/S4/S5 or recurring operations have been authorized; the next-stage Controller note is `PLANNING_ONLY / new_dispatch_issued=false`.

| Near-term role | Work/product owner | Appropriate effort and authority |
|---|---|---|
| Owner | KR/USDT-M route applicability; WSL2 direct egress/CA/shared-IP evidence; Feishu app/recipient prerequisites; separately approve/decline genuine one-run S2 | Evidence and decisions; do **not** forward sensitive data/API keys into chat |
| Controller 0-C | One engineering queue, independent receipt/hash/negative-test review, exact production holds, next-stage prioritization | Sole acceptance authority; 22:23 roadmap does **not** dispatch workers |
| Sol | P0 real-wire-capable default-disabled **OFFLINE** S2 derivative; later P1 S3 zero-retry sealed derivative and H/Core integration | XHigh for S2 security-sensitive seam; High or XHigh for S3 depending on signature/integration risks |
| Gemini Neon | Minimal Owner-local KR/WSL2 evidence, reused collectors (no new framework); later disjoint AI adapter work | Use task-suitable lower effort for mechanical inventory; reserve XHigh for real complex implementation/conflicts |
| Hydrogen | Feishu non-sensitive checklist, bounded documentation/fixture/QA | Simple/low-cost, no independent security architecture or activation |
| Astra | No new S3 general architecture task while documentary A/B/C holds are unchanged; later material funding-contract/strategy-methodology fork | On-demand architecture challenge; not routine repeated review |
| Historical 1-A (now fused into WEB Neon 0-C) | Original product/quality review, scope challenge and copy-ready prompts | Historical row only; web Neon holds both current functions, ChatGPT GPT-6 Sol reviews |

**Prompt display is mandatory, not optional:** Every Owner-facing full Prompt (new chat/task/research/audit/revision) MUST appear in one copyable card with the **entire** version and a real **复制完整 Prompt / Copy Full Prompt** action/button where the UI permits it. When custom copy controls are unavailable, use a complete WritingBlock/CodeBlock with native copy facility. Do **not** claim a nonfunctional decorative button is clickable. Never supply only a URL, an excerpt or a separate summary instead of a copyable complete prompt. The canonical Markdown and copy payload must match exactly.

Keep H-first, S5 field baseline before Pi P2. QI1/QL1 follow S5; QB1/QR1 afterward; neither these future packages nor real S4 is activated merely by updated role assignments.

## Owner-appointed fused WEB Gemini 4 Neon Controller (effective 2026-11-23)

The 2026-11-23 Owner decision supersedes the earlier **conditional backup/pilot** discussion. **Gemini 4 Neon WEB CHAT is now the combined 1-A and Controller 0-C**. **ChatGPT GPT-6 Sol** is the independent second reviewer. Local AGY Neon remains a complex engineering Worker and is NOT the Controller by virtue of sharing a model nickname. GPT-6.2 Sol stays the local complex engineering Worker; Astra and Hydrogen retain their engineering/architecture roles.

**Evidence and acceptance:** the web Neon Controller is the only active task queue/disposition writer. It must solicit/check independent ChatGPT Sol QA on important local Neon-authored packages, use additional cross-model/human challenge as appropriate for local Sol work, and resolve material concerns before final positive acceptance. A Controller is accountable for the signed scoped disposition but cannot turn Worker PASS into independent review or retroactively re-sign earlier decisions.

**Tools and copy UX:** Desktop Commander Remote MCP can inspect authorized local code and evidence when connected; GitHub and trustworthy official documentation can supplement it. Never assert access to unavailable local files or paste sensitive data into an LLM. Complete English task prompts must have a real copy action when the host supports it or a complete native-copy fenced fallback. No role change authorizes real Binance, Feishu, private accounts, production signer or TRADE.

**Historical note:** Previous suggestions to pilot Neon as a backup, and former ChatGPT 1-A/0-C separation, apply ONLY to earlier dates. Do not reinstate them as current requirements or create another queue.
