# v0.6 B-line G2 R3 — Controller terminal P1 architecture disposition / alternative engine decision R1

## Binding controller decision

**`CONTROLLER_ACCEPT_B_FINAL_ARCH_V1_BLOCKERS__P1_ENGINE_NO_GO__TERMINATE_CURRENT_VIRTUALBOOK_REPAIR_ROUTE__AUTHORIZE_ONE_BOUNDED_ALTERNATIVE_ENGINE_ARCHITECTURE_SELECTION`**

The last independent Gemini B audit was completed against frozen A implementation `b5d34aacd36dc27454944a22436db555c3f6eeb8`, returning **`ARCH_V1_B_SEMANTIC_BLOCKED_REPLAN_ALTERNATIVE_ENGINE`**. The current P1 implementation is **NOT ACCEPTED** for historical development replay, even though its normal CI green and its ordinary synthetic lifecycle runs. This is terminal for the **current mutable VirtualBook repair approach**: **NO R4/R5 patches, no retest of identical architecture as a new independent 'fix' cycle**.

The Controller only authorizes **one separate, finite, design-only alternative-engine choice**; no new code is authorized by this decision. After choosing an event/state architecture, publication of a distinct implementation task (one coherent build and one independent semantic acceptance) requires another Controller decision. If no feasible architecture can meet the time/cost and invariant constraints, stop P1 strategy-replay route and shift research design rather than unbounded development.

## Remote identity and authority verified

- A original branch `feature/v06-bline-g2-overnight-discovery-a@b5d34aacd36dc27454944a22436db555c3f6eeb8`; its full CI [37918930513](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37918930513) **SUCCESS: 2844 passed, 2 skipped, 9 warnings, mypy 170 production files clean**. This remains valid engineering hygiene, **not** independent semantic clearance.
- B independent branch `feature/v06-bline-g2-overnight-verifier-b@52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7`, **single direct child** of `068a4005f68b5ee4a970063cb1f3bc524a08784a`, six added files all in B's authorized verification-only paths. No A modifications.
- Real Controller B dispatch `5f9b7f75215b394ad86d49b468e7acd9a89c23a2`, pinned B prompt `f2ff646bb317c7a7cb4de8bf6515e1d3cbe9e5f0`. B isolated the exact A source via git archive; report, matrix and executable auditor attest to real source module files loaded under temporary archive, not old B local code:
  - [Independent B verdict](https://github.com/EXASHXE/btc-quant-agent-public/blob/52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7/docs/strategy_research/g2_r3/prep_b/architecture_v1/B_FINAL_INDEPENDENT_ARCHITECTURE_VERDICT.md)
  - [Case matrix](https://github.com/EXASHXE/btc-quant-agent-public/blob/52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7/evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/B01_B07_FINAL_INDEPENDENT_BEHAVIOR_MATRIX.json)
  - [Synthetic receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7/evidence/v0.6/b_line/g2_overnight_p0_b/architecture_v1/B_FINAL_SYNTHETIC_EXECUTION_RECEIPT.json)
  - [Independent verifier implementation](https://github.com/EXASHXE/btc-quant-agent-public/blob/52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7/scripts/strategy_research/r3_verification/architecture_v1/a_arch_v1_auditor.py).
- B exact-head [CI 37928939579](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37928939579) **FAILURE** on repository-wide inherited H40 golden `tests/test_v051_h40_m3a_production_discovery_producer.py::test_p09_through_p18_exact_scientific_graph`: expected hash `d5a962cd...`, observed `ee185f1f...`; **2828 passed / 1 failed / 2 skipped / 9 warnings**, Ruff and mypy passed. Nine new B test functions are part of 2828 passed; note that these intentionally assert the existence of real B blockers, so green verifier tests DO NOT mean green target engine. Never waive or modify H40 golden; separately investigate intermittent environment/schedule/ordering for this old scientific graph.

## Independent findings: evidence grade and decision relevance

Seven ordinary positive areas passed; only B04 passed the independent adversarial gate, so **six of seven adversarial areas remain blocked** on the frozen A target. The blocker statuses are audit results, not separate six independent failures of the entire scientific research project. The following are the *strong sufficient* reasons to terminate the current implementation:

1. **CRITICAL B05**: `_stage_2_account_risk` values only `self.positions`, not post-close pre-ACK realized economic losses in `pending_exit_acks`; a synthetically crystallized **−169.336545 USDT** unsettled trade did not latch the existing 100 USDT drawdown kill and reported **933.7769 USDT** available capital. `compute_available_capital` uses decision equity without conservative pre-ACK loss adjustment. Repeated across position lifecycle, this invalidates risk and capital constraints.
2. **CRITICAL B03/B07**: Funding reserve is consumed/released at Stage7 while payable cash debit waits for later Funding ACK; in 1.00 USDT debit with 0.40 owned reserve, **0.60 USDT shortfall is not represented as spendable-capital liability**, producing available-capital inflation (941 rather than conservative 940 in B fixture); Stage1 moves reserved money to `_unsettled_exit_trades` side-dict without maintaining the claimed typed owner ledger equation. Positions, exited trades and funding ACK are not controlled by an auditable unified state machine.
3. **HIGH B01/B02**: same-close conflicting marks produce input-order dependent price (50000 vs 52000), late duplicate may rewrite history; ACK idempotence keyed only on ID ignores contradictory payloads and later ACK can rewind cooldown. Production source confirms use of `>=` on same-close Mark and unconditional cooldown overwrite.
4. **B06 specification/state concern**: source checks only latest completed 1h bar when advancing Retest, not all skipped completed bars; a skip can bypass intermediate cancellation/low, plus same-hour cancel/rebreakout registration is not supported by frozen source without explicit method adjudication. Strongly require new design to avoid hidden state timing/candidate cross-contamination.
5. **B04 PASS**: stop-first same-bar, adverse/favorable gap semantics, conservative minute-end exit and 4h cooldown preserved. Reuse *behavioral specification and positive fixtures*, not unsafe mutable engine state.

**Qualification of isolated adversarial fixtures, required for honest authority:** A B03 test uses `open_time_ms = S−5000ms` in `step_minute_open`, which is not minute-aligned and is not a realizable normal ReplayEngine minute-open call. Thus that particular early-ACK-before-S witness is **a direct API stress case, not a demonstrated reachable production path**. Similarly, a Stage8 `economic_equity` reading the current minute's close may be legitimate **ex-post reporting** if it never influences an earlier decision; distinguish this from actual decision lookahead. These qualifications do not rescind the independently verified B05 and B03/B07 unsettled-liability/capital blockers or the B01 same-close order dependence. No unsupported claim that every adversarial tuple was shown reachable via full replay.

## Route choice / protected fences

**Architectural default to evaluate first:** a small typed event journal and double-entry position/owner ledger with explicit economic-event time vs ACK-availability time, self-financing accounting and conservative risk-visible pending liabilities. Reuse immutable eight-candidate formulas only after B06 Retest clock semantics are separately codified; reuse B04 execution contract and PIT/inference/provenance primitives, not the old `VirtualBook` mutation graph. Explicitly compare a minimal new engine with selective reuse of vetted existing framework and an external backtest runtime with adapters; libraries are **not** automatically semantically correct or approved.

No candidate-budget changes, R2 subgroup rescue, old protected Final Holdout, raw price/Mark/Funding bodies, new external exchange actions, or TESTNET/live permissions. No automatic authorization to merge previous A code into mainline. The baseline v0.6 branch, old A/B branches and their evidence must remain immutable during architecture selection.

## New bounded Sol High stage

Authorize one **`V06_G2_R3_P1_ALTERNATIVE_ENGINE_ARCHITECTURE_SELECTION_SOL_HIGH_R1`**, design-only, separate branch, to decide whether a minimal event-sourced ledger can be delivered without re-entering a patch loop. Sol must produce design decision, independent invariant/oracle/test architecture, exact reuse vs reimplement map, bounded work and one downstream Gemini implementation package; economic strategy review is already complete and is NOT repeated.

- **P1**: `TERMINAL_ARCH_V1_NO_GO__P1_ALT_ENGINE_DESIGN_AUTHORIZED`; no P1 accepted code.
- **P2**: `LOCAL_ROOT_UNKNOWN`/source-licence-true-mark check in parallel.
- **Scientific**: Sol review `SCIENCE_READY` for one descriptive, fixed-budget original-eight **proxy** diagnostic ONLY, Astra not currently necessary.
- **P3**: `PREREG_EFFECTIVE=NONE`; will require **new engine Controller acceptance**, source grants and new first-pushed SHA.
- **P4**: `EMPIRICAL_MARKET_BODIES=NOT_AUTHORIZED`; `TESTNET=NOT_AUTHORIZED`; `REAL_FUNDS_WRITE_AUTHORITY=NONE`.

**No promise of performance alpha** and no new generic audit cycles.
