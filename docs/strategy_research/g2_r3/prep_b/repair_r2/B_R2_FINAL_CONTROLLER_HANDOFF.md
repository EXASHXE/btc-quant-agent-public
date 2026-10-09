# V0.6 G2 R3 P0 — Role B Final Independent Behavioral Re-Audit Handoff (Repair R2)

## 1. Executive Summary & Terminal Verdict

- **Task ID**: `V06_G2_R3_P0_B_INDEPENDENT_R2_FINAL_BEHAVIOR_REAUDIT`
- **Auditor Role**: `GEMINI_B` (Independent Verifier & Adversarial Auditor)
- **Controller Dispatch SHA**: `20ad1e442fb7cce58c618c4aac1e2a3b6241f647` (`reviews/v0.6/b_line/V06_G2_R3_P0_A_R2_CONTROLLER_RECEIPT_CI_ADJUDICATION_AND_B_REAUDIT_DISPATCH.md`)
- **Pinned Prompt SHA**: `16fde9a2ece7a9f2a0099b3f36a289d80e72aaf9` (`prompts/v0.6/b_line/V06_G2_R3_P0_B_R2_FINAL_INDEPENDENT_REAUDIT_R1.md`)
- **Role B Start SHA**: `f1ec703b7c7276582f324ac25b9d1000f1b5ef14` (`feature/v06-bline-g2-overnight-verifier-b`)
- **Role A Immutable Target SHA (R2)**: `2c60b0653d3619eedf457753511a9ecc84c1cd5b` (`feature/v06-bline-g2-overnight-discovery-a`)
- **Role A R2 Parent SHA (R1)**: `5c542edd418a74b440162610fd540b1f01e423d3`
- **Role A R1 Initial SHA**: `2f0383816127cb7d87cf5deb559aeda0b04f1624`
- **Role A Original Blocked SHA**: `3b8befb0112cfe2d314ad65964762a3fb251e710`
- **Frozen Code Baseline SHA**: `cd907b09d4d2ebfdcf6eb0fc5ca1bd62ce2bc8aa`
- **Frozen Method Addendum SHA**: `e4b52efb89433fb1bc4ebdd0cd2fbcd7db30ff99`
- **Original G2 R3 Design SHA**: `830f64fc1be91e3bf1c06a6be53d445d42dcce2d`
- **Terminal Verdict**: **`R2_B_SEMANTIC_BLOCKED__REPLAN_ENGINE_ARCHITECTURE`**

### Summary Counts (`B01`–`B07`)

| Status | Count | Finding IDs |
| :--- | :---: | :--- |
| **`PASS`** | **2** | `B02`, `B04` |
| **`BLOCKED`** | **5** | `B01`, `B03`, `B05`, `B06`, `B07` |
| **`INCOMPLETE`** | **0** | None |

### Authority & Isolation Guards

| Guard | Status / Value |
| :--- | :--- |
| `LIVE_A_WORKTREE_READS` | `0` (All inspections and dynamic executions materialized via `git archive` into `/tmp`) |
| `RAW_MARKET_BODY_READS` | `0` (`EMPIRICAL_PRICE_BODY_AUTHORITY = NONE`) |
| `PROTECTED_HOLDOUT_2024_01_01_TO_2025_11_30` | `UNTOUCHED` (`False`) |
| `FUTURE_BLIND_2025_12_01_PLUS` | `UNTOUCHED` (`False`) |
| `TESTNET_AUTHORITY` | `NOT_AUTHORIZED` |
| `REAL_FUNDS_WRITE_AUTHORITY` | `NONE` |

---

## 2. Git Lineage, Allowlist Scope, and CI Context on Role A R2

1. **Lineage & Allowlist Verification**:
   - `git rev-parse 2c60b0653d3619eedf457753511a9ecc84c1cd5b^` == `5c542edd418a74b440162610fd540b1f01e423d3` (`True`).
   - `git rev-parse 16fde9a2ece7a9f2a0099b3f36a289d80e72aaf9^` == `20ad1e442fb7cce58c618c4aac1e2a3b6241f647` (`True`).
   - `git diff --name-only 5c542edd418a74b440162610fd540b1f01e423d3 2c60b0653d3619eedf457753511a9ecc84c1cd5b` contains exactly the 7 expected Role A R2 files:
     1. `docs/strategy_research/g2_r3/prep_a/repair_r2/R2_CONTROLLER_HANDOFF.md`
     2. `evidence/v0.6/b_line/g2_overnight_p0_a/repair_r2/R2_B01_B07_BEFORE_AFTER_MATRIX.json`
     3. `evidence/v0.6/b_line/g2_overnight_p0_a/repair_r2/R2_SYNTHETIC_EXECUTION_RECEIPT.json`
     4. `src/btc_quant_agent/strategy_research/r3_overnight/ledger.py`
     5. `src/btc_quant_agent/strategy_research/r3_overnight/replay_engine.py`
     6. `src/btc_quant_agent/strategy_research/r3_overnight/signals.py`
     7. `tests/test_strategy_research_r3_r2_invariants.py`
   - Out-of-allowlist files (`5c542edd..2c60b065` and `cd907b09..2c60b065`, 30 total files vs baseline): **`0`** (`[]`).
2. **Preservation of Closed R1 Findings (`A01`, `A02`, `A04`, and `A05` Band/Stop Subcases)**:
   - **`A01` (`PASS`)**: `src/btc_quant_agent/__init__.py` remains absent/unmodified relative to `cd907b09d4d2ebfdcf6eb0fc5ca1bd62ce2bc8aa`.
   - **`A02` (`PASS`)**: `evidence/v0.6/b_line/g2_overnight_p0_a/AUDIT_MANIFEST_INSPECTION_RECEIPT.json`, `evidence/v0.6/b_line/g2_overnight_p0_a/repair_r1/AUDIT_MANIFEST_CORRECTION_RECEIPT.json`, and `docs/strategy_research/g2_r3/prep_a/LEGACY_BTC_DEVELOPMENT_PARTITION_PROPOSAL.md` were untouched in `5c542edd..2c60b065`; the 15-month (`2022-10`..`2023-12`) canonical development partition remains intact.
   - **`A04` (`PASS`)**: `SignalGenerator._active_breakouts` remains keyed by `(candidate.id, symbol, candidate.direction)` and is permutation-invariant across all 8 frozen candidates.
   - **`A05` Band & Stop Subcases (`PASS`)**: Retest touch band (`±0.25 * ATR20`) and initial stop (`extremum -/+ 0.50 * ATR20`) remain intact.
3. **CI Context on `2c60b0653d3619eedf457753511a9ecc84c1cd5b` (GitHub Actions Run `37888079460`)**:
   - `Lint & Type Check (Python 3.12)`: **`SUCCESS`**.
   - `Unit & Audit Tests (Python 3.12)`: **`2830 passed / 1 failed / 2 skipped / 9 warnings`**. The sole failure (`tests/test_v051_h40_m3a_production_discovery_producer.py::test_m3a_production_discovery_producer_generates_locked_artifacts`) is inherited v0.5.1 H40 full-suite golden stability debt, unrelated to Role A's R2 diff and outside both Role A and Role B allowlists.

---

## 3. Positive-Oracle Behavioral Audit Matrix (`B01`–`B07`)

| Finding ID | Related R1 IDs | R1 Status (`5c542edd`) | R2 Status (`2c60b065`) | Repaired in R2 vs R1 | Residual / New R2 Semantic Blocker Summary |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **`B01`** | `A06` | `OPEN_BLOCKED` | **`BLOCKED`** | Ordered mark stream in `ReplayEngine.run_simulation` now ingests `8` completed marks across 8 books (`0` in R1); future/unavailable marks rejected | Out-of-order same-symbol marks in `ReplayEngine.run_simulation` (`replay_engine.py:L94,L110-L121`) sort by `max(close_ms, available_at_ms)` and overwrite scalar `latest_eligible = m`, causing delayed older mark `M_stale` (`close_ms=S, avail=S+120s, close=49000`) to overwrite newer mark `M_fresh` (`close_ms=S+60s, avail=S+90s, close=51000`) at step `S+120s` |
| **`B02`** | `A03`, `A08` | `OPEN_BLOCKED` | **`PASS`** | `acknowledged_fill_ids`, `acknowledged_exit_ids`, and `acknowledged_funding_ids` deduplicate 2x/3x entry, exit, and funding ACKs (`1x` vs `2x` in R1) and ignore stale ACKs after close | None |
| **`B03`** | `A03` | `OPEN_BLOCKED` | **`BLOCKED`** | Single position entering at `S` and hitting Stage 6 SL in minute `S` (`end_ms=S+59,999`) is charged `0.200000 USDT` (`0` in R1) | **(D1)** Pre-`S` minute `[S-60s, S)` Stage 6 SL (`end_ms=S-1`) has exit ACK consumed in Stage 1 at `S` *before* Stage 7 at `S` runs, leaving `trade.total_funding_usdt=0` while cash is debited `0.20` and `0.20` is stolen from another open position's `funding_reserve_rf` (`1.80` vs `2.00`); **(D2)** Close-then-reopen at `S` aggregates `max(quantity)` and charges `POS_1`'s `1.00 USDT` debit to `POS_2` (`qty=0.01`); **(D3)** `pending_exit_acks` matched by `trade.symbol == sym` (index 0) charges `POS_AT_S`'s `0.40 USDT` funding to `POS_EARLY` (closed at `S-120s` outside `[S-15s, S+15s]`) |
| **`B04`** | `A07` | `OPEN_BLOCKED` | **`PASS`** | Stage 6 stamps `exit_time_ms = open_time_ms + 59,999`, `holding_minutes >= 1` (`1` vs `0` in R1), and aligns cooldown `ceil_to_minute(exit_time_ms) + 4h` across `ledger.py` and `signals.py`; SL-first, gap open, TP cap, and 4h (`240m`)/12h (`720m`) horizons verified | None |
| **`B05`** | `A06`, `A08` | `OPEN_BLOCKED` | **`BLOCKED`** | Unacknowledged gains do not inflate `decision_equity`; post-kill exit ACK releases active position reserves to `0` (`0` vs `-3.03` / `-5.00` in R1) | **(D1)** Stage 5 (`ledger.py:L658-L659`) releases entry notional commitment at fill creation `O` before fill ACK arrives, and Stage 2 (`ledger.py:L395-L420`) ignores unacknowledged positions and never checks `economic_equity` against `DRAWDOWN_KILL_THRESHOLD_USDT` (`$100`), so a `-$125` pre-ACK mark crash (`economic_equity=874.12 < 900`) leaves `decision_equity=998.9995`, `killed=False`, and `available_capital=942.96 USDT`; **(D2)** `max(Decimal(0), ...)` in 7 places masks negative pre-clamp reserve conservation errors |
| **`B06`** | `A05`, `A04` | `OPEN_BLOCKED` | **`BLOCKED`** | `_advance_active_breakout` advances `bars_since_breakout` before `vol_bps` and 4h EMA returns when `last_exit_time_ms` is `None` (`1` vs `0` in R1) | **(D1)** Cooldown check (`signals.py:L124-L127`) returns `None` *before* `_advance_active_breakout` (`L131`), and `bars_since_breakout += 1` counts calls instead of elapsed hours, so 4 cooldown hours (`H_26..H_29`) freeze `bars_since_breakout=0` and hour `H_30` (`5` elapsed hours after breakout!) confirms a stale retest with `bars_since_breakout=1`; **(D2)** Unconfirmed 3rd hour (`bars_since_breakout == 3`) returns `None` with `canceled=False`, suppressing registration of a new 24h breakout on hour 3 |
| **`B07`** | `A08`, `A03` | `OPEN_BLOCKED` | **`BLOCKED`** | Single trade with sufficient `funding_reserves_usdt >= debit` exiting after `S` decrements `funding_reserve_rf` and leaves `0` leaked reserve on close (`0` vs `0.200000` in R1) | **(D1)** When `pos.funding_reserves_usdt` (`0.40`) `< debit` (`1.00`) at Stage 7 (`ledger.py:L866,L886`), `pos.funding_reserves_usdt` decreases by `0.40` (clamped at `0`) while `book.funding_reserve_rf` subtracts the full `1.00`, diverging `book.funding_reserve_rf` (`1.40`) from `sum(pos.funding_reserves_usdt)` (`2.00`) and driving single-book pre-clamp to `-0.60`; **(D2)** Pre-`S` exit ACK + Stage 7 settlement at `S` double-releases `0.20` from `funding_reserve_rf` and breaks flat-book `cash_delta == sum(trade.net_pnl_usdt)` |

---

## 4. Detailed Findings & Smallest Deterministic Counterexamples

### `B01` — Mark PIT & `ReplayEngine.run_simulation` Mark Ingress (`BLOCKED`)

- **What R2 Fixed vs R1**:
  - In `src/btc_quant_agent/strategy_research/r3_overnight/replay_engine.py:L92-L121`, `ReplayEngine.run_simulation` no longer demands `m.timestamp_ms == t_ms` (`close_ms = t_ms + 60,000 > t_ms`). On an ordered 1-minute mark stream, all 8 books ingest completed marks (`8` vs `0` in R1).
  - In `ledger.py:L298-L311`, `step_minute_open` rejects future marks (`close_ms > open_time_ms`) and unavailable marks (`available_at_ms > open_time_ms`) and only updates `last_available_marks[sym]` if `mark_bar.close_ms > prev_close_ms`.
- **Residual R2 Defect**:
  - In `replay_engine.py:L94,L110-L121`:
    ```python
    sorted_marks[sym] = sorted(m_list, key=lambda m: (max(m.close_ms, m.available_at_ms), m.close_ms))
    ...
    latest_eligible: MarkBar1m | None = None
    while idx < len(m_list):
        m = m_list[idx]
        effective_avail = max(m.close_ms, m.available_at_ms)
        if effective_avail <= t_ms:
            latest_eligible = m
            idx += 1
        else:
            break
    ```
    When two marks for the same symbol become eligible by minute `t_ms = S + 120,000` out of `close_ms` order because an older mark was delayed — specifically `M_fresh` (`timestamp_ms=S, close_ms=S+60,000, available_at_ms=S+90,000, close=51000`, `effective_avail=S+90,000`) and `M_stale` (`timestamp_ms=S-60,000, close_ms=S, available_at_ms=S+120,000, close=49000`, `effective_avail=S+120,000`) — `sorted_marks` places `M_fresh` *before* `M_stale`. At `t_ms = S + 120,000`, the `while` loop pops `M_fresh` (`latest_eligible = M_fresh`) and immediately overwrites it with `M_stale` (`latest_eligible = M_stale`). Only `M_stale` (`close=49000, close_ms=S`) is passed to `book.step_minute_open`, and `M_fresh` (`close=51000, close_ms=S+60,000`) is permanently dropped (`idx` advances past both).
- **Smallest Counterexample**:
  - **Input**: `ooo_marks = [MarkBar1m(timestamp_ms=S, close=51000, available_at_ms=S+90000), MarkBar1m(timestamp_ms=S-60000, close=49000, available_at_ms=S+120000)]` over 3 minutes `[S, S+60000, S+120000]`.
  - **Oracle Expected**: `last_available_marks["BTCUSDT"] == (Decimal("51000"), S + 60_000, S + 90_000)`.
  - **Role A R2 Observed**: `last_available_marks["BTCUSDT"] == (Decimal("49000"), S, S + 120_000)`.
- **Concrete Role B Test**: `tests/test_v06_g2_r3_verifier_repair_r2_reaudit.py::test_r2_b01_mark_pit_and_out_of_order_replay_engine_drop`.

---

### `B02` — Stage 1 ACK Idempotency (`PASS`)

- **What R2 Fixed vs R1**:
  - `VirtualBook` (`ledger.py:L113-L115,L313-L376`) maintains `acknowledged_fill_ids`, `acknowledged_exit_ids`, and `acknowledged_funding_ids`.
  - Delivering entry fill ACK, exit ACK, and funding ACK 2x/3x and again after economic position close applies fee/cash/PnL/reserve deltas once (`1` vs `2` in R1), produces `1` `CompletedTrade`, `1` `FundingEventRecord`, `0` resurrected positions, and exact cash reconciliation (`cash - INITIAL_EQUITY_USDT == completed_trades[0].net_pnl_usdt`).
- **Concrete Role B Test**: `tests/test_v06_g2_r3_verifier_repair_r2_reaudit.py::test_r2_b02_ack_idempotency_2x_3x_stale_and_distinct_orders`.

---

### `B03` — Hourly Settlement Ownership `[S-15000, S+15000]` & Multi-Position Attribution (`BLOCKED`)

- **What R2 Fixed vs R1**:
  - A single position entering at `S` (or `S-60s`) and hitting Stage 6 SL in minute `S` (`end_ms = S + 59,999`) is now charged `0.200000 USDT` at `S` (`0` in R1).
- **Residual / New R2 Defects**:
  1. **`B03-D1` (Pre-`S` Minute `[S-60s, S)` Stage 6 SL/TP Exit ACK Race)**:
     - When a position enters at `S - 60,000` and hits Stage 6 SL in minute `S - 60,000`, `ledger.py:L730-L735` stamps `econ_exit = S - 1` (which lies inside `[S - 15,000, S + 15,000]`) and queues `(trade, ack_available_at_ms=S, c_exit, rem_funding=2.00)` into `pending_exit_acks`.
     - At minute `S`, **Stage 1 runs before Stage 7**: `ledger.py:L347-L363` consumes the exit ACK at `S`, appends `trade` (with `total_funding_usdt=0`) to `completed_trades`, and releases 100% of `rem_funding = 2.00` from `self.funding_reserve_rf`.
     - Later in the same minute `S`, **Stage 7** (`ledger.py:L849-L886`) detects that `ExposureInterval(start_ms=S-60000, end_ms=S-1)` overlaps `[S-15000, S+15000]`, creates a `0.200000 USDT` funding charge, fails to find the trade in `self.positions` or `self.pending_exit_acks` (already popped into `completed_trades` in Stage 1!), and executes `self.funding_reserve_rf = max(Decimal(0), self.funding_reserve_rf - debit)` a second time.
     - **Result**: `completed_trades[0].total_funding_usdt` remains `0` while cash is debited `0.200000` (`cash_delta = -10.704750` vs `trade.net_pnl_usdt = -10.504750`), and `0.200000` is stolen from another open symbol's `funding_reserve_rf` (`ETHUSDT` reserve drops from `2.00` to `1.800000`).
  2. **`B03-D2` (Close-Then-Reopen at `S` `max(quantity)` Aggregation & Wrong Position Attribution)**:
     - In `ledger.py:L841,L856-L867`, `charged_settlements` is keyed by `(sym, S)` instead of `(position_id, S)`, and `qty = max(i.quantity for i in intersecting)` aggregates across distinct positions.
     - When `POS_1` (`qty=0.05`) closes in Stage 4 at `S` (`end_ms = S`) and `POS_2` (`qty=0.01`) opens in Stage 5 at `S` (`start_ms = S`), both intervals intersect `[S-15000, S+15000]`. Because `sym in self.positions` is `True` (pointing to `POS_2`), Stage 7 charges `POS_1`'s `0.05` debit (`1.000000 USDT`) entirely to `POS_2` (`qty=0.01`, 5x its size!) while `POS_1` in `pending_exit_acks` is charged `0`.
  3. **`B03-D3` (`pending_exit_acks` Matched by `trade.symbol == sym` Instead of `position_id`)**:
     - In `ledger.py:L869-L883`, when `sym not in self.positions`, Stage 7 loops over `self.pending_exit_acks` with `if trade.symbol == sym:` and `break`s on index 0.
     - When `POS_EARLY` closed at `S - 120,000` (outside `[S-15000, S+15000]`) with a delayed exit ACK (`S + 60,000`) and `POS_AT_S` (`qty=0.02`) opened and hit Stage 6 SL at `S`, Stage 7 charges `POS_AT_S`'s `0.400000 USDT` funding to `POS_EARLY` (`0.400000` vs expected `0`) and leaves `POS_AT_S` with `0` (`0` vs expected `0.400000`).
- **Concrete Role B Test**: `tests/test_v06_g2_r3_verifier_repair_r2_reaudit.py::test_r2_b03_settlement_window_ack_race_and_multi_position_misattribution`.

---

### `B04` — Minute-End SL/TP Timestamps, Causal OHLC, Cooldown & 4h/12h Horizon (`PASS`)

- **What R2 Fixed vs R1**:
  - In `ledger.py:L730-L784`, Stage 6 intraminute SL/TP stamps `econ_exit = open_time_ms + 59,999` (`1700002859999` vs `1700002800000` in R1), ensuring `holding_minutes >= 1` (`1` vs `0` in R1).
  - Cooldown in both `ledger.py:L556-L561` and `signals.py:L124-L127` is anchored to `ceil_to_minute(last_exit_time_ms) + 4h` (`1700017260000`).
  - Same-bar SL+TP collision resolves SL first (`STOP_LOSS`), adverse open gap executes at worse open, favorable TP is capped at target, and E2E `ReplayEngine` runs confirm `240` holding minutes (`04H`) and `720` holding minutes (`12H`).
- **Concrete Role B Test**: `tests/test_v06_g2_r3_verifier_repair_r2_reaudit.py::test_r2_b04_minute_end_sl_tp_causal_ohlc_and_horizons`.

---

### `B05` — Decision/Economic Equity Valuation, Pre-ACK Safety & Pre-Clamp Reserve Algebra (`BLOCKED`)

- **What R2 Fixed vs R1**:
  - Unacknowledged positions with unrealized gains no longer inflate `decision_equity` before entry fill ACK arrives (`ledger.py:L395-L400`).
  - `_trigger_kill_liquidation` (`ledger.py:L421-L435`) cancels pending orders and releases only their commitments while keeping active position reserves intact until liquidation exit ACK arrives (`0.0000000000` and `0.00` vs `-3.0315125000` and `-5.00` in R1).
- **Residual / New R2 Defects**:
  1. **`B05-D1` (Pre-ACK Unrealized Loss Ignored by Risk/Kill Supervisor & Premature Entry Notional Release in Stage 5)**:
     - In `ledger.py:L658-L659`, Stage 5 immediately releases `pending_entry_released = order.cost_commitment_usdt - c_exit` at fill creation time `O` *before* the entry fill ACK arrives in Stage 1 (`self.cost_commitment_o -= pending_entry_released`).
     - Simultaneously, in `ledger.py:L395-L420`, Stage 2 skips `not pos.is_acknowledged` when computing `decision_equity` and **never checks `self.economic_equity`** against `DRAWDOWN_KILL_THRESHOLD_USDT` (`$100`) or insolvency (`<= 0`).
     - **Counterexample**: `ORD_UNACKED_CRASH` (`qty=0.05`, `entry=50000`, `cost_commitment_usdt=2510`) fills at `S`; mark crashes to `47500` (`-$125` unrealized loss) while fill ACK is still in flight (`available_at_ms = S + 120,000`). At `S + 60,000`, `economic_equity = 874.1248750000` (drawdown `$125.88 > $100` kill threshold), yet `decision_equity = 998.999500000000`, `killed = False`, and `compute_available_capital()` reports **`942.96199875000000 USDT`** of spendable capital.
  2. **`B05-D2` (Negative Pre-Clamp Reserve Conservation Errors Masked by `max(Decimal(0), ...)`)**:
     - `ledger.py` applies `max(Decimal(0), ...)` in 7 locations (`L355, L356, L425, L426, L866, L881, L886`), masking negative pre-clamp reserve values (such as `-0.60 USDT` when a position's funding reserve `0.40` is smaller than its settlement debit `1.00`, or `-0.20 USDT` when Stage 7 at `S` debits `funding_reserve_rf` after Stage 1 at `S` already released the closed trade's full reserve).
- **Concrete Role B Test**: `tests/test_v06_g2_r3_verifier_repair_r2_reaudit.py::test_r2_b05_decision_economic_equity_and_pre_clamp_reserve_algebra`.

---

### `B06` — Closed Retest 3-Hour Elapsed Window, Intermediate Extrema & Cooldown Clock (`BLOCKED`)

- **What R2 Fixed vs R1**:
  - When `last_exit_time_ms` is `None`, `evaluate_hourly_decision` (`signals.py:L130-L131`) calls `_advance_active_breakout` before `vol_bps` and 4h EMA filter returns (`bars_since_breakout == 1` vs `0` in R1).
- **Residual R2 Defects**:
  1. **`B06-D1` (Cooldown Return Precedes `_advance_active_breakout` & Call-Count Increment Freezes Breakout Clock)**:
     - In `signals.py:L124-L131`:
       ```python
       if last_exit_time_ms is not None:
           cooldown_end_ms = ceil_to_minute(last_exit_time_ms) + COOLDOWN_DURATION_MS
           if decision_time_ms < cooldown_end_ms:
               return None

       # Advance any active breakout state for this (candidate, symbol) on this new 1h bar
       self._advance_active_breakout(candidate, symbol, current_1h, atr20)
       ```
       And inside `_advance_active_breakout` (`signals.py:L79`):
       ```python
       breakout.bars_since_breakout += 1
       ```
     - Because the 4h cooldown check returns `None` *before* `_advance_active_breakout` and `bars_since_breakout` increments by call count (`+= 1`) rather than elapsed hours `(current_1h.close_ms - breakout.breakout_hour_ms) // 3_600_000`, any 4-hour cooldown spanning hours `H_26, H_27, H_28, H_29` after a breakout at `H_25` completely skips `_advance_active_breakout`.
     - **Counterexample**: Breakout registered at `H_25`; an existing position exits at `H_25_close + 10m`, placing `H_26..H_29` in 4h cooldown. At `H_30` (**5 elapsed hours** after `H_25`!), cooldown expires, `_advance_active_breakout` increments `bars_since_breakout` from `0` to `1`, and `evaluate_hourly_decision` emits a confirmed `SignalEvent` (`stale_5th_hour_confirmed = True`, `bars_since_breakout = 1`, `elapsed_hours = 5`).
  2. **`B06-D2` (Unconfirmed 3rd Hour Leaves `breakout.canceled = False` and Suppresses New Breakout on Hour 3)**:
     - In `signals.py:L94-L95`, `_advance_active_breakout` only cancels when `breakout.bars_since_breakout > MAX_RETEST_CONFIRMATION_BARS` (`> 3`, i.e. at hour 4). At `bars_since_breakout == 3` (the 3rd post-breakout hour), if confirmation fails, `_evaluate_closed_retest` (`signals.py:L316-L376`) returns `None` at `L376` without setting `breakout.canceled = True` or falling through to register a new 24h breakout occurring on hour 3 (`active_breakout.breakout_hour_ms` stays stuck at `H_25` instead of updating to `H_28`).
- **Concrete Role B Test**: `tests/test_v06_g2_r3_verifier_repair_r2_reaudit.py::test_r2_b06_retest_elapsed_hours_cooldown_freeze_and_third_bar_expiry`.

---

### `B07` — Funding Ledger Cash/Reserve Conservation, Exhaustion & ACK Permutations (`BLOCKED`)

- **What R2 Fixed vs R1**:
  - For a single trade with sufficient `funding_reserves_usdt >= debit` (`2.00 >= 0.20`) that exits *after* settlement `S`, Stage 7 decrements `pos.funding_reserves_usdt` and `self.funding_reserve_rf` by `0.20`, and Stage 1 exit ACK releases the remaining `1.80`, leaving `0` leaked reserve (`0` vs `0.200000` in R1).
- **Residual / New R2 Defects**:
  1. **`B07-D1` (Reserve Exhaustion Before Settlement Breaks Per-Position vs Aggregate Conservation and Drives Pre-Clamp Negative)**:
     - In `ledger.py:L866,L886`:
       ```python
       pos.funding_reserves_usdt = max(Decimal(0), pos.funding_reserves_usdt - debit)
       ...
       self.funding_reserve_rf = max(Decimal(0), self.funding_reserve_rf - debit)
       ```
       When `pos_btc.funding_reserves_usdt` (`0.40 USDT`) `< debit` (`1.00 USDT`) at settlement `S`, `pos_btc.funding_reserves_usdt` is reduced by only `0.40` (to `0.00`), whereas `self.funding_reserve_rf` subtracts the full `debit = 1.00`.
     - **Counterexample**: `POS_BTC` (`funding_reserves_usdt = 0.40`, `debit = 1.00` at `S`) and `POS_ETH` (`funding_reserves_usdt = 2.00`, outside `S` window) start with `book.funding_reserve_rf = 2.40`. After Stage 7 at `S`, `sum(p.funding_reserves_usdt for p in book.positions.values()) == Decimal("2.00")`, but `book.funding_reserve_rf == Decimal("1.400000")` — a **`-0.60 USDT` conservation deficit** that artificially inflates `compute_available_capital()` by `+0.60 USDT` and causes a `-0.60` pre-clamp underflow (`1.40 - 2.00 = -0.60`) when `POS_ETH` later closes. On a single-position book, pre-clamp `funding_reserve_rf - debit = 0.40 - 1.00 = -0.60 < 0`.
  2. **`B07-D2` (Pre-`S` Exit ACK + Stage 7 Settlement at `S` Permutation Double-Releases Reserve & Breaks Cash/Trade PnL Conservation)**:
     - As demonstrated in `B03-D1`, when a position exits via Stage 6 SL in minute `S - 60,000` (`end_ms = S - 1`), Stage 1 at `S` releases 100% of its `2.00` funding reserve and finalizes `CompletedTrade` (`total_funding_usdt = 0`, `net_pnl_usdt = -10.504750`) before Stage 7 at `S` subtracts `0.200000` from `funding_reserve_rf` again (`1.800000` vs `2.00` for witness `POS_ETH`, or `-0.200000` pre-clamp on a single-position book) and debits cash by `0.200000` (`cash_delta = -10.704750 != trade.net_pnl_usdt = -10.504750`).
- **Concrete Role B Test**: `tests/test_v06_g2_r3_verifier_repair_r2_reaudit.py::test_r2_b07_funding_reserve_exhaustion_and_ack_permutation_conservation`.

---

## 5. Architectural Root-Cause Synthesis & Replan Recommendation for Controller

Why did 5 of 7 items (`B01`, `B03`, `B05`, `B06`, `B07`) remain `BLOCKED` in `2c60b0653d3619eedf457753511a9ecc84c1cd5b` after two repair rounds (`R1` and `R2`)? The root causes are **structural data-model couplings** in `r3_overnight` rather than isolated typos:

1. **Position Identity vs Symbol Indexing & Premature Trade Finalization (`B03`, `B07`)**:
   - `VirtualBook` keys active positions by `symbol` (`positions: dict[str, Position]`), keys `charged_settlements` by `(sym, S)` instead of `(position_id, S)`, matches `pending_exit_acks` by `trade.symbol == sym`, and immutable-finalizes `CompletedTrade` at exit creation time (before late-arriving or same-minute Stage 7 funding events at `S` are evaluated).
   - **Architectural Fix Required**: Key all positions, exposure intervals, reserves, and settlement charges by `position_id` (as in Role B's `IndependentBookOracle`), compute `funding_reserve_rf` and `cost_commitment_o` as exact derived sums over per-order / per-position reserve records (eliminating `max(0, ...)` clamping and cross-position reserve theft), and either defer `CompletedTrade` finalization until all settlement windows overlapping `[entry_ms, exit_ms]` have been adjudicated or update trade funding records by `position_id`.
2. **Two-Clock Reserve & Risk Separation (`B05`)**:
   - Releasing entry notional commitment in Stage 5 (`O`) before the entry fill ACK arrives (`A_fill`), while simultaneously excluding unacknowledged positions from Stage 2 risk checks, creates a blind spot where an unacknowledged position has neither entry notional commitment reserved nor mark-to-market loss supervised.
   - **Architectural Fix Required**: Either retain entry commitment until `A_fill` is acknowledged or evaluate `min(decision_equity, economic_equity)` against the `$100` drawdown kill / insolvency latch.
3. **Wall-Clock Elapsed Time vs Call-Count Stepping in `SignalGenerator` (`B06`)**:
   - Advancing breakout state via `bars_since_breakout += 1` *after* the cooldown early-return conflates "calls that passed the cooldown gate" with "elapsed 1h bars since `breakout_hour_ms`".
   - **Architectural Fix Required**: Advance breakout state unconditionally at the top of `evaluate_hourly_decision` (before cooldown gates), compute `bars_since_breakout = (current_1h.close_ms - breakout.breakout_hour_ms) // 3_600_000` from timestamps, and expire unconfirmed breakouts immediately at the end of bar 3 so hour 3 can register a fresh 24h breakout.
4. **Monotonic Mark Ingress in `ReplayEngine` (`B01`)**:
   - Overwriting `latest_eligible = m` in `ReplayEngine.run_simulation` drops fresher marks whenever a delayed older mark becomes available in the same step.
   - **Architectural Fix Required**: Select the eligible mark with the maximum `close_ms` (`if latest_eligible is None or m.close_ms > latest_eligible.close_ms: latest_eligible = m`) or pass all newly eligible marks to `VirtualBook`.

Accordingly, Role B returns the terminal verdict:
**`R2_B_SEMANTIC_BLOCKED__REPLAN_ENGINE_ARCHITECTURE`**

---

## 6. Scoped Verification Commands & Execution Receipt

| Command | Interpreter / Tool | Result |
| :--- | :--- | :--- |
| `/usr/bin/python3.12 -m pytest tests/test_v06_g2_r3_verifier_*.py -v` | `Python 3.12.3` | **`35 passed in 8.4s`** |
| `/root/miniconda3/bin/python -m pytest tests/test_v06_g2_r3_verifier_*.py -v` | `Python 3.13.13` | **`35 passed in 8.4s`** |
| `/root/miniconda3/bin/ruff check scripts/strategy_research/r3_verification tests/test_v06_g2_r3_verifier_*.py` | `ruff 0.16.9` | **`All checks passed! (0 errors)`** |
| `/usr/bin/python3.12 -m compileall -q scripts/strategy_research/r3_verification tests/test_v06_g2_r3_verifier_*.py` | `Python 3.12.3` | **`EXIT=0`** |
| `/usr/bin/python3.12 -m json.tool evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/B01_B07_R2_INDEPENDENT_BEHAVIOR_MATRIX.json > /dev/null` | `Python 3.12.3` | **`VALID_JSON (EXIT=0)`** |
| `/usr/bin/python3.12 -m json.tool evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/R2_B_INDEPENDENT_SYNTHETIC_EXECUTION_RECEIPT.json > /dev/null` | `Python 3.12.3` | **`VALID_JSON (EXIT=0)`** |
