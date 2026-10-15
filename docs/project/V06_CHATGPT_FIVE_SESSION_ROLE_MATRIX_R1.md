# quant v0.6 — Five-Session ChatGPT Role Matrix R1

> **R7 active role scheduler — 2026-10-15:** [Latest handover](../handover/V06_BLINE_CONTROLLER_R7_HANDOVER_20261015.md). Exactly five separate B-line chats: `0` Controller, `1` Auditor, `2-R` Researcher, `2-C` Challenger and `2-E` bounded Executor. A-line Controller separate. One task at a time **per chat**, cross-chat parallel only when each prerequisite is present. 2-R T6 concluded STOP; 2-C/1 final conditional T6 review not triggered; 2-E R7-S0 documentary-only pending. 0 alone adjudicates any new source-file/data permit. H40 A-line-specific and P1D full engine not in B-line active path. Earlier dated matrix examples are historical.


**Date:** 2026-10-14. **Governance layer:** B-line. **Owner-requested numbering:** `0 / 1 / 2 / 2 / 2`. The last three are **different sessions all named ChatGPT-2**, uniquely distinguished by role IDs **2-R**, **2-C** and **2-E**. **There is NO ChatGPT-3 session in the current five-session roster.** A-line Scientific Controller remains a **separate** Controller program and is not counted in these five B-line conversations.

| Conversation | Stable ID | Single core responsibility | Can author? | Can independently accept its own artifact? | Who controls escalation? |
|---|---|---|---|---|---|
| **ChatGPT-0 Controller** | `CHATGPT_0_BLINE_CONTROLLER` | Source/strategy/governance L2 task scoping and terminal decisions | Task dispatches and Controller adjudications | NO | Owner plus B-line Controller exact-SHA contract |
| **ChatGPT-1 Auditor** | `CHATGPT_1_SUPERVISORY_AUDITOR` | Consequential independent science/PIT/economic/release audit | Separate independent review only | NO | Cannot approve protected trials, Alpha/TESTNET/LIVE by itself |
| **ChatGPT-2 Researcher (2-R)** | `CHATGPT_2_RESEARCH_SCIENTIST` | Source-first, outcome-blind hypothesis, novelty and falsifiable methodology | Scoped research designs | NO | Controller authorizes outcomes/data; 2-C challenges |
| **ChatGPT-2 Challenger (2-C)** | `CHATGPT_2_ADVERSARIAL_CHALLENGER` | Independently disprove or qualify 2-R claims and methods | Scoped independent challenges (different target author) | NO | ChatGPT-1 formal high-impact acceptance; Controller L2 |
| **ChatGPT-2 Executor (2-E)** | `CHATGPT_2_DIRECT_EXECUTION_OPERATOR` | Direct light GitHub/local authorized edits, source citations, docs, deterministic small code/test fixes | Scoped implementation/repair | NO | ChatGPT-1 for consequential review; Controller for merge/admission |

**Canonical role files:** [ChatGPT-0](../roles/V0.6_CHATGPT_0_PRIMARY_CONTROLLER.md), [ChatGPT-1](../roles/V0.6_CHATGPT_1_SUPERVISORY_AUDITOR.md), [2-R](../roles/V0.6_CHATGPT_2_INDEPENDENT_RESEARCH_SCIENTIST.md), [2-C](../roles/V0.6_CHATGPT_2_ADVERSARIAL_CHALLENGER.md), [2-E](../roles/V0.6_CHATGPT_2_DIRECT_EXECUTION_OPERATOR.md).

**Bootstraps:** [all five chat prompts](V0.6_NEW_CHAT_HANDOVER_INDEX.md). Each role has a **separate chat**; same “2” number does not mean shared conversation, shared tool session, shared trust, or interchangeable independence. Each authored artifact records an exact role ID and full target SHA/blob to avoid identity collisions.

## Collaboration and authority edges

```text
                        USER / PROJECT OWNER
                                 |
                      ChatGPT-0 (Controller)
              exact task/SHA/path/data authority
                  /               |               \
     ChatGPT-2 (2-R)       ChatGPT-2 (2-C)      ChatGPT-2 (2-E)
        Researcher            Challenger        Direct Operator
        design/claims         adversarial        bounded changes
                  \              |               /
                     ChatGPT-1 (independent auditor)
                         consequential review
                                 |
                 ChatGPT-0 (final L2 decision/merge)
```

- **2-R → 2-C → 0:** Scientific source design/proposal → independently challenged counterarguments → Controller's next-scoped decision. For consequential science add **ChatGPT-1** independent formal audit before L2.
- **0 → 2-E → 1 → 0:** Bounded repair/engineering change → exact-SHA implementation receipt → independent audit where required → Controller L2. For simple typo/docs and task-specific owner permission, 2-E may act in chat immediately on a separate branch; its own diff check is **implementation QA**, not an independent scientific PASS.
- **2-R vs 2-C independence:** Each reads frozen primary sources separately for Round 0. If 2-C becomes an author of a corrective artifact, it loses independence as **its own** terminal reviewer. Another genuinely separate reviewer is needed.
- **GitHub Issue #1** historic `[R2]` and `[R3]` debate labels map to **2-R** and **2-C**. Do not rewrite the old issue/body/comments. New posts use `[2-R]` and `[2-C]`; Issue #1 is discussion only, not a study/data/release authorization. Legacy references to a “ChatGPT-3 Challenger” are an outdated session label, **not a new sixth role**.
- Gemini NORMAL, Gemini BOOST, Codex Sol, and remote/local MCP tools are **execution resources**, not additional ChatGPT chat role numbers. Choose by bounded compute/problem complexity, without automatically spawning parallel work.

## Direct execution lanes (2-E) and concrete task boundaries

| Lane | Accepted low-complexity work | Preconditions | Stop condition |
|---|---|---|---|
| **Docs/metadata** | citation repairs, role/status notes, links, task prompts, append-only provenance | Owner or Controller explicit ordinary docs scope; isolated branch and single-writer path | Existing frozen record, protected data, ambiguous base, prior conflicting edit |
| **Small code/test** | narrowly specified deterministic fix, fixtures, static parsers, exact test corrections | Real Controller/owner bounded task, source exact SHA, paths and negative cases; independent gate if consequential | Finance/PIT/order authority, source semantics, risky CI policy, broad regression or unknown cost |
| **Remote local files** | bounded text edits in explicitly named unprotected worktree through connected Desktop Commander | Device ONLINE at execution time + **specific directory/path authorization**, clean worktree/diff, no user secrets | Any protected/owner root, unrelated home filesystem, unsafe shell or side-effect uncertainty |
| **Read-only diagnosis** | GitHub evidence, static diff, reports; propose small repair | Known public reference and requested read scope | No write or access rights; report `AUTHORITY_PENDING` |

**Not allowed:** remote-access capability itself is not authorization to inspect local owner roots, open sensitive data, or run arbitrary shell commands. No trading account, private exchange endpoint, testnet, Live, historical PnL, forward market collection or holdout. No auto-merge.

## Exact evidence and task state precedence

Immutable Controller dispatch and explicitly scoped owner authority + observed Git commit/blob/diff/tests take priority over an agent's claims, cached status JSON and moving branch narratives. A successful docs-only CI, a green focused CI, a full executable safety CI, an independent science PASS, source admission and release PASS are **distinct outcomes**. If exact target/push missing, report `INCOMPLETE_TARGET_UNFROZEN` or `BLOCKED_NOT_PUSHED`, never invent SHAs.

**Current cross-role invariant:** `SOURCE_NOT_ADMITTED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`. Separate A-line H39/H40/H41/Forward authorities cannot be inherited.
