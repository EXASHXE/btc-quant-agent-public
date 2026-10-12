# Gemini Boost R1: Executive Decision and Architecture Scope

**Task ID:** V06_GEMINI_BOOST_ARCHITECTURE_LEAN_TEST_RUNTIME_R1  
**Role:** Senior Systems Architect / Quant Research Infrastructure Engineer / Scientific Test Preservation Reviewer  
**Repository:** EXASHXE/btc-quant-agent-public  
**Branch:** feature/v06-bline-gemini-boost-architecture-lean-test-r1  
**Start SHA:** 97f4040b9380f2069575a989c066d1daeef15194  
**Authority L2 SHA:** 23a5e3ca99e4224550dfd04d44c908e4e38adaf1  
**Authority URL:** https://github.com/EXASHXE/btc-quant-agent-public/blob/23a5e3ca99e4224550dfd04d44c908e4e38adaf1/reviews/v0.6/b_line/V06_GEMINI_R3_CODEX_AUDIT_AND_CI_ARCHITECTURE_OPTIMIZATION_CONTROLLER_L2_R1.md  

---

## 1. Executive Summary & Problem Context

The Gemini R3 milestone achieved FULL GitHub Actions CI passage (**3454 passed, 2 skipped in 904.17s** at `97f4040b`). However, previous engineering cycles incurred significant friction:
- Excessive worker iterations (1,117 interactions, 55 minutes intermediate turnaround);
- Repeated full test executions triggered by unmapped test paths in the CI planner;
- Residual financial and causal PIT ambiguities identified by Codex audits and Controller L2 review;
- Duplicated serialization logic, diagnostic routines, and test fixtures across newly added feed and bridge modules.

This Gemini BOOST mission operates under a **convergent execution discipline**:
1. **Zero Recursive Worker Loops**: A single execution thread with strict milestone gating.
2. **Fixed Scope**: Exactly three declared refactor waves in safely authorized namespaces.
3. **Linear Git Chain**: Maximum 4 non-forced commits, single final push.
4. **Preservation of Scientific Authority**: Strict non-touch policy for all historical holdout data, H40/H41 test suites, and production code.

---

## 2. Namespace & Authority Boundary

### Authorized Writable Paths
The scope of code modification is strictly quarantined to:
- `scripts/market_data/forward_public_feed_r1/**`
- `scripts/integration/market_event_bridge_r2/**`
- `tests/test_v06_forward_public_feed_r1_*.py`
- `tests/test_v06_market_event_bridge_r2_*.py`
- `docs/engineering/architecture_lean_r1/**`
- `evidence/v0.6/b_line/architecture_lean_r1/**`
- `scripts/engineering/architecture_lean_r1/**` (purely read-only analysis tools)
- `tests/test_v06_architecture_lean_r1_*.py`

### Strictly Prohibited Boundaries
- **CI Configuration & Planner**: `scripts/ci/test_plan.py`, `tests/test_ci_test_plan.py`, `.github/workflows/**` (exclusively owned by parallel Gemini NORMAL task).
- **Core Production & Research Suites**: `src/btc_quant_agent/**`, historical B/C frozen branches, A-line strategies.
- **Scientific Holdout & Legacy Guards**: All H39/H40/H41 test suites (`tests/test_v051_h40_*.py`, `tests/h41/**`), 2024–2026 holdout records, private keys, live network access, order routing, and real funds.

---

## 3. High-Priority Residual Financial & PIT Correctness Risks

Before performing any structural refactoring, the following 6 static residual risks identified by Codex and Controller L2 must be rigorously tested with synthetic-negative proofs and repaired:

1. **Receipt Time vs Settlement Time Mark Witness Conflation**:
   `funding_adapter.py` previously verified Mark price freshness against `observed_wall_utc_ms` (time REST was received), rather than against the actual settlement time `funding_time_ms`. A late funding notification (e.g. T+3 hours) could erroneously bind a current mark price to a past settlement.
   *Resolution*: Mark witness must be validated against `funding_time_ms`, or marked `COST_INCOMPLETE` if contemporaneous settlement mark is unavailable. Never masquerade receipt price as settlement price.

2. **Deduplication Key Rate Formatting Inconsistency**:
   `settlement_id` previously used raw unparsed `rate_str`. Numerically identical rates with varying string precision (e.g., `0.0001` vs `0.00010000`) caused journal duplication.
   *Resolution*: Canonicalize rate to normalized Decimal format and detect conflicting rates on identical settlements.

3. **Untrusted Bare Scalar Mark Witness Elevation**:
   Passing a bare float/Decimal directly created a witness with `quality="VERIFIED"` and `source_sha="manual_scalar_witness"`.
   *Resolution*: Bare scalars without provenance cannot be certified `VERIFIED`; they must be classified as non-authoritative (`UNVERIFIED_SCALAR`) or rejected for realized accounting.

4. **Non-Finite Numerical Values**:
   Funding rate and Mark price must be strictly verified finite (reject `NaN`, `+Inf`, `-Inf`, and non-positive mark prices).

5. **Mark-Derived 1m Bar Lineage**:
   Synthetic Mark 1m proxy bars must explicitly retain `DERIVED` status and cannot masquerade as official Binance Mark klines.

6. **Order Book L2 Continuity**:
   Initial snapshot gaps and sequence reconnects must reset continuity state and fail closed.

---

## 4. Execution Plan

| Wave | Scope | Key Objective | Non-Regression Guard |
| :--- | :--- | :--- | :--- |
| **Stage 1** | Financial & PIT Safety | Fix 6 residual risks; add 20+ synthetic negative tests | All 394 baseline tests pass + 20+ negative cases |
| **Wave 1** | Envelope & Provenance Consolidation | Unify MarketEvent serialization and metadata hashing | Cryptographic hash equivalence & identical schemas |
| **Wave 2** | Route Diagnostics & Fixtures Harmonization | Unify desensitized proxy inspection & synthetic exchange generator | Identical CLI behavior, zero credential leak |
| **Wave 3** | Harness Memoization & Test Runtime Lean | Memoize static Git SHA verification; bound negative socket timeouts | 100% test identity retained, zero test dropped, >=20% faster |
