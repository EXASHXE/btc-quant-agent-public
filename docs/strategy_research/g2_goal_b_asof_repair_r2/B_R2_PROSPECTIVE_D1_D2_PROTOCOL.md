# Prospective D1/D2 Experimental Evaluation Protocol (Non-Executed)

**Task ID:** `g2_goal_b_asof_repair_r2`  
**Controller Authority:** [V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/1172d3a91324c1a7379bc9e5c24ef601076547c2/reviews/v0.6/b_line/V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md)  
**Controller Dispatch SHA:** `1172d3a91324c1a7379bc9e5c24ef601076547c2`  
**Parent Commit SHA:** `397a62c1a0fbd6ad14a569a5be0058b1f684f08e`  
**Status:** PROSPECTIVE PROTOCOL ONLY — ZERO EXECUTION ON HOLDOUT DATA  

---

## 1. Executive Purpose & Non-Execution Attestation

This document formalizes the prospective experimental protocol for future evaluation of exit horizons (E0: 12h, H1: 18h, H2: 24h) on strictly independent, unexposed data partitions (D1/D2).

> [!IMPORTANT]
> **Strict Non-Execution Attestation:**  
> This protocol is strictly prospective. Zero code in this workspace accesses, processes, or evaluates D1/D2 partitions, 2024–2026 data, or any protected holdout datasets. Evaluating this protocol requires independent controller authorization and a separate dispatch.

---

## 2. Experimental Design & Predeclared Hypotheses

### 2.1 Fixed Candidate & Horizon Arms
- **Candidate Strategies:**
  1. `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H`
  2. `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H`
- **Horizon Arms:**
  - **E0 (Baseline):** Max holding period = 12 hours (720 minutes).
  - **H1 (Treatment 1):** Max holding period = 18 hours (1,080 minutes).
  - **H2 (Treatment 2):** Max holding period = 24 hours (1,440 minutes).
- **Zero Interpolation:** Testing of intermediate horizons (e.g., 14h, 15h, 16h, 20h, 22h) is strictly prohibited to prevent p-hacking.
- **Zero Conditional Switching:** Horizon rules must be applied unconditionally across all events in a given arm. Reconstructed as-of regimes must not be used as conditional entry or exit triggers.

### 2.2 Formal Null Hypotheses
1. $H_{0, 1}$: $\mathbb{E}[\Delta_{\text{net}}(\text{H1} - \text{E0})] \le 0$ under STRESS44 friction.
2. $H_{0, 2}$: $\mathbb{E}[\Delta_{\text{net}}(\text{H2} - \text{H1})] \ge 0$ under STRESS44 friction (testing momentum decay).
3. $H_{0, 3}$: $\text{Occupancy-Adjusted Return}(\text{H1}) \le \text{Occupancy-Adjusted Return}(\text{E0})$.

---

## 3. Power Analysis & Minimum Sample Size

### 3.1 Sample Size Constraints on Development Set
In development data (2021–2023), sample sizes were severely limited:
- W1: $N = 34$ total trades (20 time-capped, 14 early exits).
- W2: $N = 55$ total trades (36 time-capped, 19 early exits).
Several annual, side, and funding regime cells had $N < 10$, rendering them statistically underpowered.

### 3.2 Prospective Power Requirement
- **Target Effect Size:** $\delta = +30.0\text{ bps}$ net difference (H1 minus E0).
- **Standard Deviation:** $\sigma \approx 130.0\text{ bps}$ (observed historical contrast standard deviation).
- **Significance Level:** Two-sided $\alpha = 0.05$ with familywise error rate control across the 6 primary contrasts.
- **Statistical Power:** $1 - \beta = 0.80$.
- **Required Sample Size:**
  $$N \ge \frac{2 \times (z_{\alpha/2} + z_{\beta})^2 \times \sigma^2}{\delta^2} \approx 295 \text{ matched paired events per candidate.}$$
- **Minimum Threshold:** At least $N \ge 150$ completed trades per candidate arm are mandatory before any statistical claim of horizon superiority can be made.

---

## 4. Execution Friction & Timing Rules

### 4.1 Cost Model Vectors
- **BASE22:**
  - Fee: 12.0 bps round-trip (6.0 bps per leg)
  - Spread: 4.0 bps round-trip (2.0 bps per leg)
  - Slippage: 6.0 bps round-trip (3.0 bps per leg)
  - **Total Friction:** 22.0 bps.
- **STRESS44:**
  - Fee: 24.0 bps round-trip (12.0 bps per leg)
  - Spread: 8.0 bps round-trip (4.0 bps per leg)
  - Slippage: 12.0 bps round-trip (6.0 bps per leg)
  - **Total Friction:** 44.0 bps.

### 4.2 Clocks and Latency Sensitivity
- **Signal Decision Clock:** Evaluated at $T_{sig} = T_{entry} - 60,000\text{ ms}$.
- **Execution Fill Clock:** Limit/market proxy fill recorded at $T_{entry}$.
- **Exit ACK Delay Sensitivity:** Mandates testing of a 1-bar (60s) execution ACK delay sensitivity on time-capped exits.
- **Funding Settlements:** Exact signed funding settlements recorded at official exchange timestamps (00:00, 08:00, 16:00 UTC) applied to open position quantity as-of settlement time.

---

## 5. Statistical Inference Protocol

1. **Simultaneous Contrast Testing:**  
   Joint evaluation of the 6 primary contrasts (W1 H1-E0, W1 H2-E0, W1 H2-H1, W2 H1-E0, W2 H2-E0, W2 H2-H1) using a shared studentized block bootstrap with max-$|T|$ critical values.
2. **Block Resampling Structure:**  
   Circular block bootstrap with 7-day and 14-day calendar blocks. Zero-trade calendar blocks must be retained to preserve temporal clustering and opportunity cost structure.
3. **Falsification Gates:**
   - **Gate 1 (Continuation Decay):** If the fraction of adverse price drift in the (12h, 18h] window exceeds 50%, H1 extension is falsified.
   - **Gate 2 (H2 Stopout Acceleration):** If H2 triggers more stopouts than H1 while failing to achieve targets, H2 is falsified.
   - **Gate 3 (Opportunity Cost Penalty):** If whole-account replay reveals missed signals in the extension window that reduce portfolio return below E0, H1 is rejected.
