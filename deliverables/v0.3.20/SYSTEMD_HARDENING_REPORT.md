# Systemd Unit Hardening & Deployment Resilience Report (v0.3.20)

## 1. Problem Diagnosis

Prior to v0.3.20, user-level systemd units had four primary architectural deficiencies:
1. **Hardcoded File System Paths**: Scripts like `install-user-forward-derivatives.sh` had hard assertions on `/root/workspace/project/Quant-agent`, blocking installation in custom user directories, standard paths (e.g. `/opt/btc-quant-agent`), or on external Linux VPS hosts.
2. **Missing Exit Status Tolerance (`SuccessExitStatus`)**: When an opportunity scan was missed (e.g. during an outage or network disconnect), the CLI correctly recorded `MISSED_DECISION_SLOT` and exited with return code 2. Systemd interpreted exit code 2 as an unhandled service crash (`status=failed`), masking transient data gaps as system crashes.
3. **Absence of User Linger Assertion**: Closing interactive terminal shells in WSL caused systemd to teardown the user session, stopping timers silently.
4. **Heartbeat Thread Termination on SQLite Lock**: In `btc-quant-microstructure-forward.service`, if SQLite was busy during status queries, unhandled `OperationalError: database is locked` crashed the heartbeat worker thread while the parent process remained alive, producing a permanently stale heartbeat status.

---

## 2. Hardening Measures Implemented

### A. Parameterized & Path-Configurable Installer
`deploy/systemd/install-all-forward-services.sh` dynamically templates unit files based on the actual repository location:
- Replaces repository base path dynamically.
- Verifies and auto-enables user linger (`loginctl enable-linger`).
- Installs network environment overrides in `~/.config/btc-quant-agent/network.env`.

### B. Exit Code Normalization
Added `SuccessExitStatus=0 2` to oneshot services:
- `btc-quant-opportunity-forward.service`
- `btc-quant-forward-derivatives.service`
- `btc-quant-forward-health.service`
Now, normal missed-slot recordings terminate cleanly without marking the unit as failed.

### C. Self-Healing Daemon Architecture
In `src/btc_quant_agent/microstructure.py`:
- `heartbeat_worker` thread wraps `store.heartbeat()` in try/except to absorb transient SQLite lock contentions.
- An asynchronous supervisor task (`supervisor_loop()`) continuously monitors thread liveness and automatically respawns the heartbeat thread if it ever crashes.

### D. Subcommand Additions to CLI
- `quantctl forward-evidence doctor`: Comprehensive health diagnostic reporting systemd unit states, timer schedules, SQLite chain status, disk free space, proxy reachability, and HTTP 451 detection.
- `quantctl forward-evidence recover-services`: Safely resets failed units and restarts services without risking database mutations or retrospective backfills.
