# Goal B R2 Corrected Empirical Mechanism Report: As-Of Causal Feature Repair, Discrepancy Reconciliation, and Exit Horizon Economics

**Task ID:** `g2_goal_b_asof_repair_r2`  
**Controller Authority:** [V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/1172d3a91324c1a7379bc9e5c24ef601076547c2/reviews/v0.6/b_line/V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md)  
**Controller Dispatch SHA:** `1172d3a91324c1a7379bc9e5c24ef601076547c2`  
**Parent Commit SHA:** `397a62c1a0fbd6ad14a569a5be0058b1f684f08e`  
**Shared Base SHA:** `55ac4c631c69f6edbd275462ad23e4486b9782ed`  
**Branch:** `feature/v06-bline-gemini-goal-b-asof-repair-r2`  
**Terminal State:** `B_R2_ASOF_LABELS_CAUSALLY_RECONSTRUCTED_DEVELOPMENT_ONLY`  

---

## 1. Executive Summary & Terminal Findings

This report delivers the definitive, time-causal empirical mechanism evaluation for **GEMINI GOAL B R2**, reconciling all defects, feature leakages, and reporting discrepancies present in Goal B R1.

### Core Scientific Findings:
1. **Goal B R1 Feature Claims Formally Revoked:**  
   Goal B R1's claims of predictive trend, volatility, and funding regimes were mathematically invalid due to three implementation defects in its `run.py`:
   - Trend was computed from the post-entry $[T_{\text{entry}}, T_{\text{entry}} + 12\text{h})$ in-trade MFE/MAE (future price leakage).
   - Volatility was binned using trade initial risk `risk_bps > 300` rather than the predeclared 90d hourly ATR distribution.
   - Funding regime was read from the first post-entry funding settlement in the trade.  
   **All R1 claims asserting predictive regime advantages are formally WITHDRAWN.**
2. **Reconstructed As-Of Features Disclose Strategy Nature:**  
   When evaluated strictly as-of the signal decision timestamp ($T_{\text{sig}} = T_{\text{entry}} - 60\text{s}$):
   - **Pre-Entry 4h Trend:** **100% of candidate trades are TREND_ALIGNED** (34/34 in W1, 55/55 in W2). The candidate strategies (`ATR_EXPANSION_TREND_FOLLOW` and `ASYMMETRIC_VOLATILITY_BREAKOUT`) inherently require momentum alignment at entry. R1's alleged "countertrend" trades were an illusion caused by classifying trades that suffered in-trade drawdown.
   - **Volatility Regime (90d Hourly ATR Median Split):** W1 splits into 20 High / 14 Low; W2 splits into 27 High / 28 Low (both well-supported).
   - **Funding Regime (Prior Settled Rate):** Predominantly positive (27/7 in W1, 45/10 in W2), reflecting BTC bull/consolidation regimes. In W1, negative funding has only $N=7$ events ($< 10$), which is **UNDERPOWERED**.
3. **Mechanistic Attribution of H1 (18h) vs E0 (12h): Outlier Concentration:**  
   Of the fixed development events, 20/34 (W1) and 36/55 (W2) hit the 12h time cap. Extending the cap to 18h allowed 4 trades in W1 and 3 trades in W2 to reach full profit targets (+311.3 bp and +306.9 bp average deltas). These 7 target completions account for **>85% of the aggregate net advantage** of H1.
4. **Mechanistic Decay of H2 (24h) vs H1 (18h): Momentum Stall & Stop Accumulation:**  
   Between 18h and 24h, trades suffered momentum exhaustion and adverse drift (mean delta **-7.61 bp** in W1, **-12.87 bp** in W2). Additional stopouts occurred (2 in W1, 4 in W2) while zero additional target hits were achieved.
5. **Opportunity Cost & Capital Occupancy:**  
   Independent whole-account replays prove that **zero** candidate signals were missed during the extended holding window (12h to 24h) across 2021–2023. Signal bursts arrive within 0–7h of entry followed by multi-day quiet periods. Capital occupancy increased by +30.6% (W1) and +35.1% (W2).
6. **Inconclusive Statistical Significance & Post-Selection Caution:**  
   Simultaneous 95% block bootstrap confidence intervals across all primary contrasts **all span zero** (W1 14d H1-E0: $[-22.20, +96.89]\text{ bp}$; W2 14d H1-E0: $[-17.33, +62.20]\text{ bp}$). Because H1 was selected post-hoc following 48+8 prior research trials, and 2021 W2 performance was flat/negative under STRESS (-0.26 bp), **H1 is an observational artifact of development data, NOT a proven optimal holding period.**

---

## 2. Claim-Revocation and Discrepancy Reconciliation Matrix

| Category | Defect in Goal B R1 | Ground Truth / R2 Repair | Status |
|---|---|---|---|
| **Trend Feature** | `run.py` lines 136–142 binned trend via post-entry $[0, 12\text{h})$ MFE vs MAE | `asof_features.py` extracts strictly prior 240 1m LAST bars ending $\le T_{\text{sig}}$ | **REVOKED (R1 Claims Withdrawn)** |
| **Volatility Feature** | `run.py` lines 145–146 binned volatility via `risk_bps > 300` | `asof_features.py` computes Wilder ATR(14) on 2,160 prior 1h bars vs rolling median | **REVOKED (R1 Claims Withdrawn)** |
| **Funding Feature** | `run.py` lines 149–154 read `e0['funding_settlements'][0]` (post-entry in-trade settlement) | `asof_features.py` extracts official settlement calculated strictly before $T_{\text{sig}}$ | **REVOKED (R1 Claims Withdrawn)** |
| **W2 Annual Counts** | Human report Table 4 reported W2 as `2021: 14, 2022: 17, 2023: 24` | Primary Exit R1 machine ledgers verify `2021: 10, 2022: 21, 2023: 24` (sum 55) | **RECONCILED (Machine Truth Restored)** |
| **Skipped Signals** | Human report Table 3 stated 0 skipped signals for E0 | E0 account simulation blocked 42 (W1) and 46 (W2) signals during initial hold/cooldown | **RECONCILED (Full Visibility Restored)** |
| **Cost Vectors** | Intermediate Commit 1 set slippage to 16/8 bp | Frozen BASE22 (12/4/6 bp) and STRESS44 (24/8/12 bp) strictly verified | **VERIFIED & IMMUTABLE** |

---

## 3. Repaired Time-Causal As-Of Stratification (STRESS44)

All analyses are evaluated on frozen development events (W1 $N=34$, W2 $N=55$) under STRESS44 friction (24 bp fee + 8 bp spread + 12 bp slippage = 44 bp round-trip).

### 3.1 Candidate W1_C04 (`ATR_EXPANSION_TREND_FOLLOW_12H`)

| Stratum Dimension | Label | Event Count ($N$) | Power Status | Mean $\Delta$ (H1-E0) | Median $\Delta$ | Favorable | Adverse | Flat ($< 12\text{h}$) |
|---|---|---:|---|---:|---:|---:|---:|---:|
| **Calendar Year** | 2021 | 8 | **UNDERPOWERED** | +2.94 bp | 0.00 bp | 1 | 3 | 4 |
| | 2022 | 10 | SUFFICIENT | +33.61 bp | 0.00 bp | 2 | 4 | 4 |
| | 2023 | 16 | SUFFICIENT | +56.88 bp | 0.00 bp | 6 | 4 | 6 |
| **Trade Side** | LONG | 19 | SUFFICIENT | +60.64 bp | 0.00 bp | 6 | 7 | 6 |
| | SHORT | 15 | SUFFICIENT | +7.84 bp | 0.00 bp | 3 | 4 | 8 |
| **4h Trend Alignment** | TREND_ALIGNED | 34 | SUFFICIENT | +37.35 bp | 0.00 bp | 9 | 11 | 14 |
| | COUNTERTREND | 0 | ZERO_SUPPORT | — | — | — | — | — |
| **90d Hourly ATR** | HIGH_VOL | 20 | SUFFICIENT | +54.16 bp | 0.00 bp | 7 | 7 | 6 |
| | LOW_VOL | 14 | SUFFICIENT | +13.32 bp | 0.00 bp | 2 | 4 | 8 |
| **Prior Settled Funding** | POSITIVE | 27 | SUFFICIENT | +52.06 bp | 0.00 bp | 7 | 9 | 11 |
| | NEGATIVE | 7 | **UNDERPOWERED** | -19.41 bp | 0.00 bp | 2 | 2 | 3 |

### 3.2 Candidate W2_C05 (`ASYMMETRIC_VOLATILITY_BREAKOUT_12H`)

| Stratum Dimension | Label | Event Count ($N$) | Power Status | Mean $\Delta$ (H1-E0) | Median $\Delta$ | Favorable | Adverse | Flat ($< 12\text{h}$) |
|---|---|---:|---|---:|---:|---:|---:|---:|
| **Calendar Year** | 2021 | 10 | SUFFICIENT | -0.26 bp | 0.00 bp | 4 | 4 | 2 |
| | 2022 | 21 | SUFFICIENT | +27.58 bp | 0.00 bp | 10 | 7 | 4 |
| | 2023 | 24 | SUFFICIENT | +27.39 bp | 0.00 bp | 7 | 4 | 13 |
| **Trade Side** | LONG | 29 | SUFFICIENT | +29.12 bp | 0.00 bp | 11 | 7 | 11 |
| | SHORT | 26 | SUFFICIENT | +14.97 bp | 0.00 bp | 10 | 8 | 8 |
| **4h Trend Alignment** | TREND_ALIGNED | 55 | SUFFICIENT | +22.43 bp | 0.00 bp | 21 | 15 | 19 |
| | COUNTERTREND | 0 | ZERO_SUPPORT | — | — | — | — | — |
| **90d Hourly ATR** | HIGH_VOL | 27 | SUFFICIENT | +48.14 bp | +13.00 bp | 15 | 7 | 5 |
| | LOW_VOL | 28 | SUFFICIENT | -2.35 bp | 0.00 bp | 6 | 8 | 14 |
| **Prior Settled Funding** | POSITIVE | 45 | SUFFICIENT | +9.75 bp | 0.00 bp | 14 | 13 | 18 |
| | NEGATIVE | 10 | SUFFICIENT | +79.50 bp | +22.34 bp | 7 | 2 | 1 |

---

## 4. Mechanistic Decomposition: The 12–18h and 18–24h Pathways

### 4.1 Cohort Partitioning
- **Early Exit Stratum (Exited $< 12\text{h}$):**
  - W1: 14 / 34 events (41.2%) exited before 12h via Stop or Target.
  - W2: 19 / 55 events (34.5%) exited before 12h.
  - **Integrity Proof:** Across all early exits, E0, H1, and H2 are 100% byte-identical. Extending the time cap has zero impact on trades that already reached boundary conditions.
- **Time-Cap Censored Stratum (Active at $12\text{h}$):**
  - W1: 20 / 34 events (58.8%) reached the 12h time cap.
  - W2: 36 / 55 events (65.5%) reached the 12h time cap.

### 4.2 Pathway Fate Breakdown: The Outlier Target Concentration
When the holding window is extended from 12h to 18h (H1) and 24h (H2):

```
W1_C04 TIME_CAP Cohort (N = 20):
  12h -> 18h (H1):
    ├── TARGET Hit (N = 4): Mean Delta = +311.29 bp | Sum Delta = +1,245.16 bp (98.1% of total net gain)
    ├── Still TIME_CAP (N = 14): Mean Delta = +16.35 bp | Sum Delta = +228.89 bp (18.0% of total net gain)
    └── STOP Hit (N = 2): Mean Delta = -102.15 bp | Sum Delta = -204.31 bp (-16.1% drag)
  18h -> 24h (H2):
    ├── Momentum Decays: Mean Delta = -7.61 bp | Adverse Reversals = 9, Favorable = 5
    └── Extra Stopouts: 2 additional positions stopped out between 18h and 24h

W2_C05 TIME_CAP Cohort (N = 36):
  12h -> 18h (H1):
    ├── TARGET Hit (N = 3): Mean Delta = +306.97 bp | Sum Delta = +920.92 bp (74.6% of total net gain)
    ├── Still TIME_CAP (N = 28): Mean Delta = +29.13 bp | Sum Delta = +815.65 bp (66.1% of total net gain)
    └── STOP Hit (N = 5): Mean Delta = -100.54 bp | Sum Delta = -502.69 bp (-40.7% drag)
  18h -> 24h (H2):
    ├── Momentum Decays: Mean Delta = -12.87 bp | Adverse Reversals = 18, Favorable = 10
    └── Extra Stopouts: 4 additional positions stopped out between 18h and 24h
```

> [!IMPORTANT]
> **Scientific Explanation of H1 Advantage:**  
> The apparent historical advantage of H1 over E0 is heavily driven by **right-tail outlier concentration**. Across both strategies, 7 trades reached full profit targets during the 12h–18h window, contributing **+2,166.08 bp** of net profit (>85% of total gains). Conversely, extending from 18h to 24h fails to produce additional targets while accelerating adverse mean-reversion stopouts.

---

## 5. Whole-Account Capital Occupancy & Opportunity Cost Audit

| Metric | W1: E0 (12h) | W1: H1 (18h) | W1: H2 (24h) | W2: E0 (12h) | W2: H1 (18h) | W2: H2 (24h) |
|---|---:|---:|---:|---:|---:|---:|
| **Executed Trades** | 34 | 34 | 34 | 55 | 55 | 55 |
| **Accepted Event Set** | Exact Match | Exact Match | Exact Match | Exact Match | Exact Match | Exact Match |
| **Skipped Signals (Total Blocked)** | 42 | 42 | 42 | 46 | 46 | 46 |
| **Blocked during (12h, 24h] Hold** | **0** | **0** | **0** | **0** | **0** | **0** |
| **Total Occupied Minutes** | 18,456 min | 24,100 min | 28,308 min | 32,607 min | 44,056 min | 52,898 min |
| **Occupancy Increase vs E0** | — | **+30.6%** | **+53.4%** | — | **+35.1%** | **+62.2%** |
| **Total Occupied Days** | 12.82 d | 16.74 d | 19.66 d | 22.64 d | 30.59 d | 36.73 d |
| **Account Return % (STRESS44)** | +3.25% | +14.91% | +13.48% | +9.68% | +20.93% | +16.55% |
| **Return / Occupied Day** | +0.25%/d | **+0.89%/d** | +0.69%/d | +0.43%/d | **+0.68%/d** | +0.45%/d |
| **Max MTM Drawdown %** | 10.06% | 9.28% | 8.88% | 9.23% | 6.91% | 7.99% |

### Key Economic Takeaways:
- **Zero Opportunity Cost in Extended Windows:** Due to the episodic, clustered nature of BTC breakout signals (bursts arrive within 0–7h of each other), extending the holding duration from 12h to 18h or 24h caused **zero missed signals** between 12h and 24h.
- **Occupancy Efficiency:** Under development-set realizations, H1 delivered higher return per occupied day (+0.89%/d vs +0.25%/d in W1; +0.68%/d vs +0.43%/d in W2).

---

## 6. Block Bootstrap Uncertainty & Non-Generalizability Warning

To evaluate whether the observed point estimates can be promoted to proven trading policies, we evaluate studentized circular block bootstrap confidence intervals with simultaneous max-$|T|$ critical thresholds:

### 14-Day Calendar Block Bootstrap (STRESS44, 10,000 Draws, Seed=42)
- **Critical Max-$|T|$ (95% Simultaneous):** $2.6327$

| Contrast | Qualified $N$ | Point Estimate | Bootstrap SE | Simultaneous 95% CI | Spans Zero? | Status |
|---|---:|---:|---:|---|:---:|---|
| **W1: H1 - E0** | 34 | +37.35 bp | 22.62 bp | **[-22.20, +96.89] bp** | **YES** | Statistically Inconclusive |
| **W1: H2 - E0** | 34 | +32.87 bp | 30.28 bp | **[-46.86, +112.60] bp** | **YES** | Statistically Inconclusive |
| **W1: H2 - H1** | 34 | -4.48 bp | 21.11 bp | **[-60.05, +51.09] bp** | **YES** | Statistically Inconclusive |
| **W2: H1 - E0** | 55 | +22.43 bp | 15.10 bp | **[-17.33, +62.20] bp** | **YES** | Statistically Inconclusive |
| **W2: H2 - E0** | 55 | +14.01 bp | 18.31 bp | **[-34.21, +62.22] bp** | **YES** | Statistically Inconclusive |
| **W2: H2 - H1** | 55 | -8.43 bp | 18.41 bp | **[-56.89, +40.04] bp** | **YES** | Statistically Inconclusive |

> [!WARNING]
> **Definitive Scientific Judgment:**  
> 1. All simultaneous 95% confidence intervals span zero under both 7d and 14d block resamplings.
> 2. Candidate H1 was identified post-hoc after inspecting the historical development performance across 48+8 previous research trials.
> 3. Annual stability is absent: W2 in 2021 was flat/negative (-0.26 bp), and W1 in 2021 had only 8 trades.
> 4. Therefore, **H1 cannot and must not be promoted to a proven optimal holding period.** It remains an observational development artifact. Zero live policies or conditional rules are authorized.

---

## 7. Deliverable File Receipts and SHA256 Manifest

All artifacts are persisted under `evidence/v0.6/b_line/g2_goal_b_asof_repair_r2/`:
- `B_R2_ASOF_EVENT_ATTRIBUTION.json`: Per-event time-causal features and horizon deltas for all 89 events.
- `B_R2_RECONCILIATION_MATRIX.json`: Formal claim revocations and machine-to-human reconciliation.
- `B_R2_CORRECTED_REGIME_STRATIFICATION.json`: Predeclared one-axis stratifications and block bootstrap results.
- `B_R2_TIME_CAP_PATHWAY_DECOMPOSITION.json`: Detailed 12–18h and 18–24h pathway transitions and whole-account metrics.
- `B_R2_DECIMAL_BOUNDARY_AUDIT.json`: Stdlib Decimal 28-digit precision audit receipts.
- `B_R2_SCIENCE_EXECUTION_RECEIPT.json`: Machine execution receipt and terminal state attestations.
- `B_R2_DELIVERY_MANIFEST.json`: Cryptographic manifest with SHA256 of all delivered files.
