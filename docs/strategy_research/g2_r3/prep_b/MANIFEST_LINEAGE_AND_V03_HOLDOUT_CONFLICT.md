# G2 R3 Role B (`GEMINI_B`) — Static Manifest Lineage & v0.3 Holdout Conflict Report

## 1. Static Verification of Existing BTC `data_manifest.json`

Role B verified `artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json` strictly as **static JSON metadata** (`0` Parquet body opens, `0` ZIP archive reads, `0` recursive directory scans, `0` SHA256 passes over raw data bodies):

- **Symbol / Market / Timeframe**: `BTCUSDT`, `USD-M PERPETUAL`, `1m`, `UTC`
- **Time Span**: `start_ms = 1609459200000` (`2021-01-01T00:00:00Z`) to `end_ms_exclusive = 1785542400000` (`2026-08-01T00:00:00Z`)
- **Monthly Partitions**: `67` contiguous months (`2021-01` through `2026-07`), each with a 64-hex SHA256 digest in `partition_checksums`
- **Row & Continuity Integrity**: `expected_bars = 2,934,720`, `row_count = 2,934,720`, `missing_count = 0`, `duplicate_count = 0`, `out_of_order_count = 0`, `invalid_ohlc_count = 0`, `negative_volume_count = 0`, `known_gaps = []`, `largest_gap_missing_bars = 0`, `synthetic_rows = 0`, `zero_volume_count = 367`
- **Canonical Dataset SHA256**: `82d058b2e9e5bfbd20bf36026abec045fb778ddb72582277e0dac00846ae9901`
- **Funding Lineage**: `row_count = 6,114`, `checksum_sha256 = 4fd56440f275c351e521f483309b8a368ab8da66b5b6e070e164f985fc0e6ba3`, `duplicate_count = 0`, `missing_mark_prices = 0`, `mark_price_semantics = "official 1m mark-price candle open for the UTC minute containing the settlement timestamp"`
- **Official Archive Checksums (`210` entries)**:
  - `67` monthly `klines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip` (`2021-01`..`2026-07`)
  - `67` monthly `markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM.zip` (`2021-01`..`2026-07`)
  - `67` monthly `fundingRate/BTCUSDT/BTCUSDT-fundingRate-YYYY-MM.zip` (`2021-01`..`2026-07`)
  - `9` daily `markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-YYYY-MM-DD.zip`
- **Mandatory Source Grade**: `ARCHIVAL_EVENT_TIME_RECONSTRUCTED`. Prior research exposures remain exposed (`prior_exposures_remain_exposed = true`, `blind_oos_claim_permitted = false`).

## 2. Critical Conflict: Old BTC v0.3 Final Holdout vs. R3 Proposed Feb–Apr 2026

The historical v0.3 Bitcoin audit sealed `[2026-02-01T00:00:00Z, 2026-08-01T00:00:00Z)` (`[1769904000000, 1785542400000)`) as `FINAL_HOLDOUT`. Comparing this sealed boundary against the R3 design's proposed development windows (`CANDIDATE_REGISTER_PROPOSAL.json`):

| R3 Proposed Window | UTC Interval | Overlap with v0.3 Final Holdout `[2026-02-01, 2026-08-01)` | Status |
|---|---|---|---|
| Warm-up (`2026-01`) | `[2026-01-01T00:00:00Z, 2026-02-01T00:00:00Z)` | `0` minutes (borders holdout start) | Warm-up only |
| Dev Fold 1 (`2026-02`) | `[2026-02-01T00:00:00Z, 2026-03-01T00:00:00Z)` | `40,320` minutes (`28` days) | **`HOLDOUT_OVERLAP_BLOCKED`** |
| Dev Fold 2 (`2026-03`) | `[2026-03-01T00:00:00Z, 2026-04-01T00:00:00Z)` | `44,640` minutes (`31` days) | **`HOLDOUT_OVERLAP_BLOCKED`** |
| Dev Fold 3 (`2026-04`) | `[2026-04-01T00:00:00Z, 2026-05-01T00:00:00Z)` | `43,200` minutes (`30` days; also R2 warm-up) | **`HOLDOUT_OVERLAP_BLOCKED`** |

**Total Overlap**: `128,160` minutes (`89` full days) per symbol across all three proposed R3 development folds. Silent reclassification or reading of `[2026-02-01, 2026-08-01)` is strictly prohibited without an explicit Controller exposure adjudication.

## 3. Eligible Pre-2026 Exposed Historic Development Months (Calendar-Only Proposals)

Static inspection of `data_manifest.json` confirms `60` contiguous pre-2026 BTCUSDT months (`2021-01` through `2025-12`) with zero overlap against `[2026-02-01, 2026-08-01)`. Without reading any price/return bodies (and never selecting dates by strategy performance), Role B catalogs three calendar-only 4-month windows (1 warm-up month + 3 development folds) for Controller consideration:

1. **`CALENDAR_OPTION_A_2025_Q4`**: Warm-up `2025-09`; Development folds `2025-10`, `2025-11`, `2025-12` (most recent contiguous pre-2026 quarter; `0` overlap with v0.3 holdout; graded `HISTORICAL_EXPOSED_DEVELOPMENT` / `ARCHIVAL_EVENT_TIME_RECONSTRUCTED`).
2. **`CALENDAR_OPTION_B_2025_Q2`**: Warm-up `2025-03`; Development folds `2025-04`, `2025-05`, `2025-06` (`0` overlap with v0.3 holdout; graded `HISTORICAL_EXPOSED_DEVELOPMENT`).
3. **`CALENDAR_OPTION_C_2024_Q4`**: Warm-up `2024-09`; Development folds `2024-10`, `2024-11`, `2024-12` (`0` overlap with v0.3 holdout; graded `HISTORICAL_EXPOSED_DEVELOPMENT`).

Any adoption of a pre-2026 development window requires:
- Explicit Controller method amendment and window freeze,
- Admission and checksum verification of matching `ETHUSDT` and `SOLUSDT` 1m trade, 1m mark, and funding archives for the same frozen calendar,
- A **first-pushed preregistration SHA verified on remote BEFORE opening any market price/mark/funding bodies**.
