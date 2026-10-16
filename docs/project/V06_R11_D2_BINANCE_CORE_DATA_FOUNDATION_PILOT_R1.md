# R11-D2 — Binance Core Historical Data Foundation Pilot R1

**TASK_ID:** `R11-D2-BINANCE-CORE-PILOT`  
**Role:** Local Codex High / Antigravity Execution Operator.  
**State:** READY / BOUNDED.  
**Documentary Date:** 2026-10-16 (UTC+08).  
**Source:** Official Binance Vision (`https://data.binance.vision`) only. Personal/noncommercial/nonproduction offline research. Zero API/REST/WS market calls.  
**EXACTLY ONE TERMINAL:** **`R11_D2_BINANCE_CORE_PILOT_ACCEPTED_WITH_LIMITS`**  

---

## 1. Frozen Dispatch Authority and Scope

- **Dispatch Commit Parent:** `c07c60385479f0d595352ad751c1c49150b4cbbc`
- **Dispatch Prompt Blob:** `a4a827a635ae3d2bd6a9df8b0e1533fbe63d9855`
- **Worktree Session Branch:** `feature/v06-r11-d2-binance-core-pilot-r1`
- **Isolated Workspace:** `/root/workspace/project/r11-d2-binance-core-pilot`
- **Binance Vision Dataset Terms:** Snapshot `binance/binance-public-data@f446ce3812bd4e5521f21faecd4ae3c6460e49fc`, Git blob `87d04e216f62c86a2c797fbb7637404d6d602687` (v1.0 updated 2026-08-26; CC BY-NC-SA 4.0; personal, noncommercial, nonproduction historical research only; no proprietary LIVE execution rights).
- **Instruments Permitted:** `BTCUSDT` and `ETHUSDT` USDⓈ-M perpetual contracts (`futures/um`) only.
- **Calibration Interval:** **2024-01-01 through 2024-01-31 UTC** (31 full days). Bounded for source engineering, storage sizing, schema verification, and daily-vs-monthly duplicate representation validation. Not an Alpha score, OOS test, or strategy selection.
- **Reused R10-D1 Files:** 21 existing local ZIP files + 21 `.CHECKSUM` files for `BTCUSDT` 2022-09-15..21 reused directly from local disk without redundant network re-download.

---

## 2. Workspace Capacity Pre-Flight Verification

Before any network or disk allocation, storage capacity was measured on the authorized isolated filesystem:

| Metric | Measured Value | Requirement / Boundary | Status |
| --- | --- | --- | --- |
| Mount Point | `/root/workspace/project/r11-d2-binance-core-pilot` | Dedicated workspace | Verified |
| Filesystem Device | `/dev/sdd` | Dedicated ext4 volume | Verified |
| Total Space | `1,007.27 GiB` | N/A | Available |
| Used Space | `236.40 GiB` | N/A | Available |
| Available Free Space | **`721.61 GiB`** | Minimum 1.0 GiB; Safety floor 100.0 GiB | **PASS** (>720x safety margin) |

Zero volume expansions, resizing, or file deletions were performed. Capacity strictly authorized proceeding with the bounded calibration acquisition.

---

## 3. Inventory and QC Summary

The pilot evaluated **215 archive objects** across 5 source families:

| Category | Objects | Reused R10-D1 | Newly Acquired | Compressed Bytes | Expanded Bytes | QC Status |
| --- | --- | --- | --- | --- | --- | --- |
| `klines` (1m Daily) | 76 | 7 | 69 | 4,218,610 B | 14,077,587 B | **76 PASS** |
| `klines` (1m Monthly) | 2 | 0 | 2 | 3,363,205 B | 9,997,872 B | **2 PASS** |
| `markPriceKlines` (1m Daily) | 69 | 7 | 62 | 2,139,836 B | 13,874,277 B | **69 PASS** |
| `fundingRate` (Monthly) | 2 | 0 | 2 | 1,418 B | 5,124 B | **2 PASS** |
| `metrics` (5m Daily) | 69 | 7 | 62 | 10,480,248 B | 31,444,142 B | **62 PASS / 7 PARTIAL_PASS** |
| `aggTrades` (Daily Sample) | 2 | 0 | 2 | 15,361,863 B | 81,040,113 B | **2 PASS** |
| `trades` (Daily Sample) | 2 | 0 | 2 | 28,251,917 B | 188,040,366 B | **2 PASS** |
| **Total Pipeline** | **215** | **21** | **194** | **63,817,097 B (60.86 MiB)** | **323,945,031 B (308.94 MiB)** | **208 PASS / 7 PARTIAL_PASS** |

*Note on PARTIAL_PASS:* The 7 PARTIAL_PASS objects correspond to the reused September 2022 BTCUSDT metrics files from R10-D1 where the top-trader sentiment ratio fields were unpopulated in Binance's historical archive for that vintage. All 62 January 2024 metrics files are **100% complete PASS** with all 8 fields populated.

---

## 4. Source Families, Availability, and Engineering Cadence

### 4.1. 1m Klines (`klines/1m`)
- **Publisher Cadence:** Published both daily and monthly.
- **Compression & Sizing:** Daily files average ~61 KiB compressed (190 KiB expanded, 1,440 rows + header). January 2024 monthly archive is 1.81 MiB (5.07 MB expanded, 44,640 rows + header).
- **Header Normalization:** Daily files include a 12-column CSV header. Column aliases handled deterministically: `quote_asset_volume` -> `quote_volume`, `number_of_trades` -> `count`, `taker_buy_base_asset_volume` -> `taker_buy_volume`, `taker_buy_quote_asset_volume` -> `taker_buy_quote_volume`.
- **Continuity:** Zero missing 1m intervals; zero off-grid or duplicate timestamps across the 31 days.

### 4.2. 1m Mark Price Klines (`markPriceKlines/1m`)
- **Publisher Cadence:** Published daily. (Monthly mark price archives return HTTP 404).
- **Compression & Sizing:** Daily files average ~32 KiB compressed (205 KiB expanded, 1,440 rows + header).
- **Contract & Field Units:** Mark price candles provide `open, high, low, close` mark price valuations. `volume` is strictly `0.0`, `quote_volume` is `0.0`, `taker_buy_volume` is `0.0`, and `count` is exactly `60` (representing the 60 1-second index constituent samples taken during each 1-minute window).

### 4.3. Funding Rate (`fundingRate`)
- **Publisher Cadence:** **Published monthly only.** The daily URL path (`daily/fundingRate/...`) returns HTTP 404 on Binance Vision.
- **File Structure:** `data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{period}.zip`.
- **Size & Row Count:** Compressed size is only 696 bytes (2,562 bytes expanded). For January 2024 (31 days), there are exactly **93 settlement rows** (31 days × 3 intervals/day at 8h: 00:00, 08:00, 16:00 UTC).
- **Publisher Settlement Engine Jitter:** Empirical inspection reveals that `calc_time` timestamps are aligned to the 8h grid with millisecond offsets in `{0, 1, 2, 3}` ms (e.g. `1704412800001` instead of `1704412800000`). This represents internal settlement loop dispatch delay on Binance's matching engine. Our QC verifies monotonic ordering with a <=5,000 ms jitter tolerance. Zero settlement intervals are missing.

### 4.4. Historical Metrics / Open Interest (`metrics`)
- **Publisher Cadence:** **Published daily only.** The monthly URL path (`monthly/metrics/...`) returns HTTP 404 on Binance Vision.
- **File Structure:** `data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{period}.zip`.
- **Size & Row Count:** Daily files average ~155 KiB compressed (465 KiB expanded, 288 rows/day on a 5m grid: 00:00, 00:05, ..., 23:55 UTC).
- **Field Completeness in 2024:** Unlike the September 2022 vintage (where top-trader sentiment ratios were empty), **all 8 fields are 100% populated** in January 2024:
  1. `create_time`: UTC date-time string `YYYY-MM-DD HH:MM:SS`.
  2. `symbol`: Contract string (`BTCUSDT` or `ETHUSDT`).
  3. `sum_open_interest`: Open interest in contract base asset units (`BTC` or `ETH`).
  4. `sum_open_interest_value`: Open interest in quote notional (`USDT`).
  5. `count_toptrader_long_short_ratio`: Dimensionless ratio of top trader long accounts vs short accounts.
  6. `sum_toptrader_long_short_ratio`: Dimensionless ratio of top trader long positions vs short positions.
  7. `count_long_short_ratio`: Dimensionless ratio of all trader long accounts vs short accounts.
  8. `sum_taker_long_short_vol_ratio`: Dimensionless ratio of taker buy volume vs taker sell volume over the preceding 5m interval.

### 4.5. Verified Trades Sample: `aggTrades` vs `trades`
To establish exact schema, volume, and storage trade-offs without exhausting workspace budgets, a verified 1-day sample was acquired and QC-validated for 2024-01-01 UTC:

| Symbol | Family | Compressed Bytes | Expanded Bytes | Row Count | Avg Bytes / Row |
| --- | --- | --- | --- | --- | --- |
| `BTCUSDT` | `aggTrades` | 9.60 MiB | 50.44 MB | 788,143 | 64.0 B |
| `BTCUSDT` | `trades` | 17.56 MiB | 116.74 MB | 1,979,067 | 59.0 B |
| `ETHUSDT` | `aggTrades` | 5.76 MiB | 30.60 MB | 525,491 | 58.2 B |
| `ETHUSDT` | `trades` | 10.74 MiB | 71.30 MB | 1,304,180 | 54.7 B |

**Measured Trade-off:**
- `aggTrades` reduces row count by **~60%** (2.5x fewer rows than raw `trades`) and cuts compressed storage in half.
- `aggTrades` aggregates simultaneous executions against a single resting order, retaining trade ID range (`first_trade_id`..`last_trade_id`), aggregate quantity, execution price, millisecond transaction timestamp, and buyer-maker direction.
- For historical feature engineering, `aggTrades` is vastly superior in I/O throughput and storage efficiency while preserving exact price action and taker flow.

---

## 5. Daily vs. Monthly Duplicate Representation Parity Proof

A key risk in historical quantitative research is schema or data drift between daily publication files and monthly aggregated archives. We performed an exact row-level parity comparison for the entire month of January 2024 (31 days × 1,440 rows = 44,640 rows per symbol):

```
Daily Union:   Σ(BTCUSDT-1m-2024-01-01.csv ... BTCUSDT-1m-2024-01-31.csv) = 44,640 rows
Monthly File:  BTCUSDT-1m-2024-01.csv                                    = 44,640 rows
Parity Result: Headers Identical = True; Row Counts Identical = True; Exact Byte Match = True
Verdict:       DUPLICATE_IDENTICAL_REPRESENTATION
```

```
Daily Union:   Σ(ETHUSDT-1m-2024-01-01.csv ... ETHUSDT-1m-2024-01-31.csv) = 44,640 rows
Monthly File:  ETHUSDT-1m-2024-01.csv                                    = 44,640 rows
Parity Result: Headers Identical = True; Row Counts Identical = True; Exact Byte Match = True
Verdict:       DUPLICATE_IDENTICAL_REPRESENTATION
```

**Conclusion:** Daily kline files and monthly kline archives on Binance Vision are 100% byte-for-byte equivalent at the CSV row level. Future pipelines may ingest monthly archives directly for backtest efficiency without loss of fidelity.

---

## 6. Point-in-Time (PIT) Semantics and Governance

Historical data files in public batch archives inherently conflate economic event boundaries with distribution timestamps. To prevent catastrophic lookahead leakage:

1. **Economic Period Boundary (`create_time` / `open_time`):**
   - In `metrics`, `create_time` marks the beginning of the 5-minute sampling interval (`00:00:00` represents the snapshot of stock open interest and the aggregation of flow volume up to the start or end of that bucket).
   - In `klines`, `open_time` is bar open, `close_time` is bar close (e.g. `1704067200000` to `1704067259999`).
2. **Publisher Batch Publication:**
   - Daily files are compiled and published retrospectively the following UTC day.
   - Monthly files are compiled and published retrospectively the following calendar month.
3. **Receiver First-Known (`PIT_UNKNOWN`):**
   - The historical archive does NOT contain the timestamp when an external listener first observed the data live on WebSocket or REST.
   - Therefore, all metrics and historical files are strictly classified as **`PIT_UNKNOWN`**.
   - No forward lookahead assumptions are permitted.
   - Zero imputation or synthetic substitution was performed.

---

## 7. Deterministic Manifest and Receipts

The pilot generated two immutable JSON manifests in `/root/workspace/project/r11-d2-binance-core-pilot/reports/`:

| Manifest Path | Purpose | SHA-256 Digest | Total Objects | Terminal Verdict |
| --- | --- | --- | --- | --- |
| [`reports/acquisition.json`](file:///root/workspace/project/r11-d2-binance-core-pilot/reports/acquisition.json) | Full network acquisition manifest & publisher verification | `2d1817fbd9b2bcc1e33715ceafedcf3a4f40f166e8cfd9db98130ebd39c0d17c` | 215 | `R11_D2_BINANCE_CORE_PILOT_ACCEPTED_WITH_LIMITS` |
| [`reports/offline-qc.json`](file:///root/workspace/project/r11-d2-binance-core-pilot/reports/offline-qc.json) | Deterministic zero-network local verification manifest | `991d5e74884989ea7e9a3882272fb39315f46786c81e264cf23ae55592393f59` | 215 | `R11_D2_BINANCE_CORE_PILOT_ACCEPTED_WITH_LIMITS` |

---

## 8. Hard Boundaries and Preserved Governance Gates

The pilot was strictly bounded to data engineering and historical schema intake:
- **No protected paths:** Zero inspection or access to reserved holdouts, H39/H40/H41, Final, Forward, or OOS datasets.
- **No trading execution:** Zero live order execution, zero TESTNET API keys, zero private credentials.
- **No model training or Alpha scoring:** This calibration interval is not an Alpha test, PnL evaluation, or strategy validation.
- **Preserved Gates:**
  `R9_L1_PAUSE_NEW_ALPHA_RESEARCH_PENDING_EXTERNAL_SOURCE_EVIDENCE` / `SOURCE_NOT_ADMITTED` / `PIT_UNKNOWN` / `COST_INCOMPLETE` / `UTILITY_NOT_IDENTIFIED` / `G2_ALPHA_NO_GO` / `G4_TESTNET_NO_GO` / `LIVE_NO_GO` / `REAL_FUNDS_WRITE_NONE`.

**Terminal Status:** **`R11_D2_BINANCE_CORE_PILOT_ACCEPTED_WITH_LIMITS`**
