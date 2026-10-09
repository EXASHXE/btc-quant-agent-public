# GPT-6 Sol High — P1 alternative engine architecture selection after independent architecture NO-GO

**TASK_ID:** `V06_G2_R3_P1_ALTERNATIVE_ENGINE_ARCHITECTURE_SELECTION_SOL_HIGH_R1`.
**Execution class:** ONE bounded engineering/scientific ARCHITECTURE DECISION; DESIGN-ONLY, NO production code or implementation changes.
**Executor preference:** GPT-6 Sol High reasoning, selected by invoking agent/user if actually supported (GitHub cannot select a model).
**CONTROLLER_DISPATCH_SHA:** `b74b932da32e4b5bbe2477c2de014f94719d6a93` — first read Controller's immutable [terminal P1 adjudication](https://github.com/EXASHXE/btc-quant-agent-public/blob/b74b932da32e4b5bbe2477c2de014f94719d6a93/reviews/v0.6/b_line/V06_G2_R3_P1_FINAL_B_ARCHITECTURE_NO_GO_AND_ALTERNATIVE_ENGINE_CONTROLLER_R1.md).
**Repository:** `EXASHXE/btc-quant-agent-public`.
**Dedicated independent science/architecture branch:** `feature/v06-bline-g2-r3-p1-alternative-engine-design-sol61-r1`.
**Branch START_SHA:** `b74b932da32e4b5bbe2477c2de014f94719d6a93`. It exists remotely at that exact commit, created by Controller, with no A/B code changes.
**Suggested fresh sibling worktree:** `/root/workspace/project/quant-v0.6/g2-p1-alt-engine-sol-r1`; create only after checking directory absence/owner.
**A frozen implementation target:** `b5d34aacd36dc27454944a22436db555c3f6eeb8` on `feature/v06-bline-g2-overnight-discovery-a` (READ-ONLY).
**Independent B verified failure SHA:** `52ee5f1e582defbfb0bb3c8bb29101a1d40d9cd7` on B's independent branch (READ-ONLY).
**B audit original dispatch:** `5f9b7f75215b394ad86d49b468e7acd9a89c23a2`.
**Frozen eight strategy formula design:** `e5b2006a89441f7eb2ec900e508aff451106b87a`; accepted limited method `cf2d5cc33774cdcff7d709636305bba830e977ef`.
**v0.6 baseline code:** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`. No merge/change permitted here.

## 0 — Hard preflight and safety

1. Verify actual remote `CONTROLLER_DISPATCH_SHA`, branch HEAD (equal to START_SHA), Prompt immutable sha/link supplied by Controller in invoking message, B final commit/parent, A exact target and v0.6 baseline. Work in a fresh sibling worktree; never checkout/reset/clean/stash A, B, P2, or `Quant-agent-sanitized`. If remote branch drift or local unowned changes: `BLOCKED_SCOPE_OR_GIT`.
2. Permitted reads: exact-code source for `r3_overnight`, frozen R3 method/registry, actual A/B hermetic adversarial tests and B matrix/receipts, public accepted H40/H41 audit *method/engineering primitives* where necessary. No sealed H41/H42 outcomes, private credential sources, current market rows, 1m real prices/Mark/Funding/OI bodies, protected old v0.3 final holdout, or external exchange APIs. Source code inspection is not data-body authorization.
3. Permitted NEW writes ONLY:
   - `docs/strategy_research/g2_r3/p1_alt_engine_sol_r1/**`
   - `evidence/v0.6/b_line/g2_r3_p1_alt_engine_sol_r1/**`
   - `reviews/v0.6/b_line/p1_alt_engine_sol_r1/**`.
   Do not touch `src/**`, `tests/**`, existing P1 A/B artifacts, Project status, Controller authority, candidate registry, fees, H40 CI/golden, protected paths. This is NOT another R4 patch.
4. Inspect truth hierarchy: actual source + frozen authority + independent observed defects > role A green CI/self-receipts > prose opinion. The independent B run `37928939579` failed ONLY old H40 golden despite **2828 pass/1 fail/2 skip**, and its new B tests intentionally assert target defects. The A run `37918930513` was **2844 pass/2 skip full suite**, but it did not exercise complex delayed-ACK adversaries. Neither number proves a safe engine.

## 1 — Mission (make exactly ONE architecture decision)

Select a **minimal, scientifically faithful, auditable, testable and tractable research replay engine** for the already-frozen R3 eight candidates. Optimize for smallest end-to-end implementation and ability to pass independent adversarial tests, NOT maximal object model, trading features, unbounded speed or hypothetical profits.

Compare these THREE options, with an explicit disposition:
- **OPTION A — Clean event-sourced research micro-engine**: minimal immutable journal, stable IDs, and double-entry/auditable owner reserve and liabilities; replace unsafe mutable `VirtualBook` and fix Retest event state only as original method requires; reuse *checked* OHLC/indicators/candidate formulas and B04 execution behaviors. Proposed default to seriously evaluate.
- **OPTION B — Vetted external event-driven backtest framework plus strict R3 adapters**: choose a concrete currently maintainable library only if actual documented version/license/event semantics are supported by source/provenance, and show adapter burden for mark PIT, frozen Funding ownership, ACK delays, 5% reserve/100 USDT kill, per-candidate books and cross-stage balances. Never assume off-the-shelf engine solves these.
- **OPTION C — Compositional event reducer + property-test oracle with no generic framework**: a limited R3-specific deterministic reducer/immutable state with independently checked invariant package; distinguish from A by smaller data model and explain why it avoids or inherits original flaws. Could be recommended if it is simpler and remains complete.

Choose **one** with: estimated engineering surface in files/modules (no fabricated time promise), number of new state types/events, ability to preserve 8 frozen candidates unchanged, PIT integrity, funding correctness, testability, isolated source branch, dependency/license risk, failure stop, migration/compatibility tradeoffs, and actual incremental benefit vs the failed A graph. If none genuinely acceptable within one finite implementation+audit, choose `NO_FEASIBLE_ENGINE_FOUND` and terminate instead of sending another patch set.

## 2 — Explicit diagnosis: distinguish actual production blockers from out-of-contract attacks

Use independent B report exact evidence; do NOT blindly endorse every adversarial fixture as a reachable production path:

- **Sufficient CRITICAL grounds:** B05 pending *economically exited but not ACKed* −169.336545 USDT loss invisible to risk kill/capital before exit ACK, with false positive available capital; B03/B07 payable Funding `1.00` vs reserved `0.40` releases owner reserve at Stage7 while cash debit delayed until Funding ACK, so 0.60 uncovered and 0.40 prematurely available. These alone invalidate current risk/accounting.
- **Other real code concerns:** B01 same-close duplicate Mark conflict (50000 vs52000) and tie/order sensitivity; B02 contradictory repeated ACK IDs and cooldown rewind; B06 state advancement only latest 1h after gaps, same-hour cancel/rebreakout not proven by method.
- **Guard method/fixture validity:** B's `open_time_ms=S−5000ms` Stage1 early exit ACK call is **not an aligned 1m replay step**; label API-only pathological input until proven reachable. B's Stage8 reading current-bar close for **ex-post reporting** is not automatically decision look-ahead, unless it influences earlier decisions; separately assess chronology. Do not use these ambiguities as excuses to waive independent verified B05/B03/B07 blocker semantics.
- **Good existing primitives:** B04 stop-first, adverse stop gap, capped favorable target, conservative minute-end economic exit and 04H/12H expiry; code may be reused **only** after its clock contract is isolated. Existing eight candidate IDs and original strategy formula/indicator source to be reused only if independently proven not to propagate PIT/state bug. H41 accepted concepts not H41 candidate outcomes.

Create a precise `FINDING_TO_REDESIGN_MATRIX`: each B01–B07 finding severity, actual reachability (verified live-engine path/isolated API/uncertain), causal minimal test, new engine state/event/ledger rule that prevents it, and independent acceptance assertion.

## 3 — Define the minimum production scientific engine contract

Publish concrete event model and state transition tables before any code handoff. Do NOT silently increase trading capabilities, candidate roster or new input sources.

**Canonical bounded event types** (field names optional but semantics MUST be explicit):
`ObservedMinuteBar`, `ObservedMark`, `SignalAtDecision`, `OrderReserved`, `EconomicFill`, `FillAck`, `EconomicExit`, `ExitAck`, `FundingObligation(position_id,S)`, `FundingAck`, `RiskKill`, `EndOfMinuteReport`.
Every event specifies stable unique event ID, cause/position/order IDs, `economic_at_ms`, `available_at_ms`, typed payload digest, candidate ID, symbol and original source/parent; duplicate ID with DIFFERENT payload is `CONFLICT_FAIL_CLOSED`; duplicate exact payload is idempotent. Immutable event journal sequence/tie order.

**Two-clock scheduling**: process only eligible information `available_at<=decision_cut`; complete 1m/bar close and conservative 60s lag semantics, no bar-body high/low/close current minute known before it closes. Economic exit may occur S−1ms but risk pre-ACK loss must be conservatively visible at next legal as-of checkpoint. An economic-equity curve at minute-end may use that already completed minute OHLC/Mark *only* as post-hoc label; formally segregate it from decision equity. No future information backfills earlier orders.

**Money and double-entry/owner obligation**: choose actual account types and show journal transfers when:
1. pending entry reservation converts on economic fill and awaiting ACK;
2. entry fee economically accrued, cash debited once on ACK;
3. exit PnL crystallizes pre-ACK; conservative net economic realized loss counts for risk/size, positive pending gains cannot be immediately reused; loss settled to cash once;
4. Funding S obligation qualified by per-position exposure interval and `[S−15000,S+15000]`, book payable **before** corresponding cash ACK and keep owner reservation/liability through ACK, including funding shortfall;
5. kill freezes new entries; closing/late ACK cannot reset kill or rewind cooldown;
6. all assets/positions retain owner-only reserves.

**Invariants as implementable exact Decimal assertions** at every transition (not only terminal):
`total_reserved_funding == sum(owner_reserved_funding including pending/unsettled)`;
`total_unpaid_funding == sum(owner_payable_funding)`;
`total_cost_commitments == sum(owner_remaining_cost_commitments)`;
`free_spendable_capital <= conservative_equity_after_visible_pending_losses - buffers - ALL reserved/payable`;
`uncovered_shortfall != 0 => specific owner liability posted`;
`cash_delta == settled_trade_net_pnl + itemized_account_flows` after all ACK and fees, each event exactly once;
`no same-symbol simultaneous live positions`;
`cooldown_until = max(previous, new_valid_cooldown)`;
`newest available mark close monotonically nondecreasing` with same-close price conflict fatal/deterministic frozen source rule.

**Funding causality at S**: ownership tolerance extends through S+15s. The engine must not claim to know future S+15s exposure at S−before; conservatively reserve conditional obligation, then finalize when causally ascertainable and account for ACK availability. Do not retroactively alter earlier decisions. Frozen proxy schedule/costs may be used solely in synthetic test; do not make cost assumptions more favorable.

**Retest**: scan all completed 1h bars not previously reduced, in chronological order; compute breakout/confirmed/canceled/expired states and 3 completed-hour limit consistently across skipped invocation/cooldown. Show explicit spec choice for dual-role same-bar (cancel and new breakout); if frozen METHOD_DESIGN does not resolve, require a separate Controller `P3_METHOD_AMENDMENT_REQUIRED` before implementation, without inventing behavior.

**Compatibility**: list what may safely remain: `CandidateRegistry`, stable R3 IDs, `Bar1m/MarkBar1m` canonical contracts, pure indicators, time-aggregation, B04 exit price function (if pure); list what MUST be replaced, e.g. live lifecycle, Stage1/Stage7 imperative money movement, ACK ID sets, reserve totals with side dictionaries, risk accounting, Retest missing-hour progression. No intermediate artifactual inheritance of `VirtualBook` side state.

## 4 — Required independent synthetic oracle / acceptance criteria

Create an **implementation-ready, not-yet-run** 20–35 item case matrix with exact inputs/expected states, including at minimum:

- existing B01–B07 independent adversarial variants, B04 preservation;
- same-close contradictory Mark order permutations, stale and not-yet-available marks, ex-post-vs-decision segregation;
- contradictory ACK payload same ID, 2x/3x duplicate identical, delayed old ACK vs new position, cooldown monotonicity;
- 1.00 Funding event with BTC reserve 0.40 and ETH reserve 2.00; hold 1.00 total BTC payable through ACK, ETH unchanged; delay/reorder funding ACK, S-stage settlement and pre-S economic exit inside uncertainty window;
- realized −169.336545 USDT pre-exit-ACK and unacknowledged positive gains; risk kill by first legal checkpoint and no extra entry; report exact risk/free-capital states;
- crossed-gap intermediate 1h Retest cancellation under skipped calls, no dual-role same-bar unless newly authorized;
- 4h/12h BASE/STRESS ineligibility, ordinary winning/losing synthetic nonempty `ReplayEngine.run_simulation` w/ 240h warmup, true Funding, fees, exit ACK, zero terminal pending balances and exact cash/net reconciliation;
- determinism under permutations of independent events and source ordering, but never reorder causally dependent events, and exception-on-contradictory payload;
- zero data bodies, no protected access, no unrealistically good maker fill.

**Independent proof protocol:** positive tests authored by implementing Gemini are NOT enough. One separate B/Sol independent suite, on a frozen exact implementation SHA and isolated archived source, must assert source- and spec-grounded correct outputs; a green full CI can coexist with semantic failures. Limit validation to a focused synthetic test suite during build plus ONE final independent behavioral audit. If a material independent failure remains, STOP alternative-engine route; do not again spiral R4/R5.

## 5 — Decision and downstream implementation handoff

Deliver a Controller-readable **implementation contract DRAFT** for the selected option:
- new isolated implementation branch base and suggested worktree (not A/B original);
- allowed files and forbidden paths, exact baseline and methods;
- module/file design with call interfaces, states, ownership and transition precedence;
- existing pure source reuse proven vs proposed and explicitly prohibited legacy methods;
- authoritative clock table per minute, money transfer journal account matrix;
- 20–35 named test cases and acceptance thresholds;
- bounded development/verification effort description without timeline promises;
- risk reduction vs A defects, with "one coherent build + one B independent audit" budget and stop criteria;
- required exact Controller freeze/dispatch and new first-pushed market prereg path only **after** implementation acceptance and P2 admission.

**Three deliverables, docs-only exact paths**:
1. `docs/strategy_research/g2_r3/p1_alt_engine_sol_r1/ENGINE_OPTION_DECISION_AND_EVENT_LEDGER_DESIGN.md`.
2. `evidence/v0.6/b_line/g2_r3_p1_alt_engine_sol_r1/ENGINE_OPTIONS_AND_INVARIANT_ORACLE_MATRIX.json`.
3. `reviews/v0.6/b_line/p1_alt_engine_sol_r1/P1_ALTERNATIVE_ENGINE_CONTROLLER_HANDOFF.md`.

**Exactly one terminal**: `ALT_ENGINE_DESIGN_READY_FOR_CONTROLLER`, `P1_SPEC_AMENDMENT_REQUIRED`, `NO_FEASIBLE_ENGINE_FOUND`, `BLOCKED_SCOPE_OR_GIT`, `BLOCKED_NOT_PUSHED`. No self-acceptance, no automatic code authorization or P3/P4.

**Delivery:** ensure actual read-first and no protected reads; validate JSON schema/path allowlist/markdown links and `git diff --check`; non-force commit and push to `feature/v06-bline-g2-r3-p1-alternative-engine-design-sol61-r1` automatically; verify `git ls-remote` exact HEAD, parent(s), changed paths, actual CI mode/status, and return `TASK_ID, CONTROLLER_DISPATCH_SHA, PINNED_PROMPT_SHA, START_SHA, FINAL_REMOTE_SHA, PARENT, TESTS_OR_STATIC_CHECKS, NO_MARKET_READS, CONTROLLER_ACTION, TERMINAL_VERDICT`. No same-commit uncomputable self-hash.

**Project gates preserved:** A/B and Sol original SCIENCE review immutable; P2 `LOCAL_ROOT_UNKNOWN`; P3 first-pushed prereg NONE; P4 empirical market body NONE; TESTNET/LIVE NONE. Faster trustworthy learning > creating additional audit bureaucracy.
