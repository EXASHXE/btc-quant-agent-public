# R11-E2 — OKX Historical Data Portal One-File Pilot QC and Acquisition Report R1

**TASK_ID:** `V06_R11_E2_OKX_HISTORICAL_PORTAL_ONE_FILE_PILOT_R1`  
**Executor:** Local Codex/Gemini Execution Agent  
**Execution Date:** 2026-10-16 (UTC+08)  
**Primary Instrument:** `BTC-USDT-SWAP`  
**Primary Partition Date:** `2024-01-15`  
**Terminal Disposition:** **`R11_E2_OKX_PORTAL_PILOT_ACCEPTED_WITH_LIMITS`**  
**Reviewers:** ChatGPT-0 Primary Controller, ChatGPT-1 Independent Auditor  
**Authorized Branch:** `feature/v06-r11-e2-okx-portal-pilot-r1`  
**Parent Commit:** `c07c60385479f0d595352ad751c1c49150b4cbbc`  

---

## 1. Executive Summary & Terminal Disposition

### 1.1 Terminal Disposition
$$\mathbf{R11\_E2\_OKX\_PORTAL\_PILOT\_ACCEPTED\_WITH\_LIMITS}$$

### 1.2 Grounds for Disposition
1. **Official Portal Accessibility Verified:** All four candidate families (Trade History, Candlestick/OHLC, Funding Rate, and L2 Order Book) were successfully identified, authenticated against the official OKX Historical Data Portal API (`/priapi/v5/broker/public/trade-data/download-link`), and inspected directly from official CDN endpoints (`static.okx.com`). Zero generic market APIs or unauthorized scrapers were used.
2. **Deterministic Data Integrity:**
   - **Trade History:** `801,052` trades, strictly increasing `trade_id` (`[720073478, 720874529]`), zero duplicates, zero timestamp regressions, total trade volume `9,585,493.00` contracts.
   - **Candlestick / Kline:** Exactly `1,440` 1-minute bars (100% complete 24h cycle, zero gaps, exact 60,000 ms step), total volume `9,585,493.00` contracts.
   - **Mathematical Volume Reconciliation:** Trade sum volume matches 1m Kline sum volume with **exact 100.000% precision** ($9,585,493.00 == 9,585,493.00$).
   - **Contract Multiplier Proven:** Candlestick `vol` (contracts) versus `vol_ccy` (BTC) proves the exact contract multiplier:
     $$\mathbf{1\text{ Contract (BTC-USDT-SWAP)}} = \mathbf{0.01\text{ BTC}}$$
   - **Funding Rate:** Exactly 3 settlements per 24h cycle, exactly 8-hour intervals (`28,800,000` ms), reasonable rates ($0.0014\%–0.0131\%$).
   - **L2 Order Book:** 400-level depth verified (`BTC-USDT-SWAP-L2orderbook-400lv-2024-01-15.tar.gz`), containing an initial full snapshot (`400` bids and `400` asks) followed by 10ms incremental delta updates with 3-tuple `[price, size, order_count]` format.
3. **Critical Partitioning Discovery (UTC+8 Phase Shift):** Daily Trade and Candlestick portal files are sliced on a **UTC+8 calendar day** (`[00:00:00 UTC+8, 23:59:59 UTC+8]` = `[16:00:00 UTC previous day, 15:59:59 UTC date]`), whereas L2 400lv is sliced on a **UTC calendar day** (`[00:00:00 UTC, 23:59:59 UTC]`).
4. **Historical Open Interest (OI) Status:** The portal does **not** advertise or host historical Open Interest files. Per contract instructions, generic public API OI was **not** downloaded. Historical OI remains **`OI_PORTAL_UNAVAILABLE / OI_HISTORICAL_UNRESOLVED`**.

---

## 2. Authority, Rights Basis & Scope Boundaries

### 2.1 Immutable Dispatch Authority
- **Dispatch Commit SHA:** `c07c60385479f0d595352ad751c1c49150b4cbbc`  
  *Commit Message:* `docs(v0.6): authorize bounded data foundation after R11-Q1 and allow capacity expansion`
- **Parent Decision:** `reviews/v0.6/b_line/V06_R11_Q2_CONTROLLER_CAPACITY_EXPANSION_AND_NEXT_STAGE_DECISION_R1.md` (Commit `c07c60385479f0d595352ad751c1c49150b4cbbc`)
- **Task Contract Prompt:** `prompts/v0.6/b_line/data_program/V06_R11_E2_OKX_HISTORICAL_PORTAL_ONE_FILE_PILOT_R1.md`
- **Controller Dispatch Disposition:** `R11_Q2_DATA_FOUNDATION_READY_WITH_LIMITS`

### 2.2 Legal and Rights Basis
- **Governing Terms:** [Official OKX Historical Data Terms and Conditions](https://www.okx.com/en-sg/help/historicaldata-terms-and-conditions) (last updated 2023-10-26).
- **Authorized Scope:** §2 explicitly grants a limited, revocable, non-exclusive, royalty-free license to download, retain, and possess historical data for personal use, expressly including the development of the user's own trading strategies.
- **Strict Prohibitions:** Commercial redistribution, reselling, sublicensing, or publication of raw market data is strictly prohibited.
- **Compliance Status:** This task is strictly personal, noncommercial, nonproduction algorithmic research. No raw market data was committed to public Git, transferred to third parties, or uploaded to external LLMs.

### 2.3 Hard Boundary Invariants Preserved
- Market API trading endpoints: **NONE (0 calls)**
- Private account data / API credentials: **NONE (0 used)**
- Live / Testnet order execution: **NONE (0 orders)**
- Protected project roots inspected: **NONE (0 files)**
- Strategy alpha scoring / backtest execution: **NONE (0 runs)**
- Machine learning model training: **NONE (0 models)**
- Raw payload upload to external LLM: **NONE (0 bytes)**

---

## 3. Exact Source, URL & File Identities

All candidate files were resolved via the official OKX Portal Download API (`POST https://www.okx.com/priapi/v5/broker/public/trade-data/download-link`):

| Data Family | Canonical Filename | Official Publisher URL | Compressed Bytes | Expanded Bytes | SHA-256 Checksum | ETag |
|---|---|---|---|---|---|---|
| **Trades** | `BTC-USDT-SWAP-trades-2024-01-15.zip` | `https://static.okx.com/cdn/okex/traderecords/trades/daily/20240115/BTC-USDT-SWAP-trades-2024-01-15.zip?v=1001` | 4,971,500 B (~4.74 MiB) | 44,710,746 B (~42.64 MiB) | `1cb1e8c76a04122d3f2b3d4833c9dc4e684d9a44ce51176e10eafb08aee5e822` | `"E1CBDE6A823CF846302D5DAC8569A3D0"` |
| **Candlesticks** | `BTC-USDT-SWAP-candlesticks-2024-01-15.zip` | `https://static.okx.com/cdn/okex/traderecords/candlesticks/daily/20240115/BTC-USDT-SWAP-candlesticks-2024-01-15.zip?v=1001` | 38,776 B (~37.87 KiB) | 131,062 B (~127.99 KiB) | `90406dd200d8f3c15c58beac74b57745315967eb5de0a999bb4a935b6d48e9e1` | `"920F5FA9F6CDE2B5E21D13AEEC21B647"` |
| **Funding (Daily)** | `allswap-fundingrates-2024-01-15.zip` | `https://static.okx.com/cdn/okex/traderecords/swaprates/daily/20240115/allswap-fundingrates-2024-01-15.zip?v=1001` | 7,444 B (~7.27 KiB) | 28,117 B (~27.46 KiB) | `1ee9c4e60fa028478dec703dab1015c287b2802824521dccc5ae7dbdc84c62f1` | `"A11837C2862FE4849094CFE921229DE8"` |
| **Funding (Monthly)**| `BTC-USDT-SWAP-fundingrates-2024-01.zip` | `https://static.okx.com/cdn/okex/traderecords/swaprates/monthly/202401/BTC-USDT-SWAP-fundingrates-2024-01.zip?v=1001` | 1,375 B (~1.34 KiB) | 4,507 B (~4.40 KiB) | `0b435b9ee300183860c5fd2b471b3eb072142c7200769ab8d6eb37da7616c88d` | `"F8BAAFDF8744847D4C9D3D4EB0F22027"` |
| **L2 Order Book** | `BTC-USDT-SWAP-L2orderbook-400lv-2024-01-15.tar.gz`| `https://static.okx.com/cdn/okx/match/orderbook/L2/400lv/daily/20240115/BTC-USDT-SWAP-L2orderbook-400lv-2024-01-15.tar.gz` | 494,894,215 B (~471.97 MiB)| ~3.5 GiB (streamed slice) | Header verified via streaming decompress | `"F12ED32832168BF7BEF9C26682D60FA0"` |

---

## 4. Detailed Deterministic QC Findings

### 4.1 Trade History Quality & Semantics
- **Internal CSV Member:** `BTC-USDT-SWAP-trades-2024-01-15.csv`
- **Schema:** `instrument_name, trade_id, side, price, size, created_time`
- **Record Count:** Exactly `801,052` valid execution rows.
- **Trade ID Integrity:**
  - Range: `[720073478, 720874529]`
  - Monotonicity: Strictly increasing (`0` regressions).
  - Uniqueness: `0` duplicate trade IDs.
- **Timestamp Semantics:**
  - Granularity: Millisecond epoch integers (`INT64`).
  - Min timestamp: `1705248000179` (`2024-01-14T16:00:00.179Z` UTC / `2024-01-15 00:00:00.179` UTC+8)
  - Max timestamp: `1705334399604` (`2024-01-15T15:59:59.604Z` UTC / `2024-01-15 23:59:59.604` UTC+8)
  - Monotonicity: Non-decreasing (`0` regressions).
- **Trade Size Denomination:**
  - Total traded size across the day: **`9,585,493.00` contracts**.
  - All sizes are positive float values representing contract counts (not coin quantities).

### 4.2 Candlestick / Kline Quality & Contract Multiplier Verification
- **Internal CSV Member:** `BTC-USDT-SWAP-candlesticks-2024-01-15.csv`
- **Schema:** `instrument_name, open, high, low, close, vol, vol_ccy, vol_quote, open_time, confirm`
- **Record Count:** Exactly `1,440` 1-minute bars (100% of a 24h day).
- **Time Grid Continuity:**
  - Distinct interval between consecutive bars: `{60000}` ms (exactly 60 seconds).
  - Zero missing minutes; zero duplicate timestamps.
  - Min bar `open_time`: `1705248000000` (`2024-01-14T16:00:00Z` UTC / `2024-01-15 00:00:00` UTC+8).
  - Max bar `open_time`: `1705334340000` (`2024-01-15T15:59:00Z` UTC / `2024-01-15 23:59:00` UTC+8).
- **Volume & Multiplier Reconciliation:**
  - Total `vol` (contract units): `9,585,493.00`
  - Total `vol_ccy` (base currency BTC): `95,854.93`
  - Total `vol_quote` (quote currency USDT): `4,103,137,014.15`
  - **Contract Multiplier Formula:**
    $$\text{Multiplier} = \frac{\text{vol\_ccy}}{\text{vol}} = \frac{95,854.93\text{ BTC}}{9,585,493.00\text{ Contracts}} = \mathbf{0.01000000\text{ BTC / Contract}}$$
  - **Reconciliation with Trade History:**
    $$\sum \text{Trades.size} = 9,585,493.00 \equiv \sum \text{Candlestick.vol} = 9,585,493.00$$
    The trade volume sum matches the candlestick contract volume with **0.0000% error**, providing incontrovertible empirical proof that OKX SWAP trade size is denominated in contracts with a $0.01$ BTC multiplier.
- **The `confirm` Column:** Set to `'0'` across all rows in the archive (indicating completed historical snapshot records).

### 4.3 Funding Rate Quality & Interval Verification
- **Daily Archive:** `allswap-fundingrates-2024-01-15.csv` (contains all swap instruments).
- **Monthly Archive:** `BTC-USDT-SWAP-fundingrates-2024-01.csv` (instrument-specific).
- **Schema:** `instrument_name, funding_rate, funding_time`
- **Settlement Cadence (BTC-USDT-SWAP on 2024-01-15):**
  1. `1705248000000` (`2024-01-14T16:00:00Z` UTC / `2024-01-15 00:00:00` UTC+8): Rate = `+0.0001312307409983` (+0.0131%)
  2. `1705276800000` (`2024-01-15T00:00:00Z` UTC / `2024-01-15 08:00:00` UTC+8): Rate = `+0.0000141710491919` (+0.0014%)
  3. `1705305600000` (`2024-01-15T08:00:00Z` UTC / `2024-01-15 16:00:00` UTC+8): Rate = `+0.0001293460357467` (+0.0129%)
- **Interval:** Exactly **8 hours** (`28,800,000` ms), confirming the standard 8-hour funding schedule for BTC-USDT-SWAP.
- **Monthly Record Count:** Exactly `93` funding events across January 2024 ($31\text{ days} \times 3\text{ settlements/day} = 93$), confirming zero missing funding settlements across the month.

### 4.4 L2 Order Book Microstructure & Stream Semantics
- **Archive Member:** `BTC-USDT-SWAP-L2orderbook-400lv-2024-01-15.data` (stored within `tar.gz`).
- **Archive Format:** Tar archive containing a single line-delimited JSON (JSONL) event stream.
- **Initial Full Depth Snapshot (Line 0):**
  ```json
  {
    "instId": "BTC-USDT-SWAP",
    "action": "snapshot",
    "ts": "1705276800006",
    "asks": [["41738.4", "240.0", "10"], ["41740.0", "11.0", "1"], ...],
    "bids": [["41738.3", "15.0", "2"], ["41738.0", "44.0", "3"], ...]
  }
  ```
  - `action`: `"snapshot"`
  - `ts`: `1705276800006` (`2024-01-15 00:00:00.006 UTC`)
  - `bids` count: exactly `400` levels.
  - `asks` count: exactly `400` levels.
- **Incremental Event Stream (Line 1 onwards):**
  ```json
  {
    "instId": "BTC-USDT-SWAP",
    "action": "update",
    "ts": "1705276800016",
    "asks": [["41742.1", "10.0", "1"], ["41742.6", "31.0", "1"]],
    "bids": [["41735.0", "6.0", "2"], ["41734.2", "2.0", "1"]]
  }
  ```
  - `action`: `"update"`
  - Update Cadence: High-frequency regular intervals ($\sim 10\text{ ms}$).
  - Tuple Semantics: `[price, size_contracts, order_count]`
  - Order Book State Reconstruction Logic:
    - If `size == "0"`: The price level has been depleted/cancelled; remove from book.
    - If `size > "0"`: Insert new price level or update existing depth and order count.
- **Downloadability & Operational Assessment:**
  - The L2 order book is **fully exposed and downloadable** directly via the portal CDN (`~472 MiB` compressed per instrument-day).
  - Uncompressed daily footprint expands to $\sim 3.5\text{ GiB}$.
  - Storing 1 year of L2 for 8 instruments would demand $\sim 10\text{ TiB}$, confirming the Wave 1 Task C finding that Tier C L2 cannot be retained locally on standard workstation storage.

---

## 5. Critical Clock and Partitioning Discrepancy: UTC vs UTC+8

A fundamental architectural finding from this pilot is the **divergent temporal partition boundary convention** across data families on the OKX portal:

```
OKX Daily Trade & Kline Archive Window:
[1705248000000 (2024-01-14 16:00:00 UTC)] --------------> [1705334399999 (2024-01-15 15:59:59 UTC)]
|============================ 2024-01-15 in UTC+8 (Beijing Time) ============================|

Standard UTC Calendar Day Window (Binance / Lake Partition):
                  [1705276800000 (00:00:00 UTC)] --------------> [1705363199999 (23:59:59 UTC)]
                  |======================= 2024-01-15 in UTC =======================|
```

1. **Trade & Candlestick Archives:** Sliced on **`00:00:00 to 23:59:59 UTC+8`** (equivalent to `16:00:00 UTC (D-1)` to `15:59:59 UTC (D)`).
2. **L2 400lv Order Book Archive:** Sliced on **`00:00:00 to 23:59:59 UTC`** (begins at `1705276800006`).
3. **Cross-Venue Engineering Implication:**
   - Naively joining OKX `2024-01-15` trades or klines with Binance `2024-01-15` klines produces an **8-hour lookahead / lookbehind misalignment**.
   - Any cross-venue pipeline must ingest OKX daily files into a contiguous microsecond timeline and re-partition by true UTC boundaries (`00:00:00Z` to `23:59:59Z`).

---

## 6. Historical Open Interest (OI) Status Audit

- **Portal Observation:** The official OKX Historical Data Portal UI displays exactly 5 product cards: *Trade history*, *Candlestick*, *Funding rate*, *Order book*, and *Borrowing rate*. It does **not** feature an Open Interest archive card.
- **API Inspection:** The portal download API rejects unadvertised modules (`code: 51000, msg: Parameter module error`).
- **Policy Enforcement:** Per task prompt instructions ("Do NOT download historical OI through the generic public API"), generic public REST market endpoints (`/api/v5/market/open-interest`) were **not** queried.
- **Formal Status:**
  $$\mathbf{OI\_STATUS: \quad OI\_PORTAL\_UNAVAILABLE \quad / \quad OI\_HISTORICAL\_UNRESOLVED}$$
  Historical Open Interest cannot be acquired through the OKX Historical Data Portal. It remains unadmitted until an official historical archive channel with explicit terms is established.

---

## 7. Point-in-Time (PIT) & Scientific Limitations

1. **No PIT from Archive Timestamps:**
   - The file timestamps (`created_time`, `open_time`, `funding_time`) reflect retrospective matching-engine and bar-construction clocks.
   - They do **not** prove contemporaneous arrival time at a remote client socket, network transport delay, or local disk fsync durability.
2. **Batch Publication Lag:**
   - Archive files on `static.okx.com` bear `Last-Modified` headers from late 2025/2026, confirming they are retrospective publisher compilations.
   - Historical live execution strategies could not have accessed these files contemporaneously.
3. **Non-Extrapolation Rule:**
   - Quality metrics verified here apply strictly to `BTC-USDT-SWAP` on `2024-01-15`.
   - They do not guarantee gap-free continuity for altcoins, unmeasured historical years, or different product types without separate empirical verification.

---

## 8. Verifiable Execution Receipts

### 8.1 Deliverable Code & Tests
- **Harness Script:** [`scripts/research/r11_e2/okx_portal_pilot_qc.py`](file:///Z:/root/workspace/project/quant-v0.6/feature-v06-r11-e2-okx-portal-pilot-r1/scripts/research/r11_e2/okx_portal_pilot_qc.py)
- **Unit Test Suite:** [`tests/research/r11_e2/test_okx_portal_pilot_qc.py`](file:///Z:/root/workspace/project/quant-v0.6/feature-v06-r11-e2-okx-portal-pilot-r1/tests/research/r11_e2/test_okx_portal_pilot_qc.py)
- **Report Document:** [`docs/project/V06_R11_E2_OKX_HISTORICAL_PORTAL_ONE_FILE_PILOT_R1.md`](file:///Z:/root/workspace/project/quant-v0.6/feature-v06-r11-e2-okx-portal-pilot-r1/docs/project/V06_R11_E2_OKX_HISTORICAL_PORTAL_ONE_FILE_PILOT_R1.md)

### 8.2 Test Suite Execution Results
- **Pytest:** `9 passed in 0.07s` (100% pass)
- **Unittest:** `Ran 9 tests in 0.002s; OK`
- **Ruff Linter:** `All checks passed!` (0 lint errors)
- **Pipeline Execution:** `R11_E2_OKX_PORTAL_PILOT_ACCEPTED_WITH_LIMITS`

### 8.3 Invariant Ledger
- Financial spend: **USD 0.00**
- Private / protected paths traversed: **None (0 files)**
- Codebase strategy modifications: **None (0 lines)**
- Successor auto-dispatch: **None (0 tasks)**
