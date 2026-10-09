# Role B Final Independent Semantic & Adversarial Architecture Verdict (P1 Architecture V1)

- **Task ID**: `V06_G2_R3_P1_ARCH_V1_B_FINAL_INDEPENDENT_SEMANTIC_AUDIT_R1`
- **Auditor Role**: `GEMINI_B_INDEPENDENT_VERIFIER`
- **Controller Dispatch SHA**: `5f9b7f75215b394ad86d49b468e7acd9a89c23a2` (`reviews/v0.6/b_line/V06_G2_R3_P1_ARCH_V1_A_FINAL_CI_CONTROLLER_L2_ACCEPTANCE_AND_B_DISPATCH_R1.md`)
- **Pinned Prompt SHA**: `f2ff646bb317c7a7cb4de8bf6515e1d3cbe9e5f0` (`prompts/v0.6/b_line/V06_G2_R3_P1_ARCH_V1_GEMINI_B_FINAL_INDEPENDENT_SEMANTIC_AUDIT_R1.md`)
- **Role A Target Commit (`A_TARGET_SHA`)**: `b5d34aacd36dc27454944a22436db555c3f6eeb8`
- **Role A Parent / Grandparent / R2 Chain**: `b5d34aacd36dc27454944a22436db555c3f6eeb8^ == 398e6bab0cdedf07a93827019ca4bf1bf913c7f9`, `398e6bab^ == 89d0c211cff96286203e4fb7459a51042c1257f1`, `89d0c211^ == 2c60b0653d3619eedf457753511a9ecc84c1cd5b`
- **Role B Start Commit (`B_START_SHA`)**: `068a4005f68b5ee4a970063cb1f3bc524a08784a`
- **Role B R1 Baseline Commit**: `f1ec703b7c7276582f324ac25b9d1000f1b5ef14`
- **Frozen Design SHA**: `e5b2006a89441f7eb2ec900e508aff451106b87a` (`docs/strategy_research/g2_r3/METHOD_DESIGN.md`)
- **Method Addendum SHA**: `cf2d5cc33774cdcff7d709636305bba830e977ef` (`docs/strategy_research/g2_r3/METHOD_R1_1_PIT_COST_ACCOUNTING.md`)
- **Code Baseline SHA**: `cd907b09d4d2ebfdcf6eb0fc5ca1bd62ce2bc8aa`
- **Terminal Verdict**: **`ARCH_V1_B_SEMANTIC_BLOCKED_REPLAN_ALTERNATIVE_ENGINE`**

---

## 1. Executive Summary & Distinction Between CI Hygiene (`37918930513`) and Role B Semantic Audit

Role B (`GEMINI_B`) materialized Role A's target commit `b5d34aacd36dc27454944a22436db555c3f6eeb8` via `git archive` into an isolated temporary runtime directory (`/tmp/g2_r3_p1_arch_v1_b_audit_b5d34aac_*`), verified that all imported modules (`ReplayEngine`, `VirtualBook`, `SignalGenerator`, `Bar1m`) resolved strictly inside that isolated archive, and executed both **positive dynamic verification** and **adversarial cross-stage semantic verification** across `B01`–`B07` and the 240h-warmup synthetic E2E pipeline.

### Engineering CI vs. Independent Semantic Audit
- **GitHub Actions Run `24259930270` / Check Run `37918930513` (`SUCCESS`)**: Confirms engineering hygiene (`ruff`, `compileall`, and Role A's self-authored unit test suite `tests/test_strategy_research_r3_architecture_invariants.py`) and confirms that Role A touched only its 8 allowed files since `2c60b0653d3619eedf457753511a9ecc84c1cd5b`.
- **Role B Independent Positive + Adversarial Audit (`ARCH_V1_B_SEMANTIC_BLOCKED_REPLAN_ALTERNATIVE_ENGINE`)**: While Role A's narrow positive fixtures for `B01`–`B07` (which directly encoded Role B's R2 counterexamples) pass (`7/7` positive cases `PASS`), **6 of 7 items (`B01`, `B02`, `B03`, `B05`, `B06`, `B07`) fail under mandatory adversarial and cross-stage conservation checks (`1/7` final `PASS`, `6/7` final `BLOCKED`)**.

Because `b5d34aacd36dc27454944a22436db555c3f6eeb8` still relies on ad-hoc mutable lists and side-dicts (`_unsettled_exit_trades`, `all_positions_by_id`, payload-blind `set[str]` ACK IDs, and position deletion prior to exit ACK settlement) rather than a true double-entry state-governed liability ledger, **Role B recommends terminating the R3/R4/R5 patch loop on Role A's current engine and transitioning to an alternative event-sourced double-entry engine**.

---

## 2. B01–B07 Positive & Adversarial Verification Matrix

| Item | Domain | R2 (`2c60b065`) | Role A Claim (`b5d34aac`) | Role B Positive Case (`b5d34aac`) | Role B Adversarial Case (`b5d34aac`) | Final Verdict |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **B01** | Mark-Bar As-Of Visibility, Monotonicity, Duplicate Conflict & Stage 8 MTM | `FAIL` | `PASS` | `PASS` | `BLOCKED` | **`BLOCKED`** |
| **B02** | ACK Idempotency, Contradictory Payload Rejection & Out-of-Order Late ACK Integrity | `FAIL` | `PASS` | `PASS` | `BLOCKED` | **`BLOCKED`** |
| **B03** | Funding Window `[S-15000, S+15000]`, Ownership Attribution & Reserve Retention | `FAIL` | `PASS` | `PASS` | `BLOCKED` | **`BLOCKED`** |
| **B04** | Exit Semantics: SL-First Tie-Break, Gap Open Execution, Minute-End Close & Cooldown | `FAIL` | `PASS` | `PASS` | `PASS` | **`PASS`** |
| **B05** | Unacknowledged Fill/Exit Exposure, Conservative Risk Equity & Available Capital | `FAIL` | `PASS` | `PASS` | `BLOCKED` | **`BLOCKED`** |
| **B06** | Signal State Machine Progression, Skipped-Bar History Scan & 12h Geometry Gate | `FAIL` | `PASS` | `PASS` | `BLOCKED` | **`BLOCKED`** |
| **B07** | Per-Position Funding Reserve Cap, Shortfall Liability & Cross-Stage Conservation | `FAIL` | `PASS` | `PASS` | `BLOCKED` | **`BLOCKED`** |

---

## 3. 8-Stage Cross-Stage Timeline & Capital Conservation Audit Around Settlement `S`

Role B traced `VirtualBook.step_minute_open` across all 8 stages around funding settlement `S = 1700002800000`:

| Stage / Timestamp | Ledger Operation in `b5d34aac` | Conservation / Semantic Defect Observed |
| :--- | :--- | :--- |
| **Pre-`S` (`S - 5000ms`)**: Stage 1 (`_stage_1_available_messages`, `ledger.py:L384-L394`) | Position exits at `S - 10000ms` (inside `[S - 15000, S)`), and its exit ACK arrives at `S - 5000ms` (`open_time_ms != target_s`). | **B03-D2**: `overlaps_current_s` checks `open_time_ms == target_s`, which is `False` at `S - 5000ms`. Stage 1 immediately decrements `self.funding_reserve_rf -= rem_funding` (`1.00 -> 0.00`), releasing 100% of the funding reserve **before** settlement `S` occurs! |
| **At `S` (`open_time_ms == S`)**: Stage 1 (`_stage_1_available_messages`, `ledger.py:L384-L394`) | Exit ACK for a pre-`S` close (`S - 1`) arrives at `S`. Stage 1 removes the tuple from `pending_exit_acks` and stashes `(trade, rem_funding)` into `self._unsettled_exit_trades[pos_id]`. | **B07-D2**: During **Stage 2 (`_stage_2_account_risk`)** and **Stage 3 (`accept_hourly_signals` / sizing)** at `S`, `book.funding_reserve_rf` (`0.50`) does **not** equal `sum(pos.funding_reserves_usdt) + sum(item[3] for item in pending_exit_acks)` (`0.00`), breaking Role A's claimed cross-stage conservation invariant. |
| **At `S` (`open_time_ms == S`)**: Stage 7 (`_stage_7_funding_ownership`, `ledger.py:L882-L926`) | Stage 7 computes funding `debit` (`1.00 USDT`), consumes `pos.funding_reserves_usdt` (`0.40 -> 0.00`) and decrements `self.funding_reserve_rf` (`2.40 -> 2.00`), then appends `f_rec` (`available_at_ms = S + 60000`, or `S + 120000` if delayed) to `pending_funding_acks`. | **B03-D1 & B07-D1**: Violates `METHOD_R1_1_PIT_COST_ACCOUNTING.md` (*"past unresolved funding ownership retains its reserve until FUNDING_ACK"*). Between Stage 7 at `S` and `f_rec.available_at_ms`, the `0.40 USDT` reserve is already released from `funding_reserve_rf`, the `0.60 USDT` shortfall has no liability reserve, and the `1.00 USDT` debit has not yet been deducted from `cash` (`1000.00`). Consequently, `compute_available_capital()` is inflated by the full `1.00 USDT` unpaid funding liability (`941.00` instead of `940.00`). |
| **At `S`**: Stage 8 (`_stage_8_ex_post_report`, `ledger.py:L943-L947`) | Stage 8 computes `economic_equity` from `marks_1m.get(sym)` without checking `m_bar.close_ms <= open_time_ms` or `m_bar.available_at_ms <= open_time_ms`, else falls back to `pos.effective_entry`. | **B01-D2**: Unclosed future mark bars (`close_ms = S + 60000`, `close = 60000`) leak directly into `economic_equity` (`1100.00` instead of `1000.00`), and when `marks_1m` is empty on a step with no newly arriving mark, `mark_price` resets to `pos.effective_entry` (`50000`) instead of `last_available_marks[sym][0]` (`51000`). |
| **Post-Close Pre-Exit-ACK (`S + 60000ms`)**: Stage 2 (`_stage_2_account_risk`, `ledger.py:L423-L455`) | Position filled at `S` (`qty = 0.15`, `entry = 50025`) hits `stop = 49000` in Stage 6 at `S`, crystallizing a `-$157.425` gross loss (`-$169.34` net loss, exceeding the `$100` drawdown kill threshold). Stage 6 deletes `self.positions["BTCUSDT"]` and places the loss into `pending_exit_acks`. | **B05-D1**: When the entry fill ACK arrives at `S + 60000ms` (releasing `unacked_entry_commitment_usdt`) while the exit ACK is still pending (`available_at_ms = S + 120000ms`), Stage 2 iterates only over `self.positions.values()` (empty!) and completely ignores `pending_exit_acks`. `risk_equity` rebounds to `992.49625 USDT`, `book.killed` stays `False`, and `compute_available_capital()` reports `933.7769 USDT` of phantom available capital despite a crystallized `-$169.34` loss! |

---

## 4. Prioritized Blocker Breakdown (B01, B02, B03, B05, B06, B07)

### Blocker 1 (CRITICAL — `B05-D1` / `B05-D2`): Pending Exit Losses Invisible to Stage 2 Drawdown Kill & Capital Sizing
- **Code Location**: `src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L134-L140,L423-L455,L551-L558,L805-L839`
- **Mechanism**: Role A fixed `B05` only for *open* unacknowledged positions still present in `self.positions`. The moment a position closes in Stage 4 (`_stage_4_due_exits`) or Stage 6 (`_stage_6_intraminute_protection`), `del self.positions[sym]` removes it from `self.positions`, while its realized loss awaits `ack_available_at_ms` in `self.pending_exit_acks`. `_stage_2_account_risk` never inspects `self.pending_exit_acks` or `self.pending_funding_acks`. Furthermore, `compute_available_capital()` (`L135`) uses `0.95 * self.decision_equity` instead of `0.95 * risk_equity`, ignoring unacknowledged unrealized losses `< $100` (`-$90.30` in `B05-D2`).

### Blocker 2 (CRITICAL — `B03-D1` / `B03-D2` / `B07-D1` / `B07-D2`): Premature Funding Reserve Release Before `FUNDING_ACK` & Unreserved Shortfall Liability
- **Code Location**: `src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L384-L394,L882-L926`
- **Mechanism**:
  1. In Stage 7 at `S`, Role A immediately decrements `self.funding_reserve_rf` by `consumed = min(avail_res, debit)` (`L885,L901,L911`) even though `f_rec` (`L928-L938`) does not debit `self.cash` until `f_rec.available_at_ms` (`S + 60000ms` or later). This violates `METHOD_R1_1_PIT_COST_ACCOUNTING.md` (*"past unresolved funding ownership retains its reserve until FUNDING_ACK"*).
  2. When `debit > avail_res` (`B07-D1`: `debit = 1.00`, `avail_res = 0.40`, `shortfall = 0.60`), neither the `0.40` consumed reserve nor the `0.60` shortfall is held in any liability reserve between `S` and `f_rec.available_at_ms`.
  3. When a position exits inside `[S - 15000, S)` and its exit ACK is processed at `open_time_ms < S` (`B03-D2`), Stage 1 checks `open_time_ms == target_s` (`False`) and releases `rem_funding` before `S`.
  4. In Stage 7 (`B03-D3`, `L889,L914`), the fallback `interval.position_id in trade.trade_id` is a substring check that attributes `POS_1`'s funding charge to `TRD_POS_10_OLD`.

### Blocker 3 (HIGH — `B01-D1` / `B01-D2`): Conflicting Same-Close Duplicate Marks & Stage 8 Future Mark Leak
- **Code Location**: `src/btc_quant_agent/strategy_research/r3_overnight/replay_engine.py:L95,L118-L126`, `ledger.py:L320-L331,L943-L947`
- **Mechanism**:
  1. Two mark bars with the same `close_ms` and `available_at_ms` but conflicting prices (`50000` vs `52000`) do not fail closed; `ReplayEngine` selects the first (`50000`) via strict `>` while `VirtualBook` selects the last (`52000`) via `>=`, and a late duplicate with the same `close_ms = S` (`avail = S + 60s`, `close = 48000`) overwrites the already-settled mark at `S + 60s`.
  2. Stage 8 (`_stage_8_ex_post_report`, `ledger.py:L943-L947`) reads `marks_1m.get(sym)` without checking `close_ms <= open_time_ms` or `available_at_ms <= open_time_ms` (leaking unclosed future mark prices into `economic_equity`), and resets `mark_price` to `pos.effective_entry` when `marks_1m` is empty.

### Blocker 4 (HIGH — `B02-D1` / `B02-D2` / `B02-D3`): Contradictory Reused ACK IDs, Late Exit ACK Cooldown Rewind & Premature Auto-ACK
- **Code Location**: `src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L336-L360,L366-L407`
- **Mechanism**:
  1. Stage 1 tracks only `set[str]` IDs (`acknowledged_fill_ids`, `acknowledged_exit_ids`, `acknowledged_funding_ids`) and silently ignores contradictory payloads reusing an existing ID (`B02-D1`).
  2. Stage 1 unconditionally assigns `self.cooldown_until_ms[trade.symbol] = ceil_exit_ms + COOLDOWN_DURATION_MS` (`L396`) without `max(...)`, so a delayed exit ACK from an earlier trade `P1` rewinds a newer trade `P2`'s active cooldown backwards by `7,140,000 ms` (119 minutes, `B02-D2`).
  3. Stage 1 auto-acknowledges any position at `entry_available_at_ms` if `not any(f.fill_id == pos.position_id for f in self.pending_fill_acks)` (`L354`), prematurely releasing `unacked_entry_commitment_usdt` whenever `VirtualFill.fill_id != pos.position_id` (`B02-D3`).

### Blocker 5 (HIGH — `B06-D1` / `B06-D2`): Single-Bar `_advance_active_breakout` Drops Skipped-Hour Cancellations & Dual-Role Bar Fallthrough
- **Code Location**: `src/btc_quant_agent/strategy_research/r3_overnight/signals.py:L62-L96,L361-L398`
- **Mechanism**:
  1. `_advance_active_breakout` computes `elapsed_hours = (current_1h.close_ms - breakout.breakout_hour_ms) // 3_600_000` (`L79`), but only appends `current_1h.high`/`current_1h.low` and only checks `current_1h.close` for cancellation instead of scanning intermediate bars in `bars_1h` since `last_advanced_hour_ms`. Skipping a single intermediate hour call drops an intermediate crash (`close = 47200`, `low = 47100`) and emits a false confirmation signal on the next bar (`B06-D1`).
  2. When a breakout cancels on hour 1, 2, or 3, ` _evaluate_closed_retest` falls through on the **same** 1h bar to register a brand-new 24h breakout (`B06-D2`).

---

## 5. Synthetic 240h-Warmup E2E Verification & Final Controller Recommendation

- **Happy-Path Synthetic E2E Reconciliation**: Role B independently reconstructed the 256-hour (15,360-minute, 240h warmup) synthetic dataset and verified Role A's happy-path numbers:
  - `CLOSED_RETEST_LONG_04H` (`BASE`): `1` trade, `qty = 0.006`, `effective_entry = 50030.10`, `effective_exit = 49979.90`, `fees = 0.360036`, `funding = 0.480048000`, `net_pnl = -1.141284000`, `final_cash = 998.858716000000`.
  - `CLOSED_RETEST_LONG_12H` (`BASE`): `1` trade, `qty = 0.006`, `fees = 0.360036`, `funding = 1.440144000`, `net_pnl = -2.101380000`, `final_cash = 997.898620000000`.
  - `CLOSED_RETEST_LONG_12H` (`STRESS`): `0` trades (`final_cash = 1000.000000000000`), retained as a `STRESS_COST_GEOMETRY_INELIGIBLE` witness.
  - Symbol input order permutation (`{"BTCUSDT", "ETHUSDT"}` vs `{"ETHUSDT", "BTCUSDT"}`) is invariant on the happy path.
- **Why Happy-Path E2E Is Insufficient**: Role A's synthetic E2E scenario uses synchronous `available_at_ms = t + 60s` with zero delayed exit ACKs, zero delayed funding ACKs, zero funding reserve shortfalls, and zero same-close conflicting marks. As proven in Sections 3 and 4, as soon as asynchronous ACK delays or reserve shortfalls occur, `VirtualBook`'s cross-stage conservation and risk-equity invariants break down.
- **Terminal Controller Action**: Emit **`ARCH_V1_B_SEMANTIC_BLOCKED_REPLAN_ALTERNATIVE_ENGINE`**. Do **not** enter an R4/R5 patch cycle on Role A's current `VirtualBook` implementation; transition to an alternative event-sourced double-entry engine architecture.
