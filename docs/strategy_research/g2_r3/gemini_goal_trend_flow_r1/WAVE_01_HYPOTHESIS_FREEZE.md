# Wave 1 Hypothesis Freeze & Pre-Registration: BTC Directional Trend × Flow Imbalance

- **TASK_ID**: `V06_G2_GEMINI_GOAL_A_TREND_FLOW_MULTI_WAVE_DISCOVERY_R1`
- **CONTROLLER_DISPATCH_SHA**: `6c6ff831868701cea05499d0b0adb0e62db67f0e`
- **PARENT_START_SHA**: `920b244d06541da5cb9fc3dcaa39e5b15e914d32`
- **PROTOCOL**: Outcome-blind freeze prior to backtest execution or outcome observation.
- **FREEZE_TIMESTAMP_UTC**: `2026-10-11T04:05:00Z`
- **DATA_GRANT**: Binance Vision BTCUSDT USD-M Perpetual 1m (2021-01 to 2023-12). Jan 2021 warmup only. Scored months: Feb 2021 to Dec 2023 (35 months). Holdout 2024-2026 sealed and untouched.

---

## 1. Candidate Roster & Economic Hypotheses

| Candidate ID | Family | Horizon | Target R | Stop (1h ATR) | Cooldown | Core Economic Mechanism |
|---|---|---|---|---|---|---|
| `W1_C01_MULTISCALE_TREND_ADOPTION_08H` | `MULTISCALE_TREND_ADOPTION` | 8h | 2.0R | 1.5x | 4h | 4h EMA20/50 slope trend + 1h trend confirm + 15m non-chase entry with 2-bar persistent taker flow ratio (> 0.15). |
| `W1_C02_PERSISTENT_TAKER_PRESSURE_08H` | `PERSISTENT_TAKER_PRESSURE` | 8h | 2.0R | 1.5x | 4h | Sustained aggressive taker order flow imbalance (3 consecutive 15m bars signed ratio > 0.10) with volume surge (> 1.2x SMA20) aligned with 4h EMA20 > EMA50 trend. |
| `W1_C03_BREAKOUT_RETEST_WITH_FLOW_04H` | `MULTIHOUR_BREAKOUT_RETEST_WITH_FLOW` | 4h | 2.0R | 1.2x | 4h | 4h 20-bar Donchian breakout within 12h, pullback retest within 0.5x ATR of breakout level, confirmed by 15m resumption with positive taker flow. |
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `ATR_EXPANSION_TREND_FOLLOW` | 12h | 2.0R | 2.0x | 6h | Volatility compression (ATR14/56 < 0.75) followed by sudden ATR expansion (> 1.25x) and 20-bar 1h channel breakout with chase gap limit (< 1.0x ATR). |
| `W1_C05_CROSS_SESSION_CONTINUATION_08H` | `CROSS_SESSION_CONTINUATION` | 8h | 2.0R | 1.5x | 8h | UTC London (08:00) and NY (13:00) session transitions with preceding 2 consecutive 1h bars of unidirectional momentum and flow confirmation. |
| `W1_C06_PERSISTENT_TREND_24H` | `PERSISTENT_TREND_24H` | 24h | 2.5R | 2.5x | 12h | Secular 24h trend following: 4h EMA20 > EMA50, 4h ADX > 25, positive cumulative 4h signed taker volume, shallow 15m pullback touching 1h EMA20. |

---

## 2. Execution Economics & Cost Models

- **BASE**: 8 bp maker/taker blended fee, 4 bp half-spread, 10 bp adverse slippage = **22 bp nominal roundtrip**.
- **STRESS**: 10 bp fee, 8 bp half-spread, 26 bp adverse slippage = **44 bp nominal roundtrip**.
- **Rules**:
  - Closed 1m bar $t$ (end $t+59999$ms) -> decision available -> enter at next open $t+60000$ms.
  - Same-minute stop before target collision priority.
  - Adverse stop gap filled at worse open; favorable target gap capped at limit target.
  - Timecap market exit at horizon bar close if neither stop nor target triggered.
  - Quarter-ATR gap veto: if entry open deviates from decision close by $> 0.25 \times \text{ATR}$, entry is aborted.

---

## 3. Strict Promotion Gate ($G_1$ to $G_7$)

Under 44 bp STRESS cost model:
1. Trade count $N \ge 100$.
2. Temporal breadth: $\ge 2$ calendar years, $\ge 6$ UTC months.
3. Equal-year weighted mean net bps $> 0$.
4. Profit Factor $\ge 1.15$.
5. Worst calendar year mean net bps $\ge -10.0$ bps.
6. Maximum MTM equity drawdown $\le 12.0\%$ (on 1000 USDT capital, 1x notional).
7. Block bootstrap (weekly / 14-day) 95% lower confidence bound of net bps $> 0$.
