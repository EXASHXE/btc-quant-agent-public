> **LATEST OWNER MODEL ROUTING — 2026-11-14 (SUPERSEDES FUTURE ORCHESTRATOR ROUTING):** **Remove Gemini Orchestrator as a role for all newly assigned stages.** Future execution: **Gemini 4 Hydrogen = simple, bounded, low-risk engineering and tests (L0-S)**; **Codex GPT Sol = complex / multi-module / stateful core engineering (L0-M and L0-X implementation)**; **Codex GPT Sol Max = specialist architecture/review when specifically required**; **Controller 0-C = independent acceptance**. **Exception: the already assigned P1C04 task retains its original Gemini Orchestrator (Argon + Hydrogen) instructions unchanged until completion and Controller review.** This exception is not renewed and does not permit orchestration for P1D or later. Assign one stage at a time. Historical notes below remain evidence of the earlier routing and are superseded for future dispatch.

> **OWNER UPDATE — 2026-11-14 / ONE STAGE AT A TIME:** Gemini may run **Orchestrator with Argon (design, decomposition, review) + Hydrogen (bounded implementation/tests)** inside one explicitly scoped next-stage task, particularly P1C04 disabled local TLS Mock; Controller 0-C still owns final acceptance and no subsequent phase dispatch. This is a scoped teamwork option, **not** blanket promotion of Hydrogen to high-risk core developer or permission for live APIs. Codex Sol remains principal core engineer and Sol Max complex architecture escalator. P1C03 detached synthetic offline acceptance is now confirmed. See [current scoped execution plan](V070_P1C03_ACCEPTANCE_AND_ONE_STAGE_AT_A_TIME_ROADMAP_20261114.md).

> **OWNER ROUTING UPDATE — 2026-11-14 / CODEX QUOTA RESTORED:** Active/default assignments are now **Astra = complex architecture and custody/time/source design**, **Sol = primary medium/high-risk multi-module engineer**, **Gemini 4 Hydrogen = bounded isolated tests/fixtures/docs/mechanical changes**, **Controller 0-C = independent review**, **1-A = Owner-facing planning**. P1C01 accepted; P1C02 F01–F03 independently reproduced and NOT accepted; latest work plan: [P1C02→L1 restored-quota plan](V070_P1C02_TO_L1_REPLAN_CODEX_RESTORED_20261114.md). Parallel first wave: Astra read-only F02 ADR, Sol F01/F03 + fail-first F02 then implement agreed design, Hydrogen isolated tests-only. Old Hydrogen L0-M exception policy no longer default. All tasks prompt-only, none dispatched; real network/Feishu/clock changes remain separately gated.

> **CURRENT EXECUTION NOTE — 2026-11-13:** Q0A5 overall G0–G4 now has Controller `ACCEPT_Q0A5_FULL_L0_OFFLINE_SCOPED`. Details: [full-L0 closure + Source readiness](V070_Q0A5_FULL_L0_CLOSURE_AND_P1_SOURCE_READINESS_20261113.md). G1/G2/G3 synthetic code is sealed; next engineering is P1 trust and data Source preparation. Hydrogen may implement only a **bounded isolated decode-only test-led `win_clock.py` repair** and simple fixtures/docs, while genuine clock authority, Source request/retention/ledger semantics and Feishu/Outbox changes remain Sol/Astra-class with Controller design control. The local Windows host `w32tm` status is UNQUALIFIED (Leap=3, Local CMOS Clock), and no worker is authorized to change host time/services or make real Binance/Feishu calls from this doc.

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

## 5. Current project state and critical path — latest 2026-11-13 FIX-01

[Q0A5 G2/G3 progress and primary evidence](V070_Q0A5_G2G3_FIX01_PROGRESS_20261113.md) is the active stage report. Earlier pre-FIX03 Q0A4 and initial Q0A5 planning snapshots are historical; do not route an already completed FIX03 again.

- M0 Q0BC/Q0R, M1 three-symbol E2E and Q0F Mock have Controller `ACCEPT_OFFLINE_SCOPED`; Q0A3 `ACCEPT_FIXED_OFFLINE_SUBSET`; Q0A4 FIX03 `ACCEPT_OFFLINE_SCOPED_FIX03`. All are limited offline scopes.
- Q0A5 unified three-symbol offline runner exists; original Controller decision `ACCEPT_PARTIAL_L0_WORK / NEEDS_SPECIFIC_G2_G3_FIX / WINDOWS_NATIVE_BLOCKED` was issued **before** the latest correction.
- **FIX-01 engineering delivered:** C01 independent `SCAN_SLOT_SCHEDULED` Shadow denominator, C02 stable closed-bar-derived `cycle_id`, C03 Producer-authoritative expiration (no scheduler direct `UPDATE outbox`). Worker: fail-first 10 FAIL/1 PASS, targeted post-fix 12/12 PASS, WSL full 28/28 PASS, M1 EXIT 0, unified mock demo EXIT 0. Windows native 6 PASS/22 SKIP. The worker UI self-reports `Gemini 4 Hydrogen (High)` but the underlying exact model ID is unverified.
- **Current stage state:** `PASS_G2G3_FIX_PENDING_CONTROLLER_ACCEPTANCE`. A fresh post-FIX01 0-C decision was not found when docs were updated. Worker PASS must not become automatic acceptance.
- **G1 remains BLOCKED:** 16 Windows tests skip for missing offline `jsonschema` wheels, six more skip because SQLite WAL on `\\wsl.localhost` UNC/9p is unsupported. Verify on Windows-local NTFS with proper offline dependencies; do not count skips as pass.
- Full Q0A5 L0 approval, genuine Source and Feishu L1, qualified Shadow/economic results are not established. Argon Q0A4 and Opus M2 reports were already consumed for their audit scopes; do not invent fresh capacity.

**Next 0-C priority** is a scoped skeptical post-FIX01 review of C01/C02/C03 actual code and JUnit/SQLite evidence with replay, missing-slot, transactional crash, owner-generation, TTL and UNKNOWN falsifiers. Then finish native Windows G1 parity and the full unified offline Controller stage decision. This is primarily a **Controller acceptance task**, not another broad engineering rewrite.

**Future task distribution remains:** Hydrogen SIMPLE bounded work; Sol MODERATELY COMPLEX integration, Source and Producer corrections; Astra COMPLEX architecture analysis if there is a real system-design dispute. The past FIX-01 reported Hydrogen authorship is factual, but does not override future complexity routing. Preserve one P0 work queue.

**Invariant status:** SOURCE_BLOCKED=true; SOURCE_QUALIFIED=false; SHADOW_QUALIFIED=false; ECONOMICALLY_VALIDATED=false; ALPHA_CLAIMED=false; execution_authority=false; REAL_FEISHU_SEND=false. No public market/Feishu access or account/trade authority follows from these tests.

## 6. Delegation, boundaries and handoff

Owner's 2026-11-11 L0 delegated offline coding/test authority remains active for 0-C. No repeated SHA, mock fixture, code-review or normal docs-branch authorizations. User-visible worker prompts may be manually forwarded by Owner; a drafted prompt is not proof of dispatch.

Separate bounded L1 Owner decisions are required for first real public market Source operating envelope and first real Feishu destination/secret/send. L2 privileged, private/account, destructive, financial and protected-history actions remain explicitly gated. No autonomous trading.

**Next 0-C action:** independently review the Q0A5 G2/G3 FIX-01 worker deliverable and issue a new scoped Controller decision from actual code/tests, preserving Windows G1 BLOCKED. Then route Windows-local NTFS/offline dependency engineering to Sol where moderate, with Hydrogen limited to simple preparatory checks; Astra remains architecture lead when a genuine hard design choice arises.