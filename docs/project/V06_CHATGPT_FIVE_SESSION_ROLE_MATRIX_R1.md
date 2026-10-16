# v0.6.5 — Five-Session Role / Executor Routing Matrix R2

**Scope:** B-line research-first personal/noncommercial project. ChatGPT has exactly **five separate conversations: 0 Controller; 1 Independent Auditor; 2-R Research Scientist; 2-C Challenger; 2-E Direct Executor.** No “ChatGPT-3” and no custom subagents. A-line Controller is separate. [Operating contract](V065_RESEARCH_FIRST_OPERATING_CONTRACT_R2.md) · [UI standard](V06_CHATGPT_OUTPUT_UI_AND_TASK_CARD_STANDARD_R1.md). Original matrix preserved at [v0.6.5 M0](https://github.com/EXASHXE/btc-quant-agent-public/blob/065d62965373627c4887e52f482d1dcb984af860/docs/project/V06_CHATGPT_FIVE_SESSION_ROLE_MATRIX_R1.md).

## Dispatch rules

| Task type | Primary executor | When review is useful | Do not waste time on |
|---|---|---|---|
| Priorities, project road map, accepted source/merge decisions, task cards | **0 Controller** | 1 only for consequential new claims | parallel Controllers or re-auditing static status |
| Independent source rights/physical PIT/economics or material integration proof | **1 Auditor** | cross-check author frozen evidence | independent audit for every ordinary docs fix |
| New BTC 4–24h mechanism/novelty/prereg | **2-R Researcher** | 2-C for hypothesis novelty, 1 for consequential source/science | indicator renaming, output-heavy 8-candidate speculation |
| Falsification of a specific novel hypothesis | **2-C Challenger** | 1 only if still economically consequential | compulsory challenge for dataset list or ordinary parser UI |
| Small deterministic docs/metadata/fix/test | **2-E Direct Executor** | usually 0 checks diff; no 1 required | large ETL, PIT/funding logic, long CI |
| Complex repo integration, data archive QC, bounded historical pipeline | **Codex High/Sol** or **Gemini** | 1 for material source admission/cross-module correctness | unbounded full test rounds on every small change |
| Normal bounded code with clear acceptance | **Gemini NORMAL** | scoped unit tests | BOOST on copy/rename tasks |
| Causal or cross-module architecture/invariant design | **Gemini BOOST** / Codex High | 1 or 2-C if actual scientific claim | recursively spawned custom agents |
| Capacity/data hygiene | local Codex/Gemini only in **owner-approved isolated workspace** | Controller verifies real sample numbers | invented disk estimates and protected-root scans |

**One substantial task per chat**, but disjoint tasks can run in parallel on independently owned worktrees. Pre-stage the next wave's conditional prompts, explicitly **NOT DISPATCHED** until dependencies pass. Authors do not independently accept their own source, strategy or release claims; no mandatory chain 2-R→2-C→1→0 for every task. For hypotheses use 2-R/2-C; for consequential source/integration use 1; only 0 decides progression.

## Verification by impact

- **T0 docs**: exact changed paths + link/diff check; no mandatory full tests.
- **T1 routine code**: focused module tests/lint/syntax.
- **T2 market-source/PIT/financial code**: affected invariant positive/negative tests + independent gate if used to claim true source/Alpha/financial authority.
- **T3 real integration/release/account capability**: required full suites, branch checks, negative financial safety, independent release verdict.

CI is **not yet formally disabled**, and protection verification is pending; this matrix does not authorize trigger changes. Failure not relabeled success.

## Current v0.6.5 queue facts

Integration candidate `065d62965373627c4887e52f482d1dcb984af860` exists but still needs independent M0 review. R11-Q1 `8c3e53f...` is an immutable negative consequential review; R11-Q2 `c07c603...` authorized bounded data work only. D2 `803a417...` and E2 `7f8c6ac...` author delivered, pending independent review; C2 `9dbb0ce...` STOP_UNMEASURED_SOURCE. Next possible L2: R11-Q3, **not** automatic Alpha. No TESTNET/LIVE/funds.

## Canonical per-role documents

[0 Controller](../roles/V0.6_CHATGPT_0_PRIMARY_CONTROLLER.md) · [1 Auditor](../roles/V0.6_CHATGPT_1_SUPERVISORY_AUDITOR.md) · [2-R Researcher](../roles/V0.6_CHATGPT_2_INDEPENDENT_RESEARCH_SCIENTIST.md) · [2-C Challenger](../roles/V0.6_CHATGPT_2_ADVERSARIAL_CHALLENGER.md) · [2-E Executor](../roles/V0.6_CHATGPT_2_DIRECT_EXECUTION_OPERATOR.md). [A-line separate Controller](../roles/V0.6_CHATGPT_A_LINE_PRIMARY_CONTROLLER.md).

**Gates:** `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
