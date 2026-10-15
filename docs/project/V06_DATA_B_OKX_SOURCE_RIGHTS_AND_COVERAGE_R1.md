# Wave 1 / Task B — OKX Official BTC+ETH Spot and USDT-SWAP Source, Rights, and Coverage Feasibility Report R1

**Document ID:** `V06_DATA_B_OKX_SOURCE_RIGHTS_AND_COVERAGE_R1`  
**Task Identifier:** `V06_DATA_B_OKX` (Wave 1 / Task B)  
**Execution Session:** Gemini NORMAL local session (isolated worktree, independent execution)  
**Worktree Directory:** `/root/workspace/project/quant-v0.6/docs-v06-data-b-okx-source-feasibility-r1`  
**Git Branch:** `docs/v06-data-b-okx-source-feasibility-r1`  
**Direct Root / Parent SHA:** `ade4df19872122686432cd955d8f139f16069449`  
**Dispatch SHA:** `ade4df19872122686432cd955d8f139f16069449`  
**Task Prompt Blob SHA:** `61dc388edccb3cb8ebcdee31deb8e64ce8f2a6a4`  
**Prompt Source Path:** `prompts/v0.6/b_line/data_program/V06_DATA_B_OKX_SOURCE_FEASIBILITY_GEMINI_R1.md`  
**Co-committed Governing Plan:** `docs/project/V06_MULTI_VENUE_DATA_PROGRAM_AND_STORAGE_PLAN_R1.md`  
**Co-committed DAG / Queue:** `docs/project/V06_PARALLEL_TASK_DAG_AND_EXECUTION_QUEUE_R1.md`  
**Audit Observation Timestamp:** `2026-10-16T01:50:00+08:00`  
**Budget Consumed:** **USD 0.00** (Zero payload requests, zero API key/market data requests, zero raw archive downloads)  
**Terminal Disposition:** **`B_DOCUMENTARY_READY_WITH_LIMITS`**  

---

## 1. Executive Summary and Scope of Investigation

This audit executes the immutable Wave-1 Task B OKX official source and rights feasibility evaluation under the multi-venue parallel data program dispatched by Controller commit `ade4df19872122686432cd955d8f139f16069449`. 

In strict adherence to the dispatch instructions:
1. **Public Documentation & Metadata Only:** No market API queries, authenticated keys, trial registrations, raw archive downloads, or private data were probed.
2. **Product Focus:** Four primary trading instruments:
   - Spot: `BTC-USDT` and `ETH-USDT`
   - Perpetual Swap (USDT-margined linear contracts): `BTC-USDT-SWAP` and `ETH-USDT-SWAP`
3. **Core Scope:** Portal family/file/index coverage, granularity, contract specifications, funding settlement mechanics, mark/index pricing, order-book L2 depth, clock and timestamp semantics (`ts`, `fundingTime`, `createdtime`), Open Interest (OI) availability, Point-in-Time (PIT) provenance, and controlling current legal terms (OKX Terms of Service and OKX API Agreement).
4. **Terminal Disposition:** **`B_DOCUMENTARY_READY_WITH_LIMITS`**. While official documentation proves extensive historical archive availability via the OKX Historical Data Portal and REST endpoints, critical documentary limits are established:
   - **Open Interest Historical Archive Gap:** Open Interest is completely absent from Historical Data Portal archive modules (`NOT_PUBLISHED` as bulk daily/monthly download files). Only a real-time current snapshot (`/api/v5/public/open-interest`) and coarse periodic statistics (`/api/v5/rubik/stat/contracts/open-interest-history`) exist.
   - **L2 Order Book Discontinuity:** High-resolution 5,000-level order book records (Module 5) exist only from November 1, 2025. Earlier records (March 2023 – October 2025) are 400-level (Module 4); 50-level records (Module 6) are deprecated. Historical order book CRC32 checksums are deprecated and return hardcoded `0`, requiring `seqId`/`prevSeqId` tracking.
   - **Clock Semantics:** All timestamps are exchange-assigned publication/matching times in milliseconds; original first-known-at receiver arrival time is unproven.
   - **Legal Rights:** Personal internal quantitative research and own-account execution are permitted under the OKX API Agreement (§9.2, §9.3(d)), but commercial redistribution, public open-source data publishing, competing data services, and commercial AI training are strictly prohibited (§9.3, §9.4). Geographic restrictions bar US persons from derivatives/swaps.

---

## 2. Primary Official Evidence and Sources

All findings are derived exclusively from verified first-party and official repository sources observed on 2026-10-16:

| Official Document / Source | Provenance / Access Details | Key Documentary Evidence and Findings |
| :--- | :--- | :--- |
| **OKX Historical Data Portal** | Landing page: `https://www.okx.com/historical-data`<br>Client bundle: `brokerHistory-79YS5Hwe.js` | Advertises venue-wide availability: Trade ticks from Sep 2021, Candlesticks from Jul 2023, Funding rates from Mar 2022, High-resolution L2 from Mar 2023, Borrowing rates from Dec 2021. **These are venue-wide marketing claims, not per-product guarantees.**<br>Internal portal schema defines module IDs: `TRADE_HISTORY` (`1`), `CANDLESTICK` (`2`), `FUNDING_RATES` (`3`), `ORDER_BOOK_400` (`4`), `ORDER_BOOK_5000` (`5`), `ORDER_BOOK` (`10`), `INTEREST_RATE` (`11`).<br>Daily aggregation imposes a 2-day publication delay (T-2) for trades/candles and a 3-day delay (T-3) for order books, with maximum query window of 7 days. Monthly aggregation imposes availability on the 2nd day of the following month, with maximum query window of 6 months.<br>**Critical finding:** Open Interest is completely missing from Historical Data Portal modules. |
| **OKX V5 API Documentation** | Official docs: `https://www.okx.com/docs-v5/en/`<br>Public Data & Market Data modules | Details REST endpoint limits and schemas:<br>• `GET /api/v5/market/history-trades`: Last 3 months only; paginated by `tradeId`; limit max 500/req; rate limit 20 req/2s.<br>• `GET /api/v5/market/history-candles`: Paginated by Unix ms `ts`; limit max 300/req; rate limit 20 req/2s.<br>• `GET /api/v5/public/funding-rate-history`: Last 3 months only; limit max 400/req; rate limit 20 req/2s. Returns both predicted `fundingRate` and actual settled `realizedRate`.<br>• `GET /api/v5/public/open-interest`: Current snapshot only; returns `oi`, `oiCcy`, `oiUsd`, `ts`.<br>• `GET /api/v5/rubik/stat/contracts/open-interest-history`: Periodic historical OI (5m, 1H, 1D); paginated by 100 rows; rate limit 10 req/2s.<br>• `GET /api/v5/public/market-data-history`: REST API to query bulk downloadable historical data links (maps to portal modules).<br>• `GET /api/v5/public/instruments`: Authoritative instrument definitions (`ctVal`, `ctMult`, `lotSz`, `tickSz`, `minSz`). |
| **OKX Python SDK** | Repository: `okxapi/python-okx@master`<br>Key files: `consts.py`, `MarketData.py`, `PublicData.py`, `TradingData.py` | Developer reference verifying endpoint constants (`MARKET_DATA_HISTORY`, `HISTORY_TRADES`, `HISTORY_CANDLES`, `FUNDING_RATE_HISTORY`, `CONTRACTS_OPEN_INTEREST_HISTORY`). Confirms private portal API backing (`/priapi/v5/broker/public/trade-data/...`). Supporting developer docs only; does not independently prove coverage or legal rights. |
| **OKX API Agreement** | Published: Mar 26, 2026<br>Last Updated: 28 July 2026<br>URL: `https://www.okx.com/en-us/help/okx-api-agreement`<br>Supplements: OKX Terms of Service | Controlling legal contract for all programmatic and API access:<br>• §9.1: Exclusive ownership of OKX Materials and Market Data by OKX.<br>• §9.2: Grants a limited, revocable, non-exclusive, non-transferable license solely for internal purposes and account management.<br>• §9.3 & §9.4: Strict non-commercial restrictions. Bars reselling, redistributing, publishing, displaying, contributing to competing data products, and using Market Data to train/fine-tune/evaluate commercial/third-party AI models.<br>• §9.3(d): Explicitly clarifies that executing trades for one's own account (even if profitable) is permitted.<br>• §9.4: Applies equally to unauthenticated public endpoints; scraping beyond personal trading needs is prohibited.<br>• §2 & §3.6: Geographic restrictions strictly apply; US persons are barred from perpetual swaps/derivatives. |

---

## 3. Product-by-Product Official Evidence Tables

### 3.1 BTC-USDT (SPOT)

| Dimension | Observed Official Specification / Evidence | Evidence Status |
| :--- | :--- | :--- |
| **Venue & Instrument ID** | OKX: `BTC-USDT` | `AVAILABLE_VERIFIED` |
| **Product Type & Family** | `SPOT`; Base currency: `BTC`; Quote currency: `USDT` | `AVAILABLE_VERIFIED` |
| **Contract Multiplier / Value** | N/A (Spot physical token exchange, not a derivative contract). `ctVal` and `ctMult` not applicable. | `AVAILABLE_VERIFIED` |
| **Min Trade Unit & Lot Size** | Minimum order size (`minSz`): `0.00001` BTC; Lot size (`lotSz`): `0.00001` BTC; Tick size (`tickSz`): `0.1` USDT | `AVAILABLE_VERIFIED` |
| **Settlement Interval & Currency** | N/A (Immediate spot settlement in BTC/USDT). No funding mechanism. | `AVAILABLE_VERIFIED` |
| **Price Mechanisms** | Real-time executed trade price (`px`); Index price (`GET /api/v5/market/index-tickers?instId=BTC-USDT`). Mark price not used for margin settlement on cash spot. | `AVAILABLE_VERIFIED` |
| **Historical Trade Tick Coverage** | Portal: Advertised from Sep 2021 (Module 1, daily/monthly archives).<br>REST: `GET /api/v5/market/history-trades` covers last 3 months only (max 500 records/req). | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Historical Candlestick (1m)** | Portal: Advertised from Jul 2023 (Module 2, daily/monthly archives).<br>REST: `GET /api/v5/market/history-candles` covers recent years via pagination (max 300 candles/req). | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Open Interest (OI) Coverage** | Not applicable to Spot markets. Neither portal nor REST endpoints provide OI for spot. | `NOT_APPLICABLE` |
| **Order Book L2 Depth & History** | Portal: Module 4 (400-level) from Mar 2023; Module 5 (5,000-level) from Nov 1, 2025.<br>REST: `GET /api/v5/market/books?instId=BTC-USDT&sz=400` (snapshot only).<br>WebSocket: `books` (400 levels, snapshot then incremental deltas) and `books-l2-tbt`. Checksum deprecated (returns 0); continuity via `seqId`. | Portal: `AVAILABLE_UNMEASURED`<br>REST/WS: `AVAILABLE_VERIFIED` |
| **Timestamp Semantics** | `ts` and `createdtime` in milliseconds (ms). Represents OKX matching engine execution time, not client reception time. UTC daily partitioning (00:00:00 – 23:59:59.999 UTC). | `AVAILABLE_VERIFIED` |
| **Legal Rights Status** | OKX API Agreement §9.2 / §9.4: Personal internal research and own-account trading permitted (`PERSONAL_INTERNAL_USE_PERMITTED`). Commercial redistribution, public GitHub publishing, and AI commercial training prohibited (`COMMERCIAL_REDISTRIBUTION_PROHIBITED`). US persons permitted for Spot. | `RIGHTS_CONDITIONAL_PERSONAL_ONLY` |

---

### 3.2 ETH-USDT (SPOT)

| Dimension | Observed Official Specification / Evidence | Evidence Status |
| :--- | :--- | :--- |
| **Venue & Instrument ID** | OKX: `ETH-USDT` | `AVAILABLE_VERIFIED` |
| **Product Type & Family** | `SPOT`; Base currency: `ETH`; Quote currency: `USDT` | `AVAILABLE_VERIFIED` |
| **Contract Multiplier / Value** | N/A (Spot physical token exchange). `ctVal` and `ctMult` not applicable. | `AVAILABLE_VERIFIED` |
| **Min Trade Unit & Lot Size** | Minimum order size (`minSz`): `0.0001` ETH; Lot size (`lotSz`): `0.0001` ETH; Tick size (`tickSz`): `0.01` USDT | `AVAILABLE_VERIFIED` |
| **Settlement Interval & Currency** | N/A (Immediate spot settlement in ETH/USDT). No funding mechanism. | `AVAILABLE_VERIFIED` |
| **Price Mechanisms** | Real-time executed trade price (`px`); Index price (`GET /api/v5/market/index-tickers?instId=ETH-USDT`). | `AVAILABLE_VERIFIED` |
| **Historical Trade Tick Coverage** | Portal: Advertised from Sep 2021 (Module 1, daily/monthly archives).<br>REST: `GET /api/v5/market/history-trades` covers last 3 months only (max 500 records/req). | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Historical Candlestick (1m)** | Portal: Advertised from Jul 2023 (Module 2, daily/monthly archives).<br>REST: `GET /api/v5/market/history-candles` covers recent years via pagination (max 300 candles/req). | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Open Interest (OI) Coverage** | Not applicable to Spot markets. | `NOT_APPLICABLE` |
| **Order Book L2 Depth & History** | Portal: Module 4 (400-level) from Mar 2023; Module 5 (5,000-level) from Nov 1, 2025.<br>REST: `GET /api/v5/market/books?instId=ETH-USDT&sz=400` (snapshot only).<br>WebSocket: `books` / `books-l2-tbt` (incremental deltas with `seqId`). | Portal: `AVAILABLE_UNMEASURED`<br>REST/WS: `AVAILABLE_VERIFIED` |
| **Timestamp Semantics** | `ts` and `createdtime` in milliseconds (ms). OKX engine event time. UTC daily partitioning. | `AVAILABLE_VERIFIED` |
| **Legal Rights Status** | Personal internal research and own-account trading permitted (§9.2, §9.3(d)). Commercial redistribution and external AI training prohibited (§9.4). US persons permitted for Spot. | `RIGHTS_CONDITIONAL_PERSONAL_ONLY` |

---

### 3.3 BTC-USDT-SWAP (USDT-Margined Perpetual Swap)

| Dimension | Observed Official Specification / Evidence | Evidence Status |
| :--- | :--- | :--- |
| **Venue & Instrument ID** | OKX: `BTC-USDT-SWAP` | `AVAILABLE_VERIFIED` |
| **Product Type & Family** | `SWAP`; Instrument Family: `BTC-USDT`; Contract Type: `linear` (USDT-margined perpetual) | `AVAILABLE_VERIFIED` |
| **Contract Value (`ctVal`) & Multiplier** | `ctVal`: `0.01` BTC (1 contract = 0.01 BTC); `ctValCcy`: `BTC`; `ctMult`: `1`.<br>Notional Value = `sz × 0.01 × markPx`. | `AVAILABLE_VERIFIED` |
| **Min Trade Unit & Lot Size** | Minimum order size (`minSz`): `1` contract (`0.01` BTC); Lot size (`lotSz`): `1` contract; Tick size (`tickSz`): `0.1` USDT | `AVAILABLE_VERIFIED` |
| **Settlement Interval & Currency** | 8-hour funding settlement at **00:00, 08:00, 16:00 UTC**. Settlement currency: `USDT`. Dynamic intervals (1h/2h/4h) may trigger during extreme volatility under exchange risk rules. | `AVAILABLE_VERIFIED` |
| **Price Mechanisms** | Executed trade price (`px`); Mark price (`GET /api/v5/public/mark-price?instId=BTC-USDT-SWAP`); Index price (`BTC-USDT` index); Premium basis (`markPx - indexPx`). | `AVAILABLE_VERIFIED` |
| **Historical Trade Tick Coverage** | Portal: Advertised from Sep 2021 (Module 1, daily/monthly archives). Note: `sz` in trades represents contract count (1 contract = 0.01 BTC).<br>REST: `GET /api/v5/market/history-trades` covers last 3 months only. | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Historical Candlestick (1m)** | Portal: Advertised from Jul 2023 (Module 2, daily/monthly archives). `vol` is in contracts, `volCcy` is in BTC.<br>REST: `GET /api/v5/market/history-candles` covers recent years via pagination. | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Historical Funding Rate Coverage** | Portal: Advertised from Mar 2022 (Module 3, daily/monthly archives). Fields: `funding_instrumentname`, `fundingrate`, `fundingtime`.<br>REST: `GET /api/v5/public/funding-rate-history` covers last 3 months only (max 400 records/req). Returns both nominal `fundingRate` and actual settled `realizedRate`. | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Open Interest (OI) Coverage** | Portal: **`NOT_PUBLISHED`** (0 bulk archive files in portal).<br>REST Public Data: `GET /api/v5/public/open-interest` returns **current snapshot only** (`oi` in contracts, `oiCcy` in BTC, `oiUsd` in USD).<br>REST Trading Statistics: `GET /api/v5/rubik/stat/contracts/open-interest-history` provides periodic history (5m, 1H, 1D), paginated by 100 rows, but multi-year depth is unverified. | Portal: `NOT_PUBLISHED`<br>REST Snapshot: `AVAILABLE_VERIFIED`<br>Rubik History: `COVERAGE_UNKNOWN` |
| **Order Book L2 Depth & History** | Portal: Module 4 (400-level) from Mar 2023; Module 5 (5,000-level) from Nov 1, 2025.<br>REST: `GET /api/v5/market/books?instId=BTC-USDT-SWAP&sz=400` (snapshot only).<br>WebSocket: `books` and `books-l2-tbt` (incremental deltas; checksum deprecated/0; sequence continuity via `seqId`). | Portal: `AVAILABLE_UNMEASURED`<br>REST/WS: `AVAILABLE_VERIFIED` |
| **Timestamp Semantics** | `ts`, `fundingTime`, `createdtime` in Unix ms. Exchange match/settlement time. UTC daily partitions. | `AVAILABLE_VERIFIED` |
| **Legal Rights Status** | Internal personal research and own-account execution permitted (§9.2, §9.3(d)). Commercial redistribution and external AI training prohibited (§9.4). **US persons prohibited from derivatives/SWAP trading and SWAP data integration** under OKX ToS §2 and §3.6. | `RIGHTS_RESTRICTED_DERIVATIVES` |

---

### 3.4 ETH-USDT-SWAP (USDT-Margined Perpetual Swap)

| Dimension | Observed Official Specification / Evidence | Evidence Status |
| :--- | :--- | :--- |
| **Venue & Instrument ID** | OKX: `ETH-USDT-SWAP` | `AVAILABLE_VERIFIED` |
| **Product Type & Family** | `SWAP`; Instrument Family: `ETH-USDT`; Contract Type: `linear` (USDT-margined perpetual) | `AVAILABLE_VERIFIED` |
| **Contract Value (`ctVal`) & Multiplier** | `ctVal`: `0.1` ETH (1 contract = 0.1 ETH); `ctValCcy`: `ETH`; `ctMult`: `1`.<br>Notional Value = `sz × 0.1 × markPx`. | `AVAILABLE_VERIFIED` |
| **Min Trade Unit & Lot Size** | Minimum order size (`minSz`): `1` contract (`0.1` ETH); Lot size (`lotSz`): `1` contract; Tick size (`tickSz`): `0.01` USDT | `AVAILABLE_VERIFIED` |
| **Settlement Interval & Currency** | 8-hour funding settlement at **00:00, 08:00, 16:00 UTC**. Settlement currency: `USDT`. Dynamic intervals (1h/2h/4h) subject to extreme market conditions. | `AVAILABLE_VERIFIED` |
| **Price Mechanisms** | Executed trade price (`px`); Mark price (`GET /api/v5/public/mark-price?instId=ETH-USDT-SWAP`); Index price (`ETH-USDT` index); Premium basis. | `AVAILABLE_VERIFIED` |
| **Historical Trade Tick Coverage** | Portal: Advertised from Sep 2021 (Module 1, daily/monthly archives). `sz` represents contracts (1 contract = 0.1 ETH).<br>REST: `GET /api/v5/market/history-trades` covers last 3 months only. | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Historical Candlestick (1m)** | Portal: Advertised from Jul 2023 (Module 2, daily/monthly archives). `vol` in contracts, `volCcy` in ETH.<br>REST: `GET /api/v5/market/history-candles` covers recent years via pagination. | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Historical Funding Rate Coverage** | Portal: Advertised from Mar 2022 (Module 3, daily/monthly archives).<br>REST: `GET /api/v5/public/funding-rate-history` covers last 3 months only (max 400 records/req). Returns nominal `fundingRate` and actual `realizedRate`. | Portal: `AVAILABLE_UNMEASURED`<br>REST: `AVAILABLE_VERIFIED` |
| **Open Interest (OI) Coverage** | Portal: **`NOT_PUBLISHED`** (0 bulk archive files in portal).<br>REST Public Data: `GET /api/v5/public/open-interest` returns **current snapshot only** (`oi` in contracts, `oiCcy` in ETH, `oiUsd` in USD).<br>REST Trading Statistics: `GET /api/v5/rubik/stat/contracts/open-interest-history` provides periodic history (5m, 1H, 1D), paginated by 100 rows. Multi-year historical depth unverified. | Portal: `NOT_PUBLISHED`<br>REST Snapshot: `AVAILABLE_VERIFIED`<br>Rubik History: `COVERAGE_UNKNOWN` |
| **Order Book L2 Depth & History** | Portal: Module 4 (400-level) from Mar 2023; Module 5 (5,000-level) from Nov 1, 2025.<br>REST: `GET /api/v5/market/books?instId=ETH-USDT-SWAP&sz=400` (snapshot only).<br>WebSocket: `books` and `books-l2-tbt` (incremental deltas; checksum deprecated/0; sequence continuity via `seqId`). | Portal: `AVAILABLE_UNMEASURED`<br>REST/WS: `AVAILABLE_VERIFIED` |
| **Timestamp Semantics** | `ts`, `fundingTime`, `createdtime` in Unix ms. Exchange match/settlement time. UTC daily partitions. | `AVAILABLE_VERIFIED` |
| **Legal Rights Status** | Internal personal research and own-account execution permitted (§9.2, §9.3(d)). Commercial redistribution and external AI training prohibited (§9.4). **US persons prohibited from derivatives/SWAP trading and SWAP data integration** under OKX ToS §2 and §3.6. | `RIGHTS_RESTRICTED_DERIVATIVES` |

---

## 4. Technical, Clock, and Point-in-Time (PIT) Gap Analysis

### 4.1 Archive Downloads vs. REST Endpoints

1. **History Span Disparity:**
   - REST endpoints for trade ticks (`/api/v5/market/history-trades`) and funding rates (`/api/v5/public/funding-rate-history`) strictly retain **only the last 3 months** of historical records.
   - Long-range multi-year backfilling requires bulk archive downloads via `/api/v5/public/market-data-history` or the Historical Data Portal.
2. **Publication Delays (T-2 / T-3):**
   - Bulk daily archives are generated with batch lag: daily trades and candlesticks become available at **T-2** (2 calendar days after session close); order books become available at **T-3** (3 calendar days after session close).
   - Monthly archives become available only after the 2nd day of the subsequent calendar month.
   - Therefore, historical archives cannot serve as low-latency forward simulation without a 48-to-72 hour lag buffer.

### 4.2 Point-in-Time (PIT) Provenance and Causal Clock Gaps

1. **Exchange Publication Time vs. Local First-Known-At:**
   - All OKX historical data timestamps (`ts`, `createdtime`, `fundingTime`) record the exchange matching engine's timestamp in milliseconds.
   - None of the archived files record the contemporaneous network arrival timestamp (`receiver_first_known_at`) at an off-exchange client node.
   - Retrospective tape timestamps create lookahead risk if backtest engines assume instant off-exchange visibility at `ts`.
2. **Order Book L2 Depth Discontinuity:**
   - On November 1, 2025, OKX introduced Module 5 (5,000-level order book snapshots/deltas).
   - Between March 2023 and October 2025, only Module 4 (400-level) was published.
   - Prior to March 2023, high-resolution order books were not archived on the portal.
   - **Crucial Rule:** Earlier 400-level records must NOT be relabeled or treated as equivalent to 5,000-level L2 depth.
3. **Deprecated Checksum Field in L2 Feeds:**
   - OKX has officially deprecated the CRC32 `checksum` field in WebSocket order book feeds; the field is hardcoded to return `0`.
   - Data integrity and missing packet detection must rely entirely on `seqId` and `prevSeqId` continuity checks.
4. **Funding Rate Cash Ledger Gap:**
   - The funding rate history API and archive provide only nominal `fundingRate`, actual `realizedRate`, and settlement timestamp `fundingTime`.
   - This records the rate index, **not an individual trading account's actual cash ledger** (actual cash debit/credit depends on exact position size held at the transition millisecond, margin tier, and fee tier).
5. **Open Interest (OI) Provenance Gap:**
   - Tick-level or event-by-event historical Open Interest is **not published** in OKX official download archives.
   - `GET /api/v5/public/open-interest` is strictly a current snapshot.
   - `GET /api/v5/rubik/stat/contracts/open-interest-history` provides only aggregated periodic intervals (5m, 1H, 1D), introducing lookahead ambiguity regarding whether the timestamp represents the start or end of the aggregation bucket.

### 4.3 Venue and Product Isolation

1. **No Venue Substitution:** OKX `BTC-USDT` / `BTC-USDT-SWAP` data must remain strictly isolated from Binance `BTCUSDT` Spot and USD-M Perpetual datasets. OKX OI and volume must never be substituted to patch Binance data gaps.
2. **Contract Multiplier Awareness:** In OKX perpetual swaps, order size `sz` represents contract count, where 1 contract of `BTC-USDT-SWAP` = `0.01` BTC and 1 contract of `ETH-USDT-SWAP` = `0.1` ETH. Failing to apply `ctVal` causes a 100x or 10x error in economic exposure.

---

## 5. Potential Future Single-File Pilot Menu (Hypothetical Menu for Wave 2 Task E)

In accordance with the prompt instructions:
- **NO DATA DOWNLOAD HAS BEEN PERFORMED.**
- No fabricated dates, synthetic checksums, or unmeasured byte counts are invented.
- The following menu defines the exact parameter template for any future bounded intake pilot under Task E, subject to explicit owner and Controller authorization:

| Candidate ID | File Family / Module | Symbol / Instrument | Legal Right Basis | Tested Publisher Checksum | Estimated Storage Class | Pilot Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `PILOT-OKX-CANDLE-BTC` | Module 2: `CANDLESTICK` (1m OHLCV) | `BTC-USDT` (SPOT) | OKX API Agreement §9.2 / §9.4 (Personal Internal DEV QC) | `UNTESTED_NO_CHECKSUM_INVENTED` | Tier A CORE (`ESTIMATED_UNMEASURED`, ~1–5 MiB/day compressed) | `UNDOWNLOADED_PROVISIONAL` |
| `PILOT-OKX-CANDLE-BTCSWAP`| Module 2: `CANDLESTICK` (1m OHLCV) | `BTC-USDT-SWAP` | OKX API Agreement §9.2 / §9.4 (Subject to non-US jurisdiction check) | `UNTESTED_NO_CHECKSUM_INVENTED` | Tier A CORE (`ESTIMATED_UNMEASURED`, ~1–5 MiB/day compressed) | `UNDOWNLOADED_PROVISIONAL` |
| `PILOT-OKX-FUNDING-BTCSWAP`| Module 3: `FUNDING_RATES` (8h Settlement) | `BTC-USDT-SWAP` | OKX API Agreement §9.2 / §9.4 (Subject to non-US jurisdiction check) | `UNTESTED_NO_CHECKSUM_INVENTED` | Tier A CORE (`ESTIMATED_UNMEASURED`, <100 KiB/day compressed) | `UNDOWNLOADED_PROVISIONAL` |
| `PILOT-OKX-TRADES-BTC` | Module 1: `TRADE_HISTORY` (Tick Trades) | `BTC-USDT` (SPOT) | OKX API Agreement §9.2 / §9.4 (Personal Internal DEV QC) | `UNTESTED_NO_CHECKSUM_INVENTED` | Tier B TRADES (`ESTIMATED_UNMEASURED`, ~50–300 MiB/day compressed) | `UNDOWNLOADED_PROVISIONAL` |
| `PILOT-OKX-L2-BTC` | Module 4: `ORDER_BOOK_400` (400-level L2) | `BTC-USDT` (SPOT) | OKX API Agreement §9.2 / §9.4 (Personal Internal DEV QC) | `UNTESTED_NO_CHECKSUM_INVENTED` | Tier C L2 (`ESTIMATED_UNMEASURED`, ~1–5 GiB/day compressed) | `UNDOWNLOADED_PROVISIONAL` |

*Note: All pilot candidates remain strictly gated. No URL was probed with HTTP GET or HEAD during this Wave 1 audit.*

---

## 6. Storage Classes and Lower-Bound Impact (Input to Task C)

To inform the parallel storage architecture task (`V06_DATA_C_STORAGE_ARCHITECTURE_GEMINI_R1`), the OKX dataset families map into three distinct storage capacity tiers:

1. **Tier A CORE (1m Klines, Funding Rates, Rubik Periodic OI):**
   - *Characteristics:* Low frequency, highly compressible tabular data.
   - *Estimated Footprint:* Tens of megabytes per instrument per year in Parquet + Zstandard format.
   - *Feasibility:* Highly feasible within existing storage margins; minimal disk pressure.
2. **Tier B TRADES (Tick-by-Tick Executed Trades):**
   - *Characteristics:* High frequency event stream containing every executed trade ID, price, size, and side.
   - *Estimated Footprint:* Estimated between 50 MiB to 300 MiB per active day per instrument (compressed); roughly 20 GiB to 100 GiB per pair-year.
   - *Feasibility:* Feasible for primary pairs (BTC/ETH Spot + Perp), but requires strict deduplication and parquet partitioning.
3. **Tier C L2 ORDER BOOK (High-Resolution 400-Level / 5,000-Level Snapshots & Deltas):**
   - *Characteristics:* Extremely high volume message stream.
   - *Estimated Footprint:* 1 GiB to 10+ GiB per day per active instrument (compressed); multi-terabyte scale across multiple instruments over multi-year periods.
   - *Impact on Storage Plan:* Consuming Tier C for OKX would rapidly exceed available disk reserves (~724 GiB provisional free space).
   - *Architectural Recommendation to Task C:* **DEFER OKX Tier C L2 completely.** Restrict Wave 2 / Task E intake to Tier A CORE (and bounded Tier B trade samples if specifically required).

---

## 7. Gating and Conditional Prerequisites for Task E

The downstream intake task **`V06_DATA_E_OKX_BOUNDED_INTAKE_CONDITIONAL_R1`** is currently in state:
```
PREPARED_CONDITIONAL / NOT_AUTHORIZED_TO_EXECUTE
```

Execution of Task E is strictly prohibited until ALL of the following gates are satisfied:
1. **Upstream Frozen Deliverables:**
   - Controller verifies and freezes Task B report author commit (`<B_AUTHOR_COMMIT_SHA>`).
   - Task C storage architecture publishes verified schema and capacity boundary (`<C_AUTHOR_COMMIT_SHA>`).
2. **Legal & Jurisdictional Clearance:**
   - Confirmation that data consumer operates strictly within personal non-commercial scope (§9.2, §9.3(d)).
   - Formal exclusion of US persons from derivatives/SWAP data capture, or restriction of intake to Spot pairs (`BTC-USDT`, `ETH-USDT`).
3. **Explicit Scope Authorization:**
   - Controller/Owner must specify the exact dates (DEV dates only, e.g. from previously exposed non-OOS periods), exact symbols, and hard byte budget (< USD 20 spend, 0 archive download fees).
4. **Isolated Working Environment:**
   - Designated isolated workspace outside the repository. Zero impact on active R10-D1 or master repository paths.

---

## 8. Preserved Governance Gates and Terminal Disposition

This feasibility audit maintains all existing project governance barriers in full force:
- **`R9_L1_PAUSE_NEW_ALPHA_RESEARCH_PENDING_EXTERNAL_SOURCE_EVIDENCE`**: Unchanged; no new alpha research or backtesting authorized.
- **`SOURCE_NOT_ADMITTED`**: OKX official data is evaluated for feasibility only; no venue data is admitted to production pipelines.
- **`PIT_UNKNOWN`**: Historical receipt time provenance unproven for archived exchange tapes.
- **`G2_ALPHA_NO_GO`**: Unchanged.
- **`TESTNET_NO_GO / LIVE_NO_GO`**: Unchanged; no live trading or testnet interaction.

**Terminal Disposition:**
```
B_DOCUMENTARY_READY_WITH_LIMITS
```
The documentary investigation of OKX official sources, API schemas, product coverage, and legal rights is fully complete. Critical technical and legal limits have been established and documented without consuming budget or probing market data.

---

## 9. Publication and Execution Integrity Receipt

- **Author Session:** Gemini NORMAL local session
- **Isolated Branch:** `docs/v06-data-b-okx-source-feasibility-r1`
- **Parent Commit:** `ade4df19872122686432cd955d8f139f16069449`
- **Deliverable Path:** `docs/project/V06_DATA_B_OKX_SOURCE_RIGHTS_AND_COVERAGE_R1.md` (ADD ONLY, zero other modifications)
- **Local Quality Assurance Verification:**
  - `mypy`: **PASS** (`Success: no issues found in 104 source files`)
  - `python -m compileall -q src skill-template/scripts`: **PASS** (Zero compilation errors)
  - `pytest -q`: **PASS** (`1189 passed, 9 warnings in 173.91s`)
  - `ruff check .`: Fails on pre-existing `evidence/v0.5/h41` repository files (6 legacy unused import/exec errors, documented in Task A parallel CI run `38781376690`), while all newly authored documentation complies fully with documentation standards.
