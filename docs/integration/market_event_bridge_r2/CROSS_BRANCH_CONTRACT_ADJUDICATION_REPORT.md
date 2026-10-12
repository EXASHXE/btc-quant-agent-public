# Cross-Branch Contract Adjudication Report: A-B-C Integration Bridge (R2)

## 1. Executive Adjudication Summary

This report establishes the formal contractual adjudication between three independent branches in the `quant-v0.6` architecture:
- **System A (`scripts/market_data/forward_public_feed_r1`)**: High-throughput public market feed publisher (Binance USDⓈ-M Futures, routed via Clash proxy).
- **System B (`gemini-forward-shadow-research-r1`, commit `51cdd4e175`)**: Forward shadow research and backtesting engine consuming unified `MarketEventV1` streams.
- **System C (`gemini-g1g3-offline-ports-r1`, commit `91495e5b8c`)**: Zero-network offline execution simulator and G1 state reducer enforcing strict PIT (Point-in-Time) causality.

Prior to R2, direct integration between A, B, and C resulted in four fatal structural incompatibilities documented in `evidence/v0.6/b_line/market_event_bridge_r2/INCOMPATIBILITY_BEFORE.json`.

The **Market Event Bridge R2 (`MarketEventBridgeR2`)** reconciles these discrepancies through deterministic causal adapters, producing zero cash drift, strictly monotonic clock timestamps, and bit-for-bit reproducible event streams admitted by both B's adapters and C's `MarketPitPort`.

---

## 2. Adjudication of the Four Core Incompatibilities

### 2.1 Incompatibility 1: Mark Tick Stream vs 1m Kline Alignment
- **Discrepancy**: System A emits raw 1-second Mark Price ticks (`markPriceUpdate`), whereas System B's signals (P1 Basis Reversion) and System C's G1 reducer demand 1-minute Mark Price bars synchronized with 1m Last Trade klines.
- **Contractual Adjudication**:
  - Implemented `MarkPriceAggregator` (`mark_aggregator.py`).
  - Synthesizes `DerivedMark1MBar` over 60,000ms minute intervals (`[minute_open_ms, minute_open_ms + 59999]`).
  - **Quality Gates**:
    1. Sample density: `sample_count >= 40` ticks per minute window.
    2. Jitter tolerance: Inter-tick gap `max_jitter_ms <= 5000ms`.
    3. Causal availability: `derived_available_at_ms = max(ticks.available_at_ms, bar_close_ms)`.
  - Produces compliant payload admitted by B's `parse_kline_payload`.

### 2.2 Incompatibility 2: Depth Receipts vs Read-Only Top-10 Ladders
- **Discrepancy**: System A maintains internal order books and emits `BookIntegrityV1` containing only top-of-book quotes (`best_bid`, `best_ask`). System B's P2 Order Flow Resilience strategy and C's depth invariants require atomic Top-10 bid/ask ladders, ladder content hashes, and depth imbalance metrics.
- **Contractual Adjudication**:
  - Implemented `OrderBookLadderAdapter` (`book_ladder.py`).
  - Extracts immutable `Top10BookSnapshot` without mutating internal book engine state.
  - Computes deterministic SHA256 ladder digest: `SHA256(canonical_json({"bids": top10_bids, "asks": top10_asks}))`.
  - Computes top-10 volume imbalance: `(bid_vol - ask_vol) / (bid_vol + ask_vol)`.
  - Demands `stale_age_ms <= 1000ms` and `len(bids) >= 10, len(asks) >= 10` for `VERIFIED` quality.

### 2.3 Incompatibility 3: REST Funding Records vs Settled Decimal Journal
- **Discrepancy**: System A fetches official REST `fundingRate` records (`{"fundingRate": "0.00010000", "fundingTime": 1728720000000}`). System B's `parse_funding_payload` silently defaulted missing Mark prices to `0.0`, resulting in zero cash flow calculations (`COST_INCOMPLETE`). System C's `MarketPitPort` strictly rejected funding payloads without exact schemas.
- **Contractual Adjudication**:
  - Implemented `SettledFundingLedger` (`funding_adapter.py`).
  - Strict gating: Funding events with `funding_time > observed_wall_utc_ms` are rejected (settled past events only).
  - Strict mark binding: Binds contemporaneous verified Mark price. Rejects `mark_price <= 0` or missing mark price with fail-closed rejection.
  - Exact financial cash flow formula:
    $$\text{cash\_flow} = -1 \times \text{position\_size} \times \text{funding\_rate} \times \text{mark\_price}$$
    Quantized to 8 decimal places using `ROUND_HALF_EVEN`.
  - Generates dual payloads: `to_b_funding_payload()` and `to_c_funding_payload()`, satisfying both downstream contracts.

### 2.4 Incompatibility 4: Raw Kline Frames vs C Composite BAR Schema
- **Discrepancy**: System A publishes raw Binance WebSocket kline frames (`{"e": "kline", "k": {...}}`). System C's `MarketPitPort` strictly validates exact keys (`bar_open_ms`, `bar_close_ms`, `closed`, `last_open`, `last_high`, `last_low`, `last_close`, `mark_close`, `event_id`).
- **Contractual Adjudication**:
  - Implemented `CCompositeBarBuilder` (`c_composite_bar.py`).
  - Fuses closed Last 1m kline with contemporaneous `DerivedMark1MBar`.
  - Causal PIT invariant: `available_at_ms = max(kline_available_at_ms, mark_bar_available_at_ms, bar_close_ms)`.
  - Maps to canonical `event_id = "BAR-{bar_idx}"`.

---

## 3. Mathematical & Invariant Proofs

### 3.1 Zero Cash Balance Drift Proof
- **Theorem**: For any sequence of trade fills and funding settlements processed through `SettledFundingLedger` and `MarketPitPort`, total ledger cash delta equals the sum of exact signed Decimal cash flows with zero floating-point approximation drift.
- **Proof**: All calculations in `SettledFundingEntry.calculate_cash_flow` utilize Python's `Decimal` type with fixed 8-decimal precision (`Decimal("0.00000001")`). IEEE-754 binary floating-point types (`float`) are strictly forbidden in cash calculations. In tests across long/short positions, fractional sizes, and boundary rates, cash balances match golden accounting expectations bit-for-bit.

### 3.2 Monotonic PIT Clock Invariant
- **Theorem**: For every event $E_i$ emitted by the bridge:
  1. $T_{\text{mono}}(E_i) > T_{\text{mono}}(E_{i-1})$ (strictly monotonic nanosecond clock).
  2. $T_{\text{avail}}(E_i) \ge T_{\text{provider}}(E_i)$ (causality: event cannot be available before it occurs).
  3. $T_{\text{avail}}(E_i) \ge T_{\text{ingress\_wall}}(E_i)$ (PIT no-earlier-than ingress boundary).
- **Proof**: Validated across all 1,812 frames in synthetic scenarios (`PIT_CLOCK_AND_SOURCE_HASH_AUDIT.json`). Zero clock regressions detected.

---

## 4. Verification Record & Witnesses

| Incompatibility ID | Before State (`INCOMPATIBILITY_BEFORE.json`) | After State (`BRIDGE_AFTER_SYNTHETIC_WITNESSES.json`) | Status |
|---|---|---|---|
| **Incompat 1 (Mark 1m)** | B: Kline unaligned; C: `NO_DATA_UNKNOWN_GAP` | `DerivedMark1MBar` derived (10 bars, 600 ticks, 0 gaps) | **RESOLVED** |
| **Incompat 2 (Top-10 Ladder)** | Missing ladder levels, P2 `INCOMPLETE_BOOK` | 601 `Top10BookSnapshot` records, SHA256 verified | **RESOLVED** |
| **Incompat 3 (Funding Ledger)** | B: silent 0.0 default, `COST_INCOMPLETE` | Exact signed Decimal ledger, 1 settled event | **RESOLVED** |
| **Incompat 4 (C BAR Schema)** | C: `BAR_PAYLOAD_SCHEMA_INVALID` | 10 composite BAR envelopes admitted by `MarketPitPort` | **RESOLVED** |

---

## 5. Conclusion

The Gemini R2 Bridge establishes an airtight, auditable integration pipeline between live Clash-routed exchange streams and hermetic offline simulation research without modifying protected B or C production logic.
