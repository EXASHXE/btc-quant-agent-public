# Goal B R2 Frozen As-Of Causal Feature Repair Method & Protocol

**Task ID:** `g2_goal_b_asof_repair_r2`  
**Controller Authority:** [V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md](https://github.com/EXASHXE/btc-quant-agent-public/blob/1172d3a91324c1a7379bc9e5c24ef601076547c2/reviews/v0.6/b_line/V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md)  
**Controller Dispatch SHA:** `1172d3a91324c1a7379bc9e5c24ef601076547c2`  
**Exact Start SHA:** `397a62c1a0fbd6ad14a569a5be0058b1f684f08e`  
**Shared Base SHA:** `55ac4c631c69f6edbd275462ad23e4486b9782ed`  
**Branch:** `feature/v06-bline-gemini-goal-b-asof-repair-r2`  
**Worktree:** `/root/workspace/project/quant-v0.6/gemini-goal-b-asof-repair-r2`  

---

## 1. Executive Summary & Bound on Scope

This protocol establishes the immutable methodology for **GEMINI GOAL B R2**, designed to repair the as-of-entry causal feature extraction, audit original mechanism findings, and reconcile discrepancies identified in Goal B R1.

### Strict Boundaries & Constraints
- **Observational Retrospective Diagnostic Only:** This work package produces an observational addendum to the development-only Exit R1 evidence. It does **not** search for new trading signals, does **not** tune new exit rules, and does **not** propose conditional regime-switching policies.
- **Zero New Strategy Searches:** No parameters, thresholds, or interpolation (15h/16h/20h/22h) are permitted.
- **Protected Space Boundary:** Zero access or references to `/root/workspace/project/Quant-agent/data`, `Quant-agent-sanitized`, 2024–2026 data, A-line, H39/H40/H41/Forward, private credentials, or live exchange endpoints.
- **Two Planned Commits:**
  - Commit 1: Freeze method, contracts, verification receipts, and deterministic synthetic test suite.
  - Commit 2: Reconstructed causal attribution, reconciliation matrix, evidence artifacts, and empirical report.

---

## 2. Formal Revocation of Goal B R1 Leaked Claims

Goal B R1 suffered from three critical feature implementation defects in its `run.py` script and several reporting discrepancies. We formally record the following revocations:

1. **R1 Trend Alignment Leakage (REVOKED):**  
   In R1 `run.py` (lines 136–142), trend alignment was computed using `path24h.before12h.Last_MFE_R` versus `Last_MAE_R`. This metric was derived from the $[T_{entry}, T_{entry} + 12\text{h})$ in-trade sample path, directly leaking future post-entry price movement. **All R1 claims asserting predictive trend regimes are WITHDRAWN.**
2. **R1 Volatility Regime Substitution (REVOKED):**  
   In R1 `run.py` (lines 145–146), volatility was categorized via `risk_bps > 300` (initial trade stop distance) rather than the preregistered expanding prior-only 90d completed 1h ATR(14)/price percentile. **All R1 claims asserting volatility-driven advantages are WITHDRAWN.**
3. **R1 Funding Regime Leakage (REVOKED):**  
   In R1 `run.py` (lines 149–154), the funding state was read from `e0['funding_settlements'][0]`. This settlement occurs strictly **after** trade entry during the holding period. **All R1 claims asserting funding-rate predictive regimes are WITHDRAWN.**
4. **W2 Annual Count Discrepancy (RECONCILED):**  
   R1 report Table 4 stated W2 counts as `2021: 14, 2022: 17, 2023: 24`. Verified machine ledgers in Exit R1 record `2021: 10, 2022: 21, 2023: 24` (total 55). The machine truth is strictly preserved.
5. **Account Skipped Signals Discrepancy (RECONCILED):**  
   R1 report Table 3 recorded 0 skipped signals for E0, masking that the E0 account simulation blocked candidate signals arriving during its 12h hold. Crucially, **zero** candidate signals were missed during the extended (12h to 24h) holding window.

---

## 3. Verified Read-Only Inputs & Cryptographic Hashes

All analyses consume public, read-only archives with immutable SHA256 digests:

### 3.1 Exit R1 Paired Ledgers (`evidence/v0.6/b_line/g2_exit_horizon_r1/`)
| File | SHA256 | Events | Candidate | Cost |
|---|---|---:|---|---|
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_BASE_paired.jsonl` | `acda3f0996931b551750e41eebc5a124127e1dac84821197264f76a3e63b00a5` | 34 | W1_C04 | BASE22 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_STRESS_paired.jsonl` | `f8d10f8a8e7d16046c2d207bf12250d63f3cc1c1ec0b3d26a692c4317f8d2d8a` | 34 | W1_C04 | STRESS44 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_BASE_paired.jsonl` | `4e417da29f07c85884199647c284031ca4c84801b48b0170bfd8f9f5e06be4b2` | 55 | W2_C05 | BASE22 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_STRESS_paired.jsonl` | `c27a8dabafd4b8e9949aa94fe76f524104481395294e812ca630a73c28db7847` | 55 | W2_C05 | STRESS44 |

### 3.2 Public Read-Only Binance Archives (`/tmp/btc-two-lead-funding-mark-r3`)
- `last-BTCUSDT-1m-2021-01.zip` through `2023-12.zip` (36 monthly archives of 1m Last bars)
- `funding-BTCUSDT-fundingRate-2021-01.zip` through `2023-12.zip` (36 monthly archives of 8h official funding settlements)
- Verified contiguous 1m bars with zero missing timestamps across 2021–2023.

---

## 4. Time-Causal As-Of Feature Mathematical Specification

All features are evaluated strictly as-of the signal decision timestamp $T_{sig} = T_{entry} - 60,000\text{ ms}$.

### 4.1 PRE_ENTRY_TREND_ALIGNED
- **Inputs:** Completed 1m LAST bars whose close timestamp $T_{close} \le T_{sig}$.
- **Window:** Exactly the last 240 contiguous 1m bars (spanning $4\text{ hours}$).
- **Continuity Verification:** $\forall i \in [1, 239], \quad T_{open, i} - T_{open, i-1} = 60,000\text{ ms}$. If broken or $< 240$ bars, status is `INCOMPLETE`.
- **Computation:**
  $$R_{4h} = \frac{P_{close, 239} - P_{open, 0}}{P_{open, 0}}$$
  $$\text{Alignment} = \text{side} \times R_{4h}$$
- **Label Assignment:**
  - $\text{Alignment} > 10^{-7} \implies \text{TREND\_ALIGNED}$
  - $\text{Alignment} < -10^{-7} \implies \text{COUNTERTREND}$
  - $|\text{Alignment}| \le 10^{-7} \implies \text{NEUTRAL}$

### 4.2 PRE_ENTRY_ATR_REGIME
- **Resampling:** Contiguous 1m bars resampled into 1-hour OHLC bars strictly aligned to UTC hour boundaries ($HH:00:00$ to $HH:59:59.999$). Each hour requires 60 complete minutes.
- **True Range:**
  $$TR_0 = High_0 - Low_0$$
  $$TR_t = \max(High_t - Low_t, |High_t - Close_{t-1}|, |Low_t - Close_{t-1}|), \quad t \ge 1$$
- **Wilder Smoothing (Period = 14):**
  $$ATR_{13} = \frac{1}{14} \sum_{j=0}^{13} TR_j$$
  $$ATR_t = \frac{13 \times ATR_{t-1} + TR_t}{14}, \quad t \ge 14$$
- **Normalization:** $\text{NormATR}_t = ATR_t / Close_t$.
- **Prior-Only Lookback Window:** Exactly 2,160 completed hourly bars (90 days) ending at the latest completed hour $L$ ($T_{close, L} \le T_{sig}$).
- **Power & Incompleteness Guard:** If $< 2,160$ completed hours exist prior to $T_{sig}$, returns `INCOMPLETE_LOOKBACK`. Never auto-substitutes low volatility.
- **Label Assignment:**
  $$\text{Median}_{90d} = \text{median}(\text{NormATR}_{L-2159 \dots L})$$
  - $\text{NormATR}_L \ge \text{Median}_{90d} \implies \text{HIGH\_VOL}$
  - $\text{NormATR}_L < \text{Median}_{90d} \implies \text{LOW\_VOL}$

### 4.3 PRE_ENTRY_FUNDING_STATE
- **Inputs:** Official exchange funding settlements.
- **Causality Criterion:** Settlement calculation timestamp $T_{calc} < T_{sig} - \text{lag}$.
- **Label Assignment:**
  - $\text{Rate} > 10^{-7} \implies \text{POSITIVE}$
  - $\text{Rate} < -10^{-7} \implies \text{NEGATIVE}$
  - $|\text{Rate}| \le 10^{-7} \implies \text{ZERO}$
  - If no settlement exists prior to signal clock $\implies \text{UNKNOWN}$.

---

## 5. Verification, Guard Rails, and Power Gating

1. **Time-Travel Mutation Invariance:**  
   Automated unit tests deliberately mutate, scale (10x), and inject extreme fake values into bars and funding settlements occurring after $T_{sig}$. Tests verify that feature outputs are 100% byte-for-byte identical.
2. **Power Gate Threshold:**  
   Minimum sample count $N \ge 10$ per stratum. Any cell with $N < 10$ is explicitly flagged as `UNDERPOWERED`.
3. **Exploratory Uncertainty:**  
   Original 7d/14d block bootstrap confidence intervals are reported as post-selection exploratory measures. All intervals span zero.
