# WAVE_04 Empirical Research Decision & Performance Report

- **TASK_ID**: `V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1`
- **FREEZE_COMMIT_SHA**: `8b7b4318db3f1f8344653cb649f2dd05b5ca9dd4`
- **WAVE_DECISION**: `ALL_CANDIDATES_FALSIFIED_PROCEED_TO_NEXT_WAVE`
- **DATE_RANGE**: `2021-02 to 2023-12 (35 scored monthly folds, 2021-01 warmup)`
- **SEALED_HOLDOUT**: `2024–2026 strictly untouched`

## 1. Candidate Performance Summary Table (STRESS 44 bp)

| Candidate ID | Family | Trades | Mean Gross bp | Mean Net bp | Equal-Yr Net bp | PF | Max MTM DD | 7d LCB | Gate Status |
|---|---|---|---|---|---|---|---|---|---|
| `W4_C01_DUAL_TIMEFRAME_VOLATILITY_EXPANSION_08H` | `DUAL_TIMEFRAME_VOLATILITY_EXPANSION` | 37 | -21.7 | -101.8 | -111.5 | 0.64 | 31.3% | -157.9 | `FALSIFIED_DEV_CANDIDATE` |
| `W4_C02_VWAP_MEAN_DRIFT_ACCELERATION_08H` | `VWAP_MEAN_DRIFT_ACCELERATION` | 573 | -2.8 | -82.7 | -82.7 | 0.97 | 98.4% | -95.2 | `FALSIFIED_DEV_CANDIDATE` |
| `W4_C03_TREND_MOMENTUM_CONVERGENCE_DIVERGENCE_12H` | `TREND_MOMENTUM_CONVERGENCE` | 306 | 21.8 | -58.3 | -56.0 | 1.54 | 84.5% | -73.9 | `FALSIFIED_DEV_CANDIDATE` |
| `W4_C04_DONCHIAN_CHANNEL_VOLATILITY_BREAKOUT_08H` | `DONCHIAN_VOLATILITY_BREAKOUT` | 256 | 11.6 | -68.5 | -68.3 | 1.23 | 82.0% | -83.8 | `FALSIFIED_DEV_CANDIDATE` |
| `W4_C05_CUMULATIVE_FLOW_PERCENTILE_SURGE_08H` | `CUMULATIVE_FLOW_PERCENTILE_SURGE` | 509 | -7.1 | -87.2 | -88.2 | 1.07 | 98.0% | -98.6 | `FALSIFIED_DEV_CANDIDATE` |
| `W4_C06_ASYMMETRIC_MOMENTUM_EXHAUSTION_CONTINUATION_24H` | `ASYMMETRIC_MOMENTUM_CONTINUATION` | 404 | -3.5 | -83.6 | -83.5 | 0.93 | 96.0% | -104.6 | `FALSIFIED_DEV_CANDIDATE` |

## 2. Gate Verification Details

### `W4_C01_DUAL_TIMEFRAME_VOLATILITY_EXPANSION_08H`
- **G1_sample_size_ge_100**: `FAIL` (details: {'passed': False, 'value': 37, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 22})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -111.47594608050332, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.6366314345583923, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -203.53533846998215, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 31.29143375000002, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -157.9472377917351, 'threshold': 0.0})

### `W4_C02_VWAP_MEAN_DRIFT_ACCELERATION_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 573, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 2, 'months': 21})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -82.7334217150208, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.9710159109931704, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -82.79286554836786, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 98.41634070908144, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -95.15916931396795, 'threshold': 0.0})

### `W4_C03_TREND_MOMENTUM_CONVERGENCE_DIVERGENCE_12H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 306, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 35})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -56.00626350781412, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 1.535078382169371, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -81.49492106994892, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 84.48030928144671, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -73.89402849263669, 'threshold': 0.0})

### `W4_C04_DONCHIAN_CHANNEL_VOLATILITY_BREAKOUT_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 256, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 35})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -68.27741635941824, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `PASS` (details: {'passed': True, 'value': 1.2284909926637393, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -76.048332514101, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 81.96987145507964, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -83.79671558924821, 'threshold': 0.0})

### `W4_C05_CUMULATIVE_FLOW_PERCENTILE_SURGE_08H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 509, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 26})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -88.16892120126046, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 1.074444968072932, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -94.87316302864049, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 97.96937821934858, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -98.55899590856879, 'threshold': 0.0})

### `W4_C06_ASYMMETRIC_MOMENTUM_EXHAUSTION_CONTINUATION_24H`
- **G1_sample_size_ge_100**: `PASS` (details: {'passed': True, 'value': 404, 'threshold': 100})
- **G2_temporal_breadth**: `PASS` (details: {'passed': True, 'years': 3, 'months': 35})
- **G3_equal_year_net_gt_0**: `FAIL` (details: {'passed': False, 'value': -83.54703624808052, 'threshold': 0.0})
- **G4_profit_factor_ge_115**: `FAIL` (details: {'passed': False, 'value': 0.9313371630447177, 'threshold': 1.15})
- **G5_worst_year_net_ge_neg10**: `FAIL` (details: {'passed': False, 'value': -86.06600029547783, 'threshold': -10.0})
- **G6_max_drawdown_le_12pct**: `FAIL` (details: {'passed': False, 'value': 96.03796774462194, 'threshold': 12.0})
- **G7_bootstrap_lcb_gt_0**: `FAIL` (details: {'passed': False, 'value': -104.59186511003337, 'threshold': 0.0})

## 3. Next Action

All 6 Wave 1 candidates failed the promotion criteria under 44 bp stress cost. Advancing to Wave 2 under the cumulative trial budget.