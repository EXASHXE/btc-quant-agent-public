# QUANT v0.8.0 — Owner Model Routing Policy (2026-11-19)

- **Status:** ACTIVE / OWNER-DIRECTED
- **Effective date:** 2026-11-19
- **Canonical branch:** docs/engineering
- **Scope:** Future v0.8.0 engineering assignments, parallel work allocation, role prompts and Controller handoffs
- **Authority:** Owner routing decision; Controller 0-C retains default task dispatch, queue ownership and sole independent scoped acceptance; explicit Owner-direct bounded OFFLINE execution is separately allowed under the 2026-11-21 protocol.

## 1. Owner decision

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
| **GPT-6.2 Astra** | Chief architecture and strategy advisor: system design, quantitative methodology, threat models, cross-module contracts and independent challenge | Architecture and consequential design decisions; does not own the engineering queue or self-accept |
| **GPT-6.2 Sol** | Primary complex engineering executor | Stateful/multi-module implementation, API/data/strategy integration and difficult bugs; default core engineering writer when capacity is available |
| **Gemini Neon** | Peer-level alternative complex engineering executor to GPT-6.2 Sol | Complex implementation when Sol quota/capacity is insufficient, or a separate non-overlapping package can be executed in parallel; same engineering and evidence bar as Sol |
| **GPT-6.2 Sol Max** | High-intensity lane within the Sol engineering role | Used when Sol is selected and unusually high cross-module reasoning is required; not a separate queue or independent role |
| **Gemini 4 Hydrogen** | Simple bounded engineering and mechanical QA | Fixtures, documentation, routine tests, lint/format, mechanical refactors and low-risk isolated fixes; not a fallback for complex work merely because Sol is unavailable |
| **Controller 0-C** | Default dispatcher, sole engineering queue/reconciliation owner, independent evidence auditor and scoped acceptance authority | Distinguishes genuine Controller dispatch from explicit Owner-direct offline start; approves/holds final acceptance |
| **ChatGPT 1-A** | Independent Owner-facing product, architecture and quantitative-research advisor | Advises and drafts; does not dispatch or accept |
| **Owner** | Product authority and permission decisions | Explicitly controls material product choices and separate live/private capability activation |

## 3. Task routing rules

- Architecture fork, quantitative methodology, threat model or cross-module design decision → **GPT-6.2 Astra**.
- Complex core implementation → **GPT-6.2 Sol** by default.
- Complex core implementation when Sol quota/capacity is unavailable → **Gemini Neon** at the same project complexity tier.
- Independent parallel engineering package → **GPT-6.2 Sol + Gemini Neon**, only after Controller 0-C approves a non-overlapping decomposition.
- Small deterministic fixtures, docs, mechanical tests and low-risk QA → **Gemini 4 Hydrogen**.
- Default dispatch, queue reconciliation, independent review and scoped acceptance → **Controller 0-C**; explicit Owner direct OFFLINE start is the narrow alternative under the [2026-11-21 protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md).

Do not downgrade a complex task to Hydrogen simply to keep work moving when Sol is quota-blocked. Use Neon if available and suitable; otherwise keep the task pending or ask the Owner to choose another route.

Astra remains the architecture authority/advisor for consequential design forks. Gemini Neon is an engineering executor, not a substitute for Astra's architecture review or Controller acceptance.

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

Controller 0-C remains the sole scoped acceptance authority and default dispatcher. An explicit Owner execute instruction for a named, bounded offline package suffices to start that limited work, even with no Controller receipt; record OWNER_DIRECT_OFFLINE_STARTED rather than inventing Controller dispatch. A worker's successful tests or READY_FOR_CONTROLLER_REVIEW handoff do not constitute Controller acceptance.

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

Use [Owner Direct Offline Protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md). Future tasks must specify CONTROLLER_DISPATCHED, OWNER_DIRECT_OFFLINE_ALLOWED, or PROPOSAL_ONLY. When Owner explicitly forwards a complete offline task to Neon or Sol with an execute instruction, a missing separate 0-C JSON does not stop offline work; log an offline Owner-start evidence note inside the isolated workroot. Never auto-start a draft or bypass real Binance/Feishu/model/private/TRADE gates. Controller remains the only independent acceptance authority.

## 9. 2026-11-23 product-first cost/effort routing update

Verified 2026-11-22 receipts and current roles: [Progress and next gates](V080_PROGRESS_AND_NEXT_GATES_20261123.md). Sol S2 V2, Neon optional CLI and Astra S3 study were independently accepted OFFLINE ONLY. Follow-up proposals in `V080_CONTROLLER_NEXT_STAGE_WSL2_S2_RELEASE_AND_S3_PREP_PLAN_20261122.json` have `new_dispatch_issued=false`.

- **P0 S2 physical transport capable but disabled wheel:** Sol XHigh because signatures, durable spend, release identity and TLS/route are consequential.
- **P0 minimal Owner-local KR/WSL2 evidence:** Neon with low/medium effort, or Hydrogen for non-sensitive mechanical inventory; do not build another verifier or overuse XHigh for a checklist. Escalate when conflicting trust/host evidence requires complex analysis.
- **Owner S4 onboarding preparation:** no new large worker task; Hydrogen can assemble a sanitized checklist. Mode0/Mode1 already accepted locally, not a real provider.
- **P1 S3 pinned three-file zero-retry offline package:** Sol High for bounded patch/QA; XHigh only if substantive signature/versioning/security complexity arises. Do not invent `fundingRate` general debit `d`.
- **Astra:** wait unless there is a consequential new source contract, funding-cost semantics or strategy methodology decision; accepted research should not be repeated without a new question.
- **Freeze optional risk CLI expansion:** no real Layer2/TRADE and no real position sizing; focus on first actual local Core market decision and S2 physical gate.

No selected model can self-accept or infer live authorization. Evaluate capability, quota, cost, change risk and test coverage together, not a blanket "all XHigh" rule. All new task/new-chat/research prompts follow [Prompt Copy Card Standard](V080_PROMPT_COPY_CARD_STANDARD_20261118.md): complete, truthful, card-shaped with an actual copy action where supported; native copyable WritingBlock/CodeBlock fallback.
