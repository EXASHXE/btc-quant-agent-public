# WAVE_02 Empirical Research Decision & Performance Report

- **TASK_ID**: `V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1`
- **FREEZE_COMMIT_SHA**: `f82eda7d930e5e158be7cc2fa60967b871e84f0f`
- **WAVE_DECISION**: `ALL_CANDIDATES_FALSIFIED_PROCEED_TO_NEXT_WAVE`
- **DATE_RANGE**: `2021-02 to 2023-12 (35 scored monthly folds, 2021-01 warmup)`
- **SEALED_HOLDOUT**: `2024–2026 strictly untouched`

## 1. Candidate Performance Summary Table (STRESS 44 bp)

| Candidate ID | Family | Trades | Mean Gross bp | Mean Net bp | Equal-Yr Net bp | PF | Max MTM DD | 7d LCB | Gate Status |
|---|---|---|---|---|---|---|---|---|---|
| `W2_C01_VOLUME_WEIGHTED_MOMENTUM_SURGE_08H` | `VOLUME_WEIGHTED_MOMENTUM_SURGE` | 583 | 8.6 | -71.4 | -69.7 | 1.21 | 97.5% | -82.1 | `FALSIFIED_DEV_CANDIDATE` |
| `W2_C02_MULTI_TIMEFRAME_CHOP_EXIT_TREND_12H` | `MULTI_TIMEFRAME_CHOP_EXIT_TREND` | 20 | -53.9 | -134.0 | -123.2 | 0.43 | 23.4% | -198.8 | `FALSIFIED_DEV_CANDIDATE` |
| `W2_C03_AGGRESSIVE_FLOW_CUMULATIVE_DELTA_DIVERGENCE_08H` | `FLOW_CUMULATIVE_DELTA_CONFIRMATION` | 504 | 0.7 | -79.4 | -80.0 | 0.98 | 97.4% | -92.9 | `FALSIFIED_DEV_CANDIDATE` |
| `W2_C04_DONCHIAN_MIDLINE_PULLBACK_CONTINUATION_08H` | `DONCHIAN_MIDLINE_PULLBACK_CONTINUATION` | 472 | -6.5 | -86.5 | -85.4 | 1.01 | 97.6% | -97.4 | `FALSIFIED_DEV_CANDIDATE` |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `ASYMMETRIC_VOLATILITY_BREAKOUT` | 55 | 63.3 | -16.8 | 0.9 | 2.99 | 16.2% | -52.3 | `FALSIFIED_DEV_CANDIDATE` |
| `W2_C06_EXTREME_FLOW_EXHAUSTION_REVERSAL_TO_TREND_04H` | `FLOW_EXHAUSTION_REVERSAL_TO_TREND` | 169 | 2.9 | -77.1 | -78.1 | 1.00 | 72.4% | -85.4 | `FALSIFIED_DEV_CANDIDATE` |

## 2. Gate Verification Details

### `W2_C01_VOLUME_WEIGHTED_MOMENTUM_SURGE_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 583, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 32})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -69.68188793919086, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 1.2122997217709026, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -86.51422186617458, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 97.51542192502255, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -82.12876968700452, 'threshold': 0.0})

### `W2_C02_MULTI_TIMEFRAME_CHOP_EXIT_TREND_12H`
- **G1_sample_size_ge_100**: `FAIL` (details: {'passed': False, 'value': 20, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 16})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -123.15781285927527, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.42993040383567516, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -152.42004323504872, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 23.433142150000048, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -198.7955635754984, 'threshold': 0.0})

### `W2_C03_AGGRESSIVE_FLOW_CUMULATIVE_DELTA_DIVERGENCE_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 504, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 30})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -79.95470096173032, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.9754010199207876, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -82.58727998416873, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 97.43467484000008, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -92.94892477045195, 'threshold': 0.0})

### `W2_C04_DONCHIAN_MIDLINE_PULLBACK_CONTINUATION_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 472, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 29})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -85.41581704778746, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 1.0094101774490047, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -93.69509284272368, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 97.55068023149144, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -97.41661778824859, 'threshold': 0.0})

### `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H`
- **G1_sample_size_ge_100**: `FAIL` (details: {'passed': False, 'value': 55, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 27})
- **G3_equal_year_net_gt_0**: `PASS` (details: {'passed': True, 'value': 0.8990992052335306, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 2.987089782680842, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -72.75771890227405, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 16.189245299191633, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -52.29090749593929, 'threshold': 0.0})

### `W2_C06_EXTREME_FLOW_EXHAUSTION_REVERSAL_TO_TREND_04H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 169, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 27})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -78.07637325566849, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 1.0017570049858908, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -86.57672060651954, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 72.40690416388456, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -85.3985808818188, 'threshold': 0.0})

## 3. Next Action

All 6 Wave 1 candidates failed the promotion criteria under 44 bp stress cost. Advancing to Wave 2 under the cumulative trial budget.