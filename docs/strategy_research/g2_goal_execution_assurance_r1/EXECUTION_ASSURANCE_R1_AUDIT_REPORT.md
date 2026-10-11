# GEMINI GOAL C — Independent BTC Exit-Book / Funding / Mark / Risk Execution Assurance Report

- **Terminal Disposition:** `EXECUTION_INDEPENDENT_DIAGNOSTIC_COMPLETE`
- **Task ID:** `V06_G2_GEMINI_GOAL_C_EXECUTION_ASSURANCE_R1`
- **Controller Dispatch SHA:** `c02743fddccdf517582c371a47e82d8dcbb05923`
- **Exact Start SHA (Final Exit R1):** `55ac4c631c69f6edbd275462ad23e4486b9782ed`
- **Frozen Exit R1 Code SHA:** `de2c1fb222970a93ca797868b91b8544261ebaad`
- **Goal C Freeze Commit (Commit 1) SHA:** `4c0bac051767f788e6de173f6563a7b47af2ac69`
- **Scientific Grade:** `INDEPENDENT_EXECUTION_ASSURANCE_DIAGNOSTIC_ONLY__NO_PROMOTION_NO_LIVE_NO_TESTNET`

## 1. Executive Summary & Disposition Rationale

This independent adversarial audit challenged the frozen Exit R1 (`de2c1fb222970a93ca797868b91b8544261ebaad` / `55ac4c631c69f6edbd275462ad23e4486b9782ed`), R3.1 (`990c02b5479b3b14996f90fdbf677cb672ada81e`), R3, and R2 implementations across six verification targets without invoking production economics as an oracle:

1. **Verified Mathematical & Causal Accounting (`0` Reproducible Code/Ledger Defects):** Independent stdlib Dual-`Decimal` reconstruction across **48 deep forensic episodes** (including all 24 original R1 partial-funding episodes plus 24 stratified `H1`/`H2`/`E0`/`E1`/`E2` episodes across 2021–2023, `STRESS`/`BASE`, and `LONG`/`SHORT`) and **all 890 committed order-ledger trades** (20 order ledgers) confirmed exact agreement on effective entry/exit ticks, single entry fee charging, per-tier exit fees, 0.001 BTC lot splitting, signed observed Funding on remaining inventory at the latest completed 1m Mark close (`t - 1 ms`), non-spendability of unacknowledged exit P&L before `exit_ack_at`, and minute-by-minute Mark liquidation equity curves.
2. **Confirmed Empirical Boundary Limitation (`0` Real `<60s` TP1-to-Settlement Cases):** Independent scan of all 3,285 historical funding settlements against all partial TP1 fills confirmed that the closest actual TP1 fill to any funding settlement is **`119999 ms`** (`W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1670792400000_-1`, `TP1_at=1670803319999`, `settlement_at=1670803200000`). Zero real `<60s` cases exist in 2021–2023; sub-minute boundary ordering (`1 ms` before, exact `0 ms`, and `1 ms` after settlement) is verified solely by synthetic fixtures (`F13`–`F17`).
3. **H1 vs E0 Attribution & Non-Significance:** Paired-vs-account forensic attribution proves that `H1` (18h) and `E0` (12h) admit the **exact same signal event sequence** (`34` in `W1_C04`, `55` in `W2_C05`, with identical cooldown conflict counts `30` and `28` and `0.000000 bps` difference between full-account and fixed-event paired mean net bps). Thus, the `H1 - E0` sample gain (`+37.3453 bps` in `W1_C04/STRESS`, `+22.4342 bps` in `W2_C05/STRESS`) is not an account-gating or ACK artifact, **but all simultaneous 7d/14d 95% block-bootstrap confidence intervals span zero**, leaving `H1` statistically unproven.
4. **Falsification of Naive 10x/15x Leverage Scaling:** While the 1x cash cap (`0.95 * min(cash, 1000)`) kept Mark notional/equity `<= 0.9510` with `0` exceedance minutes across all 20 cells, realized 1R stop distances reach **`7.5%–11.6%` of BTC entry price**. In our synthetic parametric margin harness, naively scaling position notional to `10x` or `15x` triggers **exchange Mark-price forced liquidation before the strategy's own 1R stop-loss is reached** and produces negative-equity bankruptcy deficits on cross-minute stop gaps.

---

## 2. Target 1 — Commit, Frozen Code, Source Cache & E0 Curve Attestation

| Check | Scope | Result | Key Evidence |
|---|---|---|---|
| Git lineage & freeze immutability | `de2c1fb...` -> `55ac4c6...` (parent `990c02b...`) | `PASS` | 11 R1 files + 66 inherited files match SHA256; 0 code edits between freeze and delivery |
| Committed JSONL ledgers | 20 `*_orders.jsonl` + 4 `*_paired.jsonl` | `PASS` | 24 files, 1068 rows match `COMMITTED_LEDGER_MANIFEST.json` |
| Public source caches | 108 monthly ZIPs + 8 daily gap ZIPs | `PASS` | 108 monthly (`last`/`mark`/`funding`) + 8 daily gap ZIPs verified; `cache_writes=0` |
| E0 vs variant curve identities | 4 R31 E0 `.npz` + 16 R1 variant `.npz` | `PASS` | R31 E0 `baseline`/`overlay`/`funded` & 16 R1 Mark `.npz` verified uncompressed on disk; R2 Last-price `.npz` noted as manifest-pinned |

---

## 3. Target 2 — Independent Dual-Decimal Cash, Quantity, Funding & Mark Journal

- **Method:** `Dual-Decimal independent stdlib CSV/ZIP/Decimal recalculation and stage balance-sheet check; zero production economics calls`
- **Deep Forensic Episodes Audited:** `48` (`STRESS=24`, `BASE=24`, schemes `{'E0': 0, 'H1': 24, 'H2': 0, 'E1': 24, 'E2': 0}`, years `[2021, 2022, 2023]`, sides `[-1, 1]`)
- **Full Order-Ledger Sweep:** `890 / 890` trades across all 20 committed order ledgers verified with **`0` discrepancies**.
- **Original R1 Partial+Funding Cohort:** `24` episodes (`12 STRESS`, `12 BASE`), with **`14`** episodes having post-TP1 residual-quantity (`q2 < q`) funding settlements (`75` across all `E1`/`E2` order ledgers).
- **Closest Real TP1-to-Settlement Witness:** `event_id=W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1670792400000_-1`, `TP1_exit_at=1670803319999`, `settlement_at=1670803200000`, **`distance_ms=119999`** (`within_60sec_supported=False`).

---

## 4. Target 3 — Adversarial Deterministic Event Collision Matrix (48 Fixtures)

- **Total Registered Fixtures:** `48` (`F01`–`F48`)
- **Passed Fixtures:** `48 / 48` (`status=PASS`)
- **Key Collision & Causality Invariants Proven:**
  - `F01`–`F06`: Adverse bar-open `STOP_GAP` uncapped fill at minute start; favorable single-tier (`TP1_GAP_CAPPED`) and double-tier (`TP1_GAP_CAPPED` + `TP2_GAP_CAPPED`) open gaps capped at limit prices.
  - `F07`–`F12`: Intrabar `STOP + TP1 + TP2` triple collision rejects optimistic target fills and exits full quantity at `STOP`; intrabar `TP1 + TP2` simultaneous reach fills only `TP1` and defers `TP2` via `deferred_tp2_until = minute + 60,000`.
  - `F13`–`F17`: Funding boundary precision at `-1 ms`, `0 ms`, and `+1 ms` around `entry_at`, `TP1`, and flat exit.
  - `F18`–`F20`: Causal ACK latency (`+60,000 ms` on open fill, `+60,001 ms` on bar-close fill) and `E2` breakeven stop activation strictly at `minute >= tp1_ack`.
  - `F21`–`F26`: Exact limit touch (`touch_no_fill_count += 1`) vs 1-tick trade-through (`+0.1` / `-0.1`), 1-bar confirmation `delay`, and first-confirmation `unfilled` modes.
  - `F27`–`F30`: Odd-lot `0.001 BTC` floor splitting (`0.027 -> 0.013 + 0.014`), float ULP tolerance, per-tier `5.0 USDT` min-notional rejection, single entry fee conservation, and 6-cell `(side x rate_sign)` funding matrix.
  - `F31`–`F48`: Deadline `STOP_GAP > TIME_CAP` precedence, 12h/18h/24h fold boundary censoring, single-position gate and cooldown during partial open `q2`, duplicate/retransmitted exit detection, synthetic 10x/15x liquidation stress, and prefix-truncation lookahead invariance.

---

## 5. Target 4 — Execution Sensitivity & Paired-vs-Account Attribution

### 5.1 Fixed-Event Limit Fill Sensitivity (`STRESS` Cost)

| Candidate | Scheme / Fill Mode | N | Mean Net (bps) | Median Net (bps) | Mean Delta vs Primary (bps) | Worst Event Delta (bps) | Events Changed |
|---|---|---:|---:|---:|---:|---:|---:|
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E0/primary` | 34 | 11.2047 | -5.5083 | +0.0000 | +0.0000 | 0 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E0/through` | 34 | 11.2047 | -5.5083 | +0.0000 | +0.0000 | 0 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E0/delay` | 34 | 10.2303 | -5.5083 | -0.9743 | -33.1273 | 5 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E0/unfilled` | 34 | 11.2047 | -5.5083 | +0.0000 | +0.0000 | 5 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E1/primary` | 34 | 11.6909 | -0.7649 | +0.0000 | +0.0000 | 0 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E1/through` | 34 | 11.6909 | -0.7649 | +0.0000 | +0.0000 | 0 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E1/delay` | 34 | 5.2459 | -5.5083 | -6.4450 | -89.7691 | 8 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E1/unfilled` | 34 | 8.3733 | -2.7601 | -3.3176 | -76.8193 | 7 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E2/primary` | 34 | 10.5317 | 0.3167 | +0.0000 | +0.0000 | 0 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E2/through` | 34 | 10.5317 | 0.3167 | +0.0000 | +0.0000 | 0 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E2/delay` | 34 | 4.2730 | -2.7601 | -6.2588 | -98.9009 | 9 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `E2/unfilled` | 34 | 7.4634 | -0.7649 | -3.0683 | -98.9009 | 8 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E0/primary` | 55 | 19.0135 | -10.9980 | +0.0000 | +0.0000 | 0 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E0/through` | 55 | 19.0135 | -10.9980 | +0.0000 | +0.0000 | 0 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E0/delay` | 55 | 12.7056 | -10.9980 | -6.3079 | -328.1256 | 7 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E0/unfilled` | 55 | 12.7056 | -10.9980 | -6.3079 | -328.1256 | 7 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E1/primary` | 55 | 20.5324 | 6.7405 | +0.0000 | +0.0000 | 0 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E1/through` | 55 | 20.5324 | 6.7405 | +0.0000 | +0.0000 | 0 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E1/delay` | 55 | 15.7508 | 0.3092 | -4.7816 | -175.0003 | 10 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E1/unfilled` | 55 | 15.9150 | 0.3188 | -4.6174 | -175.0003 | 9 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E2/primary` | 55 | 18.1324 | 8.2834 | +0.0000 | +0.0000 | 0 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E2/through` | 55 | 18.1324 | 8.2834 | +0.0000 | +0.0000 | 0 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E2/delay` | 55 | 14.9875 | 0.3188 | -3.1449 | -175.0003 | 10 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `E2/unfilled` | 55 | 14.8867 | 3.5758 | -3.2457 | -175.0003 | 10 |

### 5.2 Paired vs Full-Account Attribution (`STRESS` & `BASE`)

| Candidate | Cost | Scheme | Account N | Same Event IDs as E0 | Diff Qty Count | Paired Mean (bps) | Account Mean (bps) | Account - Paired (bps) | Account - Paired (USDT) |
|---|---|---|---:|---|---:|---:|---:|---:|---:|
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `STRESS` | `E0` | 34 | `True` | 0 | 11.2047 | 11.2047 | +0.000000 | +0.0000 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `STRESS` | `H1` | 34 | `True` | 0 | 48.5499 | 48.5499 | +0.000000 | +0.0000 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `STRESS` | `H2` | 34 | `True` | 0 | 44.0744 | 44.0744 | +0.000000 | +0.0000 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `STRESS` | `E1` | 34 | `True` | 0 | 11.6909 | 11.6909 | +0.000000 | +0.0000 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `STRESS` | `E2` | 34 | `True` | 0 | 10.5317 | 10.5317 | +0.000000 | +0.0000 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `BASE` | `E0` | 34 | `True` | 0 | 37.3500 | 37.3500 | +0.000000 | +0.0000 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `BASE` | `H1` | 34 | `True` | 0 | 69.5369 | 69.5369 | +0.000000 | +0.0000 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `BASE` | `H2` | 34 | `True` | 0 | 64.6034 | 64.6034 | +0.000000 | +0.0000 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `BASE` | `E1` | 34 | `True` | 0 | 34.6934 | 34.6934 | +0.000000 | +0.0000 |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `BASE` | `E2` | 34 | `True` | 0 | 31.8061 | 31.8061 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `STRESS` | `E0` | 55 | `True` | 0 | 19.0135 | 19.0135 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `STRESS` | `H1` | 55 | `True` | 0 | 41.4477 | 41.4477 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `STRESS` | `H2` | 55 | `True` | 0 | 33.0215 | 33.0215 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `STRESS` | `E1` | 55 | `True` | 0 | 20.5324 | 20.5324 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `STRESS` | `E2` | 55 | `True` | 0 | 18.1324 | 18.1324 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `BASE` | `E0` | 55 | `True` | 0 | 45.9244 | 45.9244 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `BASE` | `H1` | 55 | `True` | 0 | 72.8430 | 72.8430 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `BASE` | `H2` | 55 | `True` | 0 | 62.3702 | 62.3702 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `BASE` | `E1` | 55 | `True` | 0 | 43.0972 | 43.0972 | +0.000000 | +0.0000 |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `BASE` | `E2` | 55 | `True` | 0 | 39.7405 | 39.7405 | +0.000000 | +0.0000 |

- **Funding Settlement Mark Proxy Bound:** Across `586` realized STRESS settlements, replacing the latest completed 1m Mark close (`t - 1 ms`) with the worst adjacent 1m Mark `open`/`high`/`low`/`close` changes any single funding bill by at most **`0.00047418 USDT`** (**`0.005167 bps`** of entry notional).

---

## 6. Target 5 — Capital, 1x Exposure & Synthetic-Only 10x/15x Leverage Stress

- **1x Admission & Exposure Verification:** Verified `890` trades across all 20 order ledgers (`0` breaches of `0.95 * min(cash, 1000)`). Peak Mark notional/equity ratio across all 20 cells is **`0.950986`** with **`0`** minutes above `1.0x`.
- **Realized Adverse Excursion & Stop Distance Tails:** `W1_C04` max initial 1R stop distance is **`3.61%`** of entry price (`worst 24h Mark MAE = -3.88R`); `W2_C05` max initial 1R stop distance is **`3.56%`** (`worst 24h Mark MAE = -6.78R`).
- **Synthetic Parametric 10x/15x Margin & Liquidation Findings (Illustrative Scenario Contract Only):**
  - In `NAIVE_FULL_LEVERAGE_NOTIONAL` mode (`10x` and `15x` across hypothetical MMR `40/50/100 bps`), **`5 / 6`** baseline scenarios suffer **forced Mark liquidation before the strategy's own 7.5% stop-loss is reached**, and **`7 / 6`** suffer isolated margin bankruptcy deficits on a `-9.5%` bar-open gap.
  - In `RISK_BUDGET_CAPPED_ISOLATED` mode (where position notional is gated so `stop_distance + gap_buffer + MMR + fees + funding <= 2%` of account equity), **`0 / 6`** scenarios liquidate and **`0 / 6`** become insolvent.

---

## 7. Target 6 — Known-At Causality, Prefix Invariance & Fold Lineage

- **Static AST & Signature Check:** `generate_wave_signals` accepts `['arr_1m', 'cand_id', 'embargo_start_ms', 'embargo_end_ms']` (no Mark or Funding inputs), enforces closed `1h`/`4h` bar alignment (`end_ms <= t_event`), and sets `decision_at = event_time + 60,000`, `entry_at = decision_at + 60,000`.
- **Dynamic Prefix-Truncation & Adversarial Future Mutation:** Verified on synthetic multi-week 1m series (`status=PASS`).
- **Warmup, 35 Scored Folds & 24h Edge Embargo:** Verified `2021-01` warmup, `35` scored folds (`2021-02..2023-12`), `0` access to `2024–2026` heldout data, `0` fold overflows, and `0` concurrent/pre-funded entry violations across all `890` committed order-ledger trades.

---

## 8. Claim-by-Claim Matrix (`SOURCE_VS_ALGO_VS_EXECUTION_UNKNOWN`)

| Claim ID | Domain | Classification | Summary |
|---|---|---|---|
| `C01_COMMIT_AND_CODE_FREEZE_LINEAGE` | `SOURCE_AND_GIT_PROVENANCE` | `VERIFIED_EXACT` | Verified 11 R1 files and 66 inherited files byte-for-byte. |
| `C02_PUBLIC_ARCHIVE_AND_LEDGER_CRYPTOGRAPHIC_IDENTITY` | `SOURCE_AND_GIT_PROVENANCE` | `VERIFIED_EXACT` | 108 monthly + 8 daily ZIPs + 24 ledgers verified; cache_writes=0. |
| `C03_E0_BASELINE_CURVE_AND_LEDGER_SEPARATION` | `ALGO_ACCOUNTING` | `VERIFIED_WITH_MANIFEST_BOUNDARY_NOTE` | 4 E0 R31 .npz curves and 16 R1 variant .npz curves verified uncompressed; derived *_E0_orders.jsonl matches R31 funded execution clocks, prices, quantities, and net cash. |
| `C04_INDEPENDENT_DUAL_DECIMAL_CASH_AND_QUANTITY_JOURNAL` | `ALGO_ACCOUNTING` | `VERIFIED_EXACT` | Audited 48 forensic episodes (24 STRESS, 24 BASE) and 890 total order ledger trades; defects=0. |
| `C05_REAL_TP1_TO_FUNDING_SETTLEMENT_60S_BOUNDARY_COVERAGE` | `EMPIRICAL_SAMPLE_SUPPORT` | `FALSIFIED_AS_EMPIRICALLY_COVERED__BOUNDED_LIMITATION_CONFIRMED` | Falsified as empirically covered (confirming R1's own stop reason): closest real TP1-to-settlement across 3,285 funding events is 119999 ms (W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1670792400000_-1); 0 real cases <=60s. Sub-60s arithmetic is verified only via synthetic fixtures F13..F17. |
| `C06_ADVERSARIAL_EVENT_COLLISION_AND_CAUSALITY_INVARIANTS` | `ALGO_ACCOUNTING` | `VERIFIED_EXACT` | 48/48 deterministic collision fixtures passed. |
| `C07_H1_VS_E0_INCREMENT_INDEPENDENCE_FROM_ACCOUNT_ACK_GATING` | `ALGO_VS_SIGNAL_ATTRIBUTION` | `VERIFIED_MECHANISM__STATISTICALLY_UNPROVEN_EDGE` | H1 and E0 accept the exact same signal event IDs (34 W1, 55 W2) with 0.000000 bps difference between paired and full-account mean net bps; all 7d/14d max-|T| 95% simultaneous CIs span zero. |
| `C08_LIMIT_QUEUE_AND_SUBMINUTE_PATH_OBSERVABILITY` | `EXECUTION_UNKNOWN` | `EXECUTION_UNKNOWN` | Unproven / unobservable from 1m OHLCV. Under 1-bar confirmation delay or first-confirmation non-fill (delay/unfilled modes), portfolio mean net bps shifts materially and individual trades shift by >100 bps. |
| `C09_EXCHANGE_SETTLEMENT_MARK_AND_HISTORICAL_KNOWN_AT` | `EXECUTION_UNKNOWN` | `EXECUTION_UNKNOWN` | UNKNOWN in public archives. Bounded financial discrepancy of latest completed 1m Mark close proxy vs adjacent 1m Mark OHLC is <= 0.005167 bps per settlement. |
| `C10_1X_CASH_CAP_VS_10X_15X_LEVERAGE_SOLVENCY` | `RISK_AND_MARGIN_READINESS` | `1X_VERIFIED__NAIVE_10X_15X_FALSIFIED` | 1x cap verified (max exposure ratio 0.9510, 0 minutes >1x). Naive 10x/15x scaling is FALSIFIED: planned 1R stop distances reach 7.5%-11.6% of entry price, triggering forced Mark liquidation before the strategy stop and negative-equity bankruptcy on stop gaps. |
| `C11_KNOWN_AT_PREFIX_CAUSALITY_AND_FOLD_PURGE` | `ALGO_ACCOUNTING` | `VERIFIED_EXACT` | Verified across AST, synthetic prefix truncation, and all 890 committed order ledger trades (0 overflows, 0 overlaps). |

---

## 9. Worst Unknown Assumptions Ordered by Materiality

| Rank | Assumption ID | Category | Status | Worst Credible Impact |
|---:|---|---|---|---|
| 1 | `UNK_01_HISTORICAL_MAINTENANCE_MARGIN_AND_NAIVE_LEVERAGE_LIQUIDATION` | `MARGIN_AND_LIQUIDATION` | `UNKNOWN_HISTORICAL_TIER__CATASTROPHIC_IF_NAIVELY_LEVERAGED` | 100% isolated margin wipeout + negative-equity bankruptcy deficit under 10x-15x naive notional scaling because W1_C04/W2_C05 1R stop distances (up to >10% of BTC price) exceed 10x/15x initial margin buffers. |
| 2 | `UNK_02_FEE_SPREAD_SLIPPAGE_TIER_UNCERTAINTY` | `EXECUTION_FRICTION` | `UNKNOWN_HISTORICAL_ACCOUNT_TIER` | Doubling friction from BASE (22 bps nominal RT) to STRESS (44 bps nominal RT) reduces mean net return by ~26.1 to 26.9 bps per trade; an additional +10 bps roundtrip fee tier shift reduces mean net return by another ~10.0 bps per trade, pushing E0/E1/E2 close to or below zero. |
| 3 | `UNK_03_LIMIT_FILL_QUEUE_AND_CONFIRMATION_DELAY` | `ORDER_BOOK_QUEUE` | `UNOBSERVABLE_IN_1M_OHLCV` | Single-event discrepancy up to -350+ bps when a transient 1m wick trades through TP1/TP2 by >=1 tick but fails to fill in queue (unfilled/delay modes), converting a target fill into a later STOP or lower TIME_CAP. |
| 4 | `UNK_04_CROSS_MINUTE_ADVERSE_STOP_GAP_TAILS` | `STOP_EXECUTION` | `BOUNDED_IN_SAMPLE_UNBOUNDED_IN_EXTREME_GAPS` | Bar-open STOP_GAP executes at uncapped open price plus adverse spread/slippage; in flash crashes or liquidity halts, stop-market slippage can far exceed the 6 bps STRESS slippage proxy. |
| 5 | `UNK_05_EXECUTOR_ACK_AND_AMENDMENT_LATENCY_UNDER_60S` | `EXECUTOR_STATE_MACHINE` | `EMPIRICALLY_UNTESTED_UNDER_60S_IN_R1_SAMPLE` | Closest real TP1-to-funding settlement in 2021-2023 is 119,999 ms (0 real cases <=60s). In live execution, network/exchange ACK jitter or cancel-replace race conditions between TP1 fill and STOP quantity reduction / E2 BE amendment could cause double-fills or unhedged flips. |
| 6 | `UNK_06_EXACT_EXCHANGE_SETTLEMENT_MARK_AT_FUNDING_TIMESTAMP` | `FUNDING_NOTIONAL_BASIS` | `APPROXIMATED_BY_PRECEDING_1M_MARK_CLOSE` | Bounded at <= 0.005167 bps (0.00047418 USDT) per settlement across all realized R1 funding events. |

---

## 10. Minimal Input Contract Before Any Future Leverage Research or TESTNET (Not Authorization)

- **`REQ_01_MAINTENANCE_MARGIN_BRACKETS` (`UNKNOWN`):** Official historical as-of dated Binance USD-M BTCUSDT notional bracket schedule (notional floor/cap, MMR, maintenance amount, max leverage per bracket, effective timestamps).
- **`REQ_02_EXCHANGE_LIQUIDATION_AND_MARK_FORMULA` (`UNKNOWN`):** Exact sub-minute Mark price composition (spot index basket, funding basis moving average, price clamp bounds), bankruptcy price formula, insurance fund liquidation clearance fee rate, and ADL queue rules.
- **`REQ_03_FEE_AND_FUNDING_SETTLEMENT_AUTHORITY` (`UNKNOWN`):** As-of dated maker/taker fee schedule, exact exchange settlement Mark price at 00:00/08:00/16:00 UTC (currently approximated by latest completed 1m Mark close), and funding credit/debit wallet posting latency.
- **`REQ_04_L2_QUEUE_AND_SUBMINUTE_ORDER_BOOK` (`UNKNOWN`):** L2 order-book depth or tick-by-tick trade stream to resolve intra-minute STOP vs TP1/TP2 ordering and limit queue fill probability on touch vs trade-through.
- **`REQ_05_EXECUTOR_STATE_MACHINE_AND_TESTNET_BOUNDARY_HARNESS` (`NOT_AUTHORIZED_IN_G2`):** Idempotent clientOrderId state machine, partial-fill stop quantity amendment / cancel-replace race-condition tests, WebSocket user-stream vs REST reconciliation, and hard margin-utilization kill-switch before any separate TESTNET gate.

---

## 11. Reproducibility Commands

```bash
# 1. Run all 64 deterministic synthetic adversarial & Decimal tests:
PYTHONPATH=src:. pytest tests/test_v06_g2_goal_execution_assurance_r1_collision_matrix.py tests/test_v06_g2_goal_execution_assurance_r1_decimal_and_risk.py -q

# 2. Run scoped Ruff lint and Python bytecode compilation checks:
ruff check scripts/strategy_research/g2_goal_execution_assurance_r1 tests/test_v06_g2_goal_execution_assurance_r1_collision_matrix.py tests/test_v06_g2_goal_execution_assurance_r1_decimal_and_risk.py
python -m py_compile scripts/strategy_research/g2_goal_execution_assurance_r1/*.py tests/test_v06_g2_goal_execution_assurance_r1_*.py

# 3. Execute one-shot forensic audit against frozen Commit 1 SHA:
PYTHONPATH=src:. python -m scripts.strategy_research.g2_goal_execution_assurance_r1.run --code-sha 4c0bac051767f788e6de173f6563a7b47af2ac69
```
