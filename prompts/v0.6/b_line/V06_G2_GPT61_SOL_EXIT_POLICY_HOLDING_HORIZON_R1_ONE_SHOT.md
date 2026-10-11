# GPT-6.1 Sol High — One-shot BTC 4–24h Exit Policy × Holding Horizon R1 (B-line)

**TASK_ID:** V06_G2_POST_R31_EXIT_POLICY_HORIZON_R1_ONE_SHOT
**EXECUTOR:** Codex GPT-6.1 Sol High (requested; report if actual root model/effort cannot be observed).
**CONTROLLER_DISPATCH_SHA:** 7293d3f97f2d81167fd6ea17e69e424065e19e41
**Controller immutably binding decision:** https://github.com/EXASHXE/btc-quant-agent-public/blob/7293d3f97f2d81167fd6ea17e69e424065e19e41/reviews/v0.6/b_line/V06_G2_R31_L2_CONTROLLER_ACCEPTANCE_AND_EXIT_HORIZON_R1_AUTHORITY.md
**Frozen full research design:** https://github.com/EXASHXE/btc-quant-agent-public/blob/9a3ba717e0c8eea062d74a038f743f87d7ae1b94/docs/strategy_research/g2_exit_horizon_r1/V06_G2_POST_R31_EXIT_POLICY_AND_HOLDING_HORIZON_RESEARCH_DESIGN_R1.md
**Repository:** EXASHXE/btc-quant-agent-public
**BRANCH:** feature/v06-bline-exit-horizon-r1 (Controller-created, only authorized push target).
**START_SHA:** 990c02b5479b3b14996f90fdbf677cb672ada81e
**ISOLATED WORKTREE:** /root/workspace/project/quant-v0.6/exit-horizon-r1
**MANDATORY:** verify HEAD, origin and clean exact start before any code edit; do not reset/stash/clean/force any other worktree. If ref or parent is unexpected, STOP_NOT_STARTED.

## 1. Goal, boundaries and stop

Finish **ONE** bounded empirical exploration of exit-only modifications on two immutable code-as-executed 12h BTC lead signals. This is not an Alpha hunt/never-stop Goal; do not maximize in-sample return or optimize entry signals. R3.1 two-lead source and P&L are accepted **development-only**, NOT policy validated.

The strict test matrix is 2 candidates × [E0(12h original), H1(18h original), H2(24h original), E1(12h 50% at1R + 50% at original target), E2(E1 + remaining net break-even stop after TP1 ACK)] = 10 cells, **8 new and ONLY 8**, BASE22 and STRESS44 each, STRESS primary. W1 target 2R, W2 target 2.5R. D1 conditional extension and D2 ATR trailing are DESIGN_ONLY and MUST NOT be evaluated on any real development outcomes in this task. Keep candidate side, original ATR/stop, entry, filters, R2 extra-minute lag, 0.25ATR gap veto, ack/cooldown, 5% reserve, 1x cap, monthly score folds and costs unchanged. No extra horizons, TP fractions, stops, fees or parameter/threshold variations.

### Strict data/permissions
- Allowed public BTCUSDT Binance Vision USD-M **only** 2021-01 through 2023-12 original Last 1m/Mark 1m and actual Funding settlements, with checksum and the frozen R31 eight-day Mark gap composites. Read-only reuse of verified R3 task-owned scratch /tmp/btc-two-lead-funding-mark-r3 and R31 task-owned scratch /tmp/btc-two-lead-mark-gap-r31, only if hashes and manifests match source receipts; create a separate own /tmp/btc-exit-horizon-r1. If source caches unavailable, one documented bounded original public re-download attempt may be made *after freeze*, or FAIL_CLOSED; do not build another source service or new lookback engine.
- Absolutely NO access, including path list/stat, to /root/workspace/project/Quant-agent/data or Quant-agent-sanitized; no A-line/H39/H40/H41/Forward/protected outcome; no 2024/2025/2026 source body/path/head, Binance private API, account/credential, orders, TESTNET, LIVE, real-money writes, Feishu or deployment modifications.
- Only allowed source edits/creation: scripts/strategy_research/g2_exit_horizon_r1/**; tests/test_v06_g2_exit_horizon_r1_*.py; docs/strategy_research/g2_exit_horizon_r1/**; evidence/v0.6/b_line/g2_exit_horizon_r1/**. All prior source, R2/R3/R31 reports/evidence, CI, roles, Controller/roadmap and parallel worktrees are read-only. Import/reference inherited source/algorithms rather than rewrite them.

## 2. Two-commit execution order (binding)

**Commit 1 — pre-new-exit-outcome freeze:** create frozen machine contract with exact candidate IDs, config tuples, hashes of inherited replay/signal/source artifacts, UTC fold/purge/settlement semantics, fee/fill/order/BE conventions, partial quantity rounding, paired-event eligibility, no-lookahead and statistical family. Implement deterministic minimal sidecar ledger and pure synthetic tests; tests may use disposable synthetic fixtures, NOT actual new exit outcome replay. Commit and non-force PUSH to ONLY task branch, then verify remote HEAD, commit parent and changed-path scope. Record first SHA and remote verification in machine evidence. Before this pushed freeze: NO inspection of any **newly computed H1/H2/E1/E2 historical path outcome** and no outcome-conditioned code edits. Frozen R31 evidence and unchanged E0 source definitions may be read for inheritance.

**Commit 2 — ONE bounded public-development execution:** verify frozen tree/code SHA matches commit1, load only authenticated 2021–23 public Last/Mark/Funding, reproduce E0 exact per cost and candidate then run at most 8 new configurations. Produce comprehensive paired and full-account machine tables, fund/fee cash journal, hashes and bounded scientific report. Independently recompute ≥5 real LONG/SHORT partial/exited-near-Funding Decimal episodes from verified source CSV, including 2022/2023, and compare stage cash/quantity/fees/Mark. Run scoped ≥20 synthetic tests (not an extensive P1/full-suite refactor), Ruff, compile, JSON validity. Commit outcome/evidence (no source logic revision after seeing results), non-force PUSH and verify remote HEAD/parent/diff scope, then inspect Actions CI exactly once for status/skips. If freeze method invalid or engine bug, publish FAIL_CLOSED; never silently mutate/fix methodology and rerun to obtain favorable outcomes. At most 2 commits on task branch.

**MANDATORY AUTO-PUSH:** After each bounded stage's scoped tests pass, proactively git commit and git push without requiring user to ask 'push'. Verify remote branch HEAD and parent, no force and no branch swaps. Output REMOTE_PUSH_VERIFIED=true (only if true), branch, commit1/commit2 SHAs, parent, source-versus-evidence SHA, changed paths, test receipts, GitHub Actions URL/status including skipped suites. If network/auth blocks, return BLOCKED_NOT_PUSHED, never imply Controller receipt. Push is NOT Controller acceptance.

## 3. Execution economics, fill and journal contracts

E0's original last-price execution must be **byte/digest-identical** to R2/R31 across 2 candidates × 2 costs: original signals and accepted event IDs, trade quantity, reasons, exit time, net per-trade P&L and full month minute cash/Mark curve SHA. An E0 mismatch = FAIL_CLOSED before displaying new-cell results.

H1/H2 may change only deadline (18/24h) and downstream account event fates and funding occupancy. Freeze the original R2 STOP_GAP > TIME_CAP_OPEN > TARGET_GAP > intraminute STOP-before-TARGET conservatism; cap gap target at target price. No future bar used for decision/entry.

E1/E2 split Q at lot increments, Q1 = floor(0.5*Q/0.001)*0.001, Q2=Q-Q1 with both >0 and valid min notionals; report ineligible baseline episodes explicitly. TP1=1R, target2 original (W1 2R/W2 2.5R). E1 residual stop unchanged. E2 after TP1 actually fills and ACKs, move only residual stop in favorable direction to *per-residual net execution break-even* tick including expected entry+exit costs, never loosen original stop; motion cannot be effective within the same 1m bar. No later bars/funding used to choose stop. Determine colliding STOP/TP1/TP2/time cap minute order in frozen contract, conservatively STOP first for unknown intrabar ordering; old E0 identity remains untouched.

Tier-based fee on actual quantity and effective entry/exits, never two entry fees or full-quantity exit fee twice. Separate price P&L, effective execution spread/slippage, fee and funding signed cash, partial open quantity at every settlement, settled cash and 1m Mark residual liquidation value. Missing/negative/duplicate inventory and cash drift must reject. No positive funding cash before settlement known; use latest *completed* 1m Mark at event, flag exact exchange settlement Mark UNKNOWN. Original risk admission 5% cash reserve and 1x, no levered liquidation claim.

A TP price touched in OHLC is *not* proof of limit fill: for new partial tiers require strict 1-tick trade-through (or favorable opening gap), fill no better than capped limit using existing conservative cost proxy and log touch-no-fill. Primary analysis must **separate** exit-policy effects from this changed fill assumption. Retain immutable legacy E0 identity; add a separately labelled execution-matched *diagnostic-only* E0 fill sensitivity and a pre-specified one-bar-delay/unfilled TP sensitivity, without adding a ninth selectable strategy configuration or maximizing across execution scenarios. Results must explicitly say if a paired gain/loss is confounded by different limit-fill assumptions and not label such a raw difference causal. No L2/order queue/actual maker fills available.

**Two modes (both mandatory):**
1. Fixed-signal paired: same R31 E0-accepted event IDs and initial qty/risk, retain per-event 24h price and mark paths, report before-12/12–18/18–24h MFE/MAE, TP/STOP/TIME_CAP, age-weighted exits, incremental funding+fees, missed/delayed fills, qualified denominator and missing/censored IDs. Do not claim this predicts whole-account performance.
2. Independent full 35-month account replay: reprocess *all original candidate signals*, not the old accepted trade list. Same single-position constraint until last remaining tranche exits and ACK/cooldown passes; recompute changed admission, skipped signals, amount reserved, cash, monthly continuity, mark drawdown, occupancy, max notional/equity, worst year, side returns. New opportunity trade count may change; old partial cash cannot be redeployed into new concurrent signal unless full exit.

For H2, prove every outcome is within same authorized fold and existing 24h purge; entries whose 24h full path+exit/ACK would fall outside fold must receive prospectively declared censoring, not borrow future fold/2024 outcomes. If >10% originally E0 TIME_CAP fixed pairs lack complete 24h path, return DIAGNOSTIC_INSUFFICIENT_SUPPORT or FAIL_CLOSED source if integrity violated, no handpicked events. No posthoc month/side filters.

## 4. Mandatory metrics and inference, no optimization

For each candidate×scheme×cost and matched controls: n, acceptance/skipped fate reasons, N partial/ineligible, probability and shares of STOP/TP1/TP2/TIME_CAP, actual flat age, weighted exit age, signed funding events and cash, gross/net bp, PF, mean/median Net R, win rate, roundtrip cost by actual tier, monthly and yearly balances, Mark min equity and max DD, peak exposure and occupancy and opportunity cost from conflicting signals. Full decomposition Δ(H1,E0), Δ(H2,E0), Δ(E1,E0), Δ(E2,E1); E2-E0 only diagnostic.

STRESS44 preprimary, BASE22 sensitivity, fixed additional per-tier commission/slippage stress equivalent ±2/±5/±10bp roundtrip, 7/14d UTC calendar-block bootstrap seed42 10k fixed draws incl zero-trade blocks, 8-contrast simultaneous maxT adjustment. Cross-candidate comparisons do not add a third optimizer. Prior 48 trials were exposed; joint56 sensitivity only if jointly reconstructible without extra outcome fishing, otherwise clearly mark partial selection adjustment and prohibit Alpha inference. Report 2021/2022/2023 including 2023 failure, effective independent blocks and paired confidence bounds, no transformed LCB claimed confirmatory.

**Single-shot stop:** if E0 identity, nonlookahead, partial accounting, source authenticity, independent Decimal crosscheck, or fold purge fails -> EXIT_R1_FAIL_CLOSED_EXECUTION_OR_SOURCE; do NOT publish optimistic new-cell P&L. If checks pass but support poor, source participation sparse, or delta unstable -> EXIT_R1_DIAGNOSTIC_INSUFFICIENT_SUPPORT. If complete measurement -> EXIT_R1_EXPLORATORY_ACCOUNT_AND_PAIRED_COMPLETE_DEVELOPMENT_ONLY. All outcomes remain DEVELOPMENT_ONLY, none is POLICY_VALIDATED or holdout/real funds approval.

## 5. Terminal deliverables, scope and speed

- Machine freeze, source identity, state-transition ordering, exact8 comparison registry; complete E0 identity receipts.
- Paired event ledger and executable account full-order journal, per configuration and cost, source+ledger hashes; independent ≥5 Decimal cases.
- Concise human report with exact sample and uncertainty, 2023 attribution, per-tier fills, time-cap mechanism, alternate execution sensitivity, complete source/CI skips/unknowns and whether any *new* independent future test is scientifically justifiable (no automatic heldout access).
- Commit/test and CI evidence, remote HEAD verification. Full source blobs already exist from R31; do not redownload 108 archives if authenticated scratch available. No generic trading framework or third VirtualBook.

**Real-time instructions are limited to one task execution. Do not create or run monitoring/automation. Do not contact the user for permission to push the two authorized branch commits.** Once remote pushed, stop and return exact identities for Controller independent L2 adjudication.
