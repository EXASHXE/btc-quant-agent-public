# Quant v0.7.0 — Engineering Model Task Routing (Owner revision 2026-11-13)

**Status: CONTROLLING OWNER MODEL-ROLE DECISION.** This document supersedes the executor assignment in [Hydrogen migration and audit triage](V070_GEMINI4_HYDROGEN_EXECUTOR_MIGRATION_AND_AUDIT_TRIAGE_20261113.md) and the historical [Flash-first temporary policy](V070_TEMP_GEMINI_FLASH_EXECUTOR_POLICY_20261112.md), **only for future model-to-task routing**. It does not change Controller acceptances, source authority, access grants or scientific status.

## 1. Current three-tier assignment

| Work class | Default executor / lead | Examples | Boundary |
|---|---|---|---|
| **L0-S: simple, narrow, low-risk execution** | **Gemini 4 Hydrogen**, when locally selectable and smoke-tested | Small isolated code edits, mechanical refactoring without contract changes, fixtures, documentation, deterministic unit tests, static validation and clearly specified one-file bugs | No independent architectural decisions, external operation, source qualification or self-acceptance |
| **L0-M: moderately complex engineering** | **Codex GPT Sol**, when capacity is actually available | Multi-file implementation, bug fixes touching interfaces, test-led integration, SQLite persistence/recovery, Source/Outbox/notification seam changes and Windows/WSL cross-platform engineering | Work to a Controller-approved design/contract, fail-first tests, non-author review for high-risk changes |
| **L0-X: complex architecture and technical analysis** | **Codex GPT Astra**, when capacity is actually available | Cross-module architecture, causality and time/source trust analysis, state-machine redesign proposals, hard concurrency/security tradeoffs, release-gate design and deep root-cause investigations | Astra leads design/review, **not** independent Controller acceptance; Sol implements approved architecture, Hydrogen only receives decomposed simple subtasks |

**Controller 0-C** owns queue, task complexity classification, design choices, worktree ownership, integration, independent review, acceptance and external gate escalation. **ChatGPT 1-A** independently challenges strategy/product/architecture, but does not dispatch a competing queue or sign acceptance.

The Owner's latest instruction is **Hydrogen → simple; Sol → moderately complex; Astra → complex architecture analysis**. The previous "Hydrogen primary for all L0 engineering" default is superseded. Model hierarchy is a routing preference, not a claim of benchmark superiority.

## 2. Availability / quota rules

- Previous local Antigravity CLI scan (2026-11-13) did **not** list Gemini 4 Hydrogen. This is an evidence snapshot, **not** proof of global unavailability. Before the first Hydrogen job verify the actual interface model ID, file-edit/test tools and one isolated offline no-business-network smoke receipt.
- When Hydrogen is unavailable, **Gemini 3.8 Flash is fallback for L0-S only**, not an automatic promotion to L0-M or L0-X.
- When Sol is quota-blocked, preserve the L0-M task as PENDING_CAPACITY or decompose only genuinely independent L0-S subtasks to Hydrogen/Flash. Do not silently downgrade architecture or high-risk implementation merely to keep an agent occupied.
- When Astra is unavailable, 0-C may plan or recommend a review; do not represent a lower-tier model as an Astra-equivalent architecture acceptance.
- Reserve scarce non-author reviews for specific unresolved high-consequence defects. Completed Argon Q0A4 and Opus M2 assessments reported in the 2026-11-13 triage are treated as **already consumed for planning**; never claim fresh capacity without new evidence.
- If an agent changes role mid-task, freeze the base revision, transfer tests/failure evidence and explicitly assign new author/reviewer; no anonymous handoff.

## 3. Complexity classifier: deterministic routing, not marketing

0-C records one task's **scope, state/authority impact, failure blast radius and review needs**:

**Simple (Hydrogen):** one independently testable narrow outcome; bounded write surface; existing contract unchanged; reversible; no trust/clock/ledger/transaction/external-send semantics modified.

**Moderate (Sol):** multiple interacting files, persistence, interface or causal semantics, cross-OS integration, concurrency/retries, or an existing high-risk module requiring native tests. Examples: Q0A4 ledger-to-manifest cross-check, E1 batch exception isolation, Windows Producer persistence and Q0F pre-send changes.

**Complex architecture (Astra):** changes or adjudicates source-of-truth ownership, data provenance/clock authority, multi-stage state machines, real-channel operating architecture, failure models, Alpha/scientific validity or release gates. Astra provides design alternatives, constraints, falsifiable decision criteria and minimal change plan; 0-C approves; Sol implements; Argon/other non-author reviewer verifies where justified.

Never assign a task solely from estimated token count or lines of code. A one-line change to an Outbox retry gate or clock trust rule is **not** automatically simple.

## 4. Task prompt quality and review

Every 0-C worker assignment (including simple Hydrogen work) states: task ID; verified current baseline; exact objective and observable outcome; source-of-truth paths; base revision and exclusive worktree; allowed/prohibited edits; unchanged interfaces; step-by-step work; positive/negative/boundary tests; actual commands; failure/rollback/STOP criteria; no-business-network/protected-data guard; deliverables; reviewer; Controller decision gate.

For L0-M/L0-X add adversarial cases covering causality, 120-second combined run and clock session, raw HTTP status/instrument validation, trace/ledger rederivation, quote freshness, single Q0BC Outbox, crash/idempotency/UNKNOWN, real send barrier and Source vs NO_SETUP classifications as relevant. Prefer fail-first reproduction and narrow patches; count SKIP separately from PASS.

**Author PASS ≠ independent reviewer PASS ≠ Controller scoped acceptance ≠ real operation.** A worker never self-signs. Do not rerun immutable historical baselines solely to inflate test counts.

All Owner-visible generated prompts remain subject to the [working full-text Copy Prompt card standard](V070_PROMPT_COPY_CARD_STANDARD_20261111.md), including complete untruncated payload and truthful NOT DISPATCHED state where appropriate.

## 5. Current project state and critical path

Reconcile latest local Controller decisions before every material assignment. At the 2026-11-13 triage snapshot:

- M0 Q0BC positive semantics, M1 three-symbol synthetic E2E and Q0F adapter: Controller **ACCEPT_OFFLINE_SCOPED**. Q0A3: **ACCEPT_FIXED_OFFLINE_SUBSET**.
- Q0A4 had historical **ACCEPT_OFFLINE_SCOPED**, subsequently restricted for M2 reliance due to **Argon F-01 ledger/raw response rederivation** and **F-02 cross-stage bracket intersection** concerns. Original author 64/64 WSL and 61 PASS/3 SKIP Windows are preserved; they do not dismiss new independent findings.
- First needed correction is a task **routed to Sol as L0-M** for real code changes involving Source trust. Astra reviews the design only if 0-C identifies a genuine architectural choice; Hydrogen may do preparatory fixtures, test inventory or mechanical verification only.
- Subsequent L0-M: finish native Windows three Producer skips without weakening coverage; E1 per-symbol exception isolation; unified Q0A4→Q0BC→Q0F→Shadow synthetic offline validation; fresh-gate/1 msg/s queue-drain behavior. Complex cross-module M2 architecture decisions go to Astra.
- No automatic new Argon/Opus opportunity. Reuse reviewed findings with independent proof, not duplicate audits.

**Invariant status:** SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false. No authorized live source, private accounts or orders from this change. Protected history and FINAL_HOLDOUT remain restricted.

## 6. Delegation, boundaries and handoff

Owner's 2026-11-11 L0 delegated offline coding/test authority remains active for 0-C. No repeated SHA, mock fixture, code-review or normal docs-branch authorizations. User-visible worker prompts may be manually forwarded by Owner; a drafted prompt is not proof of dispatch.

Separate bounded L1 Owner decisions are required for first real public market Source operating envelope and first real Feishu destination/secret/send. L2 privileged, private/account, destructive, financial and protected-history actions remain explicitly gated. No autonomous trading.

**Next 0-C action:** reconcile local Argon/Opus findings and any newer Q0A4 Controller acceptance; classify the smallest remaining ledger/clock trust correction as L0-M; provide a detailed **Sol** prompt if available, otherwise mark PENDING_CAPACITY while routing only safe preparatory L0-S work to **Hydrogen** after actual availability verification. Escalate any cross-module redesign decision to **Astra**.