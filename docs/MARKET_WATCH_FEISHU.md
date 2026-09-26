# MarketWatch & Stateful Trading Policy Subsystem (`EXPERIMENTAL_OPERATIONAL_MARKET_WATCH`)

## 1. Overview & System Mission

The `market_watch` subsystem is an isolated operational market-monitoring and stateful decision-support policy engine designed for real-time cryptocurrency markets (Binance USDT Perpetual & Spot).

### Core Mission
- **Signal Quality Over Trade Frequency**: The system explicitly prioritizes high-confidence setups and says **WAIT** when conditions are noisy, overextended, crowded, or ambiguous.
- **Anti-Chasing & Anti-False-Breakout Invariants**: Enforces strict mathematical limits on distance from mean moving averages, requires closed-bar volume and structure confirmations, and penalizes trap-like derivatives regimes.
- **Dual Policy Recommendations**: Independently evaluates **Directional Playbooks** and **Range Grid Policies**, giving operators both momentum/breakout guidance and mean-reversion range boundaries.
- **Strict Advisory Boundary**: The subsystem operates strictly under the `EXPERIMENTAL_OPERATIONAL_MARKET_WATCH` governance classification. It does **not** place live orders, execute trades, or mutate any frozen research protocols (H40, P3, unblinded preregistrations).

---

## 2. Architecture & Design Principles

```
                       ┌────────────────────────────────────────┐
                       │     Binance REST & Futures Public API  │
                       └───────────────────┬────────────────────┘
                                           │ Read-only Klines & Derivatives
                                           ▼
                       ┌────────────────────────────────────────┐
                       │       MarketWatchScanner (Worker)      │
                       │   - Robust Symbol Degradation Handling │
                       └───────────────────┬────────────────────┘
                                           │
         ┌─────────────────────────────────┼────────────────────────────────┐
         ▼                                 ▼                                ▼
┌───────────────────────┐       ┌───────────────────────┐       ┌───────────────────────┐
│ Multi-Timeframe (PIT) │       │   Derivatives Regime  │       │   Benchmark Context   │
│ 4H: Macro Trend/Regime│       │ OI Delta (1h/4h/12h)  │       │ BTC Volatility Shock  │
│ 1H: Operational Setup │       │ Funding Rates/Crowding│       │ Altcoin Long Gating   │
│ 15M: Execution Trigger│       │ Taker Buy/Sell Ratios │       │ Relative Strength     │
└──────────┬────────────┘       └──────────┬────────────┘       └──────────┬────────────┘
           │                               │                               │
           └───────────────────────────────┼───────────────────────────────┘
                                           ▼
                       ┌────────────────────────────────────────┐
                       │           Decision Engine              │
                       │ - 5 Deterministic Playbooks            │
                       │ - Entry Quality & Net RR Friction      │
                       │ - Range Grid Policy & Knife Guard      │
                       │ - Fatal Vetoes & Opportunity Score     │
                       └───────────────────┬────────────────────┘
                                           │
                 ┌─────────────────────────┴─────────────────────────┐
                 ▼                                                   ▼
┌─────────────────────────────────┐                 ┌─────────────────────────────────┐
│  State Store (SQLite Database)  │                 │    Interactive Feishu Alert     │
│ - Last State & Fingerprint Dedupe│                │ - Green/Red/Blue/Orange Theme   │
│ - Audit Trail & Failed BO Memory│                 │ - Directional & Grid Cards      │
│ - Shadow Excursion Tracking     │                 │ - Cryptographic Secret Signing  │
└─────────────────────────────────┘                 └─────────────────────────────────┘
```

### Safety Invariants
1. **PIT & Causal Confirmation**: Indicators and structures are computed **strictly** on confirmed closed candles (`latest_closed_bar`). Forming candles are isolated to the `latest_bar` field solely for live display and are never used to confirm triggers.
2. **Deterministic Hashing**: Every evaluated snapshot produces a deterministic 16-character SHA-256 hash (`snapshot_hash`) for auditable replay.
3. **Graceful Failure Isolation**: Failure to retrieve core candles marks a symbol `FAILED` without crashing the universe scan. Failure of optional derivatives data marks the symbol `DEGRADED`, continuing analysis on available price action.

---

## 3. Multi-Timeframe Hierarchy

| Timeframe | Role | Indicators & Metrics | Responsibility |
|---|---|---|---|
| **4H** | Macro Anchor | EMA20, EMA50, ADX, Pivots, Structure | Defines overarching market regime (`TREND_UP`, `TREND_DOWN`, `RANGE`, `TRANSITION`). Long setups vetoed if 4H is in confirmed downtrend. |
| **1H** | Operational Setup | EMA20, EMA50, ATR, Structure, ROC | Identifies primary swing levels, breakouts, pullbacks, and range grid boundaries. |
| **15M** | Execution Trigger | Volume Z-Score, Bollinger Width, Closed Bar | Confirms candle close above/below key level with re-acceleration and volume confirmation. |

---

## 4. Derivatives Regime State Machine

The derivatives classifier combines price return, open interest change across multiple horizons (1h, 4h, 12h), funding rates, and account positioning:

```
                          ┌─────────────────────────────┐
                          │   Price & OI Observation    │
                          └──────────────┬──────────────┘
                                         │
         ┌───────────────────────────────┼───────────────────────────────┐
         │                               │                               │
         ▼                               ▼                               ▼
Price ▲ / OI ▲                   Price ▼ / OI ▲                   Price ▲ / OI ▼
[HEALTHY_LONG_BUILD]             [HEALTHY_SHORT_BUILD]            [SHORT_COVERING]
- New capital driving trend      - Fresh aggressive shorts        - Low continuation quality
- Normal funding (< 0.03%)       - Longs under pressure           - Bear-squeeze unwinding
         │                               │                               │
         ▼                               ▼                               ▼
Price ▼ / OI ▼                   Funding > 0.03% / TTP > 2.0      OI 1h Drop < -4%
[LONG_LIQUIDATION]               [LONG_CROWDING]                  [DELEVERAGING]
- Long margin calls / stop run   - Long positioning over crowded  - Violent capital exit
- Do not blindly chase short     - Vulnerable to long squeeze     - Grid & trading paused
```

---

## 5. Entry Quality & Anti-Chasing Logic

The subsystem prevents buying at swing tops or shorting into exhaustion:

### Distance from Mean (EMA20 & EMA50)
- Distance from 15m/1h EMA20 is measured in ATR multiples:
  $$\text{Dist}_{\text{EMA20}} = \frac{|\text{Price} - \text{EMA20}|}{\text{ATR}}$$
- **Normal** ($\le 2.2 \times \text{ATR}$): Favorable entry location.
- **Elevated** ($> 2.2 \times \text{ATR}$): Marginal entry; setup confidence downgraded.
- **Extreme** ($> 3.2 \times \text{ATR}$): **`DO_NOT_CHASE` VETO**. Setup is rejected, state forces `WAIT` for mean reversion/pullback.

### Real-World Net Risk/Reward
Gross RR is heavily penalized by trading frictions before an actionable signal is emitted:
- **Taker fee**: 0.05% per side (0.10% round trip).
- **Estimated slippage**: 2.0 bps per side.
- **Adverse funding penalty**: Estimated holding funding drag.
- **Invariable Rule**: If **Net RR < 1.5**, directional decision defaults to `WAIT`.

---

## 6. Supported Operational Playbooks

### 1. Trend Pullback (`TREND_PULLBACK`)
- **Condition**: 4H and 1H trends aligned. 15m pulls back into EMA20/EMA50 support buffer without breaking structural swing lows.
- **Trigger**: Closed 15m bar closes back above EMA20 with green candle (`close > open`).
- **Target**: TP1 at previous 1H swing high; TP2 at extension.

### 2. Breakout Retest (`BREAKOUT_RETEST`)
- **Condition**: 1H resistance cleanly breached. 15m retests breakout level within ATR tolerance ($0.35 \times \text{ATR}$).
- **Trigger**: Retest holds and closed 15m bar forms rejection wick/green close above resistance.
- **Filter**: If OI contracts during breakout, flags `BREAKOUT_LOW_PARTICIPATION` risk.

### 3. Failed Breakout / Breakdown Watch (`FAILED_BREAKOUT`, `FAILED_BREAKDOWN`)
- **Condition**: Candle wicks beyond 1H resistance/support but closes back inside the range (false breakout).
- **Derivatives Confirmation**: If OI expanded during the wick rejection and funding is high, longs/shorts are trapped.
- **Action**: Issues high-priority **`WATCH`** alert with levels for potential counter-reversal.

### 4. Volatility Expansion (`VOLATILITY_EXPANSION`)
- **Condition**: Bollinger Band width compressed in bottom 25th percentile (`bb_width_percentile <= 0.25`).
- **Trigger**: Sudden volume surge ($\text{Volume Z} \ge 1.0$) and ATR percentile expansion ($\ge 0.70$) breaking band edges on closed bar.

### 5. Range Mean Reversion (`RANGE_MEAN_REVERSION`)
- **Condition**: 1H and 4H regimes are `RANGE` ($\text{ADX} < 20$).
- **Trigger**: Price tests lower/upper range boundary with RSI normalization.

---

## 7. Benchmark Context & Altcoin Gating

Altcoins do not move in a vacuum; BTC and ETH macro shocks override idiosyncratic alt setups:
- **BTC Downside Volatility Shock**: If BTC drops $> 1.5\%$ in 1h with elevated ATR percentile ($> 85\%$), benchmark context switches to `BTC_VOLATILITY_SHOCK` or `MARKET_RISK_OFF`.
- **Altcoin Long Veto**: All Altcoin `LONG` recommendations are automatically vetoed and switched to `WAIT`.
- **Exceptional Relative Strength Exemption**: An altcoin long may bypass the veto only if:
  1. 1h relative strength vs BTC $\ge +2.5\%$.
  2. Entry Quality is `GOOD` or `EXCELLENT`.
  3. Net RR $\ge 2.0$.

---

## 8. Range Grid Policy & Anti-Falling-Knife Protection

The subsystem generates grid parameter recommendations independently from directional setups:
- **Clean Range Regime**: When ADX is low and market is in `RANGE`, computes arithmetic grid levels between structural support and resistance with ATR padding.
- **Minimum Grid Step**: Enforces that each grid step generates $\ge 0.25\%$ profit net of double-sided fees.
- **Anti-Falling-Knife Guard**: If market price breaches the grid's lower bound, the policy switches to **`PAUSE`**. The lower bound is **never** blindly lowered to chase falling prices.
- **Boundary Delta Alert Rule**: Minor boundary shifts ($< 2\%$) do not alert operators. Only boundary adjustments $\ge 2\%$ or state changes trigger notifications.

---

## 9. Transparent Opportunity Ranking

Symbols are ranked using a 0–100 opportunity score:
$$\text{Score} = \sum (w_i \times S_i) - \text{Penalties}$$

### Scoring Components
- **Trend Quality** (20%): ADX strength and EMA slope alignment.
- **Structure Quality** (15%): Confirmed Higher-Highs/Higher-Lows structure.
- **Entry Quality** (20%): Proximity to support and mean.
- **Derivatives Confirmation** (15%): Healthy OI build vs deleveraging.
- **Participation Quality** (10%): Volume Z-score and Taker ratio.
- **Relative Strength** (10%): Excess return vs BTC, ETH, and universe median.
- **Net RR Quality** (10%): Ratio of net reward to risk.

### Fatal Vetoes (Precede Numerical Score)
A symbol with a fatal veto has its score set to **0.0** regardless of other metrics:
1. `FATAL_VETO_EXTREME_OVEREXTENSION`: Distance from EMA20 $> 3.2 \times \text{ATR}$.
2. `FATAL_VETO_INSUFFICIENT_NET_RR`: Net RR $< 1.5$.
3. `FATAL_VETO_CONFIRMED_HTF_CONFLICT`: Trade direction directly opposes confirmed 4H trend.
4. `FATAL_VETO_EXCESSIVE_SPREAD`: Bid-ask spread exceeds safety limits.

---

## 10. State Persistence & Noise Suppression

Implemented in SQLite (`market_watch.db`):
- `market_watch_symbol_state`: Tracks current regime, directional and grid decisions, recent support/resistance, and memory of recent failed breakout/breakdown levels.
- `market_watch_assessments`: Immutable audit log of every scan evaluation.
- `market_watch_shadow_records`: Forward performance monitoring for shadow policy evaluation.
- **Deduplication Engine**: Generates a composite SHA-256 fingerprint (`alert_fingerprint`). If consecutive scans produce the same fingerprint, notifications are suppressed (`NO_NOTIFICATION_IDENTICAL_STATE`).

---

## 11. Interactive Feishu Cards

Alert cards are formatted as interactive JSON cards sent via signed webhooks:
- **Header Color Scheme**:
  - `green`: Actionable `LONG` setup.
  - `red`: Actionable `SHORT` setup.
  - `blue`: `WATCH` / Armed setup or Range Grid recommendation.
  - `orange`: Risk warning (Signal Invalidated, Deleveraging shock, Knife breach).
- **Content Blocks**: Symbol badge, Decision, Setup type, Price entry zone, Stop Loss, TP1/TP2, Net RR, Derivatives regime, Benchmark context, Evidence bullet list, Risks bullet list.
- **Security**: Feishu webhook secret is verified and signed using SHA-256 HMAC timestamp signing; secrets are never logged or exported.

---

## 12. CLI Command Reference

The subsystem is fully operable via `quantctl market-watch`:

```bash
# 1. Run universe scan across default or specified symbols
quantctl market-watch scan --all --notify
quantctl market-watch scan --symbols BTCUSDT,ETHUSDT,SOLUSDT

# 2. View current state of all tracked symbols
quantctl market-watch status
quantctl market-watch status --symbol BTCUSDT

# 3. View top-ranked opportunities
quantctl market-watch top --limit 5

# 4. Explain detailed multi-timeframe assessment for a single symbol
quantctl market-watch explain --symbol SOLUSDT

# 5. Send test alert to Feishu to verify webhook and signature
quantctl market-watch test-feishu --symbol BTCUSDT
```

---

## 13. Shadow Evaluation & Forward Excursions

To validate policy efficacy without risking capital or lookahead bias:
1. Whenever an actionable decision (`LONG` / `SHORT`) is determined, a shadow record is logged.
2. In subsequent scans, `ShadowEvaluationManager` evaluates forward price candles against entry, stop loss, and targets:
   - **MFE (Maximum Favorable Excursion)**: Maximum potential profit in R-multiples.
   - **MAE (Maximum Adverse Excursion)**: Maximum drawdown in R-multiples.
   - **Target Reached**: Whether TP1, TP2, or SL was reached first.
   - **Net R Realization**: Standardized return in units of initial risk.
