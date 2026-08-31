# Microstructure schema

## Partition model

Directory: `data/forward/BTCUSDT/microstructure/`

Each receive UTC date maps to `microstructure-YYYY-MM-DD.sqlite3` in SQLite WAL mode. High-frequency raw databases, WAL files, and shared-memory files are not committed. On graceful shutdown, every closed UTC partition is checkpointed and listed in `closed-partitions.sha256.json` with its SHA-256 digest.

## Tables

### `depth_events`

Primary key: `(event_time_ms, final_update_id)`.

Stores exchange event time, final update ID, local wall-clock receive time, local monotonic receive time, the canonical serialized `DepthEvent` payload, and its SHA-256 hash. The payload contains exchange `E`, optional `T`, `U`, `u`, `pu`, bids, asks, and both receive timestamps.

### `agg_trades`

Primary key: `aggregate_trade_id`.

Stores aggregate trade ID, exchange event/transaction times, local receive wall/monotonic times, price, quantity, buyer-is-maker flag, mechanically derived aggressive side, and payload hash.

### `book_samples`

Primary key: `(event_time_ms, final_update_id)`.

Stores causal post-update book statistics: spread bps, top-1/top-5/top-20 depth imbalance, microprice, and best-level event OFI. A sample is written only after a synchronized local book has applied the event.

### `aggregates`

Primary key: `(interval_ms, bucket_start_ms)` where `interval_ms` is exactly `1000`, `60000`, or `900000`.

Fields are trade count, aggressive buy/sell quantity, aggressive buy/sell notional, book sample count, sums for spread and top-N imbalance, OFI sum, and gap count. A closed bucket is complete only when it has both trade and synchronized book observations and `gap_count == 0`.

### `gaps`

Append-only audit rows with unique ID, start/end milliseconds, gap kind, and detail. Current disconnect/resync observations are point timestamps; no unavailable interval is fabricated as continuous data.

### `sessions`

Stores session ID, stream (`depth` or `trade`), start/end wall-clock milliseconds, and connected/closed state. Formal connected coverage is the minimum naturally observed coverage of the two required streams, so process uptime or one surviving socket cannot overstate campaign uptime.

### `audit_counters`

Persistent counters distinguish duplicate raw events from conflicting payloads with the same identity. Derived book-sample duplicates are also counted.

## Time semantics

Exchange event/transaction timestamps are never replaced by local receive time. Receive wall time selects the durable daily partition and supports latency measurement. Monotonic time is retained for within-process ordering and diagnostics. Aggregation buckets use exchange event time and never future prices or labels.

## Data role and safety

`FUTURE_RESEARCH_DATA` only. No Direction label, action, order, execution instruction, or final-holdout result is stored in this schema.
