# v0.6 G2 R3 Role B (`GEMINI_B`) — Independent P0 A Findings Repair R1 Re-Audit Report

- **Task ID**: `V06_G2_R3_P0_B_INDEPENDENT_REAUDIT_R1`
- **Controller Dispatch SHA**: `3fb4508110c031eb0ff9226a7e42d918684c554f`
- **Audited Role A Target (`A_REPAIR_SHA`)**: `5c542edd418a74b440162610fd540b1f01e423d3` (parent `2f0383816127cb7d87cf5deb559aeda0b04f1624`, grandparent `3b8befb0112cfe2d314ad65964762a3fb251e710`)
- **Role B Baseline HEAD**: `a0aacd105ac3f3173b15d91c869990748178e222`
- **Code Baseline SHA (`origin/v0.6`)**: `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`
- **Accepted R3 Method SHA**: `cf2d5cc33774cdcff7d709636305bba830e977ef`
- **Original 8-Candidate Registry SHA**: `e5b2006a89441f7eb2ec900e508aff451106b87a`
- **Terminal Re-Audit Verdict**: `P0_B_REPAIR_DISCREPANCY_BLOCKED`
- **Authorities**: `EMPIRICAL_PRICE_BODY_AUTHORITY=NONE`, `G4_TESTNET=NOT_AUTHORIZED`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`

---

## 1. Scope, Isolation & Remote CI Provenance

1. **Isolated Scratch Dynamic Cross-Check**: Role B materialized `5c542edd418a74b440162610fd540b1f01e423d3` strictly from local Git objects (`git archive 5c542edd418a74b440162610fd540b1f01e423d3`) into an ephemeral temporary directory (`tempfile.TemporaryDirectory`), performing **zero reads or writes** to Role A's live worktree (`g2-overnight-discovery-a`) and **zero reads** of any Parquet, ZIP, or funding rate bodies.
2. **Remote GitHub Actions CI Scope**:
   - Run [`37873215393`](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37873215393) on `2f0383816127cb7d87cf5deb559aeda0b04f1624`: **FAILURE** at Ruff `F821` (`undefined name Any` in `tests/test_strategy_research_r3_repair_regressions.py:223`); pytest was never entered.
   - Run [`37875087577`](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/37875087577) on `5c542edd418a74b440162610fd540b1f01e423d3` (after Controller's 1-line `from typing import Any` test import commit): **SUCCESS in `focused` mode (`7 passed in 0.09s`)** because `scripts/ci/test_plan.py` diffs only `BEFORE_SHA..AFTER_SHA` (`2f038381..5c542edd`), selecting only `tests/test_strategy_research_r3_repair_regressions.py`. This is **not** full-suite certification.

---

## 2. Independent Before/After Matrix (`A01`–`A08`) & New/Residual Blockers (`NEW_BLOCKER_B01`–`B07`)

| Finding ID | Before (`3b8befb0`) | After (`5c542edd`) | Verified Repairs | Residual / New Blockers Discovered by Dynamic Cross-Check |
| :--- | :--- | :--- | :--- | :--- |
| **`A01`** | `OPEN_BLOCKED` | **`REPAIRED_VERIFIED`** | `src/btc_quant_agent/strategy_research/__init__.py` deleted; all 26 changed files vs base `e0ff8c34` inside allowlist; PEP 420 namespace imports verified on Python 3.12.3 & 3.13.13. | None |
| **`A02`** | `OPEN_BLOCKED` | **`REPAIRED_VERIFIED`** | Original `AUDIT_MANIFEST_INSPECTION_RECEIPT.json` (`2,933,280`) preserved untouched; superseded by `repair_r1/AUDIT_MANIFEST_CORRECTION_RECEIPT.json` (`2,934,720` rows = `2,038` days $\times 1,440$ min including `2024-02-29`; `ETHUSDT`/`SOLUSDT` physical availability `UNKNOWN`). | None |
| **`A03`** | `OPEN_BLOCKED` | **`PARTIAL_REPAIR_RESIDUAL_BLOCKED`** | Stage 1 fill ACK preserves `max_hold_ms` (`4h`/`12h`) and tracks `closed_position_ids` so same-minute SL/TP closed positions are not resurrected. | **`NEW_BLOCKER_B02`**: Stage 1 (`ledger.py:L284-L330`) is not idempotent against duplicate/repeated fill, exit, or funding ACKs (a repeated `VirtualFill` ACK debits `fee_usdt` a second time).<br>**`NEW_BLOCKER_B03`**: Stage 7 (`ledger.py:L744`) uses strict `hour_s + 3_600_000 < minute_end`, which is `False` at `open_time_ms = S - 60,000` (`minute_end = S`), missing `[S - 15s, S)` funding for positions exiting at `S`; positions entering at `S` that hit same-minute SL/TP in Stage 6 (`L659/L668`) are deleted before Stage 7 at `S` and also pay `0` funding. |
| **`A04`** | `OPEN_BLOCKED` | **`REPAIRED_VERIFIED`** | `SignalGenerator._active_breakouts` keyed by `(candidate_id, symbol, direction)`; `event_id` includes `candidate_id`; `ReplayEngine` uses per-candidate `SignalGenerator` instances; invariant under candidate iteration permutation and repeatable BASE/STRESS hashes. | None |
| **`A05`** | `OPEN_BLOCKED` | **`PARTIAL_REPAIR_RESIDUAL_BLOCKED`** | `LONG low` / `SHORT high` required inside inclusive `[B - 0.25*ATR_b, B + 0.25*ATR_b]` (rejecting deep wicks); `breakout_low` / `breakout_high` included in stop extremum. | **`NEW_BLOCKER_B06`**: In `signals.py:L96, L263-L268`, if an intermediate hour after breakout fails the 1h `vol_bps` filter or 4h EMA ordering check, `evaluate_hourly_decision` returns `None` *before* incrementing `bars_since_breakout` or appending `intermediate_highs`/`intermediate_lows`. |
| **`A06`** | `OPEN_BLOCKED` | **`BROKEN_INTERACTION_BLOCKED`** | Standalone `VirtualBook` ingests marks in Stage 1 using `close_ms` and rejects future marks. | **`NEW_BLOCKER_B01` (CRITICAL)**: `ReplayEngine.run_simulation` (`replay_engine.py:L89-L100`) indexes `marks_by_minute` by `m.timestamp_ms = O`, passing `mbar` only at `current_open_ms = O`, while Stage 1 (`ledger.py:L279`) requires `mbar.close_ms <= O` (where `mbar.close_ms = O + 60,000`). Since `O + 60,000 <= O` is always `False`, `ReplayEngine.run_simulation` **never ingests any marks (`last_available_marks == {}`) and vetoes 100% of signals across all 8 candidates**!<br>**`NEW_BLOCKER_B05A`**: `_stage_2_account_risk` (`ledger.py:L350`) values unacknowledged positions in `decision_equity`. |
| **`A07`** | `OPEN_BLOCKED` | **`PARTIAL_REPAIR_RESIDUAL_BLOCKED`** | `ReplayEngine` passes `last_exit_time_ms` and `last_entry_4h_time_ms`; Stage 4 open exits anchor cooldown to `ceil_to_minute(open_time_ms) + 4h`. | **`NEW_BLOCKER_B04`**: Stage 6 intraminute SL/TP (`ledger.py:L658, L667`) passes `economic_exit_ms=open_time_ms` (bar open $O$) instead of bar close $O + 60\text{s}$, producing `holding_minutes = 0`, shifting `cooldown_until_ms` 60s early, and mutating `last_economic_exit_time_ms` before Stage 1 exit ACK; `signals.py:L86` checks `decision_time_ms` while `ledger.py:L145` checks `signal.available_at_ms`. |
| **`A08`** | `OPEN_BLOCKED` | **`PARTIAL_REPAIR_RESIDUAL_BLOCKED`** | Stage 5 `c_exit` (`ledger.py:L556-L562`) includes `+ sym_filter.tick_size * order.quantity`. | **`NEW_BLOCKER_B07` (CRITICAL)**: Stage 7 (`ledger.py:L761`) reduces `pos.funding_reserves_usdt` by `debit` without reducing `book.funding_reserve_rf`, so Stage 1 exit ACK (`L314`) subtracts only the reduced `pos.funding_reserves_usdt` and **permanently leaks $\sum \text{debit}$ in `book.funding_reserve_rf`** after all positions close!<br>**`NEW_BLOCKER_B05B`**: `_trigger_kill_liquidation` (`ledger.py:L377-L378`) zeroes `cost_commitment_o` and `funding_reserve_rf` at kill latch, and subsequent Stage 1 exit ACK (`L313-L314`) subtracts reserves again, driving `cost_commitment_o = -3.0315125000` and `funding_reserve_rf = -5.00` negative! |
