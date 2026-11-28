# QUANT — Owner Model Routing Policy (updated 2026-11-27)

> **Current navigation (2026-11-28):** [Wave D checkpoint](V100_WAVED_ACTIVE_CHECKPOINT_20261128.md) · [roadmap](V100_WAVED_ROADMAP_20261128.md) · [Sol WEB](../prompts/v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) · [Neon WEB](../prompts/v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md). Wave D: D1 offline delivery complete with operational blockers; D2 Run 1 delivered, Run 2 remediation RUNNING (latest T3 snapshot); D3 preparation complete, PROTOCOL_LOCK_REQUIRED (real DEV blind not executed). Joint acceptance pending. Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Older status/dispatch passages below are historical where inconsistent; durable policies remain applicable.


> Current 2026-11-28 status: Use [Wave D checkpoint](V100_WAVED_ACTIVE_CHECKPOINT_20261128.md), [current roadmap](V100_WAVED_ROADMAP_20261128.md), [Sol WEB bootstrap](../prompts/v1.0/V100_CHATGPT_SOL_WEB_1A_0C_20261128.md) and [Neon WEB bootstrap](../prompts/v1.0/V100_GEMINI_NEON_WEB_1A_0C_20261128.md) for current state. Wave C closed per Controller handoff; S7 empirical Run 2 completed and scoped accepted, 0/6 advancement; QRKP R4/R7 Rev02 sealed. Product development base 03af5397; S7 research base 3baa0ebb. Owner dispatched D1/D2/D3, original runs delivered; D2 remediation active, joint QA pending. Runtime proof/Field/recurrence not enabled, Layer 2 locked, TRADE disabled, M_global=19, no candidate promoted. Do not redispatch. Historical sections below are retained, not current gate instructions.


## Controlling local execution routing — 2026-11-27

**ACTIVE OWNER DECISION / PROSPECTIVE.** Applies to new or explicitly rerouted tasks only. All older routing defaults, including REV02 suggested executor cells, yield to this section. Do not rewrite completed work or silently switch an active run.

| Lane | Default role | Selection |
|---|---|---|
| AGY-A / AGY-B `gemini-4-neon` | Preferred complex engineering and research executor for the majority of suitable Sol-equivalent packages | Use explicit `thought_level=high` or `xhigh` when sustained high-level reasoning is required throughout; otherwise prefer Orchestrator (Neon) for suitable mixed-intensity complex tasks |
| AGY-A / AGY-B `gemini-pro-orchestrator-neon` | Variable-intensity Neon execution mode | Prefer when high-level reasoning is not required throughout (e.g. mixed planning, implementation, tests and reporting); use exact model ID and provider-managed effort |
| Codex `gpt-6.2-astra` | Priority recipient of Codex capacity | Consequential architecture, quantitative methodology, difficult research, critical design and specifically authorized high-value implementation; effort according to complexity |
| Codex `gpt-6.2-sol` | Reduced-share, selective complex engineering executor | Retain for critical integration, release/compatibility work, compatible thread continuity, distinctive engineering fit or when Neon capacity is unsuitable |
| AGY `gemini-4-hydrogen` | Lightweight deterministic executor | Docs, fixtures, mechanical checks and small changes; not a fallback for complex engineering |

**Routing procedure:** (1) classify complexity and need for sustained reasoning; (2) reserve more Codex capacity for Astra, prefer Neon for comparable implementation; (3) select standard Gemini 4 Neon High/XHigh when high-level reasoning is required throughout, otherwise prefer Orchestrator (Neon) for suitable Neon-class mixed-intensity work; (4) check actual availability, model catalog, compatible thread and write-set collisions; (5) record requested model/effort and actual executed identity where exposed in the exact Owner-approved prompt and receipt. No fixed allocation percentage is established. AGY-A/B are interchangeable provider instances, not permanent business owners.

T3 currently advertises `gemini-pro-orchestrator-neon` on both AGY instances without a separate thought-level option. This selection is not proof of uniform XHigh internal execution. Record effort as provider-managed/not exposed, unless the runtime proves otherwise; if a hard mandatory reasoning guarantee cannot be verified, disclose it and seek an alternative or stop at the applicable gate. Do not invent or silently substitute unsupported parameters.

Orchestrator (Neon) is a provider model/execution mode, not a project-level Controller or a new orchestration role. It has no added permission to dispatch T3 tasks, create child tasks beyond authorized scope, expand write sets, or bypass approvals. One accountable writer and one shared project queue remain. Required independent QA is performed directly by the opposite-family WEB Controller: Codex workers -> Neon WEB; AGY workers including Orchestrator Neon -> Sol WEB. No routine local QA-only dispatch.

No role change grants network, private USER_DATA, TRADE, production, deployment or recurrence permissions. The WEB appointments remain coequal and unchanged.


## Research specialization and evidence discipline — 2026-11-27

**Controller routing guidance, based on Owner-provided Neon WEB comparative review and prior Sol WEB QA.** This refines the active Owner routing override above; it is not a universal model ranking or new acceptance authority.

- **Astra (Codex, normally XHigh for difficult research):** prefer for quantitative methodology, paired empirical failure attribution, causal/temporal identification, leakage and overfitting controls, sample power and dependence, multiplicity, cost/funding/portfolio accounting, experiment protocol and consequential architecture contracts. Prefer Astra for method-lock work and high-value execution where justified; do not turn it into a permanent local QA-only lane.
- **Standard Gemini 4 Neon (AGY, High/XHigh):** prefer for sustained deep discovery, literature and source-code synthesis, external counterevidence, novel mechanisms, news/sentiment, cross-market research and open-ended engineering design. Neon also remains eligible for rigorous quantitative research. Use ordinary Neon with explicit high/xhigh when sustained advanced reasoning is required throughout; use Orchestrator (Neon) for suitable mixed-intensity implementation, tests, reporting or frozen-protocol experiment execution when continuous high effort is unnecessary.
- **Sol (Codex):** reduced-share selective implementation, critical integration and continuity; reserve more available Codex capacity for Astra. Hydrogen remains the bounded mechanical lane.

### Evidence and limits

QR-R2 (Astra) was an offline empirical attribution package. Its report records 240/240 matching ledger hashes and the TC-05 matched-cohort result: 112 common fills changed from +0.0538R to -0.0219R; 18 open-only fills averaged +0.1301R. Sol directly reread these reported values, not a new replay. Neon WEB reports QR-R2 CONTROLLER_ACCEPTED with no HIGH/MEDIUM findings; this comparison does not independently establish a zero-defect rate.

QR-R1/R3 (Neon) delivered 25 sources/38 claims/8 mechanism cards and 6 repositories/54 source references. Prior Sol WEB dispositions CONDITIONALLY_ACCEPTED include QR1-F01–F05 and QR3-F01–F05 (six HIGH and four MEDIUM findings combined). These include design refinements and evidence limitations, not ten equivalent confirmed implementation defects. Upstream verification was sampled. The tasks, access permissions, evaluation criteria, reviewer, and output sizes differ from QR-R2. T3 item counts and wall times do not measure equal-work efficiency. No controlled model comparison or independently verified external benchmark is established here; actual forecasting/profitability superiority is UNKNOWN.

Neon QR-R1 usefully challenges R2 P3's fast clock and OI assumptions and P4's one-settlement economic feasibility, and proposes new flow-variance and funding-tail hypotheses. R2 already states the two-leg cost hurdle explicitly (14 bp per leg, 28 bp of one leg's notional or 14 bp gross exposure); do not misattribute discovery of that arithmetic to Neon or label the original event-study hypothesis empirically falsified. These refinements and new hypotheses remain unvalidated.

### Practical research routing (prospective examples, not dispatch)

| Work type | Preferred route |
|---|---|
| Dynamic universe / cross-sectional statistical design (QR-R4) | Astra XHigh |
| News and sentiment / cross-asset source and mechanism discovery (QR-R5/R6) | standard Neon High/XHigh when sustained depth is needed |
| S7 estimator, evaluator, costs, PIT, preregistration and family-budget methodology | Astra XHigh, with Neon as eligible alternate or distinct discovery contributor |
| New mechanism generation and external challenge | Neon High/XHigh or Astra on a distinct research question |
| Frozen protocol execution, established modules and routine reporting | Orchestrator Neon when mixed intensity is suitable |
| Critical integration and continuity | selective Sol or appropriate Neon mode |

Use complementary contributions (discovery -> method lock -> bounded empirical execution -> independent WEB QA), not compulsory duplicate studies or a new serial review gate. Both models may challenge the other's design. A local Astra methodologist may author a scoped research/design artifact, but cannot issue final Controller acceptance or authorize promotion/live trading. Cross-family WEB Controller QA remains unchanged, and empirical evidence plus Owner authority—not model preference—governs strategy promotion. Preserve frozen B2 V1, M_global=19 historical accounting and sealed holdout. Reconcile findings during QR-SYNTH/S6/S7 design; do not restart or reroute active work.


## Controlling Owner override — 2026-11-24 09:34 +08:00

**ACTIVE Owner decision — 2026-11-24 09:34 +08:00:** **ChatGPT GPT-6.2 Sol (web)** and **Gemini 4 Neon (web)** are coequal, Owner-appointed **combined 1-A + Controller 0-C** role holders. Both independently audit code, strategy, architecture, QA and progress, plan/replan the project, challenge each other's conclusions, route local engineering and produce complete ready-to-forward next-task prompts. Neither is a permanent primary, backup, or review-only role. This supersedes the 2026-11-23 Neon-primary/Sol-review-only arrangement.

**One project queue, two collaborating Controllers:** both may independently propose tasks and scoped dispositions; reconcile the same canonical evidence and unique task IDs before starting work. For each actual dispatched package, identify one accountable 0-C (either web model) and one independent reviewer (normally the other web model); roles may rotate by task, not by model hierarchy. The accountable 0-C records one final scoped disposition after resolving material findings. Neither may overwrite a peer's receipt, manufacture a signature, launch a duplicate task or claim peer agreement not evidenced. Review disagreements remain visible; the Owner decides material unresolved priorities or scope. A missing peer response is not an automatic veto on independently authorized bounded routine OFFLINE work. Do not invent a blanket two-signature requirement or new approval layer; independent QA remains required where the established task contract requires it.

**Current Owner routing override (2026-11-27, prospective):** Prefer local AGY Gemini 4 Neon for the majority of new Sol-equivalent complex engineering and research packages; reduce local GPT-6.2 Sol task share, retaining it selectively for critical integration, continuity, or demonstrable fit. Prioritize Codex capacity for GPT-6.2 Astra's consequential architecture, quantitative methodology, difficult research and explicitly scoped high-value execution. For Neon-class work that does NOT require high-level reasoning throughout, prefer Orchestrator (Neon), exact model `gemini-pro-orchestrator-neon`, on AGY-A or AGY-B; when sustained high-level reasoning is required throughout, use standard Gemini 4 Neon (`gemini-4-neon`) with explicit `thought_level=high` or `xhigh`. Hydrogen handles simple bounded work. This routing override supersedes older default assignments but does not change dispatched tasks, historical receipts, authorization or WEB Controller authority. The web role holders are distinct from local same-family Workers. Favor the other model family for independent review of a Worker package; no Worker self-acceptance and no same-family-only review as evidence of independence for consequential work. Record actual reviewer and author provenance.

**Task and authorization discipline:** both web models can prepare a complete English task prompt, regardless of who reviewed or proposed it; Owner-facing discussion remains Chinese. Each prompt is copyable in full, with exact task ID, executor, scope, tests, evidence, and truthful start mode (PROPOSAL_ONLY / OWNER_DIRECT_OFFLINE_ALLOWED / CONTROLLER_DISPATCHED). Only actual valid dispatch or explicit Owner-direct offline execution starts a Worker. No duplicate dispatch prerequisite for the latter. Startup is read-only, no auto-dispatch; roles do not grant live Binance/Feishu/provider, private USER_DATA, TRADE, privileged operations, or retrospective signing authority. Historical receipts and prior authorship remain unchanged.

**Canonical active bootstraps:** [ChatGPT GPT-6.2 Sol — combined 1-A/0-C](../prompts/v0.8/V080_NEW_CHAT_CHATGPT_GPT6_SOL_INDEPENDENT_REVIEW_20261123.md) · [Gemini 4 Neon — combined 1-A/0-C](../prompts/v0.8/V080_GEMINI_NEON_WEB_FUSED_1A_0C_20261123.md). [Sol role definition](../roles/V080_CHATGPT_GPT6_SOL_INDEPENDENT_REVIEWER_20261123.md) · [Shared role matrix](../roles/V080_ACTIVE_ROLE_MATRIX_20261118.md). Existing filenames are retained for link compatibility; legacy standalone 1-A and 0-C entrypoints are not additional roles.

## Current model-routing checkpoint — 2026-11-23 02:27 +08:00

**WORKER HANDOFF (2026-11-23 ~02:52; not Controller acceptance):** Neon S3 isolated workroot has CONTROLLER_HANDOFF.md with READY_FOR_CONTROLLER_REVIEW_S3_ZERO_RETRY_OFFLINE; the worker reports 337/337 test invocations, 14/14 default-deny probes and a byte-reproducible post4 wheel. No later 0-C S3 acceptance was present in the inspected Controller directory. Treat all 337 PASS as WORKER_REPORTED until independent 0-C QA/review; do not redispatch the S3 implementation.

Sol's P0A S2 transport and Neon's P0B evidence have independent **OFFLINE** acceptances. An actual 0-C receipt dispatched **AGY Gemini 4 Neon XHigh** to the S3 zero-retry **OFFLINE** candidate at 02:27 (supersedes the historical planned Sol S3 assignment). See [current evidence](V080_PROGRESS_AND_NEXT_GATES_20261123.md). No genuine S2/S3/S4 grants.

Keep the Owner conversation in **Chinese**, but write all model/agent-facing prompts, including 1-A/0-C new-chat and worker review prompts, in **English**, with complete functional copy-card or honest native-copy fallback.


## 1. Historical Owner decision — 2026-11-19 (superseded for prospective routing by 2026-11-27 override)

Gemini Argon is replaced by **Gemini Neon** for future model routing.

The Owner designates Gemini Neon as a **peer-level alternative to GPT-6.2 Sol for complex engineering execution**. Neon is intended for substantial engineering work, including multi-module implementation, stateful changes, integration and difficult bugs.

Use Gemini Neon particularly when:

1. GPT-6.2 Sol quota or execution capacity is insufficient;
2. a genuinely independent engineering work package can proceed in parallel with Sol;
3. Controller 0-C determines that splitting the work reduces elapsed time without creating overlapping write ownership or integration ambiguity.

This is an Owner-defined project routing equivalence tier. It is not a claim of universal benchmark equivalence across every model, task or tool environment. Record the actual model identifier/variant exposed by the execution interface for each worker run; do not infer a version from the nickname Gemini Neon.

This change applies prospectively. Historical Gemini Argon reviews and completed worker attributions remain unchanged.

## 2. Active role matrix

| Role / model | Primary responsibility | Routing boundary |
|---|---|---|
| **WEB Gemini 4 Neon — combined 1-A + 0-C** | Coequal product/quant/architecture audit, planning, prompt generation and Controller disposition | One shared queue, accountable 0-C per task; independent peer challenge; not local Worker |
| **WEB ChatGPT GPT-6.2 Sol — combined 1-A + 0-C** | Same coequal authority: planning, audit, complete task prompts and scoped Controller work | Same coordination and independence requirements; not local Sol Worker |
| **GPT-6.2 Astra** | Codex priority lane: architecture, quantitative methodology, difficult research and scoped high-value execution | Does not own the engineering queue or self-accept |
| **LOCAL GPT-6.2 Sol** | Selective complex engineering executor, reduced share | Critical integration, release work, compatible thread continuity or demonstrable fit |
| **LOCAL AGY Gemini Neon** | Preferred Sol-equivalent complex engineering and research executor | Majority of suitable new packages; same engineering and evidence bar as Sol |
| **LOCAL AGY Orchestrator (Neon)** | Variable-intensity Neon execution mode | Exact ID `gemini-pro-orchestrator-neon`; provider-managed effort, no separate project authority |
| **GPT-6.2 Sol Max** | High-intensity lane within the Sol engineering role | Used when Sol is selected and unusually high cross-module reasoning is required; not a separate queue or independent role |
| **Gemini 4 Hydrogen** | Simple bounded engineering and mechanical QA | Fixtures, documentation, routine tests, lint/format, mechanical refactors and low-risk isolated fixes; not a fallback for complex work merely because Sol is unavailable |
| **Controller 0-C (both web models)** | Either can be accountable for dispatch and final disposition of a named task | No duplicate task, no same-family-only consequential self-review; one record per task |
| **1-A (both web models)** | Independent product, strategy and architecture advice, mutual review and next-task prompts | Advisory findings are not automatic dispatches |
| **Owner** | Product authority and permission decisions | Explicitly controls material product choices and separate live/private capability activation |

## 3. Task routing rules

- Architecture fork, quantitative methodology, threat model or cross-module design decision → **GPT-6.2 Astra**.
- Sol-equivalent complex implementation → **Gemini 4 Neon** preferentially; reserve Sol for critical integration, continuity or clear task fit.
- Neon-class task requiring advanced reasoning throughout → **standard Gemini 4 Neon High/XHigh**; when sustained high effort is not necessary, prefer **Orchestrator (Neon)**. Prioritize Codex capacity for Astra.
- Independent parallel engineering package → **GPT-6.2 Sol + Gemini Neon**, only after Controller 0-C approves a non-overlapping decomposition.
- Small deterministic fixtures, docs, mechanical tests and low-risk QA → **Gemini 4 Hydrogen**.
- Default dispatch, queue reconciliation, independent review and scoped acceptance → **either combined web 0-C with per-task accountable owner**; explicit Owner direct OFFLINE start is the narrow alternative under the [2026-11-21 protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md).

Do not downgrade a complex task to Hydrogen to keep work moving. If the preferred lane is unavailable or cannot meet the contract, replan or seek Owner approval for a suitable alternative.

Astra remains the preferred architecture and quantitative-methodology lane and may execute explicitly scoped high-value packages. Local AGY Gemini Neon and Orchestrator (Neon) remain Workers, not substitutes for required independent Controller QA.

## 4. Parallel execution protocol

Parallel Sol/Neon work is permitted only when all of the following are true:

1. Controller 0-C defines separate, independently testable work packages.
2. Each worker has an isolated worktree/work root and an explicit write-set.
3. Interface contracts and shared schemas are frozen before parallel implementation.
4. Workers do not concurrently modify the same files, migrations, package metadata, generated artifacts, shared database or mutable integration surface.
5. Each handoff identifies its base revision, changed paths, tests, evidence and exact model identity.
6. One named integration owner is responsible for combining the outputs and running integrated regression.
7. Controller 0-C performs one consolidated independent package/integration acceptance at the agreed boundary.

If the work cannot be separated cleanly, assign one core writer and execute sequentially. Parallelism is an option to reduce elapsed time, not a reason to create duplicate queues or conflicting ownership.

## 5. Consistent engineering and acceptance bar

Sol and Neon receive the same task quality requirements:

- complete, self-contained task prompt and verified baseline;
- explicit allowed/prohibited write surface;
- fail-first positive, negative, boundary and recovery tests;
- exact commands and actual PASS / FAIL / SKIP reporting;
- isolated workspace, reproducible build/install and sealed handoff;
- preservation of accepted baselines and evidence;
- no self-acceptance and no implied external permissions.

Either appointed web 0-C can be the accountable scoped acceptance authority and dispatcher for a task; only one final disposition may be recorded. An explicit Owner execute instruction for a named, bounded offline package suffices to start that limited work, even with no Controller receipt; record OWNER_DIRECT_OFFLINE_STARTED rather than inventing Controller dispatch. A worker's successful tests or READY_FOR_CONTROLLER_REVIEW handoff do not constitute Controller acceptance.

For each worker run, record the actual model label/identifier, thinking effort if exposed, execution environment, base commit, work root, changed paths and final handoff. Do not claim a model identity that the execution surface does not verify.

## 6. Existing work and historical attribution

- Existing B2 work was assigned to GPT-6.2 Sol and has a worker-reported READY_FOR_CONTROLLER_REVIEW handoff dated 2026-11-19. This routing update does not reassign, restart or modify that completed worker task.
- Do not edit an already-forwarded task prompt to silently change its executor. Apply this policy to future tasks and supplemental assignments.
- Completed Gemini Argon reviews in v0.7.0 remain attributed to Gemini Argon. Do not globally replace historical names in old reports, receipts or dated decisions.
- Future role matrices and newly created task prompts must use Gemini Neon, not Gemini Argon, as the Owner-designated complex engineering alternative.

## 7. Security and project boundaries

Gemini Neon inherits the same constraints as Sol:

- no secrets, private account payloads or credentials in prompts, logs, GitHub or external model inputs;
- no real Binance calls unless a separate live PUBLIC_MARKET activation has been reviewed and explicitly enabled;
- no private USER_DATA connection unless its independent read-only permission gate is proven and activated;
- Layer 3 TRADE_EXECUTION remains disabled;
- no Feishu/external message, deployment or financial action without its own authority.

This policy changes model routing only. It does not grant network access, credentials, private-account permission, deployment rights, trading rights or acceptance authority.

## 8. Prevent administrative dispatch deadlocks (Owner 2026-11-21)

Use [Owner Direct Offline Protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md). Future tasks must specify CONTROLLER_DISPATCHED, OWNER_DIRECT_OFFLINE_ALLOWED, or PROPOSAL_ONLY. When Owner explicitly forwards a complete offline task to Neon or Sol with an execute instruction, a missing separate 0-C JSON does not stop offline work; log an offline Owner-start evidence note inside the isolated workroot. Never auto-start a draft or bypass real Binance/Feishu/model/private/TRADE gates. Only the accountable 0-C records the final scoped acceptance after independent evidence; either web role holder may serve.

## 9. Historical 2026-11-22 proposed task routing (P0A/P0B now accepted; S3 Neon dispatch takes precedence)

Verified 2026-11-22 receipts and current roles: [Progress and next gates](V080_PROGRESS_AND_NEXT_GATES_20261123.md). Sol S2 V2, Neon optional CLI and Astra S3 study were independently accepted OFFLINE ONLY. Follow-up proposals in `V080_CONTROLLER_NEXT_STAGE_WSL2_S2_RELEASE_AND_S3_PREP_PLAN_20261122.json` have `new_dispatch_issued=false`.

- **P0 S2 physical transport capable but disabled wheel:** Sol XHigh because signatures, durable spend, release identity and TLS/route are consequential.
- **P0 minimal Owner-local KR/WSL2 evidence:** Neon with low/medium effort, or Hydrogen for non-sensitive mechanical inventory; do not build another verifier or overuse XHigh for a checklist. Escalate when conflicting trust/host evidence requires complex analysis.
- **Owner S4 onboarding preparation:** no new large worker task; Hydrogen can assemble a sanitized checklist. Mode0/Mode1 already accepted locally, not a real provider.
- **P1 S3 pinned three-file zero-retry offline package:** Sol High for bounded patch/QA; XHigh only if substantive signature/versioning/security complexity arises. Do not invent `fundingRate` general debit `d`.
- **Astra:** wait unless there is a consequential new source contract, funding-cost semantics or strategy methodology decision; accepted research should not be repeated without a new question.
- **Freeze optional risk CLI expansion:** no real Layer2/TRADE and no real position sizing; focus on first actual local Core market decision and S2 physical gate.

No selected model can self-accept or infer live authorization. Evaluate capability, quota, cost, change risk and test coverage together, not a blanket "all XHigh" rule. All new task/new-chat/research prompts follow [Prompt Copy Card Standard](V080_PROMPT_COPY_CARD_STANDARD_20261118.md): complete, truthful, card-shaped with an actual copy action where supported; native copyable WritingBlock/CodeBlock fallback.

## 10. Historical conditional Neon backup discussion (superseded 2026-11-23)

**HISTORICAL ONLY — superseded by the Owner 2026-11-24 dual appointment.** The following backup/pilot guidance described the state before Neon web actually became 1-A/0-C; it is no longer a precondition for the active assignment. Neon may handle 1-A-like advisory reviews (High for ordinary evidence/roadmap review, XHigh for difficult cross-module reasoning), subject to Owner's assessment and a canonical read-only brief. It may be a backup for 0-C only with explicit Owner activation, clean role handoff and independent review distinct from its own implementation output. The active S3 worker is AGY Neon XHigh: **do not route its self-review as final independent Controller acceptance.**

Tool order: (1) Desktop Commander Remote MCP for local read-only repositories and isolated QA (already available); (2) optional authenticated GitHub MCP for remote branch/commit/PR verification; (3) official web/documentation search MCP for time-sensitive venue policy; (4) optional dedicated read-only receipt/hash-verifier and prompt copy-card MCP App only if repeated work proves useful. Do not add a redundant filesystem MCP, broker/TRADE connector, production signer or an autonomous schedule. Restrict MCP tools to allowed roots; require human approval for privileged shell, git push or provider activity.

Independent QA depends on **isolation, reproducible challenges and conflict-of-interest separation**, not a model name or number of PASSES. Copy-card compliance depends on the **host UI**: ChatGPT clipboard action cannot be assumed in AGY. Use supported MCP App interactive copy UI or complete fenced English prompt with native copy.

### Minimum Owner-gated Neon role pilot (read-only; not auto-dispatched)

Before treating AGY Neon as a Controller substitute, let it audit **copies of three already adjudicated receipt packets plus two negative/counterexample fixtures**, and compare its traceable verdicts against the existing 0-C records; include at least one stale Worker-only PASS, one unsigned/unknown live eligibility, and the current S3 worker/Controller conflict. It must (1) verify actual code/docs HEAD and SHA manifests, (2) correctly separate Worker report, independent QA and 0-C acceptance, (3) preserve no-live/no-trade boundaries, (4) issue no new dispatch or false acceptance, (5) produce complete **English** prompt copy cards, and (6) handle missing MCP/browser data as UNKNOWN rather than hallucinate. Only then may Owner authorize a one-task, time-bounded alternate 0-C handoff with an independent human/different-model reviewer. The pilot may use Neon High for 1-A-style advice; reserve XHigh for an eventual isolated Controller-level critical review. No credential, production signer, recurring agent or second queue is required.
