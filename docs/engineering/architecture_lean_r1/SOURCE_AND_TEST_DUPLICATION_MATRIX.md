# Source and Test Duplication Matrix

**Milestone:** v0.6 Gemini Boost R1 Architecture Lean  
**Repository Tree Baseline:** `97f4040b9380f2069575a989c066d1daeef15194`  
**Inventory Source:** Static AST and Git Analysis (`inventory_analyzer.py`)  

---

## 1. Repository Source Inventory Summary

| Package Namespace | Python Files | Total Lines | Code Lines | Comment Lines | Blank Lines | Primary Architectural Role |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `src/btc_quant_agent` | 161 | 75,534 | 67,623 | 1,233 | 6,678 | Core production quant agent engine (IMMUTABLE) |
| `scripts/strategy_research` | 35 | 7,824 | 6,966 | 97 | 761 | Research protocols and backtest pipelines (IMMUTABLE) |
| `scripts/market_data` | 11 | 3,748 | 3,180 | 79 | 489 | Forward public feed connectors & book integrity (WRITABLE) |
| `scripts/integration` | 12 | 2,696 | 2,320 | 56 | 320 | Market event bridge R2 & adapters (WRITABLE) |
| `scripts/ops_g3` | 2 | 873 | 747 | 23 | 103 | Operational readiness diagnostics (IMMUTABLE) |
| `scripts/ci` | 1 | 404 | 325 | 31 | 48 | CI test plan mapper (HANDLED BY NORMAL TASK) |
| `tests` | 205 | 45,957 | 39,788 | 1,180 | 4,989 | Test suites (3,456 collected test items) |
| `tools` | 7 | 1,421 | 1,202 | 34 | 185 | Operation tools (IMMUTABLE) |
| **Total Tracked** | **436** | **138,537** | **122,230** | **2,734** | **13,573** | Full Repository |

---

## 2. Test Suite Burden & Categorization Matrix

A total of 3,456 tests were collected via pytest (`3454 passed, 2 skipped` at baseline SHA `97f4040b`).

| Categorization Tier | Files | Tests Count | Description & Policy |
| :--- | :--- | :--- | :--- |
| **`SCIENCE_AUTHORITY_IMMUTABLE`** | 78 | 1,547 | H40, H41, 2024–2026 historical scientific holdout tests, P-series and B-series formal research tests. **STRICTLY PRESERVED WITHOUT MODIFICATION**. |
| **`SAME_METHOD_DIFFERENT_INVARIANT`** | 12 | 394 | Scoped Feed (`forward_public_feed_r1`) and Bridge (`market_event_bridge_r2`) invariant suites testing book continuity, PIT clocks, funding ledgers, and hermetic CI harness. |
| **`UNKNOWN_NEEDS_REVIEW`** | 115 | 1,444 | General application, storage, and utility tests outside feed/bridge scope. Unmodified. |

### Top Slow Tests (from GitHub Actions 38270967488 reference log)

1. `tests/test_v051_h40_m3a_production_discovery_producer.py`: **59.62s** (H40 production grid)
2. `tests/test_v051_h40_p3b_production_verifier_behavior_seal.py`: **50.61s** (H40 verifier roundtrip)
3. `tests/test_v051_h40_f01r3r3_api_seal.py`: **38.20s** (H40 API state sealing)
4. `tests/test_v041_p6_metrics_benchmarks_qualification.py`: **28.45s** (Metric benchmarks)
5. `tests/test_v042_b06_random_experiment_replay.py`: **24.12s** (Monte Carlo replay)
6. `tests/test_v040_research_kernel_economic_validation.py`: **22.80s** (Economic validation)
7. `tests/test_v041_c2_intrabar_exit_slippage_bounds.py`: **19.50s** (Slippage bounds)

*Engineering Insight*: The ~904s full CI runtime is dominated by scientific holdouts and multi-run research simulations. Eliminating these is strictly forbidden as they form the empirical scientific bedrock. The focused feed/bridge test suite, however, takes ~15.98s, of which ~7.5s consists of idle socket connection timeouts and un-cached Git subprocessing.

---

## 3. Structural Duplication Across Writable Modules

Within the authorized namespaces (`scripts/market_data/forward_public_feed_r1` and `scripts/integration/market_event_bridge_r2`), static analysis reveals five concrete duplication hotspots:

```
+---------------------------------------------------------------------------------------+
| Hotspot 1: MarketEvent Serialization & Manifest Hashing                               |
| Location: contracts.py vs bridge_engine.py vs funding_adapter.py                       |
| AST overlap: Canonical SHA-256 calculation over sorted JSON envelopes, schema dicts   |
+---------------------------------------------------------------------------------------+
| Hotspot 2: Proxy Credential Desensitization & CLI Diagnostics                         |
| Location: proxy_route.py vs feed cli.py vs bridge cli.py                              |
| AST overlap: sanitize_env_proxy_map, detect_wsl2_networking, error mapping            |
+---------------------------------------------------------------------------------------+
| Hotspot 3: Synthetic Exchange Fixture Generation                                      |
| Location: feed/fixture.py vs bridge/fixtures.py                                       |
| AST overlap: Depth snapshots, 1m kline frames, mark price ticks, random seed control  |
+---------------------------------------------------------------------------------------+
| Hotspot 4: Cold Authority Git SHA Verification                                        |
| Location: portable_ci_refs.py                                                         |
| AST overlap: Repeated subprocess git cat-file / git archive per test execution        |
+---------------------------------------------------------------------------------------+
| Hotspot 5: Synchronous Socket Probe Timeouts in Negative Tests                        |
| Location: proxy_route.py probe_tcp_socket                                             |
| AST overlap: Hardcoded 2.0s socket timeout when probing closed local test ports       |
+---------------------------------------------------------------------------------------+
```

---

## 4. Ranked Architectural Simplification Opportunities

| Rank | Opportunity ID | Target Scope | Semantic Risk | Expected Gain |
| :---: | :--- | :--- | :---: | :--- |
| **1** | **SIMP-01: Canonical Envelope & Provenance Consolidation** | `contracts.py`, `bridge_engine.py`, `funding_adapter.py` | Low | Eliminates 80+ duplicate lines; unifies hashing and serialization logic into a single authoritative module. |
| **2** | **SIMP-02: Unified Proxy Route & Diagnostic Engine** | `proxy_route.py`, `cli.py` (feed & bridge) | Low | Eliminates 60+ duplicate lines; ensures 100% credential redaction consistency. |
| **3** | **SIMP-03: Shared Hermetic Exchange Fixture Engine** | `feed/fixture.py`, `bridge/fixtures.py` | Low | Eliminates 90+ duplicate lines; centralizes reproducible scenario generators. |
| **4** | **SIMP-04: Portable CI Harness Memoization** | `portable_ci_refs.py` | Low | Caches immutable Git SHA checkouts; saves 2–3 seconds in focused tests without mutable state leakage. |
| **5** | **SIMP-05: Bounded Probe Timeouts in Negative Tests** | `proxy_route.py`, `test_*_proxy*.py` | Very Low | Configures probe timeout; eliminates ~3.5 seconds of dead waiting time in focused negative tests. |
