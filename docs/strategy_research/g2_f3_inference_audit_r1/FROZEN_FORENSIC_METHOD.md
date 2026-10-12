# Gemini Goal S — F3 Mark/Last Sparse-Alpha Source and Statistical-Validity Forensic R1: Frozen Execution Method

- **Task ID**: `V06_G2_GEMINI_F3_SPARSE_INFERENCE_AUDIT_R1`
- **Controller Authority**: `https://github.com/EXASHXE/btc-quant-agent-public/blob/4a487fcef182edc6c68486ff53d4a64caa10debc/reviews/v0.6/b_line/V06_G1_G2_GEMINI_ONLY_NEXT_GATE_R1_CONTROLLER_AUTHORITY.md`
- **Controller Dispatch SHA**: `4a487fcef182edc6c68486ff53d4a64caa10debc`
- **Authorized Base SHA**: `f25954b45577cebb7624fae86cd91df9071a87ab`
- **Branch**: `feature/v06-bline-gemini-f3-sparse-inference-audit-r1`
- **Isolated Worktree**: `/root/workspace/project/quant-v0.6/gemini-f3-inference-audit-r1`
- **Own Write Namespace**: `g2_f3_inference_audit_r1`
- **Protocol Stage**: `STAGE_1_PRE_OUTCOME_FORENSIC_METHOD_FREEZE`

---

## 1. Scientific Auditor Mandate & Scope

This study is conducted by an **independent scientific auditor**, strictly separated from the author of the original Gemini entry-strategy exploratory evaluation (`g2_flow_funding_entries_r1`).

### Core Principles
1. **No Optimization or Search**: Under no circumstances will candidate parameters, lookbacks, thresholds, or execution rules be tuned, modified, or searched to produce higher returns.
2. **Valid Negative Outcome Fulfillment**: A rigorously proven negative, invalidating, or inconclusive verdict completely fulfills the scientific mission of Goal S.
3. **Immutability of Historical Research**: Original implementation files under `scripts/strategy_research/g2_flow_funding_entries_r1/` and delivered empirical ledgers under `evidence/v0.6/b_line/g2_flow_funding_entries_r1/` remain completely untouched and read-only.
4. **Hermetic Sandbox Boundary**: The auditor may inspect only already-admitted public BTC 2021–2023 data hashes and the 12 previously committed trade rows. Under statutory protocol, the auditor will never list, stat, inspect, or touch protected 2024–2026 data, H39/H40/H41, Forward, private accounts, A-line, `/root/workspace/project/Quant-agent/data`, or `Quant-agent-sanitized`.

---

## 2. Mathematical Failure Mechanism of Frozen Simultaneous Max-|T| Studentization

In the frozen implementation of `scripts/strategy_research/g2_flow_funding_entries_r1/statistics.py` (lines 128–142), simultaneous confidence intervals across all candidate series were formed via calendar block bootstrapping with studentized test statistics:

$$t^* = \frac{|\bar{X}^* - \bar{X}|}{s^* / \sqrt{B}}$$

where $B$ is the number of calendar blocks ($B=76$ for 14-day blocks, $B=152$ for 7-day blocks), $\bar{X}^*$ is the bootstrap resample mean, and $s^*$ is the sample standard deviation of the resample.

### 2.1 The Degenerate Denominator Mechanism
To prevent division by zero when a bootstrap draw has identical values, line 136 enforces:
```python
b_se = np.std(boot_sample, ddof=1) / math.sqrt(n_blocks) if len(boot_sample) > 1 else 1e-6
b_se = max(b_se, 1e-6)
```

For candidate **F1** (`F1_AGGRESSOR_FLOW_ABSORPTION`), only $n=2$ trades occurred across the entire 35-month development timeline. Consequently, in the block partition:
- For 14-day blocks ($B=76$): exactly 2 blocks contain non-zero returns, and 74 blocks contain identically 0.0.
- For 7-day blocks ($B=152$): exactly 2 blocks contain non-zero returns, and 150 blocks contain identically 0.0.

When drawing $B$ blocks with replacement from an urn containing $k=2$ non-zero blocks and $B-k$ zero blocks, the probability that a bootstrap draw contains **only zero blocks** is:

$$P(\text{all zero}) = \left(\frac{B - 2}{B}\right)^B = \left(1 - \frac{2}{B}\right)^B$$

In the asymptotic limit as $B \to \infty$, this probability approaches:

$$\lim_{B \to \infty} \left(1 - \frac{2}{B}\right)^B = e^{-2} \approx 0.135335 \quad (13.53\%)$$

For finite samples:
- $B=76$: $P(\text{all zero}) = (74/76)^{76} \approx 0.13174$ (13.17%)
- $B=152$: $P(\text{all zero}) = (150/152)^{152} \approx 0.13354$ (13.35%)

In approximately **13.2% to 13.4% of all bootstrap rounds**:
1. Every resampled block in the draw has return $0.0$.
2. The resample mean is $\bar{X}^* = 0.0$.
3. The resample standard deviation is $s^* = 0.0$.
4. The standard error hits the floor: $b\_se = \max(0.0, 10^{-6}) = 10^{-6}$.
5. The studentized test statistic evaluates to:
   $$t^* = \frac{|0.0 - \bar{X}|}{10^{-6}} = |\bar{X}| \times 10^6$$

For F1, the cumulative 35-month return across its 2 executed trades was $-182.606385$ bps:
- For 14-day blocks ($B=76$): $\bar{X} = -182.606385 / 76 = -2.40271559$ bps.
  $$t^* = 2.40271559 \times 10^6 = 2,402,715.594$$
- For 7-day blocks ($B=152$): $\bar{X} = -182.606385 / 152 = -1.20135780$ bps.
  $$t^* = 1.20135780 \times 10^6 = 1,201,357.797$$

### 2.2 Family Contamination of Simultaneous Critical Values
Because $P(\text{all zero}) \approx 13.3\% > 5.0\%$, degenerate test statistics occur in over 13% of all bootstrap rounds. When computing the 95th percentile ($q_{0.95}$) of the maximum statistic across candidates:

$$\max_{k} t_k^* \ge t_{\text{F1}}^*$$

the top 5% of draws is **entirely saturated** by these degenerate events. Thus, the simultaneous critical value is mathematically forced to:
- $q_{0.95} = 2,402,715.59$ (14-day)
- $q_{0.95} = 1,201,357.80$ (7-day)

When simultaneous confidence intervals are formed:

$$CI_{0.95}(i) = \left[ \bar{X}_i - q_{0.95} \cdot SE_i, \; \bar{X}_i + q_{0.95} \cdot SE_i \right]$$

the critical value $q_{0.95} \sim 10^6$ multiplies the standard error of **every other candidate** (including F3, where $SE \approx 10.76$ bps for 14d and $SE \approx 5.81$ bps for 7d), yielding absurd interval half-widths of:
- F3 12H 14d: $\pm 25,854,412.2$ bps ($\pm 2,585\%$)
- F3 12H 7d: $\pm 6,984,766.4$ bps ($\pm 698\%$)

### 2.3 Scientific Implication
The fact that "simultaneous CI spans zero" was **not** empirical evidence against F3; it was a pure numerical singularity caused by an arbitrary floating-point floor ($10^{-6}$) under sparse all-zero bootstrap draws from F1.

However, as pre-declared, **this numerical defect does NOT validate F3**. F3 remains completely unvalidated and ineligible for promotion because:
1. It generated only $n=12$ executed trades across 35 months, failing the pre-registered sample viability threshold ($n \ge 30$).
2. The trades are concentrated in 2021 ($n=9$), with only $n=2$ in 2022 and $n=1$ in 2023.
3. A single trade (Trade 7 on 2021-05-19) accounts for 89.5% of total net profits.

---

## 3. Pre-Registered Forensic Diagnostics

The auditor pre-registers the following non-selectable diagnostic evaluations:

### 3.1 Block & Calendar Support Diagnostics
- $N_{\text{trades}}$: Total executed trades. Must satisfy $n \ge 30$ for sample viability.
- $N_{\text{blocks}}$: Number of calendar blocks (7-day and 14-day).
- $N_{\text{active}}$: Number of blocks containing $\ge 1$ executed trade.
- $N_{\text{weeks}}$: Number of independent calendar weeks with trade activity.
- $ZeroFraction$: Proportion of calendar blocks with zero trades.

### 3.2 12h vs 18h Horizon Overlap Audit
- Identify trades with identical entry timestamp, direction, and entry price between 12h and 18h configurations.
- Categorize exit fates: trades that exit prior to 12h via TARGET or STOP are mechanically **100% identical** across both horizons, providing zero independent information.

### 3.3 Leave-One-Event-Out (LOEO) Jackknife Influence
- For each trade $i \in \{1 \dots n\}$, evaluate the impact of omitting trade $i$:
  $$\Delta \bar{X}_i = \bar{X}_{\text{total}} - \bar{X}_{-i}$$
  $$\text{ProfitShare}_i = \frac{\text{NetUSDT}_i}{\sum \text{NetUSDT}}$$
- Pre-register flag `IS_HIGHLY_CONCENTRATED` if $\text{ProfitShare}_{\text{top1}} \ge 50\%$.

### 3.4 Gross-to-Fee Economics & Drag Attribution
- Reconcile exact accounting: Gross USDT, entry/exit fees, adverse spread/slippage drag, and funding cashflow.
- Compute Gross / Fee ratio and net-to-gross capture.

### 3.5 Profit Factor Sentinel Classification
- When negative trading losses are $0.0$, the standard formula $\text{pos} / \text{neg}$ produces division by zero, for which the code substitutes `999.0`.
- Pre-register that `PF = 999.0` in 2023 is classified as `ZERO_LOSS_PLACEHOLDER_NOT_FINITE_STATISTICAL_EVIDENCE`, not proof of infinite risk-adjusted edge.

### 3.6 Data Causality & Known-At Uncertainty Classification
- Categorize the three price/clock sources:
  1. **Last 1m close**: Tradeable fill proxy from public completed 1m transaction kline.
  2. **Mark 1m close**: Valuation proxy used for margin/liquidation; non-executable index composite.
  3. **Mark historical broadcast timestamp**: UNKNOWN in public historical archives.
- Feature construction audit: verify that no post-event price extrema or future bars are used.

---

## 4. Pre-Declared Statistical Alternatives

### 4.1 Nonparametric Sparse-Support Refusal
- Rule: If $n < 30$ or $N_{\text{active\_blocks}} < 10$, declare `SPARSE_SUPPORT_REFUSAL`.
- Refuse to publish asymptotic parametric or studentized confidence intervals on sparse data where empirical distribution functions cannot guarantee nominal coverage.

### 4.2 Exact Binomial Sign Test
- Null hypothesis: $H_0: p = 0.5$ (directional entry has zero predictive edge).
- Compute exact two-sided binomial $p$-value for $k$ wins out of $n=12$.
- Compute Clopper-Pearson exact confidence bounds for win probability.

### 4.3 Adverse-Event Sensitivity Analysis
- Test whether net cumulative profits survive if the top 1 or top 2 winning trades are perturbed into standard adverse losses (-44 bps).

### 4.4 Exploratory Fixed-SE Centered Block Bootstrap
- Replace the unstable resample denominator $s^* / \sqrt{B}$ with the constant sample standard error $SE_{\text{sample}} = s / \sqrt{B}$:
  $$t^* = \frac{|\bar{X}^* - \bar{X}|}{SE_{\text{sample}}}$$
- This eliminates the zero-denominator singularity while maintaining multi-block resampling.
- **Strict Pre-Declaration**: This alternative interval is exploratory and descriptive only. It CANNOT grant promotion or statistical PASS to F3 because sample viability ($n \ge 30$) remains failed.

---

## 5. Prospective Scientific Design for Future F3 Studies

For any future research trial attempting to evaluate fair-value dislocation or basis-repair mechanisms:
1. **Contemporaneous Millisecond Timestamping**: Must capture live exchange WebSocket book ticker dissemination timestamps alongside Mark index updates, proving point-in-time tradability.
2. **Order Book Trade-Through Proof**: Must demonstrate that the dislocation exceeded bid/ask spread and that fill was executable without market-impact slippage.
3. **Minimum Temporal Support**: Pre-register minimum sample viability: $n \ge 30$ executed trades distributed across $\ge 15$ distinct calendar weeks and $\ge 2$ independent market regimes.
4. **Independent Execution Costs**: Apply dynamic queue and slippage models reflecting liquidity at dislocation peaks.
5. **Statutory Protected Holdout Approval**: Zero access to protected 2024–2026 data without explicit custodian and Controller authorization.

---

## 6. Freeze Protocol & Terminal Verdict Criteria

- Commit 1 freezes this method document, the forensic audit scripts, and all unit tests.
- Commit 1 is pushed to `origin feature/v06-bline-gemini-f3-sparse-inference-audit-r1` and verified.
- Stage 2 runs the audit runner to generate machine evidence and the final empirical audit report.
- The terminal verdict will be declared from:
  - `F3_SPARSE_MECHANISM_SOURCE_AND_STATS_DIAGNOSED`
  - `F3_SOURCE_OR_CAUSALITY_INVALID`
  - `F3_AUDIT_INCONCLUSIVE`
