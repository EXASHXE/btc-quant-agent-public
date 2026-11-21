# QUANT v0.8.0 — Active Role Matrix (updated 2026-11-21)

Current routing authority: [V080 Model Routing Policy](../project/V080_MODEL_ROUTING_POLICY_20261119.md).

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

## 2026-11-21 H4 current engineering queue

H4 S2–S5 consolidated readiness is independently accepted OFFLINE ONLY (336 independent PASS, 103 sealed files). For future Neon local readiness, Controller may prepare a formal dispatch or Owner may explicitly start scoped offline engineering with a full task card; do not impose both administrative paths. S2 genuine Canary remains BLOCKED_PRODUCTION/INPUT, S3 fundingRate history weight UNKNOWN, S4 real Feishu identity/callback blocked, S5 real end-to-end not observed. Pi P2 Owner-deferred. See [Project Home](../project/V080_PROJECT_HOME_20261118.md).
