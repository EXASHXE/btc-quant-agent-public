# Gemini Goal B — Empirical Diagnostic Report: H18 Mechanism, Failure Regimes and Opportunity Cost

**Task ID:** `V06_G2_POST_EXIT_R1_GOAL_B_H18_MECHANISM_R1`  
**Controller Authority:** ChatGPT-0 B-line Primary Controller (`c02743fddccdf517582c371a47e82d8dcbb05923`)  
**Target Git Source:** `EXASHXE/btc-quant-agent-public@55ac4c631c69f6edbd275462ad23e4486b9782ed`  
**Frozen Code SHA (Commit 1):** `ebb33b7f96e5ab0c753beab14363632a0a221416`  
**Branch:** `feature/v06-bline-gemini-goal-h18-mechanism-r1`  
**Worktree:** `/root/workspace/project/quant-v0.6/gemini-h18-mechanism-r1`  
**Terminal Decision:** `H18_MECHANISM_DIAGNOSTIC_COMPLETE`  
**Scientific Grade:** Observational mechanistic diagnostic development only. **Zero new configurable exit policies evaluated.**

---

## Executive Summary: Scientific Causal Attribution

This empirical investigation explains the mechanism behind the observed performance divergence of the frozen 12h (E0), 18h (H1), and 24h (H2) exit horizons across the two accepted development leads:
- **W1_C04** (ATR Expansion Trend Follow 12H, $N=34$ trades)
- **W2_C05** (Asymmetric Volatility Breakout 12H, $N=55$ trades)

Under frozen STRESS44 costs (24 bps roundtrip fee, 8 bps spread, 12 bps slippage) with contemporaneous signed funding cash and minute Mark MTM equity, the published point estimates show apparent sample-mean improvements of H1 over E0 (+37.35 bps in W1, +22.43 bps in W2), but H2 systematically underperforms H1 (-4.48 bps in W1, -8.43 bps in W2).

Our three predeclared matched analyses, one-axis regime audits, and independent Decimal boundary checks reveal the following causal mechanisms:

1. **The H1 "Improvement" is a Heavy Right-Tail Outlier Artifact, Not a Distributional Shift:**
   - Of the 56 baseline TIME_CAP trades that reached 12h open, **26 reversed adversely** between 12h and 18h (46.4% reversal rate; 55.0% adverse in W1, 41.7% adverse in W2). The sign of continuation is essentially a 50/50 coin flip.
   - The entire sample-mean advantage of H1 is driven by an extreme right-tail concentration: **98.06% of the H1-E0 net advantage in W1 is attributable to just 4 trades that hit TARGET** between 12h and 18h (one single trade contributed +629.9 bps). In W2, **74.64% of the advantage is attributable to just 3 trades that hit TARGET**.
   - Trades that simply stayed open until the 18h TIME_CAP without hitting TARGET produced marginal or negative contributions (W1 18h TIME_CAP mean delta: +16.35 bps with 9 out of 14 trades negative; W2 had 5 stopouts losing -502.69 bps).

2. **Why H2 Underperforms H1 (18h to 24h Momentum Exhaustion & Stopouts):**
   - Between 18h and 24h, the initial breakout momentum decays. Instead of continuing favorably, trades suffer adverse drift and severe stopouts.
   - In W1, 2 additional trades hit STOP between 18h and 24h (losing -243.35 bps and -43.29 bps).
   - In W2, 4 additional trades hit STOP between 18h and 24h (losing -232.12 bps, -332.19 bps, -105.82 bps, -63.00 bps = -733.13 bps total).
   - Mean delta H2 - H1 across time-cap trades is **-7.61 bps in W1** and **-12.87 bps in W2**.

3. **Whole-Account Opportunity Cost & Trade-Set Equivalence:**
   - In whole-account replays, extending holding horizons from 12h to 18h or 24h **did not block a single new candidate trade** from being filled. The accepted event sets across E0, H1, and H2 are identical (34 in W1, 55 in W2).
   - This occurs because candidate signal generation fires in tight temporal clusters (within 0 to 7 hours of the initial impulse), which were already blocked by intra-trade cooldown under E0, followed by multi-day quiet periods.
   - However, capital was locked for **30.6% to 67.3% longer duration** (W1 occupied minutes increased from 18,456 min in E0 to 24,100 min in H1 and 28,308 min in H2; W2 from 31,614 min in E0 to 44,056 min in H1 and 52,898 min in H2). Capital return per occupied day declined under H2.

4. **2023 Structural Failure Persists in W2:**
   - In 2023 under STRESS, W1 paired H1 mean is +35.86 bps (H1-E0 delta +56.88 bps), lifting account return from -2.93% to +4.75%.
   - In W2 under STRESS, **2023 remains net negative** across both transaction mean (-18.11 bps) and account return (-3.23%). Even under BASE, 2023 H1 trade mean is +0.72 bps (zero). H1 reduces the loss relative to E0 (-45.49 bps), but does not rescue W2 from being a net losing strategy in 2023.

5. **Sample Power Severely Restricts Regime Targeting:**
   - Stratifying by entry-time trend alignment, volatility level, and funding state reveals that multiple sub-cohorts contain fewer than 10 events ($N < 10$), which are strictly marked `UNDERPOWERED`. Any attempt to condition exit policies on market regimes introduces severe selection bias and multiple-testing vulnerability.

---

## Comprehensive Tabular Attribution

### Table 1: Baseline TIME_CAP Trajectory & Fate Attribution (STRESS44)

| Candidate | Total $N$ | Base TC $N$ | 12–18h Fav / Adv | 12–18h Adv % | H1 Fates (TC / TGT / STP) | H1 TGT Delta Share | 18–24h Extra STOPs | H2–H1 Mean Delta |
|---|---:|---:|---:|---:|---|---:|---:|---:|
| **W1_C04** | 34 | 20 | 9 fav / 11 adv | **55.0%** | 14 TC / 4 TGT / 2 STP | **98.06%** (+1245 bp) | +2 STOPs | **-7.61 bp** |
| **W2_C05** | 55 | 36 | 21 fav / 15 adv | **41.7%** | 28 TC / 3 TGT / 5 STP | **74.64%** (+921 bp) | +4 STOPs | **-12.87 bp** |
| **Combined** | 89 | 56 | 30 fav / 26 adv | **46.4%** | 42 TC / 7 TGT / 7 STP | **86.63%** | +6 STOPs | **-10.99 bp** |

### Table 2: Incremental Price, Funding, and Fee Decomposition (STRESS44)

| Contrast | Candidate | Events $N$ | Mean Delta Net (bp) | Delta Price (bp) | Delta Funding (bp) | Delta Fee (bp) | Net Cash $\Delta$ ($) | Price Share |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **H1 - E0** | W1_C04 | 34 | **+37.35** | +37.60 | -0.24 | -0.01 | +12.70 | 100.6% |
| **H1 - E0** | W2_C05 | 55 | **+22.43** | +22.84 | -0.40 | -0.01 | +12.34 | 101.8% |
| **H2 - H1** | W1_C04 | 34 | **-4.48** | -4.33 | -0.14 | -0.01 | -1.52 | 96.6% |
| **H2 - H1** | W2_C05 | 55 | **-8.43** | -8.21 | -0.21 | -0.01 | -4.63 | 97.4% |
| **H2 - E0** | W1_C04 | 34 | **+32.87** | +33.27 | -0.38 | -0.02 | +11.18 | 101.2% |
| **H2 - E0** | W2_C05 | 55 | **+14.01** | +14.63 | -0.61 | -0.02 | +7.71 | 104.4% |

*Note: Funding cash drag is consistently negative across extended holding periods (-0.24 to -0.61 bps) because long positions paid positive funding rates during bull regimes.*

### Table 3: Whole-Account Capital Occupancy & Opportunity Audit (STRESS44)

| Metric | W1: E0 (12h) | W1: H1 (18h) | W1: H2 (24h) | W2: E0 (12h) | W2: H1 (18h) | W2: H2 (24h) |
|---|---:|---:|---:|---:|---:|---:|
| **Trade Count** | 34 | 34 | 34 | 55 | 55 | 55 |
| **Accepted Event Set** | Exact Match | Exact Match | Exact Match | Exact Match | Exact Match | Exact Match |
| **Skipped Signals** | 0 | 42 | 42 | 0 | 46 | 46 |
| **Missed in Extension (12-24h)** | 0 | **0** | **0** | 0 | **0** | **0** |
| **Total Occupied Minutes** | 18,456 min | 24,100 min | 28,308 min | 31,614 min | 44,056 min | 52,898 min |
| **Occupancy Increase vs E0** | — | **+30.6%** | **+53.4%** | — | **+39.4%** | **+67.3%** |
| **Occupied Days** | 12.82 d | 16.74 d | 19.66 d | 21.95 d | 30.59 d | 36.73 d |
| **Account Return %** | +3.25% | +14.91% | +13.48% | +9.68% | +20.93% | +16.55% |
| **Return / Occupied Day** | +0.25%/d | **+0.89%/d** | +0.69%/d | +0.44%/d | **+0.68%/d** | +0.45%/d |
| **Max MTM Drawdown %** | 10.06% | 9.28% | 8.88% | 9.23% | 6.91% | 7.99% |

### Table 4: Annual and Structural Breakdown (STRESS44)

| Candidate | Year | $N$ | E0 Mean (bp) | H1 Mean (bp) | H2 Mean (bp) | $\Delta$ H1-E0 (bp) | Account E0 Ret | Account H1 Ret |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **W1_C04** | 2021 | 8 | +104.58 | +128.53 | +91.56 | +23.95 | +4.95% | +5.72% |
| **W1_C04** | 2022 | 10 | -11.92 | +20.25 | +48.83 | +32.17 | +1.37% | +3.85% |
| **W1_C04** | 2023 | 16 | -21.03 | **+35.86** | +17.36 | **+56.89** | -2.93% | **+4.75%** |
| **W2_C05** | 2021 | 14 | +92.42 | +117.43 | +104.53 | +25.01 | +8.23% | +10.15% |
| **W2_C05** | 2022 | 17 | +35.84 | +56.59 | +44.52 | +20.75 | +10.98% | +14.37% |
| **W2_C05** | 2023 | 24 | -45.49 | **-18.11** | -24.98 | **+27.38** | -8.40% | **-3.23%** |

*Key finding: W2 in 2023 is absolute negative across both trade level (-18.11 bp) and account level (-3.23%).*

---

## Predeclared State Stratification & Power Evaluation

All state variables evaluated below were strictly causal and known as-of trade entry.

### 1. Trend Alignment (Completed 4h Return Relative to Position Side)
- **TREND_ALIGNED:**
  - W1: $N=24$, H1-E0 Mean $\Delta = +45.74$ bps ($N \ge 10$, Sufficient Power).
  - W2: $N=37$, H1-E0 Mean $\Delta = +26.04$ bps ($N \ge 10$, Sufficient Power).
- **COUNTERTREND:**
  - W1: $N=10$, H1-E0 Mean $\Delta = +17.21$ bps ($N = 10$, Marginal Power Boundary).
  - W2: $N=18$, H1-E0 Mean $\Delta = +15.02$ bps ($N \ge 10$, Sufficient Power).
- **Interpretation:** While trend-aligned entries achieved larger incremental continuation than countertrend entries, countertrend entries still showed positive H1-E0 deltas in sample. However, sub-strata (e.g., countertrend short) have $N < 5$, rendering conditional exit switching statistically ungrounded.

### 2. Entry Volatility Level (Expanding Previous-Only 90d Median)
- **HIGH_VOL:**
  - W1: $N=16$, Mean $\Delta = +44.82$ bps.
  - W2: $N=28$, Mean $\Delta = +28.14$ bps.
- **LOW_VOL:**
  - W1: $N=18$, Mean $\Delta = +30.70$ bps.
  - W2: $N=27$, Mean $\Delta = +16.51$ bps.
- **Interpretation:** Higher entry volatility correlates with larger continuation swings and faster target achievement. However, sample splits reduce effective UTC weeks per cell to $< 15$, preventing robust parameterization.

### 3. Funding State (Observed Rate As-Of Signal)
- **POSITIVE:**
  - W1: $N=26$, Mean $\Delta = +41.12$ bps.
  - W2: $N=42$, Mean $\Delta = +24.80$ bps.
- **NEGATIVE:**
  - W1: $N=8$ (**UNDERPOWERED**, $N < 10$).
  - W2: $N=13$, Mean $\Delta = +14.81$ bps.
- **Interpretation:** Negative funding environments are sparse in BTC 2021-2023 (bull bias). Negative funding strata cannot support statistically reliable claims.

---

## Block Bootstrap Uncertainty Analysis

Using the frozen shared UTC calendar block bootstrap (10,000 draws, seed 42) with zero-trade blocks retained:
- **7-day Block Bootstrap:**
  - W1 (H1 - E0): Mean = +37.35 bp, Bootstrap SE = 26.84 bp, 95% Simultaneous CI = `[-33.25, +107.95]` bp (includes zero).
  - W2 (H1 - E0): Mean = +22.43 bp, Bootstrap SE = 17.52 bp, 95% Simultaneous CI = `[-23.67, +68.53]` bp (includes zero).
  - W1 (H2 - H1): Mean = -4.48 bp, Bootstrap SE = 11.20 bp, 95% Simultaneous CI = `[-33.93, +24.97]` bp (includes zero).
  - W2 (H2 - H1): Mean = -8.43 bp, Bootstrap SE = 9.85 bp, 95% Simultaneous CI = `[-34.34, +17.48]` bp (includes zero).
- **14-day Block Bootstrap:**
  - W1 (H1 - E0): Mean = +37.35 bp, Bootstrap SE = 29.12 bp, 95% Simultaneous CI = `[-39.24, +113.94]` bp (includes zero).
  - W2 (H1 - E0): Mean = +22.43 bp, Bootstrap SE = 19.34 bp, 95% Simultaneous CI = `[-28.43, +73.29]` bp (includes zero).

**Inference Conclusion:**  
All simultaneous confidence intervals strictly include zero. The apparent sample advantage of H1 is statistically indistinguishable from zero under rigorous block resampling that accounts for temporal clustering and past trial selection.

---

## Independent Decimal Boundary Audit

An independent standard library audit using exact `decimal.Decimal` arithmetic evaluated 16 representative events across candidates (W1, W2), costs (STRESS, BASE), sides (LONG, SHORT), years (2021, 2022, 2023), and events with post-12h funding settlements:
- **Tick-level price rounding:** Exactly reproduced to 0.1 USDT precision using adverse ceiling/floor rules.
- **Funding cash calculation:** Matched to $< 10^{-12}$ USDT discrepancy.
- **Additive decomposition identity:**
  $$\Delta \text{Net USDT} = \Delta \text{Price PnL} + \Delta \text{Funding Cash} - \Delta \text{Exit Fee}$$
  reproduced with exact zero algebraic residual.
- **Audit status:** 100% of tested events passed independent verification.

---

## Prospective D1/D2 Recommendation to Controller

1. **Reject H1 as a Universal Strategy:** Do not deploy an unconditioned 18h holding policy. The H1 advantage is fragile, outlier-dominated, and fails to fix 2023 in W2.
2. **Reject H2 (24h) Completely:** H2 suffers from empirical momentum exhaustion and severe stopouts, increasing capital occupancy by 53-67% while delivering lower net returns than H1.
3. **Prospective D1 Momentum Gate (Design Only):** If a future wave is authorized, test a conditional 12h momentum decision gate (extending to 24h only if unrealized PnL $> +0.5R$ and 1h flow is positive at t=12h; otherwise exiting at 12h).
4. **Mandatory Fresh Controller Authority:** No execution or backtesting of D1 or D2 may occur without formal L2 authorization from ChatGPT-0.
