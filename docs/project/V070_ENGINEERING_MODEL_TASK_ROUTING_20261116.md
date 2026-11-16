# Quant v0.7.0 — Engineering Model and Task Routing (Current 2026-11-16)

> **Current project baseline:** [Nov 16 progress audit and accelerated Real MVP roadmap](V070_PROJECT_PROGRESS_AUDIT_AND_CLOSURE_ROADMAP_20261116.md) · [MVP Closure Home](V070_MVP_CLOSURE_HOME_20261111.md) · [Current 0-C startup](../../prompts/v0.7/V070_NEW_CHAT_CONTROLLER_0C_20261116_REAL_MVP_ACCELERATION.md) · [Prompt Copy Card Standard](V070_PROMPT_COPY_CARD_STANDARD_20261111.md).

## 1. Controlling role separation

| Role | Default responsibility | Explicit boundary |
|---|---|---|
| Owner | Product scope, routine delegated L0 authority, separate Source L1-A, Venue WATCH L1-B and Feishu L1 approvals, L2 privileged/financial decisions | A prompt or worker delivery is not an approval or Controller acceptance |
| Controller 0-C | Sole queue owner, task classifier, architecture gate, dispatch authority, independent evidence reviewer and scope-specific acceptance | No worker PASS is self-acceptance; no L1/L2 authority may be inferred |
| Codex GPT Sol | Core stateful/multi-file engineering: Source, custody, retention, clock adapters, Q0BC/Producer/Outbox, WAL, cross-platform integration and recovery | Implement Controller-approved contracts; fail-first tests; no self-acceptance or external operations without separate grant |
| Gemini 4 Hydrogen | Simple bounded L0 work: fixtures, deterministic tests, docs, mechanical edits and isolated low-risk QA | No independent trust/architecture decisions; no core custody/clock/Outbox state machine changes solely because a patch is small |
| Codex GPT Sol Max | Specialist architecture/security/provenance review when a consequential design fork exists | Separate independent reviewer session when required; advisory result is not Controller acceptance and does not own a competing queue |
| ChatGPT 1-A | Independent Owner-facing product/strategy/architecture/quant advisor; audits status and challenges roadmap; prepares complete prompts and docs on explicit request | Not 0-C; no dispatch, acceptance, live Source, Feishu, deploy, account access or trading |
| Q0BC Producer | Sole canonical plan/eligibility/transition and Outbox writer | No second dispatcher or direct scheduler mutation |
| Q0F / Feishu | Mock adapter and later separately authorized provider channel | Real send requires its own L1 and UNKNOWN handling; provider ACK is not human read |

No future standing Gemini Orchestrator. Historical Argon+Hydrogen P1C04 collaboration remains a one-time historical assignment. Sol Max is a specialist reviewer, not a parallel Controller. Model routing is an execution preference, not a benchmark claim.

## 2. Complexity routing

- **Hydrogen / L0-S:** one narrow independently testable outcome, no contract or trust change, bounded write surface, reversible and offline.
- **Sol / L0-M or stateful L0-X implementation:** interacting modules, state/persistence, clock/source semantics, identity, authorization, crash/restart, concurrency, Outbox or cross-OS behavior.
- **Sol Max / specialist review:** a separate design review only where independent architecture, threat-model or provenance assessment materially changes a high-consequence decision.
- **0-C:** decides whether a task is simple, core or architecture-critical, owns the only active core queue and accepts the result.

Never route by line count or apparent patch size. A one-line clock/authorization/Outbox change may be high-risk. If Sol is unavailable, preserve the core task as pending or decompose only genuinely independent fixtures/QA to Hydrogen; do not silently downgrade a stateful trust task.

## 3. Current evidence state and ownership

As of 2026-11-16 local Controller decisions:

- Q0A5 G0–G4 synthetic L0 is accepted.
- P1C04 Fix01 is ACCEPT_OFFLINE_SCOPED, mock-only.
- P1D01 dual-platform L0 is accepted within its scope; SQLITE_WAL_ENGINE_NOT_QUALIFIED remains true.
- P1D02 Clock Trust L0 is accepted; REAL_INDEPENDENT_UTC_QUALIFIED remains false.
- P1D02B offline NTS contract is accepted with native NTS client hold.
- P1-B Venue WATCH admission Fix01 and detached Venue Time WATCH-only L0 are SCOPED_ACCEPTED.
- P1-B ADR-01 V2 remains proposed. Sol Max's independent review package is delivered with NEEDS_SPECIFIC_ARCHITECTURE_FIX recommendation, awaiting 0-C reconciliation. Do not repeat the review task.
- P1D03 formal disabled-source Controller acceptance is not yet recorded. The existing package contains a static disabled-source review only.
- Public RAW L1-A, Venue WATCH L1-B and Feishu L1 remain not authorized.

See the [current evidence ledger](V070_PROJECT_PROGRESS_AUDIT_AND_CLOSURE_ROADMAP_20261116.md).

## 4. Next task routing

1. **0-C read-only review:** reconcile Sol Max's sealed ADR review against the later P1-B Fix01 acceptance; decide the design-only ADR V2 disposition. Independently inspect the existing P1D03 disabled-source evidence and issue a scoped decision if sufficient. This is Controller work, not a new worker queue.
2. **Next Sol core task candidate:** canonical Q0BC COMMIT ambiguity L0. The existing miniature WSL VFS test recorded an xSync error while the candidate pair remained visible after reopen; it did not test conflicting payload under the same stable ID or the canonical Q0BC path. Require stable ID + payload fingerprint, Ledger/Outbox pairing, UNKNOWN, recovery fence and no automatic dispatch/retry of UNKNOWN. Do not claim power-loss or production WAL qualification.
3. **Sol offline preparation:** exact L1-A raw-capture grant package and L1-B separate WATCH derivation package, only after the ADR disposition. No real requests or grants are implied.
4. **Hydrogen QA:** only isolated fixture matrices and deterministic tests that do not mutate Sol's active worktree or accepted baselines.
5. **Optional clock feasibility:** WSL-only Chrony/NTS feasibility may be planned as a separate L0 lane. No live NTS/DNS/UDP request, package installation or system-time mutation is implied. Independent UTC is deferred from the Venue WATCH critical path, not waived from strict Source/retention qualification.

## 5. Concurrency and dispatch discipline

- One active core implementation owner at a time.
- Controller read-only audits and document reconciliation may proceed while a worker runs if they do not mutate the same baseline.
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
