# V0.6 B-Line G2 Goal C — Independent BTC Exit-Book / Funding / Mark / Risk Execution Assurance: Frozen Method Contract (R1)

- **Program Role:** Gemini Goal C — Independent Adversarial Implementation & Forensic Accounting Auditor
- **Controller Dispatch SHA:** `c02743fddccdf517582c371a47e82d8dcbb05923`
- **Exact Start SHA (Parent):** `55ac4c631c69f6edbd275462ad23e4486b9782ed`
- **Audited Exit R1 Freeze Commit:** `de2c1fb222970a93ca797868b91b8544261ebaad`
- **Audited Exit R1 Final Commit:** `55ac4c631c69f6edbd275462ad23e4486b9782ed`
- **Own Branch:** `feature/v06-bline-gemini-goal-execution-assurance-r1`
- **Own Prefix:** `g2_goal_execution_assurance_r1`
- **Stage 1 Gate:** Pre-execution freeze of independent Decimal journal, 48-fixture adversarial collision matrix, synthetic 10x/15x leverage risk harness, causality provers, and one-shot audit runner before historical forensic execution.

---

## 1. Threat Model & Epistemic Classification

Published R2, R3, R3.1, and Exit R1 results (`55ac4c631c69f6edbd275462ad23e4486b9782ed`) report `DEVELOPMENT_ONLY` evidence across 35 monthly folds (`2021-02..2023-12` after `2021-01` warmup). Exit R1 introduced stateful multi-tier order books (`E1`/`E2`), breakeven (`BE`) stop ratification after `TP1_ACK`, quantity reductions prior to 8-hour funding settlements, pending ACK cash locks, and horizon-dependent (`12h`/`18h`/`24h`) prospective fold-end censoring.

Every audited claim is classified into one of five mutually exclusive epistemic categories:

1. `SOURCE_VERIFIED`: Cryptographically verified against committed manifests and local read-only 2021–2023 public Binance USD-M Last, Mark, and Funding archives (`108` monthly ZIPs + `8` daily Mark gap patches).
2. `ALGO_PROVED`: Proved by independent Dual-Decimal recalculation (`decimal_journal.py` with zero production imports), AST/prefix-truncation causality proofs, and the 48-fixture deterministic collision matrix (`F01`–`F48`).
3. `EXECUTION_SENSITIVITY_BOUNDED`: Bounded across the frozen R1 fill modes (`primary`, `through`, `delay`, `unfilled`), cost envelopes (`BASE` 22 bps vs `STRESS` 44 bps nominal roundtrip), and 1-minute settlement Mark OHLC range.
4. `EXCHANGE_UNKNOWN`: Unobservable from 1-minute OHLCV/Mark/Funding archives (sub-minute Last/Mark path ordering, L2 limit-order queue position, exact exchange sub-second settlement Mark at `00:00`/`08:00`/`16:00` UTC, historical as-of fee/maintenance margin brackets, and live API ACK latency).
5. `SYNTHETIC_SCENARIO_ONLY`: Parametric stress contracts (`1x`/`5x`/`10x`/`15x` isolated margin, variation margin, Mark-triggered liquidation, stop-gap bankruptcy deficits) used strictly to falsify naive leverage extrapolation without claiming empirical leveraged returns.

---

## 2. Independent Dual-Decimal Accounting Oracle (`decimal_journal.py`)

To prevent circular verification where production replay code validates itself, `decimal_journal.py` imports **zero** modules from `scripts/strategy_research/g2_*` or `src/`. It implements two orthogonal 50-digit `decimal.Decimal` verifiers:

- **Implementation A (Chronological Event Re-derivation):**
  - Recomputes adverse effective entry and exit prices on the `0.1` USDT tick grid (`ROUND_CEILING` for buy/short-cover, `ROUND_FLOOR` for sell/long-exit).
  - Recomputes 1x cash-cap (`min(cash_before_entry, 1000.0)`) and `5%` reserve admission sizing (`0.95 * min(cash, 1000)`), worst-shock entry reserve (`+0.25 * ATR_1h`), `1.10x` exit friction reserve, and `1.10x * 8 bps * horizon_hours` funding reserve.
  - Recomputes `0.001` BTC lot splitting (`q1 = floor((q / 2) / 0.001) * 0.001`, `q2 = q - q1`) and enforces the `5.0` USDT per-leg minimum notional floor across entry and target prices.
  - Independently searches the `0.1` tick grid for the breakeven stop `BE` that yields non-negative residual net P&L after entry fee, exit fee, and adverse exit spread/slippage, ratified strictly at `tp1_ack_at` (never on the `TP1` fill bar).
  - Recomputes each funding settlement (`00:00`, `08:00`, `16:00` UTC) on the exact remaining open inventory `open_qty(t_settle)` using the latest completed 1-minute Mark bar close `mark_close_asof(t_settle)` where `open_time + 60,000 <= t_settle` (`close_time = t_settle - 1 ms`).
- **Implementation B (Double-Entry Stage Balance-Sheet & Mark Liquidation Verifier):**
  - Verifies at every stage (`BEFORE_ENTRY`, `AFTER_ENTRY`, `TP1_FILL`, `TP1_ACK`, `FUNDING`, `FINAL_EXIT`, `EXIT_ACK`) that:
    - Entry fee is debited **once** at `entry_at`;
    - Realized `TP1` gross P&L is held in `pending_ack_cash` at `tp1_at` and is **not** spendable wallet `cash` until `tp1_ack_at`;
    - Signed funding cash flows immediately adjust wallet `cash` at `settlement_at`;
    - Final exit P&L is held in `pending_ack_cash` at `exit_at` until `exit_ack_at`, preventing any subsequent entry from being pre-funded before `exit_ack_at`;
    - Marked liquidation equity satisfies the exact identity:
      $$\text{MarkEquity}(t) = \text{cash}(t) + \text{pending\_ack\_cash}(t) + \text{open\_qty}(t)\cdot\text{eff\_entry} + \text{side}\cdot\text{open\_qty}(t)\cdot(\text{eff\_mark\_exit}(t) - \text{eff\_entry}) - \text{fee\_exit}(\text{eff\_mark\_exit}(t), \text{open\_qty}(t)).$$

---

## 3. Deterministic 48-Fixture Adversarial Collision Matrix (`collision_matrix.py`)

We freeze `48` deterministic synthetic fixtures (`F01`–`F48`) across 11 categories:

| ID Range | Category | Key Invariants Challenged |
| :--- | :--- | :--- |
| `F01`–`F06` | `GAP_PRECEDENCE` | LONG/SHORT adverse opening `STOP_GAP` (uncapped at bar open) vs favorable single/double tier opening gaps (`TP1_GAP_CAPPED` / `TP2_GAP_CAPPED` capped at limit prices). |
| `F07`–`F10` | `INTRABAR_COLLISION` | Intrabar `STOP + TP1 + TP2` triple collision (fail-closed `STOP` precedence); intrabar `TP1 + TP2` simultaneous reach without opening gap (single-tier `TP1` fill only, `TP2` deferred). |
| `F11`–`F12` | `TOCTOU_STAGE` | Opening gap `TP1` fill blocking intrabar `TP2` on the same 1m bar (`F11`) while permitting intrabar `STOP` on residual `q2` (`F12`). |
| `F13`–`F19` | `FUNDING_BOUNDARY` | `TP1` at `t_settle - 1 ms` vs `t_settle` vs `t_settle + 60s`; funding sign (`+`, `-`, `0`); settlement strictly before entry or at/after final exit excluded. |
| `F20`–`F22` | `BE_ACK_CAUSALITY` | `TP1_ACK` latency (`+60s`), `E2` breakeven stop dormant during the `TP1` fill bar and active strictly from `tp1_ack_at`, `BE` fee+slippage coverage on `0.1` tick grid. |
| `F23`–`F26` | `QUEUE_SENSITIVITY` | Exact limit touch vs one-tick-through (`primary` vs `through`), 1-bar fill delay (`delay`), and non-fill until `TIME_CAP` (`unfilled`). |
| `F27`–`F32` | `LOT_AND_NOTIONAL` | Odd-lot splitting (`0.003` -> `0.001 + 0.002`), single-lot `0.001` rejection, per-tier `< 5.0` USDT notional rejection, and 1x/5%-reserve sizing cap. |
| `F33`–`F35` | `FEE_INTEGRITY` | Single entry fee invariant across partial tiers, exact per-tier exit fees, and zero exit fee on `0.0` residual quantity after double-tier opening gap. |
| `F36`–`F40` | `FOLD_AND_COOLDOWN` | `12h`/`18h`/`24h` `TIME_CAP` closes, prospective fold-end censoring (`entry_at + H + 1m < fold_end`), post-exit cooldown enforcement, and pending ACK cash lock blocking overlapping entries. |
| `F41`–`F45` | `CAUSAL_DATA_GUARDS` | Missing/stale Mark minute rejection (`> 60s`), future Mark exclusion at funding settlement, duplicate exit idempotency rejection, non-minute/out-of-order clock rejection, and zero/negative Mark equity insolvency guard. |
| `F46`–`F48` | `RISK_AND_AUDIT_ORACLE` | Synthetic `10x`/`15x` Mark liquidation vs risk-capped survival (`F46`), signal prefix-truncation lookahead invariance (`F47`), and 4-way tamper detection across fees, funding quantity, ACK clock, and Mark curve (`F48`). |

---

## 4. Synthetic-Only 10x/15x Margin & Liquidation Stress Envelope (`risk_envelope.py`)

- **Strict Prohibition:** 1x cash-account trade returns may **never** be multiplied by `10x` or `15x` and presented as empirical leveraged performance.
- **Parametric Stress Grid:** Evaluates `40` deterministic isolated-margin scenarios across leverage $L \in \{1\times, 5\times, 10\times, 15\times\}$, maintenance margin rates $\text{MMR} \in \{0.004, 0.005, 0.010, 0.025\}$, liquidation clearance fee `75 bps`, realized strategy stop distances (`3.5%` median vs `7.5%`–`8.0%` tail), intrabar adverse Mark shocks, and opening adverse gaps (`10%`), comparing `NAIVE_FULL_LEVERAGE_NOTIONAL` against `RISK_BUDGET_CAPPED_ISOLATED`.
