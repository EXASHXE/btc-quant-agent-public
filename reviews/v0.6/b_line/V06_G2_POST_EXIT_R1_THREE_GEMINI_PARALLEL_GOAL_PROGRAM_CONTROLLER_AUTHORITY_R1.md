# v0.6 B-line Controller — Three parallel Gemini Goal tasks R1

**Date:** 2026-10-12 Asia/Shanghai.
**Controller:** ChatGPT-0 B-line Primary Controller, not A-line or Supervisory Auditor.
**Decision:** AUTHORIZE_THREE_ISOLATED_BOUNDED_GEMINI_GOALS_DEV_ONLY.
**Trigger:** explicit user request for up to three Gemini Goal agents running in parallel, with substantially broader genuine work than a single follow-up; GPT-6.1 Sol quota constrained.
**Target source HEAD:** \`EXASHXE/btc-quant-agent-public@55ac4c631c69f6edbd275462ad23e4486b9782ed\`, frozen Exit R1 implementation \`de2c1fb222970a93ca797868b91b8544261ebaad\`. Do not incorporate future unverified changes on neighboring branches.

## Scientific starting facts

R3.1 accepted public 2021–23 Last+Mark1m 1,576,800 each, authentic signed funding 3,285; latest completed 1m Mark at settlement is only approximation, historical-known-at/fees/maker queue UNKNOWN. Exit/Horizon R1 is one-shot, two candidates W1_C04(n34) and W2_C05(n55), E0 12h/H1 18h/H2 24h/E1 half at1R/E2 half+net BE. R1 \`EXIT_R1_DIAGNOSTIC_INSUFFICIENT_SUPPORT\` accepted at Controller L2 \`7126f40bdde44fdea03f82fa61a45ba750a70b2b\`; exact remote result HEAD \`55ac4c...\`. STRESS44 funded per-trade mean W1 E0 +11.2047bp/H1 +48.5499bp/H2 +44.0744bp; W2 +19.0135/+41.4477/+33.0215bp. Conditional 8-contrast 7/14d 95% simultaneous intervals ALL include zero. W1 H1-E0 14d [-25.9301,+100.6206]bp and W2 [-18.3493,+63.2178]bp; these are not probabilities, not proof zero advantage, and certainly not Alpha. Earlier 48 trials and exit 8 comparisons are exposed, so any new testing is *additional exploratory selection*.

**All three goals are independent, and all three are worth completing even if every measured strategy fails. Goal success=auditable economic/scientific answer, not positive backtest or indefinitely searching until profitable.**

## Three distinct authorized work packages

| Goal | Independent research question and primary measured work | Maximum new selectable configurations | Outputs |
|---|---|---:|---|
| **G-A Entry Discovery** | Discover causally new BTC 4–24h entry families, freeze up to 6 explicit signal hypotheses, evaluate fixed 12h and ex-post-selected 18h with signed funding/Mark + true account feasibility | **6 candidate identities × 2 fixed horizons = 12**, no retuning | Frozen hypothesis/feature registry, real development replay, all candidates incl failures, cost-adjusted trade/portfolio economics, causal source/selection audit |
| **G-B H18 Mechanism / Regime** | Explain 12→18→24h incremental economic mechanism and 2023 breakdown with predeclared regime/event cohorts, occupancy, funding, missed fills, cash and counterfactual decomposition | **0 new selectable exit policies** (E0/H1/H2 reused only) | Independent comparison attribution from published R1 + bounded source checks, mechanism falsification, future D1/D2 prespecification DESIGN_ONLY |
| **G-C Execution Assurance** | Adversarial independent check of R1 multi-tier book, order causality, signed residual Funding, E0 identity/Mark cash curve and declared margin/execution assumption envelope | **0 new strategies or parameter variants** | Independent discrepancy/reproduction receipts, adversarial deterministic+real episodic Decimal checks, 1x futures proxy and hypothetical leverage gate design (NO unproven leveraged trade P&L) |

**No cross-agent reviewer becoming policy authority.** Gemini executes each branch; ChatGPT-0 alone decides L2 and requests additional experiments, ChatGPT-1 separately audits if independently delegated. Parallel work starts from one pinned existing code SHA and creates *no shared code branch*.

## Isolation and exact starting identities

- G-A: \`feature/v06-bline-gemini-goal-entry-discovery-r2\`, \`/root/workspace/project/quant-v0.6/gemini-entry-discovery-r2\`, prefix \`g2_goal_entry_discovery_r2\`.
- G-B: \`feature/v06-bline-gemini-goal-h18-mechanism-r1\`, \`/root/workspace/project/quant-v0.6/gemini-h18-mechanism-r1\`, prefix \`g2_goal_h18_mechanism_r1\`.
- G-C: \`feature/v06-bline-gemini-goal-execution-assurance-r1\`, \`/root/workspace/project/quant-v0.6/gemini-execution-assurance-r1\`, prefix \`g2_goal_execution_assurance_r1\`.
- Each starts **exact** \`55ac4c631c69f6edbd275462ad23e4486b9782ed\`; each task's prompt binds this **Controller authority's immutable commit SHA** and its own branch/worktree/prefix.
- Only create/modify \`scripts/strategy_research/<task_prefix>/**\`, \`tests/test_v06_<task_prefix>_*.py\`, \`docs/strategy_research/<task_prefix>/**\`, \`evidence/v0.6/b_line/<task_prefix>/**\`. Read-only original R2/R3/R3.1/Exit R1, GitHub actions, Controller docs and other branches. Never commit changes to other agents' prefixes or use another agent's scratch.
- Scratch roots \`/tmp/btc-gemini-entry-goal-r2\`, \`/tmp/btc-gemini-h18-goal-r1\`, \`/tmp/btc-gemini-execution-assurance-r1\`, each unique, reject symlink/access outside own scratch and explicitly admitted read-only historic source caches.

## Common fail-closed boundary

1. Public data only: official Binance Vision **BTCUSDT USDT-M 2021–2023** Last/Mark/Funding and authenticated R31 eight-day daily Mark repair, read-only caches only after source hashes/manifest check. Never access owner \`/root/workspace/project/Quant-agent/data\` (even list/stat), \`Quant-agent-sanitized\`, 2024–26 datasets/heldout outcomes, protected H39/H40/H41/Forward, A-line data, private accounts/API credentials, LIVE/TESTNET, real money or non-research side effects. Do not re-open ended P1 engine or P2 owner-file work.
2. Data-body discipline: before computing *any new historical research outcome*, a frozen method+hypothesis+budget+source contract must be committed and non-force pushed, verify exact remote SHA. Reading earlier published R1 aggregates in order to design a **diagnostic** is permitted; no outcome-tuned exploratory new candidate thresholds and no post-result selection of folds/costs.
3. At most **two planned commits per task**: (a) freeze schemas/code/hypotheses + deterministic synthetic tests, (b) one real-development outcome/evidence+report. A research failure is a legitimate final outcome; narrow correctness blockage may yield FAIL_CLOSED evidence rather than endless CI churn or method revision after outcome inspection. If an immutable freeze bug is fundamental, stop and ask a fresh Controller gate, do not silently alter it.
4. **Auto commit and non-force push** each finished stage, verify remote HEAD/parent and changed paths, report observed Actions CI and actual skipped suites. No force push, no rewrites/rebases across other tasks, no branch merging until separate Controller acceptance. If runtime quota interrupts, publish conservative provenance of actual completed work and explicit INCOMPLETE, never fabricate success.
5. Run focused Ruff/compile/JSON validity/≥20 meaningful deterministic tests per task (G-A ideally ≥30), with independent Decimal or alternate implementation crosschecks where cash semantics depend on it. Preserve same-signal, minute-by-minute event and remaining quantity integrity. Do not claim success because green CI, synthetic PASS or positive past profit.
6. Models: **Gemini Goal**, separate authorized sessions. Gemini's self-reported confidence is not policy authority. On discovering critical source/accounting defect, STOP, produce minimal reproducible counterexample and \`FAIL_CLOSED\`, no optimistic P&L.
7. Inferential honesty: all 2021–23 historical trials remain **EX_POST_EXPOSED_DEVELOPMENT_ONLY**. Per-contrast 7/14d calendar-block intervals, maxT across new selectable configurations, past 48+8 selection disclosed. The 2024–25 heldout is never a free sample; no access, even to spot-check. No promotion, no Testnet/Live.
8. Decouple workflows: G-A not dependent on G-B/G-C completion, G-B not authorized to retune G-A, G-C issues scoped findings but cannot modify a sibling's artifact. Controller reviews all three exact SHAs individually and decides whether *one*, if any, hypothesis deserves a future newly authorized chronological test.

## Practical science gates

- G-A seeks not “some profitable strategy” but 3–6 genuinely distinct, time-causal, auditable hypotheses; 12h primary, 18h sensitivity (18h learned on prior selected strategies, not a neutral a priori best). Explicit separate strategy families and control pseudo-entries; require monthly/yearly 2023 analysis and cost-adjusted account P&L, signal counts even when zero. No >12-new-cell optimizer wave.
- G-B seeks discriminating 18h mechanism vs H2 decline and potential sample selection; predefine 3–5 coarse state bins and decomposition from R1 ledger. No new trading policy candidates, no numerical tuning from data.
- G-C seeks independent correctness and realistic operational constraints, not prettier backtest output; any nontrivial discrepancy between original published account and independent journal must downgrade interpretation and potentially block future signal experiments pending Controller ruling. Actual exchange order queue/maintenance margin historical state unknown; label hypothetical leverage as feasibility envelope only.

**Terminal vocabulary:**
- G-A: \`ENTRY_GOAL_EXPLORATORY_COMPLETE_NO_PROMOTION\` / \`ENTRY_GOAL_NO_SUPPORTED_NEW_LEADS\` / \`ENTRY_GOAL_FAIL_CLOSED\`.
- G-B: \`H18_MECHANISM_DIAGNOSTIC_COMPLETE\` / \`H18_MECHANISM_INCONCLUSIVE\` / \`H18_MECHANISM_FAIL_CLOSED\`.
- G-C: \`EXECUTION_INDEPENDENT_DIAGNOSTIC_COMPLETE\` / \`EXECUTION_MATERIAL_DEFECT_FOUND_STOP\` / \`EXECUTION_INCONCLUSIVE\`.

No terminal authorizes a new development wave, holdout read, testnet or live.
