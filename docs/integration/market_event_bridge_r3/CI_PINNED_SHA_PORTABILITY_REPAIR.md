# CI Pinned SHA Portability Repair Report

## 1. Executive Summary & Root Cause Analysis

In Market Event Bridge R2, CI workflow run `38252226915` aborted during test collection due to hardcoded development environment worktree paths. Specifically, 5 integration test files (`test_v06_market_event_bridge_r2_c_composite_g1.py`, `test_v06_market_event_bridge_r2_depth_ladder_l2.py`, `test_v06_market_event_bridge_r2_pit_clock_mark_last.py`, `test_v06_market_event_bridge_r2_settled_funding_ledger.py`, and `test_v06_market_event_bridge_r2_stress_and_security.py`) directly called `Path("/root/workspace/project/quant-v0.6/...").exists()` at module load time.

When executed inside standard GitHub Actions runners (where the process runs as unprivileged user `runner` with UID 1001), traversing `/root` immediately triggered `PermissionError: [Errno 13] Permission denied: '/root'` during pytest test discovery. Furthermore, tests lacked automatic repository root injection into `sys.path`, leading to `ModuleNotFoundError: No module named 'scripts'` when executed without `PYTHONPATH=.`. When external paths were absent, tests silently skipped upstream verification via `pytest.skip(...)`, resulting in a false sense of security where upstream B and C consumers were never actually verified.

---

## 2. Portable Pinned Source Architecture

To guarantee 100% portable, reproducible, and unprivileged CI execution, R3 implements [`scripts/integration/market_event_bridge_r2/portable_ci_refs.py`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/integration/market_event_bridge_r2/portable_ci_refs.py).

### Pinned Upstream Commits
All external dependencies are pinned to immutable Git commit SHAs:
- **Upstream B (`forward-shadow-research-r1`)**: `51cdd4e17503fbd18ad22aaeeaba3580f5efacf8`
- **Upstream C (`g1g3-offline-ports-r1`)**: `91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b`
- **Original G1 (`g1_core_read_only`)**: `861a9d148f72db00e6079e53af78220bdd7e84ce`
- **Base Foundation A**: `df00997f344eba82f7cca0d03ee1617948abee44`

### Isolated Materialization via `git archive`
Rather than relying on local directories or sibling checkouts, [`PortablePinnedSourceHarness`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/integration/market_event_bridge_r2/portable_ci_refs.py) extracts exact source trees directly from the local Git object store using:
```bash
git archive <commit_sha>:<subpath> | tar -x -C /tmp/btc-r3-ci-pit-source/materialized_pinned/<name>_<sha>/<subpath>
```
If a commit is not present locally, it fetches `--depth=1 origin <commit_sha>` safely.

### Cryptographic Manifest Verification
Before loading any materialized Python module, [`PortablePinnedSourceHarness`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/integration/market_event_bridge_r2/portable_ci_refs.py) computes SHA-256 digests of all materialized files and asserts exact match against `PINNED_FILE_CHECKSUMS`:
- `scripts/strategy_research/forward_shadow_research_r1/contract.py`: `ecc809f8922cb20283305993b3e54307777f121f5e59bea0fa1bb04af9389d0a`
- `scripts/strategy_research/forward_shadow_research_r1/adapter.py`: `fa31bc3fe2ee5bdadd8b5554d0f01e53986c8a304caa53005f357963d6bba9a3`
- `scripts/strategy_research/forward_shadow_research_r1/signals.py`: `ae340ac4e5d5aa3bc67b2276bad684715b0b1c03e32f9b748b4376a48f594006`
- `scripts/g1g3_offline_ports_r1/market_pit_port.py`: `e57e3319f14547a8031adebae0aab61ee041751c1f949f152410959c7454b9c9`
- `scripts/g1_offline_preview_r1/model.py`: `086d6ec8747f82d59b6f8f42bfefd2d9c61e5f962707b4f9119f784741dd206e`

Any deviation, missing file, or hash discrepancy immediately raises [`ManifestMismatchError`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/integration/market_event_bridge_r2/portable_ci_refs.py).

### Path Security & Namespace Isolation
- **Path Traversal Defense**: All extraction and access paths are validated using `resolved.relative_to(base_dir)`. Symlinks pointing outside scratch or containing `..` trigger [`SecurityViolationError`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/scripts/integration/market_event_bridge_r2/portable_ci_refs.py).
- **Cross-Package Contamination Prevention**: Subprocess isolation executes tests in clean child processes where `sys.path` only contains the designated consumer tree.
- **Dynamic Portable Path Resolution**: All test files now determine repo root via `Path(__file__).resolve().parent.parent` and insert it into `sys.path`.

---

## 3. Verification & CI Reproduction Proof

1. **Simulated Unprivileged User Reproduction**:
   Executed test discovery under user `nobody` (UID 65534). R2 failed with `PermissionError: [Errno 13]`. Under R3, test discovery and execution succeeded 100% without accessing `/root`.
2. **Zero Skips Enforcement**:
   All 7 existing bridge test suites were refactored to replace `pytest.skip` guards with exact pinned imports via `ensure_portable_b_on_path()` and `ensure_portable_c_on_path()`.
3. **Dedicated Portability Suite**:
   Implemented [`tests/test_v06_market_event_bridge_r2_portable_ci.py`](file:///root/workspace/project/quant-v0.6/gemini-r3-portable-ci-pit-source/tests/test_v06_market_event_bridge_r2_portable_ci.py) containing 27 rigorous unit tests verifying hash verification, extraction error handling, security guards, and isolated subprocess execution. All 27 tests pass cleanly.
