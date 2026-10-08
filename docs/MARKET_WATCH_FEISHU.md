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
1. **PIT & Causal Confirmation**: Indicators and structures are computed **strictly** on confirmed closed candles (`latest_closed_bar`). Forming candles are isolated to the `latest_bar` field solely for live display and are never used to confirm triggers. Same-candle breakout + retest is rejected; breakout requires Bar N closed confirmation, and retest requires subsequent closed Bar N+1..N+k confirmation.
2. **Deterministic Hashing**: Every evaluated snapshot produces a deterministic 16-character SHA-256 hash (`snapshot_hash`) for auditable replay. Config produces a deterministic SHA-256 hash (`compute_market_watch_config_hash`) and policy version `0.5.0-r1`.
3. **Graceful Failure Isolation & Health**: Failure to retrieve core candles marks a symbol `FAILED` without crashing the universe scan. Failure of optional derivatives data or partial endpoint failures marks the symbol `DEGRADED`, continuing analysis on available price action. Candle staleness (> 1h) also marks health as `DEGRADED`.
4. **DataConfig Propagation**: The subsystem directly inherits and respects `AppConfig.data` (REST base URLs, request timeouts, and source clock bounds).

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

### 2. Multi-Bar Sequential Breakout Retest (`BREAKOUT_RETEST`)
- **Condition**: 1H resistance cleanly breached. Multi-bar state machine enforces:
  - **Bar N**: Closed 15m candle confirms breakout above resistance (`close > resistance`), moving breakout state to `BREAKOUT_CONFIRMED`. Does not trigger entry on Bar N.
  - **Bar N+1..N+k**: Subsequent closed candles retest the breakout level within ATR tolerance ($0.35 \times \text{ATR}$) without breaching invalidation.
- **Trigger**: Retest holds and closed 15m bar forms rejection wick/green close above resistance, transitioning to `RETEST_CONFIRMED`.
- **Failed Breakout Memory (R1-04)**: If a level previously failed within TTL (`failed_level_ttl_ms`), subsequent breakouts require $1.3\times$ higher ATR breakout buffer and higher volume Z-score ($\ge 1.5$) to confirm.

### 3. Failed Breakout / Breakdown Watch (`FAILED_BREAKOUT`, `FAILED_BREAKDOWN`)
- **Condition**: Candle wicks beyond 1H resistance/support but closes back inside the range (false breakout).
- **Derivatives Confirmation**: If OI expanded during the wick rejection and funding is high, longs/shorts are trapped.
- **Action**: Issues high-priority **`WATCH`** alert with levels for potential counter-reversal and writes to failed memory store.

### 4. Volatility Expansion (`VOLATILITY_EXPANSION`)
- **Condition**: Requires prior Bollinger Band width compression window (`vol_compression_min_bars` bars in bottom 25th percentile).
- **Trigger**: Closed structure breakout beyond recent swing level combined with simultaneous volume surge ($\text{Volume Z} \ge 1.0$) and ATR percentile expansion ($\ge 0.70$). Rejects simple EMA crossings without prior compression.

### 5. Range Mean Reversion (`RANGE_MEAN_REVERSION`)
- **Condition**: 1H and 4H regimes are `RANGE` ($\text{ADX} < 20$).
- **Trigger**: Price tests lower/upper range boundary with RSI normalization.

---

## 7. Benchmark Context & Altcoin Gating

Altcoins do not move in a vacuum; BTC and ETH macro shocks override idiosyncratic alt setups:
- **Automatic Benchmark Dependency Loading**: When single altcoins (e.g. `LINKUSDT`) are requested, the scanner automatically loads `BTCUSDT` and `ETHUSDT` dependencies in the background for relative strength and gating calculations, but emits reports only for the requested target symbols.
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
- **Anti-Falling-Knife Guard**: If market price breaches the grid's lower bound, the policy switches to **`PAUSE`** and emits a high-priority `RISK` alert (`LOWER_BOUND_BREACHED`).
- **Independent Alert Emission (R1-03)**: Grid change alerts (e.g., transition to/from `PAUSE`, lower bound breach, or boundary delta $\ge 2\%$) are emitted even if the directional decision is `WAIT`.

---

## 9. Transparent Opportunity Ranking

Symbols are ranked using a 0–100 opportunity score:
$$\text{Score} = \sum (w_i \times S_i) - \text{Penalties}$$

### Direction-Aware Scoring (R1-02)
- **Directional Alignment**: Scoring explicitly differentiates `LONG`, `SHORT`, and `WAIT`.
  - `LONG`: rewards `HH_HL` structures and `HEALTHY_LONG_BUILD`.
  - `SHORT`: rewards `LH_LL` structures and `HEALTHY_SHORT_BUILD`; penalizes `HEALTHY_LONG_BUILD`.
  - `WAIT`: capped at $\le 25.0$ and discounted by 50%.
- **Multi-TF Relative Strength (R1-11)**: Weights 15m (20%), 1h (50%), and 4h (30%) returns evaluated against BTC, ETH, and universe median.

### Fatal Vetoes (Precede Numerical Score)
A symbol with a fatal veto has its score set to **0.0** regardless of other metrics:
1. `FATAL_VETO_EXTREME_OVEREXTENSION`: Distance from EMA20 $> 3.2 \times \text{ATR}$.
2. `FATAL_VETO_INSUFFICIENT_NET_RR`: Net RR $< 1.5$.
3. `FATAL_VETO_CONFIRMED_HTF_CONFLICT`: Trade direction directly opposes confirmed 4H trend.
4. `FATAL_VETO_EXCESSIVE_SPREAD`: Bid-ask spread exceeds safety limits.

---

## 10. State Persistence, Lifecycle, & Noise Suppression

Implemented in SQLite (`market_watch.db`):
- `market_watch_symbol_state`: Tracks current regime, directional and grid decisions, recent support/resistance, breakout state machine, and lifecycle timestamps (`created_bar_end_ms`, `armed_bar_end_ms`, `triggered_bar_end_ms`, `age_bars`).
- `market_watch_assessments`: Immutable audit log of every scan evaluation, storing `policy_version` and `config_hash`.
- `market_watch_shadow_records`: Forward performance monitoring for shadow policy evaluation.
- **Signal Lifecycle (R1-05)**:
  - `CANDIDATE`: Candidate setup identified.
  - `ARMED`: Reached when breakout confirms on Bar N (waiting retest) or marginal setup forms near readiness. Reachable under default configuration.
  - `TRIGGERED`: Reached when closed candle satisfies entry quality `GOOD` or `EXCELLENT`.
  - `INVALIDATED`: Setup breached invalidation level.
  - `EXPIRED`: Signal age exceeds `max_signal_age_bars` without triggering.
- **Deduplication Engine**: Generates a composite SHA-256 fingerprint (`alert_fingerprint`). If consecutive scans produce the same fingerprint, notifications are suppressed (`NO_NOTIFICATION_IDENTICAL_STATE`).

---

## 11. Interactive Feishu Cards

Alert cards are formatted as interactive JSON cards sent via signed webhooks:
- **Header Color Scheme**:
  - `green`: Actionable `LONG` setup.
  - `red`: Actionable `SHORT` setup.
  - `blue`: `WATCH` / Armed setup or Range Grid recommendation.
  - `orange`: Risk warning (Signal Invalidated, Deleveraging shock, Knife breach).
- **Completeness & Hygiene (R1-13)**: Includes latest price, 24h change %, 1h regime, 1h ATR, key support/resistance levels, derivatives state, funding rate, and 1h/12h OI change. When directional decision is `WAIT`, fake 0-price directional plans are omitted.
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

# 5. Shadow observation tracking and resolution
quantctl market-watch shadow-status
quantctl market-watch shadow-resolve

# 6. Send test alert to Feishu to verify webhook and signature
quantctl market-watch test-feishu --symbol BTCUSDT
```

---

## 13. Shadow Evaluation & Forward Excursions

To validate policy efficacy without risking capital or lookahead bias:
1. **Auto-Recording**: Whenever a symbol enters `ARMED` or `TRIGGERED`, a shadow record is logged exactly once per signal lifecycle.
2. **Causal Forward Resolution**: `shadow-resolve` iterates pending records and evaluates subsequently closed candles without lookahead:
   - **MFE (Maximum Favorable Excursion)**: Maximum potential profit in R-multiples.
   - **MAE (Maximum Adverse Excursion)**: Maximum drawdown in R-multiples.
   - **Target Reached**: Whether TP1, TP2, or SL was reached first.
   - **Net R Realization**: Standardized return in units of initial risk.

---

## 14. Forward Evidence Runtime Semantics (`FORWARD_EVIDENCE_V1`)

The Market Watch shadow evaluation subsystem operates under strict point-in-time and causal correctness rules codified in `FORWARD_EVIDENCE_V1`:

### A. Point-in-Time Signal Discovery
A signal becomes known strictly at `signal_time_ms`, which matches the closed candle's `decision_time_ms`. Signals and shadow observations are never back-dated to bar open or unclosed candle states.

### B. Post-Signal Fill Semantics
Fills can only occur strictly post-signal ($t \ge \text{signal\_time\_ms}$). A trade cannot fill in the bar that emitted the signal prior to the signal being generated.

### C. Bounded Entry Window
The entry window is strictly bounded to `entry_window_bars` 15m bars (default 4 bars = 60 minutes). If price does not touch the entry zone within `entry_window_end_ms`, the setup expires unfilled.

### D. No-Fill Requires Complete Data Coverage
An entry window expiration can only resolve to `NO_FILL` if the historical data series provides complete, gap-free candle coverage across the entire entry window. If any data gaps exist, the observation remains open as `PENDING_DATA_GAP` (`ENTRY_WINDOW_DATA_GAP`) rather than assuming a false no-fill.

### E. Fill-Anchored Horizon Freezing
Late fills receive the full forward evaluation horizon ($H = \text{evaluation\_horizon\_bars} \times 15\text{m}$). The evaluation start is anchored at `fill_time_ms` ($\text{eval\_start\_ms} = \text{fill\_time\_ms}$), and the evaluation end is frozen at $\text{eval\_end\_ms} = \text{fill\_time\_ms} + H$. Once filled, these boundaries are immutable and never shift on subsequent solver passes.

### F. Terminal Target TP1
For Forward Evidence V1, Take-Profit 1 (TP1) is the terminal profit target. When price hits TP1 post-fill, the shadow observation resolves immediately with `terminal_reason = "TP1"` and terminal gross R calculated from entry to TP1 distance.

### G. TP2 as Excursion Metric Only
Take-Profit 2 (TP2) serves strictly as an excursion tracking metric (`tp2_hit = True`) and does not represent an active partial scale-out or secondary trailing stop in V1.

### H. 1-Minute Chronological Path Disambiguation
When available, 1-minute historical klines are queried to disambiguate intrabar fill timing and same-bar target/stop touches within 15-minute candles. The trade fill candle evaluates subsequent 1m bars after fill time for immediate TP/SL hits.

### I. 15-Minute STOP_FIRST Ambiguity Fallback
If 1-minute candle data is unavailable or if a 1-minute candle itself touches both TP1 and SL, the resolver strictly falls back to conservative `FIFTEEN_MINUTE_STOP_FIRST` resolution, counting the stop loss as hit first.

### J. Zero Fake Outcomes from Data Gaps
Maturity timeouts require complete candle coverage over the entire evaluation horizon. Missing candles prevent resolution and mark the observation as `PENDING_DATA_GAP` (`OUTCOME_WINDOW_DATA_GAP`). Data gaps never produce artificial `TIMEOUT` outcomes.

### K. Legacy Evidence Isolation
Historical shadow observations lacking `FORWARD_EVIDENCE_V1` metadata (or created prior to R2.3 schema migration) resolve as `LEGACY_INELIGIBLE`. They are strictly excluded from active trading performance metrics, win rates, and profit factors so legacy data cannot distort current policy evidence.

### L. Strict Shadow Advisory Boundary
The Market Watch subsystem is strictly advisory and operates under `EXPERIMENTAL_OPERATIONAL_MARKET_WATCH`. It maintains zero live exchange order routing, zero private API access, and zero modification of frozen research protocols (H40).

