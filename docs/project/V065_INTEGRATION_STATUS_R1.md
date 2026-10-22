# quant v0.6.5 — Current Engineering Integration Snapshot · R8 update 2026-10-22

<!-- R8-ARGON-STATE-20261022 -->

## Current Integration Snapshot — 2026-10-22

R8-8 and R8-A/B/C/D are **engineering-complete but not integrated**. All five remote Codex runs exited 0. Focused validation: R8-8 3,772 ledger checks; R8-A 48 tests; R8-B 82 tests; R8-C 76 tests; R8-D 43 tests. No new real historical outcome, no protected 2024–2026 access, no commit/push from those worktrees.

**Next gate:** metadata-only source feasibility for the selected forced-liquidation flow-exhaustion hypothesis, state `PREPARED_NOT_DISPATCHED`; see [source-feasibility plan](V065_NEXT_GATE_LIQUIDATION_FLOW_SOURCE_FEASIBILITY_PLAN_20261022.md). This gate may establish feasibility for separately authorized source/clock QA only, not source admission or receiver PIT acceptance. No market-value payload, outcome, backtest or integration is authorized by the plan.

Integration blockers: (1) R8-A SMA-seeded EMA/MACD differs from the production-seeded primitives used by R8-C; choose and validate one implementation before any shared trial. (2) R8-D joint coverage is unknown; the legacy 35,250 funding-z count is not joint feature coverage, and normalized bars do not retain taker-buy columns. (3) the selected liquidation hypothesis needs direct liquidation/OI/spot/executable-perp source completeness and receiver-clock feasibility. Do not merge or run empirical strategy outcomes until a separate scoped task and explicit Owner authorization. See [research results](V065_R8_ARGON_RESEARCH_RESULTS_20261022.md).

<!-- /R8-ARGON-STATE-20261022 -->
**Historical GitHub default snapshot (2026-10-18):** `v0.6.5@12b74b4c2fd3a22a9f4b35dbf331cfb1166aae77`. The five R8 worktrees later used baseline `40c70c740f352d1b444decb75276196d17a72dd2`; neither value is a fresh check of the moving remote ref. Refresh before code dispatch/publication. The current R8 next gate is metadata-only source feasibility; see the [live roadmap](V0.6_PROJECT_STATUS_AND_ROADMAP.md), [R5 execution policy](V065_EXECUTION_FIRST_CONTROLLER_POLICY_R5.md), and [source-feasibility plan](V065_NEXT_GATE_LIQUIDATION_FLOW_SOURCE_FEASIBILITY_PLAN_20261022.md).

| Scope | Verified state | Limit |
|---|---|---|
| Repository topology | Main `v0.6.5`; separate `docs/engineering`, `legacy/research-archive`; historical pruning completed | Old 42-ref/A-line and PR #3/#5 history are not the active B-line work queue |
| [PR #7](https://github.com/EXASHXE/btc-quant-agent-public/pull/7) | **MERGED 2026-10-17**: D-NEXT + D2 R2 code-only QC, 215-object plan, manifest v2 | Code integration **not** original ZIP L1/receiver PIT admission; 14,534,450 B remains `NOT_REPLAYED` |
| [PR #8](https://github.com/EXASHXE/btc-quant-agent-public/pull/8) | **MERGED 2026-10-17**: R3 offline claimed causal-clock kernel; reviewed original tree `c9c25c4c49fe2203fa1414f64e937243843d0fc9` | Output is `CLAIMED_TIMING_ELIGIBLE`, **not** authenticated source admission |
| Synthetic QA | Independent focused D2 41/41 and R3 clock+D2 67/67 **PASS at frozen respective commits** | No claim of current-head full CI or live source tests |
| Microstructure shutdown | Synthetic nonkill stop policy R3 independently `ACCEPT_SYNTHETIC_NONKILL_POLICY_WITH_LIMITS`; live service unchanged | Real 20s + SIGKILL policy still effective; production cutover **HOLD** until Owner tolerance/approved preflight |
| Scientific | No independently accepted original receiver-first-known, all-in execution-cost Alpha or utility | L1/L2/Alpha/TESTNET/LIVE remain `NO_GO` |

**Current code focus:** Codex/Agy implement a runnable **offline/synthetic vertical slice** using already integrated D2 QC and claimed-only timing hooks; create one deterministic demo and explicit sample/expected output. True market data capture and legacy-store migration belong to **separately authorized** lanes. Do not repeat the same code-only PR audit.

**GitHub statuses:** PR #7 and #8 merged; PR #3 and #5 still open draft as observed; historical branch-maintenance holds are not evidence of current release work. CI results must be checked for their exact SHA before claimed. No workflow edits authorized here.

**Boundaries:** `SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.
