# BTC Quant Agent v0.3.21 Release Notes

**Version**: `0.3.21`  
**Release Name**: Forward Runtime State Reconciliation & Local Resilience  
**Target Git Branch**: `agent/v0.3.21-forward-recovery-cutover`  
**Execution Context**: Windows 11 Host / WSL2 Ubuntu 24.04 LTS  
**Release Timestamp**: 2026-09-03T17:16:00Z / 2026-09-04T01:16:00+08:00  

---

## 1. Executive Summary

Version 0.3.21 executes the comprehensive forward runtime recovery following the post-activation HTTP 451 geo-blocking failure observed in v0.3.20. Under strict non-alpha and research governance policies, this release permanently reconciles the compromised v0.3.20 Derivatives and Opportunity chains into terminal archives, hardens systemd services to fail closed against stale or terminal configs, resolves a structural collector/resolver configuration mismatch, provides robust local Windows/WSL power and storage resilience tooling, enhances the Forward Doctor with a typed 10-state health model, and preregisters clean successors on a future UTC boundary after authoritative preflight verification.

All institutional safety invariants remain strictly intact:
- **Execution**: `DISABLED` (zero order generation, zero live execution code paths).
- **Final Holdout**: `SEALED` (unaccessed).
- **Direction Engine**: `NONE` (strictly directionless opportunity movement).
- **Evidence Policy**: Immutable forward history (zero backfill, zero row deletion, zero moving historical start times).

---

## 2. Key Deliverables & Artifacts

All version deliverables are compiled and verified under `deliverables/v0.3.21/`:
1. `TERMINAL_STATE_RECONCILIATION.json`: Authoritative canonical record marking `DERIVATIVES_PIT_EPOCH_V0320_001` and `H37` as terminal.
2. `LOCAL_RUNTIME_RESILIENCE_REPORT.json`: Complete audit of WSL systemd linger, power standby profiles, disk free space, SQLite integrity, and network egress.
3. `LOCAL_FORWARD_PREFLIGHT.json`: Machine-readable diagnostic preflight from `quantctl forward-evidence doctor`.
4. `SUCCESSOR_PREREGISTRATION_MANIFEST.json`: Preregistration manifest for clean successors starting at `2026-09-03T18:00:00Z`.
5. `V0.3.21_FORWARD_LOCAL_RECOVERY_REPORT.md`: In-depth engineering report detailing root cause analysis, architecture hardening, and test results.
6. `README.md`: This release summary document.

---

## 3. Core Architectural Improvements

### Phase A: Canonical Terminal State Reconciliation
- `configs/forward/derivatives_evidence_epochs.json`: `DERIVATIVES_PIT_EPOCH_V0320_001` permanently updated to `FAILED_GAP_GATE_TERMINAL` (`FORMAL_TERMINAL`, `terminal_at_ms: 1788420600000`).
- `configs/forward/opportunity_forward_campaigns.json`: `OPPORTUNITY_FORWARD_V0320_20260903T063000Z` (H37) permanently updated to `DATA_QUALITY_TERMINAL_ARCHIVE`.
- Independent microstructure capture (`MICROSTRUCTURE_CAPTURE_V0315_001`) remains active and healthy.

### Phase B: Fail-Closed Runtime Execution
- Eliminated blind execution against terminal chains. Collectors dynamically query `resolve_active_derivatives_epoch()` and `resolve_active_opportunity_campaign()`.
- If all registered campaigns are terminal, commands immediately log `REFUSED_NO_ACTIVE_EPOCH` or `REFUSED_NO_ACTIVE_CAMPAIGN` and exit cleanly without attempting network requests or modifying SQLite tables.
- Before reaching frozen start boundaries, commands log `REFUSED_PREREGISTERED_PENDING` and exit cleanly.

### Phase C: Collector / Resolver Parity Repair
- Fixed the configuration disparity where `btc-quant-opportunity-forward.service` pointed to v0.3.20 while `btc-quant-opportunity-resolve.service` pointed to v0.3.17.
- Both units now pass `--registry configs/forward/opportunity_forward_campaigns.json`, ensuring collector and resolver operate on identical active campaigns.
- Parity audit check integrated directly into `forward_doctor`.

### Phase D: Windows / WSL Local Resilience
- Automated WSL user linger verification (`Linger=yes`).
- Created `scripts/windows/recover_forward_wsl.ps1` to inspect WSL status, timer schedules, and warn of Windows Modern Standby (S0) power suspend risks.
- Storage free space monitoring ($833$ GB free), SQLite `PRAGMA quick_check` validation, and microstructure heartbeat monitoring ($< 2.5$s freshness).

### Phase E: Forward Doctor Typed Health Model
- Replaced binary health checks with a 10-state typed model:
  `HEALTHY`, `HEALTHY_ACCUMULATING`, `PREREGISTERED_NOT_STARTED`, `FORWARD_DATA_INSUFFICIENT`, `TERMINAL_BREACH`, `NETWORK_INELIGIBLE`, `CONFIGURATION_INCONSISTENT`, `SERVICE_UNHEALTHY`, `HOST_LIFECYCLE_AT_RISK`, `STORAGE_AT_RISK`.
- Evaluated and verified clean passing status `PREREGISTERED_NOT_STARTED`.

### Phase F: Fresh Successor Preregistration
- Verified healthy network egress via Tokyo, Japan node (`150.249.219.212`), returning HTTP 200 with zero HTTP 451.
- Preregistered clean successors on future UTC 15m boundary at `2026-09-03T18:00:00Z` (`1788458400000` ms, 48-minute buffer):
  - Derivatives: `DERIVATIVES_PIT_EPOCH_V0321_001`
  - Opportunity: `OPPORTUNITY_FORWARD_V0321_20260903T180000Z` (`H38_OPPORTUNITY_FORWARD_REPLICATION_LOCAL_RECOVERY`)

---

## 4. Verification Results

- **Unit & Integration Tests**: `434 passed in 12.08s` across the full test suite.
- **Resilience Suite**: `tests/test_v0321_resilience.py` (5 passed) verifying terminal refusal, parity checking, HTTP 451 fail-close, and preregistration detection.
- **Code Linter**: `ruff check .` passed with 0 violations.
- **Static Typing**: `mypy src` passed clean across all 73 source files.
- **Compilation**: `python -m compileall src tests` verified 100% clean bytecode compilation.
