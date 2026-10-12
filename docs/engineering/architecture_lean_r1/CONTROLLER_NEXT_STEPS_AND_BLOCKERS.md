# Controller Next Steps and Blockers Report

**Task Mode**: Gemini BOOST Convergent Execution  
**Worktree**: `/root/workspace/project/quant-v0.6/gemini-boost-architecture-lean-r1`  
**Base Commit**: `97f4040b9380f2069575a989c066d1daeef15194`  
**Current HEAD**: Branch `feature/v06-bline-gemini-boost-architecture-lean-test-r1`

---

## 1. Upstream Consumer C Contract Blocker (`C_CONSUMER_REQUIRES_NEW_AUTHORITY`)

### Blocker Description:
Consumer C (`MarketPitPort._translate_funding` in pinned upstream commit `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b`) strictly enforces:
```python
if avail_ms != settlement_at:
    raise SafetyViolation("FUNDING_PIT_INVALID")
```
### Impact on Production Reality:
- In real-world market operations, official funding records are published via REST endpoints with a latency of 100ms–2000ms after the scheduled funding settlement boundary $T$ (e.g., 00:00:00 UTC).
- Therefore, `available_at_ms = receipt_time > settlement_at` is normal and physically unavoidable for REST feeds.
- Under Consumer C's current pinned contract, any funding event received with `available_at_ms > settlement_at` causes `SafetyViolation("FUNDING_PIT_INVALID")`.
- In our bridge implementation (`bridge_engine.py`), this contract violation is caught gracefully and isolated with `result["c_consumer_status"] = "C_CONSUMER_CONTRACT_BLOCKED"`, ensuring zero pipeline crash.

### Action Required by Controller:
Consumer C's code is outside the permitted writable scope. The controller must either:
1. Issue a revised upstream commit for Consumer C that allows `available_at_ms >= settlement_at` when accompanied by a verified settlement mark or valid provenance witness.
2. Provide a specialized bridge adapter port for Consumer C that stamps `available_at_ms = settlement_at` ONLY if an explicit authority flag is granted.

---

## 2. CI Suite Runtime Partitioning Recommendations

Based on the audit recorded in `evidence/v0.6/b_line/architecture_lean_r1/TEST_COVERAGE_OWNERSHIP_MATRIX.json`:
- **Repository Total**: 3,456 tests across 436 Python files.
- **Scientific / Protected Tests**: 1,547 tests (H40, H41, Holdouts) with strict non-touch rules.
- **Feed / Bridge Invariant Suite**: 450 tests (focused suite) running in ~10.45s on Python 3.12/3.13.

### Recommended CI Matrix:
To avoid running 3,456 tests linearly in single runners:
1. **Job 1: Fast Invariant Check (`focused-feed-bridge`)**:
   Runs `tests/test_v06_market_event_bridge_r2*.py`, `tests/test_v06_forward_public_feed_r1*.py`, and `tests/test_v06_architecture_lean_r1*.py`. Execution wall-time: ~10.5s.
2. **Job 2: Scientific Models & Portfolios (`scientific-h40-h41`)**:
   Runs `tests/h40/` and `tests/h41/` in isolation.
3. **Job 3: General System / Regression**:
   Runs remaining tests with dependency isolation.

---

## 3. Order Book L2 Snapshot Buffering & Re-Bootstrap Lineage

### Observation:
When a WebSocket connection drops or a sequence gap is detected (`GAP_SNAPSHOT_TO_STREAM`), `OrderBookIntegrityEngine` immediately resets state and transitions to `needs_rebootstrap = True`.
- During re-bootstrap, deltas are buffered in memory until the fresh snapshot arrives.
- While this guarantees 100% causal integrity and prevents crossed books, if a network outage persists for minutes, memory growth from buffered deltas could occur if unbounded.

### Action Recommended:
In subsequent controller waves, configure an explicit buffer capacity limit (e.g., maximum 5,000 buffered deltas or 60 seconds of buffer age), dropping old buffered deltas if the snapshot is delayed beyond a defined threshold.

---

## 4. Promotion of Canonical Market Event Envelopes

### Recommendation:
The `build_market_event_envelope` factory introduced in `contracts.py` should be promoted to the primary event constructor across the entire `btc_quant_agent` repository. This will:
1. Standardize envelope generation across all downstream agents and bridges.
2. Ensure consistent payload SHA-256 computation and schema compliance (`market-event-v1`).
3. Prevent future code duplication in newer exchange connectors.
