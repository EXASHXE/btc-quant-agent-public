# Wave 1 / Task C — Venue-Native Data Schema and Capacity Model Architecture Report R1

**TASK_ID:** `V06_DATA_C_STORAGE`  
**Execution Mode / Role:** Gemini NORMAL Local Session (Data Architecture Engineer)  
**Contract Date:** 2026-10-16 (UTC+08)  
**Reviewers:** ChatGPT-0 Primary Controller, ChatGPT-1 Independent Auditor, (optional Codex for timestamp/contract-unit semantics)  
**Task Branch:** `docs/v06-data-c-storage-schema-plan-r1`  
**Target File (ADD ONLY):** `docs/project/V06_DATA_C_VENUE_STORAGE_SCHEMA_AND_CAPACITY_MODEL_R1.md`  
**Terminal Disposition:** `C_DESIGN_READY_WITH_LIMITS`  

---

## 1. Document Identification, Immutable Authority & Contract Invariants

### 1.1 Dispatch and Provenance Authority
- **Immutable Controller Dispatch SHA:** `ade4df19872122686432cd955d8f139f16069449`  
  *Commit Message:* `docs(v0.6): plan Binance OKX BTC ETH parallel data program and immutable A-H dispatch`
- **Direct Dispatch Parent SHA:** `4d83123243db8cf5ac4fd7b1c00608cb149f7bdc`  
- **Dispatch Prompt Path:** `prompts/v0.6/b_line/data_program/V06_DATA_C_STORAGE_ARCHITECTURE_GEMINI_R1.md`  
- **Dispatch Prompt Blob SHA:** `7971ec5c33233a82ffd97433fdc82c0e1d86483f`  
- **Co-Committed Multi-Venue Data Program Plan:** `docs/project/V06_MULTI_VENUE_DATA_PROGRAM_AND_STORAGE_PLAN_R1.md` (Commit `ade4df19872122686432cd955d8f139f16069449`)  
- **Co-Committed Parallel Task DAG and Queue:** `docs/project/V06_PARALLEL_TASK_DAG_AND_EXECUTION_QUEUE_R1.md` (Commit `ade4df19872122686432cd955d8f139f16069449`)  
- **Co-Committed Primary Controller Role Charter:** `docs/roles/V0.6_CHATGPT_0_PRIMARY_CONTROLLER.md` (Commit `ade4df19872122686432cd955d8f139f16069449`)

### 1.2 Execution Mandates and Boundary Constraints
1. **Planning and Architecture Only ($0 Budget):** Total authorized financial expenditure is exactly **USD 0.00**. No paid APIs, cloud services, commercial data subscriptions, or compute resources were purchased or provisioned.
2. **Zero Source Payload Downloads:** Exactly **0 bytes** of external archive files, ZIP payloads, CSV extracts, or API stream records were downloaded or requested during this task.
3. **Zero Private Local Scans:** No directory traversal, metadata stat, or inventory scanning was performed against owner confidential or protected directories (including `Quant-agent/data`, `Quant-agent-sanitized`, H39/H40/H41, Forward, Final, or unexposed holdout partitions).
4. **Historical Inventory Status:** Previously reported baseline figures (~172.33 GiB used, ~724 GiB free on ~1 TiB filesystem, 61-month aggTrades) are treated strictly as **unverified historical observations**. They are not taken as verified physical ground truth or current capacity guarantees.
5. **Zero Executable Code Modifications:** No changes were made to executable `v0.6` strategy engines, trading pipelines, backtesters, or live execution code. This task delivers exclusively one isolated documentation artifact.
6. **No Self-Activation of Downstream Work:** Tasks D, E, F, G, and H remain `PREPARED_CONDITIONAL` and `NOT_AUTHORIZED_TO_EXECUTE`.

---

## 2. Versioned Multi-Venue Manifest and Source Partition Schema

### 2.1 Partition Key and Indexing Hierarchy
To enforce strict determinism and eliminate ambiguity across disparate exchanges and product classes, all ingested and processed market data must be uniquely indexed by a 5-tuple logical partition key:
$$\text{Partition Key} = \langle \text{venue}, \text{product\_type}, \text{instrument\_id}, \text{family}, \text{UTC\_partition} \rangle$$

The allowed domain values for each component in Wave 1 are defined as:
- **`venue` $\in \{\text{BINANCE}, \text{OKX}\}$**: Authoritative exchange venue.
- **`product_type` $\in \{\text{SPOT}, \text{USDT\_MARGINED\_PERP}\}$**:
  - `SPOT`: Physical asset delivery, quote currency cash settlement, zero funding, zero open interest.
  - `USDT_MARGINED_PERP`: Linear perpetual swap margined and settled in USDT (Binance UM Perpetual, OKX USDT-SWAP).
- **`instrument_id` $\in \{\text{BTCUSDT}, \text{ETHUSDT}, \text{BTC-USDT}, \text{ETH-USDT}, \text{BTC-USDT-SWAP}, \text{ETH-USDT-SWAP}\}$**:
  - Binance Spot: `BTCUSDT`, `ETHUSDT`
  - Binance USD-M Perp: `BTCUSDT`, `ETHUSDT`
  - OKX Spot: `BTC-USDT`, `ETH-USDT`
  - OKX USDT Swap: `BTC-USDT-SWAP`, `ETH-USDT-SWAP`
- **`family` $\in \{\text{Tier A Core}, \text{Tier B Trades}, \text{Tier C L2}\}$**:
  - Tier A Core: `KLINES_1M`, `MARK_PRICE_KLINES_1M`, `INDEX_PRICE_KLINES_1M`, `PREMIUM_INDEX_KLINES_1M`, `FUNDING_RATE`, `METRICS_OI_5M`
  - Tier B Trades: `TRADES_RAW`, `AGG_TRADES`
  - Tier C L2: `L2_ORDERBOOK_DEPTH_SNAPSHOT`, `L2_ORDERBOOK_DIFF_STREAM`
- **`UTC_partition`**: Standardized ISO 8601 temporal partition string:
  - Daily partition: `YYYY-MM-DD` (covers `[YYYY-MM-DDT00:00:00.000000Z, YYYY-MM-DDT23:59:59.999999Z]`)
  - Monthly partition: `YYYY-MM` (covers first second of month to last second of month UTC)

### 2.2 Controlled Enums and Classifications
- **`source_availability_class`**:
  - `AVAILABLE_VERIFIED`: Partition existence, official URL, and publisher checksum verified against official repository/index.
  - `AVAILABLE_UNMEASURED`: Known to exist in publisher documentation/portal, but physical bytes, row counts, and checksums unmeasured in local environment.
  - `COVERAGE_UNKNOWN`: Historical reachability, date continuity, or archive availability unverified.
  - `NOT_PUBLISHED`: Confirmed not offered or generated by the venue for the specified period.
  - `RIGHTS_UNRESOLVED`: Publicly visible, but legal terms, licensing tier, or redistribution constraints unverified.
  - `PIT_UNKNOWN`: File exists, but contemporaneous arrival time or historical publication timeline unverified.
  - `SOURCE_NOT_ADMITTED`: Gated by scientific or compliance rules; barred from ingestion.
- **`exposure_class`**:
  - `EXPOSED_DEV`: Historical time interval previously accessed during development or exploratory research; permitted for non-scoring data engineering QA and parser benchmarking; permanently disqualified from clean holdout or out-of-sample (OOS) validation.
  - `PROTECTED_RESERVED`: Clean holdout, blind test, or prospective validation interval; quarantined from ad-hoc analysis, feature engineering, and model calibration.

### 2.3 Comprehensive Data Manifest Schema
Every partition in the storage lake must have exactly one corresponding record in the manifest ledger (`catalog/manifest.duckdb` or `catalog/manifest.parquet`):

| Column Name | Logical Type | Nullable | Invariant / Validation Rule | Description |
|---|---|---|---|---|
| `partition_id` | `VARCHAR(128)` | No | Primary Key: `{venue}_{product_type}_{instrument_id}_{family}_{UTC_partition}` | Unique canonical partition identifier |
| `venue` | `VARCHAR(16)` | No | Enum: `'BINANCE'`, `'OKX'` | Source trading exchange |
| `product_type` | `VARCHAR(32)` | No | Enum: `'SPOT'`, `'USDT_MARGINED_PERP'` | Economic contract class |
| `instrument_id` | `VARCHAR(32)` | No | Must match venue-native symbology | Canonical instrument identifier |
| `family` | `VARCHAR(32)` | No | Must belong to defined Tier A/B/C families | Data stream family |
| `utc_partition` | `VARCHAR(10)` | No | Matches `^\d{4}-\d{2}(-\d{2})?$` | Temporal partition boundary |
| `partition_start_utc` | `TIMESTAMP_NTZ` | No | Partition start boundary in UTC | Exact microsecond timestamp of interval start |
| `partition_end_utc` | `TIMESTAMP_NTZ` | No | `partition_end_utc > partition_start_utc` | Exact microsecond timestamp of interval end |
| `source_uri` | `VARCHAR(512)` | No | Valid URI scheme (`https://...` or `s3://...`) | Official publisher download URL |
| `source_type` | `VARCHAR(32)` | No | Enum: `'OFFICIAL_ARCHIVE'`, `'REST_BATCH'`, `'WS_JOURNAL'` | Intake ingestion mechanism |
| `publisher` | `VARCHAR(64)` | No | e.g. `'BINANCE_PUBLIC_DATA'`, `'OKX_HISTORICAL'` | Authoritative publishing entity |
| `historical_rights_tier` | `VARCHAR(64)` | No | e.g. `'VISION_TERMS_V1.0_NONCOMMERCIAL_RESEARCH'` | Applicable license and usage rights charter |
| `publisher_checksum_algo`| `VARCHAR(16)` | Yes | Allowed: `'SHA256'`, `'MD5'`, NULL if absent | Official publisher digest algorithm |
| `publisher_checksum_hex` | `VARCHAR(64)` | Yes | 64-char hex string (SHA256) | Official publisher hash digest |
| `local_checksum_hex` | `VARCHAR(64)` | Yes | Computed SHA256 of downloaded payload | Local verification hash |
| `checksum_verified` | `BOOLEAN` | No | True if `local_checksum_hex == publisher_checksum_hex` | Checksum verification gate |
| `archive_vintage_utc` | `TIMESTAMP_NTZ` | Yes | Last-Modified or release timestamp from publisher | Time publisher released the archive object |
| `transform_vintage_utc`| `TIMESTAMP_NTZ` | Yes | Local execution timestamp of Parquet transform | Pipeline execution timestamp |
| `publish_at_utc` | `TIMESTAMP_NTZ` | Yes | Documented official availability time | Retrospective batch release timestamp |
| `receiver_known_at_utc` | `TIMESTAMP_NTZ` | Yes | Earliest verified receiver timestamp | Contemporaneous observation timestamp |
| `event_time_unit` | `VARCHAR(16)` | No | Enum: `'MILLISECOND'`, `'MICROSECOND'`, `'NANOSECOND'` | Raw timestamp granularity |
| `period_time_unit` | `VARCHAR(16)` | Yes | Enum: `'1M'`, `'5M'`, `'8H'`, NULL for ticks | Temporal aggregation bar interval |
| `source_availability_class`| `VARCHAR(32)`| No | Controlled enum (§2.2) | Physical & evidentiary availability status |
| `exposure_class` | `VARCHAR(32)` | No | Controlled enum: `'EXPOSED_DEV'`, `'PROTECTED_RESERVED'` | Machine learning data split boundary |
| `completeness_flag` | `VARCHAR(32)` | No | Enum: `'VERIFIED_COMPLETE'`, `'GAP_DETECTED'`, `'UNMEASURED'`| Data continuity and gap status |
| `duplicate_flag` | `VARCHAR(32)` | No | Enum: `'UNIQUE'`, `'DUPLICATES_REMOVED'`, `'COLLISION_DETECTED'`| Row deduplication audit result |
| `row_count` | `BIGINT` | Yes | Non-negative integer; NULL until measured | Total valid events/bars in partition |
| `compressed_bytes` | `BIGINT` | Yes | Bytes; NULL until measured | Size of raw downloaded archive |
| `expanded_bytes` | `BIGINT` | Yes | Bytes; NULL until measured | Size of uncompressed raw CSV/text |
| `parquet_zstd_bytes` | `BIGINT` | Yes | Bytes; NULL until measured | Size of finalized columnar Parquet file |
| `compression_ratio` | `FLOAT` | Yes | `expanded_bytes / parquet_zstd_bytes` | Parquet space reduction factor |
| `schema_version` | `VARCHAR(16)` | No | Semantic versioning: `'v1.0.0'` | Table column and type schema vintage |
| `storage_rel_path` | `VARCHAR(256)` | Yes | Relative path within authorized workspace root | Physical location on local filesystem |

---

## 3. Venue-Native Semantics, Contract Specifications, and Causal Clock Integrity

### 3.1 Event Identity and Trade Uniqueness
- **Binance Trade & AggTrade Semantics:**
  - Raw Trades (`trades`): Monotonically increasing 64-bit integer `trade_id`. Represents single fills against passive maker orders.
  - AggTrades (`aggTrades`): Monotonically increasing 64-bit integer `agg_trade_id`. Groups all fills executed against a single aggressive order arriving at identical price and microsecond/millisecond.
  - **Non-Conflation Invariant:** Raw Trades and AggTrades represent distinct levels of execution aggregation. Merging, unioning, or summing their volumes within the same calculation results in 100% volume inflation and false liquidity estimation.
- **OKX Trade Semantics:**
  - Raw Trades: Unique string/int `tradeId`. OKX does not publish native pre-aggregated `aggTrades` in historical portal archives; trades reflect native transaction logs.
- **Composite Primary Key:** To prevent key collisions across venues and products, all event-level databases must index records by:
  $$\text{PK}_{\text{event}} = \langle \text{venue}, \text{product\_type}, \text{instrument\_id}, \text{native\_trade\_id} \rangle$$

### 3.2 Spot versus USDT-Margined Perpetual Mechanics
| Feature Dimension | Spot Market (`SPOT`) | USDT-Margined Perp (`USDT_MARGINED_PERP`) |
|---|---|---|
| **Underlying Collateral** | Physical Base Asset (BTC, ETH) | Synthetic USDT Stablecoin |
| **Settlement** | Immediate physical delivery | Periodic cash settlement against Index Price |
| **Funding Cash Flows** | None ($0.00$) | Periodic payments: $F = \text{Position Value} \times \text{Funding Rate}$ |
| **Mark Price** | Not applicable (Last traded price) | Median calculation: Index Price + Basis Moving Average |
| **Open Interest (OI)** | Economically non-existent ($0$) | Net outstanding active open contracts |
| **Liquidation Engine** | None | Triggered when Margin Ratio $\le$ Maintenance Margin |

### 3.3 Instrument Base Units, Contract Multipliers, and Metadata Revisions
- **Binance Base Units:**
  - Binance Spot `BTCUSDT`: Quantity denominated in **BTC** (decimal float, step size 0.00001 BTC).
  - Binance USD-M `BTCUSDT`: Quantity denominated in **BTC** (decimal float, step size 0.001 BTC). 1 contract = 1 BTC equivalent.
  - Binance Spot `ETHUSDT` / USD-M `ETHUSDT`: Quantity denominated in **ETH**.
- **OKX Contract Multiplier Asymmetry (Critical Hazard):**
  - OKX Spot `BTC-USDT`: Quantity denominated in **BTC** (base coin).
  - OKX USDT-SWAP `BTC-USDT-SWAP`: Quantity denominated in **Contracts**.
    $$\mathbf{1\text{ Contract}} = \mathbf{0.01\text{ BTC}}$$
  - OKX USDT-SWAP `ETH-USDT-SWAP`: Quantity denominated in **Contracts**.
    $$\mathbf{1\text{ Contract}} = \mathbf{0.1\text{ ETH}}$$
  - **Invariance Rule:** Ingesting OKX Swap volume or open interest without scaling by the authoritative `contract_val` ($0.01$ for BTC, $0.1$ for ETH) produces an immediate $10\times$ to $100\times$ distortion of turnover, order book depth, and market share.
- **Instrument Metadata Registry:** Contract specifications undergo exchange adjustments. The storage catalog must maintain a versioned `instrument_metadata_v1` table tracking `[instrument_id, valid_from_utc, valid_to_utc, contract_val, contract_val_currency, min_size, tick_size, lot_size]`.

### 3.4 Mark Price, Index Price, and Funding Rate Semantics
- **Binance USD-M Perpetual:**
  - Funding rate settled every **8 hours** at `00:00:00`, `08:00:00`, and `16:00:00` UTC.
  - Premium Index computed from Mark Price, Index Price, and Funding basis.
  - Daily archives provide `markPriceKlines`, `indexPriceKlines`, and `premiumIndexKlines` (or `premiumPriceKlines` in helper scripts).
- **OKX USDT-SWAP:**
  - Funding settlement interval: Standard **8 hours** (selected high-volatility altcoins operate on 4h or 2h; BTC/ETH swaps operate on standard 8h cycles).
  - Funding Rate historical portal tables record `fundingTime`, `fundingRate`, and `realizedRate`.
  - Mark Price derived from composite multi-exchange spot index.

### 3.5 Open Interest (OI) Semantics and Representation
- **Binance USD-M Metrics:**
  - File: `data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{date}.zip`
  - `sum_open_interest`: Base asset units (BTC / ETH).
  - `sum_open_interest_value`: Notional USDT value ($\sum \text{OI} \times \text{Mark Price}$).
- **OKX Open Interest:**
  - Endpoint/Portal: `oi` (raw contract count), `oiCcy` (coin equivalent: $\text{oi} \times \text{multiplier}$), `oiUsd` (notional USD value).
- **Cross-Venue Conflation Hazard:** Under no circumstances may OKX OI contract numbers be aggregated with Binance OI numbers without converting both to base currency equivalent ($Q_{\text{coin}}$) or USD notional.

### 3.6 Time-Label Semantics, Lookahead Hazards, and Causal Clocks
- **Closed-Bar Lookahead Boundary (1m and 5m Klines):**
  - A 1-minute kline covering `[08:00:00Z, 08:01:00Z)` is stamped with `open_time = 08:00:00.000Z` and `close_time = 08:00:59.999Z`.
  - **Strict Causal Invariant:** No trading decision, signal computation, or state transition at clock time $T = \text{08:00:00Z}$ may observe the bar's `close`, `high`, `low`, or `volume`. The earliest time this bar becomes causally observable to a live receiver is:
    $$T_{\text{eligible}} \ge \text{close\_time} + \Delta_{\text{network\_delivery}} \ge \text{08:01:00.050Z}$$
- **Binance USD-M 5m Metrics `create_time` Transition Hazard (Upstream Issue #491):**
  - Unadjudicated third-party reports allege that prior to **2026-06-25 00:00 UTC**, 5m metrics stock variables (`sum_open_interest`) labeled $T$ represented a snapshot taken at $T$, whereas flow metrics (`sum_taker_long_short_vol_ratio`) covered $[T-5\text{m}, T)$.
  - After **2026-06-25 00:00 UTC**, the label $T$ allegedly shifted to denote the observation at $T+5\text{m}$, and the daily timestamp grid shifted from `00:05...00:00(next day)` to `00:00...23:55`.
  - **Defensive Invariant:** The schema requires separate `stock_snapshot_time_utc` and `flow_interval_end_utc` fields. Ingested metrics rows must undergo synthetic transition checks; any unverified shift will force `PIT_UNKNOWN` classification on affected partitions.
- **Timestamp Precision Evolution (Milliseconds to Microseconds):**
  - Binance historical Spot transitioned from millisecond integers ($13$ digits, $10^{12}$) to microsecond integers ($16$ digits, $10^{15}$) in 2025.
  - The ingestion parser must dynamically validate timestamp integer length; timestamps must be cast to signed 64-bit microsecond integers (`INT64` microseconds since Unix epoch) upon Parquet serialization.
- **Exchange Timezone Invariance:**
  - While local user sessions or operating systems may execute in UTC+8, all partition directories, manifest timestamps, and Parquet temporal keys must strictly adhere to **UTC (ISO 8601)**.

---

## 4. Three-Tier Storage Path Architecture, Format Hypotheses, and Workspace Isolation

```
<AUTHORIZED_DATA_WORKSPACE>/
├── quarantine/                           # IMMUTABLE RAW ARCHIVES (Read-Only)
│   ├── binance/
│   │   ├── spot/{family}/{symbol}/year={YYYY}/month={MM}/
│   │   │   ├── {symbol}-{family}-{date}.zip
│   │   │   └── {symbol}-{family}-{date}.zip.CHECKSUM
│   │   └── usdt_perp/{family}/{symbol}/...
│   └── okx/
│       ├── spot/{family}/{symbol}/...
│       └── usdt_swap/{family}/{symbol}/...
├── lake/                                 # TRANSFORMED VALIDATED PARQUET (ZSTD)
│   ├── tier_a_core/                      # Klines, Mark, Index, Funding, Metrics OI
│   │   └── {venue}/{product_type}/{family}/{symbol}/year={YYYY}/
│   │       └── part-{date}-{schema_version}.parquet
│   ├── tier_b_trades/                    # Raw Trades & AggTrades (Partitioned)
│   │   └── {venue}/{product_type}/{family}/{symbol}/year={YYYY}/month={MM}/
│   │       └── part-{date}-{schema_version}.parquet
│   └── tier_c_l2/                        # L2 Snapshots & Diffs (Conditional/Quarantined)
│       └── {venue}/{product_type}/{family}/{symbol}/...
├── features/                             # CAUSAL FEATURE STORE WITH LINEAGE
│   └── {feature_set_id}/v{version}/
├── catalog/                              # METADATA LEDGER & INTEGRITY MANIFEST
│   ├── manifest.duckdb                   # Authoritative partition registry
│   └── checksums_verified.jsonl
└── staging/                              # TRANSIENT SCRATCHPAD (Ephemeral)
    └── scratch_worker_{pid}/
```

### 4.1 Tier Characteristics and Boundary Rules
1. **Tier A Core (Compact High-Value):**
   - Ingestion families: 1m Klines (OHLCV), Mark Price Klines, Index Price Klines, Premium Index Klines, Funding Rate records, 5m Metrics (Open Interest, Long/Short ratios).
   - Storage properties: Dense temporal structure, highly compressible, negligible I/O bottleneck. Primary foundation for macro regimes and multi-hour signals.
2. **Tier B Trades (High-Volume Tick History):**
   - Ingestion families: AggTrades (Binance), Raw Trades (Binance, OKX).
   - Storage properties: Hundreds of millions of rows per instrument-year; partitioned strictly by single UTC days. Requires strict partition pruning during queries.
3. **Tier C L2 Depth (Ultra-High Volume Microstructure):**
   - Ingestion families: L2 100ms order book snapshots, full depth diffs.
   - Storage properties: Multi-terabyte scale. Subject to **`STORAGE_BLOCKED_LOCAL`** under current single-disk constraints (§6). Architecture specified; physical intake barred.

### 4.2 Storage Format and Compression Hypothesis
- **Format:** Apache Parquet (Format Version 2.6+).
- **Compression Hypothesis:** Zstandard (`ZSTD`, Compression Level 3 for standard lake partitions; Level 7 for frozen cold archival).
- **Evidentiary Caveat:** The compression ratio of Parquet/ZSTD over raw CSV (typically assumed to be $4\times$ to $8\times$) is formulated here as an **engineering hypothesis**, not a verified empirical measurement. Exact compression and expansion ratios must be measured on permitted sample partitions during Task D/E before committing large backfill jobs.

### 4.3 Safe Path Layout and Workspace Security Isolation
1. **Explicit Authorized Root Selection:** No data ingestion script or pipeline worker may write outside an explicitly declared workspace directory (e.g. `z:\root\workspace\data-intake-r1\`).
2. **Symlink Escape Prevention:** Every target path must be verified using canonical path resolution (`realpath` / `Get-Item -LiteralPath`). If the canonical target does not share the authorized workspace prefix, the write operation must abort immediately with a security exception.
3. **Prohibition of Protected / Private Paths:** Traversal, directory listing, or stat probing of `Quant-agent/data`, `Quant-agent-sanitized`, H39/H40/H41, Forward, or Final holdout trees is strictly forbidden.
4. **Git Protection Rule:** Data workspace `.gitignore` must explicitly block `*.zip`, `*.csv`, `*.parquet`, `*.gz`, `*.tar`, `*.duckdb`, `*.sqlite`, `*.part`, and `/staging/`. Raw market data payloads must never be committed to Git.

---

## 5. Baseline Historical Observations & Overlap Uncertainty Analysis

### 5.1 Historical Inventory Witness Ledger
The prior historical observations referenced in project records are cataloged below. Per task contract, these are treated as **unverified historical observations**, not verified physical assets:

| Data Group / Asset Class | Reported Volume / Duration | Status in Task C | Overlap Uncertainty & Ingestion Hazard |
|---|---|---|---|
| Existing BTC Research/Forward | ~172.33 GiB (mixed formats) | **UNVERIFIED** | Format unknown (CSV/Parquet/DB); overlap with candidate download partitions unmapped. |
| Filesystem Reported Free Space | ~724 GiB free on ~1 TiB disk | **UNVERIFIED** | Physical sector allocation, OS reserve, and competing worktrees not remeasured. |
| BTC AggTrades (Spot + USD-M) | 61 months (~79.6 GiB compressed)| **UNVERIFIED** | Potential 100% duplicate of candidate public archives; re-downloading wastes ~80 GiB. |
| BTC 1m Klines (USD-M / Spot) | 67 months USD-M, 61 months Spot | **UNVERIFIED** | Date coverage overlaps candidate partitions; re-ingestion must check source hashes first. |
| Forward Microstructure Data | ~92 GiB BTC forward records | **UNVERIFIED** | Proprietary live recorder files; must remain isolated from public archive pipelines. |
| Non-BTC Hourly Series | 5 series (ETH, BNB, ADA, LTC, XRP)| **UNVERIFIED** | Hourly frequency; does not satisfy 1m intraday granularity requirements. |

### 5.2 Deduplication and Source Hash Reconciliation Invariants
- **Monthly versus Daily Archive Overlap:** Binance Public Data publishes both monthly aggregated archives (`BTCUSDT-aggTrades-2023-05.zip`) and daily archives (`BTCUSDT-aggTrades-2023-05-01.zip` through `31.zip`) for the identical trade events.
  - **Deduplication Rule:** A partition manifests daily granularity. If a monthly archive is ingested, the 31 corresponding daily archives must be marked `SUPERSEDED_BY_MONTHLY` in the manifest, and their download URLs suppressed. Ingesting both forms constitutes an unforced 100% storage waste.
- **Local Hash Preflight:** Before any remote GET request is dispatched in Wave 2, the pipeline must query the manifest index for existing matching publisher SHA-256 digests. If a matching digest exists in the quarantine store, the download must be skipped with status `ALREADY_INGESTED`.

---

## 6. Outcome-Blind Sampling Protocol and Byte Extraction Benchmark Model

### 6.1 Objective, Non-Strategy-Biased Sampling Protocol
To measure physical byte densities without introducing data-snooping or selection bias, sample partitions must be selected using **strictly calendar-driven and volatility-driven criteria**, blind to strategy profitability or backtest signals:
- **Maximum Sample Quota:** Exactly **3 daily partitions per family × instrument × venue**.
- **Sample Selection Classes:**
  1. **Quiet / Low-Activity Regime:** Lowest decile of 24h market-wide price range and transaction count (e.g. consolidation weekend: `2023-09-17 UTC`).
  2. **Typical / Median Regime:** Median 24h volume and trade count day across the multi-year history (e.g. mid-week standard trading: `2023-11-15 UTC`).
  3. **High-Activity / Market Stress Regime:** Extreme volatility, liquidation cascade, or market-wide regime shift (e.g. cascade liquidation day: `2023-08-17 UTC` or volatility spike `2024-03-05 UTC`).

### 6.2 Parametric Extraction and Benchmark Metrics
For each sampled partition $p$, the benchmark harness must record the following metrics:
$$S_{\text{compressed}}(p) = \text{File size of downloaded archive ZIP/GZ (Bytes)}$$
$$S_{\text{expanded}}(p) = \text{Size of extracted raw CSV payload (Bytes)}$$
$$S_{\text{parquet}}(p) = \text{Size of transformed Parquet file with ZSTD Level 3 (Bytes)}$$
$$R_{\text{expansion}}(p) = \frac{S_{\text{expanded}}(p)}{S_{\text{compressed}}(p)}, \quad R_{\text{parquet}}(p) = \frac{S_{\text{parquet}}(p)}{S_{\text{expanded}}(p)}$$
$$P_{\text{temp}}(p) = S_{\text{compressed}}(p) + S_{\text{expanded}}(p) + S_{\text{parquet}}(p) + S_{\text{buffer}} \quad (\text{Peak staging footprint})$$
$$T_{\text{checksum}}(p) = \text{CPU seconds for SHA-256 verification}, \quad T_{\text{parse}}(p) = \text{CPU seconds for CSV-to-Parquet conversion}$$

### 6.3 Wave 1 Status: Measured Fields Nullification
Because Wave 1 Task C operates under strict planning constraints ($0 budget, 0 byte downloads, no confidential scans), all empirical size and CPU fields remain **`NULL / UNMEASURED`**. Below is the formal specification matrix ready for population upon authorized execution of Task D/E:

| Benchmark Field | Status in Task C | Unit | Population Dependency / Method |
|---|---|---|---|
| `sample_quiet_compressed_bytes` | `NULL` | Bytes | To be measured on quiet sample partition in Task D/E |
| `sample_quiet_parquet_bytes` | `NULL` | Bytes | To be measured after Parquet conversion in Task D/E |
| `sample_typical_compressed_bytes`| `NULL` | Bytes | To be measured on typical sample partition in Task D/E |
| `sample_typical_parquet_bytes` | `NULL` | Bytes | To be measured after Parquet conversion in Task D/E |
| `sample_high_compressed_bytes` | `NULL` | Bytes | To be measured on stress sample partition in Task D/E |
| `sample_high_parquet_bytes` | `NULL` | Bytes | To be measured after Parquet conversion in Task D/E |
| `expansion_ratio_observed` | `NULL` | Ratio | Computed: `expanded_bytes / compressed_bytes` |
| `parquet_zstd_ratio_observed` | `NULL` | Ratio | Computed: `parquet_bytes / expanded_bytes` |
| `peak_temp_headroom_observed` | `NULL` | Bytes | Monitored peak transient disk utilization |
| `checksum_cpu_seconds` | `NULL` | Seconds | Wall-clock execution time of native SHA-256 |
| `parser_cpu_seconds` | `NULL` | Seconds | Wall-clock execution time of PyArrow / Polars transform |

*Statistical Integrity Note:* P50 and P90 percentiles are deliberately omitted. Deriving empirical distribution percentiles from a 3-point sample violates statistical validity; planning relies strictly on transparent Low / Base / High parametric scenarios (§7).

---

## 7. Capacity Reservation, Multi-Venue Storage Model, and Scenarios

### 7.1 Verified Usable Reserve and Safety Floor Arithmetic
The total filesystem capacity and unverified free space are governed by a mandatory safety reserve floor:
- Nominal Total Filesystem Capacity: $C_{\text{disk}} \approx 1024\text{ GiB}$ (1 TiB)
- Unverified Historical Free Capacity: $F_{\text{reported}} = 724\text{ GiB}$
- **Mandatory Safety Floor Formula:**
  $$\text{Floor}_{\text{disk}} = \max\left(100\text{ GiB}, \, 0.25 \times C_{\text{disk}}\right) = \max\left(100\text{ GiB}, \, 256\text{ GiB}\right) = \mathbf{256\text{ GiB}}$$
- **Nominal Usable Capacity Cap:**
  $$\text{Cap}_{\text{usable}} = F_{\text{reported}} - \text{Floor}_{\text{disk}} = 724\text{ GiB} - 256\text{ GiB} = \mathbf{468\text{ GiB}}$$
- **Peak Transient Staging Headroom Reserve:**
  $$S_{\text{staging\_reserve}} \ge 2 \times \max\left(\text{Monthly Compressed Partition Size}\right) \times N_{\text{workers}} \approx \mathbf{60\text{ GiB}}$$
- **Effective Permanent Storage Ceiling:**
  $$\text{Cap}_{\text{permanent}} = \text{Cap}_{\text{usable}} - S_{\text{staging\_reserve}} = 468\text{ GiB} - 60\text{ GiB} = \mathbf{408\text{ GiB}}$$

### 7.2 Multi-Venue Scope and Parametric Size Estimation Formulas
The target universe comprises **8 core trading products**:
1. Binance Spot `BTCUSDT`
2. Binance Spot `ETHUSDT`
3. Binance USD-M Perpetual `BTCUSDT`
4. Binance USD-M Perpetual `ETHUSDT`
5. OKX Spot `BTC-USDT`
6. OKX Spot `ETH-USDT`
7. OKX USDT-SWAP `BTC-USDT-SWAP`
8. OKX USDT-SWAP `ETH-USDT-SWAP`

For each data family $f$ and instrument $i$, the total storage demand over $D$ historical days is given by:
$$S_{\text{total}}(i, f) = D \times \left( b_{\text{archive}}(i, f) + b_{\text{parquet}}(i, f) \right) \times \left(1 + \mu_{\text{index}}\right)$$
where $b_{\text{archive}}$ is daily compressed archive bytes, $b_{\text{parquet}}$ is daily Parquet ZSTD bytes, and $\mu_{\text{index}} \approx 0.02$ represents DuckDB manifest metadata and catalog overhead.

### 7.3 Three-Scenario Storage Projection (5-Year History + 12-Month Forward Growth)
Assumptions per scenario:
- **Low Scenario:** Aggressive filtering (aggTrades only, Klines 1m, Funding, Metrics OI; low market volatility baseline).
- **Base Scenario:** Standard research configuration (Tier A Core complete + Tier B AggTrades / selected raw trades for BTC/ETH; typical market volatility).
- **High Scenario:** Comprehensive capture (Tier A Core + Tier B full raw trades for all 8 products; sustained high-volatility regime).

| Data Tier / Component | Low Scenario (GiB) | Base Scenario (GiB) | High Scenario (GiB) | Feasibility on 408 GiB Ceiling |
|---|---|---|---|---|
| **Tier A Core (All 8 Products)** | 8.5 GiB | 18.2 GiB | 34.0 GiB | **FEASIBLE (Fully fits in all scenarios)** |
| 1m Klines (OHLCV) | 3.2 GiB | 6.5 GiB | 11.0 GiB | Feasible |
| Mark/Index/Premium Klines (Perps) | 2.1 GiB | 4.8 GiB | 8.5 GiB | Feasible |
| Funding Rate & 5m Metrics OI | 0.8 GiB | 1.9 GiB | 3.5 GiB | Feasible |
| Raw Archive Quarantine (Tier A) | 2.4 GiB | 5.0 GiB | 11.0 GiB | Feasible |
| **Tier B Trades (Candidate Intake)** | 145.0 GiB | 320.0 GiB | 980.0 GiB | **CONDITIONAL / BOUNDED ONLY** |
| AggTrades (Binance 4 products) | 85.0 GiB | 175.0 GiB | 380.0 GiB | Feasible in Base |
| Raw Trades (OKX 4 products) | 60.0 GiB | 145.0 GiB | 600.0 GiB | Base fits ceiling; High breaches |
| **Metadata & Manifest Catalog** | 2.5 GiB | 5.0 GiB | 10.0 GiB | **FEASIBLE** |
| **Subtotal (Tier A + Tier B)** | **156.0 GiB** | **343.2 GiB** | **1,024.0 GiB** | Base fits ($343.2 \le 408$ GiB); High fails |
| **Tier C L2 Depth (All 8 Products)** | 1,800.0 GiB | 4,500.0 GiB | 12,000.0 GiB | **STORAGE_BLOCKED_LOCAL (100% Breached)** |
| **12-Month Forward Ingestion (Base)**| +32.0 GiB | +72.0 GiB | +210.0 GiB | Requires annual rolling archival |

### 7.4 Architectural Capacity Findings and Limits
1. **Tier A Core Fits Safely:** Tier A Core across all 8 products for a complete 5-year historical backfill requires only $\sim 18.2\text{ GiB}$ in the Base scenario. It can be ingested with zero capacity concerns.
2. **Tier B Trades Require Strict Pruning and Selective Bounding:**
   - Full 5-year unpruned raw trade archives for all 8 products in the High scenario ($\sim 980\text{ GiB}$) drastically breach the $408\text{ GiB}$ permanent storage ceiling.
   - **Mandatory Policy Limit:** Intake of Tier B data must prioritize **Binance AggTrades** over raw individual fills, and historical depth must be bounded to specific high-priority research windows (e.g. 24 months) unless external storage expansion is provided.
3. **Tier C L2 Depth is Hard-Blocked on Single Disk:** Even a single instrument's L2 order book depth for one year requires $\sim 350–800\text{ GiB}$. Storing Tier C locally across 8 instruments would instantly exhaust the entire 1 TiB drive. Tier C is designated **`STORAGE_BLOCKED_LOCAL`**; local execution must not ingest Tier C archives.

---

## 8. Idempotent Pipeline Architecture and Concrete Synthetic Acceptance Test Plan

### 8.1 Resilient Pipeline Invariants
1. **Atomic Ingestion Protocol:** All network payload downloads must write to temporary files with `.part` extensions. Only upon complete payload receipt and successful SHA-256 verification against the official publisher digest may the file be atomically renamed to its canonical archive name.
2. **Checksum Failure Quarantine:** If a computed digest does not match the publisher digest:
   - File is immediately moved to `quarantine/invalid_checksum/{partition_id}.corrupt`.
   - The partition manifest is flagged `CHECKSUM_FAILED`.
   - Downstream Parquet processing is blocked; zero corrupted rows enter the lake.
3. **Bounded Concurrency and I/O Throttling:**
   - Worker concurrency bounded to $N \le 2$ parallel processes to prevent disk I/O starvation.
   - Network throughput throttled to $\le 10\text{ MB/s}$ to preserve host bandwidth.
4. **L2 Snapshot/Delta State Machine (Architecture Specification):**
   - L2 depth streams must maintain a state machine tracking sequence numbers (`seqId`, `firstUpdateId`, `lastUpdateId`).
   - If an update gap is detected ($\text{update.firstUpdateId} > \text{state.lastUpdateId} + 1$), the state machine invalidates the book and awaits the next full depth snapshot.

```
+--------------------------------------------------------------------------------------------------+
|                                    IDEMPOTENT INTAKE PIPELINE                                    |
+--------------------------------------------------------------------------------------------------+
                                                 |
                                     [1. Query Manifest Status]
                                                 |
                       +-------------------------+-------------------------+
                       |                                                   |
             [Already Complete?]                                  [New / Incomplete]
                       |                                                   |
                   [SKIP GET]                                     [2. Acquire Floor Lock]
                                                                           |
                                                             [Free Space >= 256 GiB?]
                                                                           |
                                                      +--------------------+--------------------+
                                                      |                                         |
                                                   [NO]                                       [YES]
                                                      |                                         |
                                            [ABORT: DISK_FULL]                         [3. Download to .part]
                                                                                                |
                                                                                       [4. Compute SHA-256]
                                                                                                |
                                                                               +----------------+----------------+
                                                                               |                                 |
                                                                        [Hash Mismatch]                     [Hash Match]
                                                                               |                                 |
                                                                    [Move to quarantine/corrupt]      [Atomic Rename to .zip]
                                                                               |                                 |
                                                                     [Flag: CHECKSUM_FAIL]            [5. Parse to Parquet]
                                                                                                                 |
                                                                                                      [Atomic Commit to Lake]
                                                                                                                 |
                                                                                                      [Update Manifest: OK]
```

### 8.2 Concrete Synthetic Acceptance Test Plan
The following 6 acceptance tests specify synthetic verification fixtures. These tests are engineering designs and acceptance criteria for subsequent implementation tasks; they are **not claims that tests were run against live payloads during this planning contract**:

#### Test Case 1: Corrupt Publisher Checksum Quarantine Test
- **Objective:** Verify that an archive payload with a modified byte is detected, quarantined, and barred from Parquet conversion.
- **Fixture:** Generate synthetic partition `test_kline_corrupt.zip` with valid zip structure; construct `test_kline_corrupt.zip.CHECKSUM` with mismatched SHA-256 digest.
- **Action:** Execute ingestion pipeline worker against fixture.
- **Expected Outcome:** Pipeline aborts rename; moves file to `quarantine/invalid_checksum/`; records `checksum_verified = FALSE` and `source_availability_class = 'CHECKSUM_FAILED'` in manifest; zero Parquet files generated.

#### Test Case 2: Interrupted / Partial Write Resume Test
- **Objective:** Verify that an interrupted network download leaves no orphaned files and resumes idempotently.
- **Fixture:** Create synthetic incomplete `test_aggtrades.zip.part` truncated at 50% byte count.
- **Action:** Trigger ingestion run for partition; simulate resume.
- **Expected Outcome:** Pipeline identifies existing `.part` file, verifies incomplete size, wipes or resumes `.part` from byte offset, completes download, verifies hash, and commits canonical `.zip`.

#### Test Case 3: Monthly versus Daily Duplicate Partition Collision Test
- **Objective:** Prevent redundant ingestion of daily archives when a monthly archive is present.
- **Fixture:** Register monthly partition `BINANCE_USDT_PERP_BTCUSDT_AGGTRADES_2023-05` in manifest; supply daily archive URLs for `2023-05-01` through `2023-05-31`.
- **Action:** Run manifest partition resolution preflight.
- **Expected Outcome:** Manifest preflight marks all 31 daily partitions as `SUPERSEDED_BY_MONTHLY`; download manager skips daily downloads; 0 bytes duplicate bandwidth consumed.

#### Test Case 4: Schema Drift & Timestamp Anomaly Test
- **Objective:** Verify parser resilience to timestamp scale transitions (ms to $\mu$s) and inverted `create_time` grids.
- **Fixture:** Synthetic CSV containing:
  - Row 1–10: Millisecond epoch timestamps ($1.68 \times 10^{12}$).
  - Row 11–20: Microsecond epoch timestamps ($1.68 \times 10^{15}$).
  - Row 21: Duplicate `00:00` transition label with inverted stock/flow columns.
- **Action:** Pass synthetic stream to Parquet transform worker.
- **Expected Outcome:** Parser auto-detects magnitude shift, standardizes all timestamps to `TIMESTAMP_NTZ(MICROSECOND)`; detects inverted label and flags partition `TRANSITION_ANOMALY_DETECTED` in manifest.

#### Test Case 5: Hard Partition Byte-Cap Enforcement Test
- **Objective:** Ensure a single abnormal partition cannot expand indefinitely and exhaust local disk.
- **Fixture:** Synthetic zip payload that decompresses into an oversized 50 GiB sparse CSV (decompression bomb simulation); configure single-partition cap $\text{Cap}_{\text{part}} = 5\text{ GiB}$.
- **Action:** Trigger decompression worker with streaming byte counter.
- **Expected Outcome:** Stream decompressor aborts execution at $5.001\text{ GiB}$; terminates worker process; deletes temporary `.csv` buffer; flags partition `BYTE_CAP_BREACHED`.

#### Test Case 6: Safety Floor Breach / Disk-Full Rejection Test
- **Objective:** Verify that the pipeline refuses to initiate downloads if filesystem free space violates the safety floor.
- **Fixture:** Mock filesystem environment reporting $F_{\text{mock}} = 200\text{ GiB}$ free space on a $1024\text{ GiB}$ drive (violating the $256\text{ GiB}$ floor).
- **Action:** Dispatch batch ingestion job for Tier A core.
- **Expected Outcome:** Pipeline preflight calculates $F_{\text{mock}} < \text{Floor}_{\text{disk}}$ ($200 < 256$ GiB); refuses job dispatch with error `ERR_SAFETY_FLOOR_BREACH`; performs 0 HTTP requests.

---

## 9. Downstream Task Gating Matrix and Transition Prerequisites (D/E/F/G/H)

All subsequent tasks in the Wave 1 / Wave 2 program remain governed by immutable gating conditions. No downstream task may self-activate:

| Task ID | Role & Description | Prerequisite Gates Required for Unlocking | Authorization Status |
|---|---|---|---|
| **Task D** | Binance Bounded Intake (EXPOSED_DEV pilot) | (1) Frozen Task A metadata report; (2) Frozen Task C storage architecture (this document); (3) Explicit owner-authorized isolated local data workspace; (4) Formal Controller dispatch. | **PREPARED_CONDITIONAL (NOT AUTHORIZED)** |
| **Task E** | OKX Bounded Intake (Sample QC) | (1) Frozen Task B feasibility report; (2) Frozen Task C storage architecture (this document); (3) OKX historical portal rights clarification; (4) Explicit owner-authorized workspace. | **PREPARED_CONDITIONAL (NOT AUTHORIZED)** |
| **Task F** | Independent Cross-Venue QC | (1) Completed and audited Task D and Task E artifacts; (2) Synchronized clock & timestamp reconciliation; (3) Independent auditor (ChatGPT-1) review. | **PREPARED_CONDITIONAL (NOT AUTHORIZED)** |
| **Task G** | Complete Historical Backfill | (1) Task F QC PASS; (2) Measured sample compression benchmarks from D/E; (3) Explicit owner storage budget grant exceeding Floor floor; (4) Controlled rate-limit permit. | **NOT AUTHORIZED** |
| **Task H** | Forward As-Received Collector | (1) Task F QC PASS; (2) Live REST/WS legal entitlement verification; (3) Isolated forward capture daemon workspace; (4) Financial risk and order-routing firewall. | **NOT AUTHORIZED** |

---

## 10. Final Disposition, Execution Boundaries, and Verifiable Git Receipts

### 10.1 Terminal Disposition
$$\mathbf{C\_DESIGN\_READY\_WITH\_LIMITS}$$

**Grounds for Disposition:**
1. A portable, multi-venue manifest schema indexing `venue × product_type × instrument_id × family × UTC_partition` has been completely designed with explicit causal clock and legal rights attributes.
2. Exchange-native semantics, contract multiplier asymmetries ($0.01$ BTC / $0.1$ ETH for OKX Swaps), time-label lookahead hazards, and timestamp migrations ($\text{ms} \to \mu\text{s}$) have been fully specified.
3. The three-tier storage architecture (Tier A Core, Tier B Trades, Tier C L2) has been formalized with strict workspace isolation, symlink defenses, and Git contamination guards.
4. Physical capacity models established that **Tier A Core fits safely** ($\sim 18.2\text{ GiB}$ Base), **Tier B Trades require selective pruning/bounding** ($\le 408\text{ GiB}$ limit), and **Tier C L2 Depth is hard-blocked locally** (`STORAGE_BLOCKED_LOCAL`).
5. All empirical byte fields remain properly nullified (`NULL / UNMEASURED`) pending authorized sample measurements in Task D/E.
6. A concrete 6-part synthetic acceptance test plan has been established to govern implementation resilience.

### 10.2 Final Execution Boundaries
- Total financial expenditure: **USD 0.00**
- External payload bytes downloaded: **0 Bytes**
- Protected / private local paths inspected: **None (0 files)**
- Executable strategy code modified: **None (0 lines)**
- Automated successor dispatches triggered: **None (0 tasks)**

### 10.3 Verifiable Git Execution Receipts
- **Author Worktree Path:** `z:\root\workspace\project\quant-v0.6\docs-v06-data-c-storage-schema-plan-r1`
- **Target Git Branch:** `docs/v06-data-c-storage-schema-plan-r1`
- **Direct Dispatch Parent Commit SHA:** `ade4df19872122686432cd955d8f139f16069449`
- **Dispatch Prompt Blob SHA:** `7971ec5c33233a82ffd97433fdc82c0e1d86483f`
- **Added Deliverable File:** `docs/project/V06_DATA_C_VENUE_STORAGE_SCHEMA_AND_CAPACITY_MODEL_R1.md`
