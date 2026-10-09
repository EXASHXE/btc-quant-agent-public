# Gemini B — v0.6 G2 R3 P0 independent final R2 behavioral re-audit

**TASK_ID:** `V06_G2_R3_P0_B_INDEPENDENT_R2_FINAL_BEHAVIOR_REAUDIT`  
**CONTROLLER_DISPATCH_SHA:** `20ad1e442fb7cce58c618c4aac1e2a3b6241f647`  
**Read/verify immutably:** [Controller L2 CI adjudication & B authorization](https://github.com/EXASHXE/btc-quant-agent-public/blob/20ad1e442fb7cce58c618c4aac1e2a3b6241f647/reviews/v0.6/b_line/V06_G2_R3_P0_A_R2_CONTROLLER_RECEIPT_CI_ADJUDICATION_AND_B_REAUDIT_DISPATCH.md). This is a **real commit** with the Controller decision; verify existence/content/lineage before task. Prompt itself is a distinct later immutable publication; use the pinned Prompt ref in the invoking link, not a floating docs HEAD.

**REPOSITORY:** `EXASHXE/btc-quant-agent-public`  
**B_BRANCH:** `feature/v06-bline-g2-overnight-verifier-b`  
**B_EXPECTED_START_SHA:** `f1ec703b7c7276582f324ac25b9d1000f1b5ef14`  
**A_IMMUTABLE_TARGET_SHA:** `2c60b0653d3619eedf457753511a9ecc84c1cd5b`  
**A_R2_PARENT_SHA:** `5c542edd418a74b440162610fd540b1f01e423d3`  
**R3_METHOD_SHA:** `cf2d5cc33774cdcff7d709636305bba830e977ef`  
**FROZEN_EIGHT_CANDIDATES:** `e5b2006a89441f7eb2ec900e508aff451106b87a`  
**MARKET_DATA_BODY:** `FORBIDDEN` | **OLD_PROTECTED_HOLDOUT:** `FORBIDDEN` | **TESTNET/LIVE:** `NOT_AUTHORIZED`

## 1. Isolated worktree preflight

- Launch in `/root/workspace/project/quant-v0.6`, reuse ONLY `g2-overnight-verifier-b`, its existing B branch. Never create another B branch or touch A's live worktree.
- Read-only inspect `git -C "$ROOT/g2-overnight-verifier-b" status --porcelain=v1 --untracked-files=all`, exact HEAD, branch and `origin` URL. Stop if dirty/unowned, branch drift or remote mismatch; do not clean/reset/stash/force.
- Verify remote B HEAD = `f1ec703b7c7276582f324ac25b9d1000f1b5ef14`, remote A HEAD = `2c60b0653d3619eedf457753511a9ecc84c1cd5b`, original A parent = `5c542edd...`, and Controller commit and this pinned Prompt. If A/B moved: `BLOCKED_SCOPE_OR_GIT` with identity evidence, no silent rebinding.
- Access exact A code from immutable Git source objects in ephemeral synthetic scratch; serialize any shared Git fetch under existing root `.g2_p0_worktree.lock`. Never edit A or B original evidence, A branch, other worktrees or protected results.

**Allowed B changes ONLY:** `scripts/strategy_research/r3_verification/**`, `tests/test_v06_g2_r3_verifier_*.py`, `docs/strategy_research/g2_r3/prep_b/repair_r2/**`, `evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/**`. No root CI, H40 golden, source A, strategy parameters/IDs/costs, external provider/private exchange, real market price/mark/funding bodies.

## 2. Decision-specific review — implement independent positive oracles, NOT A assertions

Immutable B R1 issues: [B01–B07 matrix](https://github.com/EXASHXE/btc-quant-agent-public/blob/f1ec703b7c7276582f324ac25b9d1000f1b5ef14/evidence/v0.6/b_line/g2_overnight_p0_b/repair_r1/A01_A08_INDEPENDENT_MATRIX.json), [B R1 dynamic receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/f1ec703b7c7276582f324ac25b9d1000f1b5ef14/evidence/v0.6/b_line/g2_overnight_p0_b/repair_r1/INDEPENDENT_SYNTHETIC_EXECUTION_RECEIPT.json). [Gemini A R2 changed-source + self receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/2c60b0653d3619eedf457753511a9ecc84c1cd5b/evidence/v0.6/b_line/g2_overnight_p0_a/repair_r2/R2_B01_B07_BEFORE_AFTER_MATRIX.json). Old B R1 tests assert the *bugs* occur on A R1; do not mistake their passing as proof R2 corrected.

**Core executable tests against A exact source + B independent oracle:**
1. **B01 Mark PIT:** eligible mark at close/available boundary, lagged mark, future/unavailable mark, out-of-order same-symbol mark, multiple symbols and stale timeout; prove nonzero mark ingress into real `ReplayEngine.run_simulation` without current-minute close access. Compare source-side emitted as-of mark to event stream, not just a mocked `VirtualBook.last_available_marks`.
2. **B02 ACK idempotence:** duplicate and reordered entry/exit/funding ACKs 2×/3×, stale ACK after economic position closed, distinct orders same symbol across time; stable unique IDs per event, fees/cash/PNL exact-once, no phantom equity or resurrected position.
3. **B03 settlement:** `[S−15000,S+15000]` overlap on before/at/after S; closed before window 0, entry/SL in minute S owns S as frozen, multiple distinct positions with same symbol but disjoint ownership intervals around S, position close then reopen in the S minute (if possible), duplicate S. **Do not silently aggregate by maximum position size if two economic positions can be chargeable**, and ensure allocation maps to correct `position_id` and pending ACK/trade.
4. **B04 minute-end SL/TP:** causal OHLC future-open guard, forced SL before TP same bar, gap stop adverse open, target capped, minute-end timestamp + holding/cooldown matching 4h/12h horizon and decision/ACK clocks; no hindsight at opening.
5. **B05 decision/economic equity and kill:** pre-ACK unrealized loss can affect economic safety and not create spendable positive balance; canceled pending order releases only its own reserves; remaining open/exit obligations unaffected; forced exit, delayed exit ACK, duplicate ACK and restart-equivalent serialization if supported. Negative reserves must not be hidden by `max(0,...)`; check **pre-clamp conservation algebra** against per-position and order obligations.
6. **B06 retest:** three **elapsed** completed hours including failed vol/EMA, no double-step from candidate iteration, intermediate adverse extrema included, no stale fourth-hour confirmation, 04H/12H+LONG/SHORT isolation and order invariance.
7. **B07 funding ledger:** funding cash charge once, per-position reserve debit vs aggregate exact, flat-book residual 0, late funding ACK and exit ACK permutations, reserve exhausted before settlement, kill/reentry, equity conservation and no negative aggregate pre-clamp.

Also verify R1 accepted A01/A02/A04 remain unchanged, the exact eight frozen candidate IDs/formulas, BASE/STRESS cost proxy, no surprising code drift, original holdout segregation. Use a small **synthetic end-to-end** A `ReplayEngine` scenario with actual mark intake → signal → sizing → entry/fill ACK → exit/funding/cooldown → flat ledger; include 4h/12h where possible. If a case cannot be constructed under frozen specs, report `INCOMPLETE` with limitation, do not silently drop critical test.

## 3. CI failure classification

At A exact SHA [CI #37888079460](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37888079460) **FAILED**, full suite `2830 passed / 1 failed / 2 skipped / 9 warnings`. The only failure was inherited H40 `test_p09_through_p18_exact_scientific_graph` scientific projection hash mismatch; **do not rewrite or skip H40 golden**, do not claim CI green. Its relation to code R2 is unproven beyond non-overlapping changed-file scope and already-known stability debt. For this B verification use scoped Py3.12 focused tests, Ruff/compile + JSON validation only; inherited H40 release gate remains a separate tracked debt. Any failure in targeted R2/B oracle tests remains a real P1 blocker.

## 4. Required output, tests and terminal push

Add immutable *new* artifacts only under B repair_r2:
- `evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/B01_B07_R2_INDEPENDENT_BEHAVIOR_MATRIX.json`
- `evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/R2_B_INDEPENDENT_SYNTHETIC_EXECUTION_RECEIPT.json`
- `docs/strategy_research/g2_r3/prep_b/repair_r2/B_R2_FINAL_CONTROLLER_HANDOFF.md`
- Positive independent synthetic tests under allowed B path; include actual per-case values and original A R1 vs new R2 comparison, status PASS/BLOCKED/INCOMPLETE and test references.

Tests: Python3.12 scoped B oracle, optional 3.13, `ruff`, `compileall`, targeted source test if helpful, `git diff --check`, JSON parse. Avoid full-scope H40 golden rerun. Preserve failed outcomes; no result-informed threshold changes. One terminal evidence package, no recursive new implementation review loop.

After tests, proactively **commit and push** on **original B branch** with non-force `git push -u origin feature/v06-bline-g2-overnight-verifier-b`. Verify `ls-remote` exactly matches final commit, parent/changed paths allowlist, CI link/status where available, and return `REMOTE_PUSH_VERIFIED=true`, exact branch/final SHA and prompt+dispatch identities. A local commit is NOT delivered.

**Allowed verdicts only:**
- `R2_B_SCOPED_SYNTHETIC_BEHAVIOR_PASS_FOR_CONTROLLER`
- `R2_B_SEMANTIC_BLOCKED__REPLAN_ENGINE_ARCHITECTURE` (provide smallest source/trace counterexample)
- `R2_B_INCOMPLETE_DYNAMIC_CROSSCHECK`
- `BLOCKED_SCOPE_OR_GIT`
- `BLOCKED_NOT_PUSHED`

**Bound:** This is one final independent review of R2, not permission for R3/R4 iterative repair. Findings go to Controller for final L2 accept/replan. No Alpha or release grants: `EMPIRICAL_PRICE_BODY_AUTHORITY=NONE`, `TESTNET=NOT_AUTHORIZED`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`.
