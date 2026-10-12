# Gemini Goal A — BTC Flow–Funding–Price Response New Entry Alpha Discovery R1: Frozen Execution Method

## 1. Governance & Protocol Identity
- **Task ID**: `V06_G2_GEMINI_A_FLOW_FUNDING_ENTRY_R1`
- **Controller Dispatch SHA**: `99df4ed8e820984d69d7b895be8808b892ed7f5f`
- **Authorized Baseline SHA**: `55ac4c631c69f6edbd275462ad23e4486b9782ed`
- **Branch**: `feature/v06-bline-gemini-g2-flow-funding-entries-r1`
- **Execution Namespace**: `g2_flow_funding_entries_r1`
- **Scratch Directory**: `/tmp/btc-g2_flow_funding_entries_r1`
- **Protocol**: Two-stage binding freeze. Stage 1 freezes code, synthetic tests, method specification, and cryptographic contract hashes prior to running any empirical 2021–2023 historical backtests. Stage 2 executes one bounded evaluation pass without parameter tuning. Stage 3 commits immutable evidence and report.

## 2. Scientific Motivation & Structural Distinctions
Prior entry research across Waves 1–4 evaluated 48+ exploratory hypotheses, 8 Goal A R1 variants, and 8 exit horizon variations. W1/W2 entries failed out-of-sample and multi-year regime persistence. Former Goal A C04 was invalidated by a monthly ATR reset defect that caused non-equivalence between research and production.

This study explores **three genuinely distinct microstructure and crowding mechanisms** that do NOT depend on unadmitted L2 order books or unauthenticated open interest:
1. **F1: Aggressor-Flow / Price Response Divergence (Absorption/Exhaustion)**
   - *Economic Rationale*: Taker trades represent aggressive market orders demanding immediate liquidity. When aggressive buyers dominate volume over a completed 1-hour window (taker-buy volume $\ge 60\%$ of total volume, signed flow $\ge +0.20$), but price fails to make upward progress ($\Delta P_{1h} \le 0$), aggressive buyers are absorbed by resting limit sell orders (passive supply). Conversely, heavy aggressive selling without price depreciation ($\Delta P_{1h} \ge 0$) indicates passive accumulation. Signals enter in the direction of passive absorption (SHORT on buyer absorption, LONG on seller absorption).
   - *Source Provenance*: Binance USD-M BTCUSDT 1m kline archives contain authenticated column 9 (`taker_buy_volume`). Plain OHLC inference of volume delta is strictly forbidden.
2. **F2: Realized Funding Crowding Sign Reversal**
   - *Economic Rationale*: Official USDT-M funding rates settle every 8 hours (00:00, 08:00, 16:00 UTC). When the settled rate reverses sign across consecutive periods (positive to negative, or negative to positive), leveraged positioning has washed out and speculative crowding has flipped. Combined with backward-looking 8-hour price progress confirmation, entries capture the subsequent multi-session rebalancing.
   - *Point-in-Time Publication Rule*: Historical settlement publication time is officially labeled `UNKNOWN_CURRENT_ARCHIVE_IS_RETROSPECTIVE`. An explicit conservative $\ge 1$-minute lag is enforced ($T_{decision} = T_{settle} + 1\text{m}$, $T_{entry} = T_{settle} + 2\text{m}$).
3. **F3: Mark–Last Dislocation and Flow Repair**
   - *Economic Rationale*: The Mark price represents the fair spot index median with moving basis, while the Last price represents trades in the perpetual contract. When Last trades at a sustained dislocation from Mark over a completed 1-hour window ($|B_{1h}| \ge 3\text{ bps}$), and taker flow begins driving prices back toward fair value, entries capture basis convergence.

## 3. Pre-Registered Research Budget (6 Candidate Configurations)
Exactly 3 named identities evaluated at 2 fixed horizons (12h and 18h) = 6 configurations. No parameter searching, no alt horizons.

| Candidate ID | Family | Horizon | Stop Loss | Target R | Cooldown | Decision Clock |
|---|---|---|---|---|---|---|
| `F1_AGGRESSOR_FLOW_ABSORPTION_12H` | F1 | 12h | $1.5 \times ATR_{14}$ | $2.0 \times R$ | 4h | Hourly closed bar ($T+0\text{m}$) |
| `F1_AGGRESSOR_FLOW_ABSORPTION_18H` | F1 | 18h | $1.5 \times ATR_{14}$ | $2.0 \times R$ | 4h | Hourly closed bar ($T+0\text{m}$) |
| `F2_REALIZED_FUNDING_REVERSAL_12H` | F2 | 12h | $1.5 \times ATR_{14}$ | $2.0 \times R$ | 4h | Settled funding $+1\text{m}$ lag |
| `F2_REALIZED_FUNDING_REVERSAL_18H` | F2 | 18h | $1.5 \times ATR_{14}$ | $2.0 \times R$ | 4h | Settled funding $+1\text{m}$ lag |
| `F3_MARK_LAST_DISLOCATION_REPAIR_12H` | F3 | 12h | $1.5 \times ATR_{14}$ | $2.0 \times R$ | 4h | Hourly closed bar ($T+0\text{m}$) |
| `F3_MARK_LAST_DISLOCATION_REPAIR_18H` | F3 | 18h | $1.5 \times ATR_{14}$ | $2.0 \times R$ | 4h | Hourly closed bar ($T+0\text{m}$) |

## 4. Feature Formulas & Continuous Causal Timeline
- **Timeline**: 1,576,800 contiguous 1m bars from 2021-01-01 00:00:00 UTC to 2023-12-31 23:59:00 UTC.
- **Warmup**: January 2021 (744 hours) serves as causal warmup. Evaluation strictly covers 2021-02-01 through 2023-12-31 (35 folds).
- **Wilder's ATR(14)**: Continuous calculation across all 26,280 hours. Zero state reset at month or year boundaries.
- **Signed Flow Ratio**: $S_t = \frac{2 \cdot TBV_t - V_t}{\max(V_t, 10^{-6})} \in [-1.0, 1.0]$.
- **1h Basis**: $B_t = \frac{\overline{P}_{last, 1h} - \overline{P}_{mark, 1h}}{\overline{P}_{mark, 1h}}$.
- **Execution Clocks**:
  - $T_{event} = T_{decision} - 1\text{m}$ (last closed bar of feature window).
  - $T_{decision}$: when bar/settlement window is completed and confirmed.
  - $T_{entry} = T_{decision} + 1\text{m}$ ($+2\text{m}$ for F2): order filled at the open of the entry minute bar.

## 5. Execution, Sizing & Cash Accounting
- **1x Portfolio Sizing**: Maximum notional exposure $\le 1.0\times$ portfolio equity.
- **5% Cash Reserve**: Budget capped at $0.95 \times \text{cash}$. Per-unit sizing incorporates adverse entry, exit fee buffers, spread, slippage, and funding reserve.
- **Discretization**: $0.001\text{ BTC}$ lot size. $5.0\text{ USDT}$ minimum notional. $0.1\text{ USDT}$ tick rounding.
- **Execution Order Priority**:
  1. STOP_GAP (opening adverse gap through stop).
  2. TIME_CAP (horizon expiration capped at target).
  3. TARGET_GAP_CAPPED (opening favorable gap through target).
  4. Same-minute STOP before TARGET collision.
- **Funding Attribution**: Settled signed funding cash flows attributed using latest completed 1m Mark close approximation: $\Delta \text{Cash} = -\text{side} \times \text{quantity} \times P_{mark} \times \text{rate}$.
- **Cost Regimes**:
  - STRESS (Primary): $44\text{ bps}$ nominal roundtrip (`fee_bps=12.0, spread_bps=8.0, slip_bps=6.0`).
  - BASE (Secondary): $22\text{ bps}$ nominal roundtrip (`fee_bps=6.0, spread_bps=4.0, slip_bps=3.0`).
- **Portfolio Constraints**:
  - Single active position.
  - 4h cooldown after exit ACK before next entry.
  - 24h prospective fold embargo to prevent fold boundary leakage.

## 6. Primary Decision Criteria & Falsification Rules
A candidate can earn `EXPLORATORY_ELIGIBLE_FOR_NEW_INDEPENDENT_DESIGN` ONLY if:
1. **Sample Viability**: $\ge 30$ executed trades per candidate identity across the 35 development months.
2. **Cost-Adjusted Profitability**: After-cost Profit Factor $> 1.0$ under STRESS (44 bps).
3. **2023 Stability**: Positive after-cost net PnL in 2023.
4. **Simultaneous Statistical Support**: 95% simultaneous max-|T| interval across all 6 comparisons (14d calendar block bootstrap) must have lower bound strictly $> 0$. A CI spanning zero constitutes `INSUFFICIENT_COST_ADJUSTED_SUPPORT` even if historical sample mean is positive.
