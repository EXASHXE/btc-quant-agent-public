# Wave 3 Hypothesis Freeze: Directional Trend, Efficiency Shifts, Squeeze & Asymmetries

- **TASK_ID**: `V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1`
- **CONTROLLER_DISPATCH_SHA**: `6c6ff831868701cea05499d0b0adb0e62db67f0e`
- **PARENT_WAVE_2_RESULT_SHA**: `93c6a7624f0002803816ffab9292075463c3e07d`
- **PROTOCOL**: Outcome-blind freeze prior to Wave 3 execution.
- **FREEZE_TIMESTAMP_UTC**: `2026-10-11T04:17:00Z`
- **BUDGET_STATUS**: Waves 1 & 2 evaluated 12 candidates (all 12 falsified). Wave 3 adds 6 candidates (total 18 / 24 trials).

---

## 1. Wave 3 Candidate Roster

| Candidate ID | Family | Horizon | Target R | Stop (1h ATR) | Cooldown | Core Economic Mechanism |
|---|---|---|---|---|---|---|
| `W3_C01_EMA_CROSS_MULTI_HORIZON_TREND_FILTER_08H` | `EMA_CROSS_MULTI_HORIZON_TREND` | 8h | 2.0R | 1.5x | 4h | Fresh 1h EMA10/30 cross within 2h, aligned with 4h EMA20 > EMA50, and 15m signed flow > 0.20. |
| `W3_C02_KAUFMAN_EFFICIENCY_RATIO_EXPANSION_08H` | `KAUFMAN_EFFICIENCY_RATIO_EXPANSION` | 8h | 2.0R | 1.5x | 4h | Kaufman Efficiency Ratio transition from noise (< 0.30) to directional trend (> 0.65) with 15m taker flow confirmation. |
| `W3_C03_BOLLINGER_BAND_WIDTH_SQUEEZE_EXPLOSION_12H` | `BOLLINGER_BAND_WIDTH_SQUEEZE` | 12h | 2.5R | 1.8x | 6h | 1h Bollinger bandwidth squeeze to 30-bar low, followed by breakout of band with volume > 1.5x and 15m flow > 0.15. |
| `W3_C04_ASYMMETRIC_LONG_BIASED_TREND_FLOW_12H` | `ASYMMETRIC_LONG_BIASED_TREND` | 12h | 2.5R | 1.5x | 6h | Asymmetric long trend riding: 4h bull trend, 1h trend confirm, 1h ATR expanding, and 2 consecutive 15m bars of positive flow (> 0.15). |
| `W3_C05_ASYMMETRIC_SHORT_BIASED_FLOW_COLLAPSE_08H` | `ASYMMETRIC_SHORT_BIASED_COLLAPSE` | 8h | 2.0R | 1.2x | 4h | Short-biased liquidation cascade: 4h downtrend, sharp 1h drop (> 1.5x ATR) with massive negative flow (< -0.25) and volume surge (> 2.0x). |
| `W3_C06_TIME_WEIGHTED_SESSION_PULLBACK_08H` | `SESSION_PULLBACK_TREND` | 8h | 2.0R | 1.5x | 6h | Peak liquidity window (10:00 to 18:00 UTC) pullback touch of 1h EMA10 in 4h trend with strong taker flow confirmation. |

---

## 2. Evaluation Rules & Gates

Identical to prior waves: 44 bp STRESS cost model, 100+ trades, $\ge 2$ years, $\ge 6$ months, equal-year net $> 0$, PF $\ge 1.15$, max MTM DD $\le 12\%$, block bootstrap LCB $> 0$.
