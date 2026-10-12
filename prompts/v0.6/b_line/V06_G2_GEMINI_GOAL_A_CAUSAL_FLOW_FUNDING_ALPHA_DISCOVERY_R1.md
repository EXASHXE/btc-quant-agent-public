# Gemini Goal A — BTC Flow–Funding–Price Response New Entry Alpha Discovery R1

ROLE: Independent Gemini scientific executor under ChatGPT-0 Controller. Execute a bounded, complete research project, not just write a proposed plan. The scientific objective is *new genuinely different directional entry signals*, not endless strategy mutation until profits appear. Negative findings are valid Goal completion.

TASK_ID: V06_G2_GEMINI_A_FLOW_FUNDING_ENTRY_R1
CONTROLLER_DISPATCH_SHA: 99df4ed8e820984d69d7b895be8808b892ed7f5f
AUTHORITY_URL: https://github.com/EXASHXE/btc-quant-agent-public/blob/99df4ed8e820984d69d7b895be8808b892ed7f5f/reviews/v0.6/b_line/V06_G2_NEXT_WAVE_CODEX_GEMINI_PARALLEL_R1_CONTROLLER_AUTHORITY.md
REPOSITORY: EXASHXE/btc-quant-agent-public
EXACT_START_SHA: 55ac4c631c69f6edbd275462ad23e4486b9782ed
BRANCH: feature/v06-bline-gemini-g2-flow-funding-entries-r1
WORKTREE: /root/workspace/project/quant-v0.6/gemini-g2-flow-funding-r1
SCRATCH: /tmp/btc-g2_flow_funding_entries_r1
OWN_NAMESPACE: g2_flow_funding_entries_r1
READ_ONLY_PREVIOUS: A R2@9415441f216b2eaca6078102cf7ec05b8e6b57cf, B R2@d5e3a8407b1b84111dc7f4276865ffd68cb0a7d2, C R2@c9846adacc1f2df85931ecf4649e02a3a61cf466. Do not import their mutable working trees.

## Why this is new scientific work

Past entry research has tested 48+ hypotheses, 8 additional Goal A R1 variants and 8 Exit/Horizon R1 comparisons. Two W1/W2 developmental lead entries (12h) did not pass multiple-test and year-regime support. Former Goal A C04 required full historical Wilder state, but its live implementation reset monthly state and was non-equivalent; do not rebrand old C01–C04 or manipulate ATR lookback or take results from 2024–25. Focus genuinely distinct source-available microstructure-/crowding-motivated causal mechanisms without claiming L2 or OI.

The research budget is **at most 3 named new signal identities × only two prespecified fixed horizons 12h and 18h = max 6 selectable trials**, each evaluated at STRESS 44bp roundtrip primary, BASE 22bp secondary. Never search parameter grids or use asymmetric alt horizons as unregistered extra trials. Pre-register n minima, event-time source conditions and falsifiers; if only 1–2 identifiable mechanisms are genuinely distinct, evaluate fewer. Avoid constructing 3 synthetic variations of the same signal.

Candidate hypothesis classes (choose at most 3, each must be concretely specified WITHOUT looking at new outcomes):
- **F1 Aggressor-flow / price response divergence:** direction of taker-buy imbalance over completed 15m/1h futures candles versus price progress; price absorption/exhaustion only if exchange source contains authenticated taker-buy base-volume by minute. Never infer aggressive volume from plain OHLC. Forecast falsifier: directionally signed next 12h/18h move remains negative after fee, across distinct years.
- **F2 Realized Funding crowding change:** last two or three previously SETTLED official USDT-M funding rates have a defined sign/quantile shift or positive→negative reversal. Combine with purely backward-looking Last/Mark response, not future estimated funding. If not enough settlements or provider publication time absent, label historical publication-known-at UNKNOWN and use explicit settlement-available proxy with >=1m conservative lag; do not silently assume exchange delivery at settlement instant.
- **F3 Mark–Last divergence/repair:** normalized difference of latest COMPLETED 1m Mark-close vs Last-close sustained over strictly prior 15m/1h; cross with last completed realized volume imbalance for fade/reversion or continuation. These are 1m proxy prices, not true top-of-book futures basis/spot index or proof of available execution prices. Treat as new family only if causally and structurally non-overlapping F1/F2, else omit.

Sources: only Binance USD-M BTCUSDT authenticated public Last/Mark 1m, settled signed funding 2021–23 from original R3/R31 read-only signed ZIPs, including exactly 8 gap repaired daily ZIPs; require the inherited checksum/manifest admission. Source dimensions for futures taker-buy base volume must be proven by raw ZIP CSV schema plus schema tests before use. NEVER use unadmitted OI, liquidation flow, maker/taker book queues, or user private trading records. Never download a substitute after admission fails. No model-generated/invented market candles.

## Stage 1 — PRE-OUTCOME binding freeze (code + independent synthetic tests + remote push)

A1. Verify exact branch base, Controller SHA and excluded paths; inspect previous task negative conclusions and avoid shared worktrees. Define each candidate's economic rationale, precise feature formula, lookback, entry side, signal decision clock, executed signal event time, stop/target/time cap, account no-overlap, rate settlement lag and executable pricing assumptions. Never modify old signals/books.

A2. Freeze explicit **3 max** family definitions, no threshold optimization. Recommend a small number of ex ante coarse, defensible constants that depend only on prior historical knowledge or invariant dimensionless ratios; never select by running P&L or peeking at outcomes. Contract must name objective failure conditions for missing taker-volume/Funding known-at.

A3. Use full 36-month causal feature window or prove warmup equivalence with prefix-mutating tests. Do not repeat C04 monthly ATR(168) reset defect. Signatures and data structures deterministic, UTC PIT bounded, no unclosed minute/1h bar. Freeze exact 12h/18h max duration, TP/SL mechanics, entry/exit fill conservatism and all cost/risk assumptions. 1x notional, 5% reserve, lot 0.001 BTC, minimum notional and tick, no negative available cash, signed Funding on remaining inventory using prior completed 1m Mark proxy, recorded FEE_SPREAD_SLIPPAGE BASE22/STRESS44. Include one-position and cooldown and full 35-fold 24h embargo.

A4. Freeze primary evaluation BEFORE new outcome: full 2021-02..2023-12 development, January warmup; 2023 absolute after-cost PnL, yearly/quarterly counts, total account cash and per-trade signed Funding, per-event matched inverse/control under non-tradable caveat, PSR/PF and MaxMTM DD, 7d/14d calendar blocks with simultaneous max-|T| including all 6 new comparisons. Old earlier ~48 + 8 entry + 8 exit exploratory trials must be disclosed separately; a local six-family correction cannot make global historical optimization bias disappear. Sample viability test predeclare ≥30 executed trade events per identity (not per horizon) and meaningful calendar-week spread; no cutoffs changed after outcomes.

A5. Synthetic suite at least **45 meaningful deterministic tests**: source provenance and column availability, PIT + future mutation, month boundary, 1m Mark Last alignment, funding before/after clock and sign, spot/Mark divergence, extreme imbalance without taker cols fail, account funding/replay/fee/partial, volatility warmup, year boundary, STOP vs TP, entry gates, no negative reserve, replay deterministic. Only read synthetic and manifest metadata before first empirical study. Record each candidate identity SHA256 and method source. Publish code, synthetic tests, method, registration, no historical results FIRST commit; non-force push; independently GET remote branch HEAD/parent and exact changed paths. If unable, terminate SOURCE_OR_FREEZE_BLOCKED.

## Stage 2 — ONE bounded 2021–23 development trial

- Run each frozen eligible hypothesis exactly once across all 35 folds and both 12h/18h, STRESS/BASE. Use identical source and accounting across candidates; actual exchange execution queue uncertainty separate.
- Provide complete 1x account ledger (per-event and daily MTM, cash, funding, drift, signal arrivals, rejected opportunities, capital exhaustion), plus fixed-event equal-notional returns to detect C01-style 2023 false zero-exposure. Compare account vs fixed event separately; no invented ability to scale to 10x/15x.
- Machine outputs per year, 2023 and full 35 months, profits AND losses, event/side, entry and exit clocks, basis, return after roundtrip stress and sign funding, 95% 7d/14d calibrated simultaneous intervals; CI spanning zero means INSUFFICIENT_SUPPORT even if historical mean positive.
- Include kill controls for skipped entry due no source, cash exhaustion, signal absence, support under 30, and after-cost PF≤1. Candidate can earn EXPLORATORY_ELIGIBLE_FOR_NEW_INDEPENDENT_DESIGN only if source valid, freeze exact, support count, 2023 stability, costs and nonzero adjusted lower bound as previously frozen; due exposed prior family this is NOT permission for old protected holdout or TESTNET.
- One pass. No backfill tuning, parameter sensitivity tests with outcomes, hidden second trial, design improvements after seeing results or post-freeze code alterations. If runner bug makes pass invalid, STOP, output INVALID_METHOD rather than silently fix then rerun.

## Stage 3 — evidence / final delivery

- Publish dataset source receipts, immutable first freeze SHA, honest config count, ALL trial results (including negatives), predeclared vs actual identity SHA, full CSV/JSON ledgers, statistical intervals, finance breakdown, untraded controls, clock causal proof, missing data disclaimers, independent Decimal spot cases.
- Test Ruff, compile, strict machine JSON, offline hashes and synthetic suite. Second **evidence/report-only** commit and nonforce push. If final Actions CI documentation lane skips tests, state actual skipped steps and local test command/results, do not equate green docs with full validation. If H40 inherited hash fails, report as separate unrelated red, do not touch H40.
- Terminal: G2_FLOW_FUNDING_NEW_LEADS_DEVELOPMENT_ONLY / G2_FLOW_FUNDING_NO_COST_ADJUSTED_SUPPORT / G2_FLOW_FUNDING_SOURCE_OR_METHOD_BLOCKED. Include exact HEAD+parent+files+CI, full candidate count, positive/negative evidence. No unattended follow-up.

Write only scripts/strategy_research/g2_flow_funding_entries_r1/**; tests/test_v06_g2_flow_funding_entries_r1_*.py; docs/strategy_research/g2_flow_funding_entries_r1/**; evidence/v0.6/b_line/g2_flow_funding_entries_r1/**. Never even list/stat /root/workspace/project/Quant-agent/data or Quant-agent-sanitized, H39/H40/H41/Forward, protected 2024–25, 2024–26 data, A-line or other Goal agents. No private accounts, Binance private or TESTNET/LIVE order API and no merge.
