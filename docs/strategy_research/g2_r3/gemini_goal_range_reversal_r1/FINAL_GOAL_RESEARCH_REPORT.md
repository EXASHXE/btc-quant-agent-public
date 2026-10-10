# Final Multi-Wave Empirical Strategy Discovery Report — Gemini Goal-B (Range / Reversal / Flow Exhaustion / Volatility Transition)

## 1. Executive Decision & Terminal Verdict

- **Task ID:** `V06_G2_GEMINI_GOAL_B_RANGE_REVERSAL_VOL_MULTI_WAVE_DISCOVERY_R1`
- **Agent Track:** `Gemini-B / Goal-R` (Independent of `Gemini-A / Goal-T`)
- **Controller Dispatch SHA:** `6c6ff831868701cea05499d0b0adb0e62db67f0e` (`reviews/v0.6/b_line/V06_G2_TWO_GEMINI_GOAL_LONG_HORIZON_PARALLEL_STRATEGY_DISCOVERY_DISPATCH_R1.md`)
- **Prompt SHA:** `e2101b58556a660e504cfdef66d33a64b42d9c21` (`prompts/v0.6/b_line/V06_G2_GEMINI_GOAL_B_ULTRALONG_BTC_RANGE_REVERSAL_VOL_DISCOVERY_R1.md`)
- **Exact Start SHA:** `920b244d06541da5cb9fc3dcaa39e5b15e914d32`
- **Branch & Isolated Worktree:** `feature/v06-bline-gemini-goal-range-reversal-r1` at `/root/workspace/project/quant-v0.6/gemini-goal-range-reversal-r1`
- **Terminal Verdict:** **`NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED`**
- **Promotable Candidates Ready for Holdout (`PROMOTABLE_DEV_HYPOTHESIS_PENDING_CONTROLLER_HOLDOUT`):** `0 / 24`
- **Cumulative Trial Budget Used:** `24 / 24` agent candidates across `4 / 4` pre-registered waves (`48` combined project trial budget across `Gemini-A + Gemini-B`, with `q = 0.05 / 48 = 0.0010417` multiplicity adjustment)
- **Candidates with Positive Gross Expectancy (2021–2023 STRESS execution):** `9 / 24` (`W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H, W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H, W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H, W4_C02_SQUEEZE_SNAPBACK_LOW_DRIFT_08H, W4_C05_ASIA_RANGE_EUROPE_SWEEP_RETURN_12H, W2_C03_LOW_VOL_REGIME_SHOCK_FADE_24H, W4_C01_WIDE_72H_RECLAIM_DYNAMIC_MIDLINE_12H, W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H, W1_C06_REGIME_TRANSITION_REVERSAL_24H`)
- **Candidates with Positive Equal-Year Edge over Time-Matched Balanced Control (STRESS):** `10 / 24` (`W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H, W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H, W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H, W4_C05_ASIA_RANGE_EUROPE_SWEEP_RETURN_12H, W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H, W1_C06_REGIME_TRANSITION_REVERSAL_24H, W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H, W3_C01_HIGH_VOL_72H_FAILED_BREAKOUT_WIDE_TARGET_24H, W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H, W4_C03_BOUNDED_48H_RANGE_REJECTION_12H`)
- **Strongest Overall STRESS Candidate (Rank #1 / 24):** `W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H` (`WAVE_02`, equal-year STRESS net `-33.29` bp, overall STRESS net `-33.10` bp, BASE net `-12.75` bp, gross **`+10.97` bp**, equal-year incremental vs balanced control **`+7.87` bp**, STRESS PF `0.62`, 1x account MTM drawdown `6.74%`)
- **Weakest Overall STRESS Candidate (Rank #24 / 24):** `W2_C02_EXTREME_BOLLINGER_FLOW_DIVERGENCE_08H` (`WAVE_02`, equal-year STRESS net `-62.12` bp, overall STRESS net `-59.96` bp, BASE net `-38.41` bp, gross `-15.93` bp, equal-year incremental vs balanced control `-20.19` bp, STRESS PF `0.31`, 1x account MTM drawdown `21.83%`)

### Why Terminal Verdict is `NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED`
Across 35 scored monthly windows (`2021-02` through `2023-12`, after `2021-01` warmup), 9 of the 24 pre-registered range/reversal/flow/volatility mechanisms achieved **positive gross returns before fees** (`+0.06` bp to `+10.97` bp per trade) and 10 of 24 beat time-matched 50/50 balanced controls on an equal-weighted annual basis (up to **`+9.34` bp/trade** in `W4_C04` and **`+8.93` bp/trade** in `W1_C06`). Moreover, in high-volatility regimes (`1h ATR >= 100 bps`), structural failed-breakout reclaim (`W2_C01`) and low-conviction extreme flow flip (`W4_C04`) generated **`+30.86` bp** and **`+37.47` bp gross** (**`+8.86` bp** and **`+15.47` bp net under BASE 22bp costs**, or `-13.14` bp and `-6.53` bp under STRESS 44bp costs). However, **no candidate simultaneously cleared the full 2021–2023 unconditional 44bp STRESS promotion gate** (`equal-year STRESS net > 0`, `STRESS PF >= 1.15`, `worst-year >= -10 bp`, and `48-trial-adjusted 7d/14d block bootstrap LCB > 0`). In accordance with the Skeptical Falsifier mandate, we issue an honest, fully audited `NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED` decision rather than relaxing gates or cherry-picking sub-slices.

---

## 2. Git Provenance, Multi-Wave Freeze-Before-Read Chain & Isolation Audit

| Wave | Candidate Indices | Frozen Registry File | Freeze Parent SHA | Freeze Commit SHA (Pushed Before Execution) | Result Commit SHA | Determinism Ledger SHA256 (Run1 == Run2) | Hand-Audited Trades |
|---|---|---|---|---|---|---|---:|
| `WAVE_01` | 1..6 | `evidence/v0.6/b_line/g2_gemini_goal_range_reversal_r1/WAVE_01_FROZEN_REGISTRY.json` | `920b244d06541da5cb9fc3dcaa39e5b15e914d32` | **`d558c45437681fe0b85056b11a71c9c7ea9bac49`** | `c116970123db2d116be2fbe740ce07df9e0523f2` | `b678ef0368a2c914eb2a5cdaa3e049ed109d2de8539519e0cc0cfafbbf5be7b4` | `30 / 30 PASS` |
| `WAVE_02` | 7..12 | `evidence/v0.6/b_line/g2_gemini_goal_range_reversal_r1/WAVE_02_FROZEN_REGISTRY.json` | `c116970123db2d116be2fbe740ce07df9e0523f2` | **`a6548f8e4b5b6fc4b63135d9cffeed8b97f23094`** | `bcd54875cb4f6ad85c5954dc96c5ba1c2dd5e12b` | `720fe202887f6e43deb1743b56aa858793c1d46440275a73dc3cab242fba0d45` | `30 / 30 PASS` |
| `WAVE_03` | 13..18 | `evidence/v0.6/b_line/g2_gemini_goal_range_reversal_r1/WAVE_03_FROZEN_REGISTRY.json` | `bcd54875cb4f6ad85c5954dc96c5ba1c2dd5e12b` | **`0c24218938be740113b6c80a3e1c847d2b08ca76`** | `7e4f407863ff7b7252365a254612518a1d517a72` | `f51cd09b0691bfbe04daea9854a4f572ef737ca6e67d438e8e9743925c9bbe12` | `30 / 30 PASS` |
| `WAVE_04` | 19..24 | `evidence/v0.6/b_line/g2_gemini_goal_range_reversal_r1/WAVE_04_FROZEN_REGISTRY.json` | `7e4f407863ff7b7252365a254612518a1d517a72` | **`4828e1532098e16b42e84e90952387b7cbd60d02`** | `30fe821040bacec6b75163017b2d79b2874900fa` | `ae91ae09b370594ba1dc6750aa24905ee2cf52917a053db43974c410e817c73e` | `30 / 30 PASS` |

### Strict Scope & Zero-Leakage Verification
- **2024–2026 Holdout / Future Data Access:** `0` files, `0` URLs, `0` bytes (`sources.py` enforces hard `ValueError` on any year outside `(2021, 2022, 2023)`).
- **Owner Local Data (`/root/workspace/project/Quant-agent/data`) & `Quant-agent-sanitized` Access:** `0` reads, `0` listings.
- **Sibling Worktree (`gemini-goal-trend-flow-r1`, `g2-btc-flow-regime-r2`) Access:** `0` reads, `0` writes.
- **Prior R1 Disclosure:** Prior R1 (`12` candidates on 2022–2023, freeze `21ee4c11b789d54aca6c602ce5c84426a3944fde`, result `920b244d06541da5cb9fc3dcaa39e5b15e914d32`) is explicitly disclosed in `CUMULATIVE_TRIAL_BUDGET_LEDGER.json` as prior development exposure.

---

## 3. Official Public 2021–2023 BTCUSDT USD-M 1m Data Manifest Summary

- **Manifest File:** `evidence/v0.6/b_line/g2_gemini_goal_range_reversal_r1/SOURCE_MANIFEST_2021_2023.json`
- **Source Prefix:** `https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/`
- **License & Attribution:** Binance Vision public archive under **CC BY-NC-SA 4.0** noncommercial research attribution; raw data stored only in private scratch `/tmp/g2-gemini-goal-range-reversal-r1` (`raw_data_rehosting: false`).
- **Verified Complete Months:** `36 / 36` (`2021-01` through `2023-12`)
- **Total Verified 1m Bars:** `1,576,800` contiguous 1m bars (`0` gaps, `0` duplicates, `0` out-of-order rows, `0` corrupted OHLCV/taker rows).
- **Timestamp Unit Detection:** Automatically detected `MILLISECONDS_DETECTED` across all 36 monthly archives (`2021-01` has no header row; `2021-02`..`2023-12` have 12-column header row; all 12 columns including `taker_buy_volume` validated).
- **Warmup & Monthly Window Edge Isolation:** `2021-01` (`44,640` 1m bars = 31 days) serves as pure indicator warmup. Each of the **35 scored months (`2021-02`..`2023-12`)** purges the first `24h` and last `24h` (`[month_start + 24h, month_end - 24h)`) and forbids any trade from holding across a month boundary (`EXIT_OUTSIDE_FOLD` / `PURGED_FOLD_EDGE`).
- **Economic Grade:** `COST_PROXY_DEV_ONLY` (historical mark-price klines and actual 8h funding-rate history were not fabricated; funding impact is evaluated via explicit `UTC8H_ASSUMED_SCHEDULE` and `UNKNOWN_HOURLY_STRESS` sensitivity debits at `4` bp and `8` bp).

---

## 4. Multi-Wave Exploration Trajectory & Hypothesis Evolution

1. **Wave 1 (`WAVE_01`, Freeze `d558c45437681fe0b85056b11a71c9c7ea9bac49`):** Tested 6 baseline 15m/1h/4h hypotheses across all 6 families with `2.0R` (or dynamic midline) targets and 95% 1x cash sizing:
   - **What Worked:** `W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H` (`+0.64` bp gross overall, `+10.65` bp in 2021, `+4.82` bp in 2022) and `W1_C06_REGIME_TRANSITION_REVERSAL_24H` (`+0.06` bp gross, positive balanced-control edge in all 3 years: `+16.29` bp in 2021, `+8.22` bp in 2022, `+2.28` bp in 2023; equal-year **`+8.93` bp**).
   - **What Failed & Why:** High-frequency 15m triggers (`W1_C01`..`W1_C04`, 500–1,100 trades) had tight stops (`0.8x–1.5x` 1h ATR) that were stopped out by 1m noise, where a 44bp roundtrip cost overwhelmed small expected excursions.
2. **Wave 2 (`WAVE_02`, Freeze `a6548f8e4b5b6fc4b63135d9cffeed8b97f23094`):** Shifted to wider structural dislocations (72h range reclaim, 48h Bollinger + flow divergence, low-vol shock fade, 2h volume climax, US-close/Asia-open handoff, and post-squeeze false expansion snap-back) with `15%` fractional 1x cash sizing:
   - **What Worked:** `W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H` achieved **`+10.97` bp gross** across 167 trades (**positive gross in all 3 years**: `+12.13` bp in 2021, `+19.46` bp in 2022, `+0.74` bp in 2023), `+7.87` bp equal-year control increment, `6.74%` 1x MTM drawdown, and **`+30.86` bp gross (`+8.86` bp BASE net)** in `ATR >= 100bp`. `W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H` achieved **`+7.10` bp gross** (positive gross and positive control increment in all 3 years: `+8.57` bp, `+10.25` bp, `+3.70` bp).
   - **What Failed & Why:** `W2_C02` (48h 2.15-sigma Bollinger fade, `-15.93` bp gross) and `W2_C04` (2h volume climax fade, `-7.37` bp gross) showed that high-volume/high-sigma extensions in BTC USD-M futures continue trending over 8h–12h rather than mean-reverting.
3. **Wave 3 (`WAVE_03`, Freeze `0c24218938be740113b6c80a3e1c847d2b08ca76`):** Tested whether filtering for higher hourly ATR (`>= 55–65` bps) and stretching targets to `2.4R–2.8R` over 12h–24h would allow winners to clear the 44bp STRESS hurdle:
   - **What Worked:** `W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H` achieved **`+17.92` bp gross** and **`+20.02` bp control increment** in **2023** (`103` trades). `W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H` beat balanced control in **all 3 years** (`+1.16` bp in 2021, `+8.73` bp in 2022, `+10.52` bp in 2023; `+6.80` bp equal-year). `W3_C01` beat balanced control by `+19.04` bp in 2021 and `+13.98` bp in 2022.
   - **What Failed & Why:** Stretching `target_r` to `2.4R–2.8R` on 24h horizons caused mean-reversion trades that were profitable at 8h–12h to reverse back into their wider stops during hours 12–24.
4. **Wave 4 (`WAVE_04`, Freeze `4828e1532098e16b42e84e90952387b7cbd60d02`):** Combined moderate `1.75R–1.85R` targets and 8h/12h horizons with macro efficiency filters (`4h ER12 <= 0.32–0.42`) and tested **low-conviction volume probe + taker-flow flip** (`W4_C04`):
   - **What Worked:** `W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H` achieved **`+8.97` bp gross** across 185 trades, **`+9.34` bp equal-year edge over balanced control** (highest of all 24 candidates), `6.14%` 1x MTM drawdown, **`+42.91` bp gross (`+20.89` bp BASE net, `-1.11` bp STRESS net, `+34.94` bp control edge)** in 2022 (`61` trades), and **`+37.47` bp gross (`+15.47` bp BASE net, `-6.53` bp STRESS net)** in `ATR >= 100bp` (`69` trades). Four of six Wave 4 candidates (`W4_C01`, `W4_C02`, `W4_C04`, `W4_C05`) achieved positive gross expectancy (`+1.34` bp to `+8.97` bp).

---

## 5. Complete 24-Candidate Empirical Comparison Table (Ranked by Equal-Year STRESS Mean Net bps)

| Rank | Wave | Candidate | Family | Hold | Signals | Fills BASE/STRESS | Long% | Gross bp (STRESS) | Net bp BASE / STRESS | Equal-Yr STRESS Net / Inc bp | Worst-Yr STRESS bp | STRESS PF / Win% | 1x Ret% / MTM DD% (STRESS) | Status |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | `WAVE_02` | `W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H` | `FAILED_ACCEPTANCE_REENTRY` | 12h | 265 | 167/167 | 49.70 | 10.97 | -12.75 / -33.10 | -33.29 / 7.87 | -43.33 | 0.62 / 34.73 | -6.37% / 6.74% | `FALSIFIED_DEV_CANDIDATE` |
| 2 | `WAVE_04` | `W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H` | `AGGRESSIVE_FLOW_EXHAUSTION` | 8h | 311 | 185/185 | 43.78 | 8.97 | -14.37 / -35.04 | -35.67 / 9.34 | -59.83 | 0.55 / 34.59 | -5.95% / 6.14% | `FALSIFIED_DEV_CANDIDATE` |
| 3 | `WAVE_02` | `W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H` | `VOL_COMPRESSION_TO_REVERT` | 4h | 2893 | 673/669 | 47.53 | 7.10 | -15.86 / -36.93 | -36.41 / 7.51 | -40.22 | 0.37 / 26.46 | -26.51% / 27.04% | `FALSIFIED_DEV_CANDIDATE` |
| 4 | `WAVE_04` | `W4_C02_SQUEEZE_SNAPBACK_LOW_DRIFT_08H` | `VOL_COMPRESSION_TO_REVERT` | 8h | 1373 | 406/405 | 44.94 | 3.64 | -19.96 / -40.38 | -39.95 / -0.25 | -45.32 | 0.42 / 26.42 | -14.76% / 15.78% | `FALSIFIED_DEV_CANDIDATE` |
| 5 | `WAVE_04` | `W4_C05_ASIA_RANGE_EUROPE_SWEEP_RETURN_12H` | `OVERNIGHT_SESSION_BOUNDARY_RETURN` | 12h | 386 | 289/289 | 44.64 | 1.34 | -21.22 / -42.70 | -42.38 / 4.46 | -58.54 | 0.52 / 31.49 | -11.20% / 11.66% | `FALSIFIED_DEV_CANDIDATE` |
| 6 | `WAVE_02` | `W2_C03_LOW_VOL_REGIME_SHOCK_FADE_24H` | `REGIME_TRANSITION_REVERSAL` | 24h | 9433 | 951/941 | 42.30 | 0.97 | -20.76 / -43.07 | -42.96 / -3.18 | -44.56 | 0.57 / 35.07 | -38.50% / 38.81% | `FALSIFIED_DEV_CANDIDATE` |
| 7 | `WAVE_04` | `W4_C01_WIDE_72H_RECLAIM_DYNAMIC_MIDLINE_12H` | `FAILED_ACCEPTANCE_REENTRY` | 12h | 167 | 103/103 | 44.66 | 3.35 | -18.14 / -40.68 | -43.06 / -1.33 | -61.45 | 0.56 / 33.98 | -3.98% / 4.26% | `FALSIFIED_DEV_CANDIDATE` |
| 8 | `WAVE_01` | `W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H` | `OVERNIGHT_SESSION_BOUNDARY_RETURN` | 12h | 736 | 511/511 | 50.10 | 0.64 | -21.53 / -43.39 | -43.10 / 0.24 | -56.74 | 0.58 / 32.49 | -86.63% / 87.02% | `FALSIFIED_DEV_CANDIDATE` |
| 9 | `WAVE_01` | `W1_C06_REGIME_TRANSITION_REVERSAL_24H` | `REGIME_TRANSITION_REVERSAL` | 24h | 875 | 424/423 | 47.52 | 0.06 | -22.66 / -43.97 | -44.11 / 8.93 | -46.30 | 0.60 / 34.99 | -82.27% / 85.17% | `FALSIFIED_DEV_CANDIDATE` |
| 10 | `WAVE_03` | `W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H` | `VOL_COMPRESSION_TO_REVERT` | 12h | 1307 | 385/385 | 48.31 | -2.67 | -25.04 / -46.68 | -44.80 / 1.50 | -61.30 | 0.53 / 30.65 | -15.08% / 16.18% | `FALSIFIED_DEV_CANDIDATE` |
| 11 | `WAVE_01` | `W1_C04_AGGRESSIVE_FLOW_EXHAUSTION_08H` | `AGGRESSIVE_FLOW_EXHAUSTION` | 8h | 3021 | 1301/978 | 55.32 | -1.09 | -20.62 / -45.11 | -45.07 / -1.54 | -45.85 | 0.53 / 32.92 | -97.29% / 97.59% | `FALSIFIED_DEV_CANDIDATE` |
| 12 | `WAVE_01` | `W1_C02_RANGE_MEAN_REVERT_WITH_VOLUME_04H` | `RANGE_MEAN_REVERT_WITH_VOLUME` | 4h | 1878 | 1050/946 | 53.28 | -0.94 | -22.44 / -44.97 | -45.21 / -1.10 | -47.59 | 0.39 / 29.81 | -97.20% / 97.20% | `FALSIFIED_DEV_CANDIDATE` |
| 13 | `WAVE_01` | `W1_C01_FAILED_ACCEPTANCE_REENTRY_04H` | `FAILED_ACCEPTANCE_REENTRY` | 4h | 4211 | 1746/1100 | 48.55 | -1.52 | -24.36 / -45.54 | -45.36 / -1.08 | -46.07 | 0.40 / 31.82 | -98.26% / 98.27% | `FALSIFIED_DEV_CANDIDATE` |
| 14 | `WAVE_02` | `W2_C05_US_CLOSE_ASIA_OPEN_REVERSAL_12H` | `OVERNIGHT_SESSION_BOUNDARY_RETURN` | 12h | 1351 | 787/787 | 49.43 | -1.47 | -24.60 / -45.49 | -45.44 / -0.78 | -46.81 | 0.48 / 32.27 | -35.24% / 35.48% | `FALSIFIED_DEV_CANDIDATE` |
| 15 | `WAVE_04` | `W4_C06_FOUR_HOUR_EXHAUSTION_MODERATE_VOL_24H` | `REGIME_TRANSITION_REVERSAL` | 24h | 561 | 340/335 | 48.06 | -3.07 | -27.14 / -47.10 | -46.12 / -0.43 | -53.43 | 0.53 / 31.64 | -13.62% / 14.23% | `FALSIFIED_DEV_CANDIDATE` |
| 16 | `WAVE_03` | `W3_C01_HIGH_VOL_72H_FAILED_BREAKOUT_WIDE_TARGET_24H` | `FAILED_ACCEPTANCE_REENTRY` | 24h | 267 | 148/148 | 48.65 | -2.34 | -21.25 / -46.41 | -46.68 / 4.59 | -48.16 | 0.61 / 35.81 | -6.52% / 6.97% | `FALSIFIED_DEV_CANDIDATE` |
| 17 | `WAVE_03` | `W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H` | `RANGE_MEAN_REVERT_WITH_VOLUME` | 24h | 1305 | 369/368 | 47.28 | -3.40 | -27.31 / -47.49 | -48.11 / 6.80 | -50.28 | 0.63 / 31.25 | -15.17% / 15.74% | `FALSIFIED_DEV_CANDIDATE` |
| 18 | `WAVE_03` | `W3_C04_HOURLY_TAKER_EXHAUSTION_WICK_REVERSAL_12H` | `AGGRESSIVE_FLOW_EXHAUSTION` | 12h | 688 | 398/398 | 55.03 | -6.55 | -29.68 / -50.58 | -51.64 / -4.16 | -60.20 | 0.51 / 34.17 | -17.23% / 17.37% | `FALSIFIED_DEV_CANDIDATE` |
| 19 | `WAVE_02` | `W2_C04_CLIMAX_VOLUME_TAKER_ABSORPTION_12H` | `AGGRESSIVE_FLOW_EXHAUSTION` | 12h | 3442 | 735/734 | 53.41 | -7.37 | -29.57 / -51.38 | -52.04 / -9.74 | -58.00 | 0.47 / 32.56 | -35.80% / 36.02% | `FALSIFIED_DEV_CANDIDATE` |
| 20 | `WAVE_04` | `W4_C03_BOUNDED_48H_RANGE_REJECTION_12H` | `RANGE_MEAN_REVERT_WITH_VOLUME` | 12h | 340 | 187/186 | 44.09 | -10.05 | -34.87 / -54.04 | -53.89 / 0.79 | -57.87 | 0.48 / 34.41 | -8.68% / 8.79% | `FALSIFIED_DEV_CANDIDATE` |
| 21 | `WAVE_03` | `W3_C06_FOUR_HOUR_CLIMAX_STALL_REVERSAL_24H` | `REGIME_TRANSITION_REVERSAL` | 24h | 616 | 356/355 | 52.11 | -10.67 | -33.31 / -54.71 | -54.58 / -3.36 | -60.52 | 0.55 / 30.99 | -16.89% / 18.12% | `FALSIFIED_DEV_CANDIDATE` |
| 22 | `WAVE_01` | `W1_C03_VOL_COMPRESSION_TO_REVERT_08H` | `VOL_COMPRESSION_TO_REVERT` | 8h | 784 | 514/514 | 43.77 | -10.19 | -32.44 / -54.21 | -55.50 / -11.02 | -67.60 | 0.35 / 26.07 | -91.32% / 91.37% | `FALSIFIED_DEV_CANDIDATE` |
| 23 | `WAVE_03` | `W3_C05_REGIONAL_SESSION_SWEEP_RECLAIM_12H` | `OVERNIGHT_SESSION_BOUNDARY_RETURN` | 12h | 542 | 345/345 | 50.72 | -16.92 | -38.82 / -60.96 | -60.20 / -10.15 | -76.17 | 0.40 / 30.72 | -18.36% / 18.65% | `FALSIFIED_DEV_CANDIDATE` |
| 24 | `WAVE_02` | `W2_C02_EXTREME_BOLLINGER_FLOW_DIVERGENCE_08H` | `RANGE_MEAN_REVERT_WITH_VOLUME` | 8h | 1257 | 334/334 | 47.90 | -15.93 | -38.41 / -59.96 | -62.12 / -20.19 | -84.03 | 0.31 / 29.94 | -21.83% / 21.83% | `FALSIFIED_DEV_CANDIDATE` |

---

## 6. Annual Breakdown (`2021`, `2022`, `2023`) & Time-Matched Controls Across All 24 Candidates (STRESS 44bp)

| Wave | Candidate | 2021 Fills / Gross / STRESS Net / Inc bp | 2022 Fills / Gross / STRESS Net / Inc bp | 2023 Fills / Gross / STRESS Net / Inc bp | Matched Long / Short / Balanced 50-50 Control bp (Overall STRESS) |
|---|---|---|---|---|---|
| `WAVE_02` | `W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H` | 53 / 12.13 / -31.94 / 21.88 | 59 / 19.46 / -24.60 / 16.86 | 55 / 0.74 / -43.33 / -15.13 | -39.35 / -42.68 / -41.02 |
| `WAVE_04` | `W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H` | 73 / -2.07 / -46.09 / -1.58 | 61 / 42.91 / -1.11 / 34.94 | 51 / -15.83 / -59.83 / -5.34 | -54.77 / -34.17 / -44.47 |
| `WAVE_02` | `W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H` | 151 / 9.44 / -34.57 / 8.57 | 234 / 9.57 / -34.44 / 10.25 | 284 / 3.81 / -40.22 / 3.70 | -50.04 / -37.99 / -44.01 |
| `WAVE_04` | `W4_C02_SQUEEZE_SNAPBACK_LOW_DRIFT_08H` | 84 / 4.97 / -39.01 / -5.13 | 150 / 8.51 / -35.52 / 3.86 | 171 / -1.29 / -45.32 / 0.51 | -47.15 / -34.78 / -40.96 |
| `WAVE_04` | `W4_C05_ASIA_RANGE_EUROPE_SWEEP_RETURN_12H` | 90 / 19.61 / -24.40 / 16.12 | 94 / -14.47 / -58.54 / -0.23 | 105 / -0.17 / -44.21 / -2.51 | -47.62 / -45.86 / -46.74 |
| `WAVE_02` | `W2_C03_LOW_VOL_REGIME_SHOCK_FADE_24H` | 284 / 3.40 / -40.62 / -3.07 | 326 / -0.53 / -44.56 / -3.23 | 331 / 0.35 / -43.70 / -3.25 | -40.39 / -39.37 / -39.88 |
| `WAVE_04` | `W4_C01_WIDE_72H_RECLAIM_DYNAMIC_MIDLINE_12H` | 42 / 8.08 / -35.97 / 21.92 | 36 / 12.20 / -31.74 / 5.22 | 25 / -17.34 / -61.45 / -31.14 | -42.95 / -44.81 / -43.88 |
| `WAVE_01` | `W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H` | 156 / 10.65 / -33.35 / 8.16 | 181 / 4.82 / -39.23 / 9.71 | 174 / -12.68 / -56.74 / -17.16 | -43.47 / -43.49 / -43.48 |
| `WAVE_01` | `W1_C06_REGIME_TRANSITION_REVERSAL_24H` | 129 / -2.27 / -46.30 / 16.29 | 144 / -2.03 / -46.03 / 8.22 | 150 / 4.06 / -39.99 / 2.28 | -55.31 / -49.78 / -52.55 |
| `WAVE_03` | `W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H` | 142 / -17.32 / -61.30 / -17.62 | 140 / -2.95 / -46.96 / 2.09 | 103 / 17.92 / -26.15 / 20.02 | -54.99 / -37.61 / -46.30 |
| `WAVE_01` | `W1_C04_AGGRESSIVE_FLOW_EXHAUSTION_08H` | 377 / -0.22 / -44.23 / -3.97 | 450 / -1.83 / -45.85 / -6.23 | 151 / -1.07 / -45.13 / 5.58 | -49.46 / -33.69 / -41.57 |
| `WAVE_01` | `W1_C02_RANGE_MEAN_REVERT_WITH_VOLUME_04H` | 384 / -3.57 / -47.59 / -1.30 | 369 / 2.70 / -41.33 / 0.81 | 193 / -2.66 / -46.70 / -2.82 | -47.13 / -41.23 / -44.18 |
| `WAVE_01` | `W1_C01_FAILED_ACCEPTANCE_REENTRY_04H` | 689 / -2.06 / -46.07 / -2.87 | 411 / -0.62 / -44.64 / 0.71 | 0 / NA / NA / NA | -48.24 / -39.77 / -44.00 |
| `WAVE_02` | `W2_C05_US_CLOSE_ASIA_OPEN_REVERSAL_12H` | 249 / 0.52 / -43.49 / 2.69 | 269 / -2.79 / -46.81 / -5.28 | 269 / -1.99 / -46.02 / 0.25 | -48.75 / -40.49 / -44.62 |
| `WAVE_04` | `W4_C06_FOUR_HOUR_EXHAUSTION_MODERATE_VOL_24H` | 70 / 0.30 / -43.68 / 0.59 | 118 / 2.79 / -41.25 / 3.53 | 147 / -9.38 / -53.43 / -5.42 | -44.86 / -47.33 / -46.10 |
| `WAVE_03` | `W3_C01_HIGH_VOL_72H_FAILED_BREAKOUT_WIDE_TARGET_24H` | 59 / -1.22 / -45.25 / 19.04 | 57 / -2.61 / -46.62 / 13.98 | 32 / -3.93 / -48.16 / -19.26 | -54.29 / -56.15 / -55.22 |
| `WAVE_03` | `W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H` | 164 / -1.02 / -45.10 / 1.16 | 134 / -4.85 / -48.95 / 8.73 | 70 / -6.20 / -50.28 / 10.52 | -39.91 / -66.45 / -53.18 |
| `WAVE_03` | `W3_C04_HOURLY_TAKER_EXHAUSTION_WICK_REVERSAL_12H` | 150 / -2.06 / -46.09 / 6.30 | 148 / -4.62 / -48.63 / -5.08 | 100 / -16.16 / -60.20 / -13.69 | -56.64 / -38.60 / -47.62 |
| `WAVE_02` | `W2_C04_CLIMAX_VOLUME_TAKER_ABSORPTION_12H` | 197 / -13.99 / -58.00 / -18.56 | 257 / -7.52 / -51.53 / -5.86 | 280 / -2.56 / -46.59 / -4.80 | -51.62 / -33.42 / -42.52 |
| `WAVE_04` | `W4_C03_BOUNDED_48H_RANGE_REJECTION_12H` | 85 / -13.91 / -57.87 / -18.79 | 67 / -4.59 / -48.63 / 10.14 | 34 / -11.14 / -55.17 / 11.03 | -74.57 / -27.69 / -51.13 |
| `WAVE_03` | `W3_C06_FOUR_HOUR_CLIMAX_STALL_REVERSAL_24H` | 118 / -6.35 / -50.34 / 1.92 | 113 / -8.83 / -52.89 / -1.93 | 124 / -16.45 / -60.52 / -10.07 | -49.18 / -53.24 / -51.21 |
| `WAVE_01` | `W1_C03_VOL_COMPRESSION_TO_REVERT_08H` | 136 / -23.64 / -67.60 / -26.22 | 163 / -5.79 / -49.84 / -4.36 | 215 / -5.01 / -49.05 / -2.47 | -44.55 / -45.17 / -44.86 |
| `WAVE_03` | `W3_C05_REGIONAL_SESSION_SWEEP_RECLAIM_12H` | 148 / -9.78 / -53.82 / -16.07 | 121 / -32.18 / -76.17 / -17.22 | 76 / -6.52 / -50.62 / 2.83 | -59.00 / -38.29 / -48.64 |
| `WAVE_02` | `W2_C02_EXTREME_BOLLINGER_FLOW_DIVERGENCE_08H` | 87 / -40.00 / -84.03 / -45.60 | 105 / -5.09 / -49.10 / -2.50 | 142 / -9.19 / -53.23 / -12.49 | -45.39 / -38.58 / -41.99 |

---

## 7. Multiplicity-Adjusted Block Bootstrap (`48` Combined Project Trials) & Funding Sensitivity (STRESS 44bp)

| Wave | Candidate | Distinct Yrs / Mos | 7d Week Net 95% CI | 7d Adj-48 Net / Inc LCB | 14d Adj-48 Net / Inc LCB | UTC8h Adverse 4bp / 8bp Net Mean | Hourly Adverse 4bp / 8bp Net Mean | MAE / MFE Mean bp | Worst 5% Mean bp |
|---|---|---|---|---|---|---|---|---|---|
| `WAVE_02` | `W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H` | 3 / 35 | `[-58.48, -8.60]` | -72.46 / -29.21 | -74.38 / -32.85 | -37.08 / -41.06 | -65.08 / -97.06 | -113.85 / 128.23 | -288.88 |
| `WAVE_04` | `W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H` | 3 / 35 | `[-55.36, -16.11]` | -65.12 / -16.86 | -64.65 / -15.09 | -37.94 / -40.84 | -56.94 / -78.83 | -93.56 / 118.61 | -249.26 |
| `WAVE_02` | `W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H` | 3 / 35 | `[-43.59, -29.22]` | -47.38 / -2.37 | -47.79 / -3.33 | -38.59 / -40.25 | -49.39 / -61.86 | -54.63 / 73.40 | -205.01 |
| `WAVE_04` | `W4_C02_SQUEEZE_SNAPBACK_LOW_DRIFT_08H` | 3 / 35 | `[-52.00, -27.00]` | -58.21 / -18.31 | -60.00 / -18.18 | -42.71 / -45.04 | -59.95 / -79.52 | -65.99 / 85.83 | -211.53 |
| `WAVE_04` | `W4_C05_ASIA_RANGE_EUROPE_SWEEP_RETURN_12H` | 3 / 35 | `[-59.29, -25.75]` | -68.11 / -21.40 | -68.28 / -22.75 | -45.53 / -48.35 | -70.05 / -97.39 | -102.85 / 130.58 | -279.91 |
| `WAVE_02` | `W2_C03_LOW_VOL_REGIME_SHOCK_FADE_24H` | 3 / 35 | `[-53.44, -32.22]` | -58.87 / -18.18 | -59.20 / -19.35 | -48.19 / -53.31 | -84.51 / -125.95 | -108.27 / 129.55 | -265.56 |
| `WAVE_04` | `W4_C01_WIDE_72H_RECLAIM_DYNAMIC_MIDLINE_12H` | 3 / 34 | `[-78.73, -6.09]` | -99.03 / -51.89 | -101.68 / -53.31 | -44.76 / -48.84 | -74.99 / -109.29 | -125.35 / 135.60 | -289.49 |
| `WAVE_01` | `W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H` | 3 / 35 | `[-56.75, -29.74]` | -64.72 / -19.38 | -61.63 / -16.61 | -46.96 / -50.53 | -73.65 / -103.91 | -106.96 / 133.85 | -274.83 |
| `WAVE_01` | `W1_C06_REGIME_TRANSITION_REVERSAL_24H` | 3 / 35 | `[-64.74, -23.71]` | -76.65 / -18.93 | -76.44 / -21.51 | -50.43 / -56.90 | -100.33 / -156.68 | -131.19 / 167.72 | -319.41 |
| `WAVE_03` | `W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H` | 3 / 34 | `[-61.49, -27.20]` | -70.42 / -21.20 | -70.46 / -20.34 | -50.62 / -54.56 | -78.47 / -110.26 | -109.38 / 150.36 | -279.03 |
| `WAVE_01` | `W1_C04_AGGRESSIVE_FLOW_EXHAUSTION_08H` | 3 / 29 | `[-52.93, -37.17]` | -58.33 / -14.62 | -57.84 / -14.62 | -48.04 / -50.96 | -68.76 / -92.40 | -102.86 / 121.21 | -289.21 |
| `WAVE_01` | `W1_C02_RANGE_MEAN_REVERT_WITH_VOLUME_04H` | 3 / 32 | `[-51.02, -39.62]` | -54.32 / -9.77 | -54.89 / -10.29 | -46.27 / -47.58 | -55.70 / -66.43 | -69.77 / 77.68 | -218.79 |
| `WAVE_01` | `W1_C01_FAILED_ACCEPTANCE_REENTRY_04H` | 2 / 21 | `[-51.36, -39.16]` | -55.42 / -11.04 | -54.17 / -10.32 | -47.03 / -48.53 | -57.23 / -68.93 | -81.85 / 95.96 | -243.74 |
| `WAVE_02` | `W2_C05_US_CLOSE_ASIA_OPEN_REVERSAL_12H` | 3 / 35 | `[-55.34, -35.49]` | -61.09 / -15.26 | -63.57 / -17.15 | -49.72 / -53.96 | -77.73 / -109.98 | -98.59 / 112.89 | -287.33 |
| `WAVE_04` | `W4_C06_FOUR_HOUR_EXHAUSTION_MODERATE_VOL_24H` | 3 / 34 | `[-65.84, -25.22]` | -77.77 / -28.07 | -75.48 / -24.92 | -52.53 / -57.95 | -94.70 / -142.30 | -110.28 / 132.06 | -233.57 |
| `WAVE_03` | `W3_C01_HIGH_VOL_72H_FAILED_BREAKOUT_WIDE_TARGET_24H` | 3 / 32 | `[-83.01, -9.50]` | -99.55 / -46.03 | -97.67 / -45.23 | -53.01 / -59.62 | -98.41 / -150.41 | -143.39 / 193.16 | -296.64 |
| `WAVE_03` | `W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H` | 3 / 35 | `[-71.03, -25.90]` | -85.90 / -25.70 | -82.23 / -22.07 | -53.37 / -59.25 | -94.74 / -141.99 | -146.74 / 193.00 | -309.63 |
| `WAVE_03` | `W3_C04_HOURLY_TAKER_EXHAUSTION_WICK_REVERSAL_12H` | 3 / 35 | `[-66.83, -36.40]` | -76.70 / -25.34 | -75.72 / -25.47 | -54.46 / -58.35 | -83.29 / -116.00 | -126.38 / 153.35 | -297.17 |
| `WAVE_02` | `W2_C04_CLIMAX_VOLUME_TAKER_ABSORPTION_12H` | 3 / 35 | `[-64.12, -39.84]` | -70.54 / -27.83 | -72.28 / -27.32 | -55.50 / -59.61 | -82.49 / -113.60 | -112.80 / 119.44 | -292.07 |
| `WAVE_04` | `W4_C03_BOUNDED_48H_RANGE_REJECTION_12H` | 3 / 35 | `[-73.47, -35.40]` | -83.97 / -24.54 | -86.60 / -22.76 | -57.04 / -60.03 | -78.93 / -103.81 | -118.64 / 131.07 | -271.51 |
| `WAVE_03` | `W3_C06_FOUR_HOUR_CLIMAX_STALL_REVERSAL_24H` | 3 / 35 | `[-78.09, -30.30]` | -91.83 / -34.84 | -91.47 / -33.24 | -60.84 / -66.97 | -108.21 / -161.71 | -139.58 / 174.75 | -314.76 |
| `WAVE_01` | `W1_C03_VOL_COMPRESSION_TO_REVERT_08H` | 3 / 35 | `[-67.11, -44.24]` | -73.39 / -27.77 | -74.11 / -27.80 | -57.41 / -60.61 | -78.95 / -103.69 | -87.95 / 92.58 | -261.24 |
| `WAVE_03` | `W3_C05_REGIONAL_SESSION_SWEEP_RECLAIM_12H` | 3 / 35 | `[-77.08, -42.93]` | -85.75 / -34.37 | -84.16 / -31.90 | -63.49 / -66.02 | -94.34 / -127.72 | -120.43 / 141.30 | -282.82 |
| `WAVE_02` | `W2_C02_EXTREME_BOLLINGER_FLOW_DIVERGENCE_08H` | 3 / 35 | `[-76.73, -47.10]` | -86.05 / -43.39 | -85.06 / -43.97 | -62.74 / -65.52 | -82.85 / -105.75 | -107.12 / 90.89 | -280.84 |

---

## 8. Volatility Regime Slices (`ATR < 50bp`, `ATR 50-100bp`, `ATR >= 100bp`) & Exit Reason Breakdown (STRESS 44bp)

| Wave | Candidate | ATR < 50bp (N / STRESS Net bp) | ATR 50-100bp (N / STRESS Net bp) | ATR >= 100bp (N / STRESS Net bp) | Exit Counts (STOP / TARGET / TIME_CAP / GAP) |
|---|---|---|---|---|---|
| `WAVE_02` | `W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H` | 21 / -56.45 | 80 / -43.43 | 66 / -13.14 | 62 / 29 / 76 / 0 |
| `WAVE_04` | `W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H` | 29 / -33.58 | 87 / -58.15 | 69 / -6.53 | 77 / 24 / 84 / 0 |
| `WAVE_02` | `W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H` | 213 / -41.52 | 323 / -37.19 | 133 / -28.92 | 194 / 104 / 371 / 0 |
| `WAVE_04` | `W4_C02_SQUEEZE_SNAPBACK_LOW_DRIFT_08H` | 127 / -44.89 | 205 / -46.70 | 73 / -14.80 | 191 / 73 / 141 / 0 |
| `WAVE_04` | `W4_C05_ASIA_RANGE_EUROPE_SWEEP_RETURN_12H` | 61 / -45.95 | 138 / -41.28 | 90 / -42.68 | 147 / 57 / 85 / 0 |
| `WAVE_02` | `W2_C03_LOW_VOL_REGIME_SHOCK_FADE_24H` | 152 / -49.96 | 471 / -43.98 | 318 / -38.43 | 528 / 274 / 139 / 0 |
| `WAVE_04` | `W4_C01_WIDE_72H_RECLAIM_DYNAMIC_MIDLINE_12H` | 0 / NA | 57 / -46.90 | 46 / -32.97 | 39 / 12 / 52 / 0 |
| `WAVE_01` | `W1_C05_OVERNIGHT_SESSION_BOUNDARY_RETURN_12H` | 91 / -43.56 | 261 / -48.71 | 159 / -34.58 | 249 / 72 / 190 / 0 |
| `WAVE_01` | `W1_C06_REGIME_TRANSITION_REVERSAL_24H` | 48 / -7.39 | 223 / -34.10 | 152 / -70.00 | 204 / 77 / 142 / 0 |
| `WAVE_03` | `W3_C02_FOUR_HOUR_FALSE_EXPANSION_SNAPBACK_12H` | 0 / NA | 251 / -42.46 | 134 / -54.60 | 179 / 38 / 168 / 0 |
| `WAVE_01` | `W1_C04_AGGRESSIVE_FLOW_EXHAUSTION_08H` | 105 / -38.53 | 480 / -41.62 | 393 / -51.13 | 369 / 89 / 520 / 0 |
| `WAVE_01` | `W1_C02_RANGE_MEAN_REVERT_WITH_VOLUME_04H` | 124 / -43.00 | 463 / -46.22 | 359 / -44.04 | 403 / 128 / 415 / 0 |
| `WAVE_01` | `W1_C01_FAILED_ACCEPTANCE_REENTRY_04H` | 8 / -27.58 | 469 / -44.75 | 623 / -46.36 | 427 / 85 / 588 / 0 |
| `WAVE_02` | `W2_C05_US_CLOSE_ASIA_OPEN_REVERSAL_12H` | 143 / -47.19 | 364 / -43.61 | 280 / -47.06 | 305 / 119 / 363 / 0 |
| `WAVE_04` | `W4_C06_FOUR_HOUR_EXHAUSTION_MODERATE_VOL_24H` | 51 / -25.69 | 219 / -51.64 | 65 / -48.65 | 184 / 75 / 76 / 0 |
| `WAVE_03` | `W3_C01_HIGH_VOL_72H_FAILED_BREAKOUT_WIDE_TARGET_24H` | 0 / NA | 67 / -36.86 | 81 / -54.31 | 87 / 21 / 40 / 0 |
| `WAVE_03` | `W3_C03_MULTI_DAY_RANGE_MIDLINE_ROTATION_24H` | 0 / NA | 206 / -36.94 | 162 / -60.90 | 232 / 60 / 76 / 0 |
| `WAVE_03` | `W3_C04_HOURLY_TAKER_EXHAUSTION_WICK_REVERSAL_12H` | 0 / NA | 227 / -35.43 | 171 / -70.70 | 174 / 33 / 191 / 0 |
| `WAVE_02` | `W2_C04_CLIMAX_VOLUME_TAKER_ABSORPTION_12H` | 165 / -48.79 | 392 / -49.59 | 177 / -57.78 | 314 / 109 / 311 / 0 |
| `WAVE_04` | `W4_C03_BOUNDED_48H_RANGE_REJECTION_12H` | 0 / NA | 113 / -42.65 | 73 / -71.68 | 101 / 32 / 53 / 0 |
| `WAVE_03` | `W3_C06_FOUR_HOUR_CLIMAX_STALL_REVERSAL_24H` | 34 / -51.62 | 174 / -49.28 | 147 / -61.84 | 203 / 34 / 118 / 0 |
| `WAVE_01` | `W1_C03_VOL_COMPRESSION_TO_REVERT_08H` | 111 / -46.96 | 234 / -49.47 | 169 / -65.55 | 188 / 36 / 290 / 0 |
| `WAVE_03` | `W3_C05_REGIONAL_SESSION_SWEEP_RECLAIM_12H` | 0 / NA | 183 / -65.55 | 162 / -55.77 | 160 / 15 / 170 / 0 |
| `WAVE_02` | `W2_C02_EXTREME_BOLLINGER_FLOW_DIVERGENCE_08H` | 80 / -52.96 | 180 / -55.76 | 74 / -77.74 | 133 / 31 / 170 / 0 |

---

## 9. Three Diagnostic Strategy / Mechanism Cards (`NOT_YET_VALIDATED_OUT_OF_SAMPLE`)

> **Important Disclosure:** None of the 3 diagnostic cards below cleared the unconditional 2021–2023 44bp STRESS promotion gate. They are documented strictly as falsified/diagnostic development findings (`FALSIFIED_DEV_CANDIDATE` / `NOT_YET_VALIDATED_OUT_OF_SAMPLE`) to preserve empirical lessons on where range/reversal/flow mechanisms showed positive gross expectancy and positive control increments.

### Card 1 — `W2_C01_WIDE_72H_FAILED_BREAKOUT_RECLAIM_12H` (Rank #1 Overall STRESS Net & Gross Expectancy)
- **Family:** `FAILED_ACCEPTANCE_REENTRY` (`WAVE_02`, Freeze `a6548f8e4b5b6fc4b63135d9cffeed8b97f23094`)
- **Validation Status:** `FALSIFIED_DEV_CANDIDATE` / `NOT_YET_VALIDATED_OUT_OF_SAMPLE`
- **Exact Causal Rule:** Evaluated on completed 1h boundaries (`15m` bar `k` with `end_ms % 3_600_000 == 0`). Compute prior 72h range `hi_72h = max(high[k-291:k-3])`, `lo_72h = min(low[k-291:k-3])` with width in `[180, 1200]` bps. Enter Long (Short) at next 1m open (`event_time + 120s`) if the last 1h window `[k-3:k+1]` swept below `lo_72h` (above `hi_72h`), `close[k]` reclaimed inside the range by `>= 0.25 * ATR14_15m`, 1h return `close[k] - open[k-3]` is positive (negative), and 1h taker imbalance `taker_imb_4 >= -0.02` (`<= +0.02`).
- **Brackets & Sizing:** `12h` max hold, initial stop `3.0 * ATR14_15m` (clamped to `[40, 250]` bps), target `1.55 R`, cooldown `6h`, `15%` 1x cash allocation.
- **2021–2023 Empirical Performance:** `167` trades across `3` years / `35` months (`49.70%` Long). **Gross Mean: `+10.97` bp** (`+12.13` bp in 2021, `+19.46` bp in 2022, `+0.74` bp in 2023 — **positive gross in all 3 years**). BASE Net: `-12.75` bp (PF `0.83`). STRESS Net: `-33.10` bp (PF `0.62`, MTM DD `6.74%`). Equal-year edge over balanced control: **`+7.87` bp** (`+21.88` bp in 2021, `+16.86` bp in 2022). In **`ATR >= 100bp` (`66` trades)**: **`+30.86` bp gross, `+8.86` bp BASE net, `-13.14` bp STRESS net**.
- **Failure Mode:** In low-volatility compression (`ATR < 50bp` and `2023` tight ranges), 72h range reclaims lack sufficient follow-through to cover 44bp roundtrip costs.

### Card 2 — `W4_C04_LOW_CONVICTION_EXTREME_FLOW_FLIP_08H` (Rank #2 Overall STRESS Net, Rank #1 Balanced-Control Edge)
- **Family:** `AGGRESSIVE_FLOW_EXHAUSTION` (`WAVE_04`, Freeze `4828e1532098e16b42e84e90952387b7cbd60d02`)
- **Validation Status:** `FALSIFIED_DEV_CANDIDATE` / `NOT_YET_VALIDATED_OUT_OF_SAMPLE`
- **Exact Causal Rule:** Evaluated on completed 15m bars when 4h Efficiency Ratio `er4_12 <= 0.36`. When the last 1h `[k-3:k+1]` probes the prior 24h (`96` 15m bars) high or low on **non-climax 1h volume** (`0.55x` to `1.35x` of `4 * SMA20(vol15)`), and bar `k` prints a counter-directional body `>= 0.35 * ATR14_15m` with a strong **30m taker-buy imbalance flip `>= +5%` (`<= -5%`)**, enter at next 1m open.
- **Brackets & Sizing:** `8h` max hold, initial stop `2.6 * ATR14_15m` (clamped to `[45, 240]` bps), target `1.80 R`, cooldown `4h`, `12%` 1x cash allocation.
- **2021–2023 Empirical Performance:** `185` trades across `3` years / `35` months (`43.78%` Long). **Gross Mean: `+8.97` bp**. BASE Net: `-14.37` bp (PF `0.76`, MTM DD `2.81%`). STRESS Net: `-35.04` bp (PF `0.55`, MTM DD `6.14%`). **Equal-year edge over balanced control: `+9.34` bp** (Rank #1 of 24). In **2022 (`61` trades)**: **`+42.91` bp gross, `+20.89` bp BASE net, `-1.11` bp STRESS net, `+34.94` bp edge over balanced control, PF `0.95`**. In **`ATR >= 100bp` (`69` trades)**: **`+37.47` bp gross, `+15.47` bp BASE net, `-6.53` bp STRESS net**.
- **Failure Mode:** Slow-grind low-volatility directional creep in 2023 (`-15.83` bp gross) where low-volume new highs/lows continue drifting without snapping back.

### Card 3 — `W2_C06_KELTNER_SQUEEZE_FALSE_EXPANSION_04H` (Rank #3 Overall STRESS Net, Positive Gross & Control Edge in All 3 Years)
- **Family:** `VOL_COMPRESSION_TO_REVERT` (`WAVE_02`, Freeze `a6548f8e4b5b6fc4b63135d9cffeed8b97f23094`)
- **Validation Status:** `FALSIFIED_DEV_CANDIDATE` / `NOT_YET_VALIDATED_OUT_OF_SAMPLE`
- **Exact Causal Rule:** Evaluated on completed 15m bars. Require prior volatility compression (`ATR48 / ATR192 <= 0.85` at `k-8`), a 2h expansion excursion `>= 1.60 * ATR14_15m` away from the 24h SMA `m96`, followed by a snap-back closing within `0.80 * ATR14_15m` of `m96` with 30m snap-back momentum `>= 0.45 * ATR14_15m`.
- **Brackets & Sizing:** `4h` max hold, initial stop `2.5 * ATR14_15m`, target `1.55 R`, cooldown `4h`, `15%` 1x cash allocation.
- **2021–2023 Empirical Performance:** `669` STRESS trades across `3` years / `35` months (`47.53%` Long). **Gross Mean: `+7.10` bp** (**positive in all 3 years**: `+9.44` bp in 2021, `+9.57` bp in 2022, `+3.81` bp in 2023). **Incremental vs Balanced Control: `+7.51` bp equal-year** (**positive in all 3 years**: `+8.57` bp in 2021, `+10.25` bp in 2022, `+3.70` bp in 2023). Its 12h variant (`W3_C02`) achieved **`+17.92` bp gross** and **`+20.02` bp control edge** in 2023.
- **Failure Mode:** 4h horizon and 15m trigger frequency (`669` trades) incur too many 44bp roundtrip tolls relative to the `+7.10` bp gross move.

---

## 10. Determinism & Independent Decimal Hand-Audit Summary

- **Two-Run Determinism:** Every wave (`WAVE_01`..`WAVE_04`) executed two full independent passes across the 1,576,800 1m bars and verified bit-identical trade and decision event ledgers (`determinism_verified_two_runs: true`).
- **Independent Decimal Hand-Audit:** `30` real trades per wave (`120` trades total across all 24 candidates and both `BASE` and `STRESS` cost tiers) were independently verified using Python `Decimal` arithmetic (`scripts/strategy_research/g2_gemini_goal_range_reversal_r1/audit.py`) for tick rounding, adverse slippage, single-leg fee application, first-hit bar collision (`STOP` beats `TARGET` on same 1m bar), open-gap handling, and net PnL (`120 / 120 PASS`).
- **Report Generated At (UTC):** `2026-10-10T20:59:07.465994+00:00`

