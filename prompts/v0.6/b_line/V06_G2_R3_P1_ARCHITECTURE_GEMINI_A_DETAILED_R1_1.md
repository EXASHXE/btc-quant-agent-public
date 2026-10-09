# V06 G2 R3 P1 — Gemini A architecture refactor: detailed execution contract R1.1

**Scope:** Clarification of the EXISTING task `V06_G2_R3_P1_ENGINE_ARCHITECTURE_REBUILD_V1`, not a second implementation or new authority. Read and obey the [complete original implementation contract](https://github.com/EXASHXE/btc-quant-agent-public/blob/9398c016b8b7134905eb40f61426f91a2cfb8e43/prompts/v0.6/b_line/V06_G2_R3_P1_ENGINE_ARCHITECTURE_REBUILD_V1_GEMINI_A.md) in full. This detailed prompt **adds** implementable sequence, test matrices, and audit-proof receipt requirements. Any difference in permission/strategic semantics fails closed against the immutable [Controller architecture authority](https://github.com/EXASHXE/btc-quant-agent-public/blob/e5fcd76370a1b03d7d83b825af6a8cac842b1ae5/reviews/v0.6/b_line/V06_G2_R3_B_R2_TERMINAL_CONTROLLER_ADJUDICATION_AND_ENGINE_ARCHITECTURE_REPLAN_R1.md).

**TASK_ID:** `V06_G2_R3_P1_ENGINE_ARCHITECTURE_REBUILD_V1`
**CONTROLLER_DISPATCH_SHA:** `e5fcd76370a1b03d7d83b825af6a8cac842b1ae5`.
**A branch:** `feature/v06-bline-g2-overnight-discovery-a`.
**Existing A worktree:** `/root/workspace/project/quant-v0.6/g2-overnight-discovery-a`.
**Exact start:** `2c60b0653d3619eedf457753511a9ecc84c1cd5b`.
**B immutable finding source:** `068a4005f68b5ee4a970063cb1f3bc524a08784a`.
**Original R3 eight candidates:** `e5b2006a89441f7eb2ec900e508aff451106b87a`.
**Method publication:** `cf2d5cc33774cdcff7d709636305bba830e977ef`; method proposal detail `35d2b8488fd6fbdab0d3d7ff8cf2b84ee5b60b6f` is NOT an independent preregistration/price-data grant.

**Read-only preflight (required):** Verify remote Git source for the Controller decision and BOTH prompts. Before touching code, validate current A branch/HEAD/local clean status/remote origin/remote A HEAD, and verify the fixed B source commit; preserve other worktrees. If an authorized branch has moved or contains unowned changes, STOP `BLOCKED_SCOPE_OR_GIT`, no reset/stash/clean/force push. This addendum does not relax the original allowed path list, attempt budget, zero real data/exchange reads or release gates.

## 1. Runbook — do NOT substitute planning for implementation

Execute in this order, with no permission checkpoints for each substep (only stop on explicit scope, data, semantic or code-safety blockers):

1. **Baseline:** Read B final matrix, receipt, executable synthetic counterexamples and R2 source. Freeze a list of case IDs, old observed failures, independent expected output, and intended positive A regression test. Do not edit B files or use B's old bug-asserting tests as evidence of a fix.
2. **Design FIRST:** Create the architecture design/handoff under `docs/strategy_research/g2_r3/prep_a/architecture_v1/`. Document position-ID ownership, lifecycle states, two clocks, event IDs, one settlement window, per-owner funding, reserve conservation and exact fail-closed behavior.
3. **Implement in dependency order:** identity and event journal → per-owner reserves and pending trade lifecycle → funding settlement attribution and deferred finalization → risk of economically filled but not yet ACKed positions → monotonic Mark ingress → wall-clock Retest expiry → compatibility/E2E.
4. **Test each slice:** A positive regression for each B defect, then multiple cross-stage permutations. At the terminal gate run scoped Python 3.12 R3 tests, available 3.13, Ruff, compileall, JSON parse and diff checks. Do not repeatedly run unrelated 12-minute H40 CI during internal edits.
5. **Publish full evidence:** Required original three artifacts, plus measured event timelines, algebraic reserve/mark/position-ID traces; then non-force commit and push the original A branch. Verify remote SHA/parent/changed scope/CI status. Without verified remote push: `BLOCKED_NOT_PUSHED`, never READY.
6. **Bounded stop:** One coherent architecture work package with bounded internal same-design corrections. If semantic conflict: `BLOCKED_SPEC_CONFLICT`; if unsolved material invariant: `ARCH_V1_IMPLEMENTATION_FAILED_REPLAN_ALTERNATIVE_ENGINE`. Do not start independent patch rounds R4/R5.

## 2. Exact model obligations — explain them before editing source

| Authority | Required fields / indexing | Immutable invariant |
|---|---|---|
| Economic position | unique position_id, order_id, symbol, q, entry/exit event ms, ACK states, original 4h/12h hold | Position identity owns PnL and funding; a symbol-only map is at most a current-open index |
| Event receipt | unique message/event ID, position_id, created/economic/available ms, kind, amount, processed ID | Exactly-once cash/fee/funding; different events cannot be merged |
| Exposure interval | position_id, start_ms, end_ms, q | Qualify funding independently for each overlap of the existing [S−15s,S+15s] window |
| Pending trade | trade_id, position_id, effective exit, exit ACK, unresolved settlements, finalized flag | Early exit ACK must not erase an unsettled funding liability |
| Funding obligation | key (position_id, settlement_S), owner quantity, model rate, debit, status, ACK ms | Never key by (symbol,S), take max(quantity) across owners, or match exit by symbol |
| Reserve ownership | order/position ID, entry commitment, entry fee, exit cost, remaining future funding, unresolved settlement, release flags | Individual and aggregate reserved values reconcile exactly at every stage |
| Latest usable mark | symbol, close_ms, available_at_ms, close/source_id | Effective availability is max(close_ms,available_at_ms); newest eligible CLOSE wins, regardless of arrival order |
| Retest state | candidate ID, symbol, direction, breakout completed hour, last completed hour | Three-hour window advances by elapsed CLOSED clock hours; cooldown/EMA/vol filters cannot freeze elapsed time |

State transitions must be explicit, e.g. RESERVED → ECONOMIC_FILL_UNACKED → ACKED_OPEN → ECONOMIC_EXIT_UNFINALIZED → EXIT_ACK_SETTLEMENT_PENDING → RECONCILED_FINAL. If the current code keeps legacy `book.positions[symbol]` for compatibility, implement a safe view/index, **not** a second conflicting authoritative ledger. Do not enable simultaneous active positions on one symbol if the original strategy did not permit it.

## 3. Exact reserve / capital conservation

**Before any actual reserve debit**, compute and assert:

- `C_o == sum(outstanding_cost_reserve_by_owner)`.
- `R_f == sum(outstanding_funding_reserve_by_owner)`.
- Each owner reserve >= 0 and no cross-owner release.
- `settlement_event_id=(position_id,S)` applies economic funding cost and actual cash debit **once**, and correct trade.net_pnl gets it **once**.
- If `owner_remaining_funding_reserve=0.40` and expense `debit=1.00`, use that owner's 0.40 and record the additional 0.60 as a payable / actual expense belonging to that owner. Do **not** decrement ETH's separate 2.00 reserve. Do not use `max(0,R_f-debit)` to hide a negative pre-clamp balance.
- At a fully settled FLAT terminal book, `C_o=R_f=0`, unsettled liabilities=0; `cash_final-cash_initial == sum(all_finalized_net_trade_pnl) + explicitly_itemized_other_flows`. In intermediate steps reconcile outstanding obligations rather than falsely requiring terminal equality.
- Decision equity cannot include unavailable gains. Economically opened (but not ACKed) positions cannot hide a causally observable -125 USDT drawdown, nor free capital without a matching live obligation. Trigger existing 100 USDT kill protection at the FIRST authorized as-of risk checkpoint, not retroactively from unpublished 1m OHLC.

**Nonnegativity by clipping is NOT a proof.** For every reserve movement print owner ID, old reserve, applied amount, uncovered fee, new reserve, aggregate expected sum, and actual aggregate sum in synthetic receipts. Keep Decimal and frozen fee/stress/ATR/stop/hold values unchanged.

## 4. Critical multi-stage timelines — MUST appear in tests

**Pre-S exit ACK race**: At [S−60000,S) a position stops, conservative economic exit=S−1ms; exit ACK available at S. At minute-open S, Stage 1 can process its exit ACK but the closed position remains an owner of S funding because its interval intersects [S−15000,S+15000]. Stage 7 must record S charge against that exact position before true terminal finalization. Subsequent Funding ACK is applied once. Cash, trade net PnL, liabilities and ETH reserve reconcile. No future OHLC leaks into S−60000 decision.

**Close/reopen at S**: P1 q=.05 exits and P2 q=.01 enters at S under existing no-same-open-reentry fences where applicable (synthetic event-ledger fixture may test both obligations even if strategy scheduler forbids such a path). Each position qualifies independently under the conservative original ownership rule; P1 charge reflects .05, P2 reflects .01; never charge both through symbol key or assign `max(.05,.01)` to P2.

**Late earlier exit ACK**: Old position outside S funding window has a delayed exit ACK; newer same-symbol position overlaps S. Pending-exit matching by `position_id`, not `trade.symbol`, must leave old position's funding zero.

**Out-of-order Mark**: Fresh close at S+60s becomes available S+90s (e.g. 51000); older close at S is delayed until S+120s (e.g. 49000). When both are eligible at S+120s, newest completed close wins (51000), and accepted mark never regresses.

**Retest:** Breakout H25; H26–H29 filtered by cooldown; attempt at H30 is five CLOSED hours later and must not resurrect a Retest with 3-hour limit. Hour 3 unsuccessful confirmation expires old breakout correctly; only register a fresh breakout there if original scientific method unambiguously permits it, else `BLOCKED_SPEC_CONFLICT`.

**B02/B04 regression protection:** duplicated ACKs 2×/3× settle once; same-bar SL+TP chooses SL; adverse gap is not improved; intraminute exit is recorded only with conservative minute-end semantics; preserve both 240m and 720m horizons and their cooldown.

## 5. Minimum positive test matrix (no bug-assertion theater)

Test REAL implementation paths, not hand-populated final balance snapshots:

| Area | Positive assertions |
|---|---|
| Mark | Future mark rejected, out-of-order freshest close selected, 120s stale veto, multisymbol isolation, arrival permutation |
| Funding | Pre-S ACK race, close→reopen 2 position IDs, late old ACK, duplicate settlement, charge per ID not max quantity |
| Reserves | Funding owner shortfall, independent other-symbol reserve unchanged, no pre-clamp negative, flat reconciliation, kill + delayed ACK |
| Risk | Pre-ACK loss trips kill when causally available, pre-ACK gain does not increase available capital, new entries blocked after kill |
| Retest | Five-hour cooldown gap expires stale event, exact third-hour semantics, invalid intermediate EMA/vol still consumes elapsed hour, candidates permutation-invariant |
| Execution | B02 dedup, B04 SL-first/targets/gaps, 4h+12h expiry, BASE+STRESS, full ReplayEngine mark→signal→fill→ACK→exit→funding→flat |

For each B01/B03/B05/B06/B07 original blocker, retain a before/after row with `case_id, exact input timeline, old failing value, independent expected value, NEW observed value, actual pytest node ID, source reference, PASS/FAIL`. Preserve B02/B04 passing behavior. A green test that asserts the **R2 failure** is expected is not a green repair.

Do not invent an E2E winner by modifying fixed strategy thresholds. If a frozen STRESS geometry case is ineligible, report eligibility/WAIT and choose a pre-existing eligible synthetic fixture rather than changing R3 design. The frozen eight IDs remain unchanged.

## 6. Verification, artifacts and delivery

**Required exact artifact paths and test namespace** are those in the original prompt: design `ENGINE_EVENT_LEDGER_DESIGN_AND_HANDOFF.md`, architecture before/after JSON, synthetic execution receipt JSON, and `tests/test_strategy_research_r3_architecture_*.py`. Add to the design document a per-minute 8-stage table, position/ACK/funding ID relationship diagram (text), per-owner reserve reconciling table and each impossible-event fail-closed error.

Record separately `local_focused_tests`, `remote_ci_conclusion` and `inherited_H40_failure`. The H40 scientific hash failure reproduced in both A and B full CI: do not waive/change/skip the golden, repeatedly rerun full tests, or report `CI=PASS` on a failing run.

**Evidence commit identity:** a JSON included in its own Git commit cannot know that same commit's SHA in advance. Record actual inputs and tested tree/working version, then give exact SOURCE/EVIDENCE SHA, parent and final remote HEAD in your post-push response. If needed a bounded evidence-only follow-up commit can attest to the previous exact SHA, preserving chronology.

**Terminal required fields:** `TASK_ID, PROMPT_SHA, CONTROLLER_DISPATCH_SHA, A_START_SHA, IMPLEMENTATION_SHA, EVIDENCE_SHA, PUSHED_BRANCH, REMOTE_PUSH_VERIFIED, FINAL_REMOTE_SHA, CHANGED_PATHS, TESTS, CI, B01/B02/B03/B04/B05/B06/B07_VERDICTS, MATERIAL_BLOCKERS, TERMINAL_VERDICT`. Proactively commit/push non-force only to the original A branch and verify `ls-remote`; local-only commits are NOT delivered. The only READY status permitted is `ARCH_V1_SYNTHETIC_READY_FOR_INDEPENDENT_REVIEW`, which does NOT imply Controller engine acceptance, historical-body access, TESTNET or real-money permissions.

**No silent data reads:** real price/mark/funding bodies=0, protected holdout reads=0, exchange order calls=0. These boundaries and allowed edit paths are unchanged from original dispatch.
