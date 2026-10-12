# B-Line CI Risk-Mapped Fast Path R1 — Mapping and Safety Rationale

## 1. Executive Summary & Root Cause at R3 Baseline (`97f4040b`)

At exact Gemini R3 baseline SHA `97f4040b9380f2069575a989c066d1daeef15194` ([GitHub Actions run `38270967488`](https://github.com/EXASHXE/btc-quant-agent-public/actions/runs/38270967488)), the CI test planner `scripts/ci/test_plan.py` fell back to `mode="full"` (lines 191–193) for any executable path not explicitly listed in `classify()`. Because `scripts/market_data/forward_public_feed_r1/**` and `scripts/integration/market_event_bridge_r2/**` lacked explicit risk-ownership mappings, even a single-line modification to `bridge_engine.py` or `cli.py` triggered the complete 3,454-test suite (904.17 seconds / ~15.07 minutes of pytest runtime, dominated by historical H40/H41 scientific discovery and holdout verification suites).

This task (`V06_GEMINI_NORMAL_FAST_CI_RISKMAP_R1`) adds **two explicit, independent, bi-directionally coupled ownership dependency matrices** (`OWNER_FEED_MATRIX` and `OWNER_BRIDGE_MATRIX`) to `scripts/ci/test_plan.py` while strictly preserving all fail-closed invariants and release gates.

---

## 2. Explicit Ownership Dependency Matrices

### 2.1 Owner `FEED`: `scripts/market_data/forward_public_feed_r1/**`

- **Root Prefix**: `scripts/market_data/forward_public_feed_r1/`
- **Known Baseline Production Modules (11 files)**:
  1. `scripts/market_data/forward_public_feed_r1/__init__.py` (`package_init`)
  2. `scripts/market_data/forward_public_feed_r1/cli.py` (`cli`)
  3. `scripts/market_data/forward_public_feed_r1/connector.py` (`binance_2026_public_market_ws_routing` — 2026 Binance `/public` and `/market` websocket routing)
  4. `scripts/market_data/forward_public_feed_r1/contracts.py` (`contracts`)
  5. `scripts/market_data/forward_public_feed_r1/durability.py` (`durability`)
  6. `scripts/market_data/forward_public_feed_r1/fixture.py` (`fixture`)
  7. `scripts/market_data/forward_public_feed_r1/health.py` (`health`)
  8. `scripts/market_data/forward_public_feed_r1/order_book.py` (`order_book`)
  9. `scripts/market_data/forward_public_feed_r1/proxy_route.py` (`proxy_route`)
  10. `scripts/market_data/forward_public_feed_r1/replay.py` (`replay`)
  11. `scripts/market_data/forward_public_feed_r1/time_authority.py` (`time_authority`)
- **Primary Owned Suite (`12 files, 186 tests`)**:
  - `tests/test_v06_forward_public_feed_r1_adversarial.py`
  - `tests/test_v06_forward_public_feed_r1_book.py`
  - `tests/test_v06_forward_public_feed_r1_connector.py`
  - `tests/test_v06_forward_public_feed_r1_contracts.py`
  - `tests/test_v06_forward_public_feed_r1_durability.py`
  - `tests/test_v06_forward_public_feed_r1_e2e_scenarios.py`
  - `tests/test_v06_forward_public_feed_r1_health.py`
  - `tests/test_v06_forward_public_feed_r1_proxy_route.py`
  - `tests/test_v06_forward_public_feed_r1_replay.py`
  - `tests/test_v06_forward_public_feed_r1_reviewer_fixes.py`
  - `tests/test_v06_forward_public_feed_r1_source_qualification.py`
  - `tests/test_v06_forward_public_feed_r1_time.py`
- **Mandatory Downstream Dependent Suite (`9 files, 208 tests`)**:
  - All `tests/test_v06_market_event_bridge_r2_*.py` files are always selected alongside the FEED suite because `market_event_bridge_r2` directly imports and consumes `OrderBookIntegrityEngine`, `BinancePublicFeedClient`, `proxy_route`, source timestamps, funding payloads, and feed contracts.
- **Boundary Map Coupling**:
  - If `scripts/ci/test_plan.py` changes in the same diff, `tests/test_ci_test_plan.py` is unioned automatically (`22 files, 446 tests`).

### 2.2 Owner `BRIDGE`: `scripts/integration/market_event_bridge_r2/**`

- **Root Prefix**: `scripts/integration/market_event_bridge_r2/`
- **Known Baseline Production Modules (12 files)**:
  1. `scripts/integration/market_event_bridge_r2/__init__.py` (`package_init`)
  2. `scripts/integration/market_event_bridge_r2/__main__.py` (`module_entrypoint`)
  3. `scripts/integration/market_event_bridge_r2/book_ladder.py` (`book`)
  4. `scripts/integration/market_event_bridge_r2/bridge_engine.py` (`bridge_engine`)
  5. `scripts/integration/market_event_bridge_r2/c_composite_bar.py` (`c_composite_bar`)
  6. `scripts/integration/market_event_bridge_r2/cli.py` (`cli`)
  7. `scripts/integration/market_event_bridge_r2/fixtures.py` (`fixtures`)
  8. `scripts/integration/market_event_bridge_r2/funding_adapter.py` (`funding`)
  9. `scripts/integration/market_event_bridge_r2/generate_r3_evidence.py` (`generate_r3_evidence`)
  10. `scripts/integration/market_event_bridge_r2/mark_aggregator.py` (`mark`)
  11. `scripts/integration/market_event_bridge_r2/portable_ci_refs.py` (`portable_ci_refs`)
  12. `scripts/integration/market_event_bridge_r2/source_qualification.py` (`source_qualification`)
- **Primary Owned Suite (`9 files, 208 tests`)**:
  - `tests/test_v06_market_event_bridge_r2_binance_2026_routes.py`
  - `tests/test_v06_market_event_bridge_r2_c_composite_g1.py`
  - `tests/test_v06_market_event_bridge_r2_clash_proxy_network.py`
  - `tests/test_v06_market_event_bridge_r2_depth_ladder_l2.py`
  - `tests/test_v06_market_event_bridge_r2_funding_pit_provenance.py`
  - `tests/test_v06_market_event_bridge_r2_pit_clock_mark_last.py`
  - `tests/test_v06_market_event_bridge_r2_portable_ci.py`
  - `tests/test_v06_market_event_bridge_r2_settled_funding_ledger.py`
  - `tests/test_v06_market_event_bridge_r2_stress_and_security.py`
- **Pinned Downstream B/C Consumer Interface Probes (Included in Bridge Suite)**:
  - `tests/test_v06_market_event_bridge_r2_portable_ci.py` (materializes and executes isolated consumer probes against pinned upstream B SHA `51cdd4e17503fbd18ad22aaeeaba3580f5efacf8` and pinned upstream C SHA `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b`)
  - `tests/test_v06_market_event_bridge_r2_c_composite_g1.py` (proves C `MarketPitPort` and G1 composite bar contract compatibility)
  - `tests/test_v06_market_event_bridge_r2_settled_funding_ledger.py` (proves B `parse_funding_payload` and decimal ledger conservation)
  - `tests/test_v06_market_event_bridge_r2_funding_pit_provenance.py` (proves PIT funding arrival causality and mark witness checks)
- **Mandatory Upstream Coupled Suite (`12 files, 186 tests`)**:
  - All `tests/test_v06_forward_public_feed_r1_*.py` files are always selected alongside the BRIDGE suite (`21 total test files, 394 tests`).

---

## 3. Fail-Closed Safety Architecture

1. **No Blanket `scripts/**` or `tests/**` Exemptions**:
   - Narrow script namespaces without proven independent owning test matrices (`scripts/strategy_research/**`, `scripts/rc1/**`, `scripts/market_data/<other>/**`, `scripts/integration/<other>/**`) fall through to `full = True`.
2. **Shared Project-Level Schemas & Clock/Wallet Base Modules Remain `FULL`**:
   - Broad foundational modules (`src/btc_quant_agent/sqlite_schema.py`, `src/btc_quant_agent/time_boundary.py`, `src/btc_quant_agent/account_watch/**`, `src/btc_quant_agent/execution/**`, `src/btc_quant_agent/economic/**`, `src/btc_quant_agent/h40/**`, `src/btc_quant_agent/h41/**`, `src/btc_quant_agent/live_db.py`, `src/btc_quant_agent/storage.py`) are intentionally excluded from the FEED/BRIDGE fast path and force `mode = "full"`.
3. **Path Normalization & Traversal Rejection (`_normalize_changed_path`)**:
   - Windows backslash separators (`\`) are normalized to POSIX `/` across `classify()`, `files()`, and `lint_baseline()`.
   - Any path containing `..` segments, leading `/`, Windows drive letters (`:`), null bytes, empty segments (`//`), trailing `/`, or leading/trailing whitespace returns `None` and forces `mode = "full"`.
4. **Deleted or Renamed Source/Test Files Force `FULL`**:
   - `changed_paths()` uses `git diff --no-renames --name-only <base> HEAD` so renames always surface both the deleted source path and destination path.
   - If any known baseline FEED or BRIDGE module, any mapped `src/` / `configs/` / `scripts/ci/` file, or any `tests/test_*.py` file in `changed` does not exist on disk (`not (ROOT / name).is_file()`), `classify()` forces `mode = "full"` and clears `tests = []`.
   - Furthermore, `_resolve_feed_bridge_suite()` verifies that all 21 baseline FEED and BRIDGE test files exist on disk before returning a focused suite; if any baseline test file was deleted from the worktree, it returns `None` and forces `mode = "full"`.
5. **Direct Test File Edits Expand Coupled Owner Suites**:
   - Editing any `tests/test_v06_forward_public_feed_r1_*.py` or `tests/test_v06_market_event_bridge_r2_*.py` file directly selects the entire 21-file (`394-test`) coupled FEED + BRIDGE suite.
   - Editing or deleting files in test subdirectories (`tests/h41/**`, `tests/goldens/**`) forces `mode = "full"`.
