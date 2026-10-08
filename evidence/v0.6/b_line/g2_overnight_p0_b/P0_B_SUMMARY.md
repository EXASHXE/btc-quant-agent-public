# G2 R3 Parallel P0 — Role B (`GEMINI_B`) Independent Synthetic Oracle & Static Audit Summary

- **Task ID**: `V06_G2_R3_PARALLEL_P0_OFFLINE_PREPARATION`
- **Role**: `GEMINI_B` / Independent PIT, Fill, Cost & MTM Verifier
- **Worktree**: `/root/workspace/project/quant-v0.6/g2-overnight-verifier-b`
- **Branch**: `feature/v06-bline-g2-overnight-verifier-b`
- **Controller Dispatch SHA**: `56f8a9faa1a4539124ab006b49bf42b6e7c997e3`
- **Frozen Base SHA (`origin/v0.6`)**: `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`
- **Accepted Design Addendum HEAD SHA**: `cf2d5cc33774cdcff7d709636305bba830e977ef`
- **Original 8-Candidate Design SHA**: `e5b2006a89441f7eb2ec900e508aff451106b87a`
- **Source Audit SHA**: `12793bc04db7414d11a0961684fd14f5df3ce16e`
- **Audited Role A Remote Commit (`origin/feature/v06-bline-g2-overnight-discovery-a`)**: `3b8befb0112cfe2d314ad65964762a3fb251e710` (handoff `a_impl_sha`: `3ebb7db9a1043e58843b518af9381218d9f25af1`)
- **Standalone Role B Oracle Status**: `P0_B_ORACLE_READY_FOR_CONTROLLER`
- **Overall Terminal Status (Role A Cross-Audit)**: `P0_B_DISCREPANCY_BLOCKED`
- **Authority & Safety**: `REAL_FUNDS_WRITE_AUTHORITY=NONE`, `EMPIRICAL_EXECUTION_AUTHORITY=NONE`, `raw_parquet_or_zip_body_reads=0`, `live_sibling_worktree_reads=0`, `external_network_calls=0`.

---

## 1. Independent Synthetic Oracle & Focused L1 Test Suite (`20 / 20 PASS`)

Role B implemented a standalone mathematical and event-driven synthetic oracle in `scripts/strategy_research/r3_verification/` without importing or copying Role A's replay engine:

1. **PIT Aggregation & Signal Oracle (`pit_bar_and_signal_oracle.py`)**:
   - Enforces `[open_ms, close_ms)` half-open intervals, `available_at_ms = close_ms + 60,000 ms`, exclusion of unfinished 1h/4h buckets, and invalidation on missing/duplicate/non-monotonic/corrupted 1m bars.
   - Verifies SMA-seeded EMA20/EMA50 on 4h closes, prior-close 20-bar True Range arithmetic mean (`ATR20`), 12-bar Efficiency Ratio (`ER12`), Family 1 (`STRUCTURAL_CONTINUATION`) and Family 2 (`CLOSED_RETEST`) state transitions, single-use breakout consumption, and `STRESS_COST_GEOMETRY_INELIGIBLE` classification (`280bp > 250bp` max stop) for all four 12h candidates under hourly `8bp` stress while keeping all 8 candidate IDs in the registry.
2. **Two-Clock 8-Stage Accounting & Risk Oracle (`two_clock_accounting_oracle.py`)**:
   - Explicitly separates Economic Clock (`t_econ`) and Decision Clock (`t_dec = t_econ + 60s`), implementing the exact 8-stage minute-open pipeline (`1. Available messages` -> `2. Account risk & mark freshness` -> `3. Scheduling` -> `4. Previously due exits` -> `5. Previously due entries` -> `6. Intraminute protection` -> `7. Funding ownership` -> `8. Ex-post report`).
   - Verifies 5% reserve buffer (`A = max(0, 0.95*E_d - R_f - C_o)`), 1x gross leverage and `333.333333333333 USDT` per-asset ceiling, Base (`22bp`) and Stress (`44bp`) round-trip one-time costs, tick/lot adverse rounding, same-minute SL-over-TP collision priority, no TP gap overcredit, `[S - 15s, S + 15s]` funding ownership with zero positive funding credit under stress, and Mark-Price-only unrealized MTM with delayed next-open (`M + 60s`) drawdown kill liquidation.
3. **Static Manifest & Boundary Oracle (`manifest_and_boundary_oracle.py`)**:
   - Verifies `artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json` (`67` months `2021-01..2026-07`, `2,934,720` rows, `0` gaps, `6,114` funding rows, `210` archive checksums, `ARCHIVAL_EVENT_TIME_RECONSTRUCTED`), blocks `v0.3` holdout overlap `[2026-02-01, 2026-08-01)` (`128,160` overlapping minutes across `2026-02..2026-04`), proposes calendar-only pre-2026 exposed development windows (`60` eligible months `2021-01..2025-12`), and enforces negative boundary checks on stale/corrupted marks, RC2 protected symbols, wrong products, and denylist paths.

| Runner | Version | Focused Tests | Result |
| :--- | :--- | :--- | :--- |
| `/usr/bin/python3.12` | `Python 3.12.3` (`pytest 9.0.3`) | `20` tests across `tests/test_v06_g2_r3_verifier_*.py` | `20 passed, 0 failed, 0 skipped` |
| `/root/miniconda3/bin/python` | `Python 3.13.13` (`pytest 8.4.2`) | `20` tests across `tests/test_v06_g2_r3_verifier_*.py` | `20 passed, 0 failed, 0 skipped` |
| `/root/miniconda3/bin/ruff` | `ruff 0.16.9` | `scripts/strategy_research/r3_verification` + `tests/test_v06_g2_r3_verifier_*.py` | `0 errors` |

---

## 2. Static Audit of Role A Immutable Remote Commit (`3b8befb0112cfe2d314ad65964762a3fb251e710` / `3ebb7db9a1043e58843b518af9381218d9f25af1`)

Role B inspected Role A's immutable remote commit via read-only Git object commands (`git diff --name-only` and `git show`) without reading Role A's live worktree or modifying Role A's branch. **8 concrete discrepancies** were identified (`evidence/v0.6/b_line/g2_overnight_p0_b/A_IMPL_STATIC_COMPARISON_RECEIPT.json`):

1. **`DISCREPANCY_A01` (Allowlist Scope Violation)**: Role A created `src/btc_quant_agent/strategy_research/__init__.py` outside `src/btc_quant_agent/strategy_research/r3_overnight/**`.
2. **`DISCREPANCY_A02` (Static Manifest Row Count Mismatch)**: Role A's `AUDIT_MANIFEST_INSPECTION_RECEIPT.json` reported `"reported_row_count": 2933280` instead of `2,934,720` in `data_manifest.json` (off by `1,440` minutes = 1 leap day).
3. **`DISCREPANCY_A03` (Stage 1 Fill Ack Overwrites Active Position With `max_hold_ms=0` & Resurrects Closed Positions)**: In `ledger.py` (`L280-L294`), `_stage_1_available_messages` at `t0 + 60s` overwrites `self.positions[fill.symbol]` (already created in `_stage_5_due_entries` at `t0`) with `Position(..., max_hold_ms=0)`. This resets `max_hold_ms` to `0` (causing `_stage_6_intraminute_protection` at `L614` to trigger `ExitReason.EXPIRY` after 2 minutes instead of 4h/12h and wiping out `t0` funding charges), and resurrects any position that already closed via same-minute SL/TP at `t0`.
4. **`DISCREPANCY_A04` (Shared `SignalGenerator` Corrupts `CLOSED_RETEST` State Across `04H` and `12H`)**: `ReplayEngine` (`L42`) uses a single `SignalGenerator` shared across all 8 candidates while `_active_breakouts` (`signals.py:L260`) is keyed by `(symbol, direction)` without `candidate.id`, causing `04H` and `12H` retest variants to mutate and consume each other's breakout state on the same hour.
5. **`DISCREPANCY_A05` (Retest Touch-Zone Inequality & Stop Extremum Omission)**: `signals.py` (`L295-L307`, `L323-L335`) checks range overlap rather than requiring `LONG low` (or `SHORT high`) to lie inside `[B - 0.25*ATR_b, B + 0.25*ATR_b]`, and omits `breakout_low` / `breakout_high` from `min(breakout.intermediate_lows)` / `max(breakout.intermediate_highs)`.
6. **`DISCREPANCY_A06` (Stage 2 Mark Update Ordering & Bar-Open Timestamp Age Check)**: `ledger.py` (`L147`, `L331-L341`) updates `last_available_marks` in Stage 2 rather than Stage 1 and records `mbar.timestamp_ms` (open) instead of `mbar.close_ms` (close) for the 120s mark staleness check.
7. **`DISCREPANCY_A07` (Cooldown Origin & Omitted 4h Dedup Args in `ReplayEngine`)**: `ledger.py` (`L309`) anchors cooldown to acknowledgment time (`open_time_ms + 4h`) instead of `ceil_to_minute(economic_exit_at) + 4h`, and `ReplayEngine.run_simulation` (`L129-L134`) never passes `last_exit_time_ms` or `last_entry_4h_time_ms` to `evaluate_hourly_decision`.
8. **`DISCREPANCY_A08` (Stage 5 Exit Commitment Missing `+ tick_size`)**: `ledger.py` (`L556-L559`) omits `+ sym_filter.tick_size * order.quantity` from `Position.cost_commitment_exit_usdt`.

Per Controller Dispatch `56f8a9faa1a4539124ab006b49bf42b6e7c997e3`, Role B leaves Role A's branch untouched and reports terminal status `P0_B_DISCREPANCY_BLOCKED`.
