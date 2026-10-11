# Prospective Experimental Protocol: Future D1 and D2 Exit Designs

**Task ID:** `V06_G2_POST_EXIT_R1_GOAL_B_H18_MECHANISM_R1`  
**Scientific Grade:** Formal Protocol Specification — **DESIGN ONLY, NON-EXECUTED**.  
**Prerequisite:** Explicit Controller (ChatGPT-0) authorization required prior to any historical or forward evaluation. Exactly zero new exit configurations were evaluated or optimized in Goal B.

---

## 1. Context & Motivation from Empirical Goal B Findings

The empirical findings from Goal B demonstrate that:
1. **Continuation is a coin-flip:** Among the 56 baseline TIME_CAP trades that reached 12 hours open, 46.4% suffered adverse reversals between 12h and 18h.
2. **Right-tail dominance:** The sample-mean advantage of 18h (H1) is almost entirely concentrated in a tiny fraction of trades (7 out of 89 total trades, or 7.8%) that hit the profit target between 12h and 18h (>86% of total net gains).
3. **Momentum exhaustion at 24h:** Extending to 24h (H2) results in increased stopouts (+6 additional stops) and adverse drift, causing H2 to underperform H1 by -7.61 bp in W1 and -12.87 bp in W2.
4. **2023 structural breakdown:** In W2, 2023 remains net negative under STRESS (-18.11 bp) even with 18h holding.

These findings suggest that passive, unconditioned holding horizon extension (whether 18h or 24h) is economically ungrounded and statistically fragile. Any future exploration of extended exit horizons must be framed as a prospective hypothesis testing conditional momentum persistence, rather than passive time inflation.

---

## 2. Prospective Candidate D1: Conditional 12→24h Momentum Gate

### 2.1 Formal Hypothesis
*If and only if* an open position has established a clear trend surplus and favorable order flow as of $t = 12\text{h}$, the probability of positive continuation through 24h exceeds the baseline reversal rate; otherwise, capital should be immediately liberated at 12h.

### 2.2 Mathematical Decision Rule
At decision timestamp $t_{\text{dec}} = t_{\text{entry}} + 12 \times 3600 \times 1000$ (evaluated strictly on completed bars as-of 12h):

1. **Unrealized Surplus Gate:**
   $$\text{Unrealized } R(t_{\text{dec}}) = \frac{\text{side} \times (P_{\text{mark}}(t_{\text{dec}}) - P_{\text{entry}})}{|P_{\text{entry}} - P_{\text{stop}}|}$$
   Criterion: $\text{Unrealized } R(t_{\text{dec}}) \ge +0.50 R$.
2. **Flow Confirmation Gate:**
   $$\text{Signed Flow Ratio}_{1h}(t_{\text{dec}}) = \frac{2 \times \text{TakerBuyVol}_{1h} - \text{TotalVol}_{1h}}{\text{TotalVol}_{1h}}$$
   Criterion: $\text{side} \times \text{Signed Flow Ratio}_{1h}(t_{\text{dec}}) > +0.10$.
3. **Trend Preservation Gate:**
   $$P_{\text{close, 1m}}(t_{\text{dec}}) \text{ strictly above (below for Short) EMA20}_{1h}(t_{\text{dec}})$$

### 2.3 Action Execution
- **If all criteria satisfied:** Extend hard time cap from 12h to 24h ($t_{\text{exit, max}} = t_{\text{entry}} + 24\text{h}$). Stop and target remain active.
- **If any criterion breached:** Trigger immediate taker close at $t_{\text{dec}} + 1\text{m}$ ACK under full frozen STRESS44 friction.

### 2.4 Sample Power and Feasibility
- Historical eligible cohort across 2021–2023: 56 baseline TIME_CAP trades (~1.6 trades/month).
- Splitting this sample into conditional branches leaves approximately 15–20 events per branch.
- **Feasibility Assessment:** Statistically underpowered for single-parameter rejection. Requires pre-specifying a joint test across both candidates with a high hurdle (+25 bp net advantage).

### 2.5 Falsification Conditions
1. D1 fails if its net bps does not exceed E0 (12h) by at least +25 bp under STRESS44.
2. D1 fails if its net bps does not exceed H1 (18h) after applying a multiple-testing penalty.
3. D1 fails if 2023 W2 net bps remains negative.

---

## 3. Prospective Candidate D2: Dynamic ATR Trailing Tracking Post-12h

### 3.1 Formal Hypothesis
*If* an open position has survived to 12h without hitting stop or target, ratcheting an ATR-based trailing stop from 12h onward will protect accumulated paper gains against the severe adverse reversals and stopouts observed between 18h and 24h.

### 3.2 Mathematical Specification
1. **Activation:** Strictly at $t = t_{\text{entry}} + 12\text{h}$, applied only to still-open positions.
2. **Reference Volatility:** Completed 1h $\text{ATR}(14)$ as-of $t = 12\text{h}$, denoted $\text{ATR}_{12h}$.
3. **Trailing Distance:**
   $$\Delta_{\text{trail}} = 1.5 \times \text{ATR}_{12h}$$
4. **Ratchet Rule:** Evaluated on every completed 1-minute bar $t \in [12\text{h}, 24\text{h}]$:
   - For LONG: $\text{Stop}_t = \max(\text{Stop}_{t-1}, P_{\text{high}, t} - \Delta_{\text{trail}})$
   - For SHORT: $\text{Stop}_t = \min(\text{Stop}_{t-1}, P_{\text{low}, t} + \Delta_{\text{trail}})$
   - Ratchet moves strictly in the favorable direction (monotonically non-decreasing for Long, non-increasing for Short).
5. **Maximum Horizon:** Position terminates at $t_{\text{entry}} + 24\text{h}$ if trailing stop or target is not hit earlier.

### 3.3 Execution Budget & Latency
- Simulated stop trigger evaluated at 1-minute resolution on Last price.
- Executed at next-bar open with full STRESS44 taker fee (12 bp), half-spread (4 bp), and adverse slippage (6 bp), plus 1-bar ACK delay.

### 3.4 Sample Power and Falsification Conditions
- **Power:** Low ($N=56$).
- **Falsification Conditions:**
  1. D2 fails if whipsaw ratchets cause premature stopouts, resulting in total net bps lower than E0.
  2. D2 fails if maximum drawdown on minute Mark curves is not reduced by at least 15% relative to H2.
  3. D2 fails if net cash return per occupied day is lower than H1.

---

## 4. Governance and Controller Gate Requirements

Neither D1 nor D2 may be executed, backtested, or calibrated on historical data without:
1. Formal review and written authorization from ChatGPT-0 B-line Controller;
2. Pre-registration of exact parameter values (no grid searches over trailing multipliers or surplus thresholds);
3. Evaluation strictly on isolated worktrees with immutable commit hashing.
