# Gemini Goal B — One-Shot Causal Conditional 12h→18h Exit Study R1

Role: autonomous Gemini scientific executor, separate from Gemini A flow-funding search and Codex G1 offline preview. Implement an end-to-end frozen, bounded 2021–23 development study. A transparent negative/insufficient result is successful Goal completion; never rerun and tune for profit.

TASK_ID: V06_G2_GEMINI_B_CONDITIONAL_EXIT_R1
CONTROLLER_DISPATCH_SHA: 99df4ed8e820984d69d7b895be8808b892ed7f5f
CONTROLLER_AUTHORITY: https://github.com/EXASHXE/btc-quant-agent-public/blob/99df4ed8e820984d69d7b895be8808b892ed7f5f/reviews/v0.6/b_line/V06_G2_NEXT_WAVE_CODEX_GEMINI_PARALLEL_R1_CONTROLLER_AUTHORITY.md
REPOSITORY: EXASHXE/btc-quant-agent-public
BRANCH: feature/v06-bline-gemini-g2-conditional-exit-r1
EXACT_START_SHA: d5e3a8407b1b84111dc7f4276865ffd68cb0a7d2
WORKTREE: /root/workspace/project/quant-v0.6/gemini-g2-conditional-exit-r1
SCRATCH: /tmp/btc-g2_conditional_exit_r1
OWN_NAMESPACE: g2_conditional_exit_r1
READ_ONLY_ORIGINAL_EXIT_R1: 55ac4c631c69f6edbd275462ad23e4486b9782ed
READ_ONLY_MARGIN_R2: c9846adacc1f2df85931ecf4649e02a3a61cf466

## B-line Controller rationale

The frozen W1_C04 (34 original 12h events) and W2_C05 (55 original 12h events) showed positive 12→18h point increment, +37.3453/+22.4342 STRESS basis points per original trade, but ALL 7-day and 14-day eight-comparison simultaneous CIs span zero, and W2 year 2023 absolute returns remain negative. B R2 as-of market state labels are descriptive and cannot act as proven predictors. The 18h increment is concentrated in a handful of 12–18h target hits, not a universal horizon effect; 24h deteriorates. This authorizes **one new precommitted conditional decision at the 12h boundary**, not retrospective optimization or previous D1/D2 design replay.

## Exact 4-config research contract

Original two entry IDs, stop, target and original 1x / Mark / signed observed funding / 5% reserve / lot / cash / ACK / cooldown unchanged. Two new **conditional schemes** for each candidate; no threshold variants, horizon grid, TP retuning or leverage:

- **X1_NET_POSITIVE_AT_12H**: For an original entry that survives to the moment immediately before its 12h TIME_CAP, compute unrealized signed direction-adjusted net USDT at the most recent strictly completed 1m Mark close (as-of UTC decision), using effective entry and all accrued known funding plus known entry fee and hypothetical frozen exit fee+STRESS/BASE execution friction. If this estimated liquidation NET > 0 USDT, then continue with same original STOP/TARGET until 18h maximum; otherwise exit at 12h exactly as E0. A zero estimate exits. This is a **Mark-based selection proxy** and does not assume Mark fill. The actual exit fill remains Last with conservative slippage and fee. Use no future minute or later funding.
- **X2_COMPLETED_4H_TREND_AT_12H**: For a surviving original entry at 12h, compute signed price return over the most recent 4 fully closed 1h Last candles available at that exact decision clock; if side * (last closed 1h close − earliest previous completed 1h close) > 0, continue with identical original STOP/TARGET up to 18h; otherwise close at 12h exactly E0. Zero returns exit. Use 1h candle CLOSE-TIMESTAMP ≤ decision time, NOT future or unclosed hour bar.
- An original trade that already exits by STOP/TARGET before 12h stays byte-identical to E0. A trade that exits at 12h uses original E0 execution and ACK semantics; extension uses unchanged H1 18h stop/target and costs except the conditional decision as-of.
- **No switch based on future 12–18h path, hindsight TARGET, past B R2 outcome-favorable subgroup or 2023 results.** No "selected best exit" after results; both schemes reported regardless of support.

There are exactly **2 signals × 2 schemes = 4 new selectable test cells**. E0 original 12h / H1 18h baselines are pre-exposed references; STRESS44 (24 fee+8 spread+12 slippage bps roundtrip) primary, BASE22 secondary, not alternative selection cells. The oldest 48 entry+8 Goal A+8 original Exit tests plus 4 new conditional comparisons remain disclosed to prevent overclaiming after serial tests. Don't claim valid independent Alpha from any family-wise bound estimated solely on these same 2021–23 data.

## Work package P0 — exact as-of and source provenance

- Confirm Git branch SHA and original immutable paired E0/H1 event IDs: W1 34, W2 55; source Last 2021–23 1,576,800 minutes, Mark stitched gap-composite with exact SHA256, 3,285 historical official signed Funding events, all read-only from authorized R3/R31 caches. If source missing, stop NO_SOURCE, do not download substitute.
- Verify B R2 old post-entry future MFE/MAE and funding bins are formally revoked. X1/ X2 may use price history observed by the 12h **holding-time decision** but cannot use data after that decision, and must never be mislabeled as an ENTRY-time predictor.
- Define exact 12h TIME_CAP semantics relative to decision time, last completed Mark/Last stamps and known settled Funding. An 11:59 bar with close not observed at decision must not be used; use conservative publication lag where exact known-at uncertain. Enforce no off-by-one time edge crossing. If E0 has earlier stop at the boundary minute, conservative intrabar STOP precedence holds, no contingent selection.
- Verify final month censoring (2021-02 to 2023-12 scored 35 folds; Jan2021 warmup; 24h embargo) and no trade crossing to a later month.

## Work package P1 — freeze complete implementation BEFORE outcome

- Write a **standalone sibling executable accounting/exit mechanism under own namespace** that reuses original immutable entry candidate and source-loader contracts read-only but never modifies original Exit R1, B R2, other 2 agents, or production engine. Validate original E0/H1 ledger SHA and all original E0/H1 price/fee/Funding/Mark before first execution. Dynamic exit accounting shall conserve quantities/cash after partial fills and record ACK and missed signal arrivals.
- Predeclare detailed primary research gates: (a) enough original eligible 12h TIME_CAP supports ≥20 W1 / ≥36 W2 but conditional branch splits may be underpowered and cannot be optimized; (b) new X1 and X2 exact event-level cash and full-account PnL; (c) support by UTC weeks, same-day clustering and 2023 absolute sign; (d) 7d/14d paired block bootstrap with simultaneous max-|T| for all **four** comparisons (X1−E0, X1−H1, X2−E0, X2−H1) across W1/W2, disclose 8 contrasts or exact full family as applicable. Report multiplicity and post-selection.
- Strict account proxy: 1x, 5% cash reserve, 0.001 lot, minimum 5USDT notional, one position, cooldown, fee/spread/slip, signed historical funding at latest completed 1m Mark. No 10x/15x scale. If new scheme changes next accepted signal, recompute full account events instead of asserting the old set is unchanged. Fixed-event matched report and whole account separately, with all missing/censored counts.
- Build **≥55 deterministic synthetic tests**, covering X1 positive/negative/zero at 12h, net PnL cost handling, funding sign and accrual before/after 12h, Mark/Last divergence, 1h close time mid-hour, STOP within boundary minute versus conditional cap, TP before 12h, STOP and TARGET collision during extension, 18h cap, entry/exit ACK, funding receipt de-dup, partial tiers despite policy normally full-position, 2023 and 2021 clock month edge, no future data after 12h, 50% future bar mutation invariance, lot/min notional, cooldown, account position blocking, 35 fold embargo and replay-to-original baseline identity. Independent Decimal ≥20 synthetic/previous-R1 event witnesses for cost and quantity.
- Freeze ALL thresholds, policies, code, module imports, tests, cost and data admission in **one FIRST method/code/tests commit**. Nonforce push and explicitly verify remote HEAD+parent+changed scope BEFORE any new real historical outcome. If bug discovered afterward, STOP INVALID_METHOD and report without post-freeze implementation code alteration. No silent optimizing second run.

## Work package P2 — exactly one full development pass

- For 2021-02 through 2023-12 public BTCUSDT Last/Mark/Funding replay each X1 and X2 once per W1/W2, and at both frozen STRESS/BASE cost tiers. Recompute **full-cash portfolio** and paired-event deltas. Do not generate new entry candidates, D1/D2 variations or third policy.
- Output decisions at 12h with exact as-of feature values and source bar/settlement clocks; count X1/X2 extensions, false extensions, early-stop, early-target, 12–18h new TP/STOP/cap, 2021/22/23 breakdown, fee/funding/drag, per-trade means & medians, PF, account return, MTM MaxDD, capital occupancy and missed opportunities. If a fraction of extension outcomes are only 1–2 trades, declare thin evidence.
- Compare against E0 and H1 original immutable evidence, include W2 2023 negative sign and right-tail concentration. Every metric from machine primary ledger; human report generated from that canonical object, machine-to-report equality test prevents prior copy errors.
- Bootstrap 7d/14d same-calendar block resampling and simultaneous confidence for all predeclared pairwise comparisons. Do not promote a positive observed subgroup if its adjusted interval includes zero. A counterfactual 12h Mark estimate may be optimistic relative to Last fill; evaluate as causal proxy, not executable 1m L2 queue evidence.
- One pass; no extra outcome-informed control tweaks, thresholds, unregistered 18/24h variants, extending to 2024–25, "stop only once positive". Reproducibility outputs all configs including losing ones.

## Work package P3 — delivery/terminal

Publish X1 and X2 frozen registry, actual code freeze SHA (strict check), source checksum/source known-at, cohort support, 35-fold & year ledgers, paired/full account decomposition, block interval family, independent 20 Decimal audits and machine-composed report. Submit second EVIDENCE+REPORT ONLY commit and nonforce push; verify exact parent chain, file diff and observed GitHub Actions mode. All tests Ruff/compile/strict JSON; inherited H40 hash failure a separately stated preexisting CI failure. If any implementation post-freeze semantic change is needed, refuse automatic rerun; Controller must approve fresh method.
 
Terminal classification only: X1_X2_DEVELOPMENT_ONLY_CANDIDATE_SIGNAL (if genuinely independently supportive), X1_X2_INSUFFICIENT_SUPPORT, X1_X2_METHOD_OR_SOURCE_BLOCKED. NONE grants policy promotion, protected holdout, TESTNET, LIVE or real funds; do not claim "optimal horizon" or automatic conditional switching.

Only write scripts/strategy_research/g2_conditional_exit_r1/**, tests/test_v06_g2_conditional_exit_r1_*.py, docs/strategy_research/g2_conditional_exit_r1/**, evidence/v0.6/b_line/g2_conditional_exit_r1/**. **Never even stat or list** /root/workspace/project/Quant-agent/data or Quant-agent-sanitized, any protected 2024–26/H39/H40/H41/Forward, other agent worktrees, A-line/Performance, private accounts or trading APIs. No merges. Be willing to fail closed.
