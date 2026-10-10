# Wave 2 Hypothesis Freeze: BTC Directional Flow Innovations & Regime Shifts

- **TASK_ID**: `V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1`
- **CONTROLLER_DISPATCH_SHA**: `6c6ff831868701cea05499d0b0adb0e62db67f0e`
- **PARENT_WAVE_1_RESULT_SHA**: `b670d28d4810edc8050d820d67526d78f1f334a1`
- **PROTOCOL**: Outcome-blind freeze prior to Wave 2 execution.
- **FREEZE_TIMESTAMP_UTC**: `2026-10-11T04:14:00Z`
- **BUDGET_STATUS**: Wave 1 evaluated 6 candidates (6 falsified). Wave 2 adds 6 candidates (total 12 / 24 trials).

---

## 1. Wave 2 Candidate Roster

| Candidate ID | Family | Horizon | Target R | Stop (1h ATR) | Cooldown | Core Economic Mechanism |
|---|---|---|---|---|---|---|
| `W2_C01_VOLUME_WEIGHTED_MOMENTUM_SURGE_08H` | `VOLUME_WEIGHTED_MOMENTUM_SURGE` | 8h | 2.0R | 1.5x | 4h | 1h close breaks 24h rolling VWAP by > 0.5x ATR with volume surge (> 1.5x) and signed taker flow (> 0.15). |
| `W2_C02_MULTI_TIMEFRAME_CHOP_EXIT_TREND_12H` | `MULTI_TIMEFRAME_CHOP_EXIT_TREND` | 12h | 2.0R | 2.0x | 6h | 4h consolidation regime exit: ADX < 18 for >= 12h, crossing above 20 with DI direction and 12h high/low breakout. |
| `W2_C03_AGGRESSIVE_FLOW_CUMULATIVE_DELTA_DIVERGENCE_08H` | `FLOW_CUMULATIVE_DELTA_CONFIRMATION` | 8h | 2.0R | 1.5x | 4h | Cumulative volume delta (CVD) momentum confirmation: 12h price breakout accompanied by new 12h high in 12h CVD. |
| `W2_C04_DONCHIAN_MIDLINE_PULLBACK_CONTINUATION_08H` | `DONCHIAN_MIDLINE_PULLBACK_CONTINUATION` | 8h | 2.0R | 1.5x | 4h | Trend continuation entering on 15m pullback touching 20-bar 1h Donchian midline in aligned 4h trend. |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `ASYMMETRIC_VOLATILITY_BREAKOUT` | 12h | 2.5R | 1.8x | 6h | Calibrated volatility compression (ATR14/56 < 0.85) + expansion (> 1.2x SMA10) + volume surge (> 1.5x) + 15m flow. |
| `W2_C06_EXTREME_FLOW_EXHAUSTION_REVERSAL_TO_TREND_04H` | `FLOW_EXHAUSTION_REVERSAL_TO_TREND` | 4h | 2.0R | 1.2x | 4h | Liquidity sweep exhaustion into trend: sharp counter-trend flush with signed flow < -0.30 and long wick, followed by trend resumption. |

---

## 2. Evaluation Rules & Gates

Identical to Wave 1: 44 bp STRESS cost model, 100+ trades, $\ge 2$ years, $\ge 6$ months, equal-year net $> 0$, PF $\ge 1.15$, max MTM DD $\le 12\%$, block bootstrap LCB $> 0$.
