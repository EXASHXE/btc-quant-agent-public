# v0.6 P2 S2 Source Location, Role, Rights, and Clock Matrix

**Document ID:** `V06_P2_S2_SOURCE_LOCATION_ROLE_RIGHTS_AND_CLOCK_MATRIX_R1`
**Task ID:** `V06_P2_S2_GEMINI_LONG_SOURCE_CONTRACT_AND_SYNTHETIC_CAPABILITY_GATE_R1`
**Role:** Gemini Primary Engineering Implementer (B-line)
**Lineage & Authorities:**
- **Controller Dispatch SHA:** `b176f4361cd97d1d89c3e25173b2c72a6af93ec4`
- **Code Start SHA:** `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`
- **Physical Metadata Stat Receipt SHA:** `c6823dbc46249cac43aa10400aacbbe9f4542410`
- **Terminated Verifier Counterexample SHA:** `4a1fcc2871708f0e9e3a7c40036ecaab39ba99b8`
- **Controller Termination Adjudication SHA:** `ca0b6ea62613e6981b6f818f37f45be8c1d74901`
- **Controller Prospective Admission Design SHA:** `519b2e9ba2ca847e76ad9c0a7fbafcec5fcda158`
- **Owner WSL Data Root (Immutable):** `/root/workspace/project/Quant-agent/data`

---

## 1. Executive Summary & Hard Boundary Commitments

This document establishes the machine-readable data source map, role classifications, rights status, and point-in-time (PIT) clock semantics for the proposed future data qualification pipeline on the B-line.

In strict compliance with Controller Dispatch `b176f4361cd97d1d89c3e25173b2c72a6af93ec4`:
1. **Zero Real Market Reads (HARD NO-READ):** No system call (`lstat`, `open`, `read`, `scandir`) has been or will be executed against the owner's physical WSL data root (`/root/workspace/project/Quant-agent/data`). No raw Parquet footers have been parsed, no raw CSV lines read, no hashes computed on physical market files, and no market downloads conducted.
2. **Acceptance of Frozen Metadata Evidence Only:** All physical file existence and size assertions derive strictly and exclusively from the immutable executor stat receipt `c6823dbc46249cac43aa10400aacbbe9f4542410`.
3. **Rejection of Counterexample Locator (`4a1fcc2871`):** The terminated verifier is treated strictly as an architectural counterexample (F01 CLI custom root override bypass; F02 uncounted direct stat calls and cache bypass). No code, imports, or patches from that locator are reused.
4. **Synthetic Execution Isolation:** All executable capability gates and security tests operate exclusively on synthetic in-memory fixtures and temporary scratch structures. Passing synthetic simulation does **NOT** authorize physical market data access.

---

## 2. Authoritative Data Source Map by Role and Certainty Tier

The table below catalogs every known data location under the owner root, categorized by evidence certainty tiers:
- `OWNER_DECLARED`: Tree topology declared by repository owner.
- `PHYSICAL_METADATA_EXECUTOR_OBSERVED`: Verified regular file/directory and size via immutable receipt `c6823dbc46249cac43aa10400aacbbe9f4542410`.
- `UNVERIFIED_RIGHTS`: Legal and terms-of-service usage rights not yet granted or cleared.
- `UNKNOWN_FILE_CONTINUITY`: Internal schema, row continuity, timestamps, and ordering uninspected and unproven.
- `PROTECTED_DO_NOT_TOUCH`: Strictly excluded holdout evaluation partitions.

| Source ID | Candidate Relative Path | Semantic Role | Evidence Certainty | Size (Bytes) | Clock Definition & PIT Availability | Current Admission Status |
|---|---|---|---|---|---|---|
| `btc_perp_1m_2021_03` | `research/BTCUSDT/1m/year=2021/month=03/data.parquet` | BTC Perp 1m Kline | `PHYSICAL_METADATA_OBSERVED`, `UNVERIFIED_RIGHTS`, `UNKNOWN_CONTINUITY` | 2,756,024 | UTC minute open $[m, m+60\text{s})$, available at $\ge m+60\text{s}$ | **METADATA LOCATED; BODY BLOCKED** |
| `btc_perp_1m_2021_04` | `research/BTCUSDT/1m/year=2021/month=04/data.parquet` | BTC Perp 1m Kline | `PHYSICAL_METADATA_OBSERVED`, `UNVERIFIED_RIGHTS`, `UNKNOWN_CONTINUITY` | 2,621,313 | UTC minute open $[m, m+60\text{s})$, available at $\ge m+60\text{s}$ | **METADATA LOCATED; BODY BLOCKED** |
| `btc_perp_1m_2023_03` | `research/BTCUSDT/1m/year=2023/month=03/data.parquet` | BTC Perp 1m Kline | `PHYSICAL_METADATA_OBSERVED`, `UNVERIFIED_RIGHTS`, `UNKNOWN_CONTINUITY` | 2,415,597 | UTC minute open $[m, m+60\text{s})$, available at $\ge m+60\text{s}$ | **METADATA LOCATED; BODY BLOCKED** |
| `btc_perp_1m_2023_04` | `research/BTCUSDT/1m/year=2023/month=04/data.parquet` | BTC Perp 1m Kline | `PHYSICAL_METADATA_OBSERVED`, `UNVERIFIED_RIGHTS`, `UNKNOWN_CONTINUITY` | 2,201,521 | UTC minute open $[m, m+60\text{s})$, available at $\ge m+60\text{s}$ | **METADATA LOCATED; BODY BLOCKED** |
| `btc_perp_1m_2025_03` | `research/BTCUSDT/1m/year=2025/month=03/data.parquet` | BTC Perp 1m Kline | `PHYSICAL_METADATA_OBSERVED`, `UNVERIFIED_RIGHTS`, `UNKNOWN_CONTINUITY` | 2,352,476 | UTC minute open $[m, m+60\text{s})$, available at $\ge m+60\text{s}$ | **METADATA LOCATED; BODY BLOCKED** |
| `btc_perp_1m_2025_04` | `research/BTCUSDT/1m/year=2025/month=04/data.parquet` | BTC Perp 1m Kline | `PHYSICAL_METADATA_OBSERVED`, `UNVERIFIED_RIGHTS`, `UNKNOWN_CONTINUITY` | 2,329,220 | UTC minute open $[m, m+60\text{s})$, available at $\ge m+60\text{s}$ | **METADATA LOCATED; BODY BLOCKED** |
| `btc_perp_manifest` | `research/BTCUSDT/data_manifest.json` | Manifest Metadata | `PHYSICAL_METADATA_OBSERVED`, `UNVERIFIED_RIGHTS` | 45,234 | Static partition manifest | **METADATA LOCATED; BODY UNPARSED** |
| `btc_perp_funding_events` | `research/BTCUSDT/funding_events.csv` | Funding Rate Events | `PHYSICAL_METADATA_OBSERVED`, `UNVERIFIED_RIGHTS`, `UNKNOWN_CONTINUITY` | 219,066 | Settlement clock vs known-at clock unverified | **METADATA LOCATED; CLOCK UNPROVEN** |
| `btc_perp_raw_klines` | `research/BTCUSDT/raw/klines` | Raw Kline Container | `PHYSICAL_METADATA_OBSERVED` | 4,096 (dir) | Raw zip ingestion timestamps | **CONTAINER OBSERVED; DESCENT BLOCKED** |
| `btc_perp_raw_mark` | `research/BTCUSDT/raw/mark_price` | Raw Mark Container | `PHYSICAL_METADATA_OBSERVED` | 4,096 (dir) | Exchange mark index calculation clock | **CONTAINER OBSERVED; 1M PIT UNPROVEN** |
| `btc_perp_raw_funding` | `research/BTCUSDT/raw/funding` | Raw Funding Container | `PHYSICAL_METADATA_OBSERVED` | 4,096 (dir) | Settlement cycle archive | **CONTAINER OBSERVED; DESCENT BLOCKED** |
| `btc_spot_manifest` | `research/BTCUSDT_SPOT/data_manifest.json` | Spot Manifest Metadata | `PHYSICAL_METADATA_OBSERVED` | 19,855 | Static spot manifest | **SPOT IS NOT PERPETUAL; BLOCKED** |
| `btc_spot_1m` | `research/BTCUSDT_SPOT/1m` | Spot Kline Container | `PHYSICAL_METADATA_OBSERVED` | 4,096 (dir) | Cash spot trading clock | **SPOT IS NOT PERPETUAL; BLOCKED** |
| `eth_hourly_aux` | `research/cross_asset_1h/ETHUSDT.parquet` | Cross-Asset Hourly | `PHYSICAL_METADATA_OBSERVED` | 3,391,374 | 1h macro clock (NOT 1m perp execution) | **HOURLY NOT MINUTE; BLOCKED** |
| `eth_basket_manifest` | `research/cross_asset_1h/basket_manifest.json` | Basket Manifest | `PHYSICAL_METADATA_OBSERVED` | 3,674 | Static basket manifest | **HOURLY NOT MINUTE; BLOCKED** |
| `legacy_v0319_derivatives`| `research/v0.3.19_official_derivatives/hourly_inputs.parquet` | Legacy v0.3.19 Archive | `PHYSICAL_METADATA_OBSERVED` | 2,058,958 | Historical v0.3.19 hourly feature clock | **HISTORICAL ARCHIVE ONLY; BLOCKED** |
| `unproven_eth_sol_1m` | `research/{ETHUSDT,SOLUSDT}/1m/**` | Multi-asset 1m Perp | `UNKNOWN_FILE_CONTINUITY` | N/A (None) | Unproven | **ABSENT; STRICT FAIL-CLOSED** |
| `protected_2026_holdout`| `research/BTCUSDT/1m/year=2026/**` | Evaluation Holdout | `PROTECTED_DO_NOT_TOUCH` | Sealed | $[2026\text{-}02\text{-}01, 2026\text{-}08\text{-}01)$ | **PERMANENT ZERO ACCESS** |
| `protected_forward` | `data/forward/**` | Forward Paper Trade | `PROTECTED_DO_NOT_TOUCH` | Sealed | Forward operational ledger | **PERMANENT ZERO ACCESS** |
| `protected_h39` | `data/research/h39_validation/**` | Validation Holdout | `PROTECTED_DO_NOT_TOUCH` | Sealed | Out-of-sample test gates | **PERMANENT ZERO ACCESS** |

---

## 3. Disambiguation of Critical Source Classes

### 3.1. BTC Perpetual 1m Trade Klines vs. True Continuous 1m Mark Price
- **Trade Kline Series (`1m/year=YYYY/month=MM/data.parquet`):**
  Represents completed trade transactions aggregated over the 60-second window $[m, m+60000\text{ms})$. The closing trade price is sensitive to aggressive liquidity taker trades.
- **Mark Price Series (`raw/mark_price`):**
  Represents the index-derived fair price used by the exchange clearinghouse for margin, liquidation, and funding calculations.
- **Critical PIT Gap:**
  The physical presence of the `raw/mark_price` parent directory does **NOT** prove that continuous 1-minute Mark Price bars exist. If `raw/mark_price` contains only daily summaries (e.g. 9 daily files as indicated in owner notes), attempting to construct 1m Mark prices via interpolation or forward-fill is **strictly prohibited**. In the absence of proven continuous 1m Mark data, all liquidations and mark-to-market calculations must fail closed.

### 3.2. Funding Events Timing: `known_at` vs. `settlement_at`
- **Settlement Timestamp (`settlement_at`):**
  The exchange clock timestamp when funding payments are debited/credited (typically 00:00, 08:00, 16:00 UTC).
- **Publication Timestamp (`known_at`):**
  The precise point in time when the exchange API publishes the predicted or locked funding rate for the upcoming interval.
- **Causality Requirement:**
  Using `settlement_at` as the availability timestamp causes lookahead bias. The funding rate is known prior to settlement. Conversely, treating future funding rates as known before exchange broadcast violates PIT causality. The `funding_events.csv` file presence proves neither clock; explicit timestamp proof is required prior to economic admission.

### 3.3. Spot vs. Perpetual Distinction
- `BTCUSDT_SPOT` represents an asset-for-cash exchange with immediate physical delivery and zero funding rate cashflows.
- `BTCUSDT` Perpetual futures incorporate leverage, basis spread, margin collateralization, and periodic funding payments.
- **Policy Enforcement:** Spot data cannot be substituted for perpetual futures data under any circumstance.

### 3.4. ETH/SOL 1m Perp Absence & Single-Asset Concentration
- The original strategy protocol required $\le 60\%$ single-asset exposure for positive multi-asset strategy evaluation.
- Neither ETH nor SOL 1m perpetual files have been located or verified on disk.
- Evaluating a BTC-only strategy results in $100\%$ single-asset concentration, which fails the original three-asset positive screen. Any future BTC-only research must be prospectively registered as a **bounded diagnostic amendment**, not a silent revision of the original three-asset criteria.

---

## 4. Expected Future Schema Specifications (Non-Asserted Design)

For future explicit read grants (Level L2 schema and Level L3 quality QA), the expected data model for the 6 candidate month Parquet files is defined as follows:

```text
Field Name               Expected Type    Semantic Definition
---------------------------------------------------------------------------------------------------
event_ts                 int64 (ms UTC)   Start of minute bar [m, m+60000ms)
known_at                 int64 (ms UTC)   Earliest exchange publication timestamp (>= m+60000ms)
available_at             int64 (ms UTC)   Local ingestion availability timestamp (>= known_at)
open                     float64          Price of first trade within minute window
high                     float64          Highest trade price within minute window
low                      float64          Lowest trade price within minute window
close                    float64          Price of last trade within minute window
volume                   float64          Total base asset (BTC) volume executed
quote_volume             float64          Total quote asset (USDT) volume executed
count                    int64            Total number of executed trade fills
taker_buy_volume         float64          Volume executed by market buy orders
taker_buy_quote_volume   float64          Quote volume executed by market buy orders
```
*Note: This specification represents the contract design model. Actual presence of these columns will only be evaluated if and when an explicit Level L2 grant is issued by the Controller.*

---

## 5. Proposed Owner Data Grant and Rights Questionnaire

To transition from Level S2 (design only) to Level S3 (restricted QA), the owner must provide written clearance on the following five questions:

1. **License & Terms of Use Clearance:**
   *Question:* Under what specific commercial or research license was the historical Binance perpetual data extracted and stored, and does that license permit automated backtesting and algorithm verification without violating API terms?
   *Status:* `PROPOSED_PENDING_OWNER_RESPONSE`

2. **VIP Fee Tier Schedule:**
   *Question:* What historical maker/taker fee tier schedule (e.g. VIP 0: 0.02% maker / 0.05% taker, vs. higher VIP tiers with BUSD/BNB fee discounts) should be used as the mandatory execution friction model?
   *Status:* `PROPOSED_PENDING_OWNER_RESPONSE`

3. **True Continuous 1m Mark Price Provenance:**
   *Question:* Does `raw/mark_price` contain genuine uninterrupted 1-minute sampled Mark Price records matching the trade Kline timestamps, or is it composed solely of daily/sparse archives?
   *Status:* `PROPOSED_PENDING_OWNER_RESPONSE`

4. **Funding Rate Causality Clocks:**
   *Question:* Does `funding_events.csv` record the point-in-time publication timestamp (`known_at`) or merely the retrospective settlement timestamp (`settlement_at`)?
   *Status:* `PROPOSED_PENDING_OWNER_RESPONSE`

5. **Staged Reader Capability Grant Scope:**
   *Question:* Will the owner issue an explicit capability token authorizing Level L2 (Parquet footer metadata only, $\le 64\text{ KB}$) or Level L3 (bounded timestamp QA sample, $\le 10\text{ MB}$), or does the owner intend to maintain a full read embargo?
   *Status:* `PROPOSED_PENDING_OWNER_RESPONSE`
