# GEMINI GOAL B — Investigate 18h vs 12h/24h Mechanism, Failure Regimes and Opportunity Cost

**Mode:** Gemini Goal / complete a rigorous one-shot empirical causal-mechanism diagnostic and future experimental protocol, not a vague brainstorm. Continue until the scientific mechanism is explained or rigorously inconclusive; do not change policies to obtain positive backtests.
**CONTROLLER_DISPATCH_SHA:** c02743fddccdf517582c371a47e82d8dcbb05923
**Authority:** https://github.com/EXASHXE/btc-quant-agent-public/blob/c02743fddccdf517582c371a47e82d8dcbb05923/reviews/v0.6/b_line/V06_G2_POST_EXIT_R1_THREE_GEMINI_PARALLEL_GOAL_PROGRAM_CONTROLLER_AUTHORITY_R1.md
**B-line Controller:** ChatGPT-0, only scientific/controller authority.
**Repository:** EXASHXE/btc-quant-agent-public
**EXACT_START_SHA:** 55ac4c631c69f6edbd275462ad23e4486b9782ed
**OWN BRANCH:** feature/v06-bline-gemini-goal-h18-mechanism-r1
**OWN WORKTREE:** /root/workspace/project/quant-v0.6/gemini-h18-mechanism-r1
**OWN SCRATCH:** /tmp/btc-gemini-h18-goal-r1
**OWN PREFIX:** g2_goal_h18_mechanism_r1
**Allowed write paths only:** scripts/strategy_research/g2_goal_h18_mechanism_r1/**; tests/test_v06_g2_goal_h18_mechanism_r1_*.py; docs/strategy_research/g2_goal_h18_mechanism_r1/**; evidence/v0.6/b_line/g2_goal_h18_mechanism_r1/**. No edits to old R1 implementation/evidence or any other Agent worktree.

## Purpose: distinguish causal economics from the already exposed H1 point estimate

Exit R1 accepted development-only: BTCUSDT USD-M public 2021–2023, W1 n34 and W2 n55. Under STRESS44 observed signed Funding/Mark completed-close proxy, E0 12h means +11.2047/+19.0135bp, H1 18h +48.5499/+41.4477bp, H2 24h +44.0744/+33.0215bp. Of fixed original E0 events, W1 20/34 and W2 36/55 stopped at 12h time cap. R1 95% simultaneous 7/14d maxT eight-contrast intervals for H1-E0 include zero (W1 14d [-25.9301,+100.6206]bp, W2 [-18.3493,+63.2178]bp). H1 was selected after observing development and 2023 is unstable; **do not promote it to a proven optimal 18h holding period**.

**GOAL:** deliver an auditable, economically interpretable attribution of why H1 may improve E0, why H2 may underperform H1, how those effects differ across market states and sides, and whether net advantage would survive realistic opportunity/cost constraints. The task is observational/mechanistic, not new H1 tuning, OOS test or signal discovery.

## Strict source and experiment budget

Only R1 frozen E0/H1/H2 schemes on the **same original two leads**, three original years and two frozen BASE22/STRESS44 cost vectors. No newly selectable exit rules, no 15h/16h/20h/22h interpolation, no new stop/target/TP fraction/BE/trailing optimization, no D1/D2 historical evaluation, no extra assets, no threshold hunts. You may implement deeper *diagnostics* on already frozen 12/18/24h paths using published R1 full ledgers and admitted public 2021–23 Last/Mark/Funding where independent path reconstruction materially adds evidence. This is an additional exploratory interpretation; every stratum's sample count and earlier family selection must be disclosed. No 2024–26, owner /root/workspace/project/Quant-agent/data (not even stat/list), Quant-agent-sanitized, A-line, H39/H40/H41/Forward, private accounts/credentials, real orders, TESTNET/LIVE.

Predeclare **three primary matched analyses** plus bounded state bins; no outcome-driven choosing/combining state bins:
1. Frozen E0-accepted **time-cap censored** versus early STOP/TARGET baseline strata, preserving same E0 event ID/initial Q/entry, trace what happens between 12–18 and 18–24h; separate raw favorable/adverse Last path, funding cash, fee changes, target/stop fate, MFE/MAE, risk-scaled conditional returns and actual exit timestamps.
2. **Whole-account opportunity cost**: independent E0/H1/H2 signal-stream replays and log who was declined because prior position extended, exit ACK/cooldown, 5% cash reserve, 1x notional, cumulative cash and minute Mark MTM; *matched same-event* versus *different account event set* estimands. Quantify counts/notional blocked; hypothetical skipped-signal P&L is not a realizable performance claim and should be a clearly separate upper/lower-bound sensitivity.
3. **Time and execution decomposition**: show post-12h incremental signed price P&L vs extra settled Funding vs fees/spread/slip, additional Mark drawdown / occupancy and 2021/22/23 attribution; one bar later exit-ACK or worse slip fixed sensitivity under both costs (diagnostic only; never new selectable strategy). Verify raw Last/time-cap clocks and Funding settlement open quantity asof.

Predeclared state labels as-of entry (no future data in any "prediction" label):
- Calendar year 2021 / 2022 / 2023, side LONG / SHORT (always report but do not choose winners);
- *Only for path diagnostics*, entry-time trend alignment versus countertrend using completed 4h return sign relative to side (zero as neutral);
- Entry volatility / realized-range level: low/high split from an expanding **previous-only** 90d distribution of completed 1h ATR(14)/price (skip when lookback incomplete; never a full 2021–23 sample median);
- Entry funding *already observed* at signal time: previous settled positive/negative/unknown; never use later rate as entry feature.
Avoid combinatorial strata explosion; report each label one-at-a-time, event N, and effective UTC weeks. If no ≥10 events per stratum, mark UNDERPOWERED and do not claim effects.

## GOAL workflow

**0. Identity and forensic input.** Confirm own branch exact start SHA, worktree isolated and clean; read Controller/R31/R1 review, provenance, original trade/event/funded order ledgers, time-cap E0 count, CI truth; verify hashes in COMMITTED_LEDGER_MANIFEST. No private/heldout touches and no writing another agent's task.

**1. Freeze BEFORE novel historical diagnostic output.** Write machine method contract with exact E0/H1/H2 identity digests, three analyses above, 3+ fixed regime labels, price/funding/fee decomposition equations, expected source hashes, 7d/14d matched uncertainty, zero-trade-block handling, and stop/falsification gates. Implement deterministic pure feature/analysis code and **≥25 synthetic tests** for underpowered bins, incomplete as-of window, stop/target/timing, sign/quantity, same-event pairing vs account, gap/slippage/ACK, folded endpoints, and determinism. Before looking at new regimen-specific outcomes COMMIT 1, nonforce push, verify remote HEAD/parent and record freeze SHA.

**2. One source-bounded genuine diagnostic pass.** Work only with published real E0/H1/H2 ledgers or verified read-only 2021–23 public arrays. Build (a) per-event price-path trajectories through 24h; (b) E0 TIME_CAP-specific incremental 12→18 and 18→24 outcomes; (c) account-level capital occupancy, missed/declined signal fates, opportunity bound and Mark DD; (d) predeclared one-axis regime/year/side; (e) resampled uncertainty with calendar block and effective support. Do not claim that a favorable H1 sign conditional on earlier selected leading candidates provides independent evidence. Audit >10 real event decompositions with an independent Decimal/std library path including both sides/years and funding-after-timecap where present; if missing label unavailable and justify.

**3. Mechanism falsification and output.** Give a clear answer to all:
- Among 56 original STRESS E0 TIME_CAP events, how many show favorable net continuation 12–18h versus adverse reversal? Report W1/W2 and fee/funding breakdown;
- How much of H1-E0 +37.3453bp / +22.4342bp is attributable to specific exit fates versus cost/funding artifacts? Are there outlier/month-dominance effects?;
- Why does H2 underperform H1 in means despite a larger duration? How many extra STOPs, gap events, negative 18–24h continuation, extra capital occupied?;
- Does positive H1-E0 persist in 2023 at transaction and account levels, and is 2023 **absolute** W2 still negative?;
- Are there identifiable, **as-of** state differences, or are samples too sparse to support regime targeting?;
- Can any of this justify a *future* D1 12→24h completed-K-line conditional decision, or D2 ATR tracking, without testing D1/D2 now? Provide a prospective, non-executed formal method, input timing/fill budget, power/sample feasibility, falsification conditions and explicit requirement of fresh Controller authority.

Keep 7/14d UTC block CIs and point estimates for *fixed* contrasts; no arbitrary "p-hack" state selection. Compare BASE22/STRESS44 and cost/latency pressure; fixed matched negative control should be labeled diagnostic rather than a ninth trade policy.

**4. Finish end-to-end.** Publish concise quantitative report + JSON: frozen hypotheses, event-level timecap contributions, 12/18/24 bucket metrics, annual/side/regime tables, full account opportunity-cost audit, funding/fee decomposition and code/source identity; report negative cases, limitations, near-term design recommended to Controller. Ruff/compile/strict JSON/≥25 pytest, second **evidence-only** commit and non-force push, remote HEAD/parent/files, GitHub Actions actual conclusion + skips. No production code changes.

## Acceptance/termination

- \`H18_MECHANISM_DIAGNOSTIC_COMPLETE\` if empirical attribution is reproducible and properly bounded, even if no robust alpha exists.
- \`H18_MECHANISM_INCONCLUSIVE\` if cohort support insufficient, outlier-dominated or as-of state features are unavailable; report what was learned rather than endlessly search bins.
- \`H18_MECHANISM_FAIL_CLOSED\` for source/economic/inheritance/cash discrepancy; issue minimal counterexample and do not propagate optimistic R1 interpretation.

Exactly **zero new configurable live/historical exit policies** evaluated. Neither a prospective holdout plan nor a deep diagnostic grants permission to read reserved data or initiate TESTNET/LIVE.
