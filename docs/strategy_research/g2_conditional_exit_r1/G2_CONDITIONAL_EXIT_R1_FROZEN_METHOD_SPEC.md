# Gemini Goal B — One-Shot Causal Conditional 12h->18h Exit Study R1 (`V06_G2_GEMINI_B_CONDITIONAL_EXIT_R1`) — Frozen Method Specification

- **Task ID**: `V06_G2_GEMINI_B_CONDITIONAL_EXIT_R1`
- **Role**: `gemini_b_conditional_exit_r1_worker`
- **Branch**: `feature/v06-bline-gemini-g2-conditional-exit-r1`
- **Controller Dispatch SHA**: `99df4ed8e820984d69d7b895be8808b892ed7f5f`
- **Exact Start SHA**: `d5e3a8407b1b84111dc7f4276865ffd68cb0a7d2`
- **Read-Only Original Exit R1 SHA**: `55ac4c631c69f6edbd275462ad23e4486b9782ed`
- **Read-Only Margin R2 SHA**: `c9846adacc1f2df85931ecf4649e02a3a61cf466`
- **R31 Composite Source Manifest SHA256**: `1f06a24b892a24430f3d2f9e5f2c46e926ed24a437785614c400a1fa536b677c`
- **Development Window**: `2021-02-01 00:00:00 UTC` through `2023-12-31 23:59:59.999 UTC` (`35` monthly walk-forward folds, `2021-01` warmup)
- **Selectable New Configurations**: `4` (`2` frozen entry candidates $\times$ `2` precommitted 12h conditional exit schemes)
- **Cumulative Development Multiplicity**: `48` (entry screen) + `8` (Goal A R1) + `8` (Exit R1) + `4` (Conditional Exit R1) = **`68` exposed development configurations**

---

## 1. Scientific Motivation & Scope

In `V06_G2_GEMINI_EXIT_HORIZON_R1` (`55ac4c631c69f6edbd275462ad23e4486b9782ed`), extending the time cap unconditionally from `E0` (`12h`) to `H1` (`18h`) improved mean `STRESS` net return on both frozen entry candidates (`W1_C04` `+37.3453 bps`, `W2_C05` `+22.4342 bps`), because a majority of accepted `E0` trades terminated at the `12h` `TIME_CAP` (`20/34` on `W1_C04`, `36/55` on `W2_C05`). However:

1. Simultaneous 7-day and 14-day calendar block bootstrap 95% confidence intervals crossed zero across all contrasts; and
2. `W2_C05` remained negative in calendar year `2023` (`-39.7498 bps` under `STRESS` `H1`).

This study tests whether a **precommitted, parameter-free, zero-lookahead conditional decision evaluated strictly at the 12h holding-time boundary (`decision_at = entry_at + 12h`)** can selectively extend favorable `12h` survivors to `18h` while cutting losing or counter-trend `12h` trades at the original `12h` time cap.

### Strict Non-Leakage & Governance Declarations

1. **Holding-Time Decision Rule (Not an Entry-Time Predictor)**: Both `X1_NET_POSITIVE_AT_12H` and `X2_COMPLETED_4H_TREND_AT_12H` are evaluated strictly at `decision_at = entry_at + 12h` (`43,200,000 ms` after `entry_at`) conditional on the trade still being open at `decision_at` and not gapping through `stop` on the `decision_at` bar open. Neither scheme alters entry signals, entry sizing, stop placement, target placement, or pre-12h execution.
2. **Formal Revocations Upheld**: Goal B R1/R2 post-entry future MFE/MAE (`R1_TREND_LEAKAGE`), realized volatility substitution (`R1_VOLATILITY_SUBSTITUTION`), and future funding bins (`R1_FUNDING_LEAKAGE`) remain formally revoked and are never referenced.
3. **Zero Parameter Tuning**: `4` hours for `X2`, `0.0 USDT` net threshold for `X1`, `12h` decision boundary, `18h` extended horizon, and `2.0R` target are frozen before historical execution. No threshold sweeps, horizon grid searches, or ex-post subperiod cherry-picking are permitted.

---

## 2. Frozen Entry Candidates & Cost Tiers

### 2.1 Immutable Entry Candidates (from R3/R31 and Exit R1)

| Candidate ID | Horizon (Base) | Initial Stop | Target | Cooldown | Original Accepted Events (`2021-02..2023-12`) | Original `STRESS` `E0` `TIME_CAP` Count |
|---|---:|---:|---:|---:|---:|---:|
| `W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H` | `12h` | `2.0 * ATR_1h` | `2.0R` | `6h` | `34` | `20` |
| `W2_C05_ASYMMETRIC_VOLATILITY_BREAKOUT_12H` | `12h` | `1.8 * ATR_1h` | `2.5R` | `6h` | `55` | `36` |

### 2.2 Cost & Friction Tiers

| Cost Tier | Taker Fee (per fill) | Spread (round-trip) | Adverse Slippage (per fill) | Total Effective Adverse Tick Offset (per fill) | Tick Rounding |
|---|---:|---:|---:|---:|---|
| `STRESS` (Primary Gate) | `12.0 bps` | `8.0 bps` | `6.0 bps` | `10.0 bps` (`spread/2 + slip`) | Adverse to $0.10 (`ROUND_CEILING` when buying, `ROUND_FLOOR` when selling) |
| `BASE` (Reference) | `6.0 bps` | `4.0 bps` | `3.0 bps` | `5.0 bps` (`spread/2 + slip`) | Adverse to $0.10 (`ROUND_CEILING` when buying, `ROUND_FLOOR` when selling) |

---

## 3. Exact Mathematical Specification of Schemes (`E0`, `H1`, `X1`, `X2`)

For any trade entering at `entry_at` (a UTC minute open $t_0 \equiv 0 \pmod{60\,000}$) with side $s \in \{+1, -1\}$, quantity $q > 0$, raw entry price $P_{\text{raw,in}}$, effective entry price $P_{\text{eff,in}}$, initial stop $P_{\text{stop}}$, and target $P_{\text{target}} = P_{\text{eff,in}} + s \cdot 2.0 R$:

Let $t_{12} = t_0 + 12 \times 3\,600\,000$ (`entry_at + 12h`) and $t_{18} = t_0 + 18 \times 3\,600\,000$ (`entry_at + 18h`).

### 3.1 Identical Pre-12h Path & 12h Boundary Bar-Open Precedence

1. **Strict Pre-12h Identity**: On all 1m bars with `open_time` $t \in [t_0, t_{12} - 60\,000]$, `E0`, `H1`, `X1`, and `X2` follow the exact same bar-open gap and intraminute `STOP`-before-`TARGET` execution rules. Any trade that hits `STOP`, `STOP_GAP`, `TARGET`, or `TARGET_GAP_CAPPED` before $t_{12}$ has `reached_12h_time_cap_boundary = False` and produces byte-identical fills, fees, funding, and PnL across `E0`, `H1`, `X1`, and `X2`.
2. **12h Boundary Bar-Open `STOP_GAP` Precedence**: At the 12h boundary bar $t = t_{12}$, Priority 1 (`STOP_GAP` on `Last[t_12].open`, i.e., $s \cdot (\text{Last\_open}(t_{12}) - P_{\text{stop}}) \le 0$) is checked **before** any `TIME_CAP` or conditional `X1`/`X2` decision. If triggered, all four schemes exit immediately via `STOP_GAP` at `Last[t_12].open` with `outcome_at_12h = "BOUNDARY_OPEN_STOP_GAP_PRECEDENCE"`.

### 3.2 Baseline Reference Schemes (`E0` and `H1`)

- **`E0` (Baseline 12h Time Cap)**: At $t = t_{12}$ (if not stopped on open), exit immediately via `TIME_CAP` at raw price $\min(\text{Last\_open}(t_{12}), P_{\text{target}})$ for $s = +1$ or $\max(\text{Last\_open}(t_{12}), P_{\text{target}})$ for $s = -1$.
- **`H1` (Unconditional 18h Time Cap)**: At $t = t_{12}$, unconditionally extend the active time cap to $t_{18}$ while keeping $P_{\text{stop}}$ and $P_{\text{target}}$ unchanged.

### 3.3 Conditional Scheme 1: `X1_NET_POSITIVE_AT_12H`

At $t_{12}$, using only information closed at or before $t_{12}$:

1. **Latest Completed 1m Mark Close**: Select the 1m Mark candle with `open_time` $= t_{12} - 60\,000$ and `close_time` $= t_{12} - 1$. Let its close price be $M(t_{12}-1)$. (No bar opening at or after $t_{12}$ is read by `X1`'s decision predicate.)
2. **Hypothetical Adverse Exit Price & Fee**:
   $$P_{\text{hyp,out}}(t_{12}) = \text{dec\_effective\_tick}\big(M(t_{12}-1),\, s,\, \text{cost},\, \text{entry}=\text{False}\big)$$
   $$\text{Fee}_{\text{in}} = P_{\text{eff,in}} \cdot q \cdot \frac{\text{fee\_bps}}{10\,000}, \qquad \text{Fee}_{\text{hyp,out}}(t_{12}) = P_{\text{hyp,out}}(t_{12}) \cdot q \cdot \frac{\text{fee\_bps}}{10\,000}$$
3. **Accrued Official Funding Cash up to $t_{12}$**:
   $$\text{Funding}(t_0, t_{12}) = \sum_{\tau \in \mathcal{F}:\, t_0 \le \tau < t_{12} - L_{\text{fund}}} \big(-s \cdot q \cdot M_{\text{asof}}(\tau) \cdot r(\tau)\big)$$
   where $\mathcal{F}$ is the set of official 8h funding timestamps (`00:00`, `08:00`, `16:00` UTC), $M_{\text{asof}}(\tau)$ is the close of the latest completed 1m Mark bar with `close_time` $\le \tau$, and $L_{\text{fund}} = 0$ in baseline (`funding_lag_ms > 0` supported for boundary sensitivity tests).
4. **Estimated Net Liquidation PnL at $t_{12}$**:
   $$\widehat{\text{Net}}_{12\text{h}} = s \cdot \big(P_{\text{hyp,out}}(t_{12}) - P_{\text{eff,in}}\big) \cdot q - \text{Fee}_{\text{in}} - \text{Fee}_{\text{hyp,out}}(t_{12}) + \text{Funding}(t_0, t_{12})$$
5. **Decision Rule**:
   - If $\widehat{\text{Net}}_{12\text{h}} > 0$: set `extend_to_18h = True` (`active_deadline = t_18`), continuing on `[t_12, t_18]` with unchanged $P_{\text{stop}}$ and $P_{\text{target}}$ (producing the exact `H1` path).
   - If $\widehat{\text{Net}}_{12\text{h}} \le 0$: set `extend_to_18h = False` and exit immediately at $t_{12}$ `TIME_CAP` on `Last[t_12].open` (producing the exact `E0` path).

### 3.4 Conditional Scheme 2: `X2_COMPLETED_4H_TREND_AT_12H`

At $t_{12}$, using only completed UTC 1-hour `Last` candles with `close_time` $\le t_{12}$:

1. **Completed 1h Candle Extraction**: Let $H(t_{12}) = \lfloor t_{12} / 3\,600\,000 \rfloor \times 3\,600\,000$ be the latest UTC hour boundary at or before $t_{12}$. The 4 most recently completed UTC 1-hour candles before $H(t_{12})$ are:
   $$B_k = \big[H(t_{12}) - (5-k) \times 3\,600\,000,\; H(t_{12}) - (4-k) \times 3\,600\,000 - 1\big], \quad k \in \{1, 2, 3, 4\}$$
   Each 1-hour candle $B_k$ must consist of exactly `60` contiguous 1m `Last` bars; its close price $C_k$ is the close of its 60th 1m bar (`open_time` $= H(t_{12}) - (4-k) \times 3\,600\,000 - 60\,000$, `close_time` $= H(t_{12}) - (4-k) \times 3\,600\,000 - 1 \le t_{12} - 1$). Any partially formed current hour $[H(t_{12}), t_{12})$ when $t_{12}$ is mid-hour is strictly excluded.
2. **Signed 4-Bar Completed 1h Trend**:
   $$\Delta_{4\text{h}}(t_{12}) = s \cdot (C_4 - C_1)$$
3. **Decision Rule**:
   - If $\Delta_{4\text{h}}(t_{12}) > 0$: set `extend_to_18h = True` (`active_deadline = t_18`, exact `H1` path).
   - If $\Delta_{4\text{h}}(t_{12}) \le 0$: set `extend_to_18h = False` (immediate $t_{12}$ `TIME_CAP`, exact `E0` path).

---

## 4. Account Replay, Fold Embargo, and Statistical Inference

1. **35-Fold Single-Position Account Replay**:
   - Initial cash: `1000.0 USDT` per candidate/scheme/cost cell at `2021-02-01 00:00:00 UTC`, compounded across 35 monthly folds (`2021-02` to `2023-12`).
   - Sizing: `2%` risk per trade, `95%` maximum deployable equity (`5%` cash reserve), `1.0x` gross notional cap, quantized down to `0.001 BTC` lot (`>= 5.0 USDT` min notional).
   - Cooldown: `6h` after `exit_ack_at`.
   - Prospective Fold Censor: `24h` (`PROSPECTIVE_HORIZON_HOURS = 24`) for `E0`, `H1`, `X1`, and `X2` so that fold-end admission is identical across all four schemes and independent of whether a trade extends at `12h`.
2. **Paired Contrasts & Simultaneous Calendar Block Bootstrap**:
   - Primary joint family (`8` contrasts): `W1_C04` and `W2_C05` $\times$ `{X1-E0, X1-H1, X2-E0, X2-H1}`.
   - Secondary per-candidate family (`4` contrasts per candidate): `{X1-E0, X1-H1, X2-E0, X2-H1}`.
   - Resampling: Shared UTC calendar block bootstrap (`7-day` and `14-day` contiguous blocks across `2021-02-01` to `2024-01-01`), `10,000` draws with fixed seed `42`, centered two-sided `max-|T|` simultaneous 95% confidence intervals.
3. **Independent Pure-Decimal Audit**:
   - `>= 20` new `X1`/`X2` real trade witnesses audited from raw R3/R31 ZIP archives in `stdlib` `csv`/`zipfile`/`decimal` (`audit.py`) with zero production helper calls, plus `40` previous Exit R1 `E0`/`H1` witnesses (`>= 60` total Decimal witnesses).

---

## 5. Predeclared Terminal Classification Gate

Exactly one terminal label from `VALID_TERMINALS` is assigned mechanically by `run.py`:

- `X1_X2_DEVELOPMENT_ONLY_CANDIDATE_SIGNAL`: Assigned only if at least one `(candidate, conditional_scheme)` cell beats both `E0` and `H1` under `STRESS`, its simultaneous 7d and 14d `max-|T|` 95% LCBs are strictly $> 0$, neither conditional branch is underpowered (`extended_n >= 10`, `exited_at_12h_n >= 10`, and `post_12h_target_hits_n > 2`), and `W2_C05` year `2023` net return is strictly positive.
- `X1_X2_INSUFFICIENT_SUPPORT`: Assigned when any simultaneous 7d or 14d calendar block bootstrap 95% confidence interval spans zero or negative, or any conditional branch split is thin/underpowered (`< 10` events or `<= 2` post-12h target hits), or `W2_C05` year `2023` absolute return remains $\le 0$, or neither conditional scheme beats both `E0` and `H1` under `STRESS`.
- `X1_X2_METHOD_OR_SOURCE_BLOCKED`: Assigned if any P0 source hash, baseline `E0`/`H1` parity, or Decimal audit check fails.
