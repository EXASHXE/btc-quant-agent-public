# QUANT v0.8.0 — Canonical Documentation Branch Policy (2026-11-18)

## Controlling Owner role decision — 2026-11-24 09:34 +08:00

**ACTIVE Owner decision — 2026-11-24 09:34 +08:00:** **ChatGPT GPT-6 Sol (web)** and **Gemini 4 Neon (web)** are coequal, Owner-appointed **combined 1-A + Controller 0-C** role holders. Both independently audit code, strategy, architecture, QA and progress, plan/replan the project, challenge each other's conclusions, route local engineering and produce complete ready-to-forward next-task prompts. Neither is a permanent primary, backup, or review-only role. This supersedes the 2026-11-23 Neon-primary/Sol-review-only arrangement.

**One project queue, two collaborating Controllers:** both may independently propose tasks and scoped dispositions; reconcile the same canonical evidence and unique task IDs before starting work. For each actual dispatched package, identify one accountable 0-C (either web model) and one independent reviewer (normally the other web model); roles may rotate by task, not by model hierarchy. The accountable 0-C records one final scoped disposition after resolving material findings. Neither may overwrite a peer's receipt, manufacture a signature, launch a duplicate task or claim peer agreement not evidenced. Review disagreements remain visible; the Owner decides material unresolved priorities or scope. A missing peer response is not an automatic veto on independently authorized bounded routine OFFLINE work. Do not invent a blanket two-signature requirement or new approval layer; independent QA remains required where the established task contract requires it.

**Local executors unchanged:** local GPT-6.2 Sol is primary complex engineering, local AGY Gemini 4 Neon is peer complex engineering, Gemini 4 Hydrogen handles simple bounded work, GPT-6.2 Astra handles consequential architecture/quantitative-methodology challenges. The web role holders are distinct from local same-family Workers. Favor the other model family for independent review of a Worker package; no Worker self-acceptance and no same-family-only review as evidence of independence for consequential work. Record actual reviewer and author provenance.

**Task and authorization discipline:** both web models can prepare a complete English task prompt, regardless of who reviewed or proposed it; Owner-facing discussion remains Chinese. Each prompt is copyable in full, with exact task ID, executor, scope, tests, evidence, and truthful start mode (PROPOSAL_ONLY / OWNER_DIRECT_OFFLINE_ALLOWED / CONTROLLER_DISPATCHED). Only actual valid dispatch or explicit Owner-direct offline execution starts a Worker. No duplicate dispatch prerequisite for the latter. Startup is read-only, no auto-dispatch; roles do not grant live Binance/Feishu/provider, private USER_DATA, TRADE, privileged operations, or retrospective signing authority. Historical receipts and prior authorship remain unchanged.

**Historical audit checkpoint (2026-11-23; recheck current originals):** Local Neon full-system audit V080-NEON-FULL-SYSTEM-AUDIT-AND-REFACTOR-BLUEPRINT-20261123 was WORKER_REPORTED / READY_FOR_OWNER_AND_INDEPENDENT_ARCHITECTURE_REVIEW; 14 report seals were checked and 12 work packages were ADVISORY_PROPOSAL_NOT_DISPATCHED. Disputed vendor contracts, post6/post7 readiness and risk-cap changes need independent evidence. Role changes do not adopt or dispatch that blueprint.

**Canonical active bootstraps:** [ChatGPT GPT-6 Sol — combined 1-A/0-C](../prompts/v0.8/V080_NEW_CHAT_CHATGPT_GPT6_SOL_INDEPENDENT_REVIEW_20261123.md) · [Gemini 4 Neon — combined 1-A/0-C](../prompts/v0.8/V080_GEMINI_NEON_WEB_FUSED_1A_0C_20261123.md). [Sol role definition](../roles/V080_CHATGPT_GPT6_SOL_INDEPENDENT_REVIEWER_20261123.md) · [Shared role matrix](../roles/V080_ACTIVE_ROLE_MATRIX_20261118.md). Existing filenames are retained for link compatibility; legacy standalone 1-A and 0-C entrypoints are not additional roles.



- **Status:** ACTIVE
- **Canonical documentation branch:** GitHub docs/engineering
- **Executable source/runtime branch:** GitHub v0.8.0
- **Repository:** EXASHXE/btc-quant-agent-public

## 1. Owner decision and authority

The Owner designates docs/engineering as the sole canonical writable source for all QUANT project documentation, including v0.8.0.

This includes:

- Product baseline and Owner decisions;
- Architecture and API endpoint matrices;
- Roadmaps, stage gates and milestone definitions;
- Role matrices and role descriptions;
- New-chat bootstrap prompts;
- Engineering, architecture-review and research task cards;
- Controller/worker handoffs and progress audits;
- Runbooks and project documentation standards.

The v0.8.0 branch is the executable code/runtime baseline. Any same-path project documentation retained on v0.8.0 is a historical or implementation-time mirror, not the current canonical documentation source.

## 2. Branch separation

| Branch | Authority | Permitted content |
|---|---|---|
| docs/engineering | Sole project-document authority | Project docs, architecture, role docs, roadmap, task prompts, handoffs, runbooks and documentation standards |
| v0.8.0 | Executable code/runtime authority | Source code, tests, runtime configuration, local implementation evidence and approved workspaces |

Do not force-merge docs/engineering into v0.8.0. Do not change the repository default branch as part of documentation updates.

Do not create a second writable documentation authority on v0.8.0.

## 3. Source-of-truth procedure

For project direction, roles, architecture decisions, task state summaries and prompts:

1. Read the latest GitHub docs/engineering HEAD.
2. Treat docs/engineering documents as canonical even if a same-path copy exists on v0.8.0 or in a local code checkout.
3. Read actual code, tests, local Controller decisions and worker handoffs from the v0.8.0 local workspace separately.
4. Keep VERIFIED, OWNER_ATTESTED, WORKER_REPORTED, CONTROLLER_ACCEPTED and UNKNOWN distinct.
5. Do not infer runtime progress or acceptance from documentation-only commits.

If docs/engineering cannot be reached, report the limitation. Do not silently substitute stale v0.8.0 documentation.

## 4. Documentation update procedure

Every documentation-only update must:

1. Target GitHub docs/engineering.
2. Be bounded to documentation paths.
3. Preserve historical Controller decisions and worker receipts; add supplemental records rather than rewriting immutable decisions.
4. Avoid source code, tests, runtime configuration, credentials, private account payloads, protected market data, registries and deployment files.
5. Run whitespace/link/path checks where applicable.
6. Create one bounded docs-only commit.
7. Report the exact commit SHA, changed paths and canonical links.

Do not commit docs-only changes to v0.8.0.

## 5. Prompt presentation

All Owner-facing prompt authors must follow:

[V080 Prompt Copy Card Standard](V080_PROMPT_COPY_CARD_STANDARD_20261118.md).

Every distinct complete prompt requires its own compact card, truthful status, intended executor and full-text copy action where supported. If the UI cannot provide a dedicated clipboard action, provide a complete copyable WritingBlock/CodeBlock. Never fabricate an interactive control or copy only a summary.

A task prompt FILE alone is not a dispatch. Either appointed web Controller 0-C may be accountable for a named dispatch and scoped acceptance, with one reconciled disposition per task. A complete strictly offline task that the Owner explicitly forwards with EXECUTE is independently startable as OWNER_DIRECT_OFFLINE_STARTED under the [newer 2026-11-21 protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md); do not invent a Controller dispatch receipt. All real capability gates remain separate.

## 6. Active v0.8.0 documentation entrypoints

- [Project Home](V080_PROJECT_HOME_20261118.md)
- [Owner Rebaseline Decision](V080_OWNER_REBASELINE_DECISION_20261118.md)
- [Three-Layer API Architecture](../architecture/V080_THREE_LAYER_API_ARCHITECTURE_20261118.md)
- [Binance Endpoint Matrix](../architecture/V080_BINANCE_API_ENDPOINT_MATRIX_20261118.md)
- [Roadmap and Gates](V080_ROADMAP_AND_GATES_20261118.md)
- [Baseline Migration Record](V080_BASELINE_MIGRATION_RECORD_20261118.md)
- [Active Role Matrix](../roles/V080_ACTIVE_ROLE_MATRIX_20261118.md)
- [1-A New-Chat Prompt](../prompts/v0.8/V080_NEW_CHAT_1A_20261118.md)
- [Controller 0-C New-Chat Prompt](../prompts/v0.8/V080_NEW_CHAT_CONTROLLER_0C_20261118.md)

## 7. Historical v0.7.0 documentation

Existing v0.7.0 documents remain available as historical records. They are not automatically rewritten to describe v0.8.0. For current v0.8.0 roles, product baseline and task state, use the V080 documents linked above.

This policy is documentation-only. It does not authorize API calls, credentials, external messages, deployment, private-account access or trading.

## 8. Operational AGENTS pointer caveat (2026-11-21)

The executable v0.8.0 root AGENTS.md contains historical initial-R1 wording that a worker may mistake for a general dispatch prerequisite. Current canonical Owner-direct OFFLINE start policy is in [this protocol](V080_OWNER_DIRECT_OFFLINE_TASK_EXECUTION_PROTOCOL_20261121.md). All new worker chat prompts must cite it explicitly. Changing executable-root AGENTS.md is a separately scoped runtime bootstrap adjustment, not an excuse to create a second canonical project-document authority on v0.8.0. Do not update executable source or accepted manifests merely as part of docs-only work.

## 2026-11-23 status/copy-card update

- Active latest status appendix: [V080_PROGRESS_AND_NEXT_GATES_20261123.md](V080_PROGRESS_AND_NEXT_GATES_20261123.md); older 2026-11-21 inline tables remain historical when superseded by verified later Controller records.
- Active new Controller bootstrap: [V080_NEW_CHAT_CONTROLLER_0C_20261118.md](../prompts/v0.8/V080_NEW_CHAT_CONTROLLER_0C_20261118.md).
- Every Owner-facing complete prompt MUST be displayed in a **complete copyable card with a genuine Copy control whenever supported**, otherwise a WritingBlock/CodeBlock with native copy. Preserve precise content/version. No fake button, links-only, or partial excerpt. See [Prompt Copy Card Standard](V080_PROMPT_COPY_CARD_STANDARD_20261118.md).

## 2026-11-23 original-file policy correction

Update the **original canonical v0.8.0 files in place** for current roles, Controller/1-A new-chat bootstraps, prompt presentation and roadmaps. New dated evidence records can be kept as dated references, but must not become conflicting secondary new-chat authorities. Current canonical new chats are `docs/prompts/v0.8/V080_NEW_CHAT_1A_20261118.md` and `docs/prompts/v0.8/V080_NEW_CHAT_CONTROLLER_0C_20261118.md`, both revised in place. The duplicate `V080_NEW_CHAT_CONTROLLER_0C_20261123.md` is retired as a compatibility pointer.

The Owner-facing discussion is Chinese; the **agent-facing copy payload is English by default**. All complete prompts require a real copy-card or a complete native-copy fallback. Source/Controller evidence remains in the executable workroot; docs text alone never approves live action.
