# R11-Q2 Controller Decision — Capacity Expansion + Data Foundation

**Date:** 2026-10-16 Asia/Shanghai  
**Authority:** ChatGPT-0 B-line Controller  
**State:** `R11_Q2_DATA_FOUNDATION_READY_WITH_LIMITS`

## Decision

The R11-Q1 independent audit is preserved as an immutable negative consequential gate. It correctly prevents treating the current A/B/C/D1 package as general source/PIT/Alpha admission. However, two blockers are now materially narrowed by new evidence:

1. **OKX historical-portal rights:** the official OKX Historical Data Terms explicitly state that personal use includes possession, retention and use of the historical Data for development of the user's own trading strategy, and grant a limited, revocable, non-exclusive, royalty-free license for personal use. This is materially different from the separate API Agreement's generic Market Data restrictions. Therefore the prior Q1 B block should NOT be applied to the historical-data portal channel as if it were only an API-use question. The portal still does not grant redistribution/commercial use, and it does not prove every instrument/file is available. Source: official OKX Historical Data Terms, last updated 2023-10-26. `https://www.okx.com/en-sg/help/historicaldata-terms-and-conditions`.
2. **Capacity:** physical disk capacity is an operational scaling variable, not a scientific blocker. The owner may expand the filesystem. Nevertheless, actual per-family bytes, staging high-water mark and expected retained footprint must be measured before committing to multi-year/full-L2 backfill. C's previous numerical capacity model remains illustrative until measured.

## Immediate scope

Authorize three **separate local-agent bounded data-foundation tasks** in parallel, each with its own isolated workspace and no strategy scoring:

- **C2:** measure current filesystem and representative source-family storage ratios; produce an expansion target. No protected-root scan. Do not automatically resize infrastructure.
- **D2:** Binance official Vision core historical data foundation pilot for BTCUSDT/ETHUSDT USD-M, reusing existing D1 bytes and adding a bounded new calibration interval. Core families: 1m Klines, Mark Price Klines, Funding Rate, historical OI/metrics where officially archived, plus trade/aggTrade only where explicitly included in the task. Preserve source-native timestamps and label PIT as unknown unless proven.
- **E2:** OKX official Historical Data Portal one-file-per-family pilot for BTC-USDT-SWAP (and only a second instrument if the first succeeds), using portal downloads rather than generic API endpoints. Validate Trade, Kline, Funding and, if the portal actually exposes it, L2. **Do not treat OKX public API OI as licensed by this portal decision**; OI remains separate/unknown unless an applicable source term and historical path are established.

No Alpha scoring, strategy rerun, model training, TESTNET, LIVE, account access, orders, or protected-history reads. Existing R9 new-Alpha pause remains.

## Data strategy

The project may now use a **single primary Binance historical data path** for offline strategy development. Cross-venue OKX data is an additional validation/robustness source, not a prerequisite for beginning engineering around the Binance path.

Do not require every future research dataset to exclude every historically exposed date. Exposure controls apply to scientific claims: data-engineering/source-QC may reuse exposed samples; any later Alpha/OOS evaluation must use a frozen exposure mask and independent holdout.

## Capacity expansion rule

If measured required retained storage exceeds current safe free space, report:

- required permanent GiB;
- temporary/staging peak GiB;
- recommended reserve;
- additional GiB to provision;
- expected 1-year / 3-year / full-history footprint;
- whether L2 should be separately provisioned.

Disk expansion may be performed by the owner outside this task. Do not auto-resize, delete existing data, or repurpose protected storage.

## Gates preserved

`SOURCE_NOT_ADMITTED / PIT_UNKNOWN / COST_INCOMPLETE / UTILITY_NOT_IDENTIFIED / G2_ALPHA_NO_GO / G4_TESTNET_NO_GO / LIVE_NO_GO / REAL_FUNDS_WRITE_NONE`.

This decision does **not** turn the data into validated Alpha or execution evidence. It authorizes only the three bounded data-foundation tasks below.