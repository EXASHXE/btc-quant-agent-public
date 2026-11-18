# v0.6.5 — Controller B Execution-First Policy R5

<!-- R8-ARGON-STATE-20261022 -->

## Current R8 State — 2026-10-22

All five R8-8/Argon tasks completed successfully; do not relaunch them. R8-7's frozen X-only baseline is negative and closed. The only immediate work candidate is `V065-R8-NEXT-SOURCE-FEASIBILITY-01`, state `PREPARED_NOT_DISPATCHED`; follow the [source-feasibility plan](V065_NEXT_GATE_LIQUIDATION_FLOW_SOURCE_FEASIBILITY_PLAN_20261022.md). Its scope is metadata-only. No market payload, outcome, backtest, merge or Alpha claim is authorized. The five R8 worktrees remain isolated; passing synthetic tests do not establish source completeness or receiver PIT.

<!-- /R8-ARGON-STATE-20261022 -->
**Purpose:** maximize useful implementation throughput, historical-data coverage, effective research samples, and credible BTCUSDT 4–24h evidence for a personal research project. This is an execution-routing policy, not a grant of source rights, outcome access, or trading authority.

## Default loop

`Controller B → Codex or Antigravity → focused evidence → Controller B acceptance`.

- Codex and Antigravity (Agy/Gemini) are the default implementation executors for data inventory/acquisition, archive QA, adapters, research pipelines, sample diagnostics, tests, and documentation.
- Controller B owns prioritization, task isolation, acceptance, and the owner-facing dashboard.
- Keep at most two active tasks only when their write paths are independent; otherwise sequence them.
- Routine code changes need focused changed-invariant tests, runnable commands, and inspectable outputs—not a mandatory independent audit.
- 1-A is on demand for consequential source rights/PIT, financial/execution semantics, production migration, material code-integration risk, or release decisions.
- 2-R is on demand when new evidence justifies a genuinely differentiated, falsifiable mechanism. 2-C is on demand to challenge one material novelty/causal/economic claim. Neither is a compulsory engineering stage.
- Avoid repeated review cycles with no new evidence. After one focused corrective pass, state the exact blocker or move to the next informative task.
- Preserve owner files, active collectors, protected roots, and parallel-agent outputs. Never use destructive cleanup/reset to make a workspace appear clean.

## Stage-closeout commit/push rule (Owner decision, 2026-10-20)

On acceptance of a completed implementation/research stage, **commit and push the scoped deliverable to the remote executable branch**; do not leave completed stage code exclusively in the owner's local untracked/dirty working tree. Keep this separate from documentary updates to `docs/engineering`.

1. Refresh local `HEAD`, `git status`, remote `refs/heads/v0.6.5`, active writers and stage receipts. Re-check writer ownership and avoid duplicate work.
2. Stage **only** explicit, stage-related code/test/doc paths plus the minimal dependency closure. Scan staged paths/content for private Owner/archive/Forward/Final/OOS data, credentials, large artifacts, temporary test files and private links. Do not stage unrelated pre-existing dirty user files or use reset/clean/stash/force-push.
3. Run focused changed-invariant tests, reproduce the stage terminal verdict, perform appropriate secret/scope inspection, and document exceptions. Full CI, workflow runs and unrelated broad Ruff failures **may be nonblocking for now** under the owner's instruction; substantive source/PIT, safety and scope blockers are never waived by skipping CI.
4. Commit the scoped stage checkpoint with terminal verdict, no-alpha/no-live boundaries and relevant source/test dependencies; push normally to the intended remote branch if authorized, subject to normal fast-forward checks and branch protections. On a remote divergence or permission failure, do not force-push; report the exact blocker.
5. **Confirm published remote SHA** (not merely local commit SHA). Report commit URL, file scope, tests, terminal decision and remaining uncommitted work. Distinguish source-code publication from data rights, authenticated source clock, real-return scope or trading permission.

2026-10-20 precedent: `v0.6.5@a4e28c0c7952a84ea77597f18c72dac30b6b3723` contains 89 scoped offline R1–R3 code/test files; 472 relevant tests passed using `pytest --import-mode=importlib` (duplicate filenames), and R2/R3 focused Ruff passed. Preexisting modified docs and unrelated dirty work were not included.

## Verification ladder

- **Docs-only:** inspect changed paths, links, and diff scope.
- **Routine offline engineering:** run focused tests for changed invariants, and relevant lint/format checks if available.
- **Offline source/clock prototype:** challenge positive and negative boundaries and keep caller-claimed evidence separate from authenticated evidence.
- **Actual source/PIT admission, private outcomes, production cutover, TESTNET/LIVE, or funds:** require separately scoped authority and the appropriate consequential review. A passing synthetic test is not admission.

## Current work priority

R1/R2 data expansion and the R8-8 five-task packet are completed; do not relaunch their historical jobs. The current candidate is one metadata-only source-feasibility task for the forced-liquidation flow-exhaustion mechanism, documented in [Next Gate — Liquidation-Flow Source Feasibility](V065_NEXT_GATE_LIQUIDATION_FLOW_SOURCE_FEASIBILITY_PLAN_20261022.md). It is `PREPARED_NOT_DISPATCHED`, not running. First establish documented field availability, lawful source route, native units, coverage metadata and timestamp/receiver-clock evidence. No market payload reads, outcome access, backtest, live collection or integration are included. A blocked or inconclusive source result closes this route or identifies one missing piece; do not automatically pivot to R8-C/R8-D.

Check receipts before dispatching. Any future public-data acquisition must be separately scoped, terms-reviewed, resumable, hash-verified and bounded by an explicit disk budget. Do not start a live collector or use private accounts.

## Conversation and task-card contract — mandatory across all roles and executors

Follow the [project-wide prompt-card standard](V06_CHATGPT_OUTPUT_UI_AND_TASK_CARD_STANDARD_R1.md). This rule applies to every role document and every executor prompt; it is not a Controller-only UI preference.

- Respond to the owner in **Chinese by default**, unless the owner explicitly asks for English conversation.
- Write repository role docs, project docs, handover prompts, and runnable execution prompts in **English by default**, unless the owner explicitly requests another language.
- Render at most two compact task cards. Each card shows task title/ID, assignee, priority/status, one-sentence objective, and concise acceptance criteria.
- Each task card has exactly one **Copy prompt** button. The complete prompt is passed only to the button's copy action. Do **not** print the prompt body in visible text, a code block, a writing block, a collapsible panel, or elsewhere in the message.
- If a working copy button is unavailable, state the limitation and ask before displaying the full prompt as a fallback. Never claim the button worked until the host handles the action.

## Non-negotiable boundaries

`P3_ACCESS_SCOPE_HOLD / SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / NO_ALPHA_ESTABLISHED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.

This policy does not authorize protected H39/H40/H41/Forward/Final/OOS access, retroactive receiver-PIT claims, Alpha promotion, TESTNET/LIVE, orders, or funds operations.
