# BTC exit-aware developmental results R3

**Terminal: R3_DEV_NO_GO. Eligible hypotheses: [].**

Freeze `45bf7cc72eb9a870323c5da056fc9287d42b7b22` was remotely verified at 2026-10-12T17:06:55.100883+00:00 before new scoring. Parent `3df7a9a490a06c398d20da57bf19fc48d3b1c74e`. Actual model/effort UNKNOWN.

Exactly 27 frozen hypotheses, BASE and STRESS each; no retuning. All 12 exposed 2021–2023 scored folds and their warmups passed source admission: 24 archives, 1,045,440 rows. Current ZIP hashes match the previous public R2 development manifest. Reserved 2024–2025 reads = 0.

Every PnL below is NET_EX_FUNDING_PROXY with assumed taker fees, spread, slip, tick/lot and hypothetical fills. Mark, actual funding, historical L2/capacity and historical ingress are UNKNOWN. Results are exposed-development hypotheses, not OOS Alpha or trading permission.

Source manifest SHA256 `688f6a7ae3a7d5c492b3f6b3b567c03d13f957f4ed952c787056c4f281be797d`. Measured campaign time 16.759 seconds; 54 candidate/cost rows, 648 independent month books. Repeated candidate trade records are not independent discoveries.

| Cell | BASE N / gross / net bp | STRESS N / gross / net bp | STRESS PF | Max closed+dense DD % | Disposition |
|---|---|---|---:|---:|---|
| A_X0_H08 | 34 / 8.52 / -13.50 | 34 / 10.29 / -33.72 | 0.50 | 2.50 | NO_GO |
| A_X0_H18 | 34 / 20.04 / -1.98 | 34 / 19.97 / -24.03 | 0.68 | 3.06 | NO_GO |
| A_X0_H24 | 34 / 16.72 / -5.31 | 34 / 17.97 / -26.04 | 0.70 | 3.81 | NO_GO |
| A_X1_H08 | 34 / 19.42 / -2.61 | 34 / 24.62 / -19.42 | 0.63 | 2.50 | NO_GO |
| A_X1_H18 | 34 / 14.83 / -7.21 | 34 / 25.92 / -18.15 | 0.71 | 3.06 | NO_GO |
| A_X1_H24 | 34 / 15.64 / -6.41 | 34 / 24.56 / -19.50 | 0.73 | 3.81 | NO_GO |
| A_X2_H08 | 34 / 19.37 / -2.66 | 34 / 21.99 / -22.04 | 0.63 | 2.50 | NO_GO |
| A_X2_H18 | 34 / 21.11 / -0.93 | 34 / 23.19 / -20.85 | 0.69 | 3.05 | NO_GO |
| A_X2_H24 | 34 / 22.56 / 0.52 | 34 / 20.81 / -23.24 | 0.71 | 3.80 | NO_GO |
| B_X0_H08 | 5 / -43.29 / -65.28 | 5 / -40.29 / -84.24 | 0.17 | 1.24 | NO_GO |
| B_X0_H18 | 5 / -18.53 / -40.49 | 5 / -48.66 / -92.62 | 0.16 | 1.24 | NO_GO |
| B_X0_H24 | 5 / -18.53 / -40.49 | 5 / -48.66 / -92.62 | 0.16 | 1.24 | NO_GO |
| B_X1_H08 | 5 / -7.05 / -29.06 | 5 / -51.38 / -95.31 | 0.06 | 1.24 | NO_GO |
| B_X1_H18 | 5 / -7.05 / -29.06 | 5 / -34.35 / -78.25 | 0.14 | 1.24 | NO_GO |
| B_X1_H24 | 5 / -7.05 / -29.06 | 5 / -34.35 / -78.25 | 0.14 | 1.24 | NO_GO |
| B_X2_H08 | 5 / -40.03 / -62.03 | 5 / -46.99 / -90.93 | 0.10 | 1.24 | NO_GO |
| B_X2_H18 | 5 / -33.45 / -55.43 | 5 / -46.62 / -90.51 | 0.03 | 1.24 | NO_GO |
| B_X2_H24 | 5 / -33.45 / -55.43 | 5 / -46.62 / -90.51 | 0.03 | 1.24 | NO_GO |
| C_X0_H08 | 34 / 19.20 / -2.83 | 34 / 21.79 / -22.24 | 0.67 | 2.00 | NO_GO |
| C_X0_H18 | 34 / 4.19 / -17.85 | 34 / 8.60 / -35.45 | 0.57 | 2.00 | NO_GO |
| C_X0_H24 | 34 / -0.02 / -22.06 | 34 / 4.40 / -39.66 | 0.53 | 2.10 | NO_GO |
| C_X1_H08 | 35 / 6.83 / -15.20 | 35 / 10.13 / -33.88 | 0.45 | 2.00 | NO_GO |
| C_X1_H18 | 35 / 0.81 / -21.21 | 35 / 6.17 / -37.83 | 0.43 | 2.00 | NO_GO |
| C_X1_H24 | 35 / 0.64 / -21.38 | 35 / 6.18 / -37.83 | 0.43 | 2.00 | NO_GO |
| C_X2_H08 | 34 / 16.28 / -5.74 | 34 / 15.90 / -28.12 | 0.58 | 2.00 | NO_GO |
| C_X2_H18 | 34 / -2.08 / -24.12 | 34 / -1.86 / -45.91 | 0.44 | 2.00 | NO_GO |
| C_X2_H24 | 34 / -5.72 / -27.77 | 34 / -6.64 / -50.70 | 0.41 | 2.10 | NO_GO |

## Annual and monthly book interpretation

Each cost/candidate/month resets to 1000 USDT. Annual percentages are the mean of four independent month-book returns; they are neither compounded annual ROI nor net USDT on one continuous account. Full 54×12 month rows, all three years, LONG/SHORT and zero-trade groups are in DEVELOPMENT_RESULTS_BASE_STRESS.json.

| STRESS cell | 2021 N / net bp | 2022 N / net bp | 2023 N / net bp |
|---|---|---|---|
| A_X0_H08 | 7 / 13.43 | 14 / -72.87 | 13 / -16.94 |
| A_X0_H18 | 7 / -59.73 | 14 / -38.09 | 13 / 10.32 |
| A_X0_H24 | 7 / -91.59 | 14 / -22.75 | 13 / 5.71 |
| A_X1_H08 | 7 / 7.37 | 14 / -38.70 | 13 / -13.08 |
| A_X1_H18 | 7 / -52.74 | 14 / -27.56 | 13 / 10.61 |
| A_X1_H24 | 7 / -84.17 | 14 / -15.07 | 13 / 10.55 |
| A_X2_H08 | 7 / 28.17 | 14 / -58.70 | 13 / -9.60 |
| A_X2_H18 | 7 / -40.55 | 14 / -41.04 | 13 / 11.49 |
| A_X2_H24 | 7 / -71.98 | 14 / -24.53 | 13 / 4.39 |
| B_X0_H08 | 1 / -105.79 | 2 / -174.75 | 2 / 17.04 |
| B_X0_H18 | 1 / -105.79 | 2 / -174.75 | 2 / -3.92 |
| B_X0_H24 | 1 / -105.79 | 2 / -174.75 | 2 / -3.92 |
| B_X1_H08 | 1 / -105.79 | 2 / -174.75 | 2 / -10.64 |
| B_X1_H18 | 1 / -105.79 | 2 / -174.75 | 2 / 32.03 |
| B_X1_H24 | 1 / -105.79 | 2 / -174.75 | 2 / 32.03 |
| B_X2_H08 | 1 / -105.79 | 2 / -174.75 | 2 / 0.31 |
| B_X2_H18 | 1 / -105.79 | 2 / -174.75 | 2 / 1.36 |
| B_X2_H24 | 1 / -105.79 | 2 / -174.75 | 2 / 1.36 |
| C_X0_H08 | 12 / -6.91 | 10 / -10.64 | 12 / -47.24 |
| C_X0_H18 | 12 / -7.61 | 10 / -61.96 | 12 / -41.19 |
| C_X0_H24 | 12 / -7.61 | 10 / -76.28 | 12 / -41.19 |
| C_X1_H08 | 12 / -35.38 | 10 / 2.23 | 13 / -60.27 |
| C_X1_H18 | 12 / -39.21 | 10 / -7.02 | 13 / -60.27 |
| C_X1_H24 | 12 / -39.31 | 10 / -6.90 | 13 / -60.24 |
| C_X2_H08 | 12 / -21.82 | 10 / -9.60 | 12 / -49.85 |
| C_X2_H18 | 12 / -31.80 | 10 / -60.96 | 12 / -47.47 |
| C_X2_H24 | 12 / -31.50 | 10 / -77.61 | 12 / -47.47 |

## Same-entry exit improvements and selection effects

Paired episodes use the same frozen entry, side, cap, cost and initial quantity, with a fixed unfunded 1000-USDT sizing reference. They ignore account blocking and cannot be treated as portfolio ROI. Portfolio admission/size/cooldown/risk fates are separately recorded, including unmatched entry IDs in scratch event ledgers.

| STRESS alternate | Matched entries | Mean delta vs X0 bp | Tail5 alternate / X0 bp | Portfolio intersection / only X0 / only alternate |
|---|---:|---:|---|---|
| A_X1_H08 | 35 | 13.80 | -171.22 / -180.82 | 34 / 0 / 0 |
| A_X1_H18 | 35 | 5.80 | -246.29 / -246.29 | 34 / 0 / 0 |
| A_X1_H24 | 35 | 6.35 | -246.29 / -246.29 | 34 / 0 / 0 |
| A_X2_H08 | 35 | 11.56 | -171.22 / -180.82 | 34 / 0 / 0 |
| A_X2_H18 | 35 | 3.03 | -246.29 / -246.29 | 34 / 0 / 0 |
| A_X2_H24 | 35 | 2.72 | -246.29 / -246.29 | 34 / 0 / 0 |
| B_X1_H08 | 5 | -11.07 | -203.40 / -203.40 | 5 / 0 / 0 |
| B_X1_H18 | 5 | 14.38 | -203.40 / -203.40 | 5 / 0 / 0 |
| B_X1_H24 | 5 | 14.38 | -203.40 / -203.40 | 5 / 0 / 0 |
| B_X2_H08 | 5 | -6.69 | -203.40 / -203.40 | 5 / 0 / 0 |
| B_X2_H18 | 5 | 2.11 | -203.40 / -203.40 | 5 / 0 / 0 |
| B_X2_H24 | 5 | 2.11 | -203.40 / -203.40 | 5 / 0 / 0 |
| C_X1_H08 | 37 | -9.17 | -171.41 / -171.41 | 34 / 0 / 1 |
| C_X1_H18 | 37 | -0.78 | -200.04 / -200.04 | 34 / 0 / 1 |
| C_X1_H24 | 37 | 3.10 | -200.04 / -200.04 | 34 / 0 / 1 |
| C_X2_H08 | 37 | -4.37 | -171.41 / -171.41 | 34 / 0 / 0 |
| C_X2_H18 | 37 | -8.58 | -200.04 / -200.04 | 34 / 0 / 0 |
| C_X2_H24 | 37 | -9.12 | -200.04 / -200.04 | 34 / 0 / 0 |

A scale-outs sometimes reduce losses versus X0 while remaining negative after STRESS costs. B has very little support. C scale-outs/trailing can reduce profit as well as tail exposure. Every STRESS cell remains below the 50-trade support gate and has nonpositive equal-year net economics; no winner is promoted. The least-negative table entry is not an eligible hypothesis.

## Execution, financing and uncertainty

JSON reports per-leg fees/spread/slip/tick drag, netR, PF, collision count, partial TP frequency, cap8/18/24 triggers, min/median/p75/max holding minutes and exits before4/12/18/24h. There is no 12h cap experiment. STOP/GAP/TIME_CAP/RISK_CLOSE are actual simulator causes; holding caps do not force a minimum holding time.

Funding sensitivities are adverse4/8bp at possible UTC8h windows and adverse8bp hourly, using remaining quantity and conservative Last high. These are separate hypothetical financing charges, not verified historical costs. Additional exit2bp spread+3bp slip is a fixed-leg price/fee sensitivity, not a newly tuned strategy replay.

Inference uses 10,000 shared deterministic calendar-week block draws within year, includes empty eligible weeks, and applies Bonferroni27 to net and paired improvement. Calendar-month blocks are a descriptive sensitivity. Undefined support/resamples are reported explicitly. No minute-IID sample claim or post-result threshold changes.

A retains raw R2 entry dictionaries and hashes. All exits use a common24h+ACK fold cutoff, so admitted A accounts differ from the old8h-specific cutoff. R3 uses a full causal account risk close rather than R2 partial notional reduction. These account differences cannot be attributed solely to new exit targets.

## Reproducibility and examples

```sh
PYTHONDONTWRITEBYTECODE=1 python3.12 -m pytest -q --noconftest tests/test_v06_g2_btc_exit_aware_r3_engine.py -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 python3.12 -m scripts.strategy_research.g2_btc_exit_aware_r3.run
PYTHONDONTWRITEBYTECODE=1 python3.12 -m scripts.strategy_research.g2_btc_exit_aware_r3.report
```

Download admission precedes replay and requires the remote freeze receipt; raw ZIP/CSV/NPY and full entry/leg/curve paths remain in task scratch. Five unique real-development event examples (good and bad hypothetical trades) are in result.sample_trades; five synthetic Decimal audits are in MANUAL_DECIMAL_EXIT_LEG_AUDITS.json. CI_TEST_EXECUTION_EXACT_SHA.json distinguishes source/test hashes, exact committed test SHA, local focused execution and GitHub status; no docs-only green is used as code acceptance.

Binance Vision attribution. Dataset-derived analytical results are CC BY-NC-SA4.0 for noncommercial historical research. [Official data format/checksums](https://github.com/binance/binance-public-data); [dataset terms](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md).

## Exact code and regression receipt

Executable code/source tested SHA `3af438490da4497132a5c32c786752ca527e0d99`; parent freeze `45bf7cc72eb9a870323c5da056fc9287d42b7b22`. Local Python3.12.3 focused suite61passed/0failed/0skipped, Ruff PASS.

[Actual GitHub code CI run38285054954](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38285054954) succeeded at that exact SHA. Its actual PROFILE full test step executed2955passed,2skipped,9warnings in884.00s; the supplied3454-scale expectation is not the actual count at this snapshot. No local full repository run was performed.

The final attestation commit changes only docs/evidence and leaves all executable source and tests byte-identical to the tested code commit. Its docs-only CI is not substituted for the full code gate above. Scoring ran twice on the same27frozen hypotheses and two cost cases, with no retunes; final code file hashes match the tested immutable source.

Five public-development sample traces bind the hypothetical event/leg ledger to its provider ZIP/CSV hashes. Monthly equity/MTM arrays are floating-point descriptive measurements; per-leg cash, prices, fees and quantity conservation use Decimal and independent eight-place audits.
