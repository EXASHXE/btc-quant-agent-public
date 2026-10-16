# v0.6.5 — Controller UI and Copyable Task Cards R2

**ACTIVE for owner-facing presentation under V065-M1; scientific/release acceptance is separate.** Audience: B-line 0 / 1 / 2-R / 2-C / 2-E. Owner preference: **visual, compact, action-oriented**, with prompt-copy controls and exact links, not full prompt dumps. [Research-first operating contract](V065_RESEARCH_FIRST_OPERATING_CONTRACT_R2.md). [Prior complete R1 standard](https://github.com/EXASHXE/btc-quant-agent-public/blob/065d62965373627c4887e52f482d1dcb984af860/docs/project/V06_CHATGPT_OUTPUT_UI_AND_TASK_CARD_STANDARD_R1.md).

## First-screen contract for Controller 0

Show the same five elements in this order (aim for one mobile screen):
1. **Phase header:** `quant v0.6.5 | observed SHA | priority BTC 4–24h after-cost Alpha`.
2. **4–7 row dashboard:** branch integration, data/D2/E2/C2, PIT/source, strategy/Alpha, critical blocker, next gate, TESTNET/LIVE. Avoid decorative green `PASS` for author-only receipts.
3. **One Controller decision:** `GO_FOR_BOUNDED_TASK`, `WAIT_FOR_EVIDENCE` or `STOP/REPLAN` + strongest factual reason.
4. **Small READY task cards**, grouped by parallel W1 / serial gate / conditional W2.
5. **Next checkpoint:** the exact new fact or owner choice that can change the decision.

No repeated list of old phases or massive review quote before actionable choices.

## Task card fields (always populated where known)

**`TASK_ID · SHORT TITLE`** / state `READY | RUNNING | DELIVERED | REVIEWED | BLOCKED | PREPARED_CONDITIONAL | STOP`

- **Executor + observed model:** ChatGPT role or Codex/Gemini mode; no unverified model assertion.
- **Objective + acceptance:** one result in 1–2 sentences.
- **Prerequisite and parallel wave:** exact SHA for consequential targets; distinct branch/worktree/path owner; W2 conditions visibly **NOT DISPATCHED**.
- **Frozen original Prompt:** a real `github.com/.../blob/<full commit SHA>/<prompt path>` URL. If no published prompt exists, explicitly label `UNPUBLISHED` instead of inventing a link.
- **Copy prompt:** where interactive UI supports host copy, use a real button/action that copies the exact ready prompt; otherwise show **one** copyable code block or exact prompt link, not an inert fake button or raw prompt repeated in narrative.
- **Receipt:** if task delivered, replace “Copy to execute” with author SHA, report link, actual test status and review dependency.

Do not paste full task prose outside the card. If owner specifically requests the full prompt, give one clearly copyable block, not multiple identical versions.

## Ready wave vs conditional successors

The Controller should present all independent READY tasks in one packet where source scopes and path ownership are known. They may run concurrently across **different** role chats/Codex worktrees. **One substantive task per chat at a time**. W2 remains draft/prepared until W1 evidence is frozen and gates are decided; prewriting does not constitute dispatch. Parallelize docs/architecture/source metadata only if no overlapping target files or decisions.

## Progress vocabulary

- `DRAFT`: unpublished; `READY`: requirements met and scope frozen; `RUNNING`: observed execution; `DELIVERED`: author pushed only; `REVIEWED`: an independent verdict, including FAIL; `CONTROLLER_DECIDED`: exact authority; `BLOCKED`: missing specific source/rights/PIT/capacity; `STOP`: finite terminal; `SUPERSEDED`: pointer replaced, old evidence frozen.
- Do **not** conflate published commit, local tests, hosted green CI, independently accepted source or successful Alpha.
- A/C2/D2/E2 docs should never show an independently green check solely because the author says accepted-with-limits.

## Other roles' default UIs

| Role | Default |
|---|---|
| Controller 0 | concise dashboard → decision → W1 cards → W2 conditional → next evidence |
| Auditor 1 | target/evidence → top 2–4 consequential findings → one verdict/required witness |
| Researcher 2-R | novelty vs historical X → new data Z → falsifier → causal/cost/power gates |
| Challenger 2-C | strongest claim → most damaging counterexample → challenge verdict |
| Executor 2-E | changed file/SHA → focused test/NOT_RUN → completion |
| Codex/Gemini | implemented change + measured evidence + exact diff, no unbounded logs |

## Testing and receipt economy

**T0 docs:** changed path/commit, link/diff integrity; **no mandatory entire pytest/Ruff/mypy**. **T1 low-risk code:** only changed-module unit tests/lint. **T2 causal/source/financial semantics:** targeted positive and negative invariants and an independent decision *when consequential*. **T3 TESTNET/live/release:** full required exact-SHA CI and independent gate. Actual automatic CI may run under existing workflow; report its real status. `NOT_RUN_BY_SCOPE` is not `PASS`. See [test ladder](V065_RESEARCH_FIRST_OPERATING_CONTRACT_R2.md#5-risk-weighted-verification-instead-of-all-tests-always).

## Immutable prompt lifecycle and boundaries

`DRAFT → PUBLISHED_READY → RUNNING → DELIVERED → INDEPENDENTLY_REVIEWED (when material) → CONTROLLER_DECIDED`. Content edits to a dispatched prompt need a new revision and blob. No role can create authority by presentation, and one green card cannot remove `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
