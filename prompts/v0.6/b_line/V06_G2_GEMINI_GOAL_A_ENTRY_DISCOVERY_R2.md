# GEMINI GOAL A — BTC 4–24h Causally New Entry Discovery R2

**Mode:** Gemini Goal / sustained autonomous implementation + research, NOT summary-only. Continue through schema inspection, freeze, code/tests, one historical run, independent evidence, reporting and non-force push until a scientifically legitimate terminal is reached; never loop indefinitely seeking a positive backtest.
**CONTROLLER_DISPATCH_SHA:** c02743fddccdf517582c371a47e82d8dcbb05923
**Authority:** https://github.com/EXASHXE/btc-quant-agent-public/blob/c02743fddccdf517582c371a47e82d8dcbb05923/reviews/v0.6/b_line/V06_G2_POST_EXIT_R1_THREE_GEMINI_PARALLEL_GOAL_PROGRAM_CONTROLLER_AUTHORITY_R1.md
**B-line Controller:** ChatGPT-0. **No cross-line authority.**
**Repository:** EXASHXE/btc-quant-agent-public
**EXACT_START_SHA:** 55ac4c631c69f6edbd275462ad23e4486b9782ed
**OWN BRANCH:** feature/v06-bline-gemini-goal-entry-discovery-r2
**OWN WORKTREE:** /root/workspace/project/quant-v0.6/gemini-entry-discovery-r2
**OWN SCRATCH:** /tmp/btc-gemini-entry-goal-r2
**OWN PREFIX:** g2_goal_entry_discovery_r2
**Allowed write paths only:** scripts/strategy_research/g2_goal_entry_discovery_r2/**; tests/test_v06_g2_goal_entry_discovery_r2_*.py; docs/strategy_research/g2_goal_entry_discovery_r2/**; evidence/v0.6/b_line/g2_goal_entry_discovery_r2/**.
**No force push. Auto push BOTH stage commits and independently verify exact remote HEAD/parent.**

## Mission and scientific question

Find **genuinely new entry signals** suitable for BTCUSDT USD-M 4–24h short swings with friction-adjusted observed-Funding economics, without rehashing, retuning or cherry-picking old 48 trials, original W1_C04/W2_C05 or 8 Exit R1 contrasts. Make the signal causally available at entry, and evaluate not only isolated trades but feasible account execution. You have the full Goal loop to implement all components and close the evidence, not merely write a proposal.

Historical source: official Binance Vision BTCUSDT USD-M **2021–2023 only**, Last 1m authenticated archives including OHLC/volume and valid taker trade volumes where proven present; 1m Mark proven R31 daily eight-day composite; authentic 3,285 past funding rate settlements. Original R3/R31 source caches read-only if SHA verified; if not available, one bounded public provider-original same-era redownload with checksum allowed after method freeze. Historical known-at publication, exact exchange settlement Mark, L2 and actual maker fills remain unproven. All 2024–2026/private/protected owner/A-line/Forward/H39/H40/H41 and even list/stat of /root/workspace/project/Quant-agent/data or Quant-agent-sanitized are absolutely forbidden; no orders, Testnet, Live, credentials.

**Core novelty:** do not merely change previous W1/W2 entry threshold or search new ATR multipliers. Design **3–6 different entry hypotheses** with distinct causal mechanisms from a fixed menu such as:
1. Macro-to-micro trend pullback/reclaim using confirmed 1h alignment, completed 15m retracement and 5m confirmation, not original high-channel breakout;
2. Failed-breakout exhaustion / directional reversal with causally completed reclaim and observable volume confirmation, not original directional breakout;
3. Post-liquidation-proxy volatility shock continuation OR exhaustion with public-volume/return-only proxy clearly not true liquidation tape (choose one pre-freeze);
4. Intraday range reversion at pre-known range limits in range-classified states;
5. Volatility compression release with a different causal filter than existing W1/W2, or omit if duplicate;
6. Directional participation imbalance using verified taker-buy/base-volume bar fields *only if source schema proves known-at*, else omit.

Do not force six weak hypotheses: minimum three genuinely distinct executable hypotheses is a valid Goal output. For each, create exact independent candidate ID, mathematical Boolean event, feature units, historical availability time, minimum warmup, entry order/proxy, side, fixed stop rule from completed ATR/structure, R target, cooldown, risk caps, and falsifiable economic mechanism. None is a text-only aspirational hypothesis. Reject clones before freeze, with an explicit duplicate map to old 48 trials.

## Nonnegotiable research budget

- **Maximum 6 immutable new candidate identities × 2 predetermined horizons (12h primary, 18h secondary) = ≤12 new exploratory configurations.** 18h is a sensitivity motivated by the *already exposed* R1; it is NOT unbiased. No 8h/24h extra tests in this Goal. Do not select which horizon to report based on profit.
- Execution: fixed original 1x/5% reserve single-position and LOT/tick/min-notional/ACK/cooldown semantics, initial risk frozen per hypothesis, original Last-open adverse effective execution; actual observed signed funding and completed-Mark-close notional approximation, minute Mark MTM; BASE22bp and STRESS44bp (STRESS primary). Do not simply label a high-price backtest as executable. If existing imported replay cannot validly handle a proposed feature or account book, implement **minimal sidecar** and prove E0 R31 reference runs without mutating old code.
- **Trial budget includes every failed/no-trade attempted config**. Publish counts, names, reasons, all 3y results, market-state/side/yield distribution including 2023 and negative cases, never omit rejected candidates. No parameter grids, Bayesian optimizer, gene search, manual threshold post-tuning, choosing entry confirmation time after seeing P&L or repeating with new thresholds after outcomes.
- Causal sampling: derive 1h/15m/5m windows only from completed raw 1m; last unfinished bar never used; set event end -> decision -> entry order with at least original two 1m causal delays; first open trade fill adverse cost, gap veto; time cap 12/18h, risk stops and pre-frozen target exit, stop-before-target collision, conservative limit TP proxy. Require no use of future realized vol/funding/regime classification at entry.
- No 2024–25 reserved holdout or partial probe. Do not try to compensate small N by repeated thousands of speculative signals. Stop when eligible N too small / source claims unproven: report diagnostics and objective unsupported grades.

## GOAL workflow (must be executed, not merely described)

**STEP 0 — identity & schema-only scope.** Confirm branch HEAD exactly start SHA and clean independent worktree. Verify inherited source hash and allowable 2021–23 volume field schema from archived manifest/header **without looking at newly computed strategy outcomes**. Declare selected 3–6 families and maximum 12 configurations.

**STEP 1 — code-and-hypothesis FREEZE before new outcome inspection.** Implement frozen signal registry, causal feature compiler, first-entry/stop/target/cost/settlement contracts, monthly fold/purge protocol, per-account replayer adapted to frozen R3.1/E1 models only as legitimately needed, controls and inference plan. Freeze candidate IDs and thresholds in machine JSON (include max trial family 12 and prior 48+8 exposure). At least **30 bounded synthetic tests** including lookahead/resample, entry delay, stop/target collision, signed Funding, fee/quantization, source gap, monthly fold/purge, cash and reproducibility. Commit (parent exact start), non-force **PUSH** branch, verify remote exact SHA; write stage-1 remote verification. This is a no-market-new-outcome method freeze.

**STEP 2 — single COMPLETE genuine development replay.** Re-check freeze code bytes/SHA before using real outcomes. Use only admitted Last/Mark/Funding 2021–23, Jan2021 warmup + 35 scoring months and 24h purge; only those 3–6 hypotheses and 12h/18h caps; calculate actual signals, admitted fills, declined entries, direct/trade + funded cash, BASE and STRESS, minute account liquidation-value MTM and opportunity constraints. Whole-account fresh signal stream per hypothesis (not editing existing trades). Export trade/event/cash and month-ledger hash receipts, source/computation identities, ≥6 independent real Decimal transaction + signed Funding crosschecks including both sides where present.

**STEP 3 — adversarial scientific result and controls.** Add predeclared matched baseline events (time/vol matched where causal), monthly/annual/2023, 7d/14d block simultaneous 95% maxT across all *attempted* new configs, shared seed=42 / 10k draws, empty blocks preserved. Cite previous 48 entry and 8 exits as already exposed; if cannot reconstruct joint null over all, say familywise adjustment is conditional and no Alpha. Report STRESS positive *and* failures, 2023, effective N, robustness under alternative friction 22/44 plus fixed +5/+10bp tier pressure, cost/Mark/fee/queue unknowns; no positive-PF auto promotion.

**STEP 4 — deliver, validate, push.** Produce readable scientific report plus frozen registry JSON, all attempted results JSON, per-year metrics, source/CI/tests and negative outcomes, reproducible commands. Scoped Ruff/compile/strict JSON/pytest, independent hash review; second result/evidence-only commit and nonforce push; verify remote HEAD, exact parent, changed paths and CI actual status/skip. Return branch, freeze SHA, result SHA, commit manifest, top mechanisms, all result rows, blockers, terminal.

## STOP/TERMINALS

- \`ENTRY_GOAL_EXPLORATORY_COMPLETE_NO_PROMOTION\`: full frozen bounded run with honest diagnostics (regardless profits).
- \`ENTRY_GOAL_NO_SUPPORTED_NEW_LEADS\`: full run, no credible cost-adjusted hypotheses under predeclared evidence gate, or insufficient observations; a **successfully closed scientific Goal**, not a task failure.
- \`ENTRY_GOAL_FAIL_CLOSED\`: unacceptable source, lookahead, data-scope, cash/ledger, frozen identity, or semantic error. Show minimal proof; no misleading P&L and no new variants or optimization.

Do NOT independently dispatch follow-on experiments, heldout, Testnet, Live, real account, an unbounded multi-agent swarm, or change branches to find favorable results. Strong evidence can be *suggested* to Controller for new preregistered independent chronological validation only.
