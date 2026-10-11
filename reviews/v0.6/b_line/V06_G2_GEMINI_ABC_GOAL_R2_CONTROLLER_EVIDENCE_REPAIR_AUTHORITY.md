# Quant v0.6 B-line — Three Gemini Goal R2 evidence-conformance tracks

Decision date: 2026-10-12 Asia/Shanghai.
Decision: AUTHORIZE_THREE_ISOLATED_GEMINI_GOAL_R2__RECONCILE_FIRST__NO_NEW_STRATEGY_SEARCH.
Controller: ChatGPT-0 B-line. Executing agent: Gemini Goal.
TESTNET/LIVE/real-funds/protected holdout authority: NONE.

## Verified state

Goal A: remote HEAD efa0b302233800f6474b3dda5775be56a77d0860 (frozen method 83c0ef60d9eacfd2440fa223c57f042cfff4912f), two commits since shared 55ac4c631c69f6edbd275462ad23e4486b9782ed. Final CI 38161124788 SUCCESS, 3095 passed/2 skipped; freeze CI unrelated H40 graph hash failed. Research 4 signal families x 12/18h, all reported STRESS44 PF 0.35 to 0.61, no alpha. A method constraint: final run.py changes whole-history array to previous+current-month window, funding array and opposite-side controls AFTER implementation freeze. Human yearly C01 12h report n569/n549 (2021/2022) vs machine n619/n499, C03 report 4/7 vs machine 5/6. Science still provisional; semantics proof and reporting reconciliation required.

Goal B: remote HEAD 397a62c1a0fbd6ad14a569a5be0058b1f684f08e (frozen ebb33b7f96e5ab0c753beab14363632a0a221416), two commits. Final CI 38161000757 FAIL unrelated H40 graph hash (3088 passed/1 failed/2 skipped). Existing code labeled first 12h POST-entry MFE/MAE as entry-trend; first future in-trade funding as pre-entry funding; uses initial-risk 300bps split instead of promised past-only 90d ATR. Trend/funding/regime predictive conclusions INVALID. Human W2 2021/2022 14/17 vs original R1 10/21; account skipped-count human table disputed. 12/18/24h retrospective aggregate E0/H1/H2 remains descriptive and post-selection 95% block intervals all include zero.

Goal C: remote HEAD f381dd73a8c583e2a28dcab2e354b019b1d946fa. Three commits: freeze 8db2e3ff36011c6a65458f8cf4c2ba5e90d5fee2 -> repair 4c0bac051767f788e6de173f6563a7b47af2ac69 (attestation/run.py and frozen contract changes) -> final evidence f381dd73...; original two-commit limit exceeded. Final CI 38162845456 SUCCESS but docs-only checks: tests/Ruff/type SKIPPED. Report claims 48 independent deep episodes, 890 ledger trades, 48 fixtures, no account mismatch; Controller has not independently run full source datasets. Severe claim mismatch: report describes 7.5%-11.6% 1R historical stop distance while machine reports max 3.612% W1 and 3.5591% W2. Machine risk text falsely says 3.61% stop exceeds 15x 6.67% initial margin buffer. Report claims 7/6 insolvencies (impossible); synthetic scenario JSON has 32 cases, 5 naive liquidated before target stop per summary, 7 alleged bankruptcy deficit cases but deficit field appears to disagree; recompute denominators and scenario ledger. E0 exposure cell summaries record peak ratio 0 despite 34/55 trades. Unverified leverage, maintenance tiers, market queue and settlement exact Mark cannot support real leverage or TESTNET promotion.

Prior Controller L2 source review: https://github.com/EXASHXE/btc-quant-agent-public/blob/34ff43d686976714d9f25afca407c6c8cb070e01/reviews/v0.6/b_line/V06_G2_GEMINI_GOALS_A_B_EXACT_SHA_L2_EVIDENCE_QUARANTINE_R1.md .

## Authorized independent Goal R2 branches

A: feature/v06-bline-gemini-goal-a-conformance-r2 starts exact A HEAD efa0b302233800f6474b3dda5775be56a77d0860; isolated worktree /root/workspace/project/quant-v0.6/gemini-goal-a-conformance-r2; unique prefix g2_goal_a_conformance_r2.
B: feature/v06-bline-gemini-goal-b-asof-repair-r2 starts exact B HEAD 397a62c1a0fbd6ad14a569a5be0058b1f684f08e; worktree /root/workspace/project/quant-v0.6/gemini-goal-b-asof-repair-r2; prefix g2_goal_b_asof_repair_r2.
C: feature/v06-bline-gemini-goal-c-risk-assurance-r2 starts exact C HEAD f381dd73a8c583e2a28dcab2e354b019b1d946fa; worktree /root/workspace/project/quant-v0.6/gemini-goal-c-risk-assurance-r2; prefix g2_goal_c_risk_assurance_r2.

Each may write only scripts/strategy_research/<own_prefix>/**, tests/test_v06_<own_prefix>_*.py, docs/strategy_research/<own_prefix>/**, evidence/v0.6/b_line/<own_prefix>/**; no changes to old A/B/C source or artifacts, P1, CI, roles, protected data or any other worktree. Scratch exclusively /tmp/btc-gemini-goal-{a-conformance,b-asof-repair,c-risk-assurance}-r2. Parallel execution independent; no shared scratch or merge. Use at most two planned commits, freeze method+tests+verify remote BEFORE newly computed historical diagnostic, then one bounded reconciliation evidence commit+nonforce push+verify remote. A post-freeze code modification requires stopping and fresh Controller authorization, not silent patch/re-run. Research failure is a valid terminal; never keep optimizing to profit.

## Scope and nonnegotiable exclusions

All tasks are SOURCE/SEMANTICS/EVIDENCE correction only. No new entry strategy, conditional 18h policy, D1/D2 historical tests, parameter sweep, or 2024–26 holdout. Public Binance BTCUSDT USDT-M 2021–23 authenticated Last/Mark/Funding may be used read-only, after cryptographic admission; originals and R1 ledgers immutable. Never list/stat/read /root/workspace/project/Quant-agent/data or Quant-agent-sanitized, protected H39/H40/H41/Forward, A-line/Performance, private account or secrets, owner P1/P2 paths. No exchange order, TESTNET/LIVE, leverage order or funds.

A work: semantic old-vs-new engine diff for all 35 folds and 8 hypotheses (candidate event clocks, entry/side/qty, cash, funding, Mark valuation); reconcile all annual/gross/fee/net numbers directly from committed machine data with a typed comparison table. If equivalence not provable, mark original Goal A preregistration invalid and stop, do not tune/re-run for better economics.

B work: strict completed previous 4h Last return asof-entry, prior 90d completed 1h ATR14 divided by price percentile/median, latest settled Funding strictly before decision. Instrument unit tests for future mutation invariance. New analyses are an addendum labeled post-hoc observational (NOT the original preregistered Goal B), reconcile all years and collision/skip counts; never treat future path states as entry signal.

C work: recompute 32 synthetic margin cases/5 and 7 counts from scenario rows with precise denominator; independently test actual isolated margin conservation, compare real past stop distance 3.612/3.559% to hypothetical 7.5% scenario, repair zero E0 exposure report from real order/cash paths or mark UNKNOWN, audit attestation freeze repair and test coverage. No historical leveraged P&L, no real historical maintenance margin invented, no claim risk caps guarantee solvency.

All three require precise pass/fail witness, >=25 synthetic tests (C >=40), Ruff/compile/strict JSON, CI status/skip truth and exact SHA/parent/diff verifications. Controller checks results individually and no branch advances any protected gate. A-line and Performance independent.
