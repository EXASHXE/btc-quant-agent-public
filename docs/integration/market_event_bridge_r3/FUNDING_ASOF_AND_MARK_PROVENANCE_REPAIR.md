# Funding Point-in-Time (PIT) Clock & Mark Price Provenance Repair

## 1. Defect Analysis: The R2 PIT Clock Backdating Vector

In Market Event Bridge R2, settled funding ingestion contained a critical point-in-time clock violation. Upstream C (`MarketPitPort._translate_funding`) enforces an immutable contract on funding events:
```python
if wall_ms < settlement_at or avail_ms != settlement_at:
    raise SafetyViolation("FUNDING_PIT_INVALID")
```
Because Binance REST settled funding records are queried and received *after* settlement time (e.g., received at 00:00:05 UTC for 00:00:00 UTC settlement), normal receiver arrival time has `avail_ms > settlement_at`. In R2, the author artificially backdated `observed_wall_utc_ms = entry.funding_time_ms` and `available_at_ms = entry.funding_time_ms` to force C's check to pass.

This backdating corrupted the causal timeline, creating a false illusion that late-arriving funding was known and available at exact settlement timestamp. Furthermore, Mark prices used to calculate realized cash flows were ingested as unvalidated scalar floats without verifying timestamp age, clock uncertainty, or routing provenance.

---

## 2. Engineering Repair Architecture

R3 resolves this architectural defect cleanly in [`scripts/integration/market_event_bridge_r2/funding_adapter.py`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/integration/market_event_bridge_r2/funding_adapter.py) and [`scripts/integration/market_event_bridge_r2/bridge_engine.py`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/integration/market_event_bridge_r2/bridge_engine.py).

### Real PIT Arrival Clock Preservation
The receiver arrival clock is strictly preserved:
- `observed_wall_utc_ms` is set to actual receiver wall clock time at ingestion.
- `available_at_ms` is set to actual arrival time.
- Backdating to `entry.funding_time_ms` is strictly prohibited.

### Fail-Closed C Consumer Handling
When normal late arrival occurs (`observed_wall_utc_ms > funding_time_ms`), dispatching to C's unmodified port triggers `SafetyViolation("FUNDING_PIT_INVALID")`.
The bridge wraps C port dispatch in a fail-closed exception handler:
```python
try:
    self.c_port.ingest_market_event(c_fund_env)
    self.stats.c_events_dispatched += 1
    result["emitted_to_c"] = True
    result["c_envelope"] = c_fund_env
except Exception as c_exc:
    result["emitted_to_c"] = False
    result["c_consumer_status"] = "C_CONSUMER_CONTRACT_BLOCKED"
    result["c_consumer_error"] = str(c_exc)
```
This preserves C's strict safety boundary without modifying C's upstream code and without compromising the bridge's true arrival clock.

### Certified `MarkPriceWitness` Provenance
Cash flow realization requires a certified [`MarkPriceWitness`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/integration/market_event_bridge_r2/funding_adapter.py):
- **Price Positivity**: `price > Decimal(0)` strictly enforced.
- **Freshness Bound**: Maximum staleness age `<= 60.0` seconds (`max_mark_staleness_ms = 60000`). If older than 60s, rejected with `STALE_MARK_PRICE`.
- **Clock Quality**: Must be `"VERIFIED"`. If `"CLOCK_UNCERTAIN"` is present, rejected immediately.
- **Routing Provenance**: Must match the current active `route_epoch` and `connection_epoch`. Cross-epoch mark ticks are rejected.
- **Fail-Closed Fallback**: If no valid mark witness is present, the ledger records `cash_realization_status = "CASH_INCOMPLETE"` and `calculate_cash_flow(...)` returns `None`.

### Exact 8-Decimal Cash Flow Conservation
Settled cash flows are computed using exact Python `Decimal` arithmetic:
$$\text{cash\_flow} = -1 \times \text{position\_size} \times \text{funding\_rate} \times \text{mark\_price}$$
- Rounded to exactly 8 decimal places using `ROUND_HALF_EVEN`.
- **Long Positions**: Pay positive rates (negative cash flow), receive negative rates (positive cash flow).
- **Short Positions**: Receive positive rates (positive cash flow), pay negative rates (negative cash flow).
- **Zero Positions**: Always yield `Decimal('0.00000000')`.
- **Conservation**: Opposing long and short positions of equal magnitude sum to exact zero (`0.00000000`).

---

## 3. Verification Summary

The suite in [`tests/test_v06_market_event_bridge_r2_funding_pit_provenance.py`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/tests/test_v06_market_event_bridge_r2_funding_pit_provenance.py) provides 33 tests verifying:
1. Real arrival time preservation across 100ms, 5s, and 3h delays.
2. C consumer contract rejection recording `c_consumer_status: "C_CONSUMER_CONTRACT_BLOCKED"`.
3. Negative rate battery verifying long receiving and short paying.
4. MarkPriceWitness freshness gating (59s accepted, 61s rejected).
5. Exact 8-decimal rounding conservation across random position sizes.
