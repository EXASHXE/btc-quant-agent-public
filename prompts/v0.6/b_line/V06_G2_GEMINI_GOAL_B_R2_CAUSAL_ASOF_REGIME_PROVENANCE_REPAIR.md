# GEMINI GOAL B R2 — As-of-ENTRY causal feature repair, original mechanism audit and prospective readiness

MODE: Gemini Goal sustained execution. Complete code/test/source-receipt/report workflow, not a planning note. A scientifically valid negative or inconclusive result terminates the Goal. You are NOT authorized to find a profitable policy through a new search.
CONTROLLER_DISPATCH_SHA: 1172d3a91324c1a7379bc9e5c24ef601076547c2
AUTHORITY_URL: https://github.com/EXASHXE/btc-quant-agent-public/blob/1172d3a91324c1a7379bc9e5c24ef601076547c2/reviews/v0.6/b_line/V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md
REPO: EXASHXE/btc-quant-agent-public
EXACT_START_SHA: 397a62c1a0fbd6ad14a569a5be0058b1f684f08e
BRANCH: feature/v06-bline-gemini-goal-b-asof-repair-r2
WORKTREE: /root/workspace/project/quant-v0.6/gemini-goal-b-asof-repair-r2
SCRATCH: /tmp/btc-gemini-goal-b-asof-repair-r2
OWN_PREFIX: g2_goal_b_asof_repair_r2
R1_FROZEN_SHA: ebb33b7f96e5ab0c753beab14363632a0a221416
R1_FINAL_SHA: 397a62c1a0fbd6ad14a569a5be0058b1f684f08e
R1_EXIT_SOURCE_SHA: 55ac4c631c69f6edbd275462ad23e4486b9782ed

## Critical context and task

Goal B R1 did NOT implement its own declared as-of-entry definitions in its actual run.py. It labeled a post-entry 0–12h MFE/MAE as an entry-time trend, used the first after-entry signed Funding rate as entry-known Funding and categorized volatility via trade risk_bps >300 instead of prior-only 90d completed 1h ATR14/price percentile. Its R1 report also misstates original W2 year counts (human 14/17 vs verified E0 10/21 in 2021/2022) and skipped signals (human zero for E0 despite R1 account blocked-fate counts). Avoid making B's contaminated regime conclusions look preregistered: they are invalid. R1 12h vs 18h descriptive per-event economic effect remains useful but all 7/14d familywise intervals span zero, and original sample selected after prior 48+8 research trials.

GOAL: produce a time-causal, source-proven independent as-of regime *retrospective addendum* and an exact corrected machine-to-human report. A separate post-hoc addendum does NOT convert previous leaked feature into a confirmed trading signal. No new thresholds, policies, or conditional trading variants.

## Work package B0 — verified inputs and independent audit plan

- Verify remote branch pinned EXACT_START_SHA, immutable first freeze and result code tree; inspect Exit R1's 4 paired JSONL ledgers and original final result receipts. Prove SHA256 and ledger event ID preservation.
- Confirm Last minute source 2021-01 through 2023-12, 1m Mark composites, real funding 3,285 events are public authenticated READ-ONLY archives. No protected/private data. Never even list/stat owner /root/workspace/project/Quant-agent/data or Quant-agent-sanitized; no 2024–26 bodies, H39/H40/H41/Forward, A-line, private credentials, TESTNET/LIVE.
- Take a code-flow inventory: freeze contract definitions vs actual run.py call graph, line-based evidence of future MFE/MAE, first future Funding, substitute risk_bps volatility, and report/account discrepancies. Label invalid R1 sections as WITHDRAW rather than report them as stale but valid.

## Work package B1 — source-backed method freeze (PUSH first)

Author exact immutable protocol and implement independent event-state source reader under own prefix; use STRICT pre-entry timestamps:
1. PRE_ENTRY_TREND_ALIGNED: last completed 240 consecutive 1m LAST bars composing strictly PRE-entry 4h return, side multiplied. No sample-path after entry. Compute endpoint close time <= min(signal_decision_available_at, entry_at-1ms), with source row close/open clocks verified. Reject incomplete histories.
2. PRE_ENTRY_ATR_REGIME: resample ONLY fully closed public 1h OHLC bars; ATR(14) via explicitly frozen Wilder definition; current 1h normalized ATR/Last price from latest completed 1h, compare against median of prior-only 90d hourly normalized ATR values strictly known by the entry decision. Do not use trade risk_bps, pooled future years or 2023 final aggregate median. Incomplete 90d -> UNKNOWN/INCOMPLETE, never auto-substitute low volatility.
3. PRE_ENTRY_FUNDING_STATE: latest signed official Funding rate settled strictly BEFORE signal decision clock. No next funding event, no predicted displayed rate. Explicit settlement known-at is retrospective proxy only, not proof of exchange publication latency; option for arbitrary >=1m availability lag sensitivity using prespecified fixed lag, not selectable strategy.
4. Calendar year/side are valid labels, but never causal conditions for future policy.

Declare exactly which bars are consumed and source ZIP sha. Synthetic time-travel tests should mutate every bar/rate AFTER signal_decision and prove all three label outputs byte-for-byte unchanged. Also test incomplete 4h/90d history, 1h boundary at 00:00, 08:00/16:00 Funding, UTC month boundary, Jan2021 warmup, 2023 last fold purge, long/short and N<10 support; >=40 synthetic tests plus an explicit manual 12 real events source-decoded input/label as-of Decimal/stdlib audit plan.

Freeze before calculating any newly recomputed B R2 state/returns. COMMIT1 frozen method/schema/code/tests only; NON-FORCE PUSH, verify remote SHA/parent and changed files. If need post-freeze implementation change due bug, stop FAIL_CLOSED, do not silently replace freezing and rerun.

## Work package B2 — ONE finite post-hoc descriptive pass

- Reconstruct both leads' original 34/55 event IDs from Exit R1 E0/H1 fixed data; require exact counts per cost and year. Derive above three as-of state labels for each event from admitted public source. Export per-event event ID/entry clock/source SHA/feature latest close as-of/label and diagnostic delta H1-E0 net bp. This is 2 leads x BASE/STRESS with no new exit/entry policy executed.
- Calculate ONE-axis-only regime diagnostics for year, side, trend, vol, known funding with all cell N, support independent calendar weeks and missingness; preserve small strata <10 as UNDERPOWERED; since we are reinterpreting exposed outcomes, no profitability or market-regime threshold selection based on positive mean.
- Preserve original 7d/14d uncertainty and pre-registered 8 family exposure; if recomputing intervals, present as exploratory post-selection uncertainty, with explicit new as-of strata multiplicity; no false "p-value proves good strategy".
- Reconstruct descriptive 12-18h and 18-24h original TIME_CAP pathway from the *previous* R1 ledger without changing fills: price PnL, fee, signed funding, right-tail contribution, 2023 W2 absolute loss, multiple regression effect support, opportunity cost and accepted event set. No D1/D2 simulation.
- Reconcile every B R1 human number against R1 machine E0/H1/H2: year W1/W2 n, net bp and actual 2023, skipped signals (distinguish candidate signals generated vs rejected/available), occupied minutes, Mark DD, target/stop fate, per-eligible-event target contribution vs entire sample. Each corrected table should carry source path/key and reconstruction formula. If wrong/future label found, mark report claim REVOKED.
- Compare R1 freeze to R1 final code changes: audit slippage STRESS 16 -> 6bps and BASE 8 -> 3bps, selection logic, report output. Test consistency with freeze contract; separate corrected code from unchanged analysis if no valid frozen-to-final equality.

## Work package B3 — designed but NOT executed prospective program

Write robust future D1/D2 hypothesis design only: feature decision clock at 12h, completed bars, order queuing/ACK/one-position causality, no auto rollout. Explain why any 0.5R, 0.10 flow and ATR 1.5x multipliers previously suggested are now exposed exploratory design parameters, not prevalidated. Provide power/event-count feasibility and falsifiers before external/newly permitted sample. Absolutely no new historical D1/D2 result, no "18h universally optimal".

## Work package B4 — quality, publication and terminal

- At least 40 synthetic deterministic tests, 12 real independent as-of source checks, Ruff/compile/strict JSON/hashes. Publish machine-labeled new addendum, original R1 claim-withdrawal matrix and corrected version-controlled report with clear supersession caveats, all source mapping.
- Second commit results-and-docs only; auto NON-FORCE PUSH and verify new head,parent, changed-paths, Actions CI actual failed/skipped suites. No old code/report edits; no more than 2 commits.
- Terminal B_R2_ASOF_LABELS_CAUSALLY_RECONSTRUCTED_DEVELOPMENT_ONLY / B_R2_ASOF_SOURCE_OR_FOLD_INCONCLUSIVE / B_R2_CAUSALITY_FAIL_CLOSED. Report any remaining UNKNOWN, including Funding exchange publication known-at and 1m bar intra-minute ordering.

Writes limited to scripts/strategy_research/g2_goal_b_asof_repair_r2/**, tests/test_v06_g2_goal_b_asof_repair_r2_*.py, docs/strategy_research/g2_goal_b_asof_repair_r2/**, evidence/v0.6/b_line/g2_goal_b_asof_repair_r2/**. Never repair historical H40 CI or interact with Goal A/C worktrees.
