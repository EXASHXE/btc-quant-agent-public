# Gemini Goal S — F3 Mark/Last Sparse-Alpha Source and Statistical-Validity Forensic R1: Audit Report

- **Terminal Scientific Verdict**: `F3_SPARSE_MECHANISM_SOURCE_AND_STATS_DIAGNOSED`
- **Task ID**: `V06_G2_GEMINI_F3_SPARSE_INFERENCE_AUDIT_R1`
- **Controller Authority**: [Controller Authority Document](https://github.com/EXASHXE/btc-quant-agent-public/blob/4a487fcef182edc6c68486ff53d4a64caa10debc/reviews/v0.6/b_line/V06_G1_G2_GEMINI_ONLY_NEXT_GATE_R1_CONTROLLER_AUTHORITY.md)
- **Controller Dispatch SHA**: `4a487fcef182edc6c68486ff53d4a64caa10debc`
- **Authorized Base SHA**: `f25954b45577cebb7624fae86cd91df9071a87ab`
- **First Freeze Commit SHA**: `6d20579486cc62daf5420e61ced2f8dc4732a414`
- **Branch**: `feature/v06-bline-gemini-f3-sparse-inference-audit-r1`
- **Isolated Worktree**: `/root/workspace/project/quant-v0.6/gemini-f3-inference-audit-r1`
- **Own Write Namespace**: `g2_f3_inference_audit_r1`
- **Protocol Stage**: `STAGE_2_EVIDENCE_DELIVERY_AND_FINAL_DISPOSITION`

---

## 1. Executive Summary & Terminal Verdict

An independent scientific audit of candidate family **F3** (`F3_MARK_LAST_DISLOCATION_REPAIR`) and the underlying statistical calibration harness frozen in `scripts/strategy_research/g2_flow_funding_entries_r1/` was executed under strict protocol bounds.

### Key Conclusions
1. **Exact Numerical Failure Mechanism Diagnosed**:
   The multi-million critical values ($q_{0.95} \approx 1,201,357.8$ for 7-day blocks and $2,402,715.6$ for 14-day blocks) reported in the prior study are **pure numerical artifacts** of degenerate studentization under sparse all-zero bootstrap resamples. In approximately 13.2% to 13.4% of bootstrap draws for sparse candidate F1 ($n=2$), all sampled calendar blocks contain zero trades, causing the resample standard deviation to vanish and the standard error denominator to clamp to the arbitrary floor $b\_se = 10^{-6}$. The resulting ratio $|0 - \bar{X}| / 10^{-6} = |\bar{X}| \times 10^6$ saturates the top 5% of the simultaneous distribution and contaminates all candidates across the family.
2. **"CI Spans Zero" Was Not Calibrated Edge Evidence**:
   Reporting that simultaneous confidence intervals span zero (with half-widths of $\pm 25.8$ million bps) was physically uninformative and did not represent calibrated evidence against directional edge.
3. **F3 Lacks Statistical Viability and Support to Establish Alpha**:
   Despite surviving cost with positive sample profit (+108.11 USDT at 12h, +109.70 USDT at 18h under STRESS 44bp), F3 is **unvalidated and ineligible for promotion**:
   - **Sample Sparsity**: Generates only $n=12$ executed trades across 35 development months (1,064 days), failing the pre-declared viability gate ($n \ge 30$).
   - **Severe Temporal Concentration**: 9 trades occurred in 2021, 2 in 2022, and exactly **1 trade in 2023** (a single win of +10.27 USDT).
   - **Extreme Single-Event Fragility**: A single trade (Trade 7 on 2021-05-19, +96.76 USDT / +1044.2 bps) accounts for **89.5% of total 35-month net profit**. Omitting this single event collapses net profit to +11.35 USDT and Profit Factor to 1.12.
   - **Zero Win-Rate Edge**: The two-sided exact binomial sign test on $k=6$ wins out of $n=12$ yields $p = 1.000$, indistinguishable from random coin tossing.
   - **Adverse Sensitivity Failure**: Shifting just 2 winning trades into standard -44bp adverse execution losses turns the entire 3-year performance negative (-38.00 USDT, PF 0.63).
4. **Data Causality & Valuation vs Execution Dichotomy**:
   F3 features are constructed by comparing 1h average Last traded price with 1h average Mark price. While Last 1m close is a valid fill proxy, Mark 1m close is a synthetic valuation composite used for margin/liquidation, **not an executable order book**. Furthermore, the exact intra-minute exchange broadcast timestamp for historical Mark klines is UNKNOWN in public archives.

**Terminal Scientific Decision**: `F3_SPARSE_MECHANISM_SOURCE_AND_STATS_DIAGNOSED`  
No trading promotion, parameter tuning, or holdout evaluation is authorized.

---

## 2. Stage 0 Source Provenance & Three-Commit Lineage Reconciliation

### 2.1 Commit Lineage Audit
The repository history leading to this audit was verified:
1. `c0296ad38739281b69bcc3294b7706c1009d426a`: Initial pre-outcome freeze of candidates, book execution, and test suite. Parent: `55ac4c631c69f6edbd275462ad23e4486b9782ed`.
2. `846de3881ef1604fe66d120a15fc4b1821cfdfbe`: Delivery of empirical backtest results, analysis tables, and trade ledgers.
3. `f25954b45577cebb7624fae86cd91df9071a87ab`: Delivery manifest hash update and report refinement.
4. `6d20579486cc62daf5420e61ced2f8dc4732a414`: First freeze commit of this audit branch (`feature/v06-bline-gemini-f3-sparse-inference-audit-r1`), pre-registering the independent forensic method, diagnostics, and 56 synthetic unit tests before any outcome calculations.

All 14 code implementation hashes from `FROZEN_CONTRACT.json` and all 31 artifact hashes from `FLOW_FUNDING_DELIVERY_MANIFEST.json` matched their exact byte digests with zero modifications.

### 2.2 Independent Ledger Reconciliation
Every trade ledger in `evidence/v0.6/b_line/g2_flow_funding_entries_r1/` was independently parsed and verified:

| Ledger File | Trades ($n$) | Gross USDT | Fees USDT | Execution Drag | Funding USDT | Ending Cash | Net PnL USDT | Profit Factor | Max DD (%) |
|---|---|---|---|---|---|---|---|---|---|
| `F3_12H_STRESS_orders.jsonl` | 12 | +147.19 | 26.14 | 21.81 | +8.87 | 1108.11 | +108.11 | 2.15 | 4.06% |
| `F3_18H_STRESS_orders.jsonl` | 12 | +146.66 | 25.95 | 21.65 | +10.64 | 1109.70 | +109.70 | 1.77 | 7.25% |
| `F3_12H_BASE_orders.jsonl` | 12 | +141.41 | 13.16 | 11.00 | +8.90 | 1126.14 | +126.14 | 2.49 | 3.79% |
| `F3_18H_BASE_orders.jsonl` | 12 | +141.28 | 12.98 | 10.84 | +10.64 | 1128.10 | +128.10 | 1.97 | 6.86% |

- **Cash Balance Continuity**: For 100% of trades, $\text{cash\_before} + \sum \text{journal\_deltas} \equiv \text{cash\_after}$.
- **Net-to-Cash Invariant**: Ending cash minus starting cash ($1000.0$ USDT) matched cumulative net PnL within sub-cent floating tolerance ($< 10^{-6}$ USDT).
- **Paired Control Caveat**: Paired reference files (`*paired.jsonl`) correctly carried the immutable disclaimer `"caveat": "NONTRADABLE_SAME_EVENT_PAIRED_REFERENCE_NOT_POOLED_CASH"`.

---

## 3. Mathematical Proof: Degenerate Studentization Failure

### 3.1 Formal Derivation
Let a candidate series have $k$ non-zero calendar blocks out of $B$ total blocks. When drawing $B$ blocks with replacement:

$$P(\text{all-zero draw}) = \left(\frac{B - k}{B}\right)^B$$

For candidate F1 ($k=2$):
- 14-day blocks ($B=76$): $P = (74/76)^{76} = 0.13174$ (13.17%)
- 7-day blocks ($B=152$): $P = (150/152)^{152} = 0.13354$ (13.35%)

In every all-zero draw:
1. Resample mean: $\bar{X}^* = 0.0$.
2. Resample standard deviation: $s^* = 0.0$.
3. Clamped standard error: $b\_se = \max(s^* / \sqrt{B}, 10^{-6}) = 10^{-6}$.
4. Test statistic: $t^* = |0.0 - \bar{X}| / 10^{-6} = |\bar{X}| \times 10^6$.

### 3.2 Exact Numerical Replication
Cumulative F1 return across 35 months is $-182.6063851570522$ bps:
- **7-day ($B=152$)**: $\bar{X} = -1.2013577970858698$ bps.
  $$t^* = 1.2013577970858698 \times 10^6 = 1,201,357.7970858698$$
  Original code reported $q_{0.95} = 1,201,357.80$ (exact match).
- **14-day ($B=76$)**: $\bar{X} = -2.4027155941717395$ bps.
  $$t^* = 2.4027155941717395 \times 10^6 = 2,402,715.5941717396$$
  Original code reported $q_{0.95} = 2,402,715.59$ (exact match).

Because $P(\text{all zero}) \approx 13.3\% > 5\%$, the 95th percentile of the maximum over all 6 candidates was mathematically guaranteed to equal this exact degenerate value. F1's sparsity contaminated the simultaneous critical value for the entire family, expanding F3's confidence interval to $\pm 25.8$ million bps.

---

## 4. F3 Support Weakness & Severe Concentration Audit

### 4.1 Temporal Support & Sparsity
Across 35 development months (1,064 calendar days), F3 generated only **12 executed trades**:
- **2021**: 9 trades (4 wins, 5 losses, net +65.90 USDT)
- **2022**: 2 trades (1 win, 1 loss, net +31.93 USDT)
- **2023**: **1 trade** (1 win, 0 losses, net +10.27 USDT)
- **Active Calendar Blocks**: Only 8 out of 76 14-day blocks (89.5% zero blocks).
- **Active Calendar Weeks**: Only 9 distinct calendar weeks.

### 4.2 Signal Count vs Executed Trades Reconciliation
The signal generator emitted 16 raw signals, while exactly 12 trades were executed:
- The 4 non-executed signals occurred while a previous trade was still open or within the mandatory 4-hour post-exit cooldown window (`POSITION_ACK_OR_COOLDOWN`).
- Zero signals were rejected due to gap vetos or sizing limits.

### 4.3 Severe Concentration: Trade 7 Dominance
Leave-One-Event-Out (LOEO) jackknife analysis reveals extreme single-event dependence:

| Trade ID | Date (UTC) | Side | Exit Reason | Net Bps | Net USDT | Profit Share | Without Trade: Net USDT | Without Trade: PF |
|---|---|---|---|---|---|---|---|---|
| Trade 7 | 2021-05-19 | Short | TARGET (51 min) | +1044.22 | **+96.76** | **89.50%** | **+11.35** | **1.12** |
| Trade 10 | 2022-05-10 | Long | TIME_CAP (12h) | +440.14 | +40.54 | 37.50% | +67.56 | 1.83 |
| Trade 2 | 2021-02-06 | Short | TARGET (420 min) | +383.83 | +34.36 | 31.78% | +73.74 | 1.81 |
| Trade 5 | 2021-02-22 | Short | TIME_CAP (12h) | +122.64 | +11.07 | 10.24% | +97.04 | 2.04 |
| Trade 12 | 2023-04-10 | Long | TARGET (527 min) | +110.03 | +10.27 | 9.50% | +97.84 | 2.05 |
| Trade 4 | 2021-02-09 | Short | TIME_CAP (12h) | +100.77 | +9.00 | 8.33% | +99.10 | 2.06 |

**Key Finding**: Omitting Trade 7 reduces total net profit across 3 years from +108.11 USDT to **+11.35 USDT** (an 89.5% collapse), and reduces Profit Factor from 2.15 to **1.12** (nearly breaking even). The purported edge of F3 is essentially a single profitable trade during the May 2021 market crash.

### 4.4 Profit Factor Sentinel (PF = 999.0 in 2023)
In 2023, F3 executed exactly 1 trade, which was a win (+10.27 USDT). Because there were zero losing trades (`neg_usdt == 0`), the formula $\text{pos} / \text{neg}$ evaluated to `999.0`.  
As pre-declared in this audit, `PF = 999.0` is an arbitrary software placeholder for division by zero; it provides **zero finite statistical evidence** of edge in 2023.

---

## 5. Horizon Overlap & Data Causality Audit

### 5.1 12h vs 18h Horizon Overlap
- **Entry Overlap**: 12 out of 12 trades (100%) share identical entry timestamps, sides, and prices.
- **Exit Overlap**: 4 out of 12 trades (33.3%) hit TARGET or STOP before the 12-hour limit, producing **identically identical PnL and cash flows** in both horizons.
- The 18h candidate provides zero independent sample trials; it is a correlated variation of the same 12 historical events.

### 5.2 Microstructure Fill vs Mark Valuation Dichotomy
- **Last 1m Close**: Tradeable execution price proxy (order fills executed against Last traded price with adverse spread and slippage).
- **Mark 1m Close**: Valuation proxy calculated as an index moving average. Mark price is **not executable**; market participants cannot submit orders to trade against Mark.
- **Historical Broadcast Timestamp**: Unknown in public archives. Whether Binance Mark price was broadcast before or after minute-boundary Last ticks cannot be proven retrospectively.

---

## 6. Pre-Declared Statistical Alternatives

### 6.1 Nonparametric Sparse-Support Refusal
Under the pre-registered audit rule ($n < 30$), the auditor formally issues a **SPARSE_SUPPORT_REFUSAL**. No asymptotic confidence interval can be certified on 12 events across 35 months.

### 6.2 Exact Binomial Sign Test
Evaluating directional entry predictive ability against null hypothesis $H_0: p = 0.5$:
- **12H**: 6 wins / 6 losses (50.0% win rate). Two-sided exact binomial $p = 1.0000$.
- **18H**: 7 wins / 5 losses (58.3% win rate). Two-sided exact binomial $p = 0.7744$.
- Directional predictive win rate is statistically indistinguishable from a fair coin toss.

### 6.3 Adverse-Event Sensitivity Analysis
Testing sensitivity to execution drag or fill delays:
- If **1 winning trade** becomes an adverse loss (-44 bps): 12H net profit collapses from +108.11 to **+6.95 USDT** (PF 1.07).
- If **2 winning trades** become adverse losses (-44 bps): 12H net profit turns **negative** to **-38.00 USDT** (PF 0.63).

### 6.4 Exploratory Fixed-SE Centered Block Bootstrap
When replacing the vanishing resample denominator with the constant sample standard error $SE_{\text{sample}} = 10.76$ bps:
- Critical value: $q_{0.95} = 1.87$
- Simultaneous 95% CI: $[-4.93, +35.37]$ bps per block.
- Percentile 95% CI: $[-1.74, +39.75]$ bps per block.
- Both well-conditioned exploratory intervals span zero, confirming that even without the studentizer explosion, F3 fails cost-adjusted statistical significance.

---

## 7. Prospective Scientific Design for Future F3 Studies

For any future research trial seeking to test fair-value basis dislocation or repair mechanisms:
1. **Contemporaneous Millisecond Tick Data**: Must record live exchange WebSocket tick timestamps for both Last and Mark feeds, proving real-time availability before entry.
2. **Order Book Depth & Trade-Through Proof**: Must establish that basis dislocation exceeded the actual bid/ask spread and that available depth at top-of-book permitted execution without price impact.
3. **Pre-Declared Sample Viability**: Require at least $n \ge 30$ executed trades spanning $\ge 15$ distinct calendar weeks across $\ge 2$ independent calendar years before computing inferential statistics.
4. **Independent Non-Studentized Resampling**: Avoid variance-floor studentization on sparse point processes; utilize stationary block bootstrap with percentile bounds or exact permutation tests.
5. **Statutory Protected Holdout Custodian Authorization**: Zero exploratory trials on 2024–2026 data without explicit Controller and custodian sign-off.

---

## 8. Exact Verification Record & Commit Provenance

- **Stage 1 Freeze Commit**: `6d20579486cc62daf5420e61ced2f8dc4732a414` (Pushed and verified via `git ls-remote`).
- **Parent Commit**: `f25954b45577cebb7624fae86cd91df9071a87ab`.
- **Unit Test Coverage**: 56 deterministic synthetic forensic tests passed locally in 0.20s (`tests/test_v06_g2_f3_inference_audit_r1_forensics.py`).
- **Original Test Regression**: 50 original tests passed in 0.50s (`tests/test_v06_g2_flow_funding_entries_r1_*.py`). Total active suite: 106 tests, 100% passing.
- **CI Disclosure**: In accordance with task protocol, the initial freeze push CI status may be superseded or cancelled by this final evidence commit push. Local test execution is 100% verified.
