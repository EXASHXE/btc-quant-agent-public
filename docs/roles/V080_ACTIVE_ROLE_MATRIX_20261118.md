# QUANT v0.8.0 — Active Role Matrix (updated 2026-11-23)


## Current routing checkpoint — 2026-11-23 02:27 +08:00

**WORKER HANDOFF (2026-11-23 ~02:52; not Controller acceptance):** Neon S3 isolated workroot has CONTROLLER_HANDOFF.md with READY_FOR_CONTROLLER_REVIEW_S3_ZERO_RETRY_OFFLINE; the worker reports 337/337 test invocations, 14/14 default-deny probes and a byte-reproducible post4 wheel. No later 0-C S3 acceptance was present in the inspected Controller directory. Treat all 337 PASS as WORKER_REPORTED until independent 0-C QA/review; do not redispatch the S3 implementation.

P0A S2 transport and P0B KR/WSL2 evidence accepted in their **OFFLINE** scopes. **AGY Neon XHigh is the actively dispatched S3 zero-retry offline executor** (Controller decision `V080_CONTROLLER_NEON_S3_ZERO_RETRY_OFFLINE_ENGINEERING_DISPATCH_20261123.json`). Do not reassign to Sol without a new legitimate decision. **Gemini Neon may be a candidate advisory/backup Controller under explicit Owner handoff; a Neon Worker may not self-accept.** See [verified progress](../project/V080_PROGRESS_AND_NEXT_GATES_20261123.md).

**Mandatory prompt format:** Owner discussion Chinese; every *agent-facing* prompt (including new chats) **English** by default, one functional complete-copy card per prompt, not a summary/link/fake button. No role recommendation grants real provider access.


| Role | Responsibility | Boundary |
|---|---|---|
| Owner | Product and permission authority; may directly START a specifically identified, bounded OFFLINE engineering task by explicitly forwarding it to a worker; separate live/privileged approvals remain mandatory | Do not infer authorization from a draft file or a previous chat; no secrets or automatic trading permission |
| GPT-6.2 Astra | Chief architecture and strategy role; cross-module design, critical technical decisions, threat models and independent challenge of Sol's design | Advises/reviews; does not dispatch, implement by default or self-accept |
| GPT-6.2 Sol | Primary engineering executor: public/private API adapters, data engine, strategy implementation, integration and difficult bug fixes | Implements scoped task in isolated workspace; no live calls/credentials during offline task; no self-acceptance |
| GPT-6.2 Sol Max | High-intensity implementation lane within the Sol engineering role for cross-module or unusually complex changes | Not a separate queue or controller; same Sol scope and acceptance boundaries |
| Gemini Neon | Peer-level alternative complex engineering executor to GPT-6.2 Sol; used when Sol quota/capacity is insufficient or for approved independent parallel packages | Same engineering/evidence/acceptance bar as Sol; isolated worktree and non-overlapping write set; not architecture authority or self-acceptance |
| Gemini 4 Hydrogen | Simple engineering, docs, fixtures, mechanical tests, routine lint/format and QA | Simple bounded work only; not a substitute for Sol/Neon on complex work; does not accept its own work |
| Controller 0-C | Default dispatcher, sole queue/reconciliation owner and independent scoped acceptance authority; recognizes explicit Owner-direct offline starts as a separately labeled execution mode | Do not require a duplicate formal dispatch JSON for a task the Owner explicitly starts OFFLINE; never forge past receipts; live gates separate |
| ChatGPT 1-A | Independent Owner-facing advisor; audits plans, challenges architecture, quantitative strategy and product tradeoffs, prepares prompts/docs on request | Not 0-C; does not dispatch or issue acceptance |
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
- Dispatch, queue control, independent audit and acceptance → Controller 0-C.
- Independent Owner advice → ChatGPT 1-A.

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
| ChatGPT 1-A | Independent product/quality review, scope challenge, copy-ready 0-C/Worker Prompt drafts, project docs only at Owner request | Advisory; no task dispatch, signature, live grant or acceptance |

**Prompt display is mandatory, not optional:** Every Owner-facing full Prompt (new chat/task/research/audit/revision) MUST appear in one copyable card with the **entire** version and a real **复制完整 Prompt / Copy Full Prompt** action/button where the UI permits it. When custom copy controls are unavailable, use a complete WritingBlock/CodeBlock with native copy facility. Do **not** claim a nonfunctional decorative button is clickable. Never supply only a URL, an excerpt or a separate summary instead of a copyable complete prompt. The canonical Markdown and copy payload must match exactly.

Keep H-first, S5 field baseline before Pi P2. QI1/QL1 follow S5; QB1/QR1 afterward; neither these future packages nor real S4 is activated merely by updated role assignments.

## Conditional Gemini 4 Neon advisor / Controller backup (not auto-activated)

The Owner may designate Gemini 4 Neon **High or XHigh** for an *independent advisory 1-A-style* review after it is given the canonical docs/engineering read-only bootstrap. **It is a functional alternative, not proof of identical judgment to ChatGPT 1-A.** The model may audit roadmap, architecture, quantitative reasoning and produce English task-copy cards. Check provenance, source citations, math and hallucination through real examples.

**0-C replacement is stricter:** AGY Neon may be a temporary **backup Controller only after an explicit Owner role handoff**, with one active acceptance authority and documented changeover. A Neon implementation worker (including the presently dispatched S3 task) may NEVER be the sole independent Controller accepting its own work or the QA runner's same-family output. Require a separate reviewer/model or independently witnessed substantive QA; distinguish tool execution from final Controller acceptance. Prior Controller receipts remain immutable; no retroactive role reassignment, forged signatures, authority to trade or automatic live access.

**MCP / tool profile:** Desktop Commander Remote MCP already supplies file, local git and shell operations, so no extra filesystem MCP is required. Optional: an authenticated GitHub MCP for remote branch/PR/commit review and a trustworthy web/documentation search MCP for current official provider evidence. Keep production credentials/provider network tools disabled; use separate read-only Controller role/policy for access. Antigravity does not inherit ChatGPT's native copy-card UI or connected apps automatically. A genuine MCP App (`ui://` interactive viewer) may be built for copy cards if the selected AGY client supports it; otherwise use full English Markdown fenced prompt with native copy. Never claim an inert plain Markdown link is a copy button.
