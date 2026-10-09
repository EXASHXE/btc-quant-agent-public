# V06 G2 R3 P0 — Gemini A R2 Interaction Repair Controller Handoff

**TASK_ID:** `V06_G2_R3_P0_A_INTERACTION_REPAIR_R2`
**BRANCH:** `feature/v06-bline-g2-overnight-discovery-a`
**CONTROLLER_DISPATCH_SHA:** `218c126c9fd5395767fa27af984bf14b265c4a8f`
**START_SHA:** `5c542edd418a74b440162610fd540b1f01e423d3`
**B_FINDING_SOURCE_SHA:** `f1ec703b7c7276582f324ac25b9d1000f1b5ef14`
**TERMINAL_STATUS:** `R2_SYNTHETIC_REPAIR_READY_FOR_INDEPENDENT_B_REVIEW`

---

## 1. Executive Summary

This handoff packages the single consolidated synthetic engineering repair (R2) addressing all seven cross-stage interaction findings (B01–B07) identified during the Gemini B / Sol re-audit. All repairs strictly preserve the 8 original candidate specifications, horizons (04H/12H), risk limits, and fee schedules.

All 46 targeted regression and positive invariant tests pass on both **Python 3.12.3** and **Python 3.13.13** without warnings, Ruff linter violations, or whitespace defects.

---

## 2. Engineering Repair Architecture (B01–B07)

### B01: Causal Mark Price Stream Ingestion
- **Root Cause in R1:** `ReplayEngine` passed marks with timestamp at open $O$ to minute $O$, but Stage 1 required `close_ms <= O` and `available_at_ms <= O`. Consequently, marks were rejected, leaving `last_available_marks` empty.
- **R2 Resolution:** `ReplayEngine` indexes marks by **effective availability**: $\max(\text{close\_ms}, \text{available\_at\_ms}) \le \text{current\_open\_ms}$. Stage 1 admits eligible marks upon completed close and availability, enforces 120s staleness fail-close, rejects future bars, and ignores out-of-order stale arrivals.

### B02: Exactly-Once ACK Idempotency
- **Root Cause in R1:** Repeated delivery of fill ACKs debited cash multiple times, charged redundant fees, or created duplicate completed trades upon duplicate exit ACKs.
- **R2 Resolution:** Introduced tracking sets in `VirtualBook`: `acknowledged_fill_ids`, `acknowledged_exit_ids`, and `acknowledged_funding_ids`. Each economic event maps to exactly one cash, fee, funding, and commitment effect. Duplicate deliveries (2× or 3×) are silently ignored without state corruption or zombie revival.

### B03: Settlement Ownership Interval $[S - 15\,\text{s}, S + 15\,\text{s}]$
- **Root Cause in R1:** Strict inequality and Stage 6 deletion prior to Stage 7 funding evaluation dropped positions that exited intraminute at $S$ via Stop Loss, failing to charge funding.
- **R2 Resolution:** Implemented `ExposureInterval` tracking position economic occupancy. In Stage 7, overlap with $[S - 15000, S + 15000]$ is evaluated for active, exiting, and same-minute SL positions. When an exiting position is charged, its pending exit ACK is updated with the funding debit so cashflow and PnL reconcile precisely upon Stage 1 ACK consumption.

### B04: Deterministic Minute-End Exit Timestamps & Cooldown Anchoring
- **Root Cause in R1:** Intraminute SL/TP exits were stamped at bar open $O$, leaking full-minute OHLC results into the opening timestamp, resulting in `holding_minutes = 0`. Cooldown anchoring between ledger and signals drifted.
- **R2 Resolution:** Intraminute SL/TP exits are stamped at the deterministic minute-end effective timestamp `open_time_ms + 60_000 - 1`. `holding_minutes` is bounded by $\max(1, \dots)$. Cooldown checks in both `VirtualBook` and `SignalGenerator` anchor consistently to:
  $$\text{cooldown\_until\_ms} = \left\lfloor\frac{\text{exit\_time\_ms} + 59999}{60000}\right\rfloor \times 60000 + 4 \times 3600000$$

### B05: Available vs Economic Equity & Kill Reservation Integrity
- **Root Cause in R1:** `decision_equity` counted unrealized PnL of unacknowledged positions before fill ACK arrived. On drawdown kill, cost commitment and funding reserve were zeroed out while open positions remained live, driving reserves negative (-5.00) upon liquidation.
- **R2 Resolution:** `decision_equity` values only positions where `pos.is_acknowledged` is true. Drawdown kill cancels pending orders (releasing order commitments) but retains obligations for active positions. Commitments release exactly once upon liquidation exit ACK without negative drift.

### B06: Retest State Progression Across Intermediate Invalid Hours
- **Root Cause in R1:** `SignalGenerator.evaluate_hourly_decision` checked EMA/volatility filters before advancing breakout state. An intermediate hour failing a filter returned `None`, freezing `bars_since_breakout` at 0 and skipping time.
- **R2 Resolution:** Added `_advance_active_breakout` executed for all completed post-breakout hourly bars before any filter check. `bars_since_breakout` advances deterministically, intermediate highs/lows are recorded, and 3-hour expiry cancellation is enforced.

### B07: Exact Funding Reserve Conservation
- **Root Cause in R1:** VirtualBook debited position funding reserve in Stage 7 but did not debit aggregate `funding_reserve_rf`, leaking residual reserve after position close.
- **R2 Resolution:** Stage 7 debits funding from both `pos.funding_reserves_usdt` and aggregate `funding_reserve_rf` with exact Decimal equality. Upon position close ACK, remaining funding reserve is cleanly released, guaranteeing exactly 0 leaked funding reserve.

---

## 3. End-to-End Synthetic Simulation Verification

A real synthetic `ReplayEngine.run_simulation` test was constructed:
- Causal synthetic 1m trade and mark series (247 hours).
- Breakout detection on hour 240, retest confirmation on hour 241.
- Hourly signal generation at `decision_time + 60s`.
- Order sizing and placement at Stage 3, filled at Stage 5 (`decision + 120s`).
- Fill ACK consumed at Stage 1 (`fill + 60s`).
- Position held and exited via Take Profit (and verified separately via 240-minute 4h Expiry).
- Complete ledger reconciliation:
  - `cost_commitment_o = 0`
  - `funding_reserve_rf = 0`
  - `decision_equity = cash = 1005.369943120000`

---

## 4. Verification Evidence & Test Summary

| Metric | Python 3.12.3 | Python 3.13.13 | Result |
| :--- | :--- | :--- | :--- |
| **Total Tests Passed** | 46 / 46 | 46 / 46 | **PASS** |
| **R2 Positive Invariant Tests** | 11 / 11 | 11 / 11 | **PASS** |
| **R1 Regression Tests** | 7 / 7 | 7 / 7 | **PASS** |
| **Hermetic Fixture Tests** | 12 / 12 | 12 / 12 | **PASS** |
| **Ruff Linter Violations** | 0 | 0 | **PASS** |
| **Git Diff Whitespace Check** | Clean | Clean | **PASS** |

### Deterministic Book Receipt Hashes
- **BASE Scenario Hash:** `b53cd3089779f54da0d72dd404cae49c43bb8c9683bb304df4fcc20525ad85f9`
- **STRESS Scenario Hash:** `c476cece5fed6bac9f24511821f8925a6e7ce76933b8bc8177b8a808c1eb1ae7`

---

## 5. Scope & Boundary Certification

- **Allowed Paths Strictly Respected:** All changes confined to `src/btc_quant_agent/strategy_research/r3_overnight/**`, `tests/test_strategy_research_r3*.py`, `docs/.../repair_r2/**`, and `evidence/.../repair_r2/**`.
- **Zero Real Market Access:** `EMPIRICAL_PRICE_BODY_AUTHORITY=NONE`, `G4_TESTNET=NOT_AUTHORIZED`, `REAL_FUNDS_WRITE_AUTHORITY=NONE`, `AUTONOMOUS_LIVE=FORBIDDEN`.
- **Ready for Verifier Review:** The branch is ready for independent Gemini B / Sol re-audit.
