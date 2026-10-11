# GEMINI GOAL A — BTC 4–24h Causally New Entry Discovery R2: Frozen Hypothesis & Experiment Plan

**Task ID:** `g2_goal_entry_discovery_r2`  
**Parent Start Commit SHA:** `55ac4c631c69f6edbd275462ad23e4486b9782ed`  
**Controller Authority SHA:** `c02743fddccdf517582c371a47e82d8dcbb05923`  
**Authority Document:** `reviews/v0.6/b_line/V06_G2_POST_EXIT_R1_THREE_GEMINI_PARALLEL_GOAL_PROGRAM_CONTROLLER_AUTHORITY_R1.md`  
**Controller Authority:** ChatGPT-0 (No cross-line authority)  
**Branch:** `feature/v06-bline-gemini-goal-entry-discovery-r2`  
**Allowed Write Paths:**
- `scripts/strategy_research/g2_goal_entry_discovery_r2/**`
- `tests/test_v06_g2_goal_entry_discovery_r2_*.py`
- `docs/strategy_research/g2_goal_entry_discovery_r2/**`
- `evidence/v0.6/b_line/g2_goal_entry_discovery_r2/**`

---

## 1. Scientific Mission & Novelty Mandate

The objective of Gemini Goal A is to discover **genuinely new entry signals** suitable for BTCUSDT USD-M 4–24h swings with friction-adjusted observed-Funding economics on official Binance Vision 2021–2023 archives.

### Strict Negative Constraints
1. **No Rehashing or Retuning:** No re-parameterization of previous W1/W2 entry thresholds, ATR multipliers, or Exit R1 contrasts.
2. **Data Boundary Enforcement:** Only authenticated Binance Vision BTCUSDT USD-M 2021-01 through 2023-12 UTC data is permitted. Zero access, list, or stat of `/root/workspace/project/Quant-agent/data` or `Quant-agent-sanitized`. All 2024–2026/private/protected owner/A-line/Forward/H39/H40/H41 data are strictly forbidden. No orders, Testnet, Live, or API credentials.
3. **No Optimization Loops:** No parameter grids, Bayesian optimization, genetic searches, or post-hoc threshold tuning. All candidate hypotheses and parameters are frozen prior to real-development replay.
4. **Finite Research Budget:** Maximum 6 candidate identities × 2 predetermined horizons (12h primary, 18h secondary) = $\le 12$ exploratory configurations. Here, exactly 4 distinct candidate families $\times 2$ horizons = 8 configurations are registered.

---

## 2. Frozen Candidate Hypotheses

We specify 4 distinct causal entry hypotheses spanning orthogonal market mechanisms:

### Family 1: Macro-to-Micro Trend Pullback Reclaim (`C01_MACRO_PULLBACK_RECLAIM`)
- **Falsifiable Economic Mechanism:**
  During persistent trending regimes, breakout entries suffer severe slippage and adverse selection at local climaxes. Instead, trend continuation edge occurs when a macro-aligned market (1h trend) undergoes an intraday liquidity retracement (15m dip below value), followed by a micro 5m volume-confirmed reclaim demonstrating resumption of aggressive participation.
- **Mathematical Specification:**
  - Macro Alignment (1h): Long if 1h EMA(20) > 1h EMA(50); Short if 1h EMA(20) < 1h EMA(50).
  - 15m Value Retracement: Within the last 4 completed 15m bars (1 hour), the 15m low dips below 15m EMA(20) (for Long; 15m high rises above EMA(20) for Short).
  - 5m Confirmation Reclaim: The latest completed 5m bar closes back above 5m EMA(20) (for Long; closes below for Short), with 5m volume > rolling 15m mean 5m volume, and positive signed taker flow ratio $\frac{2 \times \text{taker\_buy\_volume} - \text{volume}}{\text{volume}} > 0.0$ for Long ($< 0.0$ for Short).
- **Causal Timing:**
  - $t_{\text{event}}$: Timestamp of completed 5m confirmation bar close.
  - $t_{\text{decision}} = t_{\text{event}} + 60,000$ ms.
  - $t_{\text{entry}} = t_{\text{decision}} + 60,000$ ms (Open of 1m bar, exactly 2 minutes post-event).
- **Risk Stop & Target:**
  - Stop: Lowest low of the 4 retracement 15m bars $- 0.2 \times \text{ATR}_{1\text{h}}$ for Long; Highest high $+ 0.2 \times \text{ATR}_{1\text{h}}$ for Short.
  - Target: Fixed $2.0 \times \text{Initial Risk}$ ($R = 2.0$).
- **Configurations:**
  - `C01_MACRO_PULLBACK_RECLAIM_12H` (12h primary)
  - `C01_MACRO_PULLBACK_RECLAIM_18H` (18h sensitivity)

---

### Family 2: Failed Breakout Liquidity Exhaustion (`C02_FAILED_BREAKOUT_EXHAUSTION`)
- **Falsifiable Economic Mechanism:**
  When price breaks through an established multi-session extreme (24h high/low), aggressive market orders trigger retail stops and breakout buyers. When passive liquidity absorbs this surge without follow-through, trapped breakout participants are forced to unwind, producing a rapid counter-directional inventory flush.
- **Mathematical Specification:**
  - Range Definition: Rolling 24h high ($H_{24}$) and low ($L_{24}$) over completed 1m bars (1440 minutes). Requires range width $(H_{24} - L_{24}) \ge 1.5 \times \text{ATR}_{24\text{h}}$.
  - Penetration: A completed 15m bar pierces above $H_{24}$ by $\ge 0.1 \times \text{ATR}_{1\text{h}}$ (for Short candidate) or below $L_{24}$ by $\ge 0.1 \times \text{ATR}_{1\text{h}}$ (for Long candidate).
  - Reclaim / Exhaustion: Within 2 completed 15m bars following penetration, a 15m bar closes strictly back inside the range (close $< H_{24}$ for Short; close $> L_{24}$ for Long), accompanied by elevated 15m volume ($V_{15\text{m}} > 1.25 \times \text{mean}(V_{15\text{m}, 24\text{h}})$).
- **Causal Timing:**
  - $t_{\text{event}}$: Timestamp of completed 15m reclaim bar close.
  - $t_{\text{decision}} = t_{\text{event}} + 60,000$ ms.
  - $t_{\text{entry}} = t_{\text{decision}} + 60,000$ ms.
- **Risk Stop & Target:**
  - Stop: Breakout wick extreme $+ 0.25 \times \text{ATR}_{1\text{h}}$ for Short ($- 0.25 \times \text{ATR}_{1\text{h}}$ for Long).
  - Target: Fixed $2.0 \times \text{Initial Risk}$ ($R = 2.0$).
- **Configurations:**
  - `C02_FAILED_BREAKOUT_EXHAUSTION_12H` (12h primary)
  - `C02_FAILED_BREAKOUT_EXHAUSTION_18H` (18h sensitivity)

---

### Family 3: Post-Liquidation-Proxy Volatility Shock Exhaustion (`C03_VOLATILITY_SHOCK_EXHAUSTION`)
- **Falsifiable Economic Mechanism:**
  Violent, outsized single-bar displacements accompanied by extreme volume surges represent cascading liquidation flushes and stop cascades rather than informed directional accumulation. Once the forced liquidation flow depletes, order books replenish and price exhibits mean-reverting exhaustion.
- **Mathematical Specification:**
  - Volatility Shock Bar: A completed 15m bar with absolute candle body $|C - O| > 2.0 \times \text{ATR}_{1\text{h}}$ and 15m volume z-score $Z_{\text{vol}} > 3.0$ relative to rolling 24h 15m volume.
  - Stabilization Bar: The immediately following completed 15m bar fails to breach the shock bar's extreme wick, prints a range smaller than the shock bar, and reclaims at least $30\%$ of the shock bar's directional body.
  - Side: Long following downward shock exhaustion; Short following upward shock exhaustion.
- **Causal Timing:**
  - $t_{\text{event}}$: Timestamp of completed stabilization bar close.
  - $t_{\text{decision}} = t_{\text{event}} + 60,000$ ms.
  - $t_{\text{entry}} = t_{\text{decision}} + 60,000$ ms.
- **Risk Stop & Target:**
  - Stop: Shock bar extreme wick $\mp 0.25 \times \text{ATR}_{1\text{h}}$.
  - Target: Fixed $2.0 \times \text{Initial Risk}$ ($R = 2.0$).
- **Configurations:**
  - `C03_VOLATILITY_SHOCK_EXHAUSTION_12H` (12h primary)
  - `C03_VOLATILITY_SHOCK_EXHAUSTION_18H` (18h sensitivity)

---

### Family 4: Intraday Range Boundary Mean Reversion (`C04_INTRADAY_RANGE_REVERSION`)
- **Falsifiable Economic Mechanism:**
  In verified non-trending consolidation states, prices oscillate between statistical value boundaries. When price touches the outer perimeter of a multi-session range and prints an exhaustion wick back toward the interior, liquidity provision edge favors mean reversion toward the structural midline.
- **Mathematical Specification:**
  - Regime State Classification: 24-period Choppiness Index on 1h bars $> 55.0$ (confirming non-trending chop), and $\text{ATR}_{24\text{h}} / \text{ATR}_{7\text{d}} \le 1.1$ (non-expanding volatility).
  - Pre-known Range Limits: 24h Bollinger Bands (20-period 1h SMA $\pm 2.0$ standard deviations).
  - Boundary Rejection: Over the last 2 completed 15m bars, price touches the upper band (for Short) or lower band (for Long), and the latest 15m bar closes inside with a rejection wick (upper wick $> 40\%$ of bar range for Short; lower wick $> 40\%$ for Long).
- **Causal Timing:**
  - $t_{\text{event}}$: Timestamp of completed 15m rejection bar close.
  - $t_{\text{decision}} = t_{\text{event}} + 60,000$ ms.
  - $t_{\text{entry}} = t_{\text{decision}} + 60,000$ ms.
- **Risk Stop & Target:**
  - Stop: $0.5 \times \text{ATR}_{1\text{h}}$ outside the touched Bollinger Band boundary.
  - Target: Fixed $2.0 \times \text{Initial Risk}$ ($R = 2.0$).
- **Configurations:**
  - `C04_INTRADAY_RANGE_REVERSION_12H` (12h primary)
  - `C04_INTRADAY_RANGE_REVERSION_18H` (18h sensitivity)

---

## 3. Explicit Duplicate Map Against Past 48 Trials & 8 Exit Contrasts

| Candidate ID | Novel Causal Mechanism | Prior Trial Contrast | Structural Differentiation |
|---|---|---|---|
| `C01_MACRO_PULLBACK_RECLAIM` | 1h trend + 15m value dip + 5m taker flow reclaim | `W1_C04_ATR_EXPANSION_TREND_FOLLOW` / `W1_C01_MULTISCALE_TREND_ADOPTION` | W1_C04 was an aggressive high-channel ATR breakout. W1_C01 was a fixed MACD cross without multi-scale retracement/reclaim confirmation or flow volume filtering. |
| `C02_FAILED_BREAKOUT_EXHAUSTION` | Rolling 24h boundary penetration + 2-bar reclaim + volume absorption | `W2_C01_WIDE_72H_FAILED_BREAKOUT` / `W1_C03_BREAKOUT_RETEST` | W2_C01 required 72h lookbacks without volume absorption filters. W1_C03 traded continuation retests rather than immediate false-breakout fade. |
| `C03_VOLATILITY_SHOCK_EXHAUSTION` | Directional liquidation proxy ($>2\times \text{ATR}$, $Z_{\text{vol}} > 3.0$) + stabilization | `W2_C04_CLIMAX_VOLUME_TAKER_ABSORPTION` / `W2_C06_EXTREME_FLOW_EXHAUSTION` | W2_C04 and W2_C06 used CVD divergences and 5m taker exhaustion without explicit statistical volume shock z-scores and return displacement thresholds. |
| `C04_INTRADAY_RANGE_REVERSION` | 1h Chop Index $>55$ + 20-period BB boundary touch with $\ge 40\%$ rejection wick | `W1_C02_RANGE_MEAN_REVERT_WITH_VOLUME` / `W4_C03_BOUNDED_48H_RANGE_REJECTION` | Prior range trials relied on linear Bollinger touches without formal Choppiness Index regime classification and wick rejection proportion gates. |

---

## 4. Execution, Account & Accounting Contracts

1. **Account Parameters:**
   - Initial Capital: $1,000.00$ USDT cash.
   - Exposure Limit: 1x maximum exposure. Budget cap = $0.95 \times \min(\text{cash}, 1000.00)$.
   - Single-Position Exclusivity: Exactly one open position per account at any time.
   - Quantity Lotting: $0.001$ BTC ($\text{LOT} = 0.001$), $\text{MIN\_NOTIONAL} = 5.0$ USDT.
   - Price Tick: $0.1$ USDT ($\text{TICK} = 0.1$).
2. **Causal Fills & Friction:**
   - Adverse Entry: $\text{effective\_entry} = \text{\_effective}(\text{raw\_open}, \text{side}, \text{cost}, \text{entry}=\text{True})$.
   - Adverse Exit: $\text{effective\_exit} = \text{\_effective}(\text{raw\_exit}, \text{side}, \text{cost}, \text{entry}=\text{False})$.
   - Gap Veto: If $|\text{raw\_open} - \text{decision\_close}| > 0.25 \times \text{ATR}_{1\text{h}}$, entry is vetoed.
   - Collision Priority: If both stop and target are touched in the same 1m bar, **Stop Loss takes precedence**.
   - Cooldown: 4 hours post-exit. $\text{next\_allowed} = \max(\text{exit\_ack\_at}, \text{exit\_at} + 4 \times 3600,000)$.
   - Cost Tiers: BASE ($22$ bp roundtrip: $6$ bp fee, $4$ bp spread, $3$ bp slip) and STRESS ($44$ bp roundtrip: $12$ bp fee, $8$ bp spread, $6$ bp slip; STRESS primary).
3. **Signed Observed Funding:**
   - Applied at $00:00$, $08:00$, $16:00$ UTC settlements.
   - Cash delta: $-\text{side} \times \text{rate} \times \text{quantity} \times \text{mark\_price}$.
   - Mark price taken from latest completed 1m Mark close.

---

## 5. Statistical Inference & Terminal Policy

- **Matched Baseline Controls:** Every candidate event is paired with a counterfactual opposite-side execution to isolate directional edge from generic market drift.
- **Simultaneous MaxT Bootstrap:** 7-day and 14-day calendar-block bootstrap across all 8 exploratory configurations, $B = 10,000$ draws, fixed seed = 42. Preserves empty blocks.
- **Predeclared Terminals:**
  - `ENTRY_GOAL_EXPLORATORY_COMPLETE_NO_PROMOTION`: Full frozen bounded run completed with honest diagnostics.
  - `ENTRY_GOAL_NO_SUPPORTED_NEW_LEADS`: Full run completed, no candidate passes cost-adjusted statistical hurdles.
  - `ENTRY_GOAL_FAIL_CLOSED`: Data integrity or accounting defect discovered.
