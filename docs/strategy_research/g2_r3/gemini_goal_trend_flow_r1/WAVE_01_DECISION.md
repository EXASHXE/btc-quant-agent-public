# WAVE_01 Empirical Research Decision & Performance Report

- **TASK_ID**: `V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1`
- **FREEZE_COMMIT_SHA**: `5295eff5c63797fd28a5b7b5733a009536e4fdf3`
- **WAVE_DECISION**: `ALL_CANDIDATES_FALSIFIED_PROCEED_TO_NEXT_WAVE`
- **DATE_RANGE**: `2021-02 to 2023-12 (35 scored monthly folds, 2021-01 warmup)`
- **SEALED_HOLDOUT**: `2024–2026 strictly untouched`

## 1. Candidate Performance Summary Table (STRESS 44 bp)

| Candidate ID | Family | Trades | Mean Gross bp | Mean Net bp | Equal-Yr Net bp | PF | Max MTM DD | 7d LCB | Gate Status |
|---|---|---|---|---|---|---|---|---|---|
| `W1_C01_MULTISCALE_TREND_ADOPTION_08H` | `MULTISCALE_TREND_ADOPTION` | 400 | 3.4 | -76.6 | -66.1 | 1.30 | 94.4% | -87.4 | `FALSIFIED_DEV_CANDIDATE` |
| `W1_C02_PERSISTENT_TAKER_PRESSURE_08H` | `PERSISTENT_TAKER_PRESSURE` | 304 | 4.5 | -75.5 | -69.0 | 1.18 | 89.7% | -87.1 | `FALSIFIED_DEV_CANDIDATE` |
| `W1_C03_BREAKOUT_RETEST_WITH_FLOW_04H` | `MULTIHOUR_BREAKOUT_RETEST_WITH_FLOW` | 386 | -11.9 | -92.0 | -89.9 | 0.69 | 96.0% | -103.5 | `FALSIFIED_DEV_CANDIDATE` |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `ATR_EXPANSION_TREND_FOLLOW` | 34 | 61.6 | -18.4 | -5.4 | 2.31 | 15.1% | -77.2 | `FALSIFIED_DEV_CANDIDATE` |
| `W1_C05_CROSS_SESSION_CONTINUATION_08H` | `CROSS_SESSION_CONTINUATION` | 85 | -19.7 | -99.7 | -99.3 | 0.75 | 56.7% | -121.5 | `FALSIFIED_DEV_CANDIDATE` |
| `W1_C06_PERSISTENT_TREND_24H` | `PERSISTENT_TREND_24H` | 240 | 15.8 | -64.2 | -63.8 | 1.22 | 85.1% | -95.5 | `FALSIFIED_DEV_CANDIDATE` |

## 2. Gate Verification Details

### `W1_C01_MULTISCALE_TREND_ADOPTION_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 400, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 34})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -66.09360720509498, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 1.3034625211541906, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -88.5369219720218, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 94.39684066732242, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -87.43710973296568, 'threshold': 0.0})

### `W1_C02_PERSISTENT_TAKER_PRESSURE_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 304, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 35})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -68.99800855610584, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 1.1805739325831592, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -89.51321775252653, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 89.65094141486772, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -87.11930772557389, 'threshold': 0.0})

### `W1_C03_BREAKOUT_RETEST_WITH_FLOW_04H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 386, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 35})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -89.9092651495123, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.6919659025170801, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -101.63530004208712, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 95.95046864608379, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -103.47851453765698, 'threshold': 0.0})

### `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H`
- **G1_sample_size_ge_100**: `FAIL` (details: {'passed': False, 'value': 34, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 22})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -5.397867056312134, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 2.305191554016654, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -50.653858654905186, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 15.082660979852792, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -77.17211758355747, 'threshold': 0.0})

### `W1_C05_CROSS_SESSION_CONTINUATION_08H`
- **G1_sample_size_ge_100**: `FAIL` (details: {'passed': False, 'value': 85, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 30})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -99.31755799667268, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.746564325721993, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -118.5001772168541, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 56.70749853, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -121.49926033507343, 'threshold': 0.0})

### `W1_C06_PERSISTENT_TREND_24H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 240, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 35})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -63.797489562386716, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 1.2169537868522906, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -93.42306012609883, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 85.0505748783521, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -95.48503978940688, 'threshold': 0.0})

## 3. Next Action

All 6 Wave 1 candidates failed the promotion criteria under 44 bp stress cost. Advancing to Wave 2 under the cumulative trial budget.