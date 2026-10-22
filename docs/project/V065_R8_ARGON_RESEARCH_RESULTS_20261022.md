# R8-8 and Argon Parallel Research Results — 2026-10-22

**Status: five tasks completed; no new empirical strategy result.** This report consolidates verified remote receipts and the existing R8-7 ledger diagnosis. The engineering tasks ran in separate worktrees from executable baseline `40c70c740f352d1b444decb75276196d17a72dd2`. All five Codex processes exited with code 0. No task committed or pushed code, read protected 2024–2026 outcomes, downloaded market data, or calculated new historical returns for R8-A/B/C/D.

## Executive decision

1. Close the fixed 8-hour R8-7 X-only baseline as economically negative. Do not rescue it by sign, side, delay, threshold, exposed regime cell, or an after-the-fact exit rule.
2. Accept R8-A indicator primitives and R8-B E0–E3 as **synthetic engineering artifacts only**, pending an explicit integration review. Their tests are not evidence of alpha.
3. Keep R8-C trend and R8-D carry/flow as untested, pre-outcome candidate designs. No empirical strategy study is authorized by their engineering receipts.
4. The sole mechanism selected by R8-8 for a future independent registration is **forced-liquidation flow exhaustion with contract-count open-interest destruction and a still-displaced perpetual/spot anchor**. This is a hypothesis, not a completed registration or a proven signal.
5. Before any new historical outcome access, establish source completeness and receiver-clock availability for the selected mechanism; otherwise reject it rather than substitute price/volume proxies. Owner authorization and a frozen registration are required before outcome evaluation.

## 1. Frozen R8-7 economic baseline

R8-7 used 545 frozen BTCUSDT X-only reference events across 2021–2023: 150/215/180 events by year, 275 LONG and 270 SHORT. Each event uses 10,000 USDT fixed notional against 100,000 USDT initial research equity, a cutoff+2-minute entry and an 8-hour modeled hold. These are modeled fixed-notional economics, not real account PnL.

| Layer | Cash PnL (USDT) | Profit Factor | Interpretation |
|---|---:|---:|---|
| Gross | -3,081.947168 | 0.918662 | The reference rule is already negative before modeled execution charges. |
| Base, ex-funding | -11,802.832667 | 0.719279 | Costs worsen the result materially. |
| Stress, ex-funding | -20,523.718167 | 0.561721 | The result deteriorates under stress assumptions. |

All three years are base ex-funding negative. Funding-inclusive net is **unknown/null**, not zero. Fill/no-fill evidence is absent, and receiver-clock point-in-time availability remains unknown. The result is not a liquidation-survival or collateral drawdown study.

## 2. R8-8: existing-ledger loss diagnosis

R8-8 did not rerun R8-7 or read raw price archives. It aggregated only five existing R8-7 artifacts and checked the existing ledger against the frozen summary and receipt.

- **3,772 checks passed** across 15 overall/year/side/frozen-regime cohorts.
- Maximum numeric discrepancy: approximately (2.84\times10^{-14}).
- The base cost bridge is approximately -3,081.947168 gross minus 8,720.885500 modeled charges = -11,802.832667 USDT.
- The accounting attribution assigns 73.8881% of the absolute base loss to modeled fees, half-spread and slippage. This is not a causal estimate of costs that could actually be eliminated; gross PnL is already negative.
- Gross-direction wins occurred in 303/545 events (55.5963%), but mean gross loser was about -156.574 USDT versus mean gross winner +114.881 USDT. Hit rate therefore overstates economic quality.
- No year is base-net positive. Both pooled long and short sides are negative.
- Moving entry and exit together to the existing +60-minute timing case improves base ex-funding cash PnL to -8,402.706097 USDT, but still does not cover modeled charges. This does not isolate an entry effect and is not a delayed-entry rescue.
- An exposed positive return/RV tercile cell has only 32 events. It is descriptive and cannot be promoted into a post-hoc strategy filter.

Conclusion: unfavorable payoff asymmetry and insufficient edge per turnover both matter. Do not infer that lower costs alone would fix the rule, and do not interpret exposed subgroup differences as validated conditional alpha.

### Selected next mechanism (not yet registered)

R8-8 selected one prospective question: can directly observed forced perpetual-liquidation flow create temporary inventory pressure that relaxes after compulsory flow subsides?

A future registration must require, before entry:
- directly reported, side-specific liquidation transactions with documented completeness;
- contract-count open-interest destruction (not USD OI change alone);
- a subsequent pre-entry interval demonstrating that forced flow has subsided;
- an independently timestamped spot anchor and a still-present perp/spot displacement;
- executable perpetual quotes/depth and valid receiver clocks for every required input.

The proposed single hold is four hours after modeled entry, with no threshold grid or optimized exit sweep. Compare against a frozen spot-led/no-OI-destruction control to test the competing explanation of informed repricing. The traded perpetual itself must move in the predicted direction; basis convergence caused only by spot moving is not tradable evidence. Freeze costs, fill/no-fill treatment, funding settlement, uncertainty method and acceptance/falsification criteria before outcome access. If feed completeness, contract OI, receiver clocks or executable-price evidence cannot be established, reject the mechanism. No performance estimate or event count has been produced.

## 3. Five-task completion record

| Task | Completed scope | Validation | Research status |
|---|---|---|---|
| R8-8 loss attribution | Existing-ledger reconciliation and one new mechanism proposal | 3,772 reconciliation checks; read-only verify passed | Completed; no new outcomes |
| R8-A indicator layer | Causal closed-hour aggregation and indicator primitives | 48 tests; Ruff and compilation passed | Synthetic engineering only |
| R8-B exit engine | E0–E3 path exits, costs/funding adapters, causal chronology | 82 tests (51 new focused + 31 existing cost semantics); Ruff and diff checks passed | Synthetic engineering only |
| R8-C trend candidate | Frozen trend/regime candidate and paired X controls | 76 tests; Ruff and compilation passed | No empirical PnL or alpha claim |
| R8-D carry/flow | Causal basis/funding z-scores and signed flow interaction | 43 synthetic tests; Ruff, compilation and reproducibility passed | No real joint coverage or empirical PnL |

All tasks ran in independent worktrees under:
`/root/workspace/project/crypto-data/lakehouse/r8-argon-parallel-20261022/worktrees/`

Per-task receipts and launch/exit logs are authoritative. All five completed on attempt 1 with `exit.code=0`. The supervisor verified R8-C and R8-D task output after their post-06:00 Beijing launch. No retries were required.

## 4. Engineering findings and integration blockers

### R8-A indicators

The library implements closed-only UTC hourly aggregation and EMA/MACD, Wilder ATR/ADX, KDJ, prior-24-hour median RVOL, VWAP, signed taker-flow imbalance and KER, with explicit seeds, missingness and configurable 240-hour readiness policy. The warmup is an engineering readiness choice, not empirical convergence evidence.

**Seed mismatch must be resolved before integration:** R8-A uses SMA-seeded EMA/MACD initialization, while R8-C intentionally uses existing production EMA/ATR primitives with different seeding. Their values cannot be silently mixed or described as a shared feature baseline. Freeze one implementation and validate compatibility before any real-data trial.

### R8-B exit engine

E0 is fixed maximum hold plus mandatory ATR hard stop; E1 adds a take-profit; E2 uses a completed-hour reversal with delayed HH:02 execution while monitoring the hard stop during the delay; E3 uses an ATR trailing stop updated only from prior completed minute bars. Missing bars, unresolved fills, cost assumptions and funding coverage remain explicit.

E0–E3 are **new strategy arms**, not a replacement definition for R8-7's original 8-hour no-stop baseline. No historical backtest was run.

### R8-C trend candidate

The synthetic plan declares five arms × three holds (4/12/24h) × four exit policies = 60 cells. Its sole primary candidate comparison is `X_KER / 12h / E0` versus `X / 12h / E0`. The declared candidate family contains 48 candidate comparisons; any future family-wide inference must account for multiplicity. The 76 passing tests establish implementation behavior only.

### R8-D carry/basis and source feasibility

The new feature API passed 43 synthetic tests. **Real joint feature coverage remains unknown.** The legacy count of 35,250 funding-z eligible hours is not coverage evidence for the new intersection of price/flow X, basis z-score, funding z-score, signed flow and valid receiver clocks. The canonical normalized bars schema does not retain native taker-buy columns; a separately validated flow source may be required. Historical normalizer clocks can be null/PIT-unknown. No source was admitted by this task.

## 5. Required next gates

1. **Source feasibility first, metadata-only:** verify whether one venue/contract has complete side-specific liquidation reports, contract-count OI, spot reference, executable perp quotes/depth and usable receiver timestamps over an independently authorized period. Do not inspect outcomes while defining the source contract.
2. **Freeze the registration:** define one burst rule, flow-cessation window, spot anchor, entry latency, four-hour exit, overlap policy, cost/funding assumptions, missingness accounting, paired controls, inference method and acceptance/falsification criteria. No parameter grid.
3. **Resolve integration semantics:** align indicator seeds and the cutoff/decision/entry clock; integrate R8-A/B/C in a separate review worktree only after an explicit integration task. Preserve R8-7 and protected-data boundaries.
4. **Owner authorization before outcomes:** no historical return calculation for the selected mechanism or R8-C/R8-D candidates until the source/registration is frozen and the Owner explicitly authorizes the exact sample and outcome scope.
5. If the selected liquidation mechanism fails source feasibility, report it as source-blocked; do not automatically pivot to carry/basis outcomes without a separate decision.

## 6. Evidence locations and provenance

Remote execution root:
`/root/workspace/project/crypto-data/lakehouse/r8-argon-parallel-20261022/`

- R8-8: `worktrees/R8_8_LOSS_ATTRIBUTION/R8_8_LOSS_DIAGNOSIS.md`, `R8_8_NEW_MECHANISMS.md`, `R8_8_RECEIPT.json`
- R8-A: `worktrees/R8_INDICATORS/R8_INDICATOR_SPEC.md`, `R8_INDICATORS_RECEIPT.json`
- R8-B: `worktrees/R8_EXIT_ENGINE/R8_EXIT_SPEC.md`, `R8_EXIT_RECEIPT.json`
- R8-C: `worktrees/R8_TREND_DESIGN/R8_TREND_PLAN.md`, `R8_TREND_RECEIPT.json`
- R8-D: `worktrees/R8_CARRY_DESIGN/R8_CARRY_PLAN.md`, `R8_CARRY_SOURCE_COVERAGE.md`, `R8_CARRY_RECEIPT.json`
- Process proof: `runs/<TASK>/attempt_1.log`, `runs/<TASK>/exit.code`, `future_schedule_monitor.log`, `monitor_latest.tsv`

The five worktrees remain isolated and unmerged. No real market payloads, new historical outcome calculations, protected 2024–2026 outcome reads, account operations, commits or pushes were part of these research tasks.
