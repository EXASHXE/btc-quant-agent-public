# Gemini Goal A — BTC Flow–Funding–Price Response New Entry Alpha Discovery R1: Empirical Research Report

**Terminal Scientific Decision**: `G2_FLOW_FUNDING_NO_COST_ADJUSTED_SUPPORT`  
**Task ID**: `V06_G2_GEMINI_A_FLOW_FUNDING_ENTRY_R1`  
**Execution Date**: 2026-10-12  
**Controller Dispatch SHA**: `99df4ed8e820984d69d7b895be8808b892ed7f5f`  
**Authorized Base SHA**: `55ac4c631c69f6edbd275462ad23e4486b9782ed`  
**First Freeze Commit SHA**: `c0296ad38739281b69bcc3294b7706c1009d426a`  
**Branch**: `feature/v06-bline-gemini-g2-flow-funding-entries-r1`  
**Repository**: `EXASHXE/btc-quant-agent-public`  

---

## 1. Executive Summary

This research project executed a strictly bounded, two-stage scientific evaluation of three novel microstructure- and crowding-motivated directional entry mechanisms for Bitcoin perpetuals (Binance USD-M BTCUSDT) across 35 monthly development folds (2021-02 through 2023-12, with January 2021 as causal warmup).

In adherence to scientific integrity principles, **negative findings are reported as valid project completion**. We did not perform unconstrained parameter searches, backfill adjustments, or ad-hoc hypothesis mutations until artificial profits appeared.

### Core Findings
1. **F1: Aggressor-Flow / Price Response Divergence (Absorption)**:
   - Across the 35 development months, the pre-registered coarse flow absorption criteria ($|S_{1h}| \ge 0.20$ with price stalling $\Delta P_{1h} \times \text{side} \le 0$) triggered only **2 executed trade events** (both in 2023).
   - Failed the pre-registered sample viability threshold ($n \ge 30$). Both trades closed at a loss after cost (Profit Factor = 0.0, Mean Net = -91.30 bps, net PnL = -16.54 USDT under STRESS).
2. **F2: Realized Funding Crowding Sign Reversal**:
   - Satisfied the sample viability threshold with **37 executed trades** across distinct years (2021: 3 trades, 2022: 6 trades, 2023: 28 trades).
   - Under the primary STRESS 44bp cost regime, both horizons generated net losses across the 35-month development period:
     - 12h Horizon: Profit Factor **0.37**, 35M Net PnL **-175.21 USDT** (2023 PnL: -115.22 USDT), Win Rate 24.3%, Mean Net -55.42 bps.
     - 18h Horizon: Profit Factor **0.52**, 35M Net PnL **-134.44 USDT** (2023 PnL: -95.42 USDT), Win Rate 32.4%, Mean Net -41.11 bps.
   - The 14-day simultaneous confidence intervals span zero. The directional edge of simple consecutive funding sign flips does not survive exchange fees, spreads, and slippage.
3. **F3: Mark–Last Basis Dislocation and Flow Repair**:
   - Generated **12 executed trades** over 35 months (2021: 9 trades, 2022: 2 trades, 2023: 1 trade).
   - Displayed positive sample performance (12h: PF = **2.15**, 35M Net PnL = **+108.11 USDT**, 2023 PnL = **+10.27 USDT**, Mean Net = +96.39 bps; 18h: PF = **1.77**, 35M Net PnL = **+109.70 USDT**, 2023 PnL = **+9.96 USDT**, Mean Net = +101.93 bps).
   - However, with $n = 12$, it **failed the pre-registered sample viability gate ($n \ge 30$)**. Both 7-day and 14-day simultaneous max-|T| confidence intervals span zero. Under multi-comparison penalization, this sparse sample cannot be distinguished from random drift without further independent data.

**Conclusion**: None of the 6 pre-registered candidate configurations passed all four pre-declared falsification gates. The terminal scientific conclusion is `G2_FLOW_FUNDING_NO_COST_ADJUSTED_SUPPORT`.

---

## 2. Protocol Integrity & Binding Freeze Audit

The experiment strictly adhered to the pre-outcome protocol freeze:
- **Pre-Registration**: Candidate configurations, formulas, and 50 synthetic test cases were frozen and committed in commit `c0296ad38739281b69bcc3294b7706c1009d426a` before running any historical 2021–2023 evaluations.
- **Remote Verification**: Commit `c0296ad38739281b69bcc3294b7706c1009d426a` was pushed to GitHub and independently verified via `git ls-remote` prior to Stage 2.
- **Research Budget**: Exactly 3 candidate families $\times$ 2 fixed horizons (12h, 18h) = **6 selectable trials**. No unadmitted parameters, alternative lookbacks, or hidden grid searches were conducted.
- **Prior Trial Disclosure**: Consistent with the trial family registry, this work explicitly accounts for prior ~48 exploratory trials, 8 Goal A R1 variants, and 8 Exit R1 horizon comparisons. Local multi-comparison adjustments cannot erase global historical selection bias.

---

## 3. Data Source Integrity & Causal Warmup

- **Source Inputs**: Authenticated Binance USD-M BTCUSDT public 1m Last trade klines, 1m Mark price klines (with R31 8-day composite gap repairs), and official settled funding archives from 2021-01 to 2023-12.
- **Taker Volume Provenance**: Authenticated raw ZIP CSV column 9 (`taker_buy_volume`) was strictly required. Plain OHLC volume delta inference was forbidden and tested.
- **Continuous Timeline & Warmup**: The 36 monthly files were assembled into an unbroken, strictly contiguous timeline of **1,576,800 minutes** (26,280 hours). January 2021 served as uninterrupted causal warmup.
- **Absence of Monthly Reset Defect**: In contrast to the legacy Goal A C04 defect where Wilder's ATR(168) state was wiped at monthly boundaries, this engine computed continuous ATR(14) across all 35 development folds without state resets.

---

## 4. Empirical Evaluation Tables

### Table 1: Candidate Overview (STRESS 44bp Primary Regime)

| Candidate Configuration | Family | Horizon | Signals Total | Executed Trades | Win Rate (%) | Profit Factor | Mean Net (bps) | Net PnL (USDT) | Primary Verdict |
|---|---|---|---|---|---|---|---|---|---|
| `F1_AGGRESSOR_FLOW_ABSORPTION_12H` | F1 | 12h | 2 | 2 | 0.0% | 0.00 | -91.30 | -16.54 | INSUFFICIENT_SUPPORT |
| `F1_AGGRESSOR_FLOW_ABSORPTION_18H` | F1 | 18h | 2 | 2 | 0.0% | 0.00 | -91.30 | -16.54 | INSUFFICIENT_SUPPORT |
| `F2_REALIZED_FUNDING_REVERSAL_12H` | F2 | 12h | 48 | 37 | 24.3% | 0.37 | -55.42 | -175.21 | INSUFFICIENT_SUPPORT |
| `F2_REALIZED_FUNDING_REVERSAL_18H` | F2 | 18h | 48 | 37 | 32.4% | 0.52 | -41.11 | -134.44 | INSUFFICIENT_SUPPORT |
| `F3_MARK_LAST_DISLOCATION_REPAIR_12H` | F3 | 12h | 16 | 12 | 50.0% | 2.15 | +96.39 | +108.11 | INSUFFICIENT_SUPPORT |
| `F3_MARK_LAST_DISLOCATION_REPAIR_18H` | F3 | 18h | 16 | 12 | 58.3% | 1.77 | +101.93 | +109.70 | INSUFFICIENT_SUPPORT |

### Table 2: Candidate Performance under BASE 22bp Secondary Regime

| Candidate Configuration | Executed Trades | Win Rate (%) | Profit Factor | Mean Net (bps) | Net PnL (USDT) | Ending Cash (USDT) |
|---|---|---|---|---|---|---|
| `F1_AGGRESSOR_FLOW_ABSORPTION_12H` | 2 | 0.0% | 0.00 | -69.36 | -12.74 | 987.26 |
| `F1_AGGRESSOR_FLOW_ABSORPTION_18H` | 2 | 0.0% | 0.00 | -69.36 | -12.56 | 987.44 |
| `F2_REALIZED_FUNDING_REVERSAL_12H` | 37 | 32.4% | 0.54 | -32.73 | -108.69 | 891.31 |
| `F2_REALIZED_FUNDING_REVERSAL_18H` | 37 | 37.8% | 0.71 | -20.12 | -70.06 | 929.94 |
| `F3_MARK_LAST_DISLOCATION_REPAIR_12H` | 12 | 58.3% | 2.49 | +114.59 | +126.14 | 1126.14 |
| `F3_MARK_LAST_DISLOCATION_REPAIR_18H` | 12 | 58.3% | 1.97 | +118.85 | +128.10 | 1128.10 |

### Table 3: Annual Breakdown under STRESS (44bp)

| Candidate | Year | Trades (n) | Win Rate (%) | Mean Net (bps) | Profit Factor | Net PnL (USDT) |
|---|---|---|---|---|---|---|
| `F1_12H` | 2021 | 0 | 0.0% | 0.00 | 0.00 | 0.00 |
| `F1_12H` | 2022 | 0 | 0.0% | 0.00 | 0.00 | 0.00 |
| `F1_12H` | 2023 | 2 | 0.0% | -91.30 | 0.00 | -16.54 |
| `F1_18H` | 2021 | 0 | 0.0% | 0.00 | 0.00 | 0.00 |
| `F1_18H` | 2022 | 0 | 0.0% | 0.00 | 0.00 | 0.00 |
| `F1_18H` | 2023 | 2 | 0.0% | -91.30 | 0.00 | -16.54 |
| `F2_12H` | 2021 | 3 | 33.3% | -222.39 | 0.26 | -62.24 |
| `F2_12H` | 2022 | 6 | 33.3% | +4.92 | 1.07 | +2.25 |
| `F2_12H` | 2023 | 28 | 21.4% | -50.46 | 0.28 | -115.22 |
| `F2_18H` | 2021 | 3 | 33.3% | -222.39 | 0.26 | -62.24 |
| `F2_18H` | 2022 | 6 | 50.0% | +45.79 | 1.73 | +23.22 |
| `F2_18H` | 2023 | 28 | 28.6% | -40.31 | 0.42 | -95.42 |
| `F3_12H` | 2021 | 9 | 44.4% | +77.73 | 1.77 | +65.90 |
| `F3_12H` | 2022 | 2 | 50.0% | +173.52 | 4.71 | +31.93 |
| `F3_12H` | 2023 | 1 | 100.0% | +110.03 | 999.00 | +10.27 |
| `F3_18H` | 2021 | 9 | 55.6% | +112.10 | 1.71 | +90.20 |
| `F3_18H` | 2022 | 2 | 50.0% | +52.08 | 1.68 | +9.54 |
| `F3_18H` | 2023 | 1 | 100.0% | +110.03 | 999.00 | +9.96 |

### Table 4: Objective Falsification Gate Matrix

| Candidate Identity | Horizon | Gate 1: $n \ge 30$ | Gate 2: PF $> 1.0$ (STRESS) | Gate 3: 2023 PnL $> 0$ | Gate 4: 14d Sim. CI Lower $> 0$ | Final Eligible Status |
|---|---|---|---|---|---|---|
| `F1_AGGRESSOR_FLOW_ABSORPTION` | 12h | FAIL ($n=2$) | FAIL (0.00) | FAIL (-16.54) | FAIL (Spans 0) | INSUFFICIENT_SUPPORT |
| `F1_AGGRESSOR_FLOW_ABSORPTION` | 18h | FAIL ($n=2$) | FAIL (0.00) | FAIL (-16.54) | FAIL (Spans 0) | INSUFFICIENT_SUPPORT |
| `F2_REALIZED_FUNDING_REVERSAL` | 12h | **PASS** ($n=37$) | FAIL (0.37) | FAIL (-115.22) | FAIL (Spans 0) | INSUFFICIENT_SUPPORT |
| `F2_REALIZED_FUNDING_REVERSAL` | 18h | **PASS** ($n=37$) | FAIL (0.52) | FAIL (-95.42) | FAIL (Spans 0) | INSUFFICIENT_SUPPORT |
| `F3_MARK_LAST_DISLOCATION_REPAIR` | 12h | FAIL ($n=12$) | **PASS** (2.15) | **PASS** (+10.27) | FAIL (Spans 0) | INSUFFICIENT_SUPPORT |
| `F3_MARK_LAST_DISLOCATION_REPAIR` | 18h | FAIL ($n=12$) | **PASS** (1.77) | **PASS** (+9.96) | FAIL (Spans 0) | INSUFFICIENT_SUPPORT |

---

## 5. Statistical Falsification & Block Bootstrapping Analysis

To calibrate uncertainty while accounting for serial dependence, we performed 2,000 rounds of calendar block bootstrapping across both 7-day and 14-day non-overlapping intervals, computing studentized max-|T| critical values simultaneously across all 6 comparisons:

- **14-day Block Bootstrap ($n_{blocks} = 76$)**:
  - Frozen studentizer critical value $q_{0.95}$: **2,402,715.59**
  - All 6 candidate configurations produced 95% simultaneous confidence intervals that span zero.
- **7-day Block Bootstrap ($n_{blocks} = 152$)**:
  - Frozen studentizer critical value $q_{0.95}$: **1,201,357.80**
  - All 6 candidate configurations produced 95% simultaneous confidence intervals that span zero.

### Forensic Studentization Analysis
The explosive magnitude of the machine-generated studentized critical value ($q_{0.95} = 2.40 \times 10^6$ for 14d, $1.20 \times 10^6$ for 7d) stems from sample sparsity:
- Candidate F1 generated only 2 trade events across the entire 76-block calendar ($n_{blocks}=76$).
- In approximately 13.5% of bootstrap resamples, all 76 resampled blocks contain zero trades for Candidate F1, resulting in zero sample variance ($\text{std} = 0.0$).
- The algorithm's variance floor ($b\_se = 10^{-6}$) caused studentized test statistics $t = |0 - \mu| / 10^{-6}$ to reach $2.40 \times 10^6$ in those degenerate draws, which directly drove the 95th percentile.
- When evaluated under standard fixed sample standard error studentization ($t = |\bar{X}^* - \bar{X}| / SE_{sample}$), the simultaneous critical value is well-conditioned at $q_{0.95} \approx 2.14$, with realistic confidence intervals (e.g. F2 12h: $[-50.6, -3.3]$ bps per block; F3 12h: $[-7.8, +38.2]$ bps per block).
- **Crucially, under both studentization models**, the simultaneous 95% confidence intervals span zero (or remain strictly negative for F2). Even for F3, where sample mean net return was positive (+96.39 bps), the sparse sample size ($n=12$ over 3 years) produces a lower bound that spans zero, confirming that none of the candidates achieve cost-adjusted statistical significance after controlling for multi-trial evaluation.

---

## 6. Disclaimers & Known Research Limitations

1. **Retrospective Source Publication Timing**: Official Binance funding CSV archives do not contain machine timestamps recording when a settlement was broadcast via WebSocket or REST API. We enforced a conservative $\ge 1$-minute lag ($T_{decision} = T_{settle} + 1\text{m}$), but historical intra-second dissemination latency remains unknown.
2. **Aggregated Base Taker Volume**: Binance 1m kline taker volume aggregates market buys and sells across the entire minute. Sub-minute microstructure features (such as limit order book queue positioning, iceberg absorption, or trade-level cancel ratios) cannot be observed from public 1m klines.
3. **Absence of Optimization**: Thresholds were chosen ex ante based on dimensional logic. While post-hoc optimization could trivially locate profitable parameters in-sample, doing so would violate the scientific mandate of pre-registered discovery.

---

## 7. Deliverables & Artifact Index

All deliverables are cryptographically bound in the namespace directory:
- Frozen Contract: [`FROZEN_CONTRACT.json`](file:///root/workspace/project/quant-v0.6/gemini-g2-flow-funding-r1/evidence/v0.6/b_line/g2_flow_funding_entries_r1/FROZEN_CONTRACT.json)
- Remote Verification: [`FIRST_FREEZE_REMOTE_VERIFICATION.json`](file:///root/workspace/project/quant-v0.6/gemini-g2-flow-funding-r1/evidence/v0.6/b_line/g2_flow_funding_entries_r1/FIRST_FREEZE_REMOTE_VERIFICATION.json)
- Source Identity: [`SOURCE_IDENTITY.json`](file:///root/workspace/project/quant-v0.6/gemini-g2-flow-funding-r1/evidence/v0.6/b_line/g2_flow_funding_entries_r1/SOURCE_IDENTITY.json)
- Full Results: [`FLOW_FUNDING_RESULTS.json`](file:///root/workspace/project/quant-v0.6/gemini-g2-flow-funding-r1/evidence/v0.6/b_line/g2_flow_funding_entries_r1/FLOW_FUNDING_RESULTS.json)
- Delivery Manifest: [`FLOW_FUNDING_DELIVERY_MANIFEST.json`](file:///root/workspace/project/quant-v0.6/gemini-g2-flow-funding-r1/evidence/v0.6/b_line/g2_flow_funding_entries_r1/FLOW_FUNDING_DELIVERY_MANIFEST.json)
- Analysis Tables: [`FLOW_FUNDING_COMPLETE_ANALYSIS_TABLES.json`](file:///root/workspace/project/quant-v0.6/gemini-g2-flow-funding-r1/evidence/v0.6/b_line/g2_flow_funding_entries_r1/FLOW_FUNDING_COMPLETE_ANALYSIS_TABLES.json)
- Complete Order Ledgers: 12 `.jsonl` trade order and paired control records under `evidence/v0.6/b_line/g2_flow_funding_entries_r1/`.
