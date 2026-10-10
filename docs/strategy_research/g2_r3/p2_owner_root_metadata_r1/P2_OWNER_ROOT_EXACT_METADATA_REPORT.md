# Gemini P2 — Exact Owner-Supplied WSL Data Root Lstat-Only Verification Report (R1)

- **TASK_ID:** `V06_P2_OWNER_EXACT_WSL_ROOT_LSTAT_ONLY_VERIFICATION_R1`
- **ROLE:** Gemini Trusted Read-Only Filesystem Metadata Verifier
- **CONTROLLER_DISPATCH_SHA:** `b6120e2557d26fc822e740b7d889714a8c0124e6` ([Review Document](https://github.com/EXASHXE/btc-quant-agent-public/blob/b6120e2557d26fc822e740b7d889714a8c0124e6/reviews/v0.6/b_line/V06_P2_OWNER_SUPPLIED_EXACT_WSL_DATA_ROOT_BINDING_AND_METADATA_VERIFICATION_DISPATCH_R1.md))
- **PROMPT_PINNED_SHA:** `7becda2c752e1f557e72a9a8e735a698ab1a680f` ([Prompt Document](https://github.com/EXASHXE/btc-quant-agent-public/blob/7becda2c752e1f557e72a9a8e735a698ab1a680f/prompts/v0.6/b_line/V06_P2_GEMINI_OWNER_EXACT_WSL_ROOT_LSTAT_ONLY_VERIFICATION_R1.md))
- **BRANCH_START_SHA:** `1e12d6a6467d3bc39c0deedd97204604ac623f18`
- **EXECUTION_BRANCH:** `feature/v06-bline-p2-owner-exact-root-metadata-r1`
- **OWNER_DECLARED_WSL_DATA_ROOT:** `/root/workspace/project/Quant-agent/data`
- **BTC_PERP_SELECTED_ROOT:** `/root/workspace/project/Quant-agent/data/research/BTCUSDT`
- **TERMINAL_VERDICT:** `P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY`
- **TIMESTAMP_UTC:** `2026-10-10T01:50:48.323193+00:00`

---

## 1. Executive Summary & Terminal Verdict

Under binding Controller dispatch `b6120e2557d26fc822e740b7d889714a8c0124e6`, Gemini conducted an exact, bounded, pure stdlib `lstat`-only verification of the owner-supplied WSL data root `/root/workspace/project/Quant-agent/data`. Unlike earlier exploratory discovery runs across generic candidate paths, this task operated strictly against the user's declared root using a positive allowlist of precisely six non-protected monthly partitions and eleven designated sibling metadata/parent targets.

- **Terminal Verdict:** `P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY`
- **All 6 Approved Non-Protected Month Partitions:** Verified present as regular `.parquet` files (`PRESENT_METADATA_ONLY`).
- **Real Data Body Bytes Read:** Exactly `0` bytes (strict zero-open policy enforced).
- **Ancestor Integrity:** Verified all ancestors from `/root` down to `Quant-agent/data/research/BTCUSDT` are physical directories, non-symlinks.
- **Zero Protected Access:** Zero stats, zero directory listings, and zero accesses to `year=2026`, `forward/`, or `h39_validation/`.
- **P2 Source Admission Status:** **NOT ADMITTED**. Metadata presence confirms physical location only; empirical source admission, P3 preregistration, P4 market body access, and live trading remain strictly blocked pending future Controller decisions.

---

## 2. Execution Caps and Resource Counters

| Metric | Limit / Cap | Actual Consumed | Safety Status |
| :--- | :--- | :--- | :--- |
| **Max `lstat` Calls** | 100 | 30 | **PASSED** (within bound) |
| **Max Selected Month Scandir** | 6 | 0 | **PASSED** (within bound) |
| **Max Entries Per Scandir** | 16 | 0 | **PASSED** (within bound) |
| **Max Real Data Body Bytes Read** | 0 | 0 | **STRICT ZERO** |
| **Max Symlink Follow** | 0 | 0 | **STRICT ZERO** |
| **Protected File / Dir Accesses** | 0 | 0 | **STRICT ZERO** |
| **Remote Market API Calls** | 0 | 0 | **STRICT ZERO** |
| **Wall Clock Duration** | Bounded | 0.0003 s | **PASSED** |

---

## 3. Ancestor Hierarchy Provenance (Stat-Only, No Follow)

Every ancestor directory between `/root` and `Quant-agent/data/research/BTCUSDT` was stat-checked without following symlinks:

| Ancestor Path | Exists | Is Dir | Is Symlink | Mode | Dev | Inode |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `/root` | True | True | False | `0o40700` | 2096 | 49153 |
| `/root/workspace` | True | True | False | `0o40755` | 2096 | 90823 |
| `/root/workspace/project` | True | True | False | `0o40755` | 2096 | 12830 |
| `/root/workspace/project/Quant-agent` | True | True | False | `0o40755` | 2096 | 1723 |
| `/root/workspace/project/Quant-agent/data` | True | True | False | `0o40755` | 2096 | 397871 |
| `/root/workspace/project/Quant-agent/data/research` | True | True | False | `0o40755` | 2096 | 399715 |
| `/root/workspace/project/Quant-agent/data/research/BTCUSDT` | True | True | False | `0o40755` | 2096 | 399719 |

---

## 4. Candidate-Month × File-Existence Matrix (6 Approved BTC Months)

Only the six authorized non-protected month directories (2021, 2023, 2025 March & April) were probed. Zero other months or years were touched.

| Partition | Relative Directory | Parquet File Name | File Size (Bytes) | Mode | Verification Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **2021-03** | `research/BTCUSDT/1m/year=2021/month=03` | `data.parquet` | 2,756,024 bytes | `0o100644` | `PRESENT_METADATA_ONLY` |
| **2021-04** | `research/BTCUSDT/1m/year=2021/month=04` | `data.parquet` | 2,621,313 bytes | `0o100644` | `PRESENT_METADATA_ONLY` |
| **2023-03** | `research/BTCUSDT/1m/year=2023/month=03` | `data.parquet` | 2,415,597 bytes | `0o100644` | `PRESENT_METADATA_ONLY` |
| **2023-04** | `research/BTCUSDT/1m/year=2023/month=04` | `data.parquet` | 2,201,521 bytes | `0o100644` | `PRESENT_METADATA_ONLY` |
| **2025-03** | `research/BTCUSDT/1m/year=2025/month=03` | `data.parquet` | 2,352,476 bytes | `0o100644` | `PRESENT_METADATA_ONLY` |
| **2025-04** | `research/BTCUSDT/1m/year=2025/month=04` | `data.parquet` | 2,329,220 bytes | `0o100644` | `PRESENT_METADATA_ONLY` |

---

## 5. Additional Target Sibling & Parent Directory Observations (NO OPEN)

| Target ID | Relative Path | Expected | Mode | Size (Bytes) | Verification Status | Notes / Limitations |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `btc_perp_data_manifest` | `research/BTCUSDT/data_manifest.json` | file | `0o100644` | 45,234 | `PRESENT_METADATA_ONLY` | Metadata file exists; stat-only, no contents opened |
| `btc_perp_funding_events` | `research/BTCUSDT/funding_events.csv` | file | `0o100644` | 219,066 | `PRESENT_METADATA_ONLY` | Metadata file exists; stat-only, no contents opened |
| `btc_perp_raw_mark_price_parent` | `research/BTCUSDT/raw/mark_price` | dir | `0o40755` | 4,096 | `PRESENT_METADATA_ONLY` | Parent directory exists; existence does NOT prove continuous true 1m PIT or valid clock |
| `btc_perp_raw_funding_parent` | `research/BTCUSDT/raw/funding` | dir | `0o40755` | 4,096 | `PRESENT_METADATA_ONLY` | Parent directory exists; existence does NOT prove continuous true 1m PIT or valid clock |
| `btc_perp_raw_klines_parent` | `research/BTCUSDT/raw/klines` | dir | `0o40755` | 4,096 | `PRESENT_METADATA_ONLY` | Parent directory exists; existence does NOT prove continuous true 1m PIT or valid clock |
| `btc_spot_data_manifest` | `research/BTCUSDT_SPOT/data_manifest.json` | file | `0o100644` | 19,855 | `PRESENT_METADATA_ONLY` | Metadata file exists; stat-only, no contents opened |
| `btc_spot_1m_parent` | `research/BTCUSDT_SPOT/1m` | dir | `0o40755` | 4,096 | `PRESENT_METADATA_ONLY` | Parent directory exists; existence does NOT prove continuous true 1m PIT or valid clock |
| `cross_asset_ethusdt_1h` | `research/cross_asset_1h/ETHUSDT.parquet` | file | `0o100644` | 2,907,000 | `PRESENT_METADATA_ONLY` | Metadata file exists; stat-only, no contents opened |
| `cross_asset_basket_manifest` | `research/cross_asset_1h/basket_manifest.json` | file | `0o100644` | 56,012 | `PRESENT_METADATA_ONLY` | Metadata file exists; stat-only, no contents opened |
| `v0319_derivatives_hourly_inputs` | `research/v0.3.19_official_derivatives/hourly_inputs.parquet` | file | `0o100644` | 3,101,084 | `PRESENT_METADATA_ONLY` | Metadata file exists; stat-only, no contents opened |
| `v0319_derivatives_raw_manifest` | `research/v0.3.19_official_derivatives/raw_data_manifest.json` | file | `0o100644` | 420,725 | `PRESENT_METADATA_ONLY` | Metadata file exists; stat-only, no contents opened |

---

## 6. Source Classes and Permissions Summary

### BTC Perpetual 1m Klines (Selected Non-Protected Partitions)
- **Asset / Instrument / Frequency:** BTC | Perpetual (USD-M) | 1m
- **Scope:** 6 selected candidate months (2021-03, 2021-04, 2023-03, 2023-04, 2025-03, 2025-04)
- **Existence Status:** `LOCATED_METADATA_ONLY`
- **True Continuous 1m PIT Status:** `UNVERIFIED_PENDING_CONTENT_AUDIT`
- **Spot vs. Perp Distinction:** Perpetual derivative contract; distinct from spot cash market
- **License & Rights:** `UNVERIFIED_PENDING_OWNER_GRANT`
- **P2 Source Admission Status:** `BLOCKED_NOT_ADMITTED`
- **Policy Rule:** Metadata presence does NOT constitute empirical source admission; no P3/P4 grant.

### BTC Perpetual Data Manifest & Funding Events
- **Asset / Instrument / Frequency:** BTC | Perpetual (USD-M) | N/A (Manifest JSON / Event CSV)
- **Scope:** research/BTCUSDT/data_manifest.json and research/BTCUSDT/funding_events.csv
- **Existence Status:** `LOCATED_METADATA_ONLY`
- **True Continuous 1m PIT Status:** `UNPROVEN: CSV existence is NOT verified funding event clock/right or true known-at timestamp`
- **Spot vs. Perp Distinction:** Perpetual funding event series; not spot
- **License & Rights:** `UNVERIFIED_PENDING_OWNER_GRANT`
- **P2 Source Admission Status:** `BLOCKED_NOT_ADMITTED`
- **Policy Rule:** Stat-only inspection; files not opened or parsed.

### BTC Perpetual Raw Source Directories (Mark Price, Funding, Klines)
- **Asset / Instrument / Frequency:** BTC | Perpetual (USD-M) | Directory container only
- **Scope:** research/BTCUSDT/raw/{mark_price,funding,klines}
- **Existence Status:** `PARENT_DIRECTORIES_LOCATED_ONLY`
- **True Continuous 1m PIT Status:** `UNPROVEN: raw/mark_price parent directory existence does NOT prove continuous true 1m Mark PIT`
- **Spot vs. Perp Distinction:** Raw perp ingestion landing zone
- **License & Rights:** `UNVERIFIED_PENDING_OWNER_GRANT`
- **P2 Source Admission Status:** `EXCLUDED_FROM_LISTING_OR_READ`
- **Policy Rule:** Strict prohibition against scandir or descent into raw subdirectories.

### BTC Spot Separate Dataset
- **Asset / Instrument / Frequency:** BTC | Spot (Cash) | 1m (Separate tree)
- **Scope:** research/BTCUSDT_SPOT/{data_manifest.json,1m}
- **Existence Status:** `LOCATED_METADATA_ONLY`
- **True Continuous 1m PIT Status:** `NOT_APPLICABLE_SPOT_ONLY`
- **Spot vs. Perp Distinction:** SPOT IS NOT PERPETUAL: Spot cash data cannot substitute for perpetual futures mechanics or funding rate dynamics
- **License & Rights:** `UNVERIFIED_PENDING_OWNER_GRANT`
- **P2 Source Admission Status:** `BLOCKED_NOT_ADMITTED`
- **Policy Rule:** Distinct source class; no automatic interchangeability.

### Cross-Asset Hourly Auxiliary Data
- **Asset / Instrument / Frequency:** ETH / Basket | USD-M / Spot / Mixed | 1h (HOURLY, NOT 1m)
- **Scope:** research/cross_asset_1h/{ETHUSDT.parquet,basket_manifest.json}
- **Existence Status:** `LOCATED_METADATA_ONLY`
- **True Continuous 1m PIT Status:** `HOURLY NOT MINUTE: 1h ETH data is NOT evidence of ETH/SOL perp 1m or true continuous Mark`
- **Spot vs. Perp Distinction:** Auxiliary hourly macro features
- **License & Rights:** `UNVERIFIED_PENDING_OWNER_GRANT`
- **P2 Source Admission Status:** `BLOCKED_NOT_ADMITTED`
- **Policy Rule:** Does NOT satisfy 1m perp execution requirement for multi-asset trading.

### Legacy Official Derivatives (v0.3.19)
- **Asset / Instrument / Frequency:** BTC | Derivatives archive | Hourly
- **Scope:** research/v0.3.19_official_derivatives/{hourly_inputs.parquet,raw_data_manifest.json}
- **Existence Status:** `LOCATED_METADATA_ONLY`
- **True Continuous 1m PIT Status:** `NOT_APPLICABLE_HOURLY_DERIVATIVE_ARCHIVE`
- **Spot vs. Perp Distinction:** Older derivative archive; not minute execution series
- **License & Rights:** `UNVERIFIED_PENDING_OWNER_GRANT`
- **P2 Source Admission Status:** `BLOCKED_NOT_ADMITTED`
- **Policy Rule:** Retained for historical traceability only; no new live trading use.

### Protected Forward & Validation Holdout Data
- **Asset / Instrument / Frequency:** BTC | Forward / Held-out partitions | All frequencies
- **Scope:** data/forward/BTCUSDT/**, data/research/h39_validation/**, data/research/BTCUSDT/1m/year=2026/**, and any BTC market file in [2026-02-01, 2026-08-01)
- **Existence Status:** `STRICT_ZERO_ACCESS_PRESERVED`
- **True Continuous 1m PIT Status:** `PROTECTED_HOLD_OUT`
- **Spot vs. Perp Distinction:** Protected evaluation domain
- **License & Rights:** `STRICTLY_SEALED`
- **P2 Source Admission Status:** `PERMANENTLY_BLOCKED_FROM_P2_INSPECTION`
- **Policy Rule:** Zero stat, zero scandir, zero open, zero read bytes.

---

## 7. Next Bounded Readiness Checks (Formulated Unexecuted)

The following five bounded checks are formulated for future Controller consideration without execution:

### CHECK_A_KLINE_READ_AND_SHA_GRANT: Owner Grants Future Selected Kline Parquet Read/SHA
- **Status:** `PROPOSED_UNEXECUTED`
- **Description:** Owner provides explicit cryptographic sha256 golden references and bounded read authorization for the 6 verified non-protected monthly kline parquets (2021-03, 2021-04, 2023-03, 2023-04, 2025-03, 2025-04) to audit column schema and timestamp monotonicity.

### CHECK_B_RAW_MARK_1M_SCHEMA_AND_PIT_CONTINUITY: Raw Mark 1m Schema/Timestamp Availability & True Continuous 1m PIT
- **Status:** `PROPOSED_UNEXECUTED`
- **Description:** Rigorous audit of raw/mark_price internal structure to establish whether continuous 1-minute point-in-time Mark prices exist without gaps or forward leakage across backtest windows.

### CHECK_C_FUNDING_TRUE_KNOWN_AT_AND_SETTLEMENT_SOURCES: Funding True Known-At, Settlement/Index, and Price Sources
- **Status:** `PROPOSED_UNEXECUTED`
- **Description:** Verification that funding_events.csv records point-in-time publication timestamps rather than retrospective settlement timestamps, verifying cash settlement flow causality.

### CHECK_D_RIGHTS_FEES_FILTER_AND_PROTECTION_GATES: Rights, Fees, Filter, and Protection Gates
- **Status:** `PROPOSED_UNEXECUTED`
- **Description:** Formal legal/commercial data usage clearance, VIP fee tier schedule verification, and cryptographic verification that [2026-02-01, 2026-08-01) holdout remains completely uninspected.

### CHECK_E_ETH_SOL_MINUTE_DECISION_OR_PROSPECTIVE_BTC_ONLY_ROUTE: ETH/SOL Minute Data Decision or Prospective BTC-Only Diagnostic Route
- **Status:** `PROPOSED_UNEXECUTED`
- **Description:** Address multi-asset diversification vs single-asset concentration. Note: BTC-only positive screen issue is 100% single asset exposure >60% ceiling; NOT '1/3 assets 33% below >=60% positive support'. A BTC-only separately authorized diagnostic need not claim 3-asset positive support and must be a new prospective method if selected.

---

## 8. Verifier Script Integrity Hashes (Own Scripts Only)

| Script Path | SHA-256 Digest |
| :--- | :--- |
| `scripts/strategy_research/p2_owner_root_metadata/__init__.py` | `49155ac73b70a2f6f3f43dcd4f02a56329e4250ca57fa539b96cb3a77b51ab60` |
| `scripts/strategy_research/p2_owner_root_metadata/config.py` | `b45f6ba8abc710be88ed81ccda2fd0abd95f534895082c30832e0c5a397b8ab1` |
| `scripts/strategy_research/p2_owner_root_metadata/probe.py` | `3c3fe5fde2ae5d70ad6e8fb875daff27f844fd6354d154c163c527fa9dbdfcdd` |
| `scripts/strategy_research/p2_owner_root_metadata/matrix.py` | `1769b1256c525f437ffc372a1b0e25ade7c824f089183d1ecde19de224215e48` |
| `scripts/strategy_research/p2_owner_root_metadata/cli.py` | `b66176441774070915b11f753e0647fffa5808c80cbd475ab217309cf95ca270` |

---

## 9. Conclusion and Next Controller Decision

This verification confirms that the owner-supplied data root `/root/workspace/project/Quant-agent/data` physically exists in WSL and contains the expected directory layout and file metadata for the six authorized non-protected BTC partitions. No protected data was accessed, no file bodies were opened, and no symlinks were traversed. Terminal verdict is strictly `P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY`. Empirical source admission and trading execution authority remain reserved for subsequent Controller determination.
