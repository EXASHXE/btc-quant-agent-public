# Gemini Goal C R2 — Frozen Methodological Contract (`g2_goal_c_risk_assurance_r2`)

- **Task ID:** `V06_G2_GOAL_C_RISK_ASSURANCE_R2`
- **Controller Dispatch SHA:** `1172d3a91324c1a7379bc9e5c24ef601076547c2`
- **Authority URL:** `https://github.com/EXASHXE/btc-quant-agent-public/blob/1172d3a91324c1a7379bc9e5c24ef601076547c2/reviews/v0.6/b_line/V06_G2_GEMINI_ABC_GOAL_R2_CONTROLLER_EVIDENCE_REPAIR_AUTHORITY.md`
- **Repository / Branch:** `EXASHXE/btc-quant-agent-public` / `feature/v06-bline-gemini-goal-c-risk-assurance-r2`
- **Exact Start SHA (`C_R1_FINAL_SHA`):** `f381dd73a8c583e2a28dcab2e354b019b1d946fa`
- **Goal C R1 3-Commit Chain Under Audit:** `8db2e3ff36011c6a65458f8cf4c2ba5e90d5fee2` -> `4c0bac051767f788e6de173f6563a7b47af2ac69` -> `f381dd73a8c583e2a28dcab2e354b019b1d946fa`
- **Original Exit R1 Frozen / Final SHAs:** `de2c1fb222970a93ca797868b91b8544261ebaad` / `55ac4c631c69f6edbd275462ad23e4486b9782ed`

---

## 1. Non-Negotiable Scope & Two-Commit Discipline

1. **Read-Only Upstream Guarantee:** All R2, R3, R3.1, Exit R1 (`g2_exit_horizon_r1`), and Goal C R1 (`g2_goal_execution_assurance_r1`) code and evidence artifacts are strictly read-only. No 2024–2026 holdout data, `/root/workspace/project/Quant-agent/data`, `Quant-agent-sanitized`, other agent worktrees, TESTNET, or LIVE APIs may be accessed.
2. **Strict Two-Commit Protocol:**
   - **Commit 1 (Freeze Method & Tests):** Commits `scripts/strategy_research/g2_goal_c_risk_assurance_r2/**`, `tests/test_v06_g2_goal_c_risk_assurance_r2_*.py`, this method specification, and `evidence/v0.6/b_line/g2_goal_c_risk_assurance_r2/RISK_ASSURANCE_R2_FROZEN_CONTRACT.json` directly parenting `EXACT_START_SHA` (`f381dd73a8c583e2a28dcab2e354b019b1d946fa`).
   - **Commit 2 (Reconciliation Evidence & Report Only):** Commits only the generated reconciliation JSONs and Markdown report under `evidence/v0.6/b_line/g2_goal_c_risk_assurance_r2/**` and `docs/strategy_research/g2_goal_c_risk_assurance_r2/**` directly parenting Commit 1, with zero post-freeze edits to `scripts/` or `tests/`.

---

## 2. Pure-Decimal Isolated & Total Account Margin Model (`decimal_margin_engine.py`)

For an admitted position of signed direction $s \in \{+1, -1\}$, initial BTC quantity $q > 0$, entry price $P_{\text{entry}}$, adverse effective entry price $P_{\text{eff,entry}}$, and target leverage $L \in \{1, 5, 10, 15\}$:

1. **Strict Exchange Initial Margin vs Discretionary Buffer:**
   - Initial notional: $N = q \cdot P_{\text{entry}}$.
   - Strict exchange required initial margin: $M_{\text{strict}} = N / L$.
   - Posted isolated margin: $M_{\text{posted}} = M_{\text{strict}} + B_{\text{disc}}$, where $B_{\text{disc}} \ge 0$ is the explicit discretionary buffer above $N / L$.
   - Effective isolated position leverage: $L_{\text{eff,iso}} = N / M_{\text{posted}}$.
2. **Wallet Margin Balance & Pending ACK Cash:**
   - Entry fee: $\text{fee}_{\text{entry}} = q \cdot P_{\text{eff,entry}} \cdot f_{\text{fee}}$.
   - If partial TP1 executes prior to shock: $q_1 = \lfloor (q / 2) / 0.001 \rfloor \cdot 0.001$, remaining open quantity $q_{\text{open}} = q - q_1$, TP1 exit fee $\text{fee}_{\text{tp1}} = q_1 \cdot P_{\text{eff,tp1}} \cdot f_{\text{fee}}$, and realized TP1 gross-less-drag P&L $\text{PNL}_{\text{tp1}} = s \cdot (P_{\text{eff,tp1}} - P_{\text{eff,entry}}) \cdot q_1$.
   - Un-ACKed TP1 receivable is **not** spendable wallet margin until its ACK clock; only when `tp1_cash_acked_before_shock=True` does $\text{PNL}_{\text{tp1}}$ credit $M_{\text{wallet}}$.
   - Accumulated funding debit on remaining open inventory: $\Delta F_{\text{debit}} = q_{\text{open}} \cdot P_{\text{entry}} \cdot r_{\text{fund}}$ (if settled before shock).
   - Supporting isolated wallet margin:
     $$M_{\text{wallet}} = M_{\text{posted}} - \text{fee}_{\text{entry}} - \text{fee}_{\text{tp1}} - \Delta F_{\text{debit}} + \mathbb{I}_{\text{tp1\_acked}} \cdot \text{PNL}_{\text{tp1}}$$
3. **Closed-Form Decimal Mark Liquidation Price & Threshold:**
   - At Mark price $P_{\text{Mark}} = P_{\text{entry}} \cdot (1 - s \cdot \delta)$, isolated Mark equity after exit fee/slippage buffer $f_{\text{fee}} + f_{\text{adv}}$ is:
     $$E_{\text{iso,Mark}}(P_{\text{Mark}}) = M_{\text{wallet}} + s \cdot (P_{\text{Mark}} - P_{\text{eff,entry}}) \cdot q_{\text{open}} - q_{\text{open}} \cdot P_{\text{Mark}} \cdot (f_{\text{fee}} + f_{\text{adv}})$$
   - Required maintenance margin plus liquidation clearance buffer $c$:
     $$\text{MM}_{\text{req}}(P_{\text{Mark}}) = q_{\text{open}} \cdot P_{\text{Mark}} \cdot (\text{MMR} + c)$$
   - Setting $E_{\text{iso,Mark}}(P_{\text{liq}}) = \text{MM}_{\text{req}}(P_{\text{liq}})$ with $\theta = f_{\text{fee}} + f_{\text{adv}} + \text{MMR} + c$ yields the exact closed-form `Decimal` liquidation price:
     $$P_{\text{liq}} = \begin{cases} \dfrac{P_{\text{eff,entry}} - M_{\text{wallet}} / q_{\text{open}}}{1 - \theta} & (s = +1) \\[8pt] \dfrac{P_{\text{eff,entry}} + M_{\text{wallet}} / q_{\text{open}}}{1 + \theta} & (s = -1) \end{cases}, \qquad \Delta p_{\text{liq}} = \frac{|P_{\text{liq}} - P_{\text{entry}}|}{P_{\text{entry}}}$$
4. **Stop-vs-Liquidation Clock & Intrabar Uncertainty:**
   - Evaluates both 1m settled Mark close (`mark_close_adverse_pct`) and 1m intrabar worst Mark High/Low (`intrabar_adverse_mark_pct`).
   - A strategy stop at distance $d_{\text{stop}}$ triggers before liquidation **only if** $d_{\text{stop}} < \Delta p_{\text{liq}}$ and the intrabar Mark wick does not breach $P_{\text{liq}}$ prior to Last-price stop execution. Under conservative 1m intrabar unknown sequencing, if $\Delta p_{\text{liq}} \le d_{\text{stop}}$ or an intrabar Mark wick breaches $P_{\text{liq}}$, liquidation-first holds (`no retroactive stop fill`).
5. **Gap-Bankruptcy of Isolated Collateral vs Total Account Wealth:**
   - On a bar-open gap to $P_{\text{gap}} = P_{\text{entry}} \cdot (1 - s \cdot d_{\text{gap}})$ with effective exit $P_{\text{eff,gap}}$ and executed stop quantity $q_{\text{stop}}$ ($q_{\text{open}}$ normally, or full $q$ if a cancel-replace ACK race occurs before `tp1_ack_at`):
     $$E_{\text{iso,after\_gap}} = M_{\text{wallet}} + s \cdot (P_{\text{eff,gap}} - P_{\text{eff,entry}}) \cdot q_{\text{stop}} - \text{fee}_{\text{exit}}(P_{\text{eff,gap}}, q_{\text{stop}})$$
   - Isolated collateral bankruptcy occurs iff $E_{\text{iso,after\_gap}} < 0$, with signed deficit $D_{\text{iso}} = \min(0, E_{\text{iso,after\_gap}})$.
   - Total account equity after gap is tracked separately:
     $$E_{\text{total,after\_gap}} = E_0 - \text{fee}_{\text{entry}} - \text{fee}_{\text{tp1}} - \Delta F_{\text{debit}} + \text{PNL}_{\text{tp1}} + s \cdot (P_{\text{eff,gap}} - P_{\text{eff,entry}}) \cdot q_{\text{stop}} - \text{fee}_{\text{exit}}(P_{\text{eff,gap}}, q_{\text{stop}})$$

---

## 3. Exact Filtered Denominator Rule

For any subset filter predicate $P$ applied to a scenario array $S$, let $S_P = \{s \in S \mid P(s)\}$ and $Y = |S_P|$.
For any outcome condition $C$:
- If $Y = 0$, the reported ratio is `"UNKNOWN"` (never `0/0` or a hardcoded constant).
- If $Y > 0$, $X = |\{s \in S_P \mid C(s)\}|$ satisfies $0 \le X \le Y$ and is reported as `f"{X}/{Y}"`.

---

## 4. Per-Minute `E0` and 20-Cell Exposure Reconstruction (`exposure_and_stop_audit.py`)

For all 20 cells (`W1_C04` and `W2_C05` $\times$ `BASE` and `STRESS` $\times$ `E0, H1, H2, E1, E2`), per-minute open quantity $q(t)$, raw Mark notional $q(t) \cdot \text{Mark}_{\text{close}}(t)$, and Marked liquidation equity $E_{\text{Mark}}(t)$ are reconstructed in `Decimal` directly from the committed `*_orders.jsonl` ledgers and authenticated 1m Mark bars, requiring:
- $\max_t |E_{\text{Mark,Decimal}}(t) - E_{\text{Mark,NPZ}}(t)| \le 10^{-7}$ USDT,
- $\left|\max_t \frac{q(t)\cdot\text{Mark}_{\text{close}}(t)}{E_{\text{Mark,Decimal}}(t)} - \text{PeakRatio}_{\text{committed}}\right| \le 10^{-7}$,
- Explicit emission of both `earliest_positive_q_witness` and `peak_exposure_witness` for all four `E0` cells.
