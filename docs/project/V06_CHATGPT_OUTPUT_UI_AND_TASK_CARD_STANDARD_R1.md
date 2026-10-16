# quant v0.6 — ChatGPT Output UI & Task Card Standard R1

**Status:** ACTIVE  
**Applies to:** B-line five sessions and the separate A-line Controller  
**Purpose:** keep owner-facing outputs scannable while preserving exact-SHA scientific governance.

> [!IMPORTANT]
> Presentation never changes authority. A compact card, green status, or copyable prompt is not a scientific acceptance, source-admission grant, merge approval, TESTNET approval, or LIVE approval.

## 1. Owner-facing hierarchy

Unless the owner explicitly asks for the full report, use:

1. **Status dashboard** — phase, gates, blockers, next gate.
2. **Decision card** — only when a decision exists.
3. **Task cards** — grouped by parallel wave.
4. **Evidence/receipt card** — exact SHA/blob, tests, diff, terminal.
5. **Long-form detail** — only on request or where a consequential audit trail requires it.

Do not repeat the same information in prose, tables and prompt bodies.

## 2. Status dashboard

Keep the first screen to 6–8 rows.

| Dimension | Status | Next gate |
|---|---|---|
| Phase | current stage | stage gate |
| Alpha | NO_GO / CANDIDATE / VALIDATED | explicit scientific test |
| Data | READY / PARTIAL / BLOCKED | source/PIT admission |
| Engineering | RESEARCH_ONLY / INTEGRATION / RELEASE | engineering gate |
| TESTNET | NOT_AUTHORIZED / READY | safety gate |
| LIVE | NO_GO / NOT_AUTHORIZED | release authorization |
| Critical blocker | one line | owner/controller action |
| Next wave | task IDs | dependencies |

The dashboard is navigation, not evidence.

## 3. Task card

### STATUS · TASK_ID · SHORT TITLE

| Field | Value |
|---|---|
| Executor | role + model mode |
| Objective | one sentence |
| Scope | one short line |
| Prerequisites | exact task IDs / SHA state |
| Expected output | report / code / data receipt |
| Authorization | READY / CONDITIONAL / BLOCKED / NOT_AUTHORIZED |
| Original prompt | exact GitHub prompt link |
| Parallel wave | W1 / W2 / SERIAL |

Rules:
- Never paste the full prompt into card prose.
- The exact GitHub prompt is canonical.
- READY tasks may expose one copyable prompt block when dispatch is requested.
- PREPARED_CONDITIONAL tasks show dependencies but do not look executable.
- BLOCKED tasks show blocker and required evidence, not a large prompt.
- COMPLETED tasks show the receipt and original prompt link; do not reissue them.
- Never invent future SHAs.
- One substantive task per chat/session; parallelism is cross-session only when safe.

## 4. Copyable prompt UX

For ChatGPT owner-facing responses, use one copyable code/writing block for a READY prompt when the owner needs to dispatch it. Do not duplicate the prompt in prose.

Copy/edit actions vary by ChatGPT plan, device and rollout, so use supported copyable blocks rather than fabricated HTML buttons.

For repository Markdown, long prompt bodies should be inside a collapsed details section:

<details>
<summary>Copy / inspect exact prompt</summary>

~~~text
EXACT PROMPT CONTENT
~~~

</details>

Keep the original GitHub prompt link visible outside the collapsed section.

## 5. Parallel waves

Represent concurrent work as:

### Parallel Wave W1
- task card A
- task card B
- task card C

### Gate W1 → W2
A PASS + B PASS + C PASS → W2

Do not serialize independent documentary, capacity or source-feasibility work without a dependency reason.

Do not parallelize work that shares a path, depends on an unfrozen SHA, compromises reviewer independence, violates one-chat-one-task, or exceeds approved resource limits.

## 6. Status vocabulary

- READY — dispatchable now.
- PREPARED_CONDITIONAL — designed but prerequisites are not satisfied.
- BLOCKED — authority/evidence missing.
- RUNNING — execution started.
- DELIVERED — artifact exists; Controller has not adjudicated.
- ACCEPTED — authorized independent acceptance exists.
- STOP — terminal negative decision.
- SUPERSEDED — replaced by later exact-SHA authority.

A prepared prompt is never implicit execution authorization.

## 7. Role output defaults

| Role | Default surface |
|---|---|
| 0 Controller | STATUS → DECISION → TASK CARDS → NEXT GATE |
| 1 Auditor | TARGET → EVIDENCE → FINDINGS → VERDICT |
| 2-R Researcher | HYPOTHESIS → MECHANISM → DATA/PIT → FALSIFICATION → NEXT TEST |
| 2-C Challenger | TARGET → COUNTERARGUMENT → FAILURE MODE → REPAIR/STOP |
| 2-E Executor | EXECUTION → CHANGE → TEST → REMOTE RECEIPT → TERMINAL |
| A-line Controller | STATUS → DECISION → TASK CARDS → EVIDENCE, with A-line authority boundary |

## 8. Evidence receipt

| Field | Value |
|---|---|
| Task | task ID |
| Start SHA | exact |
| Parent | exact |
| Changed paths | allowlist result |
| Output SHA | exact |
| Output blob | exact |
| Tests | actual commands/results |
| Remote push | VERIFIED / NOT_VERIFIED |
| Reviewer | distinct role |
| Terminal | exact |

A local commit is not a remote delivery receipt.

## 9. Project progress

Status documents lead with phase, scientific verdict, active gates, parallel wave, critical blockers and next decision. Historical detail may be collapsed. Historical evidence remains immutable and must not be overwritten to make the dashboard look cleaner.

## 10. Prompt lifecycle

DRAFT → READY → DISPATCHED → RUNNING → DELIVERED → INDEPENDENTLY REVIEWED → CONTROLLER ADJUDICATED

A material scope change requires a new prompt SHA/blob and revision/task identity. Never silently mutate an already dispatched prompt.

## 11. Governance invariant

The UI must never bypass PIT, execution-cost, source-rights, multiplicity, protected-data, TESTNET/LIVE, reviewer-independence or G2/G4 gates.

## 12. Owner preference

Default communication is **card-first and concise**. Full prompts/reports are shown only once, inside the appropriate copyable or requested detailed surface. The objective is maximum decision information per screen without reducing the underlying scientific record.
