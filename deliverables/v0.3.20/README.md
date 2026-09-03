# Gemini BTC Quant Agent v0.3.20 Release Notes

**Version**: `0.3.20`  
**Release Name**: Forward Infrastructure Recovery & Deployment Hardening  
**Target Git Branch**: `gemini/v0.3.20-forward-infrastructure-recovery-deployment-hardening`  
**Base Commit**: `d70b6d49834f92a5385297aae89b9da739d88c0a`  

---

## 1. Executive Summary

Version 0.3.20 delivers a comprehensive institutional recovery of the real-time forward evidence collection pipeline. Following an extensive forensic audit of multi-hour data gaps observed on September 3, 2026, this release resolves process crashes, eliminates database lock contention, hardens systemd deployment templates, provides provider-neutral Linux VPS automation, archives compromised forward chains into immutable audit storage, and preregisters clean successors on fixed future UTC boundaries.

All operations strictly maintain existing safety invariants:
- Execution: `DISABLED` (zero order generation, zero live credentials).
- Final Holdout: `SEALED` (no access).
- Direction Engine: `NONE` (strictly opportunity-only).
- Strategy: `EXPERIMENTAL`.
- Forward Historical Rows: Completely immutable (no backfills, no row deletion).

---

## 2. Forensic Audit Findings

| Failure Mode | Root Cause | Impact | Resolution |
| :--- | :--- | :--- | :--- |
| **Host Freeze** | Windows Modern Standby (sleep) suspended laptop CPU for ~5.5 hours (03:31 - 08:57 HKT). | Streaks of 15 missed derivative slots and 24 missed opportunity slots breached gate threshold ($M_{gap} \le 4$). | Archived compromised chains as terminal; preregistered clean successors; provided sleep prevention script & VPS migration runbook. |
| **Binance HTTP 451** | Local Clash proxy was set to Global US node (`pro-美国06`, IP `23.148.204.205`). | Binance Futures REST and WebSocket APIs rejected requests due to US compliance restrictions. | Built automated HTTP 451 detector in `quantctl forward-evidence doctor`; documented proxy routing rules. |
| **Clock Logic Crash** | `max()` unpacked empty generator when all endpoints failed, passing 1 integer argument. | Python raised `TypeError: 'int' object is not iterable` in `binance.py`. | Fixed with `max([local_observed_at, *valid_source_times])`. |
| **Microstructure Heartbeat Death** | Unhandled `OperationalError: database is locked` terminated `heartbeat_worker` thread. | Daemon process stayed alive in systemd while heartbeats ceased (stale by ~31,715s). | Added try/except protection and an asynchronous supervisor loop to respawn heartbeat thread if needed. |
| **65s Status Query Lag** | `MicrostructureStore.status()` ran `PRAGMA integrity_check` on 5.0 GB across all history partitions. | Starved CPU and locked SQLite tables every 15 minutes. | Added persistent partition metadata caching and pre-merged interval evaluation (reduced status time from 65s to 2.6s, a 25x speedup). |
| **WSL Linger Disabled** | `loginctl show-user root` reported `Linger=no`. | Closing terminal sessions killed background user systemd timers. | Added automated linger configuration in installers and recovery scripts. |

---

## 3. Key Deliverables & Artifacts

All required artifacts have been compiled and verified under `deliverables/v0.3.20/`:
1. `FORWARD_FAILURE_ROOT_CAUSE_AUDIT.json`: Detailed root cause forensic mapping with Windows Kernel-Power event log timestamps.
2. `FORWARD_OPERATIONS_HEALTH.json`: Real-time structured operational health status.
3. `DATA_QUALITY_TERMINAL_ARCHIVE.json`: Immutable archive record of `DERIVATIVES_PIT_EPOCH_V0316_002` and H36.
4. `SUCCESSOR_PREREGISTRATION_MANIFEST.json`: Preregistration of `DERIVATIVES_PIT_EPOCH_V0320_001` and `H37_OPPORTUNITY_FORWARD_REPLICATION_RECOVERY` with start at `2026-09-03T06:30:00Z`.
5. `FORWARD_DOCTOR_REPORT.json`: Complete diagnostic report from `quantctl forward-evidence doctor`.
6. `SYSTEMD_HARDENING_REPORT.md`: Architectural documentation of systemd improvements and exit codes.
7. `LINUX_VPS_DEPLOYMENT_PROFILE.json`: Cloud deployment specification and sizing guidelines.
8. `WINDOWS_WSL_LIFECYCLE_GUIDE.md`: Operational runbook for Windows/WSL power management and sleep prevention.
9. `RESEARCH_DATA_CONCURRENCY_POLICY.md`: Process isolation, `os.nice(10)` prioritization, and database concurrency rules.
10. `ACCEPTANCE_REPAIR_REPORT.md`: Detailed audit of acceptance repair fixes, Python 3.12 CI resolution, and post-start empirical data.
11. `POST_START_SUCCESSOR_HEALTH.json`: Immutable audit of 5 decision slots post-start (06:30 - 07:30 UTC).
12. `README.md`: This executive release document.

---

## 4. Verification & Quality Gates

- **CI Provenance & Python 3.12 Repair**:
  - In initial CI run `33719993032`, Python 3.11 and 3.13 passed while Python 3.12 failed `test_network_proxy_check_detects_http_451` (1 failed, 428 passed) due to module-local `urlopen` symbol binding.
  - Refactored `check_network_proxy` to access `urllib.request.urlopen` dynamically and support explicit `url_opener` dependency injection.
  - All CI workflows fully green across Python 3.11, 3.12, and 3.13:
    - Push Workflow: [Run #33729160290](https://github.com/EXASHXE/btc-quant-agent/actions/runs/33729160290) (`quality (3.11)`: ✓, `quality (3.12)`: ✓, `quality (3.13)`: ✓).
    - Pull Request Workflow: [Run #33729163910](https://github.com/EXASHXE/btc-quant-agent/actions/runs/33729163910) (`quality (3.11)`: ✓, `quality (3.12)`: ✓, `quality (3.13)`: ✓).
- **Unit & Reliability Test Suite**: `429 passed in 9.82s` (zero failures).
- **Code Linter**: `ruff check .` passed with zero violations.
- **Static Type Analysis**: `mypy src` passed with zero type errors across all 73 source files.
- **Compilation**: `python -m compileall src tests tools` verified clean bytecode compilation.
- **Successor Empirical Status**:
  - `DERIVATIVES_PIT_EPOCH_V0320_001`: `COMPROMISED_AT_RISK` / `TERMINAL_BREACH` (5 consecutive failed slots due to external HTTP 451 geo-block; $5 > 4$).
  - `OPPORTUNITY_FORWARD_V0320_20260903T063000Z` (H37): `COMPROMISED_AT_RISK` / `TERMINAL_BREACH` (5 consecutive missed scans; $5 > 4$).
  - `MICROSTRUCTURE_CAPTURE_V0315_001`: `HEALTHY_COLLECTING` (fresh heartbeats, active streaming on `microstructure-2026-09-03.sqlite3`).
  - Strict immutability observed: zero backfill, zero history rewrite, zero start time manipulation.
