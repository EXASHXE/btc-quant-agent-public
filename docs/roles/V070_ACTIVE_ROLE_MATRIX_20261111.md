# Quant v0.7.0 — Active Roles and Engineering Accountability (Current 2026-11-18)

[Current progress audit](../project/V070_PROJECT_PROGRESS_AUDIT_AND_CLOSURE_ROADMAP_20261116.md) · [Current GPT-6.2 model routing](../project/V070_ENGINEERING_MODEL_TASK_ROUTING_20261118.md) · [MVP Home](../project/V070_MVP_CLOSURE_HOME_20261111.md) · [New 0-C chat](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261118_REAL_MVP_CONTINUATION.md) · [New 1-A chat](../../prompts/v0.7/V070_NEW_CHAT_1A_20261118_REAL_MVP_CONTINUATION.md) · [Prompt copy standard](../project/V070_PROMPT_COPY_CARD_STANDARD_20261111.md).

## Current controlling roles

| Role | Accountable work | Limit and proof boundary |
|---|---|---|
| **Owner** | Product priorities; routine delegated offline L0 authority; separate public RAW L1-A, Venue WATCH L1-B and Feishu L1 approvals; L2 privileged/financial decisions | A task prompt is not a grant; no inferred Source, Feishu or execution authority |
| **Controller 0-C** | Sole engineering queue owner, architecture gate, dispatcher, independent reviewer and scope-specific acceptance authority | No worker self-acceptance; no parallel queue; no implicit L1/L2 |
| **Codex GPT-6.2 Astra** | Complex architecture analysis, threat models, architecture alternatives, trust boundaries, cross-module contracts and critical-path decisions | Design/recommendation role; no dispatch, grant issuance or self-acceptance |
| **Codex GPT-6.2 Sol** | Primary complex engineering implementation: stateful/multi-file work, Source/custody/retention, clock adapters, Q0BC/Producer/Outbox, WAL, concurrency and recovery | Implements approved designs in isolated worktrees; fail-first tests; no self-acceptance |
| **Gemini 4 Hydrogen** | Simple bounded L0 fixtures, deterministic tests, docs, mechanical changes and low-risk QA | No trust/architecture decisions or core custody/clock/Outbox state-machine changes |
| **ChatGPT 1-A** | Independent Owner-facing strategy/product/architecture/quant advisor; status audit, roadmap challenge and docs/prompt preparation on explicit request | Not 0-C; no dispatch, acceptance, live access, deployment or trading |
| **Q0BC Producer** | Sole canonical plan/eligibility/transition and Outbox writer | No second dispatcher or direct scheduler Outbox mutation |
| **Q0F / Feishu** | Mock adapter and later separately authorized provider channel | Real send requires its own L1; provider ACK is not human read |
| **Source / Custody** | Provenance, rights, time, exact bytes, identity, retention and admission | Real Source remains blocked until exact source gates and grants pass |
| **Shadow / dashboard** | Append-only observations, immutable scan roster, honest denominators and forward monitoring | Static fixtures and offline acceptance are not forward qualification or Alpha |

**Historical attribution:** the 2026-11-17 Track A L1-A architecture review remains attributed to Codex GPT Sol Max in its original receipts. This is not a current default role. Future complex architecture work routes to GPT-6.2 Astra. No historical task or Controller decision is renamed retroactively.

No future standing Gemini Orchestrator. GPT-6.2 model routing is an Owner-selected task allocation, not a benchmark claim.

## Routing and execution contract

1. **Astra 6.2** analyzes complex architecture and produces a bounded ADR, threat model or implementation contract.
2. **Controller 0-C** decides whether the design is acceptable for the scoped task and owns dispatch.
3. **Sol 6.2** implements the accepted design when a core engineering task is authorized.
4. **Controller 0-C** independently verifies evidence and issues or withholds scoped acceptance.
5. **Hydrogen** handles simple, non-overlapping fixtures/docs/QA tasks delegated by 0-C.

For routine implementation without a consequential design fork, 0-C may route directly to Sol. Astra's analysis never grants permission or replaces Controller acceptance. One active core implementation owner at a time.

## Verified stage state — 2026-11-17

- Q0A5 G0–G4 three-symbol synthetic L0: accepted.
- P1C04 Fix01: ACCEPT_OFFLINE_SCOPED, mock-only.
- P1D01 dual-platform L0: accepted within scope; production WAL remains unqualified.
- P1D02 Clock Trust L0: accepted; independent authenticated UTC remains false.
- P1D02B NTS contract: offline accepted with native NTS hold.
- P1-B Venue WATCH admission Fix01 and detached Venue Time WATCH-only L0: scoped accepted.
- P1-B ADR-01 V2: ACCEPTED_DESIGN_ONLY_NO_L1_AUTHORITY; no public L1 follows.
- P1D03: SCOPED_ACCEPTED for static 12-symbol disabled-source monitor and synthetic fixture separation only; not a live scanner.
- Protected-window design: accepted design-only; PROTECTED_2024_2026 and FINAL_HOLDOUT_2026 remain active with no November 2026 bar exception.
- Pre-grant readiness: accepted offline/documentary only; A/B templates remain unsigned and the endpoint allowlist remains empty.
- Q0BC COMMIT ambiguity: accepted offline L0 only; production WAL and power-loss durability remain unqualified.
- TIME_ONLY one-shot: accepted synthetic L0 only; TIMEONLY-F01 report-contract follow-up remains open and TIMEONLY-F02 transport/durability remains unknown.
- Hydrogen Track A Longrun P0–P4: accepted offline L0 only.
- Hydrogen TIME_ONLY report-contract hardening: dispatched for Owner manual forward; Controller record says worker not started by Controller.
- Track A L1-A rights/applicability screening: HOLD_UNPROVED; Owner evidence is pending.
- PUBLIC_SOURCE_L1, VENUE_WATCH_L1 and real Feishu L1 remain NOT_AUTHORIZED; real screened denominator remains zero.

## Current task ownership

1. **Owner:** provide controlled operator, physical-region, permitted-route, current USD-M rights and COLLECT/RETAIN evidence, including audience and retention/purge scope. Keep private identity/contract material out of ordinary chat.
2. **Controller 0-C:** review the supplied materials and retain HOLD_UNPROVED if incomplete. Do not start host/network work or issue a grant automatically.
3. **Hydrogen:** complete the isolated TIMEONLY-F01 report-contract task only if it has been manually forwarded; inspect current status before any dispatch.
4. **Astra 6.2:** architecture-critical analysis only when a real decision fork exists; do not repeat the accepted Sol Max L1-A review.
5. **Sol 6.2:** complex implementation only after 0-C defines the task and verifies prerequisites; no duplicate or speculative L0 expansion.

## Permission and communication rules

- Routine offline L0 coding, tests, fixtures and docs are delegated; do not request repeated SHA/test approval.
- Public RAW L1-A and derived Venue WATCH L1-B are separate explicit Owner + 0-C grants.
- Real Feishu send is a third separate L1.
- Privileged host changes, private accounts, financial/destructive actions and protected-history access require distinct L2.
- No real Source, DNS/NTP/NTS, Feishu, account, order or trade operation follows from a worker prompt.
- Every Owner-facing worker/new-chat prompt uses a functional full-text copy action or a complete copyable fallback. A prompt does not prove dispatch.

## Immutable project gates

CLOCK_UNTRUSTED=true; REAL_INDEPENDENT_UTC_QUALIFIED=false; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; SQLITE_WAL_ENGINE_NOT_QUALIFIED=true; REAL_FEISHU_SEND=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false.
