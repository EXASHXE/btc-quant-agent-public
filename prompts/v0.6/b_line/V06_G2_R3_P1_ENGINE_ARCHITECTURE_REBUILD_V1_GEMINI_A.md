# quant-agent v0.6 — Gemini A P1 Engine Architecture Rebuild V1 (one bounded implementation package)

## 0. Immutable authority / start identity — READ BEFORE WORK

**TASK_ID:** `V06_G2_R3_P1_ENGINE_ARCHITECTURE_REBUILD_V1`  
**CONTROLLER_DISPATCH_SHA:** `e5fcd76370a1b03d7d83b825af6a8cac842b1ae5` — **genuine Git commit**, containing [Controller R2 terminal adjudication and architecture contract](https://github.com/EXASHXE/btc-quant-agent-public/blob/e5fcd76370a1b03d7d83b825af6a8cac842b1ae5/reviews/v0.6/b_line/V06_G2_R3_B_R2_TERMINAL_CONTROLLER_ADJUDICATION_AND_ENGINE_ARCHITECTURE_REPLAN_R1.md). This Prompt is separately committed later; use the immutable Prompt ref supplied by Controller and verify its Git blob. Both objects must be verified; a 40-hex-looking string alone is not authorization.

**Repository:** `EXASHXE/btc-quant-agent-public`  
**Owned existing worktree:** `~/workspace/project/quant-v0.6/g2-overnight-discovery-a`  
**Authorized existing branch:** `feature/v06-bline-g2-overnight-discovery-a`  
**Exact START_SHA / expected remote A HEAD:** `2c60b0653d3619eedf457753511a9ecc84c1cd5b`  
**Independent B R2 evidence SHA:** `068a4005f68b5ee4a970063cb1f3bc524a08784a`  
**Original B findings report SHA:** `f1ec703b7c7276582f324ac25b9d1000f1b5ef14`  
**Frozen eight-candidate method SHA:** `cf2d5cc33774cdcff7d709636305bba830e977ef`; **registry/design:** `e5b2006a89441f7eb2ec900e508aff451106b87a`; **v0.6 base:** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`.

This is a **new bounded architecture contract**, not R2's third patch iteration and not empirical strategy discovery.

## 1. Worktree authority checks / hard fences

Start inside `/root/workspace/project/quant-v0.6`, then reuse the existing `g2-overnight-discovery-a` worktree **only**. Inspect exact branch, `git status --porcelain=v1 --untracked-files=all`, HEAD, remote identity `EXASHXE/btc-quant-agent-public`, and remote A/B refs. Require local A HEAD and remote A HEAD exactly `2c60b0653d3619eedf457753511a9ecc84c1cd5b`, B remote exactly `068a4005f68b5ee4a970063cb1f3bc524a08784a`, clean owned tree. Do NOT reset, clean, stash, change remote/branch, force push or delete/mutate another worktree. Halt `BLOCKED_SCOPE_OR_GIT` if any identity or ownership mismatch.

Read immutable B R2 [matrix](https://github.com/EXASHXE/btc-quant-agent-public/blob/068a4005f68b5ee4a970063cb1f3bc524a08784a/evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/B01_B07_R2_INDEPENDENT_BEHAVIOR_MATRIX.json), [receipt](https://github.com/EXASHXE/btc-quant-agent-public/blob/068a4005f68b5ee4a970063cb1f3bc524a08784a/evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/R2_B_INDEPENDENT_SYNTHETIC_EXECUTION_RECEIPT.json) and [review](https://github.com/EXASHXE/btc-quant-agent-public/blob/068a4005f68b5ee4a970063cb1f3bc524a08784a/docs/strategy_research/g2_r3/prep_b/repair_r2/B_R2_FINAL_CONTROLLER_HANDOFF.md). Inspect B independent **positive/negative** tests from immutable Git source objects read-only. Do not open B's live worktree, alter B tests, or rewrite B artifacts. Serialize shared Git fetch using existing `.g2_p0_worktree.lock` if needed.

**Allowed edits only:**
- `src/btc_quant_agent/strategy_research/r3_overnight/**` — refactor actual architecture behind stable research-sidecar external API. Preserve exact existing candidate IDs, rules, horizons, fee/funding/stress constants, study gates, lookahead and symbol ranges. No changing historical source dataset or secrets.
- `tests/test_strategy_research_r3*.py` — architecture positive invariant fixtures and regressions.
- `docs/strategy_research/g2_r3/prep_a/architecture_v1/**` — architecture specification and handoff.
- `evidence/v0.6/b_line/g2_overnight_p0_a/architecture_v1/**` — new machine receipts / before-after traces.

Forbidden: `H40/H41` scientific golden, `RC2` old final holdout, A-line scientific code/outcomes, B original tests and evidence, root CI selector, execution/trading/API, production credentials, other worktrees, real Parquet/ZIP/CSV/mark/funding body access, data download, external provider smoke, TESTNET and LIVE. ZERO historical-data empirical evaluations. No cost/rule/metric tuning.

## 2. Architecture target — these are mandatory, not optional bug-specific flags

**2.1 Immutable position/event identity**. Use `position_id` and stable economic/ACK/settlement IDs for every lifecycle transition. Active symbol index may limit simultaneous opens per symbol but **must not become a cash/funding ownership key**. Close→reopen same symbol during a funding window is two separate positions, each with its own deterministic interval/quantity/debit. `charged_settlements` must identify `(position_id,S)`, not `(symbol,S)`. Never match pending exit ACK by symbol alone. Dedup messages exactly once even after close; preserve B02 PASS.

**2.2 Explicit event timeline and delayed finalization**. Distinguish `bar_open`, `bar_close`, `available_at`, `economic_entry_at`, `economic_exit_at`, `ack_at`, `funding_S`, `finalized_at`. Preserve conservative full-minute OHLC SL-first/adverse gap/target cap; do not observe an intraminute outcome before completion. At `S`, Stage1 may consume a pre-S exit ACK before Stage7 funding: the position and its **unfinalized** trade/reserve owner must remain addressable by position_id until all qualifying settlements are resolved. Final cash/trade PnL must reconcile after delayed funding ACK without mutating protected historical outcomes. If a position was flat before the frozen window, no funding. Follow frozen settlement window `[S-15_000,S+15_000]`; no invented sub-minute trade tick timestamps.

**2.3 Exact per-owner reserve/liability ledger**. Represent entry/cost and funding obligations per order/position; `book.cost_commitment_o` and `book.funding_reserve_rf` derive from / assert equal exact remaining obligations. Reserve `max(0,...)` **must not hide a negative balance** on cancellation, settlement, kill, exit or funding ACK. If actual cost exceeds prepaid reserve, consume only the owned reserve and book the remainder as an economic cash liability at valid event time; never debit other position/symbol's funds. Explicit evidence: before/after `cash, fee/funding liability, reserved_by_owner, aggregate_reserved, economic_equity, decision_equity, risk_equity` and `net_trades+unsettled` reconciliation. Post-terminal flat fully settled book has zero owned reserves, zero unsettled liabilities and consistent cash/trade totals. Fail closed on any contradiction.

**2.4 Two-clock risk safety for pre-ACK positions**. The fill is economically live when executed even if acknowledgment is pending. Its negative economic PnL MUST affect conservative loss/kill decisions; unacknowledged positive gain MUST NOT inflate spendable decision equity. Pending filled notional may not be released without being replaced by an equivalent owned exposure/risk liability. A pre-ACK >100 USDT drawdown must trip existing kill threshold, disallow new orders and preserve obligations; no new threshold. Protect insolvency with correct as-of marks, never retroactively using data not yet available.

**2.5 Monotonic available market state**. For each symbol use effective mark availability `max(close_ms,available_at_ms)`, then choose greatest **completed close_ms** among all eligible marks, not last popped by arrival ordering. Carry latest valid mark forward, ignore delayed older arrivals, fail closed if older than 120s; do not leak future OHLC into decision. Test two eligible marks in one minute where older arrives later, out-of-order interleavings, same-close ties, multiple symbols, stale/missing marks, market gaps and duplicate mark events.

**2.6 Wall-clock retest state**. For each closed post-breakout hourly bar, advance/expire state based on `(current_completed_hour_close_ms - breakout_hour_ms) / 3600000` or equivalent exact clock; never count calls or skip elapsed hours because a cooldown/volatility/EMA predicate returned early. At end of the third allowed unconfirmed hour cancel according to original method; assess whether a fresh breakout on that third hour is permitted by **frozen method** before implementing. If semantics genuinely ambiguous, write `BLOCKED_SPEC_CONFLICT` rather than silently inventing retrospective rule. Preserve A04 isolation and B04 confirmed 4h/12h horizon/time handling.

**2.7 Deterministic API/harness**. Keep `ReplayEngine.run_simulation`, candidate registry and result receipt backward compatible where possible. If types must change, provide a deterministic migration/compatibility adapter **only** within the R3 sidecar and tests. Do not introduce external dependencies, network or trading writes. Event log/reconciliation should be bounded in test memory; record typed fail-closed diagnostic on impossible ordering.

## 3. Required evidence-driven development and finite exit gate

First reproduce each independent B R2 `BLOCKED` case on immutable **A R2 source** as baseline: `B01-D1, B03-D1/D2/D3, B05-D1/D2, B06-D1/D2, B07-D1/D2`. Preserve B02/B04 as positive regression guards. Then build **positive post-architecture invariants** on actual new A source, not by asserting observed bad values or mocking state around broken execution.

At least these independent-looking synthetic interactions must be exercised from real R3 sidecar:
- eligible old-vs-fresh mark arrival collision, replay remains fresher and causally correct;
- two same-symbol positions with distinct IDs eligible at S, each charged correct funding, including close/reopen and late earlier exit ACK;
- pre-S exit ACK consumed at S + settlement S, final `trade.total_funding_usdt` and cash/net agree, other symbol's reserve untouched;
- reserve shortfall debit > owner reserve, excess charged as liability without negative/clamped aggregate or borrowing another position's reserve;
- unacknowledged position 125 USDT economic loss, kill latch and no spendable phantom capital;
- 5 elapsed hours after breakout with 4-hour cooldown, stale retest cannot confirm; exactly 3 elapsed hour expiry;
- 2x/3x duplicate entry/exit/funding ACK and close↔reopen across same symbol;
- SL+TP same bar SL first, adverse gap, 240/720-minute positions, BASE/STRESS deterministic receipt;
- synthetic integrated `ReplayEngine` nonzero eligible marks, signal, entry, ACK, TP/SL/expiry and funding, then flat fully reconciled books. Do not change allowed strategy quality thresholds to produce tests.

**Required new artifacts:**
1. `docs/strategy_research/g2_r3/prep_a/architecture_v1/ENGINE_EVENT_LEDGER_DESIGN_AND_HANDOFF.md` — types, state machine, event ordering, position IDs, clock diagram in text, failure cases and exact compat impact.
2. `evidence/v0.6/b_line/g2_overnight_p0_a/architecture_v1/B01_B07_ARCHITECTURE_BEFORE_AFTER_MATRIX.json` — each independent B original counterexample and new expected/observed output, test/trace, typed status and explicit non-rescued failures.
3. `evidence/v0.6/b_line/g2_overnight_p0_a/architecture_v1/ARCHITECTURE_SYNTHETIC_EXECUTION_RECEIPT.json` — immutable inputs, test command logs, source/receipt SHA, eight IDs, zero protected market access, no exchange calls, all reported cash/reserve state and confidence/coverage. Distinguish tests run vs tests claimed.
4. New tests in `tests/test_strategy_research_r3_architecture_*.py` with positive invariants.

**Test economy:** focused Python 3.12 tests for R3 A source and new invariants, optional Python 3.13, Ruff/compile, JSON schema sanity, `git diff --check`; no full 12-minute repo suite in every edit. Existing H40 scientific golden hash discrepancy is REPRODUCIBLE on A/B R2 full CI; **do not alter H40 golden or claim full CI PASS**. Run one reasonable terminal CI; report exact mode and any failure honestly.

## 4. Stop-loss, terminal and auto-push

This is **one architecture implementation work package**, allowing same-design local corrections, not a stream of R3/R4/R5 patches. If a frozen method conflict, external unowned worktree change or irreconcilable invariant blocks a defensible build, stop with evidence rather than continue patching. After terminal commit/push, a single independent Gemini B (or high-effort Sol if B independence compromised) semantic re-audit is the next decision boundary; no automatic further code round if fundamental architecture still fails.

- Verify changed paths against allowlist; `git diff --check`; staged name-status; immutable evidence.
- **Proactively commit and push non-force** only `feature/v06-bline-g2-overnight-discovery-a`; verify remote `ls-remote` matches exact pushed commit and report parent ancestry and changed-path list. Do not wait for the user to say push. If unavailable `BLOCKED_NOT_PUSHED`, no READY claim.
- Terminal one of `ARCH_V1_SYNTHETIC_READY_FOR_INDEPENDENT_REVIEW`, `ARCH_V1_IMPLEMENTATION_FAILED_REPLAN_ALTERNATIVE_ENGINE`, `BLOCKED_SPEC_CONFLICT`, `BLOCKED_SCOPE_OR_GIT`, `BLOCKED_NOT_PUSHED`.
- Terminal output includes real `CONTROLLER_DISPATCH_SHA`, immutable Prompt SHA, A start SHA, source commit SHA, evidence commit SHA (if split), final remote HEAD SHA, `REMOTE_PUSH_VERIFIED`, focused tests/CI and ALL 9+ red→positive case identities.

**Unchanged safety:** `EMPIRICAL_PRICE_BODY_AUTHORITY=NONE`, `OLD_FINAL_HOLDOUT=PROTECTED`, `FIRST_PUSHED_PREREG_SHA=NONE`, `TESTNET=NOT_AUTHORIZED`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`, `AUTONOMOUS_LIVE=FORBIDDEN`.
