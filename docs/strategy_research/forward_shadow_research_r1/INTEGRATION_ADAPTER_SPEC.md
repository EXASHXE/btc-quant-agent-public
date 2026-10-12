# Public Feed Integration Adapter Contract: Specification R1

**Task ID:** `V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1`  
**Controller Dispatch SHA:** `e35724f1d1ee7458709e003dfc5673c826c68ffd`  
**Component:** `scripts.strategy_research.forward_shadow_research_r1.adapter.PublicFeedAdapter`

---

## 1. Architecture & Decoupling Mandate

Under B-line Controller Authority, Gemini Goal B operates concurrently with Gemini Goal A (Public Feed Collector) and Gemini Goal C (Offline Adapters). Direct cross-worktree imports or writes between Goal workspaces are prohibited. 

To ensure complete interoperability upon future Controller L2 integration without violating worktree isolation, Goal B implements an independent `PublicFeedAdapter` that parses and consumes standard `MarketEventV1` JSON streams adhering to the official Controller envelope specification.

---

## 2. Wire Contract: MarketEventV1

The adapter ingests newline-delimited JSON records satisfying schema version `market-event-v1`:

```json
{
  "schema_version": "market-event-v1",
  "symbol": "BTCUSDT",
  "product": "BINANCE_USDT_M_PERP",
  "channel": "last_kline_1m | mark_price | agg_trade | depth_delta | depth_snapshot | funding_settled | health",
  "provider_event_ms": 1776000000000,
  "provider_transaction_ms": 1776000000000,
  "observed_wall_utc_ms": 1776000000005,
  "observed_monotonic_ns": 1000000000,
  "available_at_ms": 1776000000005,
  "source_stream_id": "stream_channel_name",
  "connection_epoch": "epoch_uuid_or_counter",
  "source_sequence": 101,
  "payload_sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
  "payload": { ... },
  "quality": "VERIFIED | DEGRADED | UNKNOWN | INVALID",
  "reason_codes": [],
  "raw_source_manifest_sha256": "raw_segment_sha256",
  "book": { ... }
}
```

### Key Field Semantics

1. **`available_at_ms`:** Receiver ingress wall clock. Signals and features are unavailable until this timestamp, regardless of bar close or provider timestamp.
2. **`observed_monotonic_ns`:** Monotonic ingress ordering. Used to detect wall-clock backwards jumps.
3. **`payload_sha256`:** Deterministic SHA-256 digest of canonical UTF-8 JSON payload. Mismatches invalidate the event immediately.
4. **`book` (`BookIntegrityV1`):** Optional depth ledger containing top bids, asks, update IDs, continuity status, and staleness age.

---

## 3. Adapter Ingress Pipeline & Quality Checks

```
Incoming JSON Line
       │
       ▼
[JSON Parsing & Schema Validation] ───(Invalid Schema)───► Raise ValueError
       │
       ▼
[Payload SHA-256 Verification] ───────(Mismatch)─────────► Quality = INVALID
       │
       ▼
[Deduplication Check] ────────────────(Duplicate)────────► Drop & Increment Counter
       │
       ▼
[Monotonic vs Wall Clock Causality] ──(Wall Jump Back)───► Quality = INVALID
       │
       ▼
[Book Integrity & Staleness] ─────────(Stale >1s/Cross)──► Quality = DEGRADED/INVALID
       │
       ▼
[Channel Dispatch to Shadow Engine]
```

### 3.1 Deduplication
The deduplication key is computed as:
$$\text{DedupeKey} = \text{SHA256}(\text{Symbol} : \text{Channel} : \text{ConnectionEpoch} : \text{ProviderID/PayloadSHA})$$
Duplicate records are recorded in adapter statistics but excluded from feature computation.

### 3.2 Time-Alignment for 1m Bar Pairing
The adapter synchronises `last_kline_1m` and `mark_price` 1m bars by matching `bar_open_ms` and `bar_close_ms`. Only when both streams deliver completed bars for the same minute does the engine evaluate higher-timeframe features (5m, 15m, 30m, 1h).

### 3.3 Fail-Closed Rules
- If depth `stale_age_ms > 1000`, the book is degraded and shadow fills are suspended (`FILL_UNCERTAIN`).
- If `best_bid >= best_ask`, the book is marked crossed (`CROSSED_SPREAD`) and rejected.
- If mark price is older than 2000ms at ingress, it is marked `STALE_MARK_OVER_2000MS`.

---

## 4. Decoupled Integration Pattern

Downstream evaluators or future Controller L2 integration scripts can stream records to the engine using standard Python generators or file iterators:

```python
from scripts.strategy_research.forward_shadow_research_r1 import (
    PublicFeedAdapter,
    ShadowExecutionEngine,
    get_default_hypotheses,
)

# Select one of the 6 prespecified cells
hypothesis = get_default_hypotheses()["P1_BASIS_REVERSION_V2_SHADOW_6H"]
engine = ShadowExecutionEngine(hypothesis)
adapter = PublicFeedAdapter(engine)

# Ingest line-by-line from public feed event stream or file
with open("prospective_public_feed_events.jsonl") as f:
    for line in f:
        adapter.ingest_line(line)

# Finalize summary at end of evaluation stream
summary = engine.finalize_evaluation(stream_end_ms=current_timestamp)
print(f"Status: {summary.cell_id}, Closed Positions: {len(summary.closed_positions)}")
```
