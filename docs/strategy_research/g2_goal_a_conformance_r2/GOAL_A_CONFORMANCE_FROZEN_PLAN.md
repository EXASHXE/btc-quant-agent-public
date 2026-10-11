# Goal A R2 — Conformance and Reconciliation Frozen Research Plan

## 1. Executive Authority and Mandate

- **Controller Authority:** `1172d3a91324c1a7379bc9e5c24ef601076547c2`
- **Authority Document:** `reviews/v0.6/b_line/V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md`
- **Repository:** `EXASHXE/btc-quant-agent-public`
- **Branch:** `feature/v06-bline-gemini-goal-a-conformance-r2`
- **Start Commit SHA:** `efa0b302233800f6474b3dda5775be56a77d0860`
- **Parent Frozen R1 SHA:** `83c0ef60d9eacfd2440fa223c57f042cfff4912f`
- **Final Delivered R1 SHA:** `efa0b302233800f6474b3dda5775be56a77d0860`
- **Prefix:** `g2_goal_a_conformance_r2`
- **Isolated Worktree:** `/root/workspace/project/quant-v0.6/gemini-goal-a-conformance-r2`
- **Isolated Scratch:** `/tmp/btc-gemini-goal-a-conformance-r2`

## 2. Scientific Problem and Research Questions

During Goal A R1, four new causal entry signal families (8 configurations: C01–C04 across 12h and 18h horizons) were developed. In the frozen commit `83c0ef60`, the execution engine loaded continuous multi-year concatenated arrays (`full_last`, `full_mark`, `all_rates`). In the final delivery commit `efa0b302`, `run.py` was adapted to stream month-by-month using a previous-month + current-month window (`np.vstack([prev_last, curr_last])`), and paired counterfactual controls were recorded.

This Goal A R2 conformance research resolves three core scientific questions:

1. **Replay Engine Equivalence:** Does the streaming monthly-window implementation in `efa0b302` yield identical signals, fills, funding cash flows, and account trajectories to the frozen concatenated implementation `83c0ef60` across all 8 candidates and 35 folds?
2. **Etiology of 2023 Zero-Trade Exposure:** Was the lack of executed trades in 2023 for `C01_MACRO_PULLBACK_RECLAIM_12H` caused by market signal absence or capital exhaustion under the 1x budget cap and exchange lot constraints?
3. **Publication Discrepancy Reconciliation:** What explains the discrepancies between the machine JSON outputs (`GOAL_A_RUN_STRESS.json`) and the human report (`GOAL_A_FINAL_RESEARCH_REPORT.md`), such as annual trade distributions (619/499 vs 569/549 for C01 12h; 5/6/9 vs 4/7/9 for C03 12h) and P&L figures?

## 3. Dual-Engine Structural Specification

A new sidecar differential harness (`scripts/strategy_research/g2_goal_a_conformance_r2/differential_harness.py`) is implemented to run both engines side-by-side without modifying legacy code:

- **Engine 1 (Frozen 83c0ef60):**
  - Concatenates all 36 months of 1m Last, 1m Mark R31 composites, and 3,285 settled funding rates into global continuous arrays.
  - Replays account fold-by-fold using the continuous arrays, maintaining single-position cash state across monthly fold boundaries.
- **Engine 2 (Final efa0b302):**
  - Streams monthly windows using `np.vstack([prev_last, curr_last])`, passing current-month Mark and current-month Funding rates.
  - Replays account fold-by-fold maintaining single-position cash state, generating paired counterfactual controls (`side_override = -trade_side`) for all filled trades.

### Mathematical Proof of Feature Invariance

- **EMA Convergence:** The longest EMA lookback is 50 1h bars ($\alpha = 2/51 \approx 0.0392$). Over a 1-month warmup of at least 672 1h bars, the decay of the initial seed is $(1 - \alpha)^{672} < 2.3 \times 10^{-12}$, well below floating-point machine precision.
- **Wilder ATR Convergence:** For ATR(14), the decay factor is $(13/14)^{672} < 10^{-21}$.
- **Rolling Window Features:** Rolling extremes (96 bars = 24h for 15m; 168 bars = 7d for 1h), Bollinger Bands (20 bars), Choppiness Index (24 bars), and volume z-scores (96 bars) require at most 7 days of historical bars. The previous month provides 28–31 days of completed bars, ensuring $100\%$ exact mathematical equivalence.
- **Account Replay Isolation:** Prospective fold censoring (`t_entry + horizon * HOUR + MINUTE < fold['end_ms']`) guarantees that every trade is entered, held, exited, and ACK-quantized strictly within the current month. Hence, no trade or funding event ever crosses into the subsequent month.

## 4. Conformance Contract and Tolerances

Governed by `evidence/v0.6/b_line/g2_goal_a_conformance_r2/GOAL_A_CONFORMANCE_CONTRACT.json`:

- **Discrete Entities (Exact match, tolerance = 0):**
  - Total signals generated, signal event IDs, and signal timestamps.
  - Total trades executed, trade entry/exit timestamps, exit reasons, sides, and trade quantities.
  - Account fate tallies (`FILLED`, `POSITION_ACK_OR_COOLDOWN`, `PROSPECTIVE_FOLD_CENSOR`, `ENTRY_OR_SIZE_REJECTED`).
- **Continuous Numerical Quantities (Max absolute difference $\le 10^{-9}$ USDT):**
  - Fill prices (`effective_entry`, `effective_exit`).
  - Gross PnL, trading fees, and funding cash flows.
  - Monthly ending equity and mark liquidation equity curves.
  - Net return in bps ($\le 10^{-6}$ bps).

## 5. Synthetic Unit Test Suite

Implemented in `tests/test_v06_g2_goal_a_conformance_r2_suite.py` containing 43 deterministic synthetic tests:
- Indicator warmup and mathematical decay convergence.
- Edge embargoes (month start, 24h month end).
- Prospective fold censoring and containment.
- Directional funding rate cash flows (long/short, positive/negative rates).
- Causal price gap veto and stop validation rules.
- Adverse pricing (0.1 tick ceiling/floor rounding).
- Single-position whole-account mechanics: 0.001 LOT, 5.0 USDT min notional, 1x budget cap.
- Low-equity capital exhaustion behavior.
- Paired control inversion symmetry.
- Dual-engine synthetic trace equivalence.

## 6. Execution Roadmap

1. **Stage 1 Commit (Pre-Execution Freeze):**
   - Commit harness, contract, test suite, and frozen plan.
   - Non-force push to `origin feature/v06-bline-gemini-goal-a-conformance-r2`.
   - Independently verify remote HEAD and parent SHA.
2. **Work Package A2 (One Bounded Replay Differential Audit):**
   - Run differential harness comparing Engine 1 and Engine 2 across all 8 candidates on authenticated 2021–2023 dataset under STRESS (44 bps) and BASE (22 bps).
3. **Work Package A3 (Machine-to-Human Exhaustive Reconciliation):**
   - Generate full typed reconciliation tables.
   - Document capital exhaustion proof for C01 2023.
   - Audit paired counterfactual controls.
4. **Stage 2 Commit & Non-Force Push (Evidence & Report Delivery):**
   - Output `DIFFERENTIAL_REPLAY_EVIDENCE.json`, `MACHINE_HUMAN_RECONCILIATION_TABLES.json`, `GOAL_A_CONFORMANCE_DELIVERY_MANIFEST.json`.
   - Comprehensive markdown report `GOAL_A_CONFORMANCE_REPORT.md`.
   - Non-force push and remote HEAD verification.
