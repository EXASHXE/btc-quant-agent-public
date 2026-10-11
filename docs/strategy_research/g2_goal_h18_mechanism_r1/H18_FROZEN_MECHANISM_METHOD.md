# Gemini Goal B — Frozen Mechanism Diagnostic Method

**Task ID:** `V06_G2_POST_EXIT_R1_GOAL_B_H18_MECHANISM_R1`  
**Controller Authority:** ChatGPT-0 B-line Controller (`c02743fddccdf517582c371a47e82d8dcbb05923`)  
**Exact Start SHA:** `55ac4c631c69f6edbd275462ad23e4486b9782ed`  
**Exit R1 Frozen SHA:** `de2c1fb222970a93ca797868b91b8544261ebaad`  
**Branch:** `feature/v06-bline-gemini-goal-h18-mechanism-r1`  
**Worktree:** `/root/workspace/project/quant-v0.6/gemini-h18-mechanism-r1`  
**Scratch:** `/tmp/btc-gemini-h18-goal-r1`  
**Prefix:** `g2_goal_h18_mechanism_r1`  
**Scientific Grade:** Observational mechanistic diagnostic development only. **Zero new configurable exit policies authorized.**

---

## 1. Scientific Background and Mandate

In Exit/Horizon R1, under the frozen STRESS44 cost proxy with signed funding and mark settlements, the point estimates for trade-level mean net bps were:
- **W1 (ATR Expansion Trend Follow, n=34):**
  - E0 (12h): +11.2047 bps
  - H1 (18h): +48.5499 bps (+37.3452 bps vs E0)
  - H2 (24h): +44.0744 bps (+32.8697 bps vs E0, -4.4755 bps vs H1)
- **W2 (Asymmetric Volatility Breakout, n=55):**
  - E0 (12h): +19.0135 bps
  - H1 (18h): +41.4477 bps (+22.4342 bps vs E0)
  - H2 (24h): +33.0215 bps (+14.0080 bps vs E0, -8.4262 bps vs H1)

Crucially, the 95% simultaneous 7d and 14d max-|T| eight-contrast intervals all encompass zero (W1 14d: `[-25.93, +100.62]` bps, W2 14d: `[-18.35, +63.22]` bps). H1 was selected after observing historical development data across 48+8 earlier trials; it cannot be treated as a proven optimal holding period.

**Mandate:** Deliver an auditable, economically interpretable causal diagnostic explaining:
1. Why H1 may appear to improve over E0 in sample means;
2. Why H2 systematically underperforms H1 despite longer duration;
3. How these effects distribute across market regimes and sides;
4. Whether net advantages survive whole-account capital and opportunity cost constraints.

---

## 2. Three Predeclared Matched Analyses

### Analysis 1: Time-Cap Censored vs. Early-Exit Baseline Strata
- Segregate the 89 total baseline E0 events into:
  - **Baseline TIME_CAP events:** 56 total (W1: 20/34 = 58.8%, W2: 36/55 = 65.5%).
  - **Baseline Early Exit events:** 33 total (W1: 14/34, W2: 19/55).
- Early exit events exited before 12h via STOP or TARGET; their H1 and H2 paths are mathematically identical to E0 (zero incremental delta).
- For the 56 TIME_CAP events, trace the trajectory through [12h, 18h] and [18h, 24h]:
  - Incremental signed price PnL vs funding cash vs exit fee changes.
  - Continuation vs. reversal fractions (favorable `delta_net > 0` vs adverse `delta_net < 0`).
  - Terminal fates in H1 and H2: TIME_CAP, TARGET, STOP.
  - Outlier and right-tail concentration: top 1, top 3 share of total net bps.

### Analysis 2: Whole-Account Opportunity Cost and Capital Occupancy
- Independent signal-stream replays under realistic account constraints:
  - 1x notional cap, 5% cash reserve, single-position sidecar, 4h post-exit cooldown.
- Examine skipped signals:
  - Verify whether extending horizon from 12h to 18h or 24h caused any new signal to be declined that was filled under E0.
  - Distinguish matched same-event vs different account event set estimands.
- Capital occupancy metrics:
  - Total occupied minutes for E0, H1, H2.
  - Return per occupied day (capital efficiency).
  - Maximum MTM drawdown and margin safety on minute Mark curves.
  - Bounded hypothetical sensitivity for unobservable skipped signals.

### Analysis 3: Price, Funding, and Execution Decomposition
- Mathematical decomposition per trade:
  $$\text{Net PnL (USDT)} = \text{Effective Price PnL} + \text{Funding Cash} - \text{Fee}_{\text{entry}} - \text{Fee}_{\text{exit}}$$
- Incremental contrast decomposition:
  $$\Delta \text{Net USDT} = \Delta \text{Effective Price PnL} + \Delta \text{Funding Cash} - \Delta \text{Fee}_{\text{exit}}$$
- Fixed execution sensitivities:
  - One-bar later exit ACK (1m delay).
  - Worse slippage stress (+2, +5, +10 bps drag).

---

## 3. Predeclared As-Of State Labels

All state labels are strictly causal and known as-of entry:
1. **Calendar Year:** 2021, 2022, 2023.
2. **Trade Side:** LONG (+1), SHORT (-1).
3. **Trend Alignment:** Completed 4h return strictly preceding entry relative to side:
   - $\text{TREND\_ALIGNED}$ if $\text{side} \times \text{ret}_{4h} > 0$.
   - $\text{COUNTERTREND}$ if $\text{side} \times \text{ret}_{4h} < 0$.
   - $\text{NEUTRAL}$ if $\text{side} \times \text{ret}_{4h} = 0$.
4. **Volatility Regime:** Expanding previous-only 90d distribution of completed 1h ATR(14)/price:
   - $\text{INCOMPLETE\_LOOKBACK}$ if history < 90 days.
   - $\text{HIGH\_VOL}$ if current ATR/price $\ge$ 90d median.
   - $\text{LOW\_VOL}$ if current ATR/price $<$ 90d median.
5. **Funding State:** Strictly observed prior funding settlement rate before signal time:
   - $\text{POSITIVE}$ if rate $> 0$.
   - $\text{NEGATIVE}$ if rate $< 0$.
   - $\text{ZERO}$ if rate $= 0$.
   - $\text{UNKNOWN}$ if no prior settlement.

**Power Gate:** If any stratum contains $N < 10$ events, it is flagged as `UNDERPOWERED`. No causal alpha or strategy targeting claim may be based on underpowered bins.

---

## 4. Falsification Gates

- **Gate 1 (Continuation Coin-Flip):** If $\ge 45\%$ of 12-18h continuation outcomes are adverse reversals, the H1-E0 advantage is falsified as an asymmetric right-tail outlier effect rather than robust alpha.
- **Gate 2 (H24 Momentum Exhaustion):** If 18-24h yields negative incremental mean return and increased stopouts, H2 underperformance is falsified as structural momentum decay.
- **Gate 3 (2023 Regime Instability):** If W2 remains net negative in 2023 under STRESS, 18h holding does not rescue structural failure.
- **Gate 4 (Sample Scarcity):** If regime strata have $N < 10$, regime targeting is rejected as infeasible.
- **Gate 5 (Opportunity Collision):** If no signals arrived in the (12h, 24h) window due to signal burstiness, trade sets are identical, but capital efficiency declines.

---

## 5. Prospective D1/D2 Protocol Boundary

Any future conditional exit logic (e.g., D1 12->24h momentum gate, D2 ATR trailing stop) is documented **DESIGN ONLY**. No backtest or parameter search is conducted in Goal B. Evaluation requires explicit future Controller authorization.
