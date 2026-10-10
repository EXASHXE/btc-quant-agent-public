# WAVE_03 Empirical Research Decision & Performance Report

- **TASK_ID**: `V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1`
- **FREEZE_COMMIT_SHA**: `99b443b87a0551519c87df28d63edc8e56808b98`
- **WAVE_DECISION**: `ALL_CANDIDATES_FALSIFIED_PROCEED_TO_NEXT_WAVE`
- **DATE_RANGE**: `2021-02 to 2023-12 (35 scored monthly folds, 2021-01 warmup)`
- **SEALED_HOLDOUT**: `2024–2026 strictly untouched`

## 1. Candidate Performance Summary Table (STRESS 44 bp)

| Candidate ID | Family | Trades | Mean Gross bp | Mean Net bp | Equal-Yr Net bp | PF | Max MTM DD | 7d LCB | Gate Status |
|---|---|---|---|---|---|---|---|---|---|
| `W3_C01_EMA_CROSS_MULTI_HORIZON_TREND_FILTER_08H` | `EMA_CROSS_MULTI_HORIZON_TREND` | 137 | -2.1 | -82.2 | -80.4 | 0.94 | 67.0% | -97.5 | `FALSIFIED_DEV_CANDIDATE` |
| `W3_C02_KAUFMAN_EFFICIENCY_RATIO_EXPANSION_08H` | `KAUFMAN_EFFICIENCY_RATIO_EXPANSION` | 346 | 5.2 | -74.9 | -74.8 | 1.11 | 92.0% | -90.2 | `FALSIFIED_DEV_CANDIDATE` |
| `W3_C03_BOLLINGER_BAND_WIDTH_SQUEEZE_EXPLOSION_12H` | `BOLLINGER_BAND_WIDTH_SQUEEZE` | 20 | -5.1 | -85.2 | -94.4 | 0.91 | 15.5% | -141.1 | `FALSIFIED_DEV_CANDIDATE` |
| `W3_C04_ASYMMETRIC_LONG_BIASED_TREND_FLOW_12H` | `ASYMMETRIC_LONG_BIASED_TREND` | 101 | 23.7 | -56.4 | -51.1 | 1.58 | 46.7% | -81.7 | `FALSIFIED_DEV_CANDIDATE` |
| `W3_C05_ASYMMETRIC_SHORT_BIASED_FLOW_COLLAPSE_08H` | `ASYMMETRIC_SHORT_BIASED_COLLAPSE` | 4 | 72.6 | -7.1 | 46.3 | 6.43 | 1.7% | 0.0 | `FALSIFIED_DEV_CANDIDATE` |
| `W3_C06_TIME_WEIGHTED_SESSION_PULLBACK_08H` | `SESSION_PULLBACK_TREND` | 375 | -6.4 | -86.5 | -86.4 | 0.90 | 94.9% | -96.5 | `FALSIFIED_DEV_CANDIDATE` |

## 2. Gate Verification Details

### `W3_C01_EMA_CROSS_MULTI_HORIZON_TREND_FILTER_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 137, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 31})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -80.42715922139878, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.9397942759051635, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -85.96396648827287, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 66.95886068, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -97.53944764654214, 'threshold': 0.0})

### `W3_C02_KAUFMAN_EFFICIENCY_RATIO_EXPANSION_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 346, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 35})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -74.76032808069864, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 1.1057535958986962, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -82.16022381444554, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 91.96025495199599, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -90.19288278474119, 'threshold': 0.0})

### `W3_C03_BOLLINGER_BAND_WIDTH_SQUEEZE_EXPLOSION_12H`
- **G1_sample_size_ge_100**: `FAIL` (details: {'passed': False, 'value': 20, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 15})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -94.37184244004645, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.9129824894460143, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -136.67446532468765, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 15.476340659999993, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -141.07901785474783, 'threshold': 0.0})

### `W3_C04_ASYMMETRIC_LONG_BIASED_TREND_FLOW_12H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 101, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 29})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -51.10400083185882, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 1.5834791367207959, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -78.1677226534657, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 46.682016242008636, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -81.6636395984728, 'threshold': 0.0})

### `W3_C05_ASYMMETRIC_SHORT_BIASED_FLOW_COLLAPSE_08H`
- **G1_sample_size_ge_100**: `FAIL` (details: {'passed': False, 'value': 4, 'threshold': 100})
- **G2_temporal_breadth**: `FAIL` (details: {'passed': False, 'years': 2, 'months': 4})
- **G3_equal_year_net_gt_0**: `PASS` (details: {'passed': True, 'value': 46.33779124629068, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 6.43021226282289, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -60.55930040703717, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `PASS` (details: {'passed': True, 'value': 1.739156990090521, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': 0.0, 'threshold': 0.0})

### `W3_C06_TIME_WEIGHTED_SESSION_PULLBACK_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 375, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 35})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -86.41268982198744, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.8987567319536602, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -87.00721451271409, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 94.90507249019494, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -96.46471736929728, 'threshold': 0.0})

## 3. Next Action

All 6 Wave 1 candidates failed the promotion criteria under 44 bp stress cost. Advancing to Wave 2 under the cumulative trial budget.