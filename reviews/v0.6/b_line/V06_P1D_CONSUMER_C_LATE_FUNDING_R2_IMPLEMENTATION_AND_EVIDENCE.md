# Implementation and Evidence Record: P1D Consumer C Late-Funding PIT Contract Repair R2

- **DISPATCH_ID:** `V06_P1D_CONSUMER_C_LATE_FUNDING_PIT_R2`
- **DISPATCH_SHA:** `68def8fed3fd290ffbddf00a8f86e4184a8b036f`
- **FROZEN_BASELINE_SHA:** `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b`
- **WORKTREE / BRANCH:** `feature/v06-p1d-consumer-c-late-funding-pit-r2`
- **EXECUTOR:** Gemini BOOST
- **INDEPENDENT AUDITOR:** Codex Sol High independent financial/causal review
- **TERMINAL DECISION:** `PASS_CONSUMER_PIT_CONTRACT_PENDING_INTEGRATION` (G2 Alpha/TESTNET/LIVE remain NO_GO)

---

## 1. Observed Defect & Root Cause

### Defect
In Consumer C (`scripts/g1g3_offline_ports_r1/market_pit_port.py`), function `_translate_funding` enforced:
```python
if wall_ms < settlement_at or avail_ms != settlement_at:
    raise SafetyViolation("FUNDING_PIT_INVALID")
```
This conflated the envelope's receiver-known-at bound (`available_at_ms`) with the economic settlement time (`settlement_at_ms`), causing legitimate REST settlement records arriving seconds or minutes after the 8-hour economic funding boundary to be falsely rejected.

### Causality & Financial Contract Requirements
1. **Receiver Ingress Separation**: `available_at_ms` must represent the monotonic receiver known-at bound. It must NOT be backdated to the settlement timestamp.
2. **Economic Event Preservation**: The downstream economic event timestamp `g1_event["at"]` must preserve the immutable economic settlement clock (`settlement_at_ms`), guaranteeing that exposure and mark price correspond to the exact settlement moment, not the delayed receipt moment.
3. **Decision View Causal Guard**: Future funding records received late cannot retroactively alter earlier decision state. `validate_decision_pit` must fail closed for any decision timestamp prior to `max_feature_known_at_ms`.
4. **Idempotence and Conflict Defenses**: Duplicate replays of identical settlement records must be idempotently ignored (`g1_event=None`) to prevent double posting. Replays with conflicting rates, settlement clocks, or Mark prices must hard-fail immediately (`SafetyViolation("FUNDING_SETTLEMENT_CONFLICT")` / `SafetyViolation("FUNDING_SETTLEMENT_COLLISION")`).
5. **No False Realization**: Missing Mark prices or rates must evaluate to `COST_INCOMPLETE` with cash flow as `None`; never silently defaulted to zero. Zero rate funding requires complete witnessed coverage before realization.

---

## 2. Narrow Write Allowlist Audit

All modifications were strictly constrained to the 5 authorized paths in the dispatch:

1. `scripts/g1g3_offline_ports_r1/market_pit_port.py`
2. `tests/test_v06_g1g3_offline_ports_r1_core_integration.py`
3. `tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py`
4. `reviews/v0.6/b_line/V06_P1D_CONSUMER_C_LATE_FUNDING_R2_IMPLEMENTATION_AND_EVIDENCE.md`
5. `evidence/v0.6/b_line/p1d_consumer_c_late_funding_r2/SYNTHETIC_CASE_RECEIPT.json`

- **Generic G1 ledger/runtime**: UNTOUCHED.
- **Feed bridges A/B**: UNTOUCHED.
- **Source adapters**: UNTOUCHED.
- **Exchange order engines**: UNTOUCHED.
- **Cross-branch merges**: 0 (Clean isolated worktree from `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b`).

---

## 3. Implementation Summary

### `scripts/g1g3_offline_ports_r1/market_pit_port.py`
- Repaired `_translate_funding`:
  - Enforced `wall_ms >= settlement_at` and `avail_ms >= settlement_at`, permitting on-time and late REST arrivals while strictly rejecting receipt before settlement.
  - Added support for optional `mark_price` and `mark_close` payload fields with strict decimal validation.
  - Implemented journal tracking `seen_funding_settlements` and `seen_funding_clocks`.
  - Added duplicate replay detection returning `None` (resulting in `DUPLICATE_IGNORED` at the envelope level).
  - Added conflict detection for revised rates or Mark prices on the same `settlement_id`, raising `SafetyViolation("FUNDING_SETTLEMENT_CONFLICT")`.
  - Added collision detection for distinct settlement IDs on the same settlement timestamp, raising `SafetyViolation("FUNDING_SETTLEMENT_COLLISION")`.
- Enhanced `ingest_envelope`:
  - Added connection epoch regression guard (`CONNECTION_EPOCH_REGRESSION`).
  - Integrated duplicate funding handling (`DUPLICATE_IGNORED`, `g1_event: None`).
- Enhanced `make_synthetic_market_event_v1_from_g1_funding` and added `make_synthetic_funding_envelope` to allow arbitrary late receipt offsets, provider timestamps, and Mark witnesses in synthetic testing.
- Added pure financial helper functions:
  - `calculate_settled_funding_cash_flow`: Exact Decimal cash flow evaluation enforcing side symmetry, non-zero assumption, and complete witnessed coverage.
  - `compute_settlement_exposure`: Computes signed exposure strictly at settlement timestamp (`executed_at < settlement_at_ms`), failing closed on ambiguous boundaries (`executed_at == settlement_at_ms`).

---

## 4. Synthetic Acceptance Test Battery Evidence

| # | Acceptance Criterion | Test Location | Result | Invariant Verified |
|---|---|---|---|---|
| 1 | On-time settled funding | `test_market_pit_funding_on_time_settled` | **PASS** | `avail_ms == settlement_at_ms` accepted, emitted at economic settlement clock |
| 2 | 3-second & multi-minute late receipt | `test_market_pit_funding_3s_and_multi_minute_late_receipt_with_known_at` | **PASS** | REST receipt at T+3s and T+300s accepted with receiver known-at; economic event clock remains T |
| 3 | Unchanged earlier decision feature view | `test_market_pit_funding_unchanged_earlier_decision_feature_view` | **PASS** | Earlier decision at T valid before receipt; after late receipt at T+60s, earlier decision fails closed |
| 4 | Duplicate replay idempotence | `test_market_pit_funding_duplicate_replay_idempotence` | **PASS** | Exact and re-keyed duplicates return `DUPLICATE_IGNORED` with `g1_event=None`, no double-posting |
| 5 | Same settlement ID conflicting rate/Mark hard fail | `test_market_pit_funding_same_settlement_id_conflicting_rate_or_mark_hard_fail` | **PASS** | Conflicting rate or Mark raises `FUNDING_SETTLEMENT_CONFLICT` |
| 6 | Receipt-before-settlement reject | `test_market_pit_funding_receipt_before_settlement_rejected` | **PASS** | `wall_ms < settlement_at` or `avail_ms < settlement_at` raises `FUNDING_PIT_INVALID` |
| 7 | Missing Mark/rate => COST_INCOMPLETE | `test_market_pit_funding_missing_mark_or_rate_cost_incomplete` | **PASS** | Missing mark or rate returns `COST_INCOMPLETE` with `cash_flow=None`; never assumed 0.0 |
| 8 | Funding credit/debit side symmetry | `test_market_pit_funding_credit_debit_side_symmetry` | **PASS** | LONG pays positive rate, SHORT receives positive rate; exact sum to `Decimal(0)` |
| 9 | Exposure before vs after partial fill/settlement | `test_market_pit_funding_exposure_before_vs_after_partial_fill_and_settlement` | **PASS** | Partial fill before settlement reduces settlement exposure; partial fill after settlement does not alter settlement exposure |
| 10 | Ambiguous fill-vs-settlement boundary | `test_market_pit_funding_ambiguous_fill_vs_settlement_boundary` | **PASS** | Fill at exact settlement timestamp raises `AMBIGUOUS_SETTLEMENT_BOUNDARY` |
| 11 | Reconnect or clock-regression fail closed | `test_market_pit_funding_reconnect_and_clock_regression_fail_closed` | **PASS** | Monotonic, wall clock, and connection epoch regressions fail closed immediately |
| 12 | Zero-real-funding complete witnessed coverage | `test_market_pit_funding_zero_real_funding_complete_witnessed_coverage` | **PASS** | Rate 0.0 requires complete coverage; unverified/incomplete coverage yields `COST_INCOMPLETE` |

---

## 5. Verification Record & Test Suite Results

```text
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-8.4.2, pluggy-1.6.0
rootdir: /root/workspace/project/quant-v0.6/feature-v06-p1d-consumer-c-late-funding-pit-r2
configfile: pyproject.toml
plugins: anyio-4.12.1, langsmith-0.8.5, cov-7.1.0
collected 155 items

tests/test_v06_g1g3_offline_ports_r1_bounded_llm.py ........................... [ 17%]
tests/test_v06_g1g3_offline_ports_r1_core_integration.py ..................... [ 31%]
................                                                               [ 41%]
tests/test_v06_g1g3_offline_ports_r1_feishu_outbox.py ........................ [ 57%]
tests/test_v06_g1g3_offline_ports_r1_operator_auth.py ........................ [ 72%]
..........                                                                     [ 78%]
tests/test_v06_g1g3_offline_ports_r1_recovery_and_guards.py .................. [ 90%]
................                                                               [100%]

======================= 155 passed in 185.50s (0:03:05) ========================
```

- **Ruff linter**: 0 errors across all modified files.
- **Total tests**: 155 passed, 0 failed, 0 skipped.

---

## 6. Terminal Decision

`PASS_CONSUMER_PIT_CONTRACT_PENDING_INTEGRATION`

G2 Alpha / TESTNET / LIVE remain **NO_GO**.
