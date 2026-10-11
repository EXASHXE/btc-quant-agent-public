# BTC Goal C R2 — Independent Margin, Synthetic Liquidation, and Forensic Audit Truth Repair

- **Task ID:** `V06_G2_GOAL_C_RISK_ASSURANCE_R2`
- **Controller Dispatch SHA:** `1172d3a91324c1a7379bc9e5c24ef601076547c2`
- **Authority:** `https://github.com/EXASHXE/btc-quant-agent-public/blob/1172d3a91324c1a7379bc9e5c24ef601076547c2/reviews/v0.6/b_line/V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md`
- **Repository / Branch:** `EXASHXE/btc-quant-agent-public` / `feature/v06-bline-gemini-goal-c-risk-assurance-r2`
- **Exact Start SHA (`C_R1_FINAL_SHA`):** `f381dd73a8c583e2a28dcab2e354b019b1d946fa`
- **Frozen Method Commit SHA (`COMMIT1`):** `0aa7c2fd8457ea64b343239ff7bc4c08d3c56b3f` (parent `f381dd73a8c583e2a28dcab2e354b019b1d946fa`)
- **Original Exit R1 Frozen / Final SHAs:** `de2c1fb222970a93ca797868b91b8544261ebaad` / `55ac4c631c69f6edbd275462ad23e4486b9782ed`
- **Goal C R1 3-Commit Chain Audited:** `8db2e3ff36011c6a65458f8cf4c2ba5e90d5fee2` -> `4c0bac051767f788e6de173f6563a7b47af2ac69` -> `f381dd73a8c583e2a28dcab2e354b019b1d946fa`
- **Terminal Decision:** **`C_R2_MARGIN_RISK_EVIDENCE_RECONCILED_SYNTHETIC_ONLY`**

---

## 1. Executive Contradiction Disposition Matrix

| Claim ID | Audited Subject | Disposition | Exact Machine Witness |
| :--- | :--- | :--- | :--- |
| `CLAIM_01_C_R1_FREEZE_AND_TWO_COMMIT_DISCIPLINE` | Goal C R1 commit chain (`8db2e3f -> 4c0bac0 -> f381dd7`) and CI run `38162845456` | **`POST_FREEZE_REPAIR_NOT_PREACCEPTED`** | C R1 made 3 commits instead of <=2 (`8db2e3f -> 4c0bac0 -> f381dd7`). Static byte/AST diff proves `4c0bac0` modified only `attestation.py:verify_public_source_caches`, `run.py:verify_freeze_commit`, and `EXECUTION_ASSURANCE_R1_FROZEN_CONTRACT.json` while all 6 economic modules and both test files had 0 byte changes. Final CI `38162845456` ran in `docs-only` mode with pytest/Ruff/mypy skipped. |
| `CLAIM_02_C_R1_E0_ZERO_EXPOSURE_CELL_SUMMARIES` | Goal C R1 `SYNTHETIC_MARGIN_AND_LEVERAGE_STRESS.json` `cell_exposure_summaries` for E0 | **`INVALID`** | C R1 reported `peak_mark_notional_to_equity_ratio = 0.0` for all 4 E0 cells due to a dictionary key lookup bug (`peak_exposure_ratio` vs `marked_exposure_ratio`). Independent Decimal reconstruction from read-only `*_E0_orders.jsonl` and 1m Mark bars proves E0 peak exposure ratios are W1/BASE=0.940370, W1/STRESS=0.943953, W2/BASE=0.934337, W2/STRESS=0.935323, matching R3.1 `.npz` curves within 5.68e-13 USDT. |
| `CLAIM_03_ALL_20_CELLS_1X_EXPOSURE_BOUND_AND_5PCT_RESERVE_GATE` | Exit R1 20-cell 1x cash account (`0.95 * min(cash, 1000)` reserve gate, 0 minutes > 1x) | **`ACCEPTED`** | Across all 20 cells (890 trades), 5% reserve breaches = 0, minutes with Notional/MarkEquity > 1.0 = 0, and peak ratio across all 20 cells is 0.950986 (in [0.932318, 0.950986]). |
| `CLAIM_04_C_R1_HISTORICAL_STOP_DISTANCE_7_5_TO_11_6_PCT_AND_15X_STRING` | Goal C R1 human report (`7.5%-11.6%` 1R stop) and machine string (`3.61%` exceeds 15x margin) | **`INVALID`** | Actual 2021-2023 initial 1R stop distances have max 3.6120% (W1, median 1.6507%) and 3.5591% (W2, median 1.4270%). C R1 conflated unstopped 24h Mark MAE excursion (up to 11.5861% W1 / 10.6083% W2) and synthetic 7.5% stops with historical 1R stop distances. Moreover, under 40-100 bps MMR + 75 bps clearance + STRESS fees/funding, the 15x liquidation threshold is 4.43%-5.02% > 3.6120%, so a 3.6120% stop move alone does NOT exceed 15x margin unless an intrabar Mark wick exceeds ~4.43%-5.02% or combined non-price buffers exceed 3.0547% (305.47 bps). |
| `CLAIM_05_C_R1_IMPOSSIBLE_7_OVER_6_INSOLVENCY_AND_RISK_CAPPED_SOLVENCY` | Goal C R1 human report (`5/6` liquidations, `7/6` insolvencies) and `RISK_BUDGET_CAPPED_ISOLATED` | **`INVALID`** | C R1's `naive_10x_15x` filter matched Y=10 scenarios (6 from Loop 1 + 4 from Loop 2), yielding 5/10 pre-stop liquidations and 7/10 isolated gap deficits, which `run.py` divided by a hardcoded `/ 6`. Furthermore, C R1's `RISK_BUDGET_CAPPED_ISOLATED` topped up posted margin above `N/L` (~11.5%-12.1% of notional, reducing 15x to ~8.3x-8.7x); under strict `M0 = N/L`, 3/6 risk-capped 10x/15x scenarios still liquidate on the 6.8% Mark shock. |
| `CLAIM_06_EVENT_BOOK_FEE_FUNDING_ASOF_MARK_AND_ACK_CONSISTENCY` | Exit R1 890 order-ledger trades and 24 independently re-audited deep episodes | **`ACCEPTED`** | All 890 order-ledger trades and 24 stratified deep episodes pass independent Decimal recomputation with max diff 6.00e-12 USDT, strict `close_at <= settlement_at` as-of Mark causality, +50% future Mark perturbation invariance, and post-TP1 funding strictly on remaining quantity `q_rem = q - q1`. |
| `CLAIM_07_HISTORICAL_EXCHANGE_MAINTENANCE_TIERS_L2_QUEUE_AND_LIVE_SAFETY` | Historical 2021-2023 Binance maintenance margin brackets, L2 limit queue, and settlement Mark | **`UNKNOWN`** | Exact historical as-of Binance notional bracket schedules, sub-minute spot-index/basis settlement Mark at 00:00/08:00/16:00 UTC, and L2 limit maker queue depth are not present in 1m OHLCV archives. All 56 C R2 margin scenarios are synthetic-only and never authorize leveraged trading or TESTNET/LIVE deployment. |

---

## 2. C0 & C2.5 — Goal C R1 Three-Commit Freeze Provenance and CI Skip Audit

- **Procedural Freeze Status of Goal C R1:** **`POST_FREEZE_REPAIR_NOT_PREACCEPTED`**
- **Commit Chain Verified:** `55ac4c631c` -> `8db2e3ff36` (Freeze) -> `4c0bac0517` (Mid-Repair) -> `f381dd73a8` (Evidence).
- **Files Changed in Middle Repair (`8db2e3ff..4c0bac05`):** `evidence/v0.6/b_line/g2_goal_execution_assurance_r1/EXECUTION_ASSURANCE_R1_FROZEN_CONTRACT.json, scripts/strategy_research/g2_goal_execution_assurance_r1/attestation.py, scripts/strategy_research/g2_goal_execution_assurance_r1/run.py`
- **Untouched Code/Test Modules (`8` of `10`):**

| File Path | SHA-256 at Freeze (`8db2e3ff`) | SHA-256 at Repair (`4c0bac05`) | Byte Identical | Changed AST Symbols |
| :--- | :--- | :--- | :--- | :--- |
| `scripts/strategy_research/g2_goal_execution_assurance_r1/__init__.py` | `00ba69bd82e4a57c...` | `00ba69bd82e4a57c...` | `True` | `NONE` |
| `scripts/strategy_research/g2_goal_execution_assurance_r1/attestation.py` | `d7d0c5757229526d...` | `4a5b262f5f7f98ca...` | `False` | `verify_public_source_caches` |
| `scripts/strategy_research/g2_goal_execution_assurance_r1/collision_matrix.py` | `d39a7fb9d7368738...` | `d39a7fb9d7368738...` | `True` | `NONE` |
| `scripts/strategy_research/g2_goal_execution_assurance_r1/decimal_journal.py` | `0cee8baa432c40e2...` | `0cee8baa432c40e2...` | `True` | `NONE` |
| `scripts/strategy_research/g2_goal_execution_assurance_r1/execution_sensitivity.py` | `ad65a773444e2c61...` | `ad65a773444e2c61...` | `True` | `NONE` |
| `scripts/strategy_research/g2_goal_execution_assurance_r1/lineage_audit.py` | `cac6aa9f4b930567...` | `cac6aa9f4b930567...` | `True` | `NONE` |
| `scripts/strategy_research/g2_goal_execution_assurance_r1/risk_envelope.py` | `e852402291040bc4...` | `e852402291040bc4...` | `True` | `NONE` |
| `scripts/strategy_research/g2_goal_execution_assurance_r1/run.py` | `071aaa32512aa308...` | `07dc7567c7be2f35...` | `False` | `verify_freeze_contract` |
| `tests/test_v06_g2_goal_execution_assurance_r1_collision_matrix.py` | `600a471d1f3fc2ea...` | `600a471d1f3fc2ea...` | `True` | `NONE` |
| `tests/test_v06_g2_goal_execution_assurance_r1_decimal_and_risk.py` | `17e7ed008fa23fef...` | `17e7ed008fa23fef...` | `True` | `NONE` |

### GitHub Actions CI Run `38162845456` Truth Disclosure
- **CI Run ID:** `38162845456` on HEAD `f381dd73a8c583e2a28dcab2e354b019b1d946fa`
- **Change-Filter Mode:** `docs-only`
- **Executed Jobs:** `change-filter, docs-lint`
- **Skipped Jobs:** `lint-and-typecheck, unit-tests` (`pytest_executed=False`, `ruff_executed=False`, `mypy_executed=False`)
- **Read-Only Source & Ledger Admission:** Verified `24` Exit R1 ledgers (`890` order rows, `178` paired rows), `108` monthly public ZIPs, `8` daily gap ZIPs, `4` R3.1 E0 `.npz` curves, and `16` Exit R1 `.npz` curves.

---

## 3. C2.1 — Reconciliation of All 32 Goal C R1 Synthetic Margin Scenarios & Denominators

- **C R1 Summary Findings Status:** **`INVALID__IMPOSSIBLE_7_OVER_6_DENOMINATOR_AND_HIDDEN_DISCRETIONARY_MARGIN_TOPUP`**
- **Row-Level Float vs Pure-Decimal Max Abs Diff Across All 32 Rows:** `0.00000000`
- **Why C R1 Human Report Claimed `5/6` and Impossible `7/6`:** In risk_envelope.py lines 228-232, `naive_10x_15x` filters `scenarios` for `sizing_mode == 'NAIVE_FULL_LEVERAGE_NOTIONAL' and leverage in (10.0, 15.0) and not partial_tp1_before_shock`. That filter matches 10 scenarios out of 32 (6 from Loop 1 `SYN_LEV_*` + 4 from Loop 2 `SYN_PARTIAL_TP1_*_TP1_0`), NOT 6! Across those 10 scenarios, 5 (all five 15x scenarios) have `mark_liquidated_before_strategy_stop=True` (5/10), and 7 (all five 15x scenarios plus two 10x Loop-2 scenarios with 10% gap) have `isolated_margin_bankruptcy_deficit_usdt < 0` (7/10). C R1's `run.py` hardcoded `/ 6` in the Markdown template, producing `5 / 6` and the mathematically impossible `7 / 6`.
- **Hidden Discretionary Margin Top-Up in `RISK_BUDGET_CAPPED_ISOLATED`:** In C R1's `RISK_BUDGET_CAPPED_ISOLATED` mode (lines 91-96 of risk_envelope.py), `initial_margin_posted` was set to `max(N / L, N * per_unit_risk_frac)` (~11.46%-12.06% of notional), which adds a discretionary margin buffer above `N / L` and lowers effective isolated leverage on 15x scenarios to ~8.29x-8.72x. When evaluated at strict exchange initial margin `M0 = N / L` (6.67% at 15x), all 3 of the 15x risk-capped scenarios (`SYN_LEV_15X_MMR_40BP_RISK_`, `SYN_LEV_15X_MMR_50BP_RISK_`, `SYN_LEV_15X_MMR_100BP_RISK_`) STILL liquidate on the 6.8% Mark shock (`3/6` of risk-capped 10x/15x scenarios).

### Audited Grouped Denominators Across C R1's 32 Scenarios (`X / Y` with `0 <= X <= Y`)

| Filter Group | Exact Filtered Count (`Y`) | Mark Liquidated at Shock (`X/Y`) | Mark Liquidated Before Stop (`X/Y`) | Strict `M0=N/L` Liquidated Before Stop (`X/Y`) | Isolated Gap Deficit `< 0` (`X/Y`) | Total Account Insolvent `<= 0` (`X/Y`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `all_32_scenarios` | `32` | `5/32` | `5/32` | `8/32` | `7/32` | `5/32` |
| `all_1x_5x_scenarios` | `12` | `0/12` | `0/12` | `0/12` | `0/12` | `0/12` |
| `naive_1x_5x_scenarios` | `6` | `0/6` | `0/6` | `0/6` | `0/6` | `0/6` |
| `risk_capped_1x_5x_scenarios` | `6` | `0/6` | `0/6` | `0/6` | `0/6` | `0/6` |
| `naive_10x_15x_no_tp1_c_r1_filter` | `10` | `5/10` | `5/10` | `5/10` | `7/10` | `5/10` |
| `naive_10x_15x_loop1_only_6_cases` | `6` | `3/6` | `3/6` | `3/6` | `3/6` | `3/6` |
| `naive_10x_15x_loop2_partial_tp1_false_4_cases` | `4` | `2/4` | `2/4` | `2/4` | `4/4` | `2/4` |
| `naive_10x_15x_loop2_partial_tp1_true_4_cases` | `4` | `0/4` | `0/4` | `0/4` | `0/4` | `0/4` |
| `naive_10x_15x_all_14_cases` | `14` | `5/14` | `5/14` | `5/14` | `7/14` | `5/14` |
| `risk_capped_10x_15x_6_cases` | `6` | `0/6` | `0/6` | `3/6` | `0/6` | `0/6` |

### Complete 32-Row C R1 Scenario Truth Table (Observed vs Pure Decimal Recomputed)

| Row | Scenario ID | Mode | Lev | MMR | Side | TP1 | Strict `N/L` Margin | Posted Margin | Eff Iso Lev | Liq Move % (Posted / Strict) | Liq Before Stop (Posted / Strict) | Iso Gap Deficit USDT | Total Equity After Gap USDT | Max Diff |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0 | `SYN_LEV_1X_MMR_40BP_NAIVE` | `NAIVE_FULL_` | `1x` | `0.004` | `1` | `False` | `930.00` | `930.00` | `1.00x` | `99.70% / 99.70%` | `False / False` | `0.00` | `907.01` | `0.000000` |
| 1 | `SYN_LEV_1X_MMR_40BP_RISK_` | `RISK_BUDGET` | `1x` | `0.004` | `1` | `False` | `150.00` | `150.00` | `1.00x` | `99.70% / 99.70%` | `False / False` | `0.00` | `985.00` | `0.000000` |
| 2 | `SYN_LEV_1X_MMR_50BP_NAIVE` | `NAIVE_FULL_` | `1x` | `0.005` | `1` | `False` | `930.00` | `930.00` | `1.00x` | `99.70% / 99.70%` | `False / False` | `0.00` | `907.01` | `0.000000` |
| 3 | `SYN_LEV_1X_MMR_50BP_RISK_` | `RISK_BUDGET` | `1x` | `0.005` | `1` | `False` | `150.00` | `150.00` | `1.00x` | `99.70% / 99.70%` | `False / False` | `0.00` | `985.00` | `0.000000` |
| 4 | `SYN_LEV_1X_MMR_100BP_NAIVE` | `NAIVE_FULL_` | `1x` | `0.010` | `1` | `False` | `930.00` | `930.00` | `1.00x` | `99.69% / 99.69%` | `False / False` | `0.00` | `907.01` | `0.000000` |
| 5 | `SYN_LEV_1X_MMR_100BP_RISK_` | `RISK_BUDGET` | `1x` | `0.010` | `1` | `False` | `150.00` | `150.00` | `1.00x` | `99.69% / 99.69%` | `False / False` | `0.00` | `985.00` | `0.000000` |
| 6 | `SYN_LEV_5X_MMR_40BP_NAIVE` | `NAIVE_FULL_` | `5x` | `0.004` | `1` | `False` | `948.00` | `948.00` | `5.00x` | `18.58% / 18.58%` | `False / False` | `0.00` | `526.03` | `0.000000` |
| 7 | `SYN_LEV_5X_MMR_40BP_RISK_` | `RISK_BUDGET` | `5x` | `0.004` | `1` | `False` | `30.00` | `30.00` | `5.00x` | `18.58% / 18.58%` | `False / False` | `0.00` | `985.00` | `0.000000` |
| 8 | `SYN_LEV_5X_MMR_50BP_NAIVE` | `NAIVE_FULL_` | `5x` | `0.005` | `1` | `False` | `948.00` | `948.00` | `5.00x` | `18.50% / 18.50%` | `False / False` | `0.00` | `526.03` | `0.000000` |
| 9 | `SYN_LEV_5X_MMR_50BP_RISK_` | `RISK_BUDGET` | `5x` | `0.005` | `1` | `False` | `30.00` | `30.00` | `5.00x` | `18.50% / 18.50%` | `False / False` | `0.00` | `985.00` | `0.000000` |
| 10 | `SYN_LEV_5X_MMR_100BP_NAIVE` | `NAIVE_FULL_` | `5x` | `0.010` | `1` | `False` | `948.00` | `948.00` | `5.00x` | `18.09% / 18.09%` | `False / False` | `0.00` | `526.03` | `0.000000` |
| 11 | `SYN_LEV_5X_MMR_100BP_RISK_` | `RISK_BUDGET` | `5x` | `0.010` | `1` | `False` | `30.00` | `30.00` | `5.00x` | `18.09% / 18.09%` | `False / False` | `0.00` | `985.00` | `0.000000` |
| 12 | `SYN_LEV_10X_MMR_40BP_NAIVE` | `NAIVE_FULL_` | `10x` | `0.004` | `1` | `False` | `948.00` | `948.00` | `10.00x` | `8.45% / 8.45%` | `False / False` | `0.00` | `52.07` | `0.000000` |
| 13 | `SYN_LEV_10X_MMR_40BP_RISK_` | `RISK_BUDGET` | `10x` | `0.004` | `1` | `False` | `15.00` | `16.75` | `8.95x` | `9.63% / 8.45%` | `False / False` | `0.00` | `985.00` | `0.000000` |
| 14 | `SYN_LEV_10X_MMR_50BP_NAIVE` | `NAIVE_FULL_` | `10x` | `0.005` | `1` | `False` | `948.00` | `948.00` | `10.00x` | `8.35% / 8.35%` | `False / False` | `0.00` | `52.07` | `0.000000` |
| 15 | `SYN_LEV_10X_MMR_50BP_RISK_` | `RISK_BUDGET` | `10x` | `0.005` | `1` | `False` | `15.00` | `16.91` | `8.87x` | `9.64% / 8.35%` | `False / False` | `0.00` | `985.00` | `0.000000` |
| 16 | `SYN_LEV_10X_MMR_100BP_NAIVE` | `NAIVE_FULL_` | `10x` | `0.010` | `1` | `False` | `948.00` | `948.00` | `10.00x` | `7.89% / 7.89%` | `False / False` | `0.00` | `52.07` | `0.000000` |
| 17 | `SYN_LEV_10X_MMR_100BP_RISK_` | `RISK_BUDGET` | `10x` | `0.010` | `1` | `False` | `15.00` | `17.66` | `8.50x` | `9.69% / 7.89%` | `False / False` | `0.00` | `985.00` | `0.000000` |
| 18 | `SYN_LEV_15X_MMR_40BP_NAIVE` | `NAIVE_FULL_` | `15x` | `0.004` | `1` | `False` | `950.00` | `950.00` | `15.00x` | `5.07% / 5.07%` | `True / True` | `-474.90` | `-424.90` | `0.000000` |
| 19 | `SYN_LEV_15X_MMR_40BP_RISK_` | `RISK_BUDGET` | `15x` | `0.004` | `1` | `False` | `10.00` | `16.75` | `8.95x` | `9.63% / 5.07%` | `False / True` | `0.00` | `985.00` | `0.000000` |
| 20 | `SYN_LEV_15X_MMR_50BP_NAIVE` | `NAIVE_FULL_` | `15x` | `0.005` | `1` | `False` | `950.00` | `950.00` | `15.00x` | `4.97% / 4.97%` | `True / True` | `-474.90` | `-424.90` | `0.000000` |
| 21 | `SYN_LEV_15X_MMR_50BP_RISK_` | `RISK_BUDGET` | `15x` | `0.005` | `1` | `False` | `10.00` | `16.91` | `8.87x` | `9.64% / 4.97%` | `False / True` | `0.00` | `985.00` | `0.000000` |
| 22 | `SYN_LEV_15X_MMR_100BP_NAIVE` | `NAIVE_FULL_` | `15x` | `0.010` | `1` | `False` | `950.00` | `950.00` | `15.00x` | `4.48% / 4.48%` | `True / True` | `-474.90` | `-424.90` | `0.000000` |
| 23 | `SYN_LEV_15X_MMR_100BP_RISK_` | `RISK_BUDGET` | `15x` | `0.010` | `1` | `False` | `10.00` | `17.66` | `8.50x` | `9.69% / 4.48%` | `False / True` | `0.00` | `985.00` | `0.000000` |
| 24 | `SYN_PARTIAL_TP1_10X_SIDE_1_TP1_0` | `NAIVE_FULL_` | `10x` | `0.005` | `1` | `False` | `948.00` | `948.00` | `10.00x` | `8.35% / 8.35%` | `False / False` | `-47.21` | `4.79` | `0.000000` |
| 25 | `SYN_PARTIAL_TP1_10X_SIDE_-1_TP1_0` | `NAIVE_FULL_` | `10x` | `0.005` | `-1` | `False` | `948.00` | `948.00` | `10.00x` | `8.11% / 8.11%` | `False / False` | `-51.38` | `0.62` | `0.000000` |
| 26 | `SYN_PARTIAL_TP1_10X_SIDE_1_TP1_1` | `NAIVE_FULL_` | `10x` | `0.005` | `1` | `True` | `948.00` | `948.00` | `10.00x` | `18.25% / 18.25%` | `False / False` | `0.00` | `859.90` | `0.000000` |
| 27 | `SYN_PARTIAL_TP1_10X_SIDE_-1_TP1_1` | `NAIVE_FULL_` | `10x` | `0.005` | `-1` | `True` | `948.00` | `948.00` | `10.00x` | `17.74% / 17.74%` | `False / False` | `0.00` | `859.49` | `0.000000` |
| 28 | `SYN_PARTIAL_TP1_15X_SIDE_1_TP1_0` | `NAIVE_FULL_` | `15x` | `0.005` | `1` | `False` | `950.00` | `950.00` | `15.00x` | `4.97% / 4.97%` | `True / True` | `-545.97` | `-495.97` | `0.000000` |
| 29 | `SYN_PARTIAL_TP1_15X_SIDE_-1_TP1_0` | `NAIVE_FULL_` | `15x` | `0.005` | `-1` | `False` | `950.00` | `950.00` | `15.00x` | `4.83% / 4.83%` | `True / True` | `-552.24` | `-502.24` | `0.000000` |
| 30 | `SYN_PARTIAL_TP1_15X_SIDE_1_TP1_1` | `NAIVE_FULL_` | `15x` | `0.005` | `1` | `True` | `950.00` | `950.00` | `15.00x` | `11.46% / 11.46%` | `False / False` | `0.00` | `786.71` | `0.000000` |
| 31 | `SYN_PARTIAL_TP1_15X_SIDE_-1_TP1_1` | `NAIVE_FULL_` | `15x` | `0.005` | `-1` | `True` | `950.00` | `950.00` | `15.00x` | `11.14% / 11.14%` | `False / False` | `0.00` | `786.07` | `0.000000` |

### C R2 Independent 56-Scenario Synthetic Margin/Liquidation Fixture Matrix Summary

| C R2 Fixture Group | Filtered `Y` | Mark Liq at Shock (`X/Y`) | Mark Liq Before Stop (`X/Y`) | Isolated Gap Deficit `< 0` (`X/Y`) | Total Account Insolvent `<= 0` (`X/Y`) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `all_56_c_r2_scenarios` | `56` | `11/56` | `9/56` | `14/56` | `5/56` |
| `group1_naive_1x_5x` | `6` | `0/6` | `0/6` | `0/6` | `0/6` |
| `group1_naive_10x_15x` | `6` | `3/6` | `3/6` | `3/6` | `3/6` |
| `group1_strict_nl_capped_10x_15x` | `6` | `3/6` | `3/6` | `3/6` | `0/6` |
| `group2_real_w1_stop_no_wick` | `4` | `0/4` | `0/4` | `0/4` | `0/4` |
| `group2_real_w1_stop_with_520bp_wick` | `4` | `2/4` | `0/4` | `0/4` | `0/4` |
| `group5_negative_isolated_positive_total_equity` | `9` | `3/9` | `3/9` | `9/9` | `0/9` |
| `group5_total_account_insolvent` | `5` | `5/5` | `5/5` | `5/5` | `5/5` |

---

## 4. C2.2 — Reconstruction of All 20 Exit R1 Account Cells & E0 Positive-Exposure Witnesses

- **Root Cause of C R1 E0 `0.0` Exposure Bug:** In `EXIT_R1_RESULTS.json`, the 4 inherited E0 cells store their monthly peak exposure ratio under key `'marked_exposure_ratio'` and monthly ending equity under `'funded_end'` (inherited from `R31_ECONOMIC_RESULTS.json`), whereas H1/H2/E1/E2 store `'peak_exposure_ratio'` and `'Mark_min_equity'`. C R1's `risk_envelope.py` queried `m.get('peak_exposure_ratio', m.get('max_position_notional_to_marked_equity', 0.0))` and `m.get('Mark_min_equity', m.get('ending_equity', 1000.0))`, silently defaulting all four E0 cells to `0.0` peak exposure and `1000.0` min monthly equity despite 34 (W1) and 55 (W2) executed trades.
- **Global Max Abs Minute Mark Equity Diff vs `.npz` Across All 20 Cells:** `5.68e-13` USDT (tolerance `<= 1e-7`)
- **Global Max Abs Peak Exposure Ratio Diff vs Committed Monthly Records:** `3.38e-16`
- **Total 5% Reserve Gate Breaches Across 890 Trades:** `0`
- **Total Minutes with `Notional / MarkEquity > 1.0` Across All 20 Cells:** `0`

### Four `E0` Cells — Earliest Positive-`q` Witness and Peak-Exposure Witness

| E0 Cell | Trades | Open Mins | Earliest `q>0` Event & Minute | Earliest `q` (BTC) & Ratio | Peak Exposure Event & Minute | Reconstructed Peak Ratio | R3.1/Exit R1 Committed Peak Ratio | NPZ Max Equity Diff |
| :--- | :---: | :---: | :--- | :--- | :--- | :---: | :---: | :---: |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H__BASE__E0` | `34` | `17860` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` @ `2021-04-26T01:46:59Z` | `0.018` BTC (`0.930438`) | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1637028000000_-1` @ `2021-11-16T02:16:59Z` | **`0.94036960`** | `0.94036960` | `5.32e-13` |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H__STRESS__E0` | `34` | `18442` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` @ `2021-04-26T01:46:59Z` | `0.018` BTC (`0.932347`) | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1632482100000_-1` @ `2021-09-24T14:28:59Z` | **`0.94395260`** | `0.94395260` | `5.32e-13` |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H__BASE__E0` | `55` | `31834` | `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_1619401500000_1` @ `2021-04-26T01:46:59Z` | `0.018` BTC (`0.930438`) | `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_1632477600000_-1` @ `2021-09-24T21:06:59Z` | **`0.93433701`** | `0.93433701` | `5.68e-13` |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H__STRESS__E0` | `55` | `32588` | `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_1619401500000_1` @ `2021-04-26T01:46:59Z` | `0.018` BTC (`0.932347`) | `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_1619401500000_1` @ `2021-04-26T13:44:59Z` | **`0.93532303`** | `0.93532303` | `5.32e-13` |

### Complete 20-Cell 1x Account Exposure and Reserve Audit Table

| Candidate | Cost | Scheme | Trades | Open Mins | C R1 Reported Peak | C R2 Reconstructed Peak Ratio | Committed Monthly Peak Ratio | Mins `>1x` | Min Open Mark Eq | Ending Eq | Max MTM DD % | NPZ Max Diff |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `W1_C04` | `BASE` | `E0` | `34` | `17860` | `0.000000` | **`0.940370`** | `0.940370` | `0` | `984.92` | `1116.98` | `7.73%` | `5.32e-13` |
| `W1_C04` | `BASE` | `H1` | `34` | `23382` | `0.943231` | **`0.943231`** | `0.943231` | `0` | `974.41` | `1217.53` | `8.69%` | `5.00e-13` |
| `W1_C04` | `BASE` | `H2` | `34` | `27589` | `0.943105` | **`0.943105`** | `0.943105` | `0` | `977.82` | `1202.89` | `8.29%` | `5.00e-13` |
| `W1_C04` | `BASE` | `E1` | `34` | `17860` | `0.939601` | **`0.939601`** | `0.939601` | `0` | `985.73` | `1108.76` | `7.16%` | `5.36e-13` |
| `W1_C04` | `BASE` | `E2` | `34` | `16706` | `0.939601` | **`0.939601`** | `0.939601` | `0` | `985.73` | `1099.72` | `7.16%` | `5.36e-13` |
| `W1_C04` | `STRESS` | `E0` | `34` | `18442` | `0.000000` | **`0.943953`** | `0.943953` | `0` | `974.85` | `1032.53` | `10.06%` | `5.32e-13` |
| `W1_C04` | `STRESS` | `H1` | `34` | `24100` | `0.950986` | **`0.950986`** | `0.950986` | `0` | `964.36` | `1149.06` | `9.28%` | `5.05e-13` |
| `W1_C04` | `STRESS` | `H2` | `34` | `28308` | `0.947696` | **`0.947696`** | `0.947696` | `0` | `967.76` | `1134.80` | `8.88%` | `4.69e-13` |
| `W1_C04` | `STRESS` | `E1` | `34` | `18442` | `0.942311` | **`0.942311`** | `0.942311` | `0` | `976.57` | `1034.59` | `8.50%` | `5.00e-13` |
| `W1_C04` | `STRESS` | `E2` | `34` | `16879` | `0.942311` | **`0.942311`** | `0.942311` | `0` | `976.57` | `1031.01` | `8.41%` | `5.00e-13` |
| `W2_C05` | `BASE` | `E0` | `55` | `31834` | `0.000000` | **`0.934337`** | `0.934337` | `0` | `995.16` | `1232.86` | `6.16%` | `5.68e-13` |
| `W2_C05` | `BASE` | `H1` | `55` | `42539` | `0.950691` | **`0.950691`** | `0.950691` | `0` | `994.02` | `1368.59` | `6.71%` | `5.29e-13` |
| `W2_C05` | `BASE` | `H2` | `55` | `50295` | `0.934026` | **`0.934026`** | `0.934026` | `0` | `995.16` | `1316.48` | `6.68%` | `5.00e-13` |
| `W2_C05` | `BASE` | `E1` | `55` | `32349` | `0.932318` | **`0.932318`** | `0.932318` | `0` | `995.16` | `1218.56` | `5.18%` | `5.05e-13` |
| `W2_C05` | `BASE` | `E2` | `55` | `28136` | `0.932318` | **`0.932318`** | `0.932318` | `0` | `995.16` | `1201.53` | `5.52%` | `4.68e-13` |
| `W2_C05` | `STRESS` | `E0` | `55` | `32588` | `0.000000` | **`0.935323`** | `0.935323` | `0` | `993.12` | `1096.83` | `9.23%` | `5.32e-13` |
| `W2_C05` | `STRESS` | `H1` | `55` | `44056` | `0.935901` | **`0.935901`** | `0.935901` | `0` | `980.43` | `1209.25` | `6.91%` | `5.17e-13` |
| `W2_C05` | `STRESS` | `H2` | `55` | `52898` | `0.935901` | **`0.935901`** | `0.935901` | `0` | `993.12` | `1165.52` | `7.99%` | `4.88e-13` |
| `W2_C05` | `STRESS` | `E1` | `55` | `33103` | `0.934210` | **`0.934210`** | `0.934210` | `0` | `993.12` | `1103.91` | `7.88%` | `5.00e-13` |
| `W2_C05` | `STRESS` | `E2` | `55` | `28022` | `0.934210` | **`0.934210`** | `0.934210` | `0` | `993.12` | `1091.69` | `9.06%` | `5.03e-13` |

---

## 5. C2.3 — Real 2021–2023 1R Stop Distance Distribution vs Synthetic 7.5% Stop & 10x/15x Liquidation Inequalities

### Empirical 2021–2023 1R Stop Distance vs Unstopped 24h Mark Excursion

| Lead Candidate | Events `n` | Min 1R Stop % | Median 1R Stop % | P90 1R Stop % | Max 1R Stop % | Max Stop Event Witness | Worst Unstopped 24h Mark MAE (R / % of Entry) |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :---: |
| `W1_C04` | `34` | `0.3802%` | `1.6507%` | `3.1234%` | **`3.6120%`** | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `-3.8757R` (`6.4257%`) |
| `W2_C05` | `55` | `0.3536%` | `1.4270%` | `2.5740%` | **`3.5591%`** | `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_1655545500000_-1` | `-6.7750R` (`6.4019%`) |

- **Mathematical Proof Falsifying C R1's 15x String:** At 15x gross leverage, raw initial margin is 1/15 = 6.6667%. Under STRESS costs (22 bps per leg fee+half-spread+slip = 44 bps roundtrip), 8 bps funding, 75 bps clearance, and 40-100 bps MMR, the adverse Mark move to liquidation is 4.4441% to 5.0660% (LONG) and 4.3118% to 4.9961% (SHORT). All strictly exceed historical max 1R stop distances (3.6120% W1, 3.5591% W2) by +0.70% to +1.45% of entry price. A 3.6120% stop move alone triggers liquidation at 15x ONLY if combined non-price buffers (MMR + clearance + fees + funding) exceed 6.6667% - 3.6120% = 3.0547% (305.47 bps), or if an intrabar Mark wick / cross-minute gap exceeds ~4.31%-5.07% before the 1m Last stop executes.

### Closed-Form Decimal Liquidation Threshold Grid (`STRESS` Frictions + `8 bps` Funding + `75 bps` Clearance)

| Leverage | Side | Strict Initial Margin % | Hypothetical MMR (bps) | Liq Price (from 30,000) | Adverse Mark Move to Liq % | Headroom Above W1 Max Stop (`3.6120%`) | Liquidates at `3.6120%` Without Extra Wick? | Liquidates Before Synthetic `7.50%` Stop? |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `1x` | `LONG` | `100.0000%` | `40` | `91.29` | **`99.6957%`** | `+96.0837%` | `False` | `False` |
| `1x` | `SHORT` | `100.0000%` | `40` | `59100.36` | **`97.0012%`** | `+93.3892%` | `False` | `False` |
| `1x` | `LONG` | `100.0000%` | `50` | `91.38` | **`99.6954%`** | `+96.0834%` | `False` | `False` |
| `1x` | `SHORT` | `100.0000%` | `50` | `59042.12` | **`96.8071%`** | `+93.1951%` | `False` | `False` |
| `1x` | `LONG` | `100.0000%` | `100` | `91.85` | **`99.6938%`** | `+96.0818%` | `False` | `False` |
| `1x` | `SHORT` | `100.0000%` | `100` | `58752.61` | **`95.8420%`** | `+92.2300%` | `False` | `False` |
| `5x` | `LONG` | `20.0000%` | `40` | `24424.65` | **`18.5845%`** | `+14.9725%` | `False` | `False` |
| `5x` | `SHORT` | `20.0000%` | `40` | `35424.72` | **`18.0824%`** | `+14.4704%` | `False` | `False` |
| `5x` | `LONG` | `20.0000%` | `50` | `24449.44` | **`18.5019%`** | `+14.8899%` | `False` | `False` |
| `5x` | `SHORT` | `20.0000%` | `50` | `35389.81` | **`17.9660%`** | `+14.3540%` | `False` | `False` |
| `5x` | `LONG` | `20.0000%` | `100` | `24574.15` | **`18.0862%`** | `+14.4742%` | `False` | `False` |
| `5x` | `SHORT` | `20.0000%` | `100` | `35216.28` | **`17.3876%`** | `+13.7756%` | `False` | `False` |
| `10x` | `LONG` | `10.0000%` | `40` | `27466.32` | **`8.4456%`** | `+4.8336%` | `False` | `False` |
| `10x` | `SHORT` | `10.0000%` | `40` | `32465.26` | **`8.2175%`** | `+4.6055%` | `False` | `False` |
| `10x` | `LONG` | `10.0000%` | `50` | `27494.20` | **`8.3527%`** | `+4.7407%` | `False` | `False` |
| `10x` | `SHORT` | `10.0000%` | `50` | `32433.27` | **`8.1109%`** | `+4.4989%` | `False` | `False` |
| `10x` | `LONG` | `10.0000%` | `100` | `27634.43` | **`7.8852%`** | `+4.2732%` | `False` | `False` |
| `10x` | `SHORT` | `10.0000%` | `100` | `32274.23` | **`7.5808%`** | `+3.9688%` | `False` | `False` |
| `15x` | `LONG` | `6.6667%` | `40` | `28480.21` | **`5.0660%`** | `+1.4540%` | `False` | `True` |
| `15x` | `SHORT` | `6.6667%` | `40` | `31478.78` | **`4.9293%`** | `+1.3173%` | `False` | `True` |
| `15x` | `LONG` | `6.6667%` | `50` | `28509.12` | **`4.9696%`** | `+1.3576%` | `False` | `True` |
| `15x` | `SHORT` | `6.6667%` | `50` | `31447.75` | **`4.8258%`** | `+1.2138%` | `False` | `True` |
| `15x` | `LONG` | `6.6667%` | `100` | `28654.53` | **`4.4849%`** | `+0.8729%` | `False` | `True` |
| `15x` | `SHORT` | `6.6667%` | `100` | `31293.55` | **`4.3118%`** | `+0.6998%` | `False` | `True` |

---

## 6. C2.4 — Independent Re-Audit of 24 Stratified Real R1 Episodes and All 890 Order-Ledger Trades

- **Total Committed Order-Ledger Trades Independently Recomputed:** `890` (`failures = 0`, `max_abs_decimal_diff = 6.00e-12` USDT)
- **C R2 Stratified Deep Real Episodes (`24` >= 20 required):** W1=`22`, W2=`2`, STRESS=`9`, BASE=`15`, LONG=`21`, SHORT=`3`, Schemes=`['E0', 'E1', 'E2', 'H1', 'H2']`, Years=`[2021, 2022, 2023]`, Funding Signs=`['NEGATIVE_DEBIT', 'POSITIVE_CREDIT']`, Post-TP1 Reduced-Quantity Funding Cases=`10`.

| # | Candidate | Cost | Scheme | Event ID | Year | Side | Tiers | Settlements | Funding Sign | Post-TP1 Reduced `q` | Lookahead Invariant | Max Decimal Diff |
| :---: | :--- | :---: | :---: | :--- | :---: | :---: | :---: | :---: | :--- | :---: | :---: | :---: |
| 1 | `W1_C04` | `BASE` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1627678800000_1` | `2021` | `1` | `2` | `2` | `NEGATIVE_DEBIT` | `True` | `True` | `4.00e-12` |
| 2 | `W1_C04` | `BASE` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1637028000000_-1` | `2021` | `-1` | `2` | `1` | `POSITIVE_CREDIT` | `True` | `True` | `2.80e-13` |
| 3 | `W1_C04` | `BASE` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1654488000000_1` | `2022` | `1` | `2` | `2` | `NEGATIVE_DEBIT` | `True` | `True` | `3.00e-12` |
| 4 | `W1_C04` | `BASE` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1658953800000_1` | `2022` | `1` | `2` | `2` | `NEGATIVE_DEBIT` | `True` | `True` | `4.86e-13` |
| 5 | `W1_C04` | `BASE` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1674058500000_-1` | `2023` | `-1` | `2` | `1` | `POSITIVE_CREDIT` | `True` | `True` | `3.00e-12` |
| 6 | `W1_C04` | `BASE` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1696610700000_1` | `2023` | `1` | `2` | `1` | `NEGATIVE_DEBIT` | `True` | `True` | `2.00e-12` |
| 7 | `W1_C04` | `BASE` | `E2` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1627678800000_1` | `2021` | `1` | `2` | `2` | `NEGATIVE_DEBIT` | `True` | `True` | `4.00e-12` |
| 8 | `W1_C04` | `BASE` | `E2` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1637028000000_-1` | `2021` | `-1` | `2` | `1` | `POSITIVE_CREDIT` | `True` | `True` | `2.80e-13` |
| 9 | `W1_C04` | `STRESS` | `E0` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `1` | `1` | `NEGATIVE_DEBIT` | `False` | `True` | `4.00e-12` |
| 10 | `W1_C04` | `STRESS` | `H1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `1` | `2` | `NEGATIVE_DEBIT` | `False` | `True` | `4.00e-12` |
| 11 | `W1_C04` | `STRESS` | `H2` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `1` | `3` | `NEGATIVE_DEBIT` | `False` | `True` | `4.00e-12` |
| 12 | `W1_C04` | `STRESS` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `2` | `1` | `NEGATIVE_DEBIT` | `False` | `True` | `4.00e-12` |
| 13 | `W1_C04` | `STRESS` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1627678800000_1` | `2021` | `1` | `2` | `2` | `NEGATIVE_DEBIT` | `True` | `True` | `6.00e-12` |
| 14 | `W1_C04` | `STRESS` | `E2` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `2` | `1` | `NEGATIVE_DEBIT` | `False` | `True` | `4.00e-12` |
| 15 | `W1_C04` | `STRESS` | `E2` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1627678800000_1` | `2021` | `1` | `2` | `2` | `NEGATIVE_DEBIT` | `True` | `True` | `6.00e-12` |
| 16 | `W1_C04` | `BASE` | `E0` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `1` | `1` | `NEGATIVE_DEBIT` | `False` | `True` | `6.46e-13` |
| 17 | `W1_C04` | `BASE` | `H1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `1` | `2` | `NEGATIVE_DEBIT` | `False` | `True` | `8.61e-13` |
| 18 | `W1_C04` | `BASE` | `H2` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `1` | `3` | `NEGATIVE_DEBIT` | `False` | `True` | `2.58e-13` |
| 19 | `W1_C04` | `BASE` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `2` | `1` | `NEGATIVE_DEBIT` | `False` | `True` | `4.04e-13` |
| 20 | `W1_C04` | `BASE` | `E1` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1628190900000_1` | `2021` | `1` | `1` | `1` | `NEGATIVE_DEBIT` | `False` | `True` | `3.30e-14` |
| 21 | `W1_C04` | `BASE` | `E2` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1619401500000_1` | `2021` | `1` | `2` | `1` | `NEGATIVE_DEBIT` | `False` | `True` | `4.04e-13` |
| 22 | `W1_C04` | `BASE` | `E2` | `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H_1628190900000_1` | `2021` | `1` | `1` | `1` | `NEGATIVE_DEBIT` | `False` | `True` | `3.30e-14` |
| 23 | `W2_C05` | `STRESS` | `E0` | `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_1619401500000_1` | `2021` | `1` | `1` | `1` | `NEGATIVE_DEBIT` | `False` | `True` | `4.00e-12` |
| 24 | `W2_C05` | `STRESS` | `H1` | `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H_1619401500000_1` | `2021` | `1` | `1` | `2` | `NEGATIVE_DEBIT` | `False` | `True` | `4.00e-12` |

---

## 7. C2.6 — Explicit Future TESTNET Readiness Prerequisites (Design-Only, Zero Execution)

- **Authorization Status:** `DESIGN_ONLY__NO_TESTNET_OR_LIVE_EXECUTION_AUTHORIZED_IN_G2` (`testnet_connected=False`, `live_exchange_connected=False`)

| Prerequisite ID | Component | Engineering & Exchange-Authority Requirement | Historical 2021–2023 Status |
| :--- | :--- | :--- | :--- |
| `TESTNET_PRE_01_RISK_BRACKET_AND_MMR_SNAPSHOT` | Exchange Risk & Maintenance Bracket Verifier | Query and cryptographically log the active exchange `/fapi/v1/leverageBracket` schedule (notional floor, notional cap, `maintMarginRatio`, `cum` maintenance amount, max allowed leverage) before any session startup; reject startup if bracket parameters are missing or stale. | `UNKNOWN_HISTORICAL_ASOF_SCHEDULE` |
| `TESTNET_PRE_02_ISOLATED_LEVERAGE_AND_POSITION_MODE_GATE` | Account Margin & Position Mode Guard | Explicitly assert and lock `marginType=ISOLATED`, target integer leverage `L`, and `dualSidePosition=false` (One-Way mode) via signed account configuration endpoints before enabling signal admission; forbid cross-margin collateral bleed unless explicitly authorized. | `SIMULATED_1X_CASH_ACCOUNT_ONLY` |
| `TESTNET_PRE_03_REDUCE_ONLY_AND_WORKING_TYPE_STOP_SEMANTICS` | Stop & Take-Profit Order Instruction Builder | All protective stop (`STOP_MARKET`/`STOP`) and partial take-profit (`TAKE_PROFIT`/`LIMIT`) exit orders must set `reduceOnly=true` and explicitly declare `workingType` (`CONTRACT_PRICE` vs `MARK_PRICE`) so that Last-triggered strategy stops and Mark-triggered exchange liquidations have unambiguous trigger telemetry. | `1M_OHLC_LAST_BAR_PROXY_ONLY` |
| `TESTNET_PRE_04_CLIENT_ORDER_ID_IDEMPOTENCY_AND_CANCEL_REPLACE_FSM` | Deterministic Order State Machine | Assign deterministic `newClientOrderId` keys per `(event_id, leg, revision)` and enforce a strict finite-state machine for the TP1 partial fill -> stop quantity amendment (`q -> q - q1`) and break-even price amendment (`stop -> eff_entry`) transition so in-flight cancel-replace races cannot over-close or flip net position. | `INSTANT_1M_BOUNDARY_ACK_MODEL` |
| `TESTNET_PRE_05_ACK_LATENCY_AND_WALLET_CASH_RECONCILIATION` | User-Data Stream & Wallet Cash Gate | Reconcile WebSocket `ORDER_TRADE_UPDATE` and `ACCOUNT_UPDATE` events against REST order status; keep exited notional and realized P&L locked until terminal fill ACK and verified wallet balance update, with hard kill-switch on any unexpected position or margin ratio breach. | `FIXED_1_MINUTE_ACK_DELAY_MODEL` |
| `TESTNET_PRE_06_L2_QUEUE_FILL_AND_FUNDING_SETTLEMENT_LOGGING` | Microstructure & Funding Settlement Recorder | Record top-of-book BBO/L2 depth at order submission/fill timestamps and capture exact exchange `FUNDING_FEE` income records (timestamp, symbol, income, asset, tradeId/info) at 00:00/08:00/16:00 UTC to replace the retrospective 1m Mark close approximation. | `LATEST_COMPLETED_1M_MARK_CLOSE_APPROXIMATION` |

---

## 8. Terminal Disposition

- **Terminal:** **`C_R2_MARGIN_RISK_EVIDENCE_RECONCILED_SYNTHETIC_ONLY`**
- **Scientific & Governance Separation:**
  1. Original Exit R1 1x cash-account ledger arithmetic (`890` trades across `20` cells, `5%` reserve gate, `0` minutes above `1x` Mark equity, peak exposure `0.9323–0.9510` across all 20 cells including reconstructed `E0`) is **ACCEPTED**.
  2. Goal C R1's procedural 3-commit freeze chain is marked **`POST_FREEZE_REPAIR_NOT_PREACCEPTED`** and its final CI `38162845456` is truthfully recorded as **`docs-only` (`pytest`/`Ruff`/`mypy` skipped)**.
  3. Goal C R1's `0.0` `E0` exposure summary, `7.5%–11.6%` historical 1R stop narrative, `3.61% > 15x margin` machine text, `5/6` and `7/6` scenario ratios, and unconditional `RISK_BUDGET_CAPPED_ISOLATED` 15x solvency claims are marked **`INVALID`** and replaced by the exact Decimal truth tables in this reconciliation.
  4. Historical Binance maintenance brackets, L2 limit queues, and exact 8h settlement Mark prices remain **`UNKNOWN`**. All leveraged margin/liquidation results are strictly **`SYNTHETIC_ONLY`**; no strategy promotion, empirical leveraged P&L claim, or TESTNET/LIVE execution is authorized.
