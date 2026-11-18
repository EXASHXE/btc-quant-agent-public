# quant v0.6.5 — Five-Session Routing Matrix · Execution-First R5

<!-- R8-ARGON-STATE-20261022 -->

## Current Dispatch State — 2026-10-22

R8-8, R8-A, R8-B, R8-C and R8-D are complete in isolated worktrees. The only prepared next task is `V065-R8-NEXT-SOURCE-FEASIBILITY-01` (`PREPARED_NOT_DISPATCHED`), defined in [the source-feasibility plan](V065_NEXT_GATE_LIQUIDATION_FLOW_SOURCE_FEASIBILITY_PLAN_20261022.md). Codex/Agy may execute it only after Controller dispatches the scoped card. 1-A is not currently dispatched; it may review a consequential source/rights/clock claim if one arises. 2-R registration and 2-C challenge are conditional on source-feasibility evidence and a concrete Controller question; 2-E has no integration task. A-line remains separate. Synthetic tests do not establish profitability or authorize outcome access. See [results](V065_R8_ARGON_RESEARCH_RESULTS_20261022.md).

<!-- /R8-ARGON-STATE-20261022 -->
Owner-directed dispatch policy: [R5](V065_EXECUTION_FIRST_CONTROLLER_POLICY_R5.md). Five ChatGPT conversations remain **0 / 1 / 2-R / 2-C / 2-E**, but **not five mandatory stages**. Codex and Antigravity (Agy/Gemini) are the default coding executors; these five conversations are *roles*, not a required waterfall.

| Work | Default owner | Escalation rule |
|---|---|---|
| Priorities, ready tasks, merge routing, progress/status | **0 Controller** | Owner only for true tradeoffs/rights/cost/production authority |
| Code, parsers, ingestion adapter, UI, local tests, bug fixes, documentation | **Codex / Agy** | 0 reviews diff and scoped tests; no other chat by default |
| Mechanical docs/metadata when convenient | Codex/Agy or **2-E** | No 1-A required |
| Genuine new BTC 4–24h mechanism, hypotheses | **2-R** or Codex/Agy research exploration | 2-C only if concrete novelty requires falsification |
| Specific material adversarial hypothesis claim | **2-C**, on request | No standing role in general coding |
| Consequential data/source rights, actual known-at PIT, risky integrity, financial or release claim | **1 / 1-A** | **One bounded independent review**, not 3-level automatic chain |
| Owner-visible planning and gate decisions | **0 Controller** | Single named evidence-driven gate |

**Default review policy:** T0 docs = diff only; T1 routine = scoped tests; T2 DEV source/timing = changed positive/negative invariants; T3 actual source/PIT/production execution/finance = separately approved independent gate. Repeating an accepted frozen test/review solely for a new wrapper commit is normally wasteful when content-addressed equivalence can be verified by Controller.

**Parallelism:** max two active writers across non-overlapping paths, one read-only investigation; one task per chat. Prefer current local `/root/workspace/project/quant-0.6.5`, create new worktrees only if needed. Avoid custom agents unless requested. Keep protected A-line separate.

**Success = working vertical slice and validated new information, not role utilization.** All existing source/PIT, Alpha, protected data, TESTNET/LIVE and funds gates remain unchanged.


## Mandatory shared prompt-card contract

All roles and executors must follow [V06 ChatGPT Output UI and Task Card Standard R1](V06_CHATGPT_OUTPUT_UI_AND_TASK_CARD_STANDARD_R1.md). Any executable/dispatchable prompt shown to the Owner must be represented by a compact card (at most two cards per response) with exactly one functional Copy prompt button; the complete prompt body is only the copy-action payload and must not be displayed visibly. If a working copy action is unavailable, state the limitation and ask before showing the prompt body. This applies to Controller, Auditor, Researcher, Challenger, Direct Executor, A-line Controller, Codex/Sol/Astra/Gemini, and subagents.
