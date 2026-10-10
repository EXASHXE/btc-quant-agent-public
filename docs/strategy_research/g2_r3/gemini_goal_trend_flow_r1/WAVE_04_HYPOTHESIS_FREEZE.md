# Wave 4 Hypothesis Freeze: Final Search Space Exploration (Trials 19–24)

- **TASK_ID**: `V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1`
- **CONTROLLER_DISPATCH_SHA**: `6c6ff831868701cea05499d0b0adb0e62db67f0e`
- **PARENT_WAVE_3_RESULT_SHA**: `10d8695c368f85cd23b2e4ec83ec1d177170e8a8`
- **PROTOCOL**: Outcome-blind freeze prior to Wave 4 execution.
- **FREEZE_TIMESTAMP_UTC**: `2026-10-11T04:21:00Z`
- **BUDGET_STATUS**: Final Wave 4 brings cumulative trials to exactly 24 (the complete authorized trial budget).

---

## 1. Wave 4 Candidate Roster

| Candidate ID | Family | Horizon | Target R | Stop (1h ATR) | Cooldown | Core Economic Mechanism |
|---|---|---|---|---|---|---|
| `W4_C01_DUAL_TIMEFRAME_VOLATILITY_EXPANSION_08H` | `DUAL_TIMEFRAME_VOLATILITY_EXPANSION` | 8h | 2.5R | 1.5x | 4h | Dual timeframe volatility expansion: 4h ATR14 > ATR56, 1h ATR14 surges > 1.25x SMA10 with volume > 1.3x and 15m flow > 0.15. |
| `W4_C02_VWAP_MEAN_DRIFT_ACCELERATION_08H` | `VWAP_MEAN_DRIFT_ACCELERATION` | 8h | 2.0R | 1.5x | 4h | 24h rolling VWAP acceleration: Price holds above 24h VWAP for 3 consecutive 1h bars with positive slope and 15m flow > 0.20. |
| `W4_C03_TREND_MOMENTUM_CONVERGENCE_DIVERGENCE_12H` | `TREND_MOMENTUM_CONVERGENCE` | 12h | 2.5R | 1.8x | 6h | 4h MACD histogram crosses zero, 1h close > EMA20, 15m flow > 0.15. |
| `W4_C04_DONCHIAN_CHANNEL_VOLATILITY_BREAKOUT_08H` | `DONCHIAN_VOLATILITY_BREAKOUT` | 8h | 2.0R | 1.2x | 4h | 1h 24-bar Donchian breakout with volume > 1.5x, flow > 0.15, and tight 1.2x stop to minimize drag. |
| `W4_C05_CUMULATIVE_FLOW_PERCENTILE_SURGE_08H` | `CUMULATIVE_FLOW_PERCENTILE_SURGE` | 8h | 2.0R | 1.5x | 4h | 15m signed flow in top 95th percentile of 48-bar (12h) distribution with volume > 1.5x, aligned with 4h trend. |
| `W4_C06_ASYMMETRIC_MOMENTUM_EXHAUSTION_CONTINUATION_24H` | `ASYMMETRIC_MOMENTUM_CONTINUATION` | 24h | 3.0R | 2.0x | 12h | Secular 24h trend riding with asymmetric 3.0R payoff: 4h EMA20 > EMA50, ADX > 22, 1h close > EMA20, flow > 0.15. |

---

## 2. Evaluation Rules & Gates

Identical to prior waves: 44 bp STRESS cost model, 100+ trades, $\ge 2$ years, $\ge 6$ months, equal-year net $> 0$, PF $\ge 1.15$, max MTM DD $\le 12\%$, block bootstrap LCB $> 0$.
