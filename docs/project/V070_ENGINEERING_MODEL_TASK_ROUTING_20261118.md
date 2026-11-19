> **V0.8.0 ROUTING OVERLAY — OWNER UPDATE 2026-11-19:** For QUANT v0.8.0 and future v0.8.0 engineering assignments, use [V080 Owner Model Routing Policy](V080_MODEL_ROUTING_POLICY_20261119.md). Gemini Neon replaces Gemini Argon as the Owner-designated peer-level alternative to GPT-6.2 Sol for complex engineering, including Sol quota fallback and Controller-approved independent parallel work. This overlay does **not** rewrite the v0.7.0 historical task attributions or change the version-specific routing record below.

# Quant v0.7.0 — Engineering Model and Task Routing (Current 2026-11-18)

> **Owner model-routing update — 2026-11-18.** GPT-6.2 Sol replaces the prior GPT-6.1 Sol implementation assignment. GPT-6.2 Astra replaces the prior GPT-6 Astra architecture-analysis assignment. The responsibility split is unchanged: Astra designs, Sol implements, Hydrogen handles simple bounded work, and Controller 0-C dispatches and independently accepts. This updates future routing only; it does not rewrite historical task attribution, grant operational authority, or claim a model benchmark advantage.
>
> This routing document supersedes the active role assignments in the 2026-11-16 routing snapshot. Historical Controller decisions, task cards and accepted receipts remain immutable. Latest project status must be taken from local Controller decisions, not inferred from this role document.

**Canonical references:** [Current progress audit](V070_PROJECT_PROGRESS_AUDIT_AND_CLOSURE_ROADMAP_20261116.md) · [Active role matrix](../roles/V070_ACTIVE_ROLE_MATRIX_20261111.md) · [Controller 0-C role](../roles/V070_CONTROLLER_0C_ROLE_20261111.md) · [1-A advisor role](../roles/V070_CHATGPT_1A_STRATEGIC_ADVISOR.md) · [Current 0-C startup](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261118_REAL_MVP_CONTINUATION.md) · [Current 1-A startup](../../prompts/v0.7/V070_NEW_CHAT_1A_20261118_REAL_MVP_CONTINUATION.md) · [Prompt Copy Card Standard](V070_PROMPT_COPY_CARD_STANDARD_20261111.md).

## 1. Controlling role separation

| Role | Default responsibility | Explicit boundary |
|---|---|---|
| Owner | Product scope, routine delegated L0 authority, separate Source L1-A, Venue WATCH L1-B and Feishu L1 approvals, L2 privileged/financial decisions | A prompt or worker delivery is not an approval or Controller acceptance |
| Controller 0-C | Sole engineering queue owner, task classifier, architecture gate, dispatcher, independent evidence reviewer and scope-specific acceptance authority | No worker PASS is self-acceptance; no L1/L2 authority may be inferred |
| **Codex GPT-6.2 Astra** | Complex architecture analysis: system decomposition, architecture alternatives, trust boundaries, threat models, time/source/custody contracts, cross-module invariants and high-consequence technical decisions | Produces design analysis and recommendations; does not own the engineering queue, issue grants, self-accept implementation or bypass 0-C |
| **Codex GPT-6.2 Sol** | Primary complex engineering executor: stateful and multi-file implementation, persistence, Source/custody/retention, clock adapters, Q0BC/Producer/Outbox, WAL, concurrency, crash recovery and cross-platform integration | Implements the accepted/Controller-approved design; uses isolated worktrees and fail-first tests; no self-acceptance or external operations without separate grant |
| Gemini 4 Hydrogen | Simple bounded L0 work: fixtures, deterministic tests, documentation, mechanical edits and isolated low-risk QA | No independent architecture/trust decisions; no core custody, clock, authorization or Outbox state-machine changes solely because a patch appears small |
| ChatGPT 1-A | Independent Owner-facing product, strategy, architecture and quantitative advisor; audits status, challenges roadmap and prepares complete prompts/docs on explicit request | Not 0-C; no dispatch, acceptance, live Source, Feishu, deployment, account access or trading |
| Q0BC Producer | Sole canonical plan/eligibility/transition and Outbox writer | No second dispatcher or direct scheduler mutation |
| Q0F / Feishu | Mock adapter and later separately authorized provider channel | Real send requires its own L1 and UNKNOWN handling; provider ACK is not human read |
| Source / Custody | Provenance, rights, time, exact bytes, identity, retention and admission | Real Source remains blocked until exact source gates and grants pass |
| Shadow / dashboard | Append-only observations, immutable scan roster, honest denominators and forward monitoring | Static fixtures and offline acceptance are not forward qualification or Alpha |

**Historical attribution:** the 2026-11-17 Track A L1-A architecture review was completed and accepted under the historical Codex GPT Sol Max assignment. Its evidence and reviewer attribution remain unchanged. Sol Max is not a separate active default route. Future complex architecture analysis routes to GPT-6.2 Astra unless the Owner explicitly changes it.

No future standing Gemini Orchestrator. Model routing is an Owner-selected execution policy, not a comparative capability benchmark.

## 2. Complexity routing and work sequence

- **Hydrogen / simple L0:** one narrow, independently testable outcome; no contract or trust-boundary change; bounded write surface; reversible and offline.
- **Astra / architecture-critical:** architecture alternatives, threat models, cross-module invariants, external trust assumptions, failure semantics, high-consequence design forks or a decision that changes the project critical path.
- **Sol / core implementation:** implementation of an approved architecture across interacting modules; state/persistence, clock/source semantics, identity, authorization, crash/restart, concurrency, Outbox or cross-OS behavior.
- **0-C / governance and acceptance:** decides task class and executor, owns the only engineering queue, checks conflicts and scope, dispatches, independently reviews evidence and issues scoped acceptance.
- **1-A / independent advice:** challenges product direction and technical reasoning for the Owner; does not create a parallel queue.

Default sequence for architecture-heavy work:

1. GPT-6.2 Astra produces a bounded architecture decision, threat model or implementation contract.
2. Controller 0-C reconciles the design against Owner scope, existing receipts and permission boundaries, then decides whether and how to dispatch.
3. GPT-6.2 Sol implements the accepted design in one isolated core worktree.
4. Controller 0-C independently reviews the evidence and issues or withholds scoped acceptance.

For routine implementation with no meaningful architecture fork, 0-C may route directly to Sol. For genuinely simple independent fixtures/docs/QA, 0-C may route to Hydrogen. Astra's recommendation is not a dispatch, grant or acceptance.

Never route by line count or apparent patch size. A one-line clock, authorization or Outbox change may be high risk. If Sol is unavailable, preserve a stateful core task as pending; do not silently downgrade it to Hydrogen. One active core implementation owner at a time.

## 3. Latest verified stage and handoff context — 2026-11-17

The following is a compact reconciliation of the latest local Controller receipts. It is not a replacement for the source receipts.

- **Q0BC COMMIT ambiguity:** scoped offline L0 accepted. Controller independently checked the 2,759-file V2 seal and 257 WSL symlink targets; the retained JUnit gate contains 87 cases with zero failures/errors/skips. Controller did not independently rerun all 87 tests. Production WAL, physical power-loss durability, native NTFS and coordinated journal/database rollback remain unqualified.
- **P1-B ADR-01 V2:** accepted as design-only, with no L1 authority. RAW-only A and WATCH derivation B remain non-transitive.
- **P1D03:** accepted only for a static 12-symbol disabled-source monitor and synthetic fixture separation. It is not a live scanner; real screened denominator remains zero.
- **Protected-window design:** accepted design-only. PROTECTED_2024_2026 and FINAL_HOLDOUT_2026 exclusions remain active; no November 2026 bar exception exists.
- **Pre-grant readiness:** accepted offline/documentary only. Both unsigned A/B envelopes remain unapproved; endpoint allowlist is empty.
- **TIME_ONLY one-shot:** accepted isolated synthetic L0 only (15 tests, 60 negative refusal cases). TIMEONLY-F01 report-label ambiguity remains a follow-up; TIMEONLY-F02 transport/durability guarantees remain UNKNOWN.
- **Hydrogen Longrun:** P0–P4 accepted offline L0 only. Official documentation confirms the documented /fapi/v1/time shape and weight, but not sampling/cache semantics, authenticated UTC, operator rights or a live grant.
- **Hydrogen report-contract hardening:** dispatched for manual Owner forward; the Controller dispatch record says the worker had not been started by Controller. Check the actual workspace and latest handoff before any new dispatch.
- **Track A L1-A architecture review:** accepted offline architecture review with live L1-A NO-GO/HOLD_UNPROVED. The subsequent Owner/0-C rights-applicability screening is HOLD_UNPROVED with Owner materials pending.

Current gates remain: PUBLIC_SOURCE_L1=NOT_AUTHORIZED; VENUE_WATCH_L1=NOT_AUTHORIZED; approved endpoint allowlist empty; SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; CLOCK_UNTRUSTED=true; REAL_INDEPENDENT_UTC_QUALIFIED=false; SQLITE_WAL_ENGINE_NOT_QUALIFIED=true; REAL_FEISHU_SEND=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; P2/P3/M3=HOLD.

## 4. Current work ownership and next routing

1. **Owner:** provide controlled references for the nominated actual operator, physical region, permitted outbound route, exact current USD-M terms or written authorization, COLLECT/RETAIN scope, audience, retention/purge and any qualified applicability opinion. Do not place identity documents or private contract text in ordinary chat.
2. **Controller 0-C:** review only the supplied evidence. Keep HOLD_UNPROVED if facts are incomplete. No automatic host task, real API request or L1-A grant follows.
3. **Hydrogen:** complete TIMEONLY-F01 report-contract hardening only if the task has been manually forwarded and the isolated workspace exists. Check status before dispatch; do not duplicate an existing worker.
4. **Astra 6.2:** use for the next genuinely consequential architecture decision or threat-model review. Do not repeat the already accepted Sol Max L1-A architecture review.
5. **Sol 6.2:** use for a specifically scoped core implementation after 0-C confirms prerequisites and no overlapping core worker. Do not start another synthetic expansion merely to create activity.

The next hard gate is external operator/rights/applicability evidence, not another round of generic offline fixtures. A later host/TLS/custody task must have its own exact scope and must not be treated as permission to perform a real market request.

## 5. Concurrency and dispatch discipline

- One active core implementation owner at a time.
- Astra architecture analysis and Controller read-only review may proceed in parallel only when they do not mutate the same baseline or create competing instructions.
- No duplicate dispatch when a task card and completed handoff already exist.
- A dispatched task may be PENDING, RUNNING, DELIVERED_PENDING_REVIEW or ACCEPTED; these states must not be conflated.
- Do not edit historical Controller decisions. Create a new supplemental decision when reconciling stale dispatch metadata.
- Every worker task specifies task ID, exact baseline pins, isolated worktree, allowed/prohibited files, fail-first cases, positive/negative/boundary tests, exact commands, STOP conditions, deliverables, reviewer and Controller gate.
- Worker PASS ≠ independent review PASS ≠ Controller scoped acceptance ≠ real operation.

## 6. Permission boundaries

- Routine offline L0 engineering, fixtures, tests and documentation are delegated; do not create repetitive SHA/approval loops.
- L1-A is an exact, bounded public RAW-only capture grant. It does not authorize derivation.
- L1-B is a separate exact, bounded Venue WATCH derivation grant. It does not promote to strict Source/E1.
- Feishu send is a third separate L1 grant.
- Privileged host changes, private accounts, financial/destructive actions and protected-history access require their own L2 decision.
- No real Source, DNS/NTP/NTS, Feishu, private account, order or trade operation follows from a worker prompt.

## 7. Project invariants

Keep, until separately accepted:

- CLOCK_UNTRUSTED = true
- REAL_INDEPENDENT_UTC_QUALIFIED = false
- SOURCE_QUALIFIED = false
- SHADOW_QUALIFIED = false
- SQLITE_WAL_ENGINE_NOT_QUALIFIED = true
- REAL_FEISHU_SEND = false
- ECONOMICALLY_VALIDATED = false
- ALPHA_CLAIMED = false
- execution_authority = false

VENUE_TIME_ONLY and WATCH_ONLY are separate evidence/output dimensions. They do not replace independent UTC or the four non-transitive authority modes in P1-B ADR-01.
