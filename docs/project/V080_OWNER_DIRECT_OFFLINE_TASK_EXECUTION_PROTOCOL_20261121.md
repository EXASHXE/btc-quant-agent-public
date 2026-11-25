# QUANT v0.8.0 — Owner-Direct Offline Engineering Start Protocol

## Controlling 2026-11-26 update — RC1 and Owner-confirmed T3
The current accepted local source baseline is v1.0-rc1 at 2a40471; P3 closed NO_CANDIDATE_BEATS_B2_V1 (9/24 trials), P4 not run, final OOS sealed; Stage 3 scoped acceptance recorded locally. Operator upgrade pending, remote code/tag publication and hosted CI unverified, S6 unauthorized. Current product is personal trading intelligence / market structure radar; no validated trading strategy. Current research horizon ~4h–5d; frozen B2 V1 remains unchanged.
Both web ChatGPT GPT-6.2 Sol and Gemini 4 Neon remain coequal combined 1-A + Controller 0-C, mutual audit and planning, one queue, one accountable Controller, no Worker self-acceptance. Both may use T3 MCP to inspect local tasks read-only, and launch/send an exact bounded task to Codex or AGY **only after Owner explicitly confirms T3 dispatch in a prompt identifying that task/prompt and executor**. No automatic dispatch, steering, restart, recurring tasks, permission escalation or live operations. Existing Owner-direct bounded offline forwarding (2026-11-24) remains valid without extra EXECUTE. T3 capability is not authorization; a draft/card/peer report does not grant launch authority. Record actual task/thread/run status, use exact provider options, pinned local base and non-overlapping write sets; no public sensitive identifiers. Keep full English copy-button cards and Chinese Owner communication.
See the canonical current checkpoint and T3 dispatch protocol linked below. **All older status, routing and execution restrictions below are historical where inconsistent with this controlling update; historical evidence and restrictions on real operations remain intact.**

- [Current checkpoint and roadmap](V080_CURRENT_CHECKPOINT_AND_ROADMAP_20261126.md)
- [Owner-confirmed T3 remote dispatch](V080_T3_OWNER_CONFIRMED_REMOTE_DISPATCH_20261126.md)

---


**2026-11-24 role clarification:** Both web ChatGPT GPT-6.2 Sol and web Gemini 4 Neon hold combined 1-A/0-C, mutually audit and plan, and may generate full task prompts. Either can be the accountable 0-C for a task; avoid duplicate dispatch and reconcile one disposition. This changes role allocation only, not the Owner-direct OFFLINE start rule below. Do not require two Controller signatures for routine Owner-authorized OFFLINE work.

Status: ACTIVE / OWNER-DIRECTED / FUTURE OFFLINE TASKS
Effective: 2026-11-21
Canonical branch: docs/engineering
Applies to: Controller 0-C, Sol, Neon, Hydrogen, all workers and prompt authors.

## 1. Root cause and Owner decision

A named Gemini Neon offline task was forwarded to its executor with a prior task-card label OWNER_PROPOSED / AWAITING_CONTROLLER_DISPATCH. The worker searched for a second Controller JSON receipt and stopped with zero engineering work. This is redundant administration for strictly local nonprivileged offline work. The executable branch root AGENTS.md also retains a historical R1-specific dispatch warning; that must NOT be treated as a universal rule for all future Owner-started offline jobs.

**Controlling Owner rule:** When the Owner **explicitly instructs a named worker in that worker conversation to execute a complete, identified, bounded OFFLINE task**, that message is a sufficient authorization to START OFFLINE ENGINEERING. A separate 0-C dispatch JSON is **not a prerequisite**. Record OWNER_DIRECT_OFFLINE_STARTED, NOT CONTROLLER_DISPATCHED.

A card's existence, a proposed task, a previously generated prompt, a historical chat, or a worker deciding to self-start does NOT constitute Owner execution direction. Explicit forwarding/execution instruction is required.

This newer policy supersedes conflicting general historical dispatch-stop wording only for future nonprivileged Owner-forwarded offline work. Do not modify old receipts or waive task-specific substantive safety restrictions.

## 2. Decision table

| Evidence in worker conversation | Start safe offline engineering? | Required state |
|---|---|---|
| Genuine matching 0-C dispatch | YES within scope | CONTROLLER_DISPATCHED |
| Explicit Owner execute instruction + complete named OFFLINE task card, but missing 0-C dispatch JSON | **YES, do not stop** | OWNER_DIRECT_OFFLINE_STARTED / CONTROLLER_REVIEW_PENDING |
| Task proposal only, not forwarded to execute; no matching dispatch | NO | DRAFT_ONLY / AWAITING_OWNER_FORWARD |
| Explicit Owner request containing protected production enrollment, real Binance/Feishu/model API, private account or TRADE | Offline preparation only if separately scoped; deny live/protected step | LIVE_GATE_HOLD |
| Duplicate active writer, overlapping write set, immutable baseline mutation or genuine scope conflict | Do not collide; isolate safe independent portion or hold | CONFLICT_HOLD |

If the task itself has a **substantive** reason why even offline work must await separate review (e.g. protected data, production UID, overlapping active workroot, sealed evidence, strict holdout), respect it. Missing purely administrative JSON is not such a reason.

## 3. Minimum task details and worker actions

A complete task needs: task ID, assigned executor, exact full task card or pinned canonical reference, isolated workroot/write set, prohibited live/privileged capabilities, QA/evidence/hand-off expectations and Controller reviewer.

Before starting: briefly check repo HEAD, task ID, whether a duplicate writer/workroot already exists, permitted paths, actual source constraints and sensitive boundaries. If there is a matching Controller dispatch, use it. Otherwise if Owner explicitly says EXECUTE this offline task, START WITHOUT A SECOND FORMAL RECEIPT SEARCH.

Inside the new allowed isolated workroot, write OWNER_DIRECT_OFFLINE_START.md recording:
- exact Task ID and task-card file/digest;
- execution authority = OWNER_DIRECT_OFFLINE;
- a truthful reference/summary of explicit Owner instruction;
- checked HEAD, target workroot and allowed/prohibited operations;
- note whether a matching Controller receipt was absent.
Do not forge a Controller decision, signature, approval or source identity.

Perform safe offline implementation and tests. If a genuine substep is blocked, complete other independent safe work and name the exact blocked step; do not respond only AWAITING_CONTROLLER_DISPATCH with zero work when Owner has authorized the offline task.

Deliver one sealed worker package with actual PASS/FAIL/SKIP, preserving source provenance and marking READY_FOR_CONTROLLER_REVIEW. The named accountable web 0-C can record independent scoped acceptance/hold after review. Either web model may be accountable; the other can challenge. The Controller may reconcile Owner-direct work afterward but may not fabricate a retroactive Controller dispatch receipt.

## 4. Controller and prompt-author duties

Every FUTURE task card selects exactly one start mode:

1. CONTROLLER_DISPATCHED: a real matching 0-C dispatch exists at delivery time; cite its task ID and path.
2. OWNER_DIRECT_OFFLINE_ALLOWED: include clear OFFLINE_EXECUTION_AUTHORITY = OWNER_DIRECT_AFTER_EXPLICIT_FORWARD. When Owner forwards and says EXECUTE, worker starts immediately; the card MUST NOT demand another Controller receipt for safe offline work.
3. PROPOSAL_ONLY: clearly mark not forwarded and DO NOT instruct workers to start without an explicit Owner direction or Controller dispatch.

The phrase "a prompt by itself is not a dispatch" remains true: merely authoring/reading a card gives no authority. However the Owner's explicit direct execution instruction grants limited offline execution.

For V080-NEON-S2-A1-OWNER-LOCAL-READINESS-01: if Owner has explicitly forwarded and ordered its strictly OFFLINE scope, Gemini Neon may start allowed work and log OWNER_DIRECT_OFFLINE_STARTED. Do not recreate H4, or treat Owner direct offline as a genuine A1/Canary/Feishu grant.

## 5. Non-negotiable safety/authority boundaries

This protocol does NOT permit: real Binance GET, real Feishu send/WebSocket, external model provider/OAuth/credentials, production signing or protected enrollment, deployment/host UID/security/CA mutation, recurring polling, actual private Futures USER_DATA, TRADE, protected data exfiltration or cross-user permission bypass. Every real or privileged capability retains its distinct Owner+Controller authorization gate.

No worker may self-dispatch tasks from mere file discovery, modify accepted seals/Program J/frozen contracts, write Controller decisions, or self-accept. An offline isolated workroot is not a production installation.

Expected outcome: remove redundant pre-start paperwork without weakening independent acceptance or any genuine security gate.
