# Source Feasibility, License Status, and Future Controller Questions (Role A)

**Task Identifier**: `V06_G2_R3_PARALLEL_P0_OFFLINE_PREPARATION`
**Role**: `GEMINI_A` (Synthetic Replay & Candidate Implementation)
**Controller Dispatch SHA**: `56f8a9faa1a4539124ab006b49bf42b6e7c997e3`
**Base Code SHA**: `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`
**Method Design Addendum HEAD**: `cf2d5cc33774cdcff7d709636305bba830e977ef`
**Status**: `P0_OFFLINE_SYNTHETIC_VERIFIED__NO_EMPIRICAL_DATA_ACCESS`

---

## 1. Source Feasibility and Data License Audit

In accordance with Controller Dispatch `56f8a9faa1a4539124ab006b49bf42b6e7c997e3`:
1. **Public Mark Metadata Status**:
   - 12 official Binance USD-M 1m Mark Price ZIP archives (Jan–Apr 2026 for BTCUSDT, ETHUSDT, SOLUSDT) were audited at HEAD-request level only in prior dispatch.
   - Zero object bodies were downloaded or read during this P0 task.
2. **License Suitability**:
   - The dataset usage terms remain categorized as `NONCOMMERCIAL_RESEARCH_SUITABILITY_UNDER_REVIEW`.
   - Commercial production deployment or live account integration is prohibited until explicit Controller legal clearance.
3. **Fee and Tier Authentication**:
   - All fee parameters ($6\,\text{bp}$ base taker, $12\,\text{bp}$ stress taker) are **diagnostic proxy assumptions**.
   - No private user account fees or signed Binance endpoints were queried.
   - `REAL_FUNDS_WRITE_AUTHORITY = NONE`.

---

## 2. Unresolved Empirical Gates and Preregistration Sequence

Before any empirical evaluation campaign may begin, the following technical gates must be formally settled by the Controller:

| Gate Identifier | Description | Current Status | Required Action for Future Dispatch |
|---|---|---|---|
| `GATE_HOLDOUT_SEPARATION` | v0.3 final holdout `[2026-02-01, 2026-08-01)` overlaps proposed R3 Feb–Apr development. | **BLOCKED** | Adopt historical 2021–2025 nonprotected partition proposal or issue explicit formal unsealing dispatch. |
| `GATE_MULTI_ASSET_INVENTORY` | ETHUSDT and SOLUSDT missing from legacy manifest. | **MISSING** | Conduct public archive download, checksum verification, and manifest registration for ETH and SOL. |
| `GATE_FUNDING_RATE_CONTINUITY` | Symbol-specific funding event publication and settlement times remain proxy. | **PROXY_ONLY** | Acquire and verify official 8h / hourly historical funding rate records with verified `available_at` timestamps. |
| `GATE_PREREG_FIRST_PUSH` | First-pushed preregistration SHA must be committed and pushed before opening data bodies. | **PENDING** | Controller publishes new dispatch freezing exact parameters and git commit SHA before any parquet reads. |

---

## 3. Explicit Prohibitions Enforced

Throughout Role A execution:
- **No raw historical price/mark/funding bodies read**: Zero bytes of parquet/zip price data accessed.
- **No empirical return ranking or shortlisting**: Zero candidate performance ranking performed.
- **No order generation or testnet execution**: Automated order submission remains permanently disabled (`AUTOTRADE = NONE`, `TESTNET = NOT_AUTHORIZED`).
- **No production code mutated**: G1, G3, RC1, RC2, Tactical, and MarketWatch codebases remain untouched.
