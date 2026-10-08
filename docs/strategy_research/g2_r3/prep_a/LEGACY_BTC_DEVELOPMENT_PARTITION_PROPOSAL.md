# Legacy BTC Development Partition Proposal and Holdout Conflict Audit

**Task Identifier**: `V06_G2_R3_PARALLEL_P0_OFFLINE_PREPARATION`
**Role**: `GEMINI_A` (Synthetic Replay & Candidate Implementation)
**Controller Dispatch SHA**: `56f8a9faa1a4539124ab006b49bf42b6e7c997e3`
**Base Code SHA**: `e0ff8c3473de4bfa3e66fe7928d42992a4d38a32`
**Method Design Addendum HEAD**: `cf2d5cc33774cdcff7d709636305bba830e977ef`
**Status**: `PROPOSAL_ONLY__NOT_FROZEN_PREREGISTRATION__NO_EMPIRICAL_DATA_ACCESS`

---

## 1. Static Inspection of Legacy Public Manifest

Under explicit Controller dispatch authority, the static metadata of the existing old BTC data manifest was inspected:
- **Manifest Location**: `artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json`
- **Method**: Static JSON metadata inspection only. Zero Parquet or ZIP data bodies read, zero `du -a` into private worktrees, zero full SHA256 hashing across raw market bodies.

### Manifest Metadata Summary
- **Symbol**: `BTCUSDT` (Single symbol only)
- **Timeframe**: `1m`
- **Start Timestamp**: `1609459200000` (`2021-01-01T00:00:00Z`)
- **End Timestamp (Exclusive)**: `1785542400000` (`2026-08-01T00:00:00Z`)
- **Total Monthly Partitions**: 67 monthly Parquet partitions (`1m/year=2021/month=01` through `1m/year=2026/month=07`)
- **Reported Rows**: 2,933,280 rows

---

## 2. Protected Holdout Conflict Disclosure

### Conflict Identification
The R3 design document (`docs/strategy_research/g2_r3/METHOD_DESIGN.md`) originally proposed the following candidate development calendar:
- **Warm-up**: January 2026 (`[2026-01-01T00:00:00Z, 2026-02-01T00:00:00Z)`)
- **Proposed Development Folds**:
  - Fold 1: February 2026 (`[2026-02-01T00:00:00Z, 2026-03-01T00:00:00Z)`)
  - Fold 2: March 2026 (`[2026-03-01T00:00:00Z, 2026-04-01T00:00:00Z)`)
  - Fold 3: April 2026 (`[2026-04-01T00:00:00Z, 2026-05-01T00:00:00Z)`)

**CRITICAL OVERLAP**:
Under the prior v0.3 Bitcoin audit protocol (`test_v0325_one_shot_unblind_preregistration.py` / `test_v0323_blind_validation.py`), the period:
$$\text{Holdout}_{\text{v0.3}} = [2026\text{-}02\text{-}01\text{T}00:00:00\text{Z}, 2026\text{-}08\text{-}01\text{T}00:00:00\text{Z})$$
was designated as the **FINAL SEALED HOLDOUT**.

### Prohibition Against Silent Reclassification
1. The proposed R3 February–April 2026 development folds directly collide with and overlap the sealed v0.3 final holdout period.
2. Under no circumstances may an agent or researcher silently reclassify sealed holdout months into development data without an explicit Controller decision and formal de-sealing declaration.
3. Reading raw price or mark rows from the 2026-02 through 2026-04 partitions would violate the blind holdout boundary.
4. Therefore, the proposed 2026 February–April development window remains **BLOCKED** from empirical ingestion.

---

## 3. Proposal for Reusing Legacy BTC 2021–2025 Partitions

To preserve scientific rigor without contaminating blind evaluation boundaries or unsealing the v0.3 holdout, we propose utilizing historical development partitions from the legacy BTC manifest that predate the sealed holdout:

### Eligible Historical Partitions (Proposal)
- **Historical Scope**: January 1, 2021 through December 31, 2025 (60 completed months).
- **Proposed Alternative Tri-Fold Structure** (Example proposal for Controller review):
  - **Warm-up**: 1 month preceding the chosen window (e.g. October 2025)
  - **Proposed Fold 1**: November 2025 (`[2025-11-01, 2025-12-01)`)
  - **Proposed Fold 2**: December 2025 (`[2025-12-01, 2026-01-01)`)
  - **Proposed Fold 3**: January 2026 (`[2026-01-01, 2026-02-01)`) — immediately preceding the sealed Feb 1 boundary.
- **Alternative 3-Month Window**: Any contiguous 3-month block within 2021–2025 with 1 month warm-up.

### Strict Governance Constraints
1. **No Selection by Returns**: A substitute development window must **NEVER** be selected or optimized by scanning returns, Sharpe ratios, or trade counts. Any window must be chosen a priori based on macroeconomic regime rationale or calendar continuity and prospectively pre-registered.
2. **Controller Approval Required**: This document constitutes a proposal only. The active development calendar remains strictly gated pending a new formal Controller Dispatch.

---

## 4. Missing-Asset Inventory (ETHUSDT and SOLUSDT)

The R3 candidate specifications explicitly require evaluating the fixed universe:
$$\text{Universe} = \{\text{BTCUSDT}, \text{ETHUSDT}, \text{SOLUSDT}\}$$

### Audit Findings
1. **Single Symbol Coverage**: The legacy manifest `artifacts/research/run0-dev-frozen-v022-seed7-20260825/data_manifest.json` covers **only BTCUSDT**.
2. **ETH and SOL Absence**: No historical 1m trade candles or mark candles for `ETHUSDT` or `SOLUSDT` exist in the legacy manifest.
3. **No Inference Permitted**: Presence of BTCUSDT does not imply or certify availability, continuity, tick/lot rules, or data integrity for ETHUSDT or SOLUSDT.
4. **Prerequisite for Multi-Asset Campaign**: A formal public archive download, checksum verification, and manifest creation for ETHUSDT and SOLUSDT must be authorized by a future Controller dispatch before multi-asset empirical evaluation can proceed.

---

## 5. Candidate Registry Invariance

Throughout all partition proposals, data audits, and holdout conflict analyses:
- The candidate registry contains **EXACTLY 8 CANDIDATES** at all times.
- No candidates are added, removed, substituted, or retuned.
- `12H` candidates under the stress cost scenario are preserved with status `STRESS_COST_GEOMETRY_INELIGIBLE` (diagnostic only), never dropped to fabricate a clean pass.
