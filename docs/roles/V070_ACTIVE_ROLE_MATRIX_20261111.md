# Quant v0.7.0 — Active Roles and Engineering Accountability (Current 2026-11-16)

[Current progress audit and accelerated Real MVP roadmap](../project/V070_PROJECT_PROGRESS_AUDIT_AND_CLOSURE_ROADMAP_20261116.md) · [Current model routing](../project/V070_ENGINEERING_MODEL_TASK_ROUTING_20261116.md) · [MVP Home](../project/V070_MVP_CLOSURE_HOME_20261111.md) · [New 0-C chat](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261116_REAL_MVP_ACCELERATION.md) · [Prompt copy standard](../project/V070_PROMPT_COPY_CARD_STANDARD_20261111.md).

## Current controlling roles

| Role | Accountable work | Limit and proof boundary |
|---|---|---|
| **Owner** | Product priorities; routine delegated offline L0 authority; separate public RAW L1-A, Venue WATCH L1-B and Feishu L1 approvals; L2 privileged/financial decisions | A task prompt is not a grant; no inferred Source, Feishu or execution authority |
| **Controller 0-C** | Sole engineering dispatcher, architecture decision owner, independent reviewer and scope-specific acceptance authority | No worker self-acceptance; no parallel queue; no implicit L1/L2 |
| **Codex GPT Sol** | Stateful/core multi-file implementation: Source, custody, retention, clock adapters, Q0BC/Producer/Outbox, WAL and cross-platform recovery | Implements approved contracts; isolated worktrees; fail-first tests; no self-acceptance |
| **Gemini 4 Hydrogen** | Simple bounded L0 fixtures, deterministic tests, docs, mechanical changes and QA | No trust/architecture decisions or core custody/clock/Outbox state-machine changes |
| **Codex GPT Sol Max** | Specialist architecture/security/provenance review when a consequential design fork exists | Separate reviewer session when needed; advice is not Controller acceptance |
| **ChatGPT 1-A** | Independent Owner-facing strategy/product/architecture/quant advisor; status audit, roadmap challenge and docs/prompt preparation on explicit request | Not 0-C; no dispatch, acceptance, live access, deployment or trading |
| **Q0BC Producer** | Sole canonical plan/eligibility/transition and Outbox writer | No second dispatcher or direct scheduler Outbox mutation |
| **Q0F / Feishu** | Mock adapter and later separately authorized provider channel | Real send requires its own L1; provider ACK is not human read |
| **Source / Custody** | Provenance, rights, time, exact bytes, identity, retention and admission | Real Source remains blocked until exact source gates and grants pass |
| **Shadow / dashboard** | Append-only observations, immutable scan roster, honest denominators and forward monitoring | Static fixtures and offline acceptance are not forward qualification or Alpha |

No future standing Gemini Orchestrator. Historical Argon+Hydrogen P1C04 collaboration remains a one-time historical assignment. Sol Max is a specialist reviewer, not a competing Controller. Astra is not a standing route under the current role matrix unless Owner explicitly changes the routing again.

## Verified stage state — 2026-11-16

- Q0A5 G0–G4 three-symbol synthetic L0: accepted.
- P1C04 Fix01: ACCEPT_OFFLINE_SCOPED, mock-only.
- P1D01 dual-platform L0: accepted within scope; production WAL remains unqualified.
- P1D02 Clock Trust L0: accepted; independent authenticated UTC remains false.
- P1D02B NTS contract: offline accepted with native NTS hold.
- P1-B Venue WATCH admission Fix01: SCOPED_ACCEPTED.
- Venue Time WATCH-only L0: SCOPED_ACCEPTED, WSL fixture clock only; real endpoint semantics and native Windows QPC remain unqualified.
- P1-B ADR-01 V2: proposed; Sol Max independent review delivered with NEEDS_SPECIFIC_ARCHITECTURE_FIX recommendation; 0-C decision pending.
- P1D03: not formally dispatched/accepted. Existing 12-symbol presentation is static disabled fixtures, not a live scanner; real screened denominator is zero.
- Public RAW L1-A, Venue WATCH L1-B, Feishu L1: not authorized.

## Current task ownership

1. **0-C read-only:** reconcile the Sol Max review against later P1-B Fix01 acceptance; decide ADR-01 V2 design-only disposition; audit the existing P1D03 disabled-source evidence.
2. **Next Sol core task candidate:** canonical Q0BC COMMIT ambiguity L0, including stable ID + payload fingerprint, paired Ledger/Outbox invariant, UNKNOWN, recovery fence and no automatic dispatch/retry of UNKNOWN. Dispatch only after 0-C confirms no overlapping core worker and resolves the ADR gate.
3. **Hydrogen:** independent narrow fixtures/QA only, without touching Sol's active worktree.
4. **Sol Max:** no duplicate review dispatch; current handoff already exists and awaits 0-C reconciliation.

## Permission and communication rules

- Routine offline L0 coding, tests, fixtures and docs are delegated; do not request repeated SHA/test approval.
- Public RAW L1-A and derived Venue WATCH L1-B are separate explicit Owner + 0-C grants.
- Real Feishu send is a third separate L1.
- Privileged host changes, private accounts, financial/destructive actions and protected-history access require distinct L2.
- No real Source, DNS/NTP/NTS, Feishu, account, order or trade operation follows from a worker prompt.
- Every Owner-facing worker/new-chat prompt uses a functional full-text “复制完整 Prompt” action or a complete copyable fallback. A prompt does not prove dispatch.

## Immutable project gates

CLOCK_UNTRUSTED=true; REAL_INDEPENDENT_UTC_QUALIFIED=false; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; SQLITE_WAL_ENGINE_NOT_QUALIFIED=true; REAL_FEISHU_SEND=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false.
