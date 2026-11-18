# QUANT v0.8.0 — Canonical Documentation Branch Policy (2026-11-18)

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

A task prompt is not a dispatch. Controller 0-C remains the sole engineering dispatcher and scoped acceptance authority.

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
